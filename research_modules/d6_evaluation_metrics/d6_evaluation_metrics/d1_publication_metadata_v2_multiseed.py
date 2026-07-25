"""Independent D6 evaluation for D1 immutable publication metadata v2.

The v1 evaluator remains frozen in ``d1_publication_metadata_multiseed``.
This module consumes only the preregistered v2 same-clean-commit matrix.  It
normalizes the explicitly registered D2 audit counters for business semantic
comparison, then validates those counters separately and fails closed.
"""

from __future__ import annotations

import argparse
import copy
import csv
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from research_modules.scalable_3d_simulation.cross_build_equivalence import (
    CROSS_BUILD_EQUIVALENCE_SCHEMA_VERSION,
    compare_cross_build_episodes,
)

from . import d1_publication_metadata_multiseed as _v1


D1_PUBLICATION_METADATA_V2_MULTISEED_EVALUATION_SCHEMA_VERSION = (
    "d6.d1_publication_metadata_v2_multiseed_evaluation.v1"
)
D1_PUBLICATION_METADATA_V2_MULTISEED_AGGREGATE_SCHEMA_VERSION = (
    "d6.d1_publication_metadata_v2_multiseed_aggregate.v1"
)
D1_PUBLICATION_METADATA_V2_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-publication-metadata-v2-multiseed-evidence-v1"
)
D1_PUBLICATION_METADATA_V2_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-publication-metadata-v2-multiseed-matrix-v1"
)
D1_PUBLICATION_METADATA_V2_EXPERIMENT_ID = (
    "d1-publication-metadata-v2-multiseed-20260724-v1"
)
D1_PUBLICATION_METADATA_V2_MATRIX_SHA256 = (
    "51429554d58b82e94f922f7e0042144fd3440044f5188b51d77c578424d96927"
)
D1_PUBLICATION_METADATA_V2_SOURCE_COMMIT = (
    "be399e138762f5e660f553c8caa812d52ab38c61"
)
D1_PUBLICATION_METADATA_V2_EVALUATION_DATE = "2026-07-24"
D1_PUBLICATION_AUDIT_TREE_CONTRACT_VERSION = "d1.publication_audit_tree.v2"
D2_PUBLICATION_METADATA_AUDIT_SCHEMA_VERSION = (
    "scalable3d-d2-publication-metadata-audit-v1"
)

REFERENCE_IMPLEMENTATION = "per_track_copy_v1"
CANDIDATE_IMPLEMENTATION = "immutable_shared_v2"
REFERENCE_IMPLEMENTATION_ID = "d1.publication_metadata.per_track_audit_copy.v1"
CANDIDATE_IMPLEMENTATION_ID = "d1.publication_metadata.immutable_shared_audit.v2"

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
_PUBLICATION_AUDIT_MARKER = "D6_REGISTERED_D2_PUBLICATION_AUDIT_TREATMENT"

_EXPECTED_GATES = {
    "all_pairs_business_semantics_equal": True,
    "all_pairs_d2_publication_metadata_audit_valid": True,
    "all_pairs_explicit_implementation_identity": True,
    "all_pairs_finite_state": True,
    "all_pairs_online_truth_use_count": 0,
    "long_minimum_candidate_faster_count": 2,
    "long_minimum_core_wall_improvement_pct": 5.0,
    "long_minimum_d1_fusion_improvement_pct": 10.0,
    "maximum_any_pair_rss_increase_pct": 5.0,
    "maximum_long_d2_association_mean_increase_pct": 5.0,
    "maximum_rss_mean_increase_pct": 5.0,
    "maximum_short_d2_association_mean_increase_pct": 5.0,
    "short_bootstrap_relative_change_upper_bound_pct": 0.0,
    "short_minimum_candidate_faster_count": 8,
    "short_minimum_core_wall_improvement_pct": 5.0,
    "short_minimum_d1_fusion_improvement_pct": 10.0,
}
_EXPECTED_BOUNDARY = {
    "airsim_evidence": False,
    "candidate_implementation": CANDIDATE_IMPLEMENTATION,
    "candidate_publication_audit_contract_version": (
        D1_PUBLICATION_AUDIT_TREE_CONTRACT_VERSION
    ),
    "d2_content_audit_required_before_identity_reuse": True,
    "only_allowed_runtime_treatment_difference": (
        "d1_publication_metadata_implementation"
    ),
    "prior_episode_outputs_reused": False,
    "reference_implementation": REFERENCE_IMPLEMENTATION,
    "same_source_commit_for_both_arms": True,
    "simulation_mode": "three_dimensional_point_mass",
    "system_realtime_requires_real_time_factor_at_least_one": True,
    "truth_is_online_control_input": False,
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
_D2_COUNTER_FIELDS = {
    "metadata_count",
    "shared_subtree_full_audit_count",
    "shared_subtree_equivalent_reuse_count",
    "shared_subtree_builtin_equivalent_reuse_count",
    "immutable_v2_contract_validation_count",
    "immutable_v2_full_content_audit_count",
    "immutable_v2_identity_reuse_count",
    "immutable_v2_contract_rejection_count",
}
_METRICS = _v1._METRICS
_LOWER_IS_BETTER = _v1._LOWER_IS_BETTER
_REQUIRED_ADMISSION_METRICS = {
    "d1_fusion_wall_s",
    "d2_association_wall_s",
    "core_wall_s",
    "maximum_rss_kib",
}

D1PublicationMetadataV2EvidenceError = _v1.D1PublicationMetadataEvidenceError


def load_d1_publication_metadata_v2_evidence_manifest(
    source: str | Path,
) -> _v1.D1PublicationMetadataEvidence:
    """Load and validate the exact preregistered v2 evidence manifest."""

    source_path = Path(source).expanduser().resolve()
    manifest, manifest_raw = _v1._load_strict_json_mapping(source_path)
    _v1._expect_equal(
        manifest.get("schema_version"),
        D1_PUBLICATION_METADATA_V2_EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "v2 evidence manifest schema_version",
    )
    _v1._expect_equal(
        manifest.get("experiment_id"),
        D1_PUBLICATION_METADATA_V2_EXPERIMENT_ID,
        "v2 evidence manifest experiment_id",
    )
    _v1._expect_equal(
        manifest.get("required_d6_evaluator_schema_version"),
        D1_PUBLICATION_METADATA_V2_MULTISEED_EVALUATION_SCHEMA_VERSION,
        "v2 required D6 evaluator schema",
    )
    _v1._expect_equal(
        manifest.get("publication_audit_contract_version"),
        D1_PUBLICATION_AUDIT_TREE_CONTRACT_VERSION,
        "v2 evidence publication audit contract",
    )
    if manifest.get("status") != "episodes_complete_pending_d6":
        raise D1PublicationMetadataV2EvidenceError(
            "v2 evidence status must be episodes_complete_pending_d6"
        )
    _v1._required_text(
        manifest.get("completed_at_utc"),
        "v2 evidence completed_at_utc",
    )
    source_commit = _v1._required_commit(
        manifest.get("source_commit"),
        "v2 evidence source_commit",
    )
    _v1._expect_equal(
        source_commit,
        D1_PUBLICATION_METADATA_V2_SOURCE_COMMIT,
        "v2 frozen source_commit",
    )
    if manifest.get("source_repository_dirty") is not False:
        raise D1PublicationMetadataV2EvidenceError(
            "v2 source_repository_dirty must be false"
        )
    source_worktree = _v1._explicit_path(
        manifest.get("source_worktree"),
        "v2 evidence source_worktree",
        require=None,
    )
    output_root = _v1._explicit_path(
        manifest.get("output_root"),
        "v2 evidence output_root",
        require="directory",
    )
    if source_path.parent != output_root:
        raise D1PublicationMetadataV2EvidenceError(
            "v2 evidence_manifest.json must be directly under output_root"
        )

    matrix_path = _v1._explicit_path(
        manifest.get("matrix_path"),
        "v2 evidence matrix_path",
        require="file",
    )
    matrix_sha256 = _v1._required_sha256(
        manifest.get("matrix_sha256"),
        "v2 evidence matrix_sha256",
    )
    if matrix_sha256 != _v1._file_sha256(matrix_path):
        raise D1PublicationMetadataV2EvidenceError(
            "v2 matrix_sha256 does not match matrix_path bytes"
        )
    if matrix_sha256 != D1_PUBLICATION_METADATA_V2_MATRIX_SHA256:
        raise D1PublicationMetadataV2EvidenceError(
            "v2 matrix_sha256 does not match the frozen matrix"
        )
    matrix, _ = _v1._load_strict_json_mapping(matrix_path)
    _validate_v2_matrix(matrix)
    if _v1._required_mapping(
        manifest.get("matrix"),
        "v2 embedded matrix",
    ) != matrix:
        raise D1PublicationMetadataV2EvidenceError(
            "v2 embedded matrix does not exactly match matrix_path"
        )

    raw_cases = _v1._required_sequence(manifest.get("cases"), "v2 cases")
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise D1PublicationMetadataV2EvidenceError(
            "v2 evidence manifest must contain exactly 13 cases"
        )
    pairs: list[_v1.D1PublicationMetadataPairBinding] = []
    used_paths: set[Path] = {source_path}
    for raw_case, expected in zip(raw_cases, _EXPECTED_CASES, strict=True):
        case = _v1._required_mapping(raw_case, "v2 evidence case")
        metadata = _v1._case_metadata(case)
        if metadata != expected:
            raise D1PublicationMetadataV2EvidenceError(
                "v2 evidence case differs from preregistered order: "
                f"expected {expected!r}, got {metadata!r}"
            )
        case_id, group, seed, duration_s, arm_order = metadata
        if case.get("d6_evaluation_status") != "episodes_complete_pending_d6":
            raise D1PublicationMetadataV2EvidenceError(
                f"{case_id} d6_evaluation_status is not pending D6"
            )
        raw_arms = _v1._required_mapping(case.get("arms"), f"{case_id} arms")
        if set(raw_arms) != set(_ARMS):
            raise D1PublicationMetadataV2EvidenceError(
                f"{case_id} arms must be reference and candidate"
            )
        bindings: dict[str, _v1.D1PublicationMetadataArmBinding] = {}
        commands: dict[str, list[str]] = {}
        for arm in _ARMS:
            record = _v1._required_mapping(
                raw_arms.get(arm),
                f"{case_id} {arm} arm",
            )
            implementation = _IMPLEMENTATIONS[arm]
            _v1._expect_equal(record.get("arm"), arm, f"{case_id} arm label")
            _v1._expect_equal(
                record.get("expected_implementation"),
                implementation,
                f"{case_id} {arm} expected implementation",
            )
            _v1._expect_equal(
                record.get("expected_d1_implementation_id"),
                _IMPLEMENTATION_IDS[arm],
                f"{case_id} {arm} expected D1 implementation_id",
            )
            _v1._expect_equal(
                record.get("expected_commit"),
                source_commit,
                f"{case_id} {arm} expected commit",
            )
            if record.get("status") != "complete":
                raise D1PublicationMetadataV2EvidenceError(
                    f"{case_id} {arm} status must be complete"
                )
            return_code = record.get("return_code")
            if (
                not isinstance(return_code, int)
                or isinstance(return_code, bool)
                or return_code != 0
            ):
                raise D1PublicationMetadataV2EvidenceError(
                    f"{case_id} {arm} return_code must be integer zero"
                )
            episode_dir = _v1._explicit_path(
                record.get("episode_dir"),
                f"{case_id} {arm} episode_dir",
                require="directory",
            )
            resource_path = _v1._explicit_path(
                record.get("resource_path"),
                f"{case_id} {arm} resource_path",
                require="file",
            )
            stdout_path = _v1._explicit_path(
                record.get("stdout_path"),
                f"{case_id} {arm} stdout_path",
                require="file",
            )
            stderr_path = _v1._explicit_path(
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
                _v1._require_under_root(
                    path,
                    output_root,
                    f"{case_id} {arm} {label}",
                )
            for path in (episode_dir, resource_path, stdout_path, stderr_path):
                if path in used_paths:
                    raise D1PublicationMetadataV2EvidenceError(
                        f"duplicate v2 evidence path: {path}"
                    )
                used_paths.add(path)
            command = [
                _v1._required_text(item, f"{case_id} {arm} command item")
                for item in _v1._required_sequence(
                    record.get("command"),
                    f"{case_id} {arm} command",
                )
            ]
            expected_command = _v1._expected_command(
                source_worktree=source_worktree,
                run_flags=tuple(matrix["run_flags"]),
                implementation=implementation,
                duration_s=duration_s,
                seed=seed,
                resource_count=_RESOURCE_COUNT,
                target_count=_TARGET_COUNT,
                recon_count=_RECON_COUNT,
                episode_dir=episode_dir,
            )
            if command != expected_command:
                raise D1PublicationMetadataV2EvidenceError(
                    f"{case_id} {arm} command differs from frozen v2 matrix"
                )
            commands[arm] = command
            bindings[arm] = _v1.D1PublicationMetadataArmBinding(
                arm=arm,
                implementation=implementation,
                episode_dir=episode_dir,
                resource_path=resource_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        _v1._validate_pair_command_isolation(commands, case_id)
        pairs.append(
            _v1.D1PublicationMetadataPairBinding(
                case_id=case_id,
                group=group,
                seed=seed,
                duration_s=duration_s,
                arm_order=arm_order,
                arms=bindings,
            )
        )

    return _v1.D1PublicationMetadataEvidence(
        source_path=source_path,
        source_sha256=_v1._sha256_bytes(manifest_raw),
        matrix_path=matrix_path,
        matrix_sha256=matrix_sha256,
        output_root=output_root,
        source_commit=source_commit,
        source_worktree=source_worktree,
        pairs=pairs,
    )


def evaluate_d1_publication_metadata_v2_multiseed(
    source: str | Path,
) -> dict[str, Any]:
    """Evaluate one complete 13-pair v2 same-clean-commit manifest."""

    evidence = load_d1_publication_metadata_v2_evidence_manifest(source)
    pairs = [_evaluate_v2_pair(pair, evidence) for pair in evidence.pairs]
    groups = {
        group: _summarize_v2_group(
            [pair for pair in pairs if pair["group"] == group],
            group=group,
        )
        for group in _GROUPS
    }
    gates = _v2_admission_gates(pairs, groups)
    admitted = all(bool(gate["passed"]) for gate in gates.values())
    realtime_gate = _v1._system_realtime_gate(pairs)
    return {
        "schema_version": (
            D1_PUBLICATION_METADATA_V2_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": D1_PUBLICATION_METADATA_V2_EVALUATION_DATE,
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "input_contract": {
            "evidence_manifest_path": str(evidence.source_path),
            "evidence_manifest_sha256": evidence.source_sha256,
            "evidence_manifest_schema_version": (
                D1_PUBLICATION_METADATA_V2_EVIDENCE_MANIFEST_SCHEMA_VERSION
            ),
            "evidence_manifest_status": "episodes_complete_pending_d6",
            "matrix_path": str(evidence.matrix_path),
            "matrix_sha256": evidence.matrix_sha256,
            "matrix_schema_version": (
                D1_PUBLICATION_METADATA_V2_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": D1_PUBLICATION_METADATA_V2_EXPERIMENT_ID,
            "output_root": str(evidence.output_root),
            "source_commit": evidence.source_commit,
            "source_repository_dirty": False,
            "same_commit_for_both_arms": True,
            "publication_audit_contract_version": (
                D1_PUBLICATION_AUDIT_TREE_CONTRACT_VERSION
            ),
            "arm_implementations": dict(_IMPLEMENTATIONS),
            "arm_implementation_ids": dict(_IMPLEMENTATION_IDS),
            "pair_count": len(pairs),
            "arm_count": len(pairs) * 2,
            "bootstrap_resamples": _BOOTSTRAP_RESAMPLES,
            "bootstrap_rng_seed": _BOOTSTRAP_RNG_SEED,
            "evidence_boundary": dict(_EXPECTED_BOUNDARY),
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
            "d2_publication_metadata_audit_semantics": (
                "registered_treatment_diagnostic_validated_separately"
            ),
            "business_normalization_boundary": [
                "D1 implementation selector and diagnostics",
                "D2 publication metadata audit counters",
                "treatment-derived episode identity",
                "stage and episode performance fields",
                "prevalidated opaque plan identifiers",
            ],
        },
        "thresholds": dict(_EXPECTED_GATES),
        "pairs": pairs,
        "groups": groups,
        "d2_publication_metadata_audit_aggregate": (
            _aggregate_d2_publication_audit(pairs)
        ),
        "cross_module_attribution": _v2_cross_module_attribution(groups),
        "admission_gates": gates,
        "d1_optimization_admitted": admitted,
        "system_realtime_gate": realtime_gate,
        "system_realtime_gap_closed": bool(realtime_gate["passed"]),
    }


def _validate_v2_matrix(matrix: Mapping[str, Any]) -> None:
    if set(matrix) != _EXPECTED_MATRIX_KEYS:
        raise D1PublicationMetadataV2EvidenceError(
            "v2 matrix fields differ from the frozen contract"
        )
    for field, expected in (
        ("schema_version", D1_PUBLICATION_METADATA_V2_MATRIX_SCHEMA_VERSION),
        ("experiment_id", D1_PUBLICATION_METADATA_V2_EXPERIMENT_ID),
        ("same_clean_commit_required", True),
        ("target_count", _TARGET_COUNT),
        ("resource_count", _RESOURCE_COUNT),
        ("recon_count", _RECON_COUNT),
        ("bootstrap_seed", _BOOTSTRAP_RNG_SEED),
        ("bootstrap_resamples", _BOOTSTRAP_RESAMPLES),
        ("arm_implementations", _IMPLEMENTATIONS),
        ("admission_gates", _EXPECTED_GATES),
        ("evidence_boundary", _EXPECTED_BOUNDARY),
    ):
        _v1._expect_equal(matrix.get(field), expected, f"v2 matrix {field}")
    _v1._expect_finite_equal(
        matrix.get("cooldown_s"),
        2.0,
        "v2 matrix cooldown_s",
    )
    _v1._expect_equal(
        tuple(_v1._required_sequence(matrix.get("run_flags"), "v2 run_flags")),
        _RUN_FLAGS,
        "v2 matrix run_flags",
    )
    cases = tuple(
        _v1._case_metadata(_v1._required_mapping(case, "v2 matrix case"))
        for case in _v1._required_sequence(matrix.get("cases"), "v2 cases")
    )
    _v1._expect_equal(cases, _EXPECTED_CASES, "v2 matrix cases")


def _evaluate_v2_pair(
    pair: _v1.D1PublicationMetadataPairBinding,
    evidence: _v1.D1PublicationMetadataEvidence,
) -> dict[str, Any]:
    reference = _evaluate_v2_arm(
        pair.arms[_REFERENCE_ARM],
        pair=pair,
        expected_commit=evidence.source_commit,
    )
    candidate = _evaluate_v2_arm(
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
        raise D1PublicationMetadataV2EvidenceError(
            f"{pair.case_id} full materialization counts differ"
        )
    d2_pair_audit = _validate_d2_pair_audit(
        reference["d2_publication_metadata_audit"],
        candidate["d2_publication_metadata_audit"],
        context=pair.case_id,
    )
    semantic = _compare_v2_pair_business_semantics(reference, candidate)
    reference.pop("_semantic_input", None)
    candidate.pop("_semantic_input", None)
    performance = {
        metric: _v1._compare_pair_metric(
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
        "d2_publication_metadata_audit": d2_pair_audit,
        "d2_publication_metadata_audit_passed": bool(d2_pair_audit["passed"]),
        "performance": performance,
    }


def _evaluate_v2_arm(
    binding: _v1.D1PublicationMetadataArmBinding,
    *,
    pair: _v1.D1PublicationMetadataPairBinding,
    expected_commit: str,
) -> dict[str, Any]:
    episode = binding.episode_dir
    stderr_audit = _v1._validate_stderr(
        binding.stderr_path,
        f"{pair.case_id} {binding.arm}",
    )
    paths = {
        name: episode / name for name in _v1._CONSUMED_EPISODE_FILES
    }
    for name, path in paths.items():
        if not path.is_file():
            raise D1PublicationMetadataV2EvidenceError(
                f"{pair.case_id} {binding.arm} missing {name}"
            )

    manifest, manifest_raw = _v1._load_strict_json_mapping(
        paths["manifest.json"]
    )
    config, config_raw = _v1._load_strict_json_mapping(
        paths["scenario_config.json"]
    )
    summary, summary_raw = _v1._load_strict_json_mapping(
        paths["summary.json"]
    )
    governance, governance_raw = _v1._load_strict_json_mapping(
        paths["observation_governance_audit.json"]
    )
    _validate_v2_arm_provenance(
        binding,
        pair=pair,
        expected_commit=expected_commit,
        manifest=manifest,
        config=config,
        summary=summary,
        governance=governance,
    )
    d2_audit = _validate_d2_audit_locations(
        binding.arm,
        summary=summary,
        governance=governance,
        context=f"{pair.case_id} {binding.arm}",
    )
    stages = {
        name: _v1._load_stage(paths["stage_timings.csv"], stage_name)
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
    resource = _v1._load_resource_metrics(binding.resource_path)
    _v1._strict_jsonl_digest(paths["online_observations.jsonl"])
    _v1._strict_jsonl_digest(paths["offline_truth_labels.jsonl"])
    _v1._strict_jsonl_digest(paths["offline_proximity_intercepts.jsonl"])
    _v1._validate_truth_state_finite(paths["offline_truth_state.npz"])

    runtime_profile = _v1._required_mapping(
        manifest.get("runtime_profile"),
        f"{pair.case_id} {binding.arm} runtime_profile",
    )
    diagnostics = _v1._required_mapping(
        summary.get("d1_publication_metadata_diagnostics"),
        f"{pair.case_id} {binding.arm} D1 publication diagnostics",
    )
    operation_counts = _v1._required_mapping(
        diagnostics.get("operation_counts"),
        f"{pair.case_id} {binding.arm} D1 publication operation counts",
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
        "core_wall_s": _v1._finite_nonnegative(
            summary.get("wall_time_s"),
            f"{pair.case_id} {binding.arm} summary wall_time_s",
            positive=True,
        ),
        "external_elapsed_s": resource["external_elapsed_s"],
        "maximum_rss_kib": resource["maximum_rss_kib"],
        "real_time_factor": _v1._finite_nonnegative(
            summary.get("real_time_factor"),
            f"{pair.case_id} {binding.arm} real_time_factor",
        ),
    }
    input_sha256 = {
        "manifest.json": _v1._sha256_bytes(manifest_raw),
        "scenario_config.json": _v1._sha256_bytes(config_raw),
        "summary.json": _v1._sha256_bytes(summary_raw),
        "observation_governance_audit.json": _v1._sha256_bytes(
            governance_raw
        ),
        "stage_timings.csv": _v1._file_sha256(paths["stage_timings.csv"]),
        "online_observations.jsonl": _v1._file_sha256(
            paths["online_observations.jsonl"]
        ),
        "offline_truth_state.npz": _v1._file_sha256(
            paths["offline_truth_state.npz"]
        ),
        "offline_truth_labels.jsonl": _v1._file_sha256(
            paths["offline_truth_labels.jsonl"]
        ),
        "offline_proximity_intercepts.jsonl": _v1._file_sha256(
            paths["offline_proximity_intercepts.jsonl"]
        ),
        "resource_usage": _v1._file_sha256(binding.resource_path),
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
        "normalized_runtime_profile_sha256": _v1._canonical_sha256(
            _v1._normalized_runtime_profile(runtime_profile)
        ),
        "normalized_summary_sha256": _v1._canonical_sha256(
            _normalized_v2_summary(summary)
        ),
        "normalized_governance_sha256": _v1._canonical_sha256(
            _normalized_v2_governance(governance)
        ),
        "finite_state": bool(summary["finite_state"]),
        "online_truth_use_count": int(summary["online_truth_use_count"]),
        "implementation_identity_passed": True,
        "implementation_identity_locations": (
            _v2_implementation_identity_locations(
                runtime_profile,
                summary,
                governance,
            )
        ),
        "publication_metadata_diagnostics": copy.deepcopy(diagnostics),
        "publication_metadata_operation_counts": copy.deepcopy(
            operation_counts
        ),
        "publication_audit_contract_version": diagnostics.get(
            "publication_audit_contract_version"
        ),
        "d2_publication_metadata_audit": d2_audit,
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


def _validate_v2_arm_provenance(
    binding: _v1.D1PublicationMetadataArmBinding,
    *,
    pair: _v1.D1PublicationMetadataPairBinding,
    expected_commit: str,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> None:
    context = f"{pair.case_id} {binding.arm}"
    if manifest.get("git_commit") != expected_commit:
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} source commit mismatch"
        )
    if manifest.get("repository_dirty") is not False:
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} repository is dirty"
        )
    if manifest.get("config_sha256") != _v1._canonical_sha256(config):
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} config_sha256 mismatch"
        )
    runtime_profile = _v1._required_mapping(
        manifest.get("runtime_profile"),
        f"{context} runtime_profile",
    )
    if manifest.get("runtime_profile_sha256") != _v1._canonical_sha256(
        runtime_profile
    ):
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} runtime_profile_sha256 mismatch"
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
            raise D1PublicationMetadataV2EvidenceError(
                f"{context} {label} {field} mismatch"
            )
    _v1._expect_finite_equal(
        config.get("duration_s"),
        pair.duration_s,
        f"{context} config duration_s",
    )
    _v1._expect_finite_equal(
        summary.get("simulated_duration_s"),
        pair.duration_s,
        f"{context} summary simulated_duration_s",
    )
    if summary.get("finite_state") is not True:
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} finite_state must be true"
        )
    if summary.get("online_truth_use_count") != 0:
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} online_truth_use_count must be zero"
        )
    if governance.get("online_truth_use_count") != 0:
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} governance online truth count must be zero"
        )
    _validate_v2_implementation_identity(
        binding.arm,
        binding.implementation,
        runtime_profile=runtime_profile,
        summary=summary,
        governance=governance,
        context=context,
    )


def _validate_v2_implementation_identity(
    arm: str,
    expected: str,
    *,
    runtime_profile: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
    context: str,
) -> None:
    configuration = _v1._required_mapping(
        runtime_profile.get("configuration"),
        f"{context} runtime configuration",
    )
    final = _v1._required_mapping(
        summary.get("module_final_diagnostics"),
        f"{context} module_final_diagnostics",
    )
    nested_governance = _v1._required_mapping(
        final.get("observation_governance"),
        f"{context} nested observation_governance",
    )
    selectors = {
        "manifest.runtime_profile": runtime_profile.get(
            "d1_publication_metadata_implementation"
        ),
        "manifest.runtime_profile.configuration": configuration.get(
            "d1_publication_metadata_implementation"
        ),
        "summary": summary.get("d1_publication_metadata_implementation"),
        "summary.module_final_diagnostics": final.get(
            "d1_publication_metadata_implementation"
        ),
        "summary.module_final.observation_governance": nested_governance.get(
            "d1_publication_metadata_implementation"
        ),
        "governance": governance.get("d1_publication_metadata_implementation"),
    }
    mismatches = [
        f"{name}={value!r}"
        for name, value in selectors.items()
        if value != expected
    ]
    if mismatches:
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} implementation identity mismatch: "
            + ", ".join(mismatches)
        )
    diagnostics_locations = (
        _v1._required_mapping(
            summary.get("d1_publication_metadata_diagnostics"),
            f"{context} summary D1 diagnostics",
        ),
        _v1._required_mapping(
            final.get("d1_publication_metadata_diagnostics"),
            f"{context} final D1 diagnostics",
        ),
        _v1._required_mapping(
            nested_governance.get("d1_publication_metadata_diagnostics"),
            f"{context} nested governance D1 diagnostics",
        ),
        _v1._required_mapping(
            governance.get("d1_publication_metadata_diagnostics"),
            f"{context} governance D1 diagnostics",
        ),
    )
    canonical = diagnostics_locations[0]
    for diagnostics in diagnostics_locations:
        if diagnostics != canonical:
            raise D1PublicationMetadataV2EvidenceError(
                f"{context} D1 publication metadata diagnostics mismatch"
            )
        if diagnostics.get("implementation_id") != _IMPLEMENTATION_IDS[arm]:
            raise D1PublicationMetadataV2EvidenceError(
                f"{context} D1 implementation_id mismatch"
            )
        if diagnostics.get("immutable_shared_publication_metadata") is not (
            arm == _CANDIDATE_ARM
        ):
            raise D1PublicationMetadataV2EvidenceError(
                f"{context} immutable publication metadata flag mismatch"
            )
        expected_contract = (
            D1_PUBLICATION_AUDIT_TREE_CONTRACT_VERSION
            if arm == _CANDIDATE_ARM
            else None
        )
        if diagnostics.get("publication_audit_contract_version") != (
            expected_contract
        ):
            raise D1PublicationMetadataV2EvidenceError(
                f"{context} D1 publication audit contract mismatch"
            )
        counts = _v1._required_mapping(
            diagnostics.get("operation_counts"),
            f"{context} D1 operation_counts",
        )
        for key, value in counts.items():
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise D1PublicationMetadataV2EvidenceError(
                    f"{context} D1 operation count {key} is invalid"
                )
        _v1._required_positive_count(
            counts,
            "global_track_metadata_materialization_count",
            context,
        )
        _v1._required_positive_count(
            counts,
            "global_tracks_call_count",
            context,
        )
        _v1._required_positive_count(
            counts,
            "shared_publication_context_build_count",
            context,
        )
        copy_count = int(
            counts.get("per_track_shared_audit_mapping_copy_count", 0)
        )
        reuse_count = int(counts.get("shared_audit_value_reuse_count", 0))
        if arm == _REFERENCE_ARM:
            if copy_count <= 0 or reuse_count != 0:
                raise D1PublicationMetadataV2EvidenceError(
                    f"{context} reference D1 copy/reuse counts are invalid"
                )
            for field in (
                "immutable_shared_contract_validation_count",
                "immutable_shared_contract_validated_node_count",
            ):
                if int(counts.get(field, 0)) != 0:
                    raise D1PublicationMetadataV2EvidenceError(
                        f"{context} reference unexpectedly reports {field}"
                    )
        else:
            if copy_count != 0 or reuse_count <= 0:
                raise D1PublicationMetadataV2EvidenceError(
                    f"{context} candidate D1 copy/reuse counts are invalid"
                )
            for field in (
                "immutable_shared_contract_validation_count",
                "immutable_shared_contract_validated_node_count",
                "immutable_shared_mapping_build_count",
                "immutable_shared_tuple_build_count",
            ):
                _v1._required_positive_count(counts, field, context)


def _v2_implementation_identity_locations(
    runtime_profile: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> dict[str, Any]:
    configuration = _v1._required_mapping(
        runtime_profile["configuration"],
        "v2 runtime profile configuration",
    )
    diagnostics = _v1._required_mapping(
        summary["d1_publication_metadata_diagnostics"],
        "v2 summary D1 diagnostics",
    )
    return {
        "manifest_runtime_profile": runtime_profile[
            "d1_publication_metadata_implementation"
        ],
        "manifest_runtime_configuration": configuration[
            "d1_publication_metadata_implementation"
        ],
        "summary_top_level": summary["d1_publication_metadata_implementation"],
        "summary_implementation_id": diagnostics["implementation_id"],
        "summary_publication_audit_contract_version": diagnostics[
            "publication_audit_contract_version"
        ],
        "governance_top_level": governance[
            "d1_publication_metadata_implementation"
        ],
    }


def _validate_d2_audit_locations(
    arm: str,
    *,
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
    context: str,
) -> dict[str, Any]:
    final = _v1._required_mapping(
        summary.get("module_final_diagnostics"),
        f"{context} module_final_diagnostics",
    )
    nested_governance = _v1._required_mapping(
        final.get("observation_governance"),
        f"{context} nested observation_governance",
    )
    locations = {
        "summary": _v1._required_mapping(
            summary.get("d2_publication_metadata_audit"),
            f"{context} summary D2 publication audit",
        ),
        "summary.module_final_diagnostics": _v1._required_mapping(
            final.get("d2_publication_metadata_audit"),
            f"{context} final D2 publication audit",
        ),
        "summary.module_final.observation_governance": _v1._required_mapping(
            nested_governance.get("d2_publication_metadata_audit"),
            f"{context} nested governance D2 publication audit",
        ),
        "governance": _v1._required_mapping(
            governance.get("d2_publication_metadata_audit"),
            f"{context} governance D2 publication audit",
        ),
    }
    canonical = locations["summary"]
    for name, audit in locations.items():
        if audit != canonical:
            raise D1PublicationMetadataV2EvidenceError(
                f"{context} D2 publication audit location mismatch at {name}"
            )
    validated = _validate_d2_audit_payload(
        canonical,
        candidate=(arm == _CANDIDATE_ARM),
        context=context,
    )
    validated["validated_locations"] = list(locations)
    return validated


def _validate_d2_audit_payload(
    value: Mapping[str, Any],
    *,
    candidate: bool,
    context: str,
) -> dict[str, Any]:
    if set(value) != {"schema_version", "batch_count", "latest", "totals"}:
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} D2 publication audit fields differ from contract"
        )
    if value.get("schema_version") != (
        D2_PUBLICATION_METADATA_AUDIT_SCHEMA_VERSION
    ):
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} D2 publication audit schema mismatch"
        )
    batch_count = _positive_integer(
        value.get("batch_count"),
        f"{context} D2 audit batch_count",
    )
    sections: dict[str, dict[str, int]] = {}
    for section_name in ("latest", "totals"):
        raw = _v1._required_mapping(
            value.get(section_name),
            f"{context} D2 audit {section_name}",
        )
        if set(raw) != _D2_COUNTER_FIELDS:
            raise D1PublicationMetadataV2EvidenceError(
                f"{context} D2 audit {section_name} counter fields differ"
            )
        counters: dict[str, int] = {}
        for field in sorted(_D2_COUNTER_FIELDS):
            counter = raw.get(field)
            if (
                not isinstance(counter, int)
                or isinstance(counter, bool)
                or counter < 0
            ):
                raise D1PublicationMetadataV2EvidenceError(
                    f"{context} D2 audit {section_name}.{field} is invalid"
                )
            counters[field] = counter
        if counters["metadata_count"] <= 0:
            raise D1PublicationMetadataV2EvidenceError(
                f"{context} D2 audit {section_name} metadata_count must be positive"
            )
        if counters["shared_subtree_full_audit_count"] <= 0:
            raise D1PublicationMetadataV2EvidenceError(
                f"{context} D2 audit {section_name} full audit must be positive"
            )
        if candidate:
            validation = counters[
                "immutable_v2_contract_validation_count"
            ]
            content = counters["immutable_v2_full_content_audit_count"]
            full = counters["shared_subtree_full_audit_count"]
            if validation <= 0 or validation != content or content != full:
                raise D1PublicationMetadataV2EvidenceError(
                    f"{context} candidate D2 v2 validation/content counts mismatch"
                )
            if counters["immutable_v2_identity_reuse_count"] <= 0:
                raise D1PublicationMetadataV2EvidenceError(
                    f"{context} candidate D2 identity reuse must be positive"
                )
            if counters["shared_subtree_builtin_equivalent_reuse_count"] != 0:
                raise D1PublicationMetadataV2EvidenceError(
                    f"{context} candidate D2 built-in reuse must be zero"
                )
            if counters["shared_subtree_equivalent_reuse_count"] != 0:
                raise D1PublicationMetadataV2EvidenceError(
                    f"{context} candidate D2 equivalent reuse must be zero"
                )
            if counters["immutable_v2_contract_rejection_count"] != 0:
                raise D1PublicationMetadataV2EvidenceError(
                    f"{context} candidate D2 contract rejection must be zero"
                )
        else:
            if counters["shared_subtree_builtin_equivalent_reuse_count"] <= 0:
                raise D1PublicationMetadataV2EvidenceError(
                    f"{context} reference D2 built-in reuse must be positive"
                )
            if counters["shared_subtree_equivalent_reuse_count"] != counters[
                "shared_subtree_builtin_equivalent_reuse_count"
            ]:
                raise D1PublicationMetadataV2EvidenceError(
                    f"{context} reference D2 equivalent reuse mismatch"
                )
            for field in (
                "immutable_v2_contract_validation_count",
                "immutable_v2_full_content_audit_count",
                "immutable_v2_identity_reuse_count",
                "immutable_v2_contract_rejection_count",
            ):
                if counters[field] != 0:
                    raise D1PublicationMetadataV2EvidenceError(
                        f"{context} reference D2 {field} must be zero"
                    )
        sections[section_name] = counters
    latest = sections["latest"]
    totals = sections["totals"]
    if totals["metadata_count"] < latest["metadata_count"]:
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} D2 total metadata_count is below latest batch"
        )
    if totals["shared_subtree_full_audit_count"] != (
        batch_count * latest["shared_subtree_full_audit_count"]
    ):
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} D2 full audit total is inconsistent with batch_count"
        )
    if candidate:
        for field in (
            "immutable_v2_contract_validation_count",
            "immutable_v2_full_content_audit_count",
        ):
            if totals[field] != batch_count * latest[field]:
                raise D1PublicationMetadataV2EvidenceError(
                    f"{context} D2 {field} total is inconsistent with batches"
                )
    return {
        "schema_version": D2_PUBLICATION_METADATA_AUDIT_SCHEMA_VERSION,
        "treatment_diagnostic": True,
        "passed": True,
        "arm_semantics": (
            "immutable_v2_identity_reuse"
            if candidate
            else "builtin_equivalent_reuse"
        ),
        "batch_count": batch_count,
        "latest": sections["latest"],
        "totals": sections["totals"],
    }


def _validate_d2_pair_audit(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    context: str,
) -> dict[str, Any]:
    ref_latest = _v1._required_mapping(
        reference.get("latest"),
        f"{context} reference D2 latest",
    )
    cand_latest = _v1._required_mapping(
        candidate.get("latest"),
        f"{context} candidate D2 latest",
    )
    ref_totals = _v1._required_mapping(
        reference.get("totals"),
        f"{context} reference D2 totals",
    )
    cand_totals = _v1._required_mapping(
        candidate.get("totals"),
        f"{context} candidate D2 totals",
    )
    checks = {
        "batch_count_equal": (
            int(reference["batch_count"]) == int(candidate["batch_count"])
        ),
        "latest_metadata_count_equal": (
            ref_latest["metadata_count"] == cand_latest["metadata_count"]
        ),
        "total_metadata_count_equal": (
            ref_totals["metadata_count"] == cand_totals["metadata_count"]
        ),
        "latest_full_audit_count_equal": (
            ref_latest["shared_subtree_full_audit_count"]
            == cand_latest["shared_subtree_full_audit_count"]
        ),
        "total_full_audit_count_equal": (
            ref_totals["shared_subtree_full_audit_count"]
            == cand_totals["shared_subtree_full_audit_count"]
        ),
        "latest_reuse_workload_equal": (
            ref_latest["shared_subtree_builtin_equivalent_reuse_count"]
            == cand_latest["immutable_v2_identity_reuse_count"]
        ),
        "total_reuse_workload_equal": (
            ref_totals["shared_subtree_builtin_equivalent_reuse_count"]
            == cand_totals["immutable_v2_identity_reuse_count"]
        ),
    }
    if not all(checks.values()):
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} D2 publication audit cross-arm workload mismatch"
        )
    return {
        "passed": True,
        "checks": checks,
        "normalization_scope": (
            "d2_publication_metadata_audit_only"
        ),
    }


def _positive_integer(value: Any, context: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
    ):
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} must be a positive integer"
        )
    return value


def _normalized_v2_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(summary))
    if "episode_id" not in normalized:
        raise D1PublicationMetadataV2EvidenceError(
            "normalized v2 summary lacks episode_id"
        )
    normalized["episode_id"] = _v1._TREATMENT_DERIVED_ID_MARKER
    normalized["wall_time_s"] = _v1._PERFORMANCE_MARKER
    normalized["real_time_factor"] = _v1._PERFORMANCE_MARKER
    _v1._normalize_publication_metadata_fields(
        normalized,
        "normalized v2 summary",
    )
    _normalize_d2_audit_field(normalized, "normalized v2 summary")
    final = _v1._mutable_mapping(
        normalized.get("module_final_diagnostics"),
        "normalized v2 module_final_diagnostics",
    )
    _v1._normalize_publication_metadata_fields(
        final,
        "normalized v2 module final",
    )
    _normalize_d2_audit_field(final, "normalized v2 module final")
    if "stage_timings" not in final:
        raise D1PublicationMetadataV2EvidenceError(
            "normalized v2 module final lacks stage_timings"
        )
    final["stage_timings"] = _v1._PERFORMANCE_MARKER
    nested_governance = _v1._required_mapping(
        final.get("observation_governance"),
        "normalized v2 nested observation governance",
    )
    final["observation_governance"] = _normalized_v2_governance(
        nested_governance
    )
    return normalized


def _normalized_v2_governance(
    governance: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(governance))
    _v1._normalize_publication_metadata_fields(
        normalized,
        "normalized v2 governance",
    )
    _normalize_d2_audit_field(normalized, "normalized v2 governance")
    fusion = normalized.get("d1_fusion_association")
    if isinstance(fusion, dict) and (
        "association_innovation_solve_count" in fusion
    ):
        fusion["association_innovation_solve_count"] = _v1._PERFORMANCE_MARKER
    return normalized


def _normalize_d2_audit_field(
    mapping: dict[str, Any],
    context: str,
) -> None:
    if "d2_publication_metadata_audit" not in mapping:
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} lacks d2_publication_metadata_audit"
        )
    audit = mapping["d2_publication_metadata_audit"]
    if not isinstance(audit, dict):
        raise D1PublicationMetadataV2EvidenceError(
            f"{context} D2 audit must be a mapping"
        )
    mapping["d2_publication_metadata_audit"] = {
        "value": _PUBLICATION_AUDIT_MARKER
    }


def _compare_v2_pair_business_semantics(
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
        raise D1PublicationMetadataV2EvidenceError(
            "main cross-build reader returned an unsupported schema"
        )
    cross_checks = _v1._required_mapping(cross.get("checks"), "cross checks")
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
        "d2_audit_normalization": {
            "scope": "d2_publication_metadata_audit_only",
            "other_summary_fields_ignored": False,
            "audit_validated_separately": True,
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


def _summarize_v2_group(
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
            bool(pair["implementation_identity_passed"])
            for pair in ordered
        ),
        "d2_publication_metadata_audit_pass_count": sum(
            bool(pair["d2_publication_metadata_audit_passed"])
            for pair in ordered
        ),
        "metrics": {
            metric: _v1._summarize_group_metric(ordered, metric=metric)
            for metric in _METRICS
        },
    }


def _v2_admission_gates(
    pairs: Sequence[Mapping[str, Any]],
    groups: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    short = groups["short"]
    long = groups["long"]
    short_fusion = short["metrics"]["d1_fusion_wall_s"]
    long_fusion = long["metrics"]["d1_fusion_wall_s"]
    short_core = short["metrics"]["core_wall_s"]
    long_core = long["metrics"]["core_wall_s"]
    short_d2 = short["metrics"]["d2_association_wall_s"]
    long_d2 = long["metrics"]["d2_association_wall_s"]
    rss_groups = [
        groups[group]["metrics"]["maximum_rss_kib"] for group in _GROUPS
    ]
    pair_count = len(pairs)
    semantic_count = sum(
        bool(pair["business_semantics_passed"]) for pair in pairs
    )
    finite_count = sum(bool(pair["finite_state_passed"]) for pair in pairs)
    truth_count = sum(bool(pair["truth_isolation_passed"]) for pair in pairs)
    identity_count = sum(
        bool(pair["implementation_identity_passed"]) for pair in pairs
    )
    audit_count = sum(
        bool(pair["d2_publication_metadata_audit_passed"]) for pair in pairs
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
        short_fusion["raw_relative_change"]["bootstrap_95_ci"]["upper"]
        * 100.0
    )
    short_d2_increase_pct = (
        short_d2["raw_relative_change"]["mean"] * 100.0
    )
    long_d2_increase_pct = (
        long_d2["raw_relative_change"]["mean"] * 100.0
    )
    rss_mean_increase_pct = max(
        summary["raw_relative_change"]["mean"] * 100.0
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
    return {
        "all_pairs_business_semantics_equal": _detailed_gate(
            actual=semantic_count,
            threshold=pair_count,
            comparator="==",
            passed=(pair_count == 13 and semantic_count == pair_count),
            reason="one_or_more_pair_business_semantics_mismatch",
        ),
        "all_pairs_finite_state": _detailed_gate(
            actual=finite_count,
            threshold=pair_count,
            comparator="==",
            passed=(pair_count == 13 and finite_count == pair_count),
            reason="one_or_more_pair_finite_state_check_failed",
        ),
        "all_pairs_online_truth_use_count_zero": _detailed_gate(
            actual=truth_count,
            threshold=pair_count,
            comparator="==",
            passed=(pair_count == 13 and truth_count == pair_count),
            reason="one_or_more_pair_online_truth_isolation_failed",
        ),
        "all_pairs_explicit_implementation_identity": _detailed_gate(
            actual=identity_count,
            threshold=pair_count,
            comparator="==",
            passed=(pair_count == 13 and identity_count == pair_count),
            reason="one_or_more_arm_implementation_identity_failed",
        ),
        "all_pairs_d2_publication_metadata_audit_valid": _detailed_gate(
            actual=audit_count,
            threshold=pair_count,
            comparator="==",
            passed=(pair_count == 13 and audit_count == pair_count),
            reason="one_or_more_pair_d2_publication_audit_failed",
        ),
        "required_performance_metrics_available": _detailed_gate(
            actual=required_metric_count,
            threshold=pair_count,
            comparator="==",
            passed=(
                pair_count == 13 and required_metric_count == pair_count
            ),
            reason="one_or_more_required_performance_metrics_unavailable",
        ),
        "short_candidate_faster_at_least_8_of_10": _detailed_gate(
            actual=short_fusion["candidate_better_count"],
            threshold=_EXPECTED_GATES[
                "short_minimum_candidate_faster_count"
            ],
            comparator=">=",
            passed=(
                short_fusion["candidate_better_count"]
                >= _EXPECTED_GATES[
                    "short_minimum_candidate_faster_count"
                ]
            ),
            reason="short_candidate_faster_count_below_8",
        ),
        "short_d1_fusion_mean_improvement_at_least_10_pct": _detailed_gate(
            actual=short_fusion["improvement_pct"]["mean"],
            threshold=_EXPECTED_GATES[
                "short_minimum_d1_fusion_improvement_pct"
            ],
            comparator=">=",
            passed=(
                short_fusion["improvement_pct"]["mean"]
                >= _EXPECTED_GATES[
                    "short_minimum_d1_fusion_improvement_pct"
                ]
            ),
            unit="pct",
            reason="short_d1_fusion_mean_improvement_below_10_pct",
        ),
        "short_d1_fusion_bootstrap_raw_ci_upper_at_most_zero": (
            _detailed_gate(
                actual=short_bootstrap_upper_pct,
                threshold=_EXPECTED_GATES[
                    "short_bootstrap_relative_change_upper_bound_pct"
                ],
                comparator="<=",
                passed=(
                    short_bootstrap_upper_pct
                    <= _EXPECTED_GATES[
                        "short_bootstrap_relative_change_upper_bound_pct"
                    ]
                ),
                unit="pct",
                reason=(
                    "short_d1_fusion_bootstrap_raw_ci_upper_above_zero"
                ),
            )
        ),
        "long_candidate_faster_at_least_2_of_3": _detailed_gate(
            actual=long_fusion["candidate_better_count"],
            threshold=_EXPECTED_GATES[
                "long_minimum_candidate_faster_count"
            ],
            comparator=">=",
            passed=(
                long_fusion["candidate_better_count"]
                >= _EXPECTED_GATES[
                    "long_minimum_candidate_faster_count"
                ]
            ),
            reason="long_candidate_faster_count_below_2",
        ),
        "long_d1_fusion_mean_improvement_at_least_10_pct": _detailed_gate(
            actual=long_fusion["improvement_pct"]["mean"],
            threshold=_EXPECTED_GATES[
                "long_minimum_d1_fusion_improvement_pct"
            ],
            comparator=">=",
            passed=(
                long_fusion["improvement_pct"]["mean"]
                >= _EXPECTED_GATES[
                    "long_minimum_d1_fusion_improvement_pct"
                ]
            ),
            unit="pct",
            reason="long_d1_fusion_mean_improvement_below_10_pct",
        ),
        "short_core_wall_mean_improvement_at_least_5_pct": _detailed_gate(
            actual=short_core["improvement_pct"]["mean"],
            threshold=_EXPECTED_GATES[
                "short_minimum_core_wall_improvement_pct"
            ],
            comparator=">=",
            passed=(
                short_core["improvement_pct"]["mean"]
                >= _EXPECTED_GATES[
                    "short_minimum_core_wall_improvement_pct"
                ]
            ),
            unit="pct",
            reason="short_core_wall_mean_improvement_below_5_pct",
        ),
        "long_core_wall_mean_improvement_at_least_5_pct": _detailed_gate(
            actual=long_core["improvement_pct"]["mean"],
            threshold=_EXPECTED_GATES[
                "long_minimum_core_wall_improvement_pct"
            ],
            comparator=">=",
            passed=(
                long_core["improvement_pct"]["mean"]
                >= _EXPECTED_GATES[
                    "long_minimum_core_wall_improvement_pct"
                ]
            ),
            unit="pct",
            reason="long_core_wall_mean_improvement_below_5_pct",
        ),
        "short_d2_association_mean_increase_at_most_5_pct": _detailed_gate(
            actual=short_d2_increase_pct,
            threshold=_EXPECTED_GATES[
                "maximum_short_d2_association_mean_increase_pct"
            ],
            comparator="<=",
            passed=(
                short_d2_increase_pct
                <= _EXPECTED_GATES[
                    "maximum_short_d2_association_mean_increase_pct"
                ]
            ),
            unit="pct",
            reason="short_d2_association_mean_increase_above_5_pct",
        ),
        "long_d2_association_mean_increase_at_most_5_pct": _detailed_gate(
            actual=long_d2_increase_pct,
            threshold=_EXPECTED_GATES[
                "maximum_long_d2_association_mean_increase_pct"
            ],
            comparator="<=",
            passed=(
                long_d2_increase_pct
                <= _EXPECTED_GATES[
                    "maximum_long_d2_association_mean_increase_pct"
                ]
            ),
            unit="pct",
            reason="long_d2_association_mean_increase_above_5_pct",
        ),
        "rss_mean_degradation_within_5_pct": _detailed_gate(
            actual=rss_mean_increase_pct,
            threshold=_EXPECTED_GATES[
                "maximum_rss_mean_increase_pct"
            ],
            comparator="<=",
            passed=(
                rss_mean_increase_pct
                <= _EXPECTED_GATES[
                    "maximum_rss_mean_increase_pct"
                ]
            ),
            unit="pct",
            reason="short_or_long_rss_mean_degradation_above_5_pct",
        ),
        "every_pair_rss_degradation_within_5_pct": _detailed_gate(
            actual=maximum_pair_rss_increase_pct,
            threshold=_EXPECTED_GATES[
                "maximum_any_pair_rss_increase_pct"
            ],
            comparator="<=",
            passed=(
                maximum_pair_rss_increase_pct
                <= _EXPECTED_GATES[
                    "maximum_any_pair_rss_increase_pct"
                ]
            ),
            unit="pct",
            reason="one_or_more_pair_rss_degradation_above_5_pct",
        ),
    }


def _detailed_gate(
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


def _aggregate_d2_publication_audit(
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "schema_version": D2_PUBLICATION_METADATA_AUDIT_SCHEMA_VERSION,
        "pair_count": len(pairs),
        "treatment_diagnostic": True,
        "arms": {},
    }
    for arm in _ARMS:
        arm_items = [
            _v1._required_mapping(
                pair[arm]["d2_publication_metadata_audit"],
                f"aggregate {arm} D2 audit",
            )
            for pair in pairs
        ]
        output["arms"][arm] = {
            "batch_count": sum(int(item["batch_count"]) for item in arm_items),
            "totals": {
                field: sum(
                    int(
                        _v1._required_mapping(
                            item["totals"],
                            f"aggregate {arm} totals",
                        )[field]
                    )
                    for item in arm_items
                )
                for field in sorted(_D2_COUNTER_FIELDS)
            },
        }
    return output


def _v2_cross_module_attribution(
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
        "mechanism_evidence": {
            "candidate_contract": (
                D1_PUBLICATION_AUDIT_TREE_CONTRACT_VERSION
            ),
            "candidate_d2_behavior": (
                "one structural validation and one content audit per new "
                "shared root, followed by identity reuse"
            ),
            "reference_d2_behavior": (
                "full content audit followed by built-in equivalent reuse"
            ),
            "business_comparison_rule": (
                "only D2 publication-audit counters are normalized; all "
                "other summary and governance fields remain compared"
            ),
        },
    }


def write_d1_publication_metadata_v2_multiseed_report(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write compact v2 evaluation products outside the raw evidence root."""

    if result.get("schema_version") != (
        D1_PUBLICATION_METADATA_V2_MULTISEED_EVALUATION_SCHEMA_VERSION
    ):
        raise ValueError("unsupported D1 publication-metadata v2 schema")
    contract = _v1._required_mapping(
        result.get("input_contract"),
        "v2 evaluation input_contract",
    )
    evidence_root = Path(
        _v1._required_text(
            contract.get("output_root"),
            "v2 evidence output_root",
        )
    ).expanduser().resolve()
    directory = Path(output_dir).expanduser().resolve()
    if _v1._path_is_within(directory, evidence_root):
        raise ValueError(
            "v2 report output_dir must be independent of evidence root"
        )
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "evaluation_json": directory
        / "d1_publication_metadata_v2_multiseed_evaluation.json",
        "aggregate_json": directory
        / "d1_publication_metadata_v2_multiseed_aggregate.json",
        "pairs_csv": directory
        / "d1_publication_metadata_v2_multiseed_pairs.csv",
        "markdown": directory
        / "D1_PUBLICATION_METADATA_V2_MULTISEED_EVALUATION_CN.md",
        "plot_png": directory
        / "d1_publication_metadata_v2_multiseed_curves.png",
    }
    paths["evaluation_json"].write_text(
        _v1._json_text(result),
        encoding="utf-8",
    )
    paths["aggregate_json"].write_text(
        _v1._json_text(_v2_aggregate_output(result)),
        encoding="utf-8",
    )
    _write_v2_pair_csv(result, paths["pairs_csv"])
    paths["markdown"].write_text(
        render_d1_publication_metadata_v2_multiseed_markdown(result),
        encoding="utf-8",
    )
    _write_v2_plot(result, paths["plot_png"])
    checksum_path = directory / "SHA256SUMS"
    checksum_path.write_text(
        "".join(
            f"{_v1._file_sha256(path)}  {path.name}\n"
            for path in paths.values()
        ),
        encoding="ascii",
    )
    paths["sha256sums"] = checksum_path
    return paths


def _v2_aggregate_output(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": (
            D1_PUBLICATION_METADATA_V2_MULTISEED_AGGREGATE_SCHEMA_VERSION
        ),
        "evaluation_schema_version": result["schema_version"],
        "evaluation_date": result["evaluation_date"],
        "input_contract": result["input_contract"],
        "scope": result["scope"],
        "groups": result["groups"],
        "d2_publication_metadata_audit_aggregate": result[
            "d2_publication_metadata_audit_aggregate"
        ],
        "admission_gates": result["admission_gates"],
        "d1_optimization_admitted": result["d1_optimization_admitted"],
        "system_realtime_gate": result["system_realtime_gate"],
        "system_realtime_gap_closed": result["system_realtime_gap_closed"],
    }


def render_d1_publication_metadata_v2_multiseed_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the formal Chinese v2 admission report."""

    contract = _v1._required_mapping(result["input_contract"], "input contract")
    groups = _v1._required_mapping(result["groups"], "groups")
    gates = _v1._required_mapping(result["admission_gates"], "gates")
    realtime = _v1._required_mapping(
        result["system_realtime_gate"],
        "system realtime gate",
    )
    d2_aggregate = _v1._required_mapping(
        result["d2_publication_metadata_audit_aggregate"],
        "D2 audit aggregate",
    )
    admitted_text = (
        "通过" if result["d1_optimization_admitted"] else "不通过"
    )
    realtime_text = (
        "关闭" if result["system_realtime_gap_closed"] else "未关闭"
    )
    lines = [
        "# D1 发布元数据 v2 同提交多种子评估",
        "",
        "## 结论",
        "",
        (
            f"D1 局部优化正式准入结论为 **{admitted_text}**。"
            f"系统实时缺口 **{realtime_text}**。两项结论相互独立。"
        ),
        (
            f"候选臂最低实时因子为 "
            f"`{_fmt_number(realtime['candidate_minimum_real_time_factor'])}`，"
            "系统门限为 `>=1.0`。本次证据来自三维质点仿真，"
            "不属于 AirSim、目标硬件或实飞证据。"
        ),
        "",
        "## 证据范围",
        "",
        f"- 验证日期：`{result['evaluation_date']}`。",
        f"- clean commit：`{contract['source_commit']}`。",
        (
            f"- 规模：{_TARGET_COUNT} 个目标、{_RESOURCE_COUNT} 个资源、"
            f"{_RECON_COUNT} 个侦察节点。"
        ),
        (
            f"- 短时组：{len(_SHORT_SEEDS)} 对，单臂 "
            f"{_SHORT_DURATION_S} 秒；长时组：{len(_LONG_SEEDS)} 对，"
            f"单臂 {_LONG_DURATION_S} 秒。共 13 pair、26 arm。"
        ),
        (
            f"- 参考实现：`{REFERENCE_IMPLEMENTATION}`；候选实现："
            f"`{CANDIDATE_IMPLEMENTATION}`。候选合同为 "
            f"`{D1_PUBLICATION_AUDIT_TREE_CONTRACT_VERSION}`。"
        ),
        f"- 冻结矩阵 SHA256：`{contract['matrix_sha256']}`。",
        (
            "- 回归：v1/v2 专项 `37 passed, 1 warning`；D6 全量 "
            "`771 passed, 1 warning in 47.61s`。warning 为既有 "
            "Matplotlib `Axes3D` 环境提示。"
        ),
        "",
        "## 性能结果",
        "",
        "| 组别 | 指标 | 参考均值 | 候选均值 | 配对改善均值 | 候选更快 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    metric_labels = (
        ("d1_fusion_wall_s", "D1 融合墙钟"),
        ("d2_association_wall_s", "D2 关联墙钟"),
        ("core_wall_s", "核心墙钟"),
        ("maximum_rss_kib", "最大常驻内存"),
    )
    for group in _GROUPS:
        label = "短时" if group == "short" else "长时"
        for metric, metric_label in metric_labels:
            summary = groups[group]["metrics"][metric]
            lines.append(
                "| "
                f"{label} | {metric_label} | "
                f"{_fmt_number(summary['reference']['mean'])} | "
                f"{_fmt_number(summary['candidate']['mean'])} | "
                f"{_fmt_number(summary['improvement_pct']['mean'])}% | "
                f"{summary['candidate_better_count']}/{summary['pair_count']} |"
            )
    lines.extend(
        [
            "",
            "D2 关联增幅使用 `(候选-参考)/参考` 的逐 pair 均值判定。",
            "负值表示候选更快。该指标没有被并入 D1 融合改善，单独执行 "
            "`<=5%` 门限。",
            "",
            "## D2 审计",
            "",
            (
                "D2 审计计数属于处理差异诊断。业务等价比较只替换 "
                "`d2_publication_metadata_audit` 字段，其余 summary 和治理字段"
                "继续逐项比较。审计字段随后在 summary、模块最终诊断、嵌套治理"
                "和独立治理文件四处执行一致性校验。"
            ),
            "",
            "| 臂 | 批次数 | 完整审计 | v2 合同校验 | v2 内容审计 | "
            "身份复用 | 内建等价复用 | 拒绝 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    arms = _v1._required_mapping(d2_aggregate["arms"], "D2 aggregate arms")
    for arm in _ARMS:
        item = _v1._required_mapping(arms[arm], f"{arm} D2 aggregate")
        totals = _v1._required_mapping(item["totals"], f"{arm} D2 totals")
        lines.append(
            f"| {arm} | {item['batch_count']} | "
            f"{totals['shared_subtree_full_audit_count']} | "
            f"{totals['immutable_v2_contract_validation_count']} | "
            f"{totals['immutable_v2_full_content_audit_count']} | "
            f"{totals['immutable_v2_identity_reuse_count']} | "
            f"{totals['shared_subtree_builtin_equivalent_reuse_count']} | "
            f"{totals['immutable_v2_contract_rejection_count']} |"
        )
    lines.extend(
        [
            "",
            "## 准入门",
            "",
            "| 准入门 | 实际值 | 判据 | 结果 |",
            "|---|---:|---:|---:|",
        ]
    )
    for name in sorted(gates):
        raw_gate = gates[name]
        gate = _v1._required_mapping(raw_gate, f"gate {name}")
        unit = "%" if gate.get("unit") == "pct" else ""
        lines.append(
            f"| `{name}` | {_fmt_number(gate['actual'])}{unit} | "
            f"`{gate['comparator']} {_fmt_number(gate['threshold'])}{unit}` | "
            f"{'通过' if gate['passed'] else '失败'} |"
        )
    lines.extend(
        [
            "",
            "## 逐对结果",
            "",
            "| case | D1 改善 | D2 增幅 | 核心改善 | RSS 增幅 | 语义 | 审计 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for pair in result["pairs"]:
        performance = pair["performance"]
        lines.append(
            f"| {pair['case_id']} | "
            f"{_fmt_number(performance['d1_fusion_wall_s']['improvement_pct'])}% | "
            f"{_fmt_number(performance['d2_association_wall_s']['raw_relative_change_pct'])}% | "
            f"{_fmt_number(performance['core_wall_s']['improvement_pct'])}% | "
            f"{_fmt_number(performance['maximum_rss_kib']['raw_relative_change_pct'])}% | "
            f"{'通过' if pair['business_semantics_passed'] else '失败'} | "
            f"{'通过' if pair['d2_publication_metadata_audit_passed'] else '失败'} |"
        )
    lines.extend(
        [
            "",
            "## 限制",
            "",
            (
                "持久化审计只提供最近批次和累计计数。评估器通过批次数与累计"
                "完整审计数的一致关系检查每批固定审计工作量，但没有逐批明细"
                "可以重放。该限制不影响本次计数合同判定，后续若要定位单批异常，"
                "producer 仍需增加逐批审计日志。"
            ),
            (
                "本次只回答发布元数据 v2 在冻结 200 对 200 三维质点场景中的"
                "局部准入。系统实时、AirSim 和目标处理器上的运行证据继续开放。"
            ),
            "",
            "## 制品",
            "",
            "- `d1_publication_metadata_v2_multiseed_evaluation.json`：完整评估。",
            "- `d1_publication_metadata_v2_multiseed_aggregate.json`：紧凑汇总。",
            "- `d1_publication_metadata_v2_multiseed_pairs.csv`：逐 pair 指标。",
            "- `d1_publication_metadata_v2_multiseed_curves.png`：性能曲线。",
            "- `SHA256SUMS`：制品校验值。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_v2_pair_csv(result: Mapping[str, Any], path: Path) -> None:
    fieldnames = [
        "case_id",
        "group",
        "seed",
        "duration_s",
        "business_semantics_passed",
        "finite_state_passed",
        "truth_isolation_passed",
        "implementation_identity_passed",
        "d2_publication_metadata_audit_passed",
        "reference_d2_batch_count",
        "candidate_d2_batch_count",
        "reference_d2_full_audit_total",
        "candidate_d2_contract_validation_total",
        "candidate_d2_full_content_audit_total",
        "candidate_d2_identity_reuse_total",
        "reference_d2_builtin_reuse_total",
        "candidate_d2_contract_rejection_total",
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
            ref_audit = pair["reference"]["d2_publication_metadata_audit"]
            cand_audit = pair["candidate"]["d2_publication_metadata_audit"]
            ref_totals = ref_audit["totals"]
            cand_totals = cand_audit["totals"]
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
                "d2_publication_metadata_audit_passed": pair[
                    "d2_publication_metadata_audit_passed"
                ],
                "reference_d2_batch_count": ref_audit["batch_count"],
                "candidate_d2_batch_count": cand_audit["batch_count"],
                "reference_d2_full_audit_total": ref_totals[
                    "shared_subtree_full_audit_count"
                ],
                "candidate_d2_contract_validation_total": cand_totals[
                    "immutable_v2_contract_validation_count"
                ],
                "candidate_d2_full_content_audit_total": cand_totals[
                    "immutable_v2_full_content_audit_count"
                ],
                "candidate_d2_identity_reuse_total": cand_totals[
                    "immutable_v2_identity_reuse_count"
                ],
                "reference_d2_builtin_reuse_total": ref_totals[
                    "shared_subtree_builtin_equivalent_reuse_count"
                ],
                "candidate_d2_contract_rejection_total": cand_totals[
                    "immutable_v2_contract_rejection_count"
                ],
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


def _write_v2_plot(result: Mapping[str, Any], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pairs = list(result["pairs"])
    labels = [str(pair["case_id"]).replace("_seed_", "\n") for pair in pairs]
    x = list(range(len(pairs)))
    fig, (performance_axis, realtime_axis) = plt.subplots(
        2,
        1,
        figsize=(11.0, 7.2),
        sharex=True,
        gridspec_kw={"height_ratios": [2.0, 1.0]},
    )
    for metric, label, color in (
        ("d1_fusion_wall_s", "D1 fusion", "#1f77b4"),
        ("d2_association_wall_s", "D2 association", "#ff7f0e"),
        ("core_wall_s", "Core wall", "#2ca02c"),
    ):
        performance_axis.plot(
            x,
            [
                float(pair["performance"][metric]["improvement_pct"])
                for pair in pairs
            ],
            marker="o",
            linewidth=1.5,
            label=label,
            color=color,
        )
    performance_axis.axhline(
        10.0,
        color="#1f77b4",
        linewidth=0.9,
        linestyle="--",
        alpha=0.7,
        label="D1 threshold 10%",
    )
    performance_axis.axhline(
        5.0,
        color="#2ca02c",
        linewidth=0.9,
        linestyle=":",
        alpha=0.7,
        label="Core threshold 5%",
    )
    performance_axis.axhline(
        -5.0,
        color="#d62728",
        linewidth=0.9,
        linestyle="-.",
        alpha=0.7,
        label="D2 regression limit -5%",
    )
    performance_axis.set_ylabel("Paired improvement (%)")
    performance_axis.grid(True, alpha=0.25)
    performance_axis.legend(ncol=3, fontsize=8, loc="best")

    realtime_axis.plot(
        x,
        [
            float(pair["candidate"]["metrics"]["real_time_factor"])
            for pair in pairs
        ],
        marker="o",
        linewidth=1.5,
        color="#9467bd",
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
    fig.suptitle("D1 publication metadata v2 paired evaluation")
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def _fmt_number(value: Any) -> str:
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
            "Evaluate D1 immutable publication metadata v2 same-commit "
            "multi-seed evidence"
        )
    )
    parser.add_argument(
        "--evidence-manifest",
        required=True,
        help="path to the completed v2 evidence_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="independent compact D6 output directory",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = evaluate_d1_publication_metadata_v2_multiseed(
        args.evidence_manifest
    )
    paths = write_d1_publication_metadata_v2_multiseed_report(
        result,
        args.output_dir,
    )
    print(
        _v1._json_text(
            {
                "schema_version": result["schema_version"],
                "d1_optimization_admitted": result[
                    "d1_optimization_admitted"
                ],
                "system_realtime_gap_closed": result[
                    "system_realtime_gap_closed"
                ],
                "outputs": {
                    name: str(path) for name, path in paths.items()
                },
            }
        ),
        end="",
    )
    return 0


__all__ = [
    "D1_PUBLICATION_METADATA_V2_MULTISEED_EVALUATION_SCHEMA_VERSION",
    "D1_PUBLICATION_METADATA_V2_MULTISEED_AGGREGATE_SCHEMA_VERSION",
    "D1_PUBLICATION_METADATA_V2_EVIDENCE_MANIFEST_SCHEMA_VERSION",
    "D1_PUBLICATION_METADATA_V2_MATRIX_SCHEMA_VERSION",
    "D1_PUBLICATION_METADATA_V2_MATRIX_SHA256",
    "D1PublicationMetadataV2EvidenceError",
    "evaluate_d1_publication_metadata_v2_multiseed",
    "load_d1_publication_metadata_v2_evidence_manifest",
    "render_d1_publication_metadata_v2_multiseed_markdown",
    "write_d1_publication_metadata_v2_multiseed_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
