from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from .motion import wrap_angle
from .observations import (
    CameraModel,
    acoustic_covariance,
    acoustic_h,
    eo_covariance_from_bbox,
    eo_project,
    lidar_covariance,
    radar_covariance_from_range,
    radar_h,
)
from .types import SensorObservation


def make_minimal_airsim_dry_run_fixture(include_lidar: bool = True) -> dict[str, Any]:
    """Return a deterministic fake AirSim-like fixture for offline adapter tests.

    The fixture is intentionally plain Python data. It does not import or call
    AirSim and is limited to synthetic sensing records for dry-run integration.
    """

    sensors: dict[str, Any] = {
        "radar": {
            "enabled": True,
            "sensor_id": "dry_radar_01",
            "position_ned": [0.0, 0.0, 0.0],
            "delay_s": 0.08,
            "confidence": 0.9,
        },
        "acoustic": {
            "enabled": True,
            "sensor_id": "dry_acoustic_01",
            "position_ned": [0.0, -45.0, 0.0],
            "delay_s": 0.12,
            "confidence": 0.82,
        },
        "eo": {
            "enabled": True,
            "sensor_id": "dry_eo_01",
            "delay_s": 0.05,
            "confidence": 0.88,
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
            "sensor_id": "dry_lidar_01",
            "position_ned": [0.0, 0.0, -8.0],
            "delay_s": 0.06,
            "confidence": 0.9,
        },
    }
    return {
        "fixture_id": "minimal_airsim_dry_run",
        "frame_id": "ned",
        "sensors": sensors,
        "frames": [
            {
                "timestamp": 0.0,
                "targets": [
                    {
                        "target_id": "target_01",
                        "state_ned": [120.0, 15.0, -20.0, 4.0, 0.8, 0.0],
                    }
                ],
            },
            {
                "timestamp": 0.5,
                "targets": [
                    {
                        "target_id": "target_01",
                        "state_ned": [122.0, 15.4, -20.0, 4.0, 0.8, 0.0],
                    }
                ],
            },
        ],
    }


def observations_from_airsim_dry_run_fixture(
    fixture: Mapping[str, Any],
) -> list[SensorObservation]:
    """Convert a fake AirSim dry-run fixture into D1 SensorObservation records."""

    if str(fixture.get("frame_id", "ned")).lower() != "ned":
        raise ValueError("D1 AirSim dry-run fixture must use frame_id='ned'")

    observations: list[SensorObservation] = []
    sensors = dict(fixture.get("sensors", {}))
    for frame_index, frame in enumerate(_fixture_frames(fixture)):
        timestamp = float(frame["timestamp"])
        for target_index, target in enumerate(frame.get("targets", [])):
            target_id = str(target.get("target_id", f"target_{target_index + 1:02d}"))
            state = np.asarray(target["state_ned"], dtype=float).reshape(6)
            for modality in ("radar", "acoustic", "eo", "lidar"):
                config = _sensor_config(sensors, modality)
                if not config.get("enabled", False):
                    continue
                observation = _observation_for_sensor(
                    modality=modality,
                    config=config,
                    state=state,
                    target_id=target_id,
                    frame_index=frame_index,
                    measurement_timestamp=timestamp,
                    fixture_id=str(fixture.get("fixture_id", "airsim_dry_run")),
                )
                if observation is not None:
                    observations.append(observation)

    return sorted(observations, key=lambda obs: (obs.arrival_timestamp, obs.observation_id))


def _fixture_frames(fixture: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    frames = fixture.get("frames")
    if frames is not None:
        return list(frames)
    if "targets" in fixture:
        return [
            {
                "timestamp": float(fixture.get("timestamp", 0.0)),
                "targets": fixture["targets"],
            }
        ]
    raise ValueError("AirSim dry-run fixture requires 'frames' or top-level 'targets'")


def _sensor_config(sensors: Mapping[str, Any], modality: str) -> dict[str, Any]:
    value = sensors.get(modality, {})
    if isinstance(value, bool):
        return {"enabled": value}
    config = dict(value)
    config.setdefault("enabled", False)
    return config


def _observation_for_sensor(
    modality: str,
    config: Mapping[str, Any],
    state: np.ndarray,
    target_id: str,
    frame_index: int,
    measurement_timestamp: float,
    fixture_id: str,
) -> SensorObservation | None:
    sensor_id = str(config.get("sensor_id", f"dry_{modality}_01"))
    delay_s = float(config.get("delay_s", 0.0))
    arrival_timestamp = measurement_timestamp + delay_s
    confidence = float(config.get("confidence", 0.9))
    base_metadata = {
        "truth_id": target_id,
        "fixture_id": fixture_id,
        "dry_run": True,
    }

    if modality == "radar":
        sensor_position = _vector3(config.get("position_ned", [0.0, 0.0, 0.0]))
        measurement = radar_h(state, sensor_position)
        measurement[1] = wrap_angle(measurement[1])
        measurement[2] = wrap_angle(measurement[2])
        covariance = radar_covariance_from_range(measurement[0])
        return SensorObservation(
            observation_id=f"dry_radar_{target_id}_{frame_index:04d}",
            sensor_id=sensor_id,
            modality="radar",
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_id="ned",
            measurement=measurement,
            covariance=covariance,
            confidence=confidence,
            metadata={
                **base_metadata,
                "sensor_position_ned": sensor_position,
            },
        )

    if modality == "acoustic":
        sensor_position = _vector3(config.get("position_ned", [0.0, 0.0, 0.0]))
        measurement = acoustic_h(state, sensor_position)
        covariance = acoustic_covariance(confidence)
        return SensorObservation(
            observation_id=f"dry_acoustic_{target_id}_{frame_index:04d}",
            sensor_id=sensor_id,
            modality="acoustic",
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_id="ned",
            measurement=measurement,
            covariance=covariance,
            classification_hint=str(config.get("classification_hint", f"voiceprint_{target_id}")),
            confidence=confidence,
            metadata={
                **base_metadata,
                "sensor_position_ned": sensor_position,
            },
        )

    if modality == "eo":
        camera = _camera_from_config(config.get("camera", {}))
        pixel = eo_project(state, camera)
        rel = state[:3] - camera.position_ned
        point_camera = camera.rotation_world_to_camera @ rel
        if point_camera[2] <= 1.0:
            return None
        box_size = float(config.get("box_size_px", np.clip(5200.0 / max(np.linalg.norm(rel), 1.0), 8.0, 80.0)))
        bbox = np.array(
            [
                pixel[0] - 0.5 * box_size,
                pixel[1] - 0.35 * box_size,
                pixel[0] + 0.5 * box_size,
                pixel[1] + 0.35 * box_size,
            ],
            dtype=float,
        )
        quality_flags = tuple(config.get("quality_flags", ()))
        if box_size < 14.0 and "small_bbox" not in quality_flags:
            quality_flags = (*quality_flags, "small_bbox")
        covariance = eo_covariance_from_bbox(bbox, confidence, quality_flags)
        return SensorObservation(
            observation_id=f"dry_eo_{target_id}_{frame_index:04d}",
            sensor_id=sensor_id,
            modality="eo",
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_id="pixel",
            measurement=pixel,
            covariance=covariance,
            confidence=confidence,
            quality_flags=quality_flags,
            metadata={
                **base_metadata,
                "bbox": bbox,
                "camera_model": camera,
            },
        )

    if modality == "lidar":
        sensor_position = _vector3(config.get("position_ned", [0.0, 0.0, 0.0]))
        distance = float(np.linalg.norm(state[:3] - sensor_position))
        covariance = lidar_covariance(distance, confidence)
        return SensorObservation(
            observation_id=f"dry_lidar_{target_id}_{frame_index:04d}",
            sensor_id=sensor_id,
            modality="lidar",
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_id="ned",
            measurement=state[:3].copy(),
            covariance=covariance,
            confidence=confidence,
            metadata={
                **base_metadata,
                "sensor_position_ned": sensor_position,
            },
        )

    raise ValueError(f"unsupported dry-run modality: {modality}")


def _vector3(value: Any) -> np.ndarray:
    return np.asarray(value, dtype=float).reshape(3)


def _camera_from_config(config: Mapping[str, Any]) -> CameraModel:
    return CameraModel(
        position_ned=_vector3(config.get("position_ned", [0.0, 0.0, -10.0])),
        rotation_world_to_camera=np.asarray(
            config.get(
                "rotation_world_to_camera",
                [
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                    [1.0, 0.0, 0.0],
                ],
            ),
            dtype=float,
        ),
        fx=float(config.get("fx", 900.0)),
        fy=float(config.get("fy", 900.0)),
        cx=float(config.get("cx", 640.0)),
        cy=float(config.get("cy", 360.0)),
        width=int(config.get("width", 1280)),
        height=int(config.get("height", 720)),
    )
