from __future__ import annotations

import csv
import json
from pathlib import Path

from airsim_runtime.long_range_3d_reporting import (
    write_long_range_3d_trajectory_figures,
)


def test_long_range_3d_reporting_writes_positions_and_trajectories(
    tmp_path: Path,
) -> None:
    episode_dir = tmp_path / "episode"
    episode_dir.mkdir()
    actor_rows = []
    for frame, timestamp in enumerate((0.0, 1.0, 2.0)):
        for target_index, east in ((1, -10.0), (2, 10.0)):
            actor_rows.append(
                {
                    "frame_index": frame,
                    "simulation_timestamp": timestamp,
                    "object_id": f"TGT-{target_index:03d}",
                    "actor_name": f"actor-{target_index}",
                    "px_ned_m": 1000.0 - 20.0 * timestamp,
                    "py_ned_m": east,
                    "pz_ned_m": -100.0 - target_index,
                    "vx_ned_mps": -20.0,
                    "vy_ned_mps": 0.0,
                    "vz_ned_mps": 0.0,
                    "offline_truth_only": True,
                }
            )
    _write_csv(episode_dir / "actor_trajectory_truth.csv", actor_rows)

    gimbal_rows = [
        {
            "frame_index": frame,
            "measurement_timestamp": timestamp,
            "interceptor_position_x": 800.0 - 20.0 * timestamp,
            "interceptor_position_y": 0.0,
            "interceptor_position_z": -105.0,
        }
        for frame, timestamp in enumerate((0.0, 1.0, 2.0))
    ]
    _write_csv(episode_dir / "scan_gimbal.csv", gimbal_rows)
    _write_csv(
        episode_dir / "associations.csv",
        [
            {
                "frame_index": 1,
                "camera_id": "Center_CV:0",
                "global_track_id": "GT-0001",
            },
            {
                "frame_index": 2,
                "camera_id": "Interceptor_CV:0",
                "global_track_id": "GT-0002",
            },
        ],
    )
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(
        json.dumps(
            {
                "scenario": {"center_position_ned": [0.0, 0.0, -100.0]},
                "minimum_3d_separation_m": 20.0,
            }
        ),
        encoding="utf-8",
    )

    paths, summary = write_long_range_3d_trajectory_figures(
        episode_dir,
        scenario_path=scenario_path,
        output_dir=tmp_path / "figures",
    )

    assert summary["target_count"] == 2
    assert summary["duration_s"] == 2.0
    assert summary["target_path_length_m"]["mean"] == 40.0
    assert summary["interceptor_path_length_m"] == 40.0
    assert summary["association_event_count_by_camera"] == {
        "Center_CV": 1,
        "Interceptor_CV": 1,
    }
    for output_path in paths.values():
        assert output_path.exists()
        assert output_path.stat().st_size > 0


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
