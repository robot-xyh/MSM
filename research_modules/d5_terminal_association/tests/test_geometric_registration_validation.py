from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from d5_terminal_association import (
    AssociationConfig,
    GlobalTrack,
    LocalVisualTrack,
    associate_tracks_to_detections_geometrically,
    evaluate_associations_offline,
    intrinsics_from_capture_settings,
    rotation_world_to_opencv_camera_from_quaternion,
)
from d5_terminal_association.airsim_geometry import camera_model_from_airsim_camera_info


def _track(track_id: str, position: tuple[float, float, float]) -> GlobalTrack:
    return GlobalTrack(
        global_track_id=track_id,
        position=np.array(position, dtype=float),
        velocity=np.zeros(3, dtype=float),
        covariance=np.diag([0.1, 0.1, 0.1]),
        category="uav",
        timestamp=0.0,
    )


def _local(local_id: str, center: tuple[float, float]) -> LocalVisualTrack:
    u, v = center
    return LocalVisualTrack(
        local_track_id=local_id,
        center_px=np.array([u, v], dtype=float),
        bbox=(u - 8.0, v - 8.0, u + 8.0, v + 8.0),
        category="uav",
        quality=0.95,
        mot_history_length=5,
        timestamp=0.0,
    )


def test_airsim_intrinsics_from_640x480_120deg_settings() -> None:
    intrinsics = intrinsics_from_capture_settings(
        {"ImageType": 0, "Width": 640, "Height": 480, "FOV_Degrees": 120}
    )

    assert intrinsics.width == 640
    assert intrinsics.height == 480
    np.testing.assert_allclose(intrinsics.K[0, 0], 184.752086, atol=1e-5)
    np.testing.assert_allclose(intrinsics.K[1, 1], 184.752086, atol=1e-5)
    assert intrinsics.K[0, 2] == 320.0
    assert intrinsics.K[1, 2] == 240.0


def test_camera_model_from_airsim_info_uses_non_identity_extrinsics() -> None:
    yaw_90deg = SimpleNamespace(
        w_val=np.cos(np.pi / 4.0),
        x_val=0.0,
        y_val=0.0,
        z_val=np.sin(np.pi / 4.0),
    )
    rotation = rotation_world_to_opencv_camera_from_quaternion(yaw_90deg)
    camera_info = SimpleNamespace(
        fx=184.752086,
        fy=184.752086,
        cx=320.0,
        cy=240.0,
        width=640,
        height=480,
        position_ned=(10.0, -2.0, -5.0),
        rotation_world_to_camera=rotation,
    )

    camera = camera_model_from_airsim_camera_info(camera_info)

    assert not np.allclose(camera.R, np.eye(3))
    np.testing.assert_allclose(camera.t, -camera.R @ np.array([10.0, -2.0, -5.0]))
    assert camera.image_size == (640, 480)


def test_geometric_hungarian_association_does_not_use_truth_ids() -> None:
    camera_info = SimpleNamespace(
        fx=160.0,
        fy=160.0,
        cx=320.0,
        cy=240.0,
        width=640,
        height=480,
        position_ned=(0.0, 0.0, 0.0),
        rotation_world_to_camera=np.eye(3),
    )
    camera = camera_model_from_airsim_camera_info(camera_info, measurement_sigma_px=20.0)
    tracks = [
        _track("G-left", (-2.0, 0.0, 20.0)),
        _track("G-right", (2.0, 0.0, 20.0)),
    ]
    # Deliberately misleading AirSim-like truth labels stay outside the online
    # association call; only local IDs and bbox centers are supplied.
    locals_ = [
        _local("det-object_id_TGT_WRONG_A", (336.0, 240.0)),
        _local("det-object_id_TGT_WRONG_B", (304.0, 240.0)),
    ]

    result = associate_tracks_to_detections_geometrically(
        tracks,
        locals_,
        camera,
        config=AssociationConfig(gate_chi2=25.0, min_lock_margin=1.0),
        timestamp=0.0,
        frame_id="mock-frame",
    )

    assert result.assignments == {
        "G-left": "det-object_id_TGT_WRONG_B",
        "G-right": "det-object_id_TGT_WRONG_A",
    }
    assert all(pair.gate_pass for pair in result.pairs if pair.assignment_selected)

    metrics = evaluate_associations_offline(
        result,
        {
            "det-object_id_TGT_WRONG_A": "G-left",
            "det-object_id_TGT_WRONG_B": "G-right",
        },
    )
    assert metrics.evaluated_count == 2
    assert metrics.id_mismatch_count == 2
    assert metrics.association_accuracy == 0.0


def test_geometric_result_reports_pixel_and_mahalanobis_fields() -> None:
    camera_info = SimpleNamespace(
        fx=160.0,
        fy=160.0,
        cx=320.0,
        cy=240.0,
        width=640,
        height=480,
        position_ned=(0.0, 0.0, 0.0),
        rotation_world_to_camera=np.eye(3),
    )
    camera = camera_model_from_airsim_camera_info(camera_info, measurement_sigma_px=10.0)

    result = associate_tracks_to_detections_geometrically(
        [_track("G-1", (0.0, 0.0, 20.0))],
        [_local("det-1", (323.0, 244.0))],
        camera,
        config=AssociationConfig(gate_chi2=25.0),
        timestamp=0.0,
    )

    pair = result.pairs[0]
    assert pair.projected_px == (320.0, 240.0)
    assert pair.bbox_center_px == (323.0, 244.0)
    np.testing.assert_allclose(pair.pixel_error, 5.0)
    assert pair.mahalanobis_d2 > 0.0
    assert pair.gate_pass is True
    assert pair.assignment_selected is True
