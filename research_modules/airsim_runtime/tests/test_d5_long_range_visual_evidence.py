from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np

from airsim_runtime.long_range_visual_evidence import (
    write_long_range_registration_visual_evidence,
)


def test_visual_evidence_writes_overlays_and_preserves_raw_images(tmp_path: Path) -> None:
    raw_paths = {}
    for owner, offset in (("Center_CV", 0), ("Interceptor_CV", 30)):
        image = np.full((360, 640, 3), 215, dtype=np.uint8)
        cv2.rectangle(image, (280 + offset, 150), (315 + offset, 185), (20, 20, 20), -1)
        path = tmp_path / f"{owner}.png"
        assert cv2.imwrite(str(path), image)
        raw_paths[owner] = path
    before = {owner: _sha256(path) for owner, path in raw_paths.items()}

    snapshot_rows = [
        {
            "frame_index": 10,
            "logical_timestamp": 1.0,
            "camera_vehicle_name": owner,
            "capture_reasons": "first_binding:GT-0001",
            "saved": True,
            "path": str(path),
        }
        for owner, path in raw_paths.items()
    ]
    detection_rows = []
    association_rows = []
    accuracy_rows = []
    for owner, offset in (("Center_CV", 0), ("Interceptor_CV", 30)):
        local_id = f"{owner}:L001"
        detection_rows.append(
            {
                "frame_index": 10,
                "camera_id": f"{owner}:0",
                "local_track_id": local_id,
                "bbox_x1": 280 + offset,
                "bbox_y1": 150,
                "bbox_x2": 315 + offset,
                "bbox_y2": 185,
            }
        )
        association_rows.append(
            {
                "frame_index": 10,
                "camera_id": f"{owner}:0",
                "measurement_timestamp": 1.0,
                "global_track_id": "GT-0001",
                "local_track_id": local_id,
                "projected_u": 300 + offset,
                "projected_v": 168,
                "bbox_center_u": 297.5 + offset,
                "bbox_center_v": 167.5,
                "pixel_error": 2.55,
                "mahalanobis_d2": 0.4,
            }
        )
        accuracy_rows.append(
            {
                "camera_vehicle_name": owner,
                "frame_index": 10,
                "global_track_id": "GT-0001",
                "local_track_id": local_id,
                "truth_global_track_id": "GT-0001",
                "correct": True,
            }
        )

    paths, metrics = write_long_range_registration_visual_evidence(
        tmp_path / "episode",
        snapshot_rows=snapshot_rows,
        detection_rows=detection_rows,
        association_rows=association_rows,
        accuracy_rows=accuracy_rows,
        metrics={
            "target_count": 1,
            "center_unique_discovery_count": 1,
            "association_accuracy": 1.0,
            "mot_continuity": {"aggregate": {"id_switch_count": 0, "fragmentation_count": 0}},
        },
        center_vehicle_name="Center_CV",
        interceptor_vehicle_name="Interceptor_CV",
    )

    assert metrics["annotated_snapshot_count"] == 2
    assert metrics["shared_track_handover_panel_count"] == 1
    assert metrics["online_overlay_truth_identity_used"] is False
    assert paths["camera_registration_overview"].exists()
    assert paths["handover_gallery_01"].exists()
    assert paths["offline_registration_confusion_matrix"].exists()
    assert paths["visual_registration_effect_report"].exists()
    assert before == {owner: _sha256(path) for owner, path in raw_paths.items()}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
