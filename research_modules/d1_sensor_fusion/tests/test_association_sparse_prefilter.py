from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from unittest.mock import patch

import numpy as np
import pytest

import d1_sensor_fusion.fusion as fusion_module
from d1_sensor_fusion import (
    ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_IMPLEMENTATION_ID,
    ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR,
    ASSOCIATION_SPARSE_PREFILTER_DEFAULT_SELECTOR,
    ASSOCIATION_SPARSE_PREFILTER_DIAGNOSTICS_SCHEMA_VERSION,
    ASSOCIATION_SPARSE_PREFILTER_EXECUTION_CONFIG_SCHEMA_VERSION,
    ASSOCIATION_SPARSE_PREFILTER_MODALITY_BUCKETS,
    ASSOCIATION_SPARSE_PREFILTER_REFERENCE_IMPLEMENTATION_ID,
    ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR,
    Scalable3DFusionAdapter,
)
from d1_sensor_fusion.fusion import (
    RADAR_ASSOCIATION_PINV_RCOND,
    _association_modality_bucket,
    _conservative_quadratic_gate_masks,
)
from d1_sensor_fusion.observations import (
    CameraModel,
    acoustic_3d_h,
    acoustic_covariance,
    eo_project,
    lidar_covariance,
    radar_covariance_from_range,
    radar_h,
)
from d1_sensor_fusion.types import FusionBatchResult, SensorObservation


_OPERATION_FIELDS = {
    "association_candidate_pair_count",
    "association_measurement_model_build_count",
    "association_projection_build_count",
    "association_innovation_solve_count",
    "association_radar_track_state_build_count",
    "association_radar_observation_state_build_count",
}


def _canonical(value):
    if isinstance(value, np.ndarray):
        return _canonical(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _states(count: int, timestamp: float) -> tuple[np.ndarray, ...]:
    azimuths = np.linspace(-0.72, 0.72, count)
    ranges = 950.0 + 4.0 * np.arange(count, dtype=float)
    states = []
    for index, (azimuth, distance) in enumerate(zip(azimuths, ranges)):
        state = np.array(
            [
                distance * np.cos(azimuth),
                distance * np.sin(azimuth),
                -90.0 - 0.4 * index,
                4.0 + 0.02 * index,
                -0.4 + 0.01 * index,
                0.05,
            ],
            dtype=float,
        )
        state[:3] += state[3:] * float(timestamp)
        states.append(state)
    return tuple(states)


def _radar_scan(
    count: int,
    *,
    timestamp: float,
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    observations = []
    for index, state in enumerate(_states(count, timestamp)):
        measurement = radar_h(state, np.zeros(3, dtype=float))
        observations.append(
            SensorObservation(
                observation_id=f"{scan_id}-{index:03d}",
                sensor_id="radar-prefilter",
                modality="radar",
                measurement_timestamp=timestamp,
                arrival_timestamp=timestamp + 0.1,
                frame_id="ned",
                measurement=measurement,
                covariance=radar_covariance_from_range(float(measurement[0])),
                confidence=0.95,
                metadata={
                    "sensor_position_ned": np.zeros(3, dtype=float),
                    "scan_id": scan_id,
                    "coverage_cell": "prefilter-test",
                },
            )
        )
    return tuple(observations)


def _lidar_scan(
    count: int,
    *,
    timestamp: float,
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    return tuple(
        SensorObservation(
            observation_id=f"{scan_id}-{index:03d}",
            sensor_id="lidar-prefilter",
            modality="lidar",
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.1,
            frame_id="ned",
            measurement=state[:3],
            covariance=lidar_covariance(float(np.linalg.norm(state[:3]))),
            confidence=0.95,
            metadata={"scan_id": scan_id, "coverage_cell": "prefilter-test"},
        )
        for index, state in enumerate(_states(count, timestamp))
    )


def _acoustic_scan(
    count: int,
    *,
    timestamp: float,
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    return tuple(
        SensorObservation(
            observation_id=f"{scan_id}-{index:03d}",
            sensor_id="acoustic-prefilter",
            modality="acoustic",
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.1,
            frame_id="ned",
            measurement=np.array([np.arctan2(state[1], state[0])], dtype=float),
            covariance=acoustic_covariance(0.95),
            confidence=0.95,
            metadata={
                "sensor_position_ned": np.zeros(3, dtype=float),
                "scan_id": scan_id,
                "coverage_cell": "prefilter-test",
            },
        )
        for index, state in enumerate(_states(count, timestamp))
    )


def _acoustic_3d_scan(
    count: int,
    *,
    timestamp: float,
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    sensor_position = np.zeros(3, dtype=float)
    angular_variance = float(acoustic_covariance(0.95)[0, 0])
    return tuple(
        SensorObservation(
            observation_id=f"{scan_id}-{index:03d}",
            sensor_id="acoustic-3d-prefilter",
            modality="acoustic_3d",
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.1,
            frame_id="ned",
            measurement=acoustic_3d_h(state, sensor_position),
            covariance=np.diag([angular_variance, angular_variance]),
            confidence=0.95,
            metadata={
                "sensor_position_ned": sensor_position.copy(),
                "scan_id": scan_id,
                "coverage_cell": "prefilter-test",
                "soundprint_category_only": True,
            },
        )
        for index, state in enumerate(_states(count, timestamp))
    )


def _camera() -> CameraModel:
    return CameraModel(
        position_ned=np.zeros(3, dtype=float),
        rotation_world_to_camera=np.array(
            [
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [1.0, 0.0, 0.0],
            ],
            dtype=float,
        ),
        fx=900.0,
        fy=900.0,
        cx=640.0,
        cy=360.0,
    )


def _eo_scan(
    count: int,
    *,
    timestamp: float,
    scan_id: str,
) -> tuple[SensorObservation, ...]:
    camera = _camera()
    return tuple(
        SensorObservation(
            observation_id=f"{scan_id}-{index:03d}",
            sensor_id="eo-prefilter",
            modality="eo",
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.1,
            frame_id="pixel",
            measurement=eo_project(state, camera),
            covariance=np.diag([4.0, 4.0]),
            confidence=0.95,
            metadata={
                "camera_id": "eo-prefilter",
                "camera_position_ned": camera.position_ned.copy(),
                "rotation_world_to_camera": (
                    camera.rotation_world_to_camera.copy()
                ),
                "fx": camera.fx,
                "fy": camera.fy,
                "cx": camera.cx,
                "cy": camera.cy,
                "scan_id": scan_id,
                "coverage_cell": "prefilter-test",
            },
        )
        for index, state in enumerate(_states(count, timestamp))
    )


def _adapter(selector: str) -> Scalable3DFusionAdapter:
    return Scalable3DFusionAdapter(
        association_gate=40.0,
        association_sparse_prefilter=selector,
    )


def _assert_semantically_equal(
    reference: Scalable3DFusionAdapter,
    candidate: Scalable3DFusionAdapter,
    reference_result: FusionBatchResult,
    candidate_result: FusionBatchResult,
) -> None:
    assert _canonical(
        [track.to_dict() for track in candidate_result.tracks]
    ) == _canonical([track.to_dict() for track in reference_result.tracks])
    reference_summary = reference_result.summary.to_dict()
    candidate_summary = candidate_result.summary.to_dict()
    for field_name in _OPERATION_FIELDS:
        reference_summary.pop(field_name)
        candidate_summary.pop(field_name)
    assert _canonical(candidate_summary) == _canonical(reference_summary)
    assert _canonical(
        [item.to_dict() for item in candidate.consistency_evidence_records()]
    ) == _canonical(
        [item.to_dict() for item in reference.consistency_evidence_records()]
    )


def test_selector_is_default_off_versioned_and_strictly_validated() -> None:
    adapter = Scalable3DFusionAdapter()
    execution_config = adapter.association_sparse_prefilter_execution_config()
    diagnostics = adapter.association_sparse_prefilter_diagnostics()

    assert adapter.association_sparse_prefilter == (
        ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR
    )
    assert ASSOCIATION_SPARSE_PREFILTER_DEFAULT_SELECTOR == (
        ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR
    )
    assert execution_config["schema_version"] == (
        ASSOCIATION_SPARSE_PREFILTER_EXECUTION_CONFIG_SCHEMA_VERSION
    )
    assert execution_config["default_selector"] == (
        ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR
    )
    assert execution_config["candidate_default_enabled"] is False
    assert execution_config["rollback_selector"] == (
        ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR
    )
    assert execution_config["truth_dependent_inputs"] is False
    assert execution_config["exact_association_gate_changed"] is False
    assert tuple(execution_config["modality_policies"]) == (
        ASSOCIATION_SPARSE_PREFILTER_MODALITY_BUCKETS
    )
    assert execution_config["modality_policies"]["other"] == (
        "fail_open_exact_reference_v1"
    )
    assert diagnostics["schema_version"] == (
        ASSOCIATION_SPARSE_PREFILTER_DIAGNOSTICS_SCHEMA_VERSION
    )
    assert diagnostics["execution_config"] == execution_config
    assert diagnostics["selector"] == ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR
    assert diagnostics["selected_implementation_id"] == (
        ASSOCIATION_SPARSE_PREFILTER_REFERENCE_IMPLEMENTATION_ID
    )
    assert diagnostics["candidate_implementation_id"] == (
        ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_IMPLEMENTATION_ID
    )
    assert diagnostics["candidate_enabled"] is False
    assert diagnostics["modality_order"] == (
        ASSOCIATION_SPARSE_PREFILTER_MODALITY_BUCKETS
    )
    assert tuple(diagnostics["modality_counts"]) == (
        ASSOCIATION_SPARSE_PREFILTER_MODALITY_BUCKETS
    )
    for counters in diagnostics["modality_counts"].values():
        assert set(counters) == {
            "candidate_pair_count",
            "conservative_prefilter_rejection_count",
            "exact_innovation_solve_count",
            "exact_gate_pass_count",
            "fallback_count",
        }
        assert all(value == 0 for value in counters.values())
    assert diagnostics["conservation"]["all_counter_bounds_hold"] is True
    assert diagnostics["conservation"]["fixed_modality_bucket_count"] is True

    with pytest.raises(TypeError, match="string selector"):
        Scalable3DFusionAdapter(association_sparse_prefilter=True)
    with pytest.raises(ValueError, match="unsupported"):
        Scalable3DFusionAdapter(association_sparse_prefilter="heuristic")


@pytest.mark.parametrize(
    ("modality", "bucket"),
    [
        ("radar", "radar"),
        ("lidar", "lidar"),
        ("acoustic", "acoustic"),
        ("acoustic_3d", "acoustic_3d"),
        ("eo", "eo"),
        ("vision", "eo"),
        ("thermal", "other"),
    ],
)
def test_modality_diagnostics_use_fixed_truth_free_buckets(
    modality: str,
    bucket: str,
) -> None:
    assert _association_modality_bucket(modality) == bucket


@pytest.mark.parametrize(
    ("modality", "bucket", "scan_factory"),
    [
        ("radar", "radar", _radar_scan),
        ("lidar", "lidar", _lidar_scan),
        ("acoustic", "acoustic", _acoustic_scan),
        ("acoustic_3d", "acoustic_3d", _acoustic_3d_scan),
        ("eo", "eo", _eo_scan),
    ],
)
def test_candidate_preserves_exact_scan_outputs_without_gate_pass_loss(
    modality: str,
    bucket: str,
    scan_factory,
) -> None:
    count = 24
    reference = _adapter(ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR)
    candidate = _adapter(ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR)
    origin = _radar_scan(count, timestamp=0.0, scan_id=f"{modality}-origin")
    _assert_semantically_equal(
        reference,
        candidate,
        reference.process_scan_batch(origin),
        candidate.process_scan_batch(origin),
    )

    update = scan_factory(count, timestamp=0.2, scan_id=f"{modality}-update")
    reference_result = reference.process_scan_batch(update)
    candidate_result = candidate.process_scan_batch(update)
    _assert_semantically_equal(
        reference,
        candidate,
        reference_result,
        candidate_result,
    )

    reference_counts = reference.association_sparse_prefilter_diagnostics()[
        "modality_counts"
    ][bucket]
    candidate_diagnostics = candidate.association_sparse_prefilter_diagnostics()
    candidate_counts = candidate_diagnostics["modality_counts"][bucket]
    pair_count = count * count

    assert candidate_diagnostics["candidate_enabled"] is True
    assert candidate_diagnostics["selected_implementation_id"] == (
        ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_IMPLEMENTATION_ID
    )
    assert candidate_diagnostics["execution_config"][
        "candidate_default_enabled"
    ] is False
    assert candidate_counts["candidate_pair_count"] == pair_count
    assert candidate_counts["exact_gate_pass_count"] == (
        reference_counts["exact_gate_pass_count"]
    )
    assert candidate_counts["conservative_prefilter_rejection_count"] > 0
    assert candidate_counts["exact_innovation_solve_count"] <= (
        reference_counts["exact_innovation_solve_count"]
    )
    assert (
        candidate_counts["conservative_prefilter_rejection_count"]
        + candidate_counts["exact_innovation_solve_count"]
        == pair_count
    )
    for adapter in (reference, candidate):
        diagnostics = adapter.association_sparse_prefilter_diagnostics()
        performance = adapter.fusion_performance_diagnostics()
        assert sum(
            item["candidate_pair_count"]
            for item in diagnostics["modality_counts"].values()
        ) == performance.association_candidate_pair_count
        assert sum(
            item["exact_innovation_solve_count"]
            for item in diagnostics["modality_counts"].values()
        ) == performance.association_innovation_solve_count
        assert diagnostics["conservation"]["all_counter_bounds_hold"] is True


def test_dense_lidar_candidate_is_exact_and_reduces_solve_count() -> None:
    count = 64
    reference = _adapter(ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR)
    candidate = _adapter(ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR)
    origin = _radar_scan(count, timestamp=0.0, scan_id="dense-origin")
    reference.process_scan_batch(origin)
    candidate.process_scan_batch(origin)

    update = _lidar_scan(count, timestamp=0.2, scan_id="dense-lidar")
    reference_result = reference.process_scan_batch(update)
    candidate_result = candidate.process_scan_batch(update)
    _assert_semantically_equal(
        reference,
        candidate,
        reference_result,
        candidate_result,
    )

    reference_counts = reference.association_sparse_prefilter_diagnostics()[
        "modality_counts"
    ]["lidar"]
    candidate_counts = candidate.association_sparse_prefilter_diagnostics()[
        "modality_counts"
    ]["lidar"]
    assert candidate_counts["candidate_pair_count"] == count * count
    assert candidate_counts["fallback_count"] == 0
    assert candidate_counts["exact_innovation_solve_count"] < (
        0.25 * reference_counts["exact_innovation_solve_count"]
    )


def test_disabled_selector_retains_original_four_dimensional_batch_solve() -> None:
    count = 10
    reference = _adapter(ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR)
    candidate = _adapter(ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR)
    origin = _radar_scan(count, timestamp=0.0, scan_id="shape-origin")
    reference.process_scan_batch(origin)
    candidate.process_scan_batch(origin)
    update = _lidar_scan(count, timestamp=0.2, scan_id="shape-lidar")
    original_pinv = np.linalg.pinv

    reference_shapes: list[tuple[int, ...]] = []

    def reference_spy(value, *args, **kwargs):
        shape = tuple(int(item) for item in np.asarray(value).shape)
        if len(shape) >= 3:
            reference_shapes.append(shape)
        return original_pinv(value, *args, **kwargs)

    with patch.object(fusion_module.np.linalg, "pinv", side_effect=reference_spy):
        reference.process_scan_batch(update)

    candidate_shapes: list[tuple[int, ...]] = []

    def candidate_spy(value, *args, **kwargs):
        shape = tuple(int(item) for item in np.asarray(value).shape)
        if len(shape) >= 3:
            candidate_shapes.append(shape)
        return original_pinv(value, *args, **kwargs)

    with patch.object(fusion_module.np.linalg, "pinv", side_effect=candidate_spy):
        candidate.process_scan_batch(update)

    assert (count, count, 3, 3) in reference_shapes
    assert (count, count, 3, 3) not in candidate_shapes
    assert any(
        len(shape) == 3 and shape[-2:] == (3, 3)
        for shape in candidate_shapes
    )


@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_quadratic_lower_bound_never_rejects_an_exact_gate_pass(
    dimension: int,
) -> None:
    rng = np.random.default_rng(20260725 + dimension)
    matrices = []
    residuals = []
    for _ in range(500):
        factor = rng.normal(size=(dimension, dimension))
        matrices.append(factor @ factor.T + np.eye(dimension) * 0.05)
        residuals.append(rng.normal(size=dimension) * 8.0)
    covariance = np.asarray(matrices, dtype=float)
    residual = np.asarray(residuals, dtype=float)
    gate = 40.0

    certified, rejected = _conservative_quadratic_gate_masks(
        residual,
        covariance,
        gate,
    )
    exact = np.einsum(
        "ni,nij,nj->n",
        residual,
        np.linalg.pinv(covariance, rcond=RADAR_ASSOCIATION_PINV_RCOND),
        residual,
    )

    assert np.any(certified)
    assert not np.any(rejected & (exact <= gate))


def test_angular_wrap_uses_the_exact_legacy_residual() -> None:
    residual = np.array([[2.0e-6], [np.pi - 1.0e-6]], dtype=float)
    covariance = np.array([[[1.0e-4]], [[1.0e-4]]], dtype=float)
    certified, rejected = _conservative_quadratic_gate_masks(
        residual,
        covariance,
        40.0,
    )

    assert certified.tolist() == [True, True]
    assert rejected.tolist() == [False, True]


def test_exact_gate_boundary_is_retained_for_the_legacy_exact_solve() -> None:
    gate = 40.0
    residual = np.array([[np.sqrt(gate), 0.0]], dtype=float)
    covariance = np.eye(2, dtype=float).reshape(1, 2, 2)

    certified, rejected = _conservative_quadratic_gate_masks(
        residual,
        covariance,
        gate,
    )
    exact = float(
        residual[0]
        @ np.linalg.pinv(covariance[0], rcond=RADAR_ASSOCIATION_PINV_RCOND)
        @ residual[0]
    )

    assert certified.tolist() == [True]
    assert exact == pytest.approx(gate)
    assert rejected.tolist() == [False]


@pytest.mark.parametrize(
    "covariance",
    [
        np.array([[1.0, 1.0], [1.0, 1.0]], dtype=float),
        np.array([[1.0, 0.0], [0.0, 1.0e-20]], dtype=float),
        np.array([[np.nan, 0.0], [0.0, 1.0]], dtype=float),
        np.array([[np.inf, 0.0], [0.0, 1.0]], dtype=float),
    ],
)
def test_uncertified_singular_or_nonfinite_covariance_is_never_rejected(
    covariance: np.ndarray,
) -> None:
    certified, rejected = _conservative_quadratic_gate_masks(
        np.array([[1.0e6, -1.0e6]], dtype=float),
        covariance.reshape(1, 2, 2),
        40.0,
    )

    assert certified.tolist() == [False]
    assert rejected.tolist() == [False]


@pytest.mark.parametrize(
    "residual",
    [
        np.array([np.nan, 1.0], dtype=float),
        np.array([np.inf, 1.0], dtype=float),
        np.array([1.0e308, -1.0e308], dtype=float),
    ],
    ids=("nan", "infinite", "squared_norm_overflow"),
)
def test_nonfinite_or_overflowing_residual_is_fail_open(
    residual: np.ndarray,
) -> None:
    certified, rejected = _conservative_quadratic_gate_masks(
        residual.reshape(1, 2),
        np.eye(2, dtype=float).reshape(1, 2, 2),
        40.0,
    )

    assert certified.tolist() == [False]
    assert rejected.tolist() == [False]


def test_uncertified_lidar_covariance_falls_back_to_exact_path() -> None:
    count = 6
    reference = _adapter(ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR)
    candidate = _adapter(ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR)
    origin = _radar_scan(count, timestamp=0.0, scan_id="fallback-origin")
    reference.process_scan_batch(origin)
    candidate.process_scan_batch(origin)

    unsafe_position_covariance = np.array(
        [
            [1.0, 100.0, 0.0],
            [100.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )

    def install_unsafe_state_query(adapter: Scalable3DFusionAdapter) -> None:
        original_state_at = adapter._state_at

        def unsafe_state_at(record, timestamp):
            state = original_state_at(record, timestamp)
            state.covariance[:3, :3] = unsafe_position_covariance
            return state

        adapter._state_at = unsafe_state_at

    install_unsafe_state_query(reference)
    install_unsafe_state_query(candidate)
    update = _lidar_scan(count, timestamp=0.2, scan_id="fallback-lidar")
    reference_result = reference.process_scan_batch(update)
    candidate_result = candidate.process_scan_batch(update)
    _assert_semantically_equal(
        reference,
        candidate,
        reference_result,
        candidate_result,
    )

    counts = candidate.association_sparse_prefilter_diagnostics()[
        "modality_counts"
    ]["lidar"]
    assert counts["candidate_pair_count"] == count * count
    assert counts["conservative_prefilter_rejection_count"] == 0
    assert counts["fallback_count"] == count * count
    assert counts["exact_innovation_solve_count"] == count * count


def test_candidate_batch_solve_failure_falls_back_once_per_exact_pair() -> None:
    count = 8
    reference = _adapter(ASSOCIATION_SPARSE_PREFILTER_REFERENCE_SELECTOR)
    candidate = _adapter(ASSOCIATION_SPARSE_PREFILTER_CANDIDATE_SELECTOR)
    origin = _radar_scan(count, timestamp=0.0, scan_id="solve-fallback-origin")
    reference.process_scan_batch(origin)
    candidate.process_scan_batch(origin)
    update = _lidar_scan(count, timestamp=0.2, scan_id="solve-fallback-lidar")
    reference_result = reference.process_scan_batch(update)
    original_pinv = np.linalg.pinv

    def reject_stacked_exact_solve(value, *args, **kwargs):
        array = np.asarray(value)
        if array.ndim == 3 and array.shape[-2:] == (3, 3):
            raise np.linalg.LinAlgError("forced candidate batch solve rejection")
        return original_pinv(value, *args, **kwargs)

    with patch.object(
        fusion_module.np.linalg,
        "pinv",
        side_effect=reject_stacked_exact_solve,
    ):
        candidate_result = candidate.process_scan_batch(update)

    _assert_semantically_equal(
        reference,
        candidate,
        reference_result,
        candidate_result,
    )
    diagnostics = candidate.association_sparse_prefilter_diagnostics()
    counts = diagnostics["modality_counts"]["lidar"]
    assert counts["fallback_count"] == counts["exact_innovation_solve_count"]
    assert counts["fallback_count"] > 0
    assert diagnostics["conservation"]["all_counter_bounds_hold"] is True
