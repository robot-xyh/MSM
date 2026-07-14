"""Read-only per-primary terminal visual evidence.

This module does not grant control authority and does not compare one primary
against another. It reports whether one current active primary has a safe D5
lock under a versioned center-owned binding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import TerminalAssociation


_ACTIVE_PRIMARY_ROLES = frozenset({"primary", "lead_primary", "support_primary"})
_ACTIVE_STATES = frozenset({"active", "activated", "committed", "executing"})
_AUTHORIZED_STATES = frozenset({"authorized", "approved", "granted", "active"})
_CLEAR_FRIEND_STATES = frozenset({"none", "clear", "no_conflict"})


@dataclass(frozen=True)
class PerPrimaryTerminalEvidence:
    """Passive evidence consumed by main/D7 after D3/D4 checks."""

    resource_id: str | None
    assigned_global_track_id: str
    terminal_authorization_scope: str
    arrival_coordination_required: bool
    plan_id: str | None
    plan_version: int | None
    coalition_id: str | None
    coalition_version: int | None
    member_role: str
    activation_state: str
    decision_state: str
    local_track_id: str | None
    independently_locked: bool
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "assigned_global_track_id": self.assigned_global_track_id,
            "terminal_authorization_scope": self.terminal_authorization_scope,
            "arrival_coordination_required": self.arrival_coordination_required,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "coalition_id": self.coalition_id,
            "coalition_version": self.coalition_version,
            "member_role": self.member_role,
            "activation_state": self.activation_state,
            "decision_state": self.decision_state,
            "local_track_id": self.local_track_id,
            "independently_locked": self.independently_locked,
            "rejection_reasons": list(self.rejection_reasons),
            "requires_other_primary_same_frame_lock": False,
            "grants_control_authority": False,
            "global_track_id_rewrite_count": 0,
            "truth_identity_used": False,
        }


def per_primary_terminal_evidence(
    association: TerminalAssociation,
    *,
    terminal_authorization_scope: str | None = None,
    arrival_coordination_required: bool | None = None,
    expected_resource_id: str | None = None,
    expected_assigned_global_track_id: str | None = None,
    expected_plan_id: str | None = None,
    expected_plan_version: int | None = None,
    expected_coalition_id: str | None = None,
    expected_coalition_version: int | None = None,
) -> PerPrimaryTerminalEvidence:
    """Evaluate one primary without creating or rebinding a global identity."""

    scope = association.terminal_authorization_scope
    if scope not in {"per_primary", "coalition"}:
        raise ValueError("terminal_authorization_scope must be per_primary or coalition")
    coordination_required = association.arrival_coordination_required

    reasons: list[str] = []
    if (
        terminal_authorization_scope is not None
        and str(terminal_authorization_scope).strip().lower() != scope
    ):
        reasons.append("terminal_authorization_scope_mismatch")
    if (
        arrival_coordination_required is not None
        and bool(arrival_coordination_required) != coordination_required
    ):
        reasons.append("arrival_coordination_contract_mismatch")
    if scope != "per_primary":
        reasons.append("terminal_authorization_scope_not_per_primary")
    if coordination_required:
        reasons.append("arrival_coordination_still_required")
    if not association.resource_id:
        reasons.append("resource_id_missing")
    if expected_resource_id is not None and association.resource_id != expected_resource_id:
        reasons.append("resource_binding_mismatch")
    if (
        expected_assigned_global_track_id is not None
        and association.assigned_global_track_id != expected_assigned_global_track_id
    ):
        reasons.append("global_track_binding_mismatch")
    if association.member_role not in _ACTIVE_PRIMARY_ROLES:
        reasons.append("member_role_not_active_primary")
    if association.activation_state not in _ACTIVE_STATES:
        reasons.append("primary_not_active")
    if association.authorization_state.lower() not in _AUTHORIZED_STATES:
        reasons.append("assignment_not_authorized")
    if association.plan_id is None or association.plan_version is None:
        reasons.append("versioned_plan_binding_missing")
    if expected_plan_id is not None and association.plan_id != expected_plan_id:
        reasons.append("plan_id_mismatch")
    if (
        expected_plan_version is not None
        and association.plan_version != int(expected_plan_version)
    ):
        reasons.append("plan_version_mismatch")
    if association.required_resource_count > 1 and (
        association.coalition_id is None or association.coalition_version is None
    ):
        reasons.append("versioned_coalition_binding_missing")
    if expected_coalition_id is not None and association.coalition_id != expected_coalition_id:
        reasons.append("coalition_id_mismatch")
    if (
        expected_coalition_version is not None
        and association.coalition_version != int(expected_coalition_version)
    ):
        reasons.append("coalition_version_mismatch")
    if association.decision_state != "locked":
        reasons.append("terminal_association_not_locked")
    visual_state = str(
        association.metadata.get("visual_match_decision_state", association.decision_state)
    ).lower()
    if visual_state != "locked":
        reasons.append("visual_match_not_locked")
    if association.local_track_id is None or association.local_track_state != "measured":
        reasons.append("current_measured_local_track_missing")
    if association.friend_conflict_state.lower() not in _CLEAR_FRIEND_STATES:
        reasons.append("friend_conflict_present")
    if association.duplicate_terminal_lock_risk:
        reasons.append("duplicate_terminal_lock_risk")
    if not bool(association.metadata.get("execution_gate_pass", True)):
        reasons.append("execution_gate_rejected")
    if association.truth_identity_used or bool(
        association.metadata.get("truth_identity_used", False)
    ):
        reasons.append("truth_identity_use_rejected")

    return PerPrimaryTerminalEvidence(
        resource_id=association.resource_id,
        assigned_global_track_id=association.assigned_global_track_id,
        terminal_authorization_scope=scope,
        arrival_coordination_required=coordination_required,
        plan_id=association.plan_id,
        plan_version=association.plan_version,
        coalition_id=association.coalition_id,
        coalition_version=association.coalition_version,
        member_role=association.member_role,
        activation_state=association.activation_state,
        decision_state=association.decision_state,
        local_track_id=association.local_track_id,
        independently_locked=not reasons,
        rejection_reasons=tuple(reasons),
    )
