from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    RecommendationSource,
    RegionFeatureBounds,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceRuntimeConfidenceGateDiagnostic,
    RegionResourceSnapshot,
    RegionalAuthorityLayer,
    snapshot_to_region_graph,
)
from research_modules.scalable_3d_simulation.d4_runtime_compatibility import (
    D4RuntimeCompatibilityOptions,
    D4RuntimeCompatibilityThresholds,
    _apply_candidate_runtime_gate,
    _resolve_d4_model_input,
    assess_d4_runtime_compatibility,
)


EIGHT_REGION_CANDIDATE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "d4_distributed_fallback"
    / "model_registry"
    / "region_resource_a2_8region_runtime_action_shadow_v1"
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
    runtime_gate_diagnostic: (
        RegionResourceRuntimeConfidenceGateDiagnostic | None
    ) = None,
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
            formal_decision_digest_before=None,
            runtime_confidence_gate_diagnostic=(
                runtime_gate_diagnostic
            ),
        ),
    )


def _runtime_gate_diagnostic(
    *,
    candidate_permitted: bool,
    gate_sha256: str = "b" * 64,
) -> RegionResourceRuntimeConfidenceGateDiagnostic:
    return RegionResourceRuntimeConfidenceGateDiagnostic(
        model_raw_inference_executed=True,
        gate_applied=True,
        action_consistent=candidate_permitted,
        raw_confidence=0.90,
        effective_confidence=0.90 if candidate_permitted else 0.59,
        candidate_permitted_after_gate=candidate_permitted,
        rule_fallback_due_to_gate=not candidate_permitted,
        gate_content_sha256=gate_sha256,
        formal_decision_digest=None,
        fallback_reason=(
            None
            if candidate_permitted
            else "runtime_rule_action_consistency_gate_rejected"
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


def test_runtime_gate_diagnostic_separates_raw_and_permitted_execution() -> None:
    snapshot = _snapshot()
    bounds = RegionFeatureBounds.from_graphs(
        (snapshot_to_region_graph(snapshot),)
    )
    diagnostic = _runtime_gate_diagnostic(candidate_permitted=True)
    result = assess_d4_runtime_compatibility(
        (_frame(snapshot, runtime_gate_diagnostic=diagnostic),),
        feature_bounds=bounds,
        model_version="test-model",
        model_sha256="a" * 64,
        thresholds=D4RuntimeCompatibilityThresholds(
            minimum_frame_count=1,
            minimum_in_distribution_fraction=1.0,
            minimum_model_evaluated_frame_count=1,
        ),
        bundle_metadata={
            "runtime_confidence_gate": {
                "content_sha256": diagnostic.gate_content_sha256,
            }
        },
    )

    assert result["runtime_distribution_compatible"] is True
    assert (
        result[
            "runtime_confidence_gate_raw_model_inference_frame_count"
        ]
        == 1
    )
    assert result["runtime_confidence_gate_applied_frame_count"] == 1
    assert (
        result[
            "runtime_confidence_gate_candidate_permitted_frame_count"
        ]
        == 1
    )
    assert (
        result["runtime_confidence_gate_rule_fallback_frame_count"]
        == 0
    )
    assert result["blockers"] == []
    assert result["frames"][0][
        "runtime_confidence_gate_diagnostic"
    ] == diagnostic.to_dict()
    candidate_result = _apply_candidate_runtime_gate(
        result,
        candidate={
            "applicable_region_count": 8,
            "confidence_calibration_accepted": True,
            "read_only_shadow": True,
            "permissions": {
                "schema": "test-permissions-v1",
                "assist_enabled": False,
                "control_enabled": False,
            },
        },
        cases=({"region_count": 8},),
    )
    assert candidate_result[
        "candidate_runtime_confidence_gate_bound"
    ] is True
    assert (
        candidate_result["raw_bundle_model_evaluated_frame_count"]
        == 1
    )
    assert (
        candidate_result[
            "candidate_permitted_model_evaluated_frame_count"
        ]
        == 1
    )
    assert candidate_result["candidate_blockers"] == []
    assert candidate_result["paired_development_rollout_allowed"] is True


def test_runtime_gate_rejection_keeps_raw_execution_visible() -> None:
    snapshot = _snapshot()
    bounds = RegionFeatureBounds.from_graphs(
        (snapshot_to_region_graph(snapshot),)
    )
    diagnostic = _runtime_gate_diagnostic(candidate_permitted=False)
    result = assess_d4_runtime_compatibility(
        (
            _frame(
                snapshot,
                fallback_reason=(
                    "runtime_rule_action_consistency_gate_rejected"
                ),
                runtime_gate_diagnostic=diagnostic,
            ),
        ),
        feature_bounds=bounds,
        model_version="test-model",
        model_sha256="a" * 64,
        thresholds=D4RuntimeCompatibilityThresholds(
            minimum_frame_count=1,
            minimum_in_distribution_fraction=1.0,
            minimum_model_evaluated_frame_count=1,
        ),
        bundle_metadata={
            "runtime_confidence_gate": {
                "content_sha256": diagnostic.gate_content_sha256,
            }
        },
    )

    assert (
        result[
            "runtime_confidence_gate_raw_model_inference_frame_count"
        ]
        == 1
    )
    assert result["runtime_confidence_gate_applied_frame_count"] == 1
    assert (
        result[
            "runtime_confidence_gate_candidate_permitted_frame_count"
        ]
        == 0
    )
    assert (
        result["runtime_confidence_gate_rule_fallback_frame_count"]
        == 1
    )
    assert result["runtime_distribution_compatible"] is False
    assert result["blockers"] == [
        "no_candidate_permitted_after_runtime_gate"
    ]
    candidate_result = _apply_candidate_runtime_gate(
        result,
        candidate={
            "applicable_region_count": 8,
            "confidence_calibration_accepted": True,
            "read_only_shadow": True,
            "permissions": {
                "schema": "test-permissions-v1",
                "assist_enabled": False,
                "control_enabled": False,
            },
        },
        cases=({"region_count": 8},),
    )
    assert candidate_result["candidate_blockers"] == [
        "candidate_runtime_confidence_gate_no_permitted_execution"
    ]
    assert (
        candidate_result[
            "candidate_permitted_model_evaluated_frame_count"
        ]
        == 0
    )
    assert candidate_result["paired_development_rollout_allowed"] is False


def test_runtime_gate_manifest_requires_matching_diagnostic() -> None:
    snapshot = _snapshot()
    bounds = RegionFeatureBounds.from_graphs(
        (snapshot_to_region_graph(snapshot),)
    )
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
        bundle_metadata={
            "runtime_confidence_gate": {
                "content_sha256": "b" * 64,
            }
        },
    )

    assert result["runtime_distribution_compatible"] is False
    assert result["blockers"] == [
        "runtime_confidence_gate_diagnostic_missing",
        "no_raw_model_inference",
        "runtime_confidence_gate_not_applied",
        "no_candidate_permitted_after_runtime_gate",
    ]


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


def test_audited_eight_region_candidate_resolves_bundle_and_metadata() -> None:
    bundle_dir, candidate = _resolve_d4_model_input(
        EIGHT_REGION_CANDIDATE_ROOT
    )

    assert bundle_dir == EIGHT_REGION_CANDIDATE_ROOT / "bundle"
    assert candidate is not None
    assert candidate["applicable_region_count"] == 8
    assert candidate["confidence_calibration_accepted"] is False
    assert (
        candidate[
            "validation_action_inconsistent_threshold_pass_count"
        ]
        == 51
    )
    assert candidate["read_only_shadow"] is True
    assert all(
        value is False
        for key, value in candidate["permissions"].items()
        if key != "schema"
    )


def test_candidate_gate_separates_scope_and_calibration() -> None:
    snapshot = _snapshot()
    bounds = RegionFeatureBounds.from_graphs(
        (snapshot_to_region_graph(snapshot),)
    )
    compatibility = assess_d4_runtime_compatibility(
        (_frame(snapshot),),
        feature_bounds=bounds,
        model_version="test-model",
        model_sha256="a" * 64,
        thresholds=D4RuntimeCompatibilityThresholds(
            minimum_frame_count=1,
            minimum_in_distribution_fraction=1.0,
            minimum_model_evaluated_frame_count=1,
        ),
    )
    candidate = {
        "applicable_region_count": 8,
        "confidence_calibration_accepted": False,
        "read_only_shadow": True,
        "permissions": {
            "schema": "test-permissions-v1",
            "assist_enabled": False,
            "control_enabled": False,
        },
    }

    calibration_blocked = _apply_candidate_runtime_gate(
        compatibility,
        candidate=candidate,
        cases=({"region_count": 8},),
    )
    assert calibration_blocked["runtime_distribution_compatible"] is True
    assert (
        calibration_blocked["raw_bundle_model_evaluated_frame_count"]
        == 1
    )
    assert (
        calibration_blocked[
            "candidate_permitted_model_evaluated_frame_count"
        ]
        == 0
    )
    assert calibration_blocked["paired_development_rollout_allowed"] is False
    assert calibration_blocked["candidate_blockers"] == [
        "candidate_confidence_calibration_not_accepted"
    ]

    scope_blocked = _apply_candidate_runtime_gate(
        compatibility,
        candidate={
            **candidate,
            "confidence_calibration_accepted": True,
        },
        cases=({"region_count": 2},),
    )
    assert scope_blocked["candidate_scope_compatible"] is False
    assert scope_blocked["candidate_blockers"] == [
        "candidate_region_count_out_of_scope"
    ]

    accepted = _apply_candidate_runtime_gate(
        compatibility,
        candidate={
            **candidate,
            "confidence_calibration_accepted": True,
        },
        cases=({"region_count": 8},),
    )
    assert accepted["candidate_scope_compatible"] is True
    assert (
        accepted["candidate_permitted_model_evaluated_frame_count"]
        == 1
    )
    assert accepted["paired_development_rollout_allowed"] is True
