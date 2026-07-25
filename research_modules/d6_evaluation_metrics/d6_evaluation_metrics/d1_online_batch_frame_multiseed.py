"""Independent D6 admission for the D1 online batch-to-frame handoff.

The evaluator consumes a preregistered, same-clean-commit 13-pair matrix.  It
does not mutate producer evidence and does not participate in online control.
Only the registered handoff treatment, its diagnostics, treatment-derived
identity, and performance fields are normalized for semantic comparison.
Assignment plans remain business evidence: opaque run-instance plan identities
are mapped by lineage only after version, source hash, ACK, D4 authority, and
downstream references are validated.
"""

from __future__ import annotations

import argparse
import copy
import csv
from pathlib import Path
import math
import sys
from statistics import fmean
from typing import Any, Mapping, Sequence

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from research_modules.scalable_3d_simulation.cross_build_equivalence import (
    CROSS_BUILD_EQUIVALENCE_SCHEMA_VERSION,
    compare_cross_build_episodes,
)

from . import d1_publication_metadata_multiseed as _base


D1_ONLINE_BATCH_FRAME_MULTISEED_EVALUATION_SCHEMA_VERSION = (
    "d6.d1_online_batch_frame_multiseed_evaluation.v1"
)
D1_ONLINE_BATCH_FRAME_MULTISEED_COMPACT_SCHEMA_VERSION = (
    "d6.d1_online_batch_frame_multiseed_compact.v1"
)
D1_ONLINE_BATCH_FRAME_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-online-batch-frame-multiseed-matrix-v1"
)
D1_ONLINE_BATCH_FRAME_EVIDENCE_SCHEMA_VERSION = (
    "scalable3d-d1-online-batch-frame-multiseed-evidence-v1"
)
D1_ONLINE_BATCH_FRAME_DIAGNOSTICS_SCHEMA_VERSION = (
    "d1.online_batch_frame_handoff_diagnostics.v1"
)
D1_ONLINE_BATCH_FRAME_EXPERIMENT_ID = (
    "d1-online-batch-frame-multiseed-20260725-v1"
)
D1_ONLINE_BATCH_FRAME_MATRIX_SHA256 = (
    "4afbf9ac273763a16aa01cc744fd67b52e437099460b33377a128f986ac5719b"
)
D1_ONLINE_BATCH_FRAME_SOURCE_COMMIT = (
    "43feaf600f288a85ce76a76862334256f0d0d352"
)
D1_ONLINE_BATCH_FRAME_EVALUATION_DATE = "2026-07-25"

REFERENCE_IMPLEMENTATION = "convert_then_frame_v1"
CANDIDATE_IMPLEMENTATION = "closed_immutable_batch_to_frame_v1"
REFERENCE_IMPLEMENTATION_ID = (
    "d1.online_batch_frame.convert_then_frame.v1"
)
CANDIDATE_IMPLEMENTATION_ID = (
    "d1.online_batch_frame.closed_immutable_batch_final_frame_validation.v1"
)

_REFERENCE_ARM = "reference"
_CANDIDATE_ARM = "candidate"
_ARMS = (_REFERENCE_ARM, _CANDIDATE_ARM)
_GROUPS = ("short", "long")
_IMPLEMENTATIONS = {
    _REFERENCE_ARM: REFERENCE_IMPLEMENTATION,
    _CANDIDATE_ARM: CANDIDATE_IMPLEMENTATION,
}
_IMPLEMENTATION_IDS = {
    _REFERENCE_ARM: REFERENCE_IMPLEMENTATION_ID,
    _CANDIDATE_ARM: CANDIDATE_IMPLEMENTATION_ID,
}
_RUN_FLAGS = ("--integrated-stack",)
_TARGET_COUNT = 200
_RESOURCE_COUNT = 200
_RECON_COUNT = 2
_BOOTSTRAP_RESAMPLES = 10_000
_BOOTSTRAP_RNG_SEED = 20_260_725
_SHORT_SEEDS = tuple(range(1121, 1131))
_LONG_SEEDS = tuple(range(1121, 1124))
_SHORT_DURATION_S = 2.2
_LONG_DURATION_S = 10.0
_TREATMENT_MARKER = "D6_REGISTERED_ONLINE_BATCH_FRAME_TREATMENT"
_PERFORMANCE_MARKER = "D6_REGISTERED_PERFORMANCE_DIAGNOSTIC"
_TREATMENT_DERIVED_ID_MARKER = "D6_TREATMENT_DERIVED_EPISODE_ID"
_VALIDATION_KIND = "online_batch_frame_handoff"

_EXPECTED_GATES = {
    "all_pairs_business_semantics_equal": True,
    "all_pairs_finite_state": True,
    "all_pairs_online_truth_use_count": 0,
    "all_pairs_explicit_implementation_identity": True,
    "all_pairs_online_batch_frame_audit_valid": True,
    "short_minimum_candidate_faster_count": 8,
    "short_minimum_scan_input_improvement_pct": 20.0,
    "short_bootstrap_relative_change_upper_bound_pct": 0.0,
    "long_minimum_candidate_faster_count": 2,
    "long_minimum_scan_input_improvement_pct": 20.0,
    "short_minimum_core_wall_improvement_pct": 2.0,
    "long_minimum_core_wall_improvement_pct": 2.0,
    "maximum_short_d2_association_mean_increase_pct": 5.0,
    "maximum_long_d2_association_mean_increase_pct": 5.0,
    "maximum_rss_mean_increase_pct": 5.0,
    "maximum_any_pair_rss_increase_pct": 5.0,
    "minimum_candidate_duplicate_check_reduction_pct": 95.0,
    "minimum_candidate_closed_handoff_ratio_pct": 99.0,
    "maximum_candidate_reference_fallback_count": 0,
}
_EXPECTED_BOUNDARY = {
    "simulation_mode": "three_dimensional_point_mass",
    "airsim_evidence": False,
    "truth_is_online_control_input": False,
    "system_realtime_requires_real_time_factor_at_least_one": True,
    "same_source_commit_for_both_arms": True,
    "only_allowed_runtime_treatment_difference": (
        "d1_online_batch_frame_implementation"
    ),
    "reference_implementation": REFERENCE_IMPLEMENTATION,
    "candidate_implementation": CANDIDATE_IMPLEMENTATION,
    "diagnostics_schema_version": (
        D1_ONLINE_BATCH_FRAME_DIAGNOSTICS_SCHEMA_VERSION
    ),
    "candidate_all_runtime_batches_must_use_closed_handoff": True,
    "candidate_default_off": True,
    "final_readonly_frame_check_preserved": True,
    "full_raw_batch_identity_check_preserved": True,
    "raw_source_absolute_immutability_claimed": False,
    "development_profile_seed_excluded": 1112,
    "prior_episode_outputs_reused": False,
}
_EXPECTED_CASES = (
    ("short_seed_1121", "short", 1121, 2.2, ("reference", "candidate")),
    ("short_seed_1122", "short", 1122, 2.2, ("candidate", "reference")),
    ("short_seed_1123", "short", 1123, 2.2, ("reference", "candidate")),
    ("short_seed_1124", "short", 1124, 2.2, ("candidate", "reference")),
    ("short_seed_1125", "short", 1125, 2.2, ("reference", "candidate")),
    ("short_seed_1126", "short", 1126, 2.2, ("candidate", "reference")),
    ("short_seed_1127", "short", 1127, 2.2, ("reference", "candidate")),
    ("short_seed_1128", "short", 1128, 2.2, ("candidate", "reference")),
    ("short_seed_1129", "short", 1129, 2.2, ("reference", "candidate")),
    ("short_seed_1130", "short", 1130, 2.2, ("candidate", "reference")),
    ("long_seed_1121", "long", 1121, 10.0, ("candidate", "reference")),
    ("long_seed_1122", "long", 1122, 10.0, ("reference", "candidate")),
    ("long_seed_1123", "long", 1123, 10.0, ("candidate", "reference")),
)
_EXPECTED_MATRIX_KEYS = {
    "schema_version",
    "experiment_id",
    "same_clean_commit_required",
    "target_count",
    "resource_count",
    "recon_count",
    "arm_implementations",
    "run_flags",
    "cooldown_s",
    "bootstrap_seed",
    "bootstrap_resamples",
    "cases",
    "admission_gates",
    "evidence_boundary",
}
_BATCH_FRAME_OPERATION_FIELDS = {
    "request_count",
    "reference_request_count",
    "candidate_request_count",
    "reference_path_execution_count",
    "candidate_closed_handoff_count",
    "candidate_reference_fallback_count",
    "candidate_raw_rejection_count",
    "candidate_resource_rejection_count",
    "successful_build_count",
    "rejected_build_count",
    "raw_batch_identity_check_count",
    "raw_measurement_identity_check_count",
    "measurement_conversion_count",
    "converted_observation_collection_check_count",
    "snapshot_structure_check_count",
    "snapshot_structure_eligible_count",
    "snapshot_structure_ineligible_count",
    "snapshot_structure_error_count",
    "closed_payload_snapshot_attempt_count",
    "closed_payload_snapshot_success_count",
    "closed_payload_snapshot_failure_count",
    "frame_final_identity_check_count",
    "output_observation_count",
}
_EXPECTED_CONFIG_SCHEMA_VERSION = "scalable3d-scenario-v1"
_EXPECTED_RUNTIME_PROFILE_SCHEMA_VERSION = (
    "scalable3d-integrated-stack-runtime-profile-v1"
)
_EXPECTED_GOVERNANCE_SCHEMA_VERSION = (
    "scalable3d-observation-governance-runtime-v2"
)
_METRICS = _base._METRICS
_LOWER_IS_BETTER = _base._LOWER_IS_BETTER
_REQUIRED_ADMISSION_METRICS = {
    "d1_fusion_wall_s",
    "d2_association_wall_s",
    "core_wall_s",
    "maximum_rss_kib",
    "real_time_factor",
}

D1OnlineBatchFrameEvidenceError = (
    _base.D1PublicationMetadataEvidenceError
)


class D1OnlineBatchFrameEvidence:
    """Validated immutable bindings from one completed producer manifest."""

    def __init__(
        self,
        *,
        source_path: Path,
        source_sha256: str,
        matrix_path: Path,
        matrix_sha256: str,
        matrix: Mapping[str, Any],
        output_root: Path,
        source_commit: str,
        source_worktree: Path,
        pairs: Sequence[_base.D1PublicationMetadataPairBinding],
    ) -> None:
        self.source_path = source_path
        self.source_sha256 = source_sha256
        self.matrix_path = matrix_path
        self.matrix_sha256 = matrix_sha256
        self.matrix = copy.deepcopy(dict(matrix))
        self.output_root = output_root
        self.source_commit = source_commit
        self.source_worktree = source_worktree
        self.pairs = tuple(pairs)


def load_d1_online_batch_frame_evidence_manifest(
    source: str | Path,
) -> D1OnlineBatchFrameEvidence:
    """Load and fail-closed validate the frozen batch-frame evidence manifest."""

    source_path = Path(source).expanduser().resolve()
    manifest, manifest_raw = _base._load_strict_json_mapping(source_path)
    _base._expect_equal(
        manifest.get("schema_version"),
        D1_ONLINE_BATCH_FRAME_EVIDENCE_SCHEMA_VERSION,
        "batch-frame evidence manifest schema_version",
    )
    _base._expect_equal(
        manifest.get("experiment_id"),
        D1_ONLINE_BATCH_FRAME_EXPERIMENT_ID,
        "batch-frame evidence experiment_id",
    )
    _base._expect_equal(
        manifest.get("required_d6_evaluator_schema_version"),
        D1_ONLINE_BATCH_FRAME_MULTISEED_EVALUATION_SCHEMA_VERSION,
        "batch-frame evidence required D6 evaluator schema",
    )
    _base._expect_equal(
        manifest.get(
            "online_batch_frame_diagnostics_schema_version"
        ),
        D1_ONLINE_BATCH_FRAME_DIAGNOSTICS_SCHEMA_VERSION,
        "batch-frame evidence diagnostics schema",
    )
    if manifest.get("status") != "episodes_complete_pending_d6":
        raise D1OnlineBatchFrameEvidenceError(
            "batch-frame evidence status must be episodes_complete_pending_d6"
        )
    _base._required_text(
        manifest.get("completed_at_utc"),
        "batch-frame evidence completed_at_utc",
    )
    source_commit = _base._required_commit(
        manifest.get("source_commit"),
        "batch-frame evidence source_commit",
    )
    _base._expect_equal(
        source_commit,
        D1_ONLINE_BATCH_FRAME_SOURCE_COMMIT,
        "batch-frame evidence frozen source_commit",
    )
    if manifest.get("source_repository_dirty") is not False:
        raise D1OnlineBatchFrameEvidenceError(
            "batch-frame evidence source_repository_dirty must be false"
        )
    source_worktree = _base._explicit_path(
        manifest.get("source_worktree"),
        "batch-frame evidence source_worktree",
        require=None,
    )
    output_root = _base._explicit_path(
        manifest.get("output_root"),
        "batch-frame evidence output_root",
        require="directory",
    )
    if source_path.parent != output_root:
        raise D1OnlineBatchFrameEvidenceError(
            "batch-frame evidence_manifest.json must be directly under output_root"
        )

    matrix_path = _base._explicit_path(
        manifest.get("matrix_path"),
        "batch-frame evidence matrix_path",
        require="file",
    )
    matrix_sha256 = _base._required_sha256(
        manifest.get("matrix_sha256"),
        "batch-frame evidence matrix_sha256",
    )
    if matrix_sha256 != _base._file_sha256(matrix_path):
        raise D1OnlineBatchFrameEvidenceError(
            "batch-frame matrix_sha256 does not match matrix_path bytes"
        )
    if matrix_sha256 != D1_ONLINE_BATCH_FRAME_MATRIX_SHA256:
        raise D1OnlineBatchFrameEvidenceError(
            "batch-frame matrix_sha256 does not match the frozen matrix"
        )
    matrix, _ = _base._load_strict_json_mapping(matrix_path)
    _validate_matrix(matrix)
    embedded_matrix = _base._required_mapping(
        manifest.get("matrix"),
        "batch-frame embedded matrix",
    )
    if embedded_matrix != matrix:
        raise D1OnlineBatchFrameEvidenceError(
            "batch-frame embedded matrix does not exactly match matrix_path"
        )

    raw_cases = _base._required_sequence(
        manifest.get("cases"),
        "batch-frame evidence cases",
    )
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise D1OnlineBatchFrameEvidenceError(
            "batch-frame evidence manifest must contain exactly 13 cases"
        )
    pairs: list[_base.D1PublicationMetadataPairBinding] = []
    used_paths: set[Path] = {source_path}
    for raw_case, expected_case in zip(
        raw_cases,
        _EXPECTED_CASES,
        strict=True,
    ):
        case = _base._required_mapping(
            raw_case,
            "batch-frame evidence case",
        )
        metadata = _base._case_metadata(case)
        if metadata != expected_case:
            raise D1OnlineBatchFrameEvidenceError(
                "batch-frame evidence case differs from preregistration: "
                f"expected {expected_case!r}, got {metadata!r}"
            )
        case_id, group, seed, duration_s, arm_order = metadata
        if case.get("d6_evaluation_status") != (
            "episodes_complete_pending_d6"
        ):
            raise D1OnlineBatchFrameEvidenceError(
                f"{case_id} d6_evaluation_status is not pending D6"
            )
        raw_arms = _base._required_mapping(
            case.get("arms"),
            f"{case_id} arms",
        )
        if set(raw_arms) != set(_ARMS):
            raise D1OnlineBatchFrameEvidenceError(
                f"{case_id} arms must be reference and candidate"
            )
        bindings: dict[str, _base.D1PublicationMetadataArmBinding] = {}
        commands: dict[str, list[str]] = {}
        for arm in _ARMS:
            record = _base._required_mapping(
                raw_arms.get(arm),
                f"{case_id} {arm} arm",
            )
            implementation = _IMPLEMENTATIONS[arm]
            _base._expect_equal(
                record.get("arm"),
                arm,
                f"{case_id} arm label",
            )
            _base._expect_equal(
                record.get("expected_implementation"),
                implementation,
                f"{case_id} {arm} expected implementation",
            )
            _base._expect_equal(
                record.get("expected_d1_implementation_id"),
                _IMPLEMENTATION_IDS[arm],
                f"{case_id} {arm} expected implementation_id",
            )
            _base._expect_equal(
                record.get("validation_kind"),
                _VALIDATION_KIND,
                f"{case_id} {arm} validation_kind",
            )
            _base._expect_equal(
                record.get("expected_commit"),
                source_commit,
                f"{case_id} {arm} expected commit",
            )
            if record.get("status") != "complete":
                raise D1OnlineBatchFrameEvidenceError(
                    f"{case_id} {arm} status must be complete"
                )
            if record.get("reused", False) is not False:
                raise D1OnlineBatchFrameEvidenceError(
                    f"{case_id} {arm} must be a fresh arm"
                )
            if any(
                field in record
                for field in (
                    "reused_from",
                    "source_episode_dir",
                    "prior_episode_dir",
                )
            ):
                raise D1OnlineBatchFrameEvidenceError(
                    f"{case_id} {arm} contains a reuse marker"
                )
            return_code = record.get("return_code")
            if (
                not isinstance(return_code, int)
                or isinstance(return_code, bool)
                or return_code != 0
            ):
                raise D1OnlineBatchFrameEvidenceError(
                    f"{case_id} {arm} return_code must be integer zero"
                )
            episode_dir = _base._explicit_path(
                record.get("episode_dir"),
                f"{case_id} {arm} episode_dir",
                require="directory",
            )
            resource_path = _base._explicit_path(
                record.get("resource_path"),
                f"{case_id} {arm} resource_path",
                require="file",
            )
            stdout_path = _base._explicit_path(
                record.get("stdout_path"),
                f"{case_id} {arm} stdout_path",
                require="file",
            )
            stderr_path = _base._explicit_path(
                record.get("stderr_path"),
                f"{case_id} {arm} stderr_path",
                require="file",
            )
            for path, label in (
                (episode_dir, "episode_dir"),
                (resource_path, "resource_path"),
                (stdout_path, "stdout_path"),
                (stderr_path, "stderr_path"),
            ):
                _base._require_under_root(
                    path,
                    output_root,
                    f"{case_id} {arm} {label}",
                )
                if path in used_paths:
                    raise D1OnlineBatchFrameEvidenceError(
                        f"duplicate batch-frame evidence path: {path}"
                    )
                used_paths.add(path)
            command = [
                _base._required_text(
                    item,
                    f"{case_id} {arm} command item",
                )
                for item in _base._required_sequence(
                    record.get("command"),
                    f"{case_id} {arm} command",
                )
            ]
            expected_command = _expected_command(
                source_worktree=source_worktree,
                implementation=implementation,
                duration_s=duration_s,
                seed=seed,
                episode_dir=episode_dir,
            )
            if command != expected_command:
                raise D1OnlineBatchFrameEvidenceError(
                    f"{case_id} {arm} command differs from frozen matrix"
                )
            commands[arm] = command
            bindings[arm] = _base.D1PublicationMetadataArmBinding(
                arm=arm,
                implementation=implementation,
                episode_dir=episode_dir,
                resource_path=resource_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        _validate_pair_command_isolation(commands, case_id)
        pairs.append(
            _base.D1PublicationMetadataPairBinding(
                case_id=case_id,
                group=group,
                seed=seed,
                duration_s=duration_s,
                arm_order=arm_order,
                arms=bindings,
            )
        )
    if len(pairs) * len(_ARMS) != 26:
        raise D1OnlineBatchFrameEvidenceError(
            "batch-frame evidence must bind exactly 26 fresh arms"
        )

    return D1OnlineBatchFrameEvidence(
        source_path=source_path,
        source_sha256=_base._sha256_bytes(manifest_raw),
        matrix_path=matrix_path,
        matrix_sha256=matrix_sha256,
        matrix=matrix,
        output_root=output_root,
        source_commit=source_commit,
        source_worktree=source_worktree,
        pairs=pairs,
    )


def evaluate_d1_online_batch_frame_multiseed(
    source: str | Path,
    *,
    raise_on_invalid: bool = False,
) -> dict[str, Any]:
    """Evaluate the frozen matrix or return an unavailable result."""

    try:
        return _evaluate_d1_online_batch_frame_multiseed_available(
            source
        )
    except D1OnlineBatchFrameEvidenceError as exc:
        if raise_on_invalid:
            raise
        return _unavailable_evaluation(source, str(exc))


def _evaluate_d1_online_batch_frame_multiseed_available(
    source: str | Path,
) -> dict[str, Any]:
    """Strict evaluation path after every evidence check succeeds."""

    evidence = load_d1_online_batch_frame_evidence_manifest(source)
    pairs = [_evaluate_pair(pair, evidence) for pair in evidence.pairs]
    bootstrap_resamples = int(evidence.matrix["bootstrap_resamples"])
    bootstrap_seed = int(evidence.matrix["bootstrap_seed"])
    groups = {
        group: _summarize_group(
            [pair for pair in pairs if pair["group"] == group],
            group=group,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_seed=bootstrap_seed,
        )
        for group in _GROUPS
    }
    diagnostics_aggregate = _aggregate_batch_frame_diagnostics(pairs)
    thresholds = copy.deepcopy(
        dict(evidence.matrix["admission_gates"])
    )
    gates = _admission_gates(
        pairs,
        groups,
        diagnostics_aggregate,
        thresholds,
    )
    admitted = all(bool(gate["passed"]) for gate in gates.values())
    blockers = [
        {
            "gate": name,
            "actual": gate["actual"],
            "threshold": gate["threshold"],
            "comparator": gate["comparator"],
            "reason": gate["reason"],
        }
        for name, gate in gates.items()
        if gate["passed"] is not True
    ]
    realtime_gate = _base._system_realtime_gate(pairs)
    return {
        "schema_version": (
            D1_ONLINE_BATCH_FRAME_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": D1_ONLINE_BATCH_FRAME_EVALUATION_DATE,
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "availability": {
            "available": True,
            "reason": None,
        },
        "input_contract": {
            "evidence_manifest_path": str(evidence.source_path),
            "evidence_manifest_sha256": evidence.source_sha256,
            "evidence_manifest_schema_version": (
                D1_ONLINE_BATCH_FRAME_EVIDENCE_SCHEMA_VERSION
            ),
            "evidence_manifest_status": "episodes_complete_pending_d6",
            "matrix_path": str(evidence.matrix_path),
            "matrix_sha256": evidence.matrix_sha256,
            "matrix_schema_version": (
                D1_ONLINE_BATCH_FRAME_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": D1_ONLINE_BATCH_FRAME_EXPERIMENT_ID,
            "output_root": str(evidence.output_root),
            "source_commit": evidence.source_commit,
            "source_repository_dirty": False,
            "same_commit_for_both_arms": True,
            "arm_implementations": dict(_IMPLEMENTATIONS),
            "arm_implementation_ids": dict(_IMPLEMENTATION_IDS),
            "batch_frame_diagnostics_schema_version": (
                D1_ONLINE_BATCH_FRAME_DIAGNOSTICS_SCHEMA_VERSION
            ),
            "pair_count": len(pairs),
            "arm_count": len(pairs) * 2,
            "bootstrap_resamples": bootstrap_resamples,
            "bootstrap_rng_seed": bootstrap_seed,
            "evidence_boundary": copy.deepcopy(_EXPECTED_BOUNDARY),
        },
        "scope": {
            "simulation_mode": "three_dimensional_point_mass",
            "airsim_evidence": False,
            "hardware_evidence": False,
            "target_count": _TARGET_COUNT,
            "resource_count": _RESOURCE_COUNT,
            "recon_count": _RECON_COUNT,
            "short_seeds": list(_SHORT_SEEDS),
            "long_seeds": list(_LONG_SEEDS),
            "short_duration_s": _SHORT_DURATION_S,
            "long_duration_s": _LONG_DURATION_S,
            "truth_is_online_control_input": False,
            "semantic_equivalence_generated_by_d6": True,
            "allowed_cross_build_check_exclusion": "same_runtime_profile",
            "normalized_treatment_fields": [
                "d1_online_batch_frame_implementation",
                "d1_online_batch_frame_execution_config",
                "d1_online_batch_frame_diagnostics",
                "treatment-derived episode identity",
                "stage and episode performance fields",
            ],
            "assignment_plan_semantic_normalization": {
                "opaque_plan_identity": "first_seen_lineage_token",
                "opaque_source_hashes": (
                    "normalized_only_after_in_run_source_binding_validation"
                ),
                "assignment_business_content_ignored": False,
                "authorization_state_ignored": False,
                "target_resource_binding_ignored": False,
                "state_machine_and_safety_results_ignored": False,
            },
        },
        "thresholds": thresholds,
        "pairs": pairs,
        "groups": groups,
        "batch_frame_diagnostics_aggregate": diagnostics_aggregate,
        "admission_gates": gates,
        "admission_blockers": blockers,
        "optimization_admitted": admitted,
        "system_realtime_gate": realtime_gate,
        "system_realtime_gap_closed": bool(realtime_gate["passed"]),
    }


def _unavailable_evaluation(
    source: str | Path,
    reason: str,
) -> dict[str, Any]:
    source_path = Path(source).expanduser().resolve()
    unavailable_gate = _gate(
        actual=False,
        threshold=True,
        comparator="==",
        passed=False,
        reason="evidence_unavailable",
    )
    return {
        "schema_version": (
            D1_ONLINE_BATCH_FRAME_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": D1_ONLINE_BATCH_FRAME_EVALUATION_DATE,
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "availability": {
            "available": False,
            "reason": reason,
        },
        "input_contract": {
            "evidence_manifest_path": str(source_path),
            "matrix_sha256": D1_ONLINE_BATCH_FRAME_MATRIX_SHA256,
            "matrix_schema_version": (
                D1_ONLINE_BATCH_FRAME_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": D1_ONLINE_BATCH_FRAME_EXPERIMENT_ID,
            "source_commit": D1_ONLINE_BATCH_FRAME_SOURCE_COMMIT,
            "arm_implementations": dict(_IMPLEMENTATIONS),
            "arm_implementation_ids": dict(_IMPLEMENTATION_IDS),
        },
        "scope": {
            "simulation_mode": "three_dimensional_point_mass",
            "airsim_evidence": False,
            "target_count": _TARGET_COUNT,
            "resource_count": _RESOURCE_COUNT,
            "recon_count": _RECON_COUNT,
            "pair_count": 0,
            "arm_count": 0,
        },
        "thresholds": copy.deepcopy(_EXPECTED_GATES),
        "pairs": [],
        "groups": {},
        "batch_frame_diagnostics_aggregate": {},
        "admission_gates": {
            "evidence_available": unavailable_gate,
        },
        "admission_blockers": [
            {
                "gate": "evidence_available",
                "actual": False,
                "threshold": True,
                "comparator": "==",
                "reason": "evidence_unavailable",
            }
        ],
        "optimization_admitted": False,
        "system_realtime_gate": {
            "available": False,
            "passed": False,
            "reason": "evidence_unavailable",
            "candidate_minimum_real_time_factor": None,
            "threshold": 1.0,
        },
        "system_realtime_gap_closed": False,
    }


def _validate_matrix(matrix: Mapping[str, Any]) -> None:
    if set(matrix) != _EXPECTED_MATRIX_KEYS:
        raise D1OnlineBatchFrameEvidenceError(
            "batch-frame matrix top-level fields differ from frozen contract"
        )
    expected_scalars = (
        ("schema_version", D1_ONLINE_BATCH_FRAME_MATRIX_SCHEMA_VERSION),
        ("experiment_id", D1_ONLINE_BATCH_FRAME_EXPERIMENT_ID),
        ("same_clean_commit_required", True),
        ("target_count", _TARGET_COUNT),
        ("resource_count", _RESOURCE_COUNT),
        ("recon_count", _RECON_COUNT),
        ("cooldown_s", 2.0),
        ("bootstrap_seed", _BOOTSTRAP_RNG_SEED),
        ("bootstrap_resamples", _BOOTSTRAP_RESAMPLES),
    )
    for field, expected in expected_scalars:
        _base._expect_equal(
            matrix.get(field),
            expected,
            f"batch-frame matrix {field}",
        )
    _base._expect_equal(
        matrix.get("arm_implementations"),
        _IMPLEMENTATIONS,
        "batch-frame matrix arm_implementations",
    )
    _base._expect_equal(
        tuple(
            _base._required_text(item, "batch-frame matrix run flag")
            for item in _base._required_sequence(
                matrix.get("run_flags"),
                "batch-frame matrix run_flags",
            )
        ),
        _RUN_FLAGS,
        "batch-frame matrix run_flags",
    )
    raw_cases = _base._required_sequence(
        matrix.get("cases"),
        "batch-frame matrix cases",
    )
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise D1OnlineBatchFrameEvidenceError(
            "batch-frame matrix must contain exactly 13 cases"
        )
    for raw_case, expected_case in zip(
        raw_cases,
        _EXPECTED_CASES,
        strict=True,
    ):
        case = _base._required_mapping(raw_case, "batch-frame matrix case")
        if set(case) != {
            "case_id",
            "group",
            "seed",
            "duration_s",
            "arm_order",
        }:
            raise D1OnlineBatchFrameEvidenceError(
                "batch-frame matrix case fields differ from frozen contract"
            )
        if _base._case_metadata(case) != expected_case:
            raise D1OnlineBatchFrameEvidenceError(
                "batch-frame matrix case differs from frozen order"
            )
    _base._expect_equal(
        _base._required_mapping(
            matrix.get("admission_gates"),
            "batch-frame matrix admission_gates",
        ),
        _EXPECTED_GATES,
        "batch-frame matrix admission_gates",
    )
    _base._expect_equal(
        _base._required_mapping(
            matrix.get("evidence_boundary"),
            "batch-frame matrix evidence_boundary",
        ),
        _EXPECTED_BOUNDARY,
        "batch-frame matrix evidence_boundary",
    )


def _expected_command(
    *,
    source_worktree: Path,
    implementation: str,
    duration_s: float,
    seed: int,
    episode_dir: Path,
) -> list[str]:
    return [
        "python3",
        str(
            source_worktree
            / "research_modules"
            / "scalable_3d_simulation"
            / "run_episode.py"
        ),
        *_RUN_FLAGS,
        "--d1-online-batch-frame-implementation",
        implementation,
        "--duration",
        format(duration_s, ".15g"),
        "--seed",
        str(seed),
        "--drone-count",
        str(_RESOURCE_COUNT),
        "--target-count",
        str(_TARGET_COUNT),
        "--recon-count",
        str(_RECON_COUNT),
        "--output",
        str(episode_dir),
    ]


def _validate_pair_command_isolation(
    commands: Mapping[str, Sequence[str]],
    case_id: str,
) -> None:
    reference = list(commands[_REFERENCE_ARM])
    candidate = list(commands[_CANDIDATE_ARM])
    if len(reference) != len(candidate):
        raise D1OnlineBatchFrameEvidenceError(
            f"{case_id} arm command lengths differ"
        )
    selector_index = reference.index(
        "--d1-online-batch-frame-implementation"
    ) + 1
    output_index = reference.index("--output") + 1
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index in {selector_index, output_index}:
            continue
        if left != right:
            raise D1OnlineBatchFrameEvidenceError(
                f"{case_id} commands differ outside treatment/output"
            )


def _evaluate_pair(
    pair: _base.D1PublicationMetadataPairBinding,
    evidence: D1OnlineBatchFrameEvidence,
) -> dict[str, Any]:
    reference = _evaluate_arm(
        pair.arms[_REFERENCE_ARM],
        pair=pair,
        expected_commit=evidence.source_commit,
    )
    candidate = _evaluate_arm(
        pair.arms[_CANDIDATE_ARM],
        pair=pair,
        expected_commit=evidence.source_commit,
    )
    semantic = _compare_pair_business_semantics(reference, candidate)
    reference.pop("_semantic_input", None)
    candidate.pop("_semantic_input", None)
    batch_frame_pair = _validate_pair_batch_frame_workload(
        reference["batch_frame_diagnostics"],
        candidate["batch_frame_diagnostics"],
        context=pair.case_id,
    )
    performance = {
        metric: _base._compare_pair_metric(
            reference["metrics"][metric],
            candidate["metrics"][metric],
            lower_is_better=metric in _LOWER_IS_BETTER,
        )
        for metric in _METRICS
    }
    return {
        "case_id": pair.case_id,
        "group": pair.group,
        "seed": pair.seed,
        "duration_s": pair.duration_s,
        "arm_order": list(pair.arm_order),
        "reference": reference,
        "candidate": candidate,
        "business_semantics": semantic,
        "business_semantics_passed": bool(semantic["passed"]),
        "finite_state_passed": (
            bool(reference["finite_state"])
            and bool(candidate["finite_state"])
        ),
        "truth_isolation_passed": (
            reference["online_truth_use_count"] == 0
            and candidate["online_truth_use_count"] == 0
        ),
        "implementation_identity_passed": (
            bool(reference["implementation_identity_passed"])
            and bool(candidate["implementation_identity_passed"])
        ),
        "online_batch_frame_audit": batch_frame_pair,
        "online_batch_frame_audit_passed": bool(batch_frame_pair["passed"]),
        "performance": performance,
    }


def _evaluate_arm(
    binding: _base.D1PublicationMetadataArmBinding,
    *,
    pair: _base.D1PublicationMetadataPairBinding,
    expected_commit: str,
) -> dict[str, Any]:
    context = f"{pair.case_id} {binding.arm}"
    episode = binding.episode_dir
    stderr_audit = _base._validate_stderr(binding.stderr_path, context)
    paths = {
        name: episode / name for name in _base._CONSUMED_EPISODE_FILES
    }
    for name, path in paths.items():
        if not path.is_file():
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} missing {name}"
            )
    manifest, manifest_raw = _base._load_strict_json_mapping(
        paths["manifest.json"]
    )
    config, config_raw = _base._load_strict_json_mapping(
        paths["scenario_config.json"]
    )
    summary, summary_raw = _base._load_strict_json_mapping(
        paths["summary.json"]
    )
    governance, governance_raw = _base._load_strict_json_mapping(
        paths["observation_governance_audit.json"]
    )
    runtime_profile = _validate_arm_provenance(
        binding,
        pair=pair,
        expected_commit=expected_commit,
        manifest=manifest,
        config=config,
        summary=summary,
        governance=governance,
    )
    diagnostics, batch_frame_audit = _validate_implementation_identity(
        binding.arm,
        binding.implementation,
        runtime_profile=runtime_profile,
        summary=summary,
        governance=governance,
        context=context,
    )
    stages = {
        name: _base._load_stage(paths["stage_timings.csv"], stage_name)
        for name, stage_name in {
            "d1_fusion": "module.d1_fusion",
            "d1_scan_input": "module.d1_scan_input",
            "d2_association": "module.d2_association",
            "d3_assignment": "module.d3_assignment",
            "d5_active_vision": "module.d5_active_vision",
            "d7_guidance": "module.d7_guidance",
            "module_publication_bus": "module_publication_bus",
        }.items()
    }
    resource = _base._load_resource_metrics(binding.resource_path)
    _base._strict_jsonl_digest(paths["online_observations.jsonl"])
    _base._strict_jsonl_digest(paths["offline_truth_labels.jsonl"])
    _base._strict_jsonl_digest(
        paths["offline_proximity_intercepts.jsonl"]
    )
    _base._validate_truth_state_finite(paths["offline_truth_state.npz"])
    metrics = {
        "d1_fusion_wall_s": stages["d1_fusion"]["wall_time_s"],
        "d1_fusion_p50_ms": stages["d1_fusion"]["p50_wall_time_ms"],
        "d1_fusion_p95_ms": stages["d1_fusion"]["p95_wall_time_ms"],
        "d1_fusion_max_ms": stages["d1_fusion"]["max_wall_time_ms"],
        "d1_scan_input_wall_s": stages["d1_scan_input"]["wall_time_s"],
        "d2_association_wall_s": stages["d2_association"]["wall_time_s"],
        "d3_assignment_wall_s": stages["d3_assignment"]["wall_time_s"],
        "d5_active_vision_wall_s": stages[
            "d5_active_vision"
        ]["wall_time_s"],
        "d7_guidance_wall_s": stages["d7_guidance"]["wall_time_s"],
        "module_publication_bus_wall_s": stages[
            "module_publication_bus"
        ]["wall_time_s"],
        "core_wall_s": _base._finite_nonnegative(
            summary.get("wall_time_s"),
            f"{context} summary wall_time_s",
            positive=True,
        ),
        "external_elapsed_s": resource["external_elapsed_s"],
        "maximum_rss_kib": resource["maximum_rss_kib"],
        "real_time_factor": _base._finite_nonnegative(
            summary.get("real_time_factor"),
            f"{context} summary real_time_factor",
        ),
    }
    input_sha256 = {
        "manifest.json": _base._sha256_bytes(manifest_raw),
        "scenario_config.json": _base._sha256_bytes(config_raw),
        "summary.json": _base._sha256_bytes(summary_raw),
        "observation_governance_audit.json": _base._sha256_bytes(
            governance_raw
        ),
        "stage_timings.csv": _base._file_sha256(paths["stage_timings.csv"]),
        "online_observations.jsonl": _base._file_sha256(
            paths["online_observations.jsonl"]
        ),
        "offline_truth_state.npz": _base._file_sha256(
            paths["offline_truth_state.npz"]
        ),
        "offline_truth_labels.jsonl": _base._file_sha256(
            paths["offline_truth_labels.jsonl"]
        ),
        "offline_proximity_intercepts.jsonl": _base._file_sha256(
            paths["offline_proximity_intercepts.jsonl"]
        ),
        "resource_usage": _base._file_sha256(binding.resource_path),
    }
    return {
        "arm": binding.arm,
        "expected_implementation": binding.implementation,
        "episode_dir": str(binding.episode_dir),
        "resource_path": str(binding.resource_path),
        "git_commit": manifest["git_commit"],
        "repository_dirty": manifest["repository_dirty"],
        "config_sha256": manifest["config_sha256"],
        "runtime_profile_sha256": manifest["runtime_profile_sha256"],
        "normalized_runtime_profile_sha256": _base._canonical_sha256(
            _normalized_runtime_profile(runtime_profile)
        ),
        "normalized_summary_sha256": _base._canonical_sha256(
            _normalized_summary(summary)
        ),
        "normalized_governance_sha256": _base._canonical_sha256(
            _normalized_governance(governance)
        ),
        "finite_state": summary["finite_state"],
        "online_truth_use_count": summary["online_truth_use_count"],
        "implementation_identity_passed": True,
        "implementation_identity_locations": (
            _implementation_identity_locations(
                runtime_profile,
                summary,
                governance,
            )
        ),
        "batch_frame_diagnostics": diagnostics,
        "batch_frame_audit": batch_frame_audit,
        "stage_timings": stages,
        "resource_metrics": resource,
        "stderr_audit": stderr_audit,
        "metrics": metrics,
        "input_file_sha256": input_sha256,
        "_semantic_input": {
            "episode_dir": binding.episode_dir,
            "config": config,
        },
    }


def _validate_arm_provenance(
    binding: _base.D1PublicationMetadataArmBinding,
    *,
    pair: _base.D1PublicationMetadataPairBinding,
    expected_commit: str,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> Mapping[str, Any]:
    context = f"{pair.case_id} {binding.arm}"
    if manifest.get("git_commit") != expected_commit:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} source commit mismatch"
        )
    if manifest.get("repository_dirty") is not False:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} repository is dirty"
        )
    if manifest.get("scenario_schema") != _EXPECTED_CONFIG_SCHEMA_VERSION:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} manifest scenario schema mismatch"
        )
    if manifest.get("runtime_profile_schema") != (
        _EXPECTED_RUNTIME_PROFILE_SCHEMA_VERSION
    ):
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} manifest runtime profile schema mismatch"
        )
    if config.get("schema_version") != _EXPECTED_CONFIG_SCHEMA_VERSION:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} scenario config schema mismatch"
        )
    if governance.get("schema_version") != (
        _EXPECTED_GOVERNANCE_SCHEMA_VERSION
    ):
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} governance schema mismatch"
        )
    if manifest.get("config_sha256") != _base._canonical_sha256(config):
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} config_sha256 mismatch"
        )
    runtime_profile = _base._required_mapping(
        manifest.get("runtime_profile"),
        f"{context} runtime_profile",
    )
    if manifest.get("runtime_profile_sha256") != _base._canonical_sha256(
        runtime_profile
    ):
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} runtime_profile_sha256 mismatch"
        )
    if runtime_profile.get("schema_version") != (
        _EXPECTED_RUNTIME_PROFILE_SCHEMA_VERSION
    ):
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} runtime profile schema mismatch"
        )
    for mapping, label, field, expected in (
        (manifest, "manifest", "seed", pair.seed),
        (config, "config", "seed", pair.seed),
        (summary, "summary", "seed", pair.seed),
        (config, "config", "target_count", _TARGET_COUNT),
        (summary, "summary", "target_count", _TARGET_COUNT),
        (config, "config", "resource_count", _RESOURCE_COUNT),
        (summary, "summary", "resource_count", _RESOURCE_COUNT),
        (config, "config", "recon_count", _RECON_COUNT),
        (summary, "summary", "recon_count", _RECON_COUNT),
    ):
        if mapping.get(field) != expected:
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} {label} {field} mismatch"
            )
    _base._expect_finite_equal(
        config.get("duration_s"),
        pair.duration_s,
        f"{context} config duration_s",
    )
    _base._expect_finite_equal(
        summary.get("simulated_duration_s"),
        pair.duration_s,
        f"{context} summary simulated_duration_s",
    )
    if summary.get("finite_state") is not True:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} finite_state must be true"
        )
    if summary.get("online_truth_use_count") != 0:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} online_truth_use_count must be zero"
        )
    if governance.get("online_truth_use_count") != 0:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} governance online truth count must be zero"
        )
    return runtime_profile


def _validate_implementation_identity(
    arm: str,
    expected: str,
    *,
    runtime_profile: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
    context: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    configuration = _base._required_mapping(
        runtime_profile.get("configuration"),
        f"{context} runtime configuration",
    )
    final = _base._required_mapping(
        summary.get("module_final_diagnostics"),
        f"{context} module_final_diagnostics",
    )
    nested_governance = _base._required_mapping(
        final.get("observation_governance"),
        f"{context} nested observation_governance",
    )
    selector_field = "d1_online_batch_frame_implementation"
    config_field = "d1_online_batch_frame_execution_config"
    diagnostics_field = "d1_online_batch_frame_diagnostics"
    selectors = {
        "manifest.runtime_profile": runtime_profile.get(selector_field),
        "manifest.runtime_profile.configuration": configuration.get(
            selector_field
        ),
        "summary": summary.get(selector_field),
        "summary.module_final_diagnostics": final.get(selector_field),
        "summary.module_final.observation_governance": (
            nested_governance.get(selector_field)
        ),
        "governance": governance.get(selector_field),
    }
    mismatches = [
        f"{name}={value!r}"
        for name, value in selectors.items()
        if value != expected
    ]
    if mismatches:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} batch-frame implementation identity mismatch: "
            + ", ".join(mismatches)
        )
    execution_config_locations = {
        "manifest.runtime_profile": _base._required_mapping(
            runtime_profile.get(config_field),
            f"{context} runtime execution config",
        ),
        "summary": _base._required_mapping(
            summary.get(config_field),
            f"{context} summary execution config",
        ),
        "module_final_diagnostics": _base._required_mapping(
            final.get(config_field),
            f"{context} final execution config",
        ),
        "module_final_observation_governance": _base._required_mapping(
            nested_governance.get(config_field),
            f"{context} nested execution config",
        ),
        "observation_governance_audit": _base._required_mapping(
            governance.get(config_field),
            f"{context} governance execution config",
        ),
    }
    canonical_config = execution_config_locations["manifest.runtime_profile"]
    for name, execution_config in execution_config_locations.items():
        if execution_config != canonical_config:
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} execution config mismatch at {name}"
            )
    _validate_execution_config(
        canonical_config,
        expected=expected,
        expected_id=_IMPLEMENTATION_IDS[arm],
        context=context,
    )
    diagnostics_locations = {
        "summary": _base._required_mapping(
            summary.get(diagnostics_field),
            f"{context} summary batch-frame diagnostics",
        ),
        "module_final_diagnostics": _base._required_mapping(
            final.get(diagnostics_field),
            f"{context} final batch-frame diagnostics",
        ),
        "module_final_observation_governance": _base._required_mapping(
            nested_governance.get(diagnostics_field),
            f"{context} nested governance batch-frame diagnostics",
        ),
        "observation_governance_audit": _base._required_mapping(
            governance.get(diagnostics_field),
            f"{context} governance batch-frame diagnostics",
        ),
    }
    canonical = diagnostics_locations["summary"]
    for name, diagnostics in diagnostics_locations.items():
        if diagnostics != canonical:
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} batch-frame diagnostics mismatch at {name}"
            )
    normalized, audit = _validate_final_diagnostics(
        canonical,
        arm=arm,
        context=context,
    )
    return normalized, {
        **audit,
        "execution_config_lineage_passed": True,
        "execution_config_surface_count": len(execution_config_locations),
        "four_persisted_diagnostics_equal": True,
        "persisted_diagnostics_surface_count": len(diagnostics_locations),
        "selector_surface_count": len(selectors),
    }


def _validate_execution_config(
    execution_config: Mapping[str, Any],
    *,
    expected: str,
    expected_id: str,
    context: str,
) -> None:
    required = {
        "schema_version": D1_ONLINE_BATCH_FRAME_DIAGNOSTICS_SCHEMA_VERSION,
        "implementation": expected,
        "implementation_id": expected_id,
        "candidate_default_enabled": False,
        "candidate_contract": (
            "full_raw_batch_identity_check_then_structural_eligibility_"
            "check_then_deep_snapshot_then_full_readonly_frame_check"
        ),
        "public_validation_bypass_available": False,
        "raw_source_absolute_immutability_claimed": False,
    }
    if dict(execution_config) != required:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} batch-frame execution config mismatch"
        )


def _validate_final_diagnostics(
    diagnostics: Mapping[str, Any],
    *,
    arm: str,
    context: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_candidate = arm == _CANDIDATE_ARM
    required_fields = {
        "schema_version",
        "implementation",
        "implementation_id",
        "candidate_default_enabled",
        "candidate_contract",
        "public_validation_bypass_available",
        "raw_source_absolute_immutability_claimed",
        "conservation",
        "operation_counts",
    }
    if set(diagnostics) != required_fields:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} batch-frame diagnostics fields mismatch"
        )
    _validate_execution_config(
        {key: diagnostics[key] for key in required_fields - {
            "conservation", "operation_counts"
        }},
        expected=_IMPLEMENTATIONS[arm],
        expected_id=_IMPLEMENTATION_IDS[arm],
        context=context,
    )
    conservation = _base._required_mapping(
        diagnostics.get("conservation"),
        f"{context} batch-frame conservation",
    )
    expected_conservation = {
        "candidate_never_skips_final_frame_check": True,
        "candidate_path_partition": True,
        "closed_handoff_uses_successful_snapshot": True,
        "closed_payload_snapshot_partition": True,
        "raw_batch_check_accounting": True,
        "reference_path_partition": True,
        "request_partition": True,
        "result_partition": True,
        "snapshot_structure_check_partition": True,
    }
    if dict(conservation) != expected_conservation:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} batch-frame conservation flags mismatch"
        )
    operations_raw = _base._required_mapping(
        diagnostics.get("operation_counts"),
        f"{context} batch-frame operation_counts",
    )
    unknown = set(operations_raw) - _BATCH_FRAME_OPERATION_FIELDS
    if unknown:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} batch-frame operation_counts contain unknown fields: "
            f"{sorted(unknown)}"
        )
    operations = {
        name: _nonnegative_integer(
            operations_raw.get(name, 0),
            f"{context} {name}",
        )
        for name in sorted(_BATCH_FRAME_OPERATION_FIELDS)
    }
    requests = operations["request_count"]
    if requests <= 0:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} request_count must be positive"
        )
    if operations["raw_batch_identity_check_count"] != requests:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} raw batch check accounting failed"
        )
    if operations["successful_build_count"] + operations[
        "rejected_build_count"
    ] != requests:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} result partition failed"
        )
    if expected_candidate:
        if (
            operations["candidate_request_count"] != requests
            or operations["reference_request_count"] != 0
            or operations["reference_path_execution_count"] != 0
        ):
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} candidate request partition failed"
            )
        path_total = sum(
            operations[name]
            for name in (
                "candidate_closed_handoff_count",
                "candidate_reference_fallback_count",
                "candidate_raw_rejection_count",
                "candidate_resource_rejection_count",
            )
        )
        if path_total != requests:
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} candidate path partition failed"
            )
        structure_checks = operations["snapshot_structure_check_count"]
        if structure_checks != requests or sum(
            operations[name]
            for name in (
                "snapshot_structure_eligible_count",
                "snapshot_structure_ineligible_count",
                "snapshot_structure_error_count",
            )
        ) != structure_checks:
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} snapshot structure partition failed"
            )
        attempts = operations["closed_payload_snapshot_attempt_count"]
        if (
            attempts != operations["snapshot_structure_eligible_count"]
            or operations["closed_payload_snapshot_success_count"]
            + operations["closed_payload_snapshot_failure_count"]
            != attempts
            or operations["candidate_closed_handoff_count"]
            != operations["closed_payload_snapshot_success_count"]
        ):
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} closed snapshot partition failed"
            )
    else:
        if (
            operations["reference_request_count"] != requests
            or operations["reference_path_execution_count"] != requests
            or operations["candidate_request_count"] != 0
        ):
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} reference request partition failed"
            )
        candidate_only = _BATCH_FRAME_OPERATION_FIELDS - {
            "request_count",
            "reference_request_count",
            "reference_path_execution_count",
            "successful_build_count",
            "rejected_build_count",
            "raw_batch_identity_check_count",
            "raw_measurement_identity_check_count",
            "measurement_conversion_count",
            "converted_observation_collection_check_count",
            "frame_final_identity_check_count",
            "output_observation_count",
        }
        if any(operations[name] for name in candidate_only):
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} reference reports candidate-only activity"
            )
        if operations["converted_observation_collection_check_count"] != requests:
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} reference converted collection checks mismatch"
            )
        if (
            operations["raw_measurement_identity_check_count"]
            != operations["measurement_conversion_count"]
        ):
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} reference duplicate measurement checks mismatch"
            )
    if operations["frame_final_identity_check_count"] != operations[
        "successful_build_count"
    ]:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} final frame check conservation failed"
        )
    if operations["measurement_conversion_count"] != operations[
        "output_observation_count"
    ]:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} measurement/output conservation failed"
        )
    normalized = {
        **{key: diagnostics[key] for key in required_fields - {
            "operation_counts", "conservation"
        }},
        "conservation": dict(conservation),
        "operation_counts": operations,
    }
    return normalized, {
        "passed": True,
        "request_conservation_passed": True,
        "path_partition_passed": True,
        "snapshot_partition_passed": True,
        "final_frame_check_passed": True,
        "measurement_output_conservation_passed": True,
        "request_count": requests,
        "candidate_closed_handoff_count": operations[
            "candidate_closed_handoff_count"
        ],
        "candidate_reference_fallback_count": operations[
            "candidate_reference_fallback_count"
        ],
        "raw_measurement_identity_check_count": operations[
            "raw_measurement_identity_check_count"
        ],
        "frame_final_identity_check_count": operations[
            "frame_final_identity_check_count"
        ],
    }


def _nonnegative_integer(value: Any, context: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} must be a nonnegative integer"
        )
    return int(value)


def _implementation_identity_locations(
    runtime_profile: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> dict[str, Any]:
    configuration = _base._required_mapping(
        runtime_profile["configuration"],
        "batch-frame runtime profile configuration",
    )
    final = _base._required_mapping(
        summary["module_final_diagnostics"],
        "batch-frame module final diagnostics",
    )
    summary_diagnostics = _base._required_mapping(
        summary["d1_online_batch_frame_diagnostics"],
        "batch-frame summary diagnostics",
    )
    return {
        "manifest_runtime_profile": runtime_profile[
            "d1_online_batch_frame_implementation"
        ],
        "manifest_runtime_configuration": configuration[
            "d1_online_batch_frame_implementation"
        ],
        "summary_top_level": summary[
            "d1_online_batch_frame_implementation"
        ],
        "summary_implementation_id": summary_diagnostics[
            "implementation_id"
        ],
        "module_final": final["d1_online_batch_frame_implementation"],
        "governance_top_level": governance[
            "d1_online_batch_frame_implementation"
        ],
    }


def _validate_pair_batch_frame_workload(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    context: str,
) -> dict[str, Any]:
    reference_ops = _base._required_mapping(
        reference["operation_counts"],
        f"{context} reference batch-frame operation_counts",
    )
    candidate_ops = _base._required_mapping(
        candidate["operation_counts"],
        f"{context} candidate batch-frame operation_counts",
    )
    reference_requests = int(reference_ops["request_count"])
    candidate_requests = int(candidate_ops["request_count"])
    if reference_requests != candidate_requests:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} batch-frame request workloads differ between arms"
        )
    reference_duplicate_checks = (
        int(reference_ops["raw_measurement_identity_check_count"])
        + int(reference_ops["converted_observation_collection_check_count"])
    )
    candidate_duplicate_checks = (
        int(candidate_ops["raw_measurement_identity_check_count"])
        + int(candidate_ops["converted_observation_collection_check_count"])
    )
    if reference_duplicate_checks <= 0:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} reference duplicate-check denominator is zero"
        )
    closed = int(candidate_ops["candidate_closed_handoff_count"])
    fallback = int(candidate_ops["candidate_reference_fallback_count"])
    return {
        "passed": True,
        "same_batch_frame_request_workload": True,
        "reference_request_count": reference_requests,
        "candidate_request_count": candidate_requests,
        "reference_duplicate_check_count": reference_duplicate_checks,
        "candidate_duplicate_check_count": candidate_duplicate_checks,
        "candidate_duplicate_check_reduction_pct": (
            (reference_duplicate_checks - candidate_duplicate_checks)
            / reference_duplicate_checks
            * 100.0
        ),
        "candidate_closed_handoff_count": closed,
        "candidate_reference_fallback_count": fallback,
        "candidate_closed_handoff_ratio_pct": (
            closed / candidate_requests * 100.0
        ),
    }


def _normalized_runtime_profile(
    runtime_profile: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(runtime_profile))
    selector = "d1_online_batch_frame_implementation"
    if selector not in normalized:
        raise D1OnlineBatchFrameEvidenceError(
            "normalized runtime profile lacks batch-frame selector"
        )
    normalized[selector] = _TREATMENT_MARKER
    configuration = _base._mutable_mapping(
        normalized.get("configuration"),
        "normalized runtime configuration",
    )
    if selector not in configuration:
        raise D1OnlineBatchFrameEvidenceError(
            "normalized runtime configuration lacks batch-frame selector"
        )
    configuration[selector] = _TREATMENT_MARKER
    _normalize_batch_frame_fields(normalized, "normalized runtime profile")
    return normalized


def _normalized_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(summary))
    if "episode_id" not in normalized:
        raise D1OnlineBatchFrameEvidenceError(
            "normalized summary lacks episode_id"
        )
    normalized["episode_id"] = _TREATMENT_DERIVED_ID_MARKER
    normalized["wall_time_s"] = _PERFORMANCE_MARKER
    normalized["real_time_factor"] = _PERFORMANCE_MARKER
    _normalize_batch_frame_fields(normalized, "normalized summary")
    final = _base._mutable_mapping(
        normalized.get("module_final_diagnostics"),
        "normalized batch-frame module final",
    )
    _normalize_batch_frame_fields(final, "normalized batch-frame module final")
    if "stage_timings" not in final:
        raise D1OnlineBatchFrameEvidenceError(
            "normalized batch-frame module final lacks stage_timings"
        )
    final["stage_timings"] = _PERFORMANCE_MARKER
    nested = _base._required_mapping(
        final.get("observation_governance"),
        "normalized batch-frame nested governance",
    )
    final["observation_governance"] = _normalized_governance(nested)
    return normalized


def _normalized_governance(
    governance: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(governance))
    _normalize_batch_frame_fields(
        normalized, "normalized batch-frame governance"
    )
    return normalized


def _normalize_batch_frame_fields(
    mapping: dict[str, Any],
    context: str,
) -> None:
    selector = "d1_online_batch_frame_implementation"
    if selector not in mapping:
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} lacks {selector}"
        )
    mapping[selector] = _TREATMENT_MARKER
    execution = mapping.get("d1_online_batch_frame_execution_config")
    if not isinstance(execution, dict):
        raise D1OnlineBatchFrameEvidenceError(
            f"{context} lacks mutable batch-frame execution config"
        )
    mapping["d1_online_batch_frame_execution_config"] = {
        "value": _TREATMENT_MARKER
    }
    if "d1_online_batch_frame_diagnostics" in mapping:
        diagnostics = mapping["d1_online_batch_frame_diagnostics"]
        if not isinstance(diagnostics, dict):
            raise D1OnlineBatchFrameEvidenceError(
                f"{context} has invalid batch-frame diagnostics"
            )
        mapping["d1_online_batch_frame_diagnostics"] = {
            "value": _TREATMENT_MARKER
        }


def _compare_pair_business_semantics(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    reference_input = reference["_semantic_input"]
    candidate_input = candidate["_semantic_input"]
    try:
        cross = compare_cross_build_episodes(
            reference_input["episode_dir"],
            candidate_input["episode_dir"],
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise D1OnlineBatchFrameEvidenceError(
            f"cross-episode semantic audit failed: {exc}"
        ) from exc
    if cross.get("schema_version") != (
        CROSS_BUILD_EQUIVALENCE_SCHEMA_VERSION
    ):
        raise D1OnlineBatchFrameEvidenceError(
            "cross-build reader returned an unsupported schema"
        )
    cross_checks = _base._required_mapping(
        cross.get("checks"),
        "batch-frame cross-build checks",
    )
    required_cross_checks = {
        key: value
        for key, value in cross_checks.items()
        if key != "same_runtime_profile"
    }
    checks = {
        "same_scenario_config": (
            reference["config_sha256"] == candidate["config_sha256"]
            and reference_input["config"] == candidate_input["config"]
        ),
        "normalized_runtime_profile_equal": (
            reference["normalized_runtime_profile_sha256"]
            == candidate["normalized_runtime_profile_sha256"]
        ),
        "normalized_summary_contract_equal": (
            reference["normalized_summary_sha256"]
            == candidate["normalized_summary_sha256"]
        ),
        "normalized_governance_equal": (
            reference["normalized_governance_sha256"]
            == candidate["normalized_governance_sha256"]
        ),
        "cross_build_required_checks_passed": (
            bool(required_cross_checks)
            and all(value is True for value in required_cross_checks.values())
        ),
        "online_payloads_equal": (
            cross_checks.get("normalized_online_payloads_equal") is True
        ),
        "d3_plan_lineage_valid_and_equal": (
            cross_checks.get("reference_plan_lineage_valid") is True
            and cross_checks.get("candidate_plan_lineage_valid") is True
            and cross_checks.get("plan_lineage_pattern_equal") is True
        ),
        "d4_content_address_and_ack_integrity": (
            cross_checks.get("d4_content_address_integrity") is True
            and cross_checks.get("ack_source_integrity") is True
        ),
        "offline_truth_state_equal": (
            cross_checks.get("truth_state_equal") is True
        ),
        "offline_truth_labels_equal": (
            cross_checks.get("truth_labels_semantically_equal") is True
        ),
        "offline_proximity_events_equal": (
            cross_checks.get("proximity_events_semantically_equal") is True
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "batch_frame_treatment_normalization": {
            "scope": (
                "registered_selector_execution_config_diagnostics_counts_"
                "treatment_identity_and_performance_only"
            ),
            "diagnostics_validated_separately": True,
            "other_business_fields_ignored": False,
            "assignment_plan_business_content_ignored": False,
        },
        "assignment_plan_semantic_normalization": {
            "opaque_plan_id_mapping": "first_seen_lineage_token",
            "plan_version_contiguity_validated": True,
            "source_plan_and_guidance_hashes_validated_before_mapping": True,
            "d4_authority_content_addresses_validated_before_mapping": True,
            "assignment_relations_and_target_resource_bindings_compared": True,
            "authorization_state_and_state_machine_results_compared": True,
            "counts_and_safety_results_compared": True,
        },
        "cross_build_runtime_profile_hash_equal": cross_checks.get(
            "same_runtime_profile"
        ),
        "cross_build_checks_excluding_allowed_runtime_hash": (
            required_cross_checks
        ),
        "online_bus": cross.get("online_bus"),
        "truth_artifacts": cross.get("truth_artifacts"),
        "summary_contract": cross.get("summary_contract"),
    }


def _summarize_group(
    pairs: Sequence[Mapping[str, Any]],
    *,
    group: str,
    bootstrap_resamples: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    ordered = sorted(pairs, key=lambda item: int(item["seed"]))
    return {
        "group": group,
        "pair_count": len(ordered),
        "seeds": [int(pair["seed"]) for pair in ordered],
        "business_semantics_pass_count": sum(
            bool(pair["business_semantics_passed"]) for pair in ordered
        ),
        "finite_state_pass_count": sum(
            bool(pair["finite_state_passed"]) for pair in ordered
        ),
        "truth_isolation_pass_count": sum(
            bool(pair["truth_isolation_passed"]) for pair in ordered
        ),
        "implementation_identity_pass_count": sum(
            bool(pair["implementation_identity_passed"])
            for pair in ordered
        ),
        "batch_frame_audit_pass_count": sum(
            bool(pair["online_batch_frame_audit_passed"])
            for pair in ordered
        ),
        "metrics": {
            metric: _summarize_group_metric(
                ordered,
                metric=metric,
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_seed=bootstrap_seed,
            )
            for metric in _METRICS
        },
    }


def _summarize_group_metric(
    pairs: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    bootstrap_resamples: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    comparisons = [pair["performance"][metric] for pair in pairs]
    reference = [float(item["reference"]) for item in comparisons]
    candidate = [float(item["candidate"]) for item in comparisons]
    raw = [float(item["raw_relative_change"]) for item in comparisons]
    improvement = [float(item["improvement"]) for item in comparisons]
    lower, upper = _base._bootstrap_mean_ci(
        raw,
        resamples=bootstrap_resamples,
        rng_seed=bootstrap_seed,
    )
    ratio_of_means_raw = (
        fmean(candidate) - fmean(reference)
    ) / fmean(reference)
    ratio_of_means_improvement = (
        -ratio_of_means_raw
        if metric in _LOWER_IS_BETTER
        else ratio_of_means_raw
    )
    return {
        "metric": metric,
        "direction": (
            "lower_is_better"
            if metric in _LOWER_IS_BETTER
            else "higher_is_better"
        ),
        "pair_count": len(comparisons),
        "reference": _base._distribution(reference),
        "candidate": _base._distribution(candidate),
        "raw_relative_change": {
            **_base._distribution(raw),
            "bootstrap_95_ci": {
                "method": "paired_percentile_mean",
                "lower": lower,
                "upper": upper,
                "resamples": bootstrap_resamples,
                "rng_seed": bootstrap_seed,
            },
        },
        "improvement_pct": {
            key: value * 100.0
            for key, value in _base._distribution(improvement).items()
        },
        "ratio_of_group_means": {
            "raw_relative_change": ratio_of_means_raw,
            "improvement_pct": ratio_of_means_improvement * 100.0,
        },
        "candidate_better_count": sum(
            bool(item["candidate_better"]) for item in comparisons
        ),
        "maximum_pair_raw_relative_change_pct": max(raw) * 100.0,
    }


def _aggregate_batch_frame_diagnostics(
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    for group in (*_GROUPS, "all"):
        selected = (
            list(pairs)
            if group == "all"
            else [pair for pair in pairs if pair["group"] == group]
        )
        arm_totals: dict[str, dict[str, int]] = {}
        for arm in _ARMS:
            totals = {
                name: 0 for name in sorted(_BATCH_FRAME_OPERATION_FIELDS)
            }
            for pair in selected:
                operations = pair[arm]["batch_frame_diagnostics"][
                    "operation_counts"
                ]
                for name in totals:
                    totals[name] += int(operations[name])
            arm_totals[arm] = totals
        reference_duplicate_checks = (
            arm_totals[_REFERENCE_ARM][
                "raw_measurement_identity_check_count"
            ]
            + arm_totals[_REFERENCE_ARM][
                "converted_observation_collection_check_count"
            ]
        )
        candidate_duplicate_checks = (
            arm_totals[_CANDIDATE_ARM][
                "raw_measurement_identity_check_count"
            ]
            + arm_totals[_CANDIDATE_ARM][
                "converted_observation_collection_check_count"
            ]
        )
        candidate_requests = arm_totals[_CANDIDATE_ARM]["request_count"]
        candidate_closed = arm_totals[_CANDIDATE_ARM][
            "candidate_closed_handoff_count"
        ]
        groups[group] = {
            "pair_count": len(selected),
            "arms": arm_totals,
            "candidate_duplicate_check_reduction_pct": (
                (reference_duplicate_checks - candidate_duplicate_checks)
                / reference_duplicate_checks
                * 100.0
            ),
            "candidate_closed_handoff_ratio_pct": (
                candidate_closed
                / candidate_requests
                * 100.0
            ),
            "candidate_reference_fallback_count": sum(
                int(
                    pair[_CANDIDATE_ARM]["batch_frame_diagnostics"][
                        "operation_counts"
                    ]["candidate_reference_fallback_count"]
                ) for pair in selected
            ),
            "reference_duplicate_check_count": reference_duplicate_checks,
            "candidate_duplicate_check_count": candidate_duplicate_checks,
            "candidate_request_count": candidate_requests,
            "candidate_closed_handoff_count": candidate_closed,
        }
    return {
        "schema_version": (
            "d6.d1_online_batch_frame_diagnostics_aggregate.v1"
        ),
        "groups": groups,
    }


def _admission_gates(
    pairs: Sequence[Mapping[str, Any]],
    groups: Mapping[str, Any],
    diagnostics_aggregate: Mapping[str, Any],
    thresholds: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    pair_count = len(pairs)
    short_scan = groups["short"]["metrics"]["d1_scan_input_wall_s"]
    long_scan = groups["long"]["metrics"]["d1_scan_input_wall_s"]
    short_core = groups["short"]["metrics"]["core_wall_s"]
    long_core = groups["long"]["metrics"]["core_wall_s"]
    short_d2 = groups["short"]["metrics"]["d2_association_wall_s"]
    long_d2 = groups["long"]["metrics"]["d2_association_wall_s"]
    rss_groups = [
        groups[group]["metrics"]["maximum_rss_kib"] for group in _GROUPS
    ]
    semantic_count = sum(
        bool(pair["business_semantics_passed"]) for pair in pairs
    )
    finite_count = sum(bool(pair["finite_state_passed"]) for pair in pairs)
    online_truth_use_count = sum(
        int(pair[arm]["online_truth_use_count"])
        for pair in pairs
        for arm in _ARMS
    )
    identity_count = sum(
        bool(pair["implementation_identity_passed"]) for pair in pairs
    )
    batch_frame_audit_count = sum(
        bool(pair["online_batch_frame_audit_passed"]) for pair in pairs
    )
    required_metric_count = sum(
        all(
            metric in pair["performance"]
            and math.isfinite(
                float(pair["performance"][metric]["reference"])
            )
            and math.isfinite(
                float(pair["performance"][metric]["candidate"])
            )
            for metric in _REQUIRED_ADMISSION_METRICS
        )
        for pair in pairs
    )
    short_bootstrap_upper_pct = (
        short_scan["raw_relative_change"]["bootstrap_95_ci"]["upper"]
        * 100.0
    )
    short_d2_increase_pct = (
        short_d2["ratio_of_group_means"]["raw_relative_change"] * 100.0
    )
    long_d2_increase_pct = (
        long_d2["ratio_of_group_means"]["raw_relative_change"] * 100.0
    )
    rss_mean_increase_pct = max(
        summary["ratio_of_group_means"]["raw_relative_change"] * 100.0
        for summary in rss_groups
    )
    maximum_pair_rss_increase_pct = max(
        float(
            pair["performance"]["maximum_rss_kib"][
                "raw_relative_change_pct"
            ]
        )
        for pair in pairs
    )
    diagnostics_all = diagnostics_aggregate["groups"]["all"]
    duplicate_reduction = float(
        diagnostics_all["candidate_duplicate_check_reduction_pct"]
    )
    closed_ratio = float(
        diagnostics_all["candidate_closed_handoff_ratio_pct"]
    )
    fallback_count = int(
        diagnostics_all["candidate_reference_fallback_count"]
    )
    return {
        "all_pairs_business_semantics_equal": _gate(
            actual=semantic_count,
            threshold=pair_count,
            comparator="==",
            passed=(semantic_count == pair_count),
            reason="one_or_more_pair_business_semantics_mismatch",
        ),
        "all_pairs_finite_state": _gate(
            actual=finite_count,
            threshold=pair_count,
            comparator="==",
            passed=(finite_count == pair_count),
            reason="one_or_more_pair_finite_state_check_failed",
        ),
        "all_pairs_online_truth_use_count": _gate(
            actual=online_truth_use_count,
            threshold=thresholds[
                "all_pairs_online_truth_use_count"
            ],
            comparator="==",
            passed=(
                online_truth_use_count
                == thresholds["all_pairs_online_truth_use_count"]
            ),
            reason="one_or_more_arm_online_truth_use_nonzero",
        ),
        "all_pairs_explicit_implementation_identity": _gate(
            actual=identity_count,
            threshold=pair_count,
            comparator="==",
            passed=(identity_count == pair_count),
            reason="one_or_more_arm_implementation_identity_failed",
        ),
        "all_pairs_online_batch_frame_audit_valid": _gate(
            actual=batch_frame_audit_count,
            threshold=pair_count,
            comparator="==",
            passed=(batch_frame_audit_count == pair_count),
            reason="one_or_more_pair_batch_frame_audit_failed",
        ),
        "required_performance_metrics_available": _gate(
            actual=required_metric_count,
            threshold=pair_count,
            comparator="==",
            passed=(required_metric_count == pair_count),
            reason="one_or_more_required_performance_metrics_unavailable",
        ),
        "short_minimum_candidate_faster_count": _gate(
            actual=short_scan["candidate_better_count"],
            threshold=thresholds[
                "short_minimum_candidate_faster_count"
            ],
            comparator=">=",
            passed=(
                short_scan["candidate_better_count"]
                >= thresholds["short_minimum_candidate_faster_count"]
            ),
            reason="short_candidate_faster_count_below_threshold",
        ),
        "short_minimum_scan_input_improvement_pct": _gate(
            actual=short_scan["improvement_pct"]["mean"],
            threshold=thresholds[
                "short_minimum_scan_input_improvement_pct"
            ],
            comparator=">=",
            passed=(
                short_scan["improvement_pct"]["mean"]
                >= thresholds[
                    "short_minimum_scan_input_improvement_pct"
                ]
            ),
            reason="short_scan_input_improvement_below_threshold",
            unit="pct",
        ),
        "short_bootstrap_relative_change_upper_bound_pct": _gate(
            actual=short_bootstrap_upper_pct,
            threshold=thresholds[
                "short_bootstrap_relative_change_upper_bound_pct"
            ],
            comparator="<=",
            passed=(
                short_bootstrap_upper_pct
                <= thresholds[
                    "short_bootstrap_relative_change_upper_bound_pct"
                ]
            ),
            reason="short_bootstrap_upper_bound_above_threshold",
            unit="pct",
        ),
        "long_minimum_candidate_faster_count": _gate(
            actual=long_scan["candidate_better_count"],
            threshold=thresholds[
                "long_minimum_candidate_faster_count"
            ],
            comparator=">=",
            passed=(
                long_scan["candidate_better_count"]
                >= thresholds["long_minimum_candidate_faster_count"]
            ),
            reason="long_candidate_faster_count_below_threshold",
        ),
        "long_minimum_scan_input_improvement_pct": _gate(
            actual=long_scan["improvement_pct"]["mean"],
            threshold=thresholds[
                "long_minimum_scan_input_improvement_pct"
            ],
            comparator=">=",
            passed=(
                long_scan["improvement_pct"]["mean"]
                >= thresholds[
                    "long_minimum_scan_input_improvement_pct"
                ]
            ),
            reason="long_scan_input_improvement_below_threshold",
            unit="pct",
        ),
        "short_minimum_core_wall_improvement_pct": _gate(
            actual=short_core["improvement_pct"]["mean"],
            threshold=thresholds[
                "short_minimum_core_wall_improvement_pct"
            ],
            comparator=">=",
            passed=(
                short_core["improvement_pct"]["mean"]
                >= thresholds[
                    "short_minimum_core_wall_improvement_pct"
                ]
            ),
            reason="short_core_wall_improvement_below_threshold",
            unit="pct",
        ),
        "long_minimum_core_wall_improvement_pct": _gate(
            actual=long_core["improvement_pct"]["mean"],
            threshold=thresholds[
                "long_minimum_core_wall_improvement_pct"
            ],
            comparator=">=",
            passed=(
                long_core["improvement_pct"]["mean"]
                >= thresholds[
                    "long_minimum_core_wall_improvement_pct"
                ]
            ),
            reason="long_core_wall_improvement_below_threshold",
            unit="pct",
        ),
        "maximum_short_d2_association_mean_increase_pct": _gate(
            actual=short_d2_increase_pct,
            threshold=thresholds[
                "maximum_short_d2_association_mean_increase_pct"
            ],
            comparator="<=",
            passed=(
                short_d2_increase_pct
                <= thresholds[
                    "maximum_short_d2_association_mean_increase_pct"
                ]
            ),
            reason="short_d2_association_increase_above_threshold",
            unit="pct",
        ),
        "maximum_long_d2_association_mean_increase_pct": _gate(
            actual=long_d2_increase_pct,
            threshold=thresholds[
                "maximum_long_d2_association_mean_increase_pct"
            ],
            comparator="<=",
            passed=(
                long_d2_increase_pct
                <= thresholds[
                    "maximum_long_d2_association_mean_increase_pct"
                ]
            ),
            reason="long_d2_association_increase_above_threshold",
            unit="pct",
        ),
        "maximum_rss_mean_increase_pct": _gate(
            actual=rss_mean_increase_pct,
            threshold=thresholds["maximum_rss_mean_increase_pct"],
            comparator="<=",
            passed=(
                rss_mean_increase_pct
                <= thresholds["maximum_rss_mean_increase_pct"]
            ),
            reason="short_or_long_rss_mean_increase_above_threshold",
            unit="pct",
        ),
        "maximum_any_pair_rss_increase_pct": _gate(
            actual=maximum_pair_rss_increase_pct,
            threshold=thresholds[
                "maximum_any_pair_rss_increase_pct"
            ],
            comparator="<=",
            passed=(
                maximum_pair_rss_increase_pct
                <= thresholds["maximum_any_pair_rss_increase_pct"]
            ),
            reason="one_or_more_pair_rss_increase_above_threshold",
            unit="pct",
        ),
        "minimum_candidate_duplicate_check_reduction_pct": _gate(
            actual=duplicate_reduction,
            threshold=thresholds[
                "minimum_candidate_duplicate_check_reduction_pct"
            ],
            comparator=">=",
            passed=(
                duplicate_reduction
                >= thresholds[
                    "minimum_candidate_duplicate_check_reduction_pct"
                ]
            ),
            reason="candidate_duplicate_check_reduction_below_threshold",
            unit="pct",
        ),
        "minimum_candidate_closed_handoff_ratio_pct": _gate(
            actual=closed_ratio,
            threshold=thresholds[
                "minimum_candidate_closed_handoff_ratio_pct"
            ],
            comparator=">=",
            passed=(
                closed_ratio
                >= thresholds["minimum_candidate_closed_handoff_ratio_pct"]
            ),
            reason="candidate_closed_handoff_ratio_below_threshold",
            unit="pct",
        ),
        "maximum_candidate_reference_fallback_count": _gate(
            actual=fallback_count,
            threshold=thresholds[
                "maximum_candidate_reference_fallback_count"
            ],
            comparator="<=",
            passed=(
                fallback_count
                <= thresholds[
                    "maximum_candidate_reference_fallback_count"
                ]
            ),
            reason="candidate_reference_fallback_count_above_threshold",
        ),
    }


def _gate(
    *,
    actual: Any,
    threshold: Any,
    comparator: str,
    passed: bool,
    reason: str,
    unit: str | None = None,
) -> dict[str, Any]:
    return {
        "passed": bool(passed),
        "actual": actual,
        "threshold": threshold,
        "comparator": comparator,
        "unit": unit,
        "reason": None if passed else reason,
    }


def write_d1_online_batch_frame_multiseed_report(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write deterministic compact products outside the raw evidence root."""

    if result.get("schema_version") != (
        D1_ONLINE_BATCH_FRAME_MULTISEED_EVALUATION_SCHEMA_VERSION
    ):
        raise ValueError("unsupported batch-frame evaluation schema")
    contract = _base._required_mapping(
        result.get("input_contract"),
        "batch-frame report input contract",
    )
    directory = Path(output_dir).expanduser().resolve()
    if "output_root" in contract:
        evidence_root = Path(str(contract["output_root"])).resolve()
        if _base._path_is_within(directory, evidence_root):
            raise ValueError(
                "independent D6 output must be outside the raw evidence root"
            )
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "evaluation_json": directory
        / "d1_online_batch_frame_multiseed_evaluation.json",
        "compact_json": directory
        / "d1_online_batch_frame_multiseed_compact.json",
        "pairs_csv": directory
        / "d1_online_batch_frame_multiseed_pairs.csv",
        "markdown": directory
        / "D1_ONLINE_BATCH_FRAME_MULTISEED_REPORT_CN.md",
        "plot_png": directory
        / "d1_online_batch_frame_multiseed_curves.png",
        "sha256sums": directory / "SHA256SUMS",
    }
    paths["evaluation_json"].write_text(
        _base._json_text(result),
        encoding="utf-8",
    )
    paths["compact_json"].write_text(
        _base._json_text(_compact_output(result)),
        encoding="utf-8",
    )
    _write_pair_csv(result, paths["pairs_csv"])
    paths["markdown"].write_text(
        render_d1_online_batch_frame_multiseed_markdown(result),
        encoding="utf-8",
    )
    available = bool(
        _base._required_mapping(
            result.get("availability"), "batch-frame report availability"
        ).get("available")
    )
    if available:
        _write_plot(result, paths["plot_png"])
    else:
        paths.pop("plot_png")
    checksum_lines = [
        f"{_base._file_sha256(paths[name])}  {paths[name].name}"
        for name in sorted(paths)
        if name != "sha256sums"
    ]
    paths["sha256sums"].write_text(
        "\n".join(sorted(checksum_lines)) + "\n",
        encoding="utf-8",
    )
    return paths


def _compact_output(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": (
            D1_ONLINE_BATCH_FRAME_MULTISEED_COMPACT_SCHEMA_VERSION
        ),
        "evaluation_schema_version": result["schema_version"],
        "evaluation_date": result["evaluation_date"],
        "availability": result["availability"],
        "input_contract": result["input_contract"],
        "scope": result["scope"],
        "groups": result["groups"],
        "batch_frame_diagnostics_aggregate": result[
            "batch_frame_diagnostics_aggregate"
        ],
        "admission_gates": result["admission_gates"],
        "admission_blockers": result["admission_blockers"],
        "optimization_admitted": result["optimization_admitted"],
        "system_realtime_gate": result["system_realtime_gate"],
        "system_realtime_gap_closed": result[
            "system_realtime_gap_closed"
        ],
    }


def render_d1_online_batch_frame_multiseed_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the formal Chinese batch-frame admission report."""

    availability = _base._required_mapping(
        result.get("availability"), "batch-frame report availability"
    )
    contract = _base._required_mapping(
        result["input_contract"], "batch-frame input contract"
    )
    if availability.get("available") is not True:
        return "\n".join([
            "# D1 在线批帧交接多种子正式评估", "", "## 结论", "",
            "证据不可用，D6 失败关闭：`unavailable`。候选不准入，系统实时缺口未关闭。",
            f"原因：`{availability.get('reason')}`。", "",
        ])
    groups = _base._required_mapping(result["groups"], "batch-frame groups")
    gates = _base._required_mapping(
        result["admission_gates"], "batch-frame gates"
    )
    diagnostics = result["batch_frame_diagnostics_aggregate"]["groups"]["all"]
    realtime = result["system_realtime_gate"]
    decision = "admit" if result["optimization_admitted"] else "reject"
    failed = [name for name, gate in gates.items() if not gate["passed"]]
    lines = [
        "# D1 在线批帧交接同提交多种子正式评估", "", "## 结论", "",
        f"候选优化准入结论：`{decision}`。"
        f"{'全部预注册 gate 通过。' if not failed else '失败 gate：' + '、'.join(f'`{x}`' for x in failed) + '。'}",
        (
            f"200v200 系统实时结论：`{'达标' if result['system_realtime_gap_closed'] else '仍不足'}`；"
            f"候选最低实时因子 `{_fmt(realtime['candidate_minimum_real_time_factor'])}`，"
            "门限 `>=1.0`。候选优化准入不等于系统实时达标。"
        ),
        "本报告只使用 2026-07-25 的三维质点仿真证据，不是 AirSim、实机或实飞证据。",
        "", "## 证据范围", "",
        f"- source commit：`{contract['source_commit']}`，producer clean。",
        f"- matrix SHA-256：`{contract['matrix_sha256']}`。",
        "- short 10 对、long 3 对，共 13 对/26 episode；200 目标、200 资源、2 侦察节点。",
        f"- 参考 `{REFERENCE_IMPLEMENTATION}`；候选 `{CANDIDATE_IMPLEMENTATION}`。",
        "", "## 批帧审计", "", "| 指标 | 实测 |", "|---|---:|",
        f"| 重复检查减少率 | {_fmt(diagnostics['candidate_duplicate_check_reduction_pct'])}% |",
        f"| closed handoff ratio | {_fmt(diagnostics['candidate_closed_handoff_ratio_pct'])}% |",
        f"| candidate fallback count | {diagnostics['candidate_reference_fallback_count']} |",
        f"| candidate request/closed | {diagnostics['candidate_request_count']}/{diagnostics['candidate_closed_handoff_count']} |",
        "",
        "每个 episode 均从四份最终诊断重算 request/path/result、raw batch check、"
        "snapshot structure、snapshot success/failure、final frame check 和量测输出守恒；"
        "selector 及 execution config 在 runtime profile、summary、module final、"
        "nested governance 和 governance audit 表面逐层绑定。",
        "", "## 分组性能", "",
        "| 组 | 指标 | 参考均值 | 候选均值 | 变化 | 候选更快 | 95% bootstrap CI |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for group in _GROUPS:
        label = "短时" if group == "short" else "长时"
        for metric, metric_label, use_raw in (
            ("d1_scan_input_wall_s", "scan input", False),
            ("core_wall_s", "core wall", False),
            ("d2_association_wall_s", "D2 association", True),
            ("maximum_rss_kib", "maximum RSS", True),
            ("real_time_factor", "real-time factor", False),
        ):
            item = groups[group]["metrics"][metric]
            change = (
                item["ratio_of_group_means"]["raw_relative_change"] * 100.0
                if use_raw else item["improvement_pct"]["mean"]
            )
            ci = item["raw_relative_change"]["bootstrap_95_ci"]
            lines.append(
                f"| {label} | {metric_label} | {_fmt(item['reference']['mean'])} | "
                f"{_fmt(item['candidate']['mean'])} | {_fmt(change)}% | "
                f"{item['candidate_better_count']}/{item['pair_count']} | "
                f"[{_fmt(ci['lower'] * 100.0)}, {_fmt(ci['upper'] * 100.0)}]% |"
            )
    lines.extend(["", "## 预注册 Gate", "",
                  "| gate | 实测 | 判据 | 结果 |", "|---|---:|---:|---:|"])
    for name in sorted(gates):
        gate = gates[name]
        unit = "%" if gate.get("unit") == "pct" else ""
        lines.append(
            f"| `{name}` | {_fmt(gate['actual'])}{unit} | "
            f"`{gate['comparator']} {_fmt(gate['threshold'])}{unit}` | "
            f"{'通过' if gate['passed'] else '失败'} |"
        )
    lines.extend(["", "## 逐对结果", "",
                  "| case | scan 改善 | core 改善 | D2 增幅 | RSS 增幅 | 重复检查减少 | closed ratio | 语义 |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for pair in result["pairs"]:
        perf = pair["performance"]
        audit = pair["online_batch_frame_audit"]
        lines.append(
            f"| {pair['case_id']} | {_fmt(perf['d1_scan_input_wall_s']['improvement_pct'])}% | "
            f"{_fmt(perf['core_wall_s']['improvement_pct'])}% | "
            f"{_fmt(perf['d2_association_wall_s']['raw_relative_change_pct'])}% | "
            f"{_fmt(perf['maximum_rss_kib']['raw_relative_change_pct'])}% | "
            f"{_fmt(audit['candidate_duplicate_check_reduction_pct'])}% | "
            f"{_fmt(audit['candidate_closed_handoff_ratio_pct'])}% | "
            f"{'通过' if pair['business_semantics_passed'] else '失败'} |"
        )
    lines.extend([
        "", "## 语义归一化边界", "",
        "D6 只归一化预注册 treatment selector、execution config、批帧诊断计数及其派生字段、"
        "treatment 派生 episode_id 和性能字段。assignment plan 的真实业务内容不被忽略。",
        "独立运行产生的 opaque plan ID 按首次出现的连续谱系映射为 token；"
        "源 plan/guidance 哈希、ACK 和 D4 authority 内容地址先在原始流内验证。"
        "映射后仍逐条比较 plan version/前序关系、分配关系、授权状态、目标-资源绑定、"
        "owner/coalition 业务字段、状态机结果、计数、安全结果及所有下游引用。"
        "任一真实 assignment 差异都会关闭业务语义 gate。",
        "", "## 制品", "",
        "- `d1_online_batch_frame_multiseed_evaluation.json`：完整 JSON。",
        "- `d1_online_batch_frame_multiseed_compact.json`：紧凑 JSON。",
        "- `d1_online_batch_frame_multiseed_pairs.csv`：逐 pair 数据。",
        "- `d1_online_batch_frame_multiseed_curves.png`：性能、审计和实时曲线。",
        "- `SHA256SUMS`：制品校验值。", "",
    ])
    return "\n".join(lines)


def _write_pair_csv(result: Mapping[str, Any], path: Path) -> None:
    fieldnames = [
        "case_id",
        "group",
        "seed",
        "duration_s",
        "business_semantics_passed",
        "finite_state_passed",
        "truth_isolation_passed",
        "implementation_identity_passed",
        "online_batch_frame_audit_passed",
        "reference_request_count",
        "candidate_request_count",
        "reference_duplicate_check_count",
        "candidate_duplicate_check_count",
        "candidate_duplicate_check_reduction_pct",
        "candidate_closed_handoff_count",
        "candidate_closed_handoff_ratio_pct",
        "candidate_reference_fallback_count",
    ]
    for metric in _METRICS:
        fieldnames.extend(
            (
                f"reference__{metric}",
                f"candidate__{metric}",
                f"raw_relative_change__{metric}",
                f"improvement_pct__{metric}",
            )
        )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        for pair in result["pairs"]:
            audit = pair["online_batch_frame_audit"]
            row: dict[str, Any] = {
                "case_id": pair["case_id"],
                "group": pair["group"],
                "seed": pair["seed"],
                "duration_s": pair["duration_s"],
                "business_semantics_passed": pair[
                    "business_semantics_passed"
                ],
                "finite_state_passed": pair["finite_state_passed"],
                "truth_isolation_passed": pair["truth_isolation_passed"],
                "implementation_identity_passed": pair[
                    "implementation_identity_passed"
                ],
                "online_batch_frame_audit_passed": pair[
                    "online_batch_frame_audit_passed"
                ],
                **{
                    name: audit[name]
                    for name in (
                        "reference_request_count",
                        "candidate_request_count",
                        "reference_duplicate_check_count",
                        "candidate_duplicate_check_count",
                        "candidate_duplicate_check_reduction_pct",
                        "candidate_closed_handoff_count",
                        "candidate_closed_handoff_ratio_pct",
                        "candidate_reference_fallback_count",
                    )
                },
            }
            for metric in _METRICS:
                comparison = pair["performance"][metric]
                row[f"reference__{metric}"] = comparison["reference"]
                row[f"candidate__{metric}"] = comparison["candidate"]
                row[f"raw_relative_change__{metric}"] = comparison[
                    "raw_relative_change"
                ]
                row[f"improvement_pct__{metric}"] = comparison[
                    "improvement_pct"
                ]
            writer.writerow(row)


def _write_plot(result: Mapping[str, Any], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pairs = list(result["pairs"])
    labels = [str(pair["case_id"]).replace("_seed_", "\n") for pair in pairs]
    x = list(range(len(pairs)))
    fig, axes = plt.subplots(
        3,
        1,
        figsize=(11.5, 9.0),
        sharex=True,
        gridspec_kw={"height_ratios": [1.6, 1.2, 1.0]},
    )
    performance_axis, audit_axis, realtime_axis = axes
    for metric, label, color, raw in (
        ("d1_scan_input_wall_s", "Scan-input improvement", "#1f77b4", False),
        ("core_wall_s", "Core wall improvement", "#2ca02c", False),
        ("d2_association_wall_s", "D2 association increase", "#ff7f0e", True),
    ):
        performance_axis.plot(
            x,
            [
                float(
                    pair["performance"][metric][
                        "raw_relative_change_pct"
                        if raw
                        else "improvement_pct"
                    ]
                )
                for pair in pairs
            ],
            marker="o",
            linewidth=1.4,
            label=label,
            color=color,
        )
    performance_axis.axhline(0.0, color="#444444", linewidth=0.8)
    performance_axis.set_ylabel("Change (%)")
    performance_axis.grid(True, alpha=0.25)
    performance_axis.legend(ncol=3, fontsize=8, loc="best")

    audit_axis.plot(
        x,
        [
            float(
                pair["online_batch_frame_audit"][
                    "candidate_duplicate_check_reduction_pct"
                ]
            )
            for pair in pairs
        ],
        marker="o",
        label="Duplicate-check reduction",
        color="#9467bd",
    )
    audit_axis.plot(
        x,
        [
            float(
                pair["online_batch_frame_audit"][
                    "candidate_closed_handoff_ratio_pct"
                ]
            )
            for pair in pairs
        ],
        marker="s",
        label="Closed handoff ratio",
        color="#17becf",
    )
    audit_axis.axhline(
        95.0,
        color="#d62728",
        linewidth=1.0,
        linestyle="--",
        label="Admission threshold 95%",
    )
    audit_axis.set_ylabel("Handoff audit (%)")
    audit_axis.grid(True, alpha=0.25)
    audit_axis.legend(fontsize=8, loc="best")

    realtime_axis.plot(
        x,
        [
            float(pair["candidate"]["metrics"]["real_time_factor"])
            for pair in pairs
        ],
        marker="o",
        color="#8c564b",
        label="Candidate real-time factor",
    )
    realtime_axis.axhline(
        1.0,
        color="#d62728",
        linewidth=1.0,
        linestyle="--",
        label="System threshold 1.0",
    )
    realtime_axis.set_ylabel("Real-time factor")
    realtime_axis.set_xticks(x)
    realtime_axis.set_xticklabels(labels, fontsize=8)
    realtime_axis.set_xlabel("Preregistered pair")
    realtime_axis.grid(True, alpha=0.25)
    realtime_axis.legend(fontsize=8, loc="best")
    fig.suptitle("D1 online batch-frame paired admission evaluation")
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the frozen D1 online batch-frame handoff matrix"
        )
    )
    parser.add_argument(
        "--evidence-manifest",
        required=True,
        help="completed batch-frame evidence_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="independent compact D6 output directory",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = evaluate_d1_online_batch_frame_multiseed(
        args.evidence_manifest
    )
    paths = write_d1_online_batch_frame_multiseed_report(
        result,
        args.output_dir,
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    print(
        "optimization_admitted: "
        f"{str(result['optimization_admitted']).lower()}"
    )
    print(
        "system_realtime_gap_closed: "
        f"{str(result['system_realtime_gap_closed']).lower()}"
    )
    print(
        "availability: "
        f"{str(result['availability']['available']).lower()}"
    )
    if result["availability"]["available"] is not True:
        print(f"reason: {result['availability']['reason']}")
        return 2
    return 0


__all__ = [
    "CANDIDATE_IMPLEMENTATION",
    "CANDIDATE_IMPLEMENTATION_ID",
    "D1OnlineBatchFrameEvidence",
    "D1OnlineBatchFrameEvidenceError",
    "D1_ONLINE_BATCH_FRAME_DIAGNOSTICS_SCHEMA_VERSION",
    "D1_ONLINE_BATCH_FRAME_EVALUATION_DATE",
    "D1_ONLINE_BATCH_FRAME_EVIDENCE_SCHEMA_VERSION",
    "D1_ONLINE_BATCH_FRAME_EXPERIMENT_ID",
    "D1_ONLINE_BATCH_FRAME_MATRIX_SCHEMA_VERSION",
    "D1_ONLINE_BATCH_FRAME_MATRIX_SHA256",
    "D1_ONLINE_BATCH_FRAME_MULTISEED_COMPACT_SCHEMA_VERSION",
    "D1_ONLINE_BATCH_FRAME_MULTISEED_EVALUATION_SCHEMA_VERSION",
    "D1_ONLINE_BATCH_FRAME_SOURCE_COMMIT",
    "REFERENCE_IMPLEMENTATION",
    "REFERENCE_IMPLEMENTATION_ID",
    "evaluate_d1_online_batch_frame_multiseed",
    "load_d1_online_batch_frame_evidence_manifest",
    "main",
    "render_d1_online_batch_frame_multiseed_markdown",
    "write_d1_online_batch_frame_multiseed_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
