"""AirSim runtime for the independent dual-optical association experiment."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import csv
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
from typing import Any, Iterable, Mapping, Sequence

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from .core import (
    AnonymousDetection,
    BearingTrack,
    CameraSpec,
    CameraState,
    CrossAssociationResult,
    RayObservation,
    ScanRevisitTracker,
    ScenarioConfig,
    TargetSpec,
    associate_tracks,
    generate_target_specs,
    look_angles_deg,
    minimum_target_separation,
    online_truth_leakage_keys,
    project_world_point,
    ray_observation_from_detection,
    scan_yaw_deg,
    sweep_index,
)


@dataclass(frozen=True)
class ExperimentResult:
    output_dir: Path
    settings_path: Path
    metrics_path: Path
    metrics: dict[str, Any]
    output_paths: dict[str, Path]
    tracks_a: tuple[BearingTrack, ...]
    tracks_b: tuple[BearingTrack, ...]
    association: CrossAssociationResult
    target_specs: tuple[TargetSpec, ...]


class LocalBlocksProcess:
    """Launch one Blocks process with an experiment-local settings file."""

    def __init__(
        self,
        blocks_script: Path,
        settings_path: Path,
        output_dir: Path,
        *,
        api_port: int,
        prefer_nvidia_offload: bool = True,
    ) -> None:
        self.blocks_script = Path(blocks_script)
        self.settings_path = Path(settings_path)
        self.output_dir = Path(output_dir)
        self.api_port = int(api_port)
        self.prefer_nvidia_offload = bool(prefer_nvidia_offload)
        self.process: subprocess.Popen[str] | None = None
        self._log_stream: Any = None

    @property
    def log_path(self) -> Path:
        return self.output_dir / "blocks_stdout_stderr.log"

    def start(self) -> None:
        script = self.blocks_script.resolve()
        settings = self.settings_path.resolve()
        if not script.exists():
            raise FileNotFoundError(f"Blocks script not found: {script}")
        if not settings.exists():
            raise FileNotFoundError(f"settings file not found: {settings}")
        if _tcp_port_open("127.0.0.1", self.api_port):
            raise RuntimeError(f"AirSim RPC port {self.api_port} is already open")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._log_stream = self.log_path.open("w", encoding="utf-8")
        environment = os.environ.copy()
        if self.prefer_nvidia_offload:
            environment.setdefault("__NV_PRIME_RENDER_OFFLOAD", "1")
            environment.setdefault("__GLX_VENDOR_LIBRARY_NAME", "nvidia")
            environment.setdefault("__VK_LAYER_NV_optimus", "NVIDIA_only")
        command = [
            str(script),
            f"-settings={settings}",
            "-windowed",
            "-ResX=1280",
            "-ResY=720",
            "-NoVSync",
            "-NoHMD",
            "-NoSound",
        ]
        if not os.access(script, os.X_OK):
            command.insert(0, "bash")
        self.process = subprocess.Popen(
            command,
            cwd=str(script.parent),
            stdout=self._log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            start_new_session=True,
        )

    def stop(self, timeout_s: float = 10.0) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                process.terminate()
            deadline = time.monotonic() + timeout_s
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.2)
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    process.kill()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                pass
        if self._log_stream is not None:
            self._log_stream.close()
            self._log_stream = None
        deadline = time.monotonic() + timeout_s
        while _tcp_port_open("127.0.0.1", self.api_port) and time.monotonic() < deadline:
            time.sleep(0.2)

    def diagnostics(self) -> dict[str, Any]:
        log_text = (
            self.log_path.read_text(encoding="utf-8", errors="replace")
            if self.log_path.exists()
            else ""
        )
        settings_path = str(self.settings_path.resolve())
        return {
            "settings_path": settings_path,
            "settings_loaded": "Loaded settings from" in log_text
            and settings_path in log_text,
            "engine_initialized": "Engine is initialized" in log_text,
            "game_mode_seen": "Game class is 'AirSimGameMode'" in log_text,
            "rpc_port_open": _tcp_port_open("127.0.0.1", self.api_port),
            "process_returncode": None if self.process is None else self.process.poll(),
            "log_tail": "\n".join(log_text.splitlines()[-80:]),
        }


def write_airsim_settings(
    path: Path, config: ScenarioConfig, camera_spec: CameraSpec
) -> Path:
    capture = {
        "ImageType": 0,
        "Width": int(camera_spec.width),
        "Height": int(camera_spec.height),
        "FOV_Degrees": float(camera_spec.horizontal_fov_deg),
        "MotionBlurAmount": 0,
    }

    def vehicle(position: Sequence[float]) -> dict[str, Any]:
        return {
            "VehicleType": "ComputerVision",
            "AutoCreate": True,
            "AllowAPIAlways": True,
            "X": float(position[0]),
            "Y": float(position[1]),
            "Z": float(position[2]),
            "Pitch": 0,
            "Roll": 0,
            "Yaw": 0,
            "Cameras": {
                config.camera_name: {
                    "X": 0,
                    "Y": 0,
                    "Z": 0,
                    "Pitch": 0,
                    "Roll": 0,
                    "Yaw": 0,
                    "CaptureSettings": [dict(capture)],
                }
            },
        }

    payload = {
        "SeeDocsAt": "https://microsoft.github.io/AirSim/settings/",
        "SettingsVersion": 1.2,
        "SimMode": "ComputerVision",
        "EnableRpc": True,
        "RpcEnabled": True,
        "ApiServerPort": int(config.api_port),
        "LocalHostIp": "127.0.0.1",
        "ClockSpeed": float(config.clock_speed),
        "ViewMode": "NoDisplay",
        "CameraDefaults": {"CaptureSettings": [dict(capture)]},
        "SubWindows": [],
        "Vehicles": {
            config.camera_a_name: vehicle(config.camera_a_position_ned),
            config.camera_b_name: vehicle(config.camera_b_position_ned),
        },
    }
    return write_json(path, payload)


class DualOpticalAirSimRunner:
    def __init__(
        self,
        *,
        config: ScenarioConfig,
        camera_spec: CameraSpec,
        output_dir: Path,
        blocks_script: Path,
        launch_blocks: bool = True,
        connection_timeout_s: float = 90.0,
        client_timeout_s: float = 10.0,
        save_keyframes: bool = True,
        prefer_nvidia_offload: bool = True,
        client: Any | None = None,
        airsim_module: Any | None = None,
    ) -> None:
        self.config = config
        self.camera_spec = camera_spec
        self.output_dir = Path(output_dir)
        self.blocks_script = Path(blocks_script)
        self.launch_blocks = bool(launch_blocks)
        self.connection_timeout_s = float(connection_timeout_s)
        self.client_timeout_s = float(client_timeout_s)
        self.save_keyframes = bool(save_keyframes)
        self.prefer_nvidia_offload = bool(prefer_nvidia_offload)
        self._client = client
        self._airsim = airsim_module

    def run(self) -> ExperimentResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        settings_path = write_airsim_settings(
            self.output_dir / "settings.json", self.config, self.camera_spec
        )
        target_specs = generate_target_specs(self.config)
        write_json(
            self.output_dir / "scenario.json",
            {
                "schema_version": "dual-optical-40target-scenario-v1",
                "independent_experiment": True,
                "connected_d_modules": [],
                "scenario": asdict(self.config),
                "camera": asdict(self.camera_spec)
                | {
                    "vertical_fov_deg": self.camera_spec.vertical_fov_deg,
                    "effective_ifov_mrad": self.camera_spec.effective_ifov_mrad,
                },
                "minimum_target_separation_m": minimum_target_separation(
                    target_specs, self.config.duration_s
                ),
                "target_specs_offline_truth_only": [
                    asdict(target) for target in target_specs
                ],
            },
        )
        process = LocalBlocksProcess(
            self.blocks_script,
            settings_path,
            self.output_dir,
            api_port=self.config.api_port,
            prefer_nvidia_offload=self.prefer_nvidia_offload,
        )
        if self.launch_blocks:
            process.start()
        try:
            airsim_module, client = self._connect()
            preflight = self._run_preflight(airsim_module, client)
            write_json(self.output_dir / "preflight.json", preflight)
            if not bool(preflight.get("passed")):
                raise RuntimeError(
                    f"preflight failed: {preflight.get('failure_reason', 'unknown')}"
                )
            client.reset()
            time.sleep(1.0)
            self._client = self._new_client()
            self._wait_for_client()
            client = self._client
            result = self._run_formal_episode(
                airsim_module,
                client,
                target_specs,
                float(preflight["final_scale_multiplier"]),
                settings_path,
            )
        except Exception as exc:
            write_json(
                self.output_dir / "failure.json",
                {
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                    "independent_experiment": True,
                },
            )
            raise
        finally:
            try:
                if self._client is not None:
                    self._client.simPause(False)
            except Exception:
                pass
            if self.launch_blocks:
                process.stop()
            write_json(
                self.output_dir / "blocks_diagnostics.json", process.diagnostics()
            )
        return result

    def _connect(self) -> tuple[Any, Any]:
        if self._airsim is None:
            import airsim as airsim_module

            self._airsim = airsim_module
        if self._client is None:
            self._client = self._airsim.VehicleClient(
                ip="127.0.0.1",
                port=self.config.api_port,
                timeout_value=self.client_timeout_s,
            )
        self._wait_for_client()
        return self._airsim, self._client

    def _new_client(self) -> Any:
        return self._airsim.VehicleClient(
            ip="127.0.0.1",
            port=self.config.api_port,
            timeout_value=self.client_timeout_s,
        )

    def _wait_for_client(self) -> None:
        deadline = time.monotonic() + self.connection_timeout_s
        last_error = ""
        while time.monotonic() < deadline:
            try:
                if self._client.ping():
                    return
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            # AirSim 1.8.1 msgpack-rpc does not recover a transport that first
            # connected before Blocks opened the port.
            try:
                self._client = self._new_client()
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.5)
        raise TimeoutError(f"AirSim connection timed out: {last_error}")

    def _run_preflight(self, airsim_module: Any, client: Any) -> dict[str, Any]:
        config = self.config
        camera = self.camera_spec
        base_yaw, fixed_pitch = look_angles_deg(
            config.camera_a_position_ned, config.corridor_center_ned
        )
        calibration_range = 120.0
        yaw_rad = math.radians(base_yaw)
        pitch_rad = math.radians(fixed_pitch)
        forward = np.asarray(
            (
                math.cos(pitch_rad) * math.cos(yaw_rad),
                math.cos(pitch_rad) * math.sin(yaw_rad),
                -math.sin(pitch_rad),
            ),
            dtype=float,
        )
        position = np.asarray(config.camera_a_position_ned, dtype=float) + forward * calibration_range
        calibration_name = "MSM_DualOptical_Calibration_Target"
        try:
            client.simDestroyObject(calibration_name)
        except Exception:
            pass
        client.simPause(False)
        for camera_id, camera_position in config.camera_positions.items():
            camera_yaw, camera_pitch = look_angles_deg(
                camera_position, config.corridor_center_ned
            )
            client.simSetCameraFov(
                config.camera_name,
                camera.horizontal_fov_deg,
                vehicle_name=camera_id,
            )
            client.simSetCameraPose(
                config.camera_name,
                _camera_pose(airsim_module, camera_yaw, camera_pitch),
                vehicle_name=camera_id,
            )
        spawned_name = client.simSpawnObject(
            calibration_name,
            config.target_asset_name,
            _world_pose(airsim_module, position, 0.0),
            airsim_module.Vector3r(1.0, 1.0, 1.0),
            False,
        )
        actual_name = str(spawned_name or calibration_name)
        if not spawned_name:
            return {
                "passed": False,
                "failure_reason": "calibration_actor_spawn_failed",
                "requested_actor_name": calibration_name,
            }
        self._configure_detection_filters(
            client,
            config.camera_a_name,
            (actual_name, config.target_asset_name, f"{config.target_asset_name}*"),
        )
        initial = _wait_for_detection(
            client,
            airsim_module,
            config,
            config.camera_a_name,
            timeout_s=8.0,
        )
        initial_extent = _box3d_longest_extent(initial)
        if initial is None or initial_extent is None or initial_extent <= 0.0:
            client.simDestroyObject(actual_name)
            return {
                "passed": False,
                "failure_reason": "box3d_scale_measurement_unavailable",
                "spawned_actor_name": actual_name,
                "initial_detection_count": len(
                    client.simGetDetections(
                        config.camera_name,
                        airsim_module.ImageType.Scene,
                        vehicle_name=config.camera_a_name,
                    )
                ),
            }
        multiplier = config.target_longest_dimension_m / initial_extent
        client.simSetObjectScale(
            actual_name,
            airsim_module.Vector3r(multiplier, multiplier, multiplier),
        )
        final_detection = _wait_for_detection(
            client,
            airsim_module,
            config,
            config.camera_a_name,
            timeout_s=4.0,
        )
        final_extent = _box3d_longest_extent(final_detection)
        if final_extent is not None and final_extent > 0.0:
            correction = config.target_longest_dimension_m / final_extent
            if not math.isclose(correction, 1.0, abs_tol=0.01):
                multiplier *= correction
                client.simSetObjectScale(
                    actual_name,
                    airsim_module.Vector3r(multiplier, multiplier, multiplier),
                )
                final_detection = _wait_for_detection(
                    client,
                    airsim_module,
                    config,
                    config.camera_a_name,
                    timeout_s=4.0,
                )
                final_extent = _box3d_longest_extent(final_detection)
        reported_scale = client.simGetObjectScale(actual_name)
        client.simDestroyObject(actual_name)
        camera_validation = self._validate_cameras(airsim_module, client)
        passed = bool(
            final_extent is not None
            and abs(final_extent - config.target_longest_dimension_m)
            <= config.target_dimension_tolerance_m
            and all(
                bool(item.get("passed"))
                for item in camera_validation.values()
            )
        )
        return {
            "passed": passed,
            "failure_reason": "" if passed else "camera_or_target_dimension_preflight_failed",
            "camera_validation": camera_validation,
            "spawned_actor_name": actual_name,
            "native_longest_extent_m": initial_extent,
            "final_longest_extent_m": final_extent,
            "requested_longest_extent_m": config.target_longest_dimension_m,
            "tolerance_m": config.target_dimension_tolerance_m,
            "final_scale_multiplier": multiplier,
            "reported_object_scale": _vector3_to_list(reported_scale),
            "fixed_pitch_deg": fixed_pitch,
            "base_yaw_deg": base_yaw,
        }

    def _validate_cameras(self, airsim_module: Any, client: Any) -> dict[str, Any]:
        validation: dict[str, Any] = {}
        for camera_id in self.config.camera_positions:
            info = client.simGetCameraInfo(
                self.config.camera_name, vehicle_name=camera_id
            )
            responses = client.simGetImages(
                [
                    airsim_module.ImageRequest(
                        self.config.camera_name,
                        airsim_module.ImageType.Scene,
                        False,
                        True,
                    )
                ],
                vehicle_name=camera_id,
            )
            response = responses[0] if responses else None
            actual_position = _vector3_to_list(info.pose.position)
            # ComputerVision API poses are relative to the initial positions
            # declared in settings.json.
            expected_position = [0.0, 0.0, 0.0]
            position_error = float(
                np.linalg.norm(
                    np.asarray(actual_position, dtype=float)
                    - np.asarray(expected_position, dtype=float)
                )
            )
            validation[camera_id] = {
                "horizontal_fov_deg": float(info.fov),
                "width": 0 if response is None else int(response.width),
                "height": 0 if response is None else int(response.height),
                "actual_position_ned": actual_position,
                "expected_position_ned": expected_position,
                "configured_initial_position_ned": list(
                    self.config.camera_positions[camera_id]
                ),
                "position_error_m": position_error,
                "passed": bool(
                    response is not None
                    and int(response.width) == self.camera_spec.width
                    and int(response.height) == self.camera_spec.height
                    and math.isclose(
                        float(info.fov),
                        self.camera_spec.horizontal_fov_deg,
                        abs_tol=1e-3,
                    )
                    and position_error <= 1e-3
                ),
            }
        return validation

    def _run_formal_episode(
        self,
        airsim_module: Any,
        client: Any,
        target_specs: tuple[TargetSpec, ...],
        target_scale: float,
        settings_path: Path,
    ) -> ExperimentResult:
        config = self.config
        camera_spec = self.camera_spec
        actor_name_by_truth: dict[str, str] = {}
        client.simPause(False)
        for target in target_specs:
            try:
                client.simDestroyObject(target.actor_name)
            except Exception:
                pass
            yaw = math.degrees(
                math.atan2(target.velocity_ned[1], target.velocity_ned[0])
            )
            spawned = client.simSpawnObject(
                target.actor_name,
                target.asset_name,
                _world_pose(airsim_module, target.start_ned, yaw),
                airsim_module.Vector3r(target_scale, target_scale, target_scale),
                False,
            )
            if not spawned:
                raise RuntimeError(f"failed to spawn actor {target.actor_name}")
            actor_name_by_truth[target.truth_id] = str(spawned)
            time.sleep(0.01)
        time.sleep(1.50)
        registered_targets = set(
            str(name)
            for name in client.simListSceneObjects(".*MSM_DualOptical_Target_.*")
        )
        missing_targets = sorted(set(actor_name_by_truth.values()) - registered_targets)
        if missing_targets:
            raise RuntimeError(
                f"spawned actors not registered in scene: {missing_targets[:5]}"
            )
        filter_names = tuple(actor_name_by_truth.values()) + (
            "MSM_DualOptical_Target_*",
            config.target_asset_name,
            f"{config.target_asset_name}*",
        )
        for camera_id in config.camera_positions:
            self._configure_detection_filters(client, camera_id, filter_names)
            client.simSetCameraFov(
                config.camera_name,
                camera_spec.horizontal_fov_deg,
                vehicle_name=camera_id,
            )
        fixed_angles = {
            camera_id: look_angles_deg(position, config.corridor_center_ned)
            for camera_id, position in config.camera_positions.items()
        }
        trackers = {
            camera_id: ScanRevisitTracker(
                camera_id, max_coast_s=config.track_coast_s
            )
            for camera_id in config.camera_positions
        }
        online_detection_rows: list[dict[str, Any]] = []
        offline_detection_rows: list[dict[str, Any]] = []
        scan_rows: list[dict[str, Any]] = []
        target_truth_rows: list[dict[str, Any]] = []
        keyframe_rows: list[dict[str, Any]] = []
        uid_truth: dict[str, str] = {}
        rpc_latencies_ms: list[float] = []
        detection_truth_by_camera: dict[str, set[str]] = {
            camera_id: set() for camera_id in config.camera_positions
        }
        target_by_truth = {target.truth_id: target for target in target_specs}
        actor_to_truth = {
            actor_name: truth_id for truth_id, actor_name in actor_name_by_truth.items()
        }
        keyframe_indices = _keyframe_indices(config)
        wall_started = time.perf_counter()
        for frame_index in range(config.frame_count):
            timestamp = frame_index * config.dt_s
            current_positions: dict[str, tuple[float, float, float]] = {}
            for target in target_specs:
                position = target.position_at(timestamp)
                current_positions[target.truth_id] = position
                actor_name = actor_name_by_truth[target.truth_id]
                yaw = math.degrees(
                    math.atan2(target.velocity_ned[1], target.velocity_ned[0])
                )
                moved = frame_index == 0 or _set_object_pose_with_retry(
                    client,
                    actor_name,
                    _world_pose(airsim_module, position, yaw),
                    timeout_s=0.05,
                )
                if not moved:
                    raise RuntimeError(f"failed to move actor {actor_name}")
                target_truth_rows.append(
                    {
                        "frame_index": frame_index,
                        "simulation_timestamp": timestamp,
                        "truth_id": target.truth_id,
                        "actor_name": actor_name,
                        "px_ned_m": position[0],
                        "py_ned_m": position[1],
                        "pz_ned_m": position[2],
                        "vx_ned_mps": target.velocity_ned[0],
                        "vy_ned_mps": target.velocity_ned[1],
                        "vz_ned_mps": target.velocity_ned[2],
                        "offline_truth_only": True,
                    }
                )
            states: dict[str, CameraState] = {}
            for camera_id, position in config.camera_positions.items():
                base_yaw, fixed_pitch = fixed_angles[camera_id]
                yaw = scan_yaw_deg(
                    timestamp,
                    base_yaw,
                    half_span_deg=config.scan_half_span_deg,
                    period_s=config.scan_period_s,
                )
                client.simSetCameraPose(
                    config.camera_name,
                    _camera_pose(airsim_module, yaw, fixed_pitch),
                    vehicle_name=camera_id,
                )
                state = CameraState(
                    camera_id=camera_id,
                    frame_index=frame_index,
                    timestamp=timestamp,
                    position_ned=position,
                    yaw_deg=yaw,
                    pitch_deg=fixed_pitch,
                )
                states[camera_id] = state
            # This Blocks build does not implement paused simContinueForTime.
            # Actors are scripted poses, so logical time remains deterministic
            # while a short wall-time yield lets Unreal refresh the scene.
            time.sleep(0.002)
            for camera_id, state in states.items():
                started = time.perf_counter()
                raw_detections = client.simGetDetections(
                    config.camera_name,
                    airsim_module.ImageType.Scene,
                    vehicle_name=camera_id,
                )
                latency_ms = (time.perf_counter() - started) * 1000.0
                rpc_latencies_ms.append(latency_ms)
                anonymous, offline = self._anonymize_detections(
                    raw_detections,
                    camera_id=camera_id,
                    frame_index=frame_index,
                    timestamp=timestamp,
                    arrival_timestamp=timestamp + latency_ms / 1000.0,
                    camera_state=state,
                    current_positions=current_positions,
                    actor_to_truth=actor_to_truth,
                )
                observations: list[RayObservation] = []
                for detection in anonymous:
                    online_detection_rows.append(asdict(detection))
                    observations.append(
                        ray_observation_from_detection(
                            detection,
                            state,
                            camera_spec,
                            scan_period_s=config.scan_period_s,
                        )
                    )
                for row in offline:
                    offline_detection_rows.append(row)
                    truth_id = str(row.get("truth_id") or "")
                    if truth_id:
                        uid_truth[str(row["detection_uid"])] = truth_id
                        detection_truth_by_camera[camera_id].add(truth_id)
                current_sweep = sweep_index(
                    timestamp, period_s=config.scan_period_s
                )
                trackers[camera_id].update(
                    sweep_index=current_sweep,
                    timestamp=timestamp,
                    observations=observations,
                )
                scan_rows.append(
                    {
                        "camera_id": camera_id,
                        "frame_index": frame_index,
                        "measurement_timestamp": timestamp,
                        "sweep_index": current_sweep,
                        "yaw_deg": state.yaw_deg,
                        "pitch_deg": state.pitch_deg,
                        "detection_count": len(anonymous),
                        "detection_rpc_latency_ms": latency_ms,
                    }
                )
                if self.save_keyframes and frame_index in keyframe_indices:
                    keyframe = self._capture_keyframe(
                        airsim_module,
                        client,
                        camera_id,
                        frame_index,
                        timestamp,
                    )
                    if keyframe is not None:
                        keyframe_rows.append(keyframe)
        wall_duration_s = time.perf_counter() - wall_started
        for tracker in trackers.values():
            tracker.flush()
        tracks_a = trackers[config.camera_a_name].stable_tracks(
            config.stable_sweep_count
        )
        tracks_b = trackers[config.camera_b_name].stable_tracks(
            config.stable_sweep_count
        )
        association_started = time.perf_counter()
        association = associate_tracks(
            tracks_a,
            tracks_b,
            expected_speed_mps=config.target_speed_mps,
            max_time_delta_s=config.max_cross_camera_time_delta_s,
        )
        association_wall_ms = (time.perf_counter() - association_started) * 1000.0
        return self._write_formal_outputs(
            settings_path=settings_path,
            target_specs=target_specs,
            target_scale=target_scale,
            actor_name_by_truth=actor_name_by_truth,
            trackers=trackers,
            tracks_a=tracks_a,
            tracks_b=tracks_b,
            association=association,
            online_detection_rows=online_detection_rows,
            offline_detection_rows=offline_detection_rows,
            scan_rows=scan_rows,
            target_truth_rows=target_truth_rows,
            keyframe_rows=keyframe_rows,
            uid_truth=uid_truth,
            detection_truth_by_camera=detection_truth_by_camera,
            target_by_truth=target_by_truth,
            rpc_latencies_ms=rpc_latencies_ms,
            wall_duration_s=wall_duration_s,
            association_wall_ms=association_wall_ms,
        )

    def _configure_detection_filters(
        self, client: Any, camera_id: str, names: Sequence[str]
    ) -> None:
        config = self.config
        import airsim

        client.simClearDetectionMeshNames(
            config.camera_name,
            airsim.ImageType.Scene,
            vehicle_name=camera_id,
        )
        client.simSetDetectionFilterRadius(
            config.camera_name,
            airsim.ImageType.Scene,
            350_000,
            vehicle_name=camera_id,
        )
        for name in dict.fromkeys(str(item) for item in names if str(item)):
            client.simAddDetectionFilterMeshName(
                config.camera_name,
                airsim.ImageType.Scene,
                name,
                vehicle_name=camera_id,
            )

    def _anonymize_detections(
        self,
        raw_detections: Sequence[Any],
        *,
        camera_id: str,
        frame_index: int,
        timestamp: float,
        arrival_timestamp: float,
        camera_state: CameraState,
        current_positions: Mapping[str, tuple[float, float, float]],
        actor_to_truth: Mapping[str, str],
    ) -> tuple[list[AnonymousDetection], list[dict[str, Any]]]:
        anonymous: list[AnonymousDetection] = []
        offline: list[dict[str, Any]] = []
        boxes: list[tuple[float, float, float, float]] = []
        for raw in raw_detections:
            bbox = _bbox2d(raw)
            if bbox is None:
                continue
            boxes.append(bbox)
        truth_assignments = _offline_truth_assignments(
            boxes,
            current_positions,
            camera_state,
            self.camera_spec,
        )
        box_index = 0
        for raw_index, raw in enumerate(raw_detections):
            bbox = _bbox2d(raw)
            if bbox is None:
                continue
            detection_uid = f"{camera_id}-F{frame_index:05d}-D{box_index:03d}"
            center = ((bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5)
            anonymous.append(
                AnonymousDetection(
                    detection_uid=detection_uid,
                    camera_id=camera_id,
                    frame_index=frame_index,
                    measurement_timestamp=timestamp,
                    arrival_timestamp=arrival_timestamp,
                    bbox_xyxy=bbox,
                    center_px=center,
                    confidence=1.0,
                )
            )
            raw_name = str(getattr(raw, "name", "") or "")
            truth_id = actor_to_truth.get(raw_name, "")
            assignment = truth_assignments.get(box_index)
            if not truth_id and assignment is not None:
                truth_id = assignment[0]
            offline.append(
                {
                    "detection_uid": detection_uid,
                    "camera_id": camera_id,
                    "frame_index": frame_index,
                    "measurement_timestamp": timestamp,
                    "truth_id": truth_id,
                    "raw_detection_name": raw_name,
                    "truth_assignment_pixel_error": None
                    if assignment is None
                    else assignment[1],
                    "relative_pose": _pose_to_dict(
                        getattr(raw, "relative_pose", None)
                    ),
                    "box3d": _box3d_to_dict(getattr(raw, "box3D", None)),
                    "offline_truth_only": True,
                }
            )
            box_index += 1
        return anonymous, offline

    def _capture_keyframe(
        self,
        airsim_module: Any,
        client: Any,
        camera_id: str,
        frame_index: int,
        timestamp: float,
    ) -> dict[str, Any] | None:
        responses = client.simGetImages(
            [
                airsim_module.ImageRequest(
                    self.config.camera_name,
                    airsim_module.ImageType.Scene,
                    False,
                    True,
                )
            ],
            vehicle_name=camera_id,
        )
        if not responses or not responses[0].image_data_uint8:
            return None
        response = responses[0]
        relative = Path("keyframes") / camera_id / f"frame_{frame_index:05d}.png"
        path = self.output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(response.image_data_uint8))
        return {
            "camera_id": camera_id,
            "frame_index": frame_index,
            "measurement_timestamp": timestamp,
            "airsim_image_timestamp": int(getattr(response, "time_stamp", 0)),
            "width": int(response.width),
            "height": int(response.height),
            "path": str(relative),
        }

    def _write_formal_outputs(
        self,
        *,
        settings_path: Path,
        target_specs: tuple[TargetSpec, ...],
        target_scale: float,
        actor_name_by_truth: Mapping[str, str],
        trackers: Mapping[str, ScanRevisitTracker],
        tracks_a: tuple[BearingTrack, ...],
        tracks_b: tuple[BearingTrack, ...],
        association: CrossAssociationResult,
        online_detection_rows: list[dict[str, Any]],
        offline_detection_rows: list[dict[str, Any]],
        scan_rows: list[dict[str, Any]],
        target_truth_rows: list[dict[str, Any]],
        keyframe_rows: list[dict[str, Any]],
        uid_truth: Mapping[str, str],
        detection_truth_by_camera: Mapping[str, set[str]],
        target_by_truth: Mapping[str, TargetSpec],
        rpc_latencies_ms: list[float],
        wall_duration_s: float,
        association_wall_ms: float,
    ) -> ExperimentResult:
        online_dir = self.output_dir / "online"
        truth_dir = self.output_dir / "truth"
        track_rows: list[dict[str, Any]] = []
        sample_rows: list[dict[str, Any]] = []
        uid_to_track: dict[str, str] = {}
        track_truth_rows: list[dict[str, Any]] = []
        track_truth: dict[str, str] = {}
        for tracker in trackers.values():
            for track in tracker.tracks:
                stable = track.is_stable(self.config.stable_sweep_count)
                track_rows.append(
                    {
                        "track_id": track.track_id,
                        "camera_id": track.camera_id,
                        "stable": stable,
                        "sweep_count": track.stable_sweep_count,
                        "sample_count": len(track.samples),
                        "first_timestamp": track.samples[0].timestamp,
                        "last_timestamp": track.samples[-1].timestamp,
                    }
                )
                for sample_index, sample in enumerate(track.samples):
                    sample_rows.append(
                        {
                            "track_id": track.track_id,
                            "camera_id": track.camera_id,
                            "sample_index": sample_index,
                            "sweep_index": sample.sweep_index,
                            "measurement_timestamp": sample.timestamp,
                            "ray_x_ned": sample.direction_ned[0],
                            "ray_y_ned": sample.direction_ned[1],
                            "ray_z_ned": sample.direction_ned[2],
                            "azimuth_deg": sample.azimuth_deg,
                            "elevation_deg": sample.elevation_deg,
                            "detection_uids": list(sample.detection_uids),
                        }
                    )
                    for uid in sample.detection_uids:
                        uid_to_track[uid] = track.track_id
                truth_values = [
                    uid_truth[uid]
                    for uid in track.detection_uids
                    if uid in uid_truth and uid_truth[uid]
                ]
                counts = Counter(truth_values)
                majority_truth, majority_count = (
                    counts.most_common(1)[0] if counts else ("", 0)
                )
                purity = majority_count / len(truth_values) if truth_values else None
                if majority_truth:
                    track_truth[track.track_id] = majority_truth
                track_truth_rows.append(
                    {
                        "track_id": track.track_id,
                        "camera_id": track.camera_id,
                        "stable": stable,
                        "majority_truth_id": majority_truth,
                        "purity": purity,
                        "scored_detection_count": len(truth_values),
                        "offline_truth_only": True,
                    }
                )
        candidate_rows = [asdict(item) for item in association.candidates]
        match_rows = [asdict(item) for item in association.matches]
        scored_match_rows: list[dict[str, Any]] = []
        correct_truth_ids: list[str] = []
        position_errors: list[float] = []
        velocity_errors: list[float] = []
        for match in association.matches:
            truth_a = track_truth.get(match.track_a_id, "")
            truth_b = track_truth.get(match.track_b_id, "")
            correct = bool(truth_a and truth_a == truth_b)
            position_error = None
            velocity_error = None
            if correct:
                correct_truth_ids.append(truth_a)
                target = target_by_truth[truth_a]
                position_error = float(
                    np.linalg.norm(
                        np.asarray(match.position_ned)
                        - np.asarray(target.position_at(match.reference_timestamp))
                    )
                )
                velocity_error = float(
                    np.linalg.norm(
                        np.asarray(match.velocity_ned)
                        - np.asarray(target.velocity_ned)
                    )
                )
                position_errors.append(position_error)
                velocity_errors.append(velocity_error)
            scored_match_rows.append(
                {
                    "match_id": match.match_id,
                    "track_a_id": match.track_a_id,
                    "track_b_id": match.track_b_id,
                    "truth_a": truth_a,
                    "truth_b": truth_b,
                    "correct": correct,
                    "position_error_m": position_error,
                    "velocity_error_mps": velocity_error,
                    "offline_truth_only": True,
                }
            )
        stable_truth_by_camera: dict[str, set[str]] = {}
        for camera_id in self.config.camera_positions:
            stable_truth_by_camera[camera_id] = {
                track_truth[track.track_id]
                for track in trackers[camera_id].stable_tracks(
                    self.config.stable_sweep_count
                )
                if track.track_id in track_truth
            }
        eligible_truth = set.intersection(*stable_truth_by_camera.values())
        correct_count = sum(bool(row["correct"]) for row in scored_match_rows)
        precision = (
            correct_count / len(scored_match_rows) if scored_match_rows else None
        )
        full_recall = correct_count / self.config.target_count
        eligible_recall = (
            correct_count / len(eligible_truth) if eligible_truth else None
        )
        duplicate_truth_match_count = sum(
            max(0, count - 1) for count in Counter(correct_truth_ids).values()
        )
        online_records = [
            *online_detection_rows,
            *scan_rows,
            *track_rows,
            *sample_rows,
            *candidate_rows,
            *match_rows,
        ]
        leakage_keys = online_truth_leakage_keys(online_records)
        pitch_by_camera = {
            camera_id: [
                float(row["pitch_deg"])
                for row in scan_rows
                if row["camera_id"] == camera_id
            ]
            for camera_id in self.config.camera_positions
        }
        metrics = {
            "schema_version": "dual-optical-40target-metrics-v1",
            "independent_experiment": True,
            "connected_d_modules": [],
            "seed": self.config.seed,
            "target_count": self.config.target_count,
            "spawned_target_count": len(actor_name_by_truth),
            "target_scale_multiplier": target_scale,
            "target_speed_mps": self.config.target_speed_mps,
            "minimum_target_separation_m": minimum_target_separation(
                target_specs, self.config.duration_s
            ),
            "camera_detection_coverage": {
                camera_id: len(values) / self.config.target_count
                for camera_id, values in detection_truth_by_camera.items()
            },
            "stable_track_count": {
                camera_id: len(
                    trackers[camera_id].stable_tracks(
                        self.config.stable_sweep_count
                    )
                )
                for camera_id in self.config.camera_positions
            },
            "stable_track_truth_coverage": {
                camera_id: len(values) / self.config.target_count
                for camera_id, values in stable_truth_by_camera.items()
            },
            "eligible_cross_camera_truth_count": len(eligible_truth),
            "candidate_count": len(association.candidates),
            "valid_candidate_count": sum(
                candidate.valid for candidate in association.candidates
            ),
            "match_count": len(association.matches),
            "correct_match_count": correct_count,
            "false_match_count": len(association.matches) - correct_count,
            "association_precision": precision,
            "association_full_target_recall": full_recall,
            "association_eligible_recall": eligible_recall,
            "duplicate_truth_match_count": duplicate_truth_match_count,
            "unmatched_a_count": len(association.unmatched_a_track_ids),
            "unmatched_b_count": len(association.unmatched_b_track_ids),
            "position_error_mean_m": _mean(position_errors),
            "position_error_p95_m": _percentile(position_errors, 95.0),
            "velocity_error_mean_mps": _mean(velocity_errors),
            "velocity_error_p95_mps": _percentile(velocity_errors, 95.0),
            "online_truth_leakage_count": len(leakage_keys),
            "online_truth_leakage_keys": list(leakage_keys),
            "fixed_pitch_span_deg": {
                camera_id: max(values) - min(values) if values else None
                for camera_id, values in pitch_by_camera.items()
            },
            "configured_detection_request_rate_hz": self.config.sample_rate_hz,
            "detection_rpc_latency_mean_ms": _mean(rpc_latencies_ms),
            "detection_rpc_latency_p95_ms": _percentile(rpc_latencies_ms, 95.0),
            "formal_episode_wall_duration_s": wall_duration_s,
            "detection_rpc_wall_rate_hz": (
                len(rpc_latencies_ms) / wall_duration_s
                if wall_duration_s > 0.0
                else None
            ),
            "cross_camera_association_wall_ms": association_wall_ms,
            "keyframe_count": len(keyframe_rows),
            "acceptance": {
                "truth_isolation_passed": len(leakage_keys) == 0,
                "spawn_passed": len(actor_name_by_truth) == self.config.target_count,
                "fixed_pitch_passed": all(
                    math.isclose(max(values) - min(values), 0.0, abs_tol=1e-9)
                    for values in pitch_by_camera.values()
                    if values
                ),
                "no_duplicate_match_passed": duplicate_truth_match_count == 0,
                "precision_target_passed": precision is not None and precision >= 0.95,
                "recall_target_passed": full_recall >= 0.80,
                "stable_coverage_target_passed": all(
                    len(values) / self.config.target_count >= 0.80
                    for values in stable_truth_by_camera.values()
                ),
            },
        }
        metrics["acceptance"]["overall_passed"] = all(
            bool(value) for value in metrics["acceptance"].values()
        )
        output_paths = {
            "anonymous_detections": write_csv(
                online_dir / "anonymous_detections.csv", online_detection_rows
            ),
            "camera_scan": write_csv(online_dir / "camera_scan.csv", scan_rows),
            "local_tracks": write_csv(online_dir / "local_tracks.csv", track_rows),
            "local_track_samples": write_csv(
                online_dir / "local_track_samples.csv", sample_rows
            ),
            "cross_camera_candidates": write_csv(
                online_dir / "cross_camera_candidates.csv", candidate_rows
            ),
            "cross_camera_matches": write_csv(
                online_dir / "cross_camera_matches.csv", match_rows
            ),
            "detection_truth": write_csv(
                truth_dir / "detection_truth.csv", offline_detection_rows
            ),
            "target_trajectories": write_csv(
                truth_dir / "target_trajectories.csv", target_truth_rows
            ),
            "track_scoring": write_csv(
                truth_dir / "track_scoring.csv", track_truth_rows
            ),
            "match_scoring": write_csv(
                truth_dir / "match_scoring.csv", scored_match_rows
            ),
            "keyframe_manifest": write_csv(
                self.output_dir / "keyframes" / "manifest.csv", keyframe_rows
            ),
        }
        metrics_path = write_json(self.output_dir / "metrics.json", metrics)
        output_paths["metrics"] = metrics_path
        output_paths["manifest"] = write_json(
            self.output_dir / "record_manifest.json",
            {
                "schema_version": "dual-optical-40target-record-manifest-v1",
                "independent_experiment": True,
                "settings": str(settings_path),
                "artifacts": {
                    key: str(path.relative_to(self.output_dir))
                    for key, path in output_paths.items()
                },
                "keyframes": keyframe_rows,
                "video_generated": False,
            },
        )
        return ExperimentResult(
            output_dir=self.output_dir,
            settings_path=settings_path,
            metrics_path=metrics_path,
            metrics=metrics,
            output_paths=output_paths,
            tracks_a=tracks_a,
            tracks_b=tracks_b,
            association=association,
            target_specs=target_specs,
        )



def _offline_truth_assignments(
    boxes: Sequence[tuple[float, float, float, float]],
    current_positions: Mapping[str, tuple[float, float, float]],
    camera_state: CameraState,
    camera_spec: CameraSpec,
) -> dict[int, tuple[str, float]]:
    projections: list[tuple[str, tuple[float, float]]] = []
    for truth_id, position in current_positions.items():
        pixel = project_world_point(position, camera_state, camera_spec)
        if pixel is None:
            continue
        if -100.0 <= pixel[0] <= camera_spec.width + 100.0 and -100.0 <= pixel[1] <= camera_spec.height + 100.0:
            projections.append((truth_id, pixel))
    if not boxes or not projections:
        return {}
    costs = np.full((len(boxes), len(projections)), 1e6, dtype=float)
    for row, bbox in enumerate(boxes):
        center = np.asarray(
            ((bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5),
            dtype=float,
        )
        for column, (_truth_id, pixel) in enumerate(projections):
            error = float(np.linalg.norm(center - np.asarray(pixel, dtype=float)))
            if error <= 80.0:
                costs[row, column] = error
    rows, columns = linear_sum_assignment(costs)
    assignments: dict[int, tuple[str, float]] = {}
    for row, column in zip(rows, columns):
        if costs[row, column] >= 1e5:
            continue
        assignments[int(row)] = (projections[column][0], float(costs[row, column]))
    return assignments


def _keyframe_indices(config: ScenarioConfig) -> set[int]:
    indices: set[int] = set()
    for start in np.arange(0.0, config.duration_s + 1e-9, 2.0):
        for offset in (0.25, 0.75):
            timestamp = float(start + offset)
            if timestamp <= config.duration_s:
                indices.add(int(round(timestamp * config.sample_rate_hz)))
    return indices


def _camera_pose(airsim_module: Any, yaw_deg: float, pitch_deg: float) -> Any:
    return airsim_module.Pose(
        airsim_module.Vector3r(0.0, 0.0, 0.0),
        airsim_module.to_quaternion(
            math.radians(pitch_deg), 0.0, math.radians(yaw_deg)
        ),
    )


def _world_pose(
    airsim_module: Any, position: Sequence[float], yaw_deg: float
) -> Any:
    return airsim_module.Pose(
        airsim_module.Vector3r(
            float(position[0]), float(position[1]), float(position[2])
        ),
        airsim_module.to_quaternion(0.0, 0.0, math.radians(yaw_deg)),
    )


def _find_detection(
    client: Any, airsim_module: Any, config: ScenarioConfig, camera_id: str
) -> Any | None:
    detections = client.simGetDetections(
        config.camera_name,
        airsim_module.ImageType.Scene,
        vehicle_name=camera_id,
    )
    return detections[0] if detections else None


def _set_object_pose_with_retry(
    client: Any, object_name: str, pose: Any, *, timeout_s: float
) -> bool:
    deadline = time.monotonic() + float(timeout_s)
    while True:
        try:
            if bool(client.simSetObjectPose(object_name, pose, True)):
                return True
        except Exception:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)


def _wait_for_detection(
    client: Any,
    airsim_module: Any,
    config: ScenarioConfig,
    camera_id: str,
    *,
    timeout_s: float,
) -> Any | None:
    deadline = time.monotonic() + float(timeout_s)
    while time.monotonic() < deadline:
        detection = _find_detection(client, airsim_module, config, camera_id)
        if detection is not None:
            return detection
        try:
            client.simGetImages(
                [
                    airsim_module.ImageRequest(
                        config.camera_name,
                        airsim_module.ImageType.Scene,
                        False,
                        True,
                    )
                ],
                vehicle_name=camera_id,
            )
        except Exception:
            pass
        time.sleep(0.25)
    return None


def _box3d_longest_extent(detection: Any | None) -> float | None:
    if detection is None:
        return None
    box = getattr(detection, "box3D", None)
    if box is None:
        return None
    minimum = getattr(box, "min", None)
    maximum = getattr(box, "max", None)
    if minimum is None or maximum is None:
        return None
    extents = (
        abs(float(maximum.x_val) - float(minimum.x_val)),
        abs(float(maximum.y_val) - float(minimum.y_val)),
        abs(float(maximum.z_val) - float(minimum.z_val)),
    )
    longest = max(extents)
    return longest if math.isfinite(longest) and longest > 0.0 else None


def _bbox2d(detection: Any) -> tuple[float, float, float, float] | None:
    box = getattr(detection, "box2D", None)
    if box is None or getattr(box, "min", None) is None or getattr(box, "max", None) is None:
        return None
    bbox = (
        float(box.min.x_val),
        float(box.min.y_val),
        float(box.max.x_val),
        float(box.max.y_val),
    )
    if not all(math.isfinite(value) for value in bbox):
        return None
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return bbox


def _pose_to_dict(pose: Any | None) -> dict[str, Any] | None:
    if pose is None:
        return None
    position = getattr(pose, "position", None)
    orientation = getattr(pose, "orientation", None)
    return {
        "position": _vector3_to_list(position),
        "orientation_xyzw": None
        if orientation is None
        else [
            float(orientation.x_val),
            float(orientation.y_val),
            float(orientation.z_val),
            float(orientation.w_val),
        ],
    }


def _box3d_to_dict(box: Any | None) -> dict[str, Any] | None:
    if box is None:
        return None
    return {
        "min": _vector3_to_list(getattr(box, "min", None)),
        "max": _vector3_to_list(getattr(box, "max", None)),
    }


def _vector3_to_list(vector: Any | None) -> list[float] | None:
    if vector is None:
        return None
    return [float(vector.x_val), float(vector.y_val), float(vector.z_val)]


def _tcp_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=0.2):
            return True
    except OSError:
        return False


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> Path:
    row_list = [dict(row) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(dict.fromkeys(key for row in row_list for key in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        if fieldnames:
            writer = csv.DictWriter(
                stream, fieldnames=fieldnames, lineterminator="\n"
            )
            writer.writeheader()
            for row in row_list:
                writer.writerow(
                    {key: _csv_value(row.get(key)) for key in fieldnames}
                )
    return path


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _csv_value(value: Any) -> Any:
    if isinstance(value, (Mapping, list, tuple, np.ndarray)):
        return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)
    return value


def _mean(values: Sequence[float]) -> float | None:
    return None if not values else float(np.mean(np.asarray(values, dtype=float)))


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    return (
        None
        if not values
        else float(np.percentile(np.asarray(values, dtype=float), percentile))
    )
