"""Main-to-D4 arbitration adapter for offline integration.

The adapter is intentionally passive. It converts D1/D2/D3/D5-like objects or
dict summaries into the D4 `ActiveDegradationArbiter` inputs, then returns a
D6-friendly decision record and event metadata. It does not publish commands,
change assignments, or call any simulator/control API.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .active_degradation import (
    ActiveDegradationArbiter,
    ActiveDegradationDecision,
    AssignmentValiditySummary,
    AssociationRiskSummary,
    DegradationAction,
    DegradationMode,
    SecondaryTakeoverPlanMetadata,
    TerminalAssociationSummary,
    TerminalDecisionState,
    TrackUncertaintySummary,
    build_secondary_takeover_plan_metadata,
    summarize_secondary_lifecycle,
)
from .models import (
    AvailabilityBand,
    C2Health,
    CommBand,
    CommunicationSummary,
    DistributedVisualEvidenceSummary,
    LinkType,
    NodeRole,
    PayloadKind,
    ResourceSummary,
    SecondaryNodeLifecycleSummary,
    TrackSummary,
    to_jsonable,
)


FRIEND_CONFLICT_STATES = {
    "verified_friend_overlap",
    "friend_conflict",
    "friend_overlap_hold",
    "blocked_by_friend",
}

REGISTRATION_BREAKPOINT_TERMS = (
    "global_binding",
    "global binding",
    "global-track binding",
    "global_track_binding",
    "registration",
    "registered",
    "cross_view_registration",
)
ACTIVE_DEGRADATION_REVIEW_LABELS = frozenset(
    {"necessary", "unnecessary", "inconclusive"}
)
DEFAULT_REVIEW_PRE_WINDOW_S = 2.0
DEFAULT_REVIEW_POST_WINDOW_S = 5.0
ADAPTER_HARD_RISK_FACTORS = frozenset(
    {
        "d1_track_uncertainty_high",
        "d1_covariance_trace_high",
        "d1_measurement_stale",
        "d2_id_switch_observed",
        "d2_duplicate_track_observed",
        "d2_track_continuity_low",
        "d3_assignment_not_current",
        "d3_assignment_stale",
        "d5_duplicate_terminal_lock",
        "d5_resource_assignment_mismatch",
        "terminal_friend_conflict",
        "terminal_persistent_disagreement",
    }
)


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
    review_label: str = "inconclusive"
    review_label_detail: str = "unclassified"
    review_label_source: str = "derived"
    review_pre_window_s: float = DEFAULT_REVIEW_PRE_WINDOW_S
    review_post_window_s: float = DEFAULT_REVIEW_POST_WINDOW_S
    review_pre_window_start_timestamp: float | None = None
    review_pre_window_end_timestamp: float | None = None
    review_post_window_start_timestamp: float | None = None
    review_post_window_end_timestamp: float | None = None
    plan_id: str | None = None
    plan_version: int | None = None
    active_plan_owner: str = "center"
    secondary_takeover: SecondaryTakeoverPlanMetadata = field(
        default_factory=lambda: build_secondary_takeover_plan_metadata(
            ActiveDegradationDecision(
                mode=DegradationMode.NONE,
                action=DegradationAction.CONTINUE_CENTER,
                reason="not_applicable",
            )
        )
    )
    track_version: int | None = None
    target_node_id: str | None = None
    coverage_cell: str | None = None
    terminal_consistent: bool = False
    secondary_single_camera_full_view_frame_rate: float | None = None
    secondary_network_joint_full_view_frame_rate: float | None = None
    secondary_network_mean_coverage_ratio: float | None = None
    cue_freshness_s: float | None = None
    gimbal_pointing_ok: bool | None = None
    secondary_coverage_ratio: float | None = None
    cross_view_support_count: int = 0
    cross_view_association_count: int | None = None
    cross_view_conversion_gap: float | str | None = None
    secondary_detect_to_registration_gap: float | str | None = None
    secondary_detect_to_cross_view_reject_reasons: tuple[str, ...] = ()
    secondary_detect_available_but_not_registered: bool = False
    secondary_detect_to_cross_view_diagnostic: str | None = None
    secondary_network_coverage_available: bool = False
    secondary_network_full_view_gap: float | None = None
    secondary_takeover_candidate: bool = False
    secondary_takeover_success: bool = False
    secondary_takeover_necessity_label: str | None = None
    secondary_plan_activation_delay_s: float | None = None
    secondary_plan_pending_duration_s: float | None = None
    secondary_diagnostic_node_id: str | None = None
    secondary_diagnostic_available: bool | None = None
    secondary_diagnostic_heartbeat_age_s: float | None = None
    secondary_diagnostic_heartbeat_stale: bool | None = None
    secondary_diagnostic_link_stale: bool | None = None
    secondary_diagnostic_link_fresh: bool | None = None
    secondary_diagnostic_video_cue_freshness_s: float | None = None
    secondary_diagnostic_cue_freshness_s: float | None = None
    secondary_diagnostic_cue_stale: bool | None = None
    secondary_diagnostic_gimbal_pointing_ok: bool | None = None
    secondary_diagnostic_coverage_ratio: float | None = None
    secondary_diagnostic_coverage_matches_requested_cell: bool | None = None
    secondary_diagnostic_visible: bool | None = None
    secondary_diagnostic_registered: bool | None = None
    secondary_diagnostic_takeover_capable: bool | None = None
    secondary_diagnostic_capability_score: float | None = None
    secondary_diagnostic_capability_reasons: tuple[str, ...] = ()
    risk_factors: tuple[str, ...] = ()
    hard_risk_factors: tuple[str, ...] = ()
    soft_risk_factors: tuple[str, ...] = ()
    active_degradation_false_trigger_candidate: bool = False
    active_degradation_false_trigger_reason: str | None = None
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
            "active_degradation_review_label": self.review_label,
            "review_label_detail": self.review_label_detail,
            "review_label_source": self.review_label_source,
            "review_pre_window_s": self.review_pre_window_s,
            "review_post_window_s": self.review_post_window_s,
            "review_pre_window_start_timestamp": self.review_pre_window_start_timestamp,
            "review_pre_window_end_timestamp": self.review_pre_window_end_timestamp,
            "review_post_window_start_timestamp": self.review_post_window_start_timestamp,
            "review_post_window_end_timestamp": self.review_post_window_end_timestamp,
            "active_degradation_review_window": {
                "pre_window_s": self.review_pre_window_s,
                "post_window_s": self.review_post_window_s,
                "pre_window_start_timestamp": self.review_pre_window_start_timestamp,
                "pre_window_end_timestamp": self.review_pre_window_end_timestamp,
                "post_window_start_timestamp": self.review_post_window_start_timestamp,
                "post_window_end_timestamp": self.review_post_window_end_timestamp,
            },
            "resource_id": self.resource_id,
            "global_track_id": self.global_track_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "active_plan_owner": self.active_plan_owner,
            "secondary_takeover_state": self.secondary_takeover.state.value,
            "secondary_takeover": self.secondary_takeover.to_dict(),
            "secondary_plan_source_node_id": self.secondary_takeover.secondary_plan_source_node_id,
            "secondary_plan_id": self.secondary_takeover.secondary_plan_id,
            "secondary_plan_version": self.secondary_takeover.secondary_plan_version,
            "secondary_plan_lease_epoch": (
                self.secondary_takeover.secondary_plan_lease_epoch
            ),
            "secondary_plan_lease_expires_at_s": (
                self.secondary_takeover.secondary_plan_lease_expires_at_s
            ),
            "secondary_plan_lease_valid": (
                self.secondary_takeover.secondary_plan_lease_valid
            ),
            "secondary_plan_epoch_monotonic": (
                self.secondary_takeover.secondary_plan_epoch_monotonic
            ),
            "secondary_plan_executable": (
                self.secondary_takeover.secondary_plan_executable
            ),
            "secondary_plan_reject_reason": (
                self.secondary_takeover.secondary_plan_reject_reason
            ),
            "recovery_dual_track_audit": (
                self.secondary_takeover.recovery_dual_track_audit
            ),
            "secondary_supersedes_plan_id": self.secondary_takeover.secondary_supersedes_plan_id,
            "secondary_supersedes_plan_version": (
                self.secondary_takeover.secondary_supersedes_plan_version
            ),
            "secondary_reassignment_complete": (
                self.secondary_takeover.secondary_reassignment_complete
            ),
            "track_version": self.track_version,
            "target_node_id": self.target_node_id,
            "coverage_cell": self.coverage_cell,
            "terminal_consistent": self.terminal_consistent,
            "secondary_single_camera_full_view_frame_rate": (
                self.secondary_single_camera_full_view_frame_rate
            ),
            "secondary_network_joint_full_view_frame_rate": (
                self.secondary_network_joint_full_view_frame_rate
            ),
            "secondary_network_mean_coverage_ratio": (
                self.secondary_network_mean_coverage_ratio
            ),
            "cue_freshness_s": self.cue_freshness_s,
            "gimbal_pointing_ok": self.gimbal_pointing_ok,
            "secondary_coverage_ratio": self.secondary_coverage_ratio,
            "cross_view_support_count": self.cross_view_support_count,
            "cross_view_association_count": self.cross_view_association_count,
            "cross_view_conversion_gap": self.cross_view_conversion_gap,
            "secondary_detect_to_registration_gap": (
                self.secondary_detect_to_registration_gap
            ),
            "secondary_detect_to_cross_view_reject_reasons": list(
                self.secondary_detect_to_cross_view_reject_reasons
            ),
            "secondary_detect_available_but_not_registered": (
                self.secondary_detect_available_but_not_registered
            ),
            "secondary_detect_to_cross_view_diagnostic": (
                self.secondary_detect_to_cross_view_diagnostic
            ),
            "secondary_network_coverage_available": (
                self.secondary_network_coverage_available
            ),
            "secondary_network_full_view_gap": self.secondary_network_full_view_gap,
            "secondary_takeover_candidate": self.secondary_takeover_candidate,
            "secondary_takeover_success": self.secondary_takeover_success,
            "secondary_takeover_necessity_label": self.secondary_takeover_necessity_label,
            "secondary_plan_activation_delay_s": self.secondary_plan_activation_delay_s,
            "secondary_plan_pending_duration_s": self.secondary_plan_pending_duration_s,
            "plan_activation_delay_s": self.secondary_plan_activation_delay_s,
            "secondary_diagnostic_node_id": self.secondary_diagnostic_node_id,
            "secondary_diagnostic_available": self.secondary_diagnostic_available,
            "secondary_diagnostic_heartbeat_age_s": (
                self.secondary_diagnostic_heartbeat_age_s
            ),
            "secondary_diagnostic_heartbeat_stale": (
                self.secondary_diagnostic_heartbeat_stale
            ),
            "secondary_diagnostic_link_stale": self.secondary_diagnostic_link_stale,
            "secondary_diagnostic_link_fresh": self.secondary_diagnostic_link_fresh,
            "secondary_diagnostic_video_cue_freshness_s": (
                self.secondary_diagnostic_video_cue_freshness_s
            ),
            "secondary_diagnostic_cue_freshness_s": (
                self.secondary_diagnostic_cue_freshness_s
            ),
            "secondary_diagnostic_cue_stale": self.secondary_diagnostic_cue_stale,
            "secondary_diagnostic_gimbal_pointing_ok": (
                self.secondary_diagnostic_gimbal_pointing_ok
            ),
            "secondary_diagnostic_coverage_ratio": (
                self.secondary_diagnostic_coverage_ratio
            ),
            "secondary_diagnostic_coverage_matches_requested_cell": (
                self.secondary_diagnostic_coverage_matches_requested_cell
            ),
            "risk_factors": list(self.risk_factors),
            "hard_risk_factors": list(self.hard_risk_factors),
            "soft_risk_factors": list(self.soft_risk_factors),
            "active_degradation_hard_risk_factors": list(self.hard_risk_factors),
            "active_degradation_soft_risk_factors": list(self.soft_risk_factors),
            "active_degradation_false_trigger_candidate": (
                self.active_degradation_false_trigger_candidate
            ),
            "active_degradation_false_trigger_reason": (
                self.active_degradation_false_trigger_reason
            ),
            "secondary_diagnostic_visible": self.secondary_diagnostic_visible,
            "secondary_diagnostic_registered": self.secondary_diagnostic_registered,
            "secondary_diagnostic_takeover_capable": (
                self.secondary_diagnostic_takeover_capable
            ),
            "secondary_diagnostic_capability_score": (
                self.secondary_diagnostic_capability_score
            ),
            "secondary_diagnostic_capability_reasons": list(
                self.secondary_diagnostic_capability_reasons
            ),
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
        d5_evidence: Any | None = None,
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
        active_plan_owner: str = "center",
        secondary_plan_id: str | None = None,
        secondary_plan_version: int | None = None,
        secondary_plan_active: bool = False,
        secondary_plan_source_node_id: str | None = None,
        secondary_plan_lease_epoch: int | None = None,
        secondary_plan_lease_expires_at_s: float | None = None,
        trigger_timestamp: float | None = None,
        review_label: str = "unknown",
        review_pre_window_s: float | None = None,
        review_post_window_s: float | None = None,
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
        resolved_secondary_nodes = tuple(
            item
            for item in (build_resource_summary(node) for node in secondary_nodes)
            if item is not None
        )
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
            d5_evidence=d5_evidence,
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
            list(resolved_secondary_nodes),
            resolved_coverage,
            communication_summaries=list(communications) if communications else None,
            current_time_s=timestamp,
            terminal_association=terminal_summary,
        )
        health = _c2_health(c2_health)
        decision = self.arbiter.evaluate(
            track_uncertainty=track_summary,
            association_risk=association_summary,
            assignment_validity=assignment_summary,
            terminal_association=terminal_summary,
            c2_health=health,
            secondary_nodes=list(resolved_secondary_nodes),
            communication_summaries=list(communications) if communications else None,
            current_time_s=timestamp,
        )
        resolved_plan_id = plan_id or _string_or_none(_get(plan, "plan_id"))
        resolved_plan_version = _optional_int(
            _get(plan, "version", _get(plan, "plan_version"))
        )
        if resolved_plan_version is None:
            resolved_plan_version = assignment_summary.plan_version
        secondary_takeover = build_secondary_takeover_plan_metadata(
            decision,
            current_plan_id=resolved_plan_id,
            current_plan_version=resolved_plan_version,
            current_plan_owner=active_plan_owner,
            secondary_plan_id=secondary_plan_id,
            secondary_plan_version=secondary_plan_version,
            secondary_plan_active=secondary_plan_active,
            secondary_plan_source_node_id=secondary_plan_source_node_id,
            secondary_plan_lease_epoch=(
                secondary_plan_lease_epoch
                if secondary_plan_lease_epoch is not None
                else _selected_secondary_lease_epoch(lifecycle, decision.target_node_id)
            ),
            secondary_plan_lease_expires_at_s=secondary_plan_lease_expires_at_s,
            decision_timestamp=timestamp,
        )
        resolved_trigger_timestamp = float(
            trigger_timestamp if trigger_timestamp is not None else timestamp
        )
        resolved_decision_timestamp = float(timestamp)
        review = _review_label_metadata(decision, explicit=review_label)
        review_window = _review_window_metadata(
            trigger_timestamp=resolved_trigger_timestamp,
            decision_timestamp=resolved_decision_timestamp,
            pre_window_s=review_pre_window_s,
            post_window_s=review_post_window_s,
        )
        secondary_timing = _secondary_plan_timing_metadata(
            secondary_takeover,
            trigger_timestamp=resolved_trigger_timestamp,
            decision_timestamp=resolved_decision_timestamp,
        )
        diagnostic_lifecycle = _diagnostic_secondary_lifecycle(
            lifecycle,
            target_node_id=decision.target_node_id,
        )
        network_coverage = _secondary_network_coverage_metadata(terminal_summary)
        secondary_takeover_candidate = decision.action in {
            DegradationAction.REQUEST_SECONDARY_ASSIST,
            DegradationAction.DEGRADE_TO_SECONDARY,
        }
        risk_classification = _risk_classification_metadata(
            decision.risk_factors,
            decision=decision,
            review_label=review["label"],
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
            trigger_timestamp=resolved_trigger_timestamp,
            decision_timestamp=resolved_decision_timestamp,
            review_label=review["label"],
            review_label_detail=review["detail"],
            review_label_source=review["source"],
            review_pre_window_s=review_window["pre_window_s"],
            review_post_window_s=review_window["post_window_s"],
            review_pre_window_start_timestamp=review_window["pre_window_start_timestamp"],
            review_pre_window_end_timestamp=review_window["pre_window_end_timestamp"],
            review_post_window_start_timestamp=review_window["post_window_start_timestamp"],
            review_post_window_end_timestamp=review_window["post_window_end_timestamp"],
            plan_id=resolved_plan_id,
            plan_version=resolved_plan_version,
            active_plan_owner=secondary_takeover.active_plan_owner,
            secondary_takeover=secondary_takeover,
            track_version=track_version or _optional_int(_metadata(track).get("track_version")),
            target_node_id=decision.target_node_id,
            coverage_cell=decision.coverage_cell or resolved_coverage,
            terminal_consistent=decision.terminal_consistent,
            secondary_single_camera_full_view_frame_rate=(
                terminal_summary.secondary_single_camera_full_view_frame_rate
            ),
            secondary_network_joint_full_view_frame_rate=(
                terminal_summary.secondary_network_joint_full_view_frame_rate
            ),
            secondary_network_mean_coverage_ratio=(
                terminal_summary.secondary_network_mean_coverage_ratio
            ),
            cue_freshness_s=terminal_summary.cue_freshness_s,
            gimbal_pointing_ok=terminal_summary.gimbal_pointing_ok,
            secondary_coverage_ratio=terminal_summary.secondary_coverage_ratio,
            cross_view_support_count=terminal_summary.cross_view_support_count,
            cross_view_association_count=terminal_summary.cross_view_association_count,
            cross_view_conversion_gap=terminal_summary.cross_view_conversion_gap,
            secondary_detect_to_registration_gap=terminal_summary.cross_view_conversion_gap,
            secondary_detect_to_cross_view_reject_reasons=(
                terminal_summary.secondary_detect_to_cross_view_reject_reasons
            ),
            secondary_detect_available_but_not_registered=(
                terminal_summary.secondary_detect_available_but_not_registered
            ),
            secondary_detect_to_cross_view_diagnostic=(
                terminal_summary.secondary_detect_to_cross_view_diagnostic
            ),
            secondary_network_coverage_available=network_coverage["available"],
            secondary_network_full_view_gap=network_coverage["full_view_gap"],
            secondary_takeover_candidate=secondary_takeover_candidate,
            secondary_takeover_success=_secondary_takeover_success(
                secondary_takeover,
                terminal_summary=terminal_summary,
            ),
            secondary_takeover_necessity_label=_secondary_takeover_necessity_label(
                decision,
                review["label"],
            ),
            secondary_plan_activation_delay_s=secondary_timing[
                "secondary_plan_activation_delay_s"
            ],
            secondary_plan_pending_duration_s=secondary_timing[
                "secondary_plan_pending_duration_s"
            ],
            secondary_diagnostic_node_id=(
                diagnostic_lifecycle.node_id if diagnostic_lifecycle is not None else None
            ),
            secondary_diagnostic_available=(
                diagnostic_lifecycle.secondary_available
                if diagnostic_lifecycle is not None
                else None
            ),
            secondary_diagnostic_heartbeat_age_s=(
                diagnostic_lifecycle.heartbeat_age_s
                if diagnostic_lifecycle is not None
                else None
            ),
            secondary_diagnostic_heartbeat_stale=(
                diagnostic_lifecycle.heartbeat_stale
                if diagnostic_lifecycle is not None
                else None
            ),
            secondary_diagnostic_link_stale=(
                diagnostic_lifecycle.link_stale if diagnostic_lifecycle is not None else None
            ),
            secondary_diagnostic_link_fresh=(
                diagnostic_lifecycle.link_fresh if diagnostic_lifecycle is not None else None
            ),
            secondary_diagnostic_video_cue_freshness_s=(
                diagnostic_lifecycle.video_cue_freshness_s
                if diagnostic_lifecycle is not None
                else None
            ),
            secondary_diagnostic_cue_freshness_s=(
                diagnostic_lifecycle.cue_freshness_s
                if diagnostic_lifecycle is not None
                else None
            ),
            secondary_diagnostic_cue_stale=(
                diagnostic_lifecycle.cue_stale if diagnostic_lifecycle is not None else None
            ),
            secondary_diagnostic_gimbal_pointing_ok=(
                diagnostic_lifecycle.gimbal_pointing_ok
                if diagnostic_lifecycle is not None
                else None
            ),
            secondary_diagnostic_coverage_ratio=(
                diagnostic_lifecycle.secondary_coverage_ratio
                if diagnostic_lifecycle is not None
                else None
            ),
            secondary_diagnostic_coverage_matches_requested_cell=(
                diagnostic_lifecycle.coverage_matches_requested_cell
                if diagnostic_lifecycle is not None
                else None
            ),
            risk_factors=decision.risk_factors,
            hard_risk_factors=risk_classification["hard"],
            soft_risk_factors=risk_classification["soft"],
            active_degradation_false_trigger_candidate=bool(
                risk_classification["false_trigger_candidate"]
            ),
            active_degradation_false_trigger_reason=risk_classification[
                "false_trigger_reason"
            ],
            secondary_diagnostic_visible=(
                diagnostic_lifecycle.secondary_visible
                if diagnostic_lifecycle is not None
                else None
            ),
            secondary_diagnostic_registered=(
                diagnostic_lifecycle.secondary_registered
                if diagnostic_lifecycle is not None
                else None
            ),
            secondary_diagnostic_takeover_capable=(
                diagnostic_lifecycle.secondary_takeover_capable
                if diagnostic_lifecycle is not None
                else None
            ),
            secondary_diagnostic_capability_score=(
                diagnostic_lifecycle.secondary_capability_score
                if diagnostic_lifecycle is not None
                else None
            ),
            secondary_diagnostic_capability_reasons=(
                diagnostic_lifecycle.secondary_capability_reasons
                if diagnostic_lifecycle is not None
                else ()
            ),
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


def _review_label_metadata(
    decision: ActiveDegradationDecision,
    *,
    explicit: str = "unknown",
) -> dict[str, str]:
    detail = _legacy_review_label_for_decision(decision)
    parsed = (explicit or "unknown").strip().lower()
    if parsed in ACTIVE_DEGRADATION_REVIEW_LABELS:
        return {"label": parsed, "detail": detail, "source": "explicit"}
    if parsed and parsed != "unknown":
        label = _normalise_legacy_review_label(parsed)
        return {"label": label, "detail": parsed, "source": "explicit_normalized"}

    if decision.action == DegradationAction.CONTINUE_CENTER and decision.mode == DegradationMode.NONE:
        return {"label": "unnecessary", "detail": detail, "source": "derived"}
    return {"label": "inconclusive", "detail": detail, "source": "derived"}


def _risk_classification_metadata(
    risk_factors: tuple[str, ...],
    *,
    decision: ActiveDegradationDecision,
    review_label: str,
) -> dict[str, Any]:
    hard = tuple(factor for factor in risk_factors if factor in ADAPTER_HARD_RISK_FACTORS)
    soft = tuple(factor for factor in risk_factors if factor not in ADAPTER_HARD_RISK_FACTORS)
    false_trigger_candidate = (
        decision.mode != DegradationMode.NONE and review_label == "unnecessary"
    )
    return {
        "hard": hard,
        "soft": soft,
        "false_trigger_candidate": false_trigger_candidate,
        "false_trigger_reason": decision.reason if false_trigger_candidate else None,
    }


def _selected_secondary_lease_epoch(
    lifecycle: Sequence[SecondaryNodeLifecycleSummary],
    target_node_id: str | None,
) -> int | None:
    if target_node_id is None:
        return None
    for item in lifecycle:
        if item.node_id == target_node_id:
            return item.lease_epoch
    return None


def _normalise_legacy_review_label(value: str) -> str:
    if value in {"true", "positive", "needed", "required"}:
        return "necessary"
    if value in {
        "false",
        "negative",
        "not_needed",
        "not_required",
        "continue_center",
        "observe_more_not_degradation",
    }:
        return "unnecessary"
    return "inconclusive"


def _legacy_review_label_for_decision(decision: ActiveDegradationDecision) -> str:
    if decision.mode == DegradationMode.PASSIVE_FAILOVER:
        return "passive_failover"
    if decision.reason == "terminal_transient_observe_more":
        return "observe_more_not_degradation"
    if decision.action == DegradationAction.REQUEST_CENTER_REPLAN:
        return "center_replan_candidate"
    if decision.action in {
        DegradationAction.REQUEST_SECONDARY_ASSIST,
        DegradationAction.DEGRADE_TO_SECONDARY,
    }:
        return "secondary_takeover_candidate"
    if decision.action == DegradationAction.DEGRADE_TO_DISTRIBUTED:
        return "distributed_fallback_candidate"
    if decision.action == DegradationAction.HOLD_FOR_REVIEW:
        return "human_review_required"
    return "continue_center"


def _review_window_metadata(
    *,
    trigger_timestamp: float,
    decision_timestamp: float,
    pre_window_s: float | None,
    post_window_s: float | None,
) -> dict[str, float]:
    resolved_pre = max(
        0.0,
        float(pre_window_s)
        if pre_window_s is not None
        else DEFAULT_REVIEW_PRE_WINDOW_S,
    )
    resolved_post = max(
        0.0,
        float(post_window_s)
        if post_window_s is not None
        else DEFAULT_REVIEW_POST_WINDOW_S,
    )
    return {
        "pre_window_s": resolved_pre,
        "post_window_s": resolved_post,
        "pre_window_start_timestamp": trigger_timestamp - resolved_pre,
        "pre_window_end_timestamp": trigger_timestamp,
        "post_window_start_timestamp": decision_timestamp,
        "post_window_end_timestamp": decision_timestamp + resolved_post,
    }


def _secondary_plan_timing_metadata(
    secondary_takeover: SecondaryTakeoverPlanMetadata,
    *,
    trigger_timestamp: float,
    decision_timestamp: float,
) -> dict[str, float | None]:
    elapsed = max(0.0, decision_timestamp - trigger_timestamp)
    state = secondary_takeover.state.value
    if state == "secondary_plan_active":
        return {
            "secondary_plan_activation_delay_s": elapsed,
            "secondary_plan_pending_duration_s": None,
        }
    if state == "pending_secondary_plan":
        return {
            "secondary_plan_activation_delay_s": None,
            "secondary_plan_pending_duration_s": elapsed,
        }
    return {
        "secondary_plan_activation_delay_s": None,
        "secondary_plan_pending_duration_s": None,
    }


def _diagnostic_secondary_lifecycle(
    lifecycle: Sequence[SecondaryNodeLifecycleSummary],
    *,
    target_node_id: str | None,
) -> SecondaryNodeLifecycleSummary | None:
    if not lifecycle:
        return None
    if target_node_id is not None:
        for item in lifecycle:
            if item.node_id == target_node_id:
                return item
    for item in lifecycle:
        if item.secondary_available:
            return item
    return lifecycle[0]


def _secondary_network_coverage_metadata(
    terminal_summary: TerminalAssociationSummary,
) -> dict[str, float | bool | None]:
    values = (
        terminal_summary.secondary_single_camera_full_view_frame_rate,
        terminal_summary.secondary_network_joint_full_view_frame_rate,
        terminal_summary.secondary_network_mean_coverage_ratio,
        terminal_summary.secondary_coverage_ratio,
    )
    available = any(value is not None and value > 0.0 for value in values)
    reference = terminal_summary.secondary_network_joint_full_view_frame_rate
    if reference is None:
        reference = terminal_summary.secondary_network_mean_coverage_ratio
    if reference is None:
        reference = terminal_summary.secondary_coverage_ratio
    full_view_gap = None
    if reference is not None:
        full_view_gap = max(0.0, 1.0 - min(max(float(reference), 0.0), 1.0))
    return {"available": available, "full_view_gap": full_view_gap}


def _secondary_takeover_success(
    secondary_takeover: SecondaryTakeoverPlanMetadata,
    *,
    terminal_summary: TerminalAssociationSummary,
) -> bool:
    return (
        secondary_takeover.state.value == "secondary_plan_active"
        and secondary_takeover.secondary_plan_executable
        and not terminal_summary.secondary_detect_available_but_not_registered
    )


def _secondary_takeover_necessity_label(
    decision: ActiveDegradationDecision,
    review_label: str,
) -> str:
    if decision.action in {
        DegradationAction.REQUEST_SECONDARY_ASSIST,
        DegradationAction.DEGRADE_TO_SECONDARY,
    }:
        return review_label
    if decision.action == DegradationAction.CONTINUE_CENTER and decision.mode == DegradationMode.NONE:
        return "unnecessary"
    return "inconclusive"


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
    d5_evidence: Any | None = None,
) -> TerminalAssociationSummary:
    if isinstance(terminal_association, TerminalAssociationSummary):
        if cross_view_summary is None and d5_evidence is None:
            return terminal_association
        return replace(
            terminal_association,
            **_secondary_visual_conversion_fields(
                terminal_association=terminal_association,
                cross_view_summary=cross_view_summary,
                d5_evidence=d5_evidence,
                cross_view_support_count=terminal_association.cross_view_support_count,
            ),
        )

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
    cross_view_support_count = _cross_view_support_count(cross_view_summary, d5_evidence)
    secondary_visual_fields = _secondary_visual_conversion_fields(
        terminal_association=terminal_association,
        cross_view_summary=cross_view_summary,
        d5_evidence=d5_evidence,
        cross_view_support_count=cross_view_support_count,
    )

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
        cross_view_support_count=cross_view_support_count,
        **secondary_visual_fields,
    )


def _secondary_visual_conversion_fields(
    *,
    terminal_association: Any,
    cross_view_summary: Any | None,
    d5_evidence: Any | None,
    cross_view_support_count: int,
) -> dict[str, Any]:
    sources = (d5_evidence, cross_view_summary, terminal_association)
    single_camera_rate = _optional_float(
        _first_evidence_field(sources, "secondary_single_camera_full_view_frame_rate")
    )
    network_joint_rate = _optional_float(
        _first_evidence_field(sources, "secondary_network_joint_full_view_frame_rate")
    )
    network_mean_coverage = _optional_float(
        _first_evidence_field(sources, "secondary_network_mean_coverage_ratio")
    )
    cue_freshness = _optional_float(
        _first_evidence_field_by_names(
            sources,
            "cue_freshness_s",
            "cue_freshness",
            "secondary_cue_freshness_s",
            "video_cue_freshness_s",
        )
    )
    gimbal_pointing_ok = _optional_bool(
        _first_evidence_field_by_names(
            sources,
            "gimbal_pointing_ok",
            "secondary_gimbal_pointing_ok",
        )
    )
    secondary_coverage_ratio = _optional_float(
        _first_evidence_field_by_names(
            sources,
            "secondary_coverage_ratio",
            "coverage_ratio",
        )
    )
    cross_view_count = _derived_cross_view_association_count(d5_evidence, cross_view_summary)
    conversion_gap_raw = _first_evidence_field(sources, "cross_view_conversion_gap")
    conversion_gap = _normalise_conversion_gap(conversion_gap_raw)
    reject_reasons = _unique_strings(
        _first_evidence_field(sources, "secondary_detect_to_cross_view_reject_reasons")
    )

    detect_available = _secondary_detect_available(
        sources,
        single_camera_rate=single_camera_rate,
        network_joint_rate=network_joint_rate,
        network_mean_coverage=network_mean_coverage,
        secondary_coverage_ratio=secondary_coverage_ratio,
    )
    cross_view_zero = cross_view_count == 0 or (
        cross_view_count is None and cross_view_support_count == 0
    )
    registration_break = _has_registration_breakpoint(reject_reasons) or (
        _gap_mentions_registration_breakpoint(conversion_gap_raw)
    )
    positive_gap = _positive_conversion_gap(conversion_gap_raw)
    not_registered = detect_available and (cross_view_zero or registration_break)
    diagnostic = _secondary_detect_diagnostic(
        not_registered=not_registered,
        reject_reasons=reject_reasons,
        cross_view_zero=cross_view_zero,
        registration_break=registration_break,
        positive_gap=positive_gap,
    )

    return {
        "secondary_single_camera_full_view_frame_rate": single_camera_rate,
        "secondary_network_joint_full_view_frame_rate": network_joint_rate,
        "secondary_network_mean_coverage_ratio": network_mean_coverage,
        "cue_freshness_s": cue_freshness,
        "gimbal_pointing_ok": gimbal_pointing_ok,
        "secondary_coverage_ratio": secondary_coverage_ratio,
        "cross_view_association_count": cross_view_count,
        "cross_view_conversion_gap": conversion_gap,
        "secondary_detect_to_cross_view_reject_reasons": reject_reasons,
        "secondary_detect_available_but_not_registered": not_registered,
        "secondary_detect_to_cross_view_diagnostic": diagnostic,
    }


def _secondary_detect_diagnostic(
    *,
    not_registered: bool,
    reject_reasons: tuple[str, ...],
    cross_view_zero: bool,
    registration_break: bool,
    positive_gap: bool,
) -> str | None:
    if not not_registered:
        return None
    reasons = [
        "secondary_detect_available_but_not_registered",
        *reject_reasons,
        "cross_view_association_count_zero" if cross_view_zero else "",
        "cross_view_conversion_gap" if positive_gap else "",
        "registration_or_global_binding_break" if registration_break and not reject_reasons else "",
    ]
    return ";".join(_unique_strings(item for item in reasons if item))


def _secondary_detect_available(
    sources: Sequence[Any],
    *,
    single_camera_rate: float | None,
    network_joint_rate: float | None,
    network_mean_coverage: float | None,
    secondary_coverage_ratio: float | None,
) -> bool:
    if any(
        value is not None and value > 0.0
        for value in (
            single_camera_rate,
            network_joint_rate,
            network_mean_coverage,
            secondary_coverage_ratio,
        )
    ):
        return True
    for field_name in (
        "secondary_evidence_available",
        "secondary_detect_available",
        "secondary_coverage_available",
        "secondary_network_coverage_available",
    ):
        parsed = _optional_bool(_first_evidence_field(sources, field_name))
        if parsed is not None:
            return parsed
    return False


def _cross_view_support_count(*sources: Any) -> int:
    for field_name in ("cross_view_support_count", "support_count"):
        parsed = _optional_int(_first_evidence_field(sources, field_name))
        if parsed is not None:
            return parsed

    for source in sources:
        items = _cross_view_association_items(source)
        if items is None:
            continue
        if not items:
            return 0
        return max(
            _first_int(
                _get(item, "support_count"),
                len(_unique_strings(_get(item, "supporting_resource_ids", ()))),
                0,
            )
            for item in items
        )
    return 0


def _derived_cross_view_association_count(*sources: Any) -> int | None:
    for field_name in ("cross_view_association_count", "cross_view_associations_count"):
        parsed = _optional_int(_first_evidence_field(sources, field_name))
        if parsed is not None:
            return parsed
    for source in sources:
        items = _cross_view_association_items(source)
        if items is not None:
            return len(items)
    for source in sources:
        if source is None:
            continue
        if _get(source, "support_count") is not None or _get(source, "global_track_id") is not None:
            return 1
    return None


def _cross_view_association_items(source: Any) -> tuple[Any, ...] | None:
    if source is None:
        return None
    associations = _get(source, "cross_view_associations")
    if associations is not None:
        return _tuple_values(associations)
    if isinstance(source, Mapping):
        return None
    if isinstance(source, (str, bytes)):
        return None
    if isinstance(source, Sequence):
        return tuple(source)
    return None


def _first_evidence_field(sources: Sequence[Any], field_name: str) -> Any:
    for source in sources:
        value = _evidence_field_value(source, field_name)
        if value is not None:
            return value
    return None


def _first_evidence_field_by_names(sources: Sequence[Any], *field_names: str) -> Any:
    for field_name in field_names:
        value = _first_evidence_field(sources, field_name)
        if value is not None:
            return value
    return None


def _evidence_field_value(source: Any, field_name: str) -> Any:
    if source is None:
        return None
    value = _get(source, field_name)
    if value is not None:
        return value
    metadata = _metadata(source)
    if field_name in metadata:
        return metadata[field_name]
    metrics = _get(source, "metrics")
    if metrics is not None and metrics is not source:
        value = _get(metrics, field_name)
        if value is not None:
            return value
        metric_metadata = _metadata(metrics)
        if field_name in metric_metadata:
            return metric_metadata[field_name]
    return None


def _normalise_conversion_gap(value: Any) -> float | str | None:
    if value is None:
        return None
    parsed = _optional_float(value)
    if parsed is not None:
        return parsed
    return _string_or_none(value)


def _positive_conversion_gap(value: Any) -> bool:
    parsed = _optional_float(value)
    return parsed is not None and parsed > 0.0


def _has_registration_breakpoint(reasons: Iterable[str]) -> bool:
    return any(_text_mentions_registration_breakpoint(reason) for reason in reasons)


def _gap_mentions_registration_breakpoint(value: Any) -> bool:
    if value is None:
        return False
    return _text_mentions_registration_breakpoint(str(value))


def _text_mentions_registration_breakpoint(value: str) -> bool:
    text = value.lower()
    return any(term in text for term in REGISTRATION_BREAKPOINT_TERMS)


def build_distributed_visual_evidence_summary(
    evidence: Any,
    *,
    expected_global_track_id: str | None = None,
) -> DistributedVisualEvidenceSummary:
    """Normalize D5 distributed visual evidence without importing D5 classes.

    Accepts D5 `DistributedTerminalAssociation`,
    `CrossPeerAssociationHypothesis`, equivalent dictionaries, or sequences of
    those objects. The returned summary is advisory input for D4 CBBA scoring;
    it never creates or rewrites center-owned global track IDs.
    """

    if isinstance(evidence, DistributedVisualEvidenceSummary):
        return evidence

    items = _visual_evidence_items(evidence)
    if not items:
        return DistributedVisualEvidenceSummary()

    summaries = [
        _single_visual_evidence_summary(item, expected_global_track_id=expected_global_track_id)
        for item in items
    ]
    return _merge_visual_evidence_summaries(
        summaries,
        expected_global_track_id=expected_global_track_id,
    )


def attach_distributed_visual_evidence(
    track: TrackSummary,
    evidence: Any,
) -> TrackSummary:
    """Return a TrackSummary copy with normalized D5 visual evidence attached."""

    summary = build_distributed_visual_evidence_summary(
        evidence,
        expected_global_track_id=track.track_id,
    )
    return replace(track, visual_evidence=summary)


def merge_distributed_visual_evidence_into_tracks(
    tracks: Sequence[TrackSummary],
    evidence: Any,
) -> list[TrackSummary]:
    """Attach D5 visual evidence to matching D4 tracks by upstream global ID."""

    items = _visual_evidence_items(evidence)
    by_track_id: dict[str, list[Any]] = {}
    for item in items:
        for track_id in _candidate_global_track_ids(item):
            by_track_id.setdefault(track_id, []).append(item)

    merged: list[TrackSummary] = []
    for track in tracks:
        matched = by_track_id.get(track.track_id, ())
        if matched:
            merged.append(attach_distributed_visual_evidence(track, matched))
        else:
            merged.append(track)
    return merged


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


def build_resource_summary(resource: Any) -> ResourceSummary | None:
    if resource is None:
        return None
    if isinstance(resource, ResourceSummary):
        return resource

    node_id = (
        _string_or_none(_get(resource, "node_id"))
        or _string_or_none(_get(resource, "resource_id"))
        or _string_or_none(_get(resource, "id"))
    )
    if node_id is None:
        return None

    capability = (
        _string_or_none(_get(resource, "capability_class"))
        or _string_or_none(_get(resource, "capability"))
        or "observe"
    )
    node_role = _node_role(
        _get(resource, "node_role", _get(resource, "role")),
        capability_class=capability,
    )
    return ResourceSummary(
        node_id=node_id,
        capability_class=capability,
        availability_band=_availability_band(
            _get(resource, "availability_band", _get(resource, "availability"))
        ),
        comm_band=_comm_band(_get(resource, "comm_band", _get(resource, "comm"))),
        operator_hold=bool(_get(resource, "operator_hold", False)),
        takeover_priority=_first_int(_get(resource, "takeover_priority"), 100),
        lease_epoch=_first_int(_get(resource, "lease_epoch"), 0),
        lease_expires_at_s=_optional_float(
            _get(
                resource,
                "lease_expires_at_s",
                _get(resource, "lease_expiration_s", _get(resource, "lease_expires_at")),
            )
        ),
        epoch=_first_int(_get(resource, "epoch"), 0),
        node_role=node_role,
        coordinator_only=bool(_get(resource, "coordinator_only", False)),
        coverage_cell=_string_or_none(_get(resource, "coverage_cell")),
        heartbeat_timestamp_s=_optional_float(
            _get(
                resource,
                "heartbeat_timestamp_s",
                _get(resource, "heartbeat", _get(resource, "last_heartbeat_s")),
            )
        ),
        heartbeat_stale_after_s=_first_float(_get(resource, "heartbeat_stale_after_s"), 2.0),
        cue_freshness_s=_optional_float(
            _get(
                resource,
                "cue_freshness_s",
                _get(
                    resource,
                    "cue_freshness",
                    _get(resource, "secondary_cue_freshness_s"),
                ),
            )
        ),
        gimbal_pointing_ok=_optional_bool(
            _get(resource, "gimbal_pointing_ok", _get(resource, "secondary_gimbal_pointing_ok"))
        ),
        secondary_coverage_ratio=_optional_float(
            _get(resource, "secondary_coverage_ratio", _get(resource, "coverage_ratio"))
        ),
        cross_view_support_count=_optional_int(_get(resource, "cross_view_support_count")),
    )


def _visual_evidence_items(evidence: Any) -> list[Any]:
    if evidence is None:
        return []
    if isinstance(evidence, DistributedVisualEvidenceSummary):
        return [evidence]
    if isinstance(evidence, Mapping):
        return [evidence]
    if isinstance(evidence, (str, bytes)):
        return [evidence]
    if isinstance(evidence, Sequence):
        return list(evidence)
    return [evidence]


def _single_visual_evidence_summary(
    item: Any,
    *,
    expected_global_track_id: str | None,
) -> DistributedVisualEvidenceSummary:
    metadata = _metadata(item)
    hypotheses = _tuple_values(_get(item, "hypotheses", ()))
    state = (_string_or_none(_get(item, "decision_state", _get(item, "support_state"))) or "").lower()
    recommended_action = (
        _string_or_none(_get(item, "recommended_d4_action", metadata.get("recommended_d4_action"))) or ""
    ).lower()
    reason = (
        _string_or_none(_get(item, "reason", metadata.get("hypothesis_reason", metadata.get("reason"))))
        or ""
    ).lower()

    resources = _unique_strings(
        _tuple_values(_get(item, "supporting_resource_ids", ()))
        or _tuple_values(_get(item, "visual_support_resource_ids", ()))
        or [_get(item, "resource_id")]
    )
    resource_id = _string_or_none(_get(item, "resource_id"))
    assigned_id = _string_or_none(
        _get(item, "assigned_global_track_id", metadata.get("assigned_global_track_id"))
    )
    assigned_ids = _unique_strings(
        _tuple_values(_get(item, "assigned_global_track_ids", metadata.get("assigned_global_track_ids", ())))
    )
    if assigned_id and assigned_id not in assigned_ids:
        assigned_ids = (*assigned_ids, assigned_id)
    stale_ids = _unique_strings(
        _tuple_values(
            _get(
                item,
                "stale_assigned_global_track_ids",
                metadata.get("stale_assigned_global_track_ids", ()),
            )
        )
    )

    duplicate_resources = _unique_strings(
        _tuple_values(
            _get(
                item,
                "duplicate_lock_resource_ids",
                metadata.get("duplicate_lock_resource_ids", ()),
            )
        )
    )
    duplicate_risk = bool(
        _get(item, "duplicate_terminal_lock_risk", False)
        or _get(item, "duplicate_lock_risk", False)
        or bool(duplicate_resources)
    )
    friend_state = (_string_or_none(_get(item, "friend_conflict_state")) or "none").lower()
    friend_conflict = bool(_get(item, "friend_conflict", False)) or friend_state in FRIEND_CONFLICT_STATES
    global_conflict = bool(_get(item, "global_track_id_conflict", False)) or len(assigned_ids) > 1
    local_conflict = bool(_get(item, "local_id_conflict", False))

    confidence = _first_float(
        _get(item, "association_confidence"),
        _get(item, "confidence"),
        metadata.get("association_confidence"),
        0.0,
    )
    ambiguity = _first_float(
        _get(item, "ambiguity_score"),
        metadata.get("ambiguity_score"),
        0.0,
    )
    support_count = _first_int(
        _get(item, "support_count"),
        metadata.get("support_count"),
        len(resources),
    )
    hypothesis_count = max(
        _first_int(_get(item, "hypothesis_count"), metadata.get("hypothesis_count"), 0),
        len(hypotheses),
        1,
    )

    missing_global_id = not bool(assigned_id)
    if expected_global_track_id is not None and assigned_id is None:
        missing_global_id = True
    stale_global_id = bool(stale_ids) or "stale_assigned_global_track_id" in reason
    if expected_global_track_id is not None and assigned_id not in {None, expected_global_track_id}:
        global_conflict = True

    hold_state = state == "hold" or recommended_action in {"arbitrate", "report_conflict"}
    ambiguous_state = state == "ambiguous" or global_conflict or local_conflict
    hypothesis_only = state == "hypothesis_only" or (
        not assigned_id and "hypothesis" in reason
    )
    hold_resources = resources if hold_state else ()
    ambiguous_resources = resources if ambiguous_state else ()

    risk_reasons = _unique_strings(
        item
        for item in (
            reason,
            friend_state if friend_conflict else "",
            "duplicate_terminal_lock_risk" if duplicate_risk else "",
            "stale_assigned_global_track_id" if stale_global_id else "",
            "missing_global_track_id" if missing_global_id else "",
            "global_track_id_conflict" if global_conflict else "",
            "local_track_id_conflict" if local_conflict else "",
        )
        if item
    )
    nested = [
        _single_visual_evidence_summary(hypothesis, expected_global_track_id=expected_global_track_id)
        for hypothesis in hypotheses
    ]
    base = DistributedVisualEvidenceSummary(
        visual_support_resource_ids=resources,
        hold_resource_ids=hold_resources,
        ambiguous_resource_ids=ambiguous_resources,
        duplicate_lock_resource_ids=duplicate_resources,
        assigned_global_track_id=assigned_id,
        terminal_confidence=confidence,
        terminal_ambiguity=ambiguity,
        hypothesis_count=0 if hypotheses else hypothesis_count,
        support_count=max(support_count, len(resources)),
        decision_states=_unique_strings([state] if state else ()),
        risk_reasons=risk_reasons,
        hypothesis_only=hypothesis_only,
        stale_global_track_id=stale_global_id,
        missing_global_track_id=missing_global_id,
        duplicate_terminal_lock_risk=duplicate_risk,
        friend_conflict=friend_conflict,
        global_track_id_conflict=global_conflict,
        local_id_conflict=local_conflict,
    )
    if nested:
        return _merge_visual_evidence_summaries(
            [base, *nested],
            expected_global_track_id=expected_global_track_id,
        )
    return base


def _merge_visual_evidence_summaries(
    summaries: Sequence[DistributedVisualEvidenceSummary],
    *,
    expected_global_track_id: str | None,
) -> DistributedVisualEvidenceSummary:
    usable = [summary for summary in summaries if summary.has_evidence]
    if not usable:
        return DistributedVisualEvidenceSummary()

    assigned_ids = _unique_strings(summary.assigned_global_track_id for summary in usable)
    assigned_id = assigned_ids[0] if len(assigned_ids) == 1 else None
    global_conflict = len(assigned_ids) > 1 or any(summary.global_track_id_conflict for summary in usable)
    if expected_global_track_id is not None and assigned_id not in {None, expected_global_track_id}:
        global_conflict = True

    support_ids = _unique_strings(
        resource
        for summary in usable
        for resource in summary.visual_support_resource_ids
    )
    hold_ids = _unique_strings(resource for summary in usable for resource in summary.hold_resource_ids)
    ambiguous_ids = _unique_strings(
        resource for summary in usable for resource in summary.ambiguous_resource_ids
    )
    duplicate_ids = _unique_strings(
        resource for summary in usable for resource in summary.duplicate_lock_resource_ids
    )
    decision_states = _unique_strings(state for summary in usable for state in summary.decision_states)
    risk_reasons = _unique_strings(reason for summary in usable for reason in summary.risk_reasons)
    stale_global_id = any(summary.stale_global_track_id for summary in usable)
    missing_global_id = any(summary.missing_global_track_id for summary in usable)
    if expected_global_track_id is not None and not assigned_ids:
        missing_global_id = True
        risk_reasons = _unique_strings((*risk_reasons, "missing_global_track_id"))
    if global_conflict:
        risk_reasons = _unique_strings((*risk_reasons, "global_track_id_conflict"))

    return DistributedVisualEvidenceSummary(
        visual_support_resource_ids=support_ids,
        hold_resource_ids=hold_ids,
        ambiguous_resource_ids=ambiguous_ids,
        duplicate_lock_resource_ids=duplicate_ids,
        assigned_global_track_id=assigned_id,
        terminal_confidence=max(summary.terminal_confidence for summary in usable),
        terminal_ambiguity=max(summary.terminal_ambiguity for summary in usable),
        hypothesis_count=sum(summary.hypothesis_count for summary in usable),
        support_count=max([len(support_ids), *(summary.support_count for summary in usable)]),
        decision_states=decision_states,
        risk_reasons=risk_reasons,
        hypothesis_only=any(summary.hypothesis_only for summary in usable),
        stale_global_track_id=stale_global_id,
        missing_global_track_id=missing_global_id,
        duplicate_terminal_lock_risk=any(summary.duplicate_terminal_lock_risk for summary in usable),
        friend_conflict=any(summary.friend_conflict for summary in usable),
        global_track_id_conflict=global_conflict,
        local_id_conflict=any(summary.local_id_conflict for summary in usable),
    )


def _candidate_global_track_ids(item: Any) -> tuple[str, ...]:
    metadata = _metadata(item)
    assigned = _string_or_none(_get(item, "assigned_global_track_id"))
    assigned_ids = _unique_strings(
        _tuple_values(_get(item, "assigned_global_track_ids", metadata.get("assigned_global_track_ids", ())))
    )
    if assigned and assigned not in assigned_ids:
        assigned_ids = (*assigned_ids, assigned)
    if assigned_ids:
        return assigned_ids
    return _unique_strings(
        (
            _get(item, "global_track_id"),
            _get(item, "track_id"),
            metadata.get("global_track_id"),
            metadata.get("truth_global_track_id"),
        )
    )


def _tuple_values(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Mapping):
        return tuple(value.values())
    if isinstance(value, Sequence):
        return tuple(value)
    if isinstance(value, Iterable):
        return tuple(value)
    return (value,)


def _unique_strings(values: Any) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in _tuple_values(values) if value is not None and str(value)))


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


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1", "available"}:
        return True
    if text in {"false", "no", "n", "0", "unavailable", "none"}:
        return False
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


def _availability_band(value: Any) -> AvailabilityBand:
    if isinstance(value, AvailabilityBand):
        return value
    raw = (_string_or_none(value) or "medium").lower()
    aliases = {
        "available": AvailabilityBand.HIGH,
        "healthy": AvailabilityBand.HIGH,
        "true": AvailabilityBand.HIGH,
        "offline": AvailabilityBand.NONE,
        "unavailable": AvailabilityBand.NONE,
        "false": AvailabilityBand.NONE,
    }
    if raw in {item.value for item in AvailabilityBand}:
        return AvailabilityBand(raw)
    return aliases.get(raw, AvailabilityBand.MEDIUM)


def _comm_band(value: Any) -> CommBand:
    if isinstance(value, CommBand):
        return value
    raw = (_string_or_none(value) or "good").lower()
    aliases = {
        "fresh": CommBand.GOOD,
        "healthy": CommBand.GOOD,
        "ok": CommBand.GOOD,
        "stale": CommBand.LIMITED,
        "degraded": CommBand.LIMITED,
        "lost": CommBand.POOR,
        "none": CommBand.POOR,
    }
    if raw in {item.value for item in CommBand}:
        return CommBand(raw)
    return aliases.get(raw, CommBand.GOOD)


def _node_role(value: Any, *, capability_class: str) -> NodeRole:
    if isinstance(value, NodeRole):
        return value
    raw = (_string_or_none(value) or "").lower()
    if raw.startswith("noderole."):
        raw = raw.split(".", 1)[1]
    if raw in {item.value for item in NodeRole}:
        return NodeRole(raw)

    capability = capability_class.lower()
    if capability == NodeRole.MOBILE_HIGH_RECON.value:
        return NodeRole.MOBILE_HIGH_RECON
    if capability == NodeRole.MOBILE_SECONDARY_RECON.value:
        return NodeRole.MOBILE_SECONDARY_RECON
    if capability == NodeRole.FIXED_TETHERED_SECONDARY.value:
        return NodeRole.FIXED_TETHERED_SECONDARY
    if capability in {"tethered_recon", "secondary_c2"}:
        return NodeRole.SECONDARY_RECON
    return NodeRole.INTERCEPTOR


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
