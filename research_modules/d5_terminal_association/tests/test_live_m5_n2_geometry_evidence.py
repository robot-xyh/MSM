from __future__ import annotations

import numpy as np

from d5_terminal_association import (
    Assignment,
    CameraModel,
    GlobalTrack,
    TerminalAssociator,
    associate_tracks_to_detections_geometrically,
    local_visual_tracks_from_sim_detections,
)


def _secondary_recon_1_camera() -> CameraModel:
    rotation = np.array(
        [
            [-0.9300853318281506, -0.3673435388272390, 3.955392735566221e-9],
            [0.3270065233132720, -0.8279551340817732, 0.4555842728389553],
            [-0.1673559357438086, 0.4237322508725458, 0.8901926591147562],
        ],
        dtype=float,
    )
    position = np.array([50.0, -24.0, -60.0], dtype=float)
    return CameraModel(
        K=np.array(
            [[320.0, 0.0, 320.0], [0.0, 320.0, 240.0], [0.0, 0.0, 1.0]],
            dtype=float,
        ),
        R=rotation,
        t=-rotation @ position,
        image_size=(640, 480),
    )


def _tracks() -> list[GlobalTrack]:
    return [
        GlobalTrack(
            global_track_id="T001",
            position=np.array([40.599998474121094, -0.19999998807907104, -10.0]),
            covariance=np.eye(3) * 0.01,
            category="uav",
            timestamp=4.0,
        ),
        GlobalTrack(
            global_track_id="T002",
            position=np.array([45.0, 0.19999998807907104, -10.0]),
            covariance=np.eye(3) * 0.01,
            category="uav",
            timestamp=4.0,
        ),
    ]


def test_recorded_secondary_detection_parses_without_online_truth_identity() -> None:
    local = local_visual_tracks_from_sim_detections(
        [
            {
                "bbox_xyxy": (
                    291.94891357421875,
                    242.80557250976562,
                    299.2794494628906,
                    250.13259887695312,
                ),
                "local_track_id": "Secondary_Recon_1:0:det:0001",
                "object_id": "TGT-002",
                "actor_name": "MSM_TargetActor_2",
                "category": "uav",
                "confidence": 1.0,
                "mot_history_length": 1,
            }
        ],
        resource_id="Secondary_Recon_1",
        camera_id="Secondary_Recon_1:0",
        timestamp=4.0,
    )[0]

    assert local.local_track_id == "Secondary_Recon_1:0:det:0001"
    assert "TGT-002" not in local.local_track_id
    assert "MSM_TargetActor_2" not in local.local_track_id
    np.testing.assert_allclose(local.center_px, np.array([295.6141815, 246.4690857]))


def test_recorded_detection_matches_only_with_its_own_camera_geometry() -> None:
    camera = _secondary_recon_1_camera()
    tracks = _tracks()
    local = local_visual_tracks_from_sim_detections(
        [
            {
                "bbox_xyxy": (
                    291.94891357421875,
                    242.80557250976562,
                    299.2794494628906,
                    250.13259887695312,
                ),
                "local_track_id": "Secondary_Recon_1:0:det:0001",
                "category": "uav",
                "confidence": 1.0,
                "mot_history_length": 1,
            }
        ],
        resource_id="Secondary_Recon_1",
        camera_id="Secondary_Recon_1:0",
        timestamp=4.0,
    )[0]

    result = associate_tracks_to_detections_geometrically(
        tracks,
        [local],
        camera=camera,
        timestamp=4.0,
    )
    projection = TerminalAssociator().project_tracks_to_image(
        tracks,
        camera,
        timestamp=4.0,
    )["T002"]

    assert result.assignments == {"T002": "Secondary_Recon_1:0:det:0001"}
    assert projection.pixel is not None
    assert np.linalg.norm(projection.pixel - local.center_px) < 0.2

    decision = TerminalAssociator().decide(
        Assignment("T002", resource_id="Secondary_Recon_1"),
        tracks,
        [local],
        camera=camera,
        current_time=4.0,
    )
    assert decision.decision_state == "ambiguous"
    assert decision.reason == "mot_history_too_short"
    assert decision.local_track_id == "Secondary_Recon_1:0:det:0001"
