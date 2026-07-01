#!/usr/bin/env python3
"""Run representative smoke simulations for all research modules."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

COMMANDS = [
    (
        "D1",
        "research_modules/d1_sensor_fusion/src",
        [
            "research_modules/d1_sensor_fusion/scripts/run_simulation.py",
            "--targets",
            "3",
            "--duration",
            "60",
            "--dt",
            "0.1",
            "--seed",
            "7",
            "--output",
            "research_modules/d1_sensor_fusion/reports",
        ],
    ),
    (
        "D2",
        "research_modules/d2_data_association",
        ["research_modules/d2_data_association/scripts/run_simulation.py", "--steps", "24", "--seed", "7"],
    ),
    (
        "D3",
        "research_modules/d3_assignment_planner/src",
        ["research_modules/d3_assignment_planner/simulations/run_rolling_assignment.py"],
    ),
    (
        "D4",
        "research_modules/d4_distributed_fallback",
        [
            "research_modules/d4_distributed_fallback/scripts/run_failover_simulation.py",
            "--nodes",
            "5",
            "--tasks",
            "4",
            "--packet-loss",
            "0.10",
            "--seed",
            "7",
        ],
    ),
    (
        "D5",
        "research_modules/d5_terminal_association/src",
        [
            "research_modules/d5_terminal_association/simulations/run_terminal_association_sim.py",
            "--frames",
            "120",
            "--seed",
            "7",
        ],
    ),
    (
        "D6",
        "research_modules/d6_evaluation_metrics",
        [
            "research_modules/d6_evaluation_metrics/scripts/run_batch_example.py",
            "--seeds",
            "20",
            "--output",
            "research_modules/d6_evaluation_metrics/outputs/integration_smoke",
        ],
    ),
]


def main() -> int:
    failures: list[str] = []
    for name, pythonpath, args in COMMANDS:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / pythonpath)
        cmd = [sys.executable, *[str(ROOT / arg) if arg.endswith(".py") else arg for arg in args]]
        print(f"\n=== {name}: {' '.join(cmd)} ===")
        completed = subprocess.run(cmd, cwd=ROOT, env=env, check=False)
        if completed.returncode != 0:
            failures.append(name)
    if failures:
        print(f"\nFailed simulations: {', '.join(failures)}")
        return 1
    print("\nAll smoke simulations completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
