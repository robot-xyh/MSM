from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.long_duration_performance import (
    compare_long_duration_episodes,
    load_long_duration_episode,
    render_long_duration_comparison_markdown,
    write_long_duration_comparison_bundle,
)


def _write_episode(
    root: Path,
    *,
    duration: float,
    wall_time: float,
    rss_kb: int,
    elapsed: str,
    git_commit: str = "a" * 40,
    stage_timing_v2: bool = True,
    repository_dirty: bool = False,
) -> Path:
    root.mkdir(parents=True)
    manifest = {
        "episode_id": f"episode-{duration}",
        "git_commit": git_commit,
        "repository_dirty": repository_dirty,
    }
    scenario = {
        "scenario_name": "nominal_200v200",
        "scenario_version": "200v200-nominal-v1",
        "seed": 42000,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 8,
        "duration_s": duration,
        "physics_dt_s": 0.05,
    }
    d1 = {
        "received_scan_count": int(duration * 10),
        "received_observation_count": int(duration * 100),
        "current_buffered_scan_count": 0,
        "current_buffered_observation_count": 0,
        "maximum_buffered_scan_count": 20,
        "maximum_buffered_observation_count": 400,
        "reordered_scan_count": 2,
        "buffer_overflow_scan_count": 0,
        "capacity_overflow_scan_count": 0,
        "too_late_scan_count": 0,
    }
    d2 = {
        "current_count": int(duration * 100),
        "peak_count": int(duration * 100),
        "max_count": 60000,
        "evicted_count": 0,
        "replay_rejection_count": 0,
        "too_old_rejection_count": 0,
        "overflow_rejection_count": 0,
    }
    summary = {
        "episode_id": manifest["episode_id"],
        "scenario_name": scenario["scenario_name"],
        "scenario_version": scenario["scenario_version"],
        "seed": 42000,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 8,
        "simulated_duration_s": duration,
        "wall_time_s": wall_time,
        "real_time_factor": duration / wall_time,
        "finite_state": True,
        "online_truth_use_count": 0,
        "online_observation_count": int(duration * 100),
        "online_batch_count": int(duration * 10),
        "module_publication_count": int(duration * 20),
        "assignment_plan_ack_count": max(1, int(duration)),
        "assignment_plan_control_applied_count": int(duration * 100),
        "assignment_plan_hold_count": 0,
        "intercepted_target_count": 0,
        "module_final_diagnostics": {
            "d1_track_count": 201,
            "d2_track_count": 200,
            "d3_assignment_count": 200,
            "d5_binding_count": 4,
            "d7_command_count": 199,
            "observation_governance": {
                "d1_scan_input": d1,
                "d2_claim_ledger": d2,
            },
        },
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", scenario),
        ("summary.json", summary),
    ):
        (root / name).write_text(json.dumps(payload), encoding="utf-8")
    with (root / "stage_timings.csv").open("w", newline="", encoding="utf-8") as stream:
        timing_fields = [
            "stage",
            "call_count",
            "wall_time_s",
            "mean_wall_time_ms",
        ]
        if stage_timing_v2:
            timing_fields = [
                "schema_version",
                *timing_fields,
                "p50_wall_time_ms",
                "p95_wall_time_ms",
                "max_wall_time_ms",
                "distribution_available",
                "distribution_unavailable_reason",
            ]
        writer = csv.DictWriter(
            stream,
            fieldnames=timing_fields,
        )
        writer.writeheader()
        stage_time = wall_time * 0.5
        rows = [
            {
                "stage": "module.d1_fusion",
                "call_count": int(duration * 10),
                "wall_time_s": stage_time,
                "mean_wall_time_ms": 1000 * stage_time / (duration * 10),
            },
            {
                "stage": "module.d2_association",
                "call_count": int(duration * 5),
                "wall_time_s": wall_time * 0.2,
                "mean_wall_time_ms": 40 * wall_time / duration,
            },
        ]
        for row in rows:
            if stage_timing_v2:
                mean_ms = float(row["mean_wall_time_ms"])
                row.update(
                    {
                        "schema_version": "scalable3d-stage-timings-v2",
                        "p50_wall_time_ms": 0.8 * mean_ms,
                        "p95_wall_time_ms": 1.2 * mean_ms,
                        "max_wall_time_ms": 1.6 * mean_ms,
                        "distribution_available": True,
                        "distribution_unavailable_reason": None,
                    }
                )
            writer.writerow(row)
    with (root / "post_run_timings.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["schema_version", "stage", "wall_time_s"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "schema_version": "scalable3d-post-run-timings-v1",
                "stage": "online_bus_and_identity_views",
                "wall_time_s": duration * 0.2,
            }
        )
        writer.writerow(
            {
                "schema_version": "scalable3d-post-run-timings-v1",
                "stage": "d6_runtime_plan_outcomes",
                "wall_time_s": duration * 0.1,
            }
        )
        writer.writerow(
            {
                "schema_version": "scalable3d-post-run-timings-v1",
                "stage": "total_before_timing_artifact",
                "wall_time_s": duration * 0.3,
            }
        )
    (root / "process_resource_usage.txt").write_text(
        "\n".join(
            [
                f"Elapsed (wall clock) time (h:mm:ss or m:ss): {elapsed}",
                f"Maximum resident set size (kbytes): {rss_kb}",
            ]
        ),
        encoding="utf-8",
    )
    (root / "online_observations.jsonl").write_bytes(
        b"x" * int(duration * duration * 100)
    )
    return root


def test_compare_long_duration_episodes_reports_normalized_growth(tmp_path: Path) -> None:
    short = _write_episode(
        tmp_path / "short", duration=2.0, wall_time=20.0, rss_kb=1_000, elapsed="0:22.00"
    )
    long = _write_episode(
        tmp_path / "long", duration=10.0, wall_time=200.0, rss_kb=4_000, elapsed="3:40.00"
    )

    report = compare_long_duration_episodes(short, long)

    comparison = report["comparison"]
    assert report["schema_version"] == "scalable3d-long-duration-comparison-v2"
    assert comparison["duration_ratio"] == 5.0
    assert comparison["wall_time_ratio"] == 10.0
    assert comparison["normalized_wall_time_growth"] == 2.0
    assert comparison["maximum_rss_ratio"] == 4.0
    assert comparison["normalized_online_log_growth"] == 5.0
    assert comparison["passed_safety_contracts"] is True
    assert "module.d1_fusion" in comparison["superlinear_stage_names"]
    d1 = next(
        item
        for item in comparison["stage_comparisons"]
        if item["stage"] == "module.d1_fusion"
    )
    assert d1["normalized_call_density_growth"] == 1.0
    assert d1["normalized_per_call_cost_growth"] == 2.0
    assert d1["distribution_available"] is True
    assert d1["p50_wall_time_growth"] == 2.0
    assert d1["p95_wall_time_growth"] == 2.0
    assert d1["max_wall_time_growth"] == 2.0
    assert comparison["short_measured_post_run_wall_time_s"] == 0.6
    assert comparison["long_measured_post_run_wall_time_s"] == 3.0
    assert comparison["normalized_measured_post_run_growth"] == 1.0
    assert len(comparison["post_run_stage_comparisons"]) == 2
    assert report["long_episode"]["process_resource_usage"]["elapsed_wall_time_s"] == 220.0


def test_loader_marks_missing_process_usage_unavailable(tmp_path: Path) -> None:
    episode = _write_episode(
        tmp_path / "episode", duration=2.0, wall_time=20.0, rss_kb=1_000, elapsed="22.0"
    )
    (episode / "process_resource_usage.txt").unlink()

    loaded = load_long_duration_episode(episode)

    assert loaded["process_resource_usage"] == {
        "availability": "unavailable",
        "maximum_rss_bytes": None,
        "elapsed_wall_time_s": None,
        "unavailable_reason": "process_resource_usage_missing",
    }


def test_dirty_comparison_is_labeled_development_evidence(tmp_path: Path) -> None:
    short = _write_episode(
        tmp_path / "short",
        duration=2.0,
        wall_time=20.0,
        rss_kb=1_000,
        elapsed="22.0",
        repository_dirty=True,
    )
    long = _write_episode(
        tmp_path / "long",
        duration=10.0,
        wall_time=200.0,
        rss_kb=4_000,
        elapsed="220.0",
        repository_dirty=True,
    )

    report = compare_long_duration_episodes(short, long)
    markdown = render_long_duration_comparison_markdown(report)

    assert report["evidence_class"] == "descriptive_dirty_source_development"
    assert report["comparison"]["acceptance"]["clean_source"] is False
    assert "脏工作树" in markdown


def test_loader_keeps_legacy_stage_timing_distribution_unavailable(
    tmp_path: Path,
) -> None:
    episode = _write_episode(
        tmp_path / "episode",
        duration=2.0,
        wall_time=20.0,
        rss_kb=1_000,
        elapsed="22.0",
        stage_timing_v2=False,
    )

    loaded = load_long_duration_episode(episode)
    timing = loaded["stage_timings"]["module.d1_fusion"]

    assert timing["schema_version"] is None
    assert timing["distribution_available"] is False
    assert timing["p50_wall_time_ms"] is None
    assert timing["p95_wall_time_ms"] is None
    assert timing["max_wall_time_ms"] is None
    assert timing["distribution_unavailable_reason"] is None


def test_loader_keeps_legacy_episode_without_post_run_timings_compatible(
    tmp_path: Path,
) -> None:
    episode = _write_episode(
        tmp_path / "episode", duration=2.0, wall_time=20.0, rss_kb=1_000, elapsed="22.0"
    )
    (episode / "post_run_timings.csv").unlink()

    loaded = load_long_duration_episode(episode)

    assert loaded["post_run_timings"] == {
        "availability": "unavailable",
        "schema_version": None,
        "total_wall_time_s": None,
        "stages": {},
        "unavailable_reason": "post_run_timings_missing",
    }


def test_comparison_rejects_different_source_commit(tmp_path: Path) -> None:
    short = _write_episode(
        tmp_path / "short", duration=2.0, wall_time=20.0, rss_kb=1_000, elapsed="22.0"
    )
    long = _write_episode(
        tmp_path / "long",
        duration=10.0,
        wall_time=200.0,
        rss_kb=4_000,
        elapsed="220.0",
        git_commit="b" * 40,
    )

    with pytest.raises(ValueError, match="git_commit"):
        compare_long_duration_episodes(short, long)


def test_report_bundle_writes_json_and_chinese_markdown(tmp_path: Path) -> None:
    short = _write_episode(
        tmp_path / "short", duration=2.0, wall_time=20.0, rss_kb=1_000, elapsed="22.0"
    )
    long = _write_episode(
        tmp_path / "long", duration=10.0, wall_time=200.0, rss_kb=4_000, elapsed="220.0"
    )
    report = compare_long_duration_episodes(short, long)

    outputs = write_long_duration_comparison_bundle(tmp_path / "report", report)
    markdown = render_long_duration_comparison_markdown(report)

    assert all(path.is_file() for path in outputs.values())
    assert "# 三维长时性能对照" in markdown
    assert "clean-source" in markdown
    assert "已测结束后处理" in markdown
    assert "## 结束后处理耗时" in markdown
    assert "## 阶段单次延时" in markdown
