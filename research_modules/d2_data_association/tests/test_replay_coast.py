from __future__ import annotations

import numpy as np
import pytest

from d2_data_association import (
    REPLAY_COAST_POLICY_SCHEMA_VERSION,
    ObservationClaimLedgerConfig,
    ReplayCoastConfig,
    Scalable3DTracker,
)
from d2_data_association.scalable_3d_models import Detection3D


def _posterior(
    target_index: int,
    frame_index: int,
    timestamp: float,
    *,
    observation_id: str,
    source_measurement_timestamp: float,
    position_ned: np.ndarray | None = None,
) -> Detection3D:
    return Detection3D(
        detection_id=f"posterior-{frame_index:05d}-{target_index:03d}",
        measurement_timestamp=timestamp,
        arrival_timestamp=timestamp + 0.01,
        position_ned=(
            np.asarray([timestamp, target_index * 20.0, -100.0], dtype=float)
            if position_ned is None
            else np.asarray(position_ned, dtype=float)
        ),
        covariance=np.eye(3, dtype=float) * 0.1,
        velocity_ned=np.asarray([1.0, 0.0, 0.0], dtype=float),
        velocity_covariance=np.eye(3, dtype=float) * 0.1,
        source_node_id="d1-full-posterior-test",
        source_track_id=f"d1-track-{target_index:03d}",
        metadata={
            "latest_observation_id": observation_id,
            "latest_sensor_id": "radar-replay-coast-test",
            "source_measurement_timestamp": source_measurement_timestamp,
        },
    )


def test_replay_coast_policy_is_versioned_and_validated() -> None:
    config = ReplayCoastConfig(
        config_version="replay-coast-fixture-v2",
        grace_seconds=0.75,
    )

    assert config.to_dict() == {
        "schema_version": REPLAY_COAST_POLICY_SCHEMA_VERSION,
        "config_version": "replay-coast-fixture-v2",
        "grace_seconds": 0.75,
        "clock_source": "track_last_fresh_update_time",
        "refresh_on_replay": False,
    }
    with pytest.raises(ValueError, match="grace_seconds"):
        ReplayCoastConfig(grace_seconds=-0.01)


def test_repeated_full_posterior_coasts_without_hit_birth_or_measurement_update() -> None:
    tracker = Scalable3DTracker(
        confirmation_hits=1,
        replay_coast_config=ReplayCoastConfig(grace_seconds=0.5),
    )
    first = tracker.step(
        [
            _posterior(
                0,
                0,
                0.0,
                observation_id="radar-observation-0",
                source_measurement_timestamp=0.0,
            )
        ]
    )
    track_id = first.metadata["created_track_ids_by_detection"][
        "posterior-00000-000"
    ]

    replay_one = tracker.step(
        [
            _posterior(
                0,
                1,
                0.1,
                observation_id="radar-observation-0",
                source_measurement_timestamp=0.0,
                position_ned=np.asarray([100.0, 0.0, -100.0]),
            )
        ]
    )
    replay_two = tracker.step(
        [
            _posterior(
                0,
                2,
                0.4,
                observation_id="radar-observation-0",
                source_measurement_timestamp=0.0,
                position_ned=np.asarray([200.0, 0.0, -100.0]),
            )
        ]
    )

    track = tracker.tracks[track_id]
    assert replay_one.metadata["replay_coast_count"] == 1
    assert replay_two.metadata["replay_coast_count"] == 1
    assert replay_two.metadata["replay_coast_reason_counts"] == {
        "repeated_latest_observation_id": 1
    }
    assert replay_two.metadata["created_track_ids_by_detection"] == {}
    assert replay_two.matched_pairs == []
    assert replay_two.metadata["missed_track_ids"] == []
    assert track.hits == 1
    assert track.misses == 0
    assert track.last_update_time == 0.0
    assert track.last_detection_id == "posterior-00000-000"
    assert track.position_ned[0] == pytest.approx(0.4)
    assert track.lifecycle_state.value == "confirmed"
    assert tracker.summary()["replay_coast_count"] == 2


def test_replay_after_grace_resumes_miss_and_lost_transition() -> None:
    tracker = Scalable3DTracker(
        confirmation_hits=1,
        lost_miss_threshold=1,
        drop_miss_threshold=3,
        replay_coast_config=ReplayCoastConfig(grace_seconds=0.25),
    )
    first = tracker.step(
        [
            _posterior(
                0,
                0,
                0.0,
                observation_id="radar-observation-timeout",
                source_measurement_timestamp=0.0,
            )
        ]
    )
    track_id = next(iter(first.metadata["created_track_ids_by_detection"].values()))
    within_grace = tracker.step(
        [
            _posterior(
                0,
                1,
                0.2,
                observation_id="radar-observation-timeout",
                source_measurement_timestamp=0.0,
            )
        ]
    )
    expired = tracker.step(
        [
            _posterior(
                0,
                2,
                0.3,
                observation_id="radar-observation-timeout",
                source_measurement_timestamp=0.0,
            )
        ]
    )

    assert within_grace.metadata["replay_coast_count"] == 1
    assert expired.metadata["replay_coast_count"] == 0
    assert expired.metadata["missed_track_ids"] == [track_id]
    assert tracker.tracks[track_id].misses == 1
    assert tracker.tracks[track_id].last_update_time == 0.0
    assert tracker.tracks[track_id].lifecycle_state.value == "lost"


def test_timestamp_conflict_never_receives_replay_coast() -> None:
    tracker = Scalable3DTracker(
        confirmation_hits=1,
        lost_miss_threshold=1,
        drop_miss_threshold=3,
        replay_coast_config=ReplayCoastConfig(grace_seconds=1.0),
    )
    first = tracker.step(
        [
            _posterior(
                0,
                0,
                0.0,
                observation_id="radar-observation-conflict",
                source_measurement_timestamp=0.0,
            )
        ]
    )
    track_id = next(iter(first.metadata["created_track_ids_by_detection"].values()))
    conflict = tracker.step(
        [
            _posterior(
                0,
                1,
                0.1,
                observation_id="radar-observation-conflict",
                source_measurement_timestamp=0.05,
            )
        ]
    )

    assert conflict.metadata["observation_rejection_reason_counts"] == {
        "observation_identity_timestamp_conflict": 1
    }
    assert conflict.metadata["replay_coast_count"] == 0
    assert conflict.metadata["missed_track_ids"] == [track_id]
    assert tracker.tracks[track_id].lifecycle_state.value == "lost"


def test_long_full_posterior_loop_is_bounded_and_requires_periodic_fresh_updates() -> None:
    target_count = 12
    frame_count = 200
    radar_period_frames = 5
    max_claims = target_count * 12
    tracker = Scalable3DTracker(
        confirmation_hits=2,
        observation_claim_config=ObservationClaimLedgerConfig(
            config_version="replay-coast-long-loop-ledger-v1",
            retention_seconds=2.0,
            max_count=max_claims,
            max_lateness_seconds=0.5,
        ),
        replay_coast_config=ReplayCoastConfig(
            config_version="replay-coast-long-loop-v1",
            grace_seconds=0.45,
        ),
        frame_log_limit=32,
        track_history_limit=8,
    )

    for frame_index in range(frame_count):
        timestamp = frame_index * 0.1
        observation_epoch = frame_index - frame_index % radar_period_frames
        source_timestamp = observation_epoch * 0.1
        tracker.step(
            [
                _posterior(
                    target_index,
                    frame_index,
                    timestamp,
                    observation_id=(
                        f"radar-{observation_epoch:05d}-{target_index:03d}"
                    ),
                    source_measurement_timestamp=source_timestamp,
                )
                for target_index in range(target_count)
            ],
            timestamp,
        )

    summary = tracker.summary()
    ledger = summary["observation_claim_ledger"]
    assert summary["active_track_count"] == target_count
    assert summary["lost_count"] == 0
    assert summary["drop_count"] == 0
    assert summary["replay_coast_count"] == (
        target_count
        * (frame_count - frame_count // radar_period_frames)
    )
    assert summary["replay_coast_reason_counts"] == {
        "repeated_latest_observation_id": summary["replay_coast_count"]
    }
    assert all(track.misses == 0 for track in tracker.active_tracks())
    assert all(
        track.hits == frame_count // radar_period_frames
        for track in tracker.active_tracks()
    )
    assert ledger["current_count"] <= max_claims
    assert ledger["peak_count"] <= max_claims
    assert ledger["eviction_index_count"] <= max_claims
    assert ledger["overflow_rejection_count"] == 0
    assert summary["replay_coast_config"]["config_version"] == (
        "replay-coast-long-loop-v1"
    )
    assert summary["replay_coast_config"]["refresh_on_replay"] is False
    assert summary["id_switch_count_available"] is False
