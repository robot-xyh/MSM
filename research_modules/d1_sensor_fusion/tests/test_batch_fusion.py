from __future__ import annotations

from collections.abc import Callable, Iterable

import numpy as np
import pytest

from d1_sensor_fusion import FusionAdapter, FusionBatchResult
from d1_sensor_fusion.observations import (
    acoustic_covariance,
    lidar_covariance,
    radar_covariance_from_range,
    radar_h,
)
from d1_sensor_fusion.types import GlobalTrack, SensorObservation


SENSOR_POSITION = np.zeros(3)


def _state_at(base: np.ndarray, timestamp: float) -> np.ndarray:
    state = np.asarray(base, dtype=float).copy()
    state[:3] += state[3:] * float(timestamp)
    return state


def _radar(
    observation_id: str,
    base: np.ndarray,
    measurement_timestamp: float,
    arrival_timestamp: float,
    scan_id: str,
) -> SensorObservation:
    state = _state_at(base, measurement_timestamp)
    measurement = radar_h(state, SENSOR_POSITION)
    return SensorObservation(
        observation_id=observation_id,
        sensor_id="radar-main",
        modality="radar",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id="ned",
        measurement=measurement,
        covariance=radar_covariance_from_range(measurement[0]),
        metadata={
            "sensor_position_ned": SENSOR_POSITION,
            "scan_id": scan_id,
            "coverage_cell": "batch-test-cell",
        },
    )


def _lidar(
    observation_id: str,
    base: np.ndarray,
    measurement_timestamp: float,
    arrival_timestamp: float,
    scan_id: str,
) -> SensorObservation:
    position = _state_at(base, measurement_timestamp)[:3]
    return SensorObservation(
        observation_id=observation_id,
        sensor_id="lidar-main",
        modality="lidar",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id="ned",
        measurement=position,
        covariance=lidar_covariance(float(np.linalg.norm(position))),
        metadata={"scan_id": scan_id, "coverage_cell": "batch-test-cell"},
    )


def _acoustic(
    observation_id: str,
    base: np.ndarray,
    measurement_timestamp: float,
    arrival_timestamp: float,
    scan_id: str,
) -> SensorObservation:
    position = _state_at(base, measurement_timestamp)[:3]
    return SensorObservation(
        observation_id=observation_id,
        sensor_id="acoustic-main",
        modality="acoustic",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id="ned",
        measurement=np.array([np.arctan2(position[1], position[0])]),
        covariance=acoustic_covariance(0.9),
        confidence=0.9,
        metadata={
            "sensor_position_ned": SENSOR_POSITION,
            "scan_id": scan_id,
            "coverage_cell": "batch-test-cell",
        },
    )


def _targets(count: int = 5) -> list[np.ndarray]:
    return [
        np.array(
            [
                120.0 + 18.0 * index,
                -72.0 + 36.0 * index,
                -18.0 - 2.0 * index,
                3.5 + 0.2 * index,
                0.15 * (index - 2),
                0.0,
            ]
        )
        for index in range(count)
    ]


def _process_one_by_one(
    adapter: FusionAdapter,
    observations: Iterable[SensorObservation],
) -> list[GlobalTrack]:
    tracks = adapter.global_tracks()
    for observation in observations:
        tracks = adapter.process(observation)
    return tracks


def _assert_track_sets_equivalent(
    sequential: Iterable[GlobalTrack],
    batched: Iterable[GlobalTrack],
    *,
    atol: float = 1.0e-9,
) -> None:
    sequential_by_id = {track.global_track_id: track for track in sequential}
    batched_by_id = {track.global_track_id: track for track in batched}
    assert batched_by_id.keys() == sequential_by_id.keys()
    for track_id, expected in sequential_by_id.items():
        actual = batched_by_id[track_id]
        assert actual.timestamp == pytest.approx(expected.timestamp, abs=1.0e-12)
        assert np.allclose(actual.state, expected.state, rtol=1.0e-10, atol=atol)
        assert np.allclose(actual.covariance, expected.covariance, rtol=1.0e-10, atol=atol)
        assert actual.track_level == expected.track_level
        assert actual.source_support == expected.source_support
        assert actual.identity_likelihood == pytest.approx(expected.identity_likelihood)
        assert actual.last_nis == pytest.approx(expected.last_nis)
        assert actual.metadata["hits"] == expected.metadata["hits"]
        assert actual.metadata["latest_measurement_timestamp"] == pytest.approx(
            expected.metadata["latest_measurement_timestamp"]
        )
        assert actual.metadata["latest_arrival_timestamp"] == pytest.approx(
            expected.metadata["latest_arrival_timestamp"]
        )
        assert actual.metadata["latency_audit"] == expected.metadata["latency_audit"]


def _seed_tracks(adapters: Iterable[FusionAdapter], targets: list[np.ndarray]) -> None:
    for adapter in adapters:
        for frame in range(8):
            timestamp = 0.1 * frame
            observations = [
                _radar(
                    f"seed-radar-{target_index}-{frame}",
                    target,
                    timestamp,
                    timestamp + 0.2,
                    f"seed-radar-{frame}",
                )
                for target_index, target in enumerate(targets)
            ]
            _process_one_by_one(adapter, observations)


def _count_replay_calls(adapter: FusionAdapter) -> Callable[[], int]:
    original = adapter._replay_record
    count = 0

    def counted(record, until_time):
        nonlocal count
        count += 1
        return original(record, until_time)

    adapter._replay_record = counted  # type: ignore[method-assign]
    return lambda: count


def test_process_batch_matches_streaming_for_same_frame_multimodal_observations() -> None:
    targets = _targets(5)
    sequential = FusionAdapter(association_gate=50.0)
    batched = FusionAdapter(association_gate=50.0)
    _seed_tracks((sequential, batched), targets)

    observations: list[SensorObservation] = []
    for modality in ("radar", "lidar", "acoustic"):
        for target_index, target in enumerate(targets):
            factory = {"radar": _radar, "lidar": _lidar, "acoustic": _acoustic}[modality]
            observations.append(
                factory(
                    f"frame-{modality}-{target_index}",
                    target,
                    0.8,
                    1.0,
                    f"frame-{modality}",
                )
            )

    expected = _process_one_by_one(sequential, observations)
    result = batched.process_batch(observations)

    assert isinstance(result, FusionBatchResult)
    _assert_track_sets_equivalent(expected, result.tracks)
    assert result.summary.observation_count == 15
    assert result.summary.accepted_observation_count == 15
    assert result.summary.updated_observation_count == 15
    assert result.summary.updated_track_count == 5
    assert result.summary.created_track_count == 0
    assert result.summary.finalization_replay_count == 5
    assert result.summary.deferred_update_replay_avoidance_count == 10
    assert result.summary.state_cache_hit_count > result.summary.state_cache_miss_count
    assert result.summary.ordering == "input_arrival_order"
    assert result.to_dict()["summary"]["observation_count"] == 15


def test_process_batch_preserves_oosm_order_and_audit_semantics() -> None:
    target = _targets(1)[0]
    sequential = FusionAdapter(association_gate=50.0)
    batched = FusionAdapter(association_gate=50.0)
    initial = [
        _radar("oosm-radar-0", target, 0.0, 0.1, "oosm-radar-0"),
        _radar("oosm-radar-1", target, 1.0, 1.1, "oosm-radar-1"),
        _radar("oosm-radar-2", target, 2.0, 2.1, "oosm-radar-2"),
    ]
    _process_one_by_one(sequential, initial)
    _process_one_by_one(batched, initial)

    delayed = [
        _lidar("oosm-lidar-later", target, 1.4, 2.6, "oosm-lidar-later"),
        _acoustic("oosm-acoustic-earlier", target, 0.6, 2.6, "oosm-acoustic-earlier"),
        _lidar("oosm-lidar-middle", target, 1.0, 2.65, "oosm-lidar-middle"),
    ]
    expected = _process_one_by_one(sequential, delayed)
    result = batched.process_batch(delayed)

    _assert_track_sets_equivalent(expected, result.tracks)
    assert batched.latency_audit_summary().to_dict() == sequential.latency_audit_summary().to_dict()
    assert result.summary.accepted_observation_count == 3
    assert result.summary.finalization_replay_count == 1
    assert batched.oosm_observation_count == sequential.oosm_observation_count == 3
    assert result.tracks[0].metadata["frame_id"] == "ned"


def test_process_batch_deduplicates_relayed_source_without_dropping_unique_payloads() -> None:
    target = _targets(1)[0]
    measurement = radar_h(target, SENSOR_POSITION)
    common = {
        "sensor_position_ned": SENSOR_POSITION,
        "source_lineage_key": ("radar-node-a", "payload-007"),
    }
    direct = SensorObservation(
        observation_id="batch-direct",
        sensor_id="radar-main",
        modality="radar",
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
        frame_id="ned",
        measurement=measurement,
        covariance=radar_covariance_from_range(measurement[0]),
        metadata=common,
        source_node_id="radar-node-a",
    )
    relayed_duplicate = SensorObservation(
        observation_id="batch-relayed-duplicate",
        sensor_id="radar-main",
        modality="radar",
        measurement_timestamp=0.0,
        arrival_timestamp=0.3,
        frame_id="ned",
        measurement=measurement,
        covariance=radar_covariance_from_range(measurement[0]),
        metadata=common,
        source_node_id="radar-node-a",
        relay_node_id="secondary-node-1",
    )

    result = FusionAdapter().process_batch((direct, relayed_duplicate))

    assert len(result.tracks) == 1
    assert result.tracks[0].metadata["hits"] == 1
    assert result.tracks[0].source_support == {"radar": 1}
    assert result.summary.accepted_observation_count == 1
    assert result.summary.unaccepted_observation_count == 1
    assert result.summary.duplicate_observation_count == 1


def test_process_batch_matches_streaming_across_fixed_lag_checkpoint_boundary() -> None:
    target = _targets(1)[0]
    sequential = FusionAdapter(buffer_horizon=0.5, association_gate=50.0)
    batched = FusionAdapter(buffer_horizon=0.5, association_gate=50.0)
    initial = [
        _radar("lag-radar-origin", target, 0.0, 0.0, "lag-radar-origin"),
        _radar("lag-radar-middle", target, 0.4, 0.4, "lag-radar-middle"),
        _radar("lag-radar-current", target, 1.0, 1.0, "lag-radar-current"),
    ]
    _process_one_by_one(sequential, initial)
    _process_one_by_one(batched, initial)
    assert next(iter(batched.tracks.values())).checkpoint_active

    boundary_observations = [
        _lidar("lag-inside-window", target, 0.6, 1.2, "lag-inside-window"),
        _acoustic("lag-before-checkpoint", target, 0.3, 1.2, "lag-before-checkpoint"),
    ]
    expected = _process_one_by_one(sequential, boundary_observations)
    result = batched.process_batch(boundary_observations)

    _assert_track_sets_equivalent(expected, result.tracks, atol=1.0e-8)
    sequential_record = next(iter(sequential.tracks.values()))
    batched_record = next(iter(batched.tracks.values()))
    assert batched_record.initial_state.timestamp == pytest.approx(
        sequential_record.initial_state.timestamp
    )
    assert batched_record.checkpoint_count == sequential_record.checkpoint_count
    assert batched.pre_checkpoint_oosm_replay_count == sequential.pre_checkpoint_oosm_replay_count
    assert result.summary.origin_replay_count >= 1


def test_process_batch_reduces_history_replays_for_dense_same_time_frame() -> None:
    targets = _targets(5)
    sequential = FusionAdapter(
        association_gate=50.0,
        direct_checkpoint_state_queries=False,
    )
    batched = FusionAdapter(
        association_gate=50.0,
        direct_checkpoint_state_queries=False,
    )
    _seed_tracks((sequential, batched), targets)
    sequential_replays = _count_replay_calls(sequential)
    batched_replays = _count_replay_calls(batched)

    observations = [
        factory(
            f"perf-{modality}-{target_index}",
            target,
            0.8,
            1.0,
            f"perf-{modality}",
        )
        for modality, factory in (("radar", _radar), ("lidar", _lidar), ("acoustic", _acoustic))
        for target_index, target in enumerate(targets)
    ]
    expected = _process_one_by_one(sequential, observations)
    result = batched.process_batch(observations)

    _assert_track_sets_equivalent(expected, result.tracks)
    assert result.summary.history_replay_count == batched_replays()
    assert batched_replays() <= 0.5 * sequential_replays()
    assert result.summary.finalization_replay_count == len(targets)
    assert result.summary.deferred_update_replay_avoidance_count == 10


def test_ingest_many_keeps_arrival_order_compatibility_and_uses_batch_result() -> None:
    target = _targets(1)[0]
    observations = [
        _lidar("ingest-lidar", target, 0.2, 0.4, "ingest-lidar"),
        _radar("ingest-radar", target, 0.0, 0.1, "ingest-radar"),
    ]
    adapter = FusionAdapter(association_gate=50.0)

    tracks = adapter.ingest_many(observations)

    assert len(tracks) == 1
    assert tracks[0].source_support == {"radar": 1, "lidar": 1}
    assert tracks[0].timestamp == pytest.approx(0.4)
