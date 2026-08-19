#!/usr/bin/env python3
"""Build Chinese V4 result figures for the scheme-template source material."""

from __future__ import annotations

import json
from pathlib import Path
import warnings

warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
METRICS = (
    ROOT
    / "research_modules"
    / "independent_experiments"
    / "dual_optical_online_benchmark"
    / "outputs"
    / "scale_funnel_v4"
    / "targets_020"
    / "results"
    / "comparison_metrics.json"
)
OUTPUT = (
    ROOT
    / "deliverables"
    / "leadership_report"
    / "assets"
    / "scheme_template_material"
    / "07_v4_20target_results_cn.png"
)


def main() -> None:
    payload = json.loads(METRICS.read_text(encoding="utf-8"))
    routes = payload["aggregate"]["routes"]
    route_keys = ("epipolar_mht", "gnn", "track_superglue")
    labels = ("增强几何", "图神经网络", "航迹级注意力")
    colors = ("#456B82", "#2F78B7", "#B26A2E")

    f1 = np.asarray([routes[key]["macro_f1"] for key in route_keys])
    recall = np.asarray(
        [routes[key]["macro_on_time_recall"] for key in route_keys]
    )
    latency = np.asarray([routes[key]["latency_p95_ms"] for key in route_keys])
    corruption_levels = ("clean", "light", "medium", "heavy")
    corruption_labels = ("无干扰", "轻度", "中度", "重度")
    f1_by_corruption = {
        key: np.asarray(
            [
                np.mean(
                    [
                        row["f1"]
                        for row in payload["rows"]
                        if row["route_name"] == key
                        and row["corruption_level"] == level
                    ]
                )
                for level in corruption_levels
            ]
        )
        for key in route_keys
    }
    correct_counts = np.asarray(
        [
            sum(
                row["correct_match_count"]
                for row in payload["rows"]
                if row["route_name"] == key
            )
            for key in route_keys
        ]
    )
    false_counts = np.asarray(
        [
            sum(
                row["false_association_count"]
                for row in payload["rows"]
                if row["route_name"] == key
            )
            for key in route_keys
        ]
    )

    plt.rcParams.update(
        {
            "font.sans-serif": [
                "Noto Sans CJK SC",
                "Noto Sans CJK JP",
                "Source Han Sans SC",
                "Droid Sans Fallback",
                "SimHei",
                "DejaVu Sans",
            ],
            "axes.unicode_minus": False,
            "font.size": 12,
        }
    )
    figure, axes = plt.subplots(2, 2, figsize=(16.2, 10.8))
    figure.subplots_adjust(
        left=0.065,
        right=0.985,
        bottom=0.105,
        top=0.885,
        wspace=0.23,
        hspace=0.37,
    )
    figure.suptitle("V4二十目标保留测试结果", fontsize=22, fontweight="bold")
    figure.text(
        0.5,
        0.925,
        "同一批输入分别运行增强几何、图神经网络和航迹级注意力路线",
        ha="center",
        fontsize=12,
        color="#4B5560",
    )

    x = np.arange(len(labels))
    width = 0.34
    bars_f1 = axes[0, 0].bar(
        x - width / 2,
        f1,
        width,
        label="综合匹配指标",
        color="#456B82",
    )
    bars_recall = axes[0, 0].bar(
        x + width / 2,
        recall,
        width,
        label="按时覆盖比例",
        color="#6F9E72",
    )
    axes[0, 0].set_title("总体配准质量")
    axes[0, 0].set_xticks(x, labels)
    axes[0, 0].set_ylim(0.0, 0.65)
    axes[0, 0].set_ylabel("比例")
    axes[0, 0].grid(axis="y", alpha=0.25)
    axes[0, 0].legend(frameon=False, loc="upper right")
    axes[0, 0].bar_label(bars_f1, fmt="%.3f", padding=3)
    axes[0, 0].bar_label(bars_recall, fmt="%.3f", padding=3)

    corruption_x = np.arange(len(corruption_levels))
    corruption_width = 0.25
    for route_index, (key, label, color) in enumerate(
        zip(route_keys, labels, colors)
    ):
        axes[0, 1].bar(
            corruption_x + (route_index - 1) * corruption_width,
            f1_by_corruption[key],
            corruption_width,
            label=label,
            color=color,
        )
    axes[0, 1].set_title("不同漏检与虚警条件下的综合匹配指标")
    axes[0, 1].set_xticks(corruption_x, corruption_labels)
    axes[0, 1].set_ylim(0.0, 0.80)
    axes[0, 1].set_ylabel("比例")
    axes[0, 1].grid(axis="y", alpha=0.25)
    axes[0, 1].legend(frameon=False, loc="upper right", fontsize=10)

    bars_latency = axes[1, 0].bar(x, latency, color=colors, width=0.58)
    axes[1, 0].axhline(
        1000.0,
        color="#B13C35",
        linestyle="--",
        linewidth=1.8,
        label="一秒在线时限",
    )
    axes[1, 0].set_title("95%处理时间")
    axes[1, 0].set_xticks(x, labels)
    axes[1, 0].set_ylim(0.0, 1400.0)
    axes[1, 0].set_ylabel("毫秒")
    axes[1, 0].grid(axis="y", alpha=0.25)
    axes[1, 0].legend(frameon=False, loc="upper right")
    axes[1, 0].bar_label(bars_latency, fmt="%.0f", padding=3)

    bars_correct = axes[1, 1].bar(
        x,
        correct_counts,
        color=colors,
        width=0.58,
        label="正确关系",
    )
    bars_false = axes[1, 1].bar(
        x,
        false_counts,
        bottom=correct_counts,
        color="#B13C35",
        alpha=0.82,
        width=0.58,
        label="错误关系",
    )
    axes[1, 1].set_title("120份逐圈快照累计发布关系")
    axes[1, 1].set_xticks(x, labels)
    axes[1, 1].set_ylabel("关系数量")
    axes[1, 1].grid(axis="y", alpha=0.25)
    axes[1, 1].legend(frameon=False, loc="upper right")
    axes[1, 1].bar_label(bars_correct, fmt="%.0f", label_type="center", color="white")
    axes[1, 1].bar_label(
        bars_false,
        labels=[f"错误 {int(value)}" for value in false_counts],
        padding=3,
        fontsize=10,
    )

    figure.text(
        0.5,
        0.035,
        "场景：20个3米目标、50米/秒、双站相距2千米、2秒连续周扫；"
        "5个未见测试种子、4档漏检与虚警、共120份逐圈快照。",
        ha="center",
        fontsize=11,
        color="#4B5560",
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT, dpi=180, facecolor="white")
    plt.close(figure)


if __name__ == "__main__":
    main()
