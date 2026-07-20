from __future__ import annotations

from dataclasses import replace
import json
from math import isfinite
from pathlib import Path
from time import sleep

import pytest
import torch

from d4_distributed_fallback.region_resource import (
    AdvisorMode,
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceAction,
    RegionResourceAdvisoryContract,
    RegionResourceAdvisoryGate,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceRecommendation,
    RegionResourceRewardMetrics,
    RegionResourceSnapshot,
    RegionTransferSuggestion,
    RuleRegionResourcePolicy,
    ShadowEpisodeMetrics,
    ShadowPairedEvaluator,
    compute_region_resource_reward,
    split_scenario_seed_groups,
)
from d4_distributed_fallback.region_resource_cli import main as resource_cli_main
from d4_distributed_fallback.region_resource_learning import (
    BehaviorCloningSample,
    GraphPPOTransition,
    LearnedRegionResourcePolicy,
    NonFinitePolicyOutput,
    RegionResourceAdvisor,
    RegionResourceAdvisorConfig,
    SharedRegionGraphActorCritic,
    behavior_cloning_loss,
    behavior_cloning_step,
    load_region_resource_model_bundle,
    native_clipped_ppo_update,
    recommendation_to_policy_target,
    sample_graph_policy_action,
    save_region_resource_model_bundle,
    snapshot_to_region_graph,
)
from d4_distributed_fallback.regional_failover import (
    CoalitionCommitSummary,
    RegionOwnershipMetadata,
    RegionalAction,
    RegionalAuthorityLayer,
    RegionalFailoverDecision,
    RegionalRegionDecision,
    RegionalScenarioMetadata,
)


def _snapshot(
    region_count: int = 3,
    *,
    owner_layers: tuple[RegionalAuthorityLayer, ...] | None = None,
    partitioned_edge: int | None = None,
    communication_available: bool = True,
    timestamp_s: float = 1.0,
    lease_expires_at_s: float = 20.0,
    ack_complete: bool = True,
    epoch: int = 2,
    d1_uncertainty: float = 0.2,
) -> RegionResourceSnapshot:
    layers = owner_layers or (RegionalAuthorityLayer.CENTER,) * region_count
    if len(layers) != region_count:
        raise ValueError("owner layer fixture length mismatch")
    nodes: list[RegionResourceNode] = []
    for index, layer in enumerate(layers):
        owner_id = {
            RegionalAuthorityLayer.CENTER: "CENTER",
            RegionalAuthorityLayer.SECONDARY: f"RECON-{index % 2}",
            RegionalAuthorityLayer.DISTRIBUTED: f"PEER-{index}",
        }[layer]
        available = 2 if index == 0 else (10 if index == region_count - 1 else 4)
        nodes.append(
            RegionResourceNode(
                region_id=f"region-{index:03d}",
                target_demand=8.0 if index == 0 else 1.0,
                high_threat_backlog=2.0 if index == 0 else 0.0,
                d1_uncertainty=d1_uncertainty,
                d2_uncertainty=0.1,
                d5_visibility=0.8,
                d5_consistency=0.9,
                available_resources=available,
                reserve_resources=1,
                secondary_coverage=0.9,
                secondary_readiness=0.9,
                communication_capacity=100.0,
                communication_latency_s=0.02,
                packet_loss_rate=0.01,
                current_owner_id=owner_id,
                current_owner_layer=layer,
                plan_id="regional-plan",
                plan_version=3,
                epoch=epoch,
                lease_expires_at_s=lease_expires_at_s,
                coalition_ack_complete=ack_complete,
            )
        )
    edges = tuple(
        RegionResourceEdge(
            source_region_id=f"region-{index:03d}",
            target_region_id=f"region-{index + 1:03d}",
            transferable_resources=5,
            distance_m=1000.0,
            transfer_time_s=20.0,
            bandwidth_mbps=20.0,
            communication_available=communication_available,
            partitioned=index == partitioned_edge,
            bidirectional=True,
            edge_id=f"edge-{index:03d}",
        )
        for index in range(region_count - 1)
    )
    return RegionResourceSnapshot(
        snapshot_id=f"snapshot-{region_count}",
        scenario_id=f"scenario-{region_count}",
        scenario_version="v1",
        seed=7,
        timestamp_s=timestamp_s,
        regions=tuple(nodes),
        edges=edges,
    )


def _raw_proposal(
    snapshot: RegionResourceSnapshot,
    transfers: tuple[RegionTransferSuggestion, ...],
    *,
    action_changes: dict[str, dict[str, object]] | None = None,
    confidence: float = 0.9,
) -> RegionResourceRecommendation:
    changes = action_changes or {}
    deltas = {node.region_id: 0 for node in snapshot.regions}
    for transfer in transfers:
        deltas[transfer.source_region_id] -= transfer.resource_count
        deltas[transfer.target_region_id] += transfer.resource_count
    actions: list[RegionResourceAction] = []
    for node in snapshot.regions:
        values: dict[str, object] = {
            "region_id": node.region_id,
            "resource_quota_delta": deltas[node.region_id],
            "reserve_ratio": 0.2,
            "reconnaissance_priority": 0.5,
            "hold": False,
            "request_replan": False,
            "expected_owner_id": node.current_owner_id,
            "expected_owner_layer": node.current_owner_layer,
            "expected_plan_id": node.plan_id,
            "expected_plan_version": node.plan_version,
            "expected_epoch": node.epoch,
            "expected_lease_expires_at_s": node.lease_expires_at_s,
        }
        values.update(changes.get(node.region_id, {}))
        actions.append(RegionResourceAction(**values))
    return RegionResourceRecommendation(
        snapshot_id=snapshot.snapshot_id,
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        seed=snapshot.seed,
        authority_digest=snapshot.authority_digest,
        created_at_s=snapshot.timestamp_s,
        policy_name="test-policy",
        policy_version="v1",
        source=RecommendationSource.LEARNED,
        confidence=confidence,
        actions=tuple(actions),
        transfers=transfers,
    )


@pytest.mark.parametrize("region_count", [3, 5, 8, 32, 200])
def test_variable_region_graph_and_rule_policy_do_not_assume_fixed_scale(
    region_count: int,
) -> None:
    snapshot = _snapshot(region_count)
    recommendation = RuleRegionResourcePolicy().recommend(snapshot)
    graph = snapshot_to_region_graph(snapshot)
    model = SharedRegionGraphActorCritic(hidden_dim=16, message_passing_steps=1)
    output = model(graph)

    assert recommendation.projected is True
    assert len(recommendation.actions) == region_count
    assert recommendation.total_quota_delta == 0
    assert graph.node_count == region_count
    assert graph.edge_count == 2 * (region_count - 1)
    assert output.node_mean.shape == (region_count, 5)
    assert output.edge_mean.shape == (2 * (region_count - 1), 1)
    assert torch.isfinite(output.value)


def test_snapshot_mapping_rejects_actor_truth_or_target_identity() -> None:
    payload = _snapshot().to_dict()
    payload["regions"][0]["actor_truth_id"] = "MSM_TargetActor_1"

    with pytest.raises(ValueError, match="truth or target identity"):
        RegionResourceSnapshot.from_dict(payload)


def test_projection_conserves_resources_and_protects_reserve_and_commit() -> None:
    snapshot = _snapshot(2)
    source = replace(
        snapshot.regions[1],
        available_resources=10,
        reserve_resources=2,
        committed_resources=3,
    )
    snapshot = replace(snapshot, regions=(snapshot.regions[0], source), authority_digest="")
    edge = snapshot.edges[0]
    raw = _raw_proposal(
        snapshot,
        (
            RegionTransferSuggestion(
                source_region_id=source.region_id,
                target_region_id=snapshot.regions[0].region_id,
                resource_count=9,
                edge_id=edge.edge_id,
                expected_transfer_time_s=edge.transfer_time_s,
            ),
        ),
    )

    projector = DeterministicResourceProjector()
    projected = projector.project(snapshot, raw)

    assert projected.total_quota_delta == 0
    assert projected.transfers[0].resource_count == 5
    source_action = next(
        action for action in projected.actions if action.region_id == source.region_id
    )
    assert source.available_resources + source_action.resource_quota_delta >= 5
    assert source_action.reserve_ratio >= 2 / 5
    assert "clipped_by_safety_projection" in " ".join(projected.projection_rejections)


@pytest.mark.parametrize(
    ("partitioned_edge", "communication_available"),
    [(0, True), (None, False)],
)
def test_projection_rejects_broken_or_partitioned_edges(
    partitioned_edge: int | None,
    communication_available: bool,
) -> None:
    snapshot = _snapshot(
        2,
        partitioned_edge=partitioned_edge,
        communication_available=communication_available,
    )
    edge = snapshot.edges[0]
    raw = _raw_proposal(
        snapshot,
        (
            RegionTransferSuggestion(
                source_region_id="region-001",
                target_region_id="region-000",
                resource_count=3,
                edge_id=edge.edge_id,
                expected_transfer_time_s=edge.transfer_time_s,
            ),
        ),
    )

    projector = DeterministicResourceProjector()
    projected = projector.project(snapshot, raw)
    advisory = projector.build_advisory_contract(snapshot, projected)
    consumption = projector.validate_for_consumption(
        advisory,
        snapshot,
        evaluated_at_s=snapshot.timestamp_s,
    )

    assert projected.transfers == ()
    assert projected.total_quota_delta == 0
    assert any(
        "edge_unavailable_or_partitioned" in reason
        for reason in projected.projection_rejections
    )
    assert not consumption.consumable
    assert any(
        "edge_unavailable_or_partitioned" in reason
        for reason in consumption.rejection_reasons
    )


@pytest.mark.parametrize(
    "owner_layers",
    [
        (RegionalAuthorityLayer.CENTER,) * 5,
        (
            RegionalAuthorityLayer.SECONDARY,
            RegionalAuthorityLayer.SECONDARY,
            RegionalAuthorityLayer.SECONDARY,
            RegionalAuthorityLayer.SECONDARY,
            RegionalAuthorityLayer.SECONDARY,
        ),
        (RegionalAuthorityLayer.DISTRIBUTED,) * 5,
    ],
)
def test_rule_projection_preserves_center_multi_secondary_and_distributed_owners(
    owner_layers: tuple[RegionalAuthorityLayer, ...],
) -> None:
    snapshot = _snapshot(5, owner_layers=owner_layers)
    recommendation = RuleRegionResourcePolicy().recommend(snapshot)

    assert recommendation.projected
    assert {
        action.expected_owner_layer for action in recommendation.actions
    } == set(owner_layers)
    assert [
        action.expected_owner_id for action in recommendation.actions
    ] == [node.current_owner_id for node in sorted(snapshot.regions, key=lambda item: item.region_id)]


@pytest.mark.parametrize("fence", ["stale_epoch", "expired_lease", "missing_ack"])
def test_epoch_lease_and_ack_fences_block_transfer(fence: str) -> None:
    snapshot = _snapshot(
        2,
        timestamp_s=20.0 if fence == "expired_lease" else 1.0,
        lease_expires_at_s=20.0,
        ack_complete=fence != "missing_ack",
    )
    edge = snapshot.edges[0]
    changes = (
        {"region-001": {"expected_epoch": snapshot.regions[1].epoch - 1}}
        if fence == "stale_epoch"
        else {}
    )
    raw = _raw_proposal(
        snapshot,
        (
            RegionTransferSuggestion(
                source_region_id="region-001",
                target_region_id="region-000",
                resource_count=3,
                edge_id=edge.edge_id,
                expected_transfer_time_s=edge.transfer_time_s,
            ),
        ),
        action_changes=changes,
    )

    projector = DeterministicResourceProjector()
    projected = projector.project(snapshot, raw)
    advisory = projector.build_advisory_contract(snapshot, projected)
    consumption = projector.validate_for_consumption(
        advisory,
        snapshot,
        evaluated_at_s=snapshot.timestamp_s,
    )

    assert projected.transfers == ()
    assert projected.total_quota_delta == 0
    assert any(action.hold for action in projected.actions)
    expected = {
        "stale_epoch": "authority_version_mismatch",
        "expired_lease": "authority_lease_expired",
        "missing_ack": "coalition_ack_incomplete",
    }[fence]
    assert any(expected in reason for action in projected.actions for reason in action.reasons)
    assert not consumption.consumable
    assert any(expected in reason for reason in consumption.rejection_reasons)


def test_fault_fence_blocks_all_resource_motion_for_the_region() -> None:
    snapshot = _snapshot(2)
    fenced_source = replace(snapshot.regions[1], fault_fenced=True)
    snapshot = replace(
        snapshot,
        regions=(snapshot.regions[0], fenced_source),
        authority_digest="",
    )
    edge = snapshot.edges[0]
    raw = _raw_proposal(
        snapshot,
        (
            RegionTransferSuggestion(
                source_region_id="region-001",
                target_region_id="region-000",
                resource_count=3,
                edge_id=edge.edge_id,
                expected_transfer_time_s=edge.transfer_time_s,
            ),
        ),
    )

    projected = DeterministicResourceProjector().project(snapshot, raw)

    assert projected.transfers == ()
    source_action = next(
        action for action in projected.actions if action.region_id == "region-001"
    )
    assert source_action.hold
    assert "fault_fence_active" in source_action.reasons


def test_recommendation_is_region_aggregate_only() -> None:
    recommendation = RuleRegionResourcePolicy().recommend(_snapshot())
    serialized = json.dumps(recommendation.to_dict(), sort_keys=True)

    assert '"target_id"' not in serialized
    assert "global_track_id" not in serialized
    assert "actor_truth_id" not in serialized
    assert "resource-target" not in serialized


def test_reward_contains_all_required_penalties() -> None:
    reward = compute_region_resource_reward(
        RegionResourceRewardMetrics(
            high_threat_backlog=1.0,
            transfer_time_s=1.0,
            communication_load=1.0,
            reserve_shortfall=1.0,
            assignment_conflicts=1.0,
            degradation_failures=1.0,
            plan_jitter=1.0,
        )
    )

    assert reward == pytest.approx(-(2.0 + 0.2 + 0.1 + 2.0 + 3.0 + 5.0 + 0.5))


def test_scenario_seed_split_keeps_complete_groups_together() -> None:
    records = [
        {"scenario_id": f"S-{scenario}", "seed": seed, "step": step}
        for scenario in range(3)
        for seed in range(20)
        for step in range(3)
    ]
    split = split_scenario_seed_groups(records, split_seed=11)
    groups = [set(split.train_groups), set(split.validation_groups), set(split.test_groups)]

    assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
    seed_sets = [set(split.train_seeds), set(split.validation_seeds), set(split.test_seeds)]
    assert not (
        seed_sets[0] & seed_sets[1]
        or seed_sets[0] & seed_sets[2]
        or seed_sets[1] & seed_sets[2]
    )
    assert split.unique_seed_count == 20
    assert all(
        len(
            {
                bucket_name
                for bucket_name, bucket_seeds in (
                    ("train", split.train_seeds),
                    ("validation", split.validation_seeds),
                    ("test", split.test_seeds),
                )
                if seed in bucket_seeds
            }
        )
        == 1
        for seed in range(20)
    )
    assert sum(len(item) for item in (split.train, split.validation, split.test)) == len(records)
    for bucket, bucket_groups in (
        (split.train, groups[0]),
        (split.validation, groups[1]),
        (split.test, groups[2]),
    ):
        assert all((item["scenario_id"], item["seed"]) in bucket_groups for item in bucket)


def test_behavior_cloning_loss_and_update_are_finite() -> None:
    snapshot = _snapshot(5)
    graph = snapshot_to_region_graph(snapshot)
    recommendation = RuleRegionResourcePolicy().recommend(snapshot)
    target = recommendation_to_policy_target(snapshot, graph, recommendation)
    model = SharedRegionGraphActorCritic(hidden_dim=16, message_passing_steps=1)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    before = behavior_cloning_loss(model, graph, target)
    updated = behavior_cloning_step(
        model,
        optimizer,
        (BehaviorCloningSample(graph=graph, target=target),),
    )

    assert torch.isfinite(before)
    assert isfinite(updated)
    assert all(torch.isfinite(parameter).all() for parameter in model.parameters())


def test_native_clipped_ppo_update_is_finite_across_variable_graphs() -> None:
    torch.manual_seed(7)
    model = SharedRegionGraphActorCritic(hidden_dim=16, message_passing_steps=1)
    transitions: list[GraphPPOTransition] = []
    for count, advantage in ((3, 1.0), (8, -0.5)):
        graph = snapshot_to_region_graph(_snapshot(count))
        action = sample_graph_policy_action(model, graph)
        transitions.append(
            GraphPPOTransition(
                graph=graph,
                action=action,
                advantage=advantage,
                return_value=action.value + advantage,
            )
        )
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    metrics = native_clipped_ppo_update(model, optimizer, transitions, epochs=2)

    assert metrics.update_finite
    assert all(
        isfinite(value)
        for value in (
            metrics.total_loss,
            metrics.policy_loss,
            metrics.value_loss,
            metrics.entropy,
            metrics.approximate_kl,
            metrics.clip_fraction,
        )
    )


def _bundle(tmp_path: Path, snapshot: RegionResourceSnapshot) -> Path:
    graph = snapshot_to_region_graph(snapshot)
    model = SharedRegionGraphActorCritic(hidden_dim=16, message_passing_steps=1)
    bundle_dir = tmp_path / "bundle"
    save_region_resource_model_bundle(
        model,
        bundle_dir,
        model_version="test-v1",
        training_graphs=(graph,),
        training_groups=((snapshot.scenario_id, snapshot.seed),),
        created_at_utc="2026-07-20T00:00:00Z",
    )
    return bundle_dir


def test_model_bundle_manifest_state_dict_and_sha_round_trip(tmp_path: Path) -> None:
    snapshot = _snapshot(3)
    bundle_dir = _bundle(tmp_path, snapshot)

    loaded = load_region_resource_model_bundle(
        bundle_dir,
        expected_model_version="test-v1",
    )

    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["state_dict_sha256"] == loaded.manifest.state_dict_sha256
    assert len(manifest["state_dict_sha256"]) == 64
    assert loaded.manifest.training_groups == ((snapshot.scenario_id, snapshot.seed),)


@pytest.mark.parametrize("failure", ["version", "sha"])
def test_bundle_version_or_sha_mismatch_falls_back_to_rule(
    tmp_path: Path, failure: str
) -> None:
    snapshot = _snapshot(3)
    bundle_dir = _bundle(tmp_path, snapshot)
    kwargs: dict[str, object] = {}
    if failure == "version":
        kwargs["expected_model_version"] = "wrong-version"
    else:
        state_path = bundle_dir / "state_dict.pt"
        state_path.write_bytes(state_path.read_bytes() + b"tamper")
    advisor = RegionResourceAdvisor.from_bundle(
        bundle_dir,
        config=RegionResourceAdvisorConfig(mode=AdvisorMode.SHADOW),
        **kwargs,
    )

    result = advisor.advise(snapshot)

    assert result.fallback_used
    assert result.recommendation is not None
    assert result.recommendation.source == RecommendationSource.RULE
    assert result.fallback_reason is not None
    assert "bundle_validation_failed" in result.fallback_reason


def test_ood_snapshot_falls_back_to_rule(tmp_path: Path) -> None:
    training_snapshot = _snapshot(3)
    bundle_dir = _bundle(tmp_path, training_snapshot)
    advisor = RegionResourceAdvisor.from_bundle(
        bundle_dir,
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            minimum_confidence=0.0,
            ood_margin=0.0,
        ),
    )
    ood_snapshot = _snapshot(3, d1_uncertainty=1e9)

    result = advisor.advise(ood_snapshot)

    assert result.fallback_used
    assert result.fallback_reason == "feature_ood"
    assert result.recommendation is not None
    assert result.recommendation.source == RecommendationSource.RULE


class _SlowPolicy:
    def recommend_raw(self, snapshot: RegionResourceSnapshot) -> RegionResourceRecommendation:
        sleep(0.002)
        return _raw_proposal(snapshot, ())


class _NonFinitePolicy:
    def recommend_raw(self, snapshot: RegionResourceSnapshot) -> RegionResourceRecommendation:
        raise NonFinitePolicyOutput("non-finite")


class _LowConfidencePolicy:
    def recommend_raw(self, snapshot: RegionResourceSnapshot) -> RegionResourceRecommendation:
        return _raw_proposal(snapshot, (), confidence=0.1)


@pytest.mark.parametrize(
    ("policy", "expected_reason"),
    [
        (_SlowPolicy(), "learning_timeout"),
        (_NonFinitePolicy(), "learning_output_non_finite"),
        (_LowConfidencePolicy(), "learning_confidence_below_threshold"),
    ],
)
def test_timeout_and_non_finite_learning_fall_back_to_rule(
    policy: object,
    expected_reason: str,
) -> None:
    timeout = 0.0 if isinstance(policy, _SlowPolicy) else 1.0
    advisor = RegionResourceAdvisor(
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            inference_timeout_s=timeout,
            minimum_confidence=0.6 if isinstance(policy, _LowConfidencePolicy) else 0.0,
        ),
        learned_policy=policy,
    )

    result = advisor.advise(_snapshot())

    assert result.fallback_used
    assert result.fallback_reason == expected_reason
    assert result.recommendation is not None
    assert result.recommendation.source == RecommendationSource.RULE


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
    regions = tuple(
        RegionalRegionDecision(
            region_id=node.region_id,
            selected_layer=node.current_owner_layer,
            action=RegionalAction.CONTINUE_CENTER,
            reason="fixture",
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
    )
    return RegionalFailoverDecision(
        timestamp_s=snapshot.timestamp_s,
        scenario=scenario,
        region_decisions=regions,
    )


def test_formal_committed_coalition_members_are_protected_from_transfer() -> None:
    snapshot = _snapshot(2)
    formal = _formal_decision(snapshot)
    committed = CoalitionCommitSummary(
        task_id="aggregate-only-in-formal-verdict",
        global_track_id="G-formal-only",
        commit_required=True,
        state="committed",
        coordinator_id="CENTER",
        required_member_ids=tuple(f"INT-{index}" for index in range(8)),
        acked_member_ids=tuple(f"INT-{index}" for index in range(8)),
        missing_member_ids=(),
        lease_expires_at_s=20.0,
        atomic_committed=True,
        execution_authorized=True,
        reason="all_members_acked",
    )
    source_decision = replace(formal.region_decisions[1], coalition_commits=(committed,))
    formal = replace(
        formal,
        region_decisions=(formal.region_decisions[0], source_decision),
    )
    edge = snapshot.edges[0]
    raw = _raw_proposal(
        snapshot,
        (
            RegionTransferSuggestion(
                source_region_id="region-001",
                target_region_id="region-000",
                resource_count=5,
                edge_id=edge.edge_id,
                expected_transfer_time_s=edge.transfer_time_s,
            ),
        ),
    )

    projected = DeterministicResourceProjector().project(
        snapshot,
        raw,
        formal_decision=formal,
    )

    assert projected.transfers[0].resource_count == 1
    assert snapshot.regions[1].available_resources - 1 >= 8 + 1


def test_default_is_disabled_and_shadow_does_not_change_formal_d4_verdict() -> None:
    snapshot = _snapshot(3)
    formal = _formal_decision(snapshot)
    disabled = RegionResourceAdvisor().advise(snapshot, formal_decision=formal)
    shadow = RegionResourceAdvisor(
        config=RegionResourceAdvisorConfig(mode=AdvisorMode.SHADOW)
    ).advise(snapshot, formal_decision=formal)

    assert disabled.effective_mode == AdvisorMode.DISABLED
    assert disabled.recommendation is None
    assert shadow.effective_mode == AdvisorMode.SHADOW
    assert shadow.formal_decision is formal
    assert shadow.formal_decision_unchanged
    assert shadow.formal_decision_digest_before == shadow.formal_decision_digest_after


def test_assist_requires_at_least_twenty_unseen_seeds(tmp_path: Path) -> None:
    snapshot = _snapshot(3)
    bundle_dir = _bundle(tmp_path, snapshot)
    advisor = RegionResourceAdvisor.from_bundle(
        bundle_dir,
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.ASSIST,
            minimum_confidence=0.0,
            ood_margin=0.0,
            inference_timeout_s=10.0,
        ),
    )

    insufficient = advisor.advise(snapshot, unseen_seed_count=19)
    sufficient = advisor.advise(snapshot, unseen_seed_count=20)

    assert not insufficient.assist_eligible
    assert insufficient.effective_mode == AdvisorMode.SHADOW
    assert sufficient.assist_eligible
    assert sufficient.effective_mode == AdvisorMode.ASSIST


def _shadow_records(count: int, *, candidate: bool) -> tuple[ShadowEpisodeMetrics, ...]:
    return tuple(
        ShadowEpisodeMetrics(
            scenario_id="shadow-scenario",
            seed=seed,
            high_threat_backlog=8.0 if not candidate else 7.0,
            transfer_time_s=10.0 if not candidate else 9.0,
            plan_churn=3.0 if not candidate else 2.0,
            communication_load=5.0 if not candidate else 4.0,
            fail_closed_count=1.0 if not candidate else 0.0,
            safety_violation_count=0.0,
            latency_ms=float(seed + 1),
        )
        for seed in range(count)
    )


def test_shadow_paired_evaluator_reports_required_metrics_and_seed_gate() -> None:
    evaluator = ShadowPairedEvaluator(minimum_unseen_seeds=20)
    insufficient = evaluator.evaluate(
        _shadow_records(19, candidate=False),
        _shadow_records(19, candidate=True),
    )
    sufficient = evaluator.evaluate(
        _shadow_records(20, candidate=False),
        _shadow_records(20, candidate=True),
    )

    assert not insufficient.assist_recommended
    assert sufficient.assist_recommended
    assert sufficient.backlog.mean_delta == -1.0
    assert sufficient.transfer.mean_delta == -1.0
    assert sufficient.churn.mean_delta == -1.0
    assert sufficient.communication.mean_delta == -1.0
    assert sufficient.fail_closed.mean_delta == -1.0
    assert sufficient.safety_violations.candidate_mean == 0.0
    assert sufficient.latency_p50_ms == pytest.approx(10.5)
    assert sufficient.latency_p95_ms == pytest.approx(19.05)


def test_shadow_evaluator_counts_unseen_numeric_seeds_across_scenarios() -> None:
    baseline = tuple(
        replace(record, scenario_id=scenario_id)
        for scenario_id in ("scale-2", "scale-5")
        for record in _shadow_records(3, candidate=False)
    )
    candidate = tuple(
        replace(record, scenario_id=scenario_id)
        for scenario_id in ("scale-2", "scale-5")
        for record in _shadow_records(3, candidate=True)
    )

    report = ShadowPairedEvaluator(minimum_unseen_seeds=2).evaluate(
        baseline,
        candidate,
        training_groups=(("training-scale", 0),),
    )

    assert report.pair_count == 6
    assert report.unseen_seed_count == 2
    assert report.assist_recommended


def test_cli_demo_supports_32_regions_and_remains_shadow(tmp_path: Path) -> None:
    output = tmp_path / "demo.json"

    exit_code = resource_cli_main(
        (
            "demo",
            "--region-count",
            "32",
            "--mode",
            "shadow",
            "--output",
            str(output),
        )
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    result = payload["advisory_result"]
    assert exit_code == 0
    assert payload["snapshot"]["schema"] == "d4-region-resource-snapshot-v1"
    assert len(result["recommendation"]["actions"]) == 32
    assert result["advisory_contract"]["schema"] == "d4-region-resource-advisory-v1"
    assert result["advisory_contract"]["projected"] is True
    assert result["effective_mode"] == "shadow"
    assert result["formal_decision_unchanged"] is True


def test_advisory_contract_contains_versioned_safety_and_resource_proofs() -> None:
    snapshot = _snapshot(3)
    projector = DeterministicResourceProjector()
    recommendation = RuleRegionResourcePolicy().recommend(snapshot)

    advisory = projector.build_advisory_contract(snapshot, recommendation)
    payload = json.loads(json.dumps(advisory.to_dict(), sort_keys=True))
    restored = RegionResourceAdvisoryContract.from_dict(payload)
    tampered = dict(payload)
    tampered["policy_version"] = "tampered"
    with pytest.raises(ValueError, match="advisory_id"):
        RegionResourceAdvisoryContract.from_dict(tampered)
    view = projector.validate_for_consumption(
        restored,
        snapshot,
        evaluated_at_s=1.5,
    )

    assert advisory.schema == "d4-region-resource-advisory-v1"
    assert advisory.advisory_id.startswith("d4-rr-advisory-")
    assert restored.advisory_id == advisory.advisory_id
    assert advisory.projected is True
    assert advisory.snapshot_id == snapshot.snapshot_id
    assert advisory.snapshot_version == snapshot.snapshot_version
    assert advisory.authority_digest == snapshot.authority_digest
    assert advisory.created_at_s == snapshot.timestamp_s
    assert advisory.valid_from_s == 1.0
    assert advisory.valid_until_s == 2.0
    assert advisory.source_plan_versions == (("regional-plan", 3),)
    assert advisory.policy_name == RuleRegionResourcePolicy.policy_name
    assert advisory.policy_version == RuleRegionResourcePolicy.policy_version
    assert advisory.source == RecommendationSource.RULE
    assert advisory.model_sha256 is None
    assert advisory.total_quota_delta == 0
    assert advisory.total_resources_before == advisory.total_resources_after
    assert not advisory.publication_rejections
    assert advisory.transfers
    assert all(
        region.resources_after
        >= region.protected_reserve_resources
        + region.protected_committed_resources
        for region in advisory.regions
    )
    recommendation_by_region = {
        action.region_id: action for action in recommendation.actions
    }
    assert all(
        region.hold == recommendation_by_region[region.region_id].hold
        and region.request_replan
        == recommendation_by_region[region.region_id].request_replan
        for region in advisory.regions
    )
    assert all(
        region.source_version.snapshot_id == snapshot.snapshot_id
        and region.source_version.plan_id == "regional-plan"
        and region.source_version.plan_version == 3
        and region.source_version.epoch == 2
        and region.source_version.lease_expires_at_s == 20.0
        for region in advisory.regions
    )
    assert all(
        transfer.resource_count <= transfer.edge_capacity_resources
        and transfer.communication_available
        and transfer.maneuver_available
        and not transfer.partitioned
        and transfer.source_version.snapshot_version == snapshot.snapshot_version
        and transfer.target_version.snapshot_version == snapshot.snapshot_version
        for transfer in advisory.transfers
    )
    assert view.consumable
    serialized = json.dumps(view.to_dict(), sort_keys=True)
    assert "global_track_id" not in serialized
    assert "actor_truth_id" not in serialized
    assert '"target_id"' not in serialized


def test_next_cycle_gate_rejects_repeated_advisory_consumption() -> None:
    snapshot = _snapshot(3)
    policy = RuleRegionResourcePolicy()
    advisory = policy.recommend_contract(snapshot)
    gate = RegionResourceAdvisoryGate(policy.projector)

    first = gate.consume(advisory, snapshot, evaluated_at_s=1.25)
    repeated = gate.consume(advisory, snapshot, evaluated_at_s=1.50)

    assert first.consumable
    assert advisory.advisory_id in gate.consumed_advisory_ids
    assert not repeated.consumable
    assert "advisory_already_consumed" in repeated.rejection_reasons


def test_advisory_expiry_is_strict_at_valid_until_boundary() -> None:
    snapshot = _snapshot(3)
    policy = RuleRegionResourcePolicy()
    advisory = policy.recommend_contract(snapshot)

    expired = policy.projector.validate_for_consumption(
        advisory,
        snapshot,
        evaluated_at_s=advisory.valid_until_s,
    )

    assert not expired.consumable
    assert "advisory_expired" in expired.rejection_reasons


@pytest.mark.parametrize(
    ("stale_kind", "expected_reason"),
    [
        ("snapshot", "source_snapshot_id_stale"),
        ("plan", "plan_version_stale"),
        ("epoch", "epoch_stale"),
    ],
)
def test_consumption_rejects_stale_snapshot_plan_or_epoch(
    stale_kind: str,
    expected_reason: str,
) -> None:
    snapshot = _snapshot(3)
    policy = RuleRegionResourcePolicy()
    advisory = policy.recommend_contract(snapshot)
    current = snapshot
    if stale_kind == "snapshot":
        current = replace(snapshot, snapshot_id="snapshot-next-cycle")
    else:
        first = snapshot.regions[0]
        first = replace(
            first,
            plan_version=first.plan_version + (stale_kind == "plan"),
            epoch=first.epoch + (stale_kind == "epoch"),
        )
        current = replace(
            snapshot,
            regions=(first, *snapshot.regions[1:]),
            authority_digest="",
        )

    view = policy.projector.validate_for_consumption(
        advisory,
        current,
        evaluated_at_s=1.25,
    )

    assert not view.consumable
    assert any(expected_reason in reason for reason in view.rejection_reasons)


@pytest.mark.parametrize(
    ("fence", "expected_reason"),
    [
        ("ack", "coalition_ack_incomplete"),
        ("fault", "fault_fence_active"),
    ],
)
def test_consumption_rechecks_ack_and_fault_fence(
    fence: str,
    expected_reason: str,
) -> None:
    snapshot = _snapshot(3)
    policy = RuleRegionResourcePolicy()
    advisory = policy.recommend_contract(snapshot)
    first = replace(
        snapshot.regions[0],
        coalition_ack_complete=fence != "ack",
        fault_fenced=fence == "fault",
    )
    current = replace(
        snapshot,
        regions=(first, *snapshot.regions[1:]),
        authority_digest="",
    )

    view = policy.projector.validate_for_consumption(
        advisory,
        current,
        evaluated_at_s=1.25,
    )

    assert not view.consumable
    assert any(expected_reason in reason for reason in view.rejection_reasons)


def test_non_projected_non_conserving_recommendation_is_not_consumable() -> None:
    snapshot = _snapshot(3)
    projector = DeterministicResourceProjector()
    raw = _raw_proposal(snapshot, ())
    changed_actions = (
        replace(raw.actions[0], resource_quota_delta=1),
        *raw.actions[1:],
    )
    raw = replace(raw, actions=changed_actions, projected=False)

    advisory = projector.build_advisory_contract(snapshot, raw)
    view = projector.validate_for_consumption(
        advisory,
        snapshot,
        evaluated_at_s=1.25,
    )

    assert not view.consumable
    assert "recommendation_not_projected" in view.rejection_reasons
    assert "total_resource_quota_not_conserved" in view.rejection_reasons


@pytest.mark.parametrize("invalid_transfer", ["unknown", "non_adjacent"])
def test_unknown_or_non_adjacent_transfer_cannot_become_consumable(
    invalid_transfer: str,
) -> None:
    snapshot = _snapshot(3)
    projector = DeterministicResourceProjector()
    if invalid_transfer == "unknown":
        transfer = RegionTransferSuggestion(
            source_region_id="region-001",
            target_region_id="unknown-region",
            resource_count=1,
            edge_id="unknown-edge",
            expected_transfer_time_s=1.0,
        )
        raw = replace(_raw_proposal(snapshot, ()), transfers=(transfer,))
    else:
        transfer = RegionTransferSuggestion(
            source_region_id="region-002",
            target_region_id="region-000",
            resource_count=1,
            edge_id="edge-000",
            expected_transfer_time_s=20.0,
        )
        raw = _raw_proposal(snapshot, (transfer,))

    projected = projector.project(snapshot, raw)
    advisory = projector.build_advisory_contract(snapshot, projected)
    view = projector.validate_for_consumption(
        advisory,
        snapshot,
        evaluated_at_s=1.25,
    )

    assert projected.projected
    assert projected.transfers == ()
    assert not view.consumable
    assert any(
        "unknown_region" in reason or "non_adjacent_edge" in reason
        for reason in view.rejection_reasons
    )


@pytest.mark.parametrize("edge_failure", ["partition", "communication"])
def test_partitioned_or_unavailable_edge_advice_is_not_consumable(
    edge_failure: str,
) -> None:
    snapshot = _snapshot(
        2,
        partitioned_edge=0 if edge_failure == "partition" else None,
        communication_available=edge_failure != "communication",
    )
    edge = snapshot.edges[0]
    transfer = RegionTransferSuggestion(
        source_region_id="region-001",
        target_region_id="region-000",
        resource_count=1,
        edge_id=edge.edge_id,
        expected_transfer_time_s=edge.transfer_time_s,
    )
    projector = DeterministicResourceProjector()
    projected = projector.project(snapshot, _raw_proposal(snapshot, (transfer,)))
    advisory = projector.build_advisory_contract(snapshot, projected)
    view = projector.validate_for_consumption(
        advisory,
        snapshot,
        evaluated_at_s=1.25,
    )

    assert projected.transfers == ()
    assert not view.consumable
    assert any(
        "edge_unavailable_or_partitioned" in reason
        for reason in view.rejection_reasons
    )


def test_advisory_proof_preserves_k_greater_than_one_committed_members() -> None:
    snapshot = _snapshot(2)
    formal = _formal_decision(snapshot)
    committed = CoalitionCommitSummary(
        task_id="formal-aggregate-only",
        global_track_id="formal-scope-only",
        commit_required=True,
        state="committed",
        coordinator_id="CENTER",
        required_member_ids=tuple(f"INT-{index}" for index in range(8)),
        acked_member_ids=tuple(f"INT-{index}" for index in range(8)),
        missing_member_ids=(),
        lease_expires_at_s=20.0,
        atomic_committed=True,
        execution_authorized=True,
        reason="all_members_acked",
    )
    source_decision = replace(formal.region_decisions[1], coalition_commits=(committed,))
    formal = replace(
        formal,
        region_decisions=(formal.region_decisions[0], source_decision),
    )
    edge = snapshot.edges[0]
    transfer = RegionTransferSuggestion(
        source_region_id="region-001",
        target_region_id="region-000",
        resource_count=5,
        edge_id=edge.edge_id,
        expected_transfer_time_s=edge.transfer_time_s,
    )
    projector = DeterministicResourceProjector()
    raw = replace(
        _raw_proposal(snapshot, (transfer,)),
        model_sha256="b" * 64,
    )
    projected = projector.project(
        snapshot,
        raw,
        formal_decision=formal,
    )
    advisory = projector.build_advisory_contract(
        snapshot,
        projected,
        formal_decision=formal,
    )
    view = projector.validate_for_consumption(
        advisory,
        snapshot,
        evaluated_at_s=1.25,
        formal_decision=formal,
    )
    source = next(
        region for region in advisory.regions if region.region_id == "region-001"
    )

    assert projected.transfers[0].resource_count == 1
    assert source.protected_committed_resources == 8
    assert source.protected_reserve_resources == 1
    assert source.resources_after == 9
    assert view.consumable
    serialized = json.dumps(advisory.to_dict(), sort_keys=True)
    assert "global_track_id" not in serialized
    assert "formal-scope-only" not in serialized


class _SafeLearnedPolicy:
    def recommend_raw(
        self,
        snapshot: RegionResourceSnapshot,
    ) -> RegionResourceRecommendation:
        return replace(
            _raw_proposal(snapshot, ()),
            model_sha256="a" * 64,
        )


def test_rule_and_learning_advisor_share_the_same_projector_gate() -> None:
    snapshot = _snapshot(3)
    learned = RegionResourceAdvisor(
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.SHADOW,
            minimum_confidence=0.0,
        ),
        learned_policy=_SafeLearnedPolicy(),
    )
    learned_result = learned.advise(snapshot)
    fallback = RegionResourceAdvisor(
        config=RegionResourceAdvisorConfig(mode=AdvisorMode.SHADOW)
    )
    fallback_result = fallback.advise(snapshot)

    assert learned.rule_policy.projector is learned.projector
    assert learned_result.recommendation is not None
    assert learned_result.recommendation.projected
    assert learned_result.recommendation.source == RecommendationSource.LEARNED
    assert learned_result.advisory_contract is not None
    assert not learned_result.advisory_contract.publication_rejections
    assert learned_result.advisory_contract.model_sha256 == "a" * 64
    assert learned_result.advisory_contract.source == RecommendationSource.LEARNED
    assert fallback.rule_policy.projector is fallback.projector
    assert fallback_result.recommendation is not None
    assert fallback_result.recommendation.projected
    assert fallback_result.recommendation.source == RecommendationSource.RULE
    assert fallback_result.advisory_contract is not None
