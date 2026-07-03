"""Main-to-D4 arbitration adapter for offline integration.

The adapter is intentionally passive. It converts D1/D2/D3/D5-like objects or
dict summaries into the D4 `ActiveDegradationArbiter` inputs, then returns a
D6-friendly decision record and event metadata. It does not publish commands,
change assignments, or call any simulator/control API.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

import numpy as np

from .active_degradation import (
    ActiveDegradationArbiter,
    ActiveDegradationDecision,
    AssignmentValiditySummary,
    AssociationRiskSummary,
    DegradationAction,
    DegradationMode,
    TerminalAssociationSummary,
    TerminalDecisionState,
    TrackUncertaintySummary,
    summarize_secondary_lifecycle,
)
from .models import (
    C2Health,
    CommunicationSummary,
    LinkType,
    PayloadKind,
    ResourceSummary,
    SecondaryNodeLifecycleSummary,
    to_jsonable,
)


FRIEND_CONFLICT_STATES = {
    "verified_friend_overlap",
    "friend_conflict",
    "friend_overlap_hold",
    "blocked_by_friend",
}


@dataclass(frozen=True)
class D4DecisionRecord:
    """Module-neutral D4 decision record for main and D6 logs."""

    timestamp: float
    resource_id: str
    global_track_id: str
    mode: DegradationMode
    action: DegradationAction
    reason: str
    selected_coordinator: str
    trigger_reason: str
    trigger_timestamp: float
    decision_timestamp: float
    review_label: str = "unknown"
    plan_id: str | None = None
    plan_version: int | None = None
    track_version: int | None = None
    target_node_id: str | None = None
    coverage_cell: str | None = None
    terminal_consistent: bool = False
    risk_factors: tuple[str, ...] = ()
    c2_health: C2Health = C2Health.NORMAL
    secondary_available: bool = False
    communication_fresh: bool | None = None
    secondary_lifecycle: tuple[SecondaryNodeLifecycleSummary, ...] = ()
    requires_human_review: bool = False
    arbitration_source: str = "d4_arbitration_adapter"

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def to_event_metadata(self) -> dict[str, Any]:
        """Return metadata that can be embedded in a D6 EventRecord."""

        return {
            "d4_action": self.action.value,
            "degradation_mode": _d6_degradation_mode(self.mode),
            "d4_degradation_mode": self.mode.value,
            "d4_reason": self.reason,
            "selected_coordinator": self.selected_coordinator,
            "trigger_reason": self.trigger_reason,
            "trigger_timestamp": self.trigger_timestamp,
            "decision_timestamp": self.decision_timestamp,
            "review_label": self.review_label,
            "resource_id": self.resource_id,
            "global_track_id": self.global_track_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "track_version": self.track_version,
            "target_node_id": self.target_node_id,
            "coverage_cell": self.coverage_cell,
            "terminal_consistent": self.terminal_consistent,
            "risk_factors": list(self.risk_factors),
            "c2_health": self.c2_health.value,
            "secondary_available": self.secondary_available,
            "communication_fresh": self.communication_fresh,
            "secondary_lifecycle": to_jsonable(self.secondary_lifecycle),
            "requires_human_review": self.requires_human_review,
            "arbitration_source": self.arbitration_source,
        }

    def to_event_record_kwargs(self) -> dict[str, Any]:
        """Return kwargs compatible with D6 EventRecord construction."""

        return {
            "timestamp": self.timestamp,
            "event_type": _d6_event_type(self.mode),
            "actor_id": self.resource_id,
            "severity": "info" if self.mode == DegradationMode.NONE else "warning",
            "note": self.reason,
            "metadata": self.to_event_metadata(),
        }


@dataclass(frozen=True)
class D4ArbitrationResult:
    """Adapter output with the exact summaries submitted to D4."""

    track_uncertainty: TrackUncertaintySummary
    association_risk: AssociationRiskSummary
    assignment_validity: AssignmentValiditySummary
    terminal_association: TerminalAssociationSummary
    communication_summaries: tuple[CommunicationSummary, ...]
    secondary_lifecycle: tuple[SecondaryNodeLifecycleSummary, ...]
    decision: ActiveDegradationDecision
    record: D4DecisionRecord

    def to_event_metadata(self) -> dict[str, Any]:
        metadata = self.record.to_event_metadata()
        metadata.update(
            {
                "track_uncertainty": to_jsonable(self.track_uncertainty),
                "association_risk": to_jsonable(self.association_risk),
                "assignment_validity": to_jsonable(self.assignment_validity),
                "terminal_association": to_jsonable(self.terminal_association),
                "secondary_lifecycle": to_jsonable(self.secondary_lifecycle),
            }
        )
        return metadata


class D4ArbitrationAdapter:
    """Build D4 arbitration inputs from main/integration module objects."""

    def __init__(self, arbiter: ActiveDegradationArbiter | None = None) -> None:
        self.arbiter = arbiter or ActiveDegradationArbiter()

    def evaluate(
        self,
        *,
        timestamp: float,
        track: Any,
        association_result: Any | None = None,
        association_metrics: Any | None = None,
        plan: Any | None = None,
        assignment: Any | None = None,
        terminal_association: Any,
        cross_view_summary: Any | None = None,
        c2_health: C2Health | str = C2Health.NORMAL,
        secondary_nodes: Sequence[ResourceSummary] = (),
        communication_records: Sequence[Any] = (),
        coverage_cell: str | None = None,
        resource_id: str | None = None,
        global_track_id: str | None = None,
        observed_global_track_id: str | None = None,
        consecutive_non_locked_frames: int = 0,
        consecutive_mismatch_frames: int = 0,
        current_plan_version: int | None = None,
        expected_plan_version: int | None = None,
        track_version: int | None = None,
        plan_id: str | None = None,
        trigger_timestamp: float | None = None,
        review_label: str = "unknown",
    ) -> D4ArbitrationResult:
        """Build summaries, run the arbiter, and return a decision record."""

        resolved_track_id = (
            global_track_id
            or _string_or_none(_get(track, "global_track_id"))
            or _string_or_none(_get(track, "track_id"))
            or _string_or_none(_get(assignment, "target_id"))
            or _string_or_none(_get(terminal_association, "assigned_global_track_id"))
            or "unknown_track"
        )
        resolved_resource_id = (
            resource_id
            or _string_or_none(_get(assignment, "resource_id"))
            or _string_or_none(_get(terminal_association, "resource_id"))
            or "unknown_resource"
        )
        resolved_coverage = coverage_cell or _coverage_cell(track, assignment, terminal_association)
        track_summary = build_track_uncertainty_summary(
            track,
            timestamp=timestamp,
            global_track_id=resolved_track_id,
            coverage_cell=resolved_coverage,
        )
        association_summary = build_association_risk_summary(
            track_id=resolved_track_id,
            association_result=association_result,
            association_metrics=association_metrics,
        )
        assignment_summary = build_assignment_validity_summary(
            plan=plan,
            assignment=assignment,
            timestamp=timestamp,
            global_track_id=resolved_track_id,
            resource_id=resolved_resource_id,
            current_plan_version=current_plan_version,
            expected_plan_version=expected_plan_version,
        )
        terminal_summary = build_terminal_association_summary(
            terminal_association=terminal_association,
            resource_id=resolved_resource_id,
            assigned_global_track_id=resolved_track_id,
            coverage_cell=resolved_coverage,
            observed_global_track_id=observed_global_track_id,
            consecutive_non_locked_frames=consecutive_non_locked_frames,
            consecutive_mismatch_frames=consecutive_mismatch_frames,
            cross_view_summary=cross_view_summary,
        )
        communications = tuple(
            item
            for item in (
                build_communication_summary(record)
                for record in communication_records
            )
            if item is not None
        )
        lifecycle = summarize_secondary_lifecycle(
            list(secondary_nodes),
            resolved_coverage,
            communication_summaries=list(communications) if communications else None,
            current_time_s=timestamp,
        )
        health = _c2_health(c2_health)
        decision = self.arbiter.evaluate(
            track_uncertainty=track_summary,
            association_risk=association_summary,
            assignment_validity=assignment_summary,
            terminal_association=terminal_summary,
            c2_health=health,
            secondary_nodes=list(secondary_nodes),
            communication_summaries=list(communications) if communications else None,
            current_time_s=timestamp,
        )
        record = D4DecisionRecord(
            timestamp=float(timestamp),
            resource_id=resolved_resource_id,
            global_track_id=resolved_track_id,
            mode=decision.mode,
            action=decision.action,
            reason=decision.reason,
            selected_coordinator=_selected_coordinator(decision.action),
            trigger_reason=decision.reason,
            trigger_timestamp=float(trigger_timestamp if trigger_timestamp is not None else timestamp),
            decision_timestamp=float(timestamp),
            review_label=review_label,
            plan_id=plan_id or _string_or_none(_get(plan, "plan_id")),
            plan_version=_optional_int(_get(plan, "version", _get(plan, "plan_version"))),
            track_version=track_version or _optional_int(_metadata(track).get("track_version")),
            target_node_id=decision.target_node_id,
            coverage_cell=decision.coverage_cell or resolved_coverage,
            terminal_consistent=decision.terminal_consistent,
            risk_factors=decision.risk_factors,
            c2_health=health,
            secondary_available=_secondary_available(lifecycle),
            communication_fresh=_communication_fresh(communications, timestamp),
            secondary_lifecycle=lifecycle,
            requires_human_review=decision.requires_human_review,
        )
        return D4ArbitrationResult(
            track_uncertainty=track_summary,
            association_risk=association_summary,
            assignment_validity=assignment_summary,
            terminal_association=terminal_summary,
            communication_summaries=communications,
            secondary_lifecycle=lifecycle,
            decision=decision,
            record=record,
        )


def build_track_uncertainty_summary(
    track: Any,
    *,
    timestamp: float,
    global_track_id: str | None = None,
    coverage_cell: str | None = None,
) -> TrackUncertaintySummary:
    if isinstance(track, TrackUncertaintySummary):
        return track

    metadata = _metadata(track)
    track_id = (
        global_track_id
        or _string_or_none(_get(track, "global_track_id"))
        or _string_or_none(_get(track, "track_id"))
        or "unknown_track"
    )
    covariance = _covariance_matrix(_get(track, "covariance", _get(track, "covariance_6d")))
    position_covariance = _position_covariance(covariance)
    eigvals = np.linalg.eigvalsh(position_covariance)
    position_sigma_m = float(np.sqrt(max(float(eigvals[-1]), 0.0)))
    velocity_covariance = _velocity_covariance(covariance)
    velocity_sigma = float(np.sqrt(max(float(np.trace(velocity_covariance)), 0.0)))
    valid_at = _first_float(
        metadata.get("valid_at"),
        metadata.get("latest_measurement_timestamp"),
        metadata.get("measurement_timestamp"),
        _get(track, "last_update_time"),
        _get(track, "timestamp"),
        timestamp,
    )
    return TrackUncertaintySummary(
        track_id=track_id,
        coverage_cell=coverage_cell or _string_or_none(metadata.get("coverage_cell")) or "unknown",
        position_sigma_m=position_sigma_m,
        covariance_trace=float(np.trace(covariance)),
        velocity_sigma_mps=velocity_sigma,
        measurement_age_s=max(0.0, float(timestamp) - valid_at),
    )


def build_association_risk_summary(
    *,
    track_id: str,
    association_result: Any | None = None,
    association_metrics: Any | None = None,
) -> AssociationRiskSummary:
    if isinstance(association_result, AssociationRiskSummary):
        return association_result
    if isinstance(association_metrics, AssociationRiskSummary):
        return association_metrics

    result_metadata = _metadata(association_result)
    metric_summary = _call_if_present(association_metrics, "summary") or {}
    ambiguity = _first_float(
        _get(association_result, "ambiguity_score"),
        result_metadata.get("association_ambiguity"),
        _get(association_metrics, "latest_association_ambiguity"),
        _get(association_metrics, "association_ambiguity"),
        metric_summary.get("association_ambiguity"),
        0.0,
    )
    duplicate_count = _first_int(
        _get(association_metrics, "duplicate_track_count"),
        _get(association_metrics, "duplicate_assignment_count"),
        result_metadata.get("duplicate_track_count"),
        int(float(result_metadata.get("duplicate_track_risk", 0.0)) >= 0.5),
        metric_summary.get("duplicate_assignment_count"),
        0,
    )
    return AssociationRiskSummary(
        track_id=track_id,
        ambiguity_score=ambiguity,
        id_switch_count=_first_int(
            _get(association_metrics, "id_switch_count"),
            result_metadata.get("id_switch_count"),
            metric_summary.get("id_switch_count"),
            0,
        ),
        duplicate_track_count=duplicate_count,
        track_continuity=_first_float(
            _get(association_metrics, "track_continuity"),
            _get(association_metrics, "identity_continuity"),
            result_metadata.get("track_continuity"),
            metric_summary.get("track_continuity"),
            1.0,
        ),
    )


def build_assignment_validity_summary(
    *,
    plan: Any | None,
    assignment: Any | None,
    timestamp: float,
    global_track_id: str,
    resource_id: str,
    current_plan_version: int | None = None,
    expected_plan_version: int | None = None,
) -> AssignmentValiditySummary:
    if isinstance(plan, AssignmentValiditySummary):
        return plan

    plan_version = _first_int(
        _get(plan, "version"),
        _get(plan, "plan_version"),
        _get(assignment, "plan_version"),
        0,
    )
    created_at = _first_float(_get(plan, "created_at"), _get(assignment, "timestamp"), timestamp)
    stale_after_s = _optional_float(_get(plan, "stale_after_s", _get(assignment, "stale_after_s")))
    decision_state = (_string_or_none(_get(plan, "decision_state")) or "accepted").lower()
    is_current = decision_state not in {"stale", "obsolete", "rejected", "expired"}
    if expected_plan_version is not None:
        is_current = is_current and plan_version == int(expected_plan_version)
    if current_plan_version is not None:
        is_current = is_current and plan_version == int(current_plan_version)
    plan_age = max(0.0, float(timestamp) - created_at)
    if stale_after_s is not None and plan_age > stale_after_s:
        is_current = False

    return AssignmentValiditySummary(
        global_track_id=global_track_id,
        assigned_resource_id=resource_id,
        plan_version=plan_version,
        is_current=is_current,
        plan_age_s=plan_age,
        cost_margin=_cost_margin(plan, assignment),
    )


def build_terminal_association_summary(
    *,
    terminal_association: Any,
    resource_id: str,
    assigned_global_track_id: str,
    coverage_cell: str,
    observed_global_track_id: str | None = None,
    consecutive_non_locked_frames: int = 0,
    consecutive_mismatch_frames: int = 0,
    cross_view_summary: Any | None = None,
) -> TerminalAssociationSummary:
    if isinstance(terminal_association, TerminalAssociationSummary):
        return terminal_association

    friend_state = (_string_or_none(_get(terminal_association, "friend_conflict_state")) or "none").lower()
    duplicate_lock = bool(
        _get(terminal_association, "duplicate_terminal_lock", False)
        or _get(cross_view_summary, "duplicate_terminal_lock_risk", False)
    )
    cross_view_risk = _first_float(
        _get(cross_view_summary, "ambiguity_score"),
        _get(cross_view_summary, "cross_view_risk_score"),
        0.75 if duplicate_lock else 0.0,
    )
    if duplicate_lock:
        cross_view_risk = max(cross_view_risk, 0.75)

    return TerminalAssociationSummary(
        resource_id=resource_id,
        assigned_global_track_id=assigned_global_track_id,
        decision_state=_terminal_decision_state(_get(terminal_association, "decision_state")),
        association_confidence=_first_float(_get(terminal_association, "association_confidence"), 0.0),
        ambiguity_score=_first_float(_get(terminal_association, "ambiguity_score"), 1.0),
        coverage_cell=coverage_cell,
        observed_global_track_id=observed_global_track_id
        or _string_or_none(_get(terminal_association, "observed_global_track_id")),
        consecutive_non_locked_frames=int(consecutive_non_locked_frames),
        consecutive_mismatch_frames=int(consecutive_mismatch_frames),
        friend_conflict=bool(_get(terminal_association, "friend_conflict", False))
        or friend_state in FRIEND_CONFLICT_STATES,
        duplicate_terminal_lock=duplicate_lock,
        cross_view_risk_score=cross_view_risk,
        cross_view_support_count=_first_int(_get(cross_view_summary, "support_count"), 0),
    )


def build_communication_summary(record: Any) -> CommunicationSummary | None:
    if record is None:
        return None
    if isinstance(record, CommunicationSummary):
        return record

    sent = _optional_float(_get(record, "sent_timestamp"))
    received = _optional_float(_get(record, "received_timestamp", _get(record, "arrival_timestamp")))
    timestamp = _optional_float(_get(record, "timestamp"))
    if sent is None:
        sent = timestamp
    if received is None:
        received = timestamp
    if sent is None or received is None:
        return None

    return CommunicationSummary(
        source_node_id=_string_or_none(_get(record, "source_node_id")) or "unknown_source",
        target_node_id=_string_or_none(_get(record, "target_node_id")) or "broadcast",
        relay_node_id=_string_or_none(_get(record, "relay_node_id")),
        link_type=_link_type(_get(record, "link_type"), _get(record, "payload_kind")),
        sent_timestamp=float(sent),
        received_timestamp=float(received),
        payload_kind=_payload_kind(_get(record, "payload_kind", _get(record, "message_type"))),
        stale_after_s=_first_float(_get(record, "stale_after_s"), 1.0),
        sequence_id=_string_or_none(_get(record, "sequence_id")),
    )


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _metadata(obj: Any) -> dict[str, Any]:
    metadata = _get(obj, "metadata", {})
    if isinstance(metadata, Mapping):
        return dict(metadata)
    return {}


def _call_if_present(obj: Any, name: str) -> Any:
    method = getattr(obj, name, None)
    if callable(method):
        return method()
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    text = str(value)
    return text if text else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_float(*values: Any) -> float:
    for value in values:
        parsed = _optional_float(value)
        if parsed is not None:
            return parsed
    return 0.0


def _first_int(*values: Any) -> int:
    for value in values:
        parsed = _optional_int(value)
        if parsed is not None:
            return parsed
    return 0


def _covariance_matrix(value: Any) -> np.ndarray:
    if value is None:
        return np.eye(2, dtype=float) * 1_000_000.0
    array = np.asarray(value, dtype=float)
    if array.ndim == 1:
        array = np.diag(array)
    if array.ndim != 2 or array.shape[0] != array.shape[1]:
        return np.eye(2, dtype=float) * 1_000_000.0
    return array.copy()


def _position_covariance(covariance: np.ndarray) -> np.ndarray:
    if covariance.shape[0] >= 6:
        return covariance[:3, :3]
    if covariance.shape[0] >= 3:
        return covariance[:3, :3]
    return covariance[:2, :2]


def _velocity_covariance(covariance: np.ndarray) -> np.ndarray:
    if covariance.shape[0] >= 6:
        return covariance[3:6, 3:6]
    if covariance.shape[0] >= 4:
        return covariance[2:4, 2:4]
    return np.zeros((1, 1), dtype=float)


def _coverage_cell(*objects: Any) -> str:
    for obj in objects:
        metadata = _metadata(obj)
        value = _string_or_none(metadata.get("coverage_cell")) or _string_or_none(_get(obj, "coverage_cell"))
        if value:
            return value
    return "unknown"


def _cost_margin(plan: Any | None, assignment: Any | None) -> float:
    explicit = _optional_float(_get(assignment, "cost_margin"))
    if explicit is not None:
        return explicit

    candidate_total = _optional_float(_get(plan, "candidate_total_cost"))
    previous_total = _optional_float(_get(plan, "previous_total_cost_current"))
    if candidate_total is not None and previous_total is not None:
        return max(0.0, min((previous_total - candidate_total) / max(abs(previous_total), 1.0), 1.0))

    assignments = _get(plan, "assignments", ())
    costs: list[float] = []
    for item in assignments or ():
        cost = _optional_float(_get(item, "cost"))
        if cost is not None:
            costs.append(cost)
    if len(costs) >= 2:
        ordered = sorted(costs)
        return max(0.0, min(ordered[1] - ordered[0], 1.0))
    return 1.0


def _terminal_decision_state(value: Any) -> TerminalDecisionState:
    raw = (_string_or_none(value) or "reacquire").lower()
    if raw in {item.value for item in TerminalDecisionState}:
        return TerminalDecisionState(raw)
    if raw in {"lock", "terminal_lock"}:
        return TerminalDecisionState.LOCKED
    if raw in {"observed", "unknown"}:
        return TerminalDecisionState.AMBIGUOUS
    return TerminalDecisionState.HOLD


def _c2_health(value: C2Health | str) -> C2Health:
    if isinstance(value, C2Health):
        return value
    return C2Health(str(value))


def _link_type(value: Any, payload_kind: Any = None) -> LinkType:
    raw = (_string_or_none(value) or "").lower()
    if raw in {item.value for item in LinkType}:
        return LinkType(raw)
    payload = (_string_or_none(payload_kind) or "").lower()
    if payload in {"video", "video_cue", "video_metadata", "bbox"}:
        return LinkType.VIDEO_CUE
    if raw in {"secondary", "relay", "secondary_recon"}:
        return LinkType.SECONDARY_RELAY
    if raw in {"peer", "interceptor"}:
        return LinkType.INTERCEPTOR_PEER
    return LinkType.C2_DIRECT


def _payload_kind(value: Any) -> PayloadKind:
    raw = (_string_or_none(value) or "").lower()
    aliases = {
        "data": PayloadKind.RESOURCE_SUMMARY,
        "video": PayloadKind.VIDEO_METADATA,
        "video_cue": PayloadKind.VIDEO_METADATA,
        "detection_box": PayloadKind.BBOX,
        "detection_bbox": PayloadKind.BBOX,
        "terminal": PayloadKind.TERMINAL_ASSOCIATION,
        "resource": PayloadKind.RESOURCE_SUMMARY,
        "track_summary": PayloadKind.TRACK,
    }
    if raw in {item.value for item in PayloadKind}:
        return PayloadKind(raw)
    return aliases.get(raw, PayloadKind.RESOURCE_SUMMARY)


def _secondary_available(nodes: Sequence[SecondaryNodeLifecycleSummary]) -> bool:
    return any(node.secondary_available for node in nodes)


def _communication_fresh(records: Sequence[CommunicationSummary], timestamp: float) -> bool | None:
    if not records:
        return None
    return any(not record.is_stale(timestamp) for record in records)


def dataclass_to_dict(value: Any) -> dict[str, Any]:
    """Return a JSON-ready dict for dataclass-like adapter values."""

    if is_dataclass(value):
        return to_jsonable(asdict(value))
    return to_jsonable(value)


def _d6_degradation_mode(mode: DegradationMode) -> str:
    if mode == DegradationMode.ACTIVE_DEGRADATION:
        return "active"
    if mode == DegradationMode.PASSIVE_FAILOVER:
        return "passive"
    return "none"


def _d6_event_type(mode: DegradationMode) -> str:
    if mode == DegradationMode.ACTIVE_DEGRADATION:
        return "active_degradation_decision"
    if mode == DegradationMode.PASSIVE_FAILOVER:
        return "passive_failover_start"
    return "d4_arbitration_decision"


def _selected_coordinator(action: DegradationAction) -> str:
    if action in {
        DegradationAction.CONTINUE_CENTER,
        DegradationAction.REQUEST_CENTER_REPLAN,
    }:
        return "center"
    if action in {
        DegradationAction.REQUEST_SECONDARY_ASSIST,
        DegradationAction.DEGRADE_TO_SECONDARY,
    }:
        return "secondary_node"
    if action == DegradationAction.DEGRADE_TO_DISTRIBUTED:
        return "distributed_cbba"
    return "hold_review"
