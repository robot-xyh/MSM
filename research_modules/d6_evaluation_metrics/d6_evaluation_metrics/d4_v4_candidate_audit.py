"""Independent, read-only audit for one unregistered D4 v4 candidate.

The audit authenticates the complete candidate tree against caller-pinned
content, model, dataset, source-commit, and frozen-v3-registry identities.  It
then loads only TRAIN and VALIDATION payloads and independently recomputes the
actor and fixed-0.60 confidence-gate metrics.  A pass is development evidence
only: registration, formal holdout, runtime preflight, and every runtime
permission remain closed.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from hashlib import sha256
import json
from math import ceil, isclose, isfinite
from pathlib import Path, PurePosixPath
import shutil
import subprocess
from typing import Any, Iterable, Mapping, Sequence
import uuid


D4_V4_CANDIDATE_AUDIT_SCHEMA_VERSION = (
    "d6.d4-v4-candidate-independent-audit.v1"
)
D4_V4_CANDIDATE_AUDIT_INPUT_SCHEMA_VERSION = (
    "d6.d4-v4-candidate-independent-audit-input.v1"
)
D4_V4_CANDIDATE_AUDIT_PROFILE_VERSION = (
    "d6.d4-v4-observable-calibrated-development-integrity.v1"
)
D4_V4_CANDIDATE_ID = (
    "region_resource_a2_executable_transfer_shadow_v4"
)
D4_V4_MODEL_VERSION = (
    "d4-region-resource-graph-bc-executable-transfer-v4"
)
D4_V4_MANIFEST_FILE = "v4_shadow_candidate_manifest.json"
D4_V4_MANIFEST_SCHEMA = (
    "d4-region-resource-executable-shadow-candidate-v4"
)
D4_V4_PERMISSION_SCHEMA = (
    "d4-region-resource-executable-shadow-permissions-v4"
)
D4_V4_GATE_SCHEMA = (
    "d4-region-resource-executable-intervention-gate-v4"
)
D4_V4_EXTERNAL_EVIDENCE_SCHEMA = (
    "d4-region-resource-external-runtime-dataset-evidence-v1"
)
D4_V4_FIXED_CONFIDENCE_GATE = 0.60
D4_V4_FIXED_OOD_MARGIN = 0.05
D4_V4_MAXIMUM_TRANSFER_PER_EDGE = 1
D4_V4_MAXIMUM_TOTAL_TRANSFER_FRACTION = 0.10
D4_V4_POSITIVE_SAMPLE_WEIGHT_CAP = 8.0
D4_V4_NONZERO_EDGE_WEIGHT_CAP = 32.0
D4_V4_CONFIDENCE_HARD_NEGATIVE_WEIGHT_CAP = 32.0
D4_V4_ADMISSION_BLOCKER_CODES = (
    "candidate_unregistered",
    "formal_holdout_not_completed",
    "runtime_preflight_not_completed",
    "development_fixture_train_domain_smoke_only",
    "confidence_positive_recall_low",
    "confidence_threshold_passing_margin_too_thin",
    "runtime_outcome_and_benefit_unavailable",
)

D4_V3_REGISTRY_RELATIVE_ROOT = (
    "research_modules/d4_distributed_fallback/model_registry/"
    "region_resource_a2_8region_runtime_action_readiness_shadow_v3"
)
D4_V4_REGISTRY_RELATIVE_ROOT = (
    "research_modules/d4_distributed_fallback/model_registry/"
    f"{D4_V4_CANDIDATE_ID}"
)

_IMPLEMENTATION_PATHS = (
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_dataset.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_learning.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_v4_shadow_candidate.py",
)
_V4_SOURCE_PATH = _IMPLEMENTATION_PATHS[-1]
_V4_REGISTRATION_CONSTANTS = (
    "REGION_RESOURCE_V4_REGISTERED_MANIFEST_FILE_SHA256",
    "REGION_RESOURCE_V4_REGISTERED_MANIFEST_CONTENT_SHA256",
    "REGION_RESOURCE_V4_REGISTERED_MODEL_STATE_SHA256",
    "REGION_RESOURCE_V4_REGISTERED_BUNDLE_MANIFEST_SHA256",
    "REGION_RESOURCE_V4_REGISTERED_DATASET_SHA256",
)
_PERMISSION_FIELDS = (
    "formal_evaluation_authorized",
    "assist_enabled",
    "authority_enabled",
    "assignment_enabled",
    "takeover_enabled",
    "coalition_commit_enabled",
    "control_enabled",
    "production_runtime_ack_enabled",
    "physical_permission_available",
    "actual_adoption_claimed",
    "benefit_claimed",
)
_FORBIDDEN_DATASET_KEYS = frozenset(
    {
        "actor_id",
        "actor_name",
        "actor_truth_id",
        "evaluator_truth",
        "evaluator_truth_id",
        "global_track_id",
        "object_id",
        "object_name",
        "object_truth_id",
        "offline_truth",
        "segmentation_id",
        "target_id",
        "target_truth_id",
        "truth_id",
    }
)
_EXPECTED_ADMISSION_REASONS = frozenset(
    {
        "admission_closed",
        "all_production_permissions_false",
        "development_only",
        "external_truth_free_dataset_only",
        "formal_holdout_not_completed",
        "positive_negative_confidence_calibration_required",
        "reward_evidence_unavailable",
        "rule_fallback_required",
        "runtime_preflight_pending",
        "shadow_only",
    }
)
_SHA256_HEX_LENGTH = 64


class D4V4CandidateAuditError(ValueError):
    """Stable fail-closed error for invalid D4 v4 audit evidence."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class D4V4CandidateAuditInputs:
    """Caller-frozen inputs for the independent audit."""

    repository_root: Path
    candidate_root: Path
    external_evidence_root: Path
    audit_id: str
    evaluated_at_utc: str
    expected_manifest_content_sha256: str
    expected_model_state_sha256: str
    expected_dataset_sha256: str
    expected_source_git_commit: str
    expected_v3_registry_tree_sha256: str
    profile_version: str = D4_V4_CANDIDATE_AUDIT_PROFILE_VERSION
    schema_version: str = D4_V4_CANDIDATE_AUDIT_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        root = Path(self.repository_root).expanduser().resolve()
        candidate = _resolve_input_path(root, self.candidate_root)
        external = _resolve_input_path(root, self.external_evidence_root)
        if not root.is_dir():
            _fail("repository_root_unavailable", str(root))
        if not candidate.is_dir():
            _fail("candidate_root_unavailable", str(candidate))
        if not external.is_dir():
            _fail("external_evidence_root_unavailable", str(external))
        object.__setattr__(self, "repository_root", root)
        object.__setattr__(self, "candidate_root", candidate)
        object.__setattr__(self, "external_evidence_root", external)
        if self.schema_version != D4_V4_CANDIDATE_AUDIT_INPUT_SCHEMA_VERSION:
            _fail("input_schema_mismatch", self.schema_version)
        if self.profile_version != D4_V4_CANDIDATE_AUDIT_PROFILE_VERSION:
            _fail("input_profile_mismatch", self.profile_version)
        for name in ("audit_id", "evaluated_at_utc"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                _fail("input_string_invalid", name)
        for name in (
            "expected_manifest_content_sha256",
            "expected_model_state_sha256",
            "expected_dataset_sha256",
            "expected_v3_registry_tree_sha256",
        ):
            object.__setattr__(
                self,
                name,
                _normalise_sha256(getattr(self, name), name),
            )
        commit = str(self.expected_source_git_commit).lower()
        if len(commit) != 40 or any(
            character not in "0123456789abcdef" for character in commit
        ):
            _fail("input_source_git_commit_invalid", commit)
        object.__setattr__(self, "expected_source_git_commit", commit)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        repository_root: str | Path,
    ) -> "D4V4CandidateAuditInputs":
        expected = {
            "schema_version",
            "audit_id",
            "evaluated_at_utc",
            "profile_version",
            "candidate_root",
            "external_evidence_root",
            "expected_manifest_content_sha256",
            "expected_model_state_sha256",
            "expected_dataset_sha256",
            "expected_source_git_commit",
            "expected_v3_registry_tree_sha256",
        }
        _require_exact_keys(payload, expected, "audit input")
        return cls(
            repository_root=Path(repository_root),
            candidate_root=Path(str(payload["candidate_root"])),
            external_evidence_root=Path(
                str(payload["external_evidence_root"])
            ),
            audit_id=str(payload["audit_id"]),
            evaluated_at_utc=str(payload["evaluated_at_utc"]),
            expected_manifest_content_sha256=str(
                payload["expected_manifest_content_sha256"]
            ),
            expected_model_state_sha256=str(
                payload["expected_model_state_sha256"]
            ),
            expected_dataset_sha256=str(
                payload["expected_dataset_sha256"]
            ),
            expected_source_git_commit=str(
                payload["expected_source_git_commit"]
            ),
            expected_v3_registry_tree_sha256=str(
                payload["expected_v3_registry_tree_sha256"]
            ),
            profile_version=str(payload["profile_version"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class _ModelRecord:
    graph: Any
    snapshot: Any
    target: Any
    target_positive: bool
    target_signature: str
    rule_signature: str
    candidate_signature: str
    action_consistent: bool
    executable_difference: bool
    intervention_valid: bool
    projection_rejected: bool
    confidence: float


def load_d4_v4_candidate_audit_inputs(
    input_spec: str | Path,
    *,
    repository_root: str | Path,
) -> D4V4CandidateAuditInputs:
    """Load and validate one frozen audit-input specification."""

    payload = _load_json(Path(input_spec), "audit input specification")
    return D4V4CandidateAuditInputs.from_mapping(
        payload,
        repository_root=repository_root,
    )


def audit_d4_v4_candidate(
    inputs: D4V4CandidateAuditInputs,
) -> dict[str, Any]:
    """Audit one D4 v4 candidate without registration or holdout execution."""

    candidate = inputs.candidate_root
    manifest_path = candidate / D4_V4_MANIFEST_FILE
    manifest = _load_json(manifest_path, "candidate manifest")
    _expect(
        manifest.get("schema") == D4_V4_MANIFEST_SCHEMA,
        "candidate_manifest_schema_mismatch",
        str(manifest.get("schema")),
    )
    _expect(
        manifest.get("candidate_id") == D4_V4_CANDIDATE_ID
        and manifest.get("model_version") == D4_V4_MODEL_VERSION,
        "candidate_identity_mismatch",
        f"{manifest.get('candidate_id')}:{manifest.get('model_version')}",
    )
    manifest_content_sha = _verify_content_sha(
        manifest,
        content_field="content_sha256",
        code="candidate_manifest_content_sha256_mismatch",
    )
    _expect(
        manifest_content_sha
        == inputs.expected_manifest_content_sha256,
        "candidate_manifest_content_anchor_mismatch",
        manifest_content_sha,
    )
    _expect(
        _normalise_sha256(
            manifest.get("model_state_sha256"),
            "candidate model_state_sha256",
        )
        == inputs.expected_model_state_sha256,
        "candidate_model_state_anchor_mismatch",
        str(manifest.get("model_state_sha256")),
    )
    _expect(
        _normalise_sha256(
            manifest.get("dataset_sha256"),
            "candidate dataset_sha256",
        )
        == inputs.expected_dataset_sha256,
        "candidate_dataset_anchor_mismatch",
        str(manifest.get("dataset_sha256")),
    )

    candidate_tree = _audit_candidate_tree(candidate, manifest)
    source_lineage = _audit_source_lineage(
        inputs,
        manifest=manifest,
        candidate_tree=candidate_tree,
    )
    cross_bindings = _audit_cross_bindings(
        inputs,
        manifest=manifest,
        candidate_tree=candidate_tree,
    )
    registry = _audit_registry_boundary(inputs, source_lineage)
    model_evidence = _recompute_model_evidence(
        candidate,
        manifest=manifest,
        training=cross_bindings["payloads"]["training_summary"],
        build_config=cross_bindings["payloads"]["training_config"],
    )
    fixture = _audit_development_fixture(
        candidate,
        declared=manifest["development_fixture"],
        build_config=cross_bindings["payloads"]["training_config"],
        expected_state_dict_sha256=inputs.expected_model_state_sha256,
    )
    permissions = _audit_permission_boundary(
        manifest,
        training=cross_bindings["payloads"]["training_summary"],
        bundle_manifest=cross_bindings["payloads"]["bundle_manifest"],
        gate=cross_bindings["payloads"]["intervention_gate"],
        fixture=fixture,
        registry=registry,
    )
    governance = _audit_zero_use_claims(
        cross_bindings=cross_bindings,
        model_evidence=model_evidence,
        fixture=fixture,
    )

    result: dict[str, Any] = {
        "schema_version": D4_V4_CANDIDATE_AUDIT_SCHEMA_VERSION,
        "audit_id": inputs.audit_id,
        "evaluated_at_utc": inputs.evaluated_at_utc,
        "profile_version": inputs.profile_version,
        "status": "pass_development_integrity_only_admission_closed",
        "audit_passed": True,
        "audit_blocker_codes": [],
        "admission_blocker_codes": list(D4_V4_ADMISSION_BLOCKER_CODES),
        "anchors": {
            "manifest_content_sha256": manifest_content_sha,
            "manifest_file_sha256": candidate_tree[
                "manifest_file_sha256"
            ],
            "model_state_sha256": inputs.expected_model_state_sha256,
            "dataset_sha256": inputs.expected_dataset_sha256,
            "dataset_split_sha256": manifest["dataset_split_sha256"],
            "source_git_commit": inputs.expected_source_git_commit,
            "v3_registry_tree_sha256": (
                inputs.expected_v3_registry_tree_sha256
            ),
        },
        "candidate_tree": candidate_tree,
        "source_lineage": source_lineage,
        "external_dataset_binding": {
            key: value
            for key, value in cross_bindings.items()
            if key != "payloads"
        },
        "dataset_and_use_governance": governance,
        "actor_recalculation": model_evidence["actor"],
        "confidence_recalculation": model_evidence["confidence"],
        "checkpoint_recalculation": model_evidence["checkpoints"],
        "development_fixture": fixture,
        "v3_registry": registry,
        "permission_and_admission_boundary": permissions,
        "fail_closed_guards": {
            "candidate_tree_exact_closure_required": True,
            "candidate_artifact_sha256_required": True,
            "manifest_content_external_anchor_required": True,
            "model_state_external_anchor_required": True,
            "dataset_external_anchor_required": True,
            "permission_fields_must_all_be_false": True,
            "candidate_self_rehash_cannot_replace_external_anchor": True,
            "negative_control_contracts": {
                "candidate_artifact_byte_tamper": (
                    "candidate_artifact_sha256_mismatch"
                ),
                "self_rehashed_permission_claim_tamper": (
                    "candidate_manifest_content_anchor_mismatch"
                ),
            },
        },
        "evidence_boundary": {
            "development_training_and_validation_evidence_only": True,
            "development_fixture_is_training_domain_smoke_only": True,
            "independent_generalization_evidence_available": False,
            "formal_validation_claim_allowed": False,
            "formal_holdout_executed_by_d6": False,
            "runtime_preflight_executed_by_d6": False,
            "candidate_registered_by_d6": False,
            "permission_change_proposed": False,
        },
        "conclusion": {
            "candidate_integrity": "passed",
            "development_metric_recalculation": "passed",
            "formal_admission": "closed",
            "runtime_eligibility": "unregistered_unavailable",
            "thin_margin_warning": True,
            "interpretation": (
                "The fixed-gate checkpoint has zero observed false-positive "
                "passes on TRAIN/VALIDATION, but positive recall and margins "
                "are thin; the fixture is TRAIN-domain smoke only, and "
                "runtime outcome and benefit remain unavailable. This is not "
                "formal holdout or generalization evidence."
            ),
        },
    }
    result["content_sha256"] = _canonical_sha256(result)
    return result


def _audit_candidate_tree(
    root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if root.is_symlink():
        _fail("candidate_root_symlink_forbidden", str(root))
    paths = sorted(root.rglob("*"))
    symlinks = [str(path.relative_to(root)) for path in paths if path.is_symlink()]
    _expect(
        not symlinks,
        "candidate_tree_symlink_forbidden",
        ",".join(symlinks),
    )
    special = [
        str(path.relative_to(root))
        for path in paths
        if not path.is_file() and not path.is_dir()
    ]
    _expect(
        not special,
        "candidate_tree_special_file_forbidden",
        ",".join(special),
    )

    declared_raw = _mapping(
        manifest.get("artifact_files"),
        "candidate artifact_files",
    )
    declared: dict[str, str] = {}
    for relative, digest in declared_raw.items():
        normalized = _safe_relative_file(str(relative))
        _expect(
            normalized != D4_V4_MANIFEST_FILE,
            "candidate_manifest_must_not_self_declare",
            normalized,
        )
        declared[normalized] = _normalise_sha256(
            digest,
            f"candidate artifact {normalized}",
        )
    files = {
        str(path.relative_to(root)): path
        for path in paths
        if path.is_file()
    }
    expected_files = set(declared) | {D4_V4_MANIFEST_FILE}
    _expect(
        set(files) == expected_files,
        "candidate_file_inventory_mismatch",
        _set_difference_detail(expected_files, set(files)),
    )
    expected_directories = _parent_directories(expected_files)
    observed_directories = {
        str(path.relative_to(root))
        for path in paths
        if path.is_dir()
    }
    _expect(
        observed_directories == expected_directories,
        "candidate_directory_inventory_mismatch",
        _set_difference_detail(expected_directories, observed_directories),
    )

    actual: dict[str, str] = {}
    file_modes: dict[str, str] = {}
    for relative, path in sorted(files.items()):
        digest = _sha256_file(path)
        actual[relative] = digest
        file_modes[relative] = f"{path.stat().st_mode & 0o777:03o}"
        if relative != D4_V4_MANIFEST_FILE:
            _expect(
                digest == declared[relative],
                "candidate_artifact_sha256_mismatch",
                relative,
            )
    return {
        "passed": True,
        "root": str(root),
        "file_count": len(files),
        "directory_count": len(observed_directories) + 1,
        "artifact_file_count": len(declared),
        "manifest_file_sha256": actual[D4_V4_MANIFEST_FILE],
        "directories": sorted(observed_directories),
        "artifact_sha256": actual,
        "file_modes": file_modes,
        "all_artifacts_manifest_bound": True,
        "symlink_count": 0,
        "special_file_count": 0,
    }


def _audit_source_lineage(
    inputs: D4V4CandidateAuditInputs,
    *,
    manifest: Mapping[str, Any],
    candidate_tree: Mapping[str, Any],
) -> dict[str, Any]:
    source = _load_json(
        inputs.candidate_root / "source_implementation_summary.json",
        "source implementation summary",
    )
    _expect(
        source.get("source_git_commit")
        == inputs.expected_source_git_commit,
        "source_git_commit_mismatch",
        str(source.get("source_git_commit")),
    )
    _expect(
        source.get("source_worktree_dirty") is False
        and source.get("clean_lineage_claimed") is True,
        "source_clean_lineage_claim_mismatch",
        "source must claim a clean build",
    )
    resolved_commit = _git_output(
        inputs.repository_root,
        ("rev-parse", "--verify", f"{inputs.expected_source_git_commit}^{{commit}}"),
    ).decode("utf-8").strip()
    _expect(
        resolved_commit == inputs.expected_source_git_commit,
        "source_git_commit_resolution_mismatch",
        resolved_commit,
    )

    declared_files = _mapping(
        source.get("implementation_files"),
        "source implementation_files",
    )
    _expect(
        set(declared_files) == set(_IMPLEMENTATION_PATHS),
        "source_implementation_inventory_mismatch",
        _set_difference_detail(set(_IMPLEMENTATION_PATHS), set(declared_files)),
    )
    commit_file_sha256: dict[str, str] = {}
    current_file_sha256: dict[str, str] = {}
    source_bytes: dict[str, bytes] = {}
    for relative in _IMPLEMENTATION_PATHS:
        content = _git_output(
            inputs.repository_root,
            ("show", f"{inputs.expected_source_git_commit}:{relative}"),
        )
        source_bytes[relative] = content
        commit_digest = sha256(content).hexdigest()
        current_digest = _sha256_file(inputs.repository_root / relative)
        declared_digest = _normalise_sha256(
            declared_files[relative],
            f"source implementation {relative}",
        )
        _expect(
            commit_digest == declared_digest,
            "source_commit_file_sha256_mismatch",
            relative,
        )
        _expect(
            current_digest == commit_digest,
            "source_current_file_differs_from_audited_commit",
            relative,
        )
        commit_file_sha256[relative] = commit_digest
        current_file_sha256[relative] = current_digest

    inventory_sha = _canonical_sha256(commit_file_sha256)
    _expect(
        inventory_sha == source.get("implementation_inventory_sha256"),
        "source_implementation_inventory_sha256_mismatch",
        inventory_sha,
    )
    identity_content = dict(source)
    declared_identity = identity_content.pop("source_identity_sha256", None)
    identity_sha = _canonical_sha256(identity_content)
    _expect(
        identity_sha == declared_identity
        and identity_sha == manifest.get("source_identity_sha256"),
        "source_identity_sha256_mismatch",
        identity_sha,
    )
    registration_constants = _extract_none_constants(
        source_bytes[_V4_SOURCE_PATH],
        _V4_REGISTRATION_CONSTANTS,
    )
    current_head = _git_output(
        inputs.repository_root,
        ("rev-parse", "HEAD"),
    ).decode("utf-8").strip()
    return {
        "passed": True,
        "source_git_commit": resolved_commit,
        "current_head": current_head,
        "current_head_matches_source_commit": current_head == resolved_commit,
        "source_worktree_dirty_at_build": False,
        "clean_lineage_claimed": True,
        "implementation_file_count": len(commit_file_sha256),
        "implementation_file_sha256": commit_file_sha256,
        "current_implementation_file_sha256": current_file_sha256,
        "implementation_inventory_sha256": inventory_sha,
        "source_identity_sha256": identity_sha,
        "registration_constants": registration_constants,
        "all_registration_constants_none": all(
            value is None for value in registration_constants.values()
        ),
        "source_summary_file_sha256": candidate_tree["artifact_sha256"][
            "source_implementation_summary.json"
        ],
    }


def _audit_cross_bindings(
    inputs: D4V4CandidateAuditInputs,
    *,
    manifest: Mapping[str, Any],
    candidate_tree: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = inputs.candidate_root
    external = inputs.external_evidence_root
    training_config = _load_json(
        candidate / "training_config.json",
        "training config",
    )
    training = _load_json(
        candidate / "training_summary.json",
        "training summary",
    )
    source_summary = _load_json(
        candidate / "source_implementation_summary.json",
        "source implementation summary",
    )
    gate = _load_json(candidate / "intervention_gate.json", "intervention gate")
    candidate_evidence = _load_json(
        candidate / "external_dataset_evidence.json",
        "candidate external evidence",
    )
    bundle_manifest = _load_json(
        candidate / "bundle/manifest.json",
        "bundle manifest",
    )
    development_manifest = _load_json(
        candidate / "development_dataset/manifest.json",
        "development dataset manifest",
    )
    bundle_training_manifest = _load_json(
        candidate / "bundle/training_dataset_manifest.json",
        "bundle training dataset manifest",
    )
    external_evidence = _load_json(
        external / "external_dataset_evidence.json",
        "external evidence",
    )
    export_summary = _load_json(
        external / "export_summary.json",
        "external export summary",
    )
    derivation_name = _safe_relative_file(
        str(export_summary.get("derivation_manifest"))
    )
    _expect(
        "/" not in derivation_name,
        "external_derivation_manifest_path_invalid",
        derivation_name,
    )
    source_derivation_path = external / derivation_name
    source_derivation = _load_json(
        source_derivation_path,
        "external source derivation",
    )
    external_dataset_manifest = _load_json(
        external / "dataset/manifest.json",
        "external dataset manifest",
    )

    config_sha = _canonical_sha256(training_config)
    _expect(
        config_sha == manifest.get("config_sha256"),
        "training_config_content_binding_mismatch",
        config_sha,
    )
    training_sha = _verify_content_sha(
        training,
        content_field="content_sha256",
        code="training_summary_content_sha256_mismatch",
    )
    _expect(
        training_sha == manifest.get("training_summary_content_sha256"),
        "training_summary_manifest_binding_mismatch",
        training_sha,
    )
    gate_sha = _verify_content_sha(
        gate,
        content_field="content_sha256",
        code="intervention_gate_content_sha256_mismatch",
    )
    _expect(
        gate_sha == manifest.get("runtime_gate_content_sha256"),
        "intervention_gate_manifest_binding_mismatch",
        gate_sha,
    )
    evidence_sha = _verify_content_sha(
        candidate_evidence,
        content_field="content_sha256",
        code="external_evidence_content_sha256_mismatch",
    )
    _expect(
        evidence_sha == manifest.get("external_dataset_evidence_sha256"),
        "external_evidence_manifest_binding_mismatch",
        evidence_sha,
    )
    external_evidence_sha = _verify_content_sha(
        external_evidence,
        content_field="content_sha256",
        code="external_source_evidence_content_sha256_mismatch",
    )
    _expect(
        candidate_evidence == external_evidence
        and evidence_sha == external_evidence_sha,
        "candidate_external_evidence_byte_binding_mismatch",
        evidence_sha,
    )
    candidate_evidence_file_sha = candidate_tree["artifact_sha256"][
        "external_dataset_evidence.json"
    ]
    external_evidence_file_sha = _sha256_file(
        external / "external_dataset_evidence.json"
    )
    _expect(
        candidate_evidence_file_sha == external_evidence_file_sha,
        "candidate_external_evidence_byte_binding_mismatch",
        external_evidence_file_sha,
    )

    development_manifest_sha = _sha256_file(
        candidate / "development_dataset/manifest.json"
    )
    bundle_training_manifest_sha = _sha256_file(
        candidate / "bundle/training_dataset_manifest.json"
    )
    external_manifest_sha = _sha256_file(external / "dataset/manifest.json")
    _expect(
        development_manifest == external_dataset_manifest
        and bundle_training_manifest == external_dataset_manifest
        and development_manifest_sha
        == bundle_training_manifest_sha
        == external_manifest_sha,
        "dataset_manifest_cross_binding_mismatch",
        external_manifest_sha,
    )
    dataset_sha = _verify_dataset_manifest_content(external_dataset_manifest)
    _expect(
        dataset_sha == inputs.expected_dataset_sha256,
        "external_dataset_content_anchor_mismatch",
        dataset_sha,
    )
    split_sha = _verify_split_content(external_dataset_manifest["split"])
    _expect(
        split_sha == manifest.get("dataset_split_sha256"),
        "external_dataset_split_binding_mismatch",
        split_sha,
    )

    for payload_name, payload in (
        ("candidate evidence", candidate_evidence),
        ("training summary evidence", training["external_dataset_evidence"]),
    ):
        _expect(
            payload.get("dataset_sha256") == dataset_sha
            and payload.get("dataset_split_sha256") == split_sha,
            "external_dataset_evidence_dataset_binding_mismatch",
            payload_name,
        )
    _expect(
        bundle_manifest.get("training_dataset_sha256") == dataset_sha
        and bundle_manifest.get("training_split_sha256") == split_sha
        and bundle_manifest.get("training_manifest_sha256")
        == bundle_training_manifest_sha,
        "bundle_dataset_binding_mismatch",
        "bundle manifest",
    )
    _expect(
        bundle_manifest.get("state_dict_sha256")
        == inputs.expected_model_state_sha256
        and manifest.get("bundle_manifest_sha256")
        == candidate_tree["artifact_sha256"]["bundle/manifest.json"],
        "bundle_model_binding_mismatch",
        str(bundle_manifest.get("state_dict_sha256")),
    )

    source_artifact_sha = _sha256_file(source_derivation_path)
    _expect(
        source_artifact_sha
        == candidate_evidence.get("source_artifact_sha256")
        == training["external_dataset_evidence"].get(
            "source_artifact_sha256"
        )
        == source_summary.get("external_source_artifact_sha256"),
        "external_source_artifact_binding_mismatch",
        source_artifact_sha,
    )
    _expect(
        source_summary.get("config_sha256") == config_sha
        and source_summary.get("external_dataset_evidence_sha256")
        == evidence_sha
        and source_summary.get("source_identity_sha256")
        == manifest.get("source_identity_sha256"),
        "source_summary_cross_binding_mismatch",
        str(source_summary.get("source_identity_sha256")),
    )
    derivation_content_sha = _verify_content_sha(
        source_derivation,
        content_field="content_sha256",
        code="source_derivation_content_sha256_mismatch",
    )
    export_content_sha = _verify_content_sha(
        export_summary,
        content_field="content_sha256",
        code="export_summary_content_sha256_mismatch",
    )
    _expect(
        export_summary.get("source_artifact_sha256")
        == source_artifact_sha
        and export_summary.get("dataset_sha256") == dataset_sha
        and export_summary.get("dataset_split_sha256") == split_sha
        and export_summary.get("external_dataset_evidence_sha256")
        == evidence_sha,
        "external_export_summary_binding_mismatch",
        export_content_sha,
    )
    derivation_output = _mapping(
        source_derivation.get("output"),
        "source derivation output",
    )
    derivation_governance = _mapping(
        source_derivation.get("governance"),
        "source derivation governance",
    )
    _expect(
        derivation_output.get("dataset_sha256") == dataset_sha
        and derivation_output.get("split_sha256") == split_sha
        and derivation_governance.get("dataset_sha256") == dataset_sha
        and derivation_governance.get("dataset_split_sha256") == split_sha,
        "source_derivation_dataset_binding_mismatch",
        derivation_content_sha,
    )

    episode_binding = _audit_episode_cross_binding(
        candidate=candidate,
        external=external,
        dataset_manifest=external_dataset_manifest,
        candidate_tree=candidate_tree,
    )
    return {
        "passed": True,
        "config_content_sha256": config_sha,
        "training_summary_content_sha256": training_sha,
        "intervention_gate_content_sha256": gate_sha,
        "external_evidence_content_sha256": evidence_sha,
        "external_evidence_file_sha256": external_evidence_file_sha,
        "source_derivation_file_sha256": source_artifact_sha,
        "source_derivation_content_sha256": derivation_content_sha,
        "export_summary_file_sha256": _sha256_file(
            external / "export_summary.json"
        ),
        "export_summary_content_sha256": export_content_sha,
        "dataset_manifest_file_sha256": external_manifest_sha,
        "dataset_sha256": dataset_sha,
        "dataset_split_sha256": split_sha,
        "candidate_external_evidence_byte_equal": True,
        "candidate_development_manifest_byte_equal": True,
        "bundle_training_manifest_byte_equal": True,
        "episode_binding": episode_binding,
        "external_repository": source_derivation.get("repository"),
        "source_dataset_inventory": source_derivation.get("source"),
        "observable_label_audit": _mapping(
            _mapping(
                source_derivation.get("generation"),
                "source derivation generation",
            ).get("observable_label_audit"),
            "observable label audit",
        ),
        "payloads": {
            "training_config": training_config,
            "training_summary": training,
            "source_summary": source_summary,
            "intervention_gate": gate,
            "bundle_manifest": bundle_manifest,
            "source_derivation": source_derivation,
            "export_summary": export_summary,
            "external_evidence": external_evidence,
            "dataset_manifest": external_dataset_manifest,
        },
    }


def _audit_episode_cross_binding(
    *,
    candidate: Path,
    external: Path,
    dataset_manifest: Mapping[str, Any],
    candidate_tree: Mapping[str, Any],
) -> dict[str, Any]:
    entries = tuple(
        _mapping(item, "dataset episode")
        for item in _sequence(dataset_manifest.get("episodes"), "dataset episodes")
    )
    by_split: dict[str, list[Mapping[str, Any]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    for entry in entries:
        split = str(entry.get("split"))
        _expect(
            split in by_split,
            "dataset_episode_split_invalid",
            split,
        )
        by_split[split].append(entry)
    selected = tuple(by_split["train"] + by_split["validation"])
    selected_relative = {
        _safe_relative_file(str(entry.get("relative_path"))): entry
        for entry in selected
    }
    test_relative = {
        _safe_relative_file(str(entry.get("relative_path")))
        for entry in by_split["test"]
    }
    observed_candidate_relative = {
        relative.removeprefix("development_dataset/")
        for relative in candidate_tree["artifact_sha256"]
        if relative.startswith("development_dataset/episodes/")
    }
    _expect(
        observed_candidate_relative == set(selected_relative),
        "candidate_selected_episode_inventory_mismatch",
        _set_difference_detail(
            set(selected_relative),
            observed_candidate_relative,
        ),
    )
    _expect(
        not (observed_candidate_relative & test_relative),
        "candidate_test_payload_present",
        ",".join(sorted(observed_candidate_relative & test_relative)),
    )

    split_counts: dict[str, dict[str, int]] = {}
    selected_hashes: dict[str, str] = {}
    for split in ("train", "validation"):
        frame_count = 0
        reward_available_count = 0
        truth_identifier_count = 0
        for entry in by_split[split]:
            relative = _safe_relative_file(str(entry["relative_path"]))
            declared_digest = _normalise_sha256(
                entry.get("episode_sha256"),
                f"dataset episode {relative}",
            )
            candidate_path = candidate / "development_dataset" / relative
            external_path = external / "dataset" / relative
            if external_path.is_symlink():
                _fail("external_selected_episode_symlink_forbidden", relative)
            candidate_digest = _sha256_file(candidate_path)
            external_digest = _sha256_file(external_path)
            _expect(
                candidate_digest == external_digest == declared_digest,
                "selected_episode_cross_binding_mismatch",
                relative,
            )
            payload_audit = _audit_selected_episode_payload(candidate_path)
            _expect(
                payload_audit["frame_count"] == int(entry["frame_count"]),
                "selected_episode_frame_count_mismatch",
                relative,
            )
            frame_count += payload_audit["frame_count"]
            reward_available_count += payload_audit[
                "reward_available_count"
            ]
            truth_identifier_count += payload_audit[
                "truth_identifier_count"
            ]
            selected_hashes[relative] = declared_digest
        split_counts[split] = {
            "seed_count": len(
                {int(entry["source"]["seed"]) for entry in by_split[split]}
            ),
            "episode_count": len(by_split[split]),
            "frame_count": frame_count,
            "reward_available_count": reward_available_count,
            "truth_identifier_count": truth_identifier_count,
        }
    return {
        "selected_payload_splits": ["train", "validation"],
        "split_counts": split_counts,
        "selected_episode_count": len(selected),
        "selected_episode_inventory_sha256": _canonical_sha256(
            selected_hashes
        ),
        "candidate_test_payload_file_count": 0,
        "audit_test_payload_read_count": 0,
        "test_manifest_seed_count": len(
            {int(entry["source"]["seed"]) for entry in by_split["test"]}
        ),
        "test_manifest_episode_count": len(by_split["test"]),
        "test_manifest_frame_count": sum(
            int(entry["frame_count"]) for entry in by_split["test"]
        ),
        "test_payload_hash_or_content_read": False,
    }


def _audit_selected_episode_payload(path: Path) -> dict[str, int]:
    frame_count = 0
    reward_available_count = 0
    truth_identifier_count = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        _fail("selected_episode_payload_unavailable", f"{path}:{exc}")
    _expect(lines, "selected_episode_payload_empty", str(path))
    for line_number, line in enumerate(lines, start=1):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            _fail(
                "selected_episode_json_invalid",
                f"{path}:{line_number}:{exc}",
            )
        truth_identifier_count += _count_forbidden_dataset_keys(payload)
        if payload.get("record_type") != "frame":
            continue
        frame_count += 1
        frame = _mapping(payload.get("frame"), "episode frame")
        reward = _mapping(frame.get("reward"), "episode frame reward")
        reward_available_count += int(
            reward.get("availability") == "available"
            or reward.get("value") is not None
        )
    _expect(
        truth_identifier_count == 0,
        "selected_episode_truth_identifier_detected",
        str(path),
    )
    _expect(
        reward_available_count == 0,
        "selected_episode_future_outcome_detected",
        str(path),
    )
    return {
        "frame_count": frame_count,
        "reward_available_count": reward_available_count,
        "truth_identifier_count": truth_identifier_count,
    }


def _recompute_model_evidence(
    candidate: Path,
    *,
    manifest: Mapping[str, Any],
    training: Mapping[str, Any],
    build_config: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        import torch

        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource import (
            DeterministicResourceProjector,
            RegionResourceProjectionConfig,
            RuleRegionResourcePolicy,
            RuleRegionResourcePolicyConfig,
        )
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_dataset import (
            RegionLearningSplit,
            load_region_learning_dataset_splits,
        )
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_learning import (
            LearnedRegionResourcePolicy,
            load_region_behavior_cloning_samples,
            load_region_resource_model_bundle,
        )
    except (ImportError, OSError) as exc:
        _fail("d4_model_audit_dependency_unavailable", type(exc).__name__)

    dataset = load_region_learning_dataset_splits(
        candidate / "development_dataset",
        splits=(RegionLearningSplit.TRAIN, RegionLearningSplit.VALIDATION),
    )
    bundle = load_region_resource_model_bundle(
        candidate / "bundle",
        expected_model_version=D4_V4_MODEL_VERSION,
        expected_state_dict_sha256=str(manifest["model_state_sha256"]),
        map_location="cpu",
        require_training_dataset_manifest=True,
    )
    projection_config = RegionResourceProjectionConfig(
        minimum_reserve_ratio=0.10,
        minimum_reserve_resources=1,
        advisory_ttl_s=1.5,
    )
    projector = DeterministicResourceProjector(projection_config)
    rule_policy = RuleRegionResourcePolicy(
        RuleRegionResourcePolicyConfig(
            projection=projection_config,
            high_threat_weight=2.0,
            uncertainty_weight=0.5,
            transfer_pressure_margin=0.05,
        ),
        projector=projector,
    )
    learned_policy = LearnedRegionResourcePolicy(bundle.model, bundle.manifest)

    records: dict[str, tuple[_ModelRecord, ...]] = {}
    samples_by_split: dict[str, tuple[Any, ...]] = {}
    target_action_inventory = {
        "action_count": 0,
        "resource_quota_nonzero_count": 0,
        "transfer_count": 0,
        "hold_true_count": 0,
        "request_replan_true_count": 0,
    }
    for split in (RegionLearningSplit.TRAIN, RegionLearningSplit.VALIDATION):
        samples = load_region_behavior_cloning_samples(
            dataset,
            split=split,
            device="cpu",
            allow_dirty_source=False,
        )
        frames = tuple(
            frame
            for episode in dataset.episodes(split)
            for frame in episode.frames
        )
        _expect(
            len(samples) == len(frames),
            "model_sample_frame_inventory_mismatch",
            split.value,
        )
        built: list[_ModelRecord] = []
        for sample, frame in zip(samples, frames, strict=True):
            target = frame.target.recommendation
            _expect(
                target is not None,
                "model_target_recommendation_unavailable",
                split.value,
            )
            r0 = rule_policy.recommend(frame.snapshot)
            target_advisory = projector.build_advisory_contract(
                frame.snapshot,
                target,
            )
            r0_advisory = projector.build_advisory_contract(
                frame.snapshot,
                r0,
            )
            target_signature = _executable_signature(target_advisory)
            rule_signature = _executable_signature(r0_advisory)
            target_positive = target_signature != rule_signature
            if target_positive:
                _expect(
                    not _intervention_reasons(
                        frame.snapshot,
                        target,
                        r0,
                        projector=projector,
                    ),
                    "positive_target_intervention_invalid",
                    f"{split.value}:{frame.frame_index}",
                )

            raw = learned_policy.recommend_raw(frame.snapshot)
            projected = projector.project(frame.snapshot, raw)
            candidate_advisory = projector.build_advisory_contract(
                frame.snapshot,
                projected,
            )
            candidate_signature = _executable_signature(candidate_advisory)
            executable = candidate_signature != rule_signature
            reasons = _intervention_reasons(
                frame.snapshot,
                projected,
                r0,
                projector=projector,
            )
            valid = not reasons
            action_consistent = bool(
                candidate_signature == target_signature
                and (valid if target_positive else not executable)
            )
            with torch.no_grad():
                confidence = float(
                    bundle.model(sample.graph).confidence.detach().cpu()
                )
            _expect(
                isfinite(confidence) and 0.0 <= confidence <= 1.0,
                "model_confidence_invalid",
                f"{split.value}:{frame.frame_index}",
            )
            built.append(
                _ModelRecord(
                    graph=sample.graph,
                    snapshot=frame.snapshot,
                    target=target,
                    target_positive=target_positive,
                    target_signature=target_signature,
                    rule_signature=rule_signature,
                    candidate_signature=candidate_signature,
                    action_consistent=action_consistent,
                    executable_difference=executable,
                    intervention_valid=valid,
                    projection_rejected=bool(
                        projected.projection_rejections
                    ),
                    confidence=confidence,
                )
            )
            target_action_inventory["action_count"] += len(target.actions)
            target_action_inventory[
                "resource_quota_nonzero_count"
            ] += sum(
                action.resource_quota_delta != 0
                for action in target.actions
            )
            target_action_inventory["transfer_count"] += len(
                target.transfers
            )
            target_action_inventory["hold_true_count"] += sum(
                action.hold for action in target.actions
            )
            target_action_inventory[
                "request_replan_true_count"
            ] += sum(action.request_replan for action in target.actions)
        records[split.value] = tuple(built)
        samples_by_split[split.value] = tuple(samples)

    actor_metrics = {
        split: _actor_metrics(split_records)
        for split, split_records in records.items()
    }
    confidence_metrics = {
        split: _confidence_metrics(split_records)
        for split, split_records in records.items()
    }
    actor_balance = _actor_class_balance(
        records["train"],
        samples_by_split["train"],
    )
    confidence_balance = _confidence_class_balance(records["train"])
    _compare_recalculated_metrics(
        training,
        actor_metrics=actor_metrics,
        confidence_metrics=confidence_metrics,
        actor_balance=actor_balance,
        confidence_balance=confidence_balance,
        target_action_inventory=target_action_inventory,
    )
    checkpoints = _recalculate_checkpoints(
        training,
        confidence_metrics=confidence_metrics,
    )
    parameter_count = sum(
        int(parameter.numel()) for parameter in bundle.model.parameters()
    )
    parameters_finite = all(
        bool(torch.isfinite(parameter).all().item())
        for parameter in bundle.model.parameters()
    )
    _expect(
        parameter_count == int(training["model_parameter_count"])
        and parameters_finite
        and training.get("model_parameters_finite") is True,
        "model_parameter_inventory_mismatch",
        str(parameter_count),
    )
    _expect(
        int(build_config["confidence_batch_size"])
        >= len(records["train"]),
        "confidence_full_batch_capacity_insufficient",
        str(build_config["confidence_batch_size"]),
    )
    return {
        "actor": {
            "train_only_class_balance": actor_balance,
            "train": actor_metrics["train"],
            "validation": actor_metrics["validation"],
            "target_action_inventory": target_action_inventory,
            "model_parameter_count": parameter_count,
            "model_parameters_finite": parameters_finite,
            "actor_fit_is_behavior_cloning": True,
            "ppo_used": False,
            "weight_source_split": "train",
            "validation_weight_fit_count": 0,
            "test_payload_weight_fit_count": 0,
        },
        "confidence": {
            "fixed_minimum_confidence": D4_V4_FIXED_CONFIDENCE_GATE,
            "train_only_class_balance": confidence_balance,
            "train": confidence_metrics["train"],
            "validation": confidence_metrics["validation"],
            "weight_source_split": "train",
            "train_weight_fit_count": len(records["train"]),
            "validation_weight_fit_count": 0,
            "test_payload_fit_count": 0,
            "truth_identifier_use_count": 0,
            "future_outcome_use_count": 0,
        },
        "checkpoints": checkpoints,
    }


def _actor_metrics(records: Sequence[_ModelRecord]) -> dict[str, Any]:
    positive = sum(record.target_positive for record in records)
    negative = len(records) - positive
    positive_hits = sum(
        record.target_positive
        and record.executable_difference
        and record.candidate_signature == record.target_signature
        and record.intervention_valid
        and not record.projection_rejected
        for record in records
    )
    negative_hits = sum(
        not record.target_positive
        and not record.executable_difference
        and record.candidate_signature == record.target_signature
        and not record.projection_rejected
        for record in records
    )
    positive_recall = positive_hits / positive
    negative_recall = negative_hits / negative
    return {
        "sample_count": len(records),
        "target_positive_count": positive,
        "target_negative_count": negative,
        "actor_positive_hit_count": positive_hits,
        "actor_negative_hit_count": negative_hits,
        "actor_positive_miss_count": positive - positive_hits,
        "actor_negative_miss_count": negative - negative_hits,
        "actor_executable_difference_count": sum(
            record.executable_difference for record in records
        ),
        "actor_projection_rejection_count": sum(
            record.projection_rejected for record in records
        ),
        "actor_invalid_executable_difference_count": sum(
            record.executable_difference and not record.intervention_valid
            for record in records
        ),
        "positive_recall": positive_recall,
        "negative_recall": negative_recall,
        "negative_specificity": negative_recall,
        "minimum_class_recall": min(positive_recall, negative_recall),
        "balanced_recall": (positive_recall + negative_recall) / 2.0,
        "dual_class_checkpoint_threshold_passed": (
            positive_hits > 0 and negative_hits > 0
        ),
    }


def _confidence_metrics(records: Sequence[_ModelRecord]) -> dict[str, Any]:
    labels = tuple(
        bool(record.target_positive and record.action_consistent)
        for record in records
    )
    probabilities = tuple(record.confidence for record in records)
    passed = tuple(
        probability >= D4_V4_FIXED_CONFIDENCE_GATE
        for probability in probabilities
    )
    positive = sum(labels)
    negative = len(labels) - positive
    positive_pass = sum(
        is_pass and label
        for is_pass, label in zip(passed, labels, strict=True)
    )
    negative_pass = sum(
        is_pass and not label
        for is_pass, label in zip(passed, labels, strict=True)
    )
    passing_probabilities = tuple(
        probability
        for probability, is_pass in zip(
            probabilities,
            passed,
            strict=True,
        )
        if is_pass
    )
    _expect(
        passing_probabilities,
        "confidence_fixed_gate_has_no_pass",
        "TRAIN/VALIDATION split",
    )
    positive_recall = positive_pass / positive
    specificity = (negative - negative_pass) / negative
    margins = tuple(
        probability - D4_V4_FIXED_CONFIDENCE_GATE
        for probability in probabilities
    )
    return {
        "sample_count": len(records),
        "target_positive_count": positive,
        "target_negative_count": negative,
        "positive_threshold_pass_count": positive_pass,
        "negative_threshold_pass_count": negative_pass,
        "threshold_pass_count": sum(passed),
        "inconsistent_threshold_pass_count": sum(
            is_pass and not record.action_consistent
            for is_pass, record in zip(passed, records, strict=True)
        ),
        "executable_threshold_pass_count": sum(
            is_pass and record.executable_difference
            for is_pass, record in zip(passed, records, strict=True)
        ),
        "positive_recall": positive_recall,
        "negative_recall": specificity,
        "negative_specificity": specificity,
        "balanced_class_rate": (positive_recall + specificity) / 2.0,
        "brier_score": sum(
            (probability - float(label)) ** 2
            for probability, label in zip(
                probabilities,
                labels,
                strict=True,
            )
        )
        / len(records),
        "confidence_minimum": min(probabilities),
        "confidence_mean": sum(probabilities) / len(probabilities),
        "confidence_maximum": max(probabilities),
        "thin_margin": {
            "closest_absolute_margin_to_gate": min(
                abs(margin) for margin in margins
            ),
            "minimum_passing_margin": min(
                probability - D4_V4_FIXED_CONFIDENCE_GATE
                for probability in passing_probabilities
            ),
            "maximum_passing_margin": max(
                probability - D4_V4_FIXED_CONFIDENCE_GATE
                for probability in passing_probabilities
            ),
            "maximum_negative_margin": max(
                record.confidence - D4_V4_FIXED_CONFIDENCE_GATE
                for record, label in zip(records, labels, strict=True)
                if not label
            ),
            "positive_below_gate_count": positive - positive_pass,
            "thin_margin_warning": True,
        },
    }


def _actor_class_balance(
    records: Sequence[_ModelRecord],
    samples: Sequence[Any],
) -> dict[str, Any]:
    positive = sum(record.target_positive for record in records)
    negative = len(records) - positive
    edge_target_count = sum(
        int(sample.target.edge_continuous.numel()) for sample in samples
    )
    nonzero_edge_target_count = sum(
        int(
            (
                sample.target.edge_continuous.abs() > 1.0e-12
            ).count_nonzero().item()
        )
        for sample in samples
    )
    zero_edge_target_count = edge_target_count - nonzero_edge_target_count
    raw_positive_ratio = negative / positive
    raw_edge_ratio = zero_edge_target_count / nonzero_edge_target_count
    return {
        "train_sample_count": len(records),
        "target_positive_count": positive,
        "target_negative_count": negative,
        "edge_target_count": edge_target_count,
        "nonzero_edge_target_count": nonzero_edge_target_count,
        "zero_edge_target_count": zero_edge_target_count,
        "raw_positive_sample_ratio": raw_positive_ratio,
        "raw_nonzero_edge_ratio": raw_edge_ratio,
        "positive_sample_weight": min(
            raw_positive_ratio,
            D4_V4_POSITIVE_SAMPLE_WEIGHT_CAP,
        ),
        "negative_sample_weight": 1.0,
        "nonzero_edge_weight": min(
            raw_edge_ratio,
            D4_V4_NONZERO_EDGE_WEIGHT_CAP,
        ),
        "zero_edge_weight": 1.0,
        "positive_sample_weight_clipped": (
            raw_positive_ratio > D4_V4_POSITIVE_SAMPLE_WEIGHT_CAP
        ),
        "nonzero_edge_weight_clipped": (
            raw_edge_ratio > D4_V4_NONZERO_EDGE_WEIGHT_CAP
        ),
        "weight_source_split": "train",
        "validation_weight_fit_count": 0,
        "test_payload_weight_fit_count": 0,
    }


def _confidence_class_balance(
    records: Sequence[_ModelRecord],
) -> dict[str, Any]:
    labels = tuple(
        bool(record.target_positive and record.action_consistent)
        for record in records
    )
    positive = sum(labels)
    negative = len(labels) - positive
    inconsistent_negative = sum(
        not label and not record.action_consistent
        for label, record in zip(labels, records, strict=True)
    )
    executable_negative = sum(
        not label and record.executable_difference
        for label, record in zip(labels, records, strict=True)
    )
    raw_positive_ratio = negative / positive
    raw_inconsistent_ratio = negative / inconsistent_negative
    raw_executable_ratio = negative / executable_negative
    return {
        "train_sample_count": len(records),
        "target_positive_count": positive,
        "target_negative_count": negative,
        "inconsistent_negative_count": inconsistent_negative,
        "executable_negative_count": executable_negative,
        "ordinary_negative_count": negative - inconsistent_negative,
        "raw_positive_sample_ratio": raw_positive_ratio,
        "raw_inconsistent_negative_ratio": raw_inconsistent_ratio,
        "raw_executable_negative_ratio": raw_executable_ratio,
        "positive_sample_weight": min(
            raw_positive_ratio,
            D4_V4_POSITIVE_SAMPLE_WEIGHT_CAP,
        ),
        "negative_sample_weight": 1.0,
        "inconsistent_negative_weight": min(
            raw_inconsistent_ratio,
            D4_V4_POSITIVE_SAMPLE_WEIGHT_CAP,
        ),
        "executable_negative_weight": min(
            raw_executable_ratio,
            D4_V4_CONFIDENCE_HARD_NEGATIVE_WEIGHT_CAP,
        ),
        "positive_sample_weight_clipped": (
            raw_positive_ratio > D4_V4_POSITIVE_SAMPLE_WEIGHT_CAP
        ),
        "inconsistent_negative_weight_clipped": (
            raw_inconsistent_ratio > D4_V4_POSITIVE_SAMPLE_WEIGHT_CAP
        ),
        "executable_negative_weight_clipped": (
            raw_executable_ratio
            > D4_V4_CONFIDENCE_HARD_NEGATIVE_WEIGHT_CAP
        ),
        "weight_source_split": "train",
        "validation_weight_fit_count": 0,
        "test_payload_weight_fit_count": 0,
    }


def _compare_recalculated_metrics(
    training: Mapping[str, Any],
    *,
    actor_metrics: Mapping[str, Mapping[str, Any]],
    confidence_metrics: Mapping[str, Mapping[str, Any]],
    actor_balance: Mapping[str, Any],
    confidence_balance: Mapping[str, Any],
    target_action_inventory: Mapping[str, int],
) -> None:
    _expect(
        target_action_inventory == training.get("target_action_inventory"),
        "target_action_inventory_mismatch",
        str(target_action_inventory),
    )
    for split in ("train", "validation"):
        declared_actor = _mapping(
            training.get(f"{split}_actor_audit"),
            f"training {split} actor audit",
        )
        calculated_actor = actor_metrics[split]
        actor_field_map = {
            "sample_count": "sample_count",
            "target_positive_count": "target_positive_count",
            "target_negative_count": "target_negative_count",
            "actor_positive_hit_count": "actor_positive_hit_count",
            "actor_negative_hit_count": "actor_negative_hit_count",
            "actor_positive_miss_count": "actor_positive_miss_count",
            "actor_negative_miss_count": "actor_negative_miss_count",
            "actor_executable_difference_count": (
                "actor_executable_difference_count"
            ),
            "actor_projection_rejection_count": (
                "actor_projection_rejection_count"
            ),
            "actor_invalid_executable_difference_count": (
                "actor_invalid_executable_difference_count"
            ),
            "positive_hit_rate": "positive_recall",
            "negative_hit_rate": "negative_recall",
            "minimum_class_hit_rate": "minimum_class_recall",
            "balanced_hit_rate": "balanced_recall",
            "dual_class_checkpoint_threshold_passed": (
                "dual_class_checkpoint_threshold_passed"
            ),
        }
        for declared_name, calculated_name in actor_field_map.items():
            _expect_equal_number_or_bool(
                declared_actor.get(declared_name),
                calculated_actor[calculated_name],
                "actor_metric_declaration_mismatch",
                f"{split}:{declared_name}",
            )

        declared_confidence = _mapping(
            _mapping(training.get("confidence_fit"), "confidence fit").get(
                split
            ),
            f"confidence {split}",
        )
        calculated_confidence = confidence_metrics[split]
        confidence_fields = (
            "sample_count",
            "target_positive_count",
            "target_negative_count",
            "positive_threshold_pass_count",
            "negative_threshold_pass_count",
            "threshold_pass_count",
            "inconsistent_threshold_pass_count",
            "executable_threshold_pass_count",
            "brier_score",
            "confidence_minimum",
            "confidence_mean",
            "confidence_maximum",
        )
        for name in confidence_fields:
            _expect_equal_number_or_bool(
                declared_confidence.get(name),
                calculated_confidence[name],
                "confidence_metric_declaration_mismatch",
                f"{split}:{name}",
            )

    declared_actor_balance = _mapping(
        training.get("class_balance"),
        "training actor class balance",
    )
    declared_confidence_balance = _mapping(
        _mapping(training.get("confidence_fit"), "confidence fit").get(
            "class_balance"
        ),
        "confidence class balance",
    )
    for name, value in actor_balance.items():
        if name not in {
            "weight_source_split",
            "validation_weight_fit_count",
            "test_payload_weight_fit_count",
        }:
            _expect_equal_number_or_bool(
                declared_actor_balance.get(name),
                value,
                "actor_weight_declaration_mismatch",
                name,
            )
    _expect(
        declared_actor_balance.get("weight_source_split") == "train"
        and declared_actor_balance.get("validation_weight_fit_count") == 0
        and declared_actor_balance.get("test_payload_weight_fit_count") == 0,
        "actor_weight_source_split_mismatch",
        "actor class balance",
    )
    for name, value in confidence_balance.items():
        if name not in {
            "weight_source_split",
            "validation_weight_fit_count",
            "test_payload_weight_fit_count",
        }:
            _expect_equal_number_or_bool(
                declared_confidence_balance.get(name),
                value,
                "confidence_weight_declaration_mismatch",
                name,
            )
    _expect(
        declared_confidence_balance.get("weight_source_split") == "train"
        and declared_confidence_balance.get("validation_weight_fit_count")
        == 0
        and declared_confidence_balance.get(
            "test_payload_weight_fit_count"
        )
        == 0,
        "confidence_weight_source_split_mismatch",
        "confidence class balance",
    )


def _recalculate_checkpoints(
    training: Mapping[str, Any],
    *,
    confidence_metrics: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    actor_history = tuple(
        _mapping(item, "actor history row")
        for item in _sequence(training.get("history"), "actor history")
    )
    _expect(actor_history, "actor_checkpoint_history_empty", "history")
    actor_best = max(
        actor_history,
        key=lambda item: (
            int(bool(item["dual_class_checkpoint_threshold_passed"])),
            float(item["validation_minimum_class_hit_rate"]),
            float(item["validation_balanced_hit_rate"]),
            -float(item["validation_train_weighted_loss"]),
            -int(item["validation_projection_rejection_count"]),
            -int(item["epoch"]),
        ),
    )
    _expect(
        int(actor_best["epoch"]) == int(training["best_epoch"])
        and isclose(
            float(actor_best["validation_train_weighted_loss"]),
            float(training["best_validation_loss"]),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ),
        "actor_checkpoint_selection_mismatch",
        str(actor_best["epoch"]),
    )

    confidence_fit = _mapping(
        training.get("confidence_fit"),
        "confidence fit",
    )
    confidence_history = tuple(
        _mapping(item, "confidence history row")
        for item in _sequence(
            confidence_fit.get("history"),
            "confidence history",
        )
    )
    targets = {
        split: (
            int(metrics["target_positive_count"]),
            int(metrics["target_negative_count"]),
        )
        for split, metrics in confidence_metrics.items()
    }

    def confidence_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
        rates: list[float] = []
        split_accepted: list[bool] = []
        false_positive_count = 0
        dual_class_splits = 0
        for split in ("train", "validation"):
            positive_count, negative_count = targets[split]
            positive_pass = int(
                item[f"{split}_positive_threshold_pass_count"]
            )
            negative_pass = int(
                item[f"{split}_negative_threshold_pass_count"]
            )
            inconsistent_pass = int(
                item[f"{split}_inconsistent_threshold_pass_count"]
            )
            executable_pass = int(
                item[f"{split}_executable_threshold_pass_count"]
            )
            positive_recall = positive_pass / positive_count
            specificity = (negative_count - negative_pass) / negative_count
            rates.extend((positive_recall, specificity))
            accepted = bool(
                positive_pass > 0
                and negative_pass == 0
                and inconsistent_pass == 0
                and executable_pass > 0
            )
            split_accepted.append(accepted)
            false_positive_count += negative_pass
            dual_class_splits += int(
                positive_pass > 0
                and negative_count - negative_pass > 0
            )
        return (
            int(all(split_accepted)),
            int(split_accepted[1]),
            dual_class_splits,
            min(rates),
            sum(rates) / len(rates),
            -false_positive_count,
            -float(
                item[
                    "validation_train_weighted_logit_margin_loss"
                ]
            ),
            -int(item["epoch"]),
        )

    _expect(
        confidence_history,
        "confidence_checkpoint_history_empty",
        "confidence history",
    )
    confidence_best = max(confidence_history, key=confidence_key)
    accepted = tuple(
        bool(confidence_key(item)[0]) for item in confidence_history
    )
    _expect(
        all(
            bool(item["fixed_gate_checkpoint_accepted"]) is is_accepted
            for item, is_accepted in zip(
                confidence_history,
                accepted,
                strict=True,
            )
        ),
        "confidence_checkpoint_acceptance_history_mismatch",
        "confidence history",
    )
    _expect(
        int(confidence_best["epoch"]) == int(confidence_fit["best_epoch"])
        and isclose(
            float(
                confidence_best[
                    "validation_train_weighted_logit_margin_loss"
                ]
            ),
            float(
                confidence_fit[
                    "best_validation_train_weighted_logit_margin_loss"
                ]
            ),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
        and sum(accepted)
        == int(confidence_fit["accepted_checkpoint_epoch_count"])
        and _longest_true_run(accepted)
        == int(
            confidence_fit[
                "longest_consecutive_accepted_checkpoint_epochs"
            ]
        ),
        "confidence_checkpoint_selection_mismatch",
        str(confidence_best["epoch"]),
    )
    return {
        "actor": {
            "history_epoch_count": len(actor_history),
            "selected_epoch": int(actor_best["epoch"]),
            "declared_epoch": int(training["best_epoch"]),
            "selection_recalculated": True,
            "dual_class_threshold_passed": bool(
                actor_best["dual_class_checkpoint_threshold_passed"]
            ),
            "validation_train_weighted_loss": float(
                actor_best["validation_train_weighted_loss"]
            ),
        },
        "confidence": {
            "history_epoch_count": len(confidence_history),
            "selected_epoch": int(confidence_best["epoch"]),
            "declared_epoch": int(confidence_fit["best_epoch"]),
            "selection_recalculated": True,
            "fixed_gate": D4_V4_FIXED_CONFIDENCE_GATE,
            "fixed_gate_checkpoint_accepted": bool(
                confidence_key(confidence_best)[0]
            ),
            "accepted_checkpoint_epoch_count": sum(accepted),
            "longest_consecutive_accepted_checkpoint_epochs": (
                _longest_true_run(accepted)
            ),
            "validation_train_weighted_logit_margin_loss": float(
                confidence_best[
                    "validation_train_weighted_logit_margin_loss"
                ]
            ),
        },
    }


def _audit_development_fixture(
    candidate: Path,
    *,
    declared: Any,
    build_config: Mapping[str, Any],
    expected_state_dict_sha256: str,
) -> dict[str, Any]:
    try:
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource import (
            DeterministicResourceProjector,
            RegionResourceProjectionConfig,
            RuleRegionResourcePolicy,
            RuleRegionResourcePolicyConfig,
        )
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_learning import (
            load_region_resource_model_bundle,
        )
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v4_shadow_candidate import (
            RegionResourceV4BuildConfig,
            _evaluate_development_fixture,
        )
    except (ImportError, OSError) as exc:
        _fail("d4_fixture_audit_dependency_unavailable", type(exc).__name__)

    projection_config = RegionResourceProjectionConfig(
        minimum_reserve_ratio=0.10,
        minimum_reserve_resources=1,
        advisory_ttl_s=1.5,
    )
    projector = DeterministicResourceProjector(projection_config)
    rule_policy = RuleRegionResourcePolicy(
        RuleRegionResourcePolicyConfig(
            projection=projection_config,
            high_threat_weight=2.0,
            uncertainty_weight=0.5,
            transfer_pressure_margin=0.05,
        ),
        projector=projector,
    )
    bundle = load_region_resource_model_bundle(
        candidate / "bundle",
        expected_model_version=D4_V4_MODEL_VERSION,
        expected_state_dict_sha256=expected_state_dict_sha256,
        map_location="cpu",
        require_training_dataset_manifest=True,
    )
    reproduced = _evaluate_development_fixture(
        bundle,
        config=RegionResourceV4BuildConfig(**dict(build_config)),
        projector=projector,
        rule_policy=rule_policy,
    )
    declared_mapping = _mapping(declared, "development fixture")
    _expect(
        reproduced == declared_mapping,
        "development_fixture_recalculation_mismatch",
        str(reproduced.get("effective_confidence")),
    )
    _expect(
        reproduced.get("training_domain_smoke_only") is True
        and reproduced.get(
            "independent_generalization_evidence_available"
        )
        is False
        and reproduced.get("formal_validation_claim_allowed") is False
        and reproduced.get("selection_split") == "train"
        and reproduced.get("selection_validation_payload_use_count") == 0
        and reproduced.get("selection_test_payload_use_count") == 0,
        "development_fixture_scope_boundary_mismatch",
        "fixture must remain TRAIN-domain smoke only",
    )
    effective_confidence = float(reproduced["effective_confidence"])
    margin = effective_confidence - D4_V4_FIXED_CONFIDENCE_GATE
    _expect(
        isclose(
            margin,
            float(reproduced["confidence_margin_above_threshold"]),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
        and margin > 0.0,
        "development_fixture_margin_mismatch",
        str(margin),
    )
    return {
        **reproduced,
        "recalculated_from_frozen_fixture_contract": True,
        "classification": "training_domain_smoke_only",
        "generalization_evidence": False,
        "formal_validation_evidence": False,
        "thin_margin_warning": True,
    }


def _audit_registry_boundary(
    inputs: D4V4CandidateAuditInputs,
    source_lineage: Mapping[str, Any],
) -> dict[str, Any]:
    v3_root = inputs.repository_root / D4_V3_REGISTRY_RELATIVE_ROOT
    _expect(v3_root.is_dir(), "v3_registry_root_unavailable", str(v3_root))
    if v3_root.is_symlink():
        _fail("v3_registry_root_symlink_forbidden", str(v3_root))
    v3_paths = sorted(v3_root.rglob("*"))
    _expect(
        not any(path.is_symlink() for path in v3_paths),
        "v3_registry_symlink_forbidden",
        str(v3_root),
    )
    inventory = {
        str(path.relative_to(v3_root)): _sha256_file(path)
        for path in v3_paths
        if path.is_file()
    }
    tree_sha = _canonical_sha256(inventory)
    _expect(
        tree_sha == inputs.expected_v3_registry_tree_sha256,
        "v3_registry_tree_sha256_mismatch",
        tree_sha,
    )
    v4_registry_root = inputs.repository_root / D4_V4_REGISTRY_RELATIVE_ROOT
    _expect(
        not v4_registry_root.exists(),
        "v4_candidate_registry_path_present",
        str(v4_registry_root),
    )
    try:
        inputs.candidate_root.relative_to(
            inputs.repository_root
            / "research_modules/d4_distributed_fallback/model_registry"
        )
    except ValueError:
        candidate_outside_registry = True
    else:
        candidate_outside_registry = False
    _expect(
        candidate_outside_registry,
        "v4_candidate_located_in_registry",
        str(inputs.candidate_root),
    )
    constants = _mapping(
        source_lineage.get("registration_constants"),
        "registration constants",
    )
    _expect(
        set(constants) == set(_V4_REGISTRATION_CONSTANTS)
        and all(value is None for value in constants.values()),
        "v4_registration_constant_not_closed",
        str(constants),
    )
    return {
        "passed": True,
        "v3_registry_root": str(v3_root),
        "v3_registry_file_count": len(inventory),
        "v3_registry_artifact_sha256": inventory,
        "v3_registry_tree_sha256": tree_sha,
        "v3_registry_tree_unchanged": True,
        "v4_registry_path": str(v4_registry_root),
        "v4_registry_path_present": False,
        "candidate_outside_registry": True,
        "registration_constant_binding_count": 0,
        "unregistered": True,
    }


def _audit_permission_boundary(
    manifest: Mapping[str, Any],
    *,
    training: Mapping[str, Any],
    bundle_manifest: Mapping[str, Any],
    gate: Mapping[str, Any],
    fixture: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_permissions = _validate_closed_permissions(
        manifest.get("permissions"),
        "candidate permissions",
    )
    training_permissions = _validate_closed_permissions(
        training.get("permissions"),
        "training permissions",
    )
    _expect(
        manifest_permissions == training_permissions,
        "permission_declaration_cross_binding_mismatch",
        "candidate/training",
    )
    for payload_name, payload in (
        ("candidate", manifest),
        ("gate", gate),
    ):
        _expect(
            payload.get("development_only") is True
            and payload.get("shadow_only") is True
            and payload.get("admission_closed") is True
            and payload.get("rule_fallback_required") is True,
            "admission_boundary_mismatch",
            payload_name,
        )
    _expect(
        manifest.get("formal_holdout_evaluated") is False
        and manifest.get("runtime_preflight_completed") is False
        and training.get("formal_evaluation_authorized") is False
        and fixture.get("formal_validation_claim_allowed") is False,
        "formal_evaluation_boundary_mismatch",
        "formal holdout/preflight must be incomplete",
    )
    _expect(
        gate.get("schema") == D4_V4_GATE_SCHEMA
        and gate.get("fixed_minimum_confidence")
        == D4_V4_FIXED_CONFIDENCE_GATE
        and gate.get("fixed_ood_margin") == D4_V4_FIXED_OOD_MARGIN
        and gate.get("maximum_transfer_per_edge")
        == D4_V4_MAXIMUM_TRANSFER_PER_EDGE
        and gate.get("maximum_total_transfer_fraction")
        == D4_V4_MAXIMUM_TOTAL_TRANSFER_FRACTION
        and gate.get("require_binary_match_with_r0") is True
        and gate.get("require_source_r0_treatment_signatures") is True
        and gate.get("require_authority_identity_unchanged") is True
        and gate.get("require_quota_flow_conservation") is True,
        "intervention_gate_contract_mismatch",
        "intervention gate",
    )
    _expect(
        bundle_manifest.get("lifecycle_stage") == "development"
        and bundle_manifest.get("maximum_advisor_mode") == "shadow"
        and bundle_manifest.get("final_holdout_seed_count") == 0
        and bundle_manifest.get("reward_evidence_available") is False
        and bundle_manifest.get("strategy_capability_claim_allowed")
        is False
        and bundle_manifest.get("runtime_confidence_gate") is None
        and frozenset(bundle_manifest.get("admission_reasons", ()))
        == _EXPECTED_ADMISSION_REASONS,
        "bundle_admission_boundary_mismatch",
        "bundle manifest",
    )
    _expect(
        registry.get("unregistered") is True,
        "candidate_registration_boundary_mismatch",
        "registry",
    )
    return {
        "all_logical_permissions_false": True,
        "permissions": manifest_permissions,
        "unregistered": True,
        "admission_closed": True,
        "development_only": True,
        "shadow_only": True,
        "rule_fallback_required": True,
        "formal_holdout_evaluated": False,
        "formal_holdout_seed_count": 0,
        "runtime_preflight_completed": False,
        "runtime_confidence_gate_registered": False,
        "production_permission_available": False,
        "formal_validation_claim_allowed": False,
    }


def _audit_zero_use_claims(
    *,
    cross_bindings: Mapping[str, Any],
    model_evidence: Mapping[str, Any],
    fixture: Mapping[str, Any],
) -> dict[str, Any]:
    payloads = _mapping(cross_bindings.get("payloads"), "cross-binding payloads")
    training = _mapping(payloads["training_summary"], "training summary")
    source = _mapping(payloads["source_summary"], "source summary")
    derivation = _mapping(payloads["source_derivation"], "source derivation")
    export = _mapping(payloads["export_summary"], "export summary")
    generation = _mapping(derivation.get("generation"), "derivation generation")
    governance = _mapping(derivation.get("governance"), "derivation governance")
    confidence_fit = _mapping(training.get("confidence_fit"), "confidence fit")
    actor_balance = _mapping(training.get("class_balance"), "actor balance")
    confidence_balance = _mapping(
        confidence_fit.get("class_balance"),
        "confidence balance",
    )
    episode_binding = _mapping(
        cross_bindings.get("episode_binding"),
        "episode binding",
    )

    zero_claims = {
        "training_test_payload_fit_count": training.get(
            "test_payload_fit_count"
        ),
        "training_test_payload_weight_fit_count": training.get(
            "test_payload_weight_fit_count"
        ),
        "actor_test_payload_weight_fit_count": actor_balance.get(
            "test_payload_weight_fit_count"
        ),
        "confidence_test_payload_fit_count": confidence_fit.get(
            "test_payload_fit_count"
        ),
        "confidence_test_payload_weight_fit_count": confidence_balance.get(
            "test_payload_weight_fit_count"
        ),
        "builder_test_payload_read_count": _mapping(
            training.get("external_dataset_governance"),
            "training external governance",
        ).get("test_payload_read_count"),
        "derivation_test_payload_read_count": governance.get(
            "test_payload_read_count"
        ),
        "audit_test_payload_read_count": episode_binding.get(
            "audit_test_payload_read_count"
        ),
        "training_truth_identifier_use_count": training.get(
            "truth_identifier_use_count"
        ),
        "source_truth_identifier_use_count": source.get(
            "truth_identifier_use_count"
        ),
        "confidence_truth_identifier_use_count": confidence_fit.get(
            "truth_identifier_use_count"
        ),
        "derivation_truth_identifier_use_count": generation.get(
            "truth_identifier_use_count"
        ),
        "training_future_outcome_use_count": training.get(
            "future_outcome_use_count"
        ),
        "source_future_outcome_use_count": source.get(
            "future_outcome_use_count"
        ),
        "confidence_future_outcome_use_count": confidence_fit.get(
            "future_outcome_use_count"
        ),
        "derivation_future_outcome_use_count": generation.get(
            "future_outcome_use_count"
        ),
        "formal_holdout_seed_use_count": training.get(
            "formal_holdout_seed_use_count"
        ),
        "fixture_truth_identifier_use_count": fixture.get(
            "truth_identifier_use_count"
        ),
    }
    _expect(
        all(type(value) is int and value == 0 for value in zero_claims.values()),
        "zero_use_claim_mismatch",
        str(zero_claims),
    )
    _expect(
        export.get("test_payload_read_by_v4_builder") is False
        and export.get("truth_identifier_use_count") == 0
        and _mapping(
            generation.get("observable_label_audit"),
            "observable label audit",
        ).get("test_label_used_for_model_fit")
        is False
        and _mapping(
            generation.get("observable_label_audit"),
            "observable label audit",
        ).get("validation_or_test_label_used_for_weight_fit")
        is False,
        "external_zero_use_boolean_claim_mismatch",
        "export/observable label audit",
    )
    split_counts = _mapping(
        episode_binding.get("split_counts"),
        "selected split counts",
    )
    return {
        "selected_payload_splits": ["train", "validation"],
        "train": {
            **_mapping(split_counts["train"], "train split counts"),
            "target_positive_count": model_evidence["actor"]["train"][
                "target_positive_count"
            ],
            "target_negative_count": model_evidence["actor"]["train"][
                "target_negative_count"
            ],
            "confidence_positive_count": model_evidence["confidence"][
                "train"
            ]["target_positive_count"],
            "confidence_negative_count": model_evidence["confidence"][
                "train"
            ]["target_negative_count"],
        },
        "validation": {
            **_mapping(
                split_counts["validation"],
                "validation split counts",
            ),
            "target_positive_count": model_evidence["actor"][
                "validation"
            ]["target_positive_count"],
            "target_negative_count": model_evidence["actor"][
                "validation"
            ]["target_negative_count"],
            "confidence_positive_count": model_evidence["confidence"][
                "validation"
            ]["target_positive_count"],
            "confidence_negative_count": model_evidence["confidence"][
                "validation"
            ]["target_negative_count"],
        },
        "test": {
            "manifest_seed_count": episode_binding[
                "test_manifest_seed_count"
            ],
            "manifest_episode_count": episode_binding[
                "test_manifest_episode_count"
            ],
            "manifest_frame_count": episode_binding[
                "test_manifest_frame_count"
            ],
            "candidate_payload_file_count": 0,
            "builder_payload_read_count": 0,
            "audit_payload_read_count": 0,
            "fit_count": 0,
            "weight_fit_count": 0,
        },
        "truth_identifier_use_count": 0,
        "future_outcome_available_count": 0,
        "future_outcome_use_count": 0,
        "reward_available_count": 0,
        "zero_use_claims": zero_claims,
    }


def _executable_signature(advisory: Any) -> str:
    payload = {
        "regions": [
            {
                "region_id": region.region_id,
                "resource_quota_delta": int(region.resource_quota_delta),
                "reserve_resources": int(
                    ceil(
                        float(region.reserve_ratio)
                        * int(region.resources_after)
                    )
                ),
                "hold": bool(region.hold),
                "request_replan": bool(region.request_replan),
            }
            for region in sorted(
                advisory.regions,
                key=lambda item: item.region_id,
            )
        ],
        "transfer_allowances": [
            {
                "source_region_id": transfer.source_region_id,
                "target_region_id": transfer.target_region_id,
                "resource_count": int(transfer.resource_count),
                "edge_id": transfer.edge_id,
            }
            for transfer in sorted(
                advisory.transfers,
                key=lambda item: (
                    item.source_region_id,
                    item.target_region_id,
                    item.edge_id,
                ),
            )
        ],
    }
    return _canonical_sha256(payload)


def _source_executable_signature(snapshot: Any) -> str:
    return _canonical_sha256(
        {
            "regions": [
                {
                    "region_id": node.region_id,
                    "resource_quota_delta": 0,
                    "reserve_resources": int(node.reserve_resources),
                    "hold": False,
                    "request_replan": False,
                }
                for node in sorted(
                    snapshot.regions,
                    key=lambda item: item.region_id,
                )
            ],
            "transfer_allowances": [],
        }
    )


def _intervention_reasons(
    snapshot: Any,
    candidate: Any,
    r0: Any,
    *,
    projector: Any,
) -> tuple[str, ...]:
    reasons: list[str] = []
    nodes = snapshot.region_by_id
    candidate_actions = {
        action.region_id: action for action in candidate.actions
    }
    r0_actions = {action.region_id: action for action in r0.actions}
    if set(candidate_actions) != set(nodes) or set(r0_actions) != set(nodes):
        reasons.append("candidate_region_set_mismatch")
    else:
        for region_id in sorted(nodes):
            node = nodes[region_id]
            action = candidate_actions[region_id]
            if (
                action.expected_owner_id != node.current_owner_id
                or action.expected_owner_layer != node.current_owner_layer
                or action.expected_plan_id != node.plan_id
                or action.expected_plan_version != node.plan_version
                or action.expected_epoch != node.epoch
                or action.expected_lease_expires_at_s
                != node.lease_expires_at_s
            ):
                reasons.append(
                    f"region:{region_id}:authority_identity_changed"
                )
            if (
                action.hold != r0_actions[region_id].hold
                or action.request_replan
                != r0_actions[region_id].request_replan
            ):
                reasons.append(
                    f"region:{region_id}:binary_action_differs_from_r0"
                )
    reasons.extend(candidate.projection_rejections)
    edge_by_id = {edge.edge_id: edge for edge in snapshot.edges}
    net_flow = {region_id: 0 for region_id in nodes}
    total_transfer = 0
    for transfer in candidate.transfers:
        edge = edge_by_id.get(transfer.edge_id)
        if edge is None or not edge.permits(
            transfer.source_region_id,
            transfer.target_region_id,
        ):
            reasons.append(
                f"transfer:{transfer.edge_id}:edge_identity_invalid"
            )
            continue
        if (
            int(transfer.resource_count)
            > D4_V4_MAXIMUM_TRANSFER_PER_EDGE
        ):
            reasons.append(
                f"transfer:{transfer.edge_id}:per_edge_limit_exceeded"
            )
        total_transfer += int(transfer.resource_count)
        net_flow[transfer.source_region_id] -= int(
            transfer.resource_count
        )
        net_flow[transfer.target_region_id] += int(
            transfer.resource_count
        )
    maximum_total = max(
        1,
        int(
            ceil(
                D4_V4_MAXIMUM_TOTAL_TRANSFER_FRACTION
                * snapshot.total_resources
            )
        ),
    )
    if total_transfer > maximum_total:
        reasons.append("candidate_total_transfer_limit_exceeded")
    if not candidate.transfers:
        reasons.append("candidate_transfer_missing")
    if candidate.total_quota_delta != 0 or sum(net_flow.values()) != 0:
        reasons.append("candidate_total_quota_not_conserved")
    if set(candidate_actions) == set(nodes):
        for region_id in sorted(nodes):
            if (
                candidate_actions[region_id].resource_quota_delta
                != net_flow[region_id]
            ):
                reasons.append(
                    f"region:{region_id}:quota_transfer_flow_mismatch"
                )
    candidate_signature = _executable_signature(
        projector.build_advisory_contract(snapshot, candidate)
    )
    r0_signature = _executable_signature(
        projector.build_advisory_contract(snapshot, r0)
    )
    source_signature = _source_executable_signature(snapshot)
    if candidate_signature == source_signature:
        reasons.append("candidate_signature_matches_source")
    if candidate_signature == r0_signature:
        reasons.append("candidate_signature_matches_r0")
    return tuple(dict.fromkeys(reasons))


def write_d4_v4_candidate_audit_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Atomically write JSON, Chinese Markdown, and output checksums."""

    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"D4 v4 D6 audit output exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir()
    try:
        json_path = temporary / "d4_v4_candidate_independent_audit.json"
        markdown_path = temporary / "D4_V4_CANDIDATE_INDEPENDENT_AUDIT_CN.md"
        checksum_path = temporary / "SHA256SUMS"
        json_path.write_text(
            json.dumps(
                result,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(
            render_d4_v4_candidate_audit_markdown(result),
            encoding="utf-8",
        )
        checksum_path.write_text(
            "".join(
                f"{_sha256_file(path)}  {path.name}\n"
                for path in (markdown_path, json_path)
            ),
            encoding="utf-8",
        )
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "json": output / json_path.name,
        "markdown": output / markdown_path.name,
        "sha256sums": output / checksum_path.name,
    }


def render_d4_v4_candidate_audit_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the independent audit as a concise Chinese report."""

    anchors = _mapping(result["anchors"], "anchors")
    tree = _mapping(result["candidate_tree"], "candidate tree")
    source = _mapping(result["source_lineage"], "source lineage")
    binding = _mapping(
        result["external_dataset_binding"],
        "external dataset binding",
    )
    governance = _mapping(
        result["dataset_and_use_governance"],
        "dataset governance",
    )
    actor = _mapping(result["actor_recalculation"], "actor")
    confidence = _mapping(
        result["confidence_recalculation"],
        "confidence",
    )
    checkpoints = _mapping(
        result["checkpoint_recalculation"],
        "checkpoints",
    )
    fixture = _mapping(result["development_fixture"], "fixture")
    registry = _mapping(result["v3_registry"], "registry")
    permissions = _mapping(
        result["permission_and_admission_boundary"],
        "permissions",
    )
    admission_blockers = tuple(
        str(code)
        for code in _sequence(
            result["admission_blocker_codes"],
            "admission blocker codes",
        )
    )
    train_actor = _mapping(actor["train"], "train actor")
    validation_actor = _mapping(actor["validation"], "validation actor")
    train_confidence = _mapping(confidence["train"], "train confidence")
    validation_confidence = _mapping(
        confidence["validation"],
        "validation confidence",
    )
    lines = [
        "# D4 v4 未注册候选独立审计",
        "",
        "## 结论",
        "",
        (
            "D6 独立、只读审计通过候选完整性和 development 指标重算。"
            "该结论仅适用于 train/validation 开发证据；候选保持未注册、"
            "admission closed、rule fallback required，正式 holdout 与 runtime "
            "preflight 均未完成。"
        ),
        (
            "固定 0.60 门在已读 train/validation 上没有负类越门，但正类召回和"
            "置信度裕量偏薄，不能解释为泛化、正式验证、收益或运行准入证据。"
        ),
        "",
        "## 冻结身份与文件树",
        "",
        f"- manifest content SHA-256：`{anchors['manifest_content_sha256']}`",
        f"- manifest file SHA-256：`{anchors['manifest_file_sha256']}`",
        f"- model state SHA-256：`{anchors['model_state_sha256']}`",
        f"- dataset SHA-256：`{anchors['dataset_sha256']}`",
        f"- split SHA-256：`{anchors['dataset_split_sha256']}`",
        f"- clean source commit：`{anchors['source_git_commit']}`",
        (
            f"- 候选树：{tree['file_count']} 个文件，"
            f"{tree['artifact_file_count']} 个 manifest artifact，"
            f"{tree['directory_count']} 个目录；逐文件 SHA-256 全部一致，"
            "无 symlink 或特殊文件。"
        ),
        (
            f"- source implementation：{source['implementation_file_count']} "
            "个文件与 commit blob 逐字节一致。"
        ),
        "",
        "## 外部数据与用途",
        "",
        (
            f"- 外部 evidence content SHA-256："
            f"`{binding['external_evidence_content_sha256']}`"
        ),
        (
            f"- source derivation file SHA-256："
            f"`{binding['source_derivation_file_sha256']}`"
        ),
        (
            f"- train：{governance['train']['seed_count']} seeds / "
            f"{governance['train']['episode_count']} episodes / "
            f"{governance['train']['frame_count']} samples；目标正/负 "
            f"{governance['train']['target_positive_count']}/"
            f"{governance['train']['target_negative_count']}，confidence "
            f"正/负 {governance['train']['confidence_positive_count']}/"
            f"{governance['train']['confidence_negative_count']}。"
        ),
        (
            f"- validation：{governance['validation']['seed_count']} seeds / "
            f"{governance['validation']['episode_count']} episodes / "
            f"{governance['validation']['frame_count']} samples；目标正/负 "
            f"{governance['validation']['target_positive_count']}/"
            f"{governance['validation']['target_negative_count']}，confidence "
            f"正/负 {governance['validation']['confidence_positive_count']}/"
            f"{governance['validation']['confidence_negative_count']}。"
        ),
        (
            f"- test 仅解析 manifest 元数据：{governance['test']['manifest_seed_count']} "
            f"seeds / {governance['test']['manifest_episode_count']} episodes / "
            f"{governance['test']['manifest_frame_count']} frames；候选 payload、"
            "builder read、D6 payload read、fit、weight fit 均为 0。"
        ),
        "- truth identifier use、future outcome available/use、reward available 均为 0。",
        "",
        "## Actor 与权重",
        "",
        (
            f"- actor checkpoint：独立复算 epoch "
            f"{checkpoints['actor']['selected_epoch']}，与声明一致；"
            f"history 共 {checkpoints['actor']['history_epoch_count']} epochs。"
        ),
        (
            f"- train 正/负召回：{train_actor['positive_recall']:.6f} / "
            f"{train_actor['negative_recall']:.6f}；validation 正/负召回："
            f"{validation_actor['positive_recall']:.6f} / "
            f"{validation_actor['negative_recall']:.6f}。"
        ),
        (
            "- actor 与 confidence 权重均只由 TRAIN 推导；validation/test "
            "weight fit 为 0。具体权重和库存见机器可读 JSON。"
        ),
        "",
        "## 固定 0.60 门",
        "",
        "| split | 正类召回 | 负类特异度 | Brier | 越门最小裕量 | 最大负类裕量 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| train | {train_confidence['positive_recall']:.6f} | "
            f"{train_confidence['negative_specificity']:.6f} | "
            f"{train_confidence['brier_score']:.9f} | "
            f"{train_confidence['thin_margin']['minimum_passing_margin']:.9f} | "
            f"{train_confidence['thin_margin']['maximum_negative_margin']:.9f} |"
        ),
        (
            f"| validation | {validation_confidence['positive_recall']:.6f} | "
            f"{validation_confidence['negative_specificity']:.6f} | "
            f"{validation_confidence['brier_score']:.9f} | "
            f"{validation_confidence['thin_margin']['minimum_passing_margin']:.9f} | "
            f"{validation_confidence['thin_margin']['maximum_negative_margin']:.9f} |"
        ),
        "",
        (
            f"confidence checkpoint 独立复算 epoch "
            f"{checkpoints['confidence']['selected_epoch']}，固定门接受 epoch "
            f"{checkpoints['confidence']['accepted_checkpoint_epoch_count']} 个，"
            f"最长连续 {checkpoints['confidence']['longest_consecutive_accepted_checkpoint_epochs']} "
            "个。"
        ),
        "",
        "## Fixture、Registry 与权限",
        "",
        (
            f"- development fixture 有效置信度 "
            f"{fixture['effective_confidence']:.9f}，高于 0.60 的裕量仅 "
            f"{fixture['confidence_margin_above_threshold']:.9f}；其分类固定为 "
            "`training_domain_smoke_only`，不是泛化或正式验证。"
        ),
        (
            f"- v3 registry 共 {registry['v3_registry_file_count']} 个文件，树摘要 "
            f"`{registry['v3_registry_tree_sha256']}`，与冻结值一致。"
        ),
        (
            "- v4 注册常量全部为 null，registry 目标路径不存在；候选未注册。"
        ),
        (
            "- 逻辑权限全部为 false，核验通过；"
            "formal holdout/preflight 均未完成，生产权限不可用。"
        ),
        "",
        "## 准入阻断项",
        "",
        *(f"- `{code}`" for code in admission_blockers),
        "",
        "## 失败关闭负例",
        "",
        (
            "- 普通候选 artifact 的字节篡改由逐 artifact SHA-256 门拒绝，"
            "错误码为 `candidate_artifact_sha256_mismatch`。"
        ),
        (
            "- 权限声明篡改后，即使同步重算候选自有 manifest content hash，"
            "仍由 D6 固定外部锚拒绝，错误码为 "
            "`candidate_manifest_content_anchor_mismatch`。"
        ),
        (
            "- 两类合同均由 `tests/test_d4_v4_candidate_audit.py` 的临时副本"
            "负例覆盖；原候选和外部 evidence 保持只读。"
        ),
        "",
        "## 审计边界",
        "",
        "- 本次未运行正式 holdout，未执行 runtime preflight，未登记候选。",
        "- 本次未授予或建议开放 assist、authority、assignment、takeover、coalition、control 或其他生产权限。",
        "- JSON 中保留候选逐文件 SHA-256、v3 registry 逐文件 SHA-256、权重库存、checkpoint 和全部重算指标。",
        "",
    ]
    return "\n".join(lines)


def _validate_closed_permissions(value: Any, context: str) -> dict[str, Any]:
    permissions = _mapping(value, context)
    expected = set(_PERMISSION_FIELDS) | {"schema"}
    _require_exact_keys(permissions, expected, context)
    _expect(
        permissions.get("schema") == D4_V4_PERMISSION_SCHEMA,
        "permission_schema_mismatch",
        context,
    )
    for name in _PERMISSION_FIELDS:
        _expect(
            type(permissions.get(name)) is bool
            and permissions.get(name) is False,
            "permission_not_false",
            f"{context}:{name}",
        )
    return dict(permissions)


def _verify_dataset_manifest_content(manifest: Mapping[str, Any]) -> str:
    content = dict(manifest)
    declared = _normalise_sha256(
        content.pop("dataset_sha256", None),
        "dataset manifest dataset_sha256",
    )
    dataset_id = content.pop("dataset_id", None)
    actual = _canonical_sha256(content)
    _expect(
        actual == declared
        and dataset_id == f"d4-region-learning-dataset-{declared}",
        "dataset_manifest_content_sha256_mismatch",
        actual,
    )
    return actual


def _verify_split_content(split: Any) -> str:
    payload = _mapping(split, "dataset split")
    actual = _canonical_sha256(
        {
            "algorithm": payload.get("algorithm"),
            "split_seed": int(payload["split_seed"]),
            "train": sorted(int(value) for value in payload["train_seeds"]),
            "validation": sorted(
                int(value) for value in payload["validation_seeds"]
            ),
            "test": sorted(int(value) for value in payload["test_seeds"]),
        }
    )
    _expect(
        actual == payload.get("split_sha256"),
        "dataset_split_content_sha256_mismatch",
        actual,
    )
    return actual


def _verify_content_sha(
    payload: Mapping[str, Any],
    *,
    content_field: str,
    code: str,
) -> str:
    content = dict(payload)
    declared = _normalise_sha256(
        content.pop(content_field, None),
        content_field,
    )
    actual = _canonical_sha256(content)
    _expect(actual == declared, code, actual)
    return actual


def _extract_none_constants(
    source: bytes,
    names: Iterable[str],
) -> dict[str, None]:
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        _fail("source_ast_invalid", type(exc).__name__)
    expected = set(names)
    observed: dict[str, None] = {}
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        name = node.target.id
        if name not in expected:
            continue
        if not isinstance(node.value, ast.Constant) or node.value.value is not None:
            _fail("v4_registration_constant_not_none", name)
        observed[name] = None
    _expect(
        set(observed) == expected,
        "v4_registration_constant_inventory_mismatch",
        _set_difference_detail(expected, set(observed)),
    )
    return observed


def _count_forbidden_dataset_keys(value: Any) -> int:
    if isinstance(value, Mapping):
        count = 0
        for key, item in value.items():
            normalized = str(key).strip().lower()
            count += int(
                normalized in _FORBIDDEN_DATASET_KEYS
                or normalized.startswith("truth_")
                or normalized.endswith("_truth_id")
                or normalized.endswith("_global_track_id")
                or normalized.endswith("_target_id")
                or normalized.endswith("_object_id")
                or normalized.endswith("_actor_name")
                or "evaluator_truth" in normalized
                or "offline_truth" in normalized
            )
            count += _count_forbidden_dataset_keys(item)
        return count
    if isinstance(value, (list, tuple)):
        return sum(_count_forbidden_dataset_keys(item) for item in value)
    return 0


def _git_output(
    repository_root: Path,
    arguments: Sequence[str],
) -> bytes:
    try:
        return subprocess.run(
            ("git", "-C", str(repository_root), *arguments),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        _fail(
            "git_evidence_unavailable",
            f"{' '.join(arguments)}:{type(exc).__name__}",
        )


def _longest_true_run(values: Sequence[bool]) -> int:
    longest = 0
    current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def _expect_equal_number_or_bool(
    declared: Any,
    calculated: Any,
    code: str,
    detail: str,
) -> None:
    if type(calculated) is bool:
        _expect(type(declared) is bool and declared is calculated, code, detail)
        return
    if type(calculated) is int:
        _expect(type(declared) is int and declared == calculated, code, detail)
        return
    _expect(
        type(declared) in {int, float}
        and isclose(
            float(declared),
            float(calculated),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ),
        code,
        detail,
    )


def _resolve_input_path(repository_root: Path, value: Path) -> Path:
    path = Path(value).expanduser()
    return (repository_root / path).resolve() if not path.is_absolute() else path.resolve()


def _safe_relative_file(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or str(path) != value
    ):
        _fail("relative_artifact_path_invalid", value)
    return value


def _parent_directories(files: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for relative in files:
        parent = PurePosixPath(relative).parent
        while str(parent) != ".":
            result.add(str(parent))
            parent = parent.parent
    return result


def _set_difference_detail(
    expected: set[str],
    observed: set[str],
) -> str:
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    return f"missing={missing},extra={extra}"


def _load_json(path: Path, context: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("json_artifact_invalid", f"{context}:{path}:{type(exc).__name__}")
    if not isinstance(payload, Mapping):
        _fail("json_object_required", context)
    return dict(payload)


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", context)
    return value


def _sequence(value: Any, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        _fail("sequence_required", context)
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: Iterable[str],
    context: str,
) -> None:
    expected_set = set(expected)
    if set(value) != expected_set:
        _fail(
            "field_inventory_mismatch",
            f"{context}:{_set_difference_detail(expected_set, set(value))}",
        )


def _normalise_sha256(value: Any, context: str) -> str:
    digest = str(value).lower()
    if len(digest) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in digest
    ):
        _fail("sha256_invalid", context)
    return digest


def _canonical_sha256(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        _fail("artifact_unavailable", f"{path}:{type(exc).__name__}")


def _expect(condition: bool, code: str, detail: str) -> None:
    if not condition:
        _fail(code, detail)


def _fail(code: str, detail: str) -> None:
    raise D4V4CandidateAuditError(code, detail)
