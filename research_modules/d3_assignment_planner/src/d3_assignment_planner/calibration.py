"""Reusable P1 calibration matrix for full and incremental D3 planning."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Mapping, Sequence

from .fixtures import (
    P1_ASSIGNMENT_FIXTURE_PROFILE_ID,
    P1_ASSIGNMENT_FIXTURE_PROFILE_VERSION,
    AssignmentFixtureStep,
    AssignmentScenarioFixture,
    build_p1_assignment_fixtures,
)
from .models import (
    AssignmentPlan,
    PlannerConfig,
    ResourceState,
    TargetTrack,
    apply_terminal_feedback_to_planner_inputs,
    summarize_incremental_planning_comparison,
)
from .planner import AssignmentPlanner


@dataclass(frozen=True)
class P1AssignmentCalibrationRow:
    """One full-versus-incremental transition in the P1 scenario matrix."""

    scenario_id: str
    scenario_kind: str
    step_id: str
    event_type: str
    resource_count: int
    target_count: int
    incremental_applied: bool
    fallback_reason: str | None
    assignment_equivalent: bool
    cost_equivalent: bool
    incremental_latency_ms: float
    full_latency_ms: float
    latency_ratio: float | None
    incremental_churn: int
    full_churn: int
    incremental_unassigned_high_threat_count: int
    full_unassigned_high_threat_count: int
    incremental_coalition_shortfall: int
    full_coalition_shortfall: int
    incremental_hard_window_reject_count: int
    full_hard_window_reject_count: int
    role_aware_primary_preserved: bool | None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class P1AssignmentCalibrationSummary:
    """Aggregate matrix output for D6/main calibration reporting."""

    profile_id: str
    profile_version: str
    rows: tuple[P1AssignmentCalibrationRow, ...]
    scenario_count: int
    transition_count: int
    equivalent_transition_count: int
    incremental_applied_count: int
    fallback_count: int
    incremental_latency_ms_total: float
    full_latency_ms_total: float
    incremental_churn_total: int
    full_churn_total: int
    incremental_unassigned_high_threat_total: int
    full_unassigned_high_threat_total: int
    incremental_coalition_shortfall_total: int
    full_coalition_shortfall_total: int

    def as_dict(self) -> dict[str, Any]:
        return {
            key: (
                tuple(row.as_dict() for row in self.rows)
                if key == "rows"
                else value
            )
            for key, value in self.__dict__.items()
        }


def run_p1_assignment_calibration_matrix(
    fixtures: Sequence[AssignmentScenarioFixture] | None = None,
    *,
    config: PlannerConfig | None = None,
) -> P1AssignmentCalibrationSummary:
    """Run deterministic P1 transitions through full and incremental planners.

    The helper is a calibration harness, not a new online solver. Both paths use
    the existing Hungarian/demand-slot implementation and the same planner
    configuration. Dynamic set, demand, capacity, or global changes may
    conservatively fall back to full planning and report that reason.
    """

    scenario_items = tuple(
        build_p1_assignment_fixtures() if fixtures is None else fixtures
    )
    planner_config = config or PlannerConfig()
    rows: list[P1AssignmentCalibrationRow] = []

    for fixture in scenario_items:
        if len(fixture.steps) < 2:
            continue
        incremental_planner = AssignmentPlanner(config=planner_config)
        full_planner = AssignmentPlanner(config=planner_config)
        initial = fixture.steps[0]
        incremental_previous = incremental_planner.plan(
            initial.tracks,
            initial.resources,
            timestamp=initial.timestamp_s,
        )
        full_previous = full_planner.plan(
            initial.tracks,
            initial.resources,
            timestamp=initial.timestamp_s,
        )

        for step in fixture.steps[1:]:
            incremental_tracks, incremental_resources = _materialize_step(
                step,
                previous_plan=incremental_previous,
            )
            full_tracks, full_resources = _materialize_step(
                step,
                previous_plan=full_previous,
            )
            incremental_plan = incremental_planner.plan_incremental(
                incremental_tracks,
                incremental_resources,
                timestamp=step.timestamp_s,
                previous_plan=incremental_previous,
                changed_track_ids=step.changed_track_ids,
                changed_resource_ids=step.changed_resource_ids,
                expected_previous_version=incremental_previous.version,
            )
            full_started_at = perf_counter()
            full_plan = full_planner.plan(
                full_tracks,
                full_resources,
                timestamp=step.timestamp_s,
                previous_plan=full_previous,
                expected_previous_version=full_previous.version,
            )
            full_latency_ms = (perf_counter() - full_started_at) * 1000.0
            comparison = summarize_incremental_planning_comparison(
                incremental_plan,
                full_plan,
                previous_plan=incremental_previous,
                full_latency_ms=full_latency_ms,
            )
            rows.append(
                P1AssignmentCalibrationRow(
                    scenario_id=fixture.scenario_id,
                    scenario_kind=fixture.scenario_kind,
                    step_id=step.step_id,
                    event_type=step.event_type,
                    resource_count=len(incremental_resources),
                    target_count=len(incremental_tracks),
                    incremental_applied=comparison.incremental_applied,
                    fallback_reason=comparison.fallback_reason,
                    assignment_equivalent=comparison.assignment_equivalent,
                    cost_equivalent=comparison.cost_equivalent,
                    incremental_latency_ms=comparison.incremental_latency_ms,
                    full_latency_ms=comparison.full_latency_ms,
                    latency_ratio=comparison.latency_ratio,
                    incremental_churn=comparison.incremental_change_count,
                    full_churn=comparison.full_change_count,
                    incremental_unassigned_high_threat_count=(
                        _unassigned_high_threat_count(
                            incremental_plan,
                            incremental_tracks,
                            planner_config.high_threat_threshold,
                        )
                    ),
                    full_unassigned_high_threat_count=_unassigned_high_threat_count(
                        full_plan,
                        full_tracks,
                        planner_config.high_threat_threshold,
                    ),
                    incremental_coalition_shortfall=_coalition_shortfall(
                        incremental_plan
                    ),
                    full_coalition_shortfall=_coalition_shortfall(full_plan),
                    incremental_hard_window_reject_count=(
                        _hard_window_reject_count(incremental_plan)
                    ),
                    full_hard_window_reject_count=_hard_window_reject_count(full_plan),
                    role_aware_primary_preserved=_role_aware_primary_preserved(
                        step,
                        incremental_plan,
                    ),
                )
            )
            incremental_previous = incremental_plan
            full_previous = full_plan

    row_items = tuple(rows)
    return P1AssignmentCalibrationSummary(
        profile_id=P1_ASSIGNMENT_FIXTURE_PROFILE_ID,
        profile_version=P1_ASSIGNMENT_FIXTURE_PROFILE_VERSION,
        rows=row_items,
        scenario_count=len(scenario_items),
        transition_count=len(row_items),
        equivalent_transition_count=sum(
            row.assignment_equivalent and row.cost_equivalent for row in row_items
        ),
        incremental_applied_count=sum(row.incremental_applied for row in row_items),
        fallback_count=sum(not row.incremental_applied for row in row_items),
        incremental_latency_ms_total=sum(
            row.incremental_latency_ms for row in row_items
        ),
        full_latency_ms_total=sum(row.full_latency_ms for row in row_items),
        incremental_churn_total=sum(row.incremental_churn for row in row_items),
        full_churn_total=sum(row.full_churn for row in row_items),
        incremental_unassigned_high_threat_total=sum(
            row.incremental_unassigned_high_threat_count for row in row_items
        ),
        full_unassigned_high_threat_total=sum(
            row.full_unassigned_high_threat_count for row in row_items
        ),
        incremental_coalition_shortfall_total=sum(
            row.incremental_coalition_shortfall for row in row_items
        ),
        full_coalition_shortfall_total=sum(
            row.full_coalition_shortfall for row in row_items
        ),
    )


def _materialize_step(
    step: AssignmentFixtureStep,
    *,
    previous_plan: AssignmentPlan,
) -> tuple[tuple[TargetTrack, ...], tuple[ResourceState, ...]]:
    if step.event_type != "d5_feedback":
        return step.tracks, step.resources

    primary_ids = tuple(str(value) for value in step.metadata["primary_resource_ids"])
    reserve_id = str(step.metadata["reserve_resource_id"])
    target_id = str(step.metadata["target_id"])
    feedback = tuple(
        {
            "target_id": target_id,
            "resource_id": resource_id,
            "plan_version": previous_plan.version,
            "terminal_feedback_state": "consistent",
            "main_action": "continue",
        }
        for resource_id in primary_ids
    ) + (
        {
            "target_id": target_id,
            "resource_id": reserve_id,
            "plan_version": previous_plan.version,
            "terminal_feedback_state": "hold",
            "main_action": "hold",
        },
    )
    writeback = apply_terminal_feedback_to_planner_inputs(
        step.tracks,
        step.resources,
        feedback,
    )
    return writeback.tracks, writeback.resources


def _unassigned_high_threat_count(
    plan: AssignmentPlan,
    tracks: Sequence[TargetTrack],
    threshold: float,
) -> int:
    unassigned = set(plan.unassigned_target_ids) | set(plan.incomplete_target_ids)
    return sum(
        track.track_id in unassigned and track.threat_score >= threshold
        for track in tracks
    )


def _coalition_shortfall(plan: AssignmentPlan) -> int:
    return sum(max(0, summary.demand_shortfall) for summary in plan.demand_summaries)


def _hard_window_reject_count(plan: AssignmentPlan) -> int:
    rejected_edges = plan.metadata.get("rejected_edges", ())
    return sum(
        str(edge.get("reject_reason", "")).startswith("time_window_")
        for edge in rejected_edges
        if isinstance(edge, Mapping)
    )


def _role_aware_primary_preserved(
    step: AssignmentFixtureStep,
    plan: AssignmentPlan,
) -> bool | None:
    expected = step.metadata.get("primary_resource_ids")
    target_id = step.metadata.get("target_id")
    if expected is None or target_id is None:
        return None
    actual = {
        assignment.resource_id
        for assignment in plan.assignments_by_target().get(str(target_id), ())
        if assignment.member_role == "primary"
    }
    return actual == {str(resource_id) for resource_id in expected}
