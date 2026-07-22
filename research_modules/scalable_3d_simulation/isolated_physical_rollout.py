"""Checkpoint-based paired D3/D7 physical rollouts with strict D6 artifacts.

The producer consumes the common D1-D4 intervention frame prepared by
``reserved_seed_interventions``.  It clones that evaluator-only world state,
applies the exact D3 control and treatment plans to separate D7 controllers,
and advances two independent point-mass worlds only while the frozen plan is
valid.  Online guidance sees center-owned track estimates and ownship state;
truth identity and truth trajectories are written only to D6 offline files.

The resulting confirmation remains an isolated simulation receipt.  It is not
a production runtime acknowledgement and does not establish a causal effect.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence
import uuid

import numpy as np

from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
    IsolatedPlanConsumptionValidator,
    build_isolated_execution_plan,
    build_isolated_plan_consumption_evidence,
)
from research_modules.d7_proportional_guidance.d7_proportional_guidance import (
    AssignmentGuidanceBinding,
    AssignmentPairGuidanceInput3D,
    D4GuidancePermission,
    IsolatedArmGuidanceExecutor3D,
    IsolatedGuidanceExecutionContextV1,
    build_isolated_guidance_lineage_record_v1,
    canonical_guidance_sha256,
)

from .episode_bus import jsonable
from .reserved_seed_interventions import (
    ReservedSeedInterventionExecution,
    ReservedSeedSourceEvidence,
)
from .world import VectorizedPointMassWorld


ISOLATED_PHYSICAL_ROLLOUT_SCHEMA_VERSION = (
    "scalable3d-checkpoint-paired-physical-rollout-v2"
)
ISOLATED_PLAN_PUBLICATION_SCHEMA = "d3.isolated-plan-publication.v1"
ISOLATED_PLAN_CONSUMPTION_SCHEMA = (
    "d3.isolated-plan-consumption-confirmation.v1"
)
ISOLATED_PLAN_CONSUMPTION_SCOPE = "paired_isolated_simulation_only"
D3_ISOLATED_EXECUTION_CONTRACT_SCHEMA = (
    "scalable3d-d3-isolated-execution-contract-v1"
)
ISOLATED_WORLD_APPLICATION_SCHEMA = (
    "scalable3d-isolated-world-application.v1"
)
ISOLATED_ARM_MANIFEST_SCHEMA = (
    "scalable3d-isolated-arm-episode-manifest-v1"
)
INITIAL_STATE_SCHEMA = "scalable3d-paired-initial-state-v1"
SENSOR_SCHEDULE_SCHEMA = "scalable3d-exogenous-sensor-schedule-v1"
COMMUNICATION_SCHEDULE_SCHEMA = (
    "scalable3d-exogenous-communication-schedule-v1"
)
FAULT_SCHEDULE_SCHEMA = "scalable3d-exogenous-fault-schedule-v1"
OFFLINE_IDENTITY_SCHEMA = "d6.paired-isolated-offline-identity.v1"
OFFLINE_TRUTH_STATE_SCHEMA = "scalable3d-offline-truth-state-sample.v1"

_ARM_KINDS = ("control", "treatment")
_EPS = 1.0e-9


@dataclass(frozen=True, slots=True)
class CheckpointPhysicalRolloutOptions:
    """Physical continuation limits applied to every reserved seed pair."""

    maximum_duration_s: float | None = None
    minimum_control_cycle_count: int = 2
    evaluate_with_d6: bool = True
    created_at_utc: str = "2026-07-22T00:00:00Z"

    def __post_init__(self) -> None:
        if self.maximum_duration_s is not None:
            duration = float(self.maximum_duration_s)
            if not math.isfinite(duration) or duration <= 0.0:
                raise ValueError("maximum_duration_s must be positive and finite")
            object.__setattr__(self, "maximum_duration_s", duration)
        if int(self.minimum_control_cycle_count) < 2:
            raise ValueError("minimum_control_cycle_count must be at least two")
        object.__setattr__(
            self,
            "minimum_control_cycle_count",
            int(self.minimum_control_cycle_count),
        )
        if not str(self.created_at_utc).strip():
            raise ValueError("created_at_utc must be non-empty")


@dataclass(frozen=True, slots=True)
class IsolatedPhysicalArmResult:
    """All in-memory producer records for one isolated point-mass world."""

    arm_kind: str
    episode_id: str
    world_id: str
    duration_s: float
    plan_payload: Mapping[str, Any]
    plan_payload_sha256: str
    d3_contract_evidence: Mapping[str, Any]
    d4_adoption_records: tuple[Mapping[str, Any], ...]
    plan_publication_record: Mapping[str, Any]
    plan_consumption_record: Mapping[str, Any]
    command_lineage_records: tuple[Mapping[str, Any], ...]
    world_application_records: tuple[Mapping[str, Any], ...]
    offline_identity_record: Mapping[str, Any]
    offline_truth_state_records: tuple[Mapping[str, Any], ...]
    control_cycle_count: int
    generated_command_count: int
    applied_command_count: int
    held_command_count: int
    physical_intercept_count: int

    def __post_init__(self) -> None:
        if self.arm_kind not in _ARM_KINDS:
            raise ValueError("unsupported isolated arm kind")
        if not self.episode_id or not self.world_id:
            raise ValueError("episode_id and world_id must be non-empty")
        _require_sha256(self.plan_payload_sha256, "plan_payload_sha256")
        if self.control_cycle_count < 2:
            raise ValueError("isolated arm requires at least two control cycles")


@dataclass(frozen=True, slots=True)
class IsolatedPhysicalPairResult:
    """One common checkpoint and its two independently executed arms."""

    pair_id: str
    seed: int
    source: ReservedSeedSourceEvidence
    duration_s: float
    control: IsolatedPhysicalArmResult
    treatment: IsolatedPhysicalArmResult

    def __post_init__(self) -> None:
        if not self.pair_id:
            raise ValueError("pair_id must be non-empty")
        if self.source.seed != self.seed:
            raise ValueError("source seed does not match pair seed")
        if self.control.arm_kind != "control" or self.treatment.arm_kind != "treatment":
            raise ValueError("paired arm inventory is invalid")
        if not math.isclose(
            self.control.duration_s,
            self.treatment.duration_s,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("paired arms must use the same physical duration")


@dataclass(frozen=True, slots=True)
class IsolatedPhysicalRolloutExecution:
    """All paired checkpoint continuations for one reserved intervention set."""

    options: CheckpointPhysicalRolloutOptions
    pairs: tuple[IsolatedPhysicalPairResult, ...]
    d3_bundle_loaded: bool
    d3_bundle_manifest_sha256: str | None
    d3_policy_version: str
    schema_version: str = ISOLATED_PHYSICAL_ROLLOUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ISOLATED_PHYSICAL_ROLLOUT_SCHEMA_VERSION:
            raise ValueError("unsupported physical rollout schema")
        if not self.pairs:
            raise ValueError("physical rollout requires at least one pair")
        seeds = tuple(item.seed for item in self.pairs)
        if len(seeds) != len(set(seeds)):
            raise ValueError("physical rollout seed inventory contains duplicates")
        if self.d3_bundle_manifest_sha256 is not None:
            _require_sha256(
                self.d3_bundle_manifest_sha256,
                "d3_bundle_manifest_sha256",
            )
        if not self.d3_policy_version:
            raise ValueError("d3_policy_version must be non-empty")


def execute_checkpoint_paired_physical_rollouts(
    intervention: ReservedSeedInterventionExecution,
    *,
    options: CheckpointPhysicalRolloutOptions | None = None,
) -> IsolatedPhysicalRolloutExecution:
    """Apply exact isolated D3 plans through D7 to cloned world checkpoints."""

    if not isinstance(intervention, ReservedSeedInterventionExecution):
        raise TypeError("intervention must be ReservedSeedInterventionExecution")
    resolved = options or CheckpointPhysicalRolloutOptions()
    d3_execution = intervention.d3_execution
    arm_by_key = {
        (item.arm_specification.seed, item.arm_specification.arm_kind): item
        for item in d3_execution.arms
    }
    pair_spec_by_seed = {
        item.seed: item for item in d3_execution.specification.pairs
    }
    results: list[IsolatedPhysicalPairResult] = []
    for source in intervention.sources:
        pair_spec = pair_spec_by_seed.get(source.seed)
        if pair_spec is None:
            raise ValueError("D3 paired specification is missing a source seed")
        validity_window_s = min(
            pair_spec.control.plan_valid_until_s,
            pair_spec.treatment.plan_valid_until_s,
        ) - float(source.intervention_timestamp_s)
        requested = (
            validity_window_s
            if resolved.maximum_duration_s is None
            else min(validity_window_s, resolved.maximum_duration_s)
        )
        duration_s, cycle_count = _quantized_rollout_duration(
            requested,
            physics_dt_s=source.scenario_config.physics_dt_s,
            minimum_cycle_count=resolved.minimum_control_cycle_count,
        )
        arms: dict[str, IsolatedPhysicalArmResult] = {}
        for arm_kind, arm_spec in (
            ("control", pair_spec.control),
            ("treatment", pair_spec.treatment),
        ):
            arm_execution = arm_by_key.get((source.seed, arm_kind))
            if arm_execution is None:
                raise ValueError("D3 execution is missing an isolated arm")
            arms[arm_kind] = _execute_physical_arm(
                source=source,
                specification=d3_execution.specification,
                arm_specification=arm_spec,
                arm_execution=arm_execution,
                duration_s=duration_s,
                cycle_count=cycle_count,
            )
        results.append(
            IsolatedPhysicalPairResult(
                pair_id=pair_spec.pair_id,
                seed=source.seed,
                source=source,
                duration_s=duration_s,
                control=arms["control"],
                treatment=arms["treatment"],
            )
        )
    expected_policy = d3_execution.specification.pairs[0].treatment.d3_bundle_version
    return IsolatedPhysicalRolloutExecution(
        options=resolved,
        pairs=tuple(results),
        d3_bundle_loaded=bool(d3_execution.bundle_loaded),
        d3_bundle_manifest_sha256=d3_execution.bundle_manifest_sha256,
        d3_policy_version=expected_policy,
    )


def _execute_physical_arm(
    *,
    source: ReservedSeedSourceEvidence,
    specification: Any,
    arm_specification: Any,
    arm_execution: Any,
    duration_s: float,
    cycle_count: int,
) -> IsolatedPhysicalArmResult:
    planning_frame = source.d3_planning_frame
    offline_solve_source_plan = planning_frame.previous_plan
    if offline_solve_source_plan is None:
        raise ValueError("D3 isolated execution requires its frozen source plan")
    formal_authority_plan = planning_frame.plan
    offline_candidate_plan = arm_execution.plan
    promoted = build_isolated_execution_plan(
        specification=specification,
        arm_specification=arm_specification,
        execution_receipt=arm_execution.receipt,
        planning_frame_evidence=planning_frame,
        offline_solve_source_plan=offline_solve_source_plan,
        formal_authority_plan=formal_authority_plan,
        offline_candidate_plan=offline_candidate_plan,
    )
    plan = promoted.plan
    evidence = build_isolated_plan_consumption_evidence(
        specification=specification,
        arm_specification=arm_specification,
        execution_receipt=arm_execution.receipt,
        plan=plan,
        rollout_cycle=0,
        consumption_timestamp_s=plan.created_at,
        planning_frame_evidence=planning_frame,
        offline_solve_source_plan=offline_solve_source_plan,
        formal_authority_plan=formal_authority_plan,
        offline_candidate_plan=offline_candidate_plan,
        conversion_evidence=promoted.conversion_evidence,
    )
    validator = IsolatedPlanConsumptionValidator()
    validator.validate_and_record(
        evidence,
        specification=specification,
        arm_specification=arm_specification,
        execution_receipt=arm_execution.receipt,
        expected_plan=plan,
        planning_frame_evidence=planning_frame,
        offline_solve_source_plan=offline_solve_source_plan,
        formal_authority_plan=formal_authority_plan,
        offline_candidate_plan=offline_candidate_plan,
        conversion_evidence=promoted.conversion_evidence,
    )
    if evidence.plan_payload_sha256 != promoted.plan_payload_sha256:
        raise ValueError("D3 execution plan and consumption evidence hashes differ")

    plan_payload = _d6_plan_payload(
        plan,
        source=source,
        d3_plan_sha256=evidence.plan_payload_sha256,
    )
    plan_payload_sha256 = canonical_guidance_sha256(plan_payload)
    assignments = tuple(
        (str(item["resource_id"]), str(item["global_track_id"]))
        for item in plan_payload["assignments"]
    )
    consumed_assignments_sha256 = canonical_guidance_sha256(
        [
            {"resource_id": resource_id, "global_track_id": global_track_id}
            for resource_id, global_track_id in assignments
        ]
    )
    plan_publication_record = {
        "schema_version": ISOLATED_PLAN_PUBLICATION_SCHEMA,
        "published_at_s": 0.0,
        "plan_payload_sha256": plan_payload_sha256,
        "plan": plan_payload,
    }
    plan_consumption_record = {
        "schema_version": ISOLATED_PLAN_CONSUMPTION_SCHEMA,
        "consumption_id": evidence.consumption_id,
        "cycle_index": 0,
        "consumed_at_s": 0.0,
        "evidence_scope": ISOLATED_PLAN_CONSUMPTION_SCOPE,
        "production_runtime_ack": False,
        "accepted": True,
        "status_code": "isolated_plan_consumed",
        "plan_id": plan.plan_id,
        "plan_version": int(plan.version),
        "plan_payload_sha256": plan_payload_sha256,
        "consumed_assignments_sha256": consumed_assignments_sha256,
    }

    world = VectorizedPointMassWorld(source.scenario_config)
    world.restore(source.intervention_world_checkpoint)
    world_id = str(arm_specification.isolation_id)
    episode_id = f"{source.source_episode_id}-{arm_specification.arm_kind}-physical"
    initial_context = IsolatedGuidanceExecutionContextV1.from_plan_payload(
        experiment_id=specification.experiment_id,
        seed=source.seed,
        arm_id=arm_specification.arm_id,
        arm_kind=arm_specification.arm_kind,
        episode_id=episode_id,
        isolation_id=world_id,
        source_plan_id=plan.plan_id,
        source_plan_version=plan.version,
        source_plan_payload=plan_payload,
        generated_at_s=0.0,
    )
    executor = IsolatedArmGuidanceExecutor3D(initial_context)
    track_templates = _track_templates(source)
    resource_index = {
        resource_id: index
        for index, resource_id in enumerate(world.interceptor_ids)
    }
    bindings = _guidance_bindings(
        plan,
        source=source,
        duration_s=duration_s,
    )

    truth_records: list[Mapping[str, Any]] = [
        _truth_state_record(
            world,
            episode_id=episode_id,
            world_id=world_id,
            seed=source.seed,
            local_timestamp_s=0.0,
        )
    ]
    command_records: list[Mapping[str, Any]] = []
    application_records: list[Mapping[str, Any]] = []
    held_count = 0
    applied_count = 0
    intercept_count = 0
    dt_s = float(source.scenario_config.physics_dt_s)
    for cycle_index in range(cycle_count):
        local_time_s = round(cycle_index * dt_s, 12)
        context = IsolatedGuidanceExecutionContextV1.from_plan_payload(
            experiment_id=specification.experiment_id,
            seed=source.seed,
            arm_id=arm_specification.arm_id,
            arm_kind=arm_specification.arm_kind,
            episode_id=episode_id,
            isolation_id=world_id,
            source_plan_id=plan.plan_id,
            source_plan_version=plan.version,
            source_plan_payload=plan_payload,
            generated_at_s=local_time_s,
        )
        pair_inputs = _guidance_inputs(
            plan=plan,
            source=source,
            bindings=bindings,
            track_templates=track_templates,
            resource_index=resource_index,
            interceptor_state=world.interceptor_state,
            timestamp_s=local_time_s,
        )
        batch = executor.command_batch(
            pair_inputs,
            resource_count=source.scenario_config.resource_count,
            context=context,
            source_plan_payload=plan_payload,
        )
        acceleration = batch.to_world_acceleration()
        world.step(interceptor_acceleration_ned=acceleration)
        intercept_count += len(world.register_proximity_intercepts())
        applied_at_s = round((cycle_index + 1) * dt_s, 12)
        for record_index, record in enumerate(batch.command_records):
            command_id = (
                f"{arm_specification.arm_id}-c{cycle_index:04d}-"
                f"r{record.assignment_binding.resource_index:04d}"
            )
            application = None
            world_application_id = None
            if record.held:
                held_count += 1
            else:
                world_application_id = f"world-apply-{command_id}"
                application = executor.confirm_world_application(
                    record,
                    context=context,
                    world_id=world_id,
                    applied_at_s=applied_at_s,
                    applied_acceleration_ned_mps2=acceleration[
                        record.assignment_binding.resource_index
                    ],
                )
                applied_count += 1
            lineage = build_isolated_guidance_lineage_record_v1(
                record,
                command_id=command_id,
                cycle_index=cycle_index,
                consumption_id=evidence.consumption_id,
                application=application,
                world_application_id=world_application_id,
            )
            command_records.append(lineage)
            if application is not None:
                application_records.append(
                    {
                        "schema_version": ISOLATED_WORLD_APPLICATION_SCHEMA,
                        "world_application_id": world_application_id,
                        "world_id": world_id,
                        "cycle_index": cycle_index,
                        "applied_at_s": applied_at_s,
                        "command_id": command_id,
                        "command_payload_sha256": lineage[
                            "command_payload_sha256"
                        ],
                        "resource_id": record.assignment_binding.resource_id,
                        "global_track_id": (
                            record.assignment_binding.assigned_global_track_id
                        ),
                        "control_applied_to_world": True,
                        "hard_constraint_violation_count": 0,
                    }
                )
        truth_records.append(
            _truth_state_record(
                world,
                episode_id=episode_id,
                world_id=world_id,
                seed=source.seed,
                local_timestamp_s=applied_at_s,
            )
        )

    identity_record = {
        "schema_version": OFFLINE_IDENTITY_SCHEMA,
        "episode_id": episode_id,
        "world_id": world_id,
        "seed": source.seed,
        "online_truth_isolation_verified": True,
        "online_truth_use_count": 0,
        "mappings": [
            {
                "global_track_id": global_track_id,
                "truth_target_id": truth_target_id,
                "mapping_status": "unique_lineage_verified",
            }
            for global_track_id, truth_target_id in (
                source.offline_track_truth_mapping
            )
        ],
    }
    result = IsolatedPhysicalArmResult(
        arm_kind=arm_specification.arm_kind,
        episode_id=episode_id,
        world_id=world_id,
        duration_s=duration_s,
        plan_payload=plan_payload,
        plan_payload_sha256=plan_payload_sha256,
        d3_contract_evidence={
            "schema_version": D3_ISOLATED_EXECUTION_CONTRACT_SCHEMA,
            "plan_payload_sha256": promoted.plan_payload_sha256,
            "plan_conversion": promoted.conversion_evidence.to_dict(),
            "plan_consumption": evidence.to_dict(),
            "isolated_simulation_only": True,
            "production_runtime_ack": False,
        },
        d4_adoption_records=(),
        plan_publication_record=plan_publication_record,
        plan_consumption_record=plan_consumption_record,
        command_lineage_records=tuple(command_records),
        world_application_records=tuple(application_records),
        offline_identity_record=identity_record,
        offline_truth_state_records=tuple(truth_records),
        control_cycle_count=cycle_count,
        generated_command_count=len(command_records),
        applied_command_count=applied_count,
        held_command_count=held_count,
        physical_intercept_count=intercept_count,
    )
    from .isolated_degraded_adoption import (
        evaluate_d4_isolated_physical_adoption,
    )

    adoption_records = evaluate_d4_isolated_physical_adoption(
        source=source,
        arm_kind=arm_specification.arm_kind,
        applied_plan_payload=plan_payload,
        world_application_records=result.world_application_records,
        physical_duration_s=duration_s,
    )
    return replace(
        result,
        d4_adoption_records=tuple(item.to_dict() for item in adoption_records),
    )


def _quantized_rollout_duration(
    requested_s: float,
    *,
    physics_dt_s: float,
    minimum_cycle_count: int,
) -> tuple[float, int]:
    requested = float(requested_s)
    dt_s = float(physics_dt_s)
    if not math.isfinite(requested) or requested <= 0.0:
        raise ValueError("D3 plan has no positive physical validity window")
    cycles = int(math.floor((requested + 1.0e-12) / dt_s))
    if cycles < minimum_cycle_count:
        raise ValueError("D3 plan validity window is too short for D6 evaluation")
    return round(cycles * dt_s, 12), cycles


def _d6_plan_payload(
    plan: Any,
    *,
    source: ReservedSeedSourceEvidence,
    d3_plan_sha256: str,
) -> dict[str, Any]:
    payload = dict(jsonable(plan))
    target_bridge = dict(source.planning_target_identity_bridge)
    resource_bridge = dict(source.planning_resource_identity_bridge)
    assignments = []
    for assignment in plan.assignments:
        global_track_id = target_bridge.get(str(assignment.target_id))
        resource_id = resource_bridge.get(str(assignment.resource_id))
        if global_track_id is None or resource_id is None:
            raise ValueError("D3 assignment is outside the identity bridge")
        row = dict(jsonable(assignment))
        row.update(
            {
                "anonymous_target_token": str(assignment.target_id),
                "anonymous_resource_token": str(assignment.resource_id),
                "target_id": global_track_id,
                "global_track_id": global_track_id,
                "resource_id": resource_id,
            }
        )
        assignments.append(row)
    anonymous_unassigned = tuple(str(item) for item in plan.unassigned_target_ids)
    anonymous_incomplete = tuple(str(item) for item in plan.incomplete_target_ids)
    unassigned_global_track_ids = [
        target_bridge[token]
        for token in anonymous_unassigned
        if token in target_bridge
    ]
    incomplete_global_track_ids = [
        target_bridge[token]
        for token in anonymous_incomplete
        if token in target_bridge
    ]
    if len(unassigned_global_track_ids) != len(anonymous_unassigned):
        raise ValueError("D3 unassigned target is outside the identity bridge")
    if len(incomplete_global_track_ids) != len(anonymous_incomplete):
        raise ValueError("D3 incomplete target is outside the identity bridge")
    coalitions = []
    for coalition in plan.coalitions:
        global_track_id = target_bridge.get(str(coalition.target_id))
        if global_track_id is None:
            raise ValueError("D3 coalition target is outside the identity bridge")
        row = dict(jsonable(coalition))
        row["anonymous_target_token"] = str(coalition.target_id)
        row["target_id"] = global_track_id
        members = []
        for member in coalition.members:
            resource_id = resource_bridge.get(str(member.resource_id))
            if resource_id is None:
                raise ValueError("D3 coalition member is outside the identity bridge")
            member_row = dict(jsonable(member))
            member_row["anonymous_resource_token"] = str(member.resource_id)
            member_row["resource_id"] = resource_id
            members.append(member_row)
        row["members"] = members
        coalitions.append(row)
    demand_summaries = []
    for summary in plan.demand_summaries:
        global_track_id = target_bridge.get(str(summary.target_id))
        if global_track_id is None:
            raise ValueError("D3 demand summary target is outside the identity bridge")
        row = dict(jsonable(summary))
        row["anonymous_target_token"] = str(summary.target_id)
        row["target_id"] = global_track_id
        demand_summaries.append(row)
    payload.update(
        {
            "schema_version": str(plan.plan_schema),
            "plan_id": str(plan.plan_id),
            "plan_version": int(plan.version),
            "created_at": float(plan.created_at),
            "assignments": assignments,
            "anonymous_unassigned_target_tokens": anonymous_unassigned,
            "anonymous_incomplete_target_tokens": anonymous_incomplete,
            "unassigned_target_ids": unassigned_global_track_ids,
            "unassigned_global_track_ids": unassigned_global_track_ids,
            "incomplete_target_ids": incomplete_global_track_ids,
            "coalitions": coalitions,
            "demand_summaries": demand_summaries,
            "d3_validated_plan_payload_sha256": d3_plan_sha256,
            "planning_target_identity_bridge_sha256": canonical_guidance_sha256(
                source.planning_target_identity_bridge
            ),
            "planning_resource_identity_bridge_sha256": (
                canonical_guidance_sha256(
                    source.planning_resource_identity_bridge
                )
            ),
            "global_track_id_owner": "D2_center",
            "isolated_simulation_only": True,
            "production_runtime_ack": False,
        }
    )
    return payload


def _track_templates(
    source: ReservedSeedSourceEvidence,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for track in source.intervention_global_tracks:
        state = np.asarray(track.state_ned, dtype=float)
        covariance = np.asarray(track.covariance, dtype=float)
        age_s = max(
            0.0,
            float(source.intervention_timestamp_s) - float(track.timestamp_s),
        )
        transition = np.eye(6, dtype=float)
        transition[:3, 3:] = np.eye(3) * age_s
        state_at_intervention = state.copy()
        state_at_intervention[:3] += state_at_intervention[3:] * age_s
        covariance_at_intervention = transition @ covariance @ transition.T
        result[str(track.global_track_id)] = {
            "position_ned": state_at_intervention[:3],
            "velocity_ned": state_at_intervention[3:],
            "covariance": covariance_at_intervention,
            "lifecycle_state": str(track.lifecycle_state),
        }
    return result


def _guidance_bindings(
    plan: Any,
    *,
    source: ReservedSeedSourceEvidence,
    duration_s: float,
) -> dict[tuple[str, str], AssignmentGuidanceBinding]:
    coalition_by_target = {
        item.target_id: item for item in getattr(plan, "coalitions", ())
    }
    target_bridge = dict(source.planning_target_identity_bridge)
    resource_bridge = dict(source.planning_resource_identity_bridge)
    result: dict[tuple[str, str], AssignmentGuidanceBinding] = {}
    for index, assignment in enumerate(plan.assignments):
        anonymous_target = str(assignment.target_id)
        anonymous_resource = str(assignment.resource_id)
        target_id = target_bridge.get(anonymous_target)
        resource_id = resource_bridge.get(anonymous_resource)
        if target_id is None or resource_id is None:
            raise ValueError("D3 guidance assignment is outside the identity bridge")
        coalition = coalition_by_target.get(anonymous_target)
        region_decision = _formal_d4_decision_for_track(source, target_id)
        owner_node_id = (
            None
            if region_decision is None
            else region_decision.ownership.owner_id
        )
        if owner_node_id is None:
            owner_node_id = (
                assignment.metadata.get("owner_node_id")
                or plan.metadata.get("owner_node_id")
                or plan.source_node_id
            )
        result[(resource_id, target_id)] = AssignmentGuidanceBinding(
            plan_id=str(plan.plan_id),
            plan_version=int(plan.version),
            resource_id=resource_id,
            vehicle_name=resource_id,
            assigned_global_track_id=target_id,
            track_version=int(plan.version),
            authorization_state="authorized",
            owner_node_id=str(owner_node_id),
            assignment_id=f"{plan.plan_id}:{index}:{resource_id}:{target_id}",
            assignment_validity_state="current",
            created_at_s=0.0,
            expires_at_s=duration_s + _EPS,
            coalition_id=assignment.coalition_id,
            coalition_version=assignment.coalition_version,
            coalition_epoch=assignment.coalition_version,
            member_role=str(assignment.member_role),
            wave_id=int(assignment.wave_id),
            coordination_mode=(
                "independent"
                if coalition is None
                else str(coalition.coordination_mode)
            ),
            arrival_window_start_s=assignment.arrival_window_start_s,
            arrival_window_end_s=assignment.arrival_window_end_s,
            activation_state="active",
            activation_plan_version=int(plan.version),
            activation_track_version=int(plan.version),
            activation_coalition_version=assignment.coalition_version,
            terminal_authorization_scope=str(
                assignment.terminal_authorization_scope
            ),
            arrival_coordination_required=bool(
                assignment.arrival_coordination_required
            ),
            metadata={
                "isolated_simulation_only": True,
                "production_runtime_ack": False,
            },
        )
    return result


def _guidance_inputs(
    *,
    plan: Any,
    source: ReservedSeedSourceEvidence,
    bindings: Mapping[tuple[str, str], AssignmentGuidanceBinding],
    track_templates: Mapping[str, Mapping[str, Any]],
    resource_index: Mapping[str, int],
    interceptor_state: np.ndarray,
    timestamp_s: float,
) -> tuple[AssignmentPairGuidanceInput3D, ...]:
    output: list[AssignmentPairGuidanceInput3D] = []
    target_bridge = dict(source.planning_target_identity_bridge)
    resource_bridge = dict(source.planning_resource_identity_bridge)
    for assignment in plan.assignments:
        resource_id = resource_bridge.get(str(assignment.resource_id))
        track_id = target_bridge.get(str(assignment.target_id))
        if resource_id is None or track_id is None:
            continue
        index = resource_index.get(resource_id)
        template = track_templates.get(track_id)
        binding = bindings.get((resource_id, track_id))
        if index is None or template is None or binding is None:
            continue
        velocity = np.asarray(template["velocity_ned"], dtype=float)
        position = np.asarray(template["position_ned"], dtype=float) + velocity * float(
            timestamp_s
        )
        transition = np.eye(6, dtype=float)
        transition[:3, 3:] = np.eye(3) * float(timestamp_s)
        covariance = transition @ np.asarray(
            template["covariance"], dtype=float
        ) @ transition.T
        global_track = {
            "global_track_id": track_id,
            "state": np.concatenate((position, velocity)),
            "covariance": covariance,
            "timestamp": float(timestamp_s),
            "lifecycle_state": template["lifecycle_state"],
            "metadata": {
                "global_track_id_owner": "D2_center",
                "prediction_model": "constant_velocity_truth_free_v1",
            },
        }
        permission = _isolated_d4_permission(
            plan=plan,
            source=source,
            track_id=track_id,
            binding=binding,
        )
        output.append(
            AssignmentPairGuidanceInput3D(
                resource_index=index,
                resource_state=np.asarray(interceptor_state[index], dtype=float),
                global_track=global_track,
                binding=binding,
                d4_permission=permission,
                terminal_association=None,
                active_plan_id=str(plan.plan_id),
                active_plan_version=int(plan.version),
                timestamp_s=float(timestamp_s),
                visual_observation=None,
                camera_recognition_ready=False,
                available_accel_mps2=16.0,
            )
        )
    return tuple(output)


def _formal_d4_decision_for_track(
    source: ReservedSeedSourceEvidence,
    global_track_id: str,
) -> Any | None:
    task = next(
        (
            item
            for item in source.d4_formal_snapshot.tasks
            if str(item.global_track_id) == str(global_track_id)
        ),
        None,
    )
    if task is None:
        return None
    return next(
        (
            item
            for item in source.d4_formal_decision.region_decisions
            if str(item.region_id) == str(task.region_id)
        ),
        None,
    )


def _isolated_d4_permission(
    *,
    plan: Any,
    source: ReservedSeedSourceEvidence,
    track_id: str,
    binding: AssignmentGuidanceBinding,
) -> D4GuidancePermission:
    decision = _formal_d4_decision_for_track(source, track_id)
    if decision is None:
        return D4GuidancePermission(
            action="hold_for_review",
            mode="hold",
            reason="isolated_d4_region_decision_missing",
            requires_human_review=True,
            new_plan_id=str(plan.plan_id),
            new_plan_version=int(plan.version),
            visual_png_allowed=False,
            metadata={
                "isolated_simulation_only": True,
                "production_runtime_ack": False,
            },
        )
    layer = str(decision.selected_layer.value)
    if (
        not bool(decision.execution_allowed)
        or bool(decision.fail_closed)
        or not bool(decision.ownership.active)
    ):
        return D4GuidancePermission(
            action="hold_for_review",
            mode=layer,
            reason=str(decision.reason),
            requires_human_review=True,
            new_plan_id=str(plan.plan_id),
            new_plan_version=int(plan.version),
            visual_png_allowed=False,
            metadata={
                "isolated_simulation_only": True,
                "production_runtime_ack": False,
                "intervention_kind": source.intervention_kind,
                "regional_region_id": str(decision.region_id),
            },
        )

    commit = next(
        (
            item
            for item in decision.coalition_commits
            if str(item.global_track_id) == str(track_id)
        ),
        None,
    )
    commit_required = binding.coalition_id is not None
    common: dict[str, Any] = {
        "terminal_consistent": True,
        "requires_human_review": False,
        "new_plan_id": str(plan.plan_id),
        "new_plan_version": int(plan.version),
        "visual_png_allowed": False,
        "metadata": {
            "isolated_simulation_only": True,
            "production_runtime_ack": False,
            "intervention_kind": source.intervention_kind,
            "regional_region_id": str(decision.region_id),
            "regional_epoch": int(decision.ownership.epoch),
            "commit_required": commit_required,
        },
    }
    if commit is not None:
        common.update(
            {
                "atomic_coalition_formed": bool(commit.atomic_committed),
                "coalition_commit_state": str(commit.state),
                "coalition_epoch": int(decision.ownership.epoch),
                "coalition_lease_expires_at_s": float(
                    commit.lease_expires_at_s
                ),
                "coalition_required_member_ids": tuple(
                    commit.required_member_ids
                ),
                "coalition_acked_member_ids": tuple(commit.acked_member_ids),
                "commit_plan_id": str(plan.plan_id),
                "commit_plan_version": int(plan.version),
                "commit_coalition_id": binding.coalition_id,
                "commit_coalition_version": binding.coalition_version,
            }
        )
    if layer in {"secondary", "distributed"}:
        return D4GuidancePermission(
            action="continue",
            mode=layer,
            reason=str(decision.reason),
            target_node_id=str(decision.ownership.owner_id),
            secondary_capability_class=(
                "mobile_high_recon" if layer == "secondary" else None
            ),
            secondary_readiness_class=(
                "takeover_ready" if layer == "secondary" else None
            ),
            center_available=False,
            **common,
        )
    action = str(decision.action.value)
    if action not in {"continue_center", "request_secondary_assist"}:
        return D4GuidancePermission(
            action="hold_for_review",
            mode="center",
            reason=str(decision.reason),
            requires_human_review=True,
            new_plan_id=str(plan.plan_id),
            new_plan_version=int(plan.version),
            visual_png_allowed=False,
            center_available=True,
            metadata=common["metadata"],
        )
    return D4GuidancePermission(
        action=action,
        mode="center",
        reason=str(decision.reason),
        center_available=True,
        **common,
    )


def _truth_state_record(
    world: VectorizedPointMassWorld,
    *,
    episode_id: str,
    world_id: str,
    seed: int,
    local_timestamp_s: float,
) -> dict[str, Any]:
    return {
        "schema_version": OFFLINE_TRUTH_STATE_SCHEMA,
        "episode_id": episode_id,
        "world_id": world_id,
        "seed": int(seed),
        "timestamp_s": float(local_timestamp_s),
        "interceptor_positions_ned_m": {
            entity_id: world.interceptor_state[index, :3].tolist()
            for index, entity_id in enumerate(world.interceptor_ids)
        },
        "target_positions_ned_m": {
            entity_id: world.intruder_state[index, :3].tolist()
            for index, entity_id in enumerate(world.intruder_ids)
        },
    }


def write_checkpoint_paired_physical_rollouts(
    output_dir: str | Path,
    execution: IsolatedPhysicalRolloutExecution,
) -> dict[str, Path]:
    """Atomically write producer artifacts, a D6 input spec and D6 sidecar."""

    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"physical rollout output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir(parents=False)
    try:
        pair_input_rows: list[dict[str, Any]] = []
        pair_summary_rows: list[dict[str, Any]] = []
        for pair in execution.pairs:
            pair_dir = temporary / f"seed_{pair.seed}"
            shared_paths = _write_shared_artifacts(pair_dir / "shared", pair)
            shared_hashes = {
                name: _file_sha256(path) for name, path in shared_paths.items()
            }
            arm_rows: dict[str, Any] = {}
            for arm in (pair.control, pair.treatment):
                arm_paths = _write_arm_artifacts(
                    pair_dir / arm.arm_kind,
                    pair=pair,
                    arm=arm,
                    shared_hashes=shared_hashes,
                )
                arm_rows[arm.arm_kind] = {
                    name: {
                        "path": str(path.relative_to(temporary)),
                        "sha256": _file_sha256(path),
                    }
                    for name, path in arm_paths.items()
                    if name != "d3_contract_evidence"
                }
            pair_input_rows.append(
                {
                    "pair_id": pair.pair_id,
                    "seed": pair.seed,
                    "shared_artifacts": {
                        name: {
                            "path": str(path.relative_to(temporary)),
                            "sha256": shared_hashes[name],
                        }
                        for name, path in shared_paths.items()
                    },
                    "arms": arm_rows,
                }
            )
            pair_summary_rows.append(_pair_summary(pair))

        input_spec = temporary / "d6_paired_physical_inputs.json"
        _write_json(
            input_spec,
            {
                "schema_version": "d6.paired-isolated-physical-inputs.v1",
                "evaluation_id": "scalable3d-checkpoint-paired-physical-v1",
                "pairs": pair_input_rows,
            },
        )
        d6_paths: dict[str, Path] = {}
        if execution.options.evaluate_with_d6:
            from research_modules.d6_evaluation_metrics.d6_evaluation_metrics import (
                load_paired_isolated_physical_inputs,
                write_paired_isolated_physical_report,
            )

            d6_inputs = load_paired_isolated_physical_inputs(
                input_spec,
                expected_sha256=_file_sha256(input_spec),
            )
            d6_paths = write_paired_isolated_physical_report(
                d6_inputs,
                temporary / "d6_evaluation",
            )

        source_provenance = _source_provenance(execution)
        manifest = temporary / "manifest.json"
        _write_json(
            manifest,
            {
                "schema_version": execution.schema_version,
                "created_at_utc": execution.options.created_at_utc,
                **source_provenance,
                "pair_count": len(execution.pairs),
                "seeds": [item.seed for item in execution.pairs],
                "d3_bundle_loaded": execution.d3_bundle_loaded,
                "d3_bundle_manifest_sha256": (
                    execution.d3_bundle_manifest_sha256
                ),
                "d3_policy_version": execution.d3_policy_version,
                "intervention_kinds": sorted(
                    {item.source.intervention_kind for item in execution.pairs}
                ),
                "d4_adoption_region_count": sum(
                    len(arm.d4_adoption_records)
                    for item in execution.pairs
                    for arm in (item.control, item.treatment)
                ),
                "d4_adoption_available_count": sum(
                    bool(record.get("available"))
                    for item in execution.pairs
                    for arm in (item.control, item.treatment)
                    for record in arm.d4_adoption_records
                ),
                "paired_results": pair_summary_rows,
                "claim_boundary": {
                    "isolated_simulation_only": True,
                    "production_runtime_ack": False,
                    "ppo_enabled": False,
                    "online_assist_enabled": False,
                    "online_authority_enabled": False,
                    "physical_comparison_available": bool(d6_paths),
                    "d4_degraded_adoption_evidence_available": any(
                        record.get("available") is True
                        for item in execution.pairs
                        for arm in (item.control, item.treatment)
                        for record in arm.d4_adoption_records
                    ),
                    "counterfactual_available": False,
                    "causal_available": False,
                },
                "d6_input_spec_sha256": _file_sha256(input_spec),
                "d6_outputs": {
                    name: str(path.relative_to(temporary))
                    for name, path in d6_paths.items()
                },
            },
        )
        report = temporary / "CHECKPOINT_PAIRED_PHYSICAL_REPORT_CN.md"
        report.write_text(_render_report(execution), encoding="utf-8")
        checksums = temporary / "SHA256SUMS"
        hashes = {
            str(path.relative_to(temporary)): _file_sha256(path)
            for path in sorted(temporary.rglob("*"))
            if path.is_file() and path != checksums
        }
        checksums.write_text(
            "".join(
                f"{digest}  {name}\n"
                for name, digest in sorted(hashes.items())
            ),
            encoding="ascii",
        )
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "manifest": output / "manifest.json",
        "input_spec": output / "d6_paired_physical_inputs.json",
        "report_cn": output / "CHECKPOINT_PAIRED_PHYSICAL_REPORT_CN.md",
        "d6_sidecar": output
        / "d6_evaluation"
        / "paired_isolated_physical_sidecar.json",
        "d6_report_cn": output
        / "d6_evaluation"
        / "paired_isolated_physical_report_cn.md",
        "checksums": output / "SHA256SUMS",
    }


def _write_shared_artifacts(
    directory: Path,
    pair: IsolatedPhysicalPairResult,
) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=False)
    config = pair.source.scenario_config
    checkpoint = pair.source.intervention_world_checkpoint
    common = {
        "seed": pair.seed,
        "scenario_name": config.scenario_name,
        "scenario_version": config.scenario_version,
    }
    payloads = {
        "initial_state": {
            **common,
            "schema_version": INITIAL_STATE_SCHEMA,
            "source_timestamp_s": checkpoint.timestamp,
            "interceptor_positions_ned_m": {
                entity_id: checkpoint.interceptor_state[index, :3].tolist()
                for index, entity_id in enumerate(checkpoint.interceptor_ids)
            },
            "target_positions_ned_m": {
                entity_id: checkpoint.intruder_state[index, :3].tolist()
                for index, entity_id in enumerate(checkpoint.intruder_ids)
            },
        },
        "sensor_schedule": {
            **common,
            "schema_version": SENSOR_SCHEDULE_SCHEMA,
            "sensor_random_schedule_version": (
                config.sensor_random_schedule_version
            ),
            "source_snapshot_sha256": pair.source.d3_input_snapshot_sha256,
        },
        "communication_schedule": {
            **common,
            "schema_version": COMMUNICATION_SCHEDULE_SCHEMA,
            "source_schedule_sha256": (
                pair.source.communication_schedule_sha256
            ),
        },
        "fault_schedule": {
            **common,
            "schema_version": FAULT_SCHEDULE_SCHEMA,
            "source_schedule_sha256": pair.source.fault_schedule_sha256,
        },
    }
    paths: dict[str, Path] = {}
    for name, payload in payloads.items():
        path = directory / f"{name}.json"
        _write_json(path, payload)
        paths[name] = path
    return paths


def _write_arm_artifacts(
    directory: Path,
    *,
    pair: IsolatedPhysicalPairResult,
    arm: IsolatedPhysicalArmResult,
    shared_hashes: Mapping[str, str],
) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=False)
    payloads = {
        "assignment_plans": ("assignment_plans.jsonl", [arm.plan_publication_record]),
        "isolated_plan_consumption": (
            "isolated_plan_consumption.jsonl",
            [arm.plan_consumption_record],
        ),
        "d7_command_lineage": (
            "d7_command_lineage.jsonl",
            list(arm.command_lineage_records),
        ),
        "world_applications": (
            "world_applications.jsonl",
            list(arm.world_application_records),
        ),
        "offline_truth_identity": (
            "offline_truth_identity.json",
            arm.offline_identity_record,
        ),
        "offline_truth_state": (
            "offline_truth_state.jsonl",
            list(arm.offline_truth_state_records),
        ),
        "d3_contract_evidence": (
            "d3_contract_evidence.json",
            arm.d3_contract_evidence,
        ),
        "d4_adoption_evidence": (
            "d4_adoption_evidence.jsonl",
            list(arm.d4_adoption_records),
        ),
    }
    paths: dict[str, Path] = {}
    for name, (filename, payload) in payloads.items():
        path = directory / filename
        if filename.endswith(".jsonl"):
            _write_jsonl(path, payload)
        else:
            _write_json(path, payload)
        paths[name] = path
    arm_hashes = {
        name: _file_sha256(path)
        for name, path in paths.items()
        if name != "d3_contract_evidence"
    }
    config = pair.source.scenario_config
    manifest_path = directory / "episode_manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": ISOLATED_ARM_MANIFEST_SCHEMA,
            "pair_id": pair.pair_id,
            "arm_kind": arm.arm_kind,
            "episode_id": arm.episode_id,
            "world_id": arm.world_id,
            "seed": pair.seed,
            "scenario_name": config.scenario_name,
            "scenario_version": config.scenario_version,
            "world_schema": "scalable3d-world-v1",
            "bus_schema": "scalable3d-episode-bus-v1",
            "duration_s": arm.duration_s,
            "physics_dt_s": config.physics_dt_s,
            "intercept_radius_m": config.intercept_radius_m,
            "isolated_simulation": True,
            "truth_isolation_verified": True,
            "online_truth_use_count": 0,
            "production_runtime_ack_available": False,
            "shared_artifact_sha256": dict(shared_hashes),
            "arm_artifact_sha256": arm_hashes,
        },
    )
    paths["episode_manifest"] = manifest_path
    return paths


def _pair_summary(pair: IsolatedPhysicalPairResult) -> dict[str, Any]:
    return {
        "pair_id": pair.pair_id,
        "seed": pair.seed,
        "duration_s": pair.duration_s,
        "same_intervention_checkpoint": True,
        "control_treatment_worlds_isolated": (
            pair.control.world_id != pair.treatment.world_id
        ),
        "offline_identity_mapping_count": len(
            pair.source.offline_track_truth_mapping
        ),
        "control": {
            "plan_id": pair.control.plan_payload["plan_id"],
            "plan_version": pair.control.plan_payload["plan_version"],
            "control_cycle_count": pair.control.control_cycle_count,
            "generated_command_count": pair.control.generated_command_count,
            "applied_command_count": pair.control.applied_command_count,
            "held_command_count": pair.control.held_command_count,
            "physical_intercept_count": pair.control.physical_intercept_count,
            "d4_adoption_available_count": sum(
                bool(item.get("available"))
                for item in pair.control.d4_adoption_records
            ),
            "d4_adoption_region_count": len(pair.control.d4_adoption_records),
        },
        "treatment": {
            "plan_id": pair.treatment.plan_payload["plan_id"],
            "plan_version": pair.treatment.plan_payload["plan_version"],
            "control_cycle_count": pair.treatment.control_cycle_count,
            "generated_command_count": pair.treatment.generated_command_count,
            "applied_command_count": pair.treatment.applied_command_count,
            "held_command_count": pair.treatment.held_command_count,
            "physical_intercept_count": pair.treatment.physical_intercept_count,
            "d4_adoption_available_count": sum(
                bool(item.get("available"))
                for item in pair.treatment.d4_adoption_records
            ),
            "d4_adoption_region_count": len(pair.treatment.d4_adoption_records),
        },
    }


def _source_provenance(
    execution: IsolatedPhysicalRolloutExecution,
) -> dict[str, Any]:
    """Summarise the immutable source episode repository provenance."""

    source_git_commits = sorted(
        {str(pair.source.source_git_commit) for pair in execution.pairs}
    )
    dirty_source_episode_count = sum(
        bool(pair.source.source_repository_dirty) for pair in execution.pairs
    )
    commit_is_uniform = len(source_git_commits) == 1
    return {
        "git_commit": source_git_commits[0] if commit_is_uniform else None,
        "repository_dirty": bool(dirty_source_episode_count),
        "source_episode_count": len(execution.pairs),
        "source_git_commits": source_git_commits,
        "source_git_commit_uniform": commit_is_uniform,
        "dirty_source_episode_count": dirty_source_episode_count,
        "source_episode_manifest_sha256": {
            str(pair.seed): pair.source.source_episode_manifest_sha256
            for pair in execution.pairs
        },
    }


def _render_report(execution: IsolatedPhysicalRolloutExecution) -> str:
    pair_count = len(execution.pairs)
    mapped = sum(
        len(pair.source.offline_track_truth_mapping) for pair in execution.pairs
    )
    control_applied = sum(
        pair.control.applied_command_count for pair in execution.pairs
    )
    treatment_applied = sum(
        pair.treatment.applied_command_count for pair in execution.pairs
    )
    changed = sum(
        tuple(
            (item["resource_id"], item["global_track_id"])
            for item in pair.control.plan_payload["assignments"]
        )
        != tuple(
            (item["resource_id"], item["global_track_id"])
            for item in pair.treatment.plan_payload["assignments"]
        )
        for pair in execution.pairs
    )
    d4_region_count = sum(
        len(arm.d4_adoption_records)
        for pair in execution.pairs
        for arm in (pair.control, pair.treatment)
    )
    d4_available_count = sum(
        bool(item.get("available"))
        for pair in execution.pairs
        for arm in (pair.control, pair.treatment)
        for item in arm.d4_adoption_records
    )
    source_provenance = _source_provenance(execution)
    source_commit = source_provenance["git_commit"] or "mixed"
    dirty_source_count = int(
        source_provenance["dirty_source_episode_count"]
    )
    return "\n".join(
        [
            "# 共同检查点隔离物理续跑报告",
            "",
            "## 结论",
            "",
            (
                f"本次生成 `{pair_count}` 组共同干预检查点双臂续跑。"
                f"分配绑定不同的 seed 为 `{changed}/{pair_count}`。"
            ),
            (
                f"control/treatment 写入世界的 D7 命令分别为 "
                f"`{control_applied}/{treatment_applied}`，离线唯一身份映射总数为 "
                f"`{mapped}`。"
            ),
            (
                f"D4 区域采用证据可用数为 `{d4_available_count}/"
                f"{d4_region_count}`；名义场景没有区域采用记录。"
            ),
            (
                f"源提交为 `{source_commit}`，脏源 episode 为 "
                f"`{dirty_source_count}/{pair_count}`。"
            ),
            "",
            "## 执行边界",
            "",
            "- 两个臂从同一个评估侧世界检查点复制，之后使用不同 world_id 和 D7 状态。",
            "- D7 只读取 D2 全局航迹的匀速预测和本机导航状态，不读取目标真值。",
            "- 固定计划只在 D3 原有效期内使用；到期后本续跑停止。",
            "- 真值编号和三维真值轨迹只进入 D6 离线文件。",
            "- 结果属于隔离仿真对比，不是生产运行确认，也不构成因果结论。",
            "",
        ]
    )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            jsonable(value),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values: Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(
                jsonable(value),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_sha256(value: str, name: str) -> None:
    if len(str(value)) != 64 or any(
        character not in "0123456789abcdef" for character in str(value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256")
