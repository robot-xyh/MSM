"""CLI for the D4 regional action-coverage curriculum."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Sequence

from .region_resource_curriculum import (
    RegionActionCoverageCurriculumConfig,
    generate_region_action_coverage_curriculum,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a truth-free, canonical-split D4 action-coverage curriculum. "
            "The output is restricted to behavior cloning and offline shadow use."
        )
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--training-seed-registry", type=Path, required=True)
    parser.add_argument("--shared-seed-registry", type=Path, required=True)
    parser.add_argument("--created-at-utc", required=True)
    parser.add_argument("--region-count", type=int, default=4)
    parser.add_argument("--resource-count", type=int, default=17)
    parser.add_argument("--frame-interval-s", type=float, default=1.0)
    parser.add_argument("--source-git-commit")
    parser.add_argument(
        "--source-repository-dirty",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument("--tracked-summary", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    commit, dirty = _git_provenance()
    if args.source_git_commit is not None:
        commit = args.source_git_commit
    if args.source_repository_dirty is not None:
        dirty = args.source_repository_dirty
    result = generate_region_action_coverage_curriculum(
        args.output_dir,
        training_seed_registry_path=args.training_seed_registry,
        shared_seed_registry_path=args.shared_seed_registry,
        created_at_utc=args.created_at_utc,
        source_git_commit=commit,
        source_repository_dirty=dirty,
        config=RegionActionCoverageCurriculumConfig(
            region_count=args.region_count,
            resource_count=args.resource_count,
            frame_interval_s=args.frame_interval_s,
        ),
        tracked_summary_path=args.tracked_summary,
    )
    summary = result.summary
    print(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "dataset_sha256": summary["dataset"]["dataset_sha256"],
                "episode_count": summary["dataset"]["episode_count"],
                "frame_count": summary["dataset"]["frame_count"],
                "canonical_seed_counts": summary["canonical"]["canonical_split"][
                    "seed_counts"
                ],
                "action_inventory": summary["action_inventory"]["total"],
                "hard_constraint_violation_count": summary["safety"][
                    "hard_constraint_violation_count"
                ],
                "reward_availability": summary["outcome_and_reward"][
                    "reward_availability"
                ],
                "ppo_available": summary["admission"]["ppo_available"],
                "online_assist_available": summary["admission"][
                    "online_assist_available"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


def _git_provenance() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[3]
    commit = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ("git", "status", "--porcelain"),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return commit, dirty


if __name__ == "__main__":
    raise SystemExit(main())
