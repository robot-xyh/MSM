#!/usr/bin/env python3
"""Build the main-owned lightweight-versus-GNN comparison report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import warnings

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
    import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIGHT_METRICS = (
    REPO_ROOT
    / "research_modules/independent_experiments/dual_optical_100target_lightweight/"
    "outputs/formal_expanded_20260820_20260920_run01/evaluation/evaluation_metrics.json"
)
DEFAULT_GNN_METRICS = (
    REPO_ROOT
    / "research_modules/independent_experiments/dual_optical_100target_gnn/"
    "outputs/formal_expanded_20260820_20260920_run01/evaluation/evaluation_metrics.json"
)
DEFAULT_COMPARISON = DEFAULT_GNN_METRICS.parent / "promotion_comparison.json"
DEFAULT_BATCH = (
    REPO_ROOT
    / "research_modules/independent_experiments/dual_optical_100target_gnn/"
    "outputs/raw_airsim_expanded_20260901_20260920/batch_summary.json"
)
DEFAULT_REPORT = (
    REPO_ROOT
    / "research_modules/independent_experiments/"
    "DUAL_OPTICAL_100TARGET_LIGHTWEIGHT_GNN_COMPARISON_CN.md"
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _configure_plotting() -> None:
    font_paths = (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
    )
    for font_path in font_paths:
        if font_path.is_file():
            font_manager.fontManager.addfont(str(font_path))
    candidates = (
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "WenQuanYi Zen Hei",
        "Droid Sans Fallback",
    )
    installed = {font.name for font in font_manager.fontManager.ttflist}
    selected = next((name for name in candidates if name in installed), "DejaVu Sans")
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [selected, "DejaVu Sans"],
            "axes.unicode_minus": False,
            "font.size": 10,
            "figure.dpi": 140,
        }
    )


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _flow_figure(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11.2, 4.0))
    ax.set_xlim(0, 11.2)
    ax.set_ylim(0, 4.0)
    ax.axis("off")
    boxes = [
        (0.25, 1.45, 1.65, 1.1, "30个AirSim场景\n8训练＋2验证＋20测试", "#D9EAF7"),
        (2.25, 1.45, 1.55, 1.1, "匿名本地轨迹\n轻中重三档", "#E8E8E8"),
        (4.15, 2.25, 2.05, 1.05, "轻量路线\n几何重标定／概率标定／逻辑回归", "#DDEFD8"),
        (4.15, 0.65, 2.05, 1.05, "图网络路线\n两层消息传递＋混合代价", "#F8E3C8"),
        (6.65, 1.45, 1.65, 1.1, "共同硬约束\n几何门控＋匈牙利一对一", "#E6DDF2"),
        (8.75, 1.45, 2.05, 1.1, "20个未见seed评估\n配对置信区间＋晋级判定", "#F6D9D7"),
    ]
    for x, y, width, height, label, color in boxes:
        ax.add_patch(
            FancyBboxPatch(
                (x, y), width, height,
                boxstyle="round,pad=0.04,rounding_size=0.08",
                facecolor=color, edgecolor="#3F4A52", linewidth=1.2,
            )
        )
        ax.text(x + width / 2, y + height / 2, label, ha="center", va="center")
    arrows = [
        ((1.9, 2.0), (2.25, 2.0)),
        ((3.8, 2.0), (4.15, 2.77)),
        ((3.8, 2.0), (4.15, 1.17)),
        ((6.2, 2.77), (6.65, 2.0)),
        ((6.2, 1.17), (6.65, 2.0)),
        ((8.3, 2.0), (8.75, 2.0)),
    ]
    for start, end in arrows:
        ax.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle": "->", "lw": 1.4})
    ax.set_title("双路线同输入测试流程", fontsize=15, fontweight="bold", pad=10)
    _save(fig, path)


def _aggregate_figure(light: dict[str, Any], gnn: dict[str, Any], path: Path) -> None:
    light_row = light["assignment"]["selected_lightweight"]
    gnn_route = gnn["formal_selection"]["selected_route"]
    gnn_row = gnn["assignment"][gnn_route]
    metrics = ["macro_precision", "macro_recall", "macro_f1"]
    labels = ["准确率", "召回率", "F1综合指标"]
    x = np.arange(len(metrics))
    width = 0.34
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    left = ax.bar(x - width / 2, [light_row[key] for key in metrics], width, label="轻量方案", color="#2F7D64")
    right = ax.bar(x + width / 2, [gnn_row[key] for key in metrics], width, label="图网络选定方案", color="#C46A3A")
    ax.bar_label(left, fmt="%.3f", padding=3)
    ax.bar_label(right, fmt="%.3f", padding=3)
    ax.set_xticks(x, labels)
    ax.set_ylim(0.80, 1.01)
    ax.set_ylabel("指标值")
    ax.set_title("20个未见seed的总体关联结果")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, loc="lower left")
    _save(fig, path)


def _error_figure(light: dict[str, Any], gnn: dict[str, Any], path: Path) -> None:
    light_row = light["assignment"]["selected_lightweight"]
    gnn_route = gnn["formal_selection"]["selected_route"]
    gnn_row = gnn["assignment"][gnn_route]
    labels = ["错误关联", "重复身份"]
    light_values = [light_row["false_association_count"], light_row["duplicate_identity_match_count"]]
    gnn_values = [gnn_row["false_association_count"], gnn_row["duplicate_identity_match_count"]]
    x = np.arange(2)
    width = 0.34
    fig, ax = plt.subplots(figsize=(7.8, 4.7))
    left = ax.bar(x - width / 2, light_values, width, label="轻量方案", color="#2F7D64")
    right = ax.bar(x + width / 2, gnn_values, width, label="图网络选定方案", color="#C46A3A")
    ax.bar_label(left, padding=3)
    ax.bar_label(right, padding=3)
    ax.set_xticks(x, labels)
    ax.set_ylabel("累计次数（60个测试样本）")
    ax.set_title("关联错误与身份重复")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    _save(fig, path)


def _seed_figure(light: dict[str, Any], gnn: dict[str, Any], comparison: dict[str, Any], path: Path) -> None:
    light_rows = {
        int(row["seed"]): row
        for row in light["per_seed_summary"]
        if row["mode"] == "selected_lightweight"
    }
    route = gnn["formal_selection"]["selected_route"]
    gnn_rows = {
        int(row["seed"]): row
        for row in gnn["per_seed_summary"]
        if row["mode"] == route
    }
    seeds = sorted(light_rows)
    light_f1 = np.asarray([light_rows[seed]["macro_f1"] for seed in seeds])
    gnn_f1 = np.asarray([gnn_rows[seed]["macro_f1"] for seed in seeds])
    delta = gnn_f1 - light_f1
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10.5, 7.0), sharex=True, gridspec_kw={"height_ratios": [2.0, 1.0]})
    x = np.arange(len(seeds))
    ax1.plot(x, light_f1, "o-", color="#2F7D64", lw=1.6, ms=4, label="轻量方案")
    ax1.plot(x, gnn_f1, "s-", color="#C46A3A", lw=1.4, ms=3.8, label="图网络选定方案")
    ax1.set_ylabel("每seed三档平均F1")
    ax1.set_title("逐seed结果与配对差值")
    ax1.grid(alpha=0.25)
    ax1.legend(frameon=False)
    colors = np.where(delta >= 0.0, "#4F8DB8", "#B8524A")
    ax2.bar(x, delta, color=colors, width=0.72)
    ax2.axhline(0.0, color="#333333", lw=1.0)
    interval = comparison["paired_bootstrap"]["metrics"]["macro_f1"]
    ax2.text(
        0.01, 0.93,
        f"图网络－轻量：均值 {interval['estimate']:+.4f}，95%区间 [{interval['lower_95']:+.4f}, {interval['upper_95']:+.4f}]",
        transform=ax2.transAxes, va="top",
    )
    ax2.set_ylabel("F1差值")
    ax2.set_xticks(x, [str(seed)[-4:] for seed in seeds], rotation=45)
    ax2.set_xlabel("测试seed（显示末四位）")
    ax2.grid(axis="y", alpha=0.25)
    _save(fig, path)


def _corruption_figure(light: dict[str, Any], gnn: dict[str, Any], path: Path) -> None:
    levels = ["light", "medium", "heavy"]
    labels = ["轻度", "中度", "重度"]
    route = gnn["formal_selection"]["selected_route"]
    light_values = [light["assignment_by_corruption"][level]["selected_lightweight"]["macro_f1"] for level in levels]
    gnn_values = [gnn["assignment_by_corruption"][level][route]["macro_f1"] for level in levels]
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.plot(labels, light_values, "o-", lw=2.0, color="#2F7D64", label="轻量方案")
    ax.plot(labels, gnn_values, "s-", lw=2.0, color="#C46A3A", label="图网络选定方案")
    for index, value in enumerate(light_values):
        ax.text(index, value + 0.002, f"{value:.3f}", ha="center", color="#245E4C")
    for index, value in enumerate(gnn_values):
        ax.text(index, value - 0.006, f"{value:.3f}", ha="center", color="#924A29")
    ax.set_ylim(min(light_values + gnn_values) - 0.02, max(light_values + gnn_values) + 0.02)
    ax.set_ylabel("F1综合指标")
    ax.set_title("不同离线腐化强度下的结果")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    _save(fig, path)


def _report_text(
    light: dict[str, Any],
    gnn: dict[str, Any],
    comparison: dict[str, Any],
    batch: dict[str, Any],
    figures: Path,
    report_path: Path,
) -> str:
    light_row = light["assignment"]["selected_lightweight"]
    route = gnn["formal_selection"]["selected_route"]
    gnn_row = gnn["assignment"][route]
    interval = comparison["paired_bootstrap"]["metrics"]["macro_f1"]
    light_latency = light["latency_detail"]
    gnn_latency = gnn["latency"]
    relative = lambda name: (figures / name).relative_to(report_path.parent).as_posix()
    seeds = comparison["test_seeds"]
    first_return_codes = [
        int(item["attempts"][0]["returncode"])
        for item in batch["results"]
        if item.get("attempts")
    ]
    strict_pass_count = sum(code == 0 for code in first_return_codes)
    strict_fail_count = sum(code == 2 for code in first_return_codes)
    return f"""# 双站光电100目标轻量方案与图网络对比试验

## 结论

本轮不建议用图神经网络替换轻量方案。20个未见AirSim seed、60个离线腐化测试样本中，轻量方案F1为{light_row['macro_f1']:.4f}，图网络验证集选定方案F1为{gnn_row['macro_f1']:.4f}。图网络相对轻量方案的配对F1差值为{interval['estimate']:+.4f}，95%置信区间为[{interval['lower_95']:+.4f}, {interval['upper_95']:+.4f}]，没有形成稳定正收益。

图网络累计错误关联{gnn_row['false_association_count']}次，轻量方案为{light_row['false_association_count']}次。图网络重复身份{gnn_row['duplicate_identity_match_count']}次，轻量方案为{light_row['duplicate_identity_match_count']}次。图网络只在重复身份一项减少3次，未满足F1提高、置信区间和误配不增加三项条件。当前推荐保留“几何硬门控＋非负几何权重重标定＋匈牙利一对一分配”。

![双路线同输入测试流程]({relative('01_test_flow.png')})

## 试验设置

本轮只测试2公里双站、100目标场景，没有运行4公里100目标案例，也不涉及D1至D7。两台光电节点采用ComputerVision模式，间距2公里；目标长度3米、速度50米每秒，观测12秒。相机分辨率1280×1024，水平视场角2.93度，方位扫描范围正负45度，扫描周期1秒，AirSim时钟倍率0.1。

训练集使用20260820至20260827共8个seed，验证集使用20260828和20260829共2个seed。测试集使用20260901至20260920共20个新增seed。main在一次Blocks启动中顺序运行20个episode，episode之间重置场景；{batch['completed_seed_count']}/20个episode均形成完整记录和指标，没有保存截图。原始确定性基线有{strict_pass_count}个episode通过自身严格门限，另有{strict_fail_count}个返回码为2，表示基线门限未通过，不表示AirSim运行失败。本报告的轻量方案和图网络指标均在原始记录冻结后重新计算。

每个AirSim记录离线生成轻、中、重三档漏检与虚警输入。测试集共60个样本。三档样本来自同一AirSim seed，置信区间按20个完整seed成组抽样，不能按60个独立场景解释。在线图不包含真实身份、Actor名称和真实三维位置，真值只用于训练标签和冻结后的离线评分。

数据集指纹为`{comparison['dataset_fingerprint_sha256']}`，候选图指纹为`{comparison['candidate_fingerprint_sha256']}`。两条路线的候选节点、候选边、几何代价和样本顺序完全一致。

## 算法路线

轻量智能体比较了非负几何权重重标定、Platt概率标定、单调概率标定和五组二范数逻辑回归。训练集拟合后，验证集从56组模型与门限组合中选中非负几何权重重标定，概率门限为0.8。该方法重新分配共面性、重投影、运动一致性和时间重叠等八项几何证据的权重，不改变候选硬门控。

图网络采用两层消息传递、64维隐藏特征和固定训练参数。验证集选中0.4概率门限，以及40%几何代价和60%学习代价组成的混合路线。网络只对通过几何硬门控的候选边评分，最终关系仍由匈牙利算法给出，低证据候选可以保持未匹配。

![总体关联指标]({relative('02_aggregate_metrics.png')})

## 指标结果

| 方法 | 准确率 | 召回率 | F1 | 错误关联 | 重复身份 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 轻量方案 | {light_row['macro_precision']:.4f} | {light_row['macro_recall']:.4f} | {light_row['macro_f1']:.4f} | {light_row['false_association_count']} | {light_row['duplicate_identity_match_count']} |
| 图网络选定方案 | {gnn_row['macro_precision']:.4f} | {gnn_row['macro_recall']:.4f} | {gnn_row['macro_f1']:.4f} | {gnn_row['false_association_count']} | {gnn_row['duplicate_identity_match_count']} |

轻量方案准确率高0.0055，召回率高0.0003，F1高0.0024。二者召回率接近，主要差别来自图网络多产生28次错误关联。逐seed差值有正有负，整体置信区间跨过0，当前样本不能证明图网络有稳定收益。

![错误关联与身份重复]({relative('03_error_counts.png')})

![逐seed结果]({relative('04_seed_paired_f1.png')})

![腐化强度结果]({relative('05_corruption_f1.png')})

## 时延

轻量模型中央处理器评分95%分位为{light_latency['model_scoring']['p95_ms']:.3f}毫秒，匈牙利求解95%分位为{light_latency['hungarian_assignment']['p95_ms']:.3f}毫秒。图网络中央处理器和图形处理器推理95%分位分别为{gnn_latency['cpu']['p95_ms']:.3f}毫秒和{gnn_latency['gpu']['p95_ms']:.3f}毫秒。两条路线的评分时延都满足本轮100毫秒判据，时延不是本轮选型的限制因素。

## 判定

| 图网络晋级条件 | 结果 |
| --- | --- |
| F1相对轻量方案提高不少于0.02 | 未通过，实际{comparison['criteria']['macro_f1_delta']:+.4f} |
| 配对F1置信区间下限大于0 | 未通过，下限{interval['lower_95']:+.4f} |
| 错误关联不增加 | 未通过，图网络多{gnn_row['false_association_count'] - light_row['false_association_count']}次 |
| 重复身份不增加 | 通过，图网络少{light_row['duplicate_identity_match_count'] - gnn_row['duplicate_identity_match_count']}次 |
| 图形处理器推理95%分位不超过100毫秒 | 通过，实际{gnn_latency['gpu']['p95_ms']:.3f}毫秒 |

判定状态为`{comparison['status']}`。该状态只针对当前2公里、100目标、离线腐化条件。结果不证明图网络在真实探测器误差、不同目标外形或其他扫描几何下无效，但现有证据不足以承担主线替换成本。

## 后续工作

1. 以轻量方案作为本独立试验的默认对照，保留图网络代码和冻结模型，不并入D1至D7在线链路。
2. 后续取得真实探测器漏检、虚警和框中心抖动日志后，使用同一冻结协议重新比较。当前离线腐化不能代替真实误差分布。
3. 若继续研究图网络，先验证其相对重新标定几何代价的独立收益，不再只与未标定原始几何代价比较。
4. 在线应用前还需把episode结束后的批处理改为因果增量处理，并测量完整候选更新、评分和分配周期。

## 文件索引

- AirSim批次：`research_modules/independent_experiments/dual_optical_100target_gnn/outputs/raw_airsim_expanded_20260901_20260920/batch_summary.json`
- 统一数据集：`research_modules/independent_experiments/dual_optical_100target_gnn/outputs/formal_expanded_20260820_20260920_run01/dataset/dataset_manifest.json`
- 轻量评估：`research_modules/independent_experiments/dual_optical_100target_lightweight/outputs/formal_expanded_20260820_20260920_run01/evaluation/`
- 图网络评估：`research_modules/independent_experiments/dual_optical_100target_gnn/outputs/formal_expanded_20260820_20260920_run01/evaluation/`
- 正式比较：`research_modules/independent_experiments/dual_optical_100target_gnn/outputs/formal_expanded_20260820_20260920_run01/evaluation/promotion_comparison.json`
"""


def build_report(
    light_path: Path,
    gnn_path: Path,
    comparison_path: Path,
    batch_path: Path,
    report_path: Path,
) -> tuple[Path, Path]:
    light = _load(light_path)
    gnn = _load(gnn_path)
    comparison = _load(comparison_path)
    batch = _load(batch_path)
    light_hash = light["reproducibility"]["candidate_fingerprint_sha256"]
    gnn_hash = gnn["reproducibility"]["candidate_fingerprint_sha256"]
    if light_hash != gnn_hash or light_hash != comparison["candidate_fingerprint_sha256"]:
        raise ValueError("lightweight and GNN candidate fingerprints do not match")
    if light["reproducibility"]["dataset_fingerprint_sha256"] != comparison["dataset_fingerprint_sha256"]:
        raise ValueError("lightweight and comparison dataset fingerprints do not match")
    if gnn["reproducibility"]["dataset_fingerprint_sha256"] != comparison["dataset_fingerprint_sha256"]:
        raise ValueError("GNN and comparison dataset fingerprints do not match")
    if batch.get("completed_seed_count") != 20:
        raise ValueError("the AirSim batch did not complete all 20 reserved seeds")

    report_path = report_path.resolve()
    figures = report_path.parent / "assets/lightweight_gnn_expanded_20260820_20260920"
    figures.mkdir(parents=True, exist_ok=True)
    _configure_plotting()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
        _flow_figure(figures / "01_test_flow.png")
        _aggregate_figure(light, gnn, figures / "02_aggregate_metrics.png")
        _error_figure(light, gnn, figures / "03_error_counts.png")
        _seed_figure(light, gnn, comparison, figures / "04_seed_paired_f1.png")
        _corruption_figure(light, gnn, figures / "05_corruption_f1.png")
    report_path.write_text(
        _report_text(light, gnn, comparison, batch, figures, report_path),
        encoding="utf-8",
    )

    from dual_optical_100target_gnn.build_word_report import build_word_report

    word_path = build_word_report(report_path, report_path.with_suffix(".docx"))
    return report_path, word_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--light-metrics", type=Path, default=DEFAULT_LIGHT_METRICS)
    parser.add_argument("--gnn-metrics", type=Path, default=DEFAULT_GNN_METRICS)
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report, word = build_report(
        args.light_metrics.resolve(),
        args.gnn_metrics.resolve(),
        args.comparison.resolve(),
        args.batch.resolve(),
        args.output.resolve(),
    )
    print(report)
    print(word)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
