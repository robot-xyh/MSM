#!/usr/bin/env python3
"""Run a 100-seed synthetic offline D6 evaluation example."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.reporting import ReportGenerator
from d6_evaluation_metrics.simulation import (
    generate_synthetic_episode,
    write_episode_log_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic offline logs and D6 evaluation reports."
    )
    parser.add_argument("--seeds", type=int, default=100, help="Number of seeds to run.")
    parser.add_argument(
        "--seed-start",
        type=int,
        default=0,
        help="First integer seed in the batch.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Synthetic episode duration in seconds.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=MODULE_ROOT / "outputs" / "example_batch",
        help="Directory for logs, tables, report, and plots.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.seeds <= 0:
        raise SystemExit("--seeds must be positive")
    if args.duration <= 0:
        raise SystemExit("--duration must be positive")

    output_dir = args.output_dir
    logs_dir = output_dir / "logs"
    plots_dir = output_dir / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    episodes = []
    for seed in range(args.seed_start, args.seed_start + args.seeds):
        collector, truth_summary = generate_synthetic_episode(
            seed=seed,
            duration=args.duration,
        )
        episode = collector.compute_episode(
            episode_id=f"synthetic_{seed:04d}",
            seed=seed,
            duration=args.duration,
            truth_summary=truth_summary,
        )
        episodes.append(episode)
        write_episode_log_jsonl(
            collector=collector,
            truth_summary=truth_summary,
            path=logs_dir / f"episode_{seed:04d}.jsonl",
        )

    report_generator = ReportGenerator()
    episode_csv = report_generator.write_episode_csv(
        episodes,
        output_dir / "episode_metrics.csv",
    )
    summary_csv = report_generator.write_summary_csv(
        episodes,
        output_dir / "summary_metrics.csv",
    )
    markdown_report = report_generator.write_markdown_report(
        episodes,
        output_dir / "batch_report.md",
        title="D6 合成 100 种子离线评估",
    )
    plots = report_generator.write_plots(episodes, plots_dir)

    print(f"Wrote {len(episodes)} synthetic episodes")
    print(f"Episode metrics: {episode_csv}")
    print(f"Summary metrics: {summary_csv}")
    print(f"Markdown report: {markdown_report}")
    print(f"Plots: {plots_dir} ({len(plots)} files)")
    print(f"Raw JSONL logs: {logs_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
