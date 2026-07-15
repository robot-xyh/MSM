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
class CooperativeResourceTargetDiagnostic:
    """Read-only visual funnel state for one resource-target binding."""

    resource_id: str
    global_track_id: str
    target_id: str
    plan_id: str | None
    plan_version: int | None
    plan_owner: str | None
    owner_node_id: str | None
    coalition_id: str | None
    coalition_version: int | None
    terminal_authorization_scope: str
    arrival_coordination_required: bool
    member_role: str
    active_primary: bool
    committed_member: bool
    association_contract_matches: bool
    visible: bool
    projected: bool
    gate_accepted: bool
    locked: bool
    stable_lock_frame_count: int
    common_lock_window_participant: bool
    association_confidence: float
    ambiguity_score: float
    friend_conflict_state: str
    decision_state: str
    first_failure_stage: str
    failure_category: str
    reject_reason: str
    measurement_timestamp: float | None = None
    arrival_timestamp: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "global_track_id": self.global_track_id,
            "target_id": self.target_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "plan_owner": self.plan_owner,
            "owner_node_id": self.owner_node_id,
            "coalition_id": self.coalition_id,
            "coalition_version": self.coalition_version,
            "terminal_authorization_scope": self.terminal_authorization_scope,
            "arrival_coordination_required": self.arrival_coordination_required,
            "member_role": self.member_role,
            "active_primary": self.active_primary,
            "committed_member": self.committed_member,
            "association_contract_matches": self.association_contract_matches,
            "visible": self.visible,
            "projected": self.projected,
            "gate_accepted": self.gate_accepted,
            "locked": self.locked,
            "stable_lock_frame_count": self.stable_lock_frame_count,
            "common_lock_window_participant": self.common_lock_window_participant,
            "association_confidence": self.association_confidence,
            "ambiguity_score": self.ambiguity_score,
            "friend_conflict_state": self.friend_conflict_state,
            "decision_state": self.decision_state,
            "first_failure_stage": self.first_failure_stage,
            "failure_category": self.failure_category,
            "reject_reason": self.reject_reason,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "truth_identity_used": False,
        }


@dataclass(frozen=True)
class CooperativeTargetVisualFunnel:
    """Dynamic-resource visual funnel for one center-owned global target."""

    global_track_id: str
    target_id: str
    plan_id: str | None
    plan_version: int | None
    plan_owner: str | None
    owner_node_id: str | None
    coalition_id: str | None
    coalition_version: int | None
    terminal_authorization_scope: str
    arrival_coordination_required: bool
    common_lock_window_required: bool
    primary_required_count: int
    active_primary_resource_ids: tuple[str, ...]
    reserve_resource_ids: tuple[str, ...]
    resource_diagnostics: tuple[CooperativeResourceTargetDiagnostic, ...]
    visible_primary_count: int
    projected_primary_count: int
    gate_accepted_primary_count: int
    locked_primary_count: int
    stable_primary_count: int
    common_lock_frame_count: int
    common_lock_window_start_s: float | None
    common_lock_window_end_s: float | None
    cooperative_completion: bool
    second_primary_resource_id: str | None
    second_primary_first_failure_stage: str | None
    second_primary_failure_category: str | None
    second_primary_reject_reason: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "target_id": self.target_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "plan_owner": self.plan_owner,
            "owner_node_id": self.owner_node_id,
            "coalition_id": self.coalition_id,
            "coalition_version": self.coalition_version,
            "terminal_authorization_scope": self.terminal_authorization_scope,
            "arrival_coordination_required": self.arrival_coordination_required,
            "common_lock_window_required": self.common_lock_window_required,
            "primary_required_count": self.primary_required_count,
            "active_primary_resource_ids": list(self.active_primary_resource_ids),
            "reserve_resource_ids": list(self.reserve_resource_ids),
            "resource_diagnostics": [item.to_dict() for item in self.resource_diagnostics],
            "visible_primary_count": self.visible_primary_count,
            "projected_primary_count": self.projected_primary_count,
            "gate_accepted_primary_count": self.gate_accepted_primary_count,
            "locked_primary_count": self.locked_primary_count,
            "stable_primary_count": self.stable_primary_count,
            "common_lock_frame_count": self.common_lock_frame_count,
            "common_lock_window_start_s": self.common_lock_window_start_s,
            "common_lock_window_end_s": self.common_lock_window_end_s,
            "cooperative_completion": self.cooperative_completion,
            "second_primary_resource_id": self.second_primary_resource_id,
            "second_primary_first_failure_stage": self.second_primary_first_failure_stage,
            "second_primary_failure_category": self.second_primary_failure_category,
            "second_primary_reject_reason": self.second_primary_reject_reason,
            "reason": self.reason,
            "truth_identity_used": False,
        }


@dataclass(frozen=True)
class CooperativeVisualFunnelSummary:
    """Episode/snapshot D5 diagnostics without online truth identity."""

    target_summaries: tuple[CooperativeTargetVisualFunnel, ...]
    resource_binding_count: int
    target_count: int
    active_primary_count: int
    completed_target_count: int
    funnel_counts: Mapping[str, int]
    first_failure_stage_counts: Mapping[str, int]
    failure_category_counts: Mapping[str, int]
    second_primary_first_failure_stage_counts: Mapping[str, int]
    second_primary_failure_category_counts: Mapping[str, int]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "funnel_counts", dict(self.funnel_counts))
        object.__setattr__(
            self,
            "first_failure_stage_counts",
            dict(self.first_failure_stage_counts),
        )
        object.__setattr__(
            self,
            "second_primary_first_failure_stage_counts",
            dict(self.second_primary_first_failure_stage_counts),
        )
        object.__setattr__(
            self,
            "failure_category_counts",
            dict(self.failure_category_counts),
        )
        object.__setattr__(
            self,
            "second_primary_failure_category_counts",
            dict(self.second_primary_failure_category_counts),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_summaries": [item.to_dict() for item in self.target_summaries],
            "resource_binding_count": self.resource_binding_count,
            "target_count": self.target_count,
            "active_primary_count": self.active_primary_count,
            "completed_target_count": self.completed_target_count,
            "funnel_counts": dict(self.funnel_counts),
            "first_failure_stage_counts": dict(self.first_failure_stage_counts),
            "failure_category_counts": dict(self.failure_category_counts),
            "second_primary_first_failure_stage_counts": dict(
                self.second_primary_first_failure_stage_counts
            ),
            "second_primary_failure_category_counts": dict(
                self.second_primary_failure_category_counts
            ),
            "online_truth_use_count": 0,
            "global_track_id_rewrite_count": 0,
            "metadata": dict(self.metadata),
        }


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
    terminal_authorization_scope: str
    arrival_coordination_required: bool

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
            self.terminal_authorization_scope,
            self.arrival_coordination_required,
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
    camera_id: str | None = None

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
    history_key: Mapping[str, Any] = field(default_factory=dict)
    history_signature: Mapping[str, Any] = field(default_factory=dict)
    evidence_source: str = "unavailable"


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
    committed_current_primary_ids = frozenset(
        binding.resource_id
        for binding in primary_bindings
        if _binding_execution_active(binding)
        and (
            not commit_required
            or (
                not commit_conflict_reasons
                and normalized_commit is not None
                and binding.resource_id in normalized_commit.required_member_ids
                and binding.resource_id in normalized_commit.acked_member_ids
            )
        )
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
        member_committed_current = resource_id in committed_current_primary_ids
        current_locked = bool(
            member_committed_current and current_execution_locks.get(resource_id)
        )
        stability = _stable_lock_state(
            binding,
            (
                current_execution_locks.get(resource_id, ())
                if member_committed_current
                else ()
            ),
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
            member_committed_current=member_committed_current,
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
    membership_transition = _primary_membership_transition_diagnostic(
        bindings,
        historical_binding_snapshots,
    )
    current_primary_diagnostics = _current_primary_failure_diagnostics(
        primary_bindings,
        current,
        stable_counts=stable_counts,
        required_stable_frames=int(required_stable_frames),
        commit_conflict_reasons=commit_conflict_reasons,
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
            "committed_current_primary_resource_ids": tuple(
                sorted(committed_current_primary_ids)
            ),
            "uncommitted_current_primary_resource_ids": _unique(
                binding.resource_id
                for binding in primary_bindings
                if binding.resource_id not in committed_current_primary_ids
            ),
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
            "stability_history_key_by_resource": {
                resource_id: dict(state.history_key)
                for resource_id, state in stability_states.items()
            },
            "stability_history_signature_by_resource": {
                resource_id: dict(state.history_signature)
                for resource_id, state in stability_states.items()
            },
            "stability_evidence_source_by_resource": {
                resource_id: state.evidence_source
                for resource_id, state in stability_states.items()
            },
            "reserve_visual_png_authorized": False,
            "secondary_cue_policy": "search_or_registration_only",
            "global_id_policy": "existing_assigned_global_track_id_only",
            "coalition_commit_required": commit_required,
            "coalition_commit_valid": not commit_conflict_reasons,
            "coalition_commit_evaluation_time_s": evidence_time_s,
            "coalition_commit_conflict_reasons": commit_conflict_reasons,
            "primary_membership_transition": membership_transition,
            "current_primary_failure_diagnostics": current_primary_diagnostics,
            "coalition_execution_state": (
                "authorized"
                if consensus
                else "hold"
                if conflict_state != "none"
                else "cue_only"
            ),
        },
    )


def summarize_cooperative_visual_funnel(
    coalition_bindings: Iterable[Any],
    current_associations: Iterable[TerminalAssociation | TerminalObservation],
    historical_associations: Iterable[TerminalAssociation | TerminalObservation] = (),
    *,
    required_stable_frames: int = 2,
    historical_bindings: Iterable[Any] = (),
    invalid_historical_plan_versions: Iterable[int] = (),
    coalition_commits: Mapping[str, Any] | Any | None = None,
    current_time_s: float | None = None,
    center_failed: bool = False,
    fallback_active: bool = False,
    common_window_tolerance_s: float = 0.15,
) -> CooperativeVisualFunnelSummary:
    """Build target/resource diagnostics from D5's existing read-only contracts.

    Bindings are grouped by their existing ``global_track_id``. No local or
    AirSim actor identity is admitted as a replacement identity. Funnel counts
    use active primary members only; standby reserves remain diagnostic rows.
    """

    if int(required_stable_frames) < 1:
        raise ValueError("required_stable_frames must be at least 1")
    if float(common_window_tolerance_s) < 0.0:
        raise ValueError("common_window_tolerance_s must be non-negative")

    raw_bindings = tuple(coalition_bindings)
    if not raw_bindings:
        raise ValueError("coalition_bindings must not be empty")
    current_items = tuple(current_associations)
    history_items = tuple(historical_associations)
    historical_raw_bindings = tuple(historical_bindings)
    grouped_indices: dict[str, list[int]] = defaultdict(list)
    for index, binding in enumerate(raw_bindings):
        global_track_id = _binding_global_track_id(binding)
        if global_track_id is None:
            raise ValueError(
                "each coalition binding requires assigned_global_track_id or global_track_id"
            )
        grouped_indices[global_track_id].append(index)
    normalized_by_index: dict[int, _Binding] = {}
    for indices in grouped_indices.values():
        for index in indices:
            normalized_by_index[index] = _normalize_binding(
                raw_bindings[index],
                coalition_size_hint=len(indices),
            )
    normalized = tuple(normalized_by_index[index] for index in range(len(raw_bindings)))

    target_summaries: list[CooperativeTargetVisualFunnel] = []
    all_diagnostics: list[CooperativeResourceTargetDiagnostic] = []
    membership_diagnostics: dict[str, Mapping[str, Any]] = {}
    for global_track_id in sorted(grouped_indices):
        indices = grouped_indices[global_track_id]
        group_raw = tuple(raw_bindings[index] for index in indices)
        group_bindings = tuple(normalized[index] for index in indices)
        group_resource_ids = {
            binding.resource_id for binding in group_bindings
        }
        group_resource_current = tuple(
            item
            for item in current_items
            if _evidence_resource_id(item) in group_resource_ids
        )
        group_current = tuple(
            item
            for item in current_items
            if _evidence_global_track_id(item) in {None, global_track_id}
            and _evidence_resource_id(item) in group_resource_ids
        )
        group_history = tuple(
            item
            for item in history_items
            if _evidence_global_track_id(item) == global_track_id
        )
        group_historical_bindings = tuple(
            binding
            for binding in historical_raw_bindings
            if _binding_global_track_id(binding) == global_track_id
        )
        association_current = tuple(
            item for item in group_current if _terminal_association(item) is not None
        )
        association_history = tuple(
            item for item in group_history if _terminal_association(item) is not None
        )
        commit = _resolve_coalition_commit(coalition_commits, group_bindings[0])
        completion = summarize_coalition_visual_completion(
            group_raw,
            association_current,
            association_history,
            required_stable_frames=required_stable_frames,
            historical_bindings=group_historical_bindings,
            invalid_historical_plan_versions=invalid_historical_plan_versions,
            coalition_commit=commit,
            current_time_s=current_time_s,
            center_failed=center_failed,
            fallback_active=fallback_active,
        )

        association_evidence = tuple(
            _normalize_evidence(item, input_order=index)
            for index, item in enumerate((*association_history, *association_current))
        )
        current_association_evidence = tuple(
            _normalize_evidence(item, input_order=index)
            for index, item in enumerate(association_current)
        )
        resource_current_association_evidence = tuple(
            _normalize_evidence(item, input_order=index)
            for index, item in enumerate(
                item
                for item in group_resource_current
                if _terminal_association(item) is not None
            )
        )
        primary_bindings = tuple(
            binding for binding in group_bindings if binding.member_role in _PRIMARY_ROLES
        )
        committed_current_primary_bindings = tuple(
            binding
            for binding in primary_bindings
            if _binding_member_committed(binding, completion)
        )
        active_primary_ids = _unique(
            binding.resource_id
            for binding in committed_current_primary_bindings
        )
        reserve_ids = _unique(
            binding.resource_id
            for binding in group_bindings
            if binding.member_role in _RESERVE_ROLES
        )
        common_window_required = not (
            group_bindings[0].terminal_authorization_scope == "per_primary"
            and not group_bindings[0].arrival_coordination_required
        )
        if common_window_required:
            common_count, common_start, common_end = _common_primary_lock_window(
                committed_current_primary_bindings,
                association_evidence,
                historical_bindings=tuple(
                    _normalize_binding(
                        binding,
                        coalition_size_hint=max(1, len(group_historical_bindings)),
                    )
                    for binding in group_historical_bindings
                ),
                source_plan_versions_by_resource=completion.metadata.get(
                    "stability_source_plan_versions_by_resource",
                    {},
                ),
                stable_frame_count_by_resource=completion.stable_lock_frame_count_by_resource,
                tolerance_s=float(common_window_tolerance_s),
            )
        else:
            common_count, common_start, common_end = 0, None, None
        membership_diagnostics[global_track_id] = dict(
            completion.metadata.get("primary_membership_transition", {})
        )
        common_complete = bool(
            len(active_primary_ids) == completion.primary_required_count
            and common_count >= int(required_stable_frames)
        )
        completion_window_satisfied = bool(
            not common_window_required or common_complete
        )

        diagnostics: list[CooperativeResourceTargetDiagnostic] = []
        for binding in group_bindings:
            latest = _latest_resource_evidence(
                binding,
                resource_current_association_evidence,
            )
            local_only = _latest_local_only_observation(binding, group_current)
            association = latest.association if latest is not None else None
            member_committed = _binding_member_committed(binding, completion)
            contract_matches = bool(
                association is not None
                and member_committed
                and _association_matches_binding(association, binding)
            )
            visible = _diagnostic_visible(latest, local_only)
            projected = bool(association is not None and _projection_succeeded(association))
            gate_accepted = bool(association is not None and _gate_accepted(association))
            locked = bool(
                latest is not None
                and contract_matches
                and latest.execution_locked
                and binding.member_role in _PRIMARY_ROLES
                and _binding_execution_active(binding)
            )
            stable_count = int(
                completion.stable_lock_frame_count_by_resource.get(binding.resource_id, 0)
            )
            active_primary = bool(
                binding.member_role in _PRIMARY_ROLES
                and _binding_execution_active(binding)
                and member_committed
            )
            failure_stage, reject_reason = _diagnostic_failure(
                binding=binding,
                association=association,
                committed_member=member_committed,
                contract_matches=contract_matches,
                visible=visible,
                projected=projected,
                gate_accepted=gate_accepted,
                locked=locked,
                stable_count=stable_count,
                required_stable_frames=int(required_stable_frames),
                common_complete=common_complete,
                common_window_required=common_window_required,
            )
            failure_category = _diagnostic_failure_category(
                association=association,
                failure_stage=failure_stage,
                reject_reason=reject_reason,
                visible=visible,
                projected=projected,
                gate_accepted=gate_accepted,
                locked=locked,
                stable_count=stable_count,
                required_stable_frames=int(required_stable_frames),
            )
            diagnostic = CooperativeResourceTargetDiagnostic(
                resource_id=binding.resource_id,
                global_track_id=binding.global_track_id,
                target_id=binding.target_id,
                plan_id=binding.plan_id,
                plan_version=binding.plan_version,
                plan_owner=binding.plan_owner,
                owner_node_id=binding.owner_node_id,
                coalition_id=binding.coalition_id,
                coalition_version=binding.coalition_version,
                terminal_authorization_scope=binding.terminal_authorization_scope,
                arrival_coordination_required=binding.arrival_coordination_required,
                member_role=binding.member_role,
                active_primary=active_primary,
                committed_member=member_committed,
                association_contract_matches=contract_matches,
                visible=visible,
                projected=projected,
                gate_accepted=gate_accepted,
                locked=locked,
                stable_lock_frame_count=stable_count,
                common_lock_window_participant=bool(active_primary and common_count > 0),
                association_confidence=(
                    float(association.association_confidence) if association is not None else 0.0
                ),
                ambiguity_score=(
                    float(association.ambiguity_score) if association is not None else 1.0
                ),
                friend_conflict_state=(
                    association.friend_conflict_state if association is not None else "none"
                ),
                decision_state=(association.decision_state if association is not None else "unobserved"),
                first_failure_stage=failure_stage,
                failure_category=failure_category,
                reject_reason=reject_reason,
                measurement_timestamp=(
                    association.measurement_timestamp if association is not None else None
                ),
                arrival_timestamp=(
                    association.arrival_timestamp if association is not None else None
                ),
            )
            diagnostics.append(diagnostic)
            all_diagnostics.append(diagnostic)

        active_rows = tuple(item for item in diagnostics if item.active_primary)
        second = active_rows[1] if len(active_rows) > 1 else None
        cooperative_completion = bool(
            completion.coalition_visual_consensus and completion_window_satisfied
        )
        if cooperative_completion:
            target_reason = (
                "cooperative_visual_completion"
                if common_window_required
                else "per_primary_visual_completion"
            )
        elif completion.coalition_conflict_state != "none":
            target_reason = completion.coalition_conflict_state
        elif common_window_required and common_count < int(required_stable_frames) and all(
            item.stable_lock_frame_count >= int(required_stable_frames) for item in active_rows
        ):
            target_reason = "common_lock_window_insufficient"
        else:
            failing = next(
                (item for item in active_rows if item.first_failure_stage != "complete"),
                None,
            )
            target_reason = failing.reject_reason if failing is not None else completion.reason

        target_summaries.append(
            CooperativeTargetVisualFunnel(
                global_track_id=completion.global_track_id,
                target_id=group_bindings[0].target_id,
                plan_id=completion.plan_id,
                plan_version=completion.plan_version,
                plan_owner=group_bindings[0].plan_owner,
                owner_node_id=group_bindings[0].owner_node_id,
                coalition_id=completion.coalition_id,
                coalition_version=completion.coalition_version,
                terminal_authorization_scope=(
                    group_bindings[0].terminal_authorization_scope
                ),
                arrival_coordination_required=(
                    group_bindings[0].arrival_coordination_required
                ),
                common_lock_window_required=common_window_required,
                primary_required_count=completion.primary_required_count,
                active_primary_resource_ids=active_primary_ids,
                reserve_resource_ids=reserve_ids,
                resource_diagnostics=tuple(diagnostics),
                visible_primary_count=sum(
                    item.committed_member and item.visible for item in active_rows
                ),
                projected_primary_count=sum(
                    item.committed_member
                    and item.association_contract_matches
                    and item.visible
                    and item.projected
                    for item in active_rows
                ),
                gate_accepted_primary_count=sum(
                    item.committed_member
                    and item.association_contract_matches
                    and item.visible
                    and item.projected
                    and item.gate_accepted
                    for item in active_rows
                ),
                locked_primary_count=sum(item.locked for item in active_rows),
                stable_primary_count=sum(
                    item.stable_lock_frame_count >= int(required_stable_frames)
                    for item in active_rows
                ),
                common_lock_frame_count=common_count,
                common_lock_window_start_s=common_start,
                common_lock_window_end_s=common_end,
                cooperative_completion=cooperative_completion,
                second_primary_resource_id=(second.resource_id if second is not None else None),
                second_primary_first_failure_stage=(
                    second.first_failure_stage if second is not None else None
                ),
                second_primary_failure_category=(
                    second.failure_category if second is not None else None
                ),
                second_primary_reject_reason=(second.reject_reason if second is not None else None),
                reason=target_reason,
            )
        )

    active_rows = tuple(item for item in all_diagnostics if item.active_primary)
    funnel_counts = {
        "active_primary": len(active_rows),
        "visible": sum(
            item.committed_member and item.visible for item in active_rows
        ),
        "projected": sum(
            item.committed_member
            and item.association_contract_matches
            and item.visible
            and item.projected
            for item in active_rows
        ),
        "gate_accepted": sum(
            item.committed_member
            and item.association_contract_matches
            and item.visible
            and item.projected
            and item.gate_accepted
            for item in active_rows
        ),
        "locked": sum(item.locked for item in active_rows),
        "stable_lock": sum(
            item.stable_lock_frame_count >= int(required_stable_frames) for item in active_rows
        ),
        "common_lock_window": sum(
            target.primary_required_count
            for target in target_summaries
            if target.common_lock_window_required
            and target.common_lock_frame_count >= int(required_stable_frames)
        ),
        "completion_eligible": sum(
            target.primary_required_count
            for target in target_summaries
            if target.cooperative_completion
        ),
    }
    first_failure_counts: dict[str, int] = defaultdict(int)
    failure_category_counts: dict[str, int] = defaultdict(int)
    for item in active_rows:
        first_failure_counts[item.first_failure_stage] += 1
        failure_category_counts[item.failure_category] += 1
    second_failure_counts: dict[str, int] = defaultdict(int)
    second_failure_category_counts: dict[str, int] = defaultdict(int)
    for target in target_summaries:
        if target.second_primary_first_failure_stage is not None:
            second_failure_counts[target.second_primary_first_failure_stage] += 1
        if target.second_primary_failure_category is not None:
            second_failure_category_counts[
                target.second_primary_failure_category
            ] += 1

    return CooperativeVisualFunnelSummary(
        target_summaries=tuple(target_summaries),
        resource_binding_count=len(normalized),
        target_count=len(target_summaries),
        active_primary_count=len(active_rows),
        completed_target_count=sum(target.cooperative_completion for target in target_summaries),
        funnel_counts=funnel_counts,
        first_failure_stage_counts=dict(sorted(first_failure_counts.items())),
        failure_category_counts=dict(sorted(failure_category_counts.items())),
        second_primary_first_failure_stage_counts=dict(sorted(second_failure_counts.items())),
        second_primary_failure_category_counts=dict(
            sorted(second_failure_category_counts.items())
        ),
        metadata={
            "required_stable_frames": int(required_stable_frames),
            "common_window_tolerance_s": float(common_window_tolerance_s),
            "completion_policy_by_global_track_id": {
                target.global_track_id: (
                    "common_lock_window"
                    if target.common_lock_window_required
                    else "independent_per_primary"
                )
                for target in target_summaries
            },
            "reserve_completion_policy": "standby_excluded",
            "global_id_policy": "existing_assigned_global_track_id_only",
            "online_truth_fields_consumed": [],
            "primary_membership_transition_by_global_track_id": membership_diagnostics,
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
        terminal_authorization_scope=_text(
            _read(value, "terminal_authorization_scope", default="coalition")
        ).lower(),
        arrival_coordination_required=bool(
            _read(value, "arrival_coordination_required", default=True)
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
        camera_id = value.camera_id
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
        camera_id = _optional_text(
            association.metadata.get("camera_history_scope")
            or association.metadata.get("measurement_camera_id")
            or association.metadata.get("camera_id")
        )
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
        camera_id=_optional_text(camera_id),
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
        and association.terminal_authorization_scope
        == binding.terminal_authorization_scope
        and association.arrival_coordination_required
        == binding.arrival_coordination_required
        and _association_owner_matches_binding(association, binding)
    )


def _association_owner_matches_binding(
    association: TerminalAssociation,
    binding: _Binding,
) -> bool:
    """Compare owner evidence when the terminal record carries it explicitly."""

    metadata = association.metadata
    association_owner = _optional_text(
        _read(metadata, "active_plan_owner", "plan_owner", "current_plan_owner")
    )
    association_owner_node = _optional_text(
        _read(metadata, "owner_node_id", "current_plan_owner_node_id")
    )
    return bool(
        (association_owner is None or association_owner == binding.plan_owner)
        and (
            association_owner_node is None
            or association_owner_node == binding.owner_node_id
        )
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
    member_committed_current: bool,
) -> _StabilityState:
    if not member_committed_current:
        return _StabilityState(
            count=0,
            reset_reason="coalition_member_not_committed_current",
            history_key=_stability_history_key(binding),
            evidence_source="unavailable",
        )
    current_frames = _frame_states(current_locks, binding)
    if not current_frames:
        return _StabilityState(
            count=0,
            history_key=_stability_history_key(binding),
            evidence_source="unavailable",
        )
    current = current_frames[-1]
    later_evidence = max(current[4], key=_frame_order_token)
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
            history_key=_stability_history_key(binding),
            history_signature=_visual_history_signature(later_evidence),
            evidence_source=_visual_evidence_source(later_evidence),
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
            later_evidence=later_evidence,
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
        later_evidence = evidence
    return _StabilityState(
        count=count,
        continued_across_plan_version=continued,
        reset_reason=reset_reason,
        source_plan_versions=tuple(dict.fromkeys(source_versions)),
        history_key=_stability_history_key(binding),
        history_signature=_visual_history_signature(max(current[4], key=_frame_order_token)),
        evidence_source=_visual_evidence_source(max(current[4], key=_frame_order_token)),
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
    later_evidence: _Evidence,
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
        visual_identity_conflict = _visual_history_transition_conflict(
            newer=later_evidence,
            older=evidence,
        )
        if visual_identity_conflict is not None:
            reset_reason = visual_identity_conflict
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


def _stability_history_key(binding: _Binding) -> dict[str, Any]:
    return {
        "resource_id": binding.resource_id,
        "assigned_global_track_id": binding.global_track_id,
        "target_id": binding.target_id,
    }


def _visual_history_signature(evidence: _Evidence) -> dict[str, Any]:
    association = evidence.association
    metadata = association.metadata
    audited = metadata.get("bbox_history_signature")
    audited_signature = dict(audited) if isinstance(audited, Mapping) else {}
    camera_id = (
        audited_signature.get("camera_id")
        or evidence.camera_id
        or metadata.get("camera_history_scope")
        or metadata.get("measurement_camera_id")
        or metadata.get("camera_id")
    )
    detector_backend = (
        audited_signature.get("detector_backend")
        or metadata.get("detector_backend")
        or association.detection_source
    )
    tracker_backend = (
        audited_signature.get("tracker_backend")
        or metadata.get("tracker_backend")
        or association.detection_source
    )
    stream_id = (
        audited_signature.get("stream_id")
        or metadata.get("stream_id")
        or metadata.get("stream_key")
        or camera_id
    )
    return {
        "resource_id": evidence.resource_id,
        "assigned_global_track_id": association.assigned_global_track_id,
        "local_track_id": association.local_track_id,
        "camera_id": _optional_text(camera_id),
        "detector_backend": _optional_text(detector_backend),
        "tracker_backend": _optional_text(tracker_backend),
        "stream_id": _optional_text(stream_id),
        "evidence_source": _visual_evidence_source(evidence),
    }


def _visual_evidence_source(evidence: _Evidence) -> str:
    state = evidence.association.local_track_state
    if state:
        return str(state).strip().lower()
    return str(
        evidence.association.metadata.get("bbox_history_evidence_source", "unavailable")
    ).strip().lower()


def _visual_history_transition_conflict(
    *,
    newer: _Evidence,
    older: _Evidence,
) -> str | None:
    newer_association = newer.association
    if newer_association.track_reset_reason:
        return f"producer_track_reset:{newer_association.track_reset_reason}"
    if newer_association.track_transition_state in {"switched", "reset"}:
        return f"track_transition:{newer_association.track_transition_state}"
    newer_signature = _visual_history_signature(newer)
    older_signature = _visual_history_signature(older)
    if (
        newer_signature["resource_id"] != older_signature["resource_id"]
        or newer_signature["assigned_global_track_id"]
        != older_signature["assigned_global_track_id"]
    ):
        return "resource_target_binding_changed"
    if newer_signature["local_track_id"] != older_signature["local_track_id"]:
        return "local_track_id_changed"
    if newer_signature["camera_id"] != older_signature["camera_id"]:
        return "camera_changed"
    if newer_signature["detector_backend"] != older_signature["detector_backend"]:
        return "detector_backend_changed"
    if newer_signature["tracker_backend"] != older_signature["tracker_backend"]:
        return "tracker_backend_changed"
    if newer_signature["stream_id"] != older_signature["stream_id"]:
        return "stream_changed"
    if newer_signature["evidence_source"] != "measured":
        return f"non_measured_visual_source:{newer_signature['evidence_source']}"
    if older_signature["evidence_source"] != "measured":
        return f"non_measured_visual_source:{older_signature['evidence_source']}"
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
    if metadata.get("bbox_history_contract_complete") is False:
        return False
    if association.local_track_state not in {"", "measured"}:
        return False
    if bool(metadata.get("identity_conflict", False)):
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


def _terminal_association(
    value: TerminalAssociation | TerminalObservation,
) -> TerminalAssociation | None:
    if isinstance(value, TerminalAssociation):
        return value
    if isinstance(value, TerminalObservation):
        return value.terminal_association
    raise TypeError("visual evidence must be TerminalAssociation or TerminalObservation")


def _evidence_global_track_id(
    value: TerminalAssociation | TerminalObservation,
) -> str | None:
    association = _terminal_association(value)
    if association is not None:
        return association.assigned_global_track_id
    if isinstance(value, TerminalObservation):
        return _optional_text(value.metadata.get("assigned_global_track_id"))
    return None


def _evidence_resource_id(
    value: TerminalAssociation | TerminalObservation,
) -> str | None:
    if isinstance(value, TerminalObservation):
        return value.resource_id
    return value.resource_id or _optional_text(value.metadata.get("resource_id"))


def _binding_global_track_id(value: Any) -> str | None:
    return _optional_text(
        _read(value, "assigned_global_track_id", "global_track_id", "target_id")
    )


def _resolve_coalition_commit(
    commits: Mapping[str, Any] | Any | None,
    binding: _Binding,
) -> Any | None:
    if commits is None:
        return None
    if not isinstance(commits, Mapping):
        return commits
    if any(key in commits for key in ("state", "commit_state", "status")):
        return commits
    for key in (binding.global_track_id, binding.target_id, binding.coalition_id):
        if key is not None and key in commits:
            return commits[key]
    return None


def _binding_member_committed(
    binding: _Binding,
    completion: CoalitionVisualSummary,
) -> bool:
    if binding.authorization_state not in _AUTHORIZED_STATES:
        return False
    if binding.member_role in _PRIMARY_ROLES and not _binding_execution_active(binding):
        return False
    if completion.coalition_commit_required:
        required = set(completion.coalition_commit_required_member_ids)
        acked = set(completion.coalition_commit_acked_member_ids)
        return bool(
            completion.coalition_commit_valid
            and binding.resource_id in required
            and binding.resource_id in acked
        )
    return True


def _latest_binding_evidence(
    binding: _Binding,
    evidence_items: Iterable[_Evidence],
) -> _Evidence | None:
    candidates = tuple(
        evidence
        for evidence in evidence_items
        if evidence.resource_id == binding.resource_id
        and evidence.association.assigned_global_track_id == binding.global_track_id
    )
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda evidence: (
            evidence.timestamp,
            evidence.frame_index if evidence.frame_index is not None else -1,
            int(_association_matches_binding(evidence.association, binding)),
            int(evidence.execution_locked),
            float(evidence.association.association_confidence),
        ),
    )


def _latest_resource_evidence(
    binding: _Binding,
    evidence_items: Iterable[_Evidence],
) -> _Evidence | None:
    """Return the latest resource evidence, including a conflicting binding.

    The cooperative diagnostic must expose a current assignment/global-track
    mismatch instead of silently converting it into an apparent visibility
    loss. This helper is read-only and never treats the conflicting ID as a
    replacement for the binding's center-owned ``global_track_id``.
    """

    candidates = tuple(
        evidence
        for evidence in evidence_items
        if evidence.resource_id == binding.resource_id
    )
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda evidence: (
            evidence.timestamp,
            evidence.frame_index if evidence.frame_index is not None else -1,
            evidence.input_order,
        ),
    )


def _latest_local_only_observation(
    binding: _Binding,
    evidence_items: Iterable[TerminalAssociation | TerminalObservation],
) -> TerminalObservation | None:
    candidates = tuple(
        item
        for item in evidence_items
        if isinstance(item, TerminalObservation)
        and item.resource_id == binding.resource_id
        and item.terminal_association is None
        and item.local_track is not None
        and _evidence_global_track_id(item) in {None, binding.global_track_id}
    )
    return max(candidates, key=lambda item: item.timestamp) if candidates else None


def _diagnostic_visible(
    evidence: _Evidence | None,
    local_only: TerminalObservation | None,
) -> bool:
    if evidence is not None:
        return bool(
            evidence.has_own_local_detection
            and evidence.association.local_track_state == "measured"
        )
    return bool(
        local_only is not None
        and local_only.local_track is not None
        and local_only.local_track.local_track_state == "measured"
    )


def _projection_succeeded(association: TerminalAssociation) -> bool:
    metadata = association.metadata
    if metadata.get("projection_valid") is not None:
        return bool(metadata["projection_valid"])
    selected = metadata.get("selected_pair")
    if isinstance(selected, Mapping) and selected.get("projected_px") is not None:
        return True
    return any(
        isinstance(item, Mapping) and item.get("projected_px") is not None
        for item in metadata.get("candidate_pair_logs", ())
    )


def _gate_accepted(association: TerminalAssociation) -> bool:
    metadata = association.metadata
    if int(metadata.get("gate_pass_count", 0) or 0) > 0:
        return True
    selected = metadata.get("selected_pair")
    if isinstance(selected, Mapping) and bool(selected.get("gate_pass", False)):
        return True
    return any(
        isinstance(item, Mapping) and bool(item.get("gate_pass", False))
        for item in metadata.get("candidate_pair_logs", ())
    )


def _diagnostic_failure(
    *,
    binding: _Binding,
    association: TerminalAssociation | None,
    committed_member: bool,
    contract_matches: bool,
    visible: bool,
    projected: bool,
    gate_accepted: bool,
    locked: bool,
    stable_count: int,
    required_stable_frames: int,
    common_complete: bool,
    common_window_required: bool,
) -> tuple[str, str]:
    if binding.member_role in _RESERVE_ROLES and binding.activation_state not in _ACTIVE_STATES:
        return "standby_reserve", "reserve_standby_excluded_from_primary_completion"
    if not committed_member:
        return "contract", "coalition_member_not_committed"
    if association is not None and not contract_matches:
        if association.assigned_global_track_id != binding.global_track_id:
            return "contract", "assigned_global_track_id_mismatch"
        if not _association_owner_matches_binding(association, binding):
            return "contract", "plan_owner_mismatch"
        if (
            association.terminal_authorization_scope
            != binding.terminal_authorization_scope
            or association.arrival_coordination_required
            != binding.arrival_coordination_required
        ):
            return "contract", "terminal_authorization_contract_mismatch"
        return "contract", "plan_or_coalition_version_mismatch"
    if not visible:
        return (
            "visible",
            _association_rejection_reason(association)
            if association is not None
            else "no_current_local_visual_detection",
        )
    if not projected:
        return "projected", association.reason if association is not None else "projection_unavailable"
    if not gate_accepted:
        return "gate_accepted", association.reason if association is not None else "geometry_gate_rejected"
    if not locked:
        return "locked", association.reason if association is not None else "terminal_lock_not_available"
    if stable_count < required_stable_frames:
        return "stable_lock", "primary_lock_stability_incomplete"
    if common_window_required and not common_complete:
        return "common_lock_window", "common_lock_window_insufficient"
    return (
        "complete",
        "cooperative_visual_completion"
        if common_window_required
        else "per_primary_visual_completion",
    )


def _diagnostic_failure_category(
    *,
    association: TerminalAssociation | None,
    failure_stage: str,
    reject_reason: str,
    visible: bool,
    projected: bool,
    gate_accepted: bool,
    locked: bool,
    stable_count: int,
    required_stable_frames: int,
) -> str:
    """Normalize existing D5 evidence into a passive failure category.

    This classifier does not alter association, lock, hold, or reacquire
    decisions. It only provides a stable aggregation key for the next AirSim
    multi-seed failure-funnel report.
    """

    if failure_stage == "complete":
        return "complete"
    if failure_stage == "standby_reserve":
        return "standby_reserve"

    live_funnel = (
        association.metadata.get("d5_live_visual_funnel", {})
        if association is not None
        else {}
    )
    if not isinstance(live_funnel, Mapping):
        live_funnel = {}
    live_stage = str(live_funnel.get("first_failure_stage") or "").lower()
    live_reason = str(live_funnel.get("first_failure_reason") or "")
    reason_text = " ".join(
        value
        for value in (
            str(reject_reason or ""),
            live_reason,
            str(association.reason if association is not None else ""),
        )
        if value
    ).lower()

    if failure_stage == "contract" or any(
        token in reason_text
        for token in (
            "assigned_global_track_id_mismatch",
            "plan_or_coalition_version_mismatch",
            "plan_owner_mismatch",
            "assignment_version_mismatch",
            "stale_plan_version_rejected",
            "authorization_contract_mismatch",
            "coalition_member_not_committed",
        )
    ):
        return "assignment_or_identity_contract_mismatch"

    duplicate_risk = bool(
        association is not None
        and (
            association.duplicate_terminal_lock_risk
            or association.metadata.get("duplicate_terminal_lock_risk", False)
        )
    )
    friend_conflict = bool(
        association is not None
        and association.friend_conflict_state != "none"
    )
    if duplicate_risk or friend_conflict or any(
        token in reason_text
        for token in ("duplicate_terminal_lock", "friend_conflict", "friend_overlap")
    ):
        return "friend_or_duplicate_lock_conflict"

    if any(
        token in reason_text
        for token in (
            "measurement_age",
            "measurement_stale",
            "visual_evidence_expired",
            "timestamp_stale",
            "arrival_window_expired",
            "prediction_age_exceeded",
        )
    ):
        return "timestamp_or_measurement_stale"

    bbox_edge_clipped = bool(
        association is not None
        and (
            association.bbox_edge_clipped
            or association.metadata.get("bbox_edge_clipped", False)
        )
    )
    if bbox_edge_clipped or live_stage == "bbox_stability" or any(
        token in reason_text
        for token in (
            "bbox_area_unstable",
            "bbox_history",
            "bbox_edge",
            "bbox_clipped",
            "bbox_too_small",
        )
    ):
        return "bbox_unstable_or_edge_clipped"

    if not visible or failure_stage in {"visible", "live_detection", "measured_bbox"}:
        return "not_visible"
    if not projected or failure_stage in {"projected", "projection"}:
        return "projection_invalid"
    if not gate_accepted or failure_stage in {"gate_accepted", "geometry_gate"}:
        return "geometry_gate_rejected"

    visual_state = str(
        live_funnel.get(
            "visual_match_decision_state",
            association.decision_state if association is not None else "",
        )
    ).lower()
    gate_pass_count = int(
        association.metadata.get("gate_pass_count", 0) or 0
    ) if association is not None else 0
    if visual_state == "ambiguous" or any(
        token in reason_text
        for token in (
            "candidate_margin",
            "multiple_candidate",
            "candidate_not_unique",
            "ambiguous_candidate",
        )
    ) or (gate_pass_count > 1 and not locked):
        return "candidate_not_unique"

    if (
        failure_stage in {"locked", "stable_lock", "measured_stable_lock", "execution_lock"}
        or not locked
        or stable_count < required_stable_frames
    ):
        return "associated_but_stable_lock_incomplete"
    if failure_stage == "common_lock_window":
        return "coalition_lock_window_incomplete"
    return "other_terminal_failure"


def _primary_membership_transition_diagnostic(
    current_bindings: tuple[_Binding, ...],
    historical_bindings: tuple[_Binding, ...],
) -> dict[str, Any]:
    current_primary_ids = _unique(
        binding.resource_id
        for binding in current_bindings
        if binding.member_role in _PRIMARY_ROLES
    )
    first = current_bindings[0]
    prior_versions = sorted(
        {
            binding.plan_version
            for binding in historical_bindings
            if binding.plan_version is not None
            and first.plan_version is not None
            and binding.plan_version < first.plan_version
            and binding.global_track_id == first.global_track_id
            and binding.target_id == first.target_id
        }
    )
    if not prior_versions:
        return {
            "available": False,
            "current_plan_version": first.plan_version,
            "previous_plan_version": None,
            "current_primary_resource_ids": list(current_primary_ids),
            "previous_primary_resource_ids": [],
            "membership_changed": False,
            "added_primary_resource_ids": [],
            "removed_primary_resource_ids": [],
        }

    previous_version = prior_versions[-1]
    previous_primary_ids = _unique(
        binding.resource_id
        for binding in historical_bindings
        if binding.plan_version == previous_version
        and binding.global_track_id == first.global_track_id
        and binding.target_id == first.target_id
        and binding.member_role in _PRIMARY_ROLES
    )
    current_set = set(current_primary_ids)
    previous_set = set(previous_primary_ids)
    return {
        "available": True,
        "current_plan_version": first.plan_version,
        "previous_plan_version": previous_version,
        "current_primary_resource_ids": list(current_primary_ids),
        "previous_primary_resource_ids": list(previous_primary_ids),
        "membership_changed": current_set != previous_set,
        "added_primary_resource_ids": sorted(current_set - previous_set),
        "removed_primary_resource_ids": sorted(previous_set - current_set),
    }


def _current_primary_failure_diagnostics(
    primary_bindings: tuple[_Binding, ...],
    current_evidence: tuple[_Evidence, ...],
    *,
    stable_counts: Mapping[str, int],
    required_stable_frames: int,
    commit_conflict_reasons: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    diagnostics: dict[str, dict[str, Any]] = {}
    for binding in primary_bindings:
        candidates = tuple(
            evidence
            for evidence in current_evidence
            if evidence.resource_id == binding.resource_id
            and evidence.association.assigned_global_track_id == binding.global_track_id
        )
        latest = max(candidates, key=_frame_order_token) if candidates else None
        association = latest.association if latest is not None else None
        contract_matches = bool(
            association is not None and _association_matches_binding(association, binding)
        )
        visible = bool(
            latest is not None
            and latest.has_own_local_detection
            and association is not None
            and association.local_track_state == "measured"
        )
        projected = bool(association is not None and _projection_succeeded(association))
        gate_accepted = bool(association is not None and _gate_accepted(association))
        locked = bool(latest is not None and latest.execution_locked and contract_matches)
        stable_count = int(stable_counts.get(binding.resource_id, 0))

        if commit_conflict_reasons:
            failure_stage = "contract"
            failure_reason = commit_conflict_reasons[0]
        elif not _binding_execution_active(binding):
            failure_stage = "contract"
            failure_reason = "primary_binding_not_execution_authorized"
        elif association is not None and not contract_matches:
            failure_stage = "contract"
            failure_reason = "plan_or_coalition_version_mismatch"
        elif not visible:
            failure_stage = "visible"
            failure_reason = (
                _association_rejection_reason(association)
                if association is not None
                else "no_current_local_visual_detection"
            )
        elif not projected:
            failure_stage = "projected"
            failure_reason = _association_rejection_reason(association)
        elif not gate_accepted:
            failure_stage = "gate_accepted"
            failure_reason = _association_rejection_reason(association)
        elif not locked:
            failure_stage = "locked"
            failure_reason = _association_rejection_reason(association)
        elif stable_count < required_stable_frames:
            failure_stage = "stable_lock"
            failure_reason = "primary_lock_stability_incomplete"
        else:
            failure_stage = "complete"
            failure_reason = "primary_visual_lock_complete"

        diagnostics[binding.resource_id] = {
            "decision_state": association.decision_state if association is not None else "unobserved",
            "association_reason": association.reason if association is not None else None,
            "association_rejection_reason": (
                _association_rejection_reason(association)
                if association is not None
                else None
            ),
            "association_contract_matches": contract_matches,
            "has_own_local_detection": bool(
                latest is not None and latest.has_own_local_detection
            ),
            "visible": visible,
            "projected": projected,
            "gate_accepted": gate_accepted,
            "locked": locked,
            "stable_lock_frame_count": stable_count,
            "friend_conflict_state": (
                association.friend_conflict_state if association is not None else "none"
            ),
            "first_failure_stage": failure_stage,
            "failure_reason": failure_reason,
        }
    return diagnostics


def _association_rejection_reason(association: TerminalAssociation) -> str:
    value = association.metadata.get("association_rejection_reason")
    return str(value) if value else association.reason


def _common_primary_lock_window(
    primary_bindings: tuple[_Binding, ...],
    evidence_items: tuple[_Evidence, ...],
    *,
    historical_bindings: tuple[_Binding, ...] = (),
    source_plan_versions_by_resource: Mapping[str, Iterable[int]] | None = None,
    stable_frame_count_by_resource: Mapping[str, int] | None = None,
    tolerance_s: float,
) -> tuple[int, float | None, float | None]:
    active_bindings = tuple(
        binding for binding in primary_bindings if _binding_execution_active(binding)
    )
    if not active_bindings:
        return 0, None, None

    source_versions = source_plan_versions_by_resource or {}
    stable_frame_counts = stable_frame_count_by_resource or {}
    all_bindings = (*primary_bindings, *historical_bindings)
    eligible: dict[str, tuple[_Evidence, ...]] = {}
    for binding in active_bindings:
        deduplicated: dict[tuple[str, float], _Evidence] = {}
        allowed_versions = {
            int(version)
            for version in source_versions.get(binding.resource_id, ())
        }
        if not allowed_versions and binding.plan_version is not None:
            allowed_versions.add(binding.plan_version)
        for evidence in evidence_items:
            exact_binding_match = any(
                candidate.resource_id == binding.resource_id
                and candidate.global_track_id == binding.global_track_id
                and candidate.target_id == binding.target_id
                and _association_matches_binding(evidence.association, candidate)
                for candidate in all_bindings
            )
            if (
                evidence.resource_id != binding.resource_id
                or not evidence.execution_locked
                or evidence.association.plan_version not in allowed_versions
                or not exact_binding_match
                or not _evidence_safe_for_continuity(evidence)
            ):
                continue
            deduplicated[(evidence.frame_key, evidence.timestamp)] = evidence
        recent = tuple(sorted(deduplicated.values(), key=_frame_order_token))
        stable_tail_length = max(
            0,
            int(stable_frame_counts.get(binding.resource_id, len(recent))),
        )
        eligible[binding.resource_id] = (
            recent[-stable_tail_length:] if stable_tail_length else ()
        )
    if any(not values for values in eligible.values()):
        return 0, None, None

    indexed = {
        resource_id: {
            evidence.frame_index: evidence.timestamp
            for evidence in values
            if evidence.frame_index is not None
        }
        for resource_id, values in eligible.items()
    }
    if all(values for values in indexed.values()):
        common_indices = sorted(set.intersection(*(set(values) for values in indexed.values())))
        runs: list[list[int]] = []
        for frame_index in common_indices:
            if not runs or frame_index != runs[-1][-1] + 1:
                runs.append([frame_index])
            else:
                runs[-1].append(frame_index)
        if runs:
            best = max(runs, key=lambda run: (len(run), run[-1]))
            timestamps = [
                sum(indexed[resource_id][frame_index] for resource_id in indexed) / len(indexed)
                for frame_index in best
            ]
            return len(best), min(timestamps), max(timestamps)

    resource_ids = tuple(eligible)
    reference = eligible[resource_ids[0]]
    common_timestamps: list[float] = []
    for evidence in reference:
        matches = [evidence.timestamp]
        for resource_id in resource_ids[1:]:
            candidate = min(
                eligible[resource_id],
                key=lambda value: abs(value.timestamp - evidence.timestamp),
            )
            if abs(candidate.timestamp - evidence.timestamp) > tolerance_s:
                break
            matches.append(candidate.timestamp)
        else:
            common_timestamps.append(sum(matches) / len(matches))
    if not common_timestamps:
        return 0, None, None
    unique_times = sorted(dict.fromkeys(round(value, 9) for value in common_timestamps))
    max_gap = max(0.25, 3.0 * tolerance_s)
    runs: list[list[float]] = []
    for timestamp in unique_times:
        if not runs or timestamp - runs[-1][-1] > max_gap:
            runs.append([timestamp])
        else:
            runs[-1].append(timestamp)
    best_times = max(runs, key=lambda run: (len(run), run[-1]))
    return len(best_times), best_times[0], best_times[-1]


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
