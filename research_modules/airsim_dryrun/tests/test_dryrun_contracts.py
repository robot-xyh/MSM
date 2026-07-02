from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

from airsim_dryrun import (
    AirSimEpisodeConfig,
    FakeAirSimRuntimeClient,
    observations_from_airsim_frame,
    run_airsim_dry_run,
)


def test_fake_runtime_produces_nominal_5v5_frames_without_airsim_import() -> None:
    config = AirSimEpisodeConfig(duration_s=1.0, dt_s=0.5)
    runtime = FakeAirSimRuntimeClient()

    runtime.reset(config)
    frames = list(runtime.iter_frames(config))

    assert "airsim" not in sys.modules
    assert runtime.reset_count == 1
    assert len(frames) == 3
    assert len(frames[0].truth_objects) == 5
    assert len(frames[0].resources) == 5
    assert frames[0].metadata["real_airsim_used"] is False


def test_frame_to_d1_observations_preserves_latency_and_covariance() -> None:
    config = AirSimEpisodeConfig(duration_s=0.5, dt_s=0.5)
    frame = FakeAirSimRuntimeClient().frame_at(config, 0.0)

    observations = observations_from_airsim_frame(frame, arrival_timestamp=0.6)

    assert observations
    assert {obs.modality for obs in observations} >= {"radar", "acoustic", "lidar"}
    for observation in observations:
        assert observation.measurement_timestamp == 0.0
        assert observation.arrival_timestamp == 0.6
        assert observation.covariance is not None
        assert np.isfinite(observation.covariance).all()
        assert observation.metadata["real_airsim_used"] is False
        assert observation.metadata["airsim_episode_id"] == config.episode_id


def test_dry_run_orchestrator_executes_full_module_contract(tmp_path: Path) -> None:
    config = AirSimEpisodeConfig(
        scenario_name="nominal_5v5",
        episode_id="pytest_dryrun",
        duration_s=3.0,
        dt_s=0.5,
        radar_latency_s=0.5,
    )

    result = run_airsim_dry_run(config, output_dir=tmp_path)

    assert result.frame_count == 7
    assert result.module_status == {
        "D1": "passed",
        "D2": "passed",
        "D3": "passed",
        "D5": "passed",
        "D4": "passed",
        "D7": "passed",
        "D6": "passed",
    }
    assert result.metadata["real_airsim_used"] is False
    assert result.metrics["detection_probability"] > 0.0
    assert result.metrics["duplicate_assignment_count"] == 0
    assert result.output_paths["episode_log"].exists()
    assert result.output_paths["airsim_dry_run_summary"].exists()


def test_dry_run_can_disable_lidar_and_preserve_other_modalities() -> None:
    config = AirSimEpisodeConfig(include_lidar=False, duration_s=0.5, dt_s=0.5)
    frame = FakeAirSimRuntimeClient().frame_at(config, 0.0)

    observations = observations_from_airsim_frame(
        frame,
        include_lidar=False,
        include_acoustic=config.include_acoustic,
        include_eo=config.include_eo,
    )

    modalities = {obs.modality for obs in observations}
    assert "lidar" not in modalities
    assert {"radar", "acoustic"} <= modalities
