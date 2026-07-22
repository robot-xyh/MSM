from __future__ import annotations

import numpy as np

from d2_data_association import Detection3D, Scalable3DTracker


def _detection(
    detection_id: str,
    *,
    state_timestamp: float,
    observation_id: str,
    source_measurement_timestamp: float,
    position_ned: tuple[float, float, float],
    covariance_scale: float = 1.0,
    source_track_id: str | None = None,
) -> Detection3D:
    return Detection3D(
        detection_id=detection_id,
        measurement_timestamp=state_timestamp,
        arrival_timestamp=state_timestamp + 0.02,
        position_ned=np.asarray(position_ned, dtype=float),
        covariance=np.eye(3, dtype=float) * covariance_scale,
        velocity_ned=np.zeros(3, dtype=float),
        velocity_covariance=np.eye(3, dtype=float),
        source_node_id=("d1-center" if source_track_id is not None else None),
        source_track_id=source_track_id,
        metadata={
            "latest_observation_id": observation_id,
            "latest_sensor_id": "radar-center",
            "source_measurement_timestamp": source_measurement_timestamp,
        },
    )


def test_repeated_latest_observation_is_quarantined_and_cannot_confirm() -> None:
    tracker = Scalable3DTracker()
    first = tracker.step(
        [
            _detection(
                "state-0",
                state_timestamp=0.0,
                observation_id="opaque-observation-a",
                source_measurement_timestamp=0.0,
                position_ned=(0.0, 0.0, -100.0),
            )
        ]
    )
    replay_one = tracker.step(
        [
            _detection(
                "state-1",
                state_timestamp=1.0,
                observation_id="opaque-observation-a",
                source_measurement_timestamp=0.0,
                position_ned=(1.0, 0.0, -100.0),
            )
        ]
    )
    replay_two = tracker.step(
        [
            _detection(
                "state-2",
                state_timestamp=2.0,
                observation_id="opaque-observation-a",
                source_measurement_timestamp=0.0,
                position_ned=(2.0, 0.0, -100.0),
            )
        ]
    )

    assert first.metadata["created_track_ids_by_detection"] == {
        "state-0": "GT3D-000001"
    }
    assert replay_one.metadata["fresh_detection_count"] == 0
    assert replay_one.metadata["replay_quarantined_detection_count"] == 1
    assert replay_one.metadata["replay_quarantine_events"][0]["reason"] == (
        "repeated_latest_observation_id"
    )
    assert replay_one.metadata["replay_quarantine_events"][0][
        "replay_generation"
    ] == 1
    assert replay_two.metadata["replay_quarantine_events"][0][
        "replay_generation"
    ] == 2
    assert tracker.tracks["GT3D-000001"].lifecycle_state.value == "dropped"
    assert not tracker.active_tracks()
    assert tracker.summary()["tentative_stale_drop_count"] == 1
    assert tracker.summary()["id_switch_count"] is None
    assert tracker.summary()["id_switch_count_available"] is False


def test_seed_1005_equivalent_stale_branch_drops_and_old_id_survives() -> None:
    tracker = Scalable3DTracker()
    tracker.step(
        [
            _detection(
                "initial",
                state_timestamp=0.0,
                observation_id="opaque-observation-1",
                source_measurement_timestamp=0.0,
                position_ned=(0.0, 0.0, -100.0),
                covariance_scale=100.0,
            )
        ]
    )
    tracker.step(
        [
            _detection(
                "outlier-birth",
                state_timestamp=1.0,
                observation_id="opaque-observation-2",
                source_measurement_timestamp=1.0,
                position_ned=(120.0, 0.0, -100.0),
                covariance_scale=100.0,
            )
        ]
    )
    third = tracker.step(
        [
            _detection(
                "stale-posterior-1",
                state_timestamp=2.0,
                observation_id="opaque-observation-2",
                source_measurement_timestamp=1.0,
                position_ned=(120.0, 0.0, -100.0),
                covariance_scale=100.0,
            ),
            _detection(
                "fresh-reacquisition-1",
                state_timestamp=2.0,
                observation_id="opaque-observation-3",
                source_measurement_timestamp=2.0,
                position_ned=(2.0, 0.0, -100.0),
                covariance_scale=100.0,
            ),
        ]
    )
    fourth = tracker.step(
        [
            _detection(
                "stale-posterior-2",
                state_timestamp=3.0,
                observation_id="opaque-observation-2",
                source_measurement_timestamp=1.0,
                position_ned=(120.0, 0.0, -100.0),
                covariance_scale=100.0,
            ),
            _detection(
                "fresh-reacquisition-2",
                state_timestamp=3.0,
                observation_id="opaque-observation-4",
                source_measurement_timestamp=3.0,
                position_ned=(3.0, 0.0, -100.0),
                covariance_scale=100.0,
            ),
        ]
    )

    assert third.metadata["replay_quarantined_detection_count"] == 1
    assert fourth.metadata["replay_quarantined_detection_count"] == 1
    assert [item.global_track_id for item in tracker.active_tracks()] == [
        "GT3D-000001"
    ]
    assert tracker.tracks["GT3D-000001"].lifecycle_state.value == "confirmed"
    assert tracker.tracks["GT3D-000002"].lifecycle_state.value == "dropped"
    assert tracker.summary()["duplicate_coalescence_count"] == 0
    assert tracker.summary()["tentative_stale_drop_count"] == 1


def test_nearby_independent_targets_are_not_coalesced() -> None:
    tracker = Scalable3DTracker()
    tracker.step(
        [
            _detection(
                "left-0",
                state_timestamp=0.0,
                observation_id="left-observation-0",
                source_measurement_timestamp=0.0,
                position_ned=(0.0, 0.0, -100.0),
                covariance_scale=25.0,
                source_track_id="left-local-track",
            ),
            _detection(
                "right-0",
                state_timestamp=0.0,
                observation_id="right-observation-0",
                source_measurement_timestamp=0.0,
                position_ned=(0.5, 0.0, -100.0),
                covariance_scale=25.0,
                source_track_id="right-local-track",
            ),
        ]
    )
    result = tracker.step(
        [
            _detection(
                "left-1",
                state_timestamp=1.0,
                observation_id="left-observation-1",
                source_measurement_timestamp=1.0,
                position_ned=(1.0, 0.0, -100.0),
                covariance_scale=25.0,
                source_track_id="left-local-track",
            ),
            _detection(
                "right-1",
                state_timestamp=1.0,
                observation_id="right-observation-1",
                source_measurement_timestamp=1.0,
                position_ned=(1.5, 0.0, -100.0),
                covariance_scale=25.0,
                source_track_id="right-local-track",
            ),
        ]
    )

    assert len(tracker.active_tracks()) == 2
    assert all(item.lifecycle_state.value == "confirmed" for item in tracker.active_tracks())
    assert result.metadata["duplicate_coalescence_count"] == 0
    assert tracker.summary()["duplicate_coalescence_count"] == 0


def test_shared_source_requires_covariance_gate_and_uses_stable_survivor() -> None:
    outside = Scalable3DTracker()
    outside.step(
        [
            _detection(
                "outside-a",
                state_timestamp=0.0,
                observation_id="outside-observation-a",
                source_measurement_timestamp=0.0,
                position_ned=(0.0, 0.0, -100.0),
                source_track_id="reused-local-key",
            ),
            _detection(
                "outside-b",
                state_timestamp=0.0,
                observation_id="outside-observation-b",
                source_measurement_timestamp=0.0,
                position_ned=(20.0, 0.0, -100.0),
                source_track_id="reused-local-key",
            ),
        ]
    )
    outside_result = outside.step([], 1.0)
    assert len(outside.active_tracks()) == 2
    assert outside_result.metadata["duplicate_coalescence_count"] == 0

    inside = Scalable3DTracker()
    inside.step(
        [
            _detection(
                "inside-a",
                state_timestamp=0.0,
                observation_id="inside-observation-a",
                source_measurement_timestamp=0.0,
                position_ned=(0.0, 0.0, -100.0),
                covariance_scale=10.0,
                source_track_id="shared-local-key",
            ),
            _detection(
                "inside-b",
                state_timestamp=0.0,
                observation_id="inside-observation-b",
                source_measurement_timestamp=0.0,
                position_ned=(1.0, 0.0, -100.0),
                covariance_scale=10.0,
                source_track_id="shared-local-key",
            ),
        ]
    )
    inside_result = inside.step([], 1.0)

    assert [item.global_track_id for item in inside.active_tracks()] == [
        "GT3D-000001"
    ]
    event = inside_result.metadata["duplicate_coalescence_events"][0]
    assert event["survivor_global_track_id"] == "GT3D-000001"
    assert event["duplicate_global_track_id"] == "GT3D-000002"
    assert event["shared_source_track_count"] == 1
    assert event["online_truth_used"] is False


def test_asynchronous_new_evidence_is_accepted_but_identity_timestamp_conflict_is_not() -> None:
    tracker = Scalable3DTracker()
    tracker.step(
        [
            _detection(
                "first-state",
                state_timestamp=1.0,
                observation_id="opaque-delayed-observation",
                source_measurement_timestamp=0.2,
                position_ned=(0.0, 0.0, -100.0),
            )
        ]
    )
    conflict = tracker.step(
        [
            _detection(
                "conflicting-state",
                state_timestamp=2.0,
                observation_id="opaque-delayed-observation",
                source_measurement_timestamp=0.3,
                position_ned=(1.0, 0.0, -100.0),
            )
        ]
    )
    delayed_new = tracker.step(
        [
            _detection(
                "new-oosm-posterior",
                state_timestamp=3.0,
                observation_id="opaque-new-oosm-observation",
                source_measurement_timestamp=0.1,
                position_ned=(2.0, 0.0, -100.0),
            )
        ]
    )

    assert conflict.metadata["fresh_detection_count"] == 0
    assert conflict.metadata["replay_quarantine_events"][0]["reason"] == (
        "observation_identity_timestamp_conflict"
    )
    assert delayed_new.metadata["fresh_detection_count"] == 1
    assert len(delayed_new.matched_pairs) == 1
    assert tracker.summary()["observation_timestamp_conflict_count"] == 1
