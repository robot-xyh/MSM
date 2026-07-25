"""Independent D6 admission for the D1 association sparse prefilter.

The producer owns episode execution and the preregistered evidence manifest.
This evaluator is a read-only consumer: it validates provenance, reconstructs
the registered diagnostics and business-equivalence checks, computes paired
statistics, and writes reports outside the producer evidence root.
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


D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_EVALUATION_SCHEMA_VERSION = (
    "d6.d1_association_sparse_prefilter_multiseed_evaluation.v1"
)
D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_COMPACT_SCHEMA_VERSION = (
    "d6.d1_association_sparse_prefilter_multiseed_compact.v1"
)
D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-association-sparse-prefilter-multiseed-matrix-v1"
)
D1_ASSOCIATION_SPARSE_PREFILTER_EVIDENCE_SCHEMA_VERSION = (
    "scalable3d-d1-association-sparse-prefilter-multiseed-evidence-v1"
)
D1_ASSOCIATION_SPARSE_PREFILTER_EXECUTION_CONFIG_SCHEMA_VERSION = (
    "d1.association_sparse_prefilter_execution_config.v1"
)
D1_ASSOCIATION_SPARSE_PREFILTER_DIAGNOSTICS_SCHEMA_VERSION = (
    "d1.association_sparse_prefilter_diagnostics.v2"
)
D1_ASSOCIATION_SPARSE_PREFILTER_EXPERIMENT_ID = (
    "d1-association-sparse-prefilter-multiseed-20260725-v1"
)
D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SHA256 = (
    "a7162d014d1c3c0f207355b24a5d7159bf3486d134ca21876f7469d1e915b71d"
)
D1_ASSOCIATION_SPARSE_PREFILTER_SOURCE_COMMIT = (
    "9302ccede2ca513c2235370e1a464fc88bc41150"
)
D1_ASSOCIATION_SPARSE_PREFILTER_EVALUATION_DATE = "2026-07-25"

REFERENCE_IMPLEMENTATION = "disabled_v1"
CANDIDATE_IMPLEMENTATION = "modality_conservative_quadratic_bound_v1"
REFERENCE_IMPLEMENTATION_ID = (
    "d1.fusion.association_sparse_prefilter.disabled.v1"
)
CANDIDATE_IMPLEMENTATION_ID = (
    "d1.fusion.association_sparse_prefilter."
    "modality_conservative_quadratic_bound.v1"
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
_SHORT_SEEDS = tuple(range(1131, 1141))
_LONG_SEEDS = tuple(range(1131, 1134))
_SHORT_DURATION_S = 2.2
_LONG_DURATION_S = 10.0
_VALIDATION_KIND = "association_sparse_prefilter"
_SELECTOR_FIELD = "d1_association_sparse_prefilter_implementation"
_EXECUTION_CONFIG_FIELD = (
    "d1_association_sparse_prefilter_execution_config"
)
_DIAGNOSTICS_FIELD = "d1_association_sparse_prefilter_diagnostics"
_TREATMENT_MARKER = "D6_REGISTERED_ASSOCIATION_SPARSE_PREFILTER_TREATMENT"
_DIAGNOSTICS_MARKER = (
    "D6_REGISTERED_ASSOCIATION_SPARSE_PREFILTER_DIAGNOSTIC"
)
_PERFORMANCE_MARKER = "D6_REGISTERED_PERFORMANCE_DIAGNOSTIC"
_TREATMENT_DERIVED_ID_MARKER = "D6_TREATMENT_DERIVED_EPISODE_ID"

_MODALITIES = (
    "radar",
    "lidar",
    "acoustic",
    "acoustic_3d",
    "eo",
    "other",
)
_NON_RADAR_MODALITIES = tuple(
    modality for modality in _MODALITIES if modality != "radar"
)
_COUNTER_FIELDS = (
    "candidate_pair_count",
    "conservative_prefilter_rejection_count",
    "exact_innovation_solve_count",
    "exact_gate_pass_count",
    "fallback_count",
)
_CONSERVATION_FIELDS = (
    "prefilter_rejections_not_above_candidates",
    "exact_solves_not_above_candidates",
    "exact_gate_passes_not_above_exact_solves",
    "fallbacks_not_above_candidates",
)

_EXPECTED_GATES = {
    "all_pairs_association_sparse_prefilter_audit_valid": True,
    "all_pairs_business_semantics_equal": True,
    "all_pairs_exact_gate_pass_counts_equal": True,
    "all_pairs_explicit_implementation_identity": True,
    "all_pairs_finite_state": True,
    "all_pairs_online_truth_use_count": 0,
    "long_minimum_candidate_faster_count": 2,
    "long_minimum_core_wall_improvement_pct": 0.25,
    "long_minimum_d1_fusion_improvement_pct": 1.0,
    "maximum_any_pair_rss_increase_pct": 5.0,
    "maximum_long_d1_scan_input_mean_increase_pct": 5.0,
    "maximum_long_d2_association_mean_increase_pct": 5.0,
    "maximum_rss_mean_increase_pct": 5.0,
    "maximum_short_d1_scan_input_mean_increase_pct": 5.0,
    "maximum_short_d2_association_mean_increase_pct": 5.0,
    "minimum_candidate_non_radar_exact_solve_reduction_pct": 20.0,
    "short_bootstrap_relative_change_upper_bound_pct": 0.0,
    "short_minimum_candidate_faster_count": 8,
    "short_minimum_core_wall_improvement_pct": 0.25,
    "short_minimum_d1_fusion_improvement_pct": 1.0,
}
_EXPECTED_BOUNDARY = {
    "airsim_evidence": False,
    "bound_policy": "certified_quadratic_norm_inf_upper_v1",
    "candidate_default_off": True,
    "candidate_implementation": CANDIDATE_IMPLEMENTATION,
    "development_profile_seed_excluded": 3201,
    "diagnostics_schema_version": (
        D1_ASSOCIATION_SPARSE_PREFILTER_DIAGNOSTICS_SCHEMA_VERSION
    ),
    "exact_association_gate_unchanged": True,
    "exact_residual_semantics_preserved": True,
    "execution_config_schema_version": (
        D1_ASSOCIATION_SPARSE_PREFILTER_EXECUTION_CONFIG_SCHEMA_VERSION
    ),
    "only_allowed_runtime_treatment_difference": (
        "d1_association_sparse_prefilter_implementation"
    ),
    "prior_episode_outputs_reused": False,
    "reference_implementation": REFERENCE_IMPLEMENTATION,
    "same_source_commit_for_both_arms": True,
    "simulation_mode": "three_dimensional_point_mass",
    "system_realtime_requires_real_time_factor_at_least_one": True,
    "truth_dependent_inputs_forbidden": True,
    "truth_is_online_control_input": False,
    "uncertified_pairs_fail_open": True,
}
_EXPECTED_CASES = (
    ("short_seed_1131", "short", 1131, 2.2, ("reference", "candidate")),
    ("short_seed_1132", "short", 1132, 2.2, ("candidate", "reference")),
    ("short_seed_1133", "short", 1133, 2.2, ("reference", "candidate")),
    ("short_seed_1134", "short", 1134, 2.2, ("candidate", "reference")),
    ("short_seed_1135", "short", 1135, 2.2, ("reference", "candidate")),
    ("short_seed_1136", "short", 1136, 2.2, ("candidate", "reference")),
    ("short_seed_1137", "short", 1137, 2.2, ("reference", "candidate")),
    ("short_seed_1138", "short", 1138, 2.2, ("candidate", "reference")),
    ("short_seed_1139", "short", 1139, 2.2, ("reference", "candidate")),
    ("short_seed_1140", "short", 1140, 2.2, ("candidate", "reference")),
    ("long_seed_1131", "long", 1131, 10.0, ("candidate", "reference")),
    ("long_seed_1132", "long", 1132, 10.0, ("reference", "candidate")),
    ("long_seed_1133", "long", 1133, 10.0, ("candidate", "reference")),
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
_EXPECTED_MANIFEST_KEYS = {
    "schema_version",
    "experiment_id",
    "matrix_path",
    "matrix_sha256",
    "matrix",
    "source_worktree",
    "source_commit",
    "source_repository_dirty",
    "output_root",
    "required_d6_evaluator_schema_version",
    "association_sparse_prefilter_execution_config_schema_version",
    "association_sparse_prefilter_diagnostics_schema_version",
    "status",
    "started_at_utc",
    "completed_at_utc",
    "cases",
}
_EXPECTED_CASE_KEYS = {
    "case_id",
    "group",
    "seed",
    "duration_s",
    "arm_order",
    "arms",
    "d6_evaluation_status",
}
_EXPECTED_ARM_KEYS = {
    "arm",
    "command",
    "completed_at_utc",
    "episode_dir",
    "expected_commit",
    "expected_d1_implementation_id",
    "expected_implementation",
    "resource_path",
    "return_code",
    "started_at_utc",
    "status",
    "stderr_path",
    "stdout_path",
    "validation_kind",
}
_EXPECTED_CONFIG_SCHEMA_VERSION = "scalable3d-scenario-v1"
_EXPECTED_RUNTIME_PROFILE_SCHEMA_VERSION = (
    "scalable3d-integrated-stack-runtime-profile-v1"
)
_EXPECTED_GOVERNANCE_SCHEMA_VERSION = (
    "scalable3d-observation-governance-runtime-v2"
)
_EXPECTED_EXECUTION_CONFIG_KEYS = {
    "schema_version",
    "selector",
    "selected_implementation_id",
    "default_selector",
    "candidate_default_enabled",
    "reference_selector",
    "reference_implementation_id",
    "candidate_selector",
    "candidate_implementation_id",
    "candidate_enabled",
    "rollback_selector",
    "legacy_radar_lower_bound_gate_enabled",
    "modality_order",
    "modality_policies",
    "truth_dependent_inputs",
    "exact_association_gate_changed",
}
_EXPECTED_DIAGNOSTICS_KEYS = {
    "schema_version",
    "execution_config",
    "selector",
    "selected_implementation_id",
    "reference_implementation_id",
    "candidate_implementation_id",
    "candidate_enabled",
    "legacy_radar_lower_bound_gate_enabled",
    "modality_order",
    "modality_counts",
    "total_counts",
    "conservation",
}
_EXPECTED_REFERENCE_POLICIES = {
    "radar": "legacy_certified_quadratic_bound_v1",
    "lidar": "exact_reference_innovation_solve_v1",
    "acoustic": "exact_reference_innovation_solve_v1",
    "acoustic_3d": "exact_reference_innovation_solve_v1",
    "eo": "exact_reference_innovation_solve_v1",
    "other": "fail_open_exact_reference_v1",
}
_EXPECTED_CANDIDATE_POLICIES = {
    "radar": "legacy_certified_quadratic_bound_v1",
    "lidar": "certified_exact_residual_quadratic_bound_v1",
    "acoustic": "certified_exact_wrapped_residual_quadratic_bound_v1",
    "acoustic_3d": "certified_exact_wrapped_residual_quadratic_bound_v1",
    "eo": "certified_exact_projection_residual_quadratic_bound_v1",
    "other": "fail_open_exact_reference_v1",
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
_CONSUMED_EPISODE_FILES = (
    "manifest.json",
    "scenario_config.json",
    "summary.json",
    "observation_governance_audit.json",
    "stage_timings.csv",
    "online_observations.jsonl",
    "offline_truth_state.npz",
    "offline_truth_labels.jsonl",
    "offline_proximity_intercepts.jsonl",
)
_REQUIRED_HASH_KEYS = set(_CONSUMED_EPISODE_FILES) | {
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


class D1AssociationSparsePrefilterEvidenceError(ValueError):
    """Raised when persisted evidence violates the frozen D6 contract."""


@dataclass(frozen=True)
class D1AssociationSparsePrefilterArmBinding:
    arm: str
    implementation: str
    episode_dir: Path
    resource_path: Path
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True)
class D1AssociationSparsePrefilterPairBinding:
    case_id: str
    group: str
    seed: int
    duration_s: float
    arm_order: tuple[str, ...]
    arms: Mapping[str, D1AssociationSparsePrefilterArmBinding]


@dataclass(frozen=True)
class D1AssociationSparsePrefilterEvidence:
    source_path: Path
    source_sha256: str
    matrix_path: Path
    matrix_sha256: str
    matrix: Mapping[str, Any]
    output_root: Path
    source_commit: str
    source_worktree: Path
    pairs: tuple[D1AssociationSparsePrefilterPairBinding, ...]


def load_d1_association_sparse_prefilter_evidence_manifest(
    source: str | Path,
) -> D1AssociationSparsePrefilterEvidence:
    """Bind one complete 13-pair manifest and reject all contract drift."""

    source_path = Path(source).expanduser().resolve()
    manifest, manifest_raw = _load_mapping(source_path)
    if set(manifest) != _EXPECTED_MANIFEST_KEYS:
        raise D1AssociationSparsePrefilterEvidenceError(
            "evidence manifest fields differ from the frozen contract"
        )
    _expect(
        manifest.get("schema_version"),
        D1_ASSOCIATION_SPARSE_PREFILTER_EVIDENCE_SCHEMA_VERSION,
        "evidence schema_version",
    )
    _expect(
        manifest.get("experiment_id"),
        D1_ASSOCIATION_SPARSE_PREFILTER_EXPERIMENT_ID,
        "evidence experiment_id",
    )
    _expect(
        manifest.get("required_d6_evaluator_schema_version"),
        D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_EVALUATION_SCHEMA_VERSION,
        "required D6 evaluator schema",
    )
    _expect(
        manifest.get(
            "association_sparse_prefilter_execution_config_schema_version"
        ),
        D1_ASSOCIATION_SPARSE_PREFILTER_EXECUTION_CONFIG_SCHEMA_VERSION,
        "execution config schema",
    )
    _expect(
        manifest.get(
            "association_sparse_prefilter_diagnostics_schema_version"
        ),
        D1_ASSOCIATION_SPARSE_PREFILTER_DIAGNOSTICS_SCHEMA_VERSION,
        "diagnostics schema",
    )
    if manifest.get("status") != "episodes_complete_pending_d6":
        raise D1AssociationSparsePrefilterEvidenceError(
            "evidence status must be episodes_complete_pending_d6"
        )
    _required_text(manifest.get("started_at_utc"), "started_at_utc")
    _required_text(manifest.get("completed_at_utc"), "completed_at_utc")
    source_commit = _required_commit(
        manifest.get("source_commit"), "source_commit"
    )
    if source_commit != D1_ASSOCIATION_SPARSE_PREFILTER_SOURCE_COMMIT:
        raise D1AssociationSparsePrefilterEvidenceError(
            "source_commit does not match the frozen producer commit"
        )
    if manifest.get("source_repository_dirty") is not False:
        raise D1AssociationSparsePrefilterEvidenceError(
            "source_repository_dirty must be false"
        )
    source_worktree = _explicit_path(
        manifest.get("source_worktree"),
        "source_worktree",
        require="directory",
    )
    output_root = _explicit_path(
        manifest.get("output_root"), "output_root", require="directory"
    )
    if source_path.parent != output_root:
        raise D1AssociationSparsePrefilterEvidenceError(
            "evidence_manifest.json must be directly under output_root"
        )

    matrix_path = _explicit_path(
        manifest.get("matrix_path"), "matrix_path", require="file"
    )
    matrix_sha256 = _required_sha256(
        manifest.get("matrix_sha256"), "matrix_sha256"
    )
    actual_matrix_sha256 = _base._file_sha256(matrix_path)
    if matrix_sha256 != actual_matrix_sha256:
        raise D1AssociationSparsePrefilterEvidenceError(
            "matrix_sha256 does not match matrix_path bytes"
        )
    if matrix_sha256 != D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SHA256:
        raise D1AssociationSparsePrefilterEvidenceError(
            "matrix_sha256 does not match the frozen producer matrix"
        )
    matrix, _ = _load_mapping(matrix_path)
    _validate_matrix(matrix)
    if _required_mapping(manifest.get("matrix"), "embedded matrix") != matrix:
        raise D1AssociationSparsePrefilterEvidenceError(
            "embedded matrix does not exactly match matrix_path"
        )

    raw_cases = _required_sequence(manifest.get("cases"), "evidence cases")
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise D1AssociationSparsePrefilterEvidenceError(
            "evidence manifest must contain exactly 13 cases"
        )
    pairs: list[D1AssociationSparsePrefilterPairBinding] = []
    used_paths: set[Path] = {source_path}
    for raw_case, expected_case in zip(
        raw_cases, _EXPECTED_CASES, strict=True
    ):
        case = _required_mapping(raw_case, "evidence case")
        if set(case) != _EXPECTED_CASE_KEYS:
            raise D1AssociationSparsePrefilterEvidenceError(
                "evidence case fields differ from the frozen contract"
            )
        metadata = _case_metadata(case)
        if metadata != expected_case:
            raise D1AssociationSparsePrefilterEvidenceError(
                "evidence case differs from the frozen matrix"
            )
        case_id, group, seed, duration_s, arm_order = metadata
        if (
            case.get("d6_evaluation_status")
            != "episodes_complete_pending_d6"
        ):
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{case_id} is not pending D6 evaluation"
            )
        raw_arms = _required_mapping(case.get("arms"), f"{case_id} arms")
        if set(raw_arms) != set(_ARMS):
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{case_id} arms must be reference and candidate"
            )
        bindings: dict[str, D1AssociationSparsePrefilterArmBinding] = {}
        commands: dict[str, list[str]] = {}
        for arm in _ARMS:
            record = _required_mapping(
                raw_arms.get(arm), f"{case_id} {arm} arm"
            )
            if set(record) != _EXPECTED_ARM_KEYS:
                raise D1AssociationSparsePrefilterEvidenceError(
                    f"{case_id} {arm} fields differ from the frozen contract"
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
            _required_text(
                record.get("started_at_utc"),
                f"{case_id} {arm} started_at_utc",
            )
            _required_text(
                record.get("completed_at_utc"),
                f"{case_id} {arm} completed_at_utc",
            )
            if record.get("status") != "complete":
                raise D1AssociationSparsePrefilterEvidenceError(
                    f"{case_id} {arm} must be a fresh complete arm"
                )
            return_code = record.get("return_code")
            if (
                not isinstance(return_code, int)
                or isinstance(return_code, bool)
                or return_code != 0
            ):
                raise D1AssociationSparsePrefilterEvidenceError(
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
                    raise D1AssociationSparsePrefilterEvidenceError(
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
                raise D1AssociationSparsePrefilterEvidenceError(
                    f"{case_id} {arm} command differs from frozen execution"
                )
            commands[arm] = command
            bindings[arm] = D1AssociationSparsePrefilterArmBinding(
                arm=arm,
                implementation=implementation,
                episode_dir=episode_dir,
                resource_path=resource_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        _validate_pair_command_isolation(commands, case_id)
        pairs.append(
            D1AssociationSparsePrefilterPairBinding(
                case_id=case_id,
                group=group,
                seed=seed,
                duration_s=duration_s,
                arm_order=arm_order,
                arms=bindings,
            )
        )
    if len(pairs) * len(_ARMS) != 26:
        raise D1AssociationSparsePrefilterEvidenceError(
            "evidence must bind exactly 26 fresh arms"
        )
    return D1AssociationSparsePrefilterEvidence(
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


def evaluate_d1_association_sparse_prefilter_multiseed(
    source: str | Path,
    *,
    raise_on_invalid: bool = False,
) -> dict[str, Any]:
    """Evaluate the frozen matrix or return a fail-closed unavailable result."""

    try:
        return _evaluate_available(source)
    except D1AssociationSparsePrefilterEvidenceError as exc:
        if raise_on_invalid:
            raise
        return _unavailable_evaluation(source, str(exc))


def _evaluate_available(source: str | Path) -> dict[str, Any]:
    evidence = load_d1_association_sparse_prefilter_evidence_manifest(source)
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
    diagnostics_aggregate = _aggregate_diagnostics(pairs)
    thresholds = copy.deepcopy(
        dict(
            _required_mapping(
                evidence.matrix["admission_gates"], "admission gates"
            )
        )
    )
    gates = _admission_gates(
        pairs, groups, diagnostics_aggregate, thresholds
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
            D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": D1_ASSOCIATION_SPARSE_PREFILTER_EVALUATION_DATE,
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "availability": {"available": True, "reason": None},
        "input_contract": {
            "evidence_manifest_path": str(evidence.source_path),
            "evidence_manifest_sha256": evidence.source_sha256,
            "evidence_manifest_schema_version": (
                D1_ASSOCIATION_SPARSE_PREFILTER_EVIDENCE_SCHEMA_VERSION
            ),
            "evidence_manifest_status": "episodes_complete_pending_d6",
            "matrix_path": str(evidence.matrix_path),
            "matrix_sha256": evidence.matrix_sha256,
            "matrix_schema_version": (
                D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": D1_ASSOCIATION_SPARSE_PREFILTER_EXPERIMENT_ID,
            "output_root": str(evidence.output_root),
            "source_commit": evidence.source_commit,
            "source_repository_dirty": False,
            "same_commit_for_both_arms": True,
            "arm_implementations": dict(_IMPLEMENTATIONS),
            "arm_implementation_ids": dict(_IMPLEMENTATION_IDS),
            "execution_config_schema_version": (
                D1_ASSOCIATION_SPARSE_PREFILTER_EXECUTION_CONFIG_SCHEMA_VERSION
            ),
            "diagnostics_schema_version": (
                D1_ASSOCIATION_SPARSE_PREFILTER_DIAGNOSTICS_SCHEMA_VERSION
            ),
            "pair_count": len(pairs),
            "arm_count": len(pairs) * 2,
            "fresh_arm_count": len(pairs) * 2,
            "reused_arm_count": 0,
            "failed_arm_count": 0,
            "bootstrap_resamples": bootstrap_resamples,
            "bootstrap_rng_seed": bootstrap_seed,
            "evidence_boundary": copy.deepcopy(_EXPECTED_BOUNDARY),
        },
        "scope": {
            "simulation_mode": "three_dimensional_point_mass",
            "airsim_evidence": False,
            "hardware_evidence": False,
            "flight_evidence": False,
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
                _SELECTOR_FIELD,
                _EXECUTION_CONFIG_FIELD,
                _DIAGNOSTICS_FIELD,
                "association_innovation_solve_count",
                "runtime_profile_sha256-derived episode identity",
                "stage and episode performance fields",
            ],
            "candidate_default_enabled": False,
        },
        "thresholds": thresholds,
        "pairs": pairs,
        "groups": groups,
        "association_sparse_prefilter_diagnostics_aggregate": (
            diagnostics_aggregate
        ),
        "admission_gates": gates,
        "admission_blockers": blockers,
        "verdict": "admit" if admitted else "reject",
        "optimization_admitted": admitted,
        "main_default_promotion_allowed": admitted,
        "system_realtime_gate": realtime_gate,
        "system_realtime_gap_closed": bool(realtime_gate["passed"]),
        "system_realtime_status": (
            "closed" if realtime_gate["passed"] else "open"
        ),
    }


def _unavailable_evaluation(
    source: str | Path, reason: str
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
            D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": D1_ASSOCIATION_SPARSE_PREFILTER_EVALUATION_DATE,
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "availability": {"available": False, "reason": reason},
        "input_contract": {
            "evidence_manifest_path": str(source_path),
            "matrix_sha256": (
                D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SHA256
            ),
            "matrix_schema_version": (
                D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": D1_ASSOCIATION_SPARSE_PREFILTER_EXPERIMENT_ID,
            "source_commit": D1_ASSOCIATION_SPARSE_PREFILTER_SOURCE_COMMIT,
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
        "thresholds": copy.deepcopy(_EXPECTED_GATES),
        "pairs": [],
        "groups": {},
        "association_sparse_prefilter_diagnostics_aggregate": {},
        "admission_gates": {"evidence_available": unavailable_gate},
        "admission_blockers": [
            {
                "gate": "evidence_available",
                "actual": False,
                "threshold": True,
                "comparator": "==",
                "reason": "evidence_unavailable",
            }
        ],
        "verdict": "reject",
        "optimization_admitted": False,
        "main_default_promotion_allowed": False,
        "system_realtime_gate": {
            "available": False,
            "passed": False,
            "reason": "evidence_unavailable",
            "candidate_minimum_real_time_factor": None,
            "threshold": 1.0,
        },
        "system_realtime_gap_closed": False,
        "system_realtime_status": "open",
    }


def _validate_matrix(matrix: Mapping[str, Any]) -> None:
    if set(matrix) != _EXPECTED_MATRIX_KEYS:
        raise D1AssociationSparsePrefilterEvidenceError(
            "matrix fields differ from the frozen producer contract"
        )
    expected_scalars = {
        "schema_version": (
            D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SCHEMA_VERSION
        ),
        "experiment_id": D1_ASSOCIATION_SPARSE_PREFILTER_EXPERIMENT_ID,
        "same_clean_commit_required": True,
        "target_count": _TARGET_COUNT,
        "resource_count": _RESOURCE_COUNT,
        "recon_count": _RECON_COUNT,
        "arm_implementations": _IMPLEMENTATIONS,
        "run_flags": list(_RUN_FLAGS),
        "cooldown_s": 2.0,
        "bootstrap_seed": _BOOTSTRAP_RNG_SEED,
        "bootstrap_resamples": _BOOTSTRAP_RESAMPLES,
        "admission_gates": _EXPECTED_GATES,
        "evidence_boundary": _EXPECTED_BOUNDARY,
    }
    for field, expected in expected_scalars.items():
        _expect(matrix.get(field), expected, f"matrix {field}")
    raw_cases = _required_sequence(matrix.get("cases"), "matrix cases")
    actual_cases = tuple(
        _case_metadata(_required_mapping(case, "matrix case"))
        for case in raw_cases
    )
    _expect(actual_cases, _EXPECTED_CASES, "matrix cases")


def _evaluate_pair(
    pair: D1AssociationSparsePrefilterPairBinding,
    evidence: D1AssociationSparsePrefilterEvidence,
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
    exact_gate_by_modality = {
        modality: (
            int(
                reference["association_sparse_prefilter_diagnostics"][
                    "modality_counts"
                ][modality]["exact_gate_pass_count"]
            )
            == int(
                candidate["association_sparse_prefilter_diagnostics"][
                    "modality_counts"
                ][modality]["exact_gate_pass_count"]
            )
        )
        for modality in _MODALITIES
    }
    workload_by_modality = {
        modality: (
            int(
                reference["association_sparse_prefilter_diagnostics"][
                    "modality_counts"
                ][modality]["candidate_pair_count"]
            )
            == int(
                candidate["association_sparse_prefilter_diagnostics"][
                    "modality_counts"
                ][modality]["candidate_pair_count"]
            )
        )
        for modality in _MODALITIES
    }
    pair_audit = _pair_prefilter_audit(
        reference["association_sparse_prefilter_diagnostics"],
        candidate["association_sparse_prefilter_diagnostics"],
        exact_gate_by_modality=exact_gate_by_modality,
        workload_by_modality=workload_by_modality,
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
            reference["implementation_identity_passed"]
            and candidate["implementation_identity_passed"]
        ),
        "exact_gate_pass_counts_equal_by_modality": (
            exact_gate_by_modality
        ),
        "exact_gate_pass_counts_equal": all(
            exact_gate_by_modality.values()
        ),
        "candidate_pair_workload_equal_by_modality": (
            workload_by_modality
        ),
        "association_sparse_prefilter_audit": pair_audit,
        "association_sparse_prefilter_audit_passed": bool(
            pair_audit["passed"]
        ),
        "artifact_provenance_passed": (
            reference["artifact_provenance"]["passed"]
            and candidate["artifact_provenance"]["passed"]
        ),
        "performance": performance,
    }


def _evaluate_arm(
    binding: D1AssociationSparsePrefilterArmBinding,
    *,
    pair: D1AssociationSparsePrefilterPairBinding,
    expected_commit: str,
) -> dict[str, Any]:
    context = f"{pair.case_id} {binding.arm}"
    paths = {
        name: binding.episode_dir / name
        for name in _CONSUMED_EPISODE_FILES
    }
    for name, path in paths.items():
        if not path.is_file():
            raise D1AssociationSparsePrefilterEvidenceError(
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
    diagnostics, identity_audit = _validate_implementation_surfaces(
        arm=binding.arm,
        expected=binding.implementation,
        runtime_profile=runtime_profile,
        summary=summary,
        governance=governance,
        context=context,
    )
    stages = {
        name: _load_stage(paths["stage_timings.csv"], stage)
        for name, stage in _STAGES.items()
    }
    resource = _load_resource_metrics(binding.resource_path)
    online_message_count = _strict_jsonl_count(
        paths["online_observations.jsonl"]
    )
    _strict_jsonl_count(paths["offline_truth_labels.jsonl"])
    _strict_jsonl_count(paths["offline_proximity_intercepts.jsonl"])
    try:
        _base._validate_truth_state_finite(
            paths["offline_truth_state.npz"]
        )
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1AssociationSparsePrefilterEvidenceError(str(exc)) from exc
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
            positive=True,
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
        "input_file_sha256": input_sha256,
    }
    if not artifact_provenance["passed"]:
        raise D1AssociationSparsePrefilterEvidenceError(
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
        "implementation_surface_audit": identity_audit,
        "association_sparse_prefilter_diagnostics": diagnostics,
        "business_count_snapshot": _business_count_snapshot(summary),
        "artifact_provenance": artifact_provenance,
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
    pair: D1AssociationSparsePrefilterPairBinding,
    binding: D1AssociationSparsePrefilterArmBinding,
    expected_commit: str,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> Mapping[str, Any]:
    context = f"{pair.case_id} {binding.arm}"
    if manifest.get("git_commit") != expected_commit:
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} source commit mismatch"
        )
    if manifest.get("repository_dirty") is not False:
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} repository is dirty"
        )
    if manifest.get("config_sha256") != _base._canonical_sha256(config):
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} config_sha256 mismatch"
        )
    runtime_profile = _required_mapping(
        manifest.get("runtime_profile"), f"{context} runtime_profile"
    )
    if manifest.get("runtime_profile_sha256") != _base._canonical_sha256(
        runtime_profile
    ):
        raise D1AssociationSparsePrefilterEvidenceError(
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
            raise D1AssociationSparsePrefilterEvidenceError(
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
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} finite_state must be true"
        )
    if summary.get("online_truth_use_count") != 0:
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} online_truth_use_count must be zero"
        )
    if governance.get("online_truth_use_count") != 0:
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} governance online truth count must be zero"
        )
    return runtime_profile


def _validate_implementation_surfaces(
    *,
    arm: str,
    expected: str,
    runtime_profile: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
    context: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    configuration = _required_mapping(
        runtime_profile.get("configuration"),
        f"{context} runtime configuration",
    )
    final = _required_mapping(
        summary.get("module_final_diagnostics"),
        f"{context} module_final_diagnostics",
    )
    nested = _required_mapping(
        final.get("observation_governance"),
        f"{context} nested observation_governance",
    )
    selectors = {
        "runtime_profile": runtime_profile.get(_SELECTOR_FIELD),
        "runtime_profile.configuration": configuration.get(_SELECTOR_FIELD),
        "summary": summary.get(_SELECTOR_FIELD),
        "summary.module_final_diagnostics": final.get(_SELECTOR_FIELD),
        "summary.module_final.observation_governance": nested.get(
            _SELECTOR_FIELD
        ),
        "governance": governance.get(_SELECTOR_FIELD),
    }
    mismatches = [
        f"{name}={value!r}"
        for name, value in selectors.items()
        if value != expected
    ]
    if mismatches:
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} implementation selector mismatch: "
            + ", ".join(mismatches)
        )

    execution_locations = {
        "runtime_profile": _required_mapping(
            runtime_profile.get(_EXECUTION_CONFIG_FIELD),
            f"{context} runtime execution config",
        ),
        "summary": _required_mapping(
            summary.get(_EXECUTION_CONFIG_FIELD),
            f"{context} summary execution config",
        ),
        "module_final": _required_mapping(
            final.get(_EXECUTION_CONFIG_FIELD),
            f"{context} final execution config",
        ),
        "nested_governance": _required_mapping(
            nested.get(_EXECUTION_CONFIG_FIELD),
            f"{context} nested execution config",
        ),
        "governance": _required_mapping(
            governance.get(_EXECUTION_CONFIG_FIELD),
            f"{context} governance execution config",
        ),
    }
    canonical_execution: dict[str, Any] | None = None
    for name, execution_config in execution_locations.items():
        validated = _validate_execution_config(
            execution_config,
            arm=arm,
            context=f"{context} {name}",
        )
        if canonical_execution is None:
            canonical_execution = validated
        elif validated != canonical_execution:
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{context} execution config mismatch at {name}"
            )
    assert canonical_execution is not None

    initial = _required_mapping(
        runtime_profile.get(_DIAGNOSTICS_FIELD),
        f"{context} initial diagnostics",
    )
    initial_validated = _validate_diagnostics(
        initial,
        arm=arm,
        context=f"{context} runtime_profile",
        require_workload=False,
    )
    if any(
        int(initial_validated["total_counts"][field]) != 0
        for field in _COUNTER_FIELDS
    ):
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} initial diagnostics counters must be zero"
        )
    diagnostics_locations = {
        "summary": _required_mapping(
            summary.get(_DIAGNOSTICS_FIELD),
            f"{context} summary diagnostics",
        ),
        "module_final": _required_mapping(
            final.get(_DIAGNOSTICS_FIELD),
            f"{context} final diagnostics",
        ),
        "nested_governance": _required_mapping(
            nested.get(_DIAGNOSTICS_FIELD),
            f"{context} nested diagnostics",
        ),
        "governance": _required_mapping(
            governance.get(_DIAGNOSTICS_FIELD),
            f"{context} governance diagnostics",
        ),
    }
    canonical_diagnostics: dict[str, Any] | None = None
    for name, diagnostics in diagnostics_locations.items():
        validated = _validate_diagnostics(
            diagnostics,
            arm=arm,
            context=f"{context} {name}",
            require_workload=True,
        )
        if validated["execution_config"] != canonical_execution:
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{context} diagnostics execution config mismatch at {name}"
            )
        if canonical_diagnostics is None:
            canonical_diagnostics = validated
        elif validated != canonical_diagnostics:
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{context} diagnostics mismatch at {name}"
            )
    assert canonical_diagnostics is not None
    return canonical_diagnostics, {
        "passed": True,
        "primary_surface_count": 4,
        "primary_surfaces": [
            "runtime_profile",
            "summary",
            "summary.module_final_diagnostics",
            "governance",
        ],
        "selector_surface_count": len(selectors),
        "execution_config_surface_count": len(execution_locations),
        "final_diagnostics_surface_count": len(diagnostics_locations),
        "runtime_configuration_selector_checked": True,
        "nested_governance_surface_checked": True,
        "selector_consistency_passed": True,
        "implementation_id_consistency_passed": True,
        "execution_config_consistency_passed": True,
        "diagnostics_schema_passed": True,
        "four_final_diagnostics_equal": True,
        "initial_zero_diagnostics_passed": True,
    }


def _validate_execution_config(
    value: Mapping[str, Any],
    *,
    arm: str,
    context: str,
) -> dict[str, Any]:
    if set(value) != _EXPECTED_EXECUTION_CONFIG_KEYS:
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} execution config fields mismatch"
        )
    candidate = arm == _CANDIDATE_ARM
    expected = {
        "schema_version": (
            D1_ASSOCIATION_SPARSE_PREFILTER_EXECUTION_CONFIG_SCHEMA_VERSION
        ),
        "selector": _IMPLEMENTATIONS[arm],
        "selected_implementation_id": _IMPLEMENTATION_IDS[arm],
        "default_selector": REFERENCE_IMPLEMENTATION,
        "candidate_default_enabled": False,
        "reference_selector": REFERENCE_IMPLEMENTATION,
        "reference_implementation_id": REFERENCE_IMPLEMENTATION_ID,
        "candidate_selector": CANDIDATE_IMPLEMENTATION,
        "candidate_implementation_id": CANDIDATE_IMPLEMENTATION_ID,
        "candidate_enabled": candidate,
        "rollback_selector": REFERENCE_IMPLEMENTATION,
        "legacy_radar_lower_bound_gate_enabled": True,
        "modality_order": list(_MODALITIES),
        "modality_policies": (
            _EXPECTED_CANDIDATE_POLICIES
            if candidate
            else _EXPECTED_REFERENCE_POLICIES
        ),
        "truth_dependent_inputs": False,
        "exact_association_gate_changed": False,
    }
    if dict(value) != expected:
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} execution config value mismatch"
        )
    return copy.deepcopy(expected)


def _validate_diagnostics(
    value: Mapping[str, Any],
    *,
    arm: str,
    context: str,
    require_workload: bool,
) -> dict[str, Any]:
    if set(value) != _EXPECTED_DIAGNOSTICS_KEYS:
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} diagnostics fields mismatch"
        )
    candidate = arm == _CANDIDATE_ARM
    _expect(
        value.get("schema_version"),
        D1_ASSOCIATION_SPARSE_PREFILTER_DIAGNOSTICS_SCHEMA_VERSION,
        f"{context} diagnostics schema",
    )
    for field, expected in (
        ("selector", _IMPLEMENTATIONS[arm]),
        ("selected_implementation_id", _IMPLEMENTATION_IDS[arm]),
        ("reference_implementation_id", REFERENCE_IMPLEMENTATION_ID),
        ("candidate_implementation_id", CANDIDATE_IMPLEMENTATION_ID),
        ("candidate_enabled", candidate),
        ("legacy_radar_lower_bound_gate_enabled", True),
        ("modality_order", list(_MODALITIES)),
    ):
        _expect(value.get(field), expected, f"{context} {field}")
    execution_config = _validate_execution_config(
        _required_mapping(
            value.get("execution_config"),
            f"{context} diagnostics execution config",
        ),
        arm=arm,
        context=f"{context} diagnostics",
    )
    modality_counts_raw = _required_mapping(
        value.get("modality_counts"), f"{context} modality_counts"
    )
    if set(modality_counts_raw) != set(_MODALITIES):
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} modality buckets mismatch"
        )
    modality_counts: dict[str, dict[str, int]] = {}
    sums = {field: 0 for field in _COUNTER_FIELDS}
    for modality in _MODALITIES:
        raw_counts = _required_mapping(
            modality_counts_raw.get(modality),
            f"{context} {modality} counts",
        )
        if set(raw_counts) != set(_COUNTER_FIELDS):
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{context} {modality} counter fields mismatch"
            )
        counts = {
            field: _nonnegative_integer(
                raw_counts.get(field), f"{context} {modality} {field}"
            )
            for field in _COUNTER_FIELDS
        }
        if (
            counts["conservative_prefilter_rejection_count"]
            > counts["candidate_pair_count"]
            or counts["exact_innovation_solve_count"]
            > counts["candidate_pair_count"]
            or counts["exact_gate_pass_count"]
            > counts["exact_innovation_solve_count"]
            or counts["fallback_count"] > counts["candidate_pair_count"]
            or counts["fallback_count"]
            > counts["exact_innovation_solve_count"]
        ):
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{context} {modality} counter conservation failed"
            )
        modality_counts[modality] = counts
        for field in _COUNTER_FIELDS:
            sums[field] += counts[field]
    total_counts_raw = _required_mapping(
        value.get("total_counts"), f"{context} total_counts"
    )
    if set(total_counts_raw) != set(_COUNTER_FIELDS):
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} total counter fields mismatch"
        )
    total_counts = {
        field: _nonnegative_integer(
            total_counts_raw.get(field), f"{context} total {field}"
        )
        for field in _COUNTER_FIELDS
    }
    if total_counts != sums:
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} total count conservation failed"
        )
    conservation = _required_mapping(
        value.get("conservation"), f"{context} conservation"
    )
    if set(conservation) != {
        "modalities",
        "all_counter_bounds_hold",
        "fixed_modality_bucket_count",
    }:
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} conservation fields mismatch"
        )
    conservation_modalities = _required_mapping(
        conservation.get("modalities"),
        f"{context} conservation modalities",
    )
    if set(conservation_modalities) != set(_MODALITIES):
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} conservation modality buckets mismatch"
        )
    for modality in _MODALITIES:
        checks = _required_mapping(
            conservation_modalities.get(modality),
            f"{context} {modality} conservation",
        )
        if set(checks) != set(_CONSERVATION_FIELDS) or any(
            checks.get(field) is not True
            for field in _CONSERVATION_FIELDS
        ):
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{context} {modality} conservation flags mismatch"
            )
    if (
        conservation.get("all_counter_bounds_hold") is not True
        or conservation.get("fixed_modality_bucket_count") is not True
    ):
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} aggregate conservation flags failed"
        )
    non_radar_rejections = sum(
        modality_counts[modality][
            "conservative_prefilter_rejection_count"
        ]
        for modality in _NON_RADAR_MODALITIES
    )
    if not candidate and non_radar_rejections != 0:
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} reference has non-radar prefilter rejections"
        )
    if require_workload:
        if total_counts["candidate_pair_count"] <= 0:
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{context} candidate-pair workload must be positive"
            )
        if candidate and non_radar_rejections <= 0:
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{context} candidate treatment was not exercised"
            )
    return {
        "schema_version": value["schema_version"],
        "execution_config": execution_config,
        "selector": value["selector"],
        "selected_implementation_id": value[
            "selected_implementation_id"
        ],
        "reference_implementation_id": value[
            "reference_implementation_id"
        ],
        "candidate_implementation_id": value[
            "candidate_implementation_id"
        ],
        "candidate_enabled": value["candidate_enabled"],
        "legacy_radar_lower_bound_gate_enabled": value[
            "legacy_radar_lower_bound_gate_enabled"
        ],
        "modality_order": list(_MODALITIES),
        "modality_counts": modality_counts,
        "total_counts": total_counts,
        "conservation": copy.deepcopy(dict(conservation)),
    }


def _pair_prefilter_audit(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    exact_gate_by_modality: Mapping[str, bool],
    workload_by_modality: Mapping[str, bool],
) -> dict[str, Any]:
    reference_counts = _required_mapping(
        reference.get("modality_counts"), "reference modality counts"
    )
    candidate_counts = _required_mapping(
        candidate.get("modality_counts"), "candidate modality counts"
    )
    reference_non_radar_solves = sum(
        int(
            _required_mapping(
                reference_counts[modality],
                f"reference {modality} counts",
            )["exact_innovation_solve_count"]
        )
        for modality in _NON_RADAR_MODALITIES
    )
    candidate_non_radar_solves = sum(
        int(
            _required_mapping(
                candidate_counts[modality],
                f"candidate {modality} counts",
            )["exact_innovation_solve_count"]
        )
        for modality in _NON_RADAR_MODALITIES
    )
    if reference_non_radar_solves <= 0:
        raise D1AssociationSparsePrefilterEvidenceError(
            "reference non-radar exact-solve denominator is zero"
        )
    reduction = (
        (reference_non_radar_solves - candidate_non_radar_solves)
        / reference_non_radar_solves
        * 100.0
    )
    passed = all(workload_by_modality.values())
    return {
        "passed": passed,
        "same_candidate_pair_workload_by_modality": dict(
            workload_by_modality
        ),
        "same_candidate_pair_workload": passed,
        "exact_gate_pass_counts_equal_by_modality": dict(
            exact_gate_by_modality
        ),
        "exact_gate_pass_counts_equal": all(
            exact_gate_by_modality.values()
        ),
        "reference_non_radar_exact_solve_count": (
            reference_non_radar_solves
        ),
        "candidate_non_radar_exact_solve_count": (
            candidate_non_radar_solves
        ),
        "candidate_non_radar_exact_solve_reduction_pct": reduction,
    }


def _normalized_runtime_profile(
    runtime_profile: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(runtime_profile))
    _normalize_treatment_surface(
        normalized, "normalized runtime_profile"
    )
    configuration = normalized.get("configuration")
    if not isinstance(configuration, dict) or (
        _SELECTOR_FIELD not in configuration
    ):
        raise D1AssociationSparsePrefilterEvidenceError(
            "normalized runtime configuration lacks selector"
        )
    configuration[_SELECTOR_FIELD] = _TREATMENT_MARKER
    return normalized


def _normalized_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(summary))
    for field in ("episode_id", "wall_time_s", "real_time_factor"):
        if field not in normalized:
            raise D1AssociationSparsePrefilterEvidenceError(
                f"normalized summary lacks {field}"
            )
    normalized["episode_id"] = _TREATMENT_DERIVED_ID_MARKER
    normalized["wall_time_s"] = _PERFORMANCE_MARKER
    normalized["real_time_factor"] = _PERFORMANCE_MARKER
    _normalize_treatment_surface(normalized, "normalized summary")
    final = normalized.get("module_final_diagnostics")
    if not isinstance(final, dict):
        raise D1AssociationSparsePrefilterEvidenceError(
            "normalized summary lacks module_final_diagnostics"
        )
    _normalize_treatment_surface(final, "normalized module final")
    if "stage_timings" not in final:
        raise D1AssociationSparsePrefilterEvidenceError(
            "normalized module final lacks stage_timings"
        )
    final["stage_timings"] = _PERFORMANCE_MARKER
    d1_performance = final.get("d1_fusion_performance")
    if not isinstance(d1_performance, dict) or (
        "association_innovation_solve_count" not in d1_performance
    ):
        raise D1AssociationSparsePrefilterEvidenceError(
            "normalized module final lacks association solve count"
        )
    d1_performance["association_innovation_solve_count"] = (
        _DIAGNOSTICS_MARKER
    )
    nested = final.get("observation_governance")
    if not isinstance(nested, Mapping):
        raise D1AssociationSparsePrefilterEvidenceError(
            "normalized summary lacks nested observation governance"
        )
    final["observation_governance"] = _normalized_governance(nested)
    return normalized


def _normalized_governance(
    governance: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(governance))
    _normalize_treatment_surface(normalized, "normalized governance")
    fusion = normalized.get("d1_fusion_association")
    if isinstance(fusion, dict) and (
        "association_innovation_solve_count" in fusion
    ):
        fusion["association_innovation_solve_count"] = (
            _DIAGNOSTICS_MARKER
        )
    return normalized


def _normalize_treatment_surface(
    mapping: dict[str, Any], context: str
) -> None:
    for field, marker in (
        (_SELECTOR_FIELD, _TREATMENT_MARKER),
        (_EXECUTION_CONFIG_FIELD, _TREATMENT_MARKER),
        (_DIAGNOSTICS_FIELD, _DIAGNOSTICS_MARKER),
    ):
        if field not in mapping:
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{context} lacks {field}"
            )
        mapping[field] = marker


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
        raise D1AssociationSparsePrefilterEvidenceError(
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
        "normalized_governance_equal": (
            reference["normalized_governance_sha256"]
            == candidate["normalized_governance_sha256"]
        ),
        "business_count_snapshot_equal": (
            reference["business_count_snapshot"]
            == candidate["business_count_snapshot"]
        ),
        "online_message_count_equal": (
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
        "treatment_normalization": {
            "scope": (
                "registered_selector_execution_config_diagnostics_"
                "runtime_hash_and_performance_only"
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
        "exact_gate_pass_equality_count": sum(
            bool(pair["exact_gate_pass_counts_equal"])
            for pair in ordered
        ),
        "sparse_prefilter_audit_pass_count": sum(
            bool(pair["association_sparse_prefilter_audit_passed"])
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
        reference_distribution = _base._distribution(reference)
        candidate_distribution = _base._distribution(candidate)
        raw_distribution = _base._distribution(raw)
        improvement_distribution = _base._distribution(improvement)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1AssociationSparsePrefilterEvidenceError(str(exc)) from exc
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
        "reference": reference_distribution,
        "candidate": candidate_distribution,
        "raw_relative_change": {
            **raw_distribution,
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
            for key, value in improvement_distribution.items()
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


def _aggregate_diagnostics(
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    for group in (*_GROUPS, "all"):
        selected = (
            list(pairs)
            if group == "all"
            else [pair for pair in pairs if pair["group"] == group]
        )
        arms: dict[str, Any] = {}
        for arm in _ARMS:
            modality_totals = {
                modality: {field: 0 for field in _COUNTER_FIELDS}
                for modality in _MODALITIES
            }
            for pair in selected:
                counts = pair[arm][
                    "association_sparse_prefilter_diagnostics"
                ]["modality_counts"]
                for modality in _MODALITIES:
                    for field in _COUNTER_FIELDS:
                        modality_totals[modality][field] += int(
                            counts[modality][field]
                        )
            arms[arm] = {
                "modality_counts": modality_totals,
                "total_counts": {
                    field: sum(
                        modality_totals[modality][field]
                        for modality in _MODALITIES
                    )
                    for field in _COUNTER_FIELDS
                },
            }
        reference_non_radar_solves = sum(
            arms[_REFERENCE_ARM]["modality_counts"][modality][
                "exact_innovation_solve_count"
            ]
            for modality in _NON_RADAR_MODALITIES
        )
        candidate_non_radar_solves = sum(
            arms[_CANDIDATE_ARM]["modality_counts"][modality][
                "exact_innovation_solve_count"
            ]
            for modality in _NON_RADAR_MODALITIES
        )
        if reference_non_radar_solves <= 0:
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{group} reference non-radar solve denominator is zero"
            )
        groups[group] = {
            "pair_count": len(selected),
            "arms": arms,
            "candidate_modality_counts": copy.deepcopy(
                arms[_CANDIDATE_ARM]["modality_counts"]
            ),
            "reference_non_radar_exact_solve_count": (
                reference_non_radar_solves
            ),
            "candidate_non_radar_exact_solve_count": (
                candidate_non_radar_solves
            ),
            "candidate_non_radar_exact_solve_reduction_pct": (
                (reference_non_radar_solves - candidate_non_radar_solves)
                / reference_non_radar_solves
                * 100.0
            ),
        }
    return {
        "schema_version": (
            "d6.d1_association_sparse_prefilter_diagnostics_aggregate.v1"
        ),
        "modality_order": list(_MODALITIES),
        "non_radar_modalities": list(_NON_RADAR_MODALITIES),
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
    exact_gate_count = sum(
        bool(pair["exact_gate_pass_counts_equal"]) for pair in pairs
    )
    audit_count = sum(
        bool(pair["association_sparse_prefilter_audit_passed"])
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
    solve_reduction = float(
        diagnostics_aggregate["groups"]["all"][
            "candidate_non_radar_exact_solve_reduction_pct"
        ]
    )
    short_bootstrap_upper = (
        short_d1["raw_relative_change"]["bootstrap_95_ci"]["upper"]
        * 100.0
    )
    return {
        "all_pairs_association_sparse_prefilter_audit_valid": _gate(
            actual=audit_count,
            threshold=pair_count,
            comparator="==",
            passed=(audit_count == pair_count),
            reason="one_or_more_pair_sparse_prefilter_audit_failed",
        ),
        "all_pairs_business_semantics_equal": _gate(
            actual=semantic_count,
            threshold=pair_count,
            comparator="==",
            passed=(semantic_count == pair_count),
            reason="one_or_more_pair_business_semantics_mismatch",
        ),
        "all_pairs_exact_gate_pass_counts_equal": _gate(
            actual=exact_gate_count,
            threshold=pair_count,
            comparator="==",
            passed=(exact_gate_count == pair_count),
            reason="one_or_more_pair_exact_gate_pass_counts_mismatch",
        ),
        "all_pairs_explicit_implementation_identity": _gate(
            actual=identity_count,
            threshold=pair_count,
            comparator="==",
            passed=(identity_count == pair_count),
            reason="one_or_more_pair_implementation_identity_failed",
        ),
        "all_pairs_finite_state": _gate(
            actual=finite_count,
            threshold=pair_count,
            comparator="==",
            passed=(finite_count == pair_count),
            reason="one_or_more_pair_finite_state_failed",
        ),
        "all_pairs_online_truth_use_count": _gate(
            actual=truth_use_count,
            threshold=thresholds["all_pairs_online_truth_use_count"],
            comparator="==",
            passed=(
                truth_use_count
                == thresholds["all_pairs_online_truth_use_count"]
            ),
            reason="one_or_more_arm_online_truth_use_nonzero",
        ),
        "short_minimum_candidate_faster_count": _gate(
            actual=short_d1["candidate_better_count"],
            threshold=thresholds[
                "short_minimum_candidate_faster_count"
            ],
            comparator=">=",
            passed=(
                short_d1["candidate_better_count"]
                >= thresholds["short_minimum_candidate_faster_count"]
            ),
            reason="short_candidate_faster_count_below_threshold",
        ),
        "short_minimum_d1_fusion_improvement_pct": _gate(
            actual=short_d1["improvement_pct"]["mean"],
            threshold=thresholds[
                "short_minimum_d1_fusion_improvement_pct"
            ],
            comparator=">=",
            passed=(
                short_d1["improvement_pct"]["mean"]
                >= thresholds[
                    "short_minimum_d1_fusion_improvement_pct"
                ]
            ),
            reason="short_d1_fusion_improvement_below_threshold",
            unit="pct",
        ),
        "short_bootstrap_relative_change_upper_bound_pct": _gate(
            actual=short_bootstrap_upper,
            threshold=thresholds[
                "short_bootstrap_relative_change_upper_bound_pct"
            ],
            comparator="<=",
            passed=(
                short_bootstrap_upper
                <= thresholds[
                    "short_bootstrap_relative_change_upper_bound_pct"
                ]
            ),
            reason="short_bootstrap_upper_bound_above_threshold",
            unit="pct",
        ),
        "long_minimum_candidate_faster_count": _gate(
            actual=long_d1["candidate_better_count"],
            threshold=thresholds[
                "long_minimum_candidate_faster_count"
            ],
            comparator=">=",
            passed=(
                long_d1["candidate_better_count"]
                >= thresholds["long_minimum_candidate_faster_count"]
            ),
            reason="long_candidate_faster_count_below_threshold",
        ),
        "long_minimum_d1_fusion_improvement_pct": _gate(
            actual=long_d1["improvement_pct"]["mean"],
            threshold=thresholds[
                "long_minimum_d1_fusion_improvement_pct"
            ],
            comparator=">=",
            passed=(
                long_d1["improvement_pct"]["mean"]
                >= thresholds[
                    "long_minimum_d1_fusion_improvement_pct"
                ]
            ),
            reason="long_d1_fusion_improvement_below_threshold",
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
        "maximum_short_d1_scan_input_mean_increase_pct": _gate(
            actual=short_scan["raw_relative_change"]["mean"] * 100.0,
            threshold=thresholds[
                "maximum_short_d1_scan_input_mean_increase_pct"
            ],
            comparator="<=",
            passed=(
                short_scan["raw_relative_change"]["mean"] * 100.0
                <= thresholds[
                    "maximum_short_d1_scan_input_mean_increase_pct"
                ]
            ),
            reason="short_d1_scan_input_increase_above_threshold",
            unit="pct",
        ),
        "maximum_long_d1_scan_input_mean_increase_pct": _gate(
            actual=long_scan["raw_relative_change"]["mean"] * 100.0,
            threshold=thresholds[
                "maximum_long_d1_scan_input_mean_increase_pct"
            ],
            comparator="<=",
            passed=(
                long_scan["raw_relative_change"]["mean"] * 100.0
                <= thresholds[
                    "maximum_long_d1_scan_input_mean_increase_pct"
                ]
            ),
            reason="long_d1_scan_input_increase_above_threshold",
            unit="pct",
        ),
        "maximum_short_d2_association_mean_increase_pct": _gate(
            actual=short_d2["raw_relative_change"]["mean"] * 100.0,
            threshold=thresholds[
                "maximum_short_d2_association_mean_increase_pct"
            ],
            comparator="<=",
            passed=(
                short_d2["raw_relative_change"]["mean"] * 100.0
                <= thresholds[
                    "maximum_short_d2_association_mean_increase_pct"
                ]
            ),
            reason="short_d2_association_increase_above_threshold",
            unit="pct",
        ),
        "maximum_long_d2_association_mean_increase_pct": _gate(
            actual=long_d2["raw_relative_change"]["mean"] * 100.0,
            threshold=thresholds[
                "maximum_long_d2_association_mean_increase_pct"
            ],
            comparator="<=",
            passed=(
                long_d2["raw_relative_change"]["mean"] * 100.0
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
            actual=any_pair_rss_increase_pct,
            threshold=thresholds["maximum_any_pair_rss_increase_pct"],
            comparator="<=",
            passed=(
                any_pair_rss_increase_pct
                <= thresholds["maximum_any_pair_rss_increase_pct"]
            ),
            reason="one_or_more_pair_rss_increase_above_threshold",
            unit="pct",
        ),
        "minimum_candidate_non_radar_exact_solve_reduction_pct": _gate(
            actual=solve_reduction,
            threshold=thresholds[
                "minimum_candidate_non_radar_exact_solve_reduction_pct"
            ],
            comparator=">=",
            passed=(
                solve_reduction
                >= thresholds[
                    "minimum_candidate_non_radar_exact_solve_reduction_pct"
                ]
            ),
            reason="candidate_non_radar_exact_solve_reduction_below_threshold",
            unit="pct",
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


def write_d1_association_sparse_prefilter_multiseed_report(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write deterministic D6 products outside the producer evidence root."""

    if result.get("schema_version") != (
        D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_EVALUATION_SCHEMA_VERSION
    ):
        raise ValueError("unsupported association sparse-prefilter schema")
    contract = _required_mapping(
        result.get("input_contract"), "report input contract"
    )
    evidence_root_text = contract.get("output_root")
    directory = Path(output_dir).expanduser().resolve()
    if isinstance(evidence_root_text, str) and _base._path_is_within(
        directory, Path(evidence_root_text).expanduser().resolve()
    ):
        raise ValueError(
            "report output_dir must be independent of the evidence root"
        )
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "evaluation_json": directory
        / "d1_association_sparse_prefilter_multiseed_evaluation.json",
        "compact_json": directory
        / "d1_association_sparse_prefilter_multiseed_compact.json",
        "pairs_csv": directory
        / "d1_association_sparse_prefilter_multiseed_pairs.csv",
        "markdown": directory
        / "D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_REPORT_CN.md",
        "plot_png": directory
        / "d1_association_sparse_prefilter_multiseed_curves.png",
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
        render_d1_association_sparse_prefilter_multiseed_markdown(result),
        encoding="utf-8",
    )
    availability = _required_mapping(
        result.get("availability"), "report availability"
    )
    if availability.get("available") is True:
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
            D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_COMPACT_SCHEMA_VERSION
        ),
        "evaluation_schema_version": result["schema_version"],
        "evaluation_date": result["evaluation_date"],
        "availability": result["availability"],
        "input_contract": result["input_contract"],
        "scope": result["scope"],
        "thresholds": result["thresholds"],
        "groups": result["groups"],
        "association_sparse_prefilter_diagnostics_aggregate": result[
            "association_sparse_prefilter_diagnostics_aggregate"
        ],
        "admission_gates": result["admission_gates"],
        "admission_blockers": result["admission_blockers"],
        "verdict": result["verdict"],
        "optimization_admitted": result["optimization_admitted"],
        "main_default_promotion_allowed": result[
            "main_default_promotion_allowed"
        ],
        "system_realtime_gate": result["system_realtime_gate"],
        "system_realtime_gap_closed": result[
            "system_realtime_gap_closed"
        ],
        "system_realtime_status": result["system_realtime_status"],
    }


def render_d1_association_sparse_prefilter_multiseed_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the formal Chinese admission report."""

    availability = _required_mapping(
        result.get("availability"), "report availability"
    )
    contract = _required_mapping(
        result.get("input_contract"), "report input contract"
    )
    if availability.get("available") is not True:
        return "\n".join(
            [
                "# D1 关联稀疏预筛同提交多种子评估",
                "",
                "## 结论",
                "",
                "冻结证据不可用，D6 失败关闭。",
                (
                    f"原因：`{availability.get('reason')}`。候选 "
                    f"`{CANDIDATE_IMPLEMENTATION}` 不准入，main 不得默认晋升。"
                ),
                "系统实时缺口保持开放。",
                "",
                "本结果不修改 producer 证据，也不以缺失数据替代正式矩阵。",
                "",
            ]
        )
    groups = _required_mapping(result["groups"], "report groups")
    gates = _required_mapping(
        result["admission_gates"], "report gates"
    )
    diagnostics = result[
        "association_sparse_prefilter_diagnostics_aggregate"
    ]["groups"]["all"]
    candidate_modalities = diagnostics["candidate_modality_counts"]
    realtime = result["system_realtime_gate"]
    failed = [
        name for name, gate in gates.items() if gate["passed"] is not True
    ]
    if failed:
        admission_detail = (
            "失败门为 "
            + "、".join(f"`{name}`" for name in failed)
            + "。本轮不改门、不删 pair，结论为 reject。"
        )
    else:
        admission_detail = (
            "全部冻结准入门通过，结论为 admit；允许 main 在保留单参数回退的"
            "前提下另行实施默认晋升。"
        )
    lines = [
        "# D1 关联稀疏预筛同提交多种子评估",
        "",
        "## 结论",
        "",
        (
            f"正式 verdict 为 **{result['verdict']}**；main 默认晋升"
            f"{'允许' if result['main_default_promotion_allowed'] else '不允许'}。"
        ),
        (
            "系统实时缺口"
            f"{'已关闭' if result['system_realtime_gap_closed'] else '仍开放'}；"
            f"候选最低实时因子为 `{_fmt(realtime['candidate_minimum_real_time_factor'])}`，"
            "门限为 `>=1.0`，该判定与局部优化准入分离。"
        ),
        admission_detail,
        (
            "本报告仅使用三维质点仿真证据，不代表 AirSim、目标硬件、"
            "实机或实飞结论。"
        ),
        "",
        "## 证据范围",
        "",
        f"- 评估日期：`{result['evaluation_date']}`。",
        f"- clean source commit：`{contract['source_commit']}`。",
        (
            f"- evidence manifest SHA-256："
            f"`{contract['evidence_manifest_sha256']}`。"
        ),
        f"- 冻结 matrix SHA-256：`{contract['matrix_sha256']}`。",
        (
            f"- 规模：{_TARGET_COUNT} 个目标、{_RESOURCE_COUNT} 个资源、"
            f"{_RECON_COUNT} 个侦察节点。"
        ),
        (
            "- short 10 pair、long 3 pair，共 13 pair/26 fresh episode；"
            "26 complete、0 reused、0 failed。"
        ),
        (
            f"- reference `{REFERENCE_IMPLEMENTATION}`；candidate "
            f"`{CANDIDATE_IMPLEMENTATION}`；paired bootstrap "
            f"{contract['bootstrap_resamples']} 次。"
        ),
        "",
        "## 逐模态诊断",
        "",
        "| 模态 | Candidate pair | Rejection | Exact solve | Gate pass | Fallback |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for modality in _MODALITIES:
        counts = candidate_modalities[modality]
        lines.append(
            f"| `{modality}` | {counts['candidate_pair_count']} | "
            f"{counts['conservative_prefilter_rejection_count']} | "
            f"{counts['exact_innovation_solve_count']} | "
            f"{counts['exact_gate_pass_count']} | "
            f"{counts['fallback_count']} |"
        )
    lines.extend(
        [
            "",
            (
                "非雷达精确求解由 "
                f"`{diagnostics['reference_non_radar_exact_solve_count']}` "
                f"降至 `{diagnostics['candidate_non_radar_exact_solve_count']}`，"
                "减少 "
                f"`{_fmt(diagnostics['candidate_non_radar_exact_solve_reduction_pct'])}%`。"
            ),
            (
                "每个 pair、每个固定模态桶的 exact gate-pass 计数必须完全相等；"
                "六桶计数、总计和上界守恒均由 D6 重算。"
            ),
            "",
            "## 分组性能",
            "",
            "| 组别 | 指标 | Reference 均值 | Candidate 均值 | 配对变化 | Candidate 更优 |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    metric_rows = (
        ("d1_fusion_wall_s", "D1 fusion", "improvement"),
        ("core_wall_s", "核心墙钟", "improvement"),
        ("d1_scan_input_wall_s", "scan input", "raw"),
        ("d2_association_wall_s", "D2 association", "raw"),
        ("maximum_rss_kib", "RSS", "raw"),
        ("real_time_factor", "RTF", "improvement"),
    )
    for group in _GROUPS:
        label = "short" if group == "short" else "long"
        for metric, metric_label, change_kind in metric_rows:
            item = groups[group]["metrics"][metric]
            change = (
                item["improvement_pct"]["mean"]
                if change_kind == "improvement"
                else item["raw_relative_change"]["mean"] * 100.0
            )
            lines.append(
                f"| {label} | {metric_label} | "
                f"{_fmt(item['reference']['mean'])} | "
                f"{_fmt(item['candidate']['mean'])} | "
                f"{_fmt(change)}% | "
                f"{item['candidate_better_count']}/{item['pair_count']} |"
            )
    short_ci = groups["short"]["metrics"]["d1_fusion_wall_s"][
        "raw_relative_change"
    ]["bootstrap_95_ci"]
    long_ci = groups["long"]["metrics"]["d1_fusion_wall_s"][
        "raw_relative_change"
    ]["bootstrap_95_ci"]
    lines.extend(
        [
            "",
            (
                "D1 fusion 配对原始变化 95% bootstrap CI：short "
                f"`[{_fmt(short_ci['lower'] * 100.0)}, "
                f"{_fmt(short_ci['upper'] * 100.0)}]%`，long "
                f"`[{_fmt(long_ci['lower'] * 100.0)}, "
                f"{_fmt(long_ci['upper'] * 100.0)}]%`。"
            ),
            (
                "D1/core/RTF 使用正向改善口径；scan、D2、RSS 使用 "
                "`(candidate-reference)/reference`，负值表示下降。"
            ),
            "",
            "## 准入门",
            "",
            "| Gate | 实际值 | 判据 | 结果 |",
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
            "## 业务等价与边界",
            "",
            (
                "13 个 pair 均由 D6 重新执行规范跨 episode 比较。只排除预注册的 "
                "`same_runtime_profile`，并只归一化 selector、对应 execution config/"
                "diagnostics、关联精确求解诊断、运行时哈希派生 episode ID 和性能字段。"
            ),
            (
                "其他 summary、governance、在线消息、D3 计划谱系、D4 内容地址与 ACK、"
                "离线 truth state/labels/proximity 制品均继续比较；online truth use "
                "必须为 0。"
            ),
            (
                "selector、完整 implementation ID、execution config 和 diagnostics "
                "在 runtime profile、summary、module final 与 governance 四个主表面"
                "逐臂校验；runtime configuration 和 nested governance 另作冗余核对。"
            ),
            (
                "局部热点通过不能关闭系统实时、AirSim、目标硬件、RMSE、NEES、NIS "
                "或实飞验证。"
            ),
            "",
            "## 制品",
            "",
            "- `d1_association_sparse_prefilter_multiseed_evaluation.json`：完整评估。",
            "- `d1_association_sparse_prefilter_multiseed_compact.json`：紧凑汇总。",
            "- `d1_association_sparse_prefilter_multiseed_pairs.csv`：逐 pair 数据。",
            "- `d1_association_sparse_prefilter_multiseed_curves.png`：性能、求解削减与 RTF 曲线。",
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
        "association_sparse_prefilter_audit_passed",
        "exact_gate_pass_counts_equal",
        "reference_non_radar_exact_solve_count",
        "candidate_non_radar_exact_solve_count",
        "candidate_non_radar_exact_solve_reduction_pct",
    ]
    for modality in _MODALITIES:
        for field in _COUNTER_FIELDS:
            fieldnames.append(f"candidate__{modality}__{field}")
        fieldnames.append(
            f"reference__{modality}__exact_gate_pass_count"
        )
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
            audit = pair["association_sparse_prefilter_audit"]
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
                "association_sparse_prefilter_audit_passed": pair[
                    "association_sparse_prefilter_audit_passed"
                ],
                "exact_gate_pass_counts_equal": pair[
                    "exact_gate_pass_counts_equal"
                ],
                "reference_non_radar_exact_solve_count": audit[
                    "reference_non_radar_exact_solve_count"
                ],
                "candidate_non_radar_exact_solve_count": audit[
                    "candidate_non_radar_exact_solve_count"
                ],
                "candidate_non_radar_exact_solve_reduction_pct": audit[
                    "candidate_non_radar_exact_solve_reduction_pct"
                ],
            }
            reference_counts = pair["reference"][
                "association_sparse_prefilter_diagnostics"
            ]["modality_counts"]
            candidate_counts = pair["candidate"][
                "association_sparse_prefilter_diagnostics"
            ]["modality_counts"]
            for modality in _MODALITIES:
                for field in _COUNTER_FIELDS:
                    row[f"candidate__{modality}__{field}"] = (
                        candidate_counts[modality][field]
                    )
                row[
                    f"reference__{modality}__exact_gate_pass_count"
                ] = reference_counts[modality]["exact_gate_pass_count"]
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
    labels = [
        str(pair["case_id"]).replace("_seed_", "\n") for pair in pairs
    ]
    x = list(range(len(pairs)))
    fig, axes = plt.subplots(
        3,
        1,
        figsize=(11.5, 9.2),
        sharex=True,
        gridspec_kw={"height_ratios": [1.5, 1.0, 1.0]},
    )
    performance_axis, solve_axis, realtime_axis = axes
    for metric, label, color, raw in (
        ("d1_fusion_wall_s", "D1 fusion improvement", "#1f77b4", False),
        ("core_wall_s", "Core wall improvement", "#2ca02c", False),
        ("d1_scan_input_wall_s", "Scan-input increase", "#9467bd", True),
        ("d2_association_wall_s", "D2 increase", "#ff7f0e", True),
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
            linewidth=1.3,
            label=label,
            color=color,
        )
    performance_axis.axhline(0.0, color="#444444", linewidth=0.8)
    performance_axis.set_ylabel("Paired change (%)")
    performance_axis.grid(True, alpha=0.25)
    performance_axis.legend(ncol=2, fontsize=8, loc="best")

    solve_axis.plot(
        x,
        [
            float(
                pair["association_sparse_prefilter_audit"][
                    "candidate_non_radar_exact_solve_reduction_pct"
                ]
            )
            for pair in pairs
        ],
        marker="s",
        color="#17becf",
        label="Non-radar exact-solve reduction",
    )
    solve_axis.axhline(
        20.0,
        color="#d62728",
        linewidth=1.0,
        linestyle="--",
        label="Admission threshold 20%",
    )
    solve_axis.set_ylabel("Reduction (%)")
    solve_axis.grid(True, alpha=0.25)
    solve_axis.legend(fontsize=8, loc="best")

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
    fig.suptitle("D1 association sparse-prefilter paired evaluation")
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


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
        "--d1-association-sparse-prefilter-implementation",
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
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{case_id} arm command lengths differ"
        )
    selector_index = reference.index(
        "--d1-association-sparse-prefilter-implementation"
    ) + 1
    output_index = reference.index("--output") + 1
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index in {selector_index, output_index}:
            continue
        if left != right:
            raise D1AssociationSparsePrefilterEvidenceError(
                f"{case_id} arm commands differ outside treatment/output"
            )


def _case_metadata(
    case: Mapping[str, Any],
) -> tuple[str, str, int, float, tuple[str, ...]]:
    case_id = _required_text(case.get("case_id"), "case_id")
    group = _required_text(case.get("group"), f"{case_id} group")
    seed = case.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{case_id} seed must be an integer"
        )
    duration = case.get("duration_s")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(float(duration))
        or float(duration) <= 0.0
    ):
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{case_id} duration_s must be finite and positive"
        )
    arm_order = tuple(
        _required_text(item, f"{case_id} arm_order item")
        for item in _required_sequence(
            case.get("arm_order"), f"{case_id} arm_order"
        )
    )
    if len(arm_order) != 2 or set(arm_order) != set(_ARMS):
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{case_id} arm_order must contain reference and candidate"
        )
    return case_id, group, int(seed), float(duration), arm_order


def _strict_jsonl_count(path: Path) -> int:
    try:
        _base._strict_jsonl_digest(path)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1AssociationSparsePrefilterEvidenceError(str(exc)) from exc
    try:
        with path.open("r", encoding="utf-8") as stream:
            return sum(1 for line in stream if line.strip())
    except OSError as exc:
        raise D1AssociationSparsePrefilterEvidenceError(
            f"unable to count JSONL records in {path}: {exc}"
        ) from exc


def _load_stage(path: Path, stage_name: str) -> dict[str, Any]:
    try:
        return _base._load_stage(path, stage_name)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1AssociationSparsePrefilterEvidenceError(str(exc)) from exc


def _load_resource_metrics(path: Path) -> dict[str, float | int]:
    try:
        return _base._load_resource_metrics(path)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1AssociationSparsePrefilterEvidenceError(str(exc)) from exc


def _validate_stderr(path: Path, context: str) -> dict[str, Any]:
    try:
        return _base._validate_stderr(path, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1AssociationSparsePrefilterEvidenceError(str(exc)) from exc


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
        raise D1AssociationSparsePrefilterEvidenceError(str(exc)) from exc


def _load_mapping(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        return _base._load_strict_json_mapping(path)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1AssociationSparsePrefilterEvidenceError(str(exc)) from exc


def _required_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} must be a mapping"
        )
    return value


def _required_sequence(value: Any, context: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} must be a sequence"
        )
    return value


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} must be non-empty text"
        )
    return value


def _required_commit(value: Any, context: str) -> str:
    try:
        return _base._required_commit(value, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1AssociationSparsePrefilterEvidenceError(str(exc)) from exc


def _required_sha256(value: Any, context: str) -> str:
    try:
        return _base._required_sha256(value, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1AssociationSparsePrefilterEvidenceError(str(exc)) from exc


def _explicit_path(
    value: Any,
    context: str,
    *,
    require: str | None,
) -> Path:
    try:
        return _base._explicit_path(value, context, require=require)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1AssociationSparsePrefilterEvidenceError(str(exc)) from exc


def _require_under_root(path: Path, root: Path, context: str) -> None:
    try:
        _base._require_under_root(path, root, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1AssociationSparsePrefilterEvidenceError(str(exc)) from exc


def _expect(actual: Any, expected: Any, context: str) -> None:
    if actual != expected:
        raise D1AssociationSparsePrefilterEvidenceError(
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
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} mismatch: expected {expected!r}, got {actual!r}"
        )


def _nonnegative_integer(value: Any, context: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise D1AssociationSparsePrefilterEvidenceError(
            f"{context} must be a nonnegative integer"
        )
    return int(value)


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
            "Evaluate the frozen D1 association sparse-prefilter matrix"
        )
    )
    parser.add_argument(
        "--evidence-manifest",
        required=True,
        help="completed association sparse-prefilter evidence_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="independent D6 output directory",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = evaluate_d1_association_sparse_prefilter_multiseed(
        args.evidence_manifest
    )
    paths = write_d1_association_sparse_prefilter_multiseed_report(
        result, args.output_dir
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    print(f"verdict: {result['verdict']}")
    print(
        "main_default_promotion_allowed: "
        f"{str(result['main_default_promotion_allowed']).lower()}"
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
    "D1_ASSOCIATION_SPARSE_PREFILTER_DIAGNOSTICS_SCHEMA_VERSION",
    "D1_ASSOCIATION_SPARSE_PREFILTER_EVALUATION_DATE",
    "D1_ASSOCIATION_SPARSE_PREFILTER_EVIDENCE_SCHEMA_VERSION",
    "D1_ASSOCIATION_SPARSE_PREFILTER_EXECUTION_CONFIG_SCHEMA_VERSION",
    "D1_ASSOCIATION_SPARSE_PREFILTER_EXPERIMENT_ID",
    "D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SCHEMA_VERSION",
    "D1_ASSOCIATION_SPARSE_PREFILTER_MATRIX_SHA256",
    "D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_COMPACT_SCHEMA_VERSION",
    "D1_ASSOCIATION_SPARSE_PREFILTER_MULTISEED_EVALUATION_SCHEMA_VERSION",
    "D1_ASSOCIATION_SPARSE_PREFILTER_SOURCE_COMMIT",
    "D1AssociationSparsePrefilterEvidence",
    "D1AssociationSparsePrefilterEvidenceError",
    "REFERENCE_IMPLEMENTATION",
    "REFERENCE_IMPLEMENTATION_ID",
    "evaluate_d1_association_sparse_prefilter_multiseed",
    "load_d1_association_sparse_prefilter_evidence_manifest",
    "main",
    "render_d1_association_sparse_prefilter_multiseed_markdown",
    "write_d1_association_sparse_prefilter_multiseed_report",
]
