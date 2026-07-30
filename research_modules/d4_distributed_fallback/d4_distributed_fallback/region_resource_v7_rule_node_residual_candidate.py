"""Unregistered D4 v7 rule-node and learned-transfer residual candidate.

The v7 actor does not predict regional node actions. For every snapshot, the
deterministic R0 policy supplies the ownership-bound node action fields and the
baseline transfer set. The actor may override at most one directed transfer
edge and its absolute resource count. The combined proposal still passes the
existing deterministic projector and v4 intervention invariants.

Only TRAIN payloads fit model parameters and class/source weights. VALIDATION
selects a checkpoint from projected behavior. TEST payloads, formal holdout
seeds, prior evaluation seeds, and the reserved v7 independent-evaluation
seeds are rejected.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import random
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from .region_resource import (
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceRecommendation,
    RegionTransferSuggestion,
    RuleRegionResourcePolicy,
)
from .region_resource_dataset import (
    LoadedRegionLearningDataset,
    RegionLearningSplit,
    load_region_learning_dataset_splits,
)
from .region_resource_learning import (
    EDGE_FEATURE_NAMES,
    MODEL_LIFECYCLE_DEVELOPMENT,
    MODEL_MAXIMUM_MODE_SHADOW,
    NODE_FEATURE_NAMES,
    snapshot_to_region_graph,
)
from .region_resource_v4_shadow_candidate import (
    REGION_RESOURCE_V4_CANDIDATE_ID,
    REGION_RESOURCE_V4_INTERVENTION_GATE,
    _V4_PROJECTION,
    _V4_RULE_CONFIG,
    _model_parameters_finite,
    _v4_actor_records,
    evaluate_v4_intervention_invariants,
    executable_signature,
)
from .region_resource_v6_transfer_candidate import (
    _validate_frozen_v4_source,
)


try:  # The default deterministic D4 runtime remains torch-free.
    import torch
except ImportError:  # pragma: no cover - dependency gate.
    torch = None


REGION_RESOURCE_V7_CANDIDATE_ID = (
    "region_resource_a2_rule_node_transfer_residual_shadow_v7"
)
REGION_RESOURCE_V7_MODEL_VERSION = (
    "d4-region-resource-rule-node-transfer-residual-v7"
)
REGION_RESOURCE_V7_CANDIDATE_SCHEMA = (
    "d4-region-resource-rule-node-transfer-residual-candidate-v7"
)
REGION_RESOURCE_V7_CONFIG_SCHEMA = (
    "d4-region-resource-rule-node-transfer-residual-config-v7"
)
REGION_RESOURCE_V7_BALANCE_SCHEMA = (
    "d4-region-resource-rule-node-transfer-residual-balance-v7"
)
REGION_RESOURCE_V7_AUDIT_SCHEMA = (
    "d4-region-resource-rule-node-transfer-residual-audit-v7"
)
REGION_RESOURCE_V7_SOURCE_SCHEMA = (
    "d4-region-resource-rule-node-transfer-residual-sources-v7"
)
REGION_RESOURCE_V7_PERMISSIONS_SCHEMA = (
    "d4-region-resource-rule-node-transfer-residual-permissions-v7"
)
REGION_RESOURCE_V7_BUNDLE_SCHEMA = (
    "d4-region-resource-rule-node-transfer-residual-bundle-v7"
)
REGION_RESOURCE_V7_CANDIDATE_FILENAME = (
    "v7_rule_node_transfer_residual_candidate_manifest.json"
)
REGION_RESOURCE_V7_CONFIG_FILENAME = "training_config.json"
REGION_RESOURCE_V7_AUDIT_FILENAME = "training_audit.json"
REGION_RESOURCE_V7_SOURCE_FILENAME = "source_binding.json"
REGION_RESOURCE_V7_STATE_MAGIC = b"D4V7RESIDUAL1\x00"

REGION_RESOURCE_V7_SOURCE_A_ID = "frozen_v4_train_validation"
REGION_RESOURCE_V7_SOURCE_B_ID = "m16n24_labeled_train_validation"
REGION_RESOURCE_V7_SOURCE_B_DATASET_SHA256 = (
    "b1295091d4d79e423e1ced02269895d486e2dbcca9d80834d5af0cc14882b42c"
)
REGION_RESOURCE_V7_SOURCE_B_SPLIT_SHA256 = (
    "c767a48b90f6e2a3f077be4f931d95102a6b2a925a2f813ca8440c8951aae332"
)
REGION_RESOURCE_V7_ACTIVATION_THRESHOLD = 0.0
REGION_RESOURCE_V7_MAX_ACTIVE_RESIDUAL_EDGES = 1
REGION_RESOURCE_V7_POSITIVE_EDGE_WEIGHT_CAP = 128.0
REGION_RESOURCE_V7_POSITIVE_FRAME_WEIGHT_CAP = 8.0
REGION_RESOURCE_V7_DIRECTION_MARGIN = 0.50
REGION_RESOURCE_V7_ZERO_TARGET_TOLERANCE = 1.0e-12
REGION_RESOURCE_V7_FORBIDDEN_FORMAL_HOLDOUT_SEEDS = frozenset(
    range(1000, 1020)
)
REGION_RESOURCE_V7_FORBIDDEN_PRIOR_EVALUATION_SEEDS = frozenset(
    range(3008, 3040)
)
REGION_RESOURCE_V7_FORBIDDEN_INDEPENDENT_EVALUATION_SEEDS = frozenset(
    range(5216, 5280)
)


class RegionResourceV7CandidateError(RuntimeError):
    """Stable fail-closed error for the v7 development candidate."""


@dataclass(frozen=True)
class V7TransferResidualOutput:
    """Directed residual activation logits and absolute transfer counts."""

    activation_logits: Any
    resource_counts: Any
    frame_activation_logit: Any


class V7TransferResidualGraphActor(torch.nn.Module if torch else object):
    """Directed-edge actor without any node-action output head."""

    def __init__(
        self,
        *,
        hidden_dim: int = 64,
        node_feature_dim: int = len(NODE_FEATURE_NAMES),
        edge_feature_dim: int = len(EDGE_FEATURE_NAMES),
    ) -> None:
        _require_torch()
        super().__init__()
        if int(hidden_dim) <= 0:
            raise ValueError("v7 hidden_dim must be positive")
        if int(node_feature_dim) != len(NODE_FEATURE_NAMES):
            raise ValueError("v7 node feature dimension changed")
        if int(edge_feature_dim) != len(EDGE_FEATURE_NAMES):
            raise ValueError("v7 edge feature dimension changed")
        self.hidden_dim = int(hidden_dim)
        self.node_feature_dim = int(node_feature_dim)
        self.edge_feature_dim = int(edge_feature_dim)
        input_dim = self.node_feature_dim * 4 + self.edge_feature_dim + 1
        self.edge_context = torch.nn.Sequential(
            torch.nn.Linear(input_dim, self.hidden_dim),
            torch.nn.Tanh(),
            torch.nn.Linear(self.hidden_dim, self.hidden_dim),
            torch.nn.Tanh(),
        )
        self.activation_head = torch.nn.Linear(self.hidden_dim, 1)
        self.count_head = torch.nn.Linear(self.hidden_dim, 1)
        frame_input_dim = (
            self.node_feature_dim * 3 + self.edge_feature_dim * 2 + 2
        )
        self.frame_activation_head = torch.nn.Sequential(
            torch.nn.Linear(frame_input_dim, self.hidden_dim),
            torch.nn.Tanh(),
            torch.nn.Linear(self.hidden_dim, 1),
        )

    def forward(
        self,
        graph: Any,
        baseline_transfer_fractions: Any,
    ) -> V7TransferResidualOutput:
        if baseline_transfer_fractions.shape != (graph.edge_count, 1):
            raise ValueError("v7 baseline transfer feature shape mismatch")
        if graph.edge_count == 0:
            empty = torch.empty(
                (0, 1),
                dtype=graph.node_features.dtype,
                device=graph.node_features.device,
            )
            zero_edges = torch.zeros(
                self.edge_feature_dim,
                dtype=graph.node_features.dtype,
                device=graph.node_features.device,
            )
            frame_features = torch.cat(
                (
                    graph.node_features.mean(dim=0),
                    graph.node_features.max(dim=0).values,
                    graph.node_features.min(dim=0).values,
                    zero_edges,
                    zero_edges,
                    torch.tensor(
                        [graph.node_count / 8.0, 0.0],
                        dtype=graph.node_features.dtype,
                        device=graph.node_features.device,
                    ),
                )
            )
            return V7TransferResidualOutput(
                activation_logits=empty,
                resource_counts=empty,
                frame_activation_logit=(
                    self.frame_activation_head(frame_features).reshape(())
                ),
            )
        source = graph.edge_index[0]
        target = graph.edge_index[1]
        nodes = graph.node_features
        global_context = nodes.mean(dim=0).expand(graph.edge_count, -1)
        features = torch.cat(
            (
                nodes[source],
                nodes[target],
                nodes[target] - nodes[source],
                global_context,
                graph.edge_features,
                baseline_transfer_fractions,
            ),
            dim=-1,
        )
        hidden = self.edge_context(features)
        transferable = torch.tensor(
            [
                max(0, int(edge.transferable_resources))
                for edge in graph.edge_refs
            ],
            dtype=hidden.dtype,
            device=hidden.device,
        ).reshape((-1, 1))
        frame_features = torch.cat(
            (
                nodes.mean(dim=0),
                nodes.max(dim=0).values,
                nodes.min(dim=0).values,
                graph.edge_features.mean(dim=0),
                graph.edge_features.max(dim=0).values,
                torch.tensor(
                    [
                        graph.node_count / 8.0,
                        graph.edge_count / 16.0,
                    ],
                    dtype=hidden.dtype,
                    device=hidden.device,
                ),
            )
        )
        return V7TransferResidualOutput(
            activation_logits=self.activation_head(hidden),
            resource_counts=torch.sigmoid(self.count_head(hidden))
            * transferable,
            frame_activation_logit=(
                self.frame_activation_head(frame_features).reshape(())
            ),
        )


@dataclass(frozen=True)
class V7ModelIdentity:
    model_version: str
    state_dict_sha256: str

    def __post_init__(self) -> None:
        if self.model_version != REGION_RESOURCE_V7_MODEL_VERSION:
            raise ValueError("v7 model version changed")
        _require_sha256(self.state_dict_sha256, "v7_model_identity")


@dataclass(frozen=True)
class V7ResidualDecision:
    """One actor decision before deterministic projection."""

    recommendation: RegionResourceRecommendation
    baseline: RegionResourceRecommendation
    activated_edge_keys: tuple[tuple[str, str, str], ...]
    predicted_resource_counts: tuple[int, ...]


class V7RuleNodeTransferResidualPolicy:
    """Compose R0 node actions with a learned transfer-only residual."""

    policy_name = "d4-region-resource-rule-node-transfer-residual"

    def __init__(
        self,
        model: V7TransferResidualGraphActor,
        identity: V7ModelIdentity,
        *,
        rule_policy: RuleRegionResourcePolicy | None = None,
        activation_threshold: float = REGION_RESOURCE_V7_ACTIVATION_THRESHOLD,
    ) -> None:
        if not isfinite(float(activation_threshold)):
            raise ValueError("v7 activation threshold must be finite")
        self.model = model
        self.identity = identity
        self.rule_policy = rule_policy or RuleRegionResourcePolicy(
            _V4_RULE_CONFIG,
            projector=DeterministicResourceProjector(_V4_PROJECTION),
        )
        self.activation_threshold = float(activation_threshold)

    def decide(self, snapshot: Any) -> V7ResidualDecision:
        baseline = self.rule_policy.recommend(snapshot)
        graph = snapshot_to_region_graph(
            snapshot,
            device=_model_device(self.model),
        )
        fractions = _baseline_transfer_fractions(graph, baseline)
        with torch.no_grad():
            output = self.model(graph, fractions)
        _validate_v7_output(output, edge_count=graph.edge_count)
        activated_indices = _decode_active_edges(
            output.activation_logits,
            frame_activation_logit=output.frame_activation_logit,
            threshold=self.activation_threshold,
        )
        baseline_by_key = _transfer_count_by_key(baseline)
        transfer_by_key = {
            key: transfer
            for key, transfer in _transfer_by_key(baseline).items()
        }
        counts: list[int] = []
        keys: list[tuple[str, str, str]] = []
        for index in activated_indices:
            edge = graph.edge_refs[index]
            key = (
                edge.edge_id,
                edge.source_region_id,
                edge.target_region_id,
            )
            count = max(
                0,
                min(
                    int(edge.transferable_resources),
                    int(round(float(output.resource_counts[index, 0]))),
                ),
            )
            keys.append(key)
            counts.append(count)
            if count <= 0:
                transfer_by_key.pop(key, None)
                continue
            transfer_by_key[key] = RegionTransferSuggestion(
                source_region_id=edge.source_region_id,
                target_region_id=edge.target_region_id,
                resource_count=count,
                edge_id=edge.edge_id,
                expected_transfer_time_s=edge.transfer_time_s,
                reasons=(
                    "v7_learned_transfer_residual_override"
                    if key in baseline_by_key
                    else "v7_learned_transfer_residual_add"
                ),
            )
        transfers = tuple(
            transfer_by_key[key] for key in sorted(transfer_by_key)
        )
        recommendation = RegionResourceRecommendation(
            snapshot_id=snapshot.snapshot_id,
            scenario_id=snapshot.scenario_id,
            scenario_version=snapshot.scenario_version,
            seed=snapshot.seed,
            authority_digest=snapshot.authority_digest,
            created_at_s=snapshot.timestamp_s,
            policy_name=self.policy_name,
            policy_version=self.identity.model_version,
            source=RecommendationSource.LEARNED,
            confidence=0.0,
            actions=baseline.actions,
            transfers=transfers,
            projected=False,
            model_sha256=self.identity.state_dict_sha256,
            planning_authority_digest=snapshot.planning_authority_digest,
        )
        return V7ResidualDecision(
            recommendation=recommendation,
            baseline=baseline,
            activated_edge_keys=tuple(keys),
            predicted_resource_counts=tuple(counts),
        )

    def recommend_raw(self, snapshot: Any) -> RegionResourceRecommendation:
        return self.decide(snapshot).recommendation


@dataclass(frozen=True)
class RegionResourceV7Permissions:
    """Capabilities that an unregistered v7 candidate cannot obtain."""

    source_independent_evaluation_authorized: bool = False
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
    schema: str = REGION_RESOURCE_V7_PERMISSIONS_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V7_PERMISSIONS_SCHEMA:
            raise ValueError("unsupported v7 permissions schema")
        values = (
            value
            for name, value in asdict(self).items()
            if name != "schema"
        )
        if any(type(value) is not bool or value for value in values):
            raise ValueError("v7 development candidate cannot grant permissions")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionResourceV7BuildConfig:
    """Finite deterministic training contract for the v7 residual actor."""

    random_seed: int = 20260730
    hidden_dim: int = 64
    epochs: int = 260
    batch_size: int = 16
    learning_rate: float = 3.0e-3
    weight_decay: float = 1.0e-5
    max_grad_norm: float = 1.0
    early_stopping_patience: int = 45
    edge_activation_weight: float = 1.0
    direction_ranking_weight: float = 0.75
    positive_count_weight: float = 0.50
    frame_activation_weight: float = 2.0
    negative_no_transfer_weight: float = 2.0
    direction_margin: float = REGION_RESOURCE_V7_DIRECTION_MARGIN
    activation_threshold: float = REGION_RESOURCE_V7_ACTIVATION_THRESHOLD
    torch_num_threads: int = 1
    created_at_utc: str = "2026-07-30T00:00:00Z"
    candidate_id: str = REGION_RESOURCE_V7_CANDIDATE_ID
    model_version: str = REGION_RESOURCE_V7_MODEL_VERSION
    schema: str = REGION_RESOURCE_V7_CONFIG_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema != REGION_RESOURCE_V7_CONFIG_SCHEMA
            or self.candidate_id != REGION_RESOURCE_V7_CANDIDATE_ID
            or self.model_version != REGION_RESOURCE_V7_MODEL_VERSION
        ):
            raise ValueError("v7 candidate identity changed")
        for name in (
            "random_seed",
            "hidden_dim",
            "epochs",
            "batch_size",
            "early_stopping_patience",
            "torch_num_threads",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"v7 config {name} must be positive")
        for name in (
            "learning_rate",
            "weight_decay",
            "max_grad_norm",
            "edge_activation_weight",
            "direction_ranking_weight",
            "positive_count_weight",
            "frame_activation_weight",
            "negative_no_transfer_weight",
            "direction_margin",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or value < 0.0:
                raise ValueError(
                    f"v7 config {name} must be finite and non-negative"
                )
        if (
            self.learning_rate <= 0.0
            or self.max_grad_norm <= 0.0
            or self.edge_activation_weight <= 0.0
            or self.direction_ranking_weight <= 0.0
            or self.positive_count_weight <= 0.0
            or self.frame_activation_weight <= 0.0
            or self.negative_no_transfer_weight <= 0.0
            or self.direction_margin != REGION_RESOURCE_V7_DIRECTION_MARGIN
            or self.activation_threshold
            != REGION_RESOURCE_V7_ACTIVATION_THRESHOLD
        ):
            raise ValueError("v7 residual supervision contract changed")
        if not self.created_at_utc:
            raise ValueError("v7 created_at_utc must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionResourceV7TrainBalance:
    """All v7 imbalance and source weights derived from merged TRAIN."""

    train_sample_count: int
    positive_frame_count: int
    negative_frame_count: int
    edge_count: int
    positive_residual_edge_count: int
    zero_residual_edge_count: int
    positive_frame_weight: float
    negative_frame_weight: float
    positive_edge_weight: float
    zero_edge_weight: float
    source_sample_counts: Mapping[str, int]
    source_sample_weights: Mapping[str, float]
    train_label_inventory_sha256: str
    source_split: str = RegionLearningSplit.TRAIN.value
    validation_label_fit_count: int = 0
    validation_weight_fit_count: int = 0
    test_payload_read_count: int = 0
    formal_holdout_payload_read_count: int = 0
    prior_evaluation_payload_read_count: int = 0
    independent_evaluation_payload_read_count: int = 0
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_V7_BALANCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V7_BALANCE_SCHEMA:
            raise ValueError("unsupported v7 balance schema")
        if (
            self.train_sample_count
            != self.positive_frame_count + self.negative_frame_count
            or self.edge_count
            != self.positive_residual_edge_count
            + self.zero_residual_edge_count
            or min(
                self.positive_frame_count,
                self.negative_frame_count,
                self.positive_residual_edge_count,
                self.zero_residual_edge_count,
            )
            <= 0
        ):
            raise ValueError("v7 TRAIN requires positive and negative diversity")
        if (
            self.source_split != RegionLearningSplit.TRAIN.value
            or self.validation_label_fit_count != 0
            or self.validation_weight_fit_count != 0
            or self.test_payload_read_count != 0
            or self.formal_holdout_payload_read_count != 0
            or self.prior_evaluation_payload_read_count != 0
            or self.independent_evaluation_payload_read_count != 0
        ):
            raise ValueError("v7 weights must be derived from TRAIN only")
        source_counts = {
            str(key): int(value)
            for key, value in self.source_sample_counts.items()
        }
        source_weights = {
            str(key): float(value)
            for key, value in self.source_sample_weights.items()
        }
        expected_sources = {
            REGION_RESOURCE_V7_SOURCE_A_ID,
            REGION_RESOURCE_V7_SOURCE_B_ID,
        }
        if (
            set(source_counts) != expected_sources
            or set(source_weights) != expected_sources
            or any(value <= 0 for value in source_counts.values())
            or sum(source_counts.values()) != self.train_sample_count
        ):
            raise ValueError("v7 source balance inventory is incomplete")
        for value in (
            self.positive_frame_weight,
            self.negative_frame_weight,
            self.positive_edge_weight,
            self.zero_edge_weight,
            *source_weights.values(),
        ):
            if not isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError("v7 balance weights must be finite and positive")
        if (
            self.negative_frame_weight != 1.0
            or self.zero_edge_weight != 1.0
        ):
            raise ValueError("v7 negative baseline weights changed")
        object.__setattr__(self, "source_sample_counts", source_counts)
        object.__setattr__(self, "source_sample_weights", source_weights)
        _require_sha256(
            self.train_label_inventory_sha256,
            "v7_balance.train_label_inventory_sha256",
        )
        expected = _canonical_sha256(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected:
            raise ValueError("v7 balance content SHA256 mismatch")
        object.__setattr__(self, "content_sha256", expected)

    def content_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("content_sha256", None)
        return payload

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}


@dataclass(frozen=True)
class _V7ResidualRecord:
    source_id: str
    source_record: Any
    baseline: RegionResourceRecommendation
    activation_targets: Any
    count_targets: Any
    baseline_transfer_fractions: Any
    residual_edge_count: int

    @property
    def split(self) -> RegionLearningSplit:
        return self.source_record.split

    @property
    def target_positive(self) -> bool:
        return bool(self.source_record.target_positive)

    @property
    def sample(self) -> Any:
        return self.source_record.sample

    @property
    def snapshot(self) -> Any:
        return self.source_record.snapshot

    @property
    def target(self) -> RegionResourceRecommendation:
        return self.source_record.target


def derive_v7_train_balance(
    records: Sequence[_V7ResidualRecord],
) -> RegionResourceV7TrainBalance:
    """Derive frame, edge, and source weights from merged TRAIN only."""

    if not records or any(
        record.split != RegionLearningSplit.TRAIN for record in records
    ):
        raise RegionResourceV7CandidateError(
            "v7_balance_fit_requires_merged_train_only"
        )
    positive_frames = sum(record.target_positive for record in records)
    negative_frames = len(records) - positive_frames
    positive_edges = sum(record.residual_edge_count for record in records)
    edge_count = sum(record.sample.graph.edge_count for record in records)
    zero_edges = edge_count - positive_edges
    if min(positive_frames, negative_frames, positive_edges, zero_edges) <= 0:
        raise RegionResourceV7CandidateError(
            "v7_train_requires_positive_negative_and_edge_diversity"
        )
    source_counts = {
        source_id: sum(record.source_id == source_id for record in records)
        for source_id in (
            REGION_RESOURCE_V7_SOURCE_A_ID,
            REGION_RESOURCE_V7_SOURCE_B_ID,
        )
    }
    if any(value <= 0 for value in source_counts.values()):
        raise RegionResourceV7CandidateError(
            "v7_merged_train_requires_both_sources"
        )
    source_weights = {
        source_id: len(records) / (len(source_counts) * count)
        for source_id, count in source_counts.items()
    }
    inventory = [
        {
            "source_id": record.source_id,
            "episode_id": record.source_record.source_episode_id,
            "frame_index": int(record.source_record.frame_index),
            "positive": record.target_positive,
            "residual_edge_count": record.residual_edge_count,
            "target_signature": (
                record.source_record.target_executable_signature_sha256
            ),
            "rule_signature": (
                record.source_record.rule_executable_signature_sha256
            ),
        }
        for record in records
    ]
    return RegionResourceV7TrainBalance(
        train_sample_count=len(records),
        positive_frame_count=positive_frames,
        negative_frame_count=negative_frames,
        edge_count=edge_count,
        positive_residual_edge_count=positive_edges,
        zero_residual_edge_count=zero_edges,
        positive_frame_weight=min(
            negative_frames / positive_frames,
            REGION_RESOURCE_V7_POSITIVE_FRAME_WEIGHT_CAP,
        ),
        negative_frame_weight=1.0,
        positive_edge_weight=min(
            zero_edges / positive_edges,
            REGION_RESOURCE_V7_POSITIVE_EDGE_WEIGHT_CAP,
        ),
        zero_edge_weight=1.0,
        source_sample_counts=source_counts,
        source_sample_weights=source_weights,
        train_label_inventory_sha256=_canonical_sha256(inventory),
    )


def _build_v7_residual_records(
    loaded: LoadedRegionLearningDataset,
    *,
    source_id: str,
    split: RegionLearningSplit,
    projector: DeterministicResourceProjector,
    rule_policy: RuleRegionResourcePolicy,
) -> tuple[_V7ResidualRecord, ...]:
    if split not in {
        RegionLearningSplit.TRAIN,
        RegionLearningSplit.VALIDATION,
    }:
        raise RegionResourceV7CandidateError(
            "v7_test_or_holdout_payload_read_forbidden"
        )
    records = _v4_actor_records(
        loaded,
        split=split,
        projector=projector,
        rule_policy=rule_policy,
    )
    residual_records: list[_V7ResidualRecord] = []
    for record in records:
        graph = record.sample.graph
        baseline = rule_policy.recommend(record.snapshot)
        baseline_counts = _transfer_count_by_key(baseline)
        target_counts = _transfer_count_by_key(record.target)
        activation_rows: list[list[float]] = []
        count_rows: list[list[float]] = []
        baseline_rows: list[list[float]] = []
        for edge in graph.edge_refs:
            key = (
                edge.edge_id,
                edge.source_region_id,
                edge.target_region_id,
            )
            baseline_count = int(baseline_counts.get(key, 0))
            target_count = int(target_counts.get(key, 0))
            activation_rows.append(
                [float(baseline_count != target_count)]
            )
            count_rows.append([float(target_count)])
            baseline_rows.append(
                [
                    baseline_count
                    / max(1, int(edge.transferable_resources))
                ]
            )
        activation_targets = torch.tensor(
            activation_rows,
            dtype=torch.float32,
        ).reshape((-1, 1))
        count_targets = torch.tensor(
            count_rows,
            dtype=torch.float32,
        ).reshape((-1, 1))
        baseline_fractions = torch.tensor(
            baseline_rows,
            dtype=torch.float32,
        ).reshape((-1, 1))
        residual_edge_count = int(
            torch.count_nonzero(
                activation_targets
                > REGION_RESOURCE_V7_ZERO_TARGET_TOLERANCE
            ).item()
        )
        if residual_edge_count > REGION_RESOURCE_V7_MAX_ACTIVE_RESIDUAL_EDGES:
            raise RegionResourceV7CandidateError(
                "v7_source_exceeds_single_residual_edge_contract"
            )
        if bool(record.target_positive) != bool(residual_edge_count):
            raise RegionResourceV7CandidateError(
                "v7_residual_label_and_executable_label_disagree"
            )
        residual_records.append(
            _V7ResidualRecord(
                source_id=source_id,
                source_record=record,
                baseline=baseline,
                activation_targets=activation_targets,
                count_targets=count_targets,
                baseline_transfer_fractions=baseline_fractions,
                residual_edge_count=residual_edge_count,
            )
        )
    return tuple(residual_records)


def _v7_loss_components(
    model: V7TransferResidualGraphActor,
    record: _V7ResidualRecord,
    *,
    balance: RegionResourceV7TrainBalance,
    config: RegionResourceV7BuildConfig,
) -> tuple[Any, dict[str, Any]]:
    output = model(
        record.sample.graph,
        record.baseline_transfer_fractions,
    )
    targets = record.activation_targets
    positive_mask = targets[:, 0] > 0.5
    positive_weight = torch.tensor(
        [balance.positive_edge_weight],
        dtype=output.activation_logits.dtype,
        device=output.activation_logits.device,
    )
    activation = torch.nn.functional.binary_cross_entropy_with_logits(
        output.activation_logits,
        targets,
        pos_weight=positive_weight,
    )
    if bool(positive_mask.any().item()):
        positive_logits = output.activation_logits[positive_mask]
        negative_logits = output.activation_logits[~positive_mask]
        direction_ranking = torch.relu(
            config.direction_margin
            - (
                positive_logits.reshape((-1, 1))
                - negative_logits.reshape((1, -1))
            )
        ).mean()
        positive_count = torch.nn.functional.smooth_l1_loss(
            output.resource_counts[positive_mask],
            record.count_targets[positive_mask],
        )
        frame_activation = (
            torch.nn.functional.binary_cross_entropy_with_logits(
                output.frame_activation_logit.reshape((1,)),
                torch.ones(
                    (1,),
                    dtype=output.frame_activation_logit.dtype,
                    device=output.frame_activation_logit.device,
                ),
                pos_weight=torch.tensor(
                    [balance.positive_frame_weight],
                    dtype=output.frame_activation_logit.dtype,
                    device=output.frame_activation_logit.device,
                ),
            )
        )
        negative_no_transfer = output.activation_logits.sum() * 0.0
    else:
        direction_ranking = output.activation_logits.sum() * 0.0
        positive_count = output.resource_counts.sum() * 0.0
        frame_activation = output.activation_logits.sum() * 0.0
        negative_no_transfer = (
            torch.nn.functional.binary_cross_entropy_with_logits(
                output.frame_activation_logit.reshape((1,)),
                torch.zeros(
                    (1,),
                    dtype=output.frame_activation_logit.dtype,
                    device=output.frame_activation_logit.device,
                ),
            )
        )
    total = (
        config.edge_activation_weight * activation
        + config.direction_ranking_weight * direction_ranking
        + config.positive_count_weight * positive_count
        + config.frame_activation_weight * frame_activation
        + config.negative_no_transfer_weight * negative_no_transfer
    )
    source_weight = balance.source_sample_weights[record.source_id]
    weighted = source_weight * total
    return weighted, {
        "activation": activation,
        "direction_ranking": direction_ranking,
        "positive_count": positive_count,
        "frame_activation": frame_activation,
        "negative_no_transfer": negative_no_transfer,
    }


def _mean_v7_loss(
    model: V7TransferResidualGraphActor,
    records: Sequence[_V7ResidualRecord],
    *,
    balance: RegionResourceV7TrainBalance,
    config: RegionResourceV7BuildConfig,
) -> float:
    if not records:
        raise RegionResourceV7CandidateError(
            "v7_loss_records_must_not_be_empty"
        )
    model.eval()
    with torch.no_grad():
        losses = [
            _v7_loss_components(
                model,
                record,
                balance=balance,
                config=config,
            )[0]
            for record in records
        ]
        loss = torch.stack(losses).mean()
    value = float(loss.cpu())
    if not isfinite(value):
        raise RegionResourceV7CandidateError(
            "v7_validation_loss_nonfinite"
        )
    return value


def _v7_actor_step(
    model: V7TransferResidualGraphActor,
    optimizer: Any,
    records: Sequence[_V7ResidualRecord],
    *,
    balance: RegionResourceV7TrainBalance,
    config: RegionResourceV7BuildConfig,
) -> float:
    optimizer.zero_grad()
    losses = [
        _v7_loss_components(
            model,
            record,
            balance=balance,
            config=config,
        )[0]
        for record in records
    ]
    loss = torch.stack(losses).mean()
    if not bool(torch.isfinite(loss).item()):
        raise RegionResourceV7CandidateError("v7_actor_loss_nonfinite")
    loss.backward()
    torch.nn.utils.clip_grad_norm_(
        model.parameters(),
        config.max_grad_norm,
    )
    optimizer.step()
    if not _model_parameters_finite(model):
        raise RegionResourceV7CandidateError(
            "v7_actor_update_nonfinite"
        )
    return float(loss.detach().cpu())


def evaluate_v7_actor(
    model: V7TransferResidualGraphActor,
    records: Sequence[_V7ResidualRecord],
    *,
    projector: DeterministicResourceProjector,
    rule_policy: RuleRegionResourcePolicy,
    activation_threshold: float = REGION_RESOURCE_V7_ACTIVATION_THRESHOLD,
) -> dict[str, Any]:
    """Evaluate raw residuals, projected behavior, and intervention safety."""

    identity = V7ModelIdentity(
        REGION_RESOURCE_V7_MODEL_VERSION,
        "0" * 64,
    )
    policy = V7RuleNodeTransferResidualPolicy(
        model,
        identity,
        rule_policy=rule_policy,
        activation_threshold=activation_threshold,
    )
    positive_count = sum(record.target_positive for record in records)
    negative_count = len(records) - positive_count
    positive_exact = 0
    negative_exact = 0
    directed_residual_exact = 0
    actor_raw_activation_count = 0
    actor_raw_transfer_change_count = 0
    projection_rejection_count = 0
    invariant_failure_count = 0
    negative_false_transfer_count = 0
    node_action_preservation_failure_count = 0
    wrong_direction_count = 0
    wrong_count_count = 0
    failure_reasons: dict[str, int] = {}
    for record in records:
        decision = policy.decide(record.snapshot)
        raw = decision.recommendation
        baseline = decision.baseline
        actor_raw_activation_count += len(decision.activated_edge_keys)
        if not _node_nontransfer_fields_equal(raw, baseline):
            node_action_preservation_failure_count += 1
        baseline_counts = _transfer_count_by_key(baseline)
        target_counts = _transfer_count_by_key(record.target)
        raw_counts = _transfer_count_by_key(raw)
        target_residual = _residual_signature(
            baseline_counts,
            target_counts,
        )
        raw_residual = _residual_signature(
            baseline_counts,
            raw_counts,
        )
        actor_raw_transfer_change_count += int(bool(raw_residual))
        residual_edges_exact = {
            item[:3] for item in raw_residual
        } == {item[:3] for item in target_residual}
        directed_residual_exact += int(
            record.target_positive and residual_edges_exact
        )
        if record.target_positive and raw_residual != target_residual:
            expected_keys = {item[:3] for item in target_residual}
            raw_keys = {item[:3] for item in raw_residual}
            reversed_direction = any(
                (edge_id, target_id, source_id) in raw_keys
                for edge_id, source_id, target_id in expected_keys
            )
            wrong_direction_count += int(reversed_direction)
            wrong_count_count += int(
                bool(expected_keys & raw_keys)
                and any(
                    item not in raw_residual for item in target_residual
                )
            )
        projected = projector.project(record.snapshot, raw)
        projection_rejected = bool(projected.projection_rejections)
        projection_rejection_count += int(projection_rejected)
        baseline_advisory = projector.build_advisory_contract(
            record.snapshot,
            baseline,
        )
        candidate_advisory = projector.build_advisory_contract(
            record.snapshot,
            projected,
        )
        target_advisory = projector.build_advisory_contract(
            record.snapshot,
            record.target,
        )
        baseline_signature, _ = executable_signature(baseline_advisory)
        candidate_signature, _ = executable_signature(candidate_advisory)
        target_signature, _ = executable_signature(target_advisory)
        executable = candidate_signature != baseline_signature
        valid = True
        invariant_reasons: tuple[str, ...] = ()
        if executable:
            valid, invariant_reasons = evaluate_v4_intervention_invariants(
                record.snapshot,
                projected,
                baseline,
                gate=REGION_RESOURCE_V4_INTERVENTION_GATE,
                projector=projector,
                formal_decision=None,
            )
            invariant_failure_count += int(not valid)
        positive_hit = bool(
            record.target_positive
            and executable
            and candidate_signature == target_signature
            and valid
            and not projection_rejected
        )
        negative_hit = bool(
            not record.target_positive
            and not executable
            and candidate_signature == target_signature
            and not projection_rejected
        )
        positive_exact += int(positive_hit)
        negative_exact += int(negative_hit)
        negative_false_transfer_count += int(
            not record.target_positive and bool(raw_residual)
        )
        reasons: list[str] = []
        if record.target_positive and not decision.activated_edge_keys:
            reasons.append("positive_actor_activation_missing")
        if record.target_positive and not residual_edges_exact:
            reasons.append("directed_residual_edge_mismatch")
        if record.target_positive and raw_residual != target_residual:
            reasons.append("residual_resource_count_mismatch")
        if not record.target_positive and raw_residual:
            reasons.append("negative_false_transfer_residual")
        if projection_rejected:
            reasons.append("projection_rejected")
            reasons.extend(projected.projection_rejections)
        if executable and not valid:
            reasons.append("intervention_invariant_failure")
            reasons.extend(invariant_reasons)
        if not _node_nontransfer_fields_equal(raw, baseline):
            reasons.append("r0_node_action_not_preserved")
        if record.target_positive and not positive_hit:
            reasons.append("positive_exact_projected_action_miss")
        if not record.target_positive and not negative_hit:
            reasons.append("negative_exact_r0_miss")
        for reason in dict.fromkeys(reasons):
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    nondegenerate = bool(
        positive_count > 0
        and negative_count > 0
        and positive_exact > 0
        and directed_residual_exact > 0
        and negative_exact > 0
        and actor_raw_activation_count > 0
        and actor_raw_transfer_change_count > 0
        and invariant_failure_count == 0
        and node_action_preservation_failure_count == 0
    )
    checkpoint_failures = []
    if positive_exact <= 0:
        checkpoint_failures.append("positive_exact_action_hit_missing")
    if directed_residual_exact <= 0:
        checkpoint_failures.append("correct_directed_residual_hit_missing")
    if negative_exact <= 0:
        checkpoint_failures.append("negative_exact_r0_hit_missing")
    if actor_raw_activation_count <= 0:
        checkpoint_failures.append("all_no_transfer_checkpoint")
    if actor_raw_transfer_change_count <= 0:
        checkpoint_failures.append("node_only_or_no_residual_checkpoint")
    if invariant_failure_count:
        checkpoint_failures.append("intervention_invariant_failure")
    if node_action_preservation_failure_count:
        checkpoint_failures.append("r0_node_action_not_preserved")
    return {
        "sample_count": len(records),
        "target_positive_count": positive_count,
        "target_negative_count": negative_count,
        "positive_exact_projected_action_hit_count": positive_exact,
        "negative_exact_r0_action_hit_count": negative_exact,
        "correct_directed_residual_edge_hit_count": (
            directed_residual_exact
        ),
        "positive_exact_projected_action_hit_rate": (
            positive_exact / positive_count if positive_count else 0.0
        ),
        "negative_exact_r0_action_hit_rate": (
            negative_exact / negative_count if negative_count else 0.0
        ),
        "correct_directed_residual_edge_hit_rate": (
            directed_residual_exact / positive_count
            if positive_count
            else 0.0
        ),
        "actor_raw_residual_activation_count": actor_raw_activation_count,
        "actor_raw_transfer_change_count": actor_raw_transfer_change_count,
        "negative_false_transfer_count": negative_false_transfer_count,
        "projection_rejection_count": projection_rejection_count,
        "invariant_failure_count": invariant_failure_count,
        "r0_node_action_preservation_failure_count": (
            node_action_preservation_failure_count
        ),
        "wrong_direction_count": wrong_direction_count,
        "wrong_resource_count": wrong_count_count,
        "nondegenerate_checkpoint": nondegenerate,
        "checkpoint_failure_reasons": checkpoint_failures,
        "failure_reason_inventory": dict(sorted(failure_reasons.items())),
    }


def _v7_checkpoint_selection_key(
    metrics: Mapping[str, Any],
    *,
    validation_loss: float,
    epoch: int,
) -> tuple[int, int, int, int, int, int, int, int, int, float, int]:
    """Rank projected behavior before fixed-TRAIN-weight validation loss."""

    if not isfinite(float(validation_loss)):
        raise RegionResourceV7CandidateError(
            "v7_checkpoint_loss_nonfinite"
        )
    if type(epoch) is not int or epoch <= 0:
        raise RegionResourceV7CandidateError(
            "v7_checkpoint_epoch_invalid"
        )
    return (
        int(bool(metrics.get("development_gate_passed", False))),
        int(metrics["positive_exact_projected_action_hit_count"]),
        int(metrics["correct_directed_residual_edge_hit_count"]),
        int(metrics["negative_exact_r0_action_hit_count"]),
        int(metrics["invariant_failure_count"] == 0),
        int(metrics["negative_false_transfer_count"] == 0),
        int(metrics["projection_rejection_count"] == 0),
        -int(metrics["invariant_failure_count"]),
        -int(metrics["negative_false_transfer_count"]),
        -float(validation_loss),
        -epoch,
    )


def _v7_m16n24_development_gate_passed(
    metrics: Mapping[str, Any],
) -> bool:
    """Return the immutable M16N24 VALIDATION development gate."""

    return bool(
        int(metrics["target_negative_count"]) == 11
        and int(metrics["positive_exact_projected_action_hit_count"]) > 0
        and int(metrics["negative_exact_r0_action_hit_count"]) >= 8
        and int(metrics["actor_raw_residual_activation_count"]) > 0
        and int(metrics["actor_raw_transfer_change_count"]) > 0
        and int(metrics["projection_rejection_count"]) == 0
        and int(metrics["invariant_failure_count"]) == 0
        and int(
            metrics["r0_node_action_preservation_failure_count"]
        )
        == 0
    )


def train_v7_actor(
    source_a: LoadedRegionLearningDataset,
    source_b: LoadedRegionLearningDataset,
    *,
    config: RegionResourceV7BuildConfig | None = None,
) -> tuple[V7TransferResidualGraphActor, dict[str, Any]]:
    """Fit merged TRAIN and select a checkpoint with merged VALIDATION."""

    _require_torch()
    resolved = config or RegionResourceV7BuildConfig()
    prior_deterministic = torch.are_deterministic_algorithms_enabled()
    prior_threads = torch.get_num_threads()
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(resolved.torch_num_threads)
    random.seed(resolved.random_seed)
    torch.manual_seed(resolved.random_seed)
    projector = DeterministicResourceProjector(_V4_PROJECTION)
    rule_policy = RuleRegionResourcePolicy(
        _V4_RULE_CONFIG,
        projector=projector,
    )
    records_by_source_split: dict[
        tuple[str, RegionLearningSplit],
        tuple[_V7ResidualRecord, ...],
    ] = {}
    for source_id, loaded in (
        (REGION_RESOURCE_V7_SOURCE_A_ID, source_a),
        (REGION_RESOURCE_V7_SOURCE_B_ID, source_b),
    ):
        for split in (
            RegionLearningSplit.TRAIN,
            RegionLearningSplit.VALIDATION,
        ):
            records_by_source_split[(source_id, split)] = (
                _build_v7_residual_records(
                    loaded,
                    source_id=source_id,
                    split=split,
                    projector=projector,
                    rule_policy=rule_policy,
                )
            )
    train_records = tuple(
        record
        for source_id in (
            REGION_RESOURCE_V7_SOURCE_A_ID,
            REGION_RESOURCE_V7_SOURCE_B_ID,
        )
        for record in records_by_source_split[
            (source_id, RegionLearningSplit.TRAIN)
        ]
    )
    validation_records = tuple(
        record
        for source_id in (
            REGION_RESOURCE_V7_SOURCE_A_ID,
            REGION_RESOURCE_V7_SOURCE_B_ID,
        )
        for record in records_by_source_split[
            (source_id, RegionLearningSplit.VALIDATION)
        ]
    )
    if not train_records or not validation_records:
        raise RegionResourceV7CandidateError(
            "v7_train_or_validation_samples_unavailable"
        )
    balance = derive_v7_train_balance(train_records)
    model = V7TransferResidualGraphActor(hidden_dim=resolved.hidden_dim)
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=resolved.learning_rate,
        weight_decay=resolved.weight_decay,
    )
    generator = torch.Generator(device="cpu")
    generator.manual_seed(resolved.random_seed)
    best_key: (
        tuple[
            int,
            int,
            int,
            int,
            int,
            int,
            int,
            int,
            int,
            float,
            int,
        ]
        | None
    ) = None
    best_epoch = 0
    best_loss = float("inf")
    best_state: dict[str, Any] | None = None
    no_improvement = 0
    qualified_seen = False
    history: list[dict[str, Any]] = []
    try:
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
                    for index in order[
                        offset : offset + resolved.batch_size
                    ]
                )
                batch_losses.append(
                    _v7_actor_step(
                        model,
                        optimizer,
                        batch,
                        balance=balance,
                        config=resolved,
                    )
                )
            validation_loss = _mean_v7_loss(
                model,
                validation_records,
                balance=balance,
                config=resolved,
            )
            combined_metrics = evaluate_v7_actor(
                model,
                validation_records,
                projector=projector,
                rule_policy=rule_policy,
                activation_threshold=resolved.activation_threshold,
            )
            source_b_metrics = evaluate_v7_actor(
                model,
                records_by_source_split[
                    (
                        REGION_RESOURCE_V7_SOURCE_B_ID,
                        RegionLearningSplit.VALIDATION,
                    )
                ],
                projector=projector,
                rule_policy=rule_policy,
                activation_threshold=resolved.activation_threshold,
            )
            selection_metrics = dict(combined_metrics)
            selection_metrics["development_gate_passed"] = (
                _v7_m16n24_development_gate_passed(source_b_metrics)
            )
            key = _v7_checkpoint_selection_key(
                selection_metrics,
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
                        combined_metrics[
                            "positive_exact_projected_action_hit_count"
                        ]
                    ),
                    "validation_directed_residual_hits": (
                        combined_metrics[
                            "correct_directed_residual_edge_hit_count"
                        ]
                    ),
                    "validation_negative_exact_r0_hits": (
                        combined_metrics[
                            "negative_exact_r0_action_hit_count"
                        ]
                    ),
                    "validation_invariant_failures": (
                        combined_metrics["invariant_failure_count"]
                    ),
                    "validation_false_transfers": (
                        combined_metrics["negative_false_transfer_count"]
                    ),
                    "m16n24_validation_positive_exact_hits": (
                        source_b_metrics[
                            "positive_exact_projected_action_hit_count"
                        ]
                    ),
                    "m16n24_validation_negative_exact_r0_hits": (
                        source_b_metrics[
                            "negative_exact_r0_action_hit_count"
                        ]
                    ),
                    "m16n24_validation_invariant_failures": (
                        source_b_metrics["invariant_failure_count"]
                    ),
                    "m16n24_validation_r0_node_preservation_failures": (
                        source_b_metrics[
                            "r0_node_action_preservation_failure_count"
                        ]
                    ),
                    "development_gate_passed": selection_metrics[
                        "development_gate_passed"
                    ],
                }
            )
            if best_key is None or key > best_key:
                best_key = key
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
                qualified_seen
                or _v7_m16n24_development_gate_passed(
                    source_b_metrics
                )
            )
            if (
                qualified_seen
                and no_improvement >= resolved.early_stopping_patience
            ):
                break
    finally:
        torch.set_num_threads(prior_threads)
        torch.use_deterministic_algorithms(prior_deterministic)
    if best_state is None:
        raise RegionResourceV7CandidateError(
            "v7_training_produced_no_checkpoint"
        )
    model.load_state_dict(best_state, strict=True)
    model.eval()
    if not _model_parameters_finite(model):
        raise RegionResourceV7CandidateError(
            "v7_training_produced_nonfinite_model"
        )
    per_source_metrics: dict[str, dict[str, Any]] = {}
    for source_id in (
        REGION_RESOURCE_V7_SOURCE_A_ID,
        REGION_RESOURCE_V7_SOURCE_B_ID,
    ):
        per_source_metrics[source_id] = {}
        for split in (
            RegionLearningSplit.TRAIN,
            RegionLearningSplit.VALIDATION,
        ):
            per_source_metrics[source_id][split.value] = evaluate_v7_actor(
                model,
                records_by_source_split[(source_id, split)],
                projector=projector,
                rule_policy=rule_policy,
                activation_threshold=resolved.activation_threshold,
            )
    m16_validation = per_source_metrics[
        REGION_RESOURCE_V7_SOURCE_B_ID
    ][RegionLearningSplit.VALIDATION.value]
    development_failures = []
    if m16_validation["target_negative_count"] != 11:
        development_failures.append(
            "m16n24_validation_negative_denominator_changed"
        )
    if (
        m16_validation[
            "positive_exact_projected_action_hit_count"
        ]
        <= 0
    ):
        development_failures.append(
            "m16n24_validation_exact_positive_missing"
        )
    if m16_validation["actor_raw_residual_activation_count"] <= 0:
        development_failures.append(
            "m16n24_validation_raw_transfer_missing"
        )
    if m16_validation["actor_raw_transfer_change_count"] <= 0:
        development_failures.append(
            "m16n24_validation_raw_transfer_change_missing"
        )
    if m16_validation["projection_rejection_count"] != 0:
        development_failures.append(
            "m16n24_validation_projection_rejection"
        )
    if m16_validation["invariant_failure_count"] != 0:
        development_failures.append(
            "m16n24_validation_invariant_failure"
        )
    if m16_validation["negative_exact_r0_action_hit_count"] < 8:
        development_failures.append(
            "m16n24_validation_negative_exact_r0_below_8_of_11"
        )
    if (
        m16_validation[
            "r0_node_action_preservation_failure_count"
        ]
        != 0
    ):
        development_failures.append(
            "m16n24_validation_r0_node_action_not_preserved"
        )
    if development_failures:
        raise RegionResourceV7CandidateError(
            "v7_development_gate_failed:"
            + ",".join(development_failures)
        )
    state_sha256 = _model_state_content_sha256(model)
    return model, {
        "schema": REGION_RESOURCE_V7_AUDIT_SCHEMA,
        "candidate_id": resolved.candidate_id,
        "model_version": resolved.model_version,
        "architecture": (
            "deterministic-r0-node-actions-plus-learned-directed-"
            "transfer-residual"
        ),
        "fit_split": RegionLearningSplit.TRAIN.value,
        "checkpoint_selection_split": (
            RegionLearningSplit.VALIDATION.value
        ),
        "train_sample_count": len(train_records),
        "validation_sample_count": len(validation_records),
        "train_fit_count": len(train_records),
        "validation_fit_count": 0,
        "validation_weight_fit_count": 0,
        "test_payload_read_count": 0,
        "test_payload_fit_count": 0,
        "formal_holdout_payload_read_count": 0,
        "prior_evaluation_payload_read_count": 0,
        "independent_evaluation_payload_read_count": 0,
        "best_epoch": best_epoch,
        "epochs_completed": len(history),
        "best_validation_loss": best_loss,
        "checkpoint_selection_rule": (
            "rank projected exact positive actions, correct directed "
            "residual edges, exact negative R0 actions, zero invariant "
            "failure, zero false transfer, zero projection rejection, "
            "then fixed-TRAIN-weight validation loss and epoch"
        ),
        "class_and_source_balance": balance.to_dict(),
        "per_source_split_actor_audit": per_source_metrics,
        "development_gate": {
            "required_source": REGION_RESOURCE_V7_SOURCE_B_ID,
            "minimum_validation_exact_positive_hits": 1,
            "minimum_validation_negative_exact_r0_hits": 8,
            "validation_negative_sample_count": 11,
            "require_raw_transfer": True,
            "require_raw_transfer_change": True,
            "require_zero_projection_rejection": True,
            "require_zero_invariant_failure": True,
            "require_zero_r0_node_action_preservation_failure": True,
            "passed": True,
            "failure_reasons": [],
        },
        "history": history,
        "model_state_content_sha256": state_sha256,
        "model_parameter_count": sum(
            int(parameter.numel()) for parameter in model.parameters()
        ),
        "model_parameters_finite": True,
        "node_actor_present": False,
        "r0_node_actions_preserved": True,
        "explicit_residual_activation_supervision": True,
        "directed_edge_ranking_supervision": True,
        "positive_resource_count_supervision": True,
        "negative_no_transfer_consistency": True,
        "confidence_calibration_available": False,
        "fixed_confidence_gate_applied": False,
        "permissions": RegionResourceV7Permissions().to_dict(),
    }


def audit_v7_sources(
    source_a: LoadedRegionLearningDataset,
    source_b: LoadedRegionLearningDataset,
) -> dict[str, Any]:
    """Report per-source/split labels, directions, and selected hashes."""

    projector = DeterministicResourceProjector(_V4_PROJECTION)
    rule_policy = RuleRegionResourcePolicy(
        _V4_RULE_CONFIG,
        projector=projector,
    )
    payload: dict[str, Any] = {}
    for source_id, loaded in (
        (REGION_RESOURCE_V7_SOURCE_A_ID, source_a),
        (REGION_RESOURCE_V7_SOURCE_B_ID, source_b),
    ):
        source_payload: dict[str, Any] = {}
        for split in (
            RegionLearningSplit.TRAIN,
            RegionLearningSplit.VALIDATION,
        ):
            records = _build_v7_residual_records(
                loaded,
                source_id=source_id,
                split=split,
                projector=projector,
                rule_policy=rule_policy,
            )
            directions: dict[str, int] = {}
            positive_edges = 0
            for record in records:
                baseline = _transfer_count_by_key(record.baseline)
                target = _transfer_count_by_key(record.target)
                residual = _residual_signature(baseline, target)
                positive_edges += len(residual)
                for _, source_region, target_region, _, _ in residual:
                    key = f"{source_region}->{target_region}"
                    directions[key] = directions.get(key, 0) + 1
            episode_entries = [
                episode.manifest
                for episode in loaded.episode_records
                if episode.split == split
            ]
            source_payload[split.value] = {
                "sample_count": len(records),
                "positive_frame_count": sum(
                    record.target_positive for record in records
                ),
                "negative_frame_count": sum(
                    not record.target_positive for record in records
                ),
                "positive_residual_edge_count": positive_edges,
                "zero_residual_edge_count": (
                    sum(record.sample.graph.edge_count for record in records)
                    - positive_edges
                ),
                "directed_transfer_inventory": dict(
                    sorted(directions.items())
                ),
                "unique_directed_transfer_count": len(directions),
                "seed_count": len(
                    {
                        int(episode.source.seed)
                        for episode in loaded.episode_records
                        if episode.split == split
                    }
                ),
                "selected_episode_payload_sha256": _canonical_sha256(
                    [
                        {
                            "relative_path": entry.relative_path,
                            "episode_sha256": entry.episode_sha256,
                        }
                        for entry in episode_entries
                    ]
                ),
            }
        payload[source_id] = source_payload
    return {
        "schema": REGION_RESOURCE_V7_SOURCE_SCHEMA,
        "sources": payload,
        "payload_splits_read": [
            RegionLearningSplit.TRAIN.value,
            RegionLearningSplit.VALIDATION.value,
        ],
        "test_payload_read_count": 0,
        "test_payload_fit_count": 0,
        "formal_holdout_payload_read_count": 0,
        "prior_evaluation_payload_read_count": 0,
        "independent_evaluation_payload_read_count": 0,
        "truth_identifier_use_count": 0,
    }


def build_region_resource_v7_rule_node_residual_candidate(
    frozen_v4_candidate_root: str | Path,
    m16n24_dataset_root: str | Path,
    output_root: str | Path,
    *,
    config: RegionResourceV7BuildConfig | None = None,
) -> dict[str, Any]:
    """Build one deterministic, unregistered v7 development candidate."""

    _require_torch()
    resolved = config or RegionResourceV7BuildConfig()
    source_a_root = Path(frozen_v4_candidate_root).resolve()
    source_b_root = Path(m16n24_dataset_root).resolve()
    destination = Path(output_root).resolve()
    if source_a_root.name != REGION_RESOURCE_V4_CANDIDATE_ID:
        raise RegionResourceV7CandidateError(
            "v7_frozen_v4_directory_identity_mismatch"
        )
    if destination.name != resolved.candidate_id:
        raise RegionResourceV7CandidateError(
            "v7_candidate_directory_identity_mismatch"
        )
    if "model_registry" in destination.parts:
        raise RegionResourceV7CandidateError(
            "v7_unregistered_candidate_registry_output_forbidden"
        )
    if destination in {source_a_root, source_b_root}:
        raise RegionResourceV7CandidateError(
            "v7_candidate_output_matches_source_forbidden"
        )
    if (
        source_a_root in destination.parents
        or source_b_root in destination.parents
    ):
        raise RegionResourceV7CandidateError(
            "v7_candidate_output_inside_source_forbidden"
        )
    if destination.exists() or destination.is_symlink():
        raise RegionResourceV7CandidateError(
            "v7_candidate_output_already_exists"
        )
    source_a_binding = _validate_frozen_v4_source(source_a_root)
    source_a = _load_v7_source(
        source_a_root / "development_dataset",
        source_id=REGION_RESOURCE_V7_SOURCE_A_ID,
    )
    source_b = _load_v7_source(
        source_b_root,
        source_id=REGION_RESOURCE_V7_SOURCE_B_ID,
        expected_dataset_sha256=(
            REGION_RESOURCE_V7_SOURCE_B_DATASET_SHA256
        ),
        expected_split_sha256=REGION_RESOURCE_V7_SOURCE_B_SPLIT_SHA256,
    )
    selected_identity_before = {
        REGION_RESOURCE_V7_SOURCE_A_ID: _selected_source_identity(source_a),
        REGION_RESOURCE_V7_SOURCE_B_ID: _selected_source_identity(source_b),
    }
    source_a_binding = {
        **source_a_binding,
        "source_id": REGION_RESOURCE_V7_SOURCE_A_ID,
        **selected_identity_before[REGION_RESOURCE_V7_SOURCE_A_ID],
    }
    source_b_binding = {
        "source_id": REGION_RESOURCE_V7_SOURCE_B_ID,
        "source_kind": "m16n24_labeled_development_train_validation",
        "dataset_sha256": source_b.manifest.dataset_sha256,
        "dataset_split_sha256": source_b.manifest.split.split_sha256,
        "development_seed_class": "4016-4079",
        "development_seed_reuse_as_v7_independent_evaluation": False,
        **selected_identity_before[REGION_RESOURCE_V7_SOURCE_B_ID],
    }
    source_a_binding.pop("source_evaluation_payload_read_count", None)
    source_bindings = {
        "schema": REGION_RESOURCE_V7_SOURCE_SCHEMA,
        "implementation_file_sha256": _sha256_file(
            Path(__file__).resolve()
        ),
        "sources": {
            REGION_RESOURCE_V7_SOURCE_A_ID: source_a_binding,
            REGION_RESOURCE_V7_SOURCE_B_ID: source_b_binding,
        },
        "fit_splits": [RegionLearningSplit.TRAIN.value],
        "checkpoint_splits": [RegionLearningSplit.VALIDATION.value],
        "payload_splits_read": [
            RegionLearningSplit.TRAIN.value,
            RegionLearningSplit.VALIDATION.value,
        ],
        "test_payload_read_count": 0,
        "test_payload_fit_count": 0,
        "formal_holdout_payload_read_count": 0,
        "prior_evaluation_payload_read_count": 0,
        "independent_evaluation_payload_read_count": 0,
        "forbidden_formal_holdout_seeds": "1000-1019",
        "forbidden_prior_evaluation_seeds": "3008-3039",
        "forbidden_v7_independent_evaluation_seeds": "5216-5279",
    }
    source_bindings["content_sha256"] = _canonical_sha256(
        source_bindings
    )
    source_audit = audit_v7_sources(source_a, source_b)
    model, training_audit = train_v7_actor(
        source_a,
        source_b,
        config=resolved,
    )
    training_audit["source_audit"] = source_audit
    training_audit["source_binding_content_sha256"] = source_bindings[
        "content_sha256"
    ]
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
        _write_json(
            staging / REGION_RESOURCE_V7_SOURCE_FILENAME,
            source_bindings,
        )
        _write_json(
            staging / REGION_RESOURCE_V7_CONFIG_FILENAME,
            resolved.to_dict(),
        )
        _write_json(
            staging / REGION_RESOURCE_V7_AUDIT_FILENAME,
            training_audit,
        )
        bundle_manifest = _save_v7_model_bundle(
            model,
            staging / "bundle",
            config=resolved,
            training_audit=training_audit,
        )
        loaded_model, loaded_bundle = _load_v7_model_bundle(
            staging / "bundle",
            expected_model_version=resolved.model_version,
            expected_state_file_sha256=bundle_manifest[
                "state_dict_file_sha256"
            ],
        )
        if (
            loaded_bundle["content_sha256"]
            != bundle_manifest["content_sha256"]
            or _model_state_content_sha256(loaded_model)
            != training_audit["model_state_content_sha256"]
        ):
            raise RegionResourceV7CandidateError(
                "v7_saved_model_content_identity_mismatch"
            )
        selected_identity_after = {
            REGION_RESOURCE_V7_SOURCE_A_ID: _selected_source_identity(
                source_a
            ),
            REGION_RESOURCE_V7_SOURCE_B_ID: _selected_source_identity(
                source_b
            ),
        }
        if selected_identity_after != selected_identity_before:
            raise RegionResourceV7CandidateError(
                "v7_build_modified_selected_source_payload"
            )
        artifact_files = {
            str(path.relative_to(staging)): _sha256_file(path)
            for path in sorted(staging.rglob("*"))
            if path.is_file()
        }
        manifest = {
            "schema": REGION_RESOURCE_V7_CANDIDATE_SCHEMA,
            "candidate_id": resolved.candidate_id,
            "model_version": resolved.model_version,
            "base_v4_candidate_id": REGION_RESOURCE_V4_CANDIDATE_ID,
            "source_binding_content_sha256": source_bindings[
                "content_sha256"
            ],
            "implementation_file_sha256": source_bindings[
                "implementation_file_sha256"
            ],
            "source_a_dataset_sha256": source_a.manifest.dataset_sha256,
            "source_a_split_sha256": source_a.manifest.split.split_sha256,
            "source_b_dataset_sha256": source_b.manifest.dataset_sha256,
            "source_b_split_sha256": source_b.manifest.split.split_sha256,
            "training_audit_content_sha256": training_audit[
                "content_sha256"
            ],
            "model_state_content_sha256": training_audit[
                "model_state_content_sha256"
            ],
            "bundle_state_file_sha256": bundle_manifest[
                "state_dict_file_sha256"
            ],
            "bundle_manifest_content_sha256": bundle_manifest[
                "content_sha256"
            ],
            "artifact_files": artifact_files,
            "architecture": (
                "deterministic-r0-node-actions-plus-learned-directed-"
                "transfer-residual"
            ),
            "maximum_active_residual_edges": (
                REGION_RESOURCE_V7_MAX_ACTIVE_RESIDUAL_EDGES
            ),
            "activation_threshold": resolved.activation_threshold,
            "lifecycle_stage": MODEL_LIFECYCLE_DEVELOPMENT,
            "maximum_advisor_mode": MODEL_MAXIMUM_MODE_SHADOW,
            "candidate_status": (
                "unregistered_rule_node_transfer_residual_development"
            ),
            "development_gate_passed": True,
            "source_independent_evaluation_status": "not_started",
            "confidence_calibration_status": (
                "not_available_actor_must_pass_independent_evaluation"
            ),
            "confidence_calibrator_available": False,
            "fixed_minimum_confidence_gate_applied": False,
            "development_only": True,
            "shadow_only": True,
            "admission_closed": True,
            "rule_fallback_required": True,
            "formal_holdout_evaluated": False,
            "source_independent_evaluation_completed": False,
            "runtime_preflight_completed": False,
            "permissions": RegionResourceV7Permissions().to_dict(),
        }
        manifest["content_sha256"] = _canonical_sha256(manifest)
        _write_json(
            staging / REGION_RESOURCE_V7_CANDIDATE_FILENAME,
            manifest,
        )
        staging.replace(destination)
        return manifest
    except Exception:
        shutil.rmtree(temporary_parent, ignore_errors=True)
        raise
    finally:
        if temporary_parent.exists():
            shutil.rmtree(temporary_parent, ignore_errors=True)


def _load_v7_source(
    root: Path,
    *,
    source_id: str,
    expected_dataset_sha256: str | None = None,
    expected_split_sha256: str | None = None,
) -> LoadedRegionLearningDataset:
    if root.is_symlink():
        raise RegionResourceV7CandidateError(
            f"v7_source_symlink_forbidden:{source_id}"
        )
    try:
        loaded = load_region_learning_dataset_splits(
            root,
            splits=(
                RegionLearningSplit.TRAIN,
                RegionLearningSplit.VALIDATION,
            ),
        )
    except Exception as exc:
        raise RegionResourceV7CandidateError(
            f"v7_source_load_failed:{source_id}:{type(exc).__name__}:{exc}"
        ) from exc
    _validate_v7_loaded_source(loaded)
    if (
        expected_dataset_sha256 is not None
        and loaded.manifest.dataset_sha256 != expected_dataset_sha256
    ):
        raise RegionResourceV7CandidateError(
            f"v7_source_dataset_identity_mismatch:{source_id}"
        )
    if (
        expected_split_sha256 is not None
        and loaded.manifest.split.split_sha256 != expected_split_sha256
    ):
        raise RegionResourceV7CandidateError(
            f"v7_source_split_identity_mismatch:{source_id}"
        )
    return loaded


def _validate_v7_loaded_source(
    loaded: LoadedRegionLearningDataset,
) -> None:
    observed_splits = {
        episode.split for episode in loaded.episode_records
    }
    if observed_splits != {
        RegionLearningSplit.TRAIN,
        RegionLearningSplit.VALIDATION,
    }:
        raise RegionResourceV7CandidateError(
            "v7_loaded_payload_must_be_train_validation_only"
        )
    for episode in loaded.episode_records:
        seed = int(episode.source.seed)
        if seed in REGION_RESOURCE_V7_FORBIDDEN_FORMAL_HOLDOUT_SEEDS:
            raise RegionResourceV7CandidateError(
                "v7_formal_holdout_seed_read_forbidden"
            )
        if seed in REGION_RESOURCE_V7_FORBIDDEN_PRIOR_EVALUATION_SEEDS:
            raise RegionResourceV7CandidateError(
                "v7_prior_evaluation_seed_read_forbidden"
            )
        if seed in REGION_RESOURCE_V7_FORBIDDEN_INDEPENDENT_EVALUATION_SEEDS:
            raise RegionResourceV7CandidateError(
                "v7_independent_evaluation_seed_read_forbidden"
            )


def _selected_source_identity(
    loaded: LoadedRegionLearningDataset,
) -> dict[str, Any]:
    manifest_path = loaded.root / "manifest.json"
    selected_entries = [
        episode.manifest for episode in loaded.episode_records
    ]
    selected_files = {
        entry.relative_path: _sha256_file(
            loaded.root / entry.relative_path
        )
        for entry in selected_entries
    }
    if any(
        selected_files[entry.relative_path] != entry.episode_sha256
        for entry in selected_entries
    ):
        raise RegionResourceV7CandidateError(
            "v7_selected_episode_payload_hash_mismatch"
        )
    return {
        "manifest_file_sha256": _sha256_file(manifest_path),
        "dataset_sha256": loaded.manifest.dataset_sha256,
        "dataset_split_sha256": loaded.manifest.split.split_sha256,
        "selected_episode_count": len(selected_entries),
        "selected_frame_count": sum(
            int(entry.frame_count) for entry in selected_entries
        ),
        "selected_episode_files": dict(sorted(selected_files.items())),
        "selected_episode_files_content_sha256": _canonical_sha256(
            selected_files
        ),
        "payload_splits_read": [
            RegionLearningSplit.TRAIN.value,
            RegionLearningSplit.VALIDATION.value,
        ],
        "test_payload_read_count": 0,
        "formal_holdout_payload_read_count": 0,
        "prior_evaluation_payload_read_count": 0,
        "independent_evaluation_payload_read_count": 0,
    }


def _baseline_transfer_fractions(
    graph: Any,
    baseline: RegionResourceRecommendation,
) -> Any:
    counts = _transfer_count_by_key(baseline)
    return torch.tensor(
        [
            [
                counts.get(
                    (
                        edge.edge_id,
                        edge.source_region_id,
                        edge.target_region_id,
                    ),
                    0,
                )
                / max(1, int(edge.transferable_resources))
            ]
            for edge in graph.edge_refs
        ],
        dtype=graph.node_features.dtype,
        device=graph.node_features.device,
    ).reshape((-1, 1))


def _decode_active_edges(
    logits: Any,
    *,
    frame_activation_logit: Any,
    threshold: float,
) -> tuple[int, ...]:
    if (
        int(logits.numel()) == 0
        or float(frame_activation_logit) < float(threshold)
    ):
        return ()
    maximum_index = int(torch.argmax(logits[:, 0]).item())
    return (maximum_index,)


def _transfer_by_key(
    recommendation: RegionResourceRecommendation,
) -> dict[tuple[str, str, str], RegionTransferSuggestion]:
    return {
        (
            transfer.edge_id,
            transfer.source_region_id,
            transfer.target_region_id,
        ): transfer
        for transfer in recommendation.transfers
    }


def _transfer_count_by_key(
    recommendation: RegionResourceRecommendation,
) -> dict[tuple[str, str, str], int]:
    return {
        key: int(transfer.resource_count)
        for key, transfer in _transfer_by_key(recommendation).items()
    }


def _residual_signature(
    baseline: Mapping[tuple[str, str, str], int],
    candidate: Mapping[tuple[str, str, str], int],
) -> tuple[tuple[str, str, str, int, int], ...]:
    return tuple(
        sorted(
            (
                edge_id,
                source_region,
                target_region,
                int(baseline.get(key, 0)),
                int(candidate.get(key, 0)),
            )
            for key in set(baseline) | set(candidate)
            for edge_id, source_region, target_region in (key,)
            if int(baseline.get(key, 0)) != int(candidate.get(key, 0))
        )
    )


def _node_nontransfer_fields_equal(
    candidate: RegionResourceRecommendation,
    baseline: RegionResourceRecommendation,
) -> bool:
    """Require every raw RegionResourceAction field to match the R0 tuple."""

    return candidate.actions == baseline.actions


def _validate_v7_output(
    output: V7TransferResidualOutput,
    *,
    edge_count: int,
) -> None:
    if (
        output.activation_logits.shape != (edge_count, 1)
        or output.resource_counts.shape != (edge_count, 1)
        or output.frame_activation_logit.shape != ()
        or not bool(torch.isfinite(output.activation_logits).all().item())
        or not bool(torch.isfinite(output.resource_counts).all().item())
        or not bool(torch.isfinite(output.frame_activation_logit).item())
        or bool((output.resource_counts < 0.0).any().item())
    ):
        raise RegionResourceV7CandidateError(
            "v7_actor_output_invalid"
        )


def _save_v7_model_bundle(
    model: V7TransferResidualGraphActor,
    bundle_root: Path,
    *,
    config: RegionResourceV7BuildConfig,
    training_audit: Mapping[str, Any],
) -> dict[str, Any]:
    bundle_root.mkdir(parents=True, exist_ok=False)
    state_path = bundle_root / "state_dict.pt"
    temporary_state = bundle_root / "state_dict.pt.tmp"
    _write_v7_state_dict(temporary_state, model.state_dict())
    temporary_state.replace(state_path)
    manifest = {
        "schema": REGION_RESOURCE_V7_BUNDLE_SCHEMA,
        "architecture": (
            "directed-edge-transfer-residual-actor-without-node-head-v7"
        ),
        "model_version": config.model_version,
        "hidden_dim": config.hidden_dim,
        "node_feature_dim": len(NODE_FEATURE_NAMES),
        "edge_feature_dim": len(EDGE_FEATURE_NAMES),
        "state_dict_file": state_path.name,
        "state_dict_format": "d4-v7-canonical-tensor-stream-v1",
        "state_dict_file_sha256": _sha256_file(state_path),
        "model_state_content_sha256": _model_state_content_sha256(model),
        "created_at_utc": config.created_at_utc,
        "training_audit_content_sha256": training_audit["content_sha256"],
        "lifecycle_stage": MODEL_LIFECYCLE_DEVELOPMENT,
        "maximum_advisor_mode": MODEL_MAXIMUM_MODE_SHADOW,
        "runtime_loader_registered": False,
        "runtime_confidence_gate_available": False,
        "confidence_calibrator_available": False,
        "fixed_minimum_confidence_gate_applied": False,
        "admission_closed": True,
        "rule_fallback_required": True,
    }
    manifest["content_sha256"] = _canonical_sha256(manifest)
    _write_json(bundle_root / "manifest.json", manifest)
    return manifest


def _load_v7_model_bundle(
    bundle_root: Path,
    *,
    expected_model_version: str,
    expected_state_file_sha256: str,
) -> tuple[V7TransferResidualGraphActor, dict[str, Any]]:
    manifest = json.loads(
        (bundle_root / "manifest.json").read_text(encoding="utf-8")
    )
    content_sha256 = manifest.pop("content_sha256", None)
    if content_sha256 != _canonical_sha256(manifest):
        raise RegionResourceV7CandidateError(
            "v7_bundle_manifest_content_identity_mismatch"
        )
    manifest["content_sha256"] = content_sha256
    if (
        manifest.get("schema") != REGION_RESOURCE_V7_BUNDLE_SCHEMA
        or manifest.get("model_version") != expected_model_version
        or manifest.get("runtime_loader_registered") is not False
        or manifest.get("runtime_confidence_gate_available") is not False
        or manifest.get("confidence_calibrator_available") is not False
        or manifest.get("fixed_minimum_confidence_gate_applied") is not False
    ):
        raise RegionResourceV7CandidateError(
            "v7_bundle_contract_mismatch"
        )
    state_path = bundle_root / str(manifest["state_dict_file"])
    state_file_sha256 = _sha256_file(state_path)
    if (
        state_file_sha256 != expected_state_file_sha256
        or state_file_sha256 != manifest["state_dict_file_sha256"]
    ):
        raise RegionResourceV7CandidateError(
            "v7_bundle_state_file_identity_mismatch"
        )
    if manifest.get("state_dict_format") != (
        "d4-v7-canonical-tensor-stream-v1"
    ):
        raise RegionResourceV7CandidateError(
            "v7_bundle_state_format_mismatch"
        )
    model = V7TransferResidualGraphActor(
        hidden_dim=int(manifest["hidden_dim"])
    )
    model.load_state_dict(_read_v7_state_dict(state_path), strict=True)
    model.eval()
    if (
        not _model_parameters_finite(model)
        or _model_state_content_sha256(model)
        != manifest["model_state_content_sha256"]
    ):
        raise RegionResourceV7CandidateError(
            "v7_bundle_model_content_identity_mismatch"
        )
    return model, manifest


def _write_v7_state_dict(path: Path, state: Mapping[str, Any]) -> None:
    with path.open("wb") as handle:
        handle.write(REGION_RESOURCE_V7_STATE_MAGIC)
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


def _read_v7_state_dict(path: Path) -> dict[str, Any]:
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
        if handle.read(len(REGION_RESOURCE_V7_STATE_MAGIC)) != (
            REGION_RESOURCE_V7_STATE_MAGIC
        ):
            raise RegionResourceV7CandidateError(
                "v7_state_magic_mismatch"
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
                raise RegionResourceV7CandidateError(
                    "v7_state_metadata_length_invalid"
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
                raise RegionResourceV7CandidateError(
                    "v7_state_tensor_metadata_invalid"
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
                raise RegionResourceV7CandidateError(
                    "v7_state_tensor_shape_mismatch"
                )
            state[name] = tensor.reshape(shape)
        if handle.read(1):
            raise RegionResourceV7CandidateError(
                "v7_state_trailing_bytes"
            )
    return state


def _read_exact(handle: Any, size: int) -> bytes:
    value = handle.read(size)
    if len(value) != size:
        raise RegionResourceV7CandidateError("v7_state_truncated")
    return value


def _model_state_content_sha256(model: Any) -> str:
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


def _model_device(model: Any) -> Any:
    return next(model.parameters()).device


def _require_torch() -> None:
    if torch is None:
        raise RegionResourceV7CandidateError(
            "v7_rule_node_residual_candidate_requires_torch"
        )


__all__ = [
    "REGION_RESOURCE_V7_CANDIDATE_FILENAME",
    "REGION_RESOURCE_V7_CANDIDATE_ID",
    "REGION_RESOURCE_V7_FORBIDDEN_INDEPENDENT_EVALUATION_SEEDS",
    "REGION_RESOURCE_V7_MODEL_VERSION",
    "REGION_RESOURCE_V7_SOURCE_B_DATASET_SHA256",
    "REGION_RESOURCE_V7_SOURCE_B_SPLIT_SHA256",
    "RegionResourceV7BuildConfig",
    "RegionResourceV7CandidateError",
    "RegionResourceV7Permissions",
    "RegionResourceV7TrainBalance",
    "V7ModelIdentity",
    "V7RuleNodeTransferResidualPolicy",
    "V7TransferResidualGraphActor",
    "V7TransferResidualOutput",
    "audit_v7_sources",
    "build_region_resource_v7_rule_node_residual_candidate",
    "derive_v7_train_balance",
    "evaluate_v7_actor",
    "train_v7_actor",
]
