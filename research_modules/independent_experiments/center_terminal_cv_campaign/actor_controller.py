"""Main-owned actor lifecycle and motion proxy for real AirSim episodes."""

from __future__ import annotations

from dataclasses import asdict
import math
import time
from typing import Any, Sequence

from center_terminal_cv_campaign.common.scenario import TargetTruth


QUADROTOR1_THREE_METER_SCALE = 2.277743665790053


class CampaignActorClientProxy:
    """Delegate AirSim calls while main retains target lifecycle and motion."""

    def __init__(
        self,
        client: Any,
        airsim_module: Any,
        targets: Sequence[TargetTruth],
        *,
        asset_name: str = "Quadrotor1",
        scale_multiplier: float = QUADROTOR1_THREE_METER_SCALE,
    ) -> None:
        self._client = client
        self._airsim = airsim_module
        self.targets = tuple(targets)
        self.asset_name = str(asset_name)
        self.scale_multiplier = float(scale_multiplier)
        self.actual_name_by_requested: dict[str, str] = {}
        self.requested_name_by_actual: dict[str, str] = {}
        self.logical_timestamp = 0.0
        self.motion_rows: list[dict[str, Any]] = []
        self._scene_initialized = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def setup_targets(self) -> None:
        self.teardown_targets()
        scale = self._airsim.Vector3r(
            self.scale_multiplier,
            self.scale_multiplier,
            self.scale_multiplier,
        )
        for target in self.targets:
            pose = self._target_pose(target, 0.0)
            spawned = self._client.simSpawnObject(
                target.actor_name,
                self.asset_name,
                pose,
                scale,
                False,
            )
            if not spawned:
                raise RuntimeError(f"AirSim failed to spawn actor {target.actor_name}")
            actual = str(spawned)
            self.actual_name_by_requested[target.actor_name] = actual
            self.requested_name_by_actual[actual] = target.actor_name
        self._wait_for_scene_registration(timeout_s=2.0)
        self.logical_timestamp = 0.0
        self._scene_initialized = True
        self._record_motion(0.0)

    def teardown_targets(self) -> None:
        names = set(self.actual_name_by_requested.values()) | {
            target.actor_name for target in self.targets
        }
        for name in sorted(names):
            try:
                self._client.simDestroyObject(name)
            except Exception:
                pass
        self.actual_name_by_requested.clear()
        self.requested_name_by_actual.clear()
        self._scene_initialized = False

    def set_logical_time(self, timestamp: float) -> None:
        timestamp = float(timestamp)
        if self._scene_initialized and math.isclose(timestamp, self.logical_timestamp):
            return
        self.logical_timestamp = timestamp
        for target in self.targets:
            actual = self.actual_name_by_requested.get(target.actor_name, target.actor_name)
            pose = self._target_pose(target, self.logical_timestamp)
            if not self._set_object_pose_with_retry(actual, pose, timeout_s=0.5):
                raise RuntimeError(f"AirSim failed to move actor {actual}")
        self._record_motion(self.logical_timestamp)

    def _record_motion(self, timestamp: float) -> None:
        for target in self.targets:
            actual = self.actual_name_by_requested.get(target.actor_name, target.actor_name)
            self.motion_rows.append(
                {
                    "measurement_timestamp": float(timestamp),
                    "actor_name": target.actor_name,
                    "actual_actor_name": actual,
                    "truth_target_id": target.truth_target_id,
                    "position_ned_m": list(target.position_at(timestamp)),
                    "velocity_ned_mps": list(target.velocity_ned_mps),
                    "offline_truth_only": True,
                }
            )

    def _set_object_pose_with_retry(
        self, actor_name: str, pose: Any, *, timeout_s: float
    ) -> bool:
        deadline = time.monotonic() + float(timeout_s)
        while True:
            try:
                if bool(self._client.simSetObjectPose(actor_name, pose, True)):
                    return True
            except Exception:
                pass
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    def _wait_for_scene_registration(self, *, timeout_s: float) -> None:
        list_objects = getattr(self._client, "simListSceneObjects", None)
        if not callable(list_objects):
            return
        expected = set(self.actual_name_by_requested.values())
        deadline = time.monotonic() + float(timeout_s)
        while True:
            try:
                registered = {str(name) for name in list_objects(".*")}
                if expected <= registered:
                    return
            except Exception:
                return
            if time.monotonic() >= deadline:
                missing = sorted(expected - registered)
                raise RuntimeError(
                    f"spawned actors not registered in AirSim scene: {missing[:5]}"
                )
            time.sleep(0.05)

    # Experiment adapters call different optional frame hooks. All hooks are
    # aliases for the same main-owned target update.
    def set_search_frame(self, frame_index: int, timestamp: float) -> None:
        del frame_index
        self.set_logical_time(timestamp)

    def set_handover_frame(self, frame_index: int, timestamp: float) -> None:
        del frame_index
        self.set_logical_time(timestamp)

    def set_crossview_frame(self, frame_index: int, timestamp: float) -> None:
        del frame_index
        self.set_logical_time(timestamp)

    def set_experiment_frame(self, frame_index: int, timestamp: float) -> None:
        del frame_index
        self.set_logical_time(timestamp)

    def simGetDetections(self, *args: Any, **kwargs: Any) -> Any:
        rows = self._client.simGetDetections(*args, **kwargs)
        for row in rows or ():
            actual = str(getattr(row, "name", ""))
            requested = self.requested_name_by_actual.get(actual)
            if requested is not None:
                try:
                    row.name = requested
                except Exception:
                    pass
        return rows

    def actor_audit(self) -> dict[str, Any]:
        return {
            "asset_name": self.asset_name,
            "scale_multiplier": self.scale_multiplier,
            "requested_longest_dimension_m": 3.0,
            "target_count": len(self.targets),
            "spawned_names": dict(self.actual_name_by_requested),
            "targets": [asdict(target) for target in self.targets],
        }

    def _target_pose(self, target: TargetTruth, timestamp: float) -> Any:
        position = target.position_at(timestamp)
        yaw = math.atan2(target.velocity_ned_mps[1], target.velocity_ned_mps[0])
        return self._airsim.Pose(
            self._airsim.Vector3r(*position),
            self._airsim.to_quaternion(0.0, 0.0, yaw),
        )
