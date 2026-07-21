from __future__ import annotations

import csv
import json

from research_modules.scalable_3d_simulation.capacity_reporting import (
    write_capacity_probe_report,
)


def test_capacity_report_preserves_measured_results_without_plots(tmp_path) -> None:
    scenario_root = tmp_path / "scenario"
    timed_root = tmp_path / "timed"
    report_root = tmp_path / "report"
    scenario_root.mkdir()
    timed_root.mkdir()
    rows = [
        {
            "scenario": "nominal",
            "seed": 1,
            "real_time_factor": 0.05,
            "d3_exported_frame_count": 2,
            "d4_captured_frame_count": 2,
            "d5_staged_frame_count": 4,
            "d5_active_vision_staged_frame_count": 3,
            "finite_state": True,
            "online_truth_use_count": 0,
        },
        {
            "scenario": "delayed_noisy",
            "seed": 2,
            "real_time_factor": 0.02,
            "d3_exported_frame_count": 2,
            "d4_captured_frame_count": 2,
            "d5_staged_frame_count": 6,
            "d5_active_vision_staged_frame_count": 2,
            "finite_state": True,
            "online_truth_use_count": 0,
        },
    ]
    with (scenario_root / "episode_progress.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (scenario_root / "generation_summary.json").write_text(
        json.dumps(
            {
                "git_commit": "a" * 40,
                "learning_dataset_size_bytes": 2000,
                "learning_export_summary": {},
            }
        ),
        encoding="utf-8",
    )
    (timed_root / "generation_summary.json").write_text(
        json.dumps(
            {
                "git_commit": "b" * 40,
                "timing_summary": {
                    "episode_run_wall_s": 2.0,
                    "artifact_stage_wall_s": 3.0,
                    "finalization_wall_s": 4.0,
                    "generation_wall_s": 9.0,
                },
            }
        ),
        encoding="utf-8",
    )
    for name, payload in (
        ("d3_assignment", b"a"),
        ("d4_region", b"bb"),
        ("d5_tracklet_graph", b"ccc"),
        ("d5_active_vision", b"dddd"),
    ):
        component = scenario_root / "learning_dataset" / name
        component.mkdir(parents=True)
        (component / "artifact.bin").write_bytes(payload)

    paths = write_capacity_probe_report(
        scenario_root,
        timed_root,
        report_root,
        write_plots=False,
    )

    report = paths["report"].read_text(encoding="utf-8")
    assert "九类 200 对 200 场景" in report
    assert "延迟噪声" in report
    assert "制品写入 3.0 秒" in report
    assert paths["results_csv"].read_text(encoding="utf-8-sig").startswith(
        "场景,seed,实时因子"
    )
    assert not (report_root / "figures").exists()
