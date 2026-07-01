"""Synthetic offline simulations for D2 data association research."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable

import numpy as np

from .associators import (
    DataAssociator,
    GNNHungarianAssociator,
    JPDAAssociator,
    MHTAssociator,
)
from .models import Detection
from .tracker import Tracker

ASSOCIATOR_NAMES = ("gnn", "jpda", "mht")
SCENARIO_NAMES = ("crossing", "formation", "occlusion", "missed", "false_alarms")


@dataclass(frozen=True, slots=True)
class TruthTarget:
    truth_id: str
    start: np.ndarray
    velocity: np.ndarray
    acceleration: np.ndarray | None = None

    def position_at(self, time_value: float) -> np.ndarray:
        acceleration = (
            np.zeros(2, dtype=float)
            if self.acceleration is None
            else np.asarray(self.acceleration, dtype=float)
        )
        return (
            np.asarray(self.start, dtype=float)
            + np.asarray(self.velocity, dtype=float) * time_value
            + 0.5 * acceleration * time_value * time_value
        )


@dataclass(frozen=True, slots=True)
class ScenarioFrame:
    timestamp: float
    detections: list[Detection]
    truth_positions: dict[str, np.ndarray]
    truth_ids_present: list[str]


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    name: str
    targets: list[TruthTarget]
    measurement_noise_std: float
    miss_probability: float
    false_alarm_rate: float
    bounds: tuple[float, float, float, float]
    occlusion_fn: Callable[[str, int], bool] | None = None
    feature_noise_std: float = 0.08


@dataclass(frozen=True, slots=True)
class ScenarioRunResult:
    scenario: str
    associator: str
    seed: int
    steps: int
    metrics: dict[str, object]
    elapsed_seconds: float

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario": self.scenario,
            "associator": self.associator,
            "seed": self.seed,
            "steps": self.steps,
            "metrics": self.metrics,
            "elapsed_seconds": self.elapsed_seconds,
        }


def build_scenario_spec(name: str) -> ScenarioSpec:
    if name == "crossing":
        return ScenarioSpec(
            name=name,
            targets=[
                TruthTarget("A", np.array([-16.0, -0.15]), np.array([0.85, 0.02])),
                TruthTarget("B", np.array([16.0, 0.15]), np.array([-0.85, -0.02])),
            ],
            measurement_noise_std=0.55,
            miss_probability=0.02,
            false_alarm_rate=0.15,
            bounds=(-22.0, 22.0, -12.0, 12.0),
        )
    if name == "formation":
        targets = [
            TruthTarget(
                f"F{idx + 1}",
                np.array([-14.0, -1.6 + idx * 0.8]),
                np.array([0.65, 0.02 * ((idx % 2) - 0.5)]),
            )
            for idx in range(5)
        ]
        return ScenarioSpec(
            name=name,
            targets=targets,
            measurement_noise_std=0.45,
            miss_probability=0.04,
            false_alarm_rate=0.25,
            bounds=(-20.0, 22.0, -8.0, 8.0),
        )
    if name == "occlusion":
        return ScenarioSpec(
            name=name,
            targets=[
                TruthTarget("O1", np.array([-13.0, -2.0]), np.array([0.75, 0.08])),
                TruthTarget("O2", np.array([-13.0, 0.0]), np.array([0.75, 0.0])),
                TruthTarget("O3", np.array([-13.0, 2.0]), np.array([0.75, -0.08])),
            ],
            measurement_noise_std=0.50,
            miss_probability=0.05,
            false_alarm_rate=0.20,
            bounds=(-18.0, 20.0, -9.0, 9.0),
            occlusion_fn=lambda truth_id, step: truth_id == "O2" and 14 <= step <= 22,
        )
    if name == "missed":
        return ScenarioSpec(
            name=name,
            targets=[
                TruthTarget("M1", np.array([-14.0, -5.0]), np.array([0.65, 0.23])),
                TruthTarget("M2", np.array([-10.0, 4.0]), np.array([0.50, -0.18])),
                TruthTarget("M3", np.array([12.0, -4.0]), np.array([-0.48, 0.18])),
                TruthTarget("M4", np.array([10.0, 4.5]), np.array([-0.55, -0.16])),
            ],
            measurement_noise_std=0.60,
            miss_probability=0.25,
            false_alarm_rate=0.20,
            bounds=(-20.0, 20.0, -12.0, 12.0),
        )
    if name == "false_alarms":
        return ScenarioSpec(
            name=name,
            targets=[
                TruthTarget("C1", np.array([-14.0, -3.0]), np.array([0.60, 0.10])),
                TruthTarget("C2", np.array([-13.0, 3.0]), np.array([0.58, -0.08])),
                TruthTarget("C3", np.array([13.0, -2.5]), np.array([-0.55, 0.10])),
                TruthTarget("C4", np.array([12.0, 2.8]), np.array([-0.52, -0.08])),
            ],
            measurement_noise_std=0.50,
            miss_probability=0.08,
            false_alarm_rate=2.0,
            bounds=(-22.0, 22.0, -13.0, 13.0),
        )
    raise ValueError(f"unknown scenario: {name}")


def generate_scenario_frames(
    scenario_name: str,
    steps: int,
    seed: int,
    dt: float = 1.0,
) -> list[ScenarioFrame]:
    spec = build_scenario_spec(scenario_name)
    rng = np.random.default_rng(seed)
    frames: list[ScenarioFrame] = []
    covariance = np.eye(2, dtype=float) * spec.measurement_noise_std**2
    xmin, xmax, ymin, ymax = spec.bounds
    feature_by_truth = {
        target.truth_id: _feature_for_truth(target.truth_id) for target in spec.targets
    }

    for step in range(steps):
        timestamp = step * dt
        truth_positions = {
            target.truth_id: target.position_at(timestamp) for target in spec.targets
        }
        detections: list[Detection] = []
        for target in spec.targets:
            truth_position = truth_positions[target.truth_id]
            occluded = (
                spec.occlusion_fn(target.truth_id, step)
                if spec.occlusion_fn is not None
                else False
            )
            missed = rng.random() < spec.miss_probability
            if occluded or missed:
                continue
            noisy_position = truth_position + rng.normal(
                0.0, spec.measurement_noise_std, size=2
            )
            noisy_feature = feature_by_truth[target.truth_id] + rng.normal(
                0.0, spec.feature_noise_std, size=4
            )
            detections.append(
                Detection(
                    detection_id=f"{scenario_name}-{step:03d}-{target.truth_id}",
                    timestamp=timestamp,
                    position=noisy_position,
                    covariance=covariance,
                    truth_id=target.truth_id,
                    metadata={"truth_position": truth_position},
                    feature=noisy_feature,
                )
            )

        false_alarm_count = int(rng.poisson(spec.false_alarm_rate))
        for index in range(false_alarm_count):
            false_position = np.array(
                [rng.uniform(xmin, xmax), rng.uniform(ymin, ymax)], dtype=float
            )
            detections.append(
                Detection(
                    detection_id=f"{scenario_name}-{step:03d}-FA{index}",
                    timestamp=timestamp,
                    position=false_position,
                    covariance=covariance,
                    truth_id=None,
                    confidence=0.3,
                    metadata={"false_alarm": True},
                    feature=rng.normal(0.0, 1.0, size=4),
                )
            )

        rng.shuffle(detections)
        frames.append(
            ScenarioFrame(
                timestamp=timestamp,
                detections=detections,
                truth_positions=truth_positions,
                truth_ids_present=[target.truth_id for target in spec.targets],
            )
        )
    return frames


def make_associator(name: str) -> DataAssociator:
    if name == "gnn":
        return GNNHungarianAssociator(gate_threshold=9.21, feature_weight=6.0)
    if name == "jpda":
        return JPDAAssociator(
            gate_threshold=9.21,
            feature_weight=6.0,
            min_marginal_probability=0.30,
            max_joint_hypotheses=4096,
        )
    if name == "mht":
        return MHTAssociator(
            gate_threshold=9.21,
            feature_weight=6.0,
            max_hypotheses=16,
            max_history=5,
            max_generated_assignments=512,
        )
    raise ValueError(f"unknown associator: {name}")


def run_scenario(
    scenario_name: str,
    associator_name: str,
    steps: int = 36,
    seed: int = 7,
) -> ScenarioRunResult:
    frames = generate_scenario_frames(scenario_name, steps=steps, seed=seed)
    tracker = Tracker(associator=make_associator(associator_name))

    start = perf_counter()
    for frame in frames:
        tracker.step(
            frame.detections,
            timestamp=frame.timestamp,
            truth_ids_present=frame.truth_ids_present,
        )
    elapsed = perf_counter() - start

    metrics = tracker.metrics.summary()
    metrics["active_track_count"] = len(tracker.active_tracks())
    metrics["total_track_count"] = len(tracker.tracks)
    metrics["state_transition_count"] = len(tracker.state_transitions)
    return ScenarioRunResult(
        scenario=scenario_name,
        associator=associator_name,
        seed=seed,
        steps=steps,
        metrics=metrics,
        elapsed_seconds=elapsed,
    )


def run_benchmark(
    scenarios: list[str] | None = None,
    associators: list[str] | None = None,
    steps: int = 36,
    seed: int = 7,
) -> list[ScenarioRunResult]:
    scenario_names = scenarios or list(SCENARIO_NAMES)
    associator_names = associators or list(ASSOCIATOR_NAMES)
    results: list[ScenarioRunResult] = []
    for scenario_name in scenario_names:
        for associator_name in associator_names:
            results.append(
                run_scenario(
                    scenario_name=scenario_name,
                    associator_name=associator_name,
                    steps=steps,
                    seed=seed,
                )
            )
    return results


def results_to_rows(results: list[ScenarioRunResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        metrics = result.metrics
        rows.append(
            {
                "scenario": result.scenario,
                "associator": result.associator,
                "IDSW": metrics["id_switch_count"],
                "RMSE": round(float(metrics["rmse"]), 3),
                "continuity": round(float(metrics["track_continuity"]), 3),
                "duplicate": metrics["duplicate_assignment_count"],
                "runtime_ms": round(result.elapsed_seconds * 1000.0, 3),
            }
        )
    return rows


def format_markdown_table(results: list[ScenarioRunResult]) -> str:
    headers = [
        "scenario",
        "associator",
        "IDSW",
        "RMSE",
        "continuity",
        "duplicate",
        "runtime_ms",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in results_to_rows(results):
        lines.append("| " + " | ".join(str(row[header]) for header in headers) + " |")
    return "\n".join(lines)


def _feature_for_truth(truth_id: str) -> np.ndarray:
    seed = sum((index + 1) * ord(char) for index, char in enumerate(truth_id))
    rng = np.random.default_rng(seed)
    feature = rng.normal(0.0, 1.0, size=4)
    norm = np.linalg.norm(feature)
    if norm == 0.0:
        return feature
    return feature / norm
