from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
import re

import pytest

from d6_evaluation_metrics import (
    D1_COVARIANCE_LIMIT_BOOTSTRAP_RESAMPLES,
    D1_COVARIANCE_LIMIT_CANDIDATE_COMMIT,
    D1_COVARIANCE_LIMIT_EVIDENCE_MANIFEST_SCHEMA_VERSION,
    D1_COVARIANCE_LIMIT_EXPERIMENT_ID,
    D1_COVARIANCE_LIMIT_LONG_DURATION_S,
    D1_COVARIANCE_LIMIT_LONG_SEEDS,
    D1_COVARIANCE_LIMIT_MATRIX_SCHEMA_VERSION,
    D1_COVARIANCE_LIMIT_MULTISEED_LONG_SCHEMA_VERSION,
    D1_COVARIANCE_LIMIT_REFERENCE_COMMIT,
    D1_COVARIANCE_LIMIT_RUNTIME_PROFILE_SHA256,
    D1_COVARIANCE_LIMIT_RUN_FLAGS,
    D1_COVARIANCE_LIMIT_SHORT_DURATION_S,
    D1_COVARIANCE_LIMIT_SHORT_SEEDS,
    D1_COVARIANCE_LIMIT_V1_EXPERIMENT_ID,
    D1_COVARIANCE_LIMIT_V1_KNOWN_MATRIX_REGISTRATION,
    D1_COVARIANCE_LIMIT_V2_CANDIDATE_COMMIT,
    D1_COVARIANCE_LIMIT_V2_COMMON_D2_FIX_SOURCE_COMMIT,
    D1_COVARIANCE_LIMIT_V2_COMMON_D2_FIX_SUBJECT,
    D1_COVARIANCE_LIMIT_V2_EXPERIMENT_ID,
    D1_COVARIANCE_LIMIT_V2_KNOWN_MATRIX_REGISTRATION,
    D1_COVARIANCE_LIMIT_V2_REFERENCE_COMMIT,
    D1CovarianceLimitEvidenceManifestError,
    D1CovarianceLimitMatrixPairInput,
    evaluate_d1_covariance_limit_evidence_manifest,
    evaluate_d1_covariance_limit_multiseed_long,
    load_d1_covariance_limit_evidence_manifest,
    write_d1_covariance_limit_multiseed_long_report,
)
from d6_evaluation_metrics.d1_covariance_limit_multiseed_long import (
    main as multiseed_main,
)


STAGE_FIELDS = [
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
]
RUNTIME_PROFILE = {
    "configuration": {
        "assignment_lease_multiplier": 3.0,
        "capture_learning_artifacts": False,
        "d1_ambiguity_pending_evidence_limit": 4096,
        "d1_centroid_publication_overlay_shadow_enabled": False,
        "d1_coalesce_same_fusion_time": True,
        "d1_d2_structural_ambiguity_hold_enabled": True,
        "d1_identity_neutral_centroid_correction_enabled": False,
        "d1_publish_opaque_source_key": False,
        "d1_radar_assignment_ambiguity_governance_v2": False,
        "d1_scan_event_log_limit": 4096,
        "d1_scan_max_buffer_residence_s": 5.0,
        "d1_scan_max_lateness_s": 0.5,
        "d2_ambiguity_hold_gap_scan_periods": 2,
        "d2_ambiguity_hold_hard_scan_periods": 5,
        "d2_claim_capacity_safety_factor": 2.0,
        "d2_claim_max_lateness_s": 5.0,
        "d2_claim_retention_s": 30.0,
        "d2_replay_coast_grace_s": 0.5,
        "d3_candidate_edges_per_target": 32,
        "d3_human_authorization_state": "approved",
        "d3_unassigned_base_cost": 50.0,
        "d4_advisory_ttl_multiplier": 1.5,
        "d5_active_vision_enabled": True,
        "d5_active_vision_mode": "disabled",
        "d5_active_vision_zoom_fov_deg": 30.0,
        "d5_recon_track_cues_enabled": False,
        "secondary_coverage_ratio": 0.9,
        "secondary_network_full_view_rate": 0.9,
        "terminal_switch_range_m": 120.0,
    },
    "module_stack_schema_version": "scalable3d-module-stack-v1",
    "schema_version": "scalable3d-integrated-stack-runtime-profile-v1",
}
ARM_ORDER_BY_CASE = {
    "short_seed_1101": ["reference", "candidate"],
    "short_seed_1102": ["candidate", "reference"],
    "short_seed_1103": ["reference", "candidate"],
    "short_seed_1104": ["candidate", "reference"],
    "short_seed_1105": ["reference", "candidate"],
    "short_seed_1106": ["candidate", "reference"],
    "short_seed_1107": ["reference", "candidate"],
    "short_seed_1108": ["candidate", "reference"],
    "short_seed_1109": ["reference", "candidate"],
    "short_seed_1110": ["candidate", "reference"],
    "long_seed_1101": ["candidate", "reference"],
    "long_seed_1102": ["reference", "candidate"],
    "long_seed_1103": ["candidate", "reference"],
}


def test_preregistered_matrix_passes_and_outputs_are_deterministic_lf(
    tmp_path: Path,
) -> None:
    pairs = _write_matrix(tmp_path)

    first = _evaluate(pairs)
    second = _evaluate(pairs)

    assert (
        first["schema_version"]
        == D1_COVARIANCE_LIMIT_MULTISEED_LONG_SCHEMA_VERSION
    )
    assert first["d1_optimization_admitted"] is True
    assert first["system_realtime_gap_closed"] is False
    assert first["scope"]["input_pair_count"] == 13
    assert first["groups"]["short"]["pair_count"] == 10
    assert first["groups"]["long"]["pair_count"] == 3
    short_fusion = first["groups"]["short"]["metrics"][
        "d1_fusion_wall_s"
    ]
    assert short_fusion["candidate_lower_count"] == 10
    assert short_fusion["mean_improvement_pct"] == pytest.approx(10.0)
    assert (
        short_fusion["paired_relative_change_pct"]["bootstrap_95_ci"]
        == second["groups"]["short"]["metrics"]["d1_fusion_wall_s"][
            "paired_relative_change_pct"
        ]["bootstrap_95_ci"]
    )
    assert (
        short_fusion["paired_relative_change_pct"]["bootstrap_95_ci"][
            "upper"
        ]
        < 0.0
    )
    growth = first["long_short_unit_cost_growth"]["metrics"][
        "d1_fusion_wall_s"
    ]
    assert growth["availability"] == "available"
    assert growth["seed_count"] == 3
    assert growth["maximum_candidate_relative_degradation_pct"] == (
        pytest.approx(0.0, abs=1e-10)
    )

    paths = write_d1_covariance_limit_multiseed_long_report(
        first, tmp_path / "report"
    )
    csv_bytes = paths["csv"].read_bytes()
    assert b"\r" not in csv_bytes
    assert csv_bytes.count(b"\n") == 14
    rows = list(
        csv.DictReader(paths["csv"].open(newline="", encoding="utf-8"))
    )
    assert len(rows) == 13
    assert {row["group"] for row in rows} == {"short", "long"}
    report = paths["markdown"].read_text(encoding="utf-8")
    assert "D1 优化准入为 **通过**" in report
    assert "系统实时性缺口 **未关闭**" in report


def test_completed_evidence_manifest_loader_and_cli(
    tmp_path: Path,
) -> None:
    pairs = _write_matrix(tmp_path / "evidence")
    manifest_path = _write_evidence_manifest(
        tmp_path / "evidence_manifest.json",
        pairs,
    )

    evidence = load_d1_covariance_limit_evidence_manifest(manifest_path)

    assert D1_COVARIANCE_LIMIT_BOOTSTRAP_RESAMPLES == 10000
    assert evidence.bootstrap_resamples == 10000
    assert evidence.bootstrap_rng_seed == 20260724
    assert evidence.runtime_profile_sha256 == (
        D1_COVARIANCE_LIMIT_RUNTIME_PROFILE_SHA256
    )
    assert len(evidence.pairs) == 13

    output_dir = tmp_path / "manifest_report"
    assert (
        multiseed_main(
            [
                "--evidence-manifest",
                str(manifest_path),
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )
    result = _read_json(
        output_dir
        / "d1_covariance_limit_multiseed_long_evaluation.json"
    )
    assert result["bootstrap"]["resamples"] == 10000
    assert result["input_contract"]["mode"] == "evidence_manifest"
    assert result["input_contract"]["case_count"] == 13
    assert result["d1_optimization_admitted"] is True
    assert result["system_realtime_gap_closed"] is False


def test_v2_completed_evidence_manifest_uses_registered_fix_commits(
    tmp_path: Path,
) -> None:
    pairs = _write_matrix(
        tmp_path / "v2_evidence",
        reference_commit=D1_COVARIANCE_LIMIT_V2_REFERENCE_COMMIT,
        candidate_commit=D1_COVARIANCE_LIMIT_V2_CANDIDATE_COMMIT,
    )
    manifest_path = _write_evidence_manifest(
        tmp_path / "v2_evidence_manifest.json",
        pairs,
        experiment_id=D1_COVARIANCE_LIMIT_V2_EXPERIMENT_ID,
    )

    evidence = load_d1_covariance_limit_evidence_manifest(manifest_path)

    assert evidence.experiment_id == D1_COVARIANCE_LIMIT_V2_EXPERIMENT_ID
    assert evidence.reference_commit == (
        D1_COVARIANCE_LIMIT_V2_REFERENCE_COMMIT
    )
    assert evidence.candidate_commit == (
        D1_COVARIANCE_LIMIT_V2_CANDIDATE_COMMIT
    )
    assert evidence.reference_base_commit == (
        D1_COVARIANCE_LIMIT_REFERENCE_COMMIT
    )
    assert evidence.candidate_base_commit == (
        D1_COVARIANCE_LIMIT_CANDIDATE_COMMIT
    )
    assert evidence.common_d2_fix_source_commit == (
        D1_COVARIANCE_LIMIT_V2_COMMON_D2_FIX_SOURCE_COMMIT
    )
    assert evidence.common_d2_fix_subject == (
        D1_COVARIANCE_LIMIT_V2_COMMON_D2_FIX_SUBJECT
    )
    assert evidence.v1_outputs_reused is False

    result = evaluate_d1_covariance_limit_evidence_manifest(manifest_path)

    assert result["scope"]["reference_commit"] == (
        D1_COVARIANCE_LIMIT_V2_REFERENCE_COMMIT
    )
    assert result["scope"]["candidate_commit"] == (
        D1_COVARIANCE_LIMIT_V2_CANDIDATE_COMMIT
    )
    assert result["input_contract"]["experiment_id"] == (
        D1_COVARIANCE_LIMIT_V2_EXPERIMENT_ID
    )
    assert result["input_contract"]["v1_outputs_reused"] is False
    assert result["d1_optimization_admitted"] is True
    assert result["system_realtime_gap_closed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "matrix_experiment_id",
        "reference_commit",
        "candidate_commit",
        "reference_base_commit",
        "candidate_base_commit",
        "common_d2_fix_source_commit",
        "common_d2_fix_subject",
        "v1_outputs_reused",
    ],
)
def test_v2_registered_provenance_tampering_fails_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    pairs = _write_matrix(
        tmp_path / mutation / "v2_evidence",
        reference_commit=D1_COVARIANCE_LIMIT_V2_REFERENCE_COMMIT,
        candidate_commit=D1_COVARIANCE_LIMIT_V2_CANDIDATE_COMMIT,
    )
    manifest_path = _write_evidence_manifest(
        tmp_path / mutation / "v2_evidence_manifest.json",
        pairs,
        experiment_id=D1_COVARIANCE_LIMIT_V2_EXPERIMENT_ID,
    )
    payload = _read_json(manifest_path)
    matrix = payload["matrix"]
    assert isinstance(matrix, dict)
    if mutation == "matrix_experiment_id":
        matrix["experiment_id"] = D1_COVARIANCE_LIMIT_V1_EXPERIMENT_ID
    elif mutation == "v1_outputs_reused":
        boundary = matrix["evidence_boundary"]
        assert isinstance(boundary, dict)
        boundary[mutation] = True
    elif mutation == "common_d2_fix_source_commit":
        matrix[mutation] = "0000000"
    elif mutation == "common_d2_fix_subject":
        matrix[mutation] = "tampered"
    else:
        matrix[mutation] = "0" * 40
    _write_json(manifest_path, payload)

    with pytest.raises(D1CovarianceLimitEvidenceManifestError):
        load_d1_covariance_limit_evidence_manifest(manifest_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "manifest_schema",
        "experiment_id",
        "manifest_status",
        "missing_case",
        "case_seed",
        "matrix_commit",
        "matrix_seed",
        "matrix_duration",
        "matrix_scale",
        "run_flags",
        "bootstrap",
        "admission_gate",
        "runtime_profile",
        "unexpected_v2_provenance",
        "arm_label",
        "arm_commit",
        "arm_status",
        "arm_return_code",
        "missing_resource",
        "cross_status",
    ],
)
def test_evidence_manifest_tampering_fails_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    pairs = _write_matrix(tmp_path / mutation / "evidence")
    manifest_path = _write_evidence_manifest(
        tmp_path / mutation / "evidence_manifest.json",
        pairs,
    )
    payload = _read_json(manifest_path)
    _tamper_evidence_manifest(payload, mutation)
    _write_json(manifest_path, payload)

    with pytest.raises(D1CovarianceLimitEvidenceManifestError):
        load_d1_covariance_limit_evidence_manifest(manifest_path)


def test_evidence_manifest_and_explicit_pair_are_cli_mutually_exclusive(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit) as captured:
        multiseed_main(
            [
                "--output-dir",
                str(tmp_path / "report"),
                "--evidence-manifest",
                str(tmp_path / "evidence_manifest.json"),
                "--pair",
                "short",
                "1101",
                "2.2",
                "ref",
                "cand",
                "ref_resource",
                "cand_resource",
                "cross",
            ]
        )

    assert captured.value.code == 2


def test_missing_preregistered_pair_fails_closed(tmp_path: Path) -> None:
    pairs = _write_matrix(tmp_path)[:-1]

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    assert (
        result["registration_checks"]["matrix_exactly_preregistered"][
            "passed"
        ]
        is False
    )


def test_config_difference_beyond_seed_and_duration_fails(
    tmp_path: Path,
) -> None:
    pairs = _write_matrix(tmp_path)
    pair = _find_pair(pairs, "short", 1105)
    for episode in (
        pair.reference_episode_dir,
        pair.candidate_episode_dir,
    ):
        config_path = episode / "scenario_config.json"
        manifest_path = episode / "manifest.json"
        config = _read_json(config_path)
        config["sensor_fixture_variant"] = "drifted"
        manifest = _read_json(manifest_path)
        manifest["config_sha256"] = _canonical_sha256(config)
        _write_json(config_path, config)
        _write_json(manifest_path, manifest)

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    assert (
        result["registration_checks"][
            "config_equal_excluding_seed_duration"
        ]["passed"]
        is False
    )


def test_runtime_profile_hold_disabled_fails_closed(tmp_path: Path) -> None:
    pairs = _write_matrix(tmp_path)
    pair = _find_pair(pairs, "short", 1106)
    cross = _read_json(pair.cross_build_path)
    for arm_name, episode in (
        ("reference", pair.reference_episode_dir),
        ("candidate", pair.candidate_episode_dir),
    ):
        manifest_path = episode / "manifest.json"
        manifest = _read_json(manifest_path)
        manifest["runtime_profile"]["configuration"][
            "d1_d2_structural_ambiguity_hold_enabled"
        ] = False
        manifest["runtime_profile_sha256"] = _canonical_sha256(
            manifest["runtime_profile"]
        )
        cross[arm_name]["runtime_profile_sha256"] = manifest[
            "runtime_profile_sha256"
        ]
        _write_json(manifest_path, manifest)
    _write_json(pair.cross_build_path, cross)

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    evaluated = next(
        item
        for item in result["pairs"]
        if item["group"] == "short" and item["seed"] == 1106
    )
    assert (
        evaluated["matrix_registration_checks"][
            "structural_ambiguity_hold_enabled"
        ]["passed"]
        is False
    )


def test_cross_build_false_fails_closed(tmp_path: Path) -> None:
    pairs = _write_matrix(tmp_path)
    path = _find_pair(pairs, "long", 1102).cross_build_path
    cross = _read_json(path)
    cross["passed"] = False
    _write_json(path, cross)

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    assert (
        result["admission_gates"]["semantic_truth_exit_all_passed"][
            "passed"
        ]
        is False
    )


@pytest.mark.parametrize("failure", ["truth", "exit"])
def test_truth_or_process_exit_failure_closes_admission(
    tmp_path: Path,
    failure: str,
) -> None:
    pairs = _write_matrix(tmp_path)
    pair = _find_pair(pairs, "short", 1103)
    if failure == "truth":
        path = pair.candidate_episode_dir / "summary.json"
        summary = _read_json(path)
        summary["online_truth_use_count"] = 1
        _write_json(path, summary)
    else:
        path = pair.candidate_resource_path
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "Exit status: 0", "Exit status: 4"
            ),
            encoding="utf-8",
        )

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    assert (
        result["admission_gates"]["semantic_truth_exit_all_passed"][
            "passed"
        ]
        is False
    )


def test_short_faster_count_gate_fails_at_seven_of_ten(
    tmp_path: Path,
) -> None:
    pairs = _write_matrix(tmp_path)
    for seed in (1101, 1102, 1103):
        pair = _find_pair(pairs, "short", seed)
        _replace_stage_wall(
            pair.candidate_episode_dir,
            stage="module.d1_fusion",
            wall_time_s=10.5 + (seed - 1101) * 0.01,
        )

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    assert (
        result["groups"]["short"]["metrics"]["d1_fusion_wall_s"][
            "candidate_lower_count"
        ]
        == 7
    )
    assert (
        result["admission_gates"][
            "short_fusion_at_least_eight_of_ten_faster"
        ]["passed"]
        is False
    )


def test_long_short_unit_cost_growth_over_five_percent_fails(
    tmp_path: Path,
) -> None:
    pairs = _write_matrix(tmp_path)
    for seed in D1_COVARIANCE_LIMIT_LONG_SEEDS:
        pair = _find_pair(pairs, "long", seed)
        reference_wall = 40.0 + (seed - 1101) * 0.2
        _replace_stage_wall(
            pair.candidate_episode_dir,
            stage="module.d1_fusion",
            wall_time_s=reference_wall * 0.9475,
        )

    result = _evaluate(pairs)

    assert (
        result["groups"]["long"]["metrics"]["d1_fusion_wall_s"][
            "mean_improvement_pct"
        ]
        >= 5.0
    )
    growth = result["long_short_unit_cost_growth"]["metrics"][
        "d1_fusion_wall_s"
    ]
    assert growth["maximum_candidate_relative_degradation_pct"] > 5.0
    assert (
        result["admission_gates"][
            "candidate_long_short_unit_cost_growth_not_over_five_percent"
        ]["passed"]
        is False
    )


def test_single_rss_pair_over_five_percent_fails(tmp_path: Path) -> None:
    pairs = _write_matrix(tmp_path)
    pair = _find_pair(pairs, "short", 1108)
    reference_rss = _resource_rss(pair.reference_resource_path)
    _replace_resource_rss(
        pair.candidate_resource_path,
        int(reference_rss * 1.10),
    )

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    assert (
        result["admission_gates"][
            "every_rss_pair_not_degraded_over_five_percent"
        ]["passed"]
        is False
    )


@pytest.mark.parametrize(
    ("failure", "gate_name"),
    [
        (
            "short_mean",
            "short_fusion_mean_improvement_at_least_five_percent",
        ),
        (
            "short_ci",
            "short_fusion_paired_bootstrap_ci_upper_below_zero",
        ),
        ("short_p95", "short_fusion_p95_aggregate_improved"),
        (
            "long_count",
            "long_fusion_at_least_two_of_three_faster",
        ),
        (
            "long_mean",
            "long_fusion_mean_improvement_at_least_five_percent",
        ),
        (
            "core_mean",
            "core_wall_group_means_not_degraded_over_five_percent",
        ),
        (
            "rss_mean",
            "rss_group_means_not_degraded_over_five_percent",
        ),
    ],
)
def test_each_remaining_performance_gate_fails_closed(
    tmp_path: Path,
    failure: str,
    gate_name: str,
) -> None:
    pairs = _write_matrix(tmp_path)
    if failure == "short_mean":
        for seed in D1_COVARIANCE_LIMIT_SHORT_SEEDS:
            pair = _find_pair(pairs, "short", seed)
            reference = _stage_wall(
                pair.reference_episode_dir, "module.d1_fusion"
            )
            _replace_stage_wall(
                pair.candidate_episode_dir,
                stage="module.d1_fusion",
                wall_time_s=reference * 0.96,
            )
    elif failure == "short_ci":
        for index, seed in enumerate(D1_COVARIANCE_LIMIT_SHORT_SEEDS):
            pair = _find_pair(pairs, "short", seed)
            reference = _stage_wall(
                pair.reference_episode_dir, "module.d1_fusion"
            )
            factor = 0.70 if index < 8 else 1.95
            _replace_stage_wall(
                pair.candidate_episode_dir,
                stage="module.d1_fusion",
                wall_time_s=reference * factor,
            )
    elif failure == "short_p95":
        for seed in D1_COVARIANCE_LIMIT_SHORT_SEEDS:
            pair = _find_pair(pairs, "short", seed)
            _replace_stage_p95(
                pair.candidate_episode_dir,
                stage="module.d1_fusion",
                p95_wall_time_ms=1000.0,
            )
    elif failure == "long_count":
        for seed in (1101, 1102):
            pair = _find_pair(pairs, "long", seed)
            reference = _stage_wall(
                pair.reference_episode_dir, "module.d1_fusion"
            )
            _replace_stage_wall(
                pair.candidate_episode_dir,
                stage="module.d1_fusion",
                wall_time_s=reference * 1.05,
            )
    elif failure == "long_mean":
        for seed in D1_COVARIANCE_LIMIT_LONG_SEEDS:
            pair = _find_pair(pairs, "long", seed)
            reference = _stage_wall(
                pair.reference_episode_dir, "module.d1_fusion"
            )
            _replace_stage_wall(
                pair.candidate_episode_dir,
                stage="module.d1_fusion",
                wall_time_s=reference * 0.96,
            )
    elif failure == "core_mean":
        for seed in D1_COVARIANCE_LIMIT_SHORT_SEEDS:
            pair = _find_pair(pairs, "short", seed)
            _replace_summary_core_wall(
                pair.reference_episode_dir,
                pair.candidate_episode_dir,
                factor=1.06,
            )
    else:
        for seed in D1_COVARIANCE_LIMIT_SHORT_SEEDS:
            pair = _find_pair(pairs, "short", seed)
            reference_rss = _resource_rss(pair.reference_resource_path)
            _replace_resource_rss(
                pair.candidate_resource_path,
                int(reference_rss * 1.06),
            )

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    assert result["admission_gates"][gate_name]["passed"] is False


def _evaluate(
    pairs: list[D1CovarianceLimitMatrixPairInput],
) -> dict[str, object]:
    return evaluate_d1_covariance_limit_multiseed_long(
        pairs,
        bootstrap_resamples=300,
        bootstrap_rng_seed=20260724,
    )


def _write_matrix(
    root: Path,
    *,
    reference_commit: str = D1_COVARIANCE_LIMIT_REFERENCE_COMMIT,
    candidate_commit: str = D1_COVARIANCE_LIMIT_CANDIDATE_COMMIT,
) -> list[D1CovarianceLimitMatrixPairInput]:
    pairs = []
    for group, seeds, duration in (
        (
            "short",
            D1_COVARIANCE_LIMIT_SHORT_SEEDS,
            D1_COVARIANCE_LIMIT_SHORT_DURATION_S,
        ),
        (
            "long",
            D1_COVARIANCE_LIMIT_LONG_SEEDS,
            D1_COVARIANCE_LIMIT_LONG_DURATION_S,
        ),
    ):
        for seed in seeds:
            offset = seed - 1101
            if group == "short":
                reference_fusion = 10.0 + offset * 0.05
                candidate_fusion = reference_fusion * 0.90
                reference_p95 = 200.0 + offset
                candidate_p95 = reference_p95 * 0.90
                reference_core = 12.0 + offset * 0.04
                candidate_core = reference_core * 0.98
                reference_elapsed = 15.0 + offset * 0.04
                candidate_elapsed = reference_elapsed * 0.98
                observation_count = 2035 + offset
                reference_rss = 100_000 + offset * 10
            else:
                reference_fusion = 40.0 + offset * 0.2
                candidate_fusion = reference_fusion * 0.90
                reference_p95 = 600.0 + offset
                candidate_p95 = reference_p95 * 0.90
                reference_core = 50.0 + offset * 0.2
                candidate_core = reference_core * 0.98
                reference_elapsed = 55.0 + offset * 0.2
                candidate_elapsed = reference_elapsed * 0.98
                observation_count = 9000 + offset
                reference_rss = 120_000 + offset * 10
            candidate_rss = int(reference_rss * 1.01)
            pair_root = root / f"{group}_{seed}"
            reference = pair_root / "arm_a"
            candidate = pair_root / "arm_b"
            reference_resource = pair_root / "resource_a.txt"
            candidate_resource = pair_root / "resource_b.txt"
            cross_path = pair_root / "cross.json"
            _write_episode(
                reference,
                commit=reference_commit,
                seed=seed,
                duration_s=duration,
                fusion_wall_s=reference_fusion,
                fusion_p95_ms=reference_p95,
                core_wall_s=reference_core,
                observation_count=observation_count,
            )
            _write_episode(
                candidate,
                commit=candidate_commit,
                seed=seed,
                duration_s=duration,
                fusion_wall_s=candidate_fusion,
                fusion_p95_ms=candidate_p95,
                core_wall_s=candidate_core,
                observation_count=observation_count,
            )
            _write_resource(
                reference_resource,
                elapsed_s=reference_elapsed,
                maximum_rss_kib=reference_rss,
            )
            _write_resource(
                candidate_resource,
                elapsed_s=candidate_elapsed,
                maximum_rss_kib=candidate_rss,
            )
            _write_cross_build(cross_path, reference, candidate, duration)
            pairs.append(
                D1CovarianceLimitMatrixPairInput(
                    group=group,
                    seed=seed,
                    duration_s=duration,
                    reference_episode_dir=reference,
                    candidate_episode_dir=candidate,
                    reference_resource_path=reference_resource,
                    candidate_resource_path=candidate_resource,
                    cross_build_path=cross_path,
                )
            )
    return pairs


def _write_evidence_manifest(
    path: Path,
    pairs: list[D1CovarianceLimitMatrixPairInput],
    *,
    experiment_id: str = D1_COVARIANCE_LIMIT_V1_EXPERIMENT_ID,
) -> Path:
    registration = {
        D1_COVARIANCE_LIMIT_V1_EXPERIMENT_ID: (
            D1_COVARIANCE_LIMIT_V1_KNOWN_MATRIX_REGISTRATION
        ),
        D1_COVARIANCE_LIMIT_V2_EXPERIMENT_ID: (
            D1_COVARIANCE_LIMIT_V2_KNOWN_MATRIX_REGISTRATION
        ),
    }[experiment_id]
    output_root = pairs[0].reference_episode_dir.parent.parent
    cases = []
    manifest_cases = []
    for pair in pairs:
        case_id = f"{pair.group}_seed_{pair.seed}"
        arm_order = ARM_ORDER_BY_CASE[case_id]
        cases.append(
            {
                "case_id": case_id,
                "group": pair.group,
                "seed": pair.seed,
                "duration_s": pair.duration_s,
                "arm_order": arm_order,
            }
        )
        arms = {}
        for arm, episode_dir, resource_path, commit in (
            (
                "reference",
                pair.reference_episode_dir,
                pair.reference_resource_path,
                registration.reference_commit,
            ),
            (
                "candidate",
                pair.candidate_episode_dir,
                pair.candidate_resource_path,
                registration.candidate_commit,
            ),
        ):
            arms[arm] = {
                "arm": arm,
                "expected_commit": commit,
                "worktree": str(path.parent / f"{arm}_worktree"),
                "episode_dir": str(episode_dir),
                "resource_path": str(resource_path),
                "stdout_path": str(
                    episode_dir.parent / f"{arm}_stdout.log"
                ),
                "stderr_path": str(
                    episode_dir.parent / f"{arm}_stderr.log"
                ),
                "command": ["python3", "run_episode.py"],
                "status": "complete",
                "return_code": 0,
            }
        manifest_cases.append(
            {
                "case_id": case_id,
                "group": pair.group,
                "seed": pair.seed,
                "duration_s": pair.duration_s,
                "arm_order": arm_order,
                "arms": arms,
                "cross_build_dir": str(
                    pair.cross_build_path.parent / "cross_build"
                ),
                "cross_build_json": str(pair.cross_build_path),
                "cross_build_status": "passed",
            }
        )
    matrix = {
        "schema_version": D1_COVARIANCE_LIMIT_MATRIX_SCHEMA_VERSION,
        "experiment_id": registration.experiment_id,
        "reference_commit": registration.reference_commit,
        "candidate_commit": registration.candidate_commit,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "run_flags": list(D1_COVARIANCE_LIMIT_RUN_FLAGS),
        "runtime_profile_sha256": (
            D1_COVARIANCE_LIMIT_RUNTIME_PROFILE_SHA256
        ),
        "cooldown_s": 2.0,
        "bootstrap_seed": 20260724,
        "bootstrap_resamples": 10000,
        "cases": cases,
        "admission_gates": {
            "short_minimum_candidate_faster_count": 8,
            "short_minimum_fusion_improvement_pct": 5.0,
            "short_bootstrap_relative_change_upper_bound_pct": 0.0,
            "long_minimum_candidate_faster_count": 2,
            "long_minimum_fusion_improvement_pct": 5.0,
            "maximum_long_short_unit_cost_growth_degradation_pct": 5.0,
            "maximum_core_wall_mean_increase_pct": 5.0,
            "maximum_rss_mean_increase_pct": 5.0,
            "maximum_any_pair_rss_increase_pct": 5.0,
        },
        "evidence_boundary": {
            "simulation_mode": "three_dimensional_point_mass",
            "airsim_evidence": False,
            "truth_is_online_control_input": False,
            "system_realtime_requires_real_time_factor_at_least_one": True,
        },
    }
    if registration.reference_base_commit is not None:
        matrix.update(
            {
                "reference_base_commit": (
                    registration.reference_base_commit
                ),
                "candidate_base_commit": (
                    registration.candidate_base_commit
                ),
                "common_d2_fix_source_commit": (
                    registration.common_d2_fix_source_commit
                ),
                "common_d2_fix_subject": (
                    registration.common_d2_fix_subject
                ),
            }
        )
        boundary = matrix["evidence_boundary"]
        assert isinstance(boundary, dict)
        boundary["v1_outputs_reused"] = registration.v1_outputs_reused
    matrix_path = path.parent / "matrix.json"
    _write_json(matrix_path, matrix)
    _write_json(
        path,
        {
            "schema_version": (
                D1_COVARIANCE_LIMIT_EVIDENCE_MANIFEST_SCHEMA_VERSION
            ),
            "experiment_id": registration.experiment_id,
            "matrix_path": str(matrix_path),
            "matrix": matrix,
            "output_root": str(output_root),
            "status": "complete",
            "started_at_utc": "2026-07-24T00:00:00+00:00",
            "completed_at_utc": "2026-07-24T01:00:00+00:00",
            "cases": manifest_cases,
        },
    )
    return path


def _tamper_evidence_manifest(
    payload: dict[str, object],
    mutation: str,
) -> None:
    matrix = payload["matrix"]
    cases = payload["cases"]
    assert isinstance(matrix, dict)
    assert isinstance(cases, list)
    matrix_cases = matrix["cases"]
    assert isinstance(matrix_cases, list)
    first_case = cases[0]
    first_matrix_case = matrix_cases[0]
    assert isinstance(first_case, dict)
    assert isinstance(first_matrix_case, dict)
    arms = first_case["arms"]
    assert isinstance(arms, dict)
    reference = arms["reference"]
    assert isinstance(reference, dict)
    if mutation == "manifest_schema":
        payload["schema_version"] = "tampered"
    elif mutation == "experiment_id":
        payload["experiment_id"] = "tampered"
    elif mutation == "manifest_status":
        payload["status"] = "running"
    elif mutation == "missing_case":
        cases.pop()
    elif mutation == "case_seed":
        first_case["seed"] = 9999
    elif mutation == "matrix_commit":
        matrix["reference_commit"] = "0" * 40
    elif mutation == "matrix_seed":
        first_matrix_case["seed"] = 9999
    elif mutation == "matrix_duration":
        first_matrix_case["duration_s"] = 3.0
    elif mutation == "matrix_scale":
        matrix["target_count"] = 199
    elif mutation == "run_flags":
        matrix["run_flags"] = ["--integrated-stack"]
    elif mutation == "bootstrap":
        matrix["bootstrap_resamples"] = 9999
    elif mutation == "admission_gate":
        gates = matrix["admission_gates"]
        assert isinstance(gates, dict)
        gates["short_minimum_candidate_faster_count"] = 7
    elif mutation == "runtime_profile":
        matrix["runtime_profile_sha256"] = "0" * 64
    elif mutation == "unexpected_v2_provenance":
        matrix["reference_base_commit"] = (
            D1_COVARIANCE_LIMIT_REFERENCE_COMMIT
        )
    elif mutation == "arm_label":
        reference["arm"] = "candidate"
    elif mutation == "arm_commit":
        reference["expected_commit"] = "0" * 40
    elif mutation == "arm_status":
        reference["status"] = "running"
    elif mutation == "arm_return_code":
        reference["return_code"] = 1
    elif mutation == "missing_resource":
        reference["resource_path"] = str(
            Path(str(reference["resource_path"])).with_name("missing.txt")
        )
    elif mutation == "cross_status":
        first_case["cross_build_status"] = "failed"
    else:
        raise AssertionError(f"unsupported mutation: {mutation}")


def _write_episode(
    directory: Path,
    *,
    commit: str,
    seed: int,
    duration_s: float,
    fusion_wall_s: float,
    fusion_p95_ms: float,
    core_wall_s: float,
    observation_count: int,
) -> None:
    directory.mkdir(parents=True)
    config = {
        "schema_version": "scalable3d-scenario-v1",
        "scenario_name": "preregistered_200v200",
        "scenario_version": "preregistered-200v200-v1",
        "seed": seed,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "duration_s": duration_s,
        "sensor_fixture": "frozen",
    }
    runtime_profile = copy.deepcopy(RUNTIME_PROFILE)
    assert (
        _canonical_sha256(runtime_profile)
        == D1_COVARIANCE_LIMIT_RUNTIME_PROFILE_SHA256
    )
    manifest = {
        "bus_schema": "scalable3d-episode-bus-v1",
        "config_sha256": _canonical_sha256(config),
        "d1_model_version": "d1-scalable3d-fusion-v1",
        "d2_model_version": "d2-scalable3d-association-v1",
        "d3_policy_version": "d3-scalable3d-rule-cost-v1",
        "d4_policy_version": "d4-region-resource-rule-v1",
        "d5_model_version": "d5-scalable3d-geometry-rule-v1",
        "d7_model_version": "d7-scalable3d-guidance-v1",
        "episode_id": f"fixture-s{seed}-d{duration_s}",
        "git_commit": commit,
        "offline_truth_schema": "scalable3d-offline-truth-v2",
        "online_observation_schema": "scalable3d-observation-v1",
        "repository_dirty": False,
        "runtime_profile": runtime_profile,
        "runtime_profile_schema": (
            "scalable3d-integrated-stack-runtime-profile-v1"
        ),
        "runtime_profile_sha256": _canonical_sha256(runtime_profile),
        "scenario_name": "preregistered_200v200",
        "scenario_schema": "scalable3d-scenario-v1",
        "scenario_version": "preregistered-200v200-v1",
        "seed": seed,
        "threshold_version": "scalable3d-thresholds-v1",
        "world_schema": "scalable3d-world-v1",
    }
    summary = {
        "episode_id": f"fixture-s{seed}-d{duration_s}",
        "scenario_name": "preregistered_200v200",
        "scenario_version": "preregistered-200v200-v1",
        "seed": seed,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "simulated_duration_s": duration_s,
        "online_observation_count": observation_count,
        "online_truth_use_count": 0,
        "finite_state": True,
        "wall_time_s": core_wall_s,
        "real_time_factor": duration_s / core_wall_s,
        "module_final_diagnostics": {
            "schema_version": "scalable3d-module-stack-v1"
        },
    }
    _write_json(directory / "scenario_config.json", config)
    _write_json(directory / "manifest.json", manifest)
    _write_json(directory / "summary.json", summary)
    for name in (
        "online_observations.jsonl",
        "offline_proximity_intercepts.jsonl",
        "offline_truth_labels.jsonl",
    ):
        (directory / name).write_text("", encoding="utf-8")
    call_count = 89 if duration_s == 2.2 else 401
    _write_stage_rows(
        directory / "stage_timings.csv",
        [
            _stage_row(
                "module.d1_fusion",
                call_count=call_count,
                wall_time_s=fusion_wall_s,
                p95_wall_time_ms=fusion_p95_ms,
            ),
            _stage_row(
                "module.d1_scan_input",
                call_count=call_count,
                wall_time_s=duration_s * 0.8,
                p95_wall_time_ms=120.0,
            ),
        ],
    )


def _stage_row(
    stage: str,
    *,
    call_count: int,
    wall_time_s: float,
    p95_wall_time_ms: float,
) -> dict[str, object]:
    mean_ms = wall_time_s * 1000.0 / call_count
    return {
        "schema_version": "scalable3d-stage-timings-v2",
        "stage": stage,
        "call_count": call_count,
        "wall_time_s": wall_time_s,
        "mean_wall_time_ms": mean_ms,
        "p50_wall_time_ms": min(mean_ms, p95_wall_time_ms),
        "p95_wall_time_ms": max(mean_ms, p95_wall_time_ms),
        "max_wall_time_ms": max(mean_ms, p95_wall_time_ms) * 1.05,
        "distribution_available": True,
        "distribution_unavailable_reason": "",
    }


def _write_stage_rows(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=STAGE_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _replace_stage_wall(
    episode: Path,
    *,
    stage: str,
    wall_time_s: float,
) -> None:
    path = episode / "stage_timings.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    for row in rows:
        if row["stage"] != stage:
            continue
        call_count = int(row["call_count"])
        mean_ms = wall_time_s * 1000.0 / call_count
        row["wall_time_s"] = str(wall_time_s)
        row["mean_wall_time_ms"] = str(mean_ms)
        row["p50_wall_time_ms"] = str(
            min(mean_ms, float(row["p95_wall_time_ms"]))
        )
        row["max_wall_time_ms"] = str(
            max(
                mean_ms,
                float(row["p95_wall_time_ms"]),
                float(row["max_wall_time_ms"]),
            )
        )
    _write_stage_rows(path, rows)


def _replace_stage_p95(
    episode: Path,
    *,
    stage: str,
    p95_wall_time_ms: float,
) -> None:
    path = episode / "stage_timings.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    for row in rows:
        if row["stage"] != stage:
            continue
        mean_ms = float(row["mean_wall_time_ms"])
        row["p50_wall_time_ms"] = str(min(mean_ms, p95_wall_time_ms))
        row["p95_wall_time_ms"] = str(max(mean_ms, p95_wall_time_ms))
        row["max_wall_time_ms"] = str(max(mean_ms, p95_wall_time_ms) * 1.05)
    _write_stage_rows(path, rows)


def _stage_wall(episode: Path, stage: str) -> float:
    rows = csv.DictReader(
        (episode / "stage_timings.csv").open(newline="", encoding="utf-8")
    )
    return float(next(row for row in rows if row["stage"] == stage)["wall_time_s"])


def _replace_summary_core_wall(
    reference_episode: Path,
    candidate_episode: Path,
    *,
    factor: float,
) -> None:
    reference = _read_json(reference_episode / "summary.json")
    candidate_path = candidate_episode / "summary.json"
    candidate = _read_json(candidate_path)
    candidate["wall_time_s"] = float(reference["wall_time_s"]) * factor
    candidate["real_time_factor"] = (
        float(candidate["simulated_duration_s"])
        / float(candidate["wall_time_s"])
    )
    _write_json(candidate_path, candidate)


def _write_resource(
    path: Path,
    *,
    elapsed_s: float,
    maximum_rss_kib: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    minutes = int(elapsed_s // 60)
    seconds = elapsed_s - minutes * 60
    path.write_text(
        "\n".join(
            [
                (
                    "Elapsed (wall clock) time (h:mm:ss or m:ss): "
                    f"{minutes}:{seconds:05.2f}"
                ),
                (
                    "Maximum resident set size (kbytes): "
                    f"{maximum_rss_kib}"
                ),
                "Exit status: 0",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_cross_build(
    path: Path,
    reference_dir: Path,
    candidate_dir: Path,
    duration_s: float,
) -> None:
    reference = _read_json(reference_dir / "manifest.json")
    candidate = _read_json(candidate_dir / "manifest.json")
    checks = {
        "candidate_source_clean": True,
        "normalized_online_payloads_equal": True,
        "reference_source_clean": True,
        "same_duration": True,
        "same_runtime_profile": True,
        "same_scenario_config": True,
        "same_scenario_version": True,
        "same_seed": True,
        "summary_contract_equal": True,
    }
    _write_json(
        path,
        {
            "schema_version": (
                "scalable3d-cross-build-semantic-equivalence-v1"
            ),
            "passed": True,
            "checks": checks,
            "reference": _cross_arm(
                reference_dir, reference, duration_s
            ),
            "candidate": _cross_arm(
                candidate_dir, candidate, duration_s
            ),
            "online_bus": {"normalized_online_payloads_equal": True},
        },
    )


def _cross_arm(
    episode_dir: Path,
    manifest: dict[str, object],
    duration_s: float,
) -> dict[str, object]:
    return {
        "duration_s": duration_s,
        "episode_dir": str(episode_dir.resolve()),
        "git_commit": manifest["git_commit"],
        "repository_dirty": False,
        "runtime_profile_sha256": manifest["runtime_profile_sha256"],
        "scenario_version": manifest["scenario_version"],
        "seed": manifest["seed"],
    }


def _find_pair(
    pairs: list[D1CovarianceLimitMatrixPairInput],
    group: str,
    seed: int,
) -> D1CovarianceLimitMatrixPairInput:
    return next(
        pair
        for pair in pairs
        if pair.group == group and pair.seed == seed
    )


def _resource_rss(path: Path) -> int:
    match = re.search(
        r"Maximum resident set size \(kbytes\):\s*(\d+)",
        path.read_text(encoding="utf-8"),
    )
    assert match is not None
    return int(match.group(1))


def _replace_resource_rss(path: Path, value: int) -> None:
    text = re.sub(
        r"Maximum resident set size \(kbytes\):\s*\d+",
        f"Maximum resident set size (kbytes): {value}",
        path.read_text(encoding="utf-8"),
    )
    path.write_text(text, encoding="utf-8")


def _canonical_sha256(value: dict[str, object]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value
