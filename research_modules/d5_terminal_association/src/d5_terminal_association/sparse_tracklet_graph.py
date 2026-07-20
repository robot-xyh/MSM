"""Sparse geometry-first association graph for anonymous camera tracklets.

The graph is an advisory D5 association surface.  Nodes are camera-local
tracklets and may not carry evaluator truth or a global identity.  Existing
center-owned ``GlobalTrack`` objects are only used as projection hypotheses;
binding is performed after edge scoring by constrained clustering and a
one-to-one center-track assignment.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field, fields, is_dataclass
import math
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .models import CameraModel, GlobalTrack


NODE_FEATURE_NAMES = (
    "center_x_normalized",
    "center_y_normalized",
    "log_bbox_area_ratio",
    "log_bbox_aspect_ratio",
    "angular_velocity_x_rad_s",
    "angular_velocity_y_rad_s",
    "bbox_scale_rate_s",
    "confidence",
    "pixel_covariance_trace_normalized",
    "tracklet_age_s",
)

EDGE_FEATURE_NAMES = (
    "time_delta_s",
    "pixel_mahalanobis",
    "reprojection_error_px",
    "ray_closest_distance_m",
    "bbox_log_scale_delta",
    "bbox_scale_rate_delta_s",
    "angular_velocity_delta_rad_s",
    "baseline_m",
    "extrinsics_covariance_trace",
    "epipolar_error_px",
    "triangulation_angle_rad",
    "global_projection_mahalanobis",
    "confidence_product",
    "shared_global_track_count",
)

_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_entity_id",
        "truth_entity_ids",
        "ground_truth",
        "actor_id",
        "actor_name",
        "entity_id",
        "entity_name",
        "intruder_id",
        "intruder_name",
        "object_id",
        "object_name",
        "target_id",
        "target_name",
        "airsim_id",
        "global_track_id",
        "assigned_global_track_id",
        "offline_truth_label",
        "offline_truth_labels",
    }
)
_FORBIDDEN_ONLINE_TYPES = frozenset({"OfflineTruthLabel", "WorldSnapshot", "EntitySnapshot"})
_IDENTITY_TOKEN = re.compile(r"truth|actor|object", re.IGNORECASE)
_LOCAL_ID_KEYS = frozenset(
    {
        "detection_id",
        "local_detection_id",
        "local_track_id",
        "local_tracklet_id",
        "track_id",
        "tracklet_id",
    }
)
_TRUTH_LIKE_LOCAL_ID = re.compile(
    r"(?:^|[^a-z0-9])"
    r"(?:tgt|target(?:[\s_.-]*(?:drone|uav|uas|aircraft|vehicle))?|intruder)"
    r"[\s_.-]*\d+(?:$|[^a-z0-9])",
    re.IGNORECASE,
)
_EPS = 1.0e-9


def assert_anonymous_online_payload(payload: Any) -> None:
    """Reject evaluator identity recursively from a tracklet-side payload."""

    violations: list[str] = []

    def visit(value: Any, path: str) -> None:
        type_name = type(value).__name__
        if type_name in _FORBIDDEN_ONLINE_TYPES:
            violations.append(f"{path}<{type_name}>")
            return
        if is_dataclass(value) and not isinstance(value, type):
            for item in fields(value):
                key = _normalise_key(item.name)
                child_path = f"{path}.{item.name}"
                if _is_forbidden_online_key(key):
                    violations.append(child_path)
                elif _is_local_id_key(key) and is_truth_like_local_track_id(
                    getattr(value, item.name)
                ):
                    violations.append(child_path)
                else:
                    visit(getattr(value, item.name), child_path)
            return
        if isinstance(value, Mapping):
            for raw_key, item in value.items():
                key = _normalise_key(str(raw_key))
                child_path = f"{path}.{raw_key}"
                if _is_forbidden_online_key(key):
                    violations.append(child_path)
                elif _is_local_id_key(key) and is_truth_like_local_track_id(item):
                    violations.append(child_path)
                else:
                    visit(item, child_path)
            return
        if isinstance(value, (list, tuple, set, frozenset)):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
            return
        if hasattr(value, "__dict__") and not isinstance(value, type):
            visit(vars(value), path)

    visit(payload, "payload")
    if violations:
        joined = ", ".join(sorted(set(violations)))
        raise ValueError(f"anonymous online tracklet payload contains identity fields: {joined}")


@dataclass(frozen=True)
class CameraLocalTracklet:
    """Identity-free summary of one local track in one camera namespace."""

    resource_id: str
    camera_id: str
    local_track_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    center_px: np.ndarray
    covariance_px: np.ndarray
    bbox_xyxy: tuple[float, float, float, float] | None = None
    angular_velocity_rad_s: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=float))
    bbox_scale_rate_s: float = 0.0
    confidence: float = 1.0
    tracklet_start_timestamp: float | None = None
    source_observation_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    tracklet_key: str = field(default="", init=False)
    camera_key: str = field(default="", init=False)

    def __post_init__(self) -> None:
        resource_id = str(self.resource_id).strip()
        camera_id = str(self.camera_id).strip()
        local_track_id = str(self.local_track_id).strip()
        if not resource_id or not camera_id or not local_track_id:
            raise ValueError("resource_id, camera_id, and local_track_id must be non-empty")
        for name, value in (("resource_id", resource_id), ("camera_id", camera_id)):
            if is_truth_like_local_track_id(value):
                raise ValueError(f"{name} must be anonymous and camera-local")
        if is_truth_like_local_track_id(local_track_id):
            raise ValueError("local_track_id must be anonymous and camera-local")
        measurement_timestamp = _finite_float(self.measurement_timestamp, "measurement_timestamp")
        arrival_timestamp = _finite_float(self.arrival_timestamp, "arrival_timestamp")
        if arrival_timestamp + 1.0e-12 < measurement_timestamp:
            raise ValueError("arrival_timestamp must not precede measurement_timestamp")
        start_timestamp = (
            measurement_timestamp
            if self.tracklet_start_timestamp is None
            else _finite_float(self.tracklet_start_timestamp, "tracklet_start_timestamp")
        )
        if start_timestamp > measurement_timestamp + 1.0e-12:
            raise ValueError("tracklet_start_timestamp must not follow measurement_timestamp")
        center = _finite_vector(self.center_px, 2, "center_px")
        covariance = _positive_semidefinite_matrix(self.covariance_px, (2, 2), "covariance_px")
        angular_velocity = _finite_vector(
            self.angular_velocity_rad_s,
            2,
            "angular_velocity_rad_s",
        )
        bbox = _optional_bbox(self.bbox_xyxy)
        scale_rate = _finite_float(self.bbox_scale_rate_s, "bbox_scale_rate_s")
        confidence = float(np.clip(_finite_float(self.confidence, "confidence"), 0.0, 1.0))
        source_observation_id = (
            None
            if self.source_observation_id is None
            else str(self.source_observation_id).strip()
        )
        if self.source_observation_id is not None and not source_observation_id:
            raise ValueError("source_observation_id must be non-empty when present")
        if source_observation_id is not None and is_truth_like_local_track_id(
            source_observation_id
        ):
            raise ValueError("source_observation_id must be an anonymous measurement key")
        metadata = dict(self.metadata)
        assert_anonymous_online_payload(metadata)

        camera_key = f"{resource_id}/{camera_id}"
        object.__setattr__(self, "resource_id", resource_id)
        object.__setattr__(self, "camera_id", camera_id)
        object.__setattr__(self, "local_track_id", local_track_id)
        object.__setattr__(self, "measurement_timestamp", measurement_timestamp)
        object.__setattr__(self, "arrival_timestamp", arrival_timestamp)
        object.__setattr__(self, "tracklet_start_timestamp", start_timestamp)
        object.__setattr__(self, "center_px", _read_only(center))
        object.__setattr__(self, "covariance_px", _read_only(covariance))
        object.__setattr__(self, "angular_velocity_rad_s", _read_only(angular_velocity))
        object.__setattr__(self, "bbox_xyxy", bbox)
        object.__setattr__(self, "bbox_scale_rate_s", scale_rate)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "source_observation_id", source_observation_id)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))
        object.__setattr__(self, "camera_key", camera_key)
        object.__setattr__(self, "tracklet_key", f"{camera_key}:{local_track_id}")


@dataclass(frozen=True)
class TrackletCameraGeometry:
    """Time-stamped camera geometry and extrinsic covariance for graph gates."""

    resource_id: str
    camera_id: str
    camera: CameraModel
    measurement_timestamp: float
    position_covariance_ned: np.ndarray = field(default_factory=lambda: np.zeros((3, 3), dtype=float))
    attitude_covariance_rad2: np.ndarray = field(default_factory=lambda: np.zeros((3, 3), dtype=float))
    camera_key: str = field(default="", init=False)

    def __post_init__(self) -> None:
        resource_id = str(self.resource_id).strip()
        camera_id = str(self.camera_id).strip()
        if not resource_id or not camera_id:
            raise ValueError("resource_id and camera_id must be non-empty")
        if not isinstance(self.camera, CameraModel):
            raise TypeError("camera must be a CameraModel")
        timestamp = _finite_float(self.measurement_timestamp, "measurement_timestamp")
        position_covariance = _positive_semidefinite_matrix(
            self.position_covariance_ned,
            (3, 3),
            "position_covariance_ned",
        )
        attitude_covariance = _positive_semidefinite_matrix(
            self.attitude_covariance_rad2,
            (3, 3),
            "attitude_covariance_rad2",
        )
        object.__setattr__(self, "resource_id", resource_id)
        object.__setattr__(self, "camera_id", camera_id)
        object.__setattr__(self, "measurement_timestamp", timestamp)
        object.__setattr__(self, "position_covariance_ned", _read_only(position_covariance))
        object.__setattr__(self, "attitude_covariance_rad2", _read_only(attitude_covariance))
        object.__setattr__(self, "camera_key", f"{resource_id}/{camera_id}")

    @property
    def camera_center_ned(self) -> np.ndarray:
        return -self.camera.R.T @ self.camera.t

    @property
    def extrinsics_covariance_trace(self) -> float:
        return float(np.trace(self.position_covariance_ned) + np.trace(self.attitude_covariance_rad2))


@dataclass(frozen=True)
class SparseTrackletGraphConfig:
    """Geometry gates and deterministic degree cap for sparse candidates."""

    max_time_delta_s: float = 0.35
    max_arrival_time_delta_s: float = 1.0
    max_camera_geometry_age_s: float = 0.35
    fov_margin_px: float = 2.0
    max_epipolar_error_px: float = 8.0
    epipolar_covariance_sigma: float = 2.0
    max_ray_closest_distance_m: float = 25.0
    ray_covariance_sigma: float = 2.0
    min_triangulation_angle_deg: float = 0.2
    max_reprojection_error_px: float = 10.0
    reprojection_covariance_sigma: float = 2.0
    max_pixel_mahalanobis: float = 6.0
    max_global_projection_mahalanobis: float = 6.0
    global_process_noise_m2_s4: float = 1.0
    max_tracklet_covariance_trace_px2: float = 10_000.0
    max_extrinsics_covariance_trace: float = 1_000.0
    camera_overlap_near_m: float = 1.0
    camera_overlap_far_m: float = 3_000.0
    camera_index_cell_size_m: float = 1_000.0
    camera_pair_time_window_s: float = 0.35
    camera_pair_budget: int = 4_096
    camera_index_max_search_radius_cells: int = 8
    max_tracklet_candidate_edges_per_node: int = 24
    max_neighbors_per_node: int = 8
    covariance_regularization: float = 1.0e-6

    def __post_init__(self) -> None:
        positive_names = (
            "max_time_delta_s",
            "max_arrival_time_delta_s",
            "max_camera_geometry_age_s",
            "max_epipolar_error_px",
            "max_ray_closest_distance_m",
            "min_triangulation_angle_deg",
            "max_reprojection_error_px",
            "max_pixel_mahalanobis",
            "max_global_projection_mahalanobis",
            "max_tracklet_covariance_trace_px2",
            "max_extrinsics_covariance_trace",
            "camera_overlap_near_m",
            "camera_overlap_far_m",
            "camera_index_cell_size_m",
            "camera_pair_time_window_s",
            "covariance_regularization",
        )
        for name in positive_names:
            if not np.isfinite(getattr(self, name)) or float(getattr(self, name)) <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        non_negative_names = (
            "fov_margin_px",
            "epipolar_covariance_sigma",
            "ray_covariance_sigma",
            "reprojection_covariance_sigma",
            "global_process_noise_m2_s4",
        )
        for name in non_negative_names:
            if not np.isfinite(getattr(self, name)) or float(getattr(self, name)) < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.camera_overlap_far_m <= self.camera_overlap_near_m:
            raise ValueError("camera_overlap_far_m must exceed camera_overlap_near_m")
        if int(self.camera_pair_budget) < 0:
            raise ValueError("camera_pair_budget must be non-negative")
        if int(self.camera_index_max_search_radius_cells) <= 0:
            raise ValueError("camera_index_max_search_radius_cells must be positive")
        if int(self.max_tracklet_candidate_edges_per_node) <= 0:
            raise ValueError("max_tracklet_candidate_edges_per_node must be positive")
        if int(self.max_neighbors_per_node) <= 0:
            raise ValueError("max_neighbors_per_node must be positive")
        object.__setattr__(self, "camera_pair_budget", int(self.camera_pair_budget))
        object.__setattr__(
            self,
            "camera_index_max_search_radius_cells",
            int(self.camera_index_max_search_radius_cells),
        )
        object.__setattr__(
            self,
            "max_tracklet_candidate_edges_per_node",
            int(self.max_tracklet_candidate_edges_per_node),
        )
        object.__setattr__(self, "max_neighbors_per_node", int(self.max_neighbors_per_node))


@dataclass(frozen=True)
class CameraOverlapIndex:
    """Bounded camera pairs selected by time and spatial frustum overlap.

    ``all_possible_camera_pairs`` is counted arithmetically.  It is never
    materialised as a complete pair list.  Pairs omitted by the configured
    budget are deliberately absent, so downstream association leaves their
    tracklets unbound instead of inferring an identity without evidence.
    """

    camera_pairs: tuple[tuple[str, str], ...]
    candidate_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        pairs = tuple((str(left), str(right)) for left, right in self.camera_pairs)
        if any(not left or not right or left >= right for left, right in pairs):
            raise ValueError("camera overlap pairs must be canonical non-empty keys")
        if len(pairs) != len(set(pairs)):
            raise ValueError("camera overlap pairs must be unique")
        object.__setattr__(self, "camera_pairs", pairs)
        object.__setattr__(
            self,
            "candidate_counts",
            MappingProxyType(
                {str(key): int(value) for key, value in self.candidate_counts.items()}
            ),
        )


@dataclass(frozen=True)
class _CameraCoverageDescriptor:
    camera_key: str
    measurement_timestamp: float
    center_ned: np.ndarray
    coverage_anchor_ned: np.ndarray
    aabb_min_ned: np.ndarray
    aabb_max_ned: np.ndarray
    bucket: tuple[int, int, int]
    search_radius_cells: int
    radius_clipped: bool


@dataclass(frozen=True)
class SparseCandidateEdge:
    """One undirected sparse edge with truth-free geometric evidence."""

    source_index: int
    target_index: int
    source_tracklet_key: str
    target_tracklet_key: str
    shared_global_track_ids: tuple[str, ...]
    feature_values: tuple[float, ...]
    gate_score: float

    def __post_init__(self) -> None:
        if self.source_index < 0 or self.target_index <= self.source_index:
            raise ValueError("candidate edges must be canonical undirected pairs")
        if len(self.feature_values) != len(EDGE_FEATURE_NAMES):
            raise ValueError("candidate edge feature dimension mismatch")
        values = np.asarray(self.feature_values, dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError("candidate edge features must be finite")
        object.__setattr__(
            self,
            "shared_global_track_ids",
            tuple(dict.fromkeys(str(value) for value in self.shared_global_track_ids)),
        )
        object.__setattr__(self, "gate_score", _finite_float(self.gate_score, "gate_score"))

    def feature_dict(self) -> dict[str, float]:
        return dict(zip(EDGE_FEATURE_NAMES, self.feature_values, strict=True))


@dataclass(frozen=True)
class SparseTrackletGraph:
    """Immutable sparse graph consumed by native PyTorch edge scoring."""

    nodes: tuple[CameraLocalTracklet, ...]
    node_features: np.ndarray
    edge_index: np.ndarray
    edge_features: np.ndarray
    edges: tuple[SparseCandidateEdge, ...]
    candidate_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        nodes = tuple(self.nodes)
        edges = tuple(self.edges)
        node_features = np.asarray(self.node_features, dtype=np.float32)
        edge_index = np.asarray(self.edge_index, dtype=np.int64)
        edge_features = np.asarray(self.edge_features, dtype=np.float32)
        if node_features.shape != (len(nodes), len(NODE_FEATURE_NAMES)):
            raise ValueError("node_features shape does not match nodes")
        if edge_index.shape != (2, len(edges)):
            raise ValueError("edge_index must have shape (2, edge_count)")
        if edge_features.shape != (len(edges), len(EDGE_FEATURE_NAMES)):
            raise ValueError("edge_features shape does not match edges")
        if not np.all(np.isfinite(node_features)) or not np.all(np.isfinite(edge_features)):
            raise ValueError("graph features must be finite")
        if edge_index.size and (edge_index.min() < 0 or edge_index.max() >= len(nodes)):
            raise ValueError("edge_index references an unknown node")
        keys = tuple(node.tracklet_key for node in nodes)
        if len(keys) != len(set(keys)):
            raise ValueError("tracklet keys must be unique within a graph")
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "node_features", _read_only(node_features.copy()))
        object.__setattr__(self, "edge_index", _read_only(edge_index.copy()))
        object.__setattr__(self, "edge_features", _read_only(edge_features.copy()))
        object.__setattr__(
            self,
            "candidate_counts",
            MappingProxyType({str(key): int(value) for key, value in self.candidate_counts.items()}),
        )

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def possible_undirected_edge_count(self) -> int:
        return self.node_count * max(0, self.node_count - 1) // 2

    @property
    def density(self) -> float:
        possible = self.possible_undirected_edge_count
        return float(self.edge_count / possible) if possible else 0.0


@dataclass(frozen=True)
class TrackletCluster:
    """Anonymous constrained component; this is not a global track."""

    cluster_key: str
    node_indices: tuple[int, ...]
    tracklet_keys: tuple[str, ...]
    camera_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.cluster_key or not self.node_indices:
            raise ValueError("cluster_key and node_indices must be non-empty")
        if len(self.camera_keys) != len(set(self.camera_keys)):
            raise ValueError("a cluster may contain at most one tracklet from each camera")


@dataclass(frozen=True)
class CenterTrackBindingDecision:
    """Read-only reference from an anonymous cluster to a center-owned track."""

    cluster_key: str
    global_track_id: str | None
    cost: float | None
    decision_state: str
    supporting_tracklet_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.decision_state not in {"bound", "unbound", "ambiguous"}:
            raise ValueError("invalid center binding decision_state")
        if self.global_track_id is not None and not str(self.global_track_id):
            raise ValueError("global_track_id must be non-empty when present")
        if self.cost is not None:
            object.__setattr__(self, "cost", _finite_float(self.cost, "cost"))


def build_camera_overlap_index(
    camera_geometries: Iterable[TrackletCameraGeometry],
    *,
    camera_keys: Iterable[str] | None = None,
    config: SparseTrackletGraphConfig | None = None,
) -> CameraOverlapIndex:
    """Select a bounded set of camera pairs from time-stamped frustum buckets.

    Each camera is assigned to one deterministic bucket at the midpoint of its
    configured viewing range.  Its complete truncated-frustum AABB determines
    how far neighbouring buckets are queried.  Only inspected pairs whose
    timestamps and AABBs overlap are returned.  The inspection budget bounds a
    dense same-bucket case without constructing ``C choose 2`` pairs.
    """

    cfg = config or SparseTrackletGraphConfig()
    cameras = tuple(camera_geometries)
    camera_by_key = {camera.camera_key: camera for camera in cameras}
    if len(camera_by_key) != len(cameras):
        raise ValueError("camera geometry keys must be unique")
    selected_keys = (
        tuple(sorted(camera_by_key))
        if camera_keys is None
        else tuple(sorted(dict.fromkeys(str(key) for key in camera_keys)))
    )
    unknown = tuple(key for key in selected_keys if key not in camera_by_key)
    if unknown:
        raise ValueError(f"camera overlap index references unknown cameras: {unknown}")
    descriptors = tuple(
        _camera_coverage_descriptor(camera_by_key[key], cfg) for key in selected_keys
    )
    descriptor_by_key = {item.camera_key: item for item in descriptors}
    buckets: dict[tuple[int, int, int], list[str]] = defaultdict(list)
    bucket_radius: dict[tuple[int, int, int], int] = defaultdict(int)
    for descriptor in descriptors:
        buckets[descriptor.bucket].append(descriptor.camera_key)
        bucket_radius[descriptor.bucket] = max(
            bucket_radius[descriptor.bucket],
            descriptor.search_radius_cells,
        )
    for values in buckets.values():
        values.sort()

    occupied = frozenset(buckets)
    max_radius = max(bucket_radius.values(), default=0)
    bucket_pairs: set[
        tuple[tuple[int, int, int], tuple[int, int, int]]
    ] = set()
    for left_bucket in sorted(occupied):
        search_radius = min(
            cfg.camera_index_max_search_radius_cells,
            bucket_radius[left_bucket] + max_radius,
        )
        for north_offset in range(-search_radius, search_radius + 1):
            for east_offset in range(-search_radius, search_radius + 1):
                for down_offset in range(-search_radius, search_radius + 1):
                    right_bucket = (
                        left_bucket[0] + north_offset,
                        left_bucket[1] + east_offset,
                        left_bucket[2] + down_offset,
                    )
                    if right_bucket not in occupied or right_bucket < left_bucket:
                        continue
                    bucket_pairs.add((left_bucket, right_bucket))

    ordered_bucket_pairs = sorted(
        bucket_pairs,
        key=lambda item: (
            max(abs(item[0][axis] - item[1][axis]) for axis in range(3)),
            sum(abs(item[0][axis] - item[1][axis]) for axis in range(3)),
            item[0],
            item[1],
        ),
    )
    indexed_pair_space = sum(
        (
            len(buckets[left]) * max(0, len(buckets[left]) - 1) // 2
            if left == right
            else len(buckets[left]) * len(buckets[right])
        )
        for left, right in ordered_bucket_pairs
    )
    budget = cfg.camera_pair_budget
    inspected = 0
    time_rejected = 0
    overlap_rejected = 0
    retained: list[tuple[str, str]] = []
    stop = False

    for left_bucket, right_bucket in ordered_bucket_pairs:
        left_keys = buckets[left_bucket]
        right_keys = buckets[right_bucket]
        if left_bucket == right_bucket:
            pair_iter = (
                (left_keys[left_index], left_keys[right_index])
                for separation in range(1, len(left_keys))
                for left_index in range(0, len(left_keys) - separation)
                for right_index in (left_index + separation,)
            )
        else:
            pair_iter = (
                tuple(sorted((left_key, right_key)))
                for diagonal in range(len(left_keys) + len(right_keys) - 1)
                for left_index in range(len(left_keys))
                for right_index in (diagonal - left_index,)
                if 0 <= right_index < len(right_keys)
                for left_key in (left_keys[left_index],)
                for right_key in (right_keys[right_index],)
            )
        for left_key, right_key in pair_iter:
            if inspected >= budget:
                stop = True
                break
            inspected += 1
            left = descriptor_by_key[left_key]
            right = descriptor_by_key[right_key]
            if (
                abs(left.measurement_timestamp - right.measurement_timestamp)
                > cfg.camera_pair_time_window_s
            ):
                time_rejected += 1
                continue
            if not _aabb_intersects(
                left.aabb_min_ned,
                left.aabb_max_ned,
                right.aabb_min_ned,
                right.aabb_max_ned,
            ):
                overlap_rejected += 1
                continue
            retained.append((left_key, right_key))
        if stop:
            break

    all_possible = len(descriptors) * max(0, len(descriptors) - 1) // 2
    budget_dropped = max(0, indexed_pair_space - inspected)
    counts = {
        "all_possible_camera_pairs": all_possible,
        "camera_index_bucket_count": len(buckets),
        "camera_index_bucket_pair_count": len(ordered_bucket_pairs),
        "camera_index_pair_space": indexed_pair_space,
        "camera_index_rejected_pairs": max(0, all_possible - indexed_pair_space),
        "camera_pair_budget": budget,
        "camera_pairs_inspected": inspected,
        "camera_pair_budget_dropped": budget_dropped,
        "camera_pair_budget_exhausted": int(budget_dropped > 0),
        "camera_time_rejected_pairs": time_rejected,
        "camera_overlap_rejected_pairs": overlap_rejected,
        "indexed_camera_pairs": len(retained),
        "camera_index_radius_clipped_count": sum(
            int(item.radius_clipped) for item in descriptors
        ),
        "camera_index_max_bucket_population": max(
            (len(values) for values in buckets.values()),
            default=0,
        ),
    }
    return CameraOverlapIndex(
        camera_pairs=tuple(sorted(retained)),
        candidate_counts=counts,
    )


def _camera_coverage_descriptor(
    geometry: TrackletCameraGeometry,
    config: SparseTrackletGraphConfig,
) -> _CameraCoverageDescriptor:
    camera = geometry.camera
    center = geometry.camera_center_ned
    width, height = camera.image_size
    inverse_intrinsics = np.linalg.inv(camera.K)
    corners_world: list[np.ndarray] = []
    for depth in (config.camera_overlap_near_m, config.camera_overlap_far_m):
        for horizontal in (0.0, float(width)):
            for vertical in (0.0, float(height)):
                direction_camera = inverse_intrinsics @ np.array(
                    [horizontal, vertical, 1.0],
                    dtype=float,
                )
                if direction_camera[2] <= _EPS:
                    raise ValueError("camera intrinsics produce a non-forward frustum corner")
                point_camera = direction_camera * (depth / direction_camera[2])
                corners_world.append(center + camera.R.T @ point_camera)
    corners = np.vstack(corners_world)
    position_sigma = 3.0 * np.sqrt(
        np.maximum(0.0, np.diag(geometry.position_covariance_ned))
    )
    aabb_min = np.min(corners, axis=0) - position_sigma
    aabb_max = np.max(corners, axis=0) + position_sigma
    midpoint_depth = 0.5 * (
        config.camera_overlap_near_m + config.camera_overlap_far_m
    )
    optical_axis_ned = camera.R.T @ np.array([0.0, 0.0, 1.0], dtype=float)
    optical_axis_ned /= max(float(np.linalg.norm(optical_axis_ned)), _EPS)
    anchor = center + midpoint_depth * optical_axis_ned
    cell_size = config.camera_index_cell_size_m
    bucket_array = np.floor(anchor / cell_size).astype(int)
    required_radius = int(
        math.ceil(
            max(
                float(np.max(np.abs(aabb_min - anchor))),
                float(np.max(np.abs(aabb_max - anchor))),
            )
            / cell_size
        )
    ) + 1
    clipped_radius = min(
        required_radius,
        config.camera_index_max_search_radius_cells,
    )
    return _CameraCoverageDescriptor(
        camera_key=geometry.camera_key,
        measurement_timestamp=geometry.measurement_timestamp,
        center_ned=_read_only(center.copy()),
        coverage_anchor_ned=_read_only(anchor.copy()),
        aabb_min_ned=_read_only(aabb_min.copy()),
        aabb_max_ned=_read_only(aabb_max.copy()),
        bucket=tuple(int(value) for value in bucket_array),
        search_radius_cells=clipped_radius,
        radius_clipped=(clipped_radius < required_radius),
    )


def _aabb_intersects(
    left_min: np.ndarray,
    left_max: np.ndarray,
    right_min: np.ndarray,
    right_max: np.ndarray,
) -> bool:
    return bool(np.all(left_max >= right_min) and np.all(right_max >= left_min))


def _indexed_tracklet_candidate_pairs(
    nodes: Sequence[CameraLocalTracklet],
    nodes_by_camera: Mapping[str, Sequence[int]],
    camera_pairs: Sequence[tuple[str, str]],
    support_by_node: Sequence[Mapping[int, float]],
    *,
    center_tracks_present: bool,
    config: SparseTrackletGraphConfig,
) -> tuple[tuple[tuple[int, int], ...], dict[str, int]]:
    """Generate bounded deterministic tracklet pairs before expensive geometry."""

    per_node_cap = config.max_tracklet_candidate_edges_per_node
    probe_limit = max(per_node_cap, 2 * per_node_cap)
    candidate_priority: dict[tuple[int, int], tuple[Any, ...]] = {}
    selected_pair_space = 0
    time_rejected = 0
    source_cap_dropped = 0
    probe_dropped = 0

    for left_camera_key, right_camera_key in camera_pairs:
        left_indices = tuple(nodes_by_camera.get(left_camera_key, ()))
        right_indices = tuple(nodes_by_camera.get(right_camera_key, ()))
        selected_pair_space += len(left_indices) * len(right_indices)
        if not left_indices or not right_indices:
            continue
        right_by_support: dict[int, list[tuple[float, float, str, int]]] = defaultdict(list)
        if center_tracks_present:
            for right_index in right_indices:
                right = nodes[right_index]
                for track_index, distance in support_by_node[right_index].items():
                    right_by_support[int(track_index)].append(
                        (
                            float(distance),
                            right.measurement_timestamp,
                            right.tracklet_key,
                            right_index,
                        )
                    )
            for values in right_by_support.values():
                values.sort()
        else:
            right_time_order = tuple(
                sorted(
                    right_indices,
                    key=lambda index: (
                        nodes[index].measurement_timestamp,
                        nodes[index].arrival_timestamp,
                        nodes[index].tracklet_key,
                    ),
                )
            )
            right_time_values = tuple(
                nodes[index].measurement_timestamp for index in right_time_order
            )

        for left_index in left_indices:
            left = nodes[left_index]
            proposed_right: set[int] = set()
            if center_tracks_present:
                left_support = sorted(
                    support_by_node[left_index].items(),
                    key=lambda item: (float(item[1]), int(item[0])),
                )[:per_node_cap]
                for track_index, _ in left_support:
                    options = right_by_support.get(int(track_index), ())
                    probe_dropped += max(0, len(options) - probe_limit)
                    proposed_right.update(item[3] for item in options[:probe_limit])
            else:
                proposed_right.update(
                    _nearest_time_tracklets(
                        left,
                        right_time_order,
                        right_time_values,
                        nodes,
                        max_items=probe_limit,
                    )
                )

            ranked: list[tuple[tuple[Any, ...], int]] = []
            for right_index in proposed_right:
                right = nodes[right_index]
                measurement_delta = abs(
                    left.measurement_timestamp - right.measurement_timestamp
                )
                arrival_delta = abs(left.arrival_timestamp - right.arrival_timestamp)
                if (
                    measurement_delta > config.max_time_delta_s
                    or arrival_delta > config.max_arrival_time_delta_s
                ):
                    time_rejected += 1
                    continue
                shared_support = set(support_by_node[left_index]).intersection(
                    support_by_node[right_index]
                )
                if center_tracks_present and not shared_support:
                    continue
                support_cost = (
                    min(
                        support_by_node[left_index][track_index]
                        + support_by_node[right_index][track_index]
                        for track_index in shared_support
                    )
                    if shared_support
                    else 0.0
                )
                priority = (
                    -len(shared_support),
                    float(support_cost),
                    measurement_delta,
                    arrival_delta,
                    -(left.confidence * right.confidence),
                    left.tracklet_key,
                    right.tracklet_key,
                )
                ranked.append((priority, right_index))
            ranked.sort()
            source_cap_dropped += max(0, len(ranked) - per_node_cap)
            for priority, right_index in ranked[:per_node_cap]:
                source_index, target_index = sorted((left_index, right_index))
                pair = (source_index, target_index)
                previous = candidate_priority.get(pair)
                if previous is None or priority < previous:
                    candidate_priority[pair] = priority

    degrees = np.zeros(len(nodes), dtype=np.int64)
    retained: list[tuple[int, int]] = []
    degree_cap_dropped = 0
    ordered = sorted(
        candidate_priority.items(),
        key=lambda item: (*item[1], item[0]),
    )
    for (source_index, target_index), _ in ordered:
        if (
            degrees[source_index] >= per_node_cap
            or degrees[target_index] >= per_node_cap
        ):
            degree_cap_dropped += 1
            continue
        degrees[source_index] += 1
        degrees[target_index] += 1
        retained.append((source_index, target_index))

    retained.sort()
    counts = {
        "selected_camera_tracklet_pair_space": selected_pair_space,
        "tracklet_index_time_rejected": time_rejected,
        "tracklet_probe_budget_dropped": probe_dropped,
        "tracklet_source_cap_dropped": source_cap_dropped,
        "tracklet_degree_cap_dropped": degree_cap_dropped,
        "tracklet_candidate_budget_dropped": (
            probe_dropped + source_cap_dropped + degree_cap_dropped
        ),
        "candidate_tracklet_edges_before_degree_cap": len(candidate_priority),
        "candidate_tracklet_edges": len(retained),
        "max_tracklet_candidate_edges_per_node": per_node_cap,
    }
    return tuple(retained), counts


def _nearest_time_tracklets(
    source: CameraLocalTracklet,
    ordered_indices: Sequence[int],
    ordered_timestamps: Sequence[float],
    nodes: Sequence[CameraLocalTracklet],
    *,
    max_items: int,
) -> tuple[int, ...]:
    """Return a bounded timestamp-nearest prefix without a Cartesian product."""

    if not ordered_indices or max_items <= 0:
        return ()
    insertion = bisect_left(ordered_timestamps, source.measurement_timestamp)
    left = insertion - 1
    right = insertion
    output: list[int] = []
    while len(output) < max_items and (left >= 0 or right < len(ordered_indices)):
        left_key = (
            abs(
                nodes[ordered_indices[left]].measurement_timestamp
                - source.measurement_timestamp
            ),
            nodes[ordered_indices[left]].tracklet_key,
        ) if left >= 0 else (math.inf, "")
        right_key = (
            abs(
                nodes[ordered_indices[right]].measurement_timestamp
                - source.measurement_timestamp
            ),
            nodes[ordered_indices[right]].tracklet_key,
        ) if right < len(ordered_indices) else (math.inf, "")
        if left_key <= right_key:
            output.append(ordered_indices[left])
            left -= 1
        else:
            output.append(ordered_indices[right])
            right += 1
    return tuple(output)


def build_sparse_tracklet_graph(
    tracklets: Iterable[CameraLocalTracklet],
    camera_geometries: Iterable[TrackletCameraGeometry],
    *,
    center_tracks: Iterable[GlobalTrack] = (),
    config: SparseTrackletGraphConfig | None = None,
) -> SparseTrackletGraph:
    """Build sparse cross-camera candidates without using evaluator identity."""

    cfg = config or SparseTrackletGraphConfig()
    nodes = tuple(sorted(tracklets, key=lambda item: item.tracklet_key))
    cameras = tuple(camera_geometries)
    camera_by_key = {camera.camera_key: camera for camera in cameras}
    if len(camera_by_key) != len(cameras):
        raise ValueError("camera geometry keys must be unique")
    missing_cameras = sorted({node.camera_key for node in nodes if node.camera_key not in camera_by_key})
    if missing_cameras:
        raise ValueError(f"missing camera geometry for: {missing_cameras}")
    if len({node.tracklet_key for node in nodes}) != len(nodes):
        raise ValueError("tracklet keys must be unique")
    tracks = tuple(center_tracks)
    if len({track.global_track_id for track in tracks}) != len(tracks):
        raise ValueError("center global_track_id values must be unique")

    node_features = np.vstack(
        [_node_feature_vector(node, camera_by_key[node.camera_key]) for node in nodes]
    ) if nodes else np.empty((0, len(NODE_FEATURE_NAMES)), dtype=np.float32)
    projection_distances = _center_projection_distance_matrix(nodes, camera_by_key, tracks, cfg)
    support_by_node = _projection_support_by_node(projection_distances, tracks, cfg)
    fov_valid = np.array(
        [
            _center_in_fov(node.center_px, camera_by_key[node.camera_key].camera, cfg.fov_margin_px)
            and abs(
                node.measurement_timestamp
                - camera_by_key[node.camera_key].measurement_timestamp
            )
            <= cfg.max_camera_geometry_age_s
            for node in nodes
        ],
        dtype=bool,
    )
    covariance_valid = np.array(
        [float(np.trace(node.covariance_px)) <= cfg.max_tracklet_covariance_trace_px2 for node in nodes],
        dtype=bool,
    )

    nodes_by_camera: dict[str, list[int]] = defaultdict(list)
    for index, node in enumerate(nodes):
        nodes_by_camera[node.camera_key].append(index)
    possible_tracklet_pairs = (
        len(nodes) * len(nodes)
        - sum(len(indices) * len(indices) for indices in nodes_by_camera.values())
    ) // 2
    camera_overlap = build_camera_overlap_index(
        cameras,
        camera_keys=nodes_by_camera,
        config=cfg,
    )
    tracklet_pairs, tracklet_index_counts = _indexed_tracklet_candidate_pairs(
        nodes,
        nodes_by_camera,
        camera_overlap.camera_pairs,
        support_by_node,
        center_tracks_present=bool(tracks),
        config=cfg,
    )

    counts: dict[str, int] = {
        # Kept for compatibility: this is the arithmetic all-tracklet pair
        # space, not a materialised Cartesian product.
        "possible_cross_camera_pairs": int(possible_tracklet_pairs),
        "time_gate_pass": 0,
        "fov_gate_pass": 0,
        "epipolar_gate_pass": 0,
        "ray_gate_pass": 0,
        "reprojection_gate_pass": 0,
        "covariance_gate_pass": 0,
        "global_projection_gate_pass": 0,
        "pre_cap_edges": 0,
        "retained_edges": 0,
        "rejected_tracklet_time": 0,
        "rejected_tracklet_fov": 0,
        "rejected_epipolar": 0,
        "rejected_ray_geometry": 0,
        "rejected_ray_gate": 0,
        "rejected_reprojection_geometry": 0,
        "rejected_reprojection_gate": 0,
        "rejected_covariance": 0,
        "rejected_pixel_mahalanobis": 0,
        "rejected_global_projection": 0,
        "rejected_final_degree_cap": 0,
    }
    counts.update(camera_overlap.candidate_counts)
    counts.update(tracklet_index_counts)
    candidate_edges: list[SparseCandidateEdge] = []
    fundamental_by_camera_pair: dict[tuple[str, str], np.ndarray] = {}

    for source_index, target_index in tracklet_pairs:
            source = nodes[source_index]
            target = nodes[target_index]
            source_camera = camera_by_key[source.camera_key]
            target_camera = camera_by_key[target.camera_key]
            if (
                abs(source.measurement_timestamp - target.measurement_timestamp)
                > cfg.max_time_delta_s
                or abs(source.arrival_timestamp - target.arrival_timestamp)
                > cfg.max_arrival_time_delta_s
            ):
                counts["rejected_tracklet_time"] += 1
                continue
            counts["time_gate_pass"] += 1
            if not fov_valid[source_index] or not fov_valid[target_index]:
                counts["rejected_tracklet_fov"] += 1
                continue
            counts["fov_gate_pass"] += 1

            camera_pair = tuple(sorted((source.camera_key, target.camera_key)))
            fundamental = fundamental_by_camera_pair.get(camera_pair)
            if fundamental is None:
                fundamental = _fundamental_matrix(
                    camera_by_key[camera_pair[0]].camera,
                    camera_by_key[camera_pair[1]].camera,
                )
                fundamental_by_camera_pair[camera_pair] = fundamental
            pair_epipolar_error = _epipolar_error_pair(
                source.center_px,
                target.center_px,
                fundamental,
                source_is_left=(source.camera_key == camera_pair[0]),
            )
            epipolar_limit = cfg.max_epipolar_error_px + cfg.epipolar_covariance_sigma * math.sqrt(
                max(
                    0.0,
                    float(np.trace(source.covariance_px) + np.trace(target.covariance_px)),
                )
            )
            if pair_epipolar_error > epipolar_limit:
                counts["rejected_epipolar"] += 1
                continue
            counts["epipolar_gate_pass"] += 1

            ray_geometry = _ray_pair_geometry(source, target, source_camera, target_camera)
            if ray_geometry is None:
                counts["rejected_ray_geometry"] += 1
                continue
            ray_distance, midpoint, baseline, angle = ray_geometry
            ray_limit = cfg.max_ray_closest_distance_m + cfg.ray_covariance_sigma * math.sqrt(
                max(
                    0.0,
                    float(
                        np.trace(source_camera.position_covariance_ned)
                        + np.trace(target_camera.position_covariance_ned)
                    ),
                )
            )
            if angle < math.radians(cfg.min_triangulation_angle_deg) or ray_distance > ray_limit:
                counts["rejected_ray_gate"] += 1
                continue
            counts["ray_gate_pass"] += 1

            source_reprojection = _project_world_point(midpoint, source_camera.camera)
            target_reprojection = _project_world_point(midpoint, target_camera.camera)
            if source_reprojection is None or target_reprojection is None:
                counts["rejected_reprojection_geometry"] += 1
                continue
            source_residual = source.center_px - source_reprojection
            target_residual = target.center_px - target_reprojection
            reprojection_error = math.sqrt(
                0.5
                * (
                    float(source_residual @ source_residual)
                    + float(target_residual @ target_residual)
                )
            )
            reprojection_limit = cfg.max_reprojection_error_px + cfg.reprojection_covariance_sigma * math.sqrt(
                max(0.0, float(np.trace(source.covariance_px) + np.trace(target.covariance_px)))
            )
            if reprojection_error > reprojection_limit:
                counts["rejected_reprojection_gate"] += 1
                continue
            counts["reprojection_gate_pass"] += 1

            if (
                not covariance_valid[source_index]
                or not covariance_valid[target_index]
                or source_camera.extrinsics_covariance_trace
                > cfg.max_extrinsics_covariance_trace
                or target_camera.extrinsics_covariance_trace
                > cfg.max_extrinsics_covariance_trace
            ):
                counts["rejected_covariance"] += 1
                continue
            pixel_mahalanobis = math.sqrt(
                max(
                    0.0,
                    0.5
                    * (
                        _mahalanobis_squared(source_residual, source.covariance_px, cfg.covariance_regularization)
                        + _mahalanobis_squared(target_residual, target.covariance_px, cfg.covariance_regularization)
                    ),
                )
            )
            if not np.isfinite(pixel_mahalanobis) or pixel_mahalanobis > cfg.max_pixel_mahalanobis:
                counts["rejected_pixel_mahalanobis"] += 1
                continue
            counts["covariance_gate_pass"] += 1

            shared_track_indices = sorted(
                set(support_by_node[source_index]).intersection(support_by_node[target_index])
            )
            if tracks and not shared_track_indices:
                counts["rejected_global_projection"] += 1
                continue
            counts["global_projection_gate_pass"] += 1
            if shared_track_indices:
                global_mahalanobis = min(
                    math.sqrt(
                        0.5
                        * (
                            projection_distances[source_index, track_index] ** 2
                            + projection_distances[target_index, track_index] ** 2
                        )
                    )
                    for track_index in shared_track_indices
                )
                shared_track_ids = tuple(tracks[index].global_track_id for index in shared_track_indices)
            else:
                global_mahalanobis = pixel_mahalanobis
                shared_track_ids = ()

            bbox_scale_delta = _bbox_log_scale_delta(source.bbox_xyxy, target.bbox_xyxy)
            scale_rate_delta = abs(source.bbox_scale_rate_s - target.bbox_scale_rate_s)
            angular_velocity_delta = float(
                np.linalg.norm(source.angular_velocity_rad_s - target.angular_velocity_rad_s)
            )
            extrinsics_covariance_trace = (
                source_camera.extrinsics_covariance_trace
                + target_camera.extrinsics_covariance_trace
            )
            feature_values = (
                abs(source.measurement_timestamp - target.measurement_timestamp),
                pixel_mahalanobis,
                reprojection_error,
                ray_distance,
                bbox_scale_delta,
                scale_rate_delta,
                angular_velocity_delta,
                baseline,
                extrinsics_covariance_trace,
                pair_epipolar_error,
                angle,
                global_mahalanobis,
                source.confidence * target.confidence,
                float(len(shared_track_ids)),
            )
            gate_score = (
                feature_values[0] / cfg.max_time_delta_s
                + pair_epipolar_error / cfg.max_epipolar_error_px
                + ray_distance / cfg.max_ray_closest_distance_m
                + reprojection_error / cfg.max_reprojection_error_px
                + pixel_mahalanobis / cfg.max_pixel_mahalanobis
                + global_mahalanobis / cfg.max_global_projection_mahalanobis
            )
            candidate_edges.append(
                SparseCandidateEdge(
                    source_index=source_index,
                    target_index=target_index,
                    source_tracklet_key=source.tracklet_key,
                    target_tracklet_key=target.tracklet_key,
                    shared_global_track_ids=shared_track_ids,
                    feature_values=tuple(float(value) for value in feature_values),
                    gate_score=float(gate_score),
                )
            )

    counts["pre_cap_edges"] = len(candidate_edges)
    retained = _degree_limited_edges(candidate_edges, len(nodes), cfg.max_neighbors_per_node)
    counts["retained_edges"] = len(retained)
    counts["rejected_final_degree_cap"] = len(candidate_edges) - len(retained)
    edge_index = (
        np.asarray([(edge.source_index, edge.target_index) for edge in retained], dtype=np.int64).T
        if retained
        else np.empty((2, 0), dtype=np.int64)
    )
    edge_features = (
        np.asarray([edge.feature_values for edge in retained], dtype=np.float32)
        if retained
        else np.empty((0, len(EDGE_FEATURE_NAMES)), dtype=np.float32)
    )
    return SparseTrackletGraph(
        nodes=nodes,
        node_features=node_features,
        edge_index=edge_index,
        edge_features=edge_features,
        edges=retained,
        candidate_counts=counts,
    )


def constrained_tracklet_clusters(
    graph: SparseTrackletGraph,
    edge_probabilities: Sequence[float] | np.ndarray | Any,
    *,
    probability_threshold: float = 0.5,
) -> tuple[TrackletCluster, ...]:
    """Cluster high-probability edges with a one-tracklet-per-camera rule."""

    probabilities = _probability_array(edge_probabilities)
    if probabilities.shape != (graph.edge_count,):
        raise ValueError("edge_probabilities must contain one value per graph edge")
    if not 0.0 <= probability_threshold <= 1.0:
        raise ValueError("probability_threshold must be in [0, 1]")
    parent = list(range(graph.node_count))
    component_cameras = [{graph.nodes[index].camera_key} for index in range(graph.node_count)]

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    ordered_edges = sorted(
        enumerate(graph.edges),
        key=lambda item: (-float(probabilities[item[0]]), item[1].source_tracklet_key, item[1].target_tracklet_key),
    )
    for edge_index, edge in ordered_edges:
        if probabilities[edge_index] < probability_threshold:
            break
        left_root = find(edge.source_index)
        right_root = find(edge.target_index)
        if left_root == right_root:
            continue
        if component_cameras[left_root].intersection(component_cameras[right_root]):
            continue
        if left_root > right_root:
            left_root, right_root = right_root, left_root
        parent[right_root] = left_root
        component_cameras[left_root].update(component_cameras[right_root])

    components: dict[int, list[int]] = defaultdict(list)
    for node_index in range(graph.node_count):
        components[find(node_index)].append(node_index)
    clusters: list[TrackletCluster] = []
    for node_indices in sorted(components.values(), key=lambda values: graph.nodes[min(values)].tracklet_key):
        ordered_indices = tuple(sorted(node_indices, key=lambda index: graph.nodes[index].tracklet_key))
        tracklet_keys = tuple(graph.nodes[index].tracklet_key for index in ordered_indices)
        camera_keys = tuple(graph.nodes[index].camera_key for index in ordered_indices)
        clusters.append(
            TrackletCluster(
                cluster_key="cluster:" + "|".join(tracklet_keys),
                node_indices=ordered_indices,
                tracklet_keys=tracklet_keys,
                camera_keys=camera_keys,
            )
        )
    return tuple(clusters)


def bind_clusters_to_center_tracks(
    graph: SparseTrackletGraph,
    clusters: Iterable[TrackletCluster],
    camera_geometries: Iterable[TrackletCameraGeometry],
    center_tracks: Iterable[GlobalTrack],
    *,
    max_binding_mahalanobis: float = 6.0,
    ambiguity_margin: float = 0.5,
    config: SparseTrackletGraphConfig | None = None,
) -> tuple[CenterTrackBindingDecision, ...]:
    """Hungarian-bind clusters only to IDs supplied by the center."""

    if max_binding_mahalanobis <= 0.0 or ambiguity_margin < 0.0:
        raise ValueError("binding gate must be positive and ambiguity margin non-negative")
    cfg = config or SparseTrackletGraphConfig()
    cluster_items = tuple(clusters)
    tracks = tuple(center_tracks)
    camera_items = tuple(camera_geometries)
    camera_by_key = {camera.camera_key: camera for camera in camera_items}
    if len(camera_by_key) != len(camera_items):
        raise ValueError("camera geometry keys must be unique")
    center_ids = tuple(track.global_track_id for track in tracks)
    if len(center_ids) != len(set(center_ids)):
        raise ValueError("center global_track_id values must be unique")
    if not cluster_items:
        return ()
    if not tracks:
        return tuple(
            CenterTrackBindingDecision(
                cluster_key=cluster.cluster_key,
                global_track_id=None,
                cost=None,
                decision_state="unbound",
                supporting_tracklet_keys=cluster.tracklet_keys,
            )
            for cluster in cluster_items
        )

    distances = _center_projection_distance_matrix(graph.nodes, camera_by_key, tracks, cfg)
    costs = np.full((len(cluster_items), len(tracks)), np.inf, dtype=float)
    for row, cluster in enumerate(cluster_items):
        cluster_distances = distances[np.asarray(cluster.node_indices, dtype=int)]
        finite_count = np.sum(np.isfinite(cluster_distances), axis=0)
        finite_sum = np.sum(np.where(np.isfinite(cluster_distances), cluster_distances, 0.0), axis=0)
        valid = finite_count == len(cluster.node_indices)
        costs[row, valid] = finite_sum[valid] / finite_count[valid]

    assignments = _unique_assignment(costs)
    assigned_by_row = {row: col for row, col in assignments if costs[row, col] <= max_binding_mahalanobis}
    decisions: list[CenterTrackBindingDecision] = []
    for row, cluster in enumerate(cluster_items):
        column = assigned_by_row.get(row)
        if column is None:
            decisions.append(
                CenterTrackBindingDecision(
                    cluster_key=cluster.cluster_key,
                    global_track_id=None,
                    cost=None,
                    decision_state="unbound",
                    supporting_tracklet_keys=cluster.tracklet_keys,
                )
            )
            continue
        row_costs = np.sort(costs[row, np.isfinite(costs[row])])
        ambiguous = len(row_costs) > 1 and row_costs[1] - row_costs[0] < ambiguity_margin
        decisions.append(
            CenterTrackBindingDecision(
                cluster_key=cluster.cluster_key,
                global_track_id=None if ambiguous else center_ids[column],
                cost=float(costs[row, column]),
                decision_state="ambiguous" if ambiguous else "bound",
                supporting_tracklet_keys=cluster.tracklet_keys,
            )
        )
    output_ids = {decision.global_track_id for decision in decisions if decision.global_track_id is not None}
    if not output_ids.issubset(set(center_ids)):
        raise RuntimeError("D5 center binding attempted to create a global_track_id")
    return tuple(decisions)


def _node_feature_vector(
    node: CameraLocalTracklet,
    camera_geometry: TrackletCameraGeometry,
) -> np.ndarray:
    width, height = camera_geometry.camera.image_size
    area = _bbox_area(node.bbox_xyxy)
    image_area = max(float(width * height), 1.0)
    if node.bbox_xyxy is None:
        aspect = 1.0
    else:
        x1, y1, x2, y2 = node.bbox_xyxy
        aspect = max(x2 - x1, _EPS) / max(y2 - y1, _EPS)
    image_diagonal_squared = max(float(width * width + height * height), 1.0)
    return np.asarray(
        [
            (node.center_px[0] - 0.5 * width) / max(float(width), 1.0),
            (node.center_px[1] - 0.5 * height) / max(float(height), 1.0),
            math.log(max(area / image_area, 1.0e-12)),
            math.log(max(aspect, 1.0e-12)),
            node.angular_velocity_rad_s[0],
            node.angular_velocity_rad_s[1],
            node.bbox_scale_rate_s,
            node.confidence,
            float(np.trace(node.covariance_px)) / image_diagonal_squared,
            max(0.0, node.measurement_timestamp - float(node.tracklet_start_timestamp)),
        ],
        dtype=np.float32,
    )


def _center_projection_distance_matrix(
    nodes: Sequence[CameraLocalTracklet],
    camera_by_key: Mapping[str, TrackletCameraGeometry],
    tracks: Sequence[GlobalTrack],
    config: SparseTrackletGraphConfig,
) -> np.ndarray:
    distances = np.full((len(nodes), len(tracks)), np.inf, dtype=float)
    if not nodes or not tracks:
        return distances
    groups: dict[tuple[str, float], list[int]] = defaultdict(list)
    for index, node in enumerate(nodes):
        groups[(node.camera_key, node.measurement_timestamp)].append(index)

    for (camera_key, timestamp), node_indices in groups.items():
        geometry = camera_by_key[camera_key]
        camera = geometry.camera
        positions = np.vstack(
            [track.position + track.velocity * (timestamp - track.timestamp) for track in tracks]
        )
        covariances = np.stack(
            [
                track.covariance
                + np.eye(3, dtype=float)
                * config.global_process_noise_m2_s4
                * (timestamp - track.timestamp) ** 2
                for track in tracks
            ]
        )
        camera_points = positions @ camera.R.T + camera.t[None, :]
        depths = camera_points[:, 2]
        valid = depths > _EPS
        safe_depth = np.where(valid, depths, 1.0)
        pixels = np.column_stack(
            (
                camera.K[0, 0] * camera_points[:, 0] / safe_depth + camera.K[0, 2],
                camera.K[1, 1] * camera_points[:, 1] / safe_depth + camera.K[1, 2],
            )
        )
        width, height = camera.image_size
        valid &= (
            (pixels[:, 0] >= -config.fov_margin_px)
            & (pixels[:, 0] <= width + config.fov_margin_px)
            & (pixels[:, 1] >= -config.fov_margin_px)
            & (pixels[:, 1] <= height + config.fov_margin_px)
        )
        jacobian_camera = np.zeros((len(tracks), 2, 3), dtype=float)
        jacobian_camera[:, 0, 0] = camera.K[0, 0] / safe_depth
        jacobian_camera[:, 0, 2] = -camera.K[0, 0] * camera_points[:, 0] / safe_depth**2
        jacobian_camera[:, 1, 1] = camera.K[1, 1] / safe_depth
        jacobian_camera[:, 1, 2] = -camera.K[1, 1] * camera_points[:, 1] / safe_depth**2
        jacobian_ned = np.einsum("nij,jk->nik", jacobian_camera, camera.R)
        spatial_covariance = covariances + geometry.position_covariance_ned[None, :, :]
        covariance_px = np.einsum(
            "nij,njk,nlk->nil",
            jacobian_ned,
            spatial_covariance,
            jacobian_ned,
        )
        focal_mean = 0.5 * (camera.K[0, 0] + camera.K[1, 1])
        attitude_variance_px = focal_mean**2 * float(np.trace(geometry.attitude_covariance_rad2) / 3.0)
        covariance_px += camera.measurement_cov[None, :, :]
        covariance_px += np.eye(2, dtype=float)[None, :, :] * (
            attitude_variance_px + config.covariance_regularization
        )

        for node_index in node_indices:
            residual = nodes[node_index].center_px[None, :] - pixels
            combined_covariance = covariance_px + nodes[node_index].covariance_px[None, :, :]
            d2 = _batched_mahalanobis_squared(residual, combined_covariance, config.covariance_regularization)
            d2[~valid] = np.inf
            distances[node_index] = np.sqrt(np.maximum(d2, 0.0))
    return distances


def _projection_support_by_node(
    distances: np.ndarray,
    tracks: Sequence[GlobalTrack],
    config: SparseTrackletGraphConfig,
) -> tuple[dict[int, float], ...]:
    output: list[dict[int, float]] = []
    for row in distances:
        indices = np.flatnonzero(row <= config.max_global_projection_mahalanobis)
        output.append({int(index): float(row[index]) for index in indices})
    if not tracks:
        return tuple({} for _ in range(distances.shape[0]))
    return tuple(output)


def _epipolar_error_matrix(
    left_pixels: np.ndarray,
    right_pixels: np.ndarray,
    left_camera: CameraModel,
    right_camera: CameraModel,
) -> np.ndarray:
    fundamental = _fundamental_matrix(left_camera, right_camera)
    left_h = np.column_stack((left_pixels, np.ones(len(left_pixels), dtype=float)))
    right_h = np.column_stack((right_pixels, np.ones(len(right_pixels), dtype=float)))
    right_lines = (fundamental @ left_h.T).T
    left_lines = (fundamental.T @ right_h.T).T
    residual = np.abs(left_h @ fundamental.T @ right_h.T)
    right_denominator = np.maximum(
        np.sqrt(right_lines[:, 0] ** 2 + right_lines[:, 1] ** 2),
        _EPS,
    )[:, None]
    left_denominator = np.maximum(
        np.sqrt(left_lines[:, 0] ** 2 + left_lines[:, 1] ** 2),
        _EPS,
    )[None, :]
    return 0.5 * (residual / right_denominator + residual / left_denominator)


def _epipolar_error_pair(
    source_pixel: np.ndarray,
    target_pixel: np.ndarray,
    fundamental_left_to_right: np.ndarray,
    *,
    source_is_left: bool,
) -> float:
    """Compute one symmetric epipolar distance without an outer-product matrix."""

    if source_is_left:
        left_pixel = source_pixel
        right_pixel = target_pixel
    else:
        left_pixel = target_pixel
        right_pixel = source_pixel
    left_h = np.array([left_pixel[0], left_pixel[1], 1.0], dtype=float)
    right_h = np.array([right_pixel[0], right_pixel[1], 1.0], dtype=float)
    right_line = fundamental_left_to_right @ left_h
    left_line = fundamental_left_to_right.T @ right_h
    residual = abs(float(right_h @ right_line))
    right_denominator = max(float(np.linalg.norm(right_line[:2])), _EPS)
    left_denominator = max(float(np.linalg.norm(left_line[:2])), _EPS)
    return 0.5 * residual * (
        1.0 / right_denominator + 1.0 / left_denominator
    )


def _fundamental_matrix(left: CameraModel, right: CameraModel) -> np.ndarray:
    left_center = -left.R.T @ left.t
    right_center = -right.R.T @ right.t
    rotation_right_from_left = right.R @ left.R.T
    translation_right_from_left = right.R @ (left_center - right_center)
    essential = _skew(translation_right_from_left) @ rotation_right_from_left
    fundamental = np.linalg.inv(right.K).T @ essential @ np.linalg.inv(left.K)
    norm = float(np.linalg.norm(fundamental))
    return fundamental / max(norm, _EPS)


def _ray_pair_geometry(
    left: CameraLocalTracklet,
    right: CameraLocalTracklet,
    left_camera: TrackletCameraGeometry,
    right_camera: TrackletCameraGeometry,
) -> tuple[float, np.ndarray, float, float] | None:
    left_origin, left_direction = _world_ray(left.center_px, left_camera.camera)
    right_origin, right_direction = _world_ray(right.center_px, right_camera.camera)
    baseline = float(np.linalg.norm(left_origin - right_origin))
    cosine = float(np.clip(left_direction @ right_direction, -1.0, 1.0))
    angle = math.acos(cosine)
    denominator = max(0.0, 1.0 - cosine * cosine)
    if denominator <= 1.0e-12:
        return None
    offset = left_origin - right_origin
    left_distance = (cosine * float(right_direction @ offset) - float(left_direction @ offset)) / denominator
    right_distance = (float(right_direction @ offset) - cosine * float(left_direction @ offset)) / denominator
    if left_distance <= 0.0 or right_distance <= 0.0:
        return None
    left_point = left_origin + left_distance * left_direction
    right_point = right_origin + right_distance * right_direction
    ray_distance = float(np.linalg.norm(left_point - right_point))
    midpoint = 0.5 * (left_point + right_point)
    return ray_distance, midpoint, baseline, angle


def _world_ray(pixel: np.ndarray, camera: CameraModel) -> tuple[np.ndarray, np.ndarray]:
    homogeneous = np.array([pixel[0], pixel[1], 1.0], dtype=float)
    direction_camera = np.linalg.inv(camera.K) @ homogeneous
    direction_world = camera.R.T @ direction_camera
    direction_world /= max(float(np.linalg.norm(direction_world)), _EPS)
    origin_world = -camera.R.T @ camera.t
    return origin_world, direction_world


def _project_world_point(point_ned: np.ndarray, camera: CameraModel) -> np.ndarray | None:
    camera_point = camera.R @ np.asarray(point_ned, dtype=float).reshape(3) + camera.t
    if camera_point[2] <= _EPS:
        return None
    return np.array(
        [
            camera.K[0, 0] * camera_point[0] / camera_point[2] + camera.K[0, 2],
            camera.K[1, 1] * camera_point[1] / camera_point[2] + camera.K[1, 2],
        ],
        dtype=float,
    )


def _degree_limited_edges(
    edges: Iterable[SparseCandidateEdge],
    node_count: int,
    max_neighbors: int,
) -> tuple[SparseCandidateEdge, ...]:
    degrees = np.zeros(node_count, dtype=int)
    retained: list[SparseCandidateEdge] = []
    ordered = sorted(edges, key=lambda edge: (edge.gate_score, edge.source_tracklet_key, edge.target_tracklet_key))
    for edge in ordered:
        if degrees[edge.source_index] >= max_neighbors or degrees[edge.target_index] >= max_neighbors:
            continue
        retained.append(edge)
        degrees[edge.source_index] += 1
        degrees[edge.target_index] += 1
    return tuple(sorted(retained, key=lambda edge: (edge.source_index, edge.target_index)))


def _unique_assignment(costs: np.ndarray) -> tuple[tuple[int, int], ...]:
    if costs.size == 0:
        return ()
    finite = np.isfinite(costs)
    if not np.any(finite):
        return ()
    replacement = max(1.0e6, float(np.max(costs[finite])) * 1.0e6)
    work = np.where(finite, costs, replacement)
    try:
        from scipy.optimize import linear_sum_assignment  # type: ignore

        rows, columns = linear_sum_assignment(work)
        return tuple((int(row), int(column)) for row, column in zip(rows, columns) if finite[row, column])
    except Exception:  # pragma: no cover - deterministic fallback for minimal environments.
        candidates = sorted(
            (float(costs[row, column]), row, column)
            for row, column in zip(*np.nonzero(finite))
        )
        used_rows: set[int] = set()
        used_columns: set[int] = set()
        selected: list[tuple[int, int]] = []
        for _, row, column in candidates:
            if row in used_rows or column in used_columns:
                continue
            used_rows.add(row)
            used_columns.add(column)
            selected.append((row, column))
        return tuple(selected)


def _probability_array(values: Sequence[float] | np.ndarray | Any) -> np.ndarray:
    if hasattr(values, "detach") and callable(values.detach):
        values = values.detach().cpu().numpy()
    probabilities = np.asarray(values, dtype=float).reshape(-1)
    if not np.all(np.isfinite(probabilities)) or np.any((probabilities < 0.0) | (probabilities > 1.0)):
        raise ValueError("edge probabilities must be finite and in [0, 1]")
    return probabilities


def _batched_mahalanobis_squared(
    residual: np.ndarray,
    covariance: np.ndarray,
    regularization: float,
) -> np.ndarray:
    covariance = covariance.copy()
    covariance[:, 0, 0] += regularization
    covariance[:, 1, 1] += regularization
    a = covariance[:, 0, 0]
    b = 0.5 * (covariance[:, 0, 1] + covariance[:, 1, 0])
    c = covariance[:, 1, 1]
    determinant = a * c - b * b
    valid = determinant > _EPS
    output = np.full(residual.shape[0], np.inf, dtype=float)
    x = residual[:, 0]
    y = residual[:, 1]
    output[valid] = (
        c[valid] * x[valid] ** 2
        - 2.0 * b[valid] * x[valid] * y[valid]
        + a[valid] * y[valid] ** 2
    ) / determinant[valid]
    return output


def _mahalanobis_squared(residual: np.ndarray, covariance: np.ndarray, regularization: float) -> float:
    matrix = covariance + np.eye(2, dtype=float) * regularization
    return float(residual.T @ np.linalg.pinv(matrix) @ residual)


def _bbox_log_scale_delta(
    left: tuple[float, float, float, float] | None,
    right: tuple[float, float, float, float] | None,
) -> float:
    left_area = _bbox_area(left)
    right_area = _bbox_area(right)
    if left_area <= 0.0 or right_area <= 0.0:
        return 0.0
    return abs(0.5 * math.log(left_area / right_area))


def _bbox_area(bbox: tuple[float, float, float, float] | None) -> float:
    if bbox is None:
        return 0.0
    x1, y1, x2, y2 = bbox
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _center_in_fov(center: np.ndarray, camera: CameraModel, margin: float) -> bool:
    width, height = camera.image_size
    return bool(
        -margin <= center[0] <= width + margin
        and -margin <= center[1] <= height + margin
    )


def _skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = np.asarray(vector, dtype=float).reshape(3)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=float)


def _optional_bbox(values: Sequence[float] | np.ndarray | None) -> tuple[float, float, float, float] | None:
    if values is None:
        return None
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (4,) or not np.all(np.isfinite(array)):
        raise ValueError("bbox_xyxy must contain four finite values")
    x1, y1, x2, y2 = array.tolist()
    if x2 < x1 or y2 < y1:
        raise ValueError("bbox_xyxy must be ordered as x1, y1, x2, y2")
    return (float(x1), float(y1), float(x2), float(y2))


def _finite_vector(values: Any, size: int, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (size,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must have shape ({size},) with finite values")
    return array.copy()


def _positive_semidefinite_matrix(
    values: Any,
    shape: tuple[int, int],
    name: str,
) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.shape != shape or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must have shape {shape} with finite values")
    symmetric = 0.5 * (array + array.T)
    if float(np.min(np.linalg.eigvalsh(symmetric))) < -1.0e-9:
        raise ValueError(f"{name} must be positive semidefinite")
    return symmetric.copy()


def _finite_float(value: Any, name: str) -> float:
    output = float(value)
    if not np.isfinite(output):
        raise ValueError(f"{name} must be finite")
    return output


def _read_only(array: np.ndarray) -> np.ndarray:
    array.setflags(write=False)
    return array


def _normalise_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _is_forbidden_online_key(key: str) -> bool:
    if key in _FORBIDDEN_ONLINE_KEYS:
        return True
    return (
        key.startswith("truth_")
        or key.endswith("_truth_id")
        or key.endswith("_actor_id")
        or key.endswith("_actor_name")
        or key.endswith("_entity_id")
        or key.endswith("_entity_name")
        or key.endswith("_intruder_id")
        or key.endswith("_intruder_name")
        or key.endswith("_object_id")
        or key.endswith("_object_name")
        or key.endswith("_target_id")
        or key.endswith("_target_name")
    )


def _is_local_id_key(key: str) -> bool:
    return (
        key in _LOCAL_ID_KEYS
        or key.endswith("_local_track_id")
        or key.endswith("_local_tracklet_id")
    )


def is_truth_like_local_track_id(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    local_track_id = value.strip()
    return bool(
        local_track_id
        and (
            _IDENTITY_TOKEN.search(local_track_id)
            or _TRUTH_LIKE_LOCAL_ID.search(local_track_id)
        )
    )


__all__ = [
    "CameraLocalTracklet",
    "CenterTrackBindingDecision",
    "EDGE_FEATURE_NAMES",
    "NODE_FEATURE_NAMES",
    "SparseCandidateEdge",
    "SparseTrackletGraph",
    "SparseTrackletGraphConfig",
    "TrackletCameraGeometry",
    "TrackletCluster",
    "assert_anonymous_online_payload",
    "bind_clusters_to_center_tracks",
    "build_sparse_tracklet_graph",
    "constrained_tracklet_clusters",
    "is_truth_like_local_track_id",
]
