"""CLI for D5 formal audit, supplemental generation, and detached admission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Sequence

from .tracklet_supplemental_admission import (
    write_composite_admission_report,
    write_tracklet_composite_admission_view,
)
from .tracklet_supplemental_curriculum import (
    generate_tracklet_supplemental_curriculum,
)
from .tracklet_unlabeled_audit import (
    audit_formal_unlabeled_edges,
    write_unlabeled_audit,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    commit, dirty = _git_provenance()
    audit = audit_formal_unlabeled_edges(args.formal_dataset)
    audit_hashes = write_unlabeled_audit(
        audit,
        json_path=args.unlabeled_audit_json,
        markdown_path=args.unlabeled_audit_markdown,
    )
    curriculum = generate_tracklet_supplemental_curriculum(
        args.output_dir,
        formal_dataset_dir=args.formal_dataset,
        training_seed_registry_path=args.training_seed_registry,
        shared_seed_registry_path=args.shared_seed_registry,
        created_at_utc=args.created_at_utc,
        source_git_commit=commit,
        source_repository_dirty=dirty,
    )
    admission = write_tracklet_composite_admission_view(
        formal_dataset_dir=args.formal_dataset,
        supplemental_root=curriculum.output_dir,
        training_seed_registry_path=args.training_seed_registry,
        shared_seed_registry_path=args.shared_seed_registry,
        view_manifest_path=args.admission_view,
    )
    admission_hashes = write_composite_admission_report(
        admission,
        json_path=args.admission_report_json,
        markdown_path=args.admission_report_markdown,
    )
    if args.curriculum_summary_json:
        _copy_exact(
            curriculum.output_dir / "curriculum_summary.json",
            Path(args.curriculum_summary_json),
        )
    if args.curriculum_report_markdown:
        _copy_exact(
            curriculum.output_dir / "curriculum_report.md",
            Path(args.curriculum_report_markdown),
        )
    print(
        json.dumps(
            {
                "formal_unlabeled_edges": audit["summary"][
                    "unlabeled_candidate_edge_count"
                ],
                "formal_recoverable_edges": audit["summary"]["recoverable_edge_count"],
                "supplemental_episode_count": curriculum.summary["episode_count"],
                "supplemental_candidate_edge_count": curriculum.summary[
                    "candidate_edge_count"
                ],
                "supplemental_manifest_sha256": curriculum.manifest_sha256,
                "admission_view_sha256": admission.view_manifest_sha256,
                "data_support_status": admission.readiness["data_support_readiness"][
                    "status"
                ],
                "training_readiness_status": admission.readiness[
                    "training_readiness"
                ]["status"],
                "g1_assist_eligible": False,
                "audit_artifact_sha256": audit_hashes,
                "admission_artifact_sha256": admission_hashes,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the independent D5 hard cross-view curriculum"
    )
    parser.add_argument("--formal-dataset", required=True)
    parser.add_argument("--training-seed-registry", required=True)
    parser.add_argument("--shared-seed-registry", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--created-at-utc", required=True)
    parser.add_argument("--admission-view", required=True)
    parser.add_argument("--unlabeled-audit-json", required=True)
    parser.add_argument("--unlabeled-audit-markdown", required=True)
    parser.add_argument("--admission-report-json", required=True)
    parser.add_argument("--admission-report-markdown", required=True)
    parser.add_argument("--curriculum-summary-json")
    parser.add_argument("--curriculum-report-markdown")
    return parser


def _git_provenance() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[4]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, bool(status.strip())


def _copy_exact(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        temporary.write_bytes(source.read_bytes())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
