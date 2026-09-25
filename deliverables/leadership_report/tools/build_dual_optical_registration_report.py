#!/usr/bin/env python3
"""Build the dual-optical report directly from the 2026-08-19 replay evidence."""

from __future__ import annotations

from collections import defaultdict
import csv
import hashlib
import json
import math
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zipfile import ZipFile

import matplotlib

matplotlib.use("Agg")
warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from PIL import Image
from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_ROOT = REPO_ROOT / "deliverables" / "leadership_report"
REPORT_MD = REPORT_ROOT / "双光电多目标轨迹配准与交汇定位试验报告_CN.md"
REPORT_DOCX = REPORT_MD.with_suffix(".docx")
ASSET_DIR = REPORT_ROOT / "assets" / "dual_optical_registration_report"
EVIDENCE_MANIFEST = REPORT_ROOT / "双光电多目标轨迹配准与交汇定位试验报告_EVIDENCE.json"

MATRIX_ROOT = (
    REPO_ROOT
    / "research_modules"
    / "independent_experiments"
    / "dual_optical_online_benchmark"
    / "outputs"
    / "report_replay_20260819_v2"
)
MATRIX_COMPLETENESS = MATRIX_ROOT / "matrix_completeness.json"
MATRIX_SUMMARY = MATRIX_ROOT / "combined_summary.json"
MATRIX_FINAL_CASES = MATRIX_ROOT / "combined_final_case_metrics.csv"
MATRIX_REPRODUCTION = MATRIX_ROOT / "reproduction_manifest.json"
MATRIX_ROUND_FILES = {
    "oracle_360": MATRIX_ROOT / "oracle_360" / "round_metrics.csv",
    "continuous_360": MATRIX_ROOT / "continuous_360" / "round_metrics.csv",
    "s180": MATRIX_ROOT / "s180_derived" / "round_metrics.csv",
}

RANGING_ROOT = (
    REPO_ROOT
    / "research_modules"
    / "independent_experiments"
    / "dual_optical_40target"
    / "outputs"
    / "airsim_seed_20260810_run11"
)
RANGING_METRICS = RANGING_ROOT / "metrics.json"
RANGING_SCENARIO = RANGING_ROOT / "scenario.json"

TARGET_COUNTS = (20, 40, 60)
CONDITIONS = ("clean", "light", "medium", "heavy")
ROUTES = ("epipolar_mht", "gnn")
PROFILE_ORDER = ("oracle_360", "continuous_360", "s180")
DEADLINE_MS = 1000.0
ROUTE_LABELS_CN = {"epipolar_mht": "几何方法", "gnn": "图神经网络"}
CONDITION_LABELS_CN = {
    "clean": "无附加漏检虚警",
    "light": "轻度干扰",
    "medium": "中度干扰",
    "heavy": "重度干扰",
}
PROFILE_LABELS_CN = {
    "oracle_360": "360度理想单站",
    "continuous_360": "360度实际单站",
    "s180": "180度扇区扫描",
}

STATIC_FIGURE_NAMES = (
    "01_algorithm_flow.png",
    "02_single_station_tracking.png",
    "03_coplanarity_screening_3d.png",
    "04a_local_tracks_before_registration.png",
    "04b_candidate_graph_gnn_assignment.png",
    "05_multitime_triangulation_3d.png",
    "06_airsim_scene_40_targets_cn.png",
    "07_airsim_optical_observations_cn.png",
    "10_ranging_reconstruction_and_error.png",
)

FONT = "Noto Sans CJK SC"
FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
BLUE = "#245B78"
ORANGE = "#C96D2D"
GREEN = "#2E7D5A"
RED = "#A9473E"
INK = "#1F2933"
MUTED = "#65727E"
GRID = "#D7DEE5"

BODY_FONT = "宋体"
HEADING_FONT = "黑体"
LATIN_FONT = "Times New Roman"
WORD_BLUE = "1F4E78"
WORD_TEAL = "176B73"
WORD_INK = "202833"
WORD_MUTED = "5F6B78"

IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
INLINE_RE = re.compile(r"(\*\*.+?\*\*|`.+?`)")
TABLE_DIVIDER_RE = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+$")


def configure_matplotlib() -> None:
    if FONT_PATH.exists():
        font_manager.fontManager.addfont(str(FONT_PATH))
        configured = font_manager.FontProperties(fname=str(FONT_PATH)).get_name()
    else:
        configured = FONT
    matplotlib.rcParams.update(
        {
            "font.family": configured,
            "font.sans-serif": [configured, FONT, "Noto Sans CJK SC"],
            "axes.unicode_minus": False,
            "axes.edgecolor": MUTED,
            "axes.labelcolor": INK,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": INK,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def percentile_nearest_rank(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise RuntimeError("percentile requires values")
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _summary_key(row: Mapping[str, Any]) -> tuple[str, int, str, str]:
    return (
        str(row["profile"]),
        int(row["target_count"]),
        str(row["condition"]),
        str(row["route_name"]),
    )


def load_and_validate_matrix() -> dict[str, Any]:
    completeness = read_json(MATRIX_COMPLETENESS)
    expected_completeness = {
        "complete": True,
        "oracle_360_group_count": 6,
        "continuous_360_group_count": 24,
        "s180_group_count": 24,
        "total_group_count": 54,
        "seed_count_per_group": 5,
    }
    if completeness != expected_completeness:
        raise RuntimeError(f"matrix completeness changed: {completeness}")

    combined = read_json(MATRIX_SUMMARY)
    if (
        combined.get("run_id") != MATRIX_ROOT.name
        or combined.get("summary_window") != "last_revolution_or_last_round"
        or float(combined.get("deadline_ms", -1.0)) != DEADLINE_MS
        or combined.get("coverage_denominator") != "fixed_target_count"
        or combined.get("truth_used_online") is not False
        or combined.get("offline_truth_used_for_oracle_construction_and_scoring_only")
        is not True
    ):
        raise RuntimeError("combined summary contract changed")

    summary_rows = [dict(row) for row in combined["summary"]]
    if len(summary_rows) != 54:
        raise RuntimeError(f"expected 54 summary groups, found {len(summary_rows)}")
    expected_keys: set[tuple[str, int, str, str]] = set()
    for target_count in TARGET_COUNTS:
        for route in ROUTES:
            expected_keys.add(("oracle_360", target_count, "clean", route))
            for condition in CONDITIONS:
                expected_keys.add(("continuous_360", target_count, condition, route))
                expected_keys.add(("s180", target_count, condition, route))
    actual_keys = {_summary_key(row) for row in summary_rows}
    if actual_keys != expected_keys:
        raise RuntimeError(
            f"summary matrix keys changed: missing={sorted(expected_keys-actual_keys)}, "
            f"unexpected={sorted(actual_keys-expected_keys)}"
        )
    if {str(row["route_name"]) for row in summary_rows} != set(ROUTES):
        raise RuntimeError("report matrix contains an unsupported route")
    if any(int(row["sample_count"]) != 5 for row in summary_rows):
        raise RuntimeError("each summary group must contain five seeds")

    final_rows = read_csv(MATRIX_FINAL_CASES)
    if len(final_rows) != 270:
        raise RuntimeError(f"expected 270 final-case rows, found {len(final_rows)}")
    grouped: dict[tuple[str, int, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in final_rows:
        key = _summary_key(row)
        grouped[key].append(row)
        expected_round = 12 if row["profile"] == "s180" else 6
        if int(row["round_index"]) != expected_round:
            raise RuntimeError(f"non-final row in final-case file: {key}")
        deadline_met = float(row["latency_ms"]) <= DEADLINE_MS
        if (row["deadline_met"] == "True") != deadline_met:
            raise RuntimeError(f"deadline flag changed: {key}")
        if (row["timed_out"] == "True") == deadline_met:
            raise RuntimeError(f"timeout flag changed: {key}")
        offline_coverage = float(row["fixed_target_coverage"])
        expected_on_time = offline_coverage if deadline_met else 0.0
        if not math.isclose(
            float(row["on_time_fixed_target_coverage"]),
            expected_on_time,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise RuntimeError(f"on-time coverage policy changed: {key}")
        opportunity_count = int(row["single_station_identity_opportunity_count"])
        if opportunity_count != 2 * int(row["target_count"]):
            raise RuntimeError(f"single-station denominator changed: {key}")
        labeled = int(row["single_station_labeled_observation_count"])
        dominant = int(row["single_station_dominant_observation_count"])
        expected_precision = dominant / max(labeled, 1)
        expected_coverage = (
            int(row["single_station_correct_identity_count"]) / opportunity_count
        )
        if not math.isclose(
            float(row["single_station_precision"]), expected_precision, abs_tol=1.0e-12
        ) or not math.isclose(
            float(row["single_station_coverage"]), expected_coverage, abs_tol=1.0e-12
        ):
            raise RuntimeError(f"single-station metric formula changed: {key}")

    if set(grouped) != expected_keys or any(len(rows) != 5 for rows in grouped.values()):
        raise RuntimeError("final-case matrix is incomplete")

    summary_index = {_summary_key(row): row for row in summary_rows}
    for key, rows in grouped.items():
        summary = summary_index[key]
        output_count = sum(int(row["output_match_count"]) for row in rows)
        correct_count = sum(int(row["correct_match_count"]) for row in rows)
        correct_targets = sum(int(row["correct_unique_target_count"]) for row in rows)
        on_time_targets = sum(
            int(row["on_time_correct_unique_target_count"]) for row in rows
        )
        denominator = key[1] * len(rows)
        expected_values = {
            "offline_completed_precision": correct_count / output_count
            if output_count
            else None,
            "offline_completed_coverage": correct_targets / denominator,
            "on_time_coverage": on_time_targets / denominator,
            "latency_p95_ms": percentile_nearest_rank(
                [float(row["latency_ms"]) for row in rows], 0.95
            ),
            "timeout_count": sum(row["timed_out"] == "True" for row in rows),
        }
        for field, expected in expected_values.items():
            actual = summary[field]
            if expected is None and actual is None:
                continue
            if expected is None or actual is None or not math.isclose(
                float(actual), float(expected), rel_tol=0.0, abs_tol=1.0e-12
            ):
                raise RuntimeError(f"aggregate metric changed: {key}, {field}")

    round_expectations = {
        "oracle_360": (6, 30, 180),
        "continuous_360": (6, 120, 720),
        "s180": (12, 120, 1440),
    }
    for profile, path in MATRIX_ROUND_FILES.items():
        rows = read_csv(path)
        rounds, sequence_count, row_count = round_expectations[profile]
        if len(rows) != row_count:
            raise RuntimeError(f"unexpected row count in {path}: {len(rows)}")
        sequences: dict[tuple[str, str, str, str, str], list[int]] = defaultdict(list)
        for row in rows:
            key = (
                row["profile"],
                row["target_count"],
                row["seed"],
                row["condition"],
                row["route_name"],
            )
            sequences[key].append(int(row["round_index"]))
        if len(sequences) != sequence_count or any(
            sorted(values) != list(range(1, rounds + 1))
            for values in sequences.values()
        ):
            raise RuntimeError(f"incomplete round sequence in {path}")

    reproduction = read_json(MATRIX_REPRODUCTION)
    if (
        reproduction.get("experiment_id") != MATRIX_ROOT.name
        or reproduction.get("status") != "diagnostic_offline_replay"
        or reproduction["metrics_contract"].get("timeout_policy")
        != "quality retained after 1000 ms; late result contributes zero to on-time coverage"
    ):
        raise RuntimeError("reproduction manifest contract changed")
    for item in reproduction["inputs"]:
        path = Path(str(item["path"]))
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file() or sha256(path) != str(item["sha256"]):
            raise RuntimeError(f"reproduction input hash mismatch: {path}")

    correlations = [dict(row) for row in combined["correlations"]]
    if len(correlations) != 4 or any(int(row["case_count"]) != 60 for row in correlations):
        raise RuntimeError("correlation evidence changed")
    return {
        "completeness": completeness,
        "combined": combined,
        "summary_rows": summary_rows,
        "summary_index": summary_index,
        "final_rows": final_rows,
        "reproduction": reproduction,
        "correlations": correlations,
    }


def load_ranging_demonstration() -> dict[str, Any]:
    metrics = read_json(RANGING_METRICS)
    scenario = read_json(RANGING_SCENARIO)
    if (
        int(metrics.get("target_count", -1)) != 40
        or int(metrics.get("seed", -1)) != 20260810
        or int(metrics.get("online_truth_leakage_count", -1)) != 0
    ):
        raise RuntimeError("ranging demonstration contract changed")
    return {"metrics": metrics, "scenario": scenario}


def save_figure(figure: plt.Figure, name: str) -> Path:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    path = ASSET_DIR / name
    figure.savefig(path, dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return path


def _summary_rows(
    evidence: Mapping[str, Any], profile: str
) -> list[dict[str, Any]]:
    return [
        row for row in evidence["summary_rows"] if str(row["profile"]) == profile
    ]


def figure_oracle_matrix(evidence: Mapping[str, Any]) -> Path:
    rows = _summary_rows(evidence, "oracle_360")
    index = {(int(row["target_count"]), str(row["route_name"])): row for row in rows}
    figure, axes = plt.subplots(1, 2, figsize=(14.2, 5.3))
    x = np.arange(len(TARGET_COUNTS))
    width = 0.36
    for offset, route, color in ((-width / 2, "epipolar_mht", BLUE), (width / 2, "gnn", GREEN)):
        precision = [100.0 * float(index[(count, route)]["offline_completed_precision"]) for count in TARGET_COUNTS]
        coverage = [100.0 * float(index[(count, route)]["offline_completed_coverage"]) for count in TARGET_COUNTS]
        bars = axes[0].bar(
            x + offset,
            coverage,
            width,
            color=color,
            label=f"{ROUTE_LABELS_CN[route]}覆盖度",
            alpha=0.9,
        )
        axes[0].plot(x + offset, precision, "o", color=INK, markersize=4)
        for bar, value in zip(bars, coverage):
            axes[0].text(bar.get_x() + bar.get_width() / 2, value + 1.0, f"{value:.1f}", ha="center", fontsize=9)
    axes[0].set_title("离线完成质量（圆点为精度）", fontsize=14, fontweight="bold")
    axes[0].set_xticks(x, [f"{count}目标" for count in TARGET_COUNTS])
    axes[0].set_ylim(0, 108)
    axes[0].set_ylabel("比例 / %")
    axes[0].grid(axis="y", color=GRID, linewidth=0.8)
    axes[0].legend(frameon=False, fontsize=9)

    for offset, route, color in ((-width / 2, "epipolar_mht", BLUE), (width / 2, "gnn", GREEN)):
        latency = [float(index[(count, route)]["latency_p95_ms"]) for count in TARGET_COUNTS]
        bars = axes[1].bar(x + offset, latency, width, color=color, label=ROUTE_LABELS_CN[route], alpha=0.9)
        for bar, value in zip(bars, latency):
            axes[1].text(bar.get_x() + bar.get_width() / 2, value * 1.05, f"{value:.0f}", ha="center", fontsize=9)
    axes[1].axhline(DEADLINE_MS, color=RED, linestyle="--", linewidth=1.5, label="1000毫秒期限")
    axes[1].set_yscale("log")
    axes[1].set_title("最后一圈处理耗时P95", fontsize=14, fontweight="bold")
    axes[1].set_xticks(x, [f"{count}目标" for count in TARGET_COUNTS])
    axes[1].set_ylabel("毫秒（对数刻度）")
    axes[1].grid(axis="y", color=GRID, linewidth=0.8)
    axes[1].legend(frameon=False, fontsize=9)
    figure.suptitle("360度理想单站条件下的双站配准", fontsize=18, fontweight="bold")
    figure.tight_layout()
    return save_figure(figure, "13_v2_oracle_quality_timing.png")


def _heatmap(
    axis: Any,
    values: np.ndarray,
    *,
    title: str,
    vmin: float = 0.0,
    vmax: float = 100.0,
) -> None:
    image = axis.imshow(values, vmin=vmin, vmax=vmax, cmap="YlGnBu", aspect="auto")
    axis.set_xticks(np.arange(len(CONDITIONS)), [CONDITION_LABELS_CN[value].replace("无附加漏检虚警", "无附加") for value in CONDITIONS])
    axis.set_yticks(np.arange(len(TARGET_COUNTS)), [f"{value}目标" for value in TARGET_COUNTS])
    axis.set_title(title, fontsize=13, fontweight="bold")
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            color = "white" if values[row, column] >= 62 else INK
            axis.text(column, row, f"{values[row, column]:.1f}%", ha="center", va="center", fontsize=9, color=color)
    plt.colorbar(image, ax=axis, fraction=0.046, pad=0.04)


def figure_single_station(evidence: Mapping[str, Any], profile: str, name: str) -> Path:
    rows = _summary_rows(evidence, profile)
    index = {
        (int(row["target_count"]), str(row["condition"])): row
        for row in rows
        if str(row["route_name"]) == "gnn"
    }
    precision = np.asarray(
        [[100.0 * float(index[(count, condition)]["single_station_precision"]) for condition in CONDITIONS] for count in TARGET_COUNTS]
    )
    coverage = np.asarray(
        [[100.0 * float(index[(count, condition)]["single_station_coverage"]) for condition in CONDITIONS] for count in TARGET_COUNTS]
    )
    figure, axes = plt.subplots(1, 2, figsize=(14.0, 4.8))
    _heatmap(axes[0], precision, title="单站航迹精度")
    _heatmap(axes[1], coverage, title="单站航迹覆盖度")
    figure.suptitle(f"{PROFILE_LABELS_CN[profile]}的单站航迹输入", fontsize=18, fontweight="bold")
    figure.tight_layout()
    return save_figure(figure, name)


def figure_dual_matrix(evidence: Mapping[str, Any], profile: str, name: str) -> Path:
    rows = _summary_rows(evidence, profile)
    index = {
        (int(row["target_count"]), str(row["condition"]), str(row["route_name"])): row
        for row in rows
    }
    figure, axes = plt.subplots(2, 3, figsize=(15.6, 8.2), sharey=True)
    x = np.arange(len(CONDITIONS))
    width = 0.36
    for column, count in enumerate(TARGET_COUNTS):
        for row_index, metric in enumerate(("offline_completed_precision", "offline_completed_coverage")):
            axis = axes[row_index, column]
            for offset, route, color in ((-width / 2, "epipolar_mht", BLUE), (width / 2, "gnn", GREEN)):
                values = [100.0 * float(index[(count, condition, route)][metric]) for condition in CONDITIONS]
                axis.bar(x + offset, values, width, color=color, label=ROUTE_LABELS_CN[route], alpha=0.9)
            axis.set_xticks(x, ["无附加", "轻度", "中度", "重度"])
            axis.set_ylim(0, 105)
            axis.grid(axis="y", color=GRID, linewidth=0.8)
            axis.set_title(f"{count}目标 - {'精度' if row_index == 0 else '覆盖度'}", fontsize=12.5, fontweight="bold")
            if column == 0:
                axis.set_ylabel("比例 / %")
            if row_index == 0 and column == 2:
                axis.legend(frameon=False, loc="lower left", fontsize=9)
    window_label = "最后一圈" if profile == "continuous_360" else "最后一轮"
    figure.suptitle(
        f"{PROFILE_LABELS_CN[profile]}{window_label}离线完成质量",
        fontsize=18,
        fontweight="bold",
    )
    figure.tight_layout()
    return save_figure(figure, name)


def figure_latency(evidence: Mapping[str, Any]) -> Path:
    rows = evidence["summary_rows"]
    figure, axes = plt.subplots(1, 3, figsize=(15.4, 4.9), sharey=True)
    for axis, profile in zip(axes, PROFILE_ORDER):
        profile_rows = [row for row in rows if row["profile"] == profile]
        x = np.arange(len(TARGET_COUNTS))
        width = 0.32
        for offset, route, color in ((-width / 2, "epipolar_mht", BLUE), (width / 2, "gnn", GREEN)):
            values = []
            lows = []
            highs = []
            for count in TARGET_COUNTS:
                subset = [float(row["latency_p95_ms"]) for row in profile_rows if int(row["target_count"]) == count and row["route_name"] == route]
                values.append(float(np.median(subset)))
                lows.append(values[-1] - min(subset))
                highs.append(max(subset) - values[-1])
            axis.errorbar(
                x + offset,
                values,
                yerr=np.asarray([lows, highs]),
                fmt="o",
                capsize=4,
                linewidth=1.8,
                color=color,
                label=ROUTE_LABELS_CN[route],
            )
        axis.axhline(DEADLINE_MS, color=RED, linestyle="--", linewidth=1.3)
        axis.set_yscale("log")
        axis.set_xticks(x, [str(value) for value in TARGET_COUNTS])
        axis.set_title(PROFILE_LABELS_CN[profile], fontsize=13, fontweight="bold")
        axis.grid(axis="y", color=GRID, linewidth=0.8)
        axis.set_xlabel("目标数量")
    axes[0].set_ylabel("最后窗口P95耗时 / 毫秒（对数刻度）")
    axes[2].legend(frameon=False, fontsize=9)
    figure.suptitle("质量结果与1000毫秒时限分开判读", fontsize=18, fontweight="bold")
    figure.tight_layout()
    return save_figure(figure, "17_v2_latency_deadline.png")


def figure_local_dual_correlation(evidence: Mapping[str, Any]) -> Path:
    final_rows = evidence["final_rows"]
    figure, axes = plt.subplots(1, 2, figsize=(13.8, 5.2), sharex=True, sharey=True)
    colors = {"epipolar_mht": BLUE, "gnn": GREEN}
    markers = {"continuous_360": "o", "s180": "s"}
    correlation_index = {
        (row["profile"], row["route_name"]): row
        for row in evidence["correlations"]
    }
    for axis, profile in zip(axes, ("continuous_360", "s180")):
        for route in ROUTES:
            subset = [row for row in final_rows if row["profile"] == profile and row["route_name"] == route]
            x = [100.0 * float(row["single_station_coverage"]) for row in subset]
            y = [100.0 * float(row["fixed_target_coverage"]) for row in subset]
            corr = correlation_index[(profile, route)]["single_station_coverage_vs_dual_coverage_pearson"]
            axis.scatter(
                x,
                y,
                s=28,
                alpha=0.72,
                marker=markers[profile],
                color=colors[route],
                label=f"{ROUTE_LABELS_CN[route]} 相关系数{float(corr):.2f}",
            )
        axis.plot([0, 100], [0, 100], linestyle="--", color=GRID, linewidth=1.2)
        axis.set_title(PROFILE_LABELS_CN[profile], fontsize=13.5, fontweight="bold")
        axis.set_xlabel("单站航迹覆盖度 / %")
        axis.grid(color=GRID, linewidth=0.7)
        axis.legend(frameon=False, fontsize=9)
    axes[0].set_ylabel("双站正确配准覆盖度 / %")
    axes[0].set_xlim(45, 102)
    axes[0].set_ylim(0, 102)
    figure.suptitle("单站航迹覆盖度与双站配准覆盖度", fontsize=18, fontweight="bold")
    figure.tight_layout()
    return save_figure(figure, "18_v2_local_dual_correlation.png")


def generate_figures(evidence: Mapping[str, Any]) -> list[Path]:
    configure_matplotlib()
    static = [ASSET_DIR / name for name in STATIC_FIGURE_NAMES]
    missing = [path for path in static if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"supporting figure missing: {missing}")
    generated = [
        figure_oracle_matrix(evidence),
        figure_single_station(evidence, "continuous_360", "14_v2_continuous_single_station.png"),
        figure_dual_matrix(evidence, "continuous_360", "15_v2_continuous_dual_matrix.png"),
        figure_single_station(evidence, "s180", "16_v2_s180_single_station.png"),
        figure_dual_matrix(evidence, "s180", "16b_v2_s180_dual_matrix.png"),
        figure_latency(evidence),
        figure_local_dual_correlation(evidence),
    ]
    return static + generated


def percent_text(value: Any) -> str:
    if value is None:
        return "无输出"
    return f"{100.0 * float(value):.1f}%"


def latency_text(value: Any) -> str:
    return f"{float(value):.1f}毫秒"


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    lines = [
        "| " + " | ".join(str(value) for value in headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _single_station_table_rows(evidence: Mapping[str, Any], profile: str) -> list[list[str]]:
    rows = _summary_rows(evidence, profile)
    index = {
        (int(row["target_count"]), str(row["condition"])): row
        for row in rows
        if row["route_name"] == "gnn"
    }
    output = []
    for count in TARGET_COUNTS:
        for condition in CONDITIONS:
            row = index[(count, condition)]
            output.append(
                [
                    str(count),
                    CONDITION_LABELS_CN[condition],
                    percent_text(row["single_station_precision"]),
                    percent_text(row["single_station_coverage"]),
                    str(row["single_station_duplicate_track_count"]),
                    str(row["single_station_mixed_track_count"]),
                    str(row["single_station_missing_identity_count"]),
                ]
            )
    return output


def _dual_table_rows(evidence: Mapping[str, Any], profile: str) -> list[list[str]]:
    rows = sorted(
        _summary_rows(evidence, profile),
        key=lambda row: (
            int(row["target_count"]),
            CONDITIONS.index(str(row["condition"])),
            ROUTES.index(str(row["route_name"])),
        ),
    )
    return [
        [
            str(row["target_count"]),
            CONDITION_LABELS_CN[str(row["condition"])],
            ROUTE_LABELS_CN[str(row["route_name"])],
            percent_text(row["offline_completed_precision"]),
            percent_text(row["offline_completed_coverage"]),
            percent_text(row["on_time_coverage"]),
            latency_text(row["latency_p95_ms"]),
            f"{int(row['timeout_count'])}/5",
        ]
        for row in rows
    ]


def build_markdown(evidence: Mapping[str, Any], ranging: Mapping[str, Any]) -> None:
    oracle_rows = sorted(
        _summary_rows(evidence, "oracle_360"),
        key=lambda row: (int(row["target_count"]), ROUTES.index(str(row["route_name"]))),
    )
    oracle_table = markdown_table(
        ("目标数", "方法", "质量精度", "质量覆盖度", "按时覆盖度", "处理耗时P95", "超时数"),
        (
            (
                row["target_count"],
                ROUTE_LABELS_CN[str(row["route_name"])],
                percent_text(row["offline_completed_precision"]),
                percent_text(row["offline_completed_coverage"]),
                percent_text(row["on_time_coverage"]),
                latency_text(row["latency_p95_ms"]),
                f"{int(row['timeout_count'])}/5",
            )
            for row in oracle_rows
        ),
    )
    single_360_table = markdown_table(
        ("目标数", "干扰条件", "单站精度", "单站覆盖度", "重复航迹", "混合航迹", "缺失身份机会"),
        _single_station_table_rows(evidence, "continuous_360"),
    )
    dual_360_table = markdown_table(
        ("目标数", "干扰条件", "方法", "质量精度", "质量覆盖度", "按时覆盖度", "处理耗时P95", "超时数"),
        _dual_table_rows(evidence, "continuous_360"),
    )
    single_s180_table = markdown_table(
        ("目标数", "干扰条件", "单站精度", "单站覆盖度", "重复航迹", "混合航迹", "缺失身份机会"),
        _single_station_table_rows(evidence, "s180"),
    )
    dual_s180_table = markdown_table(
        ("目标数", "干扰条件", "方法", "质量精度", "质量覆盖度", "按时覆盖度", "处理耗时P95", "超时数"),
        _dual_table_rows(evidence, "s180"),
    )

    summary = evidence["summary_index"]
    clean_losses = []
    for count in TARGET_COUNTS:
        for route in ROUTES:
            ideal = float(summary[("oracle_360", count, "clean", route)]["offline_completed_coverage"])
            actual = float(summary[("continuous_360", count, "clean", route)]["offline_completed_coverage"])
            clean_losses.append(
                f"{count}目标{ROUTE_LABELS_CN[route]}由{ideal*100:.1f}%降至{actual*100:.1f}%"
            )
    correlations = {
        (row["profile"], row["route_name"]): row
        for row in evidence["correlations"]
    }
    metrics = ranging["metrics"]

    report = f"""# 双光电多目标轨迹配准与交汇定位试验报告

本报告说明两台周扫光电如何把各自形成的局部航迹配成同一目标，并在关系稳定后进行交汇定位。核心结论有两点。第一，双站配准在理想单站输入下可以工作，60目标图神经网络最后一圈达到99.3%的关系精度和98.7%的目标覆盖度。第二，实际链路的主要损失发生在单站成轨阶段；航迹断裂、错误重接和重复建轨先减少了可供双站比较的正确对象。

本次结果全部来自`report_replay_20260819_v2`确定性离线复算。矩阵包括360度理想单站6组、360度实际单站24组和180度扫描24组，每组5个测试场景。报告只统计最后一圈或最后一轮，不合并前期过渡数据。算法质量和1000毫秒处理时限分别列示，超时结果保留离线质量，但按时覆盖度记为0。

## 一、算法原理

### 1.1 处理流程

两台光电先分别完成检测和单站成轨。系统按照图像拍摄时刻校正设备位置、安装关系和云台姿态，把检测框中心转换为空间视线。随后用双站共面关系缩小候选范围，再由几何方法或图神经网络比较多时刻运动是否一致。候选评分完成后执行一一分配，同一条航迹不能重复分给多个对象。关系连续稳定后，双站视线进入交汇定位。

![双光电多目标轨迹配准与交汇定位流程](assets/dual_optical_registration_report/01_algorithm_flow.png)

配准和定位是前后两步。配准回答“两台光电看到的是否为同一目标”，定位回答“这个目标在哪里、向哪里运动”。配准关系不稳定时不输出定位结果，避免把两条不相关视线强行交会。

### 1.2 单站航迹

窄视场周扫时，目标每圈只在短时间内进入画面。连续检测先合并成一次扫描片段，下一圈重访时再根据方位、俯仰、角速度、时间间隔和预测误差恢复原航迹。短时漏检期间保留滑行或休眠状态；目标交叉且关系不清时，局部保留少量候选，等待后续观测消解。

![单站检测点形成连续航迹及断轨风险](assets/dual_optical_registration_report/02_single_station_tracking.png)

单站阶段一旦把一个目标拆成多条航迹，双站算法面对的就不再是一目标一航迹。若两目标被错误接成一条航迹，后续多时刻几何关系也会被污染。双站算法可以拒绝部分错误关系，无法恢复已经丢失的正确航迹。

### 1.3 共面筛选

相机内参、设备位置和拍摄时刻姿态已知时，检测框中心可以转换为空间单位视线。同一时刻指向同一目标的两条视线与两站基线应近似处于同一平面。系统计算归一化共面残差，并按时间差、姿态误差和航迹协方差调整门限。明显不符合双站几何关系的组合直接剔除。

![双站视线的三维共面筛选](assets/dual_optical_registration_report/03_coplanarity_screening_3d.png)

共面筛选只负责缩小比较范围。目标密集、运动方向接近时，多组航迹可能同时满足门限，还要继续比较多圈运动和周边竞争关系。

### 1.4 图神经网络配准

候选关系组成一个两侧航迹图。左侧节点是A站航迹，右侧节点是B站航迹，通过共面筛选的组合形成连线。节点保存方向、角速度、航迹年龄和不确定度；连线保存多时刻共面残差、时间差、运动一致性和交汇稳定性。图神经网络同时查看一条候选及其周边竞争候选，输出关系分数。

![双站局部航迹对应关系待确定](assets/dual_optical_registration_report/04a_local_tracks_before_registration.png)

![候选关系经图神经网络评分和一一分配后收敛](assets/dual_optical_registration_report/04b_candidate_graph_gnn_assignment.png)

图神经网络不直接发布身份。关系分数进入带空缺项的一一分配，低可信候选可以保持未匹配。输出还要经过连续多圈确认。共面门限、一一约束和连续确认均保持为确定性边界。

### 1.5 几何方法

几何方法把多时刻共面残差、运动方向差、角速度差和交汇稳定性按冻结权重形成总代价，再使用匈牙利算法求一一对应关系。该方法容易解释，也可作为学习方法不可用时的对照路线。本轮复算没有按测试结果重新调整门限。

几何方法和图神经网络使用同一批匿名单站航迹。两者的差别位于候选关系评分，前面的单站成轨和共面筛选保持一致。因此，两条路线出现相同的单站精度和单站覆盖度是预期结果。

### 1.6 交汇定位

双站关系确认后，系统把相邻时刻的两条视线配对。存在离散采样和小幅误差时，两条视线通常不严格相交，取最近点连线的中点作为位置。多个时刻的位置再进行短时运动拟合，得到速度和拟合残差。交会角过小、最近点距离过大或结果跳变时，定位结果保持待确认。

![多时刻双射线交汇定位原理](assets/dual_optical_registration_report/05_multitime_triangulation_3d.png)

## 二、试验配置

### 2.1 场景与设备

{markdown_table(
    ("项目", "设置"),
    (
        ("光电布置", "两台固定光电，横向基线2千米，高度均为100米"),
        ("相机", "1280×1024，等效焦距300毫米，水平视场2.93度，垂直视场约2.344度"),
        ("角分辨率", "标称0.05毫弧度，按图像尺寸折算约0.03995毫弧度/像素"),
        ("采样与仿真速度", "检测和云台记录100赫兹，AirSim ClockSpeed为0.1"),
        ("目标", "20、40、60个长度3米的无人机网格Actor，速度50米/秒"),
        ("运动方向", "每个场景一半沿0度方向，一半沿负30度方向；初始前后位置和交叉关系随seed变化"),
        ("360度扫描", "2秒连续周扫一圈，12秒共6圈，第6圈计入汇总"),
        ("180度扫描", "1秒单程扫过180度，2秒完成往返，12秒形成12轮，第12轮计入汇总"),
        ("云台误差", "两种扫描均保留0.4毫弧度固定偏差和0.3毫弧度逐帧随机抖动"),
        ("测试数量", "每个目标规模、干扰等级和方法均为5个测试seed"),
    ),
)}

目标并非排成规则矩形。不同seed改变目标的前后间隔和横向位置，两类航向在观察区内形成平移、接近和局部交叉。该设置用于检查多方向目标同时出现时的成轨与配准，不把规则队形作为算法先验。

![两台固定光电与多方向运动目标](assets/dual_optical_registration_report/06_airsim_scene_40_targets_cn.png)

仿真检测采用AirSim检测函数输出匿名框。图中只展示检测框位置和两站同一时刻看到的目标子集，不把Actor名称送入在线配准。两站视场不同，不能直接按图像左右位置对应，必须先转换为空间视线并形成局部航迹。

![仿真检测函数形成的两站匿名检测框示意](assets/dual_optical_registration_report/07_airsim_optical_observations_cn.png)

### 2.2 干扰设置

{markdown_table(
    ("等级", "随机漏检率", "每台每秒瞬时虚警", "每台持续虚假航迹"),
    (
        ("无附加漏检虚警", "0", "0", "0"),
        ("轻度干扰", "3%", "2个", "0"),
        ("中度干扰", "7%", "4个", "1条"),
        ("重度干扰", "12%", "8个", "2条"),
    ),
)}

四档条件均保留相同的云台固定偏差和随机抖动。“无附加漏检虚警”只表示没有额外注入漏检和虚警，不代表无云台误差。180度中、重度条件由封存匿名观测按照固定策略确定性生成，属于离线干扰复算，不是AirSim重新运行。

### 2.3 评价口径

{markdown_table(
    ("指标", "计算方法", "用途"),
    (
        ("单站精度", "两站各航迹的主导真实观测数÷全部有标签观测数", "判断局部航迹是否混入其他目标或虚警"),
        ("单站覆盖度", "身份正确的单站航迹数÷两站目标机会总数", "判断每个真实目标是否在两站形成可用局部航迹"),
        ("质量精度", "正确双站关系数÷全部已输出双站关系数", "评价离线完成结果中有多少关系正确"),
        ("质量覆盖度", "正确配准目标数÷目标总数", "评价离线完成结果覆盖了多少目标"),
        ("按时覆盖度", "1000毫秒内正确配准目标数÷目标总数", "评价处理时限内可用的目标比例"),
        ("处理耗时P95", "5个seed最后窗口耗时的最近秩95%分位", "检查1000毫秒期限"),
    ),
)}

360度只统计第6圈，180度只统计第12轮。单站结果按目标数量和干扰等级统计，与后续使用哪种跨站评分方法无关。超过1000毫秒后形成的关系仍用于分析算法质量，但不计入按时覆盖度。真实身份只在离线评分和理想单站诊断中使用，在线算法输入不含真实身份。

## 三、试验结果

### 3.1 360度理想单站条件

理想单站诊断按离线真实身份把每个目标在每台光电的观测归成一条航迹，单站精度和覆盖度均为100%。旧记录在扫描边界可能把同一目标同一圈分成两个短片段，复算只保留真实观测数最多的主片段，并记录舍弃数量；没有补造检测、位置或视线。该组用于隔离检查双站算法，不代表实际单站航迹器已经达到完全正确。

{oracle_table}

![360度理想单站条件下的质量与耗时](assets/dual_optical_registration_report/13_v2_oracle_quality_timing.png)

六组都形成了有效双站关系，说明共面筛选、候选评分、一一分配和连续确认在20至60目标范围内可以贯通。两种方法没有在全部规模上形成一致的质量排序：20目标几何方法覆盖度93.0%，高于图神经网络的82.0%；40目标分别为87.5%和79.5%；60目标图神经网络达到98.7%，高于几何方法的84.0%。

时效差异较明确。几何方法六组中的每个seed都超过1000毫秒，因此按时覆盖度为0；图神经网络六组全部按时，P95为70.9至332.0毫秒。几何方法的质量精度和质量覆盖度是超时后离线完成值，不能解释为按时在线能力。

### 3.2 360度实际单站航迹

#### 3.2.1 试验口径

实际单站复算直接使用封存的匿名局部航迹，不根据离线真实身份修复断轨、错误重接或重复建轨。20、40、60目标分别运行四档干扰和两种跨站方法，共24组，每组5个seed。两种方法读取同一单站输入。20目标沿用本规模冻结配置；40和60目标的几何方法使用既有跨规模冻结参数，属于离线诊断，不代表该参数已经完成本规模标定。

#### 3.2.2 单站航迹结果

{single_360_table}

![360度实际单站航迹精度和覆盖度](assets/dual_optical_registration_report/14_v2_continuous_single_station.png)

目标数量和干扰增加后，单站覆盖度整体下降。无附加漏检虚警时，覆盖度从20目标的91.5%降至40目标的80.2%和60目标的73.2%。重度干扰下分别为78.5%、67.2%和63.2%。混合航迹和缺失身份机会随规模增加，说明主要损失已经在跨站评分前发生。

“重复航迹”只统计同一相机内一个真实目标同时对应多条合格局部航迹的超出部分。“混合航迹”表示一条局部航迹内没有达到85%主导身份纯度。“缺失身份机会”表示在两站目标机会总数中没有形成合格局部航迹的数量。表中数量为5个seed最后一圈的合计。

#### 3.2.3 双站配准结果

{dual_360_table}

![360度实际单站条件下两种方法的最终质量](assets/dual_optical_registration_report/15_v2_continuous_dual_matrix.png)

几何方法在24组实际复算中的12组全部超过1000毫秒，图神经网络12组全部按时。离线完成质量没有出现单一方法全面占优。20目标四档条件下，几何方法的质量覆盖度均高于图神经网络；40目标无附加、轻度条件下图神经网络较高，中度相同，重度条件几何方法较高；60目标两种方法随干扰等级交替占优。

理想单站与实际单站的同规模无附加漏检虚警对照为：{'；'.join(clean_losses)}。这组差值没有改变跨站模型和目标总数，主要变化是局部航迹从一目标一航迹变为实际断轨、混合和缺失状态。

按60个最终案例计算，单站覆盖度与双站覆盖度的相关系数为：几何方法{float(correlations[('continuous_360', 'epipolar_mht')]['single_station_coverage_vs_dual_coverage_pearson']):.3f}，图神经网络{float(correlations[('continuous_360', 'gnn')]['single_station_coverage_vs_dual_coverage_pearson']):.3f}。几何路线受前级覆盖限制更直接；图神经网络还存在候选评分和连续确认造成的独立损失。两条路线都不能恢复前级没有形成的正确航迹。

### 3.3 180度扫描

180度方案把目标来袭扇区作为已知范围，云台1秒扫过180度后反向返回。12秒内形成12个关联轮次，最后统计第12轮。无附加和轻度条件来自封存观测；中度和重度在同一匿名观测上按固定漏检、虚警策略进行离线干扰复算。

#### 3.3.1 单站航迹结果

{single_s180_table}

![180度扫描的单站航迹精度和覆盖度](assets/dual_optical_registration_report/16_v2_s180_single_station.png)

180度扫描提高了目标方向的重访频率。20目标四档条件的单站覆盖度为99.0%至100.0%；40目标为92.8%至95.8%；60目标为89.0%至92.8%。与360度实际单站相比，覆盖度明显提高，但40和60目标仍存在混合航迹和缺失身份机会。

#### 3.3.2 双站配准结果

{dual_s180_table}

![180度扫描条件下两种方法的最终质量](assets/dual_optical_registration_report/16b_v2_s180_dual_matrix.png)

几何方法12组全部超时，图神经网络12组全部按时。几何方法的离线质量在20目标四档条件下较高，质量覆盖度为84.0%至95.0%；图神经网络为61.0%至89.0%。40目标两种方法接近，60目标图神经网络在无附加和轻度条件下覆盖更高，在重度条件下相同。

扇区扫描改善了单站重访，不等于跨站关系自动正确。20目标中度干扰下，单站覆盖度仍为100.0%，图神经网络双站覆盖度只有61.0%，说明该场景的剩余损失位于跨站评分和连续确认。60目标无附加条件下，图神经网络覆盖度为81.0%，比360度实际单站的41.7%高39.3个百分点，表明提高重访频率在较大规模下有明显作用。

![三类复算的处理耗时与1000毫秒期限](assets/dual_optical_registration_report/17_v2_latency_deadline.png)

![单站航迹覆盖度与双站配准覆盖度关系](assets/dual_optical_registration_report/18_v2_local_dual_correlation.png)

### 3.4 交汇定位演示

交汇定位沿用一组独立的40目标单seed理想位姿和理想时间演示。该组不参与前述54组矩阵，只用于验证“确认关系后由双视线计算位置和速度”的后半段链路。场景形成37条关系，其中36条正确、1条错误，关系精度为{percent_text(metrics['association_precision'])}，目标覆盖度为{percent_text(metrics['association_full_target_recall'])}。

{markdown_table(
    ("指标", "结果"),
    (
        ("测试seed", str(metrics["seed"])),
        ("目标数量", str(metrics["target_count"])),
        ("正确/错误关系", f"{metrics['correct_match_count']}/{metrics['false_match_count']}"),
        ("关系精度", percent_text(metrics["association_precision"])),
        ("目标覆盖度", percent_text(metrics["association_full_target_recall"])),
        ("位置误差均值/P95", f"{metrics['position_error_mean_m']:.3f}米 / {metrics['position_error_p95_m']:.3f}米"),
        ("速度误差均值/P95", f"{metrics['velocity_error_mean_mps']:.3f}米/秒 / {metrics['velocity_error_p95_mps']:.3f}米/秒"),
    ),
)}

![40目标交汇定位位置与速度误差](assets/dual_optical_registration_report/10_ranging_reconstruction_and_error.png)

该演示未加入真实安装测量误差、时间同步偏差、大气影响和检测中心系统偏差，不能把厘米级仿真误差写成设备指标。工程验证需要在已经确认的双站关系上继续注入这些误差，并记录交会角与定位误差的对应关系。

### 3.5 结论

1. **双站配准在理想单站输入下具备可行性。** 20、40、60目标的两种方法均形成有效关系。图神经网络在60目标达到99.3%的质量精度和98.7%的质量覆盖度，并在三种规模全部满足1000毫秒时限。几何方法在20和40目标的覆盖度较高，但六组全部超时。

2. **当前主要卡点是单站航迹连续性。** 360度无附加漏检虚警时，单站覆盖度随目标数从91.5%降至73.2%。同条件双站覆盖度也显著低于理想单站结果。实际360度中，单站覆盖度与双站覆盖度的相关系数达到0.903和0.613，断轨、错误重接、混合航迹和重复建轨是首要处理对象。

3. **图神经网络的主要优势是时效稳定，质量优势随场景变化。** 本轮135个图神经网络最终案例全部按时，135个几何方法案例全部超时。质量方面没有证据支持图神经网络在所有规模和干扰等级全面优于几何方法，后续应继续保留同输入对照。

4. **缩小扫描扇区能够改善重访和较大规模覆盖。** 180度扫描下60目标无附加条件的图神经网络覆盖度由360度的41.7%提高到81.0%。20目标中度干扰仍出现单站覆盖高、双站覆盖低的情况，跨站候选评分和连续确认还需单独校准。

5. **本报告属于科研仿真和确定性离线复算证据。** 40、60目标360度几何参数属于跨规模诊断，180度中重干扰属于离线干扰复算。交汇定位为理想位姿和时间下的单seed演示。上述结果不能替代真实设备外场标定。
"""
    REPORT_MD.write_text(report, encoding="utf-8")


def set_run_font(
    run: Any,
    *,
    size: float,
    bold: bool = False,
    color: str = WORD_INK,
    east_asia: str = BODY_FONT,
) -> None:
    run.font.name = LATIN_FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), east_asia)


def add_inline(paragraph: Any, text: str, *, size: float = 12, color: str = WORD_INK) -> None:
    cursor = 0
    for match in INLINE_RE.finditer(text):
        if match.start() > cursor:
            set_run_font(paragraph.add_run(text[cursor : match.start()]), size=size, color=color)
        token = match.group(0)
        if token.startswith("**"):
            set_run_font(paragraph.add_run(token[2:-2]), size=size, bold=True, color=color)
        else:
            run = paragraph.add_run(token[1:-1])
            set_run_font(run, size=size - 0.4, color=WORD_TEAL)
        cursor = match.end()
    if cursor < len(text):
        set_run_font(paragraph.add_run(text[cursor:]), size=size, color=color)


def add_page_number(paragraph: Any) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    field_begin = OxmlElement("w:fldChar")
    field_begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    field_end = OxmlElement("w:fldChar")
    field_end.set(qn("w:fldCharType"), "end")
    run._r.extend((field_begin, instruction, field_end))


def clear_paragraph(paragraph: Any) -> None:
    """Remove runs and fields while preserving paragraph properties."""

    for child in list(paragraph._p):
        if child.tag != qn("w:pPr"):
            paragraph._p.remove(child)


def reset_header_footer(container: Any) -> Any:
    """Return one empty paragraph for a newly unlinked header or footer."""

    paragraphs = list(container.paragraphs)
    first = paragraphs[0]
    clear_paragraph(first)
    for paragraph in paragraphs[1:]:
        container._element.remove(paragraph._element)
    return first


def configure_section(section: Any, *, landscape: bool = False) -> None:
    if landscape:
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width = Cm(29.7)
        section.page_height = Cm(21.0)
        section.left_margin = Cm(1.6)
        section.right_margin = Cm(1.6)
    else:
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.left_margin = Cm(2.35)
        section.right_margin = Cm(2.15)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(1.8)
    section.header_distance = Cm(0.9)
    section.footer_distance = Cm(0.8)


def configure_styles(document: Document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = LATIN_FONT
    normal.font.size = Pt(12)
    normal._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), BODY_FONT)
    normal.paragraph_format.first_line_indent = Cm(0.74)
    normal.paragraph_format.line_spacing = 1.45
    normal.paragraph_format.space_after = Pt(4)
    for index, size, color in ((1, 17, WORD_BLUE), (2, 14, WORD_TEAL), (3, 12.5, WORD_INK)):
        style = document.styles[f"Heading {index}"]
        style.font.name = LATIN_FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), HEADING_FONT)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.space_before = Pt(12 if index == 1 else 8)
        style.paragraph_format.space_after = Pt(5)


def add_header_footer(section: Any) -> None:
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    header = reset_header_footer(section.header)
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_run_font(
        header.add_run("双光电多目标轨迹配准与交汇定位试验报告"),
        size=8.5,
        color=WORD_MUTED,
    )
    add_page_number(reset_header_footer(section.footer))


def add_cover(document: Document) -> None:
    for _ in range(4):
        document.add_paragraph()
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(
        title.add_run("双光电多目标轨迹配准与交汇定位"),
        size=26,
        bold=True,
        east_asia=HEADING_FONT,
    )
    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(
        subtitle.add_run("算法原理、试验配置与结果分析"),
        size=15,
        bold=True,
        color=WORD_BLUE,
        east_asia=HEADING_FONT,
    )
    for _ in range(9):
        document.add_paragraph()
    owner = document.add_paragraph()
    owner.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(owner.add_run("MSM 项目组"), size=12)
    date = document.add_paragraph()
    date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(date.add_run("2026 年 8 月"), size=11, color=WORD_MUTED)
    boundary = document.add_paragraph()
    boundary.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(boundary.add_run("科研仿真与技术论证材料"), size=9.5, color=WORD_TEAL)


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def shade_cell(cell: Any, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def add_table(document: Document, rows: list[list[str]]) -> None:
    columns = max(len(row) for row in rows)
    table = document.add_table(rows=len(rows), cols=columns)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    font_size = 7.5 if columns >= 8 else 8.7 if columns >= 7 else 9.4
    for row in table.rows:
        properties = row._tr.get_or_add_trPr()
        properties.append(OxmlElement("w:cantSplit"))
    header_properties = table.rows[0]._tr.get_or_add_trPr()
    repeat_header = OxmlElement("w:tblHeader")
    repeat_header.set(qn("w:val"), "true")
    header_properties.append(repeat_header)
    for row_index, values in enumerate(rows):
        for column_index in range(columns):
            cell = table.cell(row_index, column_index)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.first_line_indent = Cm(0)
            paragraph.paragraph_format.space_before = Pt(0.5)
            paragraph.paragraph_format.space_after = Pt(0.5)
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            value = values[column_index] if column_index < len(values) else ""
            set_run_font(
                paragraph.add_run(value),
                size=font_size,
                bold=row_index == 0,
                color="FFFFFF" if row_index == 0 else WORD_INK,
                east_asia=HEADING_FONT if row_index == 0 else BODY_FONT,
            )
            shade_cell(
                cell,
                "1F5F99"
                if row_index == 0
                else ("F1F5F8" if row_index % 2 == 0 else "FFFFFF"),
            )
    document.add_paragraph().paragraph_format.space_after = Pt(1)


def add_image(document: Document, alt: str, path_text: str, number: int) -> None:
    image_path = (REPORT_MD.parent / path_text).resolve()
    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    with Image.open(image_path) as source:
        width_px, height_px = source.size
    ratio = width_px / height_px
    max_width_cm = 16.0
    max_height_cm = 11.5
    width_cm = min(max_width_cm, max_height_cm * ratio)
    height_cm = width_cm / ratio
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Cm(0)
    paragraph.paragraph_format.space_before = Pt(5)
    paragraph.paragraph_format.keep_together = True
    paragraph.add_run().add_picture(str(image_path), width=Cm(width_cm), height=Cm(height_cm))
    caption = document.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.first_line_indent = Cm(0)
    caption.paragraph_format.space_after = Pt(5)
    set_run_font(caption.add_run(f"图 {number}  {alt}"), size=9, color=WORD_MUTED)


def add_list(document: Document, marker: str, content: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.left_indent = Cm(0.78)
    paragraph.paragraph_format.first_line_indent = Cm(-0.52)
    paragraph.paragraph_format.space_after = Pt(3)
    set_run_font(
        paragraph.add_run(f"{marker}  "),
        size=11,
        bold=True,
        color=WORD_BLUE,
        east_asia=HEADING_FONT,
    )
    add_inline(paragraph, content, size=11)


def build_word() -> None:
    lines = REPORT_MD.read_text(encoding="utf-8").splitlines()
    document = Document()
    configure_section(document.sections[0])
    configure_styles(document)
    add_cover(document)
    body_section = document.add_section(WD_SECTION.NEW_PAGE)
    configure_section(body_section)
    add_header_footer(body_section)

    image_number = 0
    index = 0
    landscape_table_pending = False
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("# "):
            index += 1
            continue
        heading = re.match(r"^(#{2,4})\s+(.+)$", line)
        if heading:
            level = min(3, len(heading.group(1)) - 1)
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            next_line = lines[next_index].strip() if next_index < len(lines) else ""
            next_divider = (
                lines[next_index + 1].strip()
                if next_index + 1 < len(lines)
                else ""
            )
            next_is_wide_table = (
                next_line.startswith("|")
                and TABLE_DIVIDER_RE.fullmatch(next_divider) is not None
                and len(table_cells(next_line)) >= 8
            )
            if next_is_wide_table:
                landscape = document.add_section(WD_SECTION.NEW_PAGE)
                configure_section(landscape, landscape=True)
                add_header_footer(landscape)
                landscape_table_pending = True
            paragraph = document.add_paragraph(style=f"Heading {level}")
            if level == 1:
                paragraph.paragraph_format.page_break_before = True
            add_inline(
                paragraph,
                heading.group(2),
                size=(16.5, 14, 12.5)[level - 1],
                color=(WORD_BLUE, WORD_TEAL, WORD_INK)[level - 1],
            )
            index += 1
            continue
        image_match = IMAGE_RE.fullmatch(line)
        if image_match:
            image_number += 1
            add_image(document, image_match.group(1), image_match.group(2), image_number)
            index += 1
            continue
        if (
            line.startswith("|")
            and index + 1 < len(lines)
            and TABLE_DIVIDER_RE.fullmatch(lines[index + 1].strip())
        ):
            rows = [table_cells(line)]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(table_cells(lines[index]))
                index += 1
            if len(rows[0]) >= 8:
                if not landscape_table_pending:
                    landscape = document.add_section(WD_SECTION.NEW_PAGE)
                    configure_section(landscape, landscape=True)
                    add_header_footer(landscape)
                add_table(document, rows)
                portrait = document.add_section(WD_SECTION.NEW_PAGE)
                configure_section(portrait)
                add_header_footer(portrait)
                landscape_table_pending = False
            else:
                add_table(document, rows)
            continue
        numbered = re.match(r"^(\d+)\.\s+(.+)$", line)
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if numbered or bullet:
            marker = f"{numbered.group(1)}." if numbered else "•"
            content = numbered.group(2) if numbered else bullet.group(1)
            add_list(document, marker, content)
            index += 1
            continue

        parts = [line]
        lookahead = index + 1
        while lookahead < len(lines):
            candidate = lines[lookahead].strip()
            if not candidate or candidate.startswith(("#", "![", "|")):
                break
            if re.match(r"^(?:\d+\.|[-*])\s+", candidate):
                break
            parts.append(candidate)
            lookahead += 1
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.widow_control = True
        add_inline(paragraph, " ".join(parts), size=12)
        index = lookahead

    properties = document.core_properties
    properties.title = "双光电多目标轨迹配准与交汇定位试验报告"
    properties.subject = "算法原理、试验配置与结果分析"
    properties.author = "MSM 项目组"
    properties.keywords = "双光电, 多目标轨迹配准, 图神经网络, 交汇定位, AirSim"
    document.save(REPORT_DOCX)


def validate_word() -> dict[str, int]:
    document = Document(REPORT_DOCX)
    with ZipFile(REPORT_DOCX) as archive:
        damaged = archive.testzip()
        if damaged is not None:
            raise RuntimeError(f"generated DOCX archive is damaged: {damaged}")
        images = [name for name in archive.namelist() if name.startswith("word/media/")]
    text = "\n".join(
        [paragraph.text for paragraph in document.paragraphs]
        + [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    )
    required = (
        "3.1 360度理想单站条件",
        "3.2.1 试验口径",
        "3.2.2 单站航迹结果",
        "3.2.3 双站配准结果",
        "3.3 180度扫描",
        "质量精度",
        "按时覆盖度",
        "1000毫秒",
        "99.3%",
        "98.7%",
        "当前主要卡点是单站航迹连续性",
        "离线干扰复算",
        "0.4毫弧度固定偏差",
        "多方向运动目标",
        "仿真检测函数",
    )
    for value in required:
        if value not in text:
            raise RuntimeError(f"Word output is missing required content: {value}")
    for value in ("待测试；无机器记录",):
        if value in text:
            raise RuntimeError(f"Word output contains removed content: {value}")
    if len(images) < 14 or len(document.tables) < 9:
        raise RuntimeError(
            f"Word output is incomplete: images={len(images)}, tables={len(document.tables)}"
        )
    return {
        "paragraphs": len(document.paragraphs),
        "tables": len(document.tables),
        "images": len(images),
        "sections": len(document.sections),
        "bytes": REPORT_DOCX.stat().st_size,
    }


def build_evidence_manifest(
    evidence: Mapping[str, Any],
    ranging: Mapping[str, Any],
    figures: Sequence[Path],
) -> None:
    source_paths = [
        MATRIX_COMPLETENESS,
        MATRIX_SUMMARY,
        MATRIX_FINAL_CASES,
        MATRIX_REPRODUCTION,
        *MATRIX_ROUND_FILES.values(),
        RANGING_METRICS,
        RANGING_SCENARIO,
        Path(__file__),
    ]
    manifest = {
        "schema_version": "dual-optical-leadership-report-evidence-v6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report": relative(REPORT_MD),
        "authoritative_matrix_run": relative(MATRIX_ROOT),
        "matrix_completeness": evidence["completeness"],
        "reporting_policy": {
            "summary_window": "last_revolution_or_last_round",
            "continuous_360_final_round": 6,
            "s180_final_round": 12,
            "seed_count_per_group": 5,
            "deadline_ms": DEADLINE_MS,
            "quality_after_deadline_retained": True,
            "late_result_on_time_coverage": 0.0,
            "single_station_precision": (
                "dominant real observations / all labeled observations at both stations"
            ),
            "single_station_coverage": (
                "identity-correct local tracks / (2 * fixed target count)"
            ),
            "dual_station_precision": "correct confirmed relations / all confirmed relations",
            "dual_station_coverage": "unique correctly confirmed targets / fixed target count",
            "routes": list(ROUTES),
        },
        "matrix_summary_rows": evidence["summary_rows"],
        "correlations": evidence["correlations"],
        "ranging_demonstration": {
            key: ranging["metrics"][key]
            for key in (
                "seed",
                "target_count",
                "correct_match_count",
                "false_match_count",
                "association_precision",
                "association_full_target_recall",
                "position_error_mean_m",
                "position_error_p95_m",
                "velocity_error_mean_mps",
                "velocity_error_p95_mps",
            )
        },
        "source_artifacts": [
            {"path": relative(path), "sha256": sha256(path)} for path in source_paths
        ],
        "generated_artifacts": [
            {"path": relative(path), "sha256": sha256(path)}
            for path in (REPORT_MD, REPORT_DOCX, *figures)
        ],
        "limitations": [
            "All 54 matrix groups are deterministic offline replays of preserved AirSim evidence, not new AirSim runs.",
            "The 360-degree 40/60-target geometry route uses a pre-existing cross-scale diagnostic freeze.",
            "S180 medium/heavy observations are deterministic offline corruption replays.",
            "The ideal-local-track matrix uses offline labels to construct one local track per observed target and camera; it is a diagnostic upper-bound input.",
            "The 40-target ranging demonstration uses ideal pose/time and one seed and is separate from the 54-group matrix.",
            "Latency is machine-dependent; quality metrics are deterministic for the preserved inputs and frozen routes.",
        ],
    }
    EVIDENCE_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    evidence = load_and_validate_matrix()
    ranging = load_ranging_demonstration()
    figures = generate_figures(evidence)
    build_markdown(evidence, ranging)
    build_word()
    word_metrics = validate_word()
    build_evidence_manifest(evidence, ranging, figures)
    print(
        f"generated {REPORT_DOCX.name}: figures={len(figures)}, "
        f"tables={word_metrics['tables']}, sections={word_metrics['sections']}, "
        f"bytes={word_metrics['bytes']}"
    )
    print(f"evidence: {EVIDENCE_MANIFEST.name}")


if __name__ == "__main__":
    main()
