"""CLI and main-callable entry point for the independent search experiment."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .fake_client import FakeAirSimModule, GeometricFakeAirSimClient
from .fixture import build_default_fixture, load_fixture
from .models import SearchExperimentConfig
from .runtime import AirSimSearchAdapter, SearchExperimentResult, SearchExperimentRunner


def run_experiment(
    *,
    mode: str,
    output_dir: Path,
    fixture_dir: Path | None = None,
    target_count: int | None = None,
    resource_count: int = 8,
    seed: int | None = None,
    client: Any | None = None,
    airsim_module: Any | None = None,
    assignment_cycles: int = 3,
    frames_per_assignment: int = 3,
    api_port: int = 41451,
) -> SearchExperimentResult:
    """Run one episode without launching, resetting, or closing AirSim Blocks."""

    if mode not in {"offline", "airsim"}:
        raise ValueError("mode must be 'offline' or 'airsim'")
    if fixture_dir is not None:
        fixture = load_fixture(Path(fixture_dir), target_count=target_count, seed=seed)
    else:
        fixture = build_default_fixture(
            target_count=5 if target_count is None else target_count,
            seed=20260816 if seed is None else seed,
        )
    config = SearchExperimentConfig(
        target_count=fixture.scenario.target_count,
        resource_count=resource_count,
        seed=fixture.scenario.seed,
        assignment_cycles=assignment_cycles,
        frames_per_assignment=frames_per_assignment,
    )
    if mode == "offline":
        if client is None:
            client = GeometricFakeAirSimClient(
                fixture.targets,
                image_width=config.image_width,
                image_height=config.image_height,
                horizontal_fov_deg=config.horizontal_fov_deg,
            )
        if airsim_module is None:
            airsim_module = FakeAirSimModule
    truth_map = {target.actor_name: target.truth_target_id for target in fixture.targets}
    adapter = AirSimSearchAdapter(
        config,
        client=client,
        airsim_module=airsim_module,
        truth_name_to_id=truth_map,
        api_port=api_port,
    )
    runner = SearchExperimentRunner(
        config=config,
        source_cues=fixture.source_cues,
        source_truth_labels=fixture.source_truth_labels,
        targets=fixture.targets,
        adapter=adapter,
        fixture_source=fixture.source,
        data_source=("offline_geometric_fake_client" if mode == "offline" else "airsim_computervision"),
    )
    result = runner.run()
    from .reporting import write_experiment_outputs

    write_experiment_outputs(result, Path(output_dir))
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "airsim"), required=True)
    parser.add_argument("--fixture-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--target-count",
        type=int,
        help="generated-fixture size; with --fixture-dir it must match scenario.json",
    )
    parser.add_argument("--resource-count", type=int, default=8)
    parser.add_argument(
        "--seed",
        type=int,
        help="generated-fixture seed; with --fixture-dir it must match scenario.json",
    )
    parser.add_argument("--assignment-cycles", type=int, default=3)
    parser.add_argument(
        "--frames-per-assignment",
        type=int,
        default=3,
        help="camera observations per assigned cell; confirmation still requires two consecutive frames",
    )
    parser.add_argument("--api-port", type=int, default=41451)
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = run_experiment(
        mode=args.mode,
        fixture_dir=args.fixture_dir,
        output_dir=args.output_dir,
        target_count=args.target_count,
        resource_count=args.resource_count,
        seed=args.seed,
        assignment_cycles=args.assignment_cycles,
        frames_per_assignment=args.frames_per_assignment,
        api_port=args.api_port,
    )
    print(Path(args.output_dir) / "metrics.json")
    print(Path(args.output_dir) / "REPORT_CN.md")
    return 0 if result.metrics["online_truth_leakage_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
