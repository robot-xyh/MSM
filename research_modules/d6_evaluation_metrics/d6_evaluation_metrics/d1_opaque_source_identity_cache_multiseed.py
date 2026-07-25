"""Independent D6 admission for the D1 source-only opaque source identity cache.

The evaluator consumes a preregistered, same-clean-commit 13-pair matrix.  It
does not mutate producer evidence and does not participate in online control.
Only the registered source-only opaque source identity implementation fields and
performance-derived fields are normalized for semantic comparison.  Cache
diagnostics are validated independently at every persisted location.
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


D1_OPAQUE_SOURCE_IDENTITY_CACHE_MULTISEED_EVALUATION_SCHEMA_VERSION = (
    "d6.d1_opaque_source_identity_cache_multiseed_evaluation.v1"
)
D1_OPAQUE_SOURCE_IDENTITY_CACHE_MULTISEED_COMPACT_SCHEMA_VERSION = (
    "d6.d1_opaque_source_identity_cache_multiseed_compact.v1"
)
D1_OPAQUE_SOURCE_IDENTITY_CACHE_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-opaque-source-identity-cache-multiseed-matrix-v1"
)
D1_OPAQUE_SOURCE_IDENTITY_CACHE_EVIDENCE_SCHEMA_VERSION = (
    "scalable3d-d1-opaque-source-identity-cache-multiseed-evidence-v1"
)
D1_OPAQUE_SOURCE_IDENTITY_CACHE_DIAGNOSTICS_SCHEMA_VERSION = (
    "d1.opaque_source_identity_cache_diagnostics.v1"
)
D1_OPAQUE_SOURCE_IDENTITY_CACHE_EXPERIMENT_ID = (
    "d1-opaque-source-identity-cache-multiseed-20260725-v1"
)
D1_OPAQUE_SOURCE_IDENTITY_CACHE_MATRIX_SHA256 = (
    "218d04f3fc4a764fef82de612c78c8fbb5490380ae5d20aff6b9089635f2060d"
)
D1_OPAQUE_SOURCE_IDENTITY_CACHE_SOURCE_COMMIT = (
    "d8fc76c066f21b077154f7be33c0b43558d237e5"
)
D1_OPAQUE_SOURCE_IDENTITY_CACHE_EVALUATION_DATE = "2026-07-25"

REFERENCE_IMPLEMENTATION = "per_publication_build_v1"
CANDIDATE_IMPLEMENTATION = "bounded_generation_lru_v1"
REFERENCE_IMPLEMENTATION_ID = (
    "d1.publication.opaque_source_identity.per_publication_build.v1"
)
CANDIDATE_IMPLEMENTATION_ID = (
    "d1.publication.opaque_source_identity.bounded_generation_lru.v1"
)
CACHE_CAPACITY = 1024

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
    "--d1-publish-opaque-source-key",
)
_TARGET_COUNT = 200
_RESOURCE_COUNT = 200
_RECON_COUNT = 2
_BOOTSTRAP_RESAMPLES = 10_000
_BOOTSTRAP_RNG_SEED = 20_260_725
_SHORT_SEEDS = tuple(range(1101, 1111))
_LONG_SEEDS = tuple(range(1101, 1104))
_SHORT_DURATION_S = 2.2
_LONG_DURATION_S = 10.0
_TREATMENT_MARKER = "D6_REGISTERED_OPAQUE_SOURCE_IDENTITY_CACHE_TREATMENT"
_PERFORMANCE_MARKER = "D6_REGISTERED_PERFORMANCE_DIAGNOSTIC"
_TREATMENT_DERIVED_ID_MARKER = "D6_TREATMENT_DERIVED_EPISODE_ID"
_VALIDATION_KIND = "opaque_source_identity_cache"

_EXPECTED_GATES = {
    "all_pairs_business_semantics_equal": True,
    "all_pairs_finite_state": True,
    "all_pairs_online_truth_use_count": 0,
    "all_pairs_explicit_implementation_identity": True,
    "all_pairs_opaque_source_identity_cache_audit_valid": True,
    "short_minimum_candidate_faster_count": 8,
    "short_minimum_d1_fusion_improvement_pct": 5.0,
    "short_bootstrap_relative_change_upper_bound_pct": 0.0,
    "long_minimum_candidate_faster_count": 2,
    "long_minimum_d1_fusion_improvement_pct": 5.0,
    "short_minimum_core_wall_improvement_pct": 2.0,
    "long_minimum_core_wall_improvement_pct": 2.0,
    "maximum_short_d2_association_mean_increase_pct": 5.0,
    "maximum_long_d2_association_mean_increase_pct": 5.0,
    "maximum_rss_mean_increase_pct": 5.0,
    "maximum_any_pair_rss_increase_pct": 5.0,
    "minimum_candidate_identity_build_reduction_pct": 95.0,
    "minimum_candidate_cache_hit_ratio_pct": 95.0,
}
_EXPECTED_BOUNDARY = {
    "simulation_mode": "three_dimensional_point_mass",
    "airsim_evidence": False,
    "truth_is_online_control_input": False,
    "system_realtime_requires_real_time_factor_at_least_one": True,
    "same_source_commit_for_both_arms": True,
    "only_allowed_runtime_treatment_difference": (
        "d1_opaque_source_identity_implementation"
    ),
    "reference_implementation": REFERENCE_IMPLEMENTATION,
    "candidate_implementation": CANDIDATE_IMPLEMENTATION,
    "cache_key_policy": "publisher_node_id_publisher_epoch_track_id",
    "cache_capacity": CACHE_CAPACITY,
    "source_only_publication": True,
    "structural_ambiguity_hold_enabled": False,
    "cache_values_are_immutable_strings": True,
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
_CACHE_OPERATION_FIELDS = {
    "request_count",
    "identity_build_count",
    "reference_bypass_count",
    "cache_hit_count",
    "cache_miss_count",
    "cache_eviction_count",
    "peak_entry_count",
    "generation_invalidation_count",
    "generation_invalidated_entry_count",
    "explicit_reset_count",
    "explicit_reset_entry_count",
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

D1OpaqueSourceIdentityCacheEvidenceError = (
    _base.D1PublicationMetadataEvidenceError
)


class D1OpaqueSourceIdentityCacheEvidence:
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


def load_d1_opaque_source_identity_cache_evidence_manifest(
    source: str | Path,
) -> D1OpaqueSourceIdentityCacheEvidence:
    """Load and fail-closed validate the frozen cache evidence manifest."""

    source_path = Path(source).expanduser().resolve()
    manifest, manifest_raw = _base._load_strict_json_mapping(source_path)
    _base._expect_equal(
        manifest.get("schema_version"),
        D1_OPAQUE_SOURCE_IDENTITY_CACHE_EVIDENCE_SCHEMA_VERSION,
        "cache evidence manifest schema_version",
    )
    _base._expect_equal(
        manifest.get("experiment_id"),
        D1_OPAQUE_SOURCE_IDENTITY_CACHE_EXPERIMENT_ID,
        "cache evidence experiment_id",
    )
    _base._expect_equal(
        manifest.get("required_d6_evaluator_schema_version"),
        D1_OPAQUE_SOURCE_IDENTITY_CACHE_MULTISEED_EVALUATION_SCHEMA_VERSION,
        "cache evidence required D6 evaluator schema",
    )
    _base._expect_equal(
        manifest.get("opaque_source_identity_cache_capacity"),
        CACHE_CAPACITY,
        "cache evidence capacity",
    )
    _base._expect_equal(
        manifest.get(
            "opaque_source_identity_cache_diagnostics_schema_version"
        ),
        D1_OPAQUE_SOURCE_IDENTITY_CACHE_DIAGNOSTICS_SCHEMA_VERSION,
        "cache evidence diagnostics schema",
    )
    if manifest.get("status") != "episodes_complete_pending_d6":
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "cache evidence status must be episodes_complete_pending_d6"
        )
    _base._required_text(
        manifest.get("completed_at_utc"),
        "cache evidence completed_at_utc",
    )
    source_commit = _base._required_commit(
        manifest.get("source_commit"),
        "cache evidence source_commit",
    )
    _base._expect_equal(
        source_commit,
        D1_OPAQUE_SOURCE_IDENTITY_CACHE_SOURCE_COMMIT,
        "cache evidence frozen source_commit",
    )
    if manifest.get("source_repository_dirty") is not False:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "cache evidence source_repository_dirty must be false"
        )
    source_worktree = _base._explicit_path(
        manifest.get("source_worktree"),
        "cache evidence source_worktree",
        require=None,
    )
    output_root = _base._explicit_path(
        manifest.get("output_root"),
        "cache evidence output_root",
        require="directory",
    )
    if source_path.parent != output_root:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "cache evidence_manifest.json must be directly under output_root"
        )

    matrix_path = _base._explicit_path(
        manifest.get("matrix_path"),
        "cache evidence matrix_path",
        require="file",
    )
    matrix_sha256 = _base._required_sha256(
        manifest.get("matrix_sha256"),
        "cache evidence matrix_sha256",
    )
    if matrix_sha256 != _base._file_sha256(matrix_path):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "cache matrix_sha256 does not match matrix_path bytes"
        )
    if matrix_sha256 != D1_OPAQUE_SOURCE_IDENTITY_CACHE_MATRIX_SHA256:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "cache matrix_sha256 does not match the frozen matrix"
        )
    matrix, _ = _base._load_strict_json_mapping(matrix_path)
    _validate_matrix(matrix)
    embedded_matrix = _base._required_mapping(
        manifest.get("matrix"),
        "cache embedded matrix",
    )
    if embedded_matrix != matrix:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "cache embedded matrix does not exactly match matrix_path"
        )

    raw_cases = _base._required_sequence(
        manifest.get("cases"),
        "cache evidence cases",
    )
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "cache evidence manifest must contain exactly 13 cases"
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
            "cache evidence case",
        )
        metadata = _base._case_metadata(case)
        if metadata != expected_case:
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                "cache evidence case differs from preregistration: "
                f"expected {expected_case!r}, got {metadata!r}"
            )
        case_id, group, seed, duration_s, arm_order = metadata
        if case.get("d6_evaluation_status") != (
            "episodes_complete_pending_d6"
        ):
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                f"{case_id} d6_evaluation_status is not pending D6"
            )
        raw_arms = _base._required_mapping(
            case.get("arms"),
            f"{case_id} arms",
        )
        if set(raw_arms) != set(_ARMS):
            raise D1OpaqueSourceIdentityCacheEvidenceError(
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
                raise D1OpaqueSourceIdentityCacheEvidenceError(
                    f"{case_id} {arm} status must be complete"
                )
            if record.get("reused", False) is not False:
                raise D1OpaqueSourceIdentityCacheEvidenceError(
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
                raise D1OpaqueSourceIdentityCacheEvidenceError(
                    f"{case_id} {arm} contains a reuse marker"
                )
            return_code = record.get("return_code")
            if (
                not isinstance(return_code, int)
                or isinstance(return_code, bool)
                or return_code != 0
            ):
                raise D1OpaqueSourceIdentityCacheEvidenceError(
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
                    raise D1OpaqueSourceIdentityCacheEvidenceError(
                        f"duplicate cache evidence path: {path}"
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
                raise D1OpaqueSourceIdentityCacheEvidenceError(
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
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "cache evidence must bind exactly 26 fresh arms"
        )

    return D1OpaqueSourceIdentityCacheEvidence(
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


def evaluate_d1_opaque_source_identity_cache_multiseed(
    source: str | Path,
    *,
    raise_on_invalid: bool = False,
) -> dict[str, Any]:
    """Evaluate the frozen matrix or return an unavailable result."""

    try:
        return _evaluate_d1_opaque_source_identity_cache_multiseed_available(
            source
        )
    except D1OpaqueSourceIdentityCacheEvidenceError as exc:
        if raise_on_invalid:
            raise
        return _unavailable_evaluation(source, str(exc))


def _evaluate_d1_opaque_source_identity_cache_multiseed_available(
    source: str | Path,
) -> dict[str, Any]:
    """Strict evaluation path after every evidence check succeeds."""

    evidence = load_d1_opaque_source_identity_cache_evidence_manifest(source)
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
    cache_aggregate = _aggregate_cache_diagnostics(pairs)
    thresholds = copy.deepcopy(
        dict(evidence.matrix["admission_gates"])
    )
    gates = _admission_gates(
        pairs,
        groups,
        cache_aggregate,
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
            D1_OPAQUE_SOURCE_IDENTITY_CACHE_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": D1_OPAQUE_SOURCE_IDENTITY_CACHE_EVALUATION_DATE,
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
                D1_OPAQUE_SOURCE_IDENTITY_CACHE_EVIDENCE_SCHEMA_VERSION
            ),
            "evidence_manifest_status": "episodes_complete_pending_d6",
            "matrix_path": str(evidence.matrix_path),
            "matrix_sha256": evidence.matrix_sha256,
            "matrix_schema_version": (
                D1_OPAQUE_SOURCE_IDENTITY_CACHE_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": D1_OPAQUE_SOURCE_IDENTITY_CACHE_EXPERIMENT_ID,
            "output_root": str(evidence.output_root),
            "source_commit": evidence.source_commit,
            "source_repository_dirty": False,
            "same_commit_for_both_arms": True,
            "arm_implementations": dict(_IMPLEMENTATIONS),
            "arm_implementation_ids": dict(_IMPLEMENTATION_IDS),
            "cache_capacity": CACHE_CAPACITY,
            "cache_diagnostics_schema_version": (
                D1_OPAQUE_SOURCE_IDENTITY_CACHE_DIAGNOSTICS_SCHEMA_VERSION
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
            "source_only_publication": True,
            "structural_ambiguity_hold_enabled": False,
            "default_no_source_key_r0_evidence": False,
            "normalized_treatment_fields": [
                "d1_opaque_source_identity_implementation",
                "d1_opaque_source_identity_cache_diagnostics",
                "treatment-derived episode identity",
                "stage and episode performance fields",
            ],
        },
        "thresholds": thresholds,
        "pairs": pairs,
        "groups": groups,
        "cache_diagnostics_aggregate": cache_aggregate,
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
            D1_OPAQUE_SOURCE_IDENTITY_CACHE_MULTISEED_EVALUATION_SCHEMA_VERSION
        ),
        "evaluation_date": D1_OPAQUE_SOURCE_IDENTITY_CACHE_EVALUATION_DATE,
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "input_mutation_permitted": False,
        "availability": {
            "available": False,
            "reason": reason,
        },
        "input_contract": {
            "evidence_manifest_path": str(source_path),
            "matrix_sha256": D1_OPAQUE_SOURCE_IDENTITY_CACHE_MATRIX_SHA256,
            "matrix_schema_version": (
                D1_OPAQUE_SOURCE_IDENTITY_CACHE_MATRIX_SCHEMA_VERSION
            ),
            "experiment_id": D1_OPAQUE_SOURCE_IDENTITY_CACHE_EXPERIMENT_ID,
            "source_commit": D1_OPAQUE_SOURCE_IDENTITY_CACHE_SOURCE_COMMIT,
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
            "source_only_publication": True,
            "default_no_source_key_r0_evidence": False,
        },
        "thresholds": copy.deepcopy(_EXPECTED_GATES),
        "pairs": [],
        "groups": {},
        "cache_diagnostics_aggregate": {},
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
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "cache matrix top-level fields differ from frozen contract"
        )
    expected_scalars = (
        ("schema_version", D1_OPAQUE_SOURCE_IDENTITY_CACHE_MATRIX_SCHEMA_VERSION),
        ("experiment_id", D1_OPAQUE_SOURCE_IDENTITY_CACHE_EXPERIMENT_ID),
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
            f"cache matrix {field}",
        )
    _base._expect_equal(
        matrix.get("arm_implementations"),
        _IMPLEMENTATIONS,
        "cache matrix arm_implementations",
    )
    _base._expect_equal(
        tuple(
            _base._required_text(item, "cache matrix run flag")
            for item in _base._required_sequence(
                matrix.get("run_flags"),
                "cache matrix run_flags",
            )
        ),
        _RUN_FLAGS,
        "cache matrix run_flags",
    )
    raw_cases = _base._required_sequence(
        matrix.get("cases"),
        "cache matrix cases",
    )
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "cache matrix must contain exactly 13 cases"
        )
    for raw_case, expected_case in zip(
        raw_cases,
        _EXPECTED_CASES,
        strict=True,
    ):
        case = _base._required_mapping(raw_case, "cache matrix case")
        if set(case) != {
            "case_id",
            "group",
            "seed",
            "duration_s",
            "arm_order",
        }:
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                "cache matrix case fields differ from frozen contract"
            )
        if _base._case_metadata(case) != expected_case:
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                "cache matrix case differs from frozen order"
            )
    _base._expect_equal(
        _base._required_mapping(
            matrix.get("admission_gates"),
            "cache matrix admission_gates",
        ),
        _EXPECTED_GATES,
        "cache matrix admission_gates",
    )
    _base._expect_equal(
        _base._required_mapping(
            matrix.get("evidence_boundary"),
            "cache matrix evidence_boundary",
        ),
        _EXPECTED_BOUNDARY,
        "cache matrix evidence_boundary",
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
        "--d1-opaque-source-identity-implementation",
        implementation,
        "--d1-opaque-source-identity-cache-capacity",
        str(CACHE_CAPACITY),
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
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{case_id} arm command lengths differ"
        )
    selector_index = reference.index(
        "--d1-opaque-source-identity-implementation"
    ) + 1
    output_index = reference.index("--output") + 1
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index in {selector_index, output_index}:
            continue
        if left != right:
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                f"{case_id} commands differ outside treatment/output"
            )


def _evaluate_pair(
    pair: _base.D1PublicationMetadataPairBinding,
    evidence: D1OpaqueSourceIdentityCacheEvidence,
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
    cache_pair = _validate_pair_cache_workload(
        reference["cache_diagnostics"],
        candidate["cache_diagnostics"],
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
        "opaque_source_identity_cache_audit": cache_pair,
        "opaque_source_identity_cache_audit_passed": bool(cache_pair["passed"]),
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
            raise D1OpaqueSourceIdentityCacheEvidenceError(
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
    diagnostics, cache_audit = _validate_implementation_identity(
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
        "cache_diagnostics": diagnostics,
        "cache_audit": cache_audit,
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
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} source commit mismatch"
        )
    if manifest.get("repository_dirty") is not False:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} repository is dirty"
        )
    if manifest.get("scenario_schema") != _EXPECTED_CONFIG_SCHEMA_VERSION:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} manifest scenario schema mismatch"
        )
    if manifest.get("runtime_profile_schema") != (
        _EXPECTED_RUNTIME_PROFILE_SCHEMA_VERSION
    ):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} manifest runtime profile schema mismatch"
        )
    if config.get("schema_version") != _EXPECTED_CONFIG_SCHEMA_VERSION:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} scenario config schema mismatch"
        )
    if governance.get("schema_version") != (
        _EXPECTED_GOVERNANCE_SCHEMA_VERSION
    ):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} governance schema mismatch"
        )
    if manifest.get("config_sha256") != _base._canonical_sha256(config):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} config_sha256 mismatch"
        )
    runtime_profile = _base._required_mapping(
        manifest.get("runtime_profile"),
        f"{context} runtime_profile",
    )
    if manifest.get("runtime_profile_sha256") != _base._canonical_sha256(
        runtime_profile
    ):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} runtime_profile_sha256 mismatch"
        )
    if runtime_profile.get("schema_version") != (
        _EXPECTED_RUNTIME_PROFILE_SCHEMA_VERSION
    ):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
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
            raise D1OpaqueSourceIdentityCacheEvidenceError(
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
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} finite_state must be true"
        )
    if summary.get("online_truth_use_count") != 0:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} online_truth_use_count must be zero"
        )
    if governance.get("online_truth_use_count") != 0:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
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
    selectors = {
        "manifest.runtime_profile": runtime_profile.get(
            "d1_opaque_source_identity_implementation"
        ),
        "manifest.runtime_profile.configuration": configuration.get(
            "d1_opaque_source_identity_implementation"
        ),
        "summary": summary.get("d1_opaque_source_identity_implementation"),
        "summary.module_final_diagnostics": final.get(
            "d1_opaque_source_identity_implementation"
        ),
        "summary.module_final.observation_governance": (
            nested_governance.get("d1_opaque_source_identity_implementation")
        ),
        "governance": governance.get(
            "d1_opaque_source_identity_implementation"
        ),
    }
    mismatches = [
        f"{name}={value!r}"
        for name, value in selectors.items()
        if value != expected
    ]
    if mismatches:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} cache implementation identity mismatch: "
            + ", ".join(mismatches)
        )
    if configuration.get("d1_opaque_source_identity_cache_capacity") != (
        CACHE_CAPACITY
    ):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} runtime cache capacity mismatch"
        )
    source_only_locations = {
        "runtime.configuration": configuration.get(
            "d1_publish_opaque_source_key"
        ),
        "module_final.observation_governance": nested_governance.get(
            "d1_publish_opaque_source_key"
        ),
        "observation_governance_audit": governance.get(
            "d1_publish_opaque_source_key"
        ),
    }
    if any(value is not True for value in source_only_locations.values()):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} matrix is not source-only publication: "
            f"{source_only_locations}"
        )
    hold_locations = {
        "runtime.configuration": configuration.get(
            "d1_d2_structural_ambiguity_hold_enabled"
        ),
        "module_final.observation_governance": nested_governance.get(
            "d1_d2_structural_ambiguity_hold_enabled"
        ),
        "observation_governance_audit": governance.get(
            "d1_d2_structural_ambiguity_hold_enabled"
        ),
    }
    if any(value is not False for value in hold_locations.values()):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} structural ambiguity hold must be disabled: "
            f"{hold_locations}"
        )

    initial = _base._required_mapping(
        runtime_profile.get("d1_opaque_source_identity_cache_diagnostics"),
        f"{context} initial cache diagnostics",
    )
    _validate_initial_diagnostics(initial, arm=arm, context=context)
    diagnostics_locations = {
        "summary": _base._required_mapping(
            summary.get("d1_opaque_source_identity_cache_diagnostics"),
            f"{context} summary cache diagnostics",
        ),
        "module_final_diagnostics": _base._required_mapping(
            final.get("d1_opaque_source_identity_cache_diagnostics"),
            f"{context} final cache diagnostics",
        ),
        "module_final_observation_governance": _base._required_mapping(
            nested_governance.get(
                "d1_opaque_source_identity_cache_diagnostics"
            ),
            f"{context} nested governance cache diagnostics",
        ),
        "observation_governance_audit": _base._required_mapping(
            governance.get("d1_opaque_source_identity_cache_diagnostics"),
            f"{context} governance cache diagnostics",
        ),
    }
    canonical = diagnostics_locations["summary"]
    for name, diagnostics in diagnostics_locations.items():
        if diagnostics != canonical:
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                f"{context} cache diagnostics mismatch at {name}"
            )
    normalized, audit = _validate_final_diagnostics(
        canonical,
        arm=arm,
        context=context,
    )
    return normalized, {
        **audit,
        "initial_runtime_profile_diagnostics_passed": True,
        "four_persisted_diagnostics_equal": True,
        "persisted_diagnostics_surface_count": len(diagnostics_locations),
        "selector_surface_count": len(selectors),
        "source_only_locations": source_only_locations,
        "hold_disabled_locations": hold_locations,
    }


def _validate_initial_diagnostics(
    diagnostics: Mapping[str, Any],
    *,
    arm: str,
    context: str,
) -> None:
    expected_candidate = arm == _CANDIDATE_ARM
    expected_id = _IMPLEMENTATION_IDS[arm]
    conservation = {
        "request_equals_hit_plus_miss_plus_bypass": True,
        "build_equals_miss_plus_bypass": True,
        "entry_count_within_capacity": True,
        "peak_entry_count_within_capacity": True,
        "eviction_not_above_miss": True,
    }
    required = {
        "schema_version": (
            D1_OPAQUE_SOURCE_IDENTITY_CACHE_DIAGNOSTICS_SCHEMA_VERSION
        ),
        "implementation_id": expected_id,
        "candidate_enabled": expected_candidate,
        "cache_capacity": CACHE_CAPACITY,
        "cache_entry_count": 0,
        "cache_generation": None,
        "conservation": conservation,
        "operation_counts": {},
    }
    if dict(diagnostics) != required:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} initial cache diagnostics mismatch"
        )


def _validate_final_diagnostics(
    diagnostics: Mapping[str, Any],
    *,
    arm: str,
    context: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_candidate = arm == _CANDIDATE_ARM
    if diagnostics.get("schema_version") != (
        D1_OPAQUE_SOURCE_IDENTITY_CACHE_DIAGNOSTICS_SCHEMA_VERSION
    ):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} cache diagnostics schema mismatch"
        )
    if diagnostics.get("implementation_id") != _IMPLEMENTATION_IDS[arm]:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} cache diagnostics implementation_id mismatch"
        )
    if diagnostics.get("candidate_enabled") is not expected_candidate:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} cache candidate_enabled mismatch"
        )
    if diagnostics.get("cache_capacity") != CACHE_CAPACITY:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} cache diagnostics capacity mismatch"
        )
    required_fields = {
        "schema_version",
        "implementation_id",
        "candidate_enabled",
        "cache_capacity",
        "cache_entry_count",
        "cache_generation",
        "conservation",
        "operation_counts",
    }
    if set(diagnostics) != required_fields:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} cache diagnostics fields mismatch"
        )
    conservation = _base._required_mapping(
        diagnostics.get("conservation"),
        f"{context} cache conservation",
    )
    expected_conservation = {
        "request_equals_hit_plus_miss_plus_bypass": True,
        "build_equals_miss_plus_bypass": True,
        "entry_count_within_capacity": True,
        "peak_entry_count_within_capacity": True,
        "eviction_not_above_miss": True,
    }
    if dict(conservation) != expected_conservation:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} cache conservation flags mismatch"
        )
    generation_raw = diagnostics.get("cache_generation")
    if (
        not isinstance(generation_raw, list)
        or len(generation_raw) != 2
        or any(
            not isinstance(item, str) or not item
            for item in generation_raw
        )
    ):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} cache_generation must contain node and epoch"
        )
    generation = list(generation_raw)
    entry_count = _nonnegative_integer(
        diagnostics.get("cache_entry_count"),
        f"{context} cache_entry_count",
    )
    operations_raw = _base._required_mapping(
        diagnostics.get("operation_counts"),
        f"{context} cache operation_counts",
    )
    unknown = set(operations_raw) - _CACHE_OPERATION_FIELDS
    if unknown:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} cache operation_counts contain unknown fields: "
            f"{sorted(unknown)}"
        )
    operations = {
        name: _nonnegative_integer(
            operations_raw.get(name, 0),
            f"{context} {name}",
        )
        for name in sorted(_CACHE_OPERATION_FIELDS)
    }
    requests = operations["request_count"]
    builds = operations["identity_build_count"]
    bypasses = operations["reference_bypass_count"]
    hits = operations["cache_hit_count"]
    misses = operations["cache_miss_count"]
    evictions = operations["cache_eviction_count"]
    peak = operations["peak_entry_count"]
    if requests <= 0:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} request_count must be positive"
        )
    if entry_count > CACHE_CAPACITY or peak > CACHE_CAPACITY:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} cache entry/peak exceeds capacity"
        )
    if entry_count > peak or evictions > misses:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} cache entry/eviction bounds failed"
        )
    if expected_candidate:
        if hits <= 0 or misses <= 0 or builds <= 0:
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                f"{context} candidate hit/miss/build counts must be positive"
            )
        if bypasses != 0:
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                f"{context} candidate reference_bypass_count must be zero"
            )
        if requests != hits + misses + bypasses:
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                f"{context} candidate request conservation failed"
            )
        if builds != misses + bypasses:
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                f"{context} candidate identity build conservation failed"
            )
    else:
        if any((hits, misses, evictions, peak, entry_count)):
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                f"{context} reference unexpectedly reports cache activity"
            )
        if builds <= 0:
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                f"{context} reference identity_build_count must be positive"
            )
        if bypasses != requests:
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                f"{context} reference bypass must equal request count"
            )
        if builds != misses + bypasses or builds != requests:
            raise D1OpaqueSourceIdentityCacheEvidenceError(
                f"{context} reference identity build conservation failed"
            )
    normalized = {
        "schema_version": diagnostics["schema_version"],
        "implementation_id": diagnostics["implementation_id"],
        "candidate_enabled": diagnostics["candidate_enabled"],
        "cache_capacity": CACHE_CAPACITY,
        "cache_entry_count": entry_count,
        "cache_generation": generation,
        "conservation": expected_conservation,
        "operation_counts": operations,
    }
    lookup_count = hits + misses
    return normalized, {
        "passed": True,
        "request_conservation_passed": True,
        "identity_build_conservation_passed": True,
        "capacity_passed": True,
        "request_count": requests,
        "identity_build_count": builds,
        "reference_bypass_count": bypasses,
        "cache_hit_count": hits,
        "cache_miss_count": misses,
        "cache_eviction_count": evictions,
        "cache_entry_count": entry_count,
        "peak_entry_count": peak,
        "cache_generation": generation,
        "cache_hit_ratio": (
            hits / lookup_count if lookup_count > 0 else None
        ),
    }


def _nonnegative_integer(value: Any, context: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
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
        "cache runtime profile configuration",
    )
    final = _base._required_mapping(
        summary["module_final_diagnostics"],
        "cache module final diagnostics",
    )
    summary_diagnostics = _base._required_mapping(
        summary["d1_opaque_source_identity_cache_diagnostics"],
        "cache summary diagnostics",
    )
    return {
        "manifest_runtime_profile": runtime_profile[
            "d1_opaque_source_identity_implementation"
        ],
        "manifest_runtime_configuration": configuration[
            "d1_opaque_source_identity_implementation"
        ],
        "manifest_runtime_capacity": configuration[
            "d1_opaque_source_identity_cache_capacity"
        ],
        "summary_top_level": summary[
            "d1_opaque_source_identity_implementation"
        ],
        "summary_implementation_id": summary_diagnostics[
            "implementation_id"
        ],
        "summary_cache_capacity": summary_diagnostics["cache_capacity"],
        "module_final": final["d1_opaque_source_identity_implementation"],
        "governance_top_level": governance[
            "d1_opaque_source_identity_implementation"
        ],
    }


def _validate_pair_cache_workload(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    context: str,
) -> dict[str, Any]:
    reference_ops = _base._required_mapping(
        reference["operation_counts"],
        f"{context} reference cache operation_counts",
    )
    candidate_ops = _base._required_mapping(
        candidate["operation_counts"],
        f"{context} candidate cache operation_counts",
    )
    reference_requests = int(reference_ops["request_count"])
    candidate_requests = int(candidate_ops["request_count"])
    if reference_requests != candidate_requests:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} publication request workloads differ between arms"
        )
    if reference["cache_generation"] != candidate["cache_generation"]:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} publisher node/epoch generation differs between arms"
        )
    reference_builds = int(reference_ops["identity_build_count"])
    candidate_builds = int(candidate_ops["identity_build_count"])
    if reference_builds <= 0:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} reference identity build denominator is zero"
        )
    hits = int(candidate_ops["cache_hit_count"])
    misses = int(candidate_ops["cache_miss_count"])
    if hits + misses <= 0:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} candidate cache lookup denominator is zero"
        )
    return {
        "passed": True,
        "same_publication_request_workload": True,
        "same_publisher_generation": True,
        "publisher_generation": reference["cache_generation"],
        "reference_request_count": reference_requests,
        "candidate_request_count": candidate_requests,
        "reference_identity_build_count": reference_builds,
        "candidate_identity_build_count": candidate_builds,
        "candidate_identity_build_reduction_pct": (
            (reference_builds - candidate_builds)
            / reference_builds
            * 100.0
        ),
        "candidate_cache_hit_count": hits,
        "candidate_cache_miss_count": misses,
        "candidate_cache_hit_ratio_pct": hits / (hits + misses) * 100.0,
    }


def _normalized_runtime_profile(
    runtime_profile: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(runtime_profile))
    if "d1_opaque_source_identity_implementation" not in normalized:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "normalized runtime profile lacks cache selector"
        )
    normalized["d1_opaque_source_identity_implementation"] = _TREATMENT_MARKER
    configuration = _base._mutable_mapping(
        normalized.get("configuration"),
        "normalized runtime configuration",
    )
    if "d1_opaque_source_identity_implementation" not in configuration:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "normalized runtime configuration lacks cache selector"
        )
    configuration["d1_opaque_source_identity_implementation"] = _TREATMENT_MARKER
    _normalize_cache_diagnostics(
        normalized,
        "normalized runtime profile",
    )
    return normalized


def _normalized_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(summary))
    if "episode_id" not in normalized:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "normalized summary lacks episode_id"
        )
    normalized["episode_id"] = _TREATMENT_DERIVED_ID_MARKER
    normalized["wall_time_s"] = _PERFORMANCE_MARKER
    normalized["real_time_factor"] = _PERFORMANCE_MARKER
    _normalize_cache_fields(normalized, "normalized summary")
    final = _base._mutable_mapping(
        normalized.get("module_final_diagnostics"),
        "normalized cache module final",
    )
    _normalize_cache_fields(final, "normalized cache module final")
    if "stage_timings" not in final:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "normalized cache module final lacks stage_timings"
        )
    final["stage_timings"] = _PERFORMANCE_MARKER
    nested = _base._required_mapping(
        final.get("observation_governance"),
        "normalized cache nested governance",
    )
    final["observation_governance"] = _normalized_governance(nested)
    return normalized


def _normalized_governance(
    governance: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(governance))
    _normalize_cache_fields(normalized, "normalized cache governance")
    return normalized


def _normalize_cache_fields(
    mapping: dict[str, Any],
    context: str,
) -> None:
    if "d1_opaque_source_identity_implementation" not in mapping:
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} lacks d1_opaque_source_identity_implementation"
        )
    mapping["d1_opaque_source_identity_implementation"] = _TREATMENT_MARKER
    _normalize_cache_diagnostics(mapping, context)


def _normalize_cache_diagnostics(
    mapping: dict[str, Any],
    context: str,
) -> None:
    diagnostics = mapping.get("d1_opaque_source_identity_cache_diagnostics")
    if not isinstance(diagnostics, dict):
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            f"{context} lacks mutable cache diagnostics"
        )
    mapping["d1_opaque_source_identity_cache_diagnostics"] = {
        "value": _TREATMENT_MARKER
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
        raise D1OpaqueSourceIdentityCacheEvidenceError(
            "cross-build reader returned an unsupported schema"
        )
    cross_checks = _base._required_mapping(
        cross.get("checks"),
        "cache cross-build checks",
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
        "cache_treatment_normalization": {
            "scope": (
                "d1_opaque_source_identity_selector_cache_diagnostics_"
                "runtime_identity_and_performance_only"
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
        "cache_audit_pass_count": sum(
            bool(pair["opaque_source_identity_cache_audit_passed"])
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


def _aggregate_cache_diagnostics(
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
            totals = {name: 0 for name in sorted(_CACHE_OPERATION_FIELDS)}
            for pair in selected:
                operations = pair[arm]["cache_diagnostics"][
                    "operation_counts"
                ]
                for name in totals:
                    totals[name] += int(operations[name])
            arm_totals[arm] = totals
        reference_builds = arm_totals[_REFERENCE_ARM][
            "identity_build_count"
        ]
        candidate_builds = arm_totals[_CANDIDATE_ARM][
            "identity_build_count"
        ]
        candidate_hits = arm_totals[_CANDIDATE_ARM]["cache_hit_count"]
        candidate_misses = arm_totals[_CANDIDATE_ARM]["cache_miss_count"]
        groups[group] = {
            "pair_count": len(selected),
            "arms": arm_totals,
            "candidate_identity_build_reduction_pct": (
                (reference_builds - candidate_builds)
                / reference_builds
                * 100.0
            ),
            "candidate_cache_hit_ratio_pct": (
                candidate_hits
                / (candidate_hits + candidate_misses)
                * 100.0
            ),
            "candidate_maximum_entry_count": max(
                int(
                    pair[_CANDIDATE_ARM]["cache_diagnostics"][
                        "cache_entry_count"
                    ]
                )
                for pair in selected
            ),
            "candidate_maximum_peak_entry_count": max(
                int(
                    pair[_CANDIDATE_ARM]["cache_diagnostics"][
                        "operation_counts"
                    ]["peak_entry_count"]
                )
                for pair in selected
            ),
            "cache_capacity": CACHE_CAPACITY,
        }
    return {
        "schema_version": (
            "d6.d1_opaque_source_identity_cache_diagnostics_aggregate.v1"
        ),
        "groups": groups,
    }


def _admission_gates(
    pairs: Sequence[Mapping[str, Any]],
    groups: Mapping[str, Any],
    cache_aggregate: Mapping[str, Any],
    thresholds: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    pair_count = len(pairs)
    short_fusion = groups["short"]["metrics"]["d1_fusion_wall_s"]
    long_fusion = groups["long"]["metrics"]["d1_fusion_wall_s"]
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
    cache_audit_count = sum(
        bool(pair["opaque_source_identity_cache_audit_passed"]) for pair in pairs
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
    cache_all = cache_aggregate["groups"]["all"]
    build_reduction = float(
        cache_all["candidate_identity_build_reduction_pct"]
    )
    hit_ratio = float(cache_all["candidate_cache_hit_ratio_pct"])
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
        "all_pairs_opaque_source_identity_cache_audit_valid": _gate(
            actual=cache_audit_count,
            threshold=pair_count,
            comparator="==",
            passed=(cache_audit_count == pair_count),
            reason="one_or_more_pair_cache_audit_failed",
        ),
        "required_performance_metrics_available": _gate(
            actual=required_metric_count,
            threshold=pair_count,
            comparator="==",
            passed=(required_metric_count == pair_count),
            reason="one_or_more_required_performance_metrics_unavailable",
        ),
        "short_minimum_candidate_faster_count": _gate(
            actual=short_fusion["candidate_better_count"],
            threshold=thresholds[
                "short_minimum_candidate_faster_count"
            ],
            comparator=">=",
            passed=(
                short_fusion["candidate_better_count"]
                >= thresholds["short_minimum_candidate_faster_count"]
            ),
            reason="short_candidate_faster_count_below_threshold",
        ),
        "short_minimum_d1_fusion_improvement_pct": _gate(
            actual=short_fusion["improvement_pct"]["mean"],
            threshold=thresholds[
                "short_minimum_d1_fusion_improvement_pct"
            ],
            comparator=">=",
            passed=(
                short_fusion["improvement_pct"]["mean"]
                >= thresholds[
                    "short_minimum_d1_fusion_improvement_pct"
                ]
            ),
            reason="short_d1_fusion_improvement_below_threshold",
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
            actual=long_fusion["candidate_better_count"],
            threshold=thresholds[
                "long_minimum_candidate_faster_count"
            ],
            comparator=">=",
            passed=(
                long_fusion["candidate_better_count"]
                >= thresholds["long_minimum_candidate_faster_count"]
            ),
            reason="long_candidate_faster_count_below_threshold",
        ),
        "long_minimum_d1_fusion_improvement_pct": _gate(
            actual=long_fusion["improvement_pct"]["mean"],
            threshold=thresholds[
                "long_minimum_d1_fusion_improvement_pct"
            ],
            comparator=">=",
            passed=(
                long_fusion["improvement_pct"]["mean"]
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
        "minimum_candidate_identity_build_reduction_pct": _gate(
            actual=build_reduction,
            threshold=thresholds[
                "minimum_candidate_identity_build_reduction_pct"
            ],
            comparator=">=",
            passed=(
                build_reduction
                >= thresholds[
                    "minimum_candidate_identity_build_reduction_pct"
                ]
            ),
            reason="candidate_identity_build_reduction_below_threshold",
            unit="pct",
        ),
        "minimum_candidate_cache_hit_ratio_pct": _gate(
            actual=hit_ratio,
            threshold=thresholds[
                "minimum_candidate_cache_hit_ratio_pct"
            ],
            comparator=">=",
            passed=(
                hit_ratio
                >= thresholds["minimum_candidate_cache_hit_ratio_pct"]
            ),
            reason="candidate_cache_hit_ratio_below_threshold",
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


def write_d1_opaque_source_identity_cache_multiseed_report(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write deterministic compact products outside the raw evidence root."""

    if result.get("schema_version") != (
        D1_OPAQUE_SOURCE_IDENTITY_CACHE_MULTISEED_EVALUATION_SCHEMA_VERSION
    ):
        raise ValueError("unsupported cache evaluation schema")
    contract = _base._required_mapping(
        result.get("input_contract"),
        "cache report input contract",
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
        / "d1_opaque_source_identity_cache_multiseed_evaluation.json",
        "compact_json": directory
        / "d1_opaque_source_identity_cache_multiseed_compact.json",
        "pairs_csv": directory
        / "d1_opaque_source_identity_cache_multiseed_pairs.csv",
        "markdown": directory
        / "D1_OPAQUE_SOURCE_IDENTITY_CACHE_MULTISEED_REPORT_CN.md",
        "plot_png": directory
        / "d1_opaque_source_identity_cache_multiseed_curves.png",
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
        render_d1_opaque_source_identity_cache_multiseed_markdown(result),
        encoding="utf-8",
    )
    available = bool(
        _base._required_mapping(
            result.get("availability"), "cache report availability"
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
            D1_OPAQUE_SOURCE_IDENTITY_CACHE_MULTISEED_COMPACT_SCHEMA_VERSION
        ),
        "evaluation_schema_version": result["schema_version"],
        "evaluation_date": result["evaluation_date"],
        "availability": result["availability"],
        "input_contract": result["input_contract"],
        "scope": result["scope"],
        "groups": result["groups"],
        "cache_diagnostics_aggregate": result[
            "cache_diagnostics_aggregate"
        ],
        "admission_gates": result["admission_gates"],
        "admission_blockers": result["admission_blockers"],
        "optimization_admitted": result["optimization_admitted"],
        "system_realtime_gate": result["system_realtime_gate"],
        "system_realtime_gap_closed": result[
            "system_realtime_gap_closed"
        ],
    }


def render_d1_opaque_source_identity_cache_multiseed_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the formal Chinese cache admission report."""

    availability = _base._required_mapping(
        result.get("availability"), "cache report availability"
    )
    contract = _base._required_mapping(
        result["input_contract"],
        "cache input contract",
    )
    if availability.get("available") is not True:
        return "\n".join(
            [
                "# D1 不透明来源标识缓存多种子评估",
                "",
                "## 结论",
                "",
                "冻结证据不可用，D6 失败关闭。模块优化不准入，系统实时缺口未关闭。",
                "",
                "## 原因",
                "",
                f"`{availability.get('reason')}`",
                "",
                "该结果不修改生产侧证据，也不以缺失数据替代正式矩阵。",
                "",
            ]
        )
    groups = _base._required_mapping(result["groups"], "cache groups")
    gates = _base._required_mapping(
        result["admission_gates"],
        "cache gates",
    )
    cache = result["cache_diagnostics_aggregate"]["groups"]["all"]
    realtime = result["system_realtime_gate"]
    failed_gates = [
        name for name, gate in gates.items() if gate["passed"] is not True
    ]
    long_d2_gate = gates[
        "maximum_long_d2_association_mean_increase_pct"
    ]
    long_1101 = next(
        pair for pair in result["pairs"]
        if pair["case_id"] == "long_seed_1101"
    )
    if failed_gates == [
        "maximum_long_d2_association_mean_increase_pct"
    ]:
        admission_detail = (
            "唯一性能阻断为长时 D2 关联墙钟：三组候选均值相对参考均值增加 "
            f"`{_fmt(long_d2_gate['actual'])}%`，超过冻结上限 "
            f"`{_fmt(long_d2_gate['threshold'])}%`。`long_seed_1101` 增幅为 "
            f"`{_fmt(long_1101['performance']['d2_association_wall_s']['raw_relative_change_pct'])}%`，"
            "仍按预注册矩阵保留；其余两个长时 pair 的下降不能抵消聚合门失败。"
        )
        follow_up = (
            "后续可运行新的预注册确认矩阵判断该增幅是否稳定。本轮不调整门限、"
            "不剔除 pair，结论保持不准入。"
        )
    elif failed_gates:
        admission_detail = (
            "失败门为 "
            + "、".join(f"`{name}`" for name in failed_gates)
            + "。"
        )
        follow_up = "本轮按冻结矩阵失败关闭，不修改门限或样本集合。"
    else:
        admission_detail = "全部冻结准入门通过。"
        follow_up = "系统实时判定仍按全部候选实时因子是否不低于 1 单独计算。"
    lines = [
        "# D1 不透明来源标识缓存同提交多种子评估",
        "",
        "## 结论",
        "",
        (
            "D1 局部优化准入"
            f"{'通过' if result['optimization_admitted'] else '未通过'}；"
            "系统实时缺口"
            f"{'已关闭' if result['system_realtime_gap_closed'] else '未关闭'}。"
            "两项判定相互独立。"
        ),
        (
            f"候选最低实时因子为 "
            f"`{_fmt(realtime['candidate_minimum_real_time_factor'])}`，"
            "系统实时门限为 `>=1.0`。本报告只使用三维质点仿真证据，"
            "不代表 AirSim、目标硬件或实飞结果。"
        ),
        admission_detail,
        follow_up,
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
            "每臂 10 秒；共 13 pair、26 个全新 arm。"
        ),
        (
            f"- 参考实现 `{REFERENCE_IMPLEMENTATION}`；候选实现 "
            f"`{CANDIDATE_IMPLEMENTATION}`；缓存容量 `{CACHE_CAPACITY}`。"
        ),
        "",
        "## 缓存审计",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        (
            "| 候选标识构造减少率 | "
            f"{_fmt(cache['candidate_identity_build_reduction_pct'])}% |"
        ),
        (
            "| 候选缓存命中率 | "
            f"{_fmt(cache['candidate_cache_hit_ratio_pct'])}% |"
        ),
        (
            "| 候选最大当前条目数 | "
            f"{cache['candidate_maximum_entry_count']}/{CACHE_CAPACITY} |"
        ),
        (
            "| 候选最大峰值条目数 | "
            f"{cache['candidate_maximum_peak_entry_count']}/{CACHE_CAPACITY} |"
        ),
        "",
        (
            "每个 arm 均独立检查发布请求守恒和标识构造守恒。候选必须同时出现"
            "命中和缺失且旁路为 0；参考必须全部旁路且不得出现缓存活动。未知字段、"
            "负值、非整数、身份不一致或容量越界直接拒绝证据。"
        ),
        "",
        "## 分组结果",
        "",
        "| 组别 | 指标 | 参考均值 | 候选均值 | 冻结门变化口径 | 候选更优 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    metric_rows = (
        ("d1_fusion_wall_s", "D1 融合墙钟", "improvement_pct"),
        ("d2_association_wall_s", "D2 关联墙钟", "raw_relative_change"),
        ("core_wall_s", "核心墙钟", "improvement_pct"),
        ("maximum_rss_kib", "最大常驻内存", "raw_relative_change"),
        ("real_time_factor", "实时因子", "improvement_pct"),
    )
    for group in _GROUPS:
        group_label = "短时" if group == "short" else "长时"
        for metric, label, change_kind in metric_rows:
            summary = groups[group]["metrics"][metric]
            if change_kind == "improvement_pct":
                change = summary["improvement_pct"]["mean"]
            else:
                change = (
                    summary["ratio_of_group_means"][
                        "raw_relative_change"
                    ]
                    * 100.0
                )
            lines.append(
                f"| {group_label} | {label} | "
                f"{_fmt(summary['reference']['mean'])} | "
                f"{_fmt(summary['candidate']['mean'])} | "
                f"{_fmt(change)}% | "
                f"{summary['candidate_better_count']}/"
                f"{summary['pair_count']} |"
            )
    lines.extend(
        [
            "",
            "D2 关联和内存采用组均值 `(候选-参考)/参考`，负值表示下降。"
            "D1 融合、核心墙钟和实时因子列使用配对正向改善均值。"
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
            "| case | D1 改善 | D2 增幅 | 核心改善 | RSS 增幅 | "
            "构造减少 | 命中率 | 语义 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for pair in result["pairs"]:
        performance = pair["performance"]
        cache_pair = pair["opaque_source_identity_cache_audit"]
        lines.append(
            f"| {pair['case_id']} | "
            f"{_fmt(performance['d1_fusion_wall_s']['improvement_pct'])}% | "
            f"{_fmt(performance['d2_association_wall_s']['raw_relative_change_pct'])}% | "
            f"{_fmt(performance['core_wall_s']['improvement_pct'])}% | "
            f"{_fmt(performance['maximum_rss_kib']['raw_relative_change_pct'])}% | "
            f"{_fmt(cache_pair['candidate_identity_build_reduction_pct'])}% | "
            f"{_fmt(cache_pair['candidate_cache_hit_ratio_pct'])}% | "
            f"{'通过' if pair['business_semantics_passed'] else '失败'} |"
        )
    lines.extend(
        [
            "",
            "## 边界",
            "",
            (
                "D6 在内部重新执行跨 episode 语义比较。只排除预注册的 "
                "`same_runtime_profile` 检查，并对缓存 selector、缓存诊断、"
                "处理派生 episode 标识和性能字段做窄范围归一化。其他在线消息、"
                "计划谱系、治理字段和离线真值制品继续比较。"
            ),
            (
                "本评估只回答显式发布来源键且结构歧义 hold 关闭的 200 对 200 "
                "三维质点矩阵。它不证明默认无来源键 R0 路径获得收益。"
            ),
            (
                "系统实时、AirSim 和目标处理器容量需使用独立证据关闭。"
            ),
            "",
            "## 制品",
            "",
            "- `d1_opaque_source_identity_cache_multiseed_evaluation.json`：完整评估。",
            "- `d1_opaque_source_identity_cache_multiseed_compact.json`：紧凑汇总。",
            "- `d1_opaque_source_identity_cache_multiseed_pairs.csv`：逐 pair 数据。",
            "- `d1_opaque_source_identity_cache_multiseed_curves.png`：性能与缓存曲线。",
            "- `SHA256SUMS`：制品校验值。",
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
        "opaque_source_identity_cache_audit_passed",
        "reference_request_count",
        "candidate_request_count",
        "reference_identity_build_count",
        "candidate_identity_build_count",
        "candidate_identity_build_reduction_pct",
        "candidate_cache_hit_count",
        "candidate_cache_miss_count",
        "candidate_cache_hit_ratio_pct",
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
            cache = pair["opaque_source_identity_cache_audit"]
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
                "opaque_source_identity_cache_audit_passed": pair[
                    "opaque_source_identity_cache_audit_passed"
                ],
                **{
                    name: cache[name]
                    for name in (
                        "reference_request_count",
                        "candidate_request_count",
                        "reference_identity_build_count",
                        "candidate_identity_build_count",
                        "candidate_identity_build_reduction_pct",
                        "candidate_cache_hit_count",
                        "candidate_cache_miss_count",
                        "candidate_cache_hit_ratio_pct",
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
    performance_axis, cache_axis, realtime_axis = axes
    for metric, label, color, raw in (
        ("d1_fusion_wall_s", "D1 fusion improvement", "#1f77b4", False),
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

    cache_axis.plot(
        x,
        [
            float(
                pair["opaque_source_identity_cache_audit"][
                    "candidate_identity_build_reduction_pct"
                ]
            )
            for pair in pairs
        ],
        marker="o",
        label="Identity-build reduction",
        color="#9467bd",
    )
    cache_axis.plot(
        x,
        [
            float(
                pair["opaque_source_identity_cache_audit"][
                    "candidate_cache_hit_ratio_pct"
                ]
            )
            for pair in pairs
        ],
        marker="s",
        label="Cache hit ratio",
        color="#17becf",
    )
    cache_axis.axhline(
        95.0,
        color="#d62728",
        linewidth=1.0,
        linestyle="--",
        label="Admission threshold 95%",
    )
    cache_axis.set_ylabel("Cache metric (%)")
    cache_axis.grid(True, alpha=0.25)
    cache_axis.legend(fontsize=8, loc="best")

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
    fig.suptitle("D1 source-only opaque source identity cache paired evaluation")
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
            "Evaluate the frozen D1 source-only opaque source identity cache matrix"
        )
    )
    parser.add_argument(
        "--evidence-manifest",
        required=True,
        help="completed cache evidence_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="independent compact D6 output directory",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = evaluate_d1_opaque_source_identity_cache_multiseed(
        args.evidence_manifest
    )
    paths = write_d1_opaque_source_identity_cache_multiseed_report(
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
    "CACHE_CAPACITY",
    "CANDIDATE_IMPLEMENTATION",
    "CANDIDATE_IMPLEMENTATION_ID",
    "D1OpaqueSourceIdentityCacheEvidence",
    "D1OpaqueSourceIdentityCacheEvidenceError",
    "D1_OPAQUE_SOURCE_IDENTITY_CACHE_DIAGNOSTICS_SCHEMA_VERSION",
    "D1_OPAQUE_SOURCE_IDENTITY_CACHE_EVALUATION_DATE",
    "D1_OPAQUE_SOURCE_IDENTITY_CACHE_EVIDENCE_SCHEMA_VERSION",
    "D1_OPAQUE_SOURCE_IDENTITY_CACHE_EXPERIMENT_ID",
    "D1_OPAQUE_SOURCE_IDENTITY_CACHE_MATRIX_SCHEMA_VERSION",
    "D1_OPAQUE_SOURCE_IDENTITY_CACHE_MATRIX_SHA256",
    "D1_OPAQUE_SOURCE_IDENTITY_CACHE_MULTISEED_COMPACT_SCHEMA_VERSION",
    "D1_OPAQUE_SOURCE_IDENTITY_CACHE_MULTISEED_EVALUATION_SCHEMA_VERSION",
    "D1_OPAQUE_SOURCE_IDENTITY_CACHE_SOURCE_COMMIT",
    "REFERENCE_IMPLEMENTATION",
    "REFERENCE_IMPLEMENTATION_ID",
    "evaluate_d1_opaque_source_identity_cache_multiseed",
    "load_d1_opaque_source_identity_cache_evidence_manifest",
    "main",
    "render_d1_opaque_source_identity_cache_multiseed_markdown",
    "write_d1_opaque_source_identity_cache_multiseed_report",
]
