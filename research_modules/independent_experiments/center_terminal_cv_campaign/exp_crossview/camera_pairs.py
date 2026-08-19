"""Camera-pair sparsification from online-safe capture-plan geometry."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math
from typing import Any, Mapping, Sequence

import numpy as np

from .config import CameraCalibration
from .geometry import normalize, rotation_camera_to_ned


CAMERA_PAIR_POLICIES = ("full", "sector_fov")


@dataclass(frozen=True)
class CameraViewSample:
    frame_index: int
    sector_index: int
    yaw_pitch_roll_deg: tuple[float, float, float]


@dataclass(frozen=True)
class CameraPairPlan:
    policy: str
    all_pairs: frozenset[tuple[str, str]]
    allowed_pairs: frozenset[tuple[str, str]]
    rejection_reason_counts: Mapping[str, int]
    overlap_margin_deg: float = 5.0

    def __post_init__(self) -> None:
        if self.policy not in CAMERA_PAIR_POLICIES:
            raise ValueError(f"unsupported camera pair policy: {self.policy}")
        if not self.allowed_pairs <= self.all_pairs:
            raise ValueError("allowed camera pairs must be a subset of all pairs")

    @property
    def total_count(self) -> int:
        return len(self.all_pairs)

    @property
    def retained_count(self) -> int:
        return len(self.allowed_pairs)

    @property
    def pruned_count(self) -> int:
        return self.total_count - self.retained_count

    def allows(self, camera_a: str, camera_b: str) -> bool:
        return tuple(sorted((camera_a, camera_b))) in self.allowed_pairs

    def to_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "camera_pair_total_count": self.total_count,
            "camera_pair_retained_count": self.retained_count,
            "camera_pair_pruned_count": self.pruned_count,
            "rejection_reason_counts": dict(self.rejection_reason_counts),
            "overlap_margin_deg": self.overlap_margin_deg,
        }


def _all_pairs(camera_ids: Sequence[str]) -> frozenset[tuple[str, str]]:
    return frozenset(combinations(sorted(set(camera_ids)), 2))


def full_camera_pair_plan(camera_ids: Sequence[str]) -> CameraPairPlan:
    pairs = _all_pairs(camera_ids)
    return CameraPairPlan(
        policy="full",
        all_pairs=pairs,
        allowed_pairs=pairs,
        rejection_reason_counts={},
    )


def online_capture_views(
    capture_plan: Mapping[str, Any],
) -> dict[str, tuple[CameraViewSample, ...]]:
    """Extract only camera geometry; ignore all offline expectations and labels."""

    if capture_plan.get("schema_version") != "terminal-crossview-airsim-capture-plan-v1":
        raise ValueError("unsupported AirSim capture plan")
    frames = capture_plan.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("capture plan must contain at least one frame")
    by_camera: dict[str, list[CameraViewSample]] = {}
    sector_by_camera: dict[str, int] = {}
    for fallback_index, frame in enumerate(frames):
        if not isinstance(frame, Mapping):
            raise ValueError("capture plan frame must be an object")
        frame_index = int(frame.get("frame_index", fallback_index))
        cameras = frame.get("cameras")
        if not isinstance(cameras, list):
            raise ValueError("capture plan frame cameras must be a list")
        for camera in cameras:
            if not isinstance(camera, Mapping):
                raise ValueError("capture plan camera must be an object")
            camera_id = str(camera["camera_id"])
            if "sector_index" not in camera:
                raise ValueError(
                    f"sector_fov requires sector_index for camera {camera_id}"
                )
            sector_index = int(camera["sector_index"])
            if sector_index < 0:
                raise ValueError("sector_index cannot be negative")
            previous_sector = sector_by_camera.setdefault(camera_id, sector_index)
            if previous_sector != sector_index:
                raise ValueError(f"camera {camera_id} changes sector_index between frames")
            orientation = tuple(
                float(value) for value in camera["yaw_pitch_roll_deg"]
            )
            if len(orientation) != 3:
                raise ValueError("camera orientation must contain yaw, pitch, and roll")
            by_camera.setdefault(camera_id, []).append(
                CameraViewSample(
                    frame_index=frame_index,
                    sector_index=sector_index,
                    yaw_pitch_roll_deg=orientation,  # type: ignore[arg-type]
                )
            )
    return {
        camera_id: tuple(sorted(samples, key=lambda item: item.frame_index))
        for camera_id, samples in by_camera.items()
    }


def _half_diagonal_fov_deg(calibration: CameraCalibration) -> float:
    half_horizontal = math.radians(calibration.horizontal_fov_deg / 2.0)
    half_vertical = math.atan(
        math.tan(half_horizontal) * calibration.height_px / calibration.width_px
    )
    return math.degrees(
        math.atan(math.hypot(math.tan(half_horizontal), math.tan(half_vertical)))
    )


def _forward_direction(sample: CameraViewSample) -> np.ndarray:
    return normalize(
        rotation_camera_to_ned(sample.yaw_pitch_roll_deg)
        @ np.asarray((1.0, 0.0, 0.0), dtype=float)
    )


def _view_cones_overlap(
    samples_a: Sequence[CameraViewSample],
    samples_b: Sequence[CameraViewSample],
    calibration_a: CameraCalibration,
    calibration_b: CameraCalibration,
    margin_deg: float,
) -> bool:
    by_frame_b = {sample.frame_index: sample for sample in samples_b}
    maximum_angle = (
        _half_diagonal_fov_deg(calibration_a)
        + _half_diagonal_fov_deg(calibration_b)
        + margin_deg
    )
    for sample_a in samples_a:
        sample_b = by_frame_b.get(sample_a.frame_index)
        if sample_b is None:
            continue
        cosine = float(
            np.clip(
                np.dot(_forward_direction(sample_a), _forward_direction(sample_b)),
                -1.0,
                1.0,
            )
        )
        if math.degrees(math.acos(cosine)) <= maximum_angle:
            return True
    return False


def build_camera_pair_plan(
    calibrations: Mapping[str, CameraCalibration],
    *,
    policy: str = "full",
    capture_plan: Mapping[str, Any] | None = None,
    overlap_margin_deg: float = 5.0,
) -> CameraPairPlan:
    if policy not in CAMERA_PAIR_POLICIES:
        raise ValueError(f"unsupported camera pair policy: {policy}")
    if overlap_margin_deg < 0.0 or not math.isfinite(overlap_margin_deg):
        raise ValueError("overlap margin must be finite and non-negative")
    all_pairs = _all_pairs(tuple(calibrations))
    if policy == "full":
        return full_camera_pair_plan(tuple(calibrations))
    if capture_plan is None:
        raise ValueError("sector_fov requires an AirSim capture plan")
    views = online_capture_views(capture_plan)
    missing = sorted(set(calibrations) - set(views))
    if missing:
        raise ValueError(f"capture plan is missing cameras: {', '.join(missing)}")

    allowed: set[tuple[str, str]] = set()
    rejected = {
        "non_adjacent_sector": 0,
        "adjacent_sector_without_fov_overlap": 0,
    }
    for camera_a, camera_b in sorted(all_pairs):
        sector_a = views[camera_a][0].sector_index
        sector_b = views[camera_b][0].sector_index
        separation = abs(sector_a - sector_b)
        if separation == 0:
            allowed.add((camera_a, camera_b))
        elif separation == 1 and _view_cones_overlap(
            views[camera_a],
            views[camera_b],
            calibrations[camera_a],
            calibrations[camera_b],
            overlap_margin_deg,
        ):
            allowed.add((camera_a, camera_b))
        elif separation == 1:
            rejected["adjacent_sector_without_fov_overlap"] += 1
        else:
            rejected["non_adjacent_sector"] += 1
    return CameraPairPlan(
        policy=policy,
        all_pairs=all_pairs,
        allowed_pairs=frozenset(allowed),
        rejection_reason_counts={key: value for key, value in rejected.items() if value},
        overlap_margin_deg=float(overlap_margin_deg),
    )


__all__ = [
    "CAMERA_PAIR_POLICIES",
    "CameraPairPlan",
    "CameraViewSample",
    "build_camera_pair_plan",
    "full_camera_pair_plan",
    "online_capture_views",
]
