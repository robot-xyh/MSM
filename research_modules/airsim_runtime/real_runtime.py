"""Real AirSim runtime client for Blocks smoke and controlled intercept tests."""

from __future__ import annotations

from collections.abc import Callable
import math
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from airsim_dryrun.models import (
    AirSimCameraInfo,
    AirSimDetectionBox,
    AirSimFrame,
    AirSimResourceState,
    AirSimTruthObject,
)
from d5_terminal_association.airsim_geometry import (
    intrinsics_from_capture_settings,
    rotation_world_to_opencv_camera_from_quaternion,
)
from d5_terminal_association import (
    LocalVisualTrack,
    YoloMotAdapter,
    YoloMotAdapterConfig,
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
        yolo_adapter_factory: Callable[[YoloMotAdapterConfig], YoloMotAdapter] | None = None,
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
        self._yolo_adapter_factory = yolo_adapter_factory
        self._yolo_mot_adapters: dict[str, YoloMotAdapter] = {}
        self._scene_image_frame_cache: dict[tuple[int, str, str], tuple[Any, dict[str, Any]]] = {}
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
        yaw_deg_override: float | None = None,
    ) -> None:
        """Send a horizontal velocity command while holding configured NED Z."""

        target_z = _local_z_from_global_z(
            config,
            vehicle_name,
            config.intercept_altitude_ned_z,
        )
        vx, vy, _vz = velocity_ned
        yaw_deg = (
            float(yaw_deg_override)
            if yaw_deg_override is not None
            else float(np.degrees(np.arctan2(vy, vx)))
            if abs(vx) + abs(vy) > 1e-9
            else 0.0
        )
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
        self._yolo_mot_adapters = {}
        self._scene_image_frame_cache = {}
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
        cv_camera_guidance = self._update_cv_camera_poses_for_assignments(
            config,
            timestamp,
            truth_objects,
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
        lidar_metas = (
            [
                self._capture_lidar(config, lidar_vehicle_name=vehicle_name)
                for vehicle_name in config.effective_lidar_vehicle_names()
                if not vehicles or vehicle_name in vehicles
            ]
            if config.capture_lidar
            else []
        )
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
                "camera_vehicle_names": list(camera_vehicle_names),
                "resource_vehicle_names": list(config.resource_vehicle_names),
                "secondary_camera_vehicle_names": list(config.secondary_camera_vehicle_names),
                "cv_camera_guidance": cv_camera_guidance,
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
            start = _vehicle_start_offset(config, vehicle_name)
            position = tuple(position[index] + start[index] for index in range(3))
            orientation = getattr(pose, "orientation", None)
            rotation_world_to_camera = (
                rotation_world_to_opencv_camera_from_quaternion(orientation)
                if orientation is not None
                else None
            )
        except Exception:
            position = _camera_position_from_settings(config, vehicle_name, config.camera_name)
            rotation_world_to_camera = None
        intrinsics = _camera_intrinsics_from_settings(config, vehicle_name, config.camera_name)
        if rotation_world_to_camera is None:
            rotation_world_to_camera = _rotation_from_settings_or_identity(config, vehicle_name, config.camera_name)
        return AirSimCameraInfo(
            camera_id=f"{vehicle_name}:{config.camera_name}",
            owner_id=vehicle_name,
            timestamp=timestamp,
            position_ned=position,
            rotation_world_to_camera=tuple(tuple(float(value) for value in row) for row in rotation_world_to_camera),
            fx=float(intrinsics.K[0, 0]),
            fy=float(intrinsics.K[1, 1]),
            cx=float(intrinsics.K[0, 2]),
            cy=float(intrinsics.K[1, 2]),
            width=intrinsics.width,
            height=intrinsics.height,
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
            metadata = {
                "ok": True,
                "saved": False,
                "width": int(response.width),
                "height": int(response.height),
                "image_type": int(response.image_type),
                "camera_vehicle_name": vehicle_name,
                "camera_name": config.camera_name,
            }
            if str(config.detection_backend).lower() in {"yolo", "yolov8", "yolo_mot"}:
                decoded, decode_backend = _decode_scene_image_bytes(data)
                self._scene_image_frame_cache[
                    (frame_index, vehicle_name, config.camera_name)
                ] = (
                    decoded,
                    {
                        **metadata,
                        "byte_count": len(data),
                        "decode_backend": decode_backend,
                    },
                )
                metadata["decode_backend"] = decode_backend
            if config.save_images:
                image_path = output_dir / f"frame_{frame_index:04d}_{vehicle_name}_scene.png"
                image_path.write_bytes(data)
                metadata["saved"] = True
                metadata["path"] = str(image_path)
            return metadata
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
        backend = str(config.detection_backend).lower()
        if backend in {"yolo", "yolov8", "yolo_mot"}:
            return self._capture_yolo_mot_detections(
                config,
                frame_index=frame_index,
                timestamp=timestamp,
                camera_vehicle_names=camera_vehicle_names,
            )
        if backend not in {"airsim", "detect", "simgetdetections", "airsim_builtin"}:
            return (), [
                {
                    "ok": False,
                    "backend": backend,
                    "reason": f"unsupported detection_backend {config.detection_backend!r}",
                }
            ]
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

    def _capture_yolo_mot_detections(
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
            camera_id = f"{vehicle_name}:{config.camera_name}"
            resource_id = _resource_id_for_vehicle(config, vehicle_name)
            image_frame, image_meta = self._capture_scene_image_frame(
                config,
                frame_index=frame_index,
                camera_vehicle_name=vehicle_name,
            )
            if image_frame is None:
                metadata.append(
                    {
                        "ok": False,
                        "backend": "yolo",
                        "camera_vehicle_name": vehicle_name,
                        "camera_name": config.camera_name,
                        "reason": image_meta.get("reason", "image_unavailable"),
                        "image": image_meta,
                    }
                )
                continue
            adapter = self._yolo_mot_adapter(config, camera_id)
            result = adapter.process_frame(
                image_frame,
                resource_id=resource_id,
                camera_id=camera_id,
                frame_id=f"{camera_id}:{frame_index:04d}",
                timestamp=timestamp,
            )
            result_meta = {
                "ok": result.status == "ok",
                "backend": "yolo",
                "camera_vehicle_name": vehicle_name,
                "camera_name": config.camera_name,
                "camera_id": camera_id,
                "resource_id": resource_id,
                "status": result.status,
                "detector_backend": result.detector_backend,
                "tracker_backend": result.tracker_backend,
                "count": len(result.tracks),
                "image": image_meta,
                **dict(result.metadata),
            }
            metadata.append(result_meta)
            for index, track in enumerate(result.tracks):
                detections.append(
                    _detection_from_yolo_track(
                        track,
                        camera_id=camera_id,
                        frame_index=frame_index,
                        detection_index=index,
                        timestamp=timestamp,
                        result_metadata=result_meta,
                    )
                )
        return tuple(detections), metadata

    def _capture_scene_image_frame(
        self,
        config: BlocksSmokeConfig,
        *,
        frame_index: int,
        camera_vehicle_name: str,
    ) -> tuple[Any | None, dict[str, Any]]:
        cached = self._scene_image_frame_cache.get(
            (frame_index, camera_vehicle_name, config.camera_name)
        )
        if cached is not None:
            return cached
        try:
            request = self.airsim.ImageRequest(
                config.camera_name,
                self.airsim.ImageType.Scene,
                False,
                True,
            )
            responses = self.client.simGetImages([request], vehicle_name=camera_vehicle_name)
            if not responses:
                return None, {"ok": False, "reason": "no_image_response"}
            response = responses[0]
            data = bytes(response.image_data_uint8)
            if not data:
                return None, {"ok": False, "reason": "empty_image_data"}
            decoded, decode_backend = _decode_scene_image_bytes(data)
            return decoded, {
                "ok": True,
                "width": int(response.width),
                "height": int(response.height),
                "image_type": int(response.image_type),
                "camera_vehicle_name": camera_vehicle_name,
                "camera_name": config.camera_name,
                "byte_count": len(data),
                "decode_backend": decode_backend,
            }
        except Exception as exc:
            return None, {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}

    def _yolo_mot_adapter(
        self,
        config: BlocksSmokeConfig,
        camera_id: str,
    ) -> YoloMotAdapter:
        adapter = self._yolo_mot_adapters.get(camera_id)
        if adapter is not None:
            return adapter
        adapter_config = YoloMotAdapterConfig(
            weights_path=config.yolo_weights_path,
            tracker_backend=config.yolo_tracker_backend,
            confidence_threshold=config.yolo_confidence_threshold,
            use_native_ultralytics_tracker=config.yolo_use_native_tracker,
            allow_iou_fallback=config.yolo_allow_iou_fallback,
        )
        adapter = (
            self._yolo_adapter_factory(adapter_config)
            if self._yolo_adapter_factory is not None
            else YoloMotAdapter(adapter_config)
        )
        self._yolo_mot_adapters[camera_id] = adapter
        return adapter

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

    def _update_cv_camera_poses_for_assignments(
        self,
        config: BlocksSmokeConfig,
        timestamp: float,
        truth_objects: tuple[AirSimTruthObject, ...],
    ) -> list[dict[str, Any]]:
        if not config.cv_camera_follow_assignments or not config.target_actor_specs:
            return []
        truth_by_id = {truth.object_id: truth for truth in truth_objects}
        guidance: list[dict[str, Any]] = []
        for vehicle_name in config.resource_vehicle_names:
            target_id, phase = _cv_assignment_target_id(config, vehicle_name, timestamp)
            target = truth_by_id.get(target_id)
            if target is None:
                guidance.append(
                    {
                        "vehicle_name": vehicle_name,
                        "role": "interceptor_camera",
                        "target_id": target_id,
                        "assignment_phase": phase,
                        "pose_update_ok": False,
                        "reason": "target_not_available",
                    }
                )
                continue
            start = _vehicle_start_offset(config, vehicle_name)
            position = _follow_position(
                start,
                target.position_ned,
                follow_distance_m=config.cv_camera_follow_distance_m,
            )
            pose_update = self._set_vehicle_pose_look_at(config, vehicle_name, position, target.position_ned)
            guidance.append(
                {
                    "vehicle_name": vehicle_name,
                    "role": "interceptor_camera",
                    "target_id": target_id,
                    "assignment_phase": phase,
                    "position_ned": position,
                    "look_at_ned": target.position_ned,
                    **pose_update,
                }
            )

        if config.cv_secondary_look_at_enabled:
            for vehicle_name in config.secondary_camera_vehicle_names:
                recon_guidance = _secondary_recon_guidance(config, vehicle_name, truth_objects)
                if recon_guidance is None:
                    continue
                target_position = recon_guidance["look_at_ned"]
                position = recon_guidance["position_ned"]
                pose_update = self._set_vehicle_pose_look_at(config, vehicle_name, position, target_position)
                guidance.append(
                    {
                        "vehicle_name": vehicle_name,
                        "role": "secondary_recon_camera",
                        "capability_class": recon_guidance["capability_class"],
                        "target_id": recon_guidance["target_id"],
                        "assignment_phase": "secondary_overwatch",
                        "cue_source": recon_guidance["cue_source"],
                        "cue_freshness_s": recon_guidance["cue_freshness_s"],
                        "cue_covariance_trace": recon_guidance["cue_covariance_trace"],
                        "coverage_cell": recon_guidance["coverage_cell"],
                        "active_target_ids": recon_guidance["active_target_ids"],
                        "cue_position_ned": recon_guidance["cue_position_ned"],
                        "position_ned": position,
                        "look_at_ned": target_position,
                        "cue_pointing_error_m": recon_guidance["cue_pointing_error_m"],
                        "gimbal_pointing_ok": pose_update.get("pose_update_ok") is True,
                        **pose_update,
                    }
                )
        return guidance

    def _set_vehicle_pose_look_at(
        self,
        config: BlocksSmokeConfig,
        vehicle_name: str,
        position_ned: tuple[float, float, float],
        target_ned: tuple[float, float, float],
    ) -> dict[str, Any]:
        pitch, roll, yaw = _look_at_euler_ned(position_ned, target_ned)
        orientation = self._quaternion_from_euler(pitch, roll, yaw)
        try:
            start = _vehicle_start_offset(config, vehicle_name)
            local_position = tuple(position_ned[index] - start[index] for index in range(3))
            pose = self._pose_from_position_orientation(local_position, orientation)
            result = self.client.simSetVehiclePose(
                pose,
                ignore_collision=True,
                vehicle_name=vehicle_name,
            )
            ok = result is not False
            reason = "updated" if ok else "airsim_returned_false"
        except Exception as exc:
            ok = False
            reason = f"{type(exc).__name__}: {exc}"
        return {
            "pose_update_ok": ok,
            "reason": reason,
            "yaw_rad": yaw,
            "pitch_rad": pitch,
            "roll_rad": roll,
            "yaw_deg": math.degrees(yaw),
            "pitch_deg": math.degrees(pitch),
            "roll_deg": math.degrees(roll),
        }

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

    def _pose_from_position_orientation(
        self,
        position_ned: tuple[float, float, float],
        orientation: Any,
    ) -> Any:
        position = self._vector3(*position_ned)
        try:
            return self.airsim.Pose(position_val=position, orientation_val=orientation)
        except TypeError:
            pose = self.airsim.Pose(position_val=position)
            try:
                pose.orientation = orientation
            except Exception:
                pass
            return pose

    def _quaternion_from_euler(self, pitch: float, roll: float, yaw: float) -> Any:
        to_quaternion = getattr(self.airsim, "to_quaternion", None)
        if callable(to_quaternion):
            return to_quaternion(float(pitch), float(roll), float(yaw))
        quaternion_cls = getattr(self.airsim, "Quaternionr", None)
        quat = _quaternion_components_from_euler(pitch, roll, yaw)
        if callable(quaternion_cls):
            return quaternion_cls(quat["x"], quat["y"], quat["z"], quat["w"])
        return SimpleNamespace(
            x_val=quat["x"],
            y_val=quat["y"],
            z_val=quat["z"],
            w_val=quat["w"],
        )

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


def _cv_assignment_target_id(
    config: BlocksSmokeConfig,
    vehicle_name: str,
    timestamp: float,
) -> tuple[str, str]:
    resource_names = tuple(config.resource_vehicle_names)
    target_specs = tuple(config.target_actor_specs)
    if not target_specs:
        return ("", "unassigned")
    try:
        index = resource_names.index(vehicle_name)
    except ValueError:
        index = 0
    target_index = min(index, len(target_specs) - 1)
    phase = "initial_assignment"
    if config.cv_reassignment_time_s is not None and timestamp >= config.cv_reassignment_time_s:
        phase = "secondary_reassignment"
        if target_index == 1 and len(target_specs) > 2:
            target_index = 2
        elif target_index == 2 and len(target_specs) > 1:
            target_index = 1
    return target_specs[target_index].object_id, phase


def _follow_position(
    start_ned: tuple[float, float, float],
    target_ned: tuple[float, float, float],
    *,
    follow_distance_m: float,
) -> tuple[float, float, float]:
    start = np.asarray(start_ned, dtype=float)
    target = np.asarray(target_ned, dtype=float)
    direction = start - target
    horizontal = direction.copy()
    horizontal[2] = 0.0
    norm = float(np.linalg.norm(horizontal))
    if norm < 1e-6:
        horizontal = np.array([-1.0, 0.0, 0.0], dtype=float)
        norm = 1.0
    unit = horizontal / norm
    position = target.copy()
    position[:2] = target[:2] + unit[:2] * max(float(follow_distance_m), 1.0)
    position[2] = start[2]
    return tuple(float(value) for value in position)


def _secondary_look_at_position(
    config: BlocksSmokeConfig,
    vehicle_name: str,
    truth_objects: tuple[AirSimTruthObject, ...],
) -> tuple[float, float, float] | None:
    subset = _secondary_truth_subset(config, vehicle_name, truth_objects)
    if not subset:
        return None
    positions = np.asarray([truth.position_ned for truth in subset], dtype=float)
    centroid = np.mean(positions, axis=0)
    return tuple(float(value) for value in centroid)


def _secondary_recon_guidance(
    config: BlocksSmokeConfig,
    vehicle_name: str,
    truth_objects: tuple[AirSimTruthObject, ...],
) -> dict[str, Any] | None:
    subset = _secondary_truth_subset(config, vehicle_name, truth_objects)
    if not subset:
        return None
    positions = np.asarray([truth.position_ned for truth in subset], dtype=float)
    cue_position = tuple(float(value) for value in np.mean(positions, axis=0))
    position = (
        _mobile_secondary_recon_position(config, vehicle_name, cue_position)
        if config.cv_secondary_mobile_recon_enabled
        else _vehicle_start_offset(config, vehicle_name)
    )
    coverage_cell = _secondary_expected_cell(config, vehicle_name)
    cue_error = float(np.linalg.norm(np.asarray(cue_position, dtype=float) - np.asarray(cue_position, dtype=float)))
    return {
        "capability_class": (
            "mobile_high_recon"
            if config.cv_secondary_mobile_recon_enabled
            else str(config.metadata.get("secondary_capability_class", "fixed_secondary_recon"))
        ),
        "cue_source": (
            "radar_global_track_cue"
            if config.cv_secondary_mobile_recon_enabled
            else str(config.metadata.get("secondary_guidance_source", "coverage_centroid"))
        ),
        "cue_freshness_s": 0.0,
        "cue_covariance_trace": _secondary_cue_covariance_trace(subset),
        "coverage_cell": coverage_cell,
        "target_id": f"{coverage_cell}_centroid" if coverage_cell != "all" else "coverage_centroid",
        "active_target_ids": [truth.object_id for truth in subset],
        "cue_position_ned": cue_position,
        "position_ned": position,
        "look_at_ned": cue_position,
        "cue_pointing_error_m": cue_error,
    }


def _secondary_truth_subset(
    config: BlocksSmokeConfig,
    vehicle_name: str,
    truth_objects: tuple[AirSimTruthObject, ...],
) -> list[AirSimTruthObject]:
    if not truth_objects:
        return []
    expected_cell = _secondary_expected_cell(config, vehicle_name)
    if expected_cell == "all":
        return list(truth_objects)
    selected = [truth for truth in truth_objects if truth.coverage_cell == expected_cell]
    return selected if selected else list(truth_objects)


def _secondary_expected_cell(config: BlocksSmokeConfig, vehicle_name: str) -> str:
    secondary_names = tuple(config.secondary_camera_vehicle_names)
    try:
        index = secondary_names.index(vehicle_name)
    except ValueError:
        index = 0
    if len(secondary_names) <= 1:
        return "all"
    midpoint = (len(secondary_names) - 1) * 0.5
    return "cell-north" if index <= midpoint else "cell-south"


def _mobile_secondary_recon_position(
    config: BlocksSmokeConfig,
    vehicle_name: str,
    cue_position_ned: tuple[float, float, float],
) -> tuple[float, float, float]:
    start = _vehicle_start_offset(config, vehicle_name)
    standoff = float(config.cv_secondary_recon_standoff_m)
    return (
        float(cue_position_ned[0]) - max(standoff, 0.0),
        float(cue_position_ned[1]),
        float(start[2]),
    )


def _secondary_cue_covariance_trace(subset: list[AirSimTruthObject]) -> float:
    if not subset:
        return 0.0
    positions = np.asarray([truth.position_ned for truth in subset], dtype=float)
    if len(subset) <= 1:
        return 25.0
    covariance = np.cov(positions.T)
    trace = float(np.trace(covariance))
    return max(trace, 25.0)


def _look_at_euler_ned(
    position_ned: tuple[float, float, float],
    target_ned: tuple[float, float, float],
) -> tuple[float, float, float]:
    position = np.asarray(position_ned, dtype=float)
    target = np.asarray(target_ned, dtype=float)
    direction = target - position
    yaw = math.atan2(float(direction[1]), float(direction[0]))
    horizontal = math.hypot(float(direction[0]), float(direction[1]))
    pitch = -math.atan2(float(direction[2]), max(horizontal, 1e-6))
    roll = 0.0
    return pitch, roll, yaw


def _quaternion_components_from_euler(pitch: float, roll: float, yaw: float) -> dict[str, float]:
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    return {
        "w": cr * cp * cy + sr * sp * sy,
        "x": sr * cp * cy - cr * sp * sy,
        "y": cr * sp * cy + sr * cp * sy,
        "z": cr * cp * sy - sr * sp * cy,
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


def _resource_id_for_vehicle(config: BlocksSmokeConfig, vehicle_name: str) -> str:
    try:
        index = tuple(config.resource_vehicle_names).index(vehicle_name)
    except ValueError:
        return vehicle_name
    return f"INT-{index + 1:02d}"


def _detection_from_yolo_track(
    track: LocalVisualTrack,
    *,
    camera_id: str,
    frame_index: int,
    detection_index: int,
    timestamp: float,
    result_metadata: dict[str, Any],
) -> AirSimDetectionBox:
    bbox = tuple(float(value) for value in track.bbox)
    center = (float(track.center_px[0]), float(track.center_px[1]))
    local_track_id = str(track.local_track_id)
    return AirSimDetectionBox(
        detection_id=f"{camera_id}:{frame_index:04d}:yolo:{detection_index}",
        camera_id=camera_id,
        object_id=f"local_yolo_track:{local_track_id}",
        local_track_id=local_track_id,
        timestamp=float(timestamp),
        center_px=center,
        bbox_xyxy=bbox,
        confidence=float(track.quality),
        classification_hint=str(track.category),
        metadata={
            "source": "yolov8_mot",
            "detector_backend": result_metadata.get("detector_backend"),
            "tracker_backend": result_metadata.get("tracker_backend"),
            "requested_tracker_backend": result_metadata.get("requested_tracker_backend"),
            "detector_status": result_metadata.get("status"),
            "mot_history_length": int(track.mot_history_length),
        },
    )


def _decode_scene_image_bytes(data: bytes) -> tuple[Any, str]:
    try:
        import cv2  # type: ignore

        encoded = np.frombuffer(data, dtype=np.uint8)
        decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if decoded is not None:
            return decoded, "cv2_imdecode"
    except Exception:
        pass
    return data, "raw_bytes"


def _camera_dimensions_from_settings(
    config: BlocksSmokeConfig,
    vehicle_name: str,
    camera_name: str,
) -> tuple[int, int]:
    intrinsics = _camera_intrinsics_from_settings(config, vehicle_name, camera_name)
    return (intrinsics.width, intrinsics.height)


def _camera_intrinsics_from_settings(
    config: BlocksSmokeConfig,
    vehicle_name: str,
    camera_name: str,
) -> Any:
    capture = _scene_capture_settings(config, vehicle_name, camera_name)
    return intrinsics_from_capture_settings(capture)


def _scene_capture_settings(
    config: BlocksSmokeConfig,
    vehicle_name: str,
    camera_name: str,
) -> dict[str, Any]:
    settings = config._settings()
    vehicles = settings.get("Vehicles", {})
    vehicle = vehicles.get(vehicle_name, {}) if isinstance(vehicles, dict) else {}
    cameras = vehicle.get("Cameras", {}) if isinstance(vehicle, dict) else {}
    camera = cameras.get(camera_name, {}) if isinstance(cameras, dict) else {}
    capture_settings = camera.get("CaptureSettings")
    if not capture_settings:
        defaults = settings.get("CameraDefaults", {})
        capture_settings = defaults.get("CaptureSettings", []) if isinstance(defaults, dict) else []
    for item in capture_settings if isinstance(capture_settings, list) else []:
        if int(item.get("ImageType", 0)) == 0:
            return dict(item)
    return {"ImageType": 0, "Width": 640, "Height": 480, "FOV_Degrees": 90}


def _camera_position_from_settings(
    config: BlocksSmokeConfig,
    vehicle_name: str,
    camera_name: str,
) -> tuple[float, float, float]:
    start = _vehicle_start_offset(config, vehicle_name)
    camera = _camera_mount_settings(config, vehicle_name, camera_name)
    return (
        start[0] + float(camera.get("X", 0.0)),
        start[1] + float(camera.get("Y", 0.0)),
        start[2] + float(camera.get("Z", 0.0)),
    )


def _rotation_from_settings_or_identity(
    config: BlocksSmokeConfig,
    vehicle_name: str,
    camera_name: str,
) -> np.ndarray:
    vehicle = _vehicle_settings(config, vehicle_name)
    camera = _camera_mount_settings(config, vehicle_name, camera_name)
    pitch = math.radians(float(vehicle.get("Pitch", 0.0)) + float(camera.get("Pitch", 0.0)))
    roll = math.radians(float(vehicle.get("Roll", 0.0)) + float(camera.get("Roll", 0.0)))
    yaw = math.radians(float(vehicle.get("Yaw", 0.0)) + float(camera.get("Yaw", 0.0)))
    quat = _quaternion_components_from_euler(pitch, roll, yaw)
    orientation = SimpleNamespace(
        w_val=quat["w"],
        x_val=quat["x"],
        y_val=quat["y"],
        z_val=quat["z"],
    )
    return rotation_world_to_opencv_camera_from_quaternion(orientation)


def _vehicle_settings(config: BlocksSmokeConfig, vehicle_name: str) -> dict[str, Any]:
    vehicles = config._settings().get("Vehicles", {})
    vehicle = vehicles.get(vehicle_name, {}) if isinstance(vehicles, dict) else {}
    return dict(vehicle) if isinstance(vehicle, dict) else {}


def _camera_mount_settings(
    config: BlocksSmokeConfig,
    vehicle_name: str,
    camera_name: str,
) -> dict[str, Any]:
    vehicle = _vehicle_settings(config, vehicle_name)
    cameras = vehicle.get("Cameras", {}) if isinstance(vehicle, dict) else {}
    camera = cameras.get(camera_name, {}) if isinstance(cameras, dict) else {}
    if isinstance(camera, dict):
        return dict(camera)
    defaults = config._settings().get("CameraDefaults", {})
    return dict(defaults) if isinstance(defaults, dict) else {}


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
