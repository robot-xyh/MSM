"""Offline comparison of three ClockSpeed variants of the M5N2 suite.

The evaluator is deliberately file-only. ClockSpeed is accepted only from
suite/case provenance, and the nested main-bus/control-tick timing layers are
kept separate throughout normalization and reporting.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import csv
import json
import math
from pathlib import Path
import statistics
from typing import Any

from .stage_timing import (
    StageTimingValidationError,
    load_stage_timing_jsonl,
    summarize_stage_timing_records,
)


CLOCK_SPEED_COMPARISON_SCHEMA_VERSION = "d6-m5n2-clock-speed-comparison-v2"
EXPECTED_CLOCK_SPEEDS = (0.1, 0.2, 1.0)
EXPECTED_SEEDS = tuple(range(1, 11))
EXPECTED_CASE_COUNT_PER_SUITE = 20
M5N2_EXPECTED_OPPORTUNITIES = {
    "active_primary_pair": 3,
    "target": 2,
    "coalition": 1,
}

_CONTRACT_GATED_METRICS = (
    "active_primary_pair_success_count",
    "active_primary_pair_opportunity_count",
    "target_success_count",
    "target_opportunity_count",
    "coalition_success_count",
    "coalition_opportunity_count",
    "second_primary_5m_success_count",
    "second_primary_opportunity_count",
    "second_primary_min_distance_m",
    "active_primary_final_lock_count",
    "active_primary_final_lock_opportunity_count",
    "coalition_terminal_consensus_count",
    "coalition_terminal_consensus_opportunity_count",
    "collision_stop_count",
    "collision_stop_opportunity_count",
)

_SUMMARY_NAMES = (
    "p1_terminal_closure_summary.json",
    "m5n2_suite_summary.json",
    "suite_summary.json",
)

_COUNT_METRICS = (
    "active_primary_pair_success_count",
    "active_primary_pair_opportunity_count",
    "target_success_count",
    "target_opportunity_count",
    "coalition_success_count",
    "coalition_opportunity_count",
    "second_primary_5m_success_count",
    "second_primary_opportunity_count",
    "active_primary_final_lock_count",
    "active_primary_final_lock_opportunity_count",
    "coalition_terminal_consensus_count",
    "coalition_terminal_consensus_opportunity_count",
    "collision_stop_count",
    "collision_stop_opportunity_count",
    "truth_identity_online_use_count",
    "truth_state_online_use_count",
)

_DISTRIBUTION_METRICS = (
    "second_primary_min_distance_m",
    "case_wall_elapsed_s",
    "main_bus_wall_mean_ms",
    "main_bus_wall_p95_ms",
    "control_tick_wall_mean_ms",
    "control_tick_wall_p95_ms",
    "simulated_time_per_tick_s",
)

_CASE_CSV_FIELDS = (
    "clock_speed",
    "clock_speed_provenance_scope",
    "summary_path",
    "case_id",
    "comparison_role",
    "profile",
    "seed",
    "family",
    "resource_count",
    "target_count",
    "opportunity_contract_availability",
    "opportunity_contract_status",
    "opportunity_contract_reasons",
    "expected_active_primary_pair_opportunities",
    "observed_active_primary_pair_opportunities",
    "expected_target_opportunities",
    "observed_target_opportunities",
    "expected_coalition_opportunities",
    "observed_coalition_opportunities",
    "standby_reserve_count",
    "standby_reserve_physical_success_count",
    *(
        field
        for name in (*_COUNT_METRICS, *_DISTRIBUTION_METRICS)
        for field in (name, f"{name}_availability", f"{name}_unavailable_reason")
    ),
    "main_bus_timing_sample_count",
    "main_bus_timing_sample_count_availability",
    "main_bus_timing_sample_count_unavailable_reason",
    "control_tick_timing_sample_count",
    "control_tick_timing_sample_count_availability",
    "control_tick_timing_sample_count_unavailable_reason",
)

_AGGREGATE_CSV_FIELDS = (
    "clock_speed",
    "profile",
    "comparison_role",
    "case_count",
    *(
        field
        for name in (
            "active_primary_pair_success_rate",
            "target_success_rate",
            "coalition_success_rate",
            "second_primary_5m_success_rate",
            "active_primary_final_lock_rate",
            "coalition_terminal_consensus_rate",
            "collision_stop_rate",
            "second_primary_min_distance_m",
            "case_wall_elapsed_s",
            "main_bus_wall_mean_ms",
            "main_bus_wall_p95_ms",
            "control_tick_wall_mean_ms",
            "control_tick_wall_p95_ms",
            "simulated_time_per_tick_s",
            "truth_identity_online_use_count",
            "truth_state_online_use_count",
        )
        for field in (
            name,
            f"{name}_availability",
            f"{name}_available_case_count",
            f"{name}_unavailable_reason",
        )
    ),
)


class ClockSpeedComparisonValidationError(ValueError):
    """Raised when a suite cannot participate in the strict paired comparison."""


class ClockSpeedComparisonReportGenerator:
    """Validate three suites and write JSON, CSV, Chinese Markdown, and PNG."""

    def write_report_bundle(
        self,
        output_dir: str | Path,
        *,
        suite_inputs: Sequence[str | Path | Mapping[str, Any]],
        title: str = "M5N2 三档 ClockSpeed 离线对比报告",
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = compare_clock_speed_suites(suite_inputs)

        json_path = output_dir / "clock_speed_comparison_summary.json"
        json_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        case_csv_path = output_dir / "clock_speed_comparison_cases.csv"
        with case_csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=_CASE_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(_case_csv_row(row) for row in summary["case_rows"])

        aggregate_csv_path = output_dir / "clock_speed_comparison_aggregates.csv"
        with aggregate_csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=_AGGREGATE_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(
                _aggregate_csv_row(row) for row in summary["aggregates"]
            )

        plot_path = output_dir / "clock_speed_comparison_curves.png"
        _write_plot(summary, plot_path)

        markdown_path = output_dir / "CLOCK_SPEED_COMPARISON_REPORT_CN.md"
        markdown_path.write_text(
            render_clock_speed_comparison_markdown(
                summary,
                title=title,
                plot_name=plot_path.name,
            ),
            encoding="utf-8",
        )
        return {
            "json": json_path,
            "cases_csv": case_csv_path,
            "aggregates_csv": aggregate_csv_path,
            "markdown": markdown_path,
            "plot": plot_path,
        }


def compare_clock_speed_suites(
    suite_inputs: Sequence[str | Path | Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate and compare exactly the 1.0/0.2/0.1 M5N2 suites."""

    if len(suite_inputs) != len(EXPECTED_CLOCK_SPEEDS):
        raise ClockSpeedComparisonValidationError(
            "exactly three suite roots or summaries are required"
        )

    suites = [_load_and_validate_suite(source) for source in suite_inputs]
    suites.sort(key=lambda item: item["clock_speed"])
    actual_speeds = tuple(float(item["clock_speed"]) for item in suites)
    if any(
        not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)
        for actual, expected in zip(actual_speeds, EXPECTED_CLOCK_SPEEDS)
    ):
        raise ClockSpeedComparisonValidationError(
            f"expected provenance ClockSpeed values {EXPECTED_CLOCK_SPEEDS}, "
            f"got {actual_speeds}"
        )

    reference_keys = set(suites[0]["case_keys"])
    for suite in suites[1:]:
        keys = set(suite["case_keys"])
        if keys != reference_keys:
            missing = sorted(reference_keys - keys)
            extra = sorted(keys - reference_keys)
            raise ClockSpeedComparisonValidationError(
                "suite case_id/profile/seed pairing mismatch; "
                f"ClockSpeed={suite['clock_speed']}, missing={missing}, extra={extra}"
            )

    case_rows = [
        row
        for suite in suites
        for row in _evaluate_suite_cases(suite)
    ]
    aggregates = _build_aggregates(case_rows)
    paired_rows = _build_paired_rows(case_rows)
    truth_audit = _build_truth_audit(case_rows)
    contract_audit = _build_opportunity_contract_audit(case_rows)
    return {
        "schema_version": CLOCK_SPEED_COMPARISON_SCHEMA_VERSION,
        "offline_only": True,
        "expected_clock_speeds": list(EXPECTED_CLOCK_SPEEDS),
        "expected_profiles": [
            {
                "profile": profile,
                "comparison_role": role,
            }
            for profile, role in sorted(suites[0]["profile_roles"].items())
        ],
        "expected_seeds": list(EXPECTED_SEEDS),
        "suite_count": len(suites),
        "case_count_per_suite": EXPECTED_CASE_COUNT_PER_SUITE,
        "total_case_count": len(case_rows),
        "pairing": {
            "availability": "available",
            "key_fields": ["case_id", "profile", "seed"],
            "paired_case_count": len(reference_keys),
            "clock_speed_count_per_pair": len(suites),
        },
        "timing_contract": {
            "main_bus_scope": "main_episode_bus",
            "control_tick_scope": "simpleflight_control_tick",
            "nested_layers": True,
            "cross_layer_aggregation_prohibited": True,
            "cross_layer_total_ms": None,
            "simulated_time_per_tick_formula": (
                "control_tick_wall_mean_ms / 1000 * provenance.ClockSpeed"
            ),
        },
        "m5n2_frozen_opportunity_contract": {
            "expected_per_case": dict(M5N2_EXPECTED_OPPORTUNITIES),
            "mismatch_policy": "affected_case_metrics_unavailable",
            "missing_evidence_is_zero": False,
            "standby_reserve_in_active_primary": False,
        },
        "suite_manifest": [
            {
                "clock_speed": suite["clock_speed"],
                "clock_speed_provenance_scope": suite[
                    "clock_speed_provenance_scope"
                ],
                "clock_speed_provenance_evidence": suite[
                    "clock_speed_provenance_evidence"
                ],
                "summary_path": suite["summary_path"],
                "case_count": len(suite["case_keys"]),
                "profiles": suite["profile_roles"],
                "seeds": list(EXPECTED_SEEDS),
            }
            for suite in suites
        ],
        "truth_audit": truth_audit,
        "opportunity_contract_audit": contract_audit,
        "case_rows": case_rows,
        "aggregates": aggregates,
        "paired_rows": paired_rows,
    }


def render_clock_speed_comparison_markdown(
    summary: Mapping[str, Any],
    *,
    title: str,
    plot_name: str,
) -> str:
    """Render a concise Chinese report without promoting unavailable values."""

    lines = [
        f"# {title}",
        "",
        "D6 仅消费三份已落盘 suite summary 及其注册 artifact，不连接 AirSim、不参与控制。ClockSpeed 只读取 suite/case `provenance`，不从目录名推断。",
        "",
        f"![ClockSpeed 对比曲线]({plot_name})",
        "",
        "## 完整性与配对",
        "",
        f"- 三档 ClockSpeed：`{', '.join(str(item) for item in summary.get('expected_clock_speeds', []))}`；每档 `{summary.get('case_count_per_suite')}` case，总计 `{summary.get('total_case_count')}`。",
        f"- 配对键：`case_id/profile/seed`；跨档完整配对 `{_get(summary, 'pairing', 'paired_case_count')}` 组。baseline/candidate 各 seed 1-10 已在输入校验阶段强制检查。",
        "- main bus 是 control tick 的嵌套内层，两层禁止相加；报告中的 `cross_layer_total_ms` 固定为 `null`。",
        "",
        "## 物理完成率",
        "",
        "| ClockSpeed | Profile | Active-primary pair | Target | Coalition | 第二 primary 5 m |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for row in summary.get("aggregates", []):
        metrics = row.get("metrics", {})
        lines.append(
            "| {clock} | `{profile}` | {pair} | {target} | {coalition} | {second} |".format(
                clock=row.get("clock_speed"),
                profile=row.get("profile"),
                pair=_metric_text(metrics.get("active_primary_pair_success_rate")),
                target=_metric_text(metrics.get("target_success_rate")),
                coalition=_metric_text(metrics.get("coalition_success_rate")),
                second=_metric_text(metrics.get("second_primary_5m_success_rate")),
            )
        )

    lines.extend(
        [
            "",
            "## 末端、安全与距离",
            "",
            "| ClockSpeed | Profile | Final lock | Coalition consensus | Collision stop | 第二 primary 最小距离 mean m |",
            "|---:|---|---:|---:|---:|---:|",
        ]
    )
    for row in summary.get("aggregates", []):
        metrics = row.get("metrics", {})
        lines.append(
            "| {clock} | `{profile}` | {lock} | {consensus} | {collision} | {distance} |".format(
                clock=row.get("clock_speed"),
                profile=row.get("profile"),
                lock=_metric_text(metrics.get("active_primary_final_lock_rate")),
                consensus=_metric_text(
                    metrics.get("coalition_terminal_consensus_rate")
                ),
                collision=_metric_text(metrics.get("collision_stop_rate")),
                distance=_metric_text(metrics.get("second_primary_min_distance_m")),
            )
        )

    lines.extend(
        [
            "",
            "## Wall timing 与归一化 tick",
            "",
            "| ClockSpeed | Profile | Case wall mean s | Main bus mean ms | Control tick mean ms | Simulated time/tick s |",
            "|---:|---|---:|---:|---:|---:|",
        ]
    )
    for row in summary.get("aggregates", []):
        metrics = row.get("metrics", {})
        lines.append(
            "| {clock} | `{profile}` | {case_wall} | {main} | {control} | {normalized} |".format(
                clock=row.get("clock_speed"),
                profile=row.get("profile"),
                case_wall=_metric_text(metrics.get("case_wall_elapsed_s")),
                main=_metric_text(metrics.get("main_bus_wall_mean_ms")),
                control=_metric_text(metrics.get("control_tick_wall_mean_ms")),
                normalized=_metric_text(
                    metrics.get("simulated_time_per_tick_s")
                ),
            )
        )

    truth = summary.get("truth_audit", {})
    contract = summary.get("opportunity_contract_audit", {})
    lines.extend(
        [
            "",
            "## M5N2 冻结机会合同审计",
            "",
            "- 每 case 固定机会数：active-primary pair=`3`、target=`2`、coalition=`1`。actual-execution 不可用或任何机会数不符时，该 case 的物理/末端派生指标整体为 `unavailable`，不缩小分母、不补零。",
            f"- Match/mismatch：`{contract.get('match_case_count')}/{contract.get('mismatch_case_count')}`；standby reserve 始终排除在 active-primary 成功与分母之外。",
            "",
            "| ClockSpeed | Case | Profile | 状态 | Expected pair/target/coalition | Observed pair/target/coalition | Reserve success | 原因 |",
            "|---:|---|---|---|---|---|---:|---|",
        ]
    )
    for item in contract.get("mismatch_cases", []):
        expected = item.get("expected", {})
        observed = item.get("observed", {})
        intercept = item.get("intercept_audit", {})
        lines.append(
            "| {clock} | `{case}` | `{profile}` | `{status}` | {ep}/{et}/{ec} | {op}/{ot}/{oc} | {reserve} | `{reasons}` |".format(
                clock=item.get("clock_speed"),
                case=item.get("case_id"),
                profile=item.get("profile"),
                status=item.get("status"),
                ep=expected.get("active_primary_pair"),
                et=expected.get("target"),
                ec=expected.get("coalition"),
                op=observed.get("active_primary_pair"),
                ot=observed.get("target"),
                oc=observed.get("coalition"),
                reserve=intercept.get("standby_reserve_physical_success_count"),
                reasons=", ".join(str(reason) for reason in item.get("reasons", [])),
            )
        )
    if not contract.get("mismatch_cases"):
        lines.append("| NA | NA | NA | `match` | 3/2/1 | 3/2/1 | 0 | 无不一致 case |")

    lines.extend(
        [
            "",
            "## Truth 在线使用审计",
            "",
            f"- Identity：`{_audit_text(truth.get('identity'))}`。",
            f"- State：`{_audit_text(truth.get('state'))}`。",
            "- 任一 case 缺 truth count 时整体审计为 `unavailable`，不会把缺失项补成 0；显式非零会保留并使 `all_zero=false`。",
            "",
            "## 口径边界",
            "",
            "- Active-primary pair、target、coalition 使用固定且独立的 M5N2 分母，禁止跨层回填成功。第二 primary 按同一 target 内 `resource_id` 稳定排序后的第 2 个 required active primary 定义。",
            "- Terminal lock 与 coalition consensus 是 `intercept_summary` 的 required active-primary 最终状态，不等同于事件累计数。collision stop 只统计显式 `control_stop_reason=collision_stop`。",
            "- 缺失值、坏 schema、不可读 artifact 或证据不完整均显示为 `unavailable`；报告不会生成性能结论或把接口测试升级为真实 AirSim 结果。",
            "",
        ]
    )
    return "\n".join(lines)


def _load_and_validate_suite(
    source: str | Path | Mapping[str, Any],
) -> dict[str, Any]:
    payload, summary_path = _load_suite_payload(source)
    cases_raw = payload.get("cases")
    rows_raw = payload.get("rows")
    if not _is_sequence(cases_raw) or not _is_sequence(rows_raw):
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: suite must contain cases[] and rows[]"
        )
    cases = [dict(item) for item in cases_raw if isinstance(item, Mapping)]
    rows = [dict(item) for item in rows_raw if isinstance(item, Mapping)]
    if len(cases) != len(cases_raw) or len(rows) != len(rows_raw):
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: cases[] and rows[] entries must be objects"
        )
    if len(cases) != EXPECTED_CASE_COUNT_PER_SUITE or len(rows) != len(cases):
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: expected exactly {EXPECTED_CASE_COUNT_PER_SUITE} "
            f"cases and rows, got cases={len(cases)}, rows={len(rows)}"
        )

    clock_speed, provenance_scope, provenance_evidence = (
        _clock_speed_from_provenance(
            payload,
            cases,
            rows,
            summary_path=summary_path,
        )
    )
    case_by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    profile_roles: dict[str, str] = {}
    for case in cases:
        key = _case_key(case, summary_path=summary_path, where="cases")
        if key in case_by_key:
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: duplicate case_id/profile/seed key {key}"
            )
        family = case.get("family")
        resource_count = case.get("resource_count")
        target_count = case.get("target_count")
        if family != "m5n2_paired" or resource_count != 5 or target_count != 2:
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: case {key} is not explicit M5N2 evidence; "
                f"family/resource_count/target_count={family!r}/{resource_count!r}/{target_count!r}"
            )
        raw_role = case.get("comparison_role")
        role = "candidate" if raw_role == "enhanced" else raw_role
        if role not in {"baseline", "candidate"}:
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: case {key} comparison_role must be "
                "baseline/candidate (enhanced is the accepted candidate alias)"
            )
        profile = key[1]
        previous_role = profile_roles.setdefault(profile, str(role))
        if previous_role != role:
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: profile {profile!r} has conflicting roles"
            )
        case_by_key[key] = case

    roles = defaultdict(list)
    for profile, role in profile_roles.items():
        roles[role].append(profile)
    if len(roles["baseline"]) != 1 or len(roles["candidate"]) != 1:
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: expected one baseline and one candidate profile"
        )
    for profile in profile_roles:
        seeds = sorted(key[2] for key in case_by_key if key[1] == profile)
        if tuple(seeds) != EXPECTED_SEEDS:
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: profile {profile!r} expected seeds 1-10, got {seeds}"
            )

    row_by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in rows:
        key = _case_key(row, summary_path=summary_path, where="rows")
        if key in row_by_key:
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: duplicate result row key {key}"
            )
        case = case_by_key.get(key)
        if case is None:
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: row {key} has no matching case registration"
            )
        for field in ("family", "resource_count", "target_count"):
            if row.get(field) != case.get(field):
                raise ClockSpeedComparisonValidationError(
                    f"{summary_path}: row {key} conflicts with case field {field}"
                )
        row_by_key[key] = row
    missing_rows = sorted(set(case_by_key) - set(row_by_key))
    if missing_rows:
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: missing result rows for {missing_rows}"
        )

    return {
        "payload": payload,
        "summary_path": summary_path,
        "summary_dir": (
            Path(summary_path).parent if summary_path != "<mapping>" else Path.cwd()
        ),
        "clock_speed": clock_speed,
        "clock_speed_provenance_scope": provenance_scope,
        "clock_speed_provenance_evidence": provenance_evidence,
        "profile_roles": dict(sorted(profile_roles.items())),
        "case_keys": sorted(case_by_key),
        "cases": case_by_key,
        "rows": row_by_key,
    }


def _load_suite_payload(
    source: str | Path | Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    if isinstance(source, Mapping):
        return dict(source), "<mapping>"
    path = Path(source)
    if path.is_dir():
        candidates = [path / name for name in _SUMMARY_NAMES if (path / name).is_file()]
        if len(candidates) != 1:
            raise ClockSpeedComparisonValidationError(
                f"{path}: expected exactly one suite summary named one of {_SUMMARY_NAMES}, "
                f"found {[item.name for item in candidates]}"
            )
        path = candidates[0]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClockSpeedComparisonValidationError(
            f"cannot read suite summary {path}: {exc}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ClockSpeedComparisonValidationError(f"{path}: summary root must be an object")
    return dict(payload), str(path.resolve())


def _clock_speed_from_provenance(
    payload: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    *,
    summary_path: str,
) -> tuple[float, str, list[str]]:
    suite_values: list[float] = []
    for field in ("provenance", "suite_provenance"):
        provenance = payload.get(field)
        if isinstance(provenance, Mapping):
            value = _clock_value_in_provenance(provenance)
            if value is not None:
                suite_values.append(value)
    if suite_values and any(
        not math.isclose(value, suite_values[0], rel_tol=0.0, abs_tol=1e-12)
        for value in suite_values[1:]
    ):
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: conflicting suite provenance ClockSpeed values"
        )

    case_values: list[float] = []
    missing_case_provenance = 0
    for case in cases:
        provenance = case.get("provenance")
        value = (
            _clock_value_in_provenance(provenance)
            if isinstance(provenance, Mapping)
            else None
        )
        if value is None:
            missing_case_provenance += 1
        else:
            case_values.append(value)
    if case_values and any(
        not math.isclose(value, case_values[0], rel_tol=0.0, abs_tol=1e-12)
        for value in case_values[1:]
    ):
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: conflicting case provenance ClockSpeed values"
        )

    row_values: list[float] = []
    missing_row_provenance = 0
    for row in rows:
        provenance = row.get("provenance")
        value = (
            _clock_value_in_provenance(provenance)
            if isinstance(provenance, Mapping)
            else None
        )
        if value is None and "clock_speed" in row:
            value = _finite_nonnegative(row["clock_speed"])
            if value is None or value <= 0.0:
                raise ClockSpeedComparisonValidationError(
                    f"{summary_path}: invalid case result clock_speed"
                )
        if value is None:
            missing_row_provenance += 1
        else:
            row_values.append(value)
    if row_values and any(
        not math.isclose(value, row_values[0], rel_tol=0.0, abs_tol=1e-12)
        for value in row_values[1:]
    ):
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: conflicting case result ClockSpeed values"
        )

    suite_value = suite_values[0] if suite_values else None
    case_value = case_values[0] if case_values else None
    row_value = row_values[0] if row_values else None
    if suite_value is None and (
        (case_value is None or missing_case_provenance > 0)
        and (row_value is None or missing_row_provenance > 0)
    ):
        no_explicit_clock_speed = not (suite_values or case_values or row_values)
        if no_explicit_clock_speed and summary_path != "<mapping>":
            return _clock_speed_from_sibling_case_settings(
                cases,
                summary_path=summary_path,
            )
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: ClockSpeed must come from suite provenance, every "
            "case provenance/result row, or all sibling case generated settings"
        )
    available_scopes = [
        ("suite", suite_value),
        ("case", case_value),
        ("case_result", row_value),
    ]
    explicit_values = [value for _, value in available_scopes if value is not None]
    if any(
        not math.isclose(value, explicit_values[0], rel_tol=0.0, abs_tol=1e-12)
        for value in explicit_values[1:]
    ):
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: suite/case provenance ClockSpeed conflict"
        )
    if suite_value is not None:
        scope = "suite"
        if case_values or row_values:
            scope += "_and_case"
        return suite_value, scope, []
    if case_value is not None and missing_case_provenance == 0:
        scope = "case_and_case_result" if row_values else "case"
        return float(case_value), scope, []
    return float(row_value), "case_result", []


def _clock_speed_from_sibling_case_settings(
    cases: Sequence[Mapping[str, Any]],
    *,
    summary_path: str,
) -> tuple[float, str, list[str]]:
    summary = Path(summary_path)
    suite_root = summary.parent
    settings_paths: list[Path] = []
    values: list[float] = []
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.startswith("m5n2_"):
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: invalid M5N2 case_id for sibling settings: "
                f"{case_id!r}"
            )
        sibling_suffix = case_id.removeprefix("m5n2_")
        if not sibling_suffix or Path(sibling_suffix).name != sibling_suffix:
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: unsafe case_id for sibling settings: {case_id!r}"
            )
        settings_path = (
            suite_root.parent
            / f"{suite_root.name}_{sibling_suffix}"
            / "generated_settings"
            / "blocks_actor_m5_n2_settings.json"
        )
        if not settings_path.is_file():
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: sibling case settings missing for {case_id}: "
                f"{settings_path}"
            )
        try:
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: cannot read sibling case settings for "
                f"{case_id}: {exc}"
            ) from exc
        if not isinstance(payload, Mapping) or "ClockSpeed" not in payload:
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: sibling case settings for {case_id} must "
                "explicitly contain ClockSpeed"
            )
        value = _finite_nonnegative(payload["ClockSpeed"])
        if value is None or value <= 0.0:
            raise ClockSpeedComparisonValidationError(
                f"{summary_path}: sibling case settings for {case_id} contain "
                f"invalid ClockSpeed {payload['ClockSpeed']!r}"
            )
        settings_paths.append(settings_path.resolve())
        values.append(value)

    if len(settings_paths) != EXPECTED_CASE_COUNT_PER_SUITE:
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: expected {EXPECTED_CASE_COUNT_PER_SUITE} sibling "
            f"case settings, got {len(settings_paths)}"
        )
    first_value = values[0]
    conflicting = [
        (str(path), value)
        for path, value in zip(settings_paths, values)
        if not math.isclose(value, first_value, rel_tol=0.0, abs_tol=1e-12)
    ]
    if conflicting:
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: conflicting sibling case settings ClockSpeed "
            f"values; expected {first_value}, conflicts={conflicting}"
        )
    return (
        first_value,
        "sibling_case_generated_settings",
        [str(path) for path in settings_paths],
    )


def _clock_value_in_provenance(provenance: Mapping[str, Any]) -> float | None:
    paths = (
        ("clock_speed",),
        ("ClockSpeed",),
        ("airsim", "clock_speed"),
        ("airsim", "ClockSpeed"),
        ("settings", "ClockSpeed"),
        ("generated_settings", "ClockSpeed"),
        ("runtime", "clock_speed"),
    )
    values: list[float] = []
    for path in paths:
        current: Any = provenance
        for field in path:
            if not isinstance(current, Mapping) or field not in current:
                current = None
                break
            current = current[field]
        if current is None:
            continue
        value = _finite_nonnegative(current)
        if value is None or value <= 0.0:
            raise ClockSpeedComparisonValidationError(
                f"invalid provenance ClockSpeed value at {'.'.join(path)}: {current!r}"
            )
        values.append(value)
    if not values:
        return None
    if any(
        not math.isclose(value, values[0], rel_tol=0.0, abs_tol=1e-12)
        for value in values[1:]
    ):
        raise ClockSpeedComparisonValidationError(
            "conflicting ClockSpeed values inside one provenance object"
        )
    return values[0]


def _case_key(
    item: Mapping[str, Any],
    *,
    summary_path: str,
    where: str,
) -> tuple[str, str, int]:
    case_id = item.get("case_id")
    profile = item.get("profile")
    seed = item.get("seed")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: {where} entry has invalid case_id"
        )
    if not isinstance(profile, str) or not profile.strip():
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: {where} entry has invalid profile"
        )
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ClockSpeedComparisonValidationError(
            f"{summary_path}: {where} entry has invalid seed"
        )
    return case_id, profile, seed


def _evaluate_suite_cases(suite: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for key in suite["case_keys"]:
        case = suite["cases"][key]
        row = suite["rows"][key]
        metrics = _row_physical_metrics(row)
        intercept_metrics = _intercept_metrics(
            row,
            summary_dir=suite["summary_dir"],
            expected_clock_speed=float(suite["clock_speed"]),
        )
        metrics.update(intercept_metrics)
        intercept_audit = _intercept_contract_audit(
            row,
            summary_dir=suite["summary_dir"],
        )
        opportunity_contract = _opportunity_contract(row, intercept_audit)
        if opportunity_contract["availability"] != "available":
            reason = "m5n2_opportunity_contract_mismatch:" + ",".join(
                opportunity_contract["reasons"]
            )
            for metric_name in _CONTRACT_GATED_METRICS:
                metrics[metric_name] = _unavailable(
                    reason,
                    source="m5n2_frozen_opportunity_contract",
                )
        else:
            derived_successes = (
                (
                    "active_primary_pair_success_count",
                    "active_primary_physical_success_count",
                ),
                (
                    "target_success_count",
                    "active_primary_target_physical_success_count",
                ),
                (
                    "coalition_success_count",
                    "active_primary_coalition_physical_success_count",
                ),
            )
            for metric_name, audit_name in derived_successes:
                if metrics[metric_name].get("availability") != "available":
                    continue
                value = _nonnegative_integer(intercept_audit.get(audit_name))
                metrics[metric_name] = (
                    _available(value, source="intercept_summary.required_active_primary")
                    if value is not None
                    else _unavailable(
                        f"{audit_name}_unavailable",
                        source="intercept_summary.required_active_primary",
                    )
                )
        timing_metrics = _timing_metrics(
            row,
            summary_dir=suite["summary_dir"],
            clock_speed=float(suite["clock_speed"]),
        )
        metrics.update(timing_metrics)
        metrics["case_wall_elapsed_s"] = _case_wall_metric(row)
        metrics["truth_identity_online_use_count"] = _row_count_metric(
            row,
            "truth_identity_online_use_count",
        )
        metrics["truth_state_online_use_count"] = _row_count_metric(
            row,
            "truth_state_online_use_count",
        )
        result.append(
            {
                "clock_speed": suite["clock_speed"],
                "clock_speed_provenance_scope": suite[
                    "clock_speed_provenance_scope"
                ],
                "summary_path": suite["summary_path"],
                "case_id": key[0],
                "comparison_role": suite["profile_roles"][key[1]],
                "profile": key[1],
                "seed": key[2],
                "family": case["family"],
                "resource_count": case["resource_count"],
                "target_count": case["target_count"],
                "opportunity_contract": opportunity_contract,
                "intercept_audit": intercept_audit,
                "metrics": metrics,
            }
        )
    return result


def _row_physical_metrics(row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    physical_available = row.get("physical_metrics_available")
    physical_reason = row.get("physical_metrics_unavailable_reason")
    metrics: dict[str, dict[str, Any]] = {}
    mappings = (
        ("active_primary_pair_success_count", "pair_success_count"),
        ("active_primary_pair_opportunity_count", "pair_opportunity_count"),
        ("target_success_count", "target_success_count"),
        ("target_opportunity_count", "target_opportunity_count"),
        ("coalition_success_count", "coalition_completion_count"),
        ("coalition_opportunity_count", "coalition_opportunity_count"),
    )
    for target_name, source_name in mappings:
        if physical_available is False:
            metrics[target_name] = _unavailable(
                str(physical_reason or "physical_metrics_explicitly_unavailable"),
                source="suite_row",
            )
            continue
        availability_name = (
            "coalition_completion_availability"
            if source_name == "coalition_completion_count"
            else f"{source_name}_availability"
        )
        metrics[target_name] = _row_count_metric(
            row,
            source_name,
            availability_name=availability_name,
        )
    return metrics


def _row_count_metric(
    row: Mapping[str, Any],
    field: str,
    *,
    availability_name: str | None = None,
) -> dict[str, Any]:
    availability_name = availability_name or f"{field}_availability"
    availability = row.get(availability_name)
    if availability is not None and availability != "available":
        return _unavailable(
            str(
                row.get(f"{field}_unavailable_reason")
                or row.get("coalition_completion_unavailable_reason")
                or f"{availability_name}={availability}"
            ),
            source="suite_row",
        )
    if field not in row:
        return _unavailable(f"{field}_missing", source="suite_row")
    value = _nonnegative_integer(row[field])
    if value is None:
        return _unavailable(f"{field}_invalid", source="suite_row")
    return _available(value, source="suite_row")


def _intercept_metrics(
    row: Mapping[str, Any],
    *,
    summary_dir: Path,
    expected_clock_speed: float,
) -> dict[str, dict[str, Any]]:
    source = row.get("intercept_summary")
    try:
        payload, evidence_path = _load_registered_json(source, summary_dir=summary_dir)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        reason = f"intercept_summary_unavailable:{type(exc).__name__}"
        return {
            name: _unavailable(reason, source="intercept_summary")
            for name in (
                "second_primary_5m_success_count",
                "second_primary_opportunity_count",
                "second_primary_min_distance_m",
                "active_primary_final_lock_count",
                "active_primary_final_lock_opportunity_count",
                "coalition_terminal_consensus_count",
                "coalition_terminal_consensus_opportunity_count",
                "collision_stop_count",
                "collision_stop_opportunity_count",
            )
        }
    pairs = payload.get("pairs")
    parameters = payload.get("parameters")
    if isinstance(parameters, Mapping) and "clock_speed" in parameters:
        artifact_clock_speed = _finite_nonnegative(parameters["clock_speed"])
        if artifact_clock_speed is None or not math.isclose(
            artifact_clock_speed,
            expected_clock_speed,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ClockSpeedComparisonValidationError(
                f"{evidence_path}: intercept ClockSpeed conflicts with suite/case provenance"
            )
    if not _is_sequence(pairs) or not all(isinstance(item, Mapping) for item in pairs):
        reason = "intercept_summary_pairs_missing_or_invalid"
        return {
            name: _unavailable(reason, source=evidence_path)
            for name in (
                "second_primary_5m_success_count",
                "second_primary_opportunity_count",
                "second_primary_min_distance_m",
                "active_primary_final_lock_count",
                "active_primary_final_lock_opportunity_count",
                "coalition_terminal_consensus_count",
                "coalition_terminal_consensus_opportunity_count",
                "collision_stop_count",
                "collision_stop_opportunity_count",
            )
        }
    active_primaries = [
        dict(pair)
        for pair in pairs
        if pair.get("member_role") == "primary"
        and pair.get("required_primary") is True
        and pair.get("activation_state") == "active"
    ]
    source_name = evidence_path
    by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    valid_identity = True
    for pair in active_primaries:
        target_id = pair.get("target_id")
        resource_id = pair.get("resource_id")
        if not isinstance(target_id, str) or not isinstance(resource_id, str):
            valid_identity = False
            continue
        by_target[target_id].append(pair)
    cooperative_groups = [
        sorted(group, key=lambda item: str(item["resource_id"]))
        for group in by_target.values()
        if len(group) > 1
    ]

    second_metrics: dict[str, dict[str, Any]]
    if not valid_identity or len(cooperative_groups) != 1:
        second_metrics = {
            "second_primary_5m_success_count": _unavailable(
                "second_primary_group_not_unique", source=source_name
            ),
            "second_primary_opportunity_count": _unavailable(
                "second_primary_group_not_unique", source=source_name
            ),
            "second_primary_min_distance_m": _unavailable(
                "second_primary_group_not_unique", source=source_name
            ),
        }
    else:
        second = cooperative_groups[0][1]
        physical_available = second.get("physical_evidence_available")
        success = second.get("physical_success")
        distance = _finite_nonnegative(second.get("physical_min_range_m"))
        if physical_available is not True or not isinstance(success, bool):
            second_metrics = {
                "second_primary_5m_success_count": _unavailable(
                    "second_primary_physical_result_unavailable", source=source_name
                ),
                "second_primary_opportunity_count": _unavailable(
                    "second_primary_physical_result_unavailable", source=source_name
                ),
                "second_primary_min_distance_m": _unavailable(
                    "second_primary_physical_result_unavailable", source=source_name
                ),
            }
        else:
            second_metrics = {
                "second_primary_5m_success_count": _available(
                    int(success), source=source_name
                ),
                "second_primary_opportunity_count": _available(1, source=source_name),
                "second_primary_min_distance_m": (
                    _available(distance, source=source_name)
                    if distance is not None
                    else _unavailable(
                        "second_primary_physical_min_range_missing", source=source_name
                    )
                ),
            }

    lock_values = [pair.get("terminal_locked") for pair in active_primaries]
    if active_primaries and all(isinstance(value, bool) for value in lock_values):
        lock_metrics = {
            "active_primary_final_lock_count": _available(
                sum(bool(value) for value in lock_values), source=source_name
            ),
            "active_primary_final_lock_opportunity_count": _available(
                len(lock_values), source=source_name
            ),
        }
    else:
        lock_metrics = {
            "active_primary_final_lock_count": _unavailable(
                "active_primary_terminal_lock_state_incomplete", source=source_name
            ),
            "active_primary_final_lock_opportunity_count": _unavailable(
                "active_primary_terminal_lock_state_incomplete", source=source_name
            ),
        }

    if cooperative_groups and all(
        all(isinstance(pair.get("terminal_locked"), bool) for pair in group)
        for group in cooperative_groups
    ):
        consensus_metrics = {
            "coalition_terminal_consensus_count": _available(
                sum(
                    all(bool(pair["terminal_locked"]) for pair in group)
                    for group in cooperative_groups
                ),
                source=source_name,
            ),
            "coalition_terminal_consensus_opportunity_count": _available(
                len(cooperative_groups), source=source_name
            ),
        }
    else:
        consensus_metrics = {
            "coalition_terminal_consensus_count": _unavailable(
                "coalition_terminal_lock_state_incomplete", source=source_name
            ),
            "coalition_terminal_consensus_opportunity_count": _unavailable(
                "coalition_terminal_lock_state_incomplete", source=source_name
            ),
        }

    stop_values = [pair.get("control_stop_reason") for pair in active_primaries]
    if active_primaries and all(
        value is None or isinstance(value, str) for value in stop_values
    ) and all("control_stop_reason" in pair for pair in active_primaries):
        collision_metrics = {
            "collision_stop_count": _available(
                sum(value == "collision_stop" for value in stop_values),
                source=source_name,
            ),
            "collision_stop_opportunity_count": _available(
                len(stop_values), source=source_name
            ),
        }
    else:
        collision_metrics = {
            "collision_stop_count": _unavailable(
                "active_primary_control_stop_reason_incomplete", source=source_name
            ),
            "collision_stop_opportunity_count": _unavailable(
                "active_primary_control_stop_reason_incomplete", source=source_name
            ),
        }
    return {**second_metrics, **lock_metrics, **consensus_metrics, **collision_metrics}


def _intercept_contract_audit(
    row: Mapping[str, Any],
    *,
    summary_dir: Path,
) -> dict[str, Any]:
    source = row.get("intercept_summary")
    try:
        payload, evidence_path = _load_registered_json(source, summary_dir=summary_dir)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {
            "availability": "unavailable",
            "unavailable_reason": (
                f"intercept_summary_unavailable:{type(exc).__name__}"
            ),
            "evidence_path": str(source) if source is not None else None,
            "standby_reserve_excluded_from_active_primary_success": True,
        }
    pairs = payload.get("pairs")
    if not _is_sequence(pairs) or not all(isinstance(item, Mapping) for item in pairs):
        return {
            "availability": "unavailable",
            "unavailable_reason": "intercept_summary_pairs_missing_or_invalid",
            "evidence_path": evidence_path,
            "standby_reserve_excluded_from_active_primary_success": True,
        }

    active_primaries = [
        item
        for item in pairs
        if item.get("member_role") == "primary"
        and item.get("required_primary") is True
        and item.get("activation_state") == "active"
    ]
    standby_reserves = [
        item
        for item in pairs
        if item.get("member_role") == "reserve"
        and item.get("required_primary") is False
        and item.get("activation_state") == "standby"
    ]
    active_targets = {
        item.get("target_id")
        for item in active_primaries
        if isinstance(item.get("target_id"), str) and item.get("target_id")
    }
    target_group_sizes: dict[str, int] = defaultdict(int)
    for item in active_primaries:
        target_id = item.get("target_id")
        if isinstance(target_id, str) and target_id:
            target_group_sizes[target_id] += 1
    active_success_values = [
        item.get("physical_success")
        for item in active_primaries
        if item.get("physical_evidence_available") is True
    ]
    reserve_success_values = [
        item.get("physical_success")
        for item in standby_reserves
        if item.get("physical_evidence_available") is True
    ]
    success_semantics = payload.get("success_semantics")
    active_physical_complete = (
        len(active_success_values) == len(active_primaries)
        and all(isinstance(value, bool) for value in active_success_values)
    )
    target_success_count: int | None = None
    coalition_success_count: int | None = None
    if active_physical_complete:
        target_success_count = len(
            {
                item["target_id"]
                for item in active_primaries
                if item.get("physical_success") is True
                and isinstance(item.get("target_id"), str)
                and item.get("target_id")
            }
        )
        coalition_success_count = sum(
            all(item.get("physical_success") is True for item in active_primaries if item.get("target_id") == target_id)
            for target_id, count in target_group_sizes.items()
            if count > 1
        )
    return {
        "availability": "available",
        "unavailable_reason": "",
        "evidence_path": evidence_path,
        "active_primary_count": len(active_primaries),
        "active_primary_target_count": len(active_targets),
        "active_primary_coalition_count": sum(
            count > 1 for count in target_group_sizes.values()
        ),
        "active_primary_physical_success_count": (
            sum(value is True for value in active_success_values)
            if active_physical_complete
            else None
        ),
        "active_primary_target_physical_success_count": target_success_count,
        "active_primary_coalition_physical_success_count": coalition_success_count,
        "standby_reserve_count": len(standby_reserves),
        "standby_reserve_physical_success_count": sum(
            value is True for value in reserve_success_values
        ),
        "standby_reserve_excluded_from_active_primary_success": True,
        "raw_top_level_success_count": _nonnegative_integer(
            payload.get("success_count")
        ),
        "success_semantics_pair_physical_success_count": (
            _nonnegative_integer(success_semantics.get("pair_physical_success_count"))
            if isinstance(success_semantics, Mapping)
            else None
        ),
    }


def _opportunity_contract(
    row: Mapping[str, Any],
    intercept_audit: Mapping[str, Any],
) -> dict[str, Any]:
    observed = {
        "active_primary_pair": _nonnegative_integer(row.get("pair_opportunity_count")),
        "target": _nonnegative_integer(row.get("target_opportunity_count")),
        "coalition": _nonnegative_integer(row.get("coalition_opportunity_count")),
    }
    derived = {
        "active_primary_pair": _nonnegative_integer(
            intercept_audit.get("active_primary_count")
        ),
        "target": _nonnegative_integer(
            intercept_audit.get("active_primary_target_count")
        ),
        "coalition": _nonnegative_integer(
            intercept_audit.get("active_primary_coalition_count")
        ),
    }
    reasons: list[str] = []
    actual_execution_status = row.get("d7_actual_execution_status")
    actual_reasons_raw = row.get("d7_actual_execution_unavailable_reasons")
    actual_reasons = (
        [str(item) for item in actual_reasons_raw]
        if _is_sequence(actual_reasons_raw)
        else []
    )
    if actual_execution_status != "available":
        reasons.append(
            "d7_actual_execution_status_missing"
            if actual_execution_status is None
            else f"d7_actual_execution_status={actual_execution_status}"
        )
        reasons.extend(actual_reasons)

    if intercept_audit.get("availability") != "available":
        reasons.append(
            str(
                intercept_audit.get("unavailable_reason")
                or "intercept_contract_audit_unavailable"
            )
        )
    for name, expected in M5N2_EXPECTED_OPPORTUNITIES.items():
        if observed[name] != expected:
            reasons.append(
                f"suite_row_{name}_opportunity_mismatch:"
                f"expected={expected},observed={observed[name]}"
            )
        if derived[name] != expected:
            reasons.append(
                f"intercept_{name}_opportunity_mismatch:"
                f"expected={expected},observed={derived[name]}"
            )
    reasons = list(dict.fromkeys(reasons))
    return {
        "availability": "available" if not reasons else "unavailable",
        "status": "match" if not reasons else "contract_mismatch",
        "expected": dict(M5N2_EXPECTED_OPPORTUNITIES),
        "observed": observed,
        "intercept_derived": derived,
        "actual_execution_status": actual_execution_status,
        "actual_execution_reasons": actual_reasons,
        "reasons": reasons,
        "mismatch_policy": "affected_case_metrics_unavailable",
        "missing_evidence_is_zero": False,
        "standby_reserve_in_active_primary": False,
    }


def _timing_metrics(
    row: Mapping[str, Any],
    *,
    summary_dir: Path,
    clock_speed: float,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for layer, field in (
        ("main_bus", "main_stage_timings"),
        ("control_tick", "control_tick_stage_timings"),
    ):
        source = row.get(field)
        path = _resolve_registered_path(source, summary_dir=summary_dir)
        try:
            if path is None:
                raise FileNotFoundError(f"{field} not registered")
            records = load_stage_timing_jsonl(path, expected_layer=layer)
            timing = summarize_stage_timing_records(
                records,
                expected_layer=layer,
                evidence_path=path,
            )
        except (OSError, StageTimingValidationError, ValueError) as exc:
            reason = f"{layer}_timing_unavailable:{type(exc).__name__}"
            result[f"{layer}_wall_mean_ms"] = _unavailable(reason, source=str(path))
            result[f"{layer}_wall_p95_ms"] = _unavailable(reason, source=str(path))
            result[f"{layer}_timing_sample_count"] = _unavailable(
                reason, source=str(path)
            )
            continue
        total = timing.get("total", {})
        result[f"{layer}_wall_mean_ms"] = _available(
            total["mean_ms"], source=str(path)
        )
        result[f"{layer}_wall_p95_ms"] = _available(
            total["p95_ms"], source=str(path)
        )
        result[f"{layer}_timing_sample_count"] = _available(
            timing["record_count"], source=str(path)
        )

    control_mean = result.get("control_tick_wall_mean_ms", {})
    if control_mean.get("availability") == "available":
        result["simulated_time_per_tick_s"] = _available(
            float(control_mean["value"]) / 1000.0 * clock_speed,
            source="control_tick_wall_mean_ms*provenance.ClockSpeed",
        )
    else:
        result["simulated_time_per_tick_s"] = _unavailable(
            str(control_mean.get("unavailable_reason") or "control_tick_timing_unavailable"),
            source="control_tick_wall_mean_ms*provenance.ClockSpeed",
        )
    return result


def _case_wall_metric(row: Mapping[str, Any]) -> dict[str, Any]:
    wall = row.get("wall_timing")
    if isinstance(wall, Mapping):
        availability = wall.get("availability")
        if availability is not None and availability != "available":
            return _unavailable(
                str(wall.get("unavailable_reason") or f"availability={availability}"),
                source="suite_row.wall_timing",
            )
        for field in ("elapsed_s", "wall_elapsed_s", "duration_s"):
            if field in wall:
                value = _finite_nonnegative(wall[field])
                if value is not None:
                    return _available(value, source=f"suite_row.wall_timing.{field}")
                return _unavailable(
                    f"wall_timing.{field}_invalid", source="suite_row.wall_timing"
                )
    for field in ("case_wall_elapsed_s", "wall_elapsed_s"):
        if field in row:
            availability = row.get(f"{field}_availability")
            if availability is not None and availability != "available":
                return _unavailable(
                    str(row.get(f"{field}_unavailable_reason") or availability),
                    source=f"suite_row.{field}",
                )
            value = _finite_nonnegative(row[field])
            if value is not None:
                return _available(value, source=f"suite_row.{field}")
            return _unavailable(f"{field}_invalid", source=f"suite_row.{field}")
    return _unavailable("case_wall_timing_missing", source="suite_row")


def _build_aggregates(case_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[float, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in case_rows:
        grouped[(float(row["clock_speed"]), str(row["profile"]))].append(row)
    aggregates: list[dict[str, Any]] = []
    for (clock_speed, profile), rows in sorted(grouped.items()):
        metrics = {
            "active_primary_pair_success_rate": _aggregate_rate(
                rows,
                "active_primary_pair_success_count",
                "active_primary_pair_opportunity_count",
            ),
            "target_success_rate": _aggregate_rate(
                rows, "target_success_count", "target_opportunity_count"
            ),
            "coalition_success_rate": _aggregate_rate(
                rows, "coalition_success_count", "coalition_opportunity_count"
            ),
            "second_primary_5m_success_rate": _aggregate_rate(
                rows,
                "second_primary_5m_success_count",
                "second_primary_opportunity_count",
            ),
            "active_primary_final_lock_rate": _aggregate_rate(
                rows,
                "active_primary_final_lock_count",
                "active_primary_final_lock_opportunity_count",
            ),
            "coalition_terminal_consensus_rate": _aggregate_rate(
                rows,
                "coalition_terminal_consensus_count",
                "coalition_terminal_consensus_opportunity_count",
            ),
            "collision_stop_rate": _aggregate_rate(
                rows, "collision_stop_count", "collision_stop_opportunity_count"
            ),
        }
        for name in _DISTRIBUTION_METRICS:
            metrics[name] = _aggregate_distribution(rows, name)
        metrics["truth_identity_online_use_count"] = _aggregate_sum(
            rows, "truth_identity_online_use_count"
        )
        metrics["truth_state_online_use_count"] = _aggregate_sum(
            rows, "truth_state_online_use_count"
        )
        aggregates.append(
            {
                "clock_speed": clock_speed,
                "profile": profile,
                "comparison_role": rows[0]["comparison_role"],
                "case_count": len(rows),
                "metrics": metrics,
            }
        )
    return aggregates


def _aggregate_rate(
    rows: Sequence[Mapping[str, Any]],
    numerator_name: str,
    denominator_name: str,
) -> dict[str, Any]:
    numerator_metrics = [row["metrics"][numerator_name] for row in rows]
    denominator_metrics = [row["metrics"][denominator_name] for row in rows]
    available = [
        numerator.get("availability") == "available"
        and denominator.get("availability") == "available"
        for numerator, denominator in zip(numerator_metrics, denominator_metrics)
    ]
    if not all(available):
        return _aggregate_unavailable(
            rows,
            available,
            reason=f"incomplete_{numerator_name}_or_{denominator_name}",
        )
    numerator = sum(int(metric["value"]) for metric in numerator_metrics)
    denominator = sum(int(metric["value"]) for metric in denominator_metrics)
    if denominator <= 0:
        return _aggregate_unavailable(
            rows,
            available,
            reason=f"nonpositive_{denominator_name}",
        )
    return {
        "availability": "available",
        "value": numerator / denominator,
        "numerator": numerator,
        "denominator": denominator,
        "available_case_count": len(rows),
        "unavailable_case_count": 0,
        "unavailable_reason": "",
    }


def _aggregate_distribution(
    rows: Sequence[Mapping[str, Any]],
    name: str,
) -> dict[str, Any]:
    metrics = [row["metrics"][name] for row in rows]
    available = [metric.get("availability") == "available" for metric in metrics]
    if not all(available):
        return _aggregate_unavailable(
            rows,
            available,
            reason=f"incomplete_{name}",
        )
    values = sorted(float(metric["value"]) for metric in metrics)
    return {
        "availability": "available",
        "value": statistics.fmean(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "min": values[0],
        "max": values[-1],
        "sample_count": len(values),
        "available_case_count": len(rows),
        "unavailable_case_count": 0,
        "unavailable_reason": "",
    }


def _aggregate_sum(
    rows: Sequence[Mapping[str, Any]],
    name: str,
) -> dict[str, Any]:
    metrics = [row["metrics"][name] for row in rows]
    available = [metric.get("availability") == "available" for metric in metrics]
    if not all(available):
        return _aggregate_unavailable(
            rows,
            available,
            reason=f"incomplete_{name}",
        )
    return {
        "availability": "available",
        "value": sum(int(metric["value"]) for metric in metrics),
        "available_case_count": len(rows),
        "unavailable_case_count": 0,
        "unavailable_reason": "",
    }


def _aggregate_unavailable(
    rows: Sequence[Mapping[str, Any]],
    available: Sequence[bool],
    *,
    reason: str,
) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "value": None,
        "available_case_count": sum(available),
        "unavailable_case_count": len(rows) - sum(available),
        "unavailable_case_ids": [
            str(row["case_id"])
            for row, is_available in zip(rows, available)
            if not is_available
        ],
        "unavailable_reason": reason,
    }


def _build_paired_rows(
    case_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in case_rows:
        grouped[(str(row["case_id"]), str(row["profile"]), int(row["seed"]))].append(
            row
        )
    result = []
    for key, rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda row: float(row["clock_speed"]))
        result.append(
            {
                "case_id": key[0],
                "profile": key[1],
                "seed": key[2],
                "clock_speeds": [row["clock_speed"] for row in ordered],
                "metrics_by_clock_speed": {
                    str(row["clock_speed"]): row["metrics"] for row in ordered
                },
            }
        )
    return result


def _build_truth_audit(case_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def audit(name: str) -> dict[str, Any]:
        metrics = [row["metrics"][name] for row in case_rows]
        available = [metric.get("availability") == "available" for metric in metrics]
        if not all(available):
            return {
                "availability": "unavailable",
                "total_online_use_count": None,
                "all_zero": None,
                "available_case_count": sum(available),
                "unavailable_case_count": len(metrics) - sum(available),
            }
        total = sum(int(metric["value"]) for metric in metrics)
        return {
            "availability": "available",
            "total_online_use_count": total,
            "all_zero": total == 0,
            "available_case_count": len(metrics),
            "unavailable_case_count": 0,
        }

    return {
        "scope": "online identity and online target-state use; offline truth scoring excluded",
        "identity": audit("truth_identity_online_use_count"),
        "state": audit("truth_state_online_use_count"),
    }


def _build_opportunity_contract_audit(
    case_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    mismatch_cases: list[dict[str, Any]] = []
    for row in case_rows:
        contract = row.get("opportunity_contract", {})
        if not isinstance(contract, Mapping) or contract.get("status") != "match":
            mismatch_cases.append(
                {
                    "clock_speed": row.get("clock_speed"),
                    "case_id": row.get("case_id"),
                    "profile": row.get("profile"),
                    "seed": row.get("seed"),
                    "availability": (
                        contract.get("availability")
                        if isinstance(contract, Mapping)
                        else "unavailable"
                    ),
                    "status": (
                        contract.get("status")
                        if isinstance(contract, Mapping)
                        else "contract_mismatch"
                    ),
                    "expected": (
                        contract.get("expected", {})
                        if isinstance(contract, Mapping)
                        else dict(M5N2_EXPECTED_OPPORTUNITIES)
                    ),
                    "observed": (
                        contract.get("observed", {})
                        if isinstance(contract, Mapping)
                        else {}
                    ),
                    "intercept_derived": (
                        contract.get("intercept_derived", {})
                        if isinstance(contract, Mapping)
                        else {}
                    ),
                    "actual_execution_status": (
                        contract.get("actual_execution_status")
                        if isinstance(contract, Mapping)
                        else None
                    ),
                    "reasons": (
                        list(contract.get("reasons", []))
                        if isinstance(contract, Mapping)
                        else ["opportunity_contract_missing"]
                    ),
                    "intercept_audit": row.get("intercept_audit", {}),
                }
            )
    return {
        "availability": "available",
        "expected_per_case": dict(M5N2_EXPECTED_OPPORTUNITIES),
        "case_count": len(case_rows),
        "match_case_count": len(case_rows) - len(mismatch_cases),
        "mismatch_case_count": len(mismatch_cases),
        "mismatch_cases": mismatch_cases,
        "mismatch_policy": "affected_case_metrics_unavailable",
        "standby_reserve_in_active_primary": False,
    }


def _load_registered_json(
    source: Any,
    *,
    summary_dir: Path,
) -> tuple[dict[str, Any], str]:
    if isinstance(source, Mapping):
        return dict(source), "inline:intercept_summary"
    path = _resolve_registered_path(source, summary_dir=summary_dir)
    if path is None:
        raise ValueError("artifact path not registered")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("artifact root must be an object")
    return dict(payload), str(path)


def _resolve_registered_path(source: Any, *, summary_dir: Path) -> Path | None:
    if not isinstance(source, (str, Path)) or not str(source):
        return None
    path = Path(source)
    if path.is_absolute():
        return path
    candidates = (summary_dir / path, Path.cwd() / path)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return (summary_dir / path).resolve()


def _available(value: Any, *, source: str | None) -> dict[str, Any]:
    return {
        "availability": "available",
        "value": value,
        "unavailable_reason": "",
        "source": source,
    }


def _unavailable(reason: str, *, source: str | None) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "value": None,
        "unavailable_reason": reason,
        "source": source,
    }


def _nonnegative_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return int(value)


def _finite_nonnegative(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0.0:
        return None
    return normalized


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _case_csv_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = {field: row.get(field) for field in _CASE_CSV_FIELDS}
    contract = row.get("opportunity_contract", {})
    intercept = row.get("intercept_audit", {})
    if isinstance(contract, Mapping):
        expected = contract.get("expected", {})
        observed = contract.get("observed", {})
        result.update(
            {
                "opportunity_contract_availability": contract.get("availability"),
                "opportunity_contract_status": contract.get("status"),
                "opportunity_contract_reasons": ";".join(
                    str(reason) for reason in contract.get("reasons", [])
                ),
                "expected_active_primary_pair_opportunities": _get(
                    expected, "active_primary_pair"
                ),
                "observed_active_primary_pair_opportunities": _get(
                    observed, "active_primary_pair"
                ),
                "expected_target_opportunities": _get(expected, "target"),
                "observed_target_opportunities": _get(observed, "target"),
                "expected_coalition_opportunities": _get(expected, "coalition"),
                "observed_coalition_opportunities": _get(observed, "coalition"),
            }
        )
    if isinstance(intercept, Mapping):
        result["standby_reserve_count"] = intercept.get("standby_reserve_count")
        result["standby_reserve_physical_success_count"] = intercept.get(
            "standby_reserve_physical_success_count"
        )
    metrics = row.get("metrics", {})
    for name in (
        *_COUNT_METRICS,
        *_DISTRIBUTION_METRICS,
        "main_bus_timing_sample_count",
        "control_tick_timing_sample_count",
    ):
        metric = metrics.get(name, {}) if isinstance(metrics, Mapping) else {}
        result[name] = metric.get("value")
        result[f"{name}_availability"] = metric.get(
            "availability", "unavailable"
        )
        result[f"{name}_unavailable_reason"] = metric.get(
            "unavailable_reason", ""
        )
    return result


def _aggregate_csv_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = {field: row.get(field) for field in _AGGREGATE_CSV_FIELDS}
    metrics = row.get("metrics", {})
    if not isinstance(metrics, Mapping):
        return result
    for name, metric in metrics.items():
        if not isinstance(metric, Mapping):
            continue
        result[name] = metric.get("value")
        result[f"{name}_availability"] = metric.get("availability")
        result[f"{name}_available_case_count"] = metric.get(
            "available_case_count"
        )
        result[f"{name}_unavailable_reason"] = metric.get("unavailable_reason")
    return result


def _metric_text(metric: Any) -> str:
    if not isinstance(metric, Mapping) or metric.get("availability") != "available":
        return "unavailable"
    value = metric.get("value")
    if value is None:
        return "unavailable"
    if "numerator" in metric and "denominator" in metric:
        return f"{metric['numerator']}/{metric['denominator']} ({float(value):.3f})"
    return f"{float(value):.4g}" if isinstance(value, float) else str(value)


def _audit_text(audit: Any) -> str:
    if not isinstance(audit, Mapping) or audit.get("availability") != "available":
        if isinstance(audit, Mapping):
            return (
                "unavailable; available/unavailable="
                f"{audit.get('available_case_count')}/{audit.get('unavailable_case_count')}"
            )
        return "unavailable"
    return (
        f"available; total={audit.get('total_online_use_count')}; "
        f"all_zero={str(audit.get('all_zero')).lower()}"
    )


def _get(value: Any, *path: str) -> Any:
    current = value
    for field in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(field)
    return current


def _write_plot(summary: Mapping[str, Any], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    cjk_font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if cjk_font_path.exists():
        font_manager.fontManager.addfont(str(cjk_font_path))
        family = font_manager.FontProperties(fname=str(cjk_font_path)).get_name()
    else:
        family = "DejaVu Sans"
    plt.rcParams["font.sans-serif"] = [family, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    aggregates = summary.get("aggregates", [])
    profiles = sorted({str(row["profile"]) for row in aggregates})
    fig, axes = plt.subplots(2, 2, figsize=(14.0, 10.0))

    def series(profile: str, metric_name: str) -> tuple[list[float], list[float]]:
        selected = sorted(
            (row for row in aggregates if row["profile"] == profile),
            key=lambda row: float(row["clock_speed"]),
        )
        x: list[float] = []
        y: list[float] = []
        for row in selected:
            metric = row["metrics"].get(metric_name, {})
            if metric.get("availability") == "available":
                x.append(float(row["clock_speed"]))
                y.append(float(metric["value"]))
        return x, y

    colors = ("#20639b", "#d1495b", "#2a9d8f", "#f4a261")
    success_axis = axes[0][0]
    for profile_index, profile in enumerate(profiles):
        for metric_index, (name, label, marker) in enumerate(
            (
                ("active_primary_pair_success_rate", "pair", "o"),
                ("target_success_rate", "target", "s"),
                ("coalition_success_rate", "coalition", "^"),
            )
        ):
            x, y = series(profile, name)
            success_axis.plot(
                x,
                y,
                marker=marker,
                color=colors[profile_index % len(colors)],
                linestyle=("-", "--", ":")[metric_index],
                label=f"{profile}:{label}",
            )
    success_axis.set_title("三层物理成功率")
    success_axis.set_ylabel("成功率")
    success_axis.set_ylim(-0.03, 1.03)

    distance_axis = axes[0][1]
    for index, profile in enumerate(profiles):
        x, y = series(profile, "second_primary_min_distance_m")
        distance_axis.plot(
            x, y, marker="o", color=colors[index], label=profile
        )
    distance_axis.axhline(5.0, color="#555555", linestyle="--", label="5 m")
    distance_axis.set_title("第二 primary 最小距离")
    distance_axis.set_ylabel("距离（m）")

    terminal_axis = axes[1][0]
    for profile_index, profile in enumerate(profiles):
        for metric_index, (name, label) in enumerate(
            (
                ("active_primary_final_lock_rate", "final lock"),
                ("coalition_terminal_consensus_rate", "consensus"),
                ("collision_stop_rate", "collision stop"),
            )
        ):
            x, y = series(profile, name)
            terminal_axis.plot(
                x,
                y,
                marker=("o", "s", "^")[metric_index],
                color=colors[profile_index],
                linestyle=("-", "--", ":")[metric_index],
                label=f"{profile}:{label}",
            )
    terminal_axis.set_title("末端锁、共识与 collision stop")
    terminal_axis.set_ylabel("比例")
    terminal_axis.set_ylim(-0.03, 1.03)

    timing_axis = axes[1][1]
    normalized_axis = timing_axis.twinx()
    for profile_index, profile in enumerate(profiles):
        for metric_index, (name, label) in enumerate(
            (
                ("main_bus_wall_mean_ms", "main bus wall"),
                ("control_tick_wall_mean_ms", "control tick wall"),
            )
        ):
            x, y = series(profile, name)
            timing_axis.plot(
                x,
                y,
                marker=("o", "s")[metric_index],
                color=colors[profile_index],
                linestyle=("-", "--")[metric_index],
                label=f"{profile}:{label}",
            )
        normalized_x, normalized_y = series(
            profile, "simulated_time_per_tick_s"
        )
        normalized_axis.plot(
            normalized_x,
            normalized_y,
            marker="^",
            color=colors[profile_index],
            linestyle=":",
            label=f"{profile}:simulated/tick",
        )
    timing_axis.set_title("嵌套 timing 分层对比（禁止相加）")
    timing_axis.set_ylabel("wall time（ms）")
    normalized_axis.set_ylabel("simulated time/tick（s）")

    for axis in axes.flat:
        axis.set_xlabel("ClockSpeed")
        axis.set_xticks(list(EXPECTED_CLOCK_SPEEDS))
        axis.grid(alpha=0.25)
        axis.legend(fontsize=7)
    normalized_axis.legend(fontsize=7, loc="center right")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
