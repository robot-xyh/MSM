"""Terminal consistency summaries for D4/D6 consumers."""

from __future__ import annotations

from dataclasses import dataclass
from math import inf

from .models import CrossViewAssociation, TerminalAssociation, TerminalConsistencySummary


@dataclass(frozen=True)
class TerminalConsistencyConfig:
    """Thresholds for deriving advisory consistency state."""

    stable_confidence: float = 0.6
    stable_ambiguity: float = 0.5
    stable_lock_age_s: float = 1.0
    stable_candidate_margin: float = 3.0
    stable_locked_frames: int = 1
    ambiguous_frames_for_secondary: int = 5
    hold_frames_for_conflict_report: int = 2
    reacquire_frames_for_arbitration: int = 5
    conflict_frames_for_arbitration: int = 3


@dataclass
class _TrackState:
    previous_decision_state: str | None = None
    lock_started_at: float | None = None
    last_locked_timestamp: float | None = None
    consecutive_locked_frames: int = 0
    consecutive_ambiguous_frames: int = 0
    consecutive_hold_frames: int = 0
    consecutive_reacquire_frames: int = 0
    consecutive_assignment_conflict_frames: int = 0


class TerminalConsistencyTracker:
    """Convert terminal association streams into consistency summaries.

    The tracker is intentionally passive. It retains per-resource/per-global-ID
    state for event summaries but never rewrites assignments or global IDs.
    """

    def __init__(self, config: TerminalConsistencyConfig | None = None) -> None:
        self.config = config or TerminalConsistencyConfig()
        self._states: dict[tuple[str, str], _TrackState] = {}

    def update(
        self,
        *,
        resource_id: str,
        timestamp: float,
        association: TerminalAssociation,
        cross_view_association: CrossViewAssociation | None = None,
        competing_global_track_id: str | None = None,
        local_best_conflicts_with_assignment: bool = False,
        metadata: dict | None = None,
    ) -> TerminalConsistencySummary:
        """Return a D4/D6 summary for one terminal association sample."""

        key = (
            resource_id,
            association.assigned_global_track_id,
        )
        state = self._states.setdefault(key, _TrackState())
        previous = state.previous_decision_state
        decision = association.decision_state
        timestamp = float(timestamp)

        if decision == "locked":
            if previous != "locked" or state.lock_started_at is None:
                state.lock_started_at = timestamp
            state.last_locked_timestamp = timestamp
            state.consecutive_locked_frames += 1
            state.consecutive_ambiguous_frames = 0
            state.consecutive_hold_frames = 0
            state.consecutive_reacquire_frames = 0
        elif decision == "ambiguous":
            state.consecutive_locked_frames = 0
            state.consecutive_ambiguous_frames += 1
            state.consecutive_hold_frames = 0
            state.consecutive_reacquire_frames = 0
        elif decision == "hold":
            state.consecutive_locked_frames = 0
            state.consecutive_ambiguous_frames = 0
            state.consecutive_hold_frames += 1
            state.consecutive_reacquire_frames = 0
        elif decision == "reacquire":
            state.consecutive_locked_frames = 0
            state.consecutive_ambiguous_frames = 0
            state.consecutive_hold_frames = 0
            state.consecutive_reacquire_frames += 1
        else:
            state.consecutive_locked_frames = 0
            state.consecutive_ambiguous_frames = 0
            state.consecutive_hold_frames = 0
            state.consecutive_reacquire_frames = 0

        if local_best_conflicts_with_assignment:
            state.consecutive_assignment_conflict_frames += 1
        else:
            state.consecutive_assignment_conflict_frames = 0

        lost_lock_event = previous == "locked" and decision in {"ambiguous", "hold", "reacquire"}
        lock_reacquired_event = previous in {"ambiguous", "hold", "reacquire"} and decision == "locked"
        terminal_lock_age = (
            max(0.0, timestamp - state.lock_started_at)
            if decision == "locked" and state.lock_started_at is not None
            else 0.0
        )

        duplicate_risk = bool(
            cross_view_association is not None
            and cross_view_association.duplicate_terminal_lock_risk
        )
        candidate_margin = candidate_cost_margin(association)
        consistency_state, recommended_action, reason = self._classify(
            association=association,
            terminal_lock_age_s=terminal_lock_age,
            candidate_cost_margin=candidate_margin,
            local_best_conflicts_with_assignment=local_best_conflicts_with_assignment,
            consecutive_assignment_conflict_frames=state.consecutive_assignment_conflict_frames,
            duplicate_terminal_lock_risk=duplicate_risk,
            consecutive_locked_frames=state.consecutive_locked_frames,
            consecutive_ambiguous_frames=state.consecutive_ambiguous_frames,
            consecutive_hold_frames=state.consecutive_hold_frames,
            consecutive_reacquire_frames=state.consecutive_reacquire_frames,
        )
        lifecycle = _lifecycle_state(decision, lost_lock_event, lock_reacquired_event)
        event_summary = _event_summary(
            lost_lock_event=lost_lock_event,
            lock_reacquired_event=lock_reacquired_event,
            previous_decision_state=previous,
            decision_state=decision,
            reason=association.reason,
        )

        state.previous_decision_state = decision

        summary_metadata = dict(association.metadata)
        if metadata:
            summary_metadata.update(metadata)
        summary_metadata.update(
            {
                "consistency_window_key": f"{resource_id}:{association.assigned_global_track_id}",
                "assignment_version_resets_window": False,
                "assignment_version": association.assignment_version,
                "resource_id": resource_id,
                "assigned_global_track_id": association.assigned_global_track_id,
                "decision_state": decision,
                "duplicate_terminal_lock_risk": duplicate_risk,
                "cross_view_support_count": (
                    cross_view_association.support_count if cross_view_association is not None else 0
                ),
                "projection_valid": association.metadata.get("projection_valid"),
                "reprojection_error": association.metadata.get("reprojection_error"),
                "reprojection_error_px": association.metadata.get("reprojection_error_px"),
                "camera_pose_source": association.metadata.get("camera_pose_source"),
                "calibration_health": association.metadata.get("calibration_health"),
                "drift_warning": association.metadata.get("drift_warning"),
            }
        )

        return TerminalConsistencySummary(
            resource_id=resource_id,
            assigned_global_track_id=association.assigned_global_track_id,
            assignment_version=association.assignment_version,
            timestamp=timestamp,
            decision_state=decision,
            consistency_state=consistency_state,
            association_confidence=association.association_confidence,
            ambiguity_score=association.ambiguity_score,
            friend_conflict_state=association.friend_conflict_state,
            candidate_cost_margin=candidate_margin,
            recon_cue_used=association.recon_cue_used,
            terminal_lock_age_s=terminal_lock_age,
            consecutive_locked_frames=state.consecutive_locked_frames,
            consecutive_ambiguous_frames=state.consecutive_ambiguous_frames,
            consecutive_hold_frames=state.consecutive_hold_frames,
            consecutive_reacquire_frames=state.consecutive_reacquire_frames,
            local_track_id=association.local_track_id,
            previous_decision_state=previous,
            lock_lifecycle_state=lifecycle,
            lost_lock_event=lost_lock_event,
            lock_reacquired_event=lock_reacquired_event,
            event_summary=event_summary,
            competing_global_track_id=competing_global_track_id,
            local_best_conflicts_with_assignment=local_best_conflicts_with_assignment,
            duplicate_terminal_lock_risk=duplicate_risk,
            duplicate_lock_resource_ids=(
                cross_view_association.duplicate_lock_resource_ids
                if cross_view_association is not None
                else ()
            ),
            duplicate_local_track_ids=(
                cross_view_association.duplicate_local_track_ids
                if cross_view_association is not None
                else ()
            ),
            cross_view_support_count=(
                cross_view_association.support_count if cross_view_association is not None else 0
            ),
            cross_view_supporting_resource_ids=(
                cross_view_association.supporting_resource_ids
                if cross_view_association is not None
                else ()
            ),
            cross_view_decision_states=(
                cross_view_association.decision_states
                if cross_view_association is not None
                else ()
            ),
            recommended_d4_action=recommended_action,
            reason=reason,
            metadata=summary_metadata,
        )

    def clear(self) -> None:
        """Drop all retained temporal state."""

        self._states.clear()

    def _classify(
        self,
        *,
        association: TerminalAssociation,
        terminal_lock_age_s: float,
        candidate_cost_margin: float,
        local_best_conflicts_with_assignment: bool,
        consecutive_assignment_conflict_frames: int,
        duplicate_terminal_lock_risk: bool,
        consecutive_locked_frames: int,
        consecutive_ambiguous_frames: int,
        consecutive_hold_frames: int,
        consecutive_reacquire_frames: int,
    ) -> tuple[str, str, str]:
        cfg = self.config

        if duplicate_terminal_lock_risk:
            return "conflict", "arbitrate", "duplicate_terminal_lock_risk"

        if (
            local_best_conflicts_with_assignment
            and consecutive_assignment_conflict_frames >= cfg.conflict_frames_for_arbitration
        ):
            return "inconsistent", "arbitrate", "local_best_conflicts_with_assignment"

        if association.decision_state == "hold":
            if (
                association.friend_conflict_state == "verified_friend_overlap"
                or "version" in association.reason
                or "authorized" in association.reason
            ):
                return "conflict", "report_conflict", association.reason
            if consecutive_hold_frames >= cfg.hold_frames_for_conflict_report:
                return "conflict", "report_conflict", association.reason
            return "unknown", "observe", association.reason

        if association.decision_state == "reacquire":
            if consecutive_reacquire_frames >= cfg.reacquire_frames_for_arbitration:
                return "unknown", "arbitrate", association.reason
            return "unknown", "observe", association.reason

        if association.decision_state == "ambiguous":
            if consecutive_ambiguous_frames >= cfg.ambiguous_frames_for_secondary:
                return "unknown", "request_secondary_cue", association.reason
            return "unknown", "observe", association.reason

        if association.decision_state == "locked":
            stable_lock = (
                association.association_confidence >= cfg.stable_confidence
                and association.ambiguity_score <= cfg.stable_ambiguity
            )
            stable_age_or_margin = (
                terminal_lock_age_s >= cfg.stable_lock_age_s
                or candidate_cost_margin == inf
                or candidate_cost_margin >= cfg.stable_candidate_margin
            )
            stable_window = consecutive_locked_frames >= cfg.stable_locked_frames
            if association.recon_cue_used and not stable_lock:
                return "unknown", "request_secondary_cue", "locked_depends_on_recon_cue"
            if stable_lock and stable_window and stable_age_or_margin:
                return "consistent", "observe", association.reason
            return "unknown", "observe", association.reason

        return "unknown", "observe", association.reason


def summarize_terminal_consistency(
    *,
    resource_id: str,
    timestamp: float,
    association: TerminalAssociation,
    cross_view_association: CrossViewAssociation | None = None,
    competing_global_track_id: str | None = None,
    local_best_conflicts_with_assignment: bool = False,
    metadata: dict | None = None,
    config: TerminalConsistencyConfig | None = None,
) -> TerminalConsistencySummary:
    """Stateless convenience wrapper for one-sample summaries."""

    tracker = TerminalConsistencyTracker(config=config)
    return tracker.update(
        resource_id=resource_id,
        timestamp=timestamp,
        association=association,
        cross_view_association=cross_view_association,
        competing_global_track_id=competing_global_track_id,
        local_best_conflicts_with_assignment=local_best_conflicts_with_assignment,
        metadata=metadata,
    )


def candidate_cost_margin(association: TerminalAssociation) -> float:
    """Return second-best minus best candidate cost for a decision."""

    if len(association.candidate_costs) < 2:
        return inf
    ordered = sorted(float(cost) for _, cost in association.candidate_costs)
    return ordered[1] - ordered[0]


def _lifecycle_state(
    decision_state: str,
    lost_lock_event: bool,
    lock_reacquired_event: bool,
) -> str:
    if lost_lock_event:
        return "lost"
    if lock_reacquired_event:
        return "reacquired"
    if decision_state == "locked":
        return "tracking"
    if decision_state == "ambiguous":
        return "ambiguous"
    if decision_state == "hold":
        return "holding"
    if decision_state == "reacquire":
        return "lost"
    return "unknown"


def _event_summary(
    *,
    lost_lock_event: bool,
    lock_reacquired_event: bool,
    previous_decision_state: str | None,
    decision_state: str,
    reason: str,
) -> str:
    if lost_lock_event:
        return f"lost_lock:{previous_decision_state}->{decision_state}:{reason}"
    if lock_reacquired_event:
        return f"lock_reacquired:{previous_decision_state}->{decision_state}:{reason}"
    return f"state:{decision_state}:{reason}"
