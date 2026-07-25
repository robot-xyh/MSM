"""Main-owned scheduler for scalable three-dimensional point-mass episodes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import heapq
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Mapping

import numpy as np

from .communication import DeterministicCommunicationNetwork, LinkProfile
from .episode_bus import (
    EpisodeManifest,
    InMemoryEpisodeBus,
    ONLINE_TRUTH_GUARD_REFERENCE_IMPLEMENTATION,
    VersionedEnvelope,
    build_episode_manifest,
    jsonable,
)
from .models import (
    ONLINE_OBSERVATION_SCHEMA_VERSION,
    OfflineTruthLabel,
    OnlineSensorBatch,
    ScenarioConfig,
    SensorMeasurement,
)
from .sensor_scene import SensorScene
from .runtime_ports import (
    CameraObservationCommand,
    CameraRuntimeState,
    PlatformNavigationBatch,
    RuntimeStepInput,
    ScalableModuleStack,
)
from .world import ProximityInterceptEvent, VectorizedPointMassWorld


@dataclass(frozen=True)
class StageTiming:
    stage: str
    call_count: int
    wall_time_s: float
    p50_wall_time_ms: float | None = None
    p95_wall_time_ms: float | None = None
    max_wall_time_ms: float | None = None
    distribution_available: bool = False
    distribution_unavailable_reason: str | None = "timing_samples_unavailable"

    @property
    def mean_wall_time_ms(self) -> float:
        if self.call_count == 0:
            return 0.0
        return 1_000.0 * self.wall_time_s / self.call_count


@dataclass(frozen=True)
class EpisodeResult:
    """In-memory result with online and evaluator data kept in separate fields."""

    config: ScenarioConfig
    manifest: EpisodeManifest
    timestamps: np.ndarray
    intruder_state_history: np.ndarray
    interceptor_state_history: np.ndarray
    recon_state_history: np.ndarray
    intruder_active_history: np.ndarray
    intruder_ids: tuple[str, ...]
    proximity_intercepts: tuple[ProximityInterceptEvent, ...]
    online_messages: tuple[VersionedEnvelope, ...]
    offline_truth_labels: tuple[OfflineTruthLabel, ...]
    d1_consistency_evidence_records: tuple[Any, ...]
    stage_timings: tuple[StageTiming, ...]
    summary: dict[str, Any]
    observation_governance_audit: dict[str, Any] | None = None
    output_paths: dict[str, Path] | None = None


class _TimingAccumulator:
    def __init__(self) -> None:
        self.total: dict[str, float] = {}
        self.calls: dict[str, int] = {}
        self.samples: dict[str, list[float]] = {}
        self.merged_distributions_ms: dict[str, tuple[float, float, float]] = {}

    def add(self, stage: str, elapsed_s: float) -> None:
        elapsed = float(elapsed_s)
        self.total[stage] = self.total.get(stage, 0.0) + elapsed
        self.calls[stage] = self.calls.get(stage, 0) + 1
        self.samples.setdefault(stage, []).append(elapsed)

    def merge_total(
        self,
        stage: str,
        *,
        wall_time_s: float,
        call_count: int,
        p50_wall_time_ms: float | None = None,
        p95_wall_time_ms: float | None = None,
        max_wall_time_ms: float | None = None,
    ) -> None:
        """Merge a cumulative child-stage record without losing its call count."""

        if call_count < 0 or wall_time_s < 0.0:
            raise ValueError("timing totals must be non-negative")
        self.total[stage] = self.total.get(stage, 0.0) + float(wall_time_s)
        self.calls[stage] = self.calls.get(stage, 0) + int(call_count)
        distribution = (p50_wall_time_ms, p95_wall_time_ms, max_wall_time_ms)
        present_count = sum(value is not None for value in distribution)
        if present_count not in {0, 3}:
            raise ValueError(
                "timing distribution fields must be all present or all absent"
            )
        if all(value is not None for value in distribution):
            values = tuple(float(value) for value in distribution)
            if any(not np.isfinite(value) or value < 0.0 for value in values):
                raise ValueError("timing distributions must be finite and non-negative")
            if not values[0] <= values[1] <= values[2]:
                raise ValueError("timing distributions must satisfy p50 <= p95 <= max")
            self.merged_distributions_ms[stage] = values

    def records(self) -> tuple[StageTiming, ...]:
        records: list[StageTiming] = []
        for stage in sorted(self.total):
            if stage in self.samples:
                p50_ms, p95_ms, max_ms = _timing_distribution_ms(
                    self.samples[stage]
                )
                distribution_available = True
                unavailable_reason = None
            elif stage in self.merged_distributions_ms:
                p50_ms, p95_ms, max_ms = self.merged_distributions_ms[stage]
                distribution_available = True
                unavailable_reason = None
            else:
                p50_ms = None
                p95_ms = None
                max_ms = None
                distribution_available = False
                unavailable_reason = "child_timing_distribution_unavailable"
            records.append(
                StageTiming(
                    stage=stage,
                    call_count=self.calls[stage],
                    wall_time_s=self.total[stage],
                    p50_wall_time_ms=p50_ms,
                    p95_wall_time_ms=p95_ms,
                    max_wall_time_ms=max_ms,
                    distribution_available=distribution_available,
                    distribution_unavailable_reason=unavailable_reason,
                )
            )
        return tuple(records)


def _timing_distribution_ms(samples_s: list[float]) -> tuple[float, float, float]:
    if not samples_s:
        return 0.0, 0.0, 0.0
    values = np.asarray(samples_s, dtype=float)
    return (
        1_000.0 * float(np.percentile(values, 50.0)),
        1_000.0 * float(np.percentile(values, 95.0)),
        1_000.0 * float(np.max(values)),
    )


class Scalable3DEpisodeRunner:
    """Advance the world and asynchronous sensor clocks on one deterministic timeline."""

    def __init__(
        self,
        config: ScenarioConfig,
        *,
        module_stack: ScalableModuleStack | None = None,
        online_truth_guard_implementation: str = (
            ONLINE_TRUTH_GUARD_REFERENCE_IMPLEMENTATION
        ),
    ) -> None:
        self.config = config
        self.world = VectorizedPointMassWorld(config)
        self.sensor_scene = SensorScene(config)
        self.bus = InMemoryEpisodeBus(
            truth_guard_implementation=online_truth_guard_implementation
        )
        self.communication = DeterministicCommunicationNetwork(
            seed=config.seed + 20_000,
            default_profile=LinkProfile(
                latency_s=config.communication_latency_s,
                jitter_s=config.communication_jitter_s,
                drop_probability=config.communication_drop_probability,
                bandwidth_bytes_per_s=config.communication_bandwidth_bytes_per_s,
            ),
        )
        self.module_stack = module_stack
        self.manifest = build_episode_manifest(
            config,
            runtime_profile=_runtime_manifest_profile(
                module_stack,
                config,
                online_truth_guard_implementation=(
                    self.bus.truth_guard_implementation
                ),
            ),
        )

    def run(self) -> EpisodeResult:
        """Run a world/sensor baseline without D1-D7 algorithm shortcuts."""

        self.world.reset()
        self.sensor_scene.reset()
        self.bus.clear()
        self.communication.reset(seed=self.config.seed + 20_000)
        if self.module_stack is not None:
            self.module_stack.reset(self.config)
        timing = _TimingAccumulator()
        pending: list[tuple[float, int, OnlineSensorBatch]] = []
        pending_counter = 0
        transport_sequence = 0
        offline_labels: list[OfflineTruthLabel] = []
        timestamps = self.config.timestamps()
        step_count = timestamps.size
        intruder_history = np.empty((step_count, self.config.target_count, 6), dtype=np.float32)
        interceptor_history = np.empty(
            (step_count, self.config.resource_count, 6), dtype=np.float32
        )
        recon_history = np.empty((step_count, self.config.recon_count, 6), dtype=np.float32)
        intruder_active_history = np.empty(
            (step_count, self.config.target_count), dtype=bool
        )
        next_radar_time = 0.0
        next_acoustic_time = 0.0
        next_visual_time = 0.0
        episode_start = time.perf_counter()
        module_publication_count = 0
        module_publication_topic_counts: dict[str, int] = {}
        last_module_diagnostics: dict[str, Any] = {}
        control_command_tick_count = 0
        proximity_intercepts: list[ProximityInterceptEvent] = []
        camera_states: dict[str, CameraRuntimeState] = {}
        camera_command_issued_count = 0
        camera_command_applied_count = 0
        camera_command_rejected_count = 0
        camera_command_rejection_reasons: Counter[str] = Counter()
        camera_command_ack_count = 0
        assignment_plan_ack_count = 0
        assignment_plan_binding_ack_count = 0
        assignment_plan_control_applied_count = 0
        assignment_plan_hold_count = 0

        for step_index in range(step_count):
            snapshot = self.world.snapshot()
            current_time = snapshot.timestamp
            _refresh_camera_runtime_states(
                camera_states,
                config=self.config,
                snapshot=snapshot,
                timestamp=current_time,
            )
            intruder_history[step_index] = snapshot.intruders.state
            interceptor_history[step_index] = snapshot.interceptors.state
            recon_history[step_index] = snapshot.recon.state
            intruder_active_history[step_index] = snapshot.intruders.active

            if self.config.radar_enabled and current_time + 1.0e-12 >= next_radar_time:
                started = time.perf_counter()
                batch = self.sensor_scene.radar_scan(snapshot)
                timing.add("radar_scene", time.perf_counter() - started)
                offline_labels.extend(batch.offline_truth_labels)
                for online_batch in _group_sensor_batches(batch.measurements):
                    pending_counter += 1
                    heapq.heappush(
                        pending,
                        (online_batch.arrival_timestamp, pending_counter, online_batch),
                    )
                next_radar_time += self.config.radar_period_s

            if self.config.acoustic_enabled and current_time + 1.0e-12 >= next_acoustic_time:
                started = time.perf_counter()
                batch = self.sensor_scene.acoustic_scan(snapshot)
                timing.add("acoustic_scene", time.perf_counter() - started)
                offline_labels.extend(batch.offline_truth_labels)
                for online_batch in _group_sensor_batches(batch.measurements):
                    pending_counter += 1
                    heapq.heappush(
                        pending,
                        (online_batch.arrival_timestamp, pending_counter, online_batch),
                    )
                next_acoustic_time += self.config.acoustic_period_s

            if self.config.visual_enabled and current_time + 1.0e-12 >= next_visual_time:
                started = time.perf_counter()
                batch = self.sensor_scene.visual_scan(
                    snapshot,
                    camera_aim_points=_camera_aim_points(camera_states, snapshot),
                    camera_horizontal_fov_deg={
                        camera_id: state.horizontal_fov_deg
                        for camera_id, state in camera_states.items()
                    },
                )
                timing.add("visual_scene", time.perf_counter() - started)
                offline_labels.extend(batch.offline_truth_labels)
                for online_batch in _group_sensor_batches(batch.measurements):
                    pending_counter += 1
                    heapq.heappush(
                        pending,
                        (online_batch.arrival_timestamp, pending_counter, online_batch),
                    )
                next_visual_time += self.config.visual_period_s

            arrived_batches: list[OnlineSensorBatch] = []
            started = time.perf_counter()
            while pending and pending[0][0] <= current_time + 1.0e-12:
                _, _, online_batch = heapq.heappop(pending)
                if self.config.communication_enabled:
                    transport_sequence += 1
                    self.communication.send(
                        source=online_batch.sensor_id,
                        destination="FUSION-CENTER",
                        send_timestamp=online_batch.arrival_timestamp,
                        envelope=VersionedEnvelope(
                            sequence=transport_sequence,
                            topic="sensor.observations",
                            source=online_batch.sensor_id,
                            timestamp=online_batch.arrival_timestamp,
                            schema_version=ONLINE_OBSERVATION_SCHEMA_VERSION,
                            payload=online_batch,
                        ),
                    )
                else:
                    arrived_batches.append(online_batch)
            if self.config.communication_enabled:
                arrived_batches.extend(
                    _retime_sensor_batch(
                        delivered.envelope.payload,
                        arrival_timestamp=delivered.arrival_timestamp,
                    )
                    for delivered in self.communication.deliver(current_time)
                )
            arrived_batches.sort(
                key=lambda item: (
                    item.arrival_timestamp,
                    item.measurement_timestamp,
                    item.sensor_id,
                    item.batch_id,
                )
            )
            for online_batch in arrived_batches:
                self.bus.publish(
                    topic="sensor.observations",
                    source=online_batch.sensor_id,
                    timestamp=online_batch.arrival_timestamp,
                    schema_version=ONLINE_OBSERVATION_SCHEMA_VERSION,
                    payload=online_batch,
                    copy_payload=False,
                )
            timing.add("episode_bus", time.perf_counter() - started)

            if step_index + 1 < step_count:
                interceptor_command = None
                recon_command = None
                if self.module_stack is not None:
                    started = time.perf_counter()
                    module_output = self.module_stack.step(
                        RuntimeStepInput(
                            timestamp=current_time,
                            arrived_sensor_batches=tuple(arrived_batches),
                            interceptors=_platform_navigation_batch(
                                "interceptor", snapshot.interceptors, current_time
                            ),
                            recon=_platform_navigation_batch(
                                "recon", snapshot.recon, current_time
                            ),
                            cameras=tuple(
                                camera_states[camera_id]
                                for camera_id in sorted(camera_states)
                            ),
                        )
                    ).validated(
                        resource_count=self.config.resource_count,
                        recon_count=self.config.recon_count,
                    )
                    interceptor_command = module_output.interceptor_acceleration_ned
                    recon_command = module_output.recon_acceleration_ned
                    camera_command_issued_count += len(module_output.camera_commands)
                    camera_acks = _apply_camera_commands(
                        camera_states,
                        module_output.camera_commands,
                        snapshot=snapshot,
                        current_timestamp=current_time,
                    )
                    feedback_recorder = getattr(
                        self.module_stack,
                        "record_active_vision_runtime_feedback",
                        None,
                    )
                    if callable(feedback_recorder) and camera_acks:
                        feedback_recorder(
                            timestamp_s=current_time,
                            camera_states=tuple(
                                camera_states[camera_id]
                                for camera_id in sorted(camera_states)
                            ),
                            acknowledgements=camera_acks,
                        )
                    for ack in camera_acks:
                        camera_command_ack_count += 1
                        if ack["status"] == "applied":
                            camera_command_applied_count += 1
                        else:
                            camera_command_rejected_count += 1
                            camera_command_rejection_reasons[str(ack["reason"])] += 1
                        self.bus.publish(
                            topic="runtime.camera_command_ack",
                            source="MAIN-RUNTIME",
                            timestamp=current_time,
                            schema_version="scalable3d-camera-command-ack-v1",
                            payload=ack,
                            copy_payload=False,
                        )
                    last_module_diagnostics = dict(module_output.diagnostics)
                    publication_started = time.perf_counter()
                    publication_envelopes: list[VersionedEnvelope] = []
                    for publication in module_output.publications:
                        publication_envelopes.append(
                            self.bus.publish(
                                topic=publication.topic,
                                source=publication.source,
                                timestamp=current_time,
                                schema_version=publication.schema_version,
                                payload=publication.payload,
                                copy_payload=publication.copy_payload,
                            )
                        )
                        module_publication_count += 1
                        module_publication_topic_counts[publication.topic] = (
                            module_publication_topic_counts.get(publication.topic, 0) + 1
                        )
                    plan_ack = _assignment_plan_runtime_ack(
                        module_output.publications,
                        source_envelopes=tuple(publication_envelopes),
                        ack_timestamp=current_time,
                    )
                    if plan_ack is not None:
                        self.bus.publish(
                            topic="runtime.assignment_plan_ack",
                            source="MAIN-RUNTIME",
                            timestamp=current_time,
                            schema_version=(
                                "scalable3d-assignment-plan-runtime-ack-v1"
                            ),
                            payload=plan_ack,
                            copy_payload=False,
                        )
                        assignment_plan_ack_count += 1
                        assignment_plan_binding_ack_count += int(
                            plan_ack["binding_ack_count"]
                        )
                        assignment_plan_control_applied_count += int(
                            plan_ack["control_applied_binding_count"]
                        )
                        assignment_plan_hold_count += int(
                            plan_ack["held_binding_count"]
                        )
                    timing.add(
                        "module_publication_bus",
                        time.perf_counter() - publication_started,
                    )
                    control_command_tick_count += 1
                    timing.add("module_stack", time.perf_counter() - started)
                started = time.perf_counter()
                diagnostics = self.world.step(
                    interceptor_acceleration_ned=interceptor_command,
                    recon_acceleration_ned=recon_command,
                )
                proximity_intercepts.extend(self.world.register_proximity_intercepts())
                timing.add("world_dynamics", time.perf_counter() - started)
                if not diagnostics.finite_state:
                    raise FloatingPointError(f"non-finite world state at {diagnostics.timestamp:.3f}s")

        if self.module_stack is not None:
            finalizer = getattr(self.module_stack, "finalize", None)
            if callable(finalizer):
                started = time.perf_counter()
                final_output = finalizer(float(timestamps[-1])).validated(
                    resource_count=self.config.resource_count,
                    recon_count=self.config.recon_count,
                )
                if final_output.camera_commands:
                    raise ValueError(
                        "module finalization must not emit camera commands"
                    )
                if np.any(final_output.interceptor_acceleration_ned) or np.any(
                    final_output.recon_acceleration_ned
                ):
                    raise ValueError(
                        "module finalization must not emit motion commands"
                    )
                publication_started = time.perf_counter()
                for publication in final_output.publications:
                    self.bus.publish(
                        topic=publication.topic,
                        source=publication.source,
                        timestamp=float(timestamps[-1]),
                        schema_version=publication.schema_version,
                        payload=publication.payload,
                        copy_payload=publication.copy_payload,
                    )
                    module_publication_count += 1
                    module_publication_topic_counts[publication.topic] = (
                        module_publication_topic_counts.get(publication.topic, 0)
                        + 1
                    )
                timing.add(
                    "module_publication_bus_finalize",
                    time.perf_counter() - publication_started,
                )
                last_module_diagnostics = dict(final_output.diagnostics)
                timing.add("module_stack_finalize", time.perf_counter() - started)

        elapsed = time.perf_counter() - episode_start
        diagnostics = self.world.diagnostics()
        communication_stats = self.communication.stats()
        messages = self.bus.messages()
        d1_consistency_records = _d1_consistency_evidence_records(
            self.module_stack
        )
        observation_governance_audit = _observation_governance_audit(
            self.module_stack
        )
        observation_governance = observation_governance_audit or {}
        learning_artifact_counts = _learning_artifact_counts(self.module_stack)
        radar_count = sum(
            len(message.payload.measurements)
            for message in messages
            if isinstance(message.payload, OnlineSensorBatch)
            and message.payload.measurements[0].modality == "radar_spherical"
        )
        acoustic_count = sum(
            len(message.payload.measurements)
            for message in messages
            if isinstance(message.payload, OnlineSensorBatch)
            and message.payload.measurements[0].modality == "acoustic_bearing"
        )
        visual_count = sum(
            len(message.payload.measurements)
            for message in messages
            if isinstance(message.payload, OnlineSensorBatch)
            and message.payload.measurements[0].modality == "vision_bbox"
        )
        module_stage_timings = last_module_diagnostics.get("stage_timings", {})
        if isinstance(module_stage_timings, dict):
            for stage, record in module_stage_timings.items():
                if not isinstance(record, dict):
                    continue
                timing.merge_total(
                    f"module.{stage}",
                    wall_time_s=float(record.get("wall_time_s", 0.0)),
                    call_count=int(record.get("call_count", 0)),
                    p50_wall_time_ms=_optional_float(
                        record.get("p50_wall_time_ms")
                    ),
                    p95_wall_time_ms=_optional_float(
                        record.get("p95_wall_time_ms")
                    ),
                    max_wall_time_ms=_optional_float(
                        record.get("max_wall_time_ms")
                    ),
                )
        summary: dict[str, Any] = {
            "episode_id": self.manifest.episode_id,
            "scenario_name": self.config.scenario_name,
            "scenario_version": self.config.scenario_version,
            "seed": self.config.seed,
            "target_count": self.config.target_count,
            "resource_count": self.config.resource_count,
            "recon_count": self.config.recon_count,
            "physics_step_count": int(max(0, step_count - 1)),
            "simulated_duration_s": float(timestamps[-1]),
            "wall_time_s": elapsed,
            "real_time_factor": float(timestamps[-1] / elapsed) if elapsed > 0.0 else None,
            "finite_state": diagnostics.finite_state,
            "radar_observation_count": radar_count,
            "acoustic_observation_count": acoustic_count,
            "visual_observation_count": visual_count,
            "online_observation_count": radar_count + acoustic_count + visual_count,
            "online_batch_count": sum(
                isinstance(message.payload, OnlineSensorBatch) for message in messages
            ),
            "offline_truth_label_count": len(offline_labels),
            "pending_after_episode_count": len(pending),
            "communication_enabled": self.config.communication_enabled,
            "communication_sent_count": communication_stats.sent_count,
            "communication_delivered_count": communication_stats.delivered_count,
            "communication_dropped_count": communication_stats.dropped_count,
            "communication_pending_count": communication_stats.pending_count,
            "communication_sent_bytes": communication_stats.sent_bytes,
            "communication_delivered_bytes": communication_stats.delivered_bytes,
            **learning_artifact_counts,
            "online_truth_use_count": 0,
            "module_stack_enabled": self.module_stack is not None,
            "module_publication_count": module_publication_count,
            "module_publication_topic_counts": dict(
                sorted(module_publication_topic_counts.items())
            ),
            "online_truth_guard_implementation": (
                self.bus.truth_guard_implementation
            ),
            "online_truth_guard_diagnostics": (
                self.bus.truth_guard_diagnostics()
            ),
            "module_final_diagnostics": last_module_diagnostics,
            "d1_scan_input_implementation": observation_governance.get(
                "d1_scan_input_implementation"
            ),
            "d1_scan_input_execution_config": observation_governance.get(
                "d1_scan_input_execution_config"
            ),
            "d1_scan_input_performance_diagnostics": observation_governance.get(
                "d1_scan_input_performance_diagnostics"
            ),
            "d1_publication_metadata_implementation": (
                observation_governance.get(
                    "d1_publication_metadata_implementation"
                )
            ),
            "d1_publication_metadata_diagnostics": observation_governance.get(
                "d1_publication_metadata_diagnostics"
            ),
            "d1_cv_motion_model_implementation": observation_governance.get(
                "d1_cv_motion_model_implementation"
            ),
            "d1_cv_motion_model_cache_diagnostics": (
                observation_governance.get(
                    "d1_cv_motion_model_cache_diagnostics"
                )
            ),
            "d2_publication_metadata_audit": observation_governance.get(
                "d2_publication_metadata_audit"
            ),
            "control_command_tick_count": control_command_tick_count,
            "camera_command_issued_count": camera_command_issued_count,
            "camera_command_applied_count": camera_command_applied_count,
            "camera_command_rejected_count": camera_command_rejected_count,
            "camera_command_ack_count": camera_command_ack_count,
            "camera_command_rejection_reason_counts": dict(
                sorted(camera_command_rejection_reasons.items())
            ),
            "assignment_plan_ack_count": assignment_plan_ack_count,
            "assignment_plan_binding_ack_count": (
                assignment_plan_binding_ack_count
            ),
            "assignment_plan_control_applied_count": (
                assignment_plan_control_applied_count
            ),
            "assignment_plan_hold_count": assignment_plan_hold_count,
            "camera_state_count": len(camera_states),
            "intercepted_target_count": len(self.world.intercepted_target_indices),
            "max_target_speed_mps": diagnostics.max_target_speed_mps,
            "max_interceptor_speed_mps": diagnostics.max_interceptor_speed_mps,
            "max_recon_speed_mps": diagnostics.max_recon_speed_mps,
        }
        return EpisodeResult(
            config=self.config,
            manifest=self.manifest,
            timestamps=timestamps,
            intruder_state_history=intruder_history,
            interceptor_state_history=interceptor_history,
            recon_state_history=recon_history,
            intruder_active_history=intruder_active_history,
            intruder_ids=tuple(self.world.intruder_ids),
            proximity_intercepts=tuple(proximity_intercepts),
            online_messages=messages,
            offline_truth_labels=tuple(offline_labels),
            d1_consistency_evidence_records=d1_consistency_records,
            stage_timings=timing.records(),
            summary=summary,
            observation_governance_audit=observation_governance_audit,
        )


def run_episode(
    config: ScenarioConfig,
    *,
    output_dir: str | Path | None = None,
    write_plot: bool = False,
    animation_formats: tuple[str, ...] = (),
    module_stack: ScalableModuleStack | None = None,
    write_learning_data: bool = False,
    online_truth_guard_implementation: str = (
        ONLINE_TRUTH_GUARD_REFERENCE_IMPLEMENTATION
    ),
) -> EpisodeResult:
    """Run one baseline episode and optionally persist its reproducibility bundle."""

    result = Scalable3DEpisodeRunner(
        config,
        module_stack=module_stack,
        online_truth_guard_implementation=(
            online_truth_guard_implementation
        ),
    ).run()
    if output_dir is None:
        if write_learning_data:
            raise ValueError("write_learning_data requires output_dir")
        return result
    from .reporting import write_episode_outputs

    paths = write_episode_outputs(
        result,
        Path(output_dir),
        write_plot=write_plot,
        animation_formats=animation_formats,
    )
    if write_learning_data:
        artifact_provider = getattr(module_stack, "learning_artifacts", None)
        if not callable(artifact_provider):
            raise ValueError(
                "write_learning_data requires an integrated stack with artifact capture"
            )
        if not bool(
            getattr(
                getattr(module_stack, "stack_config", None),
                "capture_learning_artifacts",
                False,
            )
        ):
            raise ValueError(
                "write_learning_data requires capture_learning_artifacts=True"
            )
        from .learning_export import write_episode_learning_artifacts

        learning_paths = write_episode_learning_artifacts(
            Path(output_dir) / "learning_data",
            config=result.config,
            manifest=result.manifest,
            artifacts=artifact_provider(),
            offline_truth_labels=result.offline_truth_labels,
            online_messages=result.online_messages,
        )
        paths.update(
            {f"learning_{key}": value for key, value in learning_paths.items()}
        )
    return EpisodeResult(
        config=result.config,
        manifest=result.manifest,
        timestamps=result.timestamps,
        intruder_state_history=result.intruder_state_history,
        interceptor_state_history=result.interceptor_state_history,
        recon_state_history=result.recon_state_history,
        intruder_active_history=result.intruder_active_history,
        intruder_ids=result.intruder_ids,
        proximity_intercepts=result.proximity_intercepts,
        online_messages=result.online_messages,
        offline_truth_labels=result.offline_truth_labels,
        d1_consistency_evidence_records=(
            result.d1_consistency_evidence_records
        ),
        stage_timings=result.stage_timings,
        summary=result.summary,
        observation_governance_audit=result.observation_governance_audit,
        output_paths=paths,
    )


def _group_sensor_batches(
    measurements: tuple[SensorMeasurement, ...],
) -> tuple[OnlineSensorBatch, ...]:
    grouped: dict[tuple[str, float, float], list[SensorMeasurement]] = {}
    for measurement in measurements:
        key = (
            measurement.sensor_id,
            measurement.measurement_timestamp,
            measurement.arrival_timestamp,
        )
        grouped.setdefault(key, []).append(measurement)
    batches: list[OnlineSensorBatch] = []
    for batch_index, (key, values) in enumerate(sorted(grouped.items())):
        sensor_id, measurement_timestamp, arrival_timestamp = key
        batches.append(
            OnlineSensorBatch(
                batch_id=(
                    f"{sensor_id.lower()}-scan-{measurement_timestamp:.6f}-"
                    f"{batch_index:04d}"
                ),
                sensor_id=sensor_id,
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                measurements=tuple(values),
            )
        )
    return tuple(batches)


def _retime_sensor_batch(
    batch: OnlineSensorBatch,
    *,
    arrival_timestamp: float,
) -> OnlineSensorBatch:
    """Set the consumer arrival time after sensor processing and network transport."""

    actual_arrival = float(arrival_timestamp)
    if actual_arrival + 1.0e-12 < batch.arrival_timestamp:
        raise ValueError("network arrival must not precede sensor-ready timestamp")
    measurements = tuple(
        replace(measurement, arrival_timestamp=actual_arrival)
        for measurement in batch.measurements
    )
    return replace(
        batch,
        arrival_timestamp=actual_arrival,
        measurements=measurements,
    )


def _platform_navigation_batch(
    platform_kind: str,
    snapshot: Any,
    timestamp: float,
) -> PlatformNavigationBatch:
    count = len(snapshot.entity_ids)
    covariance = np.broadcast_to(
        np.diag([0.25, 0.25, 0.25, 0.04, 0.04, 0.04]),
        (count, 6, 6),
    ).copy()
    return PlatformNavigationBatch(
        platform_kind=platform_kind,
        platform_ids=tuple(snapshot.entity_ids),
        timestamp=float(timestamp),
        state_ned=snapshot.state,
        covariance=covariance,
        active=snapshot.active,
    )


def _learning_artifact_counts(module_stack: ScalableModuleStack | None) -> dict[str, int | bool]:
    provider = getattr(module_stack, "learning_artifacts", None)
    if not callable(provider):
        return {
            "learning_artifact_capture_enabled": False,
            "d3_learning_frame_count": 0,
            "d4_learning_frame_count": 0,
            "d5_learning_graph_frame_count": 0,
            "d5_active_vision_learning_frame_count": 0,
        }
    artifacts = provider()
    enabled = bool(
        getattr(getattr(module_stack, "stack_config", None), "capture_learning_artifacts", False)
    )
    return {
        "learning_artifact_capture_enabled": enabled,
        "d3_learning_frame_count": len(artifacts.d3_planning_frames),
        "d4_learning_frame_count": len(artifacts.d4_region_frames),
        "d5_learning_graph_frame_count": len(artifacts.d5_graph_frames),
        "d5_active_vision_learning_frame_count": len(
            getattr(artifacts, "d5_active_vision_frames", ())
        ),
    }


def _d1_consistency_evidence_records(
    module_stack: ScalableModuleStack | None,
) -> tuple[Any, ...]:
    provider = getattr(module_stack, "d1_consistency_evidence_records", None)
    if not callable(provider):
        return ()
    return tuple(provider())


def _runtime_manifest_profile(
    module_stack: ScalableModuleStack | None,
    config: ScenarioConfig,
    *,
    online_truth_guard_implementation: str,
) -> dict[str, Any]:
    base = {
        "online_truth_guard_implementation": str(
            online_truth_guard_implementation
        )
    }
    if module_stack is None:
        return {
            "schema_version": "scalable3d-episode-runtime-profile-v1",
            **base,
        }
    scenario_provider = getattr(
        module_stack,
        "runtime_manifest_profile_for_scenario",
        None,
    )
    if callable(scenario_provider):
        profile = scenario_provider(config)
        if not isinstance(profile, Mapping):
            raise TypeError("runtime manifest profile must be a mapping")
        return {**dict(profile), **base}
    provider = getattr(module_stack, "runtime_manifest_profile", None)
    if not callable(provider):
        return {
            "schema_version": "scalable3d-episode-runtime-profile-v1",
            **base,
        }
    profile = provider()
    if not isinstance(profile, Mapping):
        raise TypeError("runtime manifest profile must be a mapping")
    return {**dict(profile), **base}


def _observation_governance_audit(
    module_stack: ScalableModuleStack | None,
) -> dict[str, Any] | None:
    provider = getattr(module_stack, "observation_governance_audit", None)
    if not callable(provider):
        return None
    audit = provider()
    if not isinstance(audit, Mapping):
        raise TypeError("observation governance audit must be a mapping")
    if int(audit.get("online_truth_use_count", -1)) != 0:
        raise ValueError("observation governance audit reports online truth use")
    return dict(audit)


def _refresh_camera_runtime_states(
    states: dict[str, CameraRuntimeState],
    *,
    config: ScenarioConfig,
    snapshot: Any,
    timestamp: float,
) -> None:
    active_ids: set[str] = set()
    for platform_kind, platform_snapshot, prefix, default_fov in (
        (
            "interceptor",
            snapshot.interceptors,
            "CAM-INT-",
            config.camera_horizontal_fov_deg,
        ),
        (
            "recon",
            snapshot.recon,
            "CAM-RECON-",
            config.recon_camera_horizontal_fov_deg,
        ),
    ):
        digits = 4 if platform_kind == "interceptor" else 3
        for index, (resource_id, active) in enumerate(
            zip(platform_snapshot.entity_ids, platform_snapshot.active)
        ):
            if not bool(active):
                continue
            camera_id = f"{prefix}{index + 1:0{digits}d}"
            active_ids.add(camera_id)
            existing = states.get(camera_id)
            if existing is not None:
                states[camera_id] = replace(existing, timestamp=float(timestamp))
                continue
            position = np.asarray(platform_snapshot.position_ned[index], dtype=float)
            if platform_kind == "interceptor":
                direction = np.asarray(platform_snapshot.velocity_ned[index], dtype=float)
                if float(np.linalg.norm(direction)) < 1.0e-9:
                    direction = np.array([1.0, 0.0, 0.0], dtype=float)
            else:
                direction = np.array([0.0, 0.0, -150.0], dtype=float) - position
            yaw_deg, pitch_deg = _angles_from_direction(direction)
            states[camera_id] = CameraRuntimeState(
                camera_id=camera_id,
                resource_id=str(resource_id),
                platform_kind=platform_kind,
                timestamp=float(timestamp),
                yaw_deg=yaw_deg,
                pitch_deg=pitch_deg,
                horizontal_fov_deg=float(default_fov),
            )
    for camera_id in tuple(states):
        if camera_id not in active_ids:
            del states[camera_id]


def _camera_aim_points(
    states: dict[str, CameraRuntimeState],
    snapshot: Any,
) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    for camera_id, state in states.items():
        position = _camera_platform_position(state, snapshot)
        result[camera_id] = position + _direction_from_angles(
            state.yaw_deg,
            state.pitch_deg,
        ) * 1_000.0
    return result


def _apply_camera_commands(
    states: dict[str, CameraRuntimeState],
    commands: tuple[CameraObservationCommand, ...],
    *,
    snapshot: Any,
    current_timestamp: float,
) -> tuple[dict[str, Any], ...]:
    acknowledgements: list[dict[str, Any]] = []
    for command in commands:
        state = states.get(command.camera_id)
        reason: str | None = None
        if state is None or state.resource_id != command.resource_id:
            reason = "camera_or_resource_unavailable"
        elif current_timestamp + 1.0e-9 < command.issued_timestamp:
            reason = "command_issued_in_future"
        elif current_timestamp >= command.expires_timestamp - 1.0e-9:
            reason = "command_expired"
        elif command.plan_version < state.last_plan_version:
            reason = "stale_plan_version"
        elif (
            command.plan_version == state.last_plan_version
            and command.coalition_version < state.last_coalition_version
        ):
            reason = "stale_coalition_version"
        elif command.communication_version < state.last_communication_version:
            reason = "stale_communication_version"

        if reason is None and state is not None:
            platform_position = _camera_platform_position(state, snapshot)
            direction = command.aim_point_ned - platform_position
            if float(np.linalg.norm(direction)) < 1.0e-6:
                reason = "degenerate_aim_point"
            else:
                yaw_deg, pitch_deg = _angles_from_direction(direction)
                states[command.camera_id] = CameraRuntimeState(
                    camera_id=state.camera_id,
                    resource_id=state.resource_id,
                    platform_kind=state.platform_kind,
                    timestamp=float(current_timestamp),
                    yaw_deg=yaw_deg,
                    pitch_deg=pitch_deg,
                    horizontal_fov_deg=command.horizontal_fov_deg,
                    fov_mode=command.fov_mode,
                    last_plan_version=command.plan_version,
                    last_coalition_version=command.coalition_version,
                    last_communication_version=command.communication_version,
                )

        acknowledgements.append(
            {
                "camera_id": command.camera_id,
                "resource_id": command.resource_id,
                "issued_timestamp": command.issued_timestamp,
                "ack_timestamp": float(current_timestamp),
                "expires_timestamp": command.expires_timestamp,
                "plan_version": command.plan_version,
                "coalition_version": command.coalition_version,
                "communication_version": command.communication_version,
                "command_version": command.communication_version,
                "intent": command.intent,
                "target_global_track_id": command.target_global_track_id,
                "requested_mode": command.requested_mode,
                "effective_mode": command.effective_mode,
                "status": "applied" if reason is None else "rejected",
                "reason": "accepted" if reason is None else reason,
            }
        )
    return tuple(acknowledgements)


def _assignment_plan_runtime_ack(
    publications: tuple[Any, ...],
    *,
    source_envelopes: tuple[VersionedEnvelope, ...],
    ack_timestamp: float,
) -> dict[str, Any] | None:
    """Bind one newly published D3 plan to the D7 commands consumed by main.

    The acknowledgement is an online, truth-free execution record. It proves
    that main accepted a versioned plan and records which assignment bindings
    reached D7 in the same scheduler tick. It does not claim physical
    interception success or provide an offline reward.
    """

    d3_publications = tuple(
        item
        for item in publications
        if getattr(item, "topic", None) == "modules.d3.assignment_plan"
    )
    if not d3_publications:
        return None
    if len(d3_publications) != 1:
        raise RuntimeError("one scheduler tick published multiple D3 plans")
    d3_publication = d3_publications[0]
    plan = _runtime_publication_payload(d3_publication, "D3 plan")
    d3_envelope = _single_source_envelope(
        source_envelopes,
        topic="modules.d3.assignment_plan",
        required=True,
    )
    assignments = plan.get("assignments")
    if not isinstance(assignments, list):
        raise ValueError("D3 plan publication assignments must be a list")

    d7_publications = tuple(
        item
        for item in publications
        if getattr(item, "topic", None) == "modules.d7.guidance_commands"
    )
    if len(d7_publications) > 1:
        raise RuntimeError("one scheduler tick published multiple D7 command batches")
    d7_commands: list[Any] = []
    if d7_publications:
        d7_payload = _runtime_publication_payload(
            d7_publications[0], "D7 guidance batch"
        )
        raw_commands = d7_payload.get("commands")
        if not isinstance(raw_commands, list):
            raise ValueError("D7 guidance publication commands must be a list")
        d7_commands = raw_commands
    d7_envelope = _single_source_envelope(
        source_envelopes,
        topic="modules.d7.guidance_commands",
        required=bool(d7_publications),
    )

    plan_id = str(plan.get("plan_id", "")).strip()
    plan_version = _nonnegative_int(plan.get("plan_version"), "plan_version")
    if not plan_id:
        raise ValueError("D3 plan runtime ACK requires plan_id")

    commands_by_binding: dict[tuple[str, str], Mapping[str, Any]] = {}
    for raw_command in d7_commands:
        command = _runtime_mapping(raw_command, "D7 guidance command")
        command_plan_id = str(command.get("plan_id", "")).strip()
        command_plan_version = _nonnegative_int(
            command.get("plan_version"), "D7 command plan_version"
        )
        if command_plan_id != plan_id or command_plan_version != plan_version:
            raise ValueError(
                "D7 guidance command does not reference the current D3 plan"
            )
        key = (
            str(command.get("resource_id", "")).strip(),
            str(command.get("global_track_id", "")).strip(),
        )
        if not all(key) or key in commands_by_binding:
            raise ValueError("D7 guidance command binding is missing or duplicated")
        commands_by_binding[key] = command

    binding_acks: list[dict[str, Any]] = []
    expected_bindings: set[tuple[str, str]] = set()
    for raw_assignment in assignments:
        assignment = _runtime_mapping(raw_assignment, "D3 assignment")
        key = (
            str(assignment.get("resource_id", "")).strip(),
            str(assignment.get("global_track_id", "")).strip(),
        )
        if not all(key) or key in expected_bindings:
            raise ValueError("D3 assignment binding is missing or duplicated")
        expected_bindings.add(key)
        command = commands_by_binding.get(key)
        mode = None if command is None else str(command.get("mode", "")).strip()
        held = bool(command is None or mode == "hold")
        binding_acks.append(
            {
                "resource_id": key[0],
                "global_track_id": key[1],
                "coalition_id": assignment.get("coalition_id"),
                "coalition_version": assignment.get("coalition_version"),
                "member_role": assignment.get("member_role"),
                "guidance_command_present": command is not None,
                "guidance_mode": mode,
                "guidance_gate_reason": (
                    None if command is None else command.get("gate_reason")
                ),
                "control_applied_to_world": command is not None,
                "held": held,
            }
        )

    extra_commands = sorted(set(commands_by_binding) - expected_bindings)
    if extra_commands:
        raise ValueError("D7 guidance batch contains bindings absent from D3 plan")

    metadata = _runtime_mapping(plan.get("metadata", {}), "D3 plan metadata")
    binding_ack_count = sum(
        bool(item["guidance_command_present"]) for item in binding_acks
    )
    control_applied_count = sum(
        bool(item["control_applied_to_world"]) for item in binding_acks
    )
    held_count = sum(bool(item["held"]) for item in binding_acks)
    return {
        "decision_id": f"{plan_id}:v{plan_version}",
        "ack_timestamp": float(ack_timestamp),
        "plan_id": plan_id,
        "plan_version": plan_version,
        "plan_created_at": float(plan.get("created_at", ack_timestamp)),
        "plan_schema_version": str(
            getattr(d3_publication, "schema_version", "")
        ),
        "source_plan_bus_sequence": int(d3_envelope.sequence),
        "source_plan_payload_sha256": _runtime_payload_sha256(plan),
        "source_guidance_bus_sequence": (
            None if d7_envelope is None else int(d7_envelope.sequence)
        ),
        "source_guidance_payload_sha256": (
            None
            if d7_envelope is None
            else _runtime_payload_sha256(d7_envelope.payload)
        ),
        "accepted": True,
        "status_code": "accepted_by_main_runtime",
        "assignment_count": len(assignments),
        "binding_ack_count": binding_ack_count,
        "fully_bound_to_guidance": binding_ack_count == len(assignments),
        "control_applied_binding_count": control_applied_count,
        "held_binding_count": held_count,
        "active_plan_owner": metadata.get("active_plan_owner"),
        "owner_node_id": metadata.get("owner_node_id"),
        "authority_epoch": metadata.get("authority_epoch"),
        "lease_expires_at_s": metadata.get("lease_expires_at_s"),
        "d3_learning_evidence": {
            "mode": metadata.get("learning_mode"),
            "applied": _optional_bool(metadata.get("learning_applied")),
            "shadow_only": _optional_bool(
                metadata.get("learning_shadow_only")
            ),
            "bundle_loaded": _optional_bool(
                metadata.get("learning_bundle_loaded")
            ),
            "fallback_reason": metadata.get("learning_fallback_reason"),
            "model_fingerprint": metadata.get("learning_model_fingerprint"),
        },
        "d4_regional_hint_evidence": {
            "considered": _optional_bool(
                metadata.get("regional_hint_considered")
            ),
            "applied": _optional_bool(metadata.get("regional_hint_applied")),
            "rejected": _optional_bool(
                metadata.get("regional_hint_rejected")
            ),
            "fallback_reason": metadata.get(
                "regional_hint_fallback_reason"
            ),
            "advisory_id": metadata.get("regional_hint_advisory_id"),
            "advisory_version": metadata.get(
                "regional_hint_advisory_version"
            ),
            "source_plan_id": metadata.get("regional_hint_source_plan_id"),
            "source_plan_version": metadata.get(
                "regional_hint_source_plan_version"
            ),
        },
        "binding_acks": binding_acks,
        "physical_outcome_available": False,
        "reward_available": False,
    }


def _runtime_publication_payload(publication: Any, name: str) -> Mapping[str, Any]:
    return _runtime_mapping(getattr(publication, "payload", None), name)


def _runtime_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _single_source_envelope(
    envelopes: tuple[VersionedEnvelope, ...],
    *,
    topic: str,
    required: bool,
) -> VersionedEnvelope | None:
    matches = tuple(item for item in envelopes if item.topic == topic)
    if len(matches) > 1:
        raise RuntimeError(f"one scheduler tick published multiple {topic} envelopes")
    if not matches:
        if required:
            raise RuntimeError(f"runtime ACK is missing source envelope: {topic}")
        return None
    return matches[0]


def _runtime_payload_sha256(value: Any) -> str:
    encoded = json.dumps(
        jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be a non-negative integer")
    result = int(value)
    if result < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return result


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    result = float(value)
    if not np.isfinite(result):
        raise ValueError("optional float must be finite")
    return result


def _camera_platform_position(state: CameraRuntimeState, snapshot: Any) -> np.ndarray:
    platform = snapshot.interceptors if state.platform_kind == "interceptor" else snapshot.recon
    try:
        index = tuple(platform.entity_ids).index(state.resource_id)
    except ValueError as exc:
        raise ValueError(f"camera resource is absent from world snapshot: {state.resource_id}") from exc
    return np.asarray(platform.position_ned[index], dtype=float)


def _angles_from_direction(direction_ned: np.ndarray) -> tuple[float, float]:
    vector = np.asarray(direction_ned, dtype=float).reshape(3)
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm < 1.0e-9:
        raise ValueError("camera direction must be finite and non-zero")
    unit = vector / norm
    yaw_deg = float(np.degrees(np.arctan2(unit[1], unit[0])))
    pitch_deg = float(np.degrees(np.arctan2(-unit[2], np.linalg.norm(unit[:2]))))
    return float(np.clip(yaw_deg, -180.0, 180.0)), float(
        np.clip(pitch_deg, -89.9, 89.9)
    )


def _direction_from_angles(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    yaw = np.radians(float(yaw_deg))
    pitch = np.radians(float(pitch_deg))
    return np.array(
        [
            np.cos(pitch) * np.cos(yaw),
            np.cos(pitch) * np.sin(yaw),
            -np.sin(pitch),
        ],
        dtype=float,
    )
