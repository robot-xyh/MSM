from __future__ import annotations

import json

from airsim_runtime.p1_identity_pipeline import (
    IdentityEpisodeEvidence,
    build_identity_calibration_manifest,
    freeze_identity_episode,
)
from d2_data_association import load_identity_calibration_manifest


def test_identity_pipeline_freezes_online_data_and_truth_sidecar(tmp_path) -> None:
    episode = tmp_path / "episode_006_full_flow"
    episode.mkdir()
    frame = {
        "schema_version": "main.airsim.frame.v2",
        "scenario_name": "dense-crossing",
        "frame_index": 0,
        "timestamp": 0.0,
        "truth_objects": [
            {"object_id": "TGT-001", "position_ned": [35.0, 0.0, -10.0], "timestamp": 0.0}
        ],
        "metadata": {"profile_id": "p1-dense-v1"},
    }
    observation = {
        "observation_id": "radar-TGT-001",
        "sensor_id": "RADAR-01",
        "modality": "radar",
        "measurement": [35.0, 0.0, 0.0, 1.0],
        "measurement_timestamp": 0.0,
        "arrival_timestamp": 0.1,
        "frame_id": "ned",
        "covariance": [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        "metadata": {
            "truth_id": "TGT-001",
            "event_labels": ["crossing"],
            "coverage_cell": "cell-dense",
            "sensor_position_ned": [0.0, 0.0, 0.0],
        },
    }
    (episode / "blocks_frames.jsonl").write_text(json.dumps(frame) + "\n", encoding="utf-8")
    (episode / "blocks_sensor_observations.jsonl").write_text(
        json.dumps(observation) + "\n", encoding="utf-8"
    )
    evidence = IdentityEpisodeEvidence(
        seed=3,
        episode_dir=episode,
        scenario_id="dense-crossing",
        scenario_version="v1",
    )

    paths = freeze_identity_episode(evidence, tmp_path / "frozen")

    combined = [
        json.loads(line)
        for line in paths["combined"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    capture = combined[0]["capture_provenance"]
    assert capture["scenario_id"] == "dense-crossing"
    assert capture["scenario_version"] == "v1"
    assert capture["scenario_config_version"] == "1"
    assert capture["seed"] == 3
    assert capture["target_spacing_m"] == 4.0
    assert capture["evidence_path"] == str(episode.resolve())

    bundle_text = paths["governed_bundle"].read_text(encoding="utf-8")
    assert "TGT-001" not in bundle_text
    truth = json.loads(paths["offline_truth"].read_text(encoding="utf-8"))
    assert truth["evaluator_only"] is True
    assert truth["samples"][0]["truth_id"] == "TGT-001"

    manifest = build_identity_calibration_manifest(
        ((evidence, paths),),
        tmp_path / "manifest.json",
        frozen_p95_loop_latency_budget_s=0.1,
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "d2-p1-identity-calibration-input/v1"
    assert payload["cases"][0]["seed"] == 3
    assert payload["evidence_source"] == "real_airsim_blocks_d1_governed_replay"

    cases, budget = load_identity_calibration_manifest(manifest)
    assert len(cases) == 1
    assert budget == 0.1
    assert cases[0].evidence_source == "real_airsim_blocks_d1_governed_replay"
