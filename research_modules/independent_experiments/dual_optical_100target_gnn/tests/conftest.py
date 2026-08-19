from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import pytest


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def make_episode(root: Path, seed: int, *, version: int = 2, target_count: int = 4) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    online = root / "online"
    offline = root / "truth"
    camera_positions = {
        "Optical_A": np.asarray((0.0, -1000.0, -100.0)),
        "Optical_B": np.asarray((0.0, 1000.0, -100.0)),
    }
    track_rows = []
    sample_rows = []
    detection_rows = []
    scoring_rows = []
    for camera_id, origin in camera_positions.items():
        for target_index in range(target_count):
            track_id = f"{camera_id}-T{target_index + 1:04d}"
            identity = f"ID-{target_index + 1:03d}"
            track_rows.append(
                {
                    "track_id": track_id,
                    "camera_id": camera_id,
                    "stable": True,
                    "sweep_count": 8,
                    "sample_count": 8,
                    "first_timestamp": 0.0,
                    "last_timestamp": 3.5,
                }
            )
            scoring_rows.append(
                {
                    "track_id": track_id,
                    "camera_id": camera_id,
                    "stable": True,
                    "majority_truth_id": identity,
                    "purity": 1.0,
                    "scored_detection_count": 8,
                    "offline_truth_only": True,
                }
            )
            for sweep in range(8):
                timestamp = 0.5 * sweep + (0.01 if camera_id == "Optical_B" else 0.0)
                start = np.asarray((2200.0 + target_index * 45.0, -180.0 + target_index * 120.0, -95.0 + target_index * 4.0))
                velocity = np.asarray((-50.0, (target_index - 1.5) * 1.5, 0.0))
                point = start + velocity * timestamp
                direction = point - origin
                direction /= np.linalg.norm(direction)
                uid = f"{camera_id}-F{sweep:04d}-D{target_index:03d}"
                sample_rows.append(
                    {
                        "track_id": track_id,
                        "camera_id": camera_id,
                        "sample_index": sweep,
                        "sweep_index": sweep,
                        "measurement_timestamp": timestamp,
                        "ray_x_ned": direction[0],
                        "ray_y_ned": direction[1],
                        "ray_z_ned": direction[2],
                        "azimuth_deg": math.degrees(math.atan2(direction[1], direction[0])),
                        "elevation_deg": 0.0,
                        "detection_uids": json.dumps([uid]),
                    }
                )
                detection_rows.append(
                    {
                        "detection_uid": uid,
                        "camera_id": camera_id,
                        "frame_index": sweep,
                        "measurement_timestamp": timestamp,
                        "arrival_timestamp": timestamp + 0.001,
                        "bbox_xyxy": json.dumps([600.0, 480.0, 620.0 + target_index, 492.0]),
                        "center_px": json.dumps([610.0, 486.0]),
                        "confidence": 0.95,
                    }
                )
    suffix = "_v3" if version == 3 else ""
    paths = {
        "anonymous_detections": online / f"anonymous_detections{suffix}.csv",
        "local_tracks": online / f"local_tracks{suffix}.csv",
        "local_track_samples": online / f"local_track_samples{suffix}.csv",
        "track_scoring": offline / f"track_scoring{suffix}.csv",
    }
    _write_csv(paths["anonymous_detections"], list(detection_rows[0]), detection_rows)
    _write_csv(paths["local_tracks"], list(track_rows[0]), track_rows)
    _write_csv(paths["local_track_samples"], list(sample_rows[0]), sample_rows)
    _write_csv(paths["track_scoring"], list(scoring_rows[0]), scoring_rows)
    artifacts = {
        (key + ("_v3" if version == 3 else "")): str(path.relative_to(root))
        for key, path in paths.items()
    }
    (root / "record_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": f"dual-optical-record-manifest-v{version}",
                "artifacts": artifacts,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    focal = 1280 / (2 * math.tan(math.radians(2.93) / 2))
    (root / "scenario.json").write_text(
        json.dumps(
            {
                "schema_version": "fixture-v1",
                "camera": {"width": 1280, "horizontal_fov_deg": 2.93, "focal_length_px": focal},
                "scenario": {
                    "seed": seed,
                    "target_count": target_count,
                    "camera_a_name": "Optical_A",
                    "camera_b_name": "Optical_B",
                    "camera_a_position_ned": camera_positions["Optical_A"].tolist(),
                    "camera_b_position_ned": camera_positions["Optical_B"].tolist(),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return root


@pytest.fixture
def episode_factory(tmp_path):
    def factory(seed: int, *, version: int = 2, target_count: int = 4) -> Path:
        return make_episode(tmp_path / f"episode_{seed}", seed, version=version, target_count=target_count)

    return factory
