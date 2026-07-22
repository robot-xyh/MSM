from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

import numpy as np
import pytest

from d1_sensor_fusion import Scalable3DFusionAdapter
from d1_sensor_fusion.observations import acoustic_covariance, radar_covariance_from_range, radar_h
from d1_sensor_fusion.types import FusionBatchResult, SensorObservation


def _canonical(value):
    if isinstance(value, np.ndarray):
        return _canonical(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _target_state(index: int, timestamp: float) -> np.ndarray:
    state = np.array(
        [
            800.0 + 24.0 * index,
            -900.0 + 31.0 * index,
            -120.0 - 0.5 * index,
            4.0 + 0.03 * index,
            -1.0 + 0.01 * index,
            0.05,
        ],
        dtype=float,
    )
    state[:3] += state[3:] * float(timestamp)
    return state


def _radar_scan(
    target_count: int,
    *,
    measurement_timestamp: float,
    arrival_timestamp: float,
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    observations = []
    for index in range(target_count):
        measurement = radar_h(_target_state(index, measurement_timestamp), np.zeros(3))
        observations.append(
            SensorObservation(
                observation_id=f"{scan_id}-target-{index:03d}",
                sensor_id="radar-performance",
                modality="radar",
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                frame_id="ned",
                measurement=measurement,
                covariance=radar_covariance_from_range(float(measurement[0])),
                classification_hint="unmanned_aircraft",
                confidence=0.95,
                metadata={
                    "sensor_position_ned": np.zeros(3),
                    "scan_id": scan_id,
                    "coverage_cell": "performance-cell",
                },
            )
        )
    return tuple(observations)


def _acoustic_observation(
    *,
    measurement_timestamp: float,
    arrival_timestamp: float,
    scan_id: str,
) -> SensorObservation:
    position = _target_state(0, measurement_timestamp)[:3]
    return SensorObservation(
        observation_id=scan_id,
        sensor_id="acoustic-performance",
        modality="acoustic",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id="ned",
        measurement=np.array([np.arctan2(position[1], position[0])]),
        covariance=acoustic_covariance(0.95),
        confidence=0.95,
        metadata={
            "sensor_position_ned": np.zeros(3),
            "scan_id": scan_id,
            "coverage_cell": "performance-cell",
        },
    )


def _adapters(**kwargs) -> tuple[Scalable3DFusionAdapter, Scalable3DFusionAdapter]:
    common = {"association_gate": 40.0, **kwargs}
    legacy = Scalable3DFusionAdapter(
        **common,
        incremental_replay_cache=False,
        shared_publication_audit_snapshot=False,
    )
    optimized = Scalable3DFusionAdapter(
        **common,
        incremental_replay_cache=True,
        shared_publication_audit_snapshot=True,
    )
    return legacy, optimized


def _semantic_batch(result: FusionBatchResult) -> dict:
    summary = result.summary.to_dict()
    for key in (
        "replay_filter_update_count",
        "replay_checkpoint_reuse_count",
        "global_track_materialization_count",
        "sensor_health_snapshot_build_count",
    ):
        summary.pop(key)
    return {
        "tracks": _canonical([track.to_dict() for track in result.tracks]),
        "summary": _canonical(summary),
    }


def _assert_semantically_equal(
    legacy: Scalable3DFusionAdapter,
    optimized: Scalable3DFusionAdapter,
    legacy_result: FusionBatchResult,
    optimized_result: FusionBatchResult,
) -> None:
    assert _semantic_batch(optimized_result) == _semantic_batch(legacy_result)
    assert _canonical(
        [item.to_dict() for item in optimized.consistency_evidence_records()]
    ) == _canonical([item.to_dict() for item in legacy.consistency_evidence_records()])


@pytest.mark.parametrize("target_count", [1, 7, 200])
def test_incremental_replay_is_exact_and_reduces_filter_operations(
    target_count: int,
) -> None:
    legacy, optimized = _adapters()
    legacy_filter_updates = 0
    optimized_filter_updates = 0
    optimized_checkpoint_reuse = 0
    legacy_health_snapshots = 0
    optimized_health_snapshots = 0

    for scan_index, timestamp in enumerate((0.0, 0.2, 0.4)):
        scan = _radar_scan(
            target_count,
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.2,
            scan_id=f"radar-scale-{target_count}-{scan_index}",
        )
        legacy_result = legacy.process_scan_batch(scan)
        optimized_result = optimized.process_scan_batch(scan)
        _assert_semantically_equal(legacy, optimized, legacy_result, optimized_result)
        legacy_filter_updates += legacy_result.summary.replay_filter_update_count
        optimized_filter_updates += optimized_result.summary.replay_filter_update_count
        optimized_checkpoint_reuse += (
            optimized_result.summary.replay_checkpoint_reuse_count
        )
        legacy_health_snapshots += (
            legacy_result.summary.sensor_health_snapshot_build_count
        )
        optimized_health_snapshots += (
            optimized_result.summary.sensor_health_snapshot_build_count
        )

    assert optimized_filter_updates < legacy_filter_updates
    assert optimized_checkpoint_reuse > 0
    assert legacy_health_snapshots == 3 * target_count
    assert optimized_health_snapshots == 3


def test_oosm_insertion_invalidates_only_affected_replay_suffix() -> None:
    legacy, optimized = _adapters()
    scans = (
        _radar_scan(
            1,
            measurement_timestamp=0.0,
            arrival_timestamp=0.0,
            scan_id="oosm-origin",
        ),
        _radar_scan(
            1,
            measurement_timestamp=0.2,
            arrival_timestamp=0.2,
            scan_id="oosm-middle",
        ),
        _radar_scan(
            1,
            measurement_timestamp=0.4,
            arrival_timestamp=0.4,
            scan_id="oosm-later",
        ),
        _radar_scan(
            1,
            measurement_timestamp=0.3,
            arrival_timestamp=0.6,
            scan_id="oosm-inserted",
        ),
    )
    optimized_reuse = 0
    for scan in scans:
        legacy_result = legacy.process_scan_batch(scan)
        optimized_result = optimized.process_scan_batch(scan)
        _assert_semantically_equal(legacy, optimized, legacy_result, optimized_result)
        optimized_reuse += optimized_result.summary.replay_checkpoint_reuse_count

    record = next(iter(optimized.tracks.values()))
    assert [item.observation_id for item in record.replay_checkpoints] == [
        "oosm-middle-target-000",
        "oosm-inserted-target-000",
        "oosm-later-target-000",
    ]
    assert optimized_reuse > 0


def test_pre_checkpoint_oosm_rebuild_matches_uncached_reference() -> None:
    legacy, optimized = _adapters(buffer_horizon=0.5)
    scans = (
        _radar_scan(
            1,
            measurement_timestamp=0.0,
            arrival_timestamp=0.0,
            scan_id="checkpoint-origin",
        ),
        _radar_scan(
            1,
            measurement_timestamp=0.4,
            arrival_timestamp=0.4,
            scan_id="checkpoint-middle",
        ),
        _radar_scan(
            1,
            measurement_timestamp=1.0,
            arrival_timestamp=1.0,
            scan_id="checkpoint-current",
        ),
    )
    for scan in scans:
        legacy_result = legacy.process_scan_batch(scan)
        optimized_result = optimized.process_scan_batch(scan)
        _assert_semantically_equal(legacy, optimized, legacy_result, optimized_result)

    delayed = (
        _acoustic_observation(
            measurement_timestamp=0.2,
            arrival_timestamp=1.3,
            scan_id="checkpoint-pre-oosm",
        ),
    )
    legacy_result = legacy.process_scan_batch(delayed)
    optimized_result = optimized.process_scan_batch(delayed)
    _assert_semantically_equal(legacy, optimized, legacy_result, optimized_result)

    legacy_record = next(iter(legacy.tracks.values()))
    optimized_record = next(iter(optimized.tracks.values()))
    assert optimized_record.checkpoint_active
    assert optimized_record.initial_state.timestamp == pytest.approx(
        legacy_record.initial_state.timestamp
    )
    assert optimized.pre_checkpoint_oosm_replay_count == 1
    assert optimized_result.summary.origin_replay_count >= 1


def test_published_track_arrays_do_not_alias_cached_posterior() -> None:
    _, optimized = _adapters()
    result = optimized.process_scan_batch(
        _radar_scan(
            1,
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
            scan_id="publication-alias",
        )
    )
    expected_state = result.tracks[0].state.copy()
    expected_covariance = result.tracks[0].covariance.copy()

    result.tracks[0].state[:] = -1.0
    result.tracks[0].covariance[:] = -1.0

    republished = optimized.global_tracks()[0]
    np.testing.assert_array_equal(republished.state, expected_state)
    np.testing.assert_array_equal(republished.covariance, expected_covariance)
