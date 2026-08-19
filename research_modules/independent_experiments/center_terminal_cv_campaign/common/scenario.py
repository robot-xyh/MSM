"""Deterministic target geometry and controlled center-cue corruption."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np

from .contracts import Matrix6, SourceCueRecord, SourceCueTruthLabel


@dataclass(frozen=True)
class CampaignScenario:
    target_count: int = 20
    seed: int = 20260816
    target_speed_mps: float = 50.0
    duration_s: float = 18.0
    dt_s: float = 0.1
    clock_speed: float = 0.1
    target_longest_dimension_m: float = 3.0
    source_precision: float = 0.8
    source_recall: float = 0.8
    source_latency_s: float = 0.1
    source_validity_s: float = 20.0
    source_position_sigma_m: float = 1.0
    source_velocity_sigma_mps: float = 0.2

    def __post_init__(self) -> None:
        if self.target_count <= 0:
            raise ValueError("target_count must be positive")
        if self.target_count % 5:
            raise ValueError("target_count must be divisible by five for exact 80/80 fixtures")
        if self.target_speed_mps <= 0.0 or self.duration_s <= 0.0 or self.dt_s <= 0.0:
            raise ValueError("scenario timing and speed must be positive")
        if not math.isclose(self.source_precision, 0.8) or not math.isclose(self.source_recall, 0.8):
            raise ValueError("this campaign freezes source precision and recall at 0.8")


@dataclass(frozen=True)
class TargetTruth:
    truth_target_id: str
    actor_name: str
    start_ned_m: tuple[float, float, float]
    velocity_ned_mps: tuple[float, float, float]
    longest_dimension_m: float

    def position_at(self, timestamp: float) -> tuple[float, float, float]:
        return tuple(
            float(self.start_ned_m[index] + self.velocity_ned_mps[index] * timestamp)
            for index in range(3)
        )


def generate_targets(config: CampaignScenario) -> tuple[TargetTruth, ...]:
    """Generate non-grid targets with three height layers and crossing headings."""

    rng = np.random.default_rng(config.seed)
    base_y = np.linspace(-570.0, 570.0, config.target_count)
    rng.shuffle(base_y)
    x_offsets = rng.uniform(-260.0, 260.0, size=config.target_count)
    headings_deg = rng.uniform(-30.0, 30.0, size=config.target_count)
    layers = np.asarray((-90.0, -140.0, -200.0), dtype=float)
    targets: list[TargetTruth] = []
    for index in range(config.target_count):
        heading = math.radians(float(headings_deg[index]))
        velocity = (
            -config.target_speed_mps * math.cos(heading),
            config.target_speed_mps * math.sin(heading),
            0.0,
        )
        targets.append(
            TargetTruth(
                truth_target_id=f"TGT-{index + 1:03d}",
                actor_name=f"MSM_TargetActor_{index + 1}",
                start_ned_m=(
                    3000.0 + float(x_offsets[index]),
                    float(base_y[index] + rng.uniform(-12.0, 12.0)),
                    float(layers[index % len(layers)]),
                ),
                velocity_ned_mps=tuple(float(value) for value in velocity),
                longest_dimension_m=config.target_longest_dimension_m,
            )
        )
    return tuple(targets)


def _diagonal_covariance(position_sigma: float, velocity_sigma: float) -> Matrix6:
    diagonal = (
        position_sigma**2,
        position_sigma**2,
        position_sigma**2,
        velocity_sigma**2,
        velocity_sigma**2,
        velocity_sigma**2,
    )
    return tuple(
        tuple(float(diagonal[row]) if row == column else 0.0 for column in range(6))
        for row in range(6)
    )  # type: ignore[return-value]


def build_source_fixture(
    config: CampaignScenario,
    targets: Sequence[TargetTruth],
    *,
    timestamp: float = 0.0,
) -> tuple[tuple[SourceCueRecord, ...], tuple[SourceCueTruthLabel, ...]]:
    """Build exact 80% precision and 80% recall source cues.

    Truth is used only by this fixture builder and the returned offline labels.
    Online algorithms receive only ``SourceCueRecord`` objects.
    """

    if len(targets) != config.target_count:
        raise ValueError("target count does not match scenario")
    rng = np.random.default_rng(config.seed + 7919)
    correct_count = int(round(config.target_count * config.source_recall))
    false_count = int(round(correct_count * (1.0 - config.source_precision) / config.source_precision))
    selected_indices = sorted(int(value) for value in rng.choice(config.target_count, correct_count, replace=False))
    covariance = _diagonal_covariance(
        config.source_position_sigma_m,
        config.source_velocity_sigma_mps,
    )
    records: list[SourceCueRecord] = []
    labels: list[SourceCueTruthLabel] = []

    for sequence, index in enumerate(selected_indices, start=1):
        target = targets[index]
        source_track_id = f"SRC-{sequence:03d}"
        records.append(
            SourceCueRecord(
                source_track_id=source_track_id,
                position_ned_m=target.position_at(timestamp),
                velocity_ned_mps=target.velocity_ned_mps,
                covariance_6x6=covariance,
                measurement_timestamp=timestamp,
                arrival_timestamp=timestamp + config.source_latency_s,
                valid_until=timestamp + config.source_validity_s,
                existence_probability=0.9,
            )
        )
        labels.append(
            SourceCueTruthLabel(
                source_track_id=source_track_id,
                truth_target_id=target.truth_target_id,
                is_correct_source=True,
                corruption_type="none",
            )
        )

    duplicate_count = false_count // 2
    for false_index in range(false_count):
        source_track_id = f"SRC-{correct_count + false_index + 1:03d}"
        if false_index < duplicate_count:
            target = targets[selected_indices[false_index % len(selected_indices)]]
            position = tuple(
                float(value + offset)
                for value, offset in zip(
                    target.position_at(timestamp),
                    (18.0, -15.0 if false_index % 2 else 15.0, 4.0),
                    strict=True,
                )
            )
            velocity = target.velocity_ned_mps
            truth_target_id: str | None = target.truth_target_id
            corruption_type = "duplicate_source"
        else:
            position = (
                float(rng.uniform(2500.0, 3400.0)),
                float(rng.uniform(-650.0, 650.0)),
                float(rng.choice((-90.0, -140.0, -200.0))),
            )
            heading = math.radians(float(rng.uniform(-30.0, 30.0)))
            velocity = (
                -config.target_speed_mps * math.cos(heading),
                config.target_speed_mps * math.sin(heading),
                0.0,
            )
            truth_target_id = None
            corruption_type = "ghost_source"
        records.append(
            SourceCueRecord(
                source_track_id=source_track_id,
                position_ned_m=position,
                velocity_ned_mps=tuple(float(value) for value in velocity),
                covariance_6x6=covariance,
                measurement_timestamp=timestamp,
                arrival_timestamp=timestamp + config.source_latency_s,
                valid_until=timestamp + config.source_validity_s,
                existence_probability=0.65,
            )
        )
        labels.append(
            SourceCueTruthLabel(
                source_track_id=source_track_id,
                truth_target_id=truth_target_id,
                is_correct_source=False,
                corruption_type=corruption_type,
            )
        )

    return tuple(records), tuple(labels)
