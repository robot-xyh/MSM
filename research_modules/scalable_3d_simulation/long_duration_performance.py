"""Read-only comparison of short and long scalable 3D episode artifacts."""

from __future__ import annotations

import csv
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping


LONG_DURATION_COMPARISON_SCHEMA_VERSION = (
    "scalable3d-long-duration-comparison-v2"
)
_CORE_FILES = (
    "manifest.json",
    "scenario_config.json",
    "summary.json",
    "stage_timings.csv",
)
_POST_RUN_TIMING_SCHEMA_VERSION = "scalable3d-post-run-timings-v1"
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
                "short_p50_wall_time_ms": short_stage["p50_wall_time_ms"],
                "long_p50_wall_time_ms": long_stage["p50_wall_time_ms"],
                "p50_wall_time_growth": _optional_ratio(
                    long_stage["p50_wall_time_ms"],
                    short_stage["p50_wall_time_ms"],
                ),
                "short_p95_wall_time_ms": short_stage["p95_wall_time_ms"],
                "long_p95_wall_time_ms": long_stage["p95_wall_time_ms"],
                "p95_wall_time_growth": _optional_ratio(
                    long_stage["p95_wall_time_ms"],
                    short_stage["p95_wall_time_ms"],
                ),
                "short_max_wall_time_ms": short_stage["max_wall_time_ms"],
                "long_max_wall_time_ms": long_stage["max_wall_time_ms"],
                "max_wall_time_growth": _optional_ratio(
                    long_stage["max_wall_time_ms"],
                    short_stage["max_wall_time_ms"],
                ),
                "distribution_available": bool(
                    short_stage["distribution_available"]
                    and long_stage["distribution_available"]
                ),
                "superlinear": bool(
                    normalized_growth is not None
                    and normalized_growth >= superlinear_threshold
                    and long_stage["wall_time_s"] >= 0.1
                ),
            }
        )

    post_run_stage_comparisons = _compare_post_run_stages(
        short,
        long,
        superlinear_threshold=superlinear_threshold,
    )

    short_rss = short["process_resource_usage"]["maximum_rss_bytes"]
    long_rss = long["process_resource_usage"]["maximum_rss_bytes"]
    short_process_elapsed = short["process_resource_usage"]["elapsed_wall_time_s"]
    long_process_elapsed = long["process_resource_usage"]["elapsed_wall_time_s"]
    short_process_residual = (
        None
        if short_process_elapsed is None
        else max(0.0, short_process_elapsed - short["wall_time_s"])
    )
    long_process_residual = (
        None
        if long_process_elapsed is None
        else max(0.0, long_process_elapsed - long["wall_time_s"])
    )
    short_measured_post_run = short["post_run_timings"].get("total_wall_time_s")
    long_measured_post_run = long["post_run_timings"].get("total_wall_time_s")
    rss_ratio = (
        _safe_ratio(float(long_rss), float(short_rss))
        if short_rss is not None and long_rss is not None
        else None
    )
    clean_source = not short["repository_dirty"] and not long["repository_dirty"]
    acceptance = {
        "same_git_commit": short["git_commit"] == long["git_commit"],
        "same_scenario_except_duration": (
            short["scenario_without_duration_sha256"]
            == long["scenario_without_duration_sha256"]
        ),
        "clean_source": clean_source,
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
        "evidence_class": (
            "descriptive_clean_source_calibration"
            if clean_source
            else "descriptive_dirty_source_development"
        ),
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
            # Retain the old field names for readers of comparison schema v1.
            "short_post_run_overhead_s": short_process_residual,
            "long_post_run_overhead_s": long_process_residual,
            "short_process_residual_wall_time_s": short_process_residual,
            "long_process_residual_wall_time_s": long_process_residual,
            "short_measured_post_run_wall_time_s": short_measured_post_run,
            "long_measured_post_run_wall_time_s": long_measured_post_run,
            "normalized_measured_post_run_growth": _normalized_duration_growth(
                short_measured_post_run,
                long_measured_post_run,
                short_duration_s=short["duration_s"],
                long_duration_s=long["duration_s"],
            ),
            "post_run_stage_comparisons": post_run_stage_comparisons,
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
    post_run_timings = _load_post_run_timings(root / "post_run_timings.csv")
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
        "post_run_timings": post_run_timings,
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
            f"同一提交、同一 seed 的 {short['duration_s']:.1f} 秒与 "
            f"{long['duration_s']:.1f} 秒 "
            f"{short['resource_count']} 对 {short['target_count']} episode 已完成。"
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
    short_overhead = comparison["short_process_residual_wall_time_s"]
    long_overhead = comparison["long_process_residual_wall_time_s"]
    if short_overhead is not None and long_overhead is not None:
        lines.append(
            f"| 进程非核心残差（含启动与写出）/s | {short_overhead:.3f} | {long_overhead:.3f} |"
        )
    short_measured = comparison["short_measured_post_run_wall_time_s"]
    long_measured = comparison["long_measured_post_run_wall_time_s"]
    if short_measured is not None and long_measured is not None:
        lines.append(
            f"| 已测结束后处理/s | {short_measured:.3f} | {long_measured:.3f} |"
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
    distribution_rows = [
        item
        for item in comparison["stage_comparisons"]
        if item["distribution_available"]
    ]
    if distribution_rows:
        lines.extend(
            [
                "",
                "## 阶段单次延时",
                "",
                "| 阶段 | 短时P50/ms | 长时P50/ms | 短时P95/ms | 长时P95/ms | 短时max/ms | 长时max/ms |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in distribution_rows:
            lines.append(
                f"| `{item['stage']}` | "
                f"{item['short_p50_wall_time_ms']:.3f} | "
                f"{item['long_p50_wall_time_ms']:.3f} | "
                f"{item['short_p95_wall_time_ms']:.3f} | "
                f"{item['long_p95_wall_time_ms']:.3f} | "
                f"{item['short_max_wall_time_ms']:.3f} | "
                f"{item['long_max_wall_time_ms']:.3f} |"
            )
    if comparison["post_run_stage_comparisons"]:
        lines.extend(
            [
                "",
                "## 结束后处理耗时",
                "",
                "| 阶段 | 短时/s | 长时/s | 单位仿真时间增长 | 超线性 |",
                "| --- | ---: | ---: | ---: | :---: |",
            ]
        )
        for item in comparison["post_run_stage_comparisons"]:
            lines.append(
                f"| `{item['stage']}` | {item['short_wall_time_s']:.3f} | "
                f"{item['long_wall_time_s']:.3f} | "
                f"{_format_ratio(item['normalized_growth'])} | "
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
            (
                "本报告是 clean-source 描述性性能校准，不是正式实验矩阵证据。"
                if comparison["acceptance"]["clean_source"]
                else "本报告来自脏工作树，只作为开发期性能诊断，不进入正式验收。"
            )
            + "单 seed 不能证明跨 seed P95、融合精度、身份连续性或物理拦截成功率。",
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


def _load_stage_timings(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = csv.DictReader(stream)
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            distribution = {
                name: _optional_nonnegative_float(row.get(name))
                for name in (
                    "p50_wall_time_ms",
                    "p95_wall_time_ms",
                    "max_wall_time_ms",
                )
            }
            available_count = sum(value is not None for value in distribution.values())
            if available_count not in {0, 3}:
                raise ValueError("stage timing distribution fields must be all present or all absent")
            if available_count == 3 and not (
                distribution["p50_wall_time_ms"]
                <= distribution["p95_wall_time_ms"]
                <= distribution["max_wall_time_ms"]
            ):
                raise ValueError("stage timing distribution must satisfy p50 <= p95 <= max")
            declared_available = _optional_csv_bool(
                row.get("distribution_available")
            )
            distribution_available = (
                available_count == 3
                if declared_available is None
                else declared_available
            )
            unavailable_reason = (
                row.get("distribution_unavailable_reason") or None
            )
            if distribution_available != (available_count == 3):
                raise ValueError(
                    "stage timing distribution availability conflicts with values"
                )
            if distribution_available and unavailable_reason is not None:
                raise ValueError(
                    "available stage timing distribution cannot have an unavailable reason"
                )
            if (
                declared_available is False
                and unavailable_reason is None
            ):
                raise ValueError(
                    "unavailable stage timing distribution must provide a reason"
                )
            stage = str(row["stage"])
            if stage in result:
                raise ValueError(f"duplicate stage timing: {stage}")
            result[stage] = {
                "schema_version": row.get("schema_version") or None,
                "call_count": int(row["call_count"]),
                "wall_time_s": float(row["wall_time_s"]),
                "mean_wall_time_ms": float(row["mean_wall_time_ms"]),
                **distribution,
                "distribution_available": distribution_available,
                "distribution_unavailable_reason": unavailable_reason,
            }
        return result


def _load_post_run_timings(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "availability": "unavailable",
            "schema_version": None,
            "total_wall_time_s": None,
            "stages": {},
            "unavailable_reason": "post_run_timings_missing",
        }
    stages: dict[str, float] = {}
    schema_versions: set[str] = set()
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            schema_versions.add(str(row["schema_version"]))
            stage = str(row["stage"])
            wall_time_s = float(row["wall_time_s"])
            if wall_time_s < 0.0:
                raise ValueError("post-run timing values must be non-negative")
            if stage in stages:
                raise ValueError(f"duplicate post-run timing stage: {stage}")
            stages[stage] = wall_time_s
    if schema_versions != {_POST_RUN_TIMING_SCHEMA_VERSION}:
        raise ValueError("unsupported post-run timing schema")
    total = stages.pop("total_before_timing_artifact", None)
    if total is None:
        raise ValueError("post-run timing total is missing")
    return {
        "availability": "available",
        "schema_version": _POST_RUN_TIMING_SCHEMA_VERSION,
        "total_wall_time_s": total,
        "stages": stages,
        "unavailable_reason": None,
    }


def _compare_post_run_stages(
    short: Mapping[str, Any],
    long: Mapping[str, Any],
    *,
    superlinear_threshold: float,
) -> list[dict[str, Any]]:
    short_timings = short["post_run_timings"]
    long_timings = long["post_run_timings"]
    if (
        short_timings["availability"] != "available"
        or long_timings["availability"] != "available"
    ):
        return []
    comparisons = []
    short_stages = short_timings["stages"]
    long_stages = long_timings["stages"]
    for stage in sorted(set(short_stages).intersection(long_stages)):
        short_wall_time_s = float(short_stages[stage])
        long_wall_time_s = float(long_stages[stage])
        normalized_growth = _normalized_duration_growth(
            short_wall_time_s,
            long_wall_time_s,
            short_duration_s=short["duration_s"],
            long_duration_s=long["duration_s"],
        )
        comparisons.append(
            {
                "stage": stage,
                "short_wall_time_s": short_wall_time_s,
                "long_wall_time_s": long_wall_time_s,
                "normalized_growth": normalized_growth,
                "superlinear": bool(
                    normalized_growth is not None
                    and normalized_growth >= superlinear_threshold
                    and long_wall_time_s >= 0.1
                ),
            }
        )
    return comparisons


def _normalized_duration_growth(
    short_value: float | None,
    long_value: float | None,
    *,
    short_duration_s: float,
    long_duration_s: float,
) -> float | None:
    if short_value is None or long_value is None:
        return None
    return _optional_ratio(
        long_value / long_duration_s,
        short_value / short_duration_s,
    )


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


def _optional_nonnegative_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError("optional timing values must be finite and non-negative")
    return result


def _optional_csv_bool(value: Any) -> bool | None:
    if value is None or str(value).strip() == "":
        return None
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError("optional CSV boolean must be true or false")


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
