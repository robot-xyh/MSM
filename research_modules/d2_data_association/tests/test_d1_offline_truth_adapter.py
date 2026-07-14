from __future__ import annotations

from copy import deepcopy
import json
from math import atan2, hypot

import pytest

from d2_data_association import (
    D1_AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION,
    D1_OFFLINE_TRUTH_TIMESTAMP_TOLERANCE_S,
    P1_IDENTITY_INPUT_SCHEMA_VERSION,
    align_d1_airsim_offline_truth,
    d2_labels_from_d1_airsim_offline_truth,
    load_identity_calibration_manifest,
    run_airsim_replay_association,
    run_p1_identity_calibration,
)


def _d1_governed_bundle() -> dict:
    records = []
    for frame_index in range(3):
        timestamp = frame_index * 0.5
        for target_index in range(2):
            position = (
                20.0 + frame_index + target_index * 3.0,
                -2.0 + target_index * 4.0,
                -5.0,
            )
            radius = hypot(hypot(position[0], position[1]), position[2])
            azimuth = atan2(position[1], position[0])
            elevation = atan2(position[2], hypot(position[0], position[1]))
            records.append(
                {
                    "schema_version": "d1.sensor_observation.v1",
                    "observation_id": f"opaque-{frame_index}-{target_index}",
                    "sensor_id": "RADAR-01",
                    "modality": "radar",
                    "measurement_timestamp": timestamp,
                    "arrival_timestamp": timestamp + 0.1,
                    "frame_id": "ned",
                    "working_frame": "ned",
                    "measurement": [radius, azimuth, elevation, 0.0],
                    "covariance": [
                        [0.04, 0.0, 0.0, 0.0],
                        [0.0, 0.0001, 0.0, 0.0],
                        [0.0, 0.0, 0.0001, 0.0],
                        [0.0, 0.0, 0.0, 1.0],
                    ],
                    "confidence": 0.95,
                    "metadata": {
                        "airsim_frame_index": frame_index,
                        "sensor_position_ned": [0.0, 0.0, 0.0],
                    },
                }
            )
    return {
        "manifest": {
            "schema_version": "d1.governed_replay_manifest.v1",
            "observation_schema_version": "d1.sensor_observation.v1",
            "working_frame": "ned",
            "provenance": {
                "run_id": "d1-sidecar-e2e",
                "scenario_id": "dense-crossing",
                "seed": 17,
                "metadata": {"target_count": 2, "target_spacing_m": 4.0},
            },
        },
        "records": records,
    }


def _d1_truth_sidecar() -> dict:
    samples = []
    for frame_index in range(3):
        timestamp = frame_index * 0.5
        for target_index in range(2):
            samples.append(
                {
                    "truth_id": f"TGT-{target_index + 1:03d}",
                    "timestamp": timestamp,
                    "position_ned": [
                        20.0 + frame_index + target_index * 3.0,
                        -2.0 + target_index * 4.0,
                        -5.0,
                    ],
                    "position_availability": "available",
                    "source_payload_index": frame_index,
                }
            )
    return {
        "schema_version": D1_AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION,
        "frame_id": "ned",
        "evaluator_only": True,
        "sample_count": len(samples),
        "target_count": 2,
        "samples": samples,
    }


def test_d1_governed_replay_and_truth_sidecar_end_to_end(tmp_path) -> None:
    replay_path = tmp_path / "d1_governed_replay.json"
    truth_path = tmp_path / "offline_truth.json"
    manifest_path = tmp_path / "calibration_manifest.json"
    replay_path.write_text(json.dumps(_d1_governed_bundle()), encoding="utf-8")
    truth_path.write_text(json.dumps(_d1_truth_sidecar()), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": P1_IDENTITY_INPUT_SCHEMA_VERSION,
                "evidence_source": "airsim",
                "frozen_p95_loop_latency_budget_s": 0.02,
                "cases": [
                    {
                        "seed": 17,
                        "replay_name": "d1-sidecar-e2e",
                        "replay_path": replay_path.name,
                        "truth_path": truth_path.name,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases, budget = load_identity_calibration_manifest(manifest_path)

    assert budget == 0.02
    assert len(cases) == 1
    case = cases[0]
    assert len(case.frames) == 3
    assert all(
        frame["replay_metadata"]["target_spacing_m"] == 4.0
        for frame in case.frames
    )
    assert case.target_spacing_provenance["valid"] is True
    assert len(case.offline_truth_labels) == 6
    assert {label.episode_id for label in case.offline_truth_labels} == {
        "d1-sidecar-e2e"
    }
    assert all(label.match_annotation["source_frame_id"] == "ned" for label in case.offline_truth_labels)
    online_text = json.dumps(case.frames, sort_keys=True)
    assert "TGT-001" not in online_text
    assert "TGT-002" not in online_text
    assert "truth_id" not in online_text

    report = run_airsim_replay_association(
        case.frames,
        replay_name=case.replay_name,
        offline_truth_labels=case.offline_truth_labels,
    )
    assert report.metrics["truth_metrics_available"] is True
    assert report.metrics["continuity_available"] is True
    assert report.metrics["truth_target_count"] == 2
    assert report.metrics["online_truth_isolation_violations"] == 0
    serialized_online = json.dumps(
        {
            "online_metrics": report.online_metrics,
            "association_logs": report.association_logs,
        },
        sort_keys=True,
    )
    assert "TGT-001" not in serialized_online
    assert "truth_id" not in serialized_online


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda payload: payload.update({"frame_id": "enu"}), "frame_id must be NED"),
        (
            lambda payload: payload["samples"][0].update({"timestamp": float("nan")}),
            "timestamp must be finite",
        ),
        (
            lambda payload: payload["samples"][0].update({"truth_id": ""}),
            "empty truth_id",
        ),
        (
            lambda payload: payload["samples"][0].update({"position_ned": [1.0, 2.0]}),
            "position_ned must have 3 values",
        ),
    ],
)
def test_d1_truth_sidecar_rejects_invalid_frame_time_identity_and_position(
    mutation, expected
) -> None:
    frames = [
        {
            "frame_index": index,
            "measurement_timestamp": index * 0.5,
            "detections": [],
            "replay_metadata": {"episode_id": "d1-sidecar-e2e"},
        }
        for index in range(3)
    ]
    payload = deepcopy(_d1_truth_sidecar())
    mutation(payload)

    with pytest.raises(ValueError, match=expected):
        d2_labels_from_d1_airsim_offline_truth(payload, replay_frames=frames)


def test_d1_truth_sidecar_reports_timestamp_without_governed_frame() -> None:
    frames = [
        {
            "frame_index": 0,
            "measurement_timestamp": 0.0,
            "detections": [],
            "replay_metadata": {"episode_id": "d1-sidecar-e2e"},
        }
    ]
    payload = _d1_truth_sidecar()

    result = align_d1_airsim_offline_truth(payload, replay_frames=frames)

    assert len(result.labels) == 2
    assert result.summary["availability"] == "partial"
    assert result.summary["source_sample_count"] == 6
    assert result.summary["matched_sample_count"] == 2
    assert result.summary["unmatched_sample_count"] == 4
    assert result.summary["online_truth_injected"] is False


def test_sparse_governed_replay_keeps_only_exact_labels_and_reports_partial(
    tmp_path,
) -> None:
    bundle = _d1_governed_bundle()
    bundle["records"] = [
        record
        for record in bundle["records"]
        if record["measurement_timestamp"] != 0.5
    ]
    replay_path = tmp_path / "sparse_governed_replay.json"
    truth_path = tmp_path / "offline_truth.json"
    manifest_path = tmp_path / "manifest.json"
    replay_path.write_text(json.dumps(bundle), encoding="utf-8")
    truth_path.write_text(json.dumps(_d1_truth_sidecar()), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": P1_IDENTITY_INPUT_SCHEMA_VERSION,
                "evidence_source": "real_airsim_blocks_d1_governed_replay",
                "frozen_p95_loop_latency_budget_s": 0.02,
                "cases": [
                    {
                        "seed": 17,
                        "replay_name": "sparse-real-replay",
                        "replay_path": replay_path.name,
                        "truth_path": truth_path.name,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases, _ = load_identity_calibration_manifest(manifest_path)

    case = cases[0]
    assert len(case.frames) == 2
    assert len(case.offline_truth_labels) == 4
    assert case.offline_truth_alignment["availability"] == "partial"
    assert case.offline_truth_alignment["unmatched_sample_count"] == 2
    assert case.offline_truth_alignment["unmatched_samples"] == [
        {
            "sample_index": 2,
            "timestamp": 0.5,
            "source_payload_index": 1,
            "reason": "no_governed_replay_frame_within_frozen_tolerance",
        },
        {
            "sample_index": 3,
            "timestamp": 0.5,
            "source_payload_index": 1,
            "reason": "no_governed_replay_frame_within_frozen_tolerance",
        },
    ]
    online_text = json.dumps(case.frames, sort_keys=True)
    assert "TGT-001" not in online_text
    assert "truth_id" not in online_text

    report = run_airsim_replay_association(
        case.frames,
        replay_name=case.replay_name,
        offline_truth_labels=case.offline_truth_labels,
    )
    assert report.metrics["truth_metrics_available"] is True
    assert report.metrics["online_truth_isolation_violations"] == 0

    calibration = run_p1_identity_calibration(
        cases,
        frozen_p95_loop_latency_budget_s=0.02,
    ).to_dict()
    assert calibration["screening"]["available"] is False
    assert calibration["screening"][
        "offline_truth_alignment_availability_counts"
    ]["partial"] == 1
    assert calibration["screening"]["offline_truth_unmatched_sample_count"] == 2


def test_sparse_alignment_does_not_use_nearest_neighbor_outside_tolerance() -> None:
    frames = [
        {
            "frame_index": 0,
            "measurement_timestamp": 0.0,
            "detections": [],
            "replay_metadata": {"episode_id": "strict-tolerance"},
        }
    ]
    payload = {
        "schema_version": D1_AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION,
        "frame_id": "ned",
        "evaluator_only": True,
        "sample_count": 1,
        "target_count": 1,
        "samples": [
            {
                "truth_id": "TGT-001",
                "timestamp": 2.0 * D1_OFFLINE_TRUTH_TIMESTAMP_TOLERANCE_S,
                "position_ned": [10.0, 0.0, -5.0],
                "position_availability": "available",
                "source_payload_index": 0,
            }
        ],
    }

    result = align_d1_airsim_offline_truth(payload, replay_frames=frames)

    assert result.labels == ()
    assert result.summary["availability"] == "unavailable"
    assert result.summary["truth_metrics_input_available"] is False
    assert result.summary["unmatched_sample_count"] == 1


def test_sparse_alignment_still_rejects_ambiguous_same_timestamp() -> None:
    frames = [
        {
            "frame_index": index,
            "measurement_timestamp": 0.0,
            "detections": [],
            "replay_metadata": {"episode_id": "ambiguous"},
        }
        for index in (0, 1)
    ]
    payload = deepcopy(_d1_truth_sidecar())
    payload["samples"] = [deepcopy(payload["samples"][0])]
    payload["samples"][0].pop("source_payload_index")
    payload["sample_count"] = 1
    payload["target_count"] = 1

    with pytest.raises(ValueError, match="maps to multiple replay frames"):
        align_d1_airsim_offline_truth(payload, replay_frames=frames)
