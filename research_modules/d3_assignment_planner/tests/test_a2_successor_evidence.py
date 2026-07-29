from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from commitment_test_support import committed_target_track
from d3_assignment_planner import (
    A2_ATTRIBUTION_SCOPE,
    A2CurrentLineageIdentity,
    A2SuccessorEvidenceError,
    AssignmentPlanner,
    PlannerConfig,
    REGIONAL_PLANNING_HINT_SCHEMA_V1,
    ResourceState,
    build_a2_successor_evidence_batch,
    build_a2_successor_plan_evidence,
    canonical_runtime_payload_sha256,
    load_a2_current_lineage_identity,
    load_a2_successor_evidence_batch,
    validate_a2_successor_plan_evidence,
    write_a2_successor_evidence_batch,
)


_MODEL_SHA = "1" * 64
_SOURCE_SHA = "2" * 64


def _planner() -> AssignmentPlanner:
    return AssignmentPlanner(
        config=PlannerConfig.scalable_3d(
            enable_hysteresis=False,
            max_candidate_edges_per_target=16,
            human_authorization_state="approved",
            source_node_id="CENTER",
        )
    )


def _track(target_id: str, region_id: str, x: float):
    return committed_target_track(
        target_id,
        threat_score=0.9,
        covariance=0.1,
        window_cost=0.0,
        position_ned=(x, 0.0, -100.0),
        velocity_ned=(0.0, 0.0, 0.0),
        region_id=region_id,
    )


def _resource(
    resource_id: str,
    region_id: str,
    x: float,
    *,
    status: str = "available",
) -> ResourceState:
    return ResourceState(
        resource_id,
        status=status,
        position_ned=(x, 0.0, -100.0),
        velocity_ned=(0.0, 0.0, 0.0),
        max_speed_mps=20.0,
        max_intercept_range_m=10_000.0,
        region_id=region_id,
    )


def _inputs():
    tracks = (
        _track("T-A", "A", 100.0),
        _track("T-B", "B", 1_000.0),
        _track("T-C", "C", 2_000.0),
    )
    resources = (
        _resource("R-A0", "A", 90.0),
        _resource("R-A1", "A", 980.0),
        _resource("R-B0", "B", 990.0),
        _resource("R-C0", "C", 1_990.0),
        _resource("R-C1", "C", 2_500.0),
    )
    return tracks, resources


def _hint(source_plan) -> dict[str, object]:
    base = {
        "owner_id": "CENTER",
        "owner_layer": "center",
        "owner_epoch": 7,
        "lease_expires_at_s": 10.0,
        "source_plan_id": source_plan.plan_id,
        "source_plan_version": source_plan.version,
        "reserve_ratio": 0.0,
        "request_replan": True,
    }
    return {
        "schema": REGIONAL_PLANNING_HINT_SCHEMA_V1,
        "advisory_id": "a2-current-lineage-frame-0004",
        "advisory_version": 4,
        "created_at_s": 0.5,
        "expires_at_s": 10.0,
        "source_plan_id": source_plan.plan_id,
        "source_plan_version": source_plan.version,
        "projected": True,
        "constraints": [
            {
                **base,
                "region_id": "A",
                "resource_quota_delta": -1,
                "hold": False,
            },
            {
                **base,
                "region_id": "B",
                "resource_quota_delta": 1,
                "hold": False,
            },
            {
                **base,
                "region_id": "C",
                "resource_quota_delta": 0,
                "hold": True,
            },
        ],
        "transfer_allowances": [
            {
                "source_region_id": "A",
                "target_region_id": "B",
                "resource_count": 1,
                "edge_id": "A->B",
                "expected_transfer_time_s": 2.0,
            }
        ],
    }


def _plans():
    tracks, resources = _inputs()
    source = _planner().plan(tracks, resources, timestamp=0.0)
    source = replace(
        source,
        metadata={
            **dict(source.metadata),
            "authority_epoch": 7,
            "lease_expires_at_s": 10.0,
        },
    )
    next_resources = (
        resources[0],
        resources[1],
        _resource("R-B0", "B", 990.0, status="unavailable"),
        _resource("R-C0", "C", 2_400.0),
        _resource("R-C1", "C", 1_995.0),
    )
    r0 = _planner().plan(
        tracks,
        next_resources,
        timestamp=1.0,
        previous_plan=source,
        publish=False,
    )
    hint = _hint(source)
    successor = _planner().plan(
        tracks,
        next_resources,
        timestamp=1.0,
        previous_plan=source,
        regional_planning_hint=hint,
        publish=False,
    )
    return source, r0, successor, hint


def _identity() -> A2CurrentLineageIdentity:
    return A2CurrentLineageIdentity(
        candidate_id="region_resource_a2_current_lineage_development_v1",
        model_version="d4-region-a2-current-lineage-development-v1",
        candidate_manifest_file_sha256="3" * 64,
        candidate_manifest_content_sha256="4" * 64,
        model_state_sha256=_MODEL_SHA,
        source_identity_sha256=_SOURCE_SHA,
    )


def _action(
    region_id: str,
    *,
    before: int,
    committed: int,
    quota: int,
    hold: bool,
) -> dict[str, object]:
    effect_fields = []
    if quota:
        effect_fields.append("resource_quota")
    if hold:
        effect_fields.append("hold")
    effect_fields.append("request_replan")
    return {
        "schema": "d4-region-resource-actual-policy-action-diagnostic-v1",
        "region_id": region_id,
        "resources_before": before,
        "committed_resources": committed,
        "baseline_reserve_resources": 0,
        "raw_resource_quota_delta": quota,
        "raw_requested_reserve_resources": 0,
        "raw_hold": hold,
        "raw_request_replan": True,
        "projected_resource_quota_delta": quota,
        "projected_reserve_resources": 0,
        "projected_hold": hold,
        "projected_request_replan": True,
        "raw_effect_fields": effect_fields,
        "projected_effect_fields": effect_fields,
        "reason_codes": [],
    }


def _decision() -> dict[str, object]:
    return {
        "schema": "d4-region-resource-actual-policy-sample-diagnostic-v1",
        "scenario_id": "a2-unseen-shadow",
        "scenario_version": "a2-unseen-shadow-v1",
        "seed": 1000,
        "frame_index": 4,
        "snapshot_id": "snapshot-1000-4",
        "snapshot_sha256": "5" * 64,
        "candidate_id": _identity().candidate_id,
        "model_sha256": _MODEL_SHA,
        "confidence": 0.87,
        "minimum_confidence": 0.60,
        "latency_ms": 3.2,
        "latency_limit_ms": 50.0,
        "candidate_gate_passed": True,
        "candidate_ood_passed": True,
        "candidate_finite": True,
        "policy_output_structure_valid": True,
        "safety_projection_passed": True,
        "advisory_consumable": True,
        "actual_model_identity_verified": True,
        "identifiable_intervention_available": True,
        "intervention_fields": [
            "region:A:resource_quota",
            "region:A:request_replan",
            "region:B:resource_quota",
            "region:B:request_replan",
            "region:C:hold",
            "region:C:request_replan",
            "transfer:A->B",
        ],
        "raw_executable_signature_sha256": "6" * 64,
        "outcome": "safe_nonzero_actual_model",
        "reason_codes": [],
        "safe_nonzero_actual_model": True,
        "actions": [
            _action("A", before=2, committed=1, quota=-1, hold=False),
            _action("B", before=1, committed=1, quota=1, hold=False),
            _action("C", before=2, committed=1, quota=0, hold=True),
        ],
        "transfers": [
            {
                "schema": (
                    "d4-region-resource-actual-policy-transfer-diagnostic-v1"
                ),
                "source_region_id": "A",
                "target_region_id": "B",
                "edge_id": "A->B",
                "requested_resource_count": 1,
                "projected_resource_count": 1,
                "reason_codes": [],
            }
        ],
    }


def _evidence():
    source, r0, successor, hint = _plans()
    return build_a2_successor_plan_evidence(
        candidate_identity=_identity(),
        d4_decision_summary=_decision(),
        regional_hint=hint,
        source_plan=source,
        r0_plan=r0,
        successor_plan=successor,
        r0_input_summary_sha256="5" * 64,
        episode_id="episode-a2-1000",
    )


def _manifest_payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "d4-region-resource-current-lineage-candidate-v1",
        "candidate_id": _identity().candidate_id,
        "model_version": _identity().model_version,
        "source_identity_sha256": _SOURCE_SHA,
        "model_state_sha256": _MODEL_SHA,
        "artifact_files": {"bundle/state_dict.pt": _MODEL_SHA},
        "permissions": {
            "a2_admitted": False,
            "actual_adoption_claimed": False,
            "assignment_enabled": False,
            "assist_enabled": False,
            "authority_enabled": False,
            "benefit_claimed": False,
            "coalition_commit_enabled": False,
            "control_enabled": False,
            "takeover_enabled": False,
        },
        "lifecycle_stage": "development",
        "maximum_advisor_mode": "shadow",
        "development_shadow_candidate": True,
        "formal_holdout_evaluated": False,
    }
    payload["content_sha256"] = canonical_runtime_payload_sha256(payload)
    return payload


def _write_json(path: Path, payload: object) -> str:
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return sha256(path.read_bytes()).hexdigest()


def test_load_current_lineage_identity_keeps_all_permissions_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "current_lineage_candidate_manifest.json"
    digest = _write_json(path, _manifest_payload())

    identity = load_a2_current_lineage_identity(
        path, expected_file_sha256=digest
    )

    assert identity.candidate_id == _identity().candidate_id
    assert identity.model_state_sha256 == _MODEL_SHA
    assert identity.source_identity_sha256 == _SOURCE_SHA
    assert identity.candidate_manifest_file_sha256 == digest


def test_current_lineage_identity_rejects_open_permission(
    tmp_path: Path,
) -> None:
    payload = _manifest_payload()
    payload["permissions"]["assist_enabled"] = True  # type: ignore[index]
    unsigned = dict(payload)
    unsigned.pop("content_sha256")
    payload["content_sha256"] = canonical_runtime_payload_sha256(unsigned)
    path = tmp_path / "current_lineage_candidate_manifest.json"
    _write_json(path, payload)

    with pytest.raises(A2SuccessorEvidenceError) as error:
        load_a2_current_lineage_identity(path)

    assert error.value.reason == "candidate_manifest_permission_open"


def test_build_strict_successor_is_scoped_to_same_input_r0_delta() -> None:
    evidence = _evidence()

    assert evidence.strict_successor_verified is True
    assert evidence.same_input_r0_verified is True
    assert evidence.candidate_specific_execution_changed is True
    assert evidence.ordinary_periodic_replan_changed is True
    assert evidence.attribution_scope == A2_ATTRIBUTION_SCOPE
    assert evidence.successor_plan_version == evidence.source_plan_version + 1
    assert evidence.successor_previous_plan_id == evidence.source_plan_id
    assert evidence.successor_execution_signature_sha256 not in {
        evidence.source_execution_signature_sha256,
        evidence.r0_execution_signature_sha256,
    }
    assert all(
        getattr(evidence, name) is False
        for name in (
            "runtime_plan_ack_available",
            "owner_ack_available",
            "coalition_ack_available",
            "physical_window_available",
            "d7_execution_available",
            "benefit_available",
            "learning_assist_enabled",
            "assignment_authority_granted",
            "control_authority_granted",
        )
    )


def test_public_single_record_verifier_rechecks_content() -> None:
    evidence = _evidence()
    assert validate_a2_successor_plan_evidence(evidence) == evidence

    payload = evidence.to_dict()
    payload["source_owner_id"] = "ANOTHER-CENTER"
    with pytest.raises(A2SuccessorEvidenceError) as error:
        validate_a2_successor_plan_evidence(payload)

    assert (
        error.value.reason
        == "successor_evidence_content_sha256_mismatch"
    )


def test_batch_round_trip_supports_future_seed_inventory(
    tmp_path: Path,
) -> None:
    evidence = _evidence()
    batch = build_a2_successor_evidence_batch((evidence,))
    output = write_a2_successor_evidence_batch(
        batch, tmp_path / "a2_successors.json"
    )
    digest = sha256(output.read_bytes()).hexdigest()

    loaded = load_a2_successor_evidence_batch(
        output,
        expected_file_sha256=digest,
        expected_candidate_id=_identity().candidate_id,
        expected_model_state_sha256=_MODEL_SHA,
        expected_source_identity_sha256=_SOURCE_SHA,
        expected_seed_values=(1000,),
    )

    assert loaded == batch
    assert loaded.record_count == 1
    assert loaded.seed_values == (1000,)


def test_resource_infeasible_decision_cannot_form_evidence() -> None:
    source, r0, successor, hint = _plans()
    decision = _decision()
    decision["outcome"] = "resource_infeasible"
    decision["safe_nonzero_actual_model"] = False

    with pytest.raises(A2SuccessorEvidenceError) as error:
        build_a2_successor_plan_evidence(
            candidate_identity=_identity(),
            d4_decision_summary=decision,
            regional_hint=hint,
            source_plan=source,
            r0_plan=r0,
            successor_plan=successor,
            r0_input_summary_sha256="5" * 64,
            episode_id="episode-a2-1000",
        )

    assert error.value.reason == "d4_decision_not_safe_nonzero"


def test_projected_noop_cannot_form_evidence() -> None:
    source, r0, successor, hint = _plans()
    decision = _decision()
    decision["transfers"] = []
    for action in decision["actions"]:  # type: ignore[union-attr]
        action["projected_resource_quota_delta"] = 0
        action["projected_hold"] = False
        action["projected_request_replan"] = False
        action["projected_effect_fields"] = []

    with pytest.raises(A2SuccessorEvidenceError) as error:
        build_a2_successor_plan_evidence(
            candidate_identity=_identity(),
            d4_decision_summary=decision,
            regional_hint=hint,
            source_plan=source,
            r0_plan=r0,
            successor_plan=successor,
            r0_input_summary_sha256="5" * 64,
            episode_id="episode-a2-1000",
        )

    assert error.value.reason == "d4_projected_action_noop"


def test_stale_successor_version_cannot_form_evidence() -> None:
    source, r0, successor, hint = _plans()
    stale = replace(successor, version=source.version)

    with pytest.raises(A2SuccessorEvidenceError) as error:
        build_a2_successor_plan_evidence(
            candidate_identity=_identity(),
            d4_decision_summary=_decision(),
            regional_hint=hint,
            source_plan=source,
            r0_plan=r0,
            successor_plan=stale,
            r0_input_summary_sha256="5" * 64,
            episode_id="episode-a2-1000",
        )

    assert error.value.reason == "a2_successor_plan_version_invalid"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        (
            "candidate_id",
            "another-candidate",
            "d4_candidate_identity_mismatch",
        ),
        (
            "model_sha256",
            "9" * 64,
            "d4_model_state_identity_mismatch",
        ),
    ),
)
def test_candidate_identity_mismatch_is_rejected(
    field: str,
    value: str,
    reason: str,
) -> None:
    source, r0, successor, hint = _plans()
    decision = _decision()
    decision[field] = value

    with pytest.raises(A2SuccessorEvidenceError) as error:
        build_a2_successor_plan_evidence(
            candidate_identity=_identity(),
            d4_decision_summary=decision,
            regional_hint=hint,
            source_plan=source,
            r0_plan=r0,
            successor_plan=successor,
            r0_input_summary_sha256="5" * 64,
            episode_id="episode-a2-1000",
        )

    assert error.value.reason == reason


def test_candidate_plan_cannot_be_reused_as_r0_arm() -> None:
    source, _, successor, hint = _plans()

    with pytest.raises(A2SuccessorEvidenceError) as error:
        build_a2_successor_plan_evidence(
            candidate_identity=_identity(),
            d4_decision_summary=_decision(),
            regional_hint=hint,
            source_plan=source,
            r0_plan=successor,
            successor_plan=successor,
            r0_input_summary_sha256="5" * 64,
            episode_id="episode-a2-1000",
        )

    assert error.value.reason == "candidate_r0_arm_mixed"


def test_ordinary_replan_is_not_misattributed_when_candidate_matches_r0() -> None:
    source, r0, successor, hint = _plans()
    authority_keys = (
        "plan_owner",
        "active_plan_owner",
        "owner_node_id",
        "current_plan_owner",
        "current_plan_owner_node_id",
        "authority_epoch",
        "lease_expires_at_s",
    )
    same_authority_r0 = replace(
        r0,
        metadata={
            **dict(r0.metadata),
            **{
                key: successor.metadata[key]
                for key in authority_keys
            },
        },
    )
    indistinguishable = replace(
        successor,
        assignments=same_authority_r0.assignments,
        coalitions=same_authority_r0.coalitions,
        unassigned_target_ids=same_authority_r0.unassigned_target_ids,
        incomplete_target_ids=same_authority_r0.incomplete_target_ids,
    )
    assert (
        indistinguishable.execution_signature()
        == same_authority_r0.execution_signature()
    )

    with pytest.raises(A2SuccessorEvidenceError) as error:
        build_a2_successor_plan_evidence(
            candidate_identity=_identity(),
            d4_decision_summary=_decision(),
            regional_hint=hint,
            source_plan=source,
            r0_plan=same_authority_r0,
            successor_plan=indistinguishable,
            r0_input_summary_sha256="5" * 64,
            episode_id="episode-a2-1000",
        )

    assert error.value.reason == "a2_effect_not_distinct_from_r0"


def test_d4_action_must_equal_the_d3_consumed_hint() -> None:
    source, r0, successor, hint = _plans()
    decision = _decision()
    decision["actions"][0]["projected_resource_quota_delta"] = 0  # type: ignore[index]
    decision["actions"][0]["projected_effect_fields"] = [  # type: ignore[index]
        "request_replan"
    ]

    with pytest.raises(A2SuccessorEvidenceError) as error:
        build_a2_successor_plan_evidence(
            candidate_identity=_identity(),
            d4_decision_summary=decision,
            regional_hint=hint,
            source_plan=source,
            r0_plan=r0,
            successor_plan=successor,
            r0_input_summary_sha256="5" * 64,
            episode_id="episode-a2-1000",
        )

    assert error.value.reason == "d4_d3_projected_action_binding_mismatch"


def test_truth_field_and_input_mismatch_fail_closed() -> None:
    source, r0, successor, hint = _plans()
    decision = _decision()
    decision["truth_id"] = "target-actual"

    with pytest.raises(A2SuccessorEvidenceError) as error:
        build_a2_successor_plan_evidence(
            candidate_identity=_identity(),
            d4_decision_summary=decision,
            regional_hint=hint,
            source_plan=source,
            r0_plan=r0,
            successor_plan=successor,
            r0_input_summary_sha256="5" * 64,
            episode_id="episode-a2-1000",
        )
    assert error.value.reason == "online_truth_leakage"

    decision.pop("truth_id")
    with pytest.raises(A2SuccessorEvidenceError) as error:
        build_a2_successor_plan_evidence(
            candidate_identity=_identity(),
            d4_decision_summary=decision,
            regional_hint=hint,
            source_plan=source,
            r0_plan=r0,
            successor_plan=successor,
            r0_input_summary_sha256="7" * 64,
            episode_id="episode-a2-1000",
        )
    assert error.value.reason == "candidate_r0_input_summary_mismatch"


def test_serialized_batch_cannot_claim_runtime_or_benefit(
    tmp_path: Path,
) -> None:
    payload = build_a2_successor_evidence_batch((_evidence(),)).to_dict()
    payload["runtime_plan_ack_available"] = True
    unsigned = deepcopy(payload)
    unsigned.pop("content_sha256")
    payload["content_sha256"] = canonical_runtime_payload_sha256(unsigned)
    path = tmp_path / "forged.json"
    _write_json(path, payload)

    with pytest.raises(A2SuccessorEvidenceError) as error:
        load_a2_successor_evidence_batch(path)

    assert (
        error.value.reason
        == "successor_batch_runtime_or_authority_claim_forbidden"
    )


def test_duplicate_comparison_key_cannot_enter_batch() -> None:
    evidence = _evidence()
    with pytest.raises(A2SuccessorEvidenceError) as error:
        build_a2_successor_evidence_batch((evidence, evidence))

    assert error.value.reason == "successor_batch_comparison_key_duplicate"
