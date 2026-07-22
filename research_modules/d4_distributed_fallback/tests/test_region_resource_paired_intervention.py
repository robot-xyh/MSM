from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

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
    REGION_RESOURCE_PAIRED_ARM_EVIDENCE_SCHEMA,
    REGION_RESOURCE_PAIRED_MANIFEST_SCHEMA,
    REGION_RESOURCE_PAIRED_SPEC_SCHEMA,
    REGION_RESOURCE_RESERVED_EVALUATION_SEEDS,
    RegionResourceCandidateBundleBinding,
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
from d4_distributed_fallback.region_resource_paired_intervention_cli import main
from d4_distributed_fallback.region_resource_runtime_ack import (
    canonical_runtime_payload_sha256,
)
from d4_distributed_fallback.regional_failover import RegionalAuthorityLayer


def _sha(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


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
    assert treatment.candidate_considered is True
    assert treatment.candidate_bundle_match is True
    assert treatment.candidate_thresholds_passed is True
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
