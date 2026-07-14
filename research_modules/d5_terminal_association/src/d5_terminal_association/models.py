"""Data models for terminal visual association.

The central invariant is that global track IDs are center-owned. The local
module may reference them in a decision, but it must not mutate or reassign
them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


def _as_vector(values: Any, size: int, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (size,):
        raise ValueError(f"{name} must have shape ({size},), got {array.shape}")
    return array.copy()


def _as_matrix(values: Any, shape: tuple[int, int], name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    return array.copy()


def _as_square_matrix(values: Any, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 2 or array.shape[0] != array.shape[1]:
        raise ValueError(f"{name} must be a square matrix, got {array.shape}")
    return array.copy()


def _optional_vector(values: Any | None, size: int, name: str) -> np.ndarray | None:
    if values is None:
        return None
    return _as_vector(values, size, name)


def _optional_matrix(values: Any | None, shape: tuple[int, int], name: str) -> np.ndarray | None:
    if values is None:
        return None
    return _as_matrix(values, shape, name)


def _optional_square_matrix(values: Any | None, name: str) -> np.ndarray | None:
    if values is None:
        return None
    return _as_square_matrix(values, name)


def _optional_bbox(values: Any | None) -> tuple[float, float, float, float] | None:
    if values is None:
        return None
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (4,):
        raise ValueError(f"bbox must have shape (4,), got {array.shape}")
    x1, y1, x2, y2 = array.tolist()
    if x2 < x1 or y2 < y1:
        raise ValueError("bbox must be (x_min, y_min, x_max, y_max)")
    return (x1, y1, x2, y2)


def _as_string_tuple(values: Any | None) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(str(value) for value in values)


def _optional_string(value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: Any | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _finite_float_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    if not np.isfinite(value):
        return None
    return value


def _optional_pair_tuple(values: Any | None) -> tuple[float, float] | None:
    if values is None:
        return None
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (2,):
        raise ValueError(f"pair must have shape (2,), got {array.shape}")
    return (float(array[0]), float(array[1]))


def _optional_image_size(values: Any | None) -> tuple[int, int] | None:
    if values is None:
        return None
    array = np.asarray(values, dtype=int).reshape(-1)
    if array.shape != (2,):
        raise ValueError(f"image_size must have shape (2,), got {array.shape}")
    width, height = int(array[0]), int(array[1])
    if width <= 0 or height <= 0:
        raise ValueError("image_size must be positive (width, height)")
    return (width, height)


def _visual_tracklet_key(resource_id: str, camera_id: str | None, local_track_id: str) -> str:
    if camera_id:
        return f"{resource_id}/{camera_id}:{local_track_id}"
    return f"{resource_id}:{local_track_id}"


def _bbox_area(bbox: tuple[float, float, float, float] | None) -> float:
    if bbox is None:
        return 0.0
    x1, y1, x2, y2 = bbox
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _normalized_clip_sides(values: Any | None) -> tuple[str, ...]:
    allowed = {"left", "top", "right", "bottom"}
    normalized = tuple(dict.fromkeys(str(value).strip().lower() for value in (values or ())))
    invalid = tuple(value for value in normalized if value not in allowed)
    if invalid:
        raise ValueError(f"bbox_edge_clip_sides contains invalid values: {invalid}")
    return normalized


@dataclass(frozen=True)
class CameraModel:
    """Pinhole camera with a world-to-camera transform.

    `R` and `t` implement `P_c = R @ P_w + t`.
    """

    K: np.ndarray
    R: np.ndarray
    t: np.ndarray
    image_size: tuple[int, int]
    measurement_cov: np.ndarray = field(default_factory=lambda: np.diag([4.0, 4.0]))
    dist_coeffs: np.ndarray | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "K", _as_matrix(self.K, (3, 3), "K"))
        object.__setattr__(self, "R", _as_matrix(self.R, (3, 3), "R"))
        object.__setattr__(self, "t", _as_vector(self.t, 3, "t"))
        object.__setattr__(
            self, "measurement_cov", _as_matrix(self.measurement_cov, (2, 2), "measurement_cov")
        )
        if self.dist_coeffs is not None:
            coeffs = np.asarray(self.dist_coeffs, dtype=float).reshape(-1).copy()
            object.__setattr__(self, "dist_coeffs", coeffs)
        image_size = _optional_image_size(self.image_size)
        if image_size is None:
            raise ValueError("image_size is required")
        object.__setattr__(self, "image_size", image_size)


@dataclass(frozen=True)
class GlobalTrack:
    """Center-owned global track state.

    The frozen dataclass prevents accidental reassignment of `global_track_id`
    inside the terminal module.
    """

    global_track_id: str
    position: np.ndarray
    covariance: np.ndarray
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    category: str = "unknown"
    timestamp: float = 0.0
    track_version: int = 0

    def __post_init__(self) -> None:
        if not self.global_track_id:
            raise ValueError("global_track_id must be non-empty")
        object.__setattr__(self, "position", _as_vector(self.position, 3, "position"))
        object.__setattr__(self, "covariance", _as_matrix(self.covariance, (3, 3), "covariance"))
        object.__setattr__(self, "velocity", _as_vector(self.velocity, 3, "velocity"))


@dataclass(frozen=True)
class CameraGeometryEvidence:
    """Truth-free camera geometry and timing evidence for D7/replay consumers.

    A missing field is represented explicitly. `geometry_valid` is true only
    when intrinsics, camera-to-NED extrinsics, and synchronized attitude are
    all available and validated.
    """

    measurement_timestamp: float
    arrival_timestamp: float
    exposure_timestamp: float | None = None
    camera_intrinsics: np.ndarray | None = None
    camera_to_ned_rotation: np.ndarray | None = None
    camera_position_ned: np.ndarray | None = None
    attitude_timestamp: float | None = None
    attitude_age_s: float | None = None
    intrinsics_valid: bool | None = None
    extrinsics_valid: bool | None = None
    attitude_valid: bool | None = None
    source: str = "unavailable"
    unavailable_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        measurement_timestamp = float(self.measurement_timestamp)
        arrival_timestamp = float(self.arrival_timestamp)
        exposure_timestamp = _finite_float_or_none(self.exposure_timestamp)
        if exposure_timestamp is None:
            exposure_timestamp = measurement_timestamp
        intrinsics = _optional_matrix(self.camera_intrinsics, (3, 3), "camera_intrinsics")
        rotation = _optional_matrix(
            self.camera_to_ned_rotation,
            (3, 3),
            "camera_to_ned_rotation",
        )
        position = _optional_vector(self.camera_position_ned, 3, "camera_position_ned")
        attitude_timestamp = _finite_float_or_none(self.attitude_timestamp)
        attitude_age_s = _finite_float_or_none(self.attitude_age_s)
        if attitude_age_s is not None and attitude_age_s < 0.0:
            raise ValueError("attitude_age_s must be non-negative")

        intrinsics_valid = bool(intrinsics is not None) if self.intrinsics_valid is None else bool(self.intrinsics_valid)
        extrinsics_present = rotation is not None and position is not None
        extrinsics_valid = extrinsics_present if self.extrinsics_valid is None else bool(self.extrinsics_valid)
        attitude_valid = bool(attitude_timestamp is not None) if self.attitude_valid is None else bool(self.attitude_valid)
        reasons = list(dict.fromkeys(str(value) for value in self.unavailable_reasons if str(value)))
        if not intrinsics_valid:
            reasons.append("camera_intrinsics_unavailable")
        if not extrinsics_valid:
            reasons.append("camera_extrinsics_unavailable")
        if not attitude_valid:
            reasons.append("camera_attitude_unavailable_or_stale")

        object.__setattr__(self, "measurement_timestamp", measurement_timestamp)
        object.__setattr__(self, "arrival_timestamp", arrival_timestamp)
        object.__setattr__(self, "exposure_timestamp", exposure_timestamp)
        object.__setattr__(self, "camera_intrinsics", intrinsics)
        object.__setattr__(self, "camera_to_ned_rotation", rotation)
        object.__setattr__(self, "camera_position_ned", position)
        object.__setattr__(self, "attitude_timestamp", attitude_timestamp)
        object.__setattr__(self, "attitude_age_s", attitude_age_s)
        object.__setattr__(self, "intrinsics_valid", intrinsics_valid)
        object.__setattr__(self, "extrinsics_valid", extrinsics_valid)
        object.__setattr__(self, "attitude_valid", attitude_valid)
        object.__setattr__(self, "source", str(self.source or "unavailable"))
        object.__setattr__(self, "unavailable_reasons", tuple(dict.fromkeys(reasons)))

    @property
    def geometry_valid(self) -> bool:
        return bool(
            self.intrinsics_valid
            and self.extrinsics_valid
            and self.attitude_valid
            and not self.unavailable_reasons
        )

    def to_metadata(self) -> dict[str, Any]:
        return {
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "exposure_timestamp": self.exposure_timestamp,
            "camera_intrinsics": (
                self.camera_intrinsics.tolist() if self.camera_intrinsics is not None else None
            ),
            "camera_to_ned_rotation": (
                self.camera_to_ned_rotation.tolist()
                if self.camera_to_ned_rotation is not None
                else None
            ),
            "camera_position_ned": (
                self.camera_position_ned.tolist() if self.camera_position_ned is not None else None
            ),
            "attitude_timestamp": self.attitude_timestamp,
            "attitude_age_s": self.attitude_age_s,
            "intrinsics_valid": self.intrinsics_valid,
            "extrinsics_valid": self.extrinsics_valid,
            "attitude_valid": self.attitude_valid,
            "geometry_valid": self.geometry_valid,
            "geometry_source": self.source,
            "geometry_unavailable_reasons": list(self.unavailable_reasons),
        }


@dataclass(frozen=True)
class LocalVisualTrack:
    """Local detector or MOT output in image coordinates."""

    local_track_id: str
    center_px: np.ndarray
    bbox: tuple[float, float, float, float] | None = None
    bearing_rate: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=float))
    category: str = "unknown"
    quality: float = 1.0
    mot_history_length: int = 1
    timestamp: float = 0.0
    local_track_state: str = "measured"
    prediction_age_s: float | None = None
    arrival_timestamp: float | None = None
    exposure_timestamp: float | None = None
    detection_source: str = "unknown"
    track_transition_state: str = "unknown"
    track_reset_reason: str | None = None
    bbox_edge_clipped: bool = False
    bbox_edge_clip_sides: tuple[str, ...] = ()
    image_size: tuple[int, int] | None = None
    camera_geometry: CameraGeometryEvidence | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.local_track_id:
            raise ValueError("local_track_id must be non-empty")
        object.__setattr__(self, "center_px", _as_vector(self.center_px, 2, "center_px"))
        object.__setattr__(self, "bbox", _optional_bbox(self.bbox))
        object.__setattr__(self, "bearing_rate", _as_vector(self.bearing_rate, 2, "bearing_rate"))
        object.__setattr__(self, "quality", float(np.clip(self.quality, 0.0, 1.0)))
        if self.mot_history_length < 0:
            raise ValueError("mot_history_length must be non-negative")
        state = str(self.local_track_state).strip().lower()
        if state not in {"measured", "predicted", "lost"}:
            raise ValueError("local_track_state must be measured, predicted, or lost")
        prediction_age_s = _finite_float_or_none(self.prediction_age_s)
        if prediction_age_s is not None and prediction_age_s < 0.0:
            raise ValueError("prediction_age_s must be non-negative")
        object.__setattr__(self, "local_track_state", state)
        object.__setattr__(self, "prediction_age_s", prediction_age_s)
        arrival_timestamp = _finite_float_or_none(self.arrival_timestamp)
        if arrival_timestamp is None:
            arrival_timestamp = float(self.timestamp)
        exposure_timestamp = _finite_float_or_none(self.exposure_timestamp)
        if exposure_timestamp is None:
            exposure_timestamp = float(self.timestamp)
        transition = str(self.track_transition_state).strip().lower()
        if transition not in {"initialized", "continued", "switched", "reacquired", "reset", "unknown"}:
            raise ValueError("invalid track_transition_state")
        clip_sides = _normalized_clip_sides(self.bbox_edge_clip_sides)
        image_size = _optional_image_size(self.image_size)
        object.__setattr__(self, "timestamp", float(self.timestamp))
        object.__setattr__(self, "arrival_timestamp", arrival_timestamp)
        object.__setattr__(self, "exposure_timestamp", exposure_timestamp)
        object.__setattr__(self, "detection_source", str(self.detection_source or "unknown"))
        object.__setattr__(self, "track_transition_state", transition)
        object.__setattr__(self, "track_reset_reason", _optional_string(self.track_reset_reason))
        object.__setattr__(self, "bbox_edge_clipped", bool(self.bbox_edge_clipped or clip_sides))
        object.__setattr__(self, "bbox_edge_clip_sides", clip_sides)
        object.__setattr__(self, "image_size", image_size)
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_evidence_metadata(self) -> dict[str, Any]:
        """Return the truth-free local evidence fields consumed by main/D7."""

        geometry = (
            self.camera_geometry.to_metadata()
            if self.camera_geometry is not None
            else {
                "geometry_valid": False,
                "geometry_source": "unavailable",
                "geometry_unavailable_reasons": ["camera_geometry_not_provided"],
            }
        )
        return {
            "local_track_id": self.local_track_id,
            "mot_history_length": int(self.mot_history_length),
            "local_track_state": self.local_track_state,
            "track_transition_state": self.track_transition_state,
            "track_reset_reason": self.track_reset_reason,
            "measurement_timestamp": float(self.timestamp),
            "arrival_timestamp": float(self.arrival_timestamp),
            "exposure_timestamp": float(self.exposure_timestamp),
            "prediction_age_s": self.prediction_age_s,
            "detection_source": self.detection_source,
            "association_input_confidence": float(self.quality),
            "bbox_edge_clipped": self.bbox_edge_clipped,
            "bbox_edge_clip_sides": list(self.bbox_edge_clip_sides),
            "image_size": self.image_size,
            "camera_geometry": geometry,
            "truth_identity_used": False,
        }


@dataclass(frozen=True)
class DistributedVisualObservation:
    """Metadata-only peer visual observation for distributed terminal fusion.

    The observation may reference an existing assigned global track, but that
    reference is advisory input only. D5 does not create, rewrite, or locally
    rebind global track IDs.
    """

    resource_id: str
    local_track_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    frame_id: str
    covariance_px: np.ndarray | None = None
    center_px: np.ndarray | None = None
    bbox: tuple[float, float, float, float] | None = None
    bearing: np.ndarray | None = None
    bearing_rate: np.ndarray | None = None
    covariance: np.ndarray | None = None
    camera_id: str | None = None
    image_size: tuple[int, int] | None = None
    category: str = "unknown"
    confidence: float = 1.0
    assigned_global_track_id: str | None = None
    assigned_global_track_stale: bool = False
    source_node_id: str | None = None
    friend_conflict_state: str = "none"
    metadata: dict[str, Any] = field(default_factory=dict)
    tracklet_key: str = field(default="", init=False)

    def __post_init__(self) -> None:
        if not self.resource_id:
            raise ValueError("resource_id must be non-empty")
        if not self.local_track_id:
            raise ValueError("local_track_id must be non-empty")
        if not self.frame_id:
            raise ValueError("frame_id must be non-empty")
        object.__setattr__(self, "measurement_timestamp", float(self.measurement_timestamp))
        object.__setattr__(self, "arrival_timestamp", float(self.arrival_timestamp))
        object.__setattr__(self, "center_px", _optional_vector(self.center_px, 2, "center_px"))
        object.__setattr__(self, "bbox", _optional_bbox(self.bbox))
        object.__setattr__(self, "bearing", _optional_vector(self.bearing, 2, "bearing"))
        object.__setattr__(self, "bearing_rate", _optional_vector(self.bearing_rate, 2, "bearing_rate"))
        object.__setattr__(self, "covariance_px", _optional_matrix(self.covariance_px, (2, 2), "covariance_px"))
        object.__setattr__(self, "covariance", _optional_square_matrix(self.covariance, "covariance"))
        if self.covariance_px is None and self.covariance is None:
            raise ValueError("DistributedVisualObservation requires covariance_px or covariance")
        if self.center_px is None and self.bearing is None:
            raise ValueError("DistributedVisualObservation requires center_px or bearing")
        object.__setattr__(self, "camera_id", _optional_string(self.camera_id))
        object.__setattr__(self, "image_size", _optional_image_size(self.image_size))
        object.__setattr__(self, "assigned_global_track_id", _optional_string(self.assigned_global_track_id))
        object.__setattr__(self, "source_node_id", _optional_string(self.source_node_id))
        object.__setattr__(self, "confidence", float(np.clip(self.confidence, 0.0, 1.0)))
        object.__setattr__(self, "metadata", dict(self.metadata))
        object.__setattr__(
            self,
            "tracklet_key",
            _visual_tracklet_key(self.resource_id, self.camera_id, self.local_track_id),
        )


@dataclass(frozen=True)
class VisualTrackletSummary:
    """Per-resource/camera/local-track summary for cross-peer matching."""

    resource_id: str
    local_track_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    frame_id: str
    covariance_px: np.ndarray | None = None
    center_px: np.ndarray | None = None
    bbox: tuple[float, float, float, float] | None = None
    bearing: np.ndarray | None = None
    bearing_rate: np.ndarray | None = None
    covariance: np.ndarray | None = None
    camera_id: str | None = None
    image_size: tuple[int, int] | None = None
    category: str = "unknown"
    confidence: float = 1.0
    bbox_area: float = 0.0
    scale_rate: float = 0.0
    observation_count: int = 1
    first_measurement_timestamp: float | None = None
    assigned_global_track_id: str | None = None
    assigned_global_track_ids: tuple[str, ...] = ()
    stale_assigned_global_track_ids: tuple[str, ...] = ()
    assigned_global_track_stale: bool = False
    source_observation_ids: tuple[str, ...] = ()
    friend_conflict_state: str = "none"
    metadata: dict[str, Any] = field(default_factory=dict)
    tracklet_key: str = field(default="", init=False)

    def __post_init__(self) -> None:
        if not self.resource_id:
            raise ValueError("resource_id must be non-empty")
        if not self.local_track_id:
            raise ValueError("local_track_id must be non-empty")
        if not self.frame_id:
            raise ValueError("frame_id must be non-empty")
        object.__setattr__(self, "measurement_timestamp", float(self.measurement_timestamp))
        object.__setattr__(self, "arrival_timestamp", float(self.arrival_timestamp))
        object.__setattr__(self, "center_px", _optional_vector(self.center_px, 2, "center_px"))
        object.__setattr__(self, "bbox", _optional_bbox(self.bbox))
        object.__setattr__(self, "bearing", _optional_vector(self.bearing, 2, "bearing"))
        object.__setattr__(self, "bearing_rate", _optional_vector(self.bearing_rate, 2, "bearing_rate"))
        object.__setattr__(self, "covariance_px", _optional_matrix(self.covariance_px, (2, 2), "covariance_px"))
        object.__setattr__(self, "covariance", _optional_square_matrix(self.covariance, "covariance"))
        if self.covariance_px is None and self.covariance is None:
            raise ValueError("VisualTrackletSummary requires covariance_px or covariance")
        if self.center_px is None and self.bearing is None:
            raise ValueError("VisualTrackletSummary requires center_px or bearing")
        object.__setattr__(self, "camera_id", _optional_string(self.camera_id))
        object.__setattr__(self, "image_size", _optional_image_size(self.image_size))
        object.__setattr__(self, "confidence", float(np.clip(self.confidence, 0.0, 1.0)))
        object.__setattr__(self, "bbox_area", max(0.0, float(self.bbox_area or _bbox_area(self.bbox))))
        object.__setattr__(self, "scale_rate", float(self.scale_rate))
        object.__setattr__(self, "observation_count", int(self.observation_count))
        if self.observation_count <= 0:
            raise ValueError("observation_count must be positive")
        first_time = self.measurement_timestamp if self.first_measurement_timestamp is None else self.first_measurement_timestamp
        object.__setattr__(self, "first_measurement_timestamp", float(first_time))
        assigned_id = _optional_string(self.assigned_global_track_id)
        assigned_ids = tuple(dict.fromkeys(_as_string_tuple(self.assigned_global_track_ids)))
        if assigned_id is not None and assigned_id not in assigned_ids:
            assigned_ids = assigned_ids + (assigned_id,)
        if assigned_id is None and len(assigned_ids) == 1:
            assigned_id = assigned_ids[0]
        if len(assigned_ids) > 1:
            assigned_id = None
        stale_ids = tuple(dict.fromkeys(_as_string_tuple(self.stale_assigned_global_track_ids)))
        stale = bool(self.assigned_global_track_stale or any(track_id in stale_ids for track_id in assigned_ids))
        object.__setattr__(self, "assigned_global_track_id", assigned_id)
        object.__setattr__(self, "assigned_global_track_ids", assigned_ids)
        object.__setattr__(self, "stale_assigned_global_track_ids", stale_ids)
        object.__setattr__(self, "assigned_global_track_stale", stale)
        object.__setattr__(self, "source_observation_ids", _as_string_tuple(self.source_observation_ids))
        object.__setattr__(self, "metadata", dict(self.metadata))
        object.__setattr__(
            self,
            "tracklet_key",
            _visual_tracklet_key(self.resource_id, self.camera_id, self.local_track_id),
        )


@dataclass(frozen=True)
class PeerCameraState:
    """Peer camera state metadata used for pose-quality gating."""

    resource_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    frame_id: str
    pose_covariance: np.ndarray
    camera_id: str | None = None
    position_ned: np.ndarray | None = None
    orientation_quat_xyzw: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resource_id:
            raise ValueError("resource_id must be non-empty")
        if not self.frame_id:
            raise ValueError("frame_id must be non-empty")
        object.__setattr__(self, "measurement_timestamp", float(self.measurement_timestamp))
        object.__setattr__(self, "arrival_timestamp", float(self.arrival_timestamp))
        object.__setattr__(self, "pose_covariance", _as_square_matrix(self.pose_covariance, "pose_covariance"))
        object.__setattr__(self, "camera_id", _optional_string(self.camera_id))
        object.__setattr__(self, "position_ned", _optional_vector(self.position_ned, 3, "position_ned"))
        object.__setattr__(
            self,
            "orientation_quat_xyzw",
            _optional_vector(self.orientation_quat_xyzw, 4, "orientation_quat_xyzw"),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class Assignment:
    """Center assignment that the terminal module must respect.

    Coalition fields mirror the D3 schema-v2 guidance binding. D5 consumes
    them as read-only execution and duplicate-lock context; it never admits,
    removes, or reassigns coalition members.
    """

    assigned_global_track_id: str
    assignment_version: int = 0
    timestamp: float = 0.0
    require_version_match: bool = True
    plan_id: str | None = None
    plan_version: int | None = None
    authorization_state: str = "authorized"
    resource_id: str | None = None
    coalition_id: str | None = None
    coalition_version: int | None = None
    member_role: str = "primary"
    wave_id: int = 0
    required_resource_count: int = 1
    coordination_mode: str = "independent"
    arrival_window_start_s: float | None = None
    arrival_window_end_s: float | None = None
    activation_state: str = "active"
    terminal_authorization_scope: str = "coalition"
    arrival_coordination_required: bool = True

    def __post_init__(self) -> None:
        if not self.assigned_global_track_id:
            raise ValueError("assigned_global_track_id must be non-empty")
        if int(self.required_resource_count) < 1:
            raise ValueError("required_resource_count must be at least 1")
        if int(self.wave_id) < 0:
            raise ValueError("wave_id must be non-negative")
        if (
            self.arrival_window_start_s is not None
            and self.arrival_window_end_s is not None
            and float(self.arrival_window_start_s) > float(self.arrival_window_end_s)
        ):
            raise ValueError("arrival window start must not exceed end")
        if (self.coalition_id is None) != (self.coalition_version is None):
            raise ValueError("coalition_id and coalition_version must be provided together")
        object.__setattr__(self, "assignment_version", int(self.assignment_version))
        object.__setattr__(self, "plan_version", _optional_int(self.plan_version))
        object.__setattr__(self, "coalition_id", _optional_string(self.coalition_id))
        object.__setattr__(self, "coalition_version", _optional_int(self.coalition_version))
        object.__setattr__(self, "member_role", str(self.member_role).strip().lower())
        object.__setattr__(self, "wave_id", int(self.wave_id))
        object.__setattr__(self, "required_resource_count", int(self.required_resource_count))
        object.__setattr__(self, "coordination_mode", str(self.coordination_mode).strip().lower())
        object.__setattr__(self, "activation_state", str(self.activation_state).strip().lower())
        authorization_scope = str(self.terminal_authorization_scope).strip().lower()
        if authorization_scope not in {"coalition", "per_primary"}:
            raise ValueError("terminal_authorization_scope must be coalition or per_primary")
        object.__setattr__(self, "terminal_authorization_scope", authorization_scope)
        object.__setattr__(
            self,
            "arrival_coordination_required",
            bool(self.arrival_coordination_required),
        )
        if self.arrival_window_start_s is not None:
            object.__setattr__(self, "arrival_window_start_s", float(self.arrival_window_start_s))
        if self.arrival_window_end_s is not None:
            object.__setattr__(self, "arrival_window_end_s", float(self.arrival_window_end_s))


@dataclass(frozen=True)
class IdentityClaim:
    """Simulated cooperative identity or friend tag claim."""

    platform_id: str
    claim_type: str
    auth_state: str
    associated_local_track_id: str | None = None
    center_px: np.ndarray | None = None
    bbox: tuple[float, float, float, float] | None = None
    timestamp: float = 0.0
    is_friend: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.platform_id:
            raise ValueError("platform_id must be non-empty")
        object.__setattr__(self, "center_px", _optional_vector(self.center_px, 2, "center_px"))
        object.__setattr__(self, "bbox", _optional_bbox(self.bbox))


@dataclass(frozen=True)
class ReconImageCue:
    """Image-plane cue produced by a secondary reconnaissance node.

    The cue is advisory evidence for a scoped set of local resources. It does
    not authorize terminal locking and cannot rewrite `global_track_id`.
    """

    cue_id: str
    producer_node_id: str
    timestamp: float
    image_frame_id: str
    global_track_id: str | None = None
    center_px: np.ndarray | None = None
    bbox: tuple[float, float, float, float] | None = None
    confidence: float = 1.0
    scoped_resource_ids: tuple[str, ...] = ()
    source_type: str = "secondary_recon"
    cue_position_ned: np.ndarray | None = None
    look_at_ned: np.ndarray | None = None
    gimbal_pointing_metadata: dict[str, Any] = field(default_factory=dict)
    cue_pointing_error_m: float | None = None
    cue_pointing_error_rad: float | None = None
    gimbal_track_error_px: float | None = None
    cue_source: str | None = None
    capability_class: str | None = None
    coverage_mode: str = "fixed_downlook_secondary"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.cue_id:
            raise ValueError("cue_id must be non-empty")
        if not self.producer_node_id:
            raise ValueError("producer_node_id must be non-empty")
        object.__setattr__(self, "timestamp", float(self.timestamp))
        object.__setattr__(self, "center_px", _optional_vector(self.center_px, 2, "center_px"))
        object.__setattr__(self, "bbox", _optional_bbox(self.bbox))
        object.__setattr__(self, "confidence", float(np.clip(self.confidence, 0.0, 1.0)))
        object.__setattr__(self, "scoped_resource_ids", _as_string_tuple(self.scoped_resource_ids))
        object.__setattr__(self, "source_type", str(self.source_type))
        object.__setattr__(self, "cue_position_ned", _optional_vector(self.cue_position_ned, 3, "cue_position_ned"))
        object.__setattr__(self, "look_at_ned", _optional_vector(self.look_at_ned, 3, "look_at_ned"))
        object.__setattr__(self, "gimbal_pointing_metadata", dict(self.gimbal_pointing_metadata))
        object.__setattr__(self, "cue_pointing_error_m", _finite_float_or_none(self.cue_pointing_error_m))
        object.__setattr__(self, "cue_pointing_error_rad", _finite_float_or_none(self.cue_pointing_error_rad))
        object.__setattr__(self, "gimbal_track_error_px", _finite_float_or_none(self.gimbal_track_error_px))
        object.__setattr__(self, "cue_source", _optional_string(self.cue_source))
        object.__setattr__(self, "capability_class", _optional_string(self.capability_class))
        object.__setattr__(self, "coverage_mode", str(self.coverage_mode or "fixed_downlook_secondary"))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ProjectionResult:
    """Image-plane projection and covariance for one global track."""

    global_track_id: str
    category: str
    pixel: np.ndarray | None
    covariance_px: np.ndarray | None
    depth: float
    valid: bool
    reason: str = ""
    predicted_px_velocity: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=float))
    image_size: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "pixel", _optional_vector(self.pixel, 2, "pixel"))
        if self.covariance_px is not None:
            object.__setattr__(
                self, "covariance_px", _as_matrix(self.covariance_px, (2, 2), "covariance_px")
            )
        object.__setattr__(
            self, "predicted_px_velocity", _as_vector(self.predicted_px_velocity, 2, "predicted_px_velocity")
        )
        object.__setattr__(self, "image_size", _optional_image_size(self.image_size))


@dataclass(frozen=True)
class CostBreakdown:
    """Per-pair cost terms used to build the association matrix."""

    global_track_id: str
    local_track_id: str
    total_cost: float
    mahalanobis_d2: float
    rate_cost: float
    category_cost: float
    friend_cost: float
    quality_cost: float
    gated: bool
    friend_conflict_state: str = "none"
    recon_cue_cost: float = 0.0
    projected_px: tuple[float, float] | None = None
    bbox_center_px: tuple[float, float] | None = None
    pixel_error_px: float | None = None
    measurement_age_s: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "projected_px", _optional_pair_tuple(self.projected_px))
        object.__setattr__(self, "bbox_center_px", _optional_pair_tuple(self.bbox_center_px))
        object.__setattr__(self, "pixel_error_px", _finite_float_or_none(self.pixel_error_px))
        object.__setattr__(self, "measurement_age_s", _finite_float_or_none(self.measurement_age_s))

    def to_log_record(self) -> dict[str, Any]:
        """Return a JSON-friendly per-pair geometry/cost log record."""

        return {
            "global_track_id": self.global_track_id,
            "local_track_id": self.local_track_id,
            "projected_px": list(self.projected_px) if self.projected_px is not None else None,
            "bbox_center_px": list(self.bbox_center_px) if self.bbox_center_px is not None else None,
            "pixel_error_px": self.pixel_error_px,
            "reprojection_error": self.pixel_error_px,
            "reprojection_error_px": self.pixel_error_px,
            "mahalanobis_d2": _finite_float_or_none(self.mahalanobis_d2),
            "gate_pass": bool(self.gated),
            "total_cost": _finite_float_or_none(self.total_cost),
            "rate_cost": _finite_float_or_none(self.rate_cost),
            "category_cost": _finite_float_or_none(self.category_cost),
            "friend_cost": _finite_float_or_none(self.friend_cost),
            "quality_cost": _finite_float_or_none(self.quality_cost),
            "recon_cue_cost": _finite_float_or_none(self.recon_cue_cost),
            "friend_conflict_state": self.friend_conflict_state,
            "measurement_age_s": self.measurement_age_s,
        }


@dataclass(frozen=True)
class CostMatrixResult:
    """Cost matrix plus explainable per-cell terms."""

    global_track_ids: list[str]
    local_track_ids: list[str]
    costs: np.ndarray
    breakdowns: dict[tuple[str, str], CostBreakdown]


@dataclass(frozen=True)
class TerminalAssociation:
    """Conservative terminal association output.

    `assigned_global_track_id` is copied from the center assignment. The local
    node reports a local visual candidate and decision state; it does not create
    or rewrite global IDs.
    """

    assigned_global_track_id: str
    local_track_id: str | None
    association_confidence: float
    ambiguity_score: float
    friend_conflict_state: str
    decision_state: str
    assignment_version: int
    reason: str = ""
    candidate_costs: list[tuple[str, float]] = field(default_factory=list)
    recon_cue_used: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    plan_id: str | None = None
    plan_version: int | None = None
    authorization_state: str = "authorized"
    resource_id: str | None = None
    coalition_id: str | None = None
    coalition_version: int | None = None
    member_role: str = "primary"
    wave_id: int = 0
    required_resource_count: int = 1
    coordination_mode: str = "independent"
    arrival_window_start_s: float | None = None
    arrival_window_end_s: float | None = None
    activation_state: str = "active"
    association_source: str = "geometric_detect"
    measurement_timestamp: float | None = None
    arrival_timestamp: float | None = None
    exposure_timestamp: float | None = None
    measurement_age_s: float | None = None
    prediction_age_s: float | None = None
    local_track_state: str | None = None
    truth_identity_used: bool = False
    mot_history_length: int | None = None
    track_transition_state: str = "unknown"
    track_reset_reason: str | None = None
    detection_source: str = "unknown"
    bbox_edge_clipped: bool = False
    bbox_edge_clip_sides: tuple[str, ...] = ()
    camera_geometry: CameraGeometryEvidence | None = None
    duplicate_terminal_lock_risk: bool = False
    terminal_authorization_scope: str = "coalition"
    arrival_coordination_required: bool = True

    def __post_init__(self) -> None:
        if not self.assigned_global_track_id:
            raise ValueError("assigned_global_track_id must be non-empty")
        if int(self.required_resource_count) < 1:
            raise ValueError("required_resource_count must be at least 1")
        if int(self.wave_id) < 0:
            raise ValueError("wave_id must be non-negative")
        if (
            self.arrival_window_start_s is not None
            and self.arrival_window_end_s is not None
            and float(self.arrival_window_start_s) > float(self.arrival_window_end_s)
        ):
            raise ValueError("arrival window start must not exceed end")
        if (self.coalition_id is None) != (self.coalition_version is None):
            raise ValueError("coalition_id and coalition_version must be provided together")
        object.__setattr__(self, "assignment_version", int(self.assignment_version))
        object.__setattr__(self, "plan_version", _optional_int(self.plan_version))
        object.__setattr__(self, "coalition_id", _optional_string(self.coalition_id))
        object.__setattr__(self, "coalition_version", _optional_int(self.coalition_version))
        object.__setattr__(self, "member_role", str(self.member_role).strip().lower())
        object.__setattr__(self, "wave_id", int(self.wave_id))
        object.__setattr__(self, "required_resource_count", int(self.required_resource_count))
        object.__setattr__(self, "coordination_mode", str(self.coordination_mode).strip().lower())
        object.__setattr__(self, "activation_state", str(self.activation_state).strip().lower())
        association_source = str(self.association_source).strip()
        if not association_source:
            raise ValueError("association_source must be non-empty")
        local_track_state = (
            str(self.local_track_state).strip().lower()
            if self.local_track_state is not None
            else ("measured" if self.local_track_id is not None else "lost")
        )
        if local_track_state not in {"measured", "predicted", "lost"}:
            raise ValueError("local_track_state must be measured, predicted, or lost")
        if local_track_state in {"predicted", "lost"} and self.decision_state in {
            "locked",
            "registered",
        }:
            raise ValueError("predicted or lost local tracks cannot produce a locked association")
        if bool(self.truth_identity_used):
            raise ValueError("TerminalAssociation online decisions cannot use truth identity")
        mot_history_length = _optional_int(self.mot_history_length)
        if mot_history_length is not None and mot_history_length < 0:
            raise ValueError("mot_history_length must be non-negative")
        transition = str(self.track_transition_state).strip().lower()
        if transition not in {"initialized", "continued", "switched", "reacquired", "reset", "lost", "unknown"}:
            raise ValueError("invalid track_transition_state")
        clip_sides = _normalized_clip_sides(self.bbox_edge_clip_sides)
        measurement_timestamp = _finite_float_or_none(self.measurement_timestamp)
        arrival_timestamp = _finite_float_or_none(self.arrival_timestamp)
        exposure_timestamp = _finite_float_or_none(self.exposure_timestamp)
        if exposure_timestamp is None:
            exposure_timestamp = measurement_timestamp
        measurement_age_s = _finite_float_or_none(self.measurement_age_s)
        prediction_age_s = _finite_float_or_none(self.prediction_age_s)
        if prediction_age_s is not None and prediction_age_s < 0.0:
            raise ValueError("prediction_age_s must be non-negative")
        object.__setattr__(self, "association_source", association_source)
        object.__setattr__(self, "measurement_timestamp", measurement_timestamp)
        object.__setattr__(self, "arrival_timestamp", arrival_timestamp)
        object.__setattr__(self, "exposure_timestamp", exposure_timestamp)
        object.__setattr__(self, "measurement_age_s", measurement_age_s)
        object.__setattr__(self, "prediction_age_s", prediction_age_s)
        object.__setattr__(self, "local_track_state", local_track_state)
        object.__setattr__(self, "truth_identity_used", False)
        object.__setattr__(self, "mot_history_length", mot_history_length)
        object.__setattr__(self, "track_transition_state", transition)
        object.__setattr__(self, "track_reset_reason", _optional_string(self.track_reset_reason))
        object.__setattr__(self, "detection_source", str(self.detection_source or "unknown"))
        object.__setattr__(self, "bbox_edge_clipped", bool(self.bbox_edge_clipped or clip_sides))
        object.__setattr__(self, "bbox_edge_clip_sides", clip_sides)
        authorization_scope = str(self.terminal_authorization_scope).strip().lower()
        if authorization_scope not in {"coalition", "per_primary"}:
            raise ValueError("terminal_authorization_scope must be coalition or per_primary")
        object.__setattr__(self, "terminal_authorization_scope", authorization_scope)
        object.__setattr__(
            self,
            "arrival_coordination_required",
            bool(self.arrival_coordination_required),
        )
        duplicate_terminal_lock_risk = bool(
            self.duplicate_terminal_lock_risk
            or self.metadata.get("duplicate_terminal_lock_risk", False)
        )
        object.__setattr__(self, "duplicate_terminal_lock_risk", duplicate_terminal_lock_risk)
        if self.arrival_window_start_s is not None:
            object.__setattr__(self, "arrival_window_start_s", float(self.arrival_window_start_s))
        if self.arrival_window_end_s is not None:
            object.__setattr__(self, "arrival_window_end_s", float(self.arrival_window_end_s))
        metadata = dict(self.metadata)
        metadata.update(
            {
                "association_source": association_source,
                "measurement_timestamp": measurement_timestamp,
                "arrival_timestamp": arrival_timestamp,
                "exposure_timestamp": exposure_timestamp,
                "measurement_age_s": measurement_age_s,
                "prediction_age_s": prediction_age_s,
                "local_track_state": local_track_state,
                "truth_identity_used": False,
                "association_confidence": float(self.association_confidence),
                "association_rejection_reason": self.reason,
                "mot_history_length": mot_history_length,
                "track_transition_state": transition,
                "track_reset_reason": self.track_reset_reason,
                "detection_source": self.detection_source,
                "bbox_edge_clipped": bool(self.bbox_edge_clipped or clip_sides),
                "bbox_edge_clip_sides": list(clip_sides),
                "camera_geometry": (
                    self.camera_geometry.to_metadata()
                    if self.camera_geometry is not None
                    else {
                        "geometry_valid": False,
                        "geometry_source": "unavailable",
                        "geometry_unavailable_reasons": ["camera_geometry_not_provided"],
                    }
                ),
                "duplicate_terminal_lock_risk": duplicate_terminal_lock_risk,
                "terminal_authorization_scope": authorization_scope,
                "arrival_coordination_required": bool(
                    self.arrival_coordination_required
                ),
            }
        )
        object.__setattr__(self, "metadata", metadata)

    def to_runtime_record(self) -> dict[str, Any]:
        """Return the stable online association contract for main/D6 sinks."""

        return {
            "association_source": self.association_source,
            "assigned_global_track_id": self.assigned_global_track_id,
            "local_track_id": self.local_track_id,
            "local_track_state": self.local_track_state,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "exposure_timestamp": self.exposure_timestamp,
            "measurement_age_s": self.measurement_age_s,
            "prediction_age_s": self.prediction_age_s,
            "truth_identity_used": False,
            "association_confidence": float(self.association_confidence),
            "ambiguity_score": float(self.ambiguity_score),
            "decision_state": self.decision_state,
            "rejection_reason": self.reason,
            "friend_conflict_state": self.friend_conflict_state,
            "duplicate_terminal_lock_risk": self.duplicate_terminal_lock_risk,
            "mot_history_length": self.mot_history_length,
            "track_transition_state": self.track_transition_state,
            "track_reset_reason": self.track_reset_reason,
            "detection_source": self.detection_source,
            "bbox_edge_clipped": self.bbox_edge_clipped,
            "bbox_edge_clip_sides": list(self.bbox_edge_clip_sides),
            "camera_geometry": (
                self.camera_geometry.to_metadata()
                if self.camera_geometry is not None
                else self.metadata.get("camera_geometry")
            ),
            "assignment_version": self.assignment_version,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "resource_id": self.resource_id,
            "terminal_authorization_scope": self.terminal_authorization_scope,
            "arrival_coordination_required": self.arrival_coordination_required,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TerminalObservation:
    """Cross-node terminal observation summary.

    This is a passive bus payload. It can carry local visual evidence,
    terminal association output, identity claims, and secondary reconnaissance
    cues, but it does not own or alter any `global_track_id`.
    """

    resource_id: str
    source_node_id: str
    link_type: str
    timestamp: float
    local_track: LocalVisualTrack | None = None
    terminal_association: TerminalAssociation | None = None
    identity_claims: tuple[IdentityClaim, ...] = ()
    recon_image_cues: tuple[ReconImageCue, ...] = ()
    camera_id: str | None = None
    frame_id: str | None = None
    arrival_timestamp: float | None = None
    measurement_timestamp: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resource_id:
            raise ValueError("resource_id must be non-empty")
        if not self.source_node_id:
            raise ValueError("source_node_id must be non-empty")
        if not self.link_type:
            raise ValueError("link_type must be non-empty")
        if (
            self.local_track is None
            and self.terminal_association is None
            and not self.identity_claims
            and not self.recon_image_cues
        ):
            raise ValueError("TerminalObservation must carry at least one payload")
        object.__setattr__(self, "timestamp", float(self.timestamp))
        measurement_timestamp = self.measurement_timestamp
        if measurement_timestamp is None and self.local_track is not None:
            measurement_timestamp = self.local_track.timestamp
        if measurement_timestamp is None and self.terminal_association is not None:
            measurement_timestamp = self.terminal_association.measurement_timestamp
        if measurement_timestamp is None:
            measurement_timestamp = self.timestamp
        arrival_timestamp = self.arrival_timestamp
        if arrival_timestamp is None and self.terminal_association is not None:
            arrival_timestamp = self.terminal_association.arrival_timestamp
        if arrival_timestamp is None:
            arrival_timestamp = self.timestamp
        object.__setattr__(self, "measurement_timestamp", float(measurement_timestamp))
        object.__setattr__(self, "arrival_timestamp", float(arrival_timestamp))
        object.__setattr__(self, "identity_claims", tuple(self.identity_claims))
        object.__setattr__(self, "recon_image_cues", tuple(self.recon_image_cues))
        metadata = dict(self.metadata)
        metadata.update(
            {
                "measurement_timestamp": float(measurement_timestamp),
                "arrival_timestamp": float(arrival_timestamp),
                "truth_identity_used": False,
            }
        )
        object.__setattr__(self, "metadata", metadata)

    def to_runtime_record(self) -> dict[str, Any]:
        """Flatten this passive bus payload for runtime/D6 consumption."""

        if self.terminal_association is not None:
            record = self.terminal_association.to_runtime_record()
            runtime_metadata = dict(self.terminal_association.metadata)
            runtime_metadata.update(self.metadata)
        else:
            state = self.local_track.local_track_state if self.local_track is not None else "lost"
            prediction_age_s = self.local_track.prediction_age_s if self.local_track is not None else None
            local_evidence = (
                self.local_track.to_evidence_metadata() if self.local_track is not None else {}
            )
            record = {
                "association_source": self.metadata.get("association_source", self.link_type),
                "assigned_global_track_id": None,
                "local_track_id": self.local_track.local_track_id if self.local_track is not None else None,
                "local_track_state": state,
                "measurement_age_s": max(0.0, self.arrival_timestamp - self.measurement_timestamp),
                "prediction_age_s": prediction_age_s,
                "truth_identity_used": False,
                "association_confidence": 0.0,
                "ambiguity_score": 1.0,
                "decision_state": "reacquire" if state != "measured" else "unassociated",
                "rejection_reason": self.metadata.get("association_rejection_reason", "no_global_binding"),
                "friend_conflict_state": "none",
                "duplicate_terminal_lock_risk": False,
                "mot_history_length": local_evidence.get("mot_history_length"),
                "track_transition_state": local_evidence.get("track_transition_state", "lost"),
                "track_reset_reason": local_evidence.get("track_reset_reason"),
                "detection_source": local_evidence.get("detection_source", "unavailable"),
                "bbox_edge_clipped": local_evidence.get("bbox_edge_clipped", False),
                "bbox_edge_clip_sides": local_evidence.get("bbox_edge_clip_sides", []),
                "camera_geometry": local_evidence.get("camera_geometry"),
            }
            runtime_metadata = dict(self.metadata)
            runtime_metadata["local_visual_evidence"] = local_evidence
        record.update(
            {
                "resource_id": self.resource_id,
                "source_node_id": self.source_node_id,
                "link_type": self.link_type,
                "camera_id": self.camera_id,
                "frame_id": self.frame_id,
                "measurement_timestamp": self.measurement_timestamp,
                "arrival_timestamp": self.arrival_timestamp,
                "truth_identity_used": False,
                "metadata": runtime_metadata,
            }
        )
        return record


@dataclass(frozen=True)
class CrossViewAssociation:
    """Passive cross-view evidence grouped by an existing global track ID.

    `duplicate_terminal_lock_risk` is only a signal for D3/D4 arbitration. D5
    still does not change assignments or rewrite global IDs.
    """

    global_track_id: str
    supporting_resource_ids: tuple[str, ...]
    local_track_ids: tuple[str, ...]
    ambiguity_score: float
    duplicate_terminal_lock_risk: bool
    source_node_id: str
    link_type: str
    source_node_ids: tuple[str, ...] = ()
    link_types: tuple[str, ...] = ()
    decision_states: tuple[str, ...] = ()
    association_confidences: tuple[float, ...] = ()
    friend_conflict_states: tuple[str, ...] = ()
    recon_cue_used_count: int = 0
    support_count: int = 0
    duplicate_lock_resource_ids: tuple[str, ...] = ()
    duplicate_local_track_ids: tuple[str, ...] = ()
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    planned_cooperative_lock: bool = False
    coalition_id: str | None = None
    coalition_version: int | None = None
    required_resource_count: int = 1
    coordination_mode: str = "independent"
    excess_lock_resource_ids: tuple[str, ...] = ()
    coalition_conflict_state: str = "none"

    def __post_init__(self) -> None:
        if not self.global_track_id:
            raise ValueError("global_track_id must be non-empty")
        if not self.source_node_id:
            raise ValueError("source_node_id must be non-empty")
        if not self.link_type:
            raise ValueError("link_type must be non-empty")
        object.__setattr__(self, "supporting_resource_ids", _as_string_tuple(self.supporting_resource_ids))
        object.__setattr__(self, "local_track_ids", _as_string_tuple(self.local_track_ids))
        object.__setattr__(self, "source_node_ids", _as_string_tuple(self.source_node_ids))
        object.__setattr__(self, "link_types", _as_string_tuple(self.link_types))
        object.__setattr__(self, "decision_states", _as_string_tuple(self.decision_states))
        object.__setattr__(self, "friend_conflict_states", _as_string_tuple(self.friend_conflict_states))
        object.__setattr__(
            self, "duplicate_lock_resource_ids", _as_string_tuple(self.duplicate_lock_resource_ids)
        )
        object.__setattr__(self, "duplicate_local_track_ids", _as_string_tuple(self.duplicate_local_track_ids))
        object.__setattr__(self, "excess_lock_resource_ids", _as_string_tuple(self.excess_lock_resource_ids))
        object.__setattr__(
            self,
            "association_confidences",
            tuple(float(np.clip(value, 0.0, 1.0)) for value in self.association_confidences),
        )
        object.__setattr__(self, "ambiguity_score", float(np.clip(self.ambiguity_score, 0.0, 1.0)))
        object.__setattr__(self, "recon_cue_used_count", int(self.recon_cue_used_count))
        object.__setattr__(self, "support_count", int(self.support_count))
        object.__setattr__(self, "coalition_id", _optional_string(self.coalition_id))
        object.__setattr__(self, "coalition_version", _optional_int(self.coalition_version))
        object.__setattr__(self, "required_resource_count", int(self.required_resource_count))
        if self.required_resource_count < 1:
            raise ValueError("required_resource_count must be at least 1")
        object.__setattr__(self, "coordination_mode", str(self.coordination_mode).strip().lower())
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class CrossPeerAssociationHypothesis:
    """Metadata-only cross-peer visual association hypothesis.

    This is an evidence packet for D4 distributed decisions. It can reference
    existing assigned global IDs, but it is not a new global track and does not
    authorize assignment changes.
    """

    hypothesis_id: str
    resource_id: str
    local_track_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    frame_id: str
    covariance_px: np.ndarray | None
    participant_tracklet_keys: tuple[str, ...]
    supporting_resource_ids: tuple[str, ...]
    local_track_ids: tuple[str, ...]
    frame_ids: tuple[str, ...]
    assigned_global_track_id: str | None = None
    assigned_global_track_ids: tuple[str, ...] = ()
    stale_assigned_global_track_ids: tuple[str, ...] = ()
    support_count: int = 0
    total_cost: float = 0.0
    confidence: float = 0.0
    ambiguity_score: float = 1.0
    max_time_skew_s: float = 0.0
    category: str = "unknown"
    support_state: str = "hypothesis_only"
    duplicate_terminal_lock_risk: bool = False
    global_track_id_conflict: bool = False
    local_id_conflict: bool = False
    friend_conflict_state: str = "none"
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.hypothesis_id:
            raise ValueError("hypothesis_id must be non-empty")
        if not self.resource_id:
            raise ValueError("resource_id must be non-empty")
        if not self.local_track_id:
            raise ValueError("local_track_id must be non-empty")
        if not self.frame_id:
            raise ValueError("frame_id must be non-empty")
        object.__setattr__(self, "measurement_timestamp", float(self.measurement_timestamp))
        object.__setattr__(self, "arrival_timestamp", float(self.arrival_timestamp))
        object.__setattr__(self, "covariance_px", _optional_matrix(self.covariance_px, (2, 2), "covariance_px"))
        if self.covariance_px is None:
            raise ValueError("CrossPeerAssociationHypothesis requires covariance_px")
        object.__setattr__(self, "participant_tracklet_keys", _as_string_tuple(self.participant_tracklet_keys))
        object.__setattr__(self, "supporting_resource_ids", _as_string_tuple(self.supporting_resource_ids))
        object.__setattr__(self, "local_track_ids", _as_string_tuple(self.local_track_ids))
        object.__setattr__(self, "frame_ids", _as_string_tuple(self.frame_ids))
        assigned_id = _optional_string(self.assigned_global_track_id)
        assigned_ids = tuple(dict.fromkeys(_as_string_tuple(self.assigned_global_track_ids)))
        if assigned_id is not None and assigned_id not in assigned_ids:
            assigned_ids = assigned_ids + (assigned_id,)
        if assigned_id is None and len(assigned_ids) == 1:
            assigned_id = assigned_ids[0]
        if len(assigned_ids) > 1:
            assigned_id = None
        object.__setattr__(self, "assigned_global_track_id", assigned_id)
        object.__setattr__(self, "assigned_global_track_ids", assigned_ids)
        object.__setattr__(
            self, "stale_assigned_global_track_ids", _as_string_tuple(self.stale_assigned_global_track_ids)
        )
        object.__setattr__(self, "support_count", int(self.support_count))
        object.__setattr__(self, "total_cost", float(self.total_cost))
        object.__setattr__(self, "confidence", float(np.clip(self.confidence, 0.0, 1.0)))
        object.__setattr__(self, "ambiguity_score", float(np.clip(self.ambiguity_score, 0.0, 1.0)))
        object.__setattr__(self, "max_time_skew_s", max(0.0, float(self.max_time_skew_s)))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class DistributedTerminalAssociation:
    """Conservative distributed-mode terminal association summary.

    `assigned_global_track_id`, when present, is copied from current upstream
    assignment context. Missing or stale global IDs keep the output in
    `hypothesis_only` or `hold` states instead of `locked`.
    """

    association_id: str
    resource_id: str
    local_track_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    frame_id: str
    covariance_px: np.ndarray | None
    decision_state: str
    assigned_global_track_id: str | None = None
    participant_tracklet_keys: tuple[str, ...] = ()
    supporting_resource_ids: tuple[str, ...] = ()
    local_track_ids: tuple[str, ...] = ()
    hypotheses: tuple[CrossPeerAssociationHypothesis, ...] = ()
    selected_hypothesis_id: str | None = None
    association_confidence: float = 0.0
    ambiguity_score: float = 1.0
    duplicate_terminal_lock_risk: bool = False
    duplicate_lock_resource_ids: tuple[str, ...] = ()
    duplicate_local_track_ids: tuple[str, ...] = ()
    global_track_id_conflict: bool = False
    local_id_conflict: bool = False
    friend_conflict_state: str = "none"
    recommended_d4_action: str = "observe"
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.association_id:
            raise ValueError("association_id must be non-empty")
        if not self.resource_id:
            raise ValueError("resource_id must be non-empty")
        if not self.local_track_id:
            raise ValueError("local_track_id must be non-empty")
        if not self.frame_id:
            raise ValueError("frame_id must be non-empty")
        object.__setattr__(self, "measurement_timestamp", float(self.measurement_timestamp))
        object.__setattr__(self, "arrival_timestamp", float(self.arrival_timestamp))
        object.__setattr__(self, "covariance_px", _optional_matrix(self.covariance_px, (2, 2), "covariance_px"))
        if self.covariance_px is None:
            raise ValueError("DistributedTerminalAssociation requires covariance_px")
        object.__setattr__(self, "assigned_global_track_id", _optional_string(self.assigned_global_track_id))
        object.__setattr__(self, "participant_tracklet_keys", _as_string_tuple(self.participant_tracklet_keys))
        object.__setattr__(self, "supporting_resource_ids", _as_string_tuple(self.supporting_resource_ids))
        object.__setattr__(self, "local_track_ids", _as_string_tuple(self.local_track_ids))
        object.__setattr__(self, "hypotheses", tuple(self.hypotheses))
        object.__setattr__(self, "selected_hypothesis_id", _optional_string(self.selected_hypothesis_id))
        object.__setattr__(
            self, "association_confidence", float(np.clip(self.association_confidence, 0.0, 1.0))
        )
        object.__setattr__(self, "ambiguity_score", float(np.clip(self.ambiguity_score, 0.0, 1.0)))
        object.__setattr__(self, "duplicate_lock_resource_ids", _as_string_tuple(self.duplicate_lock_resource_ids))
        object.__setattr__(self, "duplicate_local_track_ids", _as_string_tuple(self.duplicate_local_track_ids))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class TerminalConsistencySummary:
    """Window/state summary for D4/D6 consumers.

    This summary is derived from one resource's terminal association stream and
    optional cross-view summaries. It is an advisory signal only; it does not
    create assignments or alter center-owned global track IDs.
    """

    resource_id: str
    assigned_global_track_id: str
    assignment_version: int
    timestamp: float
    decision_state: str
    consistency_state: str
    association_confidence: float
    ambiguity_score: float
    friend_conflict_state: str
    candidate_cost_margin: float
    recon_cue_used: bool
    terminal_lock_age_s: float
    consecutive_locked_frames: int
    consecutive_ambiguous_frames: int
    consecutive_hold_frames: int
    consecutive_reacquire_frames: int
    local_track_id: str | None = None
    previous_decision_state: str | None = None
    lock_lifecycle_state: str = "unknown"
    lost_lock_event: bool = False
    lock_reacquired_event: bool = False
    event_summary: str = ""
    competing_global_track_id: str | None = None
    local_best_conflicts_with_assignment: bool = False
    duplicate_terminal_lock_risk: bool = False
    duplicate_lock_resource_ids: tuple[str, ...] = ()
    duplicate_local_track_ids: tuple[str, ...] = ()
    cross_view_support_count: int = 0
    cross_view_supporting_resource_ids: tuple[str, ...] = ()
    cross_view_decision_states: tuple[str, ...] = ()
    recommended_d4_action: str = "observe"
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resource_id:
            raise ValueError("resource_id must be non-empty")
        if not self.assigned_global_track_id:
            raise ValueError("assigned_global_track_id must be non-empty")
        object.__setattr__(self, "timestamp", float(self.timestamp))
        object.__setattr__(
            self, "association_confidence", float(np.clip(self.association_confidence, 0.0, 1.0))
        )
        object.__setattr__(self, "ambiguity_score", float(np.clip(self.ambiguity_score, 0.0, 1.0)))
        object.__setattr__(self, "terminal_lock_age_s", max(0.0, float(self.terminal_lock_age_s)))
        object.__setattr__(self, "consecutive_locked_frames", int(self.consecutive_locked_frames))
        object.__setattr__(self, "consecutive_ambiguous_frames", int(self.consecutive_ambiguous_frames))
        object.__setattr__(self, "consecutive_hold_frames", int(self.consecutive_hold_frames))
        object.__setattr__(self, "consecutive_reacquire_frames", int(self.consecutive_reacquire_frames))
        object.__setattr__(self, "duplicate_lock_resource_ids", _as_string_tuple(self.duplicate_lock_resource_ids))
        object.__setattr__(self, "duplicate_local_track_ids", _as_string_tuple(self.duplicate_local_track_ids))
        object.__setattr__(
            self, "cross_view_supporting_resource_ids", _as_string_tuple(self.cross_view_supporting_resource_ids)
        )
        object.__setattr__(self, "cross_view_decision_states", _as_string_tuple(self.cross_view_decision_states))
        object.__setattr__(self, "cross_view_support_count", int(self.cross_view_support_count))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_metadata(self) -> dict[str, Any]:
        """Return D4/D6/D7-consumable consistency metadata."""

        return {
            "resource_id": self.resource_id,
            "assigned_global_track_id": self.assigned_global_track_id,
            "assignment_version": self.assignment_version,
            "timestamp": self.timestamp,
            "decision_state": self.decision_state,
            "consistency_state": self.consistency_state,
            "association_confidence": self.association_confidence,
            "ambiguity_score": self.ambiguity_score,
            "friend_conflict_state": self.friend_conflict_state,
            "candidate_cost_margin": _finite_float_or_none(self.candidate_cost_margin),
            "recon_cue_used": self.recon_cue_used,
            "terminal_lock_age_s": self.terminal_lock_age_s,
            "consecutive_locked_frames": self.consecutive_locked_frames,
            "consecutive_ambiguous_frames": self.consecutive_ambiguous_frames,
            "consecutive_hold_frames": self.consecutive_hold_frames,
            "consecutive_reacquire_frames": self.consecutive_reacquire_frames,
            "local_track_id": self.local_track_id,
            "previous_decision_state": self.previous_decision_state,
            "lock_lifecycle_state": self.lock_lifecycle_state,
            "lost_lock_event": self.lost_lock_event,
            "lock_reacquired_event": self.lock_reacquired_event,
            "event_summary": self.event_summary,
            "competing_global_track_id": self.competing_global_track_id,
            "local_best_conflicts_with_assignment": self.local_best_conflicts_with_assignment,
            "duplicate_terminal_lock_risk": self.duplicate_terminal_lock_risk,
            "duplicate_lock_resource_ids": list(self.duplicate_lock_resource_ids),
            "duplicate_local_track_ids": list(self.duplicate_local_track_ids),
            "cross_view_support_count": self.cross_view_support_count,
            "cross_view_supporting_resource_ids": list(self.cross_view_supporting_resource_ids),
            "cross_view_decision_states": list(self.cross_view_decision_states),
            "recommended_d4_action": self.recommended_d4_action,
            "reason": self.reason,
            "consistency_window_key": f"{self.resource_id}:{self.assigned_global_track_id}",
            "assignment_version_resets_window": False,
            "projection_valid": self.metadata.get("projection_valid"),
            "reprojection_error": self.metadata.get("reprojection_error"),
            "reprojection_error_px": self.metadata.get("reprojection_error_px"),
            "camera_pose_source": self.metadata.get("camera_pose_source"),
            "calibration_health": self.metadata.get("calibration_health"),
            "drift_warning": self.metadata.get("drift_warning"),
            "metadata": dict(self.metadata),
        }
