"""Versioned and checksum-verified model bundles for optional D3 inference."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .learning import (
    EDGE_FEATURE_NAMES,
    LEARNING_RESIDUAL_SCHEMA_V1,
    FeatureDistributionGuard,
    LearningAssistConfig,
    LearningCostAssistant,
    ResidualPrediction,
)
from .learning_data import (
    LEARNING_DATASET_SCHEMA_V2,
    LEARNING_DATASET_SPLIT_POLICY_V2,
)
from .native_ppo import (
    SHARED_EDGE_ACTOR_CRITIC_POLICY_V1,
    SharedEdgeActorCriticPolicy,
    torch,
)


MODEL_BUNDLE_SCHEMA_V1 = "d3_learning_model_bundle_v1"
MODEL_BUNDLE_SCHEMA_V2 = "d3_learning_model_bundle_v2"
MODEL_BUNDLE_SCHEMA_V3 = "d3_learning_model_bundle_v3"
MODEL_BUNDLE_MANIFEST_FILENAME = "manifest.json"
MODEL_BUNDLE_STATE_DICT_FILENAME = "state_dict.pt"
PROMOTION_EVIDENCE_SCHEMA_V1 = "d3_shadow_promotion_evidence_v1"
PROMOTION_EVIDENCE_KIND = "paired_rule_residual_shadow"
PROMOTION_COST_BASIS = "rule_cost_matrix_v1"
ASSIST_EVIDENCE_ASSEMBLER_UNAVAILABLE_REASON = (
    "bundle_assist_evidence_assembler_unavailable"
)


@dataclass(frozen=True)
class ModelBundleManifest:
    bundle_schema_version: str
    dataset_schema_version: str
    split_policy_version: str
    feature_schema_version: str
    feature_names: tuple[str, ...]
    policy_version: str
    provenance: Mapping[str, Any]
    admission: Mapping[str, Any]
    split_hash: str
    dataset_frames_sha256: str
    normalization_mean: tuple[float, ...]
    normalization_scale: tuple[float, ...]
    alpha: float
    min_confidence: float
    ood_z_threshold: float
    deadline_s: float
    training_results: Mapping[str, Any]
    promotion_manifest: Mapping[str, Any]
    model_config: Mapping[str, Any]
    state_dict_file: str
    state_dict_sha256: str

    def __post_init__(self) -> None:
        if self.bundle_schema_version not in {
            MODEL_BUNDLE_SCHEMA_V2,
            MODEL_BUNDLE_SCHEMA_V3,
        }:
            raise ValueError("unsupported D3 model bundle schema")
        if self.dataset_schema_version != LEARNING_DATASET_SCHEMA_V2:
            raise ValueError("unsupported D3 model bundle dataset schema")
        if self.split_policy_version != LEARNING_DATASET_SPLIT_POLICY_V2:
            raise ValueError("unsupported D3 model bundle split policy")
        if self.feature_schema_version != LEARNING_RESIDUAL_SCHEMA_V1:
            raise ValueError("unsupported D3 model feature schema")
        if self.feature_names != EDGE_FEATURE_NAMES:
            raise ValueError("model bundle feature names do not match D3")
        if self.policy_version != SHARED_EDGE_ACTOR_CRITIC_POLICY_V1:
            raise ValueError("unsupported D3 model policy version")
        if not all(
            _is_sha256(value)
            for value in (
                self.split_hash,
                self.dataset_frames_sha256,
                self.state_dict_sha256,
            )
        ):
            raise ValueError("split, dataset frame, and state_dict SHA256 are required")
        mean = np.asarray(self.normalization_mean, dtype=float)
        scale = np.asarray(self.normalization_scale, dtype=float)
        if mean.shape != (len(EDGE_FEATURE_NAMES),) or scale.shape != mean.shape:
            raise ValueError("bundle normalization statistics have the wrong shape")
        if not np.all(np.isfinite(mean)) or not np.all(np.isfinite(scale)):
            raise ValueError("bundle normalization statistics must be finite")
        if np.any(scale <= 0.0):
            raise ValueError("bundle normalization scale must be positive")
        guardrails = (
            self.alpha,
            self.min_confidence,
            self.ood_z_threshold,
            self.deadline_s,
        )
        if not all(isfinite(float(value)) for value in guardrails):
            raise ValueError("bundle guardrails must be finite")
        if self.alpha < 0.0 or not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("bundle alpha or confidence guardrail is invalid")
        if self.ood_z_threshold <= 0.0 or self.deadline_s <= 0.0:
            raise ValueError("bundle OOD and deadline guardrails must be positive")
        if Path(self.state_dict_file).name != self.state_dict_file:
            raise ValueError("state_dict_file must be a bundle-local filename")
        if self.bundle_schema_version == MODEL_BUNDLE_SCHEMA_V3:
            _validate_v3_provenance(self.provenance)
            _validate_v3_admission(self.admission)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "bundle_schema_version": self.bundle_schema_version,
            "dataset_schema_version": self.dataset_schema_version,
            "split_policy_version": self.split_policy_version,
            "feature_schema_version": self.feature_schema_version,
            "feature_names": list(self.feature_names),
            "policy_version": self.policy_version,
            "split_hash": self.split_hash,
            "dataset_frames_sha256": self.dataset_frames_sha256,
            "normalization": {
                "mean": [float(value) for value in self.normalization_mean],
                "scale": [float(value) for value in self.normalization_scale],
            },
            "guardrails": {
                "alpha": float(self.alpha),
                "min_confidence": float(self.min_confidence),
                "ood_z_threshold": float(self.ood_z_threshold),
                "deadline_s": float(self.deadline_s),
            },
            "training_results": _json_safe(self.training_results),
            "promotion_manifest": _json_safe(self.promotion_manifest),
            "model_config": _json_safe(self.model_config),
            "state_dict": {
                "file": self.state_dict_file,
                "sha256": self.state_dict_sha256,
                "load_policy": "torch_weights_only_true",
            },
        }
        if self.bundle_schema_version == MODEL_BUNDLE_SCHEMA_V3:
            payload["provenance"] = _json_safe(self.provenance)
            payload["admission"] = _json_safe(self.admission)
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ModelBundleManifest":
        bundle_schema_version = str(value["bundle_schema_version"])
        normalization = value["normalization"]
        guardrails = value["guardrails"]
        state_dict = value["state_dict"]
        return cls(
            bundle_schema_version=bundle_schema_version,
            dataset_schema_version=str(value["dataset_schema_version"]),
            split_policy_version=str(value["split_policy_version"]),
            feature_schema_version=str(value["feature_schema_version"]),
            feature_names=tuple(str(item) for item in value["feature_names"]),
            policy_version=str(value["policy_version"]),
            provenance=(
                dict(value["provenance"])
                if bundle_schema_version == MODEL_BUNDLE_SCHEMA_V3
                else {"legacy_bundle_schema": MODEL_BUNDLE_SCHEMA_V2}
            ),
            admission=(
                dict(value["admission"])
                if bundle_schema_version == MODEL_BUNDLE_SCHEMA_V3
                else {"stage": "legacy_promotion_contract"}
            ),
            split_hash=str(value["split_hash"]),
            dataset_frames_sha256=str(value["dataset_frames_sha256"]),
            normalization_mean=tuple(float(item) for item in normalization["mean"]),
            normalization_scale=tuple(float(item) for item in normalization["scale"]),
            alpha=float(guardrails["alpha"]),
            min_confidence=float(guardrails["min_confidence"]),
            ood_z_threshold=float(guardrails["ood_z_threshold"]),
            deadline_s=float(guardrails["deadline_s"]),
            training_results=dict(value["training_results"]),
            promotion_manifest=dict(value["promotion_manifest"]),
            model_config=dict(value["model_config"]),
            state_dict_file=str(state_dict["file"]),
            state_dict_sha256=str(state_dict["sha256"]),
        )


@dataclass(frozen=True)
class ModelBundleLoadResult:
    loaded: bool
    fallback_reason: str | None
    assistant: Any
    policy: SharedEdgeActorCriticPolicy | None
    manifest: ModelBundleManifest | None


class NormalizedPolicyPredictor:
    """Apply train-split normalization before policy residual inference."""

    def __init__(
        self,
        policy: SharedEdgeActorCriticPolicy,
        mean: Sequence[float],
        scale: Sequence[float],
    ) -> None:
        self.policy = policy
        self.mean = np.asarray(mean, dtype=np.float32).reshape(-1)
        self.scale = np.asarray(scale, dtype=np.float32).reshape(-1)

    def predict(self, features: np.ndarray) -> ResidualPrediction:
        matrix = np.asarray(features, dtype=np.float32)
        return self.policy.predict((matrix - self.mean) / self.scale)


class RuleFallbackLearningAssistant:
    """Preserve exact rule costs while exposing a stable bundle fallback reason."""

    def __init__(self, reason: str, *, mode: str) -> None:
        self.reason = str(reason)
        self.mode = str(mode)

    def apply(
        self,
        matrix_result: Any,
        tracks: Any,
        resources: Any,
        *,
        expected_previous_version: int,
        current_plan_version: int,
        previous_plan: Any = None,
    ) -> Any:
        del tracks, resources, previous_plan
        reason = (
            "version_constraint"
            if int(expected_previous_version) != int(current_plan_version)
            else self.reason
        )
        candidate_mask = matrix_result.hard_safe_candidate_mask
        if reason == "version_constraint":
            candidate_mask.fill(False)
        return replace(
            matrix_result,
            matrix=np.asarray(matrix_result.matrix, dtype=float).copy(),
            candidate_mask=candidate_mask,
            metadata={
                **dict(matrix_result.metadata),
                "learning_residual_schema": LEARNING_RESIDUAL_SCHEMA_V1,
                "learning_mode": self.mode,
                "learning_applied": False,
                "learning_shadow_only": False,
                "learning_bundle_loaded": False,
                "learning_fallback_reason": reason,
                "learning_expected_previous_version": int(expected_previous_version),
                "learning_current_plan_version": int(current_plan_version),
            },
        )


def unavailable_promotion_manifest(
    reason: str = "insufficient_unseen_seed_evidence",
    *,
    split_hash: str = "",
    dataset_frames_sha256: str = "",
    model_state_dict_sha256: str = "",
) -> dict[str, Any]:
    return {
        "evidence_schema_version": PROMOTION_EVIDENCE_SCHEMA_V1,
        "evidence_kind": PROMOTION_EVIDENCE_KIND,
        "cost_basis": PROMOTION_COST_BASIS,
        "dataset_schema_version": LEARNING_DATASET_SCHEMA_V2,
        "split_policy_version": LEARNING_DATASET_SPLIT_POLICY_V2,
        "seed_identity_scope": "numeric_seed_global_across_scenarios",
        "evaluated_split": "none",
        "evidence_eligible": False,
        "evidence_hashes_bound": False,
        "split_hash": str(split_hash),
        "dataset_frames_sha256": str(dataset_frames_sha256),
        "model_state_dict_sha256": str(model_state_dict_sha256),
        "promotion_recommended": False,
        "promotion_status": "unavailable",
        "unseen_seed_count": 0,
        "minimum_unseen_seed_count": 20,
        "safety_non_degradation": False,
        "assignment_cost_non_degradation": False,
        "fallback_frame_count": 0,
        "reason": str(reason),
    }


def save_model_bundle(
    output_dir: str | Path,
    policy: SharedEdgeActorCriticPolicy,
    *,
    split_hash: str,
    dataset_frames_sha256: str,
    dataset_schema_version: str = LEARNING_DATASET_SCHEMA_V2,
    split_policy_version: str = LEARNING_DATASET_SPLIT_POLICY_V2,
    normalization_mean: Sequence[float],
    normalization_scale: Sequence[float],
    training_results: Mapping[str, Any],
    promotion_manifest: Mapping[str, Any] | None = None,
    alpha: float = 0.25,
    min_confidence: float = 0.6,
    ood_z_threshold: float = 6.0,
    deadline_s: float = 0.05,
    provenance: Mapping[str, Any] | None = None,
    admission: Mapping[str, Any] | None = None,
    promotion_unavailable_reason: str = "insufficient_unseen_seed_evidence",
) -> ModelBundleManifest:
    """Save an unqualified research bundle and its promotion manifest.

    A qualified assist bundle must eventually be created by a separate
    evidence assembler that validates D6-owned source artifacts. Until that
    assembler exists, caller-provided positive admission fields are rejected.
    """

    if torch is None:  # pragma: no cover
        raise ImportError("PyTorch is required to save a D3 model bundle")
    if (provenance is None) != (admission is None):
        raise ValueError("bundle provenance and admission must be provided together")
    bundle_schema = (
        MODEL_BUNDLE_SCHEMA_V3
        if provenance is not None
        else MODEL_BUNDLE_SCHEMA_V2
    )
    if bundle_schema == MODEL_BUNDLE_SCHEMA_V3:
        assert provenance is not None
        assert admission is not None
        _validate_v3_provenance(provenance)
        _validate_v3_admission(admission)
        if _admission_allows_assist(admission):
            raise ValueError(
                "D3 assist admission evidence assembler is unavailable; "
                "the production writer rejects caller-provided qualified admission"
            )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / MODEL_BUNDLE_STATE_DICT_FILENAME
    state_dict = {
        str(key): tensor.detach().cpu()
        for key, tensor in policy.state_dict().items()
    }
    torch.save(state_dict, state_path)
    state_sha = _file_sha256(state_path)
    manifest = ModelBundleManifest(
        bundle_schema_version=bundle_schema,
        dataset_schema_version=str(dataset_schema_version),
        split_policy_version=str(split_policy_version),
        feature_schema_version=LEARNING_RESIDUAL_SCHEMA_V1,
        feature_names=EDGE_FEATURE_NAMES,
        policy_version=SHARED_EDGE_ACTOR_CRITIC_POLICY_V1,
        provenance=dict(provenance or {"legacy_bundle_schema": MODEL_BUNDLE_SCHEMA_V2}),
        admission=dict(admission or {"stage": "legacy_promotion_contract"}),
        split_hash=str(split_hash),
        dataset_frames_sha256=str(dataset_frames_sha256),
        normalization_mean=tuple(float(value) for value in normalization_mean),
        normalization_scale=tuple(float(value) for value in normalization_scale),
        alpha=float(alpha),
        min_confidence=float(min_confidence),
        ood_z_threshold=float(ood_z_threshold),
        deadline_s=float(deadline_s),
        training_results=dict(training_results),
        promotion_manifest=dict(
            promotion_manifest
            or unavailable_promotion_manifest(
                reason=str(promotion_unavailable_reason),
                split_hash=str(split_hash),
                dataset_frames_sha256=str(dataset_frames_sha256),
                model_state_dict_sha256=state_sha,
            )
        ),
        model_config={
            "feature_count": int(policy.feature_count),
            "hidden_size": int(policy.hidden_size),
            "residual_bound": float(policy.residual_bound),
            "action_space": "current_sparse_candidate_edges_plus_low_frequency_advice",
            "assignment_output": False,
        },
        state_dict_file=MODEL_BUNDLE_STATE_DICT_FILENAME,
        state_dict_sha256=state_sha,
    )
    manifest_path = output / MODEL_BUNDLE_MANIFEST_FILENAME
    with manifest_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest.to_dict(), stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")
    return manifest


def load_model_bundle(
    bundle_dir: str | Path,
    *,
    mode: str = "shadow",
    expected_split_hash: str | None = None,
    expected_dataset_frames_sha256: str | None = None,
    require_promotion_for_assist: bool = True,
) -> ModelBundleLoadResult:
    """Safely load a bundle or return an exact-rule fallback assistant."""

    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in {"shadow", "assist"}:
        raise ValueError("bundle mode must be shadow or assist")
    path = Path(bundle_dir)

    def fallback(
        reason: str,
        manifest: ModelBundleManifest | None = None,
    ) -> ModelBundleLoadResult:
        return ModelBundleLoadResult(
            loaded=False,
            fallback_reason=reason,
            assistant=RuleFallbackLearningAssistant(reason, mode=normalized_mode),
            policy=None,
            manifest=manifest,
        )

    manifest_path = path / MODEL_BUNDLE_MANIFEST_FILENAME
    if not path.is_dir() or not manifest_path.is_file():
        return fallback("model_bundle_missing")
    try:
        with manifest_path.open(encoding="utf-8") as stream:
            raw_manifest = json.load(stream)
        if not isinstance(raw_manifest, Mapping):
            raise TypeError("model bundle manifest must be a JSON object")
        if raw_manifest.get("bundle_schema_version") not in {
            MODEL_BUNDLE_SCHEMA_V2,
            MODEL_BUNDLE_SCHEMA_V3,
        }:
            return fallback("model_bundle_schema_unsupported")
        if (
            raw_manifest.get("dataset_schema_version") != LEARNING_DATASET_SCHEMA_V2
            or raw_manifest.get("split_policy_version")
            != LEARNING_DATASET_SPLIT_POLICY_V2
        ):
            return fallback("model_dataset_contract_unsupported")
        manifest = ModelBundleManifest.from_dict(raw_manifest)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return fallback("model_manifest_invalid")
    if expected_split_hash is not None and manifest.split_hash != expected_split_hash:
        return fallback("split_hash_mismatch", manifest)
    if (
        expected_dataset_frames_sha256 is not None
        and manifest.dataset_frames_sha256 != expected_dataset_frames_sha256
    ):
        return fallback("dataset_frames_sha256_mismatch", manifest)
    if (
        normalized_mode == "assist"
        and require_promotion_for_assist is not True
    ):
        return fallback("promotion_bypass_forbidden", manifest)
    if (
        normalized_mode == "assist"
        and manifest.bundle_schema_version != MODEL_BUNDLE_SCHEMA_V3
    ):
        return fallback("bundle_assist_admission_missing", manifest)
    if (
        normalized_mode == "assist"
        and not _admission_allows_assist(manifest.admission)
    ):
        return fallback("bundle_shadow_only", manifest)
    if (
        normalized_mode == "assist"
        and not _promotion_is_authorized(manifest.promotion_manifest, manifest)
    ):
        return fallback("promotion_not_recommended", manifest)
    if normalized_mode == "assist":
        return fallback(ASSIST_EVIDENCE_ASSEMBLER_UNAVAILABLE_REASON, manifest)
    state_path = path / manifest.state_dict_file
    if not state_path.is_file():
        return fallback("model_state_missing", manifest)
    try:
        actual_sha = _file_sha256(state_path)
    except OSError:
        return fallback("model_state_unreadable", manifest)
    if actual_sha != manifest.state_dict_sha256:
        return fallback("state_dict_sha256_mismatch", manifest)
    if torch is None:  # pragma: no cover
        return fallback("pytorch_unavailable", manifest)
    try:
        state_dict = torch.load(state_path, map_location="cpu", weights_only=True)
        if not isinstance(state_dict, Mapping) or not all(
            isinstance(key, str) and torch.is_tensor(value)
            for key, value in state_dict.items()
        ):
            raise TypeError("state_dict is not a tensor mapping")
        policy = SharedEdgeActorCriticPolicy(
            feature_count=int(manifest.model_config["feature_count"]),
            hidden_size=int(manifest.model_config["hidden_size"]),
            residual_bound=float(manifest.model_config["residual_bound"]),
        )
        policy.load_state_dict(state_dict, strict=True)
        policy.eval()
    except (KeyError, RuntimeError, TypeError, ValueError, OSError):
        return fallback("model_state_invalid", manifest)
    guard = FeatureDistributionGuard(
        mean=np.asarray(manifest.normalization_mean, dtype=np.float32),
        scale=np.asarray(manifest.normalization_scale, dtype=np.float32),
        feature_names=manifest.feature_names,
    )
    assistant = LearningCostAssistant(
        NormalizedPolicyPredictor(
            policy, manifest.normalization_mean, manifest.normalization_scale
        ),
        config=LearningAssistConfig(
            mode=normalized_mode,
            alpha=manifest.alpha,
            timeout_s=manifest.deadline_s,
            min_confidence=manifest.min_confidence,
            ood_z_threshold=manifest.ood_z_threshold,
        ),
        distribution_guard=guard,
    )
    return ModelBundleLoadResult(
        loaded=True,
        fallback_reason=None,
        assistant=assistant,
        policy=policy,
        manifest=manifest,
    )


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _promotion_is_authorized(
    value: Mapping[str, Any],
    manifest: ModelBundleManifest,
) -> bool:
    raw_counts = (
        value.get("unseen_seed_count"),
        value.get("minimum_unseen_seed_count"),
        value.get("fallback_frame_count"),
    )
    if any(isinstance(item, bool) or not isinstance(item, int) for item in raw_counts):
        return False
    unseen_seed_count, minimum_seed_count, fallback_frame_count = raw_counts
    if minimum_seed_count < 20 or unseen_seed_count < 0 or fallback_frame_count < 0:
        return False
    return bool(
        value.get("evidence_schema_version") == PROMOTION_EVIDENCE_SCHEMA_V1
        and value.get("evidence_kind") == PROMOTION_EVIDENCE_KIND
        and value.get("cost_basis") == PROMOTION_COST_BASIS
        and value.get("dataset_schema_version") == LEARNING_DATASET_SCHEMA_V2
        and value.get("split_policy_version") == LEARNING_DATASET_SPLIT_POLICY_V2
        and value.get("seed_identity_scope")
        == "numeric_seed_global_across_scenarios"
        and value.get("evaluated_split") == "test"
        and value.get("evidence_eligible") is True
        and value.get("evidence_hashes_bound") is True
        and value.get("split_hash") == manifest.split_hash
        and value.get("dataset_frames_sha256")
        == manifest.dataset_frames_sha256
        and value.get("model_state_dict_sha256") == manifest.state_dict_sha256
        and value.get("promotion_recommended") is True
        and value.get("promotion_status") == "recommended"
        and value.get("safety_non_degradation") is True
        and value.get("assignment_cost_non_degradation") is True
        and unseen_seed_count >= minimum_seed_count
        and fallback_frame_count == 0
    )


def _is_sha256(value: Any) -> bool:
    text = str(value)
    return len(text) == 64 and set(text).issubset(frozenset("0123456789abcdef"))


def development_shadow_admission(
    external_holdout_seed_values: Sequence[int] = tuple(range(1000, 1020)),
) -> dict[str, Any]:
    """Return the fail-closed admission state for a development BC bundle."""

    return {
        "stage": "development",
        "allowed_modes": ["shadow"],
        "assist_authorized": False,
        "external_holdout_status": "not_evaluated",
        "external_holdout_seed_values": [
            int(value) for value in external_holdout_seed_values
        ],
        "rule_fallback_required": True,
    }


def _validate_v3_provenance(value: Mapping[str, Any]) -> None:
    expected = {
        "repository_git_commit",
        "repository_git_commit_role",
        "training_worktree_state",
        "training_date",
        "dataset_manifest_sha256",
        "training_source_sha256",
        "training_entrypoint",
    }
    if set(value) != expected:
        raise ValueError("v3 bundle provenance fields are invalid")
    commit = str(value["repository_git_commit"])
    if len(commit) not in {40, 64} or not set(commit).issubset(
        frozenset("0123456789abcdef")
    ):
        raise ValueError("repository_git_commit must be a hexadecimal Git object ID")
    if value["repository_git_commit_role"] not in {
        "exact_training_source_commit",
        "dataset_and_training_base_commit",
    }:
        raise ValueError("repository_git_commit_role is invalid")
    if value["training_worktree_state"] not in {
        "clean",
        "module_changes_present_source_sha256_bound",
    }:
        raise ValueError("training_worktree_state is invalid")
    if not _is_sha256(value["dataset_manifest_sha256"]) or not _is_sha256(
        value["training_source_sha256"]
    ):
        raise ValueError("v3 bundle provenance SHA256 values are invalid")
    try:
        date.fromisoformat(str(value["training_date"]))
    except ValueError as exc:
        raise ValueError("v3 bundle training_date must be ISO-8601") from exc
    if not str(value["training_entrypoint"]).strip():
        raise ValueError("v3 bundle training_entrypoint is required")


def _validate_v3_admission(value: Mapping[str, Any]) -> None:
    expected = {
        "stage",
        "allowed_modes",
        "assist_authorized",
        "external_holdout_status",
        "external_holdout_seed_values",
        "rule_fallback_required",
    }
    if set(value) != expected:
        raise ValueError("v3 bundle admission fields are invalid")
    stage = str(value["stage"])
    allowed_modes = tuple(str(item) for item in value["allowed_modes"])
    seeds = tuple(int(item) for item in value["external_holdout_seed_values"])
    if stage not in {"development", "qualified", "retired"}:
        raise ValueError("v3 bundle admission stage is invalid")
    if not allowed_modes or any(item not in {"shadow", "assist"} for item in allowed_modes):
        raise ValueError("v3 bundle allowed modes are invalid")
    if tuple(sorted(set(seeds))) != seeds or len(seeds) < 20:
        raise ValueError("v3 bundle requires at least 20 sorted holdout seeds")
    if value["rule_fallback_required"] is not True:
        raise ValueError("v3 bundle must require deterministic rule fallback")
    if not isinstance(value["assist_authorized"], bool):
        raise ValueError("v3 bundle assist authorization must be boolean")
    status = str(value["external_holdout_status"])
    if stage == "development" and (
        allowed_modes != ("shadow",)
        or value["assist_authorized"] is not False
        or status != "not_evaluated"
    ):
        raise ValueError("development bundles must remain shadow-only")
    if stage == "qualified" and (
        "assist" not in allowed_modes
        or value["assist_authorized"] is not True
        or status != "passed"
    ):
        raise ValueError("qualified bundles require passed external holdout evidence")


def _admission_allows_assist(value: Mapping[str, Any]) -> bool:
    try:
        _validate_v3_admission(value)
    except (TypeError, ValueError):
        return False
    return bool(
        value.get("stage") == "qualified"
        and "assist" in value.get("allowed_modes", ())
        and value.get("assist_authorized") is True
        and value.get("external_holdout_status") == "passed"
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("bundle JSON cannot contain non-finite values")
        return value
    raise TypeError(f"bundle value is not JSON serializable: {type(value).__name__}")
