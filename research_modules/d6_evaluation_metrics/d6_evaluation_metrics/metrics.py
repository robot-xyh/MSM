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
class LinkRecord:
    """Optional cross-node communication record for offline evaluation."""

    timestamp: float
    source_node_id: str
    target_node_id: str | None = None
    relay_node_id: str | None = None
    link_type: str = "data"
    message_type: str = "data"
    sequence_id: int | str | None = None
    sent_timestamp: float | None = None
    received_timestamp: float | None = None
    measurement_timestamp: float | None = None
    arrival_timestamp: float | None = None
    payload_kind: str = "data"
    delivered: bool = True
    stale_after_s: float | None = None
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
    multi_view_consensus_rate: float = 0.0
    cross_view_conflict_count: int = 0
    duplicate_terminal_lock_count: int = 0
    cross_node_latency_ms: float = 0.0
    message_drop_rate: float = 0.0
    out_of_order_count: int = 0
    stale_track_update_count: int = 0
    video_metadata_delivery_rate: float = 0.0
    bbox_delivery_rate: float = 0.0
    consensus_latency_s: float = 0.0
    camera_quality_gate_pass_rate: float = 0.0
    los_quality_gate_pass_rate: float = 0.0
    maneuver_margin_gate_pass_rate: float = 0.0
    terminal_switch_allowed_rate: float = 0.0
    terminal_switch_reject_count: int = 0
    intercept_success_count: int = 0
    collision_intercept_count: int = 0
    range_intercept_count: int = 0
    time_to_intercept_s: float = 0.0
    min_range_m: float = 0.0
    gate_reject_count: int = 0
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
            "multi_view_consensus_rate",
            "cross_view_conflict_count",
            "duplicate_terminal_lock_count",
            "cross_node_latency_ms",
            "message_drop_rate",
            "out_of_order_count",
            "stale_track_update_count",
            "video_metadata_delivery_rate",
            "bbox_delivery_rate",
            "consensus_latency_s",
            "camera_quality_gate_pass_rate",
            "los_quality_gate_pass_rate",
            "maneuver_margin_gate_pass_rate",
            "terminal_switch_allowed_rate",
            "terminal_switch_reject_count",
            "intercept_success_count",
            "collision_intercept_count",
            "range_intercept_count",
            "time_to_intercept_s",
            "min_range_m",
            "gate_reject_count",
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
    MESSAGE_DROP_EVENTS = {
        "message_drop",
        "link_drop",
        "packet_drop",
        "communication_drop",
    }
    OUT_OF_ORDER_EVENTS = {
        "out_of_order_message",
        "message_out_of_order",
        "link_out_of_order",
    }
    STALE_TRACK_EVENTS = {"stale_track_update", "stale_track_summary"}
    MULTI_VIEW_CONSENSUS_EVENTS = {
        "multi_view_consensus",
        "multi_view_consensus_result",
        "cross_view_consensus",
    }
    MULTI_VIEW_CONSENSUS_FAILURE_EVENTS = {
        "multi_view_consensus_failed",
        "cross_view_consensus_failed",
    }
    CROSS_VIEW_CONFLICT_EVENTS = {
        "cross_view_conflict",
        "multi_view_conflict",
        "terminal_cross_view_conflict",
    }
    DUPLICATE_TERMINAL_LOCK_EVENTS = {
        "duplicate_terminal_lock",
        "terminal_duplicate_lock",
    }
    TERMINAL_SWITCH_REJECT_EVENTS = {
        "terminal_switch_reject",
        "terminal_switch_rejected",
        "d7_terminal_switch_reject",
    }
    INTERCEPT_SUCCESS_STATUSES = {"collision_intercept", "range_intercept"}
    INTERCEPT_PAIR_SUMMARY_EVENTS = {
        "d7_intercept_pair_summary",
        "intercept_pair_summary",
    }
    INTERCEPT_SUMMARY_EVENTS = {"d7_intercept_summary", "intercept_summary"}
    D7_CONTROL_COMMAND_EVENTS = {"d7_control_command", "control_command"}
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
        self.link_records: list[LinkRecord] = []
        self.terminal_records: list[TerminalRecord] = []

    def add_track(self, record: TrackRecord) -> None:
        self.track_records.append(record)

    def add_assignment(self, record: AssignmentRecord) -> None:
        self.assignment_records.append(record)

    def add_event(self, record: EventRecord) -> None:
        self.event_records.append(record)

    def add_link(self, record: LinkRecord) -> None:
        self.link_records.append(record)

    def add_terminal(self, record: TerminalRecord) -> None:
        self.terminal_records.append(record)

    def extend_tracks(self, records: Iterable[TrackRecord]) -> None:
        self.track_records.extend(records)

    def extend_assignments(self, records: Iterable[AssignmentRecord]) -> None:
        self.assignment_records.extend(records)

    def extend_events(self, records: Iterable[EventRecord]) -> None:
        self.event_records.extend(records)

    def extend_links(self, records: Iterable[LinkRecord]) -> None:
        self.link_records.extend(records)

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
        link = self._compute_link_metrics()
        guidance_gate = self._compute_guidance_gate_metrics()
        guidance_metadata = guidance_gate.pop("_metadata", {})
        intercept = self._compute_intercept_metrics()
        intercept_metadata = intercept.pop("_metadata", {})
        safety = self._compute_safety_metrics()

        for metric_group in (
            detection,
            tracking,
            assignment,
            degradation,
            terminal,
            link,
            guidance_gate,
            intercept,
            safety,
        ):
            for key, value in metric_group.items():
                setattr(metrics, key, value)

        metrics.metadata = {
            "track_record_count": len(self.track_records),
            "assignment_record_count": len(self.assignment_records),
            "event_record_count": len(self.event_records),
            "link_record_count": len(self.link_records),
            "terminal_record_count": len(self.terminal_records),
            "offline_only": True,
            **guidance_metadata,
            **intercept_metadata,
        }
        return metrics

    def to_record_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "tracks": [asdict(record) for record in self.track_records],
            "assignments": [asdict(record) for record in self.assignment_records],
            "events": [asdict(record) for record in self.event_records],
            "links": [asdict(record) for record in self.link_records],
            "terminals": [asdict(record) for record in self.terminal_records],
        }

    def _infer_duration_from_records(self) -> float:
        timestamps: list[float] = []
        timestamps.extend(record.timestamp for record in self.track_records)
        timestamps.extend(record.timestamp for record in self.assignment_records)
        timestamps.extend(record.timestamp for record in self.event_records)
        timestamps.extend(record.timestamp for record in self.link_records)
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
        multi_view_consensus_rate = self._compute_multi_view_consensus_rate()
        cross_view_conflict_count = self._compute_cross_view_conflict_count()
        duplicate_terminal_lock_count = self._compute_duplicate_terminal_lock_count()

        return {
            "terminal_association_accuracy": terminal_association_accuracy,
            "terminal_id_switch_count": terminal_id_switch_count,
            "ambiguous_fov_event_count": ambiguous_fov_event_count,
            "friend_overlap_hold_count": friend_overlap_hold_count,
            "time_to_terminal_lock": time_to_terminal_lock,
            "multi_view_consensus_rate": multi_view_consensus_rate,
            "cross_view_conflict_count": cross_view_conflict_count,
            "duplicate_terminal_lock_count": duplicate_terminal_lock_count,
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

    def _compute_multi_view_consensus_rate(self) -> float:
        attempts = 0
        successes = 0
        for record in self.event_records:
            event_type = _event_type(record)
            metadata = record.metadata
            has_consensus_field = any(
                key in metadata
                for key in (
                    "multi_view_consensus",
                    "consensus",
                    "consensus_reached",
                    "multi_view_consensus_reached",
                )
            )
            if (
                event_type in self.MULTI_VIEW_CONSENSUS_EVENTS
                or event_type in self.MULTI_VIEW_CONSENSUS_FAILURE_EVENTS
                or has_consensus_field
            ):
                attempts += 1
                if event_type in self.MULTI_VIEW_CONSENSUS_FAILURE_EVENTS:
                    default = False
                else:
                    default = event_type in self.MULTI_VIEW_CONSENSUS_EVENTS
                successes += int(
                    _bool_from_metadata(
                        metadata,
                        (
                            "multi_view_consensus",
                            "consensus_reached",
                            "multi_view_consensus_reached",
                            "consensus",
                        ),
                        default=default,
                    )
                )
        return successes / attempts if attempts else 0.0

    def _compute_cross_view_conflict_count(self) -> int:
        return sum(
            1
            for record in self.event_records
            if _event_type(record) in self.CROSS_VIEW_CONFLICT_EVENTS
            or _bool_from_metadata(
                record.metadata,
                ("cross_view_conflict", "multi_view_conflict"),
                default=False,
            )
        )

    def _compute_duplicate_terminal_lock_count(self) -> int:
        duplicate_events = sum(
            1
            for record in self.event_records
            if _event_type(record) in self.DUPLICATE_TERMINAL_LOCK_EVENTS
            or _bool_from_metadata(record.metadata, ("duplicate_terminal_lock",), default=False)
        )
        locks_by_snapshot: dict[tuple[float, str], set[str]] = defaultdict(set)
        for record in self.terminal_records:
            if _state(record.decision_state) not in self.LOCK_STATES:
                continue
            if record.assigned_global_track_id is None:
                continue
            locks_by_snapshot[
                (float(record.timestamp), str(record.assigned_global_track_id))
            ].add(record.resource_id)
        duplicate_record_count = sum(
            1 for resources in locks_by_snapshot.values() if len(resources) > 1
        )
        return duplicate_events + duplicate_record_count

    def _compute_link_metrics(self) -> dict[str, float | int]:
        link_items = self._communication_items()
        delivered_items = [item for item in link_items if item["delivered"]]
        latencies_s = [
            latency_s
            for item in delivered_items
            for latency_s in [_communication_latency_s(item)]
            if latency_s is not None
        ]

        dropped_count = sum(1 for item in link_items if not item["delivered"])
        total_messages = len(link_items)
        message_drop_rate = dropped_count / total_messages if total_messages else 0.0

        return {
            "cross_node_latency_ms": _mean(latencies_s) * 1000.0,
            "message_drop_rate": message_drop_rate,
            "out_of_order_count": self._compute_out_of_order_count(link_items),
            "stale_track_update_count": self._compute_stale_track_update_count(link_items),
            "video_metadata_delivery_rate": _delivery_rate(
                link_items,
                {
                    "video_metadata",
                    "video",
                    "video_cue",
                    "video_metadata_delivery",
                    "video_metadata_delivered",
                },
            ),
            "bbox_delivery_rate": _delivery_rate(
                link_items,
                {
                    "bbox",
                    "bboxes",
                    "detection_bbox",
                    "detection_box",
                    "bbox_delivery",
                    "bbox_delivered",
                },
            ),
            "consensus_latency_s": self._compute_consensus_latency_s(link_items),
        }

    def _communication_items(self) -> list[dict[str, Any]]:
        items = [_link_record_to_item(record) for record in self.link_records]
        for record in self.event_records:
            item = _event_to_communication_item(record)
            if item is not None:
                items.append(item)
        return items

    def _compute_out_of_order_count(self, link_items: Sequence[Mapping[str, Any]]) -> int:
        explicit_count = sum(
            1
            for record in self.event_records
            if _event_type(record) in self.OUT_OF_ORDER_EVENTS
            or _bool_from_metadata(record.metadata, ("out_of_order",), default=False)
        )
        previous_by_stream: dict[tuple[str, str, str, str], int] = {}
        sequence_count = 0
        ordered_items = sorted(
            link_items,
            key=lambda item: float(
                item.get("received_timestamp")
                or item.get("arrival_timestamp")
                or item.get("timestamp")
                or 0.0
            ),
        )
        for item in ordered_items:
            if not item.get("delivered", True):
                continue
            sequence = _sequence_int(item.get("sequence_id"))
            if sequence is None:
                continue
            stream_key = (
                str(item.get("source_node_id") or ""),
                str(item.get("target_node_id") or ""),
                str(item.get("link_type") or ""),
                str(item.get("message_type") or item.get("payload_kind") or ""),
            )
            previous = previous_by_stream.get(stream_key)
            if previous is not None and sequence < previous:
                sequence_count += 1
            previous_by_stream[stream_key] = max(previous or sequence, sequence)
        return explicit_count + sequence_count

    def _compute_stale_track_update_count(
        self,
        link_items: Sequence[Mapping[str, Any]],
    ) -> int:
        explicit_count = sum(
            1
            for record in self.event_records
            if _event_type(record) in self.STALE_TRACK_EVENTS
            or _bool_from_metadata(record.metadata, ("stale", "stale_track_update"), default=False)
        )
        stale_count = 0
        for item in link_items:
            if not item.get("delivered", True):
                continue
            if _payload_kind(item) not in {"track", "track_summary", "global_track"}:
                continue
            stale_after_s = _optional_float_value(item.get("stale_after_s"))
            if stale_after_s is None:
                continue
            age_s = _track_update_age_s(item)
            if age_s is not None and age_s > stale_after_s:
                stale_count += 1
        return explicit_count + stale_count

    def _compute_consensus_latency_s(
        self,
        link_items: Sequence[Mapping[str, Any]],
    ) -> float:
        latencies: list[float] = []
        for record in self.event_records:
            for key in ("consensus_latency_s", "consensus_latency"):
                value = _metadata_float(record.metadata, key)
                if value is not None:
                    latencies.append(value)
            start_timestamp = _metadata_float(record.metadata, "consensus_start_timestamp")
            if start_timestamp is not None and _event_type(record) in {
                "consensus_stable",
                "consensus_complete",
            }:
                latencies.append(max(0.0, record.timestamp - start_timestamp))

        for item in link_items:
            if not item.get("delivered", True):
                continue
            if _payload_kind(item) not in {"consensus", "bid", "bid_state"}:
                continue
            latency_s = _communication_latency_s(item)
            if latency_s is not None:
                latencies.append(latency_s)
        return _mean(latencies)

    def _compute_guidance_gate_metrics(self) -> dict[str, Any]:
        camera_values: list[bool] = []
        los_values: list[bool] = []
        maneuver_values: list[bool] = []
        terminal_switch_allowed_values: list[bool] = []
        terminal_switch_reject_count = 0
        gate_reject_count = 0
        guidance_law_counts: dict[str, int] = defaultdict(int)
        reject_reasons: dict[str, int] = defaultdict(int)

        for record in self.event_records:
            metadata = record.metadata
            event_type = _event_type(record)
            guidance_law = metadata.get("guidance_law")
            if guidance_law is not None:
                guidance_law_counts[str(guidance_law)] += 1

            if (
                event_type in self.D7_CONTROL_COMMAND_EVENTS
                and "terminal_switch_allowed" in metadata
            ):
                terminal_switch_allowed_values.append(
                    _as_bool(metadata["terminal_switch_allowed"], default=False)
                )

            _append_gate_value(
                camera_values,
                metadata,
                (
                    "camera_quality_gate_pass",
                    "camera_quality_gate_passed",
                    "camera_gate_pass",
                    "camera_gate",
                ),
            )
            _append_gate_value(
                los_values,
                metadata,
                (
                    "los_quality_gate_pass",
                    "los_quality_gate_passed",
                    "los_gate_pass",
                    "los_gate",
                ),
            )
            _append_gate_value(
                maneuver_values,
                metadata,
                (
                    "maneuver_margin_gate_pass",
                    "maneuver_margin_gate_passed",
                    "maneuver_gate_pass",
                    "maneuver_margin_gate",
                    "maneuver_gate",
                ),
            )

            reject_reason = _metadata_text(metadata, "terminal_switch_reject_reason")
            rejected = event_type in self.TERMINAL_SWITCH_REJECT_EVENTS
            rejected = rejected or reject_reason is not None
            rejected = rejected or _bool_from_metadata(
                metadata,
                ("terminal_switch_rejected", "terminal_switch_reject"),
                default=False,
            )
            if not rejected:
                rejected = _gate_reject_from_metadata(metadata)
            if rejected:
                terminal_switch_reject_count += 1
                gate_reject_count += 1
                if reject_reason is not None:
                    reject_reasons[reject_reason] += 1

        return {
            "camera_quality_gate_pass_rate": _bool_rate(camera_values),
            "los_quality_gate_pass_rate": _bool_rate(los_values),
            "maneuver_margin_gate_pass_rate": _bool_rate(maneuver_values),
            "terminal_switch_allowed_rate": _bool_rate(terminal_switch_allowed_values),
            "terminal_switch_reject_count": terminal_switch_reject_count,
            "gate_reject_count": gate_reject_count,
            "_metadata": {
                "guidance_law_counts": dict(guidance_law_counts),
                "terminal_switch_reject_reasons": dict(reject_reasons),
            },
        }

    def _compute_intercept_metrics(self) -> dict[str, Any]:
        summary_success_count: int | None = None
        pair_events: list[EventRecord] = []
        command_events: list[EventRecord] = []

        for record in self.event_records:
            event_type = _event_type(record)
            if event_type in self.INTERCEPT_SUMMARY_EVENTS:
                value = _metadata_int(record.metadata, "success_count")
                if value is not None:
                    summary_success_count = value
            elif event_type in self.INTERCEPT_PAIR_SUMMARY_EVENTS:
                pair_events.append(record)
            elif event_type in self.D7_CONTROL_COMMAND_EVENTS:
                command_events.append(record)

        if pair_events:
            result = self._intercept_metrics_from_pair_events(
                pair_events,
                summary_success_count=summary_success_count,
            )
        else:
            result = self._intercept_metrics_from_command_events(command_events)
            if summary_success_count is not None:
                result["intercept_success_count"] = summary_success_count

        result["_metadata"] = {
            **result.get("_metadata", {}),
            "intercept_summary_success_count": summary_success_count,
            "intercept_pair_event_count": len(pair_events),
            "d7_control_command_event_count": len(command_events),
        }
        return result

    def _intercept_metrics_from_pair_events(
        self,
        records: Sequence[EventRecord],
        *,
        summary_success_count: int | None,
    ) -> dict[str, Any]:
        collision_count = 0
        range_count = 0
        time_to_intercepts: list[float] = []
        min_ranges: list[float] = []
        status_counts: dict[str, int] = defaultdict(int)

        for record in records:
            metadata = record.metadata
            status = _state(str(metadata.get("status") or ""))
            if status:
                status_counts[status] += 1
            if status == "collision_intercept":
                collision_count += 1
            elif status == "range_intercept":
                range_count += 1

            min_range = _metadata_float(metadata, "min_range_m")
            if min_range is not None:
                min_ranges.append(min_range)

            if status in self.INTERCEPT_SUCCESS_STATUSES:
                time_to_intercept = _metadata_float(metadata, "time_to_intercept_s")
                if time_to_intercept is not None:
                    time_to_intercepts.append(time_to_intercept)

        success_count = (
            summary_success_count
            if summary_success_count is not None
            else collision_count + range_count
        )
        return {
            "intercept_success_count": success_count,
            "collision_intercept_count": collision_count,
            "range_intercept_count": range_count,
            "time_to_intercept_s": _mean(time_to_intercepts),
            "min_range_m": min(min_ranges) if min_ranges else 0.0,
            "_metadata": {"intercept_status_counts": dict(status_counts)},
        }

    def _intercept_metrics_from_command_events(
        self,
        records: Sequence[EventRecord],
    ) -> dict[str, Any]:
        by_pair: dict[tuple[str, str], list[EventRecord]] = defaultdict(list)
        for record in records:
            resource_id = str(record.metadata.get("resource_id") or record.actor_id or "")
            target_id = str(record.metadata.get("target_id") or "")
            by_pair[(resource_id, target_id)].append(record)

        collision_count = 0
        range_count = 0
        time_to_intercepts: list[float] = []
        min_ranges: list[float] = []
        status_counts: dict[str, int] = defaultdict(int)

        for pair_records in by_pair.values():
            ordered = sorted(pair_records, key=lambda record: record.timestamp)
            statuses = [
                _state(str(record.metadata.get("status") or ""))
                for record in ordered
                if record.metadata.get("status")
            ]
            final_status = statuses[-1] if statuses else ""
            any_collision_seen = any(
                _bool_from_metadata(
                    record.metadata,
                    ("collision_seen", "target_collision_seen"),
                    default=False,
                )
                for record in ordered
            )
            status = final_status
            if status not in self.INTERCEPT_SUCCESS_STATUSES and any_collision_seen:
                status = "collision_intercept"
            if status:
                status_counts[status] += 1

            if status == "collision_intercept":
                collision_count += 1
            elif status == "range_intercept":
                range_count += 1

            pair_ranges = [
                value
                for record in ordered
                for value in [_metadata_float(record.metadata, "range_m")]
                if value is not None
            ]
            if pair_ranges:
                min_ranges.append(min(pair_ranges))

            if status in self.INTERCEPT_SUCCESS_STATUSES:
                for record in ordered:
                    record_status = _state(str(record.metadata.get("status") or ""))
                    collision_seen = _bool_from_metadata(
                        record.metadata,
                        ("collision_seen", "target_collision_seen"),
                        default=False,
                    )
                    if (
                        record_status in self.INTERCEPT_SUCCESS_STATUSES
                        or collision_seen
                    ):
                        time_to_intercepts.append(float(record.timestamp))
                        break

        return {
            "intercept_success_count": collision_count + range_count,
            "collision_intercept_count": collision_count,
            "range_intercept_count": range_count,
            "time_to_intercept_s": _mean(time_to_intercepts),
            "min_range_m": min(min_ranges) if min_ranges else 0.0,
            "_metadata": {"intercept_status_counts": dict(status_counts)},
        }

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


def _bool_rate(values: Sequence[bool]) -> float:
    return sum(1 for value in values if value) / len(values) if values else 0.0


def _link_record_to_item(record: LinkRecord) -> dict[str, Any]:
    return {
        "timestamp": record.timestamp,
        "source_node_id": record.source_node_id,
        "target_node_id": record.target_node_id,
        "relay_node_id": record.relay_node_id,
        "link_type": record.link_type,
        "message_type": record.message_type,
        "sequence_id": record.sequence_id,
        "sent_timestamp": record.sent_timestamp,
        "received_timestamp": record.received_timestamp,
        "measurement_timestamp": record.measurement_timestamp,
        "arrival_timestamp": record.arrival_timestamp,
        "payload_kind": record.payload_kind,
        "delivered": bool(record.delivered),
        "stale_after_s": record.stale_after_s,
        "metadata": dict(record.metadata),
    }


def _event_to_communication_item(record: EventRecord) -> dict[str, Any] | None:
    metadata = record.metadata
    event_type = _event_type(record)
    communication_keys = {
        "source_node_id",
        "target_node_id",
        "relay_node_id",
        "link_type",
        "message_type",
        "sequence_id",
        "sent_timestamp",
        "received_timestamp",
        "measurement_timestamp",
        "arrival_timestamp",
        "payload_kind",
        "stale_after_s",
        "delivered",
        "cross_node_latency_ms",
        "latency_ms",
        "latency_s",
    }
    communication_events = {
        "link_message",
        "message_delivery",
        "communication_message",
        "communication_link",
        "link_delivery",
        "video_metadata_delivery",
        "video_metadata_delivered",
        "bbox_delivery",
        "bbox_delivered",
        "consensus_message",
        "bid_message",
    }
    drop_events = {
        "message_drop",
        "link_drop",
        "packet_drop",
        "communication_drop",
    }
    if not (
        event_type in communication_events
        or event_type in drop_events
        or any(key in metadata for key in communication_keys)
    ):
        return None

    delivered_default = event_type not in drop_events
    return {
        "timestamp": record.timestamp,
        "source_node_id": metadata.get("source_node_id") or record.actor_id,
        "target_node_id": metadata.get("target_node_id"),
        "relay_node_id": metadata.get("relay_node_id"),
        "link_type": metadata.get("link_type", ""),
        "message_type": metadata.get("message_type", event_type),
        "sequence_id": metadata.get("sequence_id"),
        "sent_timestamp": metadata.get("sent_timestamp"),
        "received_timestamp": metadata.get("received_timestamp"),
        "measurement_timestamp": metadata.get("measurement_timestamp"),
        "arrival_timestamp": metadata.get("arrival_timestamp"),
        "payload_kind": metadata.get("payload_kind") or metadata.get("message_type") or event_type,
        "delivered": _bool_from_metadata(
            metadata,
            ("delivered", "message_delivered"),
            default=delivered_default,
        ),
        "stale_after_s": metadata.get("stale_after_s"),
        "metadata": dict(metadata),
    }


def _communication_latency_s(item: Mapping[str, Any]) -> float | None:
    metadata = item.get("metadata", {})
    if isinstance(metadata, Mapping):
        for key in ("cross_node_latency_ms", "latency_ms"):
            value = _metadata_float(metadata, key)
            if value is not None:
                return max(0.0, value / 1000.0)
        value = _metadata_float(metadata, "latency_s")
        if value is not None:
            return max(0.0, value)

    received_timestamp = _optional_float_value(item.get("received_timestamp"))
    sent_timestamp = _optional_float_value(item.get("sent_timestamp"))
    if received_timestamp is not None and sent_timestamp is not None:
        return max(0.0, received_timestamp - sent_timestamp)

    arrival_timestamp = _optional_float_value(item.get("arrival_timestamp"))
    measurement_timestamp = _optional_float_value(item.get("measurement_timestamp"))
    if arrival_timestamp is not None and measurement_timestamp is not None:
        return max(0.0, arrival_timestamp - measurement_timestamp)
    return None


def _track_update_age_s(item: Mapping[str, Any]) -> float | None:
    measurement_timestamp = _optional_float_value(item.get("measurement_timestamp"))
    if measurement_timestamp is None:
        measurement_timestamp = _optional_float_value(item.get("valid_at"))
    if measurement_timestamp is None:
        return _communication_latency_s(item)

    received_timestamp = _optional_float_value(item.get("received_timestamp"))
    if received_timestamp is None:
        received_timestamp = _optional_float_value(item.get("arrival_timestamp"))
    if received_timestamp is None:
        received_timestamp = _optional_float_value(item.get("timestamp"))
    if received_timestamp is None:
        return _communication_latency_s(item)
    return max(0.0, received_timestamp - measurement_timestamp)


def _delivery_rate(
    link_items: Sequence[Mapping[str, Any]],
    payload_kinds: set[str],
) -> float:
    attempts = [
        item
        for item in link_items
        if _payload_kind(item) in payload_kinds
    ]
    if not attempts:
        return 0.0
    delivered = sum(1 for item in attempts if item.get("delivered", True))
    return delivered / len(attempts)


def _payload_kind(item: Mapping[str, Any]) -> str:
    return _state(str(item.get("payload_kind") or item.get("message_type") or ""))


def _sequence_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _metadata_float(metadata: Mapping[str, Any], key: str) -> float | None:
    if key not in metadata or metadata[key] is None:
        return None
    return float(metadata[key])


def _metadata_int(metadata: Mapping[str, Any], key: str) -> int | None:
    value = _metadata_float(metadata, key)
    return None if value is None else int(value)


def _metadata_text(metadata: Mapping[str, Any], key: str) -> str | None:
    if key not in metadata or metadata[key] is None:
        return None
    text = str(metadata[key]).strip()
    return text or None


def _optional_float_value(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _bool_from_metadata(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
    *,
    default: bool,
) -> bool:
    for key in keys:
        if key in metadata:
            return _as_bool(metadata[key], default=default)
    return default


def _as_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        for key in ("passed", "pass", "ok", "value"):
            if key in value:
                return _as_bool(value[key], default=default)
        return default
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1", "pass", "passed", "ok"}:
        return True
    if text in {"false", "f", "no", "n", "0", "fail", "failed", "reject", "rejected"}:
        return False
    return default


def _append_gate_value(
    values: list[bool],
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> None:
    for key in keys:
        if key in metadata:
            values.append(_as_bool(metadata[key], default=False))
            return


def _gate_reject_from_metadata(metadata: Mapping[str, Any]) -> bool:
    gate_keys = (
        "camera_quality_gate_pass",
        "camera_quality_gate_passed",
        "los_quality_gate_pass",
        "los_quality_gate_passed",
        "maneuver_margin_gate_pass",
        "maneuver_margin_gate_passed",
    )
    present_gate_values = [
        _as_bool(metadata[key], default=False)
        for key in gate_keys
        if key in metadata
    ]
    if not present_gate_values:
        return False

    terminal_switch_allowed = _bool_from_metadata(
        metadata,
        ("terminal_switch_allowed",),
        default=True,
    )
    terminal_handover_pending = _bool_from_metadata(
        metadata,
        ("terminal_handover_pending",),
        default=False,
    )
    return terminal_handover_pending and not terminal_switch_allowed and not all(present_gate_values)


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
