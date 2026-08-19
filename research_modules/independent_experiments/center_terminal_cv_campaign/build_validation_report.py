#!/usr/bin/env python3
"""Build one Chinese comparison report from real five- and twenty-target runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


EXPERIMENTS = ("search", "center_handover", "crossview")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_campaign(path: Path) -> dict[str, Any]:
    metrics = {
        name: _read(path / name / "metrics.json")
        for name in EXPERIMENTS
    }
    fixture_paths = sorted((path / "fixtures").glob("fixture_*/scenario.json"))
    if not fixture_paths:
        raise FileNotFoundError(f"scenario fixture missing below {path}")
    return {
        "path": path,
        "summary": _read(path / "campaign_summary.json"),
        "scenario": _read(fixture_paths[0]),
        "metrics": metrics,
    }


def _number(value: Any, digits: int = 3) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _value(campaign: Mapping[str, Any], experiment: str, key: str) -> Any:
    return campaign["metrics"][experiment].get(key, "未提供")


def _recognized_target_count(campaign: Mapping[str, Any]) -> Any:
    metrics = campaign["metrics"]["search"]
    return metrics.get(
        "recognized_target_count",
        metrics.get("discovered_target_count", "未提供"),
    )


def build_report(
    smoke_dir: Path,
    formal_dir: Path,
    output_path: Path,
    *,
    prior_formal_dirs: Sequence[Path] = (),
) -> Path:
    smoke = _load_campaign(smoke_dir)
    formal = _load_campaign(formal_dir)
    if smoke["summary"].get("mode") != "airsim" or formal["summary"].get("mode") != "airsim":
        raise ValueError("comparison report accepts real AirSim campaign outputs only")

    lines = [
        "# 中心线索搜索与末端配准AirSim验证报告",
        "",
        "## 1. 结论",
        "",
        f"5目标冒烟和20目标正式试验均在真实AirSim ComputerVision模式下完成。"
        f"20目标搜索有{_recognized_target_count(formal)}/20个目标至少一次达到识别门限，"
        f"其中{_value(formal, 'search', 'discovered_target_count')}/20个通过连续确认，"
        f"中心漏掉的目标补获"
        f"{_value(formal, 'search', 'center_missed_recovered_count')}/"
        f"{_value(formal, 'search', 'center_missed_target_count')}。"
        f"中心交接正确绑定{_value(formal, 'center_handover', 'true_binding_count')}条可信线索，"
        f"错误绑定为{_value(formal, 'center_handover', 'false_binding_count')}。",
        "",
        f"20目标跨视角关联得到{_value(formal, 'crossview', 'true_positive_relations')}条正确关系、"
        f"{_value(formal, 'crossview', 'false_positive_relations')}条错误关系和"
        f"{_value(formal, 'crossview', 'false_negative_relations')}条漏关联。"
        f"关联精确率为{_number(_value(formal, 'crossview', 'association_precision'))}，"
        f"召回率为{_number(_value(formal, 'crossview', 'association_recall'))}。"
        "搜索漏确认和跨视角漏关联均与detect缺帧及短航迹有关，仍需独立多seed标定。",
        "",
        "本试验使用AirSim自带检测元数据验证搜索和几何关联流程。Actor名称只进入离线评分文件。结果不能等同于真实探测器性能、实飞搜索概率或物理拦截效果。",
        "",
        "## 2. 场景配置",
        "",
        "| 项目 | 设置 |",
        "| --- | --- |",
        "| 仿真模式 | AirSim ComputerVision |",
        f"| 目标数量 | 冒烟{smoke['summary']['target_count']}，正式{formal['summary']['target_count']} |",
        f"| 搜索资源 | {formal['summary']['resource_count']}个机载相机节点 |",
        f"| 目标速度 | {formal['scenario']['target_speed_mps']}米/秒 |",
        f"| 目标尺寸 | 最长边{formal['scenario']['target_longest_dimension_m']}米 |",
        f"| 时钟倍率 | {formal['scenario']['clock_speed']} |",
        "| 中心相机 | 1280×1024，水平视场角3.67度 |",
        "| 机载相机 | 1920×1080，水平视场角19度，前移0.5米 |",
        "| 中心线索 | 精度80%，召回率80%，固定注入 |",
        "| 识别门限 | 检测框最长边不小于10像素 |",
        f"| 随机种子 | {formal['summary']['seed']} |",
        "",
        "一次Blocks进程内依次执行搜索、中心交接和机间配准。每项试验前执行reset，重新设置相机视场角、相机位姿和Actor运动状态。三个专项分别评分，避免上游失败掩盖下游算法问题。",
        "",
        "## 3. 算法流程",
        "",
        "中心80%精度、80%召回率线索先形成带协方差和有效期的概率区域。搜索资源按预期发现收益、转向代价、到达代价和重复覆盖代价进行匈牙利分配。检测框达到10像素并连续两帧出现后，输出匿名局部航迹。",
        "",
        "中心交接将线索按时间外推到机载相机，经过坐标变换投影到图像平面，再以马氏距离、时间一致性和运动一致性筛选候选。匈牙利算法解决一对多冲突。本轮连续采集5帧，在最近3帧内至少2帧一致后确认绑定。",
        "",
        "机间配准先在每个相机内形成匿名短航迹，再用时间对齐、空间视线交会、重投影误差、运动连续性和尺度变化筛选跨视角关系。候选通过匈牙利分配和连续确认后组成统一目标簇。成熟目标簇需要多相机冗余证据，短航迹需要同一目标簇内至少两台相机支持。图神经网络没有进入本轮默认路径。",
        "",
        "## 4. 指标结果",
        "",
        "### 4.1 搜索",
        "",
        "| 指标 | 5目标 | 20目标 |",
        "| --- | ---: | ---: |",
    ]
    search_keys = (
        ("达到10像素的目标", "recognized_target_count"),
        ("发现目标", "discovered_target_count"),
        ("目标发现率", "target_discovery_recall"),
        ("中心漏检目标", "center_missed_target_count"),
        ("补获中心漏检目标", "center_missed_recovered_count"),
        ("低于10像素检测", "below_ten_pixel_detection_count"),
        ("确认记录精度", "confirmed_handover_precision"),
    )
    for label, key in search_keys:
        smoke_value = (
            _recognized_target_count(smoke)
            if key == "recognized_target_count"
            else _value(smoke, "search", key)
        )
        formal_value = (
            _recognized_target_count(formal)
            if key == "recognized_target_count"
            else _value(formal, "search", key)
        )
        lines.append(
            f"| {label} | {_number(smoke_value)} | {_number(formal_value)} |"
        )

    lines.extend(
        (
            "",
            "### 4.2 中心交接",
            "",
            "| 指标 | 5目标 | 20目标 |",
            "| --- | ---: | ---: |",
        )
    )
    handover_keys = (
        ("可信源线索", "correct_source_count"),
        ("错误源线索", "false_source_count"),
        ("正确绑定", "true_binding_count"),
        ("错误绑定", "false_binding_count"),
        ("绑定精确率", "binding_precision"),
        ("错误源拒绝率", "false_source_rejection_rate"),
    )
    for label, key in handover_keys:
        lines.append(
            f"| {label} | {_number(_value(smoke, 'center_handover', key))} | "
            f"{_number(_value(formal, 'center_handover', key))} |"
        )

    lines.extend(
        (
            "",
            "### 4.3 跨视角关联",
            "",
            "| 指标 | 5目标 | 20目标 |",
            "| --- | ---: | ---: |",
        )
    )
    crossview_keys = (
        ("可识别局部航迹", "recognized_track_count"),
        ("正确关系", "true_positive_relations"),
        ("错误关系", "false_positive_relations"),
        ("漏关联", "false_negative_relations"),
        ("关联精确率", "association_precision"),
        ("关联召回率", "association_recall"),
        ("身份混合", "id_switch_count"),
    )
    for label, key in crossview_keys:
        lines.append(
            f"| {label} | {_number(_value(smoke, 'crossview', key))} | "
            f"{_number(_value(formal, 'crossview', key))} |"
        )

    comparison_campaigns = [_load_campaign(path) for path in prior_formal_dirs]
    comparison_campaigns.append(formal)
    if len(comparison_campaigns) > 1:
        lines.extend(
            (
                "",
                "## 5. 逐步修复记录",
                "",
                "| 运行目录 | 搜索发现 | 中心正确绑定 | 跨视角精确率 | 跨视角召回率 | 身份混合 |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            )
        )
        for item in comparison_campaigns:
            lines.append(
                f"| {item['path'].name} | "
                f"{_value(item, 'search', 'discovered_target_count')}/20 | "
                f"{_value(item, 'center_handover', 'true_binding_count')}/16 | "
                f"{_number(_value(item, 'crossview', 'association_precision'))} | "
                f"{_number(_value(item, 'crossview', 'association_recall'))} | "
                f"{_value(item, 'crossview', 'id_switch_count')} |"
            )
        lines.extend(
            (
                "",
                "这些运行对应逐步修复过程，算法和观察窗口并不完全相同，因此不计算均值或置信区间。表格用于说明问题如何暴露和关闭，也显示AirSim detect在相同seed下仍有运行间波动。",
                "",
            )
        )

    smoke_rel = smoke_dir.name + "/crossview/figures/03_crossview_relation_graph.png"
    formal_rel = formal_dir.name + "/crossview/figures/03_crossview_relation_graph.png"
    lines.extend(
        (
            "",
            "## 6. 图形证据",
            "",
            f"![5目标跨视角关系]({smoke_rel})",
            "",
            f"![20目标跨视角关系]({formal_rel})",
            "",
            "图形为算法结果图，不是AirSim相机截图。试验按项目规则未保存场景截图。",
            "",
            "## 7. 分析",
            "",
            f"搜索在20目标场景覆盖{_value(formal, 'search', 'covered_cell_count')}/"
            f"{_value(formal, 'search', 'search_cell_count')}个搜索单元。"
            f"共有{_value(formal, 'search', 'recognized_but_unconfirmed_target_count')}个目标达到识别门限但未满足连续确认，"
            f"中心漏检目标补获{_value(formal, 'search', 'center_missed_recovered_count')}/"
            f"{_value(formal, 'search', 'center_missed_target_count')}。"
            "仍需通过多随机种子区分detect漏帧、资源轮次和局部视场边缘造成的漏确认。",
            "",
            f"中心交接的正确绑定数量与中心可信线索数量一致，错误源没有进入绑定结果。最终帧的"
            f"{_value(formal, 'center_handover', 'unregistered_candidate_count')}条未匹配记录按相机局部航迹计数，"
            "包含已绑定目标的重复视角和中心漏检目标的局部观测，不代表同等数量的物理目标漏配。注册比例为0.8是中心输入召回率设定造成的边界。",
            "",
            f"跨视角密集场景仍有{_value(formal, 'crossview', 'false_positive_relations')}条错误关系和"
            f"{_value(formal, 'crossview', 'id_switch_count')}次身份混合。"
            "成熟簇桥接冗余和短航迹多相机确认已经关闭保存replay中的结构性错误。当前证据只覆盖一个正式随机种子，尚不足以用图神经网络替换几何基线。下一步应在独立随机种子中统计detect波动、短航迹长度和未解决关系。",
            "",
            "## 8. 文件索引",
            "",
            f"- 5目标总表：`{smoke_dir.name}/campaign_summary.json`",
            f"- 20目标总表：`{formal_dir.name}/campaign_summary.json`",
            f"- 20目标搜索指标：`{formal_dir.name}/search/metrics.json`",
            f"- 20目标中心交接指标：`{formal_dir.name}/center_handover/metrics.json`",
            f"- 20目标跨视角指标：`{formal_dir.name}/crossview/metrics.json`",
            f"- 20目标跨视角离线标签：`{formal_dir.name}/crossview/truth/local_track_truth_map.json`",
            "",
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("smoke_dir", type=Path)
    parser.add_argument("formal_dir", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("--prior-formal-dir", action="append", type=Path, default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(
        build_report(
            args.smoke_dir,
            args.formal_dir,
            args.output_path,
            prior_formal_dirs=args.prior_formal_dir,
        ).resolve()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
