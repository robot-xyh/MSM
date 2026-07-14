#!/usr/bin/env python3
"""Freeze real AirSim episodes and run the D1/D2/D6 P1 identity pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
for rel in (
    "research_modules",
    "research_modules/d1_sensor_fusion/src",
    "research_modules/d2_data_association",
    "research_modules/d3_assignment_planner/src",
    "research_modules/d4_distributed_fallback",
    "research_modules/d5_terminal_association/src",
    "research_modules/d6_evaluation_metrics",
    "research_modules/d7_proportional_guidance",
):
    path = str(ROOT / rel)
    if path not in sys.path:
        sys.path.insert(0, path)

from airsim_runtime.p1_identity_pipeline import (  # noqa: E402
    IdentityEpisodeEvidence,
    build_identity_calibration_manifest,
    freeze_identity_episode,
    materialize_identity_difficulty_profiles,
)
from d2_data_association import (  # noqa: E402
    load_identity_calibration_manifest,
    run_p1_identity_calibration,
    write_p1_identity_calibration_report,
)
from d6_evaluation_metrics import (  # noqa: E402
    DenseCrossingEvaluationInputs,
    DenseCrossingEvaluationReportGenerator,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--episode",
        action="append",
        default=[],
        help="Nominal approximately 4 m spacing episode in SEED=PATH form.",
    )
    parser.add_argument(
        "--tight-episode",
        action="append",
        default=[],
        help="Tight-crossing approximately 2 m spacing episode in SEED=PATH form.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--scenario-id", default="airsim_dense_crossing_5target")
    parser.add_argument("--scenario-version", default="v1")
    parser.add_argument("--p95-loop-latency-budget-s", type=float, default=0.1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    episodes = tuple(
        _parse_episode(value, args, spacing_m=4.0, difficulty="nominal")
        for value in args.episode
    ) + tuple(
        _parse_episode(value, args, spacing_m=2.0, difficulty="tight_crossing")
        for value in args.tight_episode
    )
    if not episodes:
        raise SystemExit("at least one --episode or --tight-episode is required")
    if len({(item.scenario_difficulty, item.seed) for item in episodes}) != len(episodes):
        raise SystemExit("episode seeds must be unique within each geometry profile")
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    frozen = []
    profiled = []
    for evidence in sorted(episodes, key=lambda item: item.seed):
        paths = freeze_identity_episode(
            evidence,
            output
            / "d1_frozen"
            / evidence.scenario_difficulty
            / f"seed{evidence.seed:03d}",
        )
        frozen.append((evidence, paths))
        profiles = (
            ("tight_crossing", "combined")
            if evidence.declared_target_spacing_m <= 2.5
            else ("nominal", "dropout", "clutter", "delayed_noisy")
        )
        profiled.extend(
            materialize_identity_difficulty_profiles(
                evidence,
                paths,
                output / "d2_profiled_replays",
                profiles=profiles,
            )
        )

    screening_rows = _first_seeds_per_profile(profiled, 10)
    confirmation_rows = _first_seeds_per_profile(profiled, 20)
    screening_manifest = build_identity_calibration_manifest(
        screening_rows,
        output / "d2_screening_manifest.json",
        frozen_p95_loop_latency_budget_s=args.p95_loop_latency_budget_s,
    )
    confirmation_manifest = build_identity_calibration_manifest(
        confirmation_rows,
        output / "d2_confirmation_manifest.json",
        frozen_p95_loop_latency_budget_s=args.p95_loop_latency_budget_s,
    )
    screening_cases, _ = load_identity_calibration_manifest(screening_manifest)
    confirmation_cases, _ = load_identity_calibration_manifest(confirmation_manifest)
    report = run_p1_identity_calibration(
        screening_cases,
        confirmation_cases=confirmation_cases,
        frozen_p95_loop_latency_budget_s=args.p95_loop_latency_budget_s,
    )
    d2_report_path = output / "d2_identity_calibration.json"
    write_p1_identity_calibration_report(d2_report_path, report)

    d1_manifest_path, d1_truth_summary_path = _write_d1_aggregate(output, frozen)
    d6_paths = DenseCrossingEvaluationReportGenerator().write_report_bundle(
        output / "d6_dense_crossing",
        inputs=DenseCrossingEvaluationInputs(
            d1_governed_manifest=d1_manifest_path,
            d1_offline_truth_summary=d1_truth_summary_path,
            d2_screening=d2_report_path,
            d2_confirmation=d2_report_path,
            p95_loop_latency_budget_s=args.p95_loop_latency_budget_s,
        ),
    )
    index = {
        "episode_count": len(episodes),
        "screening_seed_count": len(screening_rows),
        "confirmation_seed_count": len(confirmation_rows),
        "screening_available": len(screening_rows) >= 10,
        "confirmation_available": len(confirmation_rows) >= 20,
        "d2_report": str(d2_report_path),
        "d6_report": str(d6_paths["markdown"]),
    }
    (output / "p1_identity_pipeline_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(index, ensure_ascii=False, indent=2))
    return 0


def _parse_episode(
    value: str,
    args: argparse.Namespace,
    *,
    spacing_m: float,
    difficulty: str,
) -> IdentityEpisodeEvidence:
    try:
        seed_text, path_text = value.split("=", 1)
        seed = int(seed_text)
    except (ValueError, TypeError) as exc:
        raise SystemExit("--episode must use SEED=PATH") from exc
    return IdentityEpisodeEvidence(
        seed=seed,
        episode_dir=Path(path_text),
        scenario_id=args.scenario_id,
        scenario_version=args.scenario_version,
        scenario_difficulty=difficulty,
        declared_target_spacing_m=spacing_m,
    )


def _first_seeds_per_profile(rows, limit: int):
    grouped = {}
    for evidence, paths in rows:
        grouped.setdefault(evidence.scenario_difficulty, []).append((evidence, paths))
    selected = []
    for profile in sorted(grouped):
        selected.extend(sorted(grouped[profile], key=lambda item: item[0].seed)[:limit])
    return selected


def _write_d1_aggregate(output: Path, frozen):
    summaries = [
        json.loads(paths["summary"].read_text(encoding="utf-8"))
        for _, paths in frozen
    ]
    truths = [
        json.loads(paths["offline_truth"].read_text(encoding="utf-8"))
        for _, paths in frozen
    ]
    manifest_path = output / "d1_governed_manifest_aggregate.json"
    truth_path = output / "d1_offline_truth_summary_aggregate.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "main-d1-governed-aggregate-v1",
                "seed_count": len(frozen),
                "online_truth_leak_count": sum(
                    int(item.get("online_truth_leak_count", 0)) for item in summaries
                ),
                "records": [str(paths["governed_bundle"]) for _, paths in frozen],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    truth_path.write_text(
        json.dumps(
            {
                "schema_version": "main-d1-truth-summary-aggregate-v1",
                "evaluator_only": True,
                "seed_count": len(frozen),
                "sample_count": sum(int(item.get("sample_count", 0)) for item in truths),
                "target_count_max": max(
                    (int(item.get("target_count", 0)) for item in truths), default=0
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path, truth_path


if __name__ == "__main__":
    raise SystemExit(main())
