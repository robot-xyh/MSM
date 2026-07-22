from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from d4_distributed_fallback.region_resource import (
    RecommendationSource,
    RegionResourceAction,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RegionTransferSuggestion,
    ShadowPairedEvaluator,
)
from d4_distributed_fallback.region_resource_paired_intervention import (
    REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_BINDING,
    REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_ID,
    REGION_RESOURCE_FROZEN_DEVELOPMENT_MANIFEST_SHA256,
    REGION_RESOURCE_FROZEN_DEVELOPMENT_STATE_DICT_SHA256,
    REGION_RESOURCE_FROZEN_DEVELOPMENT_TRAINING_MANIFEST_SHA256,
    REGION_RESOURCE_PAIRED_ARM_EVIDENCE_SCHEMA,
    REGION_RESOURCE_PAIRED_ARM_EVIDENCE_SCHEMA_V1,
    REGION_RESOURCE_PAIRED_MANIFEST_SCHEMA,
    REGION_RESOURCE_PAIRED_SPEC_SCHEMA,
    REGION_RESOURCE_RESERVED_EVALUATION_SEEDS,
    RegionResourceCandidateBundleBinding,
    RegionResourceIsolatedPairedCandidateLoader,
    RegionResourceIsolatedPairedEvaluator,
    RegionResourcePairedArm,
    RegionResourcePairedArmEvidence,
    RegionResourcePairedArmSpecification,
    RegionResourcePairedInputBinding,
    RegionResourcePairedInterventionExecutor,
    RegionResourcePairedInterventionManifest,
    RegionResourcePairedInterventionSpecification,
    RegionResourcePairedThresholds,
    build_region_resource_paired_intervention_specification,
    build_region_resource_shadow_paired_evaluator,
)
from d4_distributed_fallback.region_resource_learning import (
    ModelBundleValidationError,
)
from d4_distributed_fallback.region_resource_paired_intervention_cli import main
from d4_distributed_fallback.region_resource_runtime_ack import (
    canonical_runtime_payload_sha256,
)
from d4_distributed_fallback.regional_failover import (
    RegionalAction,
    RegionalAuthorityLayer,
    RegionalFailoverDecision,
    RegionalRegionDecision,
    RegionalScenarioMetadata,
    RegionOwnershipMetadata,
)


_CANDIDATE_GATE_DIAGNOSTIC_FIELDS = (
    "candidate_gate_diagnostics_available",
    "candidate_confidence",
    "minimum_confidence",
    "candidate_ood_passed",
    "candidate_latency_limit_ms",
    "candidate_finite",
    "candidate_confidence_gate_passed",
    "candidate_ood_gate_passed",
    "candidate_latency_gate_passed",
    "candidate_finite_gate_passed",
    "candidate_failure_gate_passed",
)


def _sha(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _frozen_bundle_dir() -> Path:
    path = (
        Path(__file__).resolve().parents[1]
        / "outputs"
        / REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_ID
        / "bundle"
    )
    if not path.is_dir():
        pytest.skip("frozen D4 development bundle is not available locally")
    return path


def _snapshot(
    seed: int,
    *,
    coalition_ack_complete: bool = True,
    lease_expires_at_s: float = 100.0,
    fault_fenced: bool = False,
) -> RegionResourceSnapshot:
    scenario_id = f"reserved-region-scenario-{seed}"
    common = {
        "d1_uncertainty": 0.2,
        "d2_uncertainty": 0.1,
        "d5_visibility": 0.8,
        "d5_consistency": 0.9,
        "reserve_resources": 1,
        "secondary_coverage": 0.9,
        "secondary_readiness": 0.9,
        "communication_capacity": 80.0,
        "communication_latency_s": 0.02,
        "packet_loss_rate": 0.01,
        "current_owner_id": "C2",
        "current_owner_layer": RegionalAuthorityLayer.CENTER,
        "plan_id": f"PLAN-{seed}",
        "plan_version": 3,
        "epoch": 4,
        "lease_expires_at_s": lease_expires_at_s,
        "coalition_ack_complete": coalition_ack_complete,
        "owner_active": True,
        "fault_fenced": fault_fenced,
    }
    return RegionResourceSnapshot(
        snapshot_id=f"snapshot-{seed}",
        scenario_id=scenario_id,
        scenario_version="v1",
        seed=seed,
        timestamp_s=1.0,
        regions=(
            RegionResourceNode(
                region_id="region-a",
                target_demand=5.0,
                high_threat_backlog=2.0,
                available_resources=2,
                committed_resources=0,
                **common,
            ),
            RegionResourceNode(
                region_id="region-b",
                target_demand=1.0,
                high_threat_backlog=0.0,
                available_resources=5,
                committed_resources=1,
                **common,
            ),
        ),
        edges=(
            RegionResourceEdge(
                source_region_id="region-b",
                target_region_id="region-a",
                transferable_resources=2,
                distance_m=500.0,
                transfer_time_s=4.0,
                bandwidth_mbps=20.0,
                edge_id="edge-b-a",
                bidirectional=True,
            ),
        ),
    )


def _binding(snapshot: RegionResourceSnapshot) -> RegionResourcePairedInputBinding:
    seed = snapshot.seed
    return RegionResourcePairedInputBinding(
        seed=seed,
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        scenario_config_sha256=_sha(f"config-{seed}"),
        initial_state_sha256=_sha(f"initial-{seed}"),
        communication_schedule_sha256=_sha(f"communication-{seed}"),
        fault_schedule_sha256=_sha(f"fault-{seed}"),
        region_snapshot_lineage_sha256=_sha(f"lineage-{seed}"),
    )


def _formal_decision(snapshot: RegionResourceSnapshot) -> RegionalFailoverDecision:
    scenario = RegionalScenarioMetadata.from_scalable_scenario(
        {
            "schema_version": "scalable3d-scenario-v1",
            "scenario_name": snapshot.scenario_id,
            "scenario_version": snapshot.scenario_version,
            "target_count": snapshot.region_count,
            "resource_count": snapshot.total_resources,
            "recon_count": 0,
            "region_count": snapshot.region_count,
        },
        region_ids=tuple(node.region_id for node in snapshot.regions),
    )
    return RegionalFailoverDecision(
        timestamp_s=snapshot.timestamp_s,
        scenario=scenario,
        region_decisions=tuple(
            RegionalRegionDecision(
                region_id=node.region_id,
                selected_layer=node.current_owner_layer,
                action=RegionalAction.CONTINUE_CENTER,
                reason="paired_fixture",
                ownership=RegionOwnershipMetadata(
                    region_id=node.region_id,
                    owner_id=node.current_owner_id,
                    owner_layer=node.current_owner_layer,
                    owner_role=node.current_owner_layer.value,
                    plan_id=node.plan_id,
                    plan_version=node.plan_version,
                    epoch=node.epoch,
                    lease_expires_at_s=node.lease_expires_at_s,
                    active=node.owner_active,
                    task_ids=(),
                ),
                execution_allowed=True,
                fail_closed=False,
                risk_factors=(),
                task_ids=(),
            )
            for node in snapshot.regions
        ),
    )


def _bundle() -> RegionResourceCandidateBundleBinding:
    return RegionResourceCandidateBundleBinding(
        bundle_id="candidate-region-bundle",
        bundle_version="v1",
        bundle_manifest_sha256=_sha("candidate-manifest"),
        model_state_sha256=_sha("candidate-model"),
        policy_name="candidate-region-policy",
        policy_version="v1",
    )


def _specification(
    *,
    snapshots: dict[int, RegionResourceSnapshot] | None = None,
) -> RegionResourcePairedInterventionSpecification:
    resolved = snapshots or {
        seed: _snapshot(seed) for seed in REGION_RESOURCE_RESERVED_EVALUATION_SEEDS
    }
    return build_region_resource_paired_intervention_specification(
        experiment_id="reserved-region-paired-evaluation",
        experiment_version="v1",
        input_bindings=tuple(_binding(resolved[seed]) for seed in sorted(resolved)),
        candidate_bundle=_bundle(),
        thresholds=RegionResourcePairedThresholds(advisory_ttl_s=5.0),
    )


def _frozen_specification(
    *,
    thresholds: RegionResourcePairedThresholds | None = None,
) -> RegionResourcePairedInterventionSpecification:
    snapshots = {
        seed: _snapshot(seed) for seed in REGION_RESOURCE_RESERVED_EVALUATION_SEEDS
    }
    return build_region_resource_paired_intervention_specification(
        experiment_id="frozen-region-development-paired-evaluation",
        experiment_version="v1",
        input_bindings=tuple(_binding(snapshots[seed]) for seed in sorted(snapshots)),
        candidate_bundle=REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_BINDING,
        thresholds=thresholds or RegionResourcePairedThresholds(advisory_ttl_s=5.0),
    )


def _candidate(
    snapshot: RegionResourceSnapshot,
    *,
    action_epoch: int | None = None,
    model_sha256: str | None = None,
) -> RegionResourceRecommendation:
    epoch = 4 if action_epoch is None else action_epoch
    actions = tuple(
        RegionResourceAction(
            region_id=node.region_id,
            resource_quota_delta=2 if node.region_id == "region-a" else -2,
            reserve_ratio=0.25,
            reconnaissance_priority=0.7,
            hold=False,
            request_replan=False,
            expected_owner_id=node.current_owner_id,
            expected_owner_layer=node.current_owner_layer,
            expected_plan_id=node.plan_id,
            expected_plan_version=node.plan_version,
            expected_epoch=epoch,
            expected_lease_expires_at_s=node.lease_expires_at_s,
            reasons=("candidate_rebalance",),
        )
        for node in snapshot.regions
    )
    return RegionResourceRecommendation(
        snapshot_id=snapshot.snapshot_id,
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        seed=snapshot.seed,
        authority_digest=snapshot.authority_digest,
        created_at_s=snapshot.timestamp_s,
        policy_name=_bundle().policy_name,
        policy_version=_bundle().policy_version,
        source=RecommendationSource.LEARNED,
        confidence=0.9,
        actions=actions,
        transfers=(
            RegionTransferSuggestion(
                source_region_id="region-b",
                target_region_id="region-a",
                resource_count=2,
                edge_id="edge-b-a",
                expected_transfer_time_s=4.0,
                reasons=("candidate_rebalance",),
            ),
        ),
        projected=False,
        model_sha256=model_sha256 or _bundle().model_state_sha256,
    )


def _execute_pair(
    specification: RegionResourcePairedInterventionSpecification,
    snapshot: RegionResourceSnapshot,
) -> tuple[RegionResourcePairedArmEvidence, RegionResourcePairedArmEvidence]:
    executor = RegionResourcePairedInterventionExecutor(specification)
    binding = specification.arm_for(
        snapshot.seed, RegionResourcePairedArm.CONTROL
    ).input_binding
    control = executor.execute_arm(
        arm=RegionResourcePairedArm.CONTROL,
        seed=snapshot.seed,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=1.5,
    )
    treatment = executor.execute_arm(
        arm=RegionResourcePairedArm.TREATMENT,
        seed=snapshot.seed,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=1.5,
        candidate_recommendation=_candidate(snapshot),
        candidate_bundle_manifest_sha256=_bundle().bundle_manifest_sha256,
        candidate_latency_ms=2.0,
        candidate_ood_passed=True,
    )
    return control, treatment


def _execute_gate_candidate(
    *,
    confidence: float = 0.9,
    candidate_latency_ms: float = 2.0,
    candidate_ood_passed: bool = True,
    make_nonfinite: bool = False,
) -> RegionResourcePairedArmEvidence:
    specification = _specification()
    snapshot = _snapshot(1000)
    candidate = replace(_candidate(snapshot), confidence=confidence)
    if make_nonfinite:
        object.__setattr__(
            candidate.actions[0],
            "expected_lease_expires_at_s",
            float("nan"),
        )
    return RegionResourcePairedInterventionExecutor(specification).execute_arm(
        arm=RegionResourcePairedArm.TREATMENT,
        seed=1000,
        observed_input_binding=specification.arm_for(
            1000, RegionResourcePairedArm.TREATMENT
        ).input_binding,
        snapshot=snapshot,
        evaluated_at_s=1.5,
        candidate_recommendation=candidate,
        candidate_bundle_manifest_sha256=_bundle().bundle_manifest_sha256,
        candidate_latency_ms=candidate_latency_ms,
        candidate_ood_passed=candidate_ood_passed,
    )


def _as_v1_arm_evidence_payload(
    evidence: RegionResourcePairedArmEvidence,
) -> dict[str, object]:
    payload = evidence.to_dict()
    for field_name in _CANDIDATE_GATE_DIAGNOSTIC_FIELDS:
        payload.pop(field_name)
    payload["schema"] = REGION_RESOURCE_PAIRED_ARM_EVIDENCE_SCHEMA_V1
    return payload


def test_specification_freezes_exact_reserved_pairs_and_round_trips() -> None:
    specification = _specification()

    assert specification.schema == REGION_RESOURCE_PAIRED_SPEC_SCHEMA
    assert specification.reserved_seeds == tuple(range(1000, 1020))
    assert len(specification.arms) == 40
    assert specification.ppo_enabled is False
    assert specification.assist_enabled is False
    assert specification.authority_enabled is False
    assert specification.rule_fallback_enabled is True
    assert (
        RegionResourcePairedInterventionSpecification.from_dict(
            json.loads(json.dumps(specification.to_dict()))
        )
        == specification
    )


def test_specification_rejects_missing_arm_and_different_schedules() -> None:
    specification = _specification()
    with pytest.raises(ValueError, match="two arms per seed"):
        replace(specification, arms=specification.arms[:-1], specification_id="")

    treatment = specification.arm_for(1000, RegionResourcePairedArm.TREATMENT)
    mismatched_binding = replace(
        treatment.input_binding,
        communication_schedule_sha256=_sha("different-communication"),
    )
    mismatched_arm = replace(
        treatment,
        input_binding=mismatched_binding,
        arm_id="",
    )
    arms = tuple(
        mismatched_arm if item.arm_id == treatment.arm_id else item
        for item in specification.arms
    )
    with pytest.raises(ValueError, match="identical scenario inputs"):
        replace(specification, arms=arms, specification_id="")


def test_specification_parser_rejects_truth_keys_hash_tampering_and_nonfinite() -> None:
    specification = _specification()
    payload = specification.to_dict()
    payload["actor_truth_id"] = "forbidden"
    with pytest.raises(ValueError, match="truth or target identity"):
        RegionResourcePairedInterventionSpecification.from_dict(payload)

    payload = specification.to_dict()
    payload["specification_id"] = "d4-rr-paired-spec-tampered"
    with pytest.raises(ValueError, match="specification_id"):
        RegionResourcePairedInterventionSpecification.from_dict(payload)

    with pytest.raises(ValueError, match="finite"):
        RegionResourcePairedThresholds(inference_timeout_s=float("nan"))


def test_control_and_treatment_are_isolated_and_never_online_authority() -> None:
    specification = _specification()
    snapshot = _snapshot(1000)
    control, treatment = _execute_pair(specification, snapshot)

    assert control.schema == REGION_RESOURCE_PAIRED_ARM_EVIDENCE_SCHEMA
    assert control.deterministic_rule_executed is True
    assert control.isolated_arm_safe_adopted is True
    assert control.isolated_treatment_safe_adopted is False
    assert control.candidate_gate_diagnostics_available is True
    assert control.minimum_confidence == pytest.approx(0.6)
    assert control.candidate_latency_limit_ms == pytest.approx(50.0)
    assert control.candidate_confidence is None
    assert control.candidate_ood_passed is None
    assert control.candidate_finite is None
    assert control.candidate_confidence_gate_passed is None
    assert control.candidate_ood_gate_passed is None
    assert control.candidate_latency_gate_passed is None
    assert control.candidate_finite_gate_passed is None
    assert control.candidate_failure_gate_passed is None
    assert treatment.candidate_considered is True
    assert treatment.candidate_bundle_match is True
    assert treatment.candidate_thresholds_passed is True
    assert treatment.candidate_gate_diagnostics_available is True
    assert treatment.candidate_confidence == pytest.approx(0.9)
    assert treatment.minimum_confidence == pytest.approx(0.6)
    assert treatment.candidate_ood_passed is True
    assert treatment.candidate_latency_limit_ms == pytest.approx(50.0)
    assert treatment.candidate_finite is True
    assert treatment.candidate_confidence_gate_passed is True
    assert treatment.candidate_ood_gate_passed is True
    assert treatment.candidate_latency_gate_passed is True
    assert treatment.candidate_finite_gate_passed is True
    assert treatment.candidate_failure_gate_passed is True
    assert treatment.candidate_safety_projection_passed is True
    assert treatment.next_cycle_consumption_passed is True
    assert treatment.isolated_treatment_safe_adopted is True
    for evidence in (control, treatment):
        assert evidence.runtime_advisory_applied_ack_available is False
        assert evidence.post_projection_recommendation_is_applied_ack is False
        assert evidence.observed_outcome_available is False
        assert evidence.paired_non_degradation_available is False
        assert evidence.counterfactual_available is False
        assert evidence.causal_effect_available is False
        assert evidence.ppo_enabled is False
        assert evidence.assist_enabled is False
        assert evidence.online_authority is False
        assert evidence.rule_fallback_enabled is True


@pytest.mark.parametrize(
    ("gate", "reason", "kwargs"),
    (
        (
            "candidate_confidence_gate_passed",
            "candidate_low_confidence",
            {"confidence": 0.599999},
        ),
        (
            "candidate_ood_gate_passed",
            "candidate_ood_rejected",
            {"candidate_ood_passed": False},
        ),
        (
            "candidate_latency_gate_passed",
            "candidate_inference_timeout",
            {"candidate_latency_ms": 50.001},
        ),
        (
            "candidate_finite_gate_passed",
            "candidate_output_nonfinite",
            {"make_nonfinite": True},
        ),
    ),
)
def test_each_candidate_gate_has_explicit_diagnostics_and_rule_fallback(
    gate: str,
    reason: str,
    kwargs: dict[str, object],
) -> None:
    evidence = _execute_gate_candidate(**kwargs)

    assert evidence.pair_input_match is True
    assert evidence.candidate_bundle_match is True
    assert evidence.candidate_thresholds_passed is False
    assert getattr(evidence, gate) is False
    assert evidence.candidate_failure_gate_passed is True
    assert reason in evidence.rejection_reasons
    assert (
        "candidate_threshold_or_finite_gate_rejected"
        in evidence.rejection_reasons
    )
    assert evidence.rule_fallback_used is True
    assert evidence.deterministic_rule_executed is True
    assert evidence.next_cycle_consumption_passed is True
    assert evidence.isolated_arm_safe_adopted is True
    assert evidence.isolated_treatment_safe_adopted is False


def test_combined_candidate_gate_failure_persists_every_explicit_reason() -> None:
    evidence = _execute_gate_candidate(
        confidence=0.5,
        candidate_latency_ms=50.001,
        candidate_ood_passed=False,
        make_nonfinite=True,
    )

    assert evidence.candidate_confidence == pytest.approx(0.5)
    assert evidence.minimum_confidence == pytest.approx(0.6)
    assert evidence.candidate_ood_passed is False
    assert evidence.candidate_latency_ms == pytest.approx(50.001)
    assert evidence.candidate_latency_limit_ms == pytest.approx(50.0)
    assert evidence.candidate_finite is False
    assert evidence.candidate_confidence_gate_passed is False
    assert evidence.candidate_ood_gate_passed is False
    assert evidence.candidate_latency_gate_passed is False
    assert evidence.candidate_finite_gate_passed is False
    assert evidence.candidate_failure_gate_passed is True
    assert {
        "candidate_low_confidence",
        "candidate_ood_rejected",
        "candidate_inference_timeout",
        "candidate_output_nonfinite",
        "candidate_threshold_or_finite_gate_rejected",
    }.issubset(evidence.rejection_reasons)
    assert evidence.candidate_recommendation_sha256 is None
    assert evidence.rule_fallback_used is True
    assert evidence.next_cycle_consumption_passed is True
    assert evidence.isolated_treatment_safe_adopted is False


def test_candidate_threshold_boundaries_remain_closed_at_original_values() -> None:
    evidence = _execute_gate_candidate(
        confidence=0.6,
        candidate_latency_ms=50.0,
    )

    assert evidence.minimum_confidence == pytest.approx(0.6)
    assert evidence.candidate_latency_limit_ms == pytest.approx(50.0)
    assert evidence.candidate_confidence_gate_passed is True
    assert evidence.candidate_latency_gate_passed is True
    assert evidence.candidate_thresholds_passed is True
    assert evidence.rule_fallback_used is False
    assert evidence.isolated_treatment_safe_adopted is True


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("scenario_config_sha256", _sha("changed-config")),
        ("initial_state_sha256", _sha("changed-initial")),
        ("communication_schedule_sha256", _sha("changed-communication")),
        ("fault_schedule_sha256", _sha("changed-fault")),
        ("region_snapshot_lineage_sha256", _sha("changed-lineage")),
    ),
)
def test_treatment_fails_closed_when_observed_pair_input_differs(
    field: str, value: str
) -> None:
    specification = _specification()
    snapshot = _snapshot(1000)
    expected = specification.arm_for(
        1000, RegionResourcePairedArm.TREATMENT
    ).input_binding
    observed = replace(expected, **{field: value})

    evidence = RegionResourcePairedInterventionExecutor(specification).execute_arm(
        arm=RegionResourcePairedArm.TREATMENT,
        seed=1000,
        observed_input_binding=observed,
        snapshot=snapshot,
        evaluated_at_s=1.5,
        candidate_recommendation=_candidate(snapshot),
        candidate_bundle_manifest_sha256=_bundle().bundle_manifest_sha256,
        candidate_latency_ms=2.0,
    )

    assert evidence.pair_input_match is False
    assert evidence.candidate_bundle_match is True
    assert evidence.candidate_thresholds_passed is True
    assert evidence.candidate_confidence_gate_passed is True
    assert evidence.candidate_ood_gate_passed is True
    assert evidence.candidate_latency_gate_passed is True
    assert evidence.candidate_finite_gate_passed is True
    assert evidence.rule_fallback_used is True
    assert evidence.isolated_treatment_safe_adopted is False
    assert evidence.next_cycle_consumption_passed is False
    assert f"paired_input_mismatch:{field}" in evidence.rejection_reasons


def test_treatment_falls_back_on_stale_epoch_and_bundle_hash() -> None:
    specification = _specification()
    snapshot = _snapshot(1000)
    binding = specification.arm_for(
        1000, RegionResourcePairedArm.TREATMENT
    ).input_binding
    executor = RegionResourcePairedInterventionExecutor(specification)

    stale = executor.execute_arm(
        arm=RegionResourcePairedArm.TREATMENT,
        seed=1000,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=1.5,
        candidate_recommendation=_candidate(snapshot, action_epoch=3),
        candidate_bundle_manifest_sha256=_bundle().bundle_manifest_sha256,
        candidate_latency_ms=2.0,
    )
    assert stale.isolated_treatment_safe_adopted is False
    assert stale.rule_fallback_used is True
    assert stale.deterministic_rule_executed is True
    assert any("authority_version_mismatch" in reason for reason in stale.rejection_reasons)

    wrong_bundle = executor.execute_arm(
        arm=RegionResourcePairedArm.TREATMENT,
        seed=1000,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=1.5,
        candidate_recommendation=_candidate(snapshot),
        candidate_bundle_manifest_sha256=_sha("wrong-manifest"),
        candidate_latency_ms=2.0,
    )
    assert wrong_bundle.isolated_treatment_safe_adopted is False
    assert wrong_bundle.rule_fallback_used is True
    assert wrong_bundle.candidate_thresholds_passed is True
    assert wrong_bundle.candidate_confidence_gate_passed is True
    assert wrong_bundle.candidate_ood_gate_passed is True
    assert wrong_bundle.candidate_latency_gate_passed is True
    assert wrong_bundle.candidate_finite_gate_passed is True
    assert "candidate_bundle_or_policy_mismatch" in wrong_bundle.rejection_reasons


def test_treatment_projection_clips_capacity_and_preserves_resource_conservation() -> None:
    specification = _specification()
    snapshot = _snapshot(1000)
    binding = specification.arm_for(
        1000, RegionResourcePairedArm.TREATMENT
    ).input_binding
    oversized = _candidate(snapshot)
    oversized = replace(
        oversized,
        transfers=(replace(oversized.transfers[0], resource_count=99),),
    )

    evidence = RegionResourcePairedInterventionExecutor(specification).execute_arm(
        arm=RegionResourcePairedArm.TREATMENT,
        seed=1000,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=1.5,
        candidate_recommendation=oversized,
        candidate_bundle_manifest_sha256=_bundle().bundle_manifest_sha256,
        candidate_latency_ms=2.0,
    )

    assert evidence.isolated_treatment_safe_adopted is True
    assert any(
        note.endswith(":clipped_by_safety_projection")
        for note in evidence.projection_notes
    )
    assert evidence.rule_fallback_used is False


def test_treatment_falls_back_on_non_adjacent_candidate_transfer() -> None:
    specification = _specification()
    snapshot = _snapshot(1000)
    binding = specification.arm_for(
        1000, RegionResourcePairedArm.TREATMENT
    ).input_binding
    candidate = _candidate(snapshot)
    candidate = replace(
        candidate,
        transfers=(replace(candidate.transfers[0], edge_id="unknown-edge"),),
    )

    evidence = RegionResourcePairedInterventionExecutor(specification).execute_arm(
        arm=RegionResourcePairedArm.TREATMENT,
        seed=1000,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=1.5,
        candidate_recommendation=candidate,
        candidate_bundle_manifest_sha256=_bundle().bundle_manifest_sha256,
        candidate_latency_ms=2.0,
    )

    assert evidence.isolated_treatment_safe_adopted is False
    assert evidence.rule_fallback_used is True
    assert any("non_adjacent_edge" in item for item in evidence.rejection_reasons)


@pytest.mark.parametrize(
    ("coalition_ack_complete", "lease_expires_at_s", "fault_fenced", "reason"),
    (
        (False, 100.0, False, "coalition_ack_incomplete"),
        (True, 1.25, False, "authority_lease_expired"),
        (True, 100.0, True, "fault_fence_active"),
    ),
)
def test_treatment_fails_closed_on_coalition_or_lease_fence(
    coalition_ack_complete: bool,
    lease_expires_at_s: float,
    fault_fenced: bool,
    reason: str,
) -> None:
    snapshots = {
        seed: _snapshot(
            seed,
            coalition_ack_complete=(
                coalition_ack_complete if seed == 1000 else True
            ),
            lease_expires_at_s=(lease_expires_at_s if seed == 1000 else 100.0),
            fault_fenced=(fault_fenced if seed == 1000 else False),
        )
        for seed in REGION_RESOURCE_RESERVED_EVALUATION_SEEDS
    }
    specification = _specification(snapshots=snapshots)
    snapshot = snapshots[1000]
    binding = specification.arm_for(
        1000, RegionResourcePairedArm.TREATMENT
    ).input_binding

    evidence = RegionResourcePairedInterventionExecutor(specification).execute_arm(
        arm=RegionResourcePairedArm.TREATMENT,
        seed=1000,
        observed_input_binding=binding,
        snapshot=snapshot,
        evaluated_at_s=1.5,
        candidate_recommendation=_candidate(snapshot),
        candidate_bundle_manifest_sha256=_bundle().bundle_manifest_sha256,
        candidate_latency_ms=2.0,
    )

    assert evidence.isolated_treatment_safe_adopted is False
    assert evidence.isolated_arm_safe_adopted is False
    assert evidence.candidate_bundle_match is True
    assert evidence.candidate_thresholds_passed is True
    assert evidence.candidate_confidence_gate_passed is True
    assert evidence.candidate_ood_gate_passed is True
    assert evidence.candidate_latency_gate_passed is True
    assert evidence.candidate_finite_gate_passed is True
    assert any(reason in item for item in evidence.rejection_reasons)


def test_manifest_requires_all_arms_matches_hashes_and_round_trips() -> None:
    specification = _specification()
    evidence: list[RegionResourcePairedArmEvidence] = []
    for seed in REGION_RESOURCE_RESERVED_EVALUATION_SEEDS:
        evidence.extend(_execute_pair(specification, _snapshot(seed)))
    manifest = RegionResourcePairedInterventionManifest(
        specification=specification,
        arm_evidence=tuple(evidence),
        created_at_utc="2026-07-21T00:00:00Z",
    )

    assert manifest.schema == REGION_RESOURCE_PAIRED_MANIFEST_SCHEMA
    assert manifest.treatment_safe_adoption_count == 20
    assert manifest.failed_arm_count == 0
    assert manifest.formal_twenty_seed_performance_completed is False
    assert manifest.performance_claim_allowed is False
    assert (
        RegionResourcePairedInterventionManifest.from_dict(
            json.loads(json.dumps(manifest.to_dict()))
        )
        == manifest
    )

    with pytest.raises(ValueError, match="all 40"):
        replace(manifest, arm_evidence=manifest.arm_evidence[:-1], manifest_id="")
    tampered = replace(
        manifest.arm_evidence[0],
        specification_sha256=_sha("wrong-specification"),
    )
    with pytest.raises(ValueError, match="specification hash mismatch"):
        replace(
            manifest,
            arm_evidence=(tampered, *manifest.arm_evidence[1:]),
            manifest_id="",
        )


def test_v1_arm_and_manifest_json_are_verified_then_migrated_to_v2() -> None:
    specification = _specification()
    evidence: list[RegionResourcePairedArmEvidence] = []
    for seed in REGION_RESOURCE_RESERVED_EVALUATION_SEEDS:
        evidence.extend(_execute_pair(specification, _snapshot(seed)))
    manifest = RegionResourcePairedInterventionManifest(
        specification=specification,
        arm_evidence=tuple(evidence),
        created_at_utc="2026-07-21T00:00:00Z",
    )
    legacy_payload = manifest.to_dict()
    legacy_payload["arm_evidence"] = [
        _as_v1_arm_evidence_payload(item) for item in manifest.arm_evidence
    ]
    content_payload = dict(legacy_payload)
    content_payload.pop("manifest_id")
    legacy_payload["manifest_id"] = (
        "d4-rr-paired-manifest-"
        + sha256(
            json.dumps(
                content_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
    )
    legacy_manifest_id = legacy_payload["manifest_id"]

    migrated = RegionResourcePairedInterventionManifest.from_dict(legacy_payload)

    assert migrated.manifest_id != legacy_manifest_id
    assert migrated.treatment_safe_adoption_count == 20
    assert migrated.failed_arm_count == 0
    for original, record in zip(manifest.arm_evidence, migrated.arm_evidence):
        assert record.schema == REGION_RESOURCE_PAIRED_ARM_EVIDENCE_SCHEMA
        assert record.candidate_gate_diagnostics_available is False
        assert record.candidate_confidence is None
        assert record.minimum_confidence is None
        assert record.candidate_ood_passed is None
        assert record.candidate_latency_limit_ms is None
        assert record.candidate_finite is None
        assert record.candidate_confidence_gate_passed is None
        assert record.candidate_ood_gate_passed is None
        assert record.candidate_latency_gate_passed is None
        assert record.candidate_finite_gate_passed is None
        assert record.candidate_failure_gate_passed is None
        assert record.pair_input_match is original.pair_input_match
        assert record.candidate_bundle_match is original.candidate_bundle_match
        assert record.rule_fallback_used is original.rule_fallback_used
        assert (
            record.next_cycle_consumption_passed
            is original.next_cycle_consumption_passed
        )
        assert (
            record.isolated_treatment_safe_adopted
            is original.isolated_treatment_safe_adopted
        )

    tampered = dict(legacy_payload)
    tampered["manifest_id"] = "d4-rr-paired-manifest-" + _sha("tampered")
    with pytest.raises(ValueError, match="legacy manifest content"):
        RegionResourcePairedInterventionManifest.from_dict(tampered)


def test_manifest_rejects_different_actual_arm_snapshot_hashes() -> None:
    specification = _specification()
    records: list[RegionResourcePairedArmEvidence] = []
    for seed in REGION_RESOURCE_RESERVED_EVALUATION_SEEDS:
        records.extend(_execute_pair(specification, _snapshot(seed)))
    treatment_index = next(
        index
        for index, record in enumerate(records)
        if record.seed == 1000 and record.arm == RegionResourcePairedArm.TREATMENT
    )
    records[treatment_index] = replace(
        records[treatment_index],
        snapshot_payload_sha256=_sha("different-snapshot"),
    )
    with pytest.raises(ValueError, match="snapshot payload"):
        RegionResourcePairedInterventionManifest(
            specification=specification,
            arm_evidence=tuple(records),
            created_at_utc="2026-07-21T00:00:00Z",
        )


def test_existing_shadow_evaluator_is_reused_without_outcome_claim() -> None:
    specification = _specification()
    evaluator = build_region_resource_shadow_paired_evaluator(specification)

    assert isinstance(evaluator, ShadowPairedEvaluator)
    assert evaluator.minimum_unseen_seeds == 20


def test_cli_round_trips_specification_and_manifest(tmp_path) -> None:
    specification = _specification()
    specification_path = tmp_path / "specification.json"
    specification_output = tmp_path / "specification-canonical.json"
    specification_path.write_text(
        json.dumps(specification.to_dict()), encoding="utf-8"
    )
    assert main(
        (
            "validate-spec",
            "--input",
            str(specification_path),
            "--output",
            str(specification_output),
        )
    ) == 0
    assert json.loads(specification_output.read_text(encoding="utf-8")) == specification.to_dict()

    records: list[RegionResourcePairedArmEvidence] = []
    for seed in REGION_RESOURCE_RESERVED_EVALUATION_SEEDS:
        records.extend(_execute_pair(specification, _snapshot(seed)))
    manifest = RegionResourcePairedInterventionManifest(
        specification=specification,
        arm_evidence=tuple(records),
        created_at_utc="2026-07-21T00:00:00Z",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_output = tmp_path / "manifest-canonical.json"
    manifest_path.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")
    assert main(
        (
            "validate-manifest",
            "--input",
            str(manifest_path),
            "--output",
            str(manifest_output),
        )
    ) == 0
    assert json.loads(manifest_output.read_text(encoding="utf-8")) == manifest.to_dict()


def test_arm_evidence_cannot_upgrade_projection_to_ack_or_outcome() -> None:
    specification = _specification()
    _, evidence = _execute_pair(specification, _snapshot(1000))
    with pytest.raises(ValueError, match="cannot grant outcome or online authority"):
        replace(evidence, runtime_advisory_applied_ack_available=True)
    with pytest.raises(ValueError, match="cannot grant outcome or online authority"):
        replace(evidence, paired_non_degradation_available=True)
    with pytest.raises(ValueError, match="cannot grant outcome or online authority"):
        replace(evidence, online_authority=True)


def test_frozen_candidate_loader_verifies_every_bundle_file_without_mutation() -> None:
    bundle_dir = _frozen_bundle_dir()
    expected = {
        "manifest.json": REGION_RESOURCE_FROZEN_DEVELOPMENT_MANIFEST_SHA256,
        "state_dict.pt": REGION_RESOURCE_FROZEN_DEVELOPMENT_STATE_DICT_SHA256,
        "training_dataset_manifest.json": (
            REGION_RESOURCE_FROZEN_DEVELOPMENT_TRAINING_MANIFEST_SHA256
        ),
    }
    before = {name: _file_sha256(bundle_dir / name) for name in expected}

    loader = RegionResourceIsolatedPairedCandidateLoader(
        REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_BINDING,
        bundle_dir,
    )
    evaluation = loader.evaluate(_snapshot(1000), ood_margin=0.05)
    after = {name: _file_sha256(bundle_dir / name) for name in expected}

    assert before == expected == after
    assert loader.loaded_bundle.model.training is False
    assert evaluation.bundle_manifest_sha256 == expected["manifest.json"]
    assert evaluation.recommendation.source == RecommendationSource.LEARNED
    assert evaluation.recommendation.projected is False
    assert (
        evaluation.recommendation.model_sha256
        == REGION_RESOURCE_FROZEN_DEVELOPMENT_STATE_DICT_SHA256
    )
    assert evaluation.candidate_latency_ms >= 0.0


def test_frozen_candidate_loader_rejects_any_other_bundle_binding() -> None:
    with pytest.raises(
        ModelBundleValidationError,
        match="paired_bundle_not_frozen_development_bundle",
    ):
        RegionResourceIsolatedPairedCandidateLoader(
            replace(
                REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_BINDING,
                bundle_id="different-development-bundle",
            ),
            Path("unused") / "different-development-bundle" / "bundle",
        )


def test_frozen_candidate_loader_detects_post_load_bundle_mutation(tmp_path) -> None:
    copied_bundle = (
        tmp_path / REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_ID / "bundle"
    )
    shutil.copytree(_frozen_bundle_dir(), copied_bundle)
    loader = RegionResourceIsolatedPairedCandidateLoader(
        REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_BINDING,
        copied_bundle,
    )
    training_manifest = copied_bundle / "training_dataset_manifest.json"
    training_manifest.write_bytes(training_manifest.read_bytes() + b"\n")

    with pytest.raises(
        ModelBundleValidationError,
        match="paired_bundle_changed_before_inference",
    ):
        loader.evaluate(_snapshot(1000), ood_margin=0.05)


def test_isolated_evaluator_uses_raw_candidate_then_truthful_rule_fallback() -> None:
    specification = _frozen_specification()
    snapshot = _snapshot(1000)
    input_binding = specification.arm_for(
        1000, RegionResourcePairedArm.CONTROL
    ).input_binding
    evaluator = RegionResourceIsolatedPairedEvaluator(
        specification,
        _frozen_bundle_dir(),
    )
    formal_decision = _formal_decision(snapshot)
    formal_before = formal_decision.to_dict()

    control, treatment = evaluator.execute_pair(
        seed=1000,
        observed_input_binding=input_binding,
        snapshot=snapshot,
        evaluated_at_s=1.5,
        formal_decision=formal_decision,
    )

    assert evaluator.candidate_loader_ready is True
    assert formal_decision.to_dict() == formal_before
    assert control.observed_input_sha256 == treatment.observed_input_sha256
    assert control.snapshot_payload_sha256 == treatment.snapshot_payload_sha256
    assert control.pair_input_match is treatment.pair_input_match is True
    assert treatment.candidate_considered is True
    assert treatment.candidate_recommendation_sha256 is not None
    assert treatment.candidate_bundle_match is True
    assert treatment.candidate_thresholds_passed is False
    assert treatment.candidate_gate_diagnostics_available is True
    assert treatment.minimum_confidence == pytest.approx(0.6)
    assert treatment.candidate_latency_limit_ms == pytest.approx(50.0)
    assert treatment.candidate_ood_passed is False
    assert treatment.candidate_ood_gate_passed is False
    assert treatment.candidate_finite is True
    assert treatment.candidate_finite_gate_passed is True
    assert treatment.rule_fallback_used is True
    assert treatment.deterministic_rule_executed is True
    assert treatment.isolated_treatment_safe_adopted is False
    assert "isolated_candidate_ood_rejected" in treatment.rejection_reasons
    assert "candidate_ood_rejected" in treatment.rejection_reasons
    assert "candidate_threshold_or_finite_gate_rejected" in treatment.rejection_reasons
    for evidence in (control, treatment):
        assert evidence.runtime_advisory_applied_ack_available is False
        assert evidence.observed_outcome_available is False
        assert evidence.paired_non_degradation_available is False
        assert evidence.counterfactual_available is False
        assert evidence.causal_effect_available is False
        assert evidence.ppo_enabled is False
        assert evidence.assist_enabled is False
        assert evidence.online_authority is False
        assert evidence.rule_fallback_enabled is True


def test_isolated_evaluator_records_bundle_failure_and_runs_rule(tmp_path) -> None:
    copied_bundle = (
        tmp_path / REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_ID / "bundle"
    )
    shutil.copytree(_frozen_bundle_dir(), copied_bundle)
    state_dict = copied_bundle / "state_dict.pt"
    state_dict.write_bytes(state_dict.read_bytes() + b"tampered")
    specification = _frozen_specification()
    snapshot = _snapshot(1000)
    evaluator = RegionResourceIsolatedPairedEvaluator(
        specification,
        copied_bundle,
    )

    control, treatment = evaluator.execute_pair(
        seed=1000,
        observed_input_binding=specification.arm_for(
            1000, RegionResourcePairedArm.CONTROL
        ).input_binding,
        snapshot=snapshot,
        evaluated_at_s=1.5,
    )

    assert evaluator.candidate_loader_ready is False
    assert control.snapshot_payload_sha256 == treatment.snapshot_payload_sha256
    assert treatment.candidate_considered is False
    assert treatment.candidate_recommendation_sha256 is None
    assert treatment.minimum_confidence == pytest.approx(0.6)
    assert treatment.candidate_latency_limit_ms == pytest.approx(50.0)
    assert treatment.candidate_confidence is None
    assert treatment.candidate_ood_passed is None
    assert treatment.candidate_finite is None
    assert treatment.candidate_confidence_gate_passed is None
    assert treatment.candidate_ood_gate_passed is None
    assert treatment.candidate_latency_gate_passed is None
    assert treatment.candidate_finite_gate_passed is None
    assert treatment.candidate_failure_gate_passed is None
    assert treatment.rule_fallback_used is True
    assert treatment.deterministic_rule_executed is True
    assert treatment.isolated_treatment_safe_adopted is False
    assert any(
        reason.startswith("isolated_candidate_load_failed:state_dict_sha256_mismatch")
        for reason in treatment.rejection_reasons
    )


def test_candidate_projection_exception_is_recorded_and_falls_back() -> None:
    class BrokenProjector:
        def __init__(self, delegate) -> None:
            self.delegate = delegate

        def project(self, *args, **kwargs):
            raise RuntimeError("synthetic_projection_failure")

        def build_advisory_contract(self, *args, **kwargs):
            return self.delegate.build_advisory_contract(*args, **kwargs)

        def validate_for_consumption(self, *args, **kwargs):
            return self.delegate.validate_for_consumption(*args, **kwargs)

    specification = _specification()
    snapshot = _snapshot(1000)
    executor = RegionResourcePairedInterventionExecutor(specification)
    original_projector = executor.projector
    executor.projector = BrokenProjector(original_projector)

    # The rule policy retains the original deterministic projector instance.
    assert executor.rule_policy.projector is original_projector
    evidence = executor.execute_arm(
        arm=RegionResourcePairedArm.TREATMENT,
        seed=1000,
        observed_input_binding=specification.arm_for(
            1000, RegionResourcePairedArm.TREATMENT
        ).input_binding,
        snapshot=snapshot,
        evaluated_at_s=1.5,
        candidate_recommendation=_candidate(snapshot),
        candidate_bundle_manifest_sha256=_bundle().bundle_manifest_sha256,
        candidate_latency_ms=2.0,
    )

    assert evidence.rule_fallback_used is True
    assert evidence.deterministic_rule_executed is True
    assert evidence.isolated_treatment_safe_adopted is False
    assert any(
        reason.startswith(
            "candidate_projection_failed:synthetic_projection_failure"
        )
        for reason in evidence.rejection_reasons
    )
