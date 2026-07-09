from __future__ import annotations

import csv
from pathlib import Path

from d6_evaluation_metrics import ReportGenerator, STANDARD_MAPPING_VERSION
from d6_evaluation_metrics.metrics import EpisodeMetrics
from d6_evaluation_metrics.simulation import (
    generate_synthetic_episode,
    write_episode_log_jsonl,
)


def test_report_generator_writes_tables_and_charts(tmp_path: Path) -> None:
    episodes = []
    for seed in range(3):
        collector, truth_summary = generate_synthetic_episode(
            seed=seed,
            duration=12.0,
        )
        episodes.append(
            collector.compute_episode(
                episode_id=f"synthetic_{seed}",
                seed=seed,
                duration=12.0,
                truth_summary=truth_summary,
            )
        )

    report_generator = ReportGenerator()
    episode_csv = report_generator.write_episode_csv(
        episodes,
        tmp_path / "episode_metrics.csv",
    )
    summary_csv = report_generator.write_summary_csv(
        episodes,
        tmp_path / "summary_metrics.csv",
    )
    markdown = report_generator.write_markdown_report(
        episodes,
        tmp_path / "report.md",
    )
    plots = report_generator.write_plots(episodes, tmp_path / "plots")

    assert episode_csv.exists()
    assert summary_csv.exists()
    assert markdown.exists()
    assert "detection_probability" in summary_csv.read_text(encoding="utf-8")
    report_text = markdown.read_text(encoding="utf-8")
    assert "离线记录" in report_text
    assert "图表与曲线" in report_text
    assert len(plots) >= 2
    assert all(path.exists() and path.stat().st_size > 0 for path in plots)


def test_report_generator_writes_scenario_grouped_summary(tmp_path: Path) -> None:
    episodes = [
        EpisodeMetrics(
            episode_id="normal_001",
            seed=11,
            batch_seed=101,
            scenario_group="normal",
            metric_scope="execution",
            drone_count=2,
            resource_count=2,
            target_count=2,
            camera_count=2,
            mission_outcome="partial",
            success_reason="terminal_lock_count=1",
            failure_reason="tracking: id_switch_count=1",
            eval_priority="P0-A",
            implementation_status="implemented",
            evidence_path="outputs/normal_001/main_episode_bus_metrics.json",
            scenario_version="scenario-v2",
            standard_mapping_version=STANDARD_MAPPING_VERSION,
            standard_metric_family_summary="mission/root cause=7; detection=3",
            active_degradation_count=0,
            mode_switch_count=1,
            secondary_network_joint_full_view_frame_rate=0.5,
            secondary_network_mean_coverage_ratio=0.75,
            secondary_single_camera_full_view_frame_rate=0.25,
            cross_view_association_count=2,
            secondary_detect_available_but_not_registered_count=1,
            cue_pointing_error_mean_deg=3.0,
            gimbal_pointing_error_mean_deg=1.5,
            module_duration_ms=12.0,
            loop_latency_ms=20.0,
            record_latency_ms=3.0,
            cpu_budget_utilization=0.5,
            gpu_budget_utilization=0.1,
            performance_budget_violation_count=1,
            metadata={
                "root_cause": "tracking",
                "top_failure_causes": [
                    {"cause": "tracking", "score": 1.0, "details": ["id_switch_count=1"]}
                ],
                "terminal_switch_reject_reasons": {"camera_quality": 1},
                "secondary_sensing_node_type_metrics": {
                    "fixed_downlook_secondary": {
                        "secondary_network_joint_full_view_frame_rate": 0.4,
                        "secondary_network_mean_coverage_ratio": 0.7,
                        "secondary_single_camera_full_view_frame_rate": 0.2,
                        "cross_view_association_count": 1,
                        "secondary_detect_available_but_not_registered_count": 1,
                        "cue_pointing_error_mean_deg": 0.0,
                        "gimbal_pointing_error_mean_deg": 0.0,
                    },
                    "mobile_recon_gimbal": {
                        "secondary_network_joint_full_view_frame_rate": 0.6,
                        "secondary_network_mean_coverage_ratio": 0.8,
                        "secondary_single_camera_full_view_frame_rate": 0.3,
                        "cross_view_association_count": 1,
                        "secondary_detect_available_but_not_registered_count": 0,
                        "cue_pointing_error_mean_deg": 3.0,
                        "gimbal_pointing_error_mean_deg": 1.5,
                    },
                },
            },
        ),
        EpisodeMetrics(
            episode_id="secondary_001",
            seed=12,
            batch_seed=102,
            scenario_group="secondary_200m",
            metric_scope="contract",
            drone_count=5,
            resource_count=5,
            target_count=5,
            camera_count=5,
            active_degradation_count=2,
            passive_failover_count=1,
            mode_switch_count=3,
            terminal_contract_reject_count=1,
            metadata={
                "terminal_contract_reject_reasons": {
                    "terminal_contract_not_satisfied": 2
                },
            },
        ),
    ]

    report_generator = ReportGenerator()
    episode_csv = report_generator.write_episode_csv(
        episodes,
        tmp_path / "episode_metrics.csv",
    )
    summary_csv = report_generator.write_summary_csv(
        episodes,
        tmp_path / "summary_metrics.csv",
    )
    markdown = report_generator.write_markdown_report(
        episodes,
        tmp_path / "report.md",
    )
    standard_mapping_csv = report_generator.write_standard_mapping_csv(
        tmp_path / "standard_metric_mapping.csv",
    )

    episode_text = episode_csv.read_text(encoding="utf-8")
    summary_text = summary_csv.read_text(encoding="utf-8")
    report_text = markdown.read_text(encoding="utf-8")

    assert "scenario_group" in episode_text
    assert "batch_seed" in episode_text
    assert "metric_scope" in episode_text
    assert "mission_outcome" in episode_text
    assert "success_reason" in episode_text
    assert "failure_reason" in episode_text
    assert "eval_priority" in episode_text
    assert "implementation_status" in episode_text
    assert "evidence_path" in episode_text
    assert "scenario_version" in episode_text
    assert "standard_mapping_version" in episode_text
    assert "standard_metric_family_summary" in episode_text
    assert "scenario-v2" in episode_text
    assert STANDARD_MAPPING_VERSION in episode_text
    assert "metadata" in episode_text
    assert "terminal_switch_reject_reasons" in episode_text
    assert "secondary_network_joint_full_view_frame_rate" in episode_text
    assert "drone_count" in episode_text
    assert "resource_count" in episode_text
    assert "target_count" in episode_text
    assert "camera_count" in episode_text
    assert "metric_scope" in summary_text
    assert "seed" in summary_text
    assert "drone_count" in summary_text
    assert "secondary_network_mean_coverage_ratio" in summary_text
    assert "module_duration_ms" in summary_text
    assert "performance_budget_violation_count" in summary_text
    assert "normal" in summary_text
    assert "secondary_200m" in summary_text
    assert "场景分组" in report_text
    assert "Metrics scope" in report_text
    assert "execution" in report_text
    assert "contract" in report_text
    assert "Drone count" in report_text
    assert "active_degradation_precision" in report_text
    assert "terminal_contract_reject_count" in report_text
    assert "Mission Outcome / Root Cause" in report_text
    assert "Performance Monitoring" in report_text
    assert "EVAL Tracking" in report_text
    assert "Standard C-UAS Mapping" in report_text
    assert STANDARD_MAPPING_VERSION in report_text
    assert "COURAGEOUS" in report_text
    assert "mission_outcome" in report_text
    assert "reproducibility/evidence" in report_text
    assert "outputs/normal_001/main_episode_bus_metrics.json" in report_text
    assert "performance_metrics.png" in report_text
    assert "二级视角节点对比" in report_text
    assert "fixed_downlook_secondary" in report_text
    assert "mobile_recon_gimbal" in report_text
    assert "secondary_sensing_metrics.png" in report_text
    assert "Reject reason 分布" in report_text
    assert "camera_quality" in report_text
    assert "terminal_contract_not_satisfied" in report_text

    assert standard_mapping_csv.exists()
    mapping_rows = list(csv.DictReader(standard_mapping_csv.open(encoding="utf-8")))
    assert mapping_rows
    assert set(mapping_rows[0]) == {
        "engineering_metric",
        "standard_metric_family",
        "standard_sources",
        "implementation_status",
        "evidence_requirement",
    }
    assert any(
        row["engineering_metric"] == "mission_outcome"
        and row["standard_metric_family"] == "mission/root cause"
        and "COURAGEOUS" in row["standard_sources"]
        for row in mapping_rows
    )
    assert any(
        row["engineering_metric"] == "standard_mapping_version"
        and row["standard_metric_family"] == "reproducibility/evidence"
        and row["implementation_status"] == "implemented"
        for row in mapping_rows
    )

    summary_rows = list(csv.DictReader(summary_csv.open(encoding="utf-8")))
    active_rows = [
        row for row in summary_rows if row["metric"] == "active_degradation_count"
    ]
    assert any(
        row["metric_scope"] == "execution"
        and row["seed"] == "11"
        and row["scenario_group"] == "normal"
        and row["drone_count"] == "2"
        for row in active_rows
    )
    assert any(
        row["metric_scope"] == "contract"
        and row["seed"] == "12"
        and row["scenario_group"] == "secondary_200m"
        and row["drone_count"] == "5"
        for row in active_rows
    )


def test_synthetic_log_writer_outputs_jsonl(tmp_path: Path) -> None:
    collector, truth_summary = generate_synthetic_episode(seed=7, duration=8.0)
    path = write_episode_log_jsonl(
        collector=collector,
        truth_summary=truth_summary,
        path=tmp_path / "episode.jsonl",
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines
    assert '"record_type": "truth_summary"' in lines[0]
    assert any('"record_type": "track"' in line for line in lines)
