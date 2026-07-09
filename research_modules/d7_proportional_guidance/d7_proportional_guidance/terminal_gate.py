"""Terminal PNG handoff contract checks for D7.

This module validates the non-visual contracts that must pass before a caller
is allowed to evaluate terminal visual PNG guidance.  It is intentionally
passive and dependency-light: D5 TerminalAssociation and D4 decisions are read
by field name so D7 does not import upstream modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .models import GuidanceMode


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
SECONDARY_TAKEOVER_READY_CLASS = "takeover_ready"


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
    owner_node_id: str | None = None
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
    secondary_capability_class: str | None = None
    secondary_readiness_class: str | None = None
    visual_png_allowed: bool | None = None
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
    owner_node_id: str | None = None
    d4_target_node_id: str | None = None
    track_version: int | None = None
    d4_action_block_reason: str = ""
    secondary_capability_class: str | None = None
    secondary_readiness_class: str | None = None
    d4_visual_png_allowed: bool | None = None
    d3_plan_version_consistent: bool | None = None
    d3_owner_consistent: bool | None = None
    d3_owner_version_consistent: bool | None = None
    d5_lock_consistent: bool | None = None
    d5_lock_consistency_reason: str = ""
    d5_assigned_global_track_id: str | None = None
    d5_assignment_version: int | None = None


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

    permission = coerce_d4_guidance_permission(d4_permission)
    d3_plan_version_consistent = _d4_plan_version_consistent(permission, assignment)
    d3_owner_consistent = _d4_owner_consistent(permission, assignment)
    base = {
        "assigned_global_track_id": assignment.assigned_global_track_id,
        "d4_action": permission.action,
        "plan_id": assignment.plan_id,
        "plan_version": assignment.plan_version,
        "owner_node_id": assignment.owner_node_id,
        "track_version": assignment.track_version,
        "d4_target_node_id": permission.target_node_id,
        "secondary_capability_class": permission.secondary_capability_class,
        "secondary_readiness_class": permission.secondary_readiness_class,
        "d4_visual_png_allowed": permission.visual_png_allowed,
        "d3_plan_version_consistent": d3_plan_version_consistent,
        "d3_owner_consistent": d3_owner_consistent,
        "d3_owner_version_consistent": (
            d3_plan_version_consistent is True and d3_owner_consistent is True
        ),
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

    action = permission.action.lower()
    if permission.requires_human_review:
        return TerminalPngContractDecision(
            False,
            "d4_hold_for_review",
            d4_action_block_reason="d4_hold_for_review",
            **base,
        )
    if action in BLOCKING_D4_ACTION_REASONS:
        reason = BLOCKING_D4_ACTION_REASONS[action]
        return TerminalPngContractDecision(
            False,
            reason,
            d4_action_block_reason=reason,
            **base,
        )
    if permission.visual_png_allowed is False:
        reason = permission.reason or "d4_visual_png_not_allowed"
        return TerminalPngContractDecision(
            False,
            reason,
            d4_action_block_reason=reason,
            **base,
        )
    if not permission.terminal_consistent:
        return TerminalPngContractDecision(False, "d4_terminal_inconsistent", **base)
    if permission.new_plan_id is not None and permission.new_plan_id != assignment.plan_id:
        return TerminalPngContractDecision(False, "d4_plan_mismatch", **base)
    if permission.new_plan_version is not None and permission.new_plan_version != assignment.plan_version:
        return TerminalPngContractDecision(False, "d4_plan_mismatch", **base)
    if permission.target_node_id is not None:
        if assignment.owner_node_id is None:
            return TerminalPngContractDecision(False, "d4_owner_missing", **base)
        if permission.target_node_id != assignment.owner_node_id:
            return TerminalPngContractDecision(False, "d4_owner_mismatch", **base)
    if _secondary_takeover_readiness_required(permission, assignment):
        readiness_ready = _secondary_takeover_ready(permission)
        if readiness_ready is False:
            return TerminalPngContractDecision(
                False,
                "secondary_capability_not_takeover_ready",
                d4_action_block_reason="secondary_capability_not_takeover_ready",
                **base,
            )
    if action not in ALLOWED_D4_ACTIONS:
        return TerminalPngContractDecision(
            False,
            "d4_action_not_allowed",
            d4_action_block_reason="d4_action_not_allowed",
            **base,
        )

    if terminal_association is None:
        return TerminalPngContractDecision(
            False,
            "d5_not_locked",
            d5_lock_consistent=False,
            d5_lock_consistency_reason="d5_not_locked",
            **base,
        )
    d5_decision_state = _string_value(terminal_association, "decision_state", default="").lower()
    local_track_id = _optional_string_value(terminal_association, "local_track_id")
    terminal_global_id = _string_value(
        terminal_association,
        "assigned_global_track_id",
        default="",
    )
    association_version = _optional_int_value(terminal_association, "assignment_version")
    base["d5_decision_state"] = d5_decision_state
    base["local_track_id"] = local_track_id
    base["d5_assigned_global_track_id"] = terminal_global_id or None
    base["d5_assignment_version"] = association_version
    if d5_decision_state != "locked":
        return TerminalPngContractDecision(
            False,
            "d5_not_locked",
            d5_lock_consistent=False,
            d5_lock_consistency_reason="d5_not_locked",
            **base,
        )
    if _string_value(terminal_association, "friend_conflict_state", default="none").lower() != "none":
        return TerminalPngContractDecision(
            False,
            "friend_conflict",
            d5_lock_consistent=False,
            d5_lock_consistency_reason="friend_conflict",
            **base,
        )
    if not _ids_match(terminal_global_id, assignment.assigned_global_track_id):
        return TerminalPngContractDecision(
            False,
            "terminal_identity_mismatch",
            d5_lock_consistent=False,
            d5_lock_consistency_reason="terminal_identity_mismatch",
            **base,
        )
    if association_version is not None and association_version != assignment.track_version:
        return TerminalPngContractDecision(
            False,
            "assignment_version_mismatch",
            d5_lock_consistent=False,
            d5_lock_consistency_reason="assignment_version_mismatch",
            **base,
        )

    observation_global_id = _optional_string_value(observation, "assigned_global_track_id")
    if observation_global_id and not _ids_match(observation_global_id, assignment.assigned_global_track_id):
        return TerminalPngContractDecision(
            False,
            "terminal_identity_mismatch",
            d5_lock_consistent=False,
            d5_lock_consistency_reason="terminal_identity_mismatch",
            **base,
        )

    return TerminalPngContractDecision(
        True,
        "",
        d5_lock_consistent=True,
        d5_lock_consistency_reason="consistent",
        **base,
    )


def guidance_mode_from_terminal_contract(
    decision: TerminalPngContractDecision,
    *,
    handover_pending: bool,
    terminal_locked: bool,
) -> GuidanceMode:
    """Map a terminal contract result to an explicit D7 log state."""

    if terminal_locked and decision.allowed:
        return GuidanceMode.VISION_TERMINAL
    if not handover_pending:
        return GuidanceMode.RADAR_MIDCOURSE
    if decision.allowed:
        return GuidanceMode.HANDOVER_PENDING

    reason = decision.reject_reason
    if reason in {
        "d5_not_locked",
        "terminal_identity_mismatch",
        "assignment_version_mismatch",
        "d4_terminal_inconsistent",
        "d4_plan_mismatch",
        "d4_owner_missing",
        "d4_owner_mismatch",
    }:
        return GuidanceMode.REACQUIRE
    if reason in {"d4_hold_for_review", "friend_conflict", "assignment_not_authorized"}:
        return GuidanceMode.HOLD
    if reason in {
        "assignment_revoked",
        "assignment_expired",
        "d4_reassign_pending",
        "secondary_capability_not_takeover_ready",
    }:
        return GuidanceMode.ABORT_REVOKE
    return GuidanceMode.HANDOVER_PENDING


def coerce_assignment_guidance_binding(
    value: AssignmentGuidanceBinding | Mapping[str, Any] | Any,
) -> AssignmentGuidanceBinding:
    if isinstance(value, AssignmentGuidanceBinding):
        return value
    aliases = _string_tuple(_value(value, "target_mesh_aliases", default=()))
    return AssignmentGuidanceBinding(
        plan_id=_required_string(value, "plan_id"),
        plan_version=_required_int(value, "plan_version"),
        owner_node_id=_optional_string_value(value, "owner_node_id")
        or _optional_string_value(value, "plan_owner_id")
        or _optional_string_value(value, "owner_node"),
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
    d7_action = _optional_string_value(value, "d7_action")
    action = (
        d7_action
        or _optional_string_value(value, "action")
        or _optional_string_value(value, "d4_action")
        or "continue_center"
    )
    return D4GuidancePermission(
        action=action,
        mode=_string_value(value, "mode", default="none"),
        reason=_string_value(value, "reason", default=""),
        target_node_id=_optional_string_value(value, "target_node_id")
        or _optional_string_value(value, "new_plan_owner_id")
        or _optional_string_value(value, "new_owner_node_id")
        or _optional_string_value(value, "plan_owner_id")
        or _optional_string_value(value, "owner_node_id"),
        terminal_consistent=bool(_value(value, "terminal_consistent", default=True)),
        requires_human_review=bool(_value(value, "requires_human_review", default=False)),
        new_plan_id=_optional_string_value(value, "new_plan_id"),
        new_plan_version=_optional_int_value(value, "new_plan_version"),
        secondary_capability_class=_optional_string_value_with_metadata(
            value,
            "secondary_capability_class",
        ),
        secondary_readiness_class=(
            _optional_string_value_with_metadata(value, "secondary_readiness_class")
            or _optional_string_value_with_metadata(value, "readiness_class")
            or _optional_string_value_with_metadata(value, "readiness")
            or _optional_string_value_with_metadata(value, "secondary_capability_readiness")
        ),
        visual_png_allowed=_optional_bool_value_with_metadata(value, "visual_png_allowed"),
        metadata=dict(_value(value, "metadata", default={}) or {}),
    )


def _d4_plan_version_consistent(
    permission: D4GuidancePermission,
    assignment: AssignmentGuidanceBinding,
) -> bool:
    if permission.new_plan_id is not None and permission.new_plan_id != assignment.plan_id:
        return False
    if permission.new_plan_version is not None and permission.new_plan_version != assignment.plan_version:
        return False
    return True


def _d4_owner_consistent(
    permission: D4GuidancePermission,
    assignment: AssignmentGuidanceBinding,
) -> bool:
    if permission.target_node_id is None:
        return True
    if assignment.owner_node_id is None:
        return False
    return permission.target_node_id == assignment.owner_node_id


def _secondary_takeover_readiness_required(
    permission: D4GuidancePermission,
    assignment: AssignmentGuidanceBinding,
) -> bool:
    if permission.action.lower() == "request_secondary_assist":
        return True
    metadata_owner = str(assignment.metadata.get("active_plan_owner", "")).lower()
    if metadata_owner == "secondary":
        return True
    if assignment.owner_node_id and assignment.owner_node_id.lower() not in {"center", "central"}:
        return True
    return bool(permission.target_node_id and permission.target_node_id.lower() not in {"center", "central"})


def _secondary_takeover_ready(permission: D4GuidancePermission) -> bool | None:
    values = {
        value.strip().lower()
        for value in (
            permission.secondary_readiness_class,
            permission.secondary_capability_class,
        )
        if value and value.strip()
    }
    if not values:
        return None
    return SECONDARY_TAKEOVER_READY_CLASS in values


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


def _optional_string_value_with_metadata(record: Any, name: str) -> str | None:
    return _optional_string_value(record, name) or _optional_string_value(
        _value(record, "metadata", default=None),
        name,
    )


def _optional_bool_value_with_metadata(record: Any, name: str) -> bool | None:
    value = _value(record, name, default=None)
    if value is None:
        value = _value(_value(record, "metadata", default=None), name, default=None)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1", "allowed", "allow"}:
        return True
    if text in {"false", "f", "no", "n", "0", "blocked", "block", "rejected"}:
        return False
    return None


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
