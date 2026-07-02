#!/usr/bin/env python3
"""Run all research module test suites with their required PYTHONPATH."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

SUITES = [
    ("D1", "research_modules/d1_sensor_fusion/src", "research_modules/d1_sensor_fusion/tests"),
    ("D2", "research_modules/d2_data_association", "research_modules/d2_data_association/tests"),
    ("D3", "research_modules/d3_assignment_planner/src", "research_modules/d3_assignment_planner/tests"),
    ("D4", "research_modules/d4_distributed_fallback", "research_modules/d4_distributed_fallback/tests"),
    ("D5", "research_modules/d5_terminal_association/src", "research_modules/d5_terminal_association/tests"),
    ("D6", "research_modules/d6_evaluation_metrics", "research_modules/d6_evaluation_metrics/tests"),
    ("D7", "research_modules/d7_proportional_guidance", "research_modules/d7_proportional_guidance/tests"),
    (
        "Integration",
        (
            "research_modules",
            "research_modules/d1_sensor_fusion/src",
            "research_modules/d2_data_association",
            "research_modules/d3_assignment_planner/src",
            "research_modules/d4_distributed_fallback",
            "research_modules/d5_terminal_association/src",
            "research_modules/d6_evaluation_metrics",
            "research_modules/d7_proportional_guidance",
        ),
        "research_modules/integration_tests",
    ),
    (
        "IntegratedSimulation",
        (
            "research_modules",
            "research_modules/d1_sensor_fusion/src",
            "research_modules/d2_data_association",
            "research_modules/d3_assignment_planner/src",
            "research_modules/d4_distributed_fallback",
            "research_modules/d5_terminal_association/src",
            "research_modules/d6_evaluation_metrics",
            "research_modules/d7_proportional_guidance",
        ),
        "research_modules/integrated_simulation/tests",
    ),
    (
        "AirSimDryRun",
        (
            "research_modules",
            "research_modules/d1_sensor_fusion/src",
            "research_modules/d2_data_association",
            "research_modules/d3_assignment_planner/src",
            "research_modules/d4_distributed_fallback",
            "research_modules/d5_terminal_association/src",
            "research_modules/d6_evaluation_metrics",
            "research_modules/d7_proportional_guidance",
        ),
        "research_modules/airsim_dryrun/tests",
    ),
    (
        "AirSimRuntime",
        (
            "research_modules",
            "research_modules/d1_sensor_fusion/src",
            "research_modules/d2_data_association",
            "research_modules/d3_assignment_planner/src",
            "research_modules/d4_distributed_fallback",
            "research_modules/d5_terminal_association/src",
            "research_modules/d6_evaluation_metrics",
            "research_modules/d7_proportional_guidance",
        ),
        "research_modules/airsim_runtime/tests",
    ),
]


def main() -> int:
    failures: list[str] = []
    for name, pythonpath, test_path in SUITES:
        env = os.environ.copy()
        if isinstance(pythonpath, tuple):
            env["PYTHONPATH"] = os.pathsep.join(str(ROOT / item) for item in pythonpath)
        else:
            env["PYTHONPATH"] = str(ROOT / pythonpath)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            str(ROOT / test_path),
        ]
        print(f"\n=== {name}: {' '.join(cmd)} ===")
        completed = subprocess.run(cmd, cwd=ROOT, env=env, check=False)
        if completed.returncode != 0:
            failures.append(name)
    if failures:
        print(f"\nFailed suites: {', '.join(failures)}")
        return 1
    print("\nAll research module tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
