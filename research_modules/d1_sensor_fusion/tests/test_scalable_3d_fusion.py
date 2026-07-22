from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
import math

import numpy as np
import pytest

from d1_sensor_fusion import (
    FusionStateUpdateResult,
    SCALABLE_3D_POSITION_ONLY_RADAR_NIS_GATE,
    SCALABLE_3D_UNOBSERVED_VELOCITY_VARIANCE_M2PS2,
    Scalable3DFusionAdapter,
    sensor_observation_from_online_measurement,
)
from d1_sensor_fusion.observations import (
    measurement_model_for,
    radar_state_from_observation,
)
from research_modules.scalable_3d_simulation.models import (
    OnlineSensorBatch,
    ScenarioConfig,
    SensorMeasurement,
)
from research_modules.scalable_3d_simulation.sensor_scene import SensorScene
from research_modules.scalable_3d_simulation.world import VectorizedPointMassWorld


def _online_batch(batch_id: str, measurements: tuple[SensorMeasurement, ...]) -> OnlineSensorBatch:
    first = measurements[0]
    return OnlineSensorBatch(
        batch_id=batch_id,
        sensor_id=first.sensor_id,
        measurement_timestamp=first.measurement_timestamp,
        arrival_timestamp=first.arrival_timestamp,
        measurements=measurements,
    )


def _radar_measurement(
    observation_id: str,
    position_ned: np.ndarray,
    *,
    measurement_timestamp: float,
    arrival_timestamp: float,
    sensor_id: str = "RADAR-CENTER-001",
) -> SensorMeasurement:
    position = np.asarray(position_ned, dtype=float)
    range_m = float(np.linalg.norm(position))
    horizontal = float(np.linalg.norm(position[:2]))
    range_std = 3.0 + 1.5 * range_m / 1_000.0
    angle_std = math.radians(0.2)
    return SensorMeasurement(
        observation_id=observation_id,
        sensor_id=sensor_id,
        modality="radar_spherical",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id="radar_center_frame",
        measurement=np.array(
            [
                range_m,
                math.atan2(float(position[1]), float(position[0])),
                math.atan2(float(-position[2]), max(horizontal, 1.0e-9)),
            ],
            dtype=float,
        ),
        covariance=np.diag([range_std**2, angle_std**2, angle_std**2]),
        confidence=0.98,
        classification_hint="unmanned_aircraft",
        metadata={
            "measurement_order": ["range_m", "azimuth_rad", "elevation_rad"],
            "sensor_position_ned": [0.0, 0.0, 0.0],
            "range_dependent_covariance": True,
        },
    )


def test_online_batch_can_update_state_without_materializing_tracks() -> None:
    measurement = _radar_measurement(
        "radar-state-only",
        np.array([1_000.0, 80.0, -120.0]),
        measurement_timestamp=1.0,
        arrival_timestamp=1.2,
    )
    adapter = Scalable3DFusionAdapter()

    result = adapter.process_online_sensor_batch(
        _online_batch("radar-state-only-batch", (measurement,)),
        materialize_tracks=False,
    )

    assert isinstance(result, FusionStateUpdateResult)
    assert result.current_track_count == 1
    assert result.tracks_materialized is False
    snapshot = adapter.materialize_global_tracks()
    assert len(snapshot.tracks) == 1
    assert snapshot.tracks[0].global_track_id == "global_track_001"


@pytest.mark.parametrize("target_count", [5, 20, 50, 100, 200])
def test_scan_batch_preserves_all_tracks_at_curriculum_scales(target_count: int) -> None:
    config = ScenarioConfig(
        target_count=target_count,
        resource_count=target_count,
        recon_count=0,
        duration_s=0.3,
        radar_detection_probability=1.0,
        radar_range_limit_m=8_000.0,
    )
    world = VectorizedPointMassWorld(config)
    scene = SensorScene(config)
    adapter = Scalable3DFusionAdapter(association_gate=40.0)

    first_measurements = scene.radar_scan(world.snapshot()).measurements
    first = adapter.process_online_sensor_batch(
        _online_batch(f"radar-{target_count}-000", first_measurements)
    )
    first_ids = {track.global_track_id for track in first.tracks}

    assert len(first_measurements) == target_count
    assert len(first.tracks) == target_count
    assert len(first_ids) == target_count
    assert first.summary.created_track_count == target_count
    assert first.summary.unaccepted_observation_count == 0
    assert all(track.state.shape == (6,) for track in first.tracks)
    assert all(track.covariance.shape == (6, 6) for track in first.tracks)
    assert all(np.isfinite(track.state).all() for track in first.tracks)
    assert all(np.linalg.eigvalsh(track.covariance).min() >= -1.0e-8 for track in first.tracks)

    for _ in range(4):
        world.step()
    second_measurements = scene.radar_scan(world.snapshot()).measurements
    second = adapter.process_online_sensor_batch(
        _online_batch(f"radar-{target_count}-001", second_measurements)
    )

    assert len(second.tracks) == target_count
    assert {track.global_track_id for track in second.tracks} == first_ids
    assert second.summary.created_track_count == 0
    assert second.summary.updated_track_count == target_count
    assert second.summary.unaccepted_observation_count == 0
    if target_count == 200:
        assert len(second.tracks) > 5 * 34


def test_spherical_radar_to_ned_preserves_covariance_and_dual_timestamps() -> None:
    source_covariance = np.diag(
        [8.0**2, math.radians(0.3) ** 2, math.radians(0.4) ** 2]
    )
    measurement = SensorMeasurement(
        observation_id="radar-anonymous-001",
        sensor_id="RADAR-CENTER-001",
        modality="radar_spherical",
        measurement_timestamp=2.0,
        arrival_timestamp=2.25,
        frame_id="radar_center_frame",
        measurement=np.array([1_000.0, 0.5 * np.pi, math.radians(10.0)]),
        covariance=source_covariance,
        confidence=0.9,
        metadata={
            "sensor_position_ned": [10.0, 20.0, -5.0],
            "range_dependent_covariance": True,
        },
    )
    observation = sensor_observation_from_online_measurement(
        measurement,
        batch_id="radar-transform-001",
    )
    state, covariance = radar_state_from_observation(observation)
    expected = np.array(
        [
            10.0,
            20.0 + 1_000.0 * math.cos(math.radians(10.0)),
            -5.0 - 1_000.0 * math.sin(math.radians(10.0)),
        ]
    )

    assert observation.modality == "radar"
    assert observation.frame_id == "ned"
    assert observation.measurement.shape == (4,)
    assert observation.covariance.shape == (4, 4)
    assert np.array_equal(observation.covariance[:3, :3], source_covariance)
    assert np.allclose(state[:3], expected, atol=1.0e-9)
    assert covariance.shape == (6, 6)
    assert np.linalg.eigvalsh(covariance).min() >= -1.0e-8

    adapter = Scalable3DFusionAdapter()
    result = adapter.process_measurement_scan((measurement,), batch_id="radar-transform-001")
    track = result.tracks[0]
    assert track.metadata["measurement_timestamp"] == pytest.approx(2.0)
    assert track.metadata["arrival_timestamp"] == pytest.approx(2.25)
    assert track.metadata["latest_measurement_timestamp"] == pytest.approx(2.0)
    assert track.metadata["latest_arrival_timestamp"] == pytest.approx(2.25)
    assert track.metadata["range_dependent_covariance"] is True


def test_position_only_radar_ignores_placeholder_and_uses_velocity_prior() -> None:
    measurement = _radar_measurement(
        "radar-position-only",
        np.array([1_400.0, -320.0, -180.0]),
        measurement_timestamp=3.0,
        arrival_timestamp=3.2,
    )
    observation = sensor_observation_from_online_measurement(
        measurement,
        batch_id="radar-position-only-scan",
    )
    state, covariance = radar_state_from_observation(observation)
    model = measurement_model_for(observation)

    assert observation.measurement.shape == (4,)
    assert observation.measurement[3] == pytest.approx(0.0)
    assert observation.metadata["radial_velocity_observed"] is False
    assert observation.metadata["radial_velocity_placeholder_ignored"] is True
    assert observation.metadata["filter_measurement_dimension"] == 3
    assert model.z.shape == (3,)
    assert model.r.shape == (3, 3)
    assert model.h_fn(np.concatenate((state[:3], [30.0, -20.0, 10.0]))).shape == (3,)
    assert np.array_equal(state[3:], np.zeros(3))
    assert np.allclose(covariance[:3, 3:], 0.0, atol=1.0e-12)
    assert np.allclose(covariance[3:, :3], 0.0, atol=1.0e-12)
    assert np.allclose(
        covariance[3:, 3:],
        np.eye(3) * SCALABLE_3D_UNOBSERVED_VELOCITY_VARIANCE_M2PS2,
        atol=1.0e-12,
    )
    assert observation.metadata["velocity_initialization_model"] == (
        "zero_mean_isotropic_gaussian"
    )


def test_position_only_radar_innovation_gate_rejects_outlier_with_audit() -> None:
    adapter = Scalable3DFusionAdapter(association_gate=40.0)
    scans = (
        ("gate-scan-000", 0.0, np.array([1_000.0, 0.0, -100.0])),
        ("gate-scan-001", 0.2, np.array([1_000.8, 0.0, -100.0])),
        ("gate-scan-002-outlier", 0.4, np.array([1_001.6, 20.0, -100.0])),
    )
    results = []
    for label, measurement_time, position in scans:
        measurement = _radar_measurement(
            label,
            position,
            measurement_timestamp=measurement_time,
            arrival_timestamp=measurement_time + 0.2,
        )
        results.append(
            adapter.process_online_sensor_batch(_online_batch(label, (measurement,)))
        )

    before_outlier = results[1].tracks[0]
    after_outlier = results[2].tracks[0]
    assert len(results[2].tracks) == 1
    assert results[2].summary.created_track_count == 0
    assert results[2].summary.updated_track_count == 1
    assert np.allclose(after_outlier.state[3:], before_outlier.state[3:], atol=1.0e-12)
    assert after_outlier.metadata["filter_innovation_gate_chi2"] == pytest.approx(
        SCALABLE_3D_POSITION_ONLY_RADAR_NIS_GATE
    )
    assert after_outlier.metadata["latest_replay_innovation_count"] == 2
    assert after_outlier.metadata["latest_replay_filter_update_count"] == 1
    assert (
        after_outlier.metadata["latest_replay_innovation_gate_rejection_count"]
        == 1
    )
    assert after_outlier.metadata[
        "latest_replay_innovation_gate_rejected_observation_ids"
    ] == ("gate-scan-002-outlier",)
    assert adapter.tracks[after_outlier.global_track_id].recent_nis[-1] > (
        SCALABLE_3D_POSITION_ONLY_RADAR_NIS_GATE
    )


def test_delayed_scan_is_replayed_as_oosm_without_changing_track_count() -> None:
    base_positions = np.array(
        [[1_200.0, -250.0, -120.0], [1_050.0, 380.0, -180.0]],
        dtype=float,
    )
    velocities = np.array([[5.0, 1.0, -0.2], [-3.0, 2.0, 0.1]], dtype=float)
    adapter = Scalable3DFusionAdapter(association_gate=40.0)

    def process_scan(label: str, measurement_time: float, arrival_time: float):
        items = tuple(
            _radar_measurement(
                f"{label}-d{index:03d}",
                position + velocity * measurement_time,
                measurement_timestamp=measurement_time,
                arrival_timestamp=arrival_time,
            )
            for index, (position, velocity) in enumerate(zip(base_positions, velocities))
        )
        return adapter.process_online_sensor_batch(_online_batch(label, items))

    first = process_scan("scan-000", 0.0, 0.2)
    second = process_scan("scan-100", 1.0, 1.2)
    delayed = process_scan("scan-050-delayed", 0.5, 1.4)

    assert len(first.tracks) == len(second.tracks) == len(delayed.tracks) == 2
    assert {track.global_track_id for track in delayed.tracks} == {
        track.global_track_id for track in first.tracks
    }
    assert delayed.summary.created_track_count == 0
    assert delayed.summary.updated_track_count == 2
    assert adapter.oosm_observation_count == 2
    assert all(track.timestamp == pytest.approx(1.4) for track in delayed.tracks)
    assert all(np.isfinite(track.covariance).all() for track in delayed.tracks)


def test_oosm_replay_matches_in_order_state_and_preserves_dual_timestamps() -> None:
    base_positions = np.array(
        [[1_200.0, -250.0, -120.0], [1_050.0, 380.0, -180.0]],
        dtype=float,
    )
    velocities = np.array([[3.0, 1.0, -0.2], [-2.0, 1.5, 0.1]], dtype=float)

    def run_schedule(
        schedule: tuple[tuple[str, float, float], ...],
    ) -> tuple[Scalable3DFusionAdapter, tuple]:
        adapter = Scalable3DFusionAdapter(association_gate=40.0)
        result = None
        for label, measurement_time, arrival_time in schedule:
            measurements = tuple(
                _radar_measurement(
                    f"{label}-d{index:03d}",
                    position + velocity * measurement_time,
                    measurement_timestamp=measurement_time,
                    arrival_timestamp=arrival_time,
                )
                for index, (position, velocity) in enumerate(
                    zip(base_positions, velocities)
                )
            )
            result = adapter.process_online_sensor_batch(
                _online_batch(label, measurements)
            )
        assert result is not None
        return adapter, result.tracks

    _, in_order_tracks = run_schedule(
        (
            ("scan-000", 0.0, 0.2),
            ("scan-050", 0.5, 0.7),
            ("scan-100", 1.0, 1.4),
        )
    )
    delayed_adapter, delayed_tracks = run_schedule(
        (
            ("scan-000", 0.0, 0.2),
            ("scan-100", 1.0, 1.2),
            ("scan-050", 0.5, 1.4),
        )
    )

    assert delayed_adapter.oosm_observation_count == len(delayed_tracks)
    assert [track.global_track_id for track in delayed_tracks] == [
        track.global_track_id for track in in_order_tracks
    ]
    for in_order, delayed in zip(in_order_tracks, delayed_tracks):
        assert np.allclose(delayed.state, in_order.state, atol=1.0e-9)
        assert np.allclose(delayed.covariance, in_order.covariance, atol=1.0e-9)
        assert delayed.state.shape == (6,)
        assert delayed.covariance.shape == (6, 6)
        assert delayed.timestamp == pytest.approx(1.4)
        assert delayed.metadata["measurement_timestamp"] == pytest.approx(0.5)
        assert delayed.metadata["arrival_timestamp"] == pytest.approx(1.4)
        assert delayed.metadata["latest_measurement_timestamp"] == pytest.approx(0.5)
        assert delayed.metadata["latest_arrival_timestamp"] == pytest.approx(1.4)
        assert np.linalg.eigvalsh(delayed.covariance).min() >= -1.0e-8


def test_two_hundred_position_only_tracks_remain_stable_over_ten_scans() -> None:
    target_count = 200
    config = ScenarioConfig(
        seed=17,
        target_count=target_count,
        resource_count=target_count,
        recon_count=0,
        duration_s=1.8,
        radar_detection_probability=1.0,
        radar_range_limit_m=8_000.0,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_enabled=False,
    )
    world = VectorizedPointMassWorld(config)
    scene = SensorScene(config)
    adapter = Scalable3DFusionAdapter(association_gate=40.0)
    track_ids: set[str] | None = None
    median_speeds: list[float] = []
    median_velocity_covariance_traces: list[float] = []

    for scan_index in range(10):
        measurements = scene.radar_scan(world.snapshot()).measurements
        result = adapter.process_online_sensor_batch(
            _online_batch(f"radar-200-{scan_index:03d}", measurements)
        )
        current_ids = {track.global_track_id for track in result.tracks}
        if track_ids is None:
            track_ids = current_ids
        assert len(measurements) == target_count
        assert len(result.tracks) == target_count
        assert current_ids == track_ids
        assert all(np.isfinite(track.state).all() for track in result.tracks)
        assert all(np.isfinite(track.covariance).all() for track in result.tracks)
        assert all(track.state.shape == (6,) for track in result.tracks)
        assert all(track.covariance.shape == (6, 6) for track in result.tracks)

        speeds = np.array(
            [np.linalg.norm(track.state[3:]) for track in result.tracks]
        )
        velocity_covariance_traces = np.array(
            [np.trace(track.covariance[3:, 3:]) for track in result.tracks]
        )
        median_speeds.append(float(np.median(speeds)))
        median_velocity_covariance_traces.append(
            float(np.median(velocity_covariance_traces))
        )
        assert np.isfinite(speeds).all()
        assert np.isfinite(velocity_covariance_traces).all()
        assert np.max(speeds**2 / velocity_covariance_traces) < 2.0

        if scan_index < 9:
            for _ in range(4):
                world.step()

    assert track_ids is not None and len(track_ids) == target_count
    assert max(median_speeds) < math.sqrt(
        max(median_velocity_covariance_traces)
    )
    assert median_velocity_covariance_traces[-1] > (
        0.5 * median_velocity_covariance_traces[0]
    )
    assert median_velocity_covariance_traces[-1] < (
        1.1 * median_velocity_covariance_traces[0]
    )


def test_online_adapter_rejects_truth_actor_and_object_identifiers() -> None:
    measurement = _radar_measurement(
        "anonymous-radar",
        np.array([1_000.0, 0.0, -100.0]),
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
    )
    payload = {
        "batch_id": "identity-leak",
        "sensor_id": measurement.sensor_id,
        "measurement_timestamp": 0.0,
        "arrival_timestamp": 0.2,
        "measurements": [
            {
                "observation_id": measurement.observation_id,
                "sensor_id": measurement.sensor_id,
                "modality": measurement.modality,
                "measurement_timestamp": measurement.measurement_timestamp,
                "arrival_timestamp": measurement.arrival_timestamp,
                "frame_id": measurement.frame_id,
                "measurement": measurement.measurement,
                "covariance": measurement.covariance,
                "confidence": measurement.confidence,
                "metadata": {
                    "sensor_position_ned": [0.0, 0.0, 0.0],
                    "truth_entity_id": "TGT-0001",
                    "actor_id": "actor-7",
                    "object_id": "mesh-9",
                },
            }
        ],
    }

    with pytest.raises(ValueError, match="identity truth"):
        Scalable3DFusionAdapter().process_online_sensor_batch(payload)


def test_acoustic_3d_is_category_only_update_and_never_starts_a_track() -> None:
    config = ScenarioConfig(
        target_count=5,
        resource_count=5,
        recon_count=0,
        duration_s=0.2,
        radar_detection_probability=1.0,
        radar_range_limit_m=8_000.0,
        acoustic_detection_probability=1.0,
        acoustic_range_limit_m=8_000.0,
    )
    world = VectorizedPointMassWorld(config)
    scene = SensorScene(config)
    acoustic_measurements = scene.acoustic_scan(world.snapshot()).measurements
    grouped: defaultdict[str, list[SensorMeasurement]] = defaultdict(list)
    for measurement in acoustic_measurements:
        grouped[measurement.sensor_id].append(measurement)
    sensor_id = sorted(grouped)[0]
    acoustic_batch = _online_batch(
        "acoustic-category-only",
        tuple(grouped[sensor_id]),
    )
    invalid_soundprint = replace(
        acoustic_batch.measurements[0],
        metadata={
            **dict(acoustic_batch.measurements[0].metadata),
            "soundprint_is_identity": True,
        },
    )
    with pytest.raises(ValueError, match="soundprint_is_identity must be false"):
        Scalable3DFusionAdapter().process_measurement_scan(
            (invalid_soundprint,),
            batch_id="invalid-soundprint-identity",
        )

    empty_adapter = Scalable3DFusionAdapter()
    no_birth = empty_adapter.process_online_sensor_batch(acoustic_batch)
    assert no_birth.tracks == ()
    assert no_birth.summary.created_track_count == 0

    adapter = Scalable3DFusionAdapter(association_gate=40.0)
    radar_measurements = scene.radar_scan(world.snapshot()).measurements
    radar_result = adapter.process_online_sensor_batch(
        _online_batch("radar-before-acoustic", radar_measurements)
    )
    track_ids = {track.global_track_id for track in radar_result.tracks}
    acoustic_result = adapter.process_online_sensor_batch(acoustic_batch)

    assert len(acoustic_result.tracks) == config.target_count
    assert {track.global_track_id for track in acoustic_result.tracks} == track_ids
    assert acoustic_result.summary.created_track_count == 0
    assert acoustic_result.summary.updated_track_count == config.target_count
    for track in acoustic_result.tracks:
        assert track.source_support["acoustic_3d"] == 1
        assert track.metadata["soundprint_category_only"] is True
        assert "soundprint_is_identity" not in track.metadata
        probabilities = np.asarray(track.metadata["soundprint_class_probabilities"])
        assert float(np.sum(probabilities)) == pytest.approx(1.0)
