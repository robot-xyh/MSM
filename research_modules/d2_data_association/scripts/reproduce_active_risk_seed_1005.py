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
    all_frames_center_owned = True
    for message in episode.online_messages:
        if message.topic != "modules.d2.associated_tracks":
            continue
        governance = message.payload["association"][
            "observation_evidence_governance"
        ]
        all_frames_center_owned = bool(
            all_frames_center_owned
            and governance["global_track_id_owner"] == "D2_center"
        )
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
    expected_ids = [f"GT3D-{index:06d}" for index in range(1, 6)]
    final_ids = [item["global_track_id"] for item in frames[-1]["tracks"]]
    all_frame_ids_are_canonical = bool(
        frames
        and all(
            [item["global_track_id"] for item in frame["tracks"]]
            == expected_ids
            for frame in frames
        )
    )
    replay_quarantine_count = int(
        tracker_summary["replay_quarantine_count"]
    )
    replay_coast_count = int(tracker_summary["replay_coast_count"])
    expected_replay_reason_counts = (
        {}
        if replay_quarantine_count == 0
        else {"repeated_latest_observation_id": replay_quarantine_count}
    )
    replay_audit_consistent = bool(
        replay_quarantine_count >= 0
        and replay_coast_count == replay_quarantine_count
        and tracker_summary["replay_coast_reason_counts"]
        == expected_replay_reason_counts
    )
    acceptance_passed = bool(
        final_ids == expected_ids
        and all_frame_ids_are_canonical
        and all_frames_center_owned
        and all(
            item["track_state"] == "confirmed"
            for item in frames[-1]["tracks"]
        )
        and tracker_summary["birth_count"] == 5
        and tracker_summary["active_track_count"] == 5
        and replay_audit_consistent
        and tracker_summary["tentative_stale_drop_count"] == 0
        and tracker_summary["duplicate_coalescence_count"] == 0
        and episode.summary["online_truth_use_count"] == 0
    )
    return {
        "schema_version": "d2.active-risk-seed1005-reproduction.v3",
        "acceptance_profile": (
            "canonical_five_tracks_with_optional_bounded_replay_v3"
        ),
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
        "replay_quarantine_count": replay_quarantine_count,
        "replay_coast_count": replay_coast_count,
        "replay_coast_reason_counts": dict(
            tracker_summary["replay_coast_reason_counts"]
        ),
        "replay_audit_consistent": replay_audit_consistent,
        "birth_count": tracker_summary["birth_count"],
        "active_track_count": tracker_summary["active_track_count"],
        "tentative_stale_drop_count": tracker_summary[
            "tentative_stale_drop_count"
        ],
        "duplicate_coalescence_count": tracker_summary[
            "duplicate_coalescence_count"
        ],
        "publication_count": len(frames),
        "publication_track_counts": [
            int(frame["track_count"]) for frame in frames
        ],
        "all_frame_ids_are_canonical": all_frame_ids_are_canonical,
        "all_frames_center_owned": all_frames_center_owned,
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
