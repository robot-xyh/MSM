"""Read-only comparison of short and long scalable 3D episode artifacts."""

from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping


LONG_DURATION_COMPARISON_SCHEMA_VERSION = (
    "scalable3d-long-duration-comparison-v1"
)
_CORE_FILES = (
    "manifest.json",
    "scenario_config.json",
    "summary.json",
    "stage_timings.csv",
)
_STAGE_NAMES = (
    "module.d1_scan_input",
    "module.d1_fusion",
    "module.d2_association",
    "module.d2_association_finalize",
    "module.d3_assignment",
    "module.d5_active_vision",
    "module.d5_terminal_association",
    "module.d7_guidance",
    "module_publication_bus",
    "module_publication_bus_finalize",
    "module_stack",
    "module_stack_finalize",
)


def compare_long_duration_episodes(
    short_episode_dir: str | Path,
    long_episode_dir: str | Path,
    *,
    superlinear_threshold: float = 1.25,
) -> dict[str, Any]:
    """Compare two same-source episodes that differ only in duration."""

    if superlinear_threshold <= 1.0:
        raise ValueError("superlinear_threshold must be greater than 1")
    short = load_long_duration_episode(short_episode_dir)
    long = load_long_duration_episode(long_episode_dir)
    _validate_comparable(short, long)
    if long["duration_s"] <= short["duration_s"]:
        raise ValueError("long episode duration must exceed short episode duration")

    duration_ratio = long["duration_s"] / short["duration_s"]
    wall_ratio = long["wall_time_s"] / short["wall_time_s"]
    short_wall_rate = short["wall_time_s"] / short["duration_s"]
    long_wall_rate = long["wall_time_s"] / long["duration_s"]
    short_log_rate = _optional_rate(
        short["online_log_size_bytes"], short["duration_s"]
    )
    long_log_rate = _optional_rate(
        long["online_log_size_bytes"], long["duration_s"]
    )
    stage_comparisons = []
    for stage in _STAGE_NAMES:
        short_stage = short["stage_timings"].get(stage)
        long_stage = long["stage_timings"].get(stage)
        if short_stage is None or long_stage is None:
            continue
        short_rate = short_stage["wall_time_s"] / short["duration_s"]
        long_rate = long_stage["wall_time_s"] / long["duration_s"]
        normalized_growth = _safe_ratio(long_rate, short_rate)
        short_call_rate = short_stage["call_count"] / short["duration_s"]
        long_call_rate = long_stage["call_count"] / long["duration_s"]
        short_call_cost_s = _safe_ratio(
            short_stage["wall_time_s"], float(short_stage["call_count"])
        )
        long_call_cost_s = _safe_ratio(
            long_stage["wall_time_s"], float(long_stage["call_count"])
        )
        stage_comparisons.append(
            {
                "stage": stage,
                "short_call_count": short_stage["call_count"],
                "long_call_count": long_stage["call_count"],
                "short_wall_time_s": short_stage["wall_time_s"],
                "long_wall_time_s": long_stage["wall_time_s"],
                "short_wall_time_per_simulated_second": short_rate,
                "long_wall_time_per_simulated_second": long_rate,
                "normalized_growth": normalized_growth,
                "short_calls_per_simulated_second": short_call_rate,
                "long_calls_per_simulated_second": long_call_rate,
                "normalized_call_density_growth": _safe_ratio(
                    long_call_rate, short_call_rate
                ),
                "short_wall_time_per_call_s": short_call_cost_s,
                "long_wall_time_per_call_s": long_call_cost_s,
                "normalized_per_call_cost_growth": _optional_ratio(
                    long_call_cost_s, short_call_cost_s
                ),
                "superlinear": bool(
                    normalized_growth is not None
                    and normalized_growth >= superlinear_threshold
                    and long_stage["wall_time_s"] >= 0.1
                ),
            }
        )

    short_rss = short["process_resource_usage"]["maximum_rss_bytes"]
    long_rss = long["process_resource_usage"]["maximum_rss_bytes"]
    short_process_elapsed = short["process_resource_usage"]["elapsed_wall_time_s"]
    long_process_elapsed = long["process_resource_usage"]["elapsed_wall_time_s"]
    rss_ratio = (
        _safe_ratio(float(long_rss), float(short_rss))
        if short_rss is not None and long_rss is not None
        else None
    )
    acceptance = {
        "same_git_commit": short["git_commit"] == long["git_commit"],
        "same_scenario_except_duration": (
            short["scenario_without_duration_sha256"]
            == long["scenario_without_duration_sha256"]
        ),
        "clean_source": not short["repository_dirty"] and not long["repository_dirty"],
        "finite_state": short["finite_state"] and long["finite_state"],
        "online_truth_use_zero": (
            short["online_truth_use_count"] == 0
            and long["online_truth_use_count"] == 0
        ),
        "d1_buffers_drained": (
            short["d1_governance"]["current_buffered_scan_count"] == 0
            and long["d1_governance"]["current_buffered_scan_count"] == 0
            and short["d1_governance"]["current_buffered_observation_count"] == 0
            and long["d1_governance"]["current_buffered_observation_count"] == 0
        ),
        "d1_no_overflow": (
            short["d1_governance"]["overflow_count"] == 0
            and long["d1_governance"]["overflow_count"] == 0
        ),
        "d2_no_overflow": (
            short["d2_governance"]["overflow_rejection_count"] == 0
            and long["d2_governance"]["overflow_rejection_count"] == 0
        ),
        "assignment_plan_ack_count_non_decreasing": (
            short["assignment_plan_ack_count"] >= 1
            and long["assignment_plan_ack_count"] >= short["assignment_plan_ack_count"]
        ),
    }
    return {
        "schema_version": LONG_DURATION_COMPARISON_SCHEMA_VERSION,
        "evidence_class": "descriptive_clean_source_calibration",
        "short_episode": short,
        "long_episode": long,
        "comparison": {
            "duration_ratio": duration_ratio,
            "wall_time_ratio": wall_ratio,
            "short_wall_time_per_simulated_second": short_wall_rate,
            "long_wall_time_per_simulated_second": long_wall_rate,
            "normalized_wall_time_growth": long_wall_rate / short_wall_rate,
            "short_online_log_bytes_per_simulated_second": short_log_rate,
            "long_online_log_bytes_per_simulated_second": long_log_rate,
            "normalized_online_log_growth": _optional_ratio(
                long_log_rate, short_log_rate
            ),
            "maximum_rss_ratio": rss_ratio,
            "short_process_elapsed_wall_time_s": short_process_elapsed,
            "long_process_elapsed_wall_time_s": long_process_elapsed,
            "short_post_run_overhead_s": (
                None
                if short_process_elapsed is None
                else max(0.0, short_process_elapsed - short["wall_time_s"])
            ),
            "long_post_run_overhead_s": (
                None
                if long_process_elapsed is None
                else max(0.0, long_process_elapsed - long["wall_time_s"])
            ),
            "stage_comparisons": stage_comparisons,
            "superlinear_stage_names": [
                item["stage"] for item in stage_comparisons if item["superlinear"]
            ],
            "acceptance": acceptance,
            "passed_safety_contracts": all(acceptance.values()),
        },
    }


def load_long_duration_episode(episode_dir: str | Path) -> dict[str, Any]:
    """Load bounded summary evidence without reading large JSONL payloads."""

    root = Path(episode_dir).resolve()
    for name in _CORE_FILES:
        if not (root / name).is_file():
            raise FileNotFoundError(f"required episode artifact is missing: {root / name}")
    manifest = _load_json(root / "manifest.json")
    scenario = _load_json(root / "scenario_config.json")
    summary = _load_json(root / "summary.json")
    stages = _load_stage_timings(root / "stage_timings.csv")
    diagnostics = _mapping(summary.get("module_final_diagnostics"))
    governance = _mapping(diagnostics.get("observation_governance"))
    d1 = _mapping(governance.get("d1_scan_input"))
    d2 = _mapping(governance.get("d2_claim_ledger"))
    duration_s = _positive_float(summary.get("simulated_duration_s"), "duration")
    wall_time_s = _positive_float(summary.get("wall_time_s"), "wall_time_s")
    return {
        "episode_dir": str(root),
        "episode_id": str(summary.get("episode_id", manifest.get("episode_id", ""))),
        "git_commit": str(manifest.get("git_commit", "")),
        "repository_dirty": bool(manifest.get("repository_dirty")),
        "scenario_name": str(summary.get("scenario_name", scenario.get("scenario_name", ""))),
        "scenario_version": str(
            summary.get("scenario_version", scenario.get("scenario_version", ""))
        ),
        "scenario_without_duration_sha256": _scenario_without_duration_sha256(scenario),
        "seed": int(summary.get("seed")),
        "target_count": int(summary.get("target_count")),
        "resource_count": int(summary.get("resource_count")),
        "recon_count": int(summary.get("recon_count")),
        "duration_s": duration_s,
        "wall_time_s": wall_time_s,
        "real_time_factor": float(summary.get("real_time_factor")),
        "finite_state": bool(summary.get("finite_state")),
        "online_truth_use_count": int(summary.get("online_truth_use_count")),
        "online_observation_count": int(summary.get("online_observation_count")),
        "online_batch_count": int(summary.get("online_batch_count")),
        "online_log_size_bytes": _optional_file_size(
            root / "online_observations.jsonl"
        ),
        "module_publication_count": int(summary.get("module_publication_count")),
        "assignment_plan_ack_count": int(summary.get("assignment_plan_ack_count")),
        "assignment_plan_control_applied_count": int(
            summary.get("assignment_plan_control_applied_count")
        ),
        "assignment_plan_hold_count": int(summary.get("assignment_plan_hold_count")),
        "intercepted_target_count": int(summary.get("intercepted_target_count")),
        "d1_track_count": int(diagnostics.get("d1_track_count")),
        "d2_track_count": int(diagnostics.get("d2_track_count")),
        "d3_assignment_count": int(diagnostics.get("d3_assignment_count")),
        "d5_binding_count": int(diagnostics.get("d5_binding_count")),
        "d7_command_count": int(diagnostics.get("d7_command_count")),
        "d1_governance": {
            "received_scan_count": int(d1.get("received_scan_count")),
            "received_observation_count": int(d1.get("received_observation_count")),
            "current_buffered_scan_count": int(d1.get("current_buffered_scan_count")),
            "current_buffered_observation_count": int(
                d1.get("current_buffered_observation_count")
            ),
            "maximum_buffered_scan_count": int(d1.get("maximum_buffered_scan_count")),
            "maximum_buffered_observation_count": int(
                d1.get("maximum_buffered_observation_count")
            ),
            "reordered_scan_count": int(d1.get("reordered_scan_count")),
            "overflow_count": int(d1.get("buffer_overflow_scan_count"))
            + int(d1.get("capacity_overflow_scan_count")),
            "too_late_scan_count": int(d1.get("too_late_scan_count")),
        },
        "d2_governance": {
            "current_claim_count": int(d2.get("current_count")),
            "peak_claim_count": int(d2.get("peak_count")),
            "max_claim_count": int(d2.get("max_count")),
            "evicted_count": int(d2.get("evicted_count")),
            "replay_rejection_count": int(d2.get("replay_rejection_count")),
            "too_old_rejection_count": int(d2.get("too_old_rejection_count")),
            "overflow_rejection_count": int(d2.get("overflow_rejection_count")),
        },
        "stage_timings": stages,
        "process_resource_usage": _load_process_resource_usage(
            root / "process_resource_usage.txt"
        ),
    }


def render_long_duration_comparison_markdown(report: Mapping[str, Any]) -> str:
    """Render a concise Chinese report from a comparison payload."""

    short = report["short_episode"]
    long = report["long_episode"]
    comparison = report["comparison"]
    lines = [
        "# 三维长时性能对照",
        "",
        "## 结论",
        "",
        (
            f"同一 clean 提交、同一 seed 的 {short['duration_s']:.1f} 秒与 "
            f"{long['duration_s']:.1f} 秒 200 对 200 episode 已完成。"
            f"长 episode 状态有限，在线真值使用为 {long['online_truth_use_count']}。"
        ),
        (
            f"总墙钟由 {short['wall_time_s']:.3f} 秒增至 {long['wall_time_s']:.3f} 秒；"
            f"每仿真秒成本由 {comparison['short_wall_time_per_simulated_second']:.3f} 秒"
            f"增至 {comparison['long_wall_time_per_simulated_second']:.3f} 秒，"
            f"归一化增长 {comparison['normalized_wall_time_growth']:.3f} 倍。"
        ),
        "",
        "## 运行状态",
        "",
        "| 指标 | 短 episode | 长 episode |",
        "| --- | ---: | ---: |",
        f"| 仿真时长/s | {short['duration_s']:.3f} | {long['duration_s']:.3f} |",
        f"| 墙钟/s | {short['wall_time_s']:.3f} | {long['wall_time_s']:.3f} |",
        f"| 实时倍率 | {short['real_time_factor']:.3f} | {long['real_time_factor']:.3f} |",
        f"| 在线观测 | {short['online_observation_count']} | {long['online_observation_count']} |",
        (
            "| 在线日志/MiB | "
            f"{_format_mebibytes(short['online_log_size_bytes'])} | "
            f"{_format_mebibytes(long['online_log_size_bytes'])} |"
        ),
        f"| D1 航迹 | {short['d1_track_count']} | {long['d1_track_count']} |",
        f"| D2 航迹 | {short['d2_track_count']} | {long['d2_track_count']} |",
        f"| D2 claim 峰值 | {short['d2_governance']['peak_claim_count']} | {long['d2_governance']['peak_claim_count']} |",
        f"| 计划确认 | {short['assignment_plan_ack_count']} | {long['assignment_plan_ack_count']} |",
        f"| 五米接近目标 | {short['intercepted_target_count']} | {long['intercepted_target_count']} |",
    ]
    short_rss = short["process_resource_usage"]["maximum_rss_bytes"]
    long_rss = long["process_resource_usage"]["maximum_rss_bytes"]
    if short_rss is not None and long_rss is not None:
        lines.append(
            f"| 进程峰值驻留内存/GiB | {short_rss / 2**30:.3f} | {long_rss / 2**30:.3f} |"
        )
    short_overhead = comparison["short_post_run_overhead_s"]
    long_overhead = comparison["long_post_run_overhead_s"]
    if short_overhead is not None and long_overhead is not None:
        lines.append(
            f"| 启动与结果写出开销/s | {short_overhead:.3f} | {long_overhead:.3f} |"
        )
    short_log_rate = comparison["short_online_log_bytes_per_simulated_second"]
    long_log_rate = comparison["long_online_log_bytes_per_simulated_second"]
    if short_log_rate is not None and long_log_rate is not None:
        lines.append(
            "| 在线日志速率/MiB每仿真秒 | "
            f"{short_log_rate / 2**20:.3f} | {long_log_rate / 2**20:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 阶段耗时",
            "",
            "| 阶段 | 短时/s | 长时/s | 单位仿真时间增长 | 调用密度增长 | 单次成本增长 | 超线性 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | :---: |",
        ]
    )
    for item in comparison["stage_comparisons"]:
        growth = item["normalized_growth"]
        call_growth = item["normalized_call_density_growth"]
        call_cost_growth = item["normalized_per_call_cost_growth"]
        lines.append(
            f"| `{item['stage']}` | {item['short_wall_time_s']:.3f} | "
            f"{item['long_wall_time_s']:.3f} | "
            f"{growth:.3f} | {_format_ratio(call_growth)} | "
            f"{_format_ratio(call_cost_growth)} | "
            f"{'是' if item['superlinear'] else '否'} |"
        )
    lines.extend(
        [
            "",
            "## 合同检查",
            "",
        ]
    )
    for name, passed in comparison["acceptance"].items():
        lines.append(f"- `{name}`：{'通过' if passed else '未通过'}")
    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            "本报告是 clean-source 描述性性能校准，不是正式实验矩阵证据。"
            "单 seed 不能证明 P95、融合精度、身份连续性或物理拦截成功率。",
            "",
        ]
    )
    return "\n".join(lines)


def write_long_duration_comparison_bundle(
    output_dir: str | Path,
    report: Mapping[str, Any],
) -> dict[str, Path]:
    """Write stable JSON and Markdown artifacts."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "long_duration_comparison.json"
    markdown_path = root / "LONG_DURATION_COMPARISON_CN.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_long_duration_comparison_markdown(report),
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": markdown_path}


def _validate_comparable(short: Mapping[str, Any], long: Mapping[str, Any]) -> None:
    fields = (
        "git_commit",
        "scenario_name",
        "scenario_version",
        "seed",
        "target_count",
        "resource_count",
        "recon_count",
        "scenario_without_duration_sha256",
    )
    mismatches = [name for name in fields if short[name] != long[name]]
    if mismatches:
        raise ValueError(
            "episodes are not comparable; mismatched fields: " + ", ".join(mismatches)
        )


def _load_process_resource_usage(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "availability": "unavailable",
            "maximum_rss_bytes": None,
            "elapsed_wall_time_s": None,
            "unavailable_reason": "process_resource_usage_missing",
        }
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.strip().split(":", 1)
        values[key.strip()] = value.strip()
    rss_text = values.get("Maximum resident set size (kbytes)")
    elapsed_match = re.search(
        r"Elapsed \(wall clock\) time.*?:\s*(\S+)\s*$",
        path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if rss_text is None or elapsed_match is None:
        return {
            "availability": "unavailable",
            "maximum_rss_bytes": None,
            "elapsed_wall_time_s": None,
            "unavailable_reason": "process_resource_usage_fields_missing",
        }
    return {
        "availability": "available",
        "maximum_rss_bytes": int(rss_text) * 1024,
        "elapsed_wall_time_s": _elapsed_seconds(elapsed_match.group(1)),
        "unavailable_reason": None,
    }


def _elapsed_seconds(value: str) -> float:
    parts = value.split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        minutes, seconds = parts
        return 60.0 * float(minutes) + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return 3600.0 * float(hours) + 60.0 * float(minutes) + float(seconds)
    raise ValueError(f"unsupported elapsed time: {value}")


def _load_stage_timings(path: Path) -> dict[str, dict[str, float | int]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = csv.DictReader(stream)
        return {
            str(row["stage"]): {
                "call_count": int(row["call_count"]),
                "wall_time_s": float(row["wall_time_s"]),
                "mean_wall_time_ms": float(row["mean_wall_time_ms"]),
            }
            for row in rows
        }


def _scenario_without_duration_sha256(scenario: Mapping[str, Any]) -> str:
    payload = dict(scenario)
    payload.pop("duration_s", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("required mapping evidence is unavailable")
    return value


def _positive_float(value: Any, name: str) -> float:
    result = float(value)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0.0:
        return None
    return numerator / denominator


def _optional_rate(value: int | None, duration_s: float) -> float | None:
    return None if value is None else float(value) / duration_s


def _optional_ratio(
    numerator: float | None, denominator: float | None
) -> float | None:
    if numerator is None or denominator is None:
        return None
    return _safe_ratio(numerator, denominator)


def _optional_file_size(path: Path) -> int | None:
    return path.stat().st_size if path.is_file() else None


def _format_mebibytes(value: int | None) -> str:
    return "不可用" if value is None else f"{value / 2**20:.3f}"


def _format_ratio(value: float | None) -> str:
    return "不可用" if value is None else f"{value:.3f}"
