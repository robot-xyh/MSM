"""Out-of-band structural diagnostics for the D3 planner hot path.

The records in this module are benchmark artifacts.  They are never attached
to :class:`AssignmentPlan`, included in plan identity, or consumed by runtime
control code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from hashlib import sha256
import json
from statistics import median
from time import perf_counter
from typing import Any, Mapping, Sequence

import numpy as np

from .costs import CostMatrixResult
from .models import AssignmentPlan, PlannerConfig, ResourceState, TargetTrack
from .planner import AssignmentPlanner
from .planning_evidence import PlanningFrameEvidence
from .solver import HungarianAssignmentSolver


D3_PLANNER_PERFORMANCE_DIAGNOSTIC_SCHEMA_V1 = (
    "d3_planner_performance_diagnostic_v1"
)
D3_PLANNER_PERFORMANCE_BENCHMARK_SCHEMA_V1 = (
    "d3_planner_performance_benchmark_v1"
)
D3_REPRODUCIBLE_ASSIGNMENT_FIXTURE_SCHEMA_V1 = (
    "d3_reproducible_assignment_fixture_v1"
)


@dataclass(frozen=True)
class D3PlannerOperationCounts:
    """Fixed-size structural work record for one planner call."""

    target_count: int
    resource_count: int
    full_pair_count: int
    vectorized_rule_pair_count: int
    candidate_edge_count: int
    candidate_component_count: int
    largest_component_target_count: int
    largest_component_resource_count: int
    hungarian_local_matrix_cell_count: int
    hungarian_dummy_cell_count: int
    hungarian_prepared_cell_count: int
    solver_decoded_row_count: int
    plan_build_call_count: int
    plan_id_generation_count: int
    plan_edge_materialization_count: int
    canonical_edge_hash_call_count: int
    canonical_edge_hash_item_count: int
    input_snapshot_entity_count: int
    hysteresis_candidate_edge_visit_count: int
    hysteresis_binding_rescore_count: int
    evidence_capture_call_count: int
    evidence_matrix_cell_copy_count: int
    evidence_candidate_mask_cell_copy_count: int
    evidence_breakdown_cell_visit_count: int
    evidence_unique_breakdown_sanitize_count: int
    evidence_track_copy_count: int
    evidence_resource_copy_count: int
    evidence_plan_assignment_copy_count: int
    publish_validation_call_count: int

    def to_dict(self) -> dict[str, int]:
        return {str(key): int(value) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class D3PlannerPhaseTimings:
    """Inclusive wall-clock boundaries emitted only by the benchmark."""

    end_to_end_ms: float
    search_matrix_ms: float
    hungarian_ms: float
    plan_payload_ms: float
    plan_edge_evidence_ms: float
    hysteresis_ms: float
    identity_finalize_ms: float
    publish_ms: float
    offline_evidence_ms: float
    canonical_business_hash_ms: float

    def to_dict(self) -> dict[str, float]:
        return {
            str(key): round(float(value), 6)
            for key, value in asdict(self).items()
        }


@dataclass(frozen=True)
class D3ReproducibleAssignmentFixture:
    """Anonymous deterministic input used only for isolated D3 attribution."""

    tracks: tuple[TargetTrack, ...]
    resources: tuple[ResourceState, ...]
    seed: int
    input_sha256: str
    schema_version: str = D3_REPRODUCIBLE_ASSIGNMENT_FIXTURE_SCHEMA_V1


class _TimedHungarianSolver(HungarianAssignmentSolver):
    def __init__(self) -> None:
        super().__init__()
        self.elapsed_s = 0.0
        self.call_count = 0

    def reset_diagnostics(self) -> None:
        self.elapsed_s = 0.0
        self.call_count = 0

    def solve(
        self,
        cost_matrix: np.ndarray,
        unassigned_costs: np.ndarray,
        candidate_mask: np.ndarray | None = None,
    ):
        started = perf_counter()
        try:
            return super().solve(
                cost_matrix,
                unassigned_costs,
                candidate_mask=candidate_mask,
            )
        finally:
            self.elapsed_s += perf_counter() - started
            self.call_count += 1


class _InstrumentedAssignmentPlanner(AssignmentPlanner):
    """Benchmark-only planner that leaves AssignmentPlan payloads untouched."""

    _PHASE_NAMES = (
        "search_matrix",
        "plan_payload",
        "plan_edge_evidence",
        "hysteresis",
        "identity_finalize",
        "publish",
        "offline_evidence",
    )

    def __init__(
        self,
        *,
        config: PlannerConfig,
        capture_offline_evidence: bool,
        reuse_identity_signatures: bool,
    ) -> None:
        self._timed_solver = _TimedHungarianSolver()
        super().__init__(config=config, solver=self._timed_solver)
        self.capture_offline_evidence = bool(capture_offline_evidence)
        self.reuse_identity_signatures = bool(reuse_identity_signatures)
        self.phase_elapsed_s = {name: 0.0 for name in self._PHASE_NAMES}
        self.phase_call_count = {name: 0 for name in self._PHASE_NAMES}
        self.last_rule_matrix_result: CostMatrixResult | None = None
        self.last_effective_matrix_result: CostMatrixResult | None = None

    def reset_diagnostics(self) -> None:
        self.phase_elapsed_s = {name: 0.0 for name in self._PHASE_NAMES}
        self.phase_call_count = {name: 0 for name in self._PHASE_NAMES}
        self.last_rule_matrix_result = None
        self.last_effective_matrix_result = None
        self._timed_solver.reset_diagnostics()

    def _record(self, name: str, started: float) -> None:
        self.phase_elapsed_s[name] += perf_counter() - started
        self.phase_call_count[name] += 1

    def _build_search_matrices(self, *args: Any, **kwargs: Any):
        started = perf_counter()
        try:
            result = super()._build_search_matrices(*args, **kwargs)
            self.last_rule_matrix_result, self.last_effective_matrix_result = result
            return result
        finally:
            self._record("search_matrix", started)

    def _build_plan(self, *args: Any, **kwargs: Any):
        started = perf_counter()
        try:
            return super()._build_plan(*args, **kwargs)
        finally:
            self._record("plan_payload", started)

    def _matrix_evidence_metadata(self, matrix_result: CostMatrixResult):
        started = perf_counter()
        try:
            return super()._matrix_evidence_metadata(matrix_result)
        finally:
            self._record("plan_edge_evidence", started)

    def _filter_candidate(self, *args: Any, **kwargs: Any):
        started = perf_counter()
        try:
            return super()._filter_candidate(*args, **kwargs)
        finally:
            self._record("hysteresis", started)

    def _finalize_identity(self, *args: Any, **kwargs: Any):
        started = perf_counter()
        try:
            return super()._finalize_identity(*args, **kwargs)
        finally:
            self._record("identity_finalize", started)

    def _publish_plan(self, *args: Any, **kwargs: Any):
        started = perf_counter()
        try:
            return super()._publish_plan(*args, **kwargs)
        finally:
            self._record("publish", started)

    def _capture_planning_evidence(self, **kwargs: Any) -> None:
        started = perf_counter()
        try:
            if self.capture_offline_evidence:
                super()._capture_planning_evidence(**kwargs)
                return
            self._latest_planning_context = None
            self._latest_planning_evidence = PlanningFrameEvidence.unavailable(
                reason="benchmark_reference_evidence_bypassed",
                planning_path=str(kwargs["planning_path"]),
            )
        finally:
            self._record("offline_evidence", started)

    def _finalize_and_publish(self, *args: Any, **kwargs: Any):
        if self.reuse_identity_signatures:
            return super()._finalize_and_publish(*args, **kwargs)
        plan = args[0] if args else kwargs["plan"]
        previous_plan = kwargs["previous_plan"]
        result = self._finalize_identity(
            plan,
            previous_plan=previous_plan,
            evaluated_at_s=kwargs["timestamp"],
            forced_replan=kwargs["forced_replan"],
            publish=kwargs["publish"],
        )
        if kwargs["publish"]:
            self.publish_plan(result)
        return result


def build_reproducible_assignment_fixture(
    *,
    count: int = 200,
    seed: int = 42_000,
) -> D3ReproducibleAssignmentFixture:
    """Build a deterministic one-to-one 3D input without online truth labels."""

    if count <= 0:
        raise ValueError("count must be positive")
    rng = np.random.default_rng(int(seed))
    columns = max(1, int(np.ceil(np.sqrt(count))))
    tracks: list[TargetTrack] = []
    resources: list[ResourceState] = []
    for index in range(count):
        row, column = divmod(index, columns)
        base_north = float(column * 85.0)
        base_east = float(row * 85.0)
        target_jitter = rng.uniform(-4.0, 4.0, size=3)
        resource_jitter = rng.uniform(-4.0, 4.0, size=3)
        down = -120.0 - float(index % 5) * 8.0
        tracks.append(
            TargetTrack(
                track_id=f"GT-{index:04d}",
                threat_score=0.55 + 0.4 * float((index % 17) / 16.0),
                covariance=0.04 + 0.002 * float(index % 11),
                window_cost=0.02 * float(index % 7),
                position_ned=(
                    base_north + float(target_jitter[0]),
                    base_east + float(target_jitter[1]),
                    down + float(target_jitter[2]),
                ),
                velocity_ned=(-4.0 - 0.1 * float(index % 9), 0.0, 0.0),
                position_covariance_ned=np.eye(3)
                * (1.0 + 0.01 * float(index % 13)),
                region_id="ALL",
                candidate_resource_region_ids=("ALL",),
                metadata={"fixture_source": "d3_performance", "seed": int(seed)},
            )
        )
        resources.append(
            ResourceState(
                resource_id=f"INT-{index:04d}",
                position_ned=(
                    base_north + 24.0 + float(resource_jitter[0]),
                    base_east - 18.0 + float(resource_jitter[1]),
                    down + float(resource_jitter[2]),
                ),
                velocity_ned=(0.0, 0.0, 0.0),
                position_covariance_ned=np.eye(3) * 0.25,
                max_speed_mps=14.0,
                max_intercept_range_m=5_000.0,
                region_id="ALL",
                reachable_target_region_ids=("ALL",),
                metadata={"fixture_source": "d3_performance", "seed": int(seed)},
            )
        )
    track_items = tuple(tracks)
    resource_items = tuple(resources)
    input_sha256 = _canonical_sha256(
        {
            "schema": D3_REPRODUCIBLE_ASSIGNMENT_FIXTURE_SCHEMA_V1,
            "seed": int(seed),
            "tracks": track_items,
            "resources": resource_items,
        }
    )
    return D3ReproducibleAssignmentFixture(
        tracks=track_items,
        resources=resource_items,
        seed=int(seed),
        input_sha256=input_sha256,
    )


def canonical_plan_binding_sha256(plan: AssignmentPlan) -> str:
    """Hash executable bindings without plan identity or benchmark data."""

    return _canonical_sha256(
        {
            "assignments": tuple(
                sorted(
                    (
                        assignment.target_id,
                        assignment.resource_id,
                        assignment.coalition_id,
                        assignment.coalition_version,
                        assignment.member_role,
                        assignment.wave_id,
                    )
                    for assignment in plan.assignments
                )
            ),
            "unassigned_target_ids": tuple(sorted(plan.unassigned_target_ids)),
            "incomplete_target_ids": tuple(sorted(plan.incomplete_target_ids)),
        }
    )


def canonical_plan_business_sha256(plan: AssignmentPlan) -> str:
    """Hash deterministic plan business content while excluding random identity."""

    payload = {
        field.name: getattr(plan, field.name)
        for field in fields(plan)
        if field.name not in {"plan_id", "previous_plan_id"}
    }
    return _canonical_sha256(_strip_plan_identity(payload))


def run_reproducible_planner_performance_benchmark(
    *,
    count: int = 200,
    seed: int = 42_000,
    max_candidate_edges_per_target: int = 32,
    repeat: int = 3,
) -> dict[str, Any]:
    """Compare equivalent D3 paths and return an out-of-band JSON payload."""

    if max_candidate_edges_per_target <= 0 or repeat <= 0:
        raise ValueError("max_candidate_edges_per_target and repeat must be positive")
    fixture = build_reproducible_assignment_fixture(count=count, seed=seed)
    config = PlannerConfig.scalable_3d(
        max_candidate_edges_per_target=max_candidate_edges_per_target,
        human_authorization_state="approved",
        unassigned_base_cost=50.0,
    )
    _warm_scipy_hungarian()
    modes = (
        ("default", True, True),
        ("identity_recompute_reference", True, False),
        ("evidence_bypass_reference", False, True),
    )
    summaries = []
    for mode, capture_evidence, reuse_signatures in modes:
        runs = tuple(
            _run_two_frame_cycle(
                fixture=fixture,
                config=config,
                mode=mode,
                capture_offline_evidence=capture_evidence,
                reuse_identity_signatures=reuse_signatures,
            )
            for _ in range(repeat)
        )
        summaries.append(_summarize_mode(mode, runs))

    default = summaries[0]
    for summary in summaries[1:]:
        for phase in ("initial", "refresh"):
            if summary[phase]["binding_sha256"] != default[phase]["binding_sha256"]:
                raise AssertionError(f"{summary['mode']} changed D3 bindings")
            if summary[phase]["business_sha256"] != default[phase]["business_sha256"]:
                raise AssertionError(f"{summary['mode']} changed D3 business content")
            if summary[phase]["plan_version"] != default[phase]["plan_version"]:
                raise AssertionError(f"{summary['mode']} changed D3 plan version")

    return {
        "schema": D3_PLANNER_PERFORMANCE_BENCHMARK_SCHEMA_V1,
        "diagnostic_schema": D3_PLANNER_PERFORMANCE_DIAGNOSTIC_SCHEMA_V1,
        "fixture_schema": fixture.schema_version,
        "seed": fixture.seed,
        "target_count": len(fixture.tracks),
        "resource_count": len(fixture.resources),
        "max_candidate_edges_per_target": int(max_candidate_edges_per_target),
        "repeat": int(repeat),
        "input_sha256": fixture.input_sha256,
        "wall_clock_scope": "benchmark_report_only",
        "plan_metadata_contains_performance_diagnostics": False,
        "reference_modes_are_runtime_candidates": False,
        "latest_published_signature_source": "planner_owned_cache",
        "caller_previous_signature_used_as_latest": False,
        "modes": summaries,
        "semantic_equivalence": {
            "bindings_equal": True,
            "plan_versions_equal": True,
            "canonical_business_hashes_equal": True,
            "refresh_reuses_plan_identity": all(
                summary["refresh"]["plan_id_reused"] for summary in summaries
            ),
            "rule_costs_changed": False,
            "hungarian_changed": False,
            "hysteresis_changed": False,
            "d5_d7_binding_changed": False,
        },
    }


def _run_two_frame_cycle(
    *,
    fixture: D3ReproducibleAssignmentFixture,
    config: PlannerConfig,
    mode: str,
    capture_offline_evidence: bool,
    reuse_identity_signatures: bool,
) -> dict[str, Any]:
    planner = _InstrumentedAssignmentPlanner(
        config=config,
        capture_offline_evidence=capture_offline_evidence,
        reuse_identity_signatures=reuse_identity_signatures,
    )
    planner.reset_diagnostics()
    started = perf_counter()
    initial = planner.plan(fixture.tracks, fixture.resources, timestamp=0.0)
    initial_elapsed_s = perf_counter() - started
    initial_record = _build_run_record(
        planner=planner,
        plan=initial,
        previous_plan=None,
        end_to_end_s=initial_elapsed_s,
        evidence_expected=capture_offline_evidence,
    )

    planner.reset_diagnostics()
    started = perf_counter()
    refresh = planner.plan(
        fixture.tracks,
        fixture.resources,
        timestamp=1.0,
        previous_plan=initial,
        expected_previous_version=initial.version,
    )
    refresh_elapsed_s = perf_counter() - started
    refresh_record = _build_run_record(
        planner=planner,
        plan=refresh,
        previous_plan=initial,
        end_to_end_s=refresh_elapsed_s,
        evidence_expected=capture_offline_evidence,
    )
    refresh_record["plan_id_reused"] = refresh.plan_id == initial.plan_id
    return {"mode": mode, "initial": initial_record, "refresh": refresh_record}


def _build_run_record(
    *,
    planner: _InstrumentedAssignmentPlanner,
    plan: AssignmentPlan,
    previous_plan: AssignmentPlan | None,
    end_to_end_s: float,
    evidence_expected: bool,
) -> dict[str, Any]:
    hash_started = perf_counter()
    business_sha256 = canonical_plan_business_sha256(plan)
    hash_elapsed_s = perf_counter() - hash_started
    counts = _operation_counts(
        planner=planner,
        plan=plan,
        previous_plan=previous_plan,
        evidence_expected=evidence_expected,
    )
    timings = D3PlannerPhaseTimings(
        end_to_end_ms=end_to_end_s * 1_000.0,
        search_matrix_ms=planner.phase_elapsed_s["search_matrix"] * 1_000.0,
        hungarian_ms=planner._timed_solver.elapsed_s * 1_000.0,
        plan_payload_ms=planner.phase_elapsed_s["plan_payload"] * 1_000.0,
        plan_edge_evidence_ms=(
            planner.phase_elapsed_s["plan_edge_evidence"] * 1_000.0
        ),
        hysteresis_ms=planner.phase_elapsed_s["hysteresis"] * 1_000.0,
        identity_finalize_ms=(
            planner.phase_elapsed_s["identity_finalize"] * 1_000.0
        ),
        publish_ms=planner.phase_elapsed_s["publish"] * 1_000.0,
        offline_evidence_ms=(
            planner.phase_elapsed_s["offline_evidence"] * 1_000.0
        ),
        canonical_business_hash_ms=hash_elapsed_s * 1_000.0,
    )
    diagnostic_keys = {
        "performance_diagnostic",
        "performance_diagnostics",
        "phase_timings",
        "wall_clock_ms",
    }
    if diagnostic_keys.intersection(plan.metadata):
        raise AssertionError("performance diagnostics leaked into AssignmentPlan metadata")
    return {
        "plan_version": int(plan.version),
        "decision_state": str(plan.decision_state),
        "assignment_count": len(plan.assignments),
        "plan_id_format_valid": bool(
            plan.plan_id.startswith("d3-plan-") and len(plan.plan_id) == 20
        ),
        "plan_id_reused": False,
        "binding_sha256": canonical_plan_binding_sha256(plan),
        "business_sha256": business_sha256,
        "evidence_available": bool(planner.latest_planning_evidence.available),
        "operation_counts": counts.to_dict(),
        "timings": timings.to_dict(),
    }


def _operation_counts(
    *,
    planner: _InstrumentedAssignmentPlanner,
    plan: AssignmentPlan,
    previous_plan: AssignmentPlan | None,
    evidence_expected: bool,
) -> D3PlannerOperationCounts:
    rule = planner.last_rule_matrix_result
    effective = planner.last_effective_matrix_result
    if rule is None or effective is None:
        raise AssertionError("planner benchmark did not retain its matrix boundary")
    mask = np.asarray(effective.hard_safe_candidate_mask, dtype=bool)
    components = _candidate_component_shapes(mask)
    active_components = tuple(item for item in components if item[1] > 0)
    local_cells = sum(targets * resources for targets, resources in active_components)
    dummy_cells = sum(targets * targets for targets, _ in active_components)
    full_pair_count = int(mask.size)
    candidate_edge_count = int(np.count_nonzero(mask))
    plan_build_calls = int(planner.phase_call_count["plan_payload"])
    edge_hash_calls = int(planner.phase_call_count["plan_edge_evidence"])
    edge_materialization = int(
        plan.metadata.get("cost_breakdowns_by_edge_count", 0)
    )
    evidence_available = bool(
        evidence_expected and planner.latest_planning_evidence.available
    )
    matrix_copy_cells = 0
    mask_copy_cells = 0
    breakdown_visits = 0
    unique_breakdowns = 0
    evidence_assignment_copies = 0
    if evidence_available:
        matrix_copy_cells = int(rule.matrix.size + effective.matrix.size)
        mask_copy_cells = int(
            (0 if rule.candidate_mask is None else rule.candidate_mask.size)
            + (
                0
                if effective.candidate_mask is None
                else effective.candidate_mask.size
            )
        )
        grids = [rule.breakdowns]
        if effective.breakdowns is not rule.breakdowns:
            grids.append(effective.breakdowns)
        breakdown_visits = sum(
            sum(len(row) for row in grid) for grid in grids
        )
        unique_breakdowns = len(
            {
                id(value)
                for grid in grids
                for row in grid
                for value in row
            }
        )
        evidence_assignment_copies = len(plan.assignments) + (
            0 if previous_plan is None else len(previous_plan.assignments)
        )
    hysteresis_edges = (
        candidate_edge_count
        if previous_plan is not None and planner.config.enable_hysteresis
        else 0
    )
    binding_rescores = (
        0
        if previous_plan is None or not planner.config.enable_hysteresis
        else len(previous_plan.assignments) + len(plan.assignments)
    )
    return D3PlannerOperationCounts(
        target_count=len(rule.target_ids),
        resource_count=len(rule.resource_ids),
        full_pair_count=full_pair_count,
        vectorized_rule_pair_count=int(
            rule.metadata.get("vectorized_rule_pair_count", full_pair_count)
        ),
        candidate_edge_count=candidate_edge_count,
        candidate_component_count=len(components),
        largest_component_target_count=max(
            (targets for targets, _ in components), default=0
        ),
        largest_component_resource_count=max(
            (resources for _, resources in components), default=0
        ),
        hungarian_local_matrix_cell_count=local_cells,
        hungarian_dummy_cell_count=dummy_cells,
        hungarian_prepared_cell_count=local_cells + dummy_cells,
        solver_decoded_row_count=len(rule.target_ids),
        plan_build_call_count=plan_build_calls,
        plan_id_generation_count=plan_build_calls,
        plan_edge_materialization_count=edge_materialization,
        canonical_edge_hash_call_count=edge_hash_calls,
        canonical_edge_hash_item_count=edge_hash_calls * edge_materialization,
        input_snapshot_entity_count=(
            len(rule.target_ids) * 2 + len(rule.resource_ids)
        ),
        hysteresis_candidate_edge_visit_count=hysteresis_edges,
        hysteresis_binding_rescore_count=binding_rescores,
        evidence_capture_call_count=int(
            planner.phase_call_count["offline_evidence"]
        ),
        evidence_matrix_cell_copy_count=matrix_copy_cells,
        evidence_candidate_mask_cell_copy_count=mask_copy_cells,
        evidence_breakdown_cell_visit_count=breakdown_visits,
        evidence_unique_breakdown_sanitize_count=unique_breakdowns,
        evidence_track_copy_count=(len(rule.target_ids) if evidence_available else 0),
        evidence_resource_copy_count=(
            len(rule.resource_ids) if evidence_available else 0
        ),
        evidence_plan_assignment_copy_count=evidence_assignment_copies,
        publish_validation_call_count=int(planner.phase_call_count["publish"]),
    )


def _candidate_component_shapes(mask: np.ndarray) -> tuple[tuple[int, int], ...]:
    target_count, resource_count = mask.shape
    target_neighbors = tuple(
        tuple(int(value) for value in np.flatnonzero(mask[index]))
        for index in range(target_count)
    )
    resource_neighbors: list[list[int]] = [[] for _ in range(resource_count)]
    rows, columns = np.nonzero(mask)
    for row, column in zip(rows, columns):
        resource_neighbors[int(column)].append(int(row))
    visited: set[int] = set()
    shapes: list[tuple[int, int]] = []
    for start in range(target_count):
        if start in visited:
            continue
        pending = [start]
        targets: set[int] = set()
        resources: set[int] = set()
        while pending:
            target = pending.pop()
            if target in targets:
                continue
            targets.add(target)
            visited.add(target)
            for resource in target_neighbors[target]:
                if resource in resources:
                    continue
                resources.add(resource)
                pending.extend(resource_neighbors[resource])
        shapes.append((len(targets), len(resources)))
    return tuple(shapes)


def _summarize_mode(mode: str, runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def summarize_phase(phase: str) -> dict[str, Any]:
        records = [run[phase] for run in runs]
        reference = records[0]
        for record in records[1:]:
            for key in (
                "plan_version",
                "decision_state",
                "assignment_count",
                "binding_sha256",
                "business_sha256",
                "evidence_available",
                "operation_counts",
                "plan_id_reused",
            ):
                if record[key] != reference[key]:
                    raise AssertionError(f"non-deterministic {mode} {phase} {key}")
        timing_names = tuple(reference["timings"])
        timing_samples = {
            name: [float(record["timings"][name]) for record in records]
            for name in timing_names
        }
        return {
            key: reference[key]
            for key in (
                "plan_version",
                "decision_state",
                "assignment_count",
                "plan_id_format_valid",
                "plan_id_reused",
                "binding_sha256",
                "business_sha256",
                "evidence_available",
                "operation_counts",
            )
        } | {
            "timing_samples_ms": {
                name: [round(value, 6) for value in values]
                for name, values in timing_samples.items()
            },
            "timing_medians_ms": {
                name: round(float(median(values)), 6)
                for name, values in timing_samples.items()
            },
        }

    return {
        "mode": str(mode),
        "initial": summarize_phase("initial"),
        "refresh": summarize_phase("refresh"),
    }


def _warm_scipy_hungarian() -> None:
    solver = HungarianAssignmentSolver()
    solver.solve(np.asarray([[0.0]]), np.asarray([1.0]))


_PLAN_IDENTITY_METADATA_KEYS = frozenset(
    {
        "current_plan_id",
        "previous_plan_id",
        "plan_id",
    }
)


def _strip_plan_identity(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_plan_identity(item)
            for key, item in value.items()
            if str(key) not in _PLAN_IDENTITY_METADATA_KEYS
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _strip_plan_identity(getattr(value, field.name))
            for field in fields(value)
            if field.name not in {"plan_id", "previous_plan_id"}
        }
    if isinstance(value, (tuple, list)):
        return tuple(_strip_plan_identity(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(_strip_plan_identity(item) for item in value))
    return value


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


__all__ = [
    "D3_PLANNER_PERFORMANCE_BENCHMARK_SCHEMA_V1",
    "D3_PLANNER_PERFORMANCE_DIAGNOSTIC_SCHEMA_V1",
    "D3_REPRODUCIBLE_ASSIGNMENT_FIXTURE_SCHEMA_V1",
    "D3PlannerOperationCounts",
    "D3PlannerPhaseTimings",
    "D3ReproducibleAssignmentFixture",
    "build_reproducible_assignment_fixture",
    "canonical_plan_binding_sha256",
    "canonical_plan_business_sha256",
    "run_reproducible_planner_performance_benchmark",
]
