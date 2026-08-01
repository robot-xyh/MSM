#!/usr/bin/env python3
"""Run the pinned D6 low-level audit for one active-vision candidate corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from d6_evaluation_metrics import (
    D5ActiveVisionCandidateAuditInputs,
    audit_d5_active_vision_candidate,
    write_d5_active_vision_candidate_audit_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--validation-date", required=True)
    parser.add_argument("--producer-commit", required=True)
    parser.add_argument("--generation-plan-sha256", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--checksums-sha256", required=True)
    parser.add_argument("--episode-count", type=int, required=True)
    parser.add_argument("--seed-first", type=int, required=True)
    parser.add_argument("--seed-last", type=int, required=True)
    parser.add_argument("--reserved-seed-first", type=int, required=True)
    parser.add_argument("--reserved-seed-last", type=int, required=True)
    parser.add_argument("--test-passed", type=int)
    parser.add_argument("--test-warning-count", type=int)
    parser.add_argument("--test-duration-seconds", type=float)
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = audit_d5_active_vision_candidate(
        D5ActiveVisionCandidateAuditInputs(
            dataset_root=args.dataset_root,
            expected_producer_git_commit=args.producer_commit,
            expected_generation_plan_sha256=args.generation_plan_sha256,
            expected_manifest_sha256=args.manifest_sha256,
            expected_checksums_sha256=args.checksums_sha256,
            expected_episode_count=args.episode_count,
            expected_seed_first=args.seed_first,
            expected_seed_last=args.seed_last,
            reserved_seed_first=args.reserved_seed_first,
            reserved_seed_last=args.reserved_seed_last,
        )
    )
    if result["status"] != "simulation_research_integrity_confirmed":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    test_values = (
        args.test_passed,
        args.test_warning_count,
        args.test_duration_seconds,
    )
    if any(value is not None for value in test_values) and not all(
        value is not None for value in test_values
    ):
        raise SystemExit("all three test summary arguments must be supplied together")
    software_validation = None
    if all(value is not None for value in test_values):
        software_validation = {
            "passed": args.test_passed,
            "warning_count": args.test_warning_count,
            "duration_seconds": args.test_duration_seconds,
        }
    hashes = write_d5_active_vision_candidate_audit_report(
        args.output_dir,
        result,
        validation_date=args.validation_date,
        software_validation=software_validation,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "check_counts": result["check_counts"],
                "output_hashes": hashes,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
