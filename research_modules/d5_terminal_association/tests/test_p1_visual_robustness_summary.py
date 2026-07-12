from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from d5_terminal_association import (
    P1_VISUAL_ROBUSTNESS_PROFILE_VERSION,
    P1_VISUAL_ROBUSTNESS_SCHEMA_VERSION,
    run_p1_visual_robustness_matrix,
    write_p1_visual_robustness_summary,
)


ROOT = Path(__file__).resolve().parents[3]
CLI = (
    ROOT
    / "research_modules"
    / "d5_terminal_association"
    / "scripts"
    / "run_p1_visual_robustness_summary.py"
)


def test_summary_covers_required_matrix_and_safety_counters() -> None:
    payload = run_p1_visual_robustness_matrix().to_dict()
    rows = {row["case_id"]: row for row in payload["cases"]}

    assert payload["schema_version"] == P1_VISUAL_ROBUSTNESS_SCHEMA_VERSION
    assert payload["profile_version"] == P1_VISUAL_ROBUSTNESS_PROFILE_VERSION
    assert payload["case_count"] == 10
    assert payload["pass_count"] == 10
    assert payload["passed_case_count"] == 10
    assert payload["failed_case_count"] == 0
    assert payload["online_truth_use_count"] == 0
    assert payload["global_track_id_rewrite_count"] == 0
    assert payload["metadata"]["all_cases_passed"] is True
    assert len(payload["metadata"]["case_results"]) == 10
    assert payload["metadata"]["association_path"].endswith("mahalanobis_hungarian")

    for frame_count in range(1, 6):
        row = rows[f"dropout_{frame_count}_frame_recovery"]
        assert row["passed"] is True
        assert row["metadata"]["missing_frame_count"] == frame_count
        assert row["metadata"]["expected_expired_frame_count"] == max(0, frame_count - 2)
        assert row["decision_counts"]["reacquire"] == frame_count
        assert row["decision_counts"]["ambiguous"] == 1
        assert row["decision_counts"]["locked"] == 2

    assert rows["mot_id_change_after_dropout"]["passed"] is True
    assert rows["same_camera_crossing"]["passed"] is True
    assert rows["cross_camera_partial_overlap"]["passed"] is True
    assert rows["extrinsic_drift_4m"]["rejection_reason_counts"]["geometry_gate_rejected"] == 1
    assert (
        rows["timestamp_bias_0p5s_high_dynamic"]["rejection_reason_counts"][
            "geometry_gate_rejected"
        ]
        == 1
    )


def test_json_writer_is_deterministic_and_keeps_d6_compatibility_fields(tmp_path: Path) -> None:
    first = write_p1_visual_robustness_summary(tmp_path / "first.json")
    second = write_p1_visual_robustness_summary(tmp_path / "second.json")

    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    for key in (
        "seed_count",
        "ready_seed_count",
        "total_observation_count",
        "total_terminal_association_count",
        "missing_required_fields_by_seed",
        "missing_recommended_fields_by_seed",
        "metadata",
    ):
        assert key in payload
    assert payload["ready_seed_count"] == payload["seed_count"] == 1
    assert payload["missing_required_fields_by_seed"] == {"deterministic": []}
    assert payload["metadata"]["online_truth_use_count"] == 0
    assert payload["metadata"]["global_track_id_rewrite_count"] == 0


def test_cli_writes_versioned_json_for_d6_d5_summary_argument(tmp_path: Path) -> None:
    output = tmp_path / "d5_visual_robustness_summary.json"
    completed = subprocess.run(
        [sys.executable, str(CLI), "--output", str(output)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert f"d5_summary={output.resolve()}" in completed.stdout
    assert payload["schema_version"] == P1_VISUAL_ROBUSTNESS_SCHEMA_VERSION
    assert payload["passed_case_count"] == payload["case_count"]
    assert payload["failed_case_count"] == 0
    assert payload["online_truth_use_count"] == 0
    assert payload["global_track_id_rewrite_count"] == 0
