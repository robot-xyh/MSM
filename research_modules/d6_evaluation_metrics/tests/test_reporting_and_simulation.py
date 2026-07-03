from __future__ import annotations

from pathlib import Path

from d6_evaluation_metrics import ReportGenerator
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
            active_degradation_count=0,
            mode_switch_count=1,
        ),
        EpisodeMetrics(
            episode_id="secondary_001",
            seed=12,
            batch_seed=102,
            scenario_group="secondary_200m",
            active_degradation_count=2,
            passive_failover_count=1,
            mode_switch_count=3,
            terminal_contract_reject_count=1,
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

    episode_text = episode_csv.read_text(encoding="utf-8")
    summary_text = summary_csv.read_text(encoding="utf-8")
    report_text = markdown.read_text(encoding="utf-8")

    assert "scenario_group" in episode_text
    assert "batch_seed" in episode_text
    assert "normal" in summary_text
    assert "secondary_200m" in summary_text
    assert "场景分组" in report_text
    assert "terminal_contract_reject_count" in report_text


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
