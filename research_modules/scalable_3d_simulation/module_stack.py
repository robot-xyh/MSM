"""Main-owned composition of the scalable D1-D7 online module path.

The stack is intentionally glue code.  Sensor, association, assignment,
failover, terminal-association, and guidance algorithms remain owned by their
respective D modules.  This module schedules those implementations on the
shared episode clock and translates only versioned, truth-free DTOs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping

import numpy as np

from research_modules.d1_sensor_fusion.src.d1_sensor_fusion import (
    Scalable3DFusionAdapter,
)
from research_modules.d2_data_association.d2_data_association import (
    Scalable3DTracker,
    detections3d_from_d1_global_tracks,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
    AssignmentPlanner,
    PlannerConfig,
    ResourceState,
    TargetDemand,
    TargetTrack,
    continue_active_secondary_plan,
    guidance_bindings_from_assignment_plan,
    prepare_secondary_takeover_plan,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    C2Health,
    CoalitionMemberAck,
    D5Consistency,
    MobileReconSecondary,
    RegionDefinition,
    RegionalAction,
    RegionalAuthorityLayer,
    RegionalFailoverCoordinator,
    RegionalFailoverSnapshot,
    RegionalFallbackMember,
    RegionalScenarioMetadata,
    RegionalTaskEvidence,
    SecondaryReadinessEvidence,
)
from research_modules.d5_terminal_association.src.d5_terminal_association import (
    Scalable3DTerminalAdapter,
)
from research_modules.d7_proportional_guidance.d7_proportional_guidance import (
    AssignmentPairGuidanceInput3D,
    D4GuidancePermission,
    ScalableGuidanceConfig3D,
    ScalableGuidanceController3D,
    TerminalVisualObservation3D,
)

from .models import OnlineSensorBatch, ScenarioConfig
from .runtime_ports import (
    PlatformNavigationBatch,
    RuntimePublication,
    RuntimeStepInput,
    RuntimeStepOutput,
)


INTEGRATED_STACK_SCHEMA_VERSION = "scalable3d-module-stack-v1"
_EPS = 1.0e-9


@dataclass(frozen=True)
class IntegratedStackConfig:
    """Main-level scheduling and deterministic adapter settings."""

    assignment_lease_multiplier: float = 3.0
    d3_candidate_edges_per_target: int = 32
    d3_unassigned_base_cost: float = 50.0
    d3_human_authorization_state: str = "approved"
    terminal_switch_range_m: float = 120.0
    secondary_coverage_ratio: float = 0.90
    secondary_network_full_view_rate: float = 0.90

    def __post_init__(self) -> None:
        if self.assignment_lease_multiplier <= 1.0:
            raise ValueError("assignment_lease_multiplier must exceed one")
        if self.d3_candidate_edges_per_target <= 0:
            raise ValueError("d3_candidate_edges_per_target must be positive")
        if self.d3_unassigned_base_cost <= 0.0:
            raise ValueError("d3_unassigned_base_cost must be positive")
        if self.terminal_switch_range_m <= 0.0:
            raise ValueError("terminal_switch_range_m must be positive")
        for name in ("secondary_coverage_ratio", "secondary_network_full_view_rate"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")


class IntegratedScalableModuleStack:
    """Truth-free D1-D7 rule baseline for one scalable point-mass episode.

    The first integrated profile deliberately keeps learning models optional.
    D3 uses its deterministic sparse cost/Hungarian path and D5 uses its
    geometry rule when no edge model is supplied.  D7 always remains the
    deterministic three-dimensional PN/visual-PNG controller.
    """

    def __init__(
        self,
        config: IntegratedStackConfig | None = None,
        *,
        d5_edge_model: Any | None = None,
    ) -> None:
        self.stack_config = config or IntegratedStackConfig()
        self.d5_edge_model = d5_edge_model
        self.config: ScenarioConfig | None = None
        self.d1: Scalable3DFusionAdapter | None = None
        self.d2: Scalable3DTracker | None = None
        self.d3: AssignmentPlanner | None = None
        self.d4: RegionalFailoverCoordinator | None = None
        self.d5: Scalable3DTerminalAdapter | None = None
        self.d7: ScalableGuidanceController3D | None = None
        self.latest_d1_tracks: tuple[Any, ...] = ()
        self.latest_d2_tracks: tuple[Any, ...] = ()
        self.latest_d2_result: Any | None = None
        self.latest_plan: Any | None = None
        self.latest_bindings: tuple[Any, ...] = ()
        self.latest_d4_decision: Any | None = None
        self.latest_d5_result: Any | None = None
        self.latest_guidance_batch: Any | None = None
        self._latest_terminal_by_pair: dict[tuple[str, str], tuple[dict[str, Any], Any]] = {}
        self._track_region_by_id: dict[str, str] = {}
        self._resource_index_by_id: dict[str, int] = {}
        self._next_association_s = 0.0
        self._next_assignment_s = 0.0
        self._last_center_health = C2Health.NORMAL
        self._fault_generation_changed = False

    def reset(self, config: ScenarioConfig) -> None:
        self.config = config
        self.d1 = Scalable3DFusionAdapter()
        self.d2 = Scalable3DTracker()
        self.d3 = AssignmentPlanner(
            config=PlannerConfig.scalable_3d(
                max_candidate_edges_per_target=(
                    self.stack_config.d3_candidate_edges_per_target
                ),
                unassigned_base_cost=self.stack_config.d3_unassigned_base_cost,
                human_authorization_state=(
                    self.stack_config.d3_human_authorization_state
                ),
            )
        )
        self.d4 = RegionalFailoverCoordinator()
        self.d5 = Scalable3DTerminalAdapter()
        self.d7 = ScalableGuidanceController3D(
            ScalableGuidanceConfig3D(
                terminal_switch_range_m=self.stack_config.terminal_switch_range_m,
                intercept_radius_m=config.intercept_radius_m,
            )
        )
        self.latest_d1_tracks = ()
        self.latest_d2_tracks = ()
        self.latest_d2_result = None
        self.latest_plan = None
        self.latest_bindings = ()
        self.latest_d4_decision = None
        self.latest_d5_result = None
        self.latest_guidance_batch = None
        self._latest_terminal_by_pair.clear()
        self._track_region_by_id.clear()
        self._resource_index_by_id.clear()
        self._next_association_s = 0.0
        self._next_assignment_s = 0.0
        self._last_center_health = C2Health.NORMAL
        self._fault_generation_changed = False

    def step(self, step_input: RuntimeStepInput) -> RuntimeStepOutput:
        config = self._require_ready()
        now = float(step_input.timestamp)
        if not np.isfinite(now) or now < 0.0:
            raise ValueError("runtime timestamp must be finite and non-negative")
        self._validate_navigation(step_input.interceptors, "interceptor")
        self._validate_navigation(step_input.recon, "recon")
        self._resource_index_by_id = {
            resource_id: index
            for index, resource_id in enumerate(step_input.interceptors.platform_ids)
        }
        publications: list[RuntimePublication] = []

        arrived = tuple(
            sorted(
                step_input.arrived_sensor_batches,
                key=lambda item: (
                    float(item.arrival_timestamp),
                    float(item.measurement_timestamp),
                    str(item.sensor_id),
                    str(item.batch_id),
                ),
            )
        )
        vision_batches = tuple(
            batch for batch in arrived if _batch_modality(batch) == "vision_bbox"
        )
        d1_updated = False
        for batch in arrived:
            result = self.d1.process_online_sensor_batch(batch)
            self.latest_d1_tracks = tuple(result.tracks)
            d1_updated = True
            publications.append(self._d1_publication(result, batch, now))

        if (
            d1_updated
            and self.latest_d1_tracks
            and now + _EPS >= self._next_association_s
        ):
            _, detections = detections3d_from_d1_global_tracks(
                self.latest_d1_tracks
            )
            if detections:
                d2_timestamp = max(item.measurement_timestamp for item in detections)
                self.latest_d2_result = self.d2.step(detections, d2_timestamp)
                self.latest_d2_tracks = tuple(self.d2.active_tracks())
                publications.append(self._d2_publication(now))
            self._next_association_s = _advance_schedule(
                self._next_association_s,
                config.association_period_s,
                now,
            )

        if vision_batches:
            self.latest_d5_result = self.d5.process(
                vision_batches,
                self.latest_d2_tracks,
                edge_model=self.d5_edge_model,
            )
            self._latest_terminal_by_pair = self._terminal_pairs_from_d5(
                self.latest_d5_result
            )
            publications.append(self._d5_publication(now))

        center_health, secondary_failed = self._fault_state(now)
        self._fault_generation_changed = center_health != self._last_center_health
        self._last_center_health = center_health
        if (
            self.latest_d2_tracks
            and now + _EPS >= self._next_assignment_s
        ):
            self._run_assignment_and_failover(
                step_input,
                now=now,
                center_health=center_health,
                secondary_failed=secondary_failed,
            )
            publications.append(self._d3_publication(now))
            publications.append(self._d4_publication(now))
            self._next_assignment_s = _advance_schedule(
                self._next_assignment_s,
                config.assignment_period_s,
                now,
            )

        interceptor_acceleration = np.zeros((config.resource_count, 3), dtype=float)
        if self.latest_plan is not None and self.latest_d2_tracks:
            pair_inputs = self._guidance_inputs(step_input, now)
            self.latest_guidance_batch = self.d7.command_batch(
                pair_inputs,
                resource_count=config.resource_count,
            )
            interceptor_acceleration = self.latest_guidance_batch.to_world_acceleration()
            publications.append(self._d7_publication(now))

        return RuntimeStepOutput(
            interceptor_acceleration_ned=interceptor_acceleration,
            recon_acceleration_ned=np.zeros((config.recon_count, 3), dtype=float),
            publications=tuple(publications),
            diagnostics=self._diagnostics(now),
        )

    def _run_assignment_and_failover(
        self,
        step_input: RuntimeStepInput,
        *,
        now: float,
        center_health: C2Health,
        secondary_failed: bool,
    ) -> None:
        config = self._require_ready()
        tracks = self._d3_tracks()
        resources = self._d3_resources(step_input.interceptors)
        previous_plan = self.latest_plan
        current_target_ids = {track.track_id for track in tracks}
        previous_target_ids = (
            set()
            if previous_plan is None
            else {
                *(item.target_id for item in previous_plan.assignments),
                *previous_plan.unassigned_target_ids,
                *previous_plan.incomplete_target_ids,
            }
        )
        selected_secondary = (
            None
            if secondary_failed or previous_plan is None
            else self._selected_secondary_for_active_regions(previous_plan)
        )
        active_owner = (
            "center"
            if previous_plan is None
            else str(previous_plan.metadata.get("active_plan_owner", "center"))
        )
        if active_owner == "secondary" and previous_plan is not None:
            current_secondary = str(previous_plan.metadata.get("owner_node_id", ""))
            if selected_secondary != current_secondary:
                selected_secondary = None
        if center_health == C2Health.FAILED:
            if previous_plan is None:
                # No accepted authority exists from which a fallback generation
                # can legally advance.  The caller remains fail-closed.
                self.latest_plan = None
                self.latest_bindings = ()
                self.latest_d4_decision = None
                return
            if selected_secondary is None:
                # Region-specific or distributed D3 plans are not represented by
                # the current single-owner AssignmentPlan contract.
                self.latest_plan = previous_plan
            else:
                candidate = self.d3.plan(
                    tracks,
                    resources,
                    timestamp=now,
                    previous_plan=previous_plan,
                    expected_previous_version=previous_plan.version,
                    forced_replan=(
                        self._fault_generation_changed
                        or current_target_ids != previous_target_ids
                    ),
                    publish=False,
                )
                lease_expires_at = now + max(
                    config.assignment_period_s
                    * self.stack_config.assignment_lease_multiplier,
                    config.region_policy_period_s,
                )
                if active_owner == "secondary":
                    leader_epoch = int(
                        previous_plan.metadata.get(
                            "secondary_leader_epoch",
                            previous_plan.version,
                        )
                    )
                    self.latest_plan = continue_active_secondary_plan(
                        candidate,
                        previous_plan=previous_plan,
                        readiness_class="takeover_ready",
                        readiness_sustained=True,
                        published_at_s=now,
                        lease_expires_at_s=lease_expires_at,
                        leader_epoch=leader_epoch,
                    )
                else:
                    self.latest_plan = prepare_secondary_takeover_plan(
                        candidate,
                        supersedes_plan=previous_plan,
                        secondary_node_id=selected_secondary,
                        readiness_class="takeover_ready",
                        readiness_sustained=True,
                        activated_at_s=now,
                        lease_expires_at_s=lease_expires_at,
                        leader_epoch=previous_plan.version + 1,
                    )
                self.latest_plan = self.d3.publish_plan(self.latest_plan)
        else:
            self.latest_plan = self.d3.plan(
                tracks,
                resources,
                timestamp=now,
                previous_plan=previous_plan,
                expected_previous_version=(
                    None if previous_plan is None else previous_plan.version
                ),
                forced_replan=(
                    self._fault_generation_changed
                    or current_target_ids != previous_target_ids
                ),
            )
        self.latest_bindings = guidance_bindings_from_assignment_plan(
            self.latest_plan,
            resource_vehicle_map={
                resource_id: resource_id
                for resource_id in step_input.interceptors.platform_ids
            },
            now_s=now,
            previous_plan=previous_plan,
            current_plan_id=self.latest_plan.plan_id,
            current_plan_version=self.latest_plan.version,
        )
        snapshot = self._d4_snapshot(
            step_input,
            now=now,
            center_health=center_health,
            secondary_failed=secondary_failed,
        )
        self.latest_d4_decision = self.d4.evaluate(snapshot)

    def _selected_secondary_for_active_regions(self, plan: Any) -> str | None:
        """Return one D4-vetted owner only when it covers every active region."""

        if self.latest_d4_decision is None:
            return None
        active_regions = {
            self._track_region_by_id.get(assignment.target_id)
            for assignment in plan.assignments
        }
        active_regions.discard(None)
        if not active_regions:
            return None
        decision_by_region = {
            decision.region_id: decision
            for decision in self.latest_d4_decision.region_decisions
        }
        selected_ids: set[str] = set()
        for region_id in active_regions:
            decision = decision_by_region.get(str(region_id))
            if decision is None or decision.selected_secondary_id is None:
                return None
            readiness = decision.secondary_readiness.get(
                decision.selected_secondary_id,
                {},
            )
            if readiness.get("ready") is not True:
                return None
            selected_ids.add(decision.selected_secondary_id)
        return next(iter(selected_ids)) if len(selected_ids) == 1 else None

    def _d3_tracks(self) -> tuple[TargetTrack, ...]:
        config = self._require_ready()
        usable = tuple(
            track
            for track in self.latest_d2_tracks
            if _enum_value(track.lifecycle_state) not in {"lost", "dropped"}
        )
        high_count = 0
        if config.metadata.get("demand_pattern") == "hybrid_2_primary_1_reserve":
            fraction = float(config.metadata.get("high_threat_fraction", 0.10))
            high_count = max(1, int(math.ceil(len(usable) * fraction))) if usable else 0
        output: list[TargetTrack] = []
        all_regions = _region_ids(config.region_count)
        for index, track in enumerate(sorted(usable, key=lambda item: item.global_track_id)):
            position = np.asarray(track.state[:3], dtype=float)
            region_id = _region_for_position(position, config.region_count)
            self._track_region_by_id[track.global_track_id] = region_id
            distance = float(np.linalg.norm(position[:2]))
            threat = float(
                np.clip(
                    1.0
                    - (distance - config.protected_radius_m)
                    / max(_EPS, config.world_half_extent_m - config.protected_radius_m),
                    0.05,
                    0.95,
                )
            )
            demand = None
            if index < high_count:
                threat = max(threat, 0.95)
                demand = TargetDemand(
                    required_resource_count=3,
                    primary_resource_count=2,
                    coordination_mode="hybrid",
                )
            covariance_trace = float(np.trace(track.covariance[:3, :3]))
            output.append(
                TargetTrack(
                    track_id=track.global_track_id,
                    threat_score=threat,
                    covariance=float(np.clip(covariance_trace / 100.0, 0.0, 1.0)),
                    window_cost=0.0,
                    assignable=True,
                    position_ned=tuple(float(value) for value in position),
                    velocity_ned=tuple(float(value) for value in track.state[3:]),
                    position_covariance_ned=track.covariance[:3, :3].copy(),
                    region_id=region_id,
                    candidate_resource_region_ids=all_regions,
                    demand=demand,
                    metadata={
                        "global_track_id_owner": "D2_center",
                        "lifecycle_state": _enum_value(track.lifecycle_state),
                        "track_quality": float(track.track_quality),
                    },
                )
            )
        return tuple(output)

    def _d3_resources(
        self,
        navigation: PlatformNavigationBatch,
    ) -> tuple[ResourceState, ...]:
        config = self._require_ready()
        all_regions = _region_ids(config.region_count)
        resources: list[ResourceState] = []
        for index, resource_id in enumerate(navigation.platform_ids):
            active = bool(navigation.active[index])
            position = navigation.state_ned[index, :3]
            resources.append(
                ResourceState(
                    resource_id=resource_id,
                    status="available" if active else "unavailable",
                    availability_score=1.0 if active else 0.0,
                    position_ned=tuple(float(value) for value in position),
                    velocity_ned=tuple(
                        float(value) for value in navigation.state_ned[index, 3:]
                    ),
                    position_covariance_ned=navigation.covariance[index, :3, :3].copy(),
                    max_speed_mps=config.interceptor_speed_mps,
                    # The square workspace diameter is 2*sqrt(2)*half_extent.
                    max_intercept_range_m=3.0 * config.world_half_extent_m,
                    region_id=_region_for_position(position, config.region_count),
                    reachable_target_region_ids=all_regions,
                    capability_class="intercept_visual",
                )
            )
        return tuple(resources)

    def _d4_snapshot(
        self,
        step_input: RuntimeStepInput,
        *,
        now: float,
        center_health: C2Health,
        secondary_failed: bool,
    ) -> RegionalFailoverSnapshot:
        config = self._require_ready()
        plan = self.latest_plan
        scenario = RegionalScenarioMetadata.from_scalable_scenario(config.to_dict())
        regions = _region_definitions(scenario.region_ids)
        lease_expires_at = now + max(
            config.assignment_period_s * self.stack_config.assignment_lease_multiplier,
            config.region_policy_period_s,
        )
        track_by_id = {
            track.global_track_id: track for track in self.latest_d2_tracks
        }
        assignments_by_target = plan.assignments_by_target()
        coalition_by_target = {
            coalition.target_id: coalition for coalition in plan.coalitions
        }
        tasks: list[RegionalTaskEvidence] = []
        for target_id, assignments in assignments_by_target.items():
            track = track_by_id.get(target_id)
            if track is None:
                continue
            coalition = coalition_by_target.get(target_id)
            required_count = (
                coalition.required_resource_count
                if coalition is not None
                else assignments[0].required_resource_count
            )
            assigned_ids = tuple(item.resource_id for item in assignments)
            support_ids = tuple(
                resource_id
                for resource_id in assigned_ids
                if (resource_id, target_id) in self._latest_terminal_by_pair
            )
            terminal_applicable = self._terminal_applicable(
                target_id,
                assigned_ids,
                step_input.interceptors,
            )
            if not terminal_applicable:
                consistency = D5Consistency.NOT_APPLICABLE
            elif len(support_ids) == len(assigned_ids):
                consistency = D5Consistency.CONSISTENT
            else:
                consistency = D5Consistency.UNKNOWN
            tasks.append(
                RegionalTaskEvidence(
                    task_id=f"task:{target_id}",
                    global_track_id=target_id,
                    region_id=self._track_region_by_id.get(
                        target_id,
                        _region_for_position(track.state[:3], config.region_count),
                    ),
                    d3_plan_id=plan.plan_id,
                    d3_plan_version=plan.version,
                    d3_epoch=plan.version,
                    d3_lease_expires_at_s=lease_expires_at,
                    required_member_count=required_count,
                    required_capabilities=("intercept",),
                    d3_assigned_member_ids=assigned_ids,
                    coalition_id=(None if coalition is None else coalition.coalition_id),
                    coalition_version=(None if coalition is None else coalition.version),
                    d1_covariance_trace=float(np.trace(track.covariance[:3, :3])),
                    d1_measurement_age_s=max(0.0, now - float(track.last_update_time)),
                    d2_ambiguity_score=float(
                        0.0
                        if self.latest_d2_result is None
                        else self.latest_d2_result.ambiguity_score
                    ),
                    d2_id_switch_count=0,
                    d2_duplicate_track_count=0,
                    d3_is_current=True,
                    d3_resource_feasible=all(
                        item.feasibility_state == "feasible" for item in assignments
                    ),
                    d5_consistency=consistency,
                    d5_support_member_ids=support_ids,
                )
            )
        members = self._d4_members(
            step_input.interceptors,
            tuple(tasks),
        )
        secondaries = () if secondary_failed else self._d4_secondaries(
            step_input.recon,
            scenario.region_ids,
            now=now,
            epoch=plan.version,
            lease_expires_at=lease_expires_at,
        )
        acks = self._d4_acks(tasks, step_input.interceptors, now, lease_expires_at)
        return RegionalFailoverSnapshot(
            timestamp_s=now,
            scenario=scenario,
            center_health=center_health,
            center_node_id="d3_central",
            plan_id=plan.plan_id,
            plan_version=plan.version,
            epoch=plan.version,
            lease_expires_at_s=lease_expires_at,
            regions=regions,
            tasks=tuple(tasks),
            secondary_nodes=secondaries,
            fallback_members=members,
            coalition_acks=acks,
        )

    def _d4_members(
        self,
        navigation: PlatformNavigationBatch,
        tasks: tuple[RegionalTaskEvidence, ...],
    ) -> tuple[RegionalFallbackMember, ...]:
        config = self._require_ready()
        task_track = {
            task.task_id: next(
                track
                for track in self.latest_d2_tracks
                if track.global_track_id == task.global_track_id
            )
            for task in tasks
        }
        all_regions = _region_ids(config.region_count)
        members: list[RegionalFallbackMember] = []
        for index, resource_id in enumerate(navigation.platform_ids):
            scores: dict[str, float] = {}
            for task in tasks:
                distance = float(
                    np.linalg.norm(
                        navigation.state_ned[index, :3]
                        - task_track[task.task_id].state[:3]
                    )
                )
                assigned_bonus = 1_000.0 if resource_id in task.d3_assigned_member_ids else 0.0
                scores[task.task_id] = assigned_bonus - distance
            members.append(
                RegionalFallbackMember(
                    node_id=resource_id,
                    region_ids=all_regions,
                    capabilities=("intercept", "visual"),
                    task_bid_scores=scores,
                    available=bool(navigation.active[index]),
                    communication_ready=bool(navigation.active[index]),
                    max_concurrent_tasks=1,
                )
            )
        return tuple(members)

    def _d4_secondaries(
        self,
        navigation: PlatformNavigationBatch,
        region_ids: tuple[str, ...],
        *,
        now: float,
        epoch: int,
        lease_expires_at: float,
    ) -> tuple[MobileReconSecondary, ...]:
        active_indices = [
            index for index, active in enumerate(navigation.active) if bool(active)
        ]
        if not active_indices:
            return ()
        output: list[MobileReconSecondary] = []
        for rank, index in enumerate(active_indices):
            node_id = navigation.platform_ids[index]
            covered_regions = tuple(
                region_id
                for region_index, region_id in enumerate(region_ids)
                if region_index % len(active_indices) == rank
            )
            readiness = {
                region_id: SecondaryReadinessEvidence(
                    node_id=node_id,
                    current_time_s=now,
                    readiness_timestamp_s=now,
                    readiness_stale_after_s=1.0,
                    availability_confirmed=True,
                    lease_epoch=epoch,
                    lease_expires_at_s=lease_expires_at,
                    heartbeat_timestamp_s=now,
                    heartbeat_stale_after_s=1.0,
                    cue_freshness_s=0.0,
                    cue_stale_after_s=1.0,
                    gimbal_pointing_ok=True,
                    communication_received_timestamp_s=now,
                    communication_stale_after_s=1.0,
                    coverage_matches_requested_cell=True,
                    coverage_ratio=self.stack_config.secondary_coverage_ratio,
                    network_full_view_rate=(
                        self.stack_config.secondary_network_full_view_rate
                    ),
                    takeover_ready_sustained=True,
                    takeover_ready_since_s=max(0.0, now - 0.25),
                    takeover_ready_observation_count=3,
                )
                for region_id in covered_regions
            }
            output.append(
                MobileReconSecondary(
                    node_id=node_id,
                    readiness_by_region=readiness,
                    takeover_priority=rank,
                )
            )
        return tuple(output)

    def _d4_acks(
        self,
        tasks: Iterable[RegionalTaskEvidence],
        navigation: PlatformNavigationBatch,
        now: float,
        lease_expires_at: float,
    ) -> tuple[CoalitionMemberAck, ...]:
        active_by_id = {
            resource_id: bool(navigation.active[index])
            for index, resource_id in enumerate(navigation.platform_ids)
        }
        acks: list[CoalitionMemberAck] = []
        for task in tasks:
            if task.required_member_count <= 1:
                continue
            for resource_id in task.d3_assigned_member_ids:
                acks.append(
                    CoalitionMemberAck(
                        resource_id=resource_id,
                        global_track_id=task.global_track_id,
                        coalition_id=str(task.coalition_id),
                        coalition_version=int(task.coalition_version or 0),
                        plan_id=task.d3_plan_id,
                        plan_version=task.d3_plan_version,
                        epoch=task.d3_epoch,
                        can_execute=active_by_id.get(resource_id, False),
                        evidence_timestamp=now,
                        valid_until=lease_expires_at,
                    )
                )
        return tuple(acks)

    def _terminal_applicable(
        self,
        target_id: str,
        resource_ids: Iterable[str],
        navigation: PlatformNavigationBatch,
    ) -> bool:
        track = next(
            (item for item in self.latest_d2_tracks if item.global_track_id == target_id),
            None,
        )
        if track is None:
            return False
        index_by_id = {
            resource_id: index
            for index, resource_id in enumerate(navigation.platform_ids)
        }
        ranges = [
            float(
                np.linalg.norm(
                    navigation.state_ned[index_by_id[resource_id], :3]
                    - track.state[:3]
                )
            )
            for resource_id in resource_ids
            if resource_id in index_by_id
        ]
        return bool(ranges and min(ranges) <= self.stack_config.terminal_switch_range_m)

    def _guidance_inputs(
        self,
        step_input: RuntimeStepInput,
        now: float,
    ) -> tuple[AssignmentPairGuidanceInput3D, ...]:
        track_by_id = {
            track.global_track_id: track for track in self.latest_d2_tracks
        }
        output: list[AssignmentPairGuidanceInput3D] = []
        for binding in self.latest_bindings:
            resource_index = self._resource_index_by_id.get(binding.resource_id)
            track = track_by_id.get(binding.assigned_global_track_id)
            if resource_index is None or track is None:
                continue
            association_visual = self._latest_terminal_by_pair.get(
                (binding.resource_id, binding.assigned_global_track_id)
            )
            association = None if association_visual is None else association_visual[0]
            visual = None if association_visual is None else association_visual[1]
            permission = self._d4_permission(binding.assigned_global_track_id)
            output.append(
                AssignmentPairGuidanceInput3D(
                    resource_index=resource_index,
                    resource_state=step_input.interceptors.state_ned[resource_index],
                    global_track=track,
                    binding=binding,
                    d4_permission=permission,
                    terminal_association=association,
                    active_plan_id=self.latest_plan.plan_id,
                    active_plan_version=self.latest_plan.version,
                    timestamp_s=now,
                    visual_observation=visual,
                    camera_recognition_ready=visual is not None,
                    available_accel_mps2=self.d7.config.max_accel_mps2,
                )
            )
        return tuple(output)

    def _d4_permission(self, target_id: str) -> D4GuidancePermission:
        if self.latest_d4_decision is None:
            return D4GuidancePermission(
                action="hold_for_review",
                reason="d4_decision_missing",
                requires_human_review=True,
            )
        region_id = self._track_region_by_id.get(target_id)
        decision = next(
            (
                item
                for item in self.latest_d4_decision.region_decisions
                if item.region_id == region_id
            ),
            None,
        )
        if decision is None or not decision.execution_allowed:
            return D4GuidancePermission(
                action="hold_for_review",
                mode="hold",
                reason=("region_decision_missing" if decision is None else decision.reason),
                requires_human_review=True,
            )
        if decision.selected_layer is RegionalAuthorityLayer.SECONDARY:
            plan_owner = str(
                self.latest_plan.metadata.get("active_plan_owner", "center")
            )
            owner_node_id = str(
                self.latest_plan.metadata.get("owner_node_id", "")
            )
            if (
                plan_owner != "secondary"
                or not owner_node_id
                or owner_node_id != decision.ownership.owner_id
            ):
                return D4GuidancePermission(
                    action="hold_for_review",
                    mode="secondary",
                    reason="secondary_owner_plan_mismatch",
                    requires_human_review=True,
                )
            task_commit = next(
                (
                    commit
                    for commit in decision.coalition_commits
                    if commit.global_track_id == target_id
                ),
                None,
            )
            return D4GuidancePermission(
                action="continue",
                mode="secondary",
                reason=decision.reason,
                target_node_id=owner_node_id,
                terminal_consistent=True,
                new_plan_id=self.latest_plan.plan_id,
                new_plan_version=self.latest_plan.version,
                secondary_capability_class="mobile_high_recon",
                secondary_readiness_class="takeover_ready",
                visual_png_allowed=True,
                coalition_id=_coalition_id_for(self.latest_plan, target_id),
                coalition_version=_coalition_version_for(self.latest_plan, target_id),
                center_available=False,
                atomic_coalition_formed=(
                    None if task_commit is None else task_commit.atomic_committed
                ),
                coalition_commit_state=(
                    None if task_commit is None else task_commit.state
                ),
                coalition_epoch=self.latest_plan.version,
                coalition_lease_expires_at_s=(
                    None if task_commit is None else task_commit.lease_expires_at_s
                ),
                coalition_required_member_ids=(
                    () if task_commit is None else task_commit.required_member_ids
                ),
                coalition_acked_member_ids=(
                    () if task_commit is None else task_commit.acked_member_ids
                ),
                commit_plan_id=(
                    None if task_commit is None else self.latest_plan.plan_id
                ),
                commit_plan_version=(
                    None if task_commit is None else self.latest_plan.version
                ),
                commit_coalition_id=(
                    None
                    if task_commit is None
                    else _coalition_id_for(self.latest_plan, target_id)
                ),
                commit_coalition_version=(
                    None
                    if task_commit is None
                    else _coalition_version_for(self.latest_plan, target_id)
                ),
            )
        if decision.selected_layer is not RegionalAuthorityLayer.CENTER:
            return D4GuidancePermission(
                action="hold_for_review",
                mode=decision.selected_layer.value,
                reason="fallback_plan_not_yet_reissued_by_d3",
                requires_human_review=True,
            )
        action = decision.action.value
        if action not in {
            RegionalAction.CONTINUE_CENTER.value,
            RegionalAction.REQUEST_SECONDARY_ASSIST.value,
        }:
            return D4GuidancePermission(
                action="hold_for_review",
                reason=decision.reason,
                requires_human_review=True,
            )
        task_commit = next(
            (
                commit
                for commit in decision.coalition_commits
                if commit.global_track_id == target_id
            ),
            None,
        )
        return D4GuidancePermission(
            action=action,
            reason=decision.reason,
            terminal_consistent=True,
            new_plan_id=self.latest_plan.plan_id,
            new_plan_version=self.latest_plan.version,
            visual_png_allowed=True,
            coalition_id=(None if task_commit is None else _coalition_id_for(self.latest_plan, target_id)),
            coalition_version=(None if task_commit is None else _coalition_version_for(self.latest_plan, target_id)),
            atomic_coalition_formed=(
                None if task_commit is None else task_commit.atomic_committed
            ),
            coalition_commit_state=(None if task_commit is None else task_commit.state),
            coalition_epoch=(None if task_commit is None else self.latest_plan.version),
            coalition_lease_expires_at_s=(
                None if task_commit is None else task_commit.lease_expires_at_s
            ),
            coalition_required_member_ids=(
                () if task_commit is None else task_commit.required_member_ids
            ),
            coalition_acked_member_ids=(
                () if task_commit is None else task_commit.acked_member_ids
            ),
            commit_plan_id=(None if task_commit is None else self.latest_plan.plan_id),
            commit_plan_version=(None if task_commit is None else self.latest_plan.version),
            commit_coalition_id=(None if task_commit is None else _coalition_id_for(self.latest_plan, target_id)),
            commit_coalition_version=(None if task_commit is None else _coalition_version_for(self.latest_plan, target_id)),
        )

    def _terminal_pairs_from_d5(
        self,
        result: Any,
    ) -> dict[tuple[str, str], tuple[dict[str, Any], TerminalVisualObservation3D]]:
        graph = result.association.graph
        cluster_by_key = {
            cluster.cluster_key: cluster for cluster in result.association.clusters
        }
        geometry_by_key = {
            geometry.camera_key: geometry for geometry in result.camera_geometries
        }
        output: dict[
            tuple[str, str], tuple[dict[str, Any], TerminalVisualObservation3D]
        ] = {}
        for binding in result.association.bindings:
            if binding.decision_state != "bound" or binding.global_track_id is None:
                continue
            cluster = cluster_by_key[binding.cluster_key]
            for node_index in cluster.node_indices:
                tracklet = graph.nodes[node_index]
                if tracklet.resource_id not in self._resource_index_by_id:
                    continue
                geometry = geometry_by_key.get(tracklet.camera_key)
                if geometry is None or tracklet.bbox_xyxy is None:
                    continue
                confidence = float(
                    np.clip(
                        tracklet.confidence
                        * math.exp(-max(0.0, float(binding.cost or 0.0)) / 6.0),
                        0.0,
                        1.0,
                    )
                )
                association = {
                    "assigned_global_track_id": binding.global_track_id,
                    "local_track_id": tracklet.local_track_id,
                    "association_confidence": confidence,
                    "friend_conflict_state": "none",
                    "decision_state": "locked",
                    "assignment_version": (
                        None if self.latest_plan is None else self.latest_plan.version
                    ),
                    "plan_id": None if self.latest_plan is None else self.latest_plan.plan_id,
                    "plan_version": (
                        None if self.latest_plan is None else self.latest_plan.version
                    ),
                    "resource_id": tracklet.resource_id,
                    "metadata": {
                        "source": "d5_scalable_3d_sparse_graph",
                        "cross_view_support_count": len(cluster.node_indices),
                        "probability_source": result.association.probability_source,
                    },
                }
                camera = geometry.camera
                visual = TerminalVisualObservation3D(
                    timestamp_s=tracklet.measurement_timestamp,
                    bbox_xyxy=tracklet.bbox_xyxy,
                    image_width_px=int(camera.image_size[0]),
                    image_height_px=int(camera.image_size[1]),
                    camera_intrinsics=camera.K,
                    camera_to_ned_rotation=camera.R.T,
                    detection_confidence=tracklet.confidence,
                    local_track_id=tracklet.local_track_id,
                    assigned_global_track_id=binding.global_track_id,
                    camera_id=tracklet.camera_id,
                )
                output[(tracklet.resource_id, binding.global_track_id)] = (
                    association,
                    visual,
                )
        return output

    def _fault_state(self, now: float) -> tuple[C2Health, bool]:
        config = self._require_ready()
        center = C2Health.NORMAL
        secondary_failed = False
        schedule = config.metadata.get("fault_schedule", ())
        for raw in schedule if isinstance(schedule, (list, tuple)) else ():
            if not isinstance(raw, Mapping) or float(raw.get("time_s", math.inf)) > now:
                continue
            component = str(raw.get("component", "")).lower()
            action = str(raw.get("action", "")).lower()
            if component == "center":
                center = {
                    "normal": C2Health.NORMAL,
                    "degraded": C2Health.DEGRADED,
                    "suspect": C2Health.SUSPECT,
                    "failed": C2Health.FAILED,
                }.get(action, center)
            elif component == "secondary" and action == "failed":
                secondary_failed = True
        return center, secondary_failed

    def _d1_publication(self, result: Any, batch: OnlineSensorBatch, now: float) -> RuntimePublication:
        return RuntimePublication(
            topic="modules.d1.fused_tracks",
            source="D1",
            schema_version="d1-scalable3d-fusion-v1",
            payload={
                "timestamp": now,
                "batch_id": batch.batch_id,
                "sensor_id": batch.sensor_id,
                "track_count": len(result.tracks),
                "tracks": [_track_summary(track) for track in result.tracks],
                "summary": result.summary.to_dict(),
            },
        )

    def _d2_publication(self, now: float) -> RuntimePublication:
        result = self.latest_d2_result
        risk = result.risk_summary
        return RuntimePublication(
            topic="modules.d2.associated_tracks",
            source="D2",
            schema_version="d2-scalable3d-association-v1",
            payload={
                "timestamp": now,
                "track_count": len(self.latest_d2_tracks),
                "tracks": [_track_summary(track) for track in self.latest_d2_tracks],
                "association": {
                    "timestamp": float(result.timestamp),
                    "associator_type": result.associator_type,
                    "matched_pairs": [pair.to_dict() for pair in result.matched_pairs],
                    "unmatched_track_ids": list(result.unmatched_track_ids),
                    "unmatched_detection_ids": list(result.unmatched_detection_ids),
                    "ambiguity_score": float(result.ambiguity_score),
                    "rejected_pair_count": len(result.rejected_pairs),
                    "candidate_edge_count": int(
                        result.metadata.get("candidate_edge_count", 0)
                    ),
                    "dense_pair_count": int(
                        result.metadata.get("dense_pair_count", 0)
                    ),
                    "source_binding_conflicts": list(
                        result.metadata.get("source_binding_conflicts", ())
                    ),
                    "risk_summary": (
                        None
                        if risk is None
                        else {
                            "association_ambiguity": risk.association_ambiguity,
                            "duplicate_track_risk": risk.duplicate_track_risk,
                            "covariance_overlap_rate": risk.covariance_overlap_rate,
                            "source_binding_conflict_count": (
                                risk.source_binding_conflict_count
                            ),
                        }
                    ),
                },
                "id_switch_count": None,
                "id_switch_count_available": False,
            },
        )

    def _d3_publication(self, now: float) -> RuntimePublication:
        plan = self.latest_plan
        return RuntimePublication(
            topic="modules.d3.assignment_plan",
            source="D3",
            schema_version=str(plan.plan_schema),
            payload={
                "timestamp": now,
                "plan_id": plan.plan_id,
                "plan_version": plan.version,
                "created_at": plan.created_at,
                "assignment_count": len(plan.assignments),
                "target_count": plan.target_count,
                "resource_count": plan.resource_count,
                "assignments": [
                    {
                        "resource_id": item.resource_id,
                        "global_track_id": item.target_id,
                        "coalition_id": item.coalition_id,
                        "coalition_version": item.coalition_version,
                        "member_role": item.member_role,
                    }
                    for item in plan.assignments
                ],
                "unassigned_global_track_ids": list(plan.unassigned_target_ids),
                "solver_name": plan.solver_name,
                "metadata": dict(plan.metadata),
            },
        )

    def _d4_publication(self, now: float) -> RuntimePublication:
        return RuntimePublication(
            topic="modules.d4.regional_failover",
            source="D4",
            schema_version="d4-regional-failover-v1",
            payload=self.latest_d4_decision.to_bus_payload(),
        )

    def _d5_publication(self, now: float) -> RuntimePublication:
        association = self.latest_d5_result.association
        return RuntimePublication(
            topic="modules.d5.terminal_association",
            source="D5",
            schema_version="d5-scalable3d-association-v1",
            payload={
                "timestamp": now,
                "camera_batch_count": len(self.latest_d5_result.camera_batches),
                "tracklet_count": len(self.latest_d5_result.tracklets),
                "graph_node_count": association.graph.node_count,
                "graph_edge_count": association.graph.edge_count,
                "probability_source": association.probability_source,
                "scoring_status": association.scoring_status,
                "fallback_reason": association.fallback_reason,
                "bindings": [
                    {
                        "cluster_key": item.cluster_key,
                        "global_track_id": item.global_track_id,
                        "decision_state": item.decision_state,
                        "cost": item.cost,
                        "supporting_tracklet_keys": list(item.supporting_tracklet_keys),
                    }
                    for item in association.bindings
                ],
            },
        )

    def _d7_publication(self, now: float) -> RuntimePublication:
        commands = self.latest_guidance_batch.pair_commands
        mode_counts = Counter(command.mode.value for command in commands)
        return RuntimePublication(
            topic="modules.d7.guidance_commands",
            source="D7",
            schema_version="d7-scalable3d-guidance-v1",
            payload={
                "timestamp": now,
                "command_count": len(commands),
                "mode_counts": dict(sorted(mode_counts.items())),
                "commands": [
                    {
                        "resource_id": command.resource_id,
                        "global_track_id": command.assigned_global_track_id,
                        "plan_id": command.plan_id,
                        "plan_version": command.plan_version,
                        "mode": command.mode.value,
                        "acceleration_ned_mps2": list(command.acceleration_ned_mps2),
                        "command_norm_mps2": command.command_norm_mps2,
                        "gate_reason": command.gate_reason,
                        "visual_switch_allowed": command.visual_switch_allowed,
                    }
                    for command in commands
                ],
            },
        )

    def _diagnostics(self, now: float) -> dict[str, Any]:
        return {
            "schema_version": INTEGRATED_STACK_SCHEMA_VERSION,
            "timestamp": now,
            "d1_track_count": len(self.latest_d1_tracks),
            "d2_track_count": len(self.latest_d2_tracks),
            "d3_assignment_count": (
                0 if self.latest_plan is None else len(self.latest_plan.assignments)
            ),
            "d4_region_count": (
                0
                if self.latest_d4_decision is None
                else len(self.latest_d4_decision.region_decisions)
            ),
            "d5_binding_count": (
                0
                if self.latest_d5_result is None
                else sum(
                    item.global_track_id is not None
                    for item in self.latest_d5_result.association.bindings
                )
            ),
            "d7_command_count": (
                0
                if self.latest_guidance_batch is None
                else len(self.latest_guidance_batch.pair_commands)
            ),
            "online_truth_use_count": 0,
        }

    def _validate_navigation(
        self,
        navigation: PlatformNavigationBatch,
        expected_kind: str,
    ) -> None:
        if navigation.platform_kind != expected_kind:
            raise ValueError(
                f"expected {expected_kind} navigation, got {navigation.platform_kind}"
            )

    def _require_ready(self) -> ScenarioConfig:
        if self.config is None:
            raise RuntimeError("module stack must be reset before step")
        assert self.d1 is not None
        assert self.d2 is not None
        assert self.d3 is not None
        assert self.d4 is not None
        assert self.d5 is not None
        assert self.d7 is not None
        return self.config


def _batch_modality(batch: OnlineSensorBatch) -> str:
    modalities = {str(item.modality).lower() for item in batch.measurements}
    if len(modalities) != 1:
        raise ValueError("online sensor batch must contain one modality")
    return next(iter(modalities))


def _advance_schedule(current: float, period: float, now: float) -> float:
    value = float(current)
    while value <= now + _EPS:
        value += float(period)
    return value


def _region_ids(count: int) -> tuple[str, ...]:
    width = max(3, len(str(int(count))))
    return tuple(f"region-{index:0{width}d}" for index in range(int(count)))


def _region_for_position(position_ned: np.ndarray, region_count: int) -> str:
    position = np.asarray(position_ned, dtype=float).reshape(3)
    angle = math.atan2(float(position[1]), float(position[0])) % (2.0 * math.pi)
    index = min(
        region_count - 1,
        int(math.floor(angle / (2.0 * math.pi) * region_count)),
    )
    return _region_ids(region_count)[index]


def _region_definitions(region_ids: tuple[str, ...]) -> tuple[RegionDefinition, ...]:
    if len(region_ids) == 1:
        return (RegionDefinition(region_ids[0], "sector-000"),)
    return tuple(
        RegionDefinition(
            region_id=region_id,
            coverage_cell=f"sector-{index:03d}",
            neighbor_region_ids=(
                region_ids[(index - 1) % len(region_ids)],
                region_ids[(index + 1) % len(region_ids)],
            ),
        )
        for index, region_id in enumerate(region_ids)
    )


def _track_summary(track: Any) -> dict[str, Any]:
    lifecycle = getattr(track, "lifecycle_state", getattr(track, "track_level", "unknown"))
    return {
        "global_track_id": str(track.global_track_id),
        "timestamp": float(track.timestamp),
        "state_ned": np.asarray(track.state, dtype=float).tolist(),
        "covariance": np.asarray(track.covariance, dtype=float).tolist(),
        "track_state": _enum_value(lifecycle),
    }


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw).lower()


def _coalition_id_for(plan: Any, target_id: str) -> str | None:
    coalition = next(
        (item for item in plan.coalitions if item.target_id == target_id),
        None,
    )
    return None if coalition is None else coalition.coalition_id


def _coalition_version_for(plan: Any, target_id: str) -> int | None:
    coalition = next(
        (item for item in plan.coalitions if item.target_id == target_id),
        None,
    )
    return None if coalition is None else coalition.version
