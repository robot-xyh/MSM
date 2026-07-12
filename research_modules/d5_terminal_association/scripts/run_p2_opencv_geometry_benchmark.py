#!/usr/bin/env python3
"""Run the isolated D5 OpenCV calibration/solvePnP benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from d5_terminal_association.p2_geometry_benchmark import (  # noqa: E402
    OpenCvGeometryBenchmarkConfig,
    run_opencv_geometry_perturbation_benchmark,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline-only D5 OpenCV calibration/solvePnP perturbation benchmark"
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--tracks", type=int, default=8)
    parser.add_argument("--calibration-views", type=int, default=8)
    parser.add_argument(
        "--translation-drift-m",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        default=(0.35, -0.20, 0.12),
    )
    parser.add_argument(
        "--rotation-drift-deg",
        nargs=3,
        type=float,
        metavar=("ROLL", "PITCH", "YAW"),
        default=(1.2, -0.9, 0.6),
    )
    parser.add_argument("--measurement-bias-s", type=float, default=0.08)
    parser.add_argument("--arrival-latency-s", type=float, default=0.30)
    parser.add_argument("--arrival-bias-s", type=float, default=0.18)
    parser.add_argument("--gate-chi2", type=float, default=9.21)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = OpenCvGeometryBenchmarkConfig(
        seed=args.seed,
        frame_count=args.frames,
        track_count=args.tracks,
        calibration_view_count=args.calibration_views,
        translation_drift_m=tuple(args.translation_drift_m),
        rotation_drift_deg=tuple(args.rotation_drift_deg),
        measurement_timestamp_bias_s=args.measurement_bias_s,
        nominal_arrival_latency_s=args.arrival_latency_s,
        arrival_timestamp_bias_s=args.arrival_bias_s,
        gate_chi2=args.gate_chi2,
    )
    result = run_opencv_geometry_perturbation_benchmark(config)
    payload = result.to_dict()
    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result.available else 2


if __name__ == "__main__":
    raise SystemExit(main())
