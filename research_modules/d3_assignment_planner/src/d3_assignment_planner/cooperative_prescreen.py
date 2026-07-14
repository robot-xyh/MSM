"""Deterministic P1 candidate definitions and observed-result ranking.

This module does not solve assignments or predict physical interception
outcomes.  It defines the parameter grid consumed by main, preserves D3's
versioned coalition metadata, and ranks measurements supplied by main/D6.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from .models import (
    AssignmentPlan,
    CoalitionMemberRole,
    CoalitionState,
    TargetDemand,
)


COOPERATIVE_PRESCREEN_SCHEMA_V1 = "d3_cooperative_prescreen_v1"
P1_TERMINAL_HANDOFF_RANGES_M = (20.0, 30.0, 40.0)
P1_PRIMARY_ARRIVAL_WINDOW_WIDTHS_S = (3.0, 5.0, 8.0)
P1_APPROACH_SECTOR_SEPARATIONS_DEG = (20.0, 40.0, 60.0)


class StaleCooperativeCandidatePlanError(ValueError):
    """Raised when candidate metadata is requested for a non-current plan."""


@dataclass(frozen=True)
class CooperativePrescreenCandidate:
    """One planner-independent candidate in the P1 cooperative sweep."""

    terminal_handoff_range_m: float
    primary_arrival_window_width_s: float
    approach_sector_separation_deg: float
    schema: str = COOPERATIVE_PRESCREEN_SCHEMA_V1

    def __post_init__(self) -> None:
        for name, value in (
            ("terminal_handoff_range_m", self.terminal_handoff_range_m),
            ("primary_arrival_window_width_s", self.primary_arrival_window_width_s),
            ("approach_sector_separation_deg", self.approach_sector_separation_deg),
        ):
            if float(value) <= 0.0:
                raise ValueError(f"{name} must be positive")

    @property
    def candidate_id(self) -> str:
        return (
            f"d3-p1-h{self.terminal_handoff_range_m:05.1f}"
            f"-w{self.primary_arrival_window_width_s:04.1f}"
            f"-s{self.approach_sector_separation_deg:05.1f}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_id": self.candidate_id,
            "terminal_handoff_range_m": self.terminal_handoff_range_m,
            "primary_arrival_window_width_s": (
                self.primary_arrival_window_width_s
            ),
            "approach_sector_separation_deg": (
                self.approach_sector_separation_deg
            ),
        }


@dataclass(frozen=True)
class CooperativeCandidateObservation:
    """Physical evidence supplied by main/D6 for one completed candidate run."""

    candidate_id: str
    safety_violation_count: int
    coalition_completion_count: int
    coalition_opportunity_count: int
    pair_success_count: int
    pair_opportunity_count: int
    arrival_spread_s: float
    evidence_source: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        counts = {
            "safety_violation_count": self.safety_violation_count,
            "coalition_completion_count": self.coalition_completion_count,
            "coalition_opportunity_count": self.coalition_opportunity_count,
            "pair_success_count": self.pair_success_count,
            "pair_opportunity_count": self.pair_opportunity_count,
        }
        if any(int(value) < 0 for value in counts.values()):
            raise ValueError("candidate observation counts must be non-negative")
        if self.coalition_opportunity_count < 1 or self.pair_opportunity_count < 1:
            raise ValueError("candidate observations require non-empty denominators")
        if self.coalition_completion_count > self.coalition_opportunity_count:
            raise ValueError("coalition completions cannot exceed opportunities")
        if self.pair_success_count > self.pair_opportunity_count:
            raise ValueError("pair successes cannot exceed opportunities")
        if self.arrival_spread_s < 0.0:
            raise ValueError("arrival_spread_s must be non-negative")
        if not self.evidence_source.strip():
            raise ValueError("evidence_source is required")

    @property
    def coalition_completion_rate(self) -> float:
        return self.coalition_completion_count / self.coalition_opportunity_count

    @property
    def pair_success_rate(self) -> float:
        return self.pair_success_count / self.pair_opportunity_count

    def as_dict(self) -> dict[str, Any]:
        return {
            **dict(self.__dict__),
            "coalition_completion_rate": self.coalition_completion_rate,
            "pair_success_rate": self.pair_success_rate,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RankedCooperativeCandidate:
    rank: int
    candidate: CooperativePrescreenCandidate
    observation: CooperativeCandidateObservation

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "candidate": self.candidate.as_dict(),
            "observation": self.observation.as_dict(),
        }


@dataclass(frozen=True)
class CooperativeCandidateMemberMetadata:
    candidate_id: str
    target_id: str
    resource_id: str
    member_role: str
    activation_state: str
    wave_id: int
    arrival_window_start_s: float | None
    arrival_window_end_s: float | None
    planned_arrival_window_width_s: float | None
    required_resource_count: int
    plan_id: str
    plan_version: int
    coalition_id: str | None
    coalition_version: int | None
    minimum_separation_s: float | None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class CooperativeCandidatePlanMetadata:
    """Read-only D3 plan metadata for main/D6 candidate execution."""

    candidate_id: str
    schema: str
    plan_id: str
    plan_version: int
    resource_count: int
    target_count: int
    terminal_handoff_range_m: float
    primary_arrival_window_width_s: float
    approach_sector_separation_deg: float
    candidate_parameters_match_plan: bool
    members: tuple[CooperativeCandidateMemberMetadata, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            **dict(self.__dict__),
            "members": tuple(member.as_dict() for member in self.members),
        }


def build_p1_cooperative_candidate_grid() -> tuple[CooperativePrescreenCandidate, ...]:
    """Return the fixed 3x3x3 P1 parameter grid in stable ID order."""

    candidates = (
        CooperativePrescreenCandidate(handoff, width, sector)
        for handoff in P1_TERMINAL_HANDOFF_RANGES_M
        for width in P1_PRIMARY_ARRIVAL_WINDOW_WIDTHS_S
        for sector in P1_APPROACH_SECTOR_SEPARATIONS_DEG
    )
    return tuple(sorted(candidates, key=lambda item: item.candidate_id))


def demand_for_cooperative_candidate(
    demand: TargetDemand,
    candidate: CooperativePrescreenCandidate,
    *,
    arrival_window_start_s: float | None = None,
) -> TargetDemand:
    """Apply candidate timing metadata while preserving dynamic demand size.

    Resource count, primary count, coordination mode, capabilities, wave
    interval, and minimum separation are inherited from the supplied demand.
    """

    window_start = (
        demand.arrival_window_start_s
        if arrival_window_start_s is None
        else float(arrival_window_start_s)
    )
    if window_start is None:
        raise ValueError("arrival_window_start_s is required for candidate demand")
    metadata = {
        **dict(demand.metadata),
        **candidate.as_dict(),
    }
    return replace(
        demand,
        arrival_window_start_s=window_start,
        arrival_window_end_s=(
            window_start + candidate.primary_arrival_window_width_s
        ),
        metadata=metadata,
    )


def rank_cooperative_candidates(
    candidates: Sequence[CooperativePrescreenCandidate],
    observations: Sequence[CooperativeCandidateObservation],
    *,
    limit: int = 3,
) -> tuple[RankedCooperativeCandidate, ...]:
    """Rank observed candidates without estimating missing physical results."""

    if limit < 1:
        raise ValueError("limit must be at least 1")
    candidate_by_id = _unique_by_id(candidates, "candidate")
    observation_by_id = _unique_by_id(observations, "observation")
    missing = sorted(set(candidate_by_id) - set(observation_by_id))
    unexpected = sorted(set(observation_by_id) - set(candidate_by_id))
    if missing or unexpected:
        raise ValueError(
            "candidate observations must match candidate IDs exactly; "
            f"missing={missing}, unexpected={unexpected}"
        )

    ordered = sorted(
        candidates,
        key=lambda candidate: _candidate_rank_key(
            candidate,
            observation_by_id[candidate.candidate_id],
        ),
    )
    return tuple(
        RankedCooperativeCandidate(
            rank=index + 1,
            candidate=candidate,
            observation=observation_by_id[candidate.candidate_id],
        )
        for index, candidate in enumerate(ordered[:limit])
    )


def export_cooperative_candidate_plan_metadata(
    plan: AssignmentPlan,
    candidate: CooperativePrescreenCandidate,
    *,
    current_plan_id: str,
    current_plan_version: int,
) -> CooperativeCandidatePlanMetadata:
    """Export current plan/coalition metadata and reject stale identities."""

    if plan.plan_id != current_plan_id or plan.version != current_plan_version:
        raise StaleCooperativeCandidatePlanError(
            "candidate metadata requires the current assignment plan"
        )
    coalition_by_target = {item.target_id: item for item in plan.coalitions}
    members: list[CooperativeCandidateMemberMetadata] = []
    parameters_match = True

    for assignment in sorted(
        plan.assignments,
        key=lambda item: (item.target_id, item.wave_id, item.member_role, item.resource_id),
    ):
        if assignment.plan_version not in {None, plan.version}:
            raise StaleCooperativeCandidatePlanError(
                f"assignment {assignment.resource_id} carries a stale plan version"
            )
        coalition = coalition_by_target.get(assignment.target_id)
        if assignment.coalition_id is not None and (
            coalition is None
            or coalition.coalition_id != assignment.coalition_id
            or coalition.version != assignment.coalition_version
            or coalition.state != CoalitionState.COMMITTED.value
            or not coalition.complete
        ):
            raise StaleCooperativeCandidatePlanError(
                f"assignment {assignment.resource_id} carries a stale coalition"
            )
        width = _window_width(
            assignment.arrival_window_start_s,
            assignment.arrival_window_end_s,
        )
        if (
            assignment.member_role == CoalitionMemberRole.PRIMARY.value
            and coalition is not None
            and coalition.coordination_mode != "independent"
        ):
            parameters_match = parameters_match and (
                width is not None
                and abs(width - candidate.primary_arrival_window_width_s) <= 1e-9
            )
        activation_state = (
            "active"
            if assignment.member_role == CoalitionMemberRole.PRIMARY.value
            else "standby"
        )
        members.append(
            CooperativeCandidateMemberMetadata(
                candidate_id=candidate.candidate_id,
                target_id=assignment.target_id,
                resource_id=assignment.resource_id,
                member_role=assignment.member_role,
                activation_state=activation_state,
                wave_id=assignment.wave_id,
                arrival_window_start_s=assignment.arrival_window_start_s,
                arrival_window_end_s=assignment.arrival_window_end_s,
                planned_arrival_window_width_s=width,
                required_resource_count=assignment.required_resource_count,
                plan_id=plan.plan_id,
                plan_version=plan.version,
                coalition_id=assignment.coalition_id,
                coalition_version=assignment.coalition_version,
                minimum_separation_s=(
                    None if coalition is None else coalition.minimum_separation_s
                ),
            )
        )

    return CooperativeCandidatePlanMetadata(
        candidate_id=candidate.candidate_id,
        schema=candidate.schema,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        resource_count=plan.resource_count,
        target_count=plan.target_count,
        terminal_handoff_range_m=candidate.terminal_handoff_range_m,
        primary_arrival_window_width_s=candidate.primary_arrival_window_width_s,
        approach_sector_separation_deg=candidate.approach_sector_separation_deg,
        candidate_parameters_match_plan=parameters_match,
        members=tuple(members),
    )


def _unique_by_id(values: Sequence[Any], label: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for value in values:
        candidate_id = str(value.candidate_id)
        if candidate_id in result:
            raise ValueError(f"duplicate {label} ID: {candidate_id}")
        result[candidate_id] = value
    return result


def _candidate_rank_key(
    candidate: CooperativePrescreenCandidate,
    observation: CooperativeCandidateObservation,
) -> tuple[Any, ...]:
    return (
        observation.safety_violation_count != 0,
        -observation.coalition_completion_rate,
        -observation.pair_success_rate,
        observation.arrival_spread_s,
        candidate.candidate_id,
    )


def _window_width(start_s: float | None, end_s: float | None) -> float | None:
    if start_s is None or end_s is None:
        return None
    return float(end_s - start_s)
