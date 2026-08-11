from __future__ import annotations

import math

import numpy as np

from airsim_runtime.long_range_cv_scan import INTERCEPTOR_CAMERA_NAME
from airsim_runtime.long_range_mot_reaudit import (
    camera_info_from_gimbal_record,
    reaudit_long_range_profile_rows,
)


def _project(camera_info, ray_ned):
    ray = np.asarray(camera_info.rotation_world_to_camera, dtype=float) @ np.asarray(
        ray_ned, dtype=float
    )
    return (
        camera_info.fx * ray[0] / ray[2] + camera_info.cx,
        camera_info.fy * ray[1] / ray[2] + camera_info.cy,
    )


def test_offline_reaudit_compensates_camera_motion_before_truth_join() -> None:
    target_rays = {
        "GT-A": (math.cos(math.radians(3.0)), math.sin(math.radians(3.0)), 0.0),
        "GT-B": (math.cos(math.radians(7.0)), math.sin(math.radians(7.0)), 0.0),
    }
    detection_rows = []
    offline_rows = []
    scan_rows = []
    for frame_index, yaw_deg in enumerate((0.0, 20.0)):
        timestamp = frame_index * 0.01
        camera_info = camera_info_from_gimbal_record(
            vehicle_name=INTERCEPTOR_CAMERA_NAME,
            frame_index=frame_index,
            timestamp=timestamp,
            yaw_deg=yaw_deg,
            pitch_deg=0.0,
            position_ned=(0.0, 0.0, 0.0),
        )
        order = ("GT-A", "GT-B") if frame_index == 0 else ("GT-B", "GT-A")
        for detection_index, truth_id in enumerate(order):
            u, v = _project(camera_info, target_rays[truth_id])
            size = 30.0 if truth_id == "GT-A" else 44.0
            detection_id = f"det:{frame_index}:{detection_index}"
            detection_rows.append(
                {
                    "frame_index": frame_index,
                    "camera_id": f"{INTERCEPTOR_CAMERA_NAME}:0",
                    "detection_id": detection_id,
                    "local_track_id": f"old-order-{detection_index}",
                    "measurement_timestamp": timestamp,
                    "bbox_x1": u - size / 2.0,
                    "bbox_y1": v - size / 2.0,
                    "bbox_x2": u + size / 2.0,
                    "bbox_y2": v + size / 2.0,
                    "center_u": u,
                    "center_v": v,
                }
            )
            offline_rows.append(
                {"detection_id": detection_id, "global_track_id": truth_id}
            )
        scan_rows.append(
            {
                "frame_index": frame_index,
                "interceptor_yaw_deg": yaw_deg,
                "interceptor_pitch_deg": 0.0,
                "interceptor_position_x": 0.0,
                "interceptor_position_y": 0.0,
                "interceptor_position_z": 0.0,
                "center_yaw_deg": 0.0,
                "center_pitch_deg": 0.0,
            }
        )
    crossing_windows = (
        {
            "camera_vehicle_name": INTERCEPTOR_CAMERA_NAME,
            "target_a_global_track_id": "GT-A",
            "target_b_global_track_id": "GT-B",
            "window_start_timestamp": 0.0,
            "window_end_timestamp": 0.01,
        },
    )

    result = reaudit_long_range_profile_rows(
        detection_rows=detection_rows,
        scan_rows=scan_rows,
        offline_truth_rows=offline_rows,
        crossing_windows=crossing_windows,
    )

    baseline = result["baseline_rescored"]["aggregate"]
    corrected = result["camera_motion_compensated"]["aggregate"]
    assert result["online_truth_identity_use_count"] == 0
    assert result["truth_join_stage"] == "after_anonymous_tracking_for_offline_scoring_only"
    assert baseline["id_switch_count"] == 2
    assert corrected["id_switch_count"] == 0
    assert corrected["crossing_evaluable_window_count"] == 1
    assert corrected["crossing_id_switch_count"] == 0
    assert corrected["crossing_track_purity"] == 1.0
    assert all(
        row["camera_motion_compensated"]
        and not row["online_truth_identity_used"]
        for row in result["corrected_assignments"]
    )
