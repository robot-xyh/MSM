from __future__ import annotations

from dataclasses import replace
import json
import math
from typing import Any

import numpy as np
import pytest

from d1_sensor_fusion import (
    CONSISTENCY_RANGE_BIN_SCHEMA_VERSION,
    D2_LINEAGE_MAPPING_SIDECAR_SCHEMA_VERSION,
    OFFLINE_CONSISTENCY_RESULT_SCHEMA_VERSION,
    ONLINE_CONSISTENCY_EVIDENCE_BUNDLE_SCHEMA_VERSION,
    ConsistencySourceProvenance,
    D2LineageTruthMapping,
    OnlineConsistencyEvidenceBundle,
    Scalable3DFusionAdapter,
    build_d2_lineage_mapping_sidecar,
    build_offline_truth_state_sidecar,
    evaluate_offline_consistency,
    export_online_consistency_evidence,
)


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _provenance(
    producer_id: str,
    source_character: str,
    *,
    source_schema_version: str,
) -> ConsistencySourceProvenance:
    return ConsistencySourceProvenance(
        scenario_id="scalable-consistency-contract",
        scenario_version="scenario-v3",
        run_id="seed-019",
        seed=19,
        producer_id=producer_id,
        producer_version="producer-v1",
        source_schema_version=source_schema_version,
        source_digest=_digest(source_character),
        config_digest=_digest("f"),
    )


def _radar_measurement(
    observation_id: str,
    position_ned: np.ndarray,
    *,
    measurement_timestamp: float,
    arrival_timestamp: float,
    sensor_id: str = "RADAR-CONSISTENCY-001",
) -> dict[str, Any]:
    position = np.asarray(position_ned, dtype=float)
    range_m = float(np.linalg.norm(position))
    horizontal = float(np.linalg.norm(position[:2]))
    return {
        "observation_id": observation_id,
        "sensor_id": sensor_id,
        "modality": "radar_spherical",
        "measurement_timestamp": measurement_timestamp,
        "arrival_timestamp": arrival_timestamp,
        "frame_id": "radar_consistency_frame",
        "measurement": np.array(
            [
                range_m,
                math.atan2(float(position[1]), float(position[0])),
                math.atan2(float(-position[2]), max(horizontal, 1.0e-9)),
            ]
        ),
        "covariance": np.diag(
            [4.0, math.radians(0.2) ** 2, math.radians(0.2) ** 2]
        ),
        "confidence": 0.96,
        "metadata": {
            "sensor_position_ned": [0.0, 0.0, 0.0],
            "range_dependent_covariance": True,
            "covariance_scale_reason": "range_dependent_sensor_model",
            "sequence_id": f"payload-{observation_id}",
        },
    }


def _batch(
    batch_id: str,
    measurements: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    first = measurements[0]
    return {
        "batch_id": batch_id,
        "sensor_id": first["sensor_id"],
        "measurement_timestamp": first["measurement_timestamp"],
        "arrival_timestamp": first["arrival_timestamp"],
        "measurements": measurements,
    }


def _process_radar_scan(
    adapter: Scalable3DFusionAdapter,
    label: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
    positions: tuple[np.ndarray, ...],
) -> None:
    measurements = tuple(
        _radar_measurement(
            f"{label}-d{index:03d}",
            position,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
        )
        for index, position in enumerate(positions)
    )
    adapter.process_online_sensor_batch(_batch(label, measurements))


def _online_bundle() -> OnlineConsistencyEvidenceBundle:
    adapter = Scalable3DFusionAdapter(association_gate=40.0)
    scans = (
        ("gate-000", 0.0, np.array([1_000.0, 0.0, -100.0])),
        ("gate-001", 0.2, np.array([1_000.8, 0.0, -100.0])),
        ("gate-002-outlier", 0.4, np.array([1_001.6, 20.0, -100.0])),
    )
    for label, timestamp, position in scans:
        _process_radar_scan(
            adapter,
            label,
            timestamp,
            timestamp + 0.2,
            (position,),
        )
    return adapter.export_consistency_evidence(
        _provenance("d1_sensor_fusion.scalable_3d", "a", source_schema_version="bus-v3")
    )


def _truth_for_bundle(
    bundle: OnlineConsistencyEvidenceBundle,
    *,
    timestamp_offset_s: float = 0.0,
) -> Any:
    samples = []
    offset = np.array([3.0, 4.0, 0.0, 0.0, 0.0, 12.0])
    for record in bundle.records:
        if not record.availability.estimate.available:
            continue
        assert record.state_ned is not None and record.estimate_timestamp is not None
        samples.append(
            {
                "truth_id": "truth-track-001",
                "timestamp": record.estimate_timestamp + timestamp_offset_s,
                "state_ned": (np.asarray(record.state_ned) - offset).tolist(),
            }
        )
    return build_offline_truth_state_sidecar(
        _provenance("main.offline_truth_writer", "b", source_schema_version="truth-v2"),
        samples,
    )


def _mapping_for_bundle(
    bundle: OnlineConsistencyEvidenceBundle,
    truth: Any,
    *,
    truth_id: str = "truth-track-001",
    online_evidence_digest: str | None = None,
) -> Any:
    estimate_records = [
        record for record in bundle.records if record.availability.estimate.available
    ]
    return build_d2_lineage_mapping_sidecar(
        _provenance("d2_data_association.offline_evaluator", "c", source_schema_version="d2-v4"),
        [
            D2LineageTruthMapping(
                observation_id=record.observation_id,
                measurement_timestamp=record.measurement_timestamp,
                global_track_id="D2-CANONICAL-001",
                truth_id=truth_id,
            )
            for record in estimate_records
        ],
        online_evidence_digest=(
            bundle.content_digest
            if online_evidence_digest is None
            else online_evidence_digest
        ),
        truth_sidecar_digest=truth.content_digest,
    )


def test_online_evidence_exports_accepted_and_rejected_updates_truth_free() -> None:
    bundle = _online_bundle()
    records = {record.observation_id: record for record in bundle.records}
    initial = records["gate-000-d000"]
    accepted = records["gate-001-d000"]
    rejected = records["gate-002-outlier-d000"]

    assert bundle.schema_version == ONLINE_CONSISTENCY_EVIDENCE_BUNDLE_SCHEMA_VERSION
    assert bundle.records_digest.startswith("sha256:")
    assert bundle.content_digest.startswith("sha256:")
    assert initial.disposition == "track_initialization"
    assert initial.availability.innovation.available is False
    assert accepted.accepted is True
    assert accepted.gate_decision == "accepted"
    assert accepted.innovation_dimension == 3
    assert accepted.nis is not None and accepted.nis < accepted.gate_threshold
    assert rejected.accepted is False
    assert rejected.gate_decision == "rejected"
    assert rejected.nis is not None and rejected.nis > rejected.gate_threshold
    assert rejected.source_global_track_id == initial.source_global_track_id
    assert rejected.source_lineage[0] == "opaque_online_lineage"
    assert rejected.range_m is not None
    assert rejected.range_bin == "[1000,3000)m"
    assert rejected.covariance_scale_reasons == ("range_dependent_sensor_model",)

    rows = bundle.aggregation_records()
    assert len(rows) == 3
    assert {row["scenario_id"] for row in rows} == {
        "scalable-consistency-contract"
    }
    assert {row["sensor_id"] for row in rows} == {"RADAR-CONSISTENCY-001"}
    assert all(row["online_evidence_digest"] == bundle.content_digest for row in rows)
    payload = bundle.to_dict()
    json.dumps(payload, allow_nan=False)
    assert not _contains_forbidden_online_identity_key(payload)

    tampered = json.loads(json.dumps(payload))
    tampered["records"][0]["confidence"] = 0.5
    with pytest.raises(ValueError, match="digest mismatch"):
        OnlineConsistencyEvidenceBundle.from_mapping(tampered)

    leaked = json.loads(json.dumps(payload))
    leaked["records"][0]["truth_target_id"] = "forbidden-online-truth"
    with pytest.raises(ValueError, match="unsupported field"):
        OnlineConsistencyEvidenceBundle.from_mapping(leaked)


def test_oosm_replay_revises_evidence_and_preserves_measurement_time() -> None:
    positions = {
        0.0: np.array([1_200.0, -200.0, -120.0]),
        0.5: np.array([1_202.0, -199.5, -120.1]),
        1.0: np.array([1_204.0, -199.0, -120.2]),
    }

    def run(schedule: tuple[tuple[str, float, float], ...]) -> Scalable3DFusionAdapter:
        adapter = Scalable3DFusionAdapter(association_gate=40.0)
        for label, measurement_timestamp, arrival_timestamp in schedule:
            _process_radar_scan(
                adapter,
                label,
                measurement_timestamp,
                arrival_timestamp,
                (positions[measurement_timestamp],),
            )
        return adapter

    ordered = run(
        (("scan-000", 0.0, 0.2), ("scan-050", 0.5, 0.7), ("scan-100", 1.0, 1.4))
    )
    delayed = run(
        (
            ("scan-000", 0.0, 0.2),
            ("scan-100", 1.0, 1.2),
            ("scan-050", 0.5, 1.4),
        )
    )
    ordered_records = {item.observation_id: item for item in ordered.consistency_evidence_records()}
    delayed_records = {item.observation_id: item for item in delayed.consistency_evidence_records()}

    middle = delayed_records["scan-050-d000"]
    assert middle.oosm_replayed is True
    assert middle.measurement_timestamp == pytest.approx(0.5)
    assert middle.arrival_timestamp == pytest.approx(1.4)
    assert middle.replay_count >= 1
    assert middle.replay_revision > 0
    for observation_id in ordered_records:
        left = ordered_records[observation_id]
        right = delayed_records[observation_id]
        assert right.nis == pytest.approx(left.nis, abs=1.0e-10)
        np.testing.assert_allclose(right.state_ned, left.state_ned, atol=1.0e-9)
        np.testing.assert_allclose(right.covariance_ned, left.covariance_ned, atol=1.0e-9)


def test_validated_replay_counter_copy_matches_full_dataclass_revalidation() -> None:
    record = _online_bundle().records[1]

    expected = replace(
        record,
        replay_revision=record.replay_revision + 7,
        replay_count=record.replay_count + 11,
    )
    actual = record.with_replay_counters(
        replay_revision=record.replay_revision + 7,
        replay_count=record.replay_count + 11,
    )

    assert actual == expected
    assert actual.to_dict() == expected.to_dict()
    assert actual.evidence_id == record.evidence_id
    assert actual.state_ned is record.state_ned
    assert actual.covariance_ned is record.covariance_ned
    assert actual.availability is record.availability
    with pytest.raises(ValueError, match="must be non-negative"):
        record.with_replay_counters(replay_revision=-1, replay_count=0)
    with pytest.raises(ValueError, match="must be non-negative"):
        record.with_replay_counters(replay_revision=0, replay_count=-1)


def test_radar_range_bins_and_record_count_scale_with_input() -> None:
    adapter = Scalable3DFusionAdapter()
    ranges = (500.0, 1_500.0, 3_500.0, 5_500.0)
    positions = tuple(
        np.array([distance * math.cos(index), distance * math.sin(index), -100.0])
        for index, distance in enumerate(ranges)
    )
    _process_radar_scan(adapter, "range-scan", 0.0, 0.2, positions)
    records = adapter.consistency_evidence_records()

    assert len(records) == len(ranges)
    assert [record.range_bin for record in records] == [
        "[0,1000)m",
        "[1000,3000)m",
        "[3000,5000)m",
        "[5000,+inf)m",
    ]
    assert all(record.availability.range.available for record in records)
    assert CONSISTENCY_RANGE_BIN_SCHEMA_VERSION


@pytest.mark.parametrize("measurement_count", [1, 4, 7])
def test_online_evidence_has_no_baseline_size_constant(measurement_count: int) -> None:
    adapter = Scalable3DFusionAdapter()
    positions = tuple(
        np.array([1_000.0 + 50.0 * index, 200.0 * index, -100.0])
        for index in range(measurement_count)
    )
    _process_radar_scan(adapter, f"scale-{measurement_count}", 0.0, 0.2, positions)

    assert len(adapter.consistency_evidence_records()) == measurement_count


def test_acoustic_and_eo_publish_explicit_availability() -> None:
    empty = Scalable3DFusionAdapter()
    acoustic = {
        "observation_id": "acoustic-no-track",
        "sensor_id": "ACOUSTIC-001",
        "modality": "acoustic_bearing",
        "measurement_timestamp": 0.0,
        "arrival_timestamp": 0.1,
        "frame_id": "acoustic-frame",
        "measurement": np.array([0.0, math.atan2(100.0, 1_000.0)]),
        "covariance": np.eye(2) * math.radians(2.0) ** 2,
        "metadata": {"sensor_position_ned": [0.0, 0.0, 0.0]},
    }
    eo = {
        "observation_id": "eo-no-track",
        "sensor_id": "EO-001",
        "modality": "vision_bbox",
        "measurement_timestamp": 0.2,
        "arrival_timestamp": 0.3,
        "frame_id": "camera-frame",
        "measurement": np.array([640.0, 279.0, 630.0, 270.0, 650.0, 288.0]),
        "covariance": np.eye(6) * 4.0,
        "metadata": {"camera_position_ned": [0.0, 0.0, -10.0]},
    }
    empty.process_online_sensor_batch(_batch("acoustic-empty", (acoustic,)))
    empty.process_online_sensor_batch(_batch("eo-empty", (eo,)))
    unavailable = {item.observation_id: item for item in empty.consistency_evidence_records()}
    for observation_id in ("acoustic-no-track", "eo-no-track"):
        record = unavailable[observation_id]
        assert record.availability.innovation.available is False
        assert record.availability.estimate.available is False
        assert record.availability.range.available is False
        assert record.source_global_track_id is None
        assert record.disposition == "unsupported_track_initializer"

    adapter = Scalable3DFusionAdapter(association_gate=40.0)
    _process_radar_scan(
        adapter,
        "radar-prior",
        0.0,
        0.1,
        (np.array([1_000.0, 0.0, -100.0]),),
    )
    accepted_acoustic = dict(acoustic)
    accepted_acoustic.update(
        observation_id="acoustic-update",
        measurement_timestamp=0.1,
        arrival_timestamp=0.2,
    )
    adapter.process_online_sensor_batch(_batch("acoustic-update", (accepted_acoustic,)))
    record = next(
        item
        for item in adapter.consistency_evidence_records()
        if item.observation_id == "acoustic-update"
    )
    assert record.accepted is True
    assert record.innovation_dimension == 2
    assert record.availability.innovation.available is True
    assert record.availability.gate.available is False
    assert record.gate_decision == "not_configured"
    assert record.availability.range.available is False


def test_offline_evaluator_computes_rmse_nees_and_nis_coverage() -> None:
    bundle = _online_bundle()
    truth = _truth_for_bundle(bundle)
    mapping = _mapping_for_bundle(bundle, truth)

    result = evaluate_offline_consistency(bundle, truth, mapping)
    payload = result.to_dict()

    assert result.schema_version == OFFLINE_CONSISTENCY_RESULT_SCHEMA_VERSION
    assert result.status == "available"
    assert result.metrics["position_rmse_m"].value == pytest.approx(5.0)
    assert result.metrics["velocity_rmse_mps"].value == pytest.approx(12.0)
    assert result.metrics["mean_nees"].available is True
    assert result.metrics["mean_normalized_nees"].available is True
    assert result.metrics["nis_gate_coverage"].value == pytest.approx(0.5)
    assert result.metrics["nis_gate_coverage"].sample_count == 2
    assert result.online_evidence_digest == bundle.content_digest
    assert result.truth_sidecar_digest == truth.content_digest
    assert result.d2_lineage_mapping_digest == mapping.content_digest
    assert mapping.schema_version == D2_LINEAGE_MAPPING_SIDECAR_SCHEMA_VERSION
    assert all(record.source_global_track_id for record in result.records)
    assert all(record.global_track_id == "D2-CANONICAL-001" for record in result.records)
    assert all(record.truth_id == "truth-track-001" for record in result.records)
    assert len(result.aggregation_records()) == len(bundle.records)
    assert {
        row["range_bin"] for row in result.aggregation_records()
    } == {"[1000,3000)m"}
    json.dumps(payload, allow_nan=False)


def test_missing_or_wrong_mapping_fails_truth_metrics_closed() -> None:
    bundle = _online_bundle()
    truth = _truth_for_bundle(bundle)

    missing = evaluate_offline_consistency(bundle, truth, None)
    assert missing.status == "partial"
    assert missing.metrics["position_rmse_m"].available is False
    assert missing.metrics["mean_nees"].available is False
    assert missing.metrics["mean_nis"].available is True
    assert "d2_lineage_mapping_missing" in missing.failure_reasons

    wrong_truth = _mapping_for_bundle(bundle, truth, truth_id="unknown-truth")
    wrong = evaluate_offline_consistency(bundle, truth, wrong_truth)
    assert wrong.metrics["position_rmse_m"].available is False
    assert "d2_lineage_mapping_references_unknown_truth_id" in wrong.failure_reasons

    wrong_digest = _mapping_for_bundle(
        bundle,
        truth,
        online_evidence_digest=_digest("e"),
    )
    mismatched = evaluate_offline_consistency(bundle, truth, wrong_digest)
    assert mismatched.metrics["velocity_rmse_mps"].available is False
    assert "d2_lineage_mapping_online_evidence_digest_mismatch" in mismatched.failure_reasons


def test_truth_tampering_dimension_and_time_mismatch_are_unavailable() -> None:
    bundle = _online_bundle()
    truth = _truth_for_bundle(bundle)
    mapping = _mapping_for_bundle(bundle, truth)

    tampered = truth.to_dict()
    tampered["samples"][0]["state_ned"][0] += 100.0
    tampered_result = evaluate_offline_consistency(bundle, tampered, mapping)
    assert tampered_result.metrics["position_rmse_m"].available is False
    assert any("digest_mismatch" in reason for reason in tampered_result.failure_reasons)
    assert tampered_result.metrics["mean_nis"].available is True

    wrong_dimension = truth.to_dict()
    wrong_dimension["samples"][0]["state_ned"] = [0.0, 1.0, 2.0]
    dimension_result = evaluate_offline_consistency(bundle, wrong_dimension, mapping)
    assert dimension_result.metrics["mean_nees"].available is False
    assert any("six-state" in reason for reason in dimension_result.failure_reasons)

    shifted_truth = _truth_for_bundle(bundle, timestamp_offset_s=0.01)
    shifted_mapping = _mapping_for_bundle(bundle, shifted_truth)
    time_result = evaluate_offline_consistency(bundle, shifted_truth, shifted_mapping)
    assert time_result.metrics["position_rmse_m"].available is False
    assert "offline_truth_timestamp_missing_or_ambiguous" in time_result.failure_reasons


def test_singular_covariance_disables_nees_but_keeps_finite_rmse() -> None:
    source = _online_bundle()
    records = list(source.records)
    records[0] = replace(
        records[0],
        covariance_ned=tuple(tuple(0.0 for _ in range(6)) for _ in range(6)),
    )
    bundle = export_online_consistency_evidence(records, source.provenance)
    truth = _truth_for_bundle(bundle)
    mapping = _mapping_for_bundle(bundle, truth)

    result = evaluate_offline_consistency(bundle, truth, mapping)

    assert result.metrics["position_rmse_m"].available is True
    assert result.metrics["velocity_rmse_mps"].available is True
    assert result.metrics["mean_nees"].available is False
    assert result.metrics["mean_nees"].reason == (
        "episode_contains_singular_estimate_covariance"
    )
    assert "nees_unavailable:estimate_covariance_singular" in result.failure_reasons
    assert all(
        record.nees is None
        for record in result.records
        if record.truth_alignment_availability.available
    )
    json.dumps(result.to_dict(), allow_nan=False)


def test_non_finite_online_evidence_is_rejected_without_nan_output() -> None:
    bundle = _online_bundle()
    payload = bundle.to_dict()
    payload["records"][0]["state_ned"][0] = float("nan")

    result = evaluate_offline_consistency(payload, None, None)

    assert result.status == "unavailable"
    assert result.records == ()
    assert all(not summary.available for summary in result.metrics.values())
    json.dumps(result.to_dict(), allow_nan=False)


def _contains_forbidden_online_identity_key(value: Any) -> bool:
    forbidden = {
        "truth_target_id",
        "truth_entity_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
    }
    if isinstance(value, dict):
        return any(
            str(key).lower() in forbidden
            or _contains_forbidden_online_identity_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_online_identity_key(item) for item in value)
    return False
