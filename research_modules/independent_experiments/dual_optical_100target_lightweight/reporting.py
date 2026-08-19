"""Chinese Markdown and figures for the lightweight association experiment."""

from __future__ import annotations

import csv
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

from .build_word_report import build_word_report


REPORT_NAME = "DUAL_OPTICAL_100TARGET_LIGHTWEIGHT_REPORT_CN.md"


def _configure_plotting() -> None:
    bundled_candidates = (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
    )
    for font_path in bundled_candidates:
        if font_path.is_file():
            font_manager.fontManager.addfont(str(font_path))
    candidates = (
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Source Han Sans CN",
        "WenQuanYi Zen Hei",
        "WenQuanYi Micro Hei",
        "Microsoft YaHei",
        "SimHei",
    )
    installed = {font.name for font in font_manager.fontManager.ttflist}
    selected = next((name for name in candidates if name in installed), "DejaVu Sans")
    plt.rcParams.update(
        {
            "font.family": selected,
            "axes.unicode_minus": False,
            "figure.dpi": 150,
            "savefig.bbox": "tight",
        }
    )


def _save_flow(path: Path) -> None:
    figure, axis = plt.subplots(figsize=(12, 3.4))
    axis.set_xlim(0, 12)
    axis.set_ylim(0, 3.4)
    axis.axis("off")
    labels = (
        "匿名轨迹\n与12维候选边",
        "几何硬门控\n保持不变",
        "四类轻量模型\n只输出概率",
        "验证集选择\n模型与门限",
        "匈牙利算法\n一对一或未匹配",
    )
    colors = ("#DCE9F2", "#F5E6C8", "#DDECD8", "#E8DFF0", "#D8E5E5")
    x_values = (0.2, 2.65, 5.1, 7.55, 10.0)
    for index, (x, label, color) in enumerate(zip(x_values, labels, colors)):
        axis.add_patch(
            plt.Rectangle((x, 1.15), 1.8, 1.1, facecolor=color, edgecolor="#3D4A52")
        )
        axis.text(x + 0.9, 1.7, label, ha="center", va="center", fontsize=10)
        if index < len(labels) - 1:
            axis.annotate(
                "",
                xy=(x_values[index + 1] - 0.08, 1.7),
                xytext=(x + 1.9, 1.7),
                arrowprops={"arrowstyle": "->", "lw": 1.5, "color": "#3D4A52"},
            )
    axis.text(
        6.0,
        0.35,
        "真实身份只参与训练标签和冻结后的离线评分，不进入在线特征",
        ha="center",
        fontsize=10,
        color="#8A2F2F",
    )
    figure.savefig(path)
    plt.close(figure)


def _save_method_map(path: Path) -> None:
    figure, axis = plt.subplots(figsize=(11, 5.2))
    axis.set_xlim(0, 11)
    axis.set_ylim(0, 5.2)
    axis.axis("off")
    methods = (
        ("非负几何权重", "重新标定8项归一化几何分量", "9个参数"),
        ("Platt标定", "把原几何代价映射为同目标概率", "2个参数"),
        ("单调标定", "保持代价越小、概率不降低", "分段单调函数"),
        ("逻辑回归", "标准化12维候选边特征", "5个固定正则强度"),
    )
    for row, (name, role, detail) in enumerate(methods):
        y = 4.25 - row * 1.1
        axis.add_patch(
            plt.Rectangle((0.4, y - 0.35), 2.1, 0.7, facecolor="#DCE9F2", edgecolor="#425563")
        )
        axis.add_patch(
            plt.Rectangle((3.0, y - 0.35), 4.9, 0.7, facecolor="#F4F5F6", edgecolor="#425563")
        )
        axis.add_patch(
            plt.Rectangle((8.4, y - 0.35), 2.1, 0.7, facecolor="#F5E6C8", edgecolor="#425563")
        )
        axis.text(1.45, y, name, ha="center", va="center", fontsize=10)
        axis.text(5.45, y, role, ha="center", va="center", fontsize=10)
        axis.text(9.45, y, detail, ha="center", va="center", fontsize=9)
        axis.annotate("", xy=(2.9, y), xytext=(2.55, y), arrowprops={"arrowstyle": "->"})
        axis.annotate("", xy=(8.3, y), xytext=(7.95, y), arrowprops={"arrowstyle": "->"})
    axis.set_title("轻量候选模型", fontsize=14, pad=8)
    figure.savefig(path)
    plt.close(figure)


def _save_selection(path: Path) -> None:
    figure, axis = plt.subplots(figsize=(10, 4.3))
    axis.set_xlim(0, 10)
    axis.set_ylim(0, 4.3)
    axis.axis("off")
    steps = (
        ("第一顺序", "验证集宏平均F1更高"),
        ("第二顺序", "错误关联更少"),
        ("第三顺序", "重复身份更少"),
        ("第四顺序", "参数数量更少"),
    )
    widths = (8.8, 7.2, 5.6, 4.0)
    colors = ("#D8E7F0", "#DCE9DF", "#F1E5CA", "#E7DDEB")
    for index, ((title, detail), width, color) in enumerate(zip(steps, widths, colors)):
        y = 3.45 - index * 0.85
        left = (10.0 - width) / 2.0
        axis.add_patch(
            plt.Rectangle((left, y - 0.28), width, 0.56, facecolor=color, edgecolor="#48545C")
        )
        axis.text(2.0, y, title, ha="center", va="center", fontsize=10, weight="bold")
        axis.text(5.4, y, detail, ha="center", va="center", fontsize=10)
    axis.text(5.0, 0.18, "门限只从0.3至0.9固定网格选择", ha="center", fontsize=10)
    figure.savefig(path)
    plt.close(figure)


def _save_result_figures(figures: Path, metrics: dict[str, Any]) -> list[Path]:
    generated: list[Path] = []
    methods = ("original_geometry", "selected_lightweight")
    labels = ("原始几何", "选定轻量模型")
    colors = ("#7C8A93", "#2D7194")
    assignment = metrics["assignment"]

    path = figures / "04_test_metrics.png"
    figure, axis = plt.subplots(figsize=(8.6, 4.8))
    x = np.arange(3)
    width = 0.34
    for index, method in enumerate(methods):
        values = [assignment[method][f"macro_{name}"] for name in ("precision", "recall", "f1")]
        axis.bar(x + (index - 0.5) * width, values, width, label=labels[index], color=colors[index])
    axis.set_xticks(x, ("准确率", "召回率", "F1"))
    axis.set_ylim(0.0, 1.05)
    axis.set_ylabel("宏平均")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    figure.savefig(path)
    plt.close(figure)
    generated.append(path)

    path = figures / "05_error_counts.png"
    figure, axis = plt.subplots(figsize=(8.6, 4.8))
    x = np.arange(2)
    width = 0.34
    for index, method in enumerate(methods):
        values = [
            assignment[method]["false_association_count"],
            assignment[method]["duplicate_identity_match_count"],
        ]
        axis.bar(x + (index - 0.5) * width, values, width, label=labels[index], color=colors[index])
    axis.set_xticks(x, ("错误关联", "重复身份"))
    axis.set_ylabel("累计数量")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    figure.savefig(path)
    plt.close(figure)
    generated.append(path)

    path = figures / "06_corruption_f1.png"
    figure, axis = plt.subplots(figsize=(8.6, 4.8))
    levels = list(metrics["corruption_levels"])
    x = np.arange(len(levels))
    for method, label, color in zip(methods, labels, colors):
        axis.plot(
            x,
            [metrics["assignment_by_corruption"][level][method]["macro_f1"] for level in levels],
            marker="o",
            linewidth=2,
            label=label,
            color=color,
        )
    axis.set_xticks(x, ("轻度", "中度", "重度"))
    axis.set_ylim(0.0, 1.05)
    axis.set_ylabel("宏平均F1")
    axis.legend()
    axis.grid(alpha=0.25)
    figure.savefig(path)
    plt.close(figure)
    generated.append(path)

    path = figures / "07_grouped_seed_ci.png"
    figure, axis = plt.subplots(figsize=(8.6, 4.0))
    for y, (method, label, color) in enumerate(zip(methods, labels, colors)):
        values = metrics["grouped_bootstrap_95ci"][method]["f1"]
        axis.errorbar(
            values["point"],
            y,
            xerr=[[values["point"] - values["lower"]], [values["upper"] - values["point"]]],
            fmt="o",
            capsize=5,
            color=color,
            label=label,
        )
    axis.set_yticks((0, 1), labels)
    axis.set_xlim(0.0, 1.05)
    axis.set_xlabel("按seed成组自举的F1与95%置信区间")
    axis.grid(axis="x", alpha=0.25)
    figure.savefig(path)
    plt.close(figure)
    generated.append(path)

    path = figures / "08_latency.png"
    figure, axis = plt.subplots(figsize=(7.5, 4.5))
    latency = metrics["latency_detail"]
    names = ("模型评分", "匈牙利求解")
    values = (
        latency["model_scoring"]["p95_ms"],
        latency["hungarian_assignment"]["p95_ms"],
    )
    axis.bar(names, values, color=("#2D7194", "#8A6B3E"))
    axis.set_ylabel("本机95%分位耗时/毫秒")
    axis.grid(axis="y", alpha=0.25)
    figure.savefig(path)
    plt.close(figure)
    generated.append(path)
    return generated


def _read_selected_validation_row(metrics: dict[str, Any]) -> dict[str, str] | None:
    freeze_path = Path(metrics["artifacts"]["freeze_manifest"])
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    leaderboard = freeze_path.parent / freeze["validation_leaderboard"]
    with leaderboard.open("r", encoding="utf-8", newline="") as handle:
        return next(csv.DictReader(handle), None)


def _result_text(metrics: dict[str, Any]) -> str:
    baseline = metrics["assignment"]["original_geometry"]
    selected = metrics["assignment"]["selected_lightweight"]
    ci = metrics["grouped_bootstrap_95ci"]["selected_minus_geometry"]["f1"]
    validation = _read_selected_validation_row(metrics)
    validation_text = ""
    if validation:
        validation_text = (
            f"验证阶段选定 `{validation['model_id']}`，概率门限为"
            f"{float(validation['probability_threshold']):.1f}。该门限来自验证集固定网格，"
            "不是设备通用指标。"
        )
    return f"""
## 冻结后结果

冻结后评估包含{metrics['independent_seed_count']}个独立seed、{metrics['test_sample_count']}份轻中重样本。三档腐化随各自seed成组进入自举统计，没有按三倍独立样本计算。{validation_text}

| 方法 | 宏平均准确率 | 宏平均召回率 | 宏平均F1 | 错误关联 | 重复身份 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原始几何代价 | {baseline['macro_precision']:.4f} | {baseline['macro_recall']:.4f} | {baseline['macro_f1']:.4f} | {baseline['false_association_count']} | {baseline['duplicate_identity_match_count']} |
| 选定轻量模型 | {selected['macro_precision']:.4f} | {selected['macro_recall']:.4f} | {selected['macro_f1']:.4f} | {selected['false_association_count']} | {selected['duplicate_identity_match_count']} |

![冻结后准确率、召回率和F1](figures/04_test_metrics.png)

![错误关联与重复身份](figures/05_error_counts.png)

轻、中、重三档F1分别统计如下。扰动是在已保存轨迹样本上离线注入，不能解释为真实探测器漏检率或虚警率。

![不同离线腐化等级的F1](figures/06_corruption_f1.png)

选定模型相对原始几何代价的F1差值为{ci['point']:.4f}，按seed成组自举的95%置信区间为[{ci['lower']:.4f}, {ci['upper']:.4f}]。独立seed不足时区间只反映当前有限样本，不构成算法定型依据。

![按seed成组的F1置信区间](figures/07_grouped_seed_ci.png)

本机中央处理器上，模型评分和匈牙利求解的95%分位耗时分别为{metrics['latency_detail']['model_scoring']['p95_ms']:.3f}毫秒和{metrics['latency_detail']['hungarian_assignment']['p95_ms']:.3f}毫秒。该数值是当前进程墙钟时间，会随处理器、负载和候选边数量变化。

![本机处理时延](figures/08_latency.png)
"""


def generate_report(
    output_dir: str | Path,
    *,
    metrics_path: str | Path | None = None,
    build_word: bool = True,
) -> Path:
    _configure_plotting()
    output_dir = Path(output_dir).resolve()
    figures = output_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    conceptual = (
        (figures / "01_algorithm_flow.png", _save_flow),
        (figures / "02_lightweight_models.png", _save_method_map),
        (figures / "03_validation_selection.png", _save_selection),
    )
    for path, generator in conceptual:
        generator(path)
    metrics: dict[str, Any] | None = None
    if metrics_path is not None:
        metrics = json.loads(Path(metrics_path).resolve().read_text(encoding="utf-8"))
        _save_result_figures(figures, metrics)

    if metrics is None:
        conclusion = (
            "轻量路线的模型、验证选择、冻结和报告链路已经实现，并通过匿名夹具自测。"
            "本报告不包含正式100目标测试结果，也不使用现有保留测试集形成结论。"
        )
        result = """
## 当前证据

当前证据仅来自单元测试夹具。夹具用于检查正负候选边、模型序列化、验证门限、测试集读取顺序、一对一约束和报告构建，不代表100目标AirSim性能。正式结果需要main提供冻结的数据清单和新增保留测试seed。
"""
        evidence_status = "fixture_only"
    else:
        conclusion = (
            "本报告给出冻结后轻量模型与原始几何代价的同输入对照。"
            "结论范围由独立seed数量和离线腐化来源限定。"
        )
        result = _result_text(metrics)
        evidence_status = metrics["evidence_status"]

    report = f"""# 双站光电100目标轻量关联试验

## 结论

{conclusion}

轻量模型不改变候选边。两侧匿名轨迹先经过共面、时间、重投影、交会角和条件数硬门控，再由轻量模型输出同目标概率。最终仍由带未匹配项的匈牙利算法给出一对一关系。真实身份、AirSim对象名称和真实三维位置不进入在线特征。

![算法流程](figures/01_algorithm_flow.png)

## 方法

第一类方法重新标定原几何代价中的8项归一化分量，并约束每项权重不小于零。第二类方法使用Platt标定，把原几何代价映射为概率。第三类方法使用单调回归，保持几何代价增大时同目标概率不升高。第四类方法对12维候选边特征做标准化，再使用带二范数约束的逻辑回归；正则强度固定测试0.01、0.1、1、10和100。

![轻量候选模型](figures/02_lightweight_models.png)

所有模型只在训练集拟合。验证集从0.3至0.9的固定概率网格选择未匹配门限。排序依次比较宏平均F1、错误关联、重复身份和参数数量。冻结清单写出前不打开测试图和测试标签。

![验证选择顺序](figures/03_validation_selection.png)

## 数据边界

在线输入沿用双站100目标图试验已经保存的匿名候选图，包括12维边特征、几何代价、候选边索引和匿名轨迹编号。几何硬门控、候选边和匈牙利一对一约束与图网络路线一致，因此两条路线可以在同一输入指纹上比较。

逐样本候选指纹直接使用图网络数据模块的公共函数。候选清单固定记录seed、腐化档次、逐样本候选指纹和在线图文件哈希，再按seed与腐化档次排序并计算规范JSON哈希。轻量评估同时输出统一的比较清单，图网络比较程序可以直接读取，不需要main手工转换。

轻、中、重三档漏检和虚警在AirSim测量保存完成后离线生成。它们用于控制对照条件，不是实测探测器误差分布。验证选出的概率门限属于当前数据和当前相机几何条件，换场景后必须重新验证。

{result}

## 验收口径

正式对比使用逐seed指标和按seed成组的95%置信区间。每个seed派生的轻、中、重三档样本共同组成一个统计组。报告同时保留数据指纹、模型指纹、统一候选图指纹、模型评分时延、匈牙利求解时延和失败原因。两路线的数据指纹、候选聚合指纹、测试seed或腐化档次有一项不一致，公共比较程序即拒绝计算结论。

图网络只有在相同新增测试seed上比最佳轻量方案的宏平均F1提高至少0.02、差值置信区间下限大于零、错误关联不增加且重复身份不增加时，才具备保留为可选路线的证据。本轻量试验不修改D1至D7，也不直接改变系统主线。

## 证据状态

`{evidence_status}`。AirSim测量、离线腐化和建议门限在正文中分别表述，夹具结果不作为正式性能数据。
"""
    report_path = output_dir / REPORT_NAME
    report_path.write_text(report, encoding="utf-8")
    manifest = {
        "schema_version": "dual-optical-100target-lightweight-figures-v1",
        "report": report_path.name,
        "evidence_status": evidence_status,
        "figures": [str(path.relative_to(output_dir)) for path in sorted(figures.glob("*.png"))],
    }
    (figures / "figure_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if build_word:
        build_word_report(report_path)
    return report_path
