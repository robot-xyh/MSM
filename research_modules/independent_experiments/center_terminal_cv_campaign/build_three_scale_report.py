#!/usr/bin/env python3
"""Build the 20/8, 20/30, and 40/50 AirSim comparison report."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence
import warnings

warnings.filterwarnings(
    "ignore",
    message="Unable to import Axes3D.*",
    category=UserWarning,
    module="matplotlib.projections",
)
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch, Patch, Rectangle
import numpy as np


EXPERIMENTS = ("search", "center_handover", "crossview")
DEFAULT_OUTPUT_NAME = "AIRSIM_20_8_20_30_40_50_FULL_REPORT_CN.md"
DEFAULT_FIGURE_DIR = "three_scale_report_figures"
DEFAULT_BENCHMARK_SUMMARY = (
    "gnn_offline_benchmark_20260816/benchmark_summary.json"
)


@dataclass(frozen=True)
class RunSpec:
    label: str
    directory_name: str
    target_count: int
    resource_count: int

    @property
    def scenario_id(self) -> str:
        return f"n{self.target_count}_m{self.resource_count}"


@dataclass(frozen=True)
class RunEvidence:
    spec: RunSpec
    path: Path
    summary: Mapping[str, Any]
    scenario: Mapping[str, Any]
    search: Mapping[str, Any]
    handover: Mapping[str, Any]
    crossview: Mapping[str, Any]


BenchmarkKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class BenchmarkEvidence:
    path: Path
    summary: Mapping[str, Any]
    results: Mapping[BenchmarkKey, Mapping[str, Any]]

    def result(
        self,
        scenario_id: str,
        task: str,
        backend: str,
        camera_pair_policy: str = "none",
    ) -> Mapping[str, Any]:
        key = (scenario_id, task, camera_pair_policy, backend)
        try:
            return self.results[key]
        except KeyError as exc:
            raise KeyError(f"benchmark result not found: {key}") from exc


RUN_SPECS = (
    RunSpec("20目标/8机", "airsim_n20_formal_v3_20260816", 20, 8),
    RunSpec("20目标/30机", "airsim_m30_n20_scale_20260816", 20, 30),
    RunSpec("40目标/50机", "airsim_m50_n40_scale_v2_20260816", 40, 50),
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def index_benchmark_results(
    results: Sequence[Mapping[str, Any]],
) -> dict[BenchmarkKey, Mapping[str, Any]]:
    """Index benchmark records and reject ambiguous duplicates."""

    indexed: dict[BenchmarkKey, Mapping[str, Any]] = {}
    for result in results:
        key = (
            str(result["scenario_id"]),
            str(result["task"]),
            str(result.get("camera_pair_policy", "none")),
            str(result["backend"]),
        )
        if key in indexed:
            raise ValueError(f"duplicate benchmark result: {key}")
        indexed[key] = result
    return indexed


def load_benchmark(path: Path) -> BenchmarkEvidence:
    summary = _read_json(path)
    if summary.get("schema_version") != "center-terminal-gnn-offline-benchmark-v1":
        raise ValueError(f"unsupported benchmark schema: {path}")
    if int(summary.get("held_out_seed", -1)) != 20260816:
        raise ValueError(f"unexpected benchmark held-out seed: {path}")
    indexed = index_benchmark_results(summary.get("results", ()))
    required: set[BenchmarkKey] = set()
    for spec in RUN_SPECS:
        for backend in ("geometry", "gnn"):
            required.add((spec.scenario_id, "center_handover", "none", backend))
            for policy in ("full", "sector_fov"):
                required.add((spec.scenario_id, "crossview", policy, backend))
    missing = sorted(required.difference(indexed))
    if missing:
        raise ValueError(f"benchmark is incomplete; missing {missing}")
    leakage = sum(
        int(result.get("metrics", {}).get("truth_leakage_count", 0))
        for result in indexed.values()
    )
    if leakage:
        raise ValueError(f"benchmark contains {leakage} truth-leakage events")
    return BenchmarkEvidence(path=path, summary=summary, results=indexed)


def fixture_counts(target_count: int) -> dict[str, int]:
    """Return the exact counts implied by 80% cue precision and recall."""

    if target_count <= 0 or target_count % 5:
        raise ValueError("target_count must be positive and divisible by five")
    true_cues = 4 * target_count // 5
    all_cues = target_count
    return {
        "true_cues": true_cues,
        "false_cues": all_cues - true_cues,
        "missed_targets": target_count - true_cues,
        "all_cues": all_cues,
        "gap_cells": max(5, math.ceil(0.4 * target_count)),
    }


def camera_pair_count(resource_count: int) -> int:
    if resource_count < 2:
        return 0
    return resource_count * (resource_count - 1) // 2


def _scenario_path(run_dir: Path) -> Path:
    paths = sorted((run_dir / "fixtures").glob("fixture_*/scenario.json"))
    if len(paths) != 1:
        raise FileNotFoundError(
            f"expected one scenario below {run_dir}, found {len(paths)}"
        )
    return paths[0]


def load_evidence(outputs_dir: Path, spec: RunSpec) -> RunEvidence:
    run_dir = outputs_dir / spec.directory_name
    evidence = RunEvidence(
        spec=spec,
        path=run_dir,
        summary=_read_json(run_dir / "campaign_summary.json"),
        scenario=_read_json(_scenario_path(run_dir)),
        search=_read_json(run_dir / "search" / "metrics.json"),
        handover=_read_json(run_dir / "center_handover" / "metrics.json"),
        crossview=_read_json(run_dir / "crossview" / "metrics.json"),
    )
    _validate_evidence(evidence)
    return evidence


def _validate_evidence(run: RunEvidence) -> None:
    if run.summary.get("mode") != "airsim":
        raise ValueError(f"{run.path.name} is not a real AirSim result")
    expected = (run.spec.target_count, run.spec.resource_count)
    actual = (int(run.summary["target_count"]), int(run.summary["resource_count"]))
    if actual != expected:
        raise ValueError(f"{run.path.name} count mismatch: {actual} != {expected}")
    if int(run.search["target_count"]) != run.spec.target_count:
        raise ValueError(f"{run.path.name} search target count mismatch")
    if int(run.search["resource_count"]) != run.spec.resource_count:
        raise ValueError(f"{run.path.name} search resource count mismatch")
    if not math.isclose(float(run.search["source_fixture_precision"]), 0.8):
        raise ValueError(f"{run.path.name} source precision is not 0.8")
    if not math.isclose(float(run.search["source_fixture_recall"]), 0.8):
        raise ValueError(f"{run.path.name} source recall is not 0.8")
    expected_fixture = fixture_counts(run.spec.target_count)
    expected_cells = expected_fixture["all_cues"] + expected_fixture["gap_cells"]
    if int(run.search["search_cell_count"]) != expected_cells:
        raise ValueError(f"{run.path.name} search-cell count mismatch")
    leakage = (
        int(run.search.get("online_truth_leakage_count", 0))
        + int(run.handover.get("truth_leakage_count", 0))
        + int(run.crossview.get("truth_leakage_count", 0))
    )
    if leakage:
        raise ValueError(f"{run.path.name} contains online truth leakage")


def _configure_plotting() -> None:
    plt.rcParams.update(
        {
            "font.family": "Noto Sans CJK JP",
            "axes.unicode_minus": False,
            "axes.edgecolor": "#48515a",
            "axes.labelcolor": "#22272b",
            "xtick.color": "#30363b",
            "ytick.color": "#30363b",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "font.size": 10,
        }
    )


def _save_figure(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _box(
    axis: plt.Axes,
    center: tuple[float, float],
    width: float,
    height: float,
    text: str,
    color: str,
    *,
    size: float = 10.0,
) -> None:
    x, y = center
    patch = FancyBboxPatch(
        (x - width / 2.0, y - height / 2.0),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.03",
        linewidth=1.2,
        edgecolor="#374047",
        facecolor=color,
    )
    axis.add_patch(patch)
    axis.text(x, y, text, ha="center", va="center", fontsize=size, linespacing=1.35)


def _arrow(axis: plt.Axes, start: tuple[float, float], end: tuple[float, float]) -> None:
    axis.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=13,
            linewidth=1.4,
            color="#46515a",
        )
    )


def _plot_full_chain(path: Path) -> None:
    fig, axis = plt.subplots(figsize=(16, 5.2))
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")
    centers = [0.075, 0.22, 0.365, 0.51, 0.655, 0.80, 0.935]
    texts = (
        "中心线索夹具\n精度80%\n召回率80%",
        "构造搜索单元\n线索单元+空白单元",
        "滚动匈牙利分配\n视场、转向、到达、复访",
        "AirSim匿名检测\n最长边≥10像素\n连续2帧确认",
        "中心结果交接\n几何白名单、匈牙利\n可选图网络评分",
        "机间跨视角配准\n责任区/视场稀疏\n几何+可选图网络",
        "目标簇与离线评分\n关系精度、召回率\n身份混合",
    )
    colors = ("#e5eef5", "#e8f1df", "#f8edcf", "#f5dfd9", "#dfeaf0", "#e9e0f0", "#e3ece7")
    widths = (0.12, 0.12, 0.125, 0.125, 0.125, 0.125, 0.105)
    for x, text, color, width in zip(centers, texts, colors, widths, strict=True):
        _box(axis, (x, 0.58), width, 0.36, text, color, size=9.2)
    for left, right in zip(centers[:-1], centers[1:]):
        _arrow(axis, (left + 0.065, 0.58), (right - 0.065, 0.58))
    axis.text(
        0.50,
        0.16,
        "在线链路只使用检测框、时间戳、相机内外参和匿名局部航迹；Actor名称与真实目标编号只用于运行结束后的离线评分。",
        ha="center",
        va="center",
        fontsize=11,
        color="#27313a",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#f5f6f7", "edgecolor": "#9aa2a8"},
    )
    axis.set_title("三组试验的统一计算链路", fontsize=15, pad=12)
    _save_figure(fig, path)


def _annotate_bars(axis: plt.Axes, bars: Sequence[Any], *, decimals: int = 0) -> None:
    for bar in bars:
        height = float(bar.get_height())
        text = f"{height:.{decimals}f}"
        axis.annotate(
            text,
            (bar.get_x() + bar.get_width() / 2.0, height),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8.5,
        )


def _plot_search_capacity(runs: Sequence[RunEvidence], path: Path) -> None:
    labels = [run.spec.label for run in runs]
    cells = np.asarray([run.search["search_cell_count"] for run in runs], dtype=float)
    covered = np.asarray([run.search["covered_cell_count"] for run in runs], dtype=float)
    actual = np.asarray([run.search["assignment_count"] for run in runs], dtype=float)
    capacity = np.asarray([run.search["assignment_capacity"] for run in runs], dtype=float)
    positions = np.arange(len(runs))
    width = 0.19
    fig, axis = plt.subplots(figsize=(11.5, 6.2))
    b1 = axis.bar(positions - 1.5 * width, cells, width, label="搜索单元", color="#567b9a")
    b2 = axis.bar(positions - 0.5 * width, covered, width, label="唯一覆盖", color="#5f9e6e")
    b3 = axis.bar(positions + 0.5 * width, actual, width, label="实际分配次数", color="#d3a249")
    b4 = axis.bar(positions + 1.5 * width, capacity, width, label="三轮理论容量", color="#b66a5e")
    for bars in (b1, b2, b3, b4):
        _annotate_bars(axis, bars)
    axis.set_xticks(positions, labels)
    axis.set_ylabel("单元或分配次数")
    axis.set_title("搜索单元、覆盖结果与三轮分配容量")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(ncol=4, loc="upper left")
    fig.text(
        0.50,
        0.01,
        "20目标/8机：3轮×8机=24个分配槽，小于28个单元，理论上至少留下4个单元未覆盖。",
        ha="center",
        va="bottom",
        fontsize=9.5,
    )
    fig.subplots_adjust(bottom=0.13)
    _save_figure(fig, path)


def _plot_search_results(runs: Sequence[RunEvidence], path: Path) -> None:
    labels = [run.spec.label for run in runs]
    series = (
        ("搜索单元覆盖", [100.0 * float(run.search["cell_coverage_rate"]) for run in runs], "#567b9a"),
        ("达到10像素", [100.0 * int(run.search["recognized_target_count"]) / run.spec.target_count for run in runs], "#5f9e6e"),
        ("连续确认", [100.0 * int(run.search["discovered_target_count"]) / run.spec.target_count for run in runs], "#d3a249"),
        ("中心漏检补获", [100.0 * float(run.search["center_missed_recovery_recall"]) for run in runs], "#b66a5e"),
    )
    positions = np.arange(len(runs))
    width = 0.19
    fig, axis = plt.subplots(figsize=(11.5, 6.2))
    for index, (name, values, color) in enumerate(series):
        bars = axis.bar(positions + (index - 1.5) * width, values, width, label=name, color=color)
        _annotate_bars(axis, bars, decimals=1)
    axis.set_ylim(0.0, 112.0)
    axis.set_ylabel("比例（%）")
    axis.set_xticks(positions, labels)
    axis.set_title("搜索与连续识别结果")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(ncol=4, loc="lower right")
    _save_figure(fig, path)


def _plot_handover_geometry(path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.8))
    world, image = axes
    world.set_xlim(-0.2, 10.5)
    world.set_ylim(-2.8, 3.0)
    world.set_aspect("equal")
    world.axis("off")
    world.add_patch(Rectangle((0.2, -0.75), 1.15, 1.5, facecolor="#506a7b", edgecolor="#26343d"))
    world.text(0.78, 0.0, "机载相机", color="white", ha="center", va="center")
    world.plot([1.35, 9.2], [0.0, 1.25], color="#65727b", linestyle="--", linewidth=1.2)
    world.scatter([7.6], [1.0], s=80, marker="x", color="#bb403b", linewidths=2.2, label="线索外推位置")
    world.add_patch(Ellipse((7.6, 1.0), 2.2, 1.15, angle=10, facecolor="#e8b1ac", alpha=0.45, edgecolor="#bb403b"))
    world.scatter([7.75], [0.86], s=55, color="#2c7f54", label="实际局部检测")
    world.text(4.4, 1.25, "北东地坐标 → 机体 → 云台 → 相机", ha="center", fontsize=11)
    world.text(5.6, -1.8, "先按图像时刻外推状态和协方差，再使用实测相机位姿投影", ha="center", fontsize=10)
    world.legend(loc="upper left")
    world.set_title("三维线索投到机载相机")

    image.set_xlim(0, 1920)
    image.set_ylim(1080, 0)
    image.set_aspect("equal")
    image.set_xlabel("图像横坐标（像素）")
    image.set_ylabel("图像纵坐标（像素）")
    image.add_patch(Ellipse((980, 520), 360, 180, angle=-12, facecolor="#e8b1ac", alpha=0.42, edgecolor="#bb403b", linewidth=2))
    image.scatter([980], [520], marker="x", s=90, color="#bb403b", linewidths=2.4, label="预测像点")
    image.scatter([1030, 1300, 610], [550, 430, 760], s=65, color=["#2c7f54", "#606b73", "#606b73"], label="匿名局部航迹")
    image.plot([980, 1030], [520, 550], color="#2c7f54", linewidth=2.0)
    image.text(1050, 610, "马氏距离合格", color="#2c7f54", fontsize=10)
    image.text(1190, 820, "几何、时间和运动门控后\n由匈牙利算法给出一一对应", ha="center", fontsize=10.5)
    image.legend(loc="upper right")
    image.set_title("像面不确定椭圆与局部检测匹配")
    fig.suptitle("中心结果交接原理", fontsize=15)
    _save_figure(fig, path)


def _plot_handover_results(
    runs: Sequence[RunEvidence], benchmark: BenchmarkEvidence, path: Path
) -> None:
    labels: list[str] = []
    correct: list[int] = []
    wrong: list[int] = []
    colors: list[str] = []
    for run in runs:
        for backend, method, color in (
            ("geometry", "几何", "#567b9a"),
            ("gnn", "图网络", "#5f9e6e"),
        ):
            metrics = benchmark.result(
                run.spec.scenario_id, "center_handover", backend
            )["metrics"]
            labels.append(f"{run.spec.label}\n{method}")
            correct.append(int(metrics["true_binding_count"]))
            wrong.append(int(metrics["false_binding_count"]))
            colors.append(color)

    positions = np.arange(len(labels))
    fig, axis = plt.subplots(figsize=(12.5, 6.2))
    bars = axis.bar(positions, correct, color=colors)
    error_bars = axis.bar(
        positions,
        wrong,
        bottom=correct,
        color="#b66a5e",
        edgecolor="#8f3f36",
    )
    for bar, correct_count, wrong_count in zip(bars, correct, wrong, strict=True):
        axis.annotate(
            f"{correct_count}正确 / {wrong_count}错误",
            (bar.get_x() + bar.get_width() / 2.0, correct_count + wrong_count),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8.5,
        )
    axis.set_ylim(0.0, max(np.asarray(correct) + np.asarray(wrong)) * 1.22)
    axis.set_xticks(positions, labels)
    axis.set_ylabel("绑定数量")
    axis.set_title("中心交接几何基线与图网络离线对照")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(
        handles=(
            Patch(facecolor="#567b9a", label="几何方法"),
            Patch(facecolor="#5f9e6e", label="图网络方法"),
            Patch(facecolor="#b66a5e", edgecolor="#8f3f36", label="错误绑定部分"),
        ),
        loc="upper left",
    )
    _save_figure(fig, path)


def _plot_crossview_rays(path: Path) -> None:
    fig, axis = plt.subplots(figsize=(11.8, 7.0))
    camera_a = np.asarray((0.0, -3.0, 0.0))
    camera_b = np.asarray((0.0, 3.0, 0.8))
    point_a = np.asarray((8.0, 0.15, 1.2))
    point_b = np.asarray((8.0, -0.10, 1.3))
    midpoint = (point_a + point_b) / 2.0

    def project(points: np.ndarray) -> np.ndarray:
        values = np.atleast_2d(points).astype(float)
        return np.column_stack(
            (
                values[:, 0] + 0.42 * values[:, 1],
                values[:, 2] + 0.24 * values[:, 1],
            )
        )

    pa, pb, qa, qb, middle = project(
        np.vstack((camera_a, camera_b, point_a, point_b, midpoint))
    )
    axis.scatter(*pa, s=90, marker="s", color="#567b9a", zorder=5)
    axis.scatter(*pb, s=90, marker="s", color="#d3a249", zorder=5)
    axis.text(pa[0] - 0.35, pa[1] - 0.45, "相机A")
    axis.text(pb[0] - 0.05, pb[1] + 0.28, "相机B")
    axis.plot(*project(np.vstack((camera_a, point_a))).T, color="#567b9a", linewidth=2, label="A像点反投影视线")
    axis.plot(*project(np.vstack((camera_b, point_b))).T, color="#d3a249", linewidth=2, label="B像点反投影视线")
    axis.plot(*np.vstack((qa, qb)).T, color="#bb403b", linewidth=2.4, label="两视线最短距离")
    axis.scatter(*middle, s=120, marker="*", color="#2c7f54", zorder=6)
    axis.text(middle[0] + 0.2, middle[1] + 0.2, "三角交会中点")
    trajectory = np.vstack([midpoint + np.asarray((step, 0.10 * math.sin(step), 0.03 * step)) for step in np.linspace(-2.0, 2.0, 25)])
    axis.plot(*project(trajectory).T, color="#2c7f54", linestyle="--", linewidth=1.8, label="多时刻交会轨迹")

    origin = project(np.asarray((0.0, 0.0, -0.5)))[0]
    for vector, label in (
        ((2.0, 0.0, 0.0), "北向"),
        ((0.0, 2.0, 0.0), "东向"),
        ((0.0, 0.0, 1.5), "高度"),
    ):
        endpoint = project(np.asarray(vector) + np.asarray((0.0, 0.0, -0.5)))[0]
        axis.annotate("", endpoint, origin, arrowprops={"arrowstyle": "->", "color": "#59636b"})
        axis.text(endpoint[0], endpoint[1], label, fontsize=9)
    axis.text(
        0.02,
        0.96,
        "等轴测三维示意",
        transform=axis.transAxes,
        va="top",
        color="#606970",
    )
    axis.set_title("跨视角配准的双视线交会与多时刻运动检验")
    axis.set_aspect("equal", adjustable="datalim")
    axis.axis("off")
    axis.legend(loc="upper right")
    _save_figure(fig, path)


def _plot_crossview_funnel(
    runs: Sequence[RunEvidence], benchmark: BenchmarkEvidence, path: Path
) -> None:
    labels = [run.spec.label for run in runs]
    full_pairs: list[int] = []
    sparse_pairs: list[int] = []
    full_edges: list[int] = []
    sparse_edges: list[int] = []
    for run in runs:
        full = benchmark.result(
            run.spec.scenario_id, "crossview", "geometry", "full"
        )
        sparse = benchmark.result(
            run.spec.scenario_id, "crossview", "geometry", "sector_fov"
        )
        full_pairs.append(int(full["candidate_audit"]["camera_pair_retained_count"]))
        sparse_pairs.append(int(sparse["candidate_audit"]["camera_pair_retained_count"]))
        full_edges.append(int(full["metrics"]["candidate_edge_count"]))
        sparse_edges.append(int(sparse["metrics"]["candidate_edge_count"]))

    positions = np.arange(len(runs))
    width = 0.34
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 5.9))
    left, right = axes
    left_full = left.bar(positions - width / 2, full_pairs, width, color="#8b98a1", label="全相机")
    left_sparse = left.bar(positions + width / 2, sparse_pairs, width, color="#5f9e6e", label="责任区/视场稀疏")
    _annotate_bars(left, left_full)
    _annotate_bars(left, left_sparse)
    left.set_xticks(positions, labels)
    left.set_ylabel("保留相机对")
    left.set_title("相机对预筛选")
    left.grid(axis="y", alpha=0.25)
    left.legend(loc="upper left")

    right_full = right.bar(positions - width / 2, full_edges, width, color="#8b98a1", label="全相机")
    right_sparse = right.bar(positions + width / 2, sparse_edges, width, color="#5f9e6e", label="责任区/视场稀疏")
    right.set_yscale("log")
    right.set_xticks(positions, labels)
    right.set_ylabel("候选边（对数坐标）")
    right.set_title("候选关系规模")
    right.grid(axis="y", which="both", alpha=0.2)
    right.legend(loc="upper left")
    for bars, values in ((right_full, full_edges), (right_sparse, sparse_edges)):
        for bar, value in zip(bars, values, strict=True):
            right.annotate(
                f"{value:,}",
                (bar.get_x() + bar.get_width() / 2.0, value),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8.2,
            )
    fig.suptitle("责任区和视场筛选前后的候选规模", fontsize=15)
    _save_figure(fig, path)


def _plot_scaling_results(
    runs: Sequence[RunEvidence], benchmark: BenchmarkEvidence, path: Path
) -> None:
    labels = [run.spec.label for run in runs]
    positions = np.arange(len(runs))
    methods = (
        ("full", "geometry", "全相机/几何", "#8b98a1"),
        ("full", "gnn", "全相机/图网络", "#d3a249"),
        ("sector_fov", "geometry", "稀疏/几何", "#567b9a"),
        ("sector_fov", "gnn", "稀疏/图网络", "#5f9e6e"),
    )
    width = 0.19
    fig, axes = plt.subplots(1, 2, figsize=(16.0, 6.4))
    quality_axis, timing_axis = axes
    for method_index, (policy, backend, label, color) in enumerate(methods):
        offset = (method_index - 1.5) * width
        records = [
            benchmark.result(run.spec.scenario_id, "crossview", backend, policy)
            for run in runs
        ]
        precision = [100.0 * float(record["metrics"]["association_precision"]) for record in records]
        recall = [100.0 * float(record["metrics"]["association_recall"]) for record in records]
        mixed = [int(record["metrics"]["id_switch_count"]) for record in records]
        bars = quality_axis.bar(positions + offset, precision, width, color=color, label=label)
        quality_axis.scatter(
            positions + offset,
            recall,
            marker="D",
            s=28,
            color="#26343d",
            zorder=5,
        )
        for bar, precision_value, mixed_count in zip(
            bars, precision, mixed, strict=True
        ):
            quality_axis.annotate(
                f"{precision_value:.1f}",
                (bar.get_x() + bar.get_width() / 2.0, precision_value),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=7.0,
                rotation=90,
            )
            quality_axis.text(
                bar.get_x() + bar.get_width() / 2.0,
                3.0,
                f"混{mixed_count}",
                ha="center",
                va="bottom",
                fontsize=7.0,
                rotation=90,
                color="white",
            )
        durations = [float(record["timing"]["median_wall_duration_s"]) for record in records]
        time_bars = timing_axis.bar(positions + offset, durations, width, color=color, label=label)
        for bar, duration in zip(time_bars, durations, strict=True):
            timing_axis.annotate(
                f"{duration:.1f}",
                (bar.get_x() + bar.get_width() / 2.0, duration),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=7.2,
                rotation=90,
            )

    quality_axis.set_xticks(positions, labels)
    quality_axis.set_ylim(0, 116)
    quality_axis.set_ylabel("关系精度、召回率（%）")
    quality_axis.set_title("关联质量：柱为精度，菱形为召回率")
    quality_axis.grid(axis="y", alpha=0.25)
    quality_axis.legend(ncol=2, loc="lower left", fontsize=8.5)
    timing_axis.set_xticks(positions, labels)
    timing_axis.set_yscale("log")
    timing_axis.set_ylabel("关联、审计与绘图时间（秒，对数坐标）")
    timing_axis.set_title("保存回放离线复算时间")
    timing_axis.grid(axis="y", which="both", alpha=0.2)
    timing_axis.legend(ncol=2, loc="upper left", fontsize=8.5)
    fig.suptitle("全相机、稀疏相机图与图网络对照", fontsize=15)
    _save_figure(fig, path)


def build_figures(
    runs: Sequence[RunEvidence], benchmark: BenchmarkEvidence, figure_dir: Path
) -> tuple[Path, ...]:
    _configure_plotting()
    paths = (
        figure_dir / "01_full_chain.png",
        figure_dir / "02_search_capacity.png",
        figure_dir / "03_search_results.png",
        figure_dir / "04_handover_geometry.png",
        figure_dir / "05_handover_results.png",
        figure_dir / "06_crossview_rays.png",
        figure_dir / "07_crossview_funnel.png",
        figure_dir / "08_scaling_results.png",
    )
    _plot_full_chain(paths[0])
    _plot_search_capacity(runs, paths[1])
    _plot_search_results(runs, paths[2])
    _plot_handover_geometry(paths[3])
    _plot_handover_results(runs, benchmark, paths[4])
    _plot_crossview_rays(paths[5])
    _plot_crossview_funnel(runs, benchmark, paths[6])
    _plot_scaling_results(runs, benchmark, paths[7])
    return paths


def _ratio(value: Any, digits: int = 4) -> str:
    return f"{float(value):.{digits}f}"


def _percent(value: Any, digits: int = 1) -> str:
    return f"{100.0 * float(value):.{digits}f}%"


def _table_row(values: Sequence[Any]) -> str:
    return "| " + " | ".join(str(value) for value in values) + " |"


def _relative_figure(report_path: Path, figure_path: Path) -> str:
    return figure_path.relative_to(report_path.parent).as_posix()


def build_report(
    runs: Sequence[RunEvidence],
    benchmark: BenchmarkEvidence,
    output_path: Path,
    figure_paths: Sequence[Path],
) -> Path:
    if len(runs) != 3 or len(figure_paths) != 8:
        raise ValueError("the report requires three runs and eight figures")
    run_20_8, run_20_30, run_40_50 = runs
    figure_links = [_relative_figure(output_path, path) for path in figure_paths]
    focal_px = 1920.0 / (2.0 * math.tan(math.radians(19.0) / 2.0))
    nominal_extent_px = focal_px * 3.0 / 700.0
    nominal_ten_pixel_range_m = focal_px * 3.0 / 10.0
    center_geometry = [
        benchmark.result(run.spec.scenario_id, "center_handover", "geometry")
        for run in runs
    ]
    center_gnn = [
        benchmark.result(run.spec.scenario_id, "center_handover", "gnn")
        for run in runs
    ]
    full_geometry = [
        benchmark.result(run.spec.scenario_id, "crossview", "geometry", "full")
        for run in runs
    ]
    full_gnn = [
        benchmark.result(run.spec.scenario_id, "crossview", "gnn", "full")
        for run in runs
    ]
    sparse_geometry = [
        benchmark.result(
            run.spec.scenario_id, "crossview", "geometry", "sector_fov"
        )
        for run in runs
    ]
    sparse_gnn = [
        benchmark.result(run.spec.scenario_id, "crossview", "gnn", "sector_fov")
        for run in runs
    ]
    center_validation = benchmark.summary["training"]["center_handover"]["validation_metrics"]
    crossview_validation = benchmark.summary["training"]["crossview"]["validation_metrics"]
    acceptance_checks = benchmark.summary["acceptance"]["checks"]
    acceptance_passed = sum(bool(check["passed"]) for check in acceptance_checks)
    truth_isolation_count = sum(
        1
        for result in benchmark.results.values()
        if int(result["metrics"].get("truth_leakage_count", 0)) == 0
    )
    sparse_40_reduction = 1.0 - (
        int(sparse_geometry[2]["metrics"]["candidate_edge_count"])
        / int(full_geometry[2]["metrics"]["candidate_edge_count"])
    )
    sparse_40_gnn_runtime_increase = (
        float(sparse_gnn[2]["timing"]["median_wall_duration_s"])
        / float(sparse_geometry[2]["timing"]["median_wall_duration_s"])
        - 1.0
    )

    lines = [
        "# 20目标/8机、20目标/30机与40目标/50机AirSim试验报告",
        "",
        "## 1. 结论",
        "",
        "三组试验分别验证资源不足、资源充足和目标与资源同步扩大的情况。搜索层的结果与资源容量直接相关。20目标/8机在三轮内最多执行24次唯一分配，低于28个搜索单元，因此只覆盖24个单元，连续确认19个目标，并补获中心漏掉的3个目标。20目标/30机和40目标/50机覆盖全部搜索单元，所有目标达到10像素门限并完成连续确认，中心漏掉的4个和8个目标全部补获。",
        "",
        "中心交接的几何基线在三组回放中得到16、14和31条正确绑定，前两组没有错误绑定，40目标/50机有1条错误绑定。图神经网络对照保持正确绑定数量不变，并消除了40目标/50机的这1条错误绑定。该改进只来自一个AirSim种子，暂不足以替换确定性几何基线。",
        "",
        f"跨视角配准中，限制相机比较范围是本轮最有效的规模改进。责任区和视场筛选把40目标/50机候选边从1,104,646条降到375,236条，减少{_percent(sparse_40_reduction)}；稀疏几何方法的关系精度由0.5824提高到0.9960，身份混合由18个降到0。20目标/30机的稀疏图神经网络把关系精度从0.7402提高到0.8008、召回率从0.8967提高到0.9078，并把身份混合从4个降到2个。40目标/50机的稀疏图神经网络没有继续改善质量，复算时间反而增加{_percent(sparse_40_gnn_runtime_increase)}。",
        "",
        "当前默认路径采用责任区/视场稀疏相机图、几何门控和匈牙利一一匹配。图神经网络保留为离线可选对照。三组结果来自同一随机种子20260816，是功能与规模压力证据，不是统计意义上的性能定型。搜索、中心交接和机间配准在一次Blocks进程中按reset分段运行；图神经网络对照复用保存的AirSim观测离线计算，没有重新运行Blocks。",
        "",
        "## 2. 试验范围",
        "",
        _table_row(("项目", "设置")),
        _table_row(("---", "---")),
        _table_row(("仿真模式", "AirSim ComputerVision")),
        _table_row(("目标与资源", "20目标/8机、20目标/30机、40目标/50机")),
        _table_row(("运行方式", "一个Blocks进程，搜索、中心交接和跨视角专项之间reset")),
        _table_row(("目标", "无人机静态网格模型作为Actor，以50米/秒移动，最长尺寸3米")),
        _table_row(("场景时长与步长", "18秒，状态步长0.1秒，ClockSpeed=0.1")),
        _table_row(("中心相机", "2台，1280×1024，水平视场角3.67度")),
        _table_row(("机载相机", "1920×1080，水平视场角19度，相机前移0.5米")),
        _table_row(("搜索观察距离", "距搜索单元中心标称700米")),
        _table_row(("中心线索", "固定构造精度80%、召回率80%的线索集合")),
        _table_row(("检测输入", "AirSim simGetDetections检测框，在线立即去除Actor名称")),
        _table_row(("识别门限", "检测框最长边不小于10像素，连续2帧确认")),
        _table_row(("关联主线", "责任区/视场稀疏相机图、确定性几何门控、匈牙利一一匹配、连续确认")),
        _table_row(("学习对照", "合成数据训练图神经网络，只在几何白名单内修正代价，不进入默认在线路径")),
        _table_row(("回放方式", "保存AirSim匿名观测离线复算；seed 20260816不参与模型训练")),
        _table_row(("随机种子", "20260816，三组均为单次运行")),
        "",
        "本试验没有验证真实探测器、导航误差、通信丢包、飞行动力学和物理拦截。Actor名称和真实目标编号只进入运行结束后的离线评分。搜索、几何关联和图神经网络回放只读取匿名检测框、时间戳、相机位姿、相机参数和局部航迹。",
        "",
        "## 3. 总体流程",
        "",
        f"![三组试验统一计算链路]({figure_links[0]})",
        "",
        "计算链路分为三段。第一段根据不完整中心线索构造概率区域，再把机载相机分配到线索单元和空白单元。第二段将中心线索按图像时刻外推并投到机载相机像面，与匿名局部航迹建立一一绑定。第三段先按责任区和视场保留可能共同观测的相机对，再根据检测框、位姿和时间恢复跨视角的同目标关系。几何方法始终负责候选白名单和安全门控；图神经网络只对通过白名单的候选修正匹配代价。",
        "",
        f"每个专项都保留在线数据与离线真值的边界。AirSim返回的Actor名称在适配器入口被转存到离线标签，算法收到的是重新编号的检测和局部航迹。模型训练只使用独立生成的合成样本，留出seed 20260816从未进入训练。离线评分阶段再用Actor名称核对正确关系、错误关系和身份混合。本轮{truth_isolation_count}组几何/图网络回放的真值泄漏计数均为0。",
        "",
        "## 4. 协同搜索与资源分配",
        "",
        "### 4.1 80%精度和80%召回率的数量关系",
        "",
        "设真实目标数为N，正确中心线索数为T，全部中心线索数为S。召回率为T/N=0.8，精度为T/S=0.8，因此：",
        "",
        "```text",
        "正确线索 T = 0.8N",
        "全部线索 S = T / 0.8 = N",
        "错误线索 F = S - T = 0.2N",
        "中心漏掉目标 M = N - T = 0.2N",
        "```",
        "",
        "这组构造同时保留错误线索和漏检目标。中心给出的每条线索只说明某个区域可能有目标，不能直接当作已经确认的目标身份。正确线索和错误线索都会生成线索搜索单元；中心漏掉的目标没有对应线索，只能依靠来袭走廊中的空白搜索单元补获。空白搜索单元数取 `max(5, ceil(0.4N))`，总搜索单元数为 `S + 空白单元数`。",
        "",
        "搜索单元按两步形成。第一步把线索位置从测量时刻推到本轮规划时刻，关系式为 `p(t)=p0+vΔt`。第二步根据位置协方差确定搜索范围，三个方向的半宽取 `max(30米, 3sqrt(P_ii))`。本轮线索位置标准差为1米，三倍标准差只有3米，因此实际采用30米下限，防止把搜索范围压成一个过小点位。每个线索单元保留候选中心航迹编号，但该编号只用于后续尝试交接，不会因一次发现就直接绑定。",
        "",
        "没有线索约束的空白单元铺在北向2500至3500米、东向-650至650米、高度-220至-70米的来袭走廊内。空白单元概率取0.32。它的作用是给中心漏检目标保留搜索机会，不表示该单元已经发现目标。规划时，线索单元与空白单元进入同一个收益矩阵，由资源数量和当前收益共同决定先看哪里。",
        "",
        _table_row(("目标规模", "正确线索", "错误线索", "中心漏掉", "全部线索", "空白单元", "总搜索单元")),
        _table_row(("---", "---:", "---:", "---:", "---:", "---:", "---:")),
    ]
    for run in runs:
        counts = fixture_counts(run.spec.target_count)
        lines.append(
            _table_row(
                (
                    run.spec.label,
                    counts["true_cues"],
                    counts["false_cues"],
                    counts["missed_targets"],
                    counts["all_cues"],
                    counts["gap_cells"],
                    run.search["search_cell_count"],
                )
            )
        )

    lines.extend(
        (
            "",
            "### 4.2 搜索容量与滚动分配",
            "",
            "滚动分配每轮接收三类输入：可用相机的位置和姿态、全部有效搜索单元、各单元已有覆盖次数和上次覆盖时间。若有M台可用相机、K个有效搜索单元，先建立M×K的收益矩阵。矩阵第i行第j列表示第i台相机在本轮搜索第j个单元的收益。当前确定性收益为：",
            "",
            "```text",
            "U = 3p + 4G - 0.8C_slew - 1.0C_arrival - 4C_repeat",
            "G = p × V × Q",
            "```",
            "",
            "这条式子先奖励目标概率和预期发现收益，再扣除转动、到达和重复观察代价。`p`是单元目标概率。`V`是按相机水平视场宽度与区域宽度计算的可见程度，限制在0.2至1.0。`Q=1/(1+n)`表示新颖度，`n`是该单元已经被覆盖的次数。`C_slew`由当前姿态到目标姿态的偏航、俯仰变化得到，最大记为1.5。`C_arrival`由相机到观察位置的距离除以3000米得到，最大记为1.5。`C_repeat=n/(1+Δt/2)`压低刚刚看过的单元，其中`Δt`是距上次观察的时间。这样可以优先安排高概率、容易看全且近期没有看过的单元。",
            "",
            "19度水平视场角在700米观察距离上的名义覆盖宽度为 `2×700×tan(19°/2)≈234.3米`。规划器以该宽度除以搜索单元东向宽度得到`V`。因此，面积较大的空白单元会得到较低的单次可见程度，并通过后续复访补齐。",
            "",
            "为了同时解决全部相机之间的占用冲突，规划器在收益矩阵右侧增加M个空闲列，形成M×(K+M)矩阵。空闲收益为-0.05。矩阵取负后交给匈牙利算法一次求解；每一行只能选一列，因此每台相机本轮最多承担一个单元，每个真实单元也最多分给一台相机。当某台相机对剩余单元的收益都低于空闲收益时，它保持空闲，避免为凑满矩阵而重复搜索低价值单元。",
            "",
            "匹配完成后，系统把单元中心前方700米处作为观察位置，并由观察位置指向单元中心，计算相机偏航和俯仰。相机到位后连续读取3帧检测结果。该轮结束时，无论是否发现目标，都把已执行的单元记为完成一次覆盖，并记录覆盖时间；下一轮的重复代价会优先把资源让给尚未覆盖的单元。随着间隔时间增加，重复代价逐步下降，原单元仍可再次进入分配。当前实现不会根据一次未发现自动提高邻区概率，也不会凭空生成目标航迹；没有形成连续确认的单元只保留覆盖记录，不产生交接记录。",
            "",
            "三组均执行3轮分配，理论槽位为 `3×资源数`。20目标/8机只有24个槽位，少于28个单元，因此即使没有重复分配也至少留下4个单元。20目标/30机首轮即可覆盖28个单元。40目标/50机首轮最多覆盖50个单元，第二轮可以补齐剩余6个。实际分配次数高于唯一覆盖数的部分是后续复访。",
            "",
            f"![搜索容量]({figure_links[1]})",
            "",
            _table_row(("场景", "分配矩阵规模", "三轮容量", "实际分配", "唯一覆盖", "未覆盖", "重复覆盖率")),
            _table_row(("---", "---:", "---:", "---:", "---:", "---:", "---:")),
        )
    )
    for run in runs:
        matrix_size = f"{run.spec.resource_count}×({run.search['search_cell_count']}+{run.spec.resource_count})"
        lines.append(
            _table_row(
                (
                    run.spec.label,
                    matrix_size,
                    run.search["assignment_capacity"],
                    run.search["assignment_count"],
                    run.search["covered_cell_count"],
                    run.search["unassigned_cell_count"],
                    _percent(run.search["duplicate_coverage_rate"]),
                )
            )
        )

    lines.extend(
        (
            "",
            "### 4.3 像素门限、局部航迹和连续复访",
            "",
            "机载相机焦距的像素表达为 `f_x=W/[2tan(FOV/2)]`。代入1920像素和19度水平视场角，得到 `f_x≈5736.7像素`。目标垂直于视线、可见尺寸为3米、距离700米时，理想成像尺寸约为 `5736.7×3/700≈24.6像素`。按10像素门限反算的理想最大距离约为1721米。这个计算只用于解释门限量级；Actor姿态、网格外形、遮挡和相机夹角会改变实际检测框，因此运行时仍以AirSim返回的检测框为准。",
            "",
            "每个已分配单元连续观察3帧，帧间隔0.1秒。检测框最长边达到10像素后记为可识别。相机在同一搜索单元内使用检测框中心距离建立匿名局部航迹：先计算当前检测与上一帧局部航迹之间的像素距离，超过180像素的组合直接排除，其余组合再用匈牙利算法一一连接。这个局部过程只为判断连续性，不读取Actor名称。",
            "",
            "同一局部航迹连续2帧达到10像素门限后才生成确认记录。3帧观察提供三次检测机会，但确认所需的两帧必须相邻；中间漏掉一帧不能把前后两次检测直接拼成连续确认。若本轮只有一次达到门限、检测框小于10像素或始终没有检测，系统不生成交接记录。该单元仍计入已观察范围，并按上一节的滚动规则在后续轮次参与复访。",
            "",
            f"![搜索结果]({figure_links[2]})",
            "",
            _table_row(("指标", "20目标/8机", "20目标/30机", "40目标/50机")),
            _table_row(("---", "---:", "---:", "---:")),
        )
    )
    search_rows = (
        ("搜索单元覆盖", "covered_cell_count", "search_cell_count"),
        ("达到10像素的目标", "recognized_target_count", "target_count"),
        ("连续确认目标", "discovered_target_count", "target_count"),
        ("中心漏检补获", "center_missed_recovered_count", "center_missed_target_count"),
    )
    for label, numerator, denominator in search_rows:
        values = []
        for run in runs:
            denominator_value = run.spec.target_count if denominator == "target_count" else run.search[denominator]
            values.append(f"{run.search[numerator]}/{denominator_value}")
        lines.append(_table_row((label, *values)))
    lines.extend(
        (
            _table_row(("匿名检测记录", *(run.search["online_detection_count"] for run in runs))),
            _table_row(("低于10像素检测", *(run.search["below_ten_pixel_detection_count"] for run in runs))),
            _table_row(("规划平均耗时", *(f"{float(run.search['planner_compute_mean_ms']):.3f}毫秒" for run in runs))),
            _table_row(("规划最大耗时", *(f"{float(run.search['planner_compute_max_ms']):.3f}毫秒" for run in runs))),
            "",
            "20目标/8机虽然20个目标都至少一次达到10像素，但只有19个通过连续确认。这说明“看见过”与“形成可交接航迹”是两个指标。资源不足首先表现为单元覆盖不完整，其次表现为重访和连续确认机会减少。20目标/30机和40目标/50机均完成全部目标确认，搜索规划平均耗时分别为11.739毫秒和35.753毫秒，单次计算仍低于40毫秒。该耗时不包含相机移动、AirSim接口等待和跨视角关联。",
            "",
            "## 5. 中心节点与拦截无人机关联",
            "",
            "### 5.1 状态外推与坐标转换",
            "",
            "中心线索和机载局部航迹不在同一种坐标中，也不一定在同一时刻。前者给出北东地坐标中的位置、速度和不确定范围，后者给出图像中的检测框中心。关联计算先回答“中心线索在这张图上应该出现在哪里”，再判断实际局部航迹是否落在预测范围内。",
            "",
            "中心线索包含位置、速度、测量时刻、到达时刻、有效期和6×6协方差。状态写成 `x=[p,v]`。图像时刻与线索测量时刻之差为 `Δt`，先按匀速模型把线索推到图像时刻：",
            "",
            "```text",
            "x(t) = F x0",
            "F = [[I, Δt·I], [0, I]]",
            "P(t) = F P0 F^T + Q",
            "```",
            "",
            "`Q`表示外推期间可能发生的机动。本试验按白噪声加速度模型构造，加速度标准差为0.5米/秒²。位置块为 `qΔt⁴/4`，位置与速度交叉块为 `qΔt³/2`，速度块为 `qΔt²`，其中 `q=0.5²`。外推时间越长，协方差越大，后续在图像上的允许搜索椭圆也随之扩大；这可以避免用过窄门限拒绝较旧线索，同时会增加错误候选，因此还需要运动门控和一一匹配。",
            "",
            "外推位置先减去相机位置，得到目标相对相机的三维向量，再按机体姿态、云台姿态和相机安装关系转入相机坐标 `(x_c,y_c,z_c)`。本试验每帧读取AirSim返回的最终相机位置和姿态，不沿用初始设置值。AirSim相机的x轴朝前、y轴朝图像右侧、z轴朝下，针孔投影为：",
            "",
            "```text",
            "u = c_x + f_x · y_c / x_c",
            "v = c_y + f_y · z_c / x_c",
            "```",
            "",
            "相机位于机体前方0.5米。式中的 `f_x、f_y` 是像素焦距，`c_x、c_y` 是图像中心。若 `x_c≤0` 或预测点落在图像外，该候选直接排除。投影雅可比矩阵记为J，线索位置协方差投到像面后，与投影噪声和局部检测中心噪声相加：",
            "",
            "```text",
            "S = J P_pos J^T + R_projection + R_local",
            "d² = (z - z_hat)^T S^-1 (z - z_hat)",
            "```",
            "",
            f"![中心结果交接原理]({figure_links[3]})",
            "",
            "### 5.2 门控、代价矩阵和多帧确认",
            "",
            "上式中的 `z-z_hat` 是实际检测中心与预测像点的偏差，`S` 是这项偏差的允许范围。马氏距离 `d²` 会同时考虑横向、纵向误差及其协方差，比固定像素半径更适合处理新旧程度不同的线索。候选关系必须同时满足五个条件：局部检测框达到10像素；中心线索已经到达并处于有效期；预测点位于图像内；马氏距离平方不大于9.2103；有历史速度时，预测像面速度与局部像面速度差不大于80像素/秒。9.2103对应二维卡方分布约99%的门限，协方差大时允许更大的像素偏差，协方差小时门限自动收紧。",
            "",
            "通过门控的候选进入代价矩阵。若有S条中心线索、L条局部航迹，矩阵先建立S×L个真实候选，再为每条中心线索增加一个专用未匹配列，最终为S×(L+S)。合格候选的几何代价为 `C_geo=d²+(运动残差/80)²`。已经确认的中心线索若切换到其他局部航迹，增加4.0的切换代价；未匹配虚拟项的代价为12.0。匈牙利算法在整个矩阵上一次选择，避免两条中心线索同时抢占同一条机载航迹。代价不优于未匹配项的候选保持未注册，不强行绑定。",
            "",
            "一次矩阵求解只形成当帧选择。试验连续采集5帧，并保存每对关系最近3帧的选择记录；至少2帧选择同一关系后才正式确认。未达到条件的关系处于待确认状态，中心线索可以保持未匹配，机载局部航迹也可以保持未注册。该处理把偶然落入预测椭圆的目标挡在正式交接之前。",
            "",
            "图神经网络对照不扩大候选范围，只处理已经通过时间、像面和运动硬门控的白名单。网络输出候选为同一目标的概率 `P_gnn`，再按下式修正几何代价，之后仍使用同一匈牙利匹配和多帧确认：",
            "",
            "```text",
            "C_final = C_geo - 2 log(P_gnn)",
            "```",
            "",
            f"中心交接模型只使用合成数据训练，独立合成验证的边精度为{_ratio(center_validation['edge_precision'])}，召回率为{_ratio(center_validation['edge_recall'])}。AirSim seed 20260816是留出回放，没有参与训练。合成验证指标只说明模型学会了该合成分布，不能替代AirSim多seed检验。",
            "",
            f"![中心交接结果]({figure_links[4]})",
            "",
            _table_row(("场景", "方法", "正确绑定", "错误绑定", "绑定精度", "绑定召回率", "中位复算时间")),
            _table_row(("---", "---", "---:", "---:", "---:", "---:", "---:")),
        )
    )
    for run, geometry_result, gnn_result in zip(
        runs, center_geometry, center_gnn, strict=True
    ):
        for method, result in (("几何", geometry_result), ("图网络", gnn_result)):
            metrics = result["metrics"]
            lines.append(
                _table_row(
                    (
                        run.spec.label,
                        method,
                        metrics["true_binding_count"],
                        metrics["false_binding_count"],
                        _ratio(metrics["binding_precision"]),
                        _ratio(metrics["binding_recall"]),
                        f"{float(result['timing']['median_wall_duration_s']):.3f}秒",
                    )
                )
            )
    lines.extend(
        (
            "",
            "20目标/30机的绑定召回率低于20目标/8机，说明增加相机数量不会自动提高中心交接。三个专项在reset后独立采样，AirSim检测返回的局部航迹数量和连续性存在运行差异。40目标/50机的几何基线接受了1条落入预测区并连续通过门控的错误线索；图网络对照拒绝了该关系，同时保留31条正确绑定。单seed结果只证明该对照在这次回放中有效，尚不能说明它对其他目标几何和误差条件同样稳定。",
            "",
            "## 6. 拦截无人机之间的关联",
            "",
            "### 6.1 像点反投影和双视线交会",
            "",
            "每台机先在本相机内把匿名检测框串成局部短航迹。机间关联不直接比较局部编号，因为不同相机必然使用不同编号；它比较两条局部航迹在多个时刻是否能够形成同一条三维运动。第一步把检测框中心 `(u,v)` 通过相机内参反投影为相机坐标中的单位视线：",
            "",
            "```text",
            "d_c = normalize([1, (u-c_x)/f_x, (v-c_y)/f_y])",
            "d_n = normalize(R_n_c d_c)",
            "```",
            "",
            "`R_n_c`由每帧相机偏航、俯仰和横滚得到，`d_n`位于北东地坐标。两台相机的视线写成 `o_a+s d_a` 和 `o_b+t d_b`。算法求使两条视线距离最小的正深度 `s,t`，取两个最近点的中点作为该时刻的三角交会位置。两最近点距离是视线分离误差，两条视线夹角反映三角定位的几何强度。夹角太小时，即使像面误差很小，距离估计也会非常敏感。",
            "",
            "令 `δ=o_b-o_a`、`c=d_a·d_b`、`D=1-c²`。两条视线不平行时，最近点深度按下式计算：",
            "",
            "```text",
            "s = [δ·d_a - c(δ·d_b)] / D",
            "t = [c(δ·d_a) - δ·d_b] / D",
            "q_a = o_a + s d_a,  q_b = o_b + t d_b",
            "q_mid = (q_a + q_b)/2,  e_sep = ||q_a-q_b||",
            "```",
            "",
            f"![双视线交会]({figure_links[5]})",
            "",
            "不同相机的检测不要求完全同一时刻。算法先把两条局部航迹按时间排序，在0.16秒内插值或选取最近观测，得到成对样本。每一对样本按上式求一次视线交会；至少积累3个有效交会样本，再对交会中点随时间做直线拟合。拟合均方根误差用于判断这些点能否组成连续运动，分段方向与总方向的最大夹角用于排除运动方向明显矛盾的候选。单帧视线偶然靠近不能直接形成跨视角关系。",
            "",
            "### 6.2 几何门控与关系代价",
            "",
            _table_row(("检查项", "门限", "作用")),
            _table_row(("---", "---:", "---")),
            _table_row(("图像识别", "最长边≥10像素", "排除尺寸不足的检测")),
            _table_row(("时间对齐", "≤0.16秒", "限制插值和最近观测时间差")),
            _table_row(("航迹交接间隔", "≤0.65秒", "排除长时间未更新的局部航迹")),
            _table_row(("有效几何样本", "≥3个", "避免单帧偶然交会")),
            _table_row(("视线夹角", "≥0.35度", "排除近似平行视线")),
            _table_row(("视线分离", "≤2米", "要求两条视线在空间接近")),
            _table_row(("重投影误差", "≤8像素", "核对交会点回到两幅图像的位置")),
            _table_row(("运动拟合误差", "≤5米", "排除不连续的三维运动")),
            _table_row(("运动转角", "≤55度", "排除方向明显矛盾")),
            _table_row(("尺度对数差", "≤0.28", "核对框尺寸与估计距离是否相容")),
            "",
            "硬门控先回答候选是否具备基本物理可能性。通过后再计算相对好坏，几何代价由7项归一化误差加权得到：",
            "",
            "```text",
            "C_geo = 0.24C_sep + 0.20C_reproj + 0.10C_time",
            "      + 0.18C_motion + 0.12C_turn + 0.08C_scale + 0.08C_conf",
            "```",
            "",
            "`C_sep`衡量两条视线在空间中的分离，`C_reproj`衡量交会点投回两幅图像后的偏差，`C_time`衡量时间错位，`C_motion`和`C_turn`衡量三维运动连续性，`C_scale`核对检测框大小与距离变化，`C_conf`表示相机标定可信度。每项除以对应门限并封顶为3，代价越小越可能属于同一目标。几何基线直接使用 `C_geo`。图神经网络对照只在硬门控通过后计算同目标概率 `P_gnn`，并按下式融合，不允许网络放回几何已经拒绝的候选：",
            "",
            "```text",
            "C_final = 0.55 C_geo + 0.45(1 - P_gnn)",
            "```",
            "",
            "对每一对保留相机，算法以相机A的局部航迹为行、相机B的局部航迹为列建立代价矩阵，并给每条航迹增加代价1.05的未匹配选项。匈牙利算法在该相机对内做一一匹配，防止同一时刻一条航迹同时对应多个目标。最近3帧中至少2次选中同一关系后，关系才由待确认转为确认。",
            "",
            "确认关系随后合并为跨相机目标簇。目标簇可以理解为“多台相机对同一目标的局部航迹集合”。合并时执行三项约束：同一目标簇不允许出现同一相机的两条航迹；两个已经成熟的目标簇至少要有两个不同相机对共同支持才能合并；只有2帧的短航迹必须得到同一成熟簇内至少两台相机支持。几何和图网络只负责给出局部边，目标簇约束负责阻止一条错误边沿整个相机网络扩散。",
            "",
            f"跨视角模型只使用合成数据训练，独立合成验证的边精度为{_ratio(crossview_validation['edge_precision'])}，召回率为{_ratio(crossview_validation['edge_recall'])}。该指标用于确认模型和特征链路可运行，AirSim回放结果才用于判断它是否给现有几何方法带来增益。",
            "",
            "### 6.3 候选规模计算",
            "",
            "若直接让所有相机两两比较，候选数量会随相机数和局部航迹数快速增长。全相机策略在每个时刻比较所有活动相机对。若第i台相机有 `m_i` 条活动局部航迹，第j台有 `m_j` 条，单个时刻的候选数量近似为：",
            "",
            "```text",
            "E_frame = Σ(i<j) m_i m_j",
            "相机对数量 = M(M-1)/2",
            "```",
            "",
            "候选会在多个时刻随着航迹历史重新计算，因此最终记录数还要乘以有效时间步数。8、30、50台相机分别有28、435、1225个全量相机对。全相机策略用于压力诊断，不作为当前默认路径。",
            "",
            "责任区/视场稀疏策略把相机看作节点，把可能共同看到目标的相机对看作边。它在生成航迹候选前先筛相机对：同一搜索责任区的相机对直接保留；相邻责任区只有在某个共同观测帧内视锥重叠时才保留，计算视锥时增加5度余量；不相邻责任区直接排除。筛选只读取相机责任区、相机内参和观测计划中的姿态，不读取Actor名称或目标真值。这个步骤把明显没有共同观测条件的相机对挡在精细几何计算之前，再在保留边上执行时间对齐、双视线交会、代价矩阵和目标簇合并。",
            "",
            f"![相机对与候选规模]({figure_links[6]})",
            "",
            _table_row(("场景", "相机图", "方法", "保留相机对", "候选边", "正确", "错误", "漏配", "精度", "召回率", "身份混合", "复算时间/秒")),
            _table_row(("---", "---", "---", "---:", "---:", "---:", "---:", "---:", "---:", "---:", "---:", "---:")),
        )
    )
    for run_index, run in enumerate(runs):
        result_groups = (
            ("全相机", "几何", full_geometry[run_index]),
            ("全相机", "图网络", full_gnn[run_index]),
            ("责任区/视场稀疏", "几何", sparse_geometry[run_index]),
            ("责任区/视场稀疏", "图网络", sparse_gnn[run_index]),
        )
        for policy_label, method_label, result in result_groups:
            metrics = result["metrics"]
            audit = result["candidate_audit"]
            lines.append(
                _table_row(
                    (
                        run.spec.label,
                        policy_label,
                        method_label,
                        audit["camera_pair_retained_count"],
                        metrics["candidate_edge_count"],
                        metrics["true_positive_relations"],
                        metrics["false_positive_relations"],
                        metrics["false_negative_relations"],
                        _ratio(metrics["association_precision"]),
                        _ratio(metrics["association_recall"]),
                        metrics["id_switch_count"],
                        f"{float(result['timing']['median_wall_duration_s']):.2f}",
                    )
                )
            )

    lines.extend(
        (
            "",
            "20目标/8机中，四种方法都得到30条正确关系、0条错误关系和2条漏配，精度1.0000、召回率0.9375。稀疏策略仍把相机对从28组减到16组，候选边从5778条减到3296条，说明小规模质量不变时也能减少无效计算。",
            "",
            "20目标/30机中，稀疏几何相对全相机几何把错误关系从302条降到198条，精度从0.6488提高到0.7402。稀疏图网络进一步把错误关系降到142条、漏配降到58条，精度达到0.8008、召回率达到0.9078，身份混合由稀疏几何的4个降到2个。该规模下，稀疏相机图和学习评分都产生了可测增益。",
            "",
            "40目标/50机中，全相机几何有2537条错误关系和18个身份混合。全相机图网络虽将精度提高到0.6581，仍保留2094条错误关系和7个身份混合，不能解决全局候选过密问题。责任区/视场筛选把相机对从1225组降到403组，候选边从1,104,646条降到375,236条。稀疏几何得到4031条正确关系、16条错误关系、301条漏配，精度0.9960、召回率0.9305且身份混合为0。稀疏图网络的质量完全相同，复算时间由770.99秒增至812.96秒。",
            "",
            "关系精度按 `正确关系/(正确关系+错误关系)` 计算，召回率按 `正确关系/(正确关系+漏配关系)` 计算。一个目标簇内的跨相机成员会两两展开评分，因此正确与错误关系数可能大于直接确认边数。身份混合表示同一目标簇中出现多个离线真实目标，只在运行结束后统计。",
            "",
            f"![规模变化结果]({figure_links[7]})",
            "",
            "## 7. 结果判断",
            "",
            "### 7.1 搜索资源数量",
            "",
            "20目标/8机处于明确的容量不足状态。按当前3轮计划，24个分配槽无法覆盖28个搜索单元。其结果是4个单元未覆盖、1个目标虽达到10像素但未连续确认、1个中心漏检目标未补获。20目标/30机已经跨过单轮全覆盖门槛。继续增加相机主要带来复访机会，对首次覆盖的帮助有限。40目标/50机需要第二轮补齐6个单元，仍能完成全部目标确认。",
            "",
            "搜索规划耗时随矩阵扩大而增加。三组规划矩阵分别为8×36、30×58和50×106，矩阵元素规模约为288、1740和5300。平均规划耗时为2.758、11.739和35.753毫秒。该结果说明当前确定性搜索分配可以处理50机单次计算，但尚未包含通信排队、分布式状态更新和多seed最坏情况。",
            "",
            "### 7.2 中心交接稳定性",
            "",
            "三组中心线索精度和召回率完全相同，绑定结果没有随资源数量单调改善。几何基线在20目标/8机中绑定全部16条正确线索，在20目标/30机中漏掉2条正确绑定，在40目标/50机中漏1条并误接1条错误线索。中心交接图网络在前两组不改变结果，在40目标/50机中拒绝了这1条错误绑定。当前证据支持继续保留该学习对照，尚不支持替换几何白名单、匈牙利匹配和多帧确认。",
            "",
            "### 7.3 跨视角规模限制",
            "",
            "全相机策略在30机和50机规模下比较了大量没有共同观测条件的相机。几何门控虽然删除了多数候选，剩余伪关系仍会在目标簇内传递，形成身份混合。图神经网络直接用于全相机候选只能缓解问题，不能消除过密候选造成的错误连接。",
            "",
            "责任区/视场相机图已经实现，并在三组保存回放中完成对照。它是本轮质量和计算量改善的主要来源，尤其在40目标/50机中将精度提高到0.9960并消除身份混合。图神经网络只适合处理稀疏图中通过硬几何门控后仍有歧义的候选。20目标/30机出现增益，40目标/50机的稀疏几何已经接近满精度，图网络没有继续改善且增加运行时间。因此默认路径保持稀疏几何和匈牙利匹配，图网络继续作为离线可选比较项。",
            "",
            "## 8. 证据边界与后续工作",
            "",
            "1. 三组AirSim观测使用同一随机种子20260816，每个规模只有一次正式采集。图神经网络使用独立合成数据训练，seed 20260816完全留出，只用于离线回放。当前数字不能给出置信区间或设备级成功概率。",
            "2. 中心线索的精度80%、召回率80%和位置、速度误差由夹具固定生成。位置标准差为1米，速度标准差为0.2米/秒。本轮没有注入导航误差、云台姿态误差、时间同步偏差、相机标定漂移和检测误差。",
            "3. 识别输入是AirSim检测元数据。10像素规则只验证接口和关联门限，不能代表真实可见光或红外识别器的准确率。图网络的合成验证精度和召回率也不能当作真实探测条件下的指标。",
            "4. ComputerVision节点按指令改变位姿，不含飞行动力学。目标Actor按给定速度移动。本报告不评价拦截航迹、制导切换或5米物理拦截。",
            f"5. 离线基准共检查{len(acceptance_checks)}项，通过{acceptance_passed}项。唯一未通过项要求40目标/50机稀疏图网络相对稀疏几何再提高5个百分点；稀疏几何精度已经达到0.9960，图网络结果相同，因此没有满足额外增益条件。",
            "6. 报告中的复算时间包含关联计算、审计文件和结果图生成。20目标/8机重复5次，20目标/30机稀疏主路径重复3次；全相机压力组和40目标/50机只运行1次。40目标/50机的三个长时案例在同机不同逻辑核并发运行，时间不是独占处理器条件下的部署基准。",
            "7. 跨视角审计输出模式已经实现。它只保存候选阶段计数、拒绝原因和有界样本，避免再次写出百万级完整候选。批量多seed仍需控制回放规模和磁盘占用。",
            "",
            "## 9. 文件索引",
            "",
        )
    )
    for run in runs:
        lines.extend(
            (
                f"- {run.spec.label}总表：`{run.path.name}/campaign_summary.json`",
                f"- {run.spec.label}搜索指标：`{run.path.name}/search/metrics.json`",
                f"- {run.spec.label}中心交接指标：`{run.path.name}/center_handover/metrics.json`",
                f"- {run.spec.label}跨视角指标：`{run.path.name}/crossview/metrics.json`",
            )
        )
    lines.extend(
        (
            f"- 图表目录：`{DEFAULT_FIGURE_DIR}/`",
            "- 图网络离线基准总表：`gnn_offline_benchmark_20260816/benchmark_summary.json`",
            "- 图网络离线基准专项报告：`gnn_offline_benchmark_20260816/GNN_OFFLINE_BENCHMARK_REPORT_CN.md`",
            f"- 名义焦距计算：`f_x={focal_px:.1f}像素`，700米处3米目标约`{nominal_extent_px:.1f}像素`，10像素名义距离约`{nominal_ten_pixel_range_m:.0f}米`。",
            "",
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def generate(
    outputs_dir: Path,
    output_path: Path,
    figure_dir: Path,
    benchmark_summary_path: Path,
) -> Path:
    runs = tuple(load_evidence(outputs_dir, spec) for spec in RUN_SPECS)
    benchmark = load_benchmark(benchmark_summary_path)
    figures = build_figures(runs, benchmark, figure_dir)
    return build_report(runs, benchmark, output_path, figures)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    default_outputs = Path(__file__).resolve().parent / "outputs"
    parser.add_argument("--outputs-dir", type=Path, default=default_outputs)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--figure-dir", type=Path, default=None)
    parser.add_argument("--benchmark-summary", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = args.output or args.outputs_dir / DEFAULT_OUTPUT_NAME
    figure_dir = args.figure_dir or args.outputs_dir / DEFAULT_FIGURE_DIR
    benchmark_summary_path = (
        args.benchmark_summary
        or args.outputs_dir / DEFAULT_BENCHMARK_SUMMARY
    )
    generated = generate(
        args.outputs_dir,
        output_path,
        figure_dir,
        benchmark_summary_path,
    )
    print(generated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
