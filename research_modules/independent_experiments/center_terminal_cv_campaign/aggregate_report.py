#!/usr/bin/env python3
"""Aggregate experiment metrics without hiding experiment-specific evidence."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping


EXPERIMENTS = ("search", "center_handover", "crossview")


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(item, child))
    elif isinstance(value, (list, tuple)):
        result[prefix] = json.dumps(value, ensure_ascii=False)
    else:
        result[prefix] = value
    return result


def _metric(metrics: Mapping[str, Any], *names: str) -> Any:
    flat = _flatten(metrics)
    for name in names:
        if name in flat:
            return flat[name]
        suffix = f".{name}"
        matches = [value for key, value in flat.items() if key.endswith(suffix)]
        if matches:
            return matches[0]
    return "未提供"


def aggregate_campaign(campaign_dir: Path) -> dict[str, Path]:
    loaded: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for experiment in EXPERIMENTS:
        path = campaign_dir / experiment / "metrics.json"
        if path.exists():
            loaded[experiment] = json.loads(path.read_text(encoding="utf-8"))
        else:
            missing.append(experiment)

    inventory_path = campaign_dir / "metric_inventory.csv"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    with inventory_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("experiment", "metric", "value"))
        writer.writeheader()
        for experiment, metrics in loaded.items():
            for key, value in sorted(_flatten(metrics).items()):
                writer.writerow(
                    {
                        "experiment": experiment,
                        "metric": key,
                        "value": value,
                    }
                )

    labels = {
        "search": "概率区域协同搜索",
        "center_handover": "中心双光电至机载航迹关联",
        "crossview": "拦截无人机跨视角关联",
    }
    summary_path = campaign_dir / "campaign_summary.json"
    summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.exists()
        else {}
    )
    scenario_paths = sorted((campaign_dir / "fixtures").glob("fixture_*/scenario.json"))
    scenario = (
        json.loads(scenario_paths[0].read_text(encoding="utf-8"))
        if scenario_paths
        else {}
    )
    mode_label = {
        "airsim": "真实AirSim ComputerVision运行",
        "offline": "离线几何夹具回归",
    }.get(str(summary.get("mode", "")), "未标明")
    lines = [
        "# 中心线索搜索与末端配准AirSim试验报告",
        "",
        "## 结论",
        "",
    ]
    if len(loaded) == len(EXPERIMENTS):
        search = loaded["search"]
        handover = loaded["center_handover"]
        crossview = loaded["crossview"]
        lines.extend(
            (
                f"本轮三项试验均完成。搜索发现{_metric(search, 'discovered_target_count')}/"
                f"{_metric(search, 'target_count')}个目标，并补获中心漏掉的"
                f"{_metric(search, 'center_missed_recovered_count')}/"
                f"{_metric(search, 'center_missed_target_count')}个目标。中心交接形成"
                f"{_metric(handover, 'true_binding_count')}条正确绑定，错误绑定为"
                f"{_metric(handover, 'false_binding_count')}。跨视角关联精确率为"
                f"{_format_number(_metric(crossview, 'association_precision'))}，召回率为"
                f"{_format_number(_metric(crossview, 'association_recall'))}，身份混合计数为"
                f"{_metric(crossview, 'id_switch_count')}。",
                "",
                "该结果验证的是仿真接口、搜索与配准算法，不代表真实光电装备的发现距离或实飞拦截效果。",
                "",
            )
        )
    lines.extend(
        (
        "## 试验条件",
        "",
        "| 项目 | 设置 |",
        "| --- | --- |",
        f"| 运行方式 | {mode_label} |",
        f"| 目标数量 | {summary.get('target_count', scenario.get('target_count', '未标明'))} |",
        f"| 搜索资源数量 | {summary.get('resource_count', '未标明')} |",
        f"| 随机种子 | {summary.get('seed', scenario.get('seed', '未标明'))} |",
        f"| 目标速度 | {scenario.get('target_speed_mps', '未标明')} 米/秒 |",
        f"| 目标最长尺寸 | {scenario.get('target_longest_dimension_m', '未标明')} 米 |",
        f"| AirSim时钟倍率 | {scenario.get('clock_speed', '未标明')} |",
        "| 中心相机 | 1280×1024，水平视场角3.67度 |",
        "| 机载相机 | 1920×1080，水平视场角19度 |",
        "| 中心线索 | 关联精度80%，召回率80% |",
        "| 视觉识别门限 | 检测框最长边不小于10像素 |",
        "",
        "## 试验边界",
        "",
        "本报告汇总三个相互隔离的ComputerVision试验。中心源线索的关联精度和召回率均按80%固定注入。识别条件为检测框最长边达到10像素。Actor名称和真实目标编号只用于离线评分，不进入在线搜索和配准。",
        "",
        "三个专项先分别统计，避免上游失败掩盖下游算法问题。汇总结果不能直接解释为真实光电装备的发现率或拦截能力。",
        "",
        "## 运行状态",
        "",
        "| 专项 | 指标文件 | 状态 |",
        "| --- | --- | --- |",
        )
    )
    for experiment in EXPERIMENTS:
        state = "已生成" if experiment in loaded else "缺失"
        lines.append(f"| {labels[experiment]} | `{experiment}/metrics.json` | {state} |")

    lines.extend(("", "## 试验结果", ""))
    if "search" in loaded:
        metrics = loaded["search"]
        lines.extend(
            (
                "### 概率区域协同搜索",
                "",
                f"搜索单元覆盖{_metric(metrics, 'covered_cell_count')}/"
                f"{_metric(metrics, 'search_cell_count')}，发现目标"
                f"{_metric(metrics, 'discovered_target_count')}/"
                f"{_metric(metrics, 'target_count')}。中心漏检目标补获"
                f"{_metric(metrics, 'center_missed_recovered_count')}/"
                f"{_metric(metrics, 'center_missed_target_count')}。",
                "",
                f"共读取{_metric(metrics, 'online_detection_count')}个匿名检测，其中"
                f"{_metric(metrics, 'below_ten_pixel_detection_count')}个未达到10像素门限。"
                f"两帧确认后形成{_metric(metrics, 'confirmed_handover_count')}条交接记录，"
                f"确认精度为{_format_number(_metric(metrics, 'confirmed_handover_precision'))}，"
                f"在线真值泄漏为{_metric(metrics, 'online_truth_leakage_count')}。",
                "",
            )
        )
    if "center_handover" in loaded:
        metrics = loaded["center_handover"]
        lines.extend(
            (
                "### 中心航迹与机载航迹交接",
                "",
                f"中心输入包含{_metric(metrics, 'correct_source_count')}条可信线索和"
                f"{_metric(metrics, 'false_source_count')}条错误线索。算法形成"
                f"{_metric(metrics, 'true_binding_count')}条正确绑定，错误绑定"
                f"{_metric(metrics, 'false_binding_count')}条，错误线索拒绝率为"
                f"{_format_number(_metric(metrics, 'false_source_rejection_rate'))}。",
                "",
                f"绑定精确率和对可信线索的召回率分别为"
                f"{_format_number(_metric(metrics, 'binding_precision'))}和"
                f"{_format_number(_metric(metrics, 'binding_recall'))}。注册目标占全部真实目标的"
                f"{_format_number(_metric(metrics, 'registered_target_fraction'))}，该比例受中心80%召回率约束。"
                f"在线真值泄漏为{_metric(metrics, 'truth_leakage_count')}。",
                "",
            )
        )
    if "crossview" in loaded:
        metrics = loaded["crossview"]
        lines.extend(
            (
                "### 拦截无人机跨视角关联",
                "",
                f"输入{_metric(metrics, 'recognized_track_count')}条可识别局部航迹。"
                f"几何门控保留{_metric(metrics, 'geometry_passed_edge_count')}条候选关系，"
                f"最终确认{_metric(metrics, 'confirmed_relation_count')}条关系。",
                "",
                f"离线评分得到正确关系{_metric(metrics, 'true_positive_relations')}条、"
                f"错误关系{_metric(metrics, 'false_positive_relations')}条、漏关联"
                f"{_metric(metrics, 'false_negative_relations')}条。关联精确率为"
                f"{_format_number(_metric(metrics, 'association_precision'))}，召回率为"
                f"{_format_number(_metric(metrics, 'association_recall'))}，身份混合计数为"
                f"{_metric(metrics, 'id_switch_count')}。在线真值泄漏为"
                f"{_metric(metrics, 'truth_leakage_count')}。",
                "",
            )
        )
    if missing:
        lines.extend(
            (
                "## 未完成项",
                "",
                "以下专项尚未形成统一指标文件：" + "、".join(labels[item] for item in missing) + "。",
                "",
            )
        )
    lines.extend(
        (
            "## 结论口径",
            "",
            "搜索结果重点看中心漏检目标能否由空档搜索补获。中心交接重点看错误源航迹能否被拒绝。机间配准重点看局部视场重叠、目标交叉和无共同目标时是否保持正确关系或待确认。图神经网络只作为候选排序对照，不能绕过几何门控和一一约束。",
            "",
        )
    )
    report_path = campaign_dir / "CAMPAIGN_REPORT_CN.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {"report": report_path, "metric_inventory": inventory_path}


def _format_number(value: Any) -> str:
    if isinstance(value, (float, int)):
        return f"{float(value):.3f}"
    return str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for name, path in aggregate_campaign(args.campaign_dir).items():
        print(f"{name}={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
