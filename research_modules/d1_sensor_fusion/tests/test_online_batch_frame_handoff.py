from __future__ import annotations

import inspect
import json
from collections.abc import Iterator, Mapping
from dataclasses import fields
from types import MappingProxyType
from typing import Any

import numpy as np
import pytest

import d1_sensor_fusion.scalable_3d as scalable_3d_module
from d1_sensor_fusion import (
    ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION,
    ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION_ID,
    ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION,
    ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION,
    ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION_ID,
    OnlineBatchFrameBuilder,
    SensorObservation,
    SensorScanFrame,
    canonical_sensor_scan_frame_sha256,
    sensor_observation_from_online_measurement,
    sensor_observations_from_online_batch,
    sensor_scan_frame_from_online_batch,
)
from d1_sensor_fusion.online_batch_frame_performance import (
    MINIMUM_CANDIDATE_FASTER_FRACTION,
    MINIMUM_MEASUREMENT_COUNT,
    MINIMUM_MEDIAN_IMPROVEMENT_FRACTION,
    MINIMUM_REPETITIONS,
    compare_online_batch_frame_handoff_variants,
    write_online_batch_frame_handoff_report,
)
from research_modules.scalable_3d_simulation.models import (
    OnlineSensorBatch,
    SensorMeasurement,
)


def _readonly(value: Any) -> np.ndarray:
    result = np.array(value, dtype=float, copy=True)
    result.setflags(write=False)
    return result


def _batch(count: int = 4) -> OnlineSensorBatch:
    batch_id = "handoff-test-scan"
    sensor_id = "RADAR-CENTER"
    measurements = tuple(
        SensorMeasurement(
            observation_id=f"handoff-observation-{index:04d}",
            sensor_id=sensor_id,
            modality="radar_spherical",
            measurement_timestamp=1.0,
            arrival_timestamp=1.2,
            frame_id="radar_center_frame",
            measurement=np.array([1_000.0 + index, 0.01 * index, -0.05]),
            covariance=np.diag([16.0, 1.0e-4, 1.0e-4]),
            confidence=0.95,
            classification_hint="unmanned_aircraft",
            metadata={
                "source_lineage_key": (
                    "explicit",
                    sensor_id,
                    batch_id,
                    index,
                ),
                "sensor_position_ned": (0.0, 0.0, 0.0),
            },
        )
        for index in range(count)
    )
    return OnlineSensorBatch(
        batch_id=batch_id,
        sensor_id=sensor_id,
        measurement_timestamp=1.0,
        arrival_timestamp=1.2,
        measurements=measurements,
    )


def _exception_result(
    implementation: str,
    batch: Any,
) -> tuple[tuple[str, str], dict[str, Any]]:
    builder = OnlineBatchFrameBuilder(implementation=implementation)
    with pytest.raises(Exception) as captured:
        builder.build(batch)
    return (
        (type(captured.value).__name__, str(captured.value)),
        builder.diagnostics(),
    )


def _corrupt_batch(case: str) -> OnlineSensorBatch:
    batch = _batch()
    first = batch.measurements[0]
    second = batch.measurements[1]
    if case == "truth_actor_leak":
        object.__setattr__(
            first,
            "metadata",
            MappingProxyType(
                {
                    **dict(first.metadata),
                    "actor_id": "forbidden-actor",
                }
            ),
        )
    elif case == "bad_covariance":
        object.__setattr__(
            first,
            "covariance",
            _readonly(np.diag([-1.0, 1.0e-4, 1.0e-4])),
        )
    elif case == "measurement_timestamp_conflict":
        object.__setattr__(first, "measurement_timestamp", 1.1)
    elif case == "arrival_timestamp_conflict":
        object.__setattr__(batch, "arrival_timestamp", 0.5)
    elif case == "sensor_id_conflict":
        object.__setattr__(first, "sensor_id", "RADAR-OTHER")
    elif case == "duplicate_observation_id":
        object.__setattr__(second, "observation_id", first.observation_id)
    elif case == "duplicate_source_lineage":
        object.__setattr__(
            second,
            "metadata",
            MappingProxyType(dict(first.metadata)),
        )
    elif case == "scan_modality_conflict":
        object.__setattr__(second, "modality", "lidar")
        object.__setattr__(second, "frame_id", "ned")
        object.__setattr__(
            second,
            "measurement",
            _readonly([100.0, 20.0, -5.0]),
        )
        object.__setattr__(second, "covariance", _readonly(np.eye(3)))
    else:
        raise AssertionError(f"unsupported test case: {case}")
    return batch


def test_default_candidate_and_explicit_reference_are_canonically_equal() -> None:
    batch = _batch()
    default_builder = OnlineBatchFrameBuilder()
    candidate = default_builder.build(batch)
    reference_builder = OnlineBatchFrameBuilder(
        implementation=ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION
    )
    reference = reference_builder.build(batch)

    assert default_builder.implementation == (
        ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION
    )
    assert default_builder.implementation == (
        ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    )
    assert default_builder.implementation_id == (
        ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION_ID
    )
    assert reference_builder.implementation_id == (
        ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION_ID
    )
    assert inspect.signature(OnlineBatchFrameBuilder).parameters[
        "implementation"
    ].default == ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION
    assert inspect.signature(sensor_scan_frame_from_online_batch).parameters[
        "implementation"
    ].default == ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION
    assert canonical_sensor_scan_frame_sha256(reference) == (
        canonical_sensor_scan_frame_sha256(candidate)
    )
    assert canonical_sensor_scan_frame_sha256(
        sensor_scan_frame_from_online_batch(batch)
    ) == (
        canonical_sensor_scan_frame_sha256(reference)
    )

    candidate_diagnostics = default_builder.diagnostics()
    candidate_counts = candidate_diagnostics["operation_counts"]
    reference_diagnostics = reference_builder.diagnostics()
    reference_counts = reference_diagnostics["operation_counts"]
    assert reference_counts["raw_batch_identity_check_count"] == 1
    assert reference_counts["raw_measurement_identity_check_count"] == 4
    assert reference_counts["converted_observation_collection_check_count"] == 1
    assert reference_counts["frame_final_identity_check_count"] == 1
    assert candidate_counts["raw_batch_identity_check_count"] == 1
    assert candidate_counts["raw_measurement_identity_check_count"] == 0
    assert candidate_counts["converted_observation_collection_check_count"] == 0
    assert candidate_counts["frame_final_identity_check_count"] == 1
    assert candidate_counts["candidate_closed_handoff_count"] == 1
    assert candidate_counts["candidate_reference_fallback_count"] == 0
    assert candidate_counts["snapshot_structure_check_count"] == 1
    assert candidate_counts["snapshot_structure_eligible_count"] == 1
    assert candidate_counts["closed_payload_snapshot_attempt_count"] == 1
    assert candidate_counts["closed_payload_snapshot_success_count"] == 1
    assert (
        candidate_diagnostics["raw_source_absolute_immutability_claimed"]
        is False
    )
    assert candidate_diagnostics["candidate_default_enabled"] is True
    assert reference_diagnostics["candidate_default_enabled"] is True
    assert reference_diagnostics["implementation"] == (
        ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION
    )
    assert reference_counts["reference_request_count"] == 1
    assert reference_counts["candidate_request_count"] == 0
    assert all(reference_diagnostics["conservation"].values())
    assert all(candidate_diagnostics["conservation"].values())


@pytest.mark.parametrize(
    "case",
    (
        "truth_actor_leak",
        "bad_covariance",
        "measurement_timestamp_conflict",
        "arrival_timestamp_conflict",
        "sensor_id_conflict",
        "duplicate_observation_id",
        "duplicate_source_lineage",
        "scan_modality_conflict",
    ),
)
def test_reference_and_candidate_reject_with_same_exception_summary(
    case: str,
) -> None:
    reference_summary, reference_diagnostics = _exception_result(
        ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION,
        _corrupt_batch(case),
    )
    candidate_summary, candidate_diagnostics = _exception_result(
        ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION,
        _corrupt_batch(case),
    )
    assert candidate_summary == reference_summary
    assert all(reference_diagnostics["conservation"].values())
    assert all(candidate_diagnostics["conservation"].values())


def test_public_raw_apis_keep_full_fail_closed_validation() -> None:
    batch = _corrupt_batch("truth_actor_leak")
    with pytest.raises(ValueError, match="identity truth"):
        sensor_observations_from_online_batch(batch)
    with pytest.raises(ValueError, match="identity truth"):
        sensor_observation_from_online_measurement(
            batch.measurements[0],
            batch_id=batch.batch_id,
        )

    exposed = SensorObservation(
        observation_id="exposed-observation",
        sensor_id="LIDAR-A",
        modality="lidar",
        measurement_timestamp=1.0,
        arrival_timestamp=1.1,
        frame_id="ned",
        measurement=np.array([1.0, 2.0, 3.0]),
        covariance=np.eye(3),
        metadata={
            "scan_id": "exposed-scan",
            "actor_name": "forbidden-actor",
        },
    )
    with pytest.raises(ValueError, match="identity exposure"):
        SensorScanFrame(
            scan_id="exposed-scan",
            observations=(exposed,),
        )

    public_signatures = (
        inspect.signature(sensor_observation_from_online_measurement),
        inspect.signature(sensor_observations_from_online_batch),
        inspect.signature(sensor_scan_frame_from_online_batch),
        inspect.signature(OnlineBatchFrameBuilder.build),
    )
    for signature in public_signatures:
        assert "trusted" not in signature.parameters
        assert "skip_validation" not in signature.parameters
        assert "validated" not in signature.parameters


def test_mapping_payload_falls_back_to_complete_reference_chain() -> None:
    source = _batch()
    mapping_batch = {
        "batch_id": source.batch_id,
        "sensor_id": source.sensor_id,
        "measurement_timestamp": source.measurement_timestamp,
        "arrival_timestamp": source.arrival_timestamp,
        "measurements": source.measurements,
    }
    candidate_builder = OnlineBatchFrameBuilder(
        implementation=ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    )
    candidate = candidate_builder.build(mapping_batch)
    reference = sensor_scan_frame_from_online_batch(
        mapping_batch,
        implementation=ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION,
    )
    assert canonical_sensor_scan_frame_sha256(candidate) == (
        canonical_sensor_scan_frame_sha256(reference)
    )

    diagnostics = candidate_builder.diagnostics()
    counts = diagnostics["operation_counts"]
    assert counts["candidate_reference_fallback_count"] == 1
    assert counts["candidate_closed_handoff_count"] == 0
    assert counts["snapshot_structure_ineligible_count"] == 1
    assert counts["raw_batch_identity_check_count"] == 2
    assert counts["raw_measurement_identity_check_count"] == len(
        source.measurements
    )
    assert counts["converted_observation_collection_check_count"] == 1
    assert counts["frame_final_identity_check_count"] == 1
    assert all(diagnostics["conservation"].values())


class _MutatingBatch(Mapping[str, Any]):
    def __init__(self, source: OnlineSensorBatch) -> None:
        self._payload = {
            "batch_id": source.batch_id,
            "sensor_id": source.sensor_id,
            "measurement_timestamp": source.measurement_timestamp,
            "arrival_timestamp": source.arrival_timestamp,
            "measurements": source.measurements,
        }
        self.iteration_count = 0

    def __iter__(self) -> Iterator[str]:
        self.iteration_count += 1
        keys = tuple(self._payload)
        if self.iteration_count >= 2:
            keys = (*keys, "actor_id")
        return iter(keys)

    def __len__(self) -> int:
        return len(self._payload) + int(self.iteration_count >= 2)

    def __getitem__(self, key: str) -> Any:
        if key == "actor_id":
            return "injected-actor"
        return self._payload[key]


def test_mutating_custom_payload_is_rejected_during_reference_fallback() -> None:
    payload = _MutatingBatch(_batch())
    builder = OnlineBatchFrameBuilder(
        implementation=ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    )
    with pytest.raises(ValueError, match="identity truth"):
        builder.build(payload)
    diagnostics = builder.diagnostics()
    counts = diagnostics["operation_counts"]
    assert counts["candidate_reference_fallback_count"] == 1
    assert counts["raw_batch_identity_check_count"] == 2
    assert counts["rejected_build_count"] == 1
    assert all(diagnostics["conservation"].values())


def test_snapshot_runtime_error_falls_back_to_complete_reference(
    monkeypatch,
) -> None:
    batch = _batch()
    expected = sensor_scan_frame_from_online_batch(batch)

    def raise_snapshot_runtime_error(_batch: Any) -> Any:
        raise RuntimeError("injected snapshot mapping mutation")

    monkeypatch.setattr(
        scalable_3d_module,
        "_snapshot_closed_online_batch",
        raise_snapshot_runtime_error,
    )
    builder = OnlineBatchFrameBuilder(
        implementation=ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    )
    actual = builder.build(batch)
    assert canonical_sensor_scan_frame_sha256(actual) == (
        canonical_sensor_scan_frame_sha256(expected)
    )

    diagnostics = builder.diagnostics()
    counts = diagnostics["operation_counts"]
    assert counts["candidate_reference_fallback_count"] == 1
    assert counts["candidate_closed_handoff_count"] == 0
    assert counts["candidate_resource_rejection_count"] == 0
    assert counts["closed_payload_snapshot_attempt_count"] == 1
    assert counts["closed_payload_snapshot_success_count"] == 0
    assert counts["closed_payload_snapshot_failure_count"] == 1
    assert counts["successful_build_count"] == 1
    assert counts["rejected_build_count"] == 0
    assert all(diagnostics["conservation"].values())


def test_structure_check_runtime_error_falls_back_to_complete_reference(
    monkeypatch,
) -> None:
    batch = _batch()
    expected = sensor_scan_frame_from_online_batch(batch)

    def raise_structure_runtime_error(_batch: Any) -> bool:
        raise RuntimeError("injected structure traversal mutation")

    monkeypatch.setattr(
        scalable_3d_module,
        "_is_online_batch_snapshot_structure_eligible",
        raise_structure_runtime_error,
    )
    builder = OnlineBatchFrameBuilder(
        implementation=ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    )
    actual = builder.build(batch)
    assert canonical_sensor_scan_frame_sha256(actual) == (
        canonical_sensor_scan_frame_sha256(expected)
    )

    diagnostics = builder.diagnostics()
    counts = diagnostics["operation_counts"]
    assert counts["candidate_reference_fallback_count"] == 1
    assert counts["snapshot_structure_check_count"] == 1
    assert counts["snapshot_structure_eligible_count"] == 0
    assert counts["snapshot_structure_ineligible_count"] == 0
    assert counts["snapshot_structure_error_count"] == 1
    assert counts["closed_payload_snapshot_attempt_count"] == 0
    assert counts["successful_build_count"] == 1
    assert counts["rejected_build_count"] == 0
    assert all(diagnostics["conservation"].values())


def test_snapshot_memory_error_is_rejected_without_reference_fallback(
    monkeypatch,
) -> None:
    def raise_snapshot_memory_error(_batch: Any) -> Any:
        raise MemoryError("injected snapshot allocation failure")

    monkeypatch.setattr(
        scalable_3d_module,
        "_snapshot_closed_online_batch",
        raise_snapshot_memory_error,
    )
    builder = OnlineBatchFrameBuilder(
        implementation=ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    )
    with pytest.raises(
        MemoryError,
        match="injected snapshot allocation failure",
    ):
        builder.build(_batch())

    diagnostics = builder.diagnostics()
    counts = diagnostics["operation_counts"]
    assert counts["candidate_reference_fallback_count"] == 0
    assert counts["candidate_closed_handoff_count"] == 0
    assert counts["candidate_resource_rejection_count"] == 1
    assert counts["closed_payload_snapshot_attempt_count"] == 1
    assert counts["closed_payload_snapshot_success_count"] == 0
    assert counts["closed_payload_snapshot_failure_count"] == 1
    assert counts["successful_build_count"] == 0
    assert counts["rejected_build_count"] == 1
    assert all(diagnostics["conservation"].values())


def test_snapshot_propagates_every_online_contract_field() -> None:
    assert tuple(item.name for item in fields(OnlineSensorBatch)) == (
        scalable_3d_module._ONLINE_BATCH_FIELDS
    )
    assert tuple(item.name for item in fields(SensorMeasurement)) == (
        scalable_3d_module._ONLINE_MEASUREMENT_FIELDS
    )

    batch = _batch(count=2)
    snapshot = scalable_3d_module._snapshot_closed_online_batch(batch)
    for name in scalable_3d_module._ONLINE_BATCH_FIELDS[:-1]:
        assert getattr(snapshot, name) == getattr(batch, name)
    assert len(snapshot.measurements) == len(batch.measurements)

    source = batch.measurements[0]
    copied = snapshot.measurements[0]
    for name in scalable_3d_module._ONLINE_MEASUREMENT_FIELDS:
        source_value = getattr(source, name)
        copied_value = getattr(copied, name)
        if isinstance(source_value, np.ndarray):
            np.testing.assert_array_equal(copied_value, source_value)
            assert copied_value is not source_value
            assert copied_value.flags.writeable is False
        elif isinstance(source_value, Mapping):
            assert dict(copied_value) == dict(source_value)
            assert copied_value is not source_value
        else:
            assert copied_value == source_value

    candidate = sensor_scan_frame_from_online_batch(batch)
    reference = sensor_scan_frame_from_online_batch(
        batch,
        implementation=ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION,
    )
    assert canonical_sensor_scan_frame_sha256(candidate) == (
        canonical_sensor_scan_frame_sha256(reference)
    )
    observation = candidate.observations[0]
    assert candidate.scan_id == batch.batch_id
    assert candidate.sensor_id == batch.sensor_id
    assert candidate.measurement_timestamp == batch.measurement_timestamp
    assert candidate.arrival_timestamp == batch.arrival_timestamp
    assert observation.observation_id == source.observation_id
    assert observation.sensor_id == source.sensor_id
    assert observation.classification_hint == source.classification_hint
    assert observation.confidence == source.confidence
    assert observation.metadata["source_frame_id"] == source.frame_id
    assert observation.metadata["source_modality"] == source.modality
    assert observation.measurement.flags.writeable is False
    assert observation.covariance.flags.writeable is False


def test_frame_snapshot_is_not_changed_by_source_object_mutation() -> None:
    batch = _batch()
    source = batch.measurements[0]
    original_measurement = source.measurement.copy()
    builder = OnlineBatchFrameBuilder(
        implementation=ONLINE_BATCH_FRAME_CANDIDATE_IMPLEMENTATION
    )
    frame = builder.build(batch)
    original_digest = canonical_sensor_scan_frame_sha256(frame)

    object.__setattr__(
        source,
        "measurement",
        np.array([9_999.0, 0.0, 0.0]),
    )
    object.__setattr__(
        source,
        "metadata",
        {"actor_id": "late-mutation"},
    )
    np.testing.assert_array_equal(
        frame.observations[0].measurement[:3],
        np.array(
            [
                original_measurement[0],
                original_measurement[1],
                original_measurement[2],
            ]
        ),
    )
    assert canonical_sensor_scan_frame_sha256(frame) == original_digest
    assert frame.observations[0].measurement.flags.writeable is False
    assert frame.observations[0].covariance.flags.writeable is False


def test_frozen_microbenchmark_preserves_prepromotion_gate_semantics(
    tmp_path,
) -> None:
    report = compare_online_batch_frame_handoff_variants()
    assert report["configuration"]["measurement_count"] == (
        MINIMUM_MEASUREMENT_COUNT
    )
    assert report["configuration"]["repetitions"] == MINIMUM_REPETITIONS
    assert (
        report["preregistered_policy"][
            "minimum_median_improvement_fraction"
        ]
        == MINIMUM_MEDIAN_IMPROVEMENT_FRACTION
    )
    assert (
        report["preregistered_policy"][
            "minimum_candidate_faster_fraction"
        ]
        == MINIMUM_CANDIDATE_FASTER_FRACTION
    )
    semantic_acceptance = report["comparison"]["semantic_acceptance"]
    assert (
        semantic_acceptance["default_implementation_remains_reference"]
        is False
    )
    assert all(
        value
        for name, value in semantic_acceptance.items()
        if name != "default_implementation_remains_reference"
    )
    assert all(report["comparison"]["performance_acceptance"].values())
    assert report["comparison"]["module_threshold_met"] is True
    assert report["comparison"]["recommend_main_explicit_ab"] is False
    assert report["comparison"]["recommend_default_promotion"] is False
    assert len(report["comparison"]["canonical_frame_sha256"]) == 64

    json_path = tmp_path / "benchmark.json"
    markdown_path = tmp_path / "benchmark.md"
    write_online_batch_frame_handoff_report(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["comparison"]["canonical_frame_sha256"] == (
        report["comparison"]["canonical_frame_sha256"]
    )
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "D1 模块门槛通过" in markdown
    assert "main 全栈" in markdown


def test_microbenchmark_rejects_underfilled_frozen_workload() -> None:
    with pytest.raises(ValueError, match="repetitions must be at least"):
        compare_online_batch_frame_handoff_variants(repetitions=6)
    with pytest.raises(ValueError, match="measurement_count must be at least"):
        compare_online_batch_frame_handoff_variants(measurement_count=199)
