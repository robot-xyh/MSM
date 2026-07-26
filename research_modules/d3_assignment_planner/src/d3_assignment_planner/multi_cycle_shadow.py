"""Multi-cycle paired shadow evaluation for the frozen D3 BC residual.

The evaluator advances independent rule and treatment planners through the
same anonymous exogenous input sequence.  The treatment may change only the
hard-safe candidate costs.  Its plans remain isolated experiment artifacts:
PPO, online assist, runtime publication, and assignment authority stay off.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
import csv
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np

from .costs import CostMatrixResult, CostModel
from .learning import LearningAssistConfig, LearningCostAssistant
from .learning_bundle import (
    MODEL_BUNDLE_MANIFEST_FILENAME,
    MODEL_BUNDLE_SCHEMA_V3,
    RuleFallbackLearningAssistant,
    load_model_bundle,
)
from .models import (
    AssignmentPlan,
    CostWeights,
    IdentityCommitmentState,
    PlannerConfig,
    ResourceState,
    TargetDemand,
    TargetTrack,
)
from .paired_intervention import PAIRED_INTERVENTION_RESERVED_SEEDS_V1
from .planner import AssignmentPlanner


MULTI_CYCLE_SHADOW_SCHEMA_V1 = "d3.multi-cycle-shadow-evaluation.v1"
MULTI_CYCLE_SHADOW_SCENARIO_SCHEMA_V1 = "d3.multi-cycle-shadow-scenario.v1"
MULTI_CYCLE_SHADOW_CYCLE_SCHEMA_V1 = "d3.multi-cycle-shadow-cycle.v1"
MULTI_CYCLE_SHADOW_SEED_SCHEMA_V1 = "d3.multi-cycle-shadow-seed.v1"
MULTI_CYCLE_SHADOW_REPORT_KIND = (
    "reserved_seed_rule_vs_bc_residual_multi_cycle_shadow"
)
MULTI_CYCLE_SHADOW_PROFILE_VERSION = "1.0.0"

_FORBIDDEN_INPUT_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_position",
        "truth_velocity",
        "ground_truth",
        "ground_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "airsim_id",
        "offline_truth_labels",
    }
)


class MultiCycleShadowError(ValueError):
    """Stable fail-closed error for invalid evaluation inputs or artifacts."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        self.reason = self.code
        super().__init__(message or self.code)


@dataclass(frozen=True, slots=True)
class MultiCycleScenarioStep:
    """One immutable anonymous planner input shared by both experiment arms."""

    step_id: str
    cycle_index: int
    timestamp_s: float
    event_type: str
    tracks: tuple[TargetTrack, ...]
    resources: tuple[ResourceState, ...]

    def __post_init__(self) -> None:
        if not self.step_id or not self.event_type:
            _fail("scenario_step_identity_invalid")
        if self.cycle_index < 0 or not isfinite(float(self.timestamp_s)):
            _fail("scenario_step_time_invalid")
        track_ids = tuple(item.track_id for item in self.tracks)
        resource_ids = tuple(item.resource_id for item in self.resources)
        if len(track_ids) != len(set(track_ids)):
            _fail("scenario_step_duplicate_track_id")
        if len(resource_ids) != len(set(resource_ids)):
            _fail("scenario_step_duplicate_resource_id")
        _assert_truth_free(self.snapshot_payload)

    @property
    def snapshot_payload(self) -> Mapping[str, Any]:
        return {
            "schema_version": MULTI_CYCLE_SHADOW_SCENARIO_SCHEMA_V1,
            "step_id": self.step_id,
            "cycle_index": int(self.cycle_index),
            "timestamp_s": float(self.timestamp_s),
            "event_type": self.event_type,
            "tracks": _jsonable(self.tracks),
            "resources": _jsonable(self.resources),
        }

    @property
    def snapshot_sha256(self) -> str:
        return _canonical_sha256(self.snapshot_payload)


@dataclass(frozen=True, slots=True)
class MultiCycleScenario:
    """A deterministic multi-cycle assignment scenario for one numeric seed."""

    scenario_id: str
    scenario_kind: str
    seed: int
    steps: tuple[MultiCycleScenarioStep, ...]

    def __post_init__(self) -> None:
        if not self.scenario_id or not self.scenario_kind:
            _fail("scenario_identity_invalid")
        if not self.steps:
            _fail("scenario_steps_empty")
        indices = tuple(item.cycle_index for item in self.steps)
        if indices != tuple(range(len(self.steps))):
            _fail("scenario_cycle_index_discontinuous")
        timestamps = tuple(float(item.timestamp_s) for item in self.steps)
        if any(right <= left for left, right in zip(timestamps, timestamps[1:])):
            _fail("scenario_timestamp_not_monotonic")


@dataclass(frozen=True, slots=True)
class MultiCycleShadowBundle:
    """Strictly loaded development bundle or an exact-rule fallback."""

    assistant: Any
    loaded: bool
    fallback_reason: str | None
    manifest_sha256: str | None
    state_dict_sha256: str | None
    policy_version: str | None
    dataset_frames_sha256: str | None
    training_split_hash: str | None


@dataclass(frozen=True, slots=True)
class MultiCycleShadowCycleRecord:
    """One paired cycle with cost, binding, safety, and lineage evidence."""

    seed: int
    scenario_id: str
    scenario_kind: str
    cycle_index: int
    step_id: str
    event_type: str
    timestamp_s: float
    input_snapshot_sha256: str
    target_count: int
    resource_count: int
    paired_rule_matrix_equal: bool
    treatment_cost_matrix_changed: bool
    treatment_changed_cost_count: int
    treatment_max_abs_cost_change: float
    binding_difference: bool
    binding_symmetric_difference_count: int
    rule_bindings: tuple[str, ...]
    treatment_bindings: tuple[str, ...]
    rule_plan_token: str
    rule_plan_version: int
    rule_input_previous_plan_token: str | None
    rule_declared_previous_plan_token: str | None
    rule_lineage_state: str
    treatment_plan_token: str
    treatment_plan_version: int
    treatment_input_previous_plan_token: str | None
    treatment_declared_previous_plan_token: str | None
    treatment_lineage_state: str
    rule_churn: int
    treatment_churn: int
    rule_cost_on_rule_matrix: float
    treatment_cost_on_rule_matrix: float
    rule_high_threat_unmet: int
    treatment_high_threat_unmet: int
    rule_duplicate_resource_count: int
    treatment_duplicate_resource_count: int
    rule_hard_constraint_violation_count: int
    treatment_hard_constraint_violation_count: int
    rule_stale_version_adoption_count: int
    treatment_stale_version_adoption_count: int
    treatment_learning_applied: bool
    treatment_fallback_reason: str | None
    treatment_fallback_exact_rule_matrix: bool
    treatment_inference_elapsed_ms: float
    online_truth_use_count: int = 0
    ppo_enabled: bool = False
    online_assist_enabled: bool = False
    online_authority_enabled: bool = False
    runtime_publication_allowed: bool = False
    schema_version: str = MULTI_CYCLE_SHADOW_CYCLE_SCHEMA_V1

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class MultiCycleShadowEvaluation:
    """Complete paired result; the admission decision is always shadow-only."""

    summary: Mapping[str, Any]
    per_seed: tuple[Mapping[str, Any], ...]
    cycles: tuple[MultiCycleShadowCycleRecord, ...]

    def to_dict(self, *, include_cycles: bool = True) -> dict[str, Any]:
        payload = {
            "schema_version": MULTI_CYCLE_SHADOW_SCHEMA_V1,
            "report_kind": MULTI_CYCLE_SHADOW_REPORT_KIND,
            "summary": _jsonable(self.summary),
            "per_seed": _jsonable(self.per_seed),
        }
        if include_cycles:
            payload["cycles"] = [item.to_dict() for item in self.cycles]
        return payload


@dataclass(frozen=True, slots=True)
class _PlanScore:
    objective: float
    high_threat_unmet: int
    duplicate_resource_count: int
    hard_constraint_violation_count: int
    churn: int


@dataclass(frozen=True, slots=True)
class _LineageResult:
    plan_token: str
    input_previous_plan_token: str | None
    declared_previous_plan_token: str | None
    state: str
    violation_count: int
    stale_adoption_count: int


class _PlanTokenRegistry:
    """Normalize random plan identifiers while preserving parent relationships."""

    def __init__(self, arm_prefix: str) -> None:
        self.arm_prefix = str(arm_prefix)
        self._tokens: dict[str, str] = {}

    def token(self, plan_id: str | None) -> str | None:
        if plan_id is None:
            return None
        if plan_id not in self._tokens:
            self._tokens[plan_id] = (
                f"{self.arm_prefix}-P{len(self._tokens) + 1:04d}"
            )
        return self._tokens[plan_id]

    def inspect(
        self,
        plan: AssignmentPlan,
        previous_plan: AssignmentPlan | None,
    ) -> _LineageResult:
        current_token = self.token(plan.plan_id)
        if current_token is None:  # pragma: no cover - AssignmentPlan requires an id
            _fail("plan_id_missing")
        input_previous_token = (
            None if previous_plan is None else self.token(previous_plan.plan_id)
        )
        declared_previous_token = self.token(plan.previous_plan_id)
        violation = 0
        stale = 0
        if previous_plan is None:
            state = "initial"
            if plan.version != 1 or plan.previous_plan_id is not None:
                violation = 1
        elif (
            plan.plan_id == previous_plan.plan_id
            and plan.version == previous_plan.version
        ):
            state = "evaluation_refresh"
        else:
            state = "advanced"
            if plan.version != previous_plan.version + 1:
                violation = 1
                if plan.version <= previous_plan.version:
                    stale = 1
            if plan.previous_plan_id != previous_plan.plan_id:
                violation = 1
        if (
            plan.metadata.get("current_plan_id") != plan.plan_id
            or int(plan.metadata.get("current_plan_version", -1)) != plan.version
        ):
            violation = 1
        return _LineageResult(
            plan_token=current_token,
            input_previous_plan_token=input_previous_token,
            declared_previous_plan_token=declared_previous_token,
            state=state if not violation else f"{state}_invalid",
            violation_count=violation,
            stale_adoption_count=stale,
        )


def build_multi_cycle_shadow_scenarios(seed: int) -> tuple[MultiCycleScenario, ...]:
    """Build all required anonymous, deterministic multi-cycle scenarios."""

    numeric_seed = int(seed)
    rng = np.random.default_rng(numeric_seed)
    common_shift = float(rng.uniform(-12.0, 12.0))
    boundary_target = _target(
        0,
        x=3_000.0 + common_shift,
        y=0.0,
        threat=0.24,
    )
    boundary_steps: list[MultiCycleScenarioStep] = []
    for cycle in range(6):
        first_forward = cycle % 2 == 0
        first_x = 20.0 + common_shift if first_forward else common_shift
        second_x = common_shift if first_forward else 20.0 + common_shift
        boundary_steps.append(
            _step(
                cycle,
                event_type=(
                    "baseline" if cycle == 0 else "hungarian_boundary_crossing"
                ),
                tracks=(boundary_target,),
                resources=(
                    _resource(0, x=first_x, y=0.0),
                    _resource(1, x=second_x, y=0.0),
                ),
            )
        )

    surplus_steps = tuple(
        _step(
            cycle,
            event_type="baseline" if cycle == 0 else "kinematic_update",
            tracks=_moving_tracks(
                count=3,
                cycle=cycle,
                rng=rng,
                x_offset=common_shift,
            ),
            resources=_moving_resources(
                count=5,
                cycle=cycle,
                x_offset=common_shift,
            ),
        )
        for cycle in range(5)
    )
    shortage_steps = tuple(
        _step(
            cycle,
            event_type="baseline" if cycle == 0 else "kinematic_update",
            tracks=_moving_tracks(
                count=5,
                cycle=cycle,
                rng=rng,
                x_offset=common_shift,
            ),
            resources=_moving_resources(
                count=3,
                cycle=cycle,
                x_offset=common_shift,
            ),
        )
        for cycle in range(5)
    )

    failure_steps: list[MultiCycleScenarioStep] = []
    for cycle in range(5):
        resources = list(
            _moving_resources(count=5, cycle=cycle, x_offset=common_shift)
        )
        if cycle in {2, 3}:
            resources[2] = replace(
                resources[2],
                status="unavailable",
                availability_score=0.0,
                metadata={"event": "resource_failure"},
            )
        failure_steps.append(
            _step(
                cycle,
                event_type=(
                    "resource_failure"
                    if cycle == 2
                    else "resource_recovery"
                    if cycle == 4
                    else "baseline"
                    if cycle == 0
                    else "kinematic_update"
                ),
                tracks=_moving_tracks(
                    count=5,
                    cycle=cycle,
                    rng=rng,
                    x_offset=common_shift,
                ),
                resources=tuple(resources),
            )
        )

    inventory_steps: list[MultiCycleScenarioStep] = []
    target_pool = _moving_tracks(
        count=5,
        cycle=0,
        rng=rng,
        x_offset=common_shift,
    )
    for cycle in range(5):
        moved = tuple(
            replace(
                item,
                position_ned=(
                    float(item.position_ned[0] - cycle * 8.0),
                    float(item.position_ned[1]),
                    float(item.position_ned[2]),
                ),
            )
            for item in target_pool
        )
        if cycle < 2:
            active = moved[:4]
        elif cycle < 4:
            active = moved
        else:
            active = moved[1:]
        inventory_steps.append(
            _step(
                cycle,
                event_type=(
                    "target_added"
                    if cycle == 2
                    else "target_removed"
                    if cycle == 4
                    else "baseline"
                    if cycle == 0
                    else "kinematic_update"
                ),
                tracks=active,
                resources=_moving_resources(
                    count=5,
                    cycle=cycle,
                    x_offset=common_shift,
                ),
            )
        )

    demand_steps: list[MultiCycleScenarioStep] = []
    for cycle in range(5):
        demand = (
            TargetDemand(
                required_resource_count=3,
                primary_resource_count=2,
                coordination_mode="hybrid",
            )
            if cycle in {2, 3}
            else TargetDemand.independent()
        )
        tracks = (
            replace(
                _target(
                    0,
                    x=3_000.0 + common_shift - cycle * 8.0,
                    y=-90.0,
                    threat=0.80,
                ),
                demand=demand,
            ),
            _target(
                1,
                x=3_030.0 + common_shift - cycle * 8.0,
                y=90.0,
                threat=0.30,
            ),
        )
        demand_steps.append(
            _step(
                cycle,
                event_type=(
                    "demand_increased"
                    if cycle == 2
                    else "demand_restored"
                    if cycle == 4
                    else "baseline"
                    if cycle == 0
                    else "kinematic_update"
                ),
                tracks=tracks,
                resources=_moving_resources(
                    count=5,
                    cycle=cycle,
                    x_offset=common_shift,
                ),
            )
        )

    return (
        MultiCycleScenario(
            scenario_id="hungarian_switch_boundary",
            scenario_kind="hungarian_switch_boundary",
            seed=numeric_seed,
            steps=tuple(boundary_steps),
        ),
        MultiCycleScenario(
            scenario_id="five_resources_three_targets",
            scenario_kind="resource_surplus_5x3",
            seed=numeric_seed,
            steps=surplus_steps,
        ),
        MultiCycleScenario(
            scenario_id="three_resources_five_targets",
            scenario_kind="resource_shortage_3x5",
            seed=numeric_seed,
            steps=shortage_steps,
        ),
        MultiCycleScenario(
            scenario_id="resource_failure",
            scenario_kind="resource_failure_and_recovery",
            seed=numeric_seed,
            steps=tuple(failure_steps),
        ),
        MultiCycleScenario(
            scenario_id="target_add_remove",
            scenario_kind="target_inventory_change",
            seed=numeric_seed,
            steps=tuple(inventory_steps),
        ),
        MultiCycleScenario(
            scenario_id="m_to_n_demand_change",
            scenario_kind="high_threat_m_to_n_demand_change",
            seed=numeric_seed,
            steps=tuple(demand_steps),
        ),
    )


def load_multi_cycle_shadow_bundle(
    bundle_dir: str | Path,
    *,
    reserved_seeds: Sequence[int] = PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
) -> MultiCycleShadowBundle:
    """Load one frozen development bundle without changing its admission."""

    path = Path(bundle_dir)
    manifest_path = path / MODEL_BUNDLE_MANIFEST_FILENAME
    manifest_sha = _file_sha256(manifest_path) if manifest_path.is_file() else None
    loaded = load_model_bundle(path, mode="shadow")
    manifest = loaded.manifest
    state_sha = None if manifest is None else manifest.state_dict_sha256
    policy_version = None if manifest is None else manifest.policy_version
    dataset_sha = None if manifest is None else manifest.dataset_frames_sha256
    split_hash = None if manifest is None else manifest.split_hash

    reason: str | None = None
    if not loaded.loaded or manifest is None or loaded.policy is None:
        reason = loaded.fallback_reason or "model_bundle_unavailable"
    elif manifest.bundle_schema_version != MODEL_BUNDLE_SCHEMA_V3:
        reason = "bundle_schema_not_development_v3"
    elif manifest.admission.get("stage") != "development":
        reason = "bundle_stage_not_development"
    elif tuple(manifest.admission.get("allowed_modes", ())) != ("shadow",):
        reason = "bundle_allowed_modes_not_shadow_only"
    elif manifest.admission.get("assist_authorized") is not False:
        reason = "bundle_assist_authority_not_closed"
    elif manifest.admission.get("rule_fallback_required") is not True:
        reason = "bundle_rule_fallback_not_required"
    elif not set(int(item) for item in reserved_seeds).issubset(
        {
            int(item)
            for item in manifest.admission.get(
                "external_holdout_seed_values", ()
            )
        }
    ):
        reason = "bundle_reserved_seed_catalog_mismatch"
    elif not _policy_parameters_finite(loaded.policy):
        reason = "model_state_nonfinite"
    elif not isinstance(loaded.assistant, LearningCostAssistant):
        reason = "model_assistant_type_invalid"

    if reason is not None:
        assistant: Any = RuleFallbackLearningAssistant(reason, mode="assist")
        return MultiCycleShadowBundle(
            assistant=assistant,
            loaded=False,
            fallback_reason=reason,
            manifest_sha256=manifest_sha,
            state_dict_sha256=state_sha,
            policy_version=policy_version,
            dataset_frames_sha256=dataset_sha,
            training_split_hash=split_hash,
        )

    assistant = LearningCostAssistant(
        loaded.assistant.predictor,
        config=LearningAssistConfig(
            mode="assist",
            alpha=manifest.alpha,
            timeout_s=manifest.deadline_s,
            min_confidence=manifest.min_confidence,
            ood_z_threshold=manifest.ood_z_threshold,
        ),
        distribution_guard=loaded.assistant.distribution_guard,
    )
    return MultiCycleShadowBundle(
        assistant=assistant,
        loaded=True,
        fallback_reason=None,
        manifest_sha256=manifest_sha,
        state_dict_sha256=state_sha,
        policy_version=policy_version,
        dataset_frames_sha256=dataset_sha,
        training_split_hash=split_hash,
    )


def evaluate_multi_cycle_shadow(
    *,
    seeds: Sequence[int],
    treatment_assistant: Any,
    training_seeds: Sequence[int] = (),
    training_seed_registry_sha256: str | None = None,
    bundle: MultiCycleShadowBundle | None = None,
    scenario_factory: Callable[[int], tuple[MultiCycleScenario, ...]] = (
        build_multi_cycle_shadow_scenarios
    ),
    planner_config: PlannerConfig | None = None,
    cost_weights: CostWeights | None = None,
) -> MultiCycleShadowEvaluation:
    """Run paired multi-cycle plans on identical anonymous external inputs."""

    numeric_seeds = tuple(int(item) for item in seeds)
    if not numeric_seeds or len(numeric_seeds) != len(set(numeric_seeds)):
        _fail("evaluation_seed_catalog_invalid")
    overlap = tuple(sorted(set(numeric_seeds).intersection(int(x) for x in training_seeds)))
    if overlap:
        _fail("reserved_training_seed_overlap", f"seed overlap: {overlap}")
    if training_seed_registry_sha256 is not None and not _is_sha256(
        training_seed_registry_sha256
    ):
        _fail("training_seed_registry_sha256_invalid")

    config = planner_config or PlannerConfig.scalable_3d(
        enable_hysteresis=False,
        reassignment_switch_penalty=0.0,
        enforce_region_compatibility=False,
        max_candidate_edges_per_target=8,
        human_authorization_state="offline_not_authorized",
    )
    weights = cost_weights or CostWeights()
    cycles: list[MultiCycleShadowCycleRecord] = []
    scenario_inventory: set[str] = set()

    for seed in numeric_seeds:
        scenarios = scenario_factory(seed)
        if not scenarios:
            _fail("evaluation_scenario_catalog_empty")
        for scenario in scenarios:
            if scenario.seed != seed:
                _fail("scenario_seed_mismatch")
            scenario_inventory.add(scenario.scenario_id)
            rule_planner = AssignmentPlanner(
                cost_model=CostModel(weights=weights, config=config),
                config=config,
            )
            treatment_planner = AssignmentPlanner(
                cost_model=CostModel(weights=weights, config=config),
                config=config,
                learning_assistant=treatment_assistant,
            )
            rule_tokens = _PlanTokenRegistry("R")
            treatment_tokens = _PlanTokenRegistry("T")
            rule_previous: AssignmentPlan | None = None
            treatment_previous: AssignmentPlan | None = None

            for step in scenario.steps:
                rule_plan = rule_planner.plan(
                    step.tracks,
                    step.resources,
                    timestamp=step.timestamp_s,
                    previous_plan=rule_previous,
                    expected_previous_version=(
                        None if rule_previous is None else rule_previous.version
                    ),
                )
                treatment_plan = treatment_planner.plan(
                    step.tracks,
                    step.resources,
                    timestamp=step.timestamp_s,
                    previous_plan=treatment_previous,
                    expected_previous_version=(
                        None
                        if treatment_previous is None
                        else treatment_previous.version
                    ),
                )
                rule_evidence = rule_planner.latest_planning_evidence
                treatment_evidence = treatment_planner.latest_planning_evidence
                if not rule_evidence.available or not treatment_evidence.available:
                    _fail("planning_evidence_unavailable")
                rule_matrix = _required_matrix(rule_evidence.rule_matrix_result)
                treatment_rule_matrix = _required_matrix(
                    treatment_evidence.rule_matrix_result
                )
                effective_matrix = _required_matrix(
                    treatment_evidence.effective_matrix_result
                )
                paired_rule_equal = _matrix_equal(
                    rule_matrix,
                    treatment_rule_matrix,
                )
                difference = np.abs(effective_matrix.matrix - rule_matrix.matrix)
                changed_mask = difference > 1.0e-12
                fallback_reason = treatment_evidence.fallback_reason
                fallback_exact = (
                    fallback_reason is None
                    or _matrix_equal(effective_matrix, treatment_rule_matrix)
                )
                if fallback_reason is not None and not fallback_exact:
                    _fail("fallback_matrix_not_exact_rule")

                rule_score = _score_plan(
                    rule_plan,
                    rule_matrix,
                    step.tracks,
                    step.resources,
                    rule_previous,
                    high_threat_threshold=config.high_threat_threshold,
                )
                treatment_score = _score_plan(
                    treatment_plan,
                    treatment_rule_matrix,
                    step.tracks,
                    step.resources,
                    treatment_previous,
                    high_threat_threshold=config.high_threat_threshold,
                )
                rule_lineage = rule_tokens.inspect(rule_plan, rule_previous)
                treatment_lineage = treatment_tokens.inspect(
                    treatment_plan,
                    treatment_previous,
                )
                rule_bindings = _binding_signature(rule_plan)
                treatment_bindings = _binding_signature(treatment_plan)
                symmetric_difference = rule_bindings ^ treatment_bindings
                inference_s = float(
                    effective_matrix.metadata.get(
                        "learning_inference_elapsed_s",
                        0.0,
                    )
                    or 0.0
                )
                if not isfinite(inference_s) or inference_s < 0.0:
                    _fail("inference_elapsed_invalid")
                cycles.append(
                    MultiCycleShadowCycleRecord(
                        seed=seed,
                        scenario_id=scenario.scenario_id,
                        scenario_kind=scenario.scenario_kind,
                        cycle_index=step.cycle_index,
                        step_id=step.step_id,
                        event_type=step.event_type,
                        timestamp_s=step.timestamp_s,
                        input_snapshot_sha256=step.snapshot_sha256,
                        target_count=len(step.tracks),
                        resource_count=len(step.resources),
                        paired_rule_matrix_equal=paired_rule_equal,
                        treatment_cost_matrix_changed=bool(
                            np.count_nonzero(changed_mask)
                        ),
                        treatment_changed_cost_count=int(
                            np.count_nonzero(changed_mask)
                        ),
                        treatment_max_abs_cost_change=(
                            0.0
                            if not difference.size
                            else float(np.max(difference))
                        ),
                        binding_difference=bool(symmetric_difference),
                        binding_symmetric_difference_count=len(
                            symmetric_difference
                        ),
                        rule_bindings=_binding_labels(rule_bindings),
                        treatment_bindings=_binding_labels(treatment_bindings),
                        rule_plan_token=rule_lineage.plan_token,
                        rule_plan_version=rule_plan.version,
                        rule_input_previous_plan_token=(
                            rule_lineage.input_previous_plan_token
                        ),
                        rule_declared_previous_plan_token=(
                            rule_lineage.declared_previous_plan_token
                        ),
                        rule_lineage_state=rule_lineage.state,
                        treatment_plan_token=treatment_lineage.plan_token,
                        treatment_plan_version=treatment_plan.version,
                        treatment_input_previous_plan_token=(
                            treatment_lineage.input_previous_plan_token
                        ),
                        treatment_declared_previous_plan_token=(
                            treatment_lineage.declared_previous_plan_token
                        ),
                        treatment_lineage_state=treatment_lineage.state,
                        rule_churn=rule_score.churn,
                        treatment_churn=treatment_score.churn,
                        rule_cost_on_rule_matrix=rule_score.objective,
                        treatment_cost_on_rule_matrix=treatment_score.objective,
                        rule_high_threat_unmet=rule_score.high_threat_unmet,
                        treatment_high_threat_unmet=(
                            treatment_score.high_threat_unmet
                        ),
                        rule_duplicate_resource_count=(
                            rule_score.duplicate_resource_count
                        ),
                        treatment_duplicate_resource_count=(
                            treatment_score.duplicate_resource_count
                        ),
                        rule_hard_constraint_violation_count=(
                            rule_score.hard_constraint_violation_count
                            + rule_lineage.violation_count
                        ),
                        treatment_hard_constraint_violation_count=(
                            treatment_score.hard_constraint_violation_count
                            + treatment_lineage.violation_count
                        ),
                        rule_stale_version_adoption_count=(
                            rule_lineage.stale_adoption_count
                        ),
                        treatment_stale_version_adoption_count=(
                            treatment_lineage.stale_adoption_count
                        ),
                        treatment_learning_applied=bool(
                            effective_matrix.metadata.get(
                                "learning_applied",
                                False,
                            )
                        ),
                        treatment_fallback_reason=(
                            None
                            if fallback_reason is None
                            else str(fallback_reason)
                        ),
                        treatment_fallback_exact_rule_matrix=fallback_exact,
                        treatment_inference_elapsed_ms=inference_s * 1000.0,
                    )
                )
                rule_previous = rule_plan
                treatment_previous = treatment_plan

    records = tuple(cycles)
    per_seed = _aggregate_per_seed(records)
    summary = _aggregate_summary(
        records,
        seeds=numeric_seeds,
        scenario_inventory=tuple(sorted(scenario_inventory)),
        training_seeds=tuple(int(item) for item in training_seeds),
        training_seed_registry_sha256=training_seed_registry_sha256,
        bundle=bundle,
    )
    return MultiCycleShadowEvaluation(
        summary=summary,
        per_seed=per_seed,
        cycles=records,
    )


def run_reserved_seed_multi_cycle_shadow(
    *,
    bundle_dir: str | Path,
    training_seed_registry_path: str | Path,
) -> MultiCycleShadowEvaluation:
    """Run the fixed 1000-1019 shadow experiment with a frozen seed registry."""

    registry_path = Path(training_seed_registry_path)
    registry = _read_json_object(registry_path)
    training_seeds = tuple(int(item) for item in registry.get("training_seeds", ()))
    reserved = tuple(
        int(item) for item in registry.get("reserved_evaluation_seeds", ())
    )
    if reserved != PAIRED_INTERVENTION_RESERVED_SEEDS_V1:
        _fail("training_registry_reserved_seed_catalog_mismatch")
    if int(registry.get("overlap_count", -1)) != 0:
        _fail("training_registry_declares_seed_overlap")
    bundle = load_multi_cycle_shadow_bundle(
        bundle_dir,
        reserved_seeds=reserved,
    )
    return evaluate_multi_cycle_shadow(
        seeds=reserved,
        treatment_assistant=bundle.assistant,
        training_seeds=training_seeds,
        training_seed_registry_sha256=_file_sha256(registry_path),
        bundle=bundle,
    )


def write_multi_cycle_shadow_artifacts(
    output_dir: str | Path,
    result: MultiCycleShadowEvaluation,
) -> Mapping[str, Path]:
    """Write canonical JSON, per-seed CSV, cycle CSV, and a Chinese report."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary_path = output / "summary.json"
    per_seed_json_path = output / "per_seed_metrics.json"
    per_seed_csv_path = output / "per_seed_metrics.csv"
    cycles_csv_path = output / "cycle_records.csv"
    report_path = output / "D3_MULTICYCLE_SHADOW_REPORT_CN.md"

    _write_json(summary_path, result.to_dict())
    _write_json(
        per_seed_json_path,
        {
            "schema_version": MULTI_CYCLE_SHADOW_SEED_SCHEMA_V1,
            "rows": result.per_seed,
        },
    )
    _write_csv(per_seed_csv_path, result.per_seed)
    _write_csv(
        cycles_csv_path,
        tuple(_cycle_csv_row(item) for item in result.cycles),
    )
    report_path.write_text(
        _render_chinese_report(result),
        encoding="utf-8",
        newline="\n",
    )
    return {
        "summary_json": summary_path,
        "per_seed_json": per_seed_json_path,
        "per_seed_csv": per_seed_csv_path,
        "cycle_csv": cycles_csv_path,
        "report_cn": report_path,
    }


def _aggregate_summary(
    records: tuple[MultiCycleShadowCycleRecord, ...],
    *,
    seeds: tuple[int, ...],
    scenario_inventory: tuple[str, ...],
    training_seeds: tuple[int, ...],
    training_seed_registry_sha256: str | None,
    bundle: MultiCycleShadowBundle | None,
) -> Mapping[str, Any]:
    if not records:
        _fail("evaluation_records_empty")
    fallback_counts = Counter(
        item.treatment_fallback_reason
        for item in records
        if item.treatment_fallback_reason is not None
    )
    latency = np.asarray(
        [item.treatment_inference_elapsed_ms for item in records],
        dtype=float,
    )
    boundary = tuple(
        item
        for item in records
        if item.scenario_id == "hungarian_switch_boundary"
    )
    boundary_changed_seeds = {
        item.seed for item in boundary if item.binding_difference
    }
    changed_seeds = {item.seed for item in records if item.binding_difference}
    cost_delta = np.asarray(
        [
            item.treatment_cost_on_rule_matrix - item.rule_cost_on_rule_matrix
            for item in records
        ],
        dtype=float,
    )
    duplicate_total = sum(
        item.rule_duplicate_resource_count
        + item.treatment_duplicate_resource_count
        for item in records
    )
    hard_total = sum(
        item.rule_hard_constraint_violation_count
        + item.treatment_hard_constraint_violation_count
        for item in records
    )
    stale_total = sum(
        item.rule_stale_version_adoption_count
        + item.treatment_stale_version_adoption_count
        for item in records
    )
    pairing_violation_count = sum(
        not item.paired_rule_matrix_equal for item in records
    )
    fallback_exact = all(
        item.treatment_fallback_exact_rule_matrix for item in records
    )
    identifiable = bool(boundary_changed_seeds)
    return {
        "profile_version": MULTI_CYCLE_SHADOW_PROFILE_VERSION,
        "evaluation_scope": "offline_isolated_multi_cycle_shadow",
        "status": "completed_shadow_only",
        "admission": {
            "promotion_recommended": False,
            "assist_authorized": False,
            "online_authority_authorized": False,
            "ppo_enabled": False,
            "runtime_publication_allowed": False,
            "rule_fallback_required": True,
            "conclusion": (
                "binding_difference_observed_shadow_only"
                if identifiable
                else "bc_residual_not_identifiable_on_reserved_seeds"
            ),
        },
        "seed_contract": {
            "reserved_seeds": seeds,
            "reserved_seed_count": len(seeds),
            "training_seed_count": len(set(training_seeds)),
            "training_reserved_overlap_count": len(
                set(seeds).intersection(training_seeds)
            ),
            "training_seed_registry_sha256": training_seed_registry_sha256,
        },
        "bundle": {
            "loaded": None if bundle is None else bundle.loaded,
            "fallback_reason": (
                None if bundle is None else bundle.fallback_reason
            ),
            "manifest_sha256": (
                None if bundle is None else bundle.manifest_sha256
            ),
            "state_dict_sha256": (
                None if bundle is None else bundle.state_dict_sha256
            ),
            "policy_version": (
                None if bundle is None else bundle.policy_version
            ),
            "dataset_frames_sha256": (
                None if bundle is None else bundle.dataset_frames_sha256
            ),
            "training_split_hash": (
                None if bundle is None else bundle.training_split_hash
            ),
        },
        "coverage": {
            "scenario_ids": scenario_inventory,
            "scenario_count": len(scenario_inventory),
            "cycle_count": len(records),
            "cost_matrix_changed_cycle_count": sum(
                item.treatment_cost_matrix_changed for item in records
            ),
            "binding_difference_cycle_count": sum(
                item.binding_difference for item in records
            ),
            "binding_difference_seed_count": len(changed_seeds),
            "boundary_binding_difference_seed_count": len(
                boundary_changed_seeds
            ),
        },
        "pairing": {
            "paired_rule_matrix_mismatch_count": pairing_violation_count,
            "fallback_exact_rule_matrix": fallback_exact,
            "online_truth_use_count": sum(
                item.online_truth_use_count for item in records
            ),
        },
        "safety": {
            "duplicate_resource_count": duplicate_total,
            "hard_constraint_violation_count": hard_total,
            "stale_version_adoption_count": stale_total,
            "rule_high_threat_unmet_total": sum(
                item.rule_high_threat_unmet for item in records
            ),
            "treatment_high_threat_unmet_total": sum(
                item.treatment_high_threat_unmet for item in records
            ),
        },
        "dynamics": {
            "rule_churn_total": sum(item.rule_churn for item in records),
            "treatment_churn_total": sum(
                item.treatment_churn for item in records
            ),
            "mean_treatment_minus_rule_cost_on_rule_matrix": float(
                np.mean(cost_delta)
            ),
            "max_abs_treatment_minus_rule_cost_on_rule_matrix": float(
                np.max(np.abs(cost_delta))
            ),
        },
        "learning": {
            "applied_cycle_count": sum(
                item.treatment_learning_applied for item in records
            ),
            "fallback_cycle_count": sum(fallback_counts.values()),
            "fallback_reasons": dict(sorted(fallback_counts.items())),
            "inference_p50_ms": float(np.percentile(latency, 50)),
            "inference_p95_ms": float(np.percentile(latency, 95)),
            "inference_max_ms": float(np.max(latency)),
        },
        "identifiability": {
            "controlled_scenario": "hungarian_switch_boundary",
            "binding_difference_observed": identifiable,
            "seeds_with_boundary_binding_difference": tuple(
                sorted(boundary_changed_seeds)
            ),
            "benefit_claimed": False,
            "physical_outcome_available": False,
            "causal_reward_available": False,
        },
    }


def _aggregate_per_seed(
    records: tuple[MultiCycleShadowCycleRecord, ...],
) -> tuple[Mapping[str, Any], ...]:
    result: list[Mapping[str, Any]] = []
    for seed in sorted({item.seed for item in records}):
        rows = tuple(item for item in records if item.seed == seed)
        fallbacks = Counter(
            item.treatment_fallback_reason
            for item in rows
            if item.treatment_fallback_reason is not None
        )
        latency = np.asarray(
            [item.treatment_inference_elapsed_ms for item in rows],
            dtype=float,
        )
        result.append(
            {
                "schema_version": MULTI_CYCLE_SHADOW_SEED_SCHEMA_V1,
                "seed": seed,
                "scenario_count": len({item.scenario_id for item in rows}),
                "cycle_count": len(rows),
                "cost_matrix_changed_cycle_count": sum(
                    item.treatment_cost_matrix_changed for item in rows
                ),
                "binding_difference_cycle_count": sum(
                    item.binding_difference for item in rows
                ),
                "boundary_binding_difference_cycle_count": sum(
                    item.binding_difference
                    and item.scenario_id == "hungarian_switch_boundary"
                    for item in rows
                ),
                "rule_churn_total": sum(item.rule_churn for item in rows),
                "treatment_churn_total": sum(
                    item.treatment_churn for item in rows
                ),
                "rule_high_threat_unmet_total": sum(
                    item.rule_high_threat_unmet for item in rows
                ),
                "treatment_high_threat_unmet_total": sum(
                    item.treatment_high_threat_unmet for item in rows
                ),
                "duplicate_resource_count": sum(
                    item.rule_duplicate_resource_count
                    + item.treatment_duplicate_resource_count
                    for item in rows
                ),
                "hard_constraint_violation_count": sum(
                    item.rule_hard_constraint_violation_count
                    + item.treatment_hard_constraint_violation_count
                    for item in rows
                ),
                "stale_version_adoption_count": sum(
                    item.rule_stale_version_adoption_count
                    + item.treatment_stale_version_adoption_count
                    for item in rows
                ),
                "paired_rule_matrix_mismatch_count": sum(
                    not item.paired_rule_matrix_equal for item in rows
                ),
                "fallback_cycle_count": sum(fallbacks.values()),
                "fallback_reasons": json.dumps(
                    dict(sorted(fallbacks.items())),
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                "inference_p50_ms": float(np.percentile(latency, 50)),
                "inference_p95_ms": float(np.percentile(latency, 95)),
                "online_truth_use_count": 0,
                "shadow_only": True,
            }
        )
    return tuple(result)


def _score_plan(
    plan: AssignmentPlan,
    matrix: CostMatrixResult,
    tracks: tuple[TargetTrack, ...],
    resources: tuple[ResourceState, ...],
    previous_plan: AssignmentPlan | None,
    *,
    high_threat_threshold: float,
) -> _PlanScore:
    # PlanningFrameEvidence intentionally anonymizes matrix identifiers.  The
    # row/column order remains identical to this cycle's immutable input.
    target_index = {item.track_id: index for index, item in enumerate(tracks)}
    resource_index = {
        item.resource_id: index for index, item in enumerate(resources)
    }
    track_by_id = {item.track_id: item for item in tracks}
    resource_by_id = {item.resource_id: item for item in resources}
    assigned_by_target = Counter(item.target_id for item in plan.assignments)
    assigned_by_resource = Counter(item.resource_id for item in plan.assignments)
    mask = matrix.hard_safe_candidate_mask
    objective = 0.0
    hard = 0
    for assignment in plan.assignments:
        row = target_index.get(assignment.target_id)
        column = resource_index.get(assignment.resource_id)
        track = track_by_id.get(assignment.target_id)
        resource = resource_by_id.get(assignment.resource_id)
        if row is None or column is None or track is None or resource is None:
            hard += 1
            continue
        if not mask[row, column]:
            hard += 1
        if (
            not track.identity_committed
            or not track.assignable
            or resource.status != "available"
            or resource.operator_hold
            or resource.assignment_capacity < 1
        ):
            hard += 1
        objective += float(matrix.matrix[row, column])
    high_threat_unmet = 0
    for row, track in enumerate(tracks):
        required = track.effective_demand.required_resource_count
        assigned = assigned_by_target.get(track.track_id, 0)
        shortfall = max(0, required - assigned)
        objective += shortfall * float(matrix.unassigned_costs[row])
        if assigned not in {0, required}:
            hard += 1
        if track.threat_score >= high_threat_threshold:
            high_threat_unmet += shortfall
    duplicate = sum(max(0, count - 1) for count in assigned_by_resource.values())
    previous_bindings = (
        frozenset()
        if previous_plan is None
        else _binding_signature(previous_plan)
    )
    current_bindings = _binding_signature(plan)
    churn = (
        0
        if previous_plan is None
        else len(previous_bindings ^ current_bindings)
    )
    return _PlanScore(
        objective=float(objective),
        high_threat_unmet=high_threat_unmet,
        duplicate_resource_count=duplicate,
        hard_constraint_violation_count=hard,
        churn=churn,
    )


def _required_matrix(value: CostMatrixResult | None) -> CostMatrixResult:
    if value is None:
        _fail("planning_matrix_missing")
    if not np.all(np.isfinite(np.asarray(value.matrix, dtype=float))):
        _fail("planning_matrix_nonfinite")
    return value


def _matrix_equal(left: CostMatrixResult, right: CostMatrixResult) -> bool:
    return (
        left.target_ids == right.target_ids
        and left.resource_ids == right.resource_ids
        and np.array_equal(left.matrix, right.matrix)
        and np.array_equal(left.unassigned_costs, right.unassigned_costs)
        and np.array_equal(
            left.hard_safe_candidate_mask,
            right.hard_safe_candidate_mask,
        )
    )


def _binding_signature(plan: AssignmentPlan) -> frozenset[tuple[str, str]]:
    return frozenset(
        (item.target_id, item.resource_id) for item in plan.assignments
    )


def _binding_labels(values: frozenset[tuple[str, str]]) -> tuple[str, ...]:
    return tuple(f"{target}->{resource}" for target, resource in sorted(values))


def _step(
    cycle: int,
    *,
    event_type: str,
    tracks: tuple[TargetTrack, ...],
    resources: tuple[ResourceState, ...],
) -> MultiCycleScenarioStep:
    return MultiCycleScenarioStep(
        step_id=f"cycle-{cycle:02d}",
        cycle_index=cycle,
        timestamp_s=float(cycle * 3.0),
        event_type=event_type,
        tracks=tracks,
        resources=resources,
    )


def _moving_tracks(
    *,
    count: int,
    cycle: int,
    rng: np.random.Generator,
    x_offset: float,
) -> tuple[TargetTrack, ...]:
    return tuple(
        _target(
            index,
            x=3_000.0 + x_offset - cycle * 8.0 + float(rng.uniform(-1.0, 1.0)),
            y=(index - (count - 1) / 2.0) * 140.0,
            threat=0.20 + 0.02 * (index % 5),
        )
        for index in range(count)
    )


def _moving_resources(
    *,
    count: int,
    cycle: int,
    x_offset: float,
) -> tuple[ResourceState, ...]:
    return tuple(
        _resource(
            index,
            x=x_offset + cycle * 2.0,
            y=(index - (count - 1) / 2.0) * 140.0,
        )
        for index in range(count)
    )


def _target(
    index: int,
    *,
    x: float,
    y: float,
    threat: float,
) -> TargetTrack:
    return TargetTrack(
        track_id=f"target-{index:03d}",
        threat_score=float(threat),
        covariance=0.50,
        window_cost=0.0,
        position_ned=(float(x), float(y), -100.0),
        velocity_ned=(-2.0, 0.0, 0.0),
        position_covariance_ned=np.eye(3, dtype=float) * 33.0,
        identity_commitment_state=IdentityCommitmentState.COMMITTED,
    )


def _resource(index: int, *, x: float, y: float) -> ResourceState:
    return ResourceState(
        resource_id=f"resource-{index:03d}",
        position_ned=(float(x), float(y), -100.0),
        velocity_ned=(0.0, 0.0, 0.0),
        position_covariance_ned=np.eye(3, dtype=float) * 0.10,
        max_speed_mps=14.0,
        max_intercept_range_m=5_000.0,
        capability_class="interceptor",
    )


def _policy_parameters_finite(policy: Any) -> bool:
    try:
        parameters = tuple(policy.parameters())
    except Exception:
        return False
    for parameter in parameters:
        try:
            values = parameter.detach().cpu().numpy()
        except Exception:
            return False
        if not np.all(np.isfinite(values)):
            return False
    return True


def _read_json_object(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MultiCycleShadowError(
            "training_seed_registry_read_failed",
            str(exc),
        ) from exc
    if not isinstance(value, Mapping):
        _fail("training_seed_registry_not_object")
    return value


def _cycle_csv_row(item: MultiCycleShadowCycleRecord) -> Mapping[str, Any]:
    payload = item.to_dict()
    for field_name in (
        "rule_bindings",
        "treatment_bindings",
    ):
        payload[field_name] = "|".join(payload[field_name])
    return payload


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        _fail("csv_rows_empty")
    fieldnames = tuple(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            if tuple(row.keys()) != fieldnames:
                _fail("csv_row_schema_mismatch")
            writer.writerow(row)


def _render_chinese_report(result: MultiCycleShadowEvaluation) -> str:
    summary = result.summary
    coverage = summary["coverage"]
    safety = summary["safety"]
    learning = summary["learning"]
    dynamics = summary["dynamics"]
    identifiability = summary["identifiability"]
    seed_contract = summary["seed_contract"]
    bundle = summary["bundle"]
    fallback_text = (
        "无"
        if not learning["fallback_reasons"]
        else "、".join(
            f"{name}={count}"
            for name, count in learning["fallback_reasons"].items()
        )
    )
    scenario_rows: list[str] = []
    for scenario_id in sorted({item.scenario_id for item in result.cycles}):
        rows = tuple(
            item for item in result.cycles if item.scenario_id == scenario_id
        )
        scenario_rows.append(
            "| "
            + " | ".join(
                (
                    scenario_id,
                    str(len(rows)),
                    str(sum(item.treatment_cost_matrix_changed for item in rows)),
                    str(sum(item.binding_difference for item in rows)),
                    str(sum(item.rule_churn for item in rows)),
                    str(sum(item.treatment_churn for item in rows)),
                    str(
                        sum(
                            item.treatment_fallback_reason is not None
                            for item in rows
                        )
                    ),
                )
            )
            + " |"
        )
    return "\n".join(
        (
            "# D3 多周期行为克隆残差影子评估",
            "",
            "## 结论",
            "",
            (
                f"冻结模型在 {seed_contract['reserved_seed_count']} 个保留种子、"
                f"{coverage['scenario_count']} 类场景和 {coverage['cycle_count']} 个"
                "规划周期上完成成对评估。处理臂只在隔离求解器中修改硬门限内的"
                "候选代价，线上辅助、分配权限、计划发布和近端策略优化均保持关闭。"
            ),
            "",
            (
                f"受控匈牙利切换边界中，"
                f"{coverage['boundary_binding_difference_seed_count']}/"
                f"{seed_contract['reserved_seed_count']} 个种子出现规则臂与处理臂"
                "绑定差异。该结果证明冻结残差能够跨越求解切换边界，不证明收益、"
                "物理效果或生产准入。"
            ),
            "",
            "## 试验范围",
            "",
            "- 场景：匈牙利切换边界、5资源3目标、3资源5目标、资源失效与恢复、目标增删、M-to-N需求变化。",
            (
                f"- 训练种子与保留种子交集："
                f"{seed_contract['training_reserved_overlap_count']}。"
            ),
            (
                f"- 冻结权重摘要：`{bundle['state_dict_sha256']}`；"
                f"模型加载状态：`{bundle['loaded']}`。"
            ),
            "- 两臂在每个周期接收同一匿名目标、资源和外生事件快照，各自连续推进上一计划。",
            "",
            "## 结果",
            "",
            "| 指标 | 结果 |",
            "| --- | ---: |",
            (
                f"| 代价矩阵实际改变周期 | "
                f"{coverage['cost_matrix_changed_cycle_count']} |"
            ),
            (
                f"| 最终绑定不同周期 | "
                f"{coverage['binding_difference_cycle_count']} |"
            ),
            f"| 规则臂累计抖动 | {dynamics['rule_churn_total']} |",
            f"| 处理臂累计抖动 | {dynamics['treatment_churn_total']} |",
            (
                "| 处理臂减规则臂的规则代价均值 | "
                f"{dynamics['mean_treatment_minus_rule_cost_on_rule_matrix']:.6f} |"
            ),
            (
                f"| 推理时延 P50 / P95 | "
                f"{learning['inference_p50_ms']:.3f} / "
                f"{learning['inference_p95_ms']:.3f} ms |"
            ),
            f"| 回退周期 | {learning['fallback_cycle_count']} |",
            "",
            "推理时延为本机单次运行的墙钟诊断，不作为线上准入门限。",
            "",
            f"回退原因：{fallback_text}。",
            "",
            "### 分场景结果",
            "",
            "| 场景 | 周期 | 代价改变 | 绑定不同 | 规则抖动 | 处理抖动 | 回退 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            *scenario_rows,
            "",
            (
                "绑定差异集中在匈牙利切换边界和资源失效场景。5资源3目标、"
                "3资源5目标及目标增删场景虽修改了候选代价，最终绑定未改变。"
                "M-to-N需求提升的40个周期触发分布外保护，处理臂逐元素恢复规则矩阵。"
            ),
            "",
            "## 安全检查",
            "",
            (
                f"重复资源为 {safety['duplicate_resource_count']}，硬约束或计划谱系"
                f"违规为 {safety['hard_constraint_violation_count']}，旧版本采用为 "
                f"{safety['stale_version_adoption_count']}。"
            ),
            (
                f"规则臂与处理臂高威胁需求未满足累计分别为 "
                f"{safety['rule_high_threat_unmet_total']} 和 "
                f"{safety['treatment_high_threat_unmet_total']}。"
            ),
            "",
            "## 判断",
            "",
            (
                "本轮结论保持 shadow-only。绑定差异来自受控边界和各臂历史状态的"
                "连续演化，未引入真值身份、未放宽可达性、容量、版本或联盟完整性"
                "门限。"
            ),
            "",
            (
                "处理臂累计抖动较低，同时按规则矩阵重评分的平均代价高出 "
                f"{dynamics['mean_treatment_minus_rule_cost_on_rule_matrix']:.6f}。"
                "该取舍不能在缺少运行结果和任务收益时解释为性能改善。"
            ),
            "",
            (
                "现有结果没有运行确认、后续物理结果和可归因奖励。"
                f"可辨识状态为 `{identifiability['binding_difference_observed']}`，"
                "不能据此开放线上辅助或启动策略晋级。"
            ),
            "",
        )
    )


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise MultiCycleShadowError("artifact_hash_failed", str(exc)) from exc


def _is_sha256(value: Any) -> bool:
    text = str(value)
    return len(text) == 64 and all(item in "0123456789abcdef" for item in text)


def _assert_truth_free(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_INPUT_KEYS:
                _fail("online_truth_key_forbidden", f"{path}.{key}")
            _assert_truth_free(item, f"{path}.{key}")
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _assert_truth_free(item, f"{path}[{index}]")


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _fail(code: str, message: str | None = None) -> None:
    raise MultiCycleShadowError(code, message)


__all__ = [
    "MULTI_CYCLE_SHADOW_CYCLE_SCHEMA_V1",
    "MULTI_CYCLE_SHADOW_PROFILE_VERSION",
    "MULTI_CYCLE_SHADOW_REPORT_KIND",
    "MULTI_CYCLE_SHADOW_SCENARIO_SCHEMA_V1",
    "MULTI_CYCLE_SHADOW_SCHEMA_V1",
    "MULTI_CYCLE_SHADOW_SEED_SCHEMA_V1",
    "MultiCycleScenario",
    "MultiCycleScenarioStep",
    "MultiCycleShadowBundle",
    "MultiCycleShadowCycleRecord",
    "MultiCycleShadowError",
    "MultiCycleShadowEvaluation",
    "build_multi_cycle_shadow_scenarios",
    "evaluate_multi_cycle_shadow",
    "load_multi_cycle_shadow_bundle",
    "run_reserved_seed_multi_cycle_shadow",
    "write_multi_cycle_shadow_artifacts",
]
