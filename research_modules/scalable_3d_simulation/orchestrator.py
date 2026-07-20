"""Main-owned scheduler for scalable three-dimensional point-mass episodes."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
from pathlib import Path
import time
from typing import Any

import numpy as np

from .episode_bus import (
    EpisodeManifest,
    InMemoryEpisodeBus,
    VersionedEnvelope,
    build_episode_manifest,
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
    proximity_intercepts: tuple[ProximityInterceptEvent, ...]
    online_messages: tuple[VersionedEnvelope, ...]
    offline_truth_labels: tuple[OfflineTruthLabel, ...]
    stage_timings: tuple[StageTiming, ...]
    summary: dict[str, Any]
    output_paths: dict[str, Path] | None = None


class _TimingAccumulator:
    def __init__(self) -> None:
        self.total: dict[str, float] = {}
        self.calls: dict[str, int] = {}

    def add(self, stage: str, elapsed_s: float) -> None:
        self.total[stage] = self.total.get(stage, 0.0) + float(elapsed_s)
        self.calls[stage] = self.calls.get(stage, 0) + 1

    def merge_total(self, stage: str, *, wall_time_s: float, call_count: int) -> None:
        """Merge a cumulative child-stage record without losing its call count."""

        if call_count < 0 or wall_time_s < 0.0:
            raise ValueError("timing totals must be non-negative")
        self.total[stage] = self.total.get(stage, 0.0) + float(wall_time_s)
        self.calls[stage] = self.calls.get(stage, 0) + int(call_count)

    def records(self) -> tuple[StageTiming, ...]:
        return tuple(
            StageTiming(stage, self.calls[stage], self.total[stage])
            for stage in sorted(self.total)
        )


class Scalable3DEpisodeRunner:
    """Advance the world and asynchronous sensor clocks on one deterministic timeline."""

    def __init__(
        self,
        config: ScenarioConfig,
        *,
        module_stack: ScalableModuleStack | None = None,
    ) -> None:
        self.config = config
        self.world = VectorizedPointMassWorld(config)
        self.sensor_scene = SensorScene(config)
        self.bus = InMemoryEpisodeBus()
        self.manifest = build_episode_manifest(config)
        self.module_stack = module_stack

    def run(self) -> EpisodeResult:
        """Run a world/sensor baseline without D1-D7 algorithm shortcuts."""

        self.world.reset()
        self.sensor_scene.reset()
        self.bus.clear()
        if self.module_stack is not None:
            self.module_stack.reset(self.config)
        timing = _TimingAccumulator()
        pending: list[tuple[float, int, OnlineSensorBatch]] = []
        pending_counter = 0
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

        for step_index in range(step_count):
            snapshot = self.world.snapshot()
            current_time = snapshot.timestamp
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
                batch = self.sensor_scene.visual_scan(snapshot)
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
                self.bus.publish(
                    topic="sensor.observations",
                    source=online_batch.sensor_id,
                    timestamp=online_batch.arrival_timestamp,
                    schema_version=ONLINE_OBSERVATION_SCHEMA_VERSION,
                    payload=online_batch,
                    copy_payload=False,
                )
                arrived_batches.append(online_batch)
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
                        )
                    ).validated(
                        resource_count=self.config.resource_count,
                        recon_count=self.config.recon_count,
                    )
                    interceptor_command = module_output.interceptor_acceleration_ned
                    recon_command = module_output.recon_acceleration_ned
                    last_module_diagnostics = dict(module_output.diagnostics)
                    for publication in module_output.publications:
                        self.bus.publish(
                            topic=publication.topic,
                            source=publication.source,
                            timestamp=current_time,
                            schema_version=publication.schema_version,
                            payload=publication.payload,
                        )
                        module_publication_count += 1
                        module_publication_topic_counts[publication.topic] = (
                            module_publication_topic_counts.get(publication.topic, 0) + 1
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

        elapsed = time.perf_counter() - episode_start
        diagnostics = self.world.diagnostics()
        messages = self.bus.messages()
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
            "online_truth_use_count": 0,
            "module_stack_enabled": self.module_stack is not None,
            "module_publication_count": module_publication_count,
            "module_publication_topic_counts": dict(
                sorted(module_publication_topic_counts.items())
            ),
            "module_final_diagnostics": last_module_diagnostics,
            "control_command_tick_count": control_command_tick_count,
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
            proximity_intercepts=tuple(proximity_intercepts),
            online_messages=messages,
            offline_truth_labels=tuple(offline_labels),
            stage_timings=timing.records(),
            summary=summary,
        )


def run_episode(
    config: ScenarioConfig,
    *,
    output_dir: str | Path | None = None,
    write_plot: bool = False,
    animation_formats: tuple[str, ...] = (),
    module_stack: ScalableModuleStack | None = None,
) -> EpisodeResult:
    """Run one baseline episode and optionally persist its reproducibility bundle."""

    result = Scalable3DEpisodeRunner(config, module_stack=module_stack).run()
    if output_dir is None:
        return result
    from .reporting import write_episode_outputs

    paths = write_episode_outputs(
        result,
        Path(output_dir),
        write_plot=write_plot,
        animation_formats=animation_formats,
    )
    return EpisodeResult(
        config=result.config,
        manifest=result.manifest,
        timestamps=result.timestamps,
        intruder_state_history=result.intruder_state_history,
        interceptor_state_history=result.interceptor_state_history,
        recon_state_history=result.recon_state_history,
        intruder_active_history=result.intruder_active_history,
        proximity_intercepts=result.proximity_intercepts,
        online_messages=result.online_messages,
        offline_truth_labels=result.offline_truth_labels,
        stage_timings=result.stage_timings,
        summary=result.summary,
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
