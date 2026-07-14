from __future__ import annotations

from copy import deepcopy
import json

import numpy as np
import pytest

from d2_data_association import (
    d2_frames_from_d1_governed_replay,
    transform_d1_governed_replay,
)


def _governed_bundle(*, spacing_m: float = 4.0) -> dict:
    records = []
    for frame_index in range(11):
        timestamp = frame_index * 0.2
        for detection_index in range(2):
            records.append(
                {
                    "schema_version": "d1.sensor_observation.v1",
                    "observation_id": f"opaque-radar-{frame_index}-{detection_index}",
                    "sensor_id": "RADAR-01",
                    "modality": "radar",
                    "measurement_timestamp": timestamp,
                    "arrival_timestamp": timestamp + 0.1,
                    "frame_id": "ned",
                    "working_frame": "ned",
                    "measurement": [
                        40.0 + detection_index * 2.0,
                        -0.1 + detection_index * 0.2,
                        -0.05,
                        0.0,
                    ],
                    "covariance": np.diag([0.25, 0.0001, 0.0001, 0.5]).tolist(),
                    "confidence": 0.95,
                    "classification_hint": None,
                    "quality_flags": [],
                    "coverage_cell": "cell-test",
                    "metadata": {
                        "airsim_frame_index": frame_index,
                        "sensor_position_ned": [0.0, 0.0, 0.0],
                        "received_timestamp": timestamp + 0.1,
                    },
                    "communication": {
                        "sent_timestamp": timestamp,
                        "received_timestamp": timestamp + 0.1,
                    },
                    "source_lineage": [
                        "source_payload",
                        "RADAR-01",
                        frame_index,
                        detection_index,
                    ],
                }
            )
        records.append(
            {
                "schema_version": "d1.sensor_observation.v1",
                "observation_id": f"opaque-acoustic-{frame_index}",
                "sensor_id": "ACOUSTIC-01",
                "modality": "acoustic",
                "measurement_timestamp": timestamp,
                "arrival_timestamp": timestamp + 0.15,
                "frame_id": "ned",
                "working_frame": "ned",
                "measurement": [0.1],
                "covariance": [[0.01]],
                "confidence": 0.7,
                "classification_hint": None,
                "quality_flags": [],
                "coverage_cell": "cell-test",
                "metadata": {"airsim_frame_index": frame_index},
                "source_lineage": ["source_payload", "ACOUSTIC-01", frame_index],
            }
        )
    return {
        "manifest": {
            "schema_version": "d1.governed_replay_manifest.v1",
            "observation_schema_version": "d1.sensor_observation.v1",
            "observation_count": len(records),
            "provenance": {
                "schema_version": "d1.replay_provenance.v1",
                "scenario_id": "captured-spacing-fixture",
                "run_id": "fixture-run",
                "seed": 7,
                "metadata": {
                    "target_spacing_m": spacing_m,
                    "online_truth_id_used": False,
                },
            },
            "source_lineage": [
                {
                    "observation_id": record["observation_id"],
                    "lineage": record["source_lineage"],
                }
                for record in records
            ],
        },
        "records": records,
    }


def test_nominal_and_tight_crossing_are_capture_validation_only() -> None:
    nominal_input = _governed_bundle(spacing_m=4.0)
    tight_input = _governed_bundle(spacing_m=2.0)

    nominal = transform_d1_governed_replay(
        nominal_input,
        scenario_difficulty="nominal",
        seed=3,
        declared_target_spacing_m=4.0,
    )
    tight = transform_d1_governed_replay(
        tight_input,
        scenario_difficulty="tight_crossing",
        seed=3,
        declared_target_spacing_m=2.0,
    )

    assert nominal.payload["records"] == nominal_input["records"]
    assert tight.payload["records"] == tight_input["records"]
    assert nominal.profile_metadata["geometry_modified"] is False
    assert tight.profile_metadata["geometry_modified"] is False
    assert tight.profile_metadata["spacing_validation"] == (
        "capture_declaration_only_no_truth_geometry"
    )

    with pytest.raises(ValueError, match="requires captured target spacing"):
        transform_d1_governed_replay(
            nominal_input,
            scenario_difficulty="tight_crossing",
            seed=3,
            declared_target_spacing_m=4.0,
        )
    with pytest.raises(ValueError, match="conflicts with D1 manifest"):
        transform_d1_governed_replay(
            nominal_input,
            scenario_difficulty="tight_crossing",
            seed=3,
            declared_target_spacing_m=2.0,
        )


def test_stress_profiles_change_observation_statistics_and_remain_truth_free() -> None:
    nominal_input = _governed_bundle(spacing_m=4.0)
    tight_input = _governed_bundle(spacing_m=2.0)
    nominal = transform_d1_governed_replay(
        nominal_input,
        scenario_difficulty="nominal",
        seed=11,
        declared_target_spacing_m=4.0,
    )
    dropout = transform_d1_governed_replay(
        nominal_input,
        scenario_difficulty="dropout",
        seed=11,
        declared_target_spacing_m=4.0,
    )
    clutter = transform_d1_governed_replay(
        nominal_input,
        scenario_difficulty="clutter",
        seed=11,
        declared_target_spacing_m=4.0,
    )
    delayed = transform_d1_governed_replay(
        nominal_input,
        scenario_difficulty="delayed_noisy",
        seed=11,
        declared_target_spacing_m=4.0,
    )
    combined = transform_d1_governed_replay(
        tight_input,
        scenario_difficulty="combined",
        seed=11,
        declared_target_spacing_m=2.0,
    )

    assert dropout.statistics["output_radar_record_count"] < nominal.statistics[
        "output_radar_record_count"
    ]
    assert clutter.statistics["output_radar_record_count"] > nominal.statistics[
        "output_radar_record_count"
    ]
    assert delayed.statistics["output_radar_record_count"] == nominal.statistics[
        "output_radar_record_count"
    ]
    assert delayed.statistics["delayed_radar_record_count"] == nominal.statistics[
        "output_radar_record_count"
    ]
    assert combined.statistics["dropped_radar_record_count"] > 0
    assert combined.statistics["injected_clutter_record_count"] > 0
    assert combined.statistics["delayed_radar_record_count"] > 0

    original = nominal_input["records"][0]
    delayed_record = next(
        record
        for record in delayed.payload["records"]
        if record["observation_id"] == original["observation_id"]
    )
    assert delayed_record["measurement_timestamp"] == original[
        "measurement_timestamp"
    ]
    assert delayed_record["arrival_timestamp"] > original["arrival_timestamp"]
    assert np.allclose(
        delayed_record["covariance"], np.asarray(original["covariance"]) * 3.0
    )
    assert delayed_record["source_lineage"][: len(original["source_lineage"])] == (
        original["source_lineage"]
    )

    injected = [
        record
        for record in clutter.payload["records"]
        if "injected_anonymous_clutter" in record.get("quality_flags", [])
    ]
    assert injected
    assert all(record["sensor_id"] == "D2-INJECTED-RADAR-CLUTTER" for record in injected)
    assert all(
        record["metadata"]["injected_evaluator_scenario"]["anonymous"] is True
        for record in injected
    )
    serialized_injected = json.dumps(injected, sort_keys=True).lower()
    assert "truth_id" not in serialized_injected
    assert "actor_name" not in serialized_injected
    assert "target-" not in serialized_injected

    for result in (nominal, dropout, clutter, delayed, combined):
        assert result.online_truth_leak_count == 0
        assert result.statistics["online_truth_leak_count"] == 0
        assert result.profile_metadata["truth_sidecar_consumed"] is False
        assert result.profile_metadata["profile_digest"].startswith("sha256:")
        assert result.output_digest.startswith("sha256:")
        assert d2_frames_from_d1_governed_replay(result.payload)


def test_transform_is_reproducible_for_same_seed_and_does_not_mutate_input() -> None:
    payload = _governed_bundle(spacing_m=2.0)
    original = deepcopy(payload)

    first = transform_d1_governed_replay(
        payload,
        scenario_difficulty="combined",
        seed=29,
        declared_target_spacing_m=2.0,
    )
    second = transform_d1_governed_replay(
        payload,
        scenario_difficulty="combined",
        seed=29,
        declared_target_spacing_m=2.0,
    )
    different_seed = transform_d1_governed_replay(
        payload,
        scenario_difficulty="combined",
        seed=30,
        declared_target_spacing_m=2.0,
    )

    assert payload == original
    assert first.to_dict() == second.to_dict()
    assert first.output_digest == second.output_digest
    assert first.output_digest != different_seed.output_digest


def test_transform_rejects_online_truth_fields_without_reading_sidecar() -> None:
    payload = _governed_bundle()
    payload["records"][0]["metadata"]["truth_id"] = "forbidden"

    with pytest.raises(ValueError, match="online truth field"):
        transform_d1_governed_replay(
            payload,
            scenario_difficulty="nominal",
            seed=1,
            declared_target_spacing_m=4.0,
        )
