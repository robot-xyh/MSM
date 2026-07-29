"""Optional graph-learning research path for regional resource advice.

The learned policy is never an authority source.  Every output is projected by
``DeterministicResourceProjector`` and remains advisory to D4/D3/main.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import sha256
import json
from math import atanh, isfinite, log
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Mapping, Sequence

from .region_resource import (
    AdvisorMode,
    DETERMINISTIC_RESOURCE_PROJECTOR_NAME,
    DETERMINISTIC_RESOURCE_PROJECTOR_VERSION,
    DeterministicResourceProjector,
    REGION_RESOURCE_FEATURE_SCHEMA,
    RecommendationSource,
    RegionResourceAction,
    RegionResourceAdvisoryContract,
    RegionResourceProjectionConfig,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RegionTransferSuggestion,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
    formal_decision_digest,
)
from .regional_failover import RegionalAuthorityLayer, RegionalFailoverDecision
from .region_resource_dataset import (
    REGION_LEARNING_DATASET_SCHEMA,
    LoadedRegionLearningDataset,
    RegionLearningAvailability,
    RegionLearningDataUnavailableError,
    RegionLearningDatasetManifest,
    RegionLearningEpisodeSource,
    RegionLearningSplit,
    load_region_learning_dataset,
)
from .canonical_seed_split import CanonicalRegionLearningDatasetView


try:  # The default deterministic D4 path does not require torch.
    import torch
    from torch import nn
except ImportError:  # pragma: no cover - exercised only in minimal deployments.
    torch = None
    nn = None


REGION_RESOURCE_MODEL_BUNDLE_SCHEMA = "d4-region-resource-model-bundle-v2"
REGION_GRAPH_ARCHITECTURE = "shared-region-graph-actor-critic-v1"
REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_SCHEMA = (
    "d4-region-resource-runtime-confidence-gate-v1"
)
REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_MODE = (
    "deterministic-rule-action-consistency-gate-v1"
)
REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_THRESHOLD = 0.60
REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_OOD_MARGIN = 0.05
REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_INCONSISTENT_CAP = 0.59
REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_CONTINUOUS_TOLERANCE = 0.10
REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_DIAGNOSTIC_SCHEMA = (
    "d4-region-resource-runtime-confidence-gate-diagnostic-v1"
)
MODEL_LIFECYCLE_DEVELOPMENT = "development"
MODEL_LIFECYCLE_QUALIFIED = "qualified"
MODEL_MAXIMUM_MODE_SHADOW = AdvisorMode.SHADOW.value
MODEL_MAXIMUM_MODE_ASSIST = AdvisorMode.ASSIST.value

NODE_FEATURE_NAMES = (
    "target_demand_fraction",
    "high_threat_backlog_fraction",
    "d1_uncertainty_log",
    "d2_uncertainty_log",
    "d5_visibility",
    "d5_consistency",
    "available_resource_fraction",
    "reserve_resource_fraction",
    "committed_resource_fraction",
    "secondary_coverage",
    "secondary_readiness",
    "communication_capacity_log",
    "communication_latency_log",
    "packet_loss_rate",
    "owner_center",
    "owner_secondary",
    "owner_distributed",
    "owner_hold",
    "lease_remaining_minutes",
    "coalition_ack_complete",
    "owner_active",
    "fault_fenced",
    "assignment_conflict_fraction",
    "degradation_failed",
)
EDGE_FEATURE_NAMES = (
    "transferable_resource_fraction",
    "distance_log",
    "transfer_time_log",
    "bandwidth_log",
    "communication_available",
    "maneuver_available",
    "partitioned",
)
NODE_ACTION_DIM = 5
EDGE_ACTION_DIM = 1


def _canonical_sha256(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def region_resource_projection_config_payload(
    config: RegionResourceProjectionConfig,
) -> dict[str, Any]:
    return {
        "minimum_reserve_ratio": float(config.minimum_reserve_ratio),
        "minimum_reserve_resources": int(
            config.minimum_reserve_resources
        ),
        "advisory_ttl_s": float(config.advisory_ttl_s),
    }


def region_resource_rule_policy_config_payload(
    config: RuleRegionResourcePolicyConfig,
) -> dict[str, Any]:
    return {
        "projection": region_resource_projection_config_payload(
            config.projection
        ),
        "high_threat_weight": float(config.high_threat_weight),
        "uncertainty_weight": float(config.uncertainty_weight),
        "transfer_pressure_margin": float(
            config.transfer_pressure_margin
        ),
    }


def _region_resource_projection_config_from_payload(
    value: Mapping[str, Any],
) -> RegionResourceProjectionConfig:
    expected = {
        "minimum_reserve_ratio",
        "minimum_reserve_resources",
        "advisory_ttl_s",
    }
    if set(value) != expected:
        raise ValueError("runtime gate projection config keys mismatch")
    minimum_resources = value["minimum_reserve_resources"]
    if type(minimum_resources) is not int:
        raise ValueError(
            "runtime gate minimum reserve resources must be an integer"
        )
    return RegionResourceProjectionConfig(
        minimum_reserve_ratio=float(value["minimum_reserve_ratio"]),
        minimum_reserve_resources=minimum_resources,
        advisory_ttl_s=float(value["advisory_ttl_s"]),
    )


def _region_resource_rule_policy_config_from_payload(
    value: Mapping[str, Any],
) -> RuleRegionResourcePolicyConfig:
    expected = {
        "projection",
        "high_threat_weight",
        "uncertainty_weight",
        "transfer_pressure_margin",
    }
    if set(value) != expected or not isinstance(
        value["projection"], Mapping
    ):
        raise ValueError("runtime gate rule config keys mismatch")
    return RuleRegionResourcePolicyConfig(
        projection=_region_resource_projection_config_from_payload(
            value["projection"]
        ),
        high_threat_weight=float(value["high_threat_weight"]),
        uncertainty_weight=float(value["uncertainty_weight"]),
        transfer_pressure_margin=float(
            value["transfer_pressure_margin"]
        ),
    )


def runtime_confidence_gate_consistency_definition() -> dict[str, Any]:
    definition = {
        "name": REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_MODE,
        "candidate_action": (
            "learned recommendation after deterministic safety projection"
        ),
        "reference_action": (
            "truth-free deterministic rule recommendation after the same "
            "safety projection"
        ),
        "runtime_context": (
            "the exact RegionResourceAdvisor projector, rule policy, and "
            "formal_decision supplied for the final recommendation"
        ),
        "region_identity": "exact region_id set",
        "quota_error": (
            "absolute resource_quota_delta difference divided by "
            "max(1, available_resources)"
        ),
        "reserve_error": "absolute reserve_ratio difference",
        "reconnaissance_error": (
            "absolute reconnaissance_priority difference"
        ),
        "continuous_acceptance": (
            "quota, reserve, and reconnaissance maximum error each no "
            "greater than 0.10"
        ),
        "binary_acceptance": "hold and request_replan exact for every region",
        "transfer_acceptance": (
            "exact multiset of edge_id, source_region_id, target_region_id, "
            "and resource_count"
        ),
        "confidence_action": (
            "retain raw confidence when consistent; otherwise cap effective "
            "confidence at 0.59 before the fixed 0.60 threshold"
        ),
        "truth_identifier_use_count": 0,
        "future_outcome_use_count": 0,
    }
    definition["content_sha256"] = _canonical_sha256(definition)
    return definition


class RegionResourceLearningError(RuntimeError):
    pass


class RuntimeConfidenceGateContextError(RegionResourceLearningError):
    pass


class ModelBundleValidationError(RegionResourceLearningError):
    pass


class NonFinitePolicyOutput(RegionResourceLearningError):
    pass


@dataclass(frozen=True)
class RegionGraphEdgeRef:
    edge_id: str
    source_region_id: str
    target_region_id: str
    transferable_resources: int
    transfer_time_s: float


@dataclass(frozen=True)
class RegionGraph:
    node_features: Any
    edge_features: Any
    edge_index: Any
    node_ids: tuple[str, ...]
    edge_refs: tuple[RegionGraphEdgeRef, ...]

    @property
    def node_count(self) -> int:
        return len(self.node_ids)

    @property
    def edge_count(self) -> int:
        return len(self.edge_refs)

    def to(self, device: Any) -> "RegionGraph":
        _require_torch()
        return RegionGraph(
            node_features=self.node_features.to(device),
            edge_features=self.edge_features.to(device),
            edge_index=self.edge_index.to(device),
            node_ids=self.node_ids,
            edge_refs=self.edge_refs,
        )


def snapshot_to_region_graph(
    snapshot: RegionResourceSnapshot,
    *,
    device: Any = None,
) -> RegionGraph:
    """Encode a variable-size graph with shared, fixed-width features."""

    _require_torch()
    ordered_nodes = sorted(snapshot.regions, key=lambda item: item.region_id)
    node_ids = tuple(node.region_id for node in ordered_nodes)
    node_index = {region_id: index for index, region_id in enumerate(node_ids)}
    total_resources = max(1, snapshot.total_resources)
    node_rows: list[list[float]] = []
    for node in ordered_nodes:
        layer_one_hot = [
            float(node.current_owner_layer == layer)
            for layer in (
                RegionalAuthorityLayer.CENTER,
                RegionalAuthorityLayer.SECONDARY,
                RegionalAuthorityLayer.DISTRIBUTED,
                RegionalAuthorityLayer.HOLD,
            )
        ]
        node_rows.append(
            [
                node.target_demand / total_resources,
                node.high_threat_backlog / total_resources,
                _log_feature(node.d1_uncertainty),
                _log_feature(node.d2_uncertainty),
                node.d5_visibility,
                node.d5_consistency,
                node.available_resources / total_resources,
                node.reserve_resources / total_resources,
                node.committed_resources / total_resources,
                node.secondary_coverage,
                node.secondary_readiness,
                _log_feature(node.communication_capacity),
                _log_feature(node.communication_latency_s),
                node.packet_loss_rate,
                *layer_one_hot,
                (node.lease_expires_at_s - snapshot.timestamp_s) / 60.0,
                float(node.coalition_ack_complete),
                float(node.owner_active),
                float(node.fault_fenced),
                node.assignment_conflict_count / total_resources,
                float(node.degradation_failed),
            ]
        )

    edge_rows: list[list[float]] = []
    edge_pairs: list[tuple[int, int]] = []
    edge_refs: list[RegionGraphEdgeRef] = []
    for edge in sorted(snapshot.edges, key=lambda item: item.edge_id):
        directions = [(edge.source_region_id, edge.target_region_id)]
        if edge.bidirectional:
            directions.append((edge.target_region_id, edge.source_region_id))
        for source_id, target_id in directions:
            edge_pairs.append((node_index[source_id], node_index[target_id]))
            edge_rows.append(
                [
                    edge.transferable_resources / total_resources,
                    _log_feature(edge.distance_m),
                    _log_feature(edge.transfer_time_s),
                    _log_feature(edge.bandwidth_mbps),
                    float(edge.communication_available),
                    float(edge.maneuver_available),
                    float(edge.partitioned),
                ]
            )
            edge_refs.append(
                RegionGraphEdgeRef(
                    edge_id=edge.edge_id,
                    source_region_id=source_id,
                    target_region_id=target_id,
                    transferable_resources=edge.transferable_resources,
                    transfer_time_s=edge.transfer_time_s,
                )
            )
    tensor_device = device if device is not None else "cpu"
    node_features = torch.tensor(node_rows, dtype=torch.float32, device=tensor_device)
    edge_features = torch.tensor(
        edge_rows,
        dtype=torch.float32,
        device=tensor_device,
    ).reshape((-1, len(EDGE_FEATURE_NAMES)))
    edge_index = torch.tensor(
        edge_pairs,
        dtype=torch.long,
        device=tensor_device,
    ).reshape((-1, 2)).transpose(0, 1)
    return RegionGraph(
        node_features=node_features,
        edge_features=edge_features,
        edge_index=edge_index,
        node_ids=node_ids,
        edge_refs=tuple(edge_refs),
    )


@dataclass(frozen=True)
class RegionFeatureBounds:
    node_min: tuple[float, ...]
    node_max: tuple[float, ...]
    edge_min: tuple[float, ...]
    edge_max: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.node_min) != len(NODE_FEATURE_NAMES) or len(self.node_max) != len(
            NODE_FEATURE_NAMES
        ):
            raise ValueError("node feature bounds have the wrong dimension")
        if len(self.edge_min) != len(EDGE_FEATURE_NAMES) or len(self.edge_max) != len(
            EDGE_FEATURE_NAMES
        ):
            raise ValueError("edge feature bounds have the wrong dimension")
        values = (*self.node_min, *self.node_max, *self.edge_min, *self.edge_max)
        if not all(isfinite(float(value)) for value in values):
            raise ValueError("feature bounds must be finite")
        if any(low > high for low, high in zip(self.node_min, self.node_max)):
            raise ValueError("node feature minima exceed maxima")
        if any(low > high for low, high in zip(self.edge_min, self.edge_max)):
            raise ValueError("edge feature minima exceed maxima")

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_min": list(self.node_min),
            "node_max": list(self.node_max),
            "edge_min": list(self.edge_min),
            "edge_max": list(self.edge_max),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionFeatureBounds":
        return cls(
            node_min=tuple(float(item) for item in value["node_min"]),
            node_max=tuple(float(item) for item in value["node_max"]),
            edge_min=tuple(float(item) for item in value["edge_min"]),
            edge_max=tuple(float(item) for item in value["edge_max"]),
        )

    @classmethod
    def from_graphs(cls, graphs: Sequence[RegionGraph]) -> "RegionFeatureBounds":
        _require_torch()
        if not graphs:
            raise ValueError("feature bounds require at least one graph")
        nodes = torch.cat([graph.node_features.detach().cpu() for graph in graphs], dim=0)
        nonempty_edges = [
            graph.edge_features.detach().cpu()
            for graph in graphs
            if graph.edge_count > 0
        ]
        if nonempty_edges:
            edges = torch.cat(nonempty_edges, dim=0)
            edge_min = edges.amin(dim=0)
            edge_max = edges.amax(dim=0)
        else:
            edge_min = torch.zeros(len(EDGE_FEATURE_NAMES))
            edge_max = torch.zeros(len(EDGE_FEATURE_NAMES))
        return cls(
            node_min=tuple(float(item) for item in nodes.amin(dim=0)),
            node_max=tuple(float(item) for item in nodes.amax(dim=0)),
            edge_min=tuple(float(item) for item in edge_min),
            edge_max=tuple(float(item) for item in edge_max),
        )

    def contains(self, graph: RegionGraph, *, margin: float = 0.05) -> bool:
        _require_torch()
        if margin < 0.0:
            raise ValueError("OOD margin must be non-negative")
        if not torch.isfinite(graph.node_features).all():
            return False
        if graph.edge_count and not torch.isfinite(graph.edge_features).all():
            return False
        return _tensor_inside_bounds(
            graph.node_features,
            self.node_min,
            self.node_max,
            margin,
        ) and (
            not graph.edge_count
            or _tensor_inside_bounds(
                graph.edge_features,
                self.edge_min,
                self.edge_max,
                margin,
            )
        )


@dataclass(frozen=True)
class GraphPolicyOutput:
    node_mean: Any
    edge_mean: Any
    node_log_std: Any
    edge_log_std: Any
    value: Any
    confidence: Any


_ModuleBase = nn.Module if nn is not None else object


class SharedRegionGraphActorCritic(_ModuleBase):
    """Shared node/edge actor-critic for arbitrary region graph sizes."""

    def __init__(
        self,
        *,
        hidden_dim: int = 64,
        message_passing_steps: int = 2,
        node_feature_dim: int = len(NODE_FEATURE_NAMES),
        edge_feature_dim: int = len(EDGE_FEATURE_NAMES),
    ) -> None:
        _require_torch()
        super().__init__()
        if int(hidden_dim) <= 0 or int(message_passing_steps) <= 0:
            raise ValueError("hidden_dim and message_passing_steps must be positive")
        if int(node_feature_dim) != len(NODE_FEATURE_NAMES):
            raise ValueError("unsupported node feature dimension")
        if int(edge_feature_dim) != len(EDGE_FEATURE_NAMES):
            raise ValueError("unsupported edge feature dimension")
        self.hidden_dim = int(hidden_dim)
        self.message_passing_steps = int(message_passing_steps)
        self.node_feature_dim = int(node_feature_dim)
        self.edge_feature_dim = int(edge_feature_dim)
        self.node_encoder = nn.Sequential(
            nn.Linear(self.node_feature_dim, self.hidden_dim),
            nn.Tanh(),
            nn.Linear(self.hidden_dim, self.hidden_dim),
            nn.Tanh(),
        )
        self.edge_encoder = nn.Sequential(
            nn.Linear(self.edge_feature_dim, self.hidden_dim),
            nn.Tanh(),
        )
        self.message_network = nn.Sequential(
            nn.Linear(self.hidden_dim * 3, self.hidden_dim),
            nn.Tanh(),
        )
        self.node_update = nn.Sequential(
            nn.Linear(self.hidden_dim * 2, self.hidden_dim),
            nn.Tanh(),
        )
        self.node_actor = nn.Linear(self.hidden_dim, NODE_ACTION_DIM)
        self.edge_actor = nn.Sequential(
            nn.Linear(self.hidden_dim * 3, self.hidden_dim),
            nn.Tanh(),
            nn.Linear(self.hidden_dim, EDGE_ACTION_DIM),
        )
        self.value_head = nn.Sequential(
            nn.Linear(self.hidden_dim, self.hidden_dim),
            nn.Tanh(),
            nn.Linear(self.hidden_dim, 1),
        )
        self.confidence_head = nn.Sequential(
            nn.Linear(self.hidden_dim, 1),
            nn.Sigmoid(),
        )
        self.node_log_std_parameter = nn.Parameter(torch.full((NODE_ACTION_DIM,), -0.7))
        self.edge_log_std_parameter = nn.Parameter(torch.full((EDGE_ACTION_DIM,), -0.7))

    def forward(self, graph: RegionGraph) -> GraphPolicyOutput:
        node_hidden = self.node_encoder(graph.node_features)
        edge_hidden = self.edge_encoder(graph.edge_features)
        if graph.edge_count:
            source = graph.edge_index[0]
            target = graph.edge_index[1]
            for _ in range(self.message_passing_steps):
                messages = self.message_network(
                    torch.cat(
                        (node_hidden[source], node_hidden[target], edge_hidden), dim=-1
                    )
                )
                aggregate = torch.zeros_like(node_hidden)
                aggregate.index_add_(0, target, messages)
                degree = torch.zeros(
                    graph.node_count,
                    dtype=node_hidden.dtype,
                    device=node_hidden.device,
                )
                degree.index_add_(0, target, torch.ones_like(target, dtype=node_hidden.dtype))
                aggregate = aggregate / degree.clamp_min(1.0).unsqueeze(-1)
                node_hidden = self.node_update(torch.cat((node_hidden, aggregate), dim=-1))
            edge_context = torch.cat(
                (node_hidden[source], node_hidden[target], edge_hidden), dim=-1
            )
            edge_mean = self.edge_actor(edge_context)
        else:
            for _ in range(self.message_passing_steps):
                node_hidden = self.node_update(
                    torch.cat((node_hidden, torch.zeros_like(node_hidden)), dim=-1)
                )
            edge_mean = torch.empty(
                (0, EDGE_ACTION_DIM),
                dtype=node_hidden.dtype,
                device=node_hidden.device,
            )
        pooled = node_hidden.mean(dim=0)
        node_mean = self.node_actor(node_hidden)
        return GraphPolicyOutput(
            node_mean=node_mean,
            edge_mean=edge_mean,
            node_log_std=self.node_log_std_parameter.expand_as(node_mean),
            edge_log_std=self.edge_log_std_parameter.expand_as(edge_mean),
            value=self.value_head(pooled).squeeze(-1),
            confidence=self.confidence_head(pooled).squeeze(-1),
        )


@dataclass(frozen=True)
class RegionPolicyTarget:
    node_continuous: Any
    node_binary: Any
    edge_continuous: Any


@dataclass(frozen=True)
class BehaviorCloningSample:
    graph: RegionGraph
    target: RegionPolicyTarget


def recommendation_to_policy_target(
    snapshot: RegionResourceSnapshot,
    graph: RegionGraph,
    recommendation: RegionResourceRecommendation,
) -> RegionPolicyTarget:
    _require_torch()
    actions = {action.region_id: action for action in recommendation.actions}
    nodes = snapshot.region_by_id
    continuous_rows: list[list[float]] = []
    binary_rows: list[list[float]] = []
    for region_id in graph.node_ids:
        action = actions[region_id]
        node = nodes[region_id]
        continuous_rows.append(
            [
                action.resource_quota_delta / max(1, node.available_resources),
                _logit(action.reserve_ratio),
                _logit(action.reconnaissance_priority),
            ]
        )
        binary_rows.append([float(action.hold), float(action.request_replan)])
    transfer_by_edge = {
        (transfer.edge_id, transfer.source_region_id, transfer.target_region_id): transfer
        for transfer in recommendation.transfers
    }
    edge_rows: list[list[float]] = []
    for edge_ref in graph.edge_refs:
        transfer = transfer_by_edge.get(
            (edge_ref.edge_id, edge_ref.source_region_id, edge_ref.target_region_id)
        )
        fraction = (
            transfer.resource_count / max(1, edge_ref.transferable_resources)
            if transfer is not None
            else 0.0
        )
        edge_rows.append([atanh(max(0.0, min(0.999, fraction)))])
    return RegionPolicyTarget(
        node_continuous=torch.tensor(
            continuous_rows,
            dtype=torch.float32,
            device=graph.node_features.device,
        ),
        node_binary=torch.tensor(
            binary_rows,
            dtype=torch.float32,
            device=graph.node_features.device,
        ),
        edge_continuous=torch.tensor(
            edge_rows,
            dtype=torch.float32,
            device=graph.node_features.device,
        ).reshape((-1, EDGE_ACTION_DIM)),
    )


def behavior_cloning_loss(
    model: SharedRegionGraphActorCritic,
    graph: RegionGraph,
    target: RegionPolicyTarget,
) -> Any:
    _require_torch()
    output = model(graph)
    continuous = torch.nn.functional.mse_loss(
        output.node_mean[:, :3], target.node_continuous
    )
    binary = torch.nn.functional.binary_cross_entropy_with_logits(
        output.node_mean[:, 3:], target.node_binary
    )
    edge = (
        torch.nn.functional.mse_loss(output.edge_mean, target.edge_continuous)
        if graph.edge_count
        else output.node_mean.sum() * 0.0
    )
    return continuous + binary + edge


def behavior_cloning_step(
    model: SharedRegionGraphActorCritic,
    optimizer: Any,
    samples: Sequence[BehaviorCloningSample],
    *,
    max_grad_norm: float = 1.0,
) -> float:
    _require_torch()
    if not samples:
        raise ValueError("behavior cloning requires at least one sample")
    optimizer.zero_grad()
    losses = [behavior_cloning_loss(model, sample.graph, sample.target) for sample in samples]
    loss = torch.stack(losses).mean()
    if not torch.isfinite(loss):
        raise NonFinitePolicyOutput("behavior_cloning_loss_non_finite")
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
    optimizer.step()
    if not _model_parameters_finite(model):
        raise NonFinitePolicyOutput("behavior_cloning_update_non_finite")
    return float(loss.detach().cpu())


@dataclass(frozen=True)
class RegionPPOTrainingFrame:
    """Verified offline frame for PPO rollout/return preprocessing.

    This is not a fabricated ``GraphPPOTransition``: old log probability,
    value, advantage, and return must still come from the rollout/trainer.
    """

    graph: RegionGraph
    target: RegionPolicyTarget
    reward: float
    frame_index: int
    timestamp_s: float
    target_recommendation: RegionResourceRecommendation
    recommendation: RegionResourceRecommendation | None = None

    def __post_init__(self) -> None:
        if not isfinite(float(self.reward)):
            raise ValueError("PPO training reward must be finite")


@dataclass(frozen=True)
class RegionPPOTrainingEpisode:
    source: RegionLearningEpisodeSource
    frames: tuple[RegionPPOTrainingFrame, ...]

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("PPO training episode must not be empty")


def load_region_behavior_cloning_samples(
    dataset: str | Path | LoadedRegionLearningDataset,
    *,
    split: RegionLearningSplit | str = RegionLearningSplit.TRAIN,
    device: Any = None,
    allow_dirty_source: bool = False,
    canonical_split_view: CanonicalRegionLearningDatasetView | None = None,
) -> tuple[BehaviorCloningSample, ...]:
    """Build BC samples only when every selected frame has a real target.

    The optional canonical view is an explicit, read-only split override for
    cross-module development.  Omitting it preserves the module-local split.
    """

    loaded = _resolve_region_learning_dataset(dataset)
    selected_dataset: LoadedRegionLearningDataset | CanonicalRegionLearningDatasetView
    selected_dataset = loaded
    if canonical_split_view is not None:
        canonical_split_view.assert_source(loaded)
        selected_dataset = canonical_split_view
    episodes = _training_episodes(
        selected_dataset,
        split=split,
        allow_dirty_source=allow_dirty_source,
        purpose="behavior_cloning",
    )
    samples: list[BehaviorCloningSample] = []
    for episode in episodes:
        for frame in episode.frames:
            if (
                frame.target.availability != RegionLearningAvailability.AVAILABLE
                or frame.target.recommendation is None
            ):
                raise RegionLearningDataUnavailableError(
                    f"target_unavailable:{episode.source.episode_id}:{frame.frame_index}"
                )
            graph = snapshot_to_region_graph(frame.snapshot, device=device)
            samples.append(
                BehaviorCloningSample(
                    graph=graph,
                    target=recommendation_to_policy_target(
                        frame.snapshot,
                        graph,
                        frame.target.recommendation,
                    ),
                )
            )
    return tuple(samples)


def load_region_ppo_training_episodes(
    dataset: str | Path | LoadedRegionLearningDataset,
    *,
    split: RegionLearningSplit | str = RegionLearningSplit.TRAIN,
    device: Any = None,
    allow_dirty_source: bool = False,
) -> tuple[RegionPPOTrainingEpisode, ...]:
    """Load complete PPO episodes without target or reward imputation."""

    loaded = _resolve_region_learning_dataset(dataset)
    episodes = _training_episodes(
        loaded,
        split=split,
        allow_dirty_source=allow_dirty_source,
        purpose="ppo",
    )
    result: list[RegionPPOTrainingEpisode] = []
    for episode in episodes:
        frames: list[RegionPPOTrainingFrame] = []
        for frame in episode.frames:
            if (
                frame.target.availability != RegionLearningAvailability.AVAILABLE
                or frame.target.recommendation is None
            ):
                raise RegionLearningDataUnavailableError(
                    f"target_unavailable:{episode.source.episode_id}:{frame.frame_index}"
                )
            if (
                frame.reward.availability != RegionLearningAvailability.AVAILABLE
                or frame.reward.value is None
            ):
                raise RegionLearningDataUnavailableError(
                    f"reward_unavailable:{episode.source.episode_id}:{frame.frame_index}"
                )
            graph = snapshot_to_region_graph(frame.snapshot, device=device)
            frames.append(
                RegionPPOTrainingFrame(
                    graph=graph,
                    target=recommendation_to_policy_target(
                        frame.snapshot,
                        graph,
                        frame.target.recommendation,
                    ),
                    reward=float(frame.reward.value),
                    frame_index=frame.frame_index,
                    timestamp_s=frame.timestamp_s,
                    target_recommendation=frame.target.recommendation,
                    recommendation=frame.recommendation,
                )
            )
        result.append(
            RegionPPOTrainingEpisode(source=episode.source, frames=tuple(frames))
        )
    return tuple(result)


@dataclass(frozen=True)
class GraphPolicyAction:
    node_action: Any
    edge_action: Any
    old_log_probability: float
    value: float


def sample_graph_policy_action(
    model: SharedRegionGraphActorCritic,
    graph: RegionGraph,
) -> GraphPolicyAction:
    _require_torch()
    with torch.no_grad():
        output = model(graph)
        node_distribution = torch.distributions.Normal(
            output.node_mean, output.node_log_std.exp()
        )
        edge_distribution = torch.distributions.Normal(
            output.edge_mean, output.edge_log_std.exp()
        )
        node_action = node_distribution.sample()
        edge_action = edge_distribution.sample()
        log_probability = node_distribution.log_prob(node_action).sum()
        if graph.edge_count:
            log_probability = log_probability + edge_distribution.log_prob(
                edge_action
            ).sum()
    return GraphPolicyAction(
        node_action=node_action.detach(),
        edge_action=edge_action.detach(),
        old_log_probability=float(log_probability.cpu()),
        value=float(output.value.cpu()),
    )


@dataclass(frozen=True)
class GraphPPOTransition:
    graph: RegionGraph
    action: GraphPolicyAction
    advantage: float
    return_value: float

    def __post_init__(self) -> None:
        if not isfinite(float(self.advantage)) or not isfinite(float(self.return_value)):
            raise ValueError("PPO advantage and return must be finite")


@dataclass(frozen=True)
class PPOUpdateMetrics:
    total_loss: float
    policy_loss: float
    value_loss: float
    entropy: float
    approximate_kl: float
    clip_fraction: float
    update_finite: bool


def native_clipped_ppo_update(
    model: SharedRegionGraphActorCritic,
    optimizer: Any,
    transitions: Sequence[GraphPPOTransition],
    *,
    clip_ratio: float = 0.20,
    value_coefficient: float = 0.5,
    entropy_coefficient: float = 0.01,
    max_grad_norm: float = 1.0,
    epochs: int = 1,
) -> PPOUpdateMetrics:
    """Perform a native variable-graph clipped PPO update without SB3/gym."""

    _require_torch()
    if not transitions:
        raise ValueError("PPO update requires at least one transition")
    if not 0.0 < clip_ratio < 1.0 or int(epochs) <= 0:
        raise ValueError("clip_ratio must be in (0, 1) and epochs must be positive")
    last_values: tuple[Any, ...] | None = None
    for _ in range(int(epochs)):
        policy_losses: list[Any] = []
        value_losses: list[Any] = []
        entropies: list[Any] = []
        kls: list[Any] = []
        clipped_flags: list[Any] = []
        for transition in transitions:
            output = model(transition.graph)
            node_distribution = torch.distributions.Normal(
                output.node_mean, output.node_log_std.exp()
            )
            edge_distribution = torch.distributions.Normal(
                output.edge_mean, output.edge_log_std.exp()
            )
            new_log_probability = node_distribution.log_prob(
                transition.action.node_action
            ).sum()
            entropy = node_distribution.entropy().sum()
            if transition.graph.edge_count:
                new_log_probability = new_log_probability + edge_distribution.log_prob(
                    transition.action.edge_action
                ).sum()
                entropy = entropy + edge_distribution.entropy().sum()
            old_log_probability = torch.as_tensor(
                transition.action.old_log_probability,
                dtype=new_log_probability.dtype,
                device=new_log_probability.device,
            )
            advantage = torch.as_tensor(
                transition.advantage,
                dtype=new_log_probability.dtype,
                device=new_log_probability.device,
            )
            ratio = torch.exp((new_log_probability - old_log_probability).clamp(-20, 20))
            unclipped = ratio * advantage
            clipped = ratio.clamp(1.0 - clip_ratio, 1.0 + clip_ratio) * advantage
            policy_losses.append(-torch.minimum(unclipped, clipped))
            target_value = torch.as_tensor(
                transition.return_value,
                dtype=output.value.dtype,
                device=output.value.device,
            )
            value_losses.append((output.value - target_value).pow(2))
            entropies.append(entropy)
            kls.append(old_log_probability - new_log_probability)
            clipped_flags.append((torch.abs(ratio - 1.0) > clip_ratio).float())
        policy_loss = torch.stack(policy_losses).mean()
        value_loss = torch.stack(value_losses).mean()
        entropy = torch.stack(entropies).mean()
        total_loss = (
            policy_loss
            + value_coefficient * value_loss
            - entropy_coefficient * entropy
        )
        if not torch.isfinite(total_loss):
            raise NonFinitePolicyOutput("ppo_loss_non_finite")
        optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
        optimizer.step()
        if not _model_parameters_finite(model):
            raise NonFinitePolicyOutput("ppo_update_non_finite")
        last_values = (
            total_loss.detach(),
            policy_loss.detach(),
            value_loss.detach(),
            entropy.detach(),
            torch.stack(kls).mean().detach(),
            torch.stack(clipped_flags).mean().detach(),
        )
    assert last_values is not None
    values = [float(item.cpu()) for item in last_values]
    return PPOUpdateMetrics(
        total_loss=values[0],
        policy_loss=values[1],
        value_loss=values[2],
        entropy=values[3],
        approximate_kl=values[4],
        clip_fraction=values[5],
        update_finite=all(isfinite(value) for value in values),
    )


@dataclass(frozen=True)
class RegionResourceRuntimeConfidenceGateConfig:
    mode: str = REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_MODE
    inconsistent_confidence_cap: float = (
        REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_INCONSISTENT_CAP
    )
    fixed_minimum_confidence: float = (
        REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_THRESHOLD
    )
    fixed_ood_margin: float = (
        REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_OOD_MARGIN
    )
    continuous_tolerance: float = (
        REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_CONTINUOUS_TOLERANCE
    )
    rule_policy_name: str = RuleRegionResourcePolicy.policy_name
    rule_policy_version: str = RuleRegionResourcePolicy.policy_version
    projector_name: str = DETERMINISTIC_RESOURCE_PROJECTOR_NAME
    projector_version: str = DETERMINISTIC_RESOURCE_PROJECTOR_VERSION
    projection_config: Mapping[str, Any] = field(
        default_factory=lambda: region_resource_projection_config_payload(
            RegionResourceProjectionConfig()
        )
    )
    rule_policy_config: Mapping[str, Any] = field(
        default_factory=lambda: region_resource_rule_policy_config_payload(
            RuleRegionResourcePolicyConfig()
        )
    )
    consistency_definition: Mapping[str, Any] = field(
        default_factory=runtime_confidence_gate_consistency_definition
    )
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema != REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_SCHEMA
            or self.mode != REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_MODE
        ):
            raise ValueError("unsupported runtime confidence gate")
        if (
            float(self.inconsistent_confidence_cap)
            != REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_INCONSISTENT_CAP
            or float(self.fixed_minimum_confidence)
            != REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_THRESHOLD
            or float(self.fixed_ood_margin)
            != REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_OOD_MARGIN
            or float(self.continuous_tolerance)
            != REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_CONTINUOUS_TOLERANCE
            or self.inconsistent_confidence_cap
            >= self.fixed_minimum_confidence
        ):
            raise ValueError("runtime confidence gate thresholds changed")
        if (
            self.rule_policy_name != RuleRegionResourcePolicy.policy_name
            or self.rule_policy_version != RuleRegionResourcePolicy.policy_version
            or self.projector_name != DETERMINISTIC_RESOURCE_PROJECTOR_NAME
            or self.projector_version
            != DETERMINISTIC_RESOURCE_PROJECTOR_VERSION
        ):
            raise ValueError("runtime confidence gate dependency changed")
        projection = _region_resource_projection_config_from_payload(
            self.projection_config
        )
        rule = _region_resource_rule_policy_config_from_payload(
            self.rule_policy_config
        )
        projection_payload = region_resource_projection_config_payload(
            projection
        )
        rule_payload = region_resource_rule_policy_config_payload(rule)
        if rule_payload["projection"] != projection_payload:
            raise ValueError(
                "runtime confidence gate rule/projector config mismatch"
            )
        object.__setattr__(
            self,
            "projection_config",
            projection_payload,
        )
        object.__setattr__(
            self,
            "rule_policy_config",
            rule_payload,
        )
        definition = dict(self.consistency_definition)
        if definition != runtime_confidence_gate_consistency_definition():
            raise ValueError(
                "runtime confidence gate consistency definition changed"
            )
        object.__setattr__(self, "consistency_definition", definition)
        expected = _canonical_sha256(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected:
            raise ValueError("runtime confidence gate content SHA256 mismatch")
        object.__setattr__(self, "content_sha256", expected)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "mode": self.mode,
            "inconsistent_confidence_cap": float(
                self.inconsistent_confidence_cap
            ),
            "fixed_minimum_confidence": float(
                self.fixed_minimum_confidence
            ),
            "fixed_ood_margin": float(self.fixed_ood_margin),
            "continuous_tolerance": float(self.continuous_tolerance),
            "rule_policy_name": self.rule_policy_name,
            "rule_policy_version": self.rule_policy_version,
            "projector_name": self.projector_name,
            "projector_version": self.projector_version,
            "projection_config": dict(self.projection_config),
            "rule_policy_config": dict(self.rule_policy_config),
            "consistency_definition": dict(self.consistency_definition),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.content_dict(),
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceRuntimeConfidenceGateConfig":
        expected = set(cls.__dataclass_fields__)
        if set(value) != expected:
            raise ValueError("runtime confidence gate keys mismatch")
        return cls(**dict(value))

    @classmethod
    def from_runtime_context(
        cls,
        *,
        projector: DeterministicResourceProjector,
        rule_policy: RuleRegionResourcePolicy,
        fixed_minimum_confidence: float = (
            REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_THRESHOLD
        ),
        fixed_ood_margin: float = (
            REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_FIXED_OOD_MARGIN
        ),
    ) -> "RegionResourceRuntimeConfidenceGateConfig":
        if rule_policy.projector is not projector:
            raise RuntimeConfidenceGateContextError(
                "rule_policy_projector_identity_mismatch"
            )
        return cls(
            fixed_minimum_confidence=fixed_minimum_confidence,
            fixed_ood_margin=fixed_ood_margin,
            projection_config=region_resource_projection_config_payload(
                projector.config
            ),
            rule_policy_config=region_resource_rule_policy_config_payload(
                rule_policy.config
            ),
        )

    def validate_runtime_context(
        self,
        *,
        projector: DeterministicResourceProjector,
        rule_policy: RuleRegionResourcePolicy,
        minimum_confidence: float,
        ood_margin: float,
    ) -> None:
        mismatches: list[str] = []
        if rule_policy.projector is not projector:
            mismatches.append("rule_policy_projector_identity")
        if (
            region_resource_projection_config_payload(projector.config)
            != self.projection_config
        ):
            mismatches.append("projection_config")
        if (
            region_resource_rule_policy_config_payload(rule_policy.config)
            != self.rule_policy_config
        ):
            mismatches.append("rule_policy_config")
        if float(minimum_confidence) != self.fixed_minimum_confidence:
            mismatches.append("minimum_confidence")
        if float(ood_margin) != self.fixed_ood_margin:
            mismatches.append("ood_margin")
        if mismatches:
            raise RuntimeConfidenceGateContextError(
                "runtime_confidence_gate_context_mismatch:"
                + ",".join(mismatches)
            )


@dataclass(frozen=True)
class RegionResourceActionConsistency:
    action_consistent: bool
    region_set_match: bool
    quota_error_maximum: float
    reserve_error_maximum: float
    reconnaissance_error_maximum: float
    binary_mismatch_count: int
    transfer_multiset_match: bool


@dataclass(frozen=True)
class RegionResourceRuntimeConfidenceGateEvaluation:
    gate_applied: bool
    raw_confidence: float
    effective_confidence: float
    formal_decision_digest: str | None
    action_consistency: RegionResourceActionConsistency
    raw_recommendation: RegionResourceRecommendation
    effective_recommendation: RegionResourceRecommendation
    projected_candidate: RegionResourceRecommendation
    reference_recommendation: RegionResourceRecommendation


def evaluate_region_resource_action_consistency(
    snapshot: RegionResourceSnapshot,
    candidate: RegionResourceRecommendation,
    reference: RegionResourceRecommendation,
    *,
    continuous_tolerance: float = (
        REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_CONTINUOUS_TOLERANCE
    ),
) -> RegionResourceActionConsistency:
    """Compare two projected regional actions without truth or outcome data."""

    if (
        float(continuous_tolerance)
        != REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_CONTINUOUS_TOLERANCE
    ):
        raise ValueError("runtime action-consistency tolerance changed")
    candidate_actions = {
        item.region_id: item for item in candidate.actions
    }
    reference_actions = {
        item.region_id: item for item in reference.actions
    }
    expected_regions = set(snapshot.region_by_id)
    region_set_match = bool(
        set(candidate_actions) == expected_regions
        and set(reference_actions) == expected_regions
    )
    quota_errors: list[float] = []
    reserve_errors: list[float] = []
    reconnaissance_errors: list[float] = []
    binary_mismatch_count = 0
    if region_set_match:
        for region_id in sorted(expected_regions):
            node = snapshot.region_by_id[region_id]
            observed = candidate_actions[region_id]
            expected = reference_actions[region_id]
            quota_errors.append(
                abs(
                    observed.resource_quota_delta
                    - expected.resource_quota_delta
                )
                / max(1, node.available_resources)
            )
            reserve_errors.append(
                abs(observed.reserve_ratio - expected.reserve_ratio)
            )
            reconnaissance_errors.append(
                abs(
                    observed.reconnaissance_priority
                    - expected.reconnaissance_priority
                )
            )
            binary_mismatch_count += int(observed.hold != expected.hold)
            binary_mismatch_count += int(
                observed.request_replan != expected.request_replan
            )
    else:
        quota_errors.append(1.0)
        reserve_errors.append(1.0)
        reconnaissance_errors.append(1.0)
        binary_mismatch_count = max(
            1,
            2 * len(expected_regions),
        )
    candidate_transfers = sorted(
        (
            item.edge_id,
            item.source_region_id,
            item.target_region_id,
            int(item.resource_count),
        )
        for item in candidate.transfers
    )
    reference_transfers = sorted(
        (
            item.edge_id,
            item.source_region_id,
            item.target_region_id,
            int(item.resource_count),
        )
        for item in reference.transfers
    )
    transfer_multiset_match = candidate_transfers == reference_transfers
    quota_max = max(quota_errors, default=0.0)
    reserve_max = max(reserve_errors, default=0.0)
    reconnaissance_max = max(reconnaissance_errors, default=0.0)
    consistent = bool(
        region_set_match
        and quota_max <= continuous_tolerance
        and reserve_max <= continuous_tolerance
        and reconnaissance_max <= continuous_tolerance
        and binary_mismatch_count == 0
        and transfer_multiset_match
    )
    return RegionResourceActionConsistency(
        action_consistent=consistent,
        region_set_match=region_set_match,
        quota_error_maximum=quota_max,
        reserve_error_maximum=reserve_max,
        reconnaissance_error_maximum=reconnaissance_max,
        binary_mismatch_count=binary_mismatch_count,
        transfer_multiset_match=transfer_multiset_match,
    )


def apply_region_resource_runtime_confidence_gate(
    snapshot: RegionResourceSnapshot,
    recommendation: RegionResourceRecommendation,
    gate: RegionResourceRuntimeConfidenceGateConfig,
    *,
    projector: DeterministicResourceProjector,
    rule_policy: RuleRegionResourcePolicy,
    formal_decision: RegionalFailoverDecision | None,
    minimum_confidence: float,
    ood_margin: float,
) -> RegionResourceRuntimeConfidenceGateEvaluation:
    """Apply the bundle-bound truth-free gate before confidence thresholding."""

    gate.validate_runtime_context(
        projector=projector,
        rule_policy=rule_policy,
        minimum_confidence=minimum_confidence,
        ood_margin=ood_margin,
    )
    if (
        rule_policy.policy_name != gate.rule_policy_name
        or rule_policy.policy_version != gate.rule_policy_version
    ):
        raise RuntimeConfidenceGateContextError(
            "runtime_confidence_gate_rule_policy_identity_mismatch"
        )
    projected = projector.project(
        snapshot,
        recommendation,
        formal_decision=formal_decision,
    )
    reference = rule_policy.recommend(
        snapshot,
        formal_decision=formal_decision,
    )
    consistency = evaluate_region_resource_action_consistency(
        snapshot,
        projected,
        reference,
        continuous_tolerance=gate.continuous_tolerance,
    )
    raw_confidence = float(recommendation.confidence)
    effective_confidence = (
        raw_confidence
        if consistency.action_consistent
        else min(raw_confidence, gate.inconsistent_confidence_cap)
    )
    effective = replace(
        projected,
        confidence=effective_confidence,
        fallback_reason=(
            projected.fallback_reason
            if consistency.action_consistent
            else "runtime_rule_action_consistency_gate_rejected"
        ),
    )
    return RegionResourceRuntimeConfidenceGateEvaluation(
        gate_applied=True,
        raw_confidence=raw_confidence,
        effective_confidence=effective_confidence,
        formal_decision_digest=formal_decision_digest(formal_decision),
        action_consistency=consistency,
        raw_recommendation=recommendation,
        effective_recommendation=effective,
        projected_candidate=projected,
        reference_recommendation=reference,
    )


@dataclass(frozen=True)
class RegionResourceModelManifest:
    model_version: str
    hidden_dim: int
    message_passing_steps: int
    state_dict_file: str
    state_dict_sha256: str
    feature_bounds: RegionFeatureBounds
    training_groups: tuple[tuple[str, int], ...]
    created_at_utc: str
    training_dataset_available: bool = False
    training_dataset_schema: str | None = None
    training_dataset_sha256: str | None = None
    training_split_sha256: str | None = None
    training_manifest_file: str | None = None
    training_manifest_sha256: str | None = None
    lifecycle_stage: str = MODEL_LIFECYCLE_DEVELOPMENT
    maximum_advisor_mode: str = MODEL_MAXIMUM_MODE_SHADOW
    reward_evidence_available: bool = False
    final_holdout_seed_count: int = 0
    action_diversity_sufficient: bool = False
    strategy_capability_claim_allowed: bool = False
    target_action_inventory: Mapping[str, int] = field(default_factory=dict)
    admission_reasons: tuple[str, ...] = (
        "development_bundle",
        "reward_evidence_unavailable",
        "final_holdout_not_completed",
    )
    runtime_confidence_gate: (
        RegionResourceRuntimeConfidenceGateConfig | None
    ) = None
    architecture: str = REGION_GRAPH_ARCHITECTURE
    feature_schema: str = REGION_RESOURCE_FEATURE_SCHEMA
    node_feature_dim: int = len(NODE_FEATURE_NAMES)
    edge_feature_dim: int = len(EDGE_FEATURE_NAMES)
    node_action_dim: int = NODE_ACTION_DIM
    edge_action_dim: int = EDGE_ACTION_DIM
    schema: str = REGION_RESOURCE_MODEL_BUNDLE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_MODEL_BUNDLE_SCHEMA:
            raise ValueError("unsupported model bundle schema")
        if self.architecture != REGION_GRAPH_ARCHITECTURE:
            raise ValueError("unsupported graph model architecture")
        if self.feature_schema != REGION_RESOURCE_FEATURE_SCHEMA:
            raise ValueError("unsupported graph feature schema")
        if not self.model_version or not self.state_dict_file or not self.created_at_utc:
            raise ValueError("model bundle identity must not be empty")
        if Path(self.state_dict_file).name != self.state_dict_file:
            raise ValueError("state_dict_file must be a bundle-local basename")
        if len(self.state_dict_sha256) != 64:
            raise ValueError("state_dict_sha256 must be a SHA256 hex digest")
        if self.node_feature_dim != len(NODE_FEATURE_NAMES):
            raise ValueError("manifest node feature dimension mismatch")
        if self.edge_feature_dim != len(EDGE_FEATURE_NAMES):
            raise ValueError("manifest edge feature dimension mismatch")
        if self.node_action_dim != NODE_ACTION_DIM or self.edge_action_dim != EDGE_ACTION_DIM:
            raise ValueError("manifest action dimension mismatch")
        if self.hidden_dim <= 0 or self.message_passing_steps <= 0:
            raise ValueError("manifest model dimensions must be positive")
        if self.lifecycle_stage not in {
            MODEL_LIFECYCLE_DEVELOPMENT,
            MODEL_LIFECYCLE_QUALIFIED,
        }:
            raise ValueError("unsupported model lifecycle stage")
        if self.maximum_advisor_mode not in {
            MODEL_MAXIMUM_MODE_SHADOW,
            MODEL_MAXIMUM_MODE_ASSIST,
        }:
            raise ValueError("unsupported maximum advisor mode")
        if (
            self.lifecycle_stage != MODEL_LIFECYCLE_DEVELOPMENT
            or self.maximum_advisor_mode != MODEL_MAXIMUM_MODE_SHADOW
        ):
            raise ValueError(
                "model bundle v2 is development/shadow only; "
                "assist requires an independent evidence-bound promotion contract"
            )
        if type(self.reward_evidence_available) is not bool:
            raise ValueError("reward_evidence_available must be a boolean")
        if type(self.action_diversity_sufficient) is not bool:
            raise ValueError("action_diversity_sufficient must be a boolean")
        if type(self.strategy_capability_claim_allowed) is not bool:
            raise ValueError(
                "strategy_capability_claim_allowed must be a boolean"
            )
        if int(self.final_holdout_seed_count) < 0:
            raise ValueError("final_holdout_seed_count must be non-negative")
        inventory = {
            str(name): int(count)
            for name, count in self.target_action_inventory.items()
        }
        required_inventory_fields = {
            "action_count",
            "resource_quota_nonzero_count",
            "transfer_count",
            "hold_true_count",
            "request_replan_true_count",
        }
        if inventory and set(inventory) != required_inventory_fields:
            raise ValueError("target action inventory fields are incomplete")
        if any(count < 0 for count in inventory.values()):
            raise ValueError("target action inventory counts must be non-negative")
        for name in (
            "resource_quota_nonzero_count",
            "hold_true_count",
            "request_replan_true_count",
        ):
            if inventory and inventory[name] > inventory["action_count"]:
                raise ValueError(f"{name} exceeds target action count")
        if self.action_diversity_sufficient and not inventory:
            raise ValueError("action diversity evidence requires a target inventory")
        if self.strategy_capability_claim_allowed and not self.action_diversity_sufficient:
            raise ValueError(
                "strategy capability claims require sufficient action diversity"
            )
        object.__setattr__(self, "target_action_inventory", inventory)
        reasons = tuple(sorted({str(item) for item in self.admission_reasons if str(item)}))
        object.__setattr__(self, "admission_reasons", reasons)
        runtime_gate = self.runtime_confidence_gate
        if runtime_gate is not None and not isinstance(
            runtime_gate, RegionResourceRuntimeConfidenceGateConfig
        ):
            runtime_gate = RegionResourceRuntimeConfidenceGateConfig.from_dict(
                runtime_gate
            )
        object.__setattr__(self, "runtime_confidence_gate", runtime_gate)
        groups = tuple(
            sorted({(str(item[0]), int(item[1])) for item in self.training_groups})
        )
        object.__setattr__(self, "training_groups", groups)
        provenance = (
            self.training_dataset_schema,
            self.training_dataset_sha256,
            self.training_split_sha256,
            self.training_manifest_file,
            self.training_manifest_sha256,
        )
        if self.training_dataset_available:
            if any(value is None for value in provenance):
                raise ValueError("available training dataset provenance must be complete")
            if self.training_dataset_schema != REGION_LEARNING_DATASET_SCHEMA:
                raise ValueError("unsupported training dataset schema")
            if Path(str(self.training_manifest_file)).name != self.training_manifest_file:
                raise ValueError("training_manifest_file must be a bundle-local basename")
            for name, digest in (
                ("training_dataset_sha256", self.training_dataset_sha256),
                ("training_split_sha256", self.training_split_sha256),
                ("training_manifest_sha256", self.training_manifest_sha256),
            ):
                if digest is None or len(digest) != 64 or not all(
                    character in "0123456789abcdefABCDEF" for character in digest
                ):
                    raise ValueError(f"{name} must be a SHA256 hex digest")
        elif any(value is not None for value in provenance):
            raise ValueError("unavailable training dataset must not carry provenance")

    @property
    def assist_admitted(self) -> bool:
        """Bundle v2 has no independently bound assist-admission evidence."""

        return False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "architecture": self.architecture,
            "model_version": self.model_version,
            "feature_schema": self.feature_schema,
            "node_feature_dim": self.node_feature_dim,
            "edge_feature_dim": self.edge_feature_dim,
            "node_action_dim": self.node_action_dim,
            "edge_action_dim": self.edge_action_dim,
            "hidden_dim": self.hidden_dim,
            "message_passing_steps": self.message_passing_steps,
            "state_dict_file": self.state_dict_file,
            "state_dict_sha256": self.state_dict_sha256,
            "feature_bounds": self.feature_bounds.to_dict(),
            "training_groups": [
                {"scenario_id": scenario_id, "seed": seed}
                for scenario_id, seed in self.training_groups
            ],
            "training_dataset_available": self.training_dataset_available,
            "training_dataset_schema": self.training_dataset_schema,
            "training_dataset_sha256": self.training_dataset_sha256,
            "training_split_sha256": self.training_split_sha256,
            "training_manifest_file": self.training_manifest_file,
            "training_manifest_sha256": self.training_manifest_sha256,
            "lifecycle_stage": self.lifecycle_stage,
            "maximum_advisor_mode": self.maximum_advisor_mode,
            "reward_evidence_available": self.reward_evidence_available,
            "final_holdout_seed_count": int(self.final_holdout_seed_count),
            "action_diversity_sufficient": self.action_diversity_sufficient,
            "strategy_capability_claim_allowed": (
                self.strategy_capability_claim_allowed
            ),
            "target_action_inventory": dict(self.target_action_inventory),
            "admission_reasons": list(self.admission_reasons),
            "created_at_utc": self.created_at_utc,
        }
        if self.runtime_confidence_gate is not None:
            payload["runtime_confidence_gate"] = (
                self.runtime_confidence_gate.to_dict()
            )
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionResourceModelManifest":
        payload = dict(value)
        payload["feature_bounds"] = RegionFeatureBounds.from_dict(
            payload["feature_bounds"]
        )
        payload["training_groups"] = tuple(
            (str(item["scenario_id"]), int(item["seed"]))
            for item in payload.get("training_groups", ())
        )
        payload["admission_reasons"] = tuple(payload.get("admission_reasons", ()))
        if payload.get("runtime_confidence_gate") is not None:
            payload["runtime_confidence_gate"] = (
                RegionResourceRuntimeConfidenceGateConfig.from_dict(
                    payload["runtime_confidence_gate"]
                )
            )
        return cls(**payload)


@dataclass(frozen=True)
class LoadedRegionResourceModelBundle:
    model: SharedRegionGraphActorCritic
    manifest: RegionResourceModelManifest
    bundle_dir: Path
    training_dataset_manifest: RegionLearningDatasetManifest | None = None


def save_region_resource_model_bundle(
    model: SharedRegionGraphActorCritic,
    bundle_dir: str | Path,
    *,
    model_version: str,
    training_graphs: Sequence[RegionGraph],
    training_groups: Iterable[tuple[str, int]] = (),
    created_at_utc: str,
    training_dataset_manifest: RegionLearningDatasetManifest | None = None,
    lifecycle_stage: str = MODEL_LIFECYCLE_DEVELOPMENT,
    maximum_advisor_mode: str = MODEL_MAXIMUM_MODE_SHADOW,
    reward_evidence_available: bool = False,
    final_holdout_seed_count: int = 0,
    action_diversity_sufficient: bool = False,
    strategy_capability_claim_allowed: bool = False,
    target_action_inventory: Mapping[str, int] | None = None,
    runtime_confidence_gate: (
        RegionResourceRuntimeConfidenceGateConfig | None
    ) = None,
    admission_reasons: Sequence[str] = (
        "development_bundle",
        "reward_evidence_unavailable",
        "final_holdout_not_completed",
    ),
) -> RegionResourceModelManifest:
    _require_torch()
    if (
        lifecycle_stage != MODEL_LIFECYCLE_DEVELOPMENT
        or maximum_advisor_mode != MODEL_MAXIMUM_MODE_SHADOW
    ):
        raise ValueError(
            "model bundle writer only emits development/shadow bundles; "
            "assist requires an independent evidence-bound promotion contract"
        )
    destination = Path(bundle_dir)
    destination.mkdir(parents=True, exist_ok=True)
    state_path = destination / "state_dict.pt"
    temporary_state_path = destination / "state_dict.pt.tmp"
    torch.save(model.state_dict(), temporary_state_path)
    temporary_state_path.replace(state_path)
    digest = _sha256_file(state_path)
    resolved_training_groups = tuple(training_groups)
    training_manifest_file: str | None = None
    training_manifest_sha256: str | None = None
    if training_dataset_manifest is not None:
        dataset_training_groups = tuple(
            sorted(
                {
                    (episode.source.scenario_id, int(episode.source.seed))
                    for episode in training_dataset_manifest.episodes
                    if episode.split == RegionLearningSplit.TRAIN
                }
            )
        )
        supplied_groups = tuple(
            sorted(
                {
                    (str(scenario), int(seed))
                    for scenario, seed in resolved_training_groups
                }
            )
        )
        if supplied_groups and supplied_groups != dataset_training_groups:
            raise ValueError("training_groups do not match dataset train split")
        resolved_training_groups = dataset_training_groups
        training_manifest_path = destination / "training_dataset_manifest.json"
        temporary_training_manifest_path = (
            destination / "training_dataset_manifest.json.tmp"
        )
        temporary_training_manifest_path.write_text(
            json.dumps(
                training_dataset_manifest.to_dict(),
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary_training_manifest_path.replace(training_manifest_path)
        training_manifest_file = training_manifest_path.name
        training_manifest_sha256 = _sha256_file(training_manifest_path)
    manifest = RegionResourceModelManifest(
        model_version=model_version,
        hidden_dim=model.hidden_dim,
        message_passing_steps=model.message_passing_steps,
        state_dict_file=state_path.name,
        state_dict_sha256=digest,
        feature_bounds=RegionFeatureBounds.from_graphs(training_graphs),
        training_groups=resolved_training_groups,
        created_at_utc=created_at_utc,
        training_dataset_available=training_dataset_manifest is not None,
        training_dataset_schema=(
            training_dataset_manifest.schema
            if training_dataset_manifest is not None
            else None
        ),
        training_dataset_sha256=(
            training_dataset_manifest.dataset_sha256
            if training_dataset_manifest is not None
            else None
        ),
        training_split_sha256=(
            training_dataset_manifest.split.split_sha256
            if training_dataset_manifest is not None
            else None
        ),
        training_manifest_file=training_manifest_file,
        training_manifest_sha256=training_manifest_sha256,
        lifecycle_stage=lifecycle_stage,
        maximum_advisor_mode=maximum_advisor_mode,
        reward_evidence_available=reward_evidence_available,
        final_holdout_seed_count=final_holdout_seed_count,
        action_diversity_sufficient=action_diversity_sufficient,
        strategy_capability_claim_allowed=strategy_capability_claim_allowed,
        target_action_inventory=dict(target_action_inventory or {}),
        admission_reasons=tuple(admission_reasons),
        runtime_confidence_gate=runtime_confidence_gate,
    )
    manifest_path = destination / "manifest.json"
    temporary_manifest_path = destination / "manifest.json.tmp"
    temporary_manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_manifest_path.replace(manifest_path)
    return manifest


def load_region_resource_model_bundle(
    bundle_dir: str | Path,
    *,
    expected_model_version: str | None = None,
    expected_state_dict_sha256: str | None = None,
    map_location: Any = "cpu",
    require_training_dataset_manifest: bool = False,
) -> LoadedRegionResourceModelBundle:
    _require_torch()
    source = Path(bundle_dir)
    try:
        manifest_payload = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        manifest = RegionResourceModelManifest.from_dict(manifest_payload)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ModelBundleValidationError(f"manifest_invalid:{type(exc).__name__}") from exc
    if expected_model_version is not None and manifest.model_version != expected_model_version:
        raise ModelBundleValidationError("model_version_mismatch")
    if (
        expected_state_dict_sha256 is not None
        and manifest.state_dict_sha256 != expected_state_dict_sha256
    ):
        raise ModelBundleValidationError("expected_sha256_mismatch")
    state_path = source / manifest.state_dict_file
    try:
        actual_digest = _sha256_file(state_path)
    except OSError as exc:
        raise ModelBundleValidationError("state_dict_missing") from exc
    if actual_digest != manifest.state_dict_sha256:
        raise ModelBundleValidationError("state_dict_sha256_mismatch")
    training_dataset_manifest: RegionLearningDatasetManifest | None = None
    if manifest.training_dataset_available:
        training_manifest_path = source / str(manifest.training_manifest_file)
        try:
            actual_training_digest = _sha256_file(training_manifest_path)
            if actual_training_digest != manifest.training_manifest_sha256:
                raise ModelBundleValidationError("training_manifest_sha256_mismatch")
            training_payload = json.loads(
                training_manifest_path.read_text(encoding="utf-8")
            )
            training_dataset_manifest = RegionLearningDatasetManifest.from_dict(
                training_payload
            )
        except ModelBundleValidationError:
            raise
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ModelBundleValidationError(
                f"training_manifest_invalid:{type(exc).__name__}"
            ) from exc
        if (
            training_dataset_manifest.dataset_sha256
            != manifest.training_dataset_sha256
            or training_dataset_manifest.split.split_sha256
            != manifest.training_split_sha256
        ):
            raise ModelBundleValidationError("training_dataset_provenance_mismatch")
        embedded_training_groups = tuple(
            sorted(
                {
                    (episode.source.scenario_id, int(episode.source.seed))
                    for episode in training_dataset_manifest.episodes
                    if episode.split == RegionLearningSplit.TRAIN
                }
            )
        )
        if embedded_training_groups != manifest.training_groups:
            raise ModelBundleValidationError("training_groups_provenance_mismatch")
    elif require_training_dataset_manifest:
        raise ModelBundleValidationError("training_dataset_manifest_unavailable")
    model = SharedRegionGraphActorCritic(
        hidden_dim=manifest.hidden_dim,
        message_passing_steps=manifest.message_passing_steps,
        node_feature_dim=manifest.node_feature_dim,
        edge_feature_dim=manifest.edge_feature_dim,
    )
    try:
        state_dict = torch.load(state_path, map_location=map_location, weights_only=True)
        model.load_state_dict(state_dict, strict=True)
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        raise ModelBundleValidationError(f"state_dict_invalid:{type(exc).__name__}") from exc
    model.eval()
    return LoadedRegionResourceModelBundle(
        model=model,
        manifest=manifest,
        bundle_dir=source,
        training_dataset_manifest=training_dataset_manifest,
    )


class LearnedRegionResourcePolicy:
    def __init__(
        self,
        model: SharedRegionGraphActorCritic,
        manifest: RegionResourceModelManifest,
    ) -> None:
        self.model = model
        self.manifest = manifest

    def recommend_raw(
        self, snapshot: RegionResourceSnapshot
    ) -> RegionResourceRecommendation:
        """Return model output without implying Advisor gate semantics."""

        return self._recommend_uncalibrated(snapshot)

    def recommend_with_runtime_confidence_gate(
        self,
        snapshot: RegionResourceSnapshot,
        *,
        projector: DeterministicResourceProjector,
        rule_policy: RuleRegionResourcePolicy,
        formal_decision: RegionalFailoverDecision | None,
        minimum_confidence: float,
        ood_margin: float,
    ) -> tuple[
        RegionResourceRecommendation,
        RegionResourceRuntimeConfidenceGateEvaluation | None,
    ]:
        gate = self.manifest.runtime_confidence_gate
        if gate is None:
            return self._recommend_uncalibrated(snapshot), None
        gate.validate_runtime_context(
            projector=projector,
            rule_policy=rule_policy,
            minimum_confidence=minimum_confidence,
            ood_margin=ood_margin,
        )
        raw = self._recommend_uncalibrated(snapshot)
        evaluation = apply_region_resource_runtime_confidence_gate(
            snapshot,
            raw,
            gate,
            projector=projector,
            rule_policy=rule_policy,
            formal_decision=formal_decision,
            minimum_confidence=minimum_confidence,
            ood_margin=ood_margin,
        )
        return evaluation.effective_recommendation, evaluation

    def _recommend_uncalibrated(
        self, snapshot: RegionResourceSnapshot
    ) -> RegionResourceRecommendation:
        graph = snapshot_to_region_graph(snapshot, device=_model_device(self.model))
        with torch.no_grad():
            output = self.model(graph)
        _validate_policy_output(output)
        confidence = float(output.confidence.detach().cpu())
        node_values = output.node_mean.detach().cpu()
        edge_values = output.edge_mean.detach().cpu()
        node_by_id = snapshot.region_by_id
        transfers: list[RegionTransferSuggestion] = []
        for index, edge_ref in enumerate(graph.edge_refs):
            fraction = max(0.0, float(torch.tanh(edge_values[index, 0])))
            count = min(
                edge_ref.transferable_resources,
                int(round(fraction * edge_ref.transferable_resources)),
            )
            if count <= 0:
                continue
            transfers.append(
                RegionTransferSuggestion(
                    source_region_id=edge_ref.source_region_id,
                    target_region_id=edge_ref.target_region_id,
                    resource_count=count,
                    edge_id=edge_ref.edge_id,
                    expected_transfer_time_s=edge_ref.transfer_time_s,
                    reasons=("learned_graph_transfer",),
                )
            )
        deltas = {region_id: 0 for region_id in graph.node_ids}
        for transfer in transfers:
            deltas[transfer.source_region_id] -= transfer.resource_count
            deltas[transfer.target_region_id] += transfer.resource_count
        actions: list[RegionResourceAction] = []
        for index, region_id in enumerate(graph.node_ids):
            node = node_by_id[region_id]
            actions.append(
                RegionResourceAction(
                    region_id=region_id,
                    resource_quota_delta=deltas[region_id],
                    reserve_ratio=float(torch.sigmoid(node_values[index, 1])),
                    reconnaissance_priority=float(torch.sigmoid(node_values[index, 2])),
                    hold=bool(torch.sigmoid(node_values[index, 3]) >= 0.5),
                    request_replan=bool(torch.sigmoid(node_values[index, 4]) >= 0.5),
                    expected_owner_id=node.current_owner_id,
                    expected_owner_layer=node.current_owner_layer,
                    expected_plan_id=node.plan_id,
                    expected_plan_version=node.plan_version,
                    expected_epoch=node.epoch,
                    expected_lease_expires_at_s=node.lease_expires_at_s,
                    reasons=("learned_graph_node_action",),
                )
            )
        return RegionResourceRecommendation(
            snapshot_id=snapshot.snapshot_id,
            scenario_id=snapshot.scenario_id,
            scenario_version=snapshot.scenario_version,
            seed=snapshot.seed,
            authority_digest=snapshot.authority_digest,
            created_at_s=snapshot.timestamp_s,
            policy_name=REGION_GRAPH_ARCHITECTURE,
            policy_version=self.manifest.model_version,
            source=RecommendationSource.LEARNED,
            confidence=confidence,
            actions=tuple(actions),
            transfers=tuple(transfers),
            projected=False,
            model_sha256=self.manifest.state_dict_sha256,
            planning_authority_digest=snapshot.planning_authority_digest,
        )

    def is_ood(self, snapshot: RegionResourceSnapshot, *, margin: float) -> bool:
        graph = snapshot_to_region_graph(snapshot, device=_model_device(self.model))
        return not self.manifest.feature_bounds.contains(graph, margin=margin)


@dataclass(frozen=True)
class RegionResourceAdvisorConfig:
    mode: AdvisorMode | str = AdvisorMode.DISABLED
    inference_timeout_s: float = 0.050
    minimum_confidence: float = 0.60
    ood_margin: float = 0.05
    minimum_unseen_seeds: int = 20
    projection: RegionResourceProjectionConfig = field(
        default_factory=RegionResourceProjectionConfig
    )

    def __post_init__(self) -> None:
        mode = self.mode if isinstance(self.mode, AdvisorMode) else AdvisorMode(str(self.mode))
        object.__setattr__(self, "mode", mode)
        if not isfinite(float(self.inference_timeout_s)) or self.inference_timeout_s < 0.0:
            raise ValueError("inference_timeout_s must be finite and non-negative")
        if not 0.0 <= float(self.minimum_confidence) <= 1.0:
            raise ValueError("minimum_confidence must be in [0, 1]")
        if not isfinite(float(self.ood_margin)) or self.ood_margin < 0.0:
            raise ValueError("ood_margin must be finite and non-negative")
        if int(self.minimum_unseen_seeds) <= 0:
            raise ValueError("minimum_unseen_seeds must be positive")


@dataclass(frozen=True)
class RegionResourceRuntimeConfidenceGateDiagnostic:
    model_raw_inference_executed: bool
    gate_applied: bool
    action_consistent: bool | None
    raw_confidence: float | None
    effective_confidence: float | None
    candidate_permitted_after_gate: bool
    rule_fallback_due_to_gate: bool
    gate_content_sha256: str
    formal_decision_digest: str | None
    fallback_reason: str | None
    truth_identifier_use_count: int = 0
    schema: str = (
        REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_DIAGNOSTIC_SCHEMA
    )

    def __post_init__(self) -> None:
        if (
            self.schema
            != REGION_RESOURCE_RUNTIME_CONFIDENCE_GATE_DIAGNOSTIC_SCHEMA
        ):
            raise ValueError(
                "unsupported runtime confidence gate diagnostic schema"
            )
        for name in (
            "model_raw_inference_executed",
            "gate_applied",
            "candidate_permitted_after_gate",
            "rule_fallback_due_to_gate",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if (
            len(self.gate_content_sha256) != 64
            or not all(
                character in "0123456789abcdefABCDEF"
                for character in self.gate_content_sha256
            )
        ):
            raise ValueError(
                "gate_content_sha256 must be a SHA256 hex digest"
            )
        confidence_values = (
            self.raw_confidence,
            self.effective_confidence,
        )
        if (confidence_values[0] is None) != (
            confidence_values[1] is None
        ):
            raise ValueError(
                "runtime gate confidence values must be jointly available"
            )
        if any(
            value is not None
            and (
                not isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0
            )
            for value in confidence_values
        ):
            raise ValueError(
                "runtime gate confidence values must be finite probabilities"
            )
        if self.gate_applied and (
            not self.model_raw_inference_executed
            or self.action_consistent is None
            or self.raw_confidence is None
        ):
            raise ValueError(
                "applied runtime gate requires raw inference and metrics"
            )
        if not self.gate_applied and self.action_consistent is not None:
            raise ValueError(
                "unapplied runtime gate cannot assert action consistency"
            )
        if self.candidate_permitted_after_gate and (
            not self.gate_applied
            or self.action_consistent is not True
            or self.fallback_reason is not None
        ):
            raise ValueError(
                "permitted runtime gate candidate has inconsistent evidence"
            )
        if self.rule_fallback_due_to_gate and (
            self.candidate_permitted_after_gate
            or self.fallback_reason is None
        ):
            raise ValueError(
                "runtime gate fallback requires a rejection reason"
            )
        if self.truth_identifier_use_count != 0:
            raise ValueError(
                "runtime confidence gate diagnostic cannot use truth IDs"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "model_raw_inference_executed": (
                self.model_raw_inference_executed
            ),
            "gate_applied": self.gate_applied,
            "action_consistent": self.action_consistent,
            "raw_confidence": self.raw_confidence,
            "effective_confidence": self.effective_confidence,
            "candidate_permitted_after_gate": (
                self.candidate_permitted_after_gate
            ),
            "rule_fallback_due_to_gate": (
                self.rule_fallback_due_to_gate
            ),
            "gate_content_sha256": self.gate_content_sha256,
            "formal_decision_digest": self.formal_decision_digest,
            "fallback_reason": self.fallback_reason,
            "truth_identifier_use_count": (
                self.truth_identifier_use_count
            ),
        }


@dataclass(frozen=True)
class RegionResourceAdvisoryResult:
    requested_mode: AdvisorMode
    effective_mode: AdvisorMode
    recommendation: RegionResourceRecommendation | None
    fallback_used: bool
    fallback_reason: str | None
    assist_eligible: bool
    unseen_seed_count: int
    inference_latency_ms: float
    formal_decision: RegionalFailoverDecision | None
    formal_decision_digest_before: str | None
    formal_decision_digest_after: str | None
    formal_decision_unchanged: bool
    advisory_contract: RegionResourceAdvisoryContract | None = None
    runtime_confidence_gate_diagnostic: (
        RegionResourceRuntimeConfidenceGateDiagnostic | None
    ) = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "requested_mode": self.requested_mode.value,
            "effective_mode": self.effective_mode.value,
            "recommendation": (
                self.recommendation.to_dict() if self.recommendation is not None else None
            ),
            "advisory_contract": (
                self.advisory_contract.to_dict()
                if self.advisory_contract is not None
                else None
            ),
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "assist_eligible": self.assist_eligible,
            "unseen_seed_count": self.unseen_seed_count,
            "inference_latency_ms": self.inference_latency_ms,
            "formal_decision_digest_before": self.formal_decision_digest_before,
            "formal_decision_digest_after": self.formal_decision_digest_after,
            "formal_decision_unchanged": self.formal_decision_unchanged,
        }
        if self.runtime_confidence_gate_diagnostic is not None:
            payload["runtime_confidence_gate_diagnostic"] = (
                self.runtime_confidence_gate_diagnostic.to_dict()
            )
        return payload


class RegionResourceAdvisor:
    """Fail-closed learned advisor with an immutable rule fallback."""

    def __init__(
        self,
        *,
        config: RegionResourceAdvisorConfig | None = None,
        learned_policy: Any | None = None,
        bundle_error: str | None = None,
    ) -> None:
        self.config = config or RegionResourceAdvisorConfig()
        self.learned_policy = learned_policy
        self.bundle_error = bundle_error
        self.projector = DeterministicResourceProjector(self.config.projection)
        rule_config = RuleRegionResourcePolicyConfig(projection=self.config.projection)
        self.rule_policy = RuleRegionResourcePolicy(
            rule_config,
            projector=self.projector,
        )

    @classmethod
    def from_bundle(
        cls,
        bundle_dir: str | Path,
        *,
        config: RegionResourceAdvisorConfig | None = None,
        expected_model_version: str | None = None,
        expected_state_dict_sha256: str | None = None,
    ) -> "RegionResourceAdvisor":
        try:
            bundle = load_region_resource_model_bundle(
                bundle_dir,
                expected_model_version=expected_model_version,
                expected_state_dict_sha256=expected_state_dict_sha256,
            )
        except (ModelBundleValidationError, RegionResourceLearningError) as exc:
            return cls(config=config, learned_policy=None, bundle_error=str(exc))
        return cls(
            config=config,
            learned_policy=LearnedRegionResourcePolicy(bundle.model, bundle.manifest),
        )

    def advise(
        self,
        snapshot: RegionResourceSnapshot,
        *,
        formal_decision: RegionalFailoverDecision | None = None,
        unseen_seed_count: int = 0,
    ) -> RegionResourceAdvisoryResult:
        if int(unseen_seed_count) < 0:
            raise ValueError("unseen_seed_count must be non-negative")
        digest_before = formal_decision_digest(formal_decision)
        manifest = getattr(self.learned_policy, "manifest", None)
        runtime_gate = (
            manifest.runtime_confidence_gate
            if isinstance(manifest, RegionResourceModelManifest)
            else None
        )
        if self.config.mode == AdvisorMode.DISABLED:
            return self._result(
                recommendation=None,
                effective_mode=AdvisorMode.DISABLED,
                fallback_used=False,
                fallback_reason=None,
                unseen_seed_count=unseen_seed_count,
                inference_latency_ms=0.0,
                formal_decision=formal_decision,
                digest_before=digest_before,
                advisory_contract=None,
                runtime_confidence_gate_diagnostic=(
                    self._runtime_confidence_gate_diagnostic(
                        runtime_gate,
                        evaluation=None,
                        fallback_reason="advisor_disabled",
                    )
                ),
            )

        fallback_reason: str | None = None
        raw: RegionResourceRecommendation | None = None
        runtime_gate_evaluation: (
            RegionResourceRuntimeConfidenceGateEvaluation | None
        ) = None
        elapsed_s = 0.0
        if self.bundle_error:
            fallback_reason = f"bundle_validation_failed:{self.bundle_error}"
        elif self.learned_policy is None:
            fallback_reason = "model_unavailable"
        else:
            try:
                if runtime_gate is not None:
                    runtime_gate.validate_runtime_context(
                        projector=self.projector,
                        rule_policy=self.rule_policy,
                        minimum_confidence=self.config.minimum_confidence,
                        ood_margin=self.config.ood_margin,
                    )
                if (
                    hasattr(self.learned_policy, "is_ood")
                    and self.learned_policy.is_ood(
                        snapshot,
                        margin=self.config.ood_margin,
                    )
                ):
                    fallback_reason = "feature_ood"
                else:
                    started = perf_counter()
                    if runtime_gate is not None:
                        gate_method = getattr(
                            self.learned_policy,
                            "recommend_with_runtime_confidence_gate",
                            None,
                        )
                        if not callable(gate_method):
                            raise RuntimeConfidenceGateContextError(
                                "runtime_confidence_gate_path_unavailable"
                            )
                        raw, runtime_gate_evaluation = gate_method(
                            snapshot,
                            projector=self.projector,
                            rule_policy=self.rule_policy,
                            formal_decision=formal_decision,
                            minimum_confidence=(
                                self.config.minimum_confidence
                            ),
                            ood_margin=self.config.ood_margin,
                        )
                    elif bool(
                        getattr(
                            self.learned_policy,
                            "formal_decision_aware",
                            False,
                        )
                    ):
                        raw = self.learned_policy.recommend_raw(
                            snapshot,
                            formal_decision=formal_decision,
                        )
                    else:
                        raw = self.learned_policy.recommend_raw(snapshot)
                    elapsed_s = perf_counter() - started
                    if elapsed_s > self.config.inference_timeout_s:
                        fallback_reason = "learning_timeout"
                    elif not _recommendation_finite(raw):
                        fallback_reason = "learning_output_non_finite"
                    elif (
                        raw.fallback_reason
                        == "runtime_rule_action_consistency_gate_rejected"
                    ):
                        fallback_reason = raw.fallback_reason
                    elif raw.confidence < self.config.minimum_confidence:
                        fallback_reason = (
                            raw.fallback_reason
                            or "learning_confidence_below_threshold"
                        )
            except RuntimeConfidenceGateContextError:
                fallback_reason = (
                    "runtime_confidence_gate_context_mismatch"
                )
            except NonFinitePolicyOutput:
                fallback_reason = "learning_output_non_finite"
            except Exception as exc:  # A research policy must never escape into D4.
                fallback_reason = f"learning_exception:{type(exc).__name__}"

        fallback_used = fallback_reason is not None or raw is None
        if fallback_used:
            recommendation = self.rule_policy.recommend(
                snapshot,
                formal_decision=formal_decision,
                fallback_reason=fallback_reason or "model_unavailable",
            )
        else:
            assert raw is not None
            recommendation = (
                runtime_gate_evaluation.effective_recommendation
                if runtime_gate_evaluation is not None
                else self.projector.project(
                    snapshot,
                    raw,
                    formal_decision=formal_decision,
                )
            )

        bundle_allows_assist = bool(
            isinstance(manifest, RegionResourceModelManifest)
            and manifest.assist_admitted
        )
        assist_eligible = bool(
            self.config.mode == AdvisorMode.ASSIST
            and unseen_seed_count >= self.config.minimum_unseen_seeds
            and not fallback_used
            and bundle_allows_assist
        )
        effective_mode = (
            AdvisorMode.ASSIST if assist_eligible else AdvisorMode.SHADOW
        )
        if self.config.mode == AdvisorMode.ASSIST and not assist_eligible:
            gate_reason = (
                "fewer_than_minimum_unseen_seeds"
                if unseen_seed_count < self.config.minimum_unseen_seeds
                else (
                    "model_bundle_shadow_only"
                    if not bundle_allows_assist
                    else fallback_reason or "assist_gate_not_met"
                )
            )
            if recommendation.fallback_reason is None:
                recommendation = RegionResourceRecommendation(
                    **{
                        **recommendation.__dict__,
                        "fallback_reason": gate_reason,
                    }
                )
        advisory_contract = self.projector.build_advisory_contract(
            snapshot,
            recommendation,
            formal_decision=formal_decision,
        )
        return self._result(
            recommendation=recommendation,
            effective_mode=effective_mode,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            unseen_seed_count=unseen_seed_count,
            inference_latency_ms=elapsed_s * 1000.0,
            formal_decision=formal_decision,
            digest_before=digest_before,
            advisory_contract=advisory_contract,
            runtime_confidence_gate_diagnostic=(
                self._runtime_confidence_gate_diagnostic(
                    runtime_gate,
                    evaluation=runtime_gate_evaluation,
                    fallback_reason=fallback_reason,
                )
            ),
        )

    def _runtime_confidence_gate_diagnostic(
        self,
        gate: RegionResourceRuntimeConfidenceGateConfig | None,
        *,
        evaluation: (
            RegionResourceRuntimeConfidenceGateEvaluation | None
        ),
        fallback_reason: str | None,
    ) -> RegionResourceRuntimeConfidenceGateDiagnostic | None:
        if gate is None:
            return None
        gate_rejection_reasons = {
            "runtime_rule_action_consistency_gate_rejected",
            "runtime_confidence_gate_context_mismatch",
        }
        return RegionResourceRuntimeConfidenceGateDiagnostic(
            model_raw_inference_executed=evaluation is not None,
            gate_applied=evaluation is not None,
            action_consistent=(
                evaluation.action_consistency.action_consistent
                if evaluation is not None
                else None
            ),
            raw_confidence=(
                evaluation.raw_confidence
                if evaluation is not None
                else None
            ),
            effective_confidence=(
                evaluation.effective_confidence
                if evaluation is not None
                else None
            ),
            candidate_permitted_after_gate=bool(
                evaluation is not None and fallback_reason is None
            ),
            rule_fallback_due_to_gate=(
                fallback_reason in gate_rejection_reasons
            ),
            gate_content_sha256=gate.content_sha256,
            formal_decision_digest=(
                evaluation.formal_decision_digest
                if evaluation is not None
                else None
            ),
            fallback_reason=fallback_reason,
        )

    def _result(
        self,
        *,
        recommendation: RegionResourceRecommendation | None,
        effective_mode: AdvisorMode,
        fallback_used: bool,
        fallback_reason: str | None,
        unseen_seed_count: int,
        inference_latency_ms: float,
        formal_decision: RegionalFailoverDecision | None,
        digest_before: str | None,
        advisory_contract: RegionResourceAdvisoryContract | None,
        runtime_confidence_gate_diagnostic: (
            RegionResourceRuntimeConfidenceGateDiagnostic | None
        ),
    ) -> RegionResourceAdvisoryResult:
        digest_after = formal_decision_digest(formal_decision)
        unchanged = digest_before == digest_after
        if not unchanged:
            raise RuntimeError("regional learning advisor mutated the formal D4 decision")
        return RegionResourceAdvisoryResult(
            requested_mode=self.config.mode,
            effective_mode=effective_mode,
            recommendation=recommendation,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            assist_eligible=effective_mode == AdvisorMode.ASSIST,
            unseen_seed_count=int(unseen_seed_count),
            inference_latency_ms=float(inference_latency_ms),
            formal_decision=formal_decision,
            formal_decision_digest_before=digest_before,
            formal_decision_digest_after=digest_after,
            formal_decision_unchanged=unchanged,
            advisory_contract=advisory_contract,
            runtime_confidence_gate_diagnostic=(
                runtime_confidence_gate_diagnostic
            ),
        )


def _resolve_region_learning_dataset(
    dataset: str | Path | LoadedRegionLearningDataset,
) -> LoadedRegionLearningDataset:
    if isinstance(dataset, LoadedRegionLearningDataset):
        return dataset
    return load_region_learning_dataset(dataset)


def _training_episodes(
    dataset: LoadedRegionLearningDataset | CanonicalRegionLearningDatasetView,
    *,
    split: RegionLearningSplit | str,
    allow_dirty_source: bool,
    purpose: str,
) -> tuple[Any, ...]:
    resolved_split = (
        split
        if isinstance(split, RegionLearningSplit)
        else RegionLearningSplit(str(split))
    )
    episodes = dataset.episodes(resolved_split)
    if not episodes:
        raise RegionLearningDataUnavailableError(
            f"{purpose}_split_empty:{resolved_split.value}"
        )
    if not allow_dirty_source:
        dirty = next((item for item in episodes if item.source.git_dirty), None)
        if dirty is not None:
            raise RegionLearningDataUnavailableError(
                f"dirty_source:{dirty.source.episode_id}"
            )
    return episodes


def _require_torch() -> None:
    if torch is None or nn is None:
        raise RegionResourceLearningError("torch_unavailable")


def _log_feature(value: float) -> float:
    return log(1.0 + float(value))


def _logit(value: float) -> float:
    clipped = max(1e-4, min(1.0 - 1e-4, float(value)))
    return log(clipped / (1.0 - clipped))


def _tensor_inside_bounds(
    tensor: Any,
    minima: Sequence[float],
    maxima: Sequence[float],
    margin: float,
) -> bool:
    lower = torch.tensor(minima, dtype=tensor.dtype, device=tensor.device)
    upper = torch.tensor(maxima, dtype=tensor.dtype, device=tensor.device)
    scale = torch.maximum(torch.maximum(lower.abs(), upper.abs()), torch.ones_like(lower))
    tolerance = margin * scale
    return bool(((tensor >= lower - tolerance) & (tensor <= upper + tolerance)).all())


def _validate_policy_output(output: GraphPolicyOutput) -> None:
    tensors = (
        output.node_mean,
        output.edge_mean,
        output.node_log_std,
        output.edge_log_std,
        output.value,
        output.confidence,
    )
    if not all(torch.isfinite(item).all() for item in tensors):
        raise NonFinitePolicyOutput("graph_policy_output_non_finite")


def _recommendation_finite(recommendation: RegionResourceRecommendation) -> bool:
    values: list[float] = [recommendation.confidence, recommendation.created_at_s]
    for action in recommendation.actions:
        values.extend(
            (
                action.reserve_ratio,
                action.reconnaissance_priority,
                action.expected_lease_expires_at_s,
            )
        )
    for transfer in recommendation.transfers:
        values.append(transfer.expected_transfer_time_s)
    return all(isfinite(float(value)) for value in values)


def _model_parameters_finite(model: SharedRegionGraphActorCritic) -> bool:
    return all(torch.isfinite(parameter).all() for parameter in model.parameters())


def _model_device(model: SharedRegionGraphActorCritic) -> Any:
    return next(model.parameters()).device


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
