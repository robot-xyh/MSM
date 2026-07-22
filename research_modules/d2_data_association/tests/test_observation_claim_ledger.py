from __future__ import annotations

import numpy as np
import pytest

from d2_data_association import (
    OBSERVATION_CLAIM_LEDGER_SCHEMA_VERSION,
    ObservationClaimLedgerConfig,
    Scalable3DTracker,
)
from d2_data_association.scalable_3d_models import Detection3D


def _detection(
    target_index: int,
    frame_index: int,
    timestamp: float,
    *,
    observation_id: str | None = None,
    source_measurement_timestamp: float | None = None,
) -> Detection3D:
    metadata: dict[str, object] = {
        "latest_observation_id": (
            observation_id
            if observation_id is not None
            else f"observation-{frame_index:06d}-{target_index:04d}"
        ),
        "latest_sensor_id": "radar-ledger-test",
    }
    if source_measurement_timestamp is not None:
        metadata["source_measurement_timestamp"] = source_measurement_timestamp
    return Detection3D(
        detection_id=f"detection-{frame_index:06d}-{target_index:04d}",
        measurement_timestamp=timestamp,
        arrival_timestamp=timestamp + 0.01,
        position_ned=np.asarray(
            [timestamp, target_index * 5.0, -100.0],
            dtype=float,
        ),
        covariance=np.eye(3, dtype=float) * 0.05,
        velocity_ned=np.asarray([1.0, 0.0, 0.0], dtype=float),
        velocity_covariance=np.eye(3, dtype=float) * 0.05,
        source_node_id="d1-ledger-test",
        source_track_id=f"source-track-{target_index:04d}",
        metadata=metadata,
    )


def test_claim_policy_is_versioned_and_validated() -> None:
    config = ObservationClaimLedgerConfig(
        config_version="test-policy-v3",
        retention_seconds=2.0,
        max_count=17,
        max_lateness_seconds=3.0,
    )

    assert config.protected_window_seconds == 3.0
    assert config.safe_watermark(10.0) == 7.0
    assert config.admission_watermark(10.0) == 7.0
    assert config.to_dict() == {
        "schema_version": OBSERVATION_CLAIM_LEDGER_SCHEMA_VERSION,
        "config_version": "test-policy-v3",
        "retention_seconds": 2.0,
        "max_count": 17,
        "max_lateness_seconds": 3.0,
        "protected_window_seconds": 3.0,
    }

    with pytest.raises(ValueError, match="max_count"):
        ObservationClaimLedgerConfig(max_count=0)
    with pytest.raises(ValueError, match="retention_seconds"):
        ObservationClaimLedgerConfig(retention_seconds=-1.0)


def test_evicted_old_evidence_is_rejected_by_safe_watermark_without_rebirth() -> None:
    tracker = Scalable3DTracker(
        observation_claim_config=ObservationClaimLedgerConfig(
            config_version="short-window-test-v1",
            retention_seconds=1.0,
            max_count=16,
            max_lateness_seconds=0.25,
        )
    )
    tracker.step(
        [
            _detection(
                0,
                0,
                0.0,
                observation_id="retired-observation",
                source_measurement_timestamp=0.0,
            )
        ]
    )
    result = tracker.step(
        [
            _detection(
                0,
                20,
                2.0,
                observation_id="retired-observation",
                source_measurement_timestamp=0.0,
            ),
            _detection(
                10,
                20,
                2.0,
                observation_id="legitimate-new-observation",
                source_measurement_timestamp=2.0,
            ),
        ]
    )

    assert result.metadata["fresh_detection_count"] == 1
    assert result.metadata["replay_quarantined_detection_count"] == 1
    assert result.metadata["observation_rejection_reason_counts"] == {
        "observation_measurement_too_old": 1
    }
    assert result.metadata["created_track_ids_by_detection"] == {
        "detection-000020-0010": "GT3D-000002"
    }
    assert tracker.tracks["GT3D-000001"].hits == 1
    assert tracker.tracks["GT3D-000002"].hits == 1
    ledger = tracker.summary()["observation_claim_ledger"]
    assert ledger["evicted_count"] == 1
    assert ledger["too_old_rejection_count"] == 1
    assert ledger["tombstone_count"] == 0
    assert ledger["anti_replay_mode"] == (
        "trusted_measurement_time_safe_watermark"
    )


def test_ledger_overflow_rejects_new_evidence_without_exceeding_bound() -> None:
    tracker = Scalable3DTracker(
        observation_claim_config=ObservationClaimLedgerConfig(
            retention_seconds=100.0,
            max_count=2,
            max_lateness_seconds=100.0,
        )
    )
    result = tracker.step(
        [
            _detection(
                target_index,
                0,
                0.0,
                source_measurement_timestamp=0.0,
            )
            for target_index in range(3)
        ]
    )

    assert result.metadata["fresh_detection_count"] == 2
    assert len(result.metadata["created_track_ids_by_detection"]) == 2
    assert result.metadata["observation_rejection_reason_counts"] == {
        "observation_claim_ledger_overflow": 1
    }
    ledger = tracker.summary()["observation_claim_ledger"]
    assert ledger["current_count"] == 2
    assert ledger["peak_count"] == 2
    assert ledger["overflow_rejection_count"] == 1


def test_max_lateness_rejects_old_new_key_before_retention_eviction() -> None:
    tracker = Scalable3DTracker(
        observation_claim_config=ObservationClaimLedgerConfig(
            retention_seconds=10.0,
            max_count=16,
            max_lateness_seconds=1.0,
        )
    )
    tracker.step(
        [_detection(0, 0, 0.0, source_measurement_timestamp=0.0)]
    )
    result = tracker.step(
        [
            _detection(
                1,
                50,
                5.0,
                observation_id="unseen-but-too-old",
                source_measurement_timestamp=3.0,
            )
        ]
    )

    assert result.metadata["fresh_detection_count"] == 0
    assert result.metadata["observation_rejection_reason_counts"] == {
        "observation_measurement_too_old": 1
    }
    ledger = result.metadata["observation_claim_ledger"]
    assert ledger["evicted_count"] == 0
    assert ledger["current_count"] == 1
    assert ledger["safe_watermark_measurement_timestamp"] == -5.0
    assert ledger["admission_watermark_measurement_timestamp"] == 4.0


def test_same_key_timestamp_conflict_remains_distinct_from_too_old() -> None:
    tracker = Scalable3DTracker(
        observation_claim_config=ObservationClaimLedgerConfig(
            retention_seconds=10.0,
            max_count=16,
            max_lateness_seconds=1.0,
        )
    )
    result = tracker.step(
        [
            _detection(
                0,
                50,
                5.0,
                observation_id="conflicting-old-key",
                source_measurement_timestamp=2.0,
            ),
            _detection(
                1,
                50,
                5.0,
                observation_id="conflicting-old-key",
                source_measurement_timestamp=3.0,
            ),
        ]
    )

    assert result.metadata["fresh_detection_count"] == 0
    assert result.metadata["observation_rejection_reason_counts"] == {
        "observation_identity_timestamp_conflict": 2
    }
    ledger = result.metadata["observation_claim_ledger"]
    assert ledger["current_count"] == 0
    assert ledger["too_old_rejection_count"] == 0
    assert tracker.summary()["observation_timestamp_conflict_count"] == 2


def test_undated_claims_fail_closed_at_capacity_and_remain_bounded() -> None:
    tracker = Scalable3DTracker(
        observation_claim_config=ObservationClaimLedgerConfig(
            retention_seconds=0.1,
            max_count=3,
            max_lateness_seconds=0.1,
        )
    )
    for frame_index in range(8):
        tracker.step(
            [
                _detection(
                    0,
                    frame_index,
                    float(frame_index),
                    source_measurement_timestamp=None,
                )
            ]
        )

    ledger = tracker.summary()["observation_claim_ledger"]
    assert ledger["current_count"] == 3
    assert ledger["peak_count"] == 3
    assert ledger["undated_non_evictable_count"] == 3
    assert ledger["evicted_count"] == 0
    assert ledger["overflow_rejection_count"] == 5


@pytest.mark.parametrize(
    ("target_count", "frame_count"),
    [(5, 500), (40, 200)],
)
def test_long_dynamic_n_loops_keep_claim_memory_bounded(
    target_count: int,
    frame_count: int,
) -> None:
    max_count = target_count * 6
    tracker = Scalable3DTracker(
        observation_claim_config=ObservationClaimLedgerConfig(
            config_version=f"long-loop-{target_count}-target-v1",
            retention_seconds=0.4,
            max_count=max_count,
            max_lateness_seconds=0.2,
        ),
        frame_log_limit=32,
        track_history_limit=8,
    )
    for frame_index in range(frame_count):
        timestamp = frame_index * 0.1
        tracker.step(
            [
                _detection(
                    target_index,
                    frame_index,
                    timestamp,
                    source_measurement_timestamp=timestamp,
                )
                for target_index in range(target_count)
            ],
            timestamp,
        )

    summary = tracker.summary()
    ledger = summary["observation_claim_ledger"]
    assert summary["active_track_count"] == target_count
    assert ledger["current_count"] <= max_count
    assert ledger["peak_count"] <= max_count
    assert ledger["eviction_index_count"] <= max_count
    assert ledger["track_observation_key_count"] <= max_count
    assert ledger["evicted_count"] > 0
    assert ledger["overflow_rejection_count"] == 0
    assert ledger["online_truth_used"] is False
    assert summary["global_track_id_owner"] == "D2_center"
    assert summary["id_switch_count"] is None
    assert summary["id_switch_count_available"] is False


def test_coalescence_moves_reverse_claim_index_without_leaking_duplicate_track() -> None:
    tracker = Scalable3DTracker()
    tracker.step(
        [
            _detection(
                0,
                0,
                0.0,
                observation_id="claim-left",
                source_measurement_timestamp=0.0,
            ),
            Detection3D(
                detection_id="duplicate-source-birth",
                measurement_timestamp=0.0,
                arrival_timestamp=0.01,
                position_ned=np.asarray([0.1, 0.0, -100.0]),
                covariance=np.eye(3, dtype=float) * 10.0,
                velocity_ned=np.asarray([1.0, 0.0, 0.0]),
                velocity_covariance=np.eye(3, dtype=float),
                source_node_id="d1-ledger-test",
                source_track_id="source-track-0000",
                metadata={
                    "latest_observation_id": "claim-right",
                    "latest_sensor_id": "radar-ledger-test",
                    "source_measurement_timestamp": 0.0,
                },
            ),
        ]
    )
    result = tracker.step([], 1.0)

    assert result.metadata["duplicate_coalescence_count"] == 1
    ledger = tracker.summary()["observation_claim_ledger"]
    assert ledger["current_count"] == 2
    assert ledger["track_observation_key_count"] == 2
    assert ledger["track_observation_index_track_count"] == 1
