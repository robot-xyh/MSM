"""AirSim ComputerVision geometry helpers for D5 validation.

Online association in this module uses only track state, camera geometry, and
image-space detections. AirSim object IDs are accepted only by the offline
evaluation helper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Mapping

import numpy as np

from .associator import AssociationConfig, TerminalAssociator
from .models import CameraModel, CostMatrixResult, GlobalTrack, LocalVisualTrack


AIRSIM_BODY_TO_OPENCV_CAMERA = np.array(
    [
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 0.0],
    ],
    dtype=float,
)


@dataclass(frozen=True)
class AirSimIntrinsics:
    width: int
    height: int
    fov_degrees: float
    K: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "K", np.asarray(self.K, dtype=float).reshape(3, 3).copy())


@dataclass(frozen=True)
class GeometricAssociationPair:
    track_id: str
    local_track_id: str
    projected_px: tuple[float, float] | None
    bbox_center_px: tuple[float, float]
    pixel_error: float | None
    mahalanobis_d2: float
    gate_pass: bool
    assignment_selected: bool = False
    total_cost: float | None = None
    friend_conflict_state: str = "none"
    measurement_age_s: float | None = None
    duplicate_terminal_lock_risk: bool = False

    def to_log_record(
        self,
        *,
        frame_id: str | None = None,
        timestamp: float | None = None,
        resource_id: str | None = None,
        camera_id: str | None = None,
        duplicate_terminal_lock_risk: bool | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a JSON-friendly AirSim geometry log record."""

        duplicate_risk = (
            self.duplicate_terminal_lock_risk
            if duplicate_terminal_lock_risk is None
            else bool(duplicate_terminal_lock_risk)
        )
        record = {
            "resource_id": resource_id,
            "camera_id": camera_id,
            "frame_id": frame_id,
            "timestamp": timestamp,
            "global_track_id": self.track_id,
            "local_track_id": self.local_track_id,
            "projected_px": list(self.projected_px) if self.projected_px is not None else None,
            "bbox_center_px": list(self.bbox_center_px),
            "pixel_error_px": _finite_or_none(self.pixel_error),
            "mahalanobis_d2": _finite_or_none(self.mahalanobis_d2),
            "gate_pass": bool(self.gate_pass),
            "assignment_selected": bool(self.assignment_selected),
            "total_cost": _finite_or_none(self.total_cost),
            "friend_conflict_state": self.friend_conflict_state,
            "measurement_age_s": _finite_or_none(self.measurement_age_s),
            "duplicate_terminal_lock_risk": duplicate_risk,
        }
        if metadata:
            record["metadata"] = dict(metadata)
        return record


@dataclass(frozen=True)
class GeometricAssociationResult:
    frame_id: str | None
    timestamp: float | None
    pairs: tuple[GeometricAssociationPair, ...]
    assignments: dict[str, str]
    ambiguous_count: int
    cost_matrix: CostMatrixResult

    def to_log_records(
        self,
        *,
        resource_id: str | None = None,
        camera_id: str | None = None,
        duplicate_terminal_lock_risk_by_track_id: Mapping[str, bool] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Return JSON-friendly per-pair geometry records for JSONL/CSV sinks."""

        duplicate_risk_by_track = dict(duplicate_terminal_lock_risk_by_track_id or {})
        return tuple(
            pair.to_log_record(
                frame_id=self.frame_id,
                timestamp=self.timestamp,
                resource_id=resource_id,
                camera_id=camera_id,
                duplicate_terminal_lock_risk=duplicate_risk_by_track.get(pair.track_id),
                metadata=metadata,
            )
            for pair in self.pairs
        )


@dataclass(frozen=True)
class OfflineAssociationMetrics:
    association_accuracy: float | None
    id_mismatch_count: int
    evaluated_count: int
    ambiguous_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


def intrinsics_from_capture_settings(
    capture_settings: Mapping[str, Any],
    *,
    default_width: int = 640,
    default_height: int = 480,
    default_fov_degrees: float = 90.0,
) -> AirSimIntrinsics:
    """Build OpenCV K from AirSim Width/Height/FOV_Degrees settings."""

    width = int(capture_settings.get("Width", default_width))
    height = int(capture_settings.get("Height", default_height))
    fov_degrees = float(capture_settings.get("FOV_Degrees", default_fov_degrees))
    return intrinsics_from_width_height_fov(width, height, fov_degrees)


def intrinsics_from_width_height_fov(width: int, height: int, fov_degrees: float) -> AirSimIntrinsics:
    if width <= 0 or height <= 0:
        raise ValueError("camera width and height must be positive")
    if not 0.0 < float(fov_degrees) < 180.0:
        raise ValueError("FOV_Degrees must be in (0, 180)")
    focal = float(width) / (2.0 * math.tan(math.radians(float(fov_degrees)) * 0.5))
    K = np.array(
        [
            [focal, 0.0, float(width) * 0.5],
            [0.0, focal, float(height) * 0.5],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    return AirSimIntrinsics(width=int(width), height=int(height), fov_degrees=float(fov_degrees), K=K)


def camera_model_from_airsim_camera_info(
    camera_info: Any,
    *,
    measurement_sigma_px: float = 8.0,
) -> CameraModel:
    """Convert `AirSimCameraInfo`-like metadata into D5 `CameraModel`."""

    K = np.array(
        [
            [float(camera_info.fx), 0.0, float(camera_info.cx)],
            [0.0, float(camera_info.fy), float(camera_info.cy)],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    R = np.asarray(camera_info.rotation_world_to_camera, dtype=float).reshape(3, 3)
    position = np.asarray(camera_info.position_ned, dtype=float).reshape(3)
    t = -R @ position
    return CameraModel(
        K=K,
        R=R,
        t=t,
        image_size=(int(camera_info.width), int(camera_info.height)),
        measurement_cov=np.eye(2, dtype=float) * float(measurement_sigma_px) ** 2,
    )


def rotation_world_to_opencv_camera_from_quaternion(
    orientation: Any,
    *,
    airsim_body_to_opencv_camera: np.ndarray = AIRSIM_BODY_TO_OPENCV_CAMERA,
) -> np.ndarray:
    """Return world/NED to OpenCV camera rotation from an AirSim quaternion.

    AirSim pose orientation is treated as body/camera-to-world. The fixed body
    to OpenCV transform maps AirSim camera body axes (forward, right, down) to
    OpenCV optical axes (right, down, forward).
    """

    body_to_world = quaternion_to_rotation_matrix(orientation)
    world_to_body = body_to_world.T
    return np.asarray(airsim_body_to_opencv_camera, dtype=float).reshape(3, 3) @ world_to_body


def quaternion_to_rotation_matrix(orientation: Any) -> np.ndarray:
    w = float(getattr(orientation, "w_val", getattr(orientation, "w", 1.0)))
    x = float(getattr(orientation, "x_val", getattr(orientation, "x", 0.0)))
    y = float(getattr(orientation, "y_val", getattr(orientation, "y", 0.0)))
    z = float(getattr(orientation, "z_val", getattr(orientation, "z", 0.0)))
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if norm <= 0.0:
        raise ValueError("quaternion norm must be positive")
    w, x, y, z = w / norm, x / norm, y / norm, z / norm
    return np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=float,
    )


def associate_tracks_to_detections_geometrically(
    global_tracks: Iterable[GlobalTrack],
    local_tracks: Iterable[LocalVisualTrack],
    camera: CameraModel,
    *,
    config: AssociationConfig | None = None,
    timestamp: float | None = None,
    frame_id: str | None = None,
) -> GeometricAssociationResult:
    """Associate tracks to bbox centers without using truth/detection IDs."""

    associator = TerminalAssociator(config=config)
    track_list = list(global_tracks)
    local_list = list(local_tracks)
    projections = associator.project_tracks_to_image(track_list, camera, timestamp=timestamp)
    cost_result = associator.build_cost_matrix(projections, local_list, current_time=timestamp, frame_id=frame_id)
    selected = _hungarian_like_assignments(cost_result.costs, max_cost=associator.config.cost_inf)
    assignments = {
        cost_result.global_track_ids[row]: cost_result.local_track_ids[col]
        for row, col in selected
    }

    selected_pairs = {
        (cost_result.global_track_ids[row], cost_result.local_track_ids[col])
        for row, col in selected
    }
    pairs: list[GeometricAssociationPair] = []
    for track_id in cost_result.global_track_ids:
        projection = projections[track_id]
        for local in local_list:
            breakdown = cost_result.breakdowns[(track_id, local.local_track_id)]
            projected = None
            pixel_error = None
            if projection.pixel is not None:
                projected = (float(projection.pixel[0]), float(projection.pixel[1]))
                pixel_error = float(np.linalg.norm(local.center_px - projection.pixel))
            pairs.append(
                GeometricAssociationPair(
                    track_id=track_id,
                    local_track_id=local.local_track_id,
                    projected_px=projected,
                    bbox_center_px=(float(local.center_px[0]), float(local.center_px[1])),
                    pixel_error=pixel_error,
                    mahalanobis_d2=float(breakdown.mahalanobis_d2),
                    gate_pass=bool(breakdown.gated),
                    assignment_selected=(track_id, local.local_track_id) in selected_pairs,
                    total_cost=breakdown.total_cost,
                    friend_conflict_state=breakdown.friend_conflict_state,
                    measurement_age_s=breakdown.measurement_age_s,
                )
            )

    ambiguous_count = _ambiguous_track_count(cost_result, associator.config)
    return GeometricAssociationResult(
        frame_id=frame_id,
        timestamp=timestamp,
        pairs=tuple(pairs),
        assignments=assignments,
        ambiguous_count=ambiguous_count,
        cost_matrix=cost_result,
    )


def evaluate_associations_offline(
    result: GeometricAssociationResult,
    local_truth_global_track_ids: Mapping[str, str],
) -> OfflineAssociationMetrics:
    """Evaluate selected associations with truth labels outside online logic."""

    evaluated = 0
    correct = 0
    mismatches = 0
    for track_id, local_track_id in result.assignments.items():
        truth_track_id = local_truth_global_track_ids.get(local_track_id)
        if truth_track_id is None:
            continue
        evaluated += 1
        if truth_track_id == track_id:
            correct += 1
        else:
            mismatches += 1
    accuracy = correct / evaluated if evaluated else None
    return OfflineAssociationMetrics(
        association_accuracy=accuracy,
        id_mismatch_count=mismatches,
        evaluated_count=evaluated,
        ambiguous_count=result.ambiguous_count,
    )


def _hungarian_like_assignments(costs: np.ndarray, *, max_cost: float) -> list[tuple[int, int]]:
    if costs.size == 0:
        return []
    rows, cols = costs.shape
    finite_rows = range(rows)
    finite_cols = range(cols)
    try:
        from scipy.optimize import linear_sum_assignment

        row_indices, col_indices = linear_sum_assignment(costs)
        return [
            (int(row), int(col))
            for row, col in zip(row_indices, col_indices)
            if np.isfinite(costs[row, col]) and costs[row, col] < max_cost
        ]
    except Exception:
        pass

    candidates = [
        (float(costs[row, col]), row, col)
        for row in finite_rows
        for col in finite_cols
        if np.isfinite(costs[row, col]) and costs[row, col] < max_cost
    ]
    candidates.sort(key=lambda item: item[0])
    used_rows: set[int] = set()
    used_cols: set[int] = set()
    selected: list[tuple[int, int]] = []
    for _cost, row, col in candidates:
        if row in used_rows or col in used_cols:
            continue
        used_rows.add(row)
        used_cols.add(col)
        selected.append((row, col))
    return selected


def _ambiguous_track_count(cost_result: CostMatrixResult, config: AssociationConfig) -> int:
    count = 0
    for row in range(cost_result.costs.shape[0]):
        feasible = sorted(
            float(value)
            for value in cost_result.costs[row]
            if np.isfinite(value) and value < config.cost_inf
        )
        if len(feasible) >= 2 and feasible[1] - feasible[0] < config.min_lock_margin:
            count += 1
    return count


def _finite_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    if not np.isfinite(value):
        return None
    return value
