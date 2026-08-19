"""Generate the scale comparison tables and figures used by the report."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from pathlib import Path
import warnings

import matplotlib

matplotlib.use("Agg")
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
    import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / "outputs" / "offline_three_route_scale_v1"
FORMAL_ROOT = ROOT / "outputs" / "scale_funnel_v3"
SUMMARY_ROOT = OUTPUT_ROOT / "summary"
FIGURES = ROOT / "figures"
TARGET_COUNTS = (40, 60, 100)
ROUTES = ("epipolar_mht", "lightweight", "gnn")
ROUTE_LABELS = {
    "epipolar_mht": "增强几何",
    "lightweight": "轻量几何",
    "gnn": "图神经网络",
}
COLORS = {
    "epipolar_mht": "#356A8A",
    "lightweight": "#C96D3B",
    "gnn": "#2E8B57",
}


@dataclass(frozen=True)
class SummaryRow:
    target_count: int
    route_name: str
    source_mode: str
    publication_count: int
    match_count: int
    correct_match_count: int
    false_association_count: int
    selected_relation_correct_rate: float
    macro_target_coverage: float
    macro_f1: float
    deadline_met_rate: float
    latency_p95_ms: float
    diagnostic_failed_validation: bool


def configure_font() -> None:
    candidates = (
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Source Han Sans CN",
        "Droid Sans Fallback",
        "WenQuanYi Micro Hei",
        "SimHei",
    )
    installed = {font.name for font in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            plt.rcParams["font.sans-serif"] = [name]
            break
    plt.rcParams["axes.unicode_minus"] = False


def _load_rows() -> list[SummaryRow]:
    result: list[SummaryRow] = []
    for target_count in TARGET_COUNTS:
        path = (
            OUTPUT_ROOT
            / f"targets_{target_count:03d}"
            / "results"
            / "offline_comparison_metrics.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload["rows"]
        for route_name in ROUTES:
            selected = [row for row in rows if row["route_name"] == route_name]
            matches = sum(int(row["match_count"]) for row in selected)
            correct = sum(int(row["correct_match_count"]) for row in selected)
            false = sum(int(row["false_association_count"]) for row in selected)
            aggregate = payload["aggregate"]["routes"][route_name]
            result.append(
                SummaryRow(
                    target_count=target_count,
                    route_name=route_name,
                    source_mode=str(payload["source_mode"]),
                    publication_count=len(selected),
                    match_count=matches,
                    correct_match_count=correct,
                    false_association_count=false,
                    selected_relation_correct_rate=(
                        correct / matches if matches else 0.0
                    ),
                    macro_target_coverage=float(aggregate["macro_recall"]),
                    macro_f1=float(aggregate["macro_f1"]),
                    deadline_met_rate=float(aggregate["deadline_met_rate"]),
                    latency_p95_ms=float(aggregate["latency_p95_ms"]),
                    diagnostic_failed_validation=bool(
                        payload["route_manifests"][route_name][
                            "diagnostic_failed_validation"
                        ]
                    ),
                )
            )
    return result


def _write_summary(rows: list[SummaryRow]) -> None:
    SUMMARY_ROOT.mkdir(parents=True, exist_ok=True)
    fields = list(SummaryRow.__dataclass_fields__)
    with (SUMMARY_ROOT / "offline_three_route_summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {field: getattr(row, field) for field in fields} for row in rows
        )
    (SUMMARY_ROOT / "offline_three_route_summary.json").write_text(
        json.dumps(
            [{field: getattr(row, field) for field in fields} for row in rows],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _group(rows: list[SummaryRow]) -> dict[tuple[int, str], SummaryRow]:
    return {(row.target_count, row.route_name): row for row in rows}


def _use_formal_gnn_results(rows: list[SummaryRow]) -> list[SummaryRow]:
    """Use the primary 40/60-target GNN runs in report comparison figures."""

    replacements: dict[int, SummaryRow] = {}
    for target_count in (40, 60):
        path = (
            FORMAL_ROOT
            / f"targets_{target_count:03d}"
            / "results"
            / "comparison_metrics.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        selected = [row for row in payload["rows"] if row["route_name"] == "gnn"]
        correct = sum(int(row["correct_match_count"]) for row in selected)
        false = sum(int(row["false_association_count"]) for row in selected)
        aggregate = payload["aggregate"]["routes"]["gnn"]
        replacements[target_count] = SummaryRow(
            target_count=target_count,
            route_name="gnn",
            source_mode="scale_funnel_test",
            publication_count=len(selected),
            match_count=correct + false,
            correct_match_count=correct,
            false_association_count=false,
            selected_relation_correct_rate=(
                correct / (correct + false) if correct + false else 0.0
            ),
            macro_target_coverage=float(aggregate["macro_recall"]),
            macro_f1=float(aggregate["macro_f1"]),
            deadline_met_rate=float(aggregate["deadline_met_rate"]),
            latency_p95_ms=float(aggregate["latency_p95_ms"]),
            diagnostic_failed_validation=False,
        )

    return [
        replacements[row.target_count]
        if row.route_name == "gnn" and row.target_count in replacements
        else row
        for row in rows
    ]


def draw_quality(rows: list[SummaryRow]) -> None:
    lookup = _group(rows)
    x = np.arange(len(TARGET_COUNTS), dtype=float)
    width = 0.24
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), constrained_layout=True)
    metrics = (
        ("selected_relation_correct_rate", "已给出关系中正确比例"),
        ("macro_target_coverage", "目标覆盖比例（逐扫描圈平均）"),
    )
    for axis, (field, title) in zip(axes, metrics):
        for route_index, route_name in enumerate(ROUTES):
            values = [
                float(getattr(lookup[(target_count, route_name)], field))
                for target_count in TARGET_COUNTS
            ]
            positions = x + (route_index - 1) * width
            bars = axis.bar(
                positions,
                values,
                width,
                color=COLORS[route_name],
                label=ROUTE_LABELS[route_name],
            )
            for bar, value, target_count in zip(bars, values, TARGET_COUNTS):
                row = lookup[(target_count, route_name)]
                text = "无有效关系" if row.match_count == 0 else f"{value:.2f}"
                axis.text(
                    bar.get_x() + bar.get_width() / 2,
                    max(bar.get_height(), 0.015) + 0.018,
                    text,
                    ha="center",
                    va="bottom",
                    fontsize=8.5,
                    rotation=90 if row.match_count == 0 else 0,
                )
        axis.set_title(title, fontsize=13, weight="bold")
        axis.set_xticks(x, [f"{value}目标" for value in TARGET_COUNTS])
        axis.set_ylim(0.0, 1.02)
        axis.grid(axis="y", alpha=0.22)
    axes[0].legend(loc="upper right", frameon=False)
    fig.suptitle("三种方法分规模结果", fontsize=17, weight="bold")
    fig.text(
        0.5,
        -0.02,
        "40、60目标图神经网络采用正式测试；其余高规模结果为离线测试；100目标使用封存版本。",
        ha="center",
        fontsize=9.5,
        color="#555555",
    )
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        FIGURES / "13_offline_three_route_quality.png",
        dpi=200,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)


def draw_latency(rows: list[SummaryRow]) -> None:
    lookup = _group(rows)
    x = np.arange(len(TARGET_COUNTS), dtype=float)
    width = 0.24
    fig, axis = plt.subplots(figsize=(10.8, 5.4), constrained_layout=True)
    for route_index, route_name in enumerate(ROUTES):
        values = [
            lookup[(target_count, route_name)].latency_p95_ms
            for target_count in TARGET_COUNTS
        ]
        positions = x + (route_index - 1) * width
        bars = axis.bar(
            positions,
            values,
            width,
            color=COLORS[route_name],
            label=ROUTE_LABELS[route_name],
        )
        for bar, value in zip(bars, values):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                value * 1.08,
                f"{value:.0f}",
                ha="center",
                va="bottom",
                fontsize=8.5,
            )
    axis.axhline(1000.0, color="#A9483D", linewidth=1.8, linestyle="--")
    axis.text(2.38, 1080.0, "1秒时限", ha="right", color="#A9483D", fontsize=10)
    axis.set_yscale("log")
    axis.set_ylim(100.0, 16000.0)
    axis.set_xticks(x, [f"{value}目标" for value in TARGET_COUNTS])
    axis.set_ylabel("95%分位端到端时间（毫秒）")
    axis.set_title("三种方法95%计算时间", fontsize=17, weight="bold")
    axis.grid(axis="y", which="both", alpha=0.22)
    axis.legend(loc="upper left", frameon=False)
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        FIGURES / "14_offline_three_route_latency.png",
        dpi=200,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)


def main() -> int:
    configure_font()
    offline_rows = _load_rows()
    _write_summary(offline_rows)
    report_rows = _use_formal_gnn_results(offline_rows)
    draw_quality(report_rows)
    draw_latency(report_rows)
    print(FIGURES / "13_offline_three_route_quality.png")
    print(FIGURES / "14_offline_three_route_latency.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
