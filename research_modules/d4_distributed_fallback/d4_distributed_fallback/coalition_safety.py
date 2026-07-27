"""Fail-closed safety checks for centralized multi-resource coalitions."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence

from .models import to_jsonable
from .secondary_readiness import (
    SecondaryReadinessEvidence,
    assess_secondary_readiness,
)


class CoalitionSafetyAction(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    CONTINUE_CENTER = "continue_center"
    REQUEST_CENTER_REPLAN = "request_center_replan"
    HOLD_OR_REVOKE = "hold_or_revoke"
    ALLOW_ATOMIC_FALLBACK = "allow_atomic_fallback"


COALITION_COMMIT_STATES = frozenset(
    {
        "proposed",
        "collecting_acks",
        "committed",
        "executing",
        "reconfiguring",
        "aborted",
    }
)
_SECONDARY_COORDINATOR_ROLES = frozenset(
    {
        "ground_backup",
        "fixed_tethered_secondary",
        "tethered_recon",
        "secondary_c2",
        "secondary_recon",
        "mobile_high_recon",
        "mobile_secondary_recon",
    }
)


@dataclass(frozen=True)
class CoalitionMemberAck:
    """Versioned execution acknowledgement from one required coalition member."""

    resource_id: str
    global_track_id: str
    coalition_id: str
    coalition_version: int
    plan_id: str
    plan_version: int
    epoch: int
    can_execute: bool
    evidence_timestamp: float
    valid_until: float
    reason: str = "acknowledged"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("resource_id", "global_track_id", "coalition_id", "plan_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        for name in ("coalition_version", "plan_version", "epoch"):
            object.__setattr__(
                self,
                name,
                _strict_nonnegative_int(getattr(self, name), name),
            )
        if not isinstance(self.can_execute, bool):
            raise TypeError("can_execute must be a bool")
        evidence_timestamp = _strict_nonnegative_float(
            self.evidence_timestamp,
            "evidence_timestamp",
        )
        valid_until = _strict_nonnegative_float(
            self.valid_until,
            "valid_until",
        )
        if valid_until < evidence_timestamp:
            raise ValueError("valid_until must not precede evidence_timestamp")
        object.__setattr__(self, "evidence_timestamp", evidence_timestamp)
        object.__setattr__(self, "valid_until", valid_until)
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CoalitionCommitState:
    """Immutable atomic-coalition lifecycle state shared with main and D6."""

    global_track_id: str
    coalition_id: str
    coalition_version: int
    plan_id: str
    plan_version: int
    epoch: int
    coordinator_id: str
    coordinator_role: str
    required_member_ids: tuple[str, ...]
    acked_member_ids: tuple[str, ...]
    state: str
    lease_expires_at: float
    proposed_at: float
    updated_at: float
    committed_at: float | None = None
    executing_at: float | None = None
    resolved_at: float | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_state = str(self.state).strip().lower()
        if normalized_state not in COALITION_COMMIT_STATES:
            allowed = ", ".join(sorted(COALITION_COMMIT_STATES))
            raise ValueError(f"coalition commit state must be one of: {allowed}")
        for name in (
            "global_track_id",
            "coalition_id",
            "plan_id",
            "coordinator_id",
            "coordinator_role",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        for name in ("coalition_version", "plan_version", "epoch"):
            object.__setattr__(
                self,
                name,
                _strict_nonnegative_int(getattr(self, name), name),
            )
        for name in ("lease_expires_at", "proposed_at", "updated_at"):
            object.__setattr__(
                self,
                name,
                _strict_nonnegative_float(getattr(self, name), name),
            )
        for name in ("committed_at", "executing_at", "resolved_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self,
                    name,
                    _strict_nonnegative_float(value, name),
                )
        required = _unique_strings(self.required_member_ids)
        acked = _unique_strings(self.acked_member_ids)
        if not required:
            raise ValueError("required_member_ids must not be empty")
        if any(member_id not in set(required) for member_id in acked):
            raise ValueError("acked_member_ids must be a subset of required_member_ids")
        object.__setattr__(self, "state", normalized_state)
        object.__setattr__(self, "required_member_ids", required)
        object.__setattr__(self, "acked_member_ids", acked)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def missing_member_ids(self) -> tuple[str, ...]:
        acked = set(self.acked_member_ids)
        return tuple(item for item in self.required_member_ids if item not in acked)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


class CoalitionCommitCoordinator:
    """Lightweight, fail-closed atomic commit coordinator for one D4 process."""

    def __init__(self) -> None:
        self._states_by_track: dict[str, CoalitionCommitState] = {}

    def propose(
        self,
        *,
        global_track_id: str,
        coalition_id: str,
        coalition_version: int,
        plan_id: str,
        plan_version: int,
        epoch: int,
        coordinator_id: str,
        coordinator_role: str,
        required_member_ids: Sequence[str],
        lease_expires_at: float,
        timestamp: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> CoalitionCommitState:
        proposal_metadata = dict(metadata or {})
        proposal = CoalitionCommitState(
            global_track_id=global_track_id,
            coalition_id=coalition_id,
            coalition_version=int(coalition_version),
            plan_id=plan_id,
            plan_version=int(plan_version),
            epoch=int(epoch),
            coordinator_id=coordinator_id,
            coordinator_role=str(coordinator_role).strip().lower(),
            required_member_ids=tuple(required_member_ids),
            acked_member_ids=(),
            state="proposed",
            lease_expires_at=float(lease_expires_at),
            proposed_at=float(timestamp),
            updated_at=float(timestamp),
            reason="coalition_proposed",
            metadata=proposal_metadata,
        )
        if proposal.lease_expires_at <= float(timestamp):
            return replace(
                proposal,
                state="aborted",
                resolved_at=float(timestamp),
                reason="coalition_lease_expired",
            )
        if _fallback_mode(proposal.coordinator_role) == "secondary":
            readiness_value = proposal_metadata.get("secondary_readiness_evidence")
            try:
                readiness_evidence = SecondaryReadinessEvidence.from_value(readiness_value)
                readiness = assess_secondary_readiness(
                    readiness_evidence,
                    expected_current_time_s=float(timestamp),
                )
            except (TypeError, ValueError):
                readiness_evidence = None
                readiness = None
            reject_reason = None
            if readiness is None:
                reject_reason = "secondary_readiness_evidence_missing"
            elif readiness_evidence.node_id != proposal.coordinator_id:
                reject_reason = "secondary_readiness_node_mismatch"
            elif not readiness.ready:
                reject_reason = f"secondary_readiness_{readiness.primary_reject_reason}"
            elif (
                readiness_evidence.lease_expires_at_s is None
                or proposal.lease_expires_at > readiness_evidence.lease_expires_at_s
            ):
                reject_reason = "secondary_readiness_lease_scope_exceeded"
            if reject_reason is not None:
                return replace(
                    proposal,
                    state="aborted",
                    resolved_at=float(timestamp),
                    reason=reject_reason,
                    metadata={
                        **proposal.metadata,
                        "secondary_readiness_reject_reasons": (
                            [] if readiness is None else list(readiness.reject_reasons)
                        ),
                    },
                )
            proposal = replace(
                proposal,
                metadata={
                    **proposal.metadata,
                    "takeover_ready": True,
                    "secondary_readiness_class": "takeover_ready",
                    "secondary_readiness_assessment": readiness.to_dict(),
                },
            )

        current = self._states_by_track.get(proposal.global_track_id)
        if current is not None:
            stale_reason = _proposal_stale_reason(current, proposal)
            if stale_reason:
                return replace(
                    proposal,
                    state="aborted",
                    resolved_at=float(timestamp),
                    reason=stale_reason,
                    metadata={
                        **proposal.metadata,
                        "current_commit_digest": _commit_digest(current),
                    },
                )
            same_generation = (
                current.epoch,
                current.plan_version,
                current.coalition_version,
            ) == (
                proposal.epoch,
                proposal.plan_version,
                proposal.coalition_version,
            )
            if same_generation:
                if _commit_digest(current) == _commit_digest(proposal):
                    return current
                return replace(
                    proposal,
                    state="aborted",
                    resolved_at=float(timestamp),
                    reason="coalition_digest_conflict",
                    metadata={
                        **proposal.metadata,
                        "current_commit_digest": _commit_digest(current),
                    },
                )
        self._states_by_track[proposal.global_track_id] = proposal
        return proposal

    def record_ack(
        self,
        state: CoalitionCommitState,
        ack: CoalitionMemberAck,
        *,
        timestamp: float,
    ) -> CoalitionCommitState:
        current = self._current_or_state(state)
        current = self.evaluate(current, timestamp=timestamp)
        if current.state in {"aborted", "reconfiguring"}:
            return current
        rejection = _ack_rejection_reason(current, ack, timestamp=float(timestamp))
        if rejection:
            # A rejected packet cannot authorize execution, but it must not let one
            # spoofed or reordered ACK permanently poison an otherwise valid lease.
            return self._remember(
                replace(
                    current,
                    updated_at=float(timestamp),
                    reason=rejection,
                    metadata=_increment_metadata(
                        current.metadata,
                        "rejected_ack_count",
                        last_rejected_ack_resource_id=ack.resource_id,
                        last_rejected_ack_reason=rejection,
                    ),
                )
            )
        if not ack.can_execute:
            return self._fail(
                current,
                timestamp=float(timestamp),
                reason="required_member_cannot_execute",
            )
        if ack.resource_id in set(current.acked_member_ids):
            return self._remember(
                replace(
                    current,
                    updated_at=float(timestamp),
                    reason="duplicate_ack_ignored",
                    metadata=_increment_metadata(
                        current.metadata,
                        "duplicate_ack_count",
                        duplicate_ack_resource_id=ack.resource_id,
                    ),
                )
            )

        acked = _unique_strings((*current.acked_member_ids, ack.resource_id))
        complete = len(acked) == len(current.required_member_ids)
        updated = replace(
            current,
            acked_member_ids=acked,
            state="committed" if complete else "collecting_acks",
            updated_at=float(timestamp),
            committed_at=float(timestamp) if complete else current.committed_at,
            reason="all_required_members_acked" if complete else "collecting_member_acks",
            metadata={
                **current.metadata,
                "last_ack": ack.to_dict(),
                "missing_member_ids": [
                    item for item in current.required_member_ids if item not in set(acked)
                ],
            },
        )
        return self._remember(updated)

    def evaluate(
        self,
        state: CoalitionCommitState,
        *,
        timestamp: float,
        partitioned: bool = False,
        digest_conflict: bool = False,
        finalize: bool = False,
    ) -> CoalitionCommitState:
        current = self._current_or_state(state)
        now = float(timestamp)
        if current.state in {"aborted", "reconfiguring"}:
            return current
        if partitioned:
            return self._fail(current, timestamp=now, reason="network_partition")
        if digest_conflict:
            return self._fail(current, timestamp=now, reason="coalition_digest_conflict")
        if now >= current.lease_expires_at:
            return self._fail(current, timestamp=now, reason="coalition_lease_expired")
        if finalize and current.missing_member_ids:
            return self._fail(current, timestamp=now, reason="missing_required_acks")
        if current.state == "proposed":
            return self._remember(
                replace(
                    current,
                    state="collecting_acks",
                    updated_at=now,
                    reason="collecting_member_acks",
                    metadata={
                        **current.metadata,
                        "missing_member_ids": list(current.missing_member_ids),
                    },
                )
            )
        return current

    def mark_executing(
        self,
        state: CoalitionCommitState,
        *,
        timestamp: float,
    ) -> CoalitionCommitState:
        current = self.evaluate(state, timestamp=timestamp)
        if current.state != "committed":
            return self._fail(
                current,
                timestamp=float(timestamp),
                reason="coalition_not_committed",
            )
        return self._remember(
            replace(
                current,
                state="executing",
                executing_at=float(timestamp),
                updated_at=float(timestamp),
                reason="coalition_execution_started",
            )
        )

    def audit_recovery(
        self,
        local_state: CoalitionCommitState,
        recovered_state: CoalitionCommitState,
        *,
        timestamp: float,
    ) -> dict[str, Any]:
        same_digest = _commit_runtime_digest(local_state) == _commit_runtime_digest(
            recovered_state
        )
        recovered_newer = (
            recovered_state.epoch,
            recovered_state.plan_version,
            recovered_state.coalition_version,
        ) > (
            local_state.epoch,
            local_state.plan_version,
            local_state.coalition_version,
        )
        return {
            "schema": "d4_coalition_recovery_audit_v1",
            "timestamp": float(timestamp),
            "global_track_id": local_state.global_track_id,
            "local_digest": _commit_runtime_digest(local_state),
            "recovered_digest": _commit_runtime_digest(recovered_state),
            "digest_match": same_digest,
            "recovered_newer": recovered_newer,
            "decision": (
                "consistent_keep_current"
                if same_digest
                else "dual_track_review_required"
            ),
            "immediate_takeover_allowed": False,
        }

    def _current_or_state(self, state: CoalitionCommitState) -> CoalitionCommitState:
        current = self._states_by_track.get(state.global_track_id)
        return current if current is not None else state

    def _remember(self, state: CoalitionCommitState) -> CoalitionCommitState:
        self._states_by_track[state.global_track_id] = state
        return state

    def _fail(
        self,
        state: CoalitionCommitState,
        *,
        timestamp: float,
        reason: str,
    ) -> CoalitionCommitState:
        next_state = (
            "reconfiguring" if state.state in {"committed", "executing"} else "aborted"
        )
        return self._remember(
            replace(
                state,
                state=next_state,
                updated_at=float(timestamp),
                resolved_at=float(timestamp),
                reason=reason,
            )
        )


def build_coalition_commit_d6_metadata(
    state: CoalitionCommitState | None,
    *,
    current_time_s: float | None = None,
) -> dict[str, Any]:
    """Return flat D6 event metadata without treating missing state as success."""

    if state is None:
        return {
            "coalition_commit_available": False,
            "atomic_coalition_formed": False,
        }
    lease_valid = bool(
        current_time_s is not None
        and float(current_time_s) < state.lease_expires_at
    )
    committed = bool(
        state.state in {"committed", "executing"}
        and not state.missing_member_ids
        and lease_valid
    )
    return {
        "coalition_commit_available": True,
        "coalition_commit_state": state.state,
        "coalition_commit_reason": state.reason,
        "coalition_commit_epoch": state.epoch,
        "coalition_commit_coordinator_id": state.coordinator_id,
        "coalition_commit_coordinator_role": state.coordinator_role,
        "coalition_required_member_ids": list(state.required_member_ids),
        "coalition_acked_member_ids": list(state.acked_member_ids),
        "coalition_missing_member_ids": list(state.missing_member_ids),
        "coalition_lease_expires_at": state.lease_expires_at,
        "coalition_lease_current_time_present": current_time_s is not None,
        "coalition_lease_valid": lease_valid,
        "atomic_coalition_formed": committed,
    }


@dataclass(frozen=True)
class CoalitionSafetyEvidence:
    """Serializable D4 evidence for main, D6, and D7 coalition gates."""

    schema: str = "d4_coalition_safety_v1"
    global_track_id: str = ""
    coalition_required: bool = False
    center_available: bool = True
    fallback_supported: bool = True
    safety_action: CoalitionSafetyAction = CoalitionSafetyAction.NOT_APPLICABLE
    safety_reason: str = "independent_assignment"
    safe_to_execute: bool = True
    candidate_action: str | None = None
    gated_action: str | None = None
    plan_id: str | None = None
    plan_version: int | None = None
    expected_plan_version: int | None = None
    coalition_id: str | None = None
    coalition_version: int | None = None
    expected_coalition_version: int | None = None
    required_resource_count: int = 1
    assigned_resource_count: int = 0
    coalition_complete: bool = False
    authorized_resource_ids: tuple[str, ...] = ()
    primary_resource_ids: tuple[str, ...] = ()
    locked_resource_ids: tuple[str, ...] = ()
    primary_locked_resource_ids: tuple[str, ...] = ()
    coalition_visual_consensus: bool | None = None
    coalition_visual_primary_complete: bool | None = None
    coalition_visual_current: bool = False
    center_consensus_recovered: bool = False
    coalition_visual_conflict_state: str | None = None
    legal_multi_resource_lock: bool = False
    unauthorized_resource_ids: tuple[str, ...] = ()
    excess_resource_ids: tuple[str, ...] = ()
    stale_plan_version: bool = False
    stale_coalition_version: bool = False
    atomic_coalition_formed: bool = False
    coalition_commit_state: str | None = None
    coalition_commit_epoch: int | None = None
    coalition_commit_coordinator_id: str | None = None
    coalition_commit_coordinator_role: str | None = None
    coalition_commit_lease_expires_at: float | None = None
    conflict_reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


def build_coalition_safety_evidence(
    *,
    plan: Any | None,
    assignment: Any | None,
    terminal_association: Any | None,
    cross_view_summary: Any | None,
    global_track_id: str,
    resource_id: str,
    center_available: bool,
    current_plan_version: int | None = None,
    expected_plan_version: int | None = None,
    expected_coalition_version: int | None = None,
    coalition_commit_state: CoalitionCommitState | None = None,
    current_time_s: float | None = None,
) -> CoalitionSafetyEvidence:
    """Validate one target's coalition without importing D3 implementation types."""

    plan_assignments = tuple(
        item
        for item in _sequence(_get(plan, "assignments", ()))
        if _target_id(item) == global_track_id
    )
    relevant_assignments = _unique_objects((*plan_assignments, assignment))
    coalition = _find_coalition(
        plan,
        global_track_id=global_track_id,
        coalition_id=_string(_get(assignment, "coalition_id")),
    )
    members = tuple(_sequence(_get(coalition, "members", ())))

    required = max(
        [
            1,
            _integer(_get(coalition, "required_resource_count"), 0),
            *(
                _integer(_get(item, "required_resource_count"), 0)
                for item in relevant_assignments
            ),
        ]
    )
    coordination_mode = _enum_text(_get(coalition, "coordination_mode", "independent"))
    coalition_required = bool(
        required > 1
        or len(members) > 1
        or len(plan_assignments) > 1
        or coordination_mode not in {"", "independent"}
    )
    plan_version = _optional_integer(_get(plan, "version", _get(plan, "plan_version")))
    required_plan_version = (
        expected_plan_version
        if expected_plan_version is not None
        else current_plan_version
    )
    coalition_version = _optional_integer(_get(coalition, "version"))
    coalition_id = _string(_get(coalition, "coalition_id")) or _string(
        _get(assignment, "coalition_id")
    )

    member_ids = _unique_strings(
        _get(member, "resource_id")
        for member in members
        if bool(_get(member, "executable", True))
        and _enum_text(_get(member, "member_role", "primary")) != "observer"
    )
    assignment_ids = _unique_strings(
        _get(item, "resource_id") for item in relevant_assignments
    )
    authorized_ids = member_ids or assignment_ids
    primary_member_ids = _unique_strings(
        _get(member, "resource_id")
        for member in members
        if bool(_get(member, "executable", True))
        and _enum_text(_get(member, "member_role", "primary")) == "primary"
    ) or _unique_strings(
        _get(item, "resource_id")
        for item in relevant_assignments
        if _enum_text(_get(item, "member_role", "primary")) == "primary"
    )
    locked_ids = _locked_resource_ids(
        terminal_association,
        cross_view_summary,
        global_track_id=global_track_id,
        resource_id=resource_id,
    )
    unauthorized_ids = tuple(
        item for item in locked_ids if item not in set(authorized_ids)
    )
    excess_ids = tuple(
        item for index, item in enumerate(locked_ids) if index >= required
    )

    stale_plan = bool(
        required_plan_version is not None and plan_version != int(required_plan_version)
    )
    assignment_plan_versions = {
        value
        for value in (
            _optional_integer(_get(item, "plan_version"))
            for item in relevant_assignments
        )
        if value is not None
    }
    if plan_version is not None and any(
        value != plan_version for value in assignment_plan_versions
    ):
        stale_plan = True

    stale_coalition = bool(
        expected_coalition_version is not None
        and coalition_version != int(expected_coalition_version)
    )
    assignment_coalition_versions = {
        value
        for value in (
            _optional_integer(_get(item, "coalition_version"))
            for item in relevant_assignments
        )
        if value is not None
    }
    terminal_coalition_version = _optional_integer(
        _get(terminal_association, "coalition_version")
    )
    if terminal_coalition_version is not None:
        assignment_coalition_versions.add(terminal_coalition_version)
    if coalition_version is not None and any(
        value != coalition_version for value in assignment_coalition_versions
    ):
        stale_coalition = True

    assignment_coalition_ids = _unique_strings(
        _get(item, "coalition_id") for item in relevant_assignments
    )
    coalition_id_conflict = bool(
        coalition_id
        and any(item != coalition_id for item in assignment_coalition_ids)
    )
    complete = bool(_get(coalition, "complete", False)) if coalition is not None else (
        len(assignment_ids) >= required
    )
    assigned_count = _integer(
        _get(coalition, "assigned_resource_count"), len(assignment_ids)
    )
    visual_consensus = _optional_boolean(
        _get(cross_view_summary, "coalition_visual_consensus")
    )
    visual_primary_complete = _optional_boolean(
        _get(cross_view_summary, "primary_lock_complete")
    )
    visual_primary_locked_ids = _unique_strings(
        _sequence(_get(cross_view_summary, "primary_locked_resource_ids", ()))
    )
    visual_primary_required = _optional_integer(
        _get(cross_view_summary, "primary_required_count")
    )
    visual_conflict_state = _enum_text(
        _get(cross_view_summary, "coalition_conflict_state", "")
    )
    visual_conflict_state = (
        visual_conflict_state if visual_conflict_state not in {"", "none"} else None
    )
    visual_plan_id = _string(_get(cross_view_summary, "plan_id"))
    visual_plan_version = _optional_integer(_get(cross_view_summary, "plan_version"))
    visual_coalition_id = _string(_get(cross_view_summary, "coalition_id"))
    visual_coalition_version = _optional_integer(
        _get(cross_view_summary, "coalition_version")
    )
    visual_track_id = _string(_get(cross_view_summary, "global_track_id"))
    visual_commit_required = bool(
        _get(cross_view_summary, "coalition_commit_required", False)
    )
    visual_commit_valid = bool(
        _get(cross_view_summary, "coalition_commit_valid", not visual_commit_required)
    )
    visual_commit_state = _enum_text(
        _get(cross_view_summary, "coalition_commit_state", "")
    )
    visual_commit_conflicts = _unique_strings(
        _sequence(
            _get(cross_view_summary, "coalition_commit_conflict_reasons", ())
        )
    )
    visual_required_commit_ids = _unique_strings(
        _sequence(
            _get(cross_view_summary, "coalition_commit_required_member_ids", ())
        )
    )
    visual_acked_commit_ids = _unique_strings(
        _sequence(
            _get(cross_view_summary, "coalition_commit_acked_member_ids", ())
        )
    )
    unresolved_duplicate = bool(
        coalition_required
        and _raw_duplicate_lock(terminal_association, cross_view_summary)
        and len(locked_ids) < 2
    )

    conflicts: list[str] = []
    if coalition_required and coalition is None:
        conflicts.append("coalition_plan_missing")
    if stale_plan:
        conflicts.append("stale_plan_version")
    if stale_coalition:
        conflicts.append("stale_coalition_version")
    if coalition_id_conflict:
        conflicts.append("coalition_id_mismatch")
    if coalition_required and not complete:
        conflicts.append("coalition_incomplete")
    if coalition_required and len(authorized_ids) != required:
        conflicts.append("coalition_member_count_mismatch")
    if member_ids and any(item not in set(member_ids) for item in assignment_ids):
        conflicts.append("coalition_assignment_outside_membership")
    if unauthorized_ids:
        conflicts.append("unauthorized_coalition_lock")
    if len(locked_ids) > required:
        conflicts.append("coalition_lock_count_exceeded")
    if unresolved_duplicate:
        conflicts.append("coalition_lock_membership_unresolved")
    if visual_track_id is not None and visual_track_id != global_track_id:
        conflicts.append("coalition_visual_track_mismatch")
    if visual_plan_id is not None and visual_plan_id != _string(_get(plan, "plan_id")):
        conflicts.append("coalition_visual_plan_mismatch")
    if visual_plan_version is not None and visual_plan_version != plan_version:
        conflicts.append("coalition_visual_plan_version_stale")
    if visual_coalition_id is not None and visual_coalition_id != coalition_id:
        conflicts.append("coalition_visual_coalition_mismatch")
    if (
        visual_coalition_version is not None
        and visual_coalition_version != coalition_version
    ):
        conflicts.append("coalition_visual_coalition_version_stale")
    if visual_conflict_state is not None:
        conflicts.append("coalition_visual_conflict")
    if visual_consensus is True and visual_primary_complete is not True:
        conflicts.append("coalition_visual_primary_incomplete")
    if visual_commit_required and (
        not visual_commit_valid
        or visual_commit_state not in {"committed", "executing"}
        or bool(visual_commit_conflicts)
        or not visual_required_commit_ids
        or set(visual_required_commit_ids) != set(visual_acked_commit_ids)
    ):
        conflicts.append("coalition_commit_incomplete")
    conflict_reasons = _unique_strings(conflicts)
    commit_conflicts = _coalition_commit_conflicts(
        coalition_commit_state,
        global_track_id=global_track_id,
        coalition_id=coalition_id,
        coalition_version=coalition_version,
        plan_id=_string(_get(plan, "plan_id")),
        plan_version=plan_version,
        authorized_resource_ids=authorized_ids,
        current_time_s=current_time_s,
    )
    atomic_coalition_formed = bool(
        coalition_required
        and coalition_commit_state is not None
        and not conflict_reasons
        and not commit_conflicts
    )
    effective_commit_conflicts = (
        commit_conflicts if coalition_required and not center_available else ()
    )

    visual_scope_current = bool(
        cross_view_summary is not None
        and visual_track_id == global_track_id
        and visual_plan_id == _string(_get(plan, "plan_id"))
        and visual_plan_version == plan_version
        and visual_coalition_id == coalition_id
        and visual_coalition_version == coalition_version
    )
    visual_primary_members_current = bool(
        primary_member_ids
        and visual_primary_required == len(primary_member_ids)
        and set(visual_primary_locked_ids) == set(primary_member_ids)
    )
    visual_commit_complete = bool(
        not visual_commit_required
        or (
            visual_commit_valid
            and visual_commit_state in {"committed", "executing"}
            and bool(visual_required_commit_ids)
            and set(visual_required_commit_ids) == set(visual_acked_commit_ids)
            and not visual_commit_conflicts
        )
    )
    center_consensus_recovered = bool(
        coalition_required
        and center_available
        and visual_consensus is True
        and visual_primary_complete is True
        and visual_scope_current
        and visual_primary_members_current
        and visual_conflict_state is None
        and visual_commit_complete
        and not conflict_reasons
    )

    legal_multi_lock = bool(
        coalition_required
        and len(locked_ids) > 1
        and not unauthorized_ids
        and len(locked_ids) <= required
        and not stale_plan
        and not stale_coalition
        and not coalition_id_conflict
    )
    if not coalition_required:
        action = CoalitionSafetyAction.NOT_APPLICABLE
        reason = "independent_assignment"
        safe = True
        fallback_supported = True
    elif not center_available and atomic_coalition_formed:
        action = CoalitionSafetyAction.ALLOW_ATOMIC_FALLBACK
        reason = "coalition_atomic_fallback_committed"
        safe = True
        fallback_supported = True
    elif not center_available:
        action = CoalitionSafetyAction.HOLD_OR_REVOKE
        reason = "coalition_fallback_unsupported"
        safe = False
        fallback_supported = False
    elif conflict_reasons:
        action = CoalitionSafetyAction.HOLD_OR_REVOKE
        reason = _conflict_reason(conflict_reasons)
        safe = False
        fallback_supported = False
    else:
        action = CoalitionSafetyAction.CONTINUE_CENTER
        reason = "coalition_center_plan_valid"
        safe = True
        fallback_supported = False

    return CoalitionSafetyEvidence(
        global_track_id=global_track_id,
        coalition_required=coalition_required,
        center_available=center_available,
        fallback_supported=fallback_supported,
        safety_action=action,
        safety_reason=reason,
        safe_to_execute=safe,
        plan_id=_string(_get(plan, "plan_id")),
        plan_version=plan_version,
        expected_plan_version=required_plan_version,
        coalition_id=coalition_id,
        coalition_version=coalition_version,
        expected_coalition_version=expected_coalition_version,
        required_resource_count=required,
        assigned_resource_count=assigned_count,
        coalition_complete=complete,
        authorized_resource_ids=authorized_ids,
        primary_resource_ids=primary_member_ids,
        locked_resource_ids=locked_ids,
        primary_locked_resource_ids=visual_primary_locked_ids,
        coalition_visual_consensus=visual_consensus,
        coalition_visual_primary_complete=visual_primary_complete,
        coalition_visual_current=visual_scope_current,
        center_consensus_recovered=center_consensus_recovered,
        coalition_visual_conflict_state=visual_conflict_state,
        legal_multi_resource_lock=legal_multi_lock,
        unauthorized_resource_ids=unauthorized_ids,
        excess_resource_ids=excess_ids,
        stale_plan_version=stale_plan,
        stale_coalition_version=stale_coalition,
        atomic_coalition_formed=atomic_coalition_formed,
        coalition_commit_state=(
            coalition_commit_state.state if coalition_commit_state is not None else None
        ),
        coalition_commit_epoch=(
            coalition_commit_state.epoch if coalition_commit_state is not None else None
        ),
        coalition_commit_coordinator_id=(
            coalition_commit_state.coordinator_id
            if coalition_commit_state is not None
            else None
        ),
        coalition_commit_coordinator_role=(
            coalition_commit_state.coordinator_role
            if coalition_commit_state is not None
            else None
        ),
        coalition_commit_lease_expires_at=(
            coalition_commit_state.lease_expires_at
            if coalition_commit_state is not None
            else None
        ),
        conflict_reasons=_unique_strings(
            (*conflict_reasons, *effective_commit_conflicts)
        ),
        metadata={
            "coordination_mode": coordination_mode or "independent",
            "raw_duplicate_lock": _raw_duplicate_lock(
                terminal_association, cross_view_summary
            ),
            "assignment_resource_ids": list(assignment_ids),
            "member_resource_ids": list(member_ids),
            "primary_resource_ids": list(primary_member_ids),
            "coalition_visual_primary_required_count": visual_primary_required,
            "coalition_visual_commit_required": visual_commit_required,
            "coalition_visual_commit_valid": visual_commit_valid,
            "coalition_visual_commit_conflict_reasons": list(
                visual_commit_conflicts
            ),
            "coalition_commit": (
                coalition_commit_state.to_dict()
                if coalition_commit_state is not None
                else None
            ),
            "coalition_commit_d6": build_coalition_commit_d6_metadata(
                coalition_commit_state,
                current_time_s=current_time_s,
            ),
            "coalition_fallback_mode": (
                _fallback_mode(coalition_commit_state.coordinator_role)
                if coalition_commit_state is not None
                else None
            ),
        },
    )


def _coalition_commit_conflicts(
    state: CoalitionCommitState | None,
    *,
    global_track_id: str,
    coalition_id: str | None,
    coalition_version: int | None,
    plan_id: str | None,
    plan_version: int | None,
    authorized_resource_ids: tuple[str, ...],
    current_time_s: float | None,
) -> tuple[str, ...]:
    if state is None:
        return ("coalition_commit_missing",)
    conflicts: list[str] = []
    if state.global_track_id != global_track_id:
        conflicts.append("coalition_commit_track_mismatch")
    if state.coalition_id != coalition_id or state.coalition_version != coalition_version:
        conflicts.append("coalition_commit_version_mismatch")
    if state.plan_id != plan_id or state.plan_version != plan_version:
        conflicts.append("coalition_commit_plan_mismatch")
    if set(state.required_member_ids) != set(authorized_resource_ids):
        conflicts.append("coalition_commit_membership_mismatch")
    if set(state.acked_member_ids) != set(state.required_member_ids):
        conflicts.append("coalition_commit_missing_ack")
    if state.state not in {"committed", "executing"}:
        conflicts.append("coalition_commit_not_committed")
    if current_time_s is not None and float(current_time_s) >= state.lease_expires_at:
        conflicts.append("coalition_commit_lease_expired")
    return _unique_strings(conflicts)


def _proposal_stale_reason(
    current: CoalitionCommitState,
    proposal: CoalitionCommitState,
) -> str | None:
    if proposal.epoch < current.epoch:
        return "coalition_epoch_stale"
    if proposal.plan_version < current.plan_version:
        return "coalition_plan_version_stale"
    if proposal.coalition_version < current.coalition_version:
        return "coalition_version_stale"
    return None


def _ack_rejection_reason(
    state: CoalitionCommitState,
    ack: CoalitionMemberAck,
    *,
    timestamp: float,
) -> str | None:
    if ack.resource_id not in set(state.required_member_ids):
        return "ack_resource_not_required_member"
    if ack.global_track_id != state.global_track_id:
        return "ack_track_mismatch"
    if ack.coalition_id != state.coalition_id:
        return "ack_coalition_mismatch"
    if ack.coalition_version != state.coalition_version:
        return "ack_coalition_version_stale"
    if ack.plan_id != state.plan_id or ack.plan_version != state.plan_version:
        return "ack_plan_version_stale"
    if ack.epoch != state.epoch:
        return "ack_epoch_stale"
    if timestamp > ack.valid_until:
        return "ack_expired"
    if ack.evidence_timestamp > timestamp:
        return "ack_evidence_from_future"
    return None


def _commit_identity(state: CoalitionCommitState) -> tuple[Any, ...]:
    return (
        state.global_track_id,
        state.coalition_id,
        state.coalition_version,
        state.plan_id,
        state.plan_version,
        state.epoch,
    )


def _commit_digest(state: CoalitionCommitState) -> str:
    return "|".join(
        (
            state.global_track_id,
            state.coalition_id,
            str(state.coalition_version),
            state.plan_id,
            str(state.plan_version),
            str(state.epoch),
            state.coordinator_id,
            state.coordinator_role,
            ",".join(state.required_member_ids),
        )
    )


def _commit_runtime_digest(state: CoalitionCommitState) -> str:
    return "|".join(
        (
            _commit_digest(state),
            state.state,
            ",".join(state.acked_member_ids),
            f"{state.lease_expires_at:.9f}",
        )
    )


def _fallback_mode(coordinator_role: str) -> str:
    return (
        "secondary"
        if str(coordinator_role).strip().lower() in _SECONDARY_COORDINATOR_ROLES
        else "distributed"
    )


def _increment_metadata(
    metadata: Mapping[str, Any],
    counter_name: str,
    **values: Any,
) -> dict[str, Any]:
    return {
        **dict(metadata),
        counter_name: int(metadata.get(counter_name, 0)) + 1,
        **values,
    }


def _conflict_reason(conflicts: tuple[str, ...]) -> str:
    if "stale_plan_version" in conflicts:
        return "coalition_plan_version_stale"
    if "stale_coalition_version" in conflicts:
        return "coalition_version_stale"
    if "coalition_incomplete" in conflicts or "coalition_plan_missing" in conflicts:
        return "coalition_plan_incomplete"
    return "coalition_membership_conflict"


def _find_coalition(
    plan: Any | None,
    *,
    global_track_id: str,
    coalition_id: str | None,
) -> Any | None:
    for item in _sequence(_get(plan, "coalitions", ())):
        if _target_id(item) == global_track_id:
            return item
        if coalition_id and _string(_get(item, "coalition_id")) == coalition_id:
            return item
    return None


def _locked_resource_ids(
    terminal: Any | None,
    cross_view: Any | None,
    *,
    global_track_id: str,
    resource_id: str,
) -> tuple[str, ...]:
    values: list[Any] = []
    for source in (terminal, cross_view):
        metadata = _mapping(_get(source, "metadata", {}))
        for key in (
            "locked_resource_ids",
            "primary_locked_resource_ids",
            "duplicate_lock_resource_ids",
            "excess_lock_resource_ids",
        ):
            values.extend(_sequence(_get(source, key, metadata.get(key, ()))))
    state = _enum_text(_get(terminal, "decision_state", _get(terminal, "state", "")))
    assigned_track = _string(_get(terminal, "assigned_global_track_id"))
    if state in {"lock", "locked", "terminal_lock"} and assigned_track in {
        None,
        global_track_id,
    }:
        values.append(_get(terminal, "resource_id", resource_id))
    return _unique_strings(values)


def _raw_duplicate_lock(terminal: Any | None, cross_view: Any | None) -> bool:
    for source in (terminal, cross_view):
        metadata = _mapping(_get(source, "metadata", {}))
        if bool(
            _get(source, "duplicate_terminal_lock", False)
            or _get(source, "duplicate_terminal_lock_risk", False)
            or _get(source, "duplicate_lock_risk", False)
            or metadata.get("duplicate_terminal_lock")
            or metadata.get("duplicate_terminal_lock_risk")
            or metadata.get("duplicate_lock_risk")
        ):
            return True
    return False


def _target_id(value: Any) -> str | None:
    return _string(
        _get(value, "target_id", _get(value, "global_track_id", _get(value, "track_id")))
    )


def _get(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> tuple[Any, ...]:
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


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _enum_text(value: Any) -> str:
    if isinstance(value, Enum):
        value = value.value
    return str(value).strip().lower()


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _optional_integer(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_boolean(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _strict_nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _strict_nonnegative_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite and non-negative")
    parsed = float(value)
    if not isfinite(parsed) or parsed < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return parsed


def _unique_strings(values: Iterable[Any]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = _string(value)
        if text is not None and text not in result:
            result.append(text)
    return tuple(result)


def _unique_objects(values: Iterable[Any]) -> tuple[Any, ...]:
    result: list[Any] = []
    seen: set[tuple[str | None, str | None, int | None]] = set()
    for value in values:
        if value is None:
            continue
        key = (
            _target_id(value),
            _string(_get(value, "resource_id")),
            _optional_integer(_get(value, "coalition_version")),
        )
        if key not in seen:
            result.append(value)
            seen.add(key)
    return tuple(result)
