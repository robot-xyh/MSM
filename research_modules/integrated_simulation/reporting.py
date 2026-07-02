"""Output helpers for integrated offline episodes and batches."""

from __future__ import annotations

from dataclasses import asdict
import csv
import json
from pathlib import Path
from typing import Any, Iterable

from d6_evaluation_metrics import MetricsCollector, ReportGenerator

from .adapters import jsonable_dataclass
from .models import EpisodeResult


def write_episode_outputs(
    result: EpisodeResult,
    collector: MetricsCollector,
    output_dir: Path,
) -> dict[str, Path]:
    """Write JSONL logs, scalar metrics, active-degradation records, and charts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    paths["episode_log"] = write_episode_log_jsonl(result, collector, output_dir / "episode_log.jsonl")
    paths["metrics_json"] = _write_json(
        output_dir / "metrics.json",
        {
            "metrics": result.metrics.to_dict(),
            "metadata": result.metadata,
        },
    )
    paths["active_degradation_json"] = _write_json(
        output_dir / "active_degradation_decisions.json",
        [jsonable_dataclass(decision) for decision in result.decisions],
    )
    paths["active_degradation_csv"] = write_decisions_csv(
        result,
        output_dir / "active_degradation_decisions.csv",
    )
    paths["guidance_json"] = _write_json(
        output_dir / "guidance_summaries.json",
        result.guidance_summaries,
    )
    paths["guidance_csv"] = write_guidance_records_csv(
        result,
        output_dir / "guidance_records.csv",
    )
    report_generator = ReportGenerator()
    paths["episode_metrics_csv"] = report_generator.write_episode_csv(
        [result.metrics],
        output_dir / "episode_metrics.csv",
    )
    paths["summary_csv"] = report_generator.write_summary_csv(
        [result.metrics],
        output_dir / "summary_metrics.csv",
    )
    paths["report_md"] = report_generator.write_markdown_report(
        [result.metrics],
        output_dir / "INTEGRATED_EPISODE_REPORT.md",
        title=f"集成离线评估报告 - {result.scenario.name}",
    )
    for path in report_generator.write_plots([result.metrics], output_dir / "plots"):
        paths[f"plot_{path.stem}"] = path
    return paths


def write_episode_log_jsonl(
    result: EpisodeResult,
    collector: MetricsCollector,
    path: Path,
) -> Path:
    """Write a D6-compatible JSONL log for one integrated episode."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        stream.write(_json_record("truth_summary", result.truth_summary) + "\n")
        for record in collector.track_records:
            stream.write(_json_record("track", asdict(record)) + "\n")
        for record in collector.assignment_records:
            stream.write(_json_record("assignment", asdict(record)) + "\n")
        for record in collector.event_records:
            stream.write(_json_record("event", asdict(record)) + "\n")
        for record in collector.terminal_records:
            stream.write(_json_record("terminal", asdict(record)) + "\n")
    return path


def write_batch_outputs(
    results: Iterable[EpisodeResult],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_list = list(results)
    metrics = [result.metrics for result in result_list]
    report_generator = ReportGenerator()
    paths: dict[str, Path] = {}
    paths["episode_metrics_csv"] = report_generator.write_episode_csv(
        metrics,
        output_dir / "episode_metrics.csv",
    )
    paths["summary_csv"] = report_generator.write_summary_csv(
        metrics,
        output_dir / "summary_metrics.csv",
    )
    paths["report_md"] = report_generator.write_markdown_report(
        metrics,
        output_dir / "INTEGRATED_BATCH_REPORT.md",
        title="集成离线批量评估报告",
    )
    paths["scenario_summary_json"] = _write_json(
        output_dir / "scenario_summary.json",
        [
            {
                "scenario": result.scenario.name,
                "seed": result.scenario.seed,
                "metrics": result.metrics.to_dict(),
                "decision_count": len(result.decisions),
                "guidance_summary_count": len(result.guidance_summaries),
                "guidance_summaries": result.guidance_summaries,
                "active_or_passive_decisions": [
                    jsonable_dataclass(decision)
                    for decision in result.decisions
                    if decision.action != "continue_center"
                ],
            }
            for result in result_list
        ],
    )
    for path in report_generator.write_plots(metrics, output_dir / "plots"):
        paths[f"plot_{path.stem}"] = path
    return paths


def write_decisions_csv(result: EpisodeResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "timestamp",
        "resource_id",
        "global_track_id",
        "mode",
        "action",
        "reason",
        "target_node_id",
        "terminal_consistent",
        "risk_factors",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for decision in result.decisions:
            row = jsonable_dataclass(decision)
            row["risk_factors"] = ";".join(decision.risk_factors)
            writer.writerow(row)
    return path


def write_guidance_records_csv(result: EpisodeResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "timestamp_s",
        "resource_id",
        "target_id",
        "mode",
        "range_m",
        "los_angle_rad",
        "los_rate_radps",
        "closing_speed_mps",
        "commanded_lateral_accel_mps2",
        "limited_lateral_accel_mps2",
        "limited_turn_rate_radps",
        "mode_switch",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in result.guidance_records:
            writer.writerow(record.as_dict())
    return path


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _json_record(record_type: str, payload: Any) -> str:
    return json.dumps(
        {"record_type": record_type, "payload": _jsonable(payload)},
        ensure_ascii=False,
        sort_keys=True,
    )


def _jsonable(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
