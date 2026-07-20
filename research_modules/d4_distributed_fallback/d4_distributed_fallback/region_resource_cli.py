"""CLI for D4 regional resource recommendation research workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .region_resource import (
    AdvisorMode,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceSnapshot,
    ShadowEpisodeMetrics,
    ShadowPairedEvaluator,
)
from .region_resource_learning import (
    RegionResourceAdvisor,
    RegionResourceAdvisorConfig,
)
from .regional_failover import RegionalAuthorityLayer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the optional D4 regional resource advisor. Outputs remain advisory "
            "and never replace formal D4/D3/D7 gates."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="run a deterministic variable-region demo")
    demo.add_argument("--region-count", type=int, default=8)
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument(
        "--owner-layer",
        choices=("center", "secondary", "distributed"),
        default="center",
    )
    _add_advisor_arguments(demo)
    demo.add_argument("--output", type=Path)

    recommend = subparsers.add_parser(
        "recommend", help="produce advice from a versioned snapshot JSON"
    )
    recommend.add_argument("--snapshot", type=Path, required=True)
    _add_advisor_arguments(recommend)
    recommend.add_argument("--output", type=Path)

    shadow = subparsers.add_parser(
        "shadow-evaluate", help="evaluate paired baseline/candidate seed records"
    )
    shadow.add_argument("--baseline", type=Path, required=True)
    shadow.add_argument("--candidate", type=Path, required=True)
    shadow.add_argument("--training-groups", type=Path)
    shadow.add_argument("--minimum-unseen-seeds", type=int, default=20)
    shadow.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        if args.region_count <= 0:
            raise ValueError("region-count must be positive")
        snapshot = _demo_snapshot(
            region_count=args.region_count,
            seed=args.seed,
            owner_layer=RegionalAuthorityLayer(args.owner_layer),
        )
        result = _advisor(args).advise(
            snapshot, unseen_seed_count=args.unseen_seed_count
        )
        _emit(
            {
                "snapshot": snapshot.to_dict(),
                "advisory_result": result.to_dict(),
            },
            args.output,
        )
        return 0
    if args.command == "recommend":
        payload = _load_json(args.snapshot)
        snapshot_payload = payload.get("snapshot", payload) if isinstance(payload, dict) else payload
        if not isinstance(snapshot_payload, dict):
            raise ValueError("snapshot input must be a JSON object")
        snapshot = RegionResourceSnapshot.from_dict(snapshot_payload)
        result = _advisor(args).advise(
            snapshot, unseen_seed_count=args.unseen_seed_count
        )
        _emit(result.to_dict(), args.output)
        return 0
    if args.command == "shadow-evaluate":
        baseline = _load_shadow_records(args.baseline)
        candidate = _load_shadow_records(args.candidate)
        training_groups = _load_training_groups(args.training_groups)
        report = ShadowPairedEvaluator(args.minimum_unseen_seeds).evaluate(
            baseline,
            candidate,
            training_groups=training_groups,
        )
        _emit(report.to_dict(), args.output)
        return 0
    raise RuntimeError(f"unsupported command: {args.command}")


def _add_advisor_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in AdvisorMode),
        default=AdvisorMode.SHADOW.value,
    )
    parser.add_argument("--bundle-dir", type=Path)
    parser.add_argument("--expected-model-version")
    parser.add_argument("--expected-state-dict-sha256")
    parser.add_argument("--timeout-ms", type=float, default=50.0)
    parser.add_argument("--minimum-confidence", type=float, default=0.60)
    parser.add_argument("--ood-margin", type=float, default=0.05)
    parser.add_argument("--minimum-unseen-seeds", type=int, default=20)
    parser.add_argument("--unseen-seed-count", type=int, default=0)


def _advisor(args: argparse.Namespace) -> RegionResourceAdvisor:
    config = RegionResourceAdvisorConfig(
        mode=args.mode,
        inference_timeout_s=float(args.timeout_ms) / 1000.0,
        minimum_confidence=args.minimum_confidence,
        ood_margin=args.ood_margin,
        minimum_unseen_seeds=args.minimum_unseen_seeds,
    )
    if args.bundle_dir is None:
        return RegionResourceAdvisor(config=config)
    return RegionResourceAdvisor.from_bundle(
        args.bundle_dir,
        config=config,
        expected_model_version=args.expected_model_version,
        expected_state_dict_sha256=args.expected_state_dict_sha256,
    )


def _demo_snapshot(
    *,
    region_count: int,
    seed: int,
    owner_layer: RegionalAuthorityLayer,
) -> RegionResourceSnapshot:
    region_ids = tuple(f"region-{index:03d}" for index in range(region_count))
    nodes: list[RegionResourceNode] = []
    for index, region_id in enumerate(region_ids):
        available = 8 if index == region_count - 1 else 3
        owner_id = {
            RegionalAuthorityLayer.CENTER: "CENTER",
            RegionalAuthorityLayer.SECONDARY: f"RECON-{index % max(1, region_count // 2):03d}",
            RegionalAuthorityLayer.DISTRIBUTED: f"PEER-{index:03d}",
        }[owner_layer]
        nodes.append(
            RegionResourceNode(
                region_id=region_id,
                target_demand=7.0 if index == 0 else 1.0,
                high_threat_backlog=2.0 if index == 0 else 0.0,
                d1_uncertainty=0.2 + 0.01 * index,
                d2_uncertainty=0.1,
                d5_visibility=0.8,
                d5_consistency=0.9,
                available_resources=available,
                reserve_resources=1,
                secondary_coverage=0.9,
                secondary_readiness=0.9,
                communication_capacity=100.0,
                communication_latency_s=0.02,
                packet_loss_rate=0.01,
                current_owner_id=owner_id,
                current_owner_layer=owner_layer,
                plan_id="demo-plan",
                plan_version=2,
                epoch=2,
                lease_expires_at_s=60.0,
            )
        )
    edges = tuple(
        RegionResourceEdge(
            source_region_id=region_ids[index],
            target_region_id=region_ids[(index + 1) % region_count],
            transferable_resources=3,
            distance_m=1000.0,
            transfer_time_s=20.0,
            bandwidth_mbps=20.0,
            bidirectional=True,
            edge_id=f"edge-{index:03d}",
        )
        for index in range(region_count)
        if region_count > 1
    )
    return RegionResourceSnapshot(
        snapshot_id=f"demo-{region_count}-{seed}",
        scenario_id=f"demo-{region_count}-regions",
        scenario_version="v1",
        seed=seed,
        timestamp_s=1.0,
        regions=tuple(nodes),
        edges=edges,
    )


def _load_shadow_records(path: Path) -> tuple[ShadowEpisodeMetrics, ...]:
    payload = _load_json(path)
    if isinstance(payload, dict):
        payload = payload.get("records", ())
    if not isinstance(payload, list):
        raise ValueError("shadow metrics input must be a list or records object")
    return tuple(ShadowEpisodeMetrics.from_dict(item) for item in payload)


def _load_training_groups(path: Path | None) -> tuple[tuple[str, int], ...]:
    if path is None:
        return ()
    payload = _load_json(path)
    if isinstance(payload, dict):
        payload = payload.get("training_groups", ())
    if not isinstance(payload, list):
        raise ValueError("training groups must be a list")
    groups: list[tuple[str, int]] = []
    for item in payload:
        if isinstance(item, dict):
            groups.append((str(item["scenario_id"]), int(item["seed"])))
        else:
            groups.append((str(item[0]), int(item[1])))
    return tuple(groups)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _emit(payload: Any, output: Path | None) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(serialized, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
