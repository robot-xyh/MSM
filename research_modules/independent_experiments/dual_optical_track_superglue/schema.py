"""Typed anonymous inputs for track-level partial matching."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

import numpy as np


OBSERVATION_FEATURE_NAMES = (
    "relative_time_s",
    "direction_n",
    "direction_e",
    "direction_d",
    "azimuth_rad",
    "elevation_rad",
    "confidence",
    "log_bbox_area",
    "log_detection_count",
    "sqrt_innovation_mahalanobis2",
)

TRACK_FEATURE_NAMES = (
    "sample_count",
    "duration_s",
    "sweep_count",
    "azimuth_span_deg",
    "elevation_span_deg",
    "angular_speed_deg_s",
    "missing_ratio",
    "detection_stability",
    "azimuth_rate_deg_s",
    "elevation_rate_deg_s",
    "bearing_sigma_mrad",
    "angular_rate_sigma_deg_s",
    "recent_three_hit_ratio",
    "track_state_quality",
    "snapshot_v2_available",
)

EDGE_FEATURE_NAMES = (
    "coplanarity_median_mrad",
    "coplanarity_p90_mrad",
    "coplanarity_mad_mrad",
    "coplanarity_abs_slope_mrad_s",
    "aligned_sample_count",
    "time_overlap_ratio",
    "reprojection_rms_px",
    "fitted_speed_mps",
    "log10_condition_number",
    "intersection_angle_deg",
    "motion_inconsistency_deg_s",
    "ray_residual_rms_m",
    "azimuth_rate_delta_deg_s",
    "elevation_rate_delta_deg_s",
    "normalized_motion_residual",
    "normalized_coplanarity_residual",
    "combined_bearing_sigma_mrad",
    "recent_hit_overlap_ratio",
)


@dataclass(frozen=True)
class TrackGraphInput:
    """One anonymous bipartite graph and the two stations' recent histories."""

    seed: int
    split: str
    corruption_level: str
    revolution_index: int
    cutoff_timestamp: float
    track_ids_a: tuple[str, ...]
    track_ids_b: tuple[str, ...]
    observation_history_a: np.ndarray
    observation_history_b: np.ndarray
    history_lengths_a: np.ndarray
    history_lengths_b: np.ndarray
    track_features_a: np.ndarray
    track_features_b: np.ndarray
    candidate_mask: np.ndarray
    edge_features: np.ndarray
    input_fingerprint: str = ""
    candidate_graph_fingerprint: str = ""
    metadata: Mapping[str, int | float | str] | None = None

    def validate(self) -> None:
        count_a = len(self.track_ids_a)
        count_b = len(self.track_ids_b)
        if len(set(self.track_ids_a)) != count_a or len(set(self.track_ids_b)) != count_b:
            raise ValueError("track identifiers must be unique within each station")
        if self.observation_history_a.shape != (count_a, 6, len(OBSERVATION_FEATURE_NAMES)):
            raise ValueError("invalid A observation-history shape")
        if self.observation_history_b.shape != (count_b, 6, len(OBSERVATION_FEATURE_NAMES)):
            raise ValueError("invalid B observation-history shape")
        if self.history_lengths_a.shape != (count_a,) or self.history_lengths_b.shape != (count_b,):
            raise ValueError("invalid history-length shape")
        if count_a and (np.min(self.history_lengths_a) < 1 or np.max(self.history_lengths_a) > 6):
            raise ValueError("A history lengths must be in [1, 6]")
        if count_b and (np.min(self.history_lengths_b) < 1 or np.max(self.history_lengths_b) > 6):
            raise ValueError("B history lengths must be in [1, 6]")
        if self.track_features_a.shape != (count_a, len(TRACK_FEATURE_NAMES)):
            raise ValueError("invalid A track-feature shape")
        if self.track_features_b.shape != (count_b, len(TRACK_FEATURE_NAMES)):
            raise ValueError("invalid B track-feature shape")
        if self.candidate_mask.shape != (count_a, count_b) or self.candidate_mask.dtype != np.bool_:
            raise ValueError("candidate mask must be a boolean A-by-B matrix")
        if self.edge_features.shape != (count_a, count_b, len(EDGE_FEATURE_NAMES)):
            raise ValueError("invalid dense edge-feature shape")
        if self.split not in {"train", "validation", "test", "online"}:
            raise ValueError("invalid graph split")
        if self.revolution_index < 1 or self.cutoff_timestamp < 0.0:
            raise ValueError("invalid graph time metadata")
        arrays = (
            self.observation_history_a,
            self.observation_history_b,
            self.track_features_a,
            self.track_features_b,
            self.edge_features,
        )
        if any(not np.all(np.isfinite(values)) for values in arrays):
            raise ValueError("graph features must be finite")
        if np.any(self.edge_features[~self.candidate_mask] != 0.0):
            raise ValueError("non-candidate edges must carry zero features")

    def replaced(self, **changes: object) -> "TrackGraphInput":
        result = replace(self, **changes)
        result.validate()
        return result


@dataclass(frozen=True)
class AssociationLabels:
    """Offline-only one-to-one labels kept outside online graph objects."""

    matched_pairs: tuple[tuple[int, int], ...]

    def validate(self, graph: TrackGraphInput) -> None:
        rows = [row for row, _ in self.matched_pairs]
        columns = [column for _, column in self.matched_pairs]
        if len(rows) != len(set(rows)) or len(columns) != len(set(columns)):
            raise ValueError("offline labels violate one-to-one matching")
        for row, column in self.matched_pairs:
            if not 0 <= row < len(graph.track_ids_a) or not 0 <= column < len(graph.track_ids_b):
                raise ValueError("offline label index is out of range")
            if not graph.candidate_mask[row, column]:
                raise ValueError("offline positive is absent from the frozen candidate graph")


@dataclass(frozen=True)
class TrainingExample:
    graph: TrackGraphInput
    labels: AssociationLabels

    def validate(self) -> None:
        self.graph.validate()
        self.labels.validate(self.graph)
        if self.graph.split == "test":
            raise ValueError("test labels are sealed and cannot enter training examples")
