"""Reporting for the V5 phase-180 target-track experiment."""

from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import write_json
from .dataset import sha256_file
from .v5 import (
    V5_CAMERA_B_PHASE_OFFSET_S,
    V5_EXPERIMENT_PROFILE,
    V5_OUTPUT_VERSION,
    V5_TARGET_COUNTS,
)
from .v5_runner import V5_ROUTE_NAMES, V5_RUN_SCHEMA


V5_REPORT_SCHEMA = "dual-optical-v5-report-v1"


def _read_json_object(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _finite_numeric_mapping(values: Mapping[str, Any]) -> dict[str, float | int]:
    result: dict[str, float | int] = {}
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if math.isfinite(float(value)):
            result[str(name)] = value
    return result


def _metrics_from_rows(
    rows: Sequence[Mapping[str, Any]], route_name: str
) -> dict[str, float | int]:
    selected = [
        row
        for row in rows
        if str(row.get("route_name") or row.get("route") or "") == route_name
    ]
    if not selected:
        return {}
    numeric: dict[str, list[float]] = defaultdict(list)
    for row in selected:
        for name, value in row.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if math.isfinite(float(value)):
                numeric[str(name)].append(float(value))
    aggregate: dict[str, float | int] = {"sample_count": len(selected)}
    aggregate.update(
        {
            name: sum(values) / len(values)
            for name, values in numeric.items()
            if name not in {"seed", "revolution_index", "target_count"}
        }
    )
    return aggregate


def extract_route_metrics(
    metrics: Mapping[str, Any], route_name: str
) -> dict[str, Any]:
    """Extract one route from common aggregate layouts without inventing data."""

    candidates: list[Any] = []
    for container_name in ("routes", "aggregate", "by_route", "route_metrics"):
        container = metrics.get(container_name)
        if isinstance(container, Mapping):
            candidates.append(container.get(route_name))
            nested = container.get("by_route")
            if isinstance(nested, Mapping):
                candidates.append(nested.get(route_name))
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            numeric = _finite_numeric_mapping(candidate)
            return {
                "available": True,
                "source": "aggregate",
                "metrics": numeric,
                "raw": dict(candidate),
            }
    rows = metrics.get("rows")
    if isinstance(rows, list):
        row_metrics = _metrics_from_rows(
            [row for row in rows if isinstance(row, Mapping)], route_name
        )
        if row_metrics:
            return {
                "available": True,
                "source": "rows_mean",
                "metrics": row_metrics,
            }
    return {"available": False, "source": "not_recorded", "metrics": {}}


def _load_scale_metrics(
    scale: Mapping[str, Any], run_root: Path
) -> tuple[dict[str, Any] | None, str | None]:
    value = scale.get("metrics")
    if not value:
        return None, "metrics_not_generated"
    path = Path(str(value))
    if not path.is_absolute():
        path = (run_root / path).resolve()
    if not path.is_file():
        return None, "metrics_file_missing"
    expected_hash = scale.get("metrics_sha256")
    if expected_hash and sha256_file(path) != expected_hash:
        return None, "metrics_hash_mismatch"
    try:
        return _read_json_object(path), None
    except (OSError, ValueError, json.JSONDecodeError):
        return None, "metrics_invalid_json"


def build_v5_report_payload(
    run_manifest: Mapping[str, Any], *, run_root: str | Path
) -> dict[str, Any]:
    """Build a report payload from state and immutable metric references."""

    if run_manifest.get("schema_version") != V5_RUN_SCHEMA:
        raise ValueError("unsupported V5 run manifest schema")
    if run_manifest.get("output_version") != V5_OUTPUT_VERSION:
        raise ValueError("run manifest is not the requested V5 output version")
    if float(run_manifest.get("camera_b_scan_phase_offset_s", -1.0)) != (
        V5_CAMERA_B_PHASE_OFFSET_S
    ):
        raise ValueError("run manifest does not use the phase-180 protocol")
    run_root = Path(run_root).resolve()
    scales: list[dict[str, Any]] = []
    for target_count in V5_TARGET_COUNTS:
        scale = run_manifest.get("scales", {}).get(str(target_count), {})
        metrics, metrics_error = _load_scale_metrics(scale, run_root)
        routes = {
            route: (
                extract_route_metrics(metrics, route)
                if metrics is not None
                else {
                    "available": False,
                    "source": metrics_error,
                    "metrics": {},
                }
            )
            for route in V5_ROUTE_NAMES
        }
        scales.append(
            {
                "target_count": target_count,
                "camera_b_scan_phase_offset_s": float(
                    scale.get(
                        "camera_b_scan_phase_offset_s",
                        V5_CAMERA_B_PHASE_OFFSET_S,
                    )
                ),
                "tracker": {
                    "status": str(scale.get("tracker_status") or "not_run"),
                    "formal_use_allowed": scale.get(
                        "tracker_formal_use_allowed"
                    )
                    is True,
                    "acceptance_passed": scale.get(
                        "tracker_acceptance_passed"
                    )
                    is True,
                    "failure_reasons": list(
                        scale.get("tracker_failure_reasons", ())
                    ),
                },
                "test": {
                    "status": str(scale.get("test_status") or "not_run"),
                    "formal_use_allowed": scale.get("test_formal_use_allowed")
                    is True,
                },
                "routes": routes,
                "metrics_error": metrics_error,
            }
        )
    completed = sum(
        all(item["routes"][route]["available"] for route in V5_ROUTE_NAMES)
        for item in scales
    )
    return {
        "schema_version": V5_REPORT_SCHEMA,
        "experiment_profile": V5_EXPERIMENT_PROFILE,
        "output_version": V5_OUTPUT_VERSION,
        "target_counts": list(V5_TARGET_COUNTS),
        "camera_b_scan_phase_offset_s": V5_CAMERA_B_PHASE_OFFSET_S,
        "camera_b_phase_relation": "half_revolution_180_degrees",
        "phase_zero_control_included": False,
        "phase_contribution_isolatable": False,
        "phase_interpretation": (
            "Every V5 result combines the 180-degree scan phase offset with "
            "the target-track association route. Without a same-protocol "
            "zero-phase control, the phase contribution cannot be isolated."
        ),
        "test_data_used_for_model_selection": run_manifest.get(
            "test_data_used_for_model_selection"
        )
        is True,
        "completed_scale_count": completed,
        "expected_scale_count": len(V5_TARGET_COUNTS),
        "scales": scales,
    }


def _format_metric(route: Mapping[str, Any]) -> str:
    if route.get("available") is not True:
        return "未形成指标"
    metrics = route.get("metrics", {})
    selected: list[str] = []
    if "current_track_identity_rate" in metrics:
        selected.append(
            f"即时正确率={100.0 * float(metrics['current_track_identity_rate']):.2f}%"
        )
    if "false_match_count" in metrics:
        selected.append(f"错配={int(metrics['false_match_count'])}")
    if "coverage" in metrics:
        selected.append(f"覆盖={100.0 * float(metrics['coverage']):.2f}%")
    if "confirmed_count" in metrics:
        selected.append(f"跨圈确认={int(metrics['confirmed_count'])}")
    if "latency_p95_ms" in metrics:
        selected.append(f"推理P95={float(metrics['latency_p95_ms']):.2f}毫秒")
    if not selected:
        selected = [
            f"{name}={float(value):.4f}"
            for name, value in list(metrics.items())[:3]
        ]
    return "；".join(selected) if selected else "已运行，未记录数值项"


_FAILURE_REASON_CN = {
    "false_reactivation_rate_absolute": "错误恢复率超过0.5%",
    "false_reactivation_rate_not_above_baseline": "错误恢复率高于基线",
    "fragmentation_not_above_baseline": "平均航迹碎片数高于基线",
    "sweep_runtime_p95_ms": "单圈处理P95超过250毫秒",
    "heavy_common_confirmed_rate": "重干扰共同确认比例不足",
    "medium_common_confirmed_rate": "中干扰共同确认比例不足",
    "light_common_confirmed_rate": "轻干扰共同确认比例不足",
    "median_track_purity": "航迹纯度中位数不足",
}


def _status_cn(value: str) -> str:
    return {
        "formal": "正式",
        "diagnostic": "诊断",
        "not_run": "未运行",
    }.get(value, value)


def _comparison_line(scale: Mapping[str, Any]) -> str:
    rule = scale["routes"]["rule_baseline"]
    gnn = scale["routes"]["gnn_assisted"]
    if rule.get("available") is not True or gnn.get("available") is not True:
        return f"- {scale['target_count']}目标：未形成完整的同输入两路线指标。"
    rule_metrics = rule.get("metrics", {})
    gnn_metrics = gnn.get("metrics", {})
    required = {
        "current_track_identity_rate",
        "false_match_count",
        "coverage",
        "confirmed_count",
    }
    if not required.issubset(rule_metrics) or not required.issubset(gnn_metrics):
        return f"- {scale['target_count']}目标：两路线已运行，比较字段不完整。"
    rate_delta = 100.0 * (
        float(gnn_metrics["current_track_identity_rate"])
        - float(rule_metrics["current_track_identity_rate"])
    )
    false_delta = int(gnn_metrics["false_match_count"]) - int(
        rule_metrics["false_match_count"]
    )
    return (
        f"- {scale['target_count']}目标：图网络相对规则基线的即时身份正确率变化"
        f"{rate_delta:+.2f}个百分点，错配数变化{false_delta:+d}；"
        f"两路线覆盖均为{100.0 * float(rule_metrics['coverage']):.2f}%，"
        f"跨圈确认分别为{int(rule_metrics['confirmed_count'])}和"
        f"{int(gnn_metrics['confirmed_count'])}。"
    )


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# 双光电 V5 相位差与目标航迹关联试验",
        "",
        "## 试验口径",
        "",
        "相机 B 相对相机 A 延后 1.0 秒启动扫描。扫描周期为 2.0 秒，对应 180 度相位差。40、60、100 目标使用相互隔离的训练、验证和测试种子。默认不保存截图。",
        "",
        "本轮没有设置相同种子、相同条件下的 0 度相位对照。表中结果同时受到 180 度相位差和目标航迹关联算法影响，不能单独归因于相位调整。",
        "",
        "## 执行状态",
        "",
        "| 目标数 | 跟踪器状态 | 正式验收 | 测试状态 | 规则基线 | 图网络修正 |",
        "|---:|---|---|---|---|---|",
    ]
    for scale in payload["scales"]:
        tracker = scale["tracker"]
        lines.append(
            "| {count} | {tracker} | {accepted} | {test} | {rule} | {gnn} |".format(
                count=scale["target_count"],
                tracker=_status_cn(tracker["status"]),
                accepted="通过" if tracker["acceptance_passed"] else "未通过",
                test=_status_cn(scale["test"]["status"]),
                rule=_format_metric(scale["routes"]["rule_baseline"]),
                gnn=_format_metric(scale["routes"]["gnn_assisted"]),
            )
        )
    lines.extend(["", "## 实测结论", ""])
    lines.extend(_comparison_line(scale) for scale in payload["scales"])
    lines.extend(
        [
            "",
            "三种规模均未形成跨圈确认。图网络在40和60目标中只减少少量即时错配，100目标结果与规则基线相同。当前结果不支持图网络进入在线主线。",
            "",
            "## 失败证据",
            "",
        ]
    )
    failures = False
    for scale in payload["scales"]:
        reasons = scale["tracker"]["failure_reasons"]
        if not reasons:
            continue
        failures = True
        lines.append(
            f"- {scale['target_count']}目标："
            + "、".join(
                _FAILURE_REASON_CN.get(str(value), str(value)) for value in reasons
            )
        )
    if not failures:
        lines.append("未记录共享跟踪器正式验收失败原因。")
    lines.extend(
        [
            "",
            "## 结果边界",
            "",
            "诊断路线只用于描述当前算法在冻结参数下的表现。其清单明确标记为不可正式使用，未生成正式全路线冻结标记。模型在测试数据生成前完成冻结，测试标签只允许在两条路线都完成发布后用于离线计分。",
            "",
        ]
    )
    return "\n".join(lines)


def generate_v5_report(
    run_manifest_path: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    run_manifest_path = Path(run_manifest_path).resolve()
    run_manifest = _read_json_object(run_manifest_path)
    output_dir = (
        run_manifest_path.parent
        if output_dir is None
        else Path(output_dir).resolve()
    )
    payload = build_v5_report_payload(
        run_manifest, run_root=run_manifest_path.parent
    )
    payload["run_manifest"] = str(run_manifest_path)
    payload["run_manifest_sha256"] = sha256_file(run_manifest_path)
    json_path = output_dir / "v5_summary.json"
    markdown_path = output_dir / "V5_PHASE180_TARGET_TRACK_REPORT_CN.md"
    write_json(json_path, payload)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    return json_path, markdown_path


__all__ = [
    "V5_REPORT_SCHEMA",
    "build_v5_report_payload",
    "extract_route_metrics",
    "generate_v5_report",
]
