from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from d3_assignment_planner import (
    ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA_V1,
    ASSIGNMENT_PLAN_SCHEMA_V2,
    CONTROL_ARM,
    CONTROL_PLANNER_PATH,
    D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1,
    D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1,
    D3RuntimeLearningEvidence,
    D4RegionalHintRuntimeEvidence,
    D6_SIDECAR_OWNER,
    OFFLINE_INTERVENTION_SCOPE,
    PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1,
    PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
    SHADOW_EVALUATION_SCHEMA_V2,
    TREATMENT_ARM,
    TREATMENT_PLANNER_PATH,
    AssignmentPlanRuntimeAckEvidence,
    PairedInterventionArmSpecification,
    PairedInterventionContractError,
    PairedInterventionExecutionReceipt,
    PairedInterventionManifest,
    PairedInterventionRuntimeAckReference,
    PairedInterventionSeedPair,
    PairedInterventionSpecification,
    load_paired_intervention_manifest,
    write_paired_intervention_manifest,
)
from d3_assignment_planner.learning_cli import main as learning_cli_main


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _arm(
    seed: int,
    arm_kind: str,
    **overrides: object,
) -> PairedInterventionArmSpecification:
    values: dict[str, object] = {
        "arm_id": f"d3-paired-{seed}-{arm_kind}",
        "arm_kind": arm_kind,
        "seed": seed,
        "isolation_id": f"isolated-world-{seed}-{arm_kind}",
        "intervention_scope": OFFLINE_INTERVENTION_SCOPE,
        "planner_path": (
            CONTROL_PLANNER_PATH
            if arm_kind == CONTROL_ARM
            else TREATMENT_PLANNER_PATH
        ),
        "scenario_version": "scalable3d-d3-paired-v1",
        "scenario_config_sha256": _digest(f"scenario-{seed}"),
        "initial_world_state_sha256": _digest(f"world-{seed}"),
        "observation_input_snapshot_sha256": _digest(f"observation-{seed}"),
        "input_snapshot_schema_version": "scalable3d-d3-input-snapshot-v1",
        "d1_d2_lineage_contract_version": "d1-d2-online-lineage-v1",
        "d1_d2_lineage_contract_sha256": _digest("d1-d2-lineage"),
        "rule_cost_profile_version": "d3-rule-cost-v1",
        "rule_cost_config_sha256": _digest("rule-cost-config"),
        "d3_bundle_version": "d3-bc-residual-v0.1.0",
        "d3_bundle_sha256": _digest("frozen-d3-bundle"),
        "d3_bundle_frozen": True,
        "threshold_version": "d3-learning-threshold-v1",
        "threshold_config_sha256": _digest("frozen-thresholds"),
        "threshold_frozen": True,
        "safety_shell_version": "d3-deterministic-safety-shell-v1",
        "safety_shell_config_sha256": _digest("safety-shell"),
        "source_plan_id": f"source-plan-{seed}",
        "source_plan_version": 3,
        "expected_previous_plan_version": 3,
        "current_plan_version": 3,
        "source_plan_created_at_s": 10.0,
        "intervention_timestamp_s": 12.0,
        "plan_valid_until_s": 15.0,
        "learning_cost_intervention_enabled": arm_kind == TREATMENT_ARM,
        "ppo_enabled": False,
        "online_assist_enabled": False,
        "online_authority_enabled": False,
        "rule_fallback_enabled": True,
    }
    values.update(overrides)
    return PairedInterventionArmSpecification(**values)


def _specification() -> PairedInterventionSpecification:
    pairs = tuple(
        PairedInterventionSeedPair(
            pair_id=f"d3-pair-{seed}",
            seed=seed,
            control=_arm(seed, CONTROL_ARM),
            treatment=_arm(seed, TREATMENT_ARM),
        )
        for seed in PAIRED_INTERVENTION_RESERVED_SEEDS_V1
    )
    return PairedInterventionSpecification(
        experiment_id="d3-rule-vs-residual-heldout",
        experiment_version="d3-paired-intervention-v1",
        reserved_seed_policy_version=PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1,
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
        pairs=pairs,
    )


def _receipt(
    pair: PairedInterventionSeedPair,
    arm_kind: str,
    *,
    fallback: bool = False,
    **overrides: object,
) -> PairedInterventionExecutionReceipt:
    arm = pair.control if arm_kind == CONTROL_ARM else pair.treatment
    treatment = arm_kind == TREATMENT_ARM
    values: dict[str, object] = {
        "pair_id": pair.pair_id,
        "seed": pair.seed,
        "arm_kind": arm_kind,
        "arm_spec_sha256": arm.fingerprint,
        "paired_evaluator_schema_version": SHADOW_EVALUATION_SCHEMA_V2,
        "paired_evaluator_report_sha256": _digest("paired-evaluator-report"),
        "input_snapshot_sha256": arm.observation_input_snapshot_sha256,
        "rule_cost_matrix_sha256": _digest(f"rule-matrix-{pair.seed}"),
        "action_mask_sha256": _digest(f"action-mask-{pair.seed}"),
        "planner_path": arm.planner_path,
        "source_plan_version": arm.source_plan_version,
        "expected_previous_plan_version": arm.expected_previous_plan_version,
        "current_plan_version": arm.current_plan_version,
        "output_plan_id": f"output-plan-{pair.seed}-{arm_kind}",
        "output_plan_version": arm.current_plan_version + 1,
        "output_plan_payload_sha256": _digest(
            f"output-plan-{pair.seed}-{arm_kind}"
        ),
        "isolated_simulation": True,
        "learning_cost_applied": treatment and not fallback,
        "rule_matrix_unchanged": True,
        "deterministic_action_mask_enforced": True,
        "reachability_gate_enforced": True,
        "capacity_gate_enforced": True,
        "version_gate_enforced": True,
        "hysteresis_gate_enforced": True,
        "safety_gate_enforced": True,
        "rule_fallback_available": True,
        "rule_fallback_applied": treatment and fallback,
        "fallback_reason": "out_of_distribution" if treatment and fallback else None,
        "hysteresis_decision": "accepted_gain_and_dwell",
        "inference_elapsed_ms": 0.7,
        "nonfinite_value_count": 0,
        "online_label_key_count": 0,
        "global_track_id_rewrite_count": 0,
    }
    values.update(overrides)
    return PairedInterventionExecutionReceipt(**values)


def _receipts(
    specification: PairedInterventionSpecification,
    *,
    fallback_seed: int | None = None,
) -> tuple[PairedInterventionExecutionReceipt, ...]:
    return tuple(
        _receipt(
            pair,
            arm_kind,
            fallback=(arm_kind == TREATMENT_ARM and pair.seed == fallback_seed),
        )
        for pair in specification.pairs
        for arm_kind in (CONTROL_ARM, TREATMENT_ARM)
    )


def _runtime_ack(
    receipt: PairedInterventionExecutionReceipt,
) -> AssignmentPlanRuntimeAckEvidence:
    learning_applied = receipt.learning_cost_applied
    return AssignmentPlanRuntimeAckEvidence(
        ack_envelope_schema=ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA_V1,
        decision_id=f"{receipt.output_plan_id}:v{receipt.output_plan_version}",
        ack_timestamp=20.0,
        plan_id=receipt.output_plan_id,
        plan_version=receipt.output_plan_version,
        plan_created_at=19.0,
        plan_schema_version=ASSIGNMENT_PLAN_SCHEMA_V2,
        source_plan_bus_sequence=100,
        source_plan_payload_sha256=_digest(
            f"source-plan-{receipt.seed}-{receipt.arm_kind}"
        ),
        source_guidance_bus_sequence=101,
        source_guidance_payload_sha256=_digest(
            f"source-guidance-{receipt.seed}-{receipt.arm_kind}"
        ),
        accepted=True,
        status_code="accepted_current_plan",
        assignment_count=1,
        binding_ack_count=1,
        fully_bound_to_guidance=True,
        control_applied_binding_count=1,
        held_binding_count=0,
        active_plan_owner="isolated_d3_experiment",
        owner_node_id="D3-EXPERIMENT",
        authority_epoch=1,
        lease_expires_at_s=30.0,
        d3_learning_evidence=D3RuntimeLearningEvidence(
            mode="assist" if learning_applied else "disabled",
            applied=learning_applied,
            shadow_only=False,
            bundle_loaded=True,
            fallback_reason=(
                receipt.fallback_reason if receipt.rule_fallback_applied else None
            ),
            model_fingerprint=_digest("frozen-d3-bundle"),
            runtime_applied_ack_available=True,
        ),
        d4_regional_hint_evidence=D4RegionalHintRuntimeEvidence(
            considered=False,
            applied=False,
            rejected=False,
            fallback_reason=None,
            advisory_id=None,
            advisory_version=None,
            source_plan_id=None,
            source_plan_version=None,
        ),
        binding_acks=(),
        physical_outcome_available=False,
        reward_available=False,
    )


def _assert_manifest_error(payload: dict[str, object], code: str) -> None:
    with pytest.raises(PairedInterventionContractError) as captured:
        PairedInterventionManifest.from_dict(payload)
    assert captured.value.code == code


def test_specification_only_manifest_round_trip_keeps_evidence_layers_separate() -> None:
    manifest = PairedInterventionManifest(specification=_specification())
    payload = manifest.to_dict()

    restored = PairedInterventionManifest.from_dict(payload)
    layers = payload["availability"]

    assert restored.to_dict() == payload
    assert layers["paired_input_equivalence"]["value"] is True
    assert layers["paired_input_equivalence"]["seed_count"] == 20
    assert (
        layers["treatment_safely_applied_in_isolated_simulation"]["status"]
        == "unavailable"
    )
    assert layers["runtime_ack"]["status"] == "unavailable"
    assert layers["outcome"]["status"] == "unavailable"
    assert layers["counterfactual"]["status"] == "unavailable"
    assert layers["causal"]["status"] == "unavailable"
    assert payload["admission"] == {
        "ppo_allowed": False,
        "online_assist_allowed": False,
        "online_authority_allowed": False,
        "rule_fallback_required": True,
    }
    json.dumps(payload, allow_nan=False, sort_keys=True)


def test_manifest_cli_performs_strict_json_round_trip(tmp_path, capsys) -> None:
    source = tmp_path / "source.json"
    output = tmp_path / "canonical.json"
    manifest = PairedInterventionManifest(specification=_specification())
    write_paired_intervention_manifest(source, manifest)

    assert (
        learning_cli_main(
            [
                "validate-paired-intervention",
                "--input",
                str(source),
                "--output",
                str(output),
            ]
        )
        == 0
    )

    restored = load_paired_intervention_manifest(output)
    stdout = json.loads(capsys.readouterr().out)
    assert restored.fingerprint == manifest.fingerprint
    assert stdout["manifest_sha256"] == manifest.fingerprint
    assert stdout["admission"]["ppo_allowed"] is False
    assert stdout["outcome"]["status"] == "unavailable"


def test_all_twenty_treatment_arms_can_be_declared_safely_applied() -> None:
    specification = _specification()
    manifest = PairedInterventionManifest(
        specification=specification,
        execution_receipts=_receipts(specification),
    )

    layer = manifest.availability[
        "treatment_safely_applied_in_isolated_simulation"
    ]
    assert layer == {
        "status": "available",
        "available": True,
        "value": True,
        "reason": None,
        "applied_seed_count": 20,
        "fallback_seed_count": 0,
    }
    assert manifest.availability["outcome"]["available"] is False
    assert manifest.availability["counterfactual"]["available"] is False
    assert manifest.availability["causal"]["available"] is False


def test_treatment_rule_fallback_is_safe_but_not_a_completed_intervention() -> None:
    specification = _specification()
    manifest = PairedInterventionManifest(
        specification=specification,
        execution_receipts=_receipts(specification, fallback_seed=1007),
    )

    layer = manifest.availability[
        "treatment_safely_applied_in_isolated_simulation"
    ]
    assert layer["available"] is True
    assert layer["value"] is False
    assert layer["applied_seed_count"] == 19
    assert layer["fallback_seed_count"] == 1


def test_verified_runtime_ack_references_reuse_existing_ack_contract() -> None:
    specification = _specification()
    receipts = _receipts(specification)
    references = tuple(
        PairedInterventionRuntimeAckReference.from_verified_ack(
            receipt=receipt,
            acknowledgement=_runtime_ack(receipt),
        )
        for receipt in receipts
    )
    manifest = PairedInterventionManifest(
        specification=specification,
        execution_receipts=receipts,
        runtime_ack_references=references,
    )

    layer = manifest.availability["runtime_ack"]
    assert layer["status"] == "available"
    assert layer["reference_count"] == 40
    assert layer["accepted_count"] == 40
    assert PairedInterventionManifest.from_dict(manifest.to_dict()).to_dict() == (
        manifest.to_dict()
    )


def test_partial_runtime_ack_inventory_is_reported_without_outcome_claim() -> None:
    specification = _specification()
    receipts = _receipts(specification)
    first = receipts[0]
    manifest = PairedInterventionManifest(
        specification=specification,
        execution_receipts=receipts,
        runtime_ack_references=(
            PairedInterventionRuntimeAckReference.from_verified_ack(
                receipt=first,
                acknowledgement=_runtime_ack(first),
            ),
        ),
    )

    assert manifest.availability["runtime_ack"]["status"] == "partial"
    assert manifest.availability["runtime_ack"]["available"] is False
    assert manifest.availability["outcome"]["available"] is False


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda payload: payload["specification"]["pairs"][0].pop("treatment"),
            "seed_pair_fields_mismatch",
        ),
        (
            lambda payload: (
                payload["specification"]["pairs"][1].update({"seed": 1000}),
                payload["specification"]["pairs"][1]["control"].update(
                    {"seed": 1000}
                ),
                payload["specification"]["pairs"][1]["treatment"].update(
                    {"seed": 1000}
                ),
            ),
            "duplicate_seed_pair",
        ),
        (
            lambda payload: payload["specification"]["pairs"][0][
                "treatment"
            ].update({"scenario_config_sha256": _digest("different")}),
            "paired_input_mismatch",
        ),
        (
            lambda payload: payload["specification"]["pairs"][0][
                "treatment"
            ].update({"initial_world_state_sha256": _digest("different")}),
            "paired_input_mismatch",
        ),
        (
            lambda payload: payload["specification"]["pairs"][0][
                "treatment"
            ].update({"observation_input_snapshot_sha256": _digest("different")}),
            "paired_input_mismatch",
        ),
        (
            lambda payload: payload["specification"]["pairs"][0]["control"].update(
                {"d3_bundle_frozen": False}
            ),
            "d3_bundle_not_frozen",
        ),
        (
            lambda payload: payload["specification"]["pairs"][0]["control"].update(
                {"threshold_frozen": False}
            ),
            "threshold_not_frozen",
        ),
        (
            lambda payload: payload["specification"].update({"ppo_enabled": True}),
            "ppo_must_remain_disabled",
        ),
        (
            lambda payload: payload["specification"]["pairs"][0]["treatment"].update(
                {"online_assist_enabled": True}
            ),
            "online_assist_must_remain_disabled",
        ),
        (
            lambda payload: payload["specification"]["pairs"][0]["treatment"].update(
                {"online_authority_enabled": True}
            ),
            "online_authority_must_remain_disabled",
        ),
        (
            lambda payload: payload["specification"].update(
                {"rule_fallback_enabled": False}
            ),
            "rule_fallback_disabled",
        ),
        (
            lambda payload: payload["specification"]["pairs"][0]["control"].update(
                {"current_plan_version": 4}
            ),
            "stale_plan_version",
        ),
        (
            lambda payload: payload["specification"]["pairs"][0]["control"].update(
                {"intervention_timestamp_s": 16.0}
            ),
            "stale_plan_time_window",
        ),
        (
            lambda payload: payload["specification"]["pairs"].pop(),
            "reserved_seed_pair_inventory_mismatch",
        ),
        (
            lambda payload: payload["specification"]["pairs"][0].update(
                {"truth_target_id": "forbidden"}
            ),
            "online_truth_leakage",
        ),
        (
            lambda payload: payload["specification"]["pairs"][0]["control"].update(
                {"intervention_timestamp_s": float("nan")}
            ),
            "nonfinite_value",
        ),
    ],
)
def test_manifest_contract_failures_close_before_evidence_claims(
    mutate,
    expected_code: str,
) -> None:
    payload = deepcopy(PairedInterventionManifest(_specification()).to_dict())
    mutate(payload)
    _assert_manifest_error(payload, expected_code)


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"deterministic_action_mask_enforced": False}, "deterministic_safety_gate_missing"),
        ({"reachability_gate_enforced": False}, "deterministic_safety_gate_missing"),
        ({"capacity_gate_enforced": False}, "deterministic_safety_gate_missing"),
        ({"version_gate_enforced": False}, "deterministic_safety_gate_missing"),
        ({"hysteresis_gate_enforced": False}, "deterministic_safety_gate_missing"),
        ({"safety_gate_enforced": False}, "deterministic_safety_gate_missing"),
        ({"rule_fallback_available": False}, "deterministic_safety_gate_missing"),
        ({"current_plan_version": 4}, "stale_plan_version"),
        ({"nonfinite_value_count": 1}, "nonfinite_value_count_nonzero"),
        ({"online_label_key_count": 1}, "online_label_key_count_nonzero"),
        ({"global_track_id_rewrite_count": 1}, "global_track_id_rewrite_count_nonzero"),
        (
            {
                "learning_cost_applied": False,
                "rule_fallback_applied": False,
                "fallback_reason": None,
            },
            "treatment_without_learning_or_rule_fallback",
        ),
    ],
)
def test_treatment_execution_receipt_fails_closed_on_unsafe_claims(
    overrides: dict[str, object],
    expected_code: str,
) -> None:
    pair = _specification().pairs[0]
    with pytest.raises(PairedInterventionContractError) as captured:
        _receipt(pair, TREATMENT_ARM, **overrides)
    assert captured.value.code == expected_code


def test_partial_execution_arm_inventory_fails_closed() -> None:
    specification = _specification()
    receipts = _receipts(specification)
    with pytest.raises(PairedInterventionContractError) as captured:
        PairedInterventionManifest(
            specification=specification,
            execution_receipts=receipts[:-1],
        )
    assert captured.value.code == "execution_receipt_arm_inventory_incomplete"


def test_runtime_ack_must_match_the_isolated_output_plan() -> None:
    receipt = _receipts(_specification())[1]
    acknowledgement = _runtime_ack(receipt)
    acknowledgement = AssignmentPlanRuntimeAckEvidence(
        **{
            **acknowledgement.__dict__,
            "plan_version": acknowledgement.plan_version + 1,
        }
    )
    with pytest.raises(PairedInterventionContractError) as captured:
        PairedInterventionRuntimeAckReference.from_verified_ack(
            receipt=receipt,
            acknowledgement=acknowledgement,
        )
    assert captured.value.code == "runtime_ack_plan_mismatch"
