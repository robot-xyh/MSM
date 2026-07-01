"""Offline metric collection for D6 evaluation.

The collector is intentionally passive: it consumes recorded observations and
events, then emits episode-level metrics for reports and statistical analysis.
It does not produce tasking, control, targeting, or authorization decisions.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Iterable, Mapping, Sequence


Position = Sequence[float]


@dataclass(frozen=True)
class TrackRecord:
    """Offline tracking or detection record aligned to optional truth data."""

    timestamp: float
    global_track_id: str | None
    truth_id: str | None
    position: Position | None = None
    truth_position: Position | None = None
    covariance_trace: float | None = None
    track_state: str = "active"
    association_source: str = "offline"


@dataclass(frozen=True)
class AssignmentRecord:
    """Offline assignment snapshot record.

    ``truth_id`` is optional evaluator-side annotation for measuring outcomes.
    It is not required in operational logs and is never used to make decisions.
    """

    timestamp: float
    plan_id: str
    version: int
    resource_id: str
    global_track_id: str | None
    cost_breakdown: Mapping[str, float] = field(default_factory=dict)
    authorization_state: str = "recorded"
    active: bool = True
    truth_id: str | None = None


@dataclass(frozen=True)
class EventRecord:
    """Generic offline event record."""

    timestamp: float
    event_type: str
    actor_id: str | None = None
    severity: str = "info"
    note: str = ""
    value: float | int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TerminalRecord:
    """Offline terminal registration record.

    ``expected_global_track_id`` and ``association_correct`` are evaluator
    annotations used only when truth labels are available.
    """

    timestamp: float
    resource_id: str
    assigned_global_track_id: str | None
    local_track_id: str | None
    decision_state: str = "observed"
    ambiguity_score: float | None = None
    friend_conflict_state: str = "none"
    assignment_version: int | None = None
    expected_global_track_id: str | None = None
    association_correct: bool | None = None


@dataclass
class EpisodeMetrics:
    """Scalar metrics for one offline episode."""

    episode_id: str
    seed: int | None = None
    duration: float = 0.0
    detection_probability: float = 0.0
    false_alarm_rate: float = 0.0
    missed_detection_rate: float = 0.0
    track_rmse: float = 0.0
    track_continuity: float = 0.0
    id_switch_count: int = 0
    duplicate_assignment_count: int = 0
    unassigned_high_threat_count: int = 0
    failover_time: float = 0.0
    consensus_rounds: float = 0.0
    degraded_completion_rate: float = 0.0
    terminal_association_accuracy: float = 0.0
    terminal_id_switch_count: int = 0
    ambiguous_fov_event_count: int = 0
    friend_overlap_hold_count: int = 0
    time_to_terminal_lock: float = 0.0
    constraint_violation_count: int = 0
    human_override_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def metric_names(cls) -> list[str]:
        return [
            "detection_probability",
            "false_alarm_rate",
            "missed_detection_rate",
            "track_rmse",
            "track_continuity",
            "id_switch_count",
            "duplicate_assignment_count",
            "unassigned_high_threat_count",
            "failover_time",
            "consensus_rounds",
            "degraded_completion_rate",
            "terminal_association_accuracy",
            "terminal_id_switch_count",
            "ambiguous_fov_event_count",
            "friend_overlap_hold_count",
            "time_to_terminal_lock",
            "constraint_violation_count",
            "human_override_count",
        ]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def numeric_metric_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in self.metric_names()}


class MetricsCollector:
    """Collect records and compute one offline episode's metrics."""

    CENTRAL_FAILURE_EVENTS = {"central_failure", "coordinator_failure"}
    DEGRADED_STABLE_EVENTS = {"degraded_stable", "failover_stable"}
    CONSTRAINT_VIOLATION_EVENTS = {
        "constraint_violation",
        "safety_constraint_violation",
    }
    HUMAN_OVERRIDE_EVENTS = {
        "human_override",
        "human_reject",
        "human_rejection",
        "operator_override",
    }
    AMBIGUOUS_FOV_EVENTS = {"ambiguous_fov", "terminal_ambiguous_fov"}
    FRIEND_HOLD_EVENTS = {"friend_overlap_hold", "friend_conflict_hold"}
    FOV_ENTRY_STATES = {"fov_entry", "entered_fov", "terminal_fov_entry"}
    LOCK_STATES = {"locked", "lock", "terminal_lock"}
    ASSOCIATION_STATES = {"associated", "locked", "lock", "terminal_lock"}
    EFFECTIVE_ASSIGNMENT_AUTH_STATES = {
        "recorded",
        "authorized",
        "approved",
        "human_approved",
        "operator_approved",
    }

    def __init__(self, ambiguous_fov_threshold: float = 0.6) -> None:
        self.ambiguous_fov_threshold = ambiguous_fov_threshold
        self.track_records: list[TrackRecord] = []
        self.assignment_records: list[AssignmentRecord] = []
        self.event_records: list[EventRecord] = []
        self.terminal_records: list[TerminalRecord] = []

    def add_track(self, record: TrackRecord) -> None:
        self.track_records.append(record)

    def add_assignment(self, record: AssignmentRecord) -> None:
        self.assignment_records.append(record)

    def add_event(self, record: EventRecord) -> None:
        self.event_records.append(record)

    def add_terminal(self, record: TerminalRecord) -> None:
        self.terminal_records.append(record)

    def extend_tracks(self, records: Iterable[TrackRecord]) -> None:
        self.track_records.extend(records)

    def extend_assignments(self, records: Iterable[AssignmentRecord]) -> None:
        self.assignment_records.extend(records)

    def extend_events(self, records: Iterable[EventRecord]) -> None:
        self.event_records.extend(records)

    def extend_terminals(self, records: Iterable[TerminalRecord]) -> None:
        self.terminal_records.extend(records)

    def compute_episode(
        self,
        episode_id: str,
        seed: int | None = None,
        duration: float | None = None,
        truth_summary: Mapping[str, Any] | None = None,
    ) -> EpisodeMetrics:
        truth_summary = truth_summary or {}
        episode_duration = (
            float(duration)
            if duration is not None
            else self._infer_duration_from_records()
        )
        metrics = EpisodeMetrics(
            episode_id=episode_id,
            seed=seed,
            duration=episode_duration,
        )

        detection = self._compute_detection_metrics(
            duration=episode_duration,
            truth_summary=truth_summary,
        )
        tracking = self._compute_tracking_metrics(truth_summary)
        assignment = self._compute_assignment_metrics(truth_summary)
        degradation = self._compute_degradation_metrics()
        terminal = self._compute_terminal_metrics()
        safety = self._compute_safety_metrics()

        for metric_group in (
            detection,
            tracking,
            assignment,
            degradation,
            terminal,
            safety,
        ):
            for key, value in metric_group.items():
                setattr(metrics, key, value)

        metrics.metadata = {
            "track_record_count": len(self.track_records),
            "assignment_record_count": len(self.assignment_records),
            "event_record_count": len(self.event_records),
            "terminal_record_count": len(self.terminal_records),
            "offline_only": True,
        }
        return metrics

    def to_record_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "tracks": [asdict(record) for record in self.track_records],
            "assignments": [asdict(record) for record in self.assignment_records],
            "events": [asdict(record) for record in self.event_records],
            "terminals": [asdict(record) for record in self.terminal_records],
        }

    def _infer_duration_from_records(self) -> float:
        timestamps: list[float] = []
        timestamps.extend(record.timestamp for record in self.track_records)
        timestamps.extend(record.timestamp for record in self.assignment_records)
        timestamps.extend(record.timestamp for record in self.event_records)
        timestamps.extend(record.timestamp for record in self.terminal_records)
        if not timestamps:
            return 0.0
        low = min(timestamps)
        high = max(timestamps)
        if high == low:
            return high if high > 0 else 0.0
        return high - low

    def _compute_detection_metrics(
        self,
        duration: float,
        truth_summary: Mapping[str, Any],
    ) -> dict[str, float]:
        truth_timestamps = _truth_timestamps_by_id(truth_summary)
        total_truth_opportunities = _truth_opportunity_count(truth_summary)
        if total_truth_opportunities is None:
            total_truth_opportunities = sum(len(values) for values in truth_timestamps.values())

        detected_pairs = {
            (record.truth_id, record.timestamp)
            for record in self.track_records
            if record.truth_id is not None
        }
        if truth_timestamps:
            truth_pairs = {
                (truth_id, timestamp)
                for truth_id, timestamps in truth_timestamps.items()
                for timestamp in timestamps
            }
            true_positive_count = len(detected_pairs & truth_pairs)
        else:
            true_positive_count = len(detected_pairs)

        if total_truth_opportunities == 0:
            total_truth_opportunities = true_positive_count

        false_positive_count = sum(
            1 for record in self.track_records if record.truth_id is None
        )
        false_positive_count += sum(
            1
            for record in self.event_records
            if _event_type(record) == "false_alarm"
        )

        missed_count = max(total_truth_opportunities - true_positive_count, 0)
        denominator = true_positive_count + missed_count

        detection_probability = (
            true_positive_count / denominator if denominator else 0.0
        )
        missed_detection_rate = missed_count / denominator if denominator else 0.0
        false_alarm_rate = false_positive_count / duration if duration > 0 else 0.0

        return {
            "detection_probability": detection_probability,
            "false_alarm_rate": false_alarm_rate,
            "missed_detection_rate": missed_detection_rate,
        }

    def _compute_tracking_metrics(
        self,
        truth_summary: Mapping[str, Any],
    ) -> dict[str, float | int]:
        truth_timestamps = _truth_timestamps_by_id(truth_summary)
        squared_errors: list[float] = []
        for record in self.track_records:
            if record.truth_id is None:
                continue
            distance = _euclidean_distance(record.position, record.truth_position)
            if distance is not None:
                squared_errors.append(distance * distance)
        track_rmse = math.sqrt(sum(squared_errors) / len(squared_errors)) if squared_errors else 0.0

        detected_pairs = {
            (record.truth_id, record.timestamp)
            for record in self.track_records
            if record.truth_id is not None
        }
        if truth_timestamps:
            truth_pairs = {
                (truth_id, timestamp)
                for truth_id, timestamps in truth_timestamps.items()
                for timestamp in timestamps
            }
            matched_count = len(detected_pairs & truth_pairs)
            total_truth_count = len(truth_pairs)
            track_continuity = matched_count / total_truth_count if total_truth_count else 0.0
        else:
            track_continuity = 1.0 if detected_pairs else 0.0

        id_switch_count = self._count_track_id_switches()

        return {
            "track_rmse": track_rmse,
            "track_continuity": track_continuity,
            "id_switch_count": id_switch_count,
        }

    def _count_track_id_switches(self) -> int:
        by_truth: dict[str, dict[float, str]] = defaultdict(dict)
        for record in self.track_records:
            if record.truth_id is None or record.global_track_id is None:
                continue
            by_truth[record.truth_id].setdefault(record.timestamp, record.global_track_id)

        switch_count = 0
        for timestamp_to_track in by_truth.values():
            previous_track_id: str | None = None
            for timestamp in sorted(timestamp_to_track):
                track_id = timestamp_to_track[timestamp]
                if previous_track_id is not None and track_id != previous_track_id:
                    switch_count += 1
                previous_track_id = track_id
        return switch_count

    def _compute_assignment_metrics(
        self,
        truth_summary: Mapping[str, Any],
    ) -> dict[str, int]:
        active_records = [
            record
            for record in self.assignment_records
            if record.active and _state(record.authorization_state) in self.EFFECTIVE_ASSIGNMENT_AUTH_STATES
        ]
        snapshots: dict[tuple[float, str, int], list[AssignmentRecord]] = defaultdict(list)
        for record in active_records:
            snapshots[(record.timestamp, record.plan_id, record.version)].append(record)

        duplicate_assignment_count = 0
        for records in snapshots.values():
            target_to_resources: dict[str, set[str]] = defaultdict(set)
            for record in records:
                target_key = _assignment_target_key(record)
                if target_key is not None:
                    target_to_resources[target_key].add(record.resource_id)
            duplicate_assignment_count += sum(
                1 for resources in target_to_resources.values() if len(resources) > 1
            )

        high_threat_by_timestamp = _high_threat_by_timestamp(truth_summary)
        assignment_times = sorted({record.timestamp for record in active_records})

        if not high_threat_by_timestamp:
            high_threat_ids = _high_threat_ids(truth_summary)
            truth_timestamps = _truth_timestamps_by_id(truth_summary)
            evaluation_times = sorted(
                {
                    timestamp
                    for truth_id in high_threat_ids
                    for timestamp in truth_timestamps.get(truth_id, set())
                }
            )
            if not evaluation_times:
                evaluation_times = assignment_times or [0.0]
            high_threat_by_timestamp = {timestamp: set(high_threat_ids) for timestamp in evaluation_times}

        records_by_time: dict[float, list[AssignmentRecord]] = defaultdict(list)
        for record in active_records:
            records_by_time[record.timestamp].append(record)

        unassigned_high_threat_count = 0
        for timestamp, high_threat_ids in high_threat_by_timestamp.items():
            assigned_targets = {
                target
                for record in records_by_time.get(timestamp, [])
                for target in [_assignment_target_key(record)]
                if target is not None
            }
            unassigned_high_threat_count += sum(
                1 for target in high_threat_ids if target not in assigned_targets
            )

        return {
            "duplicate_assignment_count": duplicate_assignment_count,
            "unassigned_high_threat_count": unassigned_high_threat_count,
        }

    def _compute_degradation_metrics(self) -> dict[str, float]:
        sorted_events = sorted(self.event_records, key=lambda record: record.timestamp)
        pending_failures: deque[EventRecord] = deque()
        failover_times: list[float] = []
        consensus_round_values: list[float] = []
        degraded_completed = 0
        degraded_failed = 0

        for record in sorted_events:
            event_type = _event_type(record)
            if event_type in self.CENTRAL_FAILURE_EVENTS:
                pending_failures.append(record)
            elif event_type in self.DEGRADED_STABLE_EVENTS and pending_failures:
                failure = pending_failures.popleft()
                failover_times.append(max(0.0, record.timestamp - failure.timestamp))
            elif event_type == "consensus_rounds":
                value = _event_numeric_value(record, "rounds")
                if value is not None:
                    consensus_round_values.append(value)
            elif event_type == "degraded_task_completed":
                degraded_completed += 1
            elif event_type in {"degraded_task_failed", "degraded_task_cancelled"}:
                degraded_failed += 1

        failover_time = _mean(failover_times)
        consensus_rounds = _mean(consensus_round_values)
        degraded_total = degraded_completed + degraded_failed
        degraded_completion_rate = (
            degraded_completed / degraded_total if degraded_total else 0.0
        )

        return {
            "failover_time": failover_time,
            "consensus_rounds": consensus_rounds,
            "degraded_completion_rate": degraded_completion_rate,
        }

    def _compute_terminal_metrics(self) -> dict[str, float | int]:
        accuracy_attempts = 0
        correct_attempts = 0
        for record in self.terminal_records:
            correctness = _terminal_correctness(record)
            is_attempt = (
                _state(record.decision_state) in self.ASSOCIATION_STATES
                or (
                    record.assigned_global_track_id is not None
                    and record.local_track_id is not None
                    and _state(record.decision_state) not in self.FOV_ENTRY_STATES
                )
            )
            if is_attempt and correctness is not None:
                accuracy_attempts += 1
                correct_attempts += int(correctness)

        terminal_association_accuracy = (
            correct_attempts / accuracy_attempts if accuracy_attempts else 0.0
        )

        terminal_id_switch_count = self._count_terminal_id_switches()
        ambiguous_fov_event_count = len(self._terminal_event_keys("ambiguous"))
        friend_overlap_hold_count = len(self._terminal_event_keys("friend_hold"))

        time_to_terminal_lock = self._compute_time_to_terminal_lock()

        return {
            "terminal_association_accuracy": terminal_association_accuracy,
            "terminal_id_switch_count": terminal_id_switch_count,
            "ambiguous_fov_event_count": ambiguous_fov_event_count,
            "friend_overlap_hold_count": friend_overlap_hold_count,
            "time_to_terminal_lock": time_to_terminal_lock,
        }

    def _count_terminal_id_switches(self) -> int:
        by_assigned_track: dict[str, dict[float, str]] = defaultdict(dict)
        for record in self.terminal_records:
            if record.assigned_global_track_id is None or record.local_track_id is None:
                continue
            if _state(record.decision_state) in self.FOV_ENTRY_STATES:
                continue
            by_assigned_track[record.assigned_global_track_id].setdefault(
                record.timestamp,
                record.local_track_id,
            )

        switch_count = 0
        for timestamp_to_local in by_assigned_track.values():
            previous_local_id: str | None = None
            for timestamp in sorted(timestamp_to_local):
                local_id = timestamp_to_local[timestamp]
                if previous_local_id is not None and local_id != previous_local_id:
                    switch_count += 1
                previous_local_id = local_id
        return switch_count

    def _terminal_event_keys(self, kind: str) -> set[tuple[str, float, str, str | None, str | None]]:
        keys: set[tuple[str, float, str, str | None, str | None]] = set()
        if kind == "ambiguous":
            for record in self.terminal_records:
                if (
                    record.ambiguity_score is not None
                    and record.ambiguity_score >= self.ambiguous_fov_threshold
                ):
                    keys.add(_terminal_event_key_from_record("ambiguous", record))
            for record in self.event_records:
                if _event_type(record) in self.AMBIGUOUS_FOV_EVENTS:
                    keys.add(_terminal_event_key_from_event("ambiguous", record))
        elif kind == "friend_hold":
            for record in self.terminal_records:
                if _state(record.friend_conflict_state) in {
                    "hold",
                    "friend_overlap",
                    "friend_overlap_hold",
                    "blocked",
                    "verified_friend_overlap",
                }:
                    keys.add(_terminal_event_key_from_record("friend_hold", record))
            for record in self.event_records:
                if _event_type(record) in self.FRIEND_HOLD_EVENTS:
                    keys.add(_terminal_event_key_from_event("friend_hold", record))
        else:
            raise ValueError(f"unknown terminal event kind: {kind}")
        return keys

    def _compute_time_to_terminal_lock(self) -> float:
        entries: dict[tuple[str, str], float] = {}
        locks: dict[tuple[str, str], float] = {}

        for record in self.terminal_records:
            key = _terminal_key_from_record(record)
            if key is None:
                continue
            state = _state(record.decision_state)
            if state in self.FOV_ENTRY_STATES:
                entries.setdefault(key, record.timestamp)
            elif state in self.LOCK_STATES:
                locks.setdefault(key, record.timestamp)

        for record in self.event_records:
            event_type = _event_type(record)
            if event_type not in {"terminal_fov_entry", "terminal_lock"}:
                continue
            key = _terminal_key_from_event(record)
            if key is None:
                continue
            if event_type == "terminal_fov_entry":
                entries.setdefault(key, record.timestamp)
            else:
                locks.setdefault(key, record.timestamp)

        lock_deltas = [
            locks[key] - entry_time
            for key, entry_time in entries.items()
            if key in locks and locks[key] >= entry_time
        ]
        return _mean(lock_deltas)

    def _compute_safety_metrics(self) -> dict[str, int]:
        constraint_violation_count = sum(
            1
            for record in self.event_records
            if _event_type(record) in self.CONSTRAINT_VIOLATION_EVENTS
        )
        human_override_count = sum(
            1
            for record in self.event_records
            if _event_type(record) in self.HUMAN_OVERRIDE_EVENTS
        )
        return {
            "constraint_violation_count": constraint_violation_count,
            "human_override_count": human_override_count,
        }


def _state(value: str | None) -> str:
    return (value or "").strip().lower()


def _event_type(record: EventRecord) -> str:
    return _state(record.event_type)


def _mean(values: Sequence[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _euclidean_distance(
    position: Position | None,
    truth_position: Position | None,
) -> float | None:
    if position is None or truth_position is None:
        return None
    if len(position) != len(truth_position):
        raise ValueError("position and truth_position must have the same dimension")
    squared = [(float(a) - float(b)) ** 2 for a, b in zip(position, truth_position)]
    return math.sqrt(sum(squared))


def _truth_timestamps_by_id(truth_summary: Mapping[str, Any]) -> dict[str, set[float]]:
    raw = truth_summary.get("truth_timestamps", {})
    normalized: dict[str, set[float]] = {}
    if isinstance(raw, Mapping):
        for truth_id, timestamps in raw.items():
            normalized[str(truth_id)] = {float(timestamp) for timestamp in timestamps}
    return normalized


def _truth_opportunity_count(truth_summary: Mapping[str, Any]) -> int | None:
    for key in ("total_truth_opportunities", "truth_opportunity_count"):
        if key in truth_summary and truth_summary[key] is not None:
            return int(truth_summary[key])
    return None


def _high_threat_ids(truth_summary: Mapping[str, Any]) -> set[str]:
    raw = (
        truth_summary.get("high_threat_ids")
        or truth_summary.get("high_priority_ids")
        or []
    )
    return {str(value) for value in raw}


def _high_threat_by_timestamp(
    truth_summary: Mapping[str, Any],
) -> dict[float, set[str]]:
    raw = (
        truth_summary.get("high_threat_by_timestamp")
        or truth_summary.get("high_priority_by_timestamp")
        or {}
    )
    if not isinstance(raw, Mapping):
        return {}
    return {
        float(timestamp): {str(value) for value in values}
        for timestamp, values in raw.items()
    }


def _assignment_target_key(record: AssignmentRecord) -> str | None:
    if record.truth_id is not None:
        return str(record.truth_id)
    if record.global_track_id is not None:
        return str(record.global_track_id)
    return None


def _event_numeric_value(record: EventRecord, metadata_key: str) -> float | None:
    if record.value is not None:
        return float(record.value)
    if metadata_key in record.metadata:
        return float(record.metadata[metadata_key])
    return None


def _terminal_correctness(record: TerminalRecord) -> bool | None:
    if record.association_correct is not None:
        return bool(record.association_correct)
    if record.expected_global_track_id is not None:
        return record.assigned_global_track_id == record.expected_global_track_id
    return None


def _terminal_key_from_record(record: TerminalRecord) -> tuple[str, str] | None:
    target_id = record.assigned_global_track_id or record.expected_global_track_id
    if target_id is None:
        target_id = record.local_track_id
    if target_id is None:
        return None
    return (str(record.resource_id), str(target_id))


def _terminal_key_from_event(record: EventRecord) -> tuple[str, str] | None:
    resource_id = record.actor_id or record.metadata.get("resource_id")
    target_id = (
        record.metadata.get("target_id")
        or record.metadata.get("assigned_global_track_id")
        or record.metadata.get("local_track_id")
    )
    if resource_id is None or target_id is None:
        return None
    return (str(resource_id), str(target_id))


def _terminal_event_key_from_record(
    kind: str,
    record: TerminalRecord,
) -> tuple[str, float, str, str | None, str | None]:
    return (
        kind,
        float(record.timestamp),
        str(record.resource_id),
        None if record.assigned_global_track_id is None else str(record.assigned_global_track_id),
        None if record.local_track_id is None else str(record.local_track_id),
    )


def _terminal_event_key_from_event(
    kind: str,
    record: EventRecord,
) -> tuple[str, float, str, str | None, str | None]:
    resource_id = record.actor_id or record.metadata.get("resource_id") or ""
    target_id = record.metadata.get("assigned_global_track_id") or record.metadata.get("target_id")
    local_track_id = record.metadata.get("local_track_id")
    return (
        kind,
        float(record.timestamp),
        str(resource_id),
        None if target_id is None else str(target_id),
        None if local_track_id is None else str(local_track_id),
    )
