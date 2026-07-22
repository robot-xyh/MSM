#!/usr/bin/env python3
"""Reproduce the truth-free D2 stale-posterior regression for seed 1005."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
D2_ROOT = ROOT / "research_modules" / "d2_data_association"
for path in (ROOT, D2_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from research_modules.scalable_3d_simulation.learning_runtime import (  # noqa: E402
    LearningRuntimeOptions,
    resolve_learning_runtime,
)
from research_modules.scalable_3d_simulation.module_stack import (  # noqa: E402
    IntegratedStackConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import (  # noqa: E402
    Scalable3DEpisodeRunner,
)
from research_modules.scalable_3d_simulation.reserved_seed_interventions import (  # noqa: E402
    ReservedSeedInterventionOptions,
    _make_intervention_scenario,
)


def reproduce(duration_s: float = 2.2) -> dict[str, Any]:
    options = ReservedSeedInterventionOptions(
        scenario="nominal",
        scale=5,
        duration_s=float(duration_s),
        intervention_kind="active_risk",
    )
    config = _make_intervention_scenario(options, seed=1005)
    resolved = resolve_learning_runtime(
        config,
        LearningRuntimeOptions(),
        stack_config=IntegratedStackConfig(capture_learning_artifacts=True),
    )
    episode = Scalable3DEpisodeRunner(
        resolved.config,
        module_stack=resolved.stack,
    ).run()
    frames = []
    for message in episode.online_messages:
        if message.topic != "modules.d2.associated_tracks":
            continue
        frames.append(
            {
                "timestamp_s": float(message.timestamp),
                "track_count": int(message.payload["track_count"]),
                "tracks": [
                    {
                        "global_track_id": item["global_track_id"],
                        "track_state": item["track_state"],
                    }
                    for item in message.payload["tracks"]
                ],
            }
        )
    tracker_summary = resolved.stack.d2.summary()
    final_ids = [
        item["global_track_id"] for item in frames[-1]["tracks"]
    ]
    acceptance_passed = bool(
        len(final_ids) == 5
        and "GT3D-000004" in final_ids
        and "GT3D-000006" not in final_ids
        and tracker_summary["replay_quarantine_count"] > 0
        and tracker_summary["tentative_stale_drop_count"] == 1
        and episode.summary["online_truth_use_count"] == 0
    )
    return {
        "schema_version": "d2.active-risk-seed1005-reproduction.v1",
        "seed": 1005,
        "scenario": "active_risk_5v5",
        "duration_s": float(duration_s),
        "online_truth_use_count": int(
            episode.summary["online_truth_use_count"]
        ),
        "id_switch_count": tracker_summary["id_switch_count"],
        "id_switch_count_available": tracker_summary[
            "id_switch_count_available"
        ],
        "replay_quarantine_count": tracker_summary[
            "replay_quarantine_count"
        ],
        "tentative_stale_drop_count": tracker_summary[
            "tentative_stale_drop_count"
        ],
        "duplicate_coalescence_count": tracker_summary[
            "duplicate_coalescence_count"
        ],
        "frames": frames,
        "acceptance_passed": acceptance_passed,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=2.2)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = reproduce(args.duration)
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["acceptance_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
