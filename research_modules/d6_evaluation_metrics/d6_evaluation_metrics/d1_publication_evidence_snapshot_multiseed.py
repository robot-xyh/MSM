"""Independent D6 admission for D1 publication-evidence subset snapshots.

The producer owns raw episode generation.  This module is a read-only,
fail-closed consumer of the frozen same-clean-commit 13-pair matrix.  It
validates provenance, command isolation, four published configuration and
diagnostic surfaces, online business semantics, exact consistency evidence,
existing D1 operation counts, resource measurements, and preregistered gates.
It never mutates producer evidence and never participates in online control.
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


D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_EVALUATION_SCHEMA_VERSION = (
    "d6.d1_publication_evidence_snapshot_multiseed_evaluation.v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_COMPACT_SCHEMA_VERSION = (
    "d6.d1_publication_evidence_snapshot_multiseed_compact.v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-publication-evidence-snapshot-multiseed-matrix-v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_EVIDENCE_SCHEMA_VERSION = (
    "scalable3d-d1-publication-evidence-snapshot-multiseed-evidence-v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXECUTION_CONFIG_SCHEMA_VERSION = (
    "scalable3d-d1-publication-evidence-snapshot-execution-config-v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_DIAGNOSTICS_SCHEMA_VERSION = (
    "scalable3d-d1-publication-evidence-snapshot-diagnostics-v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXPERIMENT_ID = (
    "d1-publication-evidence-snapshot-multiseed-20260725-v1"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SHA256 = (
    "6c808c4df8759fd893c6d37ff9dce4a1efa07f9867fc71aff47a55c5f8517338"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_SOURCE_COMMIT = (
    "d0219eb14c529a4fb9bf7d6610a9f32055a09206"
)
D1_PUBLICATION_EVIDENCE_SNAPSHOT_EVALUATION_DATE = "2026-07-25"

REFERENCE_IMPLEMENTATION = "full_consistency_snapshot_v1"
CANDIDATE_IMPLEMENTATION = "required_observation_subset_v1"
REFERENCE_IMPLEMENTATION_ID = (
    "main.d1_publication_evidence.full_consistency_snapshot.v1"
)
CANDIDATE_IMPLEMENTATION_ID = (
    "main.d1_publication_evidence.required_observation_subset.v1"
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
_VALIDATION_KIND = "publication_evidence_snapshot"
_SELECTOR_FIELD = "d1_publication_evidence_snapshot_implementation"
_EXECUTION_CONFIG_FIELD = (
    "d1_publication_evidence_snapshot_execution_config"
)
_DIAGNOSTICS_FIELD = "d1_publication_evidence_snapshot_diagnostics"
_REPLAY_SELECTOR_FIELD = "d1_replay_prefix_summary_implementation"
_REPLAY_REFERENCE = "per_checkpoint_prefix_rebuild_v1"
_TREATMENT_MARKER = "D6_REGISTERED_PUBLICATION_EVIDENCE_TREATMENT"
_DIAGNOSTICS_MARKER = "D6_REGISTERED_PUBLICATION_EVIDENCE_DIAGNOSTICS"
_PERFORMANCE_MARKER = "D6_REGISTERED_PERFORMANCE_DIAGNOSTIC"
_TREATMENT_DERIVED_ID_MARKER = "D6_TREATMENT_DERIVED_EPISODE_ID"

_EXPECTED_GATES = {
    "all_pairs_business_semantics_equal": True,
    "all_pairs_finite_state": True,
    "all_pairs_online_truth_use_count": 0,
    "all_pairs_explicit_implementation_identity": True,
    "all_pairs_publication_evidence_snapshot_audit_valid": True,
    "all_pairs_consistency_evidence_records_digest_equal": True,
    "all_pairs_existing_operation_counts_equal": True,
    "short_minimum_candidate_faster_count": 8,
    "short_minimum_d1_fusion_improvement_pct": 1.0,
    "short_bootstrap_relative_change_upper_bound_pct": 0.0,
    "long_minimum_candidate_faster_count": 2,
    "long_minimum_d1_fusion_improvement_pct": 1.0,
    "short_minimum_core_wall_improvement_pct": 0.25,
    "long_minimum_core_wall_improvement_pct": 0.25,
    "maximum_short_d2_association_mean_increase_pct": 5.0,
    "maximum_long_d2_association_mean_increase_pct": 5.0,
    "maximum_rss_mean_increase_pct": 5.0,
    "maximum_any_pair_rss_increase_pct": 5.0,
    "minimum_candidate_returned_record_reduction_pct": 50.0,
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
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXECUTION_CONFIG_SCHEMA_VERSION
    ),
    "diagnostics_schema_version": (
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_DIAGNOSTICS_SCHEMA_VERSION
    ),
    "candidate_default_off": True,
    "required_id_sources": [
        "source_observations",
        "materialized_track_latest_observation",
    ],
    "required_id_order": "deduplicated_lexicographic",
    "invalid_or_unknown_id_policy": "fallback_to_full_snapshot",
    "episode_final_export_scope": "full_exact_materialized_records",
    "same_release_cycle_required_ids": True,
    "published_payload_semantics_changed": False,
    "consistency_evidence_semantics_changed": False,
    "replay_prefix_selector_changed": False,
    "replay_prefix_implementation": _REPLAY_REFERENCE,
    "truth_dependent_inputs_forbidden": True,
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
    "publication_evidence_snapshot_execution_config_schema_version",
    "publication_evidence_snapshot_diagnostics_schema_version",
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
    "implementation_id",
    "candidate_enabled",
    "required_id_sources",
    "required_id_order",
    "invalid_or_unknown_id_policy",
    "episode_final_export_scope",
    "truth_dependent_inputs_allowed",
}
_EXPECTED_DIAGNOSTICS_KEYS = {
    "schema_version",
    "execution_config",
    "operation_counts",
    "fallback_reason_counts",
    "conservation",
}
_EXPECTED_CONSERVATION_KEYS = {
    "selection_partition",
    "candidate_selection_partition",
    "adapter_call_partition",
    "reference_deduplication_partition",
    "fallback_not_above_candidate_selection",
    "all_required_records_available",
}
_OPERATION_COUNT_FIELDS = {
    "selection_count",
    "reference_selection_count",
    "candidate_selection_count",
    "candidate_subset_success_count",
    "candidate_fallback_count",
    "adapter_snapshot_call_count",
    "full_snapshot_call_count",
    "subset_snapshot_call_count",
    "publication_count",
    "source_observation_reference_count",
    "track_latest_observation_reference_count",
    "required_observation_id_count",
    "duplicate_reference_count",
    "invalid_required_id_count",
    "empty_required_id_selection_count",
    "returned_record_count",
    "lookup_miss_count",
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
    "offline_identity/online_d1_records.jsonl",
    "offline_identity/online_d2_records.jsonl",
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


class D1PublicationEvidenceSnapshotEvidenceError(ValueError):
    """Raised when producer evidence violates the frozen D6 contract."""


@dataclass(frozen=True)
class D1PublicationEvidenceSnapshotArmBinding:
    arm: str
    implementation: str
    episode_dir: Path
    resource_path: Path
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True)
class D1PublicationEvidenceSnapshotPairBinding:
    case_id: str
    group: str
    seed: int
    duration_s: float
    arm_order: tuple[str, str]
    arms: Mapping[str, D1PublicationEvidenceSnapshotArmBinding]


@dataclass(frozen=True)
class D1PublicationEvidenceSnapshotEvidence:
    source_path: Path
    source_sha256: str
    matrix_path: Path
    matrix_sha256: str
    matrix: Mapping[str, Any]
    output_root: Path
    source_commit: str
    source_worktree: Path
    pairs: tuple[D1PublicationEvidenceSnapshotPairBinding, ...]


def load_d1_publication_evidence_snapshot_evidence_manifest(
    source: str | Path,
) -> D1PublicationEvidenceSnapshotEvidence:
    """Bind one complete, fresh, frozen 13-pair producer manifest."""

    source_path = Path(source).expanduser().resolve()
    manifest, manifest_raw = _load_mapping(source_path)
    if set(manifest) != _EXPECTED_MANIFEST_KEYS:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "evidence manifest fields differ from the frozen contract"
        )
    _expect(
        manifest.get("schema_version"),
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_EVIDENCE_SCHEMA_VERSION,
        "evidence schema_version",
    )
    _expect(
        manifest.get("experiment_id"),
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXPERIMENT_ID,
        "evidence experiment_id",
    )
    _expect(
        manifest.get("required_d6_evaluator_schema_version"),
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_EVALUATION_SCHEMA_VERSION,
        "required D6 evaluator schema",
    )
    _expect(
        manifest.get(
            "publication_evidence_snapshot_execution_config_schema_version"
        ),
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXECUTION_CONFIG_SCHEMA_VERSION,
        "execution config schema",
    )
    _expect(
        manifest.get(
            "publication_evidence_snapshot_diagnostics_schema_version"
        ),
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_DIAGNOSTICS_SCHEMA_VERSION,
        "diagnostics schema",
    )
    if manifest.get("status") != "episodes_complete_pending_d6":
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "evidence status must be episodes_complete_pending_d6"
        )
    _required_text(manifest.get("started_at_utc"), "started_at_utc")
    _required_text(manifest.get("completed_at_utc"), "completed_at_utc")
    source_commit = _required_commit(
        manifest.get("source_commit"), "source_commit"
    )
    _expect(
        source_commit,
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_SOURCE_COMMIT,
        "frozen producer source_commit",
    )
    if manifest.get("source_repository_dirty") is not False:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "source_repository_dirty must be false"
        )
    source_worktree = _explicit_path(
        manifest.get("source_worktree"),
        "source_worktree",
        require="directory",
    )
    entrypoint = (
        source_worktree
        / "research_modules"
        / "scalable_3d_simulation"
        / "run_episode.py"
    )
    if not entrypoint.is_file():
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "source worktree run_episode.py is unavailable"
        )
    output_root = _explicit_path(
        manifest.get("output_root"), "output_root", require="directory"
    )
    if source_path.parent != output_root:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "evidence_manifest.json must be directly under output_root"
        )
    matrix_path = _explicit_path(
        manifest.get("matrix_path"), "matrix_path", require="file"
    )
    matrix_sha256 = _required_sha256(
        manifest.get("matrix_sha256"), "matrix_sha256"
    )
    if _base._file_sha256(matrix_path) != matrix_sha256:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "matrix_sha256 does not match matrix_path bytes"
        )
    _expect(
        matrix_sha256,
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SHA256,
        "frozen matrix_sha256",
    )
    matrix, _ = _load_mapping(matrix_path)
    _validate_matrix(matrix)
    embedded_matrix = _required_mapping(
        manifest.get("matrix"), "embedded matrix"
    )
    if embedded_matrix != matrix:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "embedded matrix does not exactly match matrix_path"
        )

    raw_cases = _required_sequence(manifest.get("cases"), "evidence cases")
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "evidence manifest must contain exactly 13 cases"
        )
    used_paths: set[Path] = {source_path}
    pairs: list[D1PublicationEvidenceSnapshotPairBinding] = []
    for raw_case, expected_case in zip(
        raw_cases, _EXPECTED_CASES, strict=True
    ):
        case = _required_mapping(raw_case, "evidence case")
        if set(case) != _EXPECTED_CASE_KEYS:
            raise D1PublicationEvidenceSnapshotEvidenceError(
                "evidence case fields differ from the frozen contract"
            )
        metadata = _case_metadata(case)
        if metadata != expected_case:
            raise D1PublicationEvidenceSnapshotEvidenceError(
                "evidence case differs from the frozen matrix"
            )
        case_id, group, seed, duration_s, arm_order = metadata
        if (
            case.get("d6_evaluation_status")
            != "episodes_complete_pending_d6"
        ):
            raise D1PublicationEvidenceSnapshotEvidenceError(
                f"{case_id} is not pending D6 evaluation"
            )
        raw_arms = _required_mapping(case.get("arms"), f"{case_id} arms")
        if set(raw_arms) != set(_ARMS):
            raise D1PublicationEvidenceSnapshotEvidenceError(
                f"{case_id} arms must be reference and candidate"
            )
        bindings: dict[
            str, D1PublicationEvidenceSnapshotArmBinding
        ] = {}
        commands: dict[str, list[str]] = {}
        for arm in _ARMS:
            record = _required_mapping(
                raw_arms.get(arm), f"{case_id} {arm} arm"
            )
            if set(record) != _EXPECTED_ARM_KEYS:
                raise D1PublicationEvidenceSnapshotEvidenceError(
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
                raise D1PublicationEvidenceSnapshotEvidenceError(
                    f"{case_id} {arm} must be fresh complete, not reused/failed"
                )
            return_code = record.get("return_code")
            if (
                isinstance(return_code, bool)
                or not isinstance(return_code, int)
                or return_code != 0
            ):
                raise D1PublicationEvidenceSnapshotEvidenceError(
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
                    raise D1PublicationEvidenceSnapshotEvidenceError(
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
                raise D1PublicationEvidenceSnapshotEvidenceError(
                    f"{case_id} {arm} command differs from frozen execution"
                )
            commands[arm] = command
            bindings[arm] = D1PublicationEvidenceSnapshotArmBinding(
                arm=arm,
                implementation=implementation,
                episode_dir=episode_dir,
                resource_path=resource_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        _validate_pair_command_isolation(commands, case_id)
        pairs.append(
            D1PublicationEvidenceSnapshotPairBinding(
                case_id=case_id,
                group=group,
                seed=seed,
                duration_s=duration_s,
                arm_order=arm_order,
                arms=bindings,
            )
        )
    if len(pairs) * 2 != 26:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "evidence must bind exactly 26 fresh arms"
        )
    return D1PublicationEvidenceSnapshotEvidence(
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


def evaluate_d1_publication_evidence_snapshot_multiseed(
    source: str | Path,
    *,
    raise_on_invalid: bool = False,
) -> dict[str, Any]:
    """Evaluate the frozen matrix or return an explicit reject result."""

    try:
        return _evaluate_available(source)
    except (
        D1PublicationEvidenceSnapshotEvidenceError,
        _base.D1PublicationMetadataEvidenceError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        if raise_on_invalid:
            if isinstance(
                exc, D1PublicationEvidenceSnapshotEvidenceError
            ):
                raise
            raise D1PublicationEvidenceSnapshotEvidenceError(
                str(exc)
            ) from exc
        return _unavailable_evaluation(source, str(exc))


def _evaluate_available(source: str | Path) -> dict[str, Any]:
    evidence = load_d1_publication_evidence_snapshot_evidence_manifest(
        source
    )
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
    diagnostics_aggregate = _aggregate_snapshot_diagnostics(pairs)
    thresholds = copy.deepcopy(dict(evidence.matrix["admission_gates"]))
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
    result: dict[str, Any] = {
        "schema_version": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_EVALUATION_DATE
        ),
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "availability": {"available": True, "reason": None},
        "input_contract": {
            "evidence_manifest_path": str(evidence.source_path),
            "evidence_manifest_sha256": evidence.source_sha256,
            "evidence_manifest_schema_version": (
                D1_PUBLICATION_EVIDENCE_SNAPSHOT_EVIDENCE_SCHEMA_VERSION
            ),
            "evidence_manifest_status": (
                "episodes_complete_pending_d6"
            ),
            "matrix_path": str(evidence.matrix_path),
            "matrix_sha256": evidence.matrix_sha256,
            "matrix_schema_version": (
                D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": (
                D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXPERIMENT_ID
            ),
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
            "truth_used_for_offline_scoring_only": True,
            "clean_smoke_is_formal_evidence": False,
            "semantic_equivalence_generated_by_d6": True,
        },
        "thresholds": thresholds,
        "pairs": pairs,
        "groups": groups,
        "publication_evidence_snapshot_diagnostics_aggregate": (
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
            "The optimization verdict applies only to the frozen "
            "13-pair 200v200 three-dimensional point-mass matrix. "
            "The real-time-factor gate is reported independently. "
            "This is not AirSim, hardware, or flight-test evidence."
        ),
    }
    result["deterministic_summary_sha256"] = _payload_sha256(result)
    return result


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
    result: dict[str, Any] = {
        "schema_version": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_EVALUATION_DATE
        ),
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "availability": {"available": False, "reason": reason},
        "input_contract": {
            "evidence_manifest_path": str(
                Path(source).expanduser().resolve()
            ),
            "matrix_sha256": (
                D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SHA256
            ),
            "matrix_schema_version": (
                D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": (
                D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXPERIMENT_ID
            ),
            "source_commit": (
                D1_PUBLICATION_EVIDENCE_SNAPSHOT_SOURCE_COMMIT
            ),
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
        "publication_evidence_snapshot_diagnostics_aggregate": {},
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
    result["deterministic_summary_sha256"] = _payload_sha256(result)
    return result


def _validate_matrix(matrix: Mapping[str, Any]) -> None:
    if set(matrix) != _EXPECTED_MATRIX_KEYS:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "matrix fields differ from the frozen contract"
        )
    expected_scalars = {
        "schema_version": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SCHEMA_VERSION
        ),
        "experiment_id": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXPERIMENT_ID
        ),
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
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "matrix cooldown_s must equal 2.0"
        )
    raw_cases = _required_sequence(matrix.get("cases"), "matrix cases")
    actual = tuple(_case_metadata(item) for item in raw_cases)
    if actual != _EXPECTED_CASES:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "matrix cases differ from the frozen registration"
        )


def _evaluate_pair(
    pair: D1PublicationEvidenceSnapshotPairBinding,
    evidence: D1PublicationEvidenceSnapshotEvidence,
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
    diagnostics_audit = _pair_snapshot_diagnostics_audit(
        reference["publication_evidence_snapshot_diagnostics"],
        candidate["publication_evidence_snapshot_diagnostics"],
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
        "publication_evidence_snapshot_audit": diagnostics_audit,
        "publication_evidence_snapshot_audit_passed": bool(
            diagnostics_audit["passed"]
        ),
        "performance": performance,
    }


def _evaluate_arm(
    binding: D1PublicationEvidenceSnapshotArmBinding,
    *,
    pair: D1PublicationEvidenceSnapshotPairBinding,
    expected_commit: str,
) -> dict[str, Any]:
    context = f"{pair.case_id} {binding.arm}"
    paths = {
        name: binding.episode_dir / name
        for name in _CONSUMED_EPISODE_FILES
    }
    for name, path in paths.items():
        if not path.is_file():
            raise D1PublicationEvidenceSnapshotEvidenceError(
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
    d1_records = _semantic_jsonl_summary(
        paths["offline_identity/online_d1_records.jsonl"],
        context=f"{context} D1 online records",
    )
    d2_records = _semantic_jsonl_summary(
        paths["offline_identity/online_d2_records.jsonl"],
        context=f"{context} D2 online records",
    )
    _validate_truth_state_finite(paths["offline_truth_state.npz"])
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
    }
    for name in _CONSUMED_EPISODE_FILES:
        if name not in input_sha256:
            input_sha256[name] = _base._file_sha256(paths[name])
    input_sha256.update(
        {
            "resource_usage": _base._file_sha256(binding.resource_path),
            "stdout": _base._file_sha256(binding.stdout_path),
            "stderr": _base._file_sha256(binding.stderr_path),
        }
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
        "online_d1_records": d1_records,
        "online_d2_records": d2_records,
        "implementation_identity_passed": True,
        "implementation_surface_audit": identity_audit,
        "publication_evidence_snapshot_diagnostics": diagnostics,
        "d1_fusion_performance": fusion_performance,
        "online_consistency_evidence": consistency,
        "business_count_snapshot": _business_count_snapshot(summary),
        "artifact_provenance": {
            "passed": True,
            "path_count": len(input_sha256),
            "input_file_sha256": dict(sorted(input_sha256.items())),
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
    pair: D1PublicationEvidenceSnapshotPairBinding,
    binding: D1PublicationEvidenceSnapshotArmBinding,
    expected_commit: str,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> Mapping[str, Any]:
    context = f"{pair.case_id} {binding.arm}"
    if manifest.get("git_commit") != expected_commit:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} source commit mismatch"
        )
    if manifest.get("repository_dirty") is not False:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} repository is dirty"
        )
    if manifest.get("config_sha256") != _base._canonical_sha256(config):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} config_sha256 mismatch"
        )
    runtime_profile = _required_mapping(
        manifest.get("runtime_profile"), f"{context} runtime_profile"
    )
    if manifest.get("runtime_profile_sha256") != _base._canonical_sha256(
        runtime_profile
    ):
        raise D1PublicationEvidenceSnapshotEvidenceError(
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
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} finite_state must be true"
        )
    if (
        summary.get("online_truth_use_count") != 0
        or governance.get("online_truth_use_count") != 0
    ):
        raise D1PublicationEvidenceSnapshotEvidenceError(
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
    final = _required_mapping(
        summary.get("module_final_diagnostics"),
        f"{context} module_final_diagnostics",
    )
    runtime_configuration = _required_mapping(
        runtime_profile.get("configuration"),
        f"{context} runtime configuration",
    )
    nested_governance = _required_mapping(
        final.get("observation_governance"),
        f"{context} nested observation_governance",
    )
    expected_id = _IMPLEMENTATION_IDS[arm]
    candidate = arm == _CANDIDATE_ARM
    selector_locations = {
        "runtime_profile": runtime_profile.get(_SELECTOR_FIELD),
        "runtime_configuration": runtime_configuration.get(
            _SELECTOR_FIELD
        ),
        "summary": summary.get(_SELECTOR_FIELD),
        "module_final": final.get(_SELECTOR_FIELD),
        "governance": governance.get(_SELECTOR_FIELD),
        "nested_governance": nested_governance.get(_SELECTOR_FIELD),
    }
    for location, actual in selector_locations.items():
        _expect(actual, expected, f"{context} {location} selector")

    replay_locations = {
        "runtime_profile": runtime_profile.get(_REPLAY_SELECTOR_FIELD),
        "runtime_configuration": runtime_configuration.get(
            _REPLAY_SELECTOR_FIELD
        ),
        "summary": summary.get(_REPLAY_SELECTOR_FIELD),
        "module_final": final.get(_REPLAY_SELECTOR_FIELD),
        "governance": governance.get(_REPLAY_SELECTOR_FIELD),
        "nested_governance": nested_governance.get(
            _REPLAY_SELECTOR_FIELD
        ),
    }
    for location, actual in replay_locations.items():
        _expect(
            actual,
            _REPLAY_REFERENCE,
            f"{context} {location} replay-prefix implementation",
        )

    execution_locations = {
        "runtime_profile": runtime_profile.get(_EXECUTION_CONFIG_FIELD),
        "summary": summary.get(_EXECUTION_CONFIG_FIELD),
        "module_final": final.get(_EXECUTION_CONFIG_FIELD),
        "governance": governance.get(_EXECUTION_CONFIG_FIELD),
        "nested_governance": nested_governance.get(
            _EXECUTION_CONFIG_FIELD
        ),
    }
    for location, raw in execution_locations.items():
        _validate_execution_config(
            _required_mapping(
                raw, f"{context} {location} execution config"
            ),
            expected_selector=expected,
            expected_id=expected_id,
            candidate=candidate,
            context=f"{context} {location}",
        )

    initial = _validate_diagnostics(
        _required_mapping(
            runtime_profile.get(_DIAGNOSTICS_FIELD),
            f"{context} runtime diagnostics",
        ),
        expected_selector=expected,
        expected_id=expected_id,
        candidate=candidate,
        require_workload=False,
        context=f"{context} runtime",
    )
    workload_locations = {
        "summary": summary.get(_DIAGNOSTICS_FIELD),
        "module_final": final.get(_DIAGNOSTICS_FIELD),
        "governance": governance.get(_DIAGNOSTICS_FIELD),
        "nested_governance": nested_governance.get(_DIAGNOSTICS_FIELD),
    }
    diagnostics_by_location = {
        location: _validate_diagnostics(
            _required_mapping(
                raw, f"{context} {location} diagnostics"
            ),
            expected_selector=expected,
            expected_id=expected_id,
            candidate=candidate,
            require_workload=True,
            context=f"{context} {location}",
        )
        for location, raw in workload_locations.items()
    }
    exported = diagnostics_by_location["summary"]
    if any(
        value != exported
        for value in diagnostics_by_location.values()
    ):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} workload diagnostics differ across surfaces"
        )
    return exported, {
        "passed": True,
        "selector": expected,
        "implementation_id": expected_id,
        "selector_locations": selector_locations,
        "replay_prefix_locations": replay_locations,
        "execution_config_location_count": len(execution_locations),
        "diagnostics_location_count": (
            1 + len(diagnostics_by_location)
        ),
        "initial_diagnostics_empty": (
            not initial["operation_counts"]
            and not initial["fallback_reason_counts"]
        ),
        "workload_diagnostics_identical": True,
    }


def _validate_execution_config(
    value: Mapping[str, Any],
    *,
    expected_selector: str,
    expected_id: str,
    candidate: bool,
    context: str,
) -> dict[str, Any]:
    if set(value) != _EXPECTED_EXECUTION_CONFIG_KEYS:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} execution config fields differ from contract"
        )
    expected = {
        "schema_version": (
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXECUTION_CONFIG_SCHEMA_VERSION
        ),
        "selector": expected_selector,
        "implementation_id": expected_id,
        "candidate_enabled": candidate,
        "required_id_sources": [
            "source_observations",
            "materialized_track_latest_observation",
        ],
        "required_id_order": "deduplicated_lexicographic",
        "invalid_or_unknown_id_policy": "fallback_to_full_snapshot",
        "episode_final_export_scope": "full_exact_materialized_records",
        "truth_dependent_inputs_allowed": False,
    }
    for field, expected_value in expected.items():
        _expect(
            value.get(field),
            expected_value,
            f"{context} execution config {field}",
        )
    return copy.deepcopy(dict(value))


def _validate_diagnostics(
    value: Mapping[str, Any],
    *,
    expected_selector: str,
    expected_id: str,
    candidate: bool,
    require_workload: bool,
    context: str,
) -> dict[str, Any]:
    if set(value) != _EXPECTED_DIAGNOSTICS_KEYS:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} diagnostics fields differ from contract"
        )
    _expect(
        value.get("schema_version"),
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_DIAGNOSTICS_SCHEMA_VERSION,
        f"{context} diagnostics schema",
    )
    _validate_execution_config(
        _required_mapping(
            value.get("execution_config"),
            f"{context} nested execution config",
        ),
        expected_selector=expected_selector,
        expected_id=expected_id,
        candidate=candidate,
        context=f"{context} diagnostics",
    )
    operations = _validated_count_mapping(
        value.get("operation_counts"),
        f"{context} operation_counts",
    )
    fallbacks = _validated_count_mapping(
        value.get("fallback_reason_counts"),
        f"{context} fallback_reason_counts",
    )
    conservation = _required_mapping(
        value.get("conservation"), f"{context} conservation"
    )
    if set(conservation) != _EXPECTED_CONSERVATION_KEYS:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} conservation fields differ from contract"
        )
    if any(item is not True for item in conservation.values()):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} conservation assertion failed"
        )
    if not require_workload:
        if operations or fallbacks:
            raise D1PublicationEvidenceSnapshotEvidenceError(
                f"{context} initial diagnostics must be empty"
            )
        return copy.deepcopy(dict(value))
    if set(operations) != _OPERATION_COUNT_FIELDS:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} operation count fields differ from contract"
        )
    expected_conservation = {
        "selection_partition": (
            operations["selection_count"]
            == operations["reference_selection_count"]
            + operations["candidate_selection_count"]
        ),
        "candidate_selection_partition": (
            operations["candidate_selection_count"]
            == operations["candidate_subset_success_count"]
            + operations["candidate_fallback_count"]
        ),
        "adapter_call_partition": (
            operations["adapter_snapshot_call_count"]
            == operations["full_snapshot_call_count"]
            + operations["subset_snapshot_call_count"]
        ),
        "reference_deduplication_partition": (
            operations["source_observation_reference_count"]
            + operations["track_latest_observation_reference_count"]
            == operations["required_observation_id_count"]
            + operations["duplicate_reference_count"]
        ),
        "fallback_not_above_candidate_selection": (
            operations["candidate_fallback_count"]
            <= operations["candidate_selection_count"]
        ),
        "all_required_records_available": (
            operations["lookup_miss_count"] == 0
            and operations["invalid_required_id_count"] == 0
        ),
    }
    if dict(conservation) != expected_conservation:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} conservation does not match operation counts"
        )
    if sum(fallbacks.values()) != operations["candidate_fallback_count"]:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} fallback reasons do not conserve fallback count"
        )
    if operations["selection_count"] <= 0:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} selection_count must be positive"
        )
    if operations["publication_count"] <= 0:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} publication_count must be positive"
        )
    if operations["returned_record_count"] <= 0:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} returned_record_count must be positive"
        )
    return copy.deepcopy(dict(value))


def _pair_snapshot_diagnostics_audit(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    reference_counts = _validated_count_mapping(
        reference.get("operation_counts"),
        "reference operation_counts",
    )
    candidate_counts = _validated_count_mapping(
        candidate.get("operation_counts"),
        "candidate operation_counts",
    )
    reference_fallbacks = _validated_count_mapping(
        reference.get("fallback_reason_counts"),
        "reference fallback_reason_counts",
    )
    candidate_fallbacks = _validated_count_mapping(
        candidate.get("fallback_reason_counts"),
        "candidate fallback_reason_counts",
    )
    reference_checks = {
        "reference_selection_is_all_selections": (
            reference_counts["reference_selection_count"]
            == reference_counts["selection_count"]
        ),
        "reference_candidate_path_unused": (
            reference_counts["candidate_selection_count"] == 0
            and reference_counts["candidate_subset_success_count"] == 0
            and reference_counts["candidate_fallback_count"] == 0
        ),
        "reference_full_path_is_all_adapter_calls": (
            reference_counts["adapter_snapshot_call_count"]
            == reference_counts["full_snapshot_call_count"]
            == reference_counts["selection_count"]
            and reference_counts["subset_snapshot_call_count"] == 0
        ),
        "reference_required_id_path_unused": all(
            reference_counts[field] == 0
            for field in (
                "source_observation_reference_count",
                "track_latest_observation_reference_count",
                "required_observation_id_count",
                "duplicate_reference_count",
                "invalid_required_id_count",
                "empty_required_id_selection_count",
                "lookup_miss_count",
            )
        ),
        "reference_fallback_reasons_empty": not reference_fallbacks,
    }
    candidate_checks = {
        "candidate_selection_is_all_selections": (
            candidate_counts["candidate_selection_count"]
            == candidate_counts["selection_count"]
        ),
        "candidate_subset_success_is_all_selections": (
            candidate_counts["candidate_subset_success_count"]
            == candidate_counts["selection_count"]
        ),
        "candidate_no_fallback": (
            candidate_counts["candidate_fallback_count"] == 0
            and not candidate_fallbacks
        ),
        "candidate_subset_path_is_all_adapter_calls": (
            candidate_counts["adapter_snapshot_call_count"]
            == candidate_counts["subset_snapshot_call_count"]
            == candidate_counts["selection_count"]
            and candidate_counts["full_snapshot_call_count"] == 0
        ),
        "candidate_required_sources_exercised": (
            candidate_counts["source_observation_reference_count"] > 0
            and candidate_counts[
                "track_latest_observation_reference_count"
            ]
            > 0
            and candidate_counts["required_observation_id_count"] > 0
        ),
        "candidate_no_lookup_miss": (
            candidate_counts["lookup_miss_count"] == 0
        ),
        "candidate_no_invalid_required_id": (
            candidate_counts["invalid_required_id_count"] == 0
        ),
        "candidate_no_empty_required_set": (
            candidate_counts["empty_required_id_selection_count"] == 0
        ),
    }
    reference_returned = reference_counts["returned_record_count"]
    candidate_returned = candidate_counts["returned_record_count"]
    reduction = (
        (reference_returned - candidate_returned)
        / reference_returned
        * 100.0
    )
    checks = {**reference_checks, **candidate_checks}
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "reference_returned_record_count": reference_returned,
        "candidate_returned_record_count": candidate_returned,
        "candidate_returned_record_reduction_pct": reduction,
        "candidate_selection_count": candidate_counts[
            "candidate_selection_count"
        ],
        "candidate_subset_success_count": candidate_counts[
            "candidate_subset_success_count"
        ],
        "candidate_fallback_count": candidate_counts[
            "candidate_fallback_count"
        ],
        "candidate_lookup_miss_count": candidate_counts[
            "lookup_miss_count"
        ],
        "candidate_invalid_required_id_count": candidate_counts[
            "invalid_required_id_count"
        ],
        "candidate_empty_required_id_selection_count": candidate_counts[
            "empty_required_id_selection_count"
        ],
        "candidate_fallback_reason_counts": candidate_fallbacks,
    }


def _validate_online_consistency_evidence(
    value: Mapping[str, Any], *, context: str
) -> dict[str, Any]:
    try:
        from .d1_replay_prefix_summary_multiseed import (
            _validate_online_consistency_evidence as validate,
        )

        return validate(value, context=context)
    except Exception as exc:
        if isinstance(
            exc,
            (
                KeyboardInterrupt,
                SystemExit,
            ),
        ):
            raise
        raise D1PublicationEvidenceSnapshotEvidenceError(
            str(exc)
        ) from exc


def _validate_d1_fusion_performance(
    value: Mapping[str, Any], *, context: str
) -> dict[str, Any]:
    try:
        from .d1_replay_prefix_summary_multiseed import (
            _validate_d1_fusion_performance as validate,
        )

        return validate(value, context=context)
    except Exception as exc:
        if isinstance(
            exc,
            (
                KeyboardInterrupt,
                SystemExit,
            ),
        ):
            raise
        raise D1PublicationEvidenceSnapshotEvidenceError(
            str(exc)
        ) from exc


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
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "normalized runtime configuration lacks selector"
        )
    configuration[_SELECTOR_FIELD] = _TREATMENT_MARKER
    return normalized


def _normalized_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(summary))
    for field in ("episode_id", "wall_time_s", "real_time_factor"):
        if field not in normalized:
            raise D1PublicationEvidenceSnapshotEvidenceError(
                f"normalized summary lacks {field}"
            )
    normalized["episode_id"] = _TREATMENT_DERIVED_ID_MARKER
    normalized["wall_time_s"] = _PERFORMANCE_MARKER
    normalized["real_time_factor"] = _PERFORMANCE_MARKER
    _normalize_treatment_surface(normalized, "normalized summary")
    final = normalized.get("module_final_diagnostics")
    if not isinstance(final, dict):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "normalized summary lacks module_final_diagnostics"
        )
    _normalize_treatment_surface(final, "normalized module final")
    if "stage_timings" not in final:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            "normalized module final lacks stage_timings"
        )
    final["stage_timings"] = _PERFORMANCE_MARKER
    nested = final.get("observation_governance")
    if not isinstance(nested, Mapping):
        raise D1PublicationEvidenceSnapshotEvidenceError(
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
            raise D1PublicationEvidenceSnapshotEvidenceError(
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
    if cross.get("schema_version") != CROSS_BUILD_EQUIVALENCE_SCHEMA_VERSION:
        raise D1PublicationEvidenceSnapshotEvidenceError(
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
        "online_d1_records_semantically_equal": (
            reference["online_d1_records"]
            == candidate["online_d1_records"]
        ),
        "online_d2_records_semantically_equal": (
            reference["online_d2_records"]
            == candidate["online_d2_records"]
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
            "d1_d2_online_records_compared_explicitly": True,
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
        "publication_evidence_snapshot_audit_pass_count": sum(
            bool(pair["publication_evidence_snapshot_audit_passed"])
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


def _aggregate_snapshot_diagnostics(
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    for group in (*_GROUPS, "all"):
        selected = (
            list(pairs)
            if group == "all"
            else [pair for pair in pairs if pair["group"] == group]
        )
        reference_returned = sum(
            int(
                pair["publication_evidence_snapshot_audit"][
                    "reference_returned_record_count"
                ]
            )
            for pair in selected
        )
        candidate_returned = sum(
            int(
                pair["publication_evidence_snapshot_audit"][
                    "candidate_returned_record_count"
                ]
            )
            for pair in selected
        )
        groups[group] = {
            "pair_count": len(selected),
            "reference_returned_record_count": reference_returned,
            "candidate_returned_record_count": candidate_returned,
            "candidate_returned_record_reduction_pct": (
                (reference_returned - candidate_returned)
                / reference_returned
                * 100.0
                if reference_returned > 0
                else 0.0
            ),
            "candidate_selection_count": sum(
                int(
                    pair["publication_evidence_snapshot_audit"][
                        "candidate_selection_count"
                    ]
                )
                for pair in selected
            ),
            "candidate_subset_success_count": sum(
                int(
                    pair["publication_evidence_snapshot_audit"][
                        "candidate_subset_success_count"
                    ]
                )
                for pair in selected
            ),
            "candidate_fallback_count": sum(
                int(
                    pair["publication_evidence_snapshot_audit"][
                        "candidate_fallback_count"
                    ]
                )
                for pair in selected
            ),
            "candidate_lookup_miss_count": sum(
                int(
                    pair["publication_evidence_snapshot_audit"][
                        "candidate_lookup_miss_count"
                    ]
                )
                for pair in selected
            ),
            "candidate_invalid_required_id_count": sum(
                int(
                    pair["publication_evidence_snapshot_audit"][
                        "candidate_invalid_required_id_count"
                    ]
                )
                for pair in selected
            ),
            "candidate_empty_required_id_selection_count": sum(
                int(
                    pair["publication_evidence_snapshot_audit"][
                        "candidate_empty_required_id_selection_count"
                    ]
                )
                for pair in selected
            ),
        }
    return {
        "schema_version": (
            "d6.d1_publication_evidence_snapshot_diagnostics_aggregate.v1"
        ),
        "groups": groups,
    }


def _admission_gates(
    pairs: Sequence[Mapping[str, Any]],
    groups: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
    thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    short = _required_mapping(groups.get("short"), "short group")
    long = _required_mapping(groups.get("long"), "long group")
    short_metrics = _required_mapping(
        short.get("metrics"), "short metrics"
    )
    long_metrics = _required_mapping(long.get("metrics"), "long metrics")
    short_d1 = _required_mapping(
        short_metrics.get("d1_fusion_wall_s"), "short D1 fusion"
    )
    long_d1 = _required_mapping(
        long_metrics.get("d1_fusion_wall_s"), "long D1 fusion"
    )
    short_core = _required_mapping(
        short_metrics.get("core_wall_s"), "short core"
    )
    long_core = _required_mapping(
        long_metrics.get("core_wall_s"), "long core"
    )
    short_d2 = _required_mapping(
        short_metrics.get("d2_association_wall_s"),
        "short D2 association",
    )
    long_d2 = _required_mapping(
        long_metrics.get("d2_association_wall_s"),
        "long D2 association",
    )
    short_rss = _required_mapping(
        short_metrics.get("maximum_rss_kib"), "short RSS"
    )
    long_rss = _required_mapping(
        long_metrics.get("maximum_rss_kib"), "long RSS"
    )
    all_diag = _required_mapping(
        _required_mapping(
            diagnostics.get("groups"), "diagnostic groups"
        ).get("all"),
        "all diagnostics",
    )
    pair_count = len(pairs)
    business_count = sum(
        bool(pair["business_semantics_passed"]) for pair in pairs
    )
    finite_count = sum(
        bool(pair["finite_state_passed"]) for pair in pairs
    )
    identity_count = sum(
        bool(pair["implementation_identity_passed"]) for pair in pairs
    )
    audit_count = sum(
        bool(pair["publication_evidence_snapshot_audit_passed"])
        for pair in pairs
    )
    consistency_count = sum(
        bool(pair["consistency_evidence_records_digest_equal"])
        for pair in pairs
    )
    operation_count = sum(
        bool(pair["existing_operation_counts_equal"]) for pair in pairs
    )
    maximum_truth_use = max(
        max(
            int(pair["reference"]["online_truth_use_count"]),
            int(pair["candidate"]["online_truth_use_count"]),
        )
        for pair in pairs
    )
    short_bootstrap_upper_pct = (
        short_d1["raw_relative_change"]["bootstrap_95_ci"]["upper"]
        * 100.0
    )
    rss_mean_increase = max(
        short_rss["raw_relative_change"]["mean"] * 100.0,
        long_rss["raw_relative_change"]["mean"] * 100.0,
    )
    any_pair_rss_increase = max(
        pair["performance"]["maximum_rss_kib"]["raw_relative_change"]
        * 100.0
        for pair in pairs
    )
    definitions = {
        "all_pairs_business_semantics_equal": (
            business_count,
            pair_count,
            "==",
            business_count == pair_count,
            "one_or_more_business_semantics_mismatch",
        ),
        "all_pairs_finite_state": (
            finite_count,
            pair_count,
            "==",
            finite_count == pair_count,
            "one_or_more_nonfinite_episode",
        ),
        "all_pairs_online_truth_use_count": (
            maximum_truth_use,
            thresholds["all_pairs_online_truth_use_count"],
            "==",
            maximum_truth_use
            == thresholds["all_pairs_online_truth_use_count"],
            "online_truth_used",
        ),
        "all_pairs_explicit_implementation_identity": (
            identity_count,
            pair_count,
            "==",
            identity_count == pair_count,
            "one_or_more_implementation_identity_mismatch",
        ),
        "all_pairs_publication_evidence_snapshot_audit_valid": (
            audit_count,
            pair_count,
            "==",
            audit_count == pair_count,
            "one_or_more_snapshot_diagnostics_audit_failed",
        ),
        "all_pairs_consistency_evidence_records_digest_equal": (
            consistency_count,
            pair_count,
            "==",
            consistency_count == pair_count,
            "one_or_more_consistency_digest_mismatch",
        ),
        "all_pairs_existing_operation_counts_equal": (
            operation_count,
            pair_count,
            "==",
            operation_count == pair_count,
            "one_or_more_existing_operation_count_mismatch",
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
            short_bootstrap_upper_pct,
            thresholds[
                "short_bootstrap_relative_change_upper_bound_pct"
            ],
            "<=",
            short_bootstrap_upper_pct
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
        "minimum_candidate_returned_record_reduction_pct": (
            all_diag["candidate_returned_record_reduction_pct"],
            thresholds[
                "minimum_candidate_returned_record_reduction_pct"
            ],
            ">=",
            all_diag["candidate_returned_record_reduction_pct"]
            >= thresholds[
                "minimum_candidate_returned_record_reduction_pct"
            ],
            "candidate_returned_record_reduction_below_threshold",
        ),
    }
    percentage_gates = {
        name for name in definitions if name.endswith("_pct")
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


def write_d1_publication_evidence_snapshot_multiseed_report(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write deterministic D6 products outside the producer evidence root."""

    if result.get("schema_version") != (
        D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_EVALUATION_SCHEMA_VERSION
    ):
        raise ValueError("unsupported publication-evidence evaluation schema")
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
        / "d1_publication_evidence_snapshot_multiseed_evaluation.json",
        "compact_json": directory
        / "d1_publication_evidence_snapshot_multiseed_compact.json",
        "pairs_csv": directory
        / "d1_publication_evidence_snapshot_multiseed_pairs.csv",
        "markdown": directory
        / "D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_REPORT_CN.md",
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
        render_d1_publication_evidence_snapshot_multiseed_markdown(
            result
        ),
        encoding="utf-8",
    )
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
            D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_COMPACT_SCHEMA_VERSION
        ),
        "evaluation_schema_version": result["schema_version"],
        "evaluation_date": result["evaluation_date"],
        "deterministic_summary_sha256": result[
            "deterministic_summary_sha256"
        ],
        "availability": result["availability"],
        "input_contract": result["input_contract"],
        "scope": result["scope"],
        "groups": result.get("groups", {}),
        "publication_evidence_snapshot_diagnostics_aggregate": result[
            "publication_evidence_snapshot_diagnostics_aggregate"
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


def render_d1_publication_evidence_snapshot_multiseed_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the independent Chinese admission report."""

    availability = _required_mapping(
        result.get("availability"), "report availability"
    )
    if availability.get("available") is not True:
        return "\n".join(
            [
                "# D1 在线发布证据子集快照多种子评估",
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
        "publication_evidence_snapshot_diagnostics_aggregate"
    ]["groups"]["all"]
    failed = [name for name, gate in gates.items() if not gate["passed"]]
    lines = [
        "# D1 在线发布证据子集快照同提交多种子评估",
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
            f"`{_fmt(result['system_realtime_gate']['candidate_minimum_real_time_factor'])}`。"
            "实时门独立列示，不并入本次优化准入结论。"
        ),
        "本结论只覆盖冻结的三维质点 200 对 200 矩阵，不包含 AirSim、硬件、实机或实飞证据。",
        "",
        "## 证据",
        "",
        f"- producer clean commit：`{contract['source_commit']}`。",
        f"- matrix SHA-256：`{contract['matrix_sha256']}`。",
        "- short 10 对、long 3 对，共 13 对和 26 个全新 episode；复用 0、失败 0。",
        "- 两臂仅允许在线发布证据快照 selector 不同，回放前缀均固定为参考实现。",
        "- 在线真值使用次数为 0；真值制品只参与离线一致性评分。",
        "",
        "## 语义审计",
        "",
        "D6 独立比较在线总线、D1 和 D2 在线记录、业务计数、离线一致性记录及安全结果。"
        "两臂离线一致性记录数量和摘要必须完全相同，原 D1 融合操作计数也必须完全相同。",
        "",
        "执行配置和诊断分别在运行配置、汇总、模块结束诊断、观测治理及嵌套治理表面核验。"
        "候选不得发生回退、查询缺失、非法标识或空集合选择。参考臂必须全程走完整快照路径。",
        "",
        "## 记录工作量",
        "",
        "| 项目 | 数量 |",
        "|---|---:|",
        f"| 参考返回记录 | {aggregate['reference_returned_record_count']} |",
        f"| 候选返回记录 | {aggregate['candidate_returned_record_count']} |",
        f"| 候选削减率 | {_fmt(aggregate['candidate_returned_record_reduction_pct'])}% |",
        f"| 候选选择次数 | {aggregate['candidate_selection_count']} |",
        f"| 候选子集成功次数 | {aggregate['candidate_subset_success_count']} |",
        f"| 候选回退次数 | {aggregate['candidate_fallback_count']} |",
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
            "任何 matrix SHA、producer commit、schema、路径、arm 状态、实现标识、"
            "唯一 treatment、规模或时间参数不一致均失败关闭。评估器不写入原始证据，"
            "也不向在线控制路径发布消息。",
            "",
            "输出包括完整 JSON、紧凑 JSON、逐对 CSV、中文报告和制品校验值。",
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
        "publication_evidence_snapshot_audit_passed",
        "reference_returned_record_count",
        "candidate_returned_record_count",
        "candidate_returned_record_reduction_pct",
        "candidate_selection_count",
        "candidate_subset_success_count",
        "candidate_fallback_count",
        "candidate_lookup_miss_count",
        "candidate_invalid_required_id_count",
        "candidate_empty_required_id_selection_count",
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
            audit = pair["publication_evidence_snapshot_audit"]
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
                    "publication_evidence_snapshot_audit_passed",
                )
            }
            for name in (
                "reference_returned_record_count",
                "candidate_returned_record_count",
                "candidate_returned_record_reduction_pct",
                "candidate_selection_count",
                "candidate_subset_success_count",
                "candidate_fallback_count",
                "candidate_lookup_miss_count",
                "candidate_invalid_required_id_count",
                "candidate_empty_required_id_selection_count",
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
        "--integrated-stack",
        "--d1-publication-evidence-snapshot-implementation",
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
    reference = list(commands[_REFERENCE_ARM])
    candidate = list(commands[_CANDIDATE_ARM])
    selector_flag = "--d1-publication-evidence-snapshot-implementation"
    output_flag = "--output"
    try:
        selector_index = reference.index(selector_flag)
        candidate_selector_index = candidate.index(selector_flag)
        output_index = reference.index(output_flag)
        candidate_output_index = candidate.index(output_flag)
    except ValueError as exc:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{case_id} command lacks treatment or output flag"
        ) from exc
    if (
        selector_index != candidate_selector_index
        or output_index != candidate_output_index
    ):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{case_id} arm command structure differs"
        )
    normalized_reference = list(reference)
    normalized_candidate = list(candidate)
    normalized_reference[selector_index + 1] = _TREATMENT_MARKER
    normalized_candidate[candidate_selector_index + 1] = _TREATMENT_MARKER
    normalized_reference[output_index + 1] = "D6_ARM_OUTPUT"
    normalized_candidate[candidate_output_index + 1] = "D6_ARM_OUTPUT"
    if normalized_reference != normalized_candidate:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{case_id} commands differ outside registered treatment/output"
        )


def _semantic_jsonl_summary(
    path: Path, *, context: str
) -> dict[str, Any]:
    records: list[Any] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, start=1):
            text = raw.strip()
            if not text:
                raise D1PublicationEvidenceSnapshotEvidenceError(
                    f"{context} has blank line {line_number}"
                )
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise D1PublicationEvidenceSnapshotEvidenceError(
                    f"{context} line {line_number} is invalid JSON"
                ) from exc
            records.append(value)
    if not records:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} must contain records"
        )
    return {
        "record_count": len(records),
        "semantic_records_sha256": _payload_sha256(records),
    }


def _strict_jsonl_count(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, start=1):
            text = raw.strip()
            if not text:
                raise D1PublicationEvidenceSnapshotEvidenceError(
                    f"{path} contains blank line {line_number}"
                )
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                raise D1PublicationEvidenceSnapshotEvidenceError(
                    f"{path} contains invalid JSON at line {line_number}"
                ) from exc
            count += 1
    return count


def _load_stage(path: Path, stage_name: str) -> dict[str, Any]:
    try:
        from .d1_replay_prefix_summary_multiseed import (
            _load_stage as load,
        )

        return load(path, stage_name)
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise D1PublicationEvidenceSnapshotEvidenceError(
            str(exc)
        ) from exc


def _load_resource_metrics(path: Path) -> dict[str, float | int]:
    try:
        return _base._load_resource_metrics(path)
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise D1PublicationEvidenceSnapshotEvidenceError(
            str(exc)
        ) from exc


def _validate_truth_state_finite(path: Path) -> None:
    try:
        _base._validate_truth_state_finite(path)
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise D1PublicationEvidenceSnapshotEvidenceError(
            str(exc)
        ) from exc


def _validate_stderr(path: Path, context: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    forbidden = ("Traceback (most recent call last)", "ERROR", "FATAL")
    matches = [item for item in forbidden if item in raw]
    if matches:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} stderr contains failure marker: {matches[0]}"
        )
    return {
        "passed": True,
        "byte_count": len(raw.encode("utf-8")),
        "forbidden_marker_count": 0,
    }


def _finite_nonnegative(
    value: Any, context: str, *, positive: bool = False
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
        or (positive and float(value) <= 0.0)
    ):
        qualifier = "positive" if positive else "nonnegative"
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} must be finite {qualifier}"
        )
    return float(value)


def _case_metadata(
    value: Any,
) -> tuple[str, str, int, float, tuple[str, str]]:
    case = _required_mapping(value, "case")
    case_id = _required_text(case.get("case_id"), "case_id")
    group = _required_text(case.get("group"), f"{case_id} group")
    seed = _nonnegative_integer(case.get("seed"), f"{case_id} seed")
    duration = _finite_nonnegative(
        case.get("duration_s"), f"{case_id} duration", positive=True
    )
    arm_order_raw = _required_sequence(
        case.get("arm_order"), f"{case_id} arm_order"
    )
    arm_order = tuple(
        _required_text(item, f"{case_id} arm_order item")
        for item in arm_order_raw
    )
    if len(arm_order) != 2 or set(arm_order) != set(_ARMS):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{case_id} arm_order must contain both arms"
        )
    return case_id, group, seed, duration, (arm_order[0], arm_order[1])


def _load_mapping(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{path} must contain a JSON object"
        )
    return value, raw


def _required_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} must be a mapping"
        )
    return value


def _required_sequence(value: Any, context: str) -> Sequence[Any]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} must be a sequence"
        )
    return value


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} must be nonempty text"
        )
    return value


def _required_commit(value: Any, context: str) -> str:
    text = _required_text(value, context)
    if len(text) != 40 or any(ch not in "0123456789abcdef" for ch in text):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} must be a full lowercase Git commit"
        )
    return text


def _required_sha256(value: Any, context: str) -> str:
    text = _required_text(value, context)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} must be a lowercase SHA-256"
        )
    return text


def _explicit_path(
    value: Any, context: str, *, require: str
) -> Path:
    text = _required_text(value, context)
    raw = Path(text).expanduser()
    if not raw.is_absolute():
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} must be absolute"
        )
    path = raw.resolve()
    exists = path.is_file() if require == "file" else path.is_dir()
    if not exists:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} required {require} is unavailable: {path}"
        )
    return path


def _require_under_root(path: Path, root: Path, context: str) -> None:
    if not _base._path_is_within(path, root):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} escapes output_root"
        )


def _expect(actual: Any, expected: Any, context: str) -> None:
    if actual != expected:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} mismatch: expected {expected!r}, got {actual!r}"
        )


def _expect_finite_equal(
    actual: Any, expected: float, context: str
) -> None:
    value = _finite_nonnegative(actual, context)
    if not math.isclose(
        value, float(expected), rel_tol=0.0, abs_tol=1e-12
    ):
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} mismatch: expected {expected}, got {value}"
        )


def _nonnegative_integer(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise D1PublicationEvidenceSnapshotEvidenceError(
            f"{context} must be a nonnegative integer"
        )
    return value


def _validated_count_mapping(
    value: Any, context: str
) -> dict[str, int]:
    mapping = _required_mapping(value, context)
    result: dict[str, int] = {}
    for raw_key, raw_value in mapping.items():
        key = _required_text(raw_key, f"{context} key")
        result[key] = _nonnegative_integer(
            raw_value, f"{context}.{key}"
        )
    return result


def _payload_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return str(value).lower()
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
            "Evaluate the frozen D1 publication-evidence snapshot "
            "13-pair matrix"
        )
    )
    parser.add_argument(
        "--evidence-manifest",
        required=True,
        help="completed publication-evidence evidence_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="independent D6 output directory",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = evaluate_d1_publication_evidence_snapshot_multiseed(
        args.evidence_manifest
    )
    paths = write_d1_publication_evidence_snapshot_multiseed_report(
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
    "D1_PUBLICATION_EVIDENCE_SNAPSHOT_DIAGNOSTICS_SCHEMA_VERSION",
    "D1_PUBLICATION_EVIDENCE_SNAPSHOT_EVALUATION_DATE",
    "D1_PUBLICATION_EVIDENCE_SNAPSHOT_EVIDENCE_SCHEMA_VERSION",
    "D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXECUTION_CONFIG_SCHEMA_VERSION",
    "D1_PUBLICATION_EVIDENCE_SNAPSHOT_EXPERIMENT_ID",
    "D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SCHEMA_VERSION",
    "D1_PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_SHA256",
    "D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_COMPACT_SCHEMA_VERSION",
    "D1_PUBLICATION_EVIDENCE_SNAPSHOT_MULTISEED_EVALUATION_SCHEMA_VERSION",
    "D1_PUBLICATION_EVIDENCE_SNAPSHOT_SOURCE_COMMIT",
    "D1PublicationEvidenceSnapshotEvidence",
    "D1PublicationEvidenceSnapshotEvidenceError",
    "REFERENCE_IMPLEMENTATION",
    "REFERENCE_IMPLEMENTATION_ID",
    "evaluate_d1_publication_evidence_snapshot_multiseed",
    "load_d1_publication_evidence_snapshot_evidence_manifest",
    "main",
    "render_d1_publication_evidence_snapshot_multiseed_markdown",
    "write_d1_publication_evidence_snapshot_multiseed_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
