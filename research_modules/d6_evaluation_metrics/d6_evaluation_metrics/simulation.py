"""Synthetic offline episode generation for D6 examples and tests."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

import numpy as np

from .metrics import (
    AssignmentRecord,
    EventRecord,
    MetricsCollector,
    TerminalRecord,
    TrackRecord,
)


def generate_synthetic_episode(
    seed: int,
    duration: float = 60.0,
    step: float = 1.0,
) -> tuple[MetricsCollector, dict[str, Any]]:
    """Generate a deterministic synthetic offline episode.

    The generated data is for evaluation plumbing only. It is not a physical
    engagement model and does not contain fire-control or damage parameters.
    """

    rng = np.random.default_rng(seed)
    collector = MetricsCollector()
    timestamps = [float(value) for value in np.arange(0.0, duration + 1e-9, step)]
    truth_count = int(rng.integers(4, 8))
    truth_ids = [f"T{index:02d}" for index in range(truth_count)]
    high_count = max(1, truth_count // 3)
    high_threat_ids = set(rng.choice(truth_ids, size=high_count, replace=False).tolist())

    bases = rng.uniform(-80.0, 80.0, size=(truth_count, 3))
    velocities = rng.uniform(-1.4, 1.4, size=(truth_count, 3))
    velocities[:, 2] = rng.uniform(-0.2, 0.2, size=truth_count)

    detection_probability = float(np.clip(rng.normal(0.86, 0.05), 0.65, 0.98))
    false_alarm_intensity = float(rng.uniform(0.015, 0.075))
    measurement_noise = float(rng.uniform(0.5, 2.2))
    id_switch_probability = float(rng.uniform(0.006, 0.028))

    current_track_ids = {truth_id: f"G_{truth_id}_0" for truth_id in truth_ids}
    track_versions = {truth_id: 0 for truth_id in truth_ids}

    for timestamp in timestamps:
        for truth_index, truth_id in enumerate(truth_ids):
            truth_position = bases[truth_index] + velocities[truth_index] * timestamp
            if rng.random() <= detection_probability:
                if rng.random() <= id_switch_probability:
                    track_versions[truth_id] += 1
                    current_track_ids[truth_id] = f"G_{truth_id}_{track_versions[truth_id]}"
                measured_position = truth_position + rng.normal(0.0, measurement_noise, size=3)
                collector.add_track(
                    TrackRecord(
                        timestamp=timestamp,
                        global_track_id=current_track_ids[truth_id],
                        truth_id=truth_id,
                        position=tuple(float(value) for value in measured_position),
                        truth_position=tuple(float(value) for value in truth_position),
                        covariance_trace=measurement_noise * measurement_noise * 3.0,
                        track_state="active",
                        association_source="synthetic",
                    )
                )

        false_alarm_count = int(rng.poisson(false_alarm_intensity * step))
        for index in range(false_alarm_count):
            false_position = rng.uniform(-120.0, 120.0, size=3)
            collector.add_track(
                TrackRecord(
                    timestamp=timestamp,
                    global_track_id=f"FA_{int(timestamp):03d}_{index:02d}",
                    truth_id=None,
                    position=tuple(float(value) for value in false_position),
                    truth_position=None,
                    track_state="tentative",
                    association_source="synthetic_false_alarm",
                )
            )

    _add_synthetic_assignments(
        collector=collector,
        rng=rng,
        timestamps=timestamps,
        truth_ids=truth_ids,
        high_threat_ids=high_threat_ids,
    )
    _add_synthetic_degradation_events(collector, rng, duration)
    _add_synthetic_terminal_records(collector, rng, duration, truth_ids, high_threat_ids)
    _add_synthetic_safety_events(collector, rng, duration)

    truth_summary = {
        "truth_timestamps": {truth_id: timestamps for truth_id in truth_ids},
        "high_threat_ids": sorted(high_threat_ids),
        "high_threat_by_timestamp": {
            timestamp: sorted(high_threat_ids)
            for timestamp in timestamps
            if abs(timestamp % 5.0) < 1e-9
        },
        "scenario": {
            "duration": duration,
            "step": step,
            "truth_count": truth_count,
            "detection_probability": detection_probability,
            "false_alarm_intensity": false_alarm_intensity,
            "measurement_noise": measurement_noise,
            "id_switch_probability": id_switch_probability,
        },
    }
    return collector, truth_summary


def compute_synthetic_episode(seed: int, duration: float = 60.0):
    collector, truth_summary = generate_synthetic_episode(seed=seed, duration=duration)
    return collector.compute_episode(
        episode_id=f"synthetic_{seed:04d}",
        seed=seed,
        duration=duration,
        truth_summary=truth_summary,
    )


def write_episode_log_jsonl(
    collector: MetricsCollector,
    truth_summary: dict[str, Any],
    path: str | Path,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {"record_type": "truth_summary", "payload": truth_summary},
                sort_keys=True,
            )
            + "\n"
        )
        for record in collector.track_records:
            stream.write(_json_record("track", asdict(record)) + "\n")
        for record in collector.assignment_records:
            stream.write(_json_record("assignment", asdict(record)) + "\n")
        for record in collector.target_demand_records:
            stream.write(_json_record("target_demand", asdict(record)) + "\n")
        for record in collector.coalition_records:
            stream.write(_json_record("coalition", asdict(record)) + "\n")
        for record in collector.arrival_records:
            stream.write(_json_record("arrival", asdict(record)) + "\n")
        for record in collector.event_records:
            stream.write(_json_record("event", asdict(record)) + "\n")
        for record in collector.link_records:
            stream.write(_json_record("link", asdict(record)) + "\n")
        for record in collector.terminal_records:
            stream.write(_json_record("terminal", asdict(record)) + "\n")
    return path


def _add_synthetic_assignments(
    collector: MetricsCollector,
    rng: np.random.Generator,
    timestamps: list[float],
    truth_ids: list[str],
    high_threat_ids: set[str],
) -> None:
    assignment_times = [timestamp for timestamp in timestamps if abs(timestamp % 5.0) < 1e-9]
    resources = [f"R{index:02d}" for index in range(4)]
    for timestamp in assignment_times:
        ordered_targets = list(high_threat_ids) + [
            truth_id for truth_id in truth_ids if truth_id not in high_threat_ids
        ]
        rng.shuffle(ordered_targets)
        assigned_targets: list[str] = []
        for resource_index, resource_id in enumerate(resources):
            if rng.random() < 0.15:
                continue
            if assigned_targets and rng.random() < 0.12:
                target_id = str(rng.choice(assigned_targets))
            else:
                target_id = ordered_targets[resource_index % len(ordered_targets)]
            assigned_targets.append(target_id)
            collector.add_assignment(
                AssignmentRecord(
                    timestamp=timestamp,
                    plan_id=f"plan_{int(timestamp):03d}",
                    version=1,
                    resource_id=resource_id,
                    global_track_id=f"G_{target_id}_assignment",
                    cost_breakdown={"normalized_cost": float(rng.uniform(0.0, 1.0))},
                    authorization_state="offline_recorded",
                    active=True,
                    truth_id=target_id,
                )
            )


def _add_synthetic_degradation_events(
    collector: MetricsCollector,
    rng: np.random.Generator,
    duration: float,
) -> None:
    failure_time = float(rng.uniform(duration * 0.25, duration * 0.55))
    failover_delay = float(rng.uniform(1.0, 8.0))
    collector.add_event(
        EventRecord(
            timestamp=failure_time,
            event_type="central_failure",
            actor_id="offline_coordinator",
            severity="warning",
            note="Synthetic coordinator outage marker.",
        )
    )
    collector.add_event(
        EventRecord(
            timestamp=min(duration, failure_time + failover_delay),
            event_type="degraded_stable",
            actor_id="offline_coordinator",
            severity="info",
            note="Synthetic degraded-mode stable marker.",
        )
    )
    collector.add_event(
        EventRecord(
            timestamp=min(duration, failure_time + failover_delay),
            event_type="consensus_rounds",
            actor_id="offline_swarm",
            value=int(rng.integers(2, 9)),
        )
    )
    for index in range(6):
        event_type = "degraded_task_completed" if rng.random() < 0.82 else "degraded_task_failed"
        collector.add_event(
            EventRecord(
                timestamp=min(duration, failure_time + failover_delay + index + 1),
                event_type=event_type,
                actor_id=f"task_{index:02d}",
            )
        )


def _add_synthetic_terminal_records(
    collector: MetricsCollector,
    rng: np.random.Generator,
    duration: float,
    truth_ids: list[str],
    high_threat_ids: set[str],
) -> None:
    terminal_targets = sorted(high_threat_ids) or truth_ids[:1]
    for index, truth_id in enumerate(terminal_targets):
        resource_id = f"R{index % 4:02d}"
        entry_time = float(rng.uniform(duration * 0.45, duration * 0.75))
        lock_delay = float(rng.uniform(0.5, 4.5))
        local_track_id = f"L_{truth_id}_0"
        ambiguity_score = float(rng.uniform(0.0, 1.0))
        friend_state = "hold" if rng.random() < 0.08 else "none"

        collector.add_terminal(
            TerminalRecord(
                timestamp=entry_time,
                resource_id=resource_id,
                assigned_global_track_id=truth_id,
                local_track_id=local_track_id,
                decision_state="fov_entry",
                ambiguity_score=ambiguity_score,
                friend_conflict_state=friend_state,
                expected_global_track_id=truth_id,
            )
        )
        if ambiguity_score >= collector.ambiguous_fov_threshold:
            collector.add_event(
                EventRecord(
                    timestamp=entry_time,
                    event_type="ambiguous_fov",
                    actor_id=resource_id,
                    metadata={"target_id": truth_id},
                )
            )
        if friend_state == "hold":
            collector.add_event(
                EventRecord(
                    timestamp=entry_time,
                    event_type="friend_overlap_hold",
                    actor_id=resource_id,
                    metadata={"target_id": truth_id},
                )
            )

        correct = bool(rng.random() < 0.88)
        assigned_id = truth_id if correct else str(rng.choice(truth_ids))
        lock_time = min(duration, entry_time + lock_delay)
        collector.add_terminal(
            TerminalRecord(
                timestamp=lock_time,
                resource_id=resource_id,
                assigned_global_track_id=assigned_id,
                local_track_id=local_track_id,
                decision_state="locked",
                ambiguity_score=max(0.0, ambiguity_score - float(rng.uniform(0.1, 0.5))),
                friend_conflict_state="none",
                expected_global_track_id=truth_id,
                association_correct=correct,
            )
        )
        if rng.random() < 0.16:
            collector.add_terminal(
                TerminalRecord(
                    timestamp=min(duration, lock_time + float(rng.uniform(0.2, 2.5))),
                    resource_id=resource_id,
                    assigned_global_track_id=assigned_id,
                    local_track_id=f"L_{truth_id}_1",
                    decision_state="locked",
                    ambiguity_score=0.2,
                    friend_conflict_state="none",
                    expected_global_track_id=truth_id,
                    association_correct=correct,
                )
            )


def _add_synthetic_safety_events(
    collector: MetricsCollector,
    rng: np.random.Generator,
    duration: float,
) -> None:
    for index in range(int(rng.poisson(0.35))):
        collector.add_event(
            EventRecord(
                timestamp=float(rng.uniform(0.0, duration)),
                event_type="constraint_violation",
                actor_id=f"constraint_{index:02d}",
                severity="warning",
            )
        )
    for index in range(int(rng.poisson(0.25))):
        collector.add_event(
            EventRecord(
                timestamp=float(rng.uniform(0.0, duration)),
                event_type="human_override",
                actor_id=f"review_{index:02d}",
                severity="info",
            )
        )


def _json_record(record_type: str, payload: dict[str, Any]) -> str:
    return json.dumps(
        {"record_type": record_type, "payload": payload},
        sort_keys=True,
    )
