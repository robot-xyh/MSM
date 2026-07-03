"""Terminal PNG handoff contract checks for D7.

This module validates the non-visual contracts that must pass before a caller
is allowed to evaluate terminal visual PNG guidance.  It is intentionally
passive and dependency-light: D5 TerminalAssociation and D4 decisions are read
by field name so D7 does not import upstream modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


EFFECTIVE_AUTHORIZATION_STATES = frozenset(
    {
        "authorized",
        "approved",
        "human_approved",
        "operator_approved",
        "recorded",
    }
)

CURRENT_ASSIGNMENT_STATES = frozenset({"active", "current", "valid"})
ALLOWED_D4_ACTIONS = frozenset({"continue", "continue_center", "request_secondary_assist"})
BLOCKING_D4_ACTION_REASONS = {
    "hold_for_review": "d4_hold_for_review",
    "request_center_replan": "d4_reassign_pending",
    "degrade_to_secondary": "d4_reassign_pending",
    "degrade_to_distributed": "d4_reassign_pending",
    "reassign": "d4_reassign_pending",
}


@dataclass(frozen=True)
class AssignmentGuidanceBinding:
    """Versioned D3 assignment binding consumed by D7 guidance."""

    plan_id: str
    plan_version: int
    resource_id: str
    vehicle_name: str
    assigned_global_track_id: str
    track_version: int
    authorization_state: str
    assignment_id: str | None = None
    assignment_validity_state: str = "current"
    created_at_s: float = 0.0
    expires_at_s: float | None = None
    target_actor_name: str | None = None
    target_object_id: str | None = None
    target_mesh_aliases: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_authorized(self) -> bool:
        return self.authorization_state.lower() in EFFECTIVE_AUTHORIZATION_STATES

    @property
    def is_current(self) -> bool:
        return self.assignment_validity_state.lower() in CURRENT_ASSIGNMENT_STATES


@dataclass(frozen=True)
class D4GuidancePermission:
    """D4 action/permission summary consumed by D7 before terminal handoff."""

    action: str = "continue_center"
    mode: str = "none"
    reason: str = ""
    target_node_id: str | None = None
    terminal_consistent: bool = True
    requires_human_review: bool = False
    new_plan_id: str | None = None
    new_plan_version: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TerminalPngContractDecision:
    """Result of D3/D4/D5 terminal handoff contract validation."""

    allowed: bool
    reject_reason: str = ""
    assigned_global_track_id: str | None = None
    local_track_id: str | None = None
    d4_action: str = ""
    d5_decision_state: str = ""
    plan_id: str | None = None
    plan_version: int | None = None
    track_version: int | None = None


def evaluate_terminal_png_contract(
    *,
    binding: AssignmentGuidanceBinding | Mapping[str, Any] | Any | None,
    d4_permission: D4GuidancePermission | Mapping[str, Any] | Any | None,
    terminal_association: Mapping[str, Any] | Any | None,
    observation: Mapping[str, Any] | Any | None = None,
    timestamp_s: float | None = None,
    resource_id: str | None = None,
) -> TerminalPngContractDecision:
    """Return whether D7 may evaluate terminal visual PNG guidance."""

    if binding is None:
        return TerminalPngContractDecision(False, "assignment_missing")
    try:
        assignment = coerce_assignment_guidance_binding(binding)
    except (TypeError, ValueError) as exc:
        return TerminalPngContractDecision(False, f"assignment_invalid:{exc}")

    base = {
        "assigned_global_track_id": assignment.assigned_global_track_id,
        "d4_action": _string_value(d4_permission, "action", default=""),
        "plan_id": assignment.plan_id,
        "plan_version": assignment.plan_version,
        "track_version": assignment.track_version,
    }

    if resource_id is not None and resource_id != assignment.resource_id:
        return TerminalPngContractDecision(False, "resource_assignment_mismatch", **base)
    if not assignment.is_authorized:
        return TerminalPngContractDecision(False, "assignment_not_authorized", **base)
    if not assignment.is_current:
        state = assignment.assignment_validity_state.lower()
        reason = "assignment_revoked" if state in {"revoked", "superseded"} else "assignment_not_current"
        return TerminalPngContractDecision(False, reason, **base)
    if timestamp_s is not None and assignment.expires_at_s is not None:
        if timestamp_s > assignment.expires_at_s:
            return TerminalPngContractDecision(False, "assignment_expired", **base)

    permission = coerce_d4_guidance_permission(d4_permission)
    base["d4_action"] = permission.action
    action = permission.action.lower()
    if permission.requires_human_review:
        return TerminalPngContractDecision(False, "d4_hold_for_review", **base)
    if action in BLOCKING_D4_ACTION_REASONS:
        return TerminalPngContractDecision(False, BLOCKING_D4_ACTION_REASONS[action], **base)
    if not permission.terminal_consistent:
        return TerminalPngContractDecision(False, "d4_terminal_inconsistent", **base)
    if action not in ALLOWED_D4_ACTIONS:
        return TerminalPngContractDecision(False, "d4_action_not_allowed", **base)

    if terminal_association is None:
        return TerminalPngContractDecision(False, "d5_not_locked", **base)
    d5_decision_state = _string_value(terminal_association, "decision_state", default="").lower()
    local_track_id = _optional_string_value(terminal_association, "local_track_id")
    base["d5_decision_state"] = d5_decision_state
    base["local_track_id"] = local_track_id
    if d5_decision_state != "locked":
        return TerminalPngContractDecision(False, "d5_not_locked", **base)
    if _string_value(terminal_association, "friend_conflict_state", default="none").lower() != "none":
        return TerminalPngContractDecision(False, "friend_conflict", **base)

    terminal_global_id = _string_value(
        terminal_association,
        "assigned_global_track_id",
        default="",
    )
    if not _ids_match(terminal_global_id, assignment.assigned_global_track_id):
        return TerminalPngContractDecision(False, "terminal_identity_mismatch", **base)

    association_version = _optional_int_value(terminal_association, "assignment_version")
    if association_version is not None and association_version != assignment.track_version:
        return TerminalPngContractDecision(False, "assignment_version_mismatch", **base)

    observation_global_id = _optional_string_value(observation, "assigned_global_track_id")
    if observation_global_id and not _ids_match(observation_global_id, assignment.assigned_global_track_id):
        return TerminalPngContractDecision(False, "terminal_identity_mismatch", **base)

    return TerminalPngContractDecision(True, "", **base)


def coerce_assignment_guidance_binding(
    value: AssignmentGuidanceBinding | Mapping[str, Any] | Any,
) -> AssignmentGuidanceBinding:
    if isinstance(value, AssignmentGuidanceBinding):
        return value
    aliases = _string_tuple(_value(value, "target_mesh_aliases", default=()))
    return AssignmentGuidanceBinding(
        plan_id=_required_string(value, "plan_id"),
        plan_version=_required_int(value, "plan_version"),
        assignment_id=_optional_string_value(value, "assignment_id"),
        resource_id=_required_string(value, "resource_id"),
        vehicle_name=_required_string(value, "vehicle_name"),
        assigned_global_track_id=_required_string(value, "assigned_global_track_id"),
        track_version=_required_int(value, "track_version"),
        authorization_state=_required_string(value, "authorization_state"),
        assignment_validity_state=_string_value(value, "assignment_validity_state", default="current"),
        created_at_s=float(_value(value, "created_at_s", default=0.0)),
        expires_at_s=_optional_float_value(value, "expires_at_s"),
        target_actor_name=_optional_string_value(value, "target_actor_name"),
        target_object_id=_optional_string_value(value, "target_object_id"),
        target_mesh_aliases=aliases,
        metadata=dict(_value(value, "metadata", default={}) or {}),
    )


def coerce_d4_guidance_permission(
    value: D4GuidancePermission | Mapping[str, Any] | Any | None,
) -> D4GuidancePermission:
    if value is None:
        return D4GuidancePermission()
    if isinstance(value, D4GuidancePermission):
        return value
    return D4GuidancePermission(
        action=_string_value(value, "action", default="continue_center"),
        mode=_string_value(value, "mode", default="none"),
        reason=_string_value(value, "reason", default=""),
        target_node_id=_optional_string_value(value, "target_node_id"),
        terminal_consistent=bool(_value(value, "terminal_consistent", default=True)),
        requires_human_review=bool(_value(value, "requires_human_review", default=False)),
        new_plan_id=_optional_string_value(value, "new_plan_id"),
        new_plan_version=_optional_int_value(value, "new_plan_version"),
        metadata=dict(_value(value, "metadata", default={}) or {}),
    )


def _required_string(record: Any, name: str) -> str:
    value = _optional_string_value(record, name)
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _required_int(record: Any, name: str) -> int:
    value = _optional_int_value(record, name)
    if value is None:
        raise ValueError(f"{name} is required")
    return value


def _optional_string_value(record: Any, name: str) -> str | None:
    value = _value(record, name, default=None)
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    text = str(value)
    return text if text else None


def _string_value(record: Any, name: str, *, default: str) -> str:
    value = _optional_string_value(record, name)
    return default if value is None else value


def _optional_int_value(record: Any, name: str) -> int | None:
    value = _value(record, name, default=None)
    if value is None:
        return None
    return int(value)


def _optional_float_value(record: Any, name: str) -> float | None:
    value = _value(record, name, default=None)
    if value is None:
        return None
    return float(value)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    try:
        return tuple(str(item) for item in value if str(item))
    except TypeError:
        return (str(value),)


def _ids_match(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False
    left_aliases = {left, left.removeprefix("G-")}
    right_aliases = {right, right.removeprefix("G-")}
    left_aliases.add(f"G-{left.removeprefix('G-')}")
    right_aliases.add(f"G-{right.removeprefix('G-')}")
    return bool(left_aliases & right_aliases)


def _value(record: Any, name: str, *, default: Any) -> Any:
    if record is None:
        return default
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)
