from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import sys

import numpy as np
import pytest


EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_episode(root: Path, seed: int, *, target_count: int = 4) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    online = root / "online"
    offline = root / "truth"
    camera_positions = {
        "Optical_A": np.asarray((0.0, -1000.0, -100.0)),
        "Optical_B": np.asarray((0.0, 1000.0, -100.0)),
    }
    track_rows: list[dict[str, object]] = []
    sample_rows: list[dict[str, object]] = []
    detection_rows: list[dict[str, object]] = []
    scoring_rows: list[dict[str, object]] = []
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
                start = np.asarray(
                    (
                        2200.0 + target_index * 45.0,
                        -180.0 + target_index * 120.0,
                        -95.0 + target_index * 4.0,
                    )
                )
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
                        "bbox_xyxy": json.dumps(
                            [600.0, 480.0, 620.0 + target_index, 492.0]
                        ),
                        "center_px": json.dumps([610.0, 486.0]),
                        "confidence": 0.95,
                    }
                )
    paths = {
        "anonymous_detections": online / "anonymous_detections.csv",
        "local_tracks": online / "local_tracks.csv",
        "local_track_samples": online / "local_track_samples.csv",
        "track_scoring": offline / "track_scoring.csv",
    }
    _write_csv(paths["anonymous_detections"], detection_rows)
    _write_csv(paths["local_tracks"], track_rows)
    _write_csv(paths["local_track_samples"], sample_rows)
    _write_csv(paths["track_scoring"], scoring_rows)
    (root / "record_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "dual-optical-record-manifest-v2",
                "artifacts": {
                    key: str(path.relative_to(root)) for key, path in paths.items()
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    focal = 1280 / (2 * math.tan(math.radians(2.93) / 2))
    (root / "scenario.json").write_text(
        json.dumps(
            {
                "schema_version": "lightweight-fixture-v1",
                "camera": {
                    "width": 1280,
                    "horizontal_fov_deg": 2.93,
                    "focal_length_px": focal,
                },
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
    def factory(seed: int, *, target_count: int = 4) -> Path:
        return make_episode(tmp_path / f"episode_{seed}", seed, target_count=target_count)

    return factory


@pytest.fixture
def dataset_manifest(episode_factory, tmp_path):
    from dual_optical_100target_gnn.dataset import prepare_dataset
    from dual_optical_100target_gnn.graph import GeometryGate

    seeds = (501, 502, 503, 504)
    inputs = {seed: episode_factory(seed) for seed in seeds}
    return prepare_dataset(
        inputs,
        tmp_path / "dataset",
        splits={"train": (501, 502), "val": (503,), "test": (504,)},
        gate=GeometryGate(
            coplanarity_median_mrad=1000.0,
            maximum_reprojection_rms_px=1.0e9,
            minimum_intersection_angle_deg=0.1,
            maximum_condition_number=1.0e14,
        ),
        expected_target_count=4,
    )
