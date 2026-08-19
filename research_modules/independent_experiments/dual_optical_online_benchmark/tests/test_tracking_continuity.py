from __future__ import annotations

import json
import math

import numpy as np
import pytest

from dual_optical_40target.core import RayObservation
import dual_optical_online_benchmark.tracking as tracking_module
from dual_optical_online_benchmark.tracking import (
    SharedBearingTracker,
    SharedTrackerConfig,
    _ReconnectCost,
)


def _direction(azimuth_deg: float, elevation_deg: float = 0.0):
    azimuth = math.radians(azimuth_deg)
    elevation = math.radians(elevation_deg)
    return (
        math.cos(elevation) * math.cos(azimuth),
        math.cos(elevation) * math.sin(azimuth),
        -math.sin(elevation),
    )


def _target_azimuth(timestamp: float, cross_track_m: float = 0.0) -> float:
    target_x = 2000.0 - 50.0 * timestamp
    relative_y = 1000.0 + cross_track_m
    return math.degrees(math.atan2(relative_y, target_x))


def _observation(
    uid: str,
    sweep: int,
    timestamp: float,
    *,
    cross_track_m: float = 0.0,
) -> RayObservation:
    return RayObservation(
        detection_uid=uid,
        camera_id="Optical_A",
        frame_index=sweep,
        sweep_index=sweep,
        timestamp=timestamp,
        origin_ned=(0.0, -1000.0, -100.0),
        direction_ned=_direction(_target_azimuth(timestamp, cross_track_m)),
        bbox_xyxy=(0.0, 0.0, 1.0, 1.0),
        camera_yaw_deg=0.0,
        camera_pitch_deg=0.0,
        focal_length_px=25000.0,
    )


def _update(
    tracker: SharedBearingTracker,
    sweep: int,
    observations: list[RayObservation],
) -> None:
    tracker.update_sweep(
        sweep,
        observations,
        {item.detection_uid: 1.0 for item in observations},
    )


def _confirmed_then_dormant_tracker() -> tuple[SharedBearingTracker, str]:
    config = SharedTrackerConfig(maximum_missed_sweeps=1)
    tracker = SharedBearingTracker("Optical_A", config)
    _update(tracker, 0, [_observation("anonymous-0", 0, 0.5)])
    _update(tracker, 1, [_observation("anonymous-1", 1, 2.5)])
    old_id = tracker.tracks[0].track_id
    _update(tracker, 2, [])
    _update(tracker, 3, [])
    return tracker, old_id


def test_dormant_track_is_not_published_but_state_is_propagated() -> None:
    tracker, old_id = _confirmed_then_dormant_tracker()

    assert tracker.tracks == ()
    assert len(tracker.dormant_tracks) == 1
    dormant = tracker.dormant_tracks[0]
    assert dormant.track_id == old_id
    first_timestamp = dormant.last_timestamp
    first_covariance = dormant.covariance.copy()

    _update(tracker, 4, [])

    dormant = tracker.dormant_tracks[0]
    assert dormant.last_timestamp > first_timestamp
    assert not np.array_equal(dormant.covariance, first_covariance)
    assert tracker.tracks == ()


def test_bidirectional_reconnection_preserves_local_track_id() -> None:
    tracker, old_id = _confirmed_then_dormant_tracker()

    _update(tracker, 4, [_observation("anonymous-4", 4, 8.5)])
    assert len(tracker.tracks) == 1
    assert tracker.tracks[0].track_id != old_id
    _update(tracker, 5, [_observation("anonymous-5", 5, 10.5)])

    assert len(tracker.tracks) == 1
    reactivated = tracker.tracks[0]
    assert reactivated.track_id == old_id
    assert reactivated.lifecycle_state == "confirmed"
    assert reactivated.reconnection_boundaries == [2]
    assert any(event.event_type == "tracklet_reconnected" for event in tracker.events)


def test_duplicate_anonymous_detection_is_rejected() -> None:
    tracker = SharedBearingTracker("Optical_A", SharedTrackerConfig())
    repeated = _observation("same-anonymous-uid", 0, 0.5)

    with pytest.raises(ValueError, match="cannot be used twice"):
        tracker.update_sweep(
            0,
            [repeated, repeated],
            {repeated.detection_uid: 1.0},
        )


def test_oversized_ambiguous_component_fails_closed(monkeypatch) -> None:
    config = SharedTrackerConfig(
        maximum_missed_sweeps=1,
        maximum_ambiguous_edges=1,
    )
    tracker = SharedBearingTracker("Optical_A", config)
    _update(tracker, 0, [
        _observation("old-a0", 0, 0.5, cross_track_m=-100.0),
        _observation("old-b0", 0, 0.5, cross_track_m=100.0),
    ])
    _update(tracker, 1, [
        _observation("old-a1", 1, 2.5, cross_track_m=-100.0),
        _observation("old-b1", 1, 2.5, cross_track_m=100.0),
    ])
    _update(tracker, 2, [])
    _update(tracker, 3, [])
    assert len(tracker.dormant_tracks) == 2

    def all_to_all(dormant, tracklets, config):
        del config
        return {
            (row, column): _ReconnectCost(1.0, 1.0, 0.1, 0.1, 0.0, 2, 0.0, 0.0)
            for row in range(len(dormant))
            for column in range(len(tracklets))
        }

    monkeypatch.setattr(
        tracking_module, "_sparse_reconnection_edges", all_to_all
    )
    _update(tracker, 4, [
        _observation("new-a0", 4, 8.5, cross_track_m=-100.0),
        _observation("new-b0", 4, 8.5, cross_track_m=100.0),
    ])
    _update(tracker, 5, [
        _observation("new-a1", 5, 10.5, cross_track_m=-100.0),
        _observation("new-b1", 5, 10.5, cross_track_m=100.0),
    ])

    assert len(tracker.dormant_tracks) == 2
    assert len(tracker.tracks) == 2
    assert not any(
        event.event_type == "tracklet_reconnected" for event in tracker.events
    )
    assert any(
        event.event_type == "hypothesis_fail_closed" for event in tracker.events
    )


def test_bounded_local_hypotheses_wait_for_the_configured_window(monkeypatch) -> None:
    config = SharedTrackerConfig(
        maximum_missed_sweeps=1,
        local_k_best=3,
        local_hypothesis_window_sweeps=2,
    )
    tracker = SharedBearingTracker("Optical_A", config)
    for sweep, timestamp in ((0, 0.5), (1, 2.5)):
        _update(tracker, sweep, [
            _observation(f"old-a{sweep}", sweep, timestamp, cross_track_m=-100.0),
            _observation(f"old-b{sweep}", sweep, timestamp, cross_track_m=100.0),
        ])
    old_ids = {track.track_id for track in tracker.tracks}
    _update(tracker, 2, [])
    _update(tracker, 3, [])

    def ambiguous_edges(dormant, tracklets, config):
        del config
        return {
            (row, column): _ReconnectCost(
                1.0 if row == column else 2.0,
                1.0,
                0.1,
                0.1,
                0.0,
                2,
                0.0,
                0.0,
            )
            for row in range(len(dormant))
            for column in range(len(tracklets))
        }

    monkeypatch.setattr(
        tracking_module, "_sparse_reconnection_edges", ambiguous_edges
    )
    for sweep, timestamp in ((4, 8.5), (5, 10.5)):
        _update(tracker, sweep, [
            _observation(f"new-a{sweep}", sweep, timestamp, cross_track_m=-100.0),
            _observation(f"new-b{sweep}", sweep, timestamp, cross_track_m=100.0),
        ])
    assert len(tracker.dormant_tracks) == 2
    assert not any(
        event.event_type == "tracklet_reconnected" for event in tracker.events
    )
    assert tracker.hypothesis_count == 3

    _update(tracker, 6, [
        _observation("new-a6", 6, 12.5, cross_track_m=-100.0),
        _observation("new-b6", 6, 12.5, cross_track_m=100.0),
    ])

    assert tracker.dormant_tracks == ()
    assert {track.track_id for track in tracker.tracks} == old_ids
    assert sum(
        event.event_type == "tracklet_reconnected" for event in tracker.events
    ) == 2


def test_tracker_events_do_not_copy_source_uids_or_truth_labels() -> None:
    tracker, _ = _confirmed_then_dormant_tracker()
    rendered = json.dumps(
        [event.__dict__ for event in tracker.events], sort_keys=True
    )

    assert "anonymous-0" not in rendered
    assert "anonymous-1" not in rendered
    assert "truth_id" not in rendered


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"dormant_retention_sweeps": 2}, "must be 3 or 4"),
        ({"minimum_tracklet_hits": 1}, "at least two"),
        ({"local_k_best": 4}, "must be 3 or 5"),
        ({"local_hypothesis_window_sweeps": 1}, "must be 2 or 3"),
        ({"maximum_ambiguous_tracks": 9}, "at most eight"),
        ({"maximum_ambiguous_scanlets": 9}, "at most eight"),
        ({"maximum_ambiguous_edges": 33}, "at most 32"),
    ],
)
def test_continuity_parameters_fail_closed(values: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        SharedTrackerConfig(**values)


@pytest.mark.parametrize("retention", [3, 4])
@pytest.mark.parametrize("local_k", [3, 5])
@pytest.mark.parametrize("window", [2, 3])
def test_approved_continuity_profiles_are_supported(
    retention: int,
    local_k: int,
    window: int,
) -> None:
    config = SharedTrackerConfig(
        dormant_retention_sweeps=retention,
        local_k_best=local_k,
        local_hypothesis_window_sweeps=window,
    )
    assert config.dormant_retention_sweeps == retention
    assert config.local_k_best == local_k
    assert config.local_hypothesis_window_sweeps == window
