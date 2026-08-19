#!/usr/bin/env python3
"""Main-owned reset/retry orchestration for dense 100-target AirSim episodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = (
    REPO_ROOT
    / "research_modules"
    / "independent_experiments"
    / "dual_optical_40target"
    / "run_experiment.py"
)
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT
    / "research_modules"
    / "independent_experiments"
    / "dual_optical_100target_gnn"
    / "outputs"
    / "raw_airsim"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-start", type=int, default=20260820)
    parser.add_argument("--seed-end", type=int, default=20260831)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--api-port", type=int, default=41451)
    return parser.parse_args()


def airsim_ready(api_port: int) -> bool:
    try:
        import airsim

        return bool(airsim.VehicleClient(port=api_port, timeout_value=5).ping())
    except Exception:
        return False


def reset_airsim(api_port: int) -> None:
    import airsim

    client = airsim.VehicleClient(port=api_port, timeout_value=10)
    client.simPause(False)
    client.reset()
    time.sleep(1.0)


def run_seed(seed: int, output_root: Path, max_attempts: int, api_port: int) -> dict[str, object]:
    output_dir = output_root / f"airsim_seed_{seed}_dense100"
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "record_manifest.json").is_file() and (
        output_dir / "metrics.json"
    ).is_file():
        print(f"seed={seed} reused_completed_episode=True", flush=True)
        return {
            "seed": seed,
            "output_dir": str(output_dir.relative_to(output_root)),
            "completed": True,
            "reused_completed_episode": True,
            "attempts": [],
        }
    if not airsim_ready(api_port):
        print(f"seed={seed} airsim_unavailable=True", flush=True)
        return {
            "seed": seed,
            "output_dir": str(output_dir.relative_to(output_root)),
            "completed": False,
            "reused_completed_episode": False,
            "failure_reason": "airsim_unavailable_before_episode",
            "attempts": [],
        }
    attempts: list[dict[str, object]] = []
    completed = False
    for attempt in range(1, max_attempts + 1):
        command = [
            sys.executable,
            str(RUNNER),
            "--no-launch",
            "--target-count",
            "100",
            "--seed",
            str(seed),
            "--api-port",
            str(api_port),
            "--output-dir",
            str(output_dir),
        ]
        started = time.perf_counter()
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        log_path = output_dir / f"main_attempt_{attempt}.log"
        log_path.write_text(
            result.stdout + ("\n[stderr]\n" + result.stderr if result.stderr else ""),
            encoding="utf-8",
        )
        has_records = (output_dir / "record_manifest.json").is_file()
        has_metrics = (output_dir / "metrics.json").is_file()
        completed = bool(has_records and has_metrics and result.returncode in {0, 2})
        attempts.append(
            {
                "attempt": attempt,
                "returncode": result.returncode,
                "duration_s": time.perf_counter() - started,
                "record_manifest_present": has_records,
                "metrics_present": has_metrics,
                "log": str(log_path.relative_to(output_root)),
            }
        )
        print(
            f"seed={seed} attempt={attempt} returncode={result.returncode} "
            f"records={has_records} completed={completed}",
            flush=True,
        )
        if completed:
            break
        if not airsim_ready(api_port):
            break
        reset_airsim(api_port)
    return {
        "seed": seed,
        "output_dir": str(output_dir.relative_to(output_root)),
        "completed": completed,
        "reused_completed_episode": False,
        "attempts": attempts,
    }


def main() -> int:
    args = parse_args()
    if args.seed_end < args.seed_start:
        raise ValueError("seed-end must be greater than or equal to seed-start")
    if args.max_attempts < 1:
        raise ValueError("max-attempts must be positive")
    if not airsim_ready(args.api_port):
        raise RuntimeError(f"AirSim RPC port {args.api_port} is unavailable")

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    results = [
        run_seed(seed, output_root, args.max_attempts, args.api_port)
        for seed in range(args.seed_start, args.seed_end + 1)
    ]
    payload = {
        "schema_version": "dual-optical-100target-main-batch-v1",
        "main_owned_orchestration": True,
        "blocks_launch_count_for_batch": 1,
        "screenshots_saved": False,
        "seed_start": args.seed_start,
        "seed_end": args.seed_end,
        "completed_seed_count": sum(bool(item["completed"]) for item in results),
        "results": results,
    }
    summary_path = output_root / "batch_summary.json"
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(summary_path)
    return 0 if all(bool(item["completed"]) for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
