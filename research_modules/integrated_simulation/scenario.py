"""Scenario generation for the integrated offline simulation."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .models import ResourcePlatform, ScenarioConfig, TruthState


STANDARD_SCENARIOS = {
    "nominal_5v5",
    "center_destroyed",
    "secondary_destroyed",
    "active_terminal_mismatch",
    "friend_overlap_hold",
    "crossing_5v5",
}


def make_standard_scenario(
    name: str,
    seed: int = 7,
    duration_s: float = 8.0,
    output_root: str | Path | None = None,
) -> ScenarioConfig:
    """Return a standard deterministic scenario configuration."""

    if name not in STANDARD_SCENARIOS:
        options = ", ".join(sorted(STANDARD_SCENARIOS))
        raise ValueError(f"unknown scenario {name!r}; expected one of: {options}")

    kwargs: dict[str, object] = {
        "name": name,
        "seed": seed,
        "duration_s": duration_s,
        "output_root": None if output_root is None else Path(output_root),
    }
    if name == "center_destroyed":
        kwargs["c2_failure_time_s"] = 4.0
    elif name == "secondary_destroyed":
        kwargs["c2_failure_time_s"] = 4.0
        kwargs["secondary_failure_time_s"] = 3.5
    elif name == "active_terminal_mismatch":
        kwargs["active_mismatch_start_s"] = 4.0
    elif name == "friend_overlap_hold":
        kwargs["friend_overlap_start_s"] = 4.0
    elif name == "crossing_5v5":
        kwargs["crossing"] = True
        kwargs["duration_s"] = max(duration_s, 10.0)
    return ScenarioConfig(**kwargs)


def generate_truth_states(config: ScenarioConfig, timestamp: float) -> list[TruthState]:
    """Generate target truth states for one timestamp."""

    states: list[TruthState] = []
    for index in range(config.target_count):
        truth_id = f"TGT-{index + 1:03d}"
        coverage_cell = "cell-north" if index < (config.target_count + 1) // 2 else "cell-south"
        high_threat = index in {0, 1}
        threat_score = 0.90 if high_threat else 0.62 - 0.03 * min(index, 3)

        x0 = -130.0 + 65.0 * index
        y0 = -70.0 + 35.0 * index
        z0 = 720.0 + 18.0 * index
        vx = 3.0 + 0.25 * index
        vy = -0.7 + 0.35 * index
        vz = 0.0

        if config.crossing:
            x0 = -150.0 + 75.0 * index
            y0 = 90.0 - 45.0 * index
            vy = -8.0 + 4.0 * index
            vx = 4.0

        turn = 0.0
        if config.crossing and timestamp > 4.0:
            turn = 8.0 * np.sin(0.45 * (timestamp - 4.0) + index)

        position = np.array(
            [
                x0 + vx * timestamp,
                y0 + vy * timestamp + turn,
                z0 + vz * timestamp,
            ],
            dtype=float,
        )
        velocity = np.array([vx, vy, vz], dtype=float)
        states.append(
            TruthState(
                truth_id=truth_id,
                timestamp=timestamp,
                position=position,
                velocity=velocity,
                threat_score=threat_score,
                coverage_cell=coverage_cell,
            )
        )
    return states


def generate_resource_platforms(config: ScenarioConfig) -> list[ResourcePlatform]:
    """Generate abstract resource states for assignment and terminal cameras."""

    resources: list[ResourcePlatform] = []
    for index in range(config.resource_count):
        coverage_cell = "cell-north" if index < (config.resource_count + 1) // 2 else "cell-south"
        position = np.array(
            [
                -140.0 + 70.0 * index,
                -95.0 + 42.0 * index,
                0.0,
            ],
            dtype=float,
        )
        resources.append(
            ResourcePlatform(
                resource_id=f"INT-{index + 1:02d}",
                position=position,
                coverage_cell=coverage_cell,
            )
        )
    return resources


def truth_summary_for(config: ScenarioConfig) -> dict[str, object]:
    """Build the D6 truth summary for the whole episode."""

    timestamps = config.timestamps()
    truth_ids = [f"TGT-{index + 1:03d}" for index in range(config.target_count)]
    high_threat_ids = truth_ids[:2]
    assignment_times = [
        timestamp
        for timestamp in timestamps
        if abs((timestamp / config.assignment_period_s) - round(timestamp / config.assignment_period_s))
        < 1e-9
    ]
    return {
        "truth_timestamps": {truth_id: timestamps for truth_id in truth_ids},
        "total_truth_opportunities": len(timestamps) * len(truth_ids),
        "high_threat_ids": high_threat_ids,
        "high_threat_by_timestamp": {
            timestamp: high_threat_ids for timestamp in assignment_times
        },
        "scenario": {
            "name": config.name,
            "duration_s": config.duration_s,
            "dt_s": config.dt_s,
            "target_count": config.target_count,
            "resource_count": config.resource_count,
            "offline_only": True,
        },
    }

