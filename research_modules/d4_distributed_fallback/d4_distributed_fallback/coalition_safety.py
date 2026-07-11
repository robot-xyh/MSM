"""Fail-closed safety checks for centralized multi-resource coalitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .models import to_jsonable


class CoalitionSafetyAction(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    CONTINUE_CENTER = "continue_center"
    REQUEST_CENTER_REPLAN = "request_center_replan"
    HOLD_OR_REVOKE = "hold_or_revoke"


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
    locked_resource_ids: tuple[str, ...] = ()
    legal_multi_resource_lock: bool = False
    unauthorized_resource_ids: tuple[str, ...] = ()
    excess_resource_ids: tuple[str, ...] = ()
    stale_plan_version: bool = False
    stale_coalition_version: bool = False
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
    conflict_reasons = _unique_strings(conflicts)

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
        locked_resource_ids=locked_ids,
        legal_multi_resource_lock=legal_multi_lock,
        unauthorized_resource_ids=unauthorized_ids,
        excess_resource_ids=excess_ids,
        stale_plan_version=stale_plan,
        stale_coalition_version=stale_coalition,
        conflict_reasons=conflict_reasons,
        metadata={
            "coordination_mode": coordination_mode or "independent",
            "raw_duplicate_lock": _raw_duplicate_lock(
                terminal_association, cross_view_summary
            ),
            "assignment_resource_ids": list(assignment_ids),
            "member_resource_ids": list(member_ids),
        },
    )


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
        for key in ("locked_resource_ids", "duplicate_lock_resource_ids"):
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
