from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
from typing import Any

import numpy as np

from .fusion import FusionAdapter
from .observations import RadarCovarianceConfig, radar_covariance_from_range
from .online_anonymization import assert_online_observations_identity_free
from .types import FusionBatchResult, FusionStateUpdateResult, SensorObservation


SCALABLE_3D_FUSION_SCHEMA_VERSION = "d1-scalable3d-fusion-v1"
SCALABLE_3D_POSITION_ONLY_RADAR_NIS_GATE = 16.26623619623813
SCALABLE_3D_UNOBSERVED_VELOCITY_VARIANCE_M2PS2 = 25.0

_FORBIDDEN_IDENTITY_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_entity_id",
        "truth_entity_ids",
        "ground_truth",
        "ground_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "entity_id",
        "entity_ids",
        "target_id",
        "target_ids",
        "offline_truth_labels",
        "intercepted_target_indices",
    }
)
_FORBIDDEN_IDENTITY_TYPES = frozenset(
    {"OfflineTruthLabel", "WorldSnapshot", "EntitySnapshot"}
)
_MISSING = object()


class Scalable3DFusionAdapter(FusionAdapter):
    """Identity-free scan fusion adapter for the scalable 3D episode bus."""

    def __init__(
        self,
        *,
        unobserved_velocity_variance_m2ps2: float = (
            SCALABLE_3D_UNOBSERVED_VELOCITY_VARIANCE_M2PS2
        ),
        position_only_radar_nis_gate: float = SCALABLE_3D_POSITION_ONLY_RADAR_NIS_GATE,
        radar_assignment_ambiguity_governance: bool = False,
        **kwargs: Any,
    ) -> None:
        if bool(kwargs.pop("use_truth_hints_for_association", False)):
            raise ValueError(
                "Scalable3DFusionAdapter forbids truth-assisted online association"
            )
        self.unobserved_velocity_variance_m2ps2 = _positive_finite(
            unobserved_velocity_variance_m2ps2,
            "unobserved_velocity_variance_m2ps2",
        )
        self.position_only_radar_nis_gate = _positive_finite(
            position_only_radar_nis_gate,
            "position_only_radar_nis_gate",
        )
        super().__init__(
            use_truth_hints_for_association=False,
            radar_assignment_ambiguity_governance=(
                radar_assignment_ambiguity_governance
            ),
            **kwargs,
        )

    def process_online_sensor_batch(
        self,
        batch: Any,
        *,
        materialize_tracks: bool = True,
    ) -> FusionBatchResult | FusionStateUpdateResult:
        observations = sensor_observations_from_online_batch(
            batch,
            radar_covariance_config=self.radar_covariance_config,
            unobserved_velocity_variance_m2ps2=(
                self.unobserved_velocity_variance_m2ps2
            ),
            position_only_radar_nis_gate=self.position_only_radar_nis_gate,
        )
        return self.process_scan_batch(
            observations,
            materialize_tracks=materialize_tracks,
        )

    def process_measurement_scan(
        self,
        measurements: Iterable[Any],
        *,
        batch_id: str,
        materialize_tracks: bool = True,
    ) -> FusionBatchResult | FusionStateUpdateResult:
        items = tuple(measurements)
        if not items:
            raise ValueError("measurement scan must contain at least one measurement")
        first = items[0]
        batch = {
            "batch_id": str(batch_id),
            "sensor_id": _field(first, "sensor_id"),
            "measurement_timestamp": _field(first, "measurement_timestamp"),
            "arrival_timestamp": _field(first, "arrival_timestamp"),
            "measurements": items,
        }
        return self.process_online_sensor_batch(
            batch,
            materialize_tracks=materialize_tracks,
        )


def sensor_observations_from_online_batch(
    batch: Any,
    *,
    radar_covariance_config: RadarCovarianceConfig | Mapping[str, Any] | None = None,
    unobserved_velocity_variance_m2ps2: float = (
        SCALABLE_3D_UNOBSERVED_VELOCITY_VARIANCE_M2PS2
    ),
    position_only_radar_nis_gate: float = SCALABLE_3D_POSITION_ONLY_RADAR_NIS_GATE,
) -> tuple[SensorObservation, ...]:
    """Convert an OnlineSensorBatch-compatible payload without importing main."""

    assert_scalable_online_payload_identity_free(batch)
    batch_id = str(_field(batch, "batch_id")).strip()
    sensor_id = str(_field(batch, "sensor_id")).strip()
    measurement_timestamp = float(_field(batch, "measurement_timestamp"))
    arrival_timestamp = float(_field(batch, "arrival_timestamp"))
    measurements = tuple(_field(batch, "measurements"))
    if not batch_id or not sensor_id:
        raise ValueError("online batch_id and sensor_id must be non-empty")
    if not measurements:
        raise ValueError("online sensor batch must contain at least one measurement")
    if not np.isfinite(measurement_timestamp) or not np.isfinite(arrival_timestamp):
        raise ValueError("online batch timestamps must be finite")
    if arrival_timestamp + 1.0e-12 < measurement_timestamp:
        raise ValueError("online batch arrival_timestamp must not precede sensing time")

    observations: list[SensorObservation] = []
    for measurement in measurements:
        measurement_sensor_id = str(_field(measurement, "sensor_id")).strip()
        measurement_time = float(_field(measurement, "measurement_timestamp"))
        arrival_time = float(_field(measurement, "arrival_timestamp"))
        if measurement_sensor_id != sensor_id:
            raise ValueError("all online batch measurements must share sensor_id")
        if abs(measurement_time - measurement_timestamp) > 1.0e-9:
            raise ValueError(
                "all online batch measurements must share measurement_timestamp"
            )
        if abs(arrival_time - arrival_timestamp) > 1.0e-9:
            raise ValueError("all online batch measurements must share arrival_timestamp")
        observations.append(
            sensor_observation_from_online_measurement(
                measurement,
                batch_id=batch_id,
                radar_covariance_config=radar_covariance_config,
                unobserved_velocity_variance_m2ps2=(
                    unobserved_velocity_variance_m2ps2
                ),
                position_only_radar_nis_gate=position_only_radar_nis_gate,
            )
        )

    assert_online_observations_identity_free(observations)
    return tuple(observations)


def sensor_observation_from_online_measurement(
    measurement: Any,
    *,
    batch_id: str,
    radar_covariance_config: RadarCovarianceConfig | Mapping[str, Any] | None = None,
    unobserved_velocity_variance_m2ps2: float = (
        SCALABLE_3D_UNOBSERVED_VELOCITY_VARIANCE_M2PS2
    ),
    position_only_radar_nis_gate: float = SCALABLE_3D_POSITION_ONLY_RADAR_NIS_GATE,
) -> SensorObservation:
    """Convert one identity-free bus measurement to D1's canonical contract."""

    assert_scalable_online_payload_identity_free(measurement)
    modality = str(_field(measurement, "modality")).strip().lower()
    raw_value = np.asarray(_field(measurement, "measurement"), dtype=float).reshape(-1)
    raw_covariance = np.asarray(_field(measurement, "covariance"), dtype=float)
    metadata = dict(_field(measurement, "metadata", {}))
    common = {
        "observation_id": str(_field(measurement, "observation_id")),
        "sensor_id": str(_field(measurement, "sensor_id")),
        "measurement_timestamp": float(_field(measurement, "measurement_timestamp")),
        "arrival_timestamp": float(_field(measurement, "arrival_timestamp")),
        "classification_hint": _field(measurement, "classification_hint", None),
        "confidence": float(_field(measurement, "confidence", 1.0)),
    }
    source_frame_id = str(_field(measurement, "frame_id"))
    metadata.update(
        {
            "scan_id": str(batch_id),
            "online_batch_id": str(batch_id),
            "source_frame_id": source_frame_id,
            "source_modality": modality,
            "source_measurement_dimension": int(raw_value.size),
            "d1_fusion_schema_version": SCALABLE_3D_FUSION_SCHEMA_VERSION,
        }
    )

    if modality in {"radar_spherical", "radar"}:
        return _radar_observation(
            raw_value,
            raw_covariance,
            metadata,
            common,
            radar_covariance_config,
            unobserved_velocity_variance_m2ps2,
            position_only_radar_nis_gate,
        )
    if modality in {"vision_bbox", "eo", "camera_bbox"}:
        return _eo_observation(raw_value, raw_covariance, metadata, common)
    if modality in {"lidar", "lidar_ned", "position_ned"}:
        return _position_observation(raw_value, raw_covariance, metadata, common)
    if modality in {"acoustic", "acoustic_bearing"}:
        return _acoustic_observation(raw_value, raw_covariance, metadata, common)
    raise ValueError(f"unsupported scalable 3D sensor modality: {modality!r}")


def assert_scalable_online_payload_identity_free(payload: Any) -> None:
    """Reject truth-bearing fields before the D1 adapter reads their values."""

    violations: list[str] = []

    def visit(value: Any, path: str) -> None:
        if type(value).__name__ in _FORBIDDEN_IDENTITY_TYPES:
            violations.append(f"{path}<{type(value).__name__}>")
            return
        if isinstance(value, np.ndarray):
            return
        if is_dataclass(value) and not isinstance(value, type):
            for item in fields(value):
                child_path = f"{path}.{item.name}"
                if _is_forbidden_identity_key(item.name):
                    violations.append(child_path)
                    continue
                visit(getattr(value, item.name), child_path)
            return
        if isinstance(value, Mapping):
            for raw_key in value:
                key = str(raw_key)
                child_path = f"{path}.{key}"
                if _is_forbidden_identity_key(key):
                    violations.append(child_path)
                    continue
                visit(value[raw_key], child_path)
            return
        if isinstance(value, (list, tuple, set, frozenset)):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
            return
        if hasattr(value, "__dict__") and not isinstance(value, type):
            visit(vars(value), path)

    visit(payload, "payload")
    if violations:
        details = ", ".join(sorted(set(violations)))
        raise ValueError(f"online scalable 3D payload contains identity truth: {details}")


def _radar_observation(
    value: np.ndarray,
    covariance: np.ndarray,
    metadata: dict[str, Any],
    common: dict[str, Any],
    covariance_config: RadarCovarianceConfig | Mapping[str, Any] | None,
    unobserved_velocity_variance_m2ps2: float,
    position_only_radar_nis_gate: float,
) -> SensorObservation:
    if value.size not in {3, 4}:
        raise ValueError("radar_spherical measurement must contain 3 or 4 values")
    if covariance.shape != (value.size, value.size):
        raise ValueError("radar_spherical covariance shape must match its measurement")
    if value[0] <= 0.0:
        raise ValueError("radar range must be positive")
    if value.size == 3:
        velocity_variance = _positive_finite(
            metadata.get(
                "unobserved_velocity_variance_m2ps2",
                unobserved_velocity_variance_m2ps2,
            ),
            "unobserved_velocity_variance_m2ps2",
        )
        innovation_gate = _positive_finite(
            position_only_radar_nis_gate,
            "position_only_radar_nis_gate",
        )
        canonical_value = np.concatenate((value, np.zeros(1, dtype=float)))
        canonical_covariance = np.zeros((4, 4), dtype=float)
        canonical_covariance[:3, :3] = covariance
        canonical_covariance[3, 3] = radar_covariance_from_range(
            float(value[0]),
            covariance_config,
        )[3, 3]
        radial_velocity_observed = False
        filter_metadata = {
            "filter_measurement_dimension": 3,
            "filter_innovation_gate_chi2": innovation_gate,
            "radial_velocity_placeholder_ignored": True,
            "unobserved_velocity_variance_m2ps2": velocity_variance,
            "velocity_initialization_model": "zero_mean_isotropic_gaussian",
        }
    else:
        canonical_value = value.copy()
        canonical_covariance = covariance.copy()
        radial_velocity_observed = True
        filter_metadata = {
            "filter_measurement_dimension": 4,
            "radial_velocity_placeholder_ignored": False,
        }

    metadata.update(
        {
            "measurement_order": (
                "range_m",
                "azimuth_rad",
                "elevation_rad",
                "radial_velocity_mps",
            ),
            "radial_velocity_observed": radial_velocity_observed,
            **filter_metadata,
            "range_dependent_covariance": bool(
                metadata.get("range_dependent_covariance", value.size == 3)
            ),
            "spherical_covariance_to_ned": "analytic_jacobian",
            "unobserved_tangential_velocity_variance_m2ps2": float(
                metadata.get(
                    "unobserved_tangential_velocity_variance_m2ps2",
                    100.0,
                )
            ),
        }
    )
    metadata.setdefault("sensor_position_ned", (0.0, 0.0, 0.0))
    return SensorObservation(
        **common,
        modality="radar",
        frame_id="ned",
        measurement=canonical_value,
        covariance=canonical_covariance,
        metadata=metadata,
    )


def _eo_observation(
    value: np.ndarray,
    covariance: np.ndarray,
    metadata: dict[str, Any],
    common: dict[str, Any],
) -> SensorObservation:
    if value.size < 2 or covariance.shape != (value.size, value.size):
        raise ValueError("vision_bbox measurement and covariance dimensions are inconsistent")
    if value.size >= 6:
        metadata["bbox"] = value[2:6].copy()
        metadata["bbox_xyxy"] = value[2:6].copy()
        metadata["center_px"] = value[:2].copy()
    intrinsics = dict(metadata.get("camera_intrinsics", {}))
    metadata["camera_model"] = {
        "position_ned": metadata.get("camera_position_ned", (0.0, 0.0, -10.0)),
        "rotation_world_to_camera": metadata.get(
            "rotation_camera_from_ned",
            metadata.get("rotation_world_to_camera"),
        ),
        "intrinsics": {
            "width": intrinsics.get("width", intrinsics.get("width_px", 1280)),
            "height": intrinsics.get("height", intrinsics.get("height_px", 720)),
            "fx": intrinsics.get("fx", 900.0),
            "fy": intrinsics.get("fy", 900.0),
            "cx": intrinsics.get("cx", 640.0),
            "cy": intrinsics.get("cy", 360.0),
        },
    }
    return SensorObservation(
        **common,
        modality="eo",
        frame_id="pixel",
        measurement=value[:2],
        covariance=covariance[:2, :2],
        metadata=metadata,
    )


def _position_observation(
    value: np.ndarray,
    covariance: np.ndarray,
    metadata: dict[str, Any],
    common: dict[str, Any],
) -> SensorObservation:
    if value.size != 3 or covariance.shape != (3, 3):
        raise ValueError("NED position measurement must have dimension 3")
    return SensorObservation(
        **common,
        modality="lidar",
        frame_id="ned",
        measurement=value,
        covariance=covariance,
        metadata=metadata,
    )


def _acoustic_observation(
    value: np.ndarray,
    covariance: np.ndarray,
    metadata: dict[str, Any],
    common: dict[str, Any],
) -> SensorObservation:
    if value.size not in {1, 2} or covariance.shape != (value.size, value.size):
        raise ValueError("acoustic bearing measurement must have dimension 1 or 2")
    soundprint_marker_present = "soundprint_is_identity" in metadata
    soundprint_is_identity = metadata.pop("soundprint_is_identity", None)
    probabilities = metadata.get("soundprint_class_probabilities")
    if soundprint_marker_present and soundprint_is_identity is not False:
        raise ValueError("soundprint_is_identity must be false for online D1 fusion")
    if probabilities is not None:
        if not soundprint_marker_present:
            raise ValueError(
                "soundprint class probabilities require soundprint_is_identity=false"
            )
        probability_array = np.asarray(probabilities, dtype=float).reshape(-1)
        if (
            probability_array.size == 0
            or not np.isfinite(probability_array).all()
            or np.any(probability_array < 0.0)
            or float(np.sum(probability_array)) <= 0.0
        ):
            raise ValueError("soundprint_class_probabilities must be non-negative and finite")
        probability_array /= float(np.sum(probability_array))
        metadata["soundprint_class_probabilities"] = tuple(
            float(item) for item in probability_array
        )
        metadata["soundprint_category_only"] = True
    metadata.setdefault("sensor_position_ned", (0.0, 0.0, 0.0))
    return SensorObservation(
        **common,
        modality="acoustic_3d" if value.size == 2 else "acoustic",
        frame_id="ned",
        measurement=value,
        covariance=covariance,
        metadata=metadata,
    )


def _field(value: Any, name: str, default: Any = _MISSING) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
    elif hasattr(value, name):
        return getattr(value, name)
    if default is not _MISSING:
        return default
    raise ValueError(f"online scalable 3D payload is missing {name!r}")


def _is_forbidden_identity_key(value: str) -> bool:
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized == "soundprint_is_identity":
        return False
    if normalized in _FORBIDDEN_IDENTITY_KEYS:
        return True
    if normalized.startswith("truth_") or normalized.startswith("ground_truth"):
        return True
    if normalized.endswith("_truth_id") or normalized.endswith("_actor_id"):
        return True
    components = set(normalized.split("_"))
    if "truth" in components or "actor" in components:
        return True
    return bool(
        components & {"object", "entity"}
        and components & {"id", "ids", "name", "names"}
    )


def _positive_finite(value: Any, name: str) -> float:
    normalized = float(value)
    if not np.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return normalized
