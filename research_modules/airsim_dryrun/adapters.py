"""Adapter helpers from fake AirSim frames to module-specific inputs."""

from __future__ import annotations

from typing import Any

from d1_sensor_fusion.airsim_dry_run import observations_from_airsim_dry_run_fixture
from d1_sensor_fusion.types import SensorObservation

from .models import AirSimFrame


def observations_from_airsim_frame(
    frame: AirSimFrame,
    *,
    arrival_timestamp: float | None = None,
    include_acoustic: bool = True,
    include_eo: bool = True,
    include_lidar: bool = True,
) -> list[SensorObservation]:
    """Convert one fake AirSim frame to D1 canonical observations."""

    arrival = frame.timestamp if arrival_timestamp is None else float(arrival_timestamp)
    delay_s = max(0.0, arrival - frame.timestamp)
    fixture = {
        "fixture_id": f"{frame.episode_id}:{frame.scenario_name}:{frame.frame_index}",
        "frame_id": "ned",
        "sensors": _sensor_config(
            delay_s=delay_s,
            include_acoustic=include_acoustic,
            include_eo=include_eo,
            include_lidar=include_lidar,
        ),
        "frames": [
            {
                "timestamp": frame.timestamp,
                "targets": [
                    {
                        "target_id": obj.object_id,
                        "state_ned": list(obj.state_ned),
                    }
                    for obj in frame.truth_objects
                    if obj.object_type == "target"
                ],
            }
        ],
    }
    observations = observations_from_airsim_dry_run_fixture(fixture)
    for observation in observations:
        observation.metadata.update(
            {
                "airsim_episode_id": frame.episode_id,
                "airsim_scenario": frame.scenario_name,
                "airsim_frame_index": frame.frame_index,
                "real_airsim_used": False,
            }
        )
    return observations


def _sensor_config(
    *,
    delay_s: float,
    include_acoustic: bool,
    include_eo: bool,
    include_lidar: bool,
) -> dict[str, Any]:
    return {
        "radar": {
            "enabled": True,
            "sensor_id": "DRY-RADAR-01",
            "position_ned": [0.0, 0.0, 0.0],
            "delay_s": delay_s,
            "confidence": 0.9,
        },
        "acoustic": {
            "enabled": include_acoustic,
            "sensor_id": "DRY-ACOUSTIC-01",
            "position_ned": [0.0, -45.0, 0.0],
            "delay_s": delay_s,
            "confidence": 0.78,
        },
        "eo": {
            "enabled": include_eo,
            "sensor_id": "DRY-EO-01",
            "delay_s": delay_s,
            "confidence": 0.86,
            "camera": {
                "position_ned": [0.0, 0.0, -10.0],
                "rotation_world_to_camera": [
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                    [1.0, 0.0, 0.0],
                ],
                "fx": 900.0,
                "fy": 900.0,
                "cx": 640.0,
                "cy": 360.0,
                "width": 1280,
                "height": 720,
            },
        },
        "lidar": {
            "enabled": include_lidar,
            "sensor_id": "DRY-LIDAR-01",
            "position_ned": [0.0, 0.0, -8.0],
            "delay_s": delay_s,
            "confidence": 0.9,
        },
    }
