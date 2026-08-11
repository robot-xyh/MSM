from __future__ import annotations

import csv
import json
from pathlib import Path

from airsim_runtime.baseline_evidence import freeze_long_range_baseline


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_freeze_long_range_baseline_separates_online_and_truth(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "frozen"
    source.mkdir()
    metrics = {
        "target_count": 1,
        "association_evaluable_count": 2,
        "association_accuracy": 0.5,
        "id_switch_count": 0,
        "geometric_binding_switch_count": 1,
        "duplicate_assignment_count": 0,
        "online_truth_identity_use_count": 0,
        "global_track_id_rewrite_count": 0,
        "mot_continuity": {"aggregate": {
            "fragmentation_count": 1,
            "reacquisition_count": 0,
            "crossing_window_count": 1,
            "crossing_evaluable_window_count": 0,
            "crossing_window_results": [{"availability": False, "unavailable_reason": "missing_pair"}],
        }},
    }
    (source / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    for name in ("mot_continuity.json", "record_manifest.json"):
        (source / name).write_text("{}", encoding="utf-8")
    associations = [
        {"frame_index": 0, "camera_id": "Center_CV:0", "measurement_timestamp": 0.0,
         "global_track_id": "GT-1", "local_track_id": "local-1", "pixel_error": 1.0,
         "mahalanobis_d2": 0.1},
        {"frame_index": 10, "camera_id": "Center_CV:0", "measurement_timestamp": 0.1,
         "global_track_id": "GT-2", "local_track_id": "local-1", "pixel_error": 2.0,
         "mahalanobis_d2": 0.2},
    ]
    _write_csv(source / "associations.csv", associations)
    detections = []
    gimbal = []
    tracks = []
    truth = []
    for frame in range(11):
        gimbal.append({"frame_index": frame, "measurement_timestamp": frame * 0.01,
                       "center_yaw_deg": 0.0, "center_pitch_deg": 0.0,
                       "interceptor_yaw_deg": 0.0, "interceptor_pitch_deg": 0.0,
                       "interceptor_position_x": 10.0, "interceptor_position_y": 0.0,
                       "interceptor_position_z": -10.0})
        tracks.append({"frame_index": frame, "measurement_timestamp": frame * 0.01,
                       "arrival_timestamp": frame * 0.01, "global_track_id": "GT-1",
                       "px_ned_m": 100.0, "py_ned_m": 0.0, "pz_ned_m": -10.0,
                       "vx_ned_mps": -1.0, "vy_ned_mps": 0.0, "vz_ned_mps": 0.0,
                       "covariance_xx": 1.0, "covariance_yy": 1.0, "covariance_zz": 1.0,
                       "source": "fixture"})
    for frame in (0, 10):
        detections.append({"frame_index": frame, "camera_id": "Center_CV:0",
                           "detection_id": f"det-{frame}", "local_track_id": "local-1",
                           "measurement_timestamp": frame * 0.01, "arrival_timestamp": frame * 0.01,
                           "bbox_x1": 1.0, "bbox_y1": 1.0, "bbox_x2": 3.0, "bbox_y2": 3.0,
                           "center_u": 2.0, "center_v": 2.0, "covariance_uu": 1.0,
                           "covariance_uv": 0.0, "covariance_vv": 1.0, "rpc_latency_s": 0.0,
                           "mot_backend": "fixture", "camera_motion_compensated": True,
                           "world_ray_ned": "[1, 0, 0]", "mot_history_length": 1,
                           "online_truth_identity_used": False})
        truth.append({"frame_index": frame, "measurement_timestamp": frame * 0.01,
                      "camera_vehicle_name": "Center_CV", "local_track_id": "local-1",
                      "truth_global_track_id": "GT-1", "offline_truth_only": True})
    _write_csv(source / "detections.csv", detections)
    _write_csv(source / "global_tracks.csv", tracks)
    _write_csv(source / "scan_gimbal.csv", gimbal)
    _write_csv(source / "mot_offline_score.csv", truth)
    _write_csv(source / "offline_truth.csv", truth)

    paths = freeze_long_range_baseline(source, output)
    online = paths["online_replay"].read_text(encoding="utf-8")
    sidecar = json.loads(paths["offline_truth_sidecar"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert "truth_global_track_id" not in online
    assert "actor_name" not in online
    assert sidecar["offline_truth_only"] is True
    assert len(sidecar["incorrect_associations"]) == 1
    assert manifest["failure_counts"]["binding_switch_count"] == 1
