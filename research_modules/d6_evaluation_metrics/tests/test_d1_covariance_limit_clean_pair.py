from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics import (
    D1_COVARIANCE_LIMIT_CLEAN_PAIR_SCHEMA_VERSION,
    D1CovarianceLimitCleanPairInput,
    evaluate_d1_covariance_limit_clean_pairs,
    write_d1_covariance_limit_clean_pair_report,
)


REFERENCE_COMMIT = "7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d"
CANDIDATE_COMMIT = "95bf46e34321127313757986bb28bfb14b7e3c59"
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


def test_clean_three_pair_admission_and_report_outputs(tmp_path: Path) -> None:
    pairs = _write_suite(tmp_path)

    result = _evaluate(pairs)

    assert (
        result["schema_version"]
        == D1_COVARIANCE_LIMIT_CLEAN_PAIR_SCHEMA_VERSION
    )
    assert result["d1_optimization_admitted"] is True
    assert result["system_realtime_gap_closed"] is False
    assert result["scope"]["distinct_seed_count"] == 1
    assert (
        result["aggregate_metrics"]["d1_fusion_wall_s"][
            "candidate_lower_count"
        ]
        == 3
    )
    assert (
        result["aggregate_metrics"]["d1_fusion_wall_s"]["improvement_pct"]
        > 5.0
    )
    assert all(
        pair["business_semantics_passed"] for pair in result["pairs"]
    )

    paths = write_d1_covariance_limit_clean_pair_report(
        result, tmp_path / "report"
    )
    assert set(paths) == {"json", "csv", "markdown"}
    assert all(path.is_file() for path in paths.values())
    rows = list(
        csv.DictReader(paths["csv"].open(newline="", encoding="utf-8"))
    )
    assert len(rows) == 6
    assert {row["arm"] for row in rows} == {"reference", "candidate"}
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "D1 优化准入结论为 **通过**" in markdown
    assert "系统实时性缺口 **未关闭**" in markdown
    assert "不是多 seed、AirSim 或实机容量试验" in markdown


def test_cross_build_false_fails_closed(tmp_path: Path) -> None:
    pairs = _write_suite(tmp_path)
    cross_path = pairs[0].cross_build_path
    cross = _read_json(cross_path)
    cross["passed"] = False
    _write_json(cross_path, cross)

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    assert (
        result["pairs"][0]["cross_build_checks"]["cross_build_passed"][
            "passed"
        ]
        is False
    )
    assert (
        result["admission_gates"]["business_semantics_all_pairs"]["passed"]
        is False
    )


def test_report_csv_uses_lf_without_carriage_return(
    tmp_path: Path,
) -> None:
    result = _evaluate(_write_suite(tmp_path))

    paths = write_d1_covariance_limit_clean_pair_report(
        result, tmp_path / "report"
    )

    csv_bytes = paths["csv"].read_bytes()
    assert b"\r" not in csv_bytes
    assert csv_bytes.count(b"\n") == 7


@pytest.mark.parametrize("mismatch", ["config", "seed"])
def test_config_or_seed_mismatch_fails_closed(
    tmp_path: Path,
    mismatch: str,
) -> None:
    pairs = _write_suite(tmp_path)
    pair = pairs[0]
    config_path = pair.candidate_episode_dir / "scenario_config.json"
    manifest_path = pair.candidate_episode_dir / "manifest.json"
    summary_path = pair.candidate_episode_dir / "summary.json"
    cross_path = pair.cross_build_path
    config = _read_json(config_path)
    manifest = _read_json(manifest_path)
    summary = _read_json(summary_path)
    cross = _read_json(cross_path)
    if mismatch == "config":
        config["fixture_variant"] = "different"
        manifest["config_sha256"] = _canonical_sha256(config)
    else:
        config["seed"] = 1101
        manifest["seed"] = 1101
        summary["seed"] = 1101
        cross["candidate"]["seed"] = 1101
    _write_json(config_path, config)
    _write_json(manifest_path, manifest)
    _write_json(summary_path, summary)
    _write_json(cross_path, cross)

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    check_name = "same_config_sha256" if mismatch == "config" else "same_seed"
    assert result["pairs"][0]["pair_checks"][check_name]["passed"] is False


def test_online_truth_use_nonzero_fails_closed(tmp_path: Path) -> None:
    pairs = _write_suite(tmp_path)
    summary_path = pairs[1].candidate_episode_dir / "summary.json"
    summary = _read_json(summary_path)
    summary["online_truth_use_count"] = 1
    _write_json(summary_path, summary)

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    assert (
        result["admission_gates"]["online_truth_zero_all_arms"]["passed"]
        is False
    )
    assert (
        result["pairs"][1]["candidate"]["checks"][
            "online_truth_use_zero"
        ]["passed"]
        is False
    )


def test_missing_d1_fusion_stage_is_unavailable_and_fails(
    tmp_path: Path,
) -> None:
    pairs = _write_suite(tmp_path)
    stage_path = pairs[0].candidate_episode_dir / "stage_timings.csv"
    rows = list(csv.DictReader(stage_path.open(newline="", encoding="utf-8")))
    rows = [row for row in rows if row["stage"] != "module.d1_fusion"]
    _write_stage_rows(stage_path, rows)

    result = _evaluate(pairs)

    metric = result["pairs"][0]["candidate"]["metrics"][
        "d1_fusion_wall_s"
    ]
    assert metric["availability"] == "unavailable"
    assert result["d1_optimization_admitted"] is False
    assert (
        result["admission_gates"]["required_metrics_available"]["passed"]
        is False
    )


def test_nonzero_process_exit_fails_closed(tmp_path: Path) -> None:
    pairs = _write_suite(tmp_path)
    path = pairs[2].candidate_resource_path
    text = path.read_text(encoding="utf-8").replace(
        "Exit status: 0", "Exit status: 3"
    )
    path.write_text(text, encoding="utf-8")

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    assert (
        result["admission_gates"]["process_exit_zero_all_arms"]["passed"]
        is False
    )


def test_rss_increase_over_five_percent_fails_gate(
    tmp_path: Path,
) -> None:
    pairs = _write_suite(tmp_path)
    path = pairs[1].candidate_resource_path
    text = path.read_text(encoding="utf-8").replace(
        "Maximum resident set size (kbytes): 100000",
        "Maximum resident set size (kbytes): 130000",
    )
    path.write_text(text, encoding="utf-8")

    result = _evaluate(pairs)

    assert result["d1_optimization_admitted"] is False
    gate = result["admission_gates"]["rss_increase_within_limit"]
    assert gate["passed"] is False


def _evaluate(
    pairs: list[D1CovarianceLimitCleanPairInput],
) -> dict[str, object]:
    return evaluate_d1_covariance_limit_clean_pairs(
        pairs,
        expected_reference_commit=REFERENCE_COMMIT,
        expected_candidate_commit=CANDIDATE_COMMIT,
    )


def _write_suite(
    root: Path,
) -> list[D1CovarianceLimitCleanPairInput]:
    reference_fusion = (4.2, 4.0, 3.9)
    candidate_fusion = (3.6, 3.5, 3.4)
    pairs = []
    for index in range(3):
        round_id = f"r{index + 1}"
        reference = root / f"{round_id}_reference"
        candidate = root / f"{round_id}_candidate"
        reference_resource = root / f"{round_id}_reference_resource.txt"
        candidate_resource = root / f"{round_id}_candidate_resource.txt"
        _write_episode(
            reference,
            commit=REFERENCE_COMMIT,
            fusion_wall_s=reference_fusion[index],
            fusion_p95_ms=185.0 + index,
            core_wall_s=10.6 + index * 0.02,
            real_time_factor=0.207,
        )
        _write_episode(
            candidate,
            commit=CANDIDATE_COMMIT,
            fusion_wall_s=candidate_fusion[index],
            fusion_p95_ms=173.0 + index,
            core_wall_s=10.2 + index * 0.02,
            real_time_factor=0.215,
        )
        _write_resource(
            reference_resource,
            elapsed_s=18.2 + index * 0.1,
            maximum_rss_kib=100_000,
        )
        _write_resource(
            candidate_resource,
            elapsed_s=17.5 + index * 0.1,
            maximum_rss_kib=100_000,
        )
        cross_path = root / f"{round_id}_cross.json"
        _write_cross_build(cross_path, reference, candidate)
        pairs.append(
            D1CovarianceLimitCleanPairInput(
                round_id=round_id,
                reference_episode_dir=reference,
                candidate_episode_dir=candidate,
                cross_build_path=cross_path,
                reference_resource_path=reference_resource,
                candidate_resource_path=candidate_resource,
            )
        )
    return pairs


def _write_episode(
    directory: Path,
    *,
    commit: str,
    fusion_wall_s: float,
    fusion_p95_ms: float,
    core_wall_s: float,
    real_time_factor: float,
) -> None:
    directory.mkdir(parents=True)
    config = {
        "schema_version": "scalable3d-scenario-v1",
        "scenario_name": "fixture_200v200",
        "scenario_version": "fixture-200v200-v1",
        "seed": 1100,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "duration_s": 2.2,
    }
    runtime_profile = {
        "schema_version": "scalable3d-integrated-stack-runtime-profile-v1",
        "module_stack_schema_version": "scalable3d-module-stack-v1",
        "configuration": {"fixture": True},
    }
    manifest = {
        "bus_schema": "scalable3d-episode-bus-v1",
        "config_sha256": _canonical_sha256(config),
        "d1_model_version": "d1-scalable3d-fusion-v1",
        "d2_model_version": "d2-scalable3d-association-v1",
        "d3_policy_version": "d3-scalable3d-rule-cost-v1",
        "d4_policy_version": "d4-region-resource-rule-v1",
        "d5_model_version": "d5-scalable3d-geometry-rule-v1",
        "d7_model_version": "d7-scalable3d-guidance-v1",
        "episode_id": "fixture-200v200-s1100",
        "git_commit": commit,
        "offline_truth_schema": "scalable3d-offline-truth-v2",
        "online_observation_schema": "scalable3d-observation-v1",
        "repository_dirty": False,
        "runtime_profile": runtime_profile,
        "runtime_profile_schema": (
            "scalable3d-integrated-stack-runtime-profile-v1"
        ),
        "runtime_profile_sha256": _canonical_sha256(runtime_profile),
        "scenario_name": "fixture_200v200",
        "scenario_schema": "scalable3d-scenario-v1",
        "scenario_version": "fixture-200v200-v1",
        "seed": 1100,
        "threshold_version": "scalable3d-thresholds-v1",
        "world_schema": "scalable3d-world-v1",
    }
    summary = {
        "episode_id": "fixture-200v200-s1100",
        "scenario_name": "fixture_200v200",
        "scenario_version": "fixture-200v200-v1",
        "seed": 1100,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "simulated_duration_s": 2.2,
        "online_observation_count": 2035,
        "online_truth_use_count": 0,
        "finite_state": True,
        "wall_time_s": core_wall_s,
        "real_time_factor": real_time_factor,
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
    _write_stage_rows(
        directory / "stage_timings.csv",
        [
            _stage_row(
                "module.d1_fusion",
                wall_time_s=fusion_wall_s,
                p95_wall_time_ms=fusion_p95_ms,
            ),
            _stage_row(
                "module.d1_scan_input",
                wall_time_s=1.0,
                p95_wall_time_ms=100.0,
            ),
        ],
    )


def _stage_row(
    stage: str,
    *,
    wall_time_s: float,
    p95_wall_time_ms: float,
) -> dict[str, object]:
    call_count = 89
    mean_ms = wall_time_s * 1000.0 / call_count
    return {
        "schema_version": "scalable3d-stage-timings-v2",
        "stage": stage,
        "call_count": call_count,
        "wall_time_s": wall_time_s,
        "mean_wall_time_ms": mean_ms,
        "p50_wall_time_ms": mean_ms,
        "p95_wall_time_ms": p95_wall_time_ms,
        "max_wall_time_ms": max(p95_wall_time_ms, mean_ms),
        "distribution_available": True,
        "distribution_unavailable_reason": "",
    }


def _write_stage_rows(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=STAGE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _write_resource(
    path: Path,
    *,
    elapsed_s: float,
    maximum_rss_kib: int,
) -> None:
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
) -> None:
    reference_manifest = _read_json(reference_dir / "manifest.json")
    candidate_manifest = _read_json(candidate_dir / "manifest.json")
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
            "reference": _cross_arm(reference_dir, reference_manifest),
            "candidate": _cross_arm(candidate_dir, candidate_manifest),
            "online_bus": {"normalized_online_payloads_equal": True},
        },
    )


def _cross_arm(
    episode_dir: Path,
    manifest: dict[str, object],
) -> dict[str, object]:
    return {
        "duration_s": 2.2,
        "episode_dir": str(episode_dir.resolve()),
        "git_commit": manifest["git_commit"],
        "repository_dirty": False,
        "runtime_profile_sha256": manifest["runtime_profile_sha256"],
        "scenario_version": manifest["scenario_version"],
        "seed": manifest["seed"],
    }


def _canonical_sha256(value: dict[str, object]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value
