"""Main-owned AirSim episode bus for D1-D7 runtime records.

The bus is intentionally a coordinator layer. It runs existing module adapters
on already captured AirSim frames, preserves module ownership boundaries, and
writes D6-compatible records plus a per-frame debug snapshot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import json
import math
from pathlib import Path
import time
from typing import Any, Iterable, Mapping

import numpy as np

from airsim_dryrun.models import AirSimFrame
from d1_sensor_fusion import FusionAdapter, SensorObservation
from d2_data_association import GNNHungarianAssociator, Tracker
from d3_assignment_planner import (
    AssignmentPlan,
    AssignmentPlanner,
    CostModel,
    CostWeights,
    PlannerConfig,
    StalePlanError,
    apply_terminal_feedback_to_planner_inputs,
    guidance_bindings_from_assignment_plan,
    prepare_secondary_takeover_plan,
)
from d4_distributed_fallback import (
    ActiveDegradationArbiter,
    ActiveDegradationConfig,
    C2Health,
    D4ArbitrationAdapter,
)
from d5_terminal_association import (
    Assignment as TerminalAssignment,
    CameraModel,
    LocalVisualTrack,
    ReconImageCue,
    TerminalAssociator,
    TerminalAssociation,
    TerminalConsistencyTracker,
    TerminalObservationBus,
    annotate_visual_png_handoff,
    camera_model_from_airsim_camera_info,
)
from d6_evaluation_metrics import (
    AssignmentRecord,
    EventRecord,
    LinkRecord,
    MetricsCollector,
    TerminalRecord,
    TrackRecord,
)
from d7_proportional_guidance import (
    D4GuidancePermission,
    D7RuntimeBus,
    D7RuntimePairInput,
    GuidanceMode,
    GuidanceState,
    compute_pn_command,
    evaluate_terminal_png_contract,
    guidance_mode_from_terminal_contract,
    summarize_runtime_bus_outputs,
)
from integrated_simulation.adapters import (
    d1_tracks_to_d2_detections,
    d2_tracks_to_target_tracks,
    d2_tracks_to_terminal_tracks,
    plan_to_assignment_records,
    plan_to_terminal_assignments,
    resources_to_d3,
    resources_to_d4,
    terminal_to_record,
    track_records_from_d2,
)
from integrated_simulation.models import ResourcePlatform, TruthState

from .adapters import (
    geometric_local_visual_tracks_from_blocks_frame,
    observations_from_blocks_frame,
    offline_truth_map_from_blocks_frame,
    resources_from_blocks_frame,
    truth_states_from_blocks_frame,
)
from .models import BlocksSmokeConfig


STANDARD_MAPPING_VERSION = "cuas-standard-map-v1"


@dataclass(frozen=True)
class MainEpisodeBusTick:
    """One frame's main bus snapshot for interface debugging."""

    timestamp: float
    frame_index: int
    clock: dict[str, Any]
    module_health: dict[str, Any]
    d1: dict[str, Any]
    d2: dict[str, Any]
    d3: dict[str, Any]
    d4: dict[str, Any]
    d5: dict[str, Any]
    d7: dict[str, Any]
    record_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass(frozen=True)
class MainEpisodeBusResult:
    """Outputs written by the main runtime episode bus."""

    episode_id: str
    scenario_name: str
    frame_count: int
    metrics: dict[str, Any]
    summary: dict[str, Any]
    output_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class _TerminalDecisionContext:
    assignment: Any
    terminal_assignment: TerminalAssignment
    d2_track: Any | None
    terminal_association: TerminalAssociation
    terminal_record: TerminalRecord
    local_track: LocalVisualTrack | None
    observed_global_track_id: str | None
    consistency_summary: Any | None


class MainAirSimEpisodeBus:
    """Drive D1-D7 adapters from real AirSim frames under main control."""

    def __init__(self, config: BlocksSmokeConfig) -> None:
        self.config = config
        self.fusion = FusionAdapter(
            process_noise=4.0,
            stable_threshold_m=35.0,
            handover_threshold_m=14.0,
            association_gate=4.0,
            use_truth_hints_for_association=True,
        )
        self.tracker = Tracker(
            associator=GNNHungarianAssociator(gate_threshold=18.0, feature_weight=0.0),
            process_noise=0.8,
            confirmation_hits=2,
            engageable_hits=3,
            engageable_covariance_trace=120.0,
        )
        planner_config = PlannerConfig(
            delta=0.2,
            min_dwell=1.0,
            human_authorization_state=str(
                config.metadata.get("main_bus_human_authorization_state", "recorded")
            ),
        )
        self.assignment_planner = AssignmentPlanner(
            cost_model=CostModel(
                weights=CostWeights(
                    window=0.2,
                    covariance=0.3,
                    threat=0.5,
                    resource_state=0.4,
                    fov=2.2,
                    conflict=0.6,
                ),
                config=planner_config,
            ),
            config=planner_config,
        )
        self.d4 = D4ArbitrationAdapter(
            ActiveDegradationArbiter(
                ActiveDegradationConfig(
                    min_dwell_s=0.5,
                    release_consecutive_consistent_frames=2,
                    risk_window_size=3,
                    risk_window_threshold=2,
                )
            )
        )
        self.terminal = TerminalAssociator()
        self.terminal_consistency = TerminalConsistencyTracker()
        self.terminal_bus = TerminalObservationBus()
        self.d7_runtime_bus = D7RuntimeBus()
        self.collector = MetricsCollector()
        self.current_plan: AssignmentPlan | None = None
        self.previous_plan: AssignmentPlan | None = None
        self.current_bindings: tuple[Any, ...] = ()
        self._next_assignment_time_s = 0.0
        self._last_d4_by_pair: dict[tuple[str, str], Any] = {}
        self._last_d5_by_pair: dict[tuple[str, str], TerminalAssociation] = {}
        self._last_d7_mode_by_pair: dict[tuple[str, str], str] = {}
        self._pending_center_replan_reason: str | None = None
        self._pending_secondary_takeover: dict[str, Any] | None = None
        self._pending_terminal_feedback: list[dict[str, Any]] = []
        self._last_terminal_feedback_writeback: dict[str, Any] = {}
        self._last_d7_runtime_summary: dict[str, Any] = {}
        self._clock_source = str(
            config.metadata.get("clock_source", "airsim_frame_timestamp")
        )
        self._module_health: dict[str, dict[str, Any]] = {}
        self._runtime_errors: list[dict[str, Any]] = []
        self._frame_processing_durations_s: list[float] = []
        self.ticks: list[MainEpisodeBusTick] = []

    def process_frame(self, frame: AirSimFrame) -> MainEpisodeBusTick:
        frame_started = time.perf_counter()
        timestamp = float(frame.timestamp)
        truth_states = truth_states_from_blocks_frame(frame)
        truth_by_id = {state.truth_id: state for state in truth_states}
        resources = resources_from_blocks_frame(frame)
        observations = self._process_d1(frame)
        self._mark_module_health("D1", timestamp, record_count=len(observations))
        d1_tracks = self.fusion.global_tracks()
        association_result = self._process_d2(timestamp, d1_tracks, truth_states)
        self._mark_module_health("D2", timestamp, record_count=len(d1_tracks))
        d2_tracks = self.tracker.active_tracks()
        self.collector.extend_tracks(track_records_from_d2(d2_tracks, truth_by_id, timestamp))

        plan_changed = self._maybe_plan(timestamp, frame, d2_tracks, truth_by_id, resources)
        self._mark_module_health(
            "D3",
            timestamp,
            record_count=0 if self.current_plan is None else len(self.current_plan.assignments),
        )
        terminal_contexts: list[_TerminalDecisionContext] = []
        d4_results: list[Any] = []
        d7_events: list[EventRecord] = []
        if self.current_plan is not None:
            terminal_contexts = self._process_d5(frame, d2_tracks, truth_by_id)
            self._mark_module_health("D5", timestamp, record_count=len(terminal_contexts))
            d4_results = self._process_d4(
                frame=frame,
                d2_tracks=d2_tracks,
                association_result=association_result,
                terminal_contexts=terminal_contexts,
                resources=resources,
                communication_records=self._communication_records_for_frame(frame, observations),
            )
            self._mark_module_health("D4", timestamp, record_count=len(d4_results))
            d7_events = self._process_d7(frame, d2_tracks, resources, terminal_contexts, d4_results)
            self._mark_module_health("D7", timestamp, record_count=len(d7_events))
            self.collector.extend_events(d7_events)
        else:
            self._mark_module_health("D5", timestamp, status="idle", record_count=0)
            self._mark_module_health("D4", timestamp, status="idle", record_count=0)
            self._mark_module_health("D7", timestamp, status="idle", record_count=0)

        self._record_frame_links(frame, observations)
        self._record_cross_view_events(frame.timestamp)
        processing_duration_s = max(0.0, time.perf_counter() - frame_started)
        self._frame_processing_durations_s.append(processing_duration_s)
        tick = MainEpisodeBusTick(
            timestamp=timestamp,
            frame_index=int(frame.frame_index),
            clock=self._clock_snapshot(
                frame=frame,
                processing_duration_s=processing_duration_s,
            ),
            module_health=self._module_health_snapshot(timestamp),
            d1={
                "observation_count": len(observations),
                "track_count": len(d1_tracks),
                "track_ids": [track.global_track_id for track in d1_tracks],
                "uncertainty_summaries": [
                    summary.to_dict() for summary in self.fusion.track_uncertainty_summaries()
                ],
                "observations": [_observation_summary(item) for item in observations],
            },
            d2={
                "track_count": len(d2_tracks),
                "global_track_ids": [track.global_track_id for track in d2_tracks],
                "association_result": association_result.to_dict(),
                "id_switch_count": self.tracker.metrics.id_switch_count,
                "track_continuity": self.tracker.metrics.track_continuity,
                "risk": self.tracker.metrics.summary(),
            },
            d3={
                "plan_changed": plan_changed,
                "plan_id": None if self.current_plan is None else self.current_plan.plan_id,
                "plan_version": None if self.current_plan is None else self.current_plan.version,
                "assignment_count": 0 if self.current_plan is None else len(self.current_plan.assignments),
                "guidance_binding_count": len(self.current_bindings),
                "resource_count": len(resources),
                "target_count": len(truth_states),
                "active_plan_owner": None
                if self.current_plan is None
                else self.current_plan.metadata.get("active_plan_owner", "center"),
                "plan_schema": None
                if self.current_plan is None
                else self.current_plan.metadata.get("plan_schema"),
                "terminal_feedback_writeback": self._last_terminal_feedback_writeback,
            },
            d4={
                "decision_count": len(d4_results),
                "actions": [result.record.action.value for result in d4_results],
                "modes": [result.record.mode.value for result in d4_results],
            },
            d5={
                "terminal_association_count": len(terminal_contexts),
                "decision_states": [
                    context.terminal_association.decision_state for context in terminal_contexts
                ],
                "locked_count": sum(
                    1
                    for context in terminal_contexts
                    if context.terminal_association.decision_state == "locked"
                ),
                "cross_view_association_count": len(self.terminal_bus.cross_view_associations()),
            },
            d7={
                "event_count": len(d7_events),
                "modes": [event.metadata.get("mode") for event in d7_events],
                "terminal_contract_reject_reasons": [
                    event.metadata.get("terminal_contract_reject_reason")
                    for event in d7_events
                    if event.metadata.get("terminal_contract_reject_reason")
                ],
                "runtime_bus": self._last_d7_runtime_summary,
            },
            record_counts=self._record_counts(),
        )
        self.ticks.append(tick)
        return tick

    def finalize(self, frames: Iterable[AirSimFrame], output_dir: Path) -> MainEpisodeBusResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        frames_list = list(frames)
        truth_summary = _truth_summary_for_bus(frames_list, self.config)
        metrics = self.collector.compute_episode(
            episode_id=self.config.episode_id,
            seed=self.config.seed,
            duration=self.config.duration_s,
            truth_summary=truth_summary,
        )
        mission = self._mission_outcome(frame_count=len(frames_list))
        runtime_metadata = self._runtime_metadata(
            frames=frames_list,
            mission=mission,
        )
        metrics.mission_outcome = str(mission["mission_outcome"])
        metrics.success_reason = str(mission["success_reason"])
        metrics.failure_reason = str(mission["failure_reason"])
        metrics.eval_priority = "P0"
        metrics.implementation_status = "implemented"
        metrics.evidence_path = str(output_dir / "main_episode_bus_metrics.json")
        if hasattr(metrics, "scenario_version"):
            metrics.scenario_version = _scenario_version(self.config, frames_list)
        if hasattr(metrics, "standard_mapping_version"):
            metrics.standard_mapping_version = STANDARD_MAPPING_VERSION
        metrics.module_duration_ms = float(
            self._episode_clock_metadata(frames_list)["mean_processing_duration_s"] * 1000.0
        )
        metrics.loop_latency_ms = metrics.module_duration_ms
        metrics.record_latency_ms = float(
            runtime_metadata.get("record_latency_ms", 0.0)
        )
        metrics.performance_budget_violation_count = int(
            runtime_metadata.get("performance_budget_violation_count", 0)
        )
        metrics.metadata = {
            **dict(metrics.metadata),
            **runtime_metadata,
        }
        output_paths = {
            "main_episode_bus_jsonl": _write_d6_episode_jsonl(
                truth_summary,
                self.collector,
                output_dir / "main_episode_bus.jsonl",
            ),
            "main_episode_bus_ticks_jsonl": _write_ticks_jsonl(
                self.ticks,
                output_dir / "main_episode_bus_ticks.jsonl",
            ),
            "main_episode_bus_metrics_json": _write_json(
                output_dir / "main_episode_bus_metrics.json",
                {
                    "metrics": metrics.to_dict(),
                    "metadata": {
                        "record_counts": self._record_counts(),
                        **runtime_metadata,
                    },
                },
            ),
        }
        summary = {
            "episode_id": self.config.episode_id,
            "scenario_name": self.config.scenario_name,
            "frame_count": len(frames_list),
            "clock": self._episode_clock_metadata(frames_list),
            "scenario_config": self._scenario_config_metadata(frames_list),
            "standard_mapping_version": STANDARD_MAPPING_VERSION,
            "scenario_version": _scenario_version(self.config, frames_list),
            "module_health": self._module_health_snapshot(
                frames_list[-1].timestamp if frames_list else 0.0
            ),
            "runtime_errors": list(self._runtime_errors),
            "mission_outcome": mission,
            "module_order": ["D1", "D2", "D3", "D5", "D4", "D7", "D6"],
            "record_counts": self._record_counts(),
            "d2_metrics": self.tracker.metrics.summary(),
            "current_plan": None if self.current_plan is None else _plan_summary(self.current_plan),
            "guidance_binding_count": len(self.current_bindings),
            "last_terminal_feedback_writeback": self._last_terminal_feedback_writeback,
            "last_d7_runtime_summary": self._last_d7_runtime_summary,
            "last_d4_actions": {
                f"{resource_id}:{track_id}": result.record.action.value
                for (resource_id, track_id), result in self._last_d4_by_pair.items()
            },
            "last_d5_states": {
                f"{resource_id}:{track_id}": association.decision_state
                for (resource_id, track_id), association in self._last_d5_by_pair.items()
            },
            "last_d7_modes": {
                f"{resource_id}:{track_id}": mode
                for (resource_id, track_id), mode in self._last_d7_mode_by_pair.items()
            },
            "metrics": metrics.to_dict(),
        }
        output_paths["main_episode_bus_summary_json"] = _write_json(
            output_dir / "main_episode_bus_summary.json",
            summary,
        )
        return MainEpisodeBusResult(
            episode_id=self.config.episode_id,
            scenario_name=self.config.scenario_name,
            frame_count=len(frames_list),
            metrics=metrics.to_dict(),
            summary=summary,
            output_paths=output_paths,
        )

    def _process_d1(self, frame: AirSimFrame) -> list[SensorObservation]:
        observations = observations_from_blocks_frame(
            frame,
            arrival_timestamp=frame.timestamp + self.config.radar_latency_s,
            include_lidar=self.config.capture_lidar,
        )
        observations.sort(key=lambda obs: (obs.arrival_timestamp, obs.modality, obs.observation_id))
        for observation in observations:
            self.fusion.process(observation)
        return observations

    def _process_d2(self, timestamp: float, d1_tracks: list[Any], truth_states: list[TruthState]) -> Any:
        detections = d1_tracks_to_d2_detections(d1_tracks, timestamp)
        return self.tracker.step(
            detections,
            timestamp=timestamp,
            truth_ids_present=[state.truth_id for state in truth_states],
        )

    def _maybe_plan(
        self,
        timestamp: float,
        frame: AirSimFrame,
        d2_tracks: list[Any],
        truth_by_id: dict[str, TruthState],
        resources: list[ResourcePlatform],
    ) -> bool:
        if not d2_tracks or not resources:
            return False
        forced_replan_reason = self._pending_center_replan_reason
        secondary_takeover = self._pending_secondary_takeover
        if forced_replan_reason is None and secondary_takeover is not None:
            forced_replan_reason = str(
                secondary_takeover.get("reason") or "d4_degrade_to_secondary"
            )
        if (
            self.current_plan is not None
            and forced_replan_reason is None
            and not self._pending_terminal_feedback
            and timestamp + 1e-9 < self._next_assignment_time_s
        ):
            return False

        target_tracks = d2_tracks_to_target_tracks(d2_tracks, truth_by_id, resources)
        if not target_tracks:
            return False
        resource_states = resources_to_d3(resources)
        feedback_writeback = None
        if self._pending_terminal_feedback:
            feedback_writeback = apply_terminal_feedback_to_planner_inputs(
                target_tracks,
                resource_states,
                self._pending_terminal_feedback,
            )
            target_tracks = list(feedback_writeback.tracks)
            resource_states = list(feedback_writeback.resources)
            self._last_terminal_feedback_writeback = _jsonable(feedback_writeback.metadata)
            self.collector.add_event(
                EventRecord(
                    timestamp=timestamp,
                    event_type="d3_terminal_feedback_writeback",
                    actor_id="D3",
                    metadata={
                        **_jsonable(feedback_writeback.metadata),
                        "prohibited_edges": _jsonable(feedback_writeback.prohibited_edges),
                        "hold_resource_ids": list(feedback_writeback.hold_resource_ids),
                        "updated_target_ids": list(feedback_writeback.updated_target_ids),
                        "updated_resource_ids": list(feedback_writeback.updated_resource_ids),
                    },
                )
            )
        else:
            self._last_terminal_feedback_writeback = {"feedback_count": 0}
        previous = self.current_plan
        try:
            plan = self.assignment_planner.plan(
                target_tracks,
                resource_states,
                timestamp=timestamp,
                previous_plan=previous,
                expected_previous_version=None if previous is None else previous.version,
            )
        except StalePlanError as error:
            if previous is None:
                raise
            self.collector.add_event(
                EventRecord(
                    timestamp=timestamp,
                    event_type="d3_stale_plan_rejected",
                    actor_id="D3",
                    severity="warning",
                    note=str(error),
                    metadata={
                        **_jsonable(error.to_metadata()),
                        "retained_plan_id": previous.plan_id,
                        "retained_plan_version": previous.version,
                        "retry_policy": "retain_current_plan_and_retry_next_cycle",
                    },
                )
            )
            self._next_assignment_time_s = timestamp + max(float(self.config.dt_s), 1e-6)
            return False
        if feedback_writeback is not None:
            self._pending_terminal_feedback = []
        if forced_replan_reason is not None and previous is not None:
            plan = replace(
                plan,
                decision_state="center_replan_accepted",
                metadata={
                    **dict(plan.metadata),
                    "replan_reason": forced_replan_reason,
                    "supersedes_plan_id": previous.plan_id,
                    "supersedes_plan_version": previous.version,
                    "active_plan_owner": "center",
                },
            )
            self._pending_center_replan_reason = None
        if secondary_takeover is not None and previous is not None:
            source_node_id = _secondary_takeover_source_node_id(
                frame,
                secondary_takeover,
                previous_plan=previous,
            )
            plan = prepare_secondary_takeover_plan(
                plan,
                supersedes_plan=previous,
                secondary_node_id=source_node_id,
                takeover_reason=str(
                    secondary_takeover.get("reason") or "d4_degrade_to_secondary"
                ),
                target_node_id="D7-GUIDANCE",
                lease_expires_at_s=timestamp + max(float(self.config.dt_s) * 4.0, 1.0),
            )
            self._pending_secondary_takeover = None
        self.previous_plan = previous
        self.current_plan = plan
        self._next_assignment_time_s = timestamp + max(float(self.config.dt_s), 1e-6)
        d2_by_id = {track.global_track_id: track for track in d2_tracks}
        assignment_records = plan_to_assignment_records(plan, d2_by_id)
        self.collector.extend_assignments(assignment_records)
        self.current_bindings = guidance_bindings_from_assignment_plan(
            plan,
            resource_vehicle_map=_resource_vehicle_map(frame),
            target_alias_map=_target_alias_map(frame, d2_tracks),
            guidance_phase="radar_midcourse",
            now_s=timestamp,
            previous_plan=previous,
        )
        self.collector.add_event(
            EventRecord(
                timestamp=timestamp,
                event_type="assignment_plan_snapshot",
                actor_id="D3",
                metadata={
                    "plan_id": plan.plan_id,
                    "plan_version": plan.version,
                    "assignment_count": len(plan.assignments),
                    "resource_count": plan.resource_count,
                    "target_count": plan.target_count,
                    "decision_state": plan.decision_state,
                    "human_authorization_state": plan.human_authorization_state,
                    "replan_reason": plan.metadata.get("replan_reason"),
                    "supersedes_plan_id": plan.metadata.get("supersedes_plan_id"),
                    "supersedes_plan_version": plan.metadata.get("supersedes_plan_version"),
                    "plan_schema": plan.metadata.get("plan_schema"),
                    "active_plan_owner": plan.metadata.get("active_plan_owner", "center"),
                    "owner_node_id": plan.metadata.get("owner_node_id"),
                    "selected_secondary_node_id": plan.metadata.get("selected_secondary_node_id"),
                    "terminal_feedback_writeback_applied": bool(
                        feedback_writeback is not None
                    ),
                },
            )
        )
        return previous is None or plan.changed

    def _process_d5(
        self,
        frame: AirSimFrame,
        d2_tracks: list[Any],
        truth_by_id: dict[str, TruthState],
    ) -> list[_TerminalDecisionContext]:
        if self.current_plan is None:
            return []
        timestamp = float(frame.timestamp)
        terminal_tracks = d2_tracks_to_terminal_tracks(
            d2_tracks,
            truth_by_id,
            plan_version=self.current_plan.version,
            timestamp=timestamp,
        )
        terminal_assignments = {
            assignment.assigned_global_track_id: assignment
            for assignment in plan_to_terminal_assignments(self.current_plan)
        }
        if not terminal_tracks or not terminal_assignments:
            return []
        d2_by_id = {track.global_track_id: track for track in d2_tracks}
        local_tracks = geometric_local_visual_tracks_from_blocks_frame(frame)
        local_truth_map = offline_truth_map_from_blocks_frame(frame, d2_tracks)
        cross_view_before = {
            item.global_track_id: item for item in self.terminal_bus.cross_view_associations()
        }
        contexts: list[_TerminalDecisionContext] = []
        for assignment in self.current_plan.assignments:
            terminal_assignment = terminal_assignments.get(assignment.target_id)
            if terminal_assignment is None:
                continue
            camera = _camera_for_resource(frame, assignment.resource_id, assignment.target_id, terminal_tracks)
            scoped_local_tracks = _local_tracks_for_resource(frame, assignment.resource_id, local_tracks)
            recon_cues = _recon_cues_for_assignment(
                frame,
                assignment.resource_id,
                assignment.target_id,
                terminal_tracks,
                camera,
                self.terminal,
            )
            decision = self.terminal.decide(
                terminal_assignment,
                terminal_tracks,
                scoped_local_tracks,
                identity_claims=(),
                camera=camera,
                current_time=timestamp,
                recon_image_cues=recon_cues,
                frame_id=f"{frame.episode_id}:{frame.frame_index:04d}:{assignment.resource_id}",
            )
            local_track = _local_track_by_id(scoped_local_tracks, decision.local_track_id)
            duplicate_risk_hint = bool(
                cross_view_before.get(decision.assigned_global_track_id)
                and cross_view_before[
                    decision.assigned_global_track_id
                ].duplicate_terminal_lock_risk
            )
            decision = annotate_visual_png_handoff(
                decision,
                local_track_history=scoped_local_tracks,
                image_size=camera.image_size,
                range_to_assigned_track_m=_range_for_terminal_context(
                    frame,
                    assignment.resource_id,
                    d2_by_id.get(assignment.target_id),
                ),
                closing_speed_mps=float(self.config.intercept_speed_mps),
                measurement_age_s=None
                if local_track is None
                else max(0.0, timestamp - float(local_track.timestamp)),
                current_time=timestamp,
                assignment_consistent=True,
                current_assigned_global_track_id=assignment.target_id,
                duplicate_terminal_lock_risk=duplicate_risk_hint,
            )
            observed_global_track_id = (
                local_truth_map.get(decision.local_track_id)
                if decision.local_track_id is not None
                else None
            )
            terminal_record = terminal_to_record(
                timestamp=timestamp,
                resource_id=assignment.resource_id,
                assigned_global_track_id=terminal_assignment.assigned_global_track_id,
                local_track_id=decision.local_track_id,
                decision_state=decision.decision_state,
                ambiguity_score=decision.ambiguity_score,
                friend_conflict_state=decision.friend_conflict_state,
                assignment_version=decision.assignment_version,
                observed_global_track_id=observed_global_track_id,
            )
            self.collector.add_terminal(terminal_record)
            local_track = _local_track_by_id(scoped_local_tracks, decision.local_track_id)
            self.terminal_bus.publish_terminal_association(
                resource_id=assignment.resource_id,
                source_node_id=assignment.resource_id,
                link_type="c2_direct",
                timestamp=timestamp,
                terminal_association=decision,
                local_track=local_track,
                recon_image_cues=recon_cues,
                camera_id=_camera_id_for_resource(frame, assignment.resource_id),
                frame_id=f"{frame.episode_id}:{frame.frame_index:04d}",
                arrival_timestamp=timestamp,
                metadata={
                    "online_truth_id_used": False,
                    "offline_observed_global_track_id": observed_global_track_id,
                },
            )
            consistency = self.terminal_consistency.update(
                resource_id=assignment.resource_id,
                timestamp=timestamp,
                association=decision,
                cross_view_association=cross_view_before.get(decision.assigned_global_track_id),
                metadata={"source": "main_airsim_episode_bus"},
            )
            self._pending_terminal_feedback.append(
                _terminal_feedback_metadata(
                    assignment=assignment,
                    decision=decision,
                    consistency=consistency,
                    local_track=local_track,
                )
            )
            context = _TerminalDecisionContext(
                assignment=assignment,
                terminal_assignment=terminal_assignment,
                d2_track=d2_by_id.get(assignment.target_id),
                terminal_association=decision,
                terminal_record=terminal_record,
                local_track=local_track,
                observed_global_track_id=observed_global_track_id,
                consistency_summary=consistency,
            )
            self._last_d5_by_pair[(assignment.resource_id, assignment.target_id)] = decision
            contexts.append(context)
        return contexts

    def _process_d4(
        self,
        *,
        frame: AirSimFrame,
        d2_tracks: list[Any],
        association_result: Any,
        terminal_contexts: list[_TerminalDecisionContext],
        resources: list[ResourcePlatform],
        communication_records: list[Any],
    ) -> list[Any]:
        if self.current_plan is None:
            return []
        timestamp = float(frame.timestamp)
        d2_by_id = {track.global_track_id: track for track in d2_tracks}
        resources_by_id = {resource.resource_id: resource for resource in resources}
        cross_view = {
            item.global_track_id: item for item in self.terminal_bus.cross_view_associations()
        }
        secondary_nodes = [
            item
            for item in resources_to_d4(resources, _secondary_available(frame), epoch=1)
            if item.coordinator_only
        ]
        health = C2Health.NORMAL if frame.center_node_alive else C2Health.FAILED
        results: list[Any] = []
        for context in terminal_contexts:
            assignment = context.assignment
            d2_track = d2_by_id.get(assignment.target_id) or context.d2_track
            if d2_track is None:
                continue
            consistency = context.consistency_summary
            result = self.d4.evaluate(
                timestamp=timestamp,
                track=d2_track,
                association_result=association_result,
                association_metrics=self.tracker.metrics,
                plan=self.current_plan,
                assignment=assignment,
                terminal_association=context.terminal_association,
                cross_view_summary=cross_view.get(context.terminal_association.assigned_global_track_id),
                c2_health=health,
                secondary_nodes=secondary_nodes,
                communication_records=communication_records,
                coverage_cell=getattr(resources_by_id.get(assignment.resource_id), "coverage_cell", None),
                resource_id=assignment.resource_id,
                global_track_id=assignment.target_id,
                observed_global_track_id=None,
                consecutive_non_locked_frames=_non_locked_count(consistency),
                consecutive_mismatch_frames=0,
                current_plan_version=self.current_plan.version,
                expected_plan_version=self.current_plan.version,
                track_version=self.current_plan.version,
                plan_id=self.current_plan.plan_id,
                active_plan_owner=str(
                    self.current_plan.metadata.get("active_plan_owner", "center")
                ),
                secondary_plan_id=self.current_plan.plan_id
                if self.current_plan.metadata.get("active_plan_owner") == "secondary"
                else None,
                secondary_plan_version=self.current_plan.version
                if self.current_plan.metadata.get("active_plan_owner") == "secondary"
                else None,
                secondary_plan_active=self.current_plan.metadata.get("active_plan_owner")
                == "secondary",
                secondary_plan_source_node_id=self.current_plan.metadata.get("owner_node_id")
                or self.current_plan.metadata.get("selected_secondary_node_id"),
                trigger_timestamp=timestamp,
            )
            self.collector.add_event(EventRecord(**result.record.to_event_record_kwargs()))
            self._last_d4_by_pair[(assignment.resource_id, assignment.target_id)] = result
            if result.record.action.value == "request_center_replan":
                self._pending_center_replan_reason = result.record.reason
            if result.record.action.value == "degrade_to_secondary":
                self._pending_secondary_takeover = result.record.to_event_metadata()
            results.append(result)
        return results

    def _process_d7(
        self,
        frame: AirSimFrame,
        d2_tracks: list[Any],
        resources: list[ResourcePlatform],
        terminal_contexts: list[_TerminalDecisionContext],
        d4_results: list[Any],
    ) -> list[EventRecord]:
        if self.current_plan is None:
            return []
        timestamp = float(frame.timestamp)
        d2_by_id = {track.global_track_id: track for track in d2_tracks}
        resources_by_id = {resource.resource_id: resource for resource in resources}
        d4_by_pair = {
            (result.record.resource_id, result.record.global_track_id): result
            for result in d4_results
        }
        d5_by_pair = {
            (context.assignment.resource_id, context.assignment.target_id): context.terminal_association
            for context in terminal_contexts
        }
        binding_by_pair = {
            (binding.resource_id, binding.assigned_global_track_id): binding
            for binding in self.current_bindings
        }
        events: list[EventRecord] = []
        runtime_outputs: list[Any] = []
        for assignment in self.current_plan.assignments:
            pair = (assignment.resource_id, assignment.target_id)
            resource = resources_by_id.get(assignment.resource_id)
            track = d2_by_id.get(assignment.target_id)
            binding = binding_by_pair.get(pair)
            terminal_association = d5_by_pair.get(pair)
            d4_result = d4_by_pair.get(pair) or self._last_d4_by_pair.get(pair)
            if resource is None or track is None or binding is None:
                continue
            d4_permission = _d4_permission(d4_result)
            binding_for_d7 = _binding_for_d7(binding)
            contract = evaluate_terminal_png_contract(
                binding=binding_for_d7,
                d4_permission=d4_permission,
                terminal_association=terminal_association,
                observation=None,
                timestamp_s=timestamp,
                resource_id=assignment.resource_id,
            )
            range_m = _range_resource_to_track(resource, track)
            handover_pending = range_m <= float(self.config.intercept_terminal_switch_range_m)
            runtime_output = self.d7_runtime_bus.evaluate_pair(
                D7RuntimePairInput(
                    binding=binding_for_d7,
                    d4_permission=d4_permission,
                    terminal_association=terminal_association,
                    observation=_vision_observation_for_d7(
                        d5_by_pair.get(pair),
                        terminal_contexts,
                        assignment.resource_id,
                        assignment.target_id,
                        timestamp,
                    ),
                    timestamp_s=timestamp,
                    resource_id=assignment.resource_id,
                    handover_pending=handover_pending,
                    terminal_locked=bool(contract.allowed),
                    current_speed_mps=max(float(self.config.intercept_speed_mps), 1.0),
                    intercept_speed_mps=max(float(self.config.intercept_speed_mps), 1.0),
                    relative_position_ned=_relative_position_resource_to_track(resource, track),
                    relative_velocity_ned=_relative_velocity_resource_to_track(resource, track),
                    metadata={
                        "source": "main_airsim_episode_bus",
                        "range_m": range_m,
                    },
                )
            )
            runtime_outputs.append(runtime_output)
            mode = guidance_mode_from_terminal_contract(
                contract,
                handover_pending=handover_pending,
                terminal_locked=bool(contract.allowed),
            )
            command = _pn_command_for_pair(
                timestamp=timestamp,
                mode=mode,
                resource=resource,
                track=track,
                speed_mps=max(float(self.config.intercept_speed_mps), 1.0),
                dt_s=max(float(self.config.dt_s), 1e-3),
                navigation_constant=float(self.config.intercept_navigation_constant),
            )
            previous_mode = self._last_d7_mode_by_pair.get(pair)
            mode_text = mode.value if isinstance(mode, GuidanceMode) else str(mode)
            self._last_d7_mode_by_pair[pair] = mode_text
            metadata = {
                **command.as_dict(),
                "timestamp_s": timestamp,
                "resource_id": assignment.resource_id,
                "target_id": assignment.target_id,
                "global_track_id": assignment.target_id,
                "plan_id": binding.plan_id,
                "plan_version": binding.plan_version,
                "track_version": binding.track_version,
                "assignment_id": binding.assignment_id,
                "assignment_validity_state": binding.assignment_validity_state,
                "d4_state": d4_permission.action,
                "d4_action": d4_permission.action,
                "d4_mode": d4_permission.mode,
                "d5_state": "" if terminal_association is None else terminal_association.decision_state,
                "d5_decision_state": "" if terminal_association is None else terminal_association.decision_state,
                "terminal_switch_allowed": bool(contract.allowed),
                "terminal_handover_pending": handover_pending,
                "terminal_mode_entered": mode == GuidanceMode.VISION_TERMINAL,
                "terminal_contract_reject_reason": contract.reject_reason or None,
                "terminal_switch_reject_reason": contract.reject_reason or None,
                "guidance_law": "png_vm" if mode == GuidanceMode.VISION_TERMINAL else "radar_pn",
                "mode_switch": previous_mode is not None and previous_mode != mode_text,
                "range_m": range_m,
                "camera_quality_gate_passed": terminal_association is not None,
                "los_quality_gate_passed": True,
                "maneuver_margin_gate_passed": True,
                "d7_runtime_bus_boundary": runtime_output.metadata.get("boundary"),
                "d7_runtime_control_context_id": runtime_output.control_context_id,
                "d7_runtime_visual_png_enabled": runtime_output.visual_png_enabled,
                "d7_runtime_terminal_switch_allowed": runtime_output.terminal_switch_allowed,
                "d7_runtime_terminal_switch_reject_reason": (
                    runtime_output.terminal_switch_reject_reason or None
                ),
                "d7_runtime_guidance_law": runtime_output.guidance_law,
                "d7_runtime_stable_frame_count": runtime_output.stable_frame_count,
                "d7_runtime_ttc_s": runtime_output.ttc_s,
                "d7_runtime_los_rate_radps": runtime_output.los_rate_radps,
                "owner_node_id": runtime_output.owner_node_id,
                "d4_target_node_id": runtime_output.d4_target_node_id,
            }
            events.append(
                EventRecord(
                    timestamp=timestamp,
                    event_type="d7_guidance_record",
                    actor_id=assignment.resource_id,
                    metadata={key: value for key, value in metadata.items() if value is not None},
                )
            )
        self._last_d7_runtime_summary = summarize_runtime_bus_outputs(runtime_outputs)
        return events

    def _record_frame_links(self, frame: AirSimFrame, observations: list[SensorObservation]) -> None:
        self.collector.extend_links(_sensor_link_records(observations))
        self.collector.extend_links(_video_link_records(frame))

    def _record_cross_view_events(self, timestamp: float) -> None:
        for item in self.terminal_bus.cross_view_associations():
            if item.support_count > 1:
                self.collector.add_event(
                    EventRecord(
                        timestamp=timestamp,
                        event_type="multi_view_consensus_result",
                        actor_id=item.global_track_id,
                        metadata={
                            "assigned_global_track_id": item.global_track_id,
                            "supporting_resource_ids": list(item.supporting_resource_ids),
                            "support_count": item.support_count,
                            "multi_view_consensus": True,
                        },
                    )
                )
            if item.duplicate_terminal_lock_risk:
                self.collector.add_event(
                    EventRecord(
                        timestamp=timestamp,
                        event_type="duplicate_terminal_lock",
                        actor_id=item.global_track_id,
                        severity="warning",
                        metadata=item.__dict__,
                    )
                )

    def _communication_records_for_frame(
        self,
        frame: AirSimFrame,
        observations: list[SensorObservation],
    ) -> list[Any]:
        return [*_sensor_link_records(observations), *_video_link_records(frame)]

    def _record_counts(self) -> dict[str, int]:
        return {
            "tracks": len(self.collector.track_records),
            "assignments": len(self.collector.assignment_records),
            "events": len(self.collector.event_records),
            "links": len(self.collector.link_records),
            "terminals": len(self.collector.terminal_records),
            "ticks": len(self.ticks),
        }

    def record_runtime_exception(
        self,
        *,
        module_id: str,
        timestamp: float,
        error: BaseException,
    ) -> None:
        """Record a failed module outcome in D6-readable metadata."""

        payload = {
            "module_id": str(module_id),
            "timestamp": float(timestamp),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "mission_outcome": "failed",
            "failure_reason": "runtime_exception",
        }
        self._runtime_errors.append(payload)
        self._mark_module_health(
            str(module_id),
            float(timestamp),
            status="failed",
            error_state=type(error).__name__,
            last_error=str(error),
        )
        self.collector.add_event(
            EventRecord(
                timestamp=float(timestamp),
                event_type="runtime_exception",
                actor_id=str(module_id),
                severity="error",
                note=str(error),
                metadata=payload,
            )
        )

    def _mark_module_health(
        self,
        module_id: str,
        timestamp: float,
        *,
        status: str = "ok",
        record_count: int | None = None,
        error_state: str = "",
        last_error: str = "",
    ) -> None:
        previous = self._module_health.get(str(module_id), {})
        self._module_health[str(module_id)] = {
            "status": str(status),
            "last_update_timestamp": float(timestamp),
            "record_count": int(
                previous.get("record_count", 0) if record_count is None else record_count
            ),
            "error_state": str(error_state),
            "last_error": str(last_error),
        }

    def _module_health_snapshot(self, timestamp: float) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        for module_id in ("D1", "D2", "D3", "D4", "D5", "D6", "D7"):
            health = dict(self._module_health.get(module_id, {}))
            if not health:
                health = {
                    "status": "not_started",
                    "last_update_timestamp": None,
                    "record_count": 0,
                    "error_state": "",
                    "last_error": "",
                }
            last_update = health.get("last_update_timestamp")
            health["last_update_age_s"] = (
                None
                if last_update is None
                else max(0.0, float(timestamp) - float(last_update))
            )
            snapshot[module_id] = health
        snapshot["D6"] = {
            **snapshot["D6"],
            "status": "passive_collector",
            "record_count": sum(self._record_counts().values()),
            "last_update_timestamp": float(timestamp),
            "last_update_age_s": 0.0,
        }
        for module_id, health_value in self._module_health.items():
            if module_id in snapshot:
                continue
            health = dict(health_value)
            last_update = health.get("last_update_timestamp")
            health["last_update_age_s"] = (
                None
                if last_update is None
                else max(0.0, float(timestamp) - float(last_update))
            )
            snapshot[module_id] = health
        return snapshot

    def _clock_snapshot(
        self,
        *,
        frame: AirSimFrame,
        processing_duration_s: float,
    ) -> dict[str, Any]:
        timestamp = float(frame.timestamp)
        return {
            "episode_time_s": timestamp,
            "clock_source": self._clock_source,
            "measurement_timestamp": timestamp,
            "arrival_timestamp": timestamp,
            "publish_timestamp": timestamp,
            "processing_timestamp": timestamp,
            "processing_duration_s": float(processing_duration_s),
            "frame_index": int(frame.frame_index),
        }

    def _episode_clock_metadata(self, frames: list[AirSimFrame]) -> dict[str, Any]:
        timestamps = [float(frame.timestamp) for frame in frames]
        durations = list(self._frame_processing_durations_s)
        return {
            "clock_source": self._clock_source,
            "episode_time_start_s": min(timestamps) if timestamps else 0.0,
            "episode_time_end_s": max(timestamps) if timestamps else 0.0,
            "frame_count": len(frames),
            "mean_processing_duration_s": (
                float(sum(durations) / len(durations)) if durations else 0.0
            ),
            "max_processing_duration_s": max(durations) if durations else 0.0,
        }

    def _scenario_config_metadata(self, frames: list[AirSimFrame] | None = None) -> dict[str, Any]:
        frame_target_ids = {
            obj.object_id
            for frame in frames or ()
            for obj in frame.truth_objects
            if obj.object_type == "target"
        }
        return {
            "episode_id": self.config.episode_id,
            "scenario_name": self.config.scenario_name,
            "seed": self.config.seed,
            "duration_s": self.config.duration_s,
            "dt_s": self.config.dt_s,
            "settings_path": str(self.config.settings_path),
            "scenario_version": _scenario_version(self.config, frames),
            "standard_mapping_version": STANDARD_MAPPING_VERSION,
            "resource_vehicle_names": list(self.config.resource_vehicle_names),
            "camera_vehicle_names": list(self.config.effective_camera_vehicle_names()),
            "secondary_camera_vehicle_names": list(self.config.secondary_camera_vehicle_names),
            "target_vehicle_names": list(self.config.target_vehicle_names),
            "target_count": len(frame_target_ids) or self.config.target_count(),
            "detection_backend": self.config.detection_backend,
            "execute_intercept": self.config.execute_intercept,
            "metadata": _jsonable(dict(self.config.metadata)),
        }

    def _mission_outcome(self, *, frame_count: int) -> dict[str, Any]:
        if self._runtime_errors:
            return {
                "mission_outcome": "failed",
                "success_reason": "",
                "failure_reason": "runtime_exception",
            }
        if frame_count <= 0:
            return {
                "mission_outcome": "aborted",
                "success_reason": "",
                "failure_reason": "no_frames",
            }
        record_counts = self._record_counts()
        if record_counts["tracks"] <= 0 or record_counts["events"] <= 0:
            return {
                "mission_outcome": "partial",
                "success_reason": "",
                "failure_reason": "incomplete_module_records",
            }
        return {
            "mission_outcome": "success",
            "success_reason": "episode_bus_records_complete",
            "failure_reason": "",
        }

    def _runtime_metadata(
        self,
        *,
        frames: list[AirSimFrame],
        mission: dict[str, Any],
    ) -> dict[str, Any]:
        module_health = self._module_health_snapshot(
            frames[-1].timestamp if frames else 0.0
        )
        return {
            **mission,
            "clock": self._episode_clock_metadata(frames),
            "module_health": module_health,
            "runtime_errors": list(self._runtime_errors),
            "top_failure_causes": _top_failure_causes(
                runtime_errors=self._runtime_errors,
                module_health=module_health,
                mission=mission,
            ),
            "record_latency_ms": self._record_latency_ms(),
            "performance_budget_violation_count": self._performance_budget_violation_count(),
            "scenario_config": self._scenario_config_metadata(frames),
            "standard_mapping_version": STANDARD_MAPPING_VERSION,
            "scenario_version": _scenario_version(self.config, frames),
        }

    def _record_latency_ms(self) -> float:
        latencies_ms: list[float] = []
        for record in self.collector.link_records:
            if record.measurement_timestamp is None or record.arrival_timestamp is None:
                continue
            latencies_ms.append(
                max(0.0, float(record.arrival_timestamp) - float(record.measurement_timestamp))
                * 1000.0
            )
        return float(sum(latencies_ms) / len(latencies_ms)) if latencies_ms else 0.0

    def _performance_budget_violation_count(self) -> int:
        budget_s = float(self.config.metadata.get("loop_budget_s", self.config.dt_s))
        return sum(1 for value in self._frame_processing_durations_s if value > budget_s)


def run_main_episode_bus(
    config: BlocksSmokeConfig,
    frames: Iterable[AirSimFrame],
    output_dir: Path,
) -> MainEpisodeBusResult:
    """Run the main runtime bus on already captured AirSim frames."""

    frame_list = list(frames)
    bus = MainAirSimEpisodeBus(config)
    for frame in frame_list:
        try:
            bus.process_frame(frame)
        except Exception as exc:
            bus.record_runtime_exception(
                module_id="main_episode_bus",
                timestamp=float(frame.timestamp),
                error=exc,
            )
            break
    return bus.finalize(frame_list, output_dir)


def _top_failure_causes(
    *,
    runtime_errors: list[dict[str, Any]],
    module_health: dict[str, Any],
    mission: dict[str, Any],
) -> list[dict[str, Any]]:
    causes: list[dict[str, Any]] = []
    if runtime_errors:
        causes.append(
            {
                "cause": "runtime_exception",
                "count": len(runtime_errors),
                "severity": "error",
            }
        )
    failed_modules = [
        module_id
        for module_id, health in module_health.items()
        if isinstance(health, Mapping) and health.get("status") == "failed"
    ]
    if failed_modules:
        causes.append(
            {
                "cause": "module_failed",
                "count": len(failed_modules),
                "severity": "error",
                "module_ids": failed_modules,
            }
        )
    if mission.get("mission_outcome") == "partial":
        causes.append(
            {
                "cause": str(mission.get("failure_reason") or "partial_episode"),
                "count": 1,
                "severity": "warning",
            }
        )
    return causes


def _sensor_link_records(observations: Iterable[SensorObservation]) -> list[LinkRecord]:
    records: list[LinkRecord] = []
    for observation in observations:
        communication = observation.communication_metadata
        records.append(
            LinkRecord(
                timestamp=float(observation.measurement_timestamp),
                source_node_id=str(
                    communication.get("source_node_id")
                    or observation.source_node_id
                    or observation.sensor_id
                ),
                target_node_id=str(
                    communication.get("target_node_id")
                    or observation.target_node_id
                    or "D1-FUSION"
                ),
                relay_node_id=communication.get("relay_node_id") or observation.relay_node_id,
                link_type=str(communication.get("link_type") or observation.link_type or "c2_replay"),
                message_type=str(observation.modality),
                sequence_id=observation.metadata.get("airsim_frame_index"),
                sent_timestamp=float(observation.sent_timestamp or observation.measurement_timestamp),
                received_timestamp=float(observation.received_timestamp or observation.arrival_timestamp),
                measurement_timestamp=float(observation.measurement_timestamp),
                arrival_timestamp=float(observation.arrival_timestamp),
                payload_kind=str(
                    communication.get("payload_kind")
                    or observation.payload_kind
                    or f"{observation.modality}_observation"
                ),
                delivered=True,
                stale_after_s=observation.stale_after_s,
                metadata={
                    "observation_id": observation.observation_id,
                    "sensor_id": observation.sensor_id,
                    "modality": observation.modality,
                    "covariance": None
                    if observation.covariance is None
                    else observation.covariance.tolist(),
                    "confidence": observation.confidence,
                    "quality_flags": list(observation.quality_flags),
                },
            )
        )
    return records


def _video_link_records(frame: AirSimFrame) -> list[LinkRecord]:
    records: list[LinkRecord] = []
    for image in frame.metadata.get("images", []) or []:
        owner = str(image.get("camera_vehicle_name") or image.get("owner_id") or "")
        records.append(
            LinkRecord(
                timestamp=float(frame.timestamp),
                source_node_id=owner or "unknown_camera",
                target_node_id="MAIN-RUNTIME-BUS",
                link_type="video_cue",
                message_type="video_metadata",
                sent_timestamp=float(frame.timestamp),
                received_timestamp=float(frame.timestamp),
                payload_kind="video_metadata",
                delivered=bool(image.get("ok", False)),
                metadata={
                    "camera_name": image.get("camera_name"),
                    "width": image.get("width"),
                    "height": image.get("height"),
                    "png_saved": bool(image.get("path")),
                },
            )
        )
    for detection in frame.visual_detections:
        owner = str(detection.camera_id).split(":", 1)[0]
        records.append(
            LinkRecord(
                timestamp=float(frame.timestamp),
                source_node_id=owner or "unknown_camera",
                target_node_id="D5-TERMINAL",
                link_type="video_cue",
                message_type="bbox",
                sent_timestamp=float(detection.timestamp),
                received_timestamp=float(frame.timestamp),
                measurement_timestamp=float(detection.timestamp),
                arrival_timestamp=float(frame.timestamp),
                payload_kind="bbox",
                delivered=True,
                metadata={
                    "camera_id": detection.camera_id,
                    "detection_id": detection.detection_id,
                    "local_track_id": detection.local_track_id,
                    "bbox_xyxy": list(detection.bbox_xyxy),
                    "confidence": detection.confidence,
                    "classification_hint": detection.classification_hint,
                    "truth_object_id_offline_only": detection.object_id,
                },
            )
        )
    return records


def _truth_summary_for_bus(frames: list[AirSimFrame], config: BlocksSmokeConfig) -> dict[str, Any]:
    timestamps_by_id: dict[str, list[float]] = {}
    high_threat: set[str] = set()
    high_by_time: dict[float, list[str]] = {}
    for frame in frames:
        frame_high: list[str] = []
        for obj in frame.truth_objects:
            if obj.object_type != "target":
                continue
            timestamps_by_id.setdefault(obj.object_id, []).append(float(frame.timestamp))
            if obj.threat_score >= 0.7:
                high_threat.add(obj.object_id)
                frame_high.append(obj.object_id)
        high_by_time[float(frame.timestamp)] = sorted(frame_high)
    timestamps = sorted({float(frame.timestamp) for frame in frames})
    resource_count = max((len(frame.resources) for frame in frames), default=len(config.resource_vehicle_names))
    camera_count = max((len(frame.cameras) for frame in frames), default=len(config.effective_camera_vehicle_names()))
    target_count = len(timestamps_by_id) or config.target_count()
    return {
        "truth_timestamps": {key: sorted(values) for key, values in timestamps_by_id.items()},
        "total_truth_opportunities": sum(len(values) for values in timestamps_by_id.values()),
        "high_threat_ids": sorted(high_threat),
        "high_threat_by_timestamp": high_by_time,
        "scenario": {
            "name": config.scenario_name,
            "group": config.scenario_name,
            "duration_s": config.duration_s,
            "dt_s": config.dt_s,
            "seed": config.seed,
            "frame_count": len(frames),
            "target_count": target_count,
            "resource_count": resource_count,
            "drone_count": resource_count,
            "camera_count": camera_count,
            "source": "main_episode_bus",
            "offline_only": False,
            "real_airsim_used": True,
            "scenario_version": _scenario_version(config, frames),
            "standard_mapping_version": STANDARD_MAPPING_VERSION,
        },
        "target_count": target_count,
        "resource_count": resource_count,
        "drone_count": resource_count,
        "camera_count": camera_count,
        "scenario_version": _scenario_version(config, frames),
        "standard_mapping_version": STANDARD_MAPPING_VERSION,
        "eval_priority": "P0-A",
        "implementation_status": "implemented",
        "timestamps": timestamps,
    }


def _scenario_version(config: BlocksSmokeConfig, frames: list[AirSimFrame] | None = None) -> str:
    resource_count = max(
        [len(config.resource_vehicle_names)]
        + [len(frame.resources) for frame in frames or ()]
    )
    target_count = max(
        [config.target_count()]
        + [
            sum(1 for obj in frame.truth_objects if obj.object_type == "target")
            for frame in frames or ()
        ]
    )
    camera_count = max(
        [len(config.effective_camera_vehicle_names())]
        + [len(frame.cameras) for frame in frames or ()]
    )
    backend = str(config.detection_backend or "airsim")
    return (
        f"{config.scenario_name}:resources{resource_count}:targets{target_count}:"
        f"cameras{camera_count}:seed{config.seed}:backend{backend}:v1"
    )


def _write_d6_episode_jsonl(
    truth_summary: dict[str, Any],
    collector: MetricsCollector,
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        stream.write(_json_record("truth_summary", truth_summary) + "\n")
        for record in collector.track_records:
            stream.write(_json_record("track", asdict(record)) + "\n")
        for record in collector.assignment_records:
            stream.write(_json_record("assignment", asdict(record)) + "\n")
        for record in collector.event_records:
            stream.write(_json_record("event", asdict(record)) + "\n")
        for record in collector.link_records:
            stream.write(_json_record("link", asdict(record)) + "\n")
        for record in collector.terminal_records:
            stream.write(_json_record("terminal", asdict(record)) + "\n")
    return path


def _write_ticks_jsonl(ticks: list[MainEpisodeBusTick], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for tick in ticks:
            stream.write(json.dumps(tick.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return path


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _json_record(record_type: str, payload: Any) -> str:
    return json.dumps(
        {"record_type": record_type, "payload": _jsonable(payload)},
        ensure_ascii=False,
        sort_keys=True,
    )


def _observation_summary(observation: SensorObservation) -> dict[str, Any]:
    return {
        "observation_id": observation.observation_id,
        "sensor_id": observation.sensor_id,
        "modality": observation.modality,
        "measurement_timestamp": observation.measurement_timestamp,
        "arrival_timestamp": observation.arrival_timestamp,
        "frame_id": observation.frame_id,
        "covariance_trace": None
        if observation.covariance is None
        else float(np.trace(observation.covariance)),
        "confidence": observation.confidence,
    }


def _plan_summary(plan: AssignmentPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "version": plan.version,
        "assignment_count": len(plan.assignments),
        "resource_count": plan.resource_count,
        "target_count": plan.target_count,
        "decision_state": plan.decision_state,
        "changed": plan.changed,
        "plan_schema": plan.metadata.get("plan_schema"),
        "active_plan_owner": plan.metadata.get("active_plan_owner", "center"),
        "owner_node_id": plan.metadata.get("owner_node_id"),
        "selected_secondary_node_id": plan.metadata.get("selected_secondary_node_id"),
        "supersedes_plan_id": plan.metadata.get("supersedes_plan_id"),
        "supersedes_plan_version": plan.metadata.get("supersedes_plan_version"),
        "assignments": [
            {
                "resource_id": assignment.resource_id,
                "global_track_id": assignment.target_id,
                "cost": assignment.cost,
            }
            for assignment in plan.assignments
        ],
    }


def _resource_vehicle_map(frame: AirSimFrame) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for resource in frame.resources:
        vehicle = resource.metadata.get("airsim_vehicle_name")
        if vehicle is not None:
            mapping[resource.resource_id] = str(vehicle)
    return mapping


def _target_alias_map(frame: AirSimFrame, d2_tracks: list[Any]) -> dict[str, Mapping[str, Any]]:
    d2_by_truth = {
        str(track.truth_id): track.global_track_id
        for track in d2_tracks
        if getattr(track, "truth_id", None) is not None
    }
    aliases: dict[str, Mapping[str, Any]] = {}
    for obj in frame.truth_objects:
        global_track_id = d2_by_truth.get(str(obj.object_id))
        if global_track_id is None:
            continue
        aliases[global_track_id] = {
            "target_object_id": obj.object_id,
            "target_actor_name": obj.metadata.get("airsim_actor_name"),
            "actor_name": obj.metadata.get("airsim_actor_name"),
            "actor_asset_name": obj.metadata.get("actor_asset_name"),
        }
    return aliases


def _local_tracks_for_resource(
    frame: AirSimFrame,
    resource_id: str,
    local_tracks: list[LocalVisualTrack],
) -> list[LocalVisualTrack]:
    vehicle_name = _resource_vehicle_map(frame).get(resource_id)
    if vehicle_name:
        scoped = [
            track
            for track in local_tracks
            if track.local_track_id.startswith(f"{vehicle_name}:")
        ]
        if scoped:
            return scoped
    return local_tracks


def _camera_id_for_resource(frame: AirSimFrame, resource_id: str) -> str | None:
    vehicle = _resource_vehicle_map(frame).get(resource_id)
    if vehicle is None:
        return None
    for camera in frame.cameras:
        if camera.owner_id == vehicle:
            return camera.camera_id
    return f"{vehicle}:0"


def _camera_for_resource(
    frame: AirSimFrame,
    resource_id: str,
    global_track_id: str,
    terminal_tracks: list[Any],
) -> CameraModel:
    vehicle_name = _resource_vehicle_map(frame).get(resource_id)
    if vehicle_name is not None:
        for camera in frame.cameras:
            if camera.owner_id == vehicle_name:
                return camera_model_from_airsim_camera_info(camera, measurement_sigma_px=12.0)
    resource = next((item for item in frame.resources if item.resource_id == resource_id), None)
    track = next((item for item in terminal_tracks if item.global_track_id == global_track_id), None)
    camera_position = np.asarray(
        resource.position_ned if resource is not None else (0.0, 0.0, 0.0),
        dtype=float,
    )
    target_position = np.asarray(
        track.position if track is not None else camera_position + np.array([30.0, 0.0, 0.0]),
        dtype=float,
    )
    rotation = _look_at_world_to_camera(camera_position, target_position)
    return CameraModel(
        K=np.array([[320.0, 0.0, 320.0], [0.0, 320.0, 240.0], [0.0, 0.0, 1.0]], dtype=float),
        R=rotation,
        t=-rotation @ camera_position,
        image_size=(640, 480),
        measurement_cov=np.diag([16.0, 16.0]),
    )


def _recon_cues_for_assignment(
    frame: AirSimFrame,
    resource_id: str,
    global_track_id: str,
    terminal_tracks: list[Any],
    camera: CameraModel,
    terminal: TerminalAssociator,
) -> tuple[ReconImageCue, ...]:
    if not _secondary_available(frame):
        return ()
    if not frame.metadata.get("secondary_camera_vehicle_names"):
        return ()
    projections = terminal.project_tracks_to_image(terminal_tracks, camera, timestamp=frame.timestamp)
    projection = projections.get(global_track_id)
    if projection is None or not projection.valid or projection.pixel is None:
        return ()
    return (
        ReconImageCue(
            cue_id=f"main-bus-cue-{resource_id}-{global_track_id}-{frame.frame_index}",
            producer_node_id=str(frame.metadata.get("secondary_camera_vehicle_names", ["SEC-01"])[0]),
            timestamp=float(frame.timestamp),
            image_frame_id=f"{resource_id}:0",
            global_track_id=global_track_id,
            center_px=projection.pixel,
            confidence=0.75,
            scoped_resource_ids=(resource_id,),
            metadata={
                "source": "main_runtime_secondary_recon_cue",
                "reprojected_to_local_camera": True,
            },
        ),
    )


def _secondary_available(frame: AirSimFrame) -> bool:
    if not frame.secondary_nodes_alive:
        return False
    secondary_names = frame.metadata.get("secondary_camera_vehicle_names", ())
    return bool(secondary_names) or bool(frame.secondary_nodes_alive)


def _secondary_takeover_source_node_id(
    frame: AirSimFrame,
    secondary_takeover: Mapping[str, Any],
    *,
    previous_plan: AssignmentPlan | None,
) -> str:
    secondary_names = [
        str(name)
        for name in frame.metadata.get("secondary_camera_vehicle_names", ())
        if str(name).strip()
    ]
    valid_names = set(secondary_names)
    previous_owner = None
    if previous_plan is not None and previous_plan.metadata.get("active_plan_owner") == "secondary":
        previous_owner = (
            previous_plan.metadata.get("owner_node_id")
            or previous_plan.metadata.get("selected_secondary_node_id")
            or previous_plan.metadata.get("source_node_id")
        )
    candidates = (
        secondary_takeover.get("target_node_id"),
        secondary_takeover.get("selected_secondary_node_id"),
        secondary_takeover.get("secondary_plan_source_node_id"),
        secondary_takeover.get("source_node_id"),
        previous_owner,
        secondary_takeover.get("selected_coordinator"),
        secondary_names[0] if secondary_names else None,
    )
    for candidate in candidates:
        if candidate is None:
            continue
        node_id = str(candidate).strip()
        if not node_id:
            continue
        if valid_names and node_id not in valid_names:
            continue
        if node_id.lower() in {"center", "d3_central", "central", "secondary_node"}:
            continue
        return node_id
    return secondary_names[0] if secondary_names else "SEC-NORTH"


def _d4_permission(d4_result: Any | None) -> D4GuidancePermission:
    if d4_result is None:
        return D4GuidancePermission()
    record = d4_result.record
    metadata = record.to_event_metadata()
    action = record.action.value
    if (
        action == "degrade_to_secondary"
        and metadata.get("secondary_takeover_state") == "secondary_plan_active"
        and metadata.get("secondary_plan_id") is not None
        and metadata.get("secondary_plan_version") is not None
    ):
        action = "request_secondary_assist"
    return D4GuidancePermission(
        action=action,
        mode=record.mode.value,
        reason=record.reason,
        target_node_id=record.target_node_id or metadata.get("secondary_plan_source_node_id"),
        terminal_consistent=record.terminal_consistent,
        requires_human_review=record.requires_human_review,
        new_plan_id=metadata.get("secondary_plan_id"),
        new_plan_version=metadata.get("secondary_plan_version"),
        metadata=metadata,
    )


def _binding_for_d7(binding: Any) -> dict[str, Any]:
    if hasattr(binding, "to_assignment_metadata"):
        payload = dict(binding.to_assignment_metadata())
    else:
        payload = dict(_jsonable(binding))
    metadata = dict(payload.get("metadata") or {})
    payload.setdefault("owner_node_id", metadata.get("owner_node_id") or payload.get("source_node_id"))
    payload.setdefault("vehicle_name", payload.get("resource_actor_name") or payload.get("resource_id"))
    payload.setdefault("authorization_state", payload.get("human_authorization_state", "recorded"))
    payload.setdefault("assignment_validity_state", payload.get("assignment_validity_state", "current"))
    return payload


def _vision_observation_for_d7(
    terminal_association: TerminalAssociation | None,
    terminal_contexts: Iterable[_TerminalDecisionContext],
    resource_id: str,
    target_id: str,
    timestamp: float,
) -> dict[str, Any] | None:
    if terminal_association is None:
        return None
    context = next(
        (
            item
            for item in terminal_contexts
            if item.assignment.resource_id == resource_id and item.assignment.target_id == target_id
        ),
        None,
    )
    if context is None or context.local_track is None or context.local_track.bbox is None:
        return None
    local_track = context.local_track
    metadata = dict(terminal_association.metadata)
    return {
        "timestamp_s": float(local_track.timestamp),
        "frame_timestamp_s": float(timestamp),
        "bbox_xyxy": tuple(local_track.bbox),
        "detection_confidence": float(local_track.quality),
        "local_track_id": local_track.local_track_id,
        "assigned_global_track_id": terminal_association.assigned_global_track_id,
        "camera_id": metadata.get("camera_id"),
        "measurement_age_s": max(0.0, float(timestamp) - float(local_track.timestamp)),
        "metadata": {
            "source": "main_d5_local_visual_track",
            "measurement_age_s": max(0.0, float(timestamp) - float(local_track.timestamp)),
            "visual_png_handoff_recommended": metadata.get("visual_png_handoff_recommended"),
            "visual_png_handoff_blockers": metadata.get("visual_png_handoff_blockers"),
        },
    }


def _relative_position_resource_to_track(
    resource: ResourcePlatform,
    track: Any,
) -> tuple[float, float, float]:
    resource_position = np.asarray(resource.position, dtype=float)
    target_position = np.asarray(
        [track.state[0], track.state[1], resource_position[2]],
        dtype=float,
    )
    relative = target_position - resource_position
    return (float(relative[0]), float(relative[1]), float(relative[2]))


def _relative_velocity_resource_to_track(
    resource: ResourcePlatform,
    track: Any,
) -> tuple[float, float, float]:
    resource_velocity = np.asarray(getattr(resource, "velocity", (0.0, 0.0, 0.0)), dtype=float)
    target_velocity = np.asarray([track.state[2], track.state[3], 0.0], dtype=float)
    relative = target_velocity - resource_velocity
    return (float(relative[0]), float(relative[1]), float(relative[2]))


def _pn_command_for_pair(
    *,
    timestamp: float,
    mode: GuidanceMode,
    resource: ResourcePlatform,
    track: Any,
    speed_mps: float,
    dt_s: float,
    navigation_constant: float,
) -> Any:
    resource_position = np.asarray(resource.position, dtype=float)
    target_position = np.asarray([track.state[0], track.state[1], 0.0], dtype=float)
    target_velocity = np.asarray([track.state[2], track.state[3]], dtype=float)
    resource_velocity = np.asarray([0.0, 0.0], dtype=float)
    relative = target_position[:2] - resource_position[:2]
    distance = float(np.linalg.norm(relative))
    if distance > 1e-6:
        resource_velocity = relative / distance * speed_mps
    pursuer = GuidanceState(
        entity_id=resource.resource_id,
        timestamp_s=timestamp,
        position_m=(float(resource_position[0]), float(resource_position[1])),
        velocity_mps=(float(resource_velocity[0]), float(resource_velocity[1])),
        source="airsim_resource_state",
    )
    target = GuidanceState(
        entity_id=track.global_track_id,
        timestamp_s=timestamp,
        position_m=(float(track.state[0]), float(track.state[1])),
        velocity_mps=(float(target_velocity[0]), float(target_velocity[1])),
        source="d2_global_track",
        covariance_trace=float(np.trace(track.covariance)),
        metadata={"truth_id": getattr(track, "truth_id", None)},
    )
    return compute_pn_command(
        pursuer=pursuer,
        target=target,
        dt_s=dt_s,
        navigation_constant=navigation_constant,
        mode=mode,
        max_lateral_accel_mps2=45.0,
        max_turn_rate_radps=0.9,
    )


def _range_resource_to_track(resource: ResourcePlatform, track: Any) -> float:
    resource_position = np.asarray(resource.position, dtype=float)
    target_position = np.asarray([track.state[0], track.state[1], resource_position[2]], dtype=float)
    return float(np.linalg.norm(target_position - resource_position))


def _range_for_terminal_context(
    frame: AirSimFrame,
    resource_id: str,
    track: Any | None,
) -> float | None:
    if track is None:
        return None
    resource = next((item for item in frame.resources if item.resource_id == resource_id), None)
    if resource is None:
        return None
    resource_platform = ResourcePlatform(
        resource_id=resource.resource_id,
        position=np.asarray(resource.position_ned, dtype=float),
        coverage_cell=resource.coverage_cell,
        health_score=resource.health_score,
        status=resource.status,
    )
    return _range_resource_to_track(resource_platform, track)


def _terminal_feedback_metadata(
    *,
    assignment: Any,
    decision: TerminalAssociation,
    consistency: Any | None,
    local_track: LocalVisualTrack | None,
) -> dict[str, Any]:
    consistency_metadata = (
        consistency.to_metadata()
        if consistency is not None and hasattr(consistency, "to_metadata")
        else {}
    )
    decision_metadata = dict(decision.metadata)
    duplicate_risk = bool(
        consistency_metadata.get("duplicate_terminal_lock_risk")
        or decision_metadata.get("duplicate_terminal_lock_risk")
    )
    friend_conflict = decision.friend_conflict_state != "none"
    consistency_state = str(consistency_metadata.get("consistency_state", "unknown"))
    terminal_state = _terminal_feedback_state(
        decision.decision_state,
        consistency_state=consistency_state,
        duplicate_risk=duplicate_risk,
        friend_conflict=friend_conflict,
    )
    recommended_action = _terminal_feedback_action(terminal_state, duplicate_risk)
    metadata: dict[str, Any] = {
        "source": "main_airsim_episode_bus_d5_feedback",
        "target_id": assignment.target_id,
        "global_track_id": assignment.target_id,
        "assigned_global_track_id": decision.assigned_global_track_id,
        "resource_id": assignment.resource_id,
        "terminal_feedback_state": terminal_state,
        "recommended_action": recommended_action,
        "main_action": recommended_action,
        "d7_gate_action": "hold" if recommended_action != "continue" else "continue",
        "allow_local_rebind": False,
        "duplicate_terminal_lock_risk": duplicate_risk,
        "friend_conflict_state": decision.friend_conflict_state,
        "decision_state": decision.decision_state,
        "association_confidence": decision.association_confidence,
        "ambiguity_score": decision.ambiguity_score,
        "local_track_id": decision.local_track_id,
        "visual_png_handoff_recommended": decision_metadata.get(
            "visual_png_handoff_recommended"
        ),
        "visual_png_handoff_blockers": decision_metadata.get(
            "visual_png_handoff_blockers"
        ),
        "measurement_age_s": decision_metadata.get("measurement_age_s"),
        "consistency": consistency_metadata,
    }
    if local_track is not None:
        metadata["bbox_xyxy"] = list(local_track.bbox) if local_track.bbox is not None else None
        metadata["local_track_quality"] = local_track.quality
    if duplicate_risk or friend_conflict:
        metadata["d4_request"] = "secondary_arbitration"
        metadata["prohibit_assignment_suggested"] = True
        metadata["prohibited_edges"] = (
            {"target_id": assignment.target_id, "resource_id": assignment.resource_id},
        )
    elif decision.decision_state == "hold":
        metadata["operator_hold_suggested"] = True
    if (
        recommended_action != "continue"
        and not bool(decision_metadata.get("visual_png_gate_pass", False))
    ):
        metadata["fov_difficulty_suggestion"] = "increase_current_edge"
    return metadata


def _terminal_feedback_state(
    decision_state: str,
    *,
    consistency_state: str,
    duplicate_risk: bool,
    friend_conflict: bool,
) -> str:
    if duplicate_risk:
        return "cross_view_conflict"
    if friend_conflict:
        return "friend_overlap_hold"
    if consistency_state == "conflict":
        return "cross_view_conflict"
    if decision_state == "hold":
        return decision_state
    return "consistent"


def _terminal_feedback_action(terminal_state: str, duplicate_risk: bool) -> str:
    if duplicate_risk or terminal_state in {"cross_view_conflict", "mismatch", "multi_frame_inconsistent"}:
        return "secondary_arbitration"
    if terminal_state in {"hold", "friend_overlap_hold"}:
        return "hold"
    return "continue"


def _non_locked_count(consistency: Any | None) -> int:
    if consistency is None:
        return 0
    return int(
        getattr(consistency, "consecutive_ambiguous_frames", 0)
        + getattr(consistency, "consecutive_hold_frames", 0)
        + getattr(consistency, "consecutive_reacquire_frames", 0)
    )


def _local_track_by_id(
    local_tracks: Iterable[LocalVisualTrack],
    local_track_id: str | None,
) -> LocalVisualTrack | None:
    if local_track_id is None:
        return None
    for track in local_tracks:
        if track.local_track_id == local_track_id:
            return track
    return None


def _look_at_world_to_camera(camera_position: np.ndarray, target_position: np.ndarray) -> np.ndarray:
    forward = _unit_vector(target_position - camera_position, fallback=np.array([1.0, 0.0, 0.0]))
    up_hint = np.array([0.0, 0.0, -1.0], dtype=float)
    right = np.cross(up_hint, forward)
    if np.linalg.norm(right) < 1e-9:
        right = np.cross(np.array([0.0, 1.0, 0.0], dtype=float), forward)
    right = _unit_vector(right, fallback=np.array([0.0, 1.0, 0.0]))
    camera_y = _unit_vector(np.cross(forward, right), fallback=np.array([0.0, 0.0, -1.0]))
    return np.vstack([right, camera_y, forward])


def _unit_vector(vector: np.ndarray, *, fallback: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm <= 1e-9:
        return fallback.astype(float)
    return np.asarray(vector, dtype=float) / norm


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value
