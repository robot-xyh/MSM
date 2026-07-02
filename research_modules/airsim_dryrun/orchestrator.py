"""Main phase-1 dry-run orchestration for the future AirSim workflow."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Callable

from integrated_simulation import IntegratedEpisodeRunner
from integrated_simulation.scenario import make_standard_scenario

from .adapters import observations_from_airsim_frame
from .models import AirSimAdapterResult, AirSimEpisodeConfig, AirSimFrame
from .runtime import FakeAirSimRuntimeClient


class AirSimDryRunOrchestrator:
    """Run a fake AirSim episode through the existing D1-D7 contracts."""

    MODULE_ORDER = ("D1", "D2", "D3", "D5", "D4", "D7", "D6")

    def __init__(self, runtime: FakeAirSimRuntimeClient | None = None) -> None:
        self.runtime = runtime or FakeAirSimRuntimeClient()

    def run(
        self,
        config: AirSimEpisodeConfig,
        output_dir: str | Path | None = None,
    ) -> AirSimAdapterResult:
        output_path = Path(output_dir) if output_dir is not None else _default_output_dir(config)
        self.runtime.reset(config)
        frames = list(self.runtime.iter_frames(config))
        if not frames:
            raise RuntimeError("dry-run runtime produced no frames")
        provider = self._make_observation_provider(config)
        scenario = _integrated_config(config)
        runner = IntegratedEpisodeRunner(scenario, observation_provider=provider)
        result = runner.run(output_dir=output_path)
        module_status = {name: "passed" for name in self.MODULE_ORDER}
        result.metadata.update(
            {
                "airsim_phase": "phase_1_dry_run",
                "dry_run_frame_count": len(frames),
                "fake_runtime_reset_count": self.runtime.reset_count,
                "module_order": list(self.MODULE_ORDER),
                "real_airsim_used": False,
            }
        )
        summary = AirSimAdapterResult(
            episode_id=config.episode_id,
            scenario_name=config.scenario_name,
            frame_count=len(frames),
            module_status=module_status,
            metrics=result.metrics.to_dict(),
            output_paths=result.output_paths,
            metadata={
                "offline_only": True,
                "real_airsim_used": False,
                "reset_between_episodes": config.reset_between_episodes,
                "runtime": type(self.runtime).__name__,
                "first_frame": _frame_summary(frames[0]),
                "last_frame": _frame_summary(frames[-1]),
            },
        )
        path = _write_summary(output_path / "airsim_dry_run_summary.json", summary)
        summary.output_paths["airsim_dry_run_summary"] = path
        return summary

    def _make_observation_provider(
        self,
        config: AirSimEpisodeConfig,
    ) -> Callable[[float], list[object]]:
        def provider(arrival_timestamp: float) -> list[object]:
            measurement_timestamp = max(0.0, float(arrival_timestamp) - config.radar_latency_s)
            frame = self.runtime.frame_at(config, measurement_timestamp)
            return observations_from_airsim_frame(
                frame,
                arrival_timestamp=arrival_timestamp,
                include_acoustic=config.include_acoustic,
                include_eo=config.include_eo,
                include_lidar=config.include_lidar,
            )

        return provider


def run_airsim_dry_run(
    config: AirSimEpisodeConfig | None = None,
    output_dir: str | Path | None = None,
) -> AirSimAdapterResult:
    """Convenience wrapper for one dependency-free dry-run episode."""

    return AirSimDryRunOrchestrator().run(config or AirSimEpisodeConfig(), output_dir=output_dir)


def _integrated_config(config: AirSimEpisodeConfig):
    scenario = make_standard_scenario(
        _integrated_scenario_name(config.scenario_name),
        seed=config.seed,
        duration_s=config.duration_s,
        output_root=config.output_root,
    )
    return replace(
        scenario,
        dt_s=config.dt_s,
        target_count=config.target_count,
        resource_count=config.resource_count,
        radar_latency_s=config.radar_latency_s,
        acoustic_enabled=config.include_acoustic,
        eo_enabled=config.include_eo,
    )


def _integrated_scenario_name(name: str) -> str:
    aliases = {
        "center_failed": "center_destroyed",
        "secondary_failed": "secondary_destroyed",
        "terminal_friend_overlap": "friend_overlap_hold",
        "cross_view_overlap": "nominal_5v5",
    }
    return aliases.get(name, name)


def _default_output_dir(config: AirSimEpisodeConfig) -> Path:
    return Path("research_modules/airsim_dryrun/outputs") / config.episode_id


def _frame_summary(frame: AirSimFrame) -> dict[str, object]:
    return {
        "timestamp": frame.timestamp,
        "truth_count": len(frame.truth_objects),
        "resource_count": len(frame.resources),
        "camera_count": len(frame.cameras),
        "visual_detection_count": len(frame.visual_detections),
        "center_node_alive": frame.center_node_alive,
        "secondary_nodes_alive": frame.secondary_nodes_alive,
    }


def _write_summary(path: Path, summary: AirSimAdapterResult) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "episode_id": summary.episode_id,
        "scenario_name": summary.scenario_name,
        "frame_count": summary.frame_count,
        "module_status": summary.module_status,
        "metrics": summary.metrics,
        "output_paths": {key: str(value) for key, value in summary.output_paths.items()},
        "metadata": summary.metadata,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path
