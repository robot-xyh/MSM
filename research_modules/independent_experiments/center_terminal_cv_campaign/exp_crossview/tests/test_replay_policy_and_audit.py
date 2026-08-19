from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.camera_pairs import (
    build_camera_pair_plan,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.config import (
    CameraCalibration,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.fixture import (
    build_fixture,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.replay_io import (
    load_replay_manifest,
    load_saved_replay_online,
    sha256_file,
    write_fixture,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.run_experiment import (
    run,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.training import (
    AIRSIM_TEST_SEED,
    TrainingConfig,
    train_and_save,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _replay_manifest(
    tmp_path: Path,
    *,
    campaign_seed: int = AIRSIM_TEST_SEED,
    test_only: bool = True,
) -> Path:
    source = tmp_path / "saved_campaign"
    bundle = build_fixture("partial_3cam_5target", seed=campaign_seed)
    write_fixture(source / "fixture", bundle)
    capture_plan = source / "fixture" / "capture_plan.json"
    frames = []
    for frame_index in range(bundle.frame_count):
        frames.append(
            {
                "frame_index": frame_index,
                "cameras": [
                    {
                        "camera_id": camera_id,
                        "sector_index": index // 2,
                        "yaw_pitch_roll_deg": [0.0, 0.0, 0.0],
                    }
                    for index, camera_id in enumerate(sorted(bundle.calibrations))
                ],
            }
        )
    _write_json(
        capture_plan,
        {
            "schema_version": "terminal-crossview-airsim-capture-plan-v1",
            "frames": frames,
            "offline_sector_expectations": {
                "Terminal_CV_01": ["Actor_Should_Not_Reach_Online"]
            },
        },
    )
    truth_path = source / "truth" / "local_track_truth_map.json"
    _write_json(
        truth_path,
        {
            "schema_version": "terminal-crossview-airsim-local-truth-v1",
            "offline_truth_only": True,
            "track_to_target": bundle.truth.track_to_target,
        },
    )
    paths = {
        "crossview_local_tracks": source / "fixture" / "local_tracks.jsonl",
        "crossview_calibrations": source / "fixture" / "calibrations.json",
        "crossview_capture_plan": capture_plan,
        "crossview_truth": truth_path,
    }
    manifest_path = tmp_path / "manifests" / "replay.json"
    manifest_path.parent.mkdir(parents=True)
    relative_paths = {
        key: os.path.relpath(path, manifest_path.parent) for key, path in paths.items()
    }
    relative_paths["source_cues"] = "missing/center/source_cues.jsonl"
    _write_json(
        manifest_path,
        {
            "schema_version": "center-terminal-gnn-replay-v1",
            "scenario_id": "fixture_n5_m3",
            "campaign_seed": campaign_seed,
            "target_count": 5,
            "resource_count": 3,
            "test_only": test_only,
            "paths": relative_paths,
            "sha256": {key: sha256_file(path) for key, path in paths.items()},
        },
    )
    return manifest_path


def test_saved_replay_resolves_relative_paths_and_ignores_center_keys(
    tmp_path: Path,
) -> None:
    manifest = load_replay_manifest(_replay_manifest(tmp_path))
    online = load_saved_replay_online(manifest)
    assert len(online.records) > 0
    assert len(online.calibrations) == 3
    encoded_plan = json.dumps(online.capture_plan).lower()
    assert "offline_sector_expectations" not in encoded_plan
    assert "actor" not in encoded_plan


def test_saved_replay_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    manifest_path = _replay_manifest(tmp_path)
    manifest = load_replay_manifest(manifest_path)
    tracks_path = manifest.paths["crossview_local_tracks"]
    tracks_path.write_text(
        tracks_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        load_replay_manifest(manifest_path)


def test_saved_replay_rejects_identity_bearing_online_track(tmp_path: Path) -> None:
    manifest_path = _replay_manifest(tmp_path)
    manifest = load_replay_manifest(manifest_path)
    tracks_path = manifest.paths["crossview_local_tracks"]
    lines = tracks_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first.setdefault("metadata", {})["truth_id"] = "OFFLINE-T001"
    lines[0] = json.dumps(first)
    tracks_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["sha256"]["crossview_local_tracks"] = sha256_file(tracks_path)
    _write_json(manifest_path, payload)
    verified = load_replay_manifest(manifest_path)
    with pytest.raises(ValueError, match="identity-bearing"):
        load_saved_replay_online(verified)


def test_sector_fov_keeps_same_sector_and_overlapping_adjacent_views() -> None:
    calibrations = {
        f"C{index}": CameraCalibration(camera_id=f"C{index}", horizontal_fov_deg=19.0)
        for index in range(1, 6)
    }
    capture_plan = {
        "schema_version": "terminal-crossview-airsim-capture-plan-v1",
        "frames": [
            {
                "frame_index": 0,
                "cameras": [
                    {"camera_id": "C1", "sector_index": 0, "yaw_pitch_roll_deg": [0, 0, 0]},
                    {"camera_id": "C2", "sector_index": 0, "yaw_pitch_roll_deg": [0, 0, 0]},
                    {"camera_id": "C3", "sector_index": 1, "yaw_pitch_roll_deg": [0, 0, 0]},
                    {"camera_id": "C4", "sector_index": 1, "yaw_pitch_roll_deg": [180, 0, 0]},
                    {"camera_id": "C5", "sector_index": 3, "yaw_pitch_roll_deg": [0, 0, 0]},
                ],
            }
        ],
        "offline_sector_expectations": {"C1": ["Actor_1"]},
    }
    plan = build_camera_pair_plan(
        calibrations,
        policy="sector_fov",
        capture_plan=capture_plan,
    )
    assert plan.total_count == 10
    assert plan.allowed_pairs == frozenset(
        {("C1", "C2"), ("C1", "C3"), ("C2", "C3"), ("C3", "C4")}
    )
    assert plan.retained_count == 4
    assert plan.pruned_count == 6
    assert plan.rejection_reason_counts == {
        "adjacent_sector_without_fov_overlap": 2,
        "non_adjacent_sector": 4,
    }
    full = build_camera_pair_plan(calibrations, policy="full")
    assert full.retained_count == full.total_count == 10
    assert full.pruned_count == 0


def test_replay_defaults_to_bounded_audit_outputs_and_detailed_is_compatible(
    tmp_path: Path,
) -> None:
    manifest_path = _replay_manifest(tmp_path)
    audit_output = tmp_path / "audit"
    audit_output.mkdir()
    (audit_output / "candidate_edges.jsonl").write_text("stale\n")
    (audit_output / "candidate_graph.json").write_text("{}\n")
    artifacts = run(
        replay_manifest=manifest_path,
        output_dir=audit_output,
        association_backend="geometry",
        camera_pair_policy="sector_fov",
        candidate_sample_limit=4,
        error_sample_limit=3,
    )
    assert artifacts.output_mode == "audit"
    assert not (audit_output / "candidate_edges.jsonl").exists()
    assert not (audit_output / "candidate_graph.json").exists()
    audit = json.loads((audit_output / "candidate_audit.json").read_text())
    assert audit["retained_candidate_sample_count"] <= 4
    assert audit["candidate_stage_counts"]["generated"] > 4
    assert audit["camera_pair_policy"] == "sector_fov"
    errors = json.loads(
        (audit_output / "truth" / "offline_error_samples.json").read_text()
    )
    assert errors["retained_sample_count"] <= 3
    for online_name in ("online_result.json", "candidate_audit.json", "metrics.json"):
        text = (audit_output / online_name).read_text(encoding="utf-8").lower()
        assert "actor_should_not_reach_online" not in text
        assert "offline-t" not in text

    detailed_output = tmp_path / "detailed"
    run(
        replay_manifest=manifest_path,
        output_dir=detailed_output,
        association_backend="geometry",
        output_mode="detailed",
    )
    assert (detailed_output / "candidate_edges.jsonl").exists()
    assert (detailed_output / "candidate_graph.json").exists()


def test_training_rejects_reserved_seed_and_test_only_replay(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="20260816"):
        TrainingConfig(
            train_seeds=(AIRSIM_TEST_SEED,),
            validation_seeds=(20262000,),
        )
    with pytest.raises(ValueError, match="test-only replay"):
        train_and_save(
            tmp_path / "model",
            config=TrainingConfig(
                train_seeds=(101,),
                validation_seeds=(201,),
                target_count=3,
                epochs=1,
                hidden_dim=8,
                training_replay_manifests=(str(_replay_manifest(tmp_path)),),
            ),
        )


def test_default_training_scale_contains_twenty_and_forty_targets() -> None:
    assert TrainingConfig().effective_target_counts == (20, 40)
