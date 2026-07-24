from __future__ import annotations
from commitment_test_support import committed_target_track

from dataclasses import replace

import numpy as np
import pytest

from d3_assignment_planner import (
    AssignmentPlanner,
    CostModel,
    CostWeights,
    HungarianAssignmentSolver,
    LearningAssistConfig,
    LearningCostAssistant,
    PlannerConfig,
    RegionalAuthorityGrant,
    RegionalAuthorityInput,
    RegionalPlanAuthorityError,
    ResourceState,
    StalePlanError,
    TargetTrack,
    build_latest_learning_frame_record,
)
from d3_assignment_planner.learning import ResidualPrediction


class _FixedPredictor:
    def __init__(self, delta: float, confidence: float = 0.99) -> None:
        self.delta = float(delta)
        self.confidence = float(confidence)

    def predict(self, features: np.ndarray) -> ResidualPrediction:
        return ResidualPrediction(
            delta_costs=np.full(features.shape[0], self.delta, dtype=float),
            confidence=self.confidence,
        )


def _tracks(count: int) -> tuple[TargetTrack, ...]:
    return tuple(
        committed_target_track(
            f"internal-target-{index}",
            threat_score=0.9 - 0.02 * index,
            covariance=0.1,
            window_cost=0.0,
            fov_difficulty_by_resource={
                f"internal-resource-{resource_index}": abs(index - resource_index)
                / max(1, count)
                for resource_index in range(max(1, count))
            },
            metadata={
                "truth_id": f"truth-{index}",
                "target_actor_name": f"actor-{index}",
                "object_id": f"object-{index}",
            },
        )
        for index in range(count)
    )


def _resources(count: int) -> tuple[ResourceState, ...]:
    return tuple(
        ResourceState(
            f"internal-resource-{index}",
            metadata={
                "resource_actor_name": f"vehicle-actor-{index}",
                "object_id": f"vehicle-object-{index}",
            },
        )
        for index in range(count)
    )


def _fov_planner(config: PlannerConfig) -> AssignmentPlanner:
    weights = CostWeights(
        window=0.0,
        covariance=0.0,
        threat=0.0,
        resource_state=0.0,
        fov=1.0,
        conflict=0.0,
        reachability_3d=0.0,
        region=0.0,
    )
    return AssignmentPlanner(
        cost_model=CostModel(weights=weights, config=config),
        solver=HungarianAssignmentSolver(allow_scipy=False),
        config=config,
    )


def test_initial_plan_exposes_one_anonymous_read_only_frame_and_public_helper() -> None:
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))
    tracks = _tracks(2)
    resources = _resources(3)

    plan = planner.plan(tracks, resources, timestamp=4.5)
    evidence = planner.latest_planning_evidence
    record = build_latest_learning_frame_record(
        planner,
        scenario_version="episode-contract-v1",
        seed=17,
        episode="episode-3",
        frame_index=0,
    )

    assert evidence.available is True
    assert evidence.reason == "available"
    assert evidence.planning_path == "central_plan"
    assert evidence.selection_source == "central_solver"
    assert evidence.plan_id == plan.plan_id
    assert evidence.plan_version == plan.version == 1
    assert evidence.previous_plan_version == 0
    assert evidence.timestamp_s == 4.5
    assert evidence.rule_matrix is not evidence.effective_matrix
    assert np.array_equal(evidence.rule_matrix, evidence.effective_matrix)
    assert evidence.rule_matrix.flags.writeable is False
    assert evidence.effective_matrix.flags.writeable is False
    assert evidence.learning_state == "rule_only"
    assert tuple(item.track_id for item in evidence.tracks) == (
        "target_0000",
        "target_0001",
    )
    assert tuple(item.resource_id for item in evidence.resources) == (
        "resource_0000",
        "resource_0001",
        "resource_0002",
    )
    assert "truth-" not in repr(evidence)
    assert "actor-" not in repr(evidence)
    assert "object-" not in repr(evidence)
    assert "planning_evidence" not in plan.metadata
    assert record.timestamp_s == 4.5
    assert record.previous_plan_version == 0
    assert [item["token"] for item in record.anonymous_targets] == [
        "target_0000",
        "target_0001",
    ]
    assert [item["token"] for item in record.anonymous_resources] == [
        "resource_0000",
        "resource_0001",
        "resource_0002",
    ]


def test_held_unchanged_and_forced_replan_frames_replace_previous_evidence() -> None:
    config = PlannerConfig(enable_hysteresis=True, delta=0.2, min_dwell=2.0)
    planner = _fov_planner(config)
    resources = (ResourceState("R1"), ResourceState("R2"))
    initial = (
        committed_target_track("T1", 0.9, 0.1, 0.0, fov_difficulty_by_resource={"R1": 0.0, "R2": 1.0}),
        committed_target_track("T2", 0.8, 0.1, 0.0, fov_difficulty_by_resource={"R1": 1.0, "R2": 0.0}),
    )
    shifted = (
        replace(initial[0], fov_difficulty_by_resource={"R1": 0.8, "R2": 0.0}),
        replace(initial[1], fov_difficulty_by_resource={"R1": 0.0, "R2": 0.8}),
    )

    first = planner.plan(initial, resources, timestamp=0.0)
    first_evidence = planner.latest_planning_evidence
    unchanged = planner.plan(
        initial,
        resources,
        timestamp=0.5,
        previous_plan=first,
    )
    unchanged_evidence = planner.latest_planning_evidence
    forced = planner.plan(
        initial,
        resources,
        timestamp=0.75,
        previous_plan=unchanged,
        forced_replan=True,
    )
    forced_evidence = planner.latest_planning_evidence
    held = planner.plan(shifted, resources, timestamp=1.0, previous_plan=forced)
    held_evidence = planner.latest_planning_evidence

    assert held.decision_state == "held_by_hysteresis"
    assert held_evidence.available is True
    assert held_evidence.timestamp_s == 1.0
    assert held_evidence.plan_id == held.plan_id
    assert held_evidence.previous_plan_version == forced.version
    assert unchanged.changed is False
    assert unchanged_evidence.available is True
    assert unchanged_evidence.timestamp_s == 0.5
    assert forced.decision_state == "replan_ack_no_change"
    assert forced_evidence.available is True
    assert forced_evidence.timestamp_s == 0.75
    assert forced_evidence.forced_replan is True
    assert held_evidence.forced_replan is False
    assert forced_evidence.plan.metadata["plan_owner"] == "center"
    assert forced_evidence.plan.metadata["owner_node_id"] == "node_0000"
    assert forced_evidence.previous_plan.metadata["owner_node_id"] == "node_0000"
    assert first_evidence is not unchanged_evidence
    assert unchanged_evidence is not forced_evidence
    assert forced_evidence is not held_evidence


@pytest.mark.parametrize(
    ("mode", "confidence", "expected_state", "expected_fallback"),
    (
        ("shadow", 0.99, "shadow_proposal", None),
        ("assist", 0.99, "assist_effective", None),
        ("assist", 0.1, "rule_fallback", "low_confidence"),
    ),
)
def test_learning_evidence_distinguishes_shadow_assist_and_fallback(
    mode: str,
    confidence: float,
    expected_state: str,
    expected_fallback: str | None,
) -> None:
    config = PlannerConfig.scalable_3d(
        enable_hysteresis=False,
        max_candidate_edges_per_target=2,
    )
    planner = AssignmentPlanner(
        config=config,
        solver=HungarianAssignmentSolver(allow_scipy=False),
        learning_assistant=LearningCostAssistant(
            _FixedPredictor(-1.0, confidence=confidence),
            config=LearningAssistConfig(
                mode=mode,
                alpha=0.4,
                min_confidence=0.8,
            ),
        ),
    )
    tracks = (
        committed_target_track(
            "T",
            0.9,
            0.1,
            0.0,
            position_ned=(100.0, 0.0, -100.0),
            velocity_ned=(0.0, 0.0, 0.0),
            region_id="A",
        ),
    )
    resources = (
        ResourceState("R1", position_ned=(0.0, 0.0, -100.0), max_speed_mps=20.0, region_id="A"),
        ResourceState("R2", position_ned=(10.0, 0.0, -100.0), max_speed_mps=20.0, region_id="A"),
    )

    plan = planner.plan(tracks, resources, timestamp=0.0)
    evidence = planner.latest_planning_evidence

    assert evidence.available is True
    assert evidence.learning_mode == mode
    assert evidence.learning_state == expected_state
    assert evidence.fallback_reason == expected_fallback
    assert evidence.solver_name == plan.solver_name == "fallback_dp"
    if expected_state == "shadow_proposal":
        assert np.array_equal(evidence.rule_matrix, evidence.effective_matrix)
        assert evidence.shadow_proposal_matrix is not None
        assert not np.array_equal(evidence.rule_matrix, evidence.shadow_proposal_matrix)
    elif expected_state == "assist_effective":
        assert not np.array_equal(evidence.rule_matrix, evidence.effective_matrix)
        assert evidence.shadow_proposal_matrix is None
    else:
        assert np.array_equal(evidence.rule_matrix, evidence.effective_matrix)
        assert evidence.shadow_proposal_matrix is None


def test_failed_plan_clears_prior_evidence_and_helper_refuses_stale_frame() -> None:
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))
    tracks = _tracks(1)
    resources = _resources(1)
    planner.plan(tracks, resources, timestamp=0.0)

    with pytest.raises(StalePlanError):
        planner.plan(tracks, resources, timestamp=1.0)

    evidence = planner.latest_planning_evidence
    assert evidence.available is False
    assert evidence.reason == "central_plan_failed:previous_plan_required"
    assert evidence.rule_matrix_result is None
    assert evidence.plan is None
    with pytest.raises(RuntimeError, match="previous_plan_required"):
        build_latest_learning_frame_record(
            planner,
            scenario_version="v1",
            seed=1,
            episode="episode",
            frame_index=1,
        )


def test_regional_frame_is_recordable_and_rejected_authority_clears_it() -> None:
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))
    tracks = (committed_target_track("T", 0.9, 0.1, 0.0),)
    resources = (ResourceState("R"),)
    previous = planner.plan(tracks, resources, timestamp=0.0)
    grant = RegionalAuthorityGrant(
        region_id="A",
        owner_layer="secondary",
        owner_node_id="secondary-node",
        owner_role="mobile_high_recon",
        epoch=previous.version,
        source_plan_id=previous.plan_id,
        source_plan_version=previous.version,
        lease_expires_at_s=10.0,
        target_ids=("T",),
        assigned_resource_ids_by_target={"T": ("R",)},
    )
    regional = planner.plan_regional_authority(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        authority=RegionalAuthorityInput(1.0, (grant,)),
        expected_previous_version=previous.version,
    )
    regional_evidence = planner.latest_planning_evidence

    assert regional_evidence.available is True
    assert regional_evidence.planning_path == "regional_authority"
    assert regional_evidence.selection_source == "regional_authority"
    assert regional_evidence.plan_id == regional.plan_id
    assert regional_evidence.previous_plan_version == previous.version

    bad_grant = replace(
        grant,
        epoch=regional.version,
        source_plan_id=regional.plan_id,
        source_plan_version=regional.version,
        target_ids=("OTHER",),
        assigned_resource_ids_by_target={"OTHER": ("R",)},
    )
    with pytest.raises(RegionalPlanAuthorityError):
        planner.plan_regional_authority(
            tracks,
            resources,
            timestamp=2.0,
            previous_plan=regional,
            authority=RegionalAuthorityInput(2.0, (bad_grant,)),
            expected_previous_version=regional.version,
        )

    unavailable = planner.latest_planning_evidence
    assert unavailable.available is False
    assert unavailable.reason == (
        "regional_authority_failed:regional_authority_target_set_mismatch"
    )
    assert unavailable.plan_id is None
    assert unavailable.rule_matrix is None


def test_external_changes_cannot_mutate_planner_inputs_or_retained_snapshot() -> None:
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))
    tracks = list(_tracks(1))
    resources = list(_resources(2))
    plan = planner.plan(tracks, resources, timestamp=0.0)
    evidence = planner.latest_planning_evidence
    original_cost = float(evidence.rule_matrix[0, 0])

    tracks[0].metadata["truth_id"] = "changed-after-plan"
    resources[0].metadata["object_id"] = "changed-after-plan"
    plan.metadata["caller_mutation"] = True
    with pytest.raises(ValueError):
        evidence.rule_matrix[0, 0] = original_cost + 100.0
    with pytest.raises(ValueError):
        evidence.rule_matrix.setflags(write=True)
    with pytest.raises(TypeError):
        evidence.tracks[0].metadata["truth_id"] = "forbidden"
    with pytest.raises(TypeError):
        evidence.plan.metadata["truth_id"] = "forbidden"

    record = build_latest_learning_frame_record(
        planner,
        scenario_version="v1",
        seed=1,
        episode="episode",
        frame_index=0,
    )
    record.rule_cost_matrix[0, 0] = original_cost + 200.0
    assert planner.latest_planning_evidence.rule_matrix[0, 0] == original_cost
    assert "changed-after-plan" not in repr(planner.latest_planning_evidence)


@pytest.mark.parametrize("target_count,resource_count", ((1, 3), (3, 2), (7, 4)))
def test_evidence_shape_follows_runtime_roster_without_fixed_scale(
    target_count: int,
    resource_count: int,
) -> None:
    planner = AssignmentPlanner(config=PlannerConfig(enable_hysteresis=False))

    planner.plan(
        _tracks(target_count),
        _resources(resource_count),
        timestamp=0.0,
    )
    evidence = planner.latest_planning_evidence

    assert evidence.available is True
    assert evidence.rule_matrix.shape == (target_count, resource_count)
    assert evidence.effective_matrix.shape == (target_count, resource_count)
    assert len(evidence.tracks) == target_count
    assert len(evidence.resources) == resource_count
