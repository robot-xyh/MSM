"""Fake AirSim runtime used for phase-1 interface tests."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Any, Protocol

import numpy as np

from integrated_simulation.scenario import (
    generate_resource_platforms,
    generate_truth_states,
    make_standard_scenario,
)

from .models import (
    AirSimCameraInfo,
    AirSimDetectionBox,
    AirSimEpisodeConfig,
    AirSimFrame,
    AirSimResourceState,
    AirSimTruthObject,
)


class AirSimRuntimeClient(Protocol):
    """Runtime contract for future real/fake AirSim implementations."""

    def reset(self, config: AirSimEpisodeConfig) -> None:
        """Reset a scenario before an episode."""

    def frame_at(self, config: AirSimEpisodeConfig, timestamp: float) -> AirSimFrame:
        """Return one frame for a timestamp."""

    def iter_frames(self, config: AirSimEpisodeConfig) -> Iterable[AirSimFrame]:
        """Yield all frames for an episode."""


class FakeAirSimRuntimeClient:
    """Deterministic fake AirSim client.

    It creates synthetic NED truth, camera detections, and node-health flags.
    It deliberately has no dependency on the real AirSim package.
    """

    def __init__(self) -> None:
        self.reset_count = 0
        self.last_reset_config: AirSimEpisodeConfig | None = None

    def reset(self, config: AirSimEpisodeConfig) -> None:
        self.reset_count += 1
        self.last_reset_config = config

    def iter_frames(self, config: AirSimEpisodeConfig) -> Iterable[AirSimFrame]:
        scenario = _scenario_config(config)
        for index, timestamp in enumerate(scenario.timestamps()):
            yield self._make_frame(config, timestamp, index)

    def frame_at(self, config: AirSimEpisodeConfig, timestamp: float) -> AirSimFrame:
        index = int(round(float(timestamp) / max(config.dt_s, 1e-9)))
        return self._make_frame(config, float(timestamp), max(index, 0))

    def _make_frame(
        self,
        config: AirSimEpisodeConfig,
        timestamp: float,
        frame_index: int,
    ) -> AirSimFrame:
        scenario = _scenario_config(config)
        truth_states = generate_truth_states(scenario, timestamp)
        resources = generate_resource_platforms(scenario)
        truth_objects = tuple(
            AirSimTruthObject(
                object_id=truth.truth_id,
                object_type="target",
                timestamp=timestamp,
                position_ned=_tuple3(truth.position),
                velocity_ned=_tuple3(truth.velocity),
                classification_hint="uav",
                threat_score=truth.threat_score,
                coverage_cell=truth.coverage_cell,
                metadata={"source": "fake_airsim_truth"},
            )
            for truth in truth_states
        )
        resource_states = tuple(
            AirSimResourceState(
                resource_id=resource.resource_id,
                timestamp=timestamp,
                position_ned=_tuple3(resource.position),
                status=resource.status,
                health_score=resource.health_score,
                coverage_cell=resource.coverage_cell,
            )
            for resource in resources
        )
        cameras = _camera_infos(timestamp, resource_states)
        detections = _visual_detections(timestamp, truth_objects, cameras, config.scenario_name)
        return AirSimFrame(
            episode_id=config.episode_id,
            scenario_name=config.scenario_name,
            frame_index=frame_index,
            timestamp=timestamp,
            truth_objects=truth_objects,
            resources=resource_states,
            cameras=cameras,
            visual_detections=detections,
            center_node_alive=not _center_failed(config.scenario_name, timestamp),
            secondary_nodes_alive=not _secondary_failed(config.scenario_name, timestamp),
            metadata={
                "dry_run": True,
                "runtime": "FakeAirSimRuntimeClient",
                "real_airsim_used": False,
            },
        )


def _scenario_config(config: AirSimEpisodeConfig) -> Any:
    name = _scenario_name_for_integrated(config.scenario_name)
    scenario = make_standard_scenario(
        name,
        seed=config.seed,
        duration_s=config.duration_s,
        output_root=config.output_root,
    )
    return replace(
        scenario,
        dt_s=config.dt_s,
        target_count=config.target_count,
        resource_count=config.resource_count,
        radar_latency_s=config.radar_latency_s,
        acoustic_enabled=config.include_acoustic,
        eo_enabled=config.include_eo,
    )


def _scenario_name_for_integrated(name: str) -> str:
    aliases = {
        "center_failed": "center_destroyed",
        "secondary_failed": "secondary_destroyed",
        "terminal_friend_overlap": "friend_overlap_hold",
        "cross_view_overlap": "nominal_5v5",
    }
    return aliases.get(name, name)


def _camera_infos(
    timestamp: float,
    resources: tuple[AirSimResourceState, ...],
) -> tuple[AirSimCameraInfo, ...]:
    cameras = [
        AirSimCameraInfo(
            camera_id="EO-GND-01",
            owner_id="MAIN-C2",
            timestamp=timestamp,
            position_ned=(0.0, 0.0, 0.0),
        )
    ]
    for resource in resources:
        cameras.append(
            AirSimCameraInfo(
                camera_id=f"{resource.resource_id}-cam",
                owner_id=resource.resource_id,
                timestamp=timestamp,
                position_ned=resource.position_ned,
            )
        )
    return tuple(cameras)


def _visual_detections(
    timestamp: float,
    truth_objects: tuple[AirSimTruthObject, ...],
    cameras: tuple[AirSimCameraInfo, ...],
    scenario_name: str,
) -> tuple[AirSimDetectionBox, ...]:
    detections: list[AirSimDetectionBox] = []
    for camera in cameras:
        if camera.owner_id == "MAIN-C2":
            visible = truth_objects
        elif camera.owner_id.endswith("01"):
            visible = truth_objects[:3]
        elif camera.owner_id.endswith("02"):
            visible = truth_objects[1:4]
        else:
            visible = truth_objects[2:]
        for index, truth in enumerate(visible):
            center = _simple_projection(truth.position_ned, camera)
            if center is None:
                continue
            size = 14.0 if camera.owner_id != "MAIN-C2" else 10.0
            is_friend = scenario_name in {"terminal_friend_overlap", "friend_overlap_hold"} and index == 0
            detections.append(
                AirSimDetectionBox(
                    detection_id=f"{camera.camera_id}-{truth.object_id}-{timestamp:.2f}",
                    camera_id=camera.camera_id,
                    object_id=truth.object_id,
                    local_track_id=f"L-{camera.owner_id}-{truth.object_id}",
                    timestamp=timestamp,
                    center_px=(center[0], center[1]),
                    bbox_xyxy=(
                        center[0] - size,
                        center[1] - size,
                        center[0] + size,
                        center[1] + size,
                    ),
                    confidence=0.9,
                    classification_hint=truth.classification_hint,
                    is_friend_hint=is_friend,
                )
            )
    return tuple(detections)


def _simple_projection(position_ned: tuple[float, float, float], camera: AirSimCameraInfo) -> tuple[float, float] | None:
    rel = np.asarray(position_ned, dtype=float) - np.asarray(camera.position_ned, dtype=float)
    depth = max(abs(float(rel[2])), 1.0)
    u = camera.cx + camera.fx * float(rel[0]) / (depth + 450.0)
    v = camera.cy + camera.fy * float(rel[1]) / (depth + 450.0)
    if -100.0 <= u <= camera.width + 100.0 and -100.0 <= v <= camera.height + 100.0:
        return (float(u), float(v))
    return None


def _center_failed(scenario_name: str, timestamp: float) -> bool:
    return scenario_name in {"center_failed", "center_destroyed", "secondary_failed", "secondary_destroyed"} and timestamp >= 4.0


def _secondary_failed(scenario_name: str, timestamp: float) -> bool:
    return scenario_name in {"secondary_failed", "secondary_destroyed"} and timestamp >= 3.5


def _tuple3(value: Any) -> tuple[float, float, float]:
    array = np.asarray(value, dtype=float).reshape(3)
    return (float(array[0]), float(array[1]), float(array[2]))
