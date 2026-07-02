"""Real AirSim runtime client for Blocks smoke and controlled intercept tests."""

from __future__ import annotations

from collections.abc import Callable
import time
from pathlib import Path
from typing import Any

import numpy as np

from airsim_dryrun.models import (
    AirSimCameraInfo,
    AirSimDetectionBox,
    AirSimFrame,
    AirSimResourceState,
    AirSimTruthObject,
)

from .models import BlocksActorTargetSpec, BlocksSmokeConfig


class RealAirSimRuntimeClient:
    """Thin wrapper over the AirSim Python API.

    The default smoke path uses read/reset APIs plus simulator actor pose APIs
    for non-vehicle targets. Explicit controlled-intercept episodes call the
    control helpers below to enable SimpleFlight API control.
    """

    def __init__(
        self,
        client_factory: Callable[..., Any] | None = None,
        airsim_module: Any | None = None,
        ip: str = "",
        port: int = 41451,
        timeout_value: float = 2.0,
        client_kind: str = "vehicle",
    ) -> None:
        self.ip = ip
        self.port = port
        self.timeout_value = timeout_value
        self.client_kind = client_kind
        if client_factory is None or airsim_module is None:
            import airsim as imported_airsim

            airsim_module = imported_airsim if airsim_module is None else airsim_module
            if client_factory is None:
                if client_kind == "multirotor":
                    client_factory = imported_airsim.MultirotorClient
                else:
                    client_factory = imported_airsim.VehicleClient
        self.airsim = airsim_module
        self.client_factory = client_factory
        self.client = self._new_client()
        self._active_actor_targets: dict[str, dict[str, Any]] = {}
        self._episode_setup_metadata: dict[str, Any] = {}
        self._detection_history: dict[str, int] = {}

    def _new_client(self) -> Any:
        return self.client_factory(ip=self.ip, port=self.port, timeout_value=self.timeout_value)

    def reconnect(self) -> None:
        self.client = self._new_client()

    def wait_for_connection(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                if self.client.ping():
                    return
            except Exception as exc:  # pragma: no cover - depends on RPC transport
                last_error = exc
            time.sleep(1.0)
        message = "AirSim RPC did not become ready before timeout"
        if last_error is not None:
            message = f"{message}: {last_error}"
        raise TimeoutError(message)

    def ping(self) -> bool:
        return bool(self.client.ping())

    def reset(self) -> None:
        self.client.reset()
        time.sleep(1.0)
        self.reconnect()

    def prepare_interceptor_control(self, config: BlocksSmokeConfig) -> None:
        """Enable API control, arm, take off, and settle at intercept altitude."""

        for vehicle_name in config.resource_vehicle_names:
            self.client.enableApiControl(True, vehicle_name=vehicle_name)
            self.client.armDisarm(True, vehicle_name=vehicle_name)
        for vehicle_name in config.resource_vehicle_names:
            _join_future(
                self.client.takeoffAsync(
                    timeout_sec=config.intercept_takeoff_timeout_s,
                    vehicle_name=vehicle_name,
                )
            )
        for vehicle_name in config.resource_vehicle_names:
            target_z = _local_z_from_global_z(
                config,
                vehicle_name,
                config.intercept_altitude_ned_z,
            )
            _join_future(
                self.client.moveToZAsync(
                    target_z,
                    max(1.0, min(config.intercept_speed_mps, 3.0)),
                    timeout_sec=config.intercept_takeoff_timeout_s,
                    vehicle_name=vehicle_name,
                )
            )
            _join_future(self.client.hoverAsync(vehicle_name=vehicle_name))

    def command_velocity_z(
        self,
        config: BlocksSmokeConfig,
        *,
        vehicle_name: str,
        velocity_ned: tuple[float, float, float],
        duration_s: float,
    ) -> None:
        """Send a horizontal velocity command while holding configured NED Z."""

        target_z = _local_z_from_global_z(
            config,
            vehicle_name,
            config.intercept_altitude_ned_z,
        )
        vx, vy, _vz = velocity_ned
        yaw_deg = float(np.degrees(np.arctan2(vy, vx))) if abs(vx) + abs(vy) > 1e-9 else 0.0
        drivetrain_type = getattr(getattr(self.airsim, "DrivetrainType", object), "ForwardOnly", 0)
        yaw_mode_factory = getattr(self.airsim, "YawMode", None)
        yaw_mode = yaw_mode_factory(False, yaw_deg) if callable(yaw_mode_factory) else None
        if yaw_mode is None:
            future = self.client.moveByVelocityZAsync(
                float(vx),
                float(vy),
                float(target_z),
                float(duration_s),
                vehicle_name=vehicle_name,
            )
        else:
            future = self.client.moveByVelocityZAsync(
                float(vx),
                float(vy),
                float(target_z),
                float(duration_s),
                drivetrain_type,
                yaw_mode,
                vehicle_name=vehicle_name,
            )
        _join_future(future)

    def hover_interceptor(self, vehicle_name: str) -> None:
        _join_future(self.client.hoverAsync(vehicle_name=vehicle_name))

    def land_and_release_interceptors(
        self,
        vehicle_names: tuple[str, ...],
        *,
        land: bool = True,
    ) -> None:
        """Best-effort stop for controlled episodes."""

        for vehicle_name in vehicle_names:
            try:
                _join_future(self.client.hoverAsync(vehicle_name=vehicle_name))
            except Exception:
                pass
        if land:
            for vehicle_name in vehicle_names:
                try:
                    _join_future(self.client.landAsync(vehicle_name=vehicle_name))
                except Exception:
                    pass
        for vehicle_name in vehicle_names:
            try:
                self.client.armDisarm(False, vehicle_name=vehicle_name)
            except Exception:
                pass
            try:
                self.client.enableApiControl(False, vehicle_name=vehicle_name)
            except Exception:
                pass

    def collision_info(self, vehicle_name: str) -> dict[str, Any]:
        try:
            info = self.client.simGetCollisionInfo(vehicle_name=vehicle_name)
        except Exception as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}", "has_collided": False}
        return {
            "ok": True,
            "has_collided": bool(getattr(info, "has_collided", False)),
            "object_name": str(getattr(info, "object_name", "")),
            "object_id": int(getattr(info, "object_id", -1)),
            "time_stamp": int(getattr(info, "time_stamp", 0)),
        }

    def setup_episode(self, config: BlocksSmokeConfig) -> None:
        """Prepare actor targets and camera detection filters for one episode."""

        self._active_actor_targets = {}
        self._episode_setup_metadata = {"actor_targets": [], "detection_filters": []}
        self._detection_history = {}
        if config.target_actor_specs:
            self._destroy_stale_actor_targets(config)
            for spec in config.target_actor_specs:
                actor_name, spawned, reason = self._spawn_or_reuse_actor_target(spec)
                position = spec.position_at(0.0)
                moved = self._set_actor_pose(actor_name, position)
                self._active_actor_targets[spec.object_id] = {
                    "spec": spec,
                    "actor_name": actor_name,
                    "spawned": spawned,
                    "setup_reason": reason,
                    "initial_pose_set": moved,
                }
                self._episode_setup_metadata["actor_targets"].append(
                    {
                        "object_id": spec.object_id,
                        "actor_name": actor_name,
                        "asset_name": spec.asset_name,
                        "spawned": spawned,
                        "initial_pose_set": moved,
                        "reason": reason,
                    }
                )
        self._configure_detection_filters(config)

    def teardown_episode(self, config: BlocksSmokeConfig) -> None:
        """Remove actor targets spawned for this episode."""

        if not config.destroy_spawned_actor_targets:
            return
        for item in self._active_actor_targets.values():
            if item.get("spawned"):
                self._destroy_object(str(item["actor_name"]))
        self._active_actor_targets = {}

    def list_vehicles(self) -> tuple[str, ...]:
        last_error: Exception | None = None
        for attempt in range(20):
            try:
                return tuple(str(name) for name in self.client.listVehicles())
            except Exception as exc:
                last_error = exc
                if attempt < 19:
                    self.reconnect()
                    time.sleep(0.5)
        assert last_error is not None
        raise last_error

    def sample_frame(
        self,
        config: BlocksSmokeConfig,
        frame_index: int,
        timestamp: float,
        output_dir: Path,
    ) -> AirSimFrame:
        vehicles = set(self.list_vehicles())
        truth_objects = (
            self._truth_objects_for_actor_targets(config, timestamp)
            if config.target_actor_specs
            else tuple(
                self._truth_object_for_vehicle(
                    vehicle_name,
                    config=config,
                    truth_id=f"TGT-{index + 1:03d}",
                    timestamp=timestamp,
                    coverage_cell="cell-north",
                )
                for index, vehicle_name in enumerate(config.target_vehicle_names)
                if vehicle_name in vehicles
            )
        )
        resources = tuple(
            self._resource_for_vehicle(
                vehicle_name,
                config=config,
                resource_id=f"INT-{index + 1:02d}",
                timestamp=timestamp,
                coverage_cell="cell-north",
            )
            for index, vehicle_name in enumerate(config.resource_vehicle_names)
            if vehicle_name in vehicles
        )
        camera_vehicle_names = tuple(
            name for name in config.effective_camera_vehicle_names() if not vehicles or name in vehicles
        )
        cameras = tuple(
            self._camera_info(config, timestamp, camera_vehicle_name=vehicle_name)
            for vehicle_name in camera_vehicle_names
        )
        image_metas = [
            self._capture_image(config, frame_index, output_dir, camera_vehicle_name=vehicle_name)
            for vehicle_name in camera_vehicle_names
        ]
        lidar_metas = [
            self._capture_lidar(config, lidar_vehicle_name=vehicle_name)
            for vehicle_name in config.effective_lidar_vehicle_names()
            if not vehicles or vehicle_name in vehicles
        ]
        visual_detections, detection_meta = self._capture_detections(
            config,
            frame_index=frame_index,
            timestamp=timestamp,
            camera_vehicle_names=camera_vehicle_names,
        )
        scene_objects = self._scene_objects()
        return AirSimFrame(
            episode_id=config.episode_id,
            scenario_name=config.scenario_name,
            frame_index=frame_index,
            timestamp=timestamp,
            truth_objects=truth_objects,
            resources=resources,
            cameras=cameras,
            visual_detections=visual_detections,
            center_node_alive=True,
            secondary_nodes_alive=True,
            metadata={
                "runtime": "Blocks",
                "real_airsim_used": True,
                "vehicle_names": sorted(vehicles),
                "image": image_metas[0] if image_metas else {"ok": False, "reason": "no_camera_vehicle"},
                "images": image_metas,
                "lidar": lidar_metas[0] if lidar_metas else {"ok": False, "reason": "no_lidar_vehicle"},
                "lidars": lidar_metas,
                "detections": detection_meta,
                "detection_count": len(visual_detections),
                "actor_targets": self._episode_setup_metadata.get("actor_targets", []),
                "scene_object_count": len(scene_objects),
                "scene_objects_sample": scene_objects[:20],
            },
        )

    def _truth_objects_for_actor_targets(
        self,
        config: BlocksSmokeConfig,
        timestamp: float,
    ) -> tuple[AirSimTruthObject, ...]:
        truth_objects: list[AirSimTruthObject] = []
        for spec in config.target_actor_specs:
            item = self._active_actor_targets.get(spec.object_id)
            actor_name = str(item.get("actor_name")) if item else spec.actor_name
            planned_position = spec.position_at(timestamp)
            moved = self._set_actor_pose(actor_name, planned_position)
            position = self._object_position_ned(actor_name, fallback=planned_position)
            truth_objects.append(
                AirSimTruthObject(
                    object_id=spec.object_id,
                    object_type="target",
                    timestamp=timestamp,
                    position_ned=position,
                    velocity_ned=spec.velocity_ned,
                    classification_hint="uav",
                    threat_score=spec.threat_score,
                    coverage_cell=spec.coverage_cell,
                    metadata={
                        "airsim_actor_name": actor_name,
                        "actor_asset_name": spec.asset_name,
                        "planned_position_ned": planned_position,
                        "pose_update_ok": moved,
                    },
                )
            )
        return tuple(truth_objects)

    def _truth_object_for_vehicle(
        self,
        vehicle_name: str,
        config: BlocksSmokeConfig,
        truth_id: str,
        timestamp: float,
        coverage_cell: str,
    ) -> AirSimTruthObject:
        position = self._vehicle_position_ned(vehicle_name, config=config)
        velocity = self._vehicle_velocity(vehicle_name)
        return AirSimTruthObject(
            object_id=truth_id,
            object_type="target",
            timestamp=timestamp,
            position_ned=position,
            velocity_ned=velocity,
            classification_hint="uav",
            threat_score=0.9,
            coverage_cell=coverage_cell,
            metadata={"airsim_vehicle_name": vehicle_name},
        )

    def _resource_for_vehicle(
        self,
        vehicle_name: str,
        config: BlocksSmokeConfig,
        resource_id: str,
        timestamp: float,
        coverage_cell: str,
    ) -> AirSimResourceState:
        position = self._vehicle_position_ned(vehicle_name, config=config)
        velocity = self._vehicle_velocity(vehicle_name)
        return AirSimResourceState(
            resource_id=resource_id,
            timestamp=timestamp,
            position_ned=position,
            velocity_ned=velocity,
            status="available",
            health_score=1.0,
            role="interceptor",
            coverage_cell=coverage_cell,
            metadata={"airsim_vehicle_name": vehicle_name},
        )

    def _vehicle_velocity(self, vehicle_name: str) -> tuple[float, float, float]:
        try:
            state = self.client.getMultirotorState(vehicle_name=vehicle_name)
            return _vector3_from_airsim(state.kinematics_estimated.linear_velocity)
        except Exception:
            return (0.0, 0.0, 0.0)

    def _vehicle_position_ned(
        self,
        vehicle_name: str,
        config: BlocksSmokeConfig | None,
    ) -> tuple[float, float, float]:
        pose = self.client.simGetVehiclePose(vehicle_name)
        local_position = _vector3_from_airsim(pose.position)
        if config is None:
            return local_position
        start = _vehicle_start_offset(config, vehicle_name)
        return tuple(local_position[index] + start[index] for index in range(3))

    def _camera_info(
        self,
        config: BlocksSmokeConfig,
        timestamp: float,
        *,
        camera_vehicle_name: str | None = None,
    ) -> AirSimCameraInfo:
        vehicle_name = camera_vehicle_name or config.camera_vehicle_name
        try:
            info = self.client.simGetCameraInfo(config.camera_name, vehicle_name)
            pose = info.pose
            position = _vector3_from_airsim(pose.position)
        except Exception:
            position = (0.0, 0.0, 0.0)
        return AirSimCameraInfo(
            camera_id=f"{vehicle_name}:{config.camera_name}",
            owner_id=vehicle_name,
            timestamp=timestamp,
            position_ned=position,
            width=640,
            height=480,
        )

    def _capture_image(
        self,
        config: BlocksSmokeConfig,
        frame_index: int,
        output_dir: Path,
        *,
        camera_vehicle_name: str | None = None,
    ) -> dict[str, Any]:
        vehicle_name = camera_vehicle_name or config.camera_vehicle_name
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            request = self.airsim.ImageRequest(
                config.camera_name,
                self.airsim.ImageType.Scene,
                False,
                True,
            )
            responses = self.client.simGetImages([request], vehicle_name=vehicle_name)
            if not responses:
                return {"ok": False, "reason": "no_image_response"}
            response = responses[0]
            data = bytes(response.image_data_uint8)
            if not data:
                return {"ok": False, "reason": "empty_image_data"}
            image_path = output_dir / f"frame_{frame_index:04d}_{vehicle_name}_scene.png"
            image_path.write_bytes(data)
            return {
                "ok": True,
                "path": str(image_path),
                "width": int(response.width),
                "height": int(response.height),
                "image_type": int(response.image_type),
                "camera_vehicle_name": vehicle_name,
                "camera_name": config.camera_name,
            }
        except Exception as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}

    def _capture_lidar(
        self,
        config: BlocksSmokeConfig,
        *,
        lidar_vehicle_name: str | None = None,
    ) -> dict[str, Any]:
        vehicle_name = lidar_vehicle_name or config.lidar_vehicle_name
        try:
            lidar = self.client.getLidarData(config.lidar_name, vehicle_name)
            point_count = int(len(lidar.point_cloud) / 3)
            return {
                "ok": True,
                "point_count": point_count,
                "time_stamp": int(getattr(lidar, "time_stamp", 0)),
                "lidar_vehicle_name": vehicle_name,
                "lidar_name": config.lidar_name,
            }
        except Exception as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}

    def _capture_detections(
        self,
        config: BlocksSmokeConfig,
        *,
        frame_index: int,
        timestamp: float,
        camera_vehicle_names: tuple[str, ...],
    ) -> tuple[tuple[AirSimDetectionBox, ...], list[dict[str, Any]]]:
        detections: list[AirSimDetectionBox] = []
        metadata: list[dict[str, Any]] = []
        for vehicle_name in camera_vehicle_names:
            try:
                raw_detections = self.client.simGetDetections(
                    config.camera_name,
                    self.airsim.ImageType.Scene,
                    vehicle_name=vehicle_name,
                )
            except Exception as exc:
                metadata.append(
                    {
                        "ok": False,
                        "camera_vehicle_name": vehicle_name,
                        "camera_name": config.camera_name,
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            metadata.append(
                {
                    "ok": True,
                    "camera_vehicle_name": vehicle_name,
                    "camera_name": config.camera_name,
                    "count": len(raw_detections),
                }
            )
            for index, raw in enumerate(raw_detections):
                name = str(getattr(raw, "name", f"detection_{index}"))
                bbox = _bbox2d_from_detection(raw)
                center = ((bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5)
                object_id = self._object_id_for_actor_name(name) or name
                camera_id = f"{vehicle_name}:{config.camera_name}"
                local_track_id = f"{camera_id}:{name}"
                self._detection_history[local_track_id] = self._detection_history.get(local_track_id, 0) + 1
                detections.append(
                    AirSimDetectionBox(
                        detection_id=f"{camera_id}:{frame_index:04d}:{index}:{name}",
                        camera_id=camera_id,
                        object_id=object_id,
                        local_track_id=local_track_id,
                        timestamp=timestamp,
                        center_px=center,
                        bbox_xyxy=bbox,
                        confidence=1.0,
                        classification_hint="uav",
                        metadata={
                            "source": "airsim_builtin_detection",
                            "airsim_detection_name": name,
                            "mot_history_length": self._detection_history[local_track_id],
                            "relative_pose": _pose_to_dict(getattr(raw, "relative_pose", None)),
                            "box3d": _box3d_to_dict(getattr(raw, "box3D", None)),
                        },
                    )
                )
        return tuple(detections), metadata

    def _scene_objects(self) -> list[str]:
        try:
            return [str(name) for name in self.client.simListSceneObjects(".*")]
        except Exception:
            return []

    def _destroy_stale_actor_targets(self, config: BlocksSmokeConfig) -> None:
        for spec in config.target_actor_specs:
            self._destroy_object(spec.actor_name)

    def _spawn_or_reuse_actor_target(self, spec: BlocksActorTargetSpec) -> tuple[str, bool, str]:
        pose = self._pose_from_position(spec.position_at(0.0))
        scale = self._vector3(*spec.scale)
        try:
            spawned_name = self.client.simSpawnObject(
                spec.actor_name,
                spec.asset_name,
                pose,
                scale,
                False,
            )
            if spawned_name:
                return str(spawned_name), True, "spawned"
        except Exception as exc:
            if spec.fallback_actor_name:
                return spec.fallback_actor_name, False, f"spawn_failed_fallback: {type(exc).__name__}: {exc}"
            return spec.actor_name, False, f"spawn_failed: {type(exc).__name__}: {exc}"
        if spec.fallback_actor_name:
            return spec.fallback_actor_name, False, "spawn_returned_empty_fallback"
        return spec.actor_name, False, "spawn_returned_empty"

    def _configure_detection_filters(self, config: BlocksSmokeConfig) -> None:
        filters = list(config.detection_filter_names)
        filters.extend(str(item["actor_name"]) for item in self._active_actor_targets.values())
        unique_filters = tuple(dict.fromkeys(filters))
        for vehicle_name in config.effective_camera_vehicle_names():
            configured: list[str] = []
            try:
                self.client.simClearDetectionMeshNames(
                    config.camera_name,
                    self.airsim.ImageType.Scene,
                    vehicle_name=vehicle_name,
                )
                self.client.simSetDetectionFilterRadius(
                    config.camera_name,
                    self.airsim.ImageType.Scene,
                    int(config.detection_radius_cm),
                    vehicle_name=vehicle_name,
                )
                for mesh_name in unique_filters:
                    self.client.simAddDetectionFilterMeshName(
                        config.camera_name,
                        self.airsim.ImageType.Scene,
                        mesh_name,
                        vehicle_name=vehicle_name,
                    )
                    configured.append(mesh_name)
                self._episode_setup_metadata["detection_filters"].append(
                    {
                        "ok": True,
                        "camera_vehicle_name": vehicle_name,
                        "camera_name": config.camera_name,
                        "radius_cm": int(config.detection_radius_cm),
                        "filters": configured,
                    }
                )
            except Exception as exc:
                self._episode_setup_metadata["detection_filters"].append(
                    {
                        "ok": False,
                        "camera_vehicle_name": vehicle_name,
                        "camera_name": config.camera_name,
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                )

    def _set_actor_pose(self, actor_name: str, position_ned: tuple[float, float, float]) -> bool:
        try:
            return bool(self.client.simSetObjectPose(actor_name, self._pose_from_position(position_ned), True))
        except Exception:
            return False

    def _object_position_ned(
        self,
        actor_name: str,
        *,
        fallback: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        try:
            pose = self.client.simGetObjectPose(actor_name)
            position = _vector3_from_airsim(pose.position)
            if any(np.isnan(value) for value in position):
                return fallback
            return position
        except Exception:
            return fallback

    def _destroy_object(self, actor_name: str) -> bool:
        try:
            return bool(self.client.simDestroyObject(actor_name))
        except Exception:
            return False

    def _object_id_for_actor_name(self, actor_name: str) -> str | None:
        for object_id, item in self._active_actor_targets.items():
            active_name = str(item["actor_name"])
            if actor_name == active_name or actor_name.startswith(active_name):
                return object_id
        return None

    def _pose_from_position(self, position_ned: tuple[float, float, float]) -> Any:
        return self.airsim.Pose(position_val=self._vector3(*position_ned))

    def _vector3(self, x: float, y: float, z: float) -> Any:
        return self.airsim.Vector3r(float(x), float(y), float(z))


def _vector3_from_airsim(value: Any) -> tuple[float, float, float]:
    if hasattr(value, "x_val"):
        return (float(value.x_val), float(value.y_val), float(value.z_val))
    array = np.asarray(value, dtype=float).reshape(3)
    return (float(array[0]), float(array[1]), float(array[2]))


def _vector2_from_airsim(value: Any) -> tuple[float, float]:
    if hasattr(value, "x_val"):
        return (float(value.x_val), float(value.y_val))
    array = np.asarray(value, dtype=float).reshape(2)
    return (float(array[0]), float(array[1]))


def _bbox2d_from_detection(detection: Any) -> tuple[float, float, float, float]:
    box = getattr(detection, "box2D")
    min_xy = _vector2_from_airsim(box.min)
    max_xy = _vector2_from_airsim(box.max)
    return (min_xy[0], min_xy[1], max_xy[0], max_xy[1])


def _pose_to_dict(pose: Any | None) -> dict[str, Any]:
    if pose is None:
        return {}
    payload: dict[str, Any] = {}
    position = getattr(pose, "position", None)
    orientation = getattr(pose, "orientation", None)
    if position is not None:
        payload["position"] = _vector3_from_airsim(position)
    if orientation is not None:
        payload["orientation"] = {
            "w": float(getattr(orientation, "w_val", 0.0)),
            "x": float(getattr(orientation, "x_val", 0.0)),
            "y": float(getattr(orientation, "y_val", 0.0)),
            "z": float(getattr(orientation, "z_val", 0.0)),
        }
    return payload


def _box3d_to_dict(box: Any | None) -> dict[str, Any]:
    if box is None:
        return {}
    return {
        "min": _vector3_from_airsim(box.min),
        "max": _vector3_from_airsim(box.max),
    }


def _vehicle_start_offset(config: BlocksSmokeConfig, vehicle_name: str) -> tuple[float, float, float]:
    """Initial AirSim vehicle offset in PlayerStart NED coordinates.

    AirSim's simGetVehiclePose returns pose relative to each vehicle's start
    point, so multi-vehicle global tracks need the settings X/Y/Z added back.
    """
    vehicles = config._settings().get("Vehicles", {})
    vehicle = vehicles.get(vehicle_name, {}) if isinstance(vehicles, dict) else {}
    return (
        float(vehicle.get("X", 0.0)),
        float(vehicle.get("Y", 0.0)),
        float(vehicle.get("Z", 0.0)),
    )


def _local_z_from_global_z(
    config: BlocksSmokeConfig,
    vehicle_name: str,
    global_z: float,
) -> float:
    start = _vehicle_start_offset(config, vehicle_name)
    return float(global_z - start[2])


def _join_future(future: Any) -> None:
    join = getattr(future, "join", None)
    if callable(join):
        join()
