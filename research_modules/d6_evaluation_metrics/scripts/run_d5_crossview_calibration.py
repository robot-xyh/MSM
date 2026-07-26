#!/usr/bin/env python3
"""Run offline D5 R0/G1 candidate-graph geometry calibration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.d5_crossview_calibration import (  # noqa: E402
    D5CrossviewCalibrationConfig,
    D5CrossviewCalibrationError,
    D5CrossviewDatasetInput,
    evaluate_d5_crossview_calibration,
    load_expected_seeds_file,
    write_d5_crossview_calibration_report,
)


def _dataset(value: str) -> D5CrossviewDatasetInput:
    variant, separator, raw_path = value.partition("=")
    if not separator or not variant.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("dataset must use VARIANT=/path syntax")
    try:
        return D5CrossviewDatasetInput(variant, Path(raw_path))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _variant_path(value: str) -> tuple[str, Path]:
    variant, separator, raw_path = value.partition("=")
    normalized = variant.strip().upper()
    if (
        not separator
        or normalized not in {"R0", "G1"}
        or not raw_path.strip()
    ):
        raise argparse.ArgumentTypeError(
            "frame sidecar must use R0=/path or G1=/path syntax"
        )
    return normalized, Path(raw_path).expanduser().resolve()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        action="append",
        type=_dataset,
        required=True,
        help=(
            "repeatable explicit candidate-graph dataset; R0/G1 label graph "
            "sources, not model scoring outputs"
        ),
    )
    parser.add_argument(
        "--frame-index-sidecar",
        action="append",
        type=_variant_path,
        default=(),
        help=(
            "repeatable stable frame coordinate sidecar; required for formal "
            "R0/G1 candidate-graph pairing"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("development", "formal"),
        default="development",
    )
    parser.add_argument(
        "--expected-seeds",
        nargs="*",
        type=int,
        default=(),
        help="explicit expected seed values; formal mode requires at least 20",
    )
    parser.add_argument(
        "--expected-seeds-file",
        type=Path,
        help="JSON list or newline/comma-separated expected seed values",
    )
    parser.add_argument(
        "--measurement-window-s",
        type=float,
        default=0.35,
    )
    parser.add_argument(
        "--arrival-window-s",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=2_000,
    )
    parser.add_argument(
        "--bootstrap-rng-seed",
        type=int,
        default=20260726,
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        sidecars: dict[str, Path] = {}
        for variant, path in args.frame_index_sidecar:
            if variant in sidecars:
                raise D5CrossviewCalibrationError(
                    "frame_index_sidecar_variant_duplicate",
                    variant,
                )
            sidecars[variant] = path
        dataset_variants = {item.variant for item in args.dataset}
        unknown_sidecars = sorted(set(sidecars) - dataset_variants)
        if unknown_sidecars:
            raise D5CrossviewCalibrationError(
                "frame_index_sidecar_without_dataset",
                str(unknown_sidecars),
            )
        datasets = tuple(
            D5CrossviewDatasetInput(
                item.variant,
                item.dataset_dir,
                sidecars.get(item.variant),
            )
            for item in args.dataset
        )
        file_seeds = (
            ()
            if args.expected_seeds_file is None
            else load_expected_seeds_file(args.expected_seeds_file)
        )
        if args.expected_seeds and file_seeds:
            raise D5CrossviewCalibrationError(
                "expected_seed_source_ambiguous",
                "use either --expected-seeds or --expected-seeds-file",
            )
        config = D5CrossviewCalibrationConfig(
            mode=args.mode,
            expected_seeds=tuple(args.expected_seeds) or file_seeds,
            measurement_window_s=args.measurement_window_s,
            arrival_window_s=args.arrival_window_s,
            bootstrap_resamples=args.bootstrap_resamples,
            bootstrap_rng_seed=args.bootstrap_rng_seed,
        )
        result = evaluate_d5_crossview_calibration(
            datasets,
            config=config,
        )
        paths = write_d5_crossview_calibration_report(
            args.output_dir,
            result,
            datasets=datasets,
        )
    except (D5CrossviewCalibrationError, OSError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": getattr(exc, "code", "invalid_input"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        print(str(exc), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                "evaluation_scope": result["evaluation_scope"],
                "formal_acceptance": result["formal_acceptance"],
                "json": str(paths["json"]),
                "csv": str(paths["csv"]),
                "markdown": str(paths["markdown"]),
                "checksums": str(paths["checksums"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 2 if result["status"] == "fail_closed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
