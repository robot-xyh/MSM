from __future__ import annotations

from copy import deepcopy
from importlib import import_module
import json

import pytest

from d3_assignment_planner import (
    ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA_V1,
    FORMAL_REWARD_COMPONENT_NAMES,
    Assignment,
    AssignmentPlan,
    RuntimePlanRewardEvidenceError,
    build_runtime_plan_window_reward_evidence,
    canonical_reward_evidence_payload_sha256,
    canonical_runtime_payload_sha256,
    validate_assignment_plan_runtime_ack,
)


_SOURCE_NAMES = (
    "online_observations",
    "d2_identity_evaluation",
    "d2_identity_manifest",
    "d2_online_d1_records",
    "d2_online_d2_records",
    "d2_observation_truth_labels",
    "d2_identity_evidence",
    "offline_truth_state",
    "offline_proximity_intercepts",
    "episode_manifest",
    "scenario_config",
)


def _digest_token(value: str) -> str:
    return canonical_reward_evidence_payload_sha256({"source": value})


def _runtime_ack(*, held: bool = False, include_owner: bool = True):
    metadata: dict[str, object] = {
        "active_plan_owner": "center" if include_owner else None,
        "owner_node_id": "C2" if include_owner else None,
        "authority_epoch": 3,
        "lease_expires_at_s": 30.0,
        "learning_mode": "shadow",
        "learning_applied": False,
        "learning_shadow_only": True,
        "learning_bundle_loaded": True,
        "learning_fallback_reason": None,
        "learning_model_fingerprint": "sha256:model-7",
        "regional_hint_considered": True,
        "regional_hint_applied": False,
        "regional_hint_rejected": True,
        "regional_hint_fallback_reason": "quota_projection_rejected",
        "regional_hint_advisory_id": "ADV-9",
        "regional_hint_advisory_version": 9,
        "regional_hint_source_plan_id": "PLAN-OLD",
        "regional_hint_source_plan_version": 3,
    }
    assignment = Assignment(
        target_id="GT-000001",
        resource_id="INT-001",
        cost=1.0,
        cost_breakdown={"total": 1.0},
        plan_version=4,
        coalition_id="COAL-GT-000001",
        coalition_version=7,
        member_role="primary",
        metadata={
            "owner_node_id": "C2" if include_owner else None,
            "regional_owner_layer": "center" if include_owner else None,
            "regional_region_id": "region-0",
            "regional_epoch": 3,
            "regional_commit_mode": "single_member_authority",
        },
    )
    plan = AssignmentPlan(
        plan_id="PLAN-RUNTIME-7",
        version=4,
        window_id=4,
        assignments=(assignment,),
        unassigned_target_ids=(),
        total_cost=1.0,
        created_at=9.5,
        last_changed_at=9.5,
        solver_name="hungarian_demand_slots",
        metadata=metadata,
        resource_count=1,
        target_count=1,
    )
    source_assignment = {
        "resource_id": assignment.resource_id,
        "global_track_id": assignment.target_id,
        "coalition_id": assignment.coalition_id,
        "coalition_version": assignment.coalition_version,
        "member_role": assignment.member_role,
        "owner_node_id": assignment.metadata.get("owner_node_id"),
        "regional_owner_layer": assignment.metadata.get("regional_owner_layer"),
        "regional_region_id": assignment.metadata.get("regional_region_id"),
        "regional_epoch": assignment.metadata.get("regional_epoch"),
        "regional_commit_mode": assignment.metadata.get("regional_commit_mode"),
    }
    plan_payload = {
        "timestamp": 10.0,
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "created_at": plan.created_at,
        "assignment_count": 1,
        "target_count": 1,
        "resource_count": 1,
        "assignments": [source_assignment],
        "unassigned_global_track_ids": [],
        "solver_name": plan.solver_name,
        "metadata": metadata,
    }
    plan_source = {
        "sequence": 10,
        "topic": "modules.d3.assignment_plan",
        "source": "D3",
        "timestamp": 10.0,
        "schema_version": plan.plan_schema,
        "payload": plan_payload,
    }
    mode = "hold" if held else "midcourse_pn_3d"
    command = {
        "resource_id": "INT-001",
        "global_track_id": "GT-000001",
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "mode": mode,
        "gate_reason": "coalition_not_activated" if held else "midcourse_position_guidance",
    }
    guidance_payload = {
        "timestamp": 10.0,
        "command_count": 1,
        "mode_counts": {mode: 1},
        "commands": [command],
    }
    guidance_source = {
        "sequence": 11,
        "topic": "modules.d7.guidance_commands",
        "source": "D7",
        "timestamp": 10.0,
        "schema_version": "d7-scalable3d-guidance-v1",
        "payload": guidance_payload,
    }
    learning = {
        "mode": "shadow",
        "applied": False,
        "shadow_only": True,
        "bundle_loaded": True,
        "fallback_reason": None,
        "model_fingerprint": "sha256:model-7",
    }
    regional = {
        "considered": True,
        "applied": False,
        "rejected": True,
        "fallback_reason": "quota_projection_rejected",
        "advisory_id": "ADV-9",
        "advisory_version": 9,
        "source_plan_id": "PLAN-OLD",
        "source_plan_version": 3,
    }
    ack = {
        "decision_id": "PLAN-RUNTIME-7:v4",
        "ack_timestamp": 10.0,
        "plan_id": "PLAN-RUNTIME-7",
        "plan_version": 4,
        "plan_created_at": 9.5,
        "plan_schema_version": plan.plan_schema,
        "source_plan_bus_sequence": 10,
        "source_plan_payload_sha256": canonical_runtime_payload_sha256(plan_payload),
        "source_guidance_bus_sequence": 11,
        "source_guidance_payload_sha256": canonical_runtime_payload_sha256(
            guidance_payload
        ),
        "accepted": True,
        "status_code": "accepted_by_main_runtime",
        "assignment_count": 1,
        "binding_ack_count": 1,
        "fully_bound_to_guidance": True,
        "control_applied_binding_count": 1,
        "held_binding_count": int(held),
        "active_plan_owner": metadata["active_plan_owner"],
        "owner_node_id": metadata["owner_node_id"],
        "authority_epoch": 3,
        "lease_expires_at_s": 30.0,
        "d3_learning_evidence": learning,
        "d4_regional_hint_evidence": regional,
        "binding_acks": [
            {
                "resource_id": "INT-001",
                "global_track_id": "GT-000001",
                "coalition_id": "COAL-GT-000001",
                "coalition_version": 7,
                "member_role": "primary",
                "guidance_command_present": True,
                "guidance_mode": mode,
                "guidance_gate_reason": command["gate_reason"],
                "control_applied_to_world": True,
                "held": held,
            }
        ],
        "physical_outcome_available": False,
        "reward_available": False,
    }
    return validate_assignment_plan_runtime_ack(
        envelope_schema=ASSIGNMENT_PLAN_RUNTIME_ACK_SCHEMA_V1,
        acknowledgement=ack,
        d3_source_publication=plan_source,
        d7_source_publication=guidance_source,
        expected_plan=plan,
    )


def _window(*, held: bool = False) -> dict[str, object]:
    diagnostic: dict[str, object]
    if held:
        diagnostic = {
            "name": "bounded_assigned_pair_best_distance_progress_v1",
            "available": False,
            "value": None,
            "reason": "d7_binding_held",
            "range": [-1.0, 1.0],
            "formal_reward": False,
            "causal": False,
            "counterfactual": False,
        }
    else:
        diagnostic = {
            "name": "bounded_assigned_pair_best_distance_progress_v1",
            "available": True,
            "value": 0.75,
            "reason": None,
            "range": [-1.0, 1.0],
            "formula": "clip((d_start-d_min)/max(d_start-5m,epsilon),-1,1)",
            "formal_reward": False,
            "causal": False,
            "counterfactual": False,
        }
    return {
        "ack_bus_sequence": 12,
        "decision_id": "PLAN-RUNTIME-7:v4",
        "occurrence_id": "PLAN-RUNTIME-7:v4@ack-seq-12@t-10.000000000",
        "occurrence_index": 1,
        "adoption_kind": "new_plan_identity",
        "plan_id": "PLAN-RUNTIME-7",
        "plan_version": 4,
        "execution_signature_sha256": _digest_token("execution-v4"),
        "resource_id": "INT-001",
        "global_track_id": "GT-000001",
        "coalition_id": "COAL-GT-000001",
        "coalition_version": 7,
        "member_role": "primary",
        "window_start_timestamp": 10.0,
        "window_end_timestamp": 20.0,
        "window_interval": "closed",
        "identity_mapping": {
            "available": True,
            "truth_target_id": "TGT-OFFLINE-0001",
            "reason": None,
        },
        "state_window_available": True,
        "state_window_reason": None,
        "state_sample_count": 21,
        "first_state_timestamp": 10.0,
        "last_state_timestamp": 20.0,
        "start_3d_distance_m": 25.0,
        "end_3d_distance_m": 12.0,
        "min_3d_distance_m": 10.0,
        "distance_progress_m": 13.0,
        "best_distance_progress_m": 15.0,
        "assigned_pair_proximity_event_observed": True,
        "assigned_pair_proximity_events": [
            {
                "resource_id": "INT-001",
                "truth_target_id": "TGT-OFFLINE-0001",
                "timestamp": 15.0,
                "distance_m": 4.5,
            }
        ],
        "other_target_proximity_event_observed": False,
        "other_target_proximity_events": [],
        "guidance_command_present": True,
        "guidance_mode": "hold" if held else "midcourse_pn_3d",
        "guidance_gate_reason": (
            "coalition_not_activated" if held else "midcourse_position_guidance"
        ),
        "control_applied_to_world": True,
        "held": held,
        "d3_learning_evidence": {
            "mode": "shadow",
            "applied": False,
            "shadow_only": True,
            "bundle_loaded": True,
            "fallback_reason": None,
            "model_fingerprint": "sha256:model-7",
        },
        "d4_regional_hint_evidence": {
            "considered": True,
            "applied": False,
            "rejected": True,
            "fallback_reason": "quota_projection_rejected",
            "advisory_id": "ADV-9",
            "advisory_version": 9,
            "source_plan_id": "PLAN-OLD",
            "source_plan_version": 3,
        },
        "bounded_pair_progress_diagnostic": diagnostic,
        "formal_d3_ppo_reward_available": False,
        "formal_d3_ppo_reward": None,
        "formal_d3_ppo_reward_reason": (
            "bounded_pair_progress_is_not_a_formal_d3_ppo_reward"
        ),
        "counterfactual_available": False,
        "counterfactual": None,
        "counterfactual_reason": "same_seed_paired_formal_shadow_unavailable",
        "causal_attribution_available": False,
        "causal_attribution": None,
        "causal_attribution_reason": (
            "controlled_intervention_or_paired_causal_evidence_unavailable"
        ),
    }


def _report(*, held: bool = False) -> dict[str, object]:
    artifact_hashes = {name: _digest_token(name) for name in _SOURCE_NAMES}
    return {
        "schema_version": "d6.runtime-plan-outcome-join.v1",
        "evaluation_date": "2026-07-21",
        "evaluation_mode": "offline_read_only_fail_closed",
        "episode": {
            "episode_id": "episode-runtime-reward-001",
            "scenario_name": "runtime reward contract",
            "scenario_version": "runtime-reward-contract-v1",
            "seed": 41,
            "target_count": 1,
            "resource_count": 1,
            "duration_s": 20.0,
            "physics_dt_s": 0.5,
            "manifest_sha256": artifact_hashes["episode_manifest"],
            "scenario_config_sha256": artifact_hashes["scenario_config"],
            "config_canonical_sha256": _digest_token("config-canonical"),
        },
        "source_artifacts": {
            name: {
                "path": f"/verified/{name}",
                "sha256": digest,
                "verified": True,
            }
            for name, digest in artifact_hashes.items()
        },
        "runtime_ack_evidence": {
            "available": True,
            "reason": None,
            "ack_count": 1,
            "unique_occurrence_count": 1,
            "new_plan_identity_occurrence_count": 1,
            "same_identity_refresh_occurrence_count": 0,
            "same_identity_evaluation_refresh_occurrence_count": 0,
            "same_identity_plan_refresh_occurrence_count": 0,
            "binding_count": 1,
            "source_sequence_and_payload_hash_verified": True,
            "online_truth_use_count": 0,
            "d3_learning_applied_ack_count": 0,
            "d4_regional_applied_ack_count": 0,
        },
        "binding_windows": [_window(held=held)],
        "observed_diagnostics": {
            "bounded_pair_progress_name": (
                "bounded_assigned_pair_best_distance_progress_v1"
            ),
            "bounded_pair_progress_available_count": int(not held),
            "assigned_pair_five_meter_event_count": 1,
            "same_resource_other_target_event_count": 0,
            "formal_reward_available": False,
            "formal_reward": None,
            "formal_reward_reason": (
                "bounded_pair_progress_is_not_a_formal_d3_ppo_reward"
            ),
            "counterfactual_available": False,
            "counterfactual": None,
            "counterfactual_reason": "same_seed_paired_formal_shadow_unavailable",
            "causal_attribution_available": False,
            "causal_attribution": None,
            "causal_attribution_reason": (
                "controlled_intervention_or_paired_causal_evidence_unavailable"
            ),
        },
        "admission": {
            "runtime_ack_join_available": True,
            "observed_pair_diagnostic_available": not held,
            "formal_same_seed_paired_shadow_available": False,
            "held_out_seed_performance_available": False,
            "formal_learning_adoption_outcome_available": False,
            "ppo_allowed": False,
            "assist_allowed": False,
            "authority_allowed": False,
            "rule_fallback_required": True,
            "status": "runtime_observed_diagnostic_only_admission_closed",
            "promotion_blockers": [
                "formal_same_seed_paired_shadow_unavailable",
                "held_out_seed_performance_unavailable",
                "counterfactual_and_causal_attribution_unavailable",
                "formal_ppo_reward_unavailable",
                "multi_seed_learning_adoption_outcome_evidence_unavailable",
            ],
        },
        "audit": {
            "passed": True,
            "fail_closed": True,
            "source_mutation_performed": False,
            "frozen_900_episode_data_modified": False,
            "violation_count": 0,
            "violations": [],
        },
    }


def _build(ack, report: dict[str, object]):
    return build_runtime_plan_window_reward_evidence(
        runtime_ack_evidence=ack,
        ack_bus_sequence=12,
        d6_outcome_join=report,
        expected_d6_outcome_join_sha256=(
            canonical_reward_evidence_payload_sha256(report)
        ),
        resource_id="INT-001",
        global_track_id="GT-000001",
    )


def _assert_code(code: str, call) -> None:
    with pytest.raises(RuntimePlanRewardEvidenceError) as captured:
        call()
    assert captured.value.code == code


def test_valid_join_separates_observation_from_formal_reward() -> None:
    evidence = _build(_runtime_ack(), _report())
    payload = evidence.to_dict()

    reference = payload["reference"]
    assert reference["source_plan_bus_sequence"] == 10
    assert reference["consumption_bus_sequence"] == 11
    assert reference["ack_bus_sequence"] == 12
    assert reference["active_plan_owner"] == "center"
    assert reference["owner_node_id"] == "C2"
    assert payload["evidence_layers"]["command"]["available"] is True
    assert payload["evidence_layers"]["ack_applied"]["available"] is True
    progress = payload["evidence_layers"]["observed_outcome"][
        "bounded_assigned_pair_best_distance_progress"
    ]
    assert progress["available"] is True
    assert progress["value"] == 0.75
    assert progress["formal_reward_eligible"] is False
    assert payload["evidence_layers"]["paired"]["available"] is False
    assert payload["evidence_layers"]["counterfactual"]["available"] is False
    assert payload["evidence_layers"]["causal"]["available"] is False
    five_meter = payload["evidence_layers"]["observed_outcome"][
        "assigned_pair_five_meter_event"
    ]
    assert five_meter["available"] is True
    assert five_meter["value"] is True
    assert five_meter["formal_reward_eligible"] is False
    assert tuple(payload["raw_reward_components"]) == FORMAL_REWARD_COMPONENT_NAMES
    assert all(
        item["available"] is False and item["value"] is None and item["reason"]
        for item in payload["raw_reward_components"].values()
    )
    assert payload["formal_reward"]["available"] is False
    assert payload["formal_reward"]["value"] is None
    assert payload["admission"] == {
        "ppo_allowed": False,
        "assist_allowed": False,
        "authority_allowed": False,
        "rule_fallback_required": True,
    }
    serialized = json.dumps(payload, allow_nan=False, sort_keys=True)
    assert "TGT-OFFLINE" not in serialized
    assert '"truth_target_id"' not in serialized


def test_held_binding_keeps_ack_applied_and_progress_unavailable() -> None:
    evidence = _build(_runtime_ack(held=True), _report(held=True)).to_dict()

    assert evidence["evidence_layers"]["command"]["available"] is True
    applied = evidence["evidence_layers"]["ack_applied"]
    assert applied["available"] is False
    assert applied["reason"] == "d7_binding_held"
    progress = evidence["evidence_layers"]["observed_outcome"][
        "bounded_assigned_pair_best_distance_progress"
    ]
    assert progress["available"] is False
    assert progress["reason"] == "d7_binding_held"


def test_missing_runtime_ack_fails_closed() -> None:
    report = _report()
    _assert_code("runtime_ack_missing", lambda: _build(None, report))


def test_owner_is_required_for_attribution() -> None:
    report = _report()
    _assert_code(
        "required_text_missing",
        lambda: _build(_runtime_ack(include_owner=False), report),
    )


def test_outcome_payload_hash_mismatch_fails_closed() -> None:
    report = _report()
    _assert_code(
        "d6_outcome_join_sha256_mismatch",
        lambda: build_runtime_plan_window_reward_evidence(
            runtime_ack_evidence=_runtime_ack(),
            ack_bus_sequence=12,
            d6_outcome_join=report,
            expected_d6_outcome_join_sha256="0" * 64,
            resource_id="INT-001",
            global_track_id="GT-000001",
        ),
    )


def test_overlapping_binding_windows_fail_closed() -> None:
    report = _report()
    first = report["binding_windows"][0]
    first["window_interval"] = "left_closed_right_open"
    second = deepcopy(first)
    second.update(
        {
            "ack_bus_sequence": 13,
            "occurrence_id": "PLAN-RUNTIME-7:v4@ack-seq-13@t-15.000000000",
            "occurrence_index": 2,
            "adoption_kind": "same_identity_evaluation_refresh",
            "window_start_timestamp": 15.0,
            "window_end_timestamp": 20.0,
            "window_interval": "closed",
        }
    )
    report["binding_windows"].append(second)

    _assert_code(
        "binding_window_overlap",
        lambda: _build(_runtime_ack(), report),
    )


def test_refresh_semantics_mismatch_fails_closed() -> None:
    report = _report()
    report["binding_windows"][0]["occurrence_index"] = 2

    _assert_code(
        "refresh_semantics_mismatch",
        lambda: _build(_runtime_ack(), report),
    )


def test_version_regression_in_outcome_windows_fails_closed() -> None:
    report = _report()
    current = report["binding_windows"][0]
    prior = deepcopy(current)
    prior.update(
        {
            "ack_bus_sequence": 8,
            "decision_id": "PLAN-RUNTIME-7:v5",
            "occurrence_id": "PLAN-RUNTIME-7:v5@ack-seq-8@t-0.000000000",
            "plan_version": 5,
            "execution_signature_sha256": _digest_token("execution-v5"),
            "window_start_timestamp": 0.0,
            "window_end_timestamp": 10.0,
            "window_interval": "left_closed_right_open",
        }
    )
    report["binding_windows"] = [prior, current]

    _assert_code("stale_plan_version", lambda: _build(_runtime_ack(), report))


def test_online_truth_leakage_fails_closed() -> None:
    report = _report()
    report["runtime_ack_evidence"]["online_truth_use_count"] = 1

    _assert_code("online_truth_leakage", lambda: _build(_runtime_ack(), report))


def test_missing_window_field_fails_closed() -> None:
    report = _report()
    report["binding_windows"][0].pop("execution_signature_sha256")

    _assert_code(
        "d6_binding_window_fields_mismatch",
        lambda: _build(_runtime_ack(), report),
    )


@pytest.mark.parametrize(
    ("available_key", "value_key", "code"),
    [
        (
            "formal_d3_ppo_reward_available",
            "formal_d3_ppo_reward",
            "d6_formal_reward_claim_not_supported",
        ),
        (
            "counterfactual_available",
            "counterfactual",
            "d6_counterfactual_claim_not_supported",
        ),
        (
            "causal_attribution_available",
            "causal_attribution",
            "d6_causal_claim_not_supported",
        ),
    ],
)
def test_unsupported_reward_or_attribution_claim_fails_closed(
    available_key: str,
    value_key: str,
    code: str,
) -> None:
    report = _report()
    window = report["binding_windows"][0]
    window[available_key] = True
    window[value_key] = 1.0

    _assert_code(code, lambda: _build(_runtime_ack(), report))


def test_wrong_binding_and_sequence_order_fail_closed() -> None:
    report = _report()
    _assert_code(
        "runtime_ack_binding_missing_or_ambiguous",
        lambda: build_runtime_plan_window_reward_evidence(
            runtime_ack_evidence=_runtime_ack(),
            ack_bus_sequence=12,
            d6_outcome_join=report,
            expected_d6_outcome_join_sha256=(
                canonical_reward_evidence_payload_sha256(report)
            ),
            resource_id="INT-999",
            global_track_id="GT-000001",
        ),
    )
    _assert_code(
        "runtime_sequence_order_invalid",
        lambda: build_runtime_plan_window_reward_evidence(
            runtime_ack_evidence=_runtime_ack(),
            ack_bus_sequence=11,
            d6_outcome_join=report,
            expected_d6_outcome_join_sha256=(
                canonical_reward_evidence_payload_sha256(report)
            ),
            resource_id="INT-001",
            global_track_id="GT-000001",
        ),
    )


def test_namespaced_consumer_accepts_verified_top_level_ack_identity() -> None:
    consumer = import_module(
        "research_modules.d3_assignment_planner.src."
        "d3_assignment_planner.runtime_reward_evidence"
    )
    report = _report()

    result = consumer.build_runtime_plan_window_reward_evidence(
        runtime_ack_evidence=_runtime_ack(),
        ack_bus_sequence=12,
        d6_outcome_join=report,
        expected_d6_outcome_join_sha256=(
            consumer.canonical_reward_evidence_payload_sha256(report)
        ),
        resource_id="INT-001",
        global_track_id="GT-000001",
    )

    assert result.reference.plan_id == "PLAN-RUNTIME-7"
    assert result.formal_reward.available is False


def test_real_main_d6_report_builds_observed_only_d3_evidence(tmp_path) -> None:
    from research_modules.scalable_3d_simulation.models import ScenarioConfig
    from research_modules.scalable_3d_simulation.module_stack import (
        IntegratedScalableModuleStack,
    )
    from research_modules.scalable_3d_simulation.orchestrator import run_episode

    stack = IntegratedScalableModuleStack()
    plan_by_source_payload_sha256: dict[str, AssignmentPlan] = {}
    original_d3_publication = stack._d3_publication

    def capture_d3_plan_at_publication(now: float):
        publication = original_d3_publication(now)
        assert stack.latest_plan is not None
        plan_by_source_payload_sha256[
            canonical_runtime_payload_sha256(publication.payload)
        ] = deepcopy(stack.latest_plan)
        return publication

    stack._d3_publication = capture_d3_plan_at_publication
    result = run_episode(
        ScenarioConfig(
            scenario_name="d3-runtime-reward-real-join",
            scenario_version="d3-runtime-reward-real-join-v1",
            target_count=3,
            resource_count=3,
            recon_count=1,
            region_count=2,
            duration_s=1.2,
            seed=41,
            radar_detection_probability=1.0,
            acoustic_enabled=False,
            visual_enabled=False,
        ),
        module_stack=stack,
        output_dir=tmp_path,
    )
    acknowledgements = tuple(
        item
        for item in result.online_messages
        if item.topic == "runtime.assignment_plan_ack"
    )
    assert acknowledgements
    by_sequence = {item.sequence: item for item in result.online_messages}
    verified_acknowledgements = []
    for ack_envelope in acknowledgements:
        ack_payload = ack_envelope.payload
        plan_source = by_sequence[ack_payload["source_plan_bus_sequence"]]
        guidance_source = by_sequence[ack_payload["source_guidance_bus_sequence"]]
        expected_plan = plan_by_source_payload_sha256[
            canonical_runtime_payload_sha256(plan_source.payload)
        ]
        verified_acknowledgements.append(
            (
                ack_envelope,
                validate_assignment_plan_runtime_ack(
                    envelope_schema=ack_envelope.schema_version,
                    acknowledgement=ack_payload,
                    d3_source_publication=plan_source.to_dict(),
                    d7_source_publication=guidance_source.to_dict(),
                    expected_plan=expected_plan,
                ),
            )
        )

    ack_envelope, verified_ack, binding = next(
        (ack_envelope, verified_ack, binding)
        for ack_envelope, verified_ack in verified_acknowledgements
        for binding in verified_ack.binding_acks
        if binding.guidance_command_present and not binding.held
    )
    assert ack_envelope.sequence == acknowledgements[0].sequence
    last_binding_acks = verified_acknowledgements[-1][1].binding_acks
    assert last_binding_acks
    assert all(
        item.held and item.guidance_gate_reason == "global_track_stale"
        for item in last_binding_acks
    )
    report = json.loads(
        (
            tmp_path
            / "d6_runtime_plan_outcomes"
            / "runtime_plan_outcome_join.json"
        ).read_text(encoding="utf-8")
    )

    evidence = build_runtime_plan_window_reward_evidence(
        runtime_ack_evidence=verified_ack,
        ack_bus_sequence=ack_envelope.sequence,
        d6_outcome_join=report,
        expected_d6_outcome_join_sha256=(
            canonical_reward_evidence_payload_sha256(report)
        ),
        resource_id=binding.resource_id,
        global_track_id=binding.global_track_id,
    )

    assert evidence.reference.ack_bus_sequence == ack_envelope.sequence
    assert evidence.ack_applied.available is True
    assert evidence.formal_reward.available is False
    assert evidence.to_dict()["audit"]["online_truth_use_count"] == 0
