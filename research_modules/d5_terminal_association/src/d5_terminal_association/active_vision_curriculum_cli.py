"""CLI for the detached D5 100-seed supplemental active-vision curriculum."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Sequence

from .active_vision_curriculum_dataset import (
    generate_active_vision_supplemental_curriculum,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a synthetic, truth-free D5 active-vision curriculum with "
            "the shared canonical 60/20/20 seed view."
        )
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--training-seed-registry", type=Path, required=True)
    parser.add_argument("--shared-seed-registry", type=Path, required=True)
    parser.add_argument("--created-at-utc", required=True)
    parser.add_argument("--global-track-id", required=True)
    parser.add_argument("--tracked-summary-json", type=Path)
    parser.add_argument("--tracked-report-markdown", type=Path)
    parser.add_argument("--source-git-commit")
    parser.add_argument(
        "--source-repository-dirty",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    commit, dirty = _git_provenance()
    if args.source_git_commit is not None:
        commit = args.source_git_commit
    if args.source_repository_dirty is not None:
        dirty = args.source_repository_dirty
    result = generate_active_vision_supplemental_curriculum(
        args.output_dir,
        training_seed_registry_path=args.training_seed_registry,
        shared_seed_registry_path=args.shared_seed_registry,
        created_at_utc=args.created_at_utc,
        global_track_id=args.global_track_id,
        source_git_commit=commit,
        source_repository_dirty=dirty,
        tracked_summary_path=args.tracked_summary_json,
        tracked_markdown_path=args.tracked_report_markdown,
    )
    summary = result.summary
    print(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "dataset_manifest_sha256": summary["dataset"]["manifest_sha256"],
                "canonical_view_sha256": summary["canonical"][
                    "view_manifest_sha256"
                ],
                "episode_count": summary["coverage"]["episode_count"],
                "sample_count": summary["coverage"]["sample_count"],
                "canonical_seed_counts": summary["canonical"]["split"][
                    "seed_counts"
                ],
                "status": summary["admission"]["status"],
                "ppo_available": summary["admission"]["ppo_available"],
                "online_assist_available": summary["admission"][
                    "online_assist_available"
                ],
                "online_authority_available": summary["admission"][
                    "online_authority_available"
                ],
            },
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
        )
    )
    return 0


def _git_provenance() -> tuple[str, bool]:
    repository_root = Path(__file__).resolve().parents[4]
    commit = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ("git", "status", "--porcelain"),
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return commit, dirty


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI.
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
