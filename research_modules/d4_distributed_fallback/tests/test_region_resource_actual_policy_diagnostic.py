from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from d4_distributed_fallback.region_resource import (
    RecommendationSource,
    RegionResourceAction,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RegionTransferSuggestion,
)
from d4_distributed_fallback.region_resource_actual_policy_diagnostic import (
    REGION_RESOURCE_ACTUAL_POLICY_PERMISSIONS,
    RegionResourceActualPolicyCalibrationSplit,
    RegionResourceActualPolicyOutcome,
    diagnose_region_resource_actual_policy_calibration,
    diagnose_region_resource_actual_policy_sample,
)
from d4_distributed_fallback.region_resource_development_candidate import (
    REGION_RESOURCE_RESERVED_EVALUATION_SEEDS,
)
from d4_distributed_fallback.regional_failover import (
    RegionalAuthorityLayer,
)


_MODEL_SHA256 = "a" * 64
_BUNDLE_SHA256 = "b" * 64
_DATASET_SHA256 = "c" * 64
_CANDIDATE_SHA256 = "d" * 64
_MODEL_VERSION = "development-v1"


def _snapshot(
    *,
    seed: int = 10,
    snapshot_id: str = "snapshot-10",
    fully_committed: bool = False,
    partitioned: bool = False,
    lease_expires_at_s: float = 100.0,
    coalition_ack_complete: bool = True,
) -> RegionResourceSnapshot:
    common = {
        "target_demand": 2.0,
        "high_threat_backlog": 0.0,
        "d1_uncertainty": 0.2,
        "d2_uncertainty": 0.1,
        "d5_visibility": 0.8,
        "d5_consistency": 0.9,
        "reserve_resources": 0 if fully_committed else 1,
        "secondary_coverage": 0.9,
        "secondary_readiness": 0.9,
        "communication_capacity": 80.0,
        "communication_latency_s": 0.02,
        "packet_loss_rate": 0.01,
        "current_owner_id": "C2",
        "current_owner_layer": RegionalAuthorityLayer.CENTER,
        "plan_id": "PLAN-A2",
        "plan_version": 3,
        "epoch": 4,
        "lease_expires_at_s": lease_expires_at_s,
        "coalition_ack_complete": coalition_ack_complete,
        "owner_active": True,
        "fault_fenced": False,
    }
    return RegionResourceSnapshot(
        snapshot_id=snapshot_id,
        scenario_id="actual-policy-calibration",
        scenario_version="v1",
        seed=seed,
        timestamp_s=1.0,
        regions=(
            RegionResourceNode(
                region_id="region-a",
                available_resources=3,
                committed_resources=3 if fully_committed else 0,
                **common,
            ),
            RegionResourceNode(
                region_id="region-b",
                available_resources=6,
                committed_resources=6 if fully_committed else 1,
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
                partitioned=partitioned,
            ),
        ),
    )


def _recommendation(
    snapshot: RegionResourceSnapshot,
    *,
    confidence: float = 0.9,
    transfer: bool = False,
    reserve_ratio: float | None = None,
    epoch_offset: int = 0,
    plan_version_offset: int = 0,
    lease_offset_s: float = 0.0,
    model_sha256: str = _MODEL_SHA256,
) -> RegionResourceRecommendation:
    actions = []
    for node in snapshot.regions:
        baseline_ratio = (
            (0 if node.committed_resources == node.available_resources else 1)
            / node.available_resources
        )
        actions.append(
            RegionResourceAction(
                region_id=node.region_id,
                resource_quota_delta=(
                    1
                    if transfer and node.region_id == "region-a"
                    else (
                        -1
                        if transfer and node.region_id == "region-b"
                        else 0
                    )
                ),
                reserve_ratio=(
                    baseline_ratio
                    if reserve_ratio is None
                    else reserve_ratio
                ),
                reconnaissance_priority=0.5,
                hold=False,
                request_replan=False,
                expected_owner_id=node.current_owner_id,
                expected_owner_layer=node.current_owner_layer,
                expected_plan_id=node.plan_id,
                expected_plan_version=(
                    node.plan_version + plan_version_offset
                ),
                expected_epoch=node.epoch + epoch_offset,
                expected_lease_expires_at_s=(
                    node.lease_expires_at_s + lease_offset_s
                ),
                reasons=("actual_policy_fixture",),
            )
        )
    transfers = (
        (
            RegionTransferSuggestion(
                source_region_id="region-b",
                target_region_id="region-a",
                resource_count=1,
                edge_id="edge-b-a",
                expected_transfer_time_s=4.0,
                reasons=("actual_policy_fixture",),
            ),
        )
        if transfer
        else ()
    )
    return RegionResourceRecommendation(
        snapshot_id=snapshot.snapshot_id,
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        seed=snapshot.seed,
        authority_digest=snapshot.authority_digest,
        created_at_s=snapshot.timestamp_s,
        policy_name="d4-test-actual-model",
        policy_version=_MODEL_VERSION,
        source=RecommendationSource.LEARNED,
        confidence=confidence,
        actions=tuple(actions),
        transfers=transfers,
        model_sha256=model_sha256,
    )


class _Policy:
    def __init__(
        self,
        recommendations: dict[str, RegionResourceRecommendation],
        *,
        ood: bool = False,
    ) -> None:
        self.recommendations = recommendations
        self.ood = ood
        self.manifest = SimpleNamespace(
            model_version=_MODEL_VERSION,
            state_dict_sha256=_MODEL_SHA256,
        )

    def recommend_raw(
        self, snapshot: RegionResourceSnapshot
    ) -> RegionResourceRecommendation:
        return self.recommendations[snapshot.snapshot_id]

    def is_ood(
        self, snapshot: RegionResourceSnapshot, *, margin: float
    ) -> bool:
        return self.ood


def _diagnose(
    snapshot: RegionResourceSnapshot,
    recommendation: RegionResourceRecommendation,
):
    return diagnose_region_resource_actual_policy_sample(
        _Policy({snapshot.snapshot_id: recommendation}),
        snapshot,
        candidate_id="actual-candidate",
        expected_model_version=_MODEL_VERSION,
        expected_model_sha256=_MODEL_SHA256,
        frame_index=0,
    )


def test_actual_model_safe_transfer_is_nonzero_and_permissions_are_external() -> None:
    snapshot = _snapshot()
    result = _diagnose(
        snapshot,
        _recommendation(snapshot, transfer=True),
    )

    assert (
        result.outcome
        is RegionResourceActualPolicyOutcome.SAFE_NONZERO_ACTUAL_MODEL
    )
    assert result.safe_nonzero_actual_model is True
    assert result.actual_model_identity_verified is True
    assert any(
        value.startswith("transfer:region-b->region-a")
        for value in result.intervention_fields
    )


def test_confidence_and_owner_epoch_reasons_are_separated() -> None:
    snapshot = _snapshot()
    low = _diagnose(
        snapshot,
        _recommendation(snapshot, confidence=0.59),
    )
    assert (
        low.outcome
        is RegionResourceActualPolicyOutcome.CONFIDENCE_INSUFFICIENT
    )

    stale = _diagnose(
        snapshot,
        _recommendation(snapshot, epoch_offset=-1),
    )
    assert (
        stale.outcome
        is RegionResourceActualPolicyOutcome.OWNER_LEASE_EPOCH_BLOCKED
    )
    assert any(
        "epoch_mismatch" in reason for reason in stale.reason_codes
    )


def test_resource_feasibility_and_action_mask_are_separated() -> None:
    committed = _snapshot(fully_committed=True)
    infeasible = _diagnose(
        committed,
        _recommendation(committed, reserve_ratio=0.8),
    )
    assert (
        infeasible.outcome
        is RegionResourceActualPolicyOutcome.RESOURCE_INFEASIBLE
    )
    assert any(
        "reserve_request_exceeds_feasible_resources" in reason
        for reason in infeasible.reason_codes
    )

    partitioned = _snapshot(partitioned=True)
    masked = _diagnose(
        partitioned,
        _recommendation(partitioned, transfer=True),
    )
    assert (
        masked.outcome
        is RegionResourceActualPolicyOutcome.ACTION_MASKED
    )
    assert any(
        "transfer_action_masked_by_link" in reason
        for reason in masked.reason_codes
    )


def test_action_same_and_model_identity_mismatch_fail_closed() -> None:
    snapshot = _snapshot()
    no_op = _diagnose(snapshot, _recommendation(snapshot))
    assert (
        no_op.outcome
        is RegionResourceActualPolicyOutcome.ACTION_SAME_AS_BASELINE
    )
    assert no_op.safe_nonzero_actual_model is False

    wrong_model = _diagnose(
        snapshot,
        _recommendation(snapshot, transfer=True, model_sha256="d" * 64),
    )
    assert (
        wrong_model.outcome
        is RegionResourceActualPolicyOutcome.POLICY_OUTPUT_INVALID
    )
    assert wrong_model.safe_nonzero_actual_model is False

    policy = _Policy(
        {snapshot.snapshot_id: _recommendation(snapshot, transfer=True)}
    )
    policy.manifest.state_dict_sha256 = "e" * 64
    wrong_manifest = diagnose_region_resource_actual_policy_sample(
        policy,
        snapshot,
        candidate_id="actual-candidate",
        expected_model_version=_MODEL_VERSION,
        expected_model_sha256=_MODEL_SHA256,
        frame_index=0,
    )
    assert (
        wrong_manifest.outcome
        is RegionResourceActualPolicyOutcome.POLICY_OUTPUT_INVALID
    )
    assert (
        "actual_policy_manifest_model_sha256_mismatch"
        in wrong_manifest.reason_codes
    )


def test_unknown_and_nonfinite_actions_fail_closed_without_crashing() -> None:
    snapshot = _snapshot()
    base = _recommendation(snapshot, transfer=True)
    unknown_action = replace(
        base.actions[0],
        region_id="unknown-region",
    )
    unknown = replace(
        base,
        actions=(unknown_action, base.actions[1]),
    )
    unknown_result = _diagnose(snapshot, unknown)
    assert (
        unknown_result.outcome
        is RegionResourceActualPolicyOutcome.POLICY_OUTPUT_INVALID
    )
    assert unknown_result.policy_output_structure_valid is False
    assert "policy_output_action_region_unknown:unknown-region" in (
        unknown_result.reason_codes
    )

    nonfinite_action = replace(base.actions[0])
    object.__setattr__(
        nonfinite_action,
        "resource_quota_delta",
        float("nan"),
    )
    nonfinite = replace(
        base,
        actions=(nonfinite_action, base.actions[1]),
    )
    nonfinite_result = _diagnose(snapshot, nonfinite)
    assert (
        nonfinite_result.outcome
        is RegionResourceActualPolicyOutcome.POLICY_OUTPUT_INVALID
    )
    assert nonfinite_result.safe_nonzero_actual_model is False
    assert nonfinite_result.raw_executable_signature_sha256 is None


def test_plan_lease_and_ack_fences_are_separate_fail_closed_outcomes() -> None:
    snapshot = _snapshot()
    stale_plan = _diagnose(
        snapshot,
        _recommendation(snapshot, plan_version_offset=-1),
    )
    assert (
        stale_plan.outcome
        is RegionResourceActualPolicyOutcome.OWNER_LEASE_EPOCH_BLOCKED
    )
    assert "plan_version_mismatch" in stale_plan.reason_codes

    stale_lease = _diagnose(
        snapshot,
        _recommendation(snapshot, lease_offset_s=-1.0),
    )
    assert (
        stale_lease.outcome
        is RegionResourceActualPolicyOutcome.OWNER_LEASE_EPOCH_BLOCKED
    )
    assert "lease_binding_mismatch" in stale_lease.reason_codes

    no_ack = _snapshot(coalition_ack_complete=False)
    ack_result = _diagnose(
        no_ack,
        _recommendation(no_ack, transfer=True),
    )
    assert (
        ack_result.outcome
        is RegionResourceActualPolicyOutcome.ACTION_MASKED
    )
    assert "action_masked_by_coalition_ack" in ack_result.reason_codes


def test_external_region_and_action_authority_fields_must_be_present() -> None:
    snapshot = _snapshot()
    node_payload = snapshot.regions[0].to_dict()
    node_payload.pop("coalition_ack_complete")
    with pytest.raises(ValueError, match="coalition_ack_complete"):
        RegionResourceNode.from_dict(node_payload)

    action_payload = _recommendation(snapshot).actions[0].to_dict()
    action_payload.pop("expected_epoch")
    with pytest.raises(ValueError, match="expected_epoch"):
        RegionResourceAction.from_dict(action_payload)


def test_calibration_report_uses_only_independent_seeds_and_keeps_permissions_false() -> None:
    first = _snapshot(seed=10, snapshot_id="snapshot-10")
    second = _snapshot(seed=11, snapshot_id="snapshot-11")
    policy = _Policy(
        {
            first.snapshot_id: _recommendation(first, transfer=True),
            second.snapshot_id: _recommendation(second),
        }
    )
    episodes = tuple(
        SimpleNamespace(
            source=SimpleNamespace(seed=snapshot.seed, git_dirty=False),
            frames=(
                SimpleNamespace(frame_index=0, snapshot=snapshot),
            ),
        )
        for snapshot in (first, second)
    )
    dataset = SimpleNamespace(
        manifest=SimpleNamespace(dataset_sha256=_DATASET_SHA256),
        episode_records=episodes,
    )
    split = RegionResourceActualPolicyCalibrationSplit(
        train_seeds=(1,),
        validation_seeds=(2,),
        calibration_seeds=(10, 11),
        reserved_evaluation_seeds=(
            REGION_RESOURCE_RESERVED_EVALUATION_SEEDS
        ),
    )

    report = diagnose_region_resource_actual_policy_calibration(
        policy,
        dataset,
        candidate_id="actual-candidate",
        candidate_manifest_sha256=_CANDIDATE_SHA256,
        model_version=_MODEL_VERSION,
        expected_model_sha256=_MODEL_SHA256,
        bundle_manifest_sha256=_BUNDLE_SHA256,
        split=split,
        implementation_lineage_matches_current=False,
        implementation_lineage_reason=(
            "development_candidate_implementation_lineage_mismatch"
        ),
        truth_free_dataset_verified=True,
    )

    assert report.sample_count == 2
    assert report.safe_nonzero_actual_model_count == 1
    assert (
        report.historical_lineage_nonzero_observation_available is True
    )
    assert (
        report.actual_model_nonzero_development_evidence_available
        is False
    )
    assert report.policy_output_degenerate is False
    assert report.reserved_seed_use_count == 0
    assert report.truth_identifier_use_count == 0
    assert dict(report.permissions) == REGION_RESOURCE_ACTUAL_POLICY_PERMISSIONS
    assert all(value is False for value in report.permissions.values())
    assert report.to_dict()["evidence_boundary"] == {
        "development_only": True,
        "calibration_only": True,
        "formal_holdout_evaluated": False,
        "current_implementation_lineage_required_for_evidence": True,
        "safe_projection_is_not_runtime_adoption": True,
        "system_benefit_claimed": False,
    }
    assert report.calibration_seed_sample_counts == {"10": 1, "11": 1}
    assert sum(report.outcome_counts.values()) == report.sample_count
    assert len(report.sample_identity_sha256) == 64
    assert len(report.classification_sha256) == 64


def test_calibration_split_rejects_reserved_overlap() -> None:
    with pytest.raises(ValueError, match="seed catalogs overlap"):
        RegionResourceActualPolicyCalibrationSplit(
            train_seeds=(1,),
            validation_seeds=(2,),
            calibration_seeds=(1000,),
            reserved_evaluation_seeds=(
                REGION_RESOURCE_RESERVED_EVALUATION_SEEDS
            ),
        )


def test_calibration_report_marks_repeated_noop_signature_as_degenerate() -> None:
    snapshots = (
        _snapshot(seed=20, snapshot_id="snapshot-20"),
        _snapshot(seed=21, snapshot_id="snapshot-21"),
    )
    policy = _Policy(
        {
            snapshot.snapshot_id: _recommendation(snapshot)
            for snapshot in snapshots
        }
    )
    dataset = SimpleNamespace(
        manifest=SimpleNamespace(dataset_sha256=_DATASET_SHA256),
        episode_records=tuple(
            SimpleNamespace(
                source=SimpleNamespace(
                    seed=snapshot.seed,
                    git_dirty=False,
                ),
                frames=(
                    SimpleNamespace(frame_index=0, snapshot=snapshot),
                ),
            )
            for snapshot in snapshots
        ),
    )
    split = RegionResourceActualPolicyCalibrationSplit(
        train_seeds=(1,),
        validation_seeds=(2,),
        calibration_seeds=(20, 21),
        reserved_evaluation_seeds=(
            REGION_RESOURCE_RESERVED_EVALUATION_SEEDS
        ),
    )

    report = diagnose_region_resource_actual_policy_calibration(
        policy,
        dataset,
        candidate_id="actual-candidate",
        candidate_manifest_sha256=_CANDIDATE_SHA256,
        model_version=_MODEL_VERSION,
        expected_model_sha256=_MODEL_SHA256,
        bundle_manifest_sha256=_BUNDLE_SHA256,
        split=split,
        implementation_lineage_matches_current=True,
        implementation_lineage_reason=None,
        truth_free_dataset_verified=True,
    )

    assert report.safe_nonzero_actual_model_count == 0
    assert report.unique_raw_executable_signature_count == 1
    assert report.policy_output_degenerate is True
    assert (
        report.actual_model_nonzero_development_evidence_available
        is False
    )
