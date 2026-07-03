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
            "covariance_growth_rate": self.covariance_growth_rate,
            "source_diversity_count": self.source_diversity_count,
            "last_nis": self.last_nis,
            "handover_readiness": self.handover_readiness,
            "quality_flags": tuple(self.quality_flags),
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
