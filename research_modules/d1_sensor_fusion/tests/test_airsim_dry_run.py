from __future__ import annotations

import numpy as np

from d1_sensor_fusion import FusionAdapter
from d1_sensor_fusion.airsim_dry_run import (
    make_minimal_airsim_dry_run_fixture,
    observations_from_airsim_dry_run_fixture,
)


def test_airsim_dry_run_fixture_converts_all_enabled_modalities() -> None:
    fixture = make_minimal_airsim_dry_run_fixture(include_lidar=True)
    observations = observations_from_airsim_dry_run_fixture(fixture)

    modalities = {obs.modality for obs in observations}
    assert modalities == {"radar", "acoustic", "eo", "lidar"}
    assert observations == sorted(observations, key=lambda obs: (obs.arrival_timestamp, obs.observation_id))
    for observation in observations:
        assert observation.arrival_timestamp >= observation.measurement_timestamp
        assert observation.covariance is not None
        assert observation.metadata["dry_run"] is True
        assert observation.metadata["fixture_id"] == "minimal_airsim_dry_run"
        if observation.modality == "eo":
            assert observation.frame_id == "pixel"
            assert observation.covariance.shape == (2, 2)
        elif observation.modality == "lidar":
            assert observation.frame_id == "ned"
            assert observation.measurement.shape == (3,)
            assert observation.covariance.shape == (3, 3)
        elif observation.modality == "acoustic":
            assert observation.frame_id == "ned"
            assert observation.covariance.shape == (1, 1)
        else:
            assert observation.frame_id == "ned"
            assert observation.covariance.shape == (4, 4)


def test_airsim_dry_run_lidar_is_optional() -> None:
    fixture = make_minimal_airsim_dry_run_fixture(include_lidar=False)
    observations = observations_from_airsim_dry_run_fixture(fixture)

    assert "lidar" not in {obs.modality for obs in observations}
    assert {"radar", "acoustic", "eo"} <= {obs.modality for obs in observations}


def test_airsim_dry_run_observations_feed_fusion_adapter() -> None:
    fixture = make_minimal_airsim_dry_run_fixture(include_lidar=True)
    observations = observations_from_airsim_dry_run_fixture(fixture)
    adapter = FusionAdapter(
        process_noise=8.0,
        association_gate=45.0,
        latency_compensation=True,
        use_truth_hints_for_association=True,
    )

    tracks = adapter.ingest_many(observations)

    assert len(tracks) == 1
    track = tracks[0]
    assert track.metadata["frame_id"] == "ned"
    assert track.covariance.shape == (6, 6)
    assert np.isfinite(track.covariance).all()
    assert track.source_support["radar"] >= 1
    assert track.source_support["lidar"] >= 1
