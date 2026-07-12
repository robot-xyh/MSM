from __future__ import annotations

import numpy as np

from d5_terminal_association import (
    CameraGeometryEvidence,
    CameraModel,
    TerminalAssociation,
    TerminalObservationBus,
    YoloMotAdapter,
    YoloMotAdapterConfig,
    camera_geometry_evidence_from_camera_model,
    local_visual_tracks_from_sim_detections,
)


def _camera() -> CameraModel:
    return CameraModel(
        K=np.array([[320.0, 0.0, 320.0], [0.0, 320.0, 240.0], [0.0, 0.0, 1.0]]),
        R=np.eye(3),
        t=np.array([-1.0, -2.0, -3.0]),
        image_size=(640, 480),
    )


def test_camera_geometry_requires_intrinsics_extrinsics_and_fresh_attitude() -> None:
    valid = camera_geometry_evidence_from_camera_model(
        _camera(),
        measurement_timestamp=10.0,
        arrival_timestamp=10.04,
        attitude_timestamp=9.98,
        max_attitude_age_s=0.05,
    )
    stale = camera_geometry_evidence_from_camera_model(
        _camera(),
        measurement_timestamp=10.0,
        attitude_timestamp=9.0,
        max_attitude_age_s=0.05,
    )
    unavailable = CameraGeometryEvidence(
        measurement_timestamp=10.0,
        arrival_timestamp=10.1,
    )

    assert valid.geometry_valid is True
    np.testing.assert_allclose(valid.camera_position_ned, np.array([1.0, 2.0, 3.0]))
    assert valid.to_metadata()["camera_to_ned_rotation"] == np.eye(3).tolist()
    assert stale.geometry_valid is False
    assert "camera_attitude_unavailable_or_stale" in stale.unavailable_reasons
    assert unavailable.geometry_valid is False
    assert set(unavailable.unavailable_reasons) == {
        "camera_intrinsics_unavailable",
        "camera_extrinsics_unavailable",
        "camera_attitude_unavailable_or_stale",
    }


def test_detect_adapter_emits_truth_free_timing_clipping_and_geometry_evidence() -> None:
    geometry = camera_geometry_evidence_from_camera_model(
        _camera(),
        measurement_timestamp=4.0,
        arrival_timestamp=4.08,
        attitude_timestamp=4.0,
    )
    track = local_visual_tracks_from_sim_detections(
        [
            {
                "bbox": (0.0, 12.0, 30.0, 40.0),
                "confidence": 0.87,
                "mot_history_length": 5,
                "track_transition_state": "switched",
                "track_reset_reason": "tracker_reidentified",
                "object_id": "TargetActor_truth_only",
                "global_track_id": "G-truth-only",
            }
        ],
        resource_id="UAV1",
        camera_id="front_rgb",
        timestamp=4.0,
        arrival_timestamp=4.08,
        image_size=(640, 480),
        camera_geometry=geometry,
    )[0]

    evidence = track.to_evidence_metadata()
    assert track.arrival_timestamp == 4.08
    assert track.track_transition_state == "switched"
    assert track.track_reset_reason == "tracker_reidentified"
    assert track.bbox_edge_clipped is True
    assert track.bbox_edge_clip_sides == ("left",)
    assert track.detection_source == "simGetDetections"
    assert evidence["camera_geometry"]["geometry_valid"] is True
    assert evidence["truth_identity_used"] is False
    assert "TargetActor" not in track.local_track_id
    assert "G-truth" not in track.local_track_id


def test_runtime_record_preserves_conflicts_and_propagates_geometry() -> None:
    geometry = camera_geometry_evidence_from_camera_model(
        _camera(),
        measurement_timestamp=2.0,
        arrival_timestamp=2.1,
        attitude_timestamp=2.0,
    )
    track = local_visual_tracks_from_sim_detections(
        [{"bbox": (10.0, 10.0, 30.0, 30.0), "mot_history_length": 1}],
        resource_id="UAV1",
        camera_id="front_rgb",
        timestamp=2.0,
        arrival_timestamp=2.1,
        image_size=(640, 480),
        camera_geometry=geometry,
    )[0]
    association = TerminalAssociation(
        assigned_global_track_id="G1",
        local_track_id=track.local_track_id,
        association_confidence=0.91,
        ambiguity_score=0.09,
        friend_conflict_state="verified_friend_overlap",
        decision_state="hold",
        assignment_version=7,
        reason="friend_conflict",
        mot_history_length=track.mot_history_length,
        track_transition_state=track.track_transition_state,
        detection_source=track.detection_source,
        metadata={"duplicate_terminal_lock_risk": True},
    )
    bus = TerminalObservationBus()
    bus.publish_terminal_association(
        resource_id="UAV1",
        source_node_id="UAV1",
        link_type="airsim_cv_detection",
        timestamp=2.0,
        arrival_timestamp=2.1,
        terminal_association=association,
        local_track=track,
        camera_id="front_rgb",
    )

    record = bus.runtime_records()[0]
    assert record["assigned_global_track_id"] == "G1"
    assert record["association_confidence"] == 0.91
    assert record["friend_conflict_state"] == "verified_friend_overlap"
    assert record["duplicate_terminal_lock_risk"] is True
    assert record["track_transition_state"] == "initialized"
    assert record["camera_geometry"]["geometry_valid"] is True
    assert record["truth_identity_used"] is False


def test_yolo_mot_tracks_report_initialized_then_continued_without_authority() -> None:
    adapter = YoloMotAdapter(
        YoloMotAdapterConfig(tracker_backend="iou_fallback", confidence_threshold=0.1),
        detector=lambda frame: [
            {"bbox": (0.0, 5.0, 20.0, 25.0), "confidence": 0.9, "class_name": "uav"}
        ],
    )
    frame = np.zeros((48, 64, 3), dtype=np.uint8)

    first = adapter.process_frame(
        frame,
        resource_id="UAV1",
        camera_id="front_rgb",
        timestamp=1.0,
        arrival_timestamp=1.03,
    )
    second = adapter.process_frame(
        frame,
        resource_id="UAV1",
        camera_id="front_rgb",
        timestamp=1.1,
        arrival_timestamp=1.14,
    )

    assert first.tracks[0].local_track_id == second.tracks[0].local_track_id
    assert first.tracks[0].track_transition_state == "initialized"
    assert second.tracks[0].track_transition_state == "continued"
    assert first.tracks[0].bbox_edge_clip_sides == ("left",)
    assert first.tracks[0].arrival_timestamp == 1.03
    assert first.metadata["camera_geometry"]["geometry_valid"] is False
    assert not hasattr(first.tracks[0], "global_track_id")
