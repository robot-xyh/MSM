"""Optional graph-learning research path for regional resource advice.

The learned policy is never an authority source.  Every output is projected by
``DeterministicResourceProjector`` and remains advisory to D4/D3/main.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from math import atanh, isfinite, log
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Mapping, Sequence

from .region_resource import (
    AdvisorMode,
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


try:  # The default deterministic D4 path does not require torch.
    import torch
    from torch import nn
except ImportError:  # pragma: no cover - exercised only in minimal deployments.
    torch = None
    nn = None


REGION_RESOURCE_MODEL_BUNDLE_SCHEMA = "d4-region-resource-model-bundle-v1"
REGION_GRAPH_ARCHITECTURE = "shared-region-graph-actor-critic-v1"

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


class RegionResourceLearningError(RuntimeError):
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
class RegionResourceModelManifest:
    model_version: str
    hidden_dim: int
    message_passing_steps: int
    state_dict_file: str
    state_dict_sha256: str
    feature_bounds: RegionFeatureBounds
    training_groups: tuple[tuple[str, int], ...]
    created_at_utc: str
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
        groups = tuple(sorted({(str(item[0]), int(item[1])) for item in self.training_groups}))
        object.__setattr__(self, "training_groups", groups)

    def to_dict(self) -> dict[str, Any]:
        return {
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
            "created_at_utc": self.created_at_utc,
        }

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
        return cls(**payload)


@dataclass(frozen=True)
class LoadedRegionResourceModelBundle:
    model: SharedRegionGraphActorCritic
    manifest: RegionResourceModelManifest
    bundle_dir: Path


def save_region_resource_model_bundle(
    model: SharedRegionGraphActorCritic,
    bundle_dir: str | Path,
    *,
    model_version: str,
    training_graphs: Sequence[RegionGraph],
    training_groups: Iterable[tuple[str, int]],
    created_at_utc: str,
) -> RegionResourceModelManifest:
    _require_torch()
    destination = Path(bundle_dir)
    destination.mkdir(parents=True, exist_ok=True)
    state_path = destination / "state_dict.pt"
    temporary_state_path = destination / "state_dict.pt.tmp"
    torch.save(model.state_dict(), temporary_state_path)
    temporary_state_path.replace(state_path)
    digest = _sha256_file(state_path)
    manifest = RegionResourceModelManifest(
        model_version=model_version,
        hidden_dim=model.hidden_dim,
        message_passing_steps=model.message_passing_steps,
        state_dict_file=state_path.name,
        state_dict_sha256=digest,
        feature_bounds=RegionFeatureBounds.from_graphs(training_graphs),
        training_groups=tuple(training_groups),
        created_at_utc=created_at_utc,
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
    )


class LearnedRegionResourcePolicy:
    def __init__(
        self,
        model: SharedRegionGraphActorCritic,
        manifest: RegionResourceModelManifest,
    ) -> None:
        self.model = model
        self.manifest = manifest

    def recommend_raw(self, snapshot: RegionResourceSnapshot) -> RegionResourceRecommendation:
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
            count = int(fraction * edge_ref.transferable_resources)
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

    def to_dict(self) -> dict[str, Any]:
        return {
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
            )

        fallback_reason: str | None = None
        raw: RegionResourceRecommendation | None = None
        elapsed_s = 0.0
        if self.bundle_error:
            fallback_reason = f"bundle_validation_failed:{self.bundle_error}"
        elif self.learned_policy is None:
            fallback_reason = "model_unavailable"
        else:
            try:
                if hasattr(self.learned_policy, "is_ood") and self.learned_policy.is_ood(
                    snapshot, margin=self.config.ood_margin
                ):
                    fallback_reason = "feature_ood"
                else:
                    started = perf_counter()
                    raw = self.learned_policy.recommend_raw(snapshot)
                    elapsed_s = perf_counter() - started
                    if elapsed_s > self.config.inference_timeout_s:
                        fallback_reason = "learning_timeout"
                    elif not _recommendation_finite(raw):
                        fallback_reason = "learning_output_non_finite"
                    elif raw.confidence < self.config.minimum_confidence:
                        fallback_reason = "learning_confidence_below_threshold"
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
            recommendation = self.projector.project(
                snapshot,
                raw,
                formal_decision=formal_decision,
            )

        assist_eligible = bool(
            self.config.mode == AdvisorMode.ASSIST
            and unseen_seed_count >= self.config.minimum_unseen_seeds
            and not fallback_used
        )
        effective_mode = (
            AdvisorMode.ASSIST if assist_eligible else AdvisorMode.SHADOW
        )
        if self.config.mode == AdvisorMode.ASSIST and not assist_eligible:
            gate_reason = (
                "fewer_than_minimum_unseen_seeds"
                if unseen_seed_count < self.config.minimum_unseen_seeds
                else fallback_reason or "assist_gate_not_met"
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
        )


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
