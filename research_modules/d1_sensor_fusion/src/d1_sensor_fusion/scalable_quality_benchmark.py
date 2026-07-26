from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .fusion import FusionAdapter
from .observations import radar_covariance_from_range, radar_h
from .online_anonymization import assert_online_observations_identity_free
from .scalable_3d import assert_scalable_online_payload_identity_free
from .types import GlobalTrack, SensorObservation


D1_QUALITY_BENCHMARK_SCHEMA_VERSION = "d1.scalable-quality-benchmark.v1"
D1_QUALITY_ONLINE_SCENARIO_SCHEMA_VERSION = "d1.scalable-quality-online-scenario.v1"
D1_QUALITY_EVALUATOR_SIDECAR_SCHEMA_VERSION = (
    "d1.scalable-quality-evaluator-sidecar.v1"
)
D1_QUALITY_METRIC_SCHEMA_VERSION = "d1.scalable-quality-metric.v1"
D1_QUALITY_SCENARIO_VERSION = "dense-crossing-miss-clutter-occlusion-oosm-v1"


@dataclass(frozen=True, slots=True)
class D1QualityBenchmarkConfig:
    """Configuration for the truth-isolated D1 measurement benchmark."""

    target_count: int = 200
    duration_s: float = 8.0
    scan_period_s: float = 0.5
    warmup_s: float = 1.0
    miss_probability: float = 0.12
    false_alarm_rate_per_target: float = 0.02
    minimum_false_alarm_rate: float = 0.25
    occlusion_detection_scale: float = 0.35
    oosm_probability: float = 0.20
    base_latency_s: float = 0.12
    latency_jitter_s: float = 0.04
    oosm_extra_delay_s: float = 1.10
    crossing_group_size: int = 8
    seed: int = 1000
    schema_version: str = D1_QUALITY_BENCHMARK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D1_QUALITY_BENCHMARK_SCHEMA_VERSION:
            raise ValueError("unsupported D1 quality benchmark schema")
        if int(self.target_count) < 1:
            raise ValueError("target_count must be positive")
        if int(self.crossing_group_size) < 2:
            raise ValueError("crossing_group_size must be at least two")
        for name in (
            "duration_s",
            "scan_period_s",
            "base_latency_s",
            "oosm_extra_delay_s",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive and finite")
        for name in ("warmup_s", "latency_jitter_s"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be non-negative and finite")
        if float(self.warmup_s) >= float(self.duration_s):
            raise ValueError("warmup_s must be less than duration_s")
        for name in (
            "miss_probability",
            "occlusion_detection_scale",
            "oosm_probability",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        for name in ("false_alarm_rate_per_target", "minimum_false_alarm_rate"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be non-negative and finite")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class D1AnonymousQualityScan:
    """One online-safe scan. No evaluator truth is stored in this object."""

    scan_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    observations: tuple[SensorObservation, ...]

    def __post_init__(self) -> None:
        scan_id = str(self.scan_id).strip()
        if not scan_id:
            raise ValueError("scan_id must not be empty")
        measurement_timestamp = float(self.measurement_timestamp)
        arrival_timestamp = float(self.arrival_timestamp)
        if not np.isfinite(measurement_timestamp) or not np.isfinite(arrival_timestamp):
            raise ValueError("scan timestamps must be finite")
        if arrival_timestamp + 1.0e-12 < measurement_timestamp:
            raise ValueError("arrival_timestamp must not precede measurement_timestamp")
        observations = tuple(self.observations)
        for observation in observations:
            if observation.metadata.get("scan_id") != scan_id:
                raise ValueError("all scan observations must carry the scan_id")
            if (
                abs(observation.measurement_timestamp - measurement_timestamp) > 1.0e-9
                or abs(observation.arrival_timestamp - arrival_timestamp) > 1.0e-9
            ):
                raise ValueError("scan and observation timestamps must match")
            if observation.modality != "radar" or observation.frame_id != "ned":
                raise ValueError("quality benchmark scans require NED radar observations")
            if observation.measurement.shape != (4,):
                raise ValueError("quality benchmark radar measurement must have shape (4,)")
            if observation.covariance is None or observation.covariance.shape != (4, 4):
                raise ValueError("quality benchmark radar covariance must have shape (4, 4)")
            if (
                not np.isfinite(observation.measurement).all()
                or not np.isfinite(observation.covariance).all()
            ):
                raise ValueError("quality benchmark measurements must be finite")
        object.__setattr__(self, "scan_id", scan_id)
        object.__setattr__(self, "measurement_timestamp", measurement_timestamp)
        object.__setattr__(self, "arrival_timestamp", arrival_timestamp)
        object.__setattr__(self, "observations", observations)
        assert_online_observations_identity_free(observations)


@dataclass(frozen=True, slots=True)
class D1AnonymousQualityScenario:
    """Online scenario passed to D1; deliberately excludes evaluator truth."""

    run_id: str
    entity_count: int
    scans: tuple[D1AnonymousQualityScan, ...]
    condition_counts: Mapping[str, int]
    schema_version: str = D1_QUALITY_ONLINE_SCENARIO_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D1_QUALITY_ONLINE_SCENARIO_SCHEMA_VERSION:
            raise ValueError("unsupported D1 online quality scenario schema")
        if int(self.entity_count) < 1:
            raise ValueError("entity_count must be positive")
        ordered = tuple(
            sorted(
                self.scans,
                key=lambda item: (
                    item.arrival_timestamp,
                    item.measurement_timestamp,
                    item.scan_id,
                ),
            )
        )
        object.__setattr__(self, "scans", ordered)
        object.__setattr__(
            self,
            "condition_counts",
            {str(key): int(value) for key, value in self.condition_counts.items()},
        )


@dataclass(frozen=True, slots=True)
class D1QualityTruthTrajectory:
    """Evaluator-only constant-velocity trajectory."""

    truth_id: str
    initial_state_ned: tuple[float, ...]

    def __post_init__(self) -> None:
        truth_id = str(self.truth_id).strip()
        state = np.asarray(self.initial_state_ned, dtype=float)
        if not truth_id:
            raise ValueError("truth_id must not be empty")
        if state.shape != (6,) or not np.isfinite(state).all():
            raise ValueError("initial_state_ned must be a finite six-state vector")
        object.__setattr__(self, "truth_id", truth_id)
        object.__setattr__(
            self,
            "initial_state_ned",
            tuple(float(value) for value in state),
        )

    def state_at(self, timestamp: float) -> np.ndarray:
        state = np.asarray(self.initial_state_ned, dtype=float).copy()
        state[:3] += state[3:] * float(timestamp)
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "truth_id": self.truth_id,
            "initial_state_ned": list(self.initial_state_ned),
        }


@dataclass(frozen=True, slots=True)
class D1QualityLineageTruthRecord:
    """Evaluator-only join from anonymous source lineage to one truth entity."""

    source_lineage: tuple[str, ...]
    observation_id: str
    measurement_timestamp: float
    truth_id: str | None

    def __post_init__(self) -> None:
        lineage = tuple(str(value) for value in self.source_lineage)
        if not lineage:
            raise ValueError("source_lineage must not be empty")
        if not str(self.observation_id).strip():
            raise ValueError("observation_id must not be empty")
        if not np.isfinite(float(self.measurement_timestamp)):
            raise ValueError("measurement_timestamp must be finite")
        object.__setattr__(self, "source_lineage", lineage)
        object.__setattr__(
            self,
            "truth_id",
            None if self.truth_id is None else str(self.truth_id),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_lineage": list(self.source_lineage),
            "observation_id": self.observation_id,
            "measurement_timestamp": self.measurement_timestamp,
            "truth_id": self.truth_id,
        }


@dataclass(frozen=True, slots=True)
class D1QualityEvaluatorSidecar:
    """Truth material that is accepted only by the offline evaluator."""

    run_id: str
    trajectories: tuple[D1QualityTruthTrajectory, ...]
    lineage_records: tuple[D1QualityLineageTruthRecord, ...]
    scenario_version: str = D1_QUALITY_SCENARIO_VERSION
    usage: str = "offline_evaluation_only"
    content_digest: str = ""
    schema_version: str = D1_QUALITY_EVALUATOR_SIDECAR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D1_QUALITY_EVALUATOR_SIDECAR_SCHEMA_VERSION:
            raise ValueError("unsupported D1 evaluator sidecar schema")
        if self.usage != "offline_evaluation_only":
            raise ValueError("D1 quality sidecar is evaluator-only")
        trajectories = tuple(sorted(self.trajectories, key=lambda item: item.truth_id))
        truth_ids = [item.truth_id for item in trajectories]
        if not trajectories or len(set(truth_ids)) != len(truth_ids):
            raise ValueError("sidecar trajectories must have unique truth IDs")
        lineage_records = tuple(
            sorted(
                self.lineage_records,
                key=lambda item: (
                    item.measurement_timestamp,
                    item.observation_id,
                ),
            )
        )
        lineages = [item.source_lineage for item in lineage_records]
        if len(set(lineages)) != len(lineages):
            raise ValueError("sidecar source lineages must be unique")
        unknown = {
            item.truth_id
            for item in lineage_records
            if item.truth_id is not None and item.truth_id not in set(truth_ids)
        }
        if unknown:
            raise ValueError(f"sidecar lineage references unknown truth IDs: {sorted(unknown)}")
        object.__setattr__(self, "trajectories", trajectories)
        object.__setattr__(self, "lineage_records", lineage_records)
        digest = _sha256_json(self._unsigned_payload())
        if self.content_digest and self.content_digest != digest:
            raise ValueError("D1 evaluator sidecar digest mismatch")
        object.__setattr__(self, "content_digest", digest)

    @property
    def truth_ids(self) -> tuple[str, ...]:
        return tuple(item.truth_id for item in self.trajectories)

    @property
    def lineage_truth(self) -> dict[tuple[str, ...], str | None]:
        return {item.source_lineage: item.truth_id for item in self.lineage_records}

    @property
    def observation_truth(self) -> dict[str, str | None]:
        return {item.observation_id: item.truth_id for item in self.lineage_records}

    def state_at(self, truth_id: str, timestamp: float) -> np.ndarray:
        for trajectory in self.trajectories:
            if trajectory.truth_id == truth_id:
                return trajectory.state_at(timestamp)
        raise KeyError(f"unknown evaluator truth_id: {truth_id!r}")

    def _unsigned_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario_version": self.scenario_version,
            "usage": self.usage,
            "identity_join": "source_observation_lineage",
            "run_id": self.run_id,
            "trajectories": [item.to_dict() for item in self.trajectories],
            "lineage_records": [item.to_dict() for item in self.lineage_records],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._unsigned_payload(), "content_digest": self.content_digest}


@dataclass(frozen=True, slots=True)
class D1QualityMetric:
    available: bool
    value: float | None
    sample_count: int
    unit: str
    reason: str | None = None
    schema_version: str = D1_QUALITY_METRIC_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D1_QUALITY_METRIC_SCHEMA_VERSION:
            raise ValueError("unsupported D1 quality metric schema")
        available = bool(self.available)
        value = None if self.value is None else float(self.value)
        sample_count = int(self.sample_count)
        reason = None if self.reason is None else str(self.reason)
        if sample_count < 0:
            raise ValueError("metric sample_count must be non-negative")
        if available:
            if value is None or not np.isfinite(value) or reason is not None:
                raise ValueError("available metric requires a finite value and no reason")
        elif value is not None or not reason:
            raise ValueError("unavailable metric requires value=None and a reason")
        object.__setattr__(self, "available", available)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "sample_count", sample_count)
        object.__setattr__(self, "reason", reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "available": self.available,
            "value": self.value,
            "sample_count": self.sample_count,
            "unit": self.unit,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class D1QualitySeedResult:
    config: D1QualityBenchmarkConfig
    metrics: Mapping[str, D1QualityMetric]
    condition_counts: Mapping[str, int]
    final_track_count: int
    accepted_observation_count: int
    unaccepted_observation_count: int
    oosm_observation_count: int
    sidecar_digest: str
    online_truth_use_count: int = 0
    d2_global_track_id_write_count: int = 0
    schema_version: str = D1_QUALITY_BENCHMARK_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "config": self.config.to_dict(),
            "metrics": {
                key: value.to_dict() for key, value in sorted(self.metrics.items())
            },
            "condition_counts": dict(sorted(self.condition_counts.items())),
            "final_track_count": self.final_track_count,
            "accepted_observation_count": self.accepted_observation_count,
            "unaccepted_observation_count": self.unaccepted_observation_count,
            "oosm_observation_count": self.oosm_observation_count,
            "sidecar_digest": self.sidecar_digest,
            "online_truth_use_count": self.online_truth_use_count,
            "d2_global_track_id_write_count": self.d2_global_track_id_write_count,
        }


@dataclass(frozen=True, slots=True)
class D1QualityScaleSummary:
    target_count: int
    seed_count: int
    metrics: Mapping[str, D1QualityMetric]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_count": self.target_count,
            "seed_count": self.seed_count,
            "metrics": {
                key: value.to_dict() for key, value in sorted(self.metrics.items())
            },
        }


@dataclass(frozen=True, slots=True)
class D1QualityBatchResult:
    seed_results: tuple[D1QualitySeedResult, ...]
    scale_summaries: tuple[D1QualityScaleSummary, ...]
    schema_version: str = D1_QUALITY_BENCHMARK_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario_version": D1_QUALITY_SCENARIO_VERSION,
            "seed_result_count": len(self.seed_results),
            "seed_results": [item.to_dict() for item in self.seed_results],
            "scale_summaries": [item.to_dict() for item in self.scale_summaries],
            "constraints": {
                "online_truth_use_count": sum(
                    item.online_truth_use_count for item in self.seed_results
                ),
                "d2_global_track_id_write_count": sum(
                    item.d2_global_track_id_write_count for item in self.seed_results
                ),
                "default_fusion_algorithm_modified": False,
                "track_lifecycle_modified": False,
            },
        }


@dataclass(frozen=True, slots=True)
class _TrackLineageState:
    truth_counts: Mapping[str, int]
    clutter_count: int
    mapped_observation_count: int
    total_observation_count: int

    @property
    def dominant_truth_id(self) -> str | None:
        if not self.truth_counts:
            return None
        highest = max(self.truth_counts.values())
        return min(
            truth_id
            for truth_id, count in self.truth_counts.items()
            if count == highest
        )

    @property
    def dominant_support(self) -> int:
        return max(self.truth_counts.values(), default=0)

    @property
    def purity(self) -> float | None:
        total = sum(self.truth_counts.values()) + self.clutter_count
        if total <= 0:
            return None
        return self.dominant_support / total

    @property
    def is_mixed(self) -> bool:
        lineage_category_count = len(self.truth_counts)
        if self.clutter_count > 0:
            lineage_category_count += 1
        return lineage_category_count > 1


@dataclass(frozen=True, slots=True)
class _EvaluationSnapshot:
    timestamp: float
    tracks: tuple[GlobalTrack, ...]
    lineage_by_track: Mapping[str, _TrackLineageState]


def build_anonymous_quality_scenario(
    config: D1QualityBenchmarkConfig,
) -> tuple[D1AnonymousQualityScenario, D1QualityEvaluatorSidecar]:
    """Build disjoint online and evaluator-only inputs for one seed."""

    rng = np.random.default_rng(config.seed)
    run_id = f"d1-quality-{config.target_count:03d}-{config.seed:08d}"
    trajectories = _build_crossing_trajectories(config, rng)
    truth_ids = tuple(item.truth_id for item in trajectories)
    sensor_position = np.zeros(3, dtype=float)
    crossing_time = 0.55 * config.duration_s
    scan_times = np.arange(
        0.0,
        config.duration_s + 0.5 * config.scan_period_s,
        config.scan_period_s,
        dtype=float,
    )
    scans: list[D1AnonymousQualityScan] = []
    lineage_records: list[D1QualityLineageTruthRecord] = []
    counts: Counter[str] = Counter()

    for scan_index, measurement_timestamp in enumerate(scan_times):
        scan_id = f"{run_id}-scan-{scan_index:05d}"
        latency = config.base_latency_s + rng.uniform(
            -config.latency_jitter_s,
            config.latency_jitter_s,
        )
        latency = max(latency, 1.0e-6)
        forced_oosm_scan = len(scan_times) >= 3 and scan_index == 1
        random_oosm_scan = (
            scan_index > 2 and rng.random() < config.oosm_probability
        )
        if forced_oosm_scan or random_oosm_scan:
            latency += (
                config.oosm_extra_delay_s
                + 2.0 * config.scan_period_s
                + rng.uniform(0.0, config.scan_period_s)
            )
            counts["delayed_scan_count"] += 1
        arrival_timestamp = float(measurement_timestamp + latency)

        entries: list[tuple[np.ndarray, np.ndarray, float, tuple[str, ...], str | None]] = []
        for entity_index, trajectory in enumerate(trajectories):
            forced_occlusion = (
                entity_index % 7 == 0
                and abs(float(measurement_timestamp) - crossing_time)
                <= max(config.scan_period_s, 0.12 * config.duration_s)
            )
            detection_probability = 1.0 - config.miss_probability
            if forced_occlusion:
                detection_probability *= config.occlusion_detection_scale
            detected = scan_index == 0 or rng.random() < detection_probability
            if not detected:
                counts["missed_detection_count"] += 1
                if forced_occlusion:
                    counts["occlusion_miss_count"] += 1
                continue

            state = trajectory.state_at(float(measurement_timestamp))
            ideal_measurement = radar_h(state, sensor_position)
            covariance = radar_covariance_from_range(ideal_measurement[0])
            flags: tuple[str, ...] = ()
            confidence = 0.96
            if forced_occlusion:
                covariance = covariance * 4.0
                flags = ("occluded", "low_confidence")
                confidence = 0.55
                counts["occluded_observation_count"] += 1
            noise = rng.normal(0.0, np.sqrt(np.diag(covariance)))
            noisy_measurement = ideal_measurement + noise
            noisy_measurement[1] = _wrap_angle(noisy_measurement[1])
            noisy_measurement[2] = _wrap_angle(noisy_measurement[2])
            entries.append(
                (
                    noisy_measurement,
                    covariance,
                    confidence,
                    flags,
                    trajectory.truth_id,
                )
            )
            counts["true_observation_count"] += 1

        clutter_rate = (
            config.minimum_false_alarm_rate
            + config.false_alarm_rate_per_target * config.target_count
        )
        clutter_count = int(rng.poisson(clutter_rate)) if scan_index > 0 else 0
        for _ in range(clutter_count):
            range_m = float(rng.uniform(450.0, 1_650.0))
            measurement = np.array(
                [
                    range_m,
                    rng.uniform(-math.pi, math.pi),
                    rng.uniform(math.radians(-20.0), math.radians(20.0)),
                    rng.normal(0.0, 8.0),
                ],
                dtype=float,
            )
            covariance = radar_covariance_from_range(range_m) * 1.8
            entries.append(
                (
                    measurement,
                    covariance,
                    0.45,
                    ("clutter", "low_confidence"),
                    None,
                )
            )
            counts["false_alarm_observation_count"] += 1

        if entries:
            order = rng.permutation(len(entries))
            entries = [entries[int(index)] for index in order]
        observations: list[SensorObservation] = []
        for ordinal, (measurement, covariance, confidence, flags, truth_id) in enumerate(
            entries,
            start=1,
        ):
            observation_id = (
                f"{run_id}-frame-{scan_index:05d}-observation-{ordinal:04d}"
            )
            token = hashlib.sha256(
                f"{run_id}|{scan_index}|{ordinal}|source".encode("utf-8")
            ).hexdigest()[:24]
            source_lineage = ("explicit", "d1_quality_source", token)
            observation = SensorObservation(
                observation_id=observation_id,
                sensor_id="radar-quality-main",
                modality="radar",
                measurement_timestamp=float(measurement_timestamp),
                arrival_timestamp=arrival_timestamp,
                frame_id="ned",
                measurement=measurement,
                covariance=covariance,
                classification_hint="unmanned_aircraft",
                confidence=confidence,
                quality_flags=flags,
                metadata={
                    "sensor_position_ned": sensor_position.copy(),
                    "scan_id": scan_id,
                    "coverage_cell": "quality-benchmark-volume",
                    "source_lineage_key": source_lineage,
                    "lineage_id": token,
                    "range_dependent_covariance": True,
                },
            )
            observations.append(observation)
            lineage_records.append(
                D1QualityLineageTruthRecord(
                    source_lineage=tuple(str(value) for value in observation.source_lineage_key),
                    observation_id=observation.observation_id,
                    measurement_timestamp=observation.measurement_timestamp,
                    truth_id=truth_id,
                )
            )

        scans.append(
            D1AnonymousQualityScan(
                scan_id=scan_id,
                measurement_timestamp=float(measurement_timestamp),
                arrival_timestamp=arrival_timestamp,
                observations=tuple(observations),
            )
        )

    sidecar = D1QualityEvaluatorSidecar(
        run_id=run_id,
        trajectories=tuple(trajectories),
        lineage_records=tuple(lineage_records),
    )
    scenario = D1AnonymousQualityScenario(
        run_id=run_id,
        entity_count=len(truth_ids),
        scans=tuple(scans),
        condition_counts=counts,
    )
    _assert_scenario_identity_isolated(scenario, sidecar)
    return scenario, sidecar


def run_d1_quality_benchmark(
    config: D1QualityBenchmarkConfig,
) -> D1QualitySeedResult:
    """Run D1 online first, then join evaluator truth through source lineage."""

    scenario, sidecar = build_anonymous_quality_scenario(config)
    adapter = FusionAdapter(
        use_truth_hints_for_association=False,
        latency_compensation=True,
    )
    snapshots: list[_EvaluationSnapshot] = []
    processing_times_ms: list[float] = []
    accepted_observation_count = 0
    unaccepted_observation_count = 0

    for scan in scenario.scans:
        if not scan.observations:
            continue
        assert_online_observations_identity_free(
            scan.observations,
            identity_tokens=sidecar.truth_ids,
        )
        started = time.perf_counter()
        result = adapter.process_scan_batch(scan.observations)
        processing_times_ms.append((time.perf_counter() - started) * 1000.0)
        accepted_observation_count += result.summary.accepted_observation_count
        unaccepted_observation_count += result.summary.unaccepted_observation_count
        _assert_six_state_track_contract(result.tracks)
        assert_scalable_online_payload_identity_free(result.tracks)
        _assert_identity_tokens_absent(result.tracks, sidecar.truth_ids)
        snapshots.append(
            _EvaluationSnapshot(
                timestamp=float(result.summary.published_at),
                tracks=tuple(result.tracks),
                lineage_by_track=_track_lineage_state(adapter, sidecar),
            )
        )

    metrics = _evaluate_quality_metrics(
        config=config,
        sidecar=sidecar,
        adapter=adapter,
        snapshots=snapshots,
        processing_times_ms=processing_times_ms,
    )
    return D1QualitySeedResult(
        config=config,
        metrics=metrics,
        condition_counts=scenario.condition_counts,
        final_track_count=len(adapter.tracks),
        accepted_observation_count=accepted_observation_count,
        unaccepted_observation_count=unaccepted_observation_count,
        oosm_observation_count=int(adapter.oosm_observation_count),
        sidecar_digest=sidecar.content_digest,
    )


def run_d1_quality_benchmark_batch(
    *,
    target_counts: Sequence[int] = (200,),
    seeds: Iterable[int] = range(1000, 1020),
    base_config: D1QualityBenchmarkConfig | None = None,
) -> D1QualityBatchResult:
    """Run a deterministic multi-scale, multi-seed D1 quality batch."""

    counts = tuple(int(value) for value in target_counts)
    seed_values = tuple(int(value) for value in seeds)
    if not counts or any(value < 1 for value in counts):
        raise ValueError("target_counts must contain positive values")
    if not seed_values:
        raise ValueError("seeds must not be empty")
    base = base_config or D1QualityBenchmarkConfig()
    results = tuple(
        run_d1_quality_benchmark(
            replace(base, target_count=target_count, seed=seed)
        )
        for target_count in counts
        for seed in seed_values
    )
    summaries = tuple(
        _summarize_scale(
            target_count,
            tuple(
                result
                for result in results
                if result.config.target_count == target_count
            ),
        )
        for target_count in counts
    )
    return D1QualityBatchResult(seed_results=results, scale_summaries=summaries)


def write_d1_quality_benchmark_outputs(
    result: D1QualityBatchResult,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write evaluator results only; raw sidecars remain outside online outputs."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "d1_quality_benchmark.json"
    report_path = destination / "D1_QUALITY_BENCHMARK_REPORT_CN.md"
    json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_render_quality_report_cn(result), encoding="utf-8")
    return json_path, report_path


def _build_crossing_trajectories(
    config: D1QualityBenchmarkConfig,
    rng: np.random.Generator,
) -> list[D1QualityTruthTrajectory]:
    crossing_time = 0.55 * config.duration_s
    group_size = min(config.crossing_group_size, config.target_count)
    group_count = int(math.ceil(config.target_count / group_size))
    grid_width = int(math.ceil(math.sqrt(group_count)))
    trajectories: list[D1QualityTruthTrajectory] = []
    for index in range(config.target_count):
        group_index = index // group_size
        member_index = index % group_size
        row = group_index // grid_width
        column = group_index % grid_width
        center = np.array(
            [
                700.0 + 190.0 * row,
                210.0 * (column - 0.5 * (grid_width - 1)),
                -110.0 - 18.0 * (group_index % 4),
            ],
            dtype=float,
        )
        angle = (
            2.0 * math.pi * member_index / max(group_size, 1)
            + 0.17 * group_index
            + rng.normal(0.0, 0.015)
        )
        speed = 18.0 + 0.35 * (index % 11)
        velocity = np.array(
            [
                speed * math.cos(angle),
                speed * math.sin(angle),
                0.25 * ((index % 5) - 2),
            ],
            dtype=float,
        )
        offset = np.array(
            [
                2.0 * math.cos(1.7 * angle),
                2.0 * math.sin(1.7 * angle),
                1.5 * ((member_index % 3) - 1),
            ],
            dtype=float,
        )
        crossing_position = center + offset
        initial_position = crossing_position - velocity * crossing_time
        state = np.concatenate((initial_position, velocity))
        trajectories.append(
            D1QualityTruthTrajectory(
                truth_id=f"offline-entity-{index:04d}",
                initial_state_ned=tuple(float(value) for value in state),
            )
        )
    return trajectories


def _track_lineage_state(
    adapter: FusionAdapter,
    sidecar: D1QualityEvaluatorSidecar,
) -> dict[str, _TrackLineageState]:
    lineage_truth = sidecar.lineage_truth
    output: dict[str, _TrackLineageState] = {}
    for track_id, record in adapter.tracks.items():
        counts: Counter[str] = Counter()
        clutter_count = 0
        mapped_count = 0
        observations = {
            observation.observation_id: observation
            for observation in (*record.archived_observations, *record.observations)
        }
        for observation in observations.values():
            lineage = tuple(str(value) for value in observation.source_lineage_key)
            if lineage not in lineage_truth:
                continue
            mapped_count += 1
            truth_id = lineage_truth[lineage]
            if truth_id is None:
                clutter_count += 1
            else:
                counts[truth_id] += 1
        output[track_id] = _TrackLineageState(
            truth_counts=dict(counts),
            clutter_count=clutter_count,
            mapped_observation_count=mapped_count,
            total_observation_count=len(observations),
        )
    return output


def _evaluate_quality_metrics(
    *,
    config: D1QualityBenchmarkConfig,
    sidecar: D1QualityEvaluatorSidecar,
    adapter: FusionAdapter,
    snapshots: Sequence[_EvaluationSnapshot],
    processing_times_ms: Sequence[float],
) -> dict[str, D1QualityMetric]:
    evaluated = [
        item for item in snapshots if item.timestamp + 1.0e-9 >= config.warmup_s
    ]
    metrics: dict[str, D1QualityMetric] = {}
    truth_ids = sidecar.truth_ids
    recall_values: list[float] = []
    duplicate_values: list[float] = []
    mixed_values: list[float] = []
    squared_position_errors: list[float] = []
    nees_values: list[float] = []
    track_counts: list[float] = []
    track_times: list[float] = []
    false_first_seen: dict[str, float] = {}
    false_last_seen: dict[str, float] = {}

    for snapshot in evaluated:
        by_truth: defaultdict[str, list[tuple[GlobalTrack, _TrackLineageState]]] = (
            defaultdict(list)
        )
        false_track_ids: list[str] = []
        mixed_track_count = 0
        for track in snapshot.tracks:
            lineage = snapshot.lineage_by_track.get(track.global_track_id)
            if lineage is None:
                continue
            dominant = lineage.dominant_truth_id
            if dominant is None:
                if lineage.clutter_count > 0:
                    false_track_ids.append(track.global_track_id)
                continue
            by_truth[dominant].append((track, lineage))
            if lineage.is_mixed:
                mixed_track_count += 1

        recall_values.append(len(by_truth) / len(truth_ids))
        duplicate_count = sum(max(0, len(items) - 1) for items in by_truth.values())
        duplicate_values.append(duplicate_count / len(truth_ids))
        mixed_values.append(
            mixed_track_count / max(1, len(snapshot.tracks))
        )
        for track_id in false_track_ids:
            false_first_seen.setdefault(track_id, snapshot.timestamp)
            false_last_seen[track_id] = snapshot.timestamp

        for truth_id, candidates in by_truth.items():
            representative, _ = sorted(
                candidates,
                key=lambda item: (
                    -item[1].dominant_support,
                    -(item[1].purity or 0.0),
                    item[0].global_track_id,
                ),
            )[0]
            truth_state = sidecar.state_at(truth_id, representative.timestamp)
            error = representative.state - truth_state
            squared_position_errors.append(float(np.dot(error[:3], error[:3])))
            try:
                nees = float(
                    error.T
                    @ np.linalg.solve(representative.covariance, error)
                )
            except np.linalg.LinAlgError:
                nees = math.nan
            if np.isfinite(nees) and nees >= 0.0:
                nees_values.append(nees)
        track_counts.append(float(len(snapshot.tracks)))
        track_times.append(float(snapshot.timestamp))

    metrics["warmup_recall_rate"] = _mean_metric(
        recall_values,
        unit="ratio",
        reason="no_post_warmup_publication_frames",
    )
    metrics["duplicate_track_rate"] = _mean_metric(
        duplicate_values,
        unit="duplicates_per_truth_per_frame",
        reason="no_post_warmup_publication_frames",
    )
    metrics["mixed_lineage_track_rate"] = _mean_metric(
        mixed_values,
        unit="ratio",
        reason="no_post_warmup_publication_frames",
    )
    metrics["position_rmse_m"] = _reduced_metric(
        squared_position_errors,
        reducer=lambda values: math.sqrt(float(np.mean(values))),
        unit="m",
        reason="no_lineage_aligned_track_truth_pairs",
    )
    metrics["nees_mean"] = _mean_metric(
        nees_values,
        unit="dimensionless",
        reason="no_invertible_lineage_aligned_state_covariance_pairs",
    )

    nis_values = [
        float(record.nis)
        for record in adapter.consistency_evidence_records()
        if record.measurement_timestamp + 1.0e-9 >= config.warmup_s
        and record.nis is not None
        and record.availability.innovation.available
        and sidecar.observation_truth.get(record.observation_id) is not None
    ]
    metrics["nis_mean"] = _mean_metric(
        nis_values,
        unit="dimensionless",
        reason="no_available_truth_lineage_nis_after_warmup",
    )

    metrics["false_track_count"] = (
        D1QualityMetric(
            available=True,
            value=float(len(false_first_seen)),
            sample_count=len(evaluated),
            unit="unique_tracks",
        )
        if evaluated
        else _unavailable_metric(
            unit="unique_tracks",
            reason="no_post_warmup_publication_frames",
        )
    )
    false_lifetimes = [
        max(0.0, false_last_seen[track_id] - first_seen)
        for track_id, first_seen in false_first_seen.items()
    ]
    metrics["false_track_lifetime_mean_s"] = _mean_metric(
        false_lifetimes,
        unit="s",
        reason="no_false_tracks_after_warmup",
    )
    metrics["false_track_lifetime_p95_s"] = _percentile_metric(
        false_lifetimes,
        percentile=95.0,
        unit="s",
        reason="no_false_tracks_after_warmup",
    )
    metrics["track_count_growth"] = _growth_metric(track_counts)
    metrics["track_count_growth_rate_per_s"] = _growth_rate_metric(
        track_counts,
        track_times,
    )
    metrics["scan_processing_time_p50_ms"] = _percentile_metric(
        processing_times_ms,
        percentile=50.0,
        unit="ms",
        reason="no_nonempty_scans_processed",
    )
    metrics["scan_processing_time_p95_ms"] = _percentile_metric(
        processing_times_ms,
        percentile=95.0,
        unit="ms",
        reason="no_nonempty_scans_processed",
    )
    mapped_observations, runtime_observations = _unique_runtime_lineage_counts(
        adapter,
        sidecar,
    )
    metrics["lineage_mapping_coverage_rate"] = (
        D1QualityMetric(
            available=True,
            value=float(mapped_observations / runtime_observations),
            sample_count=runtime_observations,
            unit="ratio",
        )
        if runtime_observations > 0
        else _unavailable_metric(
            unit="ratio",
            reason="no_runtime_observation_lineage",
        )
    )
    return metrics


def _unique_runtime_lineage_counts(
    adapter: FusionAdapter,
    sidecar: D1QualityEvaluatorSidecar,
) -> tuple[int, int]:
    """Count each observation retained by the runtime exactly once."""

    lineage_by_observation: dict[str, tuple[str, ...]] = {}
    for record in adapter.tracks.values():
        observations = {
            observation.observation_id: observation
            for observation in (*record.archived_observations, *record.observations)
        }
        for observation_id, observation in observations.items():
            lineage = tuple(str(value) for value in observation.source_lineage_key)
            existing = lineage_by_observation.get(observation_id)
            if existing is not None and existing != lineage:
                raise ValueError(
                    "one runtime observation ID is bound to conflicting source lineages"
                )
            lineage_by_observation[observation_id] = lineage
    mapped = sum(
        lineage in sidecar.lineage_truth
        for lineage in lineage_by_observation.values()
    )
    return int(mapped), len(lineage_by_observation)


def _assert_six_state_track_contract(tracks: Sequence[GlobalTrack]) -> None:
    for track in tracks:
        if track.state.shape != (6,) or track.covariance.shape != (6, 6):
            raise ValueError("D1 quality benchmark requires six-state tracks")
        if not np.isfinite(track.state).all() or not np.isfinite(track.covariance).all():
            raise ValueError("D1 quality benchmark tracks must be finite")
        if not np.allclose(track.covariance, track.covariance.T, rtol=0.0, atol=1.0e-8):
            raise ValueError("D1 quality benchmark track covariance must be symmetric")
        minimum_eigenvalue = float(
            np.min(np.linalg.eigvalsh(0.5 * (track.covariance + track.covariance.T)))
        )
        if minimum_eigenvalue < -1.0e-8:
            raise ValueError("D1 quality benchmark track covariance must be PSD")


def _summarize_scale(
    target_count: int,
    results: Sequence[D1QualitySeedResult],
) -> D1QualityScaleSummary:
    metric_names = sorted(
        {name for result in results for name in result.metrics}
    )
    summaries: dict[str, D1QualityMetric] = {}
    for name in metric_names:
        candidates = [
            result.metrics[name]
            for result in results
            if name in result.metrics and result.metrics[name].available
        ]
        if not candidates:
            summaries[name] = _unavailable_metric(
                unit=(
                    results[0].metrics[name].unit
                    if results and name in results[0].metrics
                    else "unknown"
                ),
                reason="metric_unavailable_for_all_seeds",
                sample_count=len(results),
            )
            continue
        summaries[name] = D1QualityMetric(
            available=True,
            value=float(np.mean([item.value for item in candidates])),
            sample_count=len(candidates),
            unit=candidates[0].unit,
        )
    return D1QualityScaleSummary(
        target_count=int(target_count),
        seed_count=len(results),
        metrics=summaries,
    )


def _assert_scenario_identity_isolated(
    scenario: D1AnonymousQualityScenario,
    sidecar: D1QualityEvaluatorSidecar,
) -> None:
    observations = tuple(
        observation
        for scan in scenario.scans
        for observation in scan.observations
    )
    assert_online_observations_identity_free(
        observations,
        identity_tokens=sidecar.truth_ids,
    )
    assert_scalable_online_payload_identity_free(observations)
    _assert_identity_tokens_absent(observations, sidecar.truth_ids)


def _assert_identity_tokens_absent(
    payload: Any,
    identity_tokens: Iterable[str],
) -> None:
    tokens = tuple(
        token.lower()
        for value in identity_tokens
        if (token := str(value).strip())
    )
    exposures: list[str] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, str):
            lowered = value.lower()
            for token in tokens:
                if token in lowered:
                    exposures.append(path)
                    break
            return
        if isinstance(value, np.ndarray):
            if value.dtype.kind in {"O", "S", "U"}:
                visit(value.tolist(), path)
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                visit(str(key), f"{path}.key")
                visit(item, f"{path}.{key}")
            return
        if isinstance(value, (list, tuple, set, frozenset)):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
            return
        if hasattr(value, "__dataclass_fields__"):
            for name in value.__dataclass_fields__:
                visit(getattr(value, name), f"{path}.{name}")

    visit(payload, "payload")
    if exposures:
        raise ValueError(
            "online quality benchmark contains evaluator identity tokens at "
            + ", ".join(exposures[:8])
        )


def _mean_metric(
    values: Sequence[float],
    *,
    unit: str,
    reason: str,
) -> D1QualityMetric:
    return _reduced_metric(
        values,
        reducer=lambda items: float(np.mean(items)),
        unit=unit,
        reason=reason,
    )


def _percentile_metric(
    values: Sequence[float],
    *,
    percentile: float,
    unit: str,
    reason: str,
) -> D1QualityMetric:
    return _reduced_metric(
        values,
        reducer=lambda items: float(np.percentile(items, percentile)),
        unit=unit,
        reason=reason,
    )


def _reduced_metric(
    values: Sequence[float],
    *,
    reducer,
    unit: str,
    reason: str,
) -> D1QualityMetric:
    finite = [float(value) for value in values if np.isfinite(float(value))]
    if not finite:
        return _unavailable_metric(unit=unit, reason=reason)
    return D1QualityMetric(
        available=True,
        value=float(reducer(finite)),
        sample_count=len(finite),
        unit=unit,
    )


def _unavailable_metric(
    *,
    unit: str,
    reason: str,
    sample_count: int = 0,
) -> D1QualityMetric:
    return D1QualityMetric(
        available=False,
        value=None,
        sample_count=sample_count,
        unit=unit,
        reason=reason,
    )


def _growth_metric(track_counts: Sequence[float]) -> D1QualityMetric:
    if len(track_counts) < 2:
        return _unavailable_metric(
            unit="tracks",
            reason="fewer_than_two_post_warmup_publication_frames",
            sample_count=len(track_counts),
        )
    return D1QualityMetric(
        available=True,
        value=float(track_counts[-1] - track_counts[0]),
        sample_count=len(track_counts),
        unit="tracks",
    )


def _growth_rate_metric(
    track_counts: Sequence[float],
    timestamps: Sequence[float],
) -> D1QualityMetric:
    if len(track_counts) < 2 or len(timestamps) < 2:
        return _unavailable_metric(
            unit="tracks_per_s",
            reason="fewer_than_two_post_warmup_publication_frames",
            sample_count=min(len(track_counts), len(timestamps)),
        )
    x = np.asarray(timestamps, dtype=float)
    if float(np.ptp(x)) <= 1.0e-12:
        return _unavailable_metric(
            unit="tracks_per_s",
            reason="post_warmup_publication_timestamps_not_distinct",
            sample_count=len(x),
        )
    y = np.asarray(track_counts, dtype=float)
    slope = float(np.polyfit(x, y, deg=1)[0])
    return D1QualityMetric(
        available=True,
        value=slope,
        sample_count=len(x),
        unit="tracks_per_s",
    )


def _render_quality_report_cn(result: D1QualityBatchResult) -> str:
    lines = [
        "# D1 可扩展真值隔离质量基准",
        "",
        "## 结论口径",
        "",
        "本报告只测量现有融合主线，不调整关联门限、滤波算法或航迹生命周期。在线观测不携带真值、Actor、Object 或目标身份；离线评分通过匿名源观测谱系与 evaluator-only sidecar 对齐。",
        "",
        f"- 完成运行数：{len(result.seed_results)}",
        f"- 在线真值使用次数：{sum(item.online_truth_use_count for item in result.seed_results)}",
        f"- D2 global_track_id 写入次数：{sum(item.d2_global_track_id_write_count for item in result.seed_results)}",
        "",
        "## 分规模结果",
        "",
    ]
    selected_metrics = (
        "warmup_recall_rate",
        "duplicate_track_rate",
        "false_track_count",
        "false_track_lifetime_mean_s",
        "position_rmse_m",
        "nees_mean",
        "nis_mean",
        "track_count_growth",
        "scan_processing_time_p50_ms",
        "scan_processing_time_p95_ms",
        "lineage_mapping_coverage_rate",
    )
    for summary in result.scale_summaries:
        lines.extend(
            [
                f"### {summary.target_count} 目标",
                "",
                f"种子数：{summary.seed_count}",
                "",
                "| 指标 | 可用 | 数值 | 样本数 | 原因 |",
                "| --- | --- | ---: | ---: | --- |",
            ]
        )
        for name in selected_metrics:
            metric = summary.metrics.get(name)
            if metric is None:
                continue
            value = (
                f"{metric.value:.6f}"
                if metric.available and metric.value is not None
                else "-"
            )
            lines.append(
                f"| `{name}` | {'是' if metric.available else '否'} | "
                f"{value} | {metric.sample_count} | {metric.reason or '-'} |"
            )
        lines.append("")
    lines.extend(
        [
            "## 限制",
            "",
            "- 当前场景采用匀速质点和合成雷达球坐标量测，不能替代真实雷达、AirSim 或外场标定。",
            "- 航迹数量增长和虚假航迹寿命用于暴露现有生命周期缺口；本基准没有新增删除逻辑。",
            "- 身份归属仅用于离线评分。D2 的规范全局航迹编号和身份交换指标不在本基准内创建或修改。",
            "",
        ]
    )
    return "\n".join(lines)


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _wrap_angle(value: float) -> float:
    return (float(value) + math.pi) % (2.0 * math.pi) - math.pi
