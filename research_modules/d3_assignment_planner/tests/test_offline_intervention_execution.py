from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pytest

from d3_assignment_planner import (
    CONTROL_ARM,
    CONTROL_PLANNER_PATH,
    D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1,
    D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1,
    D6_SIDECAR_OWNER,
    EDGE_FEATURE_NAMES,
    OFFLINE_INTERVENTION_SCOPE,
    PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1,
    PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
    SHADOW_EVALUATION_SCHEMA_V2,
    TREATMENT_ARM,
    TREATMENT_PLANNER_PATH,
    Assignment,
    AssignmentPlan,
    AssignmentPlanRuntimeAckError,
    AssignmentPlanner,
    CostModel,
    CostWeights,
    DemandSatisfactionSummary,
    HungarianAssignmentSolver,
    PairedInterventionArmSpecification,
    PairedInterventionContractError,
    PairedInterventionSeedPair,
    PairedInterventionSpecification,
    PlannerConfig,
    ResourceState,
    RegionalAuthorityGrant,
    RegionalAuthorityInput,
    RegionalCoalitionCommitEvidence,
    SharedEdgeActorCriticPolicy,
    TargetDemand,
    TargetTrack,
    build_isolated_execution_plan,
    build_isolated_plan_consumption_evidence,
    canonical_planning_frame_snapshot_sha256,
    development_shadow_admission,
    execute_offline_paired_intervention,
    load_model_bundle,
    prepare_secondary_takeover_plan,
    save_model_bundle,
    validated_assignment_plan_payload_sha256,
    write_offline_paired_intervention_execution,
)
from d3_assignment_planner.offline_intervention_execution import (
    _normalize_isolated_plan_target_inventory,
    _recorded_regional_authority_input,
)
from d3_assignment_planner.planning_evidence import (
    canonical_recorded_authority_transition_sha256,
)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _bundle(
    path: Path,
    *,
    deadline_s: float = 1.0,
    normalization_mean: float = 0.0,
    normalization_scale: float = 1.0,
) -> None:
    torch = pytest.importorskip("torch")
    torch.manual_seed(7)
    save_model_bundle(
        path,
        SharedEdgeActorCriticPolicy(hidden_size=8),
        split_hash="1" * 64,
        dataset_frames_sha256="2" * 64,
        normalization_mean=np.full(
            len(EDGE_FEATURE_NAMES), normalization_mean, dtype=float
        ),
        normalization_scale=np.full(
            len(EDGE_FEATURE_NAMES), normalization_scale, dtype=float
        ),
        training_results={"stage": "development_unit_fixture"},
        deadline_s=deadline_s,
        min_confidence=0.0,
        provenance={
            "repository_git_commit": "a" * 40,
            "repository_git_commit_role": "exact_training_source_commit",
            "training_worktree_state": "clean",
            "training_source_sha256": "3" * 64,
            "dataset_manifest_sha256": "4" * 64,
            "training_entrypoint": "unit_fixture",
            "training_date": "2026-07-21",
        },
        admission=development_shadow_admission(
            PAIRED_INTERVENTION_RESERVED_SEEDS_V1
        ),
        promotion_unavailable_reason="reserved_seed_evaluation_pending",
    )


def _planning_frames(
    config: PlannerConfig,
) -> dict[int, object]:
    frames = {}
    for offset, seed in enumerate(PAIRED_INTERVENTION_RESERVED_SEEDS_V1):
        planner = AssignmentPlanner(config=config)
        tracks = (
            TargetTrack(
                f"global-track-{seed}-a",
                threat_score=0.9,
                covariance=0.1 + offset * 0.001,
                window_cost=0.0,
                fov_difficulty_by_resource={
                    f"resource-{seed}-a": 0.0,
                    f"resource-{seed}-b": 0.8,
                },
            ),
            TargetTrack(
                f"global-track-{seed}-b",
                threat_score=0.6,
                covariance=0.2,
                window_cost=0.0,
                fov_difficulty_by_resource={
                    f"resource-{seed}-a": 0.8,
                    f"resource-{seed}-b": 0.0,
                },
            ),
        )
        resources = (
            ResourceState(f"resource-{seed}-a"),
            ResourceState(f"resource-{seed}-b"),
        )
        previous = planner.plan(tracks, resources, timestamp=10.0)
        planner.plan(
            tracks,
            resources,
            timestamp=12.0,
            previous_plan=previous,
            expected_previous_version=previous.version,
        )
        frames[seed] = planner.latest_planning_evidence
    return frames


_HELD_5V5_SEEDS = frozenset({1002, 1009, 1017})
_FORCED_REPLAN_4_TO_5_SEEDS = frozenset({1011, 1019})
_REMOVED_TARGET_SEED = 1005


def _realistic_tracks(
    seed: int,
    count: int,
    *,
    shifted: bool = False,
) -> tuple[TargetTrack, ...]:
    resource_ids = tuple(f"interceptor-{seed}-{index}" for index in range(5))
    return tuple(
        TargetTrack(
            f"global-track-{seed}-{index}",
            threat_score=0.20 + 0.01 * index,
            covariance=0.1 + 0.01 * index,
            window_cost=0.0,
            fov_difficulty_by_resource={
                resource_id: (
                    0.0
                    if resource_index
                    == ((index + 1) % 5 if shifted else index)
                    else 1.0
                )
                for resource_index, resource_id in enumerate(resource_ids)
            },
            metadata={
                "truth_id": f"truth-{seed}-{index}",
                "target_actor_name": f"actor-{seed}-{index}",
            },
        )
        for index in range(count)
    )


def _realistic_resources(seed: int) -> tuple[ResourceState, ...]:
    return tuple(
        ResourceState(
            f"interceptor-{seed}-{index}",
            metadata={"object_id": f"vehicle-object-{seed}-{index}"},
        )
        for index in range(5)
    )


def _realistic_five_by_five_frames(
    *,
    secondary_takeover: bool = False,
) -> tuple[
    PlannerConfig,
    CostWeights,
    dict[int, object],
]:
    config = PlannerConfig(
        enable_hysteresis=True,
        delta=0.2,
        min_dwell=2.0,
        human_authorization_state="approved",
        source_node_id="private-center-node",
    )
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
    frames: dict[int, object] = {}
    for seed in PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
        planner = AssignmentPlanner(
            cost_model=CostModel(weights=weights, config=config),
            solver=HungarianAssignmentSolver(allow_scipy=False),
            config=config,
        )
        initial_count = (
            5
            if secondary_takeover
            else (4 if seed in _FORCED_REPLAN_4_TO_5_SEEDS else 5)
        )
        previous = planner.plan(
            _realistic_tracks(seed, initial_count),
            _realistic_resources(seed),
            timestamp=0.0,
        )
        current_count = (
            5
            if secondary_takeover
            else (4 if seed == _REMOVED_TARGET_SEED else 5)
        )
        candidate = planner.plan(
            _realistic_tracks(
                seed,
                current_count,
                shifted=(
                    False
                    if secondary_takeover
                    else seed in _HELD_5V5_SEEDS
                ),
            ),
            _realistic_resources(seed),
            timestamp=1.0,
            previous_plan=previous,
            expected_previous_version=previous.version,
            forced_replan=(
                secondary_takeover
                or seed in _FORCED_REPLAN_4_TO_5_SEEDS
            ),
            publish=not secondary_takeover,
        )
        if secondary_takeover:
            planner.publish_plan(
                prepare_secondary_takeover_plan(
                    candidate,
                    supersedes_plan=previous,
                    secondary_node_id="recon-secondary-node",
                    readiness_class="takeover_ready",
                    readiness_sustained=True,
                    activated_at_s=1.0,
                    lease_expires_at_s=6.0,
                    leader_epoch=previous.version + 1,
                )
            )
        frames[seed] = planner.latest_planning_evidence
    return config, weights, frames


def _regional_replay_frames() -> tuple[
    PlannerConfig,
    CostWeights,
    dict[int, object],
]:
    config = PlannerConfig(
        enable_hysteresis=False,
        human_authorization_state="approved",
        source_node_id="regional-unit-center",
    )
    weights = CostWeights()
    frames: dict[int, object] = {}
    for seed in PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
        planner = AssignmentPlanner(
            cost_model=CostModel(weights=weights, config=config),
            solver=HungarianAssignmentSolver(allow_scipy=False),
            config=config,
        )
        tracks = _realistic_tracks(seed, 5)
        resources = _realistic_resources(seed)
        pending_inventory = seed in _FORCED_REPLAN_4_TO_5_SEEDS
        solve_tracks = tracks[:4] if pending_inventory else tracks
        previous = planner.plan(solve_tracks, resources, timestamp=0.0)
        candidate = planner.plan(
            solve_tracks,
            resources,
            timestamp=1.0,
            previous_plan=previous,
            expected_previous_version=previous.version,
            forced_replan=True,
            publish=False,
        )
        secondary = prepare_secondary_takeover_plan(
            candidate,
            supersedes_plan=previous,
            secondary_node_id=f"regional-secondary-{seed}",
            readiness_class="takeover_ready",
            readiness_sustained=True,
            activated_at_s=1.0,
            lease_expires_at_s=8.0,
            leader_epoch=candidate.version,
        )
        if pending_inventory:
            pending_target = tracks[-1]
            secondary = replace(
                secondary,
                target_count=5,
                unassigned_target_ids=(pending_target.track_id,),
                incomplete_target_ids=(pending_target.track_id,),
                demand_summaries=(
                    *secondary.demand_summaries,
                    DemandSatisfactionSummary(
                        target_id=pending_target.track_id,
                        demand_required=1,
                        demand_assigned=0,
                        demand_shortfall=1,
                        coalition_complete=False,
                    ),
                ),
            )
        validated_assignment_plan_payload_sha256(secondary)
        secondary = planner.publish_plan(secondary)
        coalition_by_target = {
            item.target_id: item for item in secondary.coalitions
        }
        grants = []
        for index, (target_id, assignments) in enumerate(
            secondary.assignments_by_target().items()
        ):
            resource_ids = tuple(item.resource_id for item in assignments)
            coalition = coalition_by_target[target_id]
            grants.append(
                RegionalAuthorityGrant(
                    region_id=f"region-{index:03d}",
                    owner_layer="secondary",
                    owner_node_id=f"regional-secondary-{seed}",
                    owner_role="secondary_owner",
                    epoch=secondary.version,
                    source_plan_id=secondary.plan_id,
                    source_plan_version=secondary.version,
                    lease_expires_at_s=8.0,
                    target_ids=(target_id,),
                    assigned_resource_ids_by_target={
                        target_id: resource_ids,
                    },
                    coalition_commits=(
                        RegionalCoalitionCommitEvidence(
                            target_id=target_id,
                            coordinator_id=f"regional-secondary-{seed}",
                            epoch=secondary.version,
                            lease_expires_at_s=8.0,
                            required_member_ids=resource_ids,
                            acked_member_ids=resource_ids,
                            commit_required=False,
                            state="single_member_authorized",
                            atomic_committed=False,
                            execution_authorized=True,
                            coalition_id=coalition.coalition_id,
                            coalition_version=coalition.version,
                        ),
                    ),
                )
            )
        planner.plan_regional_authority(
            tracks,
            resources,
            timestamp=2.0,
            previous_plan=secondary,
            authority=RegionalAuthorityInput(
                adjudicated_at_s=1.5,
                grants=tuple(grants),
            ),
            expected_previous_version=secondary.version,
        )
        frames[seed] = planner.latest_planning_evidence
    return config, weights, frames


def _replace_recorded_regional_plan(frame: object, plan: AssignmentPlan) -> object:
    assert frame.previous_plan is not None
    transition_sha256 = canonical_recorded_authority_transition_sha256(
        planning_path=frame.planning_path,
        selection_source=frame.selection_source,
        timestamp_s=frame.timestamp_s,
        plan=plan,
        previous_plan=frame.previous_plan,
    )
    return replace(
        frame,
        plan=plan,
        recorded_authority_transition_sha256=transition_sha256,
    )


@pytest.fixture(scope="module")
def regional_replay_contract_fixture() -> tuple[
    PlannerConfig,
    CostWeights,
    dict[int, object],
]:
    return _regional_replay_frames()


def _target_inventory_diagnostic(plan: AssignmentPlan) -> dict[str, object]:
    return {
        "class_identity": f"{type(plan).__module__}.{type(plan).__name__}",
        "target_count": plan.target_count,
        "assignment_target_ids": tuple(
            sorted({item.target_id for item in plan.assignments})
        ),
        "unassigned_target_ids": plan.unassigned_target_ids,
        "incomplete_target_ids": plan.incomplete_target_ids,
        "coalition_target_ids": tuple(
            item.target_id for item in plan.coalitions
        ),
        "demand_summaries": tuple(
            (
                item.target_id,
                item.demand_required,
                item.demand_assigned,
                item.demand_shortfall,
                item.coalition_complete,
            )
            for item in plan.demand_summaries
        ),
    }


def test_isolated_inventory_keeps_unassignable_and_drops_old_diagnostics() -> None:
    plan = AssignmentPlan(
        plan_id="offline-inventory-fixture",
        version=1,
        window_id=1,
        assignments=(
            Assignment(
                target_id="target-current-assigned",
                resource_id="resource-0",
                cost=1.0,
                cost_breakdown={"rule": 1.0},
            ),
        ),
        unassigned_target_ids=("target-previous-only",),
        incomplete_target_ids=("target-previous-only",),
        demand_summaries=(
            DemandSatisfactionSummary(
                target_id="target-previous-only",
                demand_required=1,
                demand_assigned=0,
                demand_shortfall=1,
                coalition_complete=False,
            ),
        ),
        total_cost=1.0,
        created_at=0.0,
        last_changed_at=0.0,
        resource_count=1,
        target_count=2,
    )
    normalized = _normalize_isolated_plan_target_inventory(
        plan,
        current_tracks=(
            TargetTrack("target-current-assigned", 0.4, 0.1, 0.0),
            TargetTrack(
                "target-current-unassignable",
                0.9,
                0.2,
                0.0,
                assignable=False,
            ),
        ),
    )

    assert normalized.unassigned_target_ids == (
        "target-current-unassignable",
    )
    assert normalized.incomplete_target_ids == (
        "target-current-unassignable",
    )
    assert tuple(item.target_id for item in normalized.demand_summaries) == (
        "target-current-assigned",
        "target-current-unassignable",
    )
    assert normalized.metadata[
        "isolated_target_inventory_removed_previous_only_ids"
    ] == ("target-previous-only",)
    validated_assignment_plan_payload_sha256(normalized)


def test_isolated_inventory_marks_partial_coalition_once_as_incomplete() -> None:
    target_id = "target-high-threat"
    plan = AssignmentPlan(
        plan_id="offline-partial-coalition-fixture",
        version=1,
        window_id=1,
        assignments=tuple(
            Assignment(
                target_id=target_id,
                resource_id=f"resource-{index}",
                cost=1.0,
                cost_breakdown={"rule": 1.0},
                required_resource_count=3,
            )
            for index in range(2)
        ),
        unassigned_target_ids=(),
        incomplete_target_ids=(),
        demand_summaries=(
            DemandSatisfactionSummary(
                target_id=target_id,
                demand_required=3,
                demand_assigned=2,
                demand_shortfall=1,
                coalition_complete=False,
                primary_resource_count=2,
            ),
        ),
        total_cost=2.0,
        created_at=0.0,
        last_changed_at=0.0,
        resource_count=3,
        target_count=1,
    )
    normalized = _normalize_isolated_plan_target_inventory(
        plan,
        current_tracks=(
            TargetTrack(
                target_id,
                0.95,
                0.1,
                0.0,
                demand=TargetDemand(
                    required_resource_count=3,
                    primary_resource_count=2,
                ),
            ),
        ),
    )

    assert normalized.unassigned_target_ids == ()
    assert normalized.incomplete_target_ids == (target_id,)
    assert normalized.target_count == 1
    assert len(normalized.demand_summaries) == 1
    assert normalized.demand_summaries[0].demand_shortfall == 1
    validated_assignment_plan_payload_sha256(normalized)


def _specification(
    *,
    bundle_dir: Path,
    frames: dict[int, object],
    manifest_sha256: str | None = None,
    policy_version: str | None = None,
) -> PairedInterventionSpecification:
    raw = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    bundle_sha = manifest_sha256 or _file_digest(bundle_dir / "manifest.json")
    bundle_version = policy_version or str(raw["policy_version"])
    pairs = []
    for seed in PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
        frame = frames[seed]
        assert frame.previous_plan is not None
        common = {
            "seed": seed,
            "intervention_scope": OFFLINE_INTERVENTION_SCOPE,
            "scenario_version": "scalable3d-d3-reserved-unit-v1",
            "scenario_config_sha256": _digest(f"scenario-{seed}"),
            "initial_world_state_sha256": _digest(f"world-{seed}"),
            "observation_input_snapshot_sha256": (
                canonical_planning_frame_snapshot_sha256(frame)
            ),
            "input_snapshot_schema_version": frame.schema_version,
            "d1_d2_lineage_contract_version": "d1-d2-lineage-v1",
            "d1_d2_lineage_contract_sha256": _digest("d1-d2-lineage"),
            "rule_cost_profile_version": "d3-rule-cost-v1",
            "rule_cost_config_sha256": _digest("rule-cost-config"),
            "d3_bundle_version": bundle_version,
            "d3_bundle_sha256": bundle_sha,
            "d3_bundle_frozen": True,
            "threshold_version": "d3-threshold-v1",
            "threshold_config_sha256": _digest("threshold-config"),
            "threshold_frozen": True,
            "safety_shell_version": "d3-safety-shell-v1",
            "safety_shell_config_sha256": _digest("safety-shell"),
            "source_plan_id": frame.previous_plan.plan_id,
            "source_plan_version": frame.previous_plan.version,
            "expected_previous_plan_version": frame.previous_plan.version,
            "current_plan_version": frame.previous_plan.version,
            "source_plan_created_at_s": frame.previous_plan.created_at,
            "intervention_timestamp_s": frame.timestamp_s,
            "plan_valid_until_s": 15.0,
            "ppo_enabled": False,
            "online_assist_enabled": False,
            "online_authority_enabled": False,
            "rule_fallback_enabled": True,
        }
        control = PairedInterventionArmSpecification(
            arm_id=f"d3-{seed}-control",
            arm_kind=CONTROL_ARM,
            isolation_id=f"world-{seed}-control",
            planner_path=CONTROL_PLANNER_PATH,
            learning_cost_intervention_enabled=False,
            **common,
        )
        treatment = PairedInterventionArmSpecification(
            arm_id=f"d3-{seed}-treatment",
            arm_kind=TREATMENT_ARM,
            isolation_id=f"world-{seed}-treatment",
            planner_path=TREATMENT_PLANNER_PATH,
            learning_cost_intervention_enabled=True,
            **common,
        )
        pairs.append(
            PairedInterventionSeedPair(
                pair_id=f"d3-pair-{seed}",
                seed=seed,
                control=control,
                treatment=treatment,
            )
        )
    return PairedInterventionSpecification(
        experiment_id="d3-reserved-unit",
        experiment_version="d3-reserved-unit-v1",
        reserved_seed_policy_version=PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1,
        reserved_seeds=PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
        paired_evaluator_schema_version=SHADOW_EVALUATION_SCHEMA_V2,
        runtime_ack_evidence_schema_version=D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1,
        runtime_reward_evidence_schema_version=(
            D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1
        ),
        d6_sidecar_owner=D6_SIDECAR_OWNER,
        ppo_enabled=False,
        online_assist_enabled=False,
        online_authority_enabled=False,
        rule_fallback_enabled=True,
        pairs=tuple(pairs),
    )


def test_reserved_seed_execution_creates_real_shared_report_receipts(
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "bundle"
    _bundle(bundle_dir)
    config = PlannerConfig(enable_hysteresis=False)
    frames = _planning_frames(config)
    specification = _specification(bundle_dir=bundle_dir, frames=frames)

    result = execute_offline_paired_intervention(
        specification,
        frames,
        bundle_dir=bundle_dir,
        planner_config=config,
    )
    output = tmp_path / "execution.json"
    write_offline_paired_intervention_execution(output, result)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert result.bundle_loaded is True
    assert len(result.arms) == 40
    assert result.paired_evaluator_report.frame_count == 20
    assert result.paired_evaluator_report.unseen_seed_count == 20
    assert len(result.manifest.execution_receipts) == 40
    assert {
        item.receipt.paired_evaluator_report_sha256 for item in result.arms
    } == {result.paired_evaluator_report_sha256}
    assert all(
        item.learning_cost_applied
        for item in result.arms
        if item.arm_specification.arm_kind == TREATMENT_ARM
    )
    assert all(
        item.plan.metadata["learning_bundle_loaded_for_offline_intervention"]
        for item in result.arms
        if item.arm_specification.arm_kind == TREATMENT_ARM
    )
    assert all(
        not item.learning_cost_applied
        for item in result.arms
        if item.arm_specification.arm_kind == CONTROL_ARM
    )
    assert all(
        not item.plan.metadata["learning_bundle_loaded_for_offline_intervention"]
        for item in result.arms
        if item.arm_specification.arm_kind == CONTROL_ARM
    )
    assert result.runtime_ack_available is False
    assert result.outcome_available is False
    assert result.counterfactual_available is False
    assert result.causal_available is False
    assert payload["admission"]["online_assist_enabled"] is False
    assert payload["admission"]["online_authority_enabled"] is False
    assert payload["evidence_availability"] == {
        "runtime_ack": False,
        "outcome": False,
        "counterfactual": False,
        "causal": False,
    }
    assert "truth" not in output.read_text(encoding="utf-8").lower()
    assert load_model_bundle(bundle_dir, mode="assist").fallback_reason == (
        "bundle_shadow_only"
    )


def test_realistic_five_by_five_control_exactly_replays_execution_state(
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "bundle"
    _bundle(bundle_dir)
    config, weights, frames = _realistic_five_by_five_frames()
    specification = _specification(bundle_dir=bundle_dir, frames=frames)

    for seed in _HELD_5V5_SEEDS:
        assert frames[seed].plan.decision_state == "held_by_hysteresis"
        assert frames[seed].forced_replan is False
    for seed in _FORCED_REPLAN_4_TO_5_SEEDS:
        frame = frames[seed]
        assert frame.plan.decision_state == "replan_applied"
        assert frame.forced_replan is True
        assert frame.plan.target_count == len(frame.tracks) == 5
        assert frame.previous_plan.target_count == 4
        assert len(frame.plan.assignments) == 4
        pending_target_id = frame.tracks[-1].track_id
        assert frame.plan.unassigned_target_ids == (pending_target_id,)
        assert frame.plan.incomplete_target_ids == (pending_target_id,)

    removed = frames[_REMOVED_TARGET_SEED]
    prior_only_targets = {
        assignment.target_id
        for assignment in removed.previous_plan.assignments
        if assignment.target_id.startswith("previous_target_")
    }
    assert prior_only_targets == {"previous_target_0000"}
    assert all(
        not assignment.target_id.startswith("previous_target_")
        for assignment in removed.plan.assignments
    )
    assert removed.plan.decision_state == "accepted_previous_infeasible"

    for frame in frames.values():
        assert frame.plan.metadata["plan_owner"] == "center"
        assert frame.plan.metadata["owner_node_id"] == "node_0000"
        assert frame.previous_plan.metadata["owner_node_id"] == "node_0000"
        assert frame.plan.source_node_id == "node_0000"
        rendered = repr(frame)
        assert "private-center-node" not in rendered
        assert "global-track-" not in rendered
        assert "interceptor-" not in rendered
        assert "truth-" not in rendered
        assert "actor-" not in rendered
        assert "object-" not in rendered

    result = execute_offline_paired_intervention(
        specification,
        frames,
        bundle_dir=tmp_path / "missing-development-bundle",
        planner_config=config,
        cost_weights=weights,
    )
    assert result.bundle_loaded is False
    assert result.bundle_fallback_reason == "bundle_manifest_sha256_mismatch"
    controls = {
        item.arm_specification.seed: item
        for item in result.arms
        if item.arm_specification.arm_kind == CONTROL_ARM
    }
    assert len(controls) == 20
    for seed, frame in frames.items():
        expected = frame.plan
        replayed = controls[seed].plan
        assert {
            (item.target_id, item.resource_id) for item in replayed.assignments
        } == {
            (item.target_id, item.resource_id) for item in expected.assignments
        }
        assert replayed.version == expected.version
        assert replayed.window_id == expected.window_id
        assert replayed.decision_state == expected.decision_state
        assert replayed.changed == expected.changed
        assert replayed.resource_count == expected.resource_count
        assert replayed.target_count == expected.target_count

    assert len(result.arms) == 40
    for arm_index, execution in enumerate(result.arms):
        plan = execution.plan
        frame = frames[execution.arm_specification.seed]
        solve_source = frame.previous_plan
        authority = frame.plan
        assert solve_source is not None
        assert authority is not None
        diagnostic = _target_inventory_diagnostic(plan)
        try:
            payload_sha256 = validated_assignment_plan_payload_sha256(plan)
            consumption = build_isolated_plan_consumption_evidence(
                specification=result.specification,
                arm_specification=execution.arm_specification,
                execution_receipt=execution.receipt,
                plan=plan,
                rollout_cycle=0,
                consumption_timestamp_s=(
                    execution.arm_specification.intervention_timestamp_s
                ),
            )
            promoted = build_isolated_execution_plan(
                specification=result.specification,
                arm_specification=execution.arm_specification,
                execution_receipt=execution.receipt,
                planning_frame_evidence=frame,
                offline_solve_source_plan=solve_source,
                formal_authority_plan=authority,
                offline_candidate_plan=plan,
            )
            promoted_consumption = build_isolated_plan_consumption_evidence(
                specification=result.specification,
                arm_specification=execution.arm_specification,
                execution_receipt=execution.receipt,
                plan=promoted.plan,
                rollout_cycle=0,
                consumption_timestamp_s=promoted.plan.created_at,
                planning_frame_evidence=frame,
                offline_solve_source_plan=solve_source,
                formal_authority_plan=authority,
                offline_candidate_plan=plan,
                conversion_evidence=promoted.conversion_evidence,
            )
        except Exception as exc:  # pragma: no cover - diagnostic on regression
            pytest.fail(
                "strict offline arm validation failed: "
                f"arm_index={arm_index}, "
                f"seed={execution.arm_specification.seed}, "
                f"arm={execution.arm_specification.arm_kind}, "
                f"inventory={diagnostic!r}, error={exc!r}"
            )
        assert isinstance(plan, AssignmentPlan)
        assert type(plan).__module__ == "d3_assignment_planner.models"
        assert execution.receipt.output_plan_payload_sha256 == payload_sha256
        assert validated_assignment_plan_payload_sha256(plan) == payload_sha256
        assert consumption.production_runtime_ack is False
        assert consumption.isolated_simulation_only is True
        assert promoted.plan.version == authority.version + 1
        assert promoted.plan.previous_plan_id == authority.plan_id
        assert promoted.plan.created_at > authority.created_at
        assert promoted.plan.created_at > (
            execution.arm_specification.intervention_timestamp_s
        )
        assert promoted.plan.unassigned_target_ids == plan.unassigned_target_ids
        assert promoted.plan.incomplete_target_ids == plan.incomplete_target_ids
        assert promoted.plan.coalitions == plan.coalitions
        assert promoted.plan.demand_summaries == plan.demand_summaries
        assert promoted_consumption.plan_id == promoted.plan.plan_id
        assert promoted_consumption.plan_payload_sha256 == (
            promoted.plan_payload_sha256
        )

    by_seed_and_arm = {
        (item.arm_specification.seed, item.arm_specification.arm_kind): item
        for item in result.arms
    }
    seed_1000_control = by_seed_and_arm[(1000, CONTROL_ARM)].plan
    assert len(seed_1000_control.assignments) == 5
    assert seed_1000_control.unassigned_target_ids == ()
    assert seed_1000_control.incomplete_target_ids == ()
    assert len(seed_1000_control.demand_summaries) == 5

    for seed in _FORCED_REPLAN_4_TO_5_SEEDS:
        missing_target_id = frames[seed].tracks[-1].track_id
        for arm_kind in (CONTROL_ARM, TREATMENT_ARM):
            plan = by_seed_and_arm[(seed, arm_kind)].plan
            assert len(plan.assignments) == 4
            assert plan.unassigned_target_ids == (missing_target_id,)
            assert plan.incomplete_target_ids == (missing_target_id,)
            summary = next(
                item
                for item in plan.demand_summaries
                if item.target_id == missing_target_id
            )
            assert (
                summary.demand_required,
                summary.demand_assigned,
                summary.demand_shortfall,
                summary.coalition_complete,
            ) == (1, 0, 1, False)
            assert plan.metadata[
                "isolated_target_inventory_added_unassigned_ids"
            ] == ()
            assert plan.metadata[
                "versioned_target_inventory_added_unassigned_ids"
            ] == (missing_target_id,)
            assert plan.metadata[
                "versioned_target_inventory_added_incomplete_ids"
            ] == (missing_target_id,)

    removed_plan = by_seed_and_arm[(_REMOVED_TARGET_SEED, CONTROL_ARM)].plan
    current_removed_seed_targets = {
        item.track_id for item in frames[_REMOVED_TARGET_SEED].tracks
    }
    assert {
        *(item.target_id for item in removed_plan.assignments),
        *removed_plan.unassigned_target_ids,
        *removed_plan.incomplete_target_ids,
        *(item.target_id for item in removed_plan.coalitions),
        *(item.target_id for item in removed_plan.demand_summaries),
    } == current_removed_seed_targets

    incomplete = by_seed_and_arm[(1011, CONTROL_ARM)].plan
    with pytest.raises(AssignmentPlanRuntimeAckError) as captured:
        validated_assignment_plan_payload_sha256(
            replace(
                incomplete,
                unassigned_target_ids=(),
                incomplete_target_ids=(),
            )
        )
    assert captured.value.code == "expected_plan_target_count_invalid"


def test_center_failure_authority_identity_replays_all_reserved_seeds(
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "bundle"
    _bundle(bundle_dir)
    config, weights, frames = _realistic_five_by_five_frames(
        secondary_takeover=True,
    )
    specification = _specification(bundle_dir=bundle_dir, frames=frames)

    assert all(
        frame.planning_path == "authority_identity_publish"
        for frame in frames.values()
    )
    result = execute_offline_paired_intervention(
        specification,
        frames,
        bundle_dir=tmp_path / "missing-development-bundle",
        planner_config=config,
        cost_weights=weights,
    )
    controls = {
        item.arm_specification.seed: item.plan
        for item in result.arms
        if item.arm_specification.arm_kind == CONTROL_ARM
    }

    assert len(controls) == 20
    for seed, frame in frames.items():
        recorded = frame.plan
        replayed = controls[seed]
        assert replayed.version == recorded.version == 2
        assert replayed.window_id == recorded.window_id
        assert replayed.decision_state == recorded.decision_state
        assert replayed.changed == recorded.changed
        assert replayed.metadata["active_plan_owner"] == "secondary"
        assert replayed.metadata["offline_authority_identity_replayed"] is True
        validated_assignment_plan_payload_sha256(replayed)
        assert replayed.decision_state == "replan_ack_no_change"
        assert replayed.changed is False

    assert len(result.arms) == 40
    for execution in result.arms:
        frame = frames[execution.arm_specification.seed]
        solve_source = frame.previous_plan
        authority = frame.plan
        assert solve_source is not None
        assert authority is not None
        promoted = build_isolated_execution_plan(
            specification=result.specification,
            arm_specification=execution.arm_specification,
            execution_receipt=execution.receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=solve_source,
            formal_authority_plan=authority,
            offline_candidate_plan=execution.plan,
        )
        assert promoted.plan.version == authority.version + 1 == 3
        assert promoted.plan.previous_plan_id == authority.plan_id
        assert promoted.plan.created_at > authority.created_at
        assert promoted.plan.created_at > (
            execution.arm_specification.intervention_timestamp_s
        )
        assert promoted.conversion_evidence.valid_until_s == 6.0
        assert promoted.plan.unassigned_target_ids == (
            execution.plan.unassigned_target_ids
        )
        assert promoted.plan.incomplete_target_ids == (
            execution.plan.incomplete_target_ids
        )
        validated_assignment_plan_payload_sha256(promoted.plan)


def test_regional_authority_replay_generates_all_reserved_arms(
    tmp_path: Path,
    regional_replay_contract_fixture: tuple[
        PlannerConfig,
        CostWeights,
        dict[int, object],
    ],
) -> None:
    bundle_dir = tmp_path / "bundle"
    _bundle(bundle_dir)
    config, weights, frames = regional_replay_contract_fixture
    specification = _specification(bundle_dir=bundle_dir, frames=frames)

    result = execute_offline_paired_intervention(
        specification,
        frames,
        bundle_dir=tmp_path / "missing-development-bundle",
        planner_config=config,
        cost_weights=weights,
    )

    assert len(result.arms) == 40
    by_seed_and_arm = {
        (item.arm_specification.seed, item.arm_specification.arm_kind): item
        for item in result.arms
    }
    for seed, frame in frames.items():
        recorded = frame.plan
        assert recorded is not None
        for arm_kind in (CONTROL_ARM, TREATMENT_ARM):
            replayed = by_seed_and_arm[(seed, arm_kind)].plan
            assert {
                (item.target_id, item.resource_id) for item in replayed.assignments
            } == {
                (item.target_id, item.resource_id) for item in recorded.assignments
            }
            assert replayed.version == recorded.version
            assert replayed.window_id == recorded.window_id
            recorded_by_binding = {
                (item.target_id, item.resource_id): item
                for item in recorded.assignments
            }
            for assignment in replayed.assignments:
                authority_assignment = recorded_by_binding[
                    (assignment.target_id, assignment.resource_id)
                ]
                for key in (
                    "plan_owner",
                    "active_plan_owner",
                    "owner_node_id",
                    "regional_owner_layer",
                    "regional_region_id",
                    "regional_epoch",
                    "regional_lease_expires_at_s",
                    "regional_commit_state",
                    "regional_commit_required",
                    "regional_commit_mode",
                    "regional_commit_evidence_present",
                    "activation_state",
                    "executable",
                ):
                    assert assignment.metadata[key] == (
                        authority_assignment.metadata[key]
                    )
            assert replayed.metadata[
                "offline_regional_authority_identity_replayed"
            ] is True
            assert replayed.metadata[
                "offline_regional_authority_production_ack"
            ] is False
        if seed in _FORCED_REPLAN_4_TO_5_SEEDS:
            pending_target_id = frame.tracks[-1].track_id
            for arm_kind in (CONTROL_ARM, TREATMENT_ARM):
                replayed = by_seed_and_arm[(seed, arm_kind)].plan
                assert len(replayed.assignments) == 4
                assert replayed.unassigned_target_ids == (pending_target_id,)
                assert replayed.incomplete_target_ids == (pending_target_id,)
                assert all(
                    item.target_id != pending_target_id
                    for item in replayed.assignments
                )


@pytest.mark.parametrize(
    ("tamper_kind", "expected_code"),
    (
        (
            "source",
            "offline_regional_authority_replay_plan_contract_invalid",
        ),
        (
            "link",
            "offline_regional_authority_replay_plan_contract_invalid",
        ),
        ("owner", "offline_regional_authority_replay_owner_invalid"),
        (
            "epoch",
            "offline_regional_authority_replay_plan_authority_mismatch",
        ),
        (
            "lease",
            "offline_regional_authority_replay_assignment_contract_invalid",
        ),
        (
            "commit",
            "offline_regional_authority_replay_commit_contract_invalid",
        ),
        (
            "previous_plan_id",
            "offline_regional_authority_replay_plan_lineage_invalid",
        ),
        (
            "version",
            "offline_regional_authority_replay_plan_lineage_invalid",
        ),
        ("time", "offline_regional_authority_replay_plan_time_invalid"),
    ),
)
def test_regional_authority_replay_tampering_fails_closed_after_rehash(
    regional_replay_contract_fixture: tuple[
        PlannerConfig,
        CostWeights,
        dict[int, object],
    ],
    tamper_kind: str,
    expected_code: str,
) -> None:
    _, _, frames = regional_replay_contract_fixture
    frame = frames[1000]
    recorded = frame.plan
    previous = frame.previous_plan
    assert recorded is not None
    assert previous is not None
    first = recorded.assignments[0]

    if tamper_kind == "source":
        tampered = replace(recorded, source_node_id=None)
    elif tamper_kind == "link":
        tampered = replace(recorded, link_type="regional_tampered")
    elif tamper_kind == "owner":
        tampered = replace(
            recorded,
            metadata={**dict(recorded.metadata), "active_plan_owner": "center"},
        )
    elif tamper_kind == "epoch":
        tampered_first = replace(
            first,
            metadata={
                **dict(first.metadata),
                "regional_epoch": int(first.metadata["regional_epoch"]) + 1,
            },
        )
        tampered = replace(
            recorded,
            assignments=(tampered_first, *recorded.assignments[1:]),
        )
    elif tamper_kind == "lease":
        tampered_first = replace(
            first,
            metadata={
                **dict(first.metadata),
                "regional_lease_expires_at_s": float(frame.timestamp_s),
            },
        )
        tampered = replace(
            recorded,
            assignments=(tampered_first, *recorded.assignments[1:]),
        )
    elif tamper_kind == "commit":
        tampered_first = replace(
            first,
            metadata={
                **dict(first.metadata),
                "regional_commit_state": "committed",
            },
        )
        tampered = replace(
            recorded,
            assignments=(tampered_first, *recorded.assignments[1:]),
        )
    elif tamper_kind == "previous_plan_id":
        tampered = replace(recorded, previous_plan_id="tampered-previous-plan")
    elif tamper_kind == "version":
        tampered = replace(recorded, version=recorded.version + 1)
    elif tamper_kind == "time":
        tampered = replace(recorded, created_at=previous.created_at)
    else:  # pragma: no cover - parametrization is exhaustive
        raise AssertionError(tamper_kind)

    tampered_frame = _replace_recorded_regional_plan(frame, tampered)
    with pytest.raises(PairedInterventionContractError) as captured:
        _recorded_regional_authority_input(tampered_frame)
    assert captured.value.code == expected_code


def test_regional_authority_transition_hash_tampering_fails_closed(
    regional_replay_contract_fixture: tuple[
        PlannerConfig,
        CostWeights,
        dict[int, object],
    ],
) -> None:
    _, _, frames = regional_replay_contract_fixture
    frame = replace(
        frames[1000],
        recorded_authority_transition_sha256="f" * 64,
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        _recorded_regional_authority_input(frame)

    assert captured.value.code == (
        "offline_regional_authority_replay_transition_sha256_mismatch"
    )


def test_control_binding_tamper_still_fails_strict_replay_gate(
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "bundle"
    _bundle(bundle_dir)
    config = PlannerConfig(enable_hysteresis=False)
    frames = _planning_frames(config)
    seed = PAIRED_INTERVENTION_RESERVED_SEEDS_V1[0]
    frame = frames[seed]
    recorded = frame.plan
    first = recorded.assignments[0]
    replacement_resource = next(
        resource.resource_id
        for resource in frame.resources
        if resource.resource_id != first.resource_id
    )
    tampered = replace(
        recorded,
        assignments=(
            replace(first, resource_id=replacement_resource),
            *recorded.assignments[1:],
        ),
    )
    frames[seed] = replace(frame, plan=tampered)
    specification = _specification(bundle_dir=bundle_dir, frames=frames)

    with pytest.raises(PairedInterventionContractError) as captured:
        execute_offline_paired_intervention(
            specification,
            frames,
            bundle_dir=bundle_dir,
            planner_config=config,
        )

    assert captured.value.code == "control_plan_replay_mismatch"


@pytest.mark.parametrize(
    ("spec_overrides", "expected_reason"),
    (
        ({"manifest_sha256": "f" * 64}, "bundle_manifest_sha256_mismatch"),
        ({"policy_version": "wrong-policy-version"}, "bundle_policy_version_mismatch"),
    ),
)
def test_bundle_identity_failure_returns_rule_fallback_receipts(
    tmp_path: Path,
    spec_overrides: dict[str, str],
    expected_reason: str,
) -> None:
    bundle_dir = tmp_path / "bundle"
    _bundle(bundle_dir)
    config = PlannerConfig(enable_hysteresis=False)
    frames = _planning_frames(config)
    specification = _specification(
        bundle_dir=bundle_dir,
        frames=frames,
        **spec_overrides,
    )

    result = execute_offline_paired_intervention(
        specification,
        frames,
        bundle_dir=bundle_dir,
        planner_config=config,
    )

    treatment = tuple(
        item
        for item in result.arms
        if item.arm_specification.arm_kind == TREATMENT_ARM
    )
    assert result.bundle_loaded is False
    assert result.bundle_fallback_reason == expected_reason
    assert all(item.rule_fallback_applied for item in treatment)
    assert all(item.fallback_reason == expected_reason for item in treatment)
    assert all(not item.learning_cost_applied for item in treatment)
    assert all(
        not item.plan.metadata["learning_bundle_loaded_for_offline_intervention"]
        for item in treatment
    )
    assert result.manifest.availability[
        "treatment_safely_applied_in_isolated_simulation"
    ]["value"] is False


@pytest.mark.parametrize(
    ("deadline_s", "mean", "scale", "expected_reason"),
    (
        (1.0e-12, 0.0, 1.0, "model_timeout"),
        (1.0, 100.0, 1.0e-3, "out_of_distribution"),
    ),
)
def test_runtime_guard_failure_falls_back_without_changing_rule_matrix(
    tmp_path: Path,
    deadline_s: float,
    mean: float,
    scale: float,
    expected_reason: str,
) -> None:
    bundle_dir = tmp_path / "bundle"
    _bundle(
        bundle_dir,
        deadline_s=deadline_s,
        normalization_mean=mean,
        normalization_scale=scale,
    )
    config = PlannerConfig(enable_hysteresis=False)
    frames = _planning_frames(config)
    specification = _specification(bundle_dir=bundle_dir, frames=frames)

    result = execute_offline_paired_intervention(
        specification,
        frames,
        bundle_dir=bundle_dir,
        planner_config=config,
    )

    by_seed_and_arm = {
        (item.arm_specification.seed, item.arm_specification.arm_kind): item
        for item in result.arms
    }
    assert result.bundle_loaded is True
    for seed in PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
        control = by_seed_and_arm[(seed, CONTROL_ARM)]
        treatment = by_seed_and_arm[(seed, TREATMENT_ARM)]
        assert treatment.fallback_reason == expected_reason
        assert treatment.rule_fallback_applied is True
        assert treatment.learning_cost_applied is False
        assert (
            treatment.plan.metadata[
                "learning_bundle_loaded_for_offline_intervention"
            ]
            is True
        )
        assert (
            treatment.plan.metadata["learning_cost_intervention_applied"]
            is False
        )
        assert treatment.plan.assignment_signature() == control.plan.assignment_signature()
        assert treatment.receipt.rule_cost_matrix_sha256 == (
            control.receipt.rule_cost_matrix_sha256
        )
        assert treatment.receipt.action_mask_sha256 == (
            control.receipt.action_mask_sha256
        )


def test_nonfinite_frozen_weights_are_rejected_before_inference(
    tmp_path: Path,
) -> None:
    torch = pytest.importorskip("torch")
    bundle_dir = tmp_path / "bundle"
    _bundle(bundle_dir)
    state_path = bundle_dir / "state_dict.pt"
    state = torch.load(state_path, map_location="cpu", weights_only=True)
    first = next(iter(state))
    state[first] = torch.full_like(state[first], float("nan"))
    torch.save(state, state_path)
    raw = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    state_sha = _file_digest(state_path)
    raw["state_dict"]["sha256"] = state_sha
    raw["promotion_manifest"]["model_state_dict_sha256"] = state_sha
    (bundle_dir / "manifest.json").write_text(
        json.dumps(raw, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    config = PlannerConfig(enable_hysteresis=False)
    frames = _planning_frames(config)
    specification = _specification(bundle_dir=bundle_dir, frames=frames)

    result = execute_offline_paired_intervention(
        specification,
        frames,
        bundle_dir=bundle_dir,
        planner_config=config,
    )

    assert result.bundle_loaded is False
    assert result.bundle_fallback_reason == "model_state_nonfinite"
    assert all(
        item.fallback_reason == "model_state_nonfinite"
        for item in result.arms
        if item.arm_specification.arm_kind == TREATMENT_ARM
    )


def test_input_snapshot_mismatch_fails_before_any_receipt(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    _bundle(bundle_dir)
    config = PlannerConfig(enable_hysteresis=False)
    frames = _planning_frames(config)
    specification = _specification(bundle_dir=bundle_dir, frames=frames)
    first = specification.pairs[0]
    wrong_hash = "e" * 64
    wrong_pair = replace(
        first,
        control=replace(
            first.control,
            observation_input_snapshot_sha256=wrong_hash,
        ),
        treatment=replace(
            first.treatment,
            observation_input_snapshot_sha256=wrong_hash,
        ),
    )
    bad = replace(specification, pairs=(wrong_pair, *specification.pairs[1:]))

    with pytest.raises(PairedInterventionContractError) as captured:
        execute_offline_paired_intervention(
            bad,
            frames,
            bundle_dir=bundle_dir,
            planner_config=config,
        )

    assert captured.value.code == "offline_execution_input_snapshot_sha256_mismatch"
