"""Configuration records for the independent cross-view experiment."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Mapping


@dataclass(frozen=True)
class CameraCalibration:
    camera_id: str
    width_px: int = 1920
    height_px: int = 1080
    horizontal_fov_deg: float = 19.0
    confidence: float = 0.95

    def __post_init__(self) -> None:
        if not self.camera_id.strip():
            raise ValueError("camera_id must be non-empty")
        if self.width_px <= 0 or self.height_px <= 0:
            raise ValueError("image dimensions must be positive")
        if not 0.0 < self.horizontal_fov_deg < 179.0:
            raise ValueError("horizontal_fov_deg must be within (0, 179)")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")

    @property
    def fx_px(self) -> float:
        return self.width_px / (2.0 * math.tan(math.radians(self.horizontal_fov_deg) / 2.0))

    @property
    def fy_px(self) -> float:
        # AirSim specifies horizontal FOV. Square pixels imply fx == fy.
        return self.fx_px

    @property
    def cx_px(self) -> float:
        return (self.width_px - 1.0) / 2.0

    @property
    def cy_px(self) -> float:
        return (self.height_px - 1.0) / 2.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CameraCalibration":
        return cls(
            camera_id=str(payload["camera_id"]),
            width_px=int(payload.get("width_px", 1920)),
            height_px=int(payload.get("height_px", 1080)),
            horizontal_fov_deg=float(payload.get("horizontal_fov_deg", 19.0)),
            confidence=float(payload.get("confidence", 0.95)),
        )


@dataclass(frozen=True)
class CrossViewConfig:
    recognition_extent_px: float = 10.0
    maximum_alignment_offset_s: float = 0.16
    maximum_handoff_gap_s: float = 0.65
    minimum_intersection_angle_deg: float = 0.35
    maximum_ray_separation_m: float = 2.0
    maximum_reprojection_error_px: float = 8.0
    maximum_motion_fit_error_m: float = 5.0
    maximum_motion_turn_deg: float = 55.0
    maximum_scale_geometry_log_error: float = 0.28
    minimum_geometry_samples: int = 3
    confirmation_hits: int = 2
    confirmation_window_frames: int = 3
    unmatched_cost: float = 1.05
    confirmed_pair_cost_bonus: float = 0.35
    gnn_probability_weight: float = 0.45
    mature_cluster_min_size: int = 2
    mature_cluster_min_cross_camera_pairs: int = 2
    short_track_min_observations: int = 2
    short_track_cluster_min_support_cameras: int = 2
    short_track_cluster_min_total_aligned_samples: int = 4
    short_track_cluster_min_peak_samples: int = 2
    short_track_cluster_max_geometry_cost: float = 0.18
    short_track_cluster_min_cost_margin: float = 0.05

    def __post_init__(self) -> None:
        positive = {
            "recognition_extent_px": self.recognition_extent_px,
            "maximum_alignment_offset_s": self.maximum_alignment_offset_s,
            "maximum_handoff_gap_s": self.maximum_handoff_gap_s,
            "minimum_intersection_angle_deg": self.minimum_intersection_angle_deg,
            "maximum_ray_separation_m": self.maximum_ray_separation_m,
            "maximum_reprojection_error_px": self.maximum_reprojection_error_px,
            "maximum_motion_fit_error_m": self.maximum_motion_fit_error_m,
            "maximum_motion_turn_deg": self.maximum_motion_turn_deg,
            "maximum_scale_geometry_log_error": self.maximum_scale_geometry_log_error,
            "unmatched_cost": self.unmatched_cost,
            "short_track_cluster_max_geometry_cost": self.short_track_cluster_max_geometry_cost,
        }
        if any(not math.isfinite(value) or value <= 0.0 for value in positive.values()):
            raise ValueError("all geometry thresholds must be finite and positive")
        if self.minimum_geometry_samples < 1 or self.confirmation_hits < 1:
            raise ValueError("sample and confirmation counts must be positive")
        integer_thresholds = {
            "mature_cluster_min_size": self.mature_cluster_min_size,
            "mature_cluster_min_cross_camera_pairs": self.mature_cluster_min_cross_camera_pairs,
            "short_track_min_observations": self.short_track_min_observations,
            "short_track_cluster_min_support_cameras": self.short_track_cluster_min_support_cameras,
            "short_track_cluster_min_total_aligned_samples": self.short_track_cluster_min_total_aligned_samples,
            "short_track_cluster_min_peak_samples": self.short_track_cluster_min_peak_samples,
        }
        if any(value < 1 for value in integer_thresholds.values()):
            raise ValueError("cluster evidence counts must be positive")
        if self.short_track_min_observations >= self.minimum_geometry_samples:
            raise ValueError(
                "short_track_min_observations must be below minimum_geometry_samples"
            )
        if not math.isfinite(self.short_track_cluster_min_cost_margin):
            raise ValueError("short track cluster cost margin must be finite")
        if self.short_track_cluster_min_cost_margin < 0.0:
            raise ValueError("short track cluster cost margin cannot be negative")
        if self.confirmation_window_frames < self.confirmation_hits:
            raise ValueError("confirmation window cannot be shorter than required hits")
        if not 0.0 <= self.confirmed_pair_cost_bonus < self.unmatched_cost:
            raise ValueError("confirmed_pair_cost_bonus is invalid")
        if not 0.0 <= self.gnn_probability_weight <= 1.0:
            raise ValueError("gnn_probability_weight must be within [0, 1]")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
