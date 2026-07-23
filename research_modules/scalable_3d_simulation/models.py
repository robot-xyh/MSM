"""Versioned data models for the scalable three-dimensional simulator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np


WORLD_SCHEMA_VERSION = "scalable3d-world-v1"
BUS_SCHEMA_VERSION = "scalable3d-episode-bus-v1"
SCENARIO_SCHEMA_VERSION = "scalable3d-scenario-v1"
ONLINE_OBSERVATION_SCHEMA_VERSION = "scalable3d-observation-v1"
OFFLINE_TRUTH_SCHEMA_VERSION_V1 = "scalable3d-offline-truth-v1"
OFFLINE_TRUTH_SCHEMA_VERSION = "scalable3d-offline-truth-v2"
OFFLINE_TRUTH_DISPOSITION_TARGET = "target"
OFFLINE_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM = "known_false_alarm"
OFFLINE_TRUTH_DISPOSITION_UNKNOWN = "unknown"
OFFLINE_TRUTH_DISPOSITIONS = frozenset(
    {
        OFFLINE_TRUTH_DISPOSITION_TARGET,
        OFFLINE_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM,
        OFFLINE_TRUTH_DISPOSITION_UNKNOWN,
    }
)
DEFAULT_THRESHOLD_VERSION = "scalable3d-thresholds-v1"
SENSOR_RANDOM_SCHEDULE_VERSIONS = frozenset(
    {"sequential_v1", "entity_fixed_v1"}
)


class EntityKind(str, Enum):
    """Kinds of point masses represented by the shared world."""

    INTRUDER = "intruder"
    INTERCEPTOR = "interceptor"
    RECON = "recon"


class MotionProfile(str, Enum):
    """Synthetic intruder motion profiles."""

    CONSTANT_VELOCITY = "constant_velocity"
    COORDINATED_TURN = "coordinated_turn"
    CROSSING = "crossing"
    FORMATION_SPLIT = "formation_split"
    EVASIVE = "evasive"


@dataclass(frozen=True)
class KinematicLimits:
    """Point-mass limits in SI units."""

    max_speed_mps: float
    max_accel_mps2: float
    max_turn_rate_radps: float
    max_climb_rate_mps: float

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not np.isfinite(value) or float(value) <= 0.0:
                raise ValueError(f"{name} must be positive and finite")


@dataclass(frozen=True)
class ScenarioConfig:
    """Configuration for a scalable point-mass episode."""

    scenario_name: str = "nominal_200v200"
    scenario_version: str = "200v200-nominal-v1"
    seed: int = 7
    target_count: int = 200
    resource_count: int = 200
    recon_count: int = 8
    region_count: int = 8
    duration_s: float = 10.0
    physics_dt_s: float = 0.05
    radar_period_s: float = 0.2
    acoustic_period_s: float = 0.5
    visual_period_s: float = 0.1
    association_period_s: float = 0.2
    assignment_period_s: float = 1.0
    region_policy_period_s: float = 5.0
    world_half_extent_m: float = 6_000.0
    minimum_altitude_m: float = 30.0
    maximum_altitude_m: float = 1_500.0
    protected_radius_m: float = 1_000.0
    target_speed_min_mps: float = 3.5
    target_speed_max_mps: float = 4.7
    interceptor_speed_mps: float = 14.0
    intercept_radius_m: float = 5.0
    motion_profile: MotionProfile = MotionProfile.CONSTANT_VELOCITY
    radar_latency_s: float = 0.2
    acoustic_latency_s: float = 0.35
    visual_latency_s: float = 0.08
    radar_range_limit_m: float = 7_500.0
    radar_detection_probability: float = 0.98
    radar_range_std_base_m: float = 3.0
    radar_range_std_per_km_m: float = 1.5
    radar_angle_std_deg: float = 0.20
    acoustic_sensor_count: int = 4
    acoustic_range_limit_m: float = 2_500.0
    acoustic_detection_probability: float = 0.80
    acoustic_angle_std_deg: float = 3.0
    visual_detection_probability: float = 0.92
    visual_false_alarm_rate: float = 0.02
    visual_min_bbox_area_px2: float = 4.0
    recon_visual_min_bbox_area_px2: float = 2.0
    camera_width_px: int = 1920
    camera_height_px: int = 1080
    camera_horizontal_fov_deg: float = 90.0
    recon_camera_width_px: int = 3840
    recon_camera_height_px: int = 2160
    recon_camera_horizontal_fov_deg: float = 70.0
    target_proxy_width_m: float = 2.0
    target_proxy_height_m: float = 0.8
    communication_latency_s: float = 0.04
    communication_jitter_s: float = 0.01
    communication_drop_probability: float = 0.01
    communication_bandwidth_bytes_per_s: float = 5_000_000.0
    radar_enabled: bool = True
    acoustic_enabled: bool = True
    visual_enabled: bool = True
    communication_enabled: bool = True
    sensor_random_schedule_version: str = "sequential_v1"
    d1_model_version: str = "d1-scalable3d-fusion-v1"
    d2_model_version: str = "d2-scalable3d-association-v1"
    d3_policy_version: str = "d3-scalable3d-rule-cost-v1"
    d4_policy_version: str = "d4-region-resource-rule-v1"
    d5_model_version: str = "d5-scalable3d-geometry-rule-v1"
    d5_active_vision_policy_version: str = "d5-active-vision-rule-v1"
    d7_model_version: str = "d7-scalable3d-guidance-v1"
    threshold_version: str = DEFAULT_THRESHOLD_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.scenario_name:
            raise ValueError("scenario_name must be non-empty")
        if not self.scenario_version:
            raise ValueError("scenario_version must be non-empty")
        for name in ("target_count", "resource_count", "region_count"):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.recon_count < 0:
            raise ValueError("recon_count must be non-negative")
        positive_fields = (
            "duration_s",
            "physics_dt_s",
            "radar_period_s",
            "acoustic_period_s",
            "visual_period_s",
            "association_period_s",
            "assignment_period_s",
            "region_policy_period_s",
            "world_half_extent_m",
            "minimum_altitude_m",
            "maximum_altitude_m",
            "protected_radius_m",
            "target_speed_min_mps",
            "target_speed_max_mps",
            "interceptor_speed_mps",
            "intercept_radius_m",
            "radar_range_limit_m",
            "radar_range_std_base_m",
            "radar_range_std_per_km_m",
            "radar_angle_std_deg",
            "acoustic_range_limit_m",
            "acoustic_angle_std_deg",
            "camera_horizontal_fov_deg",
            "recon_camera_horizontal_fov_deg",
            "target_proxy_width_m",
            "target_proxy_height_m",
            "visual_min_bbox_area_px2",
            "recon_visual_min_bbox_area_px2",
            "communication_bandwidth_bytes_per_s",
        )
        for name in positive_fields:
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive and finite")
        if self.maximum_altitude_m <= self.minimum_altitude_m:
            raise ValueError("maximum_altitude_m must exceed minimum_altitude_m")
        if self.target_speed_max_mps < self.target_speed_min_mps:
            raise ValueError("target_speed_max_mps must not be below target_speed_min_mps")
        for name in (
            "radar_detection_probability",
            "acoustic_detection_probability",
            "visual_detection_probability",
            "communication_drop_probability",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.visual_false_alarm_rate < 0.0:
            raise ValueError("visual_false_alarm_rate must be non-negative")
        for name in (
            "radar_latency_s",
            "acoustic_latency_s",
            "visual_latency_s",
            "communication_latency_s",
            "communication_jitter_s",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        for name in (
            "acoustic_sensor_count",
            "camera_width_px",
            "camera_height_px",
            "recon_camera_width_px",
            "recon_camera_height_px",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("camera_horizontal_fov_deg", "recon_camera_horizontal_fov_deg"):
            if not 1.0 < float(getattr(self, name)) < 179.0:
                raise ValueError(f"{name} must be in (1, 179) degrees")
        if self.physics_dt_s > min(
            self.radar_period_s,
            self.acoustic_period_s,
            self.visual_period_s,
            self.association_period_s,
            self.assignment_period_s,
        ):
            raise ValueError("physics_dt_s must not exceed a scheduled module period")
        for name in (
            "d1_model_version",
            "d2_model_version",
            "d3_policy_version",
            "d4_policy_version",
            "d5_model_version",
            "d5_active_vision_policy_version",
            "d7_model_version",
            "threshold_version",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be non-empty")
        schedule = str(self.sensor_random_schedule_version).strip().lower()
        if schedule not in SENSOR_RANDOM_SCHEDULE_VERSIONS:
            raise ValueError(
                "sensor_random_schedule_version must be sequential_v1 or "
                "entity_fixed_v1"
            )
        object.__setattr__(self, "sensor_random_schedule_version", schedule)

    @property
    def entity_count(self) -> int:
        return self.target_count + self.resource_count + self.recon_count

    @property
    def identity_lineage_freshness_budget_s(self) -> float:
        """Maximum source-observation age shared by D2 and offline scoring."""

        return max(
            self.radar_period_s + self.radar_latency_s,
            self.acoustic_period_s + self.acoustic_latency_s,
            self.visual_period_s + self.visual_latency_s,
            self.association_period_s,
        ) + self.communication_latency_s + abs(self.communication_jitter_s)

    def timestamps(self) -> np.ndarray:
        count = int(np.floor(self.duration_s / self.physics_dt_s + 1e-9))
        return np.arange(count + 1, dtype=float) * self.physics_dt_s

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["motion_profile"] = self.motion_profile.value
        data["schema_version"] = SCENARIO_SCHEMA_VERSION
        return data

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScenarioConfig":
        values = dict(payload)
        values.pop("schema_version", None)
        if "motion_profile" in values:
            values["motion_profile"] = MotionProfile(str(values["motion_profile"]))
        return cls(**values)


@dataclass(frozen=True)
class EntitySnapshot:
    """Immutable state snapshot for one entity group."""

    kind: EntityKind
    entity_ids: tuple[str, ...]
    state: np.ndarray
    active: np.ndarray

    def __post_init__(self) -> None:
        state = np.asarray(self.state, dtype=float)
        active = np.asarray(self.active, dtype=bool).reshape(-1)
        if state.shape != (len(self.entity_ids), 6):
            raise ValueError("state must have shape (entity_count, 6)")
        if active.shape != (len(self.entity_ids),):
            raise ValueError("active must have shape (entity_count,)")
        if not np.all(np.isfinite(state)):
            raise ValueError("state must contain only finite values")
        object.__setattr__(self, "state", state.copy())
        object.__setattr__(self, "active", active.copy())

    @property
    def position_ned(self) -> np.ndarray:
        return self.state[:, :3]

    @property
    def velocity_ned(self) -> np.ndarray:
        return self.state[:, 3:]


@dataclass(frozen=True)
class WorldSnapshot:
    """One truth-bearing world snapshot kept outside the online bus."""

    timestamp: float
    intruders: EntitySnapshot
    interceptors: EntitySnapshot
    recon: EntitySnapshot
    intercepted_target_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not np.isfinite(self.timestamp) or self.timestamp < 0.0:
            raise ValueError("timestamp must be finite and non-negative")


@dataclass(frozen=True)
class SensorMeasurement:
    """Identity-free online sensor measurement."""

    observation_id: str
    sensor_id: str
    modality: str
    measurement_timestamp: float
    arrival_timestamp: float
    frame_id: str
    measurement: np.ndarray
    covariance: np.ndarray
    confidence: float
    classification_hint: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        measurement = np.asarray(self.measurement, dtype=float).reshape(-1)
        covariance = np.asarray(self.covariance, dtype=float)
        if covariance.shape != (measurement.size, measurement.size):
            raise ValueError("covariance shape must match measurement dimension")
        if not np.all(np.isfinite(measurement)) or not np.all(np.isfinite(covariance)):
            raise ValueError("measurement and covariance must be finite")
        if self.arrival_timestamp + 1e-12 < self.measurement_timestamp:
            raise ValueError("arrival_timestamp must not precede measurement_timestamp")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if not self.observation_id or not self.sensor_id or not self.modality or not self.frame_id:
            raise ValueError("observation and sensor identity fields must be non-empty")
        measurement_copy = measurement.copy()
        covariance_copy = covariance.copy()
        measurement_copy.setflags(write=False)
        covariance_copy.setflags(write=False)
        object.__setattr__(self, "measurement", measurement_copy)
        object.__setattr__(self, "covariance", covariance_copy)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True)
class OfflineTruthLabel:
    """Evaluator-only observation disposition kept outside online payloads."""

    observation_id: str
    truth_entity_id: str | None
    measurement_timestamp: float
    schema_version: str = OFFLINE_TRUTH_SCHEMA_VERSION
    disposition: str = OFFLINE_TRUTH_DISPOSITION_TARGET

    def __post_init__(self) -> None:
        observation_id = str(self.observation_id).strip()
        if not observation_id:
            raise ValueError("offline truth observation_id must be non-empty")
        timestamp = float(self.measurement_timestamp)
        if not np.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError(
                "offline truth measurement_timestamp must be finite and non-negative"
            )
        schema_version = str(self.schema_version)
        if schema_version not in {
            OFFLINE_TRUTH_SCHEMA_VERSION_V1,
            OFFLINE_TRUTH_SCHEMA_VERSION,
        }:
            raise ValueError(f"unsupported offline truth schema: {schema_version!r}")
        disposition = str(self.disposition).strip().lower()
        if disposition not in OFFLINE_TRUTH_DISPOSITIONS:
            raise ValueError(
                f"unsupported offline truth disposition: {self.disposition!r}"
            )
        if (
            schema_version == OFFLINE_TRUTH_SCHEMA_VERSION_V1
            and disposition != OFFLINE_TRUTH_DISPOSITION_TARGET
        ):
            raise ValueError("offline truth v1 supports target labels only")
        if disposition == OFFLINE_TRUTH_DISPOSITION_TARGET:
            if self.truth_entity_id is None:
                raise ValueError("target truth labels require truth_entity_id")
            truth_entity_id = str(self.truth_entity_id).strip()
            if not truth_entity_id:
                raise ValueError("target truth_entity_id must be non-empty")
        else:
            if self.truth_entity_id is not None:
                raise ValueError(
                    f"{disposition} truth labels must not carry truth_entity_id"
                )
            truth_entity_id = None
        object.__setattr__(self, "observation_id", observation_id)
        object.__setattr__(self, "truth_entity_id", truth_entity_id)
        object.__setattr__(self, "measurement_timestamp", timestamp)
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "disposition", disposition)

    @classmethod
    def known_false_alarm(
        cls,
        *,
        observation_id: str,
        measurement_timestamp: float,
    ) -> "OfflineTruthLabel":
        return cls(
            observation_id=observation_id,
            truth_entity_id=None,
            measurement_timestamp=measurement_timestamp,
            disposition=OFFLINE_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM,
        )

    @classmethod
    def unknown(
        cls,
        *,
        observation_id: str,
        measurement_timestamp: float,
    ) -> "OfflineTruthLabel":
        return cls(
            observation_id=observation_id,
            truth_entity_id=None,
            measurement_timestamp=measurement_timestamp,
            disposition=OFFLINE_TRUTH_DISPOSITION_UNKNOWN,
        )


@dataclass(frozen=True)
class ObservationBatch:
    """Online measurements and evaluator-only labels produced together but routed separately."""

    measurements: tuple[SensorMeasurement, ...]
    offline_truth_labels: tuple[OfflineTruthLabel, ...]


@dataclass(frozen=True)
class OnlineSensorBatch:
    """One identity-free scan batch from a single sensor."""

    batch_id: str
    sensor_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    measurements: tuple[SensorMeasurement, ...]

    def __post_init__(self) -> None:
        if not self.batch_id or not self.sensor_id:
            raise ValueError("batch_id and sensor_id must be non-empty")
        if self.arrival_timestamp + 1.0e-12 < self.measurement_timestamp:
            raise ValueError("arrival_timestamp must not precede measurement_timestamp")
        if not self.measurements:
            raise ValueError("online sensor batch must contain at least one measurement")
        for measurement in self.measurements:
            if measurement.sensor_id != self.sensor_id:
                raise ValueError("all measurements in a batch must share sensor_id")
            if abs(measurement.measurement_timestamp - self.measurement_timestamp) > 1.0e-9:
                raise ValueError("all measurements in a batch must share measurement_timestamp")
            if abs(measurement.arrival_timestamp - self.arrival_timestamp) > 1.0e-9:
                raise ValueError("all measurements in a batch must share arrival_timestamp")


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, np.ndarray):
        result = value.copy()
        result.setflags(write=False)
        return result
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_value(item) for item in value)
    return value
