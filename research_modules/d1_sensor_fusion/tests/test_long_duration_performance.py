from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from d1_sensor_fusion import (
    SensorObservation,
    audit_fused_track_publications,
    compare_long_duration_variants,
)
from d1_sensor_fusion.observations import radar_covariance_from_range, radar_h


def _write_frozen_input(path: Path) -> None:
    records = []
    for index in range(8):
        measurement_timestamp = float(index)
        arrival_timestamp = measurement_timestamp + 0.1
        state = np.array(
            [800.0 + 4.0 * measurement_timestamp, -200.0, -100.0, 4.0, 0.0, 0.0],
            dtype=float,
        )
        measurement = radar_h(state, np.zeros(3))
        observation = SensorObservation(
            observation_id=f"long-radar-{index}",
            sensor_id="RADAR-LONG",
            modality="radar",
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_id="ned",
            measurement=measurement,
            covariance=radar_covariance_from_range(float(measurement[0])),
            confidence=0.95,
            metadata={
                "sensor_position_ned": np.zeros(3),
                "scan_id": f"long-scan-{index}",
            },
        )
        records.append(
            {
                "sequence": index + 1,
                "topic": "sensor.observations",
                "source": "RADAR-LONG",
                "timestamp": arrival_timestamp,
                "schema_version": "scalable3d-observation-v1",
                "payload": {
                    "batch_id": f"long-scan-{index}",
                    "sensor_id": "RADAR-LONG",
                    "measurement_timestamp": measurement_timestamp,
                    "arrival_timestamp": arrival_timestamp,
                    "measurements": [
                        {
                            "observation_id": observation.observation_id,
                            "sensor_id": observation.sensor_id,
                            "modality": observation.modality,
                            "measurement_timestamp": (
                                observation.measurement_timestamp
                            ),
                            "arrival_timestamp": observation.arrival_timestamp,
                            "frame_id": observation.frame_id,
                            "measurement": observation.measurement.tolist(),
                            "covariance": observation.covariance.tolist(),
                            "classification_hint": (
                                observation.classification_hint
                            ),
                            "confidence": observation.confidence,
                            "metadata": {
                                "sensor_position_ned": [0.0, 0.0, 0.0],
                                "scan_id": f"long-scan-{index}",
                            },
                        }
                    ],
                },
            }
        )

    track_snapshot = [
        {
            "global_track_id": "global_track_001",
            "timestamp": 7.1,
            "state_ned": [828.4, -200.0, -100.0, 4.0, 0.0, 0.0],
            "covariance": np.eye(6).tolist(),
            "track_state": "stable",
        }
    ]
    for offset, (runtime_time, fusion_time, tracks) in enumerate(
        (
            (8.0, 7.1, track_snapshot),
            (8.0, 7.1, track_snapshot),
            (8.1, 7.2, [{**track_snapshot[0], "timestamp": 7.2}]),
        )
    ):
        records.append(
            {
                "sequence": 100 + offset,
                "topic": "modules.d1.fused_tracks",
                "source": "D1",
                "timestamp": runtime_time,
                "schema_version": "d1-scalable3d-fusion-v1",
                "payload": {
                    "timestamp": runtime_time,
                    "batch_id": f"publication-{offset}",
                    "sensor_id": "RADAR-LONG",
                    "track_count": len(tracks),
                    "tracks": tracks,
                    "summary": {"published_at": fusion_time},
                    "observation_lineage": [],
                },
            }
        )
    path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )


def test_frozen_long_duration_benchmark_and_publication_audit(tmp_path: Path) -> None:
    source = tmp_path / "online_observations.jsonl"
    _write_frozen_input(source)

    report = compare_long_duration_variants(source)
    audit = audit_fused_track_publications(source)

    assert report["comparison"]["passed"] is True
    assert report["input"]["released_scan_count"] == 8
    assert report["optimized"]["cumulative_diagnostics"][
        "fixed_lag_rebase_count"
    ] > 0
    assert report["optimized"]["cumulative_diagnostics"][
        "fixed_lag_checkpoint_suffix_reuse_count"
    ] > 0
    assert report["optimized"]["cumulative_diagnostics"][
        "replay_checkpoint_prefix_fast_path_count"
    ] > 0
    assert report["optimized"]["cumulative_diagnostics"][
        "cached_consistency_refresh_count"
    ] > 0
    assert report["comparison"]["acceptance"][
        "trusted_checkpoint_prefix_fast_path_exercised"
    ] is True
    assert report["comparison"]["acceptance"][
        "cached_consistency_refresh_exercised"
    ] is True
    assert (
        report["optimized"]["operation_totals"]["replay_filter_update_count"]
        < report["reference"]["operation_totals"]["replay_filter_update_count"]
    )
    assert audit["publication_count"] == 3
    assert audit["materialized_snapshot_count"] == 3
    assert audit["state_only_count"] == 0
    assert audit["track_record_count"] == 3
    assert audit["unique_runtime_timestamp_count"] == 2
    assert audit["unique_fusion_timestamp_count"] == 2
    assert audit["consecutive_unchanged_snapshot_count"] == 1
    assert audit["coalescible_same_fusion_timestamp_count"] == 1


def test_publication_audit_distinguishes_state_only_and_materialized_records(
    tmp_path: Path,
) -> None:
    source = tmp_path / "mixed_fused_tracks.jsonl"
    records = [
        {
            "sequence": 1,
            "topic": "modules.d1.fused_tracks",
            "source": "D1",
            "timestamp": 1.0,
            "schema_version": "d1-scalable3d-fusion-v1",
            "payload": {
                "tracks_materialized": False,
                "tracks": [],
                "track_count": 0,
                "current_track_count": 2,
                "summary": {"published_at": 0.9},
                "observation_lineage": [{"observation_id": "radar-001"}],
            },
        },
        {
            "sequence": 2,
            "topic": "modules.d1.fused_tracks",
            "source": "D1",
            "timestamp": 1.0,
            "schema_version": "d1-scalable3d-fusion-v1",
            "payload": {
                "tracks_materialized": False,
                "tracks": None,
                "track_count": 0,
                "current_track_count": 2,
                "summary": {"published_at": 0.95},
                "observation_lineage": [{"observation_id": "eo-001"}],
            },
        },
        {
            "sequence": 3,
            "topic": "modules.d1.fused_tracks",
            "source": "D1",
            "timestamp": 1.0,
            "schema_version": "d1-scalable3d-fusion-v1",
            "payload": {
                "tracks_materialized": True,
                "tracks": [
                    {"global_track_id": "global_track_001"},
                    {"global_track_id": "global_track_002"},
                ],
                "track_count": 2,
                "current_track_count": 2,
                "summary": {"published_at": 0.95},
                "observation_lineage": [],
            },
        },
    ]
    source.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )

    audit = audit_fused_track_publications(source)

    assert audit["publication_count"] == 3
    assert audit["materialized_snapshot_count"] == 1
    assert audit["state_only_count"] == 2
    assert audit["track_record_count"] == 2
    assert audit["lineage_record_count"] == 2
    assert audit["unique_track_snapshot_count"] == 1
    assert audit["state_change_publication_count"] == 1
    assert audit["consecutive_unchanged_snapshot_count"] == 0
