"""Main command line for the frozen dual-optical online benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .batch import run_phase, run_preflight
from .contracts import (
    ROUTE_NAMES,
    SUPPORTED_TARGET_COUNTS,
    benchmark_protocol_for_target_count,
    benchmark_protocol_from_mapping,
)
from .orchestrator import freeze_all_routes, run_frozen_test
from .promotion import build_promotion_manifest, validate_previous_promotion


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUTS = Path(__file__).resolve().parent / "outputs"
SCALE_FUNNEL_OUTPUT_VERSION = "scale_funnel_v4"


def _tier_root(target_count: int, *, scan_profile: str = "continuous_360_v1") -> Path:
    if scan_profile == "s180_triangle_1s_v1":
        return DEFAULT_OUTPUTS / "s180_1s_sector_v1" / f"targets_{int(target_count):03d}"
    return (
        DEFAULT_OUTPUTS
        / SCALE_FUNNEL_OUTPUT_VERSION
        / f"targets_{int(target_count):03d}"
    )


def _add_target_count(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--target-count",
        type=int,
        choices=SUPPORTED_TARGET_COUNTS,
        default=None,
    )


def _add_protocol_file(command: argparse.ArgumentParser) -> None:
    command.add_argument("--protocol-file", type=Path, default=None)


def _load_protocol(path: Path | None, target_count: int | None):
    if path is None:
        return benchmark_protocol_for_target_count(target_count or 100)
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("protocol", payload)
    protocol = benchmark_protocol_from_mapping(values)
    recorded_fingerprint = payload.get("protocol_fingerprint")
    if recorded_fingerprint not in {None, protocol.fingerprint}:
        raise ValueError("protocol file fingerprint mismatch")
    if target_count is not None and protocol.target_count != int(target_count):
        raise ValueError("--target-count does not match --protocol-file")
    return protocol


def _default_previous_promotion(target_count: int) -> Path | None:
    tiers = list(SUPPORTED_TARGET_COUNTS)
    index = tiers.index(int(target_count))
    if index == 0:
        return None
    return _tier_root(tiers[index - 1]) / "results" / "promotion_manifest.json"


def _add_previous_promotion(command: argparse.ArgumentParser) -> None:
    command.add_argument("--previous-promotion", type=Path, default=None)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    _add_target_count(preflight)
    _add_protocol_file(preflight)
    _add_previous_promotion(preflight)
    preflight.add_argument("--output-root", type=Path)
    preflight.add_argument("--api-port", type=int, default=41451)
    preflight.add_argument("--max-attempts", type=int, default=2)
    preflight.add_argument("--episode-timeout-s", type=float, default=900.0)
    preflight.add_argument(
        "--blocks-script", type=Path,
        default=REPO_ROOT / "Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh",
    )
    generate = sub.add_parser("generate")
    _add_target_count(generate)
    _add_protocol_file(generate)
    _add_previous_promotion(generate)
    generate.add_argument("phase", choices=("calibration", "test"))
    generate.add_argument("--output-root", type=Path)
    generate.add_argument("--dataset-root", type=Path)
    generate.add_argument("--api-port", type=int, default=41451)
    generate.add_argument("--max-attempts", type=int, default=2)
    generate.add_argument("--episode-timeout-s", type=float, default=900.0)
    generate.add_argument(
        "--blocks-script", type=Path,
        default=REPO_ROOT / "Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh",
    )
    generate.add_argument(
        "--preflight-summary",
        type=Path,
        default=None,
    )
    freeze = sub.add_parser("freeze")
    _add_target_count(freeze)
    _add_protocol_file(freeze)
    _add_previous_promotion(freeze)
    freeze.add_argument(
        "--active-route",
        action="append",
        choices=ROUTE_NAMES,
        dest="active_routes",
    )
    freeze.add_argument(
        "--calibration-manifest", type=Path,
        default=None,
    )
    freeze.add_argument("--output-root", type=Path)
    evaluate = sub.add_parser("evaluate")
    _add_target_count(evaluate)
    _add_protocol_file(evaluate)
    evaluate.add_argument(
        "--test-manifest", type=Path,
        default=None,
    )
    evaluate.add_argument(
        "--freeze-marker", type=Path,
        default=None,
    )
    evaluate.add_argument("--output-dir", type=Path)
    promote = sub.add_parser("promote")
    _add_target_count(promote)
    promote.add_argument("--metrics", type=Path, default=None)
    promote.add_argument("--output", type=Path, default=None)
    v41 = sub.add_parser(
        "v41-replay",
        help="replay sealed V4 data through deterministic target handover",
    )
    v41.add_argument("--source-root", type=Path, required=True)
    v41.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUTS / "scale_funnel_v4_1_deterministic_handover",
    )
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "v41-replay":
        from .v41_replay import run_v41_replay

        print(run_v41_replay(args.source_root, args.output_root))
        return 0
    protocol = _load_protocol(
        getattr(args, "protocol_file", None), args.target_count
    )
    target_count = protocol.target_count
    tier_root = _tier_root(target_count, scan_profile=protocol.scan_profile)
    previous = None
    if (
        args.command in {"preflight", "generate", "freeze"}
        and target_count > 20
        and protocol.is_legacy_continuous_profile
    ):
        previous = validate_previous_promotion(
            args.previous_promotion
            or _default_previous_promotion(target_count),
            requested_target_count=target_count,
        )
    if args.command == "preflight":
        summary = run_preflight(
            repo_root=REPO_ROOT,
            output_root=args.output_root or tier_root / "preflight",
            blocks_script=args.blocks_script,
            api_port=args.api_port,
            max_attempts=args.max_attempts,
            episode_timeout_s=args.episode_timeout_s,
            protocol=protocol,
        )
        print(summary)
        return 0
    if args.command == "generate":
        seeds = (
            protocol.train_seeds + protocol.validation_seeds
            if args.phase == "calibration"
            else protocol.test_seeds
        )
        print(run_phase(
            repo_root=REPO_ROOT,
            output_root=args.output_root or tier_root / "raw",
            dataset_root=args.dataset_root or tier_root / "dataset",
            seeds=seeds,
            phase=args.phase,
            blocks_script=args.blocks_script,
            api_port=args.api_port,
            max_attempts=args.max_attempts,
            episode_timeout_s=args.episode_timeout_s,
            preflight_summary=(
                args.preflight_summary
                or tier_root / "preflight" / "preflight_summary.json"
            ),
            protocol=protocol,
        ))
    elif args.command == "freeze":
        active_routes = tuple(
            args.active_routes
            or (
                previous.get("eligible_routes", previous["promoted_routes"])
                if previous is not None
                else ROUTE_NAMES
            )
        )
        print(freeze_all_routes(
            args.calibration_manifest
            or tier_root / "dataset" / "calibration_manifest.json",
            args.output_root or tier_root / "dataset",
            active_routes=active_routes,
        ))
    elif args.command == "evaluate":
        print(run_frozen_test(
            args.test_manifest or tier_root / "dataset" / "test_manifest.json",
            args.freeze_marker
            or tier_root / "dataset" / "freezes" / "all_routes_frozen.json",
            args.output_dir or tier_root / "results",
        ))
    elif args.command == "promote":
        target_count = args.target_count or 100
        tier_root = _tier_root(target_count)
        print(build_promotion_manifest(
            args.metrics or tier_root / "results" / "comparison_metrics.json",
            args.output,
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
