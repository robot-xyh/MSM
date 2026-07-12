"""Deterministic D3 P1 fixtures for N/M and feedback governance calibration."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from .models import ResourceState, TargetDemand, TargetTrack


P1_ASSIGNMENT_FIXTURE_SCHEMA = "d3_assignment_fixture_v2"
P1_ASSIGNMENT_FIXTURE_PROFILE_ID = "d3_p1_nm_feedback_governance"
P1_ASSIGNMENT_FIXTURE_PROFILE_VERSION = "1.1.0"


@dataclass(frozen=True)
class AssignmentFixtureStep:
    """One deterministic planner input snapshot within a fixture."""

    step_id: str
    timestamp_s: float
    tracks: tuple[TargetTrack, ...]
    resources: tuple[ResourceState, ...]
    event_type: str = "baseline"
    changed_track_ids: tuple[str, ...] = ()
    changed_resource_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def target_count(self) -> int:
        return len(self.tracks)

    @property
    def resource_count(self) -> int:
        return len(self.resources)


@dataclass(frozen=True)
class AssignmentScenarioFixture:
    """Versioned scenario consumed by D3 tests and main/D6 calibration."""

    scenario_id: str
    scenario_kind: str
    steps: tuple[AssignmentFixtureStep, ...]
    profile_id: str = P1_ASSIGNMENT_FIXTURE_PROFILE_ID
    profile_version: str = P1_ASSIGNMENT_FIXTURE_PROFILE_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def calibration_metadata(self) -> dict[str, Any]:
        return {
            "fixture_schema": P1_ASSIGNMENT_FIXTURE_SCHEMA,
            "fixture_profile_id": self.profile_id,
            "fixture_profile_version": self.profile_version,
            "scenario_id": self.scenario_id,
            "scenario_kind": self.scenario_kind,
            "step_count": len(self.steps),
            "step_shapes": tuple(
                {
                    "step_id": step.step_id,
                    "target_count": step.target_count,
                    "resource_count": step.resource_count,
                    "event_type": step.event_type,
                    "changed_track_ids": step.changed_track_ids,
                    "changed_resource_ids": step.changed_resource_ids,
                }
                for step in self.steps
            ),
            **dict(self.metadata),
        }


def build_p1_assignment_fixtures() -> tuple[AssignmentScenarioFixture, ...]:
    """Return the reusable P1 non-equal, feedback, and hard-window matrix.

    Scenario names use ``resources x targets`` ordering. Counts are repeated in
    metadata so consumers never need to infer that convention from the label.
    """

    five_resources = _resources(5)
    five_targets = _tracks(5, 5)
    three_resources = _resources(3)
    five_targets_for_three_resources = _tracks(5, 3)
    three_targets = _tracks(3, 5)

    target_arrival_initial = _tracks(4, 4, threat_start=0.55)
    arriving_target = _track(
        target_index=5,
        resource_count=4,
        threat_score=0.98,
        metadata={"event": "new_high_threat_target"},
    )
    target_arrival_resources = _resources(4)

    failed_resources = tuple(
        replace(
            resource,
            status="unavailable",
            availability_score=0.0,
            metadata={"event": "resource_failure"},
        )
        if resource.resource_id == "R03"
        else resource
        for resource in five_resources
    )

    demand_resources = _resources(3)
    demand_initial = (
        _track(target_index=1, resource_count=3, threat_score=0.98),
        _track(target_index=2, resource_count=3, threat_score=0.55),
    )
    demand_changed = (
        replace(
            demand_initial[0],
            demand=TargetDemand(
                required_resource_count=3,
                primary_resource_count=2,
                coordination_mode="hybrid",
                wave_interval_s=2.0,
            ),
            metadata={"event": "high_threat_demand_increase"},
        ),
        demand_initial[1],
    )

    feedback_resources = (
        ResourceState("R01", capability_class="reserve"),
        ResourceState("R02", capability_class="alpha"),
        ResourceState("R03", capability_class="beta"),
        ResourceState("R04", capability_class="beta"),
        ResourceState("R05", capability_class="interceptor"),
    )
    feedback_initial = _feedback_tracks(reserve_replan=False)
    feedback_changed = _feedback_tracks(reserve_replan=True)

    hard_window_resources = _resources(2)
    hard_window_initial = (
        replace(
            _track(target_index=1, resource_count=2, threat_score=0.90),
            fov_difficulty_by_resource={"R01": 0.0, "R02": 0.6},
        ),
    )
    hard_window_changed = (
        replace(
            hard_window_initial[0],
            hard_time_window=True,
            time_window_by_resource={
                "R01": {"state": "closed", "time_window_close_at_s": 2.0},
                "R02": {"state": "open", "time_window_close_at_s": 10.0},
            },
            metadata={"event": "hard_window_closed_for_previous_resource"},
        ),
    )

    return (
        _two_step_track_change_fixture(
            scenario_id="5v5",
            scenario_kind="equal_nm",
            tracks=five_targets,
            resources=five_resources,
        ),
        _two_step_track_change_fixture(
            scenario_id="3v5",
            scenario_kind="resource_shortage",
            tracks=five_targets_for_three_resources,
            resources=three_resources,
        ),
        _two_step_track_change_fixture(
            scenario_id="5v3",
            scenario_kind="resource_surplus",
            tracks=three_targets,
            resources=five_resources,
        ),
        AssignmentScenarioFixture(
            scenario_id="new_target",
            scenario_kind="target_arrival",
            steps=(
                AssignmentFixtureStep(
                    step_id="before_target_arrival",
                    timestamp_s=0.0,
                    tracks=target_arrival_initial,
                    resources=target_arrival_resources,
                ),
                AssignmentFixtureStep(
                    step_id="after_target_arrival",
                    timestamp_s=3.0,
                    tracks=target_arrival_initial + (arriving_target,),
                    resources=target_arrival_resources,
                    event_type="new_target",
                    changed_track_ids=(arriving_target.track_id,),
                    metadata={"new_target_id": arriving_target.track_id},
                ),
            ),
            metadata={"resource_target_order": "resources_x_targets"},
        ),
        AssignmentScenarioFixture(
            scenario_id="resource_failure",
            scenario_kind="resource_failure",
            steps=(
                AssignmentFixtureStep(
                    step_id="before_resource_failure",
                    timestamp_s=0.0,
                    tracks=five_targets,
                    resources=five_resources,
                ),
                AssignmentFixtureStep(
                    step_id="after_resource_failure",
                    timestamp_s=3.0,
                    tracks=five_targets,
                    resources=failed_resources,
                    event_type="resource_failure",
                    changed_resource_ids=("R03",),
                    metadata={"failed_resource_id": "R03"},
                ),
            ),
            metadata={"resource_target_order": "resources_x_targets"},
        ),
        AssignmentScenarioFixture(
            scenario_id="threat_demand_change",
            scenario_kind="high_threat_demand_change",
            steps=(
                AssignmentFixtureStep(
                    step_id="before_threat_demand_change",
                    timestamp_s=0.0,
                    tracks=demand_initial,
                    resources=demand_resources,
                ),
                AssignmentFixtureStep(
                    step_id="after_threat_demand_change",
                    timestamp_s=3.0,
                    tracks=demand_changed,
                    resources=demand_resources,
                    event_type="threat_demand_change",
                    changed_track_ids=("T01",),
                    metadata={
                        "target_id": "T01",
                        "required_resource_count": 3,
                        "primary_resource_count": 2,
                    },
                ),
            ),
            metadata={"resource_target_order": "resources_x_targets"},
        ),
        AssignmentScenarioFixture(
            scenario_id="d5_feedback",
            scenario_kind="terminal_feedback",
            steps=(
                AssignmentFixtureStep(
                    step_id="before_d5_feedback",
                    timestamp_s=0.0,
                    tracks=feedback_initial,
                    resources=feedback_resources,
                ),
                AssignmentFixtureStep(
                    step_id="after_d5_reserve_hold",
                    timestamp_s=3.0,
                    tracks=feedback_changed,
                    resources=feedback_resources,
                    event_type="d5_feedback",
                    changed_track_ids=("T001",),
                    changed_resource_ids=("R01",),
                    metadata={
                        "feedback_case": "reserve_soft_hold",
                        "target_id": "T001",
                        "primary_resource_ids": ("R02", "R03"),
                        "reserve_resource_id": "R01",
                    },
                ),
            ),
            metadata={"resource_target_order": "resources_x_targets"},
        ),
        AssignmentScenarioFixture(
            scenario_id="hard_window",
            scenario_kind="hard_time_window",
            steps=(
                AssignmentFixtureStep(
                    step_id="before_hard_window_close",
                    timestamp_s=0.0,
                    tracks=hard_window_initial,
                    resources=hard_window_resources,
                ),
                AssignmentFixtureStep(
                    step_id="after_hard_window_close",
                    timestamp_s=3.0,
                    tracks=hard_window_changed,
                    resources=hard_window_resources,
                    event_type="hard_window_change",
                    changed_track_ids=("T01",),
                    metadata={"closed_resource_id": "R01"},
                ),
            ),
            metadata={"resource_target_order": "resources_x_targets"},
        ),
    )


def p1_assignment_fixture_by_id(scenario_id: str) -> AssignmentScenarioFixture:
    """Return one P1 fixture by stable id."""

    fixtures = {fixture.scenario_id: fixture for fixture in build_p1_assignment_fixtures()}
    try:
        return fixtures[str(scenario_id)]
    except KeyError as exc:
        raise KeyError(f"unknown D3 assignment fixture: {scenario_id}") from exc


def _two_step_track_change_fixture(
    *,
    scenario_id: str,
    scenario_kind: str,
    tracks: tuple[TargetTrack, ...],
    resources: tuple[ResourceState, ...],
) -> AssignmentScenarioFixture:
    changed_track = replace(
        tracks[0],
        covariance=min(1.0, tracks[0].covariance + 0.15),
        metadata={**dict(tracks[0].metadata), "event": "track_state_update"},
    )
    return AssignmentScenarioFixture(
        scenario_id=scenario_id,
        scenario_kind=scenario_kind,
        steps=(
            AssignmentFixtureStep(
                step_id="baseline",
                timestamp_s=0.0,
                tracks=tracks,
                resources=resources,
            ),
            AssignmentFixtureStep(
                step_id="after_track_update",
                timestamp_s=3.0,
                tracks=(changed_track,) + tracks[1:],
                resources=resources,
                event_type="track_update",
                changed_track_ids=(changed_track.track_id,),
            ),
        ),
        metadata={"resource_target_order": "resources_x_targets"},
    )


def _feedback_tracks(*, reserve_replan: bool) -> tuple[TargetTrack, ...]:
    resource_ids = tuple(f"R{index:02d}" for index in range(1, 6))
    fov_values = (
        (0.0, 0.1, 0.5, 0.0, 1.0)
        if reserve_replan
        else (0.0, 0.1, 0.2, 0.8, 1.0)
    )
    return (
        TargetTrack(
            "T001",
            threat_score=0.95,
            covariance=0.1,
            window_cost=0.1,
            demand=TargetDemand(
                required_resource_count=3,
                primary_resource_count=2,
                coordination_mode="hybrid",
                required_capability_counts={"alpha": 1, "beta": 1},
            ),
            feasibility_by_resource={
                resource_id: resource_id != "R05" for resource_id in resource_ids
            },
            fov_difficulty_by_resource=dict(zip(resource_ids, fov_values)),
        ),
        TargetTrack(
            "T002",
            threat_score=0.50,
            covariance=0.1,
            window_cost=0.1,
            feasibility_by_resource={
                resource_id: resource_id == "R05" for resource_id in resource_ids
            },
        ),
    )


def _tracks(
    target_count: int,
    resource_count: int,
    *,
    threat_start: float = 0.60,
) -> tuple[TargetTrack, ...]:
    return tuple(
        _track(
            target_index=index,
            resource_count=resource_count,
            threat_score=min(0.95, threat_start + 0.05 * (index - 1)),
        )
        for index in range(1, target_count + 1)
    )


def _track(
    *,
    target_index: int,
    resource_count: int,
    threat_score: float,
    metadata: Mapping[str, Any] | None = None,
) -> TargetTrack:
    preferred_resource = ((target_index - 1) % resource_count) + 1
    return TargetTrack(
        track_id=f"T{target_index:02d}",
        threat_score=threat_score,
        covariance=0.10,
        window_cost=0.10,
        fov_difficulty_by_resource={
            f"R{resource_index:02d}": (
                0.0 if resource_index == preferred_resource else 0.80
            )
            for resource_index in range(1, resource_count + 1)
        },
        metadata=dict(metadata or {}),
    )


def _resources(resource_count: int) -> tuple[ResourceState, ...]:
    return tuple(
        ResourceState(
            resource_id=f"R{index:02d}",
            capability_class="interceptor",
        )
        for index in range(1, resource_count + 1)
    )
