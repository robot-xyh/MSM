from __future__ import annotations

from pathlib import Path

import pytest

from d4_distributed_fallback.region_resource import (
    RecommendationSource,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RegionTransferSuggestion,
    RuleRegionResourcePolicy,
)
from d4_distributed_fallback.region_resource_v8_dataset_writer import (
    V8CleanSourceMetadata,
    V8TrainDatasetWriter,
)
from d4_distributed_fallback.region_resource_v8_development_contract import (
    V8RequestScheduleEntry,
    V8TransferClass,
    expected_v8_directed_edges,
    load_v8_frozen_request,
)
from d4_distributed_fallback.region_resource_v8_runtime_evidence import (
    RegionResourceV8RuntimeEvidenceError,
    V8AnonymousCandidateEvidence,
    V8RuntimeEpisodeEvidenceBuilder,
    V8RuntimeFrameEvidence,
)


_MODULE_ROOT = Path(__file__).resolve().parents[1]
_REQUEST_ROOT = (
    _MODULE_ROOT
    / "reports"
    / "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801"
)
_REQUEST_PATH = _REQUEST_ROOT / "v8_development_data_request.json"
_REGISTRY_PATH = _REQUEST_ROOT / "v8_development_seed_registry.json"


def _recipe(
    *,
    seed: int,
    target_class: V8TransferClass,
    count: int = 1,
    communication_condition: str = "nominal",
) -> V8RequestScheduleEntry:
    hard = target_class == V8TransferClass.HARD_NO_TRANSFER
    return V8RequestScheduleEntry(
        seed=seed,
        split="train",
        topology_id="directed_ring_8",
        region_count=8,
        supply_demand_condition="source_surplus_target_deficit",
        communication_condition=communication_condition,
        requested_target_class=target_class,
        requested_transfer_resource_count=0 if hard else count,
        hard_negative_candidate_resource_count=count if hard else 0,
        replicate=count - 1,
    )


def _snapshot(
    *,
    seed: int,
    source_index: int,
    target_index: int,
    resource_count: int,
    executable: bool,
    timestamp_s: float = 0.0,
    partition_pair: tuple[int, int] | None = None,
    scenario_id: str = "actual-regional-runtime",
) -> RegionResourceSnapshot:
    nodes: list[RegionResourceNode] = []
    surplus_index = next(
        index
        for index in range(8)
        if index not in {source_index, target_index}
        and index not in {(target_index - 1) % 8, (target_index + 1) % 8}
    )
    for index in range(8):
        available = 2
        reserve = 1
        demand = 1.0
        if index == source_index:
            available = resource_count + 3 if executable else 1
        elif index == target_index:
            available = 1
            demand = float(resource_count)
        elif not executable and index == surplus_index:
            available = 3
        nodes.append(
            RegionResourceNode(
                region_id=f"sector-{index}",
                target_demand=demand,
                high_threat_backlog=0.0,
                d1_uncertainty=0.0,
                d2_uncertainty=0.0,
                d5_visibility=1.0,
                d5_consistency=1.0,
                available_resources=available,
                reserve_resources=reserve,
                secondary_coverage=1.0,
                secondary_readiness=1.0,
                communication_capacity=100.0,
                communication_latency_s=0.01,
                packet_loss_rate=0.0,
                current_owner_id="Center_1",
                current_owner_layer="center",
                plan_id="plan-actual-v8",
                plan_version=1,
                epoch=1,
                lease_expires_at_s=100.0,
            )
        )
    edges: list[RegionResourceEdge] = []
    for source in range(8):
        target = (source + 1) % 8
        pair = {source, target}
        partitioned = bool(
            partition_pair is not None
            and pair == {partition_pair[0], partition_pair[1]}
        )
        edges.append(
            RegionResourceEdge(
                source_region_id=f"sector-{source}",
                target_region_id=f"sector-{target}",
                transferable_resources=3,
                distance_m=100.0,
                transfer_time_s=2.0,
                bandwidth_mbps=20.0,
                communication_available=True,
                maneuver_available=True,
                partitioned=partitioned,
                bidirectional=True,
            )
        )
    return RegionResourceSnapshot(
        snapshot_id=f"snapshot-{seed}-{timestamp_s}",
        scenario_id=scenario_id,
        scenario_version="actual-v1",
        seed=seed,
        timestamp_s=timestamp_s,
        regions=tuple(nodes),
        edges=tuple(edges),
    )


def _actual_evidence(
    snapshot: RegionResourceSnapshot,
    *,
    source_index: int,
    target_index: int,
    resource_count: int,
    policy: RuleRegionResourcePolicy,
    arrival_delay_s: float = 0.1,
) -> V8RuntimeFrameEvidence:
    r0 = policy.recommend(snapshot)
    edge = next(
        item
        for item in snapshot.edges
        if item.permits(f"sector-{source_index}", f"sector-{target_index}")
    )
    transfer = RegionTransferSuggestion(
        source_region_id=f"sector-{source_index}",
        target_region_id=f"sector-{target_index}",
        resource_count=resource_count,
        edge_id=edge.edge_id,
        expected_transfer_time_s=edge.transfer_time_s,
        reasons=("anonymous_actual_candidate",),
    )
    raw = RegionResourceRecommendation(
        snapshot_id=snapshot.snapshot_id,
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        seed=snapshot.seed,
        authority_digest=snapshot.authority_digest,
        created_at_s=snapshot.timestamp_s,
        policy_name="anonymous-regional-actor",
        policy_version="actual-v1",
        source=RecommendationSource.LEARNED,
        confidence=0.9,
        actions=r0.actions,
        transfers=(transfer,),
        projected=False,
    )
    projected = policy.projector.project(snapshot, raw)
    return V8RuntimeFrameEvidence(
        snapshot=snapshot,
        r0_recommendation=r0,
        raw_actor_proposal=raw,
        projected_actor_recommendation=projected,
        anonymous_candidates=(
            V8AnonymousCandidateEvidence(
                transfer=transfer,
                activation_score=0.9,
            ),
        ),
        arrival_timestamp=snapshot.timestamp_s + arrival_delay_s,
    )


@pytest.mark.parametrize(
    ("target_class", "seed", "source_index", "target_index", "direction"),
    (
        (V8TransferClass.SAFE_FORWARD, 28100, 0, 1, "forward"),
        (V8TransferClass.SAFE_REVERSE, 28103, 1, 0, "reverse"),
    ),
)
def test_actual_safe_forward_and_reverse_are_built_from_bidirectional_ring(
    target_class: V8TransferClass,
    seed: int,
    source_index: int,
    target_index: int,
    direction: str,
) -> None:
    policy = RuleRegionResourcePolicy()
    snapshot = _snapshot(
        seed=seed,
        source_index=source_index,
        target_index=target_index,
        resource_count=1,
        executable=True,
    )
    builder = V8RuntimeEpisodeEvidenceBuilder(
        episode_id=f"actual-{direction}-{seed}",
        recipe=_recipe(seed=seed, target_class=target_class),
        rule_policy=policy,
    )
    frame, label = builder.stage_frame(
        frame_index=0,
        evidence=_actual_evidence(
            snapshot,
            source_index=source_index,
            target_index=target_index,
            resource_count=1,
            policy=policy,
        ),
    )
    episode = builder.finalize()

    assert len(frame.directed_edges) == len(
        expected_v8_directed_edges("directed_ring_8")
    ) == 16
    assert {(0, 1), (1, 0)}.issubset(
        {item.endpoint_key for item in frame.directed_edges}
    )
    assert len(frame.projected_transfers) == 1
    assert label.target_class == target_class
    assert episode.frames == (frame,)


def test_actual_hard_negative_keeps_projector_and_source_surplus_reason() -> None:
    policy = RuleRegionResourcePolicy()
    snapshot = _snapshot(
        seed=28106,
        source_index=0,
        target_index=1,
        resource_count=1,
        executable=False,
    )
    builder = V8RuntimeEpisodeEvidenceBuilder(
        episode_id="actual-hard-negative-28106",
        recipe=_recipe(
            seed=28106,
            target_class=V8TransferClass.HARD_NO_TRANSFER,
        ),
        rule_policy=policy,
    )
    frame, label = builder.stage_frame(
        frame_index=0,
        evidence=_actual_evidence(
            snapshot,
            source_index=0,
            target_index=1,
            resource_count=1,
            policy=policy,
        ),
    )
    builder.finalize()

    assert frame.projected_transfers == ()
    assert "insufficient_source_surplus" in frame.projection_rejection_reasons
    assert label.hard_negative_reasons == ("insufficient_source_surplus",)


def test_partition_blocks_actual_candidate_and_recovery_allows_it() -> None:
    policy = RuleRegionResourcePolicy()
    blocked_snapshot = _snapshot(
        seed=28106,
        source_index=0,
        target_index=1,
        resource_count=1,
        executable=True,
        partition_pair=(0, 1),
    )
    blocked_builder = V8RuntimeEpisodeEvidenceBuilder(
        episode_id="partition-blocked",
        recipe=_recipe(
            seed=28106,
            target_class=V8TransferClass.HARD_NO_TRANSFER,
            communication_condition="partition_then_recovery",
        ),
        rule_policy=policy,
    )
    blocked, blocked_label = blocked_builder.stage_frame(
        frame_index=0,
        evidence=_actual_evidence(
            blocked_snapshot,
            source_index=0,
            target_index=1,
            resource_count=1,
            policy=policy,
        ),
    )

    recovered_snapshot = _snapshot(
        seed=28100,
        source_index=0,
        target_index=1,
        resource_count=1,
        executable=True,
    )
    recovered_builder = V8RuntimeEpisodeEvidenceBuilder(
        episode_id="partition-recovered",
        recipe=_recipe(
            seed=28100,
            target_class=V8TransferClass.SAFE_FORWARD,
        ),
        rule_policy=policy,
    )
    recovered, _ = recovered_builder.stage_frame(
        frame_index=0,
        evidence=_actual_evidence(
            recovered_snapshot,
            source_index=0,
            target_index=1,
            resource_count=1,
            policy=policy,
        ),
    )
    recovered_builder.finalize()

    assert blocked.projected_transfers == ()
    assert blocked.projection_rejection_reasons == ("communication_partitioned",)
    assert blocked_label.hard_negative_reasons == (
        "communication_partition_or_expired_evidence",
    )
    assert len(recovered.projected_transfers) == 1


def test_partition_then_recovery_episode_uses_actual_unrelated_edge_state() -> None:
    policy = RuleRegionResourcePolicy()
    recipe = _recipe(
        seed=28118,
        target_class=V8TransferClass.SAFE_FORWARD,
        communication_condition="partition_then_recovery",
    )
    builder = V8RuntimeEpisodeEvidenceBuilder(
        episode_id="actual-partition-recovery",
        recipe=recipe,
        rule_policy=policy,
    )
    for frame_index, partition_pair in enumerate(((3, 4), None)):
        snapshot = _snapshot(
            seed=28118,
            source_index=0,
            target_index=1,
            resource_count=1,
            executable=True,
            timestamp_s=float(frame_index),
            partition_pair=partition_pair,
        )
        builder.stage_frame(
            frame_index=frame_index,
            evidence=_actual_evidence(
                snapshot,
                source_index=0,
                target_index=1,
                resource_count=1,
                policy=policy,
            ),
        )
    episode = builder.finalize()

    assert len(episode.frames) == 2
    assert any(
        edge.communication_partition_state.value == "partitioned"
        for edge in episode.frames[0].directed_edges
    )
    assert all(
        edge.communication_partition_state.value != "partitioned"
        for edge in episode.frames[1].directed_edges
    )


def test_wrong_resource_count_and_scenario_name_are_not_recipe_evidence() -> None:
    policy = RuleRegionResourcePolicy()
    count_mismatch = _snapshot(
        seed=28101,
        source_index=0,
        target_index=1,
        resource_count=1,
        executable=True,
    )
    builder = V8RuntimeEpisodeEvidenceBuilder(
        episode_id="wrong-count",
        recipe=_recipe(
            seed=28101,
            target_class=V8TransferClass.SAFE_FORWARD,
            count=2,
        ),
        rule_policy=policy,
    )
    with pytest.raises(
        RegionResourceV8RuntimeEvidenceError,
        match="actual_positive_recipe_not_satisfied",
    ):
        builder.stage_frame(
            frame_index=0,
            evidence=_actual_evidence(
                count_mismatch,
                source_index=0,
                target_index=1,
                resource_count=1,
                policy=policy,
            ),
        )

    spoofed = _snapshot(
        seed=28100,
        source_index=0,
        target_index=1,
        resource_count=1,
        executable=False,
        scenario_id="safe_forward_transfer",
    )
    spoof_builder = V8RuntimeEpisodeEvidenceBuilder(
        episode_id="scenario-name-is-not-evidence",
        recipe=_recipe(
            seed=28100,
            target_class=V8TransferClass.SAFE_FORWARD,
        ),
        rule_policy=policy,
    )
    with pytest.raises(
        RegionResourceV8RuntimeEvidenceError,
        match="actual_positive_recipe_not_satisfied",
    ):
        spoof_builder.stage_frame(
            frame_index=0,
            evidence=_actual_evidence(
                spoofed,
                source_index=0,
                target_index=1,
                resource_count=1,
                policy=policy,
            ),
        )


def test_identity_and_label_leaks_in_online_source_are_rejected() -> None:
    class LeakySnapshot(RegionResourceSnapshot):
        def to_dict(self) -> dict[str, object]:
            payload = super().to_dict()
            payload["global_track_id"] = "forbidden"
            return payload

    class LeakyRecommendation(RegionResourceRecommendation):
        def to_dict(self) -> dict[str, object]:
            payload = super().to_dict()
            payload["target_class"] = "safe_forward_transfer"
            return payload

    policy = RuleRegionResourcePolicy()
    snapshot = _snapshot(
        seed=28100,
        source_index=0,
        target_index=1,
        resource_count=1,
        executable=True,
    )
    evidence = _actual_evidence(
        snapshot,
        source_index=0,
        target_index=1,
        resource_count=1,
        policy=policy,
    )
    builder = V8RuntimeEpisodeEvidenceBuilder(
        episode_id="leak-rejection",
        recipe=_recipe(
            seed=28100,
            target_class=V8TransferClass.SAFE_FORWARD,
        ),
        rule_policy=policy,
    )
    leaky_snapshot = LeakySnapshot(**snapshot.__dict__)
    with pytest.raises(
        RegionResourceV8RuntimeEvidenceError,
        match="forbidden_online_source_field.*global_track_id",
    ):
        builder.stage_frame(
            frame_index=0,
            evidence=V8RuntimeFrameEvidence(
                snapshot=leaky_snapshot,
                r0_recommendation=evidence.r0_recommendation,
                raw_actor_proposal=evidence.raw_actor_proposal,
                projected_actor_recommendation=(
                    evidence.projected_actor_recommendation
                ),
                anonymous_candidates=evidence.anonymous_candidates,
                arrival_timestamp=evidence.arrival_timestamp,
            ),
        )

    leaky_raw = LeakyRecommendation(**evidence.raw_actor_proposal.__dict__)
    with pytest.raises(
        RegionResourceV8RuntimeEvidenceError,
        match="forbidden_online_source_field.*target_class",
    ):
        builder.stage_frame(
            frame_index=0,
            evidence=V8RuntimeFrameEvidence(
                snapshot=snapshot,
                r0_recommendation=evidence.r0_recommendation,
                raw_actor_proposal=leaky_raw,
                projected_actor_recommendation=(
                    evidence.projected_actor_recommendation
                ),
                anonymous_candidates=evidence.anonymous_candidates,
                arrival_timestamp=evidence.arrival_timestamp,
            ),
        )


def test_frame_index_is_contiguous() -> None:
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)
    recipe = frozen.schedule[0]
    policy = RuleRegionResourcePolicy()
    snapshot = _snapshot(
        seed=recipe.seed,
        source_index=0,
        target_index=1,
        resource_count=1,
        executable=True,
    )
    builder = V8RuntimeEpisodeEvidenceBuilder(
        episode_id="writer-runtime-round-trip",
        recipe=recipe,
        rule_policy=policy,
    )
    evidence = _actual_evidence(
        snapshot,
        source_index=0,
        target_index=1,
        resource_count=1,
        policy=policy,
    )
    with pytest.raises(
        RegionResourceV8RuntimeEvidenceError,
        match="frame_index_not_contiguous",
    ):
        builder.stage_frame(frame_index=1, evidence=evidence)
    builder.stage_frame(frame_index=0, evidence=evidence)
    builder.finalize()


def test_writer_stage_round_trip_uses_actual_built_episode(tmp_path: Path) -> None:
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)
    recipe = frozen.schedule[0]
    policy = RuleRegionResourcePolicy()
    snapshot = _snapshot(
        seed=recipe.seed,
        source_index=0,
        target_index=1,
        resource_count=1,
        executable=True,
    )
    builder = V8RuntimeEpisodeEvidenceBuilder(
        episode_id="writer-runtime-round-trip",
        recipe=recipe,
        rule_policy=policy,
    )
    builder.stage_frame(
        frame_index=0,
        evidence=_actual_evidence(
            snapshot,
            source_index=0,
            target_index=1,
            resource_count=1,
            policy=policy,
        ),
    )
    episode = builder.finalize()
    metadata = V8CleanSourceMetadata(
        source_scenario_id="actual-scalable-3d-v8-source",
        source_scenario_version="actual-v1",
        source_git_commit="a" * 40,
        source_git_dirty=False,
        source_config_sha256="b" * 64,
    )
    writer = V8TrainDatasetWriter.from_contract_files(
        dataset_root=tmp_path / "dataset",
        main_schedule_path=tmp_path / "schedule" / "main_schedule.json",
        request_path=_REQUEST_PATH,
        registry_path=_REGISTRY_PATH,
        expected_source_metadata=metadata,
        schedule_id="runtime-evidence-stage-schedule",
        dataset_id="runtime-evidence-stage-dataset",
    )
    staged = writer.stage_episode(
        schedule_index=0,
        episode_id=episode.episode_id,
        frames=episode.frames,
        labels=episode.labels,
        source_metadata=metadata,
    )
    assert staged.frame_count == 1
    assert staged.seed == recipe.seed
    writer.abort()
