"""Minimal AirSim-compatible client used by offline search tests."""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import SimpleNamespace
from typing import Mapping, Sequence

import numpy as np

from center_terminal_cv_campaign.common.scenario import TargetTruth


@dataclass(frozen=True)
class FakeVector3r:
    x_val: float = 0.0
    y_val: float = 0.0
    z_val: float = 0.0


@dataclass(frozen=True)
class FakeQuaternionr:
    pitch_rad: float = 0.0
    roll_rad: float = 0.0
    yaw_rad: float = 0.0


@dataclass(frozen=True)
class FakePose:
    position: FakeVector3r
    orientation: FakeQuaternionr


class FakeAirSimModule:
    Vector3r = FakeVector3r
    Pose = FakePose

    class ImageType:
        Scene = 0

    @staticmethod
    def to_quaternion(pitch: float, roll: float, yaw: float) -> FakeQuaternionr:
        return FakeQuaternionr(float(pitch), float(roll), float(yaw))


class FakeDetection:
    def __init__(self, name: str, bbox_xyxy: Sequence[float]) -> None:
        self.name = str(name)
        self.box2D = SimpleNamespace(
            min=SimpleNamespace(x_val=float(bbox_xyxy[0]), y_val=float(bbox_xyxy[1])),
            max=SimpleNamespace(x_val=float(bbox_xyxy[2]), y_val=float(bbox_xyxy[3])),
        )


class GeometricFakeAirSimClient:
    """Project moving point targets into the commanded ComputerVision poses."""

    def __init__(
        self,
        targets: Sequence[TargetTruth],
        *,
        image_width: int = 1920,
        image_height: int = 1080,
        horizontal_fov_deg: float = 19.0,
    ) -> None:
        self.targets = tuple(targets)
        self.image_width = int(image_width)
        self.image_height = int(image_height)
        self.horizontal_fov_deg = float(horizontal_fov_deg)
        self.vehicle_poses: dict[str, FakePose] = {}
        self.timestamp = 0.0
        self.frame_index = 0
        self.pose_commands: list[tuple[str, FakePose]] = []

    def ping(self) -> bool:
        return True

    def simSetVehiclePose(
        self, pose: FakePose, _ignore_collision: bool, *, vehicle_name: str
    ) -> bool:
        self.vehicle_poses[str(vehicle_name)] = pose
        self.pose_commands.append((str(vehicle_name), pose))
        return True

    def simClearDetectionMeshNames(self, *_args, **_kwargs) -> None:
        return None

    def simSetDetectionFilterRadius(self, *_args, **_kwargs) -> None:
        return None

    def simAddDetectionFilterMeshName(self, *_args, **_kwargs) -> None:
        return None

    def set_search_frame(self, frame_index: int, timestamp: float) -> None:
        self.frame_index = int(frame_index)
        self.timestamp = float(timestamp)

    def simGetDetections(self, *_args, vehicle_name: str, **_kwargs) -> list[FakeDetection]:
        pose = self.vehicle_poses.get(str(vehicle_name))
        if pose is None:
            return []
        detections: list[FakeDetection] = []
        for target in self.targets:
            bbox = self._project_bbox(target, pose)
            if bbox is not None:
                detections.append(FakeDetection(target.actor_name, bbox))
        return detections

    def _project_bbox(
        self, target: TargetTruth, pose: FakePose
    ) -> tuple[float, float, float, float] | None:
        camera = np.asarray(
            (pose.position.x_val, pose.position.y_val, pose.position.z_val), dtype=float
        )
        point = np.asarray(target.position_at(self.timestamp), dtype=float)
        delta = point - camera
        yaw = pose.orientation.yaw_rad
        pitch = pose.orientation.pitch_rad
        forward = np.asarray(
            (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)),
            dtype=float,
        )
        right = np.asarray((-math.sin(yaw), math.cos(yaw), 0.0), dtype=float)
        down = np.cross(forward, right)
        depth = float(np.dot(delta, forward))
        if depth <= 1.0:
            return None
        horizontal = float(np.dot(delta, right))
        vertical = float(np.dot(delta, down))
        focal = self.image_width / (2.0 * math.tan(math.radians(self.horizontal_fov_deg) * 0.5))
        u = self.image_width * 0.5 + focal * horizontal / depth
        v = self.image_height * 0.5 + focal * vertical / depth
        extent = max(0.2, focal * float(target.longest_dimension_m) / depth)
        x1, y1 = u - extent * 0.5, v - extent * 0.35
        x2, y2 = u + extent * 0.5, v + extent * 0.35
        if x2 < 0.0 or x1 > self.image_width or y2 < 0.0 or y1 > self.image_height:
            return None
        return (
            max(0.0, x1),
            max(0.0, y1),
            min(float(self.image_width), x2),
            min(float(self.image_height), y2),
        )


class ScriptedFakeAirSimClient:
    """Return exact frame/camera detection schedules for boundary tests."""

    def __init__(
        self,
        schedule: Mapping[tuple[int, str], Sequence[tuple[str, Sequence[float]]]],
    ) -> None:
        self.schedule = {
            (int(frame), str(camera)): tuple((str(name), tuple(bbox)) for name, bbox in rows)
            for (frame, camera), rows in schedule.items()
        }
        self.frame_index = 0
        self.pose_commands: list[tuple[str, FakePose]] = []

    def ping(self) -> bool:
        return True

    def set_search_frame(self, frame_index: int, _timestamp: float) -> None:
        self.frame_index = int(frame_index)

    def simSetVehiclePose(
        self, pose: FakePose, _ignore_collision: bool, *, vehicle_name: str
    ) -> bool:
        self.pose_commands.append((str(vehicle_name), pose))
        return True

    def simClearDetectionMeshNames(self, *_args, **_kwargs) -> None:
        return None

    def simSetDetectionFilterRadius(self, *_args, **_kwargs) -> None:
        return None

    def simAddDetectionFilterMeshName(self, *_args, **_kwargs) -> None:
        return None

    def simGetDetections(self, *_args, vehicle_name: str, **_kwargs) -> list[FakeDetection]:
        rows = self.schedule.get((self.frame_index, str(vehicle_name)), ())
        return [FakeDetection(name, bbox) for name, bbox in rows]
