"""Independent D6 admission for the D1 replay-prefix summary candidate.

The producer persists one preregistered same-clean-commit 13-pair matrix.
This module is a read-only consumer: it validates every raw episode, compares
business semantics and exact online-consistency evidence, audits the
candidate's lazy ledger accounting, and applies only the frozen matrix gates.
It never mutates producer evidence or participates in online control.
"""

from __future__ import annotations

import argparse
import copy
import csv
from dataclasses import dataclass
import hashlib
import json
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


D1_REPLAY_PREFIX_SUMMARY_MULTISEED_EVALUATION_SCHEMA_VERSION = (
    "d6.d1_replay_prefix_summary_multiseed_evaluation.v1"
)
D1_REPLAY_PREFIX_SUMMARY_MULTISEED_COMPACT_SCHEMA_VERSION = (
    "d6.d1_replay_prefix_summary_multiseed_compact.v1"
)
D1_REPLAY_PREFIX_SUMMARY_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-replay-prefix-summary-multiseed-matrix-v1"
)
D1_REPLAY_PREFIX_SUMMARY_EVIDENCE_SCHEMA_VERSION = (
    "scalable3d-d1-replay-prefix-summary-multiseed-evidence-v1"
)
D1_REPLAY_PREFIX_SUMMARY_EXECUTION_CONFIG_SCHEMA_VERSION = (
    "d1.fixed_lag_replay_prefix_summary_execution_config.v1"
)
D1_REPLAY_PREFIX_SUMMARY_DIAGNOSTICS_SCHEMA_VERSION = (
    "d1.fixed_lag_replay_prefix_summary_diagnostics.v1"
)
D1_REPLAY_PREFIX_SUMMARY_SCHEMA_VERSION = (
    "d1.fixed_lag_replay_prefix_summary.v1"
)
D1_REPLAY_PREFIX_SUMMARY_EXPERIMENT_ID = (
    "d1-replay-prefix-summary-multiseed-20260725-v1"
)
D1_REPLAY_PREFIX_SUMMARY_MATRIX_SHA256 = (
    "85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b"
)
D1_REPLAY_PREFIX_SUMMARY_SOURCE_COMMIT = (
    "7d2e987471b521a1e531bf03a5c99af5096f676a"
)
D1_REPLAY_PREFIX_SUMMARY_EVALUATION_DATE = "2026-07-25"

REFERENCE_IMPLEMENTATION = "per_checkpoint_prefix_rebuild_v1"
CANDIDATE_IMPLEMENTATION = (
    "fixed_lag_checkpoint_prefix_cumulative_summary_v1"
)
REFERENCE_IMPLEMENTATION_ID = (
    "d1.fusion.replay_prefix.per_checkpoint_rebuild.v1"
)
CANDIDATE_IMPLEMENTATION_ID = (
    "d1.fusion.replay_prefix."
    "frozen_cumulative_summary_lazy_evidence_ranges.v1"
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
_SHORT_SEEDS = tuple(range(1151, 1161))
_LONG_SEEDS = tuple(range(1151, 1154))
_SHORT_DURATION_S = 2.2
_LONG_DURATION_S = 10.0
_BOOTSTRAP_RESAMPLES = 10_000
_BOOTSTRAP_SEED = 20_260_725
_VALIDATION_KIND = "replay_prefix_summary"
_SELECTOR_FIELD = "d1_replay_prefix_summary_implementation"
_EXECUTION_CONFIG_FIELD = (
    "d1_replay_prefix_summary_execution_config"
)
_DIAGNOSTICS_FIELD = "d1_replay_prefix_summary_diagnostics"
_TREATMENT_MARKER = "D6_REGISTERED_REPLAY_PREFIX_SUMMARY_TREATMENT"
_DIAGNOSTICS_MARKER = "D6_REGISTERED_REPLAY_PREFIX_SUMMARY_DIAGNOSTICS"
_PERFORMANCE_MARKER = "D6_REGISTERED_PERFORMANCE_DIAGNOSTIC"
_TREATMENT_DERIVED_ID_MARKER = "D6_TREATMENT_DERIVED_EPISODE_ID"

_EXPECTED_GATES = {
    "all_pairs_business_semantics_equal": True,
    "all_pairs_finite_state": True,
    "all_pairs_online_truth_use_count": 0,
    "all_pairs_explicit_implementation_identity": True,
    "all_pairs_replay_prefix_summary_audit_valid": True,
    "all_pairs_consistency_evidence_records_digest_equal": True,
    "all_pairs_existing_operation_counts_equal": True,
    "short_minimum_candidate_faster_count": 8,
    "short_minimum_d1_fusion_improvement_pct": 1.0,
    "short_bootstrap_relative_change_upper_bound_pct": 0.0,
    "long_minimum_candidate_faster_count": 2,
    "long_minimum_d1_fusion_improvement_pct": 1.0,
    "short_minimum_core_wall_improvement_pct": 0.25,
    "long_minimum_core_wall_improvement_pct": 0.25,
    "maximum_short_d1_scan_input_mean_increase_pct": 5.0,
    "maximum_long_d1_scan_input_mean_increase_pct": 5.0,
    "maximum_short_d2_association_mean_increase_pct": 5.0,
    "maximum_long_d2_association_mean_increase_pct": 5.0,
    "maximum_rss_mean_increase_pct": 5.0,
    "maximum_any_pair_rss_increase_pct": 5.0,
    "minimum_candidate_lazy_materialization_reduction_pct": 20.0,
}
_EXPECTED_BOUNDARY = {
    "simulation_mode": "three_dimensional_point_mass",
    "airsim_evidence": False,
    "truth_is_online_control_input": False,
    "system_realtime_requires_real_time_factor_at_least_one": True,
    "same_source_commit_for_both_arms": True,
    "only_allowed_runtime_treatment_difference": _SELECTOR_FIELD,
    "reference_implementation": REFERENCE_IMPLEMENTATION,
    "candidate_implementation": CANDIDATE_IMPLEMENTATION,
    "execution_config_schema_version": (
        D1_REPLAY_PREFIX_SUMMARY_EXECUTION_CONFIG_SCHEMA_VERSION
    ),
    "diagnostics_schema_version": (
        D1_REPLAY_PREFIX_SUMMARY_DIAGNOSTICS_SCHEMA_VERSION
    ),
    "summary_schema_version": D1_REPLAY_PREFIX_SUMMARY_SCHEMA_VERSION,
    "candidate_default_off": True,
    "fixed_lag_window_changed": False,
    "checkpoint_audit_semantics_changed": False,
    "consistency_evidence_semantics_changed": False,
    "truth_dependent_inputs_forbidden": True,
    "complete_trusted_checkpoint_prefix_required": True,
    "checkpoint_mutations_advance_revision": True,
    "offline_evidence_materializes_pending_ledger": True,
    "development_profile_seed_excluded": 1141,
    "prior_episode_outputs_reused": False,
}
_EXPECTED_CASES = (
    ("short_seed_1151", "short", 1151, 2.2, ("reference", "candidate")),
    ("short_seed_1152", "short", 1152, 2.2, ("candidate", "reference")),
    ("short_seed_1153", "short", 1153, 2.2, ("reference", "candidate")),
    ("short_seed_1154", "short", 1154, 2.2, ("candidate", "reference")),
    ("short_seed_1155", "short", 1155, 2.2, ("reference", "candidate")),
    ("short_seed_1156", "short", 1156, 2.2, ("candidate", "reference")),
    ("short_seed_1157", "short", 1157, 2.2, ("reference", "candidate")),
    ("short_seed_1158", "short", 1158, 2.2, ("candidate", "reference")),
    ("short_seed_1159", "short", 1159, 2.2, ("reference", "candidate")),
    ("short_seed_1160", "short", 1160, 2.2, ("candidate", "reference")),
    ("long_seed_1151", "long", 1151, 10.0, ("candidate", "reference")),
    ("long_seed_1152", "long", 1152, 10.0, ("reference", "candidate")),
    ("long_seed_1153", "long", 1153, 10.0, ("candidate", "reference")),
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
    "status",
    "started_at_utc",
    "completed_at_utc",
    "cases",
    "replay_prefix_summary_execution_config_schema_version",
    "replay_prefix_summary_diagnostics_schema_version",
    "replay_prefix_summary_schema_version",
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
    "expected_implementation",
    "expected_d1_implementation_id",
    "validation_kind",
    "expected_commit",
    "episode_dir",
    "resource_path",
    "stdout_path",
    "stderr_path",
    "command",
    "status",
    "return_code",
    "started_at_utc",
    "completed_at_utc",
}
_EXPECTED_EXECUTION_CONFIG_KEYS = {
    "schema_version",
    "selector",
    "selected_implementation_id",
    "default_selector",
    "reference_selector",
    "reference_implementation_id",
    "candidate_selector",
    "candidate_implementation_id",
    "candidate_enabled",
    "candidate_default_enabled",
    "rollback_selector",
    "summary_schema_version",
    "buffer_horizon_s",
    "truth_dependent_inputs",
    "fixed_lag_window_changed",
    "checkpoint_audit_semantics_changed",
    "consistency_evidence_semantics_changed",
}
_EXPECTED_DIAGNOSTICS_KEYS = {
    "schema_version",
    "execution_config",
    "selector",
    "selected_implementation_id",
    "operation_counts",
    "fallback_reasons",
    "materialization_reasons",
    "pending_consistency_ledger_count",
    "conservation",
}
_EXPECTED_CONSERVATION_KEYS = {
    "attempt_partition",
    "fallback_reason_partition",
    "hits_not_above_attempts",
    "reused_checkpoints_not_below_hits",
}
_D1_FUSION_PERFORMANCE_KEYS = {
    "schema_version",
    "batch_count",
    "scan_batch_count",
    "observation_count",
    "history_replay_count",
    "origin_replay_count",
    "finalization_replay_count",
    "replay_filter_update_count",
    "replay_checkpoint_reuse_count",
    "checkpoint_state_query_count",
    "fixed_lag_rebase_count",
    "fixed_lag_checkpoint_suffix_reuse_count",
    "replay_checkpoint_prefix_fast_path_count",
    "cached_consistency_refresh_count",
    "global_track_materialization_count",
    "sensor_health_snapshot_build_count",
    "association_candidate_pair_count",
    "association_innovation_solve_count",
    "current_track_count",
    "current_time",
}
_CANDIDATE_REQUIRED_POSITIVE_COUNTS = {
    "summary_attempt_count",
    "summary_hit_count",
    "summary_reused_checkpoint_count",
    "lazy_consistency_refresh_logical_record_count",
    "append_only_revision_advance_count",
    "append_only_pending_preservation_count",
    "append_only_pending_preserved_record_count",
    "public_snapshot_projection_count",
    "public_snapshot_projected_ledger_count",
    "public_snapshot_projected_event_count",
    "public_snapshot_projected_record_count",
}
_EXPORT_MATERIALIZATION_FIELDS = {
    "lazy_consistency_materialization_count",
    "lazy_consistency_materialized_event_count",
    "lazy_consistency_materialized_record_count",
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
    "offline_consistency/online_evidence.json",
)
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
_SHA256_PREFIXED_LENGTH = len("sha256:") + 64


class D1ReplayPrefixSummaryEvidenceError(ValueError):
    """Raised when producer evidence violates the frozen D6 contract."""


@dataclass(frozen=True)
class D1ReplayPrefixSummaryArmBinding:
    arm: str
    implementation: str
    episode_dir: Path
    resource_path: Path
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True)
class D1ReplayPrefixSummaryPairBinding:
    case_id: str
    group: str
    seed: int
    duration_s: float
    arm_order: tuple[str, str]
    arms: Mapping[str, D1ReplayPrefixSummaryArmBinding]


@dataclass(frozen=True)
class D1ReplayPrefixSummaryEvidence:
    source_path: Path
    source_sha256: str
    matrix_path: Path
    matrix_sha256: str
    matrix: Mapping[str, Any]
    output_root: Path
    source_commit: str
    source_worktree: Path
    pairs: tuple[D1ReplayPrefixSummaryPairBinding, ...]


def load_d1_replay_prefix_summary_evidence_manifest(
    source: str | Path,
) -> D1ReplayPrefixSummaryEvidence:
    """Bind one complete fresh 13-pair producer manifest."""

    source_path = Path(source).expanduser().resolve()
    manifest, manifest_raw = _load_mapping(source_path)
    if set(manifest) != _EXPECTED_MANIFEST_KEYS:
        raise D1ReplayPrefixSummaryEvidenceError(
            "evidence manifest fields differ from the frozen contract"
        )
    _expect(
        manifest.get("schema_version"),
        D1_REPLAY_PREFIX_SUMMARY_EVIDENCE_SCHEMA_VERSION,
        "evidence schema_version",
    )
    _expect(
        manifest.get("experiment_id"),
        D1_REPLAY_PREFIX_SUMMARY_EXPERIMENT_ID,
        "evidence experiment_id",
    )
    _expect(
        manifest.get("required_d6_evaluator_schema_version"),
        D1_REPLAY_PREFIX_SUMMARY_MULTISEED_EVALUATION_SCHEMA_VERSION,
        "required D6 evaluator schema",
    )
    _expect(
        manifest.get(
            "replay_prefix_summary_execution_config_schema_version"
        ),
        D1_REPLAY_PREFIX_SUMMARY_EXECUTION_CONFIG_SCHEMA_VERSION,
        "execution config schema",
    )
    _expect(
        manifest.get("replay_prefix_summary_diagnostics_schema_version"),
        D1_REPLAY_PREFIX_SUMMARY_DIAGNOSTICS_SCHEMA_VERSION,
        "diagnostics schema",
    )
    _expect(
        manifest.get("replay_prefix_summary_schema_version"),
        D1_REPLAY_PREFIX_SUMMARY_SCHEMA_VERSION,
        "summary schema",
    )
    if manifest.get("status") != "episodes_complete_pending_d6":
        raise D1ReplayPrefixSummaryEvidenceError(
            "evidence status must be episodes_complete_pending_d6"
        )
    _required_text(manifest.get("started_at_utc"), "started_at_utc")
    _required_text(manifest.get("completed_at_utc"), "completed_at_utc")
    source_commit = _required_commit(
        manifest.get("source_commit"), "source_commit"
    )
    _expect(
        source_commit,
        D1_REPLAY_PREFIX_SUMMARY_SOURCE_COMMIT,
        "frozen producer source_commit",
    )
    if manifest.get("source_repository_dirty") is not False:
        raise D1ReplayPrefixSummaryEvidenceError(
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
        raise D1ReplayPrefixSummaryEvidenceError(
            "evidence_manifest.json must be directly under output_root"
        )
    matrix_path = _explicit_path(
        manifest.get("matrix_path"), "matrix_path", require="file"
    )
    matrix_sha256 = _required_sha256(
        manifest.get("matrix_sha256"), "matrix_sha256"
    )
    if _base._file_sha256(matrix_path) != matrix_sha256:
        raise D1ReplayPrefixSummaryEvidenceError(
            "matrix_sha256 does not match matrix_path bytes"
        )
    _expect(
        matrix_sha256,
        D1_REPLAY_PREFIX_SUMMARY_MATRIX_SHA256,
        "frozen matrix_sha256",
    )
    matrix, _ = _load_mapping(matrix_path)
    _validate_matrix(matrix)
    if _required_mapping(manifest.get("matrix"), "embedded matrix") != matrix:
        raise D1ReplayPrefixSummaryEvidenceError(
            "embedded matrix does not exactly match matrix_path"
        )

    raw_cases = _required_sequence(manifest.get("cases"), "evidence cases")
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise D1ReplayPrefixSummaryEvidenceError(
            "evidence manifest must contain exactly 13 cases"
        )
    used_paths: set[Path] = {source_path}
    pairs: list[D1ReplayPrefixSummaryPairBinding] = []
    for raw_case, expected_case in zip(
        raw_cases, _EXPECTED_CASES, strict=True
    ):
        case = _required_mapping(raw_case, "evidence case")
        if set(case) != _EXPECTED_CASE_KEYS:
            raise D1ReplayPrefixSummaryEvidenceError(
                "evidence case fields differ from the frozen contract"
            )
        metadata = _case_metadata(case)
        if metadata != expected_case:
            raise D1ReplayPrefixSummaryEvidenceError(
                "evidence case differs from the frozen matrix"
            )
        case_id, group, seed, duration_s, arm_order = metadata
        if (
            case.get("d6_evaluation_status")
            != "episodes_complete_pending_d6"
        ):
            raise D1ReplayPrefixSummaryEvidenceError(
                f"{case_id} is not pending D6 evaluation"
            )
        raw_arms = _required_mapping(case.get("arms"), f"{case_id} arms")
        if set(raw_arms) != set(_ARMS):
            raise D1ReplayPrefixSummaryEvidenceError(
                f"{case_id} arms must be reference and candidate"
            )
        bindings: dict[str, D1ReplayPrefixSummaryArmBinding] = {}
        commands: dict[str, list[str]] = {}
        for arm in _ARMS:
            record = _required_mapping(
                raw_arms.get(arm), f"{case_id} {arm} arm"
            )
            if set(record) != _EXPECTED_ARM_KEYS:
                raise D1ReplayPrefixSummaryEvidenceError(
                    f"{case_id} {arm} fields differ from frozen contract"
                )
            implementation = _IMPLEMENTATIONS[arm]
            for actual, expected, label in (
                (record.get("arm"), arm, "arm"),
                (
                    record.get("expected_implementation"),
                    implementation,
                    "expected implementation",
                ),
                (
                    record.get("expected_d1_implementation_id"),
                    _IMPLEMENTATION_IDS[arm],
                    "expected D1 implementation ID",
                ),
                (
                    record.get("validation_kind"),
                    _VALIDATION_KIND,
                    "validation_kind",
                ),
                (
                    record.get("expected_commit"),
                    source_commit,
                    "expected commit",
                ),
            ):
                _expect(actual, expected, f"{case_id} {arm} {label}")
            _required_text(
                record.get("started_at_utc"),
                f"{case_id} {arm} started_at_utc",
            )
            _required_text(
                record.get("completed_at_utc"),
                f"{case_id} {arm} completed_at_utc",
            )
            if record.get("status") != "complete":
                raise D1ReplayPrefixSummaryEvidenceError(
                    f"{case_id} {arm} must be fresh complete, not reused/failed"
                )
            if record.get("return_code") != 0 or isinstance(
                record.get("return_code"), bool
            ):
                raise D1ReplayPrefixSummaryEvidenceError(
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
                    raise D1ReplayPrefixSummaryEvidenceError(
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
                raise D1ReplayPrefixSummaryEvidenceError(
                    f"{case_id} {arm} command differs from frozen execution"
                )
            commands[arm] = command
            bindings[arm] = D1ReplayPrefixSummaryArmBinding(
                arm=arm,
                implementation=implementation,
                episode_dir=episode_dir,
                resource_path=resource_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        _validate_pair_command_isolation(commands, case_id)
        pairs.append(
            D1ReplayPrefixSummaryPairBinding(
                case_id=case_id,
                group=group,
                seed=seed,
                duration_s=duration_s,
                arm_order=arm_order,
                arms=bindings,
            )
        )
    if len(pairs) * 2 != 26:
        raise D1ReplayPrefixSummaryEvidenceError(
            "evidence must bind exactly 26 fresh arms"
        )
    return D1ReplayPrefixSummaryEvidence(
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


def evaluate_d1_replay_prefix_summary_multiseed(
    source: str | Path,
    *,
    raise_on_invalid: bool = False,
) -> dict[str, Any]:
    """Evaluate the frozen matrix or return a fail-closed result."""

    try:
        return _evaluate_available(source)
    except (
        D1ReplayPrefixSummaryEvidenceError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        if raise_on_invalid:
            if isinstance(exc, D1ReplayPrefixSummaryEvidenceError):
                raise
            raise D1ReplayPrefixSummaryEvidenceError(str(exc)) from exc
        return _unavailable_evaluation(source, str(exc))


def _evaluate_available(source: str | Path) -> dict[str, Any]:
    evidence = load_d1_replay_prefix_summary_evidence_manifest(source)
    pairs = [_evaluate_pair(pair, evidence) for pair in evidence.pairs]
    groups = {
        group: _summarize_group(
            [pair for pair in pairs if pair["group"] == group],
            group=group,
            bootstrap_resamples=int(
                evidence.matrix["bootstrap_resamples"]
            ),
            bootstrap_seed=int(evidence.matrix["bootstrap_seed"]),
        )
        for group in _GROUPS
    }
    diagnostics_aggregate = _aggregate_replay_diagnostics(pairs)
    thresholds = copy.deepcopy(
        dict(evidence.matrix["admission_gates"])
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
            D1_REPLAY_PREFIX_SUMMARY_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": D1_REPLAY_PREFIX_SUMMARY_EVALUATION_DATE,
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "availability": {"available": True, "reason": None},
        "input_contract": {
            "evidence_manifest_path": str(evidence.source_path),
            "evidence_manifest_sha256": evidence.source_sha256,
            "evidence_manifest_schema_version": (
                D1_REPLAY_PREFIX_SUMMARY_EVIDENCE_SCHEMA_VERSION
            ),
            "evidence_manifest_status": (
                "episodes_complete_pending_d6"
            ),
            "matrix_path": str(evidence.matrix_path),
            "matrix_sha256": evidence.matrix_sha256,
            "matrix_schema_version": (
                D1_REPLAY_PREFIX_SUMMARY_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": D1_REPLAY_PREFIX_SUMMARY_EXPERIMENT_ID,
            "output_root": str(evidence.output_root),
            "source_commit": evidence.source_commit,
            "source_repository_dirty": False,
            "same_commit_for_both_arms": True,
            "arm_implementations": dict(_IMPLEMENTATIONS),
            "arm_implementation_ids": dict(_IMPLEMENTATION_IDS),
            "pair_count": len(pairs),
            "arm_count": len(pairs) * 2,
            "fresh_arm_count": len(pairs) * 2,
            "reused_arm_count": 0,
            "failed_arm_count": 0,
            "bootstrap_resamples": int(
                evidence.matrix["bootstrap_resamples"]
            ),
            "bootstrap_rng_seed": int(
                evidence.matrix["bootstrap_seed"]
            ),
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
            "clean_seed_1151_precheck_is_formal_evidence": False,
            "module_microbenchmark_is_admission_evidence": False,
            "semantic_equivalence_generated_by_d6": True,
        },
        "thresholds": thresholds,
        "pairs": pairs,
        "groups": groups,
        "replay_prefix_summary_diagnostics_aggregate": (
            diagnostics_aggregate
        ),
        "admission_gates": gates,
        "admission_blockers": blockers,
        "optimization_admitted": admitted,
        "verdict": "admit" if admitted else "reject",
        "main_default_promotion_allowed": admitted,
        "system_realtime_gate": realtime_gate,
        "system_realtime_gap_closed": bool(realtime_gate["passed"]),
        "evidence_boundary_statement": (
            "The verdict applies only to the frozen 13-pair 200v200 "
            "three-dimensional point-mass matrix. It is not AirSim, "
            "hardware, flight-test, or module-microbenchmark evidence."
        ),
    }


def _unavailable_evaluation(
    source: str | Path, reason: str
) -> dict[str, Any]:
    gate = _gate(
        actual=False,
        threshold=True,
        comparator="==",
        passed=False,
        reason="evidence_unavailable",
    )
    return {
        "schema_version": (
            D1_REPLAY_PREFIX_SUMMARY_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": D1_REPLAY_PREFIX_SUMMARY_EVALUATION_DATE,
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "availability": {"available": False, "reason": reason},
        "input_contract": {
            "evidence_manifest_path": str(
                Path(source).expanduser().resolve()
            ),
            "matrix_sha256": D1_REPLAY_PREFIX_SUMMARY_MATRIX_SHA256,
            "matrix_schema_version": (
                D1_REPLAY_PREFIX_SUMMARY_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": D1_REPLAY_PREFIX_SUMMARY_EXPERIMENT_ID,
            "source_commit": D1_REPLAY_PREFIX_SUMMARY_SOURCE_COMMIT,
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
        "replay_prefix_summary_diagnostics_aggregate": {},
        "admission_gates": {"evidence_available": gate},
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
        "verdict": "reject",
        "main_default_promotion_allowed": False,
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
        raise D1ReplayPrefixSummaryEvidenceError(
            "matrix fields differ from the frozen contract"
        )
    expected_scalars = {
        "schema_version": D1_REPLAY_PREFIX_SUMMARY_MATRIX_SCHEMA_VERSION,
        "experiment_id": D1_REPLAY_PREFIX_SUMMARY_EXPERIMENT_ID,
        "same_clean_commit_required": True,
        "target_count": _TARGET_COUNT,
        "resource_count": _RESOURCE_COUNT,
        "recon_count": _RECON_COUNT,
        "arm_implementations": _IMPLEMENTATIONS,
        "run_flags": list(_RUN_FLAGS),
        "bootstrap_seed": _BOOTSTRAP_SEED,
        "bootstrap_resamples": _BOOTSTRAP_RESAMPLES,
        "admission_gates": _EXPECTED_GATES,
        "evidence_boundary": _EXPECTED_BOUNDARY,
    }
    for field, expected in expected_scalars.items():
        _expect(matrix.get(field), expected, f"matrix {field}")
    cooldown = matrix.get("cooldown_s")
    if (
        isinstance(cooldown, bool)
        or not isinstance(cooldown, (int, float))
        or not math.isfinite(float(cooldown))
        or float(cooldown) != 2.0
    ):
        raise D1ReplayPrefixSummaryEvidenceError(
            "matrix cooldown_s must equal 2.0"
        )
    raw_cases = _required_sequence(matrix.get("cases"), "matrix cases")
    actual = tuple(_case_metadata(item) for item in raw_cases)
    if actual != _EXPECTED_CASES:
        raise D1ReplayPrefixSummaryEvidenceError(
            "matrix cases differ from the frozen registration"
        )


def _evaluate_pair(
    pair: D1ReplayPrefixSummaryPairBinding,
    evidence: D1ReplayPrefixSummaryEvidence,
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
    consistency_equal = (
        reference["online_consistency_evidence"]["records_digest"]
        == candidate["online_consistency_evidence"]["records_digest"]
        and reference["online_consistency_evidence"]["record_count"]
        == candidate["online_consistency_evidence"]["record_count"]
    )
    operation_counts_equal = (
        reference["d1_fusion_performance"]
        == candidate["d1_fusion_performance"]
    )
    diagnostics_audit = _pair_replay_diagnostics_audit(
        reference["replay_prefix_summary_diagnostics"],
        candidate["replay_prefix_summary_diagnostics"],
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
        "consistency_evidence_records_digest_equal": consistency_equal,
        "existing_operation_counts_equal": operation_counts_equal,
        "replay_prefix_summary_audit": diagnostics_audit,
        "replay_prefix_summary_audit_passed": bool(
            diagnostics_audit["passed"]
        ),
        "performance": performance,
    }


def _evaluate_arm(
    binding: D1ReplayPrefixSummaryArmBinding,
    *,
    pair: D1ReplayPrefixSummaryPairBinding,
    expected_commit: str,
) -> dict[str, Any]:
    context = f"{pair.case_id} {binding.arm}"
    paths = {
        name: binding.episode_dir / name
        for name in _CONSUMED_EPISODE_FILES
    }
    for name, path in paths.items():
        if not path.is_file():
            raise D1ReplayPrefixSummaryEvidenceError(
                f"{context} missing {name}"
            )
    manifest, manifest_raw = _load_mapping(paths["manifest.json"])
    config, config_raw = _load_mapping(paths["scenario_config.json"])
    summary, summary_raw = _load_mapping(paths["summary.json"])
    governance, governance_raw = _load_mapping(
        paths["observation_governance_audit.json"]
    )
    online_evidence, online_evidence_raw = _load_mapping(
        paths["offline_consistency/online_evidence.json"]
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
    consistency = _validate_online_consistency_evidence(
        online_evidence, context=context
    )
    final = _required_mapping(
        summary.get("module_final_diagnostics"),
        f"{context} module_final_diagnostics",
    )
    fusion_performance = _validate_d1_fusion_performance(
        _required_mapping(
            final.get("d1_fusion_performance"),
            f"{context} d1_fusion_performance",
        ),
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
        raise D1ReplayPrefixSummaryEvidenceError(str(exc)) from exc
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
        "offline_consistency/online_evidence.json": (
            _base._sha256_bytes(online_evidence_raw)
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
        "replay_prefix_summary_diagnostics": diagnostics,
        "d1_fusion_performance": fusion_performance,
        "online_consistency_evidence": consistency,
        "business_count_snapshot": _business_count_snapshot(summary),
        "artifact_provenance": {
            "passed": True,
            "path_count": len(input_sha256),
            "input_file_sha256": input_sha256,
        },
        "stage_timings": stages,
        "resource_metrics": resource,
        "stderr_audit": stderr_audit,
        "metrics": metrics,
        "_semantic_input": {
            "episode_dir": binding.episode_dir,
            "config": config,
        },
    }


def _validate_arm_provenance(
    *,
    pair: D1ReplayPrefixSummaryPairBinding,
    binding: D1ReplayPrefixSummaryArmBinding,
    expected_commit: str,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> Mapping[str, Any]:
    context = f"{pair.case_id} {binding.arm}"
    if manifest.get("git_commit") != expected_commit:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} source commit mismatch"
        )
    if manifest.get("repository_dirty") is not False:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} repository is dirty"
        )
    if manifest.get("config_sha256") != _base._canonical_sha256(config):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} config_sha256 mismatch"
        )
    runtime_profile = _required_mapping(
        manifest.get("runtime_profile"), f"{context} runtime_profile"
    )
    if manifest.get("runtime_profile_sha256") != _base._canonical_sha256(
        runtime_profile
    ):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} runtime_profile_sha256 mismatch"
        )
    for actual, expected, label in (
        (
            config.get("schema_version"),
            "scalable3d-scenario-v1",
            "config schema",
        ),
        (
            runtime_profile.get("schema_version"),
            "scalable3d-integrated-stack-runtime-profile-v1",
            "runtime profile schema",
        ),
        (
            governance.get("schema_version"),
            "scalable3d-observation-governance-runtime-v2",
            "governance schema",
        ),
        (manifest.get("seed"), pair.seed, "manifest seed"),
        (config.get("seed"), pair.seed, "config seed"),
        (summary.get("seed"), pair.seed, "summary seed"),
        (config.get("target_count"), _TARGET_COUNT, "config target_count"),
        (
            summary.get("target_count"),
            _TARGET_COUNT,
            "summary target_count",
        ),
        (
            config.get("resource_count"),
            _RESOURCE_COUNT,
            "config resource_count",
        ),
        (
            summary.get("resource_count"),
            _RESOURCE_COUNT,
            "summary resource_count",
        ),
        (config.get("recon_count"), _RECON_COUNT, "config recon_count"),
        (
            summary.get("recon_count"),
            _RECON_COUNT,
            "summary recon_count",
        ),
    ):
        _expect(actual, expected, f"{context} {label}")
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
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} finite_state must be true"
        )
    if (
        summary.get("online_truth_use_count") != 0
        or governance.get("online_truth_use_count") != 0
    ):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} online truth use must be zero"
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
        "runtime_profile.configuration": configuration.get(
            _SELECTOR_FIELD
        ),
        "summary": summary.get(_SELECTOR_FIELD),
        "module_final": final.get(_SELECTOR_FIELD),
        "nested_governance": nested.get(_SELECTOR_FIELD),
        "governance": governance.get(_SELECTOR_FIELD),
    }
    mismatches = [
        f"{name}={value!r}"
        for name, value in selectors.items()
        if value != expected
    ]
    if mismatches:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} selector mismatch: " + ", ".join(mismatches)
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
    validated_execution = [
        _validate_execution_config(
            value, arm=arm, context=f"{context} {name}"
        )
        for name, value in execution_locations.items()
    ]
    if any(
        item != validated_execution[0] for item in validated_execution[1:]
    ):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} execution configs differ across surfaces"
        )

    initial = _validate_diagnostics(
        _required_mapping(
            runtime_profile.get(_DIAGNOSTICS_FIELD),
            f"{context} initial diagnostics",
        ),
        arm=arm,
        context=f"{context} runtime_profile",
        phase="initial",
    )
    exported = _validate_diagnostics(
        _required_mapping(
            summary.get(_DIAGNOSTICS_FIELD),
            f"{context} exported diagnostics",
        ),
        arm=arm,
        context=f"{context} summary",
        phase="exported",
    )
    governance_exported = _validate_diagnostics(
        _required_mapping(
            governance.get(_DIAGNOSTICS_FIELD),
            f"{context} governance diagnostics",
        ),
        arm=arm,
        context=f"{context} governance",
        phase="exported",
    )
    module_final = _validate_diagnostics(
        _required_mapping(
            final.get(_DIAGNOSTICS_FIELD),
            f"{context} module-final diagnostics",
        ),
        arm=arm,
        context=f"{context} module_final",
        phase="module_final",
    )
    nested_final = _validate_diagnostics(
        _required_mapping(
            nested.get(_DIAGNOSTICS_FIELD),
            f"{context} nested diagnostics",
        ),
        arm=arm,
        context=f"{context} nested governance",
        phase="module_final",
    )
    if exported != governance_exported:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} exported diagnostics surfaces differ"
        )
    if module_final != nested_final:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} module-final diagnostics surfaces differ"
        )
    _validate_export_transition(
        module_final,
        exported,
        arm=arm,
        context=context,
    )
    return {
        "initial": initial,
        "module_final": module_final,
        "exported": exported,
    }, {
        "passed": True,
        "selector_surface_count": len(selectors),
        "execution_config_surface_count": len(execution_locations),
        "initial_diagnostics_checked": True,
        "module_final_surfaces_equal": True,
        "exported_surfaces_equal": True,
        "export_transition_accounted": True,
    }


def _validate_execution_config(
    value: Mapping[str, Any],
    *,
    arm: str,
    context: str,
) -> dict[str, Any]:
    if set(value) != _EXPECTED_EXECUTION_CONFIG_KEYS:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} execution config fields mismatch"
        )
    candidate = arm == _CANDIDATE_ARM
    expected = {
        "schema_version": (
            D1_REPLAY_PREFIX_SUMMARY_EXECUTION_CONFIG_SCHEMA_VERSION
        ),
        "selector": _IMPLEMENTATIONS[arm],
        "selected_implementation_id": _IMPLEMENTATION_IDS[arm],
        "default_selector": REFERENCE_IMPLEMENTATION,
        "reference_selector": REFERENCE_IMPLEMENTATION,
        "reference_implementation_id": REFERENCE_IMPLEMENTATION_ID,
        "candidate_selector": CANDIDATE_IMPLEMENTATION,
        "candidate_implementation_id": CANDIDATE_IMPLEMENTATION_ID,
        "candidate_enabled": candidate,
        "candidate_default_enabled": False,
        "rollback_selector": REFERENCE_IMPLEMENTATION,
        "summary_schema_version": D1_REPLAY_PREFIX_SUMMARY_SCHEMA_VERSION,
        "buffer_horizon_s": 6.0,
        "truth_dependent_inputs": False,
        "fixed_lag_window_changed": False,
        "checkpoint_audit_semantics_changed": False,
        "consistency_evidence_semantics_changed": False,
    }
    if dict(value) != expected:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} execution config value mismatch"
        )
    return copy.deepcopy(expected)


def _validate_diagnostics(
    value: Mapping[str, Any],
    *,
    arm: str,
    context: str,
    phase: str,
) -> dict[str, Any]:
    if set(value) != _EXPECTED_DIAGNOSTICS_KEYS:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} diagnostics fields mismatch"
        )
    _expect(
        value.get("schema_version"),
        D1_REPLAY_PREFIX_SUMMARY_DIAGNOSTICS_SCHEMA_VERSION,
        f"{context} diagnostics schema",
    )
    _expect(
        value.get("selector"),
        _IMPLEMENTATIONS[arm],
        f"{context} selector",
    )
    _expect(
        value.get("selected_implementation_id"),
        _IMPLEMENTATION_IDS[arm],
        f"{context} implementation ID",
    )
    execution = _validate_execution_config(
        _required_mapping(
            value.get("execution_config"),
            f"{context} diagnostics execution config",
        ),
        arm=arm,
        context=f"{context} diagnostics",
    )
    operations = _validated_count_mapping(
        value.get("operation_counts"), f"{context} operation_counts"
    )
    fallback_reasons = _validated_count_mapping(
        value.get("fallback_reasons"), f"{context} fallback_reasons"
    )
    materialization_reasons = _validated_count_mapping(
        value.get("materialization_reasons"),
        f"{context} materialization_reasons",
    )
    pending = _nonnegative_integer(
        value.get("pending_consistency_ledger_count"),
        f"{context} pending ledger count",
    )
    conservation = _required_mapping(
        value.get("conservation"), f"{context} conservation"
    )
    if set(conservation) != _EXPECTED_CONSERVATION_KEYS or any(
        conservation.get(field) is not True
        for field in _EXPECTED_CONSERVATION_KEYS
    ):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} conservation flags failed"
        )
    attempts = operations.get("summary_attempt_count", 0)
    hits = operations.get("summary_hit_count", 0)
    fallbacks = operations.get("summary_fallback_count", 0)
    reused = operations.get("summary_reused_checkpoint_count", 0)
    logical = operations.get(
        "lazy_consistency_refresh_logical_record_count", 0
    )
    materialized = operations.get(
        "lazy_consistency_materialized_record_count", 0
    )
    materialization_count = operations.get(
        "lazy_consistency_materialization_count", 0
    )
    if (
        attempts != hits + fallbacks
        or fallbacks != sum(fallback_reasons.values())
        or hits > attempts
        or reused < hits
        or materialized > logical
        or materialization_count != sum(materialization_reasons.values())
    ):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} diagnostics count conservation failed"
        )
    candidate = arm == _CANDIDATE_ARM
    if phase == "initial":
        if (
            operations
            or fallback_reasons
            or materialization_reasons
            or pending != 0
        ):
            raise D1ReplayPrefixSummaryEvidenceError(
                f"{context} initial diagnostics must be zero"
            )
    elif candidate:
        missing_positive = [
            field
            for field in sorted(_CANDIDATE_REQUIRED_POSITIVE_COUNTS)
            if operations.get(field, 0) <= 0
        ]
        if missing_positive:
            raise D1ReplayPrefixSummaryEvidenceError(
                f"{context} candidate workload counters are not positive: "
                + ", ".join(missing_positive)
            )
        if (
            operations.get("append_only_pending_incompatible_count", 0)
            != 0
            or materialization_reasons.get(
                "checkpoint_suffix_appended", 0
            )
            != 0
            or materialization_reasons.get(
                "checkpoint_suffix_append_incompatible", 0
            )
            != 0
        ):
            raise D1ReplayPrefixSummaryEvidenceError(
                f"{context} normal/incompatible append materialized"
            )
        if (
            operations["append_only_pending_preservation_count"]
            > operations["append_only_revision_advance_count"]
        ):
            raise D1ReplayPrefixSummaryEvidenceError(
                f"{context} append preservation exceeds revision advances"
            )
        if phase == "exported" and pending != 0:
            raise D1ReplayPrefixSummaryEvidenceError(
                f"{context} exported pending ledger must be zero"
            )
    else:
        if (
            operations
            or fallback_reasons
            or materialization_reasons
            or pending != 0
        ):
            raise D1ReplayPrefixSummaryEvidenceError(
                f"{context} reference candidate counters must be zero"
            )
    return {
        "schema_version": value["schema_version"],
        "execution_config": execution,
        "selector": value["selector"],
        "selected_implementation_id": value[
            "selected_implementation_id"
        ],
        "operation_counts": operations,
        "fallback_reasons": fallback_reasons,
        "materialization_reasons": materialization_reasons,
        "pending_consistency_ledger_count": pending,
        "conservation": copy.deepcopy(dict(conservation)),
    }


def _validate_export_transition(
    module_final: Mapping[str, Any],
    exported: Mapping[str, Any],
    *,
    arm: str,
    context: str,
) -> None:
    if arm == _REFERENCE_ARM:
        if module_final != exported:
            raise D1ReplayPrefixSummaryEvidenceError(
                f"{context} reference diagnostics changed during export"
            )
        return
    final_ops = module_final["operation_counts"]
    exported_ops = exported["operation_counts"]
    all_fields = set(final_ops) | set(exported_ops)
    for field in all_fields:
        before = int(final_ops.get(field, 0))
        after = int(exported_ops.get(field, 0))
        if field in _EXPORT_MATERIALIZATION_FIELDS:
            if after < before:
                raise D1ReplayPrefixSummaryEvidenceError(
                    f"{context} export materialization counter decreased"
                )
        elif before != after:
            raise D1ReplayPrefixSummaryEvidenceError(
                f"{context} non-export counter changed during export: {field}"
            )
    if (
        module_final["fallback_reasons"]
        != exported["fallback_reasons"]
    ):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} fallback reasons changed during export"
        )
    final_reasons = module_final["materialization_reasons"]
    exported_reasons = exported["materialization_reasons"]
    reason_fields = set(final_reasons) | set(exported_reasons)
    for reason in reason_fields:
        before = int(final_reasons.get(reason, 0))
        after = int(exported_reasons.get(reason, 0))
        if reason == "public_evidence_snapshot":
            if after < before:
                raise D1ReplayPrefixSummaryEvidenceError(
                    f"{context} public export materialization decreased"
                )
        elif before != after:
            raise D1ReplayPrefixSummaryEvidenceError(
                f"{context} unexpected materialization reason changed: {reason}"
            )
    pending_before = int(
        module_final["pending_consistency_ledger_count"]
    )
    export_materializations = (
        int(
            exported_ops.get(
                "lazy_consistency_materialization_count", 0
            )
        )
        - int(
            final_ops.get("lazy_consistency_materialization_count", 0)
        )
    )
    export_reason_delta = int(
        exported_reasons.get("public_evidence_snapshot", 0)
    ) - int(final_reasons.get("public_evidence_snapshot", 0))
    if (
        exported["pending_consistency_ledger_count"] != 0
        or export_materializations != pending_before
        or export_reason_delta != pending_before
    ):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} final export ledger accounting mismatch"
        )


def _validate_online_consistency_evidence(
    value: Mapping[str, Any],
    *,
    context: str,
) -> dict[str, Any]:
    expected_keys = {
        "schema_version",
        "record_schema_version",
        "range_bin_schema_version",
        "range_bin_edges_m",
        "provenance",
        "record_count",
        "records_digest",
        "truth_policy",
        "content_digest",
        "records",
    }
    if set(value) != expected_keys:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} online evidence fields mismatch"
        )
    _expect(
        value.get("schema_version"),
        "d1.consistency.online_evidence_bundle.v1",
        f"{context} online evidence schema",
    )
    _expect(
        value.get("truth_policy"),
        "online_truth_forbidden",
        f"{context} online evidence truth policy",
    )
    records = _required_sequence(
        value.get("records"), f"{context} online evidence records"
    )
    record_count = _nonnegative_integer(
        value.get("record_count"), f"{context} record_count"
    )
    if record_count <= 0 or len(records) != record_count:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} online evidence record_count mismatch"
        )
    records_digest = _required_prefixed_sha256(
        value.get("records_digest"), f"{context} records_digest"
    )
    actual_records_digest = _payload_sha256(list(records))
    if records_digest != actual_records_digest:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} records_digest does not match records"
        )
    unsigned = {
        key: copy.deepcopy(value[key])
        for key in (
            "schema_version",
            "record_schema_version",
            "range_bin_schema_version",
            "range_bin_edges_m",
            "provenance",
            "record_count",
            "records_digest",
            "truth_policy",
        )
    }
    content_digest = _required_prefixed_sha256(
        value.get("content_digest"), f"{context} content_digest"
    )
    if content_digest != _payload_sha256(unsigned):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} online evidence content_digest mismatch"
        )
    return {
        "schema_version": value["schema_version"],
        "record_count": record_count,
        "records_digest": records_digest,
        "content_digest": content_digest,
    }


def _validate_d1_fusion_performance(
    value: Mapping[str, Any], *, context: str
) -> dict[str, Any]:
    if set(value) != _D1_FUSION_PERFORMANCE_KEYS:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} D1 fusion performance fields mismatch"
        )
    _expect(
        value.get("schema_version"),
        "d1.fusion_performance_diagnostics.v1",
        f"{context} D1 fusion performance schema",
    )
    result: dict[str, Any] = {"schema_version": value["schema_version"]}
    for field in sorted(
        _D1_FUSION_PERFORMANCE_KEYS - {"schema_version", "current_time"}
    ):
        result[field] = _nonnegative_integer(
            value.get(field), f"{context} D1 fusion {field}"
        )
    result["current_time"] = _finite_nonnegative(
        value.get("current_time"),
        f"{context} D1 fusion current_time",
    )
    return result


def _pair_replay_diagnostics_audit(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    reference_exported = reference["exported"]
    candidate_exported = candidate["exported"]
    candidate_final = candidate["module_final"]
    operations = candidate_exported["operation_counts"]
    logical = int(
        operations["lazy_consistency_refresh_logical_record_count"]
    )
    materialized = int(
        operations.get("lazy_consistency_materialized_record_count", 0)
    )
    reduction = (logical - materialized) / logical * 100.0
    projected = int(
        operations["public_snapshot_projected_record_count"]
    )
    checks = {
        "reference_candidate_counters_zero": (
            not reference_exported["operation_counts"]
            and not reference_exported["fallback_reasons"]
            and not reference_exported["materialization_reasons"]
            and reference_exported["pending_consistency_ledger_count"] == 0
        ),
        "candidate_summary_hits_positive": (
            operations["summary_hit_count"] > 0
        ),
        "candidate_checkpoint_reuse_positive": (
            operations["summary_reused_checkpoint_count"] > 0
        ),
        "append_revision_positive": (
            operations["append_only_revision_advance_count"] > 0
        ),
        "append_pending_preservation_positive": (
            operations["append_only_pending_preservation_count"] > 0
        ),
        "online_snapshot_projection_positive": projected > 0,
        "normal_append_materialization_zero": (
            candidate_exported["materialization_reasons"].get(
                "checkpoint_suffix_appended", 0
            )
            == 0
        ),
        "incompatible_append_materialization_zero": (
            candidate_exported["materialization_reasons"].get(
                "checkpoint_suffix_append_incompatible", 0
            )
            == 0
            and operations.get(
                "append_only_pending_incompatible_count", 0
            )
            == 0
        ),
        "exported_pending_zero": (
            candidate_exported["pending_consistency_ledger_count"] == 0
        ),
        "module_final_pending_nonnegative": (
            candidate_final["pending_consistency_ledger_count"] >= 0
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "candidate_logical_refresh_record_count": logical,
        "candidate_actual_materialized_record_count": materialized,
        "candidate_lazy_materialization_reduction_pct": reduction,
        "candidate_online_snapshot_projected_record_count": projected,
        "candidate_disclosed_record_construction_count": (
            materialized + projected
        ),
        "candidate_module_final_pending_ledger_count": candidate_final[
            "pending_consistency_ledger_count"
        ],
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
        raise D1ReplayPrefixSummaryEvidenceError(
            "normalized runtime configuration lacks selector"
        )
    configuration[_SELECTOR_FIELD] = _TREATMENT_MARKER
    return normalized


def _normalized_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(summary))
    for field in ("episode_id", "wall_time_s", "real_time_factor"):
        if field not in normalized:
            raise D1ReplayPrefixSummaryEvidenceError(
                f"normalized summary lacks {field}"
            )
    normalized["episode_id"] = _TREATMENT_DERIVED_ID_MARKER
    normalized["wall_time_s"] = _PERFORMANCE_MARKER
    normalized["real_time_factor"] = _PERFORMANCE_MARKER
    _normalize_treatment_surface(normalized, "normalized summary")
    final = normalized.get("module_final_diagnostics")
    if not isinstance(final, dict):
        raise D1ReplayPrefixSummaryEvidenceError(
            "normalized summary lacks module_final_diagnostics"
        )
    _normalize_treatment_surface(final, "normalized module final")
    if "stage_timings" not in final:
        raise D1ReplayPrefixSummaryEvidenceError(
            "normalized module final lacks stage_timings"
        )
    final["stage_timings"] = _PERFORMANCE_MARKER
    nested = final.get("observation_governance")
    if not isinstance(nested, Mapping):
        raise D1ReplayPrefixSummaryEvidenceError(
            "normalized summary lacks nested observation governance"
        )
    final["observation_governance"] = _normalized_governance(nested)
    return normalized


def _normalized_governance(
    governance: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(governance))
    _normalize_treatment_surface(normalized, "normalized governance")
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
            raise D1ReplayPrefixSummaryEvidenceError(
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
        raise D1ReplayPrefixSummaryEvidenceError(
            "cross-build reader returned unsupported schema"
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
            and all(value is True for value in required_cross_checks.values())
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "treatment_normalization": {
            "scope": (
                "registered_selector_execution_config_diagnostics_"
                "episode_identity_and_performance_only"
            ),
            "diagnostics_validated_separately": True,
            "assignment_business_content_ignored": False,
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
        "replay_prefix_summary_audit_pass_count": sum(
            bool(pair["replay_prefix_summary_audit_passed"])
            for pair in ordered
        ),
        "consistency_digest_equal_count": sum(
            bool(pair["consistency_evidence_records_digest_equal"])
            for pair in ordered
        ),
        "existing_operation_counts_equal_count": sum(
            bool(pair["existing_operation_counts_equal"])
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


def _aggregate_replay_diagnostics(
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    for group in (*_GROUPS, "all"):
        selected = (
            list(pairs)
            if group == "all"
            else [pair for pair in pairs if pair["group"] == group]
        )
        logical = sum(
            int(
                pair["replay_prefix_summary_audit"][
                    "candidate_logical_refresh_record_count"
                ]
            )
            for pair in selected
        )
        materialized = sum(
            int(
                pair["replay_prefix_summary_audit"][
                    "candidate_actual_materialized_record_count"
                ]
            )
            for pair in selected
        )
        projected = sum(
            int(
                pair["replay_prefix_summary_audit"][
                    "candidate_online_snapshot_projected_record_count"
                ]
            )
            for pair in selected
        )
        groups[group] = {
            "pair_count": len(selected),
            "candidate_logical_refresh_record_count": logical,
            "candidate_actual_materialized_record_count": materialized,
            "candidate_lazy_materialization_reduction_pct": (
                (logical - materialized) / logical * 100.0
                if logical > 0
                else 0.0
            ),
            "candidate_online_snapshot_projected_record_count": projected,
            "candidate_disclosed_record_construction_count": (
                materialized + projected
            ),
            "projection_is_disclosed_separately": True,
            "projection_count_is_not_treated_as_eliminated_work": True,
        }
    return {
        "schema_version": (
            "d6.d1_replay_prefix_summary_diagnostics_aggregate.v1"
        ),
        "groups": groups,
    }


def _admission_gates(
    pairs: Sequence[Mapping[str, Any]],
    groups: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
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
        bool(pair["implementation_identity_passed"]) for pair in pairs
    )
    audit_count = sum(
        bool(pair["replay_prefix_summary_audit_passed"])
        for pair in pairs
    )
    digest_count = sum(
        bool(pair["consistency_evidence_records_digest_equal"])
        for pair in pairs
    )
    operation_count = sum(
        bool(pair["existing_operation_counts_equal"]) for pair in pairs
    )
    short_bootstrap_upper = (
        short_d1["raw_relative_change"]["bootstrap_95_ci"]["upper"]
        * 100.0
    )
    rss_mean_increase = max(
        item["raw_relative_change"]["mean"] * 100.0
        for item in rss_groups
    )
    any_pair_rss_increase = max(
        float(
            pair["performance"]["maximum_rss_kib"][
                "raw_relative_change_pct"
            ]
        )
        for pair in pairs
    )
    lazy_reduction = float(
        diagnostics["groups"]["all"][
            "candidate_lazy_materialization_reduction_pct"
        ]
    )
    definitions = {
        "all_pairs_business_semantics_equal": (
            semantic_count,
            pair_count,
            "==",
            semantic_count == pair_count,
            "one_or_more_pair_business_semantics_mismatch",
        ),
        "all_pairs_finite_state": (
            finite_count,
            pair_count,
            "==",
            finite_count == pair_count,
            "one_or_more_pair_finite_state_failed",
        ),
        "all_pairs_online_truth_use_count": (
            truth_use_count,
            thresholds["all_pairs_online_truth_use_count"],
            "==",
            truth_use_count
            == thresholds["all_pairs_online_truth_use_count"],
            "one_or_more_arm_online_truth_use_nonzero",
        ),
        "all_pairs_explicit_implementation_identity": (
            identity_count,
            pair_count,
            "==",
            identity_count == pair_count,
            "one_or_more_pair_implementation_identity_failed",
        ),
        "all_pairs_replay_prefix_summary_audit_valid": (
            audit_count,
            pair_count,
            "==",
            audit_count == pair_count,
            "one_or_more_pair_replay_prefix_summary_audit_failed",
        ),
        "all_pairs_consistency_evidence_records_digest_equal": (
            digest_count,
            pair_count,
            "==",
            digest_count == pair_count,
            "one_or_more_pair_consistency_digest_mismatch",
        ),
        "all_pairs_existing_operation_counts_equal": (
            operation_count,
            pair_count,
            "==",
            operation_count == pair_count,
            "one_or_more_pair_existing_operation_counts_mismatch",
        ),
        "short_minimum_candidate_faster_count": (
            short_d1["candidate_better_count"],
            thresholds["short_minimum_candidate_faster_count"],
            ">=",
            short_d1["candidate_better_count"]
            >= thresholds["short_minimum_candidate_faster_count"],
            "short_candidate_faster_count_below_threshold",
        ),
        "short_minimum_d1_fusion_improvement_pct": (
            short_d1["improvement_pct"]["mean"],
            thresholds["short_minimum_d1_fusion_improvement_pct"],
            ">=",
            short_d1["improvement_pct"]["mean"]
            >= thresholds["short_minimum_d1_fusion_improvement_pct"],
            "short_d1_fusion_improvement_below_threshold",
        ),
        "short_bootstrap_relative_change_upper_bound_pct": (
            short_bootstrap_upper,
            thresholds[
                "short_bootstrap_relative_change_upper_bound_pct"
            ],
            "<=",
            short_bootstrap_upper
            <= thresholds[
                "short_bootstrap_relative_change_upper_bound_pct"
            ],
            "short_bootstrap_upper_bound_above_threshold",
        ),
        "long_minimum_candidate_faster_count": (
            long_d1["candidate_better_count"],
            thresholds["long_minimum_candidate_faster_count"],
            ">=",
            long_d1["candidate_better_count"]
            >= thresholds["long_minimum_candidate_faster_count"],
            "long_candidate_faster_count_below_threshold",
        ),
        "long_minimum_d1_fusion_improvement_pct": (
            long_d1["improvement_pct"]["mean"],
            thresholds["long_minimum_d1_fusion_improvement_pct"],
            ">=",
            long_d1["improvement_pct"]["mean"]
            >= thresholds["long_minimum_d1_fusion_improvement_pct"],
            "long_d1_fusion_improvement_below_threshold",
        ),
        "short_minimum_core_wall_improvement_pct": (
            short_core["improvement_pct"]["mean"],
            thresholds["short_minimum_core_wall_improvement_pct"],
            ">=",
            short_core["improvement_pct"]["mean"]
            >= thresholds["short_minimum_core_wall_improvement_pct"],
            "short_core_wall_improvement_below_threshold",
        ),
        "long_minimum_core_wall_improvement_pct": (
            long_core["improvement_pct"]["mean"],
            thresholds["long_minimum_core_wall_improvement_pct"],
            ">=",
            long_core["improvement_pct"]["mean"]
            >= thresholds["long_minimum_core_wall_improvement_pct"],
            "long_core_wall_improvement_below_threshold",
        ),
        "maximum_short_d1_scan_input_mean_increase_pct": (
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
        ),
        "maximum_long_d1_scan_input_mean_increase_pct": (
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
        ),
        "maximum_short_d2_association_mean_increase_pct": (
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
        ),
        "maximum_long_d2_association_mean_increase_pct": (
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
        ),
        "maximum_rss_mean_increase_pct": (
            rss_mean_increase,
            thresholds["maximum_rss_mean_increase_pct"],
            "<=",
            rss_mean_increase
            <= thresholds["maximum_rss_mean_increase_pct"],
            "short_or_long_rss_mean_increase_above_threshold",
        ),
        "maximum_any_pair_rss_increase_pct": (
            any_pair_rss_increase,
            thresholds["maximum_any_pair_rss_increase_pct"],
            "<=",
            any_pair_rss_increase
            <= thresholds["maximum_any_pair_rss_increase_pct"],
            "one_or_more_pair_rss_increase_above_threshold",
        ),
        "minimum_candidate_lazy_materialization_reduction_pct": (
            lazy_reduction,
            thresholds[
                "minimum_candidate_lazy_materialization_reduction_pct"
            ],
            ">=",
            lazy_reduction
            >= thresholds[
                "minimum_candidate_lazy_materialization_reduction_pct"
            ],
            "candidate_lazy_materialization_reduction_below_threshold",
        ),
    }
    percentage_gates = {
        name
        for name in definitions
        if name.endswith("_pct")
    }
    return {
        name: _gate(
            actual=values[0],
            threshold=values[1],
            comparator=values[2],
            passed=bool(values[3]),
            reason=str(values[4]),
            unit="pct" if name in percentage_gates else None,
        )
        for name, values in definitions.items()
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


def write_d1_replay_prefix_summary_multiseed_report(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write deterministic D6 products outside the raw evidence root."""

    if result.get("schema_version") != (
        D1_REPLAY_PREFIX_SUMMARY_MULTISEED_EVALUATION_SCHEMA_VERSION
    ):
        raise ValueError("unsupported replay-prefix evaluation schema")
    contract = _required_mapping(
        result.get("input_contract"), "report input contract"
    )
    directory = Path(output_dir).expanduser().resolve()
    if "output_root" in contract:
        evidence_root = Path(str(contract["output_root"])).resolve()
        if _base._path_is_within(directory, evidence_root):
            raise ValueError(
                "independent D6 output must be outside raw evidence root"
            )
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "evaluation_json": directory
        / "d1_replay_prefix_summary_multiseed_evaluation.json",
        "compact_json": directory
        / "d1_replay_prefix_summary_multiseed_compact.json",
        "pairs_csv": directory
        / "d1_replay_prefix_summary_multiseed_pairs.csv",
        "markdown": directory
        / "D1_REPLAY_PREFIX_SUMMARY_MULTISEED_REPORT_CN.md",
        "plot_png": directory
        / "d1_replay_prefix_summary_multiseed_curves.png",
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
        render_d1_replay_prefix_summary_multiseed_markdown(result),
        encoding="utf-8",
    )
    if result["availability"]["available"] is True:
        _write_plot(result, paths["plot_png"])
    else:
        paths.pop("plot_png")
    checksums = [
        f"{_base._file_sha256(paths[name])}  {paths[name].name}"
        for name in sorted(paths)
        if name != "sha256sums"
    ]
    paths["sha256sums"].write_text(
        "\n".join(sorted(checksums)) + "\n", encoding="utf-8"
    )
    return paths


def _compact_output(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": (
            D1_REPLAY_PREFIX_SUMMARY_MULTISEED_COMPACT_SCHEMA_VERSION
        ),
        "evaluation_schema_version": result["schema_version"],
        "evaluation_date": result["evaluation_date"],
        "availability": result["availability"],
        "input_contract": result["input_contract"],
        "scope": result["scope"],
        "groups": result["groups"],
        "replay_prefix_summary_diagnostics_aggregate": result[
            "replay_prefix_summary_diagnostics_aggregate"
        ],
        "admission_gates": result["admission_gates"],
        "admission_blockers": result["admission_blockers"],
        "optimization_admitted": result["optimization_admitted"],
        "verdict": result["verdict"],
        "main_default_promotion_allowed": result[
            "main_default_promotion_allowed"
        ],
        "system_realtime_gate": result["system_realtime_gate"],
        "system_realtime_gap_closed": result[
            "system_realtime_gap_closed"
        ],
        "evidence_boundary_statement": result.get(
            "evidence_boundary_statement"
        ),
    }


def render_d1_replay_prefix_summary_multiseed_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the formal Chinese admission report."""

    availability = _required_mapping(
        result.get("availability"), "report availability"
    )
    if availability.get("available") is not True:
        return "\n".join(
            [
                "# D1 回放前缀摘要多种子正式评估",
                "",
                "## 结论",
                "",
                "证据不可用，D6 失败关闭。候选结论为 `reject`，不允许进入默认路径。",
                f"原因：`{availability.get('reason')}`。",
                "",
            ]
        )
    contract = result["input_contract"]
    groups = result["groups"]
    gates = result["admission_gates"]
    aggregate = result[
        "replay_prefix_summary_diagnostics_aggregate"
    ]["groups"]["all"]
    failed = [name for name, gate in gates.items() if not gate["passed"]]
    lines = [
        "# D1 回放前缀摘要同提交多种子正式评估",
        "",
        "## 结论",
        "",
        f"候选准入结论为 **{result['verdict']}**。"
        + (
            "全部预注册门限通过。"
            if not failed
            else "失败门限：" + "、".join(f"`{x}`" for x in failed) + "。"
        ),
        (
            "候选最低实时因子为 "
            f"`{_fmt(result['system_realtime_gate']['candidate_minimum_real_time_factor'])}`；"
            "候选准入不等于系统达到实时运行要求。"
        ),
        "本结论只覆盖冻结的三维质点 200 对 200 矩阵，不包含 AirSim、硬件、实机或实飞证据。",
        "D1 模块微基准和 clean seed-1151 预检未写入本次正式结论。",
        "",
        "## 证据",
        "",
        f"- producer clean commit：`{contract['source_commit']}`。",
        f"- matrix SHA-256：`{contract['matrix_sha256']}`。",
        "- short 10 对、long 3 对，共 13 对和 26 个全新 episode；复用 0、失败 0。",
        "- 每对只有回放前缀摘要 selector 不同，在线真值使用次数为 0。",
        "",
        "## 语义审计",
        "",
        "D6 对每对 episode 独立比较业务输出、在线消息、离线真值、任务计划谱系和安全结果。"
        "两臂 `offline_consistency/online_evidence.json` 的记录数量与记录摘要必须完全一致。"
        "`module_final_diagnostics.d1_fusion_performance` 的原有操作计数也必须完全一致。",
        "",
        "候选诊断分别检查导出前 module-final 和导出后 summary。"
        "导出后 pending ledger 必须为 0，正常追加和不兼容追加不得触发物化。"
        "摘要命中、checkpoint 复用、revision 推进、pending 保留和在线快照投影均需实际出现。",
        "",
        "## 工作量",
        "",
        "| 项目 | 数量 |",
        "|---|---:|",
        f"| 逻辑刷新记录 | {aggregate['candidate_logical_refresh_record_count']} |",
        f"| 实际内部物化记录 | {aggregate['candidate_actual_materialized_record_count']} |",
        f"| 内部物化减少率 | {_fmt(aggregate['candidate_lazy_materialization_reduction_pct'])}% |",
        f"| 在线快照投影构造记录 | {aggregate['candidate_online_snapshot_projected_record_count']} |",
        f"| 已披露记录构造总量 | {aggregate['candidate_disclosed_record_construction_count']} |",
        "",
        "内部物化减少率只用于预注册压缩门。在线快照仍会构造不可变返回记录，"
        "该工作量单独列示，没有计为已经消失的成本。",
        "",
        "## 性能",
        "",
        "| 分组 | 指标 | 参考均值 | 候选均值 | 改善或增幅 | 候选更快 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for group in _GROUPS:
        label = "短时" if group == "short" else "长时"
        for metric, metric_label, raw in (
            ("d1_fusion_wall_s", "D1 融合耗时", False),
            ("core_wall_s", "核心流程耗时", False),
            ("d1_scan_input_wall_s", "D1 扫描输入增幅", True),
            ("d2_association_wall_s", "D2 关联增幅", True),
            ("maximum_rss_kib", "最大驻留内存增幅", True),
        ):
            item = groups[group]["metrics"][metric]
            change = (
                item["raw_relative_change"]["mean"] * 100.0
                if raw
                else item["improvement_pct"]["mean"]
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
            "## 门限",
            "",
            "| 门限 | 实测 | 判据 | 结果 |",
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
            "## 证据边界",
            "",
            "评估器不会因模块微基准结果直接准入候选。"
            "任何 matrix SHA、producer commit、schema、路径、arm 状态、"
            "实现标识、双臂唯一 treatment、时间与规模参数不一致都会失败关闭。",
            "",
            "输出包括完整 JSON、紧凑 JSON、逐对 CSV、性能曲线、中文报告和制品校验值。",
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
        "consistency_evidence_records_digest_equal",
        "existing_operation_counts_equal",
        "replay_prefix_summary_audit_passed",
        "candidate_logical_refresh_record_count",
        "candidate_actual_materialized_record_count",
        "candidate_lazy_materialization_reduction_pct",
        "candidate_online_snapshot_projected_record_count",
        "candidate_disclosed_record_construction_count",
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
            audit = pair["replay_prefix_summary_audit"]
            row: dict[str, Any] = {
                name: pair[name]
                for name in (
                    "case_id",
                    "group",
                    "seed",
                    "duration_s",
                    "business_semantics_passed",
                    "finite_state_passed",
                    "truth_isolation_passed",
                    "implementation_identity_passed",
                    "consistency_evidence_records_digest_equal",
                    "existing_operation_counts_equal",
                    "replay_prefix_summary_audit_passed",
                )
            }
            for name in (
                "candidate_logical_refresh_record_count",
                "candidate_actual_materialized_record_count",
                "candidate_lazy_materialization_reduction_pct",
                "candidate_online_snapshot_projected_record_count",
                "candidate_disclosed_record_construction_count",
            ):
                row[name] = audit[name]
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
        3, 1, figsize=(11.5, 9.0), sharex=True
    )
    axes[0].plot(
        x,
        [
            pair["performance"]["d1_fusion_wall_s"]["improvement_pct"]
            for pair in pairs
        ],
        marker="o",
        label="D1 fusion improvement",
    )
    axes[0].plot(
        x,
        [
            pair["performance"]["core_wall_s"]["improvement_pct"]
            for pair in pairs
        ],
        marker="s",
        label="Core wall improvement",
    )
    axes[0].axhline(0.0, color="#444444", linewidth=0.8)
    axes[0].set_ylabel("Improvement (%)")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(fontsize=8)

    axes[1].plot(
        x,
        [
            pair["replay_prefix_summary_audit"][
                "candidate_lazy_materialization_reduction_pct"
            ]
            for pair in pairs
        ],
        marker="o",
        label="Internal materialization reduction",
        color="#2ca02c",
    )
    axes[1].axhline(
        20.0,
        color="#d62728",
        linestyle="--",
        linewidth=1.0,
        label="Admission threshold",
    )
    axes[1].set_ylabel("Reduction (%)")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(fontsize=8)

    axes[2].plot(
        x,
        [
            pair["candidate"]["metrics"]["real_time_factor"]
            for pair in pairs
        ],
        marker="o",
        color="#9467bd",
        label="Candidate real-time factor",
    )
    axes[2].axhline(
        1.0,
        color="#d62728",
        linestyle="--",
        linewidth=1.0,
        label="System threshold",
    )
    axes[2].set_ylabel("Real-time factor")
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(labels, fontsize=8)
    axes[2].set_xlabel("Preregistered pair")
    axes[2].grid(True, alpha=0.25)
    axes[2].legend(fontsize=8)
    fig.suptitle("D1 replay-prefix summary paired admission")
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
        "--d1-replay-prefix-summary-implementation",
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
        str(episode_dir.resolve()),
    ]


def _validate_pair_command_isolation(
    commands: Mapping[str, Sequence[str]], case_id: str
) -> None:
    normalized: dict[str, list[str]] = {}
    for arm in _ARMS:
        command = list(commands[arm])
        selector_index = command.index(
            "--d1-replay-prefix-summary-implementation"
        )
        output_index = command.index("--output")
        command[selector_index + 1] = _TREATMENT_MARKER
        command[output_index + 1] = "D6_ARM_OUTPUT_PATH"
        normalized[arm] = command
    if normalized[_REFERENCE_ARM] != normalized[_CANDIDATE_ARM]:
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{case_id} arms differ beyond selector and output path"
        )


def _case_metadata(
    value: Any,
) -> tuple[str, str, int, float, tuple[str, str]]:
    case = _required_mapping(value, "case")
    case_id = _required_text(case.get("case_id"), "case_id")
    group = _required_text(case.get("group"), f"{case_id} group")
    seed = _nonnegative_integer(case.get("seed"), f"{case_id} seed")
    duration = _finite_nonnegative(
        case.get("duration_s"), f"{case_id} duration_s", positive=True
    )
    arm_order = tuple(
        _required_text(item, f"{case_id} arm_order item")
        for item in _required_sequence(
            case.get("arm_order"), f"{case_id} arm_order"
        )
    )
    if len(arm_order) != 2 or set(arm_order) != set(_ARMS):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{case_id} arm_order must contain reference and candidate"
        )
    return case_id, group, seed, duration, arm_order


def _strict_jsonl_count(path: Path) -> int:
    try:
        _base._strict_jsonl_digest(path)
        with path.open("r", encoding="utf-8") as stream:
            return sum(1 for line in stream if line.strip())
    except (
        _base.D1PublicationMetadataEvidenceError,
        OSError,
        ValueError,
    ) as exc:
        raise D1ReplayPrefixSummaryEvidenceError(str(exc)) from exc


def _load_stage(path: Path, stage_name: str) -> dict[str, Any]:
    try:
        return _base._load_stage(path, stage_name)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1ReplayPrefixSummaryEvidenceError(str(exc)) from exc


def _load_resource_metrics(path: Path) -> dict[str, float | int]:
    try:
        return _base._load_resource_metrics(path)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1ReplayPrefixSummaryEvidenceError(str(exc)) from exc


def _validate_stderr(path: Path, context: str) -> dict[str, Any]:
    try:
        return _base._validate_stderr(path, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1ReplayPrefixSummaryEvidenceError(str(exc)) from exc


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
        raise D1ReplayPrefixSummaryEvidenceError(str(exc)) from exc


def _load_mapping(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        return _base._load_strict_json_mapping(path)
    except (
        _base.D1PublicationMetadataEvidenceError,
        OSError,
        ValueError,
    ) as exc:
        raise D1ReplayPrefixSummaryEvidenceError(str(exc)) from exc


def _required_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} must be a mapping"
        )
    return value


def _required_sequence(value: Any, context: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} must be a sequence"
        )
    return value


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} must be non-empty text"
        )
    return value


def _required_commit(value: Any, context: str) -> str:
    try:
        return _base._required_commit(value, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1ReplayPrefixSummaryEvidenceError(str(exc)) from exc


def _required_sha256(value: Any, context: str) -> str:
    try:
        return _base._required_sha256(value, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1ReplayPrefixSummaryEvidenceError(str(exc)) from exc


def _required_prefixed_sha256(value: Any, context: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_PREFIXED_LENGTH
        or not value.startswith("sha256:")
        or any(
            character not in "0123456789abcdef"
            for character in value[len("sha256:") :]
        )
    ):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} must be a sha256: digest"
        )
    return value


def _explicit_path(
    value: Any,
    context: str,
    *,
    require: str | None,
) -> Path:
    try:
        return _base._explicit_path(value, context, require=require)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1ReplayPrefixSummaryEvidenceError(str(exc)) from exc


def _require_under_root(path: Path, root: Path, context: str) -> None:
    try:
        _base._require_under_root(path, root, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise D1ReplayPrefixSummaryEvidenceError(str(exc)) from exc


def _expect(actual: Any, expected: Any, context: str) -> None:
    if actual != expected:
        raise D1ReplayPrefixSummaryEvidenceError(
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
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} mismatch: expected {expected!r}, got {actual!r}"
        )


def _nonnegative_integer(value: Any, context: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise D1ReplayPrefixSummaryEvidenceError(
            f"{context} must be a nonnegative integer"
        )
    return int(value)


def _validated_count_mapping(value: Any, context: str) -> dict[str, int]:
    mapping = _required_mapping(value, context)
    return {
        str(field): _nonnegative_integer(count, f"{context} {field}")
        for field, count in mapping.items()
    }


def _payload_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


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


def parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the frozen D1 replay-prefix summary 13-pair matrix"
        )
    )
    parser.add_argument(
        "--evidence-manifest",
        required=True,
        help="completed replay-prefix evidence_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="independent D6 output directory",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = evaluate_d1_replay_prefix_summary_multiseed(
        args.evidence_manifest
    )
    paths = write_d1_replay_prefix_summary_multiseed_report(
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
    "D1_REPLAY_PREFIX_SUMMARY_DIAGNOSTICS_SCHEMA_VERSION",
    "D1_REPLAY_PREFIX_SUMMARY_EVALUATION_DATE",
    "D1_REPLAY_PREFIX_SUMMARY_EVIDENCE_SCHEMA_VERSION",
    "D1_REPLAY_PREFIX_SUMMARY_EXECUTION_CONFIG_SCHEMA_VERSION",
    "D1_REPLAY_PREFIX_SUMMARY_EXPERIMENT_ID",
    "D1_REPLAY_PREFIX_SUMMARY_MATRIX_SCHEMA_VERSION",
    "D1_REPLAY_PREFIX_SUMMARY_MATRIX_SHA256",
    "D1_REPLAY_PREFIX_SUMMARY_MULTISEED_COMPACT_SCHEMA_VERSION",
    "D1_REPLAY_PREFIX_SUMMARY_MULTISEED_EVALUATION_SCHEMA_VERSION",
    "D1_REPLAY_PREFIX_SUMMARY_SOURCE_COMMIT",
    "D1ReplayPrefixSummaryEvidence",
    "D1ReplayPrefixSummaryEvidenceError",
    "REFERENCE_IMPLEMENTATION",
    "REFERENCE_IMPLEMENTATION_ID",
    "evaluate_d1_replay_prefix_summary_multiseed",
    "load_d1_replay_prefix_summary_evidence_manifest",
    "main",
    "render_d1_replay_prefix_summary_multiseed_markdown",
    "write_d1_replay_prefix_summary_multiseed_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
