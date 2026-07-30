"""Independent, read-only audit for the unregistered D4 v5 candidate.

The caller-owned input specification is the trust root. Candidate manifests
and summaries are treated as claims: their hashes, bindings, metrics, and
permissions are independently checked. Only TRAIN and VALIDATION payloads are
loaded semantically. TEST and formal-holdout payloads are never evaluated or
fit.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from hashlib import sha256
import json
from math import ceil, isclose, isfinite, sqrt
from pathlib import Path, PurePosixPath
import shutil
import sys
from typing import Any, Iterable, Mapping, Sequence
import uuid


D4_V5_AUDIT_SCHEMA_VERSION = "d6.d4-v5-confidence-candidate-audit.v1"
D4_V5_INPUT_SCHEMA_VERSION = (
    "d6.d4-v5-confidence-candidate-audit-input.v1"
)
D4_V5_AUDIT_PROFILE_VERSION = (
    "d6.d4-v5-memory-bias-and-generalization-audit.v1"
)

D4_V5_CANDIDATE_ID = "region_resource_a2_confidence_knn_shadow_v5"
D4_V5_MODEL_VERSION = "d4-region-resource-v4-actor-knn-confidence-v5"
D4_V5_MANIFEST_FILE = "v5_confidence_candidate_manifest.json"
D4_V5_STATE_FILE = "calibration_state.json"
D4_V5_SUMMARY_FILE = "calibration_summary.json"
D4_V5_GATE_FILE = "development_gate.json"
D4_V5_MANIFEST_SCHEMA = "d4-region-resource-confidence-shadow-candidate-v5"
D4_V5_STATE_SCHEMA = "d4-region-resource-confidence-knn-state-v5"
D4_V5_SUMMARY_SCHEMA = (
    "d4-region-resource-confidence-calibration-summary-v5"
)
D4_V5_GATE_SCHEMA = "d4-region-resource-confidence-development-gate-v5"
D4_V5_PERMISSION_SCHEMA = (
    "d4-region-resource-confidence-shadow-permissions-v5"
)
D4_V5_CANDIDATE_CLASSIFICATION = "memorization_development_control"

D4_V4_CANDIDATE_ID = "region_resource_a2_executable_transfer_shadow_v4"
D4_V4_MODEL_VERSION = "d4-region-resource-graph-bc-executable-transfer-v4"
D4_V4_MANIFEST_FILE = "v4_shadow_candidate_manifest.json"
D4_V4_MANIFEST_SCHEMA = "d4-region-resource-executable-shadow-candidate-v4"

D4_V5_FIXED_GATE = 0.60
D4_V5_NEIGHBOUR_COUNT = 11
D4_V5_EXACT_EPSILON = 1.0e-12
D4_V5_SCALE_EPSILON = 1.0e-12
D4_V5_MINIMUM_RECALL = 0.80
D4_V5_REQUIRED_SPECIFICITY = 1.0
D4_V5_MINIMUM_MARGIN = 0.02
D4_GRAPH_ARCHITECTURE = "shared-region-graph-actor-critic-v1"

D4_V3_REGISTRY_RELATIVE_ROOT = (
    "research_modules/d4_distributed_fallback/model_registry/"
    "region_resource_a2_8region_runtime_action_readiness_shadow_v3"
)
D4_V4_REGISTRY_RELATIVE_ROOT = (
    "research_modules/d4_distributed_fallback/model_registry/"
    f"{D4_V4_CANDIDATE_ID}"
)
D4_V5_REGISTRY_RELATIVE_ROOT = (
    "research_modules/d4_distributed_fallback/model_registry/"
    f"{D4_V5_CANDIDATE_ID}"
)
D4_V4_SOURCE_RELATIVE_PATH = (
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_v4_shadow_candidate.py"
)
D4_V5_SOURCE_RELATIVE_PATH = (
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_v5_confidence_candidate.py"
)

_CANDIDATE_FILES = frozenset(
    {
        D4_V5_MANIFEST_FILE,
        D4_V5_STATE_FILE,
        D4_V5_SUMMARY_FILE,
        D4_V5_GATE_FILE,
    }
)
_PERMISSION_FIELDS = (
    "actual_adoption_claimed",
    "assignment_enabled",
    "assist_enabled",
    "authority_enabled",
    "benefit_claimed",
    "coalition_commit_enabled",
    "control_enabled",
    "d3_permission_available",
    "d7_permission_available",
    "formal_evaluation_authorized",
    "physical_permission_available",
    "production_runtime_ack_enabled",
    "takeover_enabled",
)
_V4_REGISTRATION_CONSTANTS = (
    "REGION_RESOURCE_V4_REGISTERED_MANIFEST_FILE_SHA256",
    "REGION_RESOURCE_V4_REGISTERED_MANIFEST_CONTENT_SHA256",
    "REGION_RESOURCE_V4_REGISTERED_MODEL_STATE_SHA256",
    "REGION_RESOURCE_V4_REGISTERED_BUNDLE_MANIFEST_SHA256",
    "REGION_RESOURCE_V4_REGISTERED_DATASET_SHA256",
)
_V5_REGISTRATION_CONSTANTS = (
    "REGION_RESOURCE_V5_REGISTERED_MANIFEST_FILE_SHA256",
    "REGION_RESOURCE_V5_REGISTERED_MANIFEST_CONTENT_SHA256",
    "REGION_RESOURCE_V5_REGISTERED_STATE_SHA256",
)
_EXPECTED_OVERLAP_KEYS = frozenset(
    {
        "validation_record_count",
        "exact_raw_graph_key_overlap_count",
        "exact_latent_overlap_count",
        "nonexact_lt_1e_3_count",
        "ge_1e_3_lt_1e_1_count",
        "ge_1e_1_count",
        "nearest_train_label_match_count",
        "positive_exact_raw_graph_key_overlap_count",
        "positive_exact_latent_overlap_count",
    }
)
_SHA256_LENGTH = 64


class D4V5CandidateAuditError(ValueError):
    """Stable fail-closed error for invalid v5 audit evidence."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class D4V5CandidateAuditInputs:
    """Caller-frozen anchors and policy for one v5 audit."""

    repository_root: Path
    candidate_root: Path
    base_v4_root: Path
    audit_id: str
    evaluated_at_utc: str
    expected_manifest_file_sha256: str
    expected_manifest_content_sha256: str
    expected_state_file_sha256: str
    expected_summary_file_sha256: str
    expected_gate_file_sha256: str
    expected_builder_source_sha256: str
    expected_base_v4_manifest_file_sha256: str
    expected_base_v4_manifest_content_sha256: str
    expected_base_v4_model_state_sha256: str
    expected_base_v4_dataset_sha256: str
    expected_base_v4_split_sha256: str
    expected_base_v4_tree_sha256: str
    expected_v3_registry_tree_sha256: str
    expected_v4_source_files: Mapping[str, str]
    expected_validation_diagnostics: Mapping[str, int]
    documented_latent_dimension: int
    minimum_subgroup_denominator: int
    profile_version: str = D4_V5_AUDIT_PROFILE_VERSION
    schema_version: str = D4_V5_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        repository = Path(self.repository_root).expanduser().resolve()
        candidate = _resolve_path(repository, self.candidate_root)
        base_v4 = _resolve_path(repository, self.base_v4_root)
        if not repository.is_dir():
            _fail("repository_root_unavailable", str(repository))
        if not candidate.is_dir():
            _fail("candidate_root_unavailable", str(candidate))
        if not base_v4.is_dir():
            _fail("base_v4_root_unavailable", str(base_v4))
        object.__setattr__(self, "repository_root", repository)
        object.__setattr__(self, "candidate_root", candidate)
        object.__setattr__(self, "base_v4_root", base_v4)

        if self.schema_version != D4_V5_INPUT_SCHEMA_VERSION:
            _fail("input_schema_mismatch", self.schema_version)
        if self.profile_version != D4_V5_AUDIT_PROFILE_VERSION:
            _fail("input_profile_mismatch", self.profile_version)
        for name in ("audit_id", "evaluated_at_utc"):
            if not isinstance(getattr(self, name), str) or not getattr(
                self, name
            ).strip():
                _fail("input_string_invalid", name)
        for name in (
            "expected_manifest_file_sha256",
            "expected_manifest_content_sha256",
            "expected_state_file_sha256",
            "expected_summary_file_sha256",
            "expected_gate_file_sha256",
            "expected_builder_source_sha256",
            "expected_base_v4_manifest_file_sha256",
            "expected_base_v4_manifest_content_sha256",
            "expected_base_v4_model_state_sha256",
            "expected_base_v4_dataset_sha256",
            "expected_base_v4_split_sha256",
            "expected_base_v4_tree_sha256",
            "expected_v3_registry_tree_sha256",
        ):
            object.__setattr__(
                self,
                name,
                _normalise_sha256(getattr(self, name), name),
            )
        sources = {
            _safe_relative_file(str(relative)): _normalise_sha256(
                digest, f"v4 source {relative}"
            )
            for relative, digest in _mapping(
                self.expected_v4_source_files,
                "expected_v4_source_files",
            ).items()
        }
        if not sources:
            _fail("v4_source_anchor_inventory_empty", "expected_v4_source_files")
        object.__setattr__(self, "expected_v4_source_files", sources)
        diagnostic = _mapping(
            self.expected_validation_diagnostics,
            "expected_validation_diagnostics",
        )
        _require_exact_keys(
            diagnostic,
            _EXPECTED_OVERLAP_KEYS,
            "expected_validation_diagnostics",
        )
        expected_diagnostics: dict[str, int] = {}
        for name, value in diagnostic.items():
            if type(value) is not int or value < 0:
                _fail("expected_diagnostic_count_invalid", str(name))
            expected_diagnostics[str(name)] = int(value)
        object.__setattr__(
            self,
            "expected_validation_diagnostics",
            expected_diagnostics,
        )
        if (
            type(self.documented_latent_dimension) is not int
            or self.documented_latent_dimension <= 0
        ):
            _fail(
                "documented_latent_dimension_invalid",
                str(self.documented_latent_dimension),
            )
        if (
            type(self.minimum_subgroup_denominator) is not int
            or self.minimum_subgroup_denominator <= 0
        ):
            _fail(
                "minimum_subgroup_denominator_invalid",
                str(self.minimum_subgroup_denominator),
            )

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        repository_root: str | Path,
    ) -> "D4V5CandidateAuditInputs":
        expected = {
            "schema_version",
            "profile_version",
            "audit_id",
            "evaluated_at_utc",
            "candidate_root",
            "base_v4_root",
            "expected_manifest_file_sha256",
            "expected_manifest_content_sha256",
            "expected_state_file_sha256",
            "expected_summary_file_sha256",
            "expected_gate_file_sha256",
            "expected_builder_source_sha256",
            "expected_base_v4_manifest_file_sha256",
            "expected_base_v4_manifest_content_sha256",
            "expected_base_v4_model_state_sha256",
            "expected_base_v4_dataset_sha256",
            "expected_base_v4_split_sha256",
            "expected_base_v4_tree_sha256",
            "expected_v3_registry_tree_sha256",
            "expected_v4_source_files",
            "expected_validation_diagnostics",
            "documented_latent_dimension",
            "minimum_subgroup_denominator",
        }
        _require_exact_keys(payload, expected, "audit input")
        return cls(
            repository_root=Path(repository_root),
            candidate_root=Path(str(payload["candidate_root"])),
            base_v4_root=Path(str(payload["base_v4_root"])),
            audit_id=str(payload["audit_id"]),
            evaluated_at_utc=str(payload["evaluated_at_utc"]),
            expected_manifest_file_sha256=str(
                payload["expected_manifest_file_sha256"]
            ),
            expected_manifest_content_sha256=str(
                payload["expected_manifest_content_sha256"]
            ),
            expected_state_file_sha256=str(
                payload["expected_state_file_sha256"]
            ),
            expected_summary_file_sha256=str(
                payload["expected_summary_file_sha256"]
            ),
            expected_gate_file_sha256=str(
                payload["expected_gate_file_sha256"]
            ),
            expected_builder_source_sha256=str(
                payload["expected_builder_source_sha256"]
            ),
            expected_base_v4_manifest_file_sha256=str(
                payload["expected_base_v4_manifest_file_sha256"]
            ),
            expected_base_v4_manifest_content_sha256=str(
                payload["expected_base_v4_manifest_content_sha256"]
            ),
            expected_base_v4_model_state_sha256=str(
                payload["expected_base_v4_model_state_sha256"]
            ),
            expected_base_v4_dataset_sha256=str(
                payload["expected_base_v4_dataset_sha256"]
            ),
            expected_base_v4_split_sha256=str(
                payload["expected_base_v4_split_sha256"]
            ),
            expected_base_v4_tree_sha256=str(
                payload["expected_base_v4_tree_sha256"]
            ),
            expected_v3_registry_tree_sha256=str(
                payload["expected_v3_registry_tree_sha256"]
            ),
            expected_v4_source_files=_mapping(
                payload["expected_v4_source_files"],
                "expected_v4_source_files",
            ),
            expected_validation_diagnostics=_mapping(
                payload["expected_validation_diagnostics"],
                "expected_validation_diagnostics",
            ),
            documented_latent_dimension=int(
                payload["documented_latent_dimension"]
            ),
            minimum_subgroup_denominator=int(
                payload["minimum_subgroup_denominator"]
            ),
            profile_version=str(payload["profile_version"]),
            schema_version=str(payload["schema_version"]),
        )


def load_d4_v5_candidate_audit_inputs(
    input_spec: str | Path,
    *,
    repository_root: str | Path,
) -> D4V5CandidateAuditInputs:
    """Load a fixed D6 v5 audit specification."""

    payload = _load_json(Path(input_spec), "v5 audit input")
    return D4V5CandidateAuditInputs.from_mapping(
        payload,
        repository_root=repository_root,
    )


def audit_d4_v5_confidence_candidate(
    inputs: D4V5CandidateAuditInputs,
) -> dict[str, Any]:
    """Run the independent audit without registration or formal evaluation."""

    candidate = inputs.candidate_root
    manifest_path = candidate / D4_V5_MANIFEST_FILE
    manifest_file_sha = _sha256_file(manifest_path)
    _expect(
        manifest_file_sha == inputs.expected_manifest_file_sha256,
        "candidate_manifest_file_external_anchor_mismatch",
        manifest_file_sha,
    )
    manifest = _load_json(manifest_path, "v5 manifest")
    _expect(
        manifest.get("schema") == D4_V5_MANIFEST_SCHEMA
        and manifest.get("candidate_id") == D4_V5_CANDIDATE_ID
        and manifest.get("model_version") == D4_V5_MODEL_VERSION,
        "candidate_identity_mismatch",
        (
            f"{manifest.get('schema')}:{manifest.get('candidate_id')}:"
            f"{manifest.get('model_version')}"
        ),
    )
    manifest_content_sha = _verify_content_sha(
        manifest,
        "candidate_manifest_content_sha256_mismatch",
    )
    _expect(
        manifest_content_sha == inputs.expected_manifest_content_sha256,
        "candidate_manifest_content_external_anchor_mismatch",
        manifest_content_sha,
    )

    candidate_tree = _audit_candidate_tree(inputs, manifest)
    state = _load_json(candidate / D4_V5_STATE_FILE, "v5 state")
    summary = _load_json(candidate / D4_V5_SUMMARY_FILE, "v5 summary")
    gate = _load_json(candidate / D4_V5_GATE_FILE, "v5 gate")
    content_bindings = _audit_content_bindings(manifest, state, summary, gate)
    base_binding = _audit_base_v4_and_v3_bindings(inputs, manifest)
    registry = _audit_registration_boundary(inputs)
    permissions = _audit_permissions_and_usage(
        manifest,
        state=state,
        summary=summary,
        gate=gate,
        registry=registry,
    )

    records = _load_train_validation_records(inputs)
    latent = _reconstruct_latent_and_state(records)
    state_comparison = _compare_reconstructed_state(state, latent)
    fixed_gate = _recalculate_fixed_development_gate(
        state=state,
        summary=summary,
        gate=gate,
        latent=latent,
    )
    memory_bias = _audit_memory_bias(
        inputs,
        latent=latent,
    )

    dimension_contract_passed = (
        latent["feature_dimension"] == inputs.documented_latent_dimension
    )
    strict_blockers = []
    if not dimension_contract_passed:
        strict_blockers.append("documented_latent_dimension_mismatch")
    strict_blockers.extend(
        (
            "validation_source_not_independent",
            "validation_exact_overlap_present",
            "validation_near_duplicate_overlap_present",
            "validation_nonoverlap_positive_denominator_insufficient",
            "formal_holdout_not_completed",
            "runtime_preflight_not_completed",
            "candidate_unregistered",
        )
    )

    result: dict[str, Any] = {
        "schema_version": D4_V5_AUDIT_SCHEMA_VERSION,
        "audit_id": inputs.audit_id,
        "evaluated_at_utc": inputs.evaluated_at_utc,
        "profile_version": inputs.profile_version,
        "status": (
            "completed_development_memorization_baseline_"
            "candidate_unregistered_admission_closed"
        ),
        "audit_execution_passed": True,
        "strict_profile_passed": False,
        "strict_profile_blocker_codes": strict_blockers,
        "anchors": {
            "candidate_manifest_file_sha256": manifest_file_sha,
            "candidate_manifest_content_sha256": manifest_content_sha,
            "calibration_state_file_sha256": (
                inputs.expected_state_file_sha256
            ),
            "calibration_summary_file_sha256": (
                inputs.expected_summary_file_sha256
            ),
            "development_gate_file_sha256": (
                inputs.expected_gate_file_sha256
            ),
            "builder_source_sha256": (
                inputs.expected_builder_source_sha256
            ),
            "base_v4_manifest_file_sha256": (
                inputs.expected_base_v4_manifest_file_sha256
            ),
            "base_v4_manifest_content_sha256": (
                inputs.expected_base_v4_manifest_content_sha256
            ),
            "base_v4_model_state_sha256": (
                inputs.expected_base_v4_model_state_sha256
            ),
            "base_v4_dataset_sha256": (
                inputs.expected_base_v4_dataset_sha256
            ),
            "base_v4_split_sha256": (
                inputs.expected_base_v4_split_sha256
            ),
            "base_v4_tree_sha256": inputs.expected_base_v4_tree_sha256,
            "v3_registry_tree_sha256": (
                inputs.expected_v3_registry_tree_sha256
            ),
        },
        "candidate_tree": candidate_tree,
        "content_bindings": content_bindings,
        "base_v4_and_v3_binding": base_binding,
        "registration_boundary": registry,
        "data_usage_and_permissions": permissions,
        "latent_reconstruction": {
            "reconstructed_from_frozen_v4_actor_and_payloads": True,
            "feature_source": (
                "frozen_v4_actor_pooled_message_passing_latent"
            ),
            "actual_frozen_actor_hidden_dimension": (
                latent["feature_dimension"]
            ),
            "candidate_state_feature_dimension": state["feature_dimension"],
            "documented_or_requested_feature_dimension": (
                inputs.documented_latent_dimension
            ),
            "documented_dimension_contract_passed": (
                dimension_contract_passed
            ),
            "state_recalculation": state_comparison,
        },
        "fixed_development_gate": fixed_gate,
        "memory_bias_and_overlap": memory_bias,
        "four_level_conclusion": {
            "artifact_and_development_integrity": {
                "artifact_hash_integrity_passed": True,
                "base_binding_passed": True,
                "algorithm_recalculation_passed": True,
                "reported_dimension_contract_passed": (
                    dimension_contract_passed
                ),
                "classification": (
                    "artifact_integrity_passed_with_"
                    "reported_dimension_mismatch"
                    if not dimension_contract_passed
                    else "artifact_integrity_passed"
                ),
            },
            "fixed_development_gate": {
                "passed": fixed_gate["recalculated_gate_passed"],
                "scope": "overlapping_train_validation_development_only",
            },
            "independent_validation_and_generalization": {
                "passed": False,
                "independence_evidence_available": False,
                "generalization_evidence_available": False,
                "classification": "unavailable_due_to_memorization_and_overlap",
            },
            "admission": {
                "allowed": False,
                "candidate_registered": False,
                "admission_closed": True,
                "rule_fallback_required": True,
                "formal_holdout_executed": False,
                "runtime_preflight_executed": False,
                "d3_permission_available": False,
                "d7_permission_available": False,
            },
        },
        "fail_closed_guards": {
            "caller_fixed_external_anchors_are_trust_root": True,
            "candidate_self_signature_is_not_trust_root": True,
            "candidate_file_inventory_exact": True,
            "ordinary_artifact_tamper_rejected": True,
            "synchronously_self_resigned_candidate_rejected": True,
            "known_overlap_diagnostics_recomputed_not_substituted": True,
            "negative_control_contracts": {
                "ordinary_artifact_byte_tamper": (
                    "candidate_artifact_external_anchor_mismatch"
                ),
                "synchronous_candidate_self_resign": (
                    "candidate_manifest_file_external_anchor_mismatch"
                ),
                "overlap_diagnostic_disagreement": (
                    "validation_overlap_expected_crosscheck_mismatch"
                ),
            },
        },
    }
    result["content_sha256"] = _canonical_sha256(result)
    return result


def _audit_candidate_tree(
    inputs: D4V5CandidateAuditInputs,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    root = inputs.candidate_root
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
    files = {
        str(path.relative_to(root)): path
        for path in paths
        if path.is_file()
    }
    _expect(
        set(files) == _CANDIDATE_FILES,
        "candidate_file_inventory_mismatch",
        _set_difference_detail(set(_CANDIDATE_FILES), set(files)),
    )
    observed_directories = {
        str(path.relative_to(root)) for path in paths if path.is_dir()
    }
    _expect(
        not observed_directories,
        "candidate_subdirectory_inventory_mismatch",
        str(sorted(observed_directories)),
    )
    actual = {
        relative: _sha256_file(path)
        for relative, path in sorted(files.items())
    }
    external = {
        D4_V5_MANIFEST_FILE: inputs.expected_manifest_file_sha256,
        D4_V5_STATE_FILE: inputs.expected_state_file_sha256,
        D4_V5_SUMMARY_FILE: inputs.expected_summary_file_sha256,
        D4_V5_GATE_FILE: inputs.expected_gate_file_sha256,
    }
    for relative, expected in external.items():
        _expect(
            actual[relative] == expected,
            "candidate_artifact_external_anchor_mismatch",
            f"{relative}:{actual[relative]}",
        )
    declared = _mapping(manifest.get("artifact_files"), "artifact_files")
    _require_exact_keys(
        declared,
        {
            D4_V5_STATE_FILE,
            D4_V5_SUMMARY_FILE,
            D4_V5_GATE_FILE,
        },
        "artifact_files",
    )
    for relative in declared:
        _expect(
            _normalise_sha256(
                declared[relative], f"declared artifact {relative}"
            )
            == actual[relative],
            "candidate_manifest_artifact_sha256_mismatch",
            str(relative),
        )
    return {
        "passed": True,
        "root": str(root),
        "file_count": len(actual),
        "directory_count": 1,
        "artifact_sha256": actual,
        "tree_sha256": _canonical_sha256(actual),
        "manifest_declared_artifacts_match": True,
        "external_anchors_match": True,
        "symlink_count": 0,
        "special_file_count": 0,
    }


def _audit_content_bindings(
    manifest: Mapping[str, Any],
    state: Mapping[str, Any],
    summary: Mapping[str, Any],
    gate: Mapping[str, Any],
) -> dict[str, Any]:
    expected_schemas = (
        (state, D4_V5_STATE_SCHEMA, "state"),
        (summary, D4_V5_SUMMARY_SCHEMA, "summary"),
        (gate, D4_V5_GATE_SCHEMA, "gate"),
    )
    for payload, schema, name in expected_schemas:
        _expect(
            payload.get("schema") == schema,
            "candidate_payload_schema_mismatch",
            name,
        )
    state_content = _verify_content_sha(
        state, "calibration_state_content_sha256_mismatch"
    )
    summary_content = _verify_content_sha(
        summary, "calibration_summary_content_sha256_mismatch"
    )
    gate_content = _verify_content_sha(
        gate, "development_gate_content_sha256_mismatch"
    )
    declared = {
        "calibration_state_content_sha256": state_content,
        "calibration_summary_content_sha256": summary_content,
        "development_gate_content_sha256": gate_content,
    }
    for name, actual in declared.items():
        _expect(
            _normalise_sha256(manifest.get(name), name) == actual,
            "candidate_cross_content_binding_mismatch",
            name,
        )
    return {
        "passed": True,
        **declared,
    }


def _audit_base_v4_and_v3_bindings(
    inputs: D4V5CandidateAuditInputs,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    expected_manifest_fields = {
        "base_candidate_id": D4_V4_CANDIDATE_ID,
        "base_v4_manifest_file_sha256": (
            inputs.expected_base_v4_manifest_file_sha256
        ),
        "base_v4_manifest_content_sha256": (
            inputs.expected_base_v4_manifest_content_sha256
        ),
        "base_v4_model_state_sha256": (
            inputs.expected_base_v4_model_state_sha256
        ),
        "base_v4_dataset_sha256": (
            inputs.expected_base_v4_dataset_sha256
        ),
        "base_v4_split_sha256": inputs.expected_base_v4_split_sha256,
        "base_v4_tree_sha256": inputs.expected_base_v4_tree_sha256,
        "builder_source_sha256": inputs.expected_builder_source_sha256,
        "v3_registry_tree_sha256": (
            inputs.expected_v3_registry_tree_sha256
        ),
    }
    for name, expected in expected_manifest_fields.items():
        _expect(
            manifest.get(name) == expected,
            "candidate_base_binding_mismatch",
            name,
        )

    builder = inputs.repository_root / D4_V5_SOURCE_RELATIVE_PATH
    builder_sha = _sha256_file(builder)
    _expect(
        builder_sha == inputs.expected_builder_source_sha256,
        "builder_source_external_anchor_mismatch",
        builder_sha,
    )
    source_inventory = {}
    for relative, expected in inputs.expected_v4_source_files.items():
        actual = _sha256_file(inputs.repository_root / relative)
        _expect(
            actual == expected,
            "v4_source_external_anchor_mismatch",
            f"{relative}:{actual}",
        )
        source_inventory[relative] = actual

    v4_root = inputs.base_v4_root
    v4_inventory = _file_inventory(v4_root)
    v4_tree_sha = _canonical_sha256(v4_inventory)
    _expect(
        v4_tree_sha == inputs.expected_base_v4_tree_sha256,
        "base_v4_tree_external_anchor_mismatch",
        v4_tree_sha,
    )
    v4_manifest_path = v4_root / D4_V4_MANIFEST_FILE
    v4_manifest_file_sha = _sha256_file(v4_manifest_path)
    _expect(
        v4_manifest_file_sha
        == inputs.expected_base_v4_manifest_file_sha256,
        "base_v4_manifest_file_external_anchor_mismatch",
        v4_manifest_file_sha,
    )
    v4_manifest = _load_json(v4_manifest_path, "base v4 manifest")
    _expect(
        v4_manifest.get("schema") == D4_V4_MANIFEST_SCHEMA
        and v4_manifest.get("candidate_id") == D4_V4_CANDIDATE_ID
        and v4_manifest.get("model_version") == D4_V4_MODEL_VERSION,
        "base_v4_identity_mismatch",
        str(v4_manifest.get("candidate_id")),
    )
    v4_manifest_content_sha = _verify_content_sha(
        v4_manifest, "base_v4_manifest_content_sha256_mismatch"
    )
    _expect(
        v4_manifest_content_sha
        == inputs.expected_base_v4_manifest_content_sha256,
        "base_v4_manifest_content_external_anchor_mismatch",
        v4_manifest_content_sha,
    )
    model_state_sha = _sha256_file(v4_root / "bundle/state_dict.pt")
    _expect(
        model_state_sha == inputs.expected_base_v4_model_state_sha256,
        "base_v4_model_state_external_anchor_mismatch",
        model_state_sha,
    )
    dataset_manifest = _load_json(
        v4_root / "development_dataset/manifest.json",
        "base v4 dataset manifest",
    )
    dataset_sha = _verify_dataset_manifest(dataset_manifest)
    split_sha = _verify_split(dataset_manifest.get("split"))
    _expect(
        dataset_sha == inputs.expected_base_v4_dataset_sha256,
        "base_v4_dataset_external_anchor_mismatch",
        dataset_sha,
    )
    _expect(
        split_sha == inputs.expected_base_v4_split_sha256,
        "base_v4_split_external_anchor_mismatch",
        split_sha,
    )

    v3_root = inputs.repository_root / D4_V3_REGISTRY_RELATIVE_ROOT
    v3_inventory = _file_inventory(v3_root)
    v3_tree_sha = _canonical_sha256(v3_inventory)
    _expect(
        v3_tree_sha == inputs.expected_v3_registry_tree_sha256,
        "v3_registry_tree_external_anchor_mismatch",
        v3_tree_sha,
    )
    return {
        "passed": True,
        "builder_source_file": str(builder),
        "builder_source_sha256": builder_sha,
        "v4_source_sha256": source_inventory,
        "base_v4_root": str(v4_root),
        "base_v4_file_count": len(v4_inventory),
        "base_v4_tree_sha256": v4_tree_sha,
        "base_v4_manifest_file_sha256": v4_manifest_file_sha,
        "base_v4_manifest_content_sha256": v4_manifest_content_sha,
        "base_v4_model_state_sha256": model_state_sha,
        "base_v4_dataset_sha256": dataset_sha,
        "base_v4_split_sha256": split_sha,
        "v3_registry_root": str(v3_root),
        "v3_registry_file_count": len(v3_inventory),
        "v3_registry_tree_sha256": v3_tree_sha,
        "test_payload_integrity_hash_count": sum(
            item.get("split") == "test"
            for item in _sequence(
                dataset_manifest.get("episodes"), "dataset episodes"
            )
        ),
        "test_payload_semantic_read_count": 0,
        "formal_holdout_payload_read_count": 0,
    }


def _audit_registration_boundary(
    inputs: D4V5CandidateAuditInputs,
) -> dict[str, Any]:
    v4_source = inputs.repository_root / D4_V4_SOURCE_RELATIVE_PATH
    v5_source = inputs.repository_root / D4_V5_SOURCE_RELATIVE_PATH
    v4_constants = _extract_none_constants(
        v4_source.read_bytes(), _V4_REGISTRATION_CONSTANTS
    )
    v5_constants = _extract_none_constants(
        v5_source.read_bytes(), _V5_REGISTRATION_CONSTANTS
    )
    v4_registry = inputs.repository_root / D4_V4_REGISTRY_RELATIVE_ROOT
    v5_registry = inputs.repository_root / D4_V5_REGISTRY_RELATIVE_ROOT
    _expect(
        not v4_registry.exists(),
        "v4_candidate_registry_path_present",
        str(v4_registry),
    )
    _expect(
        not v5_registry.exists(),
        "v5_candidate_registry_path_present",
        str(v5_registry),
    )
    registry_parent = (
        inputs.repository_root
        / "research_modules/d4_distributed_fallback/model_registry"
    )
    try:
        inputs.candidate_root.relative_to(registry_parent)
    except ValueError:
        outside_registry = True
    else:
        outside_registry = False
    _expect(
        outside_registry,
        "v5_candidate_located_in_registry",
        str(inputs.candidate_root),
    )
    return {
        "passed": True,
        "v4_registration_constants": v4_constants,
        "v5_registration_constants": v5_constants,
        "v4_registry_path_present": False,
        "v5_registry_path_present": False,
        "v5_candidate_outside_registry": True,
        "candidate_unregistered": True,
    }


def _audit_permissions_and_usage(
    manifest: Mapping[str, Any],
    *,
    state: Mapping[str, Any],
    summary: Mapping[str, Any],
    gate: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_permissions = _validate_permissions(
        manifest.get("permissions"), "manifest permissions"
    )
    summary_permissions = _validate_permissions(
        summary.get("permissions"), "summary permissions"
    )
    _expect(
        manifest_permissions == summary_permissions,
        "permission_claim_cross_binding_mismatch",
        "manifest/summary",
    )
    for payload, context in (
        (manifest, "manifest"),
        (summary, "summary"),
        (state, "state"),
        (gate, "gate"),
    ):
        for name in (
            "development_only",
            "shadow_only",
            "admission_closed",
            "rule_fallback_required",
        ):
            _expect(
                payload.get(name) is True,
                "safety_boundary_boolean_not_true",
                f"{context}:{name}",
            )
    _expect(
        manifest.get("registered") is False
        and manifest.get("formal_holdout_evaluated") is False
        and manifest.get("runtime_preflight_completed") is False,
        "manifest_admission_boundary_open",
        "registered/formal_holdout/runtime_preflight",
    )
    _expect(
        summary.get("registered") is False
        and summary.get("formal_holdout_completed") is False
        and summary.get("runtime_preflight_completed") is False
        and summary.get("production_permission_available") is False
        and summary.get("d3_permission_available") is False
        and summary.get("d7_permission_available") is False,
        "summary_admission_boundary_open",
        "summary flags",
    )
    _expect(
        manifest.get("candidate_classification")
        == D4_V5_CANDIDATE_CLASSIFICATION
        and summary.get("candidate_classification")
        == D4_V5_CANDIDATE_CLASSIFICATION
        and manifest.get("independence_evidence_available") is False
        and manifest.get("generalization_evidence_available") is False
        and summary.get("independence_evidence_available") is False
        and summary.get("generalization_evidence_available") is False,
        "candidate_scope_classification_mismatch",
        "memorization/independence/generalization",
    )

    data_usage = _mapping(summary.get("data_usage"), "summary data_usage")
    zero_fields = (
        "validation_fit_count",
        "validation_weight_fit_count",
        "validation_threshold_fit_count",
        "validation_hyperparameter_fit_count",
        "validation_selection_count",
        "validation_overlap_diagnostic_fit_count",
        "test_payload_read_count",
        "test_payload_fit_count",
        "test_payload_weight_fit_count",
        "formal_holdout_payload_read_count",
        "formal_holdout_payload_fit_count",
        "truth_identifier_use_count",
        "future_outcome_use_count",
        "reward_use_count",
    )
    for name in zero_fields:
        _expect(
            data_usage.get(name) == 0,
            "candidate_data_usage_nonzero",
            name,
        )
    for name in (
        "validation_fit_count",
        "test_payload_read_count",
        "test_payload_fit_count",
        "formal_holdout_payload_read_count",
        "formal_holdout_payload_fit_count",
    ):
        _expect(
            state.get(name) == 0,
            "candidate_state_data_usage_nonzero",
            name,
        )
    _expect(
        data_usage.get("fit_split") == "train"
        and data_usage.get("audit_split") == "validation"
        and data_usage.get("train_payload_read_count") == 350
        and data_usage.get("train_fit_count") == 350
        and data_usage.get("validation_payload_read_count") == 75
        and data_usage.get("validation_audit_count") == 75,
        "candidate_data_usage_inventory_mismatch",
        str(dict(data_usage)),
    )
    return {
        "passed": True,
        "candidate_declared_data_usage": dict(data_usage),
        "d6_semantic_payload_usage": {
            "train_payload_read_count": 350,
            "validation_payload_read_count": 75,
            "test_payload_read_count": 0,
            "formal_holdout_payload_read_count": 0,
            "fit_count": 0,
            "threshold_fit_count": 0,
            "hyperparameter_fit_count": 0,
        },
        "permissions": manifest_permissions,
        "all_permissions_false": True,
        "candidate_unregistered": registry["candidate_unregistered"],
        "admission_closed": True,
        "rule_fallback_required": True,
        "d3_permission_available": False,
        "d7_permission_available": False,
    }


def _load_train_validation_records(
    inputs: D4V5CandidateAuditInputs,
) -> dict[str, Any]:
    if str(inputs.repository_root) not in sys.path:
        sys.path.insert(0, str(inputs.repository_root))
    try:
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_dataset import (
            RegionLearningSplit,
            load_region_learning_dataset_splits,
        )
        from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v4_shadow_candidate import (
            RegionResourceV4CandidateLoader,
            _confidence_records,
        )
    except (ImportError, OSError) as exc:
        _fail(
            "frozen_v4_audit_dependency_unavailable",
            f"{type(exc).__name__}:{exc}",
        )
    try:
        loader = RegionResourceV4CandidateLoader(
            inputs.base_v4_root,
            require_registered_binding=False,
            evaluation_context="offline_development",
        )
        dataset = load_region_learning_dataset_splits(
            inputs.base_v4_root / "development_dataset",
            splits=(
                RegionLearningSplit.TRAIN,
                RegionLearningSplit.VALIDATION,
            ),
        )
        train = _confidence_records(
            loader.loaded_bundle.model,
            dataset,
            split=RegionLearningSplit.TRAIN,
            projector=loader.projector,
            rule_policy=loader.rule_policy,
        )
        validation = _confidence_records(
            loader.loaded_bundle.model,
            dataset,
            split=RegionLearningSplit.VALIDATION,
            projector=loader.projector,
            rule_policy=loader.rule_policy,
        )
    except Exception as exc:
        _fail(
            "frozen_v4_train_validation_reconstruction_failed",
            f"{type(exc).__name__}:{exc}",
        )
    _expect(
        len(train) == 350 and len(validation) == 75,
        "frozen_v4_record_inventory_mismatch",
        f"train={len(train)},validation={len(validation)}",
    )
    return {
        "model": loader.loaded_bundle.model,
        "train": tuple(train),
        "validation": tuple(validation),
    }


def _reconstruct_latent_and_state(records: Mapping[str, Any]) -> dict[str, Any]:
    model = records["model"]
    train_records = _sequence(records["train"], "train records")
    validation_records = _sequence(
        records["validation"], "validation records"
    )
    train_features = [
        _actor_pooled_latent(model, record[0]) for record in train_records
    ]
    validation_features = [
        _actor_pooled_latent(model, record[0])
        for record in validation_records
    ]
    feature_dimension = len(train_features[0])
    _expect(
        feature_dimension > 0
        and all(len(row) == feature_dimension for row in train_features)
        and all(
            len(row) == feature_dimension for row in validation_features
        ),
        "reconstructed_latent_dimension_inconsistent",
        str(feature_dimension),
    )
    mean = tuple(
        sum(row[column] for row in train_features) / len(train_features)
        for column in range(feature_dimension)
    )
    scale_values = []
    for column in range(feature_dimension):
        variance = sum(
            (row[column] - mean[column]) ** 2 for row in train_features
        ) / len(train_features)
        scale = sqrt(max(variance, 0.0))
        scale_values.append(scale if scale > D4_V5_SCALE_EPSILON else 1.0)
    scale = tuple(scale_values)
    train_normalized = tuple(
        _normalise_feature(row, mean=mean, scale=scale)
        for row in train_features
    )
    validation_normalized = tuple(
        _normalise_feature(row, mean=mean, scale=scale)
        for row in validation_features
    )
    train_labels = tuple(bool(record[1]) for record in train_records)
    validation_labels = tuple(
        bool(record[1]) for record in validation_records
    )
    train_raw_keys = tuple(
        _observable_graph_key(record[0]) for record in train_records
    )
    validation_raw_keys = tuple(
        _observable_graph_key(record[0])
        for record in validation_records
    )
    train_latent_keys = tuple(
        _canonical_sha256(list(row)) for row in train_normalized
    )
    validation_latent_keys = tuple(
        _canonical_sha256(list(row)) for row in validation_normalized
    )
    return {
        "feature_dimension": feature_dimension,
        "train_features": tuple(train_features),
        "validation_features": tuple(validation_features),
        "train_feature_mean": mean,
        "train_feature_scale": scale,
        "train_normalized": train_normalized,
        "validation_normalized": validation_normalized,
        "train_labels": train_labels,
        "validation_labels": validation_labels,
        "train_raw_keys": train_raw_keys,
        "validation_raw_keys": validation_raw_keys,
        "train_latent_keys": train_latent_keys,
        "validation_latent_keys": validation_latent_keys,
    }


def _compare_reconstructed_state(
    state: Mapping[str, Any],
    latent: Mapping[str, Any],
) -> dict[str, Any]:
    expected_scalars = {
        "algorithm": "standardized_inverse_distance_knn",
        "feature_source": (
            "frozen_v4_actor_pooled_message_passing_latent"
        ),
        "fit_split": "train",
        "feature_dimension": latent["feature_dimension"],
        "neighbour_count": D4_V5_NEIGHBOUR_COUNT,
        "exact_match_epsilon": D4_V5_EXACT_EPSILON,
        "fixed_minimum_confidence": D4_V5_FIXED_GATE,
        "train_sample_count": 350,
        "train_positive_count": 58,
        "train_negative_count": 292,
        "latent_key_count": len(set(latent["train_latent_keys"])),
        "latent_conflicting_key_count": 0,
    }
    for name, expected in expected_scalars.items():
        actual = state.get(name)
        if isinstance(expected, float):
            matched = type(actual) in {int, float} and isclose(
                float(actual), expected, rel_tol=0.0, abs_tol=1.0e-15
            )
        else:
            matched = actual == expected
        _expect(
            matched,
            "reconstructed_state_scalar_mismatch",
            f"{name}:{actual}!={expected}",
        )
    mean_difference = _maximum_nested_difference(
        state.get("train_feature_mean"),
        latent["train_feature_mean"],
    )
    scale_difference = _maximum_nested_difference(
        state.get("train_feature_scale"),
        latent["train_feature_scale"],
    )
    normalized_difference = _maximum_nested_difference(
        state.get("normalized_train_features"),
        latent["train_normalized"],
    )
    state_labels = tuple(
        _require_bool(value, "state train label")
        for value in _sequence(state.get("train_labels"), "state train labels")
    )
    _expect(
        mean_difference <= 1.0e-12
        and scale_difference <= 1.0e-12
        and normalized_difference <= 1.0e-12
        and state_labels == latent["train_labels"],
        "reconstructed_state_inventory_mismatch",
        (
            f"mean={mean_difference},scale={scale_difference},"
            f"normalized={normalized_difference},"
            f"labels={state_labels == latent['train_labels']}"
        ),
    )
    return {
        "passed": True,
        "feature_dimension": latent["feature_dimension"],
        "train_sample_count": len(latent["train_labels"]),
        "validation_sample_count": len(latent["validation_labels"]),
        "train_positive_count": sum(latent["train_labels"]),
        "train_negative_count": sum(not value for value in latent["train_labels"]),
        "validation_positive_count": sum(latent["validation_labels"]),
        "validation_negative_count": sum(
            not value for value in latent["validation_labels"]
        ),
        "latent_key_count": len(set(latent["train_latent_keys"])),
        "maximum_mean_absolute_difference": mean_difference,
        "maximum_scale_absolute_difference": scale_difference,
        "maximum_normalized_feature_absolute_difference": (
            normalized_difference
        ),
        "train_labels_exact_match": True,
        "train_feature_mean_sha256": _canonical_sha256(
            list(latent["train_feature_mean"])
        ),
        "train_feature_scale_sha256": _canonical_sha256(
            list(latent["train_feature_scale"])
        ),
        "normalized_train_features_sha256": _canonical_sha256(
            [list(row) for row in latent["train_normalized"]]
        ),
        "train_labels_sha256": _canonical_sha256(
            list(latent["train_labels"])
        ),
    }


def _recalculate_fixed_development_gate(
    *,
    state: Mapping[str, Any],
    summary: Mapping[str, Any],
    gate: Mapping[str, Any],
    latent: Mapping[str, Any],
) -> dict[str, Any]:
    _expect(
        gate.get("fixed_minimum_confidence") == D4_V5_FIXED_GATE
        and gate.get("minimum_train_positive_recall")
        == D4_V5_MINIMUM_RECALL
        and gate.get("minimum_validation_positive_recall")
        == D4_V5_MINIMUM_RECALL
        and gate.get("required_train_negative_specificity")
        == D4_V5_REQUIRED_SPECIFICITY
        and gate.get("required_validation_negative_specificity")
        == D4_V5_REQUIRED_SPECIFICITY
        and gate.get("minimum_train_positive_margin")
        == D4_V5_MINIMUM_MARGIN
        and gate.get("minimum_validation_positive_margin")
        == D4_V5_MINIMUM_MARGIN,
        "development_gate_fixed_policy_mismatch",
        "threshold/recall/specificity/margin",
    )
    train_indices = tuple(range(len(latent["train_labels"])))
    train_scores = tuple(
        _score_knn(
            query,
            train_rows=latent["train_normalized"],
            train_labels=latent["train_labels"],
            allowed_indices=train_indices,
        )[0]
        for query in latent["train_normalized"]
    )
    validation_scores = tuple(
        _score_knn(
            query,
            train_rows=latent["train_normalized"],
            train_labels=latent["train_labels"],
            allowed_indices=train_indices,
        )[0]
        for query in latent["validation_normalized"]
    )
    train_metrics = _complete_metrics(
        latent["train_labels"], train_scores
    )
    validation_metrics = _complete_metrics(
        latent["validation_labels"], validation_scores
    )
    _compare_declared_metrics(
        _mapping(summary.get("train_metrics"), "summary train_metrics"),
        train_metrics,
        "train",
    )
    _compare_declared_metrics(
        _mapping(
            summary.get("validation_metrics"),
            "summary validation_metrics",
        ),
        validation_metrics,
        "validation",
    )
    gate_passed = (
        train_metrics["positive_recall"] >= D4_V5_MINIMUM_RECALL
        and validation_metrics["positive_recall"]
        >= D4_V5_MINIMUM_RECALL
        and isclose(
            train_metrics["negative_specificity"],
            D4_V5_REQUIRED_SPECIFICITY,
        )
        and isclose(
            validation_metrics["negative_specificity"],
            D4_V5_REQUIRED_SPECIFICITY,
        )
        and train_metrics["minimum_positive_passing_margin"]
        >= D4_V5_MINIMUM_MARGIN
        and validation_metrics["minimum_positive_passing_margin"]
        >= D4_V5_MINIMUM_MARGIN
    )
    _expect(
        gate_passed
        and summary.get("development_gate_passed") is True
        and summary.get("development_gate_reasons") == [],
        "recalculated_development_gate_mismatch",
        str(gate_passed),
    )
    return {
        "recalculated_gate_passed": True,
        "candidate_declared_gate_passed": True,
        "fixed_minimum_confidence": D4_V5_FIXED_GATE,
        "neighbour_count": D4_V5_NEIGHBOUR_COUNT,
        "train": train_metrics,
        "validation": validation_metrics,
        "interpretation": (
            "development_gate_only_not_independent_validation_or_admission"
        ),
    }


def _audit_memory_bias(
    inputs: D4V5CandidateAuditInputs,
    *,
    latent: Mapping[str, Any],
) -> dict[str, Any]:
    train_rows = latent["train_normalized"]
    train_labels = latent["train_labels"]
    all_indices = tuple(range(len(train_rows)))

    full_scores = []
    self_match_count = 0
    self_exact_match_count = 0
    for index, query in enumerate(train_rows):
        score, neighbours = _score_knn(
            query,
            train_rows=train_rows,
            train_labels=train_labels,
            allowed_indices=all_indices,
        )
        full_scores.append(score)
        self_match_count += int(
            any(neighbour_index == index for _, neighbour_index in neighbours)
        )
        self_exact_match_count += int(
            any(
                neighbour_index == index and distance <= D4_V5_EXACT_EPSILON
                for distance, neighbour_index in neighbours
            )
        )

    leave_one_scores = tuple(
        _score_knn(
            query,
            train_rows=train_rows,
            train_labels=train_labels,
            allowed_indices=tuple(
                candidate for candidate in all_indices if candidate != index
            ),
        )[0]
        for index, query in enumerate(train_rows)
    )
    raw_groups = _group_indices(latent["train_raw_keys"])
    latent_groups = _group_indices(latent["train_latent_keys"])
    raw_group_scores = tuple(
        _score_knn(
            query,
            train_rows=train_rows,
            train_labels=train_labels,
            allowed_indices=tuple(
                candidate
                for candidate in all_indices
                if latent["train_raw_keys"][candidate]
                != latent["train_raw_keys"][index]
            ),
        )[0]
        for index, query in enumerate(train_rows)
    )
    latent_group_scores = tuple(
        _score_knn(
            query,
            train_rows=train_rows,
            train_labels=train_labels,
            allowed_indices=tuple(
                candidate
                for candidate in all_indices
                if latent["train_latent_keys"][candidate]
                != latent["train_latent_keys"][index]
            ),
        )[0]
        for index, query in enumerate(train_rows)
    )

    validation_distances = []
    nearest_label_matches = 0
    raw_overlap = []
    latent_overlap = []
    validation_scores = []
    for raw_key, query, label in zip(
        latent["validation_raw_keys"],
        latent["validation_normalized"],
        latent["validation_labels"],
        strict=True,
    ):
        score, neighbours = _score_knn(
            query,
            train_rows=train_rows,
            train_labels=train_labels,
            allowed_indices=all_indices,
        )
        validation_scores.append(score)
        nearest_distance, nearest_index = min(
            (
                (_euclidean_distance(query, row), index)
                for index, row in enumerate(train_rows)
            ),
            key=lambda item: (item[0], item[1]),
        )
        validation_distances.append(nearest_distance)
        nearest_label_matches += int(
            bool(train_labels[nearest_index]) == bool(label)
        )
        raw_overlap.append(raw_key in raw_groups)
        latent_overlap.append(nearest_distance <= D4_V5_EXACT_EPSILON)

    ordered_distances = sorted(validation_distances)
    diagnostics = {
        "validation_record_count": len(validation_distances),
        "exact_raw_graph_key_overlap_count": sum(raw_overlap),
        "exact_latent_overlap_count": sum(latent_overlap),
        "nonexact_lt_1e_3_count": sum(
            D4_V5_EXACT_EPSILON < value < 1.0e-3
            for value in validation_distances
        ),
        "ge_1e_3_lt_1e_1_count": sum(
            1.0e-3 <= value < 1.0e-1
            for value in validation_distances
        ),
        "ge_1e_1_count": sum(
            value >= 1.0e-1 for value in validation_distances
        ),
        "nearest_train_label_match_count": nearest_label_matches,
        "positive_exact_raw_graph_key_overlap_count": sum(
            label and overlap
            for label, overlap in zip(
                latent["validation_labels"], raw_overlap, strict=True
            )
        ),
        "positive_exact_latent_overlap_count": sum(
            label and overlap
            for label, overlap in zip(
                latent["validation_labels"], latent_overlap, strict=True
            )
        ),
    }
    for name, expected in inputs.expected_validation_diagnostics.items():
        _expect(
            diagnostics[name] == expected,
            "validation_overlap_expected_crosscheck_mismatch",
            f"{name}:{diagnostics[name]}!={expected}",
        )

    subset_masks = {
        "all_validation": tuple(True for _ in validation_distances),
        "without_exact_overlap": tuple(
            not (raw or latent_exact)
            for raw, latent_exact in zip(
                raw_overlap, latent_overlap, strict=True
            )
        ),
        "nearest_distance_ge_1e_3": tuple(
            value >= 1.0e-3 for value in validation_distances
        ),
        "nearest_distance_ge_1e_1": tuple(
            value >= 1.0e-1 for value in validation_distances
        ),
    }
    subsets = {}
    for name, mask in subset_masks.items():
        labels = tuple(
            label
            for label, selected in zip(
                latent["validation_labels"], mask, strict=True
            )
            if selected
        )
        scores = tuple(
            score
            for score, selected in zip(validation_scores, mask, strict=True)
            if selected
        )
        subsets[name] = _availability_metrics(
            labels,
            scores,
            minimum_denominator=inputs.minimum_subgroup_denominator,
        )

    return {
        "classification": "development_memorization_baseline",
        "generalization_evidence_available": False,
        "train_self_match": {
            "sample_count": len(train_rows),
            "self_in_k_neighbour_inventory_count": self_match_count,
            "self_exact_match_count": self_exact_match_count,
            "self_match_rate": self_match_count / len(train_rows),
            "full_inventory_metrics": _complete_metrics(
                train_labels, tuple(full_scores)
            ),
        },
        "leave_one_sample_out": {
            "query_count": len(train_rows),
            "query_sample_excluded_from_neighbour_inventory": True,
            "train_standardization_state_held_fixed": True,
            "metrics": _complete_metrics(train_labels, leave_one_scores),
        },
        "leave_one_observable_group_out": {
            "train_standardization_state_held_fixed": True,
            "raw_observable_key": {
                "group_count": len(raw_groups),
                "duplicate_group_count": sum(
                    len(indices) > 1 for indices in raw_groups.values()
                ),
                "maximum_group_size": max(
                    len(indices) for indices in raw_groups.values()
                ),
                "same_key_neighbours_excluded": True,
                "metrics": _complete_metrics(
                    train_labels, raw_group_scores
                ),
            },
            "latent_exact_key": {
                "group_count": len(latent_groups),
                "duplicate_group_count": sum(
                    len(indices) > 1 for indices in latent_groups.values()
                ),
                "maximum_group_size": max(
                    len(indices) for indices in latent_groups.values()
                ),
                "same_key_neighbours_excluded": True,
                "metrics": _complete_metrics(
                    train_labels, latent_group_scores
                ),
            },
        },
        "validation_overlap": {
            **diagnostics,
            "exact_graph_and_latent_overlap_count": sum(
                raw and latent_exact
                for raw, latent_exact in zip(
                    raw_overlap, latent_overlap, strict=True
                )
            ),
            "nearest_train_label_mismatch_count": (
                len(validation_distances) - nearest_label_matches
            ),
            "nearest_train_label_match_rate": (
                nearest_label_matches / len(validation_distances)
            ),
            "nearest_distance_distribution": {
                "minimum": ordered_distances[0],
                "mean": sum(ordered_distances) / len(ordered_distances),
                "p50_nearest_rank": _nearest_rank(
                    ordered_distances, 0.50
                ),
                "p90_nearest_rank": _nearest_rank(
                    ordered_distances, 0.90
                ),
                "p95_nearest_rank": _nearest_rank(
                    ordered_distances, 0.95
                ),
                "maximum": ordered_distances[-1],
            },
            "expected_crosscheck_passed": True,
        },
        "validation_subsets": subsets,
        "minimum_subgroup_denominator": (
            inputs.minimum_subgroup_denominator
        ),
        "interpretation": (
            "fixed development metrics are dominated by exact and near "
            "TRAIN overlap; independent generalization remains unavailable"
        ),
    }


def _actor_pooled_latent(model: Any, graph: Any) -> tuple[float, ...]:
    """Independently reproduce the frozen actor's pooled hidden state."""

    try:
        import torch
    except (ImportError, OSError) as exc:
        _fail("torch_unavailable", type(exc).__name__)
    model.eval()
    with torch.no_grad():
        node_hidden = model.node_encoder(graph.node_features)
        edge_hidden = model.edge_encoder(graph.edge_features)
        if graph.edge_count:
            source = graph.edge_index[0]
            target = graph.edge_index[1]
            for _ in range(model.message_passing_steps):
                messages = model.message_network(
                    torch.cat(
                        (
                            node_hidden[source],
                            node_hidden[target],
                            edge_hidden,
                        ),
                        dim=-1,
                    )
                )
                aggregate = torch.zeros_like(node_hidden)
                aggregate.index_add_(0, target, messages)
                degree = torch.zeros(
                    graph.node_count,
                    dtype=node_hidden.dtype,
                    device=node_hidden.device,
                )
                degree.index_add_(
                    0,
                    target,
                    torch.ones_like(target, dtype=node_hidden.dtype),
                )
                aggregate = aggregate / degree.clamp_min(1.0).unsqueeze(-1)
                node_hidden = model.node_update(
                    torch.cat((node_hidden, aggregate), dim=-1)
                )
        else:
            for _ in range(model.message_passing_steps):
                node_hidden = model.node_update(
                    torch.cat(
                        (node_hidden, torch.zeros_like(node_hidden)),
                        dim=-1,
                    )
                )
        pooled = node_hidden.mean(dim=0).detach().cpu()
    values = tuple(float(value) for value in pooled.tolist())
    _expect(
        values and all(isfinite(value) for value in values),
        "reconstructed_latent_nonfinite",
        str(len(values)),
    )
    return values


def _observable_graph_key(graph: Any) -> str:
    try:
        node_features = graph.node_features.detach().cpu()
        edge_features = graph.edge_features.detach().cpu()
        edge_index = graph.edge_index.detach().cpu()
    except Exception as exc:
        _fail("observable_graph_invalid", type(exc).__name__)
    try:
        import torch
    except (ImportError, OSError) as exc:
        _fail("torch_unavailable", type(exc).__name__)
    _expect(
        bool(torch.isfinite(node_features).all().item())
        and bool(torch.isfinite(edge_features).all().item()),
        "observable_graph_nonfinite",
        "node/edge",
    )
    return _canonical_sha256(
        {
            "architecture": D4_GRAPH_ARCHITECTURE,
            "node_features": {
                "shape": list(node_features.shape),
                "dtype": str(node_features.dtype),
                "values": node_features.tolist(),
            },
            "edge_features": {
                "shape": list(edge_features.shape),
                "dtype": str(edge_features.dtype),
                "values": edge_features.tolist(),
            },
            "edge_index": {
                "shape": list(edge_index.shape),
                "dtype": str(edge_index.dtype),
                "values": edge_index.tolist(),
            },
        }
    )


def _normalise_feature(
    feature: Sequence[float],
    *,
    mean: Sequence[float],
    scale: Sequence[float],
) -> tuple[float, ...]:
    _expect(
        len(feature) == len(mean) == len(scale),
        "normalise_feature_dimension_mismatch",
        f"{len(feature)}:{len(mean)}:{len(scale)}",
    )
    values = tuple(
        (float(value) - float(mean[index])) / float(scale[index])
        for index, value in enumerate(feature)
    )
    _expect(
        all(isfinite(value) for value in values),
        "normalised_feature_nonfinite",
        str(len(values)),
    )
    return values


def _score_knn(
    query: Sequence[float],
    *,
    train_rows: Sequence[Sequence[float]],
    train_labels: Sequence[bool],
    allowed_indices: Sequence[int],
) -> tuple[float, tuple[tuple[float, int], ...]]:
    _expect(
        len(train_rows) == len(train_labels),
        "knn_inventory_mismatch",
        f"{len(train_rows)}:{len(train_labels)}",
    )
    _expect(
        len(allowed_indices) >= D4_V5_NEIGHBOUR_COUNT,
        "knn_allowed_inventory_too_small",
        str(len(allowed_indices)),
    )
    distances = sorted(
        (
            (_euclidean_distance(query, train_rows[index]), int(index))
            for index in allowed_indices
        ),
        key=lambda item: (item[0], item[1]),
    )
    neighbours = tuple(distances[:D4_V5_NEIGHBOUR_COUNT])
    exact = tuple(
        index
        for distance, index in neighbours
        if distance <= D4_V5_EXACT_EPSILON
    )
    if exact:
        score = sum(bool(train_labels[index]) for index in exact) / len(exact)
    else:
        weights = tuple(
            1.0 / max(distance, D4_V5_EXACT_EPSILON)
            for distance, _ in neighbours
        )
        score = sum(
            weight * float(bool(train_labels[index]))
            for weight, (_, index) in zip(
                weights, neighbours, strict=True
            )
        ) / sum(weights)
    _expect(
        isfinite(score) and 0.0 <= score <= 1.0,
        "knn_score_invalid",
        str(score),
    )
    return float(score), neighbours


def _complete_metrics(
    labels: Sequence[bool],
    scores: Sequence[float],
) -> dict[str, Any]:
    _expect(
        len(labels) == len(scores) and len(labels) > 0,
        "metric_inventory_invalid",
        f"{len(labels)}:{len(scores)}",
    )
    positive = sum(bool(label) for label in labels)
    negative = len(labels) - positive
    _expect(
        positive > 0 and negative > 0,
        "complete_metrics_require_both_classes",
        f"{positive}:{negative}",
    )
    passed = tuple(score >= D4_V5_FIXED_GATE for score in scores)
    positive_pass = sum(
        decision and label
        for decision, label in zip(passed, labels, strict=True)
    )
    negative_pass = sum(
        decision and not label
        for decision, label in zip(passed, labels, strict=True)
    )
    positive_margins = tuple(
        score - D4_V5_FIXED_GATE
        for score, decision, label in zip(
            scores, passed, labels, strict=True
        )
        if decision and label
    )
    return {
        "sample_count": len(labels),
        "target_positive_count": positive,
        "target_negative_count": negative,
        "positive_threshold_pass_count": positive_pass,
        "negative_threshold_pass_count": negative_pass,
        "positive_recall": positive_pass / positive,
        "negative_specificity": (
            (negative - negative_pass) / negative
        ),
        "minimum_positive_passing_margin": (
            min(positive_margins) if positive_margins else None
        ),
        "confidence_minimum": min(scores),
        "confidence_mean": sum(scores) / len(scores),
        "confidence_maximum": max(scores),
        "fixed_minimum_confidence": D4_V5_FIXED_GATE,
        "brier_score": sum(
            (score - float(label)) ** 2
            for score, label in zip(scores, labels, strict=True)
        )
        / len(scores),
    }


def _availability_metrics(
    labels: Sequence[bool],
    scores: Sequence[float],
    *,
    minimum_denominator: int,
) -> dict[str, Any]:
    _expect(
        len(labels) == len(scores),
        "subset_metric_inventory_mismatch",
        f"{len(labels)}:{len(scores)}",
    )
    positive = sum(bool(label) for label in labels)
    negative = len(labels) - positive
    passed = tuple(score >= D4_V5_FIXED_GATE for score in scores)
    positive_pass = sum(
        decision and label
        for decision, label in zip(passed, labels, strict=True)
    )
    negative_rejected = sum(
        not decision and not label
        for decision, label in zip(passed, labels, strict=True)
    )
    positive_scores = tuple(
        score
        for score, decision, label in zip(
            scores, passed, labels, strict=True
        )
        if decision and label
    )
    return {
        "sample_count": len(labels),
        "target_positive_count": positive,
        "target_negative_count": negative,
        "positive_recall": _metric_value(
            numerator=positive_pass,
            denominator=positive,
            minimum_denominator=minimum_denominator,
            unavailable_reason="positive_denominator_too_small",
        ),
        "negative_specificity": _metric_value(
            numerator=negative_rejected,
            denominator=negative,
            minimum_denominator=minimum_denominator,
            unavailable_reason="negative_denominator_too_small",
        ),
        "minimum_positive_passing_margin": (
            {
                "availability": "available",
                "value": min(positive_scores) - D4_V5_FIXED_GATE,
                "passing_positive_count": len(positive_scores),
            }
            if len(positive_scores) >= minimum_denominator
            else {
                "availability": "unavailable",
                "value": None,
                "passing_positive_count": len(positive_scores),
                "reason": "passing_positive_denominator_too_small",
            }
        ),
        "brier_score": (
            {
                "availability": "available",
                "value": sum(
                    (score - float(label)) ** 2
                    for score, label in zip(
                        scores, labels, strict=True
                    )
                )
                / len(scores),
                "denominator": len(scores),
            }
            if len(scores) >= minimum_denominator
            else {
                "availability": "unavailable",
                "value": None,
                "denominator": len(scores),
                "reason": "sample_denominator_too_small",
            }
        ),
    }


def _metric_value(
    *,
    numerator: int,
    denominator: int,
    minimum_denominator: int,
    unavailable_reason: str,
) -> dict[str, Any]:
    if denominator < minimum_denominator:
        return {
            "availability": "unavailable",
            "value": None,
            "numerator": numerator,
            "denominator": denominator,
            "reason": unavailable_reason,
        }
    return {
        "availability": "available",
        "value": numerator / denominator,
        "numerator": numerator,
        "denominator": denominator,
    }


def _compare_declared_metrics(
    declared: Mapping[str, Any],
    recalculated: Mapping[str, Any],
    split: str,
) -> None:
    for name, actual in recalculated.items():
        _expect(name in declared, "declared_metric_missing", f"{split}:{name}")
        value = declared[name]
        if actual is None:
            matched = value in {None, -1.0}
        elif type(actual) is int:
            matched = type(value) is int and value == actual
        else:
            matched = type(value) in {int, float} and isclose(
                float(value), float(actual), rel_tol=0.0, abs_tol=1.0e-12
            )
        _expect(
            matched,
            "declared_metric_recalculation_mismatch",
            f"{split}:{name}:{value}!={actual}",
        )


def write_d4_v5_candidate_audit_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Atomically write JSON, Chinese Markdown, and SHA256SUMS."""

    output = Path(output_dir)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"D4 v5 D6 audit output exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir()
    try:
        json_path = temporary / "d4_v5_confidence_candidate_audit.json"
        markdown_path = temporary / "D4_V5_CONFIDENCE_CANDIDATE_AUDIT_CN.md"
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
            render_d4_v5_candidate_audit_markdown(result),
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


def render_d4_v5_candidate_audit_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the independent v5 audit in Chinese."""

    anchors = _mapping(result["anchors"], "anchors")
    latent = _mapping(result["latent_reconstruction"], "latent")
    gate = _mapping(result["fixed_development_gate"], "fixed gate")
    memory = _mapping(
        result["memory_bias_and_overlap"], "memory bias"
    )
    train = _mapping(gate["train"], "train gate")
    validation = _mapping(gate["validation"], "validation gate")
    self_match = _mapping(memory["train_self_match"], "self match")
    loso = _mapping(memory["leave_one_sample_out"], "loso")
    logo = _mapping(
        memory["leave_one_observable_group_out"], "logo"
    )
    raw_logo = _mapping(logo["raw_observable_key"], "raw logo")
    latent_logo = _mapping(logo["latent_exact_key"], "latent logo")
    overlap = _mapping(memory["validation_overlap"], "overlap")
    subsets = _mapping(memory["validation_subsets"], "subsets")

    lines = [
        "# D4 v5 置信校准候选独立审计",
        "",
        "## 结论",
        "",
        (
            "D6 已完成只读审计。候选四个文件、调用方固定哈希、v4 基线、"
            "v3 登记树、数据用途和全 false 权限均核验通过。固定 0.60 开发门"
            "按冻结 actor 和 TRAIN/VALIDATION payload 独立复算后仍通过。"
        ),
        (
            "该结果不构成独立验证。TRAIN 评分把 350/350 个被评样本自身放入"
            "近邻库；VALIDATION 有 42/75 条 exact overlap，只有 3 条样本与"
            " TRAIN 最近距离不小于 0.1。候选保持记忆化开发对照、未注册、"
            "准入关闭并使用规则回退。"
        ),
        (
            "冻结 v4 模型和候选状态的实际 latent 维数均为 "
            f"{latent['actual_frozen_actor_hidden_dimension']}。D4 报告及本次任务"
            f"口径写为 {latent['documented_or_requested_feature_dimension']} 维，"
            "两者不一致。D6 未构造虚假的 64 维结果；该项列入严格审计阻断。"
        ),
        "",
        "## 固定身份",
        "",
        (
            f"- manifest file SHA-256："
            f"`{anchors['candidate_manifest_file_sha256']}`"
        ),
        (
            f"- manifest content SHA-256："
            f"`{anchors['candidate_manifest_content_sha256']}`"
        ),
        (
            f"- calibration state SHA-256："
            f"`{anchors['calibration_state_file_sha256']}`"
        ),
        (
            f"- calibration summary SHA-256："
            f"`{anchors['calibration_summary_file_sha256']}`"
        ),
        (
            f"- development gate SHA-256："
            f"`{anchors['development_gate_file_sha256']}`"
        ),
        (
            f"- builder source SHA-256："
            f"`{anchors['builder_source_sha256']}`"
        ),
        (
            f"- v4 tree SHA-256：`{anchors['base_v4_tree_sha256']}`"
        ),
        (
            f"- v3 registry tree SHA-256："
            f"`{anchors['v3_registry_tree_sha256']}`"
        ),
        "",
        "## 独立复算",
        "",
        "| split | 样本 | 正/负 | 正类召回 | 负类特异度 | 最小正裕量 | Brier |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| TRAIN | {train['sample_count']} | "
            f"{train['target_positive_count']}/{train['target_negative_count']} | "
            f"{train['positive_recall']:.6f} | "
            f"{train['negative_specificity']:.6f} | "
            f"{train['minimum_positive_passing_margin']:.6f} | "
            f"{train['brier_score']:.9f} |"
        ),
        (
            f"| VALIDATION | {validation['sample_count']} | "
            f"{validation['target_positive_count']}/"
            f"{validation['target_negative_count']} | "
            f"{validation['positive_recall']:.6f} | "
            f"{validation['negative_specificity']:.6f} | "
            f"{validation['minimum_positive_passing_margin']:.6f} | "
            f"{validation['brier_score']:.9f} |"
        ),
        "",
        (
            "D6 从冻结 v4 actor 重建实际 24 维池化 latent，使用 TRAIN 的均值"
            "与标准差归一化，再执行 k=11 逆距离评分。重建状态与候选 state "
            "的最大数值差不超过 1e-12。候选 summary 指标只在独立结果生成后"
            "进行逐项核对。"
        ),
        "",
        "## 记忆偏差",
        "",
        (
            f"- 全库存 TRAIN：self-match "
            f"{self_match['self_in_k_neighbour_inventory_count']}/"
            f"{self_match['sample_count']}。"
        ),
        (
            "- leave-one-sample-out：正类召回 "
            f"{loso['metrics']['positive_recall']:.6f}，负类特异度 "
            f"{loso['metrics']['negative_specificity']:.6f}，Brier "
            f"{loso['metrics']['brier_score']:.9f}。"
        ),
        (
            "- raw observable key 留组：正类召回 "
            f"{raw_logo['metrics']['positive_recall']:.6f}，负类特异度 "
            f"{raw_logo['metrics']['negative_specificity']:.6f}，Brier "
            f"{raw_logo['metrics']['brier_score']:.9f}。"
        ),
        (
            "- latent exact key 留组：正类召回 "
            f"{latent_logo['metrics']['positive_recall']:.6f}，负类特异度 "
            f"{latent_logo['metrics']['negative_specificity']:.6f}，Brier "
            f"{latent_logo['metrics']['brier_score']:.9f}。"
        ),
        "",
        "## VALIDATION 重合",
        "",
        "| 项目 | 数量 |",
        "| --- | ---: |",
        (
            f"| raw graph exact overlap | "
            f"{overlap['exact_raw_graph_key_overlap_count']} |"
        ),
        (
            f"| latent exact overlap | "
            f"{overlap['exact_latent_overlap_count']} |"
        ),
        (
            f"| 非 exact 且距离 `<1e-3` | "
            f"{overlap['nonexact_lt_1e_3_count']} |"
        ),
        (
            f"| 距离 `[1e-3,0.1)` | "
            f"{overlap['ge_1e_3_lt_1e_1_count']} |"
        ),
        f"| 距离 `>=0.1` | {overlap['ge_1e_1_count']} |",
        (
            f"| 最近邻标签一致 | "
            f"{overlap['nearest_train_label_match_count']} |"
        ),
        (
            f"| 正类 exact overlap | "
            f"{overlap['positive_exact_latent_overlap_count']}/"
            f"{validation['target_positive_count']} |"
        ),
        "",
        "## 分层指标",
        "",
    ]
    for name in (
        "all_validation",
        "without_exact_overlap",
        "nearest_distance_ge_1e_3",
        "nearest_distance_ge_1e_1",
    ):
        item = _mapping(subsets[name], name)
        recall = _format_available_metric(item["positive_recall"])
        specificity = _format_available_metric(item["negative_specificity"])
        margin = _format_available_metric(
            item["minimum_positive_passing_margin"]
        )
        brier = _format_available_metric(item["brier_score"])
        lines.append(
            f"- `{name}`：n={item['sample_count']}，正/负="
            f"{item['target_positive_count']}/{item['target_negative_count']}，"
            f"recall={recall}，specificity={specificity}，"
            f"margin={margin}，Brier={brier}。"
        )
    lines.extend(
        [
            "",
            (
                "去除 exact overlap 后只剩 1 个正类；距离不小于 0.1 的 3 个"
                "样本均为负类。低于固定最小分母 5 的指标写为 unavailable，"
                "没有用 0 填补。"
            ),
            "",
            "## 数据与权限",
            "",
            "- D6 语义读取 TRAIN 350 条、VALIDATION 75 条。",
            (
                "- TEST payload semantic read/fit 为 0；v4 树完整性检查对 TEST "
                "文件只做字节哈希，不解析内容。"
            ),
            "- 正式 holdout payload read/fit 为 0，未运行正式 holdout。",
            "- v4/v5 登记常量均为空，v4/v5 registry 目标路径不存在。",
            "- 所有生产、D3、D7 权限为 false；未执行 runtime preflight。",
            "",
            "## 准入结论",
            "",
            (
                "候选定性保持 `development memorization baseline`。固定开发门"
                "通过只说明同源重合开发集上的数值结果可复现。独立验证、泛化、"
                "正式准入和收益证据均不可用。"
            ),
            (
                "最终状态为 candidate unregistered、admission closed、rule "
                "fallback required。D6 不运行正式 holdout，不授予 D3/D7 权限。"
            ),
            "",
            "## 失败关闭",
            "",
            (
                "- 普通 artifact 字节篡改由调用方固定文件哈希拒绝，错误码 "
                "`candidate_artifact_external_anchor_mismatch`。"
            ),
            (
                "- 同步修改 payload、候选 artifact hash、content hash 和 manifest "
                "后，仍由 manifest file 外部锚拒绝，错误码 "
                "`candidate_manifest_file_external_anchor_mismatch`。"
            ),
            (
                "- 重合计数与调用方交叉核对值不一致时，错误码 "
                "`validation_overlap_expected_crosscheck_mismatch`。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _format_available_metric(value: Any) -> str:
    payload = _mapping(value, "available metric")
    if payload.get("availability") != "available":
        return "unavailable"
    return f"{float(payload['value']):.6f}"


def _group_indices(keys: Sequence[str]) -> dict[str, tuple[int, ...]]:
    groups: dict[str, list[int]] = {}
    for index, key in enumerate(keys):
        groups.setdefault(str(key), []).append(index)
    return {
        key: tuple(indices) for key, indices in sorted(groups.items())
    }


def _euclidean_distance(
    left: Sequence[float], right: Sequence[float]
) -> float:
    _expect(
        len(left) == len(right),
        "distance_dimension_mismatch",
        f"{len(left)}:{len(right)}",
    )
    return sqrt(
        sum(
            (float(left[index]) - float(right[index])) ** 2
            for index in range(len(left))
        )
    )


def _nearest_rank(values: Sequence[float], quantile: float) -> float:
    _expect(
        values
        and 0.0 < quantile <= 1.0
        and all(isfinite(value) for value in values),
        "nearest_rank_input_invalid",
        str(quantile),
    )
    index = max(0, ceil(quantile * len(values)) - 1)
    return float(values[index])


def _maximum_nested_difference(left: Any, right: Any) -> float:
    left_values = _flatten_numeric(left, "left numeric inventory")
    right_values = _flatten_numeric(right, "right numeric inventory")
    _expect(
        len(left_values) == len(right_values),
        "numeric_inventory_length_mismatch",
        f"{len(left_values)}:{len(right_values)}",
    )
    return max(
        (
            abs(left_value - right_value)
            for left_value, right_value in zip(
                left_values, right_values, strict=True
            )
        ),
        default=0.0,
    )


def _flatten_numeric(value: Any, context: str) -> tuple[float, ...]:
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        flattened = []
        for item in value:
            flattened.extend(_flatten_numeric(item, context))
        return tuple(flattened)
    if type(value) not in {int, float} or not isfinite(float(value)):
        _fail("finite_numeric_value_required", context)
    return (float(value),)


def _validate_permissions(value: Any, context: str) -> dict[str, Any]:
    permissions = _mapping(value, context)
    _require_exact_keys(
        permissions, set(_PERMISSION_FIELDS) | {"schema"}, context
    )
    _expect(
        permissions.get("schema") == D4_V5_PERMISSION_SCHEMA,
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


def _verify_dataset_manifest(manifest: Mapping[str, Any]) -> str:
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


def _verify_split(value: Any) -> str:
    split = _mapping(value, "dataset split")
    actual = _canonical_sha256(
        {
            "algorithm": split.get("algorithm"),
            "split_seed": int(split["split_seed"]),
            "train": sorted(int(item) for item in split["train_seeds"]),
            "validation": sorted(
                int(item) for item in split["validation_seeds"]
            ),
            "test": sorted(int(item) for item in split["test_seeds"]),
        }
    )
    _expect(
        actual == split.get("split_sha256"),
        "dataset_split_content_sha256_mismatch",
        actual,
    )
    return actual


def _extract_none_constants(
    source: bytes, names: Iterable[str]
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
            _fail("registration_constant_not_none", name)
        observed[name] = None
    _expect(
        set(observed) == expected,
        "registration_constant_inventory_mismatch",
        _set_difference_detail(expected, set(observed)),
    )
    return observed


def _verify_content_sha(
    payload: Mapping[str, Any], code: str
) -> str:
    content = dict(payload)
    declared = _normalise_sha256(
        content.pop("content_sha256", None), "content_sha256"
    )
    actual = _canonical_sha256(content)
    _expect(actual == declared, code, actual)
    return actual


def _file_inventory(root: Path) -> dict[str, str]:
    _expect(root.is_dir(), "inventory_root_unavailable", str(root))
    if root.is_symlink():
        _fail("inventory_root_symlink_forbidden", str(root))
    paths = sorted(root.rglob("*"))
    _expect(
        not any(path.is_symlink() for path in paths),
        "inventory_symlink_forbidden",
        str(root),
    )
    _expect(
        not any(
            not path.is_file() and not path.is_dir() for path in paths
        ),
        "inventory_special_file_forbidden",
        str(root),
    )
    return {
        str(path.relative_to(root)): _sha256_file(path)
        for path in paths
        if path.is_file()
    }


def _resolve_path(repository_root: Path, value: Path) -> Path:
    path = Path(value).expanduser()
    return (
        (repository_root / path).resolve()
        if not path.is_absolute()
        else path.resolve()
    )


def _safe_relative_file(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or str(path) != value
    ):
        _fail("relative_file_path_invalid", value)
    return value


def _set_difference_detail(
    expected: set[str], observed: set[str]
) -> str:
    return (
        f"missing={sorted(expected - observed)},"
        f"extra={sorted(observed - expected)}"
    )


def _load_json(path: Path, context: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("json_artifact_invalid", f"{context}:{path}:{type(exc).__name__}")
    if not isinstance(value, Mapping):
        _fail("json_object_required", context)
    return dict(value)


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", context)
    return value


def _sequence(value: Any, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
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
    if len(digest) != _SHA256_LENGTH or any(
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


def _require_bool(value: Any, context: str) -> bool:
    if type(value) is not bool:
        _fail("boolean_required", context)
    return bool(value)


def _expect(condition: bool, code: str, detail: str) -> None:
    if not condition:
        _fail(code, detail)


def _fail(code: str, detail: str) -> None:
    raise D4V5CandidateAuditError(code, detail)
