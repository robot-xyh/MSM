from __future__ import annotations

from copy import deepcopy
from importlib import import_module
import json
from types import SimpleNamespace

import pytest

from d3_assignment_planner import (
    ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA_V1,
    D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1,
    Assignment,
    AssignmentPlan,
    AssignmentPlanRuntimeAckError,
    canonical_runtime_payload_sha256,
    validate_assignment_plan_runtime_ack,
)


def _plan(
    *,
    learning_mode: str | None = "shadow",
    learning_applied: bool | None = False,
    learning_shadow_only: bool | None = True,
    learning_bundle_loaded: bool | None = True,
    include_learning: bool = True,
) -> AssignmentPlan:
    metadata: dict[str, object] = {
        "active_plan_owner": "center",
        "owner_node_id": "C2",
        "authority_epoch": 3,
        "lease_expires_at_s": 15.0,
        "regional_hint_considered": True,
        "regional_hint_applied": False,
        "regional_hint_rejected": True,
        "regional_hint_fallback_reason": "quota_projection_rejected",
        "regional_hint_advisory_id": "ADV-9",
        "regional_hint_advisory_version": 9,
        "regional_hint_source_plan_id": "PLAN-OLD",
        "regional_hint_source_plan_version": 3,
    }
    if include_learning:
        metadata.update(
            {
                "learning_mode": learning_mode,
                "learning_applied": learning_applied,
                "learning_shadow_only": learning_shadow_only,
                "learning_bundle_loaded": learning_bundle_loaded,
                "learning_fallback_reason": None,
                "learning_model_fingerprint": "sha256:model-7",
                # A teacher diagnostic is not runtime reward evidence.
                "reward_components": {"rule_cost": -1.5},
            }
        )
    return AssignmentPlan(
        plan_id="PLAN-RUNTIME-7",
        version=4,
        window_id=4,
        assignments=(
            Assignment(
                target_id="GT-000001",
                resource_id="INT-001",
                cost=1.0,
                cost_breakdown={"total": 1.0},
                plan_version=4,
                coalition_id="COAL-GT-000001",
                coalition_version=7,
                member_role="primary",
                metadata={
                    "owner_node_id": "C2",
                    "regional_owner_layer": "center",
                    "regional_region_id": "region-0",
                    "regional_epoch": 3,
                    "regional_commit_mode": "single_member_authority",
                },
            ),
            Assignment(
                target_id="GT-000001",
                resource_id="INT-002",
                cost=1.2,
                cost_breakdown={"total": 1.2},
                plan_version=4,
                coalition_id="COAL-GT-000001",
                coalition_version=7,
                member_role="reserve",
                metadata={
                    "owner_node_id": "C2",
                    "regional_owner_layer": "center",
                    "regional_region_id": "region-0",
                    "regional_epoch": 3,
                    "regional_commit_mode": "single_member_authority",
                },
            ),
        ),
        unassigned_target_ids=(),
        total_cost=2.2,
        created_at=9.5,
        last_changed_at=9.5,
        solver_name="hungarian_demand_slots",
        metadata=metadata,
        resource_count=2,
        target_count=1,
    )


def _source_assignment(item: Assignment) -> dict[str, object]:
    return {
        "resource_id": item.resource_id,
        "global_track_id": item.target_id,
        "coalition_id": item.coalition_id,
        "coalition_version": item.coalition_version,
        "member_role": item.member_role,
        "owner_node_id": item.metadata.get("owner_node_id"),
        "regional_owner_layer": item.metadata.get("regional_owner_layer"),
        "regional_region_id": item.metadata.get("regional_region_id"),
        "regional_epoch": item.metadata.get("regional_epoch"),
        "regional_commit_mode": item.metadata.get("regional_commit_mode"),
    }


def _evidence_bundle(
    plan: AssignmentPlan,
    *,
    with_guidance: bool = True,
) -> tuple[dict[str, object], dict[str, object], dict[str, object] | None]:
    timestamp = 10.0
    plan_payload: dict[str, object] = {
        "timestamp": timestamp,
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "created_at": plan.created_at,
        "assignment_count": len(plan.assignments),
        "target_count": plan.target_count,
        "resource_count": plan.resource_count,
        "assignments": [_source_assignment(item) for item in plan.assignments],
        "unassigned_global_track_ids": list(plan.unassigned_target_ids),
        "solver_name": plan.solver_name,
        "metadata": dict(plan.metadata),
    }
    d3_source: dict[str, object] = {
        "sequence": 11,
        "topic": "modules.d3.assignment_plan",
        "source": "D3",
        "timestamp": timestamp,
        "schema_version": plan.plan_schema,
        "payload": plan_payload,
    }

    guidance_source: dict[str, object] | None = None
    commands: list[dict[str, object]] = []
    if with_guidance:
        commands = [
            {
                "resource_id": "INT-001",
                "global_track_id": "GT-000001",
                "plan_id": plan.plan_id,
                "plan_version": plan.version,
                "mode": "midcourse_pn",
                "acceleration_ned_mps2": [0.2, 0.1, 0.0],
                "command_norm_mps2": 0.22360679775,
                "gate_reason": "midcourse_position_guidance",
                "visual_switch_allowed": False,
            },
            {
                "resource_id": "INT-002",
                "global_track_id": "GT-000001",
                "plan_id": plan.plan_id,
                "plan_version": plan.version,
                "mode": "hold",
                "acceleration_ned_mps2": [0.0, 0.0, 0.0],
                "command_norm_mps2": 0.0,
                "gate_reason": "coalition_not_activated",
                "visual_switch_allowed": False,
            },
        ]
        guidance_payload = {
            "timestamp": timestamp,
            "command_count": 2,
            "mode_counts": {"hold": 1, "midcourse_pn": 1},
            "commands": commands,
        }
        guidance_source = {
            "sequence": 12,
            "topic": "modules.d7.guidance_commands",
            "source": "D7",
            "timestamp": timestamp,
            "schema_version": "d7-scalable3d-guidance-v1",
            "payload": guidance_payload,
        }

    binding_acks = []
    commands_by_resource = {
        str(item["resource_id"]): item for item in commands
    }
    for assignment in plan.assignments:
        command = commands_by_resource.get(assignment.resource_id)
        mode = None if command is None else command["mode"]
        binding_acks.append(
            {
                "resource_id": assignment.resource_id,
                "global_track_id": assignment.target_id,
                "coalition_id": assignment.coalition_id,
                "coalition_version": assignment.coalition_version,
                "member_role": assignment.member_role,
                "guidance_command_present": command is not None,
                "guidance_mode": mode,
                "guidance_gate_reason": (
                    None if command is None else command["gate_reason"]
                ),
                "control_applied_to_world": command is not None,
                "held": command is None or mode == "hold",
            }
        )
    metadata = plan.metadata
    learning = {
        key: metadata.get(metadata_key)
        for key, metadata_key in (
            ("mode", "learning_mode"),
            ("applied", "learning_applied"),
            ("shadow_only", "learning_shadow_only"),
            ("bundle_loaded", "learning_bundle_loaded"),
            ("fallback_reason", "learning_fallback_reason"),
            ("model_fingerprint", "learning_model_fingerprint"),
        )
        if metadata_key in metadata
    }
    regional = {
        "considered": metadata.get("regional_hint_considered"),
        "applied": metadata.get("regional_hint_applied"),
        "rejected": metadata.get("regional_hint_rejected"),
        "fallback_reason": metadata.get("regional_hint_fallback_reason"),
        "advisory_id": metadata.get("regional_hint_advisory_id"),
        "advisory_version": metadata.get("regional_hint_advisory_version"),
        "source_plan_id": metadata.get("regional_hint_source_plan_id"),
        "source_plan_version": metadata.get("regional_hint_source_plan_version"),
    }
    present_count = sum(item["guidance_command_present"] for item in binding_acks)
    applied_count = sum(item["control_applied_to_world"] for item in binding_acks)
    held_count = sum(item["held"] for item in binding_acks)
    acknowledgement: dict[str, object] = {
        "decision_id": f"{plan.plan_id}:v{plan.version}",
        "ack_timestamp": timestamp,
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "plan_created_at": plan.created_at,
        "plan_schema_version": plan.plan_schema,
        "source_plan_bus_sequence": 11,
        "source_plan_payload_sha256": canonical_runtime_payload_sha256(
            plan_payload
        ),
        "source_guidance_bus_sequence": (
            None if guidance_source is None else 12
        ),
        "source_guidance_payload_sha256": (
            None
            if guidance_source is None
            else canonical_runtime_payload_sha256(guidance_source["payload"])
        ),
        "accepted": True,
        "status_code": "accepted_by_main_runtime",
        "assignment_count": len(plan.assignments),
        "binding_ack_count": present_count,
        "fully_bound_to_guidance": present_count == len(plan.assignments),
        "control_applied_binding_count": applied_count,
        "held_binding_count": held_count,
        "active_plan_owner": metadata.get("active_plan_owner"),
        "owner_node_id": metadata.get("owner_node_id"),
        "authority_epoch": metadata.get("authority_epoch"),
        "lease_expires_at_s": metadata.get("lease_expires_at_s"),
        "d3_learning_evidence": learning,
        "d4_regional_hint_evidence": regional,
        "binding_acks": binding_acks,
        "physical_outcome_available": False,
        "reward_available": False,
    }
    return acknowledgement, d3_source, guidance_source


def _validate(
    plan: AssignmentPlan,
    ack: dict[str, object],
    d3_source: dict[str, object],
    d7_source: dict[str, object] | None,
):
    return validate_assignment_plan_runtime_ack(
        envelope_schema=ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA_V1,
        acknowledgement=ack,
        d3_source_publication=d3_source,
        d7_source_publication=d7_source,
        expected_plan=plan,
    )


def _assert_code(code: str, call) -> None:
    with pytest.raises(AssignmentPlanRuntimeAckError) as caught:
        call()
    assert caught.value.code == code
    assert caught.value.reason == code


def _refresh_plan_hash(
    ack: dict[str, object], d3_source: dict[str, object]
) -> None:
    ack["source_plan_payload_sha256"] = canonical_runtime_payload_sha256(
        d3_source["payload"]
    )


def _refresh_guidance_hash(
    ack: dict[str, object], d7_source: dict[str, object]
) -> None:
    ack["source_guidance_payload_sha256"] = canonical_runtime_payload_sha256(
        d7_source["payload"]
    )


def test_valid_shadow_ack_is_read_only_serializable_and_not_applied_learning() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    original = (deepcopy(plan), deepcopy(ack), deepcopy(d3_source), deepcopy(d7_source))

    evidence = _validate(plan, ack, d3_source, d7_source)

    assert evidence.binding_ack_count == 2
    assert evidence.control_applied_binding_count == 2
    assert evidence.held_binding_count == 1
    assert evidence.fully_bound_to_guidance is True
    assert evidence.runtime_learning_applied_ack_available is False
    assert evidence.d3_learning_evidence.mode == "shadow"
    serialized = evidence.to_dict()
    assert serialized["schema_version"] == D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1
    assert serialized["status"] == "verified"
    assert serialized["assignment_plan_mutated"] is False
    json.dumps(serialized, allow_nan=False, sort_keys=True)
    assert (plan, ack, d3_source, d7_source) == original


def test_loaded_assist_applied_ack_is_the_only_learning_available_case() -> None:
    plan = _plan(
        learning_mode="assist",
        learning_applied=True,
        learning_shadow_only=False,
        learning_bundle_loaded=True,
    )
    ack, d3_source, d7_source = _evidence_bundle(plan)

    evidence = _validate(plan, ack, d3_source, d7_source)

    assert evidence.runtime_learning_applied_ack_available is True


def test_missing_learning_fields_and_accepted_plan_remain_unavailable() -> None:
    plan = _plan(include_learning=False)
    ack, d3_source, d7_source = _evidence_bundle(plan)

    evidence = _validate(plan, ack, d3_source, d7_source)

    assert evidence.accepted is True
    assert evidence.d3_learning_evidence.mode is None
    assert evidence.runtime_learning_applied_ack_available is False


def test_no_guidance_source_is_valid_but_all_bindings_hold() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan, with_guidance=False)

    evidence = _validate(plan, ack, d3_source, d7_source)

    assert d7_source is None
    assert evidence.binding_ack_count == 0
    assert evidence.control_applied_binding_count == 0
    assert evidence.held_binding_count == 2
    assert evidence.fully_bound_to_guidance is False


def test_wrong_ack_schema_fails_closed() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    _assert_code(
        "ack_envelope_schema_mismatch",
        lambda: validate_assignment_plan_runtime_ack(
            envelope_schema="wrong-v1",
            acknowledgement=ack,
            d3_source_publication=d3_source,
            d7_source_publication=d7_source,
            expected_plan=plan,
        ),
    )


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("source_plan_payload_sha256", "source_plan_payload_sha256_mismatch"),
        (
            "source_guidance_payload_sha256",
            "source_guidance_payload_sha256_mismatch",
        ),
    ],
)
def test_source_payload_hash_mismatch_fails_closed(field: str, code: str) -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    ack[field] = "0" * 64
    _assert_code(code, lambda: _validate(plan, ack, d3_source, d7_source))


def test_stale_plan_version_fails_closed() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    ack["plan_version"] = plan.version - 1
    _assert_code(
        "stale_plan_version",
        lambda: _validate(plan, ack, d3_source, d7_source),
    )


def test_stale_d7_plan_version_fails_closed_after_hash_verification() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    assert d7_source is not None
    d7_source["payload"]["commands"][0]["plan_version"] = plan.version - 1
    _refresh_guidance_hash(ack, d7_source)
    _assert_code(
        "stale_plan_version",
        lambda: _validate(plan, ack, d3_source, d7_source),
    )


def test_nonpositive_source_sequence_fails_closed() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    d3_source["sequence"] = 0
    ack["source_plan_bus_sequence"] = 0
    _assert_code(
        "positive_integer_required",
        lambda: _validate(plan, ack, d3_source, d7_source),
    )


def test_duplicate_binding_ack_fails_closed() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    ack["binding_acks"][1] = deepcopy(ack["binding_acks"][0])
    _assert_code(
        "duplicate_assignment_binding_ack",
        lambda: _validate(plan, ack, d3_source, d7_source),
    )


def test_missing_binding_ack_fails_closed() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    ack["binding_acks"].pop()
    _assert_code(
        "missing_assignment_binding_ack",
        lambda: _validate(plan, ack, d3_source, d7_source),
    )


def test_extra_binding_ack_fails_closed() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    extra = deepcopy(ack["binding_acks"][0])
    extra["resource_id"] = "INT-999"
    ack["binding_acks"].append(extra)
    _assert_code(
        "extra_assignment_binding_ack",
        lambda: _validate(plan, ack, d3_source, d7_source),
    )


def test_global_track_rebinding_fails_closed() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    ack["binding_acks"][1]["global_track_id"] = "GT-REBOUND"
    _assert_code(
        "global_track_id_mismatch",
        lambda: _validate(plan, ack, d3_source, d7_source),
    )


def test_source_plan_global_track_mismatch_fails_closed() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    d3_source["payload"]["assignments"][1]["global_track_id"] = "GT-REBOUND"
    _refresh_plan_hash(ack, d3_source)
    _assert_code(
        "source_plan_global_track_id_mismatch",
        lambda: _validate(plan, ack, d3_source, d7_source),
    )


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("physical_outcome_available", "physical_outcome_sidecar_required"),
        ("reward_available", "reward_sidecar_required"),
    ],
)
def test_self_asserted_outcome_or_reward_fails_closed(
    field: str, code: str
) -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    ack[field] = True
    _assert_code(code, lambda: _validate(plan, ack, d3_source, d7_source))


def test_shadow_claiming_applied_learning_fails_closed() -> None:
    plan = _plan(
        learning_mode="shadow",
        learning_applied=True,
        learning_shadow_only=True,
        learning_bundle_loaded=True,
    )
    ack, d3_source, d7_source = _evidence_bundle(plan)
    _assert_code(
        "learning_evidence_inconsistent",
        lambda: _validate(plan, ack, d3_source, d7_source),
    )


def test_incorrect_fully_bound_statistic_fails_closed() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    ack["fully_bound_to_guidance"] = False
    _assert_code(
        "fully_bound_statistic_mismatch",
        lambda: _validate(plan, ack, d3_source, d7_source),
    )


def test_nonfinite_ack_timestamp_fails_closed() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    ack["ack_timestamp"] = float("nan")
    _assert_code(
        "nonfinite_or_negative_time",
        lambda: _validate(plan, ack, d3_source, d7_source),
    )


def test_missing_referenced_guidance_publication_fails_closed() -> None:
    plan = _plan()
    ack, d3_source, _ = _evidence_bundle(plan)
    _assert_code(
        "source_guidance_publication_missing",
        lambda: _validate(plan, ack, d3_source, None),
    )


def test_public_consumer_validates_real_namespaced_main_3v3_runtime_ack() -> None:
    from research_modules.scalable_3d_simulation.models import ScenarioConfig
    from research_modules.scalable_3d_simulation.module_stack import (
        IntegratedScalableModuleStack,
    )
    from research_modules.scalable_3d_simulation.orchestrator import run_episode

    config = ScenarioConfig(
        scenario_name="d3_runtime_ack_import_identity_3v3",
        scenario_version="d3-runtime-ack-import-identity-v1",
        target_count=3,
        resource_count=3,
        recon_count=1,
        region_count=2,
        duration_s=1.2,
        seed=7,
        radar_detection_probability=1.0,
    )
    stack = IntegratedScalableModuleStack()
    result = run_episode(config, module_stack=stack)
    acknowledgements = tuple(
        item
        for item in result.online_messages
        if item.topic == "runtime.assignment_plan_ack"
    )
    assert acknowledgements
    assert stack.latest_plan is not None
    assert type(stack.latest_plan).__module__ != AssignmentPlan.__module__
    assert type(stack.latest_plan).__module__.endswith(
        "d3_assignment_planner.models"
    )

    ack_envelope = acknowledgements[-1]
    acknowledgement = ack_envelope.payload
    source_by_sequence = {
        item.sequence: item for item in result.online_messages
    }
    d3_source = source_by_sequence[
        acknowledgement["source_plan_bus_sequence"]
    ]
    guidance_sequence = acknowledgement["source_guidance_bus_sequence"]
    d7_source = (
        None
        if guidance_sequence is None
        else source_by_sequence[guidance_sequence]
    )

    evidence = validate_assignment_plan_runtime_ack(
        envelope_schema=ack_envelope.schema_version,
        acknowledgement=acknowledgement,
        d3_source_publication=d3_source.to_dict(),
        d7_source_publication=(
            None if d7_source is None else d7_source.to_dict()
        ),
        expected_plan=stack.latest_plan,
    )

    assert len(acknowledgements) == 2
    assert evidence.assignment_count == 3
    assert evidence.binding_ack_count == 3
    assert evidence.control_applied_binding_count == 3
    assert evidence.held_binding_count == 0
    assert evidence.fully_bound_to_guidance is True
    assert evidence.runtime_learning_applied_ack_available is False
    assert result.summary["online_truth_use_count"] == 0


def test_namespaced_consumer_accepts_top_level_d3_plan_identity() -> None:
    namespaced_consumer = import_module(
        "research_modules.d3_assignment_planner.src."
        "d3_assignment_planner.runtime_plan_ack"
    )
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)

    evidence = namespaced_consumer.validate_assignment_plan_runtime_ack(
        envelope_schema=ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA_V1,
        acknowledgement=ack,
        d3_source_publication=d3_source,
        d7_source_publication=d7_source,
        expected_plan=plan,
    )

    assert type(plan).__module__ == "d3_assignment_planner.models"
    assert evidence.plan_id == plan.plan_id
    assert evidence.assignment_count == 2


def test_consumer_rejects_unconstrained_plan_duck_type() -> None:
    plan = _plan()
    ack, d3_source, d7_source = _evidence_bundle(plan)
    lookalike = SimpleNamespace(**plan.__dict__)

    _assert_code(
        "expected_plan_type_invalid",
        lambda: validate_assignment_plan_runtime_ack(
            envelope_schema=ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA_V1,
            acknowledgement=ack,
            d3_source_publication=d3_source,
            d7_source_publication=d7_source,
            expected_plan=lookalike,
        ),
    )
