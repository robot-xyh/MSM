"""Summarize the frozen 20-target SuperGlue model at larger offline scales."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
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
OUTPUT_ROOT = ROOT / "outputs" / "offline_superglue_scale_v1"
SUMMARY_ROOT = OUTPUT_ROOT / "summary"
FIGURE_ROOT = SUMMARY_ROOT / "figures"
V4_20_METRICS = (
    ROOT
    / "outputs"
    / "scale_funnel_v4"
    / "targets_020"
    / "results"
    / "comparison_metrics.json"
)
TARGET_COUNTS = (20, 40, 60, 100)


@dataclass(frozen=True)
class ScaleResult:
    target_count: int
    source_version: str
    publication_count: int
    correct_match_count: int
    false_association_count: int
    selected_relation_correct_rate: float
    target_coverage_rate: float
    availability_rate: float
    deadline_met_rate: float
    latency_p95_ms: float
    adapter_latency_p95_ms: float
    attention_latency_p95_ms: float


def _configure_font() -> None:
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


def _metrics_path(target_count: int) -> tuple[Path, str]:
    if target_count == 20:
        return V4_20_METRICS, "V4正式保留测试"
    return (
        OUTPUT_ROOT
        / f"targets_{target_count:03d}"
        / "results"
        / "offline_comparison_metrics.json",
        "冻结快照离线外推",
    )


def _load_results() -> tuple[list[ScaleResult], dict[int, dict[str, object]]]:
    results: list[ScaleResult] = []
    payloads: dict[int, dict[str, object]] = {}
    for target_count in TARGET_COUNTS:
        path, source_version = _metrics_path(target_count)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payloads[target_count] = payload
        rows = [
            row
            for row in payload["rows"]
            if row["route_name"] == "track_superglue"
        ]
        aggregate = payload["aggregate"]["routes"]["track_superglue"]
        correct = sum(int(row["correct_match_count"]) for row in rows)
        false = sum(int(row["false_association_count"]) for row in rows)
        selected = correct + false
        stages = aggregate.get("stage_latency_p95_ms", {})
        results.append(
            ScaleResult(
                target_count=target_count,
                source_version=source_version,
                publication_count=len(rows),
                correct_match_count=correct,
                false_association_count=false,
                selected_relation_correct_rate=(
                    correct / selected if selected else 0.0
                ),
                target_coverage_rate=float(aggregate["macro_on_time_recall"]),
                availability_rate=float(aggregate["availability_rate"]),
                deadline_met_rate=float(aggregate["deadline_met_rate"]),
                latency_p95_ms=float(aggregate["latency_p95_ms"]),
                adapter_latency_p95_ms=float(
                    stages.get("snapshot_adapter_ms", 0.0)
                ),
                attention_latency_p95_ms=float(
                    stages.get("attention_sinkhorn_ms", 0.0)
                ),
            )
        )
    return results, payloads


def _write_tables(results: list[ScaleResult]) -> None:
    SUMMARY_ROOT.mkdir(parents=True, exist_ok=True)
    fields = list(ScaleResult.__dataclass_fields__)
    with (SUMMARY_ROOT / "offline_superglue_scale_summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(row) for row in results)
    (SUMMARY_ROOT / "offline_superglue_scale_summary.json").write_text(
        json.dumps([asdict(row) for row in results], ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _draw_quality(results: list[ScaleResult]) -> None:
    x = np.arange(len(results))
    labels = [f"{row.target_count}目标" for row in results]
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.0), constrained_layout=True)
    values = (
        (
            [row.selected_relation_correct_rate for row in results],
            "已给出关系中的正确比例",
            "#2E6F9E",
        ),
        (
            [row.target_coverage_rate for row in results],
            "按时覆盖的目标比例",
            "#C56A3A",
        ),
    )
    for axis, (metric, title, color) in zip(axes, values):
        bars = axis.bar(x, metric, width=0.58, color=color)
        for bar, value in zip(bars, metric):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                max(value, 0.012) + 0.025,
                f"{value * 100:.1f}%",
                ha="center",
                fontsize=10,
            )
        axis.set_xticks(x, labels)
        axis.set_ylim(0.0, 1.02)
        axis.set_title(title, fontsize=14, weight="bold")
        axis.grid(axis="y", alpha=0.22)
    fig.suptitle("航迹级注意力模型跨规模离线结果", fontsize=17, weight="bold")
    FIGURE_ROOT.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        FIGURE_ROOT / "01_quality_by_scale.png",
        dpi=200,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)


def _draw_latency(results: list[ScaleResult]) -> None:
    x = np.arange(len(results))
    labels = [f"{row.target_count}目标" for row in results]
    total = [row.latency_p95_ms for row in results]
    adapter = [row.adapter_latency_p95_ms for row in results]
    attention = [row.attention_latency_p95_ms for row in results]
    fig, axis = plt.subplots(figsize=(10.8, 5.4), constrained_layout=True)
    axis.plot(x, total, marker="o", linewidth=2.4, label="端到端处理")
    axis.plot(x, adapter, marker="s", linewidth=2.0, label="候选图与特征构造")
    axis.plot(x, attention, marker="^", linewidth=2.0, label="注意力与最优传输")
    axis.axhline(1000.0, color="#A9483D", linestyle="--", linewidth=1.8)
    axis.text(3.0, 1045.0, "1秒时限", ha="right", color="#A9483D")
    for index, value in enumerate(total):
        axis.text(index, value + 55.0, f"{value:.0f}", ha="center", fontsize=9)
    axis.set_xticks(x, labels)
    axis.set_ylabel("95%扫描圈处理时间（毫秒）")
    axis.set_ylim(0.0, max(total) * 1.18)
    axis.set_title("处理时间及主要耗时环节", fontsize=17, weight="bold")
    axis.grid(axis="y", alpha=0.22)
    axis.legend(frameon=False, loc="upper left")
    FIGURE_ROOT.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        FIGURE_ROOT / "02_latency_by_scale.png",
        dpi=200,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)


def _write_report(results: list[ScaleResult]) -> Path:
    lookup = {row.target_count: row for row in results}
    lines = [
        "# 航迹级注意力模型40、60、100目标离线测试",
        "",
        "## 结论",
        "",
        (
            "20目标冻结模型直接用于更大规模后，40目标仍能形成部分可靠关系；"
            "60目标的按时覆盖明显下降；100目标没有形成确认关系。当前模型不能"
            "直接扩展到60和100目标。"
        ),
        "",
        (
            "计算瓶颈不在注意力网络。40、60和100目标的注意力计算95%时间约为"
            f"{lookup[40].attention_latency_p95_ms:.1f}、"
            f"{lookup[60].attention_latency_p95_ms:.1f}和"
            f"{lookup[100].attention_latency_p95_ms:.1f}毫秒；候选图与几何特征构造"
            f"分别达到{lookup[40].adapter_latency_p95_ms:.0f}、"
            f"{lookup[60].adapter_latency_p95_ms:.0f}和"
            f"{lookup[100].adapter_latency_p95_ms:.0f}毫秒。"
        ),
        "",
        "## 测试口径",
        "",
        (
            "40、60目标使用V3冻结匿名测试快照，每档5个随机种子、4档干扰、"
            "每档6个扫描圈，共120个结果。100目标使用封存V2匿名快照，20个随机"
            "种子、3档干扰、每档6个扫描圈，共360个结果。真实身份只在每圈算法"
            "输出完成后用于统计。"
        ),
        "",
        (
            "模型权重、归一化参数和判定门槛全部来自V4的20目标训练与验证数据。"
            "高规模数据没有用于重新训练或调整门槛。40、60、100目标结果属于跨"
            "规模离线外推，不改变原有正式在线测试结论。"
        ),
        "",
        "## 结果",
        "",
        "| 目标数 | 数据口径 | 正确/错误关系 | 已给出关系正确比例 | 按时目标覆盖 | 按时处理圈比例 | 95%处理时间 |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in results:
        relation_rate = (
            f"{row.selected_relation_correct_rate * 100:.1f}%"
            if row.correct_match_count + row.false_association_count
            else "无有效关系"
        )
        lines.append(
            "| "
            f"{row.target_count} | {row.source_version} | "
            f"{row.correct_match_count}/{row.false_association_count} | "
            f"{relation_rate} | {row.target_coverage_rate * 100:.1f}% | "
            f"{row.deadline_met_rate * 100:.1f}% | {row.latency_p95_ms:.1f}毫秒 |"
        )
    lines.extend(
        [
            "",
            "![跨规模关联质量](figures/01_quality_by_scale.png)",
            "",
            "20目标是正式保留测试，40至100目标是冻结模型离线外推。两类结果用于观察趋势，不能当作同版本在线验证。",
            "",
            "![跨规模处理时间](figures/02_latency_by_scale.png)",
            "",
            "## 分规模判断",
            "",
            (
                f"40目标共形成{lookup[40].correct_match_count}条正确关系和"
                f"{lookup[40].false_association_count}条错误关系。已给出关系中的"
                f"正确比例为{lookup[40].selected_relation_correct_rate * 100:.1f}%，"
                f"按时覆盖{lookup[40].target_coverage_rate * 100:.1f}%的目标。该结果"
                "说明模型仍能区分一部分目标，但覆盖低于20目标。"
            ),
            "",
            (
                f"60目标已给出关系中的正确比例为"
                f"{lookup[60].selected_relation_correct_rate * 100:.1f}%，但按时覆盖"
                f"降至{lookup[60].target_coverage_rate * 100:.1f}%，只有"
                f"{lookup[60].deadline_met_rate * 100:.1f}%的扫描圈在1秒内完成。"
                "较高的关系正确比例来自保守拒绝，不能理解为已经分清60个目标。"
            ),
            "",
            (
                "100目标没有形成确认关系。前三个扫描圈经常缺少成熟的双方航迹；"
                "第四圈已有候选，但20目标模型把这些候选判为不匹配；第五、六圈的"
                "几何特征构造又普遍超过1秒。旧版100目标快照没有当前候选图字段，"
                "适配器需要重新计算候选关系，这也增加了计算时间。"
            ),
            "",
            "## 与既有方法对比",
            "",
            (
                "既有图网络在40目标离线结果中的关系正确比例约82.3%，目标覆盖"
                "24.5%，95%时间约306毫秒。当前航迹级注意力模型对应数值为"
                f"{lookup[40].selected_relation_correct_rate * 100:.1f}%、"
                f"{lookup[40].target_coverage_rate * 100:.1f}%和"
                f"{lookup[40].latency_p95_ms:.0f}毫秒，没有形成优势。"
            ),
            "",
            (
                "60目标时，航迹级注意力模型减少了已输出关系中的错误，但目标覆盖"
                "由既有图网络约24.7%降至9.1%，处理时间由约427毫秒增至"
                f"{lookup[60].latency_p95_ms:.0f}毫秒。100目标为零输出。现阶段不"
                "应以该模型替换图网络或几何基线。"
            ),
            "",
            "## 后续工作",
            "",
            "1. 优化候选图的增量构造，避免每圈重复计算全部轨迹对的多时刻几何特征。",
            "2. 按20、40、60目标分别冻结归一化参数，检查性能下降来自特征分布变化还是模型容量不足。",
            "3. 将候选关系按空间邻域分块，注意力模型只处理局部竞争集合，保留全局一一约束。",
            "4. 40目标共享跟踪器达到正式时延和碎片门槛后，再生成V4同版本保留集进行在线复核。",
            "",
            "## 文件",
            "",
            "- 汇总数据：`offline_superglue_scale_summary.json`、`offline_superglue_scale_summary.csv`",
            "- 40目标指标：`../targets_040/results/offline_comparison_metrics.json`",
            "- 60目标指标：`../targets_060/results/offline_comparison_metrics.json`",
            "- 100目标指标：`../targets_100/results/offline_comparison_metrics.json`",
            "",
        ]
    )
    path = SUMMARY_ROOT / "OFFLINE_SUPERGLUE_40_60_100_REPORT_CN.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    _configure_font()
    results, _ = _load_results()
    _write_tables(results)
    _draw_quality(results)
    _draw_latency(results)
    print(_write_report(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
