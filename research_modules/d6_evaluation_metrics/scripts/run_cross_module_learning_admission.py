#!/usr/bin/env python3
"""Run the D6 read-only cross-module learning-data admission audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.cross_module_learning_admission import (  # noqa: E402
    CrossModuleLearningAdmissionError,
    CrossModuleLearningAdmissionInputs,
    write_cross_module_learning_data_admission_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-seed-registry", type=Path, required=True)
    parser.add_argument("--shared-seed-registry", type=Path, required=True)
    parser.add_argument("--d3-formal-manifest", type=Path, required=True)
    parser.add_argument("--d4-formal-manifest", type=Path, required=True)
    parser.add_argument("--d4-formal-canonical-view", type=Path, required=True)
    parser.add_argument(
        "--d4-formal-canonical-view-sha256",
        required=True,
        help="out-of-band SHA256 supplied by the D4 formal-view producer",
    )
    parser.add_argument("--d5-tracklet-formal-manifest", type=Path, required=True)
    parser.add_argument("--d5-tracklet-canonical-view", type=Path, required=True)
    parser.add_argument("--d5-tracklet-canonical-readiness", type=Path, required=True)
    parser.add_argument(
        "--d5-active-vision-formal-manifest", type=Path, required=True
    )
    parser.add_argument("--d5-active-vision-canonical-view", type=Path, required=True)
    parser.add_argument(
        "--d5-active-vision-canonical-readiness", type=Path, required=True
    )
    parser.add_argument("--d4-supplemental-summary", type=Path, required=True)
    parser.add_argument("--d5-supplemental-summary", type=Path, required=True)
    parser.add_argument(
        "--d5-supplemental-full-sample-audit", type=Path, required=True
    )
    parser.add_argument(
        "--d5-supplemental-full-sample-audit-sha256",
        required=True,
        help="out-of-band SHA256 supplied for the tracked D5 full-sample audit",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inputs = CrossModuleLearningAdmissionInputs(
        training_seed_registry_path=args.training_seed_registry,
        shared_seed_registry_path=args.shared_seed_registry,
        d3_formal_manifest_path=args.d3_formal_manifest,
        d4_formal_manifest_path=args.d4_formal_manifest,
        d4_formal_canonical_view_path=args.d4_formal_canonical_view,
        d4_formal_canonical_view_file_sha256=(
            args.d4_formal_canonical_view_sha256
        ),
        d5_tracklet_formal_manifest_path=args.d5_tracklet_formal_manifest,
        d5_tracklet_canonical_view_path=args.d5_tracklet_canonical_view,
        d5_tracklet_canonical_readiness_path=(
            args.d5_tracklet_canonical_readiness
        ),
        d5_active_vision_formal_manifest_path=(
            args.d5_active_vision_formal_manifest
        ),
        d5_active_vision_canonical_view_path=(
            args.d5_active_vision_canonical_view
        ),
        d5_active_vision_canonical_readiness_path=(
            args.d5_active_vision_canonical_readiness
        ),
        d4_supplemental_summary_path=args.d4_supplemental_summary,
        d5_supplemental_summary_path=args.d5_supplemental_summary,
        d5_supplemental_full_sample_audit_path=(
            args.d5_supplemental_full_sample_audit
        ),
        d5_supplemental_full_sample_audit_file_sha256=(
            args.d5_supplemental_full_sample_audit_sha256
        ),
    )
    try:
        outputs = write_cross_module_learning_data_admission_report(
            inputs, args.output_dir
        )
    except CrossModuleLearningAdmissionError as exc:
        print(
            json.dumps(
                {"status": "failed", "reason": exc.code},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        print(str(exc), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "ok",
                "json": str(outputs["json"]),
                "markdown": str(outputs["markdown"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
