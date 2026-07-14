"""Main-owned orchestration records for the P1 cooperative closure suite."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SUITE_NAME = "p1_cooperative_closure"
SUITE_VERSION = "p1-cooperative-closure-v2"
SCENARIO_VERSION = "airsim-m5n2-cooperative-high-clearance-v2"
THRESHOLD_VERSION = "p1-cooperative-thresholds-v2"


@dataclass(frozen=True)
class CooperativeCandidate:
    """One D3-screened cooperative timing and geometry profile."""

    candidate_id: str
    terminal_handoff_range_m: float
    primary_arrival_window_width_s: float
    approach_sector_separation_deg: float

    def __post_init__(self) -> None:
        if self.terminal_handoff_range_m <= 0.0:
            raise ValueError("terminal_handoff_range_m must be positive")
        if self.primary_arrival_window_width_s <= 0.0:
            raise ValueError("primary_arrival_window_width_s must be positive")
        if not 0.0 <= self.approach_sector_separation_deg < 180.0:
            raise ValueError("approach_sector_separation_deg must be in [0, 180)")

    def metadata(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CooperativeClosureCase:
    """One reset-separated M-to-N SimpleFlight cooperative case."""

    case_id: str
    profile: str
    seed: int
    resource_count: int
    target_count: int
    duration_s: float
    intercept_altitude_z: float
    candidate: CooperativeCandidate
    comparison_role: str = "candidate"

    def metadata(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "candidate": self.candidate.metadata(),
            "calibration_suite": SUITE_NAME,
            "calibration_suite_version": SUITE_VERSION,
            "scenario_version": SCENARIO_VERSION,
            "threshold_version": THRESHOLD_VERSION,
        }


def build_candidate_grid(
    *,
    terminal_handoff_ranges_m: Sequence[float] = (20.0, 30.0, 40.0),
    primary_arrival_window_widths_s: Sequence[float] = (3.0, 5.0, 8.0),
    approach_sector_separations_deg: Sequence[float] = (20.0, 40.0, 60.0),
) -> tuple[CooperativeCandidate, ...]:
    """Build the frozen 3x3x3 screening grid without scenario-size assumptions."""

    rows: list[CooperativeCandidate] = []
    for handoff_range in terminal_handoff_ranges_m:
        for window_width in primary_arrival_window_widths_s:
            for sector_separation in approach_sector_separations_deg:
                candidate_id = (
                    f"d3-p1-h{float(handoff_range):05.1f}"
                    f"-w{float(window_width):04.1f}"
                    f"-s{float(sector_separation):05.1f}"
                )
                rows.append(
                    CooperativeCandidate(
                        candidate_id=candidate_id,
                        terminal_handoff_range_m=float(handoff_range),
                        primary_arrival_window_width_s=float(window_width),
                        approach_sector_separation_deg=float(sector_separation),
                    )
                )
    return tuple(rows)


def select_screened_candidates(
    candidates: Iterable[CooperativeCandidate],
    screening_rows: Iterable[Mapping[str, Any]],
    *,
    limit: int = 3,
) -> tuple[CooperativeCandidate, ...]:
    """Select D3-screened candidates using the frozen lexicographic policy."""

    if limit <= 0:
        raise ValueError("limit must be positive")
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    ranked: list[tuple[tuple[Any, ...], CooperativeCandidate]] = []
    seen: set[str] = set()
    for raw in screening_rows:
        candidate_id = str(raw.get("candidate_id") or "")
        if candidate_id not in by_id:
            raise ValueError(f"unknown screening candidate_id: {candidate_id}")
        if candidate_id in seen:
            raise ValueError(f"duplicate screening candidate_id: {candidate_id}")
        seen.add(candidate_id)
        safety = _required_number(raw, "safety_violation_count")
        coalition = _required_number(raw, "coalition_completion_score")
        pair_success = _required_number(raw, "pair_success_score")
        arrival_spread = _required_number(raw, "arrival_spread_s")
        ranked.append(
            (
                (
                    0 if safety == 0.0 else 1,
                    safety,
                    -coalition,
                    -pair_success,
                    arrival_spread,
                    candidate_id,
                ),
                by_id[candidate_id],
            )
        )
    if set(by_id) != seen:
        missing = sorted(set(by_id) - seen)
        raise ValueError(f"screening rows missing candidates: {missing}")
    ranked.sort(key=lambda item: item[0])
    return tuple(candidate for _, candidate in ranked[:limit])


def run_pointmass_candidate_screen(
    candidates: Iterable[CooperativeCandidate],
    *,
    seeds: Iterable[int],
    target_range_m: float = 35.0,
    interceptor_speed_mps: float = 6.0,
    target_speed_mps: float = 1.2,
    intercept_radius_m: float = 5.0,
    minimum_member_separation_m: float = 2.0,
) -> list[dict[str, Any]]:
    """Pre-screen cooperative geometry with the existing D7 point-mass model."""

    import numpy as np
    from d7_proportional_guidance import (
        GuidanceConfig,
        GuidanceState,
        simulate_guidance_episode,
    )

    normalized_seeds = tuple(dict.fromkeys(int(seed) for seed in seeds))
    if not normalized_seeds:
        raise ValueError("at least one point-mass seed is required")
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        safety_violations = 0
        coalition_completions = 0
        pair_successes = 0
        arrival_spreads: list[float] = []
        for seed in normalized_seeds:
            target = GuidanceState(
                entity_id="TGT-001",
                timestamp_s=0.0,
                position_m=(target_range_m, 0.0),
                velocity_mps=(target_speed_mps, 0.2),
            )
            pair_records = []
            pair_summaries = []
            half_angle = math.radians(candidate.approach_sector_separation_deg / 2.0)
            for primary_index, signed_angle in enumerate((-half_angle, half_angle), start=1):
                relative = np.asarray(
                    [-target_range_m * math.cos(signed_angle), target_range_m * math.sin(signed_angle)],
                    dtype=float,
                )
                position = np.asarray(target.position_m, dtype=float) + relative
                direction = -relative / max(float(np.linalg.norm(relative)), 1e-9)
                pursuer = GuidanceState(
                    entity_id=f"INT-{primary_index:02d}",
                    timestamp_s=0.0,
                    position_m=(float(position[0]), float(position[1])),
                    velocity_mps=(
                        float(direction[0] * interceptor_speed_mps),
                        float(direction[1] * interceptor_speed_mps),
                    ),
                )
                records, summary = simulate_guidance_episode(
                    pursuer_initial=pursuer,
                    target_initial=target,
                    config=GuidanceConfig(
                        dt_s=0.1,
                        max_duration_s=35.0,
                        intercept_radius_m=intercept_radius_m,
                        terminal_switch_range_m=candidate.terminal_handoff_range_m,
                        max_lateral_accel_mps2=20.0,
                        max_turn_rate_radps=0.9,
                        radar_position_noise_m=0.25,
                        radar_velocity_noise_mps=0.05,
                        vision_los_noise_rad=0.002,
                        vision_range_noise_fraction=0.01,
                        random_seed=seed * 10 + primary_index,
                    ),
                    resource_id=pursuer.entity_id,
                    target_id=target.entity_id,
                )
                pair_records.append(records)
                pair_summaries.append(summary)
            successes = [bool(row.get("stopped_on_intercept_radius")) for row in pair_summaries]
            pair_successes += sum(successes)
            coalition_completions += int(all(successes))
            if all(successes):
                arrival_spread = abs(
                    float(pair_summaries[0]["duration_s"])
                    - float(pair_summaries[1]["duration_s"])
                )
                arrival_spreads.append(arrival_spread)
                if arrival_spread > candidate.primary_arrival_window_width_s:
                    safety_violations += 1
            common_steps = min(len(records) for records in pair_records)
            if common_steps:
                minimum_separation = min(
                    math.dist(
                        pair_records[0][index].pursuer_position_m,
                        pair_records[1][index].pursuer_position_m,
                    )
                    for index in range(common_steps)
                )
                if minimum_separation < minimum_member_separation_m:
                    safety_violations += 1
        coalition_opportunities = len(normalized_seeds)
        pair_opportunities = 2 * coalition_opportunities
        results.append(
            {
                "candidate_id": candidate.candidate_id,
                "safety_violation_count": safety_violations,
                "coalition_completion_score": coalition_completions / coalition_opportunities,
                "pair_success_score": pair_successes / pair_opportunities,
                "arrival_spread_s": (
                    sum(arrival_spreads) / len(arrival_spreads)
                    if arrival_spreads
                    else float("inf")
                ),
                "coalition_completion_count": coalition_completions,
                "coalition_opportunity_count": coalition_opportunities,
                "pair_success_count": pair_successes,
                "pair_opportunity_count": pair_opportunities,
                "evidence_source": "d7_offline_2d_point_mass",
                "online_truth_use_count": 0,
            }
        )
    return results


def build_cooperative_closure_cases(
    seeds: Iterable[int],
    selected_candidates: Iterable[CooperativeCandidate],
    *,
    resource_count: int = 5,
    target_count: int = 2,
    duration_s: float = 35.0,
    intercept_altitude_z: float = -30.0,
) -> tuple[CooperativeClosureCase, ...]:
    """Build one baseline plus the screened candidates for every seed."""

    normalized_seeds = tuple(dict.fromkeys(int(seed) for seed in seeds))
    if not normalized_seeds:
        raise ValueError("at least one seed is required")
    if resource_count <= 0 or target_count <= 0:
        raise ValueError("resource_count and target_count must be positive")
    selected = tuple(selected_candidates)
    if not selected:
        raise ValueError("at least one screened candidate is required")
    baseline = CooperativeCandidate(
        candidate_id="baseline_r30_w2_s0",
        terminal_handoff_range_m=30.0,
        primary_arrival_window_width_s=2.0,
        approach_sector_separation_deg=0.0,
    )
    cases: list[CooperativeClosureCase] = []
    for seed in normalized_seeds:
        cases.append(
            CooperativeClosureCase(
                case_id=f"baseline_seed{seed:03d}",
                profile="baseline",
                seed=seed,
                resource_count=resource_count,
                target_count=target_count,
                duration_s=duration_s,
                intercept_altitude_z=intercept_altitude_z,
                candidate=baseline,
                comparison_role="baseline",
            )
        )
        for candidate in selected:
            cases.append(
                CooperativeClosureCase(
                    case_id=f"{candidate.candidate_id}_seed{seed:03d}",
                    profile=candidate.candidate_id,
                    seed=seed,
                    resource_count=resource_count,
                    target_count=target_count,
                    duration_s=duration_s,
                    intercept_altitude_z=intercept_altitude_z,
                    candidate=candidate,
                )
            )
    return tuple(cases)


def build_pair_funnel_rows(
    case: CooperativeClosureCase,
    intercept_summary: Mapping[str, Any],
    command_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Flatten one episode into availability-aware pair funnel records."""

    commands = [dict(row) for row in command_rows]
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in commands:
        key = (str(row.get("resource_id") or ""), str(row.get("target_id") or ""))
        by_pair.setdefault(key, []).append(row)
    pairs = [row for row in intercept_summary.get("pairs", ()) if isinstance(row, Mapping)]
    result: list[dict[str, Any]] = []
    for raw_pair in pairs:
        pair = dict(raw_pair)
        resource_id = str(pair.get("resource_id") or "")
        target_id = str(pair.get("target_id") or "")
        selected = by_pair.get((resource_id, target_id), [])
        role = str(pair.get("member_role") or "")
        active_primary = role == "primary" and str(pair.get("activation_state")) == "active"
        assigned = bool(pair.get("assigned"))
        visible = _any_true(selected, "detection_seen")
        associated = any(str(row.get("d5_decision_state")) == "locked" for row in selected)
        contract_allowed = _any_true(selected, "terminal_contract_allowed")
        control_allowed = _any_true(selected, "terminal_control_allowed")
        mode_switched = any(
            str(row.get("mode") or "") == "vision_terminal" for row in selected
        )
        physical = bool(pair.get("physical_success"))
        first_failure_reason = _first_failure_reason(
            assigned=assigned,
            visible=visible,
            associated=associated,
            contract_allowed=contract_allowed,
            control_allowed=control_allowed,
            mode_switched=mode_switched,
            physical=physical,
            rows=selected,
            pair=pair,
        )
        result.append(
            {
                "case_id": case.case_id,
                "seed": case.seed,
                "profile": case.profile,
                "candidate_id": case.candidate.candidate_id,
                "resource_count": case.resource_count,
                "target_count": case.target_count,
                "resource_id": resource_id,
                "target_id": target_id,
                "member_role": role,
                "member_order": None,
                "active_primary": active_primary,
                "plan_id": pair.get("plan_id"),
                "plan_owner": pair.get("plan_owner_node_id"),
                "plan_version": pair.get("plan_version"),
                "coalition_id": pair.get("coalition_id"),
                "coalition_owner": pair.get("d4_target_node_id"),
                "coalition_version": pair.get("coalition_version"),
                "coalition_epoch": pair.get("coalition_epoch"),
                "assigned": assigned,
                "visible": visible,
                "associated": associated,
                "contract_allowed": contract_allowed,
                "control_allowed": control_allowed,
                "mode_switched": mode_switched,
                "physical_intercept": physical,
                "closest_range_m": _optional_number(pair.get("min_range_m")),
                "arrival_timestamp_s": _optional_number(pair.get("arrival_timestamp_s")),
                "arrival_error_s": _arrival_error(pair),
                "member_separation_m": _minimum_available(selected, "member_separation_m"),
                "common_lock_window_s": None,
                "common_lock_frame_count": None,
                "common_lock": None,
                "first_failure_reason": first_failure_reason,
                "reserve_unauthorized": bool(
                    role == "reserve"
                    and str(pair.get("activation_state")) != "active"
                    and (control_allowed or mode_switched or physical)
                ),
                "global_track_id_rewrite_count": int(
                    sum(_as_int(row.get("global_track_id_rewrite_count")) for row in selected)
                ),
                "online_truth_use_count": int(
                    bool(pair.get("online_truth_id_used"))
                    or any(_as_bool(row.get("truth_identity_online_use")) for row in selected)
                ),
            }
        )
    _annotate_common_lock_windows(result, by_pair)
    _annotate_member_order(result)
    return result


def summarize_cooperative_closure(
    cases: Iterable[CooperativeClosureCase],
    pair_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate pair, target and coalition layers without denominator mixing."""

    case_list = tuple(cases)
    rows = [dict(row) for row in pair_rows]
    profiles = sorted({str(row.get("profile")) for row in rows})
    aggregates: list[dict[str, Any]] = []
    for profile in profiles:
        selected = [row for row in rows if str(row.get("profile")) == profile]
        active = [row for row in selected if bool(row.get("active_primary"))]
        target_groups = _group_rows(active, ("seed", "target_id"))
        coalition_groups = {
            key: group
            for key, group in target_groups.items()
            if len(group) > 1
        }
        aggregates.append(
            {
                "profile": profile,
                "seed_count": len({row.get("seed") for row in selected}),
                "pair_opportunity_count": len(active),
                "pair_success_count": sum(bool(row.get("physical_intercept")) for row in active),
                "target_opportunity_count": len(target_groups),
                "target_success_count": sum(
                    any(bool(row.get("physical_intercept")) for row in group)
                    for group in target_groups.values()
                ),
                "coalition_opportunity_count": len(coalition_groups),
                "coalition_completion_count": sum(
                    all(bool(row.get("physical_intercept")) for row in group)
                    for group in coalition_groups.values()
                ),
                "funnel": {
                    field: sum(bool(row.get(field)) for row in active)
                    for field in (
                        "assigned",
                        "visible",
                        "associated",
                        "contract_allowed",
                        "control_allowed",
                        "mode_switched",
                        "physical_intercept",
                    )
                },
                "second_primary_failure_distribution": _failure_distribution(
                    _second_primary_rows(active)
                ),
                "common_lock_rate": _available_rate(active, "common_lock_frame_count", positive=True),
                "arrival_spread_mean_s": _available_mean(
                    _target_arrival_spreads(target_groups)
                ),
            }
        )
    candidate_aggregates = [row for row in aggregates if row["profile"] != "baseline"]
    best = max(
        candidate_aggregates,
        key=lambda row: (
            row["coalition_completion_count"],
            row["pair_success_count"],
            row["target_success_count"],
            row["profile"],
        ),
        default=None,
    )
    return {
        "calibration_suite": SUITE_NAME,
        "calibration_suite_version": SUITE_VERSION,
        "scenario_version": SCENARIO_VERSION,
        "threshold_version": THRESHOLD_VERSION,
        "case_count": len(case_list),
        "pair_row_count": len(rows),
        "cases": [case.metadata() for case in case_list],
        "pair_rows": rows,
        "aggregates": aggregates,
        "best_candidate_profile": None if best is None else best["profile"],
        "acceptance": {
            "all_cases_present": len({row.get("case_id") for row in rows}) == len(case_list),
            "coalition_completion_at_least_8_of_10": (
                None
                if best is None or best["seed_count"] < 10
                else best["coalition_completion_count"] >= 8
            ),
            "reserve_unauthorized_zero": not any(bool(row.get("reserve_unauthorized")) for row in rows),
            "global_track_id_rewrite_zero": sum(
                _as_int(row.get("global_track_id_rewrite_count")) for row in rows
            )
            == 0,
            "online_truth_use_zero": sum(
                _as_int(row.get("online_truth_use_count")) for row in rows
            )
            == 0,
        },
    }


def write_cooperative_closure_bundle(
    output_dir: str | Path,
    cases: Iterable[CooperativeClosureCase],
    pair_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = summarize_cooperative_closure(cases, pair_rows)
    json_path = output / "p1_cooperative_closure_summary.json"
    csv_path = output / "p1_cooperative_pair_funnel.csv"
    markdown_path = output / "P1_COOPERATIVE_CLOSURE_REPORT.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(csv_path, payload["pair_rows"])
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "markdown": markdown_path}


def _first_failure_reason(**kwargs: Any) -> str:
    stages = (
        ("assigned", "not_assigned"),
        ("visible", "not_visible"),
        ("associated", "not_associated"),
        ("contract_allowed", "contract_rejected"),
        ("control_allowed", "control_rejected"),
        ("mode_switched", "mode_not_switched"),
        ("physical", "physical_intercept_missed"),
    )
    rows = kwargs["rows"]
    pair = kwargs["pair"]
    for field, fallback in stages:
        if kwargs[field]:
            continue
        if field in {"contract_allowed", "control_allowed", "mode_switched"}:
            for row in rows:
                for key in (
                    "terminal_contract_reject_reason",
                    "terminal_switch_reject_reason",
                    "terminal_delivery_reason",
                ):
                    reason = str(row.get(key) or "")
                    if reason:
                        return reason
        reason = str(pair.get("abort_reason") or pair.get("terminal_switch_reject_reason") or "")
        return reason or fallback
    return "completed"


def _annotate_common_lock_windows(
    rows: list[dict[str, Any]],
    by_pair: Mapping[tuple[str, str], list[dict[str, Any]]],
) -> None:
    groups = _group_rows([row for row in rows if row["active_primary"]], ("target_id",))
    for group in groups.values():
        if len(group) < 2:
            continue
        timestamp_sets: list[set[float]] = []
        for row in group:
            commands = by_pair.get((row["resource_id"], row["target_id"]), [])
            timestamp_sets.append(
                {
                    float(command["timestamp_s"])
                    for command in commands
                    if str(command.get("d5_decision_state")) == "locked"
                    and command.get("timestamp_s") not in {None, ""}
                }
            )
        common = set.intersection(*timestamp_sets) if timestamp_sets else set()
        window = 0.0
        if common:
            ordered = sorted(common)
            window = ordered[-1] - ordered[0] if len(ordered) > 1 else 0.0
        for row in group:
            row["common_lock_window_s"] = window
            row["common_lock_frame_count"] = len(common)
            row["common_lock"] = bool(common)


def _annotate_member_order(rows: list[dict[str, Any]]) -> None:
    groups = _group_rows([row for row in rows if row["active_primary"]], ("target_id",))
    for group in groups.values():
        for order, row in enumerate(
            sorted(group, key=lambda item: str(item.get("resource_id"))), start=1
        ):
            row["member_order"] = order


def _arrival_error(pair: Mapping[str, Any]) -> float | None:
    timestamp = _optional_number(pair.get("arrival_timestamp_s"))
    window = pair.get("arrival_window")
    if timestamp is None or not isinstance(window, (list, tuple)) or len(window) != 2:
        return None
    start = _optional_number(window[0])
    end = _optional_number(window[1])
    if start is None or end is None:
        return None
    if start <= timestamp <= end:
        return 0.0
    return start - timestamp if timestamp < start else timestamp - end


def _second_primary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = _group_rows(rows, ("seed", "target_id"))
    selected: list[dict[str, Any]] = []
    for group in groups.values():
        primaries = sorted(group, key=lambda row: str(row.get("resource_id")))
        if len(primaries) > 1:
            selected.append(primaries[1])
    return selected


def _target_arrival_spreads(
    groups: Mapping[tuple[Any, ...], list[dict[str, Any]]],
) -> list[float]:
    values: list[float] = []
    for group in groups.values():
        timestamps = [
            _optional_number(row.get("arrival_timestamp_s"))
            for row in group
            if row.get("arrival_timestamp_s") is not None
        ]
        available = [value for value in timestamps if value is not None]
        if len(available) > 1:
            values.append(max(available) - min(available))
    return values


def _failure_distribution(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("first_failure_reason") or "unavailable")
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _group_rows(
    rows: Iterable[dict[str, Any]], keys: tuple[str, ...]
) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(tuple(row.get(key) for key in keys), []).append(row)
    return grouped


def _available_rate(
    rows: Iterable[Mapping[str, Any]], field: str, *, positive: bool = False
) -> float | None:
    values = [row.get(field) for row in rows if row.get(field) is not None]
    if not values:
        return None
    passed = sum(float(value) > 0.0 if positive else bool(value) for value in values)
    return passed / len(values)


def _available_mean(values: Iterable[float]) -> float | None:
    items = [float(value) for value in values if math.isfinite(float(value))]
    return None if not items else sum(items) / len(items)


def _minimum_available(rows: Iterable[Mapping[str, Any]], field: str) -> float | None:
    values = [_optional_number(row.get(field)) for row in rows]
    available = [value for value in values if value is not None]
    return None if not available else min(available)


def _any_true(rows: Iterable[Mapping[str, Any]], field: str) -> bool:
    return any(_as_bool(row.get(field)) for row in rows)


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _optional_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _required_number(row: Mapping[str, Any], field: str) -> float:
    value = _optional_number(row.get(field))
    if value is None:
        raise ValueError(f"screening row missing finite {field}")
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row}) or ["case_id"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# P1 M5N2 协同物理闭环报告",
        "",
        f"- Suite: `{payload['calibration_suite_version']}`",
        f"- Cases: `{payload['case_count']}`",
        f"- Best candidate: `{payload.get('best_candidate_profile')}`",
        "",
        "## 分层结果",
        "",
        "| Profile | Pair | Target | Coalition | Common lock |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in payload.get("aggregates", ()):
        common = row.get("common_lock_rate")
        lines.append(
            "| {profile} | {pair_success_count}/{pair_opportunity_count} | "
            "{target_success_count}/{target_opportunity_count} | "
            "{coalition_completion_count}/{coalition_opportunity_count} | {common} |".format(
                **row,
                common="unavailable" if common is None else f"{common:.3f}",
            )
        )
    lines.extend(["", "## 验收", ""])
    for key, value in payload.get("acceptance", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"
