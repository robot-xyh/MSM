from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import Any

import numpy as np

from .fusion import FusionAdapter
from .observations import RadarCovarianceConfig, radar_covariance_from_range
from .online_anonymization import assert_online_observations_identity_free
from .scan_input import SensorScanFrame
from .types import FusionBatchResult, FusionStateUpdateResult, SensorObservation


SCALABLE_3D_FUSION_SCHEMA_VERSION = "d1-scalable3d-fusion-v1"
SCALABLE_3D_POSITION_ONLY_RADAR_NIS_GATE = 16.26623619623813
SCALABLE_3D_UNOBSERVED_VELOCITY_VARIANCE_M2PS2 = 25.0
ONLINE_BATCH_FRAME_HANDOFF_DIAGNOSTICS_SCHEMA_VERSION = (
    "d1.online_batch_frame_handoff_diagnostics.v1"
)
ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION = "convert_then_frame_v1"
ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION = (
    "closed_immutable_batch_to_frame_v1"
)
ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION = (
    ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
)
ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION_ID = (
    "d1.online_batch_frame.convert_then_frame.v1"
)
ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION_ID = (
    "d1.online_batch_frame.closed_immutable_batch_final_frame_validation.v1"
)
_ONLINE_BATCH_FRAME_IMPLEMENTATION_IDS = {
    ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION: (
        ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION_ID
    ),
    ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION: (
        ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION_ID
    ),
}
_ONLINE_BATCH_FIELDS = (
    "batch_id",
    "sensor_id",
    "measurement_timestamp",
    "arrival_timestamp",
    "measurements",
)
_ONLINE_MEASUREMENT_FIELDS = (
    "observation_id",
    "sensor_id",
    "modality",
    "measurement_timestamp",
    "arrival_timestamp",
    "frame_id",
    "measurement",
    "covariance",
    "confidence",
    "classification_hint",
    "metadata",
)

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


@dataclass(frozen=True, slots=True)
class _ClosedOnlineMeasurementSnapshot:
    observation_id: str
    sensor_id: str
    modality: str
    measurement_timestamp: float
    arrival_timestamp: float
    frame_id: str
    measurement: np.ndarray
    covariance: np.ndarray
    confidence: float
    classification_hint: str | None
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _ClosedOnlineBatchSnapshot:
    batch_id: str
    sensor_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    measurements: tuple[_ClosedOnlineMeasurementSnapshot, ...]


class OnlineBatchFrameBuilder:
    """Build governed scan frames without exposing a validation bypass."""

    def __init__(
        self,
        *,
        implementation: str = ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION,
        radar_covariance_config: RadarCovarianceConfig | Mapping[str, Any] | None = None,
        unobserved_velocity_variance_m2ps2: float = (
            SCALABLE_3D_UNOBSERVED_VELOCITY_VARIANCE_M2PS2
        ),
        position_only_radar_nis_gate: float = (
            SCALABLE_3D_POSITION_ONLY_RADAR_NIS_GATE
        ),
    ) -> None:
        selected = str(implementation).strip()
        if selected not in _ONLINE_BATCH_FRAME_IMPLEMENTATION_IDS:
            supported = ", ".join(sorted(_ONLINE_BATCH_FRAME_IMPLEMENTATION_IDS))
            raise ValueError(
                f"online batch frame implementation must be one of: {supported}"
            )
        self.implementation = selected
        self.radar_covariance_config = radar_covariance_config
        self.unobserved_velocity_variance_m2ps2 = _positive_finite(
            unobserved_velocity_variance_m2ps2,
            "unobserved_velocity_variance_m2ps2",
        )
        self.position_only_radar_nis_gate = _positive_finite(
            position_only_radar_nis_gate,
            "position_only_radar_nis_gate",
        )
        self._operation_counts = {
            "request_count": 0,
            "successful_build_count": 0,
            "rejected_build_count": 0,
            "reference_request_count": 0,
            "candidate_request_count": 0,
            "reference_path_execution_count": 0,
            "candidate_closed_handoff_count": 0,
            "candidate_reference_fallback_count": 0,
            "candidate_raw_rejection_count": 0,
            "candidate_resource_rejection_count": 0,
            "snapshot_structure_check_count": 0,
            "snapshot_structure_eligible_count": 0,
            "snapshot_structure_ineligible_count": 0,
            "snapshot_structure_error_count": 0,
            "closed_payload_snapshot_attempt_count": 0,
            "closed_payload_snapshot_success_count": 0,
            "closed_payload_snapshot_failure_count": 0,
            "raw_batch_identity_check_count": 0,
            "raw_measurement_identity_check_count": 0,
            "converted_observation_collection_check_count": 0,
            "frame_final_identity_check_count": 0,
            "measurement_conversion_count": 0,
            "output_observation_count": 0,
        }

    @property
    def implementation_id(self) -> str:
        return _ONLINE_BATCH_FRAME_IMPLEMENTATION_IDS[self.implementation]

    def build(self, batch: Any) -> SensorScanFrame:
        self._increment("request_count")
        self._increment(
            "reference_request_count"
            if self.implementation == ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION
            else "candidate_request_count"
        )
        try:
            if self.implementation == ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION:
                frame = self._build_reference(batch)
            else:
                frame = self._build_candidate(batch)
        except Exception:
            self._increment("rejected_build_count")
            raise
        self._increment("successful_build_count")
        self._increment("output_observation_count", len(frame.observations))
        return frame

    def execution_config(self) -> dict[str, Any]:
        return {
            "schema_version": (
                ONLINE_BATCH_FRAME_HANDOFF_DIAGNOSTICS_SCHEMA_VERSION
            ),
            "implementation": self.implementation,
            "implementation_id": self.implementation_id,
            "candidate_default_enabled": (
                ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION
                == ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
            ),
            "public_validation_bypass_available": False,
            "raw_source_absolute_immutability_claimed": False,
            "candidate_contract": (
                "full_raw_batch_identity_check_then_structural_eligibility_"
                "check_then_deep_snapshot_then_full_readonly_frame_check"
            ),
        }

    def diagnostics(self) -> dict[str, Any]:
        counts = dict(self._operation_counts)
        conservation = {
            "request_partition": (
                counts["request_count"]
                == counts["reference_request_count"]
                + counts["candidate_request_count"]
            ),
            "result_partition": (
                counts["request_count"]
                == counts["successful_build_count"]
                + counts["rejected_build_count"]
            ),
            "reference_path_partition": (
                counts["reference_path_execution_count"]
                == counts["reference_request_count"]
                + counts["candidate_reference_fallback_count"]
            ),
            "candidate_path_partition": (
                counts["candidate_request_count"]
                == counts["candidate_closed_handoff_count"]
                + counts["candidate_reference_fallback_count"]
                + counts["candidate_raw_rejection_count"]
                + counts["candidate_resource_rejection_count"]
            ),
            "snapshot_structure_check_partition": (
                counts["snapshot_structure_check_count"]
                == counts["snapshot_structure_eligible_count"]
                + counts["snapshot_structure_ineligible_count"]
                + counts["snapshot_structure_error_count"]
            ),
            "closed_payload_snapshot_partition": (
                counts["closed_payload_snapshot_attempt_count"]
                == counts["closed_payload_snapshot_success_count"]
                + counts["closed_payload_snapshot_failure_count"]
            ),
            "closed_handoff_uses_successful_snapshot": (
                counts["candidate_closed_handoff_count"]
                == counts["closed_payload_snapshot_success_count"]
            ),
            "raw_batch_check_accounting": (
                counts["raw_batch_identity_check_count"]
                == counts["candidate_request_count"]
                + counts["reference_path_execution_count"]
            ),
            "candidate_never_skips_final_frame_check": (
                counts["frame_final_identity_check_count"]
                >= counts["successful_build_count"]
            ),
        }
        return {
            **self.execution_config(),
            "operation_counts": counts,
            "conservation": conservation,
        }

    def _build_reference(self, batch: Any) -> SensorScanFrame:
        self._increment("reference_path_execution_count")
        observations = _sensor_observations_from_online_batch_reference(
            batch,
            radar_covariance_config=self.radar_covariance_config,
            unobserved_velocity_variance_m2ps2=(
                self.unobserved_velocity_variance_m2ps2
            ),
            position_only_radar_nis_gate=self.position_only_radar_nis_gate,
            operation_counts=self._operation_counts,
        )
        return self._frame_from_observations(
            observations,
            scan_id=str(_field(batch, "batch_id")),
        )

    def _build_candidate(self, batch: Any) -> SensorScanFrame:
        self._increment("raw_batch_identity_check_count")
        try:
            assert_scalable_online_payload_identity_free(batch)
        except MemoryError:
            self._increment("candidate_resource_rejection_count")
            raise
        except Exception:
            self._increment("candidate_raw_rejection_count")
            raise

        self._increment("snapshot_structure_check_count")
        try:
            snapshot_structure_eligible = (
                _is_online_batch_snapshot_structure_eligible(batch)
            )
        except MemoryError:
            self._increment("snapshot_structure_error_count")
            self._increment("candidate_resource_rejection_count")
            raise
        except Exception:
            self._increment("snapshot_structure_error_count")
            self._increment("candidate_reference_fallback_count")
            return self._build_reference(batch)

        if not snapshot_structure_eligible:
            self._increment("snapshot_structure_ineligible_count")
            self._increment("candidate_reference_fallback_count")
            return self._build_reference(batch)

        self._increment("snapshot_structure_eligible_count")
        self._increment("closed_payload_snapshot_attempt_count")
        try:
            snapshot = _snapshot_closed_online_batch(batch)
        except MemoryError:
            self._increment("closed_payload_snapshot_failure_count")
            self._increment("candidate_resource_rejection_count")
            raise
        except Exception:
            self._increment("closed_payload_snapshot_failure_count")
            self._increment("candidate_reference_fallback_count")
            return self._build_reference(batch)

        self._increment("closed_payload_snapshot_success_count")
        self._increment("candidate_closed_handoff_count")
        observations = _sensor_observations_from_closed_online_batch(
            snapshot,
            radar_covariance_config=self.radar_covariance_config,
            unobserved_velocity_variance_m2ps2=(
                self.unobserved_velocity_variance_m2ps2
            ),
            position_only_radar_nis_gate=self.position_only_radar_nis_gate,
            operation_counts=self._operation_counts,
        )
        return self._frame_from_observations(
            observations,
            scan_id=snapshot.batch_id,
        )

    def _frame_from_observations(
        self,
        observations: tuple[SensorObservation, ...],
        *,
        scan_id: str,
    ) -> SensorScanFrame:
        self._increment("frame_final_identity_check_count")
        return SensorScanFrame.from_observations(
            observations,
            scan_id=scan_id,
        )

    def _increment(self, name: str, amount: int = 1) -> None:
        self._operation_counts[name] += int(amount)


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
        radar_assignment_ambiguity_governance_v2: bool = False,
        radar_assignment_ambiguity_hold_evidence: bool = False,
        publish_opaque_source_key: bool = False,
        radar_assignment_ambiguity_neutral_centroid_correction: bool = False,
        neutral_centroid_max_component_size: int = 8,
        neutral_centroid_gain: float = 0.5,
        neutral_centroid_max_translation_m: float = 30.0,
        neutral_centroid_gate_chi2: float = (
            SCALABLE_3D_POSITION_ONLY_RADAR_NIS_GATE
        ),
        neutral_centroid_shape_gate_m2: float = 2_500.0,
        neutral_centroid_shape_inflation_scale: float = 0.05,
        neutral_centroid_min_position_variance_m2: float = 0.25,
        neutral_centroid_generation_registry_max_entries: int = 1_024,
        vectorized_covariance_limit: bool = True,
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
            radar_assignment_ambiguity_governance_v2=(
                radar_assignment_ambiguity_governance_v2
            ),
            radar_assignment_ambiguity_hold_evidence=(
                radar_assignment_ambiguity_hold_evidence
            ),
            publish_opaque_source_key=publish_opaque_source_key,
            radar_assignment_ambiguity_neutral_centroid_correction=(
                radar_assignment_ambiguity_neutral_centroid_correction
            ),
            neutral_centroid_max_component_size=(
                neutral_centroid_max_component_size
            ),
            neutral_centroid_gain=neutral_centroid_gain,
            neutral_centroid_max_translation_m=(
                neutral_centroid_max_translation_m
            ),
            neutral_centroid_gate_chi2=neutral_centroid_gate_chi2,
            neutral_centroid_shape_gate_m2=neutral_centroid_shape_gate_m2,
            neutral_centroid_shape_inflation_scale=(
                neutral_centroid_shape_inflation_scale
            ),
            neutral_centroid_min_position_variance_m2=(
                neutral_centroid_min_position_variance_m2
            ),
            neutral_centroid_generation_registry_max_entries=(
                neutral_centroid_generation_registry_max_entries
            ),
            vectorized_covariance_limit=vectorized_covariance_limit,
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

    return _sensor_observations_from_online_batch_reference(
        batch,
        radar_covariance_config=radar_covariance_config,
        unobserved_velocity_variance_m2ps2=(
            unobserved_velocity_variance_m2ps2
        ),
        position_only_radar_nis_gate=position_only_radar_nis_gate,
        operation_counts=None,
    )


def sensor_scan_frame_from_online_batch(
    batch: Any,
    *,
    implementation: str = ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION,
    radar_covariance_config: RadarCovarianceConfig | Mapping[str, Any] | None = None,
    unobserved_velocity_variance_m2ps2: float = (
        SCALABLE_3D_UNOBSERVED_VELOCITY_VARIANCE_M2PS2
    ),
    position_only_radar_nis_gate: float = SCALABLE_3D_POSITION_ONLY_RADAR_NIS_GATE,
) -> SensorScanFrame:
    """Build one governed frame with the admitted default implementation."""

    return OnlineBatchFrameBuilder(
        implementation=implementation,
        radar_covariance_config=radar_covariance_config,
        unobserved_velocity_variance_m2ps2=(
            unobserved_velocity_variance_m2ps2
        ),
        position_only_radar_nis_gate=position_only_radar_nis_gate,
    ).build(batch)


def _sensor_observations_from_online_batch_reference(
    batch: Any,
    *,
    radar_covariance_config: RadarCovarianceConfig | Mapping[str, Any] | None,
    unobserved_velocity_variance_m2ps2: float,
    position_only_radar_nis_gate: float,
    operation_counts: dict[str, int] | None,
) -> tuple[SensorObservation, ...]:
    _increment_operation(
        operation_counts,
        "raw_batch_identity_check_count",
    )
    assert_scalable_online_payload_identity_free(batch)
    (
        batch_id,
        sensor_id,
        measurement_timestamp,
        arrival_timestamp,
        measurements,
    ) = _online_batch_fields(batch)

    observations: list[SensorObservation] = []
    for measurement in measurements:
        _validate_measurement_batch_consistency(
            measurement,
            sensor_id=sensor_id,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
        )
        _increment_operation(
            operation_counts,
            "raw_measurement_identity_check_count",
        )
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
        _increment_operation(operation_counts, "measurement_conversion_count")

    _increment_operation(
        operation_counts,
        "converted_observation_collection_check_count",
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
    return _sensor_observation_from_online_measurement(
        measurement,
        batch_id=batch_id,
        radar_covariance_config=radar_covariance_config,
        unobserved_velocity_variance_m2ps2=(
            unobserved_velocity_variance_m2ps2
        ),
        position_only_radar_nis_gate=position_only_radar_nis_gate,
    )


def _sensor_observation_from_online_measurement(
    measurement: Any,
    *,
    batch_id: str,
    radar_covariance_config: RadarCovarianceConfig | Mapping[str, Any] | None,
    unobserved_velocity_variance_m2ps2: float,
    position_only_radar_nis_gate: float,
) -> SensorObservation:
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


def _sensor_observations_from_closed_online_batch(
    batch: _ClosedOnlineBatchSnapshot,
    *,
    radar_covariance_config: RadarCovarianceConfig | Mapping[str, Any] | None,
    unobserved_velocity_variance_m2ps2: float,
    position_only_radar_nis_gate: float,
    operation_counts: dict[str, int] | None,
) -> tuple[SensorObservation, ...]:
    (
        batch_id,
        sensor_id,
        measurement_timestamp,
        arrival_timestamp,
        measurements,
    ) = _online_batch_fields(batch)
    observations: list[SensorObservation] = []
    for measurement in measurements:
        _validate_measurement_batch_consistency(
            measurement,
            sensor_id=sensor_id,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
        )
        observations.append(
            _sensor_observation_from_online_measurement(
                measurement,
                batch_id=batch_id,
                radar_covariance_config=radar_covariance_config,
                unobserved_velocity_variance_m2ps2=(
                    unobserved_velocity_variance_m2ps2
                ),
                position_only_radar_nis_gate=position_only_radar_nis_gate,
            )
        )
        _increment_operation(operation_counts, "measurement_conversion_count")
    return tuple(observations)


def _online_batch_fields(
    batch: Any,
) -> tuple[str, str, float, float, tuple[Any, ...]]:
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
    return (
        batch_id,
        sensor_id,
        measurement_timestamp,
        arrival_timestamp,
        measurements,
    )


def _validate_measurement_batch_consistency(
    measurement: Any,
    *,
    sensor_id: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
) -> None:
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


def _is_online_batch_snapshot_structure_eligible(batch: Any) -> bool:
    """Check whether strict snapshotters support the current raw structure."""

    if not _is_plain_frozen_dataclass(batch, _ONLINE_BATCH_FIELDS):
        return False
    if type(batch.batch_id) is not str or type(batch.sensor_id) is not str:
        return False
    if not _is_immutable_number(batch.measurement_timestamp):
        return False
    if not _is_immutable_number(batch.arrival_timestamp):
        return False
    if type(batch.measurements) is not tuple or not batch.measurements:
        return False
    return all(
        _is_online_measurement_snapshot_structure_eligible(item)
        for item in batch.measurements
    )


def _is_online_measurement_snapshot_structure_eligible(
    measurement: Any,
) -> bool:
    if not _is_plain_frozen_dataclass(measurement, _ONLINE_MEASUREMENT_FIELDS):
        return False
    for name in ("observation_id", "sensor_id", "modality", "frame_id"):
        if type(getattr(measurement, name)) is not str:
            return False
    if not _is_immutable_number(measurement.measurement_timestamp):
        return False
    if not _is_immutable_number(measurement.arrival_timestamp):
        return False
    if not _is_immutable_number(measurement.confidence):
        return False
    if (
        measurement.classification_hint is not None
        and type(measurement.classification_hint) is not str
    ):
        return False
    if not _is_owned_readonly_numeric_array(measurement.measurement):
        return False
    if not _is_owned_readonly_numeric_array(measurement.covariance):
        return False
    return _is_supported_snapshot_metadata_value(measurement.metadata)


def _is_plain_frozen_dataclass(
    value: Any,
    expected_fields: tuple[str, ...],
) -> bool:
    if not is_dataclass(value) or isinstance(value, type):
        return False
    params = getattr(type(value), "__dataclass_params__", None)
    if params is None or not bool(params.frozen):
        return False
    if type(value).__getattribute__ is not object.__getattribute__:
        return False
    return tuple(item.name for item in fields(value)) == expected_fields


def _is_immutable_number(value: Any) -> bool:
    return (
        type(value) in {int, float}
        or isinstance(value, np.integer)
        or isinstance(value, np.floating)
    )


def _is_owned_readonly_numeric_array(value: Any) -> bool:
    return (
        type(value) is np.ndarray
        and value.dtype.kind in {"b", "i", "u", "f", "c"}
        and bool(value.flags.owndata)
        and not bool(value.flags.writeable)
        and value.base is None
    )


def _is_supported_snapshot_metadata_value(value: Any) -> bool:
    if type(value) is MappingProxyType:
        return all(
            type(key) is str and _is_supported_snapshot_metadata_value(item)
            for key, item in value.items()
        )
    if type(value) is tuple:
        return all(_is_supported_snapshot_metadata_value(item) for item in value)
    if type(value) is frozenset:
        return all(_is_supported_snapshot_metadata_value(item) for item in value)
    if type(value) is np.ndarray:
        return _is_owned_readonly_numeric_array(value)
    if isinstance(value, np.generic):
        return value.dtype.kind in {"b", "i", "u", "f", "c"}
    return value is None or type(value) in {str, bytes, int, float, bool}


def _snapshot_closed_online_batch(batch: Any) -> _ClosedOnlineBatchSnapshot:
    return _ClosedOnlineBatchSnapshot(
        batch_id=str(batch.batch_id),
        sensor_id=str(batch.sensor_id),
        measurement_timestamp=float(batch.measurement_timestamp),
        arrival_timestamp=float(batch.arrival_timestamp),
        measurements=tuple(
            _snapshot_closed_online_measurement(item)
            for item in batch.measurements
        ),
    )


def _snapshot_closed_online_measurement(
    measurement: Any,
) -> _ClosedOnlineMeasurementSnapshot:
    return _ClosedOnlineMeasurementSnapshot(
        observation_id=str(measurement.observation_id),
        sensor_id=str(measurement.sensor_id),
        modality=str(measurement.modality),
        measurement_timestamp=float(measurement.measurement_timestamp),
        arrival_timestamp=float(measurement.arrival_timestamp),
        frame_id=str(measurement.frame_id),
        measurement=_readonly_numeric_copy(measurement.measurement),
        covariance=_readonly_numeric_copy(measurement.covariance),
        confidence=float(measurement.confidence),
        classification_hint=measurement.classification_hint,
        metadata=_snapshot_closed_metadata_value(measurement.metadata),
    )


def _snapshot_closed_metadata_value(value: Any) -> Any:
    if type(value) is MappingProxyType:
        return MappingProxyType(
            {
                key: _snapshot_closed_metadata_value(item)
                for key, item in value.items()
            }
        )
    if type(value) is tuple:
        return tuple(_snapshot_closed_metadata_value(item) for item in value)
    if type(value) is frozenset:
        return frozenset(
            _snapshot_closed_metadata_value(item) for item in value
        )
    if type(value) is np.ndarray:
        return _readonly_numeric_copy(value)
    if isinstance(value, np.generic):
        return value.item()
    if value is None or type(value) in {str, bytes, int, float, bool}:
        return value
    raise TypeError(
        "closed online batch metadata contains unsupported mutable type: "
        f"{type(value).__name__}"
    )


def _readonly_numeric_copy(value: Any) -> np.ndarray:
    result = np.array(value, copy=True)
    if result.dtype.kind not in {"b", "i", "u", "f", "c"}:
        raise TypeError("closed online batch arrays must be numeric")
    result.setflags(write=False)
    return result


def _increment_operation(
    operation_counts: dict[str, int] | None,
    name: str,
    amount: int = 1,
) -> None:
    if operation_counts is not None:
        operation_counts[name] += int(amount)


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
