#!/usr/bin/env python3
"""Replay one scalable 3D online log and benchmark D5 rule paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
for path in (MODULE_ROOT / "src", REPOSITORY_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from d5_terminal_association.scalable_3d_performance import (
    add_scalable_3d_d5_baseline_comparison,
    run_scalable_3d_d5_performance_benchmark,
    write_scalable_3d_d5_performance_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online-log", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    parser.add_argument("--repeat-count", type=int, default=3)
    parser.add_argument("--active-iteration-count", type=int, default=20)
    parser.add_argument("--baseline-json", type=Path)
    parser.add_argument("--baseline-label", default="baseline")
    args = parser.parse_args()
    report = run_scalable_3d_d5_performance_benchmark(
        args.online_log,
        repeat_count=args.repeat_count,
        active_iteration_count=args.active_iteration_count,
    )
    if args.baseline_json is not None:
        baseline = json.loads(args.baseline_json.read_text(encoding="utf-8"))
        report = add_scalable_3d_d5_baseline_comparison(
            report,
            baseline,
            baseline_label=args.baseline_label,
        )
    write_scalable_3d_d5_performance_report(
        report,
        json_path=args.output_json,
        markdown_path=args.output_markdown,
    )
    terminal = report["terminal_replay"]
    active = report["active_vision_scale"]
    print(f"terminal_semantic_match={terminal['semantic_match']}")
    print(f"terminal_median_elapsed_s={terminal['median_elapsed_s']:.6f}")
    print(f"active_median_iteration_ms={active['median_iteration_ms']:.6f}")
    print(f"output_json={args.output_json.resolve()}")
    print(f"output_markdown={args.output_markdown.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
