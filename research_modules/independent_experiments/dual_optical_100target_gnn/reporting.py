"""Chinese figures and report for the independent GNN benchmark."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
import warnings

import matplotlib

matplotlib.use("Agg")
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
    import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


REPORT_NAME = "DUAL_OPTICAL_100TARGET_GNN_REPORT_CN.md"


def _configure_chinese_font() -> None:
    candidates = (
        "Noto Sans CJK JP",
        "Noto Sans CJK SC",
        "Source Han Sans CN",
        "Droid Sans Fallback",
        "WenQuanYi Micro Hei",
        "Microsoft YaHei",
        "SimHei",
    )
    installed = {font.name for font in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            plt.rcParams["font.sans-serif"] = [name]
            break
    plt.rcParams["axes.unicode_minus"] = False


def _save(fig: plt.Figure, path: Path) -> None:
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _draw_flow(path: Path) -> None:
    fig, axis = plt.subplots(figsize=(12, 4.8))
    axis.set_xlim(0, 12)
    axis.set_ylim(0, 5)
    axis.axis("off")
    boxes = [
        (0.4, "双站匿名\n本地轨迹"),
        (2.6, "漏检与虚警\n可复现注入"),
        (4.8, "共面性等\n几何硬门控"),
        (7.0, "两层图网络\n判断候选边"),
        (9.2, "混合代价与\n匈牙利分配"),
    ]
    for x, text in boxes:
        axis.add_patch(
            plt.Rectangle((x, 1.8), 1.7, 1.3, facecolor="#E7F0F7", edgecolor="#356A8A", linewidth=1.5)
        )
        axis.text(x + 0.85, 2.45, text, ha="center", va="center", fontsize=12)
    for x in (2.1, 4.3, 6.5, 8.7):
        axis.annotate("", xy=(x + 0.45, 2.45), xytext=(x, 2.45), arrowprops=dict(arrowstyle="->", lw=1.8, color="#333333"))
    axis.text(6.0, 4.25, "离线真值只生成训练标签和评估结果，不进入在线特征", ha="center", fontsize=13, color="#8A3B2D")
    axis.text(6.0, 0.65, "输出仍是一对一关系；候选不可靠时允许不匹配", ha="center", fontsize=12)
    _save(fig, path)


def _draw_graph(path: Path) -> None:
    fig, axis = plt.subplots(figsize=(10, 6))
    axis.axis("off")
    y_a = np.linspace(0.15, 0.85, 6)
    y_b = np.linspace(0.12, 0.88, 7)
    for index, y in enumerate(y_a):
        axis.scatter([0.18], [y], s=650, color="#4E79A7", edgecolor="white", zorder=3)
        axis.text(0.18, y, f"A{index+1}", ha="center", va="center", color="white", fontsize=10)
    for index, y in enumerate(y_b):
        axis.scatter([0.82], [y], s=650, color="#E07B53", edgecolor="white", zorder=3)
        axis.text(0.82, y, f"B{index+1}", ha="center", va="center", color="white", fontsize=10)
    links = [(0, 0), (0, 2), (1, 1), (1, 3), (2, 2), (2, 4), (3, 3), (3, 5), (4, 4), (5, 5), (5, 6)]
    for left, right in links:
        axis.plot([0.22, 0.78], [y_a[left], y_b[right]], color="#A8B3BA", linewidth=1.3, zorder=1)
    for left, right in ((0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5)):
        axis.plot([0.22, 0.78], [y_a[left], y_b[right]], color="#2E8B57", linewidth=3.0, zorder=2)
    axis.text(0.18, 0.98, "A站轨迹节点", ha="center", fontsize=13, weight="bold")
    axis.text(0.82, 0.98, "B站轨迹节点", ha="center", fontsize=13, weight="bold")
    axis.text(0.50, 0.05, "灰线是几何门控保留的候选，绿线表示最终一对一关系", ha="center", fontsize=12)
    _save(fig, path)


def _draw_corruption(path: Path) -> None:
    levels = ["轻度", "中度", "重度"]
    miss = [3, 7, 12]
    transient = [1, 2, 4]
    persistent = [0, 1, 2]
    x = np.arange(3)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    axes[0].bar(x, miss, color=["#7CB5A1", "#E2B66D", "#CF6F64"])
    axes[0].set_xticks(x, levels)
    axes[0].set_ylabel("随机漏检比例（%）")
    axes[0].set_title("漏检强度")
    width = 0.34
    axes[1].bar(x - width / 2, transient, width, label="每半程瞬时虚警", color="#6D9BC3")
    axes[1].bar(x + width / 2, persistent, width, label="每相机持续假轨迹", color="#B87861")
    axes[1].set_xticks(x, levels)
    axes[1].set_ylabel("数量")
    axes[1].set_title("虚警强度")
    axes[1].legend(frameon=False)
    for axis in axes:
        axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    _save(fig, path)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _draw_results(figures: Path, metrics: dict[str, Any], metrics_path: Path) -> list[str]:
    generated = []
    per_sample = metrics_path.parent / metrics["artifacts"]["per_sample_metrics"]
    failures = metrics_path.parent / metrics["artifacts"]["failure_reasons"]
    candidates = metrics_path.parent / metrics["artifacts"]["candidate_edge_scores"]
    training_history = metrics_path.parent / metrics["artifacts"]["training_history"]
    rows = _read_rows(per_sample)
    failure_rows = _read_rows(failures)
    candidate_rows = _read_rows(candidates)
    history_rows = _read_rows(training_history)
    modes = ["geometry", "learned", "hybrid"]
    mode_names = {"geometry": "确定性几何", "learned": "学习代价", "hybrid": "混合代价"}
    levels = ["light", "medium", "heavy"]
    level_names = {"light": "轻度", "medium": "中度", "heavy": "重度"}
    selected_route = metrics.get("formal_selection", {}).get("selected_route", "hybrid")

    fig, axis = plt.subplots(figsize=(9, 4.8))
    x = np.arange(len(levels))
    width = 0.24
    for index, mode in enumerate(modes):
        values = [
            np.mean([float(row["f1"]) for row in rows if row["mode"] == mode and row["corruption_level"] == level])
            for level in levels
        ]
        axis.bar(x + (index - 1) * width, values, width, label=mode_names[mode])
    axis.set_xticks(x, [level_names[level] for level in levels])
    axis.set_ylim(0.0, 1.05)
    axis.set_ylabel("关联F1")
    axis.set_title("独立测试集关联结果")
    axis.legend(frameon=False)
    axis.grid(axis="y", alpha=0.25)
    path = figures / "04_f1_by_corruption.png"
    _save(fig, path)
    generated.append(path.name)

    reasons = sorted({row["reason"] for row in failure_rows})
    translations = {
        "missing_stable_track": "稳定轨迹缺失",
        "geometry_gate_rejected": "几何门控拒绝",
        "assignment_conflict": "全局分配冲突",
        "false_association": "错误关联",
        "selected_false_track": "假轨迹入选",
        "duplicate_identity": "身份重复",
    }
    fig, axis = plt.subplots(figsize=(9, 4.8))
    bottom = np.zeros(len(levels), dtype=float)
    for reason in reasons:
        values = np.asarray(
            [
                sum(
                    int(row["count"])
                    for row in failure_rows
                    if row["mode"] == selected_route
                    and row["reason"] == reason
                    and row["corruption_level"] == level
                )
                for level in levels
            ],
            dtype=float,
        )
        axis.bar(
            np.arange(len(levels)),
            values,
            bottom=bottom,
            label=translations.get(reason, reason),
        )
        bottom += values
    axis.set_xticks(np.arange(len(levels)), [level_names[level] for level in levels])
    axis.set_ylabel("累计次数")
    axis.set_title("各干扰档正式路线失败原因")
    axis.legend(frameon=False, ncol=2, fontsize=9)
    axis.grid(axis="y", alpha=0.25)
    path = figures / "05_failure_reasons.png"
    _save(fig, path)
    generated.append(path.name)

    devices = [name for name in ("cpu", "gpu") if metrics["latency"][name].get("available")]
    fig, axis = plt.subplots(figsize=(7, 4.5))
    x = np.arange(len(devices))
    p50 = [metrics["latency"][name]["p50_ms"] for name in devices]
    p95 = [metrics["latency"][name]["p95_ms"] for name in devices]
    axis.bar(x - 0.18, p50, 0.36, label="中位数")
    axis.bar(x + 0.18, p95, 0.36, label="95%分位")
    axis.set_xticks(x, [name.upper() for name in devices])
    axis.set_ylabel("图网络前向耗时（毫秒）")
    axis.set_title("推理耗时")
    axis.legend(frameon=False)
    axis.grid(axis="y", alpha=0.25)
    path = figures / "06_inference_latency.png"
    _save(fig, path)
    generated.append(path.name)

    fig, axis = plt.subplots(figsize=(7.5, 4.5))
    axis.plot(
        [int(row["epoch"]) for row in history_rows],
        [float(row["train_loss"]) for row in history_rows],
        label="训练损失",
        linewidth=2.0,
    )
    axis.plot(
        [int(row["epoch"]) for row in history_rows],
        [float(row["val_loss"]) for row in history_rows],
        label="验证损失",
        linewidth=2.0,
    )
    axis.set_xlabel("训练轮次")
    axis.set_ylabel("加权二元交叉熵")
    axis.set_title("训练和早停过程")
    axis.legend(frameon=False)
    axis.grid(alpha=0.25)
    path = figures / "07_training_history.png"
    _save(fig, path)
    generated.append(path.name)

    fig, axis = plt.subplots(figsize=(7.5, 4.8))
    for level in levels:
        selected = [row for row in candidate_rows if row["corruption_level"] == level]
        labels = np.asarray([int(row["offline_label"]) for row in selected])
        scores = np.asarray([float(row["probability"]) for row in selected])
        order = np.argsort(-scores, kind="mergesort")
        ordered = labels[order]
        true_positive = np.cumsum(ordered)
        false_positive = np.cumsum(1 - ordered)
        precision = true_positive / np.maximum(true_positive + false_positive, 1)
        recall = true_positive / max(int(np.sum(labels)), 1)
        axis.step(recall, precision, where="post", label=level_names[level])
    axis.set_xlim(0.0, 1.02)
    axis.set_ylim(0.0, 1.02)
    axis.set_xlabel("候选边召回率")
    axis.set_ylabel("候选边准确率")
    axis.set_title("候选边精确率-召回率曲线")
    axis.legend(frameon=False)
    axis.grid(alpha=0.25)
    path = figures / "08_candidate_pr_curve.png"
    _save(fig, path)
    generated.append(path.name)
    return generated


def _training_summary(metrics: dict[str, Any], metrics_path: Path | None) -> tuple[int, int]:
    if metrics_path is None:
        return 0, 0
    relative = metrics.get("artifacts", {}).get("training_history")
    if not relative:
        return 0, 0
    history_path = metrics_path.parent / relative
    if not history_path.is_file():
        return 0, 0
    rows = _read_rows(history_path)
    if not rows:
        return 0, 0
    best = min(rows, key=lambda row: float(row["val_loss"]))
    return len(rows), int(best["epoch"])


def _result_section(
    metrics: dict[str, Any] | None,
    metrics_path: Path | None = None,
    comparison: dict[str, Any] | None = None,
) -> str:
    if metrics is None:
        return """## 当前证据

本目录已经完成算法、数据隔离、训练冻结、评估和报告接口。本次报告调用没有提供评估指标文件，因此不在这里转录关联精度、召回率和推理耗时。正式结果必须通过`--metrics`明确指定冻结模型对应的评估文件，不能用单元测试夹具替代。

扩展正式协议固定使用8个训练种子和2个验证种子，并保留至少20个全新测试种子。模型冻结前不得打开测试图或测试标签。本节没有新增AirSim测试结果，也不据夹具结果判断正式性能。
"""
    assignment = metrics["assignment"]
    promotion = metrics["promotion"]
    rows = []
    names = {"geometry": "确定性几何", "learned": "学习代价", "hybrid": "混合代价"}
    level_names = {"light": "轻度", "medium": "中度", "heavy": "重度"}
    for mode in ("geometry", "learned", "hybrid"):
        item = assignment[mode]
        rows.append(
            f"| {names[mode]} | {item['macro_precision']:.4f} | {item['macro_recall']:.4f} | {item['macro_f1']:.4f} | {item['false_association_count']} | {item['duplicate_identity_match_count']} |"
        )
    level_rows = []
    for level in ("light", "medium", "heavy"):
        for mode in ("geometry", "learned", "hybrid"):
            item = metrics["assignment_by_corruption"][level][mode]
            level_rows.append(
                f"| {level_names[level]} | {item['sample_count']} | {names[mode]} | "
                f"{item['macro_precision']:.4f} | {item['macro_recall']:.4f} | "
                f"{item['macro_f1']:.4f} | {item['false_association_count']} | "
                f"{item['duplicate_identity_match_count']} |"
            )
    selected_route = metrics.get("formal_selection", {}).get("selected_route", "hybrid")
    selected_name = names[selected_route]
    probability_threshold = metrics.get("formal_selection", {}).get(
        "selected_probability_threshold"
    )
    threshold_text = (
        f"验证集选出的概率门限为{float(probability_threshold):.1f}"
        if probability_threshold is not None
        else "旧版冻结清单未记录概率门限"
    )
    duplicate_identity_pass = promotion.get(
        "duplicate_identity_non_increase",
        assignment[selected_route]["duplicate_identity_match_count"]
        <= assignment["geometry"]["duplicate_identity_match_count"],
    )
    if comparison is not None:
        recommendation = (
            "满足进入下一轮隔离工程验证条件"
            if comparison.get("recommend_continue_toward_mainline")
            else "暂不满足进入下一轮隔离工程验证条件"
        )
        comparison_text = (
            f"外部轻量方案为`{comparison['external_baseline_method_id']}`。图网络正式路线相对该方案的宏平均F1变化为"
            f"{comparison['criteria']['macro_f1_delta']:+.4f}；按完整seed成组重采样后，F1差值95%置信区间下限大于0="
            f"{comparison['criteria']['paired_f1_ci_lower_above_zero']}。最终判定：**{recommendation}**。"
        )
    elif metrics.get("evidence_status") == "expanded_formal_reserved_test":
        recommendation = "等待外部最佳轻量方案同输入比较"
        comparison_text = (
            "本轮只完成图网络正式路线评估。最终promotion必须读取轻量方案的独立比较清单，并核对数据指纹、候选图指纹、测试seed和腐化档次完全一致；在该比较完成前不作进入主线判断。"
        )
    else:
        recommendation = (
            "满足进入下一轮隔离工程验证条件"
            if promotion["recommend_continue_toward_mainline"] and duplicate_identity_pass
            else "暂不满足进入下一轮隔离工程验证条件"
        )
        comparison_text = f"本轮判断：**{recommendation}**。该判断只使用确定性几何方案作为本地参考。"
    completed_epochs, best_epoch = _training_summary(metrics, metrics_path)
    per_level_samples = int(
        metrics["assignment_by_corruption"]["light"]["geometry"]["sample_count"]
    )
    training_text = (
        f"模型共训练{completed_epochs}轮，最低验证损失出现在第{best_epoch}轮。"
        if completed_epochs and best_epoch
        else "训练轮次信息未随评估结果提供。"
    )
    cpu_p95 = metrics["latency"]["cpu"].get("p95_ms")
    gpu_p95 = metrics["latency"]["gpu"].get("p95_ms")
    latency_text = (
        f"图网络前向推理95%分位耗时为：中央处理器{cpu_p95:.2f}毫秒，"
        f"图形处理器{gpu_p95:.2f}毫秒。"
        if cpu_p95 is not None and gpu_p95 is not None
        else "本轮没有同时取得中央处理器和图形处理器时延。"
    )
    formal_audit = ""
    if metrics.get("evidence_status") in {
        "formal_reserved_test",
        "legacy_formal_reserved_test",
    }:
        formal_audit = f"""

主调度程序对候选边特征做了额外审计。仅使用`coplanarity_median_mrad`这一项共面残差中位数，测试集候选边平均精确率约为0.992，已经接近图网络的{metrics['candidate_edge_auprc_macro']:.4f}。这说明当前场景中的大部分区分能力可能来自共面几何特征和代价标定，现有两测试种子不足以证明必须采用图神经网络。下一轮应在相同候选边和相同匈牙利约束下，增加逻辑回归、单调概率标定和重新标定几何代价等轻量基线。
"""
    return f"""## 独立测试结果

测试集仅包含{len(metrics['test_seeds'])}个独立AirSim种子：{', '.join(str(seed) for seed in metrics['test_seeds'])}。轻、中、重三档分别形成{per_level_samples}个样本，合计{metrics['test_sample_count']}个样本。表中P、R和F1为每档样本的宏平均，错误关联和身份重复为累计值。候选边宏平均精确率-召回率曲线下面积为{metrics['candidate_edge_auprc_macro']:.4f}。验证集选出的正式路线为{selected_name}，{threshold_text}。该概率门限在求解前转换为负对数代价。

### 总体结果

| 方法 | P | R | F1 | 错误关联 | 身份重复 |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

### 分档结果

| 档次 | 样本数 | 方法 | P | R | F1 | 错误关联 | 身份重复 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(level_rows)}

![不同干扰强度下的关联结果](figures/04_f1_by_corruption.png)

![正式路线失败原因](figures/05_failure_reasons.png)

![图网络推理耗时](figures/06_inference_latency.png)

![训练和早停过程](figures/07_training_history.png)

![候选边精确率-召回率曲线](figures/08_candidate_pr_curve.png)

{training_text}{latency_text}

{selected_name}相对确定性几何方案的宏平均F1变化为{promotion['macro_f1_delta']:+.4f}。本地检查结果为：F1提升不少于2个百分点={promotion['f1_improvement_at_least_0_02']}，错误关联不增加={promotion['false_association_non_increase']}，重复真实身份数不高于几何基线={duplicate_identity_pass}（正式路线{assignment[selected_route]['duplicate_identity_match_count']}，几何基线{assignment['geometry']['duplicate_identity_match_count']}），图形处理器95%分位耗时不超过100毫秒={promotion['gpu_p95_at_most_100_ms']}。{comparison_text}该判断只允许继续开展隔离工程验证，不表示图网络已经可以替换确定性主线。{formal_audit}

三档漏检和虚警是在AirSim回合保存完成后，对本地轨迹样本离线注入。它们不是AirSim检测器产生的真实误识别分布。离线评分显示本地轨迹多数具有较高纯度，但仍存在低纯度轨迹；多数身份标签会把这部分混合轨迹压缩成单一监督身份，可能给训练和评估引入标签噪声。
"""


def generate_report(
    output_dir: str | Path,
    *,
    metrics_path: str | Path | None = None,
    comparison_path: str | Path | None = None,
) -> Path:
    _configure_chinese_font()
    output_dir = Path(output_dir).resolve()
    figures = output_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    _draw_flow(figures / "01_algorithm_flow.png")
    _draw_graph(figures / "02_bipartite_graph.png")
    _draw_corruption(figures / "03_corruption_levels.png")
    metrics = None
    if metrics_path is not None:
        metrics_path = Path(metrics_path).resolve()
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        _draw_results(figures, metrics, metrics_path)
    comparison = None
    if comparison_path is not None:
        comparison_path = Path(comparison_path).resolve()
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))

    report = f"""# 双站光电100目标图网络关联试验

## 结论

本试验把双站各自形成的匿名轨迹组织成一张二部图。图网络只负责判断候选轨迹属于同一目标的可能性，不能直接发布配准关系。最终关系仍由几何硬门控和匈牙利算法共同约束，允许可疑轨迹保持未匹配。

当前工作是独立算法试验，与D1至D7没有数据合同和运行依赖。离线身份只用于训练标签和结果评分，在线图中没有AirSim场景对象名称、真实身份或真实三维位置。

![算法链路](figures/01_algorithm_flow.png)

## 场景与问题

正式场景包含100个移动目标。双站扫描、漏检和轨迹中断会使每侧本地轨迹数与真实目标数不同；持续虚警还会形成没有真实目标来源的假轨迹。因此关联对象是两侧实际形成的轨迹，不是固定的100乘100目标编号表。

三档腐化在AirSim回合保存完成后，从同一批本地轨迹样本离线生成。轻度随机丢弃3%的轨迹样本，每个扫描半程加入1个瞬时虚警；中度为7%、2个瞬时虚警和每相机1条持续假轨迹；重度为12%、4个瞬时虚警和每相机2条持续假轨迹。持续假轨迹至少跨越4个扫描半程。这套设置用于可控对照，不代表AirSim检测器或真实光电设备的误识别分布。

![漏检和虚警设置](figures/03_corruption_levels.png)

## 二部图

A站和B站的本地轨迹分别位于图的两侧。每个轨迹节点记录样本数量、持续时间、扫描次数、方位和俯仰变化、角速度、缺失比例与检测稳定度。节点名称只用于定位匿名轨迹，不作为模型输入。

两条轨迹通过几何粗筛后形成一条候选边。边上记录共面残差的中位数、90%分位数、离散程度和变化斜率，以及时间重叠、重投影误差、拟合速度、条件数、交会角和运动一致性。共面残差超过0.50毫弧度、时间不足、重投影过大或几何条件差的候选直接拒绝。

![二部图示意](figures/02_bipartite_graph.png)

## 图网络

节点和边特征先映射到64维。两层消息传递让一条轨迹参考周围竞争候选，再由边分类器输出同一目标概率。训练采用加权二元交叉熵，优化器为AdamW，学习率为0.001，权重衰减为0.0001，最多训练80轮；验证损失连续10轮不改善时停止。

学习概率不能跨过几何硬门控。纯学习方案使用概率的负对数作为边代价；混合方案使用40%几何代价和60%学习代价。三种方案都使用带未匹配项的匈牙利算法，保证每条A站轨迹最多对应一条B站轨迹。

## 数据隔离

扩展正式协议固定使用20260820至20260827共8个训练种子，以及20260828和20260829两个验证种子。测试集由main另行保留至少20个全新种子，不复用旧报告中的20260830和20260831。归一化统计量只由训练图计算；训练程序完成早停、验证集路线选择并写出冻结清单后，评估程序才允许打开测试图和离线标签。

{_result_section(metrics, metrics_path if isinstance(metrics_path, Path) else None, comparison)}

## 验收规则

进入下一轮隔离工程验证必须同时满足四个条件：宏平均F1相对确定性几何方案提高至少0.02；错误关联数量不增加；重复真实身份数量不高于几何基线；图形处理器推理耗时95%分位不超过100毫秒。通过四项条件只代表可以继续扩大独立测试，不构成替换确定性主线的依据。

## 限制

漏检和虚警是在已保存的本地轨迹样本上离线注入，用于保持三种算法输入一致。它不能替代传感器真实漏检和虚警分布。本地轨迹多数纯度较高，但低纯度轨迹采用多数身份作为监督标签，仍可能引入标签噪声。图网络结果受训练场景覆盖范围影响，换用不同目标密度、扫描周期、双站基线或相机参数后需要重新验证。

在完成逻辑回归、概率标定和几何代价再标定对照前，不能判断图网络的消息传递是否带来独立收益。本试验不修改D1至D7，也不把离线身份、AirSim场景对象名称或真实位置作为在线特征。
"""
    report_path = output_dir / REPORT_NAME
    report_path.write_text(report, encoding="utf-8")
    figure_manifest = {
        "schema_version": "dual-optical-100target-gnn-figure-manifest-v1",
        "report": report_path.name,
        "formal_metrics_present": metrics is not None,
        "figures": [str(path.relative_to(output_dir)) for path in sorted(figures.glob("*.png"))],
    }
    (figures / "figure_manifest.json").write_text(
        json.dumps(figure_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_path
