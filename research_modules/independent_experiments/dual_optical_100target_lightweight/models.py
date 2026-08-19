"""Lightweight probability calibrators for geometry-gated candidate edges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np
from scipy.optimize import minimize
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from dual_optical_100target_gnn.schema import (
    EDGE_FEATURE_NAMES,
    LEGACY_EDGE_FEATURE_COUNT,
    GraphLabels,
    OnlineGraph,
)


LOGISTIC_C_GRID = (0.01, 0.1, 1.0, 10.0, 100.0)
PROBABILITY_THRESHOLD_GRID = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
UNMATCHED_COST_GRID = (0.15, 0.25, 0.40, 0.60, 0.90, 1.20)
MODEL_KINDS = (
    "geometry_nonnegative",
    "platt_geometry_cost",
    "isotonic_geometry_cost",
    "logistic_edge_features",
)
GEOMETRY_COMPONENT_NAMES = (
    "coplanarity_median",
    "coplanarity_p90",
    "coplanarity_mad",
    "coplanarity_slope",
    "reprojection_rms",
    "motion_inconsistency",
    "missing_time_overlap",
    "condition_number",
)
ORIGINAL_GEOMETRY_WEIGHTS = np.asarray(
    (0.25, 0.15, 0.10, 0.10, 0.15, 0.10, 0.10, 0.05), dtype=np.float64
)


def _sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    output = np.empty_like(values)
    positive = values >= 0.0
    output[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exponential = np.exp(values[~positive])
    output[~positive] = exponential / (1.0 + exponential)
    return output


def _feature_index(name: str) -> int:
    return EDGE_FEATURE_NAMES.index(name)


def _validate_feature_width(features: np.ndarray) -> None:
    if features.ndim != 2 or features.shape[1] not in {
        LEGACY_EDGE_FEATURE_COUNT,
        len(EDGE_FEATURE_NAMES),
    }:
        raise ValueError("edge feature array does not match a supported contract")


def geometry_components(
    edge_features: np.ndarray,
    geometry_gate: Mapping[str, Any],
    *,
    covariance_aware: bool = False,
) -> np.ndarray:
    """Build dimensionless geometry and motion terms.

    Snapshot V2 supplies normalized coplanarity and motion residuals propagated
    from bearing and tracker covariance.  The scale is intentionally applied
    only to residual-like terms; time overlap and numerical conditioning retain
    their original definitions.  V1 callers retain the legacy result.
    """

    features = np.asarray(edge_features, dtype=np.float64)
    _validate_feature_width(features)
    median_limit = float(geometry_gate["coplanarity_median_mrad"])
    reprojection_limit = float(geometry_gate["maximum_reprojection_rms_px"])
    if median_limit <= 0.0 or reprojection_limit <= 0.0:
        raise ValueError("geometry gate normalization limits must be positive")

    median = features[:, _feature_index("coplanarity_median_mrad")]
    p90 = features[:, _feature_index("coplanarity_p90_mrad")]
    mad = features[:, _feature_index("coplanarity_mad_mrad")]
    slope = features[:, _feature_index("coplanarity_abs_slope_mrad_s")]
    overlap = features[:, _feature_index("time_overlap_ratio")]
    reprojection = features[:, _feature_index("reprojection_rms_px")]
    condition = features[:, _feature_index("log10_condition_number")]
    motion = features[:, _feature_index("motion_inconsistency_deg_s")]
    components = np.column_stack(
        (
            np.clip(median / median_limit, 0.0, 2.0),
            np.clip(p90 / (2.0 * median_limit), 0.0, 2.0),
            np.clip(mad / median_limit, 0.0, 2.0),
            np.clip(slope / 0.25, 0.0, 2.0),
            np.clip(reprojection / reprojection_limit, 0.0, 2.0),
            np.clip(motion / 1.0, 0.0, 2.0),
            np.clip(1.0 - overlap, 0.0, 2.0),
            np.clip(np.maximum(condition - 2.0, 0.0) / 6.0, 0.0, 2.0),
        )
    )
    if covariance_aware:
        if features.shape[1] != len(EDGE_FEATURE_NAMES):
            raise ValueError("Snapshot V2 covariance calibration requires V2 features")
        required = {
            "normalized_coplanarity_residual",
            "normalized_motion_residual",
            "combined_bearing_sigma_mrad",
        }
        if not required <= set(EDGE_FEATURE_NAMES):
            raise ValueError("Snapshot V2 covariance features are unavailable")
        sigma = np.maximum(
            features[:, _feature_index("combined_bearing_sigma_mrad")], 1.0e-6
        )
        normalized_coplanarity = features[
            :, _feature_index("normalized_coplanarity_residual")
        ]
        normalized_motion = features[:, _feature_index("normalized_motion_residual")]
        # Three standard deviations is the dimensionless reference scale.  No
        # absolute milliradian threshold is introduced by this route.
        components[:, 0] = np.clip(normalized_coplanarity / 3.0, 0.0, 2.0)
        components[:, 1] = np.clip(p90 / (3.0 * sigma), 0.0, 2.0)
        components[:, 2] = np.clip(mad / (3.0 * sigma), 0.0, 2.0)
        components[:, 5] = np.clip(normalized_motion / 3.0, 0.0, 2.0)
    if not np.all(np.isfinite(components)):
        raise ValueError("normalized geometry components must be finite")
    return components


def _balanced_sample_weights(labels: np.ndarray) -> np.ndarray:
    labels = np.asarray(labels, dtype=np.float64)
    positive = labels > 0.5
    positive_count = int(np.sum(positive))
    negative_count = len(labels) - positive_count
    if positive_count == 0 or negative_count == 0:
        raise ValueError("training labels must contain positive and negative edges")
    weights = np.empty(len(labels), dtype=np.float64)
    weights[positive] = len(labels) / (2.0 * positive_count)
    weights[~positive] = len(labels) / (2.0 * negative_count)
    return weights


def flatten_training_data(
    data: Iterable[tuple[OnlineGraph, GraphLabels]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    graphs = list(data)
    edge_arrays = [graph.edge_features for graph, _ in graphs if len(graph.edge_features)]
    cost_arrays = [graph.geometry_cost for graph, _ in graphs if len(graph.geometry_cost)]
    label_arrays = [labels.edge_labels for graph, labels in graphs if len(graph.edge_features)]
    if not edge_arrays:
        raise ValueError("training split contains no geometry-gated candidate edges")
    features = np.concatenate(edge_arrays).astype(np.float64)
    costs = np.concatenate(cost_arrays).astype(np.float64)
    labels = np.concatenate(label_arrays).astype(np.float64)
    if not (np.all(np.isfinite(features)) and np.all(np.isfinite(costs))):
        raise ValueError("training features and costs must be finite")
    _balanced_sample_weights(labels)
    return features, costs, labels


@dataclass(frozen=True)
class LightweightModel:
    """JSON-serializable fitted model with deterministic NumPy inference."""

    kind: str
    parameters: Mapping[str, Any]
    parameter_count: int

    @property
    def model_id(self) -> str:
        if self.kind == "logistic_edge_features":
            return f"{self.kind}_C{float(self.parameters['C']):g}"
        return self.kind

    def predict_proba(
        self,
        graph: OnlineGraph,
        geometry_gate: Mapping[str, Any],
        *,
        edge_features: np.ndarray | None = None,
        geometry_cost: np.ndarray | None = None,
    ) -> np.ndarray:
        features = (
            graph.edge_features.astype(np.float64)
            if edge_features is None
            else np.asarray(edge_features, dtype=np.float64)
        )
        costs = (
            graph.geometry_cost.astype(np.float64)
            if geometry_cost is None
            else np.asarray(geometry_cost, dtype=np.float64)
        )
        if features.shape != graph.edge_features.shape:
            raise ValueError("normalized edge features do not match candidate graph")
        if costs.shape != graph.geometry_cost.shape:
            raise ValueError("normalized geometry costs do not match candidate graph")
        frozen_feature_names = tuple(
            self.parameters.get("edge_feature_names", EDGE_FEATURE_NAMES)
        )
        if features.shape[1] != len(frozen_feature_names):
            raise ValueError("candidate graph feature width differs from frozen model")
        covariance_aware = bool(self.parameters.get("covariance_aware", False))
        components = geometry_components(
            features, geometry_gate, covariance_aware=covariance_aware
        )
        if covariance_aware:
            costs = components @ ORIGINAL_GEOMETRY_WEIGHTS
        if self.kind == "geometry_nonnegative":
            weights = np.asarray(self.parameters["weights"], dtype=np.float64)
            logits = float(self.parameters["intercept"]) - components @ weights
            probabilities = _sigmoid(logits)
        elif self.kind == "platt_geometry_cost":
            logits = (
                float(self.parameters["coefficient"])
                * costs
                + float(self.parameters["intercept"])
            )
            probabilities = _sigmoid(logits)
        elif self.kind == "isotonic_geometry_cost":
            x = np.asarray(self.parameters["x_thresholds"], dtype=np.float64)
            y = np.asarray(self.parameters["y_thresholds"], dtype=np.float64)
            probabilities = np.interp(
                costs,
                x,
                y,
                left=float(y[0]),
                right=float(y[-1]),
            )
        elif self.kind == "logistic_edge_features":
            mean = np.asarray(self.parameters["mean"], dtype=np.float64)
            scale = np.asarray(self.parameters["scale"], dtype=np.float64)
            coefficients = np.asarray(self.parameters["coefficients"], dtype=np.float64)
            normalized = (features - mean) / scale
            probabilities = _sigmoid(
                normalized @ coefficients + float(self.parameters["intercept"])
            )
        else:
            raise ValueError(f"unsupported lightweight model kind: {self.kind}")
        if probabilities.shape != graph.geometry_cost.shape:
            raise ValueError("model must output one probability per candidate edge")
        if not np.all(np.isfinite(probabilities)):
            raise ValueError("model probabilities must be finite")
        return np.clip(probabilities.astype(np.float64), 1.0e-6, 1.0 - 1.0e-6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "dual-optical-lightweight-model-v1",
            "kind": self.kind,
            "model_id": self.model_id,
            "parameter_count": self.parameter_count,
            "parameters": dict(self.parameters),
            "edge_feature_names": list(
                self.parameters.get("edge_feature_names", EDGE_FEATURE_NAMES)
            ),
            "geometry_component_names": list(GEOMETRY_COMPONENT_NAMES),
            "online_feature_policy": {
                "truth_id": False,
                "actor_name": False,
                "true_world_position": False,
            },
        }

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "LightweightModel":
        if values.get("schema_version") != "dual-optical-lightweight-model-v1":
            raise ValueError("unsupported lightweight model schema")
        edge_feature_names = tuple(values.get("edge_feature_names", ()))
        if edge_feature_names not in {
            tuple(EDGE_FEATURE_NAMES),
            tuple(EDGE_FEATURE_NAMES[:LEGACY_EDGE_FEATURE_COUNT]),
        }:
            raise ValueError("frozen edge feature contract does not match")
        if values.get("geometry_component_names") != list(GEOMETRY_COMPONENT_NAMES):
            raise ValueError("frozen geometry component contract does not match")
        policy = values.get("online_feature_policy")
        if policy != {
            "truth_id": False,
            "actor_name": False,
            "true_world_position": False,
        }:
            raise ValueError("frozen model violates online feature policy")
        kind = str(values["kind"])
        if kind not in MODEL_KINDS:
            raise ValueError(f"unsupported lightweight model kind: {kind}")
        return cls(kind, dict(values["parameters"]), int(values["parameter_count"]))


def fit_geometry_nonnegative(
    features: np.ndarray,
    labels: np.ndarray,
    geometry_gate: Mapping[str, Any],
    *,
    covariance_aware: bool = False,
) -> LightweightModel:
    components = geometry_components(
        features, geometry_gate, covariance_aware=covariance_aware
    )
    sample_weights = _balanced_sample_weights(labels)

    def objective(parameters: np.ndarray) -> float:
        weights = parameters[:-1]
        intercept = parameters[-1]
        probabilities = np.clip(_sigmoid(intercept - components @ weights), 1e-9, 1.0 - 1e-9)
        loss = -np.average(
            labels * np.log(probabilities) + (1.0 - labels) * np.log(1.0 - probabilities),
            weights=sample_weights,
        )
        return float(loss + 1.0e-5 * np.dot(weights, weights))

    initial = np.concatenate((ORIGINAL_GEOMETRY_WEIGHTS, np.asarray((0.0,))))
    bounds = [(0.0, None)] * len(ORIGINAL_GEOMETRY_WEIGHTS) + [(None, None)]
    result = minimize(objective, initial, method="L-BFGS-B", bounds=bounds)
    if not result.success or not np.all(np.isfinite(result.x)):
        raise RuntimeError(f"nonnegative geometry calibration failed: {result.message}")
    weights = np.maximum(result.x[:-1], 0.0)
    return LightweightModel(
        kind="geometry_nonnegative",
        parameters={
            "weights": [float(value) for value in weights],
            "intercept": float(result.x[-1]),
            "optimization_loss": float(result.fun),
            "original_weights": ORIGINAL_GEOMETRY_WEIGHTS.tolist(),
            "covariance_aware": covariance_aware,
        },
        parameter_count=len(weights) + 1,
    )


def fit_platt(
    costs: np.ndarray,
    labels: np.ndarray,
    random_seed: int,
    *,
    covariance_aware: bool = False,
) -> LightweightModel:
    estimator = LogisticRegression(
        C=1.0,
        class_weight="balanced",
        solver="lbfgs",
        max_iter=2000,
        random_state=random_seed,
    )
    estimator.fit(costs.reshape(-1, 1), labels.astype(np.int64))
    return LightweightModel(
        kind="platt_geometry_cost",
        parameters={
            "coefficient": float(estimator.coef_[0, 0]),
            "intercept": float(estimator.intercept_[0]),
            "C": 1.0,
            "covariance_aware": covariance_aware,
        },
        parameter_count=2,
    )


def fit_isotonic(
    costs: np.ndarray,
    labels: np.ndarray,
    *,
    covariance_aware: bool = False,
) -> LightweightModel:
    estimator = IsotonicRegression(increasing=False, out_of_bounds="clip")
    estimator.fit(costs, labels, sample_weight=_balanced_sample_weights(labels))
    x = np.asarray(estimator.X_thresholds_, dtype=np.float64)
    y = np.asarray(estimator.y_thresholds_, dtype=np.float64)
    if len(x) < 2:
        raise ValueError("isotonic calibration produced fewer than two thresholds")
    return LightweightModel(
        kind="isotonic_geometry_cost",
        parameters={
            "x_thresholds": x.tolist(),
            "y_thresholds": y.tolist(),
            "covariance_aware": covariance_aware,
        },
        parameter_count=2 * len(x),
    )


def fit_logistic(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    c_value: float,
    random_seed: int,
    covariance_aware: bool = False,
) -> LightweightModel:
    if c_value not in LOGISTIC_C_GRID:
        raise ValueError(f"C must be one of {LOGISTIC_C_GRID}")
    scaler = StandardScaler()
    normalized = scaler.fit_transform(features)
    estimator = LogisticRegression(
        C=float(c_value),
        class_weight="balanced",
        solver="lbfgs",
        max_iter=2000,
        random_state=random_seed,
    )
    estimator.fit(normalized, labels.astype(np.int64))
    scale = np.asarray(scaler.scale_, dtype=np.float64)
    scale[scale <= 1.0e-12] = 1.0
    return LightweightModel(
        kind="logistic_edge_features",
        parameters={
            "C": float(c_value),
            "mean": np.asarray(scaler.mean_, dtype=np.float64).tolist(),
            "scale": scale.tolist(),
            "coefficients": np.asarray(estimator.coef_[0], dtype=np.float64).tolist(),
            "intercept": float(estimator.intercept_[0]),
            "class_weight": "balanced",
            "penalty": "l2",
            "covariance_aware": covariance_aware,
        },
        parameter_count=len(EDGE_FEATURE_NAMES) + 1,
    )


def fit_all_models(
    data: Iterable[tuple[OnlineGraph, GraphLabels]],
    geometry_gate: Mapping[str, Any],
    *,
    random_seed: int,
    covariance_aware: bool = False,
) -> list[LightweightModel]:
    features, costs, labels = flatten_training_data(data)
    feature_names = list(EDGE_FEATURE_NAMES[: features.shape[1]])
    if covariance_aware:
        costs = (
            geometry_components(
                features, geometry_gate, covariance_aware=True
            )
            @ ORIGINAL_GEOMETRY_WEIGHTS
        )
    models = [
        fit_geometry_nonnegative(
            features,
            labels,
            geometry_gate,
            covariance_aware=covariance_aware,
        ),
        fit_platt(
            costs, labels, random_seed, covariance_aware=covariance_aware
        ),
        fit_isotonic(costs, labels, covariance_aware=covariance_aware),
    ]
    models.extend(
        fit_logistic(
            features,
            labels,
            c_value=c_value,
            random_seed=random_seed,
            covariance_aware=covariance_aware,
        )
        for c_value in LOGISTIC_C_GRID
    )
    if len({model.model_id for model in models}) != len(models):
        raise AssertionError("lightweight model IDs must be unique")
    return [
        LightweightModel(
            model.kind,
            {**dict(model.parameters), "edge_feature_names": feature_names},
            model.parameter_count,
        )
        for model in models
    ]


def model_complexity_key(model: LightweightModel) -> tuple[int, int, float]:
    family_order = {
        "platt_geometry_cost": 0,
        "geometry_nonnegative": 1,
        "isotonic_geometry_cost": 2,
        "logistic_edge_features": 3,
    }
    c_value = float(model.parameters.get("C", 0.0))
    return model.parameter_count, family_order[model.kind], c_value
