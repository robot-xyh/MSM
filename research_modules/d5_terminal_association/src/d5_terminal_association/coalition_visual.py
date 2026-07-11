"""Read-only coalition visual completion summaries for D3/main consumers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .models import TerminalAssociation, TerminalObservation


_AUTHORIZED_STATES = {
    "authorized",
    "approved",
    "human_approved",
    "operator_approved",
    "recorded",
}
_ACTIVE_STATES = {"active", "activated", "authorized", "committed", "executing"}
_PRIMARY_ROLES = {"primary"}
_RESERVE_ROLES = {"reserve", "retry"}


@dataclass(frozen=True)
class CoalitionVisualSummary:
    """Passive M-to-N visual completion state for one versioned coalition.

    The summary references only the center-owned global track ID carried by the
    bindings and terminal associations. It never creates or rewrites an ID.
    """

    global_track_id: str
    plan_id: str | None
    plan_version: int | None
    coalition_id: str | None
    coalition_version: int | None
    coordination_mode: str
    primary_required_count: int
    primary_locked_resource_ids: tuple[str, ...]
    primary_lock_complete: bool
    reserve_ready_resource_ids: tuple[str, ...]
    coalition_visual_consensus: bool
    planned_cooperative_lock: bool = False
    duplicate_terminal_lock_risk: bool = False
    coalition_conflict_state: str = "none"
    excess_lock_resource_ids: tuple[str, ...] = ()
    stable_lock_frame_count_by_resource: Mapping[str, int] = field(default_factory=dict)
    visual_png_authorized_resource_ids: tuple[str, ...] = ()
    reason: str = "primary_lock_incomplete"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.global_track_id:
            raise ValueError("global_track_id must be non-empty")
        if int(self.primary_required_count) < 1:
            raise ValueError("primary_required_count must be at least 1")
        object.__setattr__(self, "primary_required_count", int(self.primary_required_count))
        for name in (
            "primary_locked_resource_ids",
            "reserve_ready_resource_ids",
            "excess_lock_resource_ids",
            "visual_png_authorized_resource_ids",
        ):
            object.__setattr__(self, name, _unique(getattr(self, name)))
        object.__setattr__(
            self,
            "stable_lock_frame_count_by_resource",
            {
                str(resource_id): max(0, int(count))
                for resource_id, count in self.stable_lock_frame_count_by_resource.items()
            },
        )
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class _Binding:
    resource_id: str
    global_track_id: str
    plan_id: str | None
    plan_version: int | None
    coalition_id: str | None
    coalition_version: int | None
    member_role: str
    coordination_mode: str
    primary_resource_count: int
    required_resource_count: int
    authorization_state: str
    activation_state: str

    @property
    def contract(self) -> tuple[Any, ...]:
        return (
            self.global_track_id,
            self.plan_id,
            self.plan_version,
            self.coalition_id,
            self.coalition_version,
            self.coordination_mode,
            self.primary_resource_count,
            self.required_resource_count,
        )


@dataclass(frozen=True)
class _Evidence:
    association: TerminalAssociation
    resource_id: str
    timestamp: float
    frame_index: int | None
    frame_key: str
    input_order: int
    has_own_local_detection: bool

    @property
    def visual_match_locked(self) -> bool:
        state = self.association.metadata.get(
            "visual_match_decision_state",
            self.association.decision_state,
        )
        return str(state).strip().lower() == "locked"

    @property
    def execution_locked(self) -> bool:
        return (
            self.association.decision_state == "locked"
            and self.visual_match_locked
            and self.has_own_local_detection
            and self.association.authorization_state.lower() in _AUTHORIZED_STATES
            and self.association.activation_state in _ACTIVE_STATES
            and bool(self.association.metadata.get("execution_gate_pass", True))
        )


def summarize_coalition_visual_completion(
    coalition_bindings: Iterable[Any],
    current_associations: Iterable[TerminalAssociation | TerminalObservation],
    historical_associations: Iterable[TerminalAssociation | TerminalObservation] = (),
    *,
    required_stable_frames: int = 2,
) -> CoalitionVisualSummary:
    """Summarize primary completion and reserve readiness for one coalition.

    `coalition_bindings` accepts D3 ``AssignmentGuidanceBinding`` instances or
    equivalent mappings. Standby reserve visual matches are readiness evidence
    only; they never contribute to primary completion or visual-PNG authority.
    """

    if int(required_stable_frames) < 1:
        raise ValueError("required_stable_frames must be at least 1")
    raw_bindings = tuple(coalition_bindings)
    if not raw_bindings:
        raise ValueError("coalition_bindings must not be empty")
    bindings = tuple(
        _normalize_binding(binding, coalition_size_hint=len(raw_bindings))
        for binding in raw_bindings
    )

    first = bindings[0]
    by_resource: dict[str, _Binding] = {}
    binding_conflict = False
    for binding in bindings:
        previous = by_resource.get(binding.resource_id)
        if previous is not None and previous != binding:
            binding_conflict = True
        by_resource[binding.resource_id] = binding
        if binding.contract != first.contract:
            binding_conflict = True

    primary_bindings = tuple(
        binding for binding in bindings if binding.member_role in _PRIMARY_ROLES
    )
    reserve_bindings = tuple(
        binding for binding in bindings if binding.member_role in _RESERVE_ROLES
    )
    primary_required_count = first.primary_resource_count
    inactive_primary_ids = _unique(
        binding.resource_id
        for binding in primary_bindings
        if not _binding_execution_active(binding)
    )
    primary_contract_incomplete = len(_unique(b.resource_id for b in primary_bindings)) != primary_required_count

    current_input = tuple(
        _normalize_evidence(item, input_order=index)
        for index, item in enumerate(current_associations)
    )
    explicit_history = tuple(
        _normalize_evidence(item, input_order=index)
        for index, item in enumerate(historical_associations)
    )
    current, earlier_current = _latest_resource_frames(current_input)
    history = (*explicit_history, *earlier_current)

    version_conflict_ids: list[str] = []
    unexpected_lock_ids: list[str] = []
    current_execution_locks: dict[str, list[_Evidence]] = defaultdict(list)
    current_visual_matches: dict[str, list[_Evidence]] = defaultdict(list)
    for evidence in current:
        association = evidence.association
        if association.assigned_global_track_id != first.global_track_id:
            continue
        binding = by_resource.get(evidence.resource_id)
        if binding is None:
            if evidence.execution_locked:
                unexpected_lock_ids.append(evidence.resource_id)
            continue
        if not _association_matches_binding(association, binding):
            version_conflict_ids.append(evidence.resource_id)
            continue
        if evidence.visual_match_locked and evidence.has_own_local_detection:
            current_visual_matches[evidence.resource_id].append(evidence)
        if evidence.execution_locked:
            current_execution_locks[evidence.resource_id].append(evidence)

    stable_counts: dict[str, int] = {}
    primary_locked_ids: list[str] = []
    for binding in primary_bindings:
        resource_id = binding.resource_id
        current_locked = bool(current_execution_locks.get(resource_id))
        count = _stable_lock_count(
            binding,
            current_execution_locks.get(resource_id, ()),
            history,
        )
        stable_counts[resource_id] = count
        if current_locked:
            primary_locked_ids.append(resource_id)

    reserve_ready_ids = _unique(
        binding.resource_id
        for binding in reserve_bindings
        if current_visual_matches.get(binding.resource_id)
        and not current_execution_locks.get(binding.resource_id)
    )

    duplicate_local_lock_ids = _unique(
        resource_id
        for resource_id, evidence in current_execution_locks.items()
        if len({item.association.local_track_id for item in evidence}) > 1
    )
    executing_resource_ids = _unique(current_execution_locks)
    excess_ids = _unique(
        (*unexpected_lock_ids, *executing_resource_ids[first.required_resource_count :])
    )
    over_demand = len(executing_resource_ids) > first.required_resource_count or bool(unexpected_lock_ids)

    conflict_state = "none"
    if binding_conflict:
        conflict_state = "coalition_or_plan_version_mismatch"
    elif version_conflict_ids:
        conflict_state = "coalition_or_plan_version_mismatch"
    elif primary_contract_incomplete:
        conflict_state = "primary_binding_count_mismatch"
    elif inactive_primary_ids:
        conflict_state = "primary_binding_not_execution_authorized"
    elif over_demand:
        conflict_state = "member_count_exceeds_demand"
    elif duplicate_local_lock_ids:
        conflict_state = "resource_multiple_local_locks"

    primary_complete = bool(
        conflict_state == "none"
        and len(_unique(primary_locked_ids)) == primary_required_count
        and all(
            stable_counts.get(binding.resource_id, 0) >= required_stable_frames
            for binding in primary_bindings
        )
    )
    consensus = primary_complete
    duplicate_risk = conflict_state in {
        "coalition_or_plan_version_mismatch",
        "member_count_exceeds_demand",
        "resource_multiple_local_locks",
    }
    planned_lock = bool(
        conflict_state == "none"
        and len(executing_resource_ids) > 1
        and len(executing_resource_ids) <= first.required_resource_count
    )

    if consensus:
        reason = "coalition_visual_consensus"
    elif conflict_state != "none":
        reason = conflict_state
    elif not primary_locked_ids:
        reason = "no_primary_visual_lock"
    elif any(count < required_stable_frames for count in stable_counts.values()):
        reason = "primary_lock_stability_incomplete"
    else:
        reason = "primary_lock_incomplete"

    return CoalitionVisualSummary(
        global_track_id=first.global_track_id,
        plan_id=first.plan_id,
        plan_version=first.plan_version,
        coalition_id=first.coalition_id,
        coalition_version=first.coalition_version,
        coordination_mode=first.coordination_mode,
        primary_required_count=primary_required_count,
        primary_locked_resource_ids=_unique(primary_locked_ids),
        primary_lock_complete=primary_complete,
        reserve_ready_resource_ids=reserve_ready_ids,
        coalition_visual_consensus=consensus,
        planned_cooperative_lock=planned_lock,
        duplicate_terminal_lock_risk=duplicate_risk,
        coalition_conflict_state=conflict_state,
        excess_lock_resource_ids=excess_ids,
        stable_lock_frame_count_by_resource=stable_counts,
        visual_png_authorized_resource_ids=(
            _unique(primary_locked_ids) if primary_complete else ()
        ),
        reason=reason,
        metadata={
            "required_stable_frames": int(required_stable_frames),
            "binding_resource_ids": _unique(binding.resource_id for binding in bindings),
            "primary_resource_ids": _unique(binding.resource_id for binding in primary_bindings),
            "reserve_resource_ids": _unique(binding.resource_id for binding in reserve_bindings),
            "inactive_primary_resource_ids": inactive_primary_ids,
            "version_conflict_resource_ids": _unique(version_conflict_ids),
            "unexpected_lock_resource_ids": _unique(unexpected_lock_ids),
            "duplicate_local_lock_resource_ids": duplicate_local_lock_ids,
            "reserve_visual_png_authorized": False,
            "secondary_cue_policy": "search_or_registration_only",
            "global_id_policy": "existing_assigned_global_track_id_only",
        },
    )


def _normalize_binding(value: Any, *, coalition_size_hint: int) -> _Binding:
    resource_id = _text(_read(value, "resource_id", "assigned_resource_id", "owner"))
    global_track_id = _text(
        _read(value, "assigned_global_track_id", "global_track_id", "target_id")
    )
    if not resource_id or not global_track_id:
        raise ValueError("each coalition binding requires resource_id and assigned_global_track_id")
    member_role = _text(_read(value, "member_role", default="primary")).lower()
    coordination_mode = _text(
        _read(value, "coordination_mode", default="independent")
    ).lower()
    primary_count = int(_read(value, "primary_resource_count", default=1))
    required_count = int(
        _read(
            value,
            "required_resource_count",
            default=_binding_count_hint(value, coalition_size_hint),
        )
    )
    if primary_count < 1 or required_count < primary_count:
        raise ValueError("binding resource counts are inconsistent")
    activation_state = _text(
        _read(value, "activation_state", "binding_state", default="active")
    ).lower()
    return _Binding(
        resource_id=resource_id,
        global_track_id=global_track_id,
        plan_id=_optional_text(_read(value, "plan_id")),
        plan_version=_optional_int(_read(value, "plan_version", "version")),
        coalition_id=_optional_text(_read(value, "coalition_id")),
        coalition_version=_optional_int(_read(value, "coalition_version")),
        member_role=member_role,
        coordination_mode=coordination_mode,
        primary_resource_count=primary_count,
        required_resource_count=required_count,
        authorization_state=_text(
            _read(value, "authorization_state", "human_authorization_state", default="authorized")
        ).lower(),
        activation_state=activation_state,
    )


def _binding_count_hint(value: Any, fallback: int) -> int:
    metadata = _metadata(value)
    if "required_resource_count" in metadata:
        return int(metadata["required_resource_count"])
    return fallback


def _normalize_evidence(
    value: TerminalAssociation | TerminalObservation,
    *,
    input_order: int,
) -> _Evidence:
    if isinstance(value, TerminalObservation):
        association = value.terminal_association
        if association is None:
            raise ValueError("TerminalObservation must carry terminal_association")
        resource_id = value.resource_id
        timestamp = value.timestamp
        frame_id = value.frame_id
        local_track_matches = (
            value.local_track is None
            or association.local_track_id == value.local_track.local_track_id
        )
        observation_metadata = value.metadata
    elif isinstance(value, TerminalAssociation):
        association = value
        resource_id = association.resource_id or _text(
            association.metadata.get("resource_id", "")
        )
        timestamp = float(
            association.metadata.get(
                "projection_timestamp",
                association.metadata.get("measurement_timestamp", input_order),
            )
        )
        frame_id = association.metadata.get("frame_id")
        local_track_matches = True
        observation_metadata = {}
    else:
        raise TypeError("association evidence must be TerminalAssociation or TerminalObservation")
    if not resource_id:
        raise ValueError("association evidence requires resource_id")
    if association.resource_id not in {None, resource_id}:
        local_track_matches = False
    metadata = {**observation_metadata, **association.metadata}
    frame_index = _optional_int(metadata.get("frame_index"))
    frame_key = str(frame_index if frame_index is not None else frame_id or timestamp)
    return _Evidence(
        association=association,
        resource_id=resource_id,
        timestamp=float(timestamp),
        frame_index=frame_index,
        frame_key=frame_key,
        input_order=input_order,
        has_own_local_detection=bool(
            association.local_track_id
            and local_track_matches
            and _local_detection_scope_matches(metadata, resource_id)
        ),
    )


def _local_detection_scope_matches(metadata: Mapping[str, Any], resource_id: str) -> bool:
    if bool(metadata.get("borrowed_bbox", False)):
        return False
    for key in (
        "measurement_resource_id",
        "detection_resource_id",
        "bbox_resource_id",
        "local_detection_resource_id",
    ):
        value = metadata.get(key)
        if value is not None and str(value) != resource_id:
            return False
    measurement_camera = metadata.get("measurement_camera_id")
    projection_camera = metadata.get("projection_camera_id")
    return not (
        measurement_camera is not None
        and projection_camera is not None
        and str(measurement_camera) != str(projection_camera)
    )


def _association_matches_binding(association: TerminalAssociation, binding: _Binding) -> bool:
    return bool(
        association.assigned_global_track_id == binding.global_track_id
        and association.resource_id in {None, binding.resource_id}
        and association.plan_id == binding.plan_id
        and association.plan_version == binding.plan_version
        and association.coalition_id == binding.coalition_id
        and association.coalition_version == binding.coalition_version
        and association.member_role == binding.member_role
        and association.required_resource_count == binding.required_resource_count
        and association.coordination_mode == binding.coordination_mode
    )


def _binding_execution_active(binding: _Binding) -> bool:
    return bool(
        binding.authorization_state in _AUTHORIZED_STATES
        and binding.activation_state in _ACTIVE_STATES
    )


def _latest_resource_frames(
    evidence_items: tuple[_Evidence, ...],
) -> tuple[tuple[_Evidence, ...], tuple[_Evidence, ...]]:
    latest_tokens: dict[str, tuple[float, int]] = {}
    for evidence in evidence_items:
        token = _frame_order_token(evidence)
        if token > latest_tokens.get(evidence.resource_id, (float("-inf"), -1)):
            latest_tokens[evidence.resource_id] = token
    current: list[_Evidence] = []
    earlier: list[_Evidence] = []
    for evidence in evidence_items:
        target = current if _frame_order_token(evidence) == latest_tokens[evidence.resource_id] else earlier
        target.append(evidence)
    return tuple(current), tuple(earlier)


def _frame_order_token(evidence: _Evidence) -> tuple[float, int]:
    return (
        evidence.timestamp,
        evidence.frame_index if evidence.frame_index is not None else -1,
    )


def _stable_lock_count(
    binding: _Binding,
    current_locks: Iterable[_Evidence],
    history: Iterable[_Evidence],
) -> int:
    current_frames = _frame_states(current_locks, binding)
    if not current_frames:
        return 0
    current = current_frames[-1]
    count = 1
    previous = current
    historical_frames = _frame_states(
        (
            evidence
            for evidence in history
            if evidence.resource_id == binding.resource_id
            and _association_matches_binding(evidence.association, binding)
        ),
        binding,
    )
    for frame in reversed(historical_frames):
        if frame[0] == current[0]:
            continue
        if previous[1] is not None and frame[1] is not None and frame[1] != previous[1] - 1:
            break
        if not frame[3]:
            break
        count += 1
        previous = frame
    return count


def _frame_states(
    evidence_items: Iterable[_Evidence],
    binding: _Binding,
) -> list[tuple[str, int | None, float, bool]]:
    grouped: dict[str, list[_Evidence]] = defaultdict(list)
    for evidence in evidence_items:
        if evidence.resource_id != binding.resource_id:
            continue
        grouped[evidence.frame_key].append(evidence)
    frames = [
        (
            key,
            next((item.frame_index for item in items if item.frame_index is not None), None),
            max(item.timestamp for item in items),
            any(item.execution_locked for item in items),
        )
        for key, items in grouped.items()
    ]
    return sorted(frames, key=lambda item: (item[2], item[1] if item[1] is not None else -1, item[0]))


def _read(value: Any, *names: str, default: Any = None) -> Any:
    metadata = _metadata(value)
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
        if name in metadata:
            return metadata[name]
    return default


def _metadata(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        metadata = value.get("metadata", {})
    else:
        metadata = getattr(value, "metadata", {})
    return metadata if isinstance(metadata, Mapping) else {}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _unique(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if value is not None and str(value)))
