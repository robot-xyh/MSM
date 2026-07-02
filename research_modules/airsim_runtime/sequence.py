"""Main-managed staged AirSim Blocks sequence runner."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from .blocks import BlocksProcessManager
from .models import BlocksEpisodeSpec, BlocksSequenceResult, BlocksSmokeConfig, BlocksSmokeResult
from .orchestrator import AirSimBlocksSmokeOrchestrator
from .real_runtime import RealAirSimRuntimeClient


DEFAULT_BLOCKS_EPISODES: tuple[BlocksEpisodeSpec, ...] = (
    BlocksEpisodeSpec("episode_001_d1_sensor", "D1 sensor capture", include_integrated_pipeline=False),
    BlocksEpisodeSpec("episode_002_d2_association", "D2 association replay"),
    BlocksEpisodeSpec("episode_003_d3_assignment", "D3 assignment replay"),
    BlocksEpisodeSpec("episode_004_d5_terminal", "D5 terminal association replay"),
    BlocksEpisodeSpec("episode_005_d4_degradation", "D4 degradation replay"),
    BlocksEpisodeSpec("episode_006_full_flow", "D1-D7 full integrated replay"),
)


class AirSimBlocksSequenceOrchestrator:
    """Launch Blocks once, reset between staged read-only episodes, and close once."""

    def __init__(
        self,
        runtime: RealAirSimRuntimeClient | None = None,
        process_manager: BlocksProcessManager | None = None,
    ) -> None:
        self.runtime = runtime
        self.process_manager = process_manager

    def run(
        self,
        base_config: BlocksSmokeConfig,
        *,
        sequence_id: str = "blocks_sequence_001",
        episode_specs: tuple[BlocksEpisodeSpec, ...] = DEFAULT_BLOCKS_EPISODES,
    ) -> BlocksSequenceResult:
        output_root = base_config.output_root
        sequence_dir = output_root / sequence_id
        sequence_dir.mkdir(parents=True, exist_ok=True)
        process_manager = self.process_manager or BlocksProcessManager(
            blocks_script=base_config.blocks_script,
            settings_path=base_config.settings_path,
            output_dir=sequence_dir,
            extra_args=base_config.blocks_args,
            prefer_nvidia_offload=base_config.prefer_nvidia_offload,
        )
        runtime = self.runtime or RealAirSimRuntimeClient(
            ip=base_config.api_server_host(),
            port=base_config.api_server_port(),
            timeout_value=base_config.client_timeout_s,
            client_kind=base_config.client_kind,
        )
        episode_results: list[BlocksSmokeResult] = []
        process_manager.start()
        try:
            smoke_orchestrator = AirSimBlocksSmokeOrchestrator(
                runtime=runtime,
                process_manager=process_manager,
            )
            for spec in episode_specs:
                execute_episode_intercept = (
                    base_config.execute_intercept and spec.episode_id == "episode_006_full_flow"
                )
                config = replace(
                    base_config,
                    episode_id=spec.episode_id,
                    scenario_name=spec.scenario_name,
                    duration_s=spec.duration_s,
                    dt_s=spec.dt_s,
                    output_root=sequence_dir,
                    include_integrated_pipeline=spec.include_integrated_pipeline,
                    execute_intercept=execute_episode_intercept,
                    launch_blocks=False,
                    metadata={**base_config.metadata, "sequence_id": sequence_id, "focus": spec.focus},
                )
                result = smoke_orchestrator.run(config)
                result.metadata["sequence_id"] = sequence_id
                result.metadata["focus"] = spec.focus
                episode_results.append(result)
        finally:
            process_manager.stop()
        sequence_result = BlocksSequenceResult(
            sequence_id=sequence_id,
            connected=all(result.connected for result in episode_results),
            episode_results=tuple(episode_results),
            output_paths={},
            metadata={
                "real_airsim_used": True,
                "control_api_used": any(
                    bool(result.metadata.get("control_api_used")) for result in episode_results
                ),
                "settings_path": str(base_config.settings_path.resolve()),
                "episode_count": len(episode_results),
                "episode_order": [spec.episode_id for spec in episode_specs],
                "blocks_launched_once": True,
            },
        )
        summary_path = _write_sequence_summary(sequence_dir / "blocks_sequence_summary.json", sequence_result)
        sequence_result.output_paths["blocks_sequence_summary"] = summary_path
        return sequence_result


def run_blocks_sequence(
    base_config: BlocksSmokeConfig | None = None,
    *,
    sequence_id: str = "blocks_sequence_001",
    episode_specs: tuple[BlocksEpisodeSpec, ...] = DEFAULT_BLOCKS_EPISODES,
) -> BlocksSequenceResult:
    return AirSimBlocksSequenceOrchestrator().run(
        base_config or BlocksSmokeConfig(),
        sequence_id=sequence_id,
        episode_specs=episode_specs,
    )


def _write_sequence_summary(path: Path, result: BlocksSequenceResult) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "sequence_id": result.sequence_id,
        "connected": result.connected,
        "metadata": result.metadata,
        "output_paths": {key: str(value) for key, value in result.output_paths.items()},
        "episodes": [
            {
                "episode_id": episode.episode_id,
                "frame_count": episode.frame_count,
                "vehicle_names": list(episode.vehicle_names),
                "image_ok_count": episode.image_ok_count,
                "lidar_ok_count": episode.lidar_ok_count,
                "focus": episode.metadata.get("focus"),
                "integrated_metrics": None
                if episode.integrated_result is None
                else episode.integrated_result.metrics,
                "output_paths": {key: str(value) for key, value in episode.output_paths.items()},
            }
            for episode in result.episode_results
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path
