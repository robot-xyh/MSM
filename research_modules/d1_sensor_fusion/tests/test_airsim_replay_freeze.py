from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from d1_sensor_fusion import (
    AIRSIM_FREEZE_SUMMARY_SCHEMA_VERSION,
    AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION,
    ReplayProvenance,
    freeze_airsim_replay_payloads,
    load_airsim_replay_payloads,
    read_sensor_observations_jsonl,
    write_frozen_airsim_replay,
)


MODULE_ROOT = Path(__file__).resolve().parents[1]
RUNNER = MODULE_ROOT / "scripts" / "freeze_airsim_replay.py"


def test_freeze_five_target_frames_isolates_truth_and_preserves_governance(tmp_path: Path) -> None:
    payloads = _five_target_payloads()
    result = freeze_airsim_replay_payloads(payloads, _provenance())

    assert result.manifest["observation_count"] == 7
    assert result.manifest["working_frame"] == "ned"
    assert result.manifest["capture_provenance"]["target_spacing_m"] == 4.0
    assert result.manifest["capture_provenance"]["seed"] == 17
    assert result.manifest["provenance"]["metadata"]["target_spacing_source"] == (
        "capture_provenance"
    )
    assert result.manifest["field_availability"]["target_spacing_m"] == {
        "status": "available",
        "count": 1,
        "source": "captured_payload_provenance",
    }
    assert result.summary["offline_truth_target_count"] == 5
    assert result.summary["online_truth_leak_count"] == 0
    assert result.summary["missing_measurements_fabricated"] == 0
    assert result.summary["event_counts"] == {
        "crossing": 1,
        "false_alarm": 1,
        "missed_detection": 1,
        "node_exit": 1,
        "occlusion": 1,
        "oosm": 1,
    }
    assert result.summary["sensor_health"]["RADAR-01"]["state"] == "healthy"
    assert result.summary["source_schema_versions"] == ["main.airsim.frame.v2"]
    assert result.summary["scene_ids"] == ["dense-crossing"]
    assert result.summary["profile_ids"] == ["p1-dense-v1"]

    online_text = json.dumps(result.records, sort_keys=True)
    for forbidden in ("TGT-001", "TGT-002", "TargetActor", "local:TGT"):
        assert forbidden not in online_text
    assert {record["observation_id"] for record in result.records} == {
        f"airsim-obs-{index:08d}" for index in range(1, 8)
    }
    assert all(record["working_frame"] == "ned" for record in result.records)
    assert all(record["covariance"] for record in result.records)
    assert all(record["source_lineage"] for record in result.records)
    assert all(
        record["provenance"]["metadata"]["capture_provenance_digest"]
        == result.manifest["capture_provenance"]["capture_provenance_digest"]
        for record in result.records
    )
    assert result.records[0]["metadata"]["processing_timestamp"] == 0.25
    assert result.records[0]["metadata"]["publish_timestamp"] == 0.3
    assert result.records[-1]["metadata"]["timestamp_availability"] == {
        "measurement": "available",
        "arrival": "available",
        "processing": "unavailable",
        "publish": "unavailable",
    }

    assert result.offline_truth["schema_version"] == AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION
    assert result.offline_truth["evaluator_only"] is True
    assert result.offline_truth["capture_provenance_digest"] == (
        result.manifest["capture_provenance"]["capture_provenance_digest"]
    )
    assert result.offline_truth["target_count"] == 5
    assert result.offline_truth["sample_count"] == 6
    assert result.offline_truth["position_availability_counts"] == {
        "available": 5,
        "unavailable": 1,
    }
    assert result.summary["offline_truth_unavailable_position_sample_count"] == 1
    positioned = [
        sample
        for sample in result.offline_truth["samples"]
        if sample["position_availability"] == "available"
    ]
    assert len(positioned) == 5
    assert {sample["truth_id"] for sample in positioned} == {
        f"TGT-{index:03d}" for index in range(1, 6)
    }

    paths = write_frozen_airsim_replay(tmp_path / "frozen", result)
    observations = read_sensor_observations_jsonl(paths["records"])
    assert len(observations) == 7
    assert all(observation.covariance is not None for observation in observations)
    assert all("truth_id" not in observation.metadata for observation in observations)


@pytest.mark.parametrize("available_first", [False, True])
def test_truth_sidecar_available_position_overrides_unavailable_for_same_key(
    available_first: bool,
) -> None:
    available = {
        "timestamp": 2.0,
        "truth_objects": [
            {"object_id": "TGT-001", "timestamp": 2.0, "position_ned": [10.0, 20.0, -5.0]}
        ],
    }
    unavailable = {
        "timestamp": 2.0,
        "sensor_observations": [
            _radar_observation(1, 2.0, truth_id="TGT-001")
        ],
    }
    payloads = _with_capture(
        [available, unavailable] if available_first else [unavailable, available]
    )

    result = freeze_airsim_replay_payloads(payloads, _provenance())

    samples = result.offline_truth["samples"]
    assert len(samples) == 1
    assert samples[0]["truth_id"] == "TGT-001"
    assert samples[0]["timestamp"] == 2.0
    assert samples[0]["position_ned"] == [10.0, 20.0, -5.0]
    assert samples[0]["position_availability"] == "available"
    assert result.summary["offline_truth_unavailable_position_sample_count"] == 0


def test_truth_sidecar_rejects_conflicting_available_positions_for_same_key() -> None:
    payloads = _with_capture([
        {
            "timestamp": 3.0,
            "truth_objects": [
                {"object_id": "TGT-001", "position_ned": [1.0, 2.0, -3.0]}
            ],
        },
        {
            "timestamp": 3.0,
            "truth_objects": [
                {"object_id": "TGT-001", "position_ned": [1.0, 2.5, -3.0]}
            ],
        },
    ])

    with pytest.raises(ValueError, match="conflicting available D1 offline truth positions"):
        freeze_airsim_replay_payloads(payloads, _provenance())


def test_truth_sidecar_preserves_same_identity_at_different_timestamps() -> None:
    payloads = _with_capture([
        {
            "timestamp": timestamp,
            "truth_objects": [
                {
                    "object_id": "TGT-001",
                    "position_ned": [10.0 + timestamp, 20.0, -5.0],
                }
            ],
        }
        for timestamp in (1.0, 2.0)
    ])

    result = freeze_airsim_replay_payloads(payloads, _provenance())

    assert [(sample["timestamp"], sample["position_ned"]) for sample in result.offline_truth["samples"]] == [
        (1.0, [11.0, 20.0, -5.0]),
        (2.0, [12.0, 20.0, -5.0]),
    ]
    assert result.offline_truth["position_availability_counts"] == {"available": 2}


def test_missing_observation_data_is_rejected_not_fabricated() -> None:
    payloads = _with_capture([
        {
            "schema_version": "main.airsim.frame.v2",
            "scenario_name": "occlusion-only",
            "profile_id": "dropout",
            "frame_index": 0,
            "timestamp": 1.0,
            "event_labels": ["occlusion", "missed_detection", "node_exit"],
            "sensor_observations": [],
        },
        {
            "schema_version": "main.airsim.frame.v2",
            "scenario_name": "occlusion-only",
            "profile_id": "dropout",
            "sensor_observations": [
                {
                    "sensor_id": "EO-01",
                    "modality": "eo",
                    "measurement_timestamp": 1.0,
                    "arrival_timestamp": 1.1,
                    "frame_id": "pixel",
                    "covariance": [[4.0, 0.0], [0.0, 4.0]],
                    "metadata": {"coverage_cell": "cell-a"},
                }
            ],
        },
    ])

    result = freeze_airsim_replay_payloads(payloads, _provenance())

    assert result.records == []
    assert result.summary["observation_candidate_count"] == 1
    assert result.summary["accepted_observation_count"] == 0
    assert result.summary["rejected_observation_count"] == 1
    assert "measurement" in result.summary["rejected_observations"][0]["reason"]
    assert result.summary["missing_measurements_fabricated"] == 0
    assert result.summary["event_counts"] == {
        "missed_detection": 1,
        "node_exit": 1,
        "occlusion": 1,
    }


def test_json_and_jsonl_loaders_accept_direct_and_nested_observations(tmp_path: Path) -> None:
    direct = _radar_observation(0, 0.0, truth_id="TGT-001")
    json_path = tmp_path / "payload.json"
    json_path.write_text(json.dumps({"payloads": [direct]}), encoding="utf-8")
    jsonl_path = tmp_path / "payload.jsonl"
    jsonl_path.write_text(
        json.dumps({"sensor_observations": [direct], "scenario_name": "dense-crossing"})
        + "\n",
        encoding="utf-8",
    )

    assert len(load_airsim_replay_payloads(json_path)) == 1
    assert len(load_airsim_replay_payloads(jsonl_path)) == 1
    assert freeze_airsim_replay_payloads(
        load_airsim_replay_payloads(json_path), _provenance()
    ).summary["accepted_observation_count"] == 1
    assert freeze_airsim_replay_payloads(
        load_airsim_replay_payloads(jsonl_path), _provenance()
    ).summary["accepted_observation_count"] == 1


def test_freeze_cli_writes_manifest_records_truth_and_summary(tmp_path: Path) -> None:
    input_path = tmp_path / "input.jsonl"
    input_path.write_text(
        "\n".join(json.dumps(payload) for payload in _five_target_payloads()) + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            str(input_path),
            str(output_dir),
            "--scenario-id",
            "dense-crossing",
            "--scenario-version",
            "2",
            "--config-id",
            "blocks-settings-v4",
            "--config-version",
            "4",
            "--seed",
            "17",
            "--target-spacing-m",
            "4.0",
            "--profile-id",
            "p1-dense-v1",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "7 records" in result.stdout
    for filename in ("manifest.json", "sensor_observations.jsonl", "offline_truth.json", "summary.json"):
        assert (output_dir / filename).exists()
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["schema_version"] == AIRSIM_FREEZE_SUMMARY_SCHEMA_VERSION
    assert summary["accepted_observation_count"] == 7
    assert summary["online_truth_leak_count"] == 0
    assert summary["target_spacing_m"] == 4.0
    assert summary["evidence_path"] == "capture/dense-crossing/seed-000017"


@pytest.mark.parametrize("spacing_m", [4.0, 2.0])
def test_dense_crossing_twenty_seed_capture_contract(spacing_m: float) -> None:
    for seed in range(20):
        payload = _radar_observation(seed, 0.0, truth_id=f"TGT-{seed % 5 + 1:03d}")
        payload["capture_provenance"] = _capture_provenance(
            seed=seed,
            spacing_m=spacing_m,
        )

        result = freeze_airsim_replay_payloads(
            [payload],
            _provenance(seed=seed, spacing_m=spacing_m),
        )

        assert result.manifest["provenance"]["seed"] == seed
        assert result.manifest["capture_provenance"]["target_spacing_m"] == spacing_m
        assert result.summary["field_availability"]["evidence_path"]["status"] == (
            "available"
        )


def test_missing_capture_provenance_fails_closed_without_truth_geometry_inference() -> None:
    payload = _radar_observation(0, 0.0, truth_id="TGT-001")
    payload.pop("capture_provenance")

    with pytest.raises(ValueError, match="requires explicit capture_provenance"):
        freeze_airsim_replay_payloads([payload], _provenance())


def test_capture_spacing_mismatch_with_replay_declaration_fails_closed() -> None:
    payload = _radar_observation(0, 0.0, truth_id="TGT-001")
    payload["capture_provenance"] = _capture_provenance(spacing_m=2.0)

    with pytest.raises(ValueError, match="target_spacing_m conflicts"):
        freeze_airsim_replay_payloads([payload], _provenance(spacing_m=4.0))


def test_conflicting_capture_provenance_across_payloads_fails_closed() -> None:
    first = _radar_observation(0, 0.0, truth_id="TGT-001")
    second = _radar_observation(1, 0.1, truth_id="TGT-002")
    second["capture_provenance"] = _capture_provenance(spacing_m=2.0)

    with pytest.raises(ValueError, match="conflicting D1 AirSim capture provenance"):
        freeze_airsim_replay_payloads([first, second], _provenance())


def _five_target_payloads() -> list[dict[str, object]]:
    frame0 = {
        "schema_version": "main.airsim.frame.v2",
        "scenario_name": "dense-crossing",
        "profile_id": "p1-dense-v1",
        "frame_index": 0,
        "timestamp": 0.0,
        "clock": {"processing_timestamp": 0.25, "publish_timestamp": 0.3},
        "event_labels": ["crossing"],
        "sensor_health": {"RADAR-01": {"state": "healthy", "fault_reason": None}},
        "truth_objects": [
            {
                "object_id": f"TGT-{index + 1:03d}",
                "position_ned": [50.0, -40.0 + 20.0 * index, -10.0],
                "timestamp": 0.0,
            }
            for index in range(5)
        ],
        "sensor_observations": [
            _radar_observation(index, 0.0, truth_id=f"TGT-{index + 1:03d}")
            for index in range(5)
        ],
    }
    frame1 = {
        "schema_version": "main.airsim.frame.v2",
        "scenario_name": "dense-crossing",
        "profile_id": "p1-dense-v1",
        "frame_index": 1,
        "timestamp": 0.5,
        "event_labels": ["occlusion", "missed_detection"],
        "sensor_observations": [],
    }
    frame2 = {
        "schema_version": "main.airsim.frame.v2",
        "scenario_name": "dense-crossing",
        "profile_id": "p1-dense-v1",
        "frame_index": 2,
        "timestamp": 1.0,
        "events": [{"event_type": "node_exit"}],
        "sensor_observations": [
            _radar_observation(20, 0.4, truth_id="TGT-002", arrival=1.2, labels=["oosm"]),
            _radar_observation(21, 1.0, truth_id=None, arrival=1.25, labels=["false_alarm"]),
        ],
    }
    return [frame0, frame1, frame2]


def _radar_observation(
    index: int,
    timestamp: float,
    *,
    truth_id: str | None,
    arrival: float | None = None,
    labels: list[str] | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "coverage_cell": "cell-dense",
        "sequence_id": f"local:{truth_id}:{index}",
        "sensor_position_ned": [0.0, 0.0, 0.0],
    }
    if truth_id is not None:
        metadata.update(
            {
                "truth_id": truth_id,
                "actor_name": f"TargetActor-{truth_id}",
                "local_track_id": f"local:{truth_id}",
            }
        )
    return {
        "capture_provenance": _capture_provenance(),
        "observation_id": f"blocks-radar-{truth_id or 'clutter'}-{index}",
        "sensor_id": "RADAR-01",
        "modality": "radar",
        "measurement_timestamp": timestamp,
        "arrival_timestamp": timestamp + 0.2 if arrival is None else arrival,
        "frame_id": "ned",
        "measurement": [50.0 + index, 0.01 * index, 0.0, 1.0],
        "covariance": [
            [4.0, 0.0, 0.0, 0.0],
            [0.0, 0.01, 0.0, 0.0],
            [0.0, 0.0, 0.01, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        "classification_hint": f"voiceprint_{truth_id}" if truth_id else "unknown",
        "quality_flags": labels or [],
        "metadata": metadata,
        "communication": {
            "source_node_id": "MAIN-C2",
            "target_node_id": "D1-FUSION",
            "payload_kind": "radar_observation",
        },
    }


def _capture_provenance(
    *,
    seed: int = 17,
    spacing_m: float = 4.0,
) -> dict[str, object]:
    return {
        "schema_version": "main.airsim.capture_provenance.v1",
        "scenario_id": "dense-crossing",
        "scenario_version": "2",
        "scenario_config_version": "4",
        "seed": seed,
        "target_spacing_m": spacing_m,
        "evidence_path": f"capture/dense-crossing/seed-{seed:06d}",
    }


def _with_capture(
    payloads: list[dict[str, object]],
    *,
    seed: int = 17,
    spacing_m: float = 4.0,
) -> list[dict[str, object]]:
    result = [dict(payload) for payload in payloads]
    result[0]["capture_provenance"] = _capture_provenance(
        seed=seed,
        spacing_m=spacing_m,
    )
    return result


def _provenance(
    *,
    seed: int = 17,
    spacing_m: float = 4.0,
) -> ReplayProvenance:
    return ReplayProvenance(
        scenario_id="dense-crossing",
        scenario_version="2",
        config_id="blocks-settings-v4",
        config_digest="sha256:dense-config",
        config_version="4",
        scenario_digest="sha256:dense-scenario",
        run_id=f"seed-{seed:06d}",
        seed=seed,
        source_format="main_airsim_jsonl",
        producer="d1-test",
        metadata={
            "target_spacing_m": spacing_m,
            "evidence_path": f"capture/dense-crossing/seed-{seed:06d}",
            "scenario_config_version": "4",
        },
    )
