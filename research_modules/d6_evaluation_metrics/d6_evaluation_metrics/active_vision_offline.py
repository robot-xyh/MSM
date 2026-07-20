"""Fail-closed offline audit of D5 active-vision runtime evidence.

The evaluator consumes persisted episode-bus envelopes and summary counters.  It
does not import the runtime stack, infer scale from scenario names, or turn a
missing command/ack stream into a zero.  A learned suggestion, a D5-selected
assist action, a main-runtime acknowledgement, and a physical outcome are kept
as separate evidence layers.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import math
from typing import Any, Callable, Mapping, Sequence


ACTIVE_VISION_TOPIC = "modules.d5.active_vision"
ACTIVE_VISION_RUNTIME_SCHEMA = "d5.active-vision-runtime.v1"
CAMERA_COMMAND_ACK_TOPIC = "runtime.camera_command_ack"
CAMERA_COMMAND_ACK_SCHEMA = "scalable3d-camera-command-ack-v1"

ACTIVE_VISION_NUMERIC_METRIC_FIELDS = (
    "d5_active_vision_publication_count",
    "d5_active_vision_command_issued_count",
    "d5_active_vision_rule_command_count",
    "d5_active_vision_shadow_suggestion_count",
    "d5_active_vision_assist_adopted_count",
    "d5_active_vision_ack_count",
    "d5_active_vision_ack_applied_count",
    "d5_active_vision_ack_rejected_count",
    "d5_active_vision_ack_matched_count",
    "d5_active_vision_unacknowledged_command_count",
    "d5_active_vision_unexpected_ack_count",
    "d5_active_vision_ack_completion_rate",
    "d5_active_vision_rule_applied_count",
    "d5_active_vision_assist_applied_count",
    "d5_active_vision_ack_latency_p50_ms",
    "d5_active_vision_ack_latency_p95_ms",
    "d5_active_vision_ack_latency_max_ms",
    "d5_active_vision_rejected_expired_count",
    "d5_active_vision_rejected_stale_version_count",
    "d5_active_vision_rejected_camera_unavailable_count",
    "d5_active_vision_rejected_other_count",
    "d5_active_vision_target_reference_count",
    "d5_active_vision_target_reference_evaluable_count",
    "d5_active_vision_target_reference_consistent_count",
    "d5_active_vision_target_reference_violation_count",
    "d5_active_vision_target_reference_consistency_rate",
    "d5_active_vision_ack_target_mismatch_count",
    "d5_active_vision_online_truth_field_violation_count",
    "d5_active_vision_summary_counter_consistent",
)

_MODES = frozenset({"disabled", "shadow", "assist"})
_INTENTS = frozenset({"observe_target", "search_sector", "hold", "reacquire"})
_TARGET_INTENTS = frozenset({"observe_target", "reacquire"})
_STALE_REASONS = frozenset(
    {
        "stale_plan_version",
        "stale_coalition_version",
        "stale_communication_version",
    }
)
_EXPIRED_REASONS = frozenset({"command_expired", "command_issued_in_future"})
_CAMERA_UNAVAILABLE_REASONS = frozenset({"camera_or_resource_unavailable"})


@dataclass(frozen=True)
class ActiveVisionOfflineEvidence:
    metrics: dict[str, Any]
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True)
class _Command:
    order: int
    camera_id: str
    resource_id: str
    issued_timestamp: float
    expires_timestamp: float
    plan_version: int
    coalition_version: int
    communication_version: int
    intent: str
    target_global_track_id: str | None
    requested_mode: str
    effective_mode: str
    reason: str

    @property
    def correlation_key(self) -> tuple[Any, ...]:
        return (
            self.camera_id,
            self.resource_id,
            self.issued_timestamp,
            self.plan_version,
            self.coalition_version,
            self.communication_version,
            self.intent,
            self.requested_mode,
            self.effective_mode,
        )


@dataclass(frozen=True)
class _Ack:
    camera_id: str
    resource_id: str
    issued_timestamp: float
    ack_timestamp: float
    expires_timestamp: float
    plan_version: int
    coalition_version: int
    communication_version: int
    intent: str
    target_global_track_id: str | None
    requested_mode: str
    effective_mode: str
    status: str
    reason: str

    @property
    def correlation_key(self) -> tuple[Any, ...]:
        return (
            self.camera_id,
            self.resource_id,
            self.issued_timestamp,
            self.plan_version,
            self.coalition_version,
            self.communication_version,
            self.intent,
            self.requested_mode,
            self.effective_mode,
        )


def evaluate_active_vision_runtime_evidence(
    records: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any] | None,
    *,
    online_unavailable_reason: str | None,
    forbidden_field_counter: Callable[[Any], int],
) -> ActiveVisionOfflineEvidence:
    """Evaluate active-vision output and runtime ACKs without control imports."""

    metrics: dict[str, Any] = {}
    failures: list[str] = []
    active_records = [
        record for record in records if record.get("topic") == ACTIVE_VISION_TOPIC
    ]
    ack_records = [
        record
        for record in records
        if record.get("topic") == CAMERA_COMMAND_ACK_TOPIC
    ]

    if online_unavailable_reason is not None:
        _mark_all_unavailable(metrics, online_unavailable_reason)
        return ActiveVisionOfflineEvidence(metrics, ())
    if not active_records:
        _mark_all_unavailable(metrics, "d5_active_vision_publication_missing")
        return ActiveVisionOfflineEvidence(metrics, ())

    relevant_records = [*active_records, *ack_records]
    _put_available(
        metrics,
        "d5_active_vision_online_truth_field_violation_count",
        sum(forbidden_field_counter(record) for record in relevant_records),
    )

    commands, command_error = _parse_commands(records, active_records)
    if command_error is not None:
        _mark_command_metrics_unavailable(metrics, command_error)
        _mark_ack_metrics_unavailable(metrics, command_error)
        _mark_reference_metrics_unavailable(metrics, command_error)
        _put_unavailable(
            metrics,
            "d5_active_vision_physical_outcome_attribution",
            command_error,
        )
        failures.append("d5_active_vision_command_evidence_invalid")
        return ActiveVisionOfflineEvidence(metrics, tuple(failures))

    _extract_command_metrics(metrics, active_records, commands)
    _extract_reference_metrics(metrics, records, commands)
    if int(metrics["d5_active_vision_target_reference_evaluable_count"]) < int(
        metrics["d5_active_vision_target_reference_count"]
    ):
        failures.append("d5_active_vision_center_track_reference_evidence_incomplete")

    acks: tuple[_Ack, ...] | None
    ack_error: str | None
    if ack_records:
        acks, ack_error = _parse_acks(ack_records)
    elif not commands and _summary_explicitly_reports_zero_acks(summary):
        acks, ack_error = (), None
    else:
        acks, ack_error = None, "runtime_camera_command_ack_missing"

    if ack_error is not None or acks is None:
        _mark_ack_metrics_unavailable(
            metrics,
            ack_error or "runtime_camera_command_ack_missing",
        )
        _put_unavailable(
            metrics,
            "d5_active_vision_ack_target_mismatch_count",
            ack_error or "runtime_camera_command_ack_missing",
        )
        if commands:
            failures.append("d5_active_vision_ack_evidence_incomplete")
    else:
        _extract_ack_metrics(metrics, commands, acks)
        if metrics.get("d5_active_vision_unexpected_ack_count", 0) or metrics.get(
            "d5_active_vision_unacknowledged_command_count", 0
        ):
            failures.append("d5_active_vision_command_ack_correlation_incomplete")

    _audit_summary(metrics, summary, failures)
    _put_unavailable(
        metrics,
        "d5_active_vision_physical_outcome_attribution",
        _attribution_unavailable_reason(metrics),
    )
    _put_available(
        metrics,
        "d5_active_vision_evidence_layer_semantics_json",
        {
            "rule_command": "actual D5 command selected by the deterministic rule path",
            "shadow_suggestion": (
                "valid model suggestion observed in shadow mode; the issued command remains rule"
            ),
            "assist_adopted": (
                "D5 selected a safety-screened learned action; runtime application still needs ACK"
            ),
            "ack_applied": "main runtime applied the issued camera command",
            "physical_attribution": (
                "requires paired control/treatment episodes and applied assist evidence"
            ),
        },
    )
    return ActiveVisionOfflineEvidence(
        metrics,
        tuple(dict.fromkeys(failures)),
    )


def _parse_commands(
    all_records: Sequence[Mapping[str, Any]],
    active_records: Sequence[Mapping[str, Any]],
) -> tuple[tuple[_Command, ...], str | None]:
    order_by_id = {id(record): order for order, record in enumerate(all_records)}
    commands: list[_Command] = []
    seen_per_publication: set[tuple[Any, ...]]
    for record in active_records:
        if record.get("schema_version") != ACTIVE_VISION_RUNTIME_SCHEMA:
            return (), "unsupported_d5_active_vision_runtime_schema"
        payload = _payload(record)
        raw_commands = payload.get("commands")
        declared = payload.get("command_count")
        if not isinstance(raw_commands, list):
            return (), "d5_active_vision_commands_missing_or_invalid"
        if not _is_nonnegative_int(declared) or int(declared) != len(raw_commands):
            return (), "d5_active_vision_command_count_mismatch"
        seen_per_publication = set()
        effective_counts: Counter[str] = Counter()
        intent_counts: Counter[str] = Counter()
        for raw in raw_commands:
            if not isinstance(raw, Mapping):
                return (), "d5_active_vision_command_not_object"
            try:
                command = _command_from_mapping(
                    raw,
                    order=order_by_id.get(id(record), len(all_records)),
                )
            except ValueError as exc:
                return (), f"d5_active_vision_command_invalid:{exc}"
            duplicate_key = (command.camera_id, command.issued_timestamp)
            if duplicate_key in seen_per_publication:
                return (), "d5_active_vision_duplicate_camera_command"
            seen_per_publication.add(duplicate_key)
            commands.append(command)
            effective_counts[command.effective_mode] += 1
            intent_counts[command.intent] += 1
        if "effective_mode_counts" in payload and not _counter_matches(
            payload.get("effective_mode_counts"), effective_counts
        ):
            return (), "d5_active_vision_effective_mode_count_mismatch"
        if "intent_counts" in payload and not _counter_matches(
            payload.get("intent_counts"), intent_counts
        ):
            return (), "d5_active_vision_intent_count_mismatch"
    return tuple(commands), None


def _command_from_mapping(raw: Mapping[str, Any], *, order: int) -> _Command:
    camera_id = _required_string(raw, "camera_id")
    resource_id = _required_string(raw, "resource_id")
    issued = _required_nonnegative_float(raw, "issued_timestamp")
    expires = _required_nonnegative_float(raw, "expires_timestamp")
    if expires <= issued:
        raise ValueError("expires_timestamp_not_after_issue")
    plan_version = _required_nonnegative_int(raw, "plan_version")
    coalition_version = _required_nonnegative_int(raw, "coalition_version")
    communication_version = _required_nonnegative_int(raw, "communication_version")
    intent = _required_choice(raw, "intent", _INTENTS)
    requested_mode = _required_choice(raw, "requested_mode", _MODES)
    effective_mode = _required_choice(raw, "effective_mode", _MODES)
    reason = _required_string(raw, "reason")
    target = _optional_string(raw, "target_global_track_id")
    if intent in _TARGET_INTENTS and target is None:
        raise ValueError("target_reference_missing_for_target_intent")
    if intent not in _TARGET_INTENTS and target is not None:
        raise ValueError("target_reference_present_for_nontarget_intent")
    if requested_mode == "disabled" and effective_mode != "disabled":
        raise ValueError("disabled_request_has_nonrule_effective_mode")
    if effective_mode == "assist" and requested_mode != "assist":
        raise ValueError("assist_effective_mode_without_assist_request")
    return _Command(
        order=int(order),
        camera_id=camera_id,
        resource_id=resource_id,
        issued_timestamp=issued,
        expires_timestamp=expires,
        plan_version=plan_version,
        coalition_version=coalition_version,
        communication_version=communication_version,
        intent=intent,
        target_global_track_id=target,
        requested_mode=requested_mode,
        effective_mode=effective_mode,
        reason=reason,
    )


def _parse_acks(
    records: Sequence[Mapping[str, Any]],
) -> tuple[tuple[_Ack, ...], str | None]:
    acks: list[_Ack] = []
    for record in records:
        if record.get("schema_version") != CAMERA_COMMAND_ACK_SCHEMA:
            return (), "unsupported_camera_command_ack_schema"
        raw = _payload(record)
        try:
            ack = _ack_from_mapping(raw)
        except ValueError as exc:
            return (), f"camera_command_ack_invalid:{exc}"
        acks.append(ack)
    return tuple(acks), None


def _ack_from_mapping(raw: Mapping[str, Any]) -> _Ack:
    camera_id = _required_string(raw, "camera_id")
    resource_id = _required_string(raw, "resource_id")
    issued = _required_nonnegative_float(raw, "issued_timestamp")
    acknowledged = _required_nonnegative_float(raw, "ack_timestamp")
    expires = _required_nonnegative_float(raw, "expires_timestamp")
    if acknowledged + 1.0e-12 < issued:
        raise ValueError("ack_precedes_issue")
    if expires <= issued:
        raise ValueError("expires_timestamp_not_after_issue")
    plan_version = _required_nonnegative_int(raw, "plan_version")
    coalition_version = _required_nonnegative_int(raw, "coalition_version")
    communication_version = _required_nonnegative_int(raw, "communication_version")
    intent = _required_choice(raw, "intent", _INTENTS)
    requested_mode = _required_choice(raw, "requested_mode", _MODES)
    effective_mode = _required_choice(raw, "effective_mode", _MODES)
    status = _required_choice(raw, "status", frozenset({"applied", "rejected"}))
    reason = _required_string(raw, "reason")
    target = _optional_string(raw, "target_global_track_id")
    if intent in _TARGET_INTENTS and target is None:
        raise ValueError("target_reference_missing_for_target_intent")
    if intent not in _TARGET_INTENTS and target is not None:
        raise ValueError("target_reference_present_for_nontarget_intent")
    if status == "applied" and reason != "accepted":
        raise ValueError("applied_ack_reason_not_accepted")
    if status == "rejected" and reason == "accepted":
        raise ValueError("rejected_ack_reason_is_accepted")
    return _Ack(
        camera_id=camera_id,
        resource_id=resource_id,
        issued_timestamp=issued,
        ack_timestamp=acknowledged,
        expires_timestamp=expires,
        plan_version=plan_version,
        coalition_version=coalition_version,
        communication_version=communication_version,
        intent=intent,
        target_global_track_id=target,
        requested_mode=requested_mode,
        effective_mode=effective_mode,
        status=status,
        reason=reason,
    )


def _extract_command_metrics(
    metrics: dict[str, Any],
    active_records: Sequence[Mapping[str, Any]],
    commands: Sequence[_Command],
) -> None:
    requested = Counter(command.requested_mode for command in commands)
    effective = Counter(command.effective_mode for command in commands)
    intents = Counter(command.intent for command in commands)
    rule_count = sum(command.effective_mode != "assist" for command in commands)
    shadow_count = sum(
        command.requested_mode == "shadow"
        and command.effective_mode == "shadow"
        and "fallback=" not in command.reason
        for command in commands
    )
    assist_count = sum(command.effective_mode == "assist" for command in commands)
    for field, value in (
        ("d5_active_vision_publication_count", len(active_records)),
        ("d5_active_vision_command_issued_count", len(commands)),
        ("d5_active_vision_rule_command_count", rule_count),
        ("d5_active_vision_shadow_suggestion_count", shadow_count),
        ("d5_active_vision_assist_adopted_count", assist_count),
        ("d5_active_vision_requested_mode_distribution_json", dict(sorted(requested.items()))),
        ("d5_active_vision_effective_mode_distribution_json", dict(sorted(effective.items()))),
        ("d5_active_vision_intent_distribution_json", dict(sorted(intents.items()))),
    ):
        _put_available(metrics, field, value)


def _extract_reference_metrics(
    metrics: dict[str, Any],
    records: Sequence[Mapping[str, Any]],
    commands: Sequence[_Command],
) -> None:
    center_snapshots: list[tuple[int, set[str] | None]] = []
    for order, record in enumerate(records):
        if record.get("topic") != "modules.d2.associated_tracks":
            continue
        tracks = _payload(record).get("tracks")
        if not isinstance(tracks, list) or not all(isinstance(item, Mapping) for item in tracks):
            center_snapshots.append((order, None))
            continue
        identifiers: set[str] = set()
        valid = True
        for track in tracks:
            track_id = track.get("global_track_id")
            if not isinstance(track_id, str) or not track_id.strip():
                valid = False
                break
            identifiers.add(track_id.strip())
        center_snapshots.append((order, identifiers if valid else None))

    references = [command for command in commands if command.target_global_track_id is not None]
    evaluable = 0
    consistent = 0
    violations = 0
    for command in references:
        prior = [item for item in center_snapshots if item[0] < command.order]
        if not prior or prior[-1][1] is None:
            continue
        evaluable += 1
        if command.target_global_track_id in prior[-1][1]:
            consistent += 1
        else:
            violations += 1
    for field, value in (
        ("d5_active_vision_target_reference_count", len(references)),
        ("d5_active_vision_target_reference_evaluable_count", evaluable),
    ):
        _put_available(metrics, field, value)
    if evaluable == len(references):
        _put_available(
            metrics,
            "d5_active_vision_target_reference_consistent_count",
            consistent,
        )
        _put_available(
            metrics,
            "d5_active_vision_target_reference_violation_count",
            violations,
        )
    else:
        reason = "preceding_d2_global_track_snapshot_unavailable"
        _put_unavailable(
            metrics,
            "d5_active_vision_target_reference_consistent_count",
            reason,
        )
        _put_unavailable(
            metrics,
            "d5_active_vision_target_reference_violation_count",
            reason,
        )
    if evaluable > 0 and evaluable == len(references):
        _put_available(
            metrics,
            "d5_active_vision_target_reference_consistency_rate",
            consistent / evaluable,
        )
    else:
        _put_unavailable(
            metrics,
            "d5_active_vision_target_reference_consistency_rate",
            (
                "no_target_reference_opportunity"
                if not references
                else "preceding_d2_global_track_snapshot_unavailable"
            ),
        )


def _extract_ack_metrics(
    metrics: dict[str, Any],
    commands: Sequence[_Command],
    acks: Sequence[_Ack],
) -> None:
    command_indices: dict[tuple[Any, ...], deque[int]] = defaultdict(deque)
    for index, command in enumerate(commands):
        command_indices[command.correlation_key].append(index)

    matched: list[tuple[_Command, _Ack]] = []
    unexpected = 0
    for ack in acks:
        candidates = command_indices.get(ack.correlation_key)
        if not candidates:
            unexpected += 1
            continue
        matched.append((commands[candidates.popleft()], ack))
    unmatched = sum(len(indices) for indices in command_indices.values())
    status_counts = Counter(ack.status for ack in acks)
    rejection_reasons = Counter(ack.reason for ack in acks if ack.status == "rejected")
    target_mismatches = sum(
        command.target_global_track_id != ack.target_global_track_id
        for command, ack in matched
    )
    latencies_ms = [
        max(0.0, (ack.ack_timestamp - command.issued_timestamp) * 1000.0)
        for command, ack in matched
    ]
    rule_applied = sum(
        command.effective_mode != "assist" and ack.status == "applied"
        for command, ack in matched
    )
    assist_applied = sum(
        command.effective_mode == "assist" and ack.status == "applied"
        for command, ack in matched
    )
    expired = sum(rejection_reasons[reason] for reason in _EXPIRED_REASONS)
    stale = sum(rejection_reasons[reason] for reason in _STALE_REASONS)
    unavailable = sum(
        rejection_reasons[reason] for reason in _CAMERA_UNAVAILABLE_REASONS
    )
    categorized = expired + stale + unavailable
    values = (
        ("d5_active_vision_ack_count", len(acks)),
        ("d5_active_vision_ack_applied_count", status_counts["applied"]),
        ("d5_active_vision_ack_rejected_count", status_counts["rejected"]),
        ("d5_active_vision_ack_matched_count", len(matched)),
        ("d5_active_vision_unacknowledged_command_count", unmatched),
        ("d5_active_vision_unexpected_ack_count", unexpected),
        ("d5_active_vision_rule_applied_count", rule_applied),
        ("d5_active_vision_assist_applied_count", assist_applied),
        ("d5_active_vision_rejected_expired_count", expired),
        ("d5_active_vision_rejected_stale_version_count", stale),
        ("d5_active_vision_rejected_camera_unavailable_count", unavailable),
        ("d5_active_vision_rejected_other_count", max(0, status_counts["rejected"] - categorized)),
        ("d5_active_vision_ack_target_mismatch_count", target_mismatches),
        ("d5_active_vision_rejection_reason_distribution_json", dict(sorted(rejection_reasons.items()))),
    )
    for field, value in values:
        _put_available(metrics, field, value)
    if commands:
        _put_available(
            metrics,
            "d5_active_vision_ack_completion_rate",
            len(matched) / len(commands),
        )
    else:
        _put_unavailable(
            metrics,
            "d5_active_vision_ack_completion_rate",
            "no_issued_camera_commands",
        )
    if latencies_ms:
        ordered = sorted(latencies_ms)
        _put_available(metrics, "d5_active_vision_ack_latency_p50_ms", _percentile(ordered, 50.0))
        _put_available(metrics, "d5_active_vision_ack_latency_p95_ms", _percentile(ordered, 95.0))
        _put_available(metrics, "d5_active_vision_ack_latency_max_ms", max(ordered))
    else:
        for field in (
            "d5_active_vision_ack_latency_p50_ms",
            "d5_active_vision_ack_latency_p95_ms",
            "d5_active_vision_ack_latency_max_ms",
        ):
            _put_unavailable(metrics, field, "no_matched_camera_command_ack")


def _audit_summary(
    metrics: dict[str, Any],
    summary: Mapping[str, Any] | None,
    failures: list[str],
) -> None:
    fields = {
        "camera_command_issued_count": "d5_active_vision_command_issued_count",
        "camera_command_applied_count": "d5_active_vision_ack_applied_count",
        "camera_command_rejected_count": "d5_active_vision_ack_rejected_count",
        "camera_command_ack_count": "d5_active_vision_ack_count",
    }
    if not isinstance(summary, Mapping):
        _put_unavailable(
            metrics,
            "d5_active_vision_summary_counter_consistent",
            "summary_json_missing",
        )
        failures.append("d5_active_vision_summary_counter_missing")
        return
    missing = [field for field in fields if field not in summary]
    if missing:
        _put_unavailable(
            metrics,
            "d5_active_vision_summary_counter_consistent",
            "camera_command_summary_counters_missing:" + ",".join(sorted(missing)),
        )
        failures.append("d5_active_vision_summary_counter_missing")
        return
    valid = all(_is_nonnegative_int(summary.get(field)) for field in fields)
    if not valid:
        _put_unavailable(
            metrics,
            "d5_active_vision_summary_counter_consistent",
            "camera_command_summary_counters_invalid",
        )
        failures.append("d5_active_vision_summary_counter_invalid")
        return
    if any(metrics.get(f"{metric}_availability") != "available" for metric in fields.values()):
        _put_unavailable(
            metrics,
            "d5_active_vision_summary_counter_consistent",
            "camera_command_log_counters_unavailable",
        )
        failures.append("d5_active_vision_summary_counter_unverifiable")
        return
    consistent = all(
        int(summary[source]) == int(metrics[target])
        for source, target in fields.items()
    )
    summary_reasons = summary.get("camera_command_rejection_reason_counts")
    log_reasons = metrics.get("d5_active_vision_rejection_reason_distribution_json")
    reasons_consistent = _counter_matches(summary_reasons, Counter(log_reasons or {}))
    consistent = consistent and reasons_consistent
    _put_available(metrics, "d5_active_vision_summary_counter_consistent", consistent)
    if not consistent:
        failures.append("d5_active_vision_summary_counter_mismatch")


def _attribution_unavailable_reason(metrics: Mapping[str, Any]) -> str:
    if metrics.get("d5_active_vision_assist_applied_count_availability") != "available":
        return "assist_runtime_application_evidence_unavailable"
    if int(metrics.get("d5_active_vision_assist_applied_count", 0)) <= 0:
        return "no_assist_action_applied"
    return "paired_control_treatment_episode_evidence_missing"


def _summary_explicitly_reports_zero_acks(summary: Mapping[str, Any] | None) -> bool:
    if not isinstance(summary, Mapping):
        return False
    return all(
        _is_nonnegative_int(summary.get(field)) and int(summary[field]) == 0
        for field in (
            "camera_command_issued_count",
            "camera_command_applied_count",
            "camera_command_rejected_count",
            "camera_command_ack_count",
        )
    ) and _counter_matches(
        summary.get("camera_command_rejection_reason_counts"), Counter()
    )


def _mark_all_unavailable(metrics: dict[str, Any], reason: str) -> None:
    _mark_command_metrics_unavailable(metrics, reason)
    _mark_ack_metrics_unavailable(metrics, reason)
    _mark_reference_metrics_unavailable(metrics, reason)
    _put_unavailable(metrics, "d5_active_vision_ack_target_mismatch_count", reason)
    _put_unavailable(metrics, "d5_active_vision_online_truth_field_violation_count", reason)
    _put_unavailable(metrics, "d5_active_vision_summary_counter_consistent", reason)
    _put_unavailable(metrics, "d5_active_vision_physical_outcome_attribution", reason)
    _put_unavailable(metrics, "d5_active_vision_evidence_layer_semantics_json", reason)


def _mark_command_metrics_unavailable(metrics: dict[str, Any], reason: str) -> None:
    for field in (
        "d5_active_vision_publication_count",
        "d5_active_vision_command_issued_count",
        "d5_active_vision_rule_command_count",
        "d5_active_vision_shadow_suggestion_count",
        "d5_active_vision_assist_adopted_count",
        "d5_active_vision_requested_mode_distribution_json",
        "d5_active_vision_effective_mode_distribution_json",
        "d5_active_vision_intent_distribution_json",
    ):
        _put_unavailable(metrics, field, reason)


def _mark_ack_metrics_unavailable(metrics: dict[str, Any], reason: str) -> None:
    for field in (
        "d5_active_vision_ack_count",
        "d5_active_vision_ack_applied_count",
        "d5_active_vision_ack_rejected_count",
        "d5_active_vision_ack_matched_count",
        "d5_active_vision_unacknowledged_command_count",
        "d5_active_vision_unexpected_ack_count",
        "d5_active_vision_ack_completion_rate",
        "d5_active_vision_rule_applied_count",
        "d5_active_vision_assist_applied_count",
        "d5_active_vision_ack_latency_p50_ms",
        "d5_active_vision_ack_latency_p95_ms",
        "d5_active_vision_ack_latency_max_ms",
        "d5_active_vision_rejected_expired_count",
        "d5_active_vision_rejected_stale_version_count",
        "d5_active_vision_rejected_camera_unavailable_count",
        "d5_active_vision_rejected_other_count",
        "d5_active_vision_rejection_reason_distribution_json",
    ):
        _put_unavailable(metrics, field, reason)


def _mark_reference_metrics_unavailable(metrics: dict[str, Any], reason: str) -> None:
    for field in (
        "d5_active_vision_target_reference_count",
        "d5_active_vision_target_reference_evaluable_count",
        "d5_active_vision_target_reference_consistent_count",
        "d5_active_vision_target_reference_violation_count",
        "d5_active_vision_target_reference_consistency_rate",
    ):
        _put_unavailable(metrics, field, reason)


def _payload(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = record.get("payload")
    return dict(payload) if isinstance(payload, Mapping) else {}


def _required_string(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_missing_or_invalid")
    return value.strip()


def _optional_string(payload: Mapping[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_invalid")
    return value.strip()


def _required_nonnegative_float(payload: Mapping[str, Any], field: str) -> float:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field}_missing_or_invalid")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{field}_missing_or_invalid")
    return numeric


def _required_nonnegative_int(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if not _is_nonnegative_int(value):
        raise ValueError(f"{field}_missing_or_invalid")
    return int(value)


def _required_choice(
    payload: Mapping[str, Any],
    field: str,
    choices: frozenset[str],
) -> str:
    value = _required_string(payload, field).lower()
    if value not in choices:
        raise ValueError(f"{field}_unsupported")
    return value


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _counter_matches(value: Any, expected: Counter[str]) -> bool:
    if not isinstance(value, Mapping):
        return False
    normalized: Counter[str] = Counter()
    for key, count in value.items():
        if not _is_nonnegative_int(count):
            return False
        normalized[str(key)] = int(count)
    return normalized == expected


def _percentile(ordered: Sequence[float], percentile: float) -> float:
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * percentile / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction)


def _put_available(metrics: dict[str, Any], field: str, value: Any) -> None:
    metrics[field] = value
    metrics[f"{field}_availability"] = "available"
    metrics[f"{field}_unavailable_reason"] = None


def _put_unavailable(metrics: dict[str, Any], field: str, reason: str) -> None:
    metrics[field] = None
    metrics[f"{field}_availability"] = "unavailable"
    metrics[f"{field}_unavailable_reason"] = str(reason)


__all__ = [
    "ACTIVE_VISION_NUMERIC_METRIC_FIELDS",
    "ACTIVE_VISION_RUNTIME_SCHEMA",
    "ACTIVE_VISION_TOPIC",
    "ActiveVisionOfflineEvidence",
    "CAMERA_COMMAND_ACK_SCHEMA",
    "CAMERA_COMMAND_ACK_TOPIC",
    "evaluate_active_vision_runtime_evidence",
]
