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
    scenario_group: str = "unlabeled"
    batch_seed: int | None = None
    metric_scope: str = "not_recorded"
    drone_count: int = 0
    resource_count: int = 0
    target_count: int = 0
    camera_count: int = 0
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
    active_degradation_count: int = 0
    active_degradation_precision: float = 0.0
    unnecessary_active_degradation_count: int = 0
    passive_failover_count: int = 0
    secondary_node_takeover_count: int = 0
    secondary_reassignment_count: int = 0
    d4_reassign_pending_count: int = 0
    distributed_fallback_count: int = 0
    failover_active_window_delta_s: float = 0.0
    terminal_association_accuracy: float = 0.0
    terminal_id_switch_count: int = 0
    ambiguous_fov_event_count: int = 0
    friend_overlap_hold_count: int = 0
    time_to_terminal_lock: float = 0.0
    terminal_lock_count: int = 0
    multi_view_consensus_rate: float = 0.0
    cross_view_conflict_count: int = 0
    duplicate_terminal_lock_count: int = 0
    secondary_network_joint_full_view_frame_rate: float = 0.0
    secondary_network_mean_coverage_ratio: float = 0.0
    secondary_single_camera_full_view_frame_rate: float = 0.0
    cross_view_association_count: int = 0
    secondary_detect_available_but_not_registered_count: int = 0
    cue_pointing_error_count: int = 0
    cue_pointing_error_mean_deg: float = 0.0
    cue_pointing_error_rmse_deg: float = 0.0
    cue_pointing_error_max_deg: float = 0.0
    gimbal_pointing_error_count: int = 0
    gimbal_pointing_error_mean_deg: float = 0.0
    gimbal_pointing_error_rmse_deg: float = 0.0
    gimbal_pointing_error_max_deg: float = 0.0
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
    visual_png_switch_count: int = 0
    terminal_takeover_rate: float = 0.0
    terminal_switch_reject_count: int = 0
    mode_switch_count: int = 0
    terminal_contract_reject_count: int = 0
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
            "active_degradation_count",
            "active_degradation_precision",
            "unnecessary_active_degradation_count",
            "passive_failover_count",
            "secondary_node_takeover_count",
            "secondary_reassignment_count",
            "d4_reassign_pending_count",
            "distributed_fallback_count",
            "failover_active_window_delta_s",
            "terminal_association_accuracy",
            "terminal_id_switch_count",
            "ambiguous_fov_event_count",
            "friend_overlap_hold_count",
            "time_to_terminal_lock",
            "terminal_lock_count",
            "multi_view_consensus_rate",
            "cross_view_conflict_count",
            "duplicate_terminal_lock_count",
            "secondary_network_joint_full_view_frame_rate",
            "secondary_network_mean_coverage_ratio",
            "secondary_single_camera_full_view_frame_rate",
            "cross_view_association_count",
            "secondary_detect_available_but_not_registered_count",
            "cue_pointing_error_count",
            "cue_pointing_error_mean_deg",
            "cue_pointing_error_rmse_deg",
            "cue_pointing_error_max_deg",
            "gimbal_pointing_error_count",
            "gimbal_pointing_error_mean_deg",
            "gimbal_pointing_error_rmse_deg",
            "gimbal_pointing_error_max_deg",
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
            "visual_png_switch_count",
            "terminal_takeover_rate",
            "terminal_switch_reject_count",
            "mode_switch_count",
            "terminal_contract_reject_count",
            "intercept_success_count",
            "collision_intercept_count",
            "range_intercept_count",
            "time_to_intercept_s",
            "min_range_m",
            "gate_reject_count",
            "constraint_violation_count",
            "human_override_count",
        ]

    @classmethod
    def scale_names(cls) -> list[str]:
        return [
            "drone_count",
            "resource_count",
            "target_count",
            "camera_count",
        ]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def numeric_metric_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in self.metric_names()}


class MetricsCollector:
    """Collect records and compute one offline episode's metrics."""

    CENTRAL_FAILURE_EVENTS = {"central_failure", "coordinator_failure"}
    DEGRADED_STABLE_EVENTS = {"degraded_stable", "failover_stable"}
    ACTIVE_DEGRADATION_EVENTS = {
        "active_degradation",
        "active_degradation_decision",
        "d4_active_degradation",
        "d4_active_degradation_decision",
    }
    PASSIVE_FAILOVER_EVENTS = {
        "passive_failover",
        "passive_failover_complete",
        "passive_failover_stable",
        "d4_passive_failover",
    }
    SECONDARY_NODE_TAKEOVER_EVENTS = {
        "secondary_node_takeover",
        "secondary_takeover",
        "secondary_takeover_complete",
        "d4_secondary_node_takeover",
    }
    SECONDARY_REASSIGNMENT_EVENTS = {
        "secondary_reassignment",
        "secondary_node_reassignment",
        "d4_secondary_reassignment",
        "d4_reassign_to_secondary",
        "degrade_to_secondary",
    }
    D4_REASSIGN_PENDING_EVENTS = {
        "d4_reassign_pending",
        "reassign_pending",
        "assignment_reassign_pending",
        "terminal_reassign_pending",
    }
    DISTRIBUTED_FALLBACK_EVENTS = {
        "distributed_fallback",
        "distributed_fallback_active",
        "distributed_fallback_complete",
        "d4_distributed_fallback",
    }
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
    CROSS_VIEW_ASSOCIATION_EVENTS = {
        "cross_view_association",
        "cross_view_association_result",
        "d5_cross_view_association",
        "d5_cross_view_association_result",
        "secondary_cross_view_association",
    }
    SECONDARY_DETECT_NOT_REGISTERED_EVENTS = {
        "secondary_detect_available_but_not_registered",
        "detect_available_but_not_registered",
        "d5_secondary_detect_available_but_not_registered",
        "secondary_detection_not_registered",
        "d5_registration_miss",
    }
    SECONDARY_SENSING_EVENTS = {
        "secondary_coverage_frame",
        "secondary_sensing_frame",
        "secondary_view_frame",
        "secondary_network_frame",
        "d4_secondary_coverage",
        "d5_secondary_view",
        "d5_secondary_view_frame",
        "fixed_downlook_secondary_frame",
        "mobile_recon_gimbal_frame",
        "cue_pointing_sample",
        "gimbal_pointing_sample",
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
    D7_GUIDANCE_RECORD_EVENTS = {"d7_guidance_record", "guidance_record"}
    D7_GUIDANCE_SUMMARY_EVENTS = {"d7_guidance_summary", "guidance_summary"}
    D7_GUIDANCE_PAIR_SUMMARY_EVENTS = {
        "d7_guidance_pair_summary",
        "guidance_pair_summary",
    }
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
        scenario_group: str | None = None,
        batch_seed: int | None = None,
        metric_scope: str | None = None,
    ) -> EpisodeMetrics:
        truth_summary = truth_summary or {}
        resolved_scenario_group = scenario_group or _scenario_group_from_truth_summary(
            truth_summary
        )
        resolved_metric_scope = metric_scope or _metric_scope_from_truth_summary(
            truth_summary
        )
        resolved_batch_seed = batch_seed
        if resolved_batch_seed is None:
            resolved_batch_seed = _batch_seed_from_truth_summary(truth_summary)
        if resolved_batch_seed is None:
            resolved_batch_seed = seed
        scale_counts = self._episode_scale_counts(truth_summary)
        episode_duration = (
            float(duration)
            if duration is not None
            else self._infer_duration_from_records()
        )
        metrics = EpisodeMetrics(
            episode_id=episode_id,
            seed=seed,
            scenario_group=resolved_scenario_group,
            batch_seed=resolved_batch_seed,
            metric_scope=resolved_metric_scope,
            **scale_counts,
            duration=episode_duration,
        )

        detection = self._compute_detection_metrics(
            duration=episode_duration,
            truth_summary=truth_summary,
        )
        tracking = self._compute_tracking_metrics(truth_summary)
        assignment = self._compute_assignment_metrics(truth_summary)
        degradation = self._compute_degradation_metrics()
        degradation_metadata = degradation.pop("_metadata", {})
        terminal = self._compute_terminal_metrics()
        secondary_sensing = self._compute_secondary_sensing_metrics(scale_counts)
        secondary_sensing_metadata = secondary_sensing.pop("_metadata", {})
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
            secondary_sensing,
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
            "scenario_group": resolved_scenario_group,
            "batch_seed": resolved_batch_seed,
            "metric_scope": resolved_metric_scope,
            **scale_counts,
            **degradation_metadata,
            **secondary_sensing_metadata,
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

    def _episode_scale_counts(self, truth_summary: Mapping[str, Any]) -> dict[str, int]:
        target_count = _target_count_from_truth_summary(truth_summary)
        resource_count = _resource_count_from_truth_summary(truth_summary)
        camera_count = _camera_count_from_truth_summary(truth_summary)
        drone_count = _drone_count_from_truth_summary(truth_summary)

        if target_count is None:
            target_count = self._infer_target_count_from_records()
        if resource_count is None:
            resource_count = self._infer_resource_count_from_records()
        if camera_count is None:
            camera_count = self._infer_camera_count_from_records()
        if drone_count is None:
            drone_count = resource_count

        return {
            "drone_count": int(drone_count or 0),
            "resource_count": int(resource_count or 0),
            "target_count": int(target_count or 0),
            "camera_count": int(camera_count or 0),
        }

    def _infer_target_count_from_records(self) -> int:
        target_ids: set[str] = set()
        for record in self.track_records:
            if record.truth_id is not None:
                target_ids.add(str(record.truth_id))
        for record in self.assignment_records:
            target_key = _assignment_target_key(record)
            if target_key is not None:
                target_ids.add(target_key)
        for record in self.terminal_records:
            if record.assigned_global_track_id is not None:
                target_ids.add(str(record.assigned_global_track_id))
            if record.expected_global_track_id is not None:
                target_ids.add(str(record.expected_global_track_id))
        for record in self.event_records:
            target_id = (
                _metadata_text(record.metadata, "target_id")
                or _metadata_text(record.metadata, "truth_id")
                or _metadata_text(record.metadata, "global_track_id")
                or _metadata_text(record.metadata, "assigned_global_track_id")
            )
            if target_id is not None:
                target_ids.add(target_id)
        return len(target_ids)

    def _infer_resource_count_from_records(self) -> int:
        resource_ids: set[str] = set()
        for record in self.assignment_records:
            resource_ids.add(str(record.resource_id))
        for record in self.terminal_records:
            resource_ids.add(str(record.resource_id))
        for record in self.event_records:
            resource_id = (
                _metadata_text(record.metadata, "resource_id")
                or _metadata_text(record.metadata, "vehicle_name")
                or record.actor_id
            )
            if resource_id is not None:
                resource_ids.add(str(resource_id))
        return len(resource_ids)

    def _infer_camera_count_from_records(self) -> int:
        camera_ids: set[str] = set()
        for record in self.link_records:
            _add_camera_id_from_metadata(camera_ids, record.metadata)
        for record in self.event_records:
            _add_camera_id_from_metadata(camera_ids, record.metadata)
        return len(camera_ids)

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

    def _compute_degradation_metrics(self) -> dict[str, Any]:
        sorted_events = sorted(self.event_records, key=lambda record: record.timestamp)
        pending_failures: deque[EventRecord] = deque()
        failover_times: list[float] = []
        failover_active_window_deltas: list[float] = []
        active_window_timestamps: deque[float] = deque()
        consensus_round_values: list[float] = []
        degraded_completed = 0
        degraded_failed = 0
        active_degradation_count = 0
        passive_failover_count = 0
        secondary_node_takeover_count = 0
        distributed_fallback_count = 0
        secondary_reassignment_count = 0
        d4_reassign_pending_count = 0
        trigger_reasons: dict[str, int] = defaultdict(int)
        active_degradation_necessary_count = 0
        unnecessary_active_degradation_count = 0
        active_degradation_reviewed_count = 0
        active_degradation_review_label_counts: dict[str, int] = defaultdict(int)

        for record in sorted_events:
            event_type = _event_type(record)
            classification = self._degradation_classification(record)
            active, passive, secondary, distributed = classification[:4]
            secondary_reassignment, d4_reassign_pending = classification[4:]
            if active:
                active_degradation_count += 1
                active_window_timestamps.append(record.timestamp)
                review_label = _active_degradation_review_label(record)
                review_class = _active_degradation_review_class(review_label)
                if review_label is not None:
                    active_degradation_review_label_counts[review_label] += 1
                if review_class is not None:
                    active_degradation_reviewed_count += 1
                    if review_class == "necessary":
                        active_degradation_necessary_count += 1
                    else:
                        unnecessary_active_degradation_count += 1
            if passive:
                passive_failover_count += 1
            if secondary:
                secondary_node_takeover_count += 1
            if distributed:
                distributed_fallback_count += 1
            if secondary_reassignment:
                secondary_reassignment_count += 1
            if d4_reassign_pending:
                d4_reassign_pending_count += 1

            trigger_reason = (
                _metadata_text(record.metadata, "trigger_reason")
                or _metadata_text(record.metadata, "reason")
                or _metadata_text(record.metadata, "failover_reason")
                or _metadata_text(record.metadata, "degradation_reason")
            )
            if trigger_reason is not None and (active or passive or secondary or distributed):
                trigger_reasons[trigger_reason] += 1

            explicit_delta = self._failover_active_window_delta_from_metadata(record)
            if explicit_delta is not None:
                failover_active_window_deltas.append(explicit_delta)

            if event_type in self.CENTRAL_FAILURE_EVENTS:
                pending_failures.append(record)
            elif event_type in self.DEGRADED_STABLE_EVENTS and pending_failures:
                failure = pending_failures.popleft()
                failover_times.append(max(0.0, record.timestamp - failure.timestamp))
            if (
                passive
                or secondary
                or distributed
                or event_type in self.DEGRADED_STABLE_EVENTS
            ) and explicit_delta is None:
                while active_window_timestamps and active_window_timestamps[0] > record.timestamp:
                    active_window_timestamps.popleft()
                prior_active = None
                for timestamp in active_window_timestamps:
                    if timestamp <= record.timestamp:
                        prior_active = timestamp
                    else:
                        break
                if prior_active is not None:
                    failover_active_window_deltas.append(record.timestamp - prior_active)
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
        active_degradation_precision = (
            active_degradation_necessary_count / active_degradation_reviewed_count
            if active_degradation_reviewed_count
            else 0.0
        )

        return {
            "failover_time": failover_time,
            "consensus_rounds": consensus_rounds,
            "degraded_completion_rate": degraded_completion_rate,
            "active_degradation_count": active_degradation_count,
            "active_degradation_precision": active_degradation_precision,
            "unnecessary_active_degradation_count": unnecessary_active_degradation_count,
            "passive_failover_count": passive_failover_count,
            "secondary_node_takeover_count": secondary_node_takeover_count,
            "secondary_reassignment_count": secondary_reassignment_count,
            "d4_reassign_pending_count": d4_reassign_pending_count,
            "distributed_fallback_count": distributed_fallback_count,
            "failover_active_window_delta_s": _mean(failover_active_window_deltas),
            "_metadata": {
                "trigger_reason_distribution": dict(trigger_reasons),
                "failover_active_window_deltas_s": failover_active_window_deltas,
                "active_degradation_reviewed_count": active_degradation_reviewed_count,
                "active_degradation_necessary_count": active_degradation_necessary_count,
                "active_degradation_review_label_counts": dict(
                    active_degradation_review_label_counts
                ),
            },
        }

    def _degradation_classification(
        self,
        record: EventRecord,
    ) -> tuple[bool, bool, bool, bool, bool, bool]:
        event_type = _event_type(record)
        metadata = record.metadata
        mode = _state(str(metadata.get("mode") or metadata.get("degradation_mode") or ""))
        action = _state(str(metadata.get("action") or ""))
        assignment_phase = _state(str(metadata.get("assignment_phase") or ""))
        reject_reason = _state(
            str(
                metadata.get("reject_reason")
                or metadata.get("terminal_switch_reject_reason")
                or metadata.get("terminal_contract_reject_reason")
                or ""
            )
        )
        fallback_type = _state(str(metadata.get("fallback_type") or ""))
        d4_state = _state(str(metadata.get("d4_state") or metadata.get("d4_mode") or ""))

        active = (
            event_type in self.ACTIVE_DEGRADATION_EVENTS
            or mode == "active_degradation"
            or d4_state == "active_degradation"
            or _bool_from_metadata(metadata, ("active_degradation",), default=False)
        )
        passive = (
            event_type in self.PASSIVE_FAILOVER_EVENTS
            or mode == "passive_failover"
            or fallback_type == "passive_failover"
            or _bool_from_metadata(metadata, ("passive_failover",), default=False)
        )
        secondary = (
            event_type in self.SECONDARY_NODE_TAKEOVER_EVENTS
            or action in {
                "secondary_node_takeover",
                "takeover_secondary",
                "request_secondary_assist",
                "degrade_to_secondary",
            }
            or fallback_type in {"secondary_node_takeover", "secondary_takeover"}
            or _bool_from_metadata(metadata, ("secondary_node_takeover",), default=False)
        )
        secondary_reassignment = (
            event_type in self.SECONDARY_REASSIGNMENT_EVENTS
            or mode == "secondary_reassignment"
            or action
            in {
                "secondary_reassignment",
                "reassign_to_secondary",
                "degrade_to_secondary",
                "request_secondary_assist",
                "takeover_secondary",
            }
            or assignment_phase == "secondary_reassignment"
            or fallback_type
            in {
                "secondary_reassignment",
                "secondary_node_reassignment",
                "degrade_to_secondary",
            }
            or _bool_from_metadata(
                metadata,
                ("secondary_reassignment", "reassign_to_secondary"),
                default=False,
            )
        )
        d4_reassign_pending = (
            event_type in self.D4_REASSIGN_PENDING_EVENTS
            or action in {"reassign", "request_center_replan"}
            or reject_reason == "d4_reassign_pending"
            or d4_state == "reassign_pending"
            or _bool_from_metadata(metadata, ("d4_reassign_pending",), default=False)
        )
        distributed = (
            event_type in self.DISTRIBUTED_FALLBACK_EVENTS
            or mode == "distributed_fallback"
            or fallback_type == "distributed_fallback"
            or _bool_from_metadata(metadata, ("distributed_fallback",), default=False)
        )
        return active, passive, secondary, distributed, secondary_reassignment, d4_reassign_pending

    def _failover_active_window_delta_from_metadata(
        self,
        record: EventRecord,
    ) -> float | None:
        metadata = record.metadata
        for key in (
            "failover_active_window_delta_s",
            "active_window_delta_s",
            "failover_window_delta_s",
        ):
            value = _metadata_float(metadata, key)
            if value is not None:
                return max(0.0, value)

        active_window_end = _metadata_float(metadata, "active_window_end_s")
        if active_window_end is None:
            active_window_end = _metadata_float(metadata, "active_window_end_timestamp")
        failover_timestamp = (
            _metadata_float(metadata, "failover_timestamp_s")
            or _metadata_float(metadata, "failover_timestamp")
            or _metadata_float(metadata, "takeover_timestamp_s")
            or _metadata_float(metadata, "takeover_timestamp")
        )
        if active_window_end is not None and failover_timestamp is not None:
            return max(0.0, failover_timestamp - active_window_end)
        return None

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
        terminal_lock_count = self._compute_terminal_lock_count()
        multi_view_consensus_rate = self._compute_multi_view_consensus_rate()
        cross_view_conflict_count = self._compute_cross_view_conflict_count()
        duplicate_terminal_lock_count = self._compute_duplicate_terminal_lock_count()

        return {
            "terminal_association_accuracy": terminal_association_accuracy,
            "terminal_id_switch_count": terminal_id_switch_count,
            "ambiguous_fov_event_count": ambiguous_fov_event_count,
            "friend_overlap_hold_count": friend_overlap_hold_count,
            "time_to_terminal_lock": time_to_terminal_lock,
            "terminal_lock_count": terminal_lock_count,
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

    def _compute_terminal_lock_count(self) -> int:
        keys: set[tuple[str, float, str, str | None, str | None]] = set()
        for record in self.terminal_records:
            if _state(record.decision_state) in self.LOCK_STATES:
                keys.add(_terminal_event_key_from_record("terminal_lock", record))
        for record in self.event_records:
            if _event_type(record) == "terminal_lock" or _bool_from_metadata(
                record.metadata,
                ("terminal_locked",),
                default=False,
            ):
                keys.add(_terminal_event_key_from_event("terminal_lock", record))
        return len(keys)


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

    def _compute_secondary_sensing_metrics(
        self,
        scale_counts: Mapping[str, int],
    ) -> dict[str, Any]:
        target_count = int(scale_counts.get("target_count") or 0)
        camera_count = int(scale_counts.get("camera_count") or 0)
        samples = self._secondary_sensing_samples()

        network_frames: dict[tuple[Any, ...], dict[str, Any]] = {}
        node_frames: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = defaultdict(dict)
        single_full_count = 0
        single_frame_count = 0
        node_single_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        cross_view_association_count = 0
        detect_available_not_registered_count = 0
        node_cross_counts: dict[str, int] = defaultdict(int)
        node_not_registered_counts: dict[str, int] = defaultdict(int)
        cue_errors: list[float] = []
        gimbal_errors: list[float] = []
        node_cue_errors: dict[str, list[float]] = defaultdict(list)
        node_gimbal_errors: dict[str, list[float]] = defaultdict(list)

        for sample in samples:
            metadata = sample["metadata"]
            event_type = sample["event_type"]
            fallback_text = sample["fallback_text"]
            node_type = (
                _secondary_node_type(metadata, fallback_text=fallback_text)
                or "secondary_network"
            )
            sample_target_count = _secondary_sample_target_count(
                metadata,
                default_target_count=target_count,
            )
            sample_camera_count = _secondary_sample_camera_count(
                metadata,
                default_camera_count=camera_count,
            )

            coverage = _secondary_coverage_sample(metadata)
            if coverage is not None:
                frame_key = _secondary_frame_key(sample)
                _add_secondary_frame_coverage(
                    network_frames,
                    frame_key,
                    coverage,
                    sample_target_count,
                )
                _add_secondary_frame_coverage(
                    node_frames[node_type],
                    frame_key,
                    coverage,
                    sample_target_count,
                )

            full_count, frame_count = _secondary_single_camera_counts(
                metadata,
                coverage,
                sample_target_count=sample_target_count,
                sample_camera_count=sample_camera_count,
            )
            if frame_count:
                single_full_count += full_count
                single_frame_count += frame_count
                node_single_counts[node_type][0] += full_count
                node_single_counts[node_type][1] += frame_count

            association_count = self._secondary_cross_view_association_increment(
                event_type,
                metadata,
            )
            if association_count:
                cross_view_association_count += association_count
                node_cross_counts[node_type] += association_count

            not_registered_count = self._secondary_not_registered_increment(
                event_type,
                metadata,
            )
            if not_registered_count:
                detect_available_not_registered_count += not_registered_count
                node_not_registered_counts[node_type] += not_registered_count

            cue_sample_errors = _metadata_angle_values_deg(
                metadata,
                degree_keys=(
                    "cue_pointing_error_deg",
                    "cue_error_deg",
                    "cue_angular_error_deg",
                    "cue_pointing_error_angle_deg",
                ),
                radian_keys=(
                    "cue_pointing_error_rad",
                    "cue_error_rad",
                    "cue_angular_error_rad",
                ),
            )
            gimbal_sample_errors = _metadata_angle_values_deg(
                metadata,
                degree_keys=(
                    "gimbal_pointing_error_deg",
                    "gimbal_error_deg",
                    "gimbal_angular_error_deg",
                    "gimbal_pointing_error_angle_deg",
                    "pointing_error_deg",
                ),
                radian_keys=(
                    "gimbal_pointing_error_rad",
                    "gimbal_error_rad",
                    "gimbal_angular_error_rad",
                    "pointing_error_rad",
                ),
            )
            if cue_sample_errors:
                cue_errors.extend(cue_sample_errors)
                node_cue_errors[node_type].extend(cue_sample_errors)
            if gimbal_sample_errors:
                gimbal_errors.extend(gimbal_sample_errors)
                node_gimbal_errors[node_type].extend(gimbal_sample_errors)

        network_stats = _secondary_frame_stats(network_frames)
        cue_stats = _angle_error_stats(cue_errors)
        gimbal_stats = _angle_error_stats(gimbal_errors)

        node_type_metrics: dict[str, dict[str, float | int]] = {}
        node_types = sorted(
            set(node_frames)
            | set(node_single_counts)
            | set(node_cross_counts)
            | set(node_not_registered_counts)
            | set(node_cue_errors)
            | set(node_gimbal_errors)
        )
        for node_type in node_types:
            node_frame_stats = _secondary_frame_stats(node_frames.get(node_type, {}))
            node_single_full, node_single_total = node_single_counts.get(
                node_type,
                [0, 0],
            )
            node_cue_stats = _angle_error_stats(node_cue_errors.get(node_type, []))
            node_gimbal_stats = _angle_error_stats(
                node_gimbal_errors.get(node_type, [])
            )
            node_type_metrics[node_type] = {
                "secondary_network_joint_full_view_frame_rate": (
                    node_frame_stats["full_view_frame_rate"]
                ),
                "secondary_network_mean_coverage_ratio": (
                    node_frame_stats["mean_coverage_ratio"]
                ),
                "secondary_single_camera_full_view_frame_rate": (
                    node_single_full / node_single_total
                    if node_single_total
                    else 0.0
                ),
                "cross_view_association_count": node_cross_counts.get(node_type, 0),
                "secondary_detect_available_but_not_registered_count": (
                    node_not_registered_counts.get(node_type, 0)
                ),
                "cue_pointing_error_count": node_cue_stats["count"],
                "cue_pointing_error_mean_deg": node_cue_stats["mean"],
                "cue_pointing_error_rmse_deg": node_cue_stats["rmse"],
                "cue_pointing_error_max_deg": node_cue_stats["max"],
                "gimbal_pointing_error_count": node_gimbal_stats["count"],
                "gimbal_pointing_error_mean_deg": node_gimbal_stats["mean"],
                "gimbal_pointing_error_rmse_deg": node_gimbal_stats["rmse"],
                "gimbal_pointing_error_max_deg": node_gimbal_stats["max"],
                "frame_count": node_frame_stats["frame_count"],
                "camera_frame_count": node_single_total,
            }

        return {
            "secondary_network_joint_full_view_frame_rate": network_stats[
                "full_view_frame_rate"
            ],
            "secondary_network_mean_coverage_ratio": network_stats[
                "mean_coverage_ratio"
            ],
            "secondary_single_camera_full_view_frame_rate": (
                single_full_count / single_frame_count if single_frame_count else 0.0
            ),
            "cross_view_association_count": cross_view_association_count,
            "secondary_detect_available_but_not_registered_count": (
                detect_available_not_registered_count
            ),
            "cue_pointing_error_count": cue_stats["count"],
            "cue_pointing_error_mean_deg": cue_stats["mean"],
            "cue_pointing_error_rmse_deg": cue_stats["rmse"],
            "cue_pointing_error_max_deg": cue_stats["max"],
            "gimbal_pointing_error_count": gimbal_stats["count"],
            "gimbal_pointing_error_mean_deg": gimbal_stats["mean"],
            "gimbal_pointing_error_rmse_deg": gimbal_stats["rmse"],
            "gimbal_pointing_error_max_deg": gimbal_stats["max"],
            "_metadata": {
                "secondary_sensing_frame_count": network_stats["frame_count"],
                "secondary_sensing_camera_frame_count": single_frame_count,
                "secondary_sensing_target_count": target_count,
                "secondary_sensing_camera_count": camera_count,
                "secondary_sensing_node_type_metrics": node_type_metrics,
                "secondary_sensing_source": "main_d4_d5_event_link_metadata",
            },
        }

    def _secondary_sensing_samples(self) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        for record in self.event_records:
            metadata = dict(record.metadata)
            event_type = _event_type(record)
            fallback_text = " ".join(
                str(value)
                for value in (event_type, record.actor_id, record.note)
                if value is not None
            )
            if self._is_secondary_sensing_sample(
                event_type,
                metadata,
                fallback_text,
            ):
                samples.append(
                    {
                        "timestamp": record.timestamp,
                        "event_type": event_type,
                        "metadata": metadata,
                        "fallback_text": fallback_text,
                    }
                )

        for record in self.link_records:
            metadata = dict(record.metadata)
            fallback_text = " ".join(
                str(value)
                for value in (
                    record.source_node_id,
                    record.target_node_id,
                    record.relay_node_id,
                    record.link_type,
                    record.message_type,
                    record.payload_kind,
                )
                if value is not None
            )
            if self._is_secondary_sensing_sample("", metadata, fallback_text):
                samples.append(
                    {
                        "timestamp": record.timestamp,
                        "event_type": "",
                        "metadata": metadata,
                        "fallback_text": fallback_text,
                    }
                )
        return samples

    def _is_secondary_sensing_sample(
        self,
        event_type: str,
        metadata: Mapping[str, Any],
        fallback_text: str,
    ) -> bool:
        if event_type in (
            self.SECONDARY_SENSING_EVENTS
            | self.CROSS_VIEW_ASSOCIATION_EVENTS
            | self.SECONDARY_DETECT_NOT_REGISTERED_EVENTS
            | self.MULTI_VIEW_CONSENSUS_EVENTS
        ):
            return True
        if _secondary_node_type(metadata, fallback_text=fallback_text) is not None:
            return True
        return any(key in metadata for key in _SECONDARY_SENSING_METADATA_KEYS)

    def _secondary_cross_view_association_increment(
        self,
        event_type: str,
        metadata: Mapping[str, Any],
    ) -> int:
        explicit_count = _first_metadata_int(
            metadata,
            (
                "cross_view_association_count",
                "cross_view_associated_count",
                "d5_cross_view_association_count",
            ),
        )
        if explicit_count is not None:
            return max(0, explicit_count)

        if event_type in self.CROSS_VIEW_ASSOCIATION_EVENTS:
            success = _bool_from_metadata(
                metadata,
                (
                    "association_success",
                    "cross_view_association_success",
                    "associated",
                    "registered",
                ),
                default=True,
            )
            return int(success)

        if event_type in self.MULTI_VIEW_CONSENSUS_EVENTS:
            success = _bool_from_metadata(
                metadata,
                (
                    "multi_view_consensus",
                    "consensus_reached",
                    "multi_view_consensus_reached",
                    "cross_view_association",
                ),
                default=True,
            )
            return int(success)

        if _bool_from_metadata(
            metadata,
            (
                "cross_view_association",
                "cross_view_association_success",
                "d5_cross_view_association",
            ),
            default=False,
        ):
            return 1
        return 0

    def _secondary_not_registered_increment(
        self,
        event_type: str,
        metadata: Mapping[str, Any],
    ) -> int:
        explicit_count = _first_metadata_int(
            metadata,
            (
                "secondary_detect_available_but_not_registered_count",
                "detect_available_but_not_registered_count",
                "d5_registration_miss_count",
            ),
        )
        if explicit_count is not None:
            return max(0, explicit_count)

        if event_type in self.SECONDARY_DETECT_NOT_REGISTERED_EVENTS:
            return 1

        detect_available = _bool_from_metadata(
            metadata,
            (
                "secondary_detect_available",
                "detect_available",
                "detection_available",
                "bbox_available",
            ),
            default=False,
        )
        registration_keys = (
            "registered",
            "registration_success",
            "d5_registered",
            "terminal_registered",
            "association_registered",
        )
        has_registration_state = any(key in metadata for key in registration_keys)
        if not detect_available or not has_registration_state:
            return 0
        registered = _bool_from_metadata(metadata, registration_keys, default=True)
        return int(not registered)

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
        mode_switch_count = 0
        visual_png_switch_count = 0
        terminal_contract_reject_count = 0
        guidance_law_counts: dict[str, int] = defaultdict(int)
        reject_reasons: dict[str, int] = defaultdict(int)
        contract_reject_reasons: dict[str, int] = defaultdict(int)
        guidance_mode_counts: dict[str, int] = defaultdict(int)
        d4_state_counts: dict[str, int] = defaultdict(int)
        d5_state_counts: dict[str, int] = defaultdict(int)
        plan_version_counts: dict[str, int] = defaultdict(int)
        guidance_law_by_pair: dict[tuple[str, str], tuple[float, str]] = {}
        reject_reasons_by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
        plan_ids: set[str] = set()

        for record in self.event_records:
            metadata = record.metadata
            event_type = _event_type(record)
            guidance_law = metadata.get("guidance_law")
            if guidance_law is not None:
                guidance_law_text = str(guidance_law)
                guidance_law_counts[guidance_law_text] += 1
                pair_key = _intercept_pair_key(record)
                if pair_key is not None:
                    previous = guidance_law_by_pair.get(pair_key)
                    if previous is None or record.timestamp >= previous[0]:
                        guidance_law_by_pair[pair_key] = (
                            record.timestamp,
                            guidance_law_text,
                        )
            mode = _metadata_text(metadata, "mode")
            if mode is not None:
                guidance_mode_counts[mode] += 1
            d4_state = _metadata_text(metadata, "d4_state") or _metadata_text(
                metadata, "d4_mode"
            )
            if d4_state is not None:
                d4_state_counts[d4_state] += 1
            d5_state = _metadata_text(metadata, "d5_state") or _metadata_text(
                metadata, "terminal_state"
            )
            if d5_state is not None:
                d5_state_counts[d5_state] += 1
            plan_id = _metadata_text(metadata, "plan_id")
            if plan_id is not None:
                plan_ids.add(plan_id)
            plan_version = _metadata_text(metadata, "plan_version") or _metadata_text(
                metadata, "version"
            )
            if plan_version is not None:
                plan_version_counts[plan_version] += 1

            if _bool_from_metadata(metadata, ("mode_switch",), default=False):
                mode_switch_count += 1
            if _visual_png_switch_from_event(record):
                visual_png_switch_count += 1

            if (
                event_type
                in self.D7_CONTROL_COMMAND_EVENTS | self.D7_GUIDANCE_RECORD_EVENTS
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

            reject_reason = (
                _metadata_text(metadata, "terminal_switch_reject_reason")
                or _metadata_text(metadata, "terminal_contract_reject_reason")
            )
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
                    pair_key = _intercept_pair_key(record)
                    if pair_key is not None:
                        reject_reasons_by_pair[pair_key].add(reject_reason)

            contract_reject_reason = _metadata_text(
                metadata,
                "terminal_contract_reject_reason",
            )
            if contract_reject_reason is not None:
                terminal_contract_reject_count += 1
                contract_reject_reasons[contract_reject_reason] += 1

        return {
            "camera_quality_gate_pass_rate": _bool_rate(camera_values),
            "los_quality_gate_pass_rate": _bool_rate(los_values),
            "maneuver_margin_gate_pass_rate": _bool_rate(maneuver_values),
            "terminal_switch_allowed_rate": _bool_rate(terminal_switch_allowed_values),
            "visual_png_switch_count": visual_png_switch_count,
            "terminal_switch_reject_count": terminal_switch_reject_count,
            "mode_switch_count": mode_switch_count,
            "terminal_contract_reject_count": terminal_contract_reject_count,
            "gate_reject_count": gate_reject_count,
            "_metadata": {
                "guidance_law_counts": dict(guidance_law_counts),
                "guidance_law_pair_counts": _count_guidance_laws_by_pair(
                    guidance_law_by_pair
                ),
                "terminal_switch_reject_reasons": dict(reject_reasons),
                "terminal_switch_reject_reason_pair_counts": _count_reject_reasons_by_pair(
                    reject_reasons_by_pair
                ),
                "terminal_contract_reject_reasons": dict(contract_reject_reasons),
                "guidance_mode_counts": dict(guidance_mode_counts),
                "d4_state_counts": dict(d4_state_counts),
                "d5_state_counts": dict(d5_state_counts),
                "plan_version_counts": dict(plan_version_counts),
                "plan_ids": sorted(plan_ids),
            },
        }

    def _compute_intercept_metrics(self) -> dict[str, Any]:
        summary_success_count: int | None = None
        summary_pair_count: int | None = None
        pair_events: list[EventRecord] = []
        command_events: list[EventRecord] = []

        for record in self.event_records:
            event_type = _event_type(record)
            if event_type in self.INTERCEPT_SUMMARY_EVENTS:
                value = _metadata_int(record.metadata, "success_count")
                if value is not None:
                    summary_success_count = value
                pair_count = _metadata_int(record.metadata, "pair_count")
                if pair_count is not None:
                    summary_pair_count = pair_count
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

        terminal_takeover = self._terminal_takeover_metrics(
            pair_events,
            command_events,
            summary_pair_count=summary_pair_count,
        )
        result.update(
            {
                key: value
                for key, value in terminal_takeover.items()
                if key != "_metadata"
            }
        )
        result["_metadata"] = {
            **result.get("_metadata", {}),
            **terminal_takeover.get("_metadata", {}),
            "intercept_summary_success_count": summary_success_count,
            "intercept_summary_pair_count": summary_pair_count,
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

    def _terminal_takeover_metrics(
        self,
        pair_events: Sequence[EventRecord],
        command_events: Sequence[EventRecord],
        *,
        summary_pair_count: int | None,
    ) -> dict[str, Any]:
        observed_pairs: set[tuple[str, str]] = set()
        terminal_takeover_pairs: set[tuple[str, str]] = set()
        for record in list(pair_events) + list(command_events):
            pair_key = _intercept_pair_key(record)
            if pair_key is None:
                continue
            observed_pairs.add(pair_key)
            if _terminal_takeover_from_metadata(record.metadata):
                terminal_takeover_pairs.add(pair_key)

        denominator = (
            summary_pair_count
            if summary_pair_count is not None and summary_pair_count > 0
            else len(observed_pairs)
        )
        terminal_takeover_rate = (
            len(terminal_takeover_pairs) / denominator if denominator else 0.0
        )
        return {
            "terminal_takeover_rate": terminal_takeover_rate,
            "_metadata": {
                "terminal_takeover_pair_count": len(terminal_takeover_pairs),
                "terminal_takeover_pair_denominator": denominator,
            },
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



_SECONDARY_NODE_TYPE_KEYS = (
    "secondary_node_type",
    "node_type",
    "camera_node_type",
    "sensor_node_type",
    "platform_role",
    "sensor_role",
    "camera_role",
    "view_node_type",
    "source_node_type",
    "observer_type",
)

_SECONDARY_SENSING_METADATA_KEYS = {
    "secondary_network_joint_full_view_frame_rate",
    "secondary_network_mean_coverage_ratio",
    "secondary_single_camera_full_view_frame_rate",
    "cross_view_association_count",
    "secondary_detect_available_but_not_registered_count",
    "covered_target_ids",
    "visible_target_ids",
    "detected_target_ids",
    "full_view_target_ids",
    "covered_target_count",
    "visible_target_count",
    "detected_target_count",
    "coverage_ratio",
    "secondary_coverage_ratio",
    "network_coverage_ratio",
    "joint_full_view",
    "network_joint_full_view",
    "single_camera_full_view",
    "single_camera_full_view_count",
    "detect_available",
    "detection_available",
    "secondary_detect_available",
    "registration_success",
    "d5_registered",
    "cue_pointing_error_deg",
    "cue_pointing_error_rad",
    "gimbal_pointing_error_deg",
    "gimbal_pointing_error_rad",
    "pointing_error_deg",
    "pointing_error_rad",
}


def _secondary_node_type(
    metadata: Mapping[str, Any],
    *,
    fallback_text: str = "",
) -> str | None:
    for key in _SECONDARY_NODE_TYPE_KEYS:
        value = _metadata_text(metadata, key)
        normalized = _normalize_secondary_node_type(value)
        if normalized is not None:
            return normalized

    for key in ("camera_id", "camera_name", "source_node_id", "resource_id"):
        value = _metadata_text(metadata, key)
        normalized = _normalize_secondary_node_type(value)
        if normalized is not None:
            return normalized
    return _normalize_secondary_node_type(fallback_text)


def _normalize_secondary_node_type(value: Any) -> str | None:
    text = _state(str(value or "")).replace("-", "_").replace(" ", "_")
    if not text:
        return None
    if "fixed_downlook_secondary" in text:
        return "fixed_downlook_secondary"
    if "mobile_recon_gimbal" in text:
        return "mobile_recon_gimbal"
    if "fixed" in text and ("downlook" in text or "down_look" in text):
        return "fixed_downlook_secondary"
    if "secondary" in text and ("downlook" in text or "down_look" in text):
        return "fixed_downlook_secondary"
    if "mobile" in text and ("recon" in text or "gimbal" in text):
        return "mobile_recon_gimbal"
    if "recon" in text and "gimbal" in text:
        return "mobile_recon_gimbal"
    if "gimbal" in text:
        return "mobile_recon_gimbal"
    if "secondary" in text:
        return "secondary_network"
    return None


def _secondary_sample_target_count(
    metadata: Mapping[str, Any],
    *,
    default_target_count: int,
) -> int:
    explicit = _first_metadata_int(
        metadata,
        (
            "target_count",
            "truth_count",
            "total_target_count",
            "expected_target_count",
            "target_object_count",
        ),
    )
    if explicit is not None and explicit > 0:
        return explicit
    return max(0, int(default_target_count or 0))


def _secondary_sample_camera_count(
    metadata: Mapping[str, Any],
    *,
    default_camera_count: int,
) -> int:
    explicit = _first_metadata_int(
        metadata,
        (
            "camera_count",
            "secondary_camera_count",
            "single_camera_total_count",
            "camera_frame_count",
            "single_camera_frame_count",
        ),
    )
    if explicit is not None and explicit > 0:
        return explicit
    return max(0, int(default_camera_count or 0))


def _secondary_coverage_sample(
    metadata: Mapping[str, Any],
) -> dict[str, Any] | None:
    target_ids = _metadata_id_set(
        metadata,
        (
            "covered_target_ids",
            "visible_target_ids",
            "detected_target_ids",
            "full_view_target_ids",
            "target_ids",
        ),
    )
    covered_count = _first_metadata_int(
        metadata,
        (
            "covered_target_count",
            "visible_target_count",
            "detected_target_count",
            "secondary_visible_target_count",
            "network_covered_target_count",
            "joint_covered_target_count",
            "full_view_target_count",
        ),
    )
    coverage_ratio = _first_metadata_float(
        metadata,
        (
            "coverage_ratio",
            "secondary_coverage_ratio",
            "network_coverage_ratio",
            "joint_coverage_ratio",
            "mean_coverage_ratio",
            "secondary_network_mean_coverage_ratio",
        ),
    )
    full_view = _secondary_bool_value(
        metadata,
        (
            "network_joint_full_view",
            "joint_full_view",
            "full_view",
            "full_coverage",
            "all_targets_visible",
            "all_targets_in_fov",
            "secondary_network_joint_full_view",
        ),
    )
    if (
        not target_ids
        and covered_count is None
        and coverage_ratio is None
        and full_view is None
    ):
        return None
    return {
        "target_ids": target_ids,
        "covered_count": None if covered_count is None else max(0, covered_count),
        "coverage_ratio": (
            None if coverage_ratio is None else _clamp_ratio(coverage_ratio)
        ),
        "full_view": full_view,
    }


def _secondary_frame_key(sample: Mapping[str, Any]) -> tuple[Any, ...]:
    metadata = sample["metadata"]
    frame_id = (
        metadata.get("secondary_frame_id")
        or metadata.get("frame_id")
        or metadata.get("frame_index")
        or metadata.get("timestamp")
        or sample.get("timestamp")
    )
    return (frame_id,)


def _add_secondary_frame_coverage(
    frames: dict[tuple[Any, ...], dict[str, Any]],
    frame_key: tuple[Any, ...],
    coverage: Mapping[str, Any],
    target_count: int,
) -> None:
    frame = frames.setdefault(
        frame_key,
        {
            "target_count": max(0, int(target_count or 0)),
            "target_ids": set(),
            "covered_count": None,
            "coverage_ratios": [],
            "full_view_values": [],
        },
    )
    if target_count > 0 and not frame["target_count"]:
        frame["target_count"] = int(target_count)
    frame["target_ids"].update(coverage.get("target_ids", set()))
    covered_count = coverage.get("covered_count")
    if covered_count is not None:
        previous = frame.get("covered_count")
        frame["covered_count"] = max(int(previous or 0), int(covered_count))
    coverage_ratio = coverage.get("coverage_ratio")
    if coverage_ratio is not None:
        frame["coverage_ratios"].append(_clamp_ratio(float(coverage_ratio)))
    full_view = coverage.get("full_view")
    if full_view is not None:
        frame["full_view_values"].append(bool(full_view))


def _secondary_frame_stats(
    frames: Mapping[tuple[Any, ...], Mapping[str, Any]],
) -> dict[str, float | int]:
    coverage_ratios: list[float] = []
    full_view_values: list[bool] = []
    for frame in frames.values():
        ratio = _secondary_frame_coverage_ratio(frame)
        if ratio is not None:
            coverage_ratios.append(ratio)
        full_view = _secondary_frame_full_view(frame, ratio)
        if full_view is not None:
            full_view_values.append(full_view)
    return {
        "full_view_frame_rate": _bool_rate(full_view_values),
        "mean_coverage_ratio": _mean(coverage_ratios),
        "frame_count": len(frames),
    }


def _secondary_frame_coverage_ratio(frame: Mapping[str, Any]) -> float | None:
    target_count = int(frame.get("target_count") or 0)
    target_ids = frame.get("target_ids", set())
    if target_count > 0 and target_ids:
        return _clamp_ratio(len(target_ids) / target_count)
    covered_count = frame.get("covered_count")
    if target_count > 0 and covered_count is not None:
        return _clamp_ratio(float(covered_count) / target_count)
    ratios = frame.get("coverage_ratios", [])
    if ratios:
        return _clamp_ratio(max(float(value) for value in ratios))
    return None


def _secondary_frame_full_view(
    frame: Mapping[str, Any],
    coverage_ratio: float | None,
) -> bool | None:
    if coverage_ratio is not None:
        return coverage_ratio >= 1.0
    values = frame.get("full_view_values", [])
    if values:
        return any(bool(value) for value in values)
    return None


def _secondary_single_camera_counts(
    metadata: Mapping[str, Any],
    coverage: Mapping[str, Any] | None,
    *,
    sample_target_count: int,
    sample_camera_count: int,
) -> tuple[int, int]:
    full_count = _first_metadata_int(
        metadata,
        (
            "single_camera_full_view_count",
            "secondary_single_camera_full_view_count",
            "camera_full_view_count",
        ),
    )
    if full_count is not None:
        total_count = _first_metadata_int(
            metadata,
            (
                "single_camera_total_count",
                "single_camera_frame_count",
                "camera_frame_count",
                "secondary_camera_count",
                "camera_count",
            ),
        )
        if total_count is None or total_count <= 0:
            total_count = sample_camera_count or full_count
        return max(0, full_count), max(max(0, full_count), int(total_count))

    single_full = _secondary_bool_value(
        metadata,
        (
            "single_camera_full_view",
            "camera_full_view",
            "secondary_single_camera_full_view",
        ),
    )
    if single_full is not None:
        return int(single_full), 1

    camera_id = _metadata_text(metadata, "camera_id") or _metadata_text(
        metadata,
        "camera_name",
    )
    if camera_id is None or coverage is None:
        return 0, 0

    ratio = _secondary_coverage_ratio_from_sample(coverage, sample_target_count)
    if ratio is not None:
        return int(ratio >= 1.0), 1
    full_view = coverage.get("full_view")
    if full_view is not None:
        return int(bool(full_view)), 1
    return 0, 0


def _secondary_coverage_ratio_from_sample(
    coverage: Mapping[str, Any],
    target_count: int,
) -> float | None:
    target_ids = coverage.get("target_ids", set())
    if target_count > 0 and target_ids:
        return _clamp_ratio(len(target_ids) / target_count)
    covered_count = coverage.get("covered_count")
    if target_count > 0 and covered_count is not None:
        return _clamp_ratio(float(covered_count) / target_count)
    coverage_ratio = coverage.get("coverage_ratio")
    if coverage_ratio is not None:
        return _clamp_ratio(float(coverage_ratio))
    return None


def _metadata_id_set(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> set[str]:
    for key in keys:
        if key not in metadata:
            continue
        values = _id_values(metadata[key])
        if values:
            return values
    return set()


def _id_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, Mapping):
        ids: set[str] = set()
        for key in ("target_id", "truth_id", "global_track_id", "object_id", "id"):
            if key in value and value[key] is not None:
                ids.add(str(value[key]))
        if ids:
            return ids
        return {str(key) for key in value if str(key).strip()}
    if isinstance(value, (list, tuple, set)):
        ids: set[str] = set()
        for item in value:
            ids.update(_id_values(item))
        return ids
    text = str(value).strip()
    if not text:
        return set()
    if "," in text:
        return {item.strip() for item in text.split(",") if item.strip()}
    return {text}


def _metadata_angle_values_deg(
    metadata: Mapping[str, Any],
    *,
    degree_keys: Sequence[str],
    radian_keys: Sequence[str],
) -> list[float]:
    values: list[float] = []
    for key in degree_keys:
        if key in metadata:
            values.extend(_metadata_float_values(metadata[key]))
    for key in radian_keys:
        if key in metadata:
            values.extend(
                math.degrees(value) for value in _metadata_float_values(metadata[key])
            )
    return values


def _metadata_float_values(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in ("value", "error", "angle", "mean"):
            if key in value:
                return _metadata_float_values(value[key])
        return []
    if isinstance(value, (list, tuple, set)):
        values: list[float] = []
        for item in value:
            values.extend(_metadata_float_values(item))
        return values
    if isinstance(value, str) and "," in value:
        values: list[float] = []
        for item in value.split(","):
            values.extend(_metadata_float_values(item.strip()))
        return values
    try:
        return [float(value)]
    except (TypeError, ValueError):
        return []


def _angle_error_stats(values: Sequence[float]) -> dict[str, float | int]:
    magnitudes = [abs(float(value)) for value in values]
    if not magnitudes:
        return {"count": 0, "mean": 0.0, "rmse": 0.0, "max": 0.0}
    return {
        "count": len(magnitudes),
        "mean": _mean(magnitudes),
        "rmse": math.sqrt(sum(value * value for value in magnitudes) / len(magnitudes)),
        "max": max(magnitudes),
    }


def _secondary_bool_value(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> bool | None:
    for key in keys:
        if key in metadata:
            return _as_bool(metadata[key], default=False)
    return None


def _first_metadata_int(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> int | None:
    for key in keys:
        if key in metadata:
            value = _optional_int_value(metadata[key])
            if value is not None:
                return value
    return None


def _clamp_ratio(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _metric_scope_from_truth_summary(truth_summary: Mapping[str, Any]) -> str:
    for mapping in _truth_summary_count_mappings(truth_summary):
        for key in (
            "metric_scope",
            "metrics_scope",
            "evaluation_scope",
            "metrics_kind",
            "source_scope",
        ):
            if key in mapping and mapping[key] is not None:
                return _normalize_metric_scope(mapping[key])
        for key in ("source_path", "metrics_path", "metrics_file"):
            if key in mapping and mapping[key] is not None:
                scoped = _normalize_metric_scope(mapping[key])
                if scoped != "not_recorded":
                    return scoped
    return "not_recorded"


def _normalize_metric_scope(value: Any) -> str:
    text = _state(str(value or ""))
    if not text:
        return "not_recorded"
    normalized = text.replace("-", "_").replace(" ", "_")
    if "contract" in normalized:
        return "contract"
    if (
        normalized in {"exec", "executed", "execution", "runtime", "actual"}
        or "execution" in normalized
    ):
        return "execution"
    if "main_episode_bus_metrics" in normalized:
        return "execution"
    return normalized


def _active_degradation_review_label(record: EventRecord) -> str | None:
    metadata = record.metadata
    for key in (
        "review_label",
        "active_degradation_review_label",
        "degradation_review_label",
        "active_degradation_label",
    ):
        label = _metadata_text(metadata, key)
        if label is not None:
            return _normalized_label(label)

    for key in (
        "active_degradation_necessary",
        "degradation_necessary",
        "necessary_active_degradation",
        "was_necessary",
    ):
        if key in metadata:
            necessary = _as_bool(metadata[key], default=False)
            return "necessary" if necessary else "unnecessary"

    for key in (
        "post_window_outcome",
        "post_active_outcome",
        "active_degradation_outcome",
        "review_outcome",
    ):
        label = _metadata_text(metadata, key)
        if label is not None:
            return _normalized_label(label)

    risk_reduction = _active_degradation_risk_reduction(metadata)
    if risk_reduction is not None:
        return "risk_reduced" if risk_reduction > 0.0 else "no_risk_reduction"
    return None


def _active_degradation_review_class(label: str | None) -> str | None:
    if label is None:
        return None
    normalized = _normalized_label(label)
    necessary_labels = {
        "necessary",
        "needed",
        "required",
        "warranted",
        "justified",
        "true_positive",
        "tp",
        "useful",
        "beneficial",
        "improved",
        "stabilized",
        "stabilised",
        "risk_reduced",
        "coverage_restored",
        "reassign_completed",
        "secondary_takeover_success",
        "prevented_failover",
    }
    unnecessary_labels = {
        "unnecessary",
        "not_needed",
        "unneeded",
        "false_positive",
        "fp",
        "avoidable",
        "spurious",
        "no_improvement",
        "unchanged",
        "worse",
        "failed",
        "no_risk_reduction",
    }
    if normalized in necessary_labels:
        return "necessary"
    if normalized in unnecessary_labels:
        return "unnecessary"
    return None


def _normalized_label(value: Any) -> str:
    return _state(str(value)).replace("-", "_").replace(" ", "_")


def _active_degradation_risk_reduction(metadata: Mapping[str, Any]) -> float | None:
    for key in (
        "risk_reduction",
        "risk_reduction_score",
        "post_window_risk_reduction",
        "coverage_gap_reduction",
    ):
        value = _metadata_float_if_present(metadata, key)
        if value is not None:
            return value

    pre_risk = _first_metadata_float(
        metadata,
        (
            "pre_window_risk_score",
            "pre_active_risk_score",
            "risk_score_before",
            "pre_window_coverage_gap_count",
        ),
    )
    post_risk = _first_metadata_float(
        metadata,
        (
            "post_window_risk_score",
            "post_active_risk_score",
            "risk_score_after",
            "post_window_coverage_gap_count",
        ),
    )
    if pre_risk is None or post_risk is None:
        return None
    return pre_risk - post_risk


def _first_metadata_float(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> float | None:
    for key in keys:
        value = _metadata_float_if_present(metadata, key)
        if value is not None:
            return value
    return None


def _metadata_float_if_present(metadata: Mapping[str, Any], key: str) -> float | None:
    if key not in metadata or metadata[key] is None:
        return None
    try:
        return float(metadata[key])
    except (TypeError, ValueError):
        return None


def _state(value: str | None) -> str:
    return (value or "").strip().lower()


def _intercept_pair_key(record: EventRecord) -> tuple[str, str] | None:
    resource_id = (
        _metadata_text(record.metadata, "resource_id")
        or _metadata_text(record.metadata, "vehicle_name")
        or record.actor_id
    )
    target_id = _metadata_text(record.metadata, "target_id") or _metadata_text(
        record.metadata,
        "global_track_id",
    )
    if resource_id is None and target_id is None:
        return None
    return (str(resource_id or ""), str(target_id or ""))


def _terminal_takeover_from_metadata(metadata: Mapping[str, Any]) -> bool:
    if _bool_from_metadata(
        metadata,
        (
            "terminal_locked",
            "terminal_switch_allowed",
            "terminal_mode_entered",
            "terminal_takeover",
        ),
        default=False,
    ):
        return True
    mode = _metadata_text(metadata, "mode") or _metadata_text(metadata, "guidance_mode")
    if _state(mode) in {
        "terminal",
        "vision_terminal",
        "terminal_guidance",
        "vision_terminal_guidance",
    }:
        return True
    guidance_law = _metadata_text(metadata, "guidance_law")
    return _state(guidance_law) in {"png_vm", "png_ttc", "los"}


def _visual_png_switch_from_event(record: EventRecord) -> bool:
    metadata = record.metadata
    event_type = _event_type(record)
    if _bool_from_metadata(
        metadata,
        (
            "visual_png_switch",
            "vision_png_switch",
            "png_switch",
            "switched_to_visual_png",
        ),
        default=False,
    ):
        return True
    guidance_law = _state(_metadata_text(metadata, "guidance_law"))
    mode = _state(_metadata_text(metadata, "mode") or _metadata_text(metadata, "guidance_mode"))
    return (
        event_type
        in {
            "visual_png_switch",
            "vision_png_switch",
            "d7_visual_png_switch",
        }
        or guidance_law in {"png_vm", "png_ttc", "visual_png", "vision_png"}
        and (
            _bool_from_metadata(metadata, ("mode_switch",), default=False)
            or mode in {"vision_terminal", "visual_png", "vision_png"}
            or _bool_from_metadata(metadata, ("terminal_mode_entered",), default=False)
        )
    )


def _count_guidance_laws_by_pair(
    guidance_law_by_pair: Mapping[tuple[str, str], tuple[float, str]],
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for _, guidance_law in guidance_law_by_pair.values():
        counts[guidance_law] += 1
    return dict(counts)


def _count_reject_reasons_by_pair(
    reject_reasons_by_pair: Mapping[tuple[str, str], set[str]],
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for reasons in reject_reasons_by_pair.values():
        for reason in reasons:
            counts[reason] += 1
    return dict(counts)


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


def _scenario_group_from_truth_summary(truth_summary: Mapping[str, Any]) -> str:
    explicit = truth_summary.get("scenario_group") or truth_summary.get("scenario_type")
    if explicit is None:
        scenario = truth_summary.get("scenario", {})
        if isinstance(scenario, Mapping):
            explicit = scenario.get("group") or scenario.get("scenario_group")
            if explicit is None:
                explicit = scenario.get("name")
    text = _state(str(explicit or ""))
    if not text:
        return "unlabeled"
    if text in {
        "normal",
        "secondary_200m",
        "distributed",
        "terminal_handoff_tuned",
        "multi_view_inconsistent",
    }:
        return text
    if "secondary" in text and "200" in text:
        return "secondary_200m"
    if "distributed" in text:
        return "distributed"
    if "terminal" in text and ("handoff" in text or "handover" in text) and "tuned" in text:
        return "terminal_handoff_tuned"
    if "multi" in text and "view" in text and "inconsistent" in text:
        return "multi_view_inconsistent"
    if "normal" in text or "baseline" in text:
        return "normal"
    return text


def _batch_seed_from_truth_summary(truth_summary: Mapping[str, Any]) -> int | None:
    for key in ("batch_seed", "seed"):
        if key in truth_summary and truth_summary[key] is not None:
            return int(truth_summary[key])
    scenario = truth_summary.get("scenario", {})
    if isinstance(scenario, Mapping):
        for key in ("batch_seed", "seed"):
            if key in scenario and scenario[key] is not None:
                return int(scenario[key])
    return None


def _target_count_from_truth_summary(truth_summary: Mapping[str, Any]) -> int | None:
    explicit = _count_from_truth_summary(
        truth_summary,
        (
            "target_count",
            "truth_count",
            "truth_object_count",
            "target_object_count",
        ),
    )
    if explicit is not None:
        return explicit
    truth_timestamps = _truth_timestamps_by_id(truth_summary)
    if truth_timestamps:
        return len(truth_timestamps)
    return _count_from_truth_summary(truth_summary, ("drone_count",))


def _resource_count_from_truth_summary(truth_summary: Mapping[str, Any]) -> int | None:
    return _count_from_truth_summary(
        truth_summary,
        (
            "resource_count",
            "drone_count",
            "uav_count",
            "vehicle_count",
            "interceptor_count",
        ),
    )


def _camera_count_from_truth_summary(truth_summary: Mapping[str, Any]) -> int | None:
    return _count_from_truth_summary(
        truth_summary,
        (
            "camera_count",
            "camera_node_count",
            "camera_resource_count",
        ),
    )


def _drone_count_from_truth_summary(truth_summary: Mapping[str, Any]) -> int | None:
    return _count_from_truth_summary(
        truth_summary,
        (
            "drone_count",
            "uav_count",
            "resource_count",
            "vehicle_count",
        ),
    )


def _count_from_truth_summary(
    truth_summary: Mapping[str, Any],
    keys: Sequence[str],
) -> int | None:
    mappings = _truth_summary_count_mappings(truth_summary)
    for mapping in mappings:
        for key in keys:
            if key not in mapping:
                continue
            value = _optional_int_value(mapping[key])
            if value is not None:
                return value
    return None


def _truth_summary_count_mappings(
    truth_summary: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    mappings: list[Mapping[str, Any]] = [truth_summary]
    scenario = truth_summary.get("scenario", {})
    if isinstance(scenario, Mapping):
        mappings.append(scenario)

    for mapping in list(mappings):
        for nested_key in ("counts", "metadata", "scale"):
            nested = mapping.get(nested_key)
            if isinstance(nested, Mapping):
                mappings.append(nested)
    return mappings


def _optional_int_value(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _add_camera_id_from_metadata(camera_ids: set[str], metadata: Mapping[str, Any]) -> None:
    camera_id = _metadata_text(metadata, "camera_id")
    if camera_id is not None:
        camera_ids.add(camera_id)
        return

    camera = metadata.get("camera")
    if isinstance(camera, Mapping):
        nested_camera_id = _metadata_text(camera, "camera_id")
        if nested_camera_id is not None:
            camera_ids.add(nested_camera_id)
            return

    owner = (
        _metadata_text(metadata, "camera_vehicle_name")
        or _metadata_text(metadata, "owner_id")
        or _metadata_text(metadata, "vehicle_name")
    )
    camera_name = _metadata_text(metadata, "camera_name")
    if owner is not None and camera_name is not None:
        camera_ids.add(f"{owner}:{camera_name}")
    elif camera_name is not None:
        camera_ids.add(camera_name)


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
