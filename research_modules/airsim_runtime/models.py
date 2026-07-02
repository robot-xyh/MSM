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
    asset_name: str = "1M_Cube_Chamfer"
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
    camera_name: str = "0"
    lidar_vehicle_name: str = "Interceptor"
    lidar_vehicle_names: tuple[str, ...] = ()
    lidar_name: str = "LidarSensor1"
    target_vehicle_names: tuple[str, ...] = ("Intruder",)
    resource_vehicle_names: tuple[str, ...] = ("Interceptor",)
    target_actor_specs: tuple[BlocksActorTargetSpec, ...] = ()
    detection_filter_names: tuple[str, ...] = ("MSM_TargetActor_*",)
    detection_radius_cm: int = 80 * 100
    destroy_spawned_actor_targets: bool = True
    include_integrated_pipeline: bool = True
    execute_intercept: bool = False
    control_dt_s: float = 0.1
    intercept_speed_mps: float = 6.0
    intercept_altitude_ned_z: float = -2.0
    intercept_radius_m: float = 0.75
    intercept_max_duration_s: float = 8.0
    intercept_navigation_constant: float = 3.0
    intercept_terminal_switch_range_m: float = 8.0
    intercept_detection_timeout_s: float = 1.0
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
        return self.camera_vehicle_names or (self.camera_vehicle_name,)

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


@dataclass(frozen=True)
class BlocksSequenceResult:
    """Result from a staged Blocks sequence launched once by main."""

    sequence_id: str
    connected: bool
    episode_results: tuple[BlocksSmokeResult, ...]
    output_paths: dict[str, Path]
    metadata: dict[str, Any] = field(default_factory=dict)


def default_2v2_actor_target_specs(
    *,
    target_z: float = -2.0,
) -> tuple[BlocksActorTargetSpec, ...]:
    """Default crossing horizontal actor targets for the first Blocks 2v2 run."""

    return (
        BlocksActorTargetSpec(
            object_id="TGT-001",
            actor_name="MSM_TargetActor_1",
            start_ned=(12.0, -6.0, float(target_z)),
            velocity_ned=(2.0, 0.6, 0.0),
            fallback_actor_name="OrangeBall",
        ),
        BlocksActorTargetSpec(
            object_id="TGT-002",
            actor_name="MSM_TargetActor_2",
            start_ned=(12.0, 6.0, float(target_z)),
            velocity_ned=(2.0, -0.6, 0.0),
            fallback_actor_name="PulsingCone",
        ),
    )
