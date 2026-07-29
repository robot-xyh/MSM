from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    RecommendationSource,
    RegionFeatureBounds,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceSnapshot,
    RegionalAuthorityLayer,
    snapshot_to_region_graph,
)
from research_modules.scalable_3d_simulation.d4_runtime_compatibility import (
    D4RuntimeCompatibilityOptions,
    D4RuntimeCompatibilityThresholds,
    assess_d4_runtime_compatibility,
)


def _snapshot(*, d1_uncertainty: float = 0.2) -> RegionResourceSnapshot:
    nodes = tuple(
        RegionResourceNode(
            region_id=f"region-{index:03d}",
            target_demand=2.0,
            high_threat_backlog=0.0,
            d1_uncertainty=d1_uncertainty,
            d2_uncertainty=0.1,
            d5_visibility=0.9,
            d5_consistency=0.9,
            available_resources=3,
            reserve_resources=1,
            committed_resources=2,
            secondary_coverage=0.9,
            secondary_readiness=0.9,
            communication_capacity=50.0,
            communication_latency_s=0.02,
            packet_loss_rate=0.01,
            current_owner_id="CENTER",
            current_owner_layer=RegionalAuthorityLayer.CENTER,
            plan_id="plan",
            plan_version=1,
            epoch=1,
            lease_expires_at_s=120.0,
            coalition_ack_complete=True,
        )
        for index in range(2)
    )
    return RegionResourceSnapshot(
        snapshot_id=f"snapshot-{d1_uncertainty}",
        scenario_id="test",
        scenario_version="v1",
        seed=2000,
        timestamp_s=1.0,
        regions=nodes,
        edges=(
            RegionResourceEdge(
                source_region_id="region-000",
                target_region_id="region-001",
                transferable_resources=1,
                distance_m=1000.0,
                transfer_time_s=20.0,
                bandwidth_mbps=20.0,
                communication_available=True,
                maneuver_available=True,
                partitioned=False,
                bidirectional=True,
                edge_id="edge-000",
            ),
        ),
    )


def _frame(
    snapshot: RegionResourceSnapshot,
    *,
    fallback_reason: str | None = None,
) -> SimpleNamespace:
    fallback_used = fallback_reason is not None
    recommendation = SimpleNamespace(
        source=(
            RecommendationSource.RULE
            if fallback_used
            else RecommendationSource.LEARNED
        ),
        model_sha256=None if fallback_used else "a" * 64,
    )
    return SimpleNamespace(
        frame_index=0,
        timestamp_s=snapshot.timestamp_s,
        snapshot=snapshot,
        recommendation=SimpleNamespace(
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            recommendation=recommendation,
            formal_decision_unchanged=True,
        ),
    )


def test_in_distribution_model_frame_passes_development_preflight() -> None:
    snapshot = _snapshot()
    graph = snapshot_to_region_graph(snapshot)
    bounds = RegionFeatureBounds.from_graphs((graph,))

    result = assess_d4_runtime_compatibility(
        (_frame(snapshot),),
        feature_bounds=bounds,
        model_version="test-model",
        model_sha256="a" * 64,
        thresholds=D4RuntimeCompatibilityThresholds(
            minimum_frame_count=1,
            minimum_in_distribution_fraction=1.0,
            minimum_model_evaluated_frame_count=1,
        ),
        online_truth_use_count=0,
    )

    assert result["runtime_distribution_compatible"] is True
    assert result["model_evaluated_frame_count"] == 1
    assert result["blockers"] == []
    assert result["assist_or_strategy_claim_granted"] is False


def test_feature_ood_is_reported_without_widening_model_bounds() -> None:
    training_snapshot = _snapshot(d1_uncertainty=0.2)
    bounds = RegionFeatureBounds.from_graphs(
        (snapshot_to_region_graph(training_snapshot),)
    )
    runtime_snapshot = _snapshot(d1_uncertainty=20.0)

    result = assess_d4_runtime_compatibility(
        (_frame(runtime_snapshot, fallback_reason="feature_ood"),),
        feature_bounds=bounds,
        model_version="test-model",
        model_sha256="a" * 64,
        thresholds=D4RuntimeCompatibilityThresholds(
            minimum_frame_count=1,
            minimum_in_distribution_fraction=1.0,
            minimum_model_evaluated_frame_count=1,
        ),
    )

    assert result["runtime_distribution_compatible"] is False
    assert "runtime_feature_distribution_mismatch" in result["blockers"]
    assert "no_nonfallback_model_evaluation" in result["blockers"]
    assert result["ood_gate_disagreement_count"] == 0
    assert any(
        item["feature_name"] == "d1_uncertainty_log"
        for item in result["top_feature_violations"]
    )


def test_preflight_options_reject_invalid_or_duplicate_inputs(
    tmp_path: Path,
) -> None:
    options = D4RuntimeCompatibilityOptions(
        config_path=tmp_path / "config.json",
        bundle_dir=tmp_path / "bundle",
        output_dir=tmp_path / "output",
        recon_count=0,
    )
    assert options.recon_count == 0

    with pytest.raises(ValueError, match="unique"):
        D4RuntimeCompatibilityOptions(
            config_path=tmp_path / "config.json",
            bundle_dir=tmp_path / "bundle",
            output_dir=tmp_path / "output",
            seeds=(2000, 2000),
        )

    with pytest.raises(ValueError, match="positive"):
        D4RuntimeCompatibilityOptions(
            config_path=tmp_path / "config.json",
            bundle_dir=tmp_path / "bundle",
            output_dir=tmp_path / "output",
            duration_s=0.0,
        )

    with pytest.raises(ValueError, match="fixed at 0.05"):
        D4RuntimeCompatibilityThresholds(ood_margin=0.10)
