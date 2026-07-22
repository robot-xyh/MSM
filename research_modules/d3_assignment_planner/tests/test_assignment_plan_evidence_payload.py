from __future__ import annotations

from dataclasses import asdict, replace
import json

import numpy as np
import pytest

from d3_assignment_planner import (
    ASSIGNMENT_COST_BREAKDOWNS_SCHEMA_V1,
    ASSIGNMENT_EVIDENCE_SCHEMA_V1,
    ASSIGNMENT_EVIDENCE_SCHEMA_V2,
    AssignmentPlanner,
    PlannerConfig,
    ResourceState,
    StalePlanError,
    TargetTrack,
    assignment_evidence_from_plan,
    canonical_cost_breakdowns_by_edge_sha256,
    validated_assignment_plan_payload_sha256,
)


def _tracks(count: int) -> tuple[TargetTrack, ...]:
    return tuple(
        TargetTrack(
            track_id=f"T-{index:03d}",
            threat_score=0.7,
            covariance=0.05,
            window_cost=0.0,
            position_ned=(float(index * 20), float((index % 8) * 200), -100.0),
            velocity_ned=(-2.0, 0.0, 0.0),
            position_covariance_ned=np.eye(3) * (1.0 + index * 0.01),
            region_id="ALL",
            candidate_resource_region_ids=("ALL",),
        )
        for index in range(count)
    )


def _resources(count: int) -> tuple[ResourceState, ...]:
    return tuple(
        ResourceState(
            resource_id=f"R-{index:03d}",
            position_ned=(float(index * 20), float((index % 8) * 200), -100.0),
            velocity_ned=(0.0, 0.0, 0.0),
            position_covariance_ned=np.eye(3) * 0.25,
            max_speed_mps=14.0,
            max_intercept_range_m=5_000.0,
            region_id="ALL",
            reachable_target_region_ids=("ALL",),
        )
        for index in range(count)
    )


def _planner(*, max_edges: int = 32) -> AssignmentPlanner:
    return AssignmentPlanner(
        config=PlannerConfig.scalable_3d(
            enable_hysteresis=False,
            max_candidate_edges_per_target=max_edges,
            human_authorization_state="approved",
            unassigned_base_cost=50.0,
        )
    )


def _serialized_plan_size(plan) -> int:
    return len(
        json.dumps(
            asdict(plan),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _legacy_dual_copy_plan(plan):
    metadata = dict(plan.metadata)
    edges = metadata["cost_breakdowns_by_edge"]
    metadata["current_plan_evidence_schema"] = ASSIGNMENT_EVIDENCE_SCHEMA_V1
    metadata["current_cost_breakdowns_by_edge"] = edges
    for key in (
        "cost_breakdowns_by_edge_schema",
        "cost_breakdowns_by_edge_count",
        "cost_breakdowns_by_edge_sha256",
        "cost_breakdowns_by_edge_storage",
        "current_cost_breakdowns_by_edge_ref",
    ):
        metadata.pop(key, None)
    return replace(plan, metadata=metadata)


def test_200v200_plan_payload_keeps_one_complete_cost_evidence_copy() -> None:
    plan = _planner().plan(_tracks(200), _resources(200), timestamp=0.0)
    metadata = plan.metadata
    edges = metadata["cost_breakdowns_by_edge"]

    assert len(edges) == 6_400
    assert metadata["candidate_full_edge_count"] == 40_000
    assert metadata["current_plan_evidence_schema"] == ASSIGNMENT_EVIDENCE_SCHEMA_V2
    assert metadata["cost_breakdowns_by_edge_schema"] == (
        ASSIGNMENT_COST_BREAKDOWNS_SCHEMA_V1
    )
    assert metadata["cost_breakdowns_by_edge_count"] == len(edges)
    assert metadata["cost_breakdowns_by_edge_sha256"] == (
        canonical_cost_breakdowns_by_edge_sha256(edges)
    )
    assert metadata["cost_breakdowns_by_edge_storage"] == (
        "inline_canonical_single_copy"
    )
    assert metadata["current_cost_breakdowns_by_edge_ref"] == (
        "cost_breakdowns_by_edge"
    )
    assert "current_cost_breakdowns_by_edge" not in metadata

    legacy = _legacy_dual_copy_plan(plan)
    current_size = _serialized_plan_size(plan)
    legacy_size = _serialized_plan_size(legacy)

    assert current_size < legacy_size
    assert (legacy_size - current_size) / legacy_size > 0.40
    assert plan.assignments == legacy.assignments
    assert plan.stable_signature == legacy.stable_signature
    assert plan.execution_signature() == legacy.execution_signature()
    assert (plan.plan_id, plan.version) == (legacy.plan_id, legacy.version)

    current_evidence = assignment_evidence_from_plan(plan)
    legacy_evidence = assignment_evidence_from_plan(legacy)
    assert current_evidence.cost_breakdowns_by_edge == (
        legacy_evidence.cost_breakdowns_by_edge
    )
    assert current_evidence.cost_breakdowns_by_edge_count == 6_400
    assert current_evidence.cost_breakdowns_by_edge_sha256 == (
        legacy_evidence.cost_breakdowns_by_edge_sha256
    )
    assert current_evidence.cost_breakdowns_by_edge_source_field == (
        "cost_breakdowns_by_edge"
    )
    assert validated_assignment_plan_payload_sha256(plan) != (
        validated_assignment_plan_payload_sha256(legacy)
    )


def test_legacy_current_cost_breakdown_alias_remains_readable() -> None:
    plan = _planner(max_edges=2).plan(_tracks(2), _resources(2), timestamp=0.0)
    expected_edges = tuple(plan.metadata["cost_breakdowns_by_edge"])
    metadata = dict(plan.metadata)
    metadata["current_plan_evidence_schema"] = ASSIGNMENT_EVIDENCE_SCHEMA_V1
    metadata["current_cost_breakdowns_by_edge"] = expected_edges
    metadata.pop("cost_breakdowns_by_edge")
    for key in (
        "cost_breakdowns_by_edge_schema",
        "cost_breakdowns_by_edge_count",
        "cost_breakdowns_by_edge_sha256",
        "cost_breakdowns_by_edge_storage",
        "current_cost_breakdowns_by_edge_ref",
    ):
        metadata.pop(key, None)

    evidence = assignment_evidence_from_plan(replace(plan, metadata=metadata))

    assert evidence.current_plan_evidence_schema == ASSIGNMENT_EVIDENCE_SCHEMA_V1
    assert evidence.cost_breakdowns_by_edge == expected_edges
    assert evidence.cost_breakdowns_by_edge_count == len(expected_edges)
    assert evidence.cost_breakdowns_by_edge_sha256 == (
        canonical_cost_breakdowns_by_edge_sha256(expected_edges)
    )
    assert evidence.cost_breakdowns_by_edge_storage == "legacy_alias_inline"
    assert evidence.cost_breakdowns_by_edge_source_field == (
        "current_cost_breakdowns_by_edge"
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("cost_breakdowns_by_edge_count", 999, "count mismatch"),
        ("cost_breakdowns_by_edge_sha256", "0" * 64, "SHA-256 mismatch"),
    ),
)
def test_v2_cost_evidence_rejects_audit_metadata_mismatch(
    field: str,
    value: object,
    message: str,
) -> None:
    plan = _planner(max_edges=2).plan(_tracks(2), _resources(2), timestamp=0.0)
    tampered = replace(
        plan,
        metadata={**dict(plan.metadata), field: value},
    )

    with pytest.raises(ValueError, match=message):
        assignment_evidence_from_plan(tampered)


def test_v2_cost_evidence_dedup_does_not_change_version_or_stale_semantics() -> None:
    planner = _planner(max_edges=2)
    tracks = _tracks(2)
    resources = _resources(2)
    first = planner.plan(tracks, resources, timestamp=0.0)

    with pytest.raises(StalePlanError) as exc_info:
        planner.plan(
            tracks,
            resources,
            timestamp=1.0,
            previous_plan=first,
            expected_previous_version=first.version + 1,
        )
    assert exc_info.value.reason == "expected_previous_version_mismatch"

    refreshed = planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=first,
        expected_previous_version=first.version,
    )

    assert (refreshed.plan_id, refreshed.version) == (first.plan_id, first.version)
    assert refreshed.execution_signature() == first.execution_signature()
    assert refreshed.metadata["current_plan_evidence_schema"] == (
        ASSIGNMENT_EVIDENCE_SCHEMA_V2
    )
    assert "current_cost_breakdowns_by_edge" not in refreshed.metadata
