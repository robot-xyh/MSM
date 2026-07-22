from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


CANONICAL_OBSERVATION_FRAMES = {
    "radar": {"ned"},
    "acoustic": {"ned"},
    "acoustic_3d": {"ned"},
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


@dataclass(frozen=True)
class SensorTimingExpectation:
    """Configured timing budget used to interpret latency and OOSM health."""

    expected_latency_s: float
    latency_tolerance_s: float = 0.05
    oosm_expected: bool = False

    def __post_init__(self) -> None:
        raw_oosm_expected = self.oosm_expected
        if isinstance(raw_oosm_expected, str):
            normalized = raw_oosm_expected.strip().lower()
            if normalized not in {"true", "false", "1", "0", "yes", "no"}:
                raise ValueError("oosm_expected must be a boolean value")
            raw_oosm_expected = normalized in {"true", "1", "yes"}
        object.__setattr__(self, "expected_latency_s", float(self.expected_latency_s))
        object.__setattr__(self, "latency_tolerance_s", float(self.latency_tolerance_s))
        object.__setattr__(self, "oosm_expected", bool(raw_oosm_expected))
        if not np.isfinite(self.expected_latency_s) or self.expected_latency_s < 0.0:
            raise ValueError("expected_latency_s must be non-negative")
        if not np.isfinite(self.latency_tolerance_s) or self.latency_tolerance_s < 0.0:
            raise ValueError("latency_tolerance_s must be non-negative")


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
                normalized = tuple(explicit)
                if normalized and normalized[0] in {"explicit", "source_payload"}:
                    return normalized
                return ("explicit", *normalized)
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "state": self.state.tolist(),
            "covariance": self.covariance.tolist(),
            "timestamp": self.timestamp,
            "track_level": self.track_level.value,
            "source_support": dict(self.source_support),
            "identity_likelihood": dict(self.identity_likelihood),
            "last_nis": self.last_nis,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ObserverLineage:
    """Immutable provenance for one cooperative observer payload."""

    observer_id: str
    sensor_id: str
    observation_id: str
    message_uuid: str
    source_lineage: tuple[str, ...]
    relay_node_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("observer_id", "sensor_id", "observation_id", "message_uuid"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty")
            object.__setattr__(self, name, value)
        lineage = tuple(str(item).strip() for item in self.source_lineage if str(item).strip())
        if not lineage:
            raise ValueError("source_lineage must contain an immutable source payload identifier")
        object.__setattr__(self, "source_lineage", lineage)
        object.__setattr__(
            self,
            "relay_node_ids",
            tuple(str(item).strip() for item in self.relay_node_ids if str(item).strip()),
        )

    @property
    def deduplication_key(self) -> tuple[str, ...]:
        return ("message_uuid", self.message_uuid)

    @property
    def lineage_key(self) -> tuple[str, ...]:
        return ("source_lineage", *self.source_lineage)

    def to_dict(self) -> dict[str, Any]:
        return {
            "observer_id": self.observer_id,
            "sensor_id": self.sensor_id,
            "observation_id": self.observation_id,
            "message_uuid": self.message_uuid,
            "source_lineage": tuple(self.source_lineage),
            "relay_node_ids": tuple(self.relay_node_ids),
        }


@dataclass(frozen=True)
class CooperativeBearingObservation:
    """Calibrated bearing ray and observer uncertainty at measurement time.

    Rotations map sensor -> body -> NED. Pose and extrinsics covariance use
    ``[translation_ned, small_angle_ned]`` perturbation ordering.
    """

    global_track_id: str
    lineage: ObserverLineage
    measurement_timestamp: float
    arrival_timestamp: float
    platform_position_ned: np.ndarray
    platform_rotation_body_to_ned: np.ndarray
    sensor_translation_body: np.ndarray
    sensor_rotation_sensor_to_body: np.ndarray
    bearing_unit_sensor: np.ndarray
    bearing_covariance: np.ndarray | None
    platform_pose_covariance: np.ndarray | None
    sensor_extrinsics_covariance: np.ndarray | None
    timestamp_uncertainty_s: float = 0.0
    frame_id: str = "ned"

    def __post_init__(self) -> None:
        global_track_id = str(self.global_track_id).strip()
        if not global_track_id:
            raise ValueError("global_track_id must be supplied by the canonical track owner")
        object.__setattr__(self, "global_track_id", global_track_id)
        if str(self.frame_id).lower() != "ned":
            raise ValueError("cooperative bearing observations must use the NED working frame")
        object.__setattr__(self, "frame_id", "ned")
        object.__setattr__(self, "measurement_timestamp", float(self.measurement_timestamp))
        object.__setattr__(self, "arrival_timestamp", float(self.arrival_timestamp))
        object.__setattr__(
            self, "platform_position_ned", np.asarray(self.platform_position_ned, dtype=float).reshape(3)
        )
        object.__setattr__(
            self,
            "platform_rotation_body_to_ned",
            np.asarray(self.platform_rotation_body_to_ned, dtype=float).reshape(3, 3),
        )
        object.__setattr__(
            self, "sensor_translation_body", np.asarray(self.sensor_translation_body, dtype=float).reshape(3)
        )
        object.__setattr__(
            self,
            "sensor_rotation_sensor_to_body",
            np.asarray(self.sensor_rotation_sensor_to_body, dtype=float).reshape(3, 3),
        )
        if not np.isfinite(self.measurement_timestamp) or not np.isfinite(self.arrival_timestamp):
            raise ValueError("measurement_timestamp and arrival_timestamp must be finite")
        for name in (
            "platform_position_ned",
            "platform_rotation_body_to_ned",
            "sensor_translation_body",
            "sensor_rotation_sensor_to_body",
        ):
            if not np.all(np.isfinite(getattr(self, name))):
                raise ValueError(f"{name} must be finite")
        bearing = np.asarray(self.bearing_unit_sensor, dtype=float).reshape(3)
        norm = float(np.linalg.norm(bearing))
        if not np.isfinite(norm) or norm <= 1e-12:
            raise ValueError("bearing_unit_sensor must be finite and non-zero")
        object.__setattr__(self, "bearing_unit_sensor", bearing / norm)
        for name, shape in (
            ("bearing_covariance", (2, 2)),
            ("platform_pose_covariance", (6, 6)),
            ("sensor_extrinsics_covariance", (6, 6)),
        ):
            covariance = getattr(self, name)
            if covariance is not None:
                object.__setattr__(self, name, np.asarray(covariance, dtype=float).reshape(shape))
        timestamp_uncertainty_s = abs(float(self.timestamp_uncertainty_s))
        if not np.isfinite(timestamp_uncertainty_s):
            raise ValueError("timestamp_uncertainty_s must be finite")
        object.__setattr__(self, "timestamp_uncertainty_s", timestamp_uncertainty_s)

    @property
    def ray_origin_ned(self) -> np.ndarray:
        return self.platform_position_ned + (
            self.platform_rotation_body_to_ned @ self.sensor_translation_body
        )

    @property
    def ray_direction_ned(self) -> np.ndarray:
        direction = (
            self.platform_rotation_body_to_ned
            @ self.sensor_rotation_sensor_to_body
            @ self.bearing_unit_sensor
        )
        return direction / np.linalg.norm(direction)

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "lineage": self.lineage.to_dict(),
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "estimate_frame_id": self.frame_id,
            "platform_position_ned": self.platform_position_ned.tolist(),
            "platform_rotation_body_to_ned": self.platform_rotation_body_to_ned.tolist(),
            "sensor_translation_body": self.sensor_translation_body.tolist(),
            "sensor_rotation_sensor_to_body": self.sensor_rotation_sensor_to_body.tolist(),
            "bearing_unit_sensor": self.bearing_unit_sensor.tolist(),
            "ray_origin_ned": self.ray_origin_ned.tolist(),
            "ray_direction_ned": self.ray_direction_ned.tolist(),
            "bearing_covariance": (
                None if self.bearing_covariance is None else self.bearing_covariance.tolist()
            ),
            "platform_pose_covariance": (
                None
                if self.platform_pose_covariance is None
                else self.platform_pose_covariance.tolist()
            ),
            "sensor_extrinsics_covariance": (
                None
                if self.sensor_extrinsics_covariance is None
                else self.sensor_extrinsics_covariance.tolist()
            ),
            "timestamp_uncertainty_s": self.timestamp_uncertainty_s,
        }


@dataclass(frozen=True)
class CooperativeObservationGroup:
    """D2-confirmed observations for one canonical track at a common time."""

    global_track_id: str
    estimate_timestamp: float
    observations: tuple[CooperativeBearingObservation, ...]
    target_velocity_ned: np.ndarray | None = None

    def __post_init__(self) -> None:
        global_track_id = str(self.global_track_id).strip()
        if not global_track_id:
            raise ValueError("global_track_id must be non-empty")
        object.__setattr__(self, "global_track_id", global_track_id)
        object.__setattr__(self, "estimate_timestamp", float(self.estimate_timestamp))
        if not np.isfinite(self.estimate_timestamp):
            raise ValueError("estimate_timestamp must be finite")
        observations = tuple(self.observations)
        if any(item.global_track_id != global_track_id for item in observations):
            raise ValueError("all cooperative observations must already share one canonical global_track_id")
        object.__setattr__(self, "observations", observations)
        if self.target_velocity_ned is not None:
            object.__setattr__(
                self, "target_velocity_ned", np.asarray(self.target_velocity_ned, dtype=float).reshape(3)
            )
            if not np.all(np.isfinite(self.target_velocity_ned)):
                raise ValueError("target_velocity_ned must be finite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "estimate_timestamp": self.estimate_timestamp,
            "frame_id": "ned",
            "target_velocity_ned": (
                None if self.target_velocity_ned is None else self.target_velocity_ned.tolist()
            ),
            "observations": tuple(item.to_dict() for item in self.observations),
        }


@dataclass(frozen=True)
class LosIntersectionAngle:
    first_observer_id: str
    second_observer_id: str
    angle_deg: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "first_observer_id": self.first_observer_id,
            "second_observer_id": self.second_observer_id,
            "angle_deg": self.angle_deg,
        }


@dataclass(frozen=True)
class CooperativeLocalizationSummary:
    """Geometry diagnostics and optional WLS position for one canonical track."""

    global_track_id: str
    estimate_timestamp: float
    accepted: bool
    geometry_reason: str
    quality_flags: tuple[str, ...]
    input_observer_count: int
    unique_observer_count: int
    duplicate_observer_count: int
    observer_lineages: tuple[ObserverLineage, ...]
    measurement_timestamps: tuple[float, ...]
    arrival_timestamps: tuple[float, ...]
    measurement_skew_s: float
    max_propagation_horizon_s: float
    los_intersection_angles: tuple[LosIntersectionAngle, ...]
    information_matrix: np.ndarray
    information_rank: int
    information_condition: float
    residuals_m: tuple[float, ...]
    angular_residuals_deg: tuple[float, ...]
    weighted_residual_rms: float | None
    position_ned: np.ndarray | None
    position_covariance_ned: np.ndarray | None
    covariance_inflation_trace: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "information_matrix", np.asarray(self.information_matrix, dtype=float).reshape(3, 3)
        )
        if self.position_ned is not None:
            object.__setattr__(self, "position_ned", np.asarray(self.position_ned, dtype=float).reshape(3))
        if self.position_covariance_ned is not None:
            object.__setattr__(
                self,
                "position_covariance_ned",
                np.asarray(self.position_covariance_ned, dtype=float).reshape(3, 3),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "estimate_timestamp": self.estimate_timestamp,
            "frame_id": "ned",
            "accepted": self.accepted,
            "geometry_reason": self.geometry_reason,
            "quality_flags": tuple(self.quality_flags),
            "input_observer_count": self.input_observer_count,
            "unique_observer_count": self.unique_observer_count,
            "duplicate_observer_count": self.duplicate_observer_count,
            "observer_lineages": tuple(item.to_dict() for item in self.observer_lineages),
            "measurement_timestamps": tuple(self.measurement_timestamps),
            "arrival_timestamps": tuple(self.arrival_timestamps),
            "measurement_skew_s": self.measurement_skew_s,
            "max_propagation_horizon_s": self.max_propagation_horizon_s,
            "los_intersection_angles": tuple(
                item.to_dict() for item in self.los_intersection_angles
            ),
            "information_matrix": self.information_matrix.tolist(),
            "information_rank": self.information_rank,
            "information_condition": self.information_condition,
            "residuals_m": tuple(self.residuals_m),
            "angular_residuals_deg": tuple(self.angular_residuals_deg),
            "weighted_residual_rms": self.weighted_residual_rms,
            "position_ned": None if self.position_ned is None else self.position_ned.tolist(),
            "position_covariance_ned": (
                None
                if self.position_covariance_ned is None
                else self.position_covariance_ned.tolist()
            ),
            "covariance_inflation_trace": self.covariance_inflation_trace,
        }


@dataclass(frozen=True)
class CooperativeTrackEstimate:
    """Canonical NED state estimate exchanged for conservative track fusion."""

    global_track_id: str
    state: np.ndarray
    covariance: np.ndarray
    estimate_timestamp: float
    measurement_timestamp: float
    arrival_timestamp: float
    message_uuid: str
    source_lineage: tuple[str, ...]
    timestamp_uncertainty_s: float = 0.0
    frame_id: str = "ned"

    def __post_init__(self) -> None:
        global_track_id = str(self.global_track_id).strip()
        if not global_track_id:
            raise ValueError("global_track_id must be supplied by the canonical track owner")
        object.__setattr__(self, "global_track_id", global_track_id)
        if str(self.frame_id).lower() != "ned":
            raise ValueError("cooperative track estimates must use the NED working frame")
        object.__setattr__(self, "frame_id", "ned")
        object.__setattr__(self, "state", np.asarray(self.state, dtype=float).reshape(6))
        object.__setattr__(self, "covariance", np.asarray(self.covariance, dtype=float).reshape(6, 6))
        if not np.all(np.isfinite(self.state)):
            raise ValueError("state must be finite")
        for name in ("estimate_timestamp", "measurement_timestamp", "arrival_timestamp"):
            object.__setattr__(self, name, float(getattr(self, name)))
            if not np.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        message_uuid = str(self.message_uuid).strip()
        if not message_uuid:
            raise ValueError("message_uuid must be non-empty")
        object.__setattr__(self, "message_uuid", message_uuid)
        source_lineage = tuple(str(item).strip() for item in self.source_lineage if str(item).strip())
        if not source_lineage:
            raise ValueError("source_lineage must be non-empty")
        object.__setattr__(self, "source_lineage", source_lineage)
        timestamp_uncertainty_s = abs(float(self.timestamp_uncertainty_s))
        if not np.isfinite(timestamp_uncertainty_s):
            raise ValueError("timestamp_uncertainty_s must be finite")
        object.__setattr__(self, "timestamp_uncertainty_s", timestamp_uncertainty_s)

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "state": self.state.tolist(),
            "covariance": self.covariance.tolist(),
            "estimate_timestamp": self.estimate_timestamp,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "message_uuid": self.message_uuid,
            "source_lineage": tuple(self.source_lineage),
            "timestamp_uncertainty_s": self.timestamp_uncertainty_s,
            "frame_id": self.frame_id,
        }


@dataclass(frozen=True)
class CISourceWeight:
    message_uuid: str
    source_lineage: tuple[str, ...]
    weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_uuid": self.message_uuid,
            "source_lineage": tuple(self.source_lineage),
            "weight": self.weight,
        }


@dataclass(frozen=True)
class CovarianceIntersectionSummary:
    """Result and audit evidence for unknown-correlation state fusion."""

    global_track_id: str | None
    estimate_timestamp: float | None
    accepted: bool
    reason: str
    input_count: int
    unique_source_count: int
    duplicate_source_count: int
    duplicate_message_uuids: tuple[str, ...]
    source_weights: tuple[CISourceWeight, ...]
    source_measurement_timestamps: tuple[float, ...]
    source_arrival_timestamps: tuple[float, ...]
    fused_estimate: CooperativeTrackEstimate | None

    def to_dict(self) -> dict[str, Any]:
        estimate = self.fused_estimate
        return {
            "global_track_id": self.global_track_id,
            "estimate_timestamp": self.estimate_timestamp,
            "frame_id": "ned",
            "accepted": self.accepted,
            "reason": self.reason,
            "input_count": self.input_count,
            "unique_source_count": self.unique_source_count,
            "duplicate_source_count": self.duplicate_source_count,
            "duplicate_message_uuids": tuple(self.duplicate_message_uuids),
            "source_weights": tuple(item.to_dict() for item in self.source_weights),
            "source_measurement_timestamps": tuple(self.source_measurement_timestamps),
            "source_arrival_timestamps": tuple(self.source_arrival_timestamps),
            "state": None if estimate is None else estimate.state.tolist(),
            "covariance": None if estimate is None else estimate.covariance.tolist(),
            "measurement_timestamp": None if estimate is None else estimate.measurement_timestamp,
            "arrival_timestamp": None if estimate is None else estimate.arrival_timestamp,
            "message_uuid": None if estimate is None else estimate.message_uuid,
            "source_lineage": () if estimate is None else tuple(estimate.source_lineage),
        }


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
    expected_latency_s: float | None = None
    latency_tolerance_s: float | None = None
    mean_latency_s: float = 0.0
    max_latency_s: float = 0.0
    latency_budget_exceedance_count: int = 0
    latency_budget_exceedance_rate: float = 0.0
    oosm_expected: bool = False
    unexpected_oosm_count: int = 0
    oosm_rate: float = 0.0

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
            "expected_latency_s": self.expected_latency_s,
            "latency_tolerance_s": self.latency_tolerance_s,
            "mean_latency_s": self.mean_latency_s,
            "max_latency_s": self.max_latency_s,
            "latency_budget_exceedance_count": self.latency_budget_exceedance_count,
            "latency_budget_exceedance_rate": self.latency_budget_exceedance_rate,
            "oosm_expected": self.oosm_expected,
            "unexpected_oosm_count": self.unexpected_oosm_count,
            "oosm_rate": self.oosm_rate,
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
    published_at: float | None = None

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
            "published_at": self.published_at,
        }


@dataclass(frozen=True)
class FusionBatchSummary:
    """Audit summary for one ordered batch of arrived observations.

    A batch preserves the caller-provided arrival order.  Each observation is
    still validated, audited, associated, and retained individually; only
    repeated fixed-lag history evaluations and end-of-update publication are
    coalesced.
    """

    observation_count: int
    accepted_observation_count: int
    unaccepted_observation_count: int
    duplicate_observation_count: int
    created_track_count: int
    updated_observation_count: int
    updated_track_count: int
    affected_track_ids: tuple[str, ...]
    history_replay_count: int
    origin_replay_count: int
    state_cache_hit_count: int
    state_cache_miss_count: int
    finalization_replay_count: int
    replay_filter_update_count: int
    replay_checkpoint_reuse_count: int
    global_track_materialization_count: int
    sensor_health_snapshot_build_count: int
    association_candidate_pair_count: int
    association_measurement_model_build_count: int
    association_projection_build_count: int
    association_innovation_solve_count: int
    association_radar_track_state_build_count: int
    association_radar_observation_state_build_count: int
    deferred_update_replay_avoidance_count: int
    published_at: float
    ordering: str = "input_arrival_order"

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "accepted_observation_count": self.accepted_observation_count,
            "unaccepted_observation_count": self.unaccepted_observation_count,
            "duplicate_observation_count": self.duplicate_observation_count,
            "created_track_count": self.created_track_count,
            "updated_observation_count": self.updated_observation_count,
            "updated_track_count": self.updated_track_count,
            "affected_track_ids": tuple(self.affected_track_ids),
            "history_replay_count": self.history_replay_count,
            "origin_replay_count": self.origin_replay_count,
            "state_cache_hit_count": self.state_cache_hit_count,
            "state_cache_miss_count": self.state_cache_miss_count,
            "finalization_replay_count": self.finalization_replay_count,
            "replay_filter_update_count": self.replay_filter_update_count,
            "replay_checkpoint_reuse_count": self.replay_checkpoint_reuse_count,
            "global_track_materialization_count": (
                self.global_track_materialization_count
            ),
            "sensor_health_snapshot_build_count": (
                self.sensor_health_snapshot_build_count
            ),
            "association_candidate_pair_count": (
                self.association_candidate_pair_count
            ),
            "association_measurement_model_build_count": (
                self.association_measurement_model_build_count
            ),
            "association_projection_build_count": (
                self.association_projection_build_count
            ),
            "association_innovation_solve_count": (
                self.association_innovation_solve_count
            ),
            "association_radar_track_state_build_count": (
                self.association_radar_track_state_build_count
            ),
            "association_radar_observation_state_build_count": (
                self.association_radar_observation_state_build_count
            ),
            "deferred_update_replay_avoidance_count": (
                self.deferred_update_replay_avoidance_count
            ),
            "published_at": self.published_at,
            "ordering": self.ordering,
        }


@dataclass(frozen=True)
class FusionPerformanceDiagnostics:
    """Bounded cumulative operation counters for batch/scan fusion.

    The snapshot intentionally contains scalar counters only.  It can be
    sampled by an episode profiler without retaining per-scan track snapshots
    or observation histories.
    """

    batch_count: int
    scan_batch_count: int
    observation_count: int
    history_replay_count: int
    origin_replay_count: int
    finalization_replay_count: int
    replay_filter_update_count: int
    replay_checkpoint_reuse_count: int
    checkpoint_state_query_count: int
    fixed_lag_rebase_count: int
    fixed_lag_checkpoint_suffix_reuse_count: int
    replay_checkpoint_prefix_fast_path_count: int
    cached_consistency_refresh_count: int
    global_track_materialization_count: int
    sensor_health_snapshot_build_count: int
    association_candidate_pair_count: int
    association_innovation_solve_count: int
    current_track_count: int
    current_time: float
    schema_version: str = "d1.fusion_performance_diagnostics.v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "batch_count": self.batch_count,
            "scan_batch_count": self.scan_batch_count,
            "observation_count": self.observation_count,
            "history_replay_count": self.history_replay_count,
            "origin_replay_count": self.origin_replay_count,
            "finalization_replay_count": self.finalization_replay_count,
            "replay_filter_update_count": self.replay_filter_update_count,
            "replay_checkpoint_reuse_count": self.replay_checkpoint_reuse_count,
            "checkpoint_state_query_count": self.checkpoint_state_query_count,
            "fixed_lag_rebase_count": self.fixed_lag_rebase_count,
            "fixed_lag_checkpoint_suffix_reuse_count": (
                self.fixed_lag_checkpoint_suffix_reuse_count
            ),
            "replay_checkpoint_prefix_fast_path_count": (
                self.replay_checkpoint_prefix_fast_path_count
            ),
            "cached_consistency_refresh_count": (
                self.cached_consistency_refresh_count
            ),
            "global_track_materialization_count": (
                self.global_track_materialization_count
            ),
            "sensor_health_snapshot_build_count": (
                self.sensor_health_snapshot_build_count
            ),
            "association_candidate_pair_count": (
                self.association_candidate_pair_count
            ),
            "association_innovation_solve_count": (
                self.association_innovation_solve_count
            ),
            "current_track_count": self.current_track_count,
            "current_time": self.current_time,
        }


@dataclass(frozen=True)
class FusionBatchResult:
    """Final publication and audit evidence produced by ``process_batch``."""

    tracks: tuple[GlobalTrack, ...]
    summary: FusionBatchSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "tracks": tuple(track.to_dict() for track in self.tracks),
            "summary": self.summary.to_dict(),
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
            "window_duration_s": max(0.0, self.window_end - self.window_start),
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
