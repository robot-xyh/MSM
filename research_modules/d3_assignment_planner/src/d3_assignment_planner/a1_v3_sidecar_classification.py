"""Deterministic offline classification for A1 v3 planning evidence.

The classifier consumes only the frozen episode identity and continuous,
anonymous online planning records.  Callers may attach offline identity labels,
but they cannot choose the class fields used by writer quotas.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .a1_v3_data_contract import (
    A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP,
    A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP,
    A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR,
    A1_V3_PERMISSION_FIELDS,
    A1_V3_REQUEST_SCHEMA_V1,
    A1V3DataContractError,
    A1V3FrozenRequest,
    A1V3OnlineFrame,
    A1V3ScheduledEpisode,
    canonical_json_sha256,
)


A1_V3_SIDECAR_CLASSIFICATION_POLICY_SCHEMA_V1 = (
    "d3_a1_v3_sidecar_classification_policy_v1"
)
A1_V3_SIDECAR_CLASSIFICATION_SCHEMA_V1 = (
    "d3_a1_v3_derived_sidecar_classification_v1"
)
A1_V3_SIDECAR_CLASSIFICATION_POLICY_ID = (
    "d3-a1-v3-sidecar-classification-policy-20260801-v1"
)
A1_V3_SIDECAR_CLASSIFIER_LOGICAL_PATH = (
    "research_modules/d3_assignment_planner/src/d3_assignment_planner/"
    "a1_v3_sidecar_classification.py"
)
DEFAULT_A1_V3_SIDECAR_CLASSIFICATION_POLICY_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs/a1_source_independent_v3_sidecar_classification_policy_v1.json"
)

_REQUEST_LOGICAL_PATH = (
    "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_development_data_request_v1.json"
)
_NEAR_TIE_LOGICAL_PATH = (
    "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_near_tie_boundary_v1.json"
)
_NEAR_TIE_SCHEMA = "d3_a1_v3_rule_cost_near_tie_boundary_v1"
_NEAR_TIE_ID = "d3-a1-v3-rule-cost-near-tie-boundary-v1"
_KEEP_ACTION = "keep_exact_r0"
_POSITIVE_ACTIONS = frozenset(
    {
        "single_target_rebind_with_resource_release",
        "two_target_pair_swap",
        "multi_target_cycle",
        "target_appearance_assignment",
        "target_loss_release",
        "resource_failure_reassignment",
        "resource_recovery_reassignment",
        "m_to_n_demand_increase",
        "m_to_n_demand_decrease",
    }
)
_REQUEST_ACTIONS = _POSITIVE_ACTIONS | {_KEEP_ACTION, "primary_reserve_role_change"}
_DERIVABLE_HARD_NEGATIVES = frozenset(
    {
        "near_tie_but_teacher_keeps_r0",
        "incomplete_m_to_n_coalition",
        "coverage_degrading_reassignment",
        "rule_cost_difference_boundary_exceeded",
        "binding_change_boundary_exceeded",
        "stale_or_expired_plan_candidate",
        "resource_capacity_conflict",
    }
)
A1_V3_DERIVABLE_ACTION_CHANGE_TYPES = tuple(
    sorted(_POSITIVE_ACTIONS | {_KEEP_ACTION})
)
A1_V3_DERIVABLE_HARD_NEGATIVE_TYPES = tuple(sorted(_DERIVABLE_HARD_NEGATIVES))
A1_V3_REJECTED_UNDERIVED_TAXONOMY = (
    "lower_learned_score_on_hard_forbidden_edge",
    "primary_reserve_role_change",
)
_STALE_REASON_MARKERS = ("stale", "expired", "lease")


def _intent(
    scenario_family: str,
    hard_negative_priority: Sequence[str],
    positive_actions: Sequence[str] = tuple(sorted(_POSITIVE_ACTIONS)),
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    return (
        scenario_family,
        tuple(positive_actions),
        tuple(hard_negative_priority),
    )


_CELL_INTENT_SPECS = {
    "nominal-balanced-5t5r": _intent(
        "nominal_balanced",
        (
            "near_tie_but_teacher_keeps_r0",
            "coverage_degrading_reassignment",
            "binding_change_boundary_exceeded",
            "rule_cost_difference_boundary_exceeded",
        ),
    ),
    "dense-crossing-20t20r": _intent(
        "dense_crossing",
        (
            "binding_change_boundary_exceeded",
            "resource_capacity_conflict",
            "coverage_degrading_reassignment",
            "rule_cost_difference_boundary_exceeded",
            "near_tie_but_teacher_keeps_r0",
        ),
    ),
    "dense-crossing-50t50r": _intent(
        "dense_crossing",
        (
            "binding_change_boundary_exceeded",
            "resource_capacity_conflict",
            "coverage_degrading_reassignment",
            "rule_cost_difference_boundary_exceeded",
            "near_tie_but_teacher_keeps_r0",
        ),
    ),
    "formation-split-50t50r": _intent(
        "formation_split",
        (
            "coverage_degrading_reassignment",
            "binding_change_boundary_exceeded",
            "rule_cost_difference_boundary_exceeded",
            "near_tie_but_teacher_keeps_r0",
        ),
    ),
    "evasive-multilevel-100t100r": _intent(
        "evasive_multilevel",
        (
            "rule_cost_difference_boundary_exceeded",
            "binding_change_boundary_exceeded",
            "coverage_degrading_reassignment",
            "near_tie_but_teacher_keeps_r0",
        ),
    ),
    "delayed-noisy-200t200r": _intent(
        "delayed_noisy",
        (
            "stale_or_expired_plan_candidate",
            "rule_cost_difference_boundary_exceeded",
            "coverage_degrading_reassignment",
            "binding_change_boundary_exceeded",
            "near_tie_but_teacher_keeps_r0",
        ),
    ),
    "communication-degraded-5t5r": _intent(
        "communication_degraded",
        (
            "stale_or_expired_plan_candidate",
            "coverage_degrading_reassignment",
            "binding_change_boundary_exceeded",
            "near_tie_but_teacher_keeps_r0",
        ),
    ),
    "center-failure-20t20r": _intent(
        "center_failure",
        (
            "stale_or_expired_plan_candidate",
            "binding_change_boundary_exceeded",
            "coverage_degrading_reassignment",
            "near_tie_but_teacher_keeps_r0",
        ),
    ),
    "secondary-failure-50t50r": _intent(
        "secondary_failure",
        (
            "stale_or_expired_plan_candidate",
            "binding_change_boundary_exceeded",
            "coverage_degrading_reassignment",
            "near_tie_but_teacher_keeps_r0",
        ),
    ),
    "high-threat-m-to-n-100t100r": _intent(
        "high_threat_m_to_n",
        (
            "incomplete_m_to_n_coalition",
            "resource_capacity_conflict",
            "coverage_degrading_reassignment",
            "binding_change_boundary_exceeded",
            "near_tie_but_teacher_keeps_r0",
        ),
    ),
    "high-threat-m-to-n-200t200r": _intent(
        "high_threat_m_to_n",
        (
            "incomplete_m_to_n_coalition",
            "resource_capacity_conflict",
            "coverage_degrading_reassignment",
            "binding_change_boundary_exceeded",
            "near_tie_but_teacher_keeps_r0",
        ),
    ),
    "resource-surplus-20t30r": _intent(
        "resource_surplus",
        (
            "near_tie_but_teacher_keeps_r0",
            "resource_capacity_conflict",
            "binding_change_boundary_exceeded",
            "coverage_degrading_reassignment",
        ),
    ),
    "resource-shortage-30t20r": _intent(
        "resource_shortage",
        (
            "coverage_degrading_reassignment",
            "incomplete_m_to_n_coalition",
            "resource_capacity_conflict",
            "binding_change_boundary_exceeded",
            "near_tie_but_teacher_keeps_r0",
        ),
    ),
    "dynamic-add-drop-100t80r": _intent(
        "dynamic_add_drop",
        (
            "coverage_degrading_reassignment",
            "resource_capacity_conflict",
            "binding_change_boundary_exceeded",
            "stale_or_expired_plan_candidate",
            "near_tie_but_teacher_keeps_r0",
        ),
    ),
    "near-tie-hard-negative-50t50r": _intent(
        "near_tie_hard_negative",
        ("near_tie_but_teacher_keeps_r0",),
    ),
}


@dataclass(frozen=True)
class A1V3SidecarCellIntent:
    cell_id: str
    scenario_family: str
    allowed_positive_action_change_types: tuple[str, ...]
    hard_negative_priority: tuple[str, ...]


@dataclass(frozen=True)
class A1V3SidecarClassificationPolicy:
    policy_id: str
    file_sha256: str
    request_file_sha256: str
    near_tie_boundary_file_sha256: str
    binding_change_maximum_changed_target_count: int
    intents: tuple[A1V3SidecarCellIntent, ...]

    @property
    def intents_by_cell(self) -> dict[str, A1V3SidecarCellIntent]:
        return {item.cell_id: item for item in self.intents}


@dataclass(frozen=True)
class A1V3DerivedFrameClassification:
    frame_index: int
    frame_class: str
    hard_negative: bool
    action_change_type: str
    hard_negative_type: str | None

    @property
    def signature(self) -> tuple[int, str, bool, str, str | None]:
        return (
            self.frame_index,
            self.frame_class,
            self.hard_negative,
            self.action_change_type,
            self.hard_negative_type,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": A1_V3_SIDECAR_CLASSIFICATION_SCHEMA_V1,
            "frame_index": self.frame_index,
            "classification": {
                "frame_class": self.frame_class,
                "hard_negative": self.hard_negative,
                "action_change_type": self.action_change_type,
                "hard_negative_type": self.hard_negative_type,
            },
        }


@dataclass(frozen=True)
class A1V3AnonymousTransitionEvidence:
    """Auditable anonymous change axes between two planning frames."""

    frame_index: int
    previous_frame_index: int | None
    target_count_delta: int
    demand_total_delta: int
    target_roster_demand_coupled: bool
    active_resource_count_before: int
    active_resource_count_after: int
    active_resource_added_count: int
    active_resource_removed_count: int
    observed_resource_dimension_delta: int
    teacher_edge_count_delta: int
    coverage_deficit_before: int
    coverage_deficit_after: int
    changed_axes: tuple[str, ...]

    @property
    def coverage_deficit_delta(self) -> int:
        return self.coverage_deficit_after - self.coverage_deficit_before

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "previous_frame_index": self.previous_frame_index,
            "target_count_delta": self.target_count_delta,
            "demand_total_delta": self.demand_total_delta,
            "target_roster_demand_coupled": self.target_roster_demand_coupled,
            "active_resource_count_before": self.active_resource_count_before,
            "active_resource_count_after": self.active_resource_count_after,
            "active_resource_added_count": self.active_resource_added_count,
            "active_resource_removed_count": self.active_resource_removed_count,
            "observed_resource_dimension_delta": (
                self.observed_resource_dimension_delta
            ),
            "teacher_edge_count_delta": self.teacher_edge_count_delta,
            "coverage_deficit_before": self.coverage_deficit_before,
            "coverage_deficit_after": self.coverage_deficit_after,
            "changed_axes": list(self.changed_axes),
        }


def expected_a1_v3_cell_intent_payloads() -> list[dict[str, Any]]:
    return [
        {
            "cell_id": cell_id,
            "scenario_family": scenario_family,
            "allowed_positive_action_change_types": list(positive_actions),
            "hard_negative_priority": list(hard_priority),
        }
        for cell_id, (
            scenario_family,
            positive_actions,
            hard_priority,
        ) in _CELL_INTENT_SPECS.items()
    ]


def load_a1_v3_sidecar_classification_policy(
    path: str | Path = DEFAULT_A1_V3_SIDECAR_CLASSIFICATION_POLICY_PATH,
    *,
    request: A1V3FrozenRequest,
    near_tie_boundary_file_sha256: str,
) -> A1V3SidecarClassificationPolicy:
    """Load the exact policy that turns continuous anonymous frames into labels."""

    file_path = Path(path)
    if file_path.is_symlink():
        _fail("sidecar_classification_policy_symlink_forbidden")
    try:
        content = file_path.read_bytes()
    except OSError as exc:
        _fail("sidecar_classification_policy_read_failed", str(exc))
    try:
        payload = json.loads(content.decode("ascii"), object_pairs_hook=_unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail("sidecar_classification_policy_json_invalid", str(exc))
    policy = _strict_mapping(
        payload,
        {
            "schema_version",
            "policy_id",
            "status",
            "bindings",
            "sequence_contract",
            "boundaries",
            "cell_intents",
            "permissions",
            "content_sha256",
        },
        "sidecar_classification_policy_fields_mismatch",
    )
    if policy["schema_version"] != A1_V3_SIDECAR_CLASSIFICATION_POLICY_SCHEMA_V1:
        _fail("sidecar_classification_policy_schema_mismatch")
    if policy["policy_id"] != A1_V3_SIDECAR_CLASSIFICATION_POLICY_ID:
        _fail("sidecar_classification_policy_id_mismatch")
    if policy["status"] != "frozen_deterministic_classification_only":
        _fail("sidecar_classification_policy_status_mismatch")
    declared_sha = _sha256_value(
        policy["content_sha256"], "sidecar_classification_policy.content_sha256"
    )
    content_payload = dict(policy)
    content_payload.pop("content_sha256")
    if canonical_json_sha256(content_payload) != declared_sha:
        _fail("sidecar_classification_policy_content_sha256_mismatch")

    expected_bindings = {
        "frozen_request": {
            "path": _REQUEST_LOGICAL_PATH,
            "schema_version": A1_V3_REQUEST_SCHEMA_V1,
            "request_id": request.request_id,
            "file_sha256": request.file_sha256,
        },
        "near_tie_boundary": {
            "path": _NEAR_TIE_LOGICAL_PATH,
            "schema_version": _NEAR_TIE_SCHEMA,
            "boundary_id": _NEAR_TIE_ID,
            "file_sha256": near_tie_boundary_file_sha256,
        },
    }
    if policy["bindings"] != expected_bindings:
        _fail("sidecar_classification_policy_binding_mismatch")
    if policy["sequence_contract"] != {
        "frame_order": "strict_contiguous_frame_index",
        "baseline_frame_class": "initial_nonempty_teacher_plan_is_positive",
        "positive_source": (
            "initial_teacher_or_auditable_anonymous_assignment_transition"
        ),
        "negative_source": "no_auditable_anonymous_assignment_transition",
        "caller_classification_override_allowed": False,
        "unsupported_taxonomy_is_rejected": True,
        "quota_failure_mode": "fail_closed_before_stage_write",
    }:
        _fail("sidecar_classification_policy_sequence_contract_mismatch")
    boundaries = _strict_mapping(
        policy["boundaries"],
        {
            "binding_change_maximum_changed_target_count",
            "target_roster_demand_multiset_coupling_required",
            "target_roster_precedes_simultaneous_active_resource_change",
            "active_resource_source",
            "delayed_target_appearance_requires_pending_deficit_closure",
            "single_resource_release_assignment_chain_allowed",
            "structural_hard_negative_requires_candidate_teacher_difference",
            "near_tie_hard_negative_requires_candidate_teacher_difference",
            "hard_negative_requires_effective_teacher_match",
        },
        "sidecar_classification_policy_boundary_fields_mismatch",
    )
    if boundaries != {
        "binding_change_maximum_changed_target_count": 1,
        "target_roster_demand_multiset_coupling_required": True,
        "target_roster_precedes_simultaneous_active_resource_change": True,
        "active_resource_source": "candidate_mask_resource_columns",
        "delayed_target_appearance_requires_pending_deficit_closure": True,
        "single_resource_release_assignment_chain_allowed": True,
        "structural_hard_negative_requires_candidate_teacher_difference": True,
        "near_tie_hard_negative_requires_candidate_teacher_difference": False,
        "hard_negative_requires_effective_teacher_match": True,
    }:
        _fail("sidecar_classification_policy_boundary_mismatch")
    if policy["cell_intents"] != expected_a1_v3_cell_intent_payloads():
        _fail("sidecar_classification_policy_cell_intent_mismatch")
    request_cells = [(item.cell_id, item.scenario_family) for item in request.cells]
    policy_cells = [
        (item["cell_id"], item["scenario_family"])
        for item in policy["cell_intents"]
    ]
    if policy_cells != request_cells:
        _fail("sidecar_classification_policy_request_cell_mismatch")
    if set(request.action_change_types) != _REQUEST_ACTIONS:
        _fail("sidecar_classification_policy_request_action_inventory_mismatch")
    if not _DERIVABLE_HARD_NEGATIVES.issubset(request.hard_negative_types):
        _fail("sidecar_classification_policy_request_hard_inventory_mismatch")
    if policy["permissions"] != {
        name: False for name in A1_V3_PERMISSION_FIELDS
    }:
        _fail("sidecar_classification_policy_permission_mismatch")

    intents = tuple(
        A1V3SidecarCellIntent(
            cell_id=item["cell_id"],
            scenario_family=item["scenario_family"],
            allowed_positive_action_change_types=tuple(
                item["allowed_positive_action_change_types"]
            ),
            hard_negative_priority=tuple(item["hard_negative_priority"]),
        )
        for item in policy["cell_intents"]
    )
    return A1V3SidecarClassificationPolicy(
        policy_id=A1_V3_SIDECAR_CLASSIFICATION_POLICY_ID,
        file_sha256=sha256(content).hexdigest(),
        request_file_sha256=request.file_sha256,
        near_tie_boundary_file_sha256=near_tie_boundary_file_sha256,
        binding_change_maximum_changed_target_count=1,
        intents=intents,
    )


def derive_a1_v3_frame_classifications(
    scheduled_episode: A1V3ScheduledEpisode,
    online_frames: Sequence[A1V3OnlineFrame],
    *,
    request: A1V3FrozenRequest,
    policy: A1V3SidecarClassificationPolicy,
) -> tuple[A1V3DerivedFrameClassification, ...]:
    """Derive immutable class fields from an ordered anonymous episode."""

    intent = policy.intents_by_cell.get(scheduled_episode.cell_id)
    if intent is None or intent.scenario_family != scheduled_episode.scenario_family:
        _fail("sidecar_classification_frozen_intent_missing")
    frames = tuple(online_frames)
    if not frames:
        _fail("sidecar_classification_empty_episode")
    if tuple(frame.source.frame_index for frame in frames) != tuple(range(len(frames))):
        _fail("sidecar_classification_frame_order_mismatch")
    if any(
        frame.source.episode_key != scheduled_episode.episode_key
        or frame.source.cell_id != scheduled_episode.cell_id
        or frame.source.scenario_family != scheduled_episode.scenario_family
        for frame in frames
    ):
        _fail("sidecar_classification_schedule_mismatch")

    results: list[A1V3DerivedFrameClassification] = []
    previous: A1V3OnlineFrame | None = None
    pending_target_appearance_deficit = 0
    for frame in frames:
        action, pending_target_appearance_deficit = _derive_action_change(
            previous,
            frame,
            pending_target_appearance_deficit=pending_target_appearance_deficit,
        )
        if action == _KEEP_ACTION:
            hard_type = _derive_hard_negative_type(frame, intent, policy)
            result = A1V3DerivedFrameClassification(
                frame_index=frame.source.frame_index,
                frame_class="negative",
                hard_negative=hard_type is not None,
                action_change_type=_KEEP_ACTION,
                hard_negative_type=hard_type,
            )
        else:
            if action not in intent.allowed_positive_action_change_types:
                _fail("sidecar_positive_action_outside_frozen_intent", action)
            if action not in request.action_change_types:
                _fail("sidecar_positive_action_not_requested", action)
            result = A1V3DerivedFrameClassification(
                frame_index=frame.source.frame_index,
                frame_class="positive",
                hard_negative=False,
                action_change_type=action,
                hard_negative_type=None,
            )
        results.append(result)
        previous = frame
    return tuple(results)


def _derive_action_change(
    previous: A1V3OnlineFrame | None,
    current: A1V3OnlineFrame,
    *,
    pending_target_appearance_deficit: int,
) -> tuple[str, int]:
    transition = analyze_a1_v3_anonymous_transition(previous, current)
    if previous is None:
        action = "target_appearance_assignment" if current.teacher_edges else _KEEP_ACTION
        return action, 0

    target_delta = transition.target_count_delta
    teacher_changed = set(current.teacher_edges) != set(previous.teacher_edges)
    demand_changed = current.target_demand_slots != previous.target_demand_slots
    active_resource_changed = (
        transition.active_resource_added_count > 0
        or transition.active_resource_removed_count > 0
    )

    if target_delta:
        if not transition.target_roster_demand_coupled:
            _fail("sidecar_target_demand_roster_coupling_invalid")
        if target_delta > 0:
            newly_uncovered = max(0, transition.coverage_deficit_delta)
            return (
                "target_appearance_assignment",
                pending_target_appearance_deficit + newly_uncovered,
            )
        return (
            "target_loss_release",
            min(pending_target_appearance_deficit, transition.coverage_deficit_after),
        )

    if demand_changed and active_resource_changed:
        _fail("sidecar_independent_change_axes_unclassifiable")
    if demand_changed:
        slot_deltas = tuple(
            after - before
            for before, after in zip(
                previous.target_demand_slots,
                current.target_demand_slots,
                strict=True,
            )
        )
        if all(delta >= 0 for delta in slot_deltas) and any(
            delta > 0 for delta in slot_deltas
        ):
            return (
                "m_to_n_demand_increase",
                min(pending_target_appearance_deficit, transition.coverage_deficit_after),
            )
        if all(delta <= 0 for delta in slot_deltas) and any(
            delta < 0 for delta in slot_deltas
        ):
            return (
                "m_to_n_demand_decrease",
                min(pending_target_appearance_deficit, transition.coverage_deficit_after),
            )
        _fail("sidecar_demand_redistribution_unclassifiable")

    if active_resource_changed:
        if (
            transition.active_resource_added_count > 0
            and transition.active_resource_removed_count > 0
        ):
            _fail("sidecar_active_resource_replacement_unclassifiable")
        action = (
            "resource_failure_reassignment"
            if transition.active_resource_removed_count > 0
            else "resource_recovery_reassignment"
        )
        return (
            action,
            min(pending_target_appearance_deficit, transition.coverage_deficit_after),
        )
    if transition.observed_resource_dimension_delta:
        _fail("sidecar_resource_dimension_change_without_active_inventory_change")

    if (
        pending_target_appearance_deficit > 0
        and transition.teacher_edge_count_delta > 0
        and transition.coverage_deficit_delta < 0
    ):
        closed = min(
            pending_target_appearance_deficit,
            transition.teacher_edge_count_delta,
            -transition.coverage_deficit_delta,
        )
        return (
            "target_appearance_assignment",
            pending_target_appearance_deficit - closed,
        )
    if not teacher_changed:
        return _KEEP_ACTION, pending_target_appearance_deficit

    old_by_target = _edges_by_target(previous.teacher_edges)
    new_by_target = _edges_by_target(current.teacher_edges)
    changed_targets = {
        target
        for target in set(old_by_target) | set(new_by_target)
        if old_by_target.get(target, ()) != new_by_target.get(target, ())
    }
    old_resources = Counter(
        resource
        for target in changed_targets
        for resource in old_by_target.get(target, ())
    )
    new_resources = Counter(
        resource
        for target in changed_targets
        for resource in new_by_target.get(target, ())
    )
    released_resources = old_resources - new_resources
    acquired_resources = new_resources - old_resources
    if (
        transition.teacher_edge_count_delta == -1
        and transition.coverage_deficit_delta == 1
        and sum(released_resources.values()) == 1
        and not acquired_resources
    ):
        # A single open alternating chain can rotate several anonymous bindings
        # while producing exactly one auditable resource release.
        return (
            "single_target_rebind_with_resource_release",
            pending_target_appearance_deficit,
        )
    if len(changed_targets) == 1:
        return (
            "single_target_rebind_with_resource_release",
            pending_target_appearance_deficit,
        )
    if old_resources == new_resources and len(changed_targets) == 2:
        return "two_target_pair_swap", pending_target_appearance_deficit
    if old_resources == new_resources and len(changed_targets) >= 3:
        return "multi_target_cycle", pending_target_appearance_deficit
    _fail("sidecar_teacher_change_unclassifiable")


def analyze_a1_v3_anonymous_transition(
    previous: A1V3OnlineFrame | None,
    current: A1V3OnlineFrame,
) -> A1V3AnonymousTransitionEvidence:
    """Derive change axes without identity, truth labels, or caller classes."""

    current_resources = _active_resource_columns(current)
    current_deficit = _coverage_deficit(current)
    if previous is None:
        return A1V3AnonymousTransitionEvidence(
            frame_index=current.source.frame_index,
            previous_frame_index=None,
            target_count_delta=current.observed_target_count,
            demand_total_delta=sum(current.target_demand_slots),
            target_roster_demand_coupled=True,
            active_resource_count_before=0,
            active_resource_count_after=len(current_resources),
            active_resource_added_count=len(current_resources),
            active_resource_removed_count=0,
            observed_resource_dimension_delta=current.observed_resource_count,
            teacher_edge_count_delta=len(current.teacher_edges),
            coverage_deficit_before=0,
            coverage_deficit_after=current_deficit,
            changed_axes=("episode_baseline",),
        )

    previous_resources = _active_resource_columns(previous)
    target_delta = current.observed_target_count - previous.observed_target_count
    demand_delta = sum(current.target_demand_slots) - sum(previous.target_demand_slots)
    added_resources = current_resources - previous_resources
    removed_resources = previous_resources - current_resources
    demand_changed = current.target_demand_slots != previous.target_demand_slots
    teacher_changed = set(current.teacher_edges) != set(previous.teacher_edges)
    axes: list[str] = []
    if target_delta:
        axes.append("target_roster")
    if demand_changed:
        axes.append("target_demand")
    if added_resources or removed_resources:
        axes.append("active_resource_inventory")
    if teacher_changed:
        axes.append("teacher_edges")
    return A1V3AnonymousTransitionEvidence(
        frame_index=current.source.frame_index,
        previous_frame_index=previous.source.frame_index,
        target_count_delta=target_delta,
        demand_total_delta=demand_delta,
        target_roster_demand_coupled=(
            target_delta == 0
            or _target_roster_demand_multiset_is_coupled(
                previous.target_demand_slots,
                current.target_demand_slots,
                target_delta=target_delta,
            )
        ),
        active_resource_count_before=len(previous_resources),
        active_resource_count_after=len(current_resources),
        active_resource_added_count=len(added_resources),
        active_resource_removed_count=len(removed_resources),
        observed_resource_dimension_delta=(
            current.observed_resource_count - previous.observed_resource_count
        ),
        teacher_edge_count_delta=len(current.teacher_edges) - len(previous.teacher_edges),
        coverage_deficit_before=_coverage_deficit(previous),
        coverage_deficit_after=current_deficit,
        changed_axes=tuple(axes),
    )


def _target_roster_demand_multiset_is_coupled(
    previous: Sequence[int],
    current: Sequence[int],
    *,
    target_delta: int,
) -> bool:
    before = Counter(previous)
    after = Counter(current)
    if target_delta > 0:
        return not (before - after) and sum((after - before).values()) == target_delta
    if target_delta < 0:
        return not (after - before) and sum((before - after).values()) == -target_delta
    return before == after


def _active_resource_columns(frame: A1V3OnlineFrame) -> frozenset[int]:
    return frozenset(resource for _, resource in frame.candidate_edges)


def _coverage_deficit(frame: A1V3OnlineFrame) -> int:
    return max(sum(frame.target_demand_slots) - len(frame.teacher_edges), 0)


def _derive_hard_negative_type(
    frame: A1V3OnlineFrame,
    intent: A1V3SidecarCellIntent,
    policy: A1V3SidecarClassificationPolicy,
) -> str | None:
    teacher = set(frame.teacher_edges)
    candidate = set(frame.candidate_selected_edges)
    effective = set(frame.effective_selected_edges)
    if effective != teacher:
        return None

    candidate_by_target = _edges_by_target(frame.candidate_selected_edges)
    teacher_by_target = _edges_by_target(frame.teacher_edges)
    changed_target_count = sum(
        candidate_by_target.get(target, ()) != teacher_by_target.get(target, ())
        for target in set(candidate_by_target) | set(teacher_by_target)
    )
    candidate_resources = [resource for _, resource in frame.candidate_selected_edges]
    candidate_counts = Counter(target for target, _ in frame.candidate_selected_edges)
    candidate_differs = candidate != teacher
    structural_predicates = {
        "incomplete_m_to_n_coalition": any(
            demand > 1 and candidate_counts[target] < demand
            for target, demand in enumerate(frame.target_demand_slots)
        ),
        "coverage_degrading_reassignment": (
            set(candidate_by_target) < set(teacher_by_target)
        ),
        "rule_cost_difference_boundary_exceeded": (
            _rule_cost_difference_boundary_exceeded(frame)
        ),
        "binding_change_boundary_exceeded": (
            changed_target_count
            > policy.binding_change_maximum_changed_target_count
        ),
        "stale_or_expired_plan_candidate": any(
            marker in reason
            for reason in (
                *frame.pre_projection_reason_codes,
                *frame.post_projection_reason_codes,
            )
            for marker in _STALE_REASON_MARKERS
        ),
        "resource_capacity_conflict": (
            len(candidate_resources) != len(set(candidate_resources))
            or any(
                candidate_counts[target] > demand
                for target, demand in enumerate(frame.target_demand_slots)
            )
        ),
    }
    for hard_type in intent.hard_negative_priority:
        if hard_type == "near_tie_but_teacher_keeps_r0":
            if frame.near_tie_qualifying_target_count > 0:
                return hard_type
            continue
        if candidate_differs and structural_predicates.get(hard_type, False):
            return hard_type
    return None


def _rule_cost_difference_boundary_exceeded(frame: A1V3OnlineFrame) -> bool:
    costs = dict(zip(frame.candidate_edges, frame.candidate_edge_rule_costs, strict=True))
    teacher_by_target = _edges_by_target(frame.teacher_edges)
    candidate_by_target = _edges_by_target(frame.candidate_selected_edges)
    for target in set(teacher_by_target) & set(candidate_by_target):
        teacher_costs = [
            costs[edge]
            for edge in ((target, resource) for resource in teacher_by_target[target])
            if edge in costs
        ]
        candidate_costs = [
            costs[edge]
            for edge in ((target, resource) for resource in candidate_by_target[target])
            if edge in costs
        ]
        if not teacher_costs or not candidate_costs:
            continue
        gap = abs(min(candidate_costs) - min(teacher_costs))
        relative = gap / max(abs(min(teacher_costs)), A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR)
        if (
            gap > A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP
            or relative > A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP
        ):
            return True
    return False


def _edges_by_target(
    edges: Sequence[tuple[int, int]],
) -> dict[int, tuple[int, ...]]:
    grouped: dict[int, list[int]] = {}
    for target, resource in edges:
        grouped.setdefault(target, []).append(resource)
    return {
        target: tuple(sorted(resources)) for target, resources in grouped.items()
    }


def _strict_mapping(
    value: Any,
    expected_fields: set[str],
    code: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        _fail(code)
    return value


def _sha256_value(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or not set(value).issubset(set("0123456789abcdef"))
    ):
        _fail("sidecar_classification_sha256_invalid", name)
    return value


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("sidecar_classification_duplicate_json_key", key)
        result[key] = value
    return result


def _fail(code: str, message: str = "") -> None:
    raise A1V3DataContractError(code, message)
