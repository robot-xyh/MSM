"""Independent paired admission for the scalable 3D online truth guard.

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


ONLINE_TRUTH_GUARD_MULTISEED_EVALUATION_SCHEMA_VERSION = (
    "d6.online_truth_guard_multiseed_evaluation.v1"
)
ONLINE_TRUTH_GUARD_MULTISEED_COMPACT_SCHEMA_VERSION = (
    "d6.online_truth_guard_multiseed_compact.v1"
)
ONLINE_TRUTH_GUARD_MATRIX_SCHEMA_VERSION = (
    "scalable3d-online-truth-guard-multiseed-matrix-v1"
)
ONLINE_TRUTH_GUARD_EVIDENCE_SCHEMA_VERSION = (
    "scalable3d-online-truth-guard-multiseed-evidence-v1"
)
ONLINE_TRUTH_GUARD_DIAGNOSTICS_SCHEMA_VERSION = (
    "scalable3d-online-truth-guard-diagnostics-v1"
)
ONLINE_TRUTH_GUARD_EXPERIMENT_ID = (
    "online-truth-guard-multiseed-20260724-v1"
)
ONLINE_TRUTH_GUARD_MATRIX_SHA256 = (
    "764574b9897d00101c26c555de2f407e1736c7e6ff50420eebf131e154618dc8"
)
ONLINE_TRUTH_GUARD_SOURCE_COMMIT = (
    "8d8bb6ed7a417705236835f235361f45a021bb2b"
)
ONLINE_TRUTH_GUARD_EVALUATION_DATE = "2026-07-24"

REFERENCE_IMPLEMENTATION = "generic_recursive_v1"
CANDIDATE_IMPLEMENTATION = "builtin_specialized_recursive_v2"

_REFERENCE_ARM = "reference"
_CANDIDATE_ARM = "candidate"
_ARMS = (_REFERENCE_ARM, _CANDIDATE_ARM)
_GROUPS = ("short", "long")
_IMPLEMENTATIONS = {
    _REFERENCE_ARM: REFERENCE_IMPLEMENTATION,
    _CANDIDATE_ARM: CANDIDATE_IMPLEMENTATION,
}
_RUN_FLAGS = ("--integrated-stack",)
_TARGET_COUNT = 200
_RESOURCE_COUNT = 200
_RECON_COUNT = 2
_BOOTSTRAP_RESAMPLES = 10_000
_BOOTSTRAP_RNG_SEED = 20_260_724
_SHORT_SEEDS = tuple(range(1101, 1111))
_LONG_SEEDS = tuple(range(1101, 1104))
_SHORT_DURATION_S = 2.2
_LONG_DURATION_S = 10.0
_TREATMENT_MARKER = "D6_REGISTERED_ONLINE_TRUTH_GUARD_TREATMENT"
_PERFORMANCE_MARKER = "D6_REGISTERED_PERFORMANCE_DIAGNOSTIC"
_TREATMENT_DERIVED_ID_MARKER = "D6_TREATMENT_DERIVED_EPISODE_ID"
_VALIDATION_KIND = "online_truth_guard"

_EXPECTED_GATES = {
    "all_pairs_business_semantics_equal": True,
    "all_pairs_finite_state": True,
    "all_pairs_online_truth_use_count": 0,
    "all_pairs_explicit_implementation_identity": True,
    "all_pairs_truth_guard_audit_valid": True,
    "short_minimum_candidate_faster_count": 8,
    "short_minimum_publication_bus_improvement_pct": 10.0,
    "short_bootstrap_relative_change_upper_bound_pct": 0.0,
    "long_minimum_candidate_faster_count": 2,
    "long_minimum_publication_bus_improvement_pct": 10.0,
    "long_bootstrap_relative_change_upper_bound_pct": 0.0,
    "short_minimum_core_wall_improvement_pct": 0.5,
    "long_minimum_core_wall_improvement_pct": 0.5,
    "maximum_short_d1_fusion_mean_increase_pct": 5.0,
    "maximum_long_d1_fusion_mean_increase_pct": 5.0,
    "maximum_short_d2_association_mean_increase_pct": 5.0,
    "maximum_long_d2_association_mean_increase_pct": 5.0,
    "maximum_rss_mean_increase_pct": 5.0,
    "maximum_any_pair_rss_increase_pct": 5.0,
}
_EXPECTED_BOUNDARY = {
    "simulation_mode": "three_dimensional_point_mass",
    "airsim_evidence": False,
    "truth_is_online_control_input": False,
    "system_realtime_requires_real_time_factor_at_least_one": True,
    "same_source_commit_for_both_arms": True,
    "only_allowed_runtime_treatment_difference": (
        "online_truth_guard_implementation"
    ),
    "reference_implementation": REFERENCE_IMPLEMENTATION,
    "candidate_implementation": CANDIDATE_IMPLEMENTATION,
    "default_implementation": REFERENCE_IMPLEMENTATION,
    "candidate_is_default": False,
    "truth_guard_diagnostics_schema_version": (
        ONLINE_TRUTH_GUARD_DIAGNOSTICS_SCHEMA_VERSION
    ),
    "online_message_payloads_must_match": True,
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
    ("long_seed_1101", "long", 1101, 10.0, ("candidate", "reference")),
    ("long_seed_1102", "long", 1102, 10.0, ("reference", "candidate")),
    ("long_seed_1103", "long", 1103, 10.0, ("candidate", "reference")),
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
    "d2_association": "module.d2_association",
    "module_publication_bus": "module_publication_bus",
    "module_publication_bus_finalize": "module_publication_bus_finalize",
}
_METRICS = (
    "module_publication_bus_wall_s",
    "module_publication_bus_finalize_wall_s",
    "module_publication_bus_total_wall_s",
    "core_wall_s",
    "external_elapsed_s",
    "real_time_factor",
    "d1_fusion_wall_s",
    "d2_association_wall_s",
    "maximum_rss_kib",
)
_LOWER_IS_BETTER = set(_METRICS) - {"real_time_factor"}
_REQUIRED_ADMISSION_METRICS = set(_METRICS)
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


class OnlineTruthGuardEvidenceError(ValueError):
    """Raised when producer evidence violates the frozen D6 contract."""


@dataclass(frozen=True)
class OnlineTruthGuardArmBinding:
    arm: str
    implementation: str
    episode_dir: Path
    resource_path: Path
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True)
class OnlineTruthGuardPairBinding:
    case_id: str
    group: str
    seed: int
    duration_s: float
    arm_order: tuple[str, ...]
    arms: Mapping[str, OnlineTruthGuardArmBinding]


@dataclass(frozen=True)
class OnlineTruthGuardEvidence:
    source_path: Path
    source_sha256: str
    matrix_path: Path
    matrix_sha256: str
    matrix: Mapping[str, Any]
    output_root: Path
    source_commit: str
    source_worktree: Path
    pairs: tuple[OnlineTruthGuardPairBinding, ...]


def load_online_truth_guard_evidence_manifest(
    source: str | Path,
) -> OnlineTruthGuardEvidence:
    """Load one completed producer manifest and fail closed on drift."""

    source_path = Path(source).expanduser().resolve()
    manifest, manifest_raw = _load_mapping(source_path)
    _expect(
        manifest.get("schema_version"),
        ONLINE_TRUTH_GUARD_EVIDENCE_SCHEMA_VERSION,
        "evidence schema_version",
    )
    _expect(
        manifest.get("experiment_id"),
        ONLINE_TRUTH_GUARD_EXPERIMENT_ID,
        "evidence experiment_id",
    )
    _expect(
        manifest.get("required_d6_evaluator_schema_version"),
        ONLINE_TRUTH_GUARD_MULTISEED_EVALUATION_SCHEMA_VERSION,
        "required D6 evaluator schema",
    )
    _expect(
        manifest.get("truth_guard_diagnostics_schema_version"),
        ONLINE_TRUTH_GUARD_DIAGNOSTICS_SCHEMA_VERSION,
        "truth-guard diagnostics schema",
    )
    if manifest.get("status") != "episodes_complete_pending_d6":
        raise OnlineTruthGuardEvidenceError(
            "evidence status must be episodes_complete_pending_d6"
        )
    _required_text(manifest.get("completed_at_utc"), "completed_at_utc")
    source_commit = _required_commit(
        manifest.get("source_commit"), "source_commit"
    )
    if source_commit != ONLINE_TRUTH_GUARD_SOURCE_COMMIT:
        raise OnlineTruthGuardEvidenceError(
            "source_commit does not match the frozen producer commit"
        )
    if manifest.get("source_repository_dirty") is not False:
        raise OnlineTruthGuardEvidenceError(
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
        raise OnlineTruthGuardEvidenceError(
            "evidence_manifest.json must be directly under output_root"
        )
    matrix_path = _explicit_path(
        manifest.get("matrix_path"), "matrix_path", require="file"
    )
    matrix_sha256 = _required_sha256(
        manifest.get("matrix_sha256"), "matrix_sha256"
    )
    if matrix_sha256 != _base._file_sha256(matrix_path):
        raise OnlineTruthGuardEvidenceError(
            "matrix_sha256 does not match matrix_path bytes"
        )
    if matrix_sha256 != ONLINE_TRUTH_GUARD_MATRIX_SHA256:
        raise OnlineTruthGuardEvidenceError(
            "matrix_sha256 does not match the frozen producer matrix"
        )
    matrix, _ = _load_mapping(matrix_path)
    _validate_matrix(matrix)
    if _required_mapping(manifest.get("matrix"), "embedded matrix") != matrix:
        raise OnlineTruthGuardEvidenceError(
            "embedded matrix does not exactly match matrix_path"
        )

    raw_cases = _required_sequence(manifest.get("cases"), "evidence cases")
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise OnlineTruthGuardEvidenceError(
            "evidence manifest must contain exactly 13 cases"
        )
    pairs: list[OnlineTruthGuardPairBinding] = []
    used_paths: set[Path] = {source_path}
    for raw_case, expected_case in zip(
        raw_cases, _EXPECTED_CASES, strict=True
    ):
        case = _required_mapping(raw_case, "evidence case")
        metadata = _case_metadata(case)
        if metadata != expected_case:
            raise OnlineTruthGuardEvidenceError(
                "evidence case differs from the frozen matrix"
            )
        case_id, group, seed, duration_s, arm_order = metadata
        if (
            case.get("d6_evaluation_status")
            != "episodes_complete_pending_d6"
        ):
            raise OnlineTruthGuardEvidenceError(
                f"{case_id} is not pending D6 evaluation"
            )
        raw_arms = _required_mapping(case.get("arms"), f"{case_id} arms")
        if set(raw_arms) != set(_ARMS):
            raise OnlineTruthGuardEvidenceError(
                f"{case_id} arms must be reference and candidate"
            )
        arms: dict[str, OnlineTruthGuardArmBinding] = {}
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
                record.get("expected_truth_guard_implementation"),
                implementation,
                f"{case_id} {arm} expected truth-guard implementation",
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
                raise OnlineTruthGuardEvidenceError(
                    f"{case_id} {arm} must be a fresh complete arm"
                )
            return_code = record.get("return_code")
            if (
                not isinstance(return_code, int)
                or isinstance(return_code, bool)
                or return_code != 0
            ):
                raise OnlineTruthGuardEvidenceError(
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
                    raise OnlineTruthGuardEvidenceError(
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
                raise OnlineTruthGuardEvidenceError(
                    f"{case_id} {arm} command differs from frozen execution"
                )
            commands[arm] = command
            arms[arm] = OnlineTruthGuardArmBinding(
                arm=arm,
                implementation=implementation,
                episode_dir=episode_dir,
                resource_path=resource_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        _validate_pair_command_isolation(commands, case_id)
        pairs.append(
            OnlineTruthGuardPairBinding(
                case_id=case_id,
                group=group,
                seed=seed,
                duration_s=duration_s,
                arm_order=arm_order,
                arms=arms,
            )
        )
    return OnlineTruthGuardEvidence(
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


def evaluate_online_truth_guard_multiseed(
    source: str | Path,
) -> dict[str, Any]:
    """Evaluate the frozen 13-pair online truth-guard matrix."""

    evidence = load_online_truth_guard_evidence_manifest(source)
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
    thresholds = copy.deepcopy(
        dict(_required_mapping(
            evidence.matrix["admission_gates"], "admission gates"
        ))
    )
    gates = _admission_gates(pairs, groups, thresholds)
    optimization_admitted = all(
        bool(gate["passed"]) for gate in gates.values()
    )
    realtime_gate = _base._system_realtime_gate(pairs)
    return {
        "schema_version": (
            ONLINE_TRUTH_GUARD_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": ONLINE_TRUTH_GUARD_EVALUATION_DATE,
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "input_contract": {
            "evidence_manifest_path": str(evidence.source_path),
            "evidence_manifest_sha256": evidence.source_sha256,
            "evidence_manifest_schema_version": (
                ONLINE_TRUTH_GUARD_EVIDENCE_SCHEMA_VERSION
            ),
            "evidence_manifest_status": (
                "episodes_complete_pending_d6"
            ),
            "matrix_path": str(evidence.matrix_path),
            "matrix_sha256": evidence.matrix_sha256,
            "matrix_schema_version": (
                ONLINE_TRUTH_GUARD_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": ONLINE_TRUTH_GUARD_EXPERIMENT_ID,
            "output_root": str(evidence.output_root),
            "source_commit": evidence.source_commit,
            "source_repository_dirty": False,
            "same_commit_for_both_arms": True,
            "arm_implementations": dict(_IMPLEMENTATIONS),
            "truth_guard_diagnostics_schema_version": (
                ONLINE_TRUTH_GUARD_DIAGNOSTICS_SCHEMA_VERSION
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
            "online_message_validation_conservation_required": True,
            "candidate_default_enabled": False,
        },
        "pairs": pairs,
        "groups": groups,
        "admission_gates": gates,
        "optimization_admitted": optimization_admitted,
        "system_realtime_gate": realtime_gate,
        "system_realtime_gap_closed": bool(realtime_gate["passed"]),
    }


def _validate_matrix(matrix: Mapping[str, Any]) -> None:
    if set(matrix) != _EXPECTED_MATRIX_KEYS:
        raise OnlineTruthGuardEvidenceError(
            "matrix fields differ from the frozen producer contract"
        )
    expected_scalars = {
        "schema_version": ONLINE_TRUTH_GUARD_MATRIX_SCHEMA_VERSION,
        "experiment_id": ONLINE_TRUTH_GUARD_EXPERIMENT_ID,
        "same_clean_commit_required": True,
        "target_count": _TARGET_COUNT,
        "resource_count": _RESOURCE_COUNT,
        "recon_count": _RECON_COUNT,
        "arm_implementations": _IMPLEMENTATIONS,
        "run_flags": list(_RUN_FLAGS),
        "cooldown_s": 2.0,
        "bootstrap_seed": _BOOTSTRAP_RNG_SEED,
        "bootstrap_resamples": _BOOTSTRAP_RESAMPLES,
    }
    for field, expected in expected_scalars.items():
        _expect(matrix.get(field), expected, f"matrix {field}")
    raw_cases = _required_sequence(matrix.get("cases"), "matrix cases")
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise OnlineTruthGuardEvidenceError(
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
            raise OnlineTruthGuardEvidenceError(
                "matrix case fields differ from the frozen contract"
            )
        if _case_metadata(case) != expected:
            raise OnlineTruthGuardEvidenceError(
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
        "--online-truth-guard-implementation",
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
        raise OnlineTruthGuardEvidenceError(
            f"{case_id} arm command lengths differ"
        )
    selector_index = reference.index(
        "--online-truth-guard-implementation"
    ) + 1
    output_index = reference.index("--output") + 1
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index in {selector_index, output_index}:
            continue
        if left != right:
            raise OnlineTruthGuardEvidenceError(
                f"{case_id} commands differ outside treatment/output"
            )


def _evaluate_pair(
    pair: OnlineTruthGuardPairBinding,
    evidence: OnlineTruthGuardEvidence,
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
    performance = {
        metric: _base._compare_pair_metric(
            reference["metrics"][metric],
            candidate["metrics"][metric],
            lower_is_better=metric in _LOWER_IS_BETTER,
        )
        for metric in _METRICS
    }
    audit_passed = (
        reference["truth_guard_audit"]["passed"]
        and candidate["truth_guard_audit"]["passed"]
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
        "truth_guard_audit_passed": bool(audit_passed),
        "artifact_provenance_passed": bool(
            artifact_provenance_passed
        ),
        "performance": performance,
    }


def _evaluate_arm(
    binding: OnlineTruthGuardArmBinding,
    *,
    pair: OnlineTruthGuardPairBinding,
    expected_commit: str,
) -> dict[str, Any]:
    context = f"{pair.case_id} {binding.arm}"
    episode = binding.episode_dir
    paths = {
        name: episode / name for name in _base._CONSUMED_EPISODE_FILES
    }
    for name, path in paths.items():
        if not path.is_file():
            raise OnlineTruthGuardEvidenceError(
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
    diagnostics, audit = _validate_truth_guard_identity(
        arm=binding.arm,
        expected=binding.implementation,
        runtime_profile=runtime_profile,
        summary=summary,
        online_message_count=online_message_count,
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
        raise OnlineTruthGuardEvidenceError(str(exc)) from exc
    stderr_audit = _validate_stderr(binding.stderr_path, context)
    publication_main = float(
        stages["module_publication_bus"]["wall_time_s"]
    )
    publication_finalize = float(
        stages["module_publication_bus_finalize"]["wall_time_s"]
    )
    metrics = {
        "module_publication_bus_wall_s": publication_main,
        "module_publication_bus_finalize_wall_s": publication_finalize,
        "module_publication_bus_total_wall_s": (
            publication_main + publication_finalize
        ),
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
        "d1_fusion_wall_s": stages["d1_fusion"]["wall_time_s"],
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
            "truth_guard_diagnostics": diagnostics["schema_version"],
        },
        "input_file_sha256": input_sha256,
    }
    if not artifact_provenance["passed"]:
        raise OnlineTruthGuardEvidenceError(
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
            governance
        ),
        "finite_state": summary["finite_state"],
        "online_truth_use_count": summary["online_truth_use_count"],
        "online_message_count": online_message_count,
        "implementation_identity_passed": True,
        "truth_guard_diagnostics": diagnostics,
        "truth_guard_audit": audit,
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
    pair: OnlineTruthGuardPairBinding,
    binding: OnlineTruthGuardArmBinding,
    expected_commit: str,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> Mapping[str, Any]:
    context = f"{pair.case_id} {binding.arm}"
    if manifest.get("git_commit") != expected_commit:
        raise OnlineTruthGuardEvidenceError(
            f"{context} source commit mismatch"
        )
    if manifest.get("repository_dirty") is not False:
        raise OnlineTruthGuardEvidenceError(
            f"{context} repository is dirty"
        )
    if manifest.get("config_sha256") != _base._canonical_sha256(config):
        raise OnlineTruthGuardEvidenceError(
            f"{context} config_sha256 mismatch"
        )
    runtime_profile = _required_mapping(
        manifest.get("runtime_profile"),
        f"{context} runtime_profile",
    )
    if manifest.get("runtime_profile_sha256") != _base._canonical_sha256(
        runtime_profile
    ):
        raise OnlineTruthGuardEvidenceError(
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
            raise OnlineTruthGuardEvidenceError(
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
        raise OnlineTruthGuardEvidenceError(
            f"{context} finite_state must be true"
        )
    if summary.get("online_truth_use_count") != 0:
        raise OnlineTruthGuardEvidenceError(
            f"{context} online_truth_use_count must be zero"
        )
    if governance.get("online_truth_use_count") != 0:
        raise OnlineTruthGuardEvidenceError(
            f"{context} governance online truth count must be zero"
        )
    return runtime_profile


def _validate_truth_guard_identity(
    *,
    arm: str,
    expected: str,
    runtime_profile: Mapping[str, Any],
    summary: Mapping[str, Any],
    online_message_count: int,
    context: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    selectors = {
        "manifest.runtime_profile": runtime_profile.get(
            "online_truth_guard_implementation"
        ),
        "summary": summary.get("online_truth_guard_implementation"),
    }
    mismatches = [
        f"{name}={value!r}"
        for name, value in selectors.items()
        if value != expected
    ]
    if mismatches:
        raise OnlineTruthGuardEvidenceError(
            f"{context} implementation identity mismatch: "
            + ", ".join(mismatches)
        )
    diagnostics = _required_mapping(
        summary.get("online_truth_guard_diagnostics"),
        f"{context} truth-guard diagnostics",
    )
    if set(diagnostics) != {
        "schema_version",
        "implementation",
        "candidate_enabled",
        "validation_count",
    }:
        raise OnlineTruthGuardEvidenceError(
            f"{context} truth-guard diagnostics fields mismatch"
        )
    _expect(
        diagnostics.get("schema_version"),
        ONLINE_TRUTH_GUARD_DIAGNOSTICS_SCHEMA_VERSION,
        f"{context} diagnostics schema",
    )
    _expect(
        diagnostics.get("implementation"),
        expected,
        f"{context} diagnostics implementation",
    )
    expected_candidate = arm == _CANDIDATE_ARM
    if diagnostics.get("candidate_enabled") is not expected_candidate:
        raise OnlineTruthGuardEvidenceError(
            f"{context} diagnostics candidate_enabled mismatch"
        )
    validation_count = _nonnegative_integer(
        diagnostics.get("validation_count"),
        f"{context} validation_count",
    )
    if validation_count <= 0:
        raise OnlineTruthGuardEvidenceError(
            f"{context} validation_count must be positive"
        )
    if validation_count != online_message_count:
        raise OnlineTruthGuardEvidenceError(
            f"{context} validation_count does not equal message_count"
        )
    normalized = {
        "schema_version": diagnostics["schema_version"],
        "implementation": diagnostics["implementation"],
        "candidate_enabled": diagnostics["candidate_enabled"],
        "validation_count": validation_count,
    }
    return normalized, {
        "passed": True,
        "implementation_identity_passed": True,
        "diagnostics_schema_passed": True,
        "candidate_flag_passed": True,
        "validation_conservation_passed": True,
        "validation_count": validation_count,
        "message_count": online_message_count,
    }


def _normalized_runtime_profile(
    runtime_profile: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(runtime_profile))
    if "online_truth_guard_implementation" not in normalized:
        raise OnlineTruthGuardEvidenceError(
            "normalized runtime profile lacks truth-guard selector"
        )
    normalized["online_truth_guard_implementation"] = _TREATMENT_MARKER
    return normalized


def _normalized_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(summary))
    for field in (
        "episode_id",
        "wall_time_s",
        "real_time_factor",
        "online_truth_guard_implementation",
        "online_truth_guard_diagnostics",
    ):
        if field not in normalized:
            raise OnlineTruthGuardEvidenceError(
                f"normalized summary lacks {field}"
            )
    normalized["episode_id"] = _TREATMENT_DERIVED_ID_MARKER
    normalized["wall_time_s"] = _PERFORMANCE_MARKER
    normalized["real_time_factor"] = _PERFORMANCE_MARKER
    normalized["online_truth_guard_implementation"] = _TREATMENT_MARKER
    normalized["online_truth_guard_diagnostics"] = {
        "value": _TREATMENT_MARKER
    }
    final = normalized.get("module_final_diagnostics")
    if not isinstance(final, dict):
        raise OnlineTruthGuardEvidenceError(
            "normalized summary lacks mutable module_final_diagnostics"
        )
    if "stage_timings" not in final:
        raise OnlineTruthGuardEvidenceError(
            "normalized summary lacks final stage_timings"
        )
    final["stage_timings"] = _PERFORMANCE_MARKER
    return normalized


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
        raise OnlineTruthGuardEvidenceError(
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
                "truth_guard_selector_diagnostics_performance_and_"
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
        "truth_guard_audit_pass_count": sum(
            bool(pair["truth_guard_audit_passed"]) for pair in ordered
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
        raise OnlineTruthGuardEvidenceError(str(exc)) from exc
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


def _admission_gates(
    pairs: Sequence[Mapping[str, Any]],
    groups: Mapping[str, Any],
    thresholds: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    pair_count = len(pairs)
    short_bus = groups["short"]["metrics"][
        "module_publication_bus_total_wall_s"
    ]
    long_bus = groups["long"]["metrics"][
        "module_publication_bus_total_wall_s"
    ]
    short_core = groups["short"]["metrics"]["core_wall_s"]
    long_core = groups["long"]["metrics"]["core_wall_s"]
    short_d1 = groups["short"]["metrics"]["d1_fusion_wall_s"]
    long_d1 = groups["long"]["metrics"]["d1_fusion_wall_s"]
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
    audit_count = sum(
        bool(pair["truth_guard_audit_passed"]) for pair in pairs
    )
    artifact_provenance_count = sum(
        bool(pair["artifact_provenance_passed"]) for pair in pairs
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
    rss_mean_increase_pct = max(
        summary["raw_relative_change"]["mean"] * 100.0
        for summary in rss_groups
    )
    any_pair_rss_increase_pct = max(
        float(
            pair["performance"]["maximum_rss_kib"][
                "raw_relative_change_pct"
            ]
        )
        for pair in pairs
    )
    gates = {
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
        "all_pairs_truth_guard_audit_valid": _gate(
            audit_count,
            pair_count,
            "==",
            audit_count == pair_count,
            "one_or_more_pair_truth_guard_audit_failed",
        ),
        "all_pairs_artifact_provenance_complete": _gate(
            artifact_provenance_count,
            pair_count,
            "==",
            artifact_provenance_count == pair_count,
            "one_or_more_pair_artifact_provenance_incomplete",
        ),
        "required_performance_metrics_available": _gate(
            required_metric_count,
            pair_count,
            "==",
            required_metric_count == pair_count,
            "one_or_more_required_performance_metrics_unavailable",
        ),
        "short_minimum_candidate_faster_count": _gate(
            short_bus["candidate_better_count"],
            thresholds["short_minimum_candidate_faster_count"],
            ">=",
            short_bus["candidate_better_count"]
            >= thresholds["short_minimum_candidate_faster_count"],
            "short_candidate_faster_count_below_threshold",
        ),
        "short_minimum_publication_bus_improvement_pct": _gate(
            short_bus["improvement_pct"]["mean"],
            thresholds[
                "short_minimum_publication_bus_improvement_pct"
            ],
            ">=",
            short_bus["improvement_pct"]["mean"]
            >= thresholds[
                "short_minimum_publication_bus_improvement_pct"
            ],
            "short_publication_bus_improvement_below_threshold",
            unit="pct",
        ),
        "short_bootstrap_relative_change_upper_bound_pct": _gate(
            short_bus["raw_relative_change"]["bootstrap_95_ci"]["upper"]
            * 100.0,
            thresholds[
                "short_bootstrap_relative_change_upper_bound_pct"
            ],
            "<",
            short_bus["raw_relative_change"]["bootstrap_95_ci"]["upper"]
            * 100.0
            < thresholds[
                "short_bootstrap_relative_change_upper_bound_pct"
            ],
            "short_bootstrap_upper_bound_not_below_zero",
            unit="pct",
        ),
        "long_minimum_candidate_faster_count": _gate(
            long_bus["candidate_better_count"],
            thresholds["long_minimum_candidate_faster_count"],
            ">=",
            long_bus["candidate_better_count"]
            >= thresholds["long_minimum_candidate_faster_count"],
            "long_candidate_faster_count_below_threshold",
        ),
        "long_minimum_publication_bus_improvement_pct": _gate(
            long_bus["improvement_pct"]["mean"],
            thresholds[
                "long_minimum_publication_bus_improvement_pct"
            ],
            ">=",
            long_bus["improvement_pct"]["mean"]
            >= thresholds[
                "long_minimum_publication_bus_improvement_pct"
            ],
            "long_publication_bus_improvement_below_threshold",
            unit="pct",
        ),
        "long_bootstrap_relative_change_upper_bound_pct": _gate(
            long_bus["raw_relative_change"]["bootstrap_95_ci"]["upper"]
            * 100.0,
            thresholds[
                "long_bootstrap_relative_change_upper_bound_pct"
            ],
            "<",
            long_bus["raw_relative_change"]["bootstrap_95_ci"]["upper"]
            * 100.0
            < thresholds[
                "long_bootstrap_relative_change_upper_bound_pct"
            ],
            "long_bootstrap_upper_bound_not_below_zero",
            unit="pct",
        ),
        "short_minimum_core_wall_improvement_pct": _gate(
            short_core["improvement_pct"]["mean"],
            thresholds["short_minimum_core_wall_improvement_pct"],
            ">=",
            short_core["improvement_pct"]["mean"]
            >= thresholds[
                "short_minimum_core_wall_improvement_pct"
            ],
            "short_core_wall_improvement_below_threshold",
            unit="pct",
        ),
        "long_minimum_core_wall_improvement_pct": _gate(
            long_core["improvement_pct"]["mean"],
            thresholds["long_minimum_core_wall_improvement_pct"],
            ">=",
            long_core["improvement_pct"]["mean"]
            >= thresholds[
                "long_minimum_core_wall_improvement_pct"
            ],
            "long_core_wall_improvement_below_threshold",
            unit="pct",
        ),
        "maximum_short_d1_fusion_mean_increase_pct": _gate(
            short_d1["raw_relative_change"]["mean"] * 100.0,
            thresholds[
                "maximum_short_d1_fusion_mean_increase_pct"
            ],
            "<=",
            short_d1["raw_relative_change"]["mean"] * 100.0
            <= thresholds[
                "maximum_short_d1_fusion_mean_increase_pct"
            ],
            "short_d1_fusion_increase_above_threshold",
            unit="pct",
        ),
        "maximum_long_d1_fusion_mean_increase_pct": _gate(
            long_d1["raw_relative_change"]["mean"] * 100.0,
            thresholds[
                "maximum_long_d1_fusion_mean_increase_pct"
            ],
            "<=",
            long_d1["raw_relative_change"]["mean"] * 100.0
            <= thresholds[
                "maximum_long_d1_fusion_mean_increase_pct"
            ],
            "long_d1_fusion_increase_above_threshold",
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
    }
    return gates


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


def write_online_truth_guard_multiseed_report(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write deterministic D6 products outside the raw evidence root."""

    if result.get("schema_version") != (
        ONLINE_TRUTH_GUARD_MULTISEED_EVALUATION_SCHEMA_VERSION
    ):
        raise ValueError("unsupported online truth-guard evaluation schema")
    contract = _required_mapping(
        result.get("input_contract"), "report input contract"
    )
    evidence_root = Path(str(contract["output_root"])).resolve()
    directory = Path(output_dir).expanduser().resolve()
    if _base._path_is_within(directory, evidence_root):
        raise ValueError(
            "independent D6 output must be outside the raw evidence root"
        )
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "evaluation_json": directory
        / "online_truth_guard_multiseed_evaluation.json",
        "compact_json": directory
        / "online_truth_guard_multiseed_compact.json",
        "pairs_csv": directory
        / "online_truth_guard_multiseed_pairs.csv",
        "markdown": directory
        / "ONLINE_TRUTH_GUARD_MULTISEED_REPORT_CN.md",
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
        render_online_truth_guard_multiseed_markdown(result),
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
            ONLINE_TRUTH_GUARD_MULTISEED_COMPACT_SCHEMA_VERSION
        ),
        "evaluation_schema_version": result["schema_version"],
        "evaluation_date": result["evaluation_date"],
        "input_contract": result["input_contract"],
        "scope": result["scope"],
        "groups": result["groups"],
        "admission_gates": result["admission_gates"],
        "optimization_admitted": result["optimization_admitted"],
        "system_realtime_gate": result["system_realtime_gate"],
        "system_realtime_gap_closed": result[
            "system_realtime_gap_closed"
        ],
    }


def render_online_truth_guard_multiseed_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the formal Chinese paired-admission report."""

    contract = _required_mapping(
        result["input_contract"], "report input contract"
    )
    groups = _required_mapping(result["groups"], "report groups")
    gates = _required_mapping(
        result["admission_gates"], "report admission gates"
    )
    realtime = _required_mapping(
        result["system_realtime_gate"], "report realtime gate"
    )
    lines = [
        "# 在线真值递归检查同提交多种子评估",
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
            "每臂 10 秒；共 13 pair、26 个 fresh arm。"
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
        (
            "module_publication_bus_total_wall_s",
            "发布总线及收尾墙钟",
            "improvement",
        ),
        ("core_wall_s", "核心墙钟", "improvement"),
        ("external_elapsed_s", "外层耗时", "improvement"),
        ("real_time_factor", "实时因子", "improvement"),
        ("d1_fusion_wall_s", "D1 融合墙钟", "raw"),
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
            "D1、D2 和内存采用 `(候选-参考)/参考`，负值表示下降。"
            "发布总线、核心墙钟、外层耗时和实时因子使用正向改善口径。",
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
            "| case | 发布总线改善 | 核心改善 | D1 增幅 | D2 增幅 | "
            "RSS 增幅 | 检查数守恒 | 语义 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for pair in result["pairs"]:
        performance = pair["performance"]
        conservation = (
            pair["reference"]["truth_guard_audit"][
                "validation_conservation_passed"
            ]
            and pair["candidate"]["truth_guard_audit"][
                "validation_conservation_passed"
            ]
        )
        lines.append(
            f"| {pair['case_id']} | "
            f"{_fmt(performance['module_publication_bus_total_wall_s']['improvement_pct'])}% | "
            f"{_fmt(performance['core_wall_s']['improvement_pct'])}% | "
            f"{_fmt(performance['d1_fusion_wall_s']['raw_relative_change_pct'])}% | "
            f"{_fmt(performance['d2_association_wall_s']['raw_relative_change_pct'])}% | "
            f"{_fmt(performance['maximum_rss_kib']['raw_relative_change_pct'])}% | "
            f"{'通过' if conservation else '失败'} | "
            f"{'通过' if pair['business_semantics_passed'] else '失败'} |"
        )
    lines.extend(
        [
            "",
            "## 边界",
            "",
            (
                "D6 只归一化预注册的检查实现、对应诊断、性能字段和由处理差异"
                "派生的 episode 标识。在线消息、D1/D2 航迹、关联、分配、控制"
                "计数、治理字段、计划谱系和离线真值制品继续逐对比较。"
            ),
            (
                "每个 arm 的诊断检查数必须与在线消息文件的非空记录数相等。"
                "缺字段、旧 schema、非 clean commit、reused arm、路径越界、"
                "摘要不一致或任一真值使用计数非零均失败关闭。"
            ),
            "",
            "## 制品",
            "",
            "- `online_truth_guard_multiseed_evaluation.json`：完整评估。",
            "- `online_truth_guard_multiseed_compact.json`：紧凑汇总。",
            "- `online_truth_guard_multiseed_pairs.csv`：逐 pair 数据。",
            "- `ONLINE_TRUTH_GUARD_MULTISEED_REPORT_CN.md`：中文报告。",
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
        "truth_guard_audit_passed",
        "artifact_provenance_passed",
        "reference_message_count",
        "reference_validation_count",
        "candidate_message_count",
        "candidate_validation_count",
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
                "truth_guard_audit_passed": pair[
                    "truth_guard_audit_passed"
                ],
                "artifact_provenance_passed": pair[
                    "artifact_provenance_passed"
                ],
                "reference_message_count": pair["reference"][
                    "online_message_count"
                ],
                "reference_validation_count": pair["reference"][
                    "truth_guard_audit"
                ]["validation_count"],
                "candidate_message_count": pair["candidate"][
                    "online_message_count"
                ],
                "candidate_validation_count": pair["candidate"][
                    "truth_guard_audit"
                ]["validation_count"],
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
        raise OnlineTruthGuardEvidenceError(str(exc)) from exc
    try:
        with path.open("r", encoding="utf-8") as stream:
            return sum(1 for line in stream if line.strip())
    except OSError as exc:
        raise OnlineTruthGuardEvidenceError(
            f"unable to count JSONL records in {path}: {exc}"
        ) from exc


def _load_stage(path: Path, stage_name: str) -> dict[str, Any]:
    try:
        return _base._load_stage(path, stage_name)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise OnlineTruthGuardEvidenceError(str(exc)) from exc


def _load_resource_metrics(path: Path) -> dict[str, float | int]:
    try:
        return _base._load_resource_metrics(path)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise OnlineTruthGuardEvidenceError(str(exc)) from exc


def _validate_stderr(path: Path, context: str) -> dict[str, Any]:
    try:
        return _base._validate_stderr(path, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise OnlineTruthGuardEvidenceError(str(exc)) from exc


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
        raise OnlineTruthGuardEvidenceError(str(exc)) from exc


def _load_mapping(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        return _base._load_strict_json_mapping(path)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise OnlineTruthGuardEvidenceError(str(exc)) from exc


def _required_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OnlineTruthGuardEvidenceError(
            f"{context} must be a mapping"
        )
    return value


def _required_sequence(value: Any, context: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise OnlineTruthGuardEvidenceError(
            f"{context} must be a sequence"
        )
    return value


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OnlineTruthGuardEvidenceError(
            f"{context} must be non-empty text"
        )
    return value


def _required_commit(value: Any, context: str) -> str:
    try:
        return _base._required_commit(value, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise OnlineTruthGuardEvidenceError(str(exc)) from exc


def _required_sha256(value: Any, context: str) -> str:
    try:
        return _base._required_sha256(value, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise OnlineTruthGuardEvidenceError(str(exc)) from exc


def _explicit_path(
    value: Any,
    context: str,
    *,
    require: str | None,
) -> Path:
    try:
        return _base._explicit_path(value, context, require=require)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise OnlineTruthGuardEvidenceError(str(exc)) from exc


def _require_under_root(path: Path, root: Path, context: str) -> None:
    try:
        _base._require_under_root(path, root, context)
    except _base.D1PublicationMetadataEvidenceError as exc:
        raise OnlineTruthGuardEvidenceError(str(exc)) from exc


def _expect(actual: Any, expected: Any, context: str) -> None:
    if actual != expected:
        raise OnlineTruthGuardEvidenceError(
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
        raise OnlineTruthGuardEvidenceError(
            f"{context} mismatch: expected {expected!r}, got {actual!r}"
        )


def _nonnegative_integer(value: Any, context: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise OnlineTruthGuardEvidenceError(
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
        raise OnlineTruthGuardEvidenceError(
            f"{case_id} seed must be an integer"
        )
    duration = case.get("duration_s")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(float(duration))
        or float(duration) <= 0.0
    ):
        raise OnlineTruthGuardEvidenceError(
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
            "Evaluate the frozen online truth-guard same-commit matrix"
        )
    )
    parser.add_argument(
        "--evidence-manifest",
        required=True,
        help="completed online truth-guard evidence_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="independent compact D6 output directory",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = evaluate_online_truth_guard_multiseed(
        args.evidence_manifest
    )
    paths = write_online_truth_guard_multiseed_report(
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
    return 0


__all__ = [
    "CANDIDATE_IMPLEMENTATION",
    "ONLINE_TRUTH_GUARD_DIAGNOSTICS_SCHEMA_VERSION",
    "ONLINE_TRUTH_GUARD_EVALUATION_DATE",
    "ONLINE_TRUTH_GUARD_EVIDENCE_SCHEMA_VERSION",
    "ONLINE_TRUTH_GUARD_EXPERIMENT_ID",
    "ONLINE_TRUTH_GUARD_MATRIX_SCHEMA_VERSION",
    "ONLINE_TRUTH_GUARD_MATRIX_SHA256",
    "ONLINE_TRUTH_GUARD_MULTISEED_COMPACT_SCHEMA_VERSION",
    "ONLINE_TRUTH_GUARD_MULTISEED_EVALUATION_SCHEMA_VERSION",
    "ONLINE_TRUTH_GUARD_SOURCE_COMMIT",
    "OnlineTruthGuardEvidence",
    "OnlineTruthGuardEvidenceError",
    "REFERENCE_IMPLEMENTATION",
    "evaluate_online_truth_guard_multiseed",
    "load_online_truth_guard_evidence_manifest",
    "main",
    "render_online_truth_guard_multiseed_markdown",
    "write_online_truth_guard_multiseed_report",
]
