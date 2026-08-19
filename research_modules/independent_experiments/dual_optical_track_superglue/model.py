"""Track-level SuperGlue architecture with masked partial optimal transport."""

from __future__ import annotations

from dataclasses import dataclass
import math

import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence

from .config import ModelConfig


@dataclass(frozen=True)
class OptimalTransportResult:
    log_assignment: torch.Tensor
    assignment: torch.Tensor
    row_marginals: torch.Tensor
    column_marginals: torch.Tensor


@dataclass(frozen=True)
class SuperGlueOutput:
    descriptors_a: torch.Tensor
    descriptors_b: torch.Tensor
    similarity_logits: torch.Tensor
    transport: OptimalTransportResult


def log_sinkhorn(
    log_scores: torch.Tensor,
    log_row_marginals: torch.Tensor,
    log_column_marginals: torch.Tensor,
    iterations: int = 30,
) -> torch.Tensor:
    """Run balanced Sinkhorn normalization in log space."""

    if log_scores.ndim != 2:
        raise ValueError("log_scores must be a two-dimensional matrix")
    if log_row_marginals.shape != (log_scores.shape[0],):
        raise ValueError("row marginal shape does not match scores")
    if log_column_marginals.shape != (log_scores.shape[1],):
        raise ValueError("column marginal shape does not match scores")
    if iterations <= 0:
        raise ValueError("Sinkhorn iteration count must be positive")
    if not torch.isfinite(log_scores).all():
        raise ValueError("Sinkhorn scores must be finite")
    row_dual = torch.zeros_like(log_row_marginals)
    column_dual = torch.zeros_like(log_column_marginals)
    for _ in range(iterations):
        row_dual = log_row_marginals - torch.logsumexp(
            log_scores + column_dual.unsqueeze(0), dim=1
        )
        column_dual = log_column_marginals - torch.logsumexp(
            log_scores + row_dual.unsqueeze(1), dim=0
        )
    result = log_scores + row_dual.unsqueeze(1) + column_dual.unsqueeze(0)
    if not torch.isfinite(result).all():
        raise FloatingPointError("log-Sinkhorn produced a non-finite value")
    return result


def partial_optimal_transport(
    similarity_logits: torch.Tensor,
    candidate_mask: torch.Tensor,
    dustbin_score: torch.Tensor,
    iterations: int = 30,
) -> OptimalTransportResult:
    """Add a dustbin row/column and solve the masked partial assignment."""

    if similarity_logits.ndim != 2 or candidate_mask.shape != similarity_logits.shape:
        raise ValueError("similarity logits and candidate mask must be equal two-dimensional shapes")
    if candidate_mask.dtype != torch.bool:
        raise ValueError("candidate mask must be boolean")
    count_a, count_b = similarity_logits.shape
    dtype, device = similarity_logits.dtype, similarity_logits.device
    if count_a == 0 or count_b == 0:
        assignment = torch.zeros((count_a + 1, count_b + 1), dtype=dtype, device=device)
        if count_a == 0 and count_b == 0:
            assignment[0, 0] = 1.0
        elif count_a == 0:
            assignment[0, :count_b] = 1.0
        else:
            assignment[:count_a, 0] = 1.0
        return OptimalTransportResult(
            log_assignment=torch.log(assignment.clamp_min(torch.finfo(dtype).tiny)),
            assignment=assignment,
            row_marginals=assignment.sum(dim=1),
            column_marginals=assignment.sum(dim=0),
        )

    minimum = torch.tensor(torch.finfo(dtype).min / 16.0, dtype=dtype, device=device)
    masked_scores = torch.where(candidate_mask, similarity_logits, minimum)
    dustbin_column = dustbin_score.expand(count_a, 1)
    dustbin_row = dustbin_score.expand(1, count_b)
    corner = dustbin_score.reshape(1, 1)
    augmented = torch.cat(
        (
            torch.cat((masked_scores, dustbin_column), dim=1),
            torch.cat((dustbin_row, corner), dim=1),
        ),
        dim=0,
    )
    normalizer = -math.log(count_a + count_b)
    log_rows = torch.cat(
        (
            torch.full((count_a,), normalizer, dtype=dtype, device=device),
            torch.tensor([math.log(count_b) + normalizer], dtype=dtype, device=device),
        )
    )
    log_columns = torch.cat(
        (
            torch.full((count_b,), normalizer, dtype=dtype, device=device),
            torch.tensor([math.log(count_a) + normalizer], dtype=dtype, device=device),
        )
    )
    normalized = log_sinkhorn(augmented, log_rows, log_columns, iterations)
    adjusted = normalized - normalizer
    probabilities = torch.exp(adjusted)
    real_mask = torch.ones_like(probabilities, dtype=torch.bool)
    real_mask[:count_a, :count_b] = candidate_mask
    probabilities = probabilities.masked_fill(~real_mask, 0.0)
    adjusted = torch.where(
        real_mask,
        adjusted,
        torch.full_like(adjusted, torch.finfo(dtype).min / 16.0),
    )
    return OptimalTransportResult(
        log_assignment=adjusted,
        assignment=probabilities,
        row_marginals=torch.cat(
            (
                torch.ones(count_a, dtype=dtype, device=device),
                torch.tensor([float(count_b)], dtype=dtype, device=device),
            )
        ),
        column_marginals=torch.cat(
            (
                torch.ones(count_b, dtype=dtype, device=device),
                torch.tensor([float(count_a)], dtype=dtype, device=device),
            )
        ),
    )


class TrackDescriptorEncoder(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.gru = nn.GRU(
            config.observation_feature_dim,
            config.descriptor_dim,
            num_layers=1,
            batch_first=True,
        )
        self.track_mlp = nn.Sequential(
            nn.Linear(config.track_feature_dim, config.descriptor_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.descriptor_dim, config.descriptor_dim),
        )
        self.fusion = nn.Sequential(
            nn.Linear(config.descriptor_dim * 2, config.descriptor_dim),
            nn.ReLU(),
            nn.LayerNorm(config.descriptor_dim),
        )
        self.descriptor_dim = config.descriptor_dim

    def forward(
        self,
        histories: torch.Tensor,
        lengths: torch.Tensor,
        track_features: torch.Tensor,
    ) -> torch.Tensor:
        count = histories.shape[0]
        if count == 0:
            return histories.new_empty((0, self.descriptor_dim))
        if histories.ndim != 3 or track_features.ndim != 2:
            raise ValueError("history and track features have invalid ranks")
        if lengths.shape != (count,) or torch.any(lengths < 1):
            raise ValueError("each track must have at least one history observation")
        packed = pack_padded_sequence(
            histories,
            lengths.detach().to(device="cpu", dtype=torch.long),
            batch_first=True,
            enforce_sorted=False,
        )
        _, hidden = self.gru(packed)
        sequence_descriptor = hidden[-1]
        track_descriptor = self.track_mlp(track_features)
        return self.fusion(torch.cat((sequence_descriptor, track_descriptor), dim=1))


class MaskedMultiHeadAttention(nn.Module):
    def __init__(self, descriptor_dim: int, heads: int, dropout: float) -> None:
        super().__init__()
        if descriptor_dim % heads:
            raise ValueError("descriptor dimension must be divisible by head count")
        self.query = nn.Linear(descriptor_dim, descriptor_dim)
        self.key = nn.Linear(descriptor_dim, descriptor_dim)
        self.value = nn.Linear(descriptor_dim, descriptor_dim)
        self.output = nn.Linear(descriptor_dim, descriptor_dim)
        self.heads = heads
        self.head_dim = descriptor_dim // heads
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        query: torch.Tensor,
        key_value: torch.Tensor,
        *,
        mask: torch.Tensor | None = None,
        pair_bias: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if query.shape[0] == 0 or key_value.shape[0] == 0:
            return torch.zeros_like(query)
        query_heads = self.query(query).view(len(query), self.heads, self.head_dim).permute(1, 0, 2)
        key_heads = self.key(key_value).view(len(key_value), self.heads, self.head_dim).permute(1, 0, 2)
        value_heads = self.value(key_value).view(len(key_value), self.heads, self.head_dim).permute(1, 0, 2)
        scores = torch.matmul(query_heads, key_heads.transpose(1, 2)) / math.sqrt(self.head_dim)
        if pair_bias is not None:
            if pair_bias.shape != (len(query), len(key_value), self.heads):
                raise ValueError("pair bias has an invalid shape")
            scores = scores + pair_bias.permute(2, 0, 1)
        if mask is None:
            expanded_mask = torch.ones_like(scores, dtype=torch.bool)
        else:
            if mask.shape != (len(query), len(key_value)) or mask.dtype != torch.bool:
                raise ValueError("attention mask has an invalid shape or type")
            expanded_mask = mask.unsqueeze(0).expand(self.heads, -1, -1)
        minimum = torch.finfo(scores.dtype).min / 16.0
        weights = torch.softmax(scores.masked_fill(~expanded_mask, minimum), dim=-1)
        weights = weights.masked_fill(~expanded_mask, 0.0)
        weights = weights / weights.sum(dim=-1, keepdim=True).clamp_min(1.0e-12)
        attended = torch.matmul(self.dropout(weights), value_heads)
        attended = attended.permute(1, 0, 2).reshape(len(query), -1)
        return self.output(attended)


class AttentionUpdate(nn.Module):
    def __init__(self, descriptor_dim: int, heads: int, dropout: float) -> None:
        super().__init__()
        self.attention = MaskedMultiHeadAttention(descriptor_dim, heads, dropout)
        self.norm_attention = nn.LayerNorm(descriptor_dim)
        self.feed_forward = nn.Sequential(
            nn.Linear(descriptor_dim, descriptor_dim * 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(descriptor_dim * 2, descriptor_dim),
        )
        self.norm_feed_forward = nn.LayerNorm(descriptor_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(self, values: torch.Tensor, context: torch.Tensor, **kwargs: torch.Tensor) -> torch.Tensor:
        if len(values) == 0:
            return values
        attended = self.attention(values, context, **kwargs)
        values = self.norm_attention(values + self.dropout(attended))
        return self.norm_feed_forward(values + self.dropout(self.feed_forward(values)))


class AttentionCycle(nn.Module):
    def __init__(self, descriptor_dim: int, heads: int, dropout: float) -> None:
        super().__init__()
        self.self_a = AttentionUpdate(descriptor_dim, heads, dropout)
        self.self_b = AttentionUpdate(descriptor_dim, heads, dropout)
        self.cross_a = AttentionUpdate(descriptor_dim, heads, dropout)
        self.cross_b = AttentionUpdate(descriptor_dim, heads, dropout)

    def forward(
        self,
        descriptor_a: torch.Tensor,
        descriptor_b: torch.Tensor,
        candidate_mask: torch.Tensor,
        edge_bias: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        descriptor_a = self.self_a(descriptor_a, descriptor_a)
        descriptor_b = self.self_b(descriptor_b, descriptor_b)
        previous_a, previous_b = descriptor_a, descriptor_b
        descriptor_a = self.cross_a(
            previous_a, previous_b, mask=candidate_mask, pair_bias=edge_bias
        )
        descriptor_b = self.cross_b(
            previous_b,
            previous_a,
            mask=candidate_mask.transpose(0, 1),
            pair_bias=edge_bias.permute(1, 0, 2),
        )
        return descriptor_a, descriptor_b


class TrackSuperGlue(nn.Module):
    """SuperGlue-style partial matcher over anonymous local tracks."""

    def __init__(self, config: ModelConfig | None = None) -> None:
        super().__init__()
        self.config = config or ModelConfig()
        self.encoder = TrackDescriptorEncoder(self.config)
        self.edge_bias_encoder = nn.Sequential(
            nn.Linear(self.config.edge_feature_dim, self.config.descriptor_dim),
            nn.ReLU(),
            nn.Dropout(self.config.dropout),
            nn.Linear(self.config.descriptor_dim, self.config.attention_heads),
        )
        self.cycles = nn.ModuleList(
            [
                AttentionCycle(
                    self.config.descriptor_dim,
                    self.config.attention_heads,
                    self.config.dropout,
                )
                for _ in range(self.config.attention_cycles)
            ]
        )
        self.geometry_score = nn.Sequential(
            nn.Linear(self.config.edge_feature_dim, self.config.descriptor_dim),
            nn.ReLU(),
            nn.Linear(self.config.descriptor_dim, 1),
        )
        self.dustbin_score = nn.Parameter(torch.tensor(1.0))

    def forward(
        self,
        histories_a: torch.Tensor,
        histories_b: torch.Tensor,
        lengths_a: torch.Tensor,
        lengths_b: torch.Tensor,
        track_features_a: torch.Tensor,
        track_features_b: torch.Tensor,
        edge_features: torch.Tensor,
        candidate_mask: torch.Tensor,
    ) -> SuperGlueOutput:
        descriptor_a = self.encoder(histories_a, lengths_a, track_features_a)
        descriptor_b = self.encoder(histories_b, lengths_b, track_features_b)
        expected_edge_shape = (
            len(descriptor_a),
            len(descriptor_b),
            self.config.edge_feature_dim,
        )
        if edge_features.shape != expected_edge_shape:
            raise ValueError("edge feature tensor has an invalid shape")
        if candidate_mask.shape != expected_edge_shape[:2] or candidate_mask.dtype != torch.bool:
            raise ValueError("candidate mask has an invalid shape or type")
        edge_bias = self.edge_bias_encoder(edge_features)
        edge_bias = edge_bias.masked_fill(~candidate_mask.unsqueeze(-1), 0.0)
        for cycle in self.cycles:
            descriptor_a, descriptor_b = cycle(
                descriptor_a, descriptor_b, candidate_mask, edge_bias
            )
        normalized_a = torch.nn.functional.normalize(descriptor_a, dim=1) if len(descriptor_a) else descriptor_a
        normalized_b = torch.nn.functional.normalize(descriptor_b, dim=1) if len(descriptor_b) else descriptor_b
        similarity = torch.matmul(normalized_a, normalized_b.transpose(0, 1))
        if similarity.numel():
            similarity = similarity + self.geometry_score(edge_features).squeeze(-1)
        similarity = similarity.masked_fill(
            ~candidate_mask, torch.finfo(similarity.dtype).min / 16.0
        )
        transport = partial_optimal_transport(
            similarity,
            candidate_mask,
            self.dustbin_score,
            self.config.sinkhorn_iterations,
        )
        return SuperGlueOutput(descriptor_a, descriptor_b, similarity, transport)
