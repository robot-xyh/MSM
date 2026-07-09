from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


CANONICAL_OBSERVATION_FRAMES = {
    "radar": {"ned"},
    "acoustic": {"ned"},
    "eo": {"pixel"},
    "lidar": {"ned"},
}

COMMUNICATION_METADATA_KEYS = (
    "source_node_id",
    "target_node_id",
    "relay_node_id",
    "link_type",
    "sent_timestamp",
    "received_timestamp",
    "payload_kind",
    "stale_after_s",
    "source_support",
)

SOURCE_LINEAGE_METADATA_KEYS = (
    "source_lineage_key",
    "lineage_id",
    "sequence_id",
    "sequence",
    "source_sequence",
    "payload_id",
    "payload_hash",
    "payload_digest",
    "payload_sequence",
)


class TrackLevel(str, Enum):
    """Research quality level for a fused track."""

    COARSE = "coarse"
    STABLE = "stable"
    HANDOVER = "handover"
    LOST = "lost"


@dataclass
class SensorObservation:
    """Canonical heterogeneous observation.

    `measurement_timestamp` is the physical sensing time. `arrival_timestamp`
    is when the fusion node receives the observation and is only used for
    latency accounting, ordering, and fixed-lag replay.
    """

    observation_id: str
    sensor_id: str
    modality: str
    measurement_timestamp: float
    arrival_timestamp: float
    frame_id: str
    measurement: np.ndarray
    covariance: np.ndarray | None = None
    classification_hint: str | None = None
    confidence: float = 1.0
    quality_flags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    source_node_id: str | None = None
    target_node_id: str | None = None
    relay_node_id: str | None = None
    link_type: str | None = None
    sent_timestamp: float | None = None
    received_timestamp: float | None = None
    payload_kind: str | None = None
    stale_after_s: float | None = None
    source_support: dict[str, int] | None = None
    timestamp_uncertainty_s: float | None = None

    def __post_init__(self) -> None:
        self.modality = str(self.modality).lower()
        self.frame_id = str(self.frame_id).lower()
        allowed_frames = CANONICAL_OBSERVATION_FRAMES.get(self.modality)
        if allowed_frames is None:
            raise ValueError(f"unsupported observation modality: {self.modality}")
        if self.frame_id not in allowed_frames:
            allowed = ", ".join(sorted(allowed_frames))
            raise ValueError(
                f"{self.modality} observations must use frame_id in {{{allowed}}}; "
                f"got {self.frame_id!r}. Convert external frames before fusion."
            )
        self.measurement_timestamp = float(self.measurement_timestamp)
        self.arrival_timestamp = float(self.arrival_timestamp)
        self.measurement = np.asarray(self.measurement, dtype=float)
        if self.covariance is not None:
            self.covariance = np.asarray(self.covariance, dtype=float)
        self.confidence = float(np.clip(self.confidence, 0.0, 1.0))
        self.metadata = dict(self.metadata or {})
        self._normalize_communication_metadata()
        self._normalize_timestamp_uncertainty()

    @property
    def latency(self) -> float:
        return self.arrival_timestamp - self.measurement_timestamp

    @property
    def communication_latency(self) -> float | None:
        if self.sent_timestamp is None or self.received_timestamp is None:
            return None
        return self.received_timestamp - self.sent_timestamp

    @property
    def communication_metadata(self) -> dict[str, Any]:
        return {
            key: getattr(self, key)
            for key in COMMUNICATION_METADATA_KEYS
            if getattr(self, key) is not None
        }

    @property
    def source_lineage_key(self) -> tuple[Any, ...]:
        """Stable key for suppressing repeated source/relay payloads."""

        explicit = self.metadata.get("source_lineage_key") or self.metadata.get("lineage_id")
        if explicit is not None:
            if isinstance(explicit, (list, tuple)):
                return ("explicit", *tuple(explicit))
            return ("explicit", str(explicit))

        sequence = (
            self.metadata.get("sequence_id")
            or self.metadata.get("sequence")
            or self.metadata.get("source_sequence")
            or self.metadata.get("payload_sequence")
            or self.metadata.get("airsim_frame_index")
            or self.measurement_timestamp
        )
        payload = (
            self.metadata.get("payload_id")
            or self.metadata.get("payload_hash")
            or self.metadata.get("payload_digest")
            or self._payload_fingerprint()
        )
        source = self.source_node_id or self.metadata.get("source_node_id") or self.sensor_id
        return (
            "source_payload",
            str(source),
            self.sensor_id,
            self.modality,
            self.payload_kind or self.metadata.get("payload_kind") or "",
            _lineage_scalar(sequence),
            _lineage_scalar(payload),
        )

    def is_stale_at(self, timestamp: float) -> bool:
        if self.stale_after_s is None:
            return False
        reference = self.received_timestamp
        if reference is None:
            reference = self.arrival_timestamp
        return float(timestamp) - float(reference) > self.stale_after_s

    def with_measurement_timestamp(self, timestamp: float) -> "SensorObservation":
        """Return a shallow copy with a modified measurement timestamp."""

        return SensorObservation(
            observation_id=self.observation_id,
            sensor_id=self.sensor_id,
            modality=self.modality,
            measurement_timestamp=timestamp,
            arrival_timestamp=self.arrival_timestamp,
            frame_id=self.frame_id,
            measurement=self.measurement.copy(),
            covariance=None if self.covariance is None else self.covariance.copy(),
            classification_hint=self.classification_hint,
            confidence=self.confidence,
            quality_flags=tuple(self.quality_flags),
            metadata=dict(self.metadata),
            source_node_id=self.source_node_id,
            target_node_id=self.target_node_id,
            relay_node_id=self.relay_node_id,
            link_type=self.link_type,
            sent_timestamp=self.sent_timestamp,
            received_timestamp=self.received_timestamp,
            payload_kind=self.payload_kind,
            stale_after_s=self.stale_after_s,
            source_support=None if self.source_support is None else dict(self.source_support),
            timestamp_uncertainty_s=self.timestamp_uncertainty_s,
        )

    def _normalize_communication_metadata(self) -> None:
        for key in (
            "source_node_id",
            "target_node_id",
            "relay_node_id",
            "link_type",
            "payload_kind",
        ):
            value = getattr(self, key)
            if value is None:
                value = self.metadata.get(key)
            if value is not None:
                value = str(value)
                setattr(self, key, value)
                self.metadata[key] = value

        for key in ("sent_timestamp", "received_timestamp", "stale_after_s"):
            value = getattr(self, key)
            if value is None:
                value = self.metadata.get(key)
            if value is not None:
                value = float(value)
                setattr(self, key, value)
                self.metadata[key] = value

        support = self.source_support
        if support is None:
            support = self.metadata.get("source_support")
        if support is not None:
            normalized = {str(key): int(value) for key, value in dict(support).items()}
            self.source_support = normalized
            self.metadata["source_support"] = normalized

    def _normalize_timestamp_uncertainty(self) -> None:
        candidates: list[float] = []
        if self.timestamp_uncertainty_s is not None:
            candidates.append(abs(float(self.timestamp_uncertainty_s)))

        for key in (
            "timestamp_uncertainty_s",
            "timing_uncertainty_s",
            "clock_drift_s",
            "clock_offset_s",
            "timestamp_drift_s",
            "timestamp_jitter_s",
        ):
            value = self.metadata.get(key)
            if value is not None:
                candidates.append(abs(float(value)))

        for key in (
            "timestamp_uncertainty_ms",
            "timing_uncertainty_ms",
            "clock_drift_ms",
            "timestamp_jitter_ms",
        ):
            value = self.metadata.get(key)
            if value is not None:
                candidates.append(abs(float(value)) / 1000.0)

        if self.arrival_timestamp < self.measurement_timestamp:
            candidates.append(self.measurement_timestamp - self.arrival_timestamp)

        uncertainty = max(candidates) if candidates else 0.0
        self.timestamp_uncertainty_s = float(uncertainty)
        self.metadata["timestamp_uncertainty_s"] = self.timestamp_uncertainty_s
        self.metadata["timing_uncertainty_s"] = self.timestamp_uncertainty_s

    def _payload_fingerprint(self) -> tuple[Any, ...]:
        measurement = tuple(np.round(self.measurement.reshape(-1), decimals=9).tolist())
        covariance = None
        if self.covariance is not None:
            covariance = tuple(np.round(self.covariance.reshape(-1), decimals=9).tolist())
        truth_id = self.metadata.get("truth_id")
        return (
            truth_id,
            round(self.measurement_timestamp, 9),
            measurement,
            covariance,
        )


@dataclass
class GlobalTrack:
    """Fused six-state track in NED coordinates."""

    global_track_id: str
    state: np.ndarray
    covariance: np.ndarray
    timestamp: float
    track_level: TrackLevel
    source_support: dict[str, int] = field(default_factory=dict)
    identity_likelihood: dict[str, float] = field(default_factory=dict)
    last_nis: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.state = np.asarray(self.state, dtype=float).reshape(6)
        self.covariance = np.asarray(self.covariance, dtype=float).reshape(6, 6)
        self.timestamp = float(self.timestamp)
        if not isinstance(self.track_level, TrackLevel):
            self.track_level = TrackLevel(str(self.track_level))

    @property
    def position(self) -> np.ndarray:
        return self.state[:3]

    @property
    def velocity(self) -> np.ndarray:
        return self.state[3:]

    def copy(self) -> "GlobalTrack":
        return GlobalTrack(
            global_track_id=self.global_track_id,
            state=self.state.copy(),
            covariance=self.covariance.copy(),
            timestamp=self.timestamp,
            track_level=self.track_level,
            source_support=dict(self.source_support),
            identity_likelihood=dict(self.identity_likelihood),
            last_nis=self.last_nis,
            metadata=dict(self.metadata),
        )


@dataclass(frozen=True)
class TrackUncertaintySummary:
    """Compact D1 track quality export for downstream offline modules."""

    track_id: str
    global_track_id: str
    valid_at: float
    published_at: float
    track_bucket: int
    track_level: str
    position_covariance_trace: float
    velocity_covariance_trace: float
    a95_m: float
    measurement_age_s: float
    source_support: dict[str, int]
    coverage_cell: str | None = None
    measurement_timestamp: float | None = None
    arrival_timestamp: float | None = None
    timestamp_uncertainty_s: float = 0.0
    covariance_limit_reasons: tuple[str, ...] = ()
    covariance_growth_rate: float | None = None
    source_diversity_count: int = 0
    last_nis: float | None = None
    handover_readiness: float = 0.0
    quality_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "global_track_id": self.global_track_id,
            "valid_at": self.valid_at,
            "published_at": self.published_at,
            "track_bucket": self.track_bucket,
            "track_level": self.track_level,
            "position_covariance_trace": self.position_covariance_trace,
            "position_cov_trace": self.position_covariance_trace,
            "velocity_covariance_trace": self.velocity_covariance_trace,
            "velocity_cov_trace": self.velocity_covariance_trace,
            "a95_m": self.a95_m,
            "a95_xy_m": self.a95_m,
            "measurement_age_s": self.measurement_age_s,
            "source_support": dict(self.source_support),
            "coverage_cell": self.coverage_cell,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "timestamp_uncertainty_s": self.timestamp_uncertainty_s,
            "timing_uncertainty_s": self.timestamp_uncertainty_s,
            "covariance_limit_reasons": tuple(self.covariance_limit_reasons),
            "covariance_growth_rate": self.covariance_growth_rate,
            "source_diversity_count": self.source_diversity_count,
            "last_nis": self.last_nis,
            "handover_readiness": self.handover_readiness,
            "quality_flags": tuple(self.quality_flags),
        }


@dataclass(frozen=True)
class SensorHealthSummary:
    """Per-sensor FDIR-light status derived inside the D1 fusion adapter."""

    sensor_id: str
    status: str
    fault_reason: str | None
    reject_count: int
    isolation_hint: str | None
    recovery_state: str
    observation_count: int = 0
    duplicate_count: int = 0
    oosm_count: int = 0
    stale_count: int = 0
    low_quality_count: int = 0
    anomalous_covariance_count: int = 0
    timestamp_uncertainty_s: float = 0.0
    latest_observation_timestamp: float | None = None
    fault_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "status": self.status,
            "fault_reason": self.fault_reason,
            "reject_count": self.reject_count,
            "isolation_hint": self.isolation_hint,
            "recovery_state": self.recovery_state,
            "observation_count": self.observation_count,
            "duplicate_count": self.duplicate_count,
            "oosm_count": self.oosm_count,
            "stale_count": self.stale_count,
            "low_quality_count": self.low_quality_count,
            "anomalous_covariance_count": self.anomalous_covariance_count,
            "timestamp_uncertainty_s": self.timestamp_uncertainty_s,
            "timing_uncertainty_s": self.timestamp_uncertainty_s,
            "latest_observation_timestamp": self.latest_observation_timestamp,
            "fault_reasons": tuple(self.fault_reasons),
        }


@dataclass(frozen=True)
class LatencyAuditSummary:
    """Fusion replay/latency counters exported for downstream audit."""

    observation_count: int
    replay_count: int
    oosm_observation_count: int
    stale_observation_count: int
    stale_or_oosm_observation_count: int
    max_delay_s: float
    mean_delay_s: float
    duplicate_observation_count: int
    max_replay_observation_count: int
    latency_compensation: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "replay_count": self.replay_count,
            "oosm_observation_count": self.oosm_observation_count,
            "stale_observation_count": self.stale_observation_count,
            "stale_or_oosm_observation_count": self.stale_or_oosm_observation_count,
            "max_delay_s": self.max_delay_s,
            "mean_delay_s": self.mean_delay_s,
            "duplicate_observation_count": self.duplicate_observation_count,
            "max_replay_observation_count": self.max_replay_observation_count,
            "latency_compensation": self.latency_compensation,
        }


@dataclass(frozen=True)
class FusionQualityRegionSummary:
    """Coverage-cell quality aggregate derived from track summaries."""

    coverage_cell: str
    published_at: float
    track_count: int
    coarse_track_count: int
    stable_track_count: int
    handover_track_count: int
    stale_track_count: int
    mean_a95_m: float
    max_a95_m: float
    max_measurement_age_s: float
    mean_handover_readiness: float
    source_support: dict[str, int]
    source_gap_modalities: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = ()
    mean_covariance_growth_rate: float | None = None
    max_covariance_growth_rate: float | None = None
    window_start: float | None = None
    window_end: float | None = None
    sample_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_cell": self.coverage_cell,
            "published_at": self.published_at,
            "track_count": self.track_count,
            "coarse_track_count": self.coarse_track_count,
            "stable_track_count": self.stable_track_count,
            "handover_track_count": self.handover_track_count,
            "stale_track_count": self.stale_track_count,
            "mean_a95_m": self.mean_a95_m,
            "max_a95_m": self.max_a95_m,
            "max_measurement_age_s": self.max_measurement_age_s,
            "mean_handover_readiness": self.mean_handover_readiness,
            "source_support": dict(self.source_support),
            "source_gap_modalities": tuple(self.source_gap_modalities),
            "quality_flags": tuple(self.quality_flags),
            "mean_covariance_growth_rate": self.mean_covariance_growth_rate,
            "max_covariance_growth_rate": self.max_covariance_growth_rate,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True)
class FusionQualityRegionWindowSummary:
    """Windowed coverage-cell quality trend for D4/D6 audit."""

    coverage_cell: str
    window_start: float
    window_end: float
    sample_count: int
    latest_published_at: float
    latest_track_count: int
    mean_a95_m: float
    max_a95_m: float
    mean_measurement_age_s: float
    mean_handover_readiness: float
    source_support: dict[str, int]
    source_gap_modalities: tuple[str, ...] = ()
    source_gap_sample_count: int = 0
    stale_track_sample_count: int = 0
    mean_covariance_growth_rate: float | None = None
    max_covariance_growth_rate: float | None = None
    mean_a95_growth_rate_mps: float | None = None
    measurement_age_growth_rate: float | None = None
    handover_readiness_delta: float | None = None
    latency_observation_count: int = 0
    oosm_observation_count: int = 0
    stale_observation_count: int = 0
    max_delay_s: float = 0.0
    mean_delay_s: float = 0.0
    quality_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_cell": self.coverage_cell,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "sample_count": self.sample_count,
            "latest_published_at": self.latest_published_at,
            "latest_track_count": self.latest_track_count,
            "mean_a95_m": self.mean_a95_m,
            "max_a95_m": self.max_a95_m,
            "mean_measurement_age_s": self.mean_measurement_age_s,
            "mean_handover_readiness": self.mean_handover_readiness,
            "source_support": dict(self.source_support),
            "source_gap_modalities": tuple(self.source_gap_modalities),
            "source_gap_sample_count": self.source_gap_sample_count,
            "stale_track_sample_count": self.stale_track_sample_count,
            "mean_covariance_growth_rate": self.mean_covariance_growth_rate,
            "max_covariance_growth_rate": self.max_covariance_growth_rate,
            "mean_a95_growth_rate_mps": self.mean_a95_growth_rate_mps,
            "measurement_age_growth_rate": self.measurement_age_growth_rate,
            "handover_readiness_delta": self.handover_readiness_delta,
            "latency_observation_count": self.latency_observation_count,
            "oosm_observation_count": self.oosm_observation_count,
            "stale_observation_count": self.stale_observation_count,
            "max_delay_s": self.max_delay_s,
            "mean_delay_s": self.mean_delay_s,
            "quality_flags": tuple(self.quality_flags),
        }


@dataclass(frozen=True)
class ReconCueSummary:
    """Compact D1 cue for coarse recon camera pointing over fused tracks."""

    cue_position_ned: np.ndarray
    cue_covariance: np.ndarray
    covariance_trace: float
    active_target_ids: tuple[str, ...]
    track_count: int
    stale_count: int
    total_input_count: int
    excluded_count: int
    default_covariance_count: int
    coverage_cell: str | None = None
    coverage_cells: tuple[str, ...] = ()
    measurement_timestamp: float | None = None
    arrival_timestamp: float | None = None
    quality_flags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cue_position_ned",
            np.asarray(self.cue_position_ned, dtype=float).reshape(3),
        )
        object.__setattr__(
            self,
            "cue_covariance",
            np.asarray(self.cue_covariance, dtype=float).reshape(3, 3),
        )
        object.__setattr__(self, "covariance_trace", float(self.covariance_trace))

    @property
    def centroid_ned(self) -> np.ndarray:
        return self.cue_position_ned

    def to_dict(self) -> dict[str, Any]:
        return {
            "cue_position_ned": self.cue_position_ned.tolist(),
            "centroid_ned": self.centroid_ned.tolist(),
            "cue_covariance": self.cue_covariance.tolist(),
            "covariance_trace": self.covariance_trace,
            "active_target_ids": tuple(self.active_target_ids),
            "coverage_cell": self.coverage_cell,
            "coverage_cells": tuple(self.coverage_cells),
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "track_count": self.track_count,
            "stale_count": self.stale_count,
            "total_input_count": self.total_input_count,
            "excluded_count": self.excluded_count,
            "default_covariance_count": self.default_covariance_count,
            "quality_flags": tuple(self.quality_flags),
            "metadata": dict(self.metadata),
        }


def _lineage_scalar(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return tuple(np.asarray(value).reshape(-1).tolist())
    if isinstance(value, (list, tuple)):
        return tuple(_lineage_scalar(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((str(key), _lineage_scalar(val)) for key, val in value.items()))
    if isinstance(value, float):
        return round(value, 9)
    return value
