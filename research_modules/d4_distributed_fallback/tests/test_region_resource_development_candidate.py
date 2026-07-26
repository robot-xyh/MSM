from __future__ import annotations

from dataclasses import replace

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
from d4_distributed_fallback.region_resource_development_candidate import (
    RegionResourceDevelopmentCandidateConfig,
    evaluate_region_resource_development_gate,
)
from d4_distributed_fallback.regional_failover import RegionalAuthorityLayer


_MODEL_SHA256 = "a" * 64


def _snapshot(
    *,
    timestamp_s: float = 1.0,
    lease_expires_at_s: float = 100.0,
    coalition_ack_complete: bool = True,
    partitioned: bool = False,
) -> RegionResourceSnapshot:
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
        "plan_id": "PLAN-CALIBRATION",
        "plan_version": 3,
        "epoch": 4,
        "lease_expires_at_s": lease_expires_at_s,
        "coalition_ack_complete": coalition_ack_complete,
        "owner_active": True,
        "fault_fenced": False,
    }
    return RegionResourceSnapshot(
        snapshot_id="snapshot-calibration",
        scenario_id="isolated-calibration-fixture",
        scenario_version="v1",
        seed=71,
        timestamp_s=timestamp_s,
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
                partitioned=partitioned,
            ),
        ),
    )


def _recommendation(
    snapshot: RegionResourceSnapshot,
    *,
    confidence: float = 0.9,
    expected_epoch: int | None = None,
    with_transfer: bool = False,
) -> RegionResourceRecommendation:
    actions = tuple(
        RegionResourceAction(
            region_id=node.region_id,
            resource_quota_delta=0,
            reserve_ratio=0.25,
            reconnaissance_priority=0.7,
            hold=False,
            request_replan=False,
            expected_owner_id=node.current_owner_id,
            expected_owner_layer=node.current_owner_layer,
            expected_plan_id=node.plan_id,
            expected_plan_version=node.plan_version,
            expected_epoch=(
                node.epoch if expected_epoch is None else expected_epoch
            ),
            expected_lease_expires_at_s=node.lease_expires_at_s,
            reasons=("isolated_fixture",),
        )
        for node in snapshot.regions
    )
    transfers = (
        (
            RegionTransferSuggestion(
                source_region_id="region-b",
                target_region_id="region-a",
                resource_count=1,
                edge_id="edge-b-a",
                expected_transfer_time_s=4.0,
                reasons=("isolated_fixture",),
            ),
        )
        if with_transfer
        else ()
    )
    return RegionResourceRecommendation(
        snapshot_id=snapshot.snapshot_id,
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        seed=snapshot.seed,
        authority_digest=snapshot.authority_digest,
        created_at_s=snapshot.timestamp_s,
        policy_name="d4-isolated-fixture",
        policy_version="development-only",
        source=RecommendationSource.LEARNED,
        confidence=confidence,
        actions=actions,
        transfers=transfers,
        model_sha256=_MODEL_SHA256,
    )


class _FixturePolicy:
    def __init__(
        self,
        recommendation: RegionResourceRecommendation,
        *,
        ood: bool = False,
    ) -> None:
        self.recommendation = recommendation
        self.ood = ood

    def recommend_raw(
        self, snapshot: RegionResourceSnapshot
    ) -> RegionResourceRecommendation:
        return self.recommendation

    def is_ood(self, snapshot: RegionResourceSnapshot, *, margin: float) -> bool:
        return self.ood


def _evaluate(
    snapshot: RegionResourceSnapshot,
    recommendation: RegionResourceRecommendation,
    **kwargs: object,
):
    return evaluate_region_resource_development_gate(
        _FixturePolicy(recommendation),
        snapshot,
        **kwargs,
    )


def test_isolated_fixture_has_positive_considered_and_gate_pass_sample() -> None:
    """This fixture proves a code path only; it is not system-benefit evidence."""

    snapshot = _snapshot()
    evaluation = _evaluate(snapshot, _recommendation(snapshot))

    assert evaluation.gate.candidate_considered is True
    assert evaluation.gate.gate_pass is True
    assert evaluation.gate.rule_fallback is False
    assert evaluation.consumption is not None
    assert evaluation.consumption.consumable is True


def test_development_candidate_fixed_gates_cannot_be_relaxed() -> None:
    with pytest.raises(ValueError, match="confidence threshold must remain 0.6"):
        RegionResourceDevelopmentCandidateConfig(minimum_confidence=0.59)
    with pytest.raises(ValueError, match="latency limit must remain 50 ms"):
        RegionResourceDevelopmentCandidateConfig(latency_limit_ms=50.1)


def test_low_confidence_ood_timeout_and_nonfinite_fail_closed() -> None:
    snapshot = _snapshot()
    low = _evaluate(snapshot, _recommendation(snapshot, confidence=0.59))
    assert low.gate.gate_pass is False
    assert low.gate.rule_fallback is True
    assert "candidate_low_confidence" in low.gate.rejection_reasons

    ood = evaluate_region_resource_development_gate(
        _FixturePolicy(_recommendation(snapshot), ood=True),
        snapshot,
    )
    assert ood.gate.gate_pass is False
    assert "candidate_ood_rejected" in ood.gate.rejection_reasons

    timeout = _evaluate(
        snapshot,
        _recommendation(snapshot),
        latency_override_ms=50.000001,
    )
    assert timeout.gate.gate_pass is False
    assert "candidate_inference_timeout" in timeout.gate.rejection_reasons

    corrupted = _recommendation(snapshot)
    object.__setattr__(corrupted.actions[0], "reserve_ratio", float("nan"))
    nonfinite = _evaluate(snapshot, corrupted)
    assert nonfinite.gate.gate_pass is False
    assert "candidate_output_nonfinite" in nonfinite.gate.rejection_reasons


@pytest.mark.parametrize(
    ("snapshot", "recommendation_factory", "expected_fragment"),
    [
        (
            _snapshot(),
            lambda snapshot: _recommendation(snapshot, expected_epoch=3),
            "authority_version_mismatch",
        ),
        (
            _snapshot(timestamp_s=1.0, lease_expires_at_s=1.0),
            _recommendation,
            "authority_lease_expired",
        ),
        (
            _snapshot(coalition_ack_complete=False),
            _recommendation,
            "coalition_ack_incomplete",
        ),
        (
            _snapshot(partitioned=True),
            lambda snapshot: _recommendation(snapshot, with_transfer=True),
            "edge_unavailable_or_partitioned",
        ),
    ],
)
def test_authority_lease_ack_and_partition_fences_fail_closed(
    snapshot: RegionResourceSnapshot,
    recommendation_factory,
    expected_fragment: str,
) -> None:
    evaluation = _evaluate(snapshot, recommendation_factory(snapshot))

    assert evaluation.gate.gate_pass is False
    assert evaluation.gate.rule_fallback is True
    assert evaluation.gate.candidate_safety_projection_passed is False
    assert any(
        expected_fragment in reason
        for reason in evaluation.gate.rejection_reasons
    )


def test_projection_exception_fails_closed() -> None:
    class _BrokenProjector:
        def project(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("isolated_projection_failure")

    snapshot = _snapshot()
    evaluation = _evaluate(
        snapshot,
        _recommendation(snapshot),
        projector=_BrokenProjector(),
    )

    assert evaluation.gate.gate_pass is False
    assert evaluation.gate.rule_fallback is True
    assert "candidate_projection_failed:RuntimeError" in (
        evaluation.gate.rejection_reasons
    )
    assert "candidate_safety_projection_rejected" in (
        evaluation.gate.rejection_reasons
    )
