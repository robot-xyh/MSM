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

    @property
    def latency(self) -> float:
        return self.arrival_timestamp - self.measurement_timestamp

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
