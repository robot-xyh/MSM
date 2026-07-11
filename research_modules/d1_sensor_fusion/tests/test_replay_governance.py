from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from d1_sensor_fusion import (
    FusionAdapter,
    FusionQualityRegionSummary,
    LatencyAuditSummary,
    ReplayProvenance,
    SensorObservation,
    SensorTimingExpectation,
    read_sensor_observations_csv,
    read_sensor_observations_jsonl,
    sensor_observation_to_replay_record,
    summarize_region_quality_windows,
    write_sensor_observations_csv,
    write_sensor_observations_jsonl,
)
from d1_sensor_fusion.observations import radar_covariance_from_range, radar_h


FIXTURES = Path(__file__).parent / "fixtures"


def test_real_shaped_blocks_jsonl_fixture_replays_without_online_truth_hints() -> None:
    observations = read_sensor_observations_jsonl(FIXTURES / "blocks_cv_replay_v1.jsonl")

    assert len(observations) == 5
    assert all("truth_id" not in observation.metadata for observation in observations)
    assert {observation.frame_id for observation in observations} == {"ned", "pixel"}
    assert all(observation.covariance is not None for observation in observations)
    assert all(
        observation.metadata["d1_replay_provenance"]["config_digest"]
        == "sha256:fixture-config-001"
        for observation in observations
    )
    assert {observation.metadata["coverage_cell"] for observation in observations} == {
        "cell-east",
        "cell-west",
    }

    adapter = FusionAdapter(
        association_gate=40.0,
        use_truth_hints_for_association=False,
        sensor_timing_expectations={
            "BLOCKS-RADAR-01": SensorTimingExpectation(
                expected_latency_s=0.2,
                latency_tolerance_s=0.03,
                oosm_expected=True,
            )
        },
    )
    tracks = adapter.ingest_many(observations)

    assert len(tracks) == 2
    assert all(track.state.shape == (6,) for track in tracks)
    assert all(track.covariance.shape == (6, 6) for track in tracks)
    assert all(np.isfinite(track.covariance).all() for track in tracks)
    assert all("truth_id" not in track.metadata for track in tracks)
    health = {
        summary.sensor_id: summary.to_dict()
        for summary in adapter.sensor_health_summaries()
    }["BLOCKS-RADAR-01"]
    assert health["expected_latency_s"] == pytest.approx(0.2)
    assert health["latency_budget_exceedance_count"] == 0


def test_real_shaped_blocks_csv_fixture_preserves_schema_provenance_and_covariance() -> None:
    observations = read_sensor_observations_csv(FIXTURES / "blocks_cv_replay_v1.csv")

    assert len(observations) == 3
    for observation in observations:
        assert observation.measurement_timestamp < observation.arrival_timestamp
        assert observation.covariance is not None
        assert observation.metadata["coverage_cell"] == "cell-west"
        provenance = observation.metadata["d1_replay_provenance"]
        assert provenance["scenario_id"] == "blocks_cv_csv_fixture"
        assert provenance["config_id"] == "csv_fixture_config"
        assert "truth_id" not in observation.metadata
    eo = next(observation for observation in observations if observation.modality == "eo")
    assert eo.frame_id == "pixel"
    assert eo.metadata["camera_model"]["width"] == 1920
    assert eo.metadata["bbox_xyxy"] == [493.0, 281.0, 518.0, 304.0]


def test_governed_jsonl_and_csv_writers_emit_schema_and_strip_online_truth(tmp_path) -> None:
    observation = _radar_observation(
        observation_id="writer_radar_001",
        measurement_timestamp=2.0,
        arrival_timestamp=2.2,
    )
    observation.metadata.update(
        {
            "coverage_cell": "cell-writer",
            "truth_id": "offline_target_001",
            "actor_name": "TargetActor_1",
            "detection_metadata": {
                "actor_name": "NestedTargetActor_1",
                "detector": "simGetDetections",
            },
        }
    )
    provenance = ReplayProvenance(
        scenario_id="blocks_cv_writer_roundtrip",
        scenario_version="1.0",
        config_id="settings_simpleflight_v3",
        config_digest="sha256:writer-config-001",
        run_id="seed_021",
        seed=21,
    )

    record = sensor_observation_to_replay_record(observation, provenance)
    assert record["schema_version"] == "d1.sensor_observation.v1"
    assert record["provenance"]["schema_version"] == "d1.replay_provenance.v1"
    assert "truth_id" not in record["metadata"]
    assert "actor_name" not in record["metadata"]
    assert "actor_name" not in record["metadata"]["detection_metadata"]
    assert "offline_truth" not in record

    offline_record = sensor_observation_to_replay_record(
        observation,
        provenance,
        include_offline_truth=True,
    )
    assert offline_record["offline_truth"]["truth_id"] == "offline_target_001"
    assert "truth_id" not in offline_record["metadata"]

    jsonl_path = write_sensor_observations_jsonl(
        tmp_path / "observations.jsonl",
        [observation],
        provenance,
    )
    csv_path = write_sensor_observations_csv(
        tmp_path / "observations.csv",
        [observation],
        provenance,
    )

    raw_jsonl = json.loads(jsonl_path.read_text(encoding="utf-8"))
    assert raw_jsonl["schema_version"] == "d1.sensor_observation.v1"
    for loaded in (
        read_sensor_observations_jsonl(jsonl_path)[0],
        read_sensor_observations_csv(csv_path)[0],
    ):
        assert loaded.metadata["coverage_cell"] == "cell-writer"
        assert loaded.metadata["d1_replay_provenance"]["seed"] == 21
        assert loaded.measurement_timestamp == 2.0
        assert loaded.arrival_timestamp == 2.2
        assert loaded.covariance is not None
        assert "truth_id" not in loaded.metadata


def test_replay_writer_rejects_missing_or_unsupported_provenance() -> None:
    observation = _radar_observation(
        observation_id="writer_invalid_provenance",
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
    )

    with pytest.raises(ValueError, match="missing required field"):
        sensor_observation_to_replay_record(
            observation,
            {
                "scenario_id": "scenario",
                "scenario_version": "1",
                "config_id": "",
                "config_digest": "digest",
            },
        )
    with pytest.raises(ValueError, match="unsupported D1 replay provenance"):
        sensor_observation_to_replay_record(
            observation,
            {
                "schema_version": "d1.replay_provenance.v99",
                "scenario_id": "scenario",
                "scenario_version": "1",
                "config_id": "config",
                "config_digest": "digest",
            },
        )


def test_expected_latency_and_expected_oosm_do_not_create_false_sensor_faults() -> None:
    assert SensorTimingExpectation("0.2", "0.02", "false").oosm_expected is False
    adapter = FusionAdapter(
        sensor_timing_expectations={
            "radar-timing": {
                "expected_latency_s": 0.2,
                "latency_tolerance_s": 0.02,
                "oosm_expected": True,
            }
        }
    )
    adapter.process(
        _radar_observation(
            observation_id="timing_000",
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
            sensor_id="radar-timing",
        )
    )
    adapter.process(
        _radar_observation(
            observation_id="timing_001",
            measurement_timestamp=0.1,
            arrival_timestamp=0.3,
            sensor_id="radar-timing",
        )
    )

    health = adapter.sensor_health_summaries()[0].to_dict()
    assert health["status"] == "nominal"
    assert health["oosm_expected"] is True
    assert health["oosm_count"] == 1
    assert health["unexpected_oosm_count"] == 0
    assert health["latency_budget_exceedance_count"] == 0
    assert health["mean_latency_s"] == pytest.approx(0.2)

    adapter.process(
        _radar_observation(
            observation_id="timing_002_late",
            measurement_timestamp=0.2,
            arrival_timestamp=0.7,
            sensor_id="radar-timing",
        )
    )
    degraded = adapter.sensor_health_summaries()[0].to_dict()
    assert degraded["status"] == "degraded"
    assert degraded["latency_budget_exceedance_count"] == 1
    assert degraded["latency_budget_exceedance_rate"] == pytest.approx(1.0 / 3.0)
    assert degraded["max_latency_s"] == pytest.approx(0.5)
    assert "latency_budget_exceeded" in degraded["fault_reasons"]


def test_coverage_cell_quality_uses_fixed_time_windows_and_windowed_latency() -> None:
    snapshots = [
        [_region(0.2, mean_a95=4.0, growth=1.0)],
        [_region(0.8, mean_a95=5.0, growth=2.0)],
        [_region(1.2, mean_a95=7.0, growth=3.0)],
        [_region(1.8, mean_a95=10.0, growth=4.0)],
    ]
    audits = [
        _audit(published_at=0.2, observation_count=2, oosm_count=0),
        _audit(published_at=0.8, observation_count=4, oosm_count=1),
        _audit(published_at=1.2, observation_count=6, oosm_count=1),
        _audit(published_at=1.8, observation_count=8, oosm_count=2),
    ]

    windows = summarize_region_quality_windows(
        snapshots,
        audits,
        window_size_s=1.0,
        covariance_growth_threshold=2.5,
    )

    assert len(windows) == 2
    first, second = [window.to_dict() for window in windows]
    assert (first["window_start"], first["window_end"]) == (0.0, 1.0)
    assert (second["window_start"], second["window_end"]) == (1.0, 2.0)
    assert first["window_duration_s"] == 1.0
    assert first["sample_count"] == 2
    assert second["sample_count"] == 2
    assert first["latency_observation_count"] == 2
    assert second["latency_observation_count"] == 2
    assert first["oosm_observation_count"] == 1
    assert second["oosm_observation_count"] == 1
    assert second["max_covariance_growth_rate"] == pytest.approx(4.0)
    assert "regional_covariance_growing" in second["quality_flags"]


def _radar_observation(
    *,
    observation_id: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
    sensor_id: str = "radar-writer",
) -> SensorObservation:
    state = np.array([100.0 + 4.0 * measurement_timestamp, 10.0, -8.0, 4.0, 0.0, 0.0])
    sensor_position = np.zeros(3)
    measurement = radar_h(state, sensor_position)
    return SensorObservation(
        observation_id=observation_id,
        sensor_id=sensor_id,
        modality="radar",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id="ned",
        measurement=measurement,
        covariance=radar_covariance_from_range(float(measurement[0])),
        metadata={"sensor_position_ned": sensor_position, "coverage_cell": "cell-a"},
    )


def _region(published_at: float, *, mean_a95: float, growth: float) -> FusionQualityRegionSummary:
    return FusionQualityRegionSummary(
        coverage_cell="cell-window",
        published_at=published_at,
        track_count=2,
        coarse_track_count=0,
        stable_track_count=2,
        handover_track_count=0,
        stale_track_count=0,
        mean_a95_m=mean_a95,
        max_a95_m=mean_a95 + 1.0,
        max_measurement_age_s=0.2,
        mean_handover_readiness=0.7,
        source_support={"radar": 2, "eo": 1},
        mean_covariance_growth_rate=growth,
        max_covariance_growth_rate=growth,
    )


def _audit(
    *,
    published_at: float,
    observation_count: int,
    oosm_count: int,
) -> LatencyAuditSummary:
    return LatencyAuditSummary(
        observation_count=observation_count,
        replay_count=oosm_count,
        oosm_observation_count=oosm_count,
        stale_observation_count=0,
        stale_or_oosm_observation_count=oosm_count,
        max_delay_s=0.2,
        mean_delay_s=0.2,
        duplicate_observation_count=0,
        max_replay_observation_count=2,
        latency_compensation=True,
        published_at=published_at,
    )
