#!/usr/bin/env python3
"""Run the 45-case perfect-cue offline cooperative-search matrix."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence
import warnings

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

from .offline_replay import (
    OfflineSearchConfig,
    OfflineSearchResult,
    cell_center_at,
    run_offline_search,
    write_offline_search_result,
)


CAMPAIGN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = CAMPAIGN_ROOT / "outputs" / "offline_search_100pct_cues_20260819"
DEFAULT_SEEDS = (20260816, 20260817, 20260818, 20260819, 20260820)
SIGMAS_M = (30.0, 60.0, 100.0)
SCENARIOS = (
    {
        "scenario_id": "n20_m8",
        "label": "20目标/8机",
        "target_count": 20,
        "resource_count": 8,
        "trajectory_path": CAMPAIGN_ROOT
        / "outputs"
        / "airsim_n20_formal_v3_20260816"
        / "search"
        / "truth"
        / "actor_motion.jsonl",
    },
    {
        "scenario_id": "n20_m30",
        "label": "20目标/30机",
        "target_count": 20,
        "resource_count": 30,
        "trajectory_path": CAMPAIGN_ROOT
        / "outputs"
        / "airsim_m30_n20_scale_20260816"
        / "search"
        / "truth"
        / "actor_motion.jsonl",
    },
    {
        "scenario_id": "n40_m50",
        "label": "40目标/50机",
        "target_count": 40,
        "resource_count": 50,
        "trajectory_path": CAMPAIGN_ROOT
        / "outputs"
        / "airsim_m50_n40_scale_v2_20260816"
        / "search"
        / "truth"
        / "actor_motion.jsonl",
    },
)


def _configure_plotting() -> None:
    installed = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in (
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "WenQuanYi Micro Hei",
        "Microsoft YaHei",
        "SimHei",
        "DejaVu Sans",
    ):
        if candidate in installed:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    plt.rcParams["axes.unicode_minus"] = False


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


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


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return float(np.mean(values)) if values else math.nan


def _minimum(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return float(np.min(values)) if values else math.nan


def _maximum(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return float(np.max(values)) if values else math.nan


def aggregate_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, float], list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["scenario_id"]), float(row["position_sigma_m"])), []).append(row)
    result: list[dict[str, Any]] = []
    for (scenario_id, sigma), values in sorted(grouped.items()):
        result.append(
            {
                "scenario_id": scenario_id,
                "scenario_label": values[0]["scenario_label"],
                "target_count": values[0]["target_count"],
                "resource_count": values[0]["resource_count"],
                "position_sigma_m": sigma,
                "seed_count": len(values),
                "target_discovery_rate_mean": _mean(values, "target_discovery_rate"),
                "target_discovery_rate_min": _minimum(values, "target_discovery_rate"),
                "continuous_confirmation_rate_mean": _mean(values, "continuous_confirmation_rate"),
                "continuous_confirmation_rate_min": _minimum(values, "continuous_confirmation_rate"),
                "true_frustum_probability_mass_coverage_rate_mean": _mean(
                    values, "true_frustum_probability_mass_coverage_rate"
                ),
                "true_frustum_probability_mass_coverage_rate_min": _minimum(
                    values, "true_frustum_probability_mass_coverage_rate"
                ),
                "first_discovery_mean_s": _mean(values, "first_discovery_mean_s"),
                "first_discovery_p95_s_max": _maximum(values, "first_discovery_p95_s"),
                "repeated_confirmed_observation_rate_mean": _mean(
                    values, "repeated_confirmed_observation_rate"
                ),
                "unexecuted_task_count_mean": _mean(values, "unexecuted_task_count"),
                "unexecuted_task_count_max": _maximum(values, "unexecuted_task_count"),
                "identity_misclosed_cue_count_mean": _mean(
                    values, "identity_misclosed_cue_count"
                ),
                "planner_compute_p95_ms_mean": _mean(values, "planner_compute_p95_ms"),
                "planner_compute_max_ms_max": _maximum(values, "planner_compute_max_ms"),
                "online_truth_leakage_count": int(
                    sum(int(value["online_truth_leakage_count"]) for value in values)
                ),
            }
        )
    return result


def _build_flow_figure(path: Path) -> None:
    _configure_plotting()
    fig, axis = plt.subplots(figsize=(15.5, 5.4))
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")
    labels = (
        "保存的AirSim\n目标运动轨迹",
        "每目标一条正确线索\n注入30/60/100米误差",
        "3σ区域按真实视场\n划分重叠子单元",
        "收益矩阵与\n匈牙利一一分配",
        "97米/秒飞行\n200度/秒转向",
        "真实视锥与10像素\n连续两帧确认",
        "离线真值评分\n不进入在线分配",
    )
    colors = ("#dce8ef", "#e9e3cf", "#e5eddf", "#dfe8f0", "#eee0d9", "#e4ece6", "#e6e2ed")
    centers = np.linspace(0.075, 0.925, len(labels))
    for center, label, color in zip(centers, labels, colors, strict=True):
        axis.add_patch(
            plt.Rectangle(
                (center - 0.06, 0.35),
                0.12,
                0.30,
                facecolor=color,
                edgecolor="#3f4b54",
                linewidth=1.1,
            )
        )
        axis.text(center, 0.50, label, ha="center", va="center", fontsize=10.5)
    for left, right in zip(centers[:-1], centers[1:], strict=True):
        axis.annotate(
            "",
            xy=(right - 0.064, 0.50),
            xytext=(left + 0.064, 0.50),
            arrowprops={"arrowstyle": "->", "color": "#51606a", "lw": 1.4},
        )
    axis.set_title("中心粗线索条件下的离线协同搜索流程", fontsize=16, pad=12)
    fig.savefig(path, dpi=210, bbox_inches="tight", pad_inches=0.16)
    plt.close(fig)


def _build_cell_figure(result: OfflineSearchResult, path: Path) -> None:
    _configure_plotting()
    label = result.cue_labels[0]
    cue = next(value for value in result.source_cues if value.source_track_id == label.source_track_id)
    cells = [value for value in result.cells if value.source_track_id == cue.source_track_id]
    fig, axes = plt.subplots(1, 2, figsize=(13.8, 6.2))
    weights = np.asarray([value.probability_mass for value in cells])
    points = np.asarray([cell_center_at(value, cue, 0.0) for value in cells])
    cue_point = np.asarray(cue.position_ned_m)
    truth_error = np.asarray(label.injected_error_ned_m)
    truth_point = cue_point - truth_error

    left = axes[0]
    scatter = left.scatter(
        points[:, 1],
        -points[:, 2],
        c=weights,
        cmap="YlOrRd",
        s=70 + 700 * weights,
        edgecolors="#66331f",
        linewidths=0.5,
    )
    left.scatter(cue_point[1], -cue_point[2], marker="x", s=120, color="#1f5e8c", label="中心线索均值")
    left.scatter(truth_point[1], -truth_point[2], marker="*", s=180, color="#28784c", label="离线真值位置")
    left.plot(
        (cue_point[1], truth_point[1]),
        (-cue_point[2], -truth_point[2]),
        linestyle="--",
        color="#56616a",
        linewidth=1.2,
    )
    left.set_xlabel("东向（米）")
    left.set_ylabel("高度（米）")
    left.set_title("相机横向与高度方向划分")
    left.grid(alpha=0.22)
    left.legend(loc="upper left")

    right = axes[1]
    relative = points - cue_point
    projected_x = 0.010 * relative[:, 1] - 0.004 * relative[:, 0]
    projected_y = 0.008 * (-relative[:, 2]) + 0.0025 * relative[:, 0]
    right.scatter(
        projected_x,
        projected_y,
        c=weights,
        cmap="YlOrRd",
        s=70 + 700 * weights,
        edgecolors="#66331f",
        linewidths=0.5,
    )
    truth_relative = truth_point - cue_point
    truth_projected = (
        0.010 * truth_relative[1] - 0.004 * truth_relative[0],
        0.008 * (-truth_relative[2]) + 0.0025 * truth_relative[0],
    )
    right.scatter(0.0, 0.0, marker="x", s=120, color="#1f5e8c")
    right.scatter(*truth_projected, marker="*", s=180, color="#28784c")
    right.plot((0.0, truth_projected[0]), (0.0, truth_projected[1]), linestyle="--", color="#56616a")
    right.annotate("北向深度范围±3σ", xy=(0.02, 0.07), xycoords="axes fraction", fontsize=10, color="#48545d")
    right.set_title("三维搜索区域的透视示意")
    right.set_aspect("equal", adjustable="datalim")
    right.axis("off")
    colorbar = fig.colorbar(scatter, ax=axes, shrink=0.78, pad=0.04)
    colorbar.set_label("子单元高斯概率质量")
    fig.suptitle(f"{result.config.position_sigma_m:.0f}米误差档的3σ搜索子单元")
    fig.savefig(path, dpi=210, bbox_inches="tight", pad_inches=0.14)
    plt.close(fig)


def _grouped_values(
    aggregates: Sequence[Mapping[str, Any]], key: str
) -> tuple[list[str], dict[float, list[float]]]:
    labels = [str(item["label"]) for item in SCENARIOS]
    by_sigma: dict[float, list[float]] = {}
    for sigma in SIGMAS_M:
        by_sigma[sigma] = [
            float(
                next(
                    row[key]
                    for row in aggregates
                    if row["scenario_id"] == scenario["scenario_id"]
                    and float(row["position_sigma_m"]) == sigma
                )
            )
            for scenario in SCENARIOS
        ]
    return labels, by_sigma


def _build_result_figure(aggregates: Sequence[Mapping[str, Any]], path: Path) -> None:
    _configure_plotting()
    labels, discovery = _grouped_values(aggregates, "target_discovery_rate_mean")
    _, confirmation = _grouped_values(aggregates, "continuous_confirmation_rate_mean")
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 5.6), sharey=True)
    x = np.arange(len(labels), dtype=float)
    width = 0.23
    colors = ("#4477a7", "#4d8b62", "#bc7a3a")
    for axis, values, title in (
        (axes[0], discovery, "目标至少被发现一次"),
        (axes[1], confirmation, "目标连续两帧确认"),
    ):
        for offset, (sigma, color) in enumerate(zip(SIGMAS_M, colors, strict=True)):
            axis.bar(x + (offset - 1) * width, values[sigma], width, color=color, label=f"σ={sigma:.0f}米")
        axis.set_xticks(x, labels)
        axis.set_ylim(0.0, 1.05)
        axis.set_ylabel("五个误差种子的平均比例")
        axis.set_title(title)
        axis.grid(axis="y", alpha=0.25)
    axes[1].legend(loc="lower right")
    fig.suptitle("中心线索误差与搜索确认结果")
    fig.tight_layout()
    fig.savefig(path, dpi=210, bbox_inches="tight")
    plt.close(fig)


def _build_coverage_figure(aggregates: Sequence[Mapping[str, Any]], path: Path) -> None:
    _configure_plotting()
    labels, coverage = _grouped_values(
        aggregates, "true_frustum_probability_mass_coverage_rate_mean"
    )
    _, unexecuted = _grouped_values(aggregates, "unexecuted_task_count_mean")
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 5.6))
    colors = ("#4477a7", "#4d8b62", "#bc7a3a")
    x = np.arange(len(labels), dtype=float)
    for sigma, color in zip(SIGMAS_M, colors, strict=True):
        axes[0].plot(x, coverage[sigma], marker="o", linewidth=2.0, color=color, label=f"σ={sigma:.0f}米")
        axes[1].plot(x, unexecuted[sigma], marker="s", linewidth=2.0, color=color, label=f"σ={sigma:.0f}米")
    axes[0].set_ylim(0.0, 1.05)
    axes[0].set_ylabel("实际视锥覆盖的概率质量")
    axes[0].set_title("真实视锥覆盖")
    axes[1].set_ylabel("18秒内未执行子单元数")
    axes[1].set_title("预算结束后的剩余任务")
    for axis in axes:
        axis.set_xticks(x, labels)
        axis.grid(alpha=0.25)
    axes[1].legend(loc="upper left")
    fig.suptitle("空间覆盖与时间预算")
    fig.tight_layout()
    fig.savefig(path, dpi=210, bbox_inches="tight")
    plt.close(fig)


def _build_timing_figure(aggregates: Sequence[Mapping[str, Any]], path: Path) -> None:
    _configure_plotting()
    labels, discovery_time = _grouped_values(aggregates, "first_discovery_mean_s")
    _, planner = _grouped_values(aggregates, "planner_compute_p95_ms_mean")
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 5.6))
    colors = ("#4477a7", "#4d8b62", "#bc7a3a")
    x = np.arange(len(labels), dtype=float)
    for sigma, color in zip(SIGMAS_M, colors, strict=True):
        axes[0].plot(x, discovery_time[sigma], marker="o", linewidth=2.0, color=color, label=f"σ={sigma:.0f}米")
        axes[1].plot(x, planner[sigma], marker="s", linewidth=2.0, color=color, label=f"σ={sigma:.0f}米")
    axes[0].set_ylabel("首次发现平均时间（秒）")
    axes[0].set_title("首次发现时间")
    axes[1].set_ylabel("单次规划95%耗时（毫秒）")
    axes[1].set_title("滚动分配计算时间")
    for axis in axes:
        axis.set_xticks(x, labels)
        axis.grid(alpha=0.25)
    axes[1].legend(loc="upper left")
    fig.suptitle("搜索时效与规划计算")
    fig.tight_layout()
    fig.savefig(path, dpi=210, bbox_inches="tight")
    plt.close(fig)


def _build_technical_report(summary: Mapping[str, Any]) -> str:
    lines = [
        "# 中心线索100%正确条件下的协同搜索离线矩阵",
        "",
        "本轮没有重新启动AirSim。目标运动取自既有AirSim Actor记录，记录末端以后按保存速度外推到18秒；五个seed只改变中心粗位置误差，不代表五次独立AirSim飞行。",
        "",
        "| 场景 | 位置误差σ | 发现率均值/最差 | 连续确认均值/最差 | 实际视锥概率覆盖 | 首次发现均值 | 未执行任务均值 | 规划P95均值 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary["aggregates"]:
        lines.append(
            "| {scenario_label} | {position_sigma_m:.0f}米 | {target_discovery_rate_mean:.1%}/{target_discovery_rate_min:.1%} | "
            "{continuous_confirmation_rate_mean:.1%}/{continuous_confirmation_rate_min:.1%} | "
            "{true_frustum_probability_mass_coverage_rate_mean:.1%} | {first_discovery_mean_s:.2f}秒 | "
            "{unexecuted_task_count_mean:.1f} | {planner_compute_p95_ms_mean:.2f}毫秒 |".format(**row)
        )
    lines.extend(
        [
            "",
            "在线分配记录中不含Actor名称或目标真实编号。真值只用于离线投影生成和试验结束评分。分配事件只有在平台按97米/秒限制到达观察点、云台按200度/秒限制完成转向，并完成0.3秒观察后，才计为实际观察。",
        ]
    )
    return "\n".join(lines) + "\n"


def _git_state() -> dict[str, Any]:
    root = CAMPAIGN_ROOT.parents[2]
    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        text=True,
        check=True,
        capture_output=True,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--short"),
        cwd=root,
        text=True,
        check=True,
        capture_output=True,
    ).stdout.splitlines()
    return {"git_revision": revision, "working_tree_dirty": bool(status)}


def run_matrix(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    seeds: Sequence[int] = DEFAULT_SEEDS,
) -> dict[str, Any]:
    output_root = Path(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output root: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    representative: OfflineSearchResult | None = None
    input_evidence: dict[str, dict[str, Any]] = {}
    for scenario in SCENARIOS:
        trajectory_path = Path(scenario["trajectory_path"])
        if not trajectory_path.is_file():
            raise FileNotFoundError(trajectory_path)
        for sigma in SIGMAS_M:
            for seed in seeds:
                config = OfflineSearchConfig(
                    target_count=int(scenario["target_count"]),
                    resource_count=int(scenario["resource_count"]),
                    position_sigma_m=float(sigma),
                    seed=int(seed),
                )
                result = run_offline_search(trajectory_path=trajectory_path, config=config)
                run_id = f"{scenario['scenario_id']}_sigma{int(sigma):03d}_seed{seed}"
                run_dir = output_root / "runs" / run_id
                write_offline_search_result(result, run_dir)
                row = {
                    "run_id": run_id,
                    "scenario_id": scenario["scenario_id"],
                    "scenario_label": scenario["label"],
                    **dict(result.metrics),
                    "run_path": str(run_dir.relative_to(output_root)),
                    "trajectory_sha256": result.trajectory_evidence.sha256,
                }
                rows.append(row)
                input_evidence[str(scenario["scenario_id"])] = {
                    "path": result.trajectory_evidence.source_path,
                    "sha256": result.trajectory_evidence.sha256,
                    "row_count": result.trajectory_evidence.row_count,
                    "recorded_start_s": result.trajectory_evidence.recorded_start_s,
                    "recorded_end_s": result.trajectory_evidence.recorded_end_s,
                    "extrapolated_after_s": result.trajectory_evidence.extrapolated_after_s,
                }
                if (
                    scenario["scenario_id"] == "n20_m8"
                    and sigma == 100.0
                    and seed == seeds[0]
                ):
                    representative = result
    expected = len(SCENARIOS) * len(SIGMAS_M) * len(seeds)
    if len(rows) != expected:
        raise RuntimeError(f"matrix incomplete: expected {expected}, produced {len(rows)}")
    aggregates = aggregate_rows(rows)
    summary = {
        "schema_version": "center-terminal-offline-search-matrix-v2",
        "matrix_status": "complete",
        "run_count": len(rows),
        "expected_run_count": expected,
        "seeds": list(seeds),
        "sigmas_m": list(SIGMAS_M),
        "scenarios": [
            {key: value for key, value in scenario.items() if key != "trajectory_path"}
            for scenario in SCENARIOS
        ],
        "protocol": {
            "source_precision": 1.0,
            "source_recall": 1.0,
            "position_error": "seeded zero-mean Gaussian truncated at 3 sigma on N/E/D",
            "camera": "1920x1080, horizontal FOV 19 deg, vertical FOV derived from aspect ratio",
            "observation_standoff_m": 700.0,
            "cell_overlap_fraction": 0.2,
            "platform_max_speed_mps": 97.0,
            "gimbal_max_rate_dps": 200.0,
            "observation_dwell_s": 0.3,
            "duration_s": 18.0,
            "recognition_gate_px": 10.0,
            "confirmation": "two consecutive frames",
            "random_miss_or_false_alarm": False,
            "assignment": "rolling utility matrix plus Hungarian one-to-one assignment",
            "resource_initial_state": "forward staging line at N=2100 m, E=-650..650 m, three height layers",
        },
        "trajectory_inputs": input_evidence,
        "aggregates": aggregates,
        "truth_isolation": {
            "online_truth_leakage_count": int(
                sum(int(row["online_truth_leakage_count"]) for row in rows)
            ),
            "truth_usage": "offline observation generation and scoring only",
        },
        **_git_state(),
    }
    _write_csv(output_root / "matrix.csv", rows)
    _write_json(output_root / "matrix_summary.json", summary)
    _write_json(
        output_root / "reproduction_manifest.json",
        {
            "schema_version": "center-terminal-offline-search-reproduction-v2",
            "command": (
                "PYTHONPATH=research_modules/independent_experiments python3 -m "
                "center_terminal_cv_campaign.exp_search.run_offline_matrix"
            ),
            "output_root": str(output_root.resolve()),
            "seeds": list(seeds),
            "input_evidence": input_evidence,
            "matrix_complete": len(rows) == expected,
            **_git_state(),
        },
    )
    figures = output_root / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    _build_flow_figure(figures / "01_search_flow.png")
    if representative is None:
        raise RuntimeError("representative run was not retained")
    _build_cell_figure(representative, figures / "02_search_cells_3d.png")
    _build_result_figure(aggregates, figures / "03_search_results.png")
    _build_coverage_figure(aggregates, figures / "04_search_coverage_budget.png")
    _build_timing_figure(aggregates, figures / "05_search_timing.png")
    (output_root / "OFFLINE_SEARCH_MATRIX_REPORT_CN.md").write_text(
        _build_technical_report(summary), encoding="utf-8"
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--seeds", type=int, nargs="+", default=DEFAULT_SEEDS)
    return parser


def main() -> int:
    args = _parser().parse_args()
    summary = run_matrix(output_root=args.output_root, seeds=tuple(args.seeds))
    print(args.output_root / "matrix_summary.json")
    print(f"completed={summary['run_count']}/{summary['expected_run_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
