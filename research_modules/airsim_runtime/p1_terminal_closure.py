"""Case definitions and reporting for the P1 terminal-closure AirSim suite."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
from pathlib import Path
from typing import Any, Iterable


SUITE_NAME = "p1_terminal_closure"
SUITE_VERSION = "p1-terminal-closure-v3"
THRESHOLD_VERSION = "p1-terminal-thresholds-v1"


@dataclass(frozen=True)
class TerminalClosureCase:
    """One reset-separated SimpleFlight experiment case."""

    case_id: str
    family: str
    profile: str
    seed: int
    resource_count: int
    target_count: int
    duration_s: float
    intercept_altitude_z: float
    guidance_law: str = "png_vm"
    soft_prediction_enabled: bool = False
    trend_coast_enabled: bool = False
    dropout_frames: int = 0
    dropout_start_s: float | None = None
    dropout_end_s: float | None = None

    def metadata(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "calibration_suite": SUITE_NAME,
            "calibration_suite_version": SUITE_VERSION,
            "threshold_version": THRESHOLD_VERSION,
            "comparison_role": (
                "baseline" if self.profile == "baseline" else "enhanced"
            ),
            "scenario_version": (
                "airsim-m5n2-high-clearance-v1"
                if self.family == "m5n2_paired"
                else "airsim-2v2-png-ttc-v2"
                if self.family == "png_ttc"
                else "airsim-2v2-locked-dropout-v2"
            ),
        }


def build_terminal_closure_cases(
    seeds: Iterable[int],
    *,
    dropout_frames: Iterable[int] = (1, 2, 3, 4, 5),
    control_dt_s: float = 0.1,
    dropout_start_s: float = 0.8,
    m5n2_duration_s: float = 35.0,
    dropout_duration_s: float = 8.0,
) -> tuple[TerminalClosureCase, ...]:
    """Build the frozen M5N2, png_ttc, and locked-dropout matrix."""

    normalized_seeds = tuple(dict.fromkeys(int(seed) for seed in seeds))
    normalized_dropout = tuple(dict.fromkeys(int(value) for value in dropout_frames))
    if not normalized_seeds:
        raise ValueError("at least one seed is required")
    if control_dt_s <= 0.0:
        raise ValueError("control_dt_s must be positive")
    if dropout_start_s < 0.0:
        raise ValueError("dropout_start_s must be non-negative")
    if any(value < 1 for value in normalized_dropout):
        raise ValueError("dropout frame counts must be positive")

    cases: list[TerminalClosureCase] = []
    for seed in normalized_seeds:
        for profile, soft_prediction, trend_coast in (
            ("baseline", False, False),
            ("candidate_soft_prediction_trend_coast", True, True),
        ):
            cases.append(
                TerminalClosureCase(
                    case_id=f"m5n2_{profile}_seed{seed:03d}",
                    family="m5n2_paired",
                    profile=profile,
                    seed=seed,
                    resource_count=5,
                    target_count=2,
                    duration_s=float(m5n2_duration_s),
                    intercept_altitude_z=-30.0,
                    guidance_law="png_vm",
                    soft_prediction_enabled=soft_prediction,
                    trend_coast_enabled=trend_coast,
                )
            )
        cases.append(
            TerminalClosureCase(
                case_id=f"png_ttc_2v2_seed{seed:03d}",
                family="png_ttc",
                profile="png_ttc",
                seed=seed,
                resource_count=2,
                target_count=2,
                duration_s=float(dropout_duration_s),
                intercept_altitude_z=-5.0,
                guidance_law="png_ttc",
            )
        )
        for frame_count in normalized_dropout:
            cases.append(
                TerminalClosureCase(
                    case_id=f"dropout_{frame_count}f_seed{seed:03d}",
                    family="locked_dropout",
                    profile=f"dropout_{frame_count}_frames",
                    seed=seed,
                    resource_count=2,
                    target_count=2,
                    duration_s=float(dropout_duration_s),
                    intercept_altitude_z=-5.0,
                    guidance_law="png_vm",
                    soft_prediction_enabled=True,
                    trend_coast_enabled=False,
                    dropout_frames=frame_count,
                    dropout_start_s=float(dropout_start_s),
                    dropout_end_s=float(dropout_start_s + frame_count * control_dt_s),
                )
            )
    return tuple(cases)


def summarize_terminal_closure_rows(
    cases: Iterable[TerminalClosureCase],
    rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize paired outcomes without filling unavailable values with zero."""

    case_list = tuple(cases)
    row_list = [dict(row) for row in rows]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in row_list:
        grouped.setdefault((str(row.get("family")), str(row.get("profile"))), []).append(row)

    aggregates: list[dict[str, Any]] = []
    for (family, profile), selected in sorted(grouped.items()):
        aggregates.append(
            {
                "family": family,
                "profile": profile,
                "seed_count": len({row.get("seed") for row in selected}),
                "connected_count": sum(bool(row.get("connected")) for row in selected),
                "pair_opportunity_count": _sum_available(selected, "pair_opportunity_count"),
                "pair_success_count": _sum_available(selected, "pair_success_count"),
                "target_opportunity_count": _sum_available(selected, "target_opportunity_count"),
                "target_success_count": _sum_available(selected, "target_success_count"),
                "coalition_opportunity_count": _sum_available(selected, "coalition_opportunity_count"),
                "coalition_completion_count": _sum_available(selected, "coalition_completion_count"),
                "online_truth_use_count": _sum_available(selected, "online_truth_use_count"),
                "truth_identity_online_use_count": _sum_available(
                    selected, "truth_identity_online_use_count"
                ),
                "truth_state_online_use_count": _sum_available(
                    selected, "truth_state_online_use_count"
                ),
                "physical_metrics_available_count": sum(
                    row.get("physical_metrics_available") is True for row in selected
                ),
                "physical_metrics_unavailable_count": sum(
                    row.get("physical_metrics_available") is not True for row in selected
                ),
                "actual_execution_available_count": sum(
                    row.get("d7_actual_execution_status") == "available"
                    for row in selected
                ),
                "actual_execution_unavailable_count": sum(
                    row.get("d7_actual_execution_status") != "available"
                    for row in selected
                ),
                "contract_allowed_count": _sum_available(selected, "contract_allowed_count"),
                "control_allowed_count": _sum_available(selected, "control_allowed_count"),
                "mode_switched_count": _sum_available(selected, "mode_switched_count"),
                "physical_intercept_count": _sum_available(selected, "physical_intercept_count"),
                "terminal_switch_allowed_count": _sum_available(selected, "terminal_switch_allowed_count"),
                "terminal_delivery_expired_count": _sum_available(selected, "terminal_delivery_expired_count"),
                "terminal_prediction_window_expired_count": _sum_available(
                    selected, "terminal_prediction_window_expired_count"
                ),
                "terminal_prediction_count": _sum_available(selected, "terminal_prediction_count"),
            }
        )

    paired = _paired_m5n2_rows(row_list)
    all_results_present = len(case_list) == len(row_list)
    truth_identity_zero = bool(row_list) and all(
        row.get("truth_identity_online_use_count") == 0 for row in row_list
    )
    truth_state_zero = bool(row_list) and all(
        row.get("truth_state_online_use_count") == 0 for row in row_list
    )
    physical_available = bool(row_list) and all(
        row.get("physical_metrics_available") is True for row in row_list
    )
    actual_execution_all_available = bool(row_list) and all(
        row.get("d7_actual_execution_status") == "available" for row in row_list
    )
    dropout_acceptance = _dropout_acceptance(row_list)
    candidate_target_non_degradation = paired.get(
        "candidate_target_non_degradation"
    )
    candidate_pair_non_degradation = paired.get(
        "candidate_pair_non_degradation"
    )
    return {
        "calibration_suite": SUITE_NAME,
        "calibration_suite_version": SUITE_VERSION,
        "threshold_version": THRESHOLD_VERSION,
        "case_count": len(case_list),
        "result_count": len(row_list),
        "cases": [case.metadata() for case in case_list],
        "rows": row_list,
        "aggregates": aggregates,
        "m5n2_paired": paired,
        "acceptance": {
            "online_truth_use_zero": all(
                int(row.get("online_truth_use_count") or 0) == 0 for row in row_list
            ),
            "truth_identity_online_use_zero": truth_identity_zero,
            "truth_state_online_use_zero": truth_state_zero,
            "physical_metrics_available": physical_available,
            "actual_execution_all_available": actual_execution_all_available,
            "all_results_present": all_results_present,
            "candidate_target_non_degradation": candidate_target_non_degradation,
            "candidate_pair_non_degradation": candidate_pair_non_degradation,
            "dropout_matrix": dropout_acceptance,
            "overall_acceptance_passed": bool(
                all_results_present
                and truth_identity_zero
                and truth_state_zero
                and physical_available
                and actual_execution_all_available
                and candidate_target_non_degradation is True
                and candidate_pair_non_degradation is True
                and dropout_acceptance.get("all_passed") is True
            ),
        },
    }


def write_terminal_closure_bundle(
    output_dir: str | Path,
    cases: Iterable[TerminalClosureCase],
    rows: Iterable[dict[str, Any]],
) -> dict[str, Path]:
    """Write the main-owned execution index consumed later by D6."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = summarize_terminal_closure_rows(cases, rows)
    json_path = output_dir / "p1_terminal_closure_summary.json"
    csv_path = output_dir / "p1_terminal_closure_rows.csv"
    markdown_path = output_dir / "P1_TERMINAL_CLOSURE_AIRSIM_REPORT.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_csv(csv_path, payload["rows"])
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "markdown": markdown_path}


def _paired_m5n2_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [row for row in rows if row.get("family") == "m5n2_paired"]
    by_seed: dict[int, dict[str, dict[str, Any]]] = {}
    for row in selected:
        seed = int(row["seed"])
        by_seed.setdefault(seed, {})[str(row.get("profile"))] = row
    pairs: list[dict[str, Any]] = []
    for seed, profiles in sorted(by_seed.items()):
        baseline = profiles.get("baseline")
        candidate = profiles.get("candidate_soft_prediction_trend_coast")
        if baseline is None or candidate is None:
            continue
        pairs.append(
            {
                "seed": seed,
                "baseline_target_success": baseline.get("target_success_count"),
                "candidate_target_success": candidate.get("target_success_count"),
                "baseline_pair_success": baseline.get("pair_success_count"),
                "candidate_pair_success": candidate.get("pair_success_count"),
                "baseline_coalition_completion": baseline.get("coalition_completion_count"),
                "candidate_coalition_completion": candidate.get("coalition_completion_count"),
            }
        )
    target_deltas = _available_deltas(
        pairs, "baseline_target_success", "candidate_target_success"
    )
    pair_deltas = _available_deltas(
        pairs, "baseline_pair_success", "candidate_pair_success"
    )
    return {
        "pair_count": len(pairs),
        "rows": pairs,
        "target_success_delta_sum": sum(target_deltas) if target_deltas else None,
        "pair_success_delta_sum": sum(pair_deltas) if pair_deltas else None,
        "candidate_target_non_degradation": (
            all(delta >= 0 for delta in target_deltas) if target_deltas else None
        ),
        "candidate_pair_non_degradation": (
            all(delta >= 0 for delta in pair_deltas) if pair_deltas else None
        ),
    }


def _available_deltas(
    rows: Iterable[dict[str, Any]], baseline_key: str, candidate_key: str
) -> list[float]:
    values: list[float] = []
    for row in rows:
        baseline = row.get(baseline_key)
        candidate = row.get(candidate_key)
        if baseline is None or candidate is None:
            continue
        values.append(float(candidate) - float(baseline))
    return values


def _dropout_acceptance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [row for row in rows if row.get("family") == "locked_dropout"]
    by_frames: dict[int, list[dict[str, Any]]] = {}
    for row in selected:
        by_frames.setdefault(int(row.get("dropout_frames") or 0), []).append(row)
    results: list[dict[str, Any]] = []
    for frame_count, frame_rows in sorted(by_frames.items()):
        prediction_count = _sum_available(frame_rows, "terminal_prediction_count")
        expiry_count = _sum_available(
            frame_rows, "terminal_prediction_window_expired_count"
        )
        expected_expiry = frame_count >= 3
        row_passes = [
            bool(int(row.get("terminal_prediction_count") or 0) > 0)
            and (
                int(row.get("terminal_prediction_window_expired_count") or 0) > 0
                if expected_expiry
                else int(row.get("terminal_prediction_window_expired_count") or 0) == 0
            )
            for row in frame_rows
        ]
        passed = bool(row_passes) and all(row_passes)
        results.append(
            {
                "dropout_frames": frame_count,
                "expected_prediction_window_expiry": expected_expiry,
                "record_count": len(frame_rows),
                "passed_record_count": sum(row_passes),
                "prediction_count": prediction_count,
                "prediction_window_expired_count": expiry_count,
                "passed": passed,
            }
        )
    return {
        "case_count": len(results),
        "all_passed": all(row["passed"] for row in results) if results else None,
        "rows": results,
    }


def _sum_available(rows: Iterable[dict[str, Any]], key: str) -> int | None:
    values = [row.get(key) for row in rows if row.get(key) is not None]
    return sum(int(value) for value in values) if values else None


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    keys = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# P1 末端闭环 AirSim 批量报告",
        "",
        f"- Suite: `{payload['calibration_suite']}`",
        f"- Version: `{payload['calibration_suite_version']}`",
        f"- Cases/results: `{payload['case_count']}/{payload['result_count']}`",
        "- 运行方式：M5N2 与 tuned 2v2 各自一次启动 Blocks，组内按 case/seed reset。",
        "- 默认探测：AirSim detect；在线关联禁止使用 actor/truth ID。",
        "",
        "## 聚合结果",
        "",
        "| Family | Profile | Seeds | Connected | Pair | PairSuccess | Target | TargetSuccess | Coalition | CoalitionDone | IdentityTruth | StateTruth | PhysicalAvailable | ActualAvailable | Switch | Predicted | WindowExpired |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["aggregates"]:
        lines.append(
            "| {family} | {profile} | {seed_count} | {connected_count} | "
            "{pair_opportunity_count} | {pair_success_count} | {target_opportunity_count} | "
            "{target_success_count} | {coalition_opportunity_count} | "
            "{coalition_completion_count} | {truth_identity_online_use_count} | "
            "{truth_state_online_use_count} | {physical_metrics_available_count} | "
            "{actual_execution_available_count} | "
            "{terminal_switch_allowed_count} | {terminal_prediction_count} | "
            "{terminal_prediction_window_expired_count} |".format(**row)
        )
    paired = payload["m5n2_paired"]
    acceptance = payload["acceptance"]
    lines.extend(
        [
            "",
            "## 验收判读",
            "",
            f"- M5N2 paired seeds: `{paired.get('pair_count')}`",
            f"- Candidate target non-degradation: `{acceptance.get('candidate_target_non_degradation')}`",
            f"- Candidate pair non-degradation: `{acceptance.get('candidate_pair_non_degradation')}`",
            f"- Online truth use zero: `{acceptance.get('online_truth_use_zero')}`",
            f"- Truth identity online use zero/available: `{acceptance.get('truth_identity_online_use_zero')}`",
            f"- Truth state online use zero/available: `{acceptance.get('truth_state_online_use_zero')}`",
            f"- Physical metrics available for all cases: `{acceptance.get('physical_metrics_available')}`",
            f"- Canonical actual execution available for all cases: `{acceptance.get('actual_execution_all_available')}`",
            f"- All results present: `{acceptance.get('all_results_present')}`",
            f"- Dropout matrix passed: `{acceptance.get('dropout_matrix', {}).get('all_passed')}`",
            f"- Overall acceptance passed: `{acceptance.get('overall_acceptance_passed')}`",
            "",
            "本文件只给出 main 执行索引和基础分层结果；置信区间、失败原因分布和曲线由 D6 bundle 生成。",
            "",
        ]
    )
    return "\n".join(lines)
