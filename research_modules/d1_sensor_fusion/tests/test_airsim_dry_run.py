from __future__ import annotations

import csv
import json

import numpy as np
import pytest

from d1_sensor_fusion import (
    AIRSIM_DRY_RUN_FIXTURE_SCHEMA_VERSION,
    FusionAdapter,
    summarize_sensor_observation_latency_audit,
)
from d1_sensor_fusion.airsim_dry_run import (
    make_minimal_airsim_dry_run_fixture,
    observations_from_airsim_dry_run_fixture,
)
from d1_sensor_fusion.observations import CameraModel, eo_project, measurement_model_for
from d1_sensor_fusion.replay import (
    REPLAY_SCHEMA_VERSION,
    read_blocks_sensor_observations_jsonl,
    read_sensor_observations_jsonl,
    read_sensor_observations_csv,
    replay_blocks_sensor_observations_jsonl,
    replay_sensor_observations_csv,
)


def test_airsim_dry_run_fixture_converts_all_enabled_modalities() -> None:
    fixture = make_minimal_airsim_dry_run_fixture(include_lidar=True)
    observations = observations_from_airsim_dry_run_fixture(fixture)

    assert fixture["schema_version"] == AIRSIM_DRY_RUN_FIXTURE_SCHEMA_VERSION
    modalities = {obs.modality for obs in observations}
    assert modalities == {"radar", "acoustic", "eo", "lidar"}
    assert observations == sorted(observations, key=lambda obs: (obs.arrival_timestamp, obs.observation_id))
    for observation in observations:
        assert observation.arrival_timestamp >= observation.measurement_timestamp
        assert observation.covariance is not None
        assert observation.metadata["dry_run"] is True
        assert observation.metadata["fixture_id"] == "minimal_airsim_dry_run"
        assert observation.metadata["d1_fixture_schema_version"] == AIRSIM_DRY_RUN_FIXTURE_SCHEMA_VERSION
        if observation.modality == "eo":
            assert observation.frame_id == "pixel"
            assert observation.covariance.shape == (2, 2)
        elif observation.modality == "lidar":
            assert observation.frame_id == "ned"
            assert observation.measurement.shape == (3,)
            assert observation.covariance.shape == (3, 3)
        elif observation.modality == "acoustic":
            assert observation.frame_id == "ned"
            assert observation.covariance.shape == (1, 1)
        else:
            assert observation.frame_id == "ned"
            assert observation.covariance.shape == (4, 4)


def test_airsim_dry_run_lidar_is_optional() -> None:
    fixture = make_minimal_airsim_dry_run_fixture(include_lidar=False)
    observations = observations_from_airsim_dry_run_fixture(fixture)

    assert "lidar" not in {obs.modality for obs in observations}
    assert {"radar", "acoustic", "eo"} <= {obs.modality for obs in observations}


def test_airsim_dry_run_fixture_rejects_unsupported_schema_version() -> None:
    fixture = make_minimal_airsim_dry_run_fixture(include_lidar=False)
    fixture["schema_version"] = "d1.airsim_dry_run_fixture.v99"

    with pytest.raises(ValueError, match="unsupported D1 AirSim dry-run fixture schema_version"):
        observations_from_airsim_dry_run_fixture(fixture)


def test_airsim_dry_run_observations_feed_fusion_adapter() -> None:
    fixture = make_minimal_airsim_dry_run_fixture(include_lidar=True)
    observations = observations_from_airsim_dry_run_fixture(fixture)
    adapter = FusionAdapter(
        process_noise=8.0,
        association_gate=45.0,
        latency_compensation=True,
        use_truth_hints_for_association=True,
    )

    tracks = adapter.ingest_many(observations)

    assert len(tracks) == 1
    track = tracks[0]
    assert track.metadata["frame_id"] == "ned"
    assert track.covariance.shape == (6, 6)
    assert np.isfinite(track.covariance).all()
    assert track.source_support["radar"] >= 1
    assert track.source_support["lidar"] >= 1


def test_blocks_sensor_observations_jsonl_reader_replays_fusion_adapter(tmp_path) -> None:
    fixture = make_minimal_airsim_dry_run_fixture(include_lidar=True)
    observations = observations_from_airsim_dry_run_fixture(fixture)
    jsonl_path = tmp_path / "blocks_sensor_observations.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as stream:
        for observation in observations:
            payload = {
                "observation_id": observation.observation_id.replace("dry_", "blocks_", 1),
                "sensor_id": observation.sensor_id,
                "modality": observation.modality,
                "measurement_timestamp": observation.measurement_timestamp,
                "arrival_timestamp": observation.arrival_timestamp,
                "frame_id": observation.frame_id,
                "measurement": observation.measurement.tolist(),
                "covariance": observation.covariance.tolist(),
                "classification_hint": observation.classification_hint,
                "confidence": observation.confidence,
                "quality_flags": list(observation.quality_flags),
                "metadata": {
                    key: _jsonable(value)
                    for key, value in observation.metadata.items()
                    if key != "camera_model"
                },
                "communication": {
                    "source_node_id": "MAIN-C2",
                    "target_node_id": "D1-FUSION",
                    "link_type": "c2_replay",
                    "sent_timestamp": observation.measurement_timestamp,
                    "received_timestamp": observation.arrival_timestamp,
                    "payload_kind": f"{observation.modality}_observation",
                    "stale_after_s": 1.5,
                },
            }
            if observation.modality == "eo":
                camera = observation.metadata["camera_model"]
                payload["metadata"]["camera_model"] = {
                    "position_ned": camera.position_ned.tolist(),
                    "rotation_world_to_camera": camera.rotation_world_to_camera.tolist(),
                    "fx": camera.fx,
                    "fy": camera.fy,
                    "cx": camera.cx,
                    "cy": camera.cy,
                    "width": camera.width,
                    "height": camera.height,
                }
            stream.write(json.dumps(payload) + "\n")

    loaded = read_blocks_sensor_observations_jsonl(jsonl_path)
    tracks = replay_blocks_sensor_observations_jsonl(
        jsonl_path,
        FusionAdapter(
            process_noise=8.0,
            association_gate=45.0,
            latency_compensation=True,
            use_truth_hints_for_association=True,
        ),
    )

    assert len(loaded) == len(observations)
    assert loaded[0].metadata["d1_replay_schema_version"] == "legacy.blocks_sensor_observations"
    assert loaded[0].source_node_id == "MAIN-C2"
    assert loaded[0].payload_kind.endswith("_observation")
    assert len(tracks) == 1
    assert tracks[0].metadata["source_node_ids"] == ("MAIN-C2",)
    assert tracks[0].source_support["radar"] >= 1


def test_sensor_observations_csv_reader_replays_fusion_adapter(tmp_path) -> None:
    csv_path = tmp_path / "sensor_observations.csv"
    fieldnames = [
        "schema_version",
        "observation_id",
        "sensor_id",
        "modality",
        "measurement_timestamp",
        "arrival_timestamp",
        "frame_id",
        "measurement",
        "covariance",
        "confidence",
        "quality_flags",
        "metadata",
        "communication",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "schema_version": REPLAY_SCHEMA_VERSION,
                "observation_id": "csv_radar_birth",
                "sensor_id": "radar_csv",
                "modality": "radar",
                "measurement_timestamp": "0.0",
                "arrival_timestamp": "0.2",
                "frame_id": "ned",
                "measurement": json.dumps([120.0, 0.0, 0.0, 4.0]),
                "covariance": json.dumps(np.diag([4.0, 0.01, 0.01, 1.0]).tolist()),
                "confidence": "0.95",
                "quality_flags": "csv_replay",
                "metadata": json.dumps(
                    {"sensor_position_ned": [0.0, 0.0, 0.0], "coverage_cell": "cell-csv"}
                ),
                "communication": json.dumps(
                    {
                        "source_node_id": "D1-CSV-FIXTURE",
                        "target_node_id": "D1-FUSION",
                        "payload_kind": "radar_observation",
                        "stale_after_s": 1.0,
                    }
                ),
            }
        )

    loaded = read_sensor_observations_csv(csv_path)
    tracks = replay_sensor_observations_csv(csv_path, FusionAdapter())

    assert len(loaded) == 1
    assert loaded[0].metadata["d1_replay_schema_version"] == REPLAY_SCHEMA_VERSION
    assert loaded[0].covariance.shape == (4, 4)
    assert loaded[0].quality_flags == ("csv_replay",)
    assert loaded[0].source_node_id == "D1-CSV-FIXTURE"
    assert len(tracks) == 1
    assert tracks[0].metadata["coverage_cell"] == "cell-csv"


def test_sensor_observations_jsonl_rejects_unsupported_schema_version(tmp_path) -> None:
    jsonl_path = tmp_path / "sensor_observations.jsonl"
    payload = {
        "schema_version": "d1.sensor_observation.v99",
        "observation_id": "bad_schema_radar",
        "sensor_id": "radar_schema",
        "modality": "radar",
        "measurement_timestamp": 0.0,
        "arrival_timestamp": 0.1,
        "frame_id": "ned",
        "measurement": [120.0, 0.0, 0.0, 4.0],
        "covariance": np.diag([4.0, 0.01, 0.01, 1.0]).tolist(),
    }
    jsonl_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="failed to parse .* as D1 observation") as exc_info:
        read_sensor_observations_jsonl(jsonl_path)
    assert "unsupported D1 replay schema_version" in str(exc_info.value.__cause__)


def test_real_blocks_cv_jsonl_preserves_eo_camera_bbox_and_recon_metadata(tmp_path) -> None:
    jsonl_path = tmp_path / "sensor_observations.jsonl"
    camera_metadata = {
        "camera_id": "secondary_recon_01:front_center",
        "camera_name": "front_center",
        "intrinsics": {
            "K": [[700.0, 0.0, 640.0], [0.0, 710.0, 360.0], [0.0, 0.0, 1.0]],
            "image_size": [1280, 720],
        },
        "extrinsics": {
            "position_ned": [12.0, -5.0, -80.0],
            "rotation_world_to_camera": [
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [1.0, 0.0, 0.0],
            ],
        },
    }
    payload = {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "observation_id": "blocks_cv_seed007_secondary_eo_0001",
        "sensor_id": "secondary_recon_01:front_center",
        "modality": "eo",
        "measurement_timestamp": 12.25,
        "arrival_timestamp": 12.31,
        "frame_id": "pixel",
        "measurement": [640.0, 360.0],
        "covariance": [[9.0, 0.0], [0.0, 9.0]],
        "confidence": 0.86,
        "quality_flags": ["cv_fixture", "secondary_recon"],
        "metadata": {"truth_id": "actor_red_01"},
        "coverage_cell": "cell-north",
        "camera_metadata": camera_metadata,
        "bbox_xyxy": [620.0, 340.0, 660.0, 380.0],
        "detection_metadata": {
            "detector": "simGetDetections",
            "mesh_name": "BP_FlyingPawn",
            "actor_name": "actor_red_01",
        },
        "secondary_recon": {
            "node_id": "secondary_recon_01",
            "mode": "mobile_high_altitude",
            "cue_source": "d1_recon_cue",
        },
        "mobile_recon": {
            "node_id": "mobile_recon_02",
            "platform": "uav",
            "mode": "wide_area_search",
        },
        "recon_cue_summary": {
            "cue_source": "d1_region_quality",
            "active_target_ids": ["global_track_001"],
            "coverage_cell": "cell-north",
        },
        "cue_position_ned": [112.0, -5.0, -80.0],
        "cue_covariance": [[16.0, 0.0, 0.0], [0.0, 16.0, 0.0], [0.0, 0.0, 25.0]],
        "covariance_scale_reason": "cv_bbox_distance_scale",
        "source_support": {"eo": 1},
        "communication": {
            "source_node_id": "secondary_recon_01",
            "target_node_id": "D1-FUSION",
            "link_type": "video_cue",
            "sent_timestamp": 12.26,
            "received_timestamp": 12.31,
            "payload_kind": "bbox",
            "stale_after_s": 0.4,
        },
    }
    jsonl_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    observation = read_sensor_observations_jsonl(jsonl_path)[0]
    metadata = observation.metadata

    assert observation.measurement_timestamp == 12.25
    assert observation.arrival_timestamp == 12.31
    assert observation.covariance.shape == (2, 2)
    assert observation.source_support == {"eo": 1}
    assert metadata["coverage_cell"] == "cell-north"
    assert metadata["bbox"] == [620.0, 340.0, 660.0, 380.0]
    assert metadata["bbox_xyxy"] == [620.0, 340.0, 660.0, 380.0]
    assert metadata["center_px"] == [640.0, 360.0]
    assert metadata["bbox_center_px"] == [640.0, 360.0]
    assert metadata["camera_model"]["camera_id"] == "secondary_recon_01:front_center"
    assert metadata["detection_metadata"]["detector"] == "simGetDetections"
    assert metadata["secondary_recon"]["mode"] == "mobile_high_altitude"
    assert metadata["mobile_recon"]["node_id"] == "mobile_recon_02"
    assert metadata["recon_cue_summary"]["cue_source"] == "d1_region_quality"
    assert metadata["cue_position_ned"] == [112.0, -5.0, -80.0]
    assert metadata["cue_covariance"][2][2] == 25.0
    assert metadata["covariance_scale_reason"] == "cv_bbox_distance_scale"
    assert observation.payload_kind == "bbox"
    assert np.isclose(observation.communication_latency, 0.05)

    expected_camera = CameraModel(
        position_ned=np.array([12.0, -5.0, -80.0]),
        rotation_world_to_camera=np.array(
            [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]],
            dtype=float,
        ),
        fx=700.0,
        fy=710.0,
        cx=640.0,
        cy=360.0,
        width=1280,
        height=720,
    )
    state = np.array([112.0, -5.0, -80.0, 0.0, 0.0, 0.0])
    model = measurement_model_for(observation)
    assert np.allclose(model.h_fn(state), eo_project(state, expected_camera))


def test_blocks_calibration_csv_replay_preserves_audit_and_quality_fields(tmp_path) -> None:
    csv_path = tmp_path / "blocks_calibration_sensor_observations.csv"
    fieldnames = [
        "observation_id",
        "sensor_id",
        "modality",
        "measurement_timestamp",
        "arrival_timestamp",
        "frame_id",
        "measurement",
        "covariance",
        "confidence",
        "quality_flags",
        "metadata",
        "communication",
        "source_support",
        "covariance_scale_reason",
        "mobile_recon",
        "recon_cue_summary",
        "cue_position_ned",
        "cue_covariance",
    ]
    rows = [
        {
            "observation_id": "blocks_seed007_radar_000",
            "sensor_id": "BLOCKS-RADAR-01",
            "modality": "radar",
            "measurement_timestamp": "0.0",
            "arrival_timestamp": "0.2",
            "frame_id": "ned",
            "measurement": json.dumps([120.0, 0.0, 0.0, 4.0]),
            "covariance": json.dumps(np.diag([4.0, 0.01, 0.01, 1.0]).tolist()),
            "confidence": "0.95",
            "quality_flags": "blocks_csv",
            "metadata": json.dumps(
                {
                    "sensor_position_ned": [0.0, 0.0, 0.0],
                    "coverage_cell": "cell-north",
                    "truth_id": "actor_red_01",
                    "airsim_frame_index": 0,
                }
            ),
            "communication": json.dumps(
                {
                    "source_node_id": "BLOCKS-CAL-SEED-007",
                    "target_node_id": "D1-FUSION",
                    "link_type": "c2_replay",
                    "sent_timestamp": 0.0,
                    "received_timestamp": 0.2,
                    "payload_kind": "radar_observation",
                    "stale_after_s": 0.6,
                }
            ),
            "source_support": json.dumps({"radar": 1}),
        },
        {
            "observation_id": "blocks_seed007_radar_001",
            "sensor_id": "BLOCKS-RADAR-01",
            "modality": "radar",
            "measurement_timestamp": "1.0",
            "arrival_timestamp": "1.2",
            "frame_id": "ned",
            "measurement": json.dumps([124.0, 0.0, 0.0, 4.0]),
            "covariance": json.dumps(np.diag([4.2, 0.01, 0.01, 1.0]).tolist()),
            "confidence": "0.95",
            "quality_flags": "blocks_csv",
            "metadata": json.dumps(
                {
                    "sensor_position_ned": [0.0, 0.0, 0.0],
                    "coverage_cell": "cell-north",
                    "truth_id": "actor_red_01",
                    "airsim_frame_index": 1,
                }
            ),
            "communication": json.dumps(
                {
                    "source_node_id": "BLOCKS-CAL-SEED-007",
                    "target_node_id": "D1-FUSION",
                    "link_type": "c2_replay",
                    "sent_timestamp": 1.0,
                    "received_timestamp": 1.2,
                    "payload_kind": "radar_observation",
                    "stale_after_s": 0.6,
                }
            ),
            "source_support": json.dumps({"radar": 1}),
        },
        {
            "observation_id": "blocks_seed007_acoustic_delayed",
            "sensor_id": "BLOCKS-ACOUSTIC-01",
            "modality": "acoustic",
            "measurement_timestamp": "0.5",
            "arrival_timestamp": "1.4",
            "frame_id": "ned",
            "measurement": json.dumps([0.0]),
            "covariance": json.dumps([[0.02]]),
            "confidence": "0.82",
            "quality_flags": "late_replay",
            "metadata": json.dumps(
                {
                    "sensor_position_ned": [0.0, 0.0, 0.0],
                    "coverage_cell": "cell-north",
                    "truth_id": "actor_red_01",
                    "airsim_frame_index": 1,
                }
            ),
            "communication": json.dumps(
                {
                    "source_node_id": "BLOCKS-CAL-SEED-007",
                    "target_node_id": "D1-FUSION",
                    "link_type": "c2_replay",
                    "sent_timestamp": 0.5,
                    "received_timestamp": 1.4,
                    "payload_kind": "acoustic_observation",
                    "stale_after_s": 0.4,
                }
            ),
            "source_support": json.dumps({"acoustic": 1}),
            "covariance_scale_reason": "late_calibration_covariance_scale",
            "mobile_recon": json.dumps(
                {
                    "node_id": "mobile_recon_02",
                    "platform": "uav",
                    "mode": "wide_area_search",
                }
            ),
            "recon_cue_summary": json.dumps(
                {
                    "cue_source": "d1_recon_cue",
                    "active_target_ids": ["global_track_001"],
                    "coverage_cell": "cell-north",
                }
            ),
            "cue_position_ned": json.dumps([124.0, 0.0, 0.0]),
            "cue_covariance": json.dumps(
                [[25.0, 0.0, 0.0], [0.0, 25.0, 0.0], [0.0, 0.0, 36.0]]
            ),
        },
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    loaded = read_sensor_observations_csv(csv_path)
    adapter = FusionAdapter(
        association_gate=45.0,
        latency_compensation=True,
        use_truth_hints_for_association=True,
    )
    tracks = adapter.ingest_many(loaded)

    assert len(loaded) == 3
    raw_audit = summarize_sensor_observation_latency_audit(loaded).to_dict()
    assert raw_audit["observation_count"] == 3
    assert raw_audit["oosm_observation_count"] == 1
    assert raw_audit["stale_observation_count"] == 1
    assert raw_audit["stale_or_oosm_observation_count"] == 1
    assert raw_audit["max_delay_s"] == pytest.approx(0.9)
    assert raw_audit["mean_delay_s"] == pytest.approx((0.2 + 0.2 + 0.9) / 3.0)
    assert raw_audit["latency_compensation"] is False

    delayed_observation = next(obs for obs in loaded if obs.observation_id.endswith("delayed"))
    assert delayed_observation.metadata["covariance_scale_reason"] == "late_calibration_covariance_scale"
    assert delayed_observation.metadata["mobile_recon"]["mode"] == "wide_area_search"
    assert delayed_observation.metadata["recon_cue_summary"]["cue_source"] == "d1_recon_cue"
    assert delayed_observation.metadata["cue_position_ned"] == [124.0, 0.0, 0.0]
    assert delayed_observation.metadata["cue_covariance"][2][2] == 36.0

    for observation in loaded:
        assert observation.metadata["d1_replay_schema_version"] == REPLAY_SCHEMA_VERSION
        assert observation.arrival_timestamp >= observation.measurement_timestamp
        assert observation.covariance is not None
        assert np.isfinite(observation.covariance).all()
        assert observation.metadata["coverage_cell"] == "cell-north"
        assert observation.source_support == {observation.modality: 1}

    assert len(tracks) == 1
    track = tracks[0]
    assert track.metadata["frame_id"] == "ned"
    assert track.position.shape == (3,)
    assert track.velocity.shape == (3,)
    assert track.covariance.shape == (6, 6)
    assert np.isfinite(track.state).all()
    assert np.isfinite(track.covariance).all()
    assert track.source_support["radar"] == 2
    assert track.source_support["acoustic"] == 1
    assert track.metadata["latest_measurement_timestamp"] == 0.5
    assert track.metadata["latest_arrival_timestamp"] == 1.4
    assert track.metadata["covariance_scale_reason"] == "late_calibration_covariance_scale"
    assert track.metadata["mobile_recon"]["node_id"] == "mobile_recon_02"
    assert track.metadata["recon_cue_summary"]["active_target_ids"] == ["global_track_001"]
    assert track.metadata["cue_position_ned"] == [124.0, 0.0, 0.0]

    audit = adapter.latency_audit_summary().to_dict()
    assert audit["observation_count"] == 3
    assert audit["oosm_observation_count"] == 1
    assert audit["stale_observation_count"] == 1
    assert audit["stale_or_oosm_observation_count"] == 1
    assert np.isclose(audit["max_delay_s"], 0.9)
    assert audit["replay_count"] >= 2

    summary = adapter.track_uncertainty_summaries()[0].to_dict()
    assert summary["coverage_cell"] == "cell-north"
    assert summary["measurement_timestamp"] == 0.5
    assert summary["arrival_timestamp"] == 1.4
    assert summary["source_support"] == {"radar": 2, "acoustic": 1}
    assert np.isclose(summary["measurement_age_s"], 0.9)

    regions = adapter.region_quality_summaries(
        required_modalities=("radar", "acoustic", "eo"),
        stale_age_s=0.25,
    )
    assert len(regions) == 1
    region = regions[0].to_dict()
    assert region["coverage_cell"] == "cell-north"
    assert region["track_count"] == 1
    assert region["source_support"] == {"radar": 2, "acoustic": 1}
    assert region["source_gap_modalities"] == ("eo",)
    assert region["stale_track_count"] == 1
    assert np.isclose(region["max_measurement_age_s"], 0.9)


def test_blocks_n_actor_jsonl_contract_exports_observations_and_global_tracks(tmp_path) -> None:
    fixture = make_minimal_airsim_dry_run_fixture(include_lidar=False)
    fixture["fixture_id"] = "blocks_n_actor_contract"
    target_count = 4
    frame_times = (0.0, 0.4)
    initial_states = [
        np.array(
            [
                120.0 + 35.0 * target_index,
                ((-1.0) ** target_index) * (18.0 + 7.0 * target_index),
                -20.0 - target_index,
                4.0 + 0.5 * target_index,
                ((-1.0) ** target_index) * 0.4,
                0.0,
            ],
            dtype=float,
        )
        for target_index in range(target_count)
    ]
    fixture["frames"] = [
        {
            "timestamp": timestamp,
            "targets": [
                {
                    "target_id": f"actor_red_{target_index + 1:02d}",
                    "state_ned": _propagated_state(state, timestamp).tolist(),
                }
                for target_index, state in enumerate(initial_states)
            ],
        }
        for timestamp in frame_times
    ]
    expected_truth_ids = {
        target["target_id"]
        for frame in fixture["frames"]
        for target in frame["targets"]
    }
    observations = observations_from_airsim_dry_run_fixture(fixture)
    jsonl_path = tmp_path / "blocks_n_actor_sensor_observations.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as stream:
        for sequence_id, observation in enumerate(observations):
            payload = {
                "observation_id": observation.observation_id.replace("dry_", "blocks_n_", 1),
                "sensor_id": observation.sensor_id,
                "modality": observation.modality,
                "measurement_timestamp": observation.measurement_timestamp,
                "arrival_timestamp": observation.arrival_timestamp,
                "frame_id": observation.frame_id,
                "measurement": observation.measurement.tolist(),
                "covariance": observation.covariance.tolist(),
                "classification_hint": observation.classification_hint,
                "confidence": observation.confidence,
                "quality_flags": list(observation.quality_flags),
                "metadata": {
                    key: _jsonable(value)
                    for key, value in observation.metadata.items()
                    if key != "camera_model"
                },
                "communication": {
                    "source_node_id": "BLOCKS-N-RUNTIME",
                    "target_node_id": "D1-FUSION",
                    "link_type": "truth_detection_replay",
                    "sent_timestamp": observation.measurement_timestamp,
                    "received_timestamp": observation.arrival_timestamp,
                    "payload_kind": f"{observation.modality}_observation",
                    "stale_after_s": 1.0,
                    "source_support": {observation.modality: 1},
                },
            }
            payload["metadata"]["sequence_id"] = sequence_id
            if observation.modality == "eo":
                camera = observation.metadata["camera_model"]
                payload["metadata"]["camera_model"] = {
                    "position_ned": camera.position_ned.tolist(),
                    "rotation_world_to_camera": camera.rotation_world_to_camera.tolist(),
                    "fx": camera.fx,
                    "fy": camera.fy,
                    "cx": camera.cx,
                    "cy": camera.cy,
                    "width": camera.width,
                    "height": camera.height,
                }
            stream.write(json.dumps(payload) + "\n")

    loaded = read_blocks_sensor_observations_jsonl(jsonl_path)
    tracks = replay_blocks_sensor_observations_jsonl(
        jsonl_path,
        FusionAdapter(
            process_noise=8.0,
            association_gate=45.0,
            latency_compensation=True,
            use_truth_hints_for_association=True,
        ),
    )

    assert {obs.metadata["truth_id"] for obs in loaded} == expected_truth_ids
    assert {"radar", "acoustic", "eo"} <= {obs.modality for obs in loaded}
    for observation in loaded:
        assert isinstance(observation.measurement_timestamp, float)
        assert isinstance(observation.arrival_timestamp, float)
        assert observation.arrival_timestamp >= observation.measurement_timestamp
        assert observation.covariance is not None
        assert np.isfinite(observation.covariance).all()

    assert len(tracks) == len(expected_truth_ids)
    assert {track.metadata["truth_id"] for track in tracks} == expected_truth_ids
    for track in tracks:
        assert track.position.shape == (3,)
        assert track.velocity.shape == (3,)
        assert track.covariance.shape == (6, 6)
        assert np.isfinite(track.position).all()
        assert np.isfinite(track.velocity).all()
        assert np.isfinite(track.covariance).all()
        assert track.metadata["latest_measurement_timestamp"] is not None
        assert track.metadata["latest_arrival_timestamp"] is not None
        assert track.metadata["source_node_ids"] == ("BLOCKS-N-RUNTIME",)


def _jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _propagated_state(state: np.ndarray, timestamp: float) -> np.ndarray:
    propagated = state.copy()
    propagated[:3] += propagated[3:] * timestamp
    return propagated
