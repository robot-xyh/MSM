#!/usr/bin/env python3
"""Prepare immutable settings and fixtures for one campaign seed."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import math
from pathlib import Path
import sys
from typing import Sequence


PACKAGE_PARENT = Path(__file__).resolve().parents[1]
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from center_terminal_cv_campaign.common.airsim_settings import (  # noqa: E402
    write_campaign_settings,
)
from center_terminal_cv_campaign.common.io import write_json, write_jsonl  # noqa: E402
from center_terminal_cv_campaign.common.scenario import (  # noqa: E402
    CampaignScenario,
    TargetTruth,
    build_source_fixture,
    generate_targets,
)


DEFAULT_OUTPUT_ROOT = Path(
    "research_modules/independent_experiments/center_terminal_cv_campaign/outputs"
)

CROSSVIEW_FRAME_TIMESTAMPS_S = tuple(index * 0.2 for index in range(7))
CROSSVIEW_STANDOFF_M = 1050.0


def _look_at_yaw_pitch_deg(
    origin_ned_m: Sequence[float], target_ned_m: Sequence[float]
) -> tuple[float, float]:
    delta = tuple(float(target_ned_m[index] - origin_ned_m[index]) for index in range(3))
    horizontal = math.hypot(delta[0], delta[1])
    yaw = math.degrees(math.atan2(delta[1], delta[0]))
    # AirSim's positive pitch rotates the forward axis toward NED-up.
    pitch = -math.degrees(math.atan2(delta[2], max(horizontal, 1.0e-9)))
    return float(yaw), float(pitch)


def _crossview_groups(targets: Sequence[TargetTruth]) -> tuple[tuple[TargetTruth, ...], ...]:
    """Form paired-camera sectors with partial visibility between sectors."""

    ordered = sorted(targets, key=lambda item: item.position_at(0.6)[1])
    group_size = 2 if len(ordered) <= 5 else 5
    return tuple(
        tuple(ordered[start : start + group_size])
        for start in range(0, len(ordered), group_size)
    )


def prepare_crossview_airsim_fixture(
    fixture_dir: Path,
    *,
    targets: Sequence[TargetTruth],
    interceptor_count: int,
    resource_count: int | None = None,
) -> dict[str, Path]:
    """Write the main-owned AirSim capture plan for the cross-view episode."""

    groups = _crossview_groups(targets)
    minimum_camera_count = 2 * len(groups)
    active_camera_count = (
        minimum_camera_count if resource_count is None else int(resource_count)
    )
    if active_camera_count < minimum_camera_count:
        raise ValueError(
            f"cross-view episode needs at least {minimum_camera_count} cameras for "
            f"two views per sector, got {active_camera_count}"
        )
    if active_camera_count > interceptor_count:
        raise ValueError(
            f"cross-view episode needs {active_camera_count} cameras, settings provide "
            f"{interceptor_count}"
        )

    camera_counts = [active_camera_count // len(groups)] * len(groups)
    for group_index in range(active_camera_count % len(groups)):
        camera_counts[group_index] += 1

    camera_rows: list[dict[str, object]] = []
    poses: dict[str, dict[str, object]] = {}
    camera_number = 1
    for group_index, (group, group_camera_count) in enumerate(
        zip(groups, camera_counts, strict=True)
    ):
        reference_positions = [target.position_at(0.6) for target in group]
        aim = tuple(
            sum(position[axis] for position in reference_positions) / len(reference_positions)
            for axis in range(3)
        )
        for sector_camera_index in range(group_camera_count):
            centered_index = sector_camera_index - 0.5 * (group_camera_count - 1)
            lateral_offset = 18.0 * centered_index
            height_offset = 8.0 * ((sector_camera_index % 3) - 1)
            longitudinal_offset = 10.0 if sector_camera_index % 2 else -10.0
            camera_id = f"Terminal_CV_{camera_number:02d}"
            position = (
                float(aim[0] - CROSSVIEW_STANDOFF_M + longitudinal_offset),
                float(aim[1] + lateral_offset),
                float(aim[2] + height_offset),
            )
            yaw, pitch = _look_at_yaw_pitch_deg(position, aim)
            poses[camera_id] = {
                "camera_id": camera_id,
                "position_ned_m": list(position),
                "yaw_pitch_roll_deg": [yaw, pitch, 0.0],
                "sector_index": group_index,
                "offline_expected_actor_names": [target.actor_name for target in group],
            }
            camera_rows.append(
                {
                    "camera_id": camera_id,
                    "width_px": 1920,
                    "height_px": 1080,
                    "horizontal_fov_deg": 19.0,
                    "confidence": 0.95,
                }
            )
            camera_number += 1

    crossview_dir = fixture_dir / "crossview"
    calibrations_path = write_json(
        crossview_dir / "calibrations.json",
        {
            "schema_version": "terminal-crossview-calibrations-v1",
            "cameras": camera_rows,
        },
    )
    capture_plan_path = write_json(
        crossview_dir / "capture_plan.json",
        {
            "schema_version": "terminal-crossview-airsim-capture-plan-v1",
            "camera_name": "0",
            "apply_vehicle_pose": True,
            "recognition_rule": "bbox_longest_side_px_gte_10",
            "detection_filter": {
                "radius_cm": 10_000_000.0,
                "mesh_names": ["MSM_TargetActor_*", "MSM_TargetActor*"],
            },
            "frames": [
                {
                    "frame_index": frame_index,
                    "measurement_timestamp": timestamp,
                    "arrival_timestamp": timestamp + 0.02,
                    "cameras": [
                        {
                            key: value
                            for key, value in pose.items()
                            if key not in {"offline_expected_actor_names"}
                        }
                        for pose in poses.values()
                    ],
                }
                for frame_index, timestamp in enumerate(CROSSVIEW_FRAME_TIMESTAMPS_S)
            ],
            "offline_sector_expectations": {
                camera_id: pose["offline_expected_actor_names"]
                for camera_id, pose in poses.items()
            },
        },
    )
    truth_targets_path = write_jsonl(
        crossview_dir / "truth" / "targets.jsonl",
        targets,
    )
    return {
        "fixture_dir": crossview_dir,
        "calibrations": calibrations_path,
        "capture_plan": capture_plan_path,
        "target_truth": truth_targets_path,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-count",
        type=int,
        default=5,
        help="positive multiple of five; required for exact 80/80 source fixtures",
    )
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--interceptor-count", type=int, default=40)
    parser.add_argument("--resource-count", type=int)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--api-port", type=int, default=41451)
    return parser.parse_args(argv)


def prepare_fixture(
    *,
    output_root: Path,
    target_count: int,
    seed: int,
    interceptor_count: int,
    resource_count: int | None = None,
    api_port: int = 41451,
) -> dict[str, Path]:
    config = CampaignScenario(target_count=target_count, seed=seed)
    targets = generate_targets(config)
    source_cues, source_labels = build_source_fixture(config, targets)
    fixture_dir = output_root / f"fixture_n{target_count}_seed{seed}"
    settings_path = write_campaign_settings(
        fixture_dir / "settings.json",
        interceptor_count=interceptor_count,
        api_port=api_port,
        clock_speed=config.clock_speed,
    )
    scenario_path = write_json(fixture_dir / "scenario.json", asdict(config))
    source_path = write_jsonl(fixture_dir / "online" / "source_cues.jsonl", source_cues)
    source_truth_path = write_jsonl(
        fixture_dir / "truth" / "source_cue_labels.jsonl",
        source_labels,
    )
    target_truth_path = write_jsonl(
        fixture_dir / "truth" / "targets.jsonl",
        targets,
    )
    crossview_paths = prepare_crossview_airsim_fixture(
        fixture_dir,
        targets=targets,
        interceptor_count=interceptor_count,
        resource_count=resource_count,
    )
    manifest_path = write_json(
        fixture_dir / "fixture_manifest.json",
        {
            "schema_version": "center-terminal-campaign-fixture-v1",
            "target_count": target_count,
            "resource_count": resource_count,
            "seed": seed,
            "source_precision": 0.8,
            "source_recall": 0.8,
            "recognition_rule": "bbox_longest_side_px_gte_10",
            "online_truth_allowed": False,
            "paths": {
                "settings": "settings.json",
                "scenario": "scenario.json",
                "source_cues": "online/source_cues.jsonl",
                "source_cue_labels": "truth/source_cue_labels.jsonl",
                "target_truth": "truth/targets.jsonl",
                "crossview_calibrations": "crossview/calibrations.json",
                "crossview_capture_plan": "crossview/capture_plan.json",
                "crossview_target_truth": "crossview/truth/targets.jsonl",
            },
        },
    )
    return {
        "fixture_dir": fixture_dir,
        "settings": settings_path,
        "scenario": scenario_path,
        "source_cues": source_path,
        "source_truth": source_truth_path,
        "target_truth": target_truth_path,
        "crossview_fixture_dir": crossview_paths["fixture_dir"],
        "crossview_calibrations": crossview_paths["calibrations"],
        "crossview_capture_plan": crossview_paths["capture_plan"],
        "manifest": manifest_path,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = prepare_fixture(
        output_root=args.output_root,
        target_count=args.target_count,
        seed=args.seed,
        interceptor_count=args.interceptor_count,
        resource_count=args.resource_count,
        api_port=args.api_port,
    )
    for name, path in paths.items():
        print(f"{name}={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
