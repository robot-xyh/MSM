"""Typed records shared by the independent experiment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

from dual_optical_online_benchmark.contracts import BenchmarkProtocol


NODE_FEATURE_NAMES = (
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

LEGACY_NODE_FEATURE_COUNT = 8
LEGACY_EDGE_FEATURE_COUNT = 12
FEATURE_CONTRACT_VERSION = "dual-optical-edge-gnn-features-v2"


@dataclass(frozen=True)
class CorruptionConfig:
    name: str
    miss_probability: float
    transient_false_alarms_per_half_sweep: int
    persistent_false_tracks_per_camera: int

    def __post_init__(self) -> None:
        if not 0.0 <= self.miss_probability < 1.0:
            raise ValueError("miss_probability must be in [0, 1)")
        if self.transient_false_alarms_per_half_sweep < 0:
            raise ValueError("transient false-alarm count cannot be negative")
        if self.persistent_false_tracks_per_camera < 0:
            raise ValueError("persistent false-track count cannot be negative")


CORRUPTION_LEVELS: Mapping[str, CorruptionConfig] = {
    "light": CorruptionConfig("light", 0.03, 1, 0),
    "medium": CorruptionConfig("medium", 0.07, 2, 1),
    "heavy": CorruptionConfig("heavy", 0.12, 4, 2),
}
CAUSAL_TRANSIENT_FALSE_ALARMS_PER_SECOND: Mapping[str, int] = {
    "light": 2,
    "medium": 4,
    "heavy": 8,
}

DEFAULT_SPLITS: Mapping[str, tuple[int, ...]] = {
    "train": tuple(range(20260820, 20260828)),
    "val": (20260828, 20260829),
    "test": (20260830, 20260831),
}

EXPANDED_FORMAL_TRAIN_SEEDS = DEFAULT_SPLITS["train"]
EXPANDED_FORMAL_VALIDATION_SEEDS = DEFAULT_SPLITS["val"]
LEGACY_FORMAL_TEST_SEEDS = DEFAULT_SPLITS["test"]
MINIMUM_EXPANDED_TEST_SEEDS = 20
VALIDATION_PROBABILITY_THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)

def benchmark_protocol_splits(
    protocol: BenchmarkProtocol | None = None,
) -> Mapping[str, tuple[int, ...]]:
    """Read formal seeds from the main-owned protocol instead of route constants."""

    protocol = protocol or BenchmarkProtocol()
    return {
        "train": tuple(int(seed) for seed in protocol.train_seeds),
        "val": tuple(int(seed) for seed in protocol.validation_seeds),
        "test": tuple(int(seed) for seed in protocol.test_seeds),
    }


CAUSAL_FORMAL_SPLITS: Mapping[str, tuple[int, ...]] = benchmark_protocol_splits()
CAUSAL_REVOLUTION_COUNT = 6
CAUSAL_SCAN_PERIOD_S = 2.0


@dataclass(frozen=True)
class CausalProtocolConfig:
    """Scenario contract declared and frozen by the main AirSim orchestrator."""

    scan_mode: str = "continuous_360_unidirectional"
    scan_period_s: float = CAUSAL_SCAN_PERIOD_S
    revolution_count: int = CAUSAL_REVOLUTION_COUNT
    maximum_target_axis_offset_deg: float = 30.0
    gimbal_attitude_error_rms_mrad: float = 0.5

    def __post_init__(self) -> None:
        if self.scan_mode != "continuous_360_unidirectional":
            raise ValueError("causal protocol requires continuous unidirectional 360-degree scan")
        if self.scan_period_s <= 0.0:
            raise ValueError("scan_period_s must be positive")
        if self.revolution_count != CAUSAL_REVOLUTION_COUNT:
            raise ValueError(f"causal protocol requires {CAUSAL_REVOLUTION_COUNT} revolutions")
        if not 0.0 <= self.maximum_target_axis_offset_deg <= 30.0:
            raise ValueError("maximum_target_axis_offset_deg must be in [0, 30]")
        if self.gimbal_attitude_error_rms_mrad != 0.5:
            raise ValueError("causal protocol fixes gimbal attitude RMS error at 0.5 mrad")


@dataclass(frozen=True)
class TrackSample:
    sweep_index: int
    timestamp: float
    direction_ned: tuple[float, float, float]
    detection_count: int = 1
    bbox_area_px2: float = 0.0
    confidence: float = 1.0
    direction_covariance_mrad2: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        direction = np.asarray(self.direction_ned, dtype=float)
        if direction.shape != (3,) or not np.all(np.isfinite(direction)):
            raise ValueError("direction_ned must contain three finite values")
        if np.linalg.norm(direction) <= 1e-12:
            raise ValueError("direction_ned cannot be zero")
        if self.direction_covariance_mrad2 is not None:
            covariance = np.asarray(self.direction_covariance_mrad2, dtype=float)
            if covariance.size not in {2, 4} or not np.all(np.isfinite(covariance)):
                raise ValueError("direction covariance must contain two or four finite values")
            diagonal = covariance if covariance.size == 2 else covariance.reshape(2, 2).diagonal()
            if np.any(diagonal < 0.0):
                raise ValueError("direction covariance diagonal cannot be negative")


@dataclass(frozen=True)
class AnonymousTrack:
    track_id: str
    camera_id: str
    samples: tuple[TrackSample, ...]
    source_kind: str = "measured"
    angular_velocity_deg_s: tuple[float, float] | None = None
    state_covariance: tuple[float, ...] | None = None
    recent_revolution_hits: tuple[bool, ...] = ()
    track_state: str = "legacy_v1"
    snapshot_contract_version: str = "v1"

    def __post_init__(self) -> None:
        if self.angular_velocity_deg_s is not None:
            velocity = np.asarray(self.angular_velocity_deg_s, dtype=float)
            if velocity.shape != (2,) or not np.all(np.isfinite(velocity)):
                raise ValueError("angular_velocity_deg_s must contain two finite values")
        if self.state_covariance is not None:
            covariance = np.asarray(self.state_covariance, dtype=float)
            if covariance.size not in {4, 16} or not np.all(np.isfinite(covariance)):
                raise ValueError("state_covariance must contain four or sixteen finite values")
            side = 2 if covariance.size == 4 else 4
            if np.any(covariance.reshape(side, side).diagonal() < 0.0):
                raise ValueError("state covariance diagonal cannot be negative")
        if len(self.recent_revolution_hits) > 3:
            raise ValueError("recent_revolution_hits may contain at most three entries")

    @property
    def sweep_count(self) -> int:
        return len({sample.sweep_index for sample in self.samples})

    @property
    def duration_s(self) -> float:
        if len(self.samples) < 2:
            return 0.0
        return float(self.samples[-1].timestamp - self.samples[0].timestamp)


@dataclass(frozen=True)
class OnlineEpisode:
    seed: int
    schema_version: str
    configured_target_count: int | None
    camera_ids: tuple[str, str]
    camera_positions_ned: Mapping[str, tuple[float, float, float]]
    focal_length_px: float
    tracks: Mapping[str, tuple[AnonymousTrack, ...]]
    source_hashes: Mapping[str, str] = field(default_factory=dict)
    snapshot_contract_version: str = "v1"
    geometry_candidate_pairs: tuple[tuple[str, str], ...] | None = None
    candidate_graph_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if len(self.camera_ids) != 2 or self.camera_ids[0] == self.camera_ids[1]:
            raise ValueError("exactly two distinct camera IDs are required")
        for camera_id in self.camera_ids:
            if camera_id not in self.camera_positions_ned:
                raise ValueError(f"missing camera position for {camera_id}")
        if self.geometry_candidate_pairs is not None:
            if len(self.geometry_candidate_pairs) != len(set(self.geometry_candidate_pairs)):
                raise ValueError("geometry candidate pairs contain duplicates")
        if self.configured_target_count is not None and self.configured_target_count <= 0:
            raise ValueError("configured_target_count must be positive")
        if self.candidate_graph_fingerprint is not None:
            fingerprint = self.candidate_graph_fingerprint
            if len(fingerprint) != 64 or any(
                character not in "0123456789abcdef" for character in fingerprint.lower()
            ):
                raise ValueError("candidate graph fingerprint must be a SHA-256 hex digest")


@dataclass(frozen=True)
class OfflineLabels:
    track_identity: Mapping[str, str | None]
    expected_identities: tuple[str, ...]
    source_hashes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CorruptionSummary:
    level: str
    corruption_seed: int
    dropped_sample_count: int
    retained_sample_count: int
    transient_false_track_count: int
    persistent_false_track_count: int


@dataclass(frozen=True)
class OnlineGraph:
    seed: int
    corruption_level: str
    camera_ids: tuple[str, str]
    track_ids_a: tuple[str, ...]
    track_ids_b: tuple[str, ...]
    node_features_a: np.ndarray
    node_features_b: np.ndarray
    edge_index: np.ndarray
    edge_features: np.ndarray
    geometry_cost: np.ndarray
    corruption_summary: CorruptionSummary

    def validate(self) -> None:
        valid_node_widths = {LEGACY_NODE_FEATURE_COUNT, len(NODE_FEATURE_NAMES)}
        valid_edge_widths = {LEGACY_EDGE_FEATURE_COUNT, len(EDGE_FEATURE_NAMES)}
        if (
            self.node_features_a.ndim != 2
            or self.node_features_a.shape[0] != len(self.track_ids_a)
            or self.node_features_a.shape[1] not in valid_node_widths
        ):
            raise ValueError("invalid A-node feature shape")
        if (
            self.node_features_b.ndim != 2
            or self.node_features_b.shape[0] != len(self.track_ids_b)
            or self.node_features_b.shape[1] != self.node_features_a.shape[1]
        ):
            raise ValueError("invalid B-node feature shape")
        if self.edge_index.ndim != 2 or self.edge_index.shape[0] != 2:
            raise ValueError("edge_index must have shape [2, E]")
        edge_count = self.edge_index.shape[1]
        if (
            self.edge_features.ndim != 2
            or self.edge_features.shape[0] != edge_count
            or self.edge_features.shape[1] not in valid_edge_widths
        ):
            raise ValueError("invalid edge feature shape")
        if self.geometry_cost.shape != (edge_count,):
            raise ValueError("invalid geometry cost shape")
        if edge_count:
            if int(np.max(self.edge_index[0])) >= len(self.track_ids_a):
                raise ValueError("A-node edge index out of range")
            if int(np.max(self.edge_index[1])) >= len(self.track_ids_b):
                raise ValueError("B-node edge index out of range")
        for array in (
            self.node_features_a,
            self.node_features_b,
            self.edge_features,
            self.geometry_cost,
        ):
            if not np.all(np.isfinite(array)):
                raise ValueError("graph arrays must be finite")


@dataclass(frozen=True)
class GraphLabels:
    edge_labels: np.ndarray
    identity_a: tuple[str | None, ...]
    identity_b: tuple[str | None, ...]
    expected_identities: tuple[str, ...]

    def validate(self, graph: OnlineGraph) -> None:
        if self.edge_labels.shape != (graph.edge_index.shape[1],):
            raise ValueError("edge label count does not match graph")
        if len(self.identity_a) != len(graph.track_ids_a):
            raise ValueError("A-node identity count does not match graph")
        if len(self.identity_b) != len(graph.track_ids_b):
            raise ValueError("B-node identity count does not match graph")
