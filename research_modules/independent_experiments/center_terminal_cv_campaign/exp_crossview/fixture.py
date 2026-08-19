"""Deterministic anonymous replay fixtures for cross-view association."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

import numpy as np

from ..common.contracts import LocalVisualTrackRecord
from ..common.recognition import is_recognizable_bbox
from .config import CameraCalibration
from .contracts import OfflineTruthLabels, track_key
from .geometry import pixel_to_world_ray, project_world_point, rotation_camera_to_ned


@dataclass(frozen=True)
class FixtureBundle:
    scenario_name: str
    seed: int
    records: tuple[LocalVisualTrackRecord, ...]
    calibrations: Mapping[str, CameraCalibration]
    truth: OfflineTruthLabels
    frame_count: int
    target_count: int


@dataclass(frozen=True)
class _Target:
    target_id: str
    position0_ned_m: np.ndarray
    velocity_ned_mps: np.ndarray

    def position_at(self, timestamp: float) -> np.ndarray:
        return self.position0_ned_m + timestamp * self.velocity_ned_mps


def _camera_ids(camera_count: int) -> tuple[str, ...]:
    return tuple(f"Terminal_CV_{index:02d}" for index in range(1, camera_count + 1))


def _camera_positions(camera_ids: tuple[str, ...]) -> dict[str, np.ndarray]:
    lateral = np.linspace(-42.0, 42.0, len(camera_ids))
    return {
        camera_id: np.asarray(
            (
                8.0 * (index % 2),
                float(lateral[index]),
                -128.0 + 8.0 * (index % 3),
            )
        )
        for index, camera_id in enumerate(camera_ids)
    }


def _targets(target_count: int, seed: int) -> tuple[_Target, ...]:
    rng = np.random.default_rng(seed)
    lateral = np.linspace(-54.0, 54.0, target_count)
    rng.shuffle(lateral)
    targets: list[_Target] = []
    for index in range(target_count):
        heading_deg = float(rng.uniform(-28.0, 28.0))
        if index == 0:
            lateral[index] = -12.0
            heading_deg = 22.0
        elif index == 1:
            lateral[index] = 12.0
            heading_deg = -22.0
        heading = math.radians(heading_deg)
        velocity = np.asarray((-50.0 * math.cos(heading), 50.0 * math.sin(heading), 0.0))
        targets.append(
            _Target(
                target_id=f"OFFLINE-T{index + 1:03d}",
                position0_ned_m=np.asarray(
                    (
                        520.0 + float(rng.uniform(-35.0, 35.0)) + 3.0 * (index % 3),
                        float(lateral[index]),
                        -120.0 + float((-1, 0, 1)[index % 3] * 5.0),
                    )
                ),
                velocity_ned_mps=velocity,
            )
        )
    return tuple(targets)


def _camera_count_for_scenario(scenario_name: str) -> int:
    if scenario_name in {"two_by_two_crossing", "no_common_targets"}:
        return 2
    if scenario_name == "partial_3cam_5target":
        return 3
    if scenario_name == "dense_multicamera":
        return 8
    raise ValueError(f"unknown fixture scenario: {scenario_name}")


def _visible(
    scenario_name: str,
    camera_index: int,
    target_index: int,
    frame_index: int,
    target_count: int,
) -> bool:
    if scenario_name == "two_by_two_crossing":
        return target_index < 2
    if scenario_name == "no_common_targets":
        split = max(1, target_count // 2)
        return target_index < split if camera_index == 0 else target_index >= split
    if scenario_name == "partial_3cam_5target":
        base = (
            {0, 1, 2, 3},
            {1, 2, 3, 4},
            {0, 1, 3, 4},
        )[camera_index]
        if target_index not in base:
            return False
        # Camera 1 and 2 have no shared observation in this short interval.
        if frame_index == 3:
            if camera_index == 0:
                return target_index == 0
            if camera_index == 1:
                return target_index == 4
        # Target 5 hands over from camera 2 to camera 3 with three shared
        # geometry samples before camera 2 drops it.
        if target_index == 4 and camera_index == 1:
            return frame_index <= 4
        if target_index == 4 and camera_index == 2:
            return frame_index >= 2
        return True
    # Every dense target has two views; even targets have a third. A brief
    # dropout on the first view exercises continuity and handoff.
    assigned = {
        target_index % 8,
        (target_index + 1) % 8,
    }
    if target_index % 2 == 0:
        assigned.add((target_index + 3) % 8)
    if camera_index not in assigned:
        return False
    if camera_index == target_index % 8 and frame_index >= 5 and target_index % 4 == 0:
        return False
    if camera_index == (target_index + 1) % 8 and frame_index < 2 and target_index % 4 == 0:
        return False
    return True


def _anonymous_track_ids(
    camera_ids: tuple[str, ...], target_count: int, seed: int
) -> dict[tuple[str, int], str]:
    result: dict[tuple[str, int], str] = {}
    for camera_offset, camera_id in enumerate(camera_ids):
        rng = np.random.default_rng(seed + 104729 * (camera_offset + 1))
        permutation = rng.permutation(target_count)
        for local_sequence, target_index in enumerate(permutation, start=1):
            result[(camera_id, int(target_index))] = f"L{local_sequence:03d}"
    return result


def build_fixture(
    scenario_name: str,
    *,
    seed: int = 20260816,
    target_count: int | None = None,
    frame_count: int = 7,
    dt_s: float = 0.2,
    pixel_noise_std: float = 0.25,
) -> FixtureBundle:
    camera_count = _camera_count_for_scenario(scenario_name)
    if target_count is None:
        target_count = {
            "two_by_two_crossing": 2,
            "no_common_targets": 4,
            "partial_3cam_5target": 5,
            "dense_multicamera": 20,
        }[scenario_name]
    if target_count <= 0 or frame_count < 2 or dt_s <= 0.0:
        raise ValueError("fixture dimensions and timing must be positive")
    if scenario_name == "two_by_two_crossing" and target_count != 2:
        raise ValueError("two_by_two_crossing requires exactly two targets")
    if scenario_name == "partial_3cam_5target" and target_count != 5:
        raise ValueError("partial_3cam_5target requires exactly five targets")
    camera_ids = _camera_ids(camera_count)
    calibrations = {
        camera_id: CameraCalibration(camera_id=camera_id, confidence=0.93 + 0.01 * (index % 3))
        for index, camera_id in enumerate(camera_ids)
    }
    camera_positions = _camera_positions(camera_ids)
    track_ids = _anonymous_track_ids(camera_ids, target_count, seed)
    targets = _targets(target_count, seed)
    rng = np.random.default_rng(seed + 17)
    records: list[LocalVisualTrackRecord] = []
    track_truth: dict[str, str] = {}
    trajectories: dict[str, list[tuple[float, float, float, float]]] = {
        target.target_id: [] for target in targets
    }

    for frame_index in range(frame_count):
        timestamp = frame_index * dt_s
        for target in targets:
            position = target.position_at(timestamp)
            trajectories[target.target_id].append(
                (timestamp, float(position[0]), float(position[1]), float(position[2]))
            )
        for camera_index, camera_id in enumerate(camera_ids):
            calibration = calibrations[camera_id]
            camera_position = camera_positions[camera_id]
            yaw_pitch_roll = (0.0, 0.0, 0.0)
            for target_index, target in enumerate(targets):
                if not _visible(
                    scenario_name,
                    camera_index,
                    target_index,
                    frame_index,
                    target_count,
                ):
                    continue
                position = target.position_at(timestamp)
                center = project_world_point(
                    position,
                    camera_position,
                    yaw_pitch_roll,
                    calibration,
                )
                if center is None:
                    continue
                noisy_center = np.asarray(center) + rng.normal(0.0, pixel_noise_std, size=2)
                if not (
                    0.0 <= noisy_center[0] < calibration.width_px
                    and 0.0 <= noisy_center[1] < calibration.height_px
                ):
                    continue
                distance = float(np.linalg.norm(position - camera_position))
                extent = max(4.0, calibration.fx_px * 3.0 / distance)
                bbox = (
                    float(noisy_center[0] - extent / 2.0),
                    float(noisy_center[1] - extent / 2.0),
                    float(noisy_center[0] + extent / 2.0),
                    float(noisy_center[1] + extent / 2.0),
                )
                local_id = track_ids[(camera_id, target_index)]
                key = track_key(camera_id, local_id)
                track_truth[key] = target.target_id
                ray = pixel_to_world_ray(noisy_center, calibration, yaw_pitch_roll)
                records.append(
                    LocalVisualTrackRecord(
                        camera_id=camera_id,
                        local_track_id=local_id,
                        measurement_timestamp=timestamp,
                        arrival_timestamp=timestamp + 0.01 + 0.001 * camera_index,
                        bbox_xyxy=bbox,
                        center_px=(float(noisy_center[0]), float(noisy_center[1])),
                        ray_origin_ned_m=tuple(float(value) for value in camera_position),
                        ray_direction_ned=tuple(float(value) for value in ray),
                        camera_yaw_pitch_roll_deg=yaw_pitch_roll,
                        recognized=is_recognizable_bbox(bbox),
                        recognition_extent_px=extent,
                        track_quality=0.96,
                        metadata={
                            "frame_index": frame_index,
                            "source_kind": "synthetic_pinhole_fixture",
                        },
                    )
                )
    truth = OfflineTruthLabels(
        track_to_target=track_truth,
        target_trajectories_ned_m={
            key: tuple(values) for key, values in trajectories.items()
        },
        scenario_name=scenario_name,
        seed=seed,
    )
    return FixtureBundle(
        scenario_name=scenario_name,
        seed=seed,
        records=tuple(
            sorted(records, key=lambda item: (item.measurement_timestamp, item.camera_id, item.local_track_id))
        ),
        calibrations=calibrations,
        truth=truth,
        frame_count=frame_count,
        target_count=target_count,
    )
