"""Typed, truth-free A1 v3 counterfactual safety projection.

Candidate generation is deliberately completed before an optional effective
reference or its post-projection policy is inspected.  A reference can never
influence candidate edges or pre-projection reason codes.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from math import isfinite
from typing import Any

import numpy as np

from .a1_assignment_aware_development import (
    A1SafeAssignmentProjection,
    project_a1_safe_assignment,
)
from .a1_v3_data_contract import (
    A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP,
    A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP,
    A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR,
)


A1_V3_SOURCE_ONLY_PROJECTION_SCHEMA_V1 = (
    "d3_a1_v3_source_only_counterfactual_safety_projection_v1"
)


class A1V3CounterfactualMode(str, Enum):
    COVERAGE_DEGRADING = "coverage_degrading"
    NEAR_TIE_ALTERNATIVE = "near_tie_alternative"


class A1V3PostProjectionReferencePolicy(str, Enum):
    COVERAGE_FLOOR = "coverage_floor"
    EXACT_SAFE_REFERENCE = "exact_safe_reference"


class A1V3SourceOnlyProjectionError(ValueError):
    """Stable fail-closed input-contract error."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        super().__init__(self.code if message is None else f"{self.code}: {message}")


@dataclass(frozen=True, slots=True)
class A1V3ProjectionPermissions:
    runtime: bool = False
    assignment: bool = False
    plan: bool = False
    control: bool = False
    global_track_id: bool = False

    def __post_init__(self) -> None:
        if any(asdict(self).values()):
            _fail("authority_permission_forbidden")


@dataclass(frozen=True, slots=True)
class A1V3CoverageDiagnostics:
    safety_floor_source: str
    rule_assigned_slot_count: int
    candidate_assigned_slot_count: int
    effective_assigned_slot_count: int
    rule_covered_target_count: int
    candidate_covered_target_count: int
    effective_covered_target_count: int
    lost_floor_covered_target_count: int
    rule_high_threat_assigned_slot_count: int
    candidate_high_threat_assigned_slot_count: int
    effective_high_threat_assigned_slot_count: int
    coverage_fallback_applied: bool


@dataclass(frozen=True, slots=True)
class A1V3SafetyDiagnostics:
    candidate_available: bool
    candidate_duplicate_resource_count: int
    candidate_hard_edge_violation_count: int
    candidate_m_to_n_atomicity_violation_count: int
    candidate_removed_incomplete_target_count: int
    effective_duplicate_resource_count: int
    effective_hard_edge_violation_count: int
    effective_m_to_n_atomicity_violation_count: int
    reference_supplied: bool
    reference_safety_valid: bool | None
    reference_plan_stability_fallback_applied: bool
    near_tie_qualifying_target_count: int


@dataclass(frozen=True, slots=True)
class A1V3SourceOnlyProjectionInput:
    """Strict anonymous input consumed by candidate generation."""

    frame_key: tuple[int, str, int]
    measurement_timestamp_s: float
    arrival_timestamp_s: float
    rule_cost_matrix: np.ndarray
    hard_safe_action_mask: np.ndarray
    target_demand_slots: tuple[int, ...]
    target_threat_scores: tuple[float, ...]
    unassigned_costs: np.ndarray
    previous_selected_edges: tuple[tuple[int, int], ...]
    preregistered_mode: A1V3CounterfactualMode

    def __post_init__(self) -> None:
        frame_key = _frame_key(self.frame_key)
        measurement = _finite_float(
            self.measurement_timestamp_s, "measurement_timestamp_invalid"
        )
        arrival = _finite_float(
            self.arrival_timestamp_s, "arrival_timestamp_invalid"
        )
        if arrival <= measurement:
            _fail("stale_timestamp_order")

        try:
            matrix = np.asarray(self.rule_cost_matrix, dtype=float)
            raw_mask = np.asarray(self.hard_safe_action_mask)
        except (TypeError, ValueError):
            _fail("rule_cost_matrix_invalid")
        if matrix.ndim != 2 or not all(matrix.shape):
            _fail("rule_cost_matrix_shape_invalid")
        if not np.all(np.isfinite(matrix)):
            _fail("rule_cost_matrix_non_finite")
        if raw_mask.shape != matrix.shape or raw_mask.dtype.kind != "b":
            _fail("hard_safe_action_mask_invalid")
        mask = raw_mask.astype(bool, copy=True)
        target_count, resource_count = matrix.shape

        demand = _positive_int_tuple(
            self.target_demand_slots,
            target_count,
            "target_demand_slots_invalid",
        )
        threat = _bounded_float_tuple(
            self.target_threat_scores,
            target_count,
            "target_threat_scores_invalid",
        )
        try:
            unassigned = np.asarray(
                self.unassigned_costs, dtype=float
            ).reshape(-1)
        except (TypeError, ValueError):
            _fail("unassigned_costs_invalid")
        if unassigned.shape != (target_count,) or not np.all(
            np.isfinite(unassigned)
        ):
            _fail("unassigned_costs_invalid")

        previous = _edge_tuple(
            self.previous_selected_edges,
            target_count=target_count,
            resource_count=resource_count,
            code="previous_edges_invalid",
        )
        if any(not bool(mask[row, column]) for row, column in previous):
            _fail("previous_edges_stale")
        if len({column for _, column in previous}) != len(previous):
            _fail("previous_edges_stale")
        try:
            mode = A1V3CounterfactualMode(self.preregistered_mode)
        except (TypeError, ValueError):
            _fail("preregistered_mode_invalid")

        matrix = matrix.copy()
        unassigned = unassigned.copy()
        matrix.setflags(write=False)
        mask.setflags(write=False)
        unassigned.setflags(write=False)
        object.__setattr__(self, "frame_key", frame_key)
        object.__setattr__(self, "measurement_timestamp_s", measurement)
        object.__setattr__(self, "arrival_timestamp_s", arrival)
        object.__setattr__(self, "rule_cost_matrix", matrix)
        object.__setattr__(self, "hard_safe_action_mask", mask)
        object.__setattr__(self, "target_demand_slots", demand)
        object.__setattr__(self, "target_threat_scores", threat)
        object.__setattr__(self, "unassigned_costs", unassigned)
        object.__setattr__(self, "previous_selected_edges", previous)
        object.__setattr__(self, "preregistered_mode", mode)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "A1V3SourceOnlyProjectionInput":
        if not isinstance(value, Mapping):
            _fail("input_mapping_required")
        _reject_forbidden_fields(value)
        required = {
            "frame_key",
            "measurement_timestamp_s",
            "arrival_timestamp_s",
            "rule_cost_matrix",
            "hard_safe_action_mask",
            "target_demand_slots",
            "target_threat_scores",
            "unassigned_costs",
            "previous_selected_edges",
            "preregistered_mode",
        }
        if set(value) != required:
            _fail("input_fields_mismatch")
        return cls(
            frame_key=value["frame_key"],
            measurement_timestamp_s=value["measurement_timestamp_s"],
            arrival_timestamp_s=value["arrival_timestamp_s"],
            rule_cost_matrix=value["rule_cost_matrix"],
            hard_safe_action_mask=value["hard_safe_action_mask"],
            target_demand_slots=value["target_demand_slots"],
            target_threat_scores=value["target_threat_scores"],
            unassigned_costs=value["unassigned_costs"],
            previous_selected_edges=value["previous_selected_edges"],
            preregistered_mode=value["preregistered_mode"],
        )


@dataclass(frozen=True, slots=True)
class A1V3SourceOnlyProjectionOutput:
    frame_key: tuple[int, str, int]
    measurement_timestamp_s: float
    arrival_timestamp_s: float
    preregistered_mode: A1V3CounterfactualMode
    post_projection_reference_policy: A1V3PostProjectionReferencePolicy
    candidate_pre_projection_edges: tuple[tuple[int, int], ...]
    effective_post_projection_edges: tuple[tuple[int, int], ...]
    pre_projection_reason_codes: tuple[str, ...]
    post_projection_reason_codes: tuple[str, ...]
    coverage_diagnostics: A1V3CoverageDiagnostics
    safety_diagnostics: A1V3SafetyDiagnostics
    permissions: A1V3ProjectionPermissions = A1V3ProjectionPermissions()
    schema_version: str = A1_V3_SOURCE_ONLY_PROJECTION_SCHEMA_V1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "frame_key": list(self.frame_key),
            "measurement_timestamp_s": self.measurement_timestamp_s,
            "arrival_timestamp_s": self.arrival_timestamp_s,
            "preregistered_mode": self.preregistered_mode.value,
            "post_projection_reference_policy": (
                self.post_projection_reference_policy.value
            ),
            "candidate_pre_projection_edges": [
                list(edge) for edge in self.candidate_pre_projection_edges
            ],
            "effective_post_projection_edges": [
                list(edge) for edge in self.effective_post_projection_edges
            ],
            "pre_projection_reason_codes": list(
                self.pre_projection_reason_codes
            ),
            "post_projection_reason_codes": list(
                self.post_projection_reason_codes
            ),
            "coverage_diagnostics": asdict(self.coverage_diagnostics),
            "safety_diagnostics": asdict(self.safety_diagnostics),
            "permissions": asdict(self.permissions),
        }


@dataclass(frozen=True, slots=True)
class _ProjectionRecord:
    action_mask: np.ndarray
    rule_cost_matrix: np.ndarray
    target_demand_slots: tuple[int, ...]
    target_threat_scores: tuple[float, ...]
    unassigned_costs: np.ndarray
    previous_selected_edges: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class _EdgeDiagnostics:
    assigned_slot_count: int
    covered_targets: frozenset[int]
    high_threat_assigned_slot_count: int
    duplicate_resource_count: int
    hard_edge_violation_count: int
    m_to_n_atomicity_violation_count: int

    @property
    def safety_valid(self) -> bool:
        return not (
            self.duplicate_resource_count
            or self.hard_edge_violation_count
            or self.m_to_n_atomicity_violation_count
        )


def project_a1_v3_source_only_counterfactual(
    frame: A1V3SourceOnlyProjectionInput,
    *,
    reference_effective_edges: Sequence[tuple[int, int]] | None = None,
    reference_policy: A1V3PostProjectionReferencePolicy = (
        A1V3PostProjectionReferencePolicy.COVERAGE_FLOOR
    ),
) -> A1V3SourceOnlyProjectionOutput:
    """Generate and freeze a source-only candidate, then apply safety fallback."""

    if type(frame) is not A1V3SourceOnlyProjectionInput:
        _fail("input_type_invalid")
    record = _record(frame, frame.hard_safe_action_mask)
    rule_projection = project_a1_safe_assignment(record, frame.rule_cost_matrix)

    if frame.preregistered_mode is A1V3CounterfactualMode.COVERAGE_DEGRADING:
        candidate_projection, available, qualifying_count = _coverage_candidate(
            frame, rule_projection
        )
        generator_reason = (
            "candidate_coverage_degradation_generated_v1"
            if available
            else "candidate_coverage_degradation_unavailable_v1"
        )
    else:
        candidate_projection, available, qualifying_count = _near_tie_candidate(
            frame, rule_projection
        )
        generator_reason = (
            "candidate_near_tie_alternative_generated_v1"
            if available
            else "candidate_near_tie_alternative_unavailable_v1"
        )

    candidate_pre_edges = (
        tuple(candidate_projection.pre_projection_edges)
        if candidate_projection is not None
        else ()
    )
    candidate_post_edges = (
        tuple(candidate_projection.outcome.selected_edges)
        if candidate_projection is not None
        else ()
    )
    pre_reason_items = [generator_reason]
    if (
        candidate_projection is not None
        and candidate_projection.outcome.removed_incomplete_target_count
    ):
        pre_reason_items.append("candidate_all_or_none_projection_applied_v1")
    pre_reasons = tuple(pre_reason_items)

    # Candidate edges and reasons are immutable before this point.  Only the
    # effective post-projection strategy below may inspect policy/reference.
    rule_edges = tuple(rule_projection.outcome.selected_edges)
    rule_diagnostics = _edge_diagnostics(frame, rule_edges)
    candidate_diagnostics = _edge_diagnostics(frame, candidate_post_edges)
    if type(reference_policy) is not A1V3PostProjectionReferencePolicy:
        _fail("post_projection_reference_policy_invalid")
    exact_reference_required = (
        reference_policy
        is A1V3PostProjectionReferencePolicy.EXACT_SAFE_REFERENCE
    )
    reference_supplied = reference_effective_edges is not None
    if exact_reference_required and not reference_supplied:
        _fail("exact_reference_plan_stability_reference_required")
    reference_diagnostics: _EdgeDiagnostics | None = None
    reference_edges: tuple[tuple[int, int], ...] = ()
    reference_reason: str | None = None
    if reference_supplied:
        try:
            reference_edges = _edge_tuple(
                (
                    ()
                    if reference_effective_edges is None
                    else reference_effective_edges
                ),
                target_count=frame.rule_cost_matrix.shape[0],
                resource_count=frame.rule_cost_matrix.shape[1],
                code="reference_edges_invalid",
            )
            reference_diagnostics = _edge_diagnostics(frame, reference_edges)
            if not reference_diagnostics.safety_valid:
                if exact_reference_required:
                    _fail("exact_reference_plan_stability_reference_unsafe")
                reference_reason = "reference_effective_edges_rejected_unsafe_v1"
                reference_diagnostics = None
        except A1V3SourceOnlyProjectionError as exc:
            if exact_reference_required:
                if exc.code == "exact_reference_plan_stability_reference_unsafe":
                    raise
                _fail("exact_reference_plan_stability_reference_invalid")
            reference_reason = "reference_effective_edges_rejected_unsafe_v1"

    if reference_diagnostics is not None:
        floor_source = "reference_effective_edges"
        floor_edges = reference_edges
        floor_diagnostics = reference_diagnostics
    else:
        floor_source = "source_only_rule_projection"
        floor_edges = rule_edges
        floor_diagnostics = rule_diagnostics

    lost_floor_targets = floor_diagnostics.covered_targets.difference(
        candidate_diagnostics.covered_targets
    )
    coverage_regressed = bool(lost_floor_targets) or (
        candidate_diagnostics.high_threat_assigned_slot_count
        < floor_diagnostics.high_threat_assigned_slot_count
    )
    post_reasons: list[str] = []
    if reference_reason is not None:
        post_reasons.append(reference_reason)
    reference_plan_stability_fallback_applied = False
    if exact_reference_required:
        if reference_diagnostics is None:
            _fail("internal_exact_reference_missing")
        if candidate_post_edges != reference_edges:
            effective_edges = reference_edges
            post_reasons.append(
                "effective_reference_plan_stability_fallback_v1"
            )
            fallback_applied = True
            reference_plan_stability_fallback_applied = True
        else:
            effective_edges = candidate_post_edges
            post_reasons.append("effective_reference_plan_stability_match_v1")
            fallback_applied = False
    elif not available:
        effective_edges = floor_edges
        post_reasons.append(
            "effective_reference_fallback_no_candidate_v1"
            if floor_source == "reference_effective_edges"
            else "effective_rule_fallback_no_candidate_v1"
        )
        fallback_applied = True
    elif not candidate_diagnostics.safety_valid:
        effective_edges = floor_edges
        post_reasons.append("effective_safety_fallback_v1")
        fallback_applied = True
    elif coverage_regressed:
        effective_edges = floor_edges
        post_reasons.append(
            "effective_reference_coverage_fallback_v1"
            if floor_source == "reference_effective_edges"
            else "effective_rule_coverage_fallback_v1"
        )
        fallback_applied = True
    else:
        effective_edges = candidate_post_edges
        post_reasons.append("effective_candidate_accepted_v1")
        fallback_applied = False

    effective_diagnostics = _edge_diagnostics(frame, effective_edges)
    if not effective_diagnostics.safety_valid:
        _fail("internal_effective_projection_unsafe")
    return A1V3SourceOnlyProjectionOutput(
        frame_key=frame.frame_key,
        measurement_timestamp_s=frame.measurement_timestamp_s,
        arrival_timestamp_s=frame.arrival_timestamp_s,
        preregistered_mode=frame.preregistered_mode,
        post_projection_reference_policy=reference_policy,
        candidate_pre_projection_edges=candidate_pre_edges,
        effective_post_projection_edges=effective_edges,
        pre_projection_reason_codes=pre_reasons,
        post_projection_reason_codes=tuple(post_reasons),
        coverage_diagnostics=A1V3CoverageDiagnostics(
            safety_floor_source=floor_source,
            rule_assigned_slot_count=rule_diagnostics.assigned_slot_count,
            candidate_assigned_slot_count=candidate_diagnostics.assigned_slot_count,
            effective_assigned_slot_count=effective_diagnostics.assigned_slot_count,
            rule_covered_target_count=len(rule_diagnostics.covered_targets),
            candidate_covered_target_count=len(
                candidate_diagnostics.covered_targets
            ),
            effective_covered_target_count=len(
                effective_diagnostics.covered_targets
            ),
            lost_floor_covered_target_count=len(lost_floor_targets),
            rule_high_threat_assigned_slot_count=(
                rule_diagnostics.high_threat_assigned_slot_count
            ),
            candidate_high_threat_assigned_slot_count=(
                candidate_diagnostics.high_threat_assigned_slot_count
            ),
            effective_high_threat_assigned_slot_count=(
                effective_diagnostics.high_threat_assigned_slot_count
            ),
            coverage_fallback_applied=fallback_applied,
        ),
        safety_diagnostics=A1V3SafetyDiagnostics(
            candidate_available=available,
            candidate_duplicate_resource_count=(
                candidate_diagnostics.duplicate_resource_count
            ),
            candidate_hard_edge_violation_count=(
                candidate_diagnostics.hard_edge_violation_count
            ),
            candidate_m_to_n_atomicity_violation_count=(
                candidate_diagnostics.m_to_n_atomicity_violation_count
            ),
            candidate_removed_incomplete_target_count=(
                candidate_projection.outcome.removed_incomplete_target_count
                if candidate_projection is not None
                else 0
            ),
            effective_duplicate_resource_count=(
                effective_diagnostics.duplicate_resource_count
            ),
            effective_hard_edge_violation_count=(
                effective_diagnostics.hard_edge_violation_count
            ),
            effective_m_to_n_atomicity_violation_count=(
                effective_diagnostics.m_to_n_atomicity_violation_count
            ),
            reference_supplied=reference_supplied,
            reference_safety_valid=(
                None if not reference_supplied else reference_diagnostics is not None
            ),
            reference_plan_stability_fallback_applied=(
                reference_plan_stability_fallback_applied
            ),
            near_tie_qualifying_target_count=qualifying_count,
        ),
    )


def _coverage_candidate(
    frame: A1V3SourceOnlyProjectionInput,
    rule_projection: A1SafeAssignmentProjection,
) -> tuple[A1SafeAssignmentProjection | None, bool, int]:
    assigned = Counter(row for row, _ in rule_projection.outcome.selected_edges)
    covered = [
        index
        for index, demand in enumerate(frame.target_demand_slots)
        if assigned[index] == demand
    ]
    if not covered:
        return None, False, 0
    victim = min(
        covered,
        key=lambda index: (
            frame.target_threat_scores[index],
            frame.target_demand_slots[index],
            index,
        ),
    )
    candidate_mask = frame.hard_safe_action_mask.copy()
    candidate_mask[victim, :] = False
    projection = project_a1_safe_assignment(
        _record(frame, candidate_mask), frame.rule_cost_matrix
    )
    return projection, True, 0


def _near_tie_candidate(
    frame: A1V3SourceOnlyProjectionInput,
    rule_projection: A1SafeAssignmentProjection,
) -> tuple[A1SafeAssignmentProjection | None, bool, int]:
    baseline = set(rule_projection.outcome.selected_edges)
    used_resources = {column for _, column in baseline}
    qualifying: list[
        tuple[float, int, tuple[int, int], tuple[int, int]]
    ] = []
    rows, columns = frame.rule_cost_matrix.shape
    for target_index in range(rows):
        allowed = sorted(
            (
                (
                    float(frame.rule_cost_matrix[target_index, resource]),
                    (target_index, resource),
                )
                for resource in range(columns)
                if frame.hard_safe_action_mask[target_index, resource]
            ),
            key=lambda item: (item[0], item[1]),
        )
        if len(allowed) < 2:
            continue
        (best_cost, best_edge), (second_cost, second_edge) = allowed[:2]
        gap = second_cost - best_cost
        relative = gap / max(
            abs(best_cost), A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR
        )
        if (
            gap <= A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP + 1.0e-12
            and relative <= A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP + 1.0e-12
        ):
            qualifying.append((gap, target_index, best_edge, second_edge))

    for _, target_index, best_edge, second_edge in sorted(qualifying):
        if frame.target_demand_slots[target_index] != 1:
            continue
        if best_edge in baseline and second_edge[1] not in used_resources:
            selected_edge, alternative_edge = best_edge, second_edge
        elif second_edge in baseline and best_edge[1] not in used_resources:
            selected_edge, alternative_edge = second_edge, best_edge
        else:
            continue
        candidate_mask = frame.hard_safe_action_mask.copy()
        candidate_mask[target_index, :] = False
        candidate_mask[alternative_edge] = True
        candidate_matrix = frame.rule_cost_matrix.copy()
        candidate_matrix[alternative_edge] = frame.rule_cost_matrix[selected_edge]
        projection = project_a1_safe_assignment(
            _record(frame, candidate_mask), candidate_matrix
        )
        if (
            alternative_edge in projection.outcome.selected_edges
            and projection.outcome.selected_edges
            != rule_projection.outcome.selected_edges
        ):
            return projection, True, len(qualifying)
    return None, False, len(qualifying)


def _record(
    frame: A1V3SourceOnlyProjectionInput, action_mask: np.ndarray
) -> _ProjectionRecord:
    return _ProjectionRecord(
        action_mask=np.asarray(action_mask, dtype=bool),
        rule_cost_matrix=frame.rule_cost_matrix,
        target_demand_slots=frame.target_demand_slots,
        target_threat_scores=frame.target_threat_scores,
        unassigned_costs=frame.unassigned_costs,
        previous_selected_edges=frame.previous_selected_edges,
    )


def _edge_diagnostics(
    frame: A1V3SourceOnlyProjectionInput,
    edges: Sequence[tuple[int, int]],
) -> _EdgeDiagnostics:
    counts = Counter(row for row, _ in edges)
    resources = [column for _, column in edges]
    covered = frozenset(
        index
        for index, demand in enumerate(frame.target_demand_slots)
        if counts[index] == demand
    )
    high_threat = {
        index
        for index, score in enumerate(frame.target_threat_scores)
        if score >= 0.7
    }
    return _EdgeDiagnostics(
        assigned_slot_count=len(edges),
        covered_targets=covered,
        high_threat_assigned_slot_count=sum(counts[index] for index in high_threat),
        duplicate_resource_count=len(resources) - len(set(resources)),
        hard_edge_violation_count=sum(
            not bool(frame.hard_safe_action_mask[row, column])
            for row, column in edges
        ),
        m_to_n_atomicity_violation_count=sum(
            counts[index] not in (0, demand)
            for index, demand in enumerate(frame.target_demand_slots)
        ),
    )


def _frame_key(value: Any) -> tuple[int, str, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        _fail("frame_key_invalid")
    seed, episode_id, frame_index = value
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed < 0
        or not isinstance(episode_id, str)
        or not episode_id.strip()
        or isinstance(frame_index, bool)
        or not isinstance(frame_index, int)
        or frame_index < 0
    ):
        _fail("frame_key_invalid")
    return (seed, episode_id.strip(), frame_index)


def _edge_tuple(
    value: Sequence[tuple[int, int]],
    *,
    target_count: int,
    resource_count: int,
    code: str,
) -> tuple[tuple[int, int], ...]:
    edges: list[tuple[int, int]] = []
    try:
        items = tuple(value)
    except TypeError:
        _fail(code)
    for raw in items:
        if not isinstance(raw, (tuple, list)) or len(raw) != 2:
            _fail(code)
        row, column = raw
        if (
            isinstance(row, bool)
            or isinstance(column, bool)
            or not isinstance(row, (int, np.integer))
            or not isinstance(column, (int, np.integer))
            or not 0 <= int(row) < target_count
            or not 0 <= int(column) < resource_count
        ):
            _fail(code)
        edges.append((int(row), int(column)))
    if len(edges) != len(set(edges)):
        _fail(code)
    return tuple(sorted(edges))


def _positive_int_tuple(value: Any, size: int, code: str) -> tuple[int, ...]:
    try:
        items = tuple(value)
    except TypeError:
        _fail(code)
    if len(items) != size or any(
        isinstance(item, bool)
        or not isinstance(item, (int, np.integer))
        or int(item) < 1
        for item in items
    ):
        _fail(code)
    return tuple(int(item) for item in items)


def _bounded_float_tuple(value: Any, size: int, code: str) -> tuple[float, ...]:
    try:
        items = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        _fail(code)
    if len(items) != size or any(
        not isfinite(item) or not 0.0 <= item <= 1.0 for item in items
    ):
        _fail(code)
    return items


def _finite_float(value: Any, code: str) -> float:
    if isinstance(value, bool):
        _fail(code)
    try:
        output = float(value)
    except (TypeError, ValueError):
        _fail(code)
    if not isfinite(output):
        _fail(code)
    return output


def _reject_forbidden_fields(value: Any) -> None:
    forbidden = ("truth", "teacher", "reference", "effective", "global_track_id")
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if any(token in normalized for token in forbidden):
                _fail("forbidden_truth_or_identity_field")
            _reject_forbidden_fields(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _reject_forbidden_fields(item)


def _fail(code: str, message: str | None = None) -> None:
    raise A1V3SourceOnlyProjectionError(code, message)


__all__ = [
    "A1V3CounterfactualMode",
    "A1V3PostProjectionReferencePolicy",
    "A1V3SourceOnlyProjectionError",
    "A1V3SourceOnlyProjectionInput",
    "A1V3SourceOnlyProjectionOutput",
    "project_a1_v3_source_only_counterfactual",
]
