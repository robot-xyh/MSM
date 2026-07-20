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
from time import perf_counter
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
    REGIONAL_PLANNING_HINT_SCHEMA_V1,
    RegionalAuthorityGrant,
    RegionalAuthorityInput,
    RegionalCoalitionCommitEvidence,
    RegionalPlanAuthorityError,
    ResourceState,
    TargetDemand,
    TargetTrack,
    continue_active_secondary_plan,
    guidance_bindings_from_assignment_plan,
    prepare_secondary_takeover_plan,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    AdvisorMode,
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
    RegionResourceEdge,
    RegionResourceAdvisoryGate,
    RegionResourceAdvisor,
    RegionResourceAdvisorConfig,
    RegionResourceProjectionConfig,
    RegionResourceSnapshot,
    RegionalScenarioMetadata,
    RegionalTaskEvidence,
    SecondaryReadinessEvidence,
)
from research_modules.d5_terminal_association.src.d5_terminal_association import (
    ActiveVisionAssignmentReference,
    ActiveVisionCameraState,
    ActiveVisionCameraFeedbackV1,
    ActiveVisionCommunicationState,
    ActiveVisionControllerV1,
    ActiveVisionFovMode,
    ActiveVisionPlanReference,
    ActiveVisionProjectionEvidence,
    ActiveVisionRuntimeMode,
    ActiveVisionSnapshotV1,
    ActiveVisionTrackReference,
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
    CameraObservationCommand,
    CameraRuntimeState,
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
    d4_advisory_ttl_multiplier: float = 1.5
    terminal_switch_range_m: float = 120.0
    secondary_coverage_ratio: float = 0.90
    secondary_network_full_view_rate: float = 0.90
    capture_learning_artifacts: bool = False
    d5_active_vision_enabled: bool = True
    d5_active_vision_mode: str = "disabled"
    d5_active_vision_zoom_fov_deg: float = 30.0

    def __post_init__(self) -> None:
        if self.assignment_lease_multiplier <= 1.0:
            raise ValueError("assignment_lease_multiplier must exceed one")
        if self.d3_candidate_edges_per_target <= 0:
            raise ValueError("d3_candidate_edges_per_target must be positive")
        if self.d3_unassigned_base_cost <= 0.0:
            raise ValueError("d3_unassigned_base_cost must be positive")
        if self.d4_advisory_ttl_multiplier <= 1.0:
            raise ValueError("d4_advisory_ttl_multiplier must exceed one")
        if self.terminal_switch_range_m <= 0.0:
            raise ValueError("terminal_switch_range_m must be positive")
        active_mode = str(self.d5_active_vision_mode).strip().lower()
        if active_mode not in {"disabled", "shadow", "assist"}:
            raise ValueError(
                "d5_active_vision_mode must be disabled, shadow, or assist"
            )
        object.__setattr__(self, "d5_active_vision_mode", active_mode)
        if not 1.0 < float(self.d5_active_vision_zoom_fov_deg) < 179.0:
            raise ValueError("d5_active_vision_zoom_fov_deg must be in (1, 179)")
        for name in ("secondary_coverage_ratio", "secondary_network_full_view_rate"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")


@dataclass(frozen=True)
class D4RegionLearningFrame:
    """One truth-free regional snapshot and its optional advisory output."""

    frame_index: int
    timestamp_s: float
    snapshot: Any
    recommendation: Any | None


@dataclass(frozen=True)
class D5GraphLearningFrame:
    """One anonymous cross-camera graph with measurement-to-tracklet links."""

    frame_index: int
    timestamp_s: float
    graph: Any
    source_observation_links: tuple[Any, ...]


@dataclass(frozen=True)
class D5ActiveVisionLearningFrame:
    """One truth-free active-vision decision frame and camera feedback."""

    frame_index: int
    timestamp_s: float
    snapshot: ActiveVisionSnapshotV1
    decisions: tuple[Any, ...]
    camera_feedback: tuple[ActiveVisionCameraFeedbackV1, ...]


@dataclass(frozen=True)
class IntegratedLearningArtifacts:
    """Detached, truth-free episode artifacts for offline dataset construction."""

    d3_planning_frames: tuple[Any, ...]
    d4_region_frames: tuple[D4RegionLearningFrame, ...]
    d5_graph_frames: tuple[D5GraphLearningFrame, ...]
    d5_active_vision_frames: tuple[D5ActiveVisionLearningFrame, ...] = ()


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
        d3_learning_assistant: Any | None = None,
        d4_region_advisor: Any | None = None,
        d4_unseen_seed_count: int = 0,
        d5_edge_model: Any | None = None,
        d5_active_vision_policy: Any | None = None,
        learning_runtime_diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        self.stack_config = config or IntegratedStackConfig()
        if int(d4_unseen_seed_count) < 0:
            raise ValueError("d4_unseen_seed_count must be non-negative")
        self.d3_learning_assistant = d3_learning_assistant
        self._configured_d4_region_advisor = d4_region_advisor
        self.d4_region_advisor = d4_region_advisor
        self.d4_unseen_seed_count = int(d4_unseen_seed_count)
        self.d5_edge_model = d5_edge_model
        self.d5_active_vision_policy = d5_active_vision_policy
        self.learning_runtime_diagnostics = dict(
            learning_runtime_diagnostics or {}
        )
        self.config: ScenarioConfig | None = None
        self.d1: Scalable3DFusionAdapter | None = None
        self.d2: Scalable3DTracker | None = None
        self.d3: AssignmentPlanner | None = None
        self.d4: RegionalFailoverCoordinator | None = None
        self.d5: Scalable3DTerminalAdapter | None = None
        self.d7: ScalableGuidanceController3D | None = None
        self.d5_active_vision: ActiveVisionControllerV1 | None = None
        self.latest_d1_tracks: tuple[Any, ...] = ()
        self.latest_d2_tracks: tuple[Any, ...] = ()
        self.latest_d2_result: Any | None = None
        self.latest_plan: Any | None = None
        self.latest_bindings: tuple[Any, ...] = ()
        self.latest_d4_decision: Any | None = None
        self.latest_d4_region_snapshot: Any | None = None
        self.latest_d4_region_advice: Any | None = None
        self.latest_d4_region_consumption: Any | None = None
        self.latest_d5_result: Any | None = None
        self.latest_guidance_batch: Any | None = None
        self.latest_active_vision_snapshot: ActiveVisionSnapshotV1 | None = None
        self.latest_active_vision_decisions: tuple[Any, ...] = ()
        self._latest_terminal_by_pair: dict[tuple[str, str], tuple[dict[str, Any], Any]] = {}
        self._track_region_by_id: dict[str, str] = {}
        self._resource_index_by_id: dict[str, int] = {}
        self._next_association_s = 0.0
        self._next_assignment_s = 0.0
        self._next_active_vision_s = 0.0
        self._active_vision_communication_version = 0
        self._last_center_health = C2Health.NORMAL
        self._last_secondary_failed = False
        self._fault_generation_changed = False
        self._regional_plan_rejection_reason: str | None = None
        self._d4_region_hint_bridge_rejection_reason: str | None = None
        self._d4_region_advisory_gate: RegionResourceAdvisoryGate | None = None
        self._next_d4_region_hint_version = 1
        self._d3_learning_frames: list[Any] = []
        self._d4_learning_frames: list[D4RegionLearningFrame] = []
        self._d5_learning_frames: list[D5GraphLearningFrame] = []
        self._d5_active_vision_learning_frames: list[
            D5ActiveVisionLearningFrame
        ] = []
        self._d2_identity_lineage_by_track: dict[str, tuple[dict[str, Any], ...]] = {}
        self._d2_observation_replay_generation: dict[str, int] = {}
        self._d1_latest_lineage_by_observation: dict[str, dict[str, Any]] = {}
        self._stage_wall_time_s: dict[str, float] = {}
        self._stage_call_count: dict[str, int] = {}

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
            ),
            learning_assistant=self.d3_learning_assistant,
        )
        self.d4 = RegionalFailoverCoordinator()
        if self._configured_d4_region_advisor is None:
            ttl_s = max(
                config.assignment_period_s * self.stack_config.d4_advisory_ttl_multiplier,
                config.assignment_period_s + config.physics_dt_s,
            )
            self.d4_region_advisor = RegionResourceAdvisor(
                config=RegionResourceAdvisorConfig(
                    mode=AdvisorMode.SHADOW,
                    projection=RegionResourceProjectionConfig(
                        advisory_ttl_s=ttl_s,
                    ),
                )
            )
        else:
            self.d4_region_advisor = self._configured_d4_region_advisor
        self._d4_region_advisory_gate = RegionResourceAdvisoryGate(
            projector=getattr(self.d4_region_advisor, "projector", None)
        )
        self.d5 = Scalable3DTerminalAdapter()
        self.d7 = ScalableGuidanceController3D(
            ScalableGuidanceConfig3D(
                terminal_switch_range_m=self.stack_config.terminal_switch_range_m,
                intercept_radius_m=config.intercept_radius_m,
            )
        )
        self.d5_active_vision = ActiveVisionControllerV1(
            learned_policy=self.d5_active_vision_policy,
            default_mode=ActiveVisionRuntimeMode(
                self.stack_config.d5_active_vision_mode
            ),
        )
        self.latest_d1_tracks = ()
        self.latest_d2_tracks = ()
        self.latest_d2_result = None
        self.latest_plan = None
        self.latest_bindings = ()
        self.latest_d4_decision = None
        self.latest_d4_region_snapshot = None
        self.latest_d4_region_advice = None
        self.latest_d4_region_consumption = None
        self.latest_d5_result = None
        self.latest_guidance_batch = None
        self.latest_active_vision_snapshot = None
        self.latest_active_vision_decisions = ()
        self._latest_terminal_by_pair.clear()
        self._track_region_by_id.clear()
        self._resource_index_by_id.clear()
        self._next_association_s = 0.0
        self._next_assignment_s = 0.0
        self._next_active_vision_s = 0.0
        self._active_vision_communication_version = 0
        self._last_center_health = C2Health.NORMAL
        self._last_secondary_failed = False
        self._fault_generation_changed = False
        self._regional_plan_rejection_reason = None
        self._d4_region_hint_bridge_rejection_reason = None
        self._next_d4_region_hint_version = 1
        self._d3_learning_frames.clear()
        self._d4_learning_frames.clear()
        self._d5_learning_frames.clear()
        self._d5_active_vision_learning_frames.clear()
        self._d2_identity_lineage_by_track.clear()
        self._d2_observation_replay_generation.clear()
        self._d1_latest_lineage_by_observation.clear()
        self._stage_wall_time_s.clear()
        self._stage_call_count.clear()

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
            started = perf_counter()
            result = self.d1.process_online_sensor_batch(batch)
            self._record_timing("d1_fusion", perf_counter() - started)
            self.latest_d1_tracks = tuple(result.tracks)
            d1_updated = True
            publications.append(self._d1_publication(result, batch, now))

        if (
            d1_updated
            and self.latest_d1_tracks
            and now + _EPS >= self._next_association_s
        ):
            started = perf_counter()
            _, detections = detections3d_from_d1_global_tracks(
                self.latest_d1_tracks
            )
            if detections:
                d2_timestamp = max(item.measurement_timestamp for item in detections)
                self.latest_d2_result = self.d2.step(detections, d2_timestamp)
                self.latest_d2_tracks = tuple(self.d2.active_tracks())
                self._update_d2_identity_lineage(
                    self.latest_d2_result,
                    detections,
                )
                publications.append(self._d2_publication(now))
            self._record_timing("d2_association", perf_counter() - started)
            self._next_association_s = _advance_schedule(
                self._next_association_s,
                config.association_period_s,
                now,
            )

        if vision_batches:
            started = perf_counter()
            self.latest_d5_result = self.d5.process(
                vision_batches,
                self.latest_d2_tracks,
                edge_model=self.d5_edge_model,
            )
            self._latest_terminal_by_pair = self._terminal_pairs_from_d5(
                self.latest_d5_result
            )
            if self.stack_config.capture_learning_artifacts:
                self._d5_learning_frames.append(
                    D5GraphLearningFrame(
                        frame_index=len(self._d5_learning_frames),
                        timestamp_s=now,
                        graph=self.latest_d5_result.association.graph,
                        source_observation_links=tuple(
                            self.latest_d5_result.source_observation_links
                        ),
                    )
                )
            self._record_timing("d5_terminal_association", perf_counter() - started)
            publications.append(self._d5_publication(now))

        center_health, secondary_failed = self._fault_state(now)
        self._fault_generation_changed = bool(
            self._fault_generation_changed
            or center_health != self._last_center_health
            or secondary_failed != self._last_secondary_failed
        )
        self._last_center_health = center_health
        self._last_secondary_failed = secondary_failed
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
            if self.stack_config.capture_learning_artifacts:
                self._d3_learning_frames.append(self.d3.latest_planning_evidence)
            publications.append(self._d3_publication(now))
            publications.append(self._d4_publication(now))
            if self.latest_d4_region_consumption is not None:
                publications.append(self._d4_region_consumption_publication(now))
            if self.latest_d4_region_advice is not None:
                publications.append(self._d4_region_advice_publication(now))
            self._fault_generation_changed = False
            self._next_assignment_s = _advance_schedule(
                self._next_assignment_s,
                config.assignment_period_s,
                now,
            )

        camera_commands: tuple[CameraObservationCommand, ...] = ()
        if (
            self.stack_config.d5_active_vision_enabled
            and self.latest_plan is not None
            and self.latest_d2_tracks
            and step_input.cameras
            and now + _EPS >= self._next_active_vision_s
        ):
            started = perf_counter()
            camera_commands = self._run_active_vision(step_input, now)
            self._record_timing("d5_active_vision", perf_counter() - started)
            publications.append(self._d5_active_vision_publication(now, camera_commands))
            self._next_active_vision_s = _advance_schedule(
                self._next_active_vision_s,
                config.visual_period_s,
                now,
            )

        interceptor_acceleration = np.zeros((config.resource_count, 3), dtype=float)
        if self.latest_plan is not None and self.latest_d2_tracks:
            started = perf_counter()
            pair_inputs = self._guidance_inputs(step_input, now)
            self.latest_guidance_batch = self.d7.command_batch(
                pair_inputs,
                resource_count=config.resource_count,
            )
            interceptor_acceleration = self.latest_guidance_batch.to_world_acceleration()
            self._record_timing("d7_guidance", perf_counter() - started)
            publications.append(self._d7_publication(now))

        return RuntimeStepOutput(
            interceptor_acceleration_ned=interceptor_acceleration,
            recon_acceleration_ned=np.zeros((config.recon_count, 3), dtype=float),
            camera_commands=camera_commands,
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
        previous_region_snapshot = self.latest_d4_region_snapshot
        previous_region_advice = self.latest_d4_region_advice
        previous_d4_decision = self.latest_d4_decision
        self.latest_d4_region_advice = None
        self.latest_d4_region_consumption = None
        self._d4_region_hint_bridge_rejection_reason = None
        adapter_started = perf_counter()
        tracks = self._d3_tracks()
        resources = self._d3_resources(step_input.interceptors)
        self._record_timing("main_d3_adapter", perf_counter() - adapter_started)
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
            regional_authority: RegionalAuthorityInput | None = None
            regional_authority_attempted = self._has_fallback_authority_decision()
            if regional_authority_attempted:
                try:
                    regional_authority = self._regional_authority_from_d4(
                        previous_plan,
                        target_ids=current_target_ids,
                        now=now,
                    )
                except RegionalPlanAuthorityError as error:
                    self._regional_plan_rejection_reason = error.reason

            if regional_authority is not None:
                if previous_region_advice is not None:
                    self._d4_region_hint_bridge_rejection_reason = (
                        "regional_authority_path_does_not_consume_resource_advice"
                    )
                started = perf_counter()
                try:
                    self.latest_plan = self.d3.plan_regional_authority(
                        tracks,
                        resources,
                        timestamp=now,
                        previous_plan=previous_plan,
                        authority=regional_authority,
                        expected_previous_version=previous_plan.version,
                    )
                    self._regional_plan_rejection_reason = None
                except RegionalPlanAuthorityError as error:
                    self.latest_plan = previous_plan
                    self._regional_plan_rejection_reason = error.reason
                self._record_timing("d3_regional_assignment", perf_counter() - started)
            elif regional_authority_attempted:
                # A malformed or incomplete regional authority must not fall
                # through to a different owner path.
                self.latest_plan = previous_plan
            elif selected_secondary is not None:
                regional_hint = self._d3_regional_hint_from_previous_d4(
                    previous_plan=previous_plan,
                    advice_result=previous_region_advice,
                    source_snapshot=previous_region_snapshot,
                    source_decision=previous_d4_decision,
                    now=now,
                    fault_generation_changed=self._fault_generation_changed,
                )
                started = perf_counter()
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
                    regional_planning_hint=regional_hint,
                )
                self._record_d3_regional_hint_outcome(candidate, regional_hint)
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
                self._record_timing("d3_assignment", perf_counter() - started)
                self._regional_plan_rejection_reason = None
            elif self._fault_generation_changed:
                if previous_region_advice is not None:
                    self._d4_region_hint_bridge_rejection_reason = (
                        "fault_generation_changed_before_advisory_consumption"
                    )
                # Multi-owner fallback requires D4 to observe a strictly newer
                # D3 generation before authority can change.  This center-owned
                # fence plan is immediately gated by the D4 decision below.
                started = perf_counter()
                self.latest_plan = self.d3.advance_authority_generation(
                    previous_plan,
                    timestamp=now,
                    expected_previous_version=previous_plan.version,
                    fence_reason="fault_generation_before_regional_adjudication",
                )
                self._record_timing("d3_authority_fence", perf_counter() - started)
                self._regional_plan_rejection_reason = None
            else:
                self.latest_plan = previous_plan
        else:
            regional_hint = self._d3_regional_hint_from_previous_d4(
                previous_plan=previous_plan,
                advice_result=previous_region_advice,
                source_snapshot=previous_region_snapshot,
                source_decision=previous_d4_decision,
                now=now,
                fault_generation_changed=self._fault_generation_changed,
            )
            started = perf_counter()
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
                regional_planning_hint=regional_hint,
            )
            self._record_d3_regional_hint_outcome(
                self.latest_plan,
                regional_hint,
            )
            self._record_timing("d3_assignment", perf_counter() - started)
            self._regional_plan_rejection_reason = None
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
        adapter_started = perf_counter()
        snapshot = self._d4_snapshot(
            step_input,
            now=now,
            center_health=center_health,
            secondary_failed=secondary_failed,
        )
        self._record_timing("main_d4_adapter", perf_counter() - adapter_started)
        started = perf_counter()
        self.latest_d4_decision = self.d4.evaluate(snapshot)
        self._record_timing("d4_regional_failover", perf_counter() - started)
        self._run_d4_region_resource_advisor(
            step_input,
            formal_snapshot=snapshot,
            now=now,
        )

    def _d3_regional_hint_from_previous_d4(
        self,
        *,
        previous_plan: Any | None,
        advice_result: Any | None,
        source_snapshot: Any | None,
        source_decision: Any | None,
        now: float,
        fault_generation_changed: bool,
    ) -> Mapping[str, Any] | None:
        """Gate one prior D4 advisory and translate it into a D3-owned DTO.

        The D4 snapshot and formal decision are deliberately frozen with the
        advisory.  D4 first revalidates that exact authority generation; D3
        then independently checks the current plan, resources, commitments,
        reserve and candidate graph before applying the hint.
        """

        if advice_result is None:
            return None
        if fault_generation_changed:
            self._d4_region_hint_bridge_rejection_reason = (
                "fault_generation_changed_before_advisory_consumption"
            )
            return None
        if previous_plan is None:
            self._d4_region_hint_bridge_rejection_reason = (
                "regional_advisory_previous_plan_missing"
            )
            return None
        effective_mode = getattr(advice_result, "effective_mode", None)
        effective_mode_value = getattr(effective_mode, "value", effective_mode)
        if str(effective_mode_value).lower() != AdvisorMode.ASSIST.value or not bool(
            getattr(advice_result, "assist_eligible", False)
        ):
            self._d4_region_hint_bridge_rejection_reason = (
                "regional_advisory_not_assist_eligible"
            )
            return None
        advisory = getattr(advice_result, "advisory_contract", None)
        if advisory is None:
            self._d4_region_hint_bridge_rejection_reason = (
                "regional_advisory_contract_missing"
            )
            return None
        if source_snapshot is None or source_decision is None:
            self._d4_region_hint_bridge_rejection_reason = (
                "regional_advisory_source_evidence_missing"
            )
            return None
        if self._d4_region_advisory_gate is None:
            self._d4_region_hint_bridge_rejection_reason = (
                "regional_advisory_gate_unavailable"
            )
            return None

        try:
            consumption = self._d4_region_advisory_gate.consume(
                advisory,
                source_snapshot,
                evaluated_at_s=now,
                formal_decision=source_decision,
            )
        except Exception as exc:
            self._d4_region_hint_bridge_rejection_reason = (
                f"regional_advisory_gate_error:{type(exc).__name__}"
            )
            return None
        self.latest_d4_region_consumption = consumption
        if not consumption.consumable:
            first_reason = (
                consumption.rejection_reasons[0]
                if consumption.rejection_reasons
                else "unspecified"
            )
            self._d4_region_hint_bridge_rejection_reason = (
                f"regional_advisory_rejected:{first_reason}"
            )
            return None

        source_plans = tuple(advisory.source_plan_versions)
        expected_source = (str(previous_plan.plan_id), int(previous_plan.version))
        if len(source_plans) != 1 or source_plans[0] != expected_source:
            self._d4_region_hint_bridge_rejection_reason = (
                "regional_advisory_source_plan_mismatch"
            )
            return None

        advisory_version = self._next_d4_region_hint_version
        self._next_d4_region_hint_version += 1
        constraints = tuple(
            {
                "region_id": region.region_id,
                "owner_id": region.source_version.owner_id,
                "owner_layer": region.source_version.owner_layer.value,
                "owner_epoch": int(region.source_version.epoch),
                "lease_expires_at_s": float(
                    region.source_version.lease_expires_at_s
                ),
                "source_plan_id": expected_source[0],
                "source_plan_version": expected_source[1],
                "resource_quota_delta": int(region.resource_quota_delta),
                "reserve_ratio": float(region.reserve_ratio),
                "hold": bool(region.hold),
                "request_replan": bool(region.request_replan),
            }
            for region in advisory.regions
        )
        transfers = tuple(
            {
                "source_region_id": transfer.source_region_id,
                "target_region_id": transfer.target_region_id,
                "resource_count": int(transfer.resource_count),
                "edge_id": transfer.edge_id,
                "expected_transfer_time_s": float(
                    transfer.expected_transfer_time_s
                ),
            }
            for transfer in advisory.transfers
        )
        return {
            "schema": REGIONAL_PLANNING_HINT_SCHEMA_V1,
            "advisory_id": advisory.advisory_id,
            "advisory_version": advisory_version,
            "created_at_s": float(advisory.created_at_s),
            "expires_at_s": float(advisory.valid_until_s),
            "source_plan_id": expected_source[0],
            "source_plan_version": expected_source[1],
            "projected": bool(advisory.projected),
            "constraints": constraints,
            "transfer_allowances": transfers,
        }

    def _record_d3_regional_hint_outcome(
        self,
        plan: Any,
        regional_hint: Mapping[str, Any] | None,
    ) -> None:
        if regional_hint is None:
            return
        metadata = getattr(plan, "metadata", {})
        if bool(metadata.get("regional_hint_applied", False)):
            self._d4_region_hint_bridge_rejection_reason = None
            return
        reason = metadata.get("regional_hint_fallback_reason")
        self._d4_region_hint_bridge_rejection_reason = (
            "d3_regional_hint_rejected:"
            f"{reason or 'unspecified'}"
        )

    def _run_d4_region_resource_advisor(
        self,
        step_input: RuntimeStepInput,
        *,
        formal_snapshot: RegionalFailoverSnapshot,
        now: float,
    ) -> None:
        """Publish aggregate advice without mutating D4 authority or D3 plans."""

        if self.latest_d4_decision is None:
            return
        if (
            self.d4_region_advisor is None
            and not self.stack_config.capture_learning_artifacts
        ):
            return
        started = perf_counter()
        regional_snapshot = self._d4_region_resource_snapshot(
            step_input,
            formal_snapshot=formal_snapshot,
            now=now,
        )
        self.latest_d4_region_snapshot = regional_snapshot
        recommendation = None
        if self.d4_region_advisor is not None:
            recommendation = self.d4_region_advisor.advise(
                regional_snapshot,
                formal_decision=self.latest_d4_decision,
                unseen_seed_count=self.d4_unseen_seed_count,
            )
            self.latest_d4_region_advice = recommendation
        if self.stack_config.capture_learning_artifacts:
            self._d4_learning_frames.append(
                D4RegionLearningFrame(
                    frame_index=len(self._d4_learning_frames),
                    timestamp_s=now,
                    snapshot=regional_snapshot,
                    recommendation=recommendation,
                )
            )
        self._record_timing(
            "d4_region_resource_advisor",
            perf_counter() - started,
        )

    def learning_artifacts(self) -> IntegratedLearningArtifacts:
        """Return detached truth-free frames; evaluator labels remain outside the stack."""

        return IntegratedLearningArtifacts(
            d3_planning_frames=tuple(self._d3_learning_frames),
            d4_region_frames=tuple(self._d4_learning_frames),
            d5_graph_frames=tuple(self._d5_learning_frames),
            d5_active_vision_frames=tuple(
                self._d5_active_vision_learning_frames
            ),
        )

    def d1_consistency_evidence_records(self) -> tuple[Any, ...]:
        """Return the final truth-free D1 evidence snapshot for offline scoring."""

        if self.d1 is None:
            return ()
        return tuple(self.d1.consistency_evidence_records())

    def _run_active_vision(
        self,
        step_input: RuntimeStepInput,
        now: float,
    ) -> tuple[CameraObservationCommand, ...]:
        """Build a truth-free D5 snapshot and emit bounded camera-only commands."""

        if self.d5_active_vision is None or self.latest_plan is None:
            return ()
        self._active_vision_communication_version += 1
        plan_version = int(self.latest_plan.version)
        coalition_version = max(
            (
                int(assignment.coalition_version or 0)
                for assignment in self.latest_plan.assignments
            ),
            default=0,
        )
        track_by_id = {
            track.global_track_id: track for track in self.latest_d2_tracks
        }
        camera_by_resource = {
            camera.resource_id: camera for camera in step_input.cameras
        }
        assignments = tuple(
            ActiveVisionAssignmentReference(
                resource_id=assignment.resource_id,
                camera_id=camera_by_resource[assignment.resource_id].camera_id,
                global_track_id=assignment.target_id,
            )
            for assignment in self.latest_plan.assignments
            if assignment.resource_id in camera_by_resource
            and assignment.target_id in track_by_id
        )
        tracks = tuple(
            ActiveVisionTrackReference(
                global_track_id=track.global_track_id,
                track_version=max(0, int(track.age)),
                measurement_timestamp=min(now, float(track.timestamp)),
            )
            for track in sorted(
                self.latest_d2_tracks,
                key=lambda item: item.global_track_id,
            )
        )
        cameras = tuple(
            self._active_vision_camera_state(camera)
            for camera in sorted(step_input.cameras, key=lambda item: item.camera_id)
        )
        projections = tuple(
            self._active_vision_projection(
                assignment,
                camera_by_resource[assignment.resource_id],
                track_by_id[assignment.target_id],
                step_input,
                now,
            )
            for assignment in self.latest_plan.assignments
            if assignment.resource_id in camera_by_resource
            and assignment.target_id in track_by_id
        )
        snapshot = ActiveVisionSnapshotV1(
            snapshot_timestamp=now,
            plan=ActiveVisionPlanReference(
                plan_version=plan_version,
                coalition_version=coalition_version,
                assignments=assignments,
            ),
            communication=ActiveVisionCommunicationState(
                communication_version=self._active_vision_communication_version,
                plan_version=plan_version,
                coalition_version=coalition_version,
                update_timestamp=now,
                healthy=not bool(
                    getattr(self.latest_d4_decision, "fail_closed", False)
                ),
            ),
            tracks=tracks,
            cameras=cameras,
            projections=projections,
        )
        decisions = tuple(
            self.d5_active_vision.decide(
                snapshot,
                camera_id=camera.camera_id,
                current_timestamp=now,
                expected_plan_version=plan_version,
                expected_coalition_version=coalition_version,
                expected_communication_version=(
                    self._active_vision_communication_version
                ),
                requested_mode=self.stack_config.d5_active_vision_mode,
            )
            for camera in cameras
        )
        commands = tuple(
            self._active_vision_command(
                decision,
                runtime_camera=next(
                    item
                    for item in step_input.cameras
                    if item.camera_id == decision.effective_action.camera_id
                ),
                step_input=step_input,
            )
            for decision in decisions
        )
        self.latest_active_vision_snapshot = snapshot
        self.latest_active_vision_decisions = decisions
        if self.stack_config.capture_learning_artifacts:
            self._d5_active_vision_learning_frames.append(
                D5ActiveVisionLearningFrame(
                    frame_index=len(self._d5_active_vision_learning_frames),
                    timestamp_s=now,
                    snapshot=snapshot,
                    decisions=decisions,
                    camera_feedback=tuple(
                        ActiveVisionCameraFeedbackV1(camera_state=camera)
                        for camera in cameras
                    ),
                )
            )
        return commands

    def _active_vision_camera_state(
        self,
        camera: CameraRuntimeState,
    ) -> ActiveVisionCameraState:
        config = self._require_ready()
        wide_fov = (
            config.camera_horizontal_fov_deg
            if camera.platform_kind == "interceptor"
            else config.recon_camera_horizontal_fov_deg
        )
        zoom_fov = min(
            float(self.stack_config.d5_active_vision_zoom_fov_deg),
            float(wide_fov) * 0.75,
        )
        return ActiveVisionCameraState(
            camera_id=camera.camera_id,
            resource_id=camera.resource_id,
            state_timestamp=camera.timestamp,
            yaw_deg=camera.yaw_deg,
            pitch_deg=camera.pitch_deg,
            yaw_rate_deg_s=0.0,
            pitch_rate_deg_s=0.0,
            yaw_limits_deg=(-180.0, 180.0),
            pitch_limits_deg=(-89.9, 89.9),
            max_yaw_rate_deg_s=60.0,
            max_pitch_rate_deg_s=60.0,
            max_slew_deg_s=80.0,
            current_fov_mode=ActiveVisionFovMode(camera.fov_mode),
            wide_horizontal_fov_deg=float(wide_fov),
            zoom_horizontal_fov_deg=float(zoom_fov),
        )

    def _active_vision_projection(
        self,
        assignment: Any,
        camera: CameraRuntimeState,
        track: Any,
        step_input: RuntimeStepInput,
        now: float,
    ) -> ActiveVisionProjectionEvidence:
        camera_position = _active_camera_position(camera, step_input)
        predicted_position, predicted_covariance = _predict_track_position(
            track,
            now,
        )
        relative = predicted_position - camera_position
        target_yaw, target_pitch = _yaw_pitch_from_ned(relative)
        yaw_error = _wrap_degrees(target_yaw - camera.yaw_deg)
        pitch_error = float(target_pitch - camera.pitch_deg)
        angular_covariance = _angular_covariance_deg2(
            relative,
            predicted_covariance,
            attitude_std_deg=(0.08 if camera.platform_kind == "interceptor" else 0.04),
        )
        vertical_fov = _vertical_fov_deg(
            camera.horizontal_fov_deg,
            platform_kind=camera.platform_kind,
            config=self._require_ready(),
        )
        in_fov = bool(
            abs(yaw_error) <= 0.5 * camera.horizontal_fov_deg
            and abs(pitch_error) <= 0.5 * vertical_fov
            and relative.dot(relative) > 1.0e-9
        )
        terminal = self._latest_terminal_by_pair.get(
            (assignment.resource_id, assignment.target_id)
        )
        if terminal is None:
            association_confidence = float(
                np.clip(
                    float(track.track_quality)
                    * (1.0 - float(track.association_risk)),
                    0.0,
                    1.0,
                )
            )
        else:
            association_confidence = float(
                np.clip(terminal[0]["association_confidence"], 0.0, 1.0)
            )
        visibility_probability = float(
            np.clip(
                (0.35 + 0.65 * float(track.track_quality))
                * (1.0 if in_fov else 0.15),
                0.0,
                1.0,
            )
        )
        return ActiveVisionProjectionEvidence(
            camera_id=camera.camera_id,
            global_track_id=assignment.target_id,
            measurement_timestamp=min(now, float(track.timestamp)),
            arrival_timestamp=now,
            yaw_error_deg=yaw_error,
            pitch_error_deg=pitch_error,
            projection_covariance_deg2=tuple(
                float(value) for value in angular_covariance.reshape(-1)
            ),
            visibility_probability=visibility_probability,
            occlusion_fraction=0.0,
            association_confidence=association_confidence,
            in_fov=in_fov,
        )

    def _active_vision_command(
        self,
        decision: Any,
        *,
        runtime_camera: CameraRuntimeState,
        step_input: RuntimeStepInput,
    ) -> CameraObservationCommand:
        action = decision.effective_action
        yaw = _wrap_degrees(runtime_camera.yaw_deg + action.yaw_delta_deg)
        pitch = float(
            np.clip(
                runtime_camera.pitch_deg + action.pitch_delta_deg,
                -89.9,
                89.9,
            )
        )
        position = _active_camera_position(runtime_camera, step_input)
        aim_point = position + _direction_from_yaw_pitch(yaw, pitch) * 1_000.0
        config = self._require_ready()
        wide_fov = (
            config.camera_horizontal_fov_deg
            if runtime_camera.platform_kind == "interceptor"
            else config.recon_camera_horizontal_fov_deg
        )
        horizontal_fov = (
            float(wide_fov)
            if action.fov_mode is ActiveVisionFovMode.WIDE
            else min(
                float(self.stack_config.d5_active_vision_zoom_fov_deg),
                float(wide_fov) * 0.75,
            )
        )
        reason = action.reason
        if decision.fallback_reason is not None:
            reason = f"{reason}|fallback={decision.fallback_reason}"
        return CameraObservationCommand(
            camera_id=action.camera_id,
            resource_id=runtime_camera.resource_id,
            issued_timestamp=action.issued_timestamp,
            expires_timestamp=action.expires_timestamp,
            plan_version=action.plan_version,
            coalition_version=action.coalition_version,
            communication_version=action.communication_version,
            intent=action.intent.value,
            aim_point_ned=aim_point,
            horizontal_fov_deg=horizontal_fov,
            fov_mode=action.fov_mode.value,
            target_global_track_id=action.target_global_track_id,
            requested_mode=decision.requested_mode.value,
            effective_mode=decision.effective_mode.value,
            reason=reason,
        )

    def _d4_region_resource_snapshot(
        self,
        step_input: RuntimeStepInput,
        *,
        formal_snapshot: RegionalFailoverSnapshot,
        now: float,
    ) -> RegionResourceSnapshot:
        """Aggregate online estimates into a truth-free regional graph."""

        config = self._require_ready()
        region_ids = tuple(item.region_id for item in formal_snapshot.regions)
        tasks_by_region: dict[str, list[RegionalTaskEvidence]] = {
            region_id: [] for region_id in region_ids
        }
        for task in formal_snapshot.tasks:
            tasks_by_region.setdefault(task.region_id, []).append(task)

        assigned_region_by_resource: dict[str, str] = {}
        for task in formal_snapshot.tasks:
            for resource_id in task.d3_assigned_member_ids:
                assigned_region_by_resource.setdefault(resource_id, task.region_id)
        active_resources_by_region = {region_id: 0 for region_id in region_ids}
        for index, resource_id in enumerate(step_input.interceptors.platform_ids):
            if not bool(step_input.interceptors.active[index]):
                continue
            region_id = assigned_region_by_resource.get(
                resource_id,
                _region_for_position(
                    step_input.interceptors.state_ned[index, :3],
                    config.region_count,
                ),
            )
            if region_id in active_resources_by_region:
                active_resources_by_region[region_id] += 1

        decision_by_region = {
            item.region_id: item for item in self.latest_d4_decision.region_decisions
        }
        region_signals: dict[str, dict[str, Any]] = {}
        for region_id in region_ids:
            tasks = tasks_by_region.get(region_id, [])
            decision = decision_by_region[region_id]
            committed_ids = {
                resource_id
                for task in tasks
                for resource_id in task.d3_assigned_member_ids
            }
            available = max(
                active_resources_by_region.get(region_id, 0),
                len(committed_ids),
            )
            reserve = min(
                max(0, available - len(committed_ids)),
                int(math.ceil(0.10 * available)),
            )
            applicable = [
                task
                for task in tasks
                if task.d5_consistency != D5Consistency.NOT_APPLICABLE
            ]
            required_visual = sum(task.required_member_count for task in applicable)
            supported_visual = sum(len(task.d5_support_member_ids) for task in applicable)
            d5_visibility = (
                1.0
                if required_visual == 0
                else min(1.0, supported_visual / required_visual)
            )
            consistency_score = {
                D5Consistency.CONSISTENT: 1.0,
                D5Consistency.UNKNOWN: 0.5,
                D5Consistency.INCONSISTENT: 0.0,
                D5Consistency.NOT_APPLICABLE: 1.0,
            }
            d5_consistency = (
                1.0
                if not applicable
                else float(
                    np.mean(
                        [consistency_score[task.d5_consistency] for task in applicable]
                    )
                )
            )
            readiness_records = tuple(decision.secondary_readiness.values())
            secondary_coverage = max(
                (float(item.get("coverage_ratio", 0.0)) for item in readiness_records),
                default=0.0,
            )
            secondary_readiness = max(
                (float(bool(item.get("ready", False))) for item in readiness_records),
                default=0.0,
            )
            unresolved_demand = sum(
                max(0, task.required_member_count - len(task.d3_assigned_member_ids))
                + int(not task.d3_resource_feasible)
                for task in tasks
            )
            region_signals[region_id] = {
                "target_demand": float(
                    sum(task.required_member_count for task in tasks)
                ),
                "high_threat_backlog": float(unresolved_demand),
                "d1_uncertainty": float(
                    np.mean([task.d1_covariance_trace for task in tasks])
                    if tasks
                    else 0.0
                ),
                "d2_uncertainty": float(
                    np.mean([task.d2_ambiguity_score for task in tasks])
                    if tasks
                    else 0.0
                ),
                "d5_visibility": d5_visibility,
                "d5_consistency": d5_consistency,
                "available_resources": available,
                "reserve_resources": reserve,
                "secondary_coverage": secondary_coverage,
                "secondary_readiness": secondary_readiness,
                "communication_capacity": (
                    config.communication_bandwidth_bytes_per_s * 8.0 / 1_000_000.0
                    if config.communication_enabled
                    else 0.0
                ),
                "communication_latency_s": config.communication_latency_s,
                "packet_loss_rate": config.communication_drop_probability,
                "committed_resources": len(committed_ids),
                "coalition_ack_complete": all(
                    (not commit.commit_required) or commit.execution_authorized
                    for commit in decision.coalition_commits
                ),
                "fault_fenced": bool(
                    decision.fail_closed or not decision.execution_allowed
                ),
                "fault_fence_epoch": (
                    int(formal_snapshot.epoch)
                    if decision.fail_closed or not decision.execution_allowed
                    else None
                ),
                "assignment_conflict_count": sum(
                    "conflict" in str(reason)
                    for reason in decision.risk_factors
                ),
                "degradation_failed": bool(decision.fail_closed),
            }

        edges = self._d4_region_resource_edges(
            region_ids,
            region_signals,
        )
        return RegionResourceSnapshot.from_regional_decision(
            self.latest_d4_decision,
            snapshot_id=(
                f"{config.scenario_name}-s{config.seed}-"
                f"p{formal_snapshot.plan_version}-t{now:.6f}"
            ),
            scenario_id=config.scenario_name,
            scenario_version=config.scenario_version,
            seed=config.seed,
            region_signals=region_signals,
            edges=edges,
        )

    def _d4_region_resource_edges(
        self,
        region_ids: tuple[str, ...],
        region_signals: Mapping[str, Mapping[str, Any]],
    ) -> tuple[RegionResourceEdge, ...]:
        config = self._require_ready()
        if len(region_ids) <= 1:
            return ()
        arc_distance = 2.0 * math.pi * config.protected_radius_m / len(region_ids)
        transfer_time = arc_distance / config.interceptor_speed_mps
        bandwidth_mbps = (
            config.communication_bandwidth_bytes_per_s * 8.0 / 1_000_000.0
            if config.communication_enabled
            else 0.0
        )
        directed_pairs: set[tuple[str, str]] = set()
        for index, source in enumerate(region_ids):
            directed_pairs.add((source, region_ids[(index + 1) % len(region_ids)]))
            directed_pairs.add((source, region_ids[(index - 1) % len(region_ids)]))
        edges: list[RegionResourceEdge] = []
        for source, target in sorted(directed_pairs):
            signal = region_signals[source]
            transferable = max(
                0,
                int(signal["available_resources"])
                - int(signal["reserve_resources"])
                - int(signal["committed_resources"]),
            )
            edges.append(
                RegionResourceEdge(
                    source_region_id=source,
                    target_region_id=target,
                    transferable_resources=transferable,
                    distance_m=arc_distance,
                    transfer_time_s=transfer_time,
                    bandwidth_mbps=bandwidth_mbps,
                    communication_available=config.communication_enabled,
                    maneuver_available=True,
                    partitioned=(
                        not config.communication_enabled
                        or config.communication_drop_probability >= 1.0
                    ),
                    bidirectional=False,
                )
            )
        return tuple(edges)

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

    def _has_fallback_authority_decision(self) -> bool:
        if self.latest_d4_decision is None:
            return False
        fallback_layers = {
            RegionalAuthorityLayer.SECONDARY,
            RegionalAuthorityLayer.DISTRIBUTED,
        }
        return any(
            decision.task_ids and decision.selected_layer in fallback_layers
            for decision in self.latest_d4_decision.region_decisions
        )

    def _regional_authority_from_d4(
        self,
        previous_plan: Any,
        *,
        target_ids: set[str],
        now: float,
    ) -> RegionalAuthorityInput:
        """Translate one complete D4 frame into D3-owned authority DTOs.

        The adapter never invents an owner, membership, epoch, lease or global
        track identity.  Missing coverage and inconsistent source generations
        are rejected before D3 is called.
        """

        frame = self.latest_d4_decision
        if frame is None:
            raise RegionalPlanAuthorityError("regional_d4_decision_missing")
        if float(frame.timestamp_s) > float(now) + _EPS:
            raise RegionalPlanAuthorityError("regional_d4_decision_from_future")

        assignments_by_target = previous_plan.assignments_by_target()
        coalition_by_target = {
            coalition.target_id: coalition for coalition in previous_plan.coalitions
        }
        task_to_target = {
            f"task:{target_id}": target_id for target_id in sorted(target_ids)
        }
        covered_targets: set[str] = set()
        grants: list[RegionalAuthorityGrant] = []
        fallback_layers = {
            RegionalAuthorityLayer.SECONDARY,
            RegionalAuthorityLayer.DISTRIBUTED,
        }

        for decision in frame.region_decisions:
            regional_task_ids = tuple(
                task_id for task_id in decision.task_ids if task_id in task_to_target
            )
            if not regional_task_ids:
                continue
            if len(regional_task_ids) != len(decision.task_ids):
                raise RegionalPlanAuthorityError("regional_d4_unknown_task_id")
            if decision.selected_layer not in fallback_layers:
                raise RegionalPlanAuthorityError("regional_d4_target_not_fallback_owned")
            ownership = decision.ownership
            if (
                not decision.execution_allowed
                or decision.fail_closed
                or not ownership.active
            ):
                raise RegionalPlanAuthorityError("regional_d4_execution_not_allowed")
            if (
                ownership.owner_layer is not decision.selected_layer
                or not ownership.owner_id
                or not ownership.owner_role
            ):
                raise RegionalPlanAuthorityError("regional_d4_owner_contract_mismatch")
            if (
                ownership.plan_id != previous_plan.plan_id
                or ownership.plan_version != previous_plan.version
            ):
                raise RegionalPlanAuthorityError("regional_d4_stale_source_plan")
            if set(ownership.task_ids) != set(decision.task_ids):
                raise RegionalPlanAuthorityError("regional_d4_owner_task_set_mismatch")
            if float(now) >= float(ownership.lease_expires_at_s):
                raise RegionalPlanAuthorityError("regional_d4_authority_lease_expired")

            commit_by_target = {
                commit.global_track_id: commit
                for commit in decision.coalition_commits
            }
            grant_targets: list[str] = []
            assigned_by_target: dict[str, tuple[str, ...]] = {}
            commit_evidence: list[RegionalCoalitionCommitEvidence] = []
            grant_lease = float(ownership.lease_expires_at_s)

            for task_id in regional_task_ids:
                target_id = task_to_target[task_id]
                if target_id in covered_targets:
                    raise RegionalPlanAuthorityError(
                        "regional_d4_duplicate_target_authority"
                    )
                previous_assignments = assignments_by_target.get(target_id, ())
                if not previous_assignments:
                    raise RegionalPlanAuthorityError(
                        "regional_d4_target_assignment_missing"
                    )
                assigned_resource_ids = tuple(
                    decision.fallback_assignments.get(task_id, ())
                )
                required_count = int(
                    previous_assignments[0].required_resource_count
                )
                if len(assigned_resource_ids) != required_count:
                    raise RegionalPlanAuthorityError(
                        "regional_d4_required_member_count_unsatisfied"
                    )
                commit = commit_by_target.get(target_id)
                if commit is None:
                    raise RegionalPlanAuthorityError(
                        "regional_d4_commit_evidence_missing"
                    )
                if bool(commit.commit_required) != (required_count > 1):
                    raise RegionalPlanAuthorityError(
                        "regional_d4_commit_requirement_mismatch"
                    )
                if set(commit.required_member_ids) != set(assigned_resource_ids):
                    raise RegionalPlanAuthorityError(
                        "regional_d4_commit_membership_mismatch"
                    )

                coalition_id: str | None = None
                coalition_version: int | None = None
                if required_count > 1:
                    coalition = coalition_by_target.get(target_id)
                    previous_member_ids = {
                        assignment.resource_id for assignment in previous_assignments
                    }
                    if coalition is None or previous_member_ids != set(
                        assigned_resource_ids
                    ):
                        raise RegionalPlanAuthorityError(
                            "regional_coalition_version_transition_unadjudicated"
                        )
                    coalition_id = coalition.coalition_id
                    coalition_version = coalition.version

                evidence_lease = min(
                    float(commit.lease_expires_at_s),
                    float(ownership.lease_expires_at_s),
                )
                grant_lease = min(grant_lease, evidence_lease)
                commit_evidence.append(
                    RegionalCoalitionCommitEvidence(
                        target_id=target_id,
                        coordinator_id=commit.coordinator_id,
                        epoch=int(ownership.epoch),
                        lease_expires_at_s=evidence_lease,
                        required_member_ids=tuple(commit.required_member_ids),
                        acked_member_ids=tuple(commit.acked_member_ids),
                        commit_required=bool(commit.commit_required),
                        state=commit.state,
                        atomic_committed=bool(commit.atomic_committed),
                        execution_authorized=bool(commit.execution_authorized),
                        coalition_id=coalition_id,
                        coalition_version=coalition_version,
                        metadata={
                            "d4_reason": commit.reason,
                            "formation_algorithm": commit.formation_algorithm,
                            "rejected_ack_reasons": tuple(
                                commit.rejected_ack_reasons
                            ),
                        },
                    )
                )
                grant_targets.append(target_id)
                assigned_by_target[target_id] = assigned_resource_ids
                covered_targets.add(target_id)

            grants.append(
                RegionalAuthorityGrant(
                    region_id=decision.region_id,
                    owner_layer=decision.selected_layer.value,
                    owner_node_id=str(ownership.owner_id),
                    owner_role=str(ownership.owner_role),
                    epoch=int(ownership.epoch),
                    source_plan_id=previous_plan.plan_id,
                    source_plan_version=previous_plan.version,
                    lease_expires_at_s=grant_lease,
                    target_ids=tuple(grant_targets),
                    assigned_resource_ids_by_target=assigned_by_target,
                    execution_allowed=True,
                    fail_closed=False,
                    coalition_commits=tuple(commit_evidence),
                    decision_reason=decision.reason,
                    metadata={
                        "d4_schema": frame.schema,
                        "d4_action": decision.action.value,
                        "d4_adjudicated_at_s": float(frame.timestamp_s),
                    },
                )
            )

        if covered_targets != target_ids:
            raise RegionalPlanAuthorityError("regional_d4_target_set_incomplete")
        return RegionalAuthorityInput(
            adjudicated_at_s=float(frame.timestamp_s),
            grants=tuple(grants),
        )

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
        snapshot_epoch = self._plan_authority_epoch(plan)
        if self._fault_generation_changed:
            # A new failure generation must advance the fencing epoch before D4
            # can move authority to a different layer or owner.
            snapshot_epoch = max(snapshot_epoch, int(plan.version))
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
                    d3_epoch=snapshot_epoch,
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
                    )
                    and self._regional_plan_rejection_reason is None,
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
            epoch=snapshot_epoch,
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
            epoch=snapshot_epoch,
            lease_expires_at_s=lease_expires_at,
            regions=regions,
            tasks=tuple(tasks),
            secondary_nodes=secondaries,
            fallback_members=members,
            coalition_acks=acks,
        )

    @staticmethod
    def _plan_authority_epoch(plan: Any) -> int:
        metadata = dict(plan.metadata)
        for key in ("regional_max_epoch", "secondary_leader_epoch"):
            value = metadata.get(key)
            if value is not None:
                return int(value)
        return int(plan.version)

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
        assignment = next(
            (
                item
                for item in self.latest_plan.assignments
                if item.target_id == target_id
            ),
            None,
        )
        if assignment is None:
            return D4GuidancePermission(
                action="hold_for_review",
                reason="d3_target_assignment_missing",
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
        required_count = int(assignment.required_resource_count)
        commit_required = required_count > 1
        if commit_required and (
            task_commit is None
            or not task_commit.commit_required
            or not task_commit.execution_authorized
        ):
            return D4GuidancePermission(
                action="hold_for_review",
                mode=decision.selected_layer.value,
                reason="d4_atomic_coalition_commit_missing",
                requires_human_review=True,
            )

        if decision.selected_layer in {
            RegionalAuthorityLayer.SECONDARY,
            RegionalAuthorityLayer.DISTRIBUTED,
        }:
            mismatch = self._fallback_plan_mismatch_reason(
                assignment,
                decision,
                region_id=str(region_id),
            )
            if mismatch:
                return D4GuidancePermission(
                    action="hold_for_review",
                    mode=decision.selected_layer.value,
                    reason=mismatch,
                    requires_human_review=True,
                )
            commit_fields = self._guidance_commit_fields(
                target_id,
                task_commit,
                commit_required=commit_required,
                assignment=assignment,
            )
            return D4GuidancePermission(
                action="continue",
                mode=decision.selected_layer.value,
                reason=decision.reason,
                target_node_id=str(decision.ownership.owner_id),
                terminal_consistent=True,
                new_plan_id=self.latest_plan.plan_id,
                new_plan_version=self.latest_plan.version,
                secondary_capability_class=(
                    "mobile_high_recon"
                    if decision.selected_layer is RegionalAuthorityLayer.SECONDARY
                    else None
                ),
                secondary_readiness_class=(
                    "takeover_ready"
                    if decision.selected_layer is RegionalAuthorityLayer.SECONDARY
                    else None
                ),
                visual_png_allowed=True,
                center_available=False,
                metadata={
                    "required_resource_count": required_count,
                    "commit_required": commit_required,
                    "regional_region_id": region_id,
                    "regional_owner_layer": decision.selected_layer.value,
                    "regional_owner_node_id": decision.ownership.owner_id,
                    "regional_epoch": decision.ownership.epoch,
                },
                **commit_fields,
            )

        if decision.selected_layer is not RegionalAuthorityLayer.CENTER:
            return D4GuidancePermission(
                action="hold_for_review",
                mode=decision.selected_layer.value,
                reason="d4_region_not_executable",
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
        commit_fields = self._guidance_commit_fields(
            target_id,
            task_commit,
            commit_required=commit_required,
            assignment=assignment,
        )
        return D4GuidancePermission(
            action=action,
            reason=decision.reason,
            terminal_consistent=True,
            new_plan_id=self.latest_plan.plan_id,
            new_plan_version=self.latest_plan.version,
            visual_png_allowed=True,
            center_available=True,
            metadata={
                "required_resource_count": required_count,
                "commit_required": commit_required,
            },
            **commit_fields,
        )

    def _fallback_plan_mismatch_reason(
        self,
        assignment: Any,
        decision: Any,
        *,
        region_id: str,
    ) -> str:
        plan = self.latest_plan
        ownership = decision.ownership
        if (
            ownership.plan_id != plan.plan_id
            or ownership.plan_version != plan.version
        ):
            return "regional_d4_plan_version_mismatch"
        plan_owner = str(plan.metadata.get("active_plan_owner", "center"))
        assignment_metadata = dict(assignment.metadata)
        if plan_owner == "regional":
            if (
                str(assignment_metadata.get("regional_owner_layer", ""))
                != decision.selected_layer.value
            ):
                return "regional_owner_layer_mismatch"
            if str(assignment_metadata.get("regional_region_id", "")) != region_id:
                return "regional_owner_region_mismatch"
            owner_node_id = str(assignment_metadata.get("owner_node_id", ""))
            if owner_node_id != str(ownership.owner_id):
                return "regional_owner_node_mismatch"
            if int(assignment_metadata.get("regional_epoch", -1)) != int(
                ownership.epoch
            ):
                return "regional_owner_epoch_mismatch"
            lease = float(
                assignment_metadata.get("regional_lease_expires_at_s", -math.inf)
            )
        elif (
            plan_owner == "secondary"
            and decision.selected_layer is RegionalAuthorityLayer.SECONDARY
        ):
            owner_node_id = str(plan.metadata.get("owner_node_id", ""))
            if owner_node_id != str(ownership.owner_id):
                return "secondary_owner_plan_mismatch"
            if int(plan.metadata.get("secondary_leader_epoch", -1)) != int(
                ownership.epoch
            ):
                return "secondary_owner_epoch_mismatch"
            lease = float(
                plan.metadata.get("secondary_lease_expires_at_s", -math.inf)
            )
        else:
            return "fallback_plan_not_yet_reissued_by_d3"
        if float(self.latest_d4_decision.timestamp_s) >= lease:
            return "regional_plan_lease_expired"
        if float(self.latest_d4_decision.timestamp_s) >= float(
            ownership.lease_expires_at_s
        ):
            return "regional_d4_lease_expired"
        return ""

    def _guidance_commit_fields(
        self,
        target_id: str,
        task_commit: Any | None,
        *,
        commit_required: bool,
        assignment: Any,
    ) -> dict[str, Any]:
        coalition_id = _coalition_id_for(self.latest_plan, target_id)
        coalition_version = _coalition_version_for(self.latest_plan, target_id)
        coalition_epoch = _coalition_epoch_for(self.latest_plan, target_id)
        if task_commit is None:
            return {
                "coalition_id": coalition_id,
                "coalition_version": coalition_version,
                "atomic_coalition_formed": None,
                "coalition_commit_state": None,
                "coalition_epoch": coalition_epoch,
            }
        lease_values = [float(task_commit.lease_expires_at_s)]
        assignment_lease = assignment.metadata.get("regional_lease_expires_at_s")
        if assignment_lease is not None:
            lease_values.append(float(assignment_lease))
        secondary_lease = self.latest_plan.metadata.get(
            "secondary_lease_expires_at_s"
        )
        if secondary_lease is not None:
            lease_values.append(float(secondary_lease))
        effective_lease = min(lease_values)
        return {
            "coalition_id": coalition_id,
            "coalition_version": coalition_version,
            "atomic_coalition_formed": (
                bool(task_commit.atomic_committed) if commit_required else None
            ),
            "coalition_commit_state": task_commit.state,
            "coalition_epoch": coalition_epoch,
            "coalition_lease_expires_at_s": effective_lease,
            "coalition_required_member_ids": tuple(
                task_commit.required_member_ids
            ),
            "coalition_acked_member_ids": tuple(task_commit.acked_member_ids),
            "commit_plan_id": self.latest_plan.plan_id,
            "commit_plan_version": self.latest_plan.version,
            "commit_coalition_id": coalition_id,
            "commit_coalition_version": coalition_version,
        }

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
        evidence_by_observation = {
            item.observation_id: item
            for item in self.d1.consistency_evidence_records()
        }
        observation_timestamps = {
            str(measurement.observation_id): float(
                measurement.measurement_timestamp
            )
            for measurement in batch.measurements
        }
        for track in result.tracks:
            metadata = getattr(track, "metadata", {})
            observation_id = str(
                metadata.get("latest_observation_id", "")
                if isinstance(metadata, Mapping)
                else ""
            ).strip()
            if not observation_id or observation_id in observation_timestamps:
                continue
            evidence = evidence_by_observation.get(observation_id)
            observation_timestamps[observation_id] = float(
                getattr(track, "timestamp", now)
                if evidence is None
                else evidence.measurement_timestamp
            )

        observation_lineage = []
        for observation_id, measurement_timestamp in observation_timestamps.items():
            evidence = evidence_by_observation.get(observation_id)
            lineage = (
                (observation_id,)
                if evidence is None
                else _lineage_ending_in_observation(
                    evidence.source_lineage,
                    observation_id,
                )
            )
            replay_generation = (
                self._d2_observation_replay_generation.get(
                    observation_id,
                    -1,
                )
                + 1
            )
            lineage_record = {
                "observation_id": observation_id,
                "measurement_timestamp": float(measurement_timestamp),
                "source_lineage": list(lineage),
                "replay_generation": replay_generation,
            }
            observation_lineage.append(lineage_record)
            self._d1_latest_lineage_by_observation[observation_id] = dict(
                lineage_record
            )
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
                "observation_lineage": observation_lineage,
            },
            copy_payload=False,
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
                "identity_lineage": self._d2_identity_lineage_payload(result),
                "identity_lineage_policy": (
                    "d2_center_track_to_d1_source_observation_v1"
                ),
            },
            copy_payload=False,
        )

    def _update_d2_identity_lineage(
        self,
        result: Any,
        detections: list[Any],
    ) -> None:
        """Retain truth-free D1 observation lineage for each D2-owned track."""

        self._d2_identity_lineage_by_track.clear()
        detection_by_id = {item.detection_id: item for item in detections}
        for detection_id, global_track_id in dict(
            result.metadata.get("detection_to_track", {})
        ).items():
            detection = detection_by_id.get(str(detection_id))
            if detection is None:
                continue
            observation_id = str(
                detection.metadata.get("latest_observation_id", "")
            ).strip()
            if not observation_id:
                continue
            lineage_record = self._d1_latest_lineage_by_observation.get(
                observation_id
            )
            if lineage_record is None:
                continue
            self._d2_observation_replay_generation[observation_id] = int(
                lineage_record["replay_generation"]
            )
            self._d2_identity_lineage_by_track[str(global_track_id)] = (
                dict(lineage_record),
            )

    def _d2_identity_lineage_payload(self, result: Any) -> list[dict[str, Any]]:
        detection_to_track = dict(result.metadata.get("detection_to_track", {}))
        created = set(result.metadata.get("created_track_ids_by_detection", {}).values())
        updated_track_ids = set(str(item) for item in detection_to_track.values())
        payload = []
        for track in self.latest_d2_tracks:
            global_track_id = str(track.global_track_id)
            lifecycle_state = _enum_value(track.lifecycle_state)
            if global_track_id in created:
                association_state = "created"
            elif global_track_id in updated_track_ids:
                association_state = "matched"
            elif lifecycle_state == "lost":
                association_state = "lost"
            elif lifecycle_state == "dropped":
                association_state = "dropped"
            else:
                association_state = "unmatched"
            payload.append(
                {
                    "global_track_id": global_track_id,
                    "lifecycle_state": lifecycle_state,
                    "association_state": association_state,
                    "source_observations": [
                        dict(item)
                        for item in self._d2_identity_lineage_by_track.get(
                            global_track_id,
                            (),
                        )
                    ],
                }
            )
        return payload

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
                        "owner_node_id": item.metadata.get("owner_node_id"),
                        "regional_owner_layer": item.metadata.get(
                            "regional_owner_layer"
                        ),
                        "regional_region_id": item.metadata.get(
                            "regional_region_id"
                        ),
                        "regional_epoch": item.metadata.get("regional_epoch"),
                        "regional_commit_mode": item.metadata.get(
                            "regional_commit_mode"
                        ),
                    }
                    for item in plan.assignments
                ],
                "unassigned_global_track_ids": list(plan.unassigned_target_ids),
                "solver_name": plan.solver_name,
                "metadata": dict(plan.metadata),
            },
            copy_payload=False,
        )

    def _d4_publication(self, now: float) -> RuntimePublication:
        return RuntimePublication(
            topic="modules.d4.regional_failover",
            source="D4",
            schema_version="d4-regional-failover-v1",
            payload=self.latest_d4_decision.to_bus_payload(),
            copy_payload=False,
        )

    def _d4_region_advice_publication(self, now: float) -> RuntimePublication:
        return RuntimePublication(
            topic="modules.d4.region_resource_advice",
            source="D4",
            schema_version="d4-region-resource-advisory-runtime-v1",
            payload={
                "timestamp": now,
                **self.latest_d4_region_advice.to_dict(),
            },
            copy_payload=False,
        )

    def _d4_region_consumption_publication(
        self,
        now: float,
    ) -> RuntimePublication:
        consumption = self.latest_d4_region_consumption
        return RuntimePublication(
            topic="modules.d4.region_resource_consumption",
            source="main",
            schema_version=str(consumption.schema),
            payload={
                "timestamp": now,
                **consumption.to_dict(),
                "bridge_rejection_reason": (
                    self._d4_region_hint_bridge_rejection_reason
                ),
                "d3_hint_applied": bool(
                    self.latest_plan is not None
                    and self.latest_plan.metadata.get(
                        "regional_hint_applied",
                        False,
                    )
                ),
            },
            copy_payload=False,
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
                "diagnostics": dict(association.diagnostics),
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
            copy_payload=False,
        )

    def _d5_active_vision_publication(
        self,
        now: float,
        commands: tuple[CameraObservationCommand, ...],
    ) -> RuntimePublication:
        mode_counts = Counter(command.effective_mode for command in commands)
        intent_counts = Counter(command.intent for command in commands)
        return RuntimePublication(
            topic="modules.d5.active_vision",
            source="D5",
            schema_version="d5.active-vision-runtime.v1",
            payload={
                "timestamp": now,
                "command_count": len(commands),
                "effective_mode_counts": dict(sorted(mode_counts.items())),
                "intent_counts": dict(sorted(intent_counts.items())),
                "commands": [
                    {
                        "camera_id": command.camera_id,
                        "resource_id": command.resource_id,
                        "issued_timestamp": command.issued_timestamp,
                        "expires_timestamp": command.expires_timestamp,
                        "plan_version": command.plan_version,
                        "coalition_version": command.coalition_version,
                        "communication_version": command.communication_version,
                        "intent": command.intent,
                        "horizontal_fov_deg": command.horizontal_fov_deg,
                        "fov_mode": command.fov_mode,
                        "target_global_track_id": command.target_global_track_id,
                        "requested_mode": command.requested_mode,
                        "effective_mode": command.effective_mode,
                        "reason": command.reason,
                    }
                    for command in commands
                ],
            },
            copy_payload=False,
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
            copy_payload=False,
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
            "d5_active_vision_command_count": len(
                self.latest_active_vision_decisions
            ),
            "d5_active_vision_requested_mode": (
                self.stack_config.d5_active_vision_mode
            ),
            "d5_active_vision_effective_mode_counts": dict(
                sorted(
                    Counter(
                        decision.effective_mode.value
                        for decision in self.latest_active_vision_decisions
                    ).items()
                )
            ),
            "d5_active_vision_fallback_reason_counts": dict(
                sorted(
                    Counter(
                        decision.fallback_reason
                        for decision in self.latest_active_vision_decisions
                        if decision.fallback_reason is not None
                    ).items()
                )
            ),
            "d7_command_count": (
                0
                if self.latest_guidance_batch is None
                else len(self.latest_guidance_batch.pair_commands)
            ),
            "regional_plan_rejection_reason": (
                self._regional_plan_rejection_reason
            ),
            "d4_region_advice_available": self.latest_d4_region_advice is not None,
            "d4_region_advice_effective_mode": (
                None
                if self.latest_d4_region_advice is None
                else self.latest_d4_region_advice.effective_mode.value
            ),
            "d4_region_advice_fallback_reason": (
                None
                if self.latest_d4_region_advice is None
                else self.latest_d4_region_advice.fallback_reason
            ),
            "d4_region_consumption_available": (
                self.latest_d4_region_consumption is not None
            ),
            "d4_region_consumable": (
                None
                if self.latest_d4_region_consumption is None
                else bool(self.latest_d4_region_consumption.consumable)
            ),
            "d4_region_consumption_rejection_reasons": (
                ()
                if self.latest_d4_region_consumption is None
                else tuple(
                    self.latest_d4_region_consumption.rejection_reasons
                )
            ),
            "d4_region_hint_bridge_rejection_reason": (
                self._d4_region_hint_bridge_rejection_reason
            ),
            "d3_regional_hint_applied": bool(
                self.latest_plan is not None
                and self.latest_plan.metadata.get("regional_hint_applied", False)
            ),
            "learning_runtime": dict(self.learning_runtime_diagnostics),
            "online_truth_use_count": 0,
            "stage_timings": {
                stage: {
                    "call_count": self._stage_call_count[stage],
                    "wall_time_s": self._stage_wall_time_s[stage],
                    "mean_wall_time_ms": (
                        1_000.0
                        * self._stage_wall_time_s[stage]
                        / self._stage_call_count[stage]
                    ),
                }
                for stage in sorted(self._stage_wall_time_s)
            },
        }

    def _record_timing(self, stage: str, elapsed_s: float) -> None:
        self._stage_wall_time_s[stage] = (
            self._stage_wall_time_s.get(stage, 0.0) + float(elapsed_s)
        )
        self._stage_call_count[stage] = self._stage_call_count.get(stage, 0) + 1

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


def _active_camera_position(
    camera: CameraRuntimeState,
    step_input: RuntimeStepInput,
) -> np.ndarray:
    navigation = (
        step_input.interceptors
        if camera.platform_kind == "interceptor"
        else step_input.recon
    )
    try:
        index = navigation.platform_ids.index(camera.resource_id)
    except ValueError as exc:
        raise ValueError(
            f"active-vision camera resource is unavailable: {camera.resource_id}"
        ) from exc
    if not bool(navigation.active[index]):
        raise ValueError(
            f"active-vision camera resource is inactive: {camera.resource_id}"
        )
    return np.asarray(navigation.state_ned[index, :3], dtype=float)


def _predict_track_position(track: Any, now: float) -> tuple[np.ndarray, np.ndarray]:
    state = np.asarray(track.state, dtype=float).reshape(6)
    covariance = np.asarray(track.covariance, dtype=float).reshape(6, 6)
    dt = max(0.0, float(now) - float(track.timestamp))
    position = state[:3] + state[3:] * dt
    transition = np.eye(6, dtype=float)
    transition[:3, 3:] = np.eye(3, dtype=float) * dt
    propagated = transition @ covariance @ transition.T
    position_covariance = 0.5 * (
        propagated[:3, :3] + propagated[:3, :3].T
    )
    return position, position_covariance


def _yaw_pitch_from_ned(direction_ned: np.ndarray) -> tuple[float, float]:
    vector = np.asarray(direction_ned, dtype=float).reshape(3)
    horizontal = float(np.linalg.norm(vector[:2]))
    if not np.all(np.isfinite(vector)) or float(np.linalg.norm(vector)) < 1.0e-9:
        return 0.0, 0.0
    yaw = math.degrees(math.atan2(float(vector[1]), float(vector[0])))
    pitch = math.degrees(math.atan2(float(-vector[2]), max(horizontal, 1.0e-9)))
    return _wrap_degrees(yaw), float(np.clip(pitch, -89.9, 89.9))


def _direction_from_yaw_pitch(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    yaw = math.radians(float(yaw_deg))
    pitch = math.radians(float(pitch_deg))
    return np.array(
        [
            math.cos(pitch) * math.cos(yaw),
            math.cos(pitch) * math.sin(yaw),
            -math.sin(pitch),
        ],
        dtype=float,
    )


def _wrap_degrees(value: float) -> float:
    return float((float(value) + 180.0) % 360.0 - 180.0)


def _angular_covariance_deg2(
    relative_ned: np.ndarray,
    position_covariance_ned: np.ndarray,
    *,
    attitude_std_deg: float,
) -> np.ndarray:
    relative = np.asarray(relative_ned, dtype=float).reshape(3)
    covariance = np.asarray(position_covariance_ned, dtype=float).reshape(3, 3)
    north, east, down = (float(value) for value in relative)
    horizontal_squared = north * north + east * east
    range_squared = horizontal_squared + down * down
    if range_squared < 1.0e-8 or horizontal_squared < 1.0e-8:
        return np.eye(2, dtype=float) * 1.0e6
    horizontal = math.sqrt(horizontal_squared)
    jacobian = np.array(
        [
            [-east / horizontal_squared, north / horizontal_squared, 0.0],
            [
                down * north / (range_squared * horizontal),
                down * east / (range_squared * horizontal),
                -horizontal / range_squared,
            ],
        ],
        dtype=float,
    )
    radians_covariance = jacobian @ covariance @ jacobian.T
    degrees_covariance = radians_covariance * (180.0 / math.pi) ** 2
    degrees_covariance += np.eye(2, dtype=float) * float(attitude_std_deg) ** 2
    degrees_covariance = 0.5 * (degrees_covariance + degrees_covariance.T)
    minimum_eigenvalue = float(np.linalg.eigvalsh(degrees_covariance).min())
    if minimum_eigenvalue < 0.0:
        degrees_covariance += np.eye(2, dtype=float) * (-minimum_eigenvalue + 1.0e-9)
    return degrees_covariance


def _vertical_fov_deg(
    horizontal_fov_deg: float,
    *,
    platform_kind: str,
    config: ScenarioConfig,
) -> float:
    if platform_kind == "interceptor":
        width = config.camera_width_px
        height = config.camera_height_px
    else:
        width = config.recon_camera_width_px
        height = config.recon_camera_height_px
    horizontal = math.radians(float(horizontal_fov_deg))
    return math.degrees(
        2.0 * math.atan(math.tan(0.5 * horizontal) * float(height) / float(width))
    )


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


def _lineage_ending_in_observation(
    lineage: Any,
    observation_id: str,
) -> tuple[str, ...]:
    items = tuple(str(item) for item in lineage)
    if not items:
        return (str(observation_id),)
    if items[-1] == str(observation_id):
        return items
    return (*items, str(observation_id))


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


def _coalition_epoch_for(plan: Any, target_id: str) -> int | None:
    coalition = next(
        (item for item in plan.coalitions if item.target_id == target_id),
        None,
    )
    if coalition is None:
        return None
    return int(coalition.metadata.get("coalition_epoch", coalition.version))
