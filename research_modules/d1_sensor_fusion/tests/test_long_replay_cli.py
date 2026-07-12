from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from d1_sensor_fusion import LONG_REPLAY_SUMMARY_SCHEMA_VERSION


MODULE_ROOT = Path(__file__).resolve().parents[1]
RUNNER = MODULE_ROOT / "scripts" / "run_long_replay.py"


def test_long_replay_cli_writes_requested_summary_json(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "summary.json"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--seed",
            "43",
            "--duration",
            "2",
            "--target-count",
            "1",
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert str(output_path) in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == LONG_REPLAY_SUMMARY_SCHEMA_VERSION
    assert payload["seed"] == 43
    assert payload["duration_s"] == 2.0
    assert payload["target_count"] == 1
    assert payload["observation_count"] > 0
    assert payload["online_truth_leak_count"] == 0
