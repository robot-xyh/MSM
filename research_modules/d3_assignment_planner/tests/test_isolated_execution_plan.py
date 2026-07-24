from __future__ import annotations
from commitment_test_support import committed_target_track

from dataclasses import replace
from hashlib import sha256
import json
from math import inf, nextafter

import numpy as np
import pytest

from d3_assignment_planner import (
    CONTROL_ARM,
    CONTROL_PLANNER_PATH,
    D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1,
    D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1,
    D6_SIDECAR_OWNER,
    OFFLINE_INTERVENTION_SCOPE,
    PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1,
    PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
    SHADOW_EVALUATION_SCHEMA_V2,
    TREATMENT_ARM,
    TREATMENT_PLANNER_PATH,
    Assignment,
    AssignmentPlan,
    CoalitionMember,
    CoalitionPlan,
    CostMatrixResult,
    DemandSatisfactionSummary,
    IsolatedExecutionPlanError,
    IsolatedPlanConsumptionValidator,
    PairedInterventionArmSpecification,
    PairedInterventionExecutionReceipt,
    PairedInterventionSeedPair,
    PairedInterventionSpecification,
    PlanningFrameEvidence,
    ResourceState,
    TargetTrack,
    build_isolated_execution_plan,
    build_isolated_plan_consumption_evidence,
    canonical_isolated_execution_planning_frame_sha256,
    canonical_planning_frame_snapshot_sha256,
    canonical_runtime_payload_sha256,
    validate_isolated_execution_plan_conversion,
    validated_assignment_plan_payload_sha256,
)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _specification(
    *,
    first_snapshot_sha256: str | None = None,
    first_plan_valid_until_s: float = 25.0,
) -> PairedInterventionSpecification:
    pairs = []
    for seed in PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
        common = {
            "seed": seed,
            "intervention_scope": OFFLINE_INTERVENTION_SCOPE,
            "scenario_version": "isolated-execution-unit-v1",
            "scenario_config_sha256": _digest(f"scenario-{seed}"),
            "initial_world_state_sha256": _digest(f"world-{seed}"),
            "observation_input_snapshot_sha256": (
                first_snapshot_sha256
                if seed == PAIRED_INTERVENTION_RESERVED_SEEDS_V1[0]
                and first_snapshot_sha256 is not None
                else _digest(f"snapshot-{seed}")
            ),
            "input_snapshot_schema_version": "anonymous-snapshot-v1",
            "d1_d2_lineage_contract_version": "d1-d2-lineage-v1",
            "d1_d2_lineage_contract_sha256": _digest("d1-d2-lineage"),
            "rule_cost_profile_version": "d3-rule-v1",
            "rule_cost_config_sha256": _digest("rule-config"),
            "d3_bundle_version": "d3-development-bundle-v1",
            "d3_bundle_sha256": _digest("d3-bundle"),
            "d3_bundle_frozen": True,
            "threshold_version": "d3-threshold-v1",
            "threshold_config_sha256": _digest("threshold-config"),
            "threshold_frozen": True,
            "safety_shell_version": "d3-safety-v1",
            "safety_shell_config_sha256": _digest("safety-config"),
            "source_plan_id": f"formal-source-{seed}",
            "source_plan_version": 3,
            "expected_previous_plan_version": 3,
            "current_plan_version": 3,
            "source_plan_created_at_s": 10.0,
            "intervention_timestamp_s": 12.0,
            "plan_valid_until_s": (
                first_plan_valid_until_s
                if seed == PAIRED_INTERVENTION_RESERVED_SEEDS_V1[0]
                else 25.0
            ),
            "ppo_enabled": False,
            "online_assist_enabled": False,
            "online_authority_enabled": False,
            "rule_fallback_enabled": True,
        }
        pairs.append(
            PairedInterventionSeedPair(
                pair_id=f"pair-{seed}",
                seed=seed,
                control=PairedInterventionArmSpecification(
                    arm_id=f"arm-{seed}-control",
                    arm_kind=CONTROL_ARM,
                    isolation_id=f"isolation-{seed}-control",
                    planner_path=CONTROL_PLANNER_PATH,
                    learning_cost_intervention_enabled=False,
                    **common,
                ),
                treatment=PairedInterventionArmSpecification(
                    arm_id=f"arm-{seed}-treatment",
                    arm_kind=TREATMENT_ARM,
                    isolation_id=f"isolation-{seed}-treatment",
                    planner_path=TREATMENT_PLANNER_PATH,
                    learning_cost_intervention_enabled=True,
                    **common,
                ),
            )
        )
    return PairedInterventionSpecification(
        experiment_id="isolated-execution-unit",
        experiment_version="isolated-execution-unit-v1",
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


def _formal_source(seed: int = 1000) -> AssignmentPlan:
    assignments = tuple(
        Assignment(
            target_id=f"target-{index}",
            resource_id=f"resource-{index}",
            cost=float(index + 1),
            cost_breakdown={"rule": float(index + 1)},
            source_node_id="secondary-node-1",
            target_node_id=f"resource-{index}",
            link_type="d4_secondary_relay",
            plan_version=3,
            metadata={
                "owner_node_id": "secondary-node-1",
                "active_plan_owner": "secondary",
            },
        )
        for index in range(2)
    )
    return AssignmentPlan(
        plan_id=f"formal-source-{seed}",
        version=3,
        window_id=7,
        assignments=assignments,
        unassigned_target_ids=(),
        total_cost=3.0,
        created_at=10.0,
        last_changed_at=10.0,
        human_authorization_state="approved",
        source_node_id="secondary-node-1",
        target_node_id="interceptor-network",
        link_type="d4_secondary_relay",
        resource_count=2,
        target_count=2,
        demand_summaries=tuple(
            DemandSatisfactionSummary(
                target_id=f"target-{index}",
                demand_required=1,
                demand_assigned=1,
                demand_shortfall=0,
                coalition_complete=True,
            )
            for index in range(2)
        ),
        metadata={
            "plan_schema": "secondary_plan_v2",
            "plan_owner": "secondary",
            "active_plan_owner": "secondary",
            "owner_node_id": "secondary-node-1",
            "source_node_id": "secondary-node-1",
            "target_node_id": "interceptor-network",
            "link_type": "d4_secondary_relay",
            "secondary_takeover_state": "secondary_plan_active",
            "secondary_plan_executable": True,
            "secondary_leader_epoch": 7,
            "secondary_lease_expires_at_s": 30.0,
            "current_plan_id": f"formal-source-{seed}",
            "current_plan_version": 3,
            "identity_created_at_s": 10.0,
            "last_evaluated_at_s": 10.0,
        },
    )


def _formal_authority(
    source: AssignmentPlan,
    *,
    same_generation: bool = False,
    lease_expires_at_s: float = 30.0,
) -> AssignmentPlan:
    version = source.version if same_generation else source.version + 1
    plan_id = source.plan_id if same_generation else f"formal-authority-{source.plan_id}"
    created_at = source.created_at if same_generation else 12.0
    assignments = tuple(
        replace(
            assignment,
            plan_version=version,
            metadata={
                **dict(assignment.metadata),
                "current_plan_id": plan_id,
                "current_plan_version": version,
            },
        )
        for assignment in source.assignments
    )
    return replace(
        source,
        plan_id=plan_id,
        version=version,
        assignments=assignments,
        created_at=created_at,
        last_changed_at=created_at,
        previous_plan_id=(source.previous_plan_id if same_generation else source.plan_id),
        metadata={
            **dict(source.metadata),
            "current_plan_id": plan_id,
            "current_plan_version": version,
            "identity_created_at_s": created_at,
            "last_evaluated_at_s": 12.0,
            "secondary_plan_version": version,
            "secondary_lease_expires_at_s": lease_expires_at_s,
        },
    )


def _planning_frame(
    source: AssignmentPlan,
    authority: AssignmentPlan,
) -> PlanningFrameEvidence:
    matrix = CostMatrixResult(
        matrix=np.asarray(((1.0, 2.0), (2.0, 1.0)), dtype=float),
        breakdowns=(
            ({"rule": 1.0}, {"rule": 2.0}),
            ({"rule": 2.0}, {"rule": 1.0}),
        ),
        target_ids=("target-0", "target-1"),
        resource_ids=("resource-0", "resource-1"),
        unassigned_costs=np.asarray((10.0, 10.0), dtype=float),
        target_threat_scores=(0.8, 0.7),
        reject_reasons=((None, None), (None, None)),
        candidate_mask=np.ones((2, 2), dtype=bool),
    )
    return PlanningFrameEvidence(
        available=True,
        reason="available",
        planning_path=(
            "evaluation_refresh"
            if authority.version == source.version
            else "authority_identity_publish"
        ),
        selection_source="rule",
        timestamp_s=12.0,
        plan_id=authority.plan_id,
        plan_version=authority.version,
        previous_plan_version=source.version,
        rule_matrix_result=matrix,
        effective_matrix_result=matrix,
        learning_mode="disabled",
        learning_state="rule_only",
        solver_name=authority.solver_name,
        tracks=(
            committed_target_track("target-0", 0.8, 0.1, 0.0),
            committed_target_track("target-1", 0.7, 0.1, 0.0),
        ),
        resources=(ResourceState("resource-0"), ResourceState("resource-1")),
        plan=authority,
        previous_plan=source,
    )


def _candidate(
    *,
    plan_id: str = "offline-candidate-control",
    arm: PairedInterventionArmSpecification | None = None,
    source: AssignmentPlan | None = None,
    authority: AssignmentPlan | None = None,
    frame: PlanningFrameEvidence | None = None,
) -> AssignmentPlan:
    resolved_source = source or _formal_source()
    resolved_authority = authority or _formal_authority(resolved_source)
    resolved_frame = frame or _planning_frame(resolved_source, resolved_authority)
    resolved_arm = arm or _specification(
        first_snapshot_sha256=canonical_planning_frame_snapshot_sha256(
            resolved_frame
        )
    ).pairs[0].control
    return AssignmentPlan(
        plan_id=plan_id,
        version=3,
        window_id=8,
        assignments=(
            Assignment(
                target_id="target-0",
                resource_id="resource-1",
                cost=1.25,
                cost_breakdown={"rule": 1.25},
                source_node_id="d3_offline_intervention",
                link_type="offline_isolated",
                plan_version=3,
                coalition_id="coalition-target-0",
                coalition_version=2,
                metadata={
                    "current_plan_id": plan_id,
                    "current_plan_version": 3,
                    "isolated_simulation": True,
                },
            ),
        ),
        unassigned_target_ids=("target-1",),
        incomplete_target_ids=("target-1",),
        coalitions=(
            CoalitionPlan(
                coalition_id="coalition-target-0",
                version=2,
                target_id="target-0",
                state="committed",
                coordination_mode="independent",
                required_resource_count=1,
                assigned_resource_count=1,
                shortfall=0,
                complete=True,
                members=(
                    CoalitionMember(
                        resource_id="resource-1",
                        member_role="primary",
                        wave_id=0,
                    ),
                ),
            ),
        ),
        demand_summaries=(
            DemandSatisfactionSummary(
                target_id="target-0",
                demand_required=1,
                demand_assigned=1,
                demand_shortfall=0,
                coalition_complete=True,
                coalition_id="coalition-target-0",
                coalition_version=2,
            ),
            DemandSatisfactionSummary(
                target_id="target-1",
                demand_required=1,
                demand_assigned=0,
                demand_shortfall=1,
                coalition_complete=False,
            ),
        ),
        total_cost=5.25,
        created_at=12.0,
        last_changed_at=12.0,
        source_node_id="d3_offline_intervention",
        link_type="offline_isolated",
        human_authorization_state="offline_not_authorized",
        resource_count=2,
        target_count=2,
        metadata={
            "current_plan_id": plan_id,
            "current_plan_version": 3,
            "isolated_simulation": True,
            "paired_intervention_pair_id": "pair-1000",
            "paired_intervention_arm_id": resolved_arm.arm_id,
            "paired_intervention_arm_kind": CONTROL_ARM,
            "paired_intervention_seed": resolved_arm.seed,
            "paired_intervention_arm_spec_sha256": resolved_arm.fingerprint,
            "source_snapshot_sha256": (
                resolved_arm.observation_input_snapshot_sha256
            ),
            "planning_frame_schema_version": resolved_frame.schema_version,
            "planning_frame_transition_schema_version": (
                "d3.isolated-execution-planning-frame-transition.v1"
            ),
            "planning_frame_path": resolved_frame.planning_path,
            "planning_frame_timestamp_s": float(resolved_frame.timestamp_s),
            "planning_frame_snapshot_sha256": (
                canonical_planning_frame_snapshot_sha256(resolved_frame)
            ),
            "planning_frame_transition_sha256": (
                canonical_isolated_execution_planning_frame_sha256(
                    resolved_frame
                )
            ),
            "offline_solve_source_plan_id": resolved_source.plan_id,
            "offline_solve_source_plan_version": resolved_source.version,
            "offline_solve_source_plan_payload_sha256": (
                validated_assignment_plan_payload_sha256(resolved_source)
            ),
            "formal_authority_plan_id": resolved_authority.plan_id,
            "formal_authority_plan_version": resolved_authority.version,
            "formal_authority_plan_payload_sha256": (
                validated_assignment_plan_payload_sha256(resolved_authority)
            ),
            "runtime_execution_allowed": False,
            "ppo_enabled": False,
            "online_assist_enabled": False,
            "online_authority_enabled": False,
        },
    )


def _receipt(
    arm: PairedInterventionArmSpecification,
    candidate: AssignmentPlan,
    *,
    pair_id: str = "pair-1000",
) -> PairedInterventionExecutionReceipt:
    treatment = arm.arm_kind == TREATMENT_ARM
    return PairedInterventionExecutionReceipt(
        pair_id=pair_id,
        seed=arm.seed,
        arm_kind=arm.arm_kind,
        arm_spec_sha256=arm.fingerprint,
        paired_evaluator_schema_version=SHADOW_EVALUATION_SCHEMA_V2,
        paired_evaluator_report_sha256=_digest("report"),
        input_snapshot_sha256=arm.observation_input_snapshot_sha256,
        rule_cost_matrix_sha256=_digest("rule"),
        action_mask_sha256=_digest("mask"),
        planner_path=arm.planner_path,
        source_plan_version=arm.source_plan_version,
        expected_previous_plan_version=arm.expected_previous_plan_version,
        current_plan_version=arm.current_plan_version,
        output_plan_id=candidate.plan_id,
        output_plan_version=candidate.version,
        output_plan_payload_sha256=validated_assignment_plan_payload_sha256(candidate),
        isolated_simulation=True,
        learning_cost_applied=treatment,
        rule_matrix_unchanged=True,
        deterministic_action_mask_enforced=True,
        reachability_gate_enforced=True,
        capacity_gate_enforced=True,
        version_gate_enforced=True,
        hysteresis_gate_enforced=True,
        safety_gate_enforced=True,
        rule_fallback_available=True,
        rule_fallback_applied=False,
        fallback_reason=None,
        hysteresis_decision="accepted",
        inference_elapsed_ms=0.1,
        nonfinite_value_count=0,
        online_label_key_count=0,
        global_track_id_rewrite_count=0,
    )


def _case(
    *,
    same_generation_authority: bool = False,
    lease_expires_at_s: float = 30.0,
    plan_valid_until_s: float = 25.0,
    solve_stale_after_s: float | None = None,
):
    source = _formal_source()
    if solve_stale_after_s is not None:
        source = replace(source, stale_after_s=solve_stale_after_s)
    authority = _formal_authority(
        source,
        same_generation=same_generation_authority,
        lease_expires_at_s=lease_expires_at_s,
    )
    frame = _planning_frame(source, authority)
    specification = _specification(
        first_snapshot_sha256=canonical_planning_frame_snapshot_sha256(frame),
        first_plan_valid_until_s=plan_valid_until_s,
    )
    arm = specification.pairs[0].control
    candidate = _candidate(
        arm=arm,
        source=source,
        authority=authority,
        frame=frame,
    )
    return (
        specification,
        arm,
        _receipt(arm, candidate),
        frame,
        source,
        authority,
        candidate,
    )


def test_build_strict_isolated_execution_plan_and_consumption_roundtrip() -> None:
    specification, arm, receipt, frame, source, authority, candidate = _case()
    first = build_isolated_execution_plan(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        planning_frame_evidence=frame,
        offline_solve_source_plan=source,
        formal_authority_plan=authority,
        offline_candidate_plan=candidate,
    )
    second = build_isolated_execution_plan(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        planning_frame_evidence=frame,
        offline_solve_source_plan=source,
        formal_authority_plan=authority,
        offline_candidate_plan=candidate,
    )

    plan = first.plan
    assert plan.plan_id != source.plan_id
    assert plan.plan_id != candidate.plan_id
    assert plan.version == authority.version + 1 == 5
    assert plan.previous_plan_id == authority.plan_id
    assert plan.created_at > authority.created_at
    assert plan.created_at > arm.intervention_timestamp_s
    assert plan.metadata["plan_valid_until_s"] == 25.0
    assert plan.unassigned_target_ids == candidate.unassigned_target_ids
    assert plan.incomplete_target_ids == candidate.incomplete_target_ids
    assert plan.coalitions == candidate.coalitions
    assert plan.demand_summaries == candidate.demand_summaries
    assert plan.resource_count == candidate.resource_count
    assert plan.target_count == candidate.target_count
    assert plan.source_node_id == authority.source_node_id
    assert plan.link_type == authority.link_type
    assert plan.metadata["active_plan_owner"] == "secondary"
    assert plan.metadata["authority_epoch"] == 7
    assert plan.metadata["lease_expires_at_s"] == 30.0
    assert plan.metadata["isolated_simulation_only"] is True
    assert plan.metadata["production_runtime_ack"] is False
    assert plan.metadata["runtime_publication_allowed"] is False
    assert plan.metadata["online_authority_enabled"] is False
    assert first.plan_payload_sha256 == validated_assignment_plan_payload_sha256(plan)
    assert first.conversion_evidence.offline_solve_source_plan_payload_sha256 == (
        validated_assignment_plan_payload_sha256(source)
    )
    assert first.conversion_evidence.formal_authority_plan_payload_sha256 == (
        validated_assignment_plan_payload_sha256(authority)
    )
    assert first.conversion_evidence.planning_frame_transition_sha256 == (
        canonical_isolated_execution_planning_frame_sha256(frame)
    )
    assert first.to_dict() == second.to_dict()
    json.dumps(first.to_dict(), sort_keys=True, allow_nan=False)

    validated = validate_isolated_execution_plan_conversion(
        first.conversion_evidence.to_dict(),
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        planning_frame_evidence=frame,
        offline_solve_source_plan=source,
        formal_authority_plan=authority,
        offline_candidate_plan=candidate,
        expected_execution_plan=plan,
    )
    assert validated.execution_plan_payload_sha256 == first.plan_payload_sha256

    consumption = build_isolated_plan_consumption_evidence(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        plan=plan,
        rollout_cycle=0,
        consumption_timestamp_s=12.5,
        planning_frame_evidence=frame,
        offline_solve_source_plan=source,
        formal_authority_plan=authority,
        offline_candidate_plan=candidate,
        conversion_evidence=first.conversion_evidence,
    )
    validator = IsolatedPlanConsumptionValidator()
    accepted = validator.validate_and_record(
        consumption,
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        expected_plan=plan,
        planning_frame_evidence=frame,
        offline_solve_source_plan=source,
        formal_authority_plan=authority,
        offline_candidate_plan=candidate,
        conversion_evidence=first.conversion_evidence,
    )
    assert accepted.plan_id == plan.plan_id
    assert accepted.plan_version == plan.version
    assert accepted.plan_payload_sha256 == first.plan_payload_sha256
    assert accepted.production_runtime_ack is False


def test_same_id_version_evaluation_refresh_is_frame_bound_and_supported() -> None:
    specification, arm, receipt, frame, source, authority, candidate = _case(
        same_generation_authority=True
    )

    assert authority.plan_id == source.plan_id
    assert authority.version == source.version
    assert validated_assignment_plan_payload_sha256(authority) != (
        validated_assignment_plan_payload_sha256(source)
    )
    result = build_isolated_execution_plan(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        planning_frame_evidence=frame,
        offline_solve_source_plan=source,
        formal_authority_plan=authority,
        offline_candidate_plan=candidate,
    )

    assert result.plan.version == authority.version + 1
    assert result.plan.previous_plan_id == authority.plan_id
    assert result.plan.created_at > arm.intervention_timestamp_s


def test_same_generation_authority_payload_substitution_fails_closed() -> None:
    specification, arm, receipt, frame, source, authority, candidate = _case(
        same_generation_authority=True
    )
    substituted = replace(authority, total_cost=authority.total_cost + 0.5)

    with pytest.raises(IsolatedExecutionPlanError) as captured:
        build_isolated_execution_plan(
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=source,
            formal_authority_plan=substituted,
            offline_candidate_plan=candidate,
        )
    assert captured.value.code == "planning_frame_authority_payload_mismatch"


def test_authority_previous_link_and_cross_frame_fail_closed() -> None:
    specification, arm, receipt, frame, source, authority, candidate = _case()
    wrong_link_authority = replace(
        authority,
        previous_plan_id="unrelated-formal-plan",
    )
    wrong_link_frame = replace(frame, plan=wrong_link_authority)
    with pytest.raises(IsolatedExecutionPlanError) as wrong_link:
        build_isolated_execution_plan(
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            planning_frame_evidence=wrong_link_frame,
            offline_solve_source_plan=source,
            formal_authority_plan=wrong_link_authority,
            offline_candidate_plan=candidate,
        )
    assert wrong_link.value.code == (
        "planning_frame_authority_previous_plan_mismatch"
    )

    other_authority = replace(authority, total_cost=authority.total_cost + 0.25)
    other_frame = replace(frame, plan=other_authority)
    with pytest.raises(IsolatedExecutionPlanError) as cross_frame:
        build_isolated_execution_plan(
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            planning_frame_evidence=other_frame,
            offline_solve_source_plan=source,
            formal_authority_plan=other_authority,
            offline_candidate_plan=candidate,
        )
    assert cross_frame.value.code == "candidate_source_lineage_mismatch"


def test_timestamp_and_authority_lease_without_execution_room_fail_closed() -> None:
    no_room = _case(plan_valid_until_s=nextafter(12.0, inf))
    specification, arm, receipt, frame, source, authority, candidate = no_room
    with pytest.raises(IsolatedExecutionPlanError) as timestamp:
        build_isolated_execution_plan(
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=source,
            formal_authority_plan=authority,
            offline_candidate_plan=candidate,
        )
    assert timestamp.value.code == "execution_validity_window_invalid"

    lease_case = _case(lease_expires_at_s=12.0)
    specification, arm, receipt, frame, source, authority, candidate = lease_case
    with pytest.raises(IsolatedExecutionPlanError) as lease:
        build_isolated_execution_plan(
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=source,
            formal_authority_plan=authority,
            offline_candidate_plan=candidate,
        )
    assert lease.value.code == "formal_authority_lease_invalid"


def test_candidate_inventory_tamper_without_matching_receipt_fails_closed() -> None:
    specification, arm, receipt, frame, source, authority, candidate = _case()
    tampered = replace(candidate, unassigned_target_ids=())

    with pytest.raises(IsolatedExecutionPlanError) as captured:
        build_isolated_execution_plan(
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=source,
            formal_authority_plan=authority,
            offline_candidate_plan=tampered,
        )
    assert captured.value.code == "receipt_candidate_plan_mismatch"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        (
            lambda plan, source: replace(
                plan, plan_id="new-id-without-version", version=source.version
            ),
            "execution_plan_version_not_strictly_new",
        ),
        (
            lambda plan, source: replace(plan, previous_plan_id="wrong-source"),
            "execution_previous_plan_mismatch",
        ),
        (
            lambda plan, source: replace(plan, created_at=source.created_at),
            "execution_created_at_not_strictly_new",
        ),
        (
            lambda plan, source: replace(
                plan,
                assignments=(
                    replace(plan.assignments[0], resource_id="resource-tampered"),
                ),
            ),
            "execution_assignment_inventory_changed",
        ),
        (
            lambda plan, source: replace(plan, unassigned_target_ids=()),
            "execution_unassigned_inventory_changed",
        ),
        (
            lambda plan, source: replace(plan, incomplete_target_ids=()),
            "execution_incomplete_inventory_changed",
        ),
        (
            lambda plan, source: replace(plan, coalitions=()),
            "execution_coalition_inventory_changed",
        ),
        (
            lambda plan, source: replace(
                plan,
                demand_summaries=(
                    *plan.demand_summaries[:-1],
                    replace(plan.demand_summaries[-1], demand_shortfall=0),
                ),
            ),
            "execution_demand_summary_inventory_changed",
        ),
    ),
)
def test_execution_plan_tamper_fails_closed(mutation, expected_code: str) -> None:
    specification, arm, receipt, frame, source, authority, candidate = _case()
    result = build_isolated_execution_plan(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        planning_frame_evidence=frame,
        offline_solve_source_plan=source,
        formal_authority_plan=authority,
        offline_candidate_plan=candidate,
    )
    tampered = mutation(result.plan, authority)
    with pytest.raises(IsolatedExecutionPlanError) as captured:
        validate_isolated_execution_plan_conversion(
            result.conversion_evidence,
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=source,
            formal_authority_plan=authority,
            offline_candidate_plan=candidate,
            expected_execution_plan=tampered,
        )
    assert captured.value.code == expected_code


def test_valid_until_tamper_fails_closed() -> None:
    specification, arm, receipt, frame, source, authority, candidate = _case()
    result = build_isolated_execution_plan(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        planning_frame_evidence=frame,
        offline_solve_source_plan=source,
        formal_authority_plan=authority,
        offline_candidate_plan=candidate,
    )
    tampered = replace(
        result.plan,
        metadata={**result.plan.metadata, "plan_valid_until_s": 12.0},
    )
    with pytest.raises(IsolatedExecutionPlanError) as captured:
        validate_isolated_execution_plan_conversion(
            result.conversion_evidence,
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=source,
            formal_authority_plan=authority,
            offline_candidate_plan=candidate,
            expected_execution_plan=tampered,
        )
    assert captured.value.code == "execution_valid_until_mismatch"


def test_cross_arm_seed_and_source_fail_closed() -> None:
    specification, arm, receipt, frame, source, authority, candidate = _case()
    treatment = specification.pairs[0].treatment
    with pytest.raises(IsolatedExecutionPlanError) as cross_arm:
        build_isolated_execution_plan(
            specification=specification,
            arm_specification=treatment,
            execution_receipt=receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=source,
            formal_authority_plan=authority,
            offline_candidate_plan=candidate,
        )
    assert cross_arm.value.code == "receipt_arm_identity_mismatch"

    other_seed_arm = specification.pairs[1].control
    with pytest.raises(IsolatedExecutionPlanError) as cross_seed:
        build_isolated_execution_plan(
            specification=specification,
            arm_specification=other_seed_arm,
            execution_receipt=receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=source,
            formal_authority_plan=authority,
            offline_candidate_plan=candidate,
        )
    assert cross_seed.value.code == "receipt_pair_id_mismatch"

    with pytest.raises(IsolatedExecutionPlanError) as cross_source:
        build_isolated_execution_plan(
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=replace(source, plan_id="another-source"),
            formal_authority_plan=authority,
            offline_candidate_plan=candidate,
        )
    assert cross_source.value.code == "planning_frame_solve_source_payload_mismatch"

    with pytest.raises(IsolatedExecutionPlanError) as source_payload:
        build_isolated_execution_plan(
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=replace(
                source, total_cost=source.total_cost + 1.0
            ),
            formal_authority_plan=authority,
            offline_candidate_plan=candidate,
        )
    assert source_payload.value.code == "planning_frame_solve_source_payload_mismatch"


def test_expired_source_and_truth_leak_fail_closed() -> None:
    specification, arm, receipt, frame, source, authority, candidate = _case(
        solve_stale_after_s=1.0
    )
    with pytest.raises(IsolatedExecutionPlanError) as expired:
        build_isolated_execution_plan(
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=source,
            formal_authority_plan=authority,
            offline_candidate_plan=candidate,
        )
    assert expired.value.code == "offline_solve_source_plan_expired"

    leaked = replace(
        candidate,
        metadata={**candidate.metadata, "truth_id": "forbidden-label"},
    )
    leaked_receipt = _receipt(arm, leaked)
    with pytest.raises(IsolatedExecutionPlanError) as truth:
        build_isolated_execution_plan(
            specification=specification,
            arm_specification=arm,
            execution_receipt=leaked_receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=source,
            formal_authority_plan=authority,
            offline_candidate_plan=leaked,
        )
    assert truth.value.code == "truth_field_forbidden"


def test_conversion_evidence_hash_tamper_fails_closed() -> None:
    specification, arm, receipt, frame, source, authority, candidate = _case()
    result = build_isolated_execution_plan(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        planning_frame_evidence=frame,
        offline_solve_source_plan=source,
        formal_authority_plan=authority,
        offline_candidate_plan=candidate,
    )
    payload = result.conversion_evidence.to_dict()
    payload["execution_plan_payload_sha256"] = "f" * 64
    with pytest.raises(IsolatedExecutionPlanError) as captured:
        validate_isolated_execution_plan_conversion(
            payload,
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            planning_frame_evidence=frame,
            offline_solve_source_plan=source,
            formal_authority_plan=authority,
            offline_candidate_plan=candidate,
            expected_execution_plan=result.plan,
        )
    assert captured.value.code == "conversion_evidence_mismatch"

    assert canonical_runtime_payload_sha256(result.to_dict()) == (
        canonical_runtime_payload_sha256(result.to_dict())
    )
