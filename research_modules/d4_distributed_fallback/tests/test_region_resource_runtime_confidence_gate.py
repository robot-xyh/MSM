from __future__ import annotations

import json
from math import log
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

from d4_distributed_fallback.region_resource import (
    AdvisorMode,
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceNode,
    RegionResourceProjectionConfig,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
)
from d4_distributed_fallback.region_resource_dataset import (
    RegionLearningSplit,
)
from d4_distributed_fallback.region_resource_eight_region_candidate import (
    _runtime_confidence_gate_metrics,
)
from d4_distributed_fallback.region_resource_learning import (
    REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_MODE,
    LearnedRegionResourcePolicy,
    ModelBundleValidationError,
    RegionResourceAdvisor,
    RegionResourceAdvisorConfig,
    RegionResourceRuntimeConfidenceGateConfig,
    RuntimeConfidenceGateContextError,
    SharedRegionGraphActorCritic,
    load_region_resource_model_bundle,
    save_region_resource_model_bundle,
    snapshot_to_region_graph,
)
from d4_distributed_fallback.regional_failover import (
    RegionOwnershipMetadata,
    RegionalAction,
    RegionalAuthorityLayer,
    RegionalFailoverDecision,
    RegionalRegionDecision,
    RegionalScenarioMetadata,
)


MODEL_VERSION = (
    "d4-region-a2-8region-runtime-action-readiness-shadow-v2"
)


def _snapshot() -> RegionResourceSnapshot:
    node = RegionResourceNode(
        region_id="region-000",
        target_demand=1.0,
        high_threat_backlog=0.0,
        d1_uncertainty=0.2,
        d2_uncertainty=0.1,
        d5_visibility=0.8,
        d5_consistency=0.9,
        available_resources=10,
        reserve_resources=2,
        secondary_coverage=0.9,
        secondary_readiness=0.0,
        communication_capacity=100.0,
        communication_latency_s=0.02,
        packet_loss_rate=0.01,
        current_owner_id="CENTER",
        current_owner_layer=RegionalAuthorityLayer.CENTER,
        plan_id="regional-plan",
        plan_version=3,
        epoch=2,
        lease_expires_at_s=20.0,
        coalition_ack_complete=True,
    )
    return RegionResourceSnapshot(
        snapshot_id="runtime-gate-snapshot",
        scenario_id="runtime-gate-test",
        scenario_version="v1",
        seed=7,
        timestamp_s=1.0,
        regions=(node,),
        edges=(),
    )


def _logit(value: float) -> float:
    return log(value / (1.0 - value))


def _model(*, action_consistent: bool) -> SharedRegionGraphActorCritic:
    model = SharedRegionGraphActorCritic(
        hidden_dim=16,
        message_passing_steps=1,
    )
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        model.node_actor.bias[1] = _logit(0.2)
        model.node_actor.bias[2] = _logit(0.12)
        model.node_actor.bias[3] = 10.0 if not action_consistent else -10.0
        model.node_actor.bias[4] = -10.0
        model.confidence_head[0].bias[0] = _logit(0.90)
    model.eval()
    return model


def _save_bundle(
    root: Path,
    *,
    action_consistent: bool,
    runtime_gate: bool,
    projection_config: RegionResourceProjectionConfig | None = None,
) -> Path:
    snapshot = _snapshot()
    bundle_dir = root / (
        "consistent" if action_consistent else "inconsistent"
    )
    projector, rule_policy = _runtime_context(projection_config)
    save_region_resource_model_bundle(
        _model(action_consistent=action_consistent),
        bundle_dir,
        model_version=MODEL_VERSION,
        training_graphs=(snapshot_to_region_graph(snapshot),),
        training_groups=((snapshot.scenario_id, snapshot.seed),),
        created_at_utc="2026-07-29T00:00:00Z",
        runtime_confidence_gate=(
            RegionResourceRuntimeConfidenceGateConfig.from_runtime_context(
                projector=projector,
                rule_policy=rule_policy,
            )
            if runtime_gate
            else None
        ),
    )
    return bundle_dir


def _runtime_context(
    projection_config: RegionResourceProjectionConfig | None = None,
) -> tuple[DeterministicResourceProjector, RuleRegionResourcePolicy]:
    projector = DeterministicResourceProjector(projection_config)
    rule_policy = RuleRegionResourcePolicy(
        RuleRegionResourcePolicyConfig(
            projection=projector.config,
        ),
        projector=projector,
    )
    return projector, rule_policy


def _formal_decision(
    snapshot: RegionResourceSnapshot,
    *,
    execution_allowed: bool,
) -> RegionalFailoverDecision:
    node = snapshot.regions[0]
    scenario = RegionalScenarioMetadata(
        scenario_name=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        task_count=1,
        resource_count=snapshot.total_resources,
        recon_count=0,
        region_count=1,
        region_ids=(node.region_id,),
    )
    ownership = RegionOwnershipMetadata(
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
    )
    region = RegionalRegionDecision(
        region_id=node.region_id,
        selected_layer=node.current_owner_layer,
        action=(
            RegionalAction.CONTINUE_CENTER
            if execution_allowed
            else RegionalAction.HOLD_FOR_REVIEW
        ),
        reason="runtime-gate-fixture",
        ownership=ownership,
        execution_allowed=execution_allowed,
        fail_closed=not execution_allowed,
        risk_factors=(),
        task_ids=(),
    )
    return RegionalFailoverDecision(
        timestamp_s=snapshot.timestamp_s,
        scenario=scenario,
        region_decisions=(region,),
    )


@pytest.mark.parametrize(
    ("action_consistent", "expected_effective", "expected_fallback"),
    [
        (True, 0.90, False),
        (False, 0.59, True),
    ],
)
def test_reloaded_v2_bundle_applies_runtime_gate_before_advisor_threshold(
    tmp_path: Path,
    action_consistent: bool,
    expected_effective: float,
    expected_fallback: bool,
) -> None:
    bundle_dir = _save_bundle(
        tmp_path,
        action_consistent=action_consistent,
        runtime_gate=True,
    )
    loaded = load_region_resource_model_bundle(
        bundle_dir,
        expected_model_version=MODEL_VERSION,
    )
    assert loaded.manifest.runtime_confidence_gate is not None
    assert (
        loaded.manifest.runtime_confidence_gate.mode
        == REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_MODE
    )
    policy = LearnedRegionResourcePolicy(
        loaded.model,
        loaded.manifest,
    )
    raw = policy.recommend_raw(_snapshot())
    assert raw.confidence == pytest.approx(0.90, abs=1.0e-6)
    assert raw.projected is False
    assert raw.fallback_reason is None
    projector, rule_policy = _runtime_context()
    effective, evaluation = (
        policy.recommend_with_runtime_confidence_gate(
            _snapshot(),
            projector=projector,
            rule_policy=rule_policy,
            formal_decision=None,
            minimum_confidence=0.60,
            ood_margin=0.05,
        )
    )
    assert evaluation is not None
    assert evaluation.raw_confidence == pytest.approx(0.90, abs=1.0e-6)
    assert evaluation.effective_confidence == pytest.approx(
        expected_effective,
        abs=1.0e-6,
    )
    assert (
        evaluation.action_consistency.action_consistent
        is action_consistent
    )
    assert effective.confidence == pytest.approx(
        expected_effective,
        abs=1.0e-6,
    )
    assert effective.projected is True

    advisor = RegionResourceAdvisor.from_bundle(
        bundle_dir,
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            inference_timeout_s=2.0,
            minimum_confidence=0.60,
            ood_margin=0.05,
        ),
        expected_model_version=MODEL_VERSION,
    )
    result = advisor.advise(_snapshot())
    assert result.fallback_used is expected_fallback
    diagnostic = result.runtime_confidence_gate_diagnostic
    assert diagnostic is not None
    assert diagnostic.model_raw_inference_executed is True
    assert diagnostic.gate_applied is True
    assert diagnostic.action_consistent is action_consistent
    assert diagnostic.raw_confidence == pytest.approx(
        0.90,
        abs=1.0e-6,
    )
    assert diagnostic.effective_confidence == pytest.approx(
        expected_effective,
        abs=1.0e-6,
    )
    assert (
        diagnostic.candidate_permitted_after_gate
        is (not expected_fallback)
    )
    assert diagnostic.rule_fallback_due_to_gate is expected_fallback
    assert diagnostic.truth_identifier_use_count == 0
    assert result.assist_eligible is False
    assert result.effective_mode == AdvisorMode.SHADOW
    serialized = result.to_dict()[
        "runtime_confidence_gate_diagnostic"
    ]
    assert serialized == diagnostic.to_dict()
    if expected_fallback:
        assert result.fallback_reason == (
            "runtime_rule_action_consistency_gate_rejected"
        )
        assert result.recommendation is not None
        assert result.recommendation.source == RecommendationSource.RULE
    else:
        assert result.fallback_reason is None
        assert result.recommendation is not None
        assert result.recommendation.source == RecommendationSource.LEARNED


def test_validation_metrics_and_runtime_advisor_use_the_same_gate_helper(
    tmp_path: Path,
) -> None:
    bundle_dir = _save_bundle(
        tmp_path,
        action_consistent=False,
        runtime_gate=True,
    )
    loaded = load_region_resource_model_bundle(bundle_dir)
    policy = LearnedRegionResourcePolicy(
        loaded.model,
        loaded.manifest,
    )
    projector, rule_policy = _runtime_context()
    _, evaluation = policy.recommend_with_runtime_confidence_gate(
        _snapshot(),
        projector=projector,
        rule_policy=rule_policy,
        formal_decision=None,
        minimum_confidence=0.60,
        ood_margin=0.05,
    )
    assert evaluation is not None
    frame = SimpleNamespace(
        snapshot=_snapshot(),
        target=SimpleNamespace(
            recommendation=evaluation.reference_recommendation
        ),
    )
    episode = SimpleNamespace(frames=(frame,))
    dataset = SimpleNamespace(
        episodes=lambda split: (
            (episode,)
            if split == RegionLearningSplit.VALIDATION
            else ()
        )
    )
    metrics = _runtime_confidence_gate_metrics(
        policy,
        dataset,
        split=RegionLearningSplit.VALIDATION,
        threshold=0.60,
        ood_margin=0.05,
        projector=projector,
        rule_policy=rule_policy,
        formal_decision=None,
    )
    assert metrics["raw"]["confidence_mean"] == pytest.approx(
        evaluation.raw_confidence
    )
    assert metrics["effective"]["confidence_mean"] == pytest.approx(
        evaluation.effective_confidence
    )
    assert metrics["raw"][
        "action_inconsistent_threshold_pass_count"
    ] == 1
    assert metrics["effective"][
        "action_inconsistent_threshold_pass_count"
    ] == 0
    assert metrics["runtime_reference_target_mismatch_count"] == 0
    assert metrics["validation_target_controls_effective_confidence"] is False
    assert metrics["formal_decision"] is None
    assert metrics["formal_decision_semantics"] == (
        "explicit_none_matching_dataset_generation"
    )


def test_formal_decision_projection_is_shared_by_gate_and_advisor(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    formal_decision = _formal_decision(
        snapshot,
        execution_allowed=False,
    )
    bundle_dir = _save_bundle(
        tmp_path,
        action_consistent=False,
        runtime_gate=True,
    )
    loaded = load_region_resource_model_bundle(bundle_dir)
    policy = LearnedRegionResourcePolicy(
        loaded.model,
        loaded.manifest,
    )
    projector, rule_policy = _runtime_context()
    _, without_formal = policy.recommend_with_runtime_confidence_gate(
        snapshot,
        projector=projector,
        rule_policy=rule_policy,
        formal_decision=None,
        minimum_confidence=0.60,
        ood_margin=0.05,
    )
    effective, with_formal = (
        policy.recommend_with_runtime_confidence_gate(
            snapshot,
            projector=projector,
            rule_policy=rule_policy,
            formal_decision=formal_decision,
            minimum_confidence=0.60,
            ood_margin=0.05,
        )
    )
    assert without_formal is not None
    assert with_formal is not None
    assert (
        without_formal.projected_candidate.actions
        != with_formal.projected_candidate.actions
    )
    assert without_formal.action_consistency.action_consistent is False
    assert with_formal.action_consistency.action_consistent is True

    advisor = RegionResourceAdvisor.from_bundle(
        bundle_dir,
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            inference_timeout_s=2.0,
            minimum_confidence=0.60,
            ood_margin=0.05,
        ),
    )
    result = advisor.advise(
        snapshot,
        formal_decision=formal_decision,
    )
    assert result.fallback_used is False
    assert result.recommendation is not None
    assert result.recommendation.actions == effective.actions
    assert result.recommendation.transfers == effective.transfers
    assert (
        result.recommendation.projection_rejections
        == effective.projection_rejections
    )
    diagnostic = result.runtime_confidence_gate_diagnostic
    assert diagnostic is not None
    assert diagnostic.formal_decision_digest == (
        result.formal_decision_digest_before
    )
    assert diagnostic.action_consistent is True
    assert diagnostic.candidate_permitted_after_gate is True


def test_custom_projection_config_must_match_bundle_gate(
    tmp_path: Path,
) -> None:
    custom_projection = RegionResourceProjectionConfig(
        minimum_reserve_ratio=0.20,
        minimum_reserve_resources=2,
        advisory_ttl_s=2.0,
    )
    bundle_dir = _save_bundle(
        tmp_path,
        action_consistent=True,
        runtime_gate=True,
        projection_config=custom_projection,
    )
    matching = RegionResourceAdvisor.from_bundle(
        bundle_dir,
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            inference_timeout_s=2.0,
            minimum_confidence=0.60,
            ood_margin=0.05,
            projection=custom_projection,
        ),
    ).advise(_snapshot())
    assert matching.fallback_used is False
    assert (
        matching.runtime_confidence_gate_diagnostic
        is not None
    )
    assert (
        matching.runtime_confidence_gate_diagnostic.gate_applied
        is True
    )

    mismatching = RegionResourceAdvisor.from_bundle(
        bundle_dir,
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            inference_timeout_s=2.0,
            minimum_confidence=0.60,
            ood_margin=0.05,
        ),
    ).advise(_snapshot())
    assert mismatching.fallback_used is True
    assert mismatching.fallback_reason == (
        "runtime_confidence_gate_context_mismatch"
    )
    diagnostic = mismatching.runtime_confidence_gate_diagnostic
    assert diagnostic is not None
    assert diagnostic.model_raw_inference_executed is False
    assert diagnostic.gate_applied is False
    assert diagnostic.rule_fallback_due_to_gate is True


def test_runtime_gate_rejects_equal_config_with_different_projector_identity(
    tmp_path: Path,
) -> None:
    bundle_dir = _save_bundle(
        tmp_path,
        action_consistent=True,
        runtime_gate=True,
    )
    loaded = load_region_resource_model_bundle(bundle_dir)
    policy = LearnedRegionResourcePolicy(
        loaded.model,
        loaded.manifest,
    )
    projector, _ = _runtime_context()
    _, rule_policy = _runtime_context()

    with pytest.raises(
        RuntimeConfidenceGateContextError,
        match="rule_policy_projector_identity",
    ):
        policy.recommend_with_runtime_confidence_gate(
            _snapshot(),
            projector=projector,
            rule_policy=rule_policy,
            formal_decision=None,
            minimum_confidence=0.60,
            ood_margin=0.05,
        )


@pytest.mark.parametrize(
    ("minimum_confidence", "ood_margin"),
    [
        (0.59, 0.05),
        (0.60, 0.04),
    ],
)
def test_runtime_gate_rejects_lowered_fixed_advisor_gates(
    tmp_path: Path,
    minimum_confidence: float,
    ood_margin: float,
) -> None:
    bundle_dir = _save_bundle(
        tmp_path,
        action_consistent=True,
        runtime_gate=True,
    )
    result = RegionResourceAdvisor.from_bundle(
        bundle_dir,
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            inference_timeout_s=2.0,
            minimum_confidence=minimum_confidence,
            ood_margin=ood_margin,
        ),
    ).advise(_snapshot())
    assert result.fallback_used is True
    assert result.fallback_reason == (
        "runtime_confidence_gate_context_mismatch"
    )
    diagnostic = result.runtime_confidence_gate_diagnostic
    assert diagnostic is not None
    assert diagnostic.gate_applied is False
    assert diagnostic.model_raw_inference_executed is False


def test_external_acceptance_claim_cannot_bypass_bundle_runtime_gate(
    tmp_path: Path,
) -> None:
    bundle_dir = _save_bundle(
        tmp_path,
        action_consistent=False,
        runtime_gate=True,
    )
    external_candidate_manifest = {
        "confidence_calibration_accepted": True,
    }
    assert external_candidate_manifest["confidence_calibration_accepted"]

    loaded = load_region_resource_model_bundle(bundle_dir)
    raw_output = loaded.model(snapshot_to_region_graph(_snapshot()))
    assert float(raw_output.confidence.detach()) > 0.60

    result = RegionResourceAdvisor.from_bundle(
        bundle_dir,
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            inference_timeout_s=2.0,
        ),
    ).advise(_snapshot())
    assert result.fallback_used is True
    assert result.fallback_reason == (
        "runtime_rule_action_consistency_gate_rejected"
    )


def test_runtime_gate_manifest_parameter_tamper_is_rejected(
    tmp_path: Path,
) -> None:
    bundle_dir = _save_bundle(
        tmp_path,
        action_consistent=False,
        runtime_gate=True,
    )
    manifest_path = bundle_dir / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["runtime_confidence_gate"][
        "inconsistent_confidence_cap"
    ] = 0.60
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ModelBundleValidationError,
        match="manifest_invalid:ValueError",
    ):
        load_region_resource_model_bundle(bundle_dir)


def test_runtime_gate_projection_config_tamper_is_rejected(
    tmp_path: Path,
) -> None:
    bundle_dir = _save_bundle(
        tmp_path,
        action_consistent=True,
        runtime_gate=True,
    )
    manifest_path = bundle_dir / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["runtime_confidence_gate"]["projection_config"][
        "minimum_reserve_ratio"
    ] = 0.20
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ModelBundleValidationError,
        match="manifest_invalid:ValueError",
    ):
        load_region_resource_model_bundle(bundle_dir)


def test_legacy_bundle_omits_runtime_gate_and_preserves_raw_behavior(
    tmp_path: Path,
) -> None:
    bundle_dir = _save_bundle(
        tmp_path,
        action_consistent=False,
        runtime_gate=False,
    )
    payload = (bundle_dir / "manifest.json").read_text(encoding="utf-8")
    assert '"runtime_confidence_gate"' not in payload
    loaded = load_region_resource_model_bundle(bundle_dir)
    assert loaded.manifest.runtime_confidence_gate is None
    recommendation = LearnedRegionResourcePolicy(
        loaded.model,
        loaded.manifest,
    ).recommend_raw(_snapshot())
    assert recommendation.confidence == pytest.approx(0.90, abs=1.0e-6)
    assert recommendation.fallback_reason is None
    result = RegionResourceAdvisor.from_bundle(
        bundle_dir,
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            inference_timeout_s=2.0,
            minimum_confidence=0.0,
            ood_margin=0.0,
        ),
    ).advise(_snapshot())
    assert result.runtime_confidence_gate_diagnostic is None
    assert (
        "runtime_confidence_gate_diagnostic"
        not in result.to_dict()
    )
