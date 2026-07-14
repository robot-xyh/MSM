"""Models for the real AirSim Blocks smoke runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from airsim_dryrun.models import AirSimAdapterResult

Vector3 = tuple[float, float, float]


@dataclass(frozen=True)
class BlocksActorTargetSpec:
    """One non-vehicle actor target moved by main through the AirSim sim API."""

    object_id: str
    actor_name: str
    start_ned: Vector3
    velocity_ned: Vector3
    asset_name: str = "Quadrotor1"
    scale: Vector3 = (1.0, 1.0, 1.0)
    threat_score: float = 0.9
    coverage_cell: str = "cell-north"
    fallback_actor_name: str | None = None

    def position_at(self, timestamp: float) -> Vector3:
        return tuple(
            float(self.start_ned[index] + self.velocity_ned[index] * timestamp)
            for index in range(3)
        )


@dataclass(frozen=True)
class BlocksSmokeConfig:
    """Configuration for one read-only Blocks smoke run."""

    episode_id: str = "blocks_smoke_001"
    scenario_name: str = "blocks_readonly_smoke"
    duration_s: float = 2.0
    dt_s: float = 0.5
    seed: int = 7
    radar_latency_s: float = 0.2
    blocks_script: Path = Path("Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh")
    settings_path: Path = Path("research_modules/airsim_runtime/settings/blocks_smoke_settings.json")
    output_root: Path = Path("research_modules/airsim_runtime/outputs")
    blocks_args: tuple[str, ...] = ("-windowed", "-ResX=640", "-ResY=480", "-NoVSync")
    prefer_nvidia_offload: bool = True
    launch_blocks: bool = True
    connection_timeout_s: float = 90.0
    client_timeout_s: float = 2.0
    client_kind: str = "vehicle"
    camera_vehicle_name: str = "Interceptor"
    camera_vehicle_names: tuple[str, ...] = ()
    secondary_camera_vehicle_names: tuple[str, ...] = ()
    camera_name: str = "0"
    save_images: bool = False
    capture_lidar: bool = True
    cv_camera_follow_assignments: bool = False
    cv_camera_follow_distance_m: float = 14.0
    cv_secondary_look_at_enabled: bool = True
    cv_secondary_mobile_recon_enabled: bool = False
    cv_secondary_recon_standoff_m: float = 0.0
    cv_reassignment_time_s: float | None = None
    lidar_vehicle_name: str = "Interceptor"
    lidar_vehicle_names: tuple[str, ...] = ()
    lidar_name: str = "LidarSensor1"
    target_vehicle_names: tuple[str, ...] = ("Intruder",)
    resource_vehicle_names: tuple[str, ...] = ("Interceptor",)
    target_actor_specs: tuple[BlocksActorTargetSpec, ...] = ()
    detection_backend: str = "airsim"
    detection_filter_names: tuple[str, ...] = ("MSM_TargetActor_*",)
    detection_radius_cm: int = 80 * 100
    secondary_detection_radius_cm: int | None = None
    detection_warmup_frames: int = 0
    yolo_weights_path: Path = Path("research_modules/d5_terminal_association/best.pt")
    yolo_tracker_backend: str = "bytetrack"
    yolo_confidence_threshold: float = 0.25
    yolo_use_native_tracker: bool = True
    yolo_allow_iou_fallback: bool = True
    yolo_compute_device: str = "auto"
    yolo_cpu_budget_ms: float | None = None
    yolo_gpu_budget_ms: float | None = None
    yolo_primary_inference_imgsz: int | tuple[int, int] | None = None
    yolo_secondary_inference_imgsz: int | tuple[int, int] | None = None
    yolo_offline_truth_evaluation: bool = False
    destroy_spawned_actor_targets: bool = True
    include_integrated_pipeline: bool = True
    execute_intercept: bool = False
    control_dt_s: float = 0.1
    intercept_speed_mps: float = 6.0
    intercept_altitude_ned_z: float = -2.0
    intercept_radius_m: float = 5.0
    intercept_max_duration_s: float = 8.0
    intercept_navigation_constant: float = 3.0
    intercept_terminal_switch_range_m: float = 8.0
    intercept_detection_timeout_s: float = 1.0
    intercept_guidance_law: str = "png_vm"
    intercept_yaw_mode: str = "velocity"
    intercept_min_bbox_area_ratio: float = 0.0008
    intercept_min_detection_confidence: float = 0.55
    intercept_min_stable_detection_frames: int = 2
    intercept_max_visual_latency_s: float = 0.35
    intercept_max_turn_rate_radps: float = 0.9
    intercept_max_lateral_accel_mps2: float = 20.0
    intercept_min_maneuver_margin: float = 0.15
    intercept_detection_dropout_start_s: float | None = None
    intercept_detection_dropout_end_s: float | None = None
    intercept_terminal_soft_prediction_enabled: bool = False
    intercept_terminal_trend_coast_enabled: bool = False
    cooperative_demand_enabled: bool = False
    cooperative_high_threat_target_count: int = 1
    cooperative_threat_threshold: float = 0.9
    high_threat_required_resource_count: int = 3
    cooperative_coordination_mode: str = "hybrid"
    cooperative_primary_count: int = 2
    cooperative_wave_gap_s: float = 2.0
    cooperative_minimum_separation_s: float = 0.5
    terminal_authorization_scope: str = "per_primary"
    arrival_coordination_required: bool = False
    target_asset_name: str = "Quadrotor1"
    target_detection_filter: str = "MSM_TargetActor_*"
    intercept_takeoff_timeout_s: float = 10.0
    intercept_land_after: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def timestamps(self) -> list[float]:
        count = int(round(self.duration_s / self.dt_s))
        return [round(index * self.dt_s, 6) for index in range(count + 1)]

    def api_server_port(self) -> int:
        return int(self._settings().get("ApiServerPort", 41451))

    def api_server_host(self) -> str:
        return str(self._settings().get("LocalHostIp") or "127.0.0.1")

    def _settings(self) -> dict[str, Any]:
        if not self.settings_path.exists():
            return {}
        try:
            return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    @property
    def output_dir(self) -> Path:
        return self.output_root / self.episode_id

    def effective_camera_vehicle_names(self) -> tuple[str, ...]:
        primary = self.camera_vehicle_names or (self.camera_vehicle_name,)
        return tuple(dict.fromkeys((*primary, *self.secondary_camera_vehicle_names)))

    def effective_lidar_vehicle_names(self) -> tuple[str, ...]:
        return self.lidar_vehicle_names or (self.lidar_vehicle_name,)

    def target_count(self) -> int:
        return len(self.target_actor_specs) if self.target_actor_specs else len(self.target_vehicle_names)


@dataclass(frozen=True)
class BlocksSmokeResult:
    """Result from one real Blocks read-only smoke run."""

    episode_id: str
    frame_count: int
    connected: bool
    vehicle_names: tuple[str, ...]
    image_ok_count: int
    lidar_ok_count: int
    output_paths: dict[str, Path]
    integrated_result: AirSimAdapterResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BlocksEpisodeSpec:
    """One staged Blocks episode under a single main-managed runtime."""

    episode_id: str
    focus: str
    scenario_name: str = "blocks_readonly_smoke"
    duration_s: float = 2.0
    dt_s: float = 0.5
    include_integrated_pipeline: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BlocksSequenceResult:
    """Result from a staged Blocks sequence launched once by main."""

    sequence_id: str
    connected: bool
    episode_results: tuple[BlocksSmokeResult, ...]
    output_paths: dict[str, Path]
    metadata: dict[str, Any] = field(default_factory=dict)


def default_interceptor_vehicle_names(count: int, *, prefix: str = "Interceptor") -> tuple[str, ...]:
    """Return deterministic SimpleFlight interceptor names for a run size."""

    _validate_count(count)
    return tuple(f"{prefix}{index}" for index in range(1, int(count) + 1))


def default_cv_camera_vehicle_names(count: int = 5, *, prefix: str = "Interceptor_Cam_") -> tuple[str, ...]:
    """Return deterministic ComputerVision camera vehicle names for a run size."""

    _validate_count(count)
    return tuple(f"{prefix}{index}" for index in range(1, int(count) + 1))


def default_cv_secondary_vehicle_names(count: int = 2, *, prefix: str = "Secondary_Recon_") -> tuple[str, ...]:
    """Return deterministic secondary recon camera names."""

    _validate_count(count)
    return tuple(f"{prefix}{index}" for index in range(1, int(count) + 1))


def default_actor_target_specs(
    *,
    count: int,
    target_z: float,
    target_distance_m: float,
    target_spacing_m: float,
    asset_name: str = "Quadrotor1",
    target_scale_m: float = 1.0,
    target_speed_scale: float = 1.0,
    x_spacing_m: float = 0.0,
    x_speed_base_mps: float = 1.0,
    x_speed_step_mps: float = 0.1,
    y_speed_span_mps: float = 0.8,
) -> tuple[BlocksActorTargetSpec, ...]:
    """Generate N moved actor targets centered laterally around the camera row."""

    _validate_count(count)
    y_positions = _centered_positions(int(count), float(target_spacing_m))
    y_velocities = _symmetric_velocities(int(count), float(y_speed_span_mps))
    specs: list[BlocksActorTargetSpec] = []
    for index, start_y in enumerate(y_positions):
        object_id = f"TGT-{index + 1:03d}"
        specs.append(
            BlocksActorTargetSpec(
                object_id=object_id,
                actor_name=f"MSM_TargetActor_{index + 1}",
                start_ned=(
                    float(target_distance_m) + float(x_spacing_m) * index,
                    float(start_y),
                    float(target_z),
                ),
                velocity_ned=(
                    (float(x_speed_base_mps) + float(x_speed_step_mps) * index)
                    * float(target_speed_scale),
                    y_velocities[index] * float(target_speed_scale),
                    0.0,
                ),
                asset_name=asset_name,
                scale=(float(target_scale_m), float(target_scale_m), float(target_scale_m)),
                threat_score=max(0.5, 0.95 - 0.06 * index),
                coverage_cell="cell-north" if index < max(1, int(count + 1) // 2) else "cell-south",
                fallback_actor_name=None,
            )
        )
    return tuple(specs)


def write_dynamic_multirotor_settings(
    path: Path,
    *,
    vehicle_names: tuple[str, ...],
    y_spacing_m: float = 10.0,
    vehicle_positions_ned: dict[str, Vector3] | None = None,
    tuned_terminal_camera: bool = False,
    fov_degrees: float = 120.0,
    lidar_range_m: float = 80.0,
    api_port: int = 41451,
) -> Path:
    """Write an AirSim SimpleFlight settings file for N interceptor vehicles."""

    _validate_count(len(vehicle_names))
    vehicles: dict[str, Any] = {}
    y_positions = _centered_positions(len(vehicle_names), float(y_spacing_m))
    for index, (name, y_pos) in enumerate(zip(vehicle_names, y_positions, strict=True)):
        position = (vehicle_positions_ned or {}).get(name, (0.0, float(y_pos), 0.0))
        vehicles[name] = _simpleflight_vehicle_settings(
            index=index,
            position_ned=position,
            tuned_terminal_camera=tuned_terminal_camera,
            lidar_range_m=lidar_range_m,
        )
    payload = _base_settings("Multirotor", fov_degrees=fov_degrees, api_port=api_port)
    payload["Vehicles"] = vehicles
    return _write_settings(path, payload)


def write_dynamic_computer_vision_settings(
    path: Path,
    *,
    camera_vehicle_names: tuple[str, ...],
    secondary_vehicle_names: tuple[str, ...] = (),
    camera_spacing_m: float = 20.0,
    camera_z: float = -10.0,
    secondary_height_above_targets_m: float = 50.0,
    target_z: float = -10.0,
    fov_degrees: float = 90.0,
    secondary_fov_degrees: float | None = None,
    secondary_camera_pitch_deg: float = -90.0,
    secondary_x_m: float = 50.0,
    secondary_y_spacing_m: float | None = None,
    width: int = 640,
    height: int = 480,
    secondary_width: int | None = None,
    secondary_height: int | None = None,
    api_port: int = 41451,
) -> Path:
    """Write an AirSim ComputerVision settings file for N cameras."""

    _validate_count(len(camera_vehicle_names))
    vehicles: dict[str, Any] = {}
    for name, y_pos in zip(
        camera_vehicle_names,
        _centered_positions(len(camera_vehicle_names), float(camera_spacing_m)),
        strict=True,
    ):
        vehicles[name] = _computer_vision_vehicle_settings(
            x=0.0,
            y=float(y_pos),
            z=float(camera_z),
        )
    secondary_spacing = (
        float(secondary_y_spacing_m)
        if secondary_y_spacing_m is not None
        else max(float(camera_spacing_m) * max(1, len(camera_vehicle_names) - 1), camera_spacing_m)
    )
    for index, name in enumerate(secondary_vehicle_names):
        y_pos = _centered_positions(max(1, len(secondary_vehicle_names)), secondary_spacing)[index]
        vehicle = _computer_vision_vehicle_settings(
            x=float(secondary_x_m),
            y=float(y_pos),
            z=float(target_z) - abs(float(secondary_height_above_targets_m)),
        )
        secondary_scene_width = int(secondary_width if secondary_width is not None else width)
        secondary_scene_height = int(secondary_height if secondary_height is not None else height)
        secondary_fov = float(secondary_fov_degrees if secondary_fov_degrees is not None else fov_degrees)
        vehicle["Cameras"] = {
            "0": {
                "X": 0,
                "Y": 0,
                "Z": 0,
                "Pitch": float(secondary_camera_pitch_deg),
                "Roll": 0,
                "Yaw": 0,
                "CaptureSettings": [
                    {
                        "ImageType": 0,
                        "Width": secondary_scene_width,
                        "Height": secondary_scene_height,
                        "FOV_Degrees": secondary_fov,
                        "MotionBlurAmount": 0,
                    },
                    {
                        "ImageType": 5,
                        "Width": secondary_scene_width,
                        "Height": secondary_scene_height,
                        "FOV_Degrees": secondary_fov,
                        "MotionBlurAmount": 0,
                    },
                ],
            }
        }
        vehicles[name] = vehicle
    payload = _base_settings(
        "ComputerVision",
        fov_degrees=fov_degrees,
        width=width,
        height=height,
        api_port=api_port,
        include_depth=True,
    )
    payload["Vehicles"] = vehicles
    return _write_settings(path, payload)


def default_2v2_actor_target_specs(
    *,
    target_z: float = -2.0,
    asset_name: str = "Quadrotor1",
    target_scale_m: float = 1.0,
) -> tuple[BlocksActorTargetSpec, ...]:
    """Default crossing horizontal actor targets for the first Blocks 2v2 run."""

    return (
        BlocksActorTargetSpec(
            object_id="TGT-001",
            actor_name="MSM_TargetActor_1",
            start_ned=(12.0, -6.0, float(target_z)),
            velocity_ned=(2.0, 0.6, 0.0),
            asset_name=asset_name,
            scale=(float(target_scale_m), float(target_scale_m), float(target_scale_m)),
            fallback_actor_name="OrangeBall",
        ),
        BlocksActorTargetSpec(
            object_id="TGT-002",
            actor_name="MSM_TargetActor_2",
            start_ned=(12.0, 6.0, float(target_z)),
            velocity_ned=(2.0, -0.6, 0.0),
            asset_name=asset_name,
            scale=(float(target_scale_m), float(target_scale_m), float(target_scale_m)),
            fallback_actor_name="PulsingCone",
        ),
    )


def default_5v5_actor_target_specs(
    *,
    target_z: float = -5.0,
    target_distance_m: float = 35.0,
    target_spacing_m: float = 10.0,
    asset_name: str = "Quadrotor1",
    target_scale_m: float = 2.0,
    target_speed_scale: float = 1.0,
) -> tuple[BlocksActorTargetSpec, ...]:
    """Default crossing horizontal actor targets for controlled 5v5 intercept."""

    return default_actor_target_specs(
        count=5,
        target_z=target_z,
        target_distance_m=target_distance_m,
        target_spacing_m=target_spacing_m,
        asset_name=asset_name,
        target_scale_m=target_scale_m,
        target_speed_scale=target_speed_scale,
        x_spacing_m=2.0,
        x_speed_base_mps=1.2,
        x_speed_step_mps=0.1,
        y_speed_span_mps=0.8,
    )


def default_cv_5v5_camera_vehicle_names() -> tuple[str, ...]:
    """Default ComputerVision interceptor camera vehicle names."""

    return default_cv_camera_vehicle_names(5)


def default_cv_5v5_secondary_vehicle_names() -> tuple[str, ...]:
    """Default ComputerVision secondary recon camera vehicle names."""

    return default_cv_secondary_vehicle_names(2)


def default_cv_5v5_actor_target_specs(
    *,
    target_z: float = -10.0,
    asset_name: str = "Quadrotor1",
    target_scale_m: float = 1.0,
) -> tuple[BlocksActorTargetSpec, ...]:
    """Default crossing actor targets for ComputerVision 5v5 replay."""

    return default_actor_target_specs(
        count=5,
        target_z=target_z,
        target_distance_m=35.0,
        target_spacing_m=10.0,
        asset_name=asset_name,
        target_scale_m=target_scale_m,
        target_speed_scale=1.0,
        x_spacing_m=4.0,
        x_speed_base_mps=1.4,
        x_speed_step_mps=0.1,
        y_speed_span_mps=1.2,
    )


def default_cv_5v5_d4d5_stress_actor_target_specs(
    *,
    target_z: float = -10.0,
    target_distance_m: float = 50.0,
    target_spacing_m: float = 20.0,
    target_scale_m: float = 10.0,
    asset_name: str = "Quadrotor1",
) -> tuple[BlocksActorTargetSpec, ...]:
    """5v5 D4/D5 stress geometry with 50 m camera standoff and 20 m spacing."""

    return default_actor_target_specs(
        count=5,
        target_z=target_z,
        target_distance_m=target_distance_m,
        target_spacing_m=target_spacing_m,
        asset_name=asset_name,
        target_scale_m=target_scale_m,
        target_speed_scale=1.0,
        x_spacing_m=0.0,
        x_speed_base_mps=0.8,
        x_speed_step_mps=0.1,
        y_speed_span_mps=0.7,
    )


def _validate_count(count: int) -> None:
    if int(count) <= 0:
        raise ValueError("count must be positive")


def _centered_positions(count: int, spacing: float) -> tuple[float, ...]:
    center = (int(count) - 1) * 0.5
    return tuple((index - center) * float(spacing) for index in range(int(count)))


def _symmetric_velocities(count: int, span: float) -> tuple[float, ...]:
    if int(count) == 1:
        return (0.0,)
    center = (int(count) - 1) * 0.5
    return tuple(-((index - center) / center) * float(span) for index in range(int(count)))


def _base_settings(
    sim_mode: str,
    *,
    fov_degrees: float,
    width: int = 640,
    height: int = 480,
    api_port: int,
    include_depth: bool = False,
) -> dict[str, Any]:
    capture_settings: list[dict[str, Any]] = [
        {
            "ImageType": 0,
            "Width": int(width),
            "Height": int(height),
            "FOV_Degrees": float(fov_degrees),
            "MotionBlurAmount": 0,
        }
    ]
    if include_depth:
        capture_settings.append(
            {
                "ImageType": 5,
                "Width": int(width),
                "Height": int(height),
                "FOV_Degrees": float(fov_degrees),
                "MotionBlurAmount": 0,
            }
        )
    return {
        "SeeDocsAt": "https://microsoft.github.io/AirSim/settings/",
        "SettingsVersion": 1.2,
        "SimMode": sim_mode,
        "EnableRpc": True,
        "RpcEnabled": True,
        "ApiServerPort": int(api_port),
        "LocalHostIp": "127.0.0.1",
        "ClockSpeed": 1.0,
        "ViewMode": "NoDisplay",
        "CameraDefaults": {"CaptureSettings": capture_settings},
        "SubWindows": [
            {
                "WindowID": 0,
                "CameraName": "0",
                "ImageType": 0,
                "Visible": False,
                "External": False,
            }
        ],
    }


def _simpleflight_vehicle_settings(
    *,
    index: int,
    position_ned: Vector3,
    tuned_terminal_camera: bool,
    lidar_range_m: float,
) -> dict[str, Any]:
    return {
        "VehicleType": "SimpleFlight",
        "DefaultVehicleState": "Inactive",
        "AutoCreate": True,
        "AllowAPIAlways": True,
        "EnableCollisionPassthrogh": False,
        "EnableCollisions": True,
        "EnableTrace": False,
        "X": float(position_ned[0]),
        "Y": float(position_ned[1]),
        "Z": float(position_ned[2]),
        "Pitch": 0,
        "Roll": 0,
        "Yaw": 0,
        "IsFpvVehicle": index == 0,
        "Cameras": {
            "0": {
                "X": 0.5 if tuned_terminal_camera else 0,
                "Y": 0,
                "Z": 0,
                "Pitch": 0,
                "Roll": 0,
                "Yaw": 0,
            }
        },
        "Sensors": {
            "LidarSensor1": {
                "SensorType": 6,
                "Enabled": True,
                "NumberOfChannels": 4,
                "Range": float(lidar_range_m),
                "PointsPerSecond": 8000,
                "RotationsPerSecond": 5,
                "HorizontalFOVStart": -45,
                "HorizontalFOVEnd": 45,
                "VerticalFOVUpper": 5,
                "VerticalFOVLower": -20,
                "X": 0,
                "Y": 0,
                "Z": -0.2,
                "Roll": 0,
                "Pitch": 0,
                "Yaw": 0,
                "DrawDebugPoints": False,
                "DataFrame": "VehicleInertialFrame",
            }
        },
        "RC": {
            "RemoteControlID": int(index),
            "AllowAPIWhenDisconnected": True,
        },
    }


def _computer_vision_vehicle_settings(*, x: float, y: float, z: float) -> dict[str, Any]:
    return {
        "VehicleType": "ComputerVision",
        "X": float(x),
        "Y": float(y),
        "Z": float(z),
        "Pitch": 0,
        "Roll": 0,
        "Yaw": 0,
    }


def _write_settings(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path
