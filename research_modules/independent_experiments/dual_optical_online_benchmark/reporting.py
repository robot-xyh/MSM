"""Generate the main Chinese comparison report from measured benchmark metrics."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .contracts import benchmark_protocol_from_mapping


ROUTE_LABELS = {
    "epipolar_mht": "增强极线/多假设/匈牙利",
    "lightweight": "轻量标定几何/匈牙利",
    "gnn": "图神经网络边评分/匈牙利",
    "track_superglue": "航迹级注意力/最优传输",
}
ROUTE_ORDER = tuple(ROUTE_LABELS)
ELIMINATION_REASON_LABELS = {
    "conditional_precision_floor_not_met": "条件精确率未达到验证门槛",
    "route_validation_failed_closed": "路线验证失败关闭",
    "zero_validation_association_skill": "验证阶段未形成有效关联",
    "tiny_validation_association_output": "验证阶段有效输出过少",
    "validation_rejected": "未通过验证门槛",
}


def _value(value: Any, digits: int = 4) -> str:
    return "待测" if value is None else f"{float(value):.{digits}f}"


def _read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _active_routes(
    metrics: Mapping[str, Any],
    freeze_marker: Mapping[str, Any],
) -> tuple[str, ...]:
    metrics_routes = metrics.get("active_routes")
    marker_routes = freeze_marker.get("active_routes")
    if metrics_routes is not None and marker_routes is not None:
        if tuple(metrics_routes) != tuple(marker_routes):
            raise ValueError("metrics and freeze marker active routes differ")
    raw_routes = metrics_routes if metrics_routes is not None else marker_routes
    aggregate = metrics.get("aggregate", {}).get("routes", {})
    if raw_routes is None:
        # Sealed v1-v3 evidence predates the explicit active_routes field.
        routes = tuple(route for route in ROUTE_ORDER if route in aggregate)
    else:
        routes = tuple(str(route) for route in raw_routes)
    if (
        not routes
        or len(routes) != len(set(routes))
        or any(route not in ROUTE_LABELS for route in routes)
    ):
        raise ValueError("comparison metrics contain an invalid active-route set")
    missing_aggregates = [route for route in routes if route not in aggregate]
    if missing_aggregates:
        raise ValueError(
            f"active routes missing aggregate metrics: {missing_aggregates}"
        )
    marker_route_records = freeze_marker.get("routes", {})
    missing_validation = [
        route for route in routes if route not in marker_route_records
    ]
    if missing_validation:
        raise ValueError(
            f"active routes missing validation evidence: {missing_validation}"
        )
    return routes


def _eliminated_routes(
    freeze_marker: Mapping[str, Any],
    active_routes: Sequence[str],
) -> dict[str, dict[str, str]]:
    """Read marker facts only; do not open an eliminated route's evidence."""

    raw = freeze_marker.get("eliminated_routes", {})
    if not isinstance(raw, Mapping):
        return {}
    eliminated: dict[str, dict[str, str]] = {}
    for route in ROUTE_ORDER:
        item = raw.get(route)
        if route in active_routes or not isinstance(item, Mapping):
            continue
        if item.get("status") not in {
            "eliminated_on_validation",
            "eliminated_on_main_validation_gate",
        }:
            continue
        reason_code = str(item.get("reason_code") or "validation_rejected")
        eliminated[route] = {
            "status": "eliminated_on_validation",
            "reason_code": reason_code,
            "reason": ELIMINATION_REASON_LABELS.get(reason_code, reason_code),
        }
    return eliminated


def _level_f1(
    rows: Sequence[Mapping[str, Any]],
    route: str,
    level: str,
) -> float:
    selected = [
        float(row["f1"])
        for row in rows
        if row["route_name"] == route and row["corruption_level"] == level
    ]
    return float(np.mean(selected)) if selected else 0.0


def _join_cn(values: Sequence[str]) -> str:
    if not values:
        return "无"
    if len(values) == 1:
        return values[0]
    return "、".join(values[:-1]) + "和" + values[-1]


def _route_metric_sentences(
    active_routes: Sequence[str],
    aggregate: Mapping[str, Mapping[str, Any]],
) -> str:
    return "；".join(
        (
            f"{ROUTE_LABELS[route]}宏平均F1为"
            f"{_value(aggregate[route]['macro_f1'], 6)}，召回率为"
            f"{_value(aggregate[route]['macro_recall'])}，P95时延为"
            f"{_value(aggregate[route]['latency_p95_ms'], 2)}毫秒"
        )
        for route in active_routes
    ) + "。"


def _route_runtime_sentences(
    active_routes: Sequence[str],
    timeout_counts: Mapping[str, int],
    publication_counts: Mapping[str, int],
    match_counts: Mapping[str, int],
    correct_counts: Mapping[str, int],
    availability_counts: Mapping[str, Counter[str]],
) -> str:
    parts = []
    for route in active_routes:
        parts.append(
            f"{ROUTE_LABELS[route]}完成{publication_counts[route]}次发布，"
            f"超时{timeout_counts[route]}圈，发布{match_counts[route]}个关系，"
            f"其中{correct_counts[route]}个正确，状态分布为"
            f"{dict(availability_counts[route])}"
        )
    return "；".join(parts) + "。"


def _route_analysis_sentences(
    active_routes: Sequence[str],
    aggregate: Mapping[str, Mapping[str, Any]],
) -> str:
    parts = []
    for route in active_routes:
        item = aggregate[route]
        parts.append(
            f"{ROUTE_LABELS[route]}测试精确率为"
            f"{_value(item['macro_precision'])}，召回率为"
            f"{_value(item['macro_recall'])}，累计错配"
            f"{int(item['false_association_count'])}次，P95时延为"
            f"{_value(item['latency_p95_ms'], 2)}毫秒"
        )
    return "；".join(parts) + "。"


def _corruption_table(
    active_routes: Sequence[str],
    corruption_levels: Sequence[str],
    result_rows: Sequence[Mapping[str, Any]],
) -> str:
    header = "| 路线 | " + " | ".join(
        f"{level} F1" for level in corruption_levels
    ) + " |"
    alignment = "| --- | " + " | ".join("---:" for _ in corruption_levels) + " |"
    rows = []
    for route in active_routes:
        values = " | ".join(
            _value(_level_f1(result_rows, route, level), 6)
            for level in corruption_levels
        )
        rows.append(f"| {ROUTE_LABELS[route]} | {values} |")
    return "\n".join((header, alignment, *rows))


def _tracker_level_summary(
    tracker_levels: Mapping[str, Mapping[str, Any]],
    corruption_levels: Sequence[str],
) -> str:
    parts = []
    for level in corruption_levels:
        item = tracker_levels.get(level)
        if item is not None:
            parts.append(
                f"{level}条件{_value(item['mean_common_confirmed_rate'])}"
            )
    return _join_cn(parts)


def generate_report(metrics_path: str | Path) -> Path:
    metrics_path = Path(metrics_path).resolve()
    metrics = _read_json(metrics_path)
    protocol = benchmark_protocol_from_mapping(metrics["protocol"])
    result_rows: list[Mapping[str, Any]] = list(metrics["rows"])
    aggregate: Mapping[str, Mapping[str, Any]] = metrics["aggregate"]["routes"]

    freeze_marker = _read_json(metrics["freeze_marker"])
    active_routes = _active_routes(metrics, freeze_marker)
    eliminated_routes = _eliminated_routes(freeze_marker, active_routes)
    tracker_freeze = _read_json(freeze_marker["tracker_freeze"])
    tracker_validation = tracker_freeze["validation_metrics"]
    tracker_levels = tracker_validation["by_corruption_level"]
    tracker_config = tracker_freeze["tracker_config"]
    preflight_path = metrics_path.parent.parent / "preflight" / "preflight_summary.json"
    preflight = _read_json(preflight_path)

    shared_checks = metrics.get("shared_input_checks", [])
    all_shared = bool(shared_checks) and all(
        item.get("all_equal") for item in shared_checks
    )
    timeout_counts = {
        route: sum(
            row["route_name"] == route and not row["deadline_met"]
            for row in result_rows
        )
        for route in active_routes
    }
    publication_counts = {
        route: sum(row["route_name"] == route for row in result_rows)
        for route in active_routes
    }
    match_counts = {
        route: sum(
            int(row["match_count"])
            for row in result_rows
            if row["route_name"] == route
        )
        for route in active_routes
    }
    correct_counts = {
        route: sum(
            int(row["correct_match_count"])
            for row in result_rows
            if row["route_name"] == route
        )
        for route in active_routes
    }
    availability_counts = {
        route: Counter(
            str(row["availability"])
            for row in result_rows
            if row["route_name"] == route
        )
        for route in active_routes
    }

    test_rows = []
    validation_rows = []
    for route in active_routes:
        label = ROUTE_LABELS[route]
        item = aggregate[route]
        test_rows.append(
            "| {label} | {precision} | {recall} | {f1} | {correct} | "
            "{false_count} | {deadline_rate} | {latency} |".format(
                label=label,
                precision=_value(item["macro_precision"]),
                recall=_value(item["macro_recall"]),
                f1=_value(item["macro_f1"]),
                correct=correct_counts[route],
                false_count=item["false_association_count"],
                deadline_rate=_value(item["deadline_met_rate"]),
                latency=_value(item["latency_p95_ms"], 2),
            )
        )
        evidence = freeze_marker["routes"][route]["validation_acceptance"]
        validation_rows.append(
            f"| {label} | {_value(evidence['validation_f1'], 6)} | "
            f"{evidence['validation_correct_association_count']} | "
            f"{evidence['validation_selected_count']} |"
        )

    eliminated_section = ""
    held_out_heading = "### 4.4 保留测试"
    if eliminated_routes:
        eliminated_rows = [
            f"| {ROUTE_LABELS[route]} | 验证阶段淘汰 | "
            f"{item['reason']}（`{item['reason_code']}`） |"
            for route, item in eliminated_routes.items()
        ]
        eliminated_section = """

### 4.4 验证淘汰

| 路线 | 状态 | 原因 |
| --- | --- | --- |
{rows}

淘汰路线未进入保留测试。报告不读取其聚合测试指标或验证明细。
""".format(rows=chr(10).join(eliminated_rows))
        held_out_heading = "### 4.5 保留测试"

    preflight_scenarios = preflight["acceptance"]["by_scenario"]
    active_labels = [ROUTE_LABELS[route] for route in active_routes]
    active_route_text = _join_cn(active_labels)
    metric_summary = _route_metric_sentences(active_routes, aggregate)
    runtime_summary = _route_runtime_sentences(
        active_routes,
        timeout_counts,
        publication_counts,
        match_counts,
        correct_counts,
        availability_counts,
    )
    route_analysis = _route_analysis_sentences(active_routes, aggregate)
    corruption_table = _corruption_table(
        active_routes, protocol.corruption_levels, result_rows
    )
    eliminated_count = len(eliminated_routes)
    elimination_summary = (
        f"验证阶段另有{eliminated_count}条路线按固定门槛淘汰，未接触保留测试。"
        if eliminated_count
        else "验证阶段没有路线被淘汰。"
    )
    tracker_level_text = _tracker_level_summary(
        tracker_levels, protocol.corruption_levels
    )
    route_algorithm_text = "\n\n".join(
        {
            "epipolar_mht": (
                "增强几何路线按归一化共面残差筛选跨站组合，再用多时刻"
                "视线拟合运动。交叉期间可保留多个候选，最终由匈牙利算法"
                "形成一一关系。"
            ),
            "lightweight": (
                "轻量路线从共享候选图提取几何和运动特征，用训练、验证数据"
                "冻结浅层概率模型，最后由匈牙利算法处理一一约束。"
            ),
            "gnn": (
                "图神经网络路线把两站局部航迹作为节点，把通过几何门的关系"
                "作为边，学习同目标概率，最后由匈牙利算法处理一一约束。"
            ),
            "track_superglue": (
                "航迹级注意力路线同时比较两站全部候选航迹，用站内和跨站"
                "注意力更新航迹描述，再以带空缺项的最优传输形成部分对应。"
                "互为最佳、最低分数和时间确认继续作为确定性发布门槛。"
            ),
        }[route]
        for route in active_routes
    )
    content = f"""# 双光电{protocol.target_count}目标连续周扫在线配准对比报告

## 1. 结论

本轮流程完成9个预检回合、{len(protocol.train_seeds) + len(protocol.validation_seeds)}个标定 seed 和{len(protocol.test_seeds)}个未见测试 seed。进入保留测试的路线为{active_route_text}。{metric_summary}是否晋级以准时召回、条件精确率、错配和时延的固定规则为准，不能只比较F1。

{elimination_summary}当前结果只说明本规模保留测试表现，不能直接形成工程选型结论。

{len(shared_checks)}份测试快照均完成{len(active_routes)}条存活路线同源输入校验，结果为{'通过' if all_shared else '未通过'}。AirSim真实身份和Actor名称未进入在线快照。离线标签只在全部存活路线完成当前圈发布后用于评分，未参与测试参数选择。

## 2. 场景

| 项目 | 配置 |
| --- | --- |
| 光电站 | 2个，横向基线2千米 |
| 目标 | {protocol.target_count}个3米Actor，速度{protocol.target_speed_mps:g}米/秒 |
| 航向 | {protocol.zero_heading_count}个0度，{protocol.minus_thirty_heading_count}个负30度，空间混排 |
| 扫描 | 同方向连续{protocol.scan_span_deg:g}度周扫，{protocol.scan_period_s:g}秒一圈 |
| 时长 | {protocol.duration_s:g}秒，{protocol.revolution_count}圈，逻辑采样{protocol.sample_rate_hz:g}赫兹 |
| 云台误差 | 每相机每回合固定{protocol.gimbal_fixed_bias_rms_mrad:g}毫弧度，逐帧抖动{protocol.gimbal_jitter_rms_mrad:g}毫弧度 |
| 干扰等级 | {'、'.join(protocol.corruption_levels)} |
| 数据划分 | {len(protocol.train_seeds)}个训练、{len(protocol.validation_seeds)}个验证、{len(protocol.test_seeds)}个未见测试 seed |
| 在线时限 | 每圈端到端小于{protocol.online_deadline_ms:.0f}毫秒 |

标定和测试分别使用一次Blocks启动，回合之间执行reset。seed数量以本轮协议为准。全程未保存截图或视频。

## 3. 算法

共享单站跟踪器先把同一扫描过程中的重复检测合并为扫描片段，再用运动模型初始化、卡尔曼预测和马氏距离门控连接跨圈观测。最近3圈命中2圈即可确认，允许短时漏检。检测框面积只保留为诊断信息，不参与小目标测量加权。

{route_algorithm_text}

## 4. 分阶段结果

### 4.1 预检

预检包含理想、云台姿态误差和完整干扰三种条件，每种3个 seed。三种条件的共同成轨率分别为{_value(preflight_scenarios['ideal']['mean_common_confirmed_rate'])}、{_value(preflight_scenarios['pose_error']['mean_common_confirmed_rate'])}和{_value(preflight_scenarios['full_interference']['mean_common_confirmed_rate'])}；中位轨迹纯度分别为{_value(preflight_scenarios['ideal']['median_track_purity'])}、{_value(preflight_scenarios['pose_error']['median_track_purity'])}和{_value(preflight_scenarios['full_interference']['median_track_purity'])}。预检只决定是否允许启动正式标定。

### 4.2 共享跟踪器标定

正式标定比较固定候选网格。冻结配置采用{tracker_config['motion_initialization_residual_gate_m']:.0f}米运动初始化残差门、{tracker_config['maximum_global_hypotheses']}个全局假设、卡方置信度{tracker_config['chi2_confidence']}和过程噪声{tracker_config['process_noise_deg_s2']}度每二次方秒。验证集中位轨迹纯度为{_value(tracker_validation['median_track_purity'])}，各干扰等级共同成轨率为{tracker_level_text}。

预检只用于早期止损，正式配置以完整标定数据和固定门槛为准。

### 4.3 路线验证

| 路线 | 验证F1 | 正确关联数 | 选中关系数 |
| --- | ---: | ---: | ---: |
{chr(10).join(validation_rows)}

表中路线均通过正向能力冻结门控并进入保留测试。该门控用于阻止零能力模型进入测试，不是工程性能验收线。
{eliminated_section}
{held_out_heading}

| 路线 | 宏平均精确率 | 宏平均召回率 | 宏平均F1 | 正确匹配数 | 错配数 | 时限满足率 | P95时延/毫秒 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(test_rows)}

{corruption_table}

{runtime_summary}超时输出按失败处理，没有事后回填。“候选图为空”表示当前圈未形成可评分候选，“超时”表示算法完成时间超过任务预算，两者都不会发布关系。

![存活路线测试结果](figures/02_route_test_comparison.png)

## 5. 结果分析

共享跟踪器已形成跨圈连续航迹，后续关联质量同时受跨站候选保留、关系评分和计算时延影响。

{route_analysis}

不同干扰等级会同时改变候选图大小和超时比例。宏平均指标因此同时反映关联质量和计算路径。后续评估应继续分别报告算法原始输出和施加时限后的任务输出，不得使用本轮测试标签重新选择门限。

![局部航迹与共同稳定目标](figures/01_failure_diagnostics.png)

## 6. 判定

本轮通过场景生成、在线身份隔离、共享输入、预检和冻结门控。达到更大规模的路线还需通过负收益淘汰规则。{len(protocol.test_seeds)}个测试 seed 在本规模内封存，后续参数调整必须使用新的训练、验证和保留测试划分。

## 7. 指标口径

精确率表示已发布关系中身份一致的比例。召回率以场景{protocol.target_count}个目标为分母，统计当前圈正确配准的唯一目标数。F1为精确率与召回率的调和平均。汇总表采用逐圈宏平均。超时圈按无输出计分。

## 8. 限制

本轮使用AirSim `simGetDetections`形成检测框，再按固定协议注入漏检和虚警。结果验证双光电配准算法、连续周扫和在线计算流程，不代表实际光电设备对3米无人机的远距离检测概率。云台误差按既定统计模型注入，尚未覆盖站址误差、时间同步漂移和大气传播影响。

## 9. 证据

- 指标：`{metrics_path.name}`
- 冻结标记：`{metrics.get('freeze_marker', '')}`
- 测试清单：`{metrics.get('test_manifest', '')}`
- 预检：`{preflight_path}`
- 共享跟踪器标定：`{Path(freeze_marker['tracker_freeze']).with_name('shared_tracker_calibration.json')}`
- 逐圈发布：`publications/`
- 诊断：`failure_diagnostics.json`
- 图表：`figures/01_failure_diagnostics.png`、`figures/02_route_test_comparison.png`
"""
    report_path = metrics_path.parent / (
        f"DUAL_OPTICAL_{protocol.target_count}TARGET_ONLINE_COMPARISON_REPORT_CN.md"
    )
    report_path.write_text(content, encoding="utf-8")
    return report_path
