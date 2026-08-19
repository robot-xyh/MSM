"""AirSim adapter and structured records for the independent guide case."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import csv
import json
import math
from pathlib import Path
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from .core import (
    AnonymousBearingTracker,
    AnonymousDetection,
    AssociationResult,
    BearingSample,
    BearingTrack,
    CameraSpec,
    CameraState,
    FinalMatch,
    ScenarioConfig,
    TargetSpec,
    associate_tracks,
    build_synthetic_tracks,
    crossing_pairs,
    generate_target_specs,
    half_sweep_index,
    look_angles_deg,
    majority_track_truth,
    minimum_initial_separation,
    observation_from_detection,
    online_truth_leakage_keys,
    project_world_point,
    scan_yaw_deg,
    score_matches,
    select_multi_time_pairs,
)


@dataclass(frozen=True)
class ExperimentResult:
    output_dir: Path
    config: ScenarioConfig
    camera: CameraSpec
    target_specs: tuple[TargetSpec, ...]
    tracks_a: tuple[BearingTrack, ...]
    tracks_b: tuple[BearingTrack, ...]
    association: AssociationResult
    camera_scan_rows: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]
    data_source: str


def write_airsim_settings(
    path: Path, config: ScenarioConfig, camera: CameraSpec
) -> Path:
    capture = {
        "ImageType": 0,
        "Width": camera.width,
        "Height": camera.height,
        "FOV_Degrees": camera.horizontal_fov_deg,
        "MotionBlurAmount": 0,
    }

    def camera_vehicle(position: Sequence[float]) -> dict[str, Any]:
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
        "ApiServerPort": config.api_port,
        "LocalHostIp": "127.0.0.1",
        "ClockSpeed": config.clock_speed,
        "ViewMode": "NoDisplay",
        "CameraDefaults": {"CaptureSettings": [dict(capture)]},
        "SubWindows": [],
        "Vehicles": {
            config.camera_a_name: camera_vehicle(config.camera_a_position_ned),
            config.camera_b_name: camera_vehicle(config.camera_b_position_ned),
        },
    }
    return write_json(path, payload)


def prepare_case(
    output_dir: Path, config: ScenarioConfig, camera: CameraSpec
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = generate_target_specs(config)
    settings = write_airsim_settings(output_dir / "settings.json", config, camera)
    scenario = write_json(
        output_dir / "scenario.json",
        {
            "schema_version": "dual-optical-100target-guide-scenario-v1",
            "independent_experiment": True,
            "connected_d_modules": [],
            "formal_airsim_result": False,
            "scenario": asdict(config),
            "camera": asdict(camera)
            | {
                "vertical_fov_deg": camera.vertical_fov_deg,
                "focal_length_px": camera.focal_length_px,
            },
            "derived": {
                "baseline_m": 4000.0,
                "minimum_initial_separation_m": minimum_initial_separation(targets),
                "half_sweep_count": config.half_sweep_count,
                "crossing_pair_count": len(crossing_pairs(targets)),
            },
        },
    )
    truth = write_json(
        output_dir / "truth" / "target_specs.json",
        {
            "offline_truth_only": True,
            "targets": [asdict(target) for target in targets],
            "crossing_pairs": crossing_pairs(targets),
        },
    )
    return {"settings": settings, "scenario": scenario, "target_truth": truth}


class GuideCaseAirSimRunner:
    """Connect to Blocks started by main and execute one fixed episode."""

    def __init__(
        self,
        *,
        config: ScenarioConfig,
        camera: CameraSpec,
        output_dir: Path,
        client: Any | None = None,
        airsim_module: Any | None = None,
        connection_timeout_s: float = 45.0,
    ) -> None:
        self.config = config
        self.camera = camera
        self.output_dir = Path(output_dir)
        self._client = client
        self._airsim = airsim_module
        self.connection_timeout_s = float(connection_timeout_s)

    def run(self) -> ExperimentResult:
        prepare_case(self.output_dir, self.config, self.camera)
        targets = generate_target_specs(self.config)
        airsim_module, client = self._connect()
        self._configure_cameras(airsim_module, client)
        scale = self._calibrate_actor_scale(airsim_module, client)
        actors = self._spawn_targets(airsim_module, client, targets, scale)
        online_rows: list[dict[str, Any]] = []
        truth_detection_rows: list[dict[str, Any]] = []
        scan_rows: list[dict[str, Any]] = []
        observation_truth: dict[str, str] = {}
        trackers = {
            camera_id: AnonymousBearingTracker(
                camera_id,
                gate_deg=self.config.local_track_gate_deg,
                max_coast_s=self.config.local_track_coast_s,
            )
            for camera_id in self.config.camera_positions
        }
        random_generators = {
            self.config.camera_a_name: np.random.default_rng(self.config.seed + 101),
            self.config.camera_b_name: np.random.default_rng(self.config.seed + 202),
        }
        started = time.perf_counter()
        # This Blocks 1.8.1 build does not implement simContinueForTime.
        # Targets use scripted poses, so logical time stays deterministic while
        # a short wall-clock yield lets Unreal refresh detection metadata.
        client.simPause(False)
        try:
            for frame_index in range(self.config.frame_count):
                timestamp = frame_index * self.config.dt_s
                current_positions = {
                    target.truth_id: target.position_at(timestamp) for target in targets
                }
                for target in targets:
                    actor_name = actors[target.truth_id]
                    heading = math.degrees(
                        math.atan2(target.velocity_ned[1], target.velocity_ned[0])
                    )
                    client.simSetObjectPose(
                        actor_name,
                        _world_pose(
                            airsim_module,
                            current_positions[target.truth_id],
                            heading,
                        ),
                        True,
                    )
                states = self._set_camera_scan_poses(
                    airsim_module, client, frame_index, timestamp
                )
                time.sleep(0.002)
                for camera_id, state in states.items():
                    rpc_started = time.perf_counter()
                    raw = client.simGetDetections(
                        self.config.camera_name,
                        airsim_module.ImageType.Scene,
                        vehicle_name=camera_id,
                    ) or []
                    latency_s = time.perf_counter() - rpc_started
                    detections, truth_rows = self._anonymize_detections(
                        raw,
                        state,
                        current_positions,
                        measurement_timestamp=timestamp,
                        arrival_timestamp=timestamp + latency_s,
                    )
                    observations = [
                        observation_from_detection(
                            detection,
                            state,
                            self.camera,
                            random_generators[camera_id],
                        )
                        for detection in detections
                    ]
                    trackers[camera_id].update(timestamp, observations)
                    for detection, observation in zip(
                        detections, observations, strict=True
                    ):
                        online_rows.append(
                            asdict(detection)
                            | {
                                "half_sweep_index": state.half_sweep_index,
                                "ray_x_ned": observation.direction_ned[0],
                                "ray_y_ned": observation.direction_ned[1],
                                "ray_z_ned": observation.direction_ned[2],
                            }
                        )
                    truth_detection_rows.extend(truth_rows)
                    for row in truth_rows:
                        if row.get("truth_id"):
                            observation_truth[str(row["detection_uid"])] = str(
                                row["truth_id"]
                            )
                    scan_rows.append(
                        {
                            "camera_id": camera_id,
                            "frame_index": frame_index,
                            "measurement_timestamp": timestamp,
                            "half_sweep_index": state.half_sweep_index,
                            "yaw_deg": state.yaw_deg,
                            "pitch_deg": state.pitch_deg,
                            "detection_count": len(detections),
                            "rpc_latency_ms": latency_s * 1000.0,
                        }
                    )
        finally:
            client.simPause(False)
            for actor_name in actors.values():
                try:
                    client.simDestroyObject(actor_name)
                except Exception:
                    pass

        tracks_a = trackers[self.config.camera_a_name].tracks(
            self.config.stable_sweep_count
        )
        tracks_b = trackers[self.config.camera_b_name].tracks(
            self.config.stable_sweep_count
        )
        association_started = time.perf_counter()
        association = associate_tracks(tracks_a, tracks_b)
        association_wall_s = time.perf_counter() - association_started
        result = _finalize_and_write(
            output_dir=self.output_dir,
            config=self.config,
            camera=self.camera,
            targets=targets,
            tracks_a=tracks_a,
            tracks_b=tracks_b,
            association=association,
            observation_truth=observation_truth,
            online_detection_rows=online_rows,
            truth_detection_rows=truth_detection_rows,
            camera_scan_rows=scan_rows,
            data_source="airsim_computervision",
            formal_airsim_result=True,
            wall_duration_s=time.perf_counter() - started,
            association_wall_s=association_wall_s,
            actor_scale=scale,
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
                timeout_value=10,
            )
        deadline = time.monotonic() + self.connection_timeout_s
        last_error = ""
        while time.monotonic() < deadline:
            try:
                if self._client.ping():
                    return self._airsim, self._client
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.25)
        raise TimeoutError(f"AirSim connection timed out: {last_error}")

    def _configure_cameras(self, airsim_module: Any, client: Any) -> None:
        for camera_id, position in self.config.camera_positions.items():
            yaw, pitch = look_angles_deg(position, self.config.corridor_center_ned)
            client.simSetCameraFov(
                self.config.camera_name,
                self.camera.horizontal_fov_deg,
                vehicle_name=camera_id,
            )
            client.simSetCameraPose(
                self.config.camera_name,
                _camera_pose(airsim_module, yaw, pitch),
                vehicle_name=camera_id,
            )

    def _calibrate_actor_scale(self, airsim_module: Any, client: Any) -> float:
        # A failed RPC can leave a dynamically spawned actor pending in Unreal.
        # Reusing that name crashes this Blocks build, so calibration actors are
        # intentionally unique and remain outside the scored target namespace.
        name = (
            f"MSM_Guide_Target_Calibration_{self.config.seed}_"
            f"{time.time_ns()}"
        )
        origin = np.asarray(self.config.camera_a_position_ned)
        point = np.asarray(self.config.corridor_center_ned)
        calibration_position = origin + (point - origin) / np.linalg.norm(point - origin) * 200.0
        spawned = client.simSpawnObject(
            name,
            self.config.target_asset_name,
            _world_pose(airsim_module, calibration_position, 0.0),
            airsim_module.Vector3r(1.0, 1.0, 1.0),
            False,
        )
        if not spawned:
            raise RuntimeError("target actor calibration spawn failed")
        actual_name = str(spawned)
        self._configure_detection_filter(client, self.config.camera_a_name)
        time.sleep(0.05)
        detection = self._wait_for_detection(airsim_module, client, actual_name)
        native_extent = _box3d_longest_extent(detection)
        if native_extent is None or native_extent <= 0.0:
            client.simDestroyObject(actual_name)
            raise RuntimeError("AirSim box3D cannot measure the actor size")
        scale = self.config.target_longest_dimension_m / native_extent
        client.simSetObjectScale(
            actual_name, airsim_module.Vector3r(scale, scale, scale)
        )
        time.sleep(0.05)
        final = self._wait_for_detection(airsim_module, client, actual_name)
        final_extent = _box3d_longest_extent(final)
        client.simDestroyObject(actual_name)
        if final_extent is None or abs(final_extent - 3.0) > self.config.target_dimension_tolerance_m:
            raise RuntimeError(
                f"calibrated actor extent {final_extent!r} is outside the 3 m tolerance"
            )
        write_json(
            self.output_dir / "preflight.json",
            {
                "passed": True,
                "native_longest_extent_m": native_extent,
                "final_longest_extent_m": final_extent,
                "actor_scale": scale,
            },
        )
        return scale

    def _wait_for_detection(
        self, airsim_module: Any, client: Any, actor_name: str
    ) -> Any | None:
        for _ in range(40):
            detections = client.simGetDetections(
                self.config.camera_name,
                airsim_module.ImageType.Scene,
                vehicle_name=self.config.camera_a_name,
            ) or []
            for detection in detections:
                if str(getattr(detection, "name", "")) == actor_name:
                    return detection
            if detections:
                return detections[0]
            time.sleep(0.02)
        return None

    def _spawn_targets(
        self,
        airsim_module: Any,
        client: Any,
        targets: Sequence[TargetSpec],
        scale: float,
    ) -> dict[str, str]:
        actors: dict[str, str] = {}
        for target in targets:
            spawned = client.simSpawnObject(
                target.actor_name,
                target.asset_name,
                _world_pose(airsim_module, target.start_ned, 0.0),
                airsim_module.Vector3r(scale, scale, scale),
                False,
            )
            if not spawned:
                raise RuntimeError(f"failed to spawn {target.actor_name}")
            actors[target.truth_id] = str(spawned)
        for camera_id in self.config.camera_positions:
            self._configure_detection_filter(client, camera_id)
        return actors

    def _configure_detection_filter(self, client: Any, camera_id: str) -> None:
        image_type = self._airsim.ImageType.Scene
        client.simClearDetectionMeshNames(
            self.config.camera_name, image_type, vehicle_name=camera_id
        )
        client.simSetDetectionFilterRadius(
            self.config.camera_name,
            image_type,
            self.config.detection_filter_radius_cm,
            vehicle_name=camera_id,
        )
        for pattern in (
            self.config.target_asset_name,
            f"{self.config.target_asset_name}*",
            "MSM_Guide_Target_*",
        ):
            client.simAddDetectionFilterMeshName(
                self.config.camera_name,
                image_type,
                pattern,
                vehicle_name=camera_id,
            )

    def _set_camera_scan_poses(
        self,
        airsim_module: Any,
        client: Any,
        frame_index: int,
        timestamp: float,
    ) -> dict[str, CameraState]:
        states: dict[str, CameraState] = {}
        for camera_id, position in self.config.camera_positions.items():
            base_yaw, pitch = look_angles_deg(position, self.config.corridor_center_ned)
            yaw = scan_yaw_deg(
                timestamp,
                base_yaw,
                half_span_deg=self.config.scan_half_span_deg,
                period_s=self.config.scan_period_s,
            )
            client.simSetCameraPose(
                self.config.camera_name,
                _camera_pose(airsim_module, yaw, pitch),
                vehicle_name=camera_id,
            )
            states[camera_id] = CameraState(
                camera_id,
                frame_index,
                timestamp,
                position,
                yaw,
                pitch,
                half_sweep_index(timestamp, period_s=self.config.scan_period_s),
            )
        return states

    def _anonymize_detections(
        self,
        raw_detections: Sequence[Any],
        state: CameraState,
        current_positions: Mapping[str, tuple[float, float, float]],
        *,
        measurement_timestamp: float,
        arrival_timestamp: float,
    ) -> tuple[list[AnonymousDetection], list[dict[str, Any]]]:
        raw_with_boxes = [
            (raw, _bbox2d(raw)) for raw in raw_detections if _bbox2d(raw) is not None
        ]
        raw_with_boxes.sort(key=lambda item: (item[1][0], item[1][1]))
        boxes = [item[1] for item in raw_with_boxes]
        truth_assignments = _offline_pixel_truth_assignments(
            boxes, current_positions, state, self.camera
        )
        anonymous: list[AnonymousDetection] = []
        offline: list[dict[str, Any]] = []
        for index, (raw, box) in enumerate(raw_with_boxes):
            uid = f"{state.camera_id}-F{state.frame_index:04d}-D{index:03d}"
            center = ((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5)
            anonymous.append(
                AnonymousDetection(
                    uid,
                    state.camera_id,
                    state.frame_index,
                    measurement_timestamp,
                    arrival_timestamp,
                    box,
                    center,
                    1.0,
                )
            )
            truth_id, pixel_error = truth_assignments.get(index, ("", math.inf))
            offline.append(
                {
                    "detection_uid": uid,
                    "camera_id": state.camera_id,
                    "frame_index": state.frame_index,
                    "measurement_timestamp": measurement_timestamp,
                    "truth_id": truth_id,
                    "raw_detection_name": str(getattr(raw, "name", "") or ""),
                    "pixel_assignment_error": pixel_error,
                    "offline_truth_only": True,
                }
            )
        return anonymous, offline


def run_synthetic_fixture(
    output_dir: Path,
    config: ScenarioConfig | None = None,
    camera: CameraSpec | None = None,
) -> ExperimentResult:
    """Generate deterministic geometry records for tests, never as AirSim evidence."""

    config = config or ScenarioConfig()
    camera = camera or CameraSpec()
    output_dir = Path(output_dir)
    prepare_case(output_dir, config, camera)
    targets = generate_target_specs(config)
    tracks_a, tracks_b, observation_truth = build_synthetic_tracks(config, camera)
    association_started = time.perf_counter()
    association = associate_tracks(tracks_a, tracks_b)
    association_wall_s = time.perf_counter() - association_started
    scan_rows = []
    for frame_index in range(config.frame_count):
        timestamp = frame_index * config.dt_s
        for camera_id, position in config.camera_positions.items():
            base_yaw, pitch = look_angles_deg(position, config.corridor_center_ned)
            scan_rows.append(
                {
                    "camera_id": camera_id,
                    "frame_index": frame_index,
                    "measurement_timestamp": timestamp,
                    "half_sweep_index": half_sweep_index(timestamp),
                    "yaw_deg": scan_yaw_deg(
                        timestamp,
                        base_yaw,
                        half_span_deg=config.scan_half_span_deg,
                    ),
                    "pitch_deg": pitch,
                    "detection_count": 0,
                    "rpc_latency_ms": None,
                }
            )
    return _finalize_and_write(
        output_dir=output_dir,
        config=config,
        camera=camera,
        targets=targets,
        tracks_a=tracks_a,
        tracks_b=tracks_b,
        association=association,
        observation_truth=observation_truth,
        online_detection_rows=[],
        truth_detection_rows=[],
        camera_scan_rows=scan_rows,
        data_source="synthetic_geometry_fixture",
        formal_airsim_result=False,
        wall_duration_s=None,
        association_wall_s=association_wall_s,
        actor_scale=None,
    )


def load_experiment_result(output_dir: Path) -> ExperimentResult:
    output_dir = Path(output_dir)
    scenario = json.loads((output_dir / "scenario.json").read_text(encoding="utf-8"))
    config = ScenarioConfig(**scenario["scenario"])
    camera_values = {
        key: value
        for key, value in scenario["camera"].items()
        if key in {"width", "height", "horizontal_fov_deg", "angular_noise_sigma_mrad"}
    }
    camera = CameraSpec(**camera_values)
    truth = json.loads(
        (output_dir / "truth" / "target_specs.json").read_text(encoding="utf-8")
    )
    targets = tuple(TargetSpec(**item) for item in truth["targets"])
    tracks = _load_tracks(output_dir / "online" / "local_track_samples.csv")
    tracks_a = tuple(track for track in tracks if track.camera_id == config.camera_a_name)
    tracks_b = tuple(track for track in tracks if track.camera_id == config.camera_b_name)
    association = associate_tracks(tracks_a, tracks_b)
    scan_rows = tuple(read_csv(output_dir / "online" / "camera_scan.csv"))
    metrics = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    metrics_changed = False
    acceptance = metrics.get("acceptance", {})
    legacy_detection_check = acceptance.pop(
        "detections_observed_both_cameras", None
    )
    if legacy_detection_check is not None:
        acceptance["formal_detection_requirement_passed"] = bool(
            legacy_detection_check
        )
        acceptance.pop("overall_passed", None)
        acceptance["overall_passed"] = all(acceptance.values())
        metrics_changed = True
    if "offline_track_quality" not in metrics:
        observation_truth = {
            row["detection_uid"]: row["truth_id"]
            for row in read_csv(output_dir / "truth" / "detection_truth.csv")
            if row.get("detection_uid") and row.get("truth_id")
        }
        metrics["offline_track_quality"] = {
            config.camera_a_name: _offline_track_quality(
                tracks_a, observation_truth
            ),
            config.camera_b_name: _offline_track_quality(
                tracks_b, observation_truth
            ),
        }
        metrics_changed = True
    if metrics_changed:
        write_json(output_dir / "metrics.json", metrics)
    return ExperimentResult(
        output_dir,
        config,
        camera,
        targets,
        tracks_a,
        tracks_b,
        association,
        scan_rows,
        metrics,
        str(metrics.get("data_source", "unknown")),
    )


def _finalize_and_write(
    *,
    output_dir: Path,
    config: ScenarioConfig,
    camera: CameraSpec,
    targets: Sequence[TargetSpec],
    tracks_a: Sequence[BearingTrack],
    tracks_b: Sequence[BearingTrack],
    association: AssociationResult,
    observation_truth: Mapping[str, str],
    online_detection_rows: Sequence[Mapping[str, Any]],
    truth_detection_rows: Sequence[Mapping[str, Any]],
    camera_scan_rows: Sequence[Mapping[str, Any]],
    data_source: str,
    formal_airsim_result: bool,
    wall_duration_s: float | None,
    association_wall_s: float,
    actor_scale: float | None,
) -> ExperimentResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    truth_a = majority_track_truth(tracks_a, observation_truth)
    truth_b = majority_track_truth(tracks_b, observation_truth)
    final_score = score_matches(
        association.final_matches, truth_a, truth_b, target_count=config.target_count
    )
    first_sweep = min(
        (item.half_sweep_index for item in association.scan_assignments), default=0
    )
    single_pairs = tuple(
        (item.track_a_id, item.track_b_id)
        for item in association.scan_assignments
        if item.half_sweep_index == first_sweep
    )
    multi_pairs = select_multi_time_pairs(
        association.residual_statistics,
        association.track_a_ids,
        association.track_b_ids,
    )
    confirmed_pairs = tuple(
        (item.track_a_id, item.track_b_id)
        for item in association.final_matches
        if item.state == "confirmed"
    )
    stage_metrics = {
        "single_scan_coplanarity": _score_pairs(
            single_pairs, truth_a, truth_b, config.target_count
        ),
        "multi_time_residual_and_slope": _score_pairs(
            multi_pairs, truth_a, truth_b, config.target_count
        ),
        "scan_hungarian_and_vote": final_score,
        "confirmed_only": _score_pairs(
            confirmed_pairs, truth_a, truth_b, config.target_count
        ),
    }
    online_records = [dict(row) for row in online_detection_rows]
    online_records.extend(asdict(item) for item in association.final_matches)
    leakage = online_truth_leakage_keys(online_records)
    one_to_one = bool(
        len({item.track_a_id for item in association.final_matches})
        == len(association.final_matches)
        and len({item.track_b_id for item in association.final_matches})
        == len(association.final_matches)
    )
    detections_by_camera = {
        camera_id: sum(
            1
            for row in online_detection_rows
            if str(row.get("camera_id")) == camera_id
        )
        for camera_id in config.camera_positions
    }
    offline_track_quality = {
        config.camera_a_name: _offline_track_quality(tracks_a, observation_truth),
        config.camera_b_name: _offline_track_quality(tracks_b, observation_truth),
    }
    metrics = {
        "schema_version": "dual-optical-100target-guide-metrics-v1",
        "data_source": data_source,
        "formal_airsim_result": formal_airsim_result,
        "scenario": {
            "target_count": config.target_count,
            "baseline_m": 4000.0,
            "duration_s": config.duration_s,
            "sample_rate_hz": config.sample_rate_hz,
            "half_sweep_count": config.half_sweep_count,
            "crossing_pair_count": len(crossing_pairs(targets)),
            "minimum_initial_separation_m": minimum_initial_separation(targets),
            "angular_noise_sigma_mrad": camera.angular_noise_sigma_mrad,
        },
        "local_tracks": {
            "camera_a": len(tracks_a),
            "camera_b": len(tracks_b),
            "full_pair_count": len(tracks_a) * len(tracks_b),
        },
        "detections": {
            "total": len(online_detection_rows),
            "by_camera": detections_by_camera,
        },
        "offline_track_quality": offline_track_quality,
        "association_stages": stage_metrics,
        "state_counts": _count_states(association),
        "online_truth_leakage_count": len(leakage),
        "online_truth_leakage_keys": leakage,
        "one_to_one_final": one_to_one,
        "association_wall_s": association_wall_s,
        "episode_wall_s": wall_duration_s,
        "actor_scale": actor_scale,
        "acceptance": {
            "target_count_is_100": config.target_count == 100,
            "baseline_is_4km": math.isclose(
                math.dist(config.camera_a_position_ned, config.camera_b_position_ned),
                4000.0,
            ),
            "minimum_initial_separation_above_100m": minimum_initial_separation(targets)
            > 100.0,
            "ten_crossing_pairs": len(crossing_pairs(targets)) == 10,
            "ten_half_sweeps": config.half_sweep_count == 10,
            "online_truth_isolated": not leakage,
            "final_assignment_one_to_one": one_to_one,
            "formal_detection_requirement_passed": bool(
                not formal_airsim_result
                or all(count > 0 for count in detections_by_camera.values())
            ),
            "stable_tracks_observed_both_cameras": bool(tracks_a and tracks_b),
            "final_matches_observed": bool(association.final_matches),
        },
    }
    metrics["acceptance"]["overall_passed"] = all(metrics["acceptance"].values())

    artifacts = {
        "anonymous_detections": write_csv(
            output_dir / "online" / "anonymous_detections.csv", online_detection_rows
        ),
        "camera_scan": write_csv(
            output_dir / "online" / "camera_scan.csv", camera_scan_rows
        ),
        "local_tracks": write_csv(
            output_dir / "online" / "local_tracks.csv",
            [
                {
                    "track_id": track.track_id,
                    "camera_id": track.camera_id,
                    "sweep_count": len(track.samples),
                    "observation_count": len(track.observation_uids),
                }
                for track in (*tracks_a, *tracks_b)
            ],
        ),
        "local_track_samples": write_csv(
            output_dir / "online" / "local_track_samples.csv",
            _track_sample_rows((*tracks_a, *tracks_b)),
        ),
        "residual_statistics": write_csv(
            output_dir / "online" / "residual_statistics.csv",
            [asdict(item) for item in association.residual_statistics],
        ),
        "scan_assignments": write_csv(
            output_dir / "online" / "scan_assignments.csv",
            [asdict(item) for item in association.scan_assignments],
        ),
        "association_states": write_csv(
            output_dir / "online" / "association_states.csv",
            [asdict(item) for item in association.state_history],
        ),
        "final_matches": write_csv(
            output_dir / "online" / "final_matches.csv",
            [asdict(item) for item in association.final_matches],
        ),
        "detection_truth": write_csv(
            output_dir / "truth" / "detection_truth.csv", truth_detection_rows
        ),
        "track_truth": write_csv(
            output_dir / "truth" / "track_truth.csv",
            [
                {"track_id": track_id, "truth_id": truth_id, "offline_truth_only": True}
                for track_id, truth_id in sorted((truth_a | truth_b).items())
            ],
        ),
        "match_scoring": write_csv(
            output_dir / "truth" / "match_scoring.csv",
            _match_scoring_rows(association.final_matches, truth_a, truth_b),
        ),
        "metrics": write_json(output_dir / "metrics.json", metrics),
    }
    write_json(
        output_dir / "record_manifest.json",
        {
            "schema_version": "dual-optical-100target-guide-records-v1",
            "data_source": data_source,
            "formal_airsim_result": formal_airsim_result,
            "screenshots_saved": False,
            "artifacts": {
                key: str(path.relative_to(output_dir)) for key, path in artifacts.items()
            },
        },
    )
    scenario_path = output_dir / "scenario.json"
    scenario_payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario_payload["formal_airsim_result"] = formal_airsim_result
    write_json(scenario_path, scenario_payload)
    return ExperimentResult(
        output_dir,
        config,
        camera,
        tuple(targets),
        tuple(tracks_a),
        tuple(tracks_b),
        association,
        tuple(dict(row) for row in camera_scan_rows),
        metrics,
        data_source,
    )


def _offline_track_quality(
    tracks: Sequence[BearingTrack], observation_truth: Mapping[str, str]
) -> dict[str, Any]:
    purities: list[float] = []
    majority_truth_ids: list[str] = []
    for track in tracks:
        identities = [
            observation_truth[uid]
            for uid in track.observation_uids
            if uid in observation_truth
        ]
        if not identities:
            continue
        majority_id, majority_count = Counter(identities).most_common(1)[0]
        purities.append(majority_count / len(identities))
        majority_truth_ids.append(majority_id)
    return {
        "scored_track_count": len(purities),
        "purity_values": purities,
        "purity_median": float(np.median(purities)) if purities else 0.0,
        "purity_p10": float(np.percentile(purities, 10.0)) if purities else 0.0,
        "high_purity_track_count": sum(value >= 0.90 for value in purities),
        "unique_majority_truth_count": len(set(majority_truth_ids)),
        "offline_truth_only": True,
    }


def _score_pairs(
    pairs: Sequence[tuple[str, str]],
    truth_a: Mapping[str, str],
    truth_b: Mapping[str, str],
    target_count: int,
) -> dict[str, float | int]:
    correct_pairs = [
        pair
        for pair in pairs
        if truth_a.get(pair[0], "")
        and truth_a.get(pair[0], "") == truth_b.get(pair[1], "")
    ]
    unique = {truth_a[pair[0]] for pair in correct_pairs}
    return {
        "selected_match_count": len(pairs),
        "correct_match_count": len(correct_pairs),
        "false_match_count": len(pairs) - len(correct_pairs),
        "association_precision": len(correct_pairs) / max(len(pairs), 1),
        "unique_target_recall": len(unique) / target_count,
    }


def _count_states(association: AssociationResult) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in association.state_history:
        counts[item.state] = counts.get(item.state, 0) + 1
    return counts


def _track_sample_rows(tracks: Sequence[BearingTrack]) -> list[dict[str, Any]]:
    rows = []
    for track in tracks:
        for sample_index, sample in enumerate(track.samples):
            rows.append(
                {
                    "track_id": track.track_id,
                    "camera_id": track.camera_id,
                    "sample_index": sample_index,
                    "half_sweep_index": sample.half_sweep_index,
                    "measurement_timestamp": sample.timestamp,
                    "origin_x_ned": sample.origin_ned[0],
                    "origin_y_ned": sample.origin_ned[1],
                    "origin_z_ned": sample.origin_ned[2],
                    "ray_x_ned": sample.direction_ned[0],
                    "ray_y_ned": sample.direction_ned[1],
                    "ray_z_ned": sample.direction_ned[2],
                    "observation_uids": sample.observation_uids,
                }
            )
    return rows


def _match_scoring_rows(
    matches: Sequence[FinalMatch],
    truth_a: Mapping[str, str],
    truth_b: Mapping[str, str],
) -> list[dict[str, Any]]:
    rows = []
    for match in matches:
        first = truth_a.get(match.track_a_id, "")
        second = truth_b.get(match.track_b_id, "")
        rows.append(
            {
                "match_id": match.match_id,
                "track_a_id": match.track_a_id,
                "track_b_id": match.track_b_id,
                "truth_id_a": first,
                "truth_id_b": second,
                "correct": bool(first and first == second),
                "offline_truth_only": True,
            }
        )
    return rows


def _load_tracks(path: Path) -> tuple[BearingTrack, ...]:
    grouped: dict[tuple[str, str], list[BearingSample]] = {}
    for row in read_csv(path):
        key = (row["track_id"], row["camera_id"])
        grouped.setdefault(key, []).append(
            BearingSample(
                half_sweep_index=int(row["half_sweep_index"]),
                timestamp=float(row["measurement_timestamp"]),
                origin_ned=(
                    float(row["origin_x_ned"]),
                    float(row["origin_y_ned"]),
                    float(row["origin_z_ned"]),
                ),
                direction_ned=(
                    float(row["ray_x_ned"]),
                    float(row["ray_y_ned"]),
                    float(row["ray_z_ned"]),
                ),
                observation_uids=tuple(json.loads(row["observation_uids"])),
            )
        )
    return tuple(
        BearingTrack(track_id, camera_id, tuple(sorted(samples, key=lambda x: x.timestamp)))
        for (track_id, camera_id), samples in sorted(grouped.items())
    )


def _offline_pixel_truth_assignments(
    boxes: Sequence[tuple[float, float, float, float]],
    current_positions: Mapping[str, tuple[float, float, float]],
    state: CameraState,
    camera: CameraSpec,
) -> dict[int, tuple[str, float]]:
    projected = []
    for truth_id, position in sorted(current_positions.items()):
        pixel = project_world_point(position, state, camera)
        if pixel is not None:
            projected.append((truth_id, pixel))
    if not boxes or not projected:
        return {}
    centres = [((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5) for box in boxes]
    cost = np.asarray(
        [
            [math.dist(centre, pixel) for _, pixel in projected]
            for centre in centres
        ],
        dtype=float,
    )
    rows, columns = linear_sum_assignment(cost)
    return {
        int(row): (projected[column][0], float(cost[row, column]))
        for row, column in zip(rows, columns, strict=True)
        if cost[row, column] <= 80.0
    }


def _camera_pose(airsim_module: Any, yaw_deg: float, pitch_deg: float) -> Any:
    return airsim_module.Pose(
        airsim_module.Vector3r(0.0, 0.0, 0.0),
        airsim_module.to_quaternion(
            math.radians(pitch_deg), 0.0, math.radians(yaw_deg)
        ),
    )


def _world_pose(
    airsim_module: Any, position_ned: Sequence[float], yaw_deg: float
) -> Any:
    return airsim_module.Pose(
        airsim_module.Vector3r(*[float(value) for value in position_ned]),
        airsim_module.to_quaternion(0.0, 0.0, math.radians(yaw_deg)),
    )


def _bbox2d(detection: Any) -> tuple[float, float, float, float] | None:
    box = getattr(detection, "box2D", None)
    if box is None:
        return None
    values = (
        float(box.min.x_val),
        float(box.min.y_val),
        float(box.max.x_val),
        float(box.max.y_val),
    )
    if values[2] <= values[0] or values[3] <= values[1]:
        return None
    return values


def _box3d_longest_extent(detection: Any | None) -> float | None:
    box = getattr(detection, "box3D", None)
    if box is None:
        return None
    extents = (
        abs(float(box.max.x_val) - float(box.min.x_val)),
        abs(float(box.max.y_val) - float(box.min.y_val)),
        abs(float(box.max.z_val) - float(box.min.z_val)),
    )
    return max(extents) if max(extents) > 0.0 else None


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    materialized = [dict(row) for row in rows]
    fieldnames: list[str] = []
    for row in materialized:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as stream:
        if fieldnames:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(
                {key: _csv_value(value) for key, value in row.items()}
                for row in materialized
            )
    return path


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple, dict, np.ndarray)):
        return json.dumps(_jsonable(value), ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return value
