"""Passive M-to-N cooperative-interception metric aggregation.

This module only interprets recorded evidence.  It never creates assignments,
changes coalition membership, or fills missing operational evidence.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence


M_TO_N_METRIC_NAMES = (
    "target_demand_satisfaction_rate_micro",
    "target_demand_satisfaction_rate_macro",
    "unmet_slot_count",
    "over_support_count",
    "coalition_formation_time_s",
    "coalition_reconfiguration_time_s",
    "simultaneous_arrival_dispersion_s",
    "common_window_success_rate",
    "wave_interval_s",
    "wave_order_violation_count",
    "primary_success_rate",
    "reserve_activation_count",
    "reserve_activation_rate",
    "reserve_activation_latency_s",
    "planned_cooperative_lock_count",
    "planned_cooperative_lock_success_rate",
    "authorized_cooperative_lock_count",
    "erroneous_duplicate_lock_count",
    "same_resource_lock_continuity_count",
    "replan_request_count",
    "replan_request_deduplicated_count",
    "replan_no_change_ack_count",
    "replan_applied_count",
    "replan_expired_count",
    "replan_pending_dwell_s",
    "replan_convergence_time_s",
    "coalition_commit_count",
    "coalition_required_member_count",
    "coalition_acked_member_count",
    "coalition_member_ack_rate",
    "coalition_ack_latency_s",
    "coalition_commit_timeout_count",
    "coalition_commit_aborted_count",
    "coalition_commit_reconfiguring_count",
    "coalition_commit_lease_expired_count",
    "secondary_coalition_commit_count",
    "distributed_coalition_commit_count",
    "coalition_member_loss_count",
    "coalition_member_replacement_count",
    "coalition_member_replacement_time_s",
    "coalition_digest_conflict_count",
    "coalition_stale_rejection_count",
    "coalition_stale_rejection_rate",
    "messages_sent_count",
    "messages_delivered_count",
    "messages_dropped_count",
    "payload_bytes_sent",
    "payload_bytes_delivered",
    "coalition_consensus_rounds",
    "end_to_end_latency_ms",
    "minimum_member_separation_m",
    "collision_risk_exposure_s",
    "geometry_rejection_count",
    "geometry_rejection_rate",
    "canonical_duplicate_count",
    "cross_node_id_switch_count",
    "common_information_duplicate_rejection_count",
    "common_information_duplicate_rejection_rate",
)

_EFFECTIVE_AUTHORIZATION_STATES = {
    "recorded",
    "authorized",
    "approved",
    "human_approved",
    "operator_approved",
    "activated",
    "executing",
}
_CURRENT_COALITION_STATES = {
    "committed",
    "active",
    "executing",
    "reconfigured",
    "complete",
    "completed",
}
_LOCK_STATES = {"locked", "lock", "terminal_lock"}
_RESERVE_ROLES = {"reserve", "observer"}
_REPLAN_EVENT_TYPES = {
    "center_replan_request_created",
    "center_replan_request_deduplicated",
    "center_replan_ack_no_change",
    "center_replan_applied",
    "center_replan_expired",
}
_REPLAN_RESOLVED_EVENT_TYPES = {
    "center_replan_ack_no_change",
    "center_replan_applied",
    "center_replan_expired",
}
_REPLAN_CONVERGED_EVENT_TYPES = {
    "center_replan_ack_no_change",
    "center_replan_applied",
}


def compute_m_to_n_metrics(
    *,
    demand_records: Sequence[Any],
    coalition_records: Sequence[Any],
    arrival_records: Sequence[Any],
    assignment_records: Sequence[Any],
    terminal_records: Sequence[Any],
    event_records: Sequence[Any],
    link_records: Sequence[Any],
) -> tuple[dict[str, float | int | None], dict[str, Any]]:
    """Compute episode metrics and per-metric evidence availability."""

    metrics: dict[str, float | int | None] = {
        name: None for name in M_TO_N_METRIC_NAMES
    }
    availability: dict[str, dict[str, Any]] = {}

    def record(
        name: str,
        value: float | int | None,
        *,
        status: str,
        reason: str,
        numerator: float | int | None = None,
        denominator: float | int | None = None,
    ) -> None:
        metrics[name] = value
        availability[name] = {
            "status": status,
            "reason": reason,
            "numerator": numerator,
            "denominator": denominator,
        }

    valid_demands = [
        item
        for item in demand_records
        if getattr(item, "evidence_available", True) is not False
        and _positive_int(getattr(item, "required_resource_count", None)) is not None
    ]
    _compute_demand_metrics(record, valid_demands, assignment_records, event_records)
    _compute_coalition_timing_metrics(record, valid_demands, coalition_records)
    modes = _coordination_modes(
        valid_demands, coalition_records, arrival_records, assignment_records
    )
    _compute_arrival_metrics(record, valid_demands, arrival_records, modes)
    _compute_hybrid_metrics(
        record,
        valid_demands,
        assignment_records,
        terminal_records,
        event_records,
        modes,
    )

    duplicate_assignment_count = count_illegal_assignments(
        assignment_records, valid_demands, coalition_records, event_records
    )
    (
        planned_locks,
        authorized_cooperative_locks,
        erroneous_locks,
        same_resource_continuity,
        lock_denominator,
        lock_evidence,
        duplicate_lock_evidence,
    ) = _lock_metrics(
        terminal_records,
        assignment_records,
        valid_demands,
        coalition_records,
        event_records,
    )
    if lock_evidence:
        record(
            "planned_cooperative_lock_count",
            planned_locks,
            status="available",
            reason="current coalition and assignment authorization were recorded",
            numerator=planned_locks,
            denominator=lock_denominator,
        )
        record(
            "planned_cooperative_lock_success_rate",
            planned_locks / lock_denominator if lock_denominator else None,
            status="available" if lock_denominator else "unavailable",
            reason=(
                "authorized cooperative lock opportunities were recorded"
                if lock_denominator
                else "no authorized cooperative lock opportunity"
            ),
            numerator=planned_locks,
            denominator=lock_denominator,
            )
        record(
            "authorized_cooperative_lock_count",
            authorized_cooperative_locks,
            status="available",
            reason="same-frame multi-resource locks were inside current coalition authorization and target demand",
            numerator=authorized_cooperative_locks,
        )
    else:
        for name in (
            "planned_cooperative_lock_count",
            "planned_cooperative_lock_success_rate",
            "authorized_cooperative_lock_count",
        ):
            record(
                name,
                None,
                status="unavailable",
                reason="cooperative assignment/coalition authorization evidence is absent",
            )
    record(
        "erroneous_duplicate_lock_count",
        erroneous_locks if duplicate_lock_evidence else None,
        status="available" if duplicate_lock_evidence else "unavailable",
        reason=(
            "legacy k=1 or explicit coalition authorization was applied"
            if duplicate_lock_evidence
            else "terminal lock evidence is absent"
        ),
        numerator=erroneous_locks if duplicate_lock_evidence else None,
    )
    record(
        "same_resource_lock_continuity_count",
        same_resource_continuity if duplicate_lock_evidence else None,
        status="available" if duplicate_lock_evidence else "unavailable",
        reason=(
            "continued locks were counted across distinct timestamps per target and resource"
            if duplicate_lock_evidence
            else "terminal lock evidence is absent"
        ),
        numerator=same_resource_continuity if duplicate_lock_evidence else None,
    )

    replan_audit = _compute_replan_metrics(record, event_records)
    coalition_commit_audit = _compute_coalition_commit_metrics(
        record,
        coalition_records,
        event_records,
    )
    _compute_member_metrics(record, coalition_records, event_records)
    _compute_communication_metrics(record, coalition_records, link_records)
    _compute_safety_geometry_identity_metrics(record, arrival_records, event_records)

    return metrics, {
        "m_to_n_status": "available" if any(
            item["status"] == "available" for item in availability.values()
        ) else "unavailable",
        "m_to_n_metric_availability": availability,
        "m_to_n_duplicate_assignment_count": duplicate_assignment_count,
        "m_to_n_record_counts": {
            "target_demand": len(demand_records),
            "coalition": len(coalition_records),
            "arrival": len(arrival_records),
        },
        "coordination_modes": sorted(modes),
        "replan_event_audit": replan_audit,
        **coalition_commit_audit,
    }


def count_illegal_assignments(
    assignment_records: Sequence[Any],
    demand_records: Sequence[Any],
    coalition_records: Sequence[Any],
    event_records: Sequence[Any] = (),
) -> int:
    """Count only assignments exceeding current coalition authorization.

    Historical rows without M-to-N fields use the explicit legacy contract
    ``k=1``.  Cooperative rows are legal only inside one current coalition and
    up to the recorded target demand.
    """

    active = [
        item
        for item in assignment_records
        if getattr(item, "active", True)
        and _state(getattr(item, "authorization_state", "recorded"))
        in _EFFECTIVE_AUTHORIZATION_STATES
    ]
    snapshots: dict[tuple[float, str, int, str], list[Any]] = defaultdict(list)
    for item in active:
        target = _assignment_target(item)
        if target is None:
            continue
        snapshots[
            (
                float(getattr(item, "timestamp")),
                str(getattr(item, "plan_id", "")),
                int(getattr(item, "version", 0)),
                target,
            )
        ].append(item)

    illegal = 0
    for (timestamp, _, _, target), rows in snapshots.items():
        required = _required_count(target, timestamp, rows, demand_records)
        current_identity = _current_coalition_identity(
            target, timestamp, rows, coalition_records
        )
        unique_rows: dict[str, Any] = {}
        for row in rows:
            unique_rows.setdefault(str(getattr(row, "resource_id")), row)

        legal_members = 0
        for row in unique_rows.values():
            identity = _coalition_identity(row)
            if current_identity is not None and identity != current_identity:
                illegal += 1
            elif current_identity is None and identity is not None:
                # One self-consistent coalition can establish current identity
                # without a separate lifecycle row; conflicting identities cannot.
                identities = {
                    candidate
                    for candidate in (_coalition_identity(item) for item in rows)
                    if candidate is not None
                }
                if len(identities) > 1:
                    illegal += 1
                else:
                    legal_members += 1
            else:
                legal_members += 1
        illegal += max(legal_members - required, 0)
    illegal += sum(
        1
        for item in event_records
        if _event_type(item)
        in {"duplicate_assignment", "illegal_duplicate_assignment"}
        or bool(getattr(item, "metadata", {}).get("duplicate_assignment"))
    )
    return illegal


def _compute_demand_metrics(record: Any, demands: Sequence[Any], assignments: Sequence[Any], events: Sequence[Any]) -> None:
    if not demands:
        for name in (
            "target_demand_satisfaction_rate_micro",
            "target_demand_satisfaction_rate_macro",
            "unmet_slot_count",
            "over_support_count",
        ):
            record(name, None, status="unavailable", reason="target demand evidence is absent")
        return

    required_total = 0
    satisfied_total = 0
    complete_total = 0
    unmet_total = 0
    over_total = 0
    for demand in demands:
        required = _positive_int(getattr(demand, "required_resource_count", None)) or 1
        assigned = _optional_int(getattr(demand, "demand_assigned", None))
        if assigned is None:
            assigned = _assigned_execution_count(demand, assignments, events)
        shortfall = _optional_int(getattr(demand, "demand_shortfall", None))
        if shortfall is None:
            shortfall = max(required - assigned, 0)
        complete = getattr(demand, "demand_complete", None)
        if complete is None:
            complete = shortfall == 0
        required_total += required
        satisfied_total += min(assigned, required)
        complete_total += int(bool(complete))
        unmet_total += max(shortfall, 0)
        over_total += max(assigned - required, 0)

    record(
        "target_demand_satisfaction_rate_micro",
        satisfied_total / required_total,
        status="available",
        reason="target demand and assigned execution slots were recorded",
        numerator=satisfied_total,
        denominator=required_total,
    )
    record(
        "target_demand_satisfaction_rate_macro",
        complete_total / len(demands),
        status="available",
        reason="target-complete demand snapshots were recorded",
        numerator=complete_total,
        denominator=len(demands),
    )
    record("unmet_slot_count", unmet_total, status="available", reason="demand shortfall was recorded or derived from assignments", numerator=unmet_total)
    record("over_support_count", over_total, status="available", reason="demand and assigned execution slots were recorded", numerator=over_total)


def _compute_coalition_timing_metrics(record: Any, demands: Sequence[Any], coalitions: Sequence[Any]) -> None:
    if not coalitions:
        for name in ("coalition_formation_time_s", "coalition_reconfiguration_time_s"):
            record(name, None, status="unavailable", reason="coalition lifecycle evidence is absent")
        return

    demand_start = {
        str(getattr(item, "global_track_id")): float(getattr(item, "timestamp"))
        for item in demands
    }
    grouped: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for item in coalitions:
        grouped[(str(getattr(item, "global_track_id")), str(getattr(item, "coalition_id")))].append(item)

    formation: list[float] = []
    reconfiguration: list[float] = []
    for (target, _), rows in grouped.items():
        ordered = sorted(rows, key=lambda item: float(getattr(item, "timestamp")))
        committed = [
            item for item in ordered
            if _state(getattr(item, "coalition_state", "")) in _CURRENT_COALITION_STATES
        ]
        if committed:
            start = min(
                [demand_start[target]] if target in demand_start else []
                + [
                    float(getattr(item, "timestamp"))
                    for item in ordered
                    if _state(getattr(item, "coalition_state", "")) in {"proposed", "forming", "requested"}
                ]
            ) if (target in demand_start or any(_state(getattr(item, "coalition_state", "")) in {"proposed", "forming", "requested"} for item in ordered)) else None
            if start is not None and float(getattr(committed[0], "timestamp")) >= start:
                formation.append(float(getattr(committed[0], "timestamp")) - start)
        for item in committed:
            trigger = _optional_float(getattr(item, "trigger_timestamp", None))
            if trigger is not None and float(getattr(item, "timestamp")) >= trigger:
                reconfiguration.append(float(getattr(item, "timestamp")) - trigger)

    record(
        "coalition_formation_time_s",
        _mean_or_none(formation),
        status="available" if formation else "unavailable",
        reason="formation start and committed timestamps were recorded" if formation else "formation start/commit pair is incomplete",
        numerator=sum(formation) if formation else None,
        denominator=len(formation) if formation else None,
    )
    record(
        "coalition_reconfiguration_time_s",
        _mean_or_none(reconfiguration),
        status="available" if reconfiguration else "unavailable",
        reason="trigger and new committed-version timestamps were recorded" if reconfiguration else "reconfiguration trigger/commit pair is incomplete",
        numerator=sum(reconfiguration) if reconfiguration else None,
        denominator=len(reconfiguration) if reconfiguration else None,
    )


def _compute_arrival_metrics(record: Any, demands: Sequence[Any], arrivals: Sequence[Any], modes: set[str]) -> None:
    simultaneous = [item for item in arrivals if _state(getattr(item, "coordination_mode", "")) == "simultaneous"]
    if "simultaneous" not in modes:
        for name in ("simultaneous_arrival_dispersion_s", "common_window_success_rate"):
            record(name, None, status="not_applicable", reason="coordination mode is not simultaneous")
    elif not simultaneous:
        for name in ("simultaneous_arrival_dispersion_s", "common_window_success_rate"):
            record(name, None, status="unavailable", reason="simultaneous arrival evidence is absent")
    else:
        groups: dict[tuple[str, str, int, str], list[Any]] = defaultdict(list)
        for item in simultaneous:
            if _state(getattr(item, "member_role", "primary")) in _RESERVE_ROLES:
                continue
            groups[
                (
                    str(getattr(item, "global_track_id")),
                    str(getattr(item, "coalition_id", "")),
                    int(getattr(item, "coalition_version", 0) or 0),
                    str(getattr(item, "wave_id", "")),
                )
            ].append(item)
        dispersions: list[float] = []
        successes = 0
        opportunities = 0
        for rows in groups.values():
            times = [
                _optional_float(getattr(item, "arrival_timestamp", None))
                for item in rows
                if getattr(item, "arrived", True)
            ]
            times = [value for value in times if value is not None]
            required = _positive_int(getattr(rows[0], "required_resource_count", None)) or len(rows)
            if len(times) >= required and required > 1:
                dispersion = max(times) - min(times)
                dispersions.append(dispersion)
            bounds = [_window_bounds(item) for item in rows]
            starts = [start for start, _ in bounds]
            ends = [end for _, end in bounds]
            if any(value is not None for value in starts + ends):
                opportunities += 1
                successes += int(
                    len(times) >= required
                    and all(
                        (start is None or time >= start) and (end is None or time <= end)
                        for time, start, end in zip(times, starts, ends)
                    )
                )
        record(
            "simultaneous_arrival_dispersion_s",
            _mean_or_none(dispersions),
            status="available" if dispersions else "unavailable",
            reason="all required primary arrival timestamps were recorded" if dispersions else "required primary arrivals are incomplete",
            numerator=sum(dispersions) if dispersions else None,
            denominator=len(dispersions) if dispersions else None,
        )
        record(
            "common_window_success_rate",
            successes / opportunities if opportunities else None,
            status="available" if opportunities else "unavailable",
            reason="assigned common windows and arrivals were recorded" if opportunities else "assigned common-window evidence is absent",
            numerator=successes,
            denominator=opportunities,
        )

    sequential = [item for item in arrivals if _state(getattr(item, "coordination_mode", "")) == "sequential"]
    if "sequential" not in modes:
        for name in ("wave_interval_s", "wave_order_violation_count"):
            record(name, None, status="not_applicable", reason="coordination mode is not sequential")
    elif not sequential:
        for name in ("wave_interval_s", "wave_order_violation_count"):
            record(name, None, status="unavailable", reason="sequential wave evidence is absent")
    else:
        groups: dict[tuple[str, str, int], dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
        for item in sequential:
            groups[(str(getattr(item, "global_track_id")), str(getattr(item, "coalition_id", "")), int(getattr(item, "coalition_version", 0) or 0))][str(getattr(item, "wave_id", ""))].append(item)
        intervals: list[float] = []
        violations = 0
        comparisons = 0
        for waves in groups.values():
            ordered = sorted(waves.values(), key=lambda rows: min(_arrival_time(item) for item in rows))
            for previous, current in zip(ordered, ordered[1:]):
                previous_complete = max(_wave_complete_time(item) for item in previous)
                current_start = min(_wave_start_time(item) for item in current)
                intervals.append(current_start - previous_complete)
                comparisons += 1
                violations += int(current_start < previous_complete)
        record("wave_interval_s", _mean_or_none(intervals), status="available" if intervals else "unavailable", reason="adjacent wave start/completion timestamps were recorded" if intervals else "fewer than two evidenced waves", numerator=sum(intervals) if intervals else None, denominator=len(intervals) if intervals else None)
        record("wave_order_violation_count", violations if comparisons else None, status="available" if comparisons else "unavailable", reason="adjacent wave ordering was evaluated" if comparisons else "fewer than two evidenced waves", numerator=violations, denominator=comparisons or None)


def _compute_hybrid_metrics(record: Any, demands: Sequence[Any], assignments: Sequence[Any], terminals: Sequence[Any], events: Sequence[Any], modes: set[str]) -> None:
    names = ("primary_success_rate", "reserve_activation_count", "reserve_activation_rate", "reserve_activation_latency_s")
    if "hybrid_primary_reserve" not in modes and "hybrid" not in modes:
        for name in names:
            record(name, None, status="not_applicable", reason="coordination mode has no primary/reserve policy")
        return
    primary_assignments = [item for item in assignments if _state(getattr(item, "member_role", "")) == "primary" and getattr(item, "active", True)]
    primary_locks = {
        (str(getattr(item, "resource_id")), str(getattr(item, "assigned_global_track_id", "")))
        for item in terminals
        if _state(getattr(item, "decision_state", "")) in _LOCK_STATES
        and _state(getattr(item, "member_role", "")) == "primary"
    }
    primary_opportunities = len({(str(getattr(item, "resource_id")), _assignment_target(item)) for item in primary_assignments})
    primary_success = sum(1 for item in primary_assignments if (str(getattr(item, "resource_id")), str(_assignment_target(item) or "")) in primary_locks)
    record("primary_success_rate", primary_success / primary_opportunities if primary_opportunities else None, status="available" if primary_opportunities else "unavailable", reason="primary assignment and completion evidence was recorded" if primary_opportunities else "primary assignment evidence is absent", numerator=primary_success, denominator=primary_opportunities or None)

    reserve_assignments = [item for item in assignments if _state(getattr(item, "member_role", "")) == "reserve" and getattr(item, "active", True)]
    activations = [item for item in events if _event_type(item) in {"reserve_activated", "reserve_activation", "reserve_member_activated"}]
    record("reserve_activation_count", len(activations), status="available", reason="hybrid route event stream was evaluated", numerator=len(activations), denominator=len(reserve_assignments))
    record("reserve_activation_rate", len(activations) / len(reserve_assignments) if reserve_assignments else None, status="available" if reserve_assignments else "unavailable", reason="reserve assignment opportunities were recorded" if reserve_assignments else "reserve assignment evidence is absent", numerator=len(activations), denominator=len(reserve_assignments) or None)
    latencies = []
    for item in activations:
        trigger = _metadata_float(getattr(item, "metadata", {}), "trigger_timestamp")
        if trigger is None:
            trigger = _metadata_float(getattr(item, "metadata", {}), "reserve_hold_timestamp")
        if trigger is not None and float(getattr(item, "timestamp")) >= trigger:
            latencies.append(float(getattr(item, "timestamp")) - trigger)
    record("reserve_activation_latency_s", _mean_or_none(latencies), status="available" if latencies else "unavailable", reason="reserve trigger and activation timestamps were recorded" if latencies else "reserve activation trigger timestamp is absent", numerator=sum(latencies) if latencies else None, denominator=len(latencies) if latencies else None)


def _lock_metrics(
    terminals: Sequence[Any],
    assignments: Sequence[Any],
    demands: Sequence[Any],
    coalitions: Sequence[Any],
    events: Sequence[Any],
) -> tuple[int, int, int, int, int, bool, bool]:
    locks = [
        item
        for item in terminals
        if _state(getattr(item, "decision_state", "")) in _LOCK_STATES
    ]
    groups: dict[tuple[float, str], list[Any]] = defaultdict(list)
    continuity_timestamps: dict[tuple[str, str], set[float]] = defaultdict(set)
    for item in locks:
        target = getattr(item, "assigned_global_track_id", None) or getattr(
            item, "expected_global_track_id", None
        )
        if target is None:
            continue
        timestamp = float(getattr(item, "timestamp"))
        resource_id = str(getattr(item, "resource_id"))
        groups[(timestamp, str(target))].append(item)
        continuity_timestamps[(str(target), resource_id)].add(timestamp)

    planned = 0
    authorized_cooperative = 0
    erroneous = 0
    cooperative_evidence = False
    denominator = 0
    for (timestamp, target), rows in groups.items():
        candidates = _current_assignment_candidates(assignments, target, timestamp)
        required = _required_count(target, timestamp, list(rows) + candidates, demands)
        current = _current_coalition_identity(
            target, timestamp, candidates or rows, coalitions
        )
        unique_locks = {
            str(getattr(item, "resource_id")): item for item in rows
        }
        authorized_locks: list[Any] = []
        version_conflict_count = 0
        for resource_id, lock in unique_locks.items():
            matching = [
                item
                for item in candidates
                if str(getattr(item, "resource_id")) == resource_id
            ]
            authorized = any(
                _lock_matches_assignment(lock, item, current) for item in matching
            )
            has_coalition_contract = (
                getattr(lock, "coalition_id", None) is not None
                or any(getattr(item, "coalition_id", None) is not None for item in matching)
            )
            if not matching and getattr(lock, "coalition_id", None) is not None:
                authorized = (
                    _state(getattr(lock, "authorization_state", "recorded"))
                    in _EFFECTIVE_AUTHORIZATION_STATES
                    and (current is None or _coalition_identity(lock) == current)
                    and _resource_is_current_coalition_member(
                        resource_id, target, timestamp, current, coalitions
                    )
                )
            elif not matching:
                # Historical terminal logs have no coalition contract, so their
                # explicit compatibility requirement is k=1 per frame/target.
                authorized = True

            cooperative_evidence = cooperative_evidence or has_coalition_contract
            if authorized:
                authorized_locks.append(lock)
            elif _lock_has_version_conflict(lock, matching, current):
                version_conflict_count += 1

        legal_locks = authorized_locks[:required]
        if len(unique_locks) > 1:
            erroneous += version_conflict_count
            erroneous += max(len(authorized_locks) - required, 0)
        planned += sum(
            getattr(lock, "coalition_id", None) is not None
            or any(
                getattr(item, "coalition_id", None) is not None
                for item in candidates
                if str(getattr(item, "resource_id"))
                == str(getattr(lock, "resource_id"))
            )
            for lock in legal_locks
        )

        if required > 1 and len(legal_locks) > 1:
            authorized_cooperative += len(legal_locks)
        if cooperative_evidence:
            authorized_resources = {
                str(getattr(item, "resource_id"))
                for item in candidates
                if current is None or _coalition_identity(item) == current
            }
            denominator += min(required, len(authorized_resources))

    same_resource_continuity = sum(
        max(len(timestamps) - 1, 0)
        for timestamps in continuity_timestamps.values()
    )
    duplicate_events = [
        item
        for item in events
        if _event_type(item)
        in {"duplicate_terminal_lock", "terminal_duplicate_lock"}
        or bool(getattr(item, "metadata", {}).get("duplicate_terminal_lock"))
    ]
    if not locks:
        # Legacy event-only duplicate evidence carries the historical k=1
        # interpretation. Terminal rows, when present, are authoritative and
        # prevent event/row double counting.
        erroneous += len(duplicate_events)
    return (
        planned,
        authorized_cooperative,
        erroneous,
        same_resource_continuity,
        denominator,
        cooperative_evidence,
        bool(locks or duplicate_events),
    )


def _compute_replan_metrics(record: Any, events: Sequence[Any]) -> list[dict[str, Any]]:
    replan_events = [item for item in events if _event_type(item) in _REPLAN_EVENT_TYPES]
    metric_names = (
        "replan_request_count",
        "replan_request_deduplicated_count",
        "replan_no_change_ack_count",
        "replan_applied_count",
        "replan_expired_count",
        "replan_pending_dwell_s",
        "replan_convergence_time_s",
    )
    if not replan_events:
        for name in metric_names:
            record(
                name,
                None,
                status="unavailable",
                reason="center replan lifecycle evidence is absent",
            )
        return []

    type_counts = {
        event_type: sum(_event_type(item) == event_type for item in replan_events)
        for event_type in _REPLAN_EVENT_TYPES
    }
    count_metrics = {
        "replan_request_count": "center_replan_request_created",
        "replan_request_deduplicated_count": "center_replan_request_deduplicated",
        "replan_no_change_ack_count": "center_replan_ack_no_change",
        "replan_applied_count": "center_replan_applied",
        "replan_expired_count": "center_replan_expired",
    }
    for metric_name, event_type in count_metrics.items():
        value = type_counts[event_type]
        record(
            metric_name,
            value,
            status="available",
            reason="center replan lifecycle event stream was evaluated",
            numerator=value,
        )

    created_at: dict[str, float] = {}
    for item in sorted(replan_events, key=lambda event: float(getattr(event, "timestamp"))):
        if _event_type(item) != "center_replan_request_created":
            continue
        request_id = _metadata_text(getattr(item, "metadata", {}), "request_id")
        if request_id is None:
            continue
        requested_at = _metadata_float(getattr(item, "metadata", {}), "requested_at")
        created_at.setdefault(
            request_id,
            requested_at if requested_at is not None else float(getattr(item, "timestamp")),
        )

    pending_dwells: list[float] = []
    convergence_times: list[float] = []
    audit: list[dict[str, Any]] = []
    audit_keys = (
        "request_id",
        "target_id",
        "coalition_id",
        "coalition_version",
        "risk_signature",
        "requested_at",
        "resolved_at",
        "pending_dwell_s",
        "resolved_plan_id",
        "resolved_plan_version",
    )
    for item in sorted(replan_events, key=lambda event: float(getattr(event, "timestamp"))):
        event_type = _event_type(item)
        metadata = getattr(item, "metadata", {})
        audit.append(
            {
                "event_type": event_type,
                "timestamp": float(getattr(item, "timestamp")),
                **{
                    key: metadata[key]
                    for key in audit_keys
                    if isinstance(metadata, Mapping) and key in metadata
                },
            }
        )
        if event_type not in _REPLAN_RESOLVED_EVENT_TYPES:
            continue
        request_id = _metadata_text(metadata, "request_id")
        requested_at = _metadata_float(metadata, "requested_at")
        if requested_at is None and request_id is not None:
            requested_at = created_at.get(request_id)
        resolved_at = _metadata_float(metadata, "resolved_at")
        if resolved_at is None:
            resolved_at = float(getattr(item, "timestamp"))
        pending_dwell = _metadata_float(metadata, "pending_dwell_s")
        if pending_dwell is None and requested_at is not None:
            pending_dwell = resolved_at - requested_at
        if pending_dwell is not None and pending_dwell >= 0.0:
            pending_dwells.append(pending_dwell)
        if (
            event_type in _REPLAN_CONVERGED_EVENT_TYPES
            and requested_at is not None
            and resolved_at >= requested_at
        ):
            convergence_times.append(resolved_at - requested_at)

    record(
        "replan_pending_dwell_s",
        sum(pending_dwells) if pending_dwells else None,
        status="available" if pending_dwells else "unavailable",
        reason=(
            "resolved/expired replans provided pending dwell evidence"
            if pending_dwells
            else "resolved replan pending dwell or timestamp pair is absent"
        ),
        numerator=sum(pending_dwells) if pending_dwells else None,
        denominator=len(pending_dwells) if pending_dwells else None,
    )
    record(
        "replan_convergence_time_s",
        _mean_or_none(convergence_times),
        status="available" if convergence_times else "unavailable",
        reason=(
            "created requests converged through no-change acknowledgement or applied plan"
            if convergence_times
            else "no complete created-to-no-change/applied lifecycle pair"
        ),
        numerator=sum(convergence_times) if convergence_times else None,
        denominator=len(convergence_times) if convergence_times else None,
    )
    return audit


def _compute_coalition_commit_metrics(
    record: Any,
    coalitions: Sequence[Any],
    events: Sequence[Any],
) -> dict[str, Any]:
    """Aggregate D4 atomic-commit evidence without double-counting transitions."""

    snapshots = [
        snapshot
        for item in list(coalitions) + list(events)
        for snapshot in [_coalition_commit_snapshot(item)]
        if snapshot is not None
    ]
    metric_names = (
        "coalition_commit_count",
        "coalition_required_member_count",
        "coalition_acked_member_count",
        "coalition_member_ack_rate",
        "coalition_ack_latency_s",
        "coalition_commit_timeout_count",
        "coalition_commit_aborted_count",
        "coalition_commit_reconfiguring_count",
        "coalition_commit_lease_expired_count",
        "secondary_coalition_commit_count",
        "distributed_coalition_commit_count",
    )
    if not snapshots:
        for name in metric_names:
            record(
                name,
                None,
                status="unavailable",
                reason="D4 coalition commit lifecycle evidence is absent",
            )
        return {
            "coalition_commit_state_counts": {},
            "coalition_commit_reason_counts": {},
            "coalition_commit_audit": [],
        }

    unique_snapshots: dict[tuple[Any, ...], dict[str, Any]] = {}
    for snapshot in snapshots:
        key = (
            snapshot["generation"],
            snapshot["timestamp"],
            snapshot["state"],
            tuple(snapshot["acked_member_ids"]),
            snapshot["reason"],
        )
        unique_snapshots.setdefault(key, snapshot)
    snapshots = sorted(
        unique_snapshots.values(),
        key=lambda item: (item["timestamp"], item["generation"]),
    )

    by_generation: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        by_generation[snapshot["generation"]].append(snapshot)

    required_total = 0
    acked_total = 0
    committed_generations = 0
    secondary_commits = 0
    distributed_commits = 0
    aborted = 0
    reconfiguring = 0
    timeouts = 0
    lease_expired = 0
    ack_latencies: list[float] = []
    state_counts: dict[str, int] = defaultdict(int)
    reason_counts: dict[str, int] = defaultdict(int)

    for generation_snapshots in by_generation.values():
        latest = max(generation_snapshots, key=lambda item: item["timestamp"])
        required_total += len(latest["required_member_ids"])
        acked_total += len(latest["acked_member_ids"])
        states = {item["state"] for item in generation_snapshots}
        reasons = {item["reason"] for item in generation_snapshots if item["reason"]}
        committed = bool(states & {"committed", "executing"})
        committed_generations += int(committed)
        fallback_mode = next(
            (
                item["fallback_mode"]
                for item in reversed(generation_snapshots)
                if item["fallback_mode"]
            ),
            "",
        )
        secondary_commits += int(committed and fallback_mode == "secondary")
        distributed_commits += int(committed and fallback_mode == "distributed")
        aborted += int("aborted" in states)
        reconfiguring += int("reconfiguring" in states)
        timeouts += int(
            any("timeout" in reason or "timed_out" in reason for reason in reasons)
            or any(item["timed_out"] for item in generation_snapshots)
        )
        lease_expired += int(
            any(
                ("lease" in reason and "expir" in reason)
                for reason in reasons
            )
            or any(item["lease_expired"] for item in generation_snapshots)
        )
        if committed:
            latency = next(
                (
                    item["ack_latency_s"]
                    for item in generation_snapshots
                    if item["ack_latency_s"] is not None
                ),
                None,
            )
            if latency is None:
                commit_times = [
                    item["committed_at"]
                    for item in generation_snapshots
                    if item["committed_at"] is not None
                ]
                proposal_times = [
                    item["proposed_at"]
                    for item in generation_snapshots
                    if item["proposed_at"] is not None
                ]
                if commit_times and proposal_times:
                    latency = min(commit_times) - min(proposal_times)
            if latency is not None and latency >= 0.0:
                ack_latencies.append(latency)

    for snapshot in snapshots:
        state_counts[snapshot["state"]] += 1
        if snapshot["reason"]:
            reason_counts[snapshot["reason"]] += 1

    count_values = {
        "coalition_commit_count": committed_generations,
        "coalition_required_member_count": required_total,
        "coalition_acked_member_count": acked_total,
        "coalition_commit_timeout_count": timeouts,
        "coalition_commit_aborted_count": aborted,
        "coalition_commit_reconfiguring_count": reconfiguring,
        "coalition_commit_lease_expired_count": lease_expired,
        "secondary_coalition_commit_count": secondary_commits,
        "distributed_coalition_commit_count": distributed_commits,
    }
    for name, value in count_values.items():
        record(
            name,
            value,
            status="available",
            reason="D4 coalition commit generations were evaluated",
            numerator=value,
        )
    record(
        "coalition_member_ack_rate",
        acked_total / required_total if required_total else None,
        status="available" if required_total else "unavailable",
        reason=(
            "required and acknowledged coalition members were recorded"
            if required_total
            else "required coalition member denominator is absent"
        ),
        numerator=acked_total,
        denominator=required_total or None,
    )
    record(
        "coalition_ack_latency_s",
        _mean_or_none(ack_latencies),
        status="available" if ack_latencies else "unavailable",
        reason=(
            "proposal-to-complete-ACK timestamps were recorded"
            if ack_latencies
            else "complete proposal/ACK timestamp pairs are absent"
        ),
        numerator=sum(ack_latencies) if ack_latencies else None,
        denominator=len(ack_latencies) if ack_latencies else None,
    )
    return {
        "coalition_commit_state_counts": dict(state_counts),
        "coalition_commit_reason_counts": dict(reason_counts),
        "coalition_commit_audit": snapshots,
    }


def _coalition_commit_snapshot(item: Any) -> dict[str, Any] | None:
    metadata = getattr(item, "metadata", {})
    metadata = metadata if isinstance(metadata, Mapping) else {}
    is_event = hasattr(item, "event_type")
    if is_event and _event_type(item) != "d4_coalition_commit_state":
        return None
    commit_state = (
        getattr(item, "commit_state", None)
        or metadata.get("coalition_commit_state")
        or metadata.get("commit_state")
        or (metadata.get("state") if is_event else None)
    )
    epoch = getattr(item, "epoch", None)
    if epoch is None:
        epoch = metadata.get("coalition_commit_epoch", metadata.get("epoch"))
    required = _string_tuple(
        getattr(item, "required_member_ids", ())
        or metadata.get("coalition_required_member_ids")
        or metadata.get("required_member_ids")
    )
    acked = _string_tuple(
        getattr(item, "acked_member_ids", ())
        or metadata.get("coalition_acked_member_ids")
        or metadata.get("acked_member_ids")
    )
    if not is_event and commit_state is None and epoch is None and not required and not acked:
        return None
    state = _state(commit_state or getattr(item, "coalition_state", ""))
    if not state:
        return None
    timestamp = float(getattr(item, "timestamp"))
    track_id = str(
        getattr(item, "global_track_id", "")
        or metadata.get("global_track_id")
        or metadata.get("target_id")
        or ""
    )
    coalition_id = str(
        getattr(item, "coalition_id", "") or metadata.get("coalition_id") or ""
    )
    coalition_version = _optional_int(
        getattr(item, "coalition_version", None)
        if getattr(item, "coalition_version", None) is not None
        else metadata.get("coalition_version")
    )
    plan_id = str(
        getattr(item, "plan_id", "") or metadata.get("plan_id") or ""
    )
    plan_version = _optional_int(
        getattr(item, "plan_version", None)
        if getattr(item, "plan_version", None) is not None
        else metadata.get("plan_version")
    )
    epoch_value = _optional_int(epoch)
    reason = str(
        getattr(item, "commit_reason", "")
        or metadata.get("coalition_commit_reason")
        or metadata.get("reason")
        or getattr(item, "note", "")
        or ""
    ).strip()
    lease_expires_at = _first_optional_float(
        getattr(item, "lease_expires_at", None),
        metadata.get("coalition_lease_expires_at"),
        metadata.get("lease_expires_at"),
    )
    lease_valid = metadata.get("coalition_lease_valid", metadata.get("lease_valid"))
    fallback_mode = _state(
        metadata.get("fallback_mode")
        or metadata.get("coalition_commit_mode")
        or getattr(item, "coordinator_role", "")
        or metadata.get("coordinator_role")
        or metadata.get("coalition_commit_coordinator_role")
    )
    if "secondary" in fallback_mode:
        fallback_mode = "secondary"
    elif fallback_mode in {"distributed", "interceptor_peer", "peer"}:
        fallback_mode = "distributed"
    return {
        "timestamp": timestamp,
        "generation": (
            track_id,
            coalition_id,
            coalition_version,
            plan_id,
            plan_version,
            epoch_value,
        ),
        "global_track_id": track_id,
        "coalition_id": coalition_id,
        "coalition_version": coalition_version,
        "plan_id": plan_id,
        "plan_version": plan_version,
        "epoch": epoch_value,
        "state": state,
        "reason": reason,
        "required_member_ids": required,
        "acked_member_ids": acked,
        "lease_expires_at": lease_expires_at,
        "fallback_mode": fallback_mode,
        "proposed_at": _first_optional_float(
            getattr(item, "proposed_at", None), metadata.get("proposed_at")
        ),
        "committed_at": _first_optional_float(
            getattr(item, "committed_at", None), metadata.get("committed_at")
        ),
        "ack_latency_s": _first_optional_float(
            getattr(item, "ack_latency_s", None), metadata.get("ack_latency_s")
        ),
        "timed_out": bool(metadata.get("timed_out", metadata.get("timeout", False))),
        "lease_expired": bool(lease_valid is False)
        or bool(lease_expires_at is not None and timestamp >= lease_expires_at),
    }


def _compute_member_metrics(record: Any, coalitions: Sequence[Any], events: Sequence[Any]) -> None:
    evidence = bool(coalitions) or any(_event_type(item).startswith(("coalition_", "member_", "stale_")) for item in events)
    if not evidence:
        for name in ("coalition_member_loss_count", "coalition_member_replacement_count", "coalition_member_replacement_time_s", "coalition_digest_conflict_count", "coalition_stale_rejection_count", "coalition_stale_rejection_rate"):
            record(name, None, status="unavailable", reason="coalition member lifecycle evidence is absent")
        return
    all_items = list(coalitions) + list(events)
    states = [_event_type(item) if hasattr(item, "event_type") else _state(getattr(item, "coalition_state", "")) for item in all_items]
    losses = sum(state in {"member_lost", "coalition_member_lost"} for state in states)
    replacements = sum(state in {"member_replaced", "coalition_member_replaced", "replacement_committed"} for state in states)
    digests = sum(state in {"coalition_digest_conflict", "digest_conflict"} for state in states)
    stale_detected = sum(state in {"stale_message_detected", "stale_plan_detected", "coalition_stale_detected"} for state in states)
    stale_rejected = sum(state in {"stale_message_rejected", "stale_plan_rejected", "coalition_stale_rejected", "stale_rejected"} for state in states)
    stale_detected = max(stale_detected, stale_rejected)
    replacement_times = []
    for item in all_items:
        metadata = getattr(item, "metadata", {})
        trigger = getattr(item, "trigger_timestamp", None)
        if trigger is None:
            trigger = _metadata_float(metadata, "member_loss_timestamp")
        if trigger is not None and (_event_type(item) if hasattr(item, "event_type") else _state(getattr(item, "coalition_state", ""))) in {"member_replaced", "coalition_member_replaced", "replacement_committed", "reconfigured"}:
            replacement_times.append(float(getattr(item, "timestamp")) - float(trigger))
    for name, value in (("coalition_member_loss_count", losses), ("coalition_member_replacement_count", replacements), ("coalition_digest_conflict_count", digests), ("coalition_stale_rejection_count", stale_rejected)):
        record(name, value, status="available", reason="coalition lifecycle event stream was evaluated", numerator=value)
    record("coalition_member_replacement_time_s", _mean_or_none(replacement_times), status="available" if replacement_times else "unavailable", reason="member-loss and replacement timestamps were recorded" if replacement_times else "no complete loss/replacement timestamp pair")
    record("coalition_stale_rejection_rate", stale_rejected / stale_detected if stale_detected else None, status="available" if stale_detected else "unavailable", reason="detected stale opportunities were recorded" if stale_detected else "stale detection denominator is absent", numerator=stale_rejected, denominator=stale_detected or None)


def _compute_communication_metrics(record: Any, coalitions: Sequence[Any], links: Sequence[Any]) -> None:
    aggregate_evidence = any(getattr(item, "messages_sent", None) is not None for item in coalitions)
    if not links and not aggregate_evidence:
        for name in ("messages_sent_count", "messages_delivered_count", "messages_dropped_count", "payload_bytes_sent", "payload_bytes_delivered", "coalition_consensus_rounds", "end_to_end_latency_ms"):
            record(name, None, status="unavailable", reason="coalition communication evidence is absent")
        return
    sent = (
        len(links)
        if links
        else sum(_optional_int(getattr(item, "messages_sent", None)) or 0 for item in coalitions)
    )
    delivered = (
        sum(bool(getattr(item, "delivered", True)) for item in links)
        if links
        else sum(_optional_int(getattr(item, "messages_delivered", None)) or 0 for item in coalitions)
    )
    dropped = sent - delivered
    bytes_sent_values = (
        [_metadata_float(getattr(item, "metadata", {}), "payload_bytes") for item in links]
        if links
        else [_optional_float(getattr(item, "payload_bytes_sent", None)) for item in coalitions]
    )
    known_bytes = [value for value in bytes_sent_values if value is not None]
    delivered_bytes = (
        sum(
            value
            for item, value in zip(links, bytes_sent_values)
            if value is not None and getattr(item, "delivered", True)
        )
        if links
        else sum(
            _optional_float(getattr(item, "payload_bytes_delivered", None)) or 0.0
            for item in coalitions
        )
    )
    rounds = [_optional_float(getattr(item, "consensus_rounds", None)) for item in coalitions]
    rounds = [value for value in rounds if value is not None]
    latencies = []
    for item in links:
        sent_time = _optional_float(getattr(item, "sent_timestamp", None))
        received_time = _optional_float(getattr(item, "received_timestamp", None))
        if sent_time is not None and received_time is not None:
            latencies.append((received_time - sent_time) * 1000.0)
    if not latencies:
        latencies += [value for item in coalitions for value in [_optional_float(getattr(item, "latency_ms", None))] if value is not None]
    for name, value in (("messages_sent_count", sent), ("messages_delivered_count", delivered), ("messages_dropped_count", dropped)):
        record(name, value, status="available", reason="coalition communication stream was recorded", numerator=value)
    record("payload_bytes_sent", sum(known_bytes) if known_bytes else None, status="available" if known_bytes else "unavailable", reason="payload byte counts were recorded" if known_bytes else "message sizes are absent")
    record("payload_bytes_delivered", delivered_bytes if known_bytes else None, status="available" if known_bytes else "unavailable", reason="delivered payload byte counts were recorded" if known_bytes else "message sizes are absent")
    record("coalition_consensus_rounds", sum(rounds) if rounds else None, status="available" if rounds else "unavailable", reason="coalition consensus rounds were recorded" if rounds else "consensus round evidence is absent")
    record("end_to_end_latency_ms", _mean_or_none(latencies), status="available" if latencies else "unavailable", reason="sent/received timestamps were recorded" if latencies else "complete sent/received timestamp pairs are absent")


def _compute_safety_geometry_identity_metrics(record: Any, arrivals: Sequence[Any], events: Sequence[Any]) -> None:
    separations = [_optional_float(getattr(item, "minimum_member_separation", None)) for item in arrivals]
    separations += [_metadata_float(getattr(item, "metadata", {}), "minimum_member_separation") for item in events]
    separations += [_metadata_float(getattr(item, "metadata", {}), "minimum_member_separation_m") for item in events]
    separations = [value for value in separations if value is not None]
    record("minimum_member_separation_m", min(separations) if separations else None, status="available" if separations else "unavailable", reason="member separation samples were recorded" if separations else "member position/separation evidence is absent")
    exposure = [_metadata_float(getattr(item, "metadata", {}), "collision_risk_exposure_s") for item in events]
    exposure = [value for value in exposure if value is not None]
    record("collision_risk_exposure_s", sum(exposure) if exposure else None, status="available" if exposure else "unavailable", reason="collision-risk exposure intervals were recorded" if exposure else "collision-risk exposure evidence is absent")

    geometry_events = [item for item in events if _event_type(item) in {"geometry_evaluated", "geometry_update", "geometry_rejected", "geometry_rejection"} or "geometry_rejected" in getattr(item, "metadata", {})]
    rejected = sum(_event_type(item) in {"geometry_rejected", "geometry_rejection"} or bool(getattr(item, "metadata", {}).get("geometry_rejected")) for item in geometry_events)
    record("geometry_rejection_count", rejected if geometry_events else None, status="available" if geometry_events else "unavailable", reason="geometry evaluation stream was recorded" if geometry_events else "geometry evaluation evidence is absent", numerator=rejected, denominator=len(geometry_events) or None)
    record("geometry_rejection_rate", rejected / len(geometry_events) if geometry_events else None, status="available" if geometry_events else "unavailable", reason="geometry evaluation opportunities were recorded" if geometry_events else "geometry evaluation denominator is absent", numerator=rejected, denominator=len(geometry_events) or None)

    canonical_events = [item for item in events if _event_type(item) in {"canonical_registry_snapshot", "canonical_duplicate", "canonical_duplicate_detected"}]
    canonical_count = sum((_metadata_float(getattr(item, "metadata", {}), "canonical_duplicate_count") or int(_event_type(item) in {"canonical_duplicate", "canonical_duplicate_detected"})) for item in canonical_events)
    record("canonical_duplicate_count", int(canonical_count) if canonical_events else None, status="available" if canonical_events else "unavailable", reason="truth/adjudicated canonical identity evidence was recorded" if canonical_events else "truth/adjudicated canonical identity evidence is absent")
    cross_switch = [item for item in events if _event_type(item) in {"cross_node_id_switch", "canonical_id_switch"}]
    record("cross_node_id_switch_count", len(cross_switch) if canonical_events or cross_switch else None, status="available" if canonical_events or cross_switch else "unavailable", reason="namespace-aware canonical identity stream was recorded" if canonical_events or cross_switch else "cross-node identity lineage evidence is absent")
    duplicate_opportunities = [item for item in events if _event_type(item) in {"common_information_duplicate", "common_information_duplicate_rejected", "duplicate_payload_opportunity"}]
    duplicate_rejected = sum(_event_type(item) == "common_information_duplicate_rejected" or bool(getattr(item, "metadata", {}).get("duplicate_rejected")) for item in duplicate_opportunities)
    record("common_information_duplicate_rejection_count", duplicate_rejected if duplicate_opportunities else None, status="available" if duplicate_opportunities else "unavailable", reason="lineage-backed duplicate payload opportunities were recorded" if duplicate_opportunities else "message UUID/source lineage evidence is absent", numerator=duplicate_rejected, denominator=len(duplicate_opportunities) or None)
    record("common_information_duplicate_rejection_rate", duplicate_rejected / len(duplicate_opportunities) if duplicate_opportunities else None, status="available" if duplicate_opportunities else "unavailable", reason="lineage-backed duplicate payload opportunities were recorded" if duplicate_opportunities else "duplicate payload denominator is absent", numerator=duplicate_rejected, denominator=len(duplicate_opportunities) or None)


def _assigned_execution_count(demand: Any, assignments: Sequence[Any], events: Sequence[Any]) -> int:
    target = str(getattr(demand, "global_track_id"))
    timestamp = float(getattr(demand, "timestamp"))
    active = []
    for item in assignments:
        if _assignment_target(item) != target or not getattr(item, "active", True):
            continue
        if float(getattr(item, "timestamp")) != timestamp:
            continue
        role = _state(getattr(item, "member_role", "primary"))
        if role in _RESERVE_ROLES and not _reserve_is_activated(item, events):
            continue
        active.append(str(getattr(item, "resource_id")))
    return len(set(active))


def _reserve_is_activated(item: Any, events: Sequence[Any]) -> bool:
    if _state(getattr(item, "coalition_state", "")) in {"activated", "executing"}:
        return True
    resource = str(getattr(item, "resource_id"))
    target = _assignment_target(item)
    return any(
        _event_type(event) in {"reserve_activated", "reserve_activation", "reserve_member_activated"}
        and str(getattr(event, "actor_id", "") or getattr(event, "metadata", {}).get("resource_id", "")) == resource
        and (target is None or str(getattr(event, "metadata", {}).get("global_track_id", target)) == target)
        for event in events
    )


def _required_count(target: str, timestamp: float, rows: Sequence[Any], demands: Sequence[Any]) -> int:
    explicit = [_positive_int(getattr(item, "required_resource_count", None)) for item in rows]
    explicit = [value for value in explicit if value is not None]
    if explicit:
        return max(explicit)
    candidates = [item for item in demands if str(getattr(item, "global_track_id")) == target and float(getattr(item, "timestamp")) <= timestamp]
    if candidates:
        latest = max(candidates, key=lambda item: float(getattr(item, "timestamp")))
        return _positive_int(getattr(latest, "required_resource_count", None)) or 1
    return 1


def _current_assignment_candidates(
    assignments: Sequence[Any],
    target: str,
    timestamp: float,
) -> list[Any]:
    latest_by_resource: dict[str, Any] = {}
    for item in assignments:
        if (
            _assignment_target(item) != target
            or not getattr(item, "active", True)
            or float(getattr(item, "timestamp")) > timestamp
        ):
            continue
        resource_id = str(getattr(item, "resource_id"))
        previous = latest_by_resource.get(resource_id)
        if previous is None or (
            float(getattr(item, "timestamp")), int(getattr(item, "version", 0))
        ) > (
            float(getattr(previous, "timestamp")),
            int(getattr(previous, "version", 0)),
        ):
            latest_by_resource[resource_id] = item
    return list(latest_by_resource.values())


def _resource_is_current_coalition_member(
    resource_id: str,
    target: str,
    timestamp: float,
    current: tuple[str, int] | None,
    coalitions: Sequence[Any],
) -> bool:
    candidates = [
        item
        for item in coalitions
        if str(getattr(item, "global_track_id")) == target
        and float(getattr(item, "timestamp")) <= timestamp
        and _state(getattr(item, "coalition_state", ""))
        in _CURRENT_COALITION_STATES
        and (current is None or _coalition_identity(item) == current)
    ]
    if not candidates:
        return False
    latest = max(
        candidates,
        key=lambda item: (
            int(getattr(item, "coalition_version", 0) or 0),
            float(getattr(item, "timestamp")),
        ),
    )
    return resource_id in {
        str(member_id) for member_id in getattr(latest, "member_ids", ())
    }


def _current_coalition_identity(target: str, timestamp: float, rows: Sequence[Any], coalitions: Sequence[Any]) -> tuple[str, int] | None:
    candidates = [item for item in coalitions if str(getattr(item, "global_track_id")) == target and float(getattr(item, "timestamp")) <= timestamp and _state(getattr(item, "coalition_state", "")) in _CURRENT_COALITION_STATES]
    if candidates:
        latest = max(candidates, key=lambda item: (int(getattr(item, "coalition_version", 0) or 0), float(getattr(item, "timestamp"))))
        return _coalition_identity(latest)
    identities = {_coalition_identity(item) for item in rows if _coalition_identity(item) is not None}
    return next(iter(identities)) if len(identities) == 1 else None


def _lock_matches_assignment(lock: Any, assignment: Any, current: tuple[str, int] | None) -> bool:
    if _state(getattr(assignment, "authorization_state", "recorded")) not in _EFFECTIVE_AUTHORIZATION_STATES:
        return False
    assignment_version = getattr(lock, "assignment_version", None)
    if assignment_version is not None and int(assignment_version) != int(getattr(assignment, "version", 0)):
        return False
    for field in ("coalition_id", "coalition_version", "member_role", "wave_id"):
        lock_value = getattr(lock, field, None)
        assignment_value = getattr(assignment, field, None)
        if lock_value is not None and assignment_value is not None and str(lock_value) != str(assignment_value):
            return False
    return current is None or _coalition_identity(assignment) == current


def _lock_has_version_conflict(
    lock: Any,
    assignments: Sequence[Any],
    current: tuple[str, int] | None,
) -> bool:
    lock_identity = _coalition_identity(lock)
    if current is not None and lock_identity is not None and lock_identity != current:
        return True
    assignment_version = getattr(lock, "assignment_version", None)
    if assignment_version is not None and assignments:
        return all(
            int(assignment_version) != int(getattr(item, "version", 0))
            for item in assignments
        )
    return current is not None and bool(assignments) and all(
        _coalition_identity(item) != current for item in assignments
    )


def _coordination_modes(*collections: Sequence[Any]) -> set[str]:
    return {
        _state(getattr(item, "coordination_mode", ""))
        for collection in collections
        for item in collection
        if getattr(item, "coordination_mode", None)
    }


def _coalition_identity(item: Any) -> tuple[str, int] | None:
    coalition_id = getattr(item, "coalition_id", None)
    if coalition_id is None:
        return None
    return str(coalition_id), int(getattr(item, "coalition_version", 0) or 0)


def _assignment_target(item: Any) -> str | None:
    target = getattr(item, "global_track_id", None) or getattr(item, "truth_id", None)
    return None if target is None else str(target)


def _arrival_time(item: Any) -> float:
    return _optional_float(getattr(item, "arrival_timestamp", None)) or float(getattr(item, "timestamp"))


def _window_bounds(item: Any) -> tuple[float | None, float | None]:
    start = _optional_float(getattr(item, "arrival_window_start", None))
    end = _optional_float(getattr(item, "arrival_window_end", None))
    raw = getattr(item, "arrival_window", None)
    if raw is not None and not isinstance(raw, (str, bytes)):
        values = list(raw)
        if len(values) >= 2:
            start = start if start is not None else _optional_float(values[0])
            end = end if end is not None else _optional_float(values[1])
    return start, end


def _wave_start_time(item: Any) -> float:
    return _optional_float(getattr(item, "wave_start_timestamp", None)) or _arrival_time(item)


def _wave_complete_time(item: Any) -> float:
    return _optional_float(getattr(item, "wave_complete_timestamp", None)) or _arrival_time(item)


def _event_type(item: Any) -> str:
    return _state(getattr(item, "event_type", ""))


def _state(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _positive_int(value: Any) -> int | None:
    result = _optional_int(value)
    return result if result is not None and result > 0 else None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_optional_float(*values: Any) -> float | None:
    for value in values:
        parsed = _optional_float(value)
        if parsed is not None:
            return parsed
    return None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None or isinstance(value, (str, bytes)):
        values = () if value is None else (value,)
    else:
        try:
            values = tuple(value)
        except TypeError:
            values = (value,)
    result: list[str] = []
    for item in values:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _metadata_float(metadata: Mapping[str, Any], key: str) -> float | None:
    return _optional_float(metadata.get(key)) if isinstance(metadata, Mapping) else None


def _metadata_text(metadata: Mapping[str, Any], key: str) -> str | None:
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _mean_or_none(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None
