"""Optional shared-edge learning residuals around the deterministic rule planner."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from time import perf_counter
from typing import Any, Iterable, Mapping

import numpy as np

from .costs import CostMatrixResult
from .models import AssignmentPlan, ResourceState, TargetTrack


LEARNING_RESIDUAL_SCHEMA_V1 = "d3_shared_edge_residual_v1"
FEATURE_DISTRIBUTION_ASSESSMENT_SCHEMA_V1 = (
    "d3_feature_distribution_assessment_v1"
)
EDGE_FEATURE_NAMES = (
    "rule_cost_squashed",
    "threat",
    "window_cost",
    "covariance_cost_squashed",
    "reachability_cost_squashed",
    "region_cost_squashed",
    "resource_state_cost_squashed",
    "fov_cost_squashed",
    "conflict_cost_squashed",
    "demand_count",
    "primary_count",
    "previous_binding",
)
BINARY_EDGE_FEATURE_NAMES = ("previous_binding",)
BINARY_FEATURE_ENDPOINT_TOLERANCE = 1.0e-6


@dataclass(frozen=True)
class LearningAssistConfig:
    """Runtime guardrails for optional residual inference."""

    mode: str = "shadow"
    alpha: float = 0.25
    timeout_s: float = 0.05
    min_confidence: float = 0.6
    ood_z_threshold: float = 6.0
    absolute_feature_limit: float = 10.0

    def __post_init__(self) -> None:
        mode = str(self.mode).strip().lower()
        if mode not in {"disabled", "shadow", "assist"}:
            raise ValueError("learning mode must be disabled, shadow, or assist")
        if not isfinite(self.alpha) or self.alpha < 0.0:
            raise ValueError("alpha must be finite and non-negative")
        if not isfinite(self.timeout_s) or self.timeout_s <= 0.0:
            raise ValueError("timeout_s must be finite and positive")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0, 1]")
        if not isfinite(self.ood_z_threshold) or self.ood_z_threshold <= 0.0:
            raise ValueError("ood_z_threshold must be finite and positive")
        if not isfinite(self.absolute_feature_limit) or self.absolute_feature_limit <= 0.0:
            raise ValueError("absolute_feature_limit must be finite and positive")
        object.__setattr__(self, "mode", mode)


@dataclass(frozen=True)
class LearningActionMask:
    """Full matrix mask used before candidate-edge residual inference."""

    mask: np.ndarray
    reason_counts: tuple[tuple[str, int], ...]
    expected_previous_version: int
    current_plan_version: int
    version_compatible: bool

    @property
    def action_count(self) -> int:
        return int(np.count_nonzero(self.mask))


@dataclass(frozen=True)
class CandidateEdgeBatch:
    """Variable-length candidate edge batch; no dense M-by-N action head."""

    edge_indices: tuple[tuple[int, int], ...]
    features: np.ndarray
    rule_costs: np.ndarray
    action_mask: LearningActionMask
    feature_names: tuple[str, ...] = EDGE_FEATURE_NAMES

    @property
    def edge_count(self) -> int:
        return len(self.edge_indices)


@dataclass(frozen=True)
class ResidualPrediction:
    delta_costs: np.ndarray
    confidence: float | np.ndarray


@dataclass(frozen=True)
class FeatureDistributionAssessment:
    """Truth-free explanation of one feature-distribution decision."""

    is_ood: bool
    reason: str
    z_threshold: float | None
    trigger_feature: str | None = None
    trigger_feature_index: int | None = None
    trigger_edge_offset: int | None = None
    max_continuous_z: float | None = None
    max_continuous_z_feature: str | None = None
    max_continuous_z_edge_offset: int | None = None
    binary_tolerance: float = BINARY_FEATURE_ENDPOINT_TOLERANCE
    schema_version: str = FEATURE_DISTRIBUTION_ASSESSMENT_SCHEMA_V1

    def to_metadata(self) -> dict[str, Any]:
        """Return additive metadata without target/resource identity."""

        return {
            "learning_distribution_diagnostic_schema": self.schema_version,
            "learning_distribution_is_ood": bool(self.is_ood),
            "learning_distribution_reason": self.reason,
            "learning_distribution_trigger_feature": self.trigger_feature,
            "learning_distribution_trigger_feature_index": (
                self.trigger_feature_index
            ),
            "learning_distribution_trigger_edge_offset": (
                self.trigger_edge_offset
            ),
            "learning_distribution_max_continuous_z": self.max_continuous_z,
            "learning_distribution_max_continuous_z_feature": (
                self.max_continuous_z_feature
            ),
            "learning_distribution_max_continuous_z_edge_offset": (
                self.max_continuous_z_edge_offset
            ),
            "learning_distribution_z_threshold": self.z_threshold,
            "learning_distribution_binary_tolerance": float(
                self.binary_tolerance
            ),
        }


@dataclass(frozen=True)
class FeatureDistributionGuard:
    """Feature-semantic train-split guard for shadow and assist inference."""

    mean: np.ndarray
    scale: np.ndarray
    feature_names: tuple[str, ...] = EDGE_FEATURE_NAMES

    def __post_init__(self) -> None:
        feature_names = tuple(str(value) for value in self.feature_names)
        if feature_names != EDGE_FEATURE_NAMES:
            raise ValueError("feature guard names do not match the D3 schema")
        mean = np.asarray(self.mean, dtype=np.float32).reshape(-1).copy()
        scale = np.asarray(self.scale, dtype=np.float32).reshape(-1).copy()
        if mean.shape != (len(feature_names),) or scale.shape != mean.shape:
            raise ValueError("feature guard statistics have the wrong shape")
        if not np.all(np.isfinite(mean)) or not np.all(np.isfinite(scale)):
            raise ValueError("feature guard statistics must be finite")
        if np.any(scale <= 0.0):
            raise ValueError("feature guard scales must be positive")
        mean.setflags(write=False)
        scale.setflags(write=False)
        object.__setattr__(self, "feature_names", feature_names)
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "scale", scale)

    @classmethod
    def fit(
        cls,
        features: np.ndarray | Iterable[np.ndarray],
        *,
        minimum_scale: float = 1.0e-3,
    ) -> "FeatureDistributionGuard":
        if isinstance(features, np.ndarray):
            matrix = np.asarray(features, dtype=np.float32)
        else:
            values = tuple(np.asarray(value, dtype=np.float32) for value in features)
            if not values:
                raise ValueError("at least one feature batch is required")
            matrix = np.concatenate(values, axis=0)
        if matrix.ndim != 2 or matrix.shape[0] == 0:
            raise ValueError("features must have shape (edge_count, feature_count)")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("feature guard training data must be finite")
        return cls(
            mean=np.mean(matrix, axis=0),
            scale=np.maximum(np.std(matrix, axis=0), float(minimum_scale)),
        )

    def evaluate(
        self,
        features: np.ndarray,
        *,
        z_threshold: float,
        binary_tolerance: float = BINARY_FEATURE_ENDPOINT_TOLERANCE,
    ) -> FeatureDistributionAssessment:
        """Apply domain checks to binary features and z checks to continuous ones."""

        threshold = float(z_threshold)
        tolerance = float(binary_tolerance)
        if not isfinite(threshold) or threshold <= 0.0:
            return FeatureDistributionAssessment(
                is_ood=True,
                reason="invalid_z_threshold",
                z_threshold=None,
                binary_tolerance=tolerance,
            )
        if not isfinite(tolerance) or tolerance < 0.0:
            return FeatureDistributionAssessment(
                is_ood=True,
                reason="invalid_binary_tolerance",
                z_threshold=threshold,
                binary_tolerance=BINARY_FEATURE_ENDPOINT_TOLERANCE,
            )
        try:
            matrix = np.asarray(features, dtype=np.float32)
        except (TypeError, ValueError):
            return FeatureDistributionAssessment(
                is_ood=True,
                reason="feature_array_invalid",
                z_threshold=threshold,
                binary_tolerance=tolerance,
            )
        if matrix.ndim != 2 or matrix.shape[1:] != self.mean.shape:
            return FeatureDistributionAssessment(
                is_ood=True,
                reason="feature_shape_mismatch",
                z_threshold=threshold,
                binary_tolerance=tolerance,
            )
        nonfinite = np.argwhere(~np.isfinite(matrix))
        if nonfinite.size:
            edge_offset, feature_index = (
                int(nonfinite[0, 0]),
                int(nonfinite[0, 1]),
            )
            return FeatureDistributionAssessment(
                is_ood=True,
                reason="non_finite_feature",
                z_threshold=threshold,
                trigger_feature=self.feature_names[feature_index],
                trigger_feature_index=feature_index,
                trigger_edge_offset=edge_offset,
                binary_tolerance=tolerance,
            )

        binary_indices = tuple(
            self.feature_names.index(name) for name in BINARY_EDGE_FEATURE_NAMES
        )
        continuous_indices = tuple(
            index
            for index in range(len(self.feature_names))
            if index not in binary_indices
        )
        max_z: float | None = None
        max_z_feature: str | None = None
        max_z_edge_offset: int | None = None
        if matrix.shape[0] and continuous_indices:
            index_array = np.asarray(continuous_indices, dtype=int)
            continuous_z = np.abs(
                (matrix[:, index_array] - self.mean[index_array])
                / self.scale[index_array]
            )
            flat_offset = int(np.argmax(continuous_z))
            edge_offset, local_feature_index = np.unravel_index(
                flat_offset,
                continuous_z.shape,
            )
            feature_index = continuous_indices[int(local_feature_index)]
            max_z = float(continuous_z[edge_offset, local_feature_index])
            max_z_feature = self.feature_names[feature_index]
            max_z_edge_offset = int(edge_offset)

        for feature_index in binary_indices:
            values = matrix[:, feature_index]
            at_zero = np.isclose(values, 0.0, rtol=0.0, atol=tolerance)
            at_one = np.isclose(values, 1.0, rtol=0.0, atol=tolerance)
            invalid_offsets = np.flatnonzero(~(at_zero | at_one))
            if invalid_offsets.size:
                edge_offset = int(invalid_offsets[0])
                value = float(values[edge_offset])
                reason = (
                    "binary_feature_out_of_range"
                    if value < -tolerance or value > 1.0 + tolerance
                    else "binary_feature_not_endpoint"
                )
                return FeatureDistributionAssessment(
                    is_ood=True,
                    reason=reason,
                    z_threshold=threshold,
                    trigger_feature=self.feature_names[feature_index],
                    trigger_feature_index=feature_index,
                    trigger_edge_offset=edge_offset,
                    max_continuous_z=max_z,
                    max_continuous_z_feature=max_z_feature,
                    max_continuous_z_edge_offset=max_z_edge_offset,
                    binary_tolerance=tolerance,
                )

        if max_z is not None and max_z > threshold:
            feature_index = self.feature_names.index(str(max_z_feature))
            return FeatureDistributionAssessment(
                is_ood=True,
                reason="continuous_feature_z_threshold",
                z_threshold=threshold,
                trigger_feature=max_z_feature,
                trigger_feature_index=feature_index,
                trigger_edge_offset=max_z_edge_offset,
                max_continuous_z=max_z,
                max_continuous_z_feature=max_z_feature,
                max_continuous_z_edge_offset=max_z_edge_offset,
                binary_tolerance=tolerance,
            )
        return FeatureDistributionAssessment(
            is_ood=False,
            reason="in_distribution",
            z_threshold=threshold,
            max_continuous_z=max_z,
            max_continuous_z_feature=max_z_feature,
            max_continuous_z_edge_offset=max_z_edge_offset,
            binary_tolerance=tolerance,
        )

    def is_ood(self, features: np.ndarray, *, z_threshold: float) -> bool:
        return self.evaluate(features, z_threshold=z_threshold).is_ood


def build_learning_action_mask(
    matrix_result: CostMatrixResult,
    *,
    expected_previous_version: int,
    current_plan_version: int,
) -> LearningActionMask:
    """Mask unreachable, capacity, conflict, sparse-pruned, and stale actions."""

    mask = matrix_result.hard_safe_candidate_mask
    reason_counts: dict[str, int] = {}
    for row in matrix_result.reject_reasons:
        for reason in row:
            if reason is not None:
                reason_counts[str(reason)] = reason_counts.get(str(reason), 0) + 1
    version_compatible = int(expected_previous_version) == int(current_plan_version)
    if not version_compatible:
        masked_count = int(np.count_nonzero(mask))
        if masked_count:
            reason_counts["version_constraint"] = masked_count
        mask.fill(False)
    return LearningActionMask(
        mask=mask,
        reason_counts=tuple(sorted(reason_counts.items())),
        expected_previous_version=int(expected_previous_version),
        current_plan_version=int(current_plan_version),
        version_compatible=version_compatible,
    )


def build_candidate_edge_batch(
    matrix_result: CostMatrixResult,
    tracks: list[TargetTrack] | tuple[TargetTrack, ...],
    resources: list[ResourceState] | tuple[ResourceState, ...],
    *,
    expected_previous_version: int,
    current_plan_version: int,
    previous_plan: AssignmentPlan | None = None,
) -> CandidateEdgeBatch:
    """Extract normalized features only for currently actionable candidate edges."""

    if matrix_result.matrix.shape != (len(tracks), len(resources)):
        raise ValueError("candidate edge features require the unexpanded target-resource matrix")
    action_mask = build_learning_action_mask(
        matrix_result,
        expected_previous_version=expected_previous_version,
        current_plan_version=current_plan_version,
    )
    rows, columns = np.nonzero(action_mask.mask)
    edge_indices = tuple(
        (int(row), int(column)) for row, column in zip(rows, columns)
    )
    previous_pairs = (
        set()
        if previous_plan is None
        else {
            (assignment.target_id, assignment.resource_id)
            for assignment in previous_plan.assignments
        }
    )
    # ``effective_demand`` normalizes and validates a TargetDemand.  Cache it
    # once per target instead of rebuilding the same object for every sparse
    # candidate edge at large M-by-N scales.
    effective_demands = tuple(track.effective_demand for track in tracks)
    feature_rows: list[tuple[float, ...]] = []
    rule_costs: list[float] = []
    for target_index, resource_index in edge_indices:
        track = tracks[target_index]
        resource = resources[resource_index]
        breakdown = matrix_result.breakdowns[target_index][resource_index]
        demand = effective_demands[target_index]
        rule_cost = float(matrix_result.matrix[target_index, resource_index])
        feature_rows.append(
            (
                _squash_nonnegative(rule_cost),
                _clamp01(track.threat_score),
                _clamp01(track.window_cost),
                _squash_nonnegative(breakdown.get("covariance", 0.0)),
                _squash_nonnegative(breakdown.get("reachability_3d", 0.0)),
                _squash_nonnegative(breakdown.get("region", 0.0)),
                _squash_nonnegative(breakdown.get("resource_state", 0.0)),
                _squash_nonnegative(breakdown.get("fov", 0.0)),
                _squash_nonnegative(breakdown.get("conflict", 0.0)),
                _clamp01(demand.required_resource_count / 10.0),
                _clamp01(demand.primary_resource_count / 10.0),
                float((track.track_id, resource.resource_id) in previous_pairs),
            )
        )
        rule_costs.append(rule_cost)
    features = np.asarray(feature_rows, dtype=np.float32).reshape(
        len(edge_indices), len(EDGE_FEATURE_NAMES)
    )
    return CandidateEdgeBatch(
        edge_indices=edge_indices,
        features=features,
        rule_costs=np.asarray(rule_costs, dtype=float),
        action_mask=action_mask,
    )


class LearningCostAssistant:
    """Apply a guarded residual to rule costs or run the same path in shadow mode."""

    def __init__(
        self,
        predictor: Any,
        *,
        config: LearningAssistConfig | None = None,
        distribution_guard: FeatureDistributionGuard | None = None,
    ) -> None:
        self.predictor = predictor
        self.config = config or LearningAssistConfig()
        self.distribution_guard = distribution_guard

    def apply(
        self,
        matrix_result: CostMatrixResult,
        tracks: list[TargetTrack] | tuple[TargetTrack, ...],
        resources: list[ResourceState] | tuple[ResourceState, ...],
        *,
        expected_previous_version: int,
        current_plan_version: int,
        previous_plan: AssignmentPlan | None = None,
    ) -> CostMatrixResult:
        batch = build_candidate_edge_batch(
            matrix_result,
            tracks,
            resources,
            expected_previous_version=expected_previous_version,
            current_plan_version=current_plan_version,
            previous_plan=previous_plan,
        )
        # Every assistant result, including fallback, carries the fail-closed
        # action set used for inference.
        matrix_result = replace(
            matrix_result,
            candidate_mask=batch.action_mask.mask.copy(),
        )
        common = {
            "learning_residual_schema": LEARNING_RESIDUAL_SCHEMA_V1,
            "learning_mode": self.config.mode,
            "learning_formula": "C_final=C_rule+alpha*tanh(delta_C)",
            "learning_alpha": float(self.config.alpha),
            "learning_candidate_action_count": batch.edge_count,
            "learning_dense_action_count": 0,
            "learning_action_mask_reason_counts": batch.action_mask.reason_counts,
            "learning_expected_previous_version": int(expected_previous_version),
            "learning_current_plan_version": int(current_plan_version),
        }
        if self.config.mode == "disabled":
            return self._fallback(matrix_result, common, "disabled")
        if not batch.action_mask.version_compatible:
            return self._fallback(matrix_result, common, "version_constraint")
        if batch.edge_count == 0:
            return self._fallback(matrix_result, common, "no_candidate_edges")
        distribution = self._distribution_assessment(batch.features)
        common = {**common, **distribution.to_metadata()}
        if distribution.is_ood:
            return self._fallback(matrix_result, common, "out_of_distribution")

        started = perf_counter()
        try:
            prediction = _coerce_prediction(self.predictor.predict(batch.features))
        except Exception as exc:  # optional model failures must preserve the rule path
            return self._fallback(
                matrix_result,
                {
                    **common,
                    "learning_inference_elapsed_s": perf_counter() - started,
                    "learning_model_error": type(exc).__name__,
                },
                "model_error",
            )
        elapsed = perf_counter() - started
        if elapsed > self.config.timeout_s:
            return self._fallback(
                matrix_result,
                {**common, "learning_inference_elapsed_s": elapsed},
                "model_timeout",
            )
        delta = np.asarray(prediction.delta_costs, dtype=float).reshape(-1)
        if delta.shape != (batch.edge_count,) or not np.all(np.isfinite(delta)):
            return self._fallback(
                matrix_result,
                {**common, "learning_inference_elapsed_s": elapsed},
                "invalid_model_output",
            )
        confidence = _minimum_confidence(prediction.confidence, batch.edge_count)
        if confidence is None:
            return self._fallback(
                matrix_result,
                {**common, "learning_inference_elapsed_s": elapsed},
                "invalid_model_output",
            )
        if confidence < self.config.min_confidence:
            return self._fallback(
                matrix_result,
                {
                    **common,
                    "learning_inference_elapsed_s": elapsed,
                    "learning_confidence": confidence,
                },
                "low_confidence",
            )

        adjustment = float(self.config.alpha) * np.tanh(delta)
        proposed_matrix = matrix_result.matrix.copy()
        breakdown_rows = [
            [dict(breakdown) for breakdown in row]
            for row in matrix_result.breakdowns
        ]
        for edge_offset, (target_index, resource_index) in enumerate(batch.edge_indices):
            rule_cost = float(batch.rule_costs[edge_offset])
            proposed = rule_cost + float(adjustment[edge_offset])
            proposed_matrix[target_index, resource_index] = proposed
            breakdown = breakdown_rows[target_index][resource_index]
            breakdown["learning_rule_total"] = rule_cost
            breakdown["learning_delta_c"] = float(delta[edge_offset])
            breakdown["learning_adjustment"] = float(adjustment[edge_offset])
            breakdown["learning_proposed_total"] = proposed
            if self.config.mode == "assist":
                breakdown["total"] = proposed

        applied = self.config.mode == "assist"
        return replace(
            matrix_result,
            matrix=proposed_matrix if applied else matrix_result.matrix.copy(),
            breakdowns=(
                tuple(tuple(row) for row in breakdown_rows)
                if applied
                else matrix_result.breakdowns
            ),
            metadata={
                **dict(matrix_result.metadata),
                **common,
                "learning_inference_elapsed_s": elapsed,
                "learning_confidence": confidence,
                "learning_applied": applied,
                "learning_shadow_only": not applied,
                "learning_fallback_reason": None,
                "learning_max_abs_adjustment": float(np.max(np.abs(adjustment))),
                "learning_shadow_proposed_costs": (
                    tuple(float(value) for value in proposed_matrix[batch.action_mask.mask])
                    if not applied
                    else ()
                ),
            },
        )

    def _distribution_assessment(
        self,
        features: np.ndarray,
    ) -> FeatureDistributionAssessment:
        try:
            matrix = np.asarray(features, dtype=np.float32)
        except (TypeError, ValueError):
            return FeatureDistributionAssessment(
                is_ood=True,
                reason="feature_array_invalid",
                z_threshold=float(self.config.ood_z_threshold),
            )
        if matrix.ndim != 2 or matrix.shape[1:] != (len(EDGE_FEATURE_NAMES),):
            return FeatureDistributionAssessment(
                is_ood=True,
                reason="feature_shape_mismatch",
                z_threshold=float(self.config.ood_z_threshold),
            )
        nonfinite = np.argwhere(~np.isfinite(matrix))
        if nonfinite.size:
            edge_offset, feature_index = (
                int(nonfinite[0, 0]),
                int(nonfinite[0, 1]),
            )
            return FeatureDistributionAssessment(
                is_ood=True,
                reason="non_finite_feature",
                z_threshold=float(self.config.ood_z_threshold),
                trigger_feature=EDGE_FEATURE_NAMES[feature_index],
                trigger_feature_index=feature_index,
                trigger_edge_offset=edge_offset,
            )

        guard_assessment = (
            None
            if self.distribution_guard is None
            else self.distribution_guard.evaluate(
                matrix,
                z_threshold=self.config.ood_z_threshold,
            )
        )
        absolute_values = np.abs(matrix)
        if absolute_values.size and np.any(
            absolute_values > self.config.absolute_feature_limit
        ):
            edge_offset, feature_index = np.unravel_index(
                int(np.argmax(absolute_values)),
                absolute_values.shape,
            )
            return FeatureDistributionAssessment(
                is_ood=True,
                reason="absolute_feature_limit",
                z_threshold=float(self.config.ood_z_threshold),
                trigger_feature=EDGE_FEATURE_NAMES[int(feature_index)],
                trigger_feature_index=int(feature_index),
                trigger_edge_offset=int(edge_offset),
                max_continuous_z=(
                    None
                    if guard_assessment is None
                    else guard_assessment.max_continuous_z
                ),
                max_continuous_z_feature=(
                    None
                    if guard_assessment is None
                    else guard_assessment.max_continuous_z_feature
                ),
                max_continuous_z_edge_offset=(
                    None
                    if guard_assessment is None
                    else guard_assessment.max_continuous_z_edge_offset
                ),
            )
        if guard_assessment is not None:
            return guard_assessment
        return FeatureDistributionAssessment(
            is_ood=False,
            reason="guard_not_configured",
            z_threshold=float(self.config.ood_z_threshold),
        )

    def _is_ood(self, features: np.ndarray) -> bool:
        return self._distribution_assessment(features).is_ood

    @staticmethod
    def _fallback(
        matrix_result: CostMatrixResult,
        metadata: Mapping[str, Any],
        reason: str,
    ) -> CostMatrixResult:
        return replace(
            matrix_result,
            matrix=matrix_result.matrix.copy(),
            metadata={
                **dict(matrix_result.metadata),
                **dict(metadata),
                "learning_applied": False,
                "learning_shadow_only": False,
                "learning_fallback_reason": reason,
            },
        )


try:  # PyTorch is optional for the deterministic rule path.
    import torch
    from torch import nn
except ImportError:  # pragma: no cover - exercised in dependency-light deployments
    torch = None
    nn = None


if nn is not None:

    class SharedCandidateEdgeResidualPolicy(nn.Module):
        """One shared MLP evaluated over a variable number of candidate edges."""

        def __init__(
            self,
            feature_count: int = len(EDGE_FEATURE_NAMES),
            hidden_size: int = 32,
        ) -> None:
            super().__init__()
            if feature_count < 1 or hidden_size < 1:
                raise ValueError("feature_count and hidden_size must be positive")
            self.feature_count = int(feature_count)
            self.encoder = nn.Sequential(
                nn.Linear(self.feature_count, hidden_size),
                nn.ReLU(),
                nn.Linear(hidden_size, hidden_size),
                nn.ReLU(),
            )
            self.residual_head = nn.Linear(hidden_size, 1)
            self.selection_head = nn.Linear(hidden_size, 1)

        def forward(self, features: Any) -> tuple[Any, Any]:
            hidden = self.encoder(features)
            return (
                self.residual_head(hidden).squeeze(-1),
                self.selection_head(hidden).squeeze(-1),
            )

        def predict(self, features: np.ndarray) -> ResidualPrediction:
            matrix = np.asarray(features, dtype=np.float32)
            if matrix.ndim != 2 or matrix.shape[1] != self.feature_count:
                raise ValueError("features have the wrong shared-edge shape")
            device = next(self.parameters()).device
            self.eval()
            with torch.no_grad():
                delta, logits = self(
                    torch.as_tensor(matrix, dtype=torch.float32, device=device)
                )
                confidence = torch.sigmoid(torch.abs(logits))
            return ResidualPrediction(
                delta_costs=delta.detach().cpu().numpy(),
                confidence=confidence.detach().cpu().numpy(),
            )

else:

    class SharedCandidateEdgeResidualPolicy:  # pragma: no cover
        def __init__(self, *_: Any, **__: Any) -> None:
            raise ImportError("PyTorch is required for the optional D3 learning path")


@dataclass(frozen=True)
class BehaviorCloningBatch:
    features: np.ndarray
    selected_edges: np.ndarray
    action_mask: np.ndarray | None = None
    teacher_delta_costs: np.ndarray | None = None

    def __post_init__(self) -> None:
        features = np.asarray(self.features, dtype=np.float32)
        selected = np.asarray(self.selected_edges, dtype=np.float32).reshape(-1)
        if features.ndim != 2 or selected.shape != (features.shape[0],):
            raise ValueError("behavior-cloning features and labels have incompatible shapes")
        mask = (
            np.ones(features.shape[0], dtype=bool)
            if self.action_mask is None
            else np.asarray(self.action_mask, dtype=bool).reshape(-1)
        )
        if mask.shape != selected.shape or not np.any(mask):
            raise ValueError("behavior-cloning action mask must retain at least one edge")
        teacher = None
        if self.teacher_delta_costs is not None:
            teacher = np.asarray(self.teacher_delta_costs, dtype=np.float32).reshape(-1)
            if teacher.shape != selected.shape:
                raise ValueError("teacher_delta_costs must match selected_edges")
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "selected_edges", selected)
        object.__setattr__(self, "action_mask", mask)
        object.__setattr__(self, "teacher_delta_costs", teacher)


@dataclass(frozen=True)
class BehaviorCloningResult:
    epoch_count: int
    edge_sample_count: int
    initial_loss: float
    final_loss: float


def behavior_clone_warmup(
    policy: SharedCandidateEdgeResidualPolicy,
    batches: Iterable[BehaviorCloningBatch],
    *,
    epochs: int = 10,
    learning_rate: float = 1.0e-3,
) -> BehaviorCloningResult:
    """Run a minimal supervised warm-up; this is not PPO acceptance evidence."""

    if torch is None or nn is None:  # pragma: no cover
        raise ImportError("PyTorch is required for behavior-cloning warm-up")
    items = tuple(batches)
    if not items:
        raise ValueError("at least one behavior-cloning batch is required")
    if epochs < 1 or learning_rate <= 0.0:
        raise ValueError("epochs and learning_rate must be positive")
    device = next(policy.parameters()).device
    optimizer = torch.optim.Adam(policy.parameters(), lr=float(learning_rate))

    def batch_loss(batch: BehaviorCloningBatch) -> Any:
        features = torch.as_tensor(batch.features, dtype=torch.float32, device=device)
        labels = torch.as_tensor(batch.selected_edges, dtype=torch.float32, device=device)
        mask = torch.as_tensor(batch.action_mask, dtype=torch.bool, device=device)
        delta, logits = policy(features)
        loss = nn.functional.binary_cross_entropy_with_logits(logits[mask], labels[mask])
        if batch.teacher_delta_costs is not None:
            targets = torch.as_tensor(
                batch.teacher_delta_costs,
                dtype=torch.float32,
                device=device,
            )
            loss = loss + 0.25 * nn.functional.mse_loss(delta[mask], targets[mask])
        return loss

    policy.eval()
    with torch.no_grad():
        initial_loss = float(sum(batch_loss(batch).item() for batch in items) / len(items))
    policy.train()
    for _ in range(int(epochs)):
        for batch in items:
            optimizer.zero_grad()
            loss = batch_loss(batch)
            loss.backward()
            optimizer.step()
    policy.eval()
    with torch.no_grad():
        final_loss = float(sum(batch_loss(batch).item() for batch in items) / len(items))
    return BehaviorCloningResult(
        epoch_count=int(epochs),
        edge_sample_count=sum(int(np.count_nonzero(batch.action_mask)) for batch in items),
        initial_loss=initial_loss,
        final_loss=final_loss,
    )


def _coerce_prediction(value: Any) -> ResidualPrediction:
    if isinstance(value, ResidualPrediction):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        return ResidualPrediction(delta_costs=np.asarray(value[0]), confidence=value[1])
    if isinstance(value, Mapping):
        return ResidualPrediction(
            delta_costs=np.asarray(value["delta_costs"]),
            confidence=value["confidence"],
        )
    raise TypeError("predictor must return ResidualPrediction, a pair, or a mapping")


def _minimum_confidence(value: float | np.ndarray, edge_count: int) -> float | None:
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.size not in {1, edge_count} or not np.all(np.isfinite(array)):
        return None
    if np.any(array < 0.0) or np.any(array > 1.0):
        return None
    return float(np.min(array))


def _squash_nonnegative(value: Any) -> float:
    number = max(0.0, float(value))
    return number / (1.0 + number)


def _clamp01(value: Any) -> float:
    return max(0.0, min(1.0, float(value)))
