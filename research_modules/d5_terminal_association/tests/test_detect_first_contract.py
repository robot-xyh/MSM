from __future__ import annotations

import json

import numpy as np

from d5_terminal_association import (
    AssociationConfig,
    Assignment,
    CameraModel,
    GlobalTrack,
    LocalVisualTrack,
    TerminalAssociator,
    TerminalObservationBus,
    associate_tracks_to_detections_geometrically,
    local_visual_tracks_from_sim_detections,
)


def _camera() -> CameraModel:
    return CameraModel(
        K=np.array(
            [
                [100.0, 0.0, 320.0],
                [0.0, 100.0, 240.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        ),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
        measurement_cov=np.diag([4.0, 4.0]),
    )


def _global(global_track_id: str, x_m: float = 0.0) -> GlobalTrack:
    return GlobalTrack(
        global_track_id=global_track_id,
        position=np.array([x_m, 0.0, 20.0], dtype=float),
        covariance=np.diag([0.02, 0.02, 0.02]),
        timestamp=10.0,
    )


def _measured(local_track_id: str, timestamp: float, center_x: float = 320.0) -> LocalVisualTrack:
    return LocalVisualTrack(
        local_track_id=local_track_id,
        center_px=np.array([center_x, 240.0], dtype=float),
        bbox=(center_x - 5.0, 235.0, center_x + 5.0, 245.0),
        quality=0.95,
        mot_history_length=5,
        timestamp=timestamp,
    )


def test_actor_and_object_identity_permutation_does_not_change_online_geometry() -> None:
    base = [
        {
            "bbox": (315.0, 235.0, 325.0, 245.0),
            "track_id": "actor-A",
            "actor_name": "actor-A",
            "object_id": 101,
            "truth_global_track_id": "G1",
            "mot_history_length": 3,
        },
        {
            "bbox": (335.0, 235.0, 345.0, 245.0),
            "track_id": "actor-B",
            "actor_name": "actor-B",
            "object_id": 202,
            "truth_global_track_id": "G2",
            "mot_history_length": 3,
        },
    ]
    permuted_truth = [
        dict(base[0], track_id="actor-B", actor_name="actor-B", object_id=202, truth_global_track_id="G2"),
        dict(base[1], track_id="actor-A", actor_name="actor-A", object_id=101, truth_global_track_id="G1"),
    ]

    tracks_a = local_visual_tracks_from_sim_detections(
        base,
        resource_id="R1",
        camera_id="front",
        timestamp=10.0,
    )
    tracks_b = local_visual_tracks_from_sim_detections(
        permuted_truth,
        resource_id="R1",
        camera_id="front",
        timestamp=10.0,
    )
    assert [track.local_track_id for track in tracks_a] == ["front_det_0", "front_det_1"]
    assert [track.local_track_id for track in tracks_b] == ["front_det_0", "front_det_1"]

    global_tracks = [_global("G1", 0.0), _global("G2", 4.0)]
    result_a = associate_tracks_to_detections_geometrically(
        global_tracks,
        tracks_a,
        _camera(),
        timestamp=10.0,
        arrival_timestamp=10.05,
    )
    result_b = associate_tracks_to_detections_geometrically(
        global_tracks,
        tracks_b,
        _camera(),
        timestamp=10.0,
        arrival_timestamp=10.05,
    )

    assert result_a.assignments == result_b.assignments == {
        "G1": "front_det_0",
        "G2": "front_det_1",
    }
    assert all(record["association_source"] == "geometric_detect" for record in result_a.to_log_records())
    assert all(record["truth_identity_used"] is False for record in result_a.to_log_records())


def test_predicted_track_never_locks_and_reacquire_requires_fresh_stable_measurements() -> None:
    associator = TerminalAssociator(
        AssociationConfig(stable_window_frames=3, stable_required_observations=2)
    )
    assignment = Assignment("G1", resource_id="R1")
    global_track = _global("G1")
    original_global_id = global_track.global_track_id

    initial = associator.decide(
        assignment,
        [global_track],
        [_measured("anon-7", 10.0)],
        camera=_camera(),
        current_time=10.0,
        arrival_timestamp=10.02,
    )
    predicted = LocalVisualTrack(
        local_track_id="anon-7",
        center_px=np.array([320.5, 240.0], dtype=float),
        bbox=(315.5, 235.0, 325.5, 245.0),
        quality=0.9,
        mot_history_length=6,
        timestamp=10.0,
        local_track_state="predicted",
        prediction_age_s=0.1,
    )
    predicted_decision = associator.decide(
        assignment,
        [global_track],
        [predicted],
        camera=_camera(),
        current_time=10.1,
        arrival_timestamp=10.12,
    )
    first_measured = associator.decide(
        assignment,
        [global_track],
        [_measured("anon-7", 10.2)],
        camera=_camera(),
        current_time=10.2,
        arrival_timestamp=10.22,
    )
    reacquired = associator.decide(
        assignment,
        [global_track],
        [_measured("anon-7", 10.3)],
        camera=_camera(),
        current_time=10.3,
        arrival_timestamp=10.32,
    )

    assert initial.decision_state == "locked"
    assert predicted_decision.decision_state == "reacquire"
    assert predicted_decision.local_track_state == "predicted"
    assert predicted_decision.reason == "predicted_local_track_requires_measured_reacquire"
    assert predicted_decision.prediction_age_s == 0.1
    assert predicted_decision.truth_identity_used is False
    assert first_measured.decision_state == "ambiguous"
    assert first_measured.reason == "reacquire_candidate_not_temporally_stable"
    assert reacquired.decision_state == "locked"
    assert reacquired.local_track_state == "measured"
    assert global_track.global_track_id == original_global_id


def test_observation_bus_exposes_dual_timestamps_and_truth_isolated_runtime_record() -> None:
    local_track = _measured("anon-9", 10.0)
    decision = TerminalAssociator().decide(
        Assignment("G1", resource_id="R1"),
        [_global("G1")],
        [local_track],
        camera=_camera(),
        current_time=10.1,
        arrival_timestamp=10.25,
    )
    bus = TerminalObservationBus()
    observation = bus.publish_terminal_association(
        resource_id="R1",
        source_node_id="R1",
        link_type="airsim_cv_detection",
        timestamp=10.1,
        terminal_association=decision,
        local_track=local_track,
        camera_id="front",
        frame_id="frame-10",
        arrival_timestamp=10.25,
    )

    record = bus.runtime_records()[0]
    assert observation.measurement_timestamp == 10.0
    assert observation.arrival_timestamp == 10.25
    assert record["association_source"] == "geometric_detect"
    assert record["measurement_timestamp"] == 10.0
    assert record["arrival_timestamp"] == 10.25
    assert record["measurement_age_s"] == 0.25
    assert record["prediction_age_s"] is None
    assert record["local_track_state"] == "measured"
    assert record["truth_identity_used"] is False
    assert record["association_confidence"] == decision.association_confidence
    assert record["rejection_reason"] == decision.reason
    json.dumps(record)
