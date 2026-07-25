"""Independent paired admission for the scalable 3D structured numerical Jacobian.

The main runtime owns execution and writes a preregistered evidence manifest.
D6 only reads immutable episode products, validates their provenance and
semantics, and reports paired performance.  The evaluator never participates
in the online bus or changes a producer artifact.
"""

from __future__ import annotations

import argparse
import copy
import csv
from dataclasses import dataclass
import math
from pathlib import Path
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


D1_STRUCTURED_JACOBIAN_MULTISEED_EVALUATION_SCHEMA_VERSION = (
    "d6.d1_structured_jacobian_multiseed_evaluation.v1"
)
D1_STRUCTURED_JACOBIAN_MULTISEED_COMPACT_SCHEMA_VERSION = (
    "d6.d1_structured_jacobian_multiseed_compact.v1"
)
D1_STRUCTURED_JACOBIAN_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-structured-jacobian-multiseed-matrix-v1"
)
D1_STRUCTURED_JACOBIAN_EVIDENCE_SCHEMA_VERSION = (
    "scalable3d-d1-structured-jacobian-multiseed-evidence-v1"
)
D1_STRUCTURED_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION = (
    "d1.structured_numerical_jacobian_diagnostics.v1"
)
D1_STRUCTURED_JACOBIAN_EXPERIMENT_ID = (
    "d1-structured-numerical-jacobian-multiseed-20260724-v1"
)
D1_STRUCTURED_JACOBIAN_MATRIX_SHA256 = (
    "c6c3cf53c89dfb3155a29ba49bb77a12c8bdf1a5d433c4f645de0d00c506d478"
)
D1_STRUCTURED_JACOBIAN_SOURCE_COMMIT = (
    "9d1f54f8540fdc4a7a1011121aafac5718290122"
)
D1_STRUCTURED_JACOBIAN_EVALUATION_DATE = "2026-07-25"

REFERENCE_IMPLEMENTATION = "dense_output_probe_v1"
CANDIDATE_IMPLEMENTATION = "known_dimension_structural_columns_v1"
REFERENCE_IMPLEMENTATION_ID = (
    "d1.ekf.numerical_jacobian.dense_output_probe.v1"
)
CANDIDATE_IMPLEMENTATION_ID = (
    "d1.ekf.numerical_jacobian.known_dimension_structural_columns.v1"
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
_RUN_FLAGS = (
    "--integrated-stack",
    "--d1-d2-structural-ambiguity-hold",
)
_TARGET_COUNT = 200
_RESOURCE_COUNT = 200
_RECON_COUNT = 2
_BOOTSTRAP_RESAMPLES = 10_000
_BOOTSTRAP_RNG_SEED = 20_260_724
_SHORT_SEEDS = tuple(range(1101, 1111))
_LONG_SEEDS = tuple(range(1101, 1104))
_SHORT_DURATION_S = 2.2
_LONG_DURATION_S = 10.0
_TREATMENT_MARKER = "D6_REGISTERED_D1_STRUCTURED_JACOBIAN_TREATMENT"
_PERFORMANCE_MARKER = "D6_REGISTERED_PERFORMANCE_DIAGNOSTIC"
_TREATMENT_DERIVED_ID_MARKER = "D6_TREATMENT_DERIVED_EPISODE_ID"
_VALIDATION_KIND = "structured_numerical_jacobian"

_EXPECTED_GATES = {
    "all_pairs_business_semantics_equal": True,
    "all_pairs_finite_state": True,
    "all_pairs_online_truth_use_count": 0,
    "all_pairs_explicit_implementation_identity": True,
    "all_pairs_structured_jacobian_audit_valid": True,
    "short_minimum_candidate_faster_count": 8,
    "short_minimum_d1_fusion_improvement_pct": 2.0,
    "short_bootstrap_relative_change_upper_bound_pct": 0.0,
    "long_minimum_candidate_faster_count": 2,
    "long_minimum_d1_fusion_improvement_pct": 2.0,
    "short_minimum_core_wall_improvement_pct": 0.5,
    "long_minimum_core_wall_improvement_pct": 0.5,
    "maximum_short_d1_scan_input_mean_increase_pct": 5.0,
    "maximum_long_d1_scan_input_mean_increase_pct": 5.0,
    "maximum_short_d2_association_mean_increase_pct": 5.0,
    "maximum_long_d2_association_mean_increase_pct": 5.0,
    "maximum_rss_mean_increase_pct": 5.0,
    "maximum_any_pair_rss_increase_pct": 5.0,
    "minimum_candidate_measurement_evaluation_reduction_pct": 35.0,
}
_EXPECTED_BOUNDARY = {
    "simulation_mode": "three_dimensional_point_mass",
    "airsim_evidence": False,
    "truth_is_online_control_input": False,
    "system_realtime_requires_real_time_factor_at_least_one": True,
    "same_source_commit_for_both_arms": True,
    "only_allowed_runtime_treatment_difference": (
        "d1_structured_numerical_jacobian_implementation"
    ),
    "reference_implementation": REFERENCE_IMPLEMENTATION,
    "candidate_implementation": CANDIDATE_IMPLEMENTATION,
    "structured_jacobian_diagnostics_schema_version": (
        D1_STRUCTURED_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION
    ),
    "known_active_columns_by_modality": True,
    "active_columns_preserve_reference_centered_difference": True,
    "matrix_values_are_read_only": True,
    "prior_episode_outputs_reused": False,
}
_EXPECTED_CASES = (
    ("short_seed_1101", "short", 1101, 2.2, ("reference", "candidate")),
    ("short_seed_1102", "short", 1102, 2.2, ("candidate", "reference")),
    ("short_seed_1103", "short", 1103, 2.2, ("reference", "candidate")),
    ("short_seed_1104", "short", 1104, 2.2, ("candidate", "reference")),
    ("short_seed_1105", "short", 1105, 2.2, ("reference", "candidate")),
    ("short_seed_1106", "short", 1106, 2.2, ("candidate", "reference")),
    ("short_seed_1107", "short", 1107, 2.2, ("reference", "candidate")),
    ("short_seed_1108", "short", 1108, 2.2, ("candidate", "reference")),
    ("short_seed_1109", "short", 1109, 2.2, ("reference", "candidate")),
    ("short_seed_1110", "short", 1110, 2.2, ("candidate", "reference")),
    ("long_seed_1101", "long", 1101, 10.0, ("reference", "candidate")),
    ("long_seed_1102", "long", 1102, 10.0, ("candidate", "reference")),
    ("long_seed_1103", "long", 1103, 10.0, ("reference", "candidate")),
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
_STAGES = {
    "d1_fusion": "module.d1_fusion",
    "d1_scan_input": "module.d1_scan_input",
    "d2_association": "module.d2_association",
}
_METRICS = (
    "d1_fusion_wall_s",
    "d1_fusion_p50_ms",
    "d1_fusion_p95_ms",
    "d1_fusion_max_ms",
    "core_wall_s",
    "external_elapsed_s",
    "real_time_factor",
    "d1_scan_input_wall_s",
    "d2_association_wall_s",
    "maximum_rss_kib",
)
_LOWER_IS_BETTER = set(_METRICS) - {"real_time_factor"}
_REQUIRED_ADMISSION_METRICS = {
    "d1_fusion_wall_s",
    "core_wall_s",
    "d1_scan_input_wall_s",
    "d2_association_wall_s",
    "maximum_rss_kib",
    "real_time_factor",
}
_OPERATION_FIELDS = {
    "jacobian_attempt_count",
    "jacobian_success_count",
    "jacobian_failure_count",
    "reference_call_count",
    "structured_candidate_call_count",
    "output_probe_evaluation_count",
    "output_probe_elision_count",
    "inactive_state_column_elision_count",
    "measurement_function_evaluation_count",
}
_EXPECTED_CONFIG_SCHEMA_VERSION = "scalable3d-scenario-v1"
_EXPECTED_RUNTIME_PROFILE_SCHEMA_VERSION = (
    "scalable3d-integrated-stack-runtime-profile-v1"
)
_EXPECTED_GOVERNANCE_SCHEMA_VERSION = (
    "scalable3d-observation-governance-runtime-v2"
)
_REQUIRED_HASH_KEYS = {
    "manifest.json",
    "scenario_config.json",
    "summary.json",
    "observation_governance_audit.json",
    "stage_timings.csv",
    "online_observations.jsonl",
    "offline_truth_state.npz",
    "offline_truth_labels.jsonl",
    "offline_proximity_intercepts.jsonl",
    "resource_usage",
    "stdout",
    "stderr",
}
_BUSINESS_SUMMARY_FIELDS = (
    "online_observation_count",
    "online_batch_count",
    "radar_observation_count",
    "acoustic_observation_count",
    "visual_observation_count",
    "module_publication_count",
    "module_publication_topic_counts",
    "assignment_plan_ack_count",
    "assignment_plan_binding_ack_count",
    "assignment_plan_control_applied_count",
    "assignment_plan_hold_count",
    "camera_command_ack_count",
    "camera_command_applied_count",
    "camera_command_issued_count",
    "camera_command_rejected_count",
    "camera_command_rejection_reason_counts",
    "intercepted_target_count",
)
_MODULE_FINAL_COUNT_FIELDS = (
    "d1_track_count",
    "d2_track_count",
    "d3_assignment_count",
    "d5_binding_count",
    "d7_command_count",
)


class D1StructuredJacobianEvidenceError(ValueError):
    """Raised when producer evidence violates the frozen D6 contract."""


@dataclass(frozen=True)
class D1StructuredJacobianArmBinding:
    arm: str
    implementation: str
    episode_dir: Path
    resource_path: Path
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True)
class D1StructuredJacobianPairBinding:
    case_id: str
    group: str
    seed: int
    duration_s: float
    arm_order: tuple[str, ...]
    arms: Mapping[str, D1StructuredJacobianArmBinding]


@dataclass(frozen=True)
class D1StructuredJacobianEvidence:
    source_path: Path
    source_sha256: str
    matrix_path: Path
    matrix_sha256: str
    matrix: Mapping[str, Any]
    output_root: Path
    source_commit: str
    source_worktree: Path
    pairs: tuple[D1StructuredJacobianPairBinding, ...]


def load_d1_structured_jacobian_evidence_manifest(
    source: str | Path,
) -> D1StructuredJacobianEvidence:
    """Load one completed producer manifest and fail closed on drift."""

    source_path = Path(source).expanduser().resolve()
    manifest, manifest_raw = _load_mapping(source_path)
    _expect(
        manifest.get("schema_version"),
        D1_STRUCTURED_JACOBIAN_EVIDENCE_SCHEMA_VERSION,
        "evidence schema_version",
    )
    _expect(
        manifest.get("experiment_id"),
        D1_STRUCTURED_JACOBIAN_EXPERIMENT_ID,
        "evidence experiment_id",
    )
    _expect(
        manifest.get("required_d6_evaluator_schema_version"),
        D1_STRUCTURED_JACOBIAN_MULTISEED_EVALUATION_SCHEMA_VERSION,
        "required D6 evaluator schema",
    )
    _expect(
        manifest.get("structured_jacobian_diagnostics_schema_version"),
        D1_STRUCTURED_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION,
        "structured-Jacobian diagnostics schema",
    )
    if manifest.get("status") != "episodes_complete_pending_d6":
        raise D1StructuredJacobianEvidenceError(
            "evidence status must be episodes_complete_pending_d6"
        )
    _required_text(manifest.get("completed_at_utc"), "completed_at_utc")
    source_commit = _required_commit(
        manifest.get("source_commit"), "source_commit"
    )
    if source_commit != D1_STRUCTURED_JACOBIAN_SOURCE_COMMIT:
        raise D1StructuredJacobianEvidenceError(
            "source_commit does not match the frozen producer commit"
        )
    if manifest.get("source_repository_dirty") is not False:
        raise D1StructuredJacobianEvidenceError(
            "source_repository_dirty must be false"
        )
    source_worktree = _explicit_path(
        manifest.get("source_worktree"),
        "source_worktree",
        require=None,
    )
    output_root = _explicit_path(
        manifest.get("output_root"),
        "output_root",
        require="directory",
    )
    if source_path.parent != output_root:
        raise D1StructuredJacobianEvidenceError(
            "evidence_manifest.json must be directly under output_root"
        )
    matrix_path = _explicit_path(
        manifest.get("matrix_path"), "matrix_path", require="file"
    )
    matrix_sha256 = _required_sha256(
        manifest.get("matrix_sha256"), "matrix_sha256"
    )
    if matrix_sha256 != _base._file_sha256(matrix_path):
        raise D1StructuredJacobianEvidenceError(
            "matrix_sha256 does not match matrix_path bytes"
        )
    if matrix_sha256 != D1_STRUCTURED_JACOBIAN_MATRIX_SHA256:
        raise D1StructuredJacobianEvidenceError(
            "matrix_sha256 does not match the frozen producer matrix"
        )
    matrix, _ = _load_mapping(matrix_path)
    _validate_matrix(matrix)
    if _required_mapping(manifest.get("matrix"), "embedded matrix") != matrix:
        raise D1StructuredJacobianEvidenceError(
            "embedded matrix does not exactly match matrix_path"
        )

    raw_cases = _required_sequence(manifest.get("cases"), "evidence cases")
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise D1StructuredJacobianEvidenceError(
            "evidence manifest must contain exactly 13 cases"
        )
    pairs: list[D1StructuredJacobianPairBinding] = []
    used_paths: set[Path] = {source_path}
    for raw_case, expected_case in zip(
        raw_cases, _EXPECTED_CASES, strict=True
    ):
        case = _required_mapping(raw_case, "evidence case")
        metadata = _case_metadata(case)
        if metadata != expected_case:
            raise D1StructuredJacobianEvidenceError(
                "evidence case differs from the frozen matrix"
            )
        case_id, group, seed, duration_s, arm_order = metadata
        if (
            case.get("d6_evaluation_status")
            != "episodes_complete_pending_d6"
        ):
            raise D1StructuredJacobianEvidenceError(
                f"{case_id} is not pending D6 evaluation"
            )
        raw_arms = _required_mapping(case.get("arms"), f"{case_id} arms")
        if set(raw_arms) != set(_ARMS):
            raise D1StructuredJacobianEvidenceError(
                f"{case_id} arms must be reference and candidate"
            )
        arms: dict[str, D1StructuredJacobianArmBinding] = {}
        commands: dict[str, list[str]] = {}
        for arm in _ARMS:
            record = _required_mapping(
                raw_arms.get(arm), f"{case_id} {arm} arm"
            )
            implementation = _IMPLEMENTATIONS[arm]
            _expect(record.get("arm"), arm, f"{case_id} arm label")
            _expect(
                record.get("expected_implementation"),
                implementation,
                f"{case_id} {arm} expected implementation",
            )
            _expect(
                record.get("expected_d1_implementation_id"),
                _IMPLEMENTATION_IDS[arm],
                f"{case_id} {arm} expected D1 implementation ID",
            )
            _expect(
                record.get("validation_kind"),
                _VALIDATION_KIND,
                f"{case_id} {arm} validation_kind",
            )
            _expect(
                record.get("expected_commit"),
                source_commit,
                f"{case_id} {arm} expected commit",
            )
            if record.get("status") != "complete":
                raise D1StructuredJacobianEvidenceError(
                    f"{case_id} {arm} must be a fresh complete arm"
                )
            return_code = record.get("return_code")
            if (
                not isinstance(return_code, int)
                or isinstance(return_code, bool)
                or return_code != 0
            ):
                raise D1StructuredJacobianEvidenceError(
                    f"{case_id} {arm} return_code must be integer zero"
                )
            episode_dir = _explicit_path(
                record.get("episode_dir"),
                f"{case_id} {arm} episode_dir",
                require="directory",
            )
            resource_path = _explicit_path(
                record.get("resource_path"),
                f"{case_id} {arm} resource_path",
                require="file",
            )
            stdout_path = _explicit_path(
                record.get("stdout_path"),
                f"{case_id} {arm} stdout_path",
                require="file",
            )
            stderr_path = _explicit_path(
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
                _require_under_root(
                    path, output_root, f"{case_id} {arm} {label}"
                )
                if path in used_paths:
                    raise D1StructuredJacobianEvidenceError(
                        f"duplicate evidence path: {path}"
                    )
                used_paths.add(path)
            command = [
                _required_text(item, f"{case_id} {arm} command item")
                for item in _required_sequence(
                    record.get("command"), f"{case_id} {arm} command"
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
                raise D1StructuredJacobianEvidenceError(
                    f"{case_id} {arm} command differs from frozen execution"
                )
            commands[arm] = command
            arms[arm] = D1StructuredJacobianArmBinding(
                arm=arm,
                implementation=implementation,
                episode_dir=episode_dir,
                resource_path=resource_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        _validate_pair_command_isolation(commands, case_id)
        pairs.append(
            D1StructuredJacobianPairBinding(
                case_id=case_id,
                group=group,
                seed=seed,
                duration_s=duration_s,
                arm_order=arm_order,
                arms=arms,
            )
        )
    if len(pairs) * len(_ARMS) != 26:
        raise D1StructuredJacobianEvidenceError(
            "evidence must bind exactly 26 fresh arms"
        )
    return D1StructuredJacobianEvidence(
        source_path=source_path,
        source_sha256=_base._sha256_bytes(manifest_raw),
        matrix_path=matrix_path,
        matrix_sha256=matrix_sha256,
        matrix=copy.deepcopy(dict(matrix)),
        output_root=output_root,
        source_commit=source_commit,
        source_worktree=source_worktree,
        pairs=tuple(pairs),
    )


def evaluate_d1_structured_jacobian_multiseed(
    source: str | Path,
    *,
    raise_on_invalid: bool = False,
) -> dict[str, Any]:
    """Evaluate the frozen matrix or return an unavailable fail-closed result."""

    try:
        return _evaluate_d1_structured_jacobian_multiseed_available(source)
    except D1StructuredJacobianEvidenceError as exc:
        if raise_on_invalid:
            raise
        return _unavailable_evaluation(source, str(exc))


def _evaluate_d1_structured_jacobian_multiseed_available(
    source: str | Path,
) -> dict[str, Any]:
    """Strict evaluation path used after all evidence checks pass."""

    evidence = load_d1_structured_jacobian_evidence_manifest(source)
    pairs = [_evaluate_pair(pair, evidence) for pair in evidence.pairs]
    groups = {
        group: _summarize_group(
            [pair for pair in pairs if pair["group"] == group],
            group=group,
            bootstrap_resamples=int(evidence.matrix["bootstrap_resamples"]),
            bootstrap_seed=int(evidence.matrix["bootstrap_seed"]),
        )
        for group in _GROUPS
    }
    diagnostics_aggregate = _aggregate_structured_jacobian_diagnostics(
        pairs
    )
    thresholds = copy.deepcopy(
        dict(_required_mapping(
            evidence.matrix["admission_gates"], "admission gates"
        ))
    )
    gates = _admission_gates(
        pairs,
        groups,
        diagnostics_aggregate,
        thresholds,
    )
    optimization_admitted = all(
        bool(gate["passed"]) for gate in gates.values()
    )
    realtime_gate = _base._system_realtime_gate(pairs)
    return {
        "schema_version": (
            D1_STRUCTURED_JACOBIAN_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": D1_STRUCTURED_JACOBIAN_EVALUATION_DATE,
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
                D1_STRUCTURED_JACOBIAN_EVIDENCE_SCHEMA_VERSION
            ),
            "evidence_manifest_status": (
                "episodes_complete_pending_d6"
            ),
            "matrix_path": str(evidence.matrix_path),
            "matrix_sha256": evidence.matrix_sha256,
            "matrix_schema_version": (
                D1_STRUCTURED_JACOBIAN_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": D1_STRUCTURED_JACOBIAN_EXPERIMENT_ID,
            "output_root": str(evidence.output_root),
            "source_commit": evidence.source_commit,
            "source_repository_dirty": False,
            "same_commit_for_both_arms": True,
            "arm_implementations": dict(_IMPLEMENTATIONS),
            "arm_implementation_ids": dict(_IMPLEMENTATION_IDS),
            "structured_jacobian_diagnostics_schema_version": (
                D1_STRUCTURED_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION
            ),
            "bootstrap_resamples": int(
                evidence.matrix["bootstrap_resamples"]
            ),
            "bootstrap_rng_seed": int(
                evidence.matrix["bootstrap_seed"]
            ),
            "short_seeds": list(_SHORT_SEEDS),
            "long_seeds": list(_LONG_SEEDS),
            "short_duration_s": _SHORT_DURATION_S,
            "long_duration_s": _LONG_DURATION_S,
        },
        "scope": {
            "simulation_mode": "three_dimensional_point_mass",
            "airsim_evidence": False,
            "target_count": _TARGET_COUNT,
            "resource_count": _RESOURCE_COUNT,
            "recon_count": _RECON_COUNT,
            "pair_count": len(pairs),
            "arm_count": len(pairs) * 2,
            "business_semantics_compared": True,
            "online_truth_isolation_required": True,
            "structured_jacobian_operation_conservation_required": True,
            "candidate_default_enabled": False,
        },
        "pairs": pairs,
        "groups": groups,
        "structured_jacobian_diagnostics_aggregate": diagnostics_aggregate,
        "admission_gates": gates,
        "optimization_admitted": optimization_admitted,
        "system_realtime_gate": realtime_gate,
        "system_realtime_gap_closed": bool(realtime_gate["passed"]),
    }


def _unavailable_evaluation(
    source: str | Path,
    reason: str,
) -> dict[str, Any]:
    source_path = Path(source).expanduser().resolve()
    unavailable_gate = _gate(
        False,
        True,
        "==",
        False,
        "evidence_unavailable",
    )
    return {
        "schema_version": (
            D1_STRUCTURED_JACOBIAN_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": D1_STRUCTURED_JACOBIAN_EVALUATION_DATE,
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "availability": {
            "available": False,
            "reason": reason,
        },
        "input_contract": {
            "evidence_manifest_path": str(source_path),
            "matrix_sha256": D1_STRUCTURED_JACOBIAN_MATRIX_SHA256,
            "matrix_schema_version": (
                D1_STRUCTURED_JACOBIAN_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": D1_STRUCTURED_JACOBIAN_EXPERIMENT_ID,
            "source_commit": D1_STRUCTURED_JACOBIAN_SOURCE_COMMIT,
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
            "candidate_default_enabled": False,
        },
        "pairs": [],
        "groups": {},
        "structured_jacobian_diagnostics_aggregate": {},
        "admission_gates": {
            "evidence_available": unavailable_gate,
        },
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
        raise D1StructuredJacobianEvidenceError(
            "matrix fields differ from the frozen producer contract"
        )
    expected_scalars = {
        "schema_version": D1_STRUCTURED_JACOBIAN_MATRIX_SCHEMA_VERSION,
        "experiment_id": D1_STRUCTURED_JACOBIAN_EXPERIMENT_ID,
        "same_clean_commit_required": True,
        "target_count": _TARGET_COUNT,
        "resource_count": _RESOURCE_COUNT,
        "recon_count": _RECON_COUNT,
        "arm_implementations": _IMPLEMENTATIONS,
        "run_flags": list(_RUN_FLAGS),
        "cooldown_s": 5.0,
        "bootstrap_seed": _BOOTSTRAP_RNG_SEED,
        "bootstrap_resamples": _BOOTSTRAP_RESAMPLES,
    }
    for field, expected in expected_scalars.items():
        _expect(matrix.get(field), expected, f"matrix {field}")
    raw_cases = _required_sequence(matrix.get("cases"), "matrix cases")
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise D1StructuredJacobianEvidenceError(
            "matrix must contain exactly 13 cases"
        )
    for raw_case, expected in zip(
        raw_cases, _EXPECTED_CASES, strict=True
    ):
        case = _required_mapping(raw_case, "matrix case")
        if set(case) != {
            "case_id",
            "group",
            "seed",
            "duration_s",
            "arm_order",
        }:
            raise D1StructuredJacobianEvidenceError(
                "matrix case fields differ from the frozen contract"
            )
        if _case_metadata(case) != expected:
            raise D1StructuredJacobianEvidenceError(
                "matrix case differs from the frozen order"
            )
    _expect(
        _required_mapping(matrix.get("admission_gates"), "matrix gates"),
        _EXPECTED_GATES,
        "matrix admission_gates",
    )
    _expect(
        _required_mapping(
            matrix.get("evidence_boundary"), "matrix evidence_boundary"
        ),
        _EXPECTED_BOUNDARY,
        "matrix evidence_boundary",
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
        "--d1-structured-numerical-jacobian-implementation",
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
    commands: Mapping[str, Sequence[str]], case_id: str
) -> None:
    reference = list(commands[_REFERENCE_ARM])
    candidate = list(commands[_CANDIDATE_ARM])
    if len(reference) != len(candidate):
        raise D1StructuredJacobianEvidenceError(
            f"{case_id} arm command lengths differ"
        )
    selector_index = reference.index(
        "--d1-structured-numerical-jacobian-implementation"
    ) + 1
    output_index = reference.index("--output") + 1
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index in {selector_index, output_index}:
            continue
        if left != right:
            raise D1StructuredJacobianEvidenceError(
                f"{case_id} commands differ outside treatment/output"
            )


def _evaluate_pair(
    pair: D1StructuredJacobianPairBinding,
    evidence: D1StructuredJacobianEvidence,
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
    semantics = _compare_pair_business_semantics(reference, candidate)
    reference.pop("_semantic_input", None)
    candidate.pop("_semantic_input", None)
    workload_audit = _validate_pair_structured_jacobian_workload(
        reference["structured_jacobian_diagnostics"],
        candidate["structured_jacobian_diagnostics"],
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
    audit_passed = (
        reference["structured_jacobian_audit"]["passed"]
        and candidate["structured_jacobian_audit"]["passed"]
    )
    artifact_provenance_passed = (
        reference["artifact_provenance"]["passed"]
        and candidate["artifact_provenance"]["passed"]
    )
    return {
        "case_id": pair.case_id,
        "group": pair.group,
        "seed": pair.seed,
        "duration_s": pair.duration_s,
        "arm_order": list(pair.arm_order),
        "reference": reference,
        "candidate": candidate,
        "business_semantics": semantics,
        "business_semantics_passed": bool(semantics["passed"]),
        "finite_state_passed": (
            bool(reference["finite_state"])
            and bool(candidate["finite_state"])
        ),
        "truth_isolation_passed": (
            reference["online_truth_use_count"] == 0
            and candidate["online_truth_use_count"] == 0
        ),
        "implementation_identity_passed": (
            reference["implementation_identity_passed"]
            and candidate["implementation_identity_passed"]
        ),
        "structured_jacobian_audit_passed": bool(audit_passed),
        "structured_jacobian_workload_audit": workload_audit,
        "artifact_provenance_passed": bool(
            artifact_provenance_passed
        ),
        "performance": performance,
    }


def _evaluate_arm(
    binding: D1StructuredJacobianArmBinding,
    *,
    pair: D1StructuredJacobianPairBinding,
    expected_commit: str,
) -> dict[str, Any]:
    context = f"{pair.case_id} {binding.arm}"
    episode = binding.episode_dir
    paths = {
        name: episode / name for name in _base._CONSUMED_EPISODE_FILES
    }
    for name, path in paths.items():
        if not path.is_file():
            raise D1StructuredJacobianEvidenceError(
                f"{context} missing {name}"
            )
    manifest, manifest_raw = _load_mapping(paths["manifest.json"])
    config, config_raw = _load_mapping(paths["scenario_config.json"])
    summary, summary_raw = _load_mapping(paths["summary.json"])
    governance, governance_raw = _load_mapping(
        paths["observation_governance_audit.json"]
    )
    runtime_profile = _validate_arm_provenance(
        pair=pair,
        binding=binding,
        expected_commit=expected_commit,
        manifest=manifest,
        config=config,
        summary=summary,
        governance=governance,
    )
    online_message_count = _strict_jsonl_count(
        paths["online_observations.jsonl"]
    )
    diagnostics, audit = _validate_structured_jacobian_identity(
        arm=binding.arm,
        expected=binding.implementation,
        runtime_profile=runtime_profile,
        summary=summary,
        governance=governance,
        context=context,
    )
    stages = {
        name: _load_stage(paths["stage_timings.csv"], stage_name)
        for name, stage_name in _STAGES.items()
    }
    resource = _load_resource_metrics(binding.resource_path)
    _strict_jsonl_count(paths["offline_truth_labels.jsonl"])
    _strict_jsonl_count(paths["offline_proximity_intercepts.jsonl"])
    try:
        _base._validate_truth_state_finite(
            paths["offline_truth_state.npz"]
        )
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1StructuredJacobianEvidenceError(str(exc)) from exc
    stderr_audit = _validate_stderr(binding.stderr_path, context)
    metrics = {
        "d1_fusion_wall_s": stages["d1_fusion"]["wall_time_s"],
        "d1_fusion_p50_ms": stages["d1_fusion"]["p50_wall_time_ms"],
        "d1_fusion_p95_ms": stages["d1_fusion"]["p95_wall_time_ms"],
        "d1_fusion_max_ms": stages["d1_fusion"]["max_wall_time_ms"],
        "core_wall_s": _finite_nonnegative(
            summary.get("wall_time_s"),
            f"{context} summary wall_time_s",
            positive=True,
        ),
        "external_elapsed_s": resource["external_elapsed_s"],
        "real_time_factor": _finite_nonnegative(
            summary.get("real_time_factor"),
            f"{context} summary real_time_factor",
        ),
        "d1_scan_input_wall_s": stages["d1_scan_input"]["wall_time_s"],
        "d2_association_wall_s": stages[
            "d2_association"
        ]["wall_time_s"],
        "maximum_rss_kib": resource["maximum_rss_kib"],
    }
    input_sha256 = {
        "manifest.json": _base._sha256_bytes(manifest_raw),
        "scenario_config.json": _base._sha256_bytes(config_raw),
        "summary.json": _base._sha256_bytes(summary_raw),
        "observation_governance_audit.json": _base._sha256_bytes(
            governance_raw
        ),
        "stage_timings.csv": _base._file_sha256(
            paths["stage_timings.csv"]
        ),
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
        "stdout": _base._file_sha256(binding.stdout_path),
        "stderr": _base._file_sha256(binding.stderr_path),
    }
    artifact_provenance = {
        "passed": (
            set(input_sha256) == _REQUIRED_HASH_KEYS
            and all(
                isinstance(value, str)
                and len(value) == 64
                and all(
                    character in "0123456789abcdef"
                    for character in value
                )
                for value in input_sha256.values()
            )
        ),
        "path_count": len(input_sha256),
        "required_path_count": len(_REQUIRED_HASH_KEYS),
        "schema_versions": {
            "config": config["schema_version"],
            "runtime_profile": runtime_profile["schema_version"],
            "governance": governance["schema_version"],
            "stage_timings": "scalable3d-stage-timings-v2",
            "structured_jacobian_diagnostics": diagnostics["schema_version"],
        },
        "input_file_sha256": input_sha256,
    }
    if not artifact_provenance["passed"]:
        raise D1StructuredJacobianEvidenceError(
            f"{context} artifact provenance is incomplete"
        )
    return {
        "arm": binding.arm,
        "expected_implementation": binding.implementation,
        "episode_dir": str(binding.episode_dir),
        "resource_path": str(binding.resource_path),
        "git_commit": manifest["git_commit"],
        "repository_dirty": manifest["repository_dirty"],
        "config_schema_version": config["schema_version"],
        "runtime_profile_schema_version": runtime_profile[
            "schema_version"
        ],
        "governance_schema_version": governance["schema_version"],
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
        "online_message_count": online_message_count,
        "implementation_identity_passed": True,
        "structured_jacobian_diagnostics": diagnostics,
        "structured_jacobian_audit": audit,
        "artifact_provenance": artifact_provenance,
        "business_count_snapshot": _business_count_snapshot(summary),
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
    *,
    pair: D1StructuredJacobianPairBinding,
    binding: D1StructuredJacobianArmBinding,
    expected_commit: str,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> Mapping[str, Any]:
    context = f"{pair.case_id} {binding.arm}"
    if manifest.get("git_commit") != expected_commit:
        raise D1StructuredJacobianEvidenceError(
            f"{context} source commit mismatch"
        )
    if manifest.get("repository_dirty") is not False:
        raise D1StructuredJacobianEvidenceError(
            f"{context} repository is dirty"
        )
    if manifest.get("config_sha256") != _base._canonical_sha256(config):
        raise D1StructuredJacobianEvidenceError(
            f"{context} config_sha256 mismatch"
        )
    runtime_profile = _required_mapping(
        manifest.get("runtime_profile"),
        f"{context} runtime_profile",
    )
    if manifest.get("runtime_profile_sha256") != _base._canonical_sha256(
        runtime_profile
    ):
        raise D1StructuredJacobianEvidenceError(
            f"{context} runtime_profile_sha256 mismatch"
        )
    _expect(
        config.get("schema_version"),
        _EXPECTED_CONFIG_SCHEMA_VERSION,
        f"{context} config schema_version",
    )
    _expect(
        runtime_profile.get("schema_version"),
        _EXPECTED_RUNTIME_PROFILE_SCHEMA_VERSION,
        f"{context} runtime profile schema_version",
    )
    _expect(
        governance.get("schema_version"),
        _EXPECTED_GOVERNANCE_SCHEMA_VERSION,
        f"{context} governance schema_version",
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
            raise D1StructuredJacobianEvidenceError(
                f"{context} {label} {field} mismatch"
            )
    _expect_finite_equal(
        config.get("duration_s"),
        pair.duration_s,
        f"{context} config duration_s",
    )
    _expect_finite_equal(
        summary.get("simulated_duration_s"),
        pair.duration_s,
        f"{context} summary simulated_duration_s",
    )
    if summary.get("finite_state") is not True:
        raise D1StructuredJacobianEvidenceError(
            f"{context} finite_state must be true"
        )
    if summary.get("online_truth_use_count") != 0:
        raise D1StructuredJacobianEvidenceError(
            f"{context} online_truth_use_count must be zero"
        )
    if governance.get("online_truth_use_count") != 0:
        raise D1StructuredJacobianEvidenceError(
            f"{context} governance online truth count must be zero"
        )
    return runtime_profile


def _validate_structured_jacobian_identity(
    *,
    arm: str,
    expected: str,
    runtime_profile: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
    context: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    selector_field = "d1_structured_numerical_jacobian_implementation"
    diagnostics_field = "d1_structured_numerical_jacobian_diagnostics"
    configuration = _required_mapping(
        runtime_profile.get("configuration"),
        f"{context} runtime configuration",
    )
    final = _required_mapping(
        summary.get("module_final_diagnostics"),
        f"{context} module_final_diagnostics",
    )
    nested_governance = _required_mapping(
        final.get("observation_governance"),
        f"{context} nested observation_governance",
    )
    selectors = {
        "runtime_profile": runtime_profile.get(selector_field),
        "runtime_profile.configuration": configuration.get(selector_field),
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
        raise D1StructuredJacobianEvidenceError(
            f"{context} implementation identity mismatch: "
            + ", ".join(mismatches)
        )
    initial = _required_mapping(
        runtime_profile.get(diagnostics_field),
        f"{context} initial structured-Jacobian diagnostics",
    )
    expected_candidate = arm == _CANDIDATE_ARM
    expected_initial = {
        "schema_version",
        "implementation_id",
        "candidate_enabled",
        "operation_counts",
        "conservation",
    }
    if set(initial) != expected_initial:
        raise D1StructuredJacobianEvidenceError(
            f"{context} initial diagnostics fields mismatch"
        )
    _expect(
        initial.get("schema_version"),
        D1_STRUCTURED_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION,
        f"{context} initial diagnostics schema",
    )
    _expect(
        initial.get("implementation_id"),
        _IMPLEMENTATION_IDS[arm],
        f"{context} initial diagnostics implementation_id",
    )
    if initial.get("candidate_enabled") is not expected_candidate:
        raise D1StructuredJacobianEvidenceError(
            f"{context} initial diagnostics candidate_enabled mismatch"
        )
    if initial.get("operation_counts") != {}:
        raise D1StructuredJacobianEvidenceError(
            f"{context} initial operation_counts must be empty"
        )
    expected_conservation = {
        "attempt_equals_success_plus_failure": True,
        "attempt_equals_reference_plus_candidate": True,
    }
    if initial.get("conservation") != expected_conservation:
        raise D1StructuredJacobianEvidenceError(
            f"{context} initial conservation mismatch"
        )

    diagnostics_locations = {
        "summary": _required_mapping(
            summary.get(diagnostics_field),
            f"{context} summary diagnostics",
        ),
        "module_final": _required_mapping(
            final.get(diagnostics_field),
            f"{context} module final diagnostics",
        ),
        "nested_governance": _required_mapping(
            nested_governance.get(diagnostics_field),
            f"{context} nested governance diagnostics",
        ),
        "governance": _required_mapping(
            governance.get(diagnostics_field),
            f"{context} governance diagnostics",
        ),
    }
    canonical = diagnostics_locations["summary"]
    for name, diagnostics in diagnostics_locations.items():
        if diagnostics != canonical:
            raise D1StructuredJacobianEvidenceError(
                f"{context} diagnostics mismatch at {name}"
            )
    normalized, operation_audit = _validate_final_diagnostics(
        canonical,
        arm=arm,
        context=context,
    )
    return normalized, {
        "passed": True,
        "implementation_identity_passed": True,
        "diagnostics_schema_passed": True,
        "candidate_flag_passed": True,
        "four_surface_diagnostics_equal": True,
        "selector_surface_count": len(selectors),
        "diagnostics_surface_count": len(diagnostics_locations),
        **operation_audit,
    }


def _validate_final_diagnostics(
    diagnostics: Mapping[str, Any],
    *,
    arm: str,
    context: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    required_fields = {
        "schema_version",
        "implementation_id",
        "candidate_enabled",
        "operation_counts",
        "conservation",
    }
    if set(diagnostics) != required_fields:
        raise D1StructuredJacobianEvidenceError(
            f"{context} final diagnostics fields mismatch"
        )
    _expect(
        diagnostics.get("schema_version"),
        D1_STRUCTURED_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION,
        f"{context} diagnostics schema",
    )
    _expect(
        diagnostics.get("implementation_id"),
        _IMPLEMENTATION_IDS[arm],
        f"{context} diagnostics implementation_id",
    )
    expected_candidate = arm == _CANDIDATE_ARM
    if diagnostics.get("candidate_enabled") is not expected_candidate:
        raise D1StructuredJacobianEvidenceError(
            f"{context} diagnostics candidate_enabled mismatch"
        )
    conservation = _required_mapping(
        diagnostics.get("conservation"),
        f"{context} diagnostics conservation",
    )
    expected_conservation = {
        "attempt_equals_success_plus_failure": True,
        "attempt_equals_reference_plus_candidate": True,
    }
    if conservation != expected_conservation:
        raise D1StructuredJacobianEvidenceError(
            f"{context} diagnostics conservation mismatch"
        )
    raw_operations = _required_mapping(
        diagnostics.get("operation_counts"),
        f"{context} operation_counts",
    )
    unknown = set(raw_operations) - _OPERATION_FIELDS
    if unknown:
        raise D1StructuredJacobianEvidenceError(
            f"{context} operation_counts contain unknown fields: "
            f"{sorted(unknown)}"
        )
    operations = {
        name: _nonnegative_integer(
            raw_operations.get(name, 0),
            f"{context} {name}",
        )
        for name in sorted(_OPERATION_FIELDS)
    }
    attempts = operations["jacobian_attempt_count"]
    success = operations["jacobian_success_count"]
    failures = operations["jacobian_failure_count"]
    reference_calls = operations["reference_call_count"]
    candidate_calls = operations["structured_candidate_call_count"]
    probe_evaluations = operations["output_probe_evaluation_count"]
    probe_elisions = operations["output_probe_elision_count"]
    inactive_elisions = operations[
        "inactive_state_column_elision_count"
    ]
    measurement_evaluations = operations[
        "measurement_function_evaluation_count"
    ]
    if attempts <= 0:
        raise D1StructuredJacobianEvidenceError(
            f"{context} jacobian_attempt_count must be positive"
        )
    if success != attempts or failures != 0:
        raise D1StructuredJacobianEvidenceError(
            f"{context} attempt/success/failure conservation failed"
        )
    if reference_calls + candidate_calls != attempts:
        raise D1StructuredJacobianEvidenceError(
            f"{context} reference/candidate call conservation failed"
        )
    if expected_candidate:
        candidate_valid = (
            reference_calls == 0
            and candidate_calls == attempts
            and probe_evaluations == 0
            and probe_elisions == attempts
            and inactive_elisions > 0
            and measurement_evaluations > 0
            and measurement_evaluations < 13 * attempts
            and measurement_evaluations + 2 * inactive_elisions
            == 12 * attempts
        )
        if not candidate_valid:
            raise D1StructuredJacobianEvidenceError(
                f"{context} candidate operation conservation failed"
            )
    else:
        reference_valid = (
            reference_calls == attempts
            and candidate_calls == 0
            and probe_evaluations == attempts
            and probe_elisions == 0
            and inactive_elisions == 0
            and measurement_evaluations == 13 * attempts
        )
        if not reference_valid:
            raise D1StructuredJacobianEvidenceError(
                f"{context} reference operation conservation failed"
            )
    normalized = {
        "schema_version": diagnostics["schema_version"],
        "implementation_id": diagnostics["implementation_id"],
        "candidate_enabled": diagnostics["candidate_enabled"],
        "operation_counts": operations,
        "conservation": dict(conservation),
    }
    return normalized, {
        "operation_conservation_passed": True,
        "attempt_count": attempts,
        "success_count": success,
        "failure_count": failures,
        "measurement_function_evaluation_count": measurement_evaluations,
    }


def _validate_pair_structured_jacobian_workload(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    context: str,
) -> dict[str, Any]:
    reference_operations = _required_mapping(
        reference.get("operation_counts"),
        f"{context} reference operation_counts",
    )
    candidate_operations = _required_mapping(
        candidate.get("operation_counts"),
        f"{context} candidate operation_counts",
    )
    reference_attempts = int(
        reference_operations["jacobian_attempt_count"]
    )
    candidate_attempts = int(
        candidate_operations["jacobian_attempt_count"]
    )
    if reference_attempts != candidate_attempts:
        raise D1StructuredJacobianEvidenceError(
            f"{context} Jacobian attempt workloads differ between arms"
        )
    reference_evaluations = int(
        reference_operations["measurement_function_evaluation_count"]
    )
    candidate_evaluations = int(
        candidate_operations["measurement_function_evaluation_count"]
    )
    if reference_evaluations <= 0:
        raise D1StructuredJacobianEvidenceError(
            f"{context} reference measurement evaluation denominator is zero"
        )
    return {
        "passed": True,
        "same_jacobian_attempt_workload": True,
        "reference_jacobian_attempt_count": reference_attempts,
        "candidate_jacobian_attempt_count": candidate_attempts,
        "reference_measurement_function_evaluation_count": (
            reference_evaluations
        ),
        "candidate_measurement_function_evaluation_count": (
            candidate_evaluations
        ),
        "candidate_measurement_evaluation_reduction_pct": (
            (reference_evaluations - candidate_evaluations)
            / reference_evaluations
            * 100.0
        ),
    }


def _normalized_runtime_profile(
    runtime_profile: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(runtime_profile))
    selector = "d1_structured_numerical_jacobian_implementation"
    if selector not in normalized:
        raise D1StructuredJacobianEvidenceError(
            "normalized runtime profile lacks structured-Jacobian selector"
        )
    normalized[selector] = _TREATMENT_MARKER
    configuration = normalized.get("configuration")
    if not isinstance(configuration, dict) or selector not in configuration:
        raise D1StructuredJacobianEvidenceError(
            "normalized runtime configuration lacks selector"
        )
    configuration[selector] = _TREATMENT_MARKER
    _normalize_diagnostics(normalized, "normalized runtime profile")
    return normalized


def _normalized_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(summary))
    for field in (
        "episode_id",
        "wall_time_s",
        "real_time_factor",
        "d1_structured_numerical_jacobian_implementation",
        "d1_structured_numerical_jacobian_diagnostics",
    ):
        if field not in normalized:
            raise D1StructuredJacobianEvidenceError(
                f"normalized summary lacks {field}"
            )
    normalized["episode_id"] = _TREATMENT_DERIVED_ID_MARKER
    normalized["wall_time_s"] = _PERFORMANCE_MARKER
    normalized["real_time_factor"] = _PERFORMANCE_MARKER
    _normalize_structured_jacobian_fields(
        normalized,
        "normalized summary",
    )
    final = normalized.get("module_final_diagnostics")
    if not isinstance(final, dict):
        raise D1StructuredJacobianEvidenceError(
            "normalized summary lacks mutable module_final_diagnostics"
        )
    if "stage_timings" not in final:
        raise D1StructuredJacobianEvidenceError(
            "normalized summary lacks final stage_timings"
        )
    final["stage_timings"] = _PERFORMANCE_MARKER
    _normalize_structured_jacobian_fields(
        final,
        "normalized module final",
    )
    nested = final.get("observation_governance")
    if not isinstance(nested, Mapping):
        raise D1StructuredJacobianEvidenceError(
            "normalized summary lacks nested observation_governance"
        )
    final["observation_governance"] = _normalized_governance(nested)
    return normalized


def _normalized_governance(
    governance: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(governance))
    _normalize_structured_jacobian_fields(
        normalized,
        "normalized governance",
    )
    return normalized


def _normalize_structured_jacobian_fields(
    mapping: dict[str, Any],
    context: str,
) -> None:
    selector = "d1_structured_numerical_jacobian_implementation"
    if selector not in mapping:
        raise D1StructuredJacobianEvidenceError(
            f"{context} lacks structured-Jacobian selector"
        )
    mapping[selector] = _TREATMENT_MARKER
    _normalize_diagnostics(mapping, context)


def _normalize_diagnostics(
    mapping: dict[str, Any],
    context: str,
) -> None:
    field = "d1_structured_numerical_jacobian_diagnostics"
    if not isinstance(mapping.get(field), Mapping):
        raise D1StructuredJacobianEvidenceError(
            f"{context} lacks structured-Jacobian diagnostics"
        )
    mapping[field] = {"value": _TREATMENT_MARKER}


def _business_count_snapshot(
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    final = _required_mapping(
        summary.get("module_final_diagnostics"),
        "business module_final_diagnostics",
    )
    return {
        "summary": {
            field: copy.deepcopy(summary.get(field))
            for field in _BUSINESS_SUMMARY_FIELDS
        },
        "module_final": {
            field: copy.deepcopy(final.get(field))
            for field in _MODULE_FINAL_COUNT_FIELDS
        },
    }


def _compare_pair_business_semantics(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    reference_input = reference["_semantic_input"]
    candidate_input = candidate["_semantic_input"]
    cross = compare_cross_build_episodes(
        reference_input["episode_dir"],
        candidate_input["episode_dir"],
    )
    if cross.get("schema_version") != (
        CROSS_BUILD_EQUIVALENCE_SCHEMA_VERSION
    ):
        raise D1StructuredJacobianEvidenceError(
            "cross-build reader returned an unsupported schema"
        )
    cross_checks = _required_mapping(
        cross.get("checks"), "cross-build checks"
    )
    required_cross_checks = {
        key: value
        for key, value in cross_checks.items()
        if key != "same_runtime_profile"
    }
    checks = {
        "same_source_commit": (
            reference["git_commit"] == candidate["git_commit"]
        ),
        "same_scenario_config": (
            reference["config_sha256"] == candidate["config_sha256"]
            and reference_input["config"] == candidate_input["config"]
        ),
        "normalized_runtime_profile_equal": (
            reference["normalized_runtime_profile_sha256"]
            == candidate["normalized_runtime_profile_sha256"]
        ),
        "normalized_nonperformance_summary_equal": (
            reference["normalized_summary_sha256"]
            == candidate["normalized_summary_sha256"]
        ),
        "governance_equal": (
            reference["normalized_governance_sha256"]
            == candidate["normalized_governance_sha256"]
        ),
        "business_count_snapshot_equal": (
            reference["business_count_snapshot"]
            == candidate["business_count_snapshot"]
        ),
        "message_count_equal": (
            reference["online_message_count"]
            == candidate["online_message_count"]
        ),
        "cross_build_required_checks_passed": (
            bool(required_cross_checks)
            and all(
                value is True
                for value in required_cross_checks.values()
            )
        ),
        "online_payloads_equal": (
            cross_checks.get("normalized_online_payloads_equal") is True
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
        "treatment_normalization": {
            "scope": (
                "structured_jacobian_selector_diagnostics_performance_and_"
                "treatment_derived_episode_id_only"
            ),
            "diagnostics_validated_separately": True,
            "other_business_fields_ignored": False,
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
        "structured_jacobian_audit_pass_count": sum(
            bool(pair["structured_jacobian_audit_passed"]) for pair in ordered
        ),
        "artifact_provenance_pass_count": sum(
            bool(pair["artifact_provenance_passed"])
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
    try:
        lower, upper = _base._bootstrap_mean_ci(
            raw,
            resamples=bootstrap_resamples,
            rng_seed=bootstrap_seed,
        )
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1StructuredJacobianEvidenceError(str(exc)) from exc
    ratio_raw = (fmean(candidate) - fmean(reference)) / fmean(reference)
    ratio_improvement = (
        -ratio_raw if metric in _LOWER_IS_BETTER else ratio_raw
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
            "raw_relative_change": ratio_raw,
            "improvement_pct": ratio_improvement * 100.0,
        },
        "candidate_better_count": sum(
            bool(item["candidate_better"]) for item in comparisons
        ),
        "maximum_pair_raw_relative_change_pct": max(raw) * 100.0,
    }


def _aggregate_structured_jacobian_diagnostics(
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    for group in (*_GROUPS, "all"):
        selected = (
            list(pairs)
            if group == "all"
            else [pair for pair in pairs if pair["group"] == group]
        )
        reference_evaluations = sum(
            int(
                pair["structured_jacobian_workload_audit"][
                    "reference_measurement_function_evaluation_count"
                ]
            )
            for pair in selected
        )
        candidate_evaluations = sum(
            int(
                pair["structured_jacobian_workload_audit"][
                    "candidate_measurement_function_evaluation_count"
                ]
            )
            for pair in selected
        )
        reference_attempts = sum(
            int(
                pair["structured_jacobian_workload_audit"][
                    "reference_jacobian_attempt_count"
                ]
            )
            for pair in selected
        )
        candidate_attempts = sum(
            int(
                pair["structured_jacobian_workload_audit"][
                    "candidate_jacobian_attempt_count"
                ]
            )
            for pair in selected
        )
        if reference_evaluations <= 0:
            raise D1StructuredJacobianEvidenceError(
                f"{group} reference measurement evaluation total is zero"
            )
        groups[group] = {
            "pair_count": len(selected),
            "reference_jacobian_attempt_count": reference_attempts,
            "candidate_jacobian_attempt_count": candidate_attempts,
            "reference_measurement_function_evaluation_count": (
                reference_evaluations
            ),
            "candidate_measurement_function_evaluation_count": (
                candidate_evaluations
            ),
            "candidate_measurement_evaluation_reduction_pct": (
                (reference_evaluations - candidate_evaluations)
                / reference_evaluations
                * 100.0
            ),
        }
    return {
        "schema_version": (
            "d6.d1_structured_jacobian_diagnostics_aggregate.v1"
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
    short_d1 = groups["short"]["metrics"]["d1_fusion_wall_s"]
    long_d1 = groups["long"]["metrics"]["d1_fusion_wall_s"]
    short_core = groups["short"]["metrics"]["core_wall_s"]
    long_core = groups["long"]["metrics"]["core_wall_s"]
    short_scan = groups["short"]["metrics"]["d1_scan_input_wall_s"]
    long_scan = groups["long"]["metrics"]["d1_scan_input_wall_s"]
    short_d2 = groups["short"]["metrics"]["d2_association_wall_s"]
    long_d2 = groups["long"]["metrics"]["d2_association_wall_s"]
    rss_groups = [
        groups[group]["metrics"]["maximum_rss_kib"]
        for group in _GROUPS
    ]
    diagnostics_all = _required_mapping(
        _required_mapping(
            diagnostics_aggregate.get("groups"),
            "structured-Jacobian aggregate groups",
        ).get("all"),
        "structured-Jacobian aggregate all group",
    )
    semantic_count = sum(
        bool(pair["business_semantics_passed"]) for pair in pairs
    )
    finite_count = sum(
        bool(pair["finite_state_passed"]) for pair in pairs
    )
    truth_use_count = sum(
        int(pair[arm]["online_truth_use_count"])
        for pair in pairs
        for arm in _ARMS
    )
    identity_count = sum(
        bool(pair["implementation_identity_passed"])
        for pair in pairs
    )
    audit_count = sum(
        bool(pair["structured_jacobian_audit_passed"]) for pair in pairs
    )
    provenance_count = sum(
        bool(pair["artifact_provenance_passed"]) for pair in pairs
    )
    metric_count = sum(
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
    rss_mean_increase_pct = max(
        item["raw_relative_change"]["mean"] * 100.0
        for item in rss_groups
    )
    any_pair_rss_increase_pct = max(
        float(
            pair["performance"]["maximum_rss_kib"][
                "raw_relative_change_pct"
            ]
        )
        for pair in pairs
    )
    measurement_reduction = float(
        diagnostics_all[
            "candidate_measurement_evaluation_reduction_pct"
        ]
    )
    return {
        "all_pairs_business_semantics_equal": _gate(
            semantic_count,
            pair_count,
            "==",
            semantic_count == pair_count,
            "one_or_more_pair_business_semantics_mismatch",
        ),
        "all_pairs_finite_state": _gate(
            finite_count,
            pair_count,
            "==",
            finite_count == pair_count,
            "one_or_more_pair_finite_state_failed",
        ),
        "all_pairs_online_truth_use_count": _gate(
            truth_use_count,
            thresholds["all_pairs_online_truth_use_count"],
            "==",
            truth_use_count
            == thresholds["all_pairs_online_truth_use_count"],
            "one_or_more_arm_online_truth_use_nonzero",
        ),
        "all_pairs_explicit_implementation_identity": _gate(
            identity_count,
            pair_count,
            "==",
            identity_count == pair_count,
            "one_or_more_pair_implementation_identity_failed",
        ),
        "all_pairs_structured_jacobian_audit_valid": _gate(
            audit_count,
            pair_count,
            "==",
            audit_count == pair_count,
            "one_or_more_pair_structured_jacobian_audit_failed",
        ),
        "all_pairs_artifact_provenance_complete": _gate(
            provenance_count,
            pair_count,
            "==",
            provenance_count == pair_count,
            "one_or_more_pair_artifact_provenance_incomplete",
        ),
        "required_performance_metrics_available": _gate(
            metric_count,
            pair_count,
            "==",
            metric_count == pair_count,
            "one_or_more_required_performance_metrics_unavailable",
        ),
        "short_minimum_candidate_faster_count": _gate(
            short_d1["candidate_better_count"],
            thresholds["short_minimum_candidate_faster_count"],
            ">=",
            short_d1["candidate_better_count"]
            >= thresholds["short_minimum_candidate_faster_count"],
            "short_candidate_faster_count_below_threshold",
        ),
        "short_minimum_d1_fusion_improvement_pct": _gate(
            short_d1["improvement_pct"]["mean"],
            thresholds["short_minimum_d1_fusion_improvement_pct"],
            ">=",
            short_d1["improvement_pct"]["mean"]
            >= thresholds["short_minimum_d1_fusion_improvement_pct"],
            "short_d1_fusion_improvement_below_threshold",
            unit="pct",
        ),
        "short_bootstrap_relative_change_upper_bound_pct": _gate(
            short_d1["raw_relative_change"]["bootstrap_95_ci"]["upper"]
            * 100.0,
            thresholds["short_bootstrap_relative_change_upper_bound_pct"],
            "<",
            short_d1["raw_relative_change"]["bootstrap_95_ci"]["upper"]
            * 100.0
            < thresholds[
                "short_bootstrap_relative_change_upper_bound_pct"
            ],
            "short_bootstrap_upper_bound_not_below_zero",
            unit="pct",
        ),
        "long_minimum_candidate_faster_count": _gate(
            long_d1["candidate_better_count"],
            thresholds["long_minimum_candidate_faster_count"],
            ">=",
            long_d1["candidate_better_count"]
            >= thresholds["long_minimum_candidate_faster_count"],
            "long_candidate_faster_count_below_threshold",
        ),
        "long_minimum_d1_fusion_improvement_pct": _gate(
            long_d1["improvement_pct"]["mean"],
            thresholds["long_minimum_d1_fusion_improvement_pct"],
            ">=",
            long_d1["improvement_pct"]["mean"]
            >= thresholds["long_minimum_d1_fusion_improvement_pct"],
            "long_d1_fusion_improvement_below_threshold",
            unit="pct",
        ),
        "short_minimum_core_wall_improvement_pct": _gate(
            short_core["improvement_pct"]["mean"],
            thresholds["short_minimum_core_wall_improvement_pct"],
            ">=",
            short_core["improvement_pct"]["mean"]
            >= thresholds["short_minimum_core_wall_improvement_pct"],
            "short_core_wall_improvement_below_threshold",
            unit="pct",
        ),
        "long_minimum_core_wall_improvement_pct": _gate(
            long_core["improvement_pct"]["mean"],
            thresholds["long_minimum_core_wall_improvement_pct"],
            ">=",
            long_core["improvement_pct"]["mean"]
            >= thresholds["long_minimum_core_wall_improvement_pct"],
            "long_core_wall_improvement_below_threshold",
            unit="pct",
        ),
        "maximum_short_d1_scan_input_mean_increase_pct": _gate(
            short_scan["raw_relative_change"]["mean"] * 100.0,
            thresholds[
                "maximum_short_d1_scan_input_mean_increase_pct"
            ],
            "<=",
            short_scan["raw_relative_change"]["mean"] * 100.0
            <= thresholds[
                "maximum_short_d1_scan_input_mean_increase_pct"
            ],
            "short_d1_scan_input_increase_above_threshold",
            unit="pct",
        ),
        "maximum_long_d1_scan_input_mean_increase_pct": _gate(
            long_scan["raw_relative_change"]["mean"] * 100.0,
            thresholds[
                "maximum_long_d1_scan_input_mean_increase_pct"
            ],
            "<=",
            long_scan["raw_relative_change"]["mean"] * 100.0
            <= thresholds[
                "maximum_long_d1_scan_input_mean_increase_pct"
            ],
            "long_d1_scan_input_increase_above_threshold",
            unit="pct",
        ),
        "maximum_short_d2_association_mean_increase_pct": _gate(
            short_d2["raw_relative_change"]["mean"] * 100.0,
            thresholds[
                "maximum_short_d2_association_mean_increase_pct"
            ],
            "<=",
            short_d2["raw_relative_change"]["mean"] * 100.0
            <= thresholds[
                "maximum_short_d2_association_mean_increase_pct"
            ],
            "short_d2_association_increase_above_threshold",
            unit="pct",
        ),
        "maximum_long_d2_association_mean_increase_pct": _gate(
            long_d2["raw_relative_change"]["mean"] * 100.0,
            thresholds[
                "maximum_long_d2_association_mean_increase_pct"
            ],
            "<=",
            long_d2["raw_relative_change"]["mean"] * 100.0
            <= thresholds[
                "maximum_long_d2_association_mean_increase_pct"
            ],
            "long_d2_association_increase_above_threshold",
            unit="pct",
        ),
        "maximum_rss_mean_increase_pct": _gate(
            rss_mean_increase_pct,
            thresholds["maximum_rss_mean_increase_pct"],
            "<=",
            rss_mean_increase_pct
            <= thresholds["maximum_rss_mean_increase_pct"],
            "short_or_long_rss_mean_increase_above_threshold",
            unit="pct",
        ),
        "maximum_any_pair_rss_increase_pct": _gate(
            any_pair_rss_increase_pct,
            thresholds["maximum_any_pair_rss_increase_pct"],
            "<=",
            any_pair_rss_increase_pct
            <= thresholds["maximum_any_pair_rss_increase_pct"],
            "one_or_more_pair_rss_increase_above_threshold",
            unit="pct",
        ),
        "minimum_candidate_measurement_evaluation_reduction_pct": _gate(
            measurement_reduction,
            thresholds[
                "minimum_candidate_measurement_evaluation_reduction_pct"
            ],
            ">=",
            measurement_reduction
            >= thresholds[
                "minimum_candidate_measurement_evaluation_reduction_pct"
            ],
            "candidate_measurement_evaluation_reduction_below_threshold",
            unit="pct",
        ),
    }


def _gate(
    actual: Any,
    threshold: Any,
    comparator: str,
    passed: bool,
    reason: str,
    *,
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


def write_d1_structured_jacobian_multiseed_report(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write deterministic D6 products outside the raw evidence root."""

    if result.get("schema_version") != (
        D1_STRUCTURED_JACOBIAN_MULTISEED_EVALUATION_SCHEMA_VERSION
    ):
        raise ValueError(
            "unsupported structured numerical Jacobian evaluation schema"
        )
    contract = _required_mapping(
        result.get("input_contract"), "report input contract"
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
        / "d1_structured_numerical_jacobian_multiseed_evaluation.json",
        "compact_json": directory
        / "d1_structured_numerical_jacobian_multiseed_compact.json",
        "pairs_csv": directory
        / "d1_structured_numerical_jacobian_multiseed_pairs.csv",
        "markdown": directory
        / "D1_STRUCTURED_NUMERICAL_JACOBIAN_MULTISEED_REPORT_CN.md",
        "sha256sums": directory / "SHA256SUMS",
    }
    paths["evaluation_json"].write_text(
        _base._json_text(result), encoding="utf-8"
    )
    paths["compact_json"].write_text(
        _base._json_text(_compact_output(result)), encoding="utf-8"
    )
    _write_pair_csv(result, paths["pairs_csv"])
    paths["markdown"].write_text(
        render_d1_structured_jacobian_multiseed_markdown(result),
        encoding="utf-8",
    )
    checksum_lines = [
        f"{_base._file_sha256(paths[name])}  {paths[name].name}"
        for name in (
            "compact_json",
            "evaluation_json",
            "markdown",
            "pairs_csv",
        )
    ]
    paths["sha256sums"].write_text(
        "\n".join(sorted(checksum_lines)) + "\n",
        encoding="utf-8",
    )
    return paths


def _compact_output(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": (
            D1_STRUCTURED_JACOBIAN_MULTISEED_COMPACT_SCHEMA_VERSION
        ),
        "evaluation_schema_version": result["schema_version"],
        "evaluation_date": result["evaluation_date"],
        "availability": result["availability"],
        "input_contract": result["input_contract"],
        "scope": result["scope"],
        "groups": result["groups"],
        "structured_jacobian_diagnostics_aggregate": result[
            "structured_jacobian_diagnostics_aggregate"
        ],
        "admission_gates": result["admission_gates"],
        "optimization_admitted": result["optimization_admitted"],
        "system_realtime_gate": result["system_realtime_gate"],
        "system_realtime_gap_closed": result[
            "system_realtime_gap_closed"
        ],
    }


def render_d1_structured_jacobian_multiseed_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the Chinese paired-admission or unavailable report."""

    contract = _required_mapping(
        result["input_contract"], "report input contract"
    )
    availability = _required_mapping(
        result["availability"], "report availability"
    )
    if availability.get("available") is not True:
        return "\n".join(
            [
                "# D1 结构化数值雅可比同提交多种子评估",
                "",
                "## 结论",
                "",
                "正式证据当前不可用，评估失败关闭。",
                (
                    f"原因：`{availability.get('reason')}`。候选 "
                    f"`{CANDIDATE_IMPLEMENTATION}` 保持关闭，默认继续使用 "
                    f"`{REFERENCE_IMPLEMENTATION}`。"
                ),
                "未形成优化准入结论，系统实时缺口也未关闭。",
                "",
                "## 冻结合同",
                "",
                f"- producer commit：`{contract['source_commit']}`。",
                f"- 矩阵 SHA-256：`{contract['matrix_sha256']}`。",
                (
                    "- 预期证据为 13 对、26 个 fresh arm；任何缺失、复用、"
                    "失败、版本错配、路径越界或 dirty source 均保持不可用。"
                ),
                "",
            ]
        )
    groups = _required_mapping(result["groups"], "report groups")
    gates = _required_mapping(
        result["admission_gates"], "report admission gates"
    )
    realtime = _required_mapping(
        result["system_realtime_gate"], "report realtime gate"
    )
    if result["optimization_admitted"]:
        default_status = (
            "本报告只给出冻结矩阵内的准入判断；默认实现切换须由 main "
            "另行实施并保留回退路径。"
        )
    else:
        default_status = (
            f"候选 `{CANDIDATE_IMPLEMENTATION}` 未获准替代参考实现，"
            f"默认仍为 `{REFERENCE_IMPLEMENTATION}`。"
        )
    lines = [
        "# D1 结构化数值雅可比同提交多种子评估",
        "",
        "## 结论",
        "",
        (
            "局部优化准入"
            f"{'通过' if result['optimization_admitted'] else '未通过'}；"
            "系统实时缺口"
            f"{'已关闭' if result['system_realtime_gap_closed'] else '未关闭'}。"
            "两项判定分别计算。"
        ),
        (
            "候选最低实时因子为 "
            f"`{_fmt(realtime['candidate_minimum_real_time_factor'])}`，"
            "系统实时门限为 `>=1.0`。本报告只适用于三维质点仿真，"
            "不代表 AirSim、目标硬件或实飞结果。"
        ),
        default_status,
        "",
        "## 证据范围",
        "",
        f"- 评估日期：`{result['evaluation_date']}`。",
        f"- clean commit：`{contract['source_commit']}`。",
        f"- 冻结矩阵 SHA-256：`{contract['matrix_sha256']}`。",
        (
            f"- 规模：{_TARGET_COUNT} 个目标、{_RESOURCE_COUNT} 个资源、"
            f"{_RECON_COUNT} 个侦察节点。"
        ),
        (
            "- short 组 10 pair，每臂 2.2 秒；long 组 3 pair，"
            "每臂 10 秒；共 13 pair、26 个 fresh arm，"
            "26/26 complete、0 reused、0 failed。"
        ),
        (
            f"- 参考实现 `{REFERENCE_IMPLEMENTATION}`；候选实现 "
            f"`{CANDIDATE_IMPLEMENTATION}`。"
        ),
        "",
        "## 分组结果",
        "",
        "| 组别 | 指标 | 参考均值 | 候选均值 | 改善或增幅 | 候选更优 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    rows = (
        ("d1_fusion_wall_s", "D1 融合墙钟", "improvement"),
        ("core_wall_s", "核心墙钟", "improvement"),
        ("d1_scan_input_wall_s", "D1 扫描输入墙钟", "raw"),
        ("d2_association_wall_s", "D2 关联墙钟", "raw"),
        ("maximum_rss_kib", "最大常驻内存", "raw"),
    )
    for group in _GROUPS:
        label = "短时" if group == "short" else "长时"
        for metric, metric_label, kind in rows:
            item = groups[group]["metrics"][metric]
            change = (
                item["improvement_pct"]["mean"]
                if kind == "improvement"
                else item["raw_relative_change"]["mean"] * 100.0
            )
            lines.append(
                f"| {label} | {metric_label} | "
                f"{_fmt(item['reference']['mean'])} | "
                f"{_fmt(item['candidate']['mean'])} | "
                f"{_fmt(change)}% | "
                f"{item['candidate_better_count']}/{item['pair_count']} |"
            )
    lines.extend(
        [
            "",
            "扫描输入、D2 和内存采用 `(候选-参考)/参考`，负值表示下降。"
            "D1 融合和核心墙钟使用正向改善口径。",
            (
                "全矩阵量测函数求值减少率为 "
                f"`{_fmt(result['structured_jacobian_diagnostics_aggregate']['groups']['all']['candidate_measurement_evaluation_reduction_pct'])}%`。"
            ),
            "",
            "## 准入门",
            "",
            "| 准入门 | 实际值 | 判据 | 结果 |",
            "|---|---:|---:|---:|",
        ]
    )
    for name in sorted(gates):
        gate = gates[name]
        unit = "%" if gate.get("unit") == "pct" else ""
        lines.append(
            f"| `{name}` | {_fmt(gate['actual'])}{unit} | "
            f"`{gate['comparator']} {_fmt(gate['threshold'])}{unit}` | "
            f"{'通过' if gate['passed'] else '失败'} |"
        )
    lines.extend(
        [
            "",
            "## 逐对结果",
            "",
            "| case | D1 改善 | 核心改善 | 扫描输入增幅 | D2 增幅 | "
            "RSS 增幅 | 求值减少 | 操作数守恒 | 语义 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for pair in result["pairs"]:
        performance = pair["performance"]
        conservation = (
            pair["reference"]["structured_jacobian_audit"][
                "operation_conservation_passed"
            ]
            and pair["candidate"]["structured_jacobian_audit"][
                "operation_conservation_passed"
            ]
        )
        lines.append(
            f"| {pair['case_id']} | "
            f"{_fmt(performance['d1_fusion_wall_s']['improvement_pct'])}% | "
            f"{_fmt(performance['core_wall_s']['improvement_pct'])}% | "
            f"{_fmt(performance['d1_scan_input_wall_s']['raw_relative_change_pct'])}% | "
            f"{_fmt(performance['d2_association_wall_s']['raw_relative_change_pct'])}% | "
            f"{_fmt(performance['maximum_rss_kib']['raw_relative_change_pct'])}% | "
            f"{_fmt(pair['structured_jacobian_workload_audit']['candidate_measurement_evaluation_reduction_pct'])}% | "
            f"{'通过' if conservation else '失败'} | "
            f"{'通过' if pair['business_semantics_passed'] else '失败'} |"
        )
    lines.extend(
        [
            "",
            "## 边界",
            "",
            (
                "D6 只归一化预注册的雅可比实现、对应诊断、性能字段和由处理差异"
                "派生的 episode 标识。在线消息、D1/D2 航迹、关联、分配、控制"
                "计数、治理字段、计划谱系和离线真值制品继续逐对比较。"
            ),
            (
                "selector 和完整实现 ID 必须在运行配置、摘要、最终诊断和治理"
                "表面一致；四份最终诊断及操作数守恒必须通过。缺字段、旧 schema、"
                "非 clean commit、reused arm、路径越界、语义不一致或任一在线真值"
                "使用计数非零均失败关闭。"
            ),
            "",
            "## 制品",
            "",
            "- `d1_structured_numerical_jacobian_multiseed_evaluation.json`：完整评估。",
            "- `d1_structured_numerical_jacobian_multiseed_compact.json`：紧凑汇总。",
            "- `d1_structured_numerical_jacobian_multiseed_pairs.csv`：逐 pair 数据。",
            "- `D1_STRUCTURED_NUMERICAL_JACOBIAN_MULTISEED_REPORT_CN.md`：中文报告。",
            "- `SHA256SUMS`：报告制品校验值。",
            "",
        ]
    )
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
        "structured_jacobian_audit_passed",
        "artifact_provenance_passed",
        "reference_jacobian_attempt_count",
        "candidate_jacobian_attempt_count",
        "reference_measurement_function_evaluation_count",
        "candidate_measurement_function_evaluation_count",
        "candidate_measurement_evaluation_reduction_pct",
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
            stream, fieldnames=fieldnames, lineterminator="\n"
        )
        writer.writeheader()
        for pair in result["pairs"]:
            row: dict[str, Any] = {
                "case_id": pair["case_id"],
                "group": pair["group"],
                "seed": pair["seed"],
                "duration_s": pair["duration_s"],
                "business_semantics_passed": pair[
                    "business_semantics_passed"
                ],
                "finite_state_passed": pair["finite_state_passed"],
                "truth_isolation_passed": pair[
                    "truth_isolation_passed"
                ],
                "implementation_identity_passed": pair[
                    "implementation_identity_passed"
                ],
                "structured_jacobian_audit_passed": pair[
                    "structured_jacobian_audit_passed"
                ],
                "artifact_provenance_passed": pair[
                    "artifact_provenance_passed"
                ],
                "reference_jacobian_attempt_count": pair[
                    "structured_jacobian_workload_audit"
                ]["reference_jacobian_attempt_count"],
                "candidate_jacobian_attempt_count": pair[
                    "structured_jacobian_workload_audit"
                ]["candidate_jacobian_attempt_count"],
                "reference_measurement_function_evaluation_count": pair[
                    "structured_jacobian_workload_audit"
                ][
                    "reference_measurement_function_evaluation_count"
                ],
                "candidate_measurement_function_evaluation_count": pair[
                    "structured_jacobian_workload_audit"
                ][
                    "candidate_measurement_function_evaluation_count"
                ],
                "candidate_measurement_evaluation_reduction_pct": pair[
                    "structured_jacobian_workload_audit"
                ]["candidate_measurement_evaluation_reduction_pct"],
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


def _strict_jsonl_count(path: Path) -> int:
    try:
        _base._strict_jsonl_digest(path)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1StructuredJacobianEvidenceError(str(exc)) from exc
    try:
        with path.open("r", encoding="utf-8") as stream:
            return sum(1 for line in stream if line.strip())
    except OSError as exc:
        raise D1StructuredJacobianEvidenceError(
            f"unable to count JSONL records in {path}: {exc}"
        ) from exc


def _load_stage(path: Path, stage_name: str) -> dict[str, Any]:
    try:
        return _base._load_stage(path, stage_name)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1StructuredJacobianEvidenceError(str(exc)) from exc


def _load_resource_metrics(path: Path) -> dict[str, float | int]:
    try:
        return _base._load_resource_metrics(path)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1StructuredJacobianEvidenceError(str(exc)) from exc


def _validate_stderr(path: Path, context: str) -> dict[str, Any]:
    try:
        return _base._validate_stderr(path, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1StructuredJacobianEvidenceError(str(exc)) from exc


def _finite_nonnegative(
    value: Any,
    context: str,
    *,
    positive: bool = False,
) -> float:
    try:
        return _base._finite_nonnegative(
            value, context, positive=positive
        )
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1StructuredJacobianEvidenceError(str(exc)) from exc


def _load_mapping(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        return _base._load_strict_json_mapping(path)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1StructuredJacobianEvidenceError(str(exc)) from exc


def _required_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise D1StructuredJacobianEvidenceError(
            f"{context} must be a mapping"
        )
    return value


def _required_sequence(value: Any, context: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise D1StructuredJacobianEvidenceError(
            f"{context} must be a sequence"
        )
    return value


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise D1StructuredJacobianEvidenceError(
            f"{context} must be non-empty text"
        )
    return value


def _required_commit(value: Any, context: str) -> str:
    try:
        return _base._required_commit(value, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1StructuredJacobianEvidenceError(str(exc)) from exc


def _required_sha256(value: Any, context: str) -> str:
    try:
        return _base._required_sha256(value, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1StructuredJacobianEvidenceError(str(exc)) from exc


def _explicit_path(
    value: Any,
    context: str,
    *,
    require: str | None,
) -> Path:
    try:
        return _base._explicit_path(value, context, require=require)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1StructuredJacobianEvidenceError(str(exc)) from exc


def _require_under_root(path: Path, root: Path, context: str) -> None:
    try:
        _base._require_under_root(path, root, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1StructuredJacobianEvidenceError(str(exc)) from exc


def _expect(actual: Any, expected: Any, context: str) -> None:
    if actual != expected:
        raise D1StructuredJacobianEvidenceError(
            f"{context} mismatch: expected {expected!r}, got {actual!r}"
        )


def _expect_finite_equal(
    actual: Any, expected: float, context: str
) -> None:
    if (
        isinstance(actual, bool)
        or not isinstance(actual, (int, float))
        or not math.isfinite(float(actual))
        or float(actual) != float(expected)
    ):
        raise D1StructuredJacobianEvidenceError(
            f"{context} mismatch: expected {expected!r}, got {actual!r}"
        )


def _nonnegative_integer(value: Any, context: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise D1StructuredJacobianEvidenceError(
            f"{context} must be a nonnegative integer"
        )
    return int(value)


def _case_metadata(
    case: Mapping[str, Any],
) -> tuple[str, str, int, float, tuple[str, ...]]:
    case_id = _required_text(case.get("case_id"), "case_id")
    group = _required_text(case.get("group"), f"{case_id} group")
    seed = case.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise D1StructuredJacobianEvidenceError(
            f"{case_id} seed must be an integer"
        )
    duration = case.get("duration_s")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(float(duration))
        or float(duration) <= 0.0
    ):
        raise D1StructuredJacobianEvidenceError(
            f"{case_id} duration_s must be finite and positive"
        )
    arm_order = tuple(
        _required_text(item, f"{case_id} arm_order item")
        for item in _required_sequence(
            case.get("arm_order"), f"{case_id} arm_order"
        )
    )
    return case_id, group, int(seed), float(duration), arm_order


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
            "Evaluate the frozen structured numerical Jacobian same-commit matrix"
        )
    )
    parser.add_argument(
        "--evidence-manifest",
        required=True,
        help="completed structured numerical Jacobian evidence_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="independent compact D6 output directory",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = evaluate_d1_structured_jacobian_multiseed(
        args.evidence_manifest
    )
    paths = write_d1_structured_jacobian_multiseed_report(
        result, args.output_dir
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
    "D1_STRUCTURED_JACOBIAN_DIAGNOSTICS_SCHEMA_VERSION",
    "D1_STRUCTURED_JACOBIAN_EVALUATION_DATE",
    "D1_STRUCTURED_JACOBIAN_EVIDENCE_SCHEMA_VERSION",
    "D1_STRUCTURED_JACOBIAN_EXPERIMENT_ID",
    "D1_STRUCTURED_JACOBIAN_MATRIX_SCHEMA_VERSION",
    "D1_STRUCTURED_JACOBIAN_MATRIX_SHA256",
    "D1_STRUCTURED_JACOBIAN_MULTISEED_COMPACT_SCHEMA_VERSION",
    "D1_STRUCTURED_JACOBIAN_MULTISEED_EVALUATION_SCHEMA_VERSION",
    "D1_STRUCTURED_JACOBIAN_SOURCE_COMMIT",
    "D1StructuredJacobianEvidence",
    "D1StructuredJacobianEvidenceError",
    "REFERENCE_IMPLEMENTATION",
    "REFERENCE_IMPLEMENTATION_ID",
    "evaluate_d1_structured_jacobian_multiseed",
    "load_d1_structured_jacobian_evidence_manifest",
    "main",
    "render_d1_structured_jacobian_multiseed_markdown",
    "write_d1_structured_jacobian_multiseed_report",
]
