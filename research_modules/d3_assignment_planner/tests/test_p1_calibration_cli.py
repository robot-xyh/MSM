import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPOSITORY_ROOT
    / "research_modules"
    / "d3_assignment_planner"
    / "simulations"
    / "run_p1_assignment_calibration.py"
)


def test_calibration_cli_writes_requested_json_and_keeps_stdout(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "d3_p1_summary.json"

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output_path)],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    stdout_summary = json.loads(completed.stdout)
    file_summary = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_summary == file_summary
    assert stdout_summary["profile_id"] == "d3_p1_nm_feedback_governance"
    assert stdout_summary["transition_count"] == 8
