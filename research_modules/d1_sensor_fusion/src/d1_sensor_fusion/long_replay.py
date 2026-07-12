from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

import numpy as np

from .fusion import FusionAdapter
from .motion import wrap_angle
from .observations import (
    CameraModel,
    acoustic_covariance,
    acoustic_h,
    eo_covariance_from_bbox,
    eo_project,
    radar_covariance_from_range,
    radar_h,
)
from .quality import summarize_region_quality_windows
from .replay import (
    REPLAY_SCHEMA_VERSION,
    ReplayProvenance,
    build_governed_replay_manifest,
    summarize_sensor_observation_latency_audit,
)
from .types import SensorObservation, SensorTimingExpectation


LONG_REPLAY_SCENARIO_ID = "d1-long-crossing-occlusion-oosm"
LONG_REPLAY_SCENARIO_VERSION = "d1.long_replay_scenario.v1"
LONG_REPLAY_CONFIG_VERSION = "d1.long_replay_config.v1"
LONG_REPLAY_SUMMARY_SCHEMA_VERSION = "d1.long_replay_summary.v1"
LONG_REPLAY_OFFLINE_TRUTH_SCHEMA_VERSION = "d1.long_replay_offline_truth.v1"
LONG_REPLAY_THRESHOLD_PROFILE_VERSION = "d1.long_replay_thresholds.v1"

_THRESHOLD_PROFILE = {
    "region_window_size_s": 5.0,
    "covariance_growth_threshold": 2.5,
    "freshness_growth_threshold": 0.20,
    "readiness_drop_threshold": 0.10,
    "radar_expected_latency_s": 0.35,
    "radar_latency_tolerance_s": 0.20,
    "acoustic_expected_latency_s": 0.18,
    "acoustic_latency_tolerance_s": 0.12,
    "eo_expected_latency_s": 0.10,
    "eo_latency_tolerance_s": 0.08,
}


@dataclass(frozen=True)
class LongReplayConfig:
    """Frozen synthetic challenge configuration callable by main.

    The generated online observations never carry truth/actor/object identity.
    Truth is returned in an explicit sidecar for offline scoring only.
    """

    target_count: int = 3
    duration_s: float = 60.0
    sample_period_s: float = 0.5
    radar_period_s: float = 0.5
    acoustic_period_s: float = 1.0
    eo_period_s: float = 0.5
    crossing_time_fraction: float = 0.5
    eo_occlusion_half_width_s: float = 2.0
    eo_partial_occlusion_margin_s: float = 2.0
    radar_oosm_interval_frames: int = 17
    radar_oosm_extra_delay_s: float = 1.25
    relay_duplicate_interval_frames: int = 41
    seed: int = 7

    def __post_init__(self) -> None:
        if int(self.target_count) < 1:
            raise ValueError("target_count must be positive")
        for name in (
            "duration_s",
            "sample_period_s",
            "radar_period_s",
            "acoustic_period_s",
            "eo_period_s",
        ):
            if float(getattr(self, name)) <= 0.0:
                raise ValueError(f"{name} must be positive")
        if not 0.1 <= float(self.crossing_time_fraction) <= 0.9:
            raise ValueError("crossing_time_fraction must be in [0.1, 0.9]")
        if float(self.eo_occlusion_half_width_s) < 0.0:
            raise ValueError("eo_occlusion_half_width_s must be non-negative")
        if float(self.eo_partial_occlusion_margin_s) < 0.0:
            raise ValueError("eo_partial_occlusion_margin_s must be non-negative")
        if int(self.radar_oosm_interval_frames) < 1:
            raise ValueError("radar_oosm_interval_frames must be positive")
        if int(self.relay_duplicate_interval_frames) < 1:
            raise ValueError("relay_duplicate_interval_frames must be positive")


@dataclass
class LongReplayScenario:
    config: LongReplayConfig
    provenance: ReplayProvenance
    observations: list[SensorObservation]
    offline_truth: dict[str, Any]
    event_counts: dict[str, int]

    def governed_manifest(self) -> dict[str, Any]:
        return build_governed_replay_manifest(self.observations, self.provenance)


@dataclass(frozen=True)
class LongReplaySummary:
    schema_version: str
    scenario_id: str
    scenario_version: str
    replay_schema_version: str
    config_version: str
    config_digest: str
    threshold_profile_version: str
    threshold_profile: dict[str, float]
    seed: int
    duration_s: float
    target_count: int
    observation_count: int
    modality_counts: dict[str, int]
    event_counts: dict[str, int]
    raw_latency_audit: dict[str, Any]
    fusion_latency_audit: dict[str, Any]
    sensor_health: list[dict[str, Any]]
    final_track_count: int
    final_track_levels: dict[str, int]
    final_source_support: dict[str, int]
    region_quality_windows: list[dict[str, Any]]
    online_truth_leak_count: int
    metric_availability: dict[str, dict[str, Any]]
    manifest_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_long_replay_scenario(config: LongReplayConfig | None = None) -> LongReplayScenario:
    """Build deterministic crossing/occlusion/delay/OOSM replay inputs.

    This is a D1-owned synthetic calibration fixture, not an AirSim connection.
    Main may serialize ``observations`` with the existing governed writer and
    persist ``offline_truth`` separately for D6 scoring.
    """

    cfg = config or LongReplayConfig()
    rng = np.random.default_rng(cfg.seed)
    times, truth_tracks = _generate_crossing_truth(cfg)
    config_payload = asdict(cfg)
    config_digest = _digest(config_payload)
    scenario_digest = _digest(
        {
            "scenario_id": LONG_REPLAY_SCENARIO_ID,
            "scenario_version": LONG_REPLAY_SCENARIO_VERSION,
            "config": config_payload,
        }
    )
    provenance = ReplayProvenance(
        scenario_id=LONG_REPLAY_SCENARIO_ID,
        scenario_version=LONG_REPLAY_SCENARIO_VERSION,
        config_id="d1-long-replay",
        config_digest=config_digest,
        config_version=LONG_REPLAY_CONFIG_VERSION,
        scenario_digest=scenario_digest,
        run_id=f"seed-{cfg.seed:06d}",
        seed=cfg.seed,
        source_format="d1_synthetic_long_replay",
        producer="d1",
        metadata={
            "threshold_profile_version": LONG_REPLAY_THRESHOLD_PROFILE_VERSION,
            "online_truth_policy": "stripped",
        },
    )

    observations: list[SensorObservation] = []
    labels: dict[str, str] = {}
    events: Counter[str] = Counter()
    observation_sequence = 0
    crossing_time = cfg.duration_s * cfg.crossing_time_fraction
    radar_position = np.array([0.0, 0.0, 0.0], dtype=float)
    acoustic_position = np.array([40.0, -90.0, -5.0], dtype=float)
    camera = CameraModel(position_ned=np.array([0.0, 0.0, -20.0], dtype=float))
    camera_payload = _camera_payload(camera)

    for target_index, states in enumerate(truth_tracks):
        for frame_index, (timestamp, state) in enumerate(zip(times, states)):
            timestamp = float(timestamp)
            coverage_cell = _coverage_cell(state[:3], crossing_time, timestamp)

            if _is_sample(frame_index, cfg.sample_period_s, cfg.radar_period_s):
                observation_sequence += 1
                ideal = radar_h(state, radar_position)
                covariance = radar_covariance_from_range(float(ideal[0]))
                flags: tuple[str, ...] = ()
                covariance_reason = "range_dependent"
                if abs(timestamp - crossing_time) <= 4.0:
                    covariance = covariance * 2.25
                    flags = ("clutter",)
                    covariance_reason = "range_and_crossing_clutter"
                    events["radar_clutter_observation_count"] += 1
                measurement = ideal + rng.multivariate_normal(np.zeros(4), covariance)
                measurement[1] = wrap_angle(measurement[1])
                measurement[2] = wrap_angle(measurement[2])
                delay = max(0.02, float(rng.normal(0.35, 0.06)))
                oosm_injected = frame_index > 0 and (
                    frame_index % cfg.radar_oosm_interval_frames == 0
                )
                if oosm_injected:
                    delay += cfg.radar_oosm_extra_delay_s
                    events["radar_oosm_injected_count"] += 1
                lineage = ["radar-ground-01", f"payload-{observation_sequence:08d}"]
                observation = _observation(
                    sequence=observation_sequence,
                    sensor_id="radar-ground-01",
                    modality="radar",
                    measurement_timestamp=timestamp,
                    arrival_timestamp=timestamp + delay,
                    frame_id="ned",
                    measurement=measurement,
                    covariance=covariance,
                    confidence=0.76 if flags else 0.92,
                    quality_flags=flags,
                    coverage_cell=coverage_cell,
                    lineage=lineage,
                    metadata={
                        "sensor_position_ned": radar_position.tolist(),
                        "covariance_scale_reason": covariance_reason,
                        "expected_latency_s": _THRESHOLD_PROFILE["radar_expected_latency_s"],
                        "latency_tolerance_s": _THRESHOLD_PROFILE["radar_latency_tolerance_s"],
                        "oosm_expected": True,
                        "oosm_injected": oosm_injected,
                    },
                    source_node_id="radar-site-01",
                    link_type="c2_data",
                    stale_after_s=1.20,
                )
                observations.append(observation)
                labels[observation.observation_id] = f"offline-target-{target_index + 1:03d}"
                events["radar_observation_count"] += 1

                if frame_index > 0 and frame_index % cfg.relay_duplicate_interval_frames == 0:
                    observation_sequence += 1
                    duplicate = _observation(
                        sequence=observation_sequence,
                        sensor_id=observation.sensor_id,
                        modality=observation.modality,
                        measurement_timestamp=observation.measurement_timestamp,
                        arrival_timestamp=observation.arrival_timestamp + 0.04,
                        frame_id=observation.frame_id,
                        measurement=observation.measurement.copy(),
                        covariance=observation.covariance.copy(),
                        confidence=observation.confidence,
                        quality_flags=observation.quality_flags,
                        coverage_cell=coverage_cell,
                        lineage=lineage,
                        metadata={
                            **observation.metadata,
                            "relay_duplicate": True,
                        },
                        source_node_id="radar-site-01",
                        relay_node_id="secondary-recon-01",
                        link_type="relay_data",
                        stale_after_s=1.20,
                    )
                    observations.append(duplicate)
                    labels[duplicate.observation_id] = labels[observation.observation_id]
                    events["relay_duplicate_injected_count"] += 1

            if _is_sample(frame_index, cfg.sample_period_s, cfg.acoustic_period_s):
                observation_sequence += 1
                confidence = float(rng.uniform(0.58, 0.84))
                covariance = acoustic_covariance(confidence)
                ideal = acoustic_h(state, acoustic_position)
                measurement = np.array(
                    [wrap_angle(ideal[0] + rng.normal(0.0, np.sqrt(covariance[0, 0])))],
                    dtype=float,
                )
                delay = max(0.02, float(rng.normal(0.18, 0.04)))
                observation = _observation(
                    sequence=observation_sequence,
                    sensor_id="acoustic-array-01",
                    modality="acoustic",
                    measurement_timestamp=timestamp,
                    arrival_timestamp=timestamp + delay,
                    frame_id="ned",
                    measurement=measurement,
                    covariance=covariance,
                    confidence=confidence,
                    quality_flags=("coarse_bearing",),
                    coverage_cell=coverage_cell,
                    lineage=["acoustic-array-01", f"payload-{observation_sequence:08d}"],
                    metadata={
                        "sensor_position_ned": acoustic_position.tolist(),
                        "covariance_scale_reason": "confidence_dependent_bearing",
                        "expected_latency_s": _THRESHOLD_PROFILE["acoustic_expected_latency_s"],
                        "latency_tolerance_s": _THRESHOLD_PROFILE[
                            "acoustic_latency_tolerance_s"
                        ],
                        "oosm_expected": False,
                    },
                    source_node_id="acoustic-site-01",
                    link_type="c2_data",
                    stale_after_s=0.70,
                    classification_hint="small_uas",
                )
                observations.append(observation)
                labels[observation.observation_id] = f"offline-target-{target_index + 1:03d}"
                events["acoustic_observation_count"] += 1

            if _is_sample(frame_index, cfg.sample_period_s, cfg.eo_period_s):
                events["eo_expected_observation_count"] += 1
                occlusion_distance = abs(timestamp - crossing_time)
                if occlusion_distance <= cfg.eo_occlusion_half_width_s:
                    events["eo_occlusion_drop_count"] += 1
                    continue
                pixel = eo_project(state, camera)
                rel = state[:3] - camera.position_ned
                point_camera = camera.rotation_world_to_camera @ rel
                if (
                    point_camera[2] <= 1.0
                    or pixel[0] < 0.0
                    or pixel[0] > camera.width
                    or pixel[1] < 0.0
                    or pixel[1] > camera.height
                ):
                    events["eo_out_of_fov_count"] += 1
                    continue
                observation_sequence += 1
                distance = max(float(np.linalg.norm(rel)), 1.0)
                box_size = float(np.clip(6200.0 / distance, 7.0, 90.0))
                bbox = np.array(
                    [
                        pixel[0] - box_size / 2.0,
                        pixel[1] - box_size * 0.35,
                        pixel[0] + box_size / 2.0,
                        pixel[1] + box_size * 0.35,
                    ],
                    dtype=float,
                )
                flags_list: list[str] = []
                if box_size < 14.0:
                    flags_list.append("small_bbox")
                if occlusion_distance <= (
                    cfg.eo_occlusion_half_width_s + cfg.eo_partial_occlusion_margin_s
                ):
                    flags_list.append("partial_occlusion")
                    events["eo_partial_occlusion_observation_count"] += 1
                flags = tuple(flags_list)
                confidence = float(
                    np.clip(0.93 - 0.0012 * distance + rng.normal(0.0, 0.025), 0.42, 0.95)
                )
                covariance = eo_covariance_from_bbox(bbox, confidence, flags)
                measurement = pixel + rng.multivariate_normal(np.zeros(2), covariance)
                delay = max(0.01, float(rng.normal(0.10, 0.025)))
                observation = _observation(
                    sequence=observation_sequence,
                    sensor_id="eo-camera-01",
                    modality="eo",
                    measurement_timestamp=timestamp,
                    arrival_timestamp=timestamp + delay,
                    frame_id="pixel",
                    measurement=measurement,
                    covariance=covariance,
                    confidence=confidence,
                    quality_flags=flags,
                    coverage_cell=coverage_cell,
                    lineage=["eo-camera-01", f"payload-{observation_sequence:08d}"],
                    metadata={
                        "bbox": bbox.tolist(),
                        "camera_model": camera_payload,
                        "covariance_scale_reason": (
                            "bbox_confidence_partial_occlusion"
                            if "partial_occlusion" in flags
                            else "bbox_confidence"
                        ),
                        "expected_latency_s": _THRESHOLD_PROFILE["eo_expected_latency_s"],
                        "latency_tolerance_s": _THRESHOLD_PROFILE["eo_latency_tolerance_s"],
                        "oosm_expected": False,
                    },
                    source_node_id="secondary-recon-01",
                    link_type="video_metadata",
                    stale_after_s=0.35,
                )
                observations.append(observation)
                labels[observation.observation_id] = f"offline-target-{target_index + 1:03d}"
                events["eo_observation_count"] += 1

    observations.sort(
        key=lambda observation: (
            observation.arrival_timestamp,
            observation.measurement_timestamp,
            observation.observation_id,
        )
    )
    offline_truth = {
        "schema_version": LONG_REPLAY_OFFLINE_TRUTH_SCHEMA_VERSION,
        "scenario_id": LONG_REPLAY_SCENARIO_ID,
        "scenario_version": LONG_REPLAY_SCENARIO_VERSION,
        "seed": cfg.seed,
        "observation_labels": labels,
        "tracks": {
            f"offline-target-{index + 1:03d}": {
                "times": times.tolist(),
                "states_ned": states.tolist(),
            }
            for index, states in enumerate(truth_tracks)
        },
    }
    return LongReplayScenario(
        config=cfg,
        provenance=provenance,
        observations=observations,
        offline_truth=offline_truth,
        event_counts=dict(sorted(events.items())),
    )


def summarize_long_replay(
    scenario: LongReplayScenario,
    adapter: FusionAdapter | None = None,
) -> LongReplaySummary:
    """Replay one challenge scenario and publish D1/D6-consumable summaries."""

    fusion = adapter or FusionAdapter(
        use_truth_hints_for_association=False,
        sensor_timing_expectations={
            "radar-ground-01": SensorTimingExpectation(
                _THRESHOLD_PROFILE["radar_expected_latency_s"],
                _THRESHOLD_PROFILE["radar_latency_tolerance_s"],
                oosm_expected=True,
            ),
            "acoustic-array-01": SensorTimingExpectation(
                _THRESHOLD_PROFILE["acoustic_expected_latency_s"],
                _THRESHOLD_PROFILE["acoustic_latency_tolerance_s"],
            ),
            "eo-camera-01": SensorTimingExpectation(
                _THRESHOLD_PROFILE["eo_expected_latency_s"],
                _THRESHOLD_PROFILE["eo_latency_tolerance_s"],
            ),
        },
    )
    region_snapshots: list[list[Any]] = []
    latency_snapshots: list[Any] = []
    next_snapshot_at = 0.0
    window_size_s = _THRESHOLD_PROFILE["region_window_size_s"]
    for observation in scenario.observations:
        fusion.process(observation)
        if observation.arrival_timestamp + 1e-9 >= next_snapshot_at:
            region_snapshots.append(fusion.region_quality_summaries())
            latency_snapshots.append(fusion.latency_audit_summary())
            next_snapshot_at = observation.arrival_timestamp + window_size_s

    if scenario.observations:
        final_audit = fusion.latency_audit_summary()
        if not latency_snapshots or latency_snapshots[-1].published_at != final_audit.published_at:
            region_snapshots.append(fusion.region_quality_summaries())
            latency_snapshots.append(final_audit)

    windows = summarize_region_quality_windows(
        region_snapshots,
        latency_snapshots,
        covariance_growth_threshold=_THRESHOLD_PROFILE["covariance_growth_threshold"],
        freshness_growth_threshold=_THRESHOLD_PROFILE["freshness_growth_threshold"],
        readiness_drop_threshold=_THRESHOLD_PROFILE["readiness_drop_threshold"],
        window_size_s=window_size_s,
    )
    tracks = fusion.global_tracks()
    track_levels = Counter(track.track_level.value for track in tracks)
    source_support: Counter[str] = Counter()
    for track in tracks:
        source_support.update(track.source_support)
    manifest = scenario.governed_manifest()
    online_truth_leaks = _online_truth_leak_count(scenario.observations, tracks)
    raw_audit = summarize_sensor_observation_latency_audit(scenario.observations)
    fusion_audit = fusion.latency_audit_summary()
    return LongReplaySummary(
        schema_version=LONG_REPLAY_SUMMARY_SCHEMA_VERSION,
        scenario_id=LONG_REPLAY_SCENARIO_ID,
        scenario_version=LONG_REPLAY_SCENARIO_VERSION,
        replay_schema_version=REPLAY_SCHEMA_VERSION,
        config_version=LONG_REPLAY_CONFIG_VERSION,
        config_digest=scenario.provenance.config_digest,
        threshold_profile_version=LONG_REPLAY_THRESHOLD_PROFILE_VERSION,
        threshold_profile=dict(_THRESHOLD_PROFILE),
        seed=scenario.config.seed,
        duration_s=scenario.config.duration_s,
        target_count=scenario.config.target_count,
        observation_count=len(scenario.observations),
        modality_counts=dict(sorted(Counter(obs.modality for obs in scenario.observations).items())),
        event_counts=dict(scenario.event_counts),
        raw_latency_audit=raw_audit.to_dict(),
        fusion_latency_audit=fusion_audit.to_dict(),
        sensor_health=[summary.to_dict() for summary in fusion.sensor_health_summaries()],
        final_track_count=len(tracks),
        final_track_levels=dict(sorted(track_levels.items())),
        final_source_support=dict(sorted(source_support.items())),
        region_quality_windows=[window.to_dict() for window in windows],
        online_truth_leak_count=online_truth_leaks,
        metric_availability={
            "nis": {
                "available": any(track.last_nis is not None for track in tracks),
                "reason": None
                if any(track.last_nis is not None for track in tracks)
                else "no associated measurement update produced NIS",
            },
            "rmse": {
                "available": False,
                "reason": "requires offline D2 canonical-ID mapping; truth is isolated from online fusion",
            },
            "nees": {
                "available": False,
                "reason": "requires offline D2 canonical-ID mapping; truth is isolated from online fusion",
            },
        },
        manifest_digest=_digest(manifest),
    )


def _generate_crossing_truth(config: LongReplayConfig) -> tuple[np.ndarray, list[np.ndarray]]:
    times = np.arange(
        0.0,
        config.duration_s + 0.5 * config.sample_period_s,
        config.sample_period_s,
    )
    crossing_time = config.duration_s * config.crossing_time_fraction
    crossing_position = np.array([180.0, 0.0, -30.0], dtype=float)
    tracks: list[np.ndarray] = []
    for target_index in range(config.target_count):
        heading = 2.0 * np.pi * target_index / max(config.target_count, 1)
        speed = 5.0 + 0.35 * (target_index % 4)
        direction = np.array([np.cos(heading), np.sin(heading), 0.0], dtype=float)
        lateral = np.array([-direction[1], direction[0], 0.0], dtype=float)
        phase = 2.0 * np.pi * times / config.duration_s
        maneuver_amplitude = 4.0 + 0.5 * (target_index % 3)
        states = np.zeros((times.size, 6), dtype=float)
        states[:, :3] = (
            crossing_position
            + np.outer(times - crossing_time, speed * direction)
            + np.outer(np.sin(phase), maneuver_amplitude * lateral)
        )
        states[:, 2] += 1.5 * ((target_index % 3) - 1)
        states[:, 3:] = speed * direction + np.outer(
            np.cos(phase) * (2.0 * np.pi / config.duration_s),
            maneuver_amplitude * lateral,
        )
        tracks.append(states)
    return times, tracks


def _observation(
    *,
    sequence: int,
    sensor_id: str,
    modality: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
    frame_id: str,
    measurement: np.ndarray,
    covariance: np.ndarray,
    confidence: float,
    quality_flags: tuple[str, ...],
    coverage_cell: str,
    lineage: list[str],
    metadata: dict[str, Any],
    source_node_id: str,
    link_type: str,
    stale_after_s: float,
    relay_node_id: str | None = None,
    classification_hint: str | None = None,
) -> SensorObservation:
    return SensorObservation(
        observation_id=f"obs-{sequence:08d}",
        sensor_id=sensor_id,
        modality=modality,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id=frame_id,
        measurement=measurement,
        covariance=covariance,
        classification_hint=classification_hint,
        confidence=confidence,
        quality_flags=quality_flags,
        metadata={
            **metadata,
            "coverage_cell": coverage_cell,
            "source_lineage_key": lineage,
            "working_frame": "ned",
        },
        source_node_id=source_node_id,
        target_node_id="c2-primary",
        relay_node_id=relay_node_id,
        link_type=link_type,
        sent_timestamp=measurement_timestamp,
        received_timestamp=arrival_timestamp,
        payload_kind="bbox" if modality == "eo" else "sensor_observation",
        stale_after_s=stale_after_s,
        source_support={modality: 1},
    )


def _is_sample(frame_index: int, base_period_s: float, sensor_period_s: float) -> bool:
    stride = max(1, int(round(sensor_period_s / base_period_s)))
    return frame_index % stride == 0


def _coverage_cell(position_ned: np.ndarray, crossing_time: float, timestamp: float) -> str:
    if abs(float(timestamp) - crossing_time) <= 8.0:
        return "crossing-core"
    north = "north-positive" if float(position_ned[0]) >= 180.0 else "north-negative"
    east = "east-positive" if float(position_ned[1]) >= 0.0 else "east-negative"
    return f"{north}:{east}"


def _camera_payload(camera: CameraModel) -> dict[str, Any]:
    return {
        "position_ned": camera.position_ned.tolist(),
        "rotation_world_to_camera": camera.rotation_world_to_camera.tolist(),
        "fx": camera.fx,
        "fy": camera.fy,
        "cx": camera.cx,
        "cy": camera.cy,
        "width": camera.width,
        "height": camera.height,
    }


def _online_truth_leak_count(
    observations: Iterable[SensorObservation],
    tracks: Iterable[Any],
) -> int:
    count = 0
    for observation in observations:
        count += _truth_key_count(observation.metadata)
    for track in tracks:
        count += _truth_key_count(getattr(track, "metadata", {}))
    return count


def _truth_key_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(
            (1 if _is_truth_identity_key(str(key)) else 0) + _truth_key_count(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return sum(_truth_key_count(item) for item in value)
    return 0


def _is_truth_identity_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in {
        "truth_id",
        "truth_object_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
    } or normalized.endswith(("_truth_id", "_actor_id", "_object_id"))


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
