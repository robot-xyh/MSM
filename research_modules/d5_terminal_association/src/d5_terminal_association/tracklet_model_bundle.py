"""Validated model bundles and calibrated online edge-probability scoring."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
import torch

from .sparse_tracklet_graph import EDGE_FEATURE_NAMES, NODE_FEATURE_NAMES, SparseTrackletGraph
from .tracklet_dataset import (
    DATASET_SCHEMA_VERSION,
    EDGE_FEATURE_VERSION,
    GRAPH_SCHEMA_VERSION,
    NODE_FEATURE_VERSION,
    sha256_file,
    sha256_json,
)
from .tracklet_gnn import NativeTrackletEdgeClassifier, graph_tensors


MODEL_BUNDLE_SCHEMA_VERSION = "d5.tracklet-model-bundle.v3"
LEGACY_G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION = (
    "d5.tracklet-model-bundle.v4"
)
G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION = "d5.tracklet-model-bundle.v5"
LEGACY_TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION = (
    "d5.tracklet-g1-admission-report.v1"
)
TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION = (
    "d5.tracklet-g1-admission-report.v2"
)
TRACKLET_G1_AUTHORITY_CONTRACT_SCHEMA_VERSION = (
    "d5.tracklet-g1-authority-contract.v2"
)
TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS = (
    "model_promotion_granted",
    "g1_assist_granted",
    "default_path_change_granted",
    "assignment_authority_granted",
    "failover_authority_granted",
    "control_authority_granted",
)
TRACKLET_G1_EXTERNAL_AUTHORITY_FIELDS = frozenset(
    {*TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS, "reason"}
)
MODEL_SEMANTIC_VERSION = "1.0.0"
WEIGHTS_FILENAME = "weights.pt"
MANIFEST_FILENAME = "manifest.json"
CHECKSUMS_FILENAME = "SHA256SUMS"
TRACKLET_G1_MINIMUM_UNSEEN_SEEDS = 20
TRACKLET_G1_MINIMUM_HELDOUT_EPISODES = 900
TRACKLET_G1_MINIMUM_SCENARIO_SCALE_CELLS = 45
TRACKLET_G1_REQUIRED_PAIRED_LINEAGE_RECORD_COUNT = 900
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_ADMISSION_STATUSES = frozenset(
    {"research_candidate_not_default", "development_only_fail_closed"}
)
G1_ASSIST_NOT_ELIGIBLE_REASON = "bundle_g1_assist_not_eligible"
G1_ASSIST_AUTHORITY_NOT_GRANTED_REASON = (
    "bundle_g1_assist_authority_not_granted"
)
RUNTIME_ADMISSION_REQUIREMENT_INVALID_REASON = (
    "bundle_runtime_admission_requirement_invalid"
)
_MODEL_IMPLEMENTATION_SOURCE_FILES = (
    "tracklet_gnn.py",
    "tracklet_model_bundle.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
)
_RUNTIME_IMPLEMENTATION_SOURCE_FILES = (
    "scalable_3d_adapter.py",
    "sparse_tracklet_graph.py",
    "tracklet_dataset.py",
    "tracklet_g1_evidence_assembler.py",
    "tracklet_gnn.py",
    "tracklet_heldout_evaluation.py",
    "tracklet_model_bundle.py",
    "tracklet_paired_shadow.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
)


class ModelBundleValidationError(ValueError):
    """Strict bundle-load failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class TrackletG1AuthorityContract:
    """Versioned evidence/authority boundary embedded in every new v5."""

    d6_external_audit_sha256: str
    d6_external_audit_content_sha256: str
    evidence_audit_passed: bool
    evidence_eligible: bool
    runtime_authority: Mapping[str, bool]
    reason: str
    schema_version: str = TRACKLET_G1_AUTHORITY_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRACKLET_G1_AUTHORITY_CONTRACT_SCHEMA_VERSION:
            raise ValueError("tracklet G1 authority contract schema mismatch")
        _validate_sha256(
            self.d6_external_audit_sha256,
            "authority_contract.d6_external_audit_sha256",
        )
        _validate_sha256(
            self.d6_external_audit_content_sha256,
            "authority_contract.d6_external_audit_content_sha256",
        )
        for name in ("evidence_audit_passed", "evidence_eligible"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"authority_contract.{name} must be bool")
        if self.evidence_eligible and not self.evidence_audit_passed:
            raise ValueError(
                "authority contract cannot be eligible without a passed audit"
            )
        authority = self.runtime_authority
        if not isinstance(authority, Mapping) or set(authority) != set(
            TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS
        ):
            raise ValueError(
                "authority contract runtime_authority fields mismatch"
            )
        normalized: dict[str, bool] = {}
        for name in TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS:
            value = authority[name]
            if type(value) is not bool:
                raise TypeError(
                    f"authority_contract.runtime_authority.{name} must be bool"
                )
            if value is not False:
                raise ValueError(
                    f"authority_contract.runtime_authority.{name} "
                    "must remain false"
                )
            normalized[name] = value
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("authority contract reason must be non-empty")
        object.__setattr__(
            self,
            "runtime_authority",
            MappingProxyType(normalized),
        )

    def to_manifest(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "schema_version": self.schema_version,
                "d6_external_audit_sha256": (
                    self.d6_external_audit_sha256
                ),
                "d6_external_audit_content_sha256": (
                    self.d6_external_audit_content_sha256
                ),
                "evidence_audit_passed": self.evidence_audit_passed,
                "evidence_eligible": self.evidence_eligible,
                "runtime_authority": {
                    name: self.runtime_authority[name]
                    for name in TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS
                },
                "reason": self.reason,
            }
        )

    @classmethod
    def from_manifest(
        cls,
        payload: Mapping[str, Any],
    ) -> TrackletG1AuthorityContract:
        required = {
            "schema_version",
            "d6_external_audit_sha256",
            "d6_external_audit_content_sha256",
            "evidence_audit_passed",
            "evidence_eligible",
            "runtime_authority",
            "reason",
        }
        if not isinstance(payload, Mapping) or set(payload) != required:
            raise ValueError("tracklet G1 authority contract fields mismatch")
        for name in (
            "schema_version",
            "d6_external_audit_sha256",
            "d6_external_audit_content_sha256",
            "reason",
        ):
            if not isinstance(payload[name], str):
                raise TypeError(f"authority_contract.{name} must be str")
        for name in ("evidence_audit_passed", "evidence_eligible"):
            if type(payload[name]) is not bool:
                raise TypeError(f"authority_contract.{name} must be bool")
        authority = payload["runtime_authority"]
        if not isinstance(authority, Mapping):
            raise TypeError(
                "authority_contract.runtime_authority must be a mapping"
            )
        return cls(
            d6_external_audit_sha256=payload[
                "d6_external_audit_sha256"
            ],
            d6_external_audit_content_sha256=payload[
                "d6_external_audit_content_sha256"
            ],
            evidence_audit_passed=payload["evidence_audit_passed"],
            evidence_eligible=payload["evidence_eligible"],
            runtime_authority=dict(authority),
            reason=payload["reason"],
            schema_version=payload["schema_version"],
        )


@dataclass(frozen=True)
class TrackletG1AdmissionReport:
    """Immutable evidence required to create a new G1-admitted bundle."""

    model_fingerprint: str
    implementation_sha256: str
    dataset_manifest_sha256: str
    split_sha256: str
    training_set_sha256: str
    heldout_report_sha256: str
    heldout_report_content_sha256: str
    paired_shadow_report_sha256: str
    paired_shadow_report_content_sha256: str
    paired_shadow_lineage_sha256: str
    paired_shadow_lineage_record_count: int
    paired_shadow_lineage_unique_episode_uid_count: int
    d6_external_audit_sha256: str
    d6_external_audit_content_sha256: str
    formal_evaluation: bool
    heldout_passed: bool
    paired_shadow_passed: bool
    d6_external_audit_passed: bool
    unseen_seed_count: int
    heldout_episode_count: int
    scenario_scale_cell_count: int
    online_truth_feature_count: int
    global_track_id_rewrite_count: int
    same_camera_mutual_exclusion_violation_count: int
    failure_reasons: tuple[str, ...]
    g1_assist_eligible: bool
    authority_contract: TrackletG1AuthorityContract
    schema_version: str = TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION:
            raise ValueError("tracklet G1 admission report schema mismatch")
        fingerprint = self.model_fingerprint
        if (
            not isinstance(fingerprint, str)
            or not fingerprint.startswith("sha256:")
            or not _SHA256_PATTERN.fullmatch(
                fingerprint.removeprefix("sha256:")
            )
        ):
            raise ValueError("model_fingerprint must be a sha256 fingerprint")
        for name in (
            "implementation_sha256",
            "dataset_manifest_sha256",
            "split_sha256",
            "training_set_sha256",
            "heldout_report_sha256",
            "heldout_report_content_sha256",
            "paired_shadow_report_sha256",
            "paired_shadow_report_content_sha256",
            "paired_shadow_lineage_sha256",
            "d6_external_audit_sha256",
            "d6_external_audit_content_sha256",
        ):
            _validate_sha256(getattr(self, name), name)
        for name in (
            "formal_evaluation",
            "heldout_passed",
            "paired_shadow_passed",
            "d6_external_audit_passed",
            "g1_assist_eligible",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        for name in (
            "unseen_seed_count",
            "heldout_episode_count",
            "scenario_scale_cell_count",
            "paired_shadow_lineage_record_count",
            "paired_shadow_lineage_unique_episode_uid_count",
            "online_truth_feature_count",
            "global_track_id_rewrite_count",
            "same_camera_mutual_exclusion_violation_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise TypeError(f"{name} must be a non-negative int")
        reasons = tuple(self.failure_reasons)
        if any(not isinstance(item, str) or not item.strip() for item in reasons):
            raise ValueError("failure_reasons must contain non-empty strings")
        if len(reasons) != len(set(reasons)):
            raise ValueError("failure_reasons must be unique")
        object.__setattr__(self, "failure_reasons", reasons)
        if not isinstance(
            self.authority_contract, TrackletG1AuthorityContract
        ):
            raise TypeError(
                "authority_contract must be TrackletG1AuthorityContract"
            )
        if (
            self.authority_contract.d6_external_audit_sha256
            != self.d6_external_audit_sha256
            or self.authority_contract.d6_external_audit_content_sha256
            != self.d6_external_audit_content_sha256
        ):
            raise ValueError(
                "authority contract audit hashes differ from admission report"
            )
        if (
            self.authority_contract.evidence_audit_passed
            is not self.d6_external_audit_passed
            or self.authority_contract.evidence_eligible
            is not self.g1_assist_eligible
        ):
            raise ValueError(
                "authority contract evidence state differs from admission report"
            )
        if self.g1_assist_eligible:
            failures: list[str] = []
            if not self.formal_evaluation:
                failures.append("evaluation_not_formal")
            if not self.heldout_passed:
                failures.append("heldout_not_passed")
            if not self.paired_shadow_passed:
                failures.append("paired_shadow_not_passed")
            if not self.d6_external_audit_passed:
                failures.append("d6_external_audit_not_passed")
            if self.unseen_seed_count < TRACKLET_G1_MINIMUM_UNSEEN_SEEDS:
                failures.append("insufficient_unseen_seeds")
            if (
                self.heldout_episode_count
                < TRACKLET_G1_MINIMUM_HELDOUT_EPISODES
            ):
                failures.append("insufficient_heldout_episodes")
            if (
                self.scenario_scale_cell_count
                < TRACKLET_G1_MINIMUM_SCENARIO_SCALE_CELLS
            ):
                failures.append("insufficient_scenario_scale_cells")
            if (
                self.paired_shadow_lineage_record_count
                != TRACKLET_G1_REQUIRED_PAIRED_LINEAGE_RECORD_COUNT
            ):
                failures.append("paired_lineage_record_count_not_formal")
            if (
                self.paired_shadow_lineage_unique_episode_uid_count
                != self.paired_shadow_lineage_record_count
            ):
                failures.append("paired_lineage_episode_uid_not_unique")
            if self.online_truth_feature_count:
                failures.append("online_truth_feature_use")
            if self.global_track_id_rewrite_count:
                failures.append("global_track_id_rewrite")
            if self.same_camera_mutual_exclusion_violation_count:
                failures.append("same_camera_mutual_exclusion_violation")
            if reasons:
                failures.append("reported_failure_reasons")
            if failures:
                raise ValueError(
                    "tracklet G1 report attempts unsafe admission: "
                    + ",".join(failures)
                )

    def to_manifest(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "schema_version": self.schema_version,
                "model_fingerprint": self.model_fingerprint,
                "implementation_sha256": self.implementation_sha256,
                "dataset_manifest_sha256": self.dataset_manifest_sha256,
                "split_sha256": self.split_sha256,
                "training_set_sha256": self.training_set_sha256,
                "heldout_report_sha256": self.heldout_report_sha256,
                "heldout_report_content_sha256": (
                    self.heldout_report_content_sha256
                ),
                "paired_shadow_report_sha256": (
                    self.paired_shadow_report_sha256
                ),
                "paired_shadow_report_content_sha256": (
                    self.paired_shadow_report_content_sha256
                ),
                "paired_shadow_lineage_sha256": (
                    self.paired_shadow_lineage_sha256
                ),
                "paired_shadow_lineage_record_count": (
                    self.paired_shadow_lineage_record_count
                ),
                "paired_shadow_lineage_unique_episode_uid_count": (
                    self.paired_shadow_lineage_unique_episode_uid_count
                ),
                "d6_external_audit_sha256": self.d6_external_audit_sha256,
                "d6_external_audit_content_sha256": (
                    self.d6_external_audit_content_sha256
                ),
                "formal_evaluation": self.formal_evaluation,
                "heldout_passed": self.heldout_passed,
                "paired_shadow_passed": self.paired_shadow_passed,
                "d6_external_audit_passed": self.d6_external_audit_passed,
                "unseen_seed_count": self.unseen_seed_count,
                "heldout_episode_count": self.heldout_episode_count,
                "scenario_scale_cell_count": self.scenario_scale_cell_count,
                "online_truth_feature_count": self.online_truth_feature_count,
                "global_track_id_rewrite_count": (
                    self.global_track_id_rewrite_count
                ),
                "same_camera_mutual_exclusion_violation_count": (
                    self.same_camera_mutual_exclusion_violation_count
                ),
                "failure_reasons": list(self.failure_reasons),
                "g1_assist_eligible": self.g1_assist_eligible,
                "authority_contract": dict(
                    self.authority_contract.to_manifest()
                ),
            }
        )


@dataclass(frozen=True)
class CalibratedTrackletEdgeScorer:
    """Online scorer that emits only calibrated same-target edge probability."""

    model: NativeTrackletEdgeClassifier
    temperature: float
    decision_threshold: float
    manifest: Mapping[str, Any]
    bundle_manifest_sha256: str
    bundle_weights_sha256: str
    device: torch.device
    available: bool = True

    def forward_graph(self, graph: SparseTrackletGraph) -> torch.Tensor:
        if not isinstance(graph, SparseTrackletGraph):
            raise TypeError("online scorer accepts only SparseTrackletGraph")
        node_features, edge_index, edge_features = graph_tensors(graph, device=self.device)
        self.model.eval()
        with torch.no_grad():
            logits = self.model.edge_logits(node_features, edge_index, edge_features)
            return torch.sigmoid(logits / self.temperature)


@dataclass(frozen=True)
class UnavailableTrackletEdgeScorer:
    """Non-throwing load result consumed by the adapter's rule fallback."""

    failure_reason: str
    available: bool = False

    def forward_graph(self, graph: SparseTrackletGraph) -> np.ndarray:
        raise RuntimeError(self.failure_reason)


def write_tracklet_model_bundle(
    bundle_dir: str | Path,
    model: NativeTrackletEdgeClassifier,
    *,
    dataset_manifest_sha256: str,
    split_sha256: str,
    training_set_sha256: str,
    training_config_sha256: str,
    calibration_temperature: float,
    decision_threshold: float,
    validation_results: Mapping[str, Any],
    model_semantic_version: str = MODEL_SEMANTIC_VERSION,
    admission_status: str = "research_candidate_not_default",
    readiness_audit_sha256: str | None = None,
    g1_admission_report: TrackletG1AdmissionReport | None = None,
) -> Mapping[str, Any]:
    """Write an unadmitted research or development bundle.

    The production writer cannot emit v5 admitted bundles until an independent
    evidence assembler validates and packages the held-out, paired-shadow, and
    D6 audit artifacts. A caller-provided report is not an authority source.
    """

    if not isinstance(model, NativeTrackletEdgeClassifier):
        raise TypeError("model must be NativeTrackletEdgeClassifier")
    if g1_admission_report is not None:
        raise ValueError(
            "G1 admission evidence assembler is unavailable; "
            "the production writer rejects caller-provided reports"
        )
    hashes = {
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "split_sha256": split_sha256,
        "training_set_sha256": training_set_sha256,
        "training_config_sha256": training_config_sha256,
    }
    for name, value in hashes.items():
        _validate_sha256(value, name)
    temperature = float(calibration_temperature)
    threshold = float(decision_threshold)
    if not np.isfinite(temperature) or temperature <= 0.0:
        raise ValueError("calibration_temperature must be finite and positive")
    if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("decision_threshold must be finite and in [0, 1]")
    semantic_version = str(model_semantic_version).strip()
    if not semantic_version:
        raise ValueError("model_semantic_version must be non-empty")
    admission_value = str(admission_status).strip()
    if admission_value not in _ALLOWED_ADMISSION_STATUSES:
        raise ValueError("unsupported tracklet model admission_status")
    if readiness_audit_sha256 is not None:
        _validate_sha256(readiness_audit_sha256, "readiness_audit_sha256")
    if admission_value == "development_only_fail_closed" and readiness_audit_sha256 is None:
        raise ValueError("development-only bundles require readiness_audit_sha256")
    validation_payload = _json_object(validation_results, "validation_results")
    code_provenance = _implementation_provenance()

    root = Path(bundle_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        "weights": root / WEIGHTS_FILENAME,
        "manifest": root / MANIFEST_FILENAME,
        "checksums": root / CHECKSUMS_FILENAME,
    }
    existing = [path.name for path in paths.values() if path.exists()]
    if existing:
        raise FileExistsError(f"bundle artifacts already exist: {existing}")

    state_dict: dict[str, torch.Tensor] = {}
    for key, value in model.state_dict().items():
        tensor = value.detach().cpu().clone()
        if not bool(torch.all(torch.isfinite(tensor))):
            raise ValueError(f"model state contains non-finite tensor: {key}")
        state_dict[str(key)] = tensor
    _torch_save_atomic(paths["weights"], state_dict)
    weights_sha256 = sha256_file(paths["weights"])
    weights_size = paths["weights"].stat().st_size
    manifest = {
        "schema_version": MODEL_BUNDLE_SCHEMA_VERSION,
        "model_semantic_version": semantic_version,
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "node_feature_version": NODE_FEATURE_VERSION,
        "edge_feature_version": EDGE_FEATURE_VERSION,
        "node_feature_names": list(NODE_FEATURE_NAMES),
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "architecture": {
            "class_name": "NativeTrackletEdgeClassifier",
            "node_feature_dim": model.node_feature_dim,
            "edge_feature_dim": model.edge_feature_dim,
            "hidden_dim": model.hidden_dim,
            "message_passing_steps": model.message_passing_steps,
            "dropout": model.dropout,
        },
        "training_dataset": {
            "dataset_manifest_sha256": dataset_manifest_sha256,
            "split_sha256": split_sha256,
            "training_set_sha256": training_set_sha256,
            "training_config_sha256": training_config_sha256,
        },
        "code_provenance": code_provenance,
        "calibration": {
            "method": "validation_only_scalar_temperature",
            "source_split": "validation",
            "temperature": temperature,
            "decision_threshold": threshold,
            "threshold_objective": "validation_f1",
        },
        "validation_results": validation_payload,
        "weights": {
            "filename": WEIGHTS_FILENAME,
            "format": "pytorch_state_dict_weights_only",
            "sha256": weights_sha256,
            "size_bytes": weights_size,
        },
        "admission": {
            "status": admission_value,
            "default_model": False,
            "g1_assist_eligible": False,
            "readiness_audit_sha256": readiness_audit_sha256,
        },
    }
    _write_json_atomic(paths["manifest"], manifest)
    manifest_sha256 = sha256_file(paths["manifest"])
    checksum_text = (
        f"{manifest_sha256}  {MANIFEST_FILENAME}\n"
        f"{weights_sha256}  {WEIGHTS_FILENAME}\n"
    )
    _write_bytes_atomic(paths["checksums"], checksum_text.encode("ascii"))
    load_tracklet_model_bundle(root)
    return MappingProxyType(manifest)


def load_tracklet_model_bundle(
    bundle_dir: str | Path,
    *,
    device: torch.device | str = "cpu",
    expected_model_semantic_version: str = MODEL_SEMANTIC_VERSION,
    expected_dataset_manifest_sha256: str | None = None,
    expected_split_sha256: str | None = None,
    expected_training_set_sha256: str | None = None,
    expected_readiness_audit_sha256: str | None = None,
) -> CalibratedTrackletEdgeScorer:
    """Strictly load a development v3 or evidence-assembled G1 v5 bundle."""

    return _load_tracklet_model_bundle_impl(
        bundle_dir,
        device=device,
        expected_model_semantic_version=expected_model_semantic_version,
        expected_dataset_manifest_sha256=expected_dataset_manifest_sha256,
        expected_split_sha256=expected_split_sha256,
        expected_training_set_sha256=expected_training_set_sha256,
        expected_readiness_audit_sha256=expected_readiness_audit_sha256,
    )


def _load_tracklet_model_bundle_impl(
    bundle_dir: str | Path,
    *,
    device: torch.device | str,
    expected_model_semantic_version: str,
    expected_dataset_manifest_sha256: str | None,
    expected_split_sha256: str | None,
    expected_training_set_sha256: str | None,
    expected_readiness_audit_sha256: str | None,
) -> CalibratedTrackletEdgeScorer:
    """Strictly validate checksums/schema/order and load weights safely."""

    root = Path(bundle_dir)
    if not root.is_dir():
        raise ModelBundleValidationError("bundle_missing", "model bundle directory is missing")
    manifest_path = root / MANIFEST_FILENAME
    weights_path = root / WEIGHTS_FILENAME
    checksums_path = root / CHECKSUMS_FILENAME
    for path, code in (
        (manifest_path, "manifest_missing"),
        (weights_path, "weights_missing"),
        (checksums_path, "checksums_missing"),
    ):
        if not path.is_file():
            raise ModelBundleValidationError(code, f"required bundle file is missing: {path.name}")

    checksums = _read_checksums(checksums_path)
    if MANIFEST_FILENAME not in checksums or WEIGHTS_FILENAME not in checksums:
        raise ModelBundleValidationError(
            "checksums_fields_mismatch",
            "SHA256SUMS must cover manifest and weights",
        )
    manifest_sha256 = sha256_file(manifest_path)
    weights_sha256 = sha256_file(weights_path)
    _expect_equal(manifest_sha256, checksums[MANIFEST_FILENAME], "manifest_sha_mismatch")
    _expect_equal(weights_sha256, checksums[WEIGHTS_FILENAME], "weights_sha_mismatch")
    manifest = _read_json(manifest_path)

    bundle_schema = manifest.get("schema_version")
    if bundle_schema == LEGACY_G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION:
        raise ModelBundleValidationError(
            "legacy_g1_bundle_schema_unsupported",
            (
                f"{LEGACY_G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION} retains "
                "its historical admission semantics and cannot be loaded "
                "as a v5 six-authority bundle"
            ),
        )
    if bundle_schema not in {
        MODEL_BUNDLE_SCHEMA_VERSION,
        G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION,
    }:
        raise ModelBundleValidationError(
            "bundle_schema_mismatch", "unsupported model bundle schema"
        )
    admitted_schema = bundle_schema == G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION
    if admitted_schema:
        from .tracklet_g1_evidence_assembler import (
            G1_BUNDLE_CHECKSUM_FILES,
        )

        expected_files = set(G1_BUNDLE_CHECKSUM_FILES)
    else:
        expected_files = {MANIFEST_FILENAME, WEIGHTS_FILENAME}
    if set(checksums) != expected_files:
        raise ModelBundleValidationError(
            "checksums_fields_mismatch",
            "SHA256SUMS does not cover the exact bundle file set",
        )
    for filename in expected_files - {MANIFEST_FILENAME, WEIGHTS_FILENAME}:
        artifact_path = root / filename
        if not artifact_path.is_file():
            raise ModelBundleValidationError(
                "evidence_missing",
                f"required evidence file is missing: {filename}",
            )
        _expect_equal(
            sha256_file(artifact_path),
            checksums[filename],
            "evidence_sha_mismatch",
        )
    _expect_equal(
        manifest.get("model_semantic_version"),
        expected_model_semantic_version,
        "model_semantic_version_mismatch",
    )
    _expect_equal(
        manifest.get("dataset_schema_version"),
        DATASET_SCHEMA_VERSION,
        "dataset_schema_mismatch",
    )
    _expect_equal(manifest.get("graph_schema_version"), GRAPH_SCHEMA_VERSION, "graph_schema_mismatch")
    _expect_equal(manifest.get("node_feature_version"), NODE_FEATURE_VERSION, "node_feature_version_mismatch")
    _expect_equal(manifest.get("edge_feature_version"), EDGE_FEATURE_VERSION, "edge_feature_version_mismatch")
    _expect_equal(tuple(manifest.get("node_feature_names", ())), NODE_FEATURE_NAMES, "node_feature_order_mismatch")
    _expect_equal(tuple(manifest.get("edge_feature_names", ())), EDGE_FEATURE_NAMES, "edge_feature_order_mismatch")

    architecture = manifest.get("architecture")
    if not isinstance(architecture, Mapping):
        raise ModelBundleValidationError("architecture_missing", "bundle architecture is missing")
    required_architecture = {
        "class_name",
        "node_feature_dim",
        "edge_feature_dim",
        "hidden_dim",
        "message_passing_steps",
        "dropout",
    }
    if set(architecture) != required_architecture:
        raise ModelBundleValidationError("architecture_fields_mismatch", "bundle architecture fields mismatch")
    _expect_equal(architecture["class_name"], "NativeTrackletEdgeClassifier", "model_class_mismatch")
    try:
        node_feature_dim = int(architecture["node_feature_dim"])
        edge_feature_dim = int(architecture["edge_feature_dim"])
        hidden_dim = int(architecture["hidden_dim"])
        message_passing_steps = int(architecture["message_passing_steps"])
        dropout = float(architecture["dropout"])
    except (TypeError, ValueError) as exc:
        raise ModelBundleValidationError("architecture_invalid", "bundle architecture is invalid") from exc
    _expect_equal(node_feature_dim, len(NODE_FEATURE_NAMES), "node_feature_dim_mismatch")
    _expect_equal(edge_feature_dim, len(EDGE_FEATURE_NAMES), "edge_feature_dim_mismatch")
    try:
        model = NativeTrackletEdgeClassifier(
            node_feature_dim=node_feature_dim,
            edge_feature_dim=edge_feature_dim,
            hidden_dim=hidden_dim,
            message_passing_steps=message_passing_steps,
            dropout=dropout,
        )
    except (TypeError, ValueError) as exc:
        raise ModelBundleValidationError("architecture_invalid", "bundle architecture is invalid") from exc

    training_dataset = manifest.get("training_dataset")
    if not isinstance(training_dataset, Mapping):
        raise ModelBundleValidationError("training_dataset_missing", "training dataset metadata is missing")
    required_training_hashes = {
        "dataset_manifest_sha256",
        "split_sha256",
        "training_set_sha256",
        "training_config_sha256",
    }
    if set(training_dataset) != required_training_hashes:
        raise ModelBundleValidationError("training_dataset_fields_mismatch", "training dataset fields mismatch")
    for name in required_training_hashes:
        _validate_sha256(training_dataset[name], name, error_type=ModelBundleValidationError)
    if expected_dataset_manifest_sha256 is not None:
        _expect_equal(
            training_dataset["dataset_manifest_sha256"],
            expected_dataset_manifest_sha256,
            "dataset_manifest_sha_mismatch",
        )
    if expected_split_sha256 is not None:
        _expect_equal(training_dataset["split_sha256"], expected_split_sha256, "split_sha_mismatch")
    if expected_training_set_sha256 is not None:
        _expect_equal(
            training_dataset["training_set_sha256"],
            expected_training_set_sha256,
            "training_set_sha_mismatch",
        )

    code_provenance = manifest.get("code_provenance")
    if not isinstance(code_provenance, Mapping):
        raise ModelBundleValidationError("code_provenance_missing", "bundle code provenance is missing")
    if set(code_provenance) != {
        "implementation_sha256",
        "source_files",
        "runtime_implementation_sha256",
        "runtime_source_files",
    }:
        raise ModelBundleValidationError(
            "code_provenance_fields_mismatch", "bundle code provenance fields mismatch"
        )
    source_files = code_provenance.get("source_files")
    if not isinstance(source_files, Mapping) or set(source_files) != set(
        _MODEL_IMPLEMENTATION_SOURCE_FILES
    ):
        raise ModelBundleValidationError(
            "code_provenance_files_mismatch",
            "bundle model source provenance is incomplete",
        )
    for filename, digest in source_files.items():
        _validate_sha256(digest, str(filename), error_type=ModelBundleValidationError)
    _validate_sha256(
        code_provenance.get("implementation_sha256"),
        "implementation_sha256",
        error_type=ModelBundleValidationError,
    )
    _expect_equal(
        code_provenance["implementation_sha256"],
        sha256_json(dict(sorted(source_files.items()))),
        "implementation_sha_mismatch",
    )
    runtime_source_files = code_provenance.get("runtime_source_files")
    if not isinstance(runtime_source_files, Mapping) or set(
        runtime_source_files
    ) != set(_RUNTIME_IMPLEMENTATION_SOURCE_FILES):
        raise ModelBundleValidationError(
            "runtime_provenance_files_mismatch",
            "bundle runtime source provenance is incomplete",
        )
    for filename, digest in runtime_source_files.items():
        _validate_sha256(digest, str(filename), error_type=ModelBundleValidationError)
    _validate_sha256(
        code_provenance.get("runtime_implementation_sha256"),
        "runtime_implementation_sha256",
        error_type=ModelBundleValidationError,
    )
    _expect_equal(
        code_provenance["runtime_implementation_sha256"],
        sha256_json(dict(sorted(runtime_source_files.items()))),
        "runtime_implementation_sha_mismatch",
    )
    for filename in _MODEL_IMPLEMENTATION_SOURCE_FILES:
        _expect_equal(
            source_files[filename],
            runtime_source_files[filename],
            f"model_runtime_source_mismatch.{filename}",
        )
    current_provenance = _implementation_provenance()
    _expect_equal(
        code_provenance["runtime_implementation_sha256"],
        current_provenance["runtime_implementation_sha256"],
        "implementation_runtime_mismatch",
    )

    calibration = manifest.get("calibration")
    if not isinstance(calibration, Mapping):
        raise ModelBundleValidationError("calibration_missing", "bundle calibration is missing")
    if calibration.get("method") != "validation_only_scalar_temperature":
        raise ModelBundleValidationError("calibration_method_invalid", "unsupported calibration method")
    if calibration.get("source_split") != "validation":
        raise ModelBundleValidationError("calibration_split_invalid", "calibration must use validation only")
    if calibration.get("threshold_objective") != "validation_f1":
        raise ModelBundleValidationError("threshold_objective_invalid", "threshold must be selected on validation F1")
    try:
        temperature = float(calibration["temperature"])
        threshold = float(calibration["decision_threshold"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelBundleValidationError("calibration_invalid", "calibration values are invalid") from exc
    if not np.isfinite(temperature) or temperature <= 0.0:
        raise ModelBundleValidationError("temperature_invalid", "temperature must be finite and positive")
    if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ModelBundleValidationError("threshold_invalid", "decision threshold must be in [0, 1]")
    if not isinstance(manifest.get("validation_results"), Mapping):
        raise ModelBundleValidationError("validation_results_missing", "validation results are missing")
    admission = manifest.get("admission")
    admission_report: TrackletG1AdmissionReport | None = None
    authority_contract: TrackletG1AuthorityContract | None = None
    if admitted_schema:
        if not isinstance(admission, Mapping) or set(admission) != {
            "status",
            "default_model",
            "g1_assist_eligible",
            "global_track_id_authority",
            "authority_contract",
            "report",
        }:
            raise ModelBundleValidationError(
                "admission_invalid", "admitted bundle fields are invalid"
            )
        if (
            admission.get("status")
            != "g1_evidence_eligible_not_authorized"
            or admission.get("default_model") is not False
            or admission.get("g1_assist_eligible") is not True
            or admission.get("global_track_id_authority") is not False
            or not isinstance(admission.get("authority_contract"), Mapping)
            or not isinstance(admission.get("report"), Mapping)
        ):
            raise ModelBundleValidationError(
                "admission_invalid",
                "admitted bundle requires a bound positive evidence report",
            )
        try:
            authority_contract = (
                TrackletG1AuthorityContract.from_manifest(
                    admission["authority_contract"]
                )
            )
            admission_report = tracklet_g1_admission_report_from_manifest(
                admission["report"]
            )
        except ModelBundleValidationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ModelBundleValidationError(
                "admission_invalid", "G1 admission report failed validation"
            ) from exc
        if not admission_report.g1_assist_eligible:
            raise ModelBundleValidationError(
                "admission_invalid", "G1 admission report is not eligible"
            )
        if (
            not authority_contract.evidence_audit_passed
            or not authority_contract.evidence_eligible
            or authority_contract != admission_report.authority_contract
        ):
            raise ModelBundleValidationError(
                "admission_invalid",
                "authority contract differs from the evidence report",
            )
        _expect_equal(
            admission_report.implementation_sha256,
            code_provenance["runtime_implementation_sha256"],
            "admission_implementation_sha_mismatch",
        )
        for name in (
            "dataset_manifest_sha256",
            "split_sha256",
            "training_set_sha256",
        ):
            _expect_equal(
                getattr(admission_report, name),
                training_dataset[name],
                f"admission_{name}_mismatch",
            )
        if expected_readiness_audit_sha256 is not None:
            raise ModelBundleValidationError(
                "readiness_audit_sha_mismatch",
                "legacy readiness audit cannot authorize an admitted bundle",
            )
    else:
        if not isinstance(admission, Mapping) or set(admission) != {
            "status",
            "default_model",
            "g1_assist_eligible",
            "readiness_audit_sha256",
        }:
            raise ModelBundleValidationError(
                "admission_invalid", "bundle admission fields are invalid"
            )
        admission_status = admission.get("status")
        if (
            admission_status not in _ALLOWED_ADMISSION_STATUSES
            or admission.get("default_model") is not False
            or admission.get("g1_assist_eligible") is not False
        ):
            raise ModelBundleValidationError(
                "admission_invalid",
                "legacy bundle must remain outside G1/assist admission",
            )
        audit_sha256 = admission.get("readiness_audit_sha256")
        if audit_sha256 is not None:
            _validate_sha256(
                audit_sha256,
                "readiness_audit_sha256",
                error_type=ModelBundleValidationError,
            )
        if (
            admission_status == "development_only_fail_closed"
            and audit_sha256 is None
        ):
            raise ModelBundleValidationError(
                "admission_invalid",
                "development-only bundle is missing its readiness audit hash",
            )
        if expected_readiness_audit_sha256 is not None:
            _expect_equal(
                audit_sha256,
                expected_readiness_audit_sha256,
                "readiness_audit_sha_mismatch",
            )

    weights = manifest.get("weights")
    if not isinstance(weights, Mapping):
        raise ModelBundleValidationError("weights_metadata_missing", "weights metadata is missing")
    expected_weight_fields = {
        "filename",
        "format",
        "sha256",
        "size_bytes",
        *(("model_fingerprint",) if admitted_schema else ()),
    }
    if set(weights) != expected_weight_fields:
        raise ModelBundleValidationError(
            "weights_fields_mismatch", "bundle weights fields mismatch"
        )
    _expect_equal(weights.get("filename"), WEIGHTS_FILENAME, "weights_filename_mismatch")
    _expect_equal(weights.get("format"), "pytorch_state_dict_weights_only", "weights_format_mismatch")
    _expect_equal(weights.get("sha256"), weights_sha256, "weights_manifest_sha_mismatch")
    try:
        manifest_weights_size = int(weights.get("size_bytes", -1))
    except (TypeError, ValueError) as exc:
        raise ModelBundleValidationError("weights_size_invalid", "weights size metadata is invalid") from exc
    _expect_equal(manifest_weights_size, weights_path.stat().st_size, "weights_size_mismatch")

    try:
        state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        raise ModelBundleValidationError(
            "weights_only_unavailable",
            "this PyTorch runtime does not support safe weights-only loading",
        ) from exc
    except Exception as exc:
        raise ModelBundleValidationError("weights_load_failed", "weights-only load failed") from exc
    if not isinstance(state_dict, Mapping) or not state_dict:
        raise ModelBundleValidationError("state_dict_invalid", "weights file is not a state_dict mapping")
    for key, value in state_dict.items():
        if not isinstance(key, str) or not isinstance(value, torch.Tensor):
            raise ModelBundleValidationError("state_dict_invalid", "state_dict contains an unsafe value")
        if not bool(torch.all(torch.isfinite(value))):
            raise ModelBundleValidationError("state_dict_non_finite", f"non-finite tensor: {key}")
    if admitted_schema:
        model_fingerprint = f"sha256:{weights_sha256}"
        _expect_equal(
            weights.get("model_fingerprint"),
            model_fingerprint,
            "model_fingerprint_mismatch",
        )
        assert admission_report is not None
        _expect_equal(
            admission_report.model_fingerprint,
            model_fingerprint,
            "admission_model_fingerprint_mismatch",
        )
        try:
            from .tracklet_g1_evidence_assembler import (
                TrackletG1EvidenceAssemblyError,
                validate_admitted_bundle_evidence,
            )

            validate_admitted_bundle_evidence(
                root,
                manifest,
                admission_report,
            )
        except TrackletG1EvidenceAssemblyError as exc:
            raise ModelBundleValidationError(
                f"evidence_{exc.code}",
                exc.detail,
            ) from exc
    try:
        model.load_state_dict(state_dict, strict=True)
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ModelBundleValidationError("state_dict_mismatch", "state_dict does not match architecture") from exc
    target_device = torch.device(device)
    model.to(target_device)
    model.eval()
    return CalibratedTrackletEdgeScorer(
        model=model,
        temperature=temperature,
        decision_threshold=threshold,
        manifest=MappingProxyType(dict(manifest)),
        bundle_manifest_sha256=manifest_sha256,
        bundle_weights_sha256=weights_sha256,
        device=target_device,
    )


def load_tracklet_model_bundle_for_runtime(
    bundle_dir: str | Path,
    *,
    device: torch.device | str = "cpu",
    require_g1_assist_eligible: bool = False,
) -> CalibratedTrackletEdgeScorer | UnavailableTrackletEdgeScorer:
    """Load for shadow use, or fail closed for an unauthorized assist request.

    The default preserves the historical development/shadow loading behavior.
    ``require_g1_assist_eligible=True`` is a runtime assist request: the
    bundle must be evidence-eligible and its versioned authority contract must
    explicitly grant G1 assist. Evidence eligibility alone never grants that
    runtime authority.
    """

    if type(require_g1_assist_eligible) is not bool:
        return UnavailableTrackletEdgeScorer(
            failure_reason=RUNTIME_ADMISSION_REQUIREMENT_INVALID_REASON
        )

    try:
        scorer = load_tracklet_model_bundle(bundle_dir, device=device)
    except ModelBundleValidationError as exc:
        reason = exc.code if exc.code.startswith("bundle_") else f"bundle_{exc.code}"
        return UnavailableTrackletEdgeScorer(failure_reason=reason)
    except Exception as exc:  # Defensive boundary: no load error may escape into identity logic.
        return UnavailableTrackletEdgeScorer(
            failure_reason=f"bundle_unexpected_{type(exc).__name__}"
        )
    if (
        require_g1_assist_eligible
        and scorer.manifest["admission"]["g1_assist_eligible"] is not True
    ):
        return UnavailableTrackletEdgeScorer(
            failure_reason=G1_ASSIST_NOT_ELIGIBLE_REASON
        )
    if require_g1_assist_eligible:
        raw_contract = scorer.manifest["admission"].get(
            "authority_contract"
        )
        if not isinstance(raw_contract, Mapping):
            return UnavailableTrackletEdgeScorer(
                failure_reason=G1_ASSIST_AUTHORITY_NOT_GRANTED_REASON
            )
        try:
            authority_contract = TrackletG1AuthorityContract.from_manifest(
                raw_contract
            )
        except (TypeError, ValueError):
            return UnavailableTrackletEdgeScorer(
                failure_reason=G1_ASSIST_AUTHORITY_NOT_GRANTED_REASON
            )
        if (
            authority_contract.runtime_authority["g1_assist_granted"]
            is not True
        ):
            return UnavailableTrackletEdgeScorer(
                failure_reason=G1_ASSIST_AUTHORITY_NOT_GRANTED_REASON
            )
    return scorer


def tracklet_model_fingerprint(
    model_or_state: (
        NativeTrackletEdgeClassifier | Mapping[str, torch.Tensor]
    ),
) -> str:
    """Hash tensor names, types, shapes, and bytes independently of packaging."""

    state = (
        model_or_state.state_dict()
        if isinstance(model_or_state, NativeTrackletEdgeClassifier)
        else model_or_state
    )
    if not isinstance(state, Mapping) or not state:
        raise ValueError("tracklet model fingerprint requires a state_dict")
    digest = hashlib.sha256()
    for key in sorted(state):
        value = state[key]
        if not isinstance(key, str) or not isinstance(value, torch.Tensor):
            raise ValueError("tracklet model fingerprint state_dict is invalid")
        tensor = value.detach().cpu().contiguous()
        if not bool(torch.all(torch.isfinite(tensor))):
            raise ValueError(
                "tracklet model fingerprint cannot include non-finite tensors"
            )
        digest.update(key.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(tensor.dtype).encode("ascii"))
        digest.update(b"\0")
        digest.update(
            json.dumps(list(tensor.shape), separators=(",", ":")).encode(
                "ascii"
            )
        )
        digest.update(b"\0")
        digest.update(tensor.numpy().tobytes(order="C"))
    return f"sha256:{digest.hexdigest()}"


def tracklet_runtime_implementation_sha256() -> str:
    """Return the implementation digest a new G1 report must bind."""

    return str(_implementation_provenance()["runtime_implementation_sha256"])


def tracklet_g1_admission_report_from_manifest(
    payload: Mapping[str, Any],
) -> TrackletG1AdmissionReport:
    """Parse an embedded G1 report without coercing authority-bearing values."""

    if not isinstance(payload, Mapping):
        raise ValueError("tracklet G1 admission report must be a mapping")
    schema_version = payload.get("schema_version")
    if schema_version == LEGACY_TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION:
        raise ModelBundleValidationError(
            "legacy_g1_admission_report_schema_unsupported",
            (
                f"{LEGACY_TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION} "
                "retains its historical four-authority semantics"
            ),
        )
    if schema_version != TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION:
        raise ModelBundleValidationError(
            "g1_admission_report_schema_mismatch",
            f"unsupported G1 admission report schema: {schema_version!r}",
        )
    required = {
        "schema_version",
        "model_fingerprint",
        "implementation_sha256",
        "dataset_manifest_sha256",
        "split_sha256",
        "training_set_sha256",
        "heldout_report_sha256",
        "heldout_report_content_sha256",
        "paired_shadow_report_sha256",
        "paired_shadow_report_content_sha256",
        "paired_shadow_lineage_sha256",
        "paired_shadow_lineage_record_count",
        "paired_shadow_lineage_unique_episode_uid_count",
        "d6_external_audit_sha256",
        "d6_external_audit_content_sha256",
        "formal_evaluation",
        "heldout_passed",
        "paired_shadow_passed",
        "d6_external_audit_passed",
        "unseen_seed_count",
        "heldout_episode_count",
        "scenario_scale_cell_count",
        "online_truth_feature_count",
        "global_track_id_rewrite_count",
        "same_camera_mutual_exclusion_violation_count",
        "failure_reasons",
        "g1_assist_eligible",
        "authority_contract",
    }
    if set(payload) != required:
        raise ValueError("tracklet G1 admission report fields mismatch")
    for name in (
        "formal_evaluation",
        "heldout_passed",
        "paired_shadow_passed",
        "d6_external_audit_passed",
        "g1_assist_eligible",
    ):
        if type(payload[name]) is not bool:
            raise TypeError(f"{name} must be bool")
    for name in (
        "unseen_seed_count",
        "heldout_episode_count",
        "scenario_scale_cell_count",
        "paired_shadow_lineage_record_count",
        "paired_shadow_lineage_unique_episode_uid_count",
        "online_truth_feature_count",
        "global_track_id_rewrite_count",
        "same_camera_mutual_exclusion_violation_count",
    ):
        if type(payload[name]) is not int:
            raise TypeError(f"{name} must be int")
    raw_reasons = payload["failure_reasons"]
    if not isinstance(raw_reasons, list):
        raise TypeError("failure_reasons must be a list")
    if any(not isinstance(item, str) for item in raw_reasons):
        raise TypeError("failure_reasons must contain strings")
    for name in (
        "schema_version",
        "model_fingerprint",
        "implementation_sha256",
        "dataset_manifest_sha256",
        "split_sha256",
        "training_set_sha256",
        "heldout_report_sha256",
        "heldout_report_content_sha256",
        "paired_shadow_report_sha256",
        "paired_shadow_report_content_sha256",
        "paired_shadow_lineage_sha256",
        "d6_external_audit_sha256",
        "d6_external_audit_content_sha256",
    ):
        if not isinstance(payload[name], str):
            raise TypeError(f"{name} must be str")
    authority_contract = TrackletG1AuthorityContract.from_manifest(
        payload["authority_contract"]
    )
    return TrackletG1AdmissionReport(
        model_fingerprint=payload["model_fingerprint"],
        implementation_sha256=payload["implementation_sha256"],
        dataset_manifest_sha256=payload["dataset_manifest_sha256"],
        split_sha256=payload["split_sha256"],
        training_set_sha256=payload["training_set_sha256"],
        heldout_report_sha256=payload["heldout_report_sha256"],
        heldout_report_content_sha256=payload[
            "heldout_report_content_sha256"
        ],
        paired_shadow_report_sha256=payload[
            "paired_shadow_report_sha256"
        ],
        paired_shadow_report_content_sha256=payload[
            "paired_shadow_report_content_sha256"
        ],
        paired_shadow_lineage_sha256=payload[
            "paired_shadow_lineage_sha256"
        ],
        paired_shadow_lineage_record_count=payload[
            "paired_shadow_lineage_record_count"
        ],
        paired_shadow_lineage_unique_episode_uid_count=payload[
            "paired_shadow_lineage_unique_episode_uid_count"
        ],
        d6_external_audit_sha256=payload["d6_external_audit_sha256"],
        d6_external_audit_content_sha256=payload[
            "d6_external_audit_content_sha256"
        ],
        formal_evaluation=payload["formal_evaluation"],
        heldout_passed=payload["heldout_passed"],
        paired_shadow_passed=payload["paired_shadow_passed"],
        d6_external_audit_passed=payload["d6_external_audit_passed"],
        unseen_seed_count=payload["unseen_seed_count"],
        heldout_episode_count=payload["heldout_episode_count"],
        scenario_scale_cell_count=payload["scenario_scale_cell_count"],
        online_truth_feature_count=payload["online_truth_feature_count"],
        global_track_id_rewrite_count=payload[
            "global_track_id_rewrite_count"
        ],
        same_camera_mutual_exclusion_violation_count=payload[
            "same_camera_mutual_exclusion_violation_count"
        ],
        failure_reasons=tuple(raw_reasons),
        g1_assist_eligible=payload["g1_assist_eligible"],
        authority_contract=authority_contract,
        schema_version=payload["schema_version"],
    )


def _implementation_provenance() -> dict[str, Any]:
    root = Path(__file__).resolve().parent
    model_source_files = {
        filename: sha256_file(root / filename)
        for filename in _MODEL_IMPLEMENTATION_SOURCE_FILES
    }
    runtime_source_files = {
        filename: sha256_file(root / filename)
        for filename in _RUNTIME_IMPLEMENTATION_SOURCE_FILES
    }
    return {
        "implementation_sha256": sha256_json(
            dict(sorted(model_source_files.items()))
        ),
        "source_files": dict(sorted(model_source_files.items())),
        "runtime_implementation_sha256": sha256_json(
            dict(sorted(runtime_source_files.items()))
        ),
        "runtime_source_files": dict(sorted(runtime_source_files.items())),
    }


def _read_checksums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ModelBundleValidationError("checksums_invalid", "cannot read SHA256SUMS") from exc
    result: dict[str, str] = {}
    for line in lines:
        parts = line.split("  ")
        if len(parts) != 2 or not _SHA256_PATTERN.fullmatch(parts[0]):
            raise ModelBundleValidationError("checksums_invalid", "invalid SHA256SUMS line")
        filename = parts[1]
        relative = Path(filename)
        if (
            filename in result
            or not filename
            or relative.is_absolute()
            or ".." in relative.parts
            or "." in relative.parts
            or relative.as_posix() != filename
        ):
            raise ModelBundleValidationError("checksums_invalid", "invalid checksum filename")
        result[filename] = parts[0]
    return result


def _validate_sha256(
    value: Any,
    name: str,
    *,
    error_type: type[Exception] = ValueError,
) -> None:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        message = f"{name} must be a lowercase SHA256 hex digest"
        if error_type is ModelBundleValidationError:
            raise ModelBundleValidationError("hash_invalid", message)
        raise error_type(message)


def _expect_equal(actual: Any, expected: Any, code: str) -> None:
    if actual != expected:
        raise ModelBundleValidationError(code, f"expected {expected!r}, received {actual!r}")


def _json_object(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    try:
        result = json.loads(_canonical_json_bytes(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain finite JSON data") from exc
    if not isinstance(result, dict):
        raise TypeError(f"{name} must encode an object")
    return result


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: _reject_json_constant(token),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ModelBundleValidationError("manifest_invalid", "cannot parse manifest.json") from exc
    if not isinstance(value, dict):
        raise ModelBundleValidationError("manifest_invalid", "manifest must contain an object")
    return value


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON constant: {token}")


def _write_json_atomic(path: Path, value: Any) -> None:
    _write_bytes_atomic(path, _canonical_json_bytes(value))


def _write_bytes_atomic(path: Path, value: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _torch_save_atomic(path: Path, state_dict: Mapping[str, torch.Tensor]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        torch.save(state_dict, temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "CHECKSUMS_FILENAME",
    "CalibratedTrackletEdgeScorer",
    "G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION",
    "G1_ASSIST_AUTHORITY_NOT_GRANTED_REASON",
    "G1_ASSIST_NOT_ELIGIBLE_REASON",
    "LEGACY_G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION",
    "LEGACY_TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION",
    "MANIFEST_FILENAME",
    "MODEL_BUNDLE_SCHEMA_VERSION",
    "MODEL_SEMANTIC_VERSION",
    "ModelBundleValidationError",
    "RUNTIME_ADMISSION_REQUIREMENT_INVALID_REASON",
    "TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION",
    "TRACKLET_G1_AUTHORITY_CONTRACT_SCHEMA_VERSION",
    "TRACKLET_G1_EXTERNAL_AUTHORITY_FIELDS",
    "TRACKLET_G1_MINIMUM_HELDOUT_EPISODES",
    "TRACKLET_G1_MINIMUM_SCENARIO_SCALE_CELLS",
    "TRACKLET_G1_MINIMUM_UNSEEN_SEEDS",
    "TRACKLET_G1_REQUIRED_PAIRED_LINEAGE_RECORD_COUNT",
    "TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS",
    "TrackletG1AdmissionReport",
    "TrackletG1AuthorityContract",
    "UnavailableTrackletEdgeScorer",
    "WEIGHTS_FILENAME",
    "load_tracklet_model_bundle",
    "load_tracklet_model_bundle_for_runtime",
    "tracklet_g1_admission_report_from_manifest",
    "tracklet_model_fingerprint",
    "tracklet_runtime_implementation_sha256",
    "write_tracklet_model_bundle",
]
