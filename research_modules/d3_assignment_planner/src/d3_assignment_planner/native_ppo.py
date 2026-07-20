"""Small native PyTorch PPO for sparse residual and hold/replan research."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Sequence

import numpy as np

from .learning import EDGE_FEATURE_NAMES, ResidualPrediction
from .learning_data import LearningFrameRecord, OfflineRewardComponents
from .solver import HungarianDemandSlotSolver


SHARED_EDGE_ACTOR_CRITIC_POLICY_V1 = "d3_shared_edge_actor_critic_v1"
ADVICE_ACTIONS = ("neutral", "hold", "replan")


try:  # The deterministic planner remains importable without PyTorch.
    import torch
    from torch import nn
except ImportError:  # pragma: no cover - dependency-light deployments
    torch = None
    nn = None


@dataclass(frozen=True)
class SparsePolicyAction:
    residuals: np.ndarray
    edge_mask: np.ndarray
    advice_action: int
    log_probability: float
    value: float
    confidence: float

    @property
    def advice(self) -> str:
        return ADVICE_ACTIONS[int(self.advice_action)]


if nn is not None:

    class SharedEdgeActorCriticPolicy(nn.Module):
        """Shared edge actor with masked pooled context and no dense action head."""

        def __init__(
            self,
            feature_count: int = len(EDGE_FEATURE_NAMES),
            hidden_size: int = 64,
            residual_bound: float = 2.0,
        ) -> None:
            super().__init__()
            if feature_count < 1 or hidden_size < 1 or residual_bound <= 0.0:
                raise ValueError("policy dimensions and residual_bound must be positive")
            self.feature_count = int(feature_count)
            self.hidden_size = int(hidden_size)
            self.residual_bound = float(residual_bound)
            self.edge_encoder = nn.Sequential(
                nn.Linear(self.feature_count, self.hidden_size),
                nn.Tanh(),
                nn.Linear(self.hidden_size, self.hidden_size),
                nn.Tanh(),
            )
            self.residual_mean_head = nn.Linear(self.hidden_size, 1)
            self.selection_head = nn.Linear(self.hidden_size, 1)
            self.log_std = nn.Parameter(torch.full((1,), -0.7))
            self.advice_head = nn.Sequential(
                nn.Linear(self.hidden_size, self.hidden_size),
                nn.Tanh(),
                nn.Linear(self.hidden_size, len(ADVICE_ACTIONS)),
            )
            self.value_head = nn.Sequential(
                nn.Linear(self.hidden_size, self.hidden_size),
                nn.Tanh(),
                nn.Linear(self.hidden_size, 1),
            )

        def forward(
            self,
            features: Any,
            edge_mask: Any | None = None,
        ) -> tuple[Any, Any, Any, Any, Any]:
            matrix = features
            if matrix.ndim != 2 or matrix.shape[1] != self.feature_count:
                raise ValueError("features have the wrong shared-edge shape")
            mask = _torch_edge_mask(matrix, edge_mask)
            hidden = self.edge_encoder(matrix)
            latent_mean = self.residual_mean_head(hidden).squeeze(-1)
            selection_logits = self.selection_head(hidden).squeeze(-1)
            log_std = torch.clamp(self.log_std, min=-4.0, max=1.0).expand_as(
                latent_mean
            )
            if torch.any(mask):
                pooled = hidden[mask].mean(dim=0)
            else:
                pooled = torch.zeros(
                    self.hidden_size, dtype=hidden.dtype, device=hidden.device
                )
            advice_logits = self.advice_head(pooled)
            value = self.value_head(pooled).squeeze(-1)
            return latent_mean, log_std, selection_logits, advice_logits, value

        def predict(self, features: np.ndarray) -> ResidualPrediction:
            """Return deterministic bounded residuals for guarded shadow/assist."""

            matrix = np.asarray(features, dtype=np.float32)
            if matrix.ndim != 2 or matrix.shape[1] != self.feature_count:
                raise ValueError("features have the wrong shared-edge shape")
            device = next(self.parameters()).device
            self.eval()
            with torch.no_grad():
                tensor = torch.as_tensor(matrix, dtype=torch.float32, device=device)
                mean, _, selection, _, _ = self(tensor)
                residual = self.residual_bound * torch.tanh(mean)
                confidence = torch.sigmoid(torch.abs(selection))
            return ResidualPrediction(
                delta_costs=residual.cpu().numpy(),
                confidence=confidence.cpu().numpy(),
            )

        def act(
            self,
            features: np.ndarray,
            *,
            edge_mask: np.ndarray | None = None,
            advice_allowed: bool,
            deterministic: bool = False,
        ) -> SparsePolicyAction:
            matrix = np.asarray(features, dtype=np.float32)
            mask_array = _numpy_edge_mask(matrix, edge_mask)
            device = next(self.parameters()).device
            tensor = torch.as_tensor(matrix, dtype=torch.float32, device=device)
            mask = torch.as_tensor(mask_array, dtype=torch.bool, device=device)
            self.eval()
            with torch.no_grad():
                mean, log_std, selection, advice_logits, value = self(tensor, mask)
                distribution = torch.distributions.Normal(mean, torch.exp(log_std))
                latent = mean if deterministic else distribution.sample()
                squashed = torch.tanh(latent)
                residuals = self.residual_bound * squashed
                residuals = torch.where(mask, residuals, torch.zeros_like(residuals))
                residual_log_probability = _bounded_normal_log_probability(
                    distribution,
                    latent,
                    squashed,
                    mask,
                    self.residual_bound,
                )
                if advice_allowed:
                    advice_distribution = torch.distributions.Categorical(
                        logits=advice_logits
                    )
                    advice = (
                        torch.argmax(advice_logits)
                        if deterministic
                        else advice_distribution.sample()
                    )
                    advice_log_probability = advice_distribution.log_prob(advice)
                else:
                    advice = torch.zeros((), dtype=torch.long, device=device)
                    advice_log_probability = torch.zeros((), device=device)
                log_probability = residual_log_probability + advice_log_probability
                confidence = torch.sigmoid(torch.abs(selection[mask])).min()
            return SparsePolicyAction(
                residuals=residuals.cpu().numpy(),
                edge_mask=mask_array,
                advice_action=int(advice.item()),
                log_probability=float(log_probability.item()),
                value=float(value.item()),
                confidence=float(confidence.item()),
            )

        def evaluate_action(
            self,
            features: Any,
            edge_mask: Any,
            residuals: Any,
            advice_action: int,
            *,
            advice_allowed: bool,
        ) -> tuple[Any, Any, Any, Any]:
            """Return log probability, entropy, value, and selection logits."""

            mean, log_std, selection, advice_logits, value = self(features, edge_mask)
            mask = _torch_edge_mask(features, edge_mask)
            bounded = residuals / self.residual_bound
            if torch.any(torch.abs(bounded[mask]) >= 1.0):
                bounded = torch.clamp(bounded, min=-1.0 + 1.0e-6, max=1.0 - 1.0e-6)
            latent = torch.atanh(torch.clamp(bounded, -1.0 + 1.0e-6, 1.0 - 1.0e-6))
            distribution = torch.distributions.Normal(mean, torch.exp(log_std))
            log_probability = _bounded_normal_log_probability(
                distribution,
                latent,
                torch.tanh(latent),
                mask,
                self.residual_bound,
            )
            entropy = distribution.entropy()[mask].mean()
            if advice_allowed:
                advice_distribution = torch.distributions.Categorical(
                    logits=advice_logits
                )
                advice = torch.as_tensor(
                    int(advice_action), dtype=torch.long, device=features.device
                )
                log_probability = log_probability + advice_distribution.log_prob(advice)
                entropy = entropy + advice_distribution.entropy()
            return log_probability, entropy, value, selection

else:

    class SharedEdgeActorCriticPolicy:  # pragma: no cover
        def __init__(self, *_: Any, **__: Any) -> None:
            raise ImportError("PyTorch is required for the optional D3 PPO path")


@dataclass(frozen=True)
class PPOTransition:
    features: np.ndarray
    edge_mask: np.ndarray
    residual_action: np.ndarray
    advice_action: int
    advice_allowed: bool
    old_log_probability: float
    old_value: float
    reward: float
    advantage: float
    return_value: float
    scenario_version: str
    seed: int
    episode: str
    frame_index: int

    def __post_init__(self) -> None:
        features = np.asarray(self.features, dtype=np.float32)
        mask = np.asarray(self.edge_mask, dtype=bool).reshape(-1)
        actions = np.asarray(self.residual_action, dtype=np.float32).reshape(-1)
        if features.ndim != 2 or features.shape[1] != len(EDGE_FEATURE_NAMES):
            raise ValueError("PPO transition features have the wrong shape")
        if mask.shape != (features.shape[0],) or actions.shape != mask.shape:
            raise ValueError("PPO mask and residual actions must match sparse edges")
        if not np.any(mask):
            raise ValueError("PPO transition requires at least one candidate edge")
        if np.any(np.abs(actions[~mask]) > 1.0e-8):
            raise ValueError("masked edges cannot carry a PPO residual action")
        if not 0 <= int(self.advice_action) < len(ADVICE_ACTIONS):
            raise ValueError("unsupported PPO advice action")
        if not self.advice_allowed and int(self.advice_action) != 0:
            raise ValueError("hold/replan advice is blocked outside advice intervals")
        scalars = (
            self.old_log_probability,
            self.old_value,
            self.reward,
            self.advantage,
            self.return_value,
        )
        if not all(isfinite(float(value)) for value in scalars):
            raise ValueError("PPO transition scalars must be finite")
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "edge_mask", mask)
        object.__setattr__(self, "residual_action", actions)


@dataclass(frozen=True)
class PPOUpdateResult:
    transition_count: int
    epoch_count: int
    policy_loss: float
    value_loss: float
    entropy: float
    approximate_kl: float
    clip_fraction: float
    gradient_norm: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "transition_count": int(self.transition_count),
            "epoch_count": int(self.epoch_count),
            "policy_loss": float(self.policy_loss),
            "value_loss": float(self.value_loss),
            "entropy": float(self.entropy),
            "approximate_kl": float(self.approximate_kl),
            "clip_fraction": float(self.clip_fraction),
            "gradient_norm": float(self.gradient_norm),
        }


class ClippedPPOTrainer:
    """Native clipped PPO update over variable-length frame transitions."""

    def __init__(
        self,
        policy: SharedEdgeActorCriticPolicy,
        *,
        learning_rate: float = 3.0e-4,
        clip_ratio: float = 0.2,
        value_coefficient: float = 0.5,
        entropy_coefficient: float = 0.01,
        max_gradient_norm: float = 1.0,
        epochs: int = 4,
        mini_batch_frames: int = 8,
        seed: int = 0,
    ) -> None:
        if torch is None or nn is None:  # pragma: no cover
            raise ImportError("PyTorch is required for native PPO")
        if learning_rate <= 0.0 or not 0.0 < clip_ratio < 1.0:
            raise ValueError("invalid PPO learning rate or clip ratio")
        if epochs < 1 or mini_batch_frames < 1 or max_gradient_norm <= 0.0:
            raise ValueError("invalid PPO epoch, batch, or gradient limit")
        self.policy = policy
        self.clip_ratio = float(clip_ratio)
        self.value_coefficient = float(value_coefficient)
        self.entropy_coefficient = float(entropy_coefficient)
        self.max_gradient_norm = float(max_gradient_norm)
        self.epochs = int(epochs)
        self.mini_batch_frames = int(mini_batch_frames)
        self.rng = np.random.default_rng(int(seed))
        self.optimizer = torch.optim.Adam(policy.parameters(), lr=float(learning_rate))

    def update(self, transitions: Iterable[PPOTransition]) -> PPOUpdateResult:
        items = tuple(transitions)
        if not items:
            raise ValueError("at least one PPO transition is required")
        advantages = np.asarray([item.advantage for item in items], dtype=np.float32)
        if len(items) > 1 and float(np.std(advantages)) > 1.0e-8:
            advantages = (advantages - np.mean(advantages)) / (
                np.std(advantages) + 1.0e-8
            )
        device = next(self.policy.parameters()).device
        totals: list[tuple[float, float, float, float, float, float]] = []
        self.policy.train()
        for _ in range(self.epochs):
            order = self.rng.permutation(len(items))
            for start in range(0, len(items), self.mini_batch_frames):
                indices = order[start : start + self.mini_batch_frames]
                policy_terms: list[Any] = []
                value_terms: list[Any] = []
                entropies: list[Any] = []
                kls: list[Any] = []
                clipped: list[Any] = []
                for index in indices:
                    item = items[int(index)]
                    features = torch.as_tensor(
                        item.features, dtype=torch.float32, device=device
                    )
                    mask = torch.as_tensor(item.edge_mask, dtype=torch.bool, device=device)
                    actions = torch.as_tensor(
                        item.residual_action, dtype=torch.float32, device=device
                    )
                    log_probability, entropy, value, _ = self.policy.evaluate_action(
                        features,
                        mask,
                        actions,
                        item.advice_action,
                        advice_allowed=item.advice_allowed,
                    )
                    old_log_probability = torch.as_tensor(
                        item.old_log_probability, dtype=torch.float32, device=device
                    )
                    ratio = torch.exp(log_probability - old_log_probability)
                    advantage = torch.as_tensor(
                        advantages[int(index)], dtype=torch.float32, device=device
                    )
                    unclipped = ratio * advantage
                    clipped_objective = torch.clamp(
                        ratio, 1.0 - self.clip_ratio, 1.0 + self.clip_ratio
                    ) * advantage
                    policy_terms.append(-torch.minimum(unclipped, clipped_objective))
                    return_value = torch.as_tensor(
                        item.return_value, dtype=torch.float32, device=device
                    )
                    value_terms.append((value - return_value).square())
                    entropies.append(entropy)
                    kls.append(old_log_probability - log_probability)
                    clipped.append((torch.abs(ratio - 1.0) > self.clip_ratio).float())
                policy_loss = torch.stack(policy_terms).mean()
                value_loss = torch.stack(value_terms).mean()
                entropy = torch.stack(entropies).mean()
                total_loss = (
                    policy_loss
                    + self.value_coefficient * value_loss
                    - self.entropy_coefficient * entropy
                )
                self.optimizer.zero_grad()
                total_loss.backward()
                gradient_norm = nn.utils.clip_grad_norm_(
                    self.policy.parameters(), self.max_gradient_norm
                )
                self.optimizer.step()
                totals.append(
                    (
                        float(policy_loss.detach().item()),
                        float(value_loss.detach().item()),
                        float(entropy.detach().item()),
                        float(torch.stack(kls).mean().detach().item()),
                        float(torch.stack(clipped).mean().detach().item()),
                        float(gradient_norm.detach().item()),
                    )
                )
        metrics = np.asarray(totals, dtype=float)
        if not np.all(np.isfinite(metrics)):
            raise FloatingPointError("native PPO update produced non-finite metrics")
        return PPOUpdateResult(
            transition_count=len(items),
            epoch_count=self.epochs,
            policy_loss=float(np.mean(metrics[:, 0])),
            value_loss=float(np.mean(metrics[:, 1])),
            entropy=float(np.mean(metrics[:, 2])),
            approximate_kl=float(np.mean(metrics[:, 3])),
            clip_fraction=float(np.mean(metrics[:, 4])),
            gradient_norm=float(np.max(metrics[:, 5])),
        )


def collect_ppo_transitions(
    policy: SharedEdgeActorCriticPolicy,
    records: Sequence[LearningFrameRecord],
    *,
    feature_mean: np.ndarray,
    feature_scale: np.ndarray,
    gamma: float = 0.99,
    gae_lambda: float = 0.95,
    alpha: float = 0.25,
    deterministic: bool = False,
) -> tuple[PPOTransition, ...]:
    """Collect auditable synthetic/offline rollouts without producing assignments."""

    if not 0.0 <= gamma <= 1.0 or not 0.0 <= gae_lambda <= 1.0:
        raise ValueError("gamma and gae_lambda must be in [0, 1]")
    mean = np.asarray(feature_mean, dtype=np.float32).reshape(-1)
    scale = np.asarray(feature_scale, dtype=np.float32).reshape(-1)
    if mean.shape != (len(EDGE_FEATURE_NAMES),) or scale.shape != mean.shape:
        raise ValueError("normalization statistics have the wrong feature shape")
    if np.any(scale <= 0.0) or not np.all(np.isfinite(mean + scale)):
        raise ValueError("normalization statistics must be finite and positive")
    groups: dict[tuple[str, int, str], list[LearningFrameRecord]] = {}
    for record in records:
        if record.candidate_features.shape[0] == 0:
            continue
        groups.setdefault(record.episode_group, []).append(record)
    transitions: list[PPOTransition] = []
    solver = HungarianDemandSlotSolver()
    for group in sorted(groups):
        frames = sorted(groups[group], key=lambda item: item.frame_index)
        actions: list[SparsePolicyAction] = []
        rewards: list[float] = []
        for frame in frames:
            normalized = (frame.candidate_features - mean) / scale
            action = policy.act(
                normalized,
                edge_mask=np.ones(normalized.shape[0], dtype=bool),
                advice_allowed=frame.advice_allowed,
                deterministic=deterministic,
            )
            actions.append(action)
            rewards.append(
                _counterfactual_rule_reward(
                    frame,
                    action,
                    solver=solver,
                    alpha=alpha,
                )
            )
        advantages = np.zeros(len(frames), dtype=np.float32)
        returns = np.zeros(len(frames), dtype=np.float32)
        next_value = 0.0
        gae = 0.0
        for index in range(len(frames) - 1, -1, -1):
            delta = rewards[index] + gamma * next_value - actions[index].value
            gae = delta + gamma * gae_lambda * gae
            advantages[index] = gae
            returns[index] = gae + actions[index].value
            next_value = actions[index].value
        for index, frame in enumerate(frames):
            normalized = (frame.candidate_features - mean) / scale
            action = actions[index]
            transitions.append(
                PPOTransition(
                    features=normalized,
                    edge_mask=action.edge_mask,
                    residual_action=action.residuals,
                    advice_action=action.advice_action,
                    advice_allowed=frame.advice_allowed,
                    old_log_probability=action.log_probability,
                    old_value=action.value,
                    reward=rewards[index],
                    advantage=float(advantages[index]),
                    return_value=float(returns[index]),
                    scenario_version=frame.scenario_version,
                    seed=frame.seed,
                    episode=frame.episode,
                    frame_index=frame.frame_index,
                )
            )
    if not transitions:
        raise ValueError("PPO rollout contains no candidate-edge frames")
    return tuple(transitions)


def _counterfactual_rule_reward(
    frame: LearningFrameRecord,
    action: SparsePolicyAction,
    *,
    solver: HungarianDemandSlotSolver,
    alpha: float,
) -> float:
    """Score a residual/advice proposal after deterministic mask and solver gates."""

    proposal_matrix = frame.rule_cost_matrix.copy()
    for offset, (row, column) in enumerate(frame.candidate_edge_indices):
        if action.edge_mask[offset]:
            proposal_matrix[row, column] += float(alpha) * np.tanh(
                float(action.residuals[offset])
            )
    slot_targets: list[int] = []
    for target_index, demand in enumerate(frame.target_demand_slots):
        slot_targets.extend([target_index] * max(1, int(demand)))
    slot_rows = np.asarray(slot_targets, dtype=int)
    result = solver.solve(
        proposal_matrix[slot_rows, :],
        frame.unassigned_costs[slot_rows],
        candidate_mask=frame.action_mask[slot_rows, :],
    )
    selected = tuple(
        sorted(
            {
                (slot_targets[item.target_index], int(item.resource_index))
                for item in result.assignments
            }
        )
    )
    safety_rejections = int(frame.reward_components.safety_rejections)
    if action.advice_action == 1 and frame.advice_allowed:
        if _hold_edges_are_safe(frame):
            selected = tuple(sorted(set(frame.previous_selected_edges)))
        else:
            safety_rejections += 1
    assigned_counts = {
        target_index: sum(row == target_index for row, _ in selected)
        for target_index in range(len(frame.target_demand_slots))
    }
    unmet = sum(
        max(0, int(demand) - assigned_counts[index])
        for index, demand in enumerate(frame.target_demand_slots)
    )
    high_threat_rows = [
        index
        for index, threat in enumerate(frame.target_threat_scores)
        if float(threat) >= 0.7
    ]
    high_threat_coverage = (
        1.0
        if not high_threat_rows
        else float(
            np.mean(
                [
                    min(
                        1.0,
                        assigned_counts[index]
                        / max(1, int(frame.target_demand_slots[index])),
                    )
                    for index in high_threat_rows
                ]
            )
        )
    )
    rule_total_cost = sum(
        float(frame.rule_cost_matrix[row, column]) for row, column in selected
    )
    rule_total_cost += sum(
        max(0, int(demand) - assigned_counts[index])
        * float(frame.unassigned_costs[index])
        for index, demand in enumerate(frame.target_demand_slots)
    )
    components = OfflineRewardComponents(
        high_threat_coverage=high_threat_coverage,
        rule_total_cost=max(0.0, rule_total_cost),
        unmet_demand_slots=int(unmet),
        reassignment_churn=len(
            set(selected).symmetric_difference(frame.previous_selected_edges)
        ),
        plan_expired=int(frame.reward_components.plan_expired),
        safety_rejections=safety_rejections,
    )
    return components.weighted_total()


def _hold_edges_are_safe(frame: LearningFrameRecord) -> bool:
    if not frame.previous_selected_edges:
        return False
    resources = [column for _, column in frame.previous_selected_edges]
    if len(resources) != len(set(resources)):
        return False
    counts: dict[int, int] = {}
    for row, column in frame.previous_selected_edges:
        if not frame.action_mask[row, column]:
            return False
        counts[row] = counts.get(row, 0) + 1
        if counts[row] > int(frame.target_demand_slots[row]):
            return False
    return True


def _numpy_edge_mask(
    features: np.ndarray,
    edge_mask: np.ndarray | None,
) -> np.ndarray:
    if features.ndim != 2 or features.shape[1] != len(EDGE_FEATURE_NAMES):
        raise ValueError("features have the wrong shared-edge shape")
    mask = (
        np.ones(features.shape[0], dtype=bool)
        if edge_mask is None
        else np.asarray(edge_mask, dtype=bool).reshape(-1)
    )
    if mask.shape != (features.shape[0],) or not np.any(mask):
        raise ValueError("edge mask must retain at least one sparse candidate")
    return mask


def _torch_edge_mask(features: Any, edge_mask: Any | None) -> Any:
    if edge_mask is None:
        mask = torch.ones(features.shape[0], dtype=torch.bool, device=features.device)
    else:
        mask = edge_mask.to(dtype=torch.bool, device=features.device).reshape(-1)
    if mask.shape != (features.shape[0],) or not torch.any(mask):
        raise ValueError("edge mask must retain at least one sparse candidate")
    return mask


def _bounded_normal_log_probability(
    distribution: Any,
    latent: Any,
    squashed: Any,
    mask: Any,
    residual_bound: float,
) -> Any:
    correction = torch.log(
        float(residual_bound) * (1.0 - squashed.square()) + 1.0e-6
    )
    return (distribution.log_prob(latent) - correction)[mask].mean()
