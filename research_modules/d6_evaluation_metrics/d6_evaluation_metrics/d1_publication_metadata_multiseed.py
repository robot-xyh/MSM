"""Strict read-only D1 publication-metadata same-commit multi-seed evaluation.

The producer owns execution and persists a preregistered 13-pair evidence
manifest.  D6 independently validates that manifest, reads every episode from
disk, compares business semantics, and reports paired performance.  This
module never mutates an episode, evidence manifest, runtime bus, or control
artifact.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import re
from statistics import fmean, median
import sys
from typing import Any, Mapping, Sequence

import numpy as np

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from research_modules.scalable_3d_simulation.cross_build_equivalence import (
    CROSS_BUILD_EQUIVALENCE_SCHEMA_VERSION,
    compare_cross_build_episodes,
)


D1_PUBLICATION_METADATA_MULTISEED_EVALUATION_SCHEMA_VERSION = (
    "d6.d1_publication_metadata_multiseed_evaluation.v1"
)
D1_PUBLICATION_METADATA_MULTISEED_AGGREGATE_SCHEMA_VERSION = (
    "d6.d1_publication_metadata_multiseed_aggregate.v1"
)
D1_PUBLICATION_METADATA_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-publication-metadata-multiseed-evidence-v1"
)
D1_PUBLICATION_METADATA_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-publication-metadata-multiseed-matrix-v1"
)
D1_PUBLICATION_METADATA_EXPERIMENT_ID = "d1-publication-metadata-multiseed-20260724-v1"
D1_PUBLICATION_METADATA_MATRIX_SHA256 = (
    "2517b2ac22b8e2b39e5642b0b510419e1e7f9fa18d26f1f682b8330086ee5f2f"
)
D1_PUBLICATION_METADATA_EVALUATION_DATE = "2026-07-24"
D1_PUBLICATION_METADATA_SOURCE_COMMIT = (
    "a36f519ed954a9ba8bdc3fe149ba2835da290c39"
)
D1_PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION = "per_track_copy_v1"
D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION = "immutable_shared_v1"
D1_PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION_ID = (
    "d1.publication_metadata.per_track_audit_copy.v1"
)
D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION_ID = (
    "d1.publication_metadata.immutable_shared_audit.v1"
)
D1_PUBLICATION_METADATA_BOOTSTRAP_RESAMPLES = 10_000
D1_PUBLICATION_METADATA_BOOTSTRAP_RNG_SEED = 20_260_724
D1_PUBLICATION_METADATA_SHORT_SEEDS = tuple(range(1101, 1111))
D1_PUBLICATION_METADATA_LONG_SEEDS = tuple(range(1101, 1104))
D1_PUBLICATION_METADATA_SHORT_DURATION_S = 2.2
D1_PUBLICATION_METADATA_LONG_DURATION_S = 10.0
D1_PUBLICATION_METADATA_TARGET_COUNT = 200
D1_PUBLICATION_METADATA_RESOURCE_COUNT = 200
D1_PUBLICATION_METADATA_RECON_COUNT = 2
D1_PUBLICATION_METADATA_STAGE = "module.d1_fusion"

_REFERENCE_ARM = "reference"
_CANDIDATE_ARM = "candidate"
_ARMS = (_REFERENCE_ARM, _CANDIDATE_ARM)
_GROUPS = ("short", "long")
_IMPLEMENTATIONS = {
    _REFERENCE_ARM: D1_PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION,
    _CANDIDATE_ARM: D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION,
}
_IMPLEMENTATION_IDS = {
    _REFERENCE_ARM: D1_PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION_ID,
    _CANDIDATE_ARM: D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION_ID,
}
_RUN_FLAGS = (
    "--integrated-stack",
    "--d1-d2-structural-ambiguity-hold",
)
_EXPECTED_GATES = {
    "all_pairs_business_semantics_equal": True,
    "all_pairs_finite_state": True,
    "all_pairs_online_truth_use_count": 0,
    "all_pairs_explicit_implementation_identity": True,
    "short_minimum_candidate_faster_count": 8,
    "short_minimum_d1_fusion_improvement_pct": 10.0,
    "short_bootstrap_relative_change_upper_bound_pct": 0.0,
    "long_minimum_candidate_faster_count": 2,
    "long_minimum_d1_fusion_improvement_pct": 10.0,
    "short_minimum_core_wall_improvement_pct": 5.0,
    "long_minimum_core_wall_improvement_pct": 5.0,
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
        "d1_publication_metadata_implementation"
    ),
    "reference_implementation": D1_PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION,
    "candidate_implementation": D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION,
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
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RESOURCE_PATTERNS = {
    "external_elapsed_s": re.compile(
        r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*(\S+)"
    ),
    "maximum_rss_kib": re.compile(
        r"Maximum resident set size \(kbytes\):\s*(\d+)"
    ),
    "process_exit_status": re.compile(r"Exit status:\s*(-?\d+)"),
}
_STAGE_TIMING_SCHEMA_VERSION = "scalable3d-stage-timings-v2"
_PERFORMANCE_MARKER = "D6_ALLOWED_PERFORMANCE_DIAGNOSTIC"
_IMPLEMENTATION_MARKER = "D6_PREREGISTERED_PUBLICATION_METADATA_TREATMENT"
_TREATMENT_DERIVED_ID_MARKER = "D6_TREATMENT_DERIVED_EPISODE_ID"
_ALLOWED_STDERR = (
    "/home/linux/.local/lib/python3.12/site-packages/matplotlib/"
    "projections/__init__.py:63: UserWarning: Unable to import Axes3D. "
    "This may be due to multiple versions of Matplotlib being installed "
    "(e.g. as a system package and as a pip package). As a result, the 3D "
    "projection is not available.\n"
    '  warnings.warn("Unable to import Axes3D. This may be due to multiple '
    'versions of "\n'
)
_METRICS = (
    "d1_fusion_wall_s",
    "d1_fusion_p50_ms",
    "d1_fusion_p95_ms",
    "d1_fusion_max_ms",
    "d1_scan_input_wall_s",
    "d2_association_wall_s",
    "d3_assignment_wall_s",
    "d5_active_vision_wall_s",
    "d7_guidance_wall_s",
    "module_publication_bus_wall_s",
    "core_wall_s",
    "external_elapsed_s",
    "maximum_rss_kib",
    "real_time_factor",
)
_LOWER_IS_BETTER = {
    "d1_fusion_wall_s",
    "d1_fusion_p50_ms",
    "d1_fusion_p95_ms",
    "d1_fusion_max_ms",
    "d1_scan_input_wall_s",
    "d2_association_wall_s",
    "d3_assignment_wall_s",
    "d5_active_vision_wall_s",
    "d7_guidance_wall_s",
    "module_publication_bus_wall_s",
    "core_wall_s",
    "external_elapsed_s",
    "maximum_rss_kib",
}
_REQUIRED_ADMISSION_METRICS = {
    "d1_fusion_wall_s",
    "core_wall_s",
    "maximum_rss_kib",
}
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


class D1PublicationMetadataEvidenceError(ValueError):
    """Raised when persisted publication-metadata evidence violates the frozen contract."""


class _StrictJSONConstantError(ValueError):
    pass


class D1PublicationMetadataArmBinding:
    """One explicit persisted arm binding."""

    def __init__(
        self,
        *,
        arm: str,
        implementation: str,
        episode_dir: Path,
        resource_path: Path,
        stdout_path: Path,
        stderr_path: Path,
    ) -> None:
        self.arm = arm
        self.implementation = implementation
        self.episode_dir = episode_dir
        self.resource_path = resource_path
        self.stdout_path = stdout_path
        self.stderr_path = stderr_path


class D1PublicationMetadataPairBinding:
    """One seed/duration pair from the preregistered matrix."""

    def __init__(
        self,
        *,
        case_id: str,
        group: str,
        seed: int,
        duration_s: float,
        arm_order: tuple[str, str],
        arms: Mapping[str, D1PublicationMetadataArmBinding],
    ) -> None:
        self.case_id = case_id
        self.group = group
        self.seed = seed
        self.duration_s = duration_s
        self.arm_order = arm_order
        self.arms = dict(arms)


class D1PublicationMetadataEvidence:
    """Validated immutable bindings from one completed main evidence manifest."""

    def __init__(
        self,
        *,
        source_path: Path,
        source_sha256: str,
        matrix_path: Path,
        matrix_sha256: str,
        output_root: Path,
        source_commit: str,
        source_worktree: Path,
        pairs: Sequence[D1PublicationMetadataPairBinding],
    ) -> None:
        self.source_path = source_path
        self.source_sha256 = source_sha256
        self.matrix_path = matrix_path
        self.matrix_sha256 = matrix_sha256
        self.output_root = output_root
        self.source_commit = source_commit
        self.source_worktree = source_worktree
        self.pairs = tuple(pairs)


def load_d1_publication_metadata_evidence_manifest(
    source: str | Path,
) -> D1PublicationMetadataEvidence:
    """Validate the frozen matrix and all explicit evidence path bindings."""

    source_path = Path(source).expanduser().resolve()
    manifest, manifest_raw = _load_strict_json_mapping(source_path)
    _expect_equal(
        manifest.get("schema_version"),
        D1_PUBLICATION_METADATA_EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "evidence manifest schema_version",
    )
    _expect_equal(
        manifest.get("experiment_id"),
        D1_PUBLICATION_METADATA_EXPERIMENT_ID,
        "evidence manifest experiment_id",
    )
    if manifest.get("status") != "episodes_complete_pending_d6":
        raise D1PublicationMetadataEvidenceError(
            "evidence manifest status must be episodes_complete_pending_d6"
        )
    _required_text(
        manifest.get("completed_at_utc"),
        "evidence manifest completed_at_utc",
    )
    _expect_equal(
        manifest.get("required_d6_evaluator_schema_version"),
        D1_PUBLICATION_METADATA_MULTISEED_EVALUATION_SCHEMA_VERSION,
        "required D6 evaluator schema",
    )
    source_commit = _required_commit(
        manifest.get("source_commit"),
        "evidence manifest source_commit",
    )
    _expect_equal(
        source_commit,
        D1_PUBLICATION_METADATA_SOURCE_COMMIT,
        "evidence manifest frozen source_commit",
    )
    if manifest.get("source_repository_dirty") is not False:
        raise D1PublicationMetadataEvidenceError(
            "source_repository_dirty must be false"
        )
    source_worktree = _explicit_path(
        manifest.get("source_worktree"),
        "evidence manifest source_worktree",
        require=None,
    )
    output_root = _explicit_path(
        manifest.get("output_root"),
        "evidence manifest output_root",
        require="directory",
    )
    if source_path.parent != output_root:
        raise D1PublicationMetadataEvidenceError(
            "evidence_manifest.json must be directly under output_root"
        )

    matrix_path = _explicit_path(
        manifest.get("matrix_path"),
        "evidence manifest matrix_path",
        require="file",
    )
    matrix_sha256 = _required_sha256(
        manifest.get("matrix_sha256"),
        "evidence manifest matrix_sha256",
    )
    actual_matrix_sha256 = _file_sha256(matrix_path)
    if matrix_sha256 != actual_matrix_sha256:
        raise D1PublicationMetadataEvidenceError(
            "matrix_sha256 does not match matrix_path bytes"
        )
    if matrix_sha256 != D1_PUBLICATION_METADATA_MATRIX_SHA256:
        raise D1PublicationMetadataEvidenceError(
            "matrix_sha256 does not match the frozen D1 publication-metadata matrix"
        )
    matrix, _ = _load_strict_json_mapping(matrix_path)
    _validate_matrix(matrix)
    embedded_matrix = _required_mapping(
        manifest.get("matrix"),
        "evidence manifest embedded matrix",
    )
    if embedded_matrix != matrix:
        raise D1PublicationMetadataEvidenceError(
            "embedded matrix does not exactly match matrix_path"
        )

    raw_cases = _required_sequence(
        manifest.get("cases"),
        "evidence manifest cases",
    )
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise D1PublicationMetadataEvidenceError(
            "evidence manifest must contain exactly 13 cases"
        )
    pairs: list[D1PublicationMetadataPairBinding] = []
    used_paths: set[Path] = {source_path}
    for raw_case, expected in zip(raw_cases, _EXPECTED_CASES, strict=True):
        case = _required_mapping(raw_case, "evidence manifest case")
        case_metadata = _case_metadata(case)
        if case_metadata != expected:
            raise D1PublicationMetadataEvidenceError(
                "evidence case differs from preregistered order: "
                f"expected {expected!r}, got {case_metadata!r}"
            )
        case_id, group, seed, duration_s, arm_order = case_metadata
        if case.get("d6_evaluation_status") != (
            "episodes_complete_pending_d6"
        ):
            raise D1PublicationMetadataEvidenceError(
                f"{case_id} d6_evaluation_status is not pending D6"
            )
        raw_arms = _required_mapping(
            case.get("arms"),
            f"{case_id} arms",
        )
        if set(raw_arms) != set(_ARMS):
            raise D1PublicationMetadataEvidenceError(
                f"{case_id} arms must be reference and candidate"
            )
        arm_bindings: dict[str, D1PublicationMetadataArmBinding] = {}
        commands: dict[str, list[str]] = {}
        for arm in _ARMS:
            record = _required_mapping(
                raw_arms.get(arm),
                f"{case_id} {arm} arm",
            )
            _expect_equal(record.get("arm"), arm, f"{case_id} arm label")
            implementation = _IMPLEMENTATIONS[arm]
            _expect_equal(
                record.get("expected_implementation"),
                implementation,
                f"{case_id} {arm} expected implementation",
            )
            _expect_equal(
                record.get("expected_d1_implementation_id"),
                _IMPLEMENTATION_IDS[arm],
                f"{case_id} {arm} expected D1 implementation_id",
            )
            _expect_equal(
                record.get("expected_commit"),
                source_commit,
                f"{case_id} {arm} expected commit",
            )
            if record.get("status") != "complete":
                raise D1PublicationMetadataEvidenceError(
                    f"{case_id} {arm} status must be complete"
                )
            if (
                not isinstance(record.get("return_code"), int)
                or isinstance(record.get("return_code"), bool)
                or record.get("return_code") != 0
            ):
                raise D1PublicationMetadataEvidenceError(
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
                _require_under_root(path, output_root, f"{case_id} {arm} {label}")
            for path in (episode_dir, resource_path, stdout_path, stderr_path):
                if path in used_paths:
                    raise D1PublicationMetadataEvidenceError(
                        f"duplicate evidence path: {path}"
                    )
                used_paths.add(path)
            command = [
                _required_text(item, f"{case_id} {arm} command item")
                for item in _required_sequence(
                    record.get("command"),
                    f"{case_id} {arm} command",
                )
            ]
            expected_command = _expected_command(
                source_worktree=source_worktree,
                run_flags=tuple(matrix["run_flags"]),
                implementation=implementation,
                duration_s=duration_s,
                seed=seed,
                resource_count=D1_PUBLICATION_METADATA_RESOURCE_COUNT,
                target_count=D1_PUBLICATION_METADATA_TARGET_COUNT,
                recon_count=D1_PUBLICATION_METADATA_RECON_COUNT,
                episode_dir=episode_dir,
            )
            if command != expected_command:
                raise D1PublicationMetadataEvidenceError(
                    f"{case_id} {arm} command differs from frozen matrix"
                )
            commands[arm] = command
            arm_bindings[arm] = D1PublicationMetadataArmBinding(
                arm=arm,
                implementation=implementation,
                episode_dir=episode_dir,
                resource_path=resource_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        _validate_pair_command_isolation(commands, case_id)
        pairs.append(
            D1PublicationMetadataPairBinding(
                case_id=case_id,
                group=group,
                seed=seed,
                duration_s=duration_s,
                arm_order=arm_order,
                arms=arm_bindings,
            )
        )

    return D1PublicationMetadataEvidence(
        source_path=source_path,
        source_sha256=_sha256_bytes(manifest_raw),
        matrix_path=matrix_path,
        matrix_sha256=matrix_sha256,
        output_root=output_root,
        source_commit=source_commit,
        source_worktree=source_worktree,
        pairs=pairs,
    )


def evaluate_d1_publication_metadata_multiseed(
    source: str | Path,
) -> dict[str, Any]:
    """Evaluate one complete 13-pair same-commit evidence manifest."""

    evidence = load_d1_publication_metadata_evidence_manifest(source)
    pairs = [_evaluate_pair(pair, evidence) for pair in evidence.pairs]
    groups = {
        group: _summarize_group(
            [pair for pair in pairs if pair["group"] == group],
            group=group,
        )
        for group in _GROUPS
    }
    gates = _admission_gates(pairs, groups)
    admitted = all(gate["passed"] for gate in gates.values())
    realtime_gate = _system_realtime_gate(pairs)
    return {
        "schema_version": D1_PUBLICATION_METADATA_MULTISEED_EVALUATION_SCHEMA_VERSION,
        "evaluation_date": D1_PUBLICATION_METADATA_EVALUATION_DATE,
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "input_contract": {
            "evidence_manifest_path": str(evidence.source_path),
            "evidence_manifest_sha256": evidence.source_sha256,
            "evidence_manifest_schema_version": (
                D1_PUBLICATION_METADATA_EVIDENCE_MANIFEST_SCHEMA_VERSION
            ),
            "evidence_manifest_status": "episodes_complete_pending_d6",
            "matrix_path": str(evidence.matrix_path),
            "matrix_sha256": evidence.matrix_sha256,
            "matrix_schema_version": D1_PUBLICATION_METADATA_MATRIX_SCHEMA_VERSION,
            "experiment_id": D1_PUBLICATION_METADATA_EXPERIMENT_ID,
            "output_root": str(evidence.output_root),
            "source_commit": evidence.source_commit,
            "source_repository_dirty": False,
            "same_commit_for_both_arms": True,
            "arm_implementations": dict(_IMPLEMENTATIONS),
            "arm_implementation_ids": dict(_IMPLEMENTATION_IDS),
            "pair_count": len(pairs),
            "bootstrap_resamples": D1_PUBLICATION_METADATA_BOOTSTRAP_RESAMPLES,
            "bootstrap_rng_seed": D1_PUBLICATION_METADATA_BOOTSTRAP_RNG_SEED,
            "evidence_boundary": dict(_EXPECTED_BOUNDARY),
        },
        "scope": {
            "simulation_mode": "three_dimensional_point_mass",
            "airsim_evidence": False,
            "target_count": D1_PUBLICATION_METADATA_TARGET_COUNT,
            "resource_count": D1_PUBLICATION_METADATA_RESOURCE_COUNT,
            "recon_count": D1_PUBLICATION_METADATA_RECON_COUNT,
            "short_seeds": list(D1_PUBLICATION_METADATA_SHORT_SEEDS),
            "long_seeds": list(D1_PUBLICATION_METADATA_LONG_SEEDS),
            "short_duration_s": D1_PUBLICATION_METADATA_SHORT_DURATION_S,
            "long_duration_s": D1_PUBLICATION_METADATA_LONG_DURATION_S,
            "truth_is_online_control_input": False,
            "allowed_business_equivalence_differences": [
                "d1_publication_metadata_implementation_identity",
                "d1_publication_metadata_implementation_diagnostics",
                "d1_publication_metadata_operation_counts",
                "d1_association_innovation_solve_count",
                "treatment_derived_episode_id",
                "episode_wall_time_s",
                "episode_real_time_factor",
                "module_final_stage_timings",
                "runtime_profile_sha256",
                "stage_timing",
                "external_elapsed",
                "maximum_rss",
                "opaque_plan_id_with_lineage_preserved",
                "verified_content_address_reencoding",
            ],
        },
        "thresholds": dict(_EXPECTED_GATES),
        "pairs": pairs,
        "groups": groups,
        "cross_module_attribution": _cross_module_attribution(groups),
        "admission_gates": gates,
        "d1_optimization_admitted": admitted,
        "system_realtime_gate": realtime_gate,
        "system_realtime_gap_closed": realtime_gate["passed"],
    }


def _cross_module_attribution(
    groups: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "observed_stage_effects": {
            group: {
                metric: {
                    "paired_relative_change_mean": groups[group]["metrics"][
                        metric
                    ]["raw_relative_change"]["mean"],
                    "ratio_of_group_means_raw_relative_change": groups[group][
                        "metrics"
                    ][metric]["ratio_of_group_means"][
                        "raw_relative_change"
                    ],
                }
                for metric in (
                    "d1_fusion_wall_s",
                    "d2_association_wall_s",
                    "core_wall_s",
                )
            }
            for group in _GROUPS
        },
        "source_level_mechanism": {
            "status": "confirmed_by_read_only_source_inspection",
            "consumer": "D2 assert_online_metadata_batch_truth_free",
            "condition": (
                "_is_trusted_builtin_metadata_tree accepts exact built-in "
                "containers; immutable shared mapping/list wrappers are not "
                "eligible for equivalent-value reuse"
            ),
            "effect": (
                "candidate shared audit subtrees are recursively scanned per "
                "GlobalTrack, increasing D2 association cost"
            ),
        },
        "admission_effect": (
            "cross-module D2 regression is reflected in the preregistered "
            "short/long core-wall gates"
        ),
    }


def write_d1_publication_metadata_multiseed_report(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write evaluation products outside the source evidence root."""

    if result.get("schema_version") != (
        D1_PUBLICATION_METADATA_MULTISEED_EVALUATION_SCHEMA_VERSION
    ):
        raise ValueError("unsupported D1 publication-metadata evaluation schema")
    input_contract = _required_mapping(
        result.get("input_contract"),
        "evaluation input_contract",
    )
    evidence_root = Path(
        _required_text(
            input_contract.get("output_root"),
            "evaluation evidence output_root",
        )
    ).expanduser().resolve()
    directory = Path(output_dir).expanduser().resolve()
    if _path_is_within(directory, evidence_root):
        raise ValueError(
            "report output_dir must be independent of the evidence root"
        )
    directory.mkdir(parents=True, exist_ok=True)
    evaluation_path = directory / "d1_publication_metadata_multiseed_evaluation.json"
    aggregate_path = directory / "d1_publication_metadata_multiseed_aggregate.json"
    csv_path = directory / "d1_publication_metadata_multiseed_pairs.csv"
    markdown_path = directory / "D1_PUBLICATION_METADATA_MULTISEED_EVALUATION_CN.md"
    plot_path = directory / "d1_publication_metadata_multiseed_improvement_curve.png"
    evaluation_path.write_text(
        _json_text(result),
        encoding="utf-8",
    )
    aggregate = _aggregate_output(result)
    aggregate_path.write_text(_json_text(aggregate), encoding="utf-8")
    _write_pair_csv(result, csv_path)
    markdown_path.write_text(
        render_d1_publication_metadata_multiseed_markdown(result),
        encoding="utf-8",
    )
    _write_improvement_plot(result, plot_path)
    return {
        "evaluation_json": evaluation_path,
        "aggregate_json": aggregate_path,
        "pairs_csv": csv_path,
        "markdown": markdown_path,
        "plot_png": plot_path,
    }


def render_d1_publication_metadata_multiseed_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the independent Chinese admission report."""

    admitted = bool(result.get("d1_optimization_admitted"))
    realtime = bool(result.get("system_realtime_gap_closed"))
    contract = _required_mapping(result.get("input_contract"), "input_contract")
    groups = _required_mapping(result.get("groups"), "groups")
    realtime_gate = _required_mapping(
        result.get("system_realtime_gate"),
        "system_realtime_gate",
    )
    pairs = _required_sequence(result.get("pairs"), "pairs")
    reference_operation_counts = [
        _required_mapping(
            _required_mapping(pair, "pair")["reference"][
                "publication_metadata_operation_counts"
            ],
            "reference operation counts",
        )
        for pair in pairs
    ]
    candidate_operation_counts = [
        _required_mapping(
            _required_mapping(pair, "pair")["candidate"][
                "publication_metadata_operation_counts"
            ],
            "candidate operation counts",
        )
        for pair in pairs
    ]
    reference_materialized = sum(
        int(item["global_track_metadata_materialization_count"])
        for item in reference_operation_counts
    )
    candidate_materialized = sum(
        int(item["global_track_metadata_materialization_count"])
        for item in candidate_operation_counts
    )
    reference_copies = sum(
        int(item.get("per_track_shared_audit_mapping_copy_count", 0))
        for item in reference_operation_counts
    )
    candidate_copies = sum(
        int(item.get("per_track_shared_audit_mapping_copy_count", 0))
        for item in candidate_operation_counts
    )
    candidate_reuse = sum(
        int(item.get("shared_audit_value_reuse_count", 0))
        for item in candidate_operation_counts
    )
    lines = [
        "# D1 航迹发布元数据多种子评估",
        "",
        "## 结论",
        "",
        (
            f"不可变共享审计元数据候选的正式准入结论为"
            f" **{'通过' if admitted else '不通过'}**。D6 只读取同一干净提交"
            "产生的 13 对三维质点 episode，不参与运行和控制。"
        ),
        (
            f"系统实时性缺口 **{'已关闭' if realtime else '未关闭'}**。"
            "候选臂最低实时因子为 "
            f"{_fmt(realtime_gate['candidate_minimum_real_time_factor'])}；"
            "该判定与 D1 局部优化结论分离。"
        ),
        "",
        "## 证据条件",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 源提交 | `{contract['source_commit']}` |",
        f"| 矩阵 SHA256 | `{contract['matrix_sha256']}` |",
        "| 规模 | 200 个目标、200 个资源、2 个侦察节点 |",
        "| 短时组 | seeds 1101-1110，每组 2.2 秒 |",
        "| 长时组 | seeds 1101-1103，每组 10 秒 |",
        "| 参考实现 | `per_track_copy_v1` |",
        "| 候选实现 | `immutable_shared_v1` |",
        "| bootstrap | 10000 次，随机种子 20260724 |",
        "",
        "## 实现操作数",
        "",
        "| 指标 | 参考 | 候选 |",
        "| --- | ---: | ---: |",
        f"| 完整元数据物化 | {reference_materialized} | {candidate_materialized} |",
        f"| 逐航迹共享审计映射复制 | {reference_copies} | {candidate_copies} |",
        f"| 共享审计值复用 | 0 | {candidate_reuse} |",
        "",
        "## D1 融合结果",
        "",
        "| 组别 | 参考均值/s | 候选均值/s | 均值比改善 | 逐对平均改善 | 候选更快 | 原始相对变化 95% 区间 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for group in _GROUPS:
        summary = groups[group]["metrics"]["d1_fusion_wall_s"]
        ci = summary["raw_relative_change"]["bootstrap_95_ci"]
        lines.append(
            f"| {'短时' if group == 'short' else '长时'} | "
            f"{_fmt(summary['reference']['mean'])} | "
            f"{_fmt(summary['candidate']['mean'])} | "
            f"{_fmt(summary['ratio_of_group_means']['improvement_pct'])}% | "
            f"{_fmt(summary['improvement_pct']['mean'])}% | "
            f"{summary['candidate_better_count']}/{summary['pair_count']} | "
            f"[{_fmt(ci['lower'] * 100.0)}, "
            f"{_fmt(ci['upper'] * 100.0)}]% |"
        )
    lines.extend(
        [
            "",
            "逐 pair 原始相对变化按 `(候选-参考)/参考` 计算。"
            "耗时和内存指标的正向改善为原始变化取负值。"
            "组均值采用逐 pair 相对变化的算术均值，置信区间以 seed pair 为重采样单位。",
            "",
            "## 系统阶段归因",
            "",
            "| 组别 | D1 融合改善 | D2 关联改善 | 核心墙钟改善 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for group in _GROUPS:
        metrics = groups[group]["metrics"]
        lines.append(
            f"| {'短时' if group == 'short' else '长时'} | "
            f"{_fmt(metrics['d1_fusion_wall_s']['ratio_of_group_means']['improvement_pct'])}% | "
            f"{_fmt(metrics['d2_association_wall_s']['ratio_of_group_means']['improvement_pct'])}% | "
            f"{_fmt(metrics['core_wall_s']['ratio_of_group_means']['improvement_pct'])}% |"
        )
    lines.extend(
        [
            "",
            "D1 融合阶段明显缩短，但 D2 关联阶段出现反向增长。"
            "只读源码核对确认，D2 的批量真值隔离审计只对精确的 Python "
            "内建容器启用等值代表复用；候选的只读映射和序列包装未通过该类型门，"
            "因此共享诊断树仍按每条 GlobalTrack 递归扫描。该跨模块代价已由"
            "短时和长时核心墙钟至少改善 5% 的预注册门反映，不能用 D1 局部收益绕过。",
            "",
            "## 语义审计",
            "",
            "| 组别 | 业务语义通过 | 有限状态 | 在线真值隔离 | 实现身份一致 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for group in _GROUPS:
        summary = groups[group]
        lines.append(
            f"| {'短时' if group == 'short' else '长时'} | "
            f"{summary['business_semantics_pass_count']}/{summary['pair_count']} | "
            f"{summary['finite_state_pass_count']}/{summary['pair_count']} | "
            f"{summary['truth_isolation_pass_count']}/{summary['pair_count']} | "
            f"{summary['implementation_identity_pass_count']}/{summary['pair_count']} |"
        )
    lines.extend(
        [
            "",
            "在线总线逐条比较保留 D3 计划版本和前序关系，"
            "并校验 D4 内容地址与确认消息来源。D2 身份连续性、ID switch、"
            "D5 终端输出和 D7 导引输出均保持比较。"
            "离线真值状态、真值标签和距离事件只用于等价审计，"
            "在线真值使用计数必须为零。",
            "",
            "## 准入门",
            "",
            "| 判据 | 结果 | 原因 |",
            "| --- | :---: | --- |",
        ]
    )
    for name, gate in result.get("admission_gates", {}).items():
        lines.append(
            f"| `{name}` | {'通过' if gate.get('passed') else '失败'} | "
            f"{gate.get('reason') or '-'} |"
        )
    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            "- 当前证据来自三维质点环境，不是 AirSim 或实机测试。",
            "- 候选实现未通过正式准入时，不能写成默认路径已获性能准入。",
            "- 墙钟、外部进程耗时、常驻内存和实时因子分层报告，未相加为单一指标。",
            "- 运行配置、性能诊断和所有已读取输入文件 SHA256 保留在完整评估 JSON 中。",
            "",
            "## 文件",
            "",
            "- `d1_publication_metadata_multiseed_evaluation.json`：完整逐 pair 证据和门限。",
            "- `d1_publication_metadata_multiseed_aggregate.json`：聚合结论。",
            "- `d1_publication_metadata_multiseed_pairs.csv`：逐 pair 指标。",
            "- `d1_publication_metadata_multiseed_improvement_curve.png`：短时和长时改善曲线。",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_matrix(matrix: Mapping[str, Any]) -> None:
    if set(matrix) != _EXPECTED_MATRIX_KEYS:
        raise D1PublicationMetadataEvidenceError(
            "matrix fields differ from the frozen contract"
        )
    _expect_equal(
        matrix.get("schema_version"),
        D1_PUBLICATION_METADATA_MATRIX_SCHEMA_VERSION,
        "matrix schema_version",
    )
    _expect_equal(
        matrix.get("experiment_id"),
        D1_PUBLICATION_METADATA_EXPERIMENT_ID,
        "matrix experiment_id",
    )
    _expect_equal(
        matrix.get("same_clean_commit_required"),
        True,
        "same_clean_commit_required",
    )
    for field, expected in (
        ("target_count", D1_PUBLICATION_METADATA_TARGET_COUNT),
        ("resource_count", D1_PUBLICATION_METADATA_RESOURCE_COUNT),
        ("recon_count", D1_PUBLICATION_METADATA_RECON_COUNT),
        ("bootstrap_seed", D1_PUBLICATION_METADATA_BOOTSTRAP_RNG_SEED),
        ("bootstrap_resamples", D1_PUBLICATION_METADATA_BOOTSTRAP_RESAMPLES),
    ):
        _expect_equal(matrix.get(field), expected, f"matrix {field}")
    _expect_finite_equal(matrix.get("cooldown_s"), 2.0, "matrix cooldown_s")
    _expect_equal(
        matrix.get("arm_implementations"),
        _IMPLEMENTATIONS,
        "matrix arm_implementations",
    )
    _expect_equal(
        tuple(_required_sequence(matrix.get("run_flags"), "matrix run_flags")),
        _RUN_FLAGS,
        "matrix run_flags",
    )
    _expect_equal(
        matrix.get("admission_gates"),
        _EXPECTED_GATES,
        "matrix admission_gates",
    )
    _expect_equal(
        matrix.get("evidence_boundary"),
        _EXPECTED_BOUNDARY,
        "matrix evidence_boundary",
    )
    raw_cases = _required_sequence(matrix.get("cases"), "matrix cases")
    actual_cases = tuple(
        _case_metadata(_required_mapping(case, "matrix case"))
        for case in raw_cases
    )
    _expect_equal(actual_cases, _EXPECTED_CASES, "matrix cases")


def _evaluate_pair(
    pair: D1PublicationMetadataPairBinding,
    evidence: D1PublicationMetadataEvidence,
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
    reference_materialized = int(
        reference["publication_metadata_operation_counts"][
            "global_track_metadata_materialization_count"
        ]
    )
    candidate_materialized = int(
        candidate["publication_metadata_operation_counts"][
            "global_track_metadata_materialization_count"
        ]
    )
    if reference_materialized != candidate_materialized:
        raise D1PublicationMetadataEvidenceError(
            f"{pair.case_id} full materialization counts differ"
        )
    semantic = _compare_pair_business_semantics(
        reference,
        candidate,
    )
    reference.pop("_semantic_input", None)
    candidate.pop("_semantic_input", None)
    performance = {
        metric: _compare_pair_metric(
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
        "business_semantics_passed": semantic["passed"],
        "finite_state_passed": (
            reference["finite_state"]
            and candidate["finite_state"]
        ),
        "truth_isolation_passed": (
            reference["online_truth_use_count"] == 0
            and candidate["online_truth_use_count"] == 0
        ),
        "implementation_identity_passed": (
            reference["implementation_identity_passed"]
            and candidate["implementation_identity_passed"]
        ),
        "performance": performance,
    }


def _evaluate_arm(
    binding: D1PublicationMetadataArmBinding,
    *,
    pair: D1PublicationMetadataPairBinding,
    expected_commit: str,
) -> dict[str, Any]:
    episode = binding.episode_dir
    stderr_audit = _validate_stderr(
        binding.stderr_path,
        f"{pair.case_id} {binding.arm}",
    )
    paths = {name: episode / name for name in _CONSUMED_EPISODE_FILES}
    for name, path in paths.items():
        if not path.is_file():
            raise D1PublicationMetadataEvidenceError(
                f"{pair.case_id} {binding.arm} missing {name}"
            )

    manifest, manifest_raw = _load_strict_json_mapping(paths["manifest.json"])
    config, config_raw = _load_strict_json_mapping(
        paths["scenario_config.json"]
    )
    summary, summary_raw = _load_strict_json_mapping(paths["summary.json"])
    governance, governance_raw = _load_strict_json_mapping(
        paths["observation_governance_audit.json"]
    )
    _validate_arm_provenance(
        binding,
        pair=pair,
        expected_commit=expected_commit,
        manifest=manifest,
        config=config,
        summary=summary,
        governance=governance,
    )
    stages = {
        name: _load_stage(paths["stage_timings.csv"], stage_name)
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
    resource = _load_resource_metrics(binding.resource_path)
    _strict_jsonl_digest(paths["online_observations.jsonl"])
    _strict_jsonl_digest(paths["offline_truth_labels.jsonl"])
    _strict_jsonl_digest(paths["offline_proximity_intercepts.jsonl"])
    _validate_truth_state_finite(paths["offline_truth_state.npz"])

    runtime_profile = _required_mapping(
        manifest.get("runtime_profile"),
        f"{pair.case_id} {binding.arm} runtime_profile",
    )
    diagnostics = _required_mapping(
        summary.get("d1_publication_metadata_diagnostics"),
        f"{pair.case_id} {binding.arm} publication_metadata_diagnostics",
    )
    operation_counts = _required_mapping(
        diagnostics.get("operation_counts"),
        f"{pair.case_id} {binding.arm} publication metadata operation_counts",
    )
    metrics = {
        "d1_fusion_wall_s": stages["d1_fusion"]["wall_time_s"],
        "d1_fusion_p50_ms": stages["d1_fusion"]["p50_wall_time_ms"],
        "d1_fusion_p95_ms": stages["d1_fusion"]["p95_wall_time_ms"],
        "d1_fusion_max_ms": stages["d1_fusion"]["max_wall_time_ms"],
        "d1_scan_input_wall_s": stages["d1_scan_input"]["wall_time_s"],
        "d2_association_wall_s": stages["d2_association"]["wall_time_s"],
        "d3_assignment_wall_s": stages["d3_assignment"]["wall_time_s"],
        "d5_active_vision_wall_s": stages["d5_active_vision"]["wall_time_s"],
        "d7_guidance_wall_s": stages["d7_guidance"]["wall_time_s"],
        "module_publication_bus_wall_s": stages[
            "module_publication_bus"
        ]["wall_time_s"],
        "core_wall_s": _finite_nonnegative(
            summary.get("wall_time_s"),
            f"{pair.case_id} {binding.arm} summary wall_time_s",
            positive=True,
        ),
        "external_elapsed_s": resource["external_elapsed_s"],
        "maximum_rss_kib": resource["maximum_rss_kib"],
        "real_time_factor": _finite_nonnegative(
            summary.get("real_time_factor"),
            f"{pair.case_id} {binding.arm} summary real_time_factor",
        ),
    }
    input_sha256 = {
        "manifest.json": _sha256_bytes(manifest_raw),
        "scenario_config.json": _sha256_bytes(config_raw),
        "summary.json": _sha256_bytes(summary_raw),
        "observation_governance_audit.json": _sha256_bytes(governance_raw),
        "stage_timings.csv": _file_sha256(paths["stage_timings.csv"]),
        "online_observations.jsonl": _file_sha256(
            paths["online_observations.jsonl"]
        ),
        "offline_truth_state.npz": _file_sha256(
            paths["offline_truth_state.npz"]
        ),
        "offline_truth_labels.jsonl": _file_sha256(
            paths["offline_truth_labels.jsonl"]
        ),
        "offline_proximity_intercepts.jsonl": _file_sha256(
            paths["offline_proximity_intercepts.jsonl"]
        ),
        "resource_usage": _file_sha256(binding.resource_path),
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
        "normalized_runtime_profile_sha256": _canonical_sha256(
            _normalized_runtime_profile(runtime_profile)
        ),
        "normalized_summary_sha256": _canonical_sha256(
            _normalized_summary(summary)
        ),
        "normalized_governance_sha256": _canonical_sha256(
            _normalized_governance(governance)
        ),
        "finite_state": bool(summary["finite_state"]),
        "online_truth_use_count": int(summary["online_truth_use_count"]),
        "implementation_identity_passed": True,
        "implementation_identity_locations": (
            _implementation_identity_locations(
                runtime_profile,
                summary,
                governance,
            )
        ),
        "publication_metadata_diagnostics": copy.deepcopy(diagnostics),
        "publication_metadata_operation_counts": copy.deepcopy(
            operation_counts
        ),
        "governance_publication_metadata_diagnostics": copy.deepcopy(
            governance["d1_publication_metadata_diagnostics"]
        ),
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
    binding: D1PublicationMetadataArmBinding,
    *,
    pair: D1PublicationMetadataPairBinding,
    expected_commit: str,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> None:
    context = f"{pair.case_id} {binding.arm}"
    if manifest.get("git_commit") != expected_commit:
        raise D1PublicationMetadataEvidenceError(f"{context} source commit mismatch")
    if manifest.get("repository_dirty") is not False:
        raise D1PublicationMetadataEvidenceError(f"{context} repository is dirty")
    config_sha256 = _canonical_sha256(config)
    if manifest.get("config_sha256") != config_sha256:
        raise D1PublicationMetadataEvidenceError(f"{context} config_sha256 mismatch")
    runtime_profile = _required_mapping(
        manifest.get("runtime_profile"),
        f"{context} runtime_profile",
    )
    runtime_sha256 = _canonical_sha256(runtime_profile)
    if manifest.get("runtime_profile_sha256") != runtime_sha256:
        raise D1PublicationMetadataEvidenceError(
            f"{context} runtime_profile_sha256 mismatch"
        )
    for mapping, label, field, expected in (
        (manifest, "manifest", "seed", pair.seed),
        (config, "config", "seed", pair.seed),
        (summary, "summary", "seed", pair.seed),
        (config, "config", "target_count", D1_PUBLICATION_METADATA_TARGET_COUNT),
        (summary, "summary", "target_count", D1_PUBLICATION_METADATA_TARGET_COUNT),
        (config, "config", "resource_count", D1_PUBLICATION_METADATA_RESOURCE_COUNT),
        (summary, "summary", "resource_count", D1_PUBLICATION_METADATA_RESOURCE_COUNT),
        (config, "config", "recon_count", D1_PUBLICATION_METADATA_RECON_COUNT),
        (summary, "summary", "recon_count", D1_PUBLICATION_METADATA_RECON_COUNT),
    ):
        if mapping.get(field) != expected:
            raise D1PublicationMetadataEvidenceError(
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
        raise D1PublicationMetadataEvidenceError(f"{context} finite_state must be true")
    if summary.get("online_truth_use_count") != 0:
        raise D1PublicationMetadataEvidenceError(
            f"{context} online_truth_use_count must be zero"
        )
    if governance.get("online_truth_use_count") != 0:
        raise D1PublicationMetadataEvidenceError(
            f"{context} governance online truth count must be zero"
        )
    _validate_implementation_identity(
        binding.arm,
        binding.implementation,
        runtime_profile=runtime_profile,
        summary=summary,
        governance=governance,
        context=context,
    )


def _validate_implementation_identity(
    arm: str,
    expected: str,
    *,
    runtime_profile: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
    context: str,
) -> None:
    runtime_configuration = _required_mapping(
        runtime_profile.get("configuration"),
        f"{context} runtime configuration",
    )
    summary_diagnostics = _required_mapping(
        summary.get("d1_publication_metadata_diagnostics"),
        f"{context} summary publication_metadata_diagnostics",
    )
    final = _required_mapping(
        summary.get("module_final_diagnostics"),
        f"{context} module_final_diagnostics",
    )
    final_diagnostics = _required_mapping(
        final.get("d1_publication_metadata_diagnostics"),
        f"{context} final publication_metadata_diagnostics",
    )
    governance_diagnostics = _required_mapping(
        governance.get("d1_publication_metadata_diagnostics"),
        f"{context} governance publication_metadata_diagnostics",
    )
    locations = {
        "manifest.runtime_profile": runtime_profile.get(
            "d1_publication_metadata_implementation"
        ),
        "manifest.runtime_profile.configuration": runtime_configuration.get(
            "d1_publication_metadata_implementation"
        ),
        "summary": summary.get("d1_publication_metadata_implementation"),
        "summary.module_final_diagnostics": final.get(
            "d1_publication_metadata_implementation"
        ),
        "governance": governance.get("d1_publication_metadata_implementation"),
    }
    mismatches = [
        f"{name}={value!r}"
        for name, value in locations.items()
        if value != expected
    ]
    if mismatches:
        raise D1PublicationMetadataEvidenceError(
            f"{context} implementation identity mismatch: "
            + ", ".join(mismatches)
        )
    diagnostics_set = (
        summary_diagnostics,
        final_diagnostics,
        governance_diagnostics,
    )
    for diagnostics in diagnostics_set:
        if diagnostics != summary_diagnostics:
            raise D1PublicationMetadataEvidenceError(
                f"{context} publication metadata diagnostics mismatch"
            )
        if diagnostics.get("implementation_id") != _IMPLEMENTATION_IDS[arm]:
            raise D1PublicationMetadataEvidenceError(
                f"{context} implementation_id mismatch"
            )
        immutable = diagnostics.get("immutable_shared_publication_metadata")
        if immutable is not (arm == _CANDIDATE_ARM):
            raise D1PublicationMetadataEvidenceError(
                f"{context} immutable publication metadata flag mismatch"
            )
        counts = _required_mapping(
            diagnostics.get("operation_counts"),
            f"{context} operation_counts",
        )
        for key, value in counts.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise D1PublicationMetadataEvidenceError(
                    f"{context} operation count {key} is invalid"
                )
        materialized = _required_positive_count(
            counts,
            "global_track_metadata_materialization_count",
            context,
        )
        _required_positive_count(
            counts,
            "global_tracks_call_count",
            context,
        )
        _required_positive_count(
            counts,
            "shared_publication_context_build_count",
            context,
        )
        if materialized < 1:
            raise D1PublicationMetadataEvidenceError(
                f"{context} full materialization count must be positive"
            )
        copy_count = int(
            counts.get("per_track_shared_audit_mapping_copy_count", 0)
        )
        reuse_count = int(counts.get("shared_audit_value_reuse_count", 0))
        if arm == _REFERENCE_ARM:
            if copy_count <= 0:
                raise D1PublicationMetadataEvidenceError(
                    f"{context} reference per-track copy count must be positive"
                )
            if reuse_count != 0:
                raise D1PublicationMetadataEvidenceError(
                    f"{context} reference shared reuse count must be zero"
                )
        else:
            if copy_count != 0:
                raise D1PublicationMetadataEvidenceError(
                    f"{context} candidate per-track copy count must be zero"
                )
            if reuse_count <= 0:
                raise D1PublicationMetadataEvidenceError(
                    f"{context} candidate shared reuse count must be positive"
                )


def _implementation_identity_locations(
    runtime_profile: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> dict[str, str]:
    configuration = _required_mapping(
        runtime_profile["configuration"],
        "runtime profile configuration",
    )
    summary_diagnostics = _required_mapping(
        summary["d1_publication_metadata_diagnostics"],
        "summary publication metadata diagnostics",
    )
    return {
        "manifest_runtime_profile": str(
            runtime_profile["d1_publication_metadata_implementation"]
        ),
        "manifest_runtime_configuration": str(
            configuration["d1_publication_metadata_implementation"]
        ),
        "summary_top_level": str(summary["d1_publication_metadata_implementation"]),
        "summary_implementation_id": str(
            summary_diagnostics["implementation_id"]
        ),
        "governance_top_level": str(
            governance["d1_publication_metadata_implementation"]
        ),
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
        raise D1PublicationMetadataEvidenceError(
            "main cross-build reader returned an unsupported schema"
        )
    cross_checks = _required_mapping(cross.get("checks"), "cross checks")
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


def _normalized_runtime_profile(
    runtime_profile: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(runtime_profile))
    normalized["d1_publication_metadata_implementation"] = _IMPLEMENTATION_MARKER
    configuration = _mutable_mapping(
        normalized.get("configuration"),
        "normalized runtime configuration",
    )
    configuration["d1_publication_metadata_implementation"] = _IMPLEMENTATION_MARKER
    return normalized


def _normalized_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(summary))
    if "episode_id" not in normalized:
        raise D1PublicationMetadataEvidenceError(
            "normalized summary lacks episode_id"
        )
    normalized["episode_id"] = _TREATMENT_DERIVED_ID_MARKER
    normalized["wall_time_s"] = _PERFORMANCE_MARKER
    normalized["real_time_factor"] = _PERFORMANCE_MARKER
    _normalize_publication_metadata_fields(normalized, "normalized summary")
    final = _mutable_mapping(
        normalized.get("module_final_diagnostics"),
        "normalized module_final_diagnostics",
    )
    _normalize_publication_metadata_fields(final, "normalized module final")
    if "stage_timings" not in final:
        raise D1PublicationMetadataEvidenceError(
            "normalized module final lacks stage_timings"
        )
    final["stage_timings"] = _PERFORMANCE_MARKER
    nested_governance = _required_mapping(
        final.get("observation_governance"),
        "normalized module final observation_governance",
    )
    final["observation_governance"] = _normalized_governance(
        nested_governance
    )
    return normalized


def _normalized_governance(governance: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(governance))
    _normalize_publication_metadata_fields(normalized, "normalized governance")
    fusion = normalized.get("d1_fusion_association")
    if isinstance(fusion, dict) and (
        "association_innovation_solve_count" in fusion
    ):
        fusion["association_innovation_solve_count"] = _PERFORMANCE_MARKER
    return normalized


def _normalize_publication_metadata_fields(
    mapping: dict[str, Any],
    context: str,
) -> None:
    if "d1_publication_metadata_implementation" not in mapping:
        raise D1PublicationMetadataEvidenceError(
            f"{context} lacks d1_publication_metadata_implementation"
        )
    mapping["d1_publication_metadata_implementation"] = _IMPLEMENTATION_MARKER
    diagnostics = _mutable_mapping(
        mapping.get("d1_publication_metadata_diagnostics"),
        f"{context} publication_metadata_diagnostics",
    )
    diagnostics.clear()
    diagnostics["value"] = _PERFORMANCE_MARKER


def _load_stage(path: Path, stage_name: str) -> dict[str, Any]:
    required_fields = {
        "schema_version",
        "stage",
        "call_count",
        "wall_time_s",
        "mean_wall_time_ms",
        "p50_wall_time_ms",
        "p95_wall_time_ms",
        "max_wall_time_ms",
        "distribution_available",
        "distribution_unavailable_reason",
    }
    try:
        with path.open("r", newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or not required_fields.issubset(
                reader.fieldnames
            ):
                raise D1PublicationMetadataEvidenceError(
                    "stage_timings.csv lacks required columns"
                )
            rows = [row for row in reader if row.get("stage") == stage_name]
    except OSError as exc:
        raise D1PublicationMetadataEvidenceError(
            f"unable to read stage timings: {exc}"
        ) from exc
    if len(rows) != 1:
        raise D1PublicationMetadataEvidenceError(
            f"stage_timings.csv must contain exactly one {stage_name} row"
        )
    row = rows[0]
    if row.get("schema_version") != _STAGE_TIMING_SCHEMA_VERSION:
        raise D1PublicationMetadataEvidenceError(
            f"{stage_name} stage schema mismatch"
        )
    call_count = _parse_positive_integer(row.get("call_count"), "call_count")
    if str(row.get("distribution_available", "")).strip().lower() != "true":
        raise D1PublicationMetadataEvidenceError(
            f"{stage_name} timing distribution must be available"
        )
    if str(row.get("distribution_unavailable_reason", "")).strip():
        raise D1PublicationMetadataEvidenceError(
            f"{stage_name} timing has an unexpected unavailable reason"
        )
    values = {
        field: _parse_finite_nonnegative_text(row.get(field), field)
        for field in (
            "wall_time_s",
            "mean_wall_time_ms",
            "p50_wall_time_ms",
            "p95_wall_time_ms",
            "max_wall_time_ms",
        )
    }
    if values["wall_time_s"] <= 0.0:
        raise D1PublicationMetadataEvidenceError(
            f"{stage_name} wall_time_s must be positive"
        )
    if not (
        values["p50_wall_time_ms"]
        <= values["p95_wall_time_ms"]
        <= values["max_wall_time_ms"]
    ):
        raise D1PublicationMetadataEvidenceError(
            f"{stage_name} timing percentiles are not ordered"
        )
    expected_wall_ms = values["mean_wall_time_ms"] * call_count
    if not math.isclose(
        expected_wall_ms,
        values["wall_time_s"] * 1000.0,
        rel_tol=1.0e-6,
        abs_tol=1.0e-6,
    ):
        raise D1PublicationMetadataEvidenceError(
            f"{stage_name} mean/call_count does not reconstruct wall_time_s"
        )
    if values["max_wall_time_ms"] > values["wall_time_s"] * 1000.0 + 1.0e-6:
        raise D1PublicationMetadataEvidenceError(
            f"{stage_name} max timing exceeds accumulated wall time"
        )
    return {
        "schema_version": row["schema_version"],
        "stage": stage_name,
        "call_count": call_count,
        **values,
        "distribution_available": True,
    }


def _load_resource_metrics(path: Path) -> dict[str, float | int]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise D1PublicationMetadataEvidenceError(
            f"unable to read GNU time resource evidence: {exc}"
        ) from exc
    values: dict[str, float | int] = {}
    for name, pattern in _RESOURCE_PATTERNS.items():
        match = pattern.search(text)
        if match is None:
            raise D1PublicationMetadataEvidenceError(
                f"GNU time resource field is missing: {name}"
            )
        raw = match.group(1)
        try:
            if name == "external_elapsed_s":
                value: float | int = _parse_elapsed_seconds(raw)
            else:
                value = int(raw)
        except ValueError as exc:
            raise D1PublicationMetadataEvidenceError(
                f"GNU time resource field is invalid: {name}={raw!r}"
            ) from exc
        if value < 0 or (
            isinstance(value, float) and not math.isfinite(value)
        ):
            raise D1PublicationMetadataEvidenceError(
                f"GNU time resource field is nonfinite or negative: {name}"
            )
        values[name] = value
    if values["process_exit_status"] != 0:
        raise D1PublicationMetadataEvidenceError("GNU time process exit status is not zero")
    return values


def _validate_stderr(path: Path, context: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise D1PublicationMetadataEvidenceError(
            f"{context} unable to read stderr"
        ) from exc
    if not text:
        classification = "empty"
    elif text == _ALLOWED_STDERR:
        classification = "registered_matplotlib_axes3d_warning_only"
    else:
        raise D1PublicationMetadataEvidenceError(
            f"{context} stderr contains an unregistered diagnostic"
        )
    return {
        "classification": classification,
        "byte_count": len(text.encode("utf-8")),
        "sha256": _sha256_bytes(text.encode("utf-8")),
    }


def _compare_pair_metric(
    reference: float | int,
    candidate: float | int,
    *,
    lower_is_better: bool,
) -> dict[str, Any]:
    reference_value = _finite_nonnegative(
        reference,
        "reference metric",
        positive=True,
    )
    candidate_value = _finite_nonnegative(
        candidate,
        "candidate metric",
    )
    raw_change = (candidate_value - reference_value) / reference_value
    improvement = -raw_change if lower_is_better else raw_change
    return {
        "reference": reference_value,
        "candidate": candidate_value,
        "raw_relative_change": raw_change,
        "raw_relative_change_pct": raw_change * 100.0,
        "improvement": improvement,
        "improvement_pct": improvement * 100.0,
        "candidate_better": (
            candidate_value < reference_value
            if lower_is_better
            else candidate_value > reference_value
        ),
        "direction": (
            "lower_is_better" if lower_is_better else "higher_is_better"
        ),
    }


def _summarize_group(
    pairs: Sequence[Mapping[str, Any]],
    *,
    group: str,
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
            bool(pair["implementation_identity_passed"]) for pair in ordered
        ),
        "metrics": {
            metric: _summarize_group_metric(
                ordered,
                metric=metric,
            )
            for metric in _METRICS
        },
    }


def _summarize_group_metric(
    pairs: Sequence[Mapping[str, Any]],
    *,
    metric: str,
) -> dict[str, Any]:
    comparisons = [pair["performance"][metric] for pair in pairs]
    reference = [float(item["reference"]) for item in comparisons]
    candidate = [float(item["candidate"]) for item in comparisons]
    raw = [float(item["raw_relative_change"]) for item in comparisons]
    improvement = [float(item["improvement"]) for item in comparisons]
    lower, upper = _bootstrap_mean_ci(
        raw,
        resamples=D1_PUBLICATION_METADATA_BOOTSTRAP_RESAMPLES,
        rng_seed=D1_PUBLICATION_METADATA_BOOTSTRAP_RNG_SEED,
    )
    ratio_of_group_means_raw = (
        fmean(candidate) - fmean(reference)
    ) / fmean(reference)
    ratio_of_group_means_improvement = (
        -ratio_of_group_means_raw
        if metric in _LOWER_IS_BETTER
        else ratio_of_group_means_raw
    )
    return {
        "metric": metric,
        "direction": (
            "lower_is_better" if metric in _LOWER_IS_BETTER else "higher_is_better"
        ),
        "pair_count": len(comparisons),
        "reference": _distribution(reference),
        "candidate": _distribution(candidate),
        "raw_relative_change": {
            **_distribution(raw),
            "bootstrap_95_ci": {
                "method": "paired_percentile_mean",
                "lower": lower,
                "upper": upper,
                "resamples": D1_PUBLICATION_METADATA_BOOTSTRAP_RESAMPLES,
                "rng_seed": D1_PUBLICATION_METADATA_BOOTSTRAP_RNG_SEED,
            },
        },
        "improvement_pct": {
            key: value * 100.0
            for key, value in _distribution(improvement).items()
        },
        "ratio_of_group_means": {
            "raw_relative_change": ratio_of_group_means_raw,
            "improvement_pct": ratio_of_group_means_improvement * 100.0,
        },
        "candidate_better_count": sum(
            bool(item["candidate_better"]) for item in comparisons
        ),
        "maximum_pair_raw_relative_change_pct": max(raw) * 100.0,
    }


def _admission_gates(
    pairs: Sequence[Mapping[str, Any]],
    groups: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    short_fusion = groups["short"]["metrics"]["d1_fusion_wall_s"]
    long_fusion = groups["long"]["metrics"]["d1_fusion_wall_s"]
    short_core = groups["short"]["metrics"]["core_wall_s"]
    long_core = groups["long"]["metrics"]["core_wall_s"]
    rss = [groups[group]["metrics"]["maximum_rss_kib"] for group in _GROUPS]
    semantic_pass = bool(pairs) and all(
        bool(pair["business_semantics_passed"]) for pair in pairs
    )
    finite_pass = bool(pairs) and all(
        bool(pair["finite_state_passed"]) for pair in pairs
    )
    truth_pass = bool(pairs) and all(
        bool(pair["truth_isolation_passed"]) for pair in pairs
    )
    identity_pass = bool(pairs) and all(
        bool(pair["implementation_identity_passed"]) for pair in pairs
    )
    required_metrics_pass = bool(pairs) and all(
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
    return {
        "all_pairs_business_semantics_equal": _gate(
            semantic_pass,
            "one_or_more_pair_business_semantics_mismatch",
        ),
        "all_pairs_finite_state": _gate(
            finite_pass,
            "one_or_more_pair_finite_state_check_failed",
        ),
        "all_pairs_online_truth_use_count_zero": _gate(
            truth_pass,
            "one_or_more_pair_online_truth_isolation_failed",
        ),
        "all_pairs_explicit_implementation_identity": _gate(
            identity_pass,
            "one_or_more_arm_implementation_identity_failed",
        ),
        "required_performance_metrics_available": _gate(
            required_metrics_pass,
            "one_or_more_required_performance_metrics_unavailable",
        ),
        "short_candidate_faster_at_least_8_of_10": _gate(
            short_fusion["candidate_better_count"] >= 8,
            "short_candidate_faster_count_below_8",
        ),
        "short_d1_fusion_mean_improvement_at_least_10_pct": _gate(
            short_fusion["improvement_pct"]["mean"] >= 10.0,
            "short_d1_fusion_mean_improvement_below_10_pct",
        ),
        "short_d1_fusion_bootstrap_raw_ci_upper_below_zero": _gate(
            short_fusion["raw_relative_change"]["bootstrap_95_ci"]["upper"] < 0.0,
            "short_d1_fusion_bootstrap_raw_ci_upper_not_below_zero",
        ),
        "long_candidate_faster_at_least_2_of_3": _gate(
            long_fusion["candidate_better_count"] >= 2,
            "long_candidate_faster_count_below_2",
        ),
        "long_d1_fusion_mean_improvement_at_least_10_pct": _gate(
            long_fusion["improvement_pct"]["mean"] >= 10.0,
            "long_d1_fusion_mean_improvement_below_10_pct",
        ),
        "short_core_wall_mean_improvement_at_least_5_pct": _gate(
            short_core["improvement_pct"]["mean"] >= 5.0,
            "short_core_wall_mean_improvement_below_5_pct",
        ),
        "long_core_wall_mean_improvement_at_least_5_pct": _gate(
            long_core["improvement_pct"]["mean"] >= 5.0,
            "long_core_wall_mean_improvement_below_5_pct",
        ),
        "rss_mean_degradation_within_5_pct": _gate(
            all(
                summary["raw_relative_change"]["mean"] <= 0.05
                for summary in rss
            ),
            "short_or_long_rss_mean_degradation_above_5_pct",
        ),
        "every_pair_rss_degradation_within_5_pct": _gate(
            all(
                pair["performance"]["maximum_rss_kib"][
                    "raw_relative_change"
                ]
                <= 0.05
                for pair in pairs
            ),
            "one_or_more_pair_rss_degradation_above_5_pct",
        ),
    }


def _system_realtime_gate(
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    candidate_values = [
        float(pair["candidate"]["metrics"]["real_time_factor"])
        for pair in pairs
    ]
    passed = bool(candidate_values) and all(
        value >= 1.0 for value in candidate_values
    )
    return {
        "passed": passed,
        "reason": (
            None
            if passed
            else "one_or_more_candidate_real_time_factor_below_one"
        ),
        "required_candidate_real_time_factor": 1.0,
        "candidate_pair_count": len(candidate_values),
        "candidate_minimum_real_time_factor": (
            min(candidate_values) if candidate_values else None
        ),
        "independent_of_d1_optimization_admission": True,
    }


def _aggregate_output(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": D1_PUBLICATION_METADATA_MULTISEED_AGGREGATE_SCHEMA_VERSION,
        "evaluation_schema_version": result["schema_version"],
        "evaluation_date": result["evaluation_date"],
        "input_contract": result["input_contract"],
        "groups": result["groups"],
        "cross_module_attribution": result["cross_module_attribution"],
        "admission_gates": result["admission_gates"],
        "d1_optimization_admitted": result["d1_optimization_admitted"],
        "system_realtime_gate": result["system_realtime_gate"],
        "system_realtime_gap_closed": result["system_realtime_gap_closed"],
    }


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
        "reference_implementation",
        "candidate_implementation",
        "reference_materialization_count",
        "candidate_materialization_count",
        "reference_per_track_copy_count",
        "candidate_per_track_copy_count",
        "candidate_shared_reuse_count",
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
        for pair in result.get("pairs", []):
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
                "reference_implementation": pair["reference"][
                    "expected_implementation"
                ],
                "candidate_implementation": pair["candidate"][
                    "expected_implementation"
                ],
                "reference_materialization_count": pair["reference"][
                    "publication_metadata_operation_counts"
                ]["global_track_metadata_materialization_count"],
                "candidate_materialization_count": pair["candidate"][
                    "publication_metadata_operation_counts"
                ]["global_track_metadata_materialization_count"],
                "reference_per_track_copy_count": pair["reference"][
                    "publication_metadata_operation_counts"
                ].get("per_track_shared_audit_mapping_copy_count", 0),
                "candidate_per_track_copy_count": pair["candidate"][
                    "publication_metadata_operation_counts"
                ].get("per_track_shared_audit_mapping_copy_count", 0),
                "candidate_shared_reuse_count": pair["candidate"][
                    "publication_metadata_operation_counts"
                ].get("shared_audit_value_reuse_count", 0),
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


def _write_improvement_plot(
    result: Mapping[str, Any],
    path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axis = plt.subplots(figsize=(9.0, 4.8))
    colors = {"short": "#1f77b4", "long": "#d62728"}
    for group in _GROUPS:
        group_pairs = [
            pair for pair in result["pairs"] if pair["group"] == group
        ]
        group_pairs.sort(key=lambda item: int(item["seed"]))
        axis.plot(
            [int(pair["seed"]) for pair in group_pairs],
            [
                float(
                    pair["performance"]["d1_fusion_wall_s"][
                        "improvement_pct"
                    ]
                )
                for pair in group_pairs
            ],
            marker="o",
            linewidth=1.8,
            label=("Short 2.2 s" if group == "short" else "Long 10 s"),
            color=colors[group],
        )
    axis.axhline(0.0, color="#444444", linewidth=1.0)
    axis.axhline(
        10.0,
        color="#2ca02c",
        linewidth=1.0,
        linestyle="--",
        label="D1 fusion threshold 10%",
    )
    axis.set_xlabel("Seed")
    axis.set_ylabel("D1 fusion improvement (%)")
    axis.set_title("Publication metadata paired D1-fusion improvement")
    axis.grid(True, alpha=0.25)
    axis.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _case_metadata(
    case: Mapping[str, Any],
) -> tuple[str, str, int, float, tuple[str, str]]:
    case_id = _required_text(case.get("case_id"), "case_id")
    group = _required_text(case.get("group"), f"{case_id} group")
    seed = _required_integer(case.get("seed"), f"{case_id} seed")
    duration = _finite_nonnegative(
        case.get("duration_s"),
        f"{case_id} duration_s",
        positive=True,
    )
    arm_order_raw = _required_sequence(
        case.get("arm_order"),
        f"{case_id} arm_order",
    )
    if len(arm_order_raw) != 2:
        raise D1PublicationMetadataEvidenceError(
            f"{case_id} arm_order must contain two arms"
        )
    arm_order = tuple(
        _required_text(item, f"{case_id} arm_order item")
        for item in arm_order_raw
    )
    if set(arm_order) != set(_ARMS):
        raise D1PublicationMetadataEvidenceError(
            f"{case_id} arm_order must contain reference and candidate"
        )
    return case_id, group, seed, duration, arm_order  # type: ignore[return-value]


def _expected_command(
    *,
    source_worktree: Path,
    run_flags: tuple[str, ...],
    implementation: str,
    duration_s: float,
    seed: int,
    resource_count: int,
    target_count: int,
    recon_count: int,
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
        *run_flags,
        "--d1-publication-metadata-implementation",
        implementation,
        "--duration",
        format(duration_s, ".15g"),
        "--seed",
        str(seed),
        "--drone-count",
        str(resource_count),
        "--target-count",
        str(target_count),
        "--recon-count",
        str(recon_count),
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
        raise D1PublicationMetadataEvidenceError(
            f"{case_id} arm command lengths differ"
        )
    implementation_index = reference.index(
        "--d1-publication-metadata-implementation"
    ) + 1
    output_index = reference.index("--output") + 1
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index in {implementation_index, output_index}:
            continue
        if left != right:
            raise D1PublicationMetadataEvidenceError(
                f"{case_id} arm commands differ outside treatment/output"
            )


def _distribution(values: Sequence[float]) -> dict[str, float]:
    if not values:
        raise D1PublicationMetadataEvidenceError("distribution has no values")
    if not all(math.isfinite(value) for value in values):
        raise D1PublicationMetadataEvidenceError("distribution contains nonfinite values")
    ordered = sorted(values)
    return {
        "mean": fmean(values),
        "median": median(values),
        "p95": _percentile(ordered, 0.95),
        "minimum": ordered[0],
        "maximum": ordered[-1],
    }


def _bootstrap_mean_ci(
    values: Sequence[float],
    *,
    resamples: int,
    rng_seed: int,
) -> tuple[float, float]:
    if not values:
        raise D1PublicationMetadataEvidenceError("bootstrap has no paired values")
    rng = random.Random(rng_seed)
    sample_count = len(values)
    means = [
        fmean(values[rng.randrange(sample_count)] for _ in range(sample_count))
        for _ in range(resamples)
    ]
    means.sort()
    return _percentile(means, 0.025), _percentile(means, 0.975)


def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    if not sorted_values:
        raise ValueError("percentile requires values")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be within [0, 1]")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    index = (len(sorted_values) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return float(sorted_values[lower])
    fraction = index - lower
    return float(
        sorted_values[lower] * (1.0 - fraction)
        + sorted_values[upper] * fraction
    )


def _strict_jsonl_digest(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(
                        line,
                        parse_constant=_reject_json_constant,
                    )
                except (json.JSONDecodeError, _StrictJSONConstantError) as exc:
                    raise D1PublicationMetadataEvidenceError(
                        f"invalid JSONL at {path}:{line_number}: {exc}"
                    ) from exc
                _assert_finite_tree(
                    value,
                    f"{path.name}:{line_number}",
                )
                digest.update(_canonical_json_bytes(value))
                digest.update(b"\n")
    except OSError as exc:
        raise D1PublicationMetadataEvidenceError(f"unable to read {path}: {exc}") from exc
    return digest.hexdigest()


def _validate_truth_state_finite(path: Path) -> None:
    try:
        with np.load(path, allow_pickle=False) as data:
            if not data.files:
                raise D1PublicationMetadataEvidenceError(
                    "offline_truth_state.npz has no arrays"
                )
            for key in data.files:
                array = data[key]
                if array.dtype.kind in {"f", "c"} and not np.all(
                    np.isfinite(array)
                ):
                    raise D1PublicationMetadataEvidenceError(
                        f"offline truth array {key} contains nonfinite values"
                    )
    except (OSError, ValueError) as exc:
        if isinstance(exc, D1PublicationMetadataEvidenceError):
            raise
        raise D1PublicationMetadataEvidenceError(
            f"unable to validate offline truth state: {exc}"
        ) from exc


def _load_strict_json_mapping(
    path: Path,
) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            parse_constant=_reject_json_constant,
        )
    except (OSError, json.JSONDecodeError, _StrictJSONConstantError) as exc:
        raise D1PublicationMetadataEvidenceError(
            f"unable to read strict JSON object {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise D1PublicationMetadataEvidenceError(f"expected JSON object: {path}")
    _assert_finite_tree(value, path.name)
    return value, raw


def _reject_json_constant(value: str) -> None:
    raise _StrictJSONConstantError(f"nonfinite JSON constant: {value}")


def _assert_finite_tree(value: Any, context: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise D1PublicationMetadataEvidenceError(
                f"{context} contains a nonfinite number"
            )
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            _assert_finite_tree(child, f"{context}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_finite_tree(child, f"{context}[{index}]")
        return
    raise D1PublicationMetadataEvidenceError(
        f"{context} contains unsupported value type {type(value).__name__}"
    )


def _parse_elapsed_seconds(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        seconds = float(parts[1])
    elif len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    else:
        raise ValueError("elapsed value must use m:ss or h:mm:ss")
    if hours < 0 or not 0 <= minutes < 60 or not 0.0 <= seconds < 60.0:
        raise ValueError("elapsed value has an invalid clock field")
    result = hours * 3600.0 + minutes * 60.0 + seconds
    if not math.isfinite(result):
        raise ValueError("elapsed value is nonfinite")
    return result


def _parse_positive_integer(value: Any, context: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise D1PublicationMetadataEvidenceError(f"{context} must be an integer") from exc
    if parsed <= 0 or str(parsed) != str(value).strip():
        raise D1PublicationMetadataEvidenceError(
            f"{context} must be a canonical positive integer"
        )
    return parsed


def _parse_finite_nonnegative_text(value: Any, context: str) -> float:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError) as exc:
        raise D1PublicationMetadataEvidenceError(f"{context} must be numeric") from exc
    if not math.isfinite(parsed) or parsed < 0.0:
        raise D1PublicationMetadataEvidenceError(
            f"{context} must be finite and nonnegative"
        )
    return parsed


def _finite_nonnegative(
    value: Any,
    context: str,
    *,
    positive: bool = False,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
        or (positive and float(value) <= 0.0)
    ):
        qualifier = "positive" if positive else "nonnegative"
        raise D1PublicationMetadataEvidenceError(
            f"{context} must be finite and {qualifier}"
        )
    return float(value)


def _required_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise D1PublicationMetadataEvidenceError(f"{context} must be an object")
    return value


def _mutable_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise D1PublicationMetadataEvidenceError(f"{context} must be a JSON object")
    return value


def _required_sequence(value: Any, context: str) -> Sequence[Any]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        raise D1PublicationMetadataEvidenceError(f"{context} must be an array")
    return value


def _required_text(value: Any, context: str) -> str:
    result = str(value).strip() if value is not None else ""
    if not result:
        raise D1PublicationMetadataEvidenceError(f"{context} must be non-empty")
    return result


def _required_integer(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise D1PublicationMetadataEvidenceError(
            f"{context} must be a nonnegative integer"
        )
    return int(value)


def _required_positive_count(
    mapping: Mapping[str, Any],
    field: str,
    context: str,
) -> int:
    value = mapping.get(field)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
    ):
        raise D1PublicationMetadataEvidenceError(
            f"{context} {field} must be a positive integer"
        )
    return value


def _required_commit(value: Any, context: str) -> str:
    text = _required_text(value, context)
    if _COMMIT_RE.fullmatch(text) is None:
        raise D1PublicationMetadataEvidenceError(
            f"{context} must be a lowercase 40-character commit"
        )
    return text


def _required_sha256(value: Any, context: str) -> str:
    text = _required_text(value, context)
    if _SHA256_RE.fullmatch(text) is None:
        raise D1PublicationMetadataEvidenceError(
            f"{context} must be a lowercase SHA256 digest"
        )
    return text


def _expect_equal(actual: Any, expected: Any, context: str) -> None:
    if actual != expected:
        raise D1PublicationMetadataEvidenceError(
            f"{context} mismatch: expected {expected!r}, got {actual!r}"
        )


def _expect_finite_equal(
    actual: Any,
    expected: float,
    context: str,
) -> None:
    if (
        isinstance(actual, bool)
        or not isinstance(actual, (int, float))
        or not math.isfinite(float(actual))
        or not math.isclose(
            float(actual),
            expected,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        )
    ):
        raise D1PublicationMetadataEvidenceError(
            f"{context} mismatch: expected {expected!r}, got {actual!r}"
        )


def _explicit_path(
    value: Any,
    context: str,
    *,
    require: str | None,
) -> Path:
    raw = _required_text(value, context)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise D1PublicationMetadataEvidenceError(f"{context} must be an absolute path")
    resolved = path.resolve()
    if require == "file" and not resolved.is_file():
        raise D1PublicationMetadataEvidenceError(f"{context} is not a file: {resolved}")
    if require == "directory" and not resolved.is_dir():
        raise D1PublicationMetadataEvidenceError(
            f"{context} is not a directory: {resolved}"
        )
    return resolved


def _require_under_root(path: Path, root: Path, context: str) -> None:
    if not _path_is_within(path, root) or path == root:
        raise D1PublicationMetadataEvidenceError(
            f"{context} must be strictly under output_root"
        )


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_text(value: Any) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )


def _gate(passed: bool, reason: str) -> dict[str, Any]:
    return {"passed": bool(passed), "reason": None if passed else reason}


def _fmt(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "-"
    if not math.isfinite(float(value)):
        return "-"
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-manifest",
        type=Path,
        required=True,
        help="completed main evidence_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="independent D6 report directory outside the evidence root",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = evaluate_d1_publication_metadata_multiseed(args.evidence_manifest)
    paths = write_d1_publication_metadata_multiseed_report(result, args.output_dir)
    print(f"d1_optimization_admitted={result['d1_optimization_admitted']}")
    print(
        "system_realtime_gap_closed="
        f"{result['system_realtime_gap_closed']}"
    )
    for name, path in paths.items():
        print(f"{name}={path}")
    return 0


__all__ = [
    "D1_PUBLICATION_METADATA_BOOTSTRAP_RESAMPLES",
    "D1_PUBLICATION_METADATA_BOOTSTRAP_RNG_SEED",
    "D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION",
    "D1_PUBLICATION_METADATA_EVALUATION_DATE",
    "D1_PUBLICATION_METADATA_EVIDENCE_MANIFEST_SCHEMA_VERSION",
    "D1_PUBLICATION_METADATA_EXPERIMENT_ID",
    "D1_PUBLICATION_METADATA_LONG_DURATION_S",
    "D1_PUBLICATION_METADATA_LONG_SEEDS",
    "D1_PUBLICATION_METADATA_MATRIX_SCHEMA_VERSION",
    "D1_PUBLICATION_METADATA_MATRIX_SHA256",
    "D1_PUBLICATION_METADATA_MULTISEED_AGGREGATE_SCHEMA_VERSION",
    "D1_PUBLICATION_METADATA_MULTISEED_EVALUATION_SCHEMA_VERSION",
    "D1_PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION",
    "D1_PUBLICATION_METADATA_SHORT_DURATION_S",
    "D1_PUBLICATION_METADATA_SHORT_SEEDS",
    "D1PublicationMetadataEvidence",
    "D1PublicationMetadataEvidenceError",
    "evaluate_d1_publication_metadata_multiseed",
    "load_d1_publication_metadata_evidence_manifest",
    "main",
    "render_d1_publication_metadata_multiseed_markdown",
    "write_d1_publication_metadata_multiseed_report",
]
