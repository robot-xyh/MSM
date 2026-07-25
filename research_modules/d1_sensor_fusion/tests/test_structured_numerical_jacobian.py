from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from d1_sensor_fusion import FusionAdapter
from d1_sensor_fusion.ekf import (
    numerical_jacobian,
    structured_numerical_jacobian,
)
from d1_sensor_fusion.fusion import (
    STRUCTURED_NUMERICAL_JACOBIAN_CANDIDATE_IMPLEMENTATION_ID,
    STRUCTURED_NUMERICAL_JACOBIAN_REFERENCE_IMPLEMENTATION_ID,
)
from d1_sensor_fusion.observations import (
    CameraModel,
    acoustic_3d_h,
    acoustic_h,
    eo_project,
    measurement_model_for,
    radar_h,
)
from d1_sensor_fusion.scalable_3d import Scalable3DFusionAdapter
from d1_sensor_fusion.types import SensorObservation


SENSOR_POSITION = np.array([2.0, -3.0, -1.0], dtype=float)
CAMERA = CameraModel(
    position_ned=np.array([0.0, 0.0, -20.0], dtype=float)
)


def _camera_metadata() -> dict:
    return {
        "camera_id": "camera-01:0",
        "camera_model": {
            "position_ned": CAMERA.position_ned.tolist(),
            "rotation_world_to_camera": (
                CAMERA.rotation_world_to_camera.tolist()
            ),
            "fx": CAMERA.fx,
            "fy": CAMERA.fy,
            "cx": CAMERA.cx,
            "cy": CAMERA.cy,
            "width": CAMERA.width,
            "height": CAMERA.height,
        },
    }


def _observation(
    kind: str,
    state: np.ndarray,
    *,
    observation_id: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
    scan_id: str,
) -> SensorObservation:
    metadata: dict
    if kind == "radar_full":
        modality = "radar"
        measurement = radar_h(state, SENSOR_POSITION)
        covariance = np.diag([9.0, 2.0e-4, 3.0e-4, 0.49])
        frame_id = "ned"
        metadata = {
            "sensor_position_ned": SENSOR_POSITION.tolist(),
            "radial_velocity_observed": True,
        }
    elif kind == "radar_position_only":
        modality = "radar"
        measurement = radar_h(state, SENSOR_POSITION)
        measurement[3] = 0.0
        covariance = np.diag([9.0, 2.0e-4, 3.0e-4, 100.0])
        frame_id = "ned"
        metadata = {
            "sensor_position_ned": SENSOR_POSITION.tolist(),
            "radial_velocity_observed": False,
            "unobserved_velocity_variance_m2ps2": 100.0,
        }
    elif kind == "acoustic":
        modality = "acoustic"
        measurement = acoustic_h(state, SENSOR_POSITION)
        covariance = np.diag([np.deg2rad(4.0) ** 2])
        frame_id = "ned"
        metadata = {"sensor_position_ned": SENSOR_POSITION.tolist()}
    elif kind == "acoustic_3d":
        modality = "acoustic_3d"
        measurement = acoustic_3d_h(state, SENSOR_POSITION)
        covariance = np.diag(
            [np.deg2rad(4.0) ** 2, np.deg2rad(5.0) ** 2]
        )
        frame_id = "ned"
        metadata = {"sensor_position_ned": SENSOR_POSITION.tolist()}
    elif kind == "eo":
        modality = "eo"
        measurement = eo_project(state, CAMERA)
        covariance = np.diag([16.0, 16.0])
        frame_id = "pixel"
        metadata = _camera_metadata()
    elif kind == "lidar":
        modality = "lidar"
        measurement = state[:3].copy()
        covariance = np.diag([0.25, 0.25, 0.49])
        frame_id = "ned"
        metadata = {}
    else:
        raise ValueError(f"unsupported test observation kind: {kind}")
    metadata["scan_id"] = scan_id
    return SensorObservation(
        observation_id=observation_id,
        sensor_id=f"sensor-{modality}",
        modality=modality,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id=frame_id,
        measurement=measurement,
        covariance=covariance,
        metadata=metadata,
    )


def test_candidate_is_explicit_and_default_remains_reference() -> None:
    reference = FusionAdapter()
    candidate = FusionAdapter(structured_numerical_jacobian=True)
    scalable_reference = Scalable3DFusionAdapter()
    scalable_candidate = Scalable3DFusionAdapter(
        structured_numerical_jacobian=True
    )

    assert reference.structured_numerical_jacobian is False
    assert scalable_reference.structured_numerical_jacobian is False
    assert candidate.structured_numerical_jacobian is True
    assert scalable_candidate.structured_numerical_jacobian is True
    assert (
        reference.structured_numerical_jacobian_diagnostics()[
            "implementation_id"
        ]
        == STRUCTURED_NUMERICAL_JACOBIAN_REFERENCE_IMPLEMENTATION_ID
    )
    assert (
        candidate.structured_numerical_jacobian_diagnostics()[
            "implementation_id"
        ]
        == STRUCTURED_NUMERICAL_JACOBIAN_CANDIDATE_IMPLEMENTATION_ID
    )
    with pytest.raises(TypeError, match="structured_numerical_jacobian"):
        FusionAdapter(
            structured_numerical_jacobian=1  # type: ignore[arg-type]
        )
    state = np.ones(6, dtype=float)
    observation = _observation(
        "lidar",
        state,
        observation_id="invalid-selector",
        measurement_timestamp=0.0,
        arrival_timestamp=0.1,
        scan_id="invalid-selector",
    )
    with pytest.raises(TypeError, match="structured_jacobian"):
        measurement_model_for(
            observation,
            structured_jacobian=1,  # type: ignore[arg-type]
        )


def test_structured_helper_preserves_active_columns_and_exact_zero_columns() -> None:
    state = np.array(
        [130.0, -25.0, -18.0, 4.0, -1.0, 0.5],
        dtype=float,
    )

    def observation_fn(value: np.ndarray) -> np.ndarray:
        return np.array(
            [
                np.arctan2(value[1], value[0]),
                value[2] / max(value[0], 1.0),
            ],
            dtype=float,
        )

    reference = numerical_jacobian(observation_fn, state)
    candidate = structured_numerical_jacobian(
        observation_fn,
        state,
        output_size=2,
        active_state_indices=(0, 1, 2),
    )

    assert np.array_equal(candidate, reference)
    assert np.array_equal(candidate[:, 3:], np.zeros((2, 3)))
    with pytest.raises(ValueError, match="duplicates"):
        structured_numerical_jacobian(
            observation_fn,
            state,
            output_size=2,
            active_state_indices=(0, 0),
        )
    with pytest.raises(ValueError, match="out-of-range"):
        structured_numerical_jacobian(
            observation_fn,
            state,
            output_size=2,
            active_state_indices=(6,),
        )


@pytest.mark.parametrize(
    "kind",
    (
        "radar_full",
        "radar_position_only",
        "acoustic",
        "acoustic_3d",
        "eo",
        "lidar",
    ),
)
def test_measurement_models_are_bitwise_equivalent(kind: str) -> None:
    state = np.array(
        [130.0, -25.0, -18.0, 4.0, -1.0, 0.5],
        dtype=float,
    )
    observation = _observation(
        kind,
        state,
        observation_id=f"model-{kind}",
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
        scan_id=f"model-{kind}",
    )
    reference_counts: Counter[str] = Counter()
    candidate_counts: Counter[str] = Counter()
    reference = measurement_model_for(
        observation,
        structured_jacobian=False,
        jacobian_operation_counts=reference_counts,
    )
    candidate = measurement_model_for(
        observation,
        structured_jacobian=True,
        jacobian_operation_counts=candidate_counts,
    )

    assert np.array_equal(reference.z, candidate.z)
    assert np.array_equal(reference.r, candidate.r)
    assert np.array_equal(reference.h_fn(state), candidate.h_fn(state))
    assert np.array_equal(
        reference.h_jacobian_fn(state),
        candidate.h_jacobian_fn(state),
    )
    assert reference.angle_indices == candidate.angle_indices
    assert reference.geometry_key == candidate.geometry_key
    assert reference_counts["measurement_function_evaluation_count"] == 13
    expected_candidate_evaluations = 12 if kind == "radar_full" else 6
    assert (
        candidate_counts["measurement_function_evaluation_count"]
        == expected_candidate_evaluations
    )
    expected_elided_columns = 0 if kind == "radar_full" else 3
    assert (
        candidate_counts["inactive_state_column_elision_count"]
        == expected_elided_columns
    )


def test_full_scan_fusion_preserves_tracks_covariance_and_decisions_exactly() -> None:
    reference = FusionAdapter(
        association_gate=40.0,
        structured_numerical_jacobian=False,
    )
    candidate = FusionAdapter(
        association_gate=40.0,
        structured_numerical_jacobian=True,
    )
    base_states = (
        np.array([120.0, -25.0, -15.0, 4.0, 0.5, 0.0]),
        np.array([140.0, 30.0, -18.0, 3.5, -0.4, 0.0]),
        np.array([165.0, 5.0, -22.0, 3.0, 0.2, 0.0]),
    )
    final_results = []
    for scan_index, (kind, timestamp) in enumerate(
        (
            ("radar_full", 0.0),
            ("radar_position_only", 0.1),
            ("eo", 0.2),
            ("acoustic_3d", 0.3),
            ("lidar", 0.4),
            ("acoustic", 0.25),
        )
    ):
        observations = []
        for target_index, base in enumerate(base_states):
            state = base.copy()
            state[:3] += state[3:] * timestamp
            observations.append(
                _observation(
                    kind,
                    state,
                    observation_id=(
                        f"{scan_index}-{kind}-{target_index}"
                    ),
                    measurement_timestamp=timestamp,
                    arrival_timestamp=0.2 + 0.1 * scan_index,
                    scan_id=f"{scan_index}-{kind}",
                )
            )
        reference_result = reference.process_scan_batch(observations)
        candidate_result = candidate.process_scan_batch(observations)
        assert reference_result.to_dict() == candidate_result.to_dict()
        final_results.append(candidate_result)

    assert len(final_results[-1].tracks) == 3
    for expected, actual in zip(
        reference.global_tracks(),
        candidate.global_tracks(),
        strict=True,
    ):
        assert expected.global_track_id == actual.global_track_id
        assert expected.timestamp == actual.timestamp
        assert (
            expected.metadata["latest_measurement_timestamp"]
            == actual.metadata["latest_measurement_timestamp"]
        )
        assert (
            expected.metadata["latest_arrival_timestamp"]
            == actual.metadata["latest_arrival_timestamp"]
        )
        assert np.array_equal(expected.state, actual.state)
        assert np.array_equal(expected.covariance, actual.covariance)
        assert expected.to_dict() == actual.to_dict()

    reference_diagnostics = (
        reference.structured_numerical_jacobian_diagnostics()
    )
    candidate_diagnostics = (
        candidate.structured_numerical_jacobian_diagnostics()
    )
    assert all(reference_diagnostics["conservation"].values())
    assert all(candidate_diagnostics["conservation"].values())
    reference_operations = reference_diagnostics["operation_counts"]
    candidate_operations = candidate_diagnostics["operation_counts"]
    assert (
        reference_operations["jacobian_attempt_count"]
        == candidate_operations["jacobian_attempt_count"]
    )
    assert reference_operations["output_probe_evaluation_count"] > 0
    assert candidate_operations["output_probe_elision_count"] > 0
    assert (
        candidate_operations["measurement_function_evaluation_count"]
        < reference_operations["measurement_function_evaluation_count"]
    )
