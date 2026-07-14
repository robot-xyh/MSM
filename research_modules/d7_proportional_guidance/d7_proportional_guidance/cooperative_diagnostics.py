"""Passive M-to-N cooperative-guidance diagnostics and candidate pre-screening.

This module consumes D7 runtime outputs plus physical episode evidence.  It
does not select assignments, grant terminal authority, or compute guidance
commands.  Candidate parameters are carried only as D3-authored experiment
metadata so that a main orchestrator can compare equivalent runs.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from .models import GuidanceMode
from .runtime_bus import D7RuntimePairOutput


COOPERATIVE_GUIDANCE_DIAGNOSTIC_BOUNDARY = (
    "d7_passive_diagnostic_only_no_assignment_no_gate_bypass_no_vehicle_control"
)


@dataclass(frozen=True)
class CooperativeGuidanceCandidateMetadata:
    """D3-authored candidate parameters carried through D7 diagnostics."""

    candidate_id: str
    terminal_handoff_range_m: float
    primary_arrival_window_width_s: float
    approach_sector_separation_deg: float
    minimum_member_separation_m: float | None = None
    source: str = "d3"
    schema: str = "d3_cooperative_prescreen_v1"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must not be empty")
        if not self.source.strip() or not self.schema.strip():
            raise ValueError("candidate source and schema must not be empty")
        if self.terminal_handoff_range_m <= 0.0:
            raise ValueError("terminal_handoff_range_m must be positive")
        if self.primary_arrival_window_width_s <= 0.0:
            raise ValueError("primary_arrival_window_width_s must be positive")
        if not 0.0 <= self.approach_sector_separation_deg < 180.0:
            raise ValueError("approach_sector_separation_deg must be in [0, 180)")
        if (
            self.minimum_member_separation_m is not None
            and self.minimum_member_separation_m < 0.0
        ):
            raise ValueError("minimum_member_separation_m must be nonnegative")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CooperativeGuidanceDiagnosticSample:
    """One passive diagnostic sample for one assignment pair."""

    timestamp_s: float
    assignment_id: str
    resource_id: str
    target_id: str
    candidate: CooperativeGuidanceCandidateMetadata
    plan_id: str
    plan_version: int
    episode_id: str = ""
    seed: int | None = None
    coalition_id: str | None = None
    coalition_version: int | None = None
    member_role: str = "primary"
    activation_state: str = "active"
    assigned: bool = True
    active: bool = True
    mode: str = GuidanceMode.RADAR_MIDCOURSE.value
    guidance_law: str = "radar_pn"
    radar_midcourse_active: bool = True
    reacquisition_active: bool = False
    d5_visible: bool = True
    d5_associated: bool = True
    d5_locked: bool = True
    terminal_contract_allowed: bool = False
    terminal_control_allowed: bool = False
    terminal_mode_entered: bool = False
    physical_intercept: bool = False
    intercept_radius_m: float = 5.0
    range_m: float | None = None
    closing_speed_mps: float | None = None
    member_separation_m: float | None = None
    arrival_window_start_s: float | None = None
    arrival_window_end_s: float | None = None
    terminal_contract_reject_reason: str = ""
    terminal_control_reject_reason: str = ""
    terminal_delivery_state: str = ""
    terminal_delivery_reason: str = ""
    terminal_prediction_age_s: float | None = None
    ttc_reject_reason: str = ""
    disturbance_type: str = ""
    safety_violation: bool = False
    owner_mismatch: bool = False
    version_mismatch: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_runtime_output(
        cls,
        output: D7RuntimePairOutput,
        *,
        candidate: CooperativeGuidanceCandidateMetadata | Mapping[str, Any],
        physical_intercept: bool = False,
        range_m: float | None = None,
        closing_speed_mps: float | None = None,
        member_separation_m: float | None = None,
        reacquisition_active: bool | None = None,
        disturbance_type: str = "",
        safety_violation: bool = False,
        episode_id: str | None = None,
        seed: int | None = None,
        assigned: bool = True,
        active: bool | None = None,
        d5_visible: bool | None = None,
        d5_associated: bool | None = None,
        d5_locked: bool | None = None,
        intercept_radius_m: float = 5.0,
        owner_mismatch: bool | None = None,
        version_mismatch: bool | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "CooperativeGuidanceDiagnosticSample":
        """Adapt an existing runtime output without changing its gate result."""

        candidate_metadata = coerce_cooperative_guidance_candidate(candidate)
        output_metadata = dict(output.metadata)
        explicit_reacquisition = output_metadata.get("midcourse_reacquisition_active")
        if reacquisition_active is None:
            reacquisition_active = bool(
                output.mode == GuidanceMode.REACQUIRE
                or explicit_reacquisition is True
                or output.guidance_law == "pure_pursuit"
            )
        resolved_range = range_m
        if resolved_range is None:
            resolved_range = output.range_3d_m
        if resolved_range is None:
            resolved_range = output.terminal_range_m
        resolved_closing = (
            closing_speed_mps
            if closing_speed_mps is not None
            else output.closing_speed_mps
        )
        explicit_metadata = dict(metadata or {})
        resolved_episode_id = str(
            episode_id
            if episode_id is not None
            else explicit_metadata.get(
                "episode_id",
                output_metadata.get("episode_id", output_metadata.get("case_id", "")),
            )
        )
        resolved_seed = seed
        if resolved_seed is None:
            raw_seed = explicit_metadata.get("seed", output_metadata.get("seed"))
            resolved_seed = None if raw_seed is None else int(raw_seed)
        resolved_active = (
            output.activation_state == "active" if active is None else bool(active)
        )
        resolved_visible = _runtime_d5_visible(output, output_metadata) if d5_visible is None else bool(d5_visible)
        resolved_associated = (
            _runtime_d5_associated(output, output_metadata)
            if d5_associated is None
            else bool(d5_associated)
        )
        resolved_locked = (
            output.d5_decision_state == "locked" and output.d5_lock_consistent is not False
            if d5_locked is None
            else bool(d5_locked)
        )
        resolved_owner_mismatch = (
            _runtime_owner_mismatch(output)
            if owner_mismatch is None
            else bool(owner_mismatch)
        )
        resolved_version_mismatch = (
            _runtime_version_mismatch(output)
            if version_mismatch is None
            else bool(version_mismatch)
        )
        control_reason = (
            output.ttc_reject_reason
            or output.terminal_switch_reject_reason
            or output.raw_terminal_switch_reject_reason
            or output.terminal_delivery_reason
        )
        return cls(
            timestamp_s=output.timestamp_s,
            assignment_id=output.assignment_id or output.control_context_id,
            resource_id=output.resource_id,
            target_id=output.assigned_global_track_id,
            candidate=candidate_metadata,
            plan_id=output.plan_id,
            plan_version=output.plan_version,
            episode_id=resolved_episode_id,
            seed=resolved_seed,
            coalition_id=output.coalition_id,
            coalition_version=output.coalition_version,
            member_role=output.member_role,
            activation_state=output.activation_state,
            assigned=bool(assigned),
            active=resolved_active,
            mode=output.mode.value,
            guidance_law=output.guidance_law,
            radar_midcourse_active=output.guidance_law in {"radar_pn", "pn"}
            or output.mode == GuidanceMode.RADAR_MIDCOURSE,
            reacquisition_active=bool(reacquisition_active),
            d5_visible=resolved_visible,
            d5_associated=resolved_associated,
            d5_locked=resolved_locked,
            terminal_contract_allowed=output.terminal_contract_allowed,
            terminal_control_allowed=output.terminal_switch_allowed,
            terminal_mode_entered=output.terminal_mode_entered
            or output.mode == GuidanceMode.VISION_TERMINAL,
            physical_intercept=physical_intercept,
            intercept_radius_m=float(intercept_radius_m),
            range_m=resolved_range,
            closing_speed_mps=resolved_closing,
            member_separation_m=member_separation_m,
            arrival_window_start_s=output.arrival_window_start_s,
            arrival_window_end_s=output.arrival_window_end_s,
            terminal_contract_reject_reason=output.terminal_contract_reject_reason,
            terminal_control_reject_reason=control_reason,
            terminal_delivery_state=output.terminal_delivery_state,
            terminal_delivery_reason=output.terminal_delivery_reason,
            terminal_prediction_age_s=output.terminal_prediction_age_s,
            ttc_reject_reason=output.ttc_reject_reason,
            disturbance_type=disturbance_type,
            safety_violation=safety_violation,
            owner_mismatch=resolved_owner_mismatch,
            version_mismatch=resolved_version_mismatch,
            metadata={
                "diagnostic_boundary": COOPERATIVE_GUIDANCE_DIAGNOSTIC_BOUNDARY,
                "d3_d4_d5_gate_bypassed": False,
                **explicit_metadata,
            },
        )


@dataclass(frozen=True)
class AssignmentPairGuidanceDiagnostic:
    """Episode-level guidance funnel for one assignment pair."""

    candidate_id: str
    candidate_schema: str
    terminal_handoff_range_m: float
    primary_arrival_window_width_s: float
    approach_sector_separation_deg: float
    configured_minimum_member_separation_m: float | None
    episode_id: str
    seed: int | None
    assignment_id: str
    resource_id: str
    target_id: str
    plan_id: str
    plan_version: int
    coalition_id: str | None
    coalition_version: int | None
    member_role: str
    activation_state: str
    sample_count: int
    assigned_reached: bool
    active_reached: bool
    radar_midcourse_reached: bool
    reacquisition_reached: bool
    d5_visible_reached: bool
    d5_associated_reached: bool
    d5_locked_reached: bool
    terminal_contract_reached: bool
    terminal_control_reached: bool
    terminal_mode_reached: bool
    physical_intercept_reached: bool
    intercept_radius_m: float
    closest_approach_m: float | None
    closest_approach_time_s: float | None
    closing_speed_at_closest_mps: float | None
    physical_arrival_time_s: float | None
    arrival_window_error_s: float | None
    arrival_window_violation_s: float | None
    minimum_member_separation_m: float | None
    safety_violation_count: int
    reserve_unauthorized: bool
    owner_mismatch_count: int
    version_mismatch_count: int
    first_failure_stage: str
    first_failure_reason: str
    disturbance_types: tuple[str, ...]
    disturbance_reject_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "case": self.episode_id,
                "case_id": self.episode_id,
                "profile": self.candidate_id,
                "active_primary": bool(
                    self.member_role == "primary" and self.active_reached
                ),
                "assigned": self.assigned_reached,
                "visible": self.d5_visible_reached,
                "associated": self.d5_associated_reached,
                "locked": self.d5_locked_reached,
                "contract_allowed": self.terminal_contract_reached,
                "control_allowed": self.terminal_control_reached,
                "mode_switched": self.terminal_mode_reached,
                "physical_intercept": self.physical_intercept_reached,
                "closest_range_m": self.closest_approach_m,
                "member_separation_m": self.minimum_member_separation_m,
                "owner_version_mismatch_count": (
                    self.owner_mismatch_count + self.version_mismatch_count
                ),
            }
        )
        return payload


def coerce_cooperative_guidance_candidate(
    value: CooperativeGuidanceCandidateMetadata | Mapping[str, Any],
) -> CooperativeGuidanceCandidateMetadata:
    if isinstance(value, CooperativeGuidanceCandidateMetadata):
        return value
    return CooperativeGuidanceCandidateMetadata(
        candidate_id=str(value["candidate_id"]),
        terminal_handoff_range_m=float(
            value.get("terminal_handoff_range_m", value.get("handoff_range_m"))
        ),
        primary_arrival_window_width_s=float(
            value.get(
                "primary_arrival_window_width_s",
                value.get("arrival_window_width_s"),
            )
        ),
        approach_sector_separation_deg=float(
            value.get(
                "approach_sector_separation_deg",
                value.get("sector_separation_deg"),
            )
        ),
        minimum_member_separation_m=_optional_float(
            value.get("minimum_member_separation_m")
        ),
        source=str(value.get("source", "d3")),
        schema=str(value.get("schema", "d3_cooperative_prescreen_v1")),
        metadata=dict(value.get("metadata", {})),
    )


def build_assignment_pair_guidance_diagnostics(
    samples: Iterable[CooperativeGuidanceDiagnosticSample],
) -> tuple[AssignmentPairGuidanceDiagnostic, ...]:
    """Collapse arbitrary-N pair samples into deterministic episode rows."""

    grouped: dict[
        tuple[str, str, int | None, str],
        list[CooperativeGuidanceDiagnosticSample],
    ] = defaultdict(list)
    for sample in samples:
        grouped[
            (
                sample.candidate.candidate_id,
                sample.episode_id,
                sample.seed,
                sample.assignment_id,
            )
        ].append(sample)

    diagnostics = [
        _build_pair_diagnostic(sorted(rows, key=lambda row: row.timestamp_s))
        for _, rows in sorted(grouped.items())
    ]
    return tuple(diagnostics)


def summarize_cooperative_guidance_diagnostics(
    samples: Iterable[CooperativeGuidanceDiagnosticSample],
) -> dict[str, Any]:
    """Summarize pair, primary ordinal, coalition, and disturbance evidence."""

    sample_rows = tuple(samples)
    pairs = build_assignment_pair_guidance_diagnostics(sample_rows)
    coalitions = _coalition_diagnostics(pairs)
    candidate_summaries = _candidate_summaries(pairs, coalitions)
    pair_rows = [pair.as_dict() for pair in pairs]
    primary_ordinals = {
        (
            str(coalition["episode_id"]),
            coalition["seed"],
            str(primary["assignment_id"]),
        ): int(primary["primary_ordinal"])
        for coalition in coalitions
        for primary in coalition["primary_diagnostics"]
    }
    for row in pair_rows:
        row["member_order"] = primary_ordinals.get(
            (str(row["episode_id"]), row["seed"], str(row["assignment_id"]))
        )
    second_primary_failures = Counter(
        row["second_primary_failure_stage"]
        for row in coalitions
        if row["second_primary_failure_stage"]
    )
    primary_failure_by_ordinal: dict[str, Counter[str]] = defaultdict(Counter)
    for coalition in coalitions:
        for primary in coalition["primary_diagnostics"]:
            if primary["first_failure_stage"]:
                primary_failure_by_ordinal[str(primary["primary_ordinal"])][
                    primary["first_failure_stage"]
                ] += 1
    return {
        "boundary": COOPERATIVE_GUIDANCE_DIAGNOSTIC_BOUNDARY,
        "sample_count": len(sample_rows),
        "pair_count": len(pairs),
        "candidate_count": len(candidate_summaries),
        "coalition_count": len(coalitions),
        "pair_diagnostics": pair_rows,
        "rows": pair_rows,
        "coalition_diagnostics": coalitions,
        "candidate_summaries": candidate_summaries,
        "second_primary_failure_stage_counts": dict(second_primary_failures),
        "primary_failure_stage_counts_by_ordinal": {
            ordinal: dict(counts)
            for ordinal, counts in sorted(primary_failure_by_ordinal.items())
        },
        "disturbance_first_failure_reason_counts": dict(
            Counter(
                pair.first_failure_reason
                for pair in pairs
                if pair.disturbance_types and pair.first_failure_reason
            )
        ),
        "reserve_unauthorized_count": sum(pair.reserve_unauthorized for pair in pairs),
        "owner_mismatch_count": sum(pair.owner_mismatch_count for pair in pairs),
        "version_mismatch_count": sum(pair.version_mismatch_count for pair in pairs),
        "physical_success_radius_m_values": sorted(
            {pair.intercept_radius_m for pair in pairs}
        ),
        "simultaneous_arrival_required": False,
        "coalition_completion_semantics": (
            "all_active_primaries_independently_enter_success_radius_in_same_episode"
        ),
        "png_core_formula_changed": False,
        "d3_d4_d5_gate_bypassed": False,
        "advisory_only": True,
    }


def prescreen_cooperative_guidance_candidates(
    samples: Iterable[CooperativeGuidanceDiagnosticSample],
    *,
    top_k: int = 3,
) -> dict[str, Any]:
    """Rank candidates for main-owned AirSim testing without changing runtime defaults."""

    if top_k <= 0:
        raise ValueError("top_k must be positive")
    summary = summarize_cooperative_guidance_diagnostics(samples)
    candidates = list(summary["candidate_summaries"])
    ranked = sorted(
        candidates,
        key=lambda row: (
            row["safety_violation_count"] > 0,
            -row["coalition_completion_rate"],
            -row["active_primary_physical_success_rate"],
            row["candidate_id"],
        ),
    )
    eligible = [row for row in ranked if row["safety_violation_count"] == 0]
    selected_ids = [row["candidate_id"] for row in eligible[:top_k]]
    return {
        "boundary": COOPERATIVE_GUIDANCE_DIAGNOSTIC_BOUNDARY,
        "ranking_order": (
            "zero_safety_violations",
            "coalition_completion_rate_desc",
            "active_primary_physical_success_rate_desc",
            "candidate_id",
        ),
        "ranked_candidates": ranked,
        "selected_candidate_ids": selected_ids,
        "top_k": top_k,
        "default_runtime_candidate_changed": False,
        "png_core_formula_changed": False,
        "d3_d4_d5_gate_bypassed": False,
        "advisory_only": True,
    }


def _build_pair_diagnostic(
    rows: list[CooperativeGuidanceDiagnosticSample],
) -> AssignmentPairGuidanceDiagnostic:
    first = rows[0]
    _require_pair_consistency(rows)
    range_rows = [row for row in rows if row.range_m is not None]
    closest = min(range_rows, key=lambda row: float(row.range_m)) if range_rows else None
    arrival = next((row for row in rows if row.physical_intercept), None)
    assigned_reached = any(row.assigned for row in rows)
    active_reached = any(row.active for row in rows)
    radar_reached = any(row.radar_midcourse_active for row in rows)
    visible_reached = any(row.d5_visible for row in rows)
    associated_reached = any(row.d5_associated for row in rows)
    locked_reached = any(row.d5_locked for row in rows)
    contract_reached = any(row.terminal_contract_allowed for row in rows)
    control_reached = any(row.terminal_control_allowed for row in rows)
    mode_reached = any(row.terminal_mode_entered for row in rows)
    physical_reached = arrival is not None
    failure_stage, failure_reason = _first_failure(
        rows,
        assigned_reached=assigned_reached,
        active_reached=active_reached,
        radar_reached=radar_reached,
        visible_reached=visible_reached,
        associated_reached=associated_reached,
        locked_reached=locked_reached,
        contract_reached=contract_reached,
        control_reached=control_reached,
        mode_reached=mode_reached,
        physical_reached=physical_reached,
    )
    arrival_error = _arrival_window_error(arrival)
    separations = [
        row.member_separation_m
        for row in rows
        if row.member_separation_m is not None
    ]
    return AssignmentPairGuidanceDiagnostic(
        candidate_id=first.candidate.candidate_id,
        candidate_schema=first.candidate.schema,
        terminal_handoff_range_m=first.candidate.terminal_handoff_range_m,
        primary_arrival_window_width_s=(
            first.candidate.primary_arrival_window_width_s
        ),
        approach_sector_separation_deg=(
            first.candidate.approach_sector_separation_deg
        ),
        configured_minimum_member_separation_m=(
            first.candidate.minimum_member_separation_m
        ),
        episode_id=first.episode_id,
        seed=first.seed,
        assignment_id=first.assignment_id,
        resource_id=first.resource_id,
        target_id=first.target_id,
        plan_id=first.plan_id,
        plan_version=first.plan_version,
        coalition_id=first.coalition_id,
        coalition_version=first.coalition_version,
        member_role=first.member_role,
        activation_state=first.activation_state,
        sample_count=len(rows),
        assigned_reached=assigned_reached,
        active_reached=active_reached,
        radar_midcourse_reached=radar_reached,
        reacquisition_reached=any(row.reacquisition_active for row in rows),
        d5_visible_reached=visible_reached,
        d5_associated_reached=associated_reached,
        d5_locked_reached=locked_reached,
        terminal_contract_reached=contract_reached,
        terminal_control_reached=control_reached,
        terminal_mode_reached=mode_reached,
        physical_intercept_reached=physical_reached,
        intercept_radius_m=first.intercept_radius_m,
        closest_approach_m=float(closest.range_m) if closest is not None else None,
        closest_approach_time_s=closest.timestamp_s if closest is not None else None,
        closing_speed_at_closest_mps=(
            closest.closing_speed_mps if closest is not None else None
        ),
        physical_arrival_time_s=arrival.timestamp_s if arrival is not None else None,
        arrival_window_error_s=arrival_error,
        arrival_window_violation_s=(
            abs(arrival_error) if arrival_error is not None else None
        ),
        minimum_member_separation_m=min(separations) if separations else None,
        safety_violation_count=sum(1 for row in rows if row.safety_violation),
        reserve_unauthorized=bool(
            first.member_role == "reserve"
            and first.activation_state != "active"
            and (control_reached or mode_reached or physical_reached)
        ),
        owner_mismatch_count=sum(1 for row in rows if row.owner_mismatch),
        version_mismatch_count=sum(1 for row in rows if row.version_mismatch),
        first_failure_stage=failure_stage,
        first_failure_reason=failure_reason,
        disturbance_types=tuple(
            sorted({row.disturbance_type for row in rows if row.disturbance_type})
        ),
        disturbance_reject_reasons=tuple(
            sorted(
                {
                    reason
                    for row in rows
                    if row.disturbance_type
                    for reason in (
                        row.ttc_reject_reason,
                        row.terminal_delivery_reason,
                        row.terminal_control_reject_reason,
                    )
                    if reason
                }
            )
        ),
    )


def _first_failure(
    rows: list[CooperativeGuidanceDiagnosticSample],
    *,
    assigned_reached: bool,
    active_reached: bool,
    radar_reached: bool,
    visible_reached: bool,
    associated_reached: bool,
    locked_reached: bool,
    contract_reached: bool,
    control_reached: bool,
    mode_reached: bool,
    physical_reached: bool,
) -> tuple[str, str]:
    if physical_reached:
        return "", ""
    if not assigned_reached:
        return "assignment", "not_assigned"
    if not active_reached:
        reason = next(
            (
                row.terminal_contract_reject_reason
                for row in rows
                if row.terminal_contract_reject_reason
            ),
            "assignment_not_active",
        )
        return "activation", reason
    if not radar_reached:
        return "radar_midcourse", "radar_midcourse_not_observed"
    if not visible_reached:
        return "d5_visible", "d5_target_not_visible"
    if not associated_reached:
        return "d5_associated", "d5_target_not_associated"
    if not locked_reached:
        reason = next(
            (
                row.terminal_contract_reject_reason
                for row in rows
                if row.terminal_contract_reject_reason
            ),
            "d5_not_locked",
        )
        return "d5_locked", reason
    if not contract_reached:
        reason = next(
            (row.terminal_contract_reject_reason for row in rows if row.terminal_contract_reject_reason),
            "terminal_contract_not_allowed",
        )
        return "terminal_contract", reason
    if not control_reached:
        reason = next(
            (
                row.terminal_control_reject_reason
                for row in rows
                if row.terminal_contract_allowed and row.terminal_control_reject_reason
            ),
            "terminal_control_not_allowed",
        )
        return "terminal_control", reason
    if not mode_reached:
        return "terminal_mode", "terminal_mode_not_entered"
    return "physical", "physical_intercept_not_achieved"


def _arrival_window_error(
    arrival: CooperativeGuidanceDiagnosticSample | None,
) -> float | None:
    """Signed error: negative is early, positive is late, zero is in-window."""

    if arrival is None:
        return None
    start = arrival.arrival_window_start_s
    end = arrival.arrival_window_end_s
    if start is None or end is None:
        return None
    if arrival.timestamp_s < start:
        return arrival.timestamp_s - start
    if arrival.timestamp_s > end:
        return arrival.timestamp_s - end
    return 0.0


def _coalition_diagnostics(
    pairs: tuple[AssignmentPairGuidanceDiagnostic, ...],
) -> list[dict[str, Any]]:
    grouped: dict[
        tuple[str, str, int | None, str, str],
        list[AssignmentPairGuidanceDiagnostic],
    ] = defaultdict(list)
    for pair in pairs:
        if pair.coalition_id:
            grouped[
                (
                    pair.candidate_id,
                    pair.episode_id,
                    pair.seed,
                    pair.target_id,
                    pair.coalition_id,
                )
            ].append(pair)

    result: list[dict[str, Any]] = []
    for (
        candidate_id,
        episode_id,
        seed,
        target_id,
        coalition_id,
    ), members in sorted(grouped.items(), key=lambda item: str(item[0])):
        primaries = sorted(
            (
                member
                for member in members
                if member.member_role == "primary" and member.activation_state == "active"
            ),
            key=lambda member: (member.resource_id, member.assignment_id),
        )
        arrivals = [
            member.physical_arrival_time_s
            for member in primaries
            if member.physical_arrival_time_s is not None
        ]
        complete = bool(primaries) and len(arrivals) == len(primaries)
        spread = max(arrivals) - min(arrivals) if len(arrivals) >= 2 else None
        primary_rows = [
            {
                "primary_ordinal": index,
                "assignment_id": member.assignment_id,
                "resource_id": member.resource_id,
                "physical_intercept_reached": member.physical_intercept_reached,
                "first_failure_stage": member.first_failure_stage,
                "first_failure_reason": member.first_failure_reason,
                "physical_arrival_time_s": member.physical_arrival_time_s,
            }
            for index, member in enumerate(primaries, start=1)
        ]
        second = primary_rows[1] if len(primary_rows) >= 2 else None
        result.append(
            {
                "candidate_id": candidate_id,
                "candidate_schema": members[0].candidate_schema,
                "episode_id": episode_id,
                "case": episode_id,
                "seed": seed,
                "profile": candidate_id,
                "target_id": target_id,
                "coalition_id": coalition_id,
                "primary_count": len(primaries),
                "arrived_primary_count": len(arrivals),
                "coalition_complete": complete,
                "coalition_arrival_spread_s": spread,
                "coalition_arrival_spread_complete": complete and spread is not None,
                "minimum_member_separation_m": _minimum_optional(
                    member.minimum_member_separation_m for member in primaries
                ),
                "safety_violation_count": sum(
                    member.safety_violation_count for member in primaries
                ),
                "reserve_unauthorized_count": sum(
                    member.reserve_unauthorized for member in members
                ),
                "owner_mismatch_count": sum(
                    member.owner_mismatch_count for member in members
                ),
                "version_mismatch_count": sum(
                    member.version_mismatch_count for member in members
                ),
                "primary_diagnostics": primary_rows,
                "second_primary_failure_stage": (
                    second["first_failure_stage"] if second is not None else ""
                ),
                "second_primary_failure_reason": (
                    second["first_failure_reason"] if second is not None else ""
                ),
            }
        )
    return result


def _candidate_summaries(
    pairs: tuple[AssignmentPairGuidanceDiagnostic, ...],
    coalitions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pair_groups: dict[str, list[AssignmentPairGuidanceDiagnostic]] = defaultdict(list)
    coalition_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        pair_groups[pair.candidate_id].append(pair)
    for coalition in coalitions:
        coalition_groups[str(coalition["candidate_id"])].append(coalition)

    summaries: list[dict[str, Any]] = []
    for candidate_id, candidate_pairs in sorted(pair_groups.items()):
        candidate_coalitions = coalition_groups.get(candidate_id, [])
        active_primaries = [
            pair
            for pair in candidate_pairs
            if pair.member_role == "primary" and pair.activation_state == "active"
        ]
        complete_spreads = [
            float(row["coalition_arrival_spread_s"])
            for row in candidate_coalitions
            if row["coalition_arrival_spread_complete"]
        ]
        first_pair = candidate_pairs[0]
        summaries.append(
            {
                "candidate_id": candidate_id,
                "candidate_schema": first_pair.candidate_schema,
                "terminal_handoff_range_m": first_pair.terminal_handoff_range_m,
                "primary_arrival_window_width_s": (
                    first_pair.primary_arrival_window_width_s
                ),
                "approach_sector_separation_deg": (
                    first_pair.approach_sector_separation_deg
                ),
                "configured_minimum_member_separation_m": (
                    first_pair.configured_minimum_member_separation_m
                ),
                "pair_count": len(candidate_pairs),
                "active_primary_count": len(active_primaries),
                "active_primary_physical_success_rate": _rate(
                    sum(pair.physical_intercept_reached for pair in active_primaries),
                    len(active_primaries),
                ),
                "coalition_count": len(candidate_coalitions),
                "coalition_completion_rate": _rate(
                    sum(bool(row["coalition_complete"]) for row in candidate_coalitions),
                    len(candidate_coalitions),
                ),
                "mean_complete_arrival_spread_s": (
                    sum(complete_spreads) / len(complete_spreads)
                    if complete_spreads
                    else None
                ),
                "safety_violation_count": sum(
                    pair.safety_violation_count for pair in candidate_pairs
                ),
                "candidate_metadata_available": True,
            }
        )
    return summaries


def _require_pair_consistency(rows: list[CooperativeGuidanceDiagnosticSample]) -> None:
    first = rows[0]
    identity = (
        first.candidate.candidate_id,
        first.candidate.schema,
        first.candidate.terminal_handoff_range_m,
        first.candidate.primary_arrival_window_width_s,
        first.candidate.approach_sector_separation_deg,
        first.episode_id,
        first.seed,
        first.assignment_id,
        first.resource_id,
        first.target_id,
        first.plan_id,
        first.plan_version,
        first.coalition_id,
        first.coalition_version,
        first.member_role,
        first.activation_state,
        first.intercept_radius_m,
    )
    if any(
        (
            row.candidate.candidate_id,
            row.candidate.schema,
            row.candidate.terminal_handoff_range_m,
            row.candidate.primary_arrival_window_width_s,
            row.candidate.approach_sector_separation_deg,
            row.episode_id,
            row.seed,
            row.assignment_id,
            row.resource_id,
            row.target_id,
            row.plan_id,
            row.plan_version,
            row.coalition_id,
            row.coalition_version,
            row.member_role,
            row.activation_state,
            row.intercept_radius_m,
        )
        != identity
        for row in rows[1:]
    ):
        raise ValueError("assignment pair diagnostic identity changed within one group")


def _minimum_optional(values: Iterable[float | None]) -> float | None:
    available = [float(value) for value in values if value is not None]
    return min(available) if available else None


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _runtime_d5_visible(
    output: D7RuntimePairOutput,
    metadata: Mapping[str, Any],
) -> bool:
    for key in ("d5_visible", "visible", "target_visible", "detection_seen"):
        if key in metadata:
            return bool(metadata[key])
    return output.bbox_xyxy is not None


def _runtime_d5_associated(
    output: D7RuntimePairOutput,
    metadata: Mapping[str, Any],
) -> bool:
    for key in ("d5_associated", "associated", "terminal_associated"):
        if key in metadata:
            return bool(metadata[key])
    registered = str(output.detect_registration_outcome or "").lower() in {
        "associated",
        "matched",
        "registered",
        "locked",
    }
    return bool(registered or output.d5_lock_consistent is True)


def _runtime_owner_mismatch(output: D7RuntimePairOutput) -> bool:
    return bool(
        output.d3_owner_consistent is False
        or output.terminal_contract_reject_reason
        in {"d4_owner_missing", "d4_owner_mismatch"}
    )


def _runtime_version_mismatch(output: D7RuntimePairOutput) -> bool:
    return bool(
        output.d3_plan_version_consistent is False
        or output.terminal_contract_reject_reason
        in {
            "assignment_version_mismatch",
            "d4_plan_mismatch",
            "coalition_plan_version_mismatch",
            "coalition_track_version_mismatch",
            "coalition_version_mismatch",
        }
    )


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
