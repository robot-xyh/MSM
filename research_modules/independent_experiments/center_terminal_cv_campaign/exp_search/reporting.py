"""Structured outputs, figures, and Chinese report for the search experiment."""

from __future__ import annotations

from dataclasses import asdict
import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import warnings

import matplotlib

matplotlib.use("Agg", force=True)
from matplotlib import font_manager
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
    import matplotlib.pyplot as plt

from center_terminal_cv_campaign.common.io import write_json, write_jsonl

from .runtime import SearchExperimentResult


def _configure_font() -> None:
    candidates = (
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "WenQuanYi Micro Hei",
        "Microsoft YaHei",
        "SimHei",
        "DejaVu Sans",
    )
    installed = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in candidates:
        if candidate in installed:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    plt.rcParams["axes.unicode_minus"] = False


def _assignment_row(value: Any) -> dict[str, Any]:
    row = asdict(value)
    utility = row.pop("utility")
    return row | {f"utility_{key}": item for key, item in utility.items()}


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return path
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_metrics_csv(path: Path, metrics: Mapping[str, Any]) -> Path:
    row = {
        key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
        for key, value in metrics.items()
    }
    return _write_csv(path, [row])


def _coverage_figure(result: SearchExperimentResult, path: Path) -> Path:
    _configure_font()
    x_values = [cell.center_ned_m[0] for cell in result.cells]
    y_values = [cell.center_ned_m[1] for cell in result.cells]
    counts = [result.coverage_counts.get(cell.search_cell_id, 0) for cell in result.cells]
    kinds = [cell.cell_kind for cell in result.cells]
    figure, axis = plt.subplots(figsize=(9.0, 5.4))
    scatter = axis.scatter(
        x_values,
        y_values,
        c=counts,
        s=[90 if kind == "source_directed" else 130 for kind in kinds],
        marker="o",
        cmap="viridis",
        vmin=0,
        edgecolors=["#183153" if kind == "source_directed" else "#a23b2a" for kind in kinds],
        linewidths=1.1,
    )
    axis.set_title("搜索单元覆盖")
    axis.set_xlabel("北向位置（米）")
    axis.set_ylabel("东向位置（米）")
    axis.grid(alpha=0.25)
    colorbar = figure.colorbar(scatter, ax=axis)
    colorbar.set_label("执行次数")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def _first_discovery_figure(result: SearchExperimentResult, path: Path) -> Path:
    _configure_font()
    target_ids = [target.truth_target_id for target in result.targets]
    fallback = (
        result.config.assignment_cycles
        * result.config.frames_per_assignment
        * result.config.frame_interval_s
    )
    times = [result.first_discovery_by_target_s.get(target_id, fallback) for target_id in target_ids]
    colors = [
        "#2f6f4e" if target_id in result.first_discovery_by_target_s else "#b9bec5"
        for target_id in target_ids
    ]
    figure, axis = plt.subplots(figsize=(10.0, 5.2))
    axis.bar(range(len(target_ids)), times, color=colors)
    axis.set_title("目标首次发现时间")
    axis.set_xlabel("离线评分目标序号")
    axis.set_ylabel("时间（秒）")
    axis.set_xticks(range(len(target_ids)))
    axis.set_xticklabels([str(index + 1) for index in range(len(target_ids))], rotation=0)
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def _report_text(result: SearchExperimentResult) -> str:
    metrics = result.metrics
    source = (
        "AirSim ComputerVision 接口"
        if metrics.get("data_source") == "airsim_computervision"
        else "离线几何假客户端"
    )
    return f"""# 中心线索条件下的多机区域搜索试验

## 结论

本轮使用{source}验证搜索接口。输入包含 {metrics['target_count']} 个目标、{metrics['source_cue_count']} 条中心线索和 {metrics['resource_count']} 个相机节点。中心线索精度与召回率分别为 {metrics['source_fixture_precision']:.0%} 和 {metrics['source_fixture_recall']:.0%}。

搜索共覆盖 {metrics['covered_cell_count']}/{metrics['search_cell_count']} 个单元，至少检测到 {metrics['detected_target_count']} 个目标，其中 {metrics['recognized_target_count']} 个达到10像素门限，最终有 {metrics['discovered_target_count']}/{metrics['target_count']} 个形成连续确认。中心未提供正确线索的目标共 {metrics['center_missed_target_count']} 个，其中补获 {metrics['center_missed_recovered_count']} 个。中心漏检目标补获率只统计该子集，不能代替全体目标发现率。该结果只说明当前固定场景和输入夹具下的接口表现，不代表真实装备探测率。

## 方法

每条中心线索外推为一个指向性搜索单元。搜索走廊另行划分不绑定源航迹的空档单元，用于寻找中心漏检目标。滚动分配同时计算目标概率、预计探测收益、相机转向、到达距离和重复覆盖，再通过匈牙利算法形成资源与单元的一一对应关系。

ComputerVision 节点移动到分配单元前方并朝向单元中心。每次分配连续观察 {result.config.frames_per_assignment} 帧，检测输入来自 `simGetDetections` 的检测框。检测框最长边达到10像素后才进入识别确认，连续两帧满足条件后才生成交接记录；非连续帧仍不确认。AirSim对象名称在读取检测框后立即转入离线评分映射，在线记录不保留对象名称和真实目标编号。

## 结果

| 指标 | 数值 |
| --- | ---: |
| 搜索单元覆盖率 | {metrics['cell_coverage_rate']:.3f} |
| 未调度搜索单元数 | {metrics['unassigned_cell_count']} |
| 达到门限但未连续确认目标数 | {metrics['recognized_but_unconfirmed_target_count']} |
| 正确源单元已调度但未确认目标数 | {metrics['scheduled_source_but_unconfirmed_target_count']} |
| 从未检测目标数 | {metrics['never_detected_target_count']} |
| 目标发现率 | {metrics['target_discovery_recall']:.3f} |
| 中心漏检目标补获率 | {metrics['center_missed_recovery_recall']:.3f} |
| 已确认交接精度 | {metrics['confirmed_handover_precision']:.3f} |
| 鬼线索形成确认目标数 | {metrics['ghost_source_confirmed_count']} |
| 在线真实身份泄漏数 | {metrics['online_truth_leakage_count']} |
| 平均分配计算时间 | {metrics['planner_compute_mean_ms']:.3f} 毫秒 |

![搜索单元覆盖](figures/search_cell_coverage.png)

![首次发现时间](figures/first_discovery_time.png)

## 证据边界

离线模式用于检查合同、匿名化、分配和评分流程。只有 `data_source=airsim_computervision` 的结果才能作为真实Blocks接口证据。真实AirSim运行仍由main统一启动、重置和收集日志；本实验适配器不启动、重置或关闭Blocks，也不控制目标Actor。
"""


def write_experiment_outputs(result: SearchExperimentResult, output_dir: Path) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "metrics_json": write_json(output_dir / "metrics.json", dict(result.metrics)),
        "metrics_csv": _write_metrics_csv(output_dir / "metrics.csv", result.metrics),
        "online_detections": write_jsonl(
            output_dir / "online_detections.jsonl",
            (record.to_online_dict() for record in result.online_detections),
        ),
        "assignments_jsonl": write_jsonl(
            output_dir / "search_assignments.jsonl",
            (_assignment_row(value) for value in result.assignments),
        ),
        "assignments_csv": _write_csv(
            output_dir / "search_assignments.csv",
            [_assignment_row(value) for value in result.assignments],
        ),
        "handovers": write_jsonl(output_dir / "handover_records.jsonl", result.handover_records),
        "source_truth": write_jsonl(
            output_dir / "truth" / "source_truth_labels.jsonl",
            result.source_truth_labels,
        ),
        "detection_truth": write_jsonl(
            output_dir / "truth" / "detection_truth_labels.jsonl",
            result.offline_detection_labels,
        ),
        "target_truth": write_json(
            output_dir / "truth" / "targets.json",
            {"offline_truth_only": True, "targets": [asdict(value) for value in result.targets]},
        ),
        "truth_scoring": write_json(
            output_dir / "truth" / "scoring.json",
            {
                "offline_truth_only": True,
                "first_discovery_by_target_s": dict(result.first_discovery_by_target_s),
                "target_diagnostics": dict(result.offline_target_diagnostics),
                "metrics": dict(result.metrics),
            },
        ),
        "scenario": write_json(
            output_dir / "scenario.json",
            {
                "schema_version": "center-terminal-search-scenario-v1",
                "fixture_source": result.fixture_source,
                "config": asdict(result.config),
                "online_truth_separated": True,
            },
        ),
        "probability_regions": write_json(
            output_dir / "probability_regions.json",
            [asdict(value) for value in result.regions],
        ),
        "search_cells": write_json(
            output_dir / "search_cells.json",
            [asdict(value) for value in result.cells],
        ),
        "coverage_figure": _coverage_figure(
            result, output_dir / "figures" / "search_cell_coverage.png"
        ),
        "first_discovery_figure": _first_discovery_figure(
            result, output_dir / "figures" / "first_discovery_time.png"
        ),
    }
    report_path = output_dir / "REPORT_CN.md"
    report_path.write_text(_report_text(result), encoding="utf-8")
    paths["report"] = report_path
    return paths
