"""AirSim settings generator for the shared ComputerVision scene."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CENTER_CAMERA_NAMES = ("Center_Optical_A", "Center_Optical_B")
INTERCEPTOR_CAMERA_PREFIX = "Terminal_CV_"
CENTER_HORIZONTAL_FOV_DEG = 3.67
INTERCEPTOR_HORIZONTAL_FOV_DEG = 19.0


def interceptor_camera_names(count: int) -> tuple[str, ...]:
    if count <= 0:
        raise ValueError("count must be positive")
    return tuple(f"{INTERCEPTOR_CAMERA_PREFIX}{index:02d}" for index in range(1, count + 1))


def _capture(width: int, height: int, fov_deg: float) -> list[dict[str, Any]]:
    return [
        {
            "ImageType": 0,
            "Width": int(width),
            "Height": int(height),
            "FOV_Degrees": float(fov_deg),
            "MotionBlurAmount": 0,
        }
    ]


def _vehicle(
    *,
    position_ned: tuple[float, float, float],
    width: int,
    height: int,
    horizontal_fov_deg: float,
    camera_x_m: float = 0.0,
) -> dict[str, Any]:
    return {
        "VehicleType": "ComputerVision",
        "AutoCreate": True,
        "AllowAPIAlways": True,
        "X": float(position_ned[0]),
        "Y": float(position_ned[1]),
        "Z": float(position_ned[2]),
        "Pitch": 0,
        "Roll": 0,
        "Yaw": 0,
        "Cameras": {
            "0": {
                "X": float(camera_x_m),
                "Y": 0,
                "Z": 0,
                "Pitch": 0,
                "Roll": 0,
                "Yaw": 0,
                "CaptureSettings": _capture(width, height, horizontal_fov_deg),
            }
        },
    }


def write_campaign_settings(
    path: Path,
    *,
    interceptor_count: int = 40,
    api_port: int = 41451,
    clock_speed: float = 0.1,
) -> Path:
    """Write one maximum-capacity settings file reused across reset episodes."""

    names = interceptor_camera_names(interceptor_count)
    vehicles: dict[str, Any] = {
        CENTER_CAMERA_NAMES[0]: _vehicle(
            position_ned=(0.0, -1000.0, -100.0),
            width=1280,
            height=1024,
            horizontal_fov_deg=CENTER_HORIZONTAL_FOV_DEG,
        ),
        CENTER_CAMERA_NAMES[1]: _vehicle(
            position_ned=(0.0, 1000.0, -100.0),
            width=1280,
            height=1024,
            horizontal_fov_deg=CENTER_HORIZONTAL_FOV_DEG,
        ),
    }
    for name in names:
        vehicles[name] = _vehicle(
            # CV nodes are pose-commanded every episode. A common origin avoids
            # AirSim's per-vehicle start-offset semantics changing world NED.
            position_ned=(0.0, 0.0, 0.0),
            width=1920,
            height=1080,
            horizontal_fov_deg=INTERCEPTOR_HORIZONTAL_FOV_DEG,
            camera_x_m=0.5,
        )
    payload = {
        "SeeDocsAt": "https://microsoft.github.io/AirSim/settings/",
        "SettingsVersion": 1.2,
        "SimMode": "ComputerVision",
        "EnableRpc": True,
        "RpcEnabled": True,
        "ApiServerPort": int(api_port),
        "LocalHostIp": "127.0.0.1",
        "ClockSpeed": float(clock_speed),
        "ViewMode": "NoDisplay",
        # AirSim 1.8.1 creates the built-in camera from CameraDefaults first.
        # Per-vehicle CaptureSettings then override this profile for the two
        # narrow-field center cameras.
        "CameraDefaults": {
            "CaptureSettings": _capture(1920, 1080, INTERCEPTOR_HORIZONTAL_FOV_DEG),
        },
        "SubWindows": [],
        "Vehicles": vehicles,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
