import json
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPOSITORY_ROOT
    / "research_modules"
    / "d3_assignment_planner"
    / "simulations"
    / "run_learning_export_profile.py"
)


def test_learning_export_profile_is_reproducible_without_wall_clock_gate(
    tmp_path: Path,
) -> None:
    output = tmp_path / "profile.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--count",
            "5",
            "--max-candidate-edges",
            "2",
            "--frame-count",
            "3",
            "--repeat",
            "1",
            "--output",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    stdout_payload = json.loads(completed.stdout)
    file_payload = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["schema"] == "d3_learning_export_microprofile_v1"
    assert file_payload["fixture"]["target_count"] == 5
    assert file_payload["fixture"]["resource_count"] == 5
    assert file_payload["fixture"]["candidate_edge_count"] <= 10
    assert file_payload["fixture"]["frame_count"] == 3
    assert file_payload["contract"] == {
        "dataset_schema": "d3_learning_dataset_v2",
        "split_policy": "d3_numeric_seed_atomic_split_v2",
        "timings_are_acceptance_thresholds": False,
        "truth_fields_allowed": False,
    }
    assert all(
        float(value) >= 0.0
        for key, value in file_payload["timings_s"].items()
        if key != "dataset_finalize_runs"
    )
    assert all(
        float(value) >= 0.0
        for value in file_payload["timings_s"]["dataset_finalize_runs"]
    )
