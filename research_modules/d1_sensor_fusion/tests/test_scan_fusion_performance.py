from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from unittest.mock import patch

import numpy as np
import pytest

import d1_sensor_fusion.fusion as fusion_module
from d1_sensor_fusion import (
    FusionStateUpdateResult,
    Scalable3DFusionAdapter,
    TracksNotMaterializedError,
)
from d1_sensor_fusion.fusion import (
    _radar_lower_bound_applicability,
    _radar_lower_bound_rejection_mask,
)
from d1_sensor_fusion.observations import (
    CameraModel,
    acoustic_covariance,
    eo_project,
    radar_covariance_from_range,
    radar_h,
)
from d1_sensor_fusion.types import FusionBatchResult, SensorObservation


_OPERATION_SUMMARY_FIELDS = (
    "history_replay_count",
    "origin_replay_count",
    "finalization_replay_count",
    "state_cache_hit_count",
    "state_cache_miss_count",
    "replay_filter_update_count",
    "replay_checkpoint_reuse_count",
    "global_track_materialization_count",
    "sensor_health_snapshot_build_count",
    "association_candidate_pair_count",
    "association_measurement_model_build_count",
    "association_projection_build_count",
    "association_innovation_solve_count",
    "association_radar_track_state_build_count",
    "association_radar_observation_state_build_count",
)


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


def _eo_scan(
    target_count: int,
    *,
    measurement_timestamp: float,
    arrival_timestamp: float,
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    camera = CameraModel(
        position_ned=np.zeros(3),
        rotation_world_to_camera=np.array(
            [
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [1.0, 0.0, 0.0],
            ],
            dtype=float,
        ),
        fx=900.0,
        fy=900.0,
        cx=640.0,
        cy=360.0,
    )
    observations = []
    for index in range(target_count):
        observations.append(
            SensorObservation(
                observation_id=f"{scan_id}-target-{index:03d}",
                sensor_id="eo-performance",
                modality="eo",
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                frame_id="pixel",
                measurement=eo_project(
                    _target_state(index, measurement_timestamp),
                    camera,
                ),
                covariance=np.diag([4.0, 4.0]),
                classification_hint="unmanned_aircraft",
                confidence=0.95,
                metadata={
                    "camera_id": "eo-performance",
                    "camera_position_ned": camera.position_ned.copy(),
                    "rotation_world_to_camera": (
                        camera.rotation_world_to_camera.copy()
                    ),
                    "fx": camera.fx,
                    "fy": camera.fy,
                    "cx": camera.cx,
                    "cy": camera.cy,
                    "scan_id": scan_id,
                    "coverage_cell": "performance-cell",
                },
            )
        )
    return tuple(observations)


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
    for key in _OPERATION_SUMMARY_FIELDS:
        summary.pop(key, None)
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


def test_default_scan_api_still_returns_materialized_batch_result() -> None:
    adapter = Scalable3DFusionAdapter(association_gate=40.0)

    result = adapter.process_scan_batch(
        _radar_scan(
            3,
            measurement_timestamp=0.0,
            arrival_timestamp=0.1,
            scan_id="default-materialized-scan",
        )
    )

    assert isinstance(result, FusionBatchResult)
    assert result.tracks_materialized is True
    assert len(result.tracks) == 3
    assert result.track_count == result.current_track_count == 3
    assert set(result.to_dict()) == {"tracks", "summary"}
    assert result.summary.global_track_materialization_count == 3


def test_state_only_result_exposes_count_and_fails_closed_on_tracks() -> None:
    adapter = Scalable3DFusionAdapter(association_gate=40.0)

    result = adapter.process_scan_batch(
        _radar_scan(
            3,
            measurement_timestamp=0.0,
            arrival_timestamp=0.1,
            scan_id="state-only-scan",
        ),
        materialize_tracks=False,
    )

    assert isinstance(result, FusionStateUpdateResult)
    assert result.tracks_materialized is False
    assert result.current_track_count == 3
    assert result.state_updated_at == pytest.approx(0.1)
    assert result.summary.global_track_materialization_count == 0
    assert adapter.fusion_performance_diagnostics().global_track_materialization_count == 0
    assert result.to_dict()["tracks"] == []
    assert result.to_dict()["track_count"] == 0
    assert result.to_dict()["current_track_count"] == 3
    with pytest.raises(TracksNotMaterializedError, match="materialize_global_tracks"):
        _ = result.tracks


def test_state_only_scans_then_explicit_snapshot_match_per_scan_publication() -> None:
    scans = (
        _radar_scan(
            3,
            measurement_timestamp=0.0,
            arrival_timestamp=0.1,
            scan_id="deferred-materialization-origin",
        ),
        _radar_scan(
            3,
            measurement_timestamp=3.0,
            arrival_timestamp=3.1,
            scan_id="deferred-materialization-middle",
        ),
        _radar_scan(
            3,
            measurement_timestamp=10.0,
            arrival_timestamp=10.1,
            scan_id="deferred-materialization-fixed-lag",
        ),
        _radar_scan(
            3,
            measurement_timestamp=1.5,
            arrival_timestamp=10.2,
            scan_id="deferred-materialization-pre-checkpoint-oosm",
        ),
    )
    reference = Scalable3DFusionAdapter(
        association_gate=40.0,
        buffer_horizon=6.0,
    )
    deferred = Scalable3DFusionAdapter(
        association_gate=40.0,
        buffer_horizon=6.0,
    )

    reference_result: FusionBatchResult | None = None
    for scan in scans:
        candidate = reference.process_scan_batch(scan)
        assert isinstance(candidate, FusionBatchResult)
        reference_result = candidate

        update = deferred.process_scan_batch(scan, materialize_tracks=False)
        assert isinstance(update, FusionStateUpdateResult)
        assert update.current_track_count == len(reference_result.tracks)
        assert update.summary.global_track_materialization_count == 0
        reference_summary = reference_result.summary.to_dict()
        deferred_summary = update.summary.to_dict()
        for publication_only_field in (
            "global_track_materialization_count",
            "sensor_health_snapshot_build_count",
        ):
            reference_summary.pop(publication_only_field)
            deferred_summary.pop(publication_only_field)
        assert deferred_summary == reference_summary

    assert reference_result is not None
    snapshot = deferred.materialize_global_tracks()

    assert snapshot.tracks_materialized is True
    assert snapshot.track_count == snapshot.current_track_count == 3
    assert len(snapshot.to_dict()["tracks"]) == 3
    assert snapshot.to_dict()["track_count"] == snapshot.to_dict()[
        "current_track_count"
    ]
    assert snapshot.published_at == pytest.approx(reference_result.summary.published_at)
    assert _canonical([track.to_dict() for track in snapshot.tracks]) == _canonical(
        [track.to_dict() for track in reference_result.tracks]
    )
    assert _canonical(
        [item.to_dict() for item in deferred.consistency_evidence_records()]
    ) == _canonical([item.to_dict() for item in reference.consistency_evidence_records()])
    assert deferred.latency_audit_summary().to_dict() == reference.latency_audit_summary().to_dict()
    assert [item.to_dict() for item in deferred.sensor_health_summaries()] == [
        item.to_dict() for item in reference.sensor_health_summaries()
    ]
    assert deferred._processed_lineage_keys == reference._processed_lineage_keys
    assert deferred.pre_checkpoint_oosm_replay_count == (
        reference.pre_checkpoint_oosm_replay_count
    ) == 3

    reference_diagnostics = reference.fusion_performance_diagnostics()
    deferred_diagnostics = deferred.fusion_performance_diagnostics()
    assert reference_diagnostics.global_track_materialization_count == 12
    assert deferred_diagnostics.global_track_materialization_count == 3
    assert snapshot.global_track_materialization_count == 3
    assert deferred_diagnostics.sensor_health_snapshot_build_count == 1
    assert reference_diagnostics.sensor_health_snapshot_build_count == 4
    reference_diagnostics_payload = reference_diagnostics.to_dict()
    deferred_diagnostics_payload = deferred_diagnostics.to_dict()
    for publication_only_field in (
        "global_track_materialization_count",
        "sensor_health_snapshot_build_count",
    ):
        reference_diagnostics_payload.pop(publication_only_field)
        deferred_diagnostics_payload.pop(publication_only_field)
    assert deferred_diagnostics_payload == reference_diagnostics_payload


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


def test_long_fixed_lag_checkpoint_reuse_is_exact_and_bounded() -> None:
    reference = Scalable3DFusionAdapter(
        association_gate=40.0,
        buffer_horizon=0.5,
        direct_checkpoint_state_queries=False,
        fixed_lag_checkpoint_suffix_reuse=False,
        trusted_replay_checkpoint_prefix=False,
        cached_consistency_prefix_refresh=False,
    )
    optimized = Scalable3DFusionAdapter(
        association_gate=40.0,
        buffer_horizon=0.5,
    )
    reference_filter_updates = 0
    optimized_filter_updates = 0
    optimized_checkpoint_reuse = 0

    for scan_index in range(8):
        timestamp = 0.2 * scan_index
        scan = _radar_scan(
            1,
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.1,
            scan_id=f"long-fixed-lag-{scan_index}",
        )
        reference_result = reference.process_scan_batch(scan)
        optimized_result = optimized.process_scan_batch(scan)
        _assert_semantically_equal(
            reference,
            optimized,
            reference_result,
            optimized_result,
        )
        reference_filter_updates += (
            reference_result.summary.replay_filter_update_count
        )
        optimized_filter_updates += (
            optimized_result.summary.replay_filter_update_count
        )
        optimized_checkpoint_reuse += (
            optimized_result.summary.replay_checkpoint_reuse_count
        )

    diagnostics = optimized.fusion_performance_diagnostics()
    assert optimized_filter_updates < reference_filter_updates
    assert optimized_checkpoint_reuse > 0
    assert diagnostics.batch_count == 8
    assert diagnostics.scan_batch_count == 8
    assert diagnostics.observation_count == 8
    assert diagnostics.replay_filter_update_count == optimized_filter_updates
    assert diagnostics.checkpoint_state_query_count > 0
    assert diagnostics.fixed_lag_rebase_count > 0
    assert diagnostics.fixed_lag_checkpoint_suffix_reuse_count > 0
    assert diagnostics.replay_checkpoint_prefix_fast_path_count > 0
    assert diagnostics.cached_consistency_refresh_count > 0
    assert diagnostics.current_track_count == 1
    assert diagnostics.to_dict()["schema_version"] == (
        "d1.fusion_performance_diagnostics.v1"
    )


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


def test_track_materialization_reuses_classification_a95_exactly_once() -> None:
    reference = Scalable3DFusionAdapter(
        radar_association_lower_bound_gate=False,
        reuse_track_classification_a95=False,
    )
    optimized = Scalable3DFusionAdapter(
        radar_association_lower_bound_gate=False,
        reuse_track_classification_a95=True,
    )
    scan = _radar_scan(
        7,
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
        scan_id="single-a95-materialization",
    )
    reference.process_scan_batch(scan, materialize_tracks=False)
    optimized.process_scan_batch(scan, materialize_tracks=False)

    with patch.object(
        fusion_module,
        "covariance_a95",
        wraps=fusion_module.covariance_a95,
    ) as reference_a95:
        reference_tracks = reference.global_tracks()
    with patch.object(
        fusion_module,
        "covariance_a95",
        wraps=fusion_module.covariance_a95,
    ) as optimized_a95:
        optimized_tracks = optimized.global_tracks()

    assert _canonical([item.to_dict() for item in optimized_tracks]) == _canonical(
        [item.to_dict() for item in reference_tracks]
    )
    assert reference_a95.call_count == 2 * len(reference_tracks)
    assert optimized_a95.call_count == len(optimized_tracks)


def _association_adapters(
    **kwargs,
) -> tuple[Scalable3DFusionAdapter, Scalable3DFusionAdapter]:
    common = {"association_gate": 40.0, **kwargs}
    return (
        Scalable3DFusionAdapter(
            **common,
            scan_association_model_cache=False,
        ),
        Scalable3DFusionAdapter(
            **common,
            scan_association_model_cache=True,
        ),
    )


def test_trusted_consistency_counter_refresh_matches_full_validation_per_scan() -> None:
    reference = Scalable3DFusionAdapter(
        association_gate=40.0,
        buffer_horizon=0.5,
        trusted_consistency_counter_refresh=False,
    )
    optimized = Scalable3DFusionAdapter(
        association_gate=40.0,
        buffer_horizon=0.5,
        trusted_consistency_counter_refresh=True,
    )
    scans = (
        _radar_scan(
            4,
            measurement_timestamp=0.0,
            arrival_timestamp=0.1,
            scan_id="consistency-refresh-origin",
        ),
        _eo_scan(
            4,
            measurement_timestamp=0.2,
            arrival_timestamp=0.3,
            scan_id="consistency-refresh-eo",
        ),
        _radar_scan(
            4,
            measurement_timestamp=1.0,
            arrival_timestamp=1.1,
            scan_id="consistency-refresh-fixed-lag",
        ),
        _eo_scan(
            4,
            measurement_timestamp=0.4,
            arrival_timestamp=1.2,
            scan_id="consistency-refresh-oosm",
        ),
    )

    for scan in scans:
        reference_result = reference.process_scan_batch(scan)
        optimized_result = optimized.process_scan_batch(scan)
        _assert_semantically_equal(
            reference,
            optimized,
            reference_result,
            optimized_result,
        )

    reference_diagnostics = reference.fusion_performance_diagnostics().to_dict()
    optimized_diagnostics = optimized.fusion_performance_diagnostics().to_dict()
    assert optimized_diagnostics == reference_diagnostics
    assert optimized_diagnostics["cached_consistency_refresh_count"] > 0


@pytest.mark.parametrize("target_count", [1, 7, 200])
def test_scan_association_model_cache_is_exact_and_reduces_model_builds(
    target_count: int,
) -> None:
    current, optimized = _association_adapters()
    radar_scan = _radar_scan(
        target_count,
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
        scan_id=f"association-radar-{target_count}",
    )
    current_result = current.process_scan_batch(radar_scan)
    optimized_result = optimized.process_scan_batch(radar_scan)
    _assert_semantically_equal(
        current,
        optimized,
        current_result,
        optimized_result,
    )

    eo_scan = _eo_scan(
        target_count,
        measurement_timestamp=0.1,
        arrival_timestamp=0.3,
        scan_id=f"association-eo-{target_count}",
    )
    current_result = current.process_scan_batch(eo_scan)
    optimized_result = optimized.process_scan_batch(eo_scan)
    _assert_semantically_equal(
        current,
        optimized,
        current_result,
        optimized_result,
    )

    pair_count = target_count * target_count
    assert current_result.summary.association_candidate_pair_count == pair_count
    assert optimized_result.summary.association_candidate_pair_count == pair_count
    assert (
        current_result.summary.association_measurement_model_build_count
        == pair_count
    )
    assert (
        optimized_result.summary.association_measurement_model_build_count
        == target_count
    )
    assert current_result.summary.association_projection_build_count == pair_count
    assert optimized_result.summary.association_projection_build_count == target_count
    assert current_result.summary.association_innovation_solve_count == pair_count
    assert optimized_result.summary.association_innovation_solve_count == pair_count


def test_scan_association_model_cache_matches_oosm_and_fixed_lag_reference() -> None:
    current, optimized = _association_adapters(buffer_horizon=0.5)
    scans = (
        _radar_scan(
            1,
            measurement_timestamp=0.0,
            arrival_timestamp=0.0,
            scan_id="association-fixed-lag-origin",
        ),
        _radar_scan(
            1,
            measurement_timestamp=0.4,
            arrival_timestamp=0.4,
            scan_id="association-fixed-lag-middle",
        ),
        _eo_scan(
            1,
            measurement_timestamp=0.3,
            arrival_timestamp=0.6,
            scan_id="association-window-oosm",
        ),
        _radar_scan(
            1,
            measurement_timestamp=1.0,
            arrival_timestamp=1.0,
            scan_id="association-fixed-lag-current",
        ),
        _eo_scan(
            1,
            measurement_timestamp=0.2,
            arrival_timestamp=1.3,
            scan_id="association-pre-checkpoint-oosm",
        ),
    )
    for scan in scans:
        current_result = current.process_scan_batch(scan)
        optimized_result = optimized.process_scan_batch(scan)
        _assert_semantically_equal(
            current,
            optimized,
            current_result,
            optimized_result,
        )

    assert current.pre_checkpoint_oosm_replay_count == 1
    assert optimized.pre_checkpoint_oosm_replay_count == 1


def test_batched_non_radar_innovation_solve_is_exact_and_reduces_pinv_calls() -> None:
    target_count = 200
    reference = Scalable3DFusionAdapter(
        association_gate=40.0,
        batched_non_radar_innovation_solve=False,
    )
    optimized = Scalable3DFusionAdapter(
        association_gate=40.0,
        batched_non_radar_innovation_solve=True,
    )
    radar_scan = _radar_scan(
        target_count,
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
        scan_id="batched-innovation-radar-origin",
    )
    _assert_semantically_equal(
        reference,
        optimized,
        reference.process_scan_batch(radar_scan),
        optimized.process_scan_batch(radar_scan),
    )
    eo_scan = list(
        _eo_scan(
            target_count,
            measurement_timestamp=0.1,
            arrival_timestamp=0.3,
            scan_id="batched-innovation-eo",
        )
    )
    for index, observation in enumerate(eo_scan):
        variance = 4.0 + 0.01 * index
        observation.covariance = np.diag([variance, variance])

    original_pinv = np.linalg.pinv
    with patch.object(
        fusion_module.np.linalg,
        "pinv",
        wraps=original_pinv,
    ) as reference_pinv:
        reference_result = reference.process_scan_batch(eo_scan)
    with patch.object(
        fusion_module.np.linalg,
        "pinv",
        wraps=original_pinv,
    ) as optimized_pinv:
        optimized_result = optimized.process_scan_batch(eo_scan)

    _assert_semantically_equal(
        reference,
        optimized,
        reference_result,
        optimized_result,
    )
    assert optimized_result.summary.to_dict() == reference_result.summary.to_dict()
    assert reference_pinv.call_count == target_count * target_count
    assert optimized_pinv.call_count == 1


def test_batched_non_radar_innovation_solve_falls_back_per_pair() -> None:
    reference = Scalable3DFusionAdapter(
        association_gate=40.0,
        batched_non_radar_innovation_solve=False,
    )
    optimized = Scalable3DFusionAdapter(
        association_gate=40.0,
        batched_non_radar_innovation_solve=True,
    )
    radar_scan = _radar_scan(
        7,
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
        scan_id="batched-fallback-radar-origin",
    )
    _assert_semantically_equal(
        reference,
        optimized,
        reference.process_scan_batch(radar_scan),
        optimized.process_scan_batch(radar_scan),
    )
    eo_scan = _eo_scan(
        7,
        measurement_timestamp=0.1,
        arrival_timestamp=0.3,
        scan_id="batched-fallback-eo",
    )
    original_pinv = np.linalg.pinv

    def reject_batched(values, *args, **kwargs):
        if np.asarray(values).ndim > 2:
            raise np.linalg.LinAlgError("forced batched solve rejection")
        return original_pinv(values, *args, **kwargs)

    reference_result = reference.process_scan_batch(eo_scan)
    with patch.object(
        fusion_module.np.linalg,
        "pinv",
        side_effect=reject_batched,
    ):
        optimized_result = optimized.process_scan_batch(eo_scan)

    _assert_semantically_equal(
        reference,
        optimized,
        reference_result,
        optimized_result,
    )
    assert optimized_result.summary.to_dict() == reference_result.summary.to_dict()


def test_radar_lower_bound_rejects_only_pairs_above_exact_gate() -> None:
    rng = np.random.default_rng(20260722)
    differences = rng.normal(0.0, 300.0, size=(7, 11, 3))
    diagonal = rng.uniform(20.0, 80.0, size=(7, 11, 3))
    innovation_covariances = np.zeros((7, 11, 3, 3), dtype=float)
    diagonal_index = np.arange(3)
    innovation_covariances[..., diagonal_index, diagonal_index] = diagonal
    innovation_covariances[..., 0, 1] = 0.25
    innovation_covariances[..., 1, 0] = 0.25
    innovation_covariances[..., 0, 2] = -0.1
    innovation_covariances[..., 2, 0] = -0.1
    innovation_covariances[..., 1, 2] = 0.2
    innovation_covariances[..., 2, 1] = 0.2

    certified, _ = _radar_lower_bound_applicability(
        innovation_covariances
    )
    gate = 40.0

    rejected = _radar_lower_bound_rejection_mask(
        differences,
        innovation_covariances,
        gate,
    )
    inverses = np.linalg.pinv(innovation_covariances)
    exact_costs = np.einsum(
        "toi,toij,toj->to",
        differences,
        inverses,
        differences,
    )

    assert np.all(certified)
    assert np.any(rejected)
    assert np.all(exact_costs[rejected] > gate)


@pytest.mark.parametrize(
    ("unsafe_covariance", "difference"),
    [
        (
            np.array(
                [[1.0, 2.0, 0.0], [2.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
                dtype=float,
            ),
            np.array([1.0e6, -1.0e6, 0.0], dtype=float),
        ),
        (
            np.diag([1.0e12, 1.0, 1.0e-20]),
            np.array([0.0, 0.0, 1.0e9], dtype=float),
        ),
    ],
    ids=("indefinite_cross_covariance", "pinv_truncated_near_singular"),
)
def test_radar_lower_bound_never_rejects_uncertified_covariance(
    unsafe_covariance: np.ndarray,
    difference: np.ndarray,
) -> None:
    gate = 40.0
    differences = np.broadcast_to(difference, (2, 3, 3)).copy()
    covariances = np.broadcast_to(
        unsafe_covariance,
        (2, 3, 3, 3),
    ).copy()

    certified, _ = _radar_lower_bound_applicability(covariances)
    rejected = _radar_lower_bound_rejection_mask(
        differences,
        covariances,
        association_gate=gate,
    )
    exact_costs = np.einsum(
        "toi,toij,toj->to",
        differences,
        np.linalg.pinv(covariances),
        differences,
    )
    naive_trace_lower_bounds = np.einsum(
        "toi,toi->to",
        differences,
        differences,
    ) / np.trace(covariances, axis1=-2, axis2=-1)

    assert not np.any(certified)
    assert not np.any(rejected)
    assert np.all(exact_costs <= gate)
    assert np.all(naive_trace_lower_bounds > gate)


@pytest.mark.parametrize(
    "unsafe_innovation_covariance",
    [
        np.array(
            [[1.0, 2.0, 0.0], [2.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            dtype=float,
        ),
        np.diag([1.0e12, 1.0, 0.0]),
    ],
    ids=("indefinite_cross_covariance", "pinv_truncated_near_singular"),
)
def test_uncertified_radar_scan_falls_back_to_exact_pinv_semantics(
    unsafe_innovation_covariance: np.ndarray,
) -> None:
    reference = Scalable3DFusionAdapter(
        association_gate=40.0,
        radar_association_lower_bound_gate=False,
    )
    optimized = Scalable3DFusionAdapter(
        association_gate=40.0,
        radar_association_lower_bound_gate=True,
    )
    origin = _radar_scan(
        7,
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
        scan_id="unsafe-radar-origin",
    )
    _assert_semantically_equal(
        reference,
        optimized,
        reference.process_scan_batch(origin),
        optimized.process_scan_batch(origin),
    )

    def install_unsafe_state_query(adapter: Scalable3DFusionAdapter) -> None:
        original_state_at = adapter._state_at

        def unsafe_state_at(record, timestamp):
            state = original_state_at(record, timestamp)
            state.covariance[:3, :3] = unsafe_innovation_covariance
            return state

        adapter._state_at = unsafe_state_at

    install_unsafe_state_query(reference)
    install_unsafe_state_query(optimized)
    original_radar_state = fusion_module.radar_state_from_observation

    def radar_state_with_zero_covariance(observation, config):
        state, covariance = original_radar_state(observation, config)
        return state, np.zeros_like(covariance)

    update = _radar_scan(
        7,
        measurement_timestamp=0.1,
        arrival_timestamp=0.3,
        scan_id="unsafe-radar-update",
    )
    with patch.object(
        fusion_module,
        "radar_state_from_observation",
        side_effect=radar_state_with_zero_covariance,
    ):
        reference_result = reference.process_scan_batch(update)
        optimized_result = optimized.process_scan_batch(update)

    _assert_semantically_equal(
        reference,
        optimized,
        reference_result,
        optimized_result,
    )
    pair_count = len(origin) * len(update)
    assert reference_result.summary.association_innovation_solve_count == pair_count
    assert optimized_result.summary.association_innovation_solve_count == pair_count


def test_radar_lower_bound_preserves_scan_semantics_and_reduces_exact_solves() -> None:
    reference = Scalable3DFusionAdapter(
        association_gate=40.0,
        radar_association_lower_bound_gate=False,
    )
    optimized = Scalable3DFusionAdapter(
        association_gate=40.0,
        radar_association_lower_bound_gate=True,
    )
    origin = _radar_scan(
        40,
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
        scan_id="radar-lower-bound-origin",
    )
    _assert_semantically_equal(
        reference,
        optimized,
        reference.process_scan_batch(origin),
        optimized.process_scan_batch(origin),
    )

    update = _radar_scan(
        40,
        measurement_timestamp=0.1,
        arrival_timestamp=0.3,
        scan_id="radar-lower-bound-update",
    )
    reference_result = reference.process_scan_batch(update)
    optimized_result = optimized.process_scan_batch(update)
    _assert_semantically_equal(
        reference,
        optimized,
        reference_result,
        optimized_result,
    )

    pair_count = len(origin) * len(update)
    assert reference_result.summary.association_candidate_pair_count == pair_count
    assert optimized_result.summary.association_candidate_pair_count == pair_count
    assert reference_result.summary.association_innovation_solve_count == pair_count
    assert 0 < optimized_result.summary.association_innovation_solve_count < pair_count
