"""Build v8 TRAIN evidence from actual D4 regional runtime DTOs.

The builder deliberately keeps the frozen recipe on the offline side.  Online
frames are reconstructed only from a truth-isolated ``RegionResourceSnapshot``,
the deterministic R0 rule result, anonymous candidate transfers, and the
deterministic projector result.  Scenario names never select a transfer class.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from typing import Any, Mapping, Sequence

from .region_resource import (
    DeterministicResourceProjector,
    RegionResourceAction,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RegionTransferSuggestion,
    RuleRegionResourcePolicy,
)
from .region_resource_v8_development_contract import (
    V8AnonymousRawActorAction,
    V8AnonymousTransferCandidate,
    V8DirectedEdgeState,
    V8NoAuthorityPermissions,
    V8OfflineTransferLabel,
    V8OnlineRegionResourceFrame,
    V8PartitionState,
    V8R0ActionTuple,
    V8R0RegionAction,
    V8RegionResourceState,
    V8RequestScheduleEntry,
    V8Transfer,
    V8TransferClass,
    classify_v8_edge_direction,
    expected_v8_directed_edges,
)
from .regional_failover import RegionalAuthorityLayer


V8_RUNTIME_EVIDENCE_LABEL_SOURCE = (
    "actual_snapshot_rule_and_deterministic_projection"
)

_MIN_HARD_NEGATIVE_ACTIVATION_SCORE = 0.5
_FORBIDDEN_ONLINE_SOURCE_KEYS = frozenset(
    {
        "actor_id",
        "actor_identity",
        "actor_name",
        "detection_truth_id",
        "expected_projected_transfers",
        "global_track_id",
        "ground_truth_id",
        "hard_negative_candidate_resource_count",
        "hard_negative_reasons",
        "label",
        "label_source",
        "object_id",
        "object_identity",
        "object_name",
        "offline_label",
        "positive_transfer_resource_count",
        "requested_target_class",
        "sim_object_id",
        "sim_object_name",
        "target_class",
        "target_id",
        "target_identity",
        "target_truth_id",
        "track_id",
        "truth_id",
        "truth_track_id",
    }
)


class RegionResourceV8RuntimeEvidenceError(ValueError):
    """Actual runtime evidence cannot safely satisfy the frozen v8 contract."""


@dataclass(frozen=True)
class V8AnonymousCandidateEvidence:
    """One identity-free candidate and its actual actor activation score."""

    transfer: RegionTransferSuggestion
    activation_score: float

    def __post_init__(self) -> None:
        if not isinstance(self.transfer, RegionTransferSuggestion):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_candidate_transfer_dto_required"
            )
        if (
            isinstance(self.activation_score, bool)
            or not isinstance(self.activation_score, (int, float))
            or not isfinite(float(self.activation_score))
            or not 0.0 <= float(self.activation_score) <= 1.0
        ):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_candidate_activation_score_invalid"
            )
        object.__setattr__(self, "activation_score", float(self.activation_score))


@dataclass(frozen=True)
class V8RuntimeFrameEvidence:
    """Actual, same-snapshot inputs for one v8 online/offline frame pair."""

    snapshot: RegionResourceSnapshot
    r0_recommendation: RegionResourceRecommendation
    raw_actor_proposal: RegionResourceRecommendation
    projected_actor_recommendation: RegionResourceRecommendation
    anonymous_candidates: tuple[V8AnonymousCandidateEvidence, ...]
    arrival_timestamp: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "anonymous_candidates", tuple(self.anonymous_candidates))
        if (
            isinstance(self.arrival_timestamp, bool)
            or not isinstance(self.arrival_timestamp, (int, float))
            or not isfinite(float(self.arrival_timestamp))
            or float(self.arrival_timestamp) < 0.0
        ):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_arrival_timestamp_invalid"
            )
        object.__setattr__(self, "arrival_timestamp", float(self.arrival_timestamp))


@dataclass(frozen=True)
class V8BuiltRuntimeEpisodeEvidence:
    """A complete in-memory episode ready for ``stage_episode``."""

    episode_id: str
    recipe: V8RequestScheduleEntry
    frames: tuple[V8OnlineRegionResourceFrame, ...]
    labels: tuple[V8OfflineTransferLabel, ...]


class V8RuntimeEpisodeEvidenceBuilder:
    """Incrementally convert actual D4 results into strict v8 TRAIN DTOs."""

    def __init__(
        self,
        *,
        episode_id: str,
        recipe: V8RequestScheduleEntry,
        rule_policy: RuleRegionResourcePolicy | None = None,
    ) -> None:
        if (
            not isinstance(episode_id, str)
            or not episode_id.strip()
            or episode_id != episode_id.strip()
        ):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_episode_id_invalid"
            )
        if not isinstance(recipe, V8RequestScheduleEntry):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_frozen_recipe_dto_required"
            )
        if rule_policy is not None and not isinstance(
            rule_policy, RuleRegionResourcePolicy
        ):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_rule_policy_required"
            )
        self._episode_id = episode_id
        self._recipe = V8RequestScheduleEntry(**recipe.to_registry_dict())
        self._rule_policy = rule_policy or RuleRegionResourcePolicy()
        self._frames: list[V8OnlineRegionResourceFrame] = []
        self._labels: list[V8OfflineTransferLabel] = []
        self._finalized = False

    @property
    def next_frame_index(self) -> int:
        return len(self._frames)

    @property
    def staged_frame_count(self) -> int:
        return len(self._frames)

    def stage_frame(
        self,
        *,
        frame_index: int,
        evidence: V8RuntimeFrameEvidence,
    ) -> tuple[V8OnlineRegionResourceFrame, V8OfflineTransferLabel]:
        """Validate and append exactly the next actual runtime frame."""

        if self._finalized:
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_episode_already_finalized"
            )
        if type(frame_index) is not int or frame_index != len(self._frames):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_frame_index_not_contiguous"
            )
        if not isinstance(evidence, V8RuntimeFrameEvidence):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_frame_evidence_dto_required"
            )

        snapshot = _canonical_snapshot(evidence.snapshot)
        r0 = _canonical_recommendation(evidence.r0_recommendation, "r0")
        raw_actor = _canonical_recommendation(
            evidence.raw_actor_proposal, "raw_actor"
        )
        projected_actor = _canonical_recommendation(
            evidence.projected_actor_recommendation, "projected_actor"
        )
        candidates = tuple(
            _canonical_candidate(item) for item in evidence.anonymous_candidates
        )

        self._validate_snapshot(snapshot, evidence.arrival_timestamp)
        self._validate_monotonic_time(snapshot, evidence.arrival_timestamp)
        self._validate_actual_r0(snapshot, r0)
        self._validate_actor_projection(
            snapshot,
            raw_actor,
            projected_actor,
            candidates,
        )

        mapping = _build_topology_mapping(snapshot, self._recipe.topology_id)
        regions = _build_region_states(
            snapshot,
            self._rule_policy,
        )
        edges = _build_directed_edge_states(snapshot, mapping)
        r0_tuple = _build_r0_action_tuple(snapshot, r0, mapping)
        raw_candidates = tuple(
            _candidate_to_v8(index, candidate, mapping)
            for index, candidate in enumerate(candidates)
        )
        projected_transfers = tuple(
            _transfer_to_v8(transfer, mapping)
            for transfer in projected_actor.transfers
        )
        online_rejections, hard_rejections = _derive_actual_rejections(
            snapshot=snapshot,
            raw_actor=raw_actor,
            projected_actor=projected_actor,
            candidates=candidates,
            regions=regions,
            mapping=mapping,
            projector=self._rule_policy.projector,
        )
        self._validate_recipe_result(
            raw_candidates=raw_candidates,
            projected_transfers=projected_transfers,
            projection_rejections=online_rejections,
            hard_negative_reasons=hard_rejections,
        )

        frame = V8OnlineRegionResourceFrame(
            frame_id=f"{self._episode_id}:{frame_index}",
            episode_id=self._episode_id,
            seed=snapshot.seed,
            split="train",
            frame_index=frame_index,
            measurement_timestamp=snapshot.timestamp_s,
            arrival_timestamp=evidence.arrival_timestamp,
            topology_id=self._recipe.topology_id,
            region_count=self._recipe.region_count,
            regions=regions,
            directed_edges=edges,
            r0_action_tuple=r0_tuple,
            raw_actor=V8AnonymousRawActorAction(
                activated=bool(raw_candidates),
                anonymous_candidates=raw_candidates,
            ),
            projected_transfers=projected_transfers,
            projection_rejection_reasons=online_rejections,
            invariant_failure_reasons=(),
            permissions=V8NoAuthorityPermissions(),
        )
        hard_negative = (
            self._recipe.requested_target_class
            == V8TransferClass.HARD_NO_TRANSFER
        )
        label = V8OfflineTransferLabel(
            frame_id=frame.frame_id,
            episode_id=frame.episode_id,
            seed=frame.seed,
            split="train",
            frame_index=frame.frame_index,
            online_frame_sha256=frame.content_sha256,
            target_class=self._recipe.requested_target_class,
            expected_projected_transfers=frame.projected_transfers,
            positive_transfer_resource_count=(
                0
                if hard_negative
                else sum(item.resource_count for item in frame.projected_transfers)
            ),
            hard_negative_candidate_resource_count=(
                sum(item.resource_count for item in raw_candidates)
                if hard_negative
                else 0
            ),
            hard_negative_reasons=(hard_rejections if hard_negative else ()),
            label_source=V8_RUNTIME_EVIDENCE_LABEL_SOURCE,
        )
        canonical_frame = V8OnlineRegionResourceFrame.from_dict(frame.to_dict())
        canonical_label = V8OfflineTransferLabel.from_dict(label.to_dict())
        self._frames.append(canonical_frame)
        self._labels.append(canonical_label)
        return canonical_frame, canonical_label

    def finalize(self) -> V8BuiltRuntimeEpisodeEvidence:
        """Close one episode after checking observed recipe conditions."""

        if self._finalized:
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_episode_already_finalized"
            )
        if not self._frames:
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_episode_has_no_frames"
            )
        _validate_observed_supply_demand(self._frames, self._recipe)
        _validate_observed_communication(self._frames, self._recipe)
        self._finalized = True
        return V8BuiltRuntimeEpisodeEvidence(
            episode_id=self._episode_id,
            recipe=self._recipe,
            frames=tuple(self._frames),
            labels=tuple(self._labels),
        )

    def _validate_snapshot(
        self,
        snapshot: RegionResourceSnapshot,
        arrival_timestamp: float,
    ) -> None:
        if snapshot.seed != self._recipe.seed:
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_snapshot_seed_recipe_mismatch"
            )
        if snapshot.region_count != self._recipe.region_count:
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_snapshot_region_count_recipe_mismatch"
            )
        if arrival_timestamp < snapshot.timestamp_s:
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_arrival_precedes_snapshot_measurement"
            )

    def _validate_monotonic_time(
        self,
        snapshot: RegionResourceSnapshot,
        arrival_timestamp: float,
    ) -> None:
        if not self._frames:
            return
        previous = self._frames[-1]
        if (
            snapshot.timestamp_s < previous.measurement_timestamp
            or arrival_timestamp < previous.arrival_timestamp
        ):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_episode_timestamp_not_monotonic"
            )

    def _validate_actual_r0(
        self,
        snapshot: RegionResourceSnapshot,
        actual: RegionResourceRecommendation,
    ) -> None:
        expected = self._rule_policy.recommend(
            snapshot,
            fallback_reason=actual.fallback_reason,
        )
        if actual != expected:
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_r0_not_actual_rule_policy_result"
            )

    def _validate_actor_projection(
        self,
        snapshot: RegionResourceSnapshot,
        raw_actor: RegionResourceRecommendation,
        projected_actor: RegionResourceRecommendation,
        candidates: Sequence[V8AnonymousCandidateEvidence],
    ) -> None:
        if raw_actor.projected:
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_raw_actor_must_be_unprojected"
            )
        if not projected_actor.projected:
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_actor_projection_result_required"
            )
        _validate_recommendation_snapshot_binding(snapshot, raw_actor)
        if raw_actor.created_at_s != snapshot.timestamp_s:
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_raw_actor_not_same_snapshot_time"
            )
        candidate_transfers = tuple(item.transfer for item in candidates)
        if candidate_transfers != raw_actor.transfers:
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_anonymous_candidates_raw_proposal_mismatch"
            )
        expected = self._rule_policy.projector.project(snapshot, raw_actor)
        if projected_actor != expected:
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_projection_not_actual_deterministic_result"
            )

    def _validate_recipe_result(
        self,
        *,
        raw_candidates: Sequence[V8AnonymousTransferCandidate],
        projected_transfers: Sequence[V8Transfer],
        projection_rejections: Sequence[str],
        hard_negative_reasons: Sequence[str],
    ) -> None:
        raw_count = sum(item.resource_count for item in raw_candidates)
        projected_count = sum(item.resource_count for item in projected_transfers)
        target_class = self._recipe.requested_target_class
        if target_class == V8TransferClass.HARD_NO_TRANSFER:
            if (
                raw_count != self._recipe.hard_negative_candidate_resource_count
                or projected_count != 0
                or not projection_rejections
                or not hard_negative_reasons
            ):
                raise RegionResourceV8RuntimeEvidenceError(
                    "v8_runtime_actual_hard_negative_recipe_not_satisfied"
                )
            return

        expected_direction = (
            "forward"
            if target_class == V8TransferClass.SAFE_FORWARD
            else "reverse"
        )
        if (
            raw_count != self._recipe.requested_transfer_resource_count
            or projected_count != self._recipe.requested_transfer_resource_count
            or projection_rejections
            or hard_negative_reasons
        ):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_actual_positive_recipe_not_satisfied"
            )
        if any(
            classify_v8_edge_direction(
                self._recipe.topology_id,
                item.source_region_index,
                item.target_region_index,
            )
            != expected_direction
            for item in projected_transfers
        ):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_actual_transfer_direction_recipe_mismatch"
            )
        if any(
            item.action_key
            not in {candidate.action_key for candidate in raw_candidates}
            for item in projected_transfers
        ):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_projector_clipping_not_representable"
            )


@dataclass(frozen=True)
class _TopologyMapping:
    topology_id: str
    region_index_by_id: Mapping[str, int]
    expected_pairs: tuple[tuple[int, int], ...]
    edge_by_pair: Mapping[tuple[int, int], RegionResourceEdge]


def _canonical_snapshot(value: RegionResourceSnapshot) -> RegionResourceSnapshot:
    if not isinstance(value, RegionResourceSnapshot):
        raise RegionResourceV8RuntimeEvidenceError(
            "v8_runtime_snapshot_dto_required"
        )
    try:
        payload = value.to_dict()
        _reject_online_source_leak(payload)
        return RegionResourceSnapshot.from_dict(payload)
    except RegionResourceV8RuntimeEvidenceError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceV8RuntimeEvidenceError(
            f"v8_runtime_snapshot_invalid:{type(exc).__name__}:{exc}"
        ) from exc


def _canonical_recommendation(
    value: RegionResourceRecommendation,
    role: str,
) -> RegionResourceRecommendation:
    if not isinstance(value, RegionResourceRecommendation):
        raise RegionResourceV8RuntimeEvidenceError(
            f"v8_runtime_{role}_recommendation_dto_required"
        )
    try:
        payload = value.to_dict()
        _reject_online_source_leak(payload)
        return RegionResourceRecommendation.from_dict(payload)
    except RegionResourceV8RuntimeEvidenceError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceV8RuntimeEvidenceError(
            f"v8_runtime_{role}_recommendation_invalid:{type(exc).__name__}:{exc}"
        ) from exc


def _canonical_candidate(
    value: V8AnonymousCandidateEvidence,
) -> V8AnonymousCandidateEvidence:
    if not isinstance(value, V8AnonymousCandidateEvidence):
        raise RegionResourceV8RuntimeEvidenceError(
            "v8_runtime_anonymous_candidate_dto_required"
        )
    try:
        payload = value.transfer.to_dict()
        _reject_online_source_leak(payload)
        transfer = RegionTransferSuggestion.from_dict(payload)
    except RegionResourceV8RuntimeEvidenceError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceV8RuntimeEvidenceError(
            f"v8_runtime_candidate_invalid:{type(exc).__name__}:{exc}"
        ) from exc
    return V8AnonymousCandidateEvidence(
        transfer=transfer,
        activation_score=value.activation_score,
    )


def _reject_online_source_leak(value: Any, *, path: str = "online_source") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_ONLINE_SOURCE_KEYS:
                raise RegionResourceV8RuntimeEvidenceError(
                    f"v8_runtime_forbidden_online_source_field:{path}.{key}"
                )
            _reject_online_source_leak(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_online_source_leak(item, path=f"{path}[{index}]")


def _validate_recommendation_snapshot_binding(
    snapshot: RegionResourceSnapshot,
    recommendation: RegionResourceRecommendation,
) -> None:
    if (
        recommendation.snapshot_id != snapshot.snapshot_id
        or recommendation.scenario_id != snapshot.scenario_id
        or recommendation.scenario_version != snapshot.scenario_version
        or recommendation.seed != snapshot.seed
        or recommendation.authority_digest != snapshot.authority_digest
        or recommendation.planning_authority_digest
        != snapshot.planning_authority_digest
    ):
        raise RegionResourceV8RuntimeEvidenceError(
            "v8_runtime_recommendation_snapshot_or_authority_mismatch"
        )


def _build_topology_mapping(
    snapshot: RegionResourceSnapshot,
    topology_id: str,
) -> _TopologyMapping:
    index_by_id = {
        node.region_id: index for index, node in enumerate(snapshot.regions)
    }
    edge_by_pair: dict[tuple[int, int], RegionResourceEdge] = {}
    for edge in snapshot.edges:
        source = index_by_id[edge.source_region_id]
        target = index_by_id[edge.target_region_id]
        pairs = [(source, target)]
        if edge.bidirectional:
            pairs.append((target, source))
        for pair in pairs:
            if pair in edge_by_pair:
                raise RegionResourceV8RuntimeEvidenceError(
                    "v8_runtime_actual_directed_edge_duplicate"
                )
            edge_by_pair[pair] = edge
    expected_pairs = expected_v8_directed_edges(topology_id)
    if tuple(sorted(edge_by_pair)) != expected_pairs:
        raise RegionResourceV8RuntimeEvidenceError(
            "v8_runtime_actual_directed_topology_incomplete_or_extra"
        )
    return _TopologyMapping(
        topology_id=topology_id,
        region_index_by_id=index_by_id,
        expected_pairs=expected_pairs,
        edge_by_pair=edge_by_pair,
    )


def _build_region_states(
    snapshot: RegionResourceSnapshot,
    rule_policy: RuleRegionResourcePolicy,
) -> tuple[V8RegionResourceState, ...]:
    result: list[V8RegionResourceState] = []
    for index, node in enumerate(snapshot.regions):
        weighted_demand = (
            node.target_demand
            + rule_policy.config.high_threat_weight * node.high_threat_backlog
        )
        demand_required = int(ceil(weighted_demand))
        reserve_floor = _reserve_floor(node, rule_policy.projector)
        gap = (
            node.available_resources
            - node.committed_resources
            - reserve_floor
            - demand_required
        )
        result.append(
            V8RegionResourceState(
                region_index=index,
                region_id=f"region-{index}",
                supply_available=node.available_resources,
                supply_committed=node.committed_resources,
                supply_reserved=reserve_floor,
                demand_required=demand_required,
                demand_weighted=weighted_demand,
                supply_demand_gap=gap,
                owner_id=node.current_owner_id,
                owner_layer=node.current_owner_layer,
                plan_id=node.plan_id,
                plan_version=node.plan_version,
                epoch=node.epoch,
                lease_expires_at_s=node.lease_expires_at_s,
                coalition_ack_complete=node.coalition_ack_complete,
                owner_active=node.owner_active,
                fault_fenced=bool(
                    node.fault_fenced
                    or (
                        node.fault_fence_epoch is not None
                        and node.epoch < node.fault_fence_epoch
                    )
                ),
            )
        )
    return tuple(result)


def _build_directed_edge_states(
    snapshot: RegionResourceSnapshot,
    mapping: _TopologyMapping,
) -> tuple[V8DirectedEdgeState, ...]:
    nodes = snapshot.region_by_id
    result: list[V8DirectedEdgeState] = []
    for edge_index, pair in enumerate(mapping.expected_pairs):
        edge = mapping.edge_by_pair[pair]
        source_id = snapshot.regions[pair[0]].region_id
        target_id = snapshot.regions[pair[1]].region_id
        source = nodes[source_id]
        target = nodes[target_id]
        available = bool(
            edge.communication_available
            and edge.bandwidth_mbps > 0.0
            and not edge.partitioned
        )
        partition_state = (
            V8PartitionState.PARTITIONED
            if edge.partitioned
            else (
                V8PartitionState.CONNECTED
                if available
                else V8PartitionState.RECOVERING
            )
        )
        result.append(
            V8DirectedEdgeState(
                edge_index=edge_index,
                source_region_index=pair[0],
                target_region_index=pair[1],
                transfer_capacity=int(edge.transferable_resources),
                communication_latency_s=max(
                    source.communication_latency_s,
                    target.communication_latency_s,
                ),
                communication_loss_rate=max(
                    source.packet_loss_rate,
                    target.packet_loss_rate,
                ),
                communication_partition_state=partition_state,
                communication_available=available,
                maneuver_available=edge.maneuver_available,
            )
        )
    return tuple(result)


def _build_r0_action_tuple(
    snapshot: RegionResourceSnapshot,
    recommendation: RegionResourceRecommendation,
    mapping: _TopologyMapping,
) -> V8R0ActionTuple:
    action_by_region = {item.region_id: item for item in recommendation.actions}
    if set(action_by_region) != set(mapping.region_index_by_id):
        raise RegionResourceV8RuntimeEvidenceError(
            "v8_runtime_r0_region_action_inventory_mismatch"
        )
    actions = tuple(
        _action_to_v8(index, action_by_region[node.region_id])
        for index, node in enumerate(snapshot.regions)
    )
    transfers = tuple(
        _transfer_to_v8(item, mapping) for item in recommendation.transfers
    )
    return V8R0ActionTuple(region_actions=actions, transfers=transfers)


def _action_to_v8(index: int, action: RegionResourceAction) -> V8R0RegionAction:
    return V8R0RegionAction(
        region_index=index,
        resource_quota_delta=action.resource_quota_delta,
        reserve_ratio=action.reserve_ratio,
        reconnaissance_priority=action.reconnaissance_priority,
        hold=action.hold,
        request_replan=action.request_replan,
    )


def _transfer_to_v8(
    transfer: RegionTransferSuggestion,
    mapping: _TopologyMapping,
) -> V8Transfer:
    try:
        source = mapping.region_index_by_id[transfer.source_region_id]
        target = mapping.region_index_by_id[transfer.target_region_id]
    except KeyError as exc:
        raise RegionResourceV8RuntimeEvidenceError(
            "v8_runtime_transfer_region_unknown"
        ) from exc
    pair = (source, target)
    edge = mapping.edge_by_pair.get(pair)
    if edge is None or transfer.edge_id != edge.edge_id:
        raise RegionResourceV8RuntimeEvidenceError(
            "v8_runtime_transfer_not_on_actual_directed_edge"
        )
    if transfer.expected_transfer_time_s != edge.transfer_time_s:
        raise RegionResourceV8RuntimeEvidenceError(
            "v8_runtime_transfer_time_not_from_actual_edge"
        )
    edge_index = mapping.expected_pairs.index(pair)
    return V8Transfer(
        edge_index=edge_index,
        source_region_index=source,
        target_region_index=target,
        resource_count=int(transfer.resource_count),
    )


def _candidate_to_v8(
    candidate_index: int,
    candidate: V8AnonymousCandidateEvidence,
    mapping: _TopologyMapping,
) -> V8AnonymousTransferCandidate:
    transfer = _transfer_to_v8(candidate.transfer, mapping)
    return V8AnonymousTransferCandidate(
        candidate_index=candidate_index,
        edge_index=transfer.edge_index,
        source_region_index=transfer.source_region_index,
        target_region_index=transfer.target_region_index,
        resource_count=transfer.resource_count,
        activation_score=candidate.activation_score,
    )


def _derive_actual_rejections(
    *,
    snapshot: RegionResourceSnapshot,
    raw_actor: RegionResourceRecommendation,
    projected_actor: RegionResourceRecommendation,
    candidates: Sequence[V8AnonymousCandidateEvidence],
    regions: Sequence[V8RegionResourceState],
    mapping: _TopologyMapping,
    projector: DeterministicResourceProjector,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if projected_actor.transfers:
        raw_keys = {
            _transfer_to_v8(item.transfer, mapping).action_key for item in candidates
        }
        projected_keys = {
            _transfer_to_v8(item, mapping).action_key
            for item in projected_actor.transfers
        }
        if not projected_keys.issubset(raw_keys):
            raise RegionResourceV8RuntimeEvidenceError(
                "v8_runtime_projector_clipping_not_representable"
            )

    region_by_index = {item.region_index: item for item in regions}
    node_by_id = snapshot.region_by_id
    action_by_id = {item.region_id: item for item in raw_actor.actions}
    online: list[str] = []
    offline: list[str] = []
    globally_stale = bool(
        raw_actor.snapshot_id != snapshot.snapshot_id
        or raw_actor.scenario_id != snapshot.scenario_id
        or raw_actor.scenario_version != snapshot.scenario_version
        or raw_actor.seed != snapshot.seed
        or raw_actor.authority_digest != snapshot.authority_digest
        or raw_actor.planning_authority_digest
        != snapshot.planning_authority_digest
    )
    if globally_stale:
        online.append("stale_owner_version_epoch_or_lease")
        offline.append("stale_owner_version_epoch_or_lease")

    for candidate in candidates:
        mapped = _transfer_to_v8(candidate.transfer, mapping)
        source_state = region_by_index[mapped.source_region_index]
        source_node = node_by_id[candidate.transfer.source_region_id]
        target_node = node_by_id[candidate.transfer.target_region_id]
        edge = mapping.edge_by_pair[
            (mapped.source_region_index, mapped.target_region_index)
        ]
        candidate_reasons: list[str] = []

        if edge.partitioned:
            candidate_reasons.append("communication_partitioned")
        elif not edge.communication_available or edge.bandwidth_mbps <= 0.0:
            candidate_reasons.append("communication_unavailable")
        if not edge.maneuver_available:
            candidate_reasons.append("maneuver_unavailable")
        if mapped.resource_count > int(edge.transferable_resources):
            candidate_reasons.append("edge_capacity_exceeded")

        source_budget = _transfer_budget(source_node, projector)
        if (
            mapped.resource_count > source_budget
            or mapped.resource_count > source_state.supply_demand_gap
        ):
            candidate_reasons.append("insufficient_source_surplus")

        for node in (source_node, target_node):
            action = action_by_id.get(node.region_id)
            if snapshot.timestamp_s >= node.lease_expires_at_s or not _action_matches(
                node, action
            ):
                candidate_reasons.append(
                    "stale_owner_version_epoch_or_lease"
                )
            if (
                not node.owner_active
                or node.current_owner_layer == RegionalAuthorityLayer.HOLD
            ):
                candidate_reasons.append("owner_inactive")
            if node.fault_fenced or (
                node.fault_fence_epoch is not None
                and node.epoch < node.fault_fence_epoch
            ):
                candidate_reasons.append("owner_fault_fenced")
            if not node.coalition_ack_complete:
                candidate_reasons.append("coalition_ack_incomplete")

        online.extend(candidate_reasons)
        if "insufficient_source_surplus" in candidate_reasons:
            offline.append("insufficient_source_surplus")
        if any(
            item
            in {
                "stale_owner_version_epoch_or_lease",
                "owner_inactive",
                "owner_fault_fenced",
                "coalition_ack_incomplete",
            }
            for item in candidate_reasons
        ):
            offline.append("stale_owner_version_epoch_or_lease")
        if any(
            item in {"communication_partitioned", "communication_unavailable"}
            for item in candidate_reasons
        ):
            offline.append("communication_partition_or_expired_evidence")
        if any(
            item in {"edge_capacity_exceeded", "maneuver_unavailable"}
            for item in candidate_reasons
        ):
            if candidate.activation_score < _MIN_HARD_NEGATIVE_ACTIVATION_SCORE:
                raise RegionResourceV8RuntimeEvidenceError(
                    "v8_runtime_hard_negative_activation_score_too_low"
                )
            offline.append("high_transfer_score_but_no_safe_executable_transfer")

    online_result = _unique(online)
    offline_result = _unique(offline)
    if projected_actor.projection_rejections and not online_result:
        raise RegionResourceV8RuntimeEvidenceError(
            "v8_runtime_projection_rejection_lacks_actual_dto_reason"
        )
    if not projected_actor.projection_rejections and online_result:
        raise RegionResourceV8RuntimeEvidenceError(
            "v8_runtime_actual_dto_rejection_missing_from_projector_result"
        )
    return online_result, offline_result


def _action_matches(
    node: RegionResourceNode,
    action: RegionResourceAction | None,
) -> bool:
    return bool(
        action is not None
        and action.expected_owner_id == node.current_owner_id
        and action.expected_owner_layer == node.current_owner_layer
        and action.expected_plan_id == node.plan_id
        and action.expected_plan_version == node.plan_version
        and action.expected_epoch == node.epoch
        and action.expected_lease_expires_at_s == node.lease_expires_at_s
    )


def _reserve_floor(
    node: RegionResourceNode,
    projector: DeterministicResourceProjector,
) -> int:
    return min(
        node.available_resources - node.committed_resources,
        max(
            int(node.reserve_resources),
            int(projector.config.minimum_reserve_resources),
            int(ceil(projector.config.minimum_reserve_ratio * node.available_resources)),
        ),
    )


def _transfer_budget(
    node: RegionResourceNode,
    projector: DeterministicResourceProjector,
) -> int:
    return max(
        0,
        node.available_resources
        - node.committed_resources
        - _reserve_floor(node, projector),
    )


def _validate_observed_supply_demand(
    frames: Sequence[V8OnlineRegionResourceFrame],
    recipe: V8RequestScheduleEntry,
) -> None:
    gaps = [region.supply_demand_gap for frame in frames for region in frame.regions]
    condition = recipe.supply_demand_condition
    if condition == "source_surplus_target_deficit":
        passed = any(value > 0 for value in gaps) and any(value < 0 for value in gaps)
    elif condition == "balanced_boundary":
        passed = bool(gaps) and all(abs(value) <= 1 for value in gaps)
    else:
        passed = sum(gaps) < 0 and any(value > 0 for value in gaps)
    if not passed:
        raise RegionResourceV8RuntimeEvidenceError(
            f"v8_runtime_actual_supply_demand_condition_not_observed:{condition}"
        )


def _validate_observed_communication(
    frames: Sequence[V8OnlineRegionResourceFrame],
    recipe: V8RequestScheduleEntry,
) -> None:
    condition = recipe.communication_condition
    edges = [edge for frame in frames for edge in frame.directed_edges]
    if condition == "nominal":
        passed = all(
            edge.communication_partition_state == V8PartitionState.CONNECTED
            and edge.communication_available
            and edge.communication_latency_s <= 0.05
            and edge.communication_loss_rate <= 0.01
            for edge in edges
        )
    elif condition == "bounded_delay_and_loss":
        passed = all(
            edge.communication_partition_state != V8PartitionState.PARTITIONED
            and edge.communication_available
            and edge.communication_latency_s <= 0.5
            and edge.communication_loss_rate <= 0.3
            for edge in edges
        ) and any(
            edge.communication_latency_s > 0.05
            or edge.communication_loss_rate > 0.01
            for edge in edges
        )
    else:
        partition_indices = [
            frame.frame_index
            for frame in frames
            if any(
                edge.communication_partition_state == V8PartitionState.PARTITIONED
                for edge in frame.directed_edges
            )
        ]
        recovery_indices = [
            frame.frame_index
            for frame in frames
            if all(
                edge.communication_partition_state != V8PartitionState.PARTITIONED
                for edge in frame.directed_edges
            )
        ]
        passed = bool(partition_indices) and any(
            recovered > min(partition_indices) for recovered in recovery_indices
        )
    if not passed:
        raise RegionResourceV8RuntimeEvidenceError(
            f"v8_runtime_actual_communication_condition_not_observed:{condition}"
        )


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


__all__ = [
    "RegionResourceV8RuntimeEvidenceError",
    "V8AnonymousCandidateEvidence",
    "V8BuiltRuntimeEpisodeEvidence",
    "V8RuntimeEpisodeEvidenceBuilder",
    "V8RuntimeFrameEvidence",
    "V8_RUNTIME_EVIDENCE_LABEL_SOURCE",
]
