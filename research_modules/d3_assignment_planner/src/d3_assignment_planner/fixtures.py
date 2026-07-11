"""Deterministic D3 P1 fixtures for N/M and feedback governance calibration."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from .models import ResourceState, TargetTrack


P1_ASSIGNMENT_FIXTURE_SCHEMA = "d3_assignment_fixture_v1"
P1_ASSIGNMENT_FIXTURE_PROFILE_ID = "d3_p1_nm_feedback_governance"
P1_ASSIGNMENT_FIXTURE_PROFILE_VERSION = "1.0.0"


@dataclass(frozen=True)
class AssignmentFixtureStep:
    """One deterministic planner input snapshot within a fixture."""

    step_id: str
    timestamp_s: float
    tracks: tuple[TargetTrack, ...]
    resources: tuple[ResourceState, ...]
    event_type: str = "baseline"
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
                }
                for step in self.steps
            ),
            **dict(self.metadata),
        }


def build_p1_assignment_fixtures() -> tuple[AssignmentScenarioFixture, ...]:
    """Return 5v5, 3v5, 5v3, target-arrival, and resource-failure fixtures.

    Scenario names use ``resources x targets`` ordering. Counts are repeated in
    metadata so consumers never need to infer that convention from the label.
    """

    five_resources = _resources(5)
    five_targets = _tracks(5, 5)
    three_resources = _resources(3)
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

    return (
        _single_step_fixture(
            scenario_id="5v5",
            scenario_kind="equal_nm",
            tracks=five_targets,
            resources=five_resources,
        ),
        _single_step_fixture(
            scenario_id="3v5",
            scenario_kind="resource_shortage",
            tracks=five_targets,
            resources=three_resources,
        ),
        _single_step_fixture(
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
                    metadata={"failed_resource_id": "R03"},
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


def _single_step_fixture(
    *,
    scenario_id: str,
    scenario_kind: str,
    tracks: tuple[TargetTrack, ...],
    resources: tuple[ResourceState, ...],
) -> AssignmentScenarioFixture:
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
        ),
        metadata={"resource_target_order": "resources_x_targets"},
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
