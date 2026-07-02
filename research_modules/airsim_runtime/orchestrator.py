"""Main orchestrator for real Blocks read-only smoke runs."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
from airsim_dryrun.models import AirSimAdapterResult, AirSimFrame
from d5_terminal_association import CameraModel
from integrated_simulation import IntegratedEpisodeRunner
from integrated_simulation.scenario import make_standard_scenario

from .adapters import (
    local_visual_tracks_from_blocks_frame,
    nearest_frame,
    observations_from_blocks_frame,
    resources_from_blocks_frame,
    truth_states_from_blocks_frame,
    truth_summary_from_blocks_frames,
)
from .blocks import BlocksProcessManager
from .models import BlocksSmokeConfig, BlocksSmokeResult
from .real_runtime import RealAirSimRuntimeClient


class AirSimBlocksSmokeOrchestrator:
    """Start Blocks, sample read-only frames, and replay them through D1-D7."""

    MODULE_ORDER = ("Blocks", "D1", "D2", "D3", "D5", "D4", "D7", "D6")

    def __init__(
        self,
        runtime: RealAirSimRuntimeClient | None = None,
        process_manager: BlocksProcessManager | None = None,
    ) -> None:
        self.runtime = runtime
        self.process_manager = process_manager

    def run(self, config: BlocksSmokeConfig) -> BlocksSmokeResult:
        output_dir = config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        process_manager = self.process_manager
        if config.launch_blocks and process_manager is None:
            process_manager = BlocksProcessManager(
                blocks_script=config.blocks_script,
                settings_path=config.settings_path,
                output_dir=output_dir,
                extra_args=config.blocks_args,
                prefer_nvidia_offload=config.prefer_nvidia_offload,
            )
        if process_manager is not None and config.launch_blocks:
            process_manager.start()
        runtime = self.runtime or RealAirSimRuntimeClient(
            ip=config.api_server_host(),
            port=config.api_server_port(),
            timeout_value=config.client_timeout_s,
            client_kind=config.client_kind,
        )
        frames: list[AirSimFrame] = []
        episode_setup = False
        try:
            self._wait_for_connection(runtime, config.connection_timeout_s, process_manager)
            runtime.reset()
            setup_episode = getattr(runtime, "setup_episode", None)
            if callable(setup_episode):
                setup_episode(config)
                episode_setup = True
            frames = self._capture_frames(runtime, config)
            raw_log = _write_frames_jsonl(frames, output_dir / "blocks_frames.jsonl")
            integrated = (
                self._run_integrated_replay(config, frames, output_dir)
                if config.include_integrated_pipeline
                else None
            )
            result = BlocksSmokeResult(
                episode_id=config.episode_id,
                frame_count=len(frames),
                connected=True,
                vehicle_names=_vehicle_names(frames),
                image_ok_count=sum(1 for frame in frames if frame.metadata.get("image", {}).get("ok")),
                lidar_ok_count=sum(1 for frame in frames if frame.metadata.get("lidar", {}).get("ok")),
                output_paths={"blocks_frames_jsonl": raw_log},
                integrated_result=integrated,
                metadata={
                    "real_airsim_used": True,
                    "runtime": "Blocks",
                    "settings_path": str(config.settings_path.resolve()),
                    "module_order": list(self.MODULE_ORDER),
                    "control_api_used": False,
                    "actor_target_count": len(config.target_actor_specs),
                    "detection_count": sum(len(frame.visual_detections) for frame in frames),
                    "first_frame": _frame_summary(frames[0]) if frames else {},
                    "last_frame": _frame_summary(frames[-1]) if frames else {},
                },
            )
            summary_path = _write_summary(output_dir / "airsim_blocks_summary.json", result)
            result.output_paths["airsim_blocks_summary"] = summary_path
            return result
        finally:
            teardown_episode = getattr(runtime, "teardown_episode", None)
            if episode_setup and callable(teardown_episode):
                teardown_episode(config)
            if process_manager is not None and config.launch_blocks:
                process_manager.stop()

    def _wait_for_connection(
        self,
        runtime: RealAirSimRuntimeClient,
        timeout_s: float,
        process_manager: BlocksProcessManager | None,
    ) -> None:
        deadline = time.monotonic() + timeout_s
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if process_manager is not None and process_manager.returncode() is not None:
                diagnostics_path = process_manager.write_diagnostics()
                diagnostics = process_manager.format_diagnostics()
                raise RuntimeError(
                    "Blocks exited before AirSim RPC became ready "
                    f"(returncode={process_manager.returncode()}). "
                    f"Diagnostics: {diagnostics_path}\n{diagnostics}"
                )
            try:
                if runtime.ping():
                    return
            except Exception as exc:
                last_error = exc
                reconnect = getattr(runtime, "reconnect", None)
                if callable(reconnect):
                    reconnect()
            time.sleep(1.0)
        message = "AirSim RPC did not become ready before timeout"
        if last_error is not None:
            message = f"{message}: {last_error}"
        if process_manager is not None:
            diagnostics_path = process_manager.write_diagnostics()
            message = (
                f"{message}\nDiagnostics: {diagnostics_path}\n"
                f"{process_manager.format_diagnostics()}"
            )
        raise TimeoutError(message)

    def _capture_frames(
        self,
        runtime: RealAirSimRuntimeClient,
        config: BlocksSmokeConfig,
    ) -> list[AirSimFrame]:
        frames: list[AirSimFrame] = []
        for index, timestamp in enumerate(config.timestamps()):
            frames.append(runtime.sample_frame(config, index, timestamp, config.output_dir / "images"))
            if index < len(config.timestamps()) - 1:
                time.sleep(min(max(config.dt_s, 0.05), 1.0))
        return frames

    def _run_integrated_replay(
        self,
        config: BlocksSmokeConfig,
        frames: list[AirSimFrame],
        output_dir: Path,
    ) -> AirSimAdapterResult:
        scenario = make_standard_scenario(
            "nominal_5v5",
            seed=config.seed,
            duration_s=config.duration_s,
            output_root=output_dir,
        )
        scenario = replace(
            scenario,
            name=config.scenario_name,
            dt_s=config.dt_s,
            target_count=max(1, config.target_count()),
            resource_count=max(1, len(config.resource_vehicle_names)),
            radar_latency_s=config.radar_latency_s,
        )

        def observation_provider(arrival_timestamp: float) -> list[object]:
            measurement_time = max(0.0, arrival_timestamp - config.radar_latency_s)
            frame = nearest_frame(frames, measurement_time)
            return observations_from_blocks_frame(frame, arrival_timestamp=arrival_timestamp)

        def truth_provider(timestamp: float):
            return truth_states_from_blocks_frame(nearest_frame(frames, timestamp))

        def resources_provider(timestamp: float):
            return resources_from_blocks_frame(nearest_frame(frames, timestamp))

        def terminal_visual_provider(**kwargs):
            frame = nearest_frame(frames, float(kwargs["timestamp"]))
            return local_visual_tracks_from_blocks_frame(
                frame,
                list(kwargs.get("d2_tracks", [])),
                terminal_tracks=list(kwargs.get("terminal_tracks", [])),
                terminal_associator=kwargs.get("terminal_associator"),
                terminal_camera=kwargs.get("terminal_camera"),
                timestamp=float(kwargs["timestamp"]),
            )

        runner = IntegratedEpisodeRunner(
            scenario,
            observation_provider=observation_provider,
            truth_provider=truth_provider,
            resources_provider=resources_provider,
            truth_summary_provider=lambda: truth_summary_from_blocks_frames(frames),
            terminal_visual_provider=terminal_visual_provider,
            terminal_camera=_blocks_terminal_camera(),
        )
        episode = runner.run(output_dir=output_dir / "integrated_replay")
        output_paths = dict(episode.output_paths)
        return AirSimAdapterResult(
            episode_id=config.episode_id,
            scenario_name=config.scenario_name,
            frame_count=len(frames),
            module_status={name: "passed" for name in self.MODULE_ORDER if name != "Blocks"},
            metrics=episode.metrics.to_dict(),
            output_paths=output_paths,
            metadata={
                "real_airsim_used": True,
                "runtime": "BlocksReplay",
                "control_api_used": False,
                "airsim_detection_count": sum(len(frame.visual_detections) for frame in frames),
                "record_counts": episode.metadata.get("record_counts", {}),
            },
        )


def run_blocks_smoke(config: BlocksSmokeConfig | None = None) -> BlocksSmokeResult:
    return AirSimBlocksSmokeOrchestrator().run(config or BlocksSmokeConfig())


def _write_frames_jsonl(frames: list[AirSimFrame], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for frame in frames:
            stream.write(json.dumps(_frame_to_dict(frame), ensure_ascii=False, sort_keys=True) + "\n")
    return path


def _write_summary(path: Path, result: BlocksSmokeResult) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "episode_id": result.episode_id,
        "frame_count": result.frame_count,
        "connected": result.connected,
        "vehicle_names": list(result.vehicle_names),
        "image_ok_count": result.image_ok_count,
        "lidar_ok_count": result.lidar_ok_count,
        "output_paths": {key: str(value) for key, value in result.output_paths.items()},
        "integrated_result": None
        if result.integrated_result is None
        else {
            "metrics": result.integrated_result.metrics,
            "module_status": result.integrated_result.module_status,
            "output_paths": {
                key: str(value) for key, value in result.integrated_result.output_paths.items()
            },
        },
        "metadata": result.metadata,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _frame_to_dict(frame: AirSimFrame) -> dict[str, Any]:
    payload = asdict(frame)
    return _jsonable(payload)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _vehicle_names(frames: list[AirSimFrame]) -> tuple[str, ...]:
    names: set[str] = set()
    for frame in frames:
        names.update(str(name) for name in frame.metadata.get("vehicle_names", []))
    return tuple(sorted(names))


def _blocks_terminal_camera() -> CameraModel:
    """Simple front-facing NED camera used until real AirSim extrinsics are calibrated."""

    return CameraModel(
        K=np.array([[320.0, 0.0, 640.0], [0.0, 320.0, 360.0], [0.0, 0.0, 1.0]]),
        R=np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]]),
        t=np.zeros(3),
        image_size=(1280, 720),
        measurement_cov=np.diag([4.0, 4.0]),
    )


def _frame_summary(frame: AirSimFrame) -> dict[str, Any]:
    return {
        "timestamp": frame.timestamp,
        "truth_count": len(frame.truth_objects),
        "resource_count": len(frame.resources),
        "image": frame.metadata.get("image", {}),
        "lidar": frame.metadata.get("lidar", {}),
        "detection_count": len(frame.visual_detections),
        "actor_targets": frame.metadata.get("actor_targets", []),
        "scene_object_count": frame.metadata.get("scene_object_count", 0),
    }
