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
_COMMITTED_STATES = {"committed", "executing"}


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
    coalition_commit_required: bool = False
    coalition_commit_valid: bool = True
    coalition_commit_state: str | None = None
    coalition_commit_epoch: int | None = None
    coalition_commit_lease_expires_at_s: float | None = None
    coalition_commit_required_member_ids: tuple[str, ...] = ()
    coalition_commit_acked_member_ids: tuple[str, ...] = ()
    coalition_commit_conflict_reasons: tuple[str, ...] = ()
    coalition_execution_state: str = "cue_only"
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
            "coalition_commit_required_member_ids",
            "coalition_commit_acked_member_ids",
            "coalition_commit_conflict_reasons",
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
    target_id: str
    plan_id: str | None
    plan_version: int | None
    plan_owner: str | None
    owner_node_id: str | None
    coalition_id: str | None
    coalition_version: int | None
    member_role: str
    coordination_mode: str
    primary_resource_count: int
    required_resource_count: int
    authorization_state: str
    activation_state: str
    coalition_epoch: int | None

    @property
    def contract(self) -> tuple[Any, ...]:
        return (
            self.global_track_id,
            self.target_id,
            self.plan_id,
            self.plan_version,
            self.plan_owner,
            self.owner_node_id,
            self.coalition_id,
            self.coalition_version,
            self.coordination_mode,
            self.primary_resource_count,
            self.required_resource_count,
            self.coalition_epoch,
        )


@dataclass(frozen=True)
class _CoalitionCommit:
    state: str
    epoch: int | None
    expected_epoch: int | None
    lease_expires_at_s: float | None
    coalition_id: str | None
    coalition_version: int | None
    plan_id: str | None
    plan_version: int | None
    required_member_ids: tuple[str, ...]
    acked_member_ids: tuple[str, ...]
    center_failed: bool
    fallback_active: bool


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


@dataclass(frozen=True)
class _StabilityState:
    count: int
    continued_across_plan_version: bool = False
    reset_reason: str | None = None
    stale_plan_replay: bool = False
    source_plan_versions: tuple[int, ...] = ()


def summarize_coalition_visual_completion(
    coalition_bindings: Iterable[Any],
    current_associations: Iterable[TerminalAssociation | TerminalObservation],
    historical_associations: Iterable[TerminalAssociation | TerminalObservation] = (),
    *,
    required_stable_frames: int = 2,
    historical_bindings: Iterable[Any] = (),
    invalid_historical_plan_versions: Iterable[int] = (),
    coalition_commit: Any | None = None,
    current_time_s: float | None = None,
    center_failed: bool = False,
    fallback_active: bool = False,
) -> CoalitionVisualSummary:
    """Summarize primary completion and reserve readiness for one coalition.

    `coalition_bindings` accepts D3 ``AssignmentGuidanceBinding`` instances or
    equivalent mappings. `coalition_commit` accepts D4 dict/object summaries.
    Standby reserve visual matches are readiness evidence only; they never
    contribute to primary completion or visual-PNG authority.
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
    historical_binding_snapshots = tuple(
        _normalize_binding(binding, coalition_size_hint=len(raw_bindings))
        for binding in historical_bindings
    )
    invalid_history_versions = frozenset(
        int(version) for version in invalid_historical_plan_versions
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

    normalized_commit = (
        _normalize_coalition_commit(coalition_commit)
        if coalition_commit is not None
        else None
    )
    commit_required = bool(
        first.required_resource_count > 1
        and (
            normalized_commit is not None
            or center_failed
            or fallback_active
            or (normalized_commit is not None and normalized_commit.center_failed)
            or (normalized_commit is not None and normalized_commit.fallback_active)
        )
    )
    evidence_time_s = _effective_evaluation_time(current_time_s, current)
    commit_conflict_reasons = _coalition_commit_conflicts(
        normalized_commit,
        bindings=bindings,
        commit_required=commit_required,
        evaluation_time_s=evidence_time_s,
    )

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

    duplicate_local_lock_ids = _unique(
        resource_id
        for resource_id, evidence in current_execution_locks.items()
        if len({item.association.local_track_id for item in evidence}) > 1
    )
    current_continuity_unsafe_ids = _unique(
        resource_id
        for resource_id, evidence_items in current_execution_locks.items()
        if any(not _evidence_safe_for_continuity(item) for item in evidence_items)
    )

    stable_counts: dict[str, int] = {}
    stability_states: dict[str, _StabilityState] = {}
    primary_locked_ids: list[str] = []
    for binding in primary_bindings:
        resource_id = binding.resource_id
        current_locked = bool(current_execution_locks.get(resource_id))
        stability = _stable_lock_state(
            binding,
            current_execution_locks.get(resource_id, ()),
            history,
            bindings,
            historical_binding_snapshots,
            invalid_historical_plan_versions=invalid_history_versions,
            allow_cross_version_continuity=bool(
                not commit_conflict_reasons
                and not binding_conflict
                and resource_id not in version_conflict_ids
                and resource_id not in duplicate_local_lock_ids
                and resource_id not in current_continuity_unsafe_ids
            ),
        )
        stability_states[resource_id] = stability
        stable_counts[resource_id] = stability.count
        if current_locked:
            primary_locked_ids.append(resource_id)

    reserve_ready_ids = _unique(
        binding.resource_id
        for binding in reserve_bindings
        if current_visual_matches.get(binding.resource_id)
        and not current_execution_locks.get(binding.resource_id)
    )

    stale_plan_replay_ids = _unique(
        resource_id
        for resource_id, state in stability_states.items()
        if state.stale_plan_replay
    )
    executing_resource_ids = _unique(current_execution_locks)
    excess_ids = _unique(
        (*unexpected_lock_ids, *executing_resource_ids[first.required_resource_count :])
    )
    over_demand = len(executing_resource_ids) > first.required_resource_count or bool(unexpected_lock_ids)

    conflict_state = "none"
    if commit_conflict_reasons:
        conflict_state = commit_conflict_reasons[0]
    elif stale_plan_replay_ids:
        conflict_state = "plan_version_not_strictly_monotonic"
    elif binding_conflict:
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
    elif current_continuity_unsafe_ids:
        conflict_state = "primary_continuity_safety_conflict"

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
        coalition_commit_required=commit_required,
        coalition_commit_valid=not commit_conflict_reasons,
        coalition_commit_state=(normalized_commit.state if normalized_commit else None),
        coalition_commit_epoch=(normalized_commit.epoch if normalized_commit else None),
        coalition_commit_lease_expires_at_s=(
            normalized_commit.lease_expires_at_s if normalized_commit else None
        ),
        coalition_commit_required_member_ids=(
            normalized_commit.required_member_ids if normalized_commit else ()
        ),
        coalition_commit_acked_member_ids=(
            normalized_commit.acked_member_ids if normalized_commit else ()
        ),
        coalition_commit_conflict_reasons=commit_conflict_reasons,
        coalition_execution_state=(
            "authorized" if consensus else "hold" if conflict_state != "none" else "cue_only"
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
            "current_continuity_unsafe_resource_ids": current_continuity_unsafe_ids,
            "stale_plan_replay_resource_ids": stale_plan_replay_ids,
            "stability_continued_across_plan_version_resource_ids": _unique(
                resource_id
                for resource_id, state in stability_states.items()
                if state.continued_across_plan_version
            ),
            "stability_reset_reason_by_resource": {
                resource_id: state.reset_reason
                for resource_id, state in stability_states.items()
                if state.reset_reason is not None
            },
            "stability_source_plan_versions_by_resource": {
                resource_id: list(state.source_plan_versions)
                for resource_id, state in stability_states.items()
            },
            "reserve_visual_png_authorized": False,
            "secondary_cue_policy": "search_or_registration_only",
            "global_id_policy": "existing_assigned_global_track_id_only",
            "coalition_commit_required": commit_required,
            "coalition_commit_valid": not commit_conflict_reasons,
            "coalition_commit_evaluation_time_s": evidence_time_s,
            "coalition_commit_conflict_reasons": commit_conflict_reasons,
            "coalition_execution_state": (
                "authorized"
                if consensus
                else "hold"
                if conflict_state != "none"
                else "cue_only"
            ),
        },
    )


def _normalize_binding(value: Any, *, coalition_size_hint: int) -> _Binding:
    resource_id = _text(_read(value, "resource_id", "assigned_resource_id", "owner"))
    global_track_id = _text(
        _read(value, "assigned_global_track_id", "global_track_id", "target_id")
    )
    if not resource_id or not global_track_id:
        raise ValueError("each coalition binding requires resource_id and assigned_global_track_id")
    target_id = _text(_read(value, "target_id", default=global_track_id)) or global_track_id
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
        target_id=target_id,
        plan_id=_optional_text(_read(value, "plan_id")),
        plan_version=_optional_int(_read(value, "plan_version", "version")),
        plan_owner=_optional_text(
            _read(value, "active_plan_owner", "plan_owner", "current_plan_owner")
        ),
        owner_node_id=_optional_text(
            _read(value, "owner_node_id", "current_plan_owner_node_id")
        ),
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
        coalition_epoch=_optional_int(
            _read(
                value,
                "coalition_epoch",
                "required_epoch",
                "lease_epoch",
                "secondary_leader_epoch",
                "epoch",
            )
        ),
    )


def snapshot_coalition_bindings(coalition_bindings: Iterable[Any]) -> tuple[_Binding, ...]:
    """Freeze duck-typed bindings for later continuity checks."""

    raw_bindings = tuple(coalition_bindings)
    return tuple(
        _normalize_binding(binding, coalition_size_hint=len(raw_bindings))
        for binding in raw_bindings
    )


def _normalize_coalition_commit(value: Any) -> _CoalitionCommit:
    lease = _read(value, "lease")
    nested_lease_expiry = (
        lease
        if isinstance(lease, (int, float))
        else _read(
            lease,
            "expires_at_s",
            "lease_expires_at_s",
            "expiry_s",
            "expiry",
            "valid_until_s",
        )
    )
    lease_expires_at_s = _optional_float(
        _read(
            value,
            "lease_expires_at_s",
            "lease_expiry_s",
            "lease_expiry",
            "lease_deadline_s",
            default=nested_lease_expiry,
        )
    )
    required_members = _member_ids(
        _read(value, "required_member_ids", "required_members", "members", default=())
    )
    acked_members = _member_ids(
        _read(value, "acked_member_ids", "acked_members", "member_acks", "acks", default=()),
        require_positive_ack=True,
    )
    return _CoalitionCommit(
        state=_text(_read(value, "state", "commit_state", "status")).lower(),
        epoch=_optional_int(_read(value, "epoch", "coalition_epoch", "lease_epoch")),
        expected_epoch=_optional_int(
            _read(value, "required_epoch", "expected_epoch", "current_epoch")
        ),
        lease_expires_at_s=lease_expires_at_s,
        coalition_id=_optional_text(_read(value, "coalition_id")),
        coalition_version=_optional_int(_read(value, "coalition_version")),
        plan_id=_optional_text(_read(value, "plan_id")),
        plan_version=_optional_int(_read(value, "plan_version", "version")),
        required_member_ids=required_members,
        acked_member_ids=acked_members,
        center_failed=bool(_read(value, "center_failed", default=False)),
        fallback_active=bool(
            _read(value, "fallback_active", "fallback", "is_fallback", default=False)
        ),
    )


def _coalition_commit_conflicts(
    commit: _CoalitionCommit | None,
    *,
    bindings: tuple[_Binding, ...],
    commit_required: bool,
    evaluation_time_s: float | None,
) -> tuple[str, ...]:
    if not commit_required:
        return ()
    if commit is None:
        return ("coalition_commit_missing",)

    first = bindings[0]
    reasons: list[str] = []
    if commit.state not in _COMMITTED_STATES:
        reasons.append("coalition_commit_not_committed")
    if commit.coalition_id != first.coalition_id:
        reasons.append("coalition_commit_coalition_id_mismatch")
    if commit.coalition_version != first.coalition_version:
        reasons.append("coalition_commit_coalition_version_mismatch")
    if commit.plan_id != first.plan_id:
        reasons.append("coalition_commit_plan_id_mismatch")
    if commit.plan_version != first.plan_version:
        reasons.append("coalition_commit_plan_version_mismatch")

    binding_epochs = {
        binding.coalition_epoch
        for binding in bindings
        if binding.coalition_epoch is not None
    }
    expected_epoch = commit.expected_epoch
    if len(binding_epochs) > 1:
        reasons.append("coalition_commit_binding_epoch_conflict")
    elif binding_epochs:
        expected_epoch = next(iter(binding_epochs))
    if commit.epoch is None:
        reasons.append("coalition_commit_epoch_missing")
    elif expected_epoch is not None and commit.epoch != expected_epoch:
        reasons.append("coalition_commit_epoch_mismatch")

    if commit.lease_expires_at_s is None:
        reasons.append("coalition_commit_lease_missing")
    elif evaluation_time_s is None:
        reasons.append("coalition_commit_evaluation_time_missing")
    elif evaluation_time_s > commit.lease_expires_at_s:
        reasons.append("coalition_commit_lease_expired")

    binding_member_ids = set(_unique(binding.resource_id for binding in bindings))
    required_member_ids = set(commit.required_member_ids)
    acked_member_ids = set(commit.acked_member_ids)
    if not required_member_ids:
        reasons.append("coalition_commit_required_members_missing")
    elif (
        required_member_ids != binding_member_ids
        or len(required_member_ids) != first.required_resource_count
    ):
        reasons.append("coalition_commit_required_members_mismatch")
    if not required_member_ids.issubset(acked_member_ids):
        reasons.append("coalition_commit_member_ack_incomplete")
    return _unique(reasons)


def _effective_evaluation_time(
    current_time_s: float | None,
    current_evidence: Iterable[_Evidence],
) -> float | None:
    if current_time_s is not None:
        return float(current_time_s)
    timestamps = [evidence.timestamp for evidence in current_evidence]
    return max(timestamps) if timestamps else None


def _member_ids(values: Any, *, require_positive_ack: bool = False) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, Mapping):
        if any(key in values for key in ("member_id", "resource_id", "node_id", "id")):
            iterable: Iterable[Any] = (values,)
        else:
            keyed_values: list[Any] = []
            for member_id, member_value in values.items():
                if isinstance(member_value, Mapping):
                    member_record = dict(member_value)
                    member_record.setdefault("member_id", member_id)
                    keyed_values.append(member_record)
                elif hasattr(member_value, "member_id"):
                    keyed_values.append(member_value)
                else:
                    keyed_values.append(
                        {
                            "member_id": member_id,
                            "accepted": bool(member_value),
                            "ack_state": (
                                member_value if isinstance(member_value, str) else "acked"
                            ),
                        }
                    )
            iterable = keyed_values
    elif isinstance(values, (str, bytes)):
        iterable = (values,)
    else:
        try:
            iterable = tuple(values)
        except TypeError:
            iterable = (values,)

    member_ids: list[str] = []
    for item in iterable:
        if require_positive_ack and not isinstance(item, (str, bytes)):
            ack_state = _text(
                _read(item, "ack_state", "state", "status", default="acked")
            ).lower()
            accepted = bool(_read(item, "accepted", "acknowledged", default=True))
            if not accepted or ack_state in {"rejected", "expired", "stale", "nack"}:
                continue
        member_id = (
            _text(item)
            if isinstance(item, (str, bytes))
            else _text(_read(item, "member_id", "resource_id", "node_id", "id"))
        )
        if member_id:
            member_ids.append(member_id)
    return _unique(member_ids)


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


def _stable_lock_state(
    binding: _Binding,
    current_locks: Iterable[_Evidence],
    history: Iterable[_Evidence],
    current_bindings: tuple[_Binding, ...],
    historical_bindings: tuple[_Binding, ...],
    *,
    invalid_historical_plan_versions: frozenset[int],
    allow_cross_version_continuity: bool,
) -> _StabilityState:
    current_frames = _frame_states(current_locks, binding)
    if not current_frames:
        return _StabilityState(count=0)
    current = current_frames[-1]
    count = 1
    previous = current
    source_versions: list[int] = []
    if binding.plan_version is not None:
        source_versions.append(binding.plan_version)

    resource_history = tuple(
        evidence for evidence in history if evidence.resource_id == binding.resource_id
    )
    historical_versions = tuple(
        historical_binding.plan_version
        for historical_binding in historical_bindings
        if historical_binding.resource_id == binding.resource_id
        and historical_binding.global_track_id == binding.global_track_id
        and historical_binding.target_id == binding.target_id
        and historical_binding.coalition_id == binding.coalition_id
        and historical_binding.plan_version is not None
    )
    if (
        binding.plan_version is not None
        and historical_versions
        and max(historical_versions) > binding.plan_version
    ):
        return _StabilityState(
            count=1,
            reset_reason="stale_plan_version_replay",
            stale_plan_replay=True,
            source_plan_versions=tuple(source_versions),
        )

    grouped_history = _group_evidence_frames(resource_history)
    later_binding = binding
    continued = False
    reset_reason: str | None = None
    for frame in reversed(grouped_history):
        if frame[0] == current[0]:
            continue
        if previous[1] is not None and frame[1] is not None and frame[1] != previous[1] - 1:
            reset_reason = "non_consecutive_frame"
            break
        evidence, historical_binding, reason = _select_continuity_evidence(
            frame[4],
            current_binding=binding,
            later_binding=later_binding,
            current_bindings=current_bindings,
            historical_bindings=historical_bindings,
            invalid_historical_plan_versions=invalid_historical_plan_versions,
            allow_cross_version_continuity=allow_cross_version_continuity,
        )
        if evidence is None or historical_binding is None:
            reset_reason = reason or "historical_lock_not_eligible"
            break
        if historical_binding.plan_version != later_binding.plan_version:
            continued = True
        count += 1
        if historical_binding.plan_version is not None:
            source_versions.append(historical_binding.plan_version)
        previous = frame
        later_binding = historical_binding
    return _StabilityState(
        count=count,
        continued_across_plan_version=continued,
        reset_reason=reset_reason,
        source_plan_versions=tuple(dict.fromkeys(source_versions)),
    )


def _select_continuity_evidence(
    evidence_items: tuple[_Evidence, ...],
    *,
    current_binding: _Binding,
    later_binding: _Binding,
    current_bindings: tuple[_Binding, ...],
    historical_bindings: tuple[_Binding, ...],
    invalid_historical_plan_versions: frozenset[int],
    allow_cross_version_continuity: bool,
) -> tuple[_Evidence | None, _Binding | None, str | None]:
    locked_items = tuple(
        evidence
        for evidence in evidence_items
        if evidence.execution_locked and _evidence_safe_for_continuity(evidence)
    )
    if not locked_items:
        return None, None, "historical_lock_not_safe"

    reset_reason = "historical_binding_missing"
    for evidence in locked_items:
        association = evidence.association
        if association.plan_version in invalid_historical_plan_versions:
            reset_reason = "historical_plan_version_safety_conflict"
            continue
        historical_binding, binding_reason = _binding_for_historical_association(
            association,
            resource_id=evidence.resource_id,
            historical_bindings=historical_bindings,
            current_binding=current_binding,
        )
        if historical_binding is None:
            reset_reason = binding_reason
            continue
        if not _association_matches_binding(association, historical_binding):
            reset_reason = "historical_association_binding_mismatch"
            continue
        if historical_binding.plan_version == later_binding.plan_version:
            if historical_binding == later_binding:
                return evidence, historical_binding, None
            reset_reason = "same_version_binding_conflict"
            continue
        if not allow_cross_version_continuity:
            reset_reason = "cross_version_continuity_blocked"
            continue
        transition_conflict = _binding_transition_conflict(
            newer=later_binding,
            older=historical_binding,
        )
        if transition_conflict is None:
            transition_conflict = _primary_membership_transition_conflict(
                newer=later_binding,
                older=historical_binding,
                current_bindings=current_bindings,
                historical_bindings=historical_bindings,
            )
        if transition_conflict is None:
            return evidence, historical_binding, None
        reset_reason = transition_conflict
    return None, None, reset_reason


def _binding_for_historical_association(
    association: TerminalAssociation,
    *,
    resource_id: str,
    historical_bindings: tuple[_Binding, ...],
    current_binding: _Binding,
) -> tuple[_Binding | None, str | None]:
    if association.plan_version == current_binding.plan_version:
        return current_binding, None
    candidates = tuple(
        binding
        for binding in historical_bindings
        if binding.resource_id == resource_id
        and binding.plan_id == association.plan_id
        and binding.plan_version == association.plan_version
    )
    unique_candidates = tuple(dict.fromkeys(candidates))
    if not unique_candidates:
        return None, "historical_binding_missing"
    if len(unique_candidates) > 1:
        return None, "historical_binding_ambiguous"
    return unique_candidates[0], None


def _binding_transition_conflict(*, newer: _Binding, older: _Binding) -> str | None:
    if newer.plan_version is None or older.plan_version is None:
        return "plan_version_missing"
    if newer.plan_version <= older.plan_version:
        return "plan_version_not_strictly_monotonic"
    if newer.coalition_version is None or older.coalition_version is None:
        return "coalition_version_missing"
    if newer.coalition_version <= older.coalition_version:
        return "coalition_version_not_strictly_monotonic"
    return _binding_identity_conflict(newer, older)


def _binding_identity_conflict(newer: _Binding, older: _Binding) -> str | None:
    if not newer.plan_owner or not older.plan_owner:
        return "plan_owner_missing"
    if newer.plan_owner != older.plan_owner or newer.owner_node_id != older.owner_node_id:
        return "plan_owner_changed"
    if newer.coalition_epoch != older.coalition_epoch:
        return "coalition_epoch_changed"
    if newer.coalition_id != older.coalition_id:
        return "coalition_id_changed"
    if newer.target_id != older.target_id or newer.global_track_id != older.global_track_id:
        return "resource_target_binding_changed"
    if newer.resource_id != older.resource_id:
        return "resource_changed"
    if newer.member_role != "primary" or older.member_role != "primary":
        return "primary_membership_changed"
    if (
        newer.coordination_mode != older.coordination_mode
        or newer.primary_resource_count != older.primary_resource_count
        or newer.required_resource_count != older.required_resource_count
    ):
        return "coalition_demand_changed"
    if not _binding_execution_active(newer) or not _binding_execution_active(older):
        return "primary_binding_not_execution_authorized"
    return None


def _primary_membership_transition_conflict(
    *,
    newer: _Binding,
    older: _Binding,
    current_bindings: tuple[_Binding, ...],
    historical_bindings: tuple[_Binding, ...],
) -> str | None:
    newer_primary_ids = {
        binding.resource_id
        for binding in current_bindings
        if binding.global_track_id == newer.global_track_id
        and binding.target_id == newer.target_id
        and binding.coalition_id == newer.coalition_id
        and binding.coalition_version == newer.coalition_version
        and binding.member_role == "primary"
    }
    older_primary_ids = {
        binding.resource_id
        for binding in historical_bindings
        if binding.plan_id == older.plan_id
        and binding.plan_version == older.plan_version
        and binding.global_track_id == older.global_track_id
        and binding.target_id == older.target_id
        and binding.coalition_id == older.coalition_id
        and binding.coalition_version == older.coalition_version
        and binding.member_role == "primary"
    }
    if not newer_primary_ids or not older_primary_ids:
        return "primary_membership_history_missing"
    if newer_primary_ids != older_primary_ids:
        return "primary_membership_changed"
    return None


def _evidence_safe_for_continuity(evidence: _Evidence) -> bool:
    association = evidence.association
    metadata = association.metadata
    if association.friend_conflict_state.strip().lower() not in {"", "none"}:
        return False
    if bool(metadata.get("duplicate_terminal_lock_risk", False)):
        return False
    if metadata.get("coalition_commit_valid") is False:
        return False
    if str(metadata.get("coalition_conflict_state", "none")).lower() not in {"", "none"}:
        return False
    if metadata.get("measurement_age_ok") is False:
        return False
    for key in ("assignment_validity_state", "evidence_state", "freshness_state"):
        if str(metadata.get(key, "")).strip().lower() in {
            "expired",
            "revoked",
            "stale",
            "superseded",
        }:
            return False
    return not any(
        bool(metadata.get(key, False))
        for key in (
            "wrong_binding",
            "assignment_mismatch",
            "binding_mismatch",
            "assignment_expired",
            "plan_stale",
            "evidence_expired",
            "stale_evidence",
        )
    )


def _frame_states(
    evidence_items: Iterable[_Evidence],
    binding: _Binding,
) -> list[tuple[str, int | None, float, bool, tuple[_Evidence, ...]]]:
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
            tuple(items),
        )
        for key, items in grouped.items()
    ]
    return sorted(frames, key=lambda item: (item[2], item[1] if item[1] is not None else -1, item[0]))


def _group_evidence_frames(
    evidence_items: Iterable[_Evidence],
) -> list[tuple[str, int | None, float, bool, tuple[_Evidence, ...]]]:
    grouped: dict[str, list[_Evidence]] = defaultdict(list)
    for evidence in evidence_items:
        grouped[evidence.frame_key].append(evidence)
    frames = [
        (
            key,
            next((item.frame_index for item in items if item.frame_index is not None), None),
            max(item.timestamp for item in items),
            any(item.execution_locked for item in items),
            tuple(items),
        )
        for key, items in grouped.items()
    ]
    return sorted(
        frames,
        key=lambda item: (item[2], item[1] if item[1] is not None else -1, item[0]),
    )


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


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _unique(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if value is not None and str(value)))
