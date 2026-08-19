#!/usr/bin/env python3
"""Prepare, run, or report the independent dual-optical 100-target guide case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_PARENT = Path(__file__).resolve().parents[1]
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from dual_optical_100target_guide_case.build_word_report import build_document  # noqa: E402
from dual_optical_100target_guide_case.core import CameraSpec, ScenarioConfig  # noqa: E402
from dual_optical_100target_guide_case.reporting import generate_experiment_report  # noqa: E402
from dual_optical_100target_guide_case.runtime import (  # noqa: E402
    GuideCaseAirSimRunner,
    load_experiment_result,
    prepare_case,
    run_synthetic_fixture,
    write_json,
)


DEFAULT_OUTPUT = Path(__file__).resolve().parent / "outputs" / "airsim_seed_20260812_guide_run01"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--run-airsim", action="store_true", help="connect to Blocks already started by main")
    action.add_argument("--synthetic-fixture", action="store_true", help="generate non-AirSim deterministic validation records")
    action.add_argument("--report-only", action="store_true", help="rebuild report from completed records")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--api-port", type=int, default=41451)
    parser.add_argument("--connection-timeout-s", type=float, default=45.0)
    parser.add_argument("--skip-word", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = ScenarioConfig(seed=args.seed, api_port=args.api_port)
    camera = CameraSpec()
    if args.report_only:
        result = load_experiment_result(args.output_dir)
    elif args.synthetic_fixture:
        result = run_synthetic_fixture(args.output_dir, config, camera)
    elif args.run_airsim:
        result = GuideCaseAirSimRunner(
            config=config,
            camera=camera,
            output_dir=args.output_dir,
            connection_timeout_s=args.connection_timeout_s,
        ).run()
    else:
        paths = prepare_case(args.output_dir, config, camera)
        print(f"prepared={args.output_dir.resolve()}")
        print(f"settings={paths['settings'].resolve()}")
        print("Blocks must be started by main with this settings.json before --run-airsim.")
        return 0

    reports = generate_experiment_report(result)
    word_path = reports["report"].with_suffix(".docx")
    word_metrics = None
    if not args.skip_word:
        word_metrics = build_document(reports["report"], word_path)
    manifest_path = result.output_dir / "record_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["report_artifacts"] = {
        name: str(path.relative_to(result.output_dir))
        for name, path in reports.items()
    }
    if not args.skip_word:
        manifest["report_artifacts"]["word"] = str(word_path.relative_to(result.output_dir))
        manifest["word_validation"] = word_metrics
    write_json(manifest_path, manifest)
    stage = result.metrics["association_stages"]["scan_hungarian_and_vote"]
    print(f"output_dir={result.output_dir.resolve()}")
    print(f"report={reports['report'].resolve()}")
    if not args.skip_word:
        print(f"word={word_path.resolve()}")
    print(
        "selected={selected} correct={correct} false={false} precision={precision:.4f} "
        "recall={recall:.4f} formal_airsim={formal}".format(
            selected=stage["selected_match_count"],
            correct=stage["correct_match_count"],
            false=stage["false_match_count"],
            precision=stage["association_precision"],
            recall=stage["unique_target_recall"],
            formal=result.metrics["formal_airsim_result"],
        )
    )
    return 0 if result.metrics["acceptance"]["overall_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
