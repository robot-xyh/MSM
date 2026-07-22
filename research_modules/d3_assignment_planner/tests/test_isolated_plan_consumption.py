from __future__ import annotations

from hashlib import sha256
import json

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
    IsolatedPlanConsumptionError,
    IsolatedPlanConsumptionValidator,
    PairedInterventionArmSpecification,
    PairedInterventionExecutionReceipt,
    PairedInterventionSeedPair,
    PairedInterventionSpecification,
    build_isolated_plan_consumption_evidence,
    validate_isolated_plan_consumption_evidence,
    validated_assignment_plan_payload_sha256,
)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _specification() -> PairedInterventionSpecification:
    pairs = []
    for seed in PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
        common = {
            "seed": seed,
            "intervention_scope": OFFLINE_INTERVENTION_SCOPE,
            "scenario_version": "isolated-rollout-unit-v1",
            "scenario_config_sha256": _digest(f"scenario-{seed}"),
            "initial_world_state_sha256": _digest(f"world-{seed}"),
            "observation_input_snapshot_sha256": _digest(
                f"snapshot-{seed}"
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
            "source_plan_id": f"source-plan-{seed}",
            "source_plan_version": 1,
            "expected_previous_plan_version": 1,
            "current_plan_version": 1,
            "source_plan_created_at_s": 10.0,
            "intervention_timestamp_s": 12.0,
            "plan_valid_until_s": 30.0,
            "ppo_enabled": False,
            "online_assist_enabled": False,
            "online_authority_enabled": False,
            "rule_fallback_enabled": True,
        }
        control = PairedInterventionArmSpecification(
            arm_id=f"arm-{seed}-control",
            arm_kind=CONTROL_ARM,
            isolation_id=f"isolation-{seed}-control",
            planner_path=CONTROL_PLANNER_PATH,
            learning_cost_intervention_enabled=False,
            **common,
        )
        treatment = PairedInterventionArmSpecification(
            arm_id=f"arm-{seed}-treatment",
            arm_kind=TREATMENT_ARM,
            isolation_id=f"isolation-{seed}-treatment",
            planner_path=TREATMENT_PLANNER_PATH,
            learning_cost_intervention_enabled=True,
            **common,
        )
        pairs.append(
            PairedInterventionSeedPair(
                pair_id=f"pair-{seed}",
                seed=seed,
                control=control,
                treatment=treatment,
            )
        )
    return PairedInterventionSpecification(
        experiment_id="isolated-rollout-unit",
        experiment_version="isolated-rollout-unit-v1",
        reserved_seed_policy_version=(
            PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1
        ),
        reserved_seeds=PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
        paired_evaluator_schema_version=SHADOW_EVALUATION_SCHEMA_V2,
        runtime_ack_evidence_schema_version=(
            D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1
        ),
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


def _plan(*, plan_id: str = "isolated-plan-v2", version: int = 2) -> AssignmentPlan:
    assignments = tuple(
        Assignment(
            target_id=f"global-track-{index}",
            resource_id=f"interceptor-{index}",
            cost=float(index + 1),
            cost_breakdown={"rule": float(index + 1)},
            plan_version=version,
            metadata={
                "current_plan_id": plan_id,
                "current_plan_version": version,
            },
        )
        for index in range(2)
    )
    return AssignmentPlan(
        plan_id=plan_id,
        version=version,
        window_id=1,
        assignments=assignments,
        unassigned_target_ids=(),
        total_cost=3.0,
        created_at=12.0,
        last_changed_at=12.0,
        human_authorization_state="offline_not_authorized",
        source_node_id="d3_offline_intervention",
        link_type="offline_isolated",
        resource_count=2,
        target_count=2,
        metadata={
            "isolated_simulation": True,
            "runtime_execution_allowed": False,
            "ppo_enabled": False,
            "online_assist_enabled": False,
            "online_authority_enabled": False,
        },
    )


def _arm(
    specification: PairedInterventionSpecification,
    arm_kind: str = CONTROL_ARM,
) -> tuple[str, PairedInterventionArmSpecification]:
    pair = specification.pairs[0]
    return (
        pair.pair_id,
        pair.control if arm_kind == CONTROL_ARM else pair.treatment,
    )


def _receipt(
    *,
    pair_id: str,
    arm: PairedInterventionArmSpecification,
    plan: AssignmentPlan,
) -> PairedInterventionExecutionReceipt:
    treatment = arm.arm_kind == TREATMENT_ARM
    return PairedInterventionExecutionReceipt(
        pair_id=pair_id,
        seed=arm.seed,
        arm_kind=arm.arm_kind,
        arm_spec_sha256=arm.fingerprint,
        paired_evaluator_schema_version=SHADOW_EVALUATION_SCHEMA_V2,
        paired_evaluator_report_sha256=_digest("paired-report"),
        input_snapshot_sha256=arm.observation_input_snapshot_sha256,
        rule_cost_matrix_sha256=_digest("rule-matrix"),
        action_mask_sha256=_digest("action-mask"),
        planner_path=arm.planner_path,
        source_plan_version=arm.source_plan_version,
        expected_previous_plan_version=arm.expected_previous_plan_version,
        current_plan_version=arm.current_plan_version,
        output_plan_id=plan.plan_id,
        output_plan_version=plan.version,
        output_plan_payload_sha256=(
            validated_assignment_plan_payload_sha256(plan)
        ),
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
        inference_elapsed_ms=0.2,
        nonfinite_value_count=0,
        online_label_key_count=0,
        global_track_id_rewrite_count=0,
    )


def _case() -> tuple[
    PairedInterventionSpecification,
    PairedInterventionArmSpecification,
    PairedInterventionExecutionReceipt,
    AssignmentPlan,
]:
    specification = _specification()
    pair_id, arm = _arm(specification)
    plan = _plan()
    return specification, arm, _receipt(pair_id=pair_id, arm=arm, plan=plan), plan


def test_build_validate_and_json_roundtrip_isolated_consumption() -> None:
    specification, arm, receipt, plan = _case()
    evidence = build_isolated_plan_consumption_evidence(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        plan=plan,
        rollout_cycle=0,
        consumption_timestamp_s=12.5,
    )
    payload = json.loads(json.dumps(evidence.to_dict(), allow_nan=False))
    validator = IsolatedPlanConsumptionValidator()
    validated = validator.validate_and_record(
        payload,
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        expected_plan=plan,
    )

    assert validated.accepted is True
    assert validated.assignment_count == validated.binding_count == 2
    assert validated.production_runtime_ack is False
    assert validated.isolated_simulation_only is True
    assert validated.physical_outcome_available is False
    assert validated.reward_available is False
    assert validated.causal_evidence_available is False
    assert validated.ppo_enabled is False
    assert validated.online_assist_enabled is False
    assert validated.online_authority_enabled is False
    assert validator.consumption_count == 1


def test_payload_hash_tamper_fails_closed() -> None:
    specification, arm, receipt, plan = _case()
    evidence = build_isolated_plan_consumption_evidence(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        plan=plan,
        rollout_cycle=0,
        consumption_timestamp_s=12.5,
    )
    payload = evidence.to_dict()
    payload["plan_payload_sha256"] = "f" * 64

    with pytest.raises(IsolatedPlanConsumptionError):
        validate_isolated_plan_consumption_evidence(
            payload,
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            expected_plan=plan,
        )


def test_duplicate_plan_consumption_fails_closed() -> None:
    specification, arm, receipt, plan = _case()
    evidence = build_isolated_plan_consumption_evidence(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        plan=plan,
        rollout_cycle=0,
        consumption_timestamp_s=12.5,
    )
    validator = IsolatedPlanConsumptionValidator()
    validator.validate_and_record(
        evidence,
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        expected_plan=plan,
    )

    with pytest.raises(IsolatedPlanConsumptionError) as exc_info:
        validator.validate_and_record(
            evidence.to_dict(),
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            expected_plan=plan,
        )
    assert exc_info.value.code == "duplicate_plan_consumption"


def test_wrong_arm_fails_closed() -> None:
    specification, arm, receipt, plan = _case()
    evidence = build_isolated_plan_consumption_evidence(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        plan=plan,
        rollout_cycle=0,
        consumption_timestamp_s=12.5,
    )
    pair_id, treatment_arm = _arm(specification, TREATMENT_ARM)
    treatment_receipt = _receipt(
        pair_id=pair_id,
        arm=treatment_arm,
        plan=plan,
    )

    with pytest.raises(IsolatedPlanConsumptionError) as exc_info:
        validate_isolated_plan_consumption_evidence(
            evidence,
            specification=specification,
            arm_specification=treatment_arm,
            execution_receipt=treatment_receipt,
            expected_plan=plan,
        )
    assert exc_info.value.code == "arm_identity_mismatch"


def test_wrong_plan_version_fails_closed() -> None:
    specification, arm, receipt, plan = _case()
    newer_plan = _plan(plan_id="isolated-plan-v3", version=3)
    newer_receipt = _receipt(
        pair_id=receipt.pair_id,
        arm=arm,
        plan=newer_plan,
    )
    evidence = build_isolated_plan_consumption_evidence(
        specification=specification,
        arm_specification=arm,
        execution_receipt=newer_receipt,
        plan=newer_plan,
        rollout_cycle=1,
        consumption_timestamp_s=13.0,
    )

    with pytest.raises(IsolatedPlanConsumptionError) as exc_info:
        validate_isolated_plan_consumption_evidence(
            evidence,
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            expected_plan=plan,
        )
    assert exc_info.value.code == "plan_identity_or_payload_mismatch"


def test_stale_plan_after_newer_consumption_fails_closed() -> None:
    specification, arm, _, _ = _case()
    newer_plan = _plan(plan_id="isolated-plan-v3", version=3)
    newer_receipt = _receipt(
        pair_id=specification.pairs[0].pair_id,
        arm=arm,
        plan=newer_plan,
    )
    old_plan = _plan(plan_id="isolated-plan-old-v2", version=2)
    old_receipt = _receipt(
        pair_id=specification.pairs[0].pair_id,
        arm=arm,
        plan=old_plan,
    )
    validator = IsolatedPlanConsumptionValidator()
    validator.validate_and_record(
        build_isolated_plan_consumption_evidence(
            specification=specification,
            arm_specification=arm,
            execution_receipt=newer_receipt,
            plan=newer_plan,
            rollout_cycle=1,
            consumption_timestamp_s=13.0,
        ),
        specification=specification,
        arm_specification=arm,
        execution_receipt=newer_receipt,
        expected_plan=newer_plan,
    )

    with pytest.raises(IsolatedPlanConsumptionError) as exc_info:
        validator.validate_and_record(
            build_isolated_plan_consumption_evidence(
                specification=specification,
                arm_specification=arm,
                execution_receipt=old_receipt,
                plan=old_plan,
                rollout_cycle=2,
                consumption_timestamp_s=14.0,
            ),
            specification=specification,
            arm_specification=arm,
            execution_receipt=old_receipt,
            expected_plan=old_plan,
        )
    assert exc_info.value.code == "stale_plan_version"


def test_source_snapshot_tamper_fails_closed() -> None:
    specification, arm, receipt, plan = _case()
    evidence = build_isolated_plan_consumption_evidence(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        plan=plan,
        rollout_cycle=0,
        consumption_timestamp_s=12.5,
    )
    payload = evidence.to_dict()
    payload["source_snapshot_lineage"][
        "observation_input_snapshot_sha256"
    ] = "e" * 64

    with pytest.raises(IsolatedPlanConsumptionError):
        validate_isolated_plan_consumption_evidence(
            payload,
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            expected_plan=plan,
        )


def test_production_runtime_ack_claim_fails_closed() -> None:
    specification, arm, receipt, plan = _case()
    evidence = build_isolated_plan_consumption_evidence(
        specification=specification,
        arm_specification=arm,
        execution_receipt=receipt,
        plan=plan,
        rollout_cycle=0,
        consumption_timestamp_s=12.5,
    )
    payload = evidence.to_dict()
    payload["production_runtime_ack"] = True

    with pytest.raises(IsolatedPlanConsumptionError) as exc_info:
        validate_isolated_plan_consumption_evidence(
            payload,
            specification=specification,
            arm_specification=arm,
            execution_receipt=receipt,
            expected_plan=plan,
        )
    assert exc_info.value.code == "production_runtime_ack_forbidden"
