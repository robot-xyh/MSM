"""End-to-end D1-D6 offline point-mass integration runner."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import numpy as np

from d1_sensor_fusion import FusionAdapter, SensorObservation
from d1_sensor_fusion.observations import (
    CameraModel as D1CameraModel,
    acoustic_covariance,
    acoustic_h,
    eo_covariance_from_bbox,
    eo_project,
    radar_covariance_from_range,
    radar_h,
)
from d2_data_association import GNNHungarianAssociator, Tracker
from d3_assignment_planner import (
    AssignmentPlan,
    AssignmentPlanner,
    CostModel,
    CostWeights,
    PlannerConfig,
    StalePlanError,
    TargetDemand,
)
from d3_assignment_planner.solver import HungarianAssignmentSolver
from d4_distributed_fallback.active_degradation import (
    ActiveDegradationArbiter,
    DegradationAction,
    DegradationMode,
)
from d4_distributed_fallback.cbba import CBBANegotiator
from d4_distributed_fallback.coordinator import FailoverCoordinator
from d4_distributed_fallback.models import C2Health
from d4_distributed_fallback.network import SimulatedNetwork
from d5_terminal_association import (
    AssociationConfig,
    CameraModel,
    IdentityChecker,
    LocalVisualTrack,
    ReconImageCue,
    TerminalAssociator,
)
from d6_evaluation_metrics import EventRecord, MetricsCollector
from d7_proportional_guidance import (
    GuidanceConfig,
    GuidanceMode,
    GuidanceState,
    simulate_guidance_episode,
)

from .adapters import (
    association_risk_summary,
    assignment_validity_summary,
    d1_tracks_to_d2_detections,
    d2_tracks_to_d4_tasks,
    d2_tracks_to_terminal_tracks,
    d2_tracks_to_target_tracks,
    jsonable_dataclass,
    plan_to_assignment_records,
    plan_to_m_to_n_records,
    plan_to_terminal_assignments,
    resources_to_d3,
    resources_to_d4,
    terminal_summary_from_record,
    terminal_to_record,
    track_records_from_d2,
    track_uncertainty_summary,
)
from .models import EpisodeResult, IntegratedDecisionRecord, ResourcePlatform, ScenarioConfig, TruthState
from .reporting import write_episode_outputs
from .scenario import generate_resource_platforms, generate_truth_states, truth_summary_for


class IntegratedEpisodeRunner:
    """Coordinate D1-D6 modules in one synthetic offline episode."""

    def __init__(
        self,
        config: ScenarioConfig,
        observation_provider: Callable[[float], list[SensorObservation]] | None = None,
        truth_provider: Callable[[float], Sequence[TruthState]] | None = None,
        resources_provider: Callable[[float], Sequence[ResourcePlatform]] | None = None,
        truth_summary_provider: Callable[[], dict[str, Any]] | None = None,
        terminal_visual_provider: Callable[..., tuple[list[LocalVisualTrack], dict[str, str]] | None]
        | None = None,
        terminal_camera: CameraModel | None = None,
    ) -> None:
        self.config = config
        self.observation_provider = observation_provider
        self.truth_provider = truth_provider
        self.resources_provider = resources_provider
        self.truth_summary_provider = truth_summary_provider
        self.terminal_visual_provider = terminal_visual_provider
        self.rng = np.random.default_rng(config.seed)
        self.resources = list(
            resources_provider(0.0) if resources_provider is not None else generate_resource_platforms(config)
        )
        self.collector = MetricsCollector()
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
            min_dwell=2.0,
            human_authorization_state="recorded",
        )
        weights = CostWeights(
            window=0.2,
            covariance=0.3,
            threat=0.5,
            resource_state=0.4,
            fov=2.2,
            conflict=0.6,
        )
        self.assignment_planner = AssignmentPlanner(
            cost_model=CostModel(weights=weights, config=planner_config),
            solver=HungarianAssignmentSolver(allow_scipy=True),
            config=planner_config,
        )
        self.failover = FailoverCoordinator(
            node_id="MAIN-C2",
            peer_ids=[resource.resource_id for resource in self.resources],
            heartbeat_failure_s=1.0,
        )
        self.arbiter = ActiveDegradationArbiter()
        self.terminal = TerminalAssociator(
            AssociationConfig(
                gate_chi2=16.0,
                min_lock_margin=1.0,
                max_lock_cost=18.0,
                image_margin_px=12.0,
            ),
            identity_checker=IdentityChecker(friendly_platform_ids={"FRIEND-01"}),
        )
        self.d1_camera = D1CameraModel(
            position_ned=np.zeros(3),
            rotation_world_to_camera=np.eye(3),
            fx=320.0,
            fy=320.0,
            cx=640.0,
            cy=360.0,
            width=1280,
            height=720,
        )
        self.terminal_camera = terminal_camera or CameraModel(
            K=np.array([[320.0, 0.0, 640.0], [0.0, 320.0, 360.0], [0.0, 0.0, 1.0]]),
            R=np.eye(3),
            t=np.zeros(3),
            image_size=(1280, 720),
            measurement_cov=np.diag([4.0, 4.0]),
        )
        self.current_plan: AssignmentPlan | None = None
        self.last_association_ambiguity = 0.0
        self.decisions: list[IntegratedDecisionRecord] = []
        self._terminal_non_locked: dict[tuple[str, str], int] = defaultdict(int)
        self._terminal_mismatch: dict[tuple[str, str], int] = defaultdict(int)
        self._terminal_entries: set[tuple[str, str]] = set()
        self._terminal_locks: set[tuple[str, str]] = set()
        self._degradation_keys: set[tuple[str, str, str]] = set()
        self.guidance_records: list[Any] = []
        self.guidance_summaries: list[dict[str, Any]] = []
        self._guidance_plan_keys: set[tuple[str, int | str]] = set()
        self._central_failure_recorded = False

    def run(self, output_dir: str | Path | None = None) -> EpisodeResult:
        truth_summary = (
            self.truth_summary_provider()
            if self.truth_summary_provider is not None
            else truth_summary_for(self.config)
        )
        for timestamp in self.config.timestamps():
            if self.resources_provider is not None:
                self.resources = list(self.resources_provider(timestamp))
            truth_states = self._truth_states(timestamp)
            truth_by_id = {state.truth_id: state for state in truth_states}
            self._process_d1_observations(timestamp)
            d1_tracks = self.fusion.global_tracks()
            detections = d1_tracks_to_d2_detections(d1_tracks, timestamp)
            association_result = self.tracker.step(
                detections,
                timestamp=timestamp,
                truth_ids_present=[state.truth_id for state in truth_states],
            )
            self.last_association_ambiguity = association_result.ambiguity_score
            d2_tracks = self.tracker.active_tracks()
            self.collector.extend_tracks(track_records_from_d2(d2_tracks, truth_by_id, timestamp))

            if self._should_plan(timestamp):
                self._run_assignment(timestamp, d2_tracks, truth_by_id)

            self._record_central_failure_if_due(timestamp)
            if self.current_plan is not None and timestamp >= self.config.terminal_start_s:
                self._run_terminal_and_degradation(timestamp, d2_tracks, truth_by_id)

        metrics = self.collector.compute_episode(
            episode_id=self.config.name,
            seed=self.config.seed,
            duration=self.config.duration_s,
            truth_summary=truth_summary,
        )
        result = EpisodeResult(
            scenario=self.config,
            metrics=metrics,
            truth_summary=truth_summary,
            decisions=self.decisions,
            guidance_records=self.guidance_records,
            guidance_summaries=self.guidance_summaries,
            metadata={
                "offline_only": True,
                "d2_metrics": self.tracker.metrics.summary(),
                "guidance_summary_count": len(self.guidance_summaries),
                "guidance_record_count": len(self.guidance_records),
                "record_counts": {
                    "tracks": len(self.collector.track_records),
                    "assignments": len(self.collector.assignment_records),
                    "events": len(self.collector.event_records),
                    "terminals": len(self.collector.terminal_records),
                },
            },
        )
        if output_dir is not None:
            result.output_paths = write_episode_outputs(result, self.collector, Path(output_dir))
        return result

    def _process_d1_observations(self, timestamp: float) -> None:
        if self.observation_provider is not None:
            observations = self.observation_provider(timestamp)
            observations.sort(key=lambda obs: (obs.arrival_timestamp, obs.modality, obs.observation_id))
            for observation in observations:
                self.fusion.process(observation)
            return

        measurement_time = max(0.0, timestamp - self.config.radar_latency_s)
        truth_states = self._truth_states(measurement_time)
        observations: list[SensorObservation] = []
        for index, truth in enumerate(truth_states):
            state = np.concatenate([truth.position, truth.velocity])
            distance = max(float(np.linalg.norm(truth.position)), 1.0)
            radar_cov = radar_covariance_from_range(distance) * self.config.radar_noise_scale
            radar_noise = self.rng.multivariate_normal(np.zeros(4), radar_cov)
            observations.append(
                SensorObservation(
                    observation_id=f"radar-{truth.truth_id}-{timestamp:.2f}",
                    sensor_id="RADAR-GND-01",
                    modality="radar",
                    measurement_timestamp=measurement_time,
                    arrival_timestamp=timestamp,
                    frame_id="ned",
                    measurement=radar_h(state, np.zeros(3)) + radar_noise,
                    covariance=radar_cov,
                    classification_hint="uav",
                    confidence=0.92,
                    metadata={"truth_id": truth.truth_id, "sensor_position_ned": [0.0, 0.0, 0.0]},
                )
            )
            if self.config.acoustic_enabled:
                acoustic_cov = acoustic_covariance(0.75)
                acoustic_noise = self.rng.multivariate_normal(np.zeros(1), acoustic_cov)
                observations.append(
                    SensorObservation(
                        observation_id=f"acoustic-{truth.truth_id}-{timestamp:.2f}",
                        sensor_id="ACOUSTIC-01",
                        modality="acoustic",
                        measurement_timestamp=measurement_time,
                        arrival_timestamp=timestamp,
                        frame_id="ned",
                        measurement=acoustic_h(state, np.zeros(3)) + acoustic_noise,
                        covariance=acoustic_cov,
                        classification_hint="uav_sound",
                        confidence=0.75,
                        metadata={"truth_id": truth.truth_id, "sensor_position_ned": [0.0, 0.0, 0.0]},
                    )
                )
            if self.config.eo_enabled:
                pixel = eo_project(state, self.d1_camera)
                bbox = np.array([pixel[0] - 5.0, pixel[1] - 5.0, pixel[0] + 5.0, pixel[1] + 5.0])
                eo_cov = eo_covariance_from_bbox(bbox, 0.85, ())
                eo_noise = self.rng.multivariate_normal(np.zeros(2), eo_cov)
                observations.append(
                    SensorObservation(
                        observation_id=f"eo-{truth.truth_id}-{timestamp:.2f}",
                        sensor_id="EO-GND-01",
                        modality="eo",
                        measurement_timestamp=measurement_time,
                        arrival_timestamp=timestamp,
                        frame_id="pixel",
                        measurement=pixel + eo_noise,
                        covariance=eo_cov,
                        classification_hint="uav_visual",
                        confidence=0.85,
                        metadata={
                            "truth_id": truth.truth_id,
                            "camera_model": self.d1_camera,
                            "bbox": bbox.tolist(),
                        },
                    )
                )
            del index

        observations.sort(key=lambda obs: (obs.arrival_timestamp, obs.modality, obs.observation_id))
        for observation in observations:
            self.fusion.process(observation)

    def _should_plan(self, timestamp: float) -> bool:
        if self.current_plan is None:
            return True
        quotient = timestamp / self.config.assignment_period_s
        return abs(quotient - round(quotient)) < 1e-9

    def _run_assignment(
        self,
        timestamp: float,
        d2_tracks: list[Any],
        truth_by_id: dict[str, TruthState],
    ) -> None:
        target_tracks = d2_tracks_to_target_tracks(d2_tracks, truth_by_id, self.resources)
        if self.config.cooperative_demand_enabled:
            selected_ids = {
                item.track_id
                for item in sorted(target_tracks, key=lambda value: value.track_id)[
                    : self.config.cooperative_high_threat_target_count
                ]
            }
            target_tracks = [
                replace(
                    item,
                    demand=TargetDemand(
                        required_resource_count=self.config.high_threat_required_resource_count,
                        coordination_mode=self.config.cooperative_coordination_mode,
                        primary_resource_count=self.config.cooperative_primary_count,
                        arrival_window_start_s=timestamp,
                        arrival_window_end_s=timestamp
                        + self.config.cooperative_wave_gap_s,
                        wave_interval_s=self.config.cooperative_wave_gap_s,
                        minimum_separation_s=self.config.cooperative_minimum_separation_s,
                        metadata={"source": "offline_truth_threat_fixture"},
                    ),
                )
                if item.track_id in selected_ids
                else item
                for item in target_tracks
            ]
        if not target_tracks:
            return
        previous_plan = self.current_plan
        try:
            plan = self.assignment_planner.plan(
                target_tracks,
                resources_to_d3(self.resources),
                timestamp=timestamp,
                previous_plan=previous_plan,
                expected_previous_version=None if previous_plan is None else previous_plan.version,
            )
        except StalePlanError as error:
            if previous_plan is None:
                raise
            self.collector.add_event(
                EventRecord(
                    timestamp=timestamp,
                    event_type="d3_stale_plan_rejected",
                    actor_id="D3",
                    severity="warning",
                    note=str(error),
                    metadata={
                        **error.to_metadata(),
                        "retained_plan_id": previous_plan.plan_id,
                        "retained_plan_version": previous_plan.version,
                        "retry_policy": "retain_current_plan_and_retry_next_cycle",
                    },
                )
            )
            return
        self.current_plan = plan
        d2_by_id = {track.global_track_id: track for track in d2_tracks}
        self.collector.extend_assignments(plan_to_assignment_records(plan, d2_by_id))
        demand_records, coalition_records = plan_to_m_to_n_records(plan)
        self.collector.extend_target_demands(demand_records)
        self.collector.extend_coalitions(coalition_records)
        if previous_plan is None or plan.changed:
            self._simulate_guidance_for_plan(
                timestamp=timestamp,
                plan=plan,
                d2_by_id=d2_by_id,
                truth_by_id=truth_by_id,
                source="d3_initial_assignment" if previous_plan is None else "d3_reassignment",
            )

    def _record_central_failure_if_due(self, timestamp: float) -> None:
        failure_time = self.config.c2_failure_time_s
        if failure_time is None or timestamp < failure_time or self._central_failure_recorded:
            return
        self._central_failure_recorded = True
        self.failover.health = C2Health.FAILED
        self.collector.add_event(
            EventRecord(
                timestamp=timestamp,
                event_type="central_failure",
                actor_id="MAIN-C2",
                severity="warning",
                note="Offline injected C2 failure for failover evaluation.",
            )
        )

    def _run_terminal_and_degradation(
        self,
        timestamp: float,
        d2_tracks: list[Any],
        truth_by_id: dict[str, TruthState],
    ) -> None:
        if self.current_plan is None:
            return
        d2_by_id = {track.global_track_id: track for track in d2_tracks}
        terminal_tracks = d2_tracks_to_terminal_tracks(
            d2_tracks,
            truth_by_id,
            plan_version=self.current_plan.version,
            timestamp=timestamp,
        )
        terminal_assignments = plan_to_terminal_assignments(self.current_plan)
        if not terminal_tracks or not terminal_assignments:
            return

        assigned_ids = {assignment.assigned_global_track_id for assignment in terminal_assignments}
        provided_local_tracks = (
            self.terminal_visual_provider(
                timestamp=timestamp,
                terminal_tracks=terminal_tracks,
                terminal_assignments=terminal_assignments,
                d2_tracks=d2_tracks,
                truth_by_id=truth_by_id,
                terminal_associator=self.terminal,
                terminal_camera=self.terminal_camera,
            )
            if self.terminal_visual_provider is not None
            else None
        )
        if provided_local_tracks is None:
            local_tracks, local_truth_map = self._make_local_visual_tracks(
                terminal_tracks,
                timestamp,
                assigned_ids=assigned_ids,
            )
        else:
            local_tracks, local_truth_map = provided_local_tracks
        claims = self._make_identity_claims(local_tracks, timestamp)
        cues = self._make_recon_cues(terminal_tracks, terminal_assignments, timestamp)

        for terminal_assignment in terminal_assignments:
            resource_id = terminal_assignment.resource_id or "unknown_resource"
            scoped_local_tracks = self._local_tracks_for_resource(local_tracks, resource_id)
            decision = self.terminal.decide(
                terminal_assignment,
                terminal_tracks,
                scoped_local_tracks,
                identity_claims=claims,
                camera=self.terminal_camera,
                current_time=timestamp,
                recon_image_cues=cues,
            )
            key = (resource_id, terminal_assignment.assigned_global_track_id)
            observed_global_track_id = (
                local_truth_map.get(decision.local_track_id)
                if decision.local_track_id is not None
                else None
            )
            if decision.decision_state != "locked":
                self._terminal_non_locked[key] += 1
            else:
                self._terminal_non_locked[key] = 0
            if (
                observed_global_track_id is not None
                and observed_global_track_id != terminal_assignment.assigned_global_track_id
            ):
                self._terminal_mismatch[key] += 1
            else:
                self._terminal_mismatch[key] = 0
            if key not in self._terminal_entries:
                self._terminal_entries.add(key)
                self.collector.add_event(
                    EventRecord(
                        timestamp=timestamp,
                        event_type="terminal_fov_entry",
                        actor_id=resource_id,
                        metadata={"assigned_global_track_id": terminal_assignment.assigned_global_track_id},
                    )
                )
            if decision.decision_state == "locked" and key not in self._terminal_locks:
                self._terminal_locks.add(key)
                self.collector.add_event(
                    EventRecord(
                        timestamp=timestamp,
                        event_type="terminal_lock",
                        actor_id=resource_id,
                        metadata={
                            "assigned_global_track_id": terminal_assignment.assigned_global_track_id,
                            "local_track_id": decision.local_track_id,
                        },
                    )
                )
            terminal_record = terminal_to_record(
                timestamp=timestamp,
                resource_id=resource_id,
                assigned_global_track_id=terminal_assignment.assigned_global_track_id,
                local_track_id=decision.local_track_id,
                decision_state=decision.decision_state,
                ambiguity_score=decision.ambiguity_score,
                friend_conflict_state=decision.friend_conflict_state,
                assignment_version=decision.assignment_version,
                observed_global_track_id=observed_global_track_id,
                authorization_state=decision.authorization_state,
                coordination_mode=decision.coordination_mode,
                coalition_id=decision.coalition_id,
                coalition_version=decision.coalition_version,
                coalition_state=next(
                    (
                        item.state
                        for item in self.current_plan.coalitions
                        if item.target_id == decision.assigned_global_track_id
                    ),
                    None,
                ),
                member_role=decision.member_role,
                wave_id=decision.wave_id,
                required_resource_count=decision.required_resource_count,
                arrival_window_start=decision.arrival_window_start_s,
                arrival_window_end=decision.arrival_window_end_s,
                minimum_member_separation=next(
                    (
                        item.minimum_separation_s
                        for item in self.current_plan.coalitions
                        if item.target_id == decision.assigned_global_track_id
                    ),
                    None,
                ),
            )
            self.collector.add_terminal(terminal_record)
            self._evaluate_degradation(
                timestamp=timestamp,
                resource_id=resource_id,
                assigned_global_track_id=terminal_assignment.assigned_global_track_id,
                d2_track=d2_by_id.get(terminal_assignment.assigned_global_track_id),
                truth_by_id=truth_by_id,
                terminal_decision=decision,
                observed_global_track_id=observed_global_track_id,
                non_locked_count=self._terminal_non_locked[key],
                mismatch_count=self._terminal_mismatch[key],
            )

    @staticmethod
    def _local_tracks_for_resource(
        local_tracks: list[LocalVisualTrack],
        resource_id: str,
    ) -> list[LocalVisualTrack]:
        scoped = [
            track
            for track in local_tracks
            if track.local_track_id.startswith(f"{resource_id}:")
        ]
        return scoped or local_tracks

    def _make_local_visual_tracks(
        self,
        terminal_tracks: list[Any],
        timestamp: float,
        assigned_ids: set[str],
    ) -> tuple[list[LocalVisualTrack], dict[str, str]]:
        projections = self.terminal.project_tracks_to_image(
            terminal_tracks,
            self.terminal_camera,
            timestamp=timestamp,
        )
        tracks: list[LocalVisualTrack] = []
        local_truth_map: dict[str, str] = {}
        alternate_id = next((track.global_track_id for track in terminal_tracks), None)
        for track in terminal_tracks:
            projection = projections.get(track.global_track_id)
            if projection is None or not projection.valid or projection.pixel is None:
                continue
            center = projection.pixel + self.rng.normal(0.0, self.config.visual_noise_px, size=2)
            local_truth_id = track.global_track_id
            local_id = f"L-{track.global_track_id}"
            if (
                self.config.active_mismatch_start_s is not None
                and timestamp >= self.config.active_mismatch_start_s
                and track.global_track_id in assigned_ids
                and alternate_id is not None
            ):
                alternatives = [item.global_track_id for item in terminal_tracks if item.global_track_id != track.global_track_id]
                if alternatives:
                    local_truth_id = alternatives[0]
                    local_id = f"L-MISMATCH-{track.global_track_id}"
            bbox = (
                float(center[0] - 5.0),
                float(center[1] - 5.0),
                float(center[0] + 5.0),
                float(center[1] + 5.0),
            )
            local = LocalVisualTrack(
                local_track_id=local_id,
                center_px=center,
                bbox=bbox,
                bearing_rate=projection.predicted_px_velocity,
                category="uav",
                quality=0.96,
                mot_history_length=5,
                timestamp=timestamp,
            )
            tracks.append(local)
            local_truth_map[local_id] = local_truth_id
        return tracks, local_truth_map

    def _make_identity_claims(self, local_tracks: list[LocalVisualTrack], timestamp: float) -> list[Any]:
        if self.config.friend_overlap_start_s is None or timestamp < self.config.friend_overlap_start_s:
            return []
        if not local_tracks:
            return []
        local = local_tracks[0]
        return self.terminal.identity_checker.parse_claims(
            [
                {
                    "protocol": "OpenDroneID",
                    "platform_id": "FRIEND-01",
                    "local_track_id": local.local_track_id,
                    "timestamp": timestamp,
                    "is_friend": True,
                    "signature_valid": True,
                    "trusted": True,
                }
            ],
            current_time=timestamp,
        )

    def _make_recon_cues(
        self,
        terminal_tracks: list[Any],
        terminal_assignments: list[Any],
        timestamp: float,
    ) -> list[ReconImageCue]:
        if not self._secondary_available(timestamp):
            return []
        projections = self.terminal.project_tracks_to_image(
            terminal_tracks,
            self.terminal_camera,
            timestamp=timestamp,
        )
        cues: list[ReconImageCue] = []
        for assignment in terminal_assignments:
            projection = projections.get(assignment.assigned_global_track_id)
            if projection is None or not projection.valid or projection.pixel is None:
                continue
            resource_id = assignment.resource_id or ""
            cues.append(
                ReconImageCue(
                    cue_id=f"cue-{assignment.assigned_global_track_id}-{timestamp:.2f}",
                    producer_node_id="SEC-NORTH" if resource_id in {"INT-01", "INT-02", "INT-03"} else "SEC-SOUTH",
                    timestamp=timestamp,
                    image_frame_id=f"{resource_id}-camera",
                    global_track_id=assignment.assigned_global_track_id,
                    center_px=projection.pixel,
                    confidence=0.85,
                    scoped_resource_ids=(resource_id,),
                )
            )
        return cues

    def _make_identity_event_if_needed(
        self,
        timestamp: float,
        resource_id: str,
        terminal_state: str,
    ) -> None:
        if terminal_state == "hold":
            self.collector.add_event(
                EventRecord(
                    timestamp=timestamp,
                    event_type="friend_overlap_hold",
                    actor_id=resource_id,
                    severity="warning",
                    note="Terminal association held by verified friendly identity overlap.",
                )
            )

    def _evaluate_degradation(
        self,
        timestamp: float,
        resource_id: str,
        assigned_global_track_id: str,
        d2_track: Any | None,
        truth_by_id: dict[str, TruthState],
        terminal_decision: Any,
        observed_global_track_id: str | None,
        non_locked_count: int,
        mismatch_count: int,
    ) -> None:
        if self.current_plan is None or d2_track is None or d2_track.truth_id not in truth_by_id:
            return
        truth = truth_by_id[d2_track.truth_id]
        friend_conflict = terminal_decision.friend_conflict_state == "verified_friend_overlap"
        terminal_summary = terminal_summary_from_record(
            resource_id=resource_id,
            assigned_global_track_id=assigned_global_track_id,
            decision_state=terminal_decision.decision_state,
            confidence=terminal_decision.association_confidence,
            ambiguity_score=terminal_decision.ambiguity_score,
            coverage_cell=truth.coverage_cell,
            observed_global_track_id=observed_global_track_id,
            non_locked_count=non_locked_count,
            mismatch_count=mismatch_count,
            friend_conflict=friend_conflict,
        )
        c2_health = C2Health.FAILED if self._central_failure_recorded else C2Health.NORMAL
        decision = self.arbiter.evaluate(
            track_uncertainty=track_uncertainty_summary(d2_track, truth, timestamp),
            association_risk=association_risk_summary(
                d2_track,
                ambiguity_score=self.last_association_ambiguity,
                id_switch_count=self.tracker.metrics.id_switch_count,
                duplicate_assignment_count=self.tracker.metrics.duplicate_assignment_count,
                track_continuity=self.tracker.metrics.track_continuity,
            ),
            assignment_validity=assignment_validity_summary(
                self.current_plan,
                assignment_resource_id=resource_id,
                global_track_id=assigned_global_track_id,
                timestamp=timestamp,
            ),
            terminal_association=terminal_summary,
            c2_health=c2_health,
            secondary_nodes=[
                summary
                for summary in resources_to_d4(self.resources, self._secondary_available(timestamp))
                if summary.coordinator_only
            ],
        )
        self.decisions.append(
            IntegratedDecisionRecord(
                timestamp=timestamp,
                resource_id=resource_id,
                global_track_id=assigned_global_track_id,
                mode=decision.mode.value,
                action=decision.action.value,
                reason=decision.reason,
                target_node_id=decision.target_node_id,
                terminal_consistent=decision.terminal_consistent,
                risk_factors=decision.risk_factors,
            )
        )
        self.collector.add_event(
            EventRecord(
                timestamp=timestamp,
                event_type="d4_arbitration_decision",
                actor_id=resource_id,
                severity="warning" if decision.mode != DegradationMode.NONE else "info",
                note=decision.reason,
                metadata=decision.to_dict(),
            )
        )
        if friend_conflict:
            self._make_identity_event_if_needed(timestamp, resource_id, terminal_decision.decision_state)
        if decision.action in {
            DegradationAction.DEGRADE_TO_SECONDARY,
            DegradationAction.DEGRADE_TO_DISTRIBUTED,
            DegradationAction.HOLD_FOR_REVIEW,
        }:
            self._handle_degradation_decision(timestamp, decision, truth_by_id)

    def _handle_degradation_decision(
        self,
        timestamp: float,
        decision: Any,
        truth_by_id: dict[str, TruthState],
    ) -> None:
        key = (decision.mode.value, decision.action.value, decision.reason)
        if key in self._degradation_keys:
            return
        self._degradation_keys.add(key)
        if decision.action == DegradationAction.HOLD_FOR_REVIEW:
            self.collector.add_event(
                EventRecord(
                    timestamp=timestamp,
                    event_type="human_override",
                    actor_id=decision.target_node_id,
                    severity="warning",
                    note="Offline conservative hold marker for identity conflict.",
                    metadata=decision.to_dict(),
                )
            )
            return

        d2_tracks = self.tracker.active_tracks()
        tasks = d2_tracks_to_d4_tasks(d2_tracks, truth_by_id, timestamp)
        resources = resources_to_d4(self.resources, self._secondary_available(timestamp))
        executor_resources = [resource for resource in resources if not resource.coordinator_only]
        if not tasks or not executor_resources:
            return
        node_ids = [resource.node_id for resource in executor_resources]
        network = SimulatedNetwork(
            node_ids=node_ids,
            packet_loss=0.05,
            min_delay_s=0.05,
            max_delay_s=0.15,
            seed=self.config.seed + len(self._degradation_keys),
        )
        if decision.mode == DegradationMode.PASSIVE_FAILOVER:
            self.failover.health = C2Health.FAILED
            result = self.failover.plan_degraded(
                tasks,
                resources,
                network,
                now_s=timestamp,
                bundle_limit=1,
                max_rounds=12,
                round_period_s=0.2,
            )
        else:
            negotiator = CBBANegotiator(
                node_ids=node_ids,
                epoch=1,
                bundle_limit=1,
                max_rounds=12,
                round_period_s=0.2,
            )
            result = negotiator.run(tasks, executor_resources, network, start_time_s=timestamp)
            result.final_views["coordination_mode"] = {
                "state": "active_secondary_node"
                if decision.action == DegradationAction.DEGRADE_TO_SECONDARY
                else "active_distributed_cbba",
                "leader_id": decision.target_node_id or "",
                "coverage_cell": decision.coverage_cell or "",
            }

        self.collector.add_event(
            EventRecord(
                timestamp=timestamp + result.duration_s,
                event_type="degraded_stable",
                actor_id=decision.target_node_id or "distributed",
                severity="info",
                note=f"{decision.mode.value}:{decision.action.value}",
                metadata={
                    "cbba": result.to_dict(),
                    "decision": decision.to_dict(),
                },
            )
        )
        self.collector.add_event(
            EventRecord(
                timestamp=timestamp + result.duration_s,
                event_type="consensus_rounds",
                actor_id=decision.target_node_id or "distributed",
                value=result.consensus_rounds,
                metadata={"rounds": result.consensus_rounds},
            )
        )
        for task_id in result.assignments:
            self.collector.add_event(
                EventRecord(
                    timestamp=timestamp + result.duration_s,
                    event_type="degraded_task_completed",
                    actor_id=task_id,
                    metadata={"mode": decision.mode.value, "action": decision.action.value},
                )
            )
        self._simulate_guidance_for_d4_result(
            timestamp=timestamp,
            assignments=result.assignments,
            truth_by_id=truth_by_id,
            source=f"d4_{decision.mode.value}_{decision.action.value}",
        )

    def _secondary_available(self, timestamp: float) -> bool:
        failure_time = self.config.secondary_failure_time_s
        return failure_time is None or timestamp < failure_time

    def _simulate_guidance_for_plan(
        self,
        timestamp: float,
        plan: AssignmentPlan,
        d2_by_id: dict[str, Any],
        truth_by_id: dict[str, TruthState],
        source: str,
    ) -> None:
        plan_key = (plan.plan_id, plan.version)
        if plan_key in self._guidance_plan_keys:
            return
        self._guidance_plan_keys.add(plan_key)
        for assignment in plan.assignments:
            d2_track = d2_by_id.get(assignment.target_id)
            if d2_track is None or d2_track.truth_id not in truth_by_id:
                continue
            self._simulate_guidance_pair(
                timestamp=timestamp,
                resource_id=assignment.resource_id,
                global_track_id=assignment.target_id,
                truth=truth_by_id[d2_track.truth_id],
                source=source,
                plan_id=plan.plan_id,
                plan_version=plan.version,
            )

    def _simulate_guidance_for_d4_result(
        self,
        timestamp: float,
        assignments: dict[str, Any],
        truth_by_id: dict[str, TruthState],
        source: str,
    ) -> None:
        plan_key = (source, round(timestamp, 3))
        if plan_key in self._guidance_plan_keys:
            return
        self._guidance_plan_keys.add(plan_key)
        d2_by_track_id = {track.global_track_id: track for track in self.tracker.active_tracks()}
        for global_track_id, assignment in assignments.items():
            d2_track = d2_by_track_id.get(global_track_id)
            if d2_track is None or d2_track.truth_id not in truth_by_id:
                continue
            self._simulate_guidance_pair(
                timestamp=timestamp,
                resource_id=assignment.owner,
                global_track_id=global_track_id,
                truth=truth_by_id[d2_track.truth_id],
                source=source,
                plan_id=source,
                plan_version=1,
            )

    def _simulate_guidance_pair(
        self,
        timestamp: float,
        resource_id: str,
        global_track_id: str,
        truth: TruthState,
        source: str,
        plan_id: str,
        plan_version: int,
    ) -> None:
        resource = self._resource_by_id(resource_id)
        if resource is None:
            return
        target_xy = truth.position[:2]
        resource_xy = resource.position[:2]
        line = target_xy - resource_xy
        distance = max(float(np.linalg.norm(line)), 1.0)
        direction = line / distance
        pursuer_speed = 48.0
        pursuer = GuidanceState(
            entity_id=resource_id,
            timestamp_s=0.0,
            position_m=(float(resource_xy[0]), float(resource_xy[1])),
            velocity_mps=(float(direction[0] * pursuer_speed), float(direction[1] * pursuer_speed)),
            source="assignment_resource_state",
        )
        target = GuidanceState(
            entity_id=global_track_id,
            timestamp_s=0.0,
            position_m=(float(target_xy[0]), float(target_xy[1])),
            velocity_mps=(float(truth.velocity[0]), float(truth.velocity[1])),
            source="global_track_estimate",
            covariance_trace=25.0,
            metadata={"truth_id": truth.truth_id, "coverage_cell": truth.coverage_cell},
        )
        config = GuidanceConfig(
            dt_s=0.1,
            max_duration_s=5.0,
            navigation_constant=3.0,
            max_lateral_accel_mps2=45.0,
            max_turn_rate_radps=0.65,
            terminal_switch_range_m=max(2.0, min(70.0, distance * 0.35)),
            intercept_radius_m=1.0,
            stop_at_intercept_radius=True,
            radar_position_noise_m=1.5,
            radar_velocity_noise_mps=0.2,
            vision_los_noise_rad=0.002,
            vision_range_noise_fraction=0.015,
            random_seed=self.config.seed + int(timestamp * 10.0) + len(self.guidance_summaries),
        )
        records, summary = simulate_guidance_episode(
            pursuer_initial=pursuer,
            target_initial=target,
            config=config,
            resource_id=resource_id,
            target_id=global_track_id,
        )
        for record in records:
            record_dict = record.as_dict()
            record_dict["episode_timestamp_s"] = timestamp
            record_dict["source"] = source
            record_dict["plan_id"] = plan_id
            record_dict["plan_version"] = plan_version
        self.guidance_records.extend(records)
        summary = {
            **summary,
            "episode_timestamp_s": timestamp,
            "source": source,
            "plan_id": plan_id,
            "plan_version": plan_version,
            "resource_id": resource_id,
            "global_track_id": global_track_id,
        }
        self.guidance_summaries.append(summary)
        self.collector.add_event(
            EventRecord(
                timestamp=timestamp,
                event_type="guidance_summary",
                actor_id=resource_id,
                note="Offline D7 radar/vision proportional guidance summary.",
                metadata=summary,
            )
        )
        if any(record.mode == GuidanceMode.VISION_TERMINAL for record in records):
            self.collector.add_event(
                EventRecord(
                    timestamp=timestamp,
                    event_type="guidance_terminal_mode_entered",
                    actor_id=resource_id,
                    metadata={
                        "global_track_id": global_track_id,
                        "source": source,
                        "plan_id": plan_id,
                        "plan_version": plan_version,
                    },
                )
            )

    def _resource_by_id(self, resource_id: str) -> ResourcePlatform | None:
        for resource in self.resources:
            if resource.resource_id == resource_id:
                return resource
        return None

    def _truth_states(self, timestamp: float) -> list[TruthState]:
        if self.truth_provider is not None:
            return list(self.truth_provider(timestamp))
        return generate_truth_states(self.config, timestamp)


def run_integrated_episode(
    config: ScenarioConfig,
    output_dir: str | Path | None = None,
) -> EpisodeResult:
    """Convenience wrapper for running one integrated episode."""

    return IntegratedEpisodeRunner(config).run(output_dir=output_dir)


def result_to_dict(result: EpisodeResult) -> dict[str, Any]:
    return {
        "scenario": jsonable_dataclass(result.scenario),
        "metrics": result.metrics.to_dict(),
        "truth_summary": result.truth_summary,
        "decisions": [jsonable_dataclass(decision) for decision in result.decisions],
        "guidance_summaries": result.guidance_summaries,
        "output_paths": {name: str(path) for name, path in result.output_paths.items()},
        "metadata": result.metadata,
    }
