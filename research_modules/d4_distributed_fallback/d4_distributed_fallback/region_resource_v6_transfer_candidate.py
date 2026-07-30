"""Unregistered D4 v6 edge-transfer learning development candidate.

The v6 path is version-isolated from frozen v4/v5 artifacts.  It reuses the
shared graph actor runtime contract, but trains the edge output with explicit
activation, directed-edge ranking, positive magnitude, and transfer-count
supervision.  TRAIN derives every class weight; VALIDATION only selects a
checkpoint.  TEST, the source-independent v5 evaluation seeds, and formal
holdout seeds are rejected.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import atanh, isclose, isfinite
from pathlib import Path
import random
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from .region_resource import (
    DeterministicResourceProjector,
    RuleRegionResourcePolicy,
)
from .region_resource_dataset import (
    LoadedRegionLearningDataset,
    RegionLearningSplit,
    load_region_learning_dataset_splits,
)
from .region_resource_learning import (
    EDGE_ACTION_DIM,
    EDGE_FEATURE_NAMES,
    NODE_ACTION_DIM,
    NODE_FEATURE_NAMES,
    GraphPolicyOutput,
    MODEL_LIFECYCLE_DEVELOPMENT,
    MODEL_MAXIMUM_MODE_SHADOW,
    LearnedRegionResourcePolicy,
    SharedRegionGraphActorCritic,
    load_region_resource_model_bundle,
)
from .region_resource_v4_shadow_candidate import (
    REGION_RESOURCE_V4_CANDIDATE_FILENAME,
    REGION_RESOURCE_V4_CANDIDATE_ID,
    REGION_RESOURCE_V4_INTERVENTION_GATE,
    _PolicyIdentity,
    _V4_PROJECTION,
    _V4_RULE_CONFIG,
    _model_parameters_finite,
    _v4_actor_metrics,
    _v4_actor_records,
    evaluate_v4_intervention_invariants,
    executable_signature,
)
from .region_resource_v5_confidence_candidate import (
    REGION_RESOURCE_V5_BASE_V4_DATASET_SHA256,
    REGION_RESOURCE_V5_BASE_V4_MANIFEST_CONTENT_SHA256,
    REGION_RESOURCE_V5_BASE_V4_MANIFEST_FILE_SHA256,
    REGION_RESOURCE_V5_BASE_V4_MODEL_STATE_SHA256,
    REGION_RESOURCE_V5_BASE_V4_SPLIT_SHA256,
)


try:  # The deterministic D4 runtime remains torch-free.
    import torch
except ImportError:  # pragma: no cover - exercised by the dependency gate.
    torch = None


REGION_RESOURCE_V6_CANDIDATE_ID = (
    "region_resource_a2_edge_transfer_shadow_v6"
)
REGION_RESOURCE_V6_MODEL_VERSION = (
    "d4-region-resource-graph-bc-edge-transfer-v6"
)
REGION_RESOURCE_V6_CANDIDATE_SCHEMA = (
    "d4-region-resource-edge-transfer-candidate-v6"
)
REGION_RESOURCE_V6_CONFIG_SCHEMA = (
    "d4-region-resource-edge-transfer-config-v6"
)
REGION_RESOURCE_V6_BALANCE_SCHEMA = (
    "d4-region-resource-edge-transfer-train-balance-v6"
)
REGION_RESOURCE_V6_AUDIT_SCHEMA = (
    "d4-region-resource-edge-transfer-training-audit-v6"
)
REGION_RESOURCE_V6_PERMISSIONS_SCHEMA = (
    "d4-region-resource-edge-transfer-permissions-v6"
)
REGION_RESOURCE_V6_CANDIDATE_FILENAME = (
    "v6_edge_transfer_candidate_manifest.json"
)
REGION_RESOURCE_V6_CONFIG_FILENAME = "training_config.json"
REGION_RESOURCE_V6_AUDIT_FILENAME = "training_audit.json"
REGION_RESOURCE_V6_SOURCE_FILENAME = "source_binding.json"
REGION_RESOURCE_V6_BUNDLE_SCHEMA = (
    "d4-region-resource-explicit-edge-activation-bundle-v6"
)
REGION_RESOURCE_V6_STATE_MAGIC = b"D4V6EDGE1\x00"

REGION_RESOURCE_V6_FIXED_MINIMUM_CONFIDENCE = 0.60
REGION_RESOURCE_V6_ACTIVATION_TEMPERATURE = 4.0
REGION_RESOURCE_V6_DIRECTION_MARGIN = 0.25
REGION_RESOURCE_V6_POSITIVE_SAMPLE_WEIGHT_CAP = 8.0
REGION_RESOURCE_V6_POSITIVE_EDGE_WEIGHT_CAP = 64.0
REGION_RESOURCE_V6_ZERO_TARGET_TOLERANCE = 1.0e-12
REGION_RESOURCE_V6_FORBIDDEN_FORMAL_HOLDOUT_SEEDS = frozenset(
    range(1000, 1020)
)
REGION_RESOURCE_V6_FORBIDDEN_SOURCE_EVALUATION_SEEDS = frozenset(
    range(3008, 3040)
)


class RegionResourceV6CandidateError(RuntimeError):
    """Stable fail-closed error for the v6 development candidate."""


@dataclass(frozen=True)
class V6SupervisedPolicyOutput:
    """Training output with activation separated from transfer magnitude."""

    policy: GraphPolicyOutput
    edge_activation_logits: Any
    edge_magnitude: Any


class V6EdgeTransferGraphActorCritic(SharedRegionGraphActorCritic):
    """Shared graph actor with a v6-only explicit edge activation head."""

    def __init__(
        self,
        *,
        hidden_dim: int = 64,
        message_passing_steps: int = 2,
        node_feature_dim: int = len(NODE_FEATURE_NAMES),
        edge_feature_dim: int = len(EDGE_FEATURE_NAMES),
    ) -> None:
        super().__init__(
            hidden_dim=hidden_dim,
            message_passing_steps=message_passing_steps,
            node_feature_dim=node_feature_dim,
            edge_feature_dim=edge_feature_dim,
        )
        self.edge_activation_actor = torch.nn.Sequential(
            torch.nn.Linear(self.hidden_dim * 3, self.hidden_dim),
            torch.nn.Tanh(),
            torch.nn.Linear(self.hidden_dim, EDGE_ACTION_DIM),
        )

    def forward_supervised(self, graph: Any) -> V6SupervisedPolicyOutput:
        node_hidden = self.node_encoder(graph.node_features)
        edge_hidden = self.edge_encoder(graph.edge_features)
        if graph.edge_count:
            source = graph.edge_index[0]
            target = graph.edge_index[1]
            for _ in range(self.message_passing_steps):
                messages = self.message_network(
                    torch.cat(
                        (
                            node_hidden[source],
                            node_hidden[target],
                            edge_hidden,
                        ),
                        dim=-1,
                    )
                )
                aggregate = torch.zeros_like(node_hidden)
                aggregate.index_add_(0, target, messages)
                degree = torch.zeros(
                    graph.node_count,
                    dtype=node_hidden.dtype,
                    device=node_hidden.device,
                )
                degree.index_add_(
                    0,
                    target,
                    torch.ones_like(target, dtype=node_hidden.dtype),
                )
                aggregate = (
                    aggregate / degree.clamp_min(1.0).unsqueeze(-1)
                )
                node_hidden = self.node_update(
                    torch.cat((node_hidden, aggregate), dim=-1)
                )
            edge_context = torch.cat(
                (node_hidden[source], node_hidden[target], edge_hidden),
                dim=-1,
            )
            edge_magnitude = torch.nn.functional.softplus(
                self.edge_actor(edge_context)
            )
            edge_activation_logits = self.edge_activation_actor(
                edge_context
            )
            thresholds = _edge_activation_thresholds(
                graph,
                edge_magnitude,
            )
            active_magnitude = torch.maximum(
                edge_magnitude,
                thresholds + 1.0e-6,
            )
            edge_mean = torch.where(
                edge_activation_logits >= 0.0,
                active_magnitude,
                torch.full_like(active_magnitude, -1.0),
            )
        else:
            for _ in range(self.message_passing_steps):
                node_hidden = self.node_update(
                    torch.cat(
                        (node_hidden, torch.zeros_like(node_hidden)),
                        dim=-1,
                    )
                )
            edge_magnitude = torch.empty(
                (0, EDGE_ACTION_DIM),
                dtype=node_hidden.dtype,
                device=node_hidden.device,
            )
            edge_activation_logits = torch.empty_like(edge_magnitude)
            edge_mean = torch.empty_like(edge_magnitude)
        pooled = node_hidden.mean(dim=0)
        policy = GraphPolicyOutput(
            node_mean=self.node_actor(node_hidden),
            edge_mean=edge_mean,
            node_log_std=self.node_log_std_parameter.expand(
                (graph.node_count, NODE_ACTION_DIM)
            ),
            edge_log_std=self.edge_log_std_parameter.expand_as(edge_mean),
            value=self.value_head(pooled).squeeze(-1),
            confidence=self.confidence_head(pooled).squeeze(-1),
        )
        return V6SupervisedPolicyOutput(
            policy=policy,
            edge_activation_logits=edge_activation_logits,
            edge_magnitude=edge_magnitude,
        )

    def forward(self, graph: Any) -> GraphPolicyOutput:
        return self.forward_supervised(graph).policy


@dataclass(frozen=True)
class RegionResourceV6Permissions:
    """Capabilities that an unregistered v6 candidate cannot obtain."""

    formal_evaluation_authorized: bool = False
    assist_enabled: bool = False
    authority_enabled: bool = False
    assignment_enabled: bool = False
    degradation_enabled: bool = False
    takeover_enabled: bool = False
    coalition_commit_enabled: bool = False
    control_enabled: bool = False
    production_runtime_ack_enabled: bool = False
    physical_permission_available: bool = False
    d3_permission_available: bool = False
    d7_permission_available: bool = False
    actual_adoption_claimed: bool = False
    benefit_claimed: bool = False
    schema: str = REGION_RESOURCE_V6_PERMISSIONS_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V6_PERMISSIONS_SCHEMA:
            raise ValueError("unsupported v6 permissions schema")
        values = (
            value
            for name, value in asdict(self).items()
            if name != "schema"
        )
        if any(type(value) is not bool or value for value in values):
            raise ValueError("v6 development candidate cannot grant permissions")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionResourceV6BuildConfig:
    """Finite, deterministic v6 edge-transfer training contract."""

    random_seed: int = 20260730
    hidden_dim: int = 24
    message_passing_steps: int = 2
    epochs: int = 240
    batch_size: int = 16
    learning_rate: float = 3.0e-3
    weight_decay: float = 1.0e-5
    max_grad_norm: float = 1.0
    early_stopping_patience: int = 45
    node_continuous_weight: float = 1.0
    node_binary_weight: float = 1.0
    edge_activation_weight: float = 1.0
    positive_magnitude_weight: float = 0.25
    direction_ranking_weight: float = 0.50
    positive_edge_count_weight: float = 0.25
    activation_temperature: float = (
        REGION_RESOURCE_V6_ACTIVATION_TEMPERATURE
    )
    direction_margin: float = REGION_RESOURCE_V6_DIRECTION_MARGIN
    torch_num_threads: int = 1
    created_at_utc: str = "2026-07-30T00:00:00Z"
    candidate_id: str = REGION_RESOURCE_V6_CANDIDATE_ID
    model_version: str = REGION_RESOURCE_V6_MODEL_VERSION
    schema: str = REGION_RESOURCE_V6_CONFIG_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema != REGION_RESOURCE_V6_CONFIG_SCHEMA
            or self.candidate_id != REGION_RESOURCE_V6_CANDIDATE_ID
            or self.model_version != REGION_RESOURCE_V6_MODEL_VERSION
        ):
            raise ValueError("v6 candidate identity changed")
        for name in (
            "random_seed",
            "hidden_dim",
            "message_passing_steps",
            "epochs",
            "batch_size",
            "early_stopping_patience",
            "torch_num_threads",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"v6 config {name} must be positive")
        for name in (
            "learning_rate",
            "weight_decay",
            "max_grad_norm",
            "node_continuous_weight",
            "node_binary_weight",
            "edge_activation_weight",
            "positive_magnitude_weight",
            "direction_ranking_weight",
            "positive_edge_count_weight",
            "activation_temperature",
            "direction_margin",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or value < 0.0:
                raise ValueError(
                    f"v6 config {name} must be finite and non-negative"
                )
        if (
            self.learning_rate <= 0.0
            or self.max_grad_norm <= 0.0
            or self.edge_activation_weight <= 0.0
            or self.positive_magnitude_weight <= 0.0
            or self.direction_ranking_weight <= 0.0
            or self.positive_edge_count_weight <= 0.0
            or not isclose(
                self.activation_temperature,
                REGION_RESOURCE_V6_ACTIVATION_TEMPERATURE,
            )
            or not isclose(
                self.direction_margin,
                REGION_RESOURCE_V6_DIRECTION_MARGIN,
            )
        ):
            raise ValueError("v6 edge supervision contract changed")
        if not self.created_at_utc:
            raise ValueError("v6 created_at_utc must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionResourceV6ClassBalance:
    """TRAIN-only frame and edge weights for v6."""

    train_sample_count: int
    positive_sample_count: int
    negative_sample_count: int
    edge_count: int
    positive_edge_count: int
    zero_edge_count: int
    positive_sample_weight: float
    negative_sample_weight: float
    positive_edge_weight: float
    zero_edge_weight: float
    raw_positive_sample_ratio: float
    raw_positive_edge_ratio: float
    positive_sample_weight_clipped: bool
    positive_edge_weight_clipped: bool
    train_label_inventory_sha256: str
    source_split: str = RegionLearningSplit.TRAIN.value
    validation_label_fit_count: int = 0
    validation_weight_fit_count: int = 0
    test_payload_read_count: int = 0
    test_payload_fit_count: int = 0
    formal_holdout_payload_read_count: int = 0
    source_evaluation_payload_read_count: int = 0
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_V6_BALANCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V6_BALANCE_SCHEMA:
            raise ValueError("unsupported v6 balance schema")
        for name in (
            "train_sample_count",
            "positive_sample_count",
            "negative_sample_count",
            "edge_count",
            "positive_edge_count",
            "zero_edge_count",
            "validation_label_fit_count",
            "validation_weight_fit_count",
            "test_payload_read_count",
            "test_payload_fit_count",
            "formal_holdout_payload_read_count",
            "source_evaluation_payload_read_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(
                    f"v6 balance {name} must be a non-negative integer"
                )
        if (
            self.train_sample_count
            != self.positive_sample_count + self.negative_sample_count
            or self.edge_count != self.positive_edge_count + self.zero_edge_count
            or min(
                self.positive_sample_count,
                self.negative_sample_count,
                self.positive_edge_count,
                self.zero_edge_count,
            )
            <= 0
        ):
            raise ValueError("v6 TRAIN balance requires both frame and edge classes")
        if (
            self.source_split != RegionLearningSplit.TRAIN.value
            or self.validation_label_fit_count != 0
            or self.validation_weight_fit_count != 0
            or self.test_payload_read_count != 0
            or self.test_payload_fit_count != 0
            or self.formal_holdout_payload_read_count != 0
            or self.source_evaluation_payload_read_count != 0
        ):
            raise ValueError("v6 weights must be fit from TRAIN only")
        for name in (
            "positive_sample_weight",
            "negative_sample_weight",
            "positive_edge_weight",
            "zero_edge_weight",
            "raw_positive_sample_ratio",
            "raw_positive_edge_ratio",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or value <= 0.0:
                raise ValueError(
                    f"v6 balance {name} must be finite and positive"
                )
        if (
            not isclose(self.negative_sample_weight, 1.0)
            or not isclose(self.zero_edge_weight, 1.0)
            or self.positive_sample_weight
            != min(
                self.raw_positive_sample_ratio,
                REGION_RESOURCE_V6_POSITIVE_SAMPLE_WEIGHT_CAP,
            )
            or self.positive_edge_weight
            != min(
                self.raw_positive_edge_ratio,
                REGION_RESOURCE_V6_POSITIVE_EDGE_WEIGHT_CAP,
            )
        ):
            raise ValueError("v6 TRAIN-derived weights are inconsistent")
        _require_sha256(
            self.train_label_inventory_sha256,
            "v6_balance.train_label_inventory_sha256",
        )
        expected = _canonical_sha256(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected:
            raise ValueError("v6 balance content SHA256 mismatch")
        object.__setattr__(self, "content_sha256", expected)

    def content_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("content_sha256", None)
        return payload

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}


def derive_v6_class_balance(
    records: Sequence[Any],
    *,
    split: RegionLearningSplit = RegionLearningSplit.TRAIN,
) -> RegionResourceV6ClassBalance:
    """Derive all imbalance weights from TRAIN labels only."""

    if split != RegionLearningSplit.TRAIN or any(
        record.split != RegionLearningSplit.TRAIN for record in records
    ):
        raise RegionResourceV6CandidateError(
            "v6_balance_fit_requires_train_only"
        )
    positive_samples = sum(bool(record.target_positive) for record in records)
    negative_samples = len(records) - positive_samples
    positive_edges = sum(
        int(record.nonzero_edge_target_count) for record in records
    )
    edge_count = sum(int(record.edge_target_count) for record in records)
    zero_edges = edge_count - positive_edges
    if min(positive_samples, negative_samples, positive_edges, zero_edges) <= 0:
        raise RegionResourceV6CandidateError(
            "v6_train_requires_positive_negative_and_edge_diversity"
        )
    sample_ratio = negative_samples / positive_samples
    edge_ratio = zero_edges / positive_edges
    label_inventory = [
        {
            "source_episode_id": record.source_episode_id,
            "frame_index": int(record.frame_index),
            "target_positive": bool(record.target_positive),
            "target_signature": record.target_executable_signature_sha256,
            "rule_signature": record.rule_executable_signature_sha256,
            "positive_edges": int(record.nonzero_edge_target_count),
            "edge_count": int(record.edge_target_count),
        }
        for record in records
    ]
    return RegionResourceV6ClassBalance(
        train_sample_count=len(records),
        positive_sample_count=positive_samples,
        negative_sample_count=negative_samples,
        edge_count=edge_count,
        positive_edge_count=positive_edges,
        zero_edge_count=zero_edges,
        positive_sample_weight=min(
            sample_ratio,
            REGION_RESOURCE_V6_POSITIVE_SAMPLE_WEIGHT_CAP,
        ),
        negative_sample_weight=1.0,
        positive_edge_weight=min(
            edge_ratio,
            REGION_RESOURCE_V6_POSITIVE_EDGE_WEIGHT_CAP,
        ),
        zero_edge_weight=1.0,
        raw_positive_sample_ratio=sample_ratio,
        raw_positive_edge_ratio=edge_ratio,
        positive_sample_weight_clipped=bool(
            sample_ratio > REGION_RESOURCE_V6_POSITIVE_SAMPLE_WEIGHT_CAP
        ),
        positive_edge_weight_clipped=bool(
            edge_ratio > REGION_RESOURCE_V6_POSITIVE_EDGE_WEIGHT_CAP
        ),
        train_label_inventory_sha256=_canonical_sha256(label_inventory),
    )


def _edge_activation_thresholds(graph: Any, edge_values: Any) -> Any:
    """Return raw means whose projected transfer count crosses zero."""

    thresholds = []
    for edge_ref in graph.edge_refs:
        transferable = int(edge_ref.transferable_resources)
        if transferable <= 0:
            thresholds.append(20.0)
            continue
        minimum_fraction = min(0.999, (0.5 + 1.0e-6) / transferable)
        thresholds.append(atanh(minimum_fraction))
    return torch.tensor(
        thresholds,
        dtype=edge_values.dtype,
        device=edge_values.device,
    ).reshape((-1, 1))


def _v6_edge_supervision_components(
    edge_activation_logits: Any,
    edge_magnitude: Any,
    *,
    graph: Any,
    edge_targets: Any,
    balance: RegionResourceV6ClassBalance,
    config: RegionResourceV6BuildConfig,
) -> dict[str, Any]:
    """Compute explicit activation, direction, magnitude, and count losses."""

    if graph.edge_count == 0:
        zero = edge_magnitude.sum() * 0.0
        return {
            "activation": zero,
            "positive_magnitude": zero,
            "direction_ranking": zero,
            "positive_edge_count": zero,
            "activation_logits": edge_activation_logits,
        }
    positive_mask = (
        edge_targets.abs() > REGION_RESOURCE_V6_ZERO_TARGET_TOLERANCE
    )
    scaled_activation_logits = (
        edge_activation_logits * config.activation_temperature
    )
    activation_targets = positive_mask.to(dtype=edge_magnitude.dtype)
    positive_weight = torch.tensor(
        [balance.positive_edge_weight],
        dtype=edge_magnitude.dtype,
        device=edge_magnitude.device,
    )
    activation = torch.nn.functional.binary_cross_entropy_with_logits(
        scaled_activation_logits,
        activation_targets,
        pos_weight=positive_weight,
    )
    if bool(positive_mask.any().item()):
        positive_magnitude = torch.nn.functional.smooth_l1_loss(
            edge_magnitude[positive_mask],
            edge_targets[positive_mask],
        )
    else:
        positive_magnitude = edge_magnitude.sum() * 0.0
    negative_mask = ~positive_mask
    if bool(positive_mask.any().item()) and bool(negative_mask.any().item()):
        positive_scores = scaled_activation_logits[positive_mask].reshape(
            (-1, 1)
        )
        negative_scores = scaled_activation_logits[negative_mask].reshape(
            (1, -1)
        )
        direction_ranking = torch.relu(
            config.direction_margin - (positive_scores - negative_scores)
        ).mean()
    else:
        direction_ranking = edge_magnitude.sum() * 0.0
    if bool(positive_mask.any().item()):
        transferable = torch.tensor(
            [
                max(0, int(edge_ref.transferable_resources))
                for edge_ref in graph.edge_refs
            ],
            dtype=edge_magnitude.dtype,
            device=edge_magnitude.device,
        ).reshape((-1, 1))
        predicted_counts = (
            torch.tanh(edge_magnitude[positive_mask])
            * transferable[positive_mask]
        )
        target_counts = (
            torch.tanh(edge_targets[positive_mask])
            * transferable[positive_mask]
        )
        positive_edge_count = torch.nn.functional.smooth_l1_loss(
            predicted_counts,
            target_counts,
        )
    else:
        positive_edge_count = edge_magnitude.sum() * 0.0
    return {
        "activation": activation,
        "positive_magnitude": positive_magnitude,
        "direction_ranking": direction_ranking,
        "positive_edge_count": positive_edge_count,
        "activation_logits": scaled_activation_logits,
    }


def _v6_actor_loss(
    model: V6EdgeTransferGraphActorCritic,
    record: Any,
    *,
    balance: RegionResourceV6ClassBalance,
    config: RegionResourceV6BuildConfig,
) -> tuple[Any, dict[str, Any]]:
    supervised = model.forward_supervised(record.sample.graph)
    output = supervised.policy
    target = record.sample.target
    node_continuous = torch.nn.functional.mse_loss(
        output.node_mean[:, :3],
        target.node_continuous,
    )
    node_binary = torch.nn.functional.binary_cross_entropy_with_logits(
        output.node_mean[:, 3:],
        target.node_binary,
    )
    edge = _v6_edge_supervision_components(
        supervised.edge_activation_logits,
        supervised.edge_magnitude,
        graph=record.sample.graph,
        edge_targets=target.edge_continuous,
        balance=balance,
        config=config,
    )
    node_total = (
        config.node_continuous_weight * node_continuous
        + config.node_binary_weight * node_binary
    )
    edge_total = (
        config.edge_activation_weight * edge["activation"]
        + config.positive_magnitude_weight * edge["positive_magnitude"]
        + config.direction_ranking_weight * edge["direction_ranking"]
        + config.positive_edge_count_weight * edge["positive_edge_count"]
    )
    node_sample_weight = (
        balance.positive_sample_weight
        if record.target_positive
        else balance.negative_sample_weight
    )
    total = node_sample_weight * node_total + edge_total
    return total, {
        "node_continuous": node_continuous,
        "node_binary": node_binary,
        "edge_activation": edge["activation"],
        "positive_magnitude": edge["positive_magnitude"],
        "direction_ranking": edge["direction_ranking"],
        "positive_edge_count": edge["positive_edge_count"],
    }


def _weighted_v6_loss(
    model: V6EdgeTransferGraphActorCritic,
    records: Sequence[Any],
    *,
    balance: RegionResourceV6ClassBalance,
    config: RegionResourceV6BuildConfig,
) -> Any:
    if not records:
        raise RegionResourceV6CandidateError(
            "v6_actor_batch_must_not_be_empty"
        )
    losses = []
    for record in records:
        loss, _ = _v6_actor_loss(
            model,
            record,
            balance=balance,
            config=config,
        )
        losses.append(loss)
    loss_tensor = torch.stack(losses)
    return loss_tensor.mean()


def _v6_actor_step(
    model: V6EdgeTransferGraphActorCritic,
    optimizer: Any,
    records: Sequence[Any],
    *,
    balance: RegionResourceV6ClassBalance,
    config: RegionResourceV6BuildConfig,
) -> float:
    optimizer.zero_grad()
    loss = _weighted_v6_loss(
        model,
        records,
        balance=balance,
        config=config,
    )
    if not bool(torch.isfinite(loss).item()):
        raise RegionResourceV6CandidateError("v6_actor_loss_nonfinite")
    loss.backward()
    torch.nn.utils.clip_grad_norm_(
        model.parameters(),
        config.max_grad_norm,
    )
    optimizer.step()
    if not _model_parameters_finite(model):
        raise RegionResourceV6CandidateError("v6_actor_update_nonfinite")
    return float(loss.detach().cpu())


def _mean_v6_actor_loss(
    model: V6EdgeTransferGraphActorCritic,
    records: Sequence[Any],
    *,
    balance: RegionResourceV6ClassBalance,
    config: RegionResourceV6BuildConfig,
) -> float:
    model.eval()
    with torch.no_grad():
        loss = _weighted_v6_loss(
            model,
            records,
            balance=balance,
            config=config,
        )
    value = float(loss.cpu())
    if not isfinite(value):
        raise RegionResourceV6CandidateError(
            "v6_validation_loss_nonfinite"
        )
    return value


def _directed_transfer_signature(recommendation: Any) -> tuple[
    tuple[str, str, str, int], ...
]:
    return tuple(
        sorted(
            (
                transfer.edge_id,
                transfer.source_region_id,
                transfer.target_region_id,
                int(transfer.resource_count),
            )
            for transfer in recommendation.transfers
        )
    )


def _directed_edge_identity_signature(recommendation: Any) -> tuple[
    tuple[str, str, str], ...
]:
    return tuple(
        sorted(
            (
                transfer.edge_id,
                transfer.source_region_id,
                transfer.target_region_id,
            )
            for transfer in recommendation.transfers
        )
    )


def _v6_actor_metrics(
    model: V6EdgeTransferGraphActorCritic,
    records: Sequence[Any],
    *,
    projector: DeterministicResourceProjector,
    rule_policy: RuleRegionResourcePolicy,
) -> dict[str, Any]:
    """Audit projected actions and directed transfer edges."""

    policy = LearnedRegionResourcePolicy(
        model,
        _PolicyIdentity(REGION_RESOURCE_V6_MODEL_VERSION, "0" * 64),
    )
    positive_count = sum(bool(record.target_positive) for record in records)
    negative_count = len(records) - positive_count
    positive_exact_hits = 0
    negative_exact_hits = 0
    directed_edge_exact_hits = 0
    positive_no_transfer_raw = 0
    positive_no_transfer_projected = 0
    executable_difference_count = 0
    projection_rejection_count = 0
    invalid_executable_difference_count = 0
    edge_true_positive = 0
    edge_false_positive = 0
    edge_false_negative = 0
    edge_true_negative = 0
    failure_reasons: dict[str, int] = {}
    for record in records:
        raw = policy.recommend_raw(record.snapshot)
        projected = projector.project(record.snapshot, raw)
        target_edges = _directed_transfer_signature(record.target)
        raw_edges = _directed_transfer_signature(raw)
        target_edge_identities = set(
            _directed_edge_identity_signature(record.target)
        )
        raw_edge_identities = set(
            _directed_edge_identity_signature(raw)
        )
        graph_edge_keys = {
            (
                edge_ref.edge_id,
                edge_ref.source_region_id,
                edge_ref.target_region_id,
            )
            for edge_ref in record.sample.graph.edge_refs
        }
        edge_true_positive += len(
            target_edge_identities & raw_edge_identities
        )
        edge_false_positive += len(
            raw_edge_identities - target_edge_identities
        )
        edge_false_negative += len(
            target_edge_identities - raw_edge_identities
        )
        edge_true_negative += sum(
            1
            for edge_identity in graph_edge_keys
            if edge_identity
            not in target_edge_identities | raw_edge_identities
        )
        directed_edge_exact = (
            raw_edge_identities == target_edge_identities
        )
        directed_edge_exact_hits += int(
            record.target_positive and directed_edge_exact
        )
        positive_no_transfer_raw += int(
            record.target_positive and not raw.transfers
        )
        positive_no_transfer_projected += int(
            record.target_positive and not projected.transfers
        )
        candidate_advisory = projector.build_advisory_contract(
            record.snapshot,
            projected,
        )
        candidate_signature, _ = executable_signature(candidate_advisory)
        executable = (
            candidate_signature
            != record.rule_executable_signature_sha256
        )
        executable_difference_count += int(executable)
        exact_target = (
            candidate_signature
            == record.target_executable_signature_sha256
        )
        projection_rejected = bool(projected.projection_rejections)
        projection_rejection_count += int(projection_rejected)
        valid = True
        invariant_reasons: tuple[str, ...] = ()
        if executable:
            baseline = rule_policy.recommend(record.snapshot)
            valid, invariant_reasons = evaluate_v4_intervention_invariants(
                record.snapshot,
                projected,
                baseline,
                gate=REGION_RESOURCE_V4_INTERVENTION_GATE,
                projector=projector,
                formal_decision=None,
            )
            invalid_executable_difference_count += int(not valid)
        positive_hit = bool(
            record.target_positive
            and executable
            and exact_target
            and valid
            and not projection_rejected
        )
        negative_hit = bool(
            not record.target_positive
            and not executable
            and exact_target
            and not projection_rejected
        )
        positive_exact_hits += int(positive_hit)
        negative_exact_hits += int(negative_hit)
        reasons: list[str] = []
        if record.target_positive and not raw.transfers:
            reasons.append("positive_raw_no_transfer")
        if record.target_positive and raw_edges != target_edges:
            reverse_exists = any(
                predicted[0] == expected[0]
                and predicted[1] == expected[2]
                and predicted[2] == expected[1]
                for predicted in raw_edges
                for expected in target_edges
            )
            reasons.append(
                "wrong_transfer_direction"
                if reverse_exists
                else "wrong_transfer_edge_or_count"
            )
        if not record.target_positive and raw.transfers:
            reasons.append("negative_false_transfer")
        if projection_rejected:
            reasons.append("projection_rejected")
            reasons.extend(projected.projection_rejections)
        if executable and not valid:
            reasons.append("projected_action_invariant_failure")
            reasons.extend(invariant_reasons)
        if record.target_positive and not positive_hit:
            reasons.append("positive_exact_projected_action_miss")
        if not record.target_positive and not negative_hit:
            reasons.append("negative_baseline_action_miss")
        for reason in dict.fromkeys(reasons):
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    positive_rate = (
        positive_exact_hits / positive_count if positive_count else 0.0
    )
    negative_rate = (
        negative_exact_hits / negative_count if negative_count else 0.0
    )
    directed_rate = (
        directed_edge_exact_hits / positive_count if positive_count else 0.0
    )
    no_transfer_bias = (
        positive_no_transfer_projected / positive_count
        if positive_count
        else 1.0
    )
    nondegenerate = bool(
        positive_count > 0
        and negative_count > 0
        and positive_exact_hits > 0
        and directed_edge_exact_hits > 0
        and negative_exact_hits > 0
        and executable_difference_count > 0
    )
    checkpoint_failures = []
    if positive_count <= 0:
        checkpoint_failures.append("positive_class_missing")
    elif positive_exact_hits <= 0:
        checkpoint_failures.append("positive_exact_action_hit_missing")
    if directed_edge_exact_hits <= 0:
        checkpoint_failures.append("correct_directed_edge_hit_missing")
    if negative_count <= 0:
        checkpoint_failures.append("negative_class_missing")
    elif negative_exact_hits <= 0:
        checkpoint_failures.append("negative_baseline_action_hit_missing")
    if executable_difference_count <= 0:
        checkpoint_failures.append("all_no_transfer_checkpoint")
    return {
        "sample_count": len(records),
        "target_positive_count": positive_count,
        "target_negative_count": negative_count,
        "positive_exact_projected_action_hit_count": positive_exact_hits,
        "negative_exact_baseline_action_hit_count": negative_exact_hits,
        "correct_directed_transfer_edge_hit_count": directed_edge_exact_hits,
        "positive_exact_projected_action_hit_rate": positive_rate,
        "negative_exact_baseline_action_hit_rate": negative_rate,
        "correct_directed_transfer_edge_hit_rate": directed_rate,
        "positive_raw_no_transfer_count": positive_no_transfer_raw,
        "positive_projected_no_transfer_count": (
            positive_no_transfer_projected
        ),
        "no_transfer_bias": no_transfer_bias,
        "actor_executable_difference_count": executable_difference_count,
        "projection_rejection_count": projection_rejection_count,
        "invalid_executable_difference_count": (
            invalid_executable_difference_count
        ),
        "edge_true_positive_count": edge_true_positive,
        "edge_false_positive_count": edge_false_positive,
        "edge_false_negative_count": edge_false_negative,
        "edge_true_negative_count": edge_true_negative,
        "nondegenerate_checkpoint": nondegenerate,
        "checkpoint_failure_reasons": checkpoint_failures,
        "failure_reason_inventory": dict(sorted(failure_reasons.items())),
    }


def _v6_checkpoint_selection_key(
    metrics: Mapping[str, Any],
    *,
    validation_loss: float,
    epoch: int,
) -> tuple[int, float, float, float, float, int, int, float, int]:
    """Rank projected behavior before the differentiable loss."""

    if not isfinite(float(validation_loss)):
        raise RegionResourceV6CandidateError(
            "v6_checkpoint_loss_nonfinite"
        )
    if type(epoch) is not int or epoch <= 0:
        raise RegionResourceV6CandidateError(
            "v6_checkpoint_epoch_invalid"
        )
    return (
        int(bool(metrics["nondegenerate_checkpoint"])),
        float(metrics["positive_exact_projected_action_hit_rate"]),
        float(metrics["correct_directed_transfer_edge_hit_rate"]),
        float(metrics["negative_exact_baseline_action_hit_rate"]),
        -float(metrics["no_transfer_bias"]),
        -int(metrics["projection_rejection_count"]),
        -int(metrics["invalid_executable_difference_count"]),
        -float(validation_loss),
        -epoch,
    )


def train_v6_actor(
    loaded: LoadedRegionLearningDataset,
    *,
    config: RegionResourceV6BuildConfig | None = None,
) -> tuple[V6EdgeTransferGraphActorCritic, dict[str, Any]]:
    """Fit TRAIN and select a checkpoint with VALIDATION only."""

    _require_torch()
    resolved = config or RegionResourceV6BuildConfig()
    torch.set_num_threads(resolved.torch_num_threads)
    random.seed(resolved.random_seed)
    torch.manual_seed(resolved.random_seed)
    projector = DeterministicResourceProjector(_V4_PROJECTION)
    rule_policy = RuleRegionResourcePolicy(
        _V4_RULE_CONFIG,
        projector=projector,
    )
    train_records = _v4_actor_records(
        loaded,
        split=RegionLearningSplit.TRAIN,
        projector=projector,
        rule_policy=rule_policy,
    )
    validation_records = _v4_actor_records(
        loaded,
        split=RegionLearningSplit.VALIDATION,
        projector=projector,
        rule_policy=rule_policy,
    )
    if not train_records or not validation_records:
        raise RegionResourceV6CandidateError(
            "v6_train_or_validation_samples_unavailable"
        )
    balance = derive_v6_class_balance(train_records)
    model = V6EdgeTransferGraphActorCritic(
        hidden_dim=resolved.hidden_dim,
        message_passing_steps=resolved.message_passing_steps,
    )
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=resolved.learning_rate,
        weight_decay=resolved.weight_decay,
    )
    generator = torch.Generator(device="cpu")
    generator.manual_seed(resolved.random_seed)
    best_key: tuple[int, float, float, float, float, int, int, float, int] | None = None
    best_epoch = 0
    best_loss = float("inf")
    best_state: dict[str, Any] | None = None
    no_improvement = 0
    qualified_seen = False
    history: list[dict[str, Any]] = []
    for epoch in range(1, resolved.epochs + 1):
        model.train()
        order = torch.randperm(
            len(train_records),
            generator=generator,
        ).tolist()
        batch_losses = []
        for offset in range(0, len(order), resolved.batch_size):
            batch = tuple(
                train_records[index]
                for index in order[offset : offset + resolved.batch_size]
            )
            batch_losses.append(
                _v6_actor_step(
                    model,
                    optimizer,
                    batch,
                    balance=balance,
                    config=resolved,
                )
            )
        validation_loss = _mean_v6_actor_loss(
            model,
            validation_records,
            balance=balance,
            config=resolved,
        )
        validation_metrics = _v6_actor_metrics(
            model,
            validation_records,
            projector=projector,
            rule_policy=rule_policy,
        )
        selection_key = _v6_checkpoint_selection_key(
            validation_metrics,
            validation_loss=validation_loss,
            epoch=epoch,
        )
        history.append(
            {
                "epoch": epoch,
                "mean_train_batch_loss": (
                    sum(batch_losses) / len(batch_losses)
                ),
                "validation_train_weighted_loss": validation_loss,
                "validation_positive_exact_action_hits": (
                    validation_metrics[
                        "positive_exact_projected_action_hit_count"
                    ]
                ),
                "validation_directed_edge_hits": (
                    validation_metrics[
                        "correct_directed_transfer_edge_hit_count"
                    ]
                ),
                "validation_negative_baseline_action_hits": (
                    validation_metrics[
                        "negative_exact_baseline_action_hit_count"
                    ]
                ),
                "validation_no_transfer_bias": (
                    validation_metrics["no_transfer_bias"]
                ),
                "validation_projection_rejections": (
                    validation_metrics["projection_rejection_count"]
                ),
                "nondegenerate_checkpoint": (
                    validation_metrics["nondegenerate_checkpoint"]
                ),
            }
        )
        if best_key is None or selection_key > best_key:
            best_key = selection_key
            best_epoch = epoch
            best_loss = validation_loss
            best_state = {
                name: value.detach().cpu().clone()
                for name, value in model.state_dict().items()
            }
            no_improvement = 0
        elif qualified_seen:
            no_improvement += 1
        qualified_seen = bool(
            qualified_seen or validation_metrics["nondegenerate_checkpoint"]
        )
        if (
            qualified_seen
            and no_improvement >= resolved.early_stopping_patience
        ):
            break
    if best_state is None:
        raise RegionResourceV6CandidateError(
            "v6_training_produced_no_checkpoint"
        )
    model.load_state_dict(best_state, strict=True)
    model.eval()
    if not _model_parameters_finite(model):
        raise RegionResourceV6CandidateError(
            "v6_training_produced_nonfinite_model"
        )
    train_metrics = _v6_actor_metrics(
        model,
        train_records,
        projector=projector,
        rule_policy=rule_policy,
    )
    validation_metrics = _v6_actor_metrics(
        model,
        validation_records,
        projector=projector,
        rule_policy=rule_policy,
    )
    if not train_metrics["nondegenerate_checkpoint"]:
        raise RegionResourceV6CandidateError(
            "v6_train_nondegenerate_checkpoint_unavailable:"
            + ",".join(train_metrics["checkpoint_failure_reasons"])
        )
    if not validation_metrics["nondegenerate_checkpoint"]:
        raise RegionResourceV6CandidateError(
            "v6_validation_nondegenerate_checkpoint_unavailable:"
            + ",".join(validation_metrics["checkpoint_failure_reasons"])
        )
    state_sha256 = _model_state_content_sha256(model)
    return model, {
        "schema": REGION_RESOURCE_V6_AUDIT_SCHEMA,
        "candidate_id": resolved.candidate_id,
        "model_version": resolved.model_version,
        "fit_split": RegionLearningSplit.TRAIN.value,
        "checkpoint_selection_split": RegionLearningSplit.VALIDATION.value,
        "train_sample_count": len(train_records),
        "validation_sample_count": len(validation_records),
        "train_fit_count": len(train_records),
        "validation_fit_count": 0,
        "validation_weight_fit_count": 0,
        "validation_hyperparameter_fit_count": 0,
        "test_payload_read_count": 0,
        "test_payload_fit_count": 0,
        "formal_holdout_payload_read_count": 0,
        "formal_holdout_payload_fit_count": 0,
        "source_evaluation_payload_read_count": 0,
        "source_evaluation_payload_fit_count": 0,
        "best_epoch": best_epoch,
        "epochs_completed": len(history),
        "best_validation_loss": best_loss,
        "checkpoint_selection_rule": (
            "require non-degenerate projected behavior; maximize exact "
            "projected positive action; maximize correct directed transfer "
            "edge; preserve negative baseline action; minimize no-transfer "
            "bias, projection rejection, invariant failure, fixed "
            "TRAIN-weighted "
            "validation loss, and epoch"
        ),
        "class_balance": balance.to_dict(),
        "train_actor_audit": train_metrics,
        "validation_actor_audit": validation_metrics,
        "history": history,
        "model_state_content_sha256": state_sha256,
        "model_parameter_count": sum(
            int(parameter.numel()) for parameter in model.parameters()
        ),
        "model_parameters_finite": True,
        "actor_fit_is_behavior_cloning": True,
        "explicit_edge_activation_supervision": True,
        "directed_edge_ranking_supervision": True,
        "positive_edge_count_supervision": True,
        "ppo_used": False,
        "confidence_calibration_available": False,
        "formal_evaluation_authorized": False,
        "permissions": RegionResourceV6Permissions().to_dict(),
    }


def audit_v6_training_source(
    loaded: LoadedRegionLearningDataset,
    *,
    frozen_v4_model: SharedRegionGraphActorCritic,
) -> dict[str, Any]:
    """Produce a TRAIN/VALIDATION-only, reproducible root-cause audit."""

    projector = DeterministicResourceProjector(_V4_PROJECTION)
    rule_policy = RuleRegionResourcePolicy(
        _V4_RULE_CONFIG,
        projector=projector,
    )
    split_payload: dict[str, Any] = {}
    for split in (
        RegionLearningSplit.TRAIN,
        RegionLearningSplit.VALIDATION,
    ):
        records = _v4_actor_records(
            loaded,
            split=split,
            projector=projector,
            rule_policy=rule_policy,
        )
        positive_records = [
            record for record in records if record.target_positive
        ]
        directions: dict[str, int] = {}
        transfer_frame_count = 0
        for record in records:
            transfer_frame_count += int(bool(record.target.transfers))
            for transfer in record.target.transfers:
                key = (
                    f"{transfer.source_region_id}->{transfer.target_region_id}"
                )
                directions[key] = directions.get(key, 0) + 1
        positive_edges = sum(
            record.nonzero_edge_target_count for record in records
        )
        edges = sum(record.edge_target_count for record in records)
        split_payload[split.value] = {
            "sample_count": len(records),
            "positive_executable_action_count": len(positive_records),
            "negative_no_difference_action_count": (
                len(records) - len(positive_records)
            ),
            "positive_edge_count": positive_edges,
            "zero_edge_count": edges - positive_edges,
            "positive_edge_fraction": positive_edges / edges,
            "transfer_frame_count": transfer_frame_count,
            "directed_transfer_inventory": dict(sorted(directions.items())),
            "unique_directed_transfer_count": len(directions),
            "frozen_v4_actor_audit": _v4_actor_metrics(
                frozen_v4_model,
                records,
                projector=projector,
                rule_policy=rule_policy,
            ),
        }
    train_records = _v4_actor_records(
        loaded,
        split=RegionLearningSplit.TRAIN,
        projector=projector,
        rule_policy=rule_policy,
    )
    balance = derive_v6_class_balance(train_records)
    legacy_positive_mass = (
        balance.positive_edge_count
        * min(balance.raw_positive_edge_ratio, 32.0)
    )
    legacy_zero_mass = balance.zero_edge_count
    return {
        "audit_scope": "TRAIN labels and VALIDATION checkpoint audit only",
        "split_inventory": split_payload,
        "root_cause_findings": {
            "single_continuous_edge_head_couples_activation_direction_and_count": (
                True
            ),
            "legacy_edge_loss_kind": "weighted edge mean squared error",
            "legacy_positive_edge_weight_cap": 32.0,
            "train_raw_zero_to_positive_edge_ratio": (
                balance.raw_positive_edge_ratio
            ),
            "legacy_positive_weight_clipped": bool(
                balance.raw_positive_edge_ratio > 32.0
            ),
            "legacy_effective_positive_edge_mass": legacy_positive_mass,
            "legacy_effective_zero_edge_mass": legacy_zero_mass,
            "legacy_zero_to_positive_effective_mass_ratio": (
                legacy_zero_mass / legacy_positive_mass
            ),
            "explicit_activation_loss_available_in_v4": False,
            "directed_edge_ranking_loss_available_in_v4": False,
            "positive_edge_count_loss_available_in_v4": False,
            "source_independent_generalization_established": False,
        },
        "forbidden_data_usage": {
            "test_payload_read_count": 0,
            "formal_holdout_seed_use_count": 0,
            "source_evaluation_seed_use_count": 0,
            "formal_holdout_seeds": "1000-1019",
            "source_evaluation_seeds": "3008-3039",
        },
    }


def build_region_resource_v6_transfer_candidate(
    frozen_v4_candidate_root: str | Path,
    output_root: str | Path,
    *,
    config: RegionResourceV6BuildConfig | None = None,
) -> dict[str, Any]:
    """Build one version-isolated v6 actor candidate."""

    _require_torch()
    resolved = config or RegionResourceV6BuildConfig()
    source = Path(frozen_v4_candidate_root).resolve()
    destination = Path(output_root).resolve()
    if source.name != REGION_RESOURCE_V4_CANDIDATE_ID:
        raise RegionResourceV6CandidateError(
            "v6_frozen_v4_directory_identity_mismatch"
        )
    if destination.name != resolved.candidate_id:
        raise RegionResourceV6CandidateError(
            "v6_candidate_directory_identity_mismatch"
        )
    if "model_registry" in destination.parts:
        raise RegionResourceV6CandidateError(
            "v6_unregistered_candidate_registry_output_forbidden"
        )
    if destination == source or source in destination.parents:
        raise RegionResourceV6CandidateError(
            "v6_candidate_output_inside_frozen_v4_forbidden"
        )
    if destination.exists() or destination.is_symlink():
        raise RegionResourceV6CandidateError(
            "v6_candidate_output_already_exists"
        )
    source_binding = _validate_frozen_v4_source(source)
    source_tree_before = _tree_sha256(source)
    try:
        frozen_v4_bundle = load_region_resource_model_bundle(
            source / "bundle",
            expected_model_version=(
                "d4-region-resource-graph-bc-executable-transfer-v4"
            ),
            expected_state_dict_sha256=(
                REGION_RESOURCE_V5_BASE_V4_MODEL_STATE_SHA256
            ),
            map_location="cpu",
            require_training_dataset_manifest=True,
        )
        loaded = load_region_learning_dataset_splits(
            source / "development_dataset",
            splits=(
                RegionLearningSplit.TRAIN,
                RegionLearningSplit.VALIDATION,
            ),
        )
    except Exception as exc:
        raise RegionResourceV6CandidateError(
            f"v6_frozen_training_source_load_failed:{type(exc).__name__}:{exc}"
        ) from exc
    _validate_loaded_splits(loaded)
    root_cause = audit_v6_training_source(
        loaded,
        frozen_v4_model=frozen_v4_bundle.model,
    )
    model, training_audit = train_v6_actor(loaded, config=resolved)
    training_audit["root_cause_audit"] = root_cause
    training_audit["source_binding"] = source_binding
    training_audit["content_sha256"] = _canonical_sha256(training_audit)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_parent = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.build-",
            dir=destination.parent,
        )
    )
    staging = temporary_parent / destination.name
    staging.mkdir()
    try:
        _write_json(staging / REGION_RESOURCE_V6_SOURCE_FILENAME, source_binding)
        _write_json(
            staging / REGION_RESOURCE_V6_CONFIG_FILENAME,
            resolved.to_dict(),
        )
        _write_json(
            staging / REGION_RESOURCE_V6_AUDIT_FILENAME,
            training_audit,
        )
        bundle_manifest = _save_v6_model_bundle(
            model,
            staging / "bundle",
            config=resolved,
            training_audit=training_audit,
        )
        loaded_model, loaded_manifest = _load_v6_model_bundle(
            staging / "bundle",
            expected_model_version=resolved.model_version,
            expected_state_file_sha256=bundle_manifest[
                "state_dict_file_sha256"
            ],
        )
        if (
            loaded_manifest["content_sha256"]
            != bundle_manifest["content_sha256"]
            or _model_state_content_sha256(loaded_model)
            != training_audit["model_state_content_sha256"]
        ):
            raise RegionResourceV6CandidateError(
                "v6_saved_model_content_identity_mismatch"
            )
        artifact_files = {
            str(path.relative_to(staging)): _sha256_file(path)
            for path in sorted(staging.rglob("*"))
            if path.is_file()
        }
        manifest = {
            "schema": REGION_RESOURCE_V6_CANDIDATE_SCHEMA,
            "candidate_id": resolved.candidate_id,
            "model_version": resolved.model_version,
            "base_v4_candidate_id": REGION_RESOURCE_V4_CANDIDATE_ID,
            "base_v4_manifest_content_sha256": (
                REGION_RESOURCE_V5_BASE_V4_MANIFEST_CONTENT_SHA256
            ),
            "base_v4_model_state_sha256": (
                REGION_RESOURCE_V5_BASE_V4_MODEL_STATE_SHA256
            ),
            "dataset_sha256": REGION_RESOURCE_V5_BASE_V4_DATASET_SHA256,
            "dataset_split_sha256": (
                REGION_RESOURCE_V5_BASE_V4_SPLIT_SHA256
            ),
            "training_audit_content_sha256": training_audit[
                "content_sha256"
            ],
            "model_state_content_sha256": training_audit[
                "model_state_content_sha256"
            ],
            "bundle_state_file_sha256": (
                bundle_manifest["state_dict_file_sha256"]
            ),
            "artifact_files": artifact_files,
            "fixed_minimum_confidence": (
                REGION_RESOURCE_V6_FIXED_MINIMUM_CONFIDENCE
            ),
            "lifecycle_stage": MODEL_LIFECYCLE_DEVELOPMENT,
            "maximum_advisor_mode": MODEL_MAXIMUM_MODE_SHADOW,
            "candidate_status": "unregistered_edge_transfer_development",
            "confidence_calibration_status": "not_started_actor_must_freeze_first",
            "development_only": True,
            "shadow_only": True,
            "admission_closed": True,
            "rule_fallback_required": True,
            "formal_holdout_evaluated": False,
            "source_independent_evaluation_completed": False,
            "runtime_preflight_completed": False,
            "permissions": RegionResourceV6Permissions().to_dict(),
        }
        manifest["content_sha256"] = _canonical_sha256(manifest)
        _write_json(
            staging / REGION_RESOURCE_V6_CANDIDATE_FILENAME,
            manifest,
        )
        if _tree_sha256(source) != source_tree_before:
            raise RegionResourceV6CandidateError(
                "v6_build_modified_frozen_v4_source"
            )
        staging.replace(destination)
        return manifest
    except Exception:
        shutil.rmtree(temporary_parent, ignore_errors=True)
        raise
    finally:
        if temporary_parent.exists():
            shutil.rmtree(temporary_parent, ignore_errors=True)


def _validate_loaded_splits(loaded: LoadedRegionLearningDataset) -> None:
    splits = {episode.split for episode in loaded.episode_records}
    if splits != {
        RegionLearningSplit.TRAIN,
        RegionLearningSplit.VALIDATION,
    }:
        raise RegionResourceV6CandidateError(
            "v6_loaded_payload_must_be_train_validation_only"
        )
    for episode in loaded.episode_records:
        seed = int(episode.source.seed)
        if seed in REGION_RESOURCE_V6_FORBIDDEN_FORMAL_HOLDOUT_SEEDS:
            raise RegionResourceV6CandidateError(
                "v6_formal_holdout_seed_read_forbidden"
            )
        if seed in REGION_RESOURCE_V6_FORBIDDEN_SOURCE_EVALUATION_SEEDS:
            raise RegionResourceV6CandidateError(
                "v6_source_evaluation_seed_read_forbidden"
            )


def _validate_frozen_v4_source(source: Path) -> dict[str, Any]:
    manifest_path = source / REGION_RESOURCE_V4_CANDIDATE_FILENAME
    if not manifest_path.is_file():
        raise RegionResourceV6CandidateError(
            "v6_frozen_v4_manifest_missing"
        )
    if (
        _sha256_file(manifest_path)
        != REGION_RESOURCE_V5_BASE_V4_MANIFEST_FILE_SHA256
    ):
        raise RegionResourceV6CandidateError(
            "v6_frozen_v4_manifest_file_identity_mismatch"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("content_sha256")
        != REGION_RESOURCE_V5_BASE_V4_MANIFEST_CONTENT_SHA256
        or manifest.get("dataset_sha256")
        != REGION_RESOURCE_V5_BASE_V4_DATASET_SHA256
        or manifest.get("dataset_split_sha256")
        != REGION_RESOURCE_V5_BASE_V4_SPLIT_SHA256
        or manifest.get("model_state_sha256")
        != REGION_RESOURCE_V5_BASE_V4_MODEL_STATE_SHA256
    ):
        raise RegionResourceV6CandidateError(
            "v6_frozen_v4_content_identity_mismatch"
        )
    return {
        "source_kind": "frozen_v4_train_validation_dataset",
        "base_v4_candidate_id": REGION_RESOURCE_V4_CANDIDATE_ID,
        "base_v4_manifest_file_sha256": (
            REGION_RESOURCE_V5_BASE_V4_MANIFEST_FILE_SHA256
        ),
        "base_v4_manifest_content_sha256": (
            REGION_RESOURCE_V5_BASE_V4_MANIFEST_CONTENT_SHA256
        ),
        "base_v4_model_state_sha256": (
            REGION_RESOURCE_V5_BASE_V4_MODEL_STATE_SHA256
        ),
        "dataset_sha256": REGION_RESOURCE_V5_BASE_V4_DATASET_SHA256,
        "dataset_split_sha256": REGION_RESOURCE_V5_BASE_V4_SPLIT_SHA256,
        "payload_splits_read": [
            RegionLearningSplit.TRAIN.value,
            RegionLearningSplit.VALIDATION.value,
        ],
        "test_payload_read_count": 0,
        "formal_holdout_payload_read_count": 0,
        "source_evaluation_payload_read_count": 0,
        "v5_candidate_consumed": False,
    }


def _save_v6_model_bundle(
    model: V6EdgeTransferGraphActorCritic,
    bundle_root: Path,
    *,
    config: RegionResourceV6BuildConfig,
    training_audit: Mapping[str, Any],
) -> dict[str, Any]:
    bundle_root.mkdir(parents=True, exist_ok=False)
    state_path = bundle_root / "state_dict.pt"
    temporary_state = bundle_root / "state_dict.pt.tmp"
    _write_v6_state_dict(temporary_state, model.state_dict())
    temporary_state.replace(state_path)
    manifest = {
        "schema": REGION_RESOURCE_V6_BUNDLE_SCHEMA,
        "architecture": (
            "shared-region-graph-explicit-edge-activation-actor-v6"
        ),
        "model_version": config.model_version,
        "hidden_dim": config.hidden_dim,
        "message_passing_steps": config.message_passing_steps,
        "node_feature_dim": len(NODE_FEATURE_NAMES),
        "edge_feature_dim": len(EDGE_FEATURE_NAMES),
        "node_action_dim": NODE_ACTION_DIM,
        "edge_action_dim": EDGE_ACTION_DIM,
        "state_dict_file": state_path.name,
        "state_dict_format": "d4-v6-canonical-tensor-stream-v1",
        "state_dict_file_sha256": _sha256_file(state_path),
        "model_state_content_sha256": _model_state_content_sha256(model),
        "created_at_utc": config.created_at_utc,
        "training_audit_content_sha256": training_audit["content_sha256"],
        "lifecycle_stage": MODEL_LIFECYCLE_DEVELOPMENT,
        "maximum_advisor_mode": MODEL_MAXIMUM_MODE_SHADOW,
        "runtime_loader_registered": False,
        "runtime_confidence_gate_available": False,
        "admission_closed": True,
        "rule_fallback_required": True,
    }
    manifest["content_sha256"] = _canonical_sha256(manifest)
    _write_json(bundle_root / "manifest.json", manifest)
    return manifest


def _load_v6_model_bundle(
    bundle_root: Path,
    *,
    expected_model_version: str,
    expected_state_file_sha256: str,
) -> tuple[V6EdgeTransferGraphActorCritic, dict[str, Any]]:
    manifest_path = bundle_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    content_sha256 = manifest.pop("content_sha256", None)
    if content_sha256 != _canonical_sha256(manifest):
        raise RegionResourceV6CandidateError(
            "v6_bundle_manifest_content_identity_mismatch"
        )
    manifest["content_sha256"] = content_sha256
    if (
        manifest.get("schema") != REGION_RESOURCE_V6_BUNDLE_SCHEMA
        or manifest.get("model_version") != expected_model_version
        or manifest.get("runtime_loader_registered") is not False
        or manifest.get("runtime_confidence_gate_available") is not False
    ):
        raise RegionResourceV6CandidateError(
            "v6_bundle_contract_mismatch"
        )
    state_path = bundle_root / str(manifest["state_dict_file"])
    state_file_sha256 = _sha256_file(state_path)
    if (
        state_file_sha256 != expected_state_file_sha256
        or state_file_sha256 != manifest["state_dict_file_sha256"]
    ):
        raise RegionResourceV6CandidateError(
            "v6_bundle_state_file_identity_mismatch"
        )
    if manifest.get("state_dict_format") != (
        "d4-v6-canonical-tensor-stream-v1"
    ):
        raise RegionResourceV6CandidateError(
            "v6_bundle_state_format_mismatch"
        )
    state = _read_v6_state_dict(state_path)
    model = V6EdgeTransferGraphActorCritic(
        hidden_dim=int(manifest["hidden_dim"]),
        message_passing_steps=int(manifest["message_passing_steps"]),
    )
    model.load_state_dict(state, strict=True)
    model.eval()
    if (
        not _model_parameters_finite(model)
        or _model_state_content_sha256(model)
        != manifest["model_state_content_sha256"]
    ):
        raise RegionResourceV6CandidateError(
            "v6_bundle_model_content_identity_mismatch"
        )
    return model, manifest


def _write_v6_state_dict(path: Path, state: Mapping[str, Any]) -> None:
    """Write a deterministic, unregistered v6 tensor stream."""

    with path.open("wb") as handle:
        handle.write(REGION_RESOURCE_V6_STATE_MAGIC)
        handle.write(len(state).to_bytes(4, byteorder="big", signed=False))
        for name, tensor in sorted(state.items()):
            value = tensor.detach().cpu().contiguous()
            raw = value.numpy().tobytes(order="C")
            metadata = json.dumps(
                {
                    "name": name,
                    "dtype": str(value.dtype),
                    "shape": list(value.shape),
                    "byte_count": len(raw),
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("ascii")
            handle.write(
                len(metadata).to_bytes(4, byteorder="big", signed=False)
            )
            handle.write(metadata)
            handle.write(raw)


def _read_v6_state_dict(path: Path) -> dict[str, Any]:
    dtype_by_name = {
        "torch.float16": torch.float16,
        "torch.float32": torch.float32,
        "torch.float64": torch.float64,
        "torch.int8": torch.int8,
        "torch.int16": torch.int16,
        "torch.int32": torch.int32,
        "torch.int64": torch.int64,
        "torch.uint8": torch.uint8,
        "torch.bool": torch.bool,
    }
    state: dict[str, Any] = {}
    with path.open("rb") as handle:
        if handle.read(len(REGION_RESOURCE_V6_STATE_MAGIC)) != (
            REGION_RESOURCE_V6_STATE_MAGIC
        ):
            raise RegionResourceV6CandidateError(
                "v6_state_magic_mismatch"
            )
        tensor_count = int.from_bytes(
            _read_exact(handle, 4),
            byteorder="big",
            signed=False,
        )
        for _ in range(tensor_count):
            metadata_length = int.from_bytes(
                _read_exact(handle, 4),
                byteorder="big",
                signed=False,
            )
            if metadata_length <= 0 or metadata_length > 1024 * 1024:
                raise RegionResourceV6CandidateError(
                    "v6_state_metadata_length_invalid"
                )
            metadata = json.loads(
                _read_exact(handle, metadata_length).decode("ascii")
            )
            name = str(metadata["name"])
            dtype_name = str(metadata["dtype"])
            shape = tuple(int(value) for value in metadata["shape"])
            byte_count = int(metadata["byte_count"])
            if (
                name in state
                or dtype_name not in dtype_by_name
                or any(value < 0 for value in shape)
                or byte_count < 0
            ):
                raise RegionResourceV6CandidateError(
                    "v6_state_tensor_metadata_invalid"
                )
            raw = bytearray(_read_exact(handle, byte_count))
            tensor = torch.frombuffer(
                raw,
                dtype=dtype_by_name[dtype_name],
            ).clone()
            expected_count = 1
            for value in shape:
                expected_count *= value
            if int(tensor.numel()) != expected_count:
                raise RegionResourceV6CandidateError(
                    "v6_state_tensor_shape_mismatch"
                )
            state[name] = tensor.reshape(shape)
        if handle.read(1):
            raise RegionResourceV6CandidateError(
                "v6_state_trailing_bytes"
            )
    return state


def _read_exact(handle: Any, size: int) -> bytes:
    value = handle.read(size)
    if len(value) != size:
        raise RegionResourceV6CandidateError(
            "v6_state_truncated"
        )
    return value


def _model_state_content_sha256(
    model: torch.nn.Module,
) -> str:
    digest = sha256()
    for name, tensor in sorted(model.state_dict().items()):
        value = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(
            json.dumps(list(value.shape), separators=(",", ":")).encode(
                "ascii"
            )
        )
        digest.update(value.numpy().tobytes(order="C"))
    return digest.hexdigest()


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


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    inventory = {
        str(path.relative_to(root)): _sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    return _canonical_sha256(inventory)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA256")


def _require_torch() -> None:
    if torch is None:
        raise RegionResourceV6CandidateError(
            "v6_transfer_candidate_requires_torch"
        )
