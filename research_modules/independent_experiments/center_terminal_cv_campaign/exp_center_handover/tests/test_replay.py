from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path

import pytest

from research_modules.independent_experiments.center_terminal_cv_campaign.common.io import (
    write_json,
    write_jsonl,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.fixture import (
    build_offline_fixture,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.replay import (
    REPLAY_SCHEMA,
    load_replay_fixture,
    reject_replay_as_training_input,
    sha256_file,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.run_experiment import (
    run,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.train_gnn import (
    main as train_main,
)


def test_saved_replay_supports_twenty_center_cameras_with_eight_resources(tmp_path) -> None:
    manifest = _write_replay(tmp_path, center_camera_count=20, resource_count=8)

    fixture, descriptor = load_replay_fixture(manifest)

    assert descriptor.resource_count == 8
    assert len(fixture.camera_models) == 20
    assert len(fixture.frames) == 3
    assert set(fixture.camera_models) == {row.camera_id for row in fixture.frames[0]}
    result = run(
        replay_manifest=manifest,
        output_dir=tmp_path / "result",
        mode="offline",
        association_backend="geometry",
    )
    assert result.replay_manifest == manifest.resolve()
    assert result.metrics["truth_leakage_count"] == 0


def test_replay_ignores_unneeded_crossview_paths(tmp_path) -> None:
    manifest = _write_replay(tmp_path)
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    assert "crossview_local_tracks" in raw["paths"]
    assert "crossview_local_tracks" not in raw["sha256"]
    assert not (manifest.parent / raw["paths"]["crossview_local_tracks"]).exists()

    fixture, _ = load_replay_fixture(manifest)

    assert fixture.frames


def test_replay_fails_closed_on_used_artifact_hash_mismatch(tmp_path) -> None:
    manifest = _write_replay(tmp_path)
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    source_path = (manifest.parent / raw["paths"]["source_cues"]).resolve()
    source_path.write_text(source_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="SHA256 mismatch"):
        load_replay_fixture(manifest)


def test_replay_fails_closed_on_manifest_schema_mismatch(tmp_path) -> None:
    manifest = _write_replay(tmp_path)
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["schema_version"] = "center-terminal-gnn-replay-v0"
    manifest.write_text(json.dumps(raw) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="replay schema"):
        load_replay_fixture(manifest)


def test_replay_fails_closed_on_online_schema_mismatch(tmp_path) -> None:
    manifest = _write_replay(tmp_path)
    source_path = _artifact_path(manifest, "source_cues")
    rows = _read_jsonl(source_path)
    rows[0]["schema_version"] = "old-source-schema"
    _rewrite_jsonl_and_hash(manifest, "source_cues", rows)

    with pytest.raises(ValueError, match="source-cue schema"):
        load_replay_fixture(manifest)


def test_replay_fails_closed_on_online_truth_or_actor_leak(tmp_path) -> None:
    manifest = _write_replay(tmp_path)
    local_path = _artifact_path(manifest, "center_local_tracks")
    rows = _read_jsonl(local_path)
    rows[0]["metadata"]["actor_name"] = "MSM_TargetActor_1"
    _rewrite_jsonl_and_hash(manifest, "center_local_tracks", rows)

    with pytest.raises(ValueError, match="leaked"):
        load_replay_fixture(manifest)


def test_replay_fails_closed_when_center_camera_pose_changes_across_frames(tmp_path) -> None:
    manifest = _write_replay(tmp_path)
    local_path = _artifact_path(manifest, "center_local_tracks")
    rows = _read_jsonl(local_path)
    camera_id = rows[0]["camera_id"]
    later = next(
        row
        for row in rows
        if row["camera_id"] == camera_id
        and row["measurement_timestamp"] != rows[0]["measurement_timestamp"]
    )
    later["ray_origin_ned_m"][0] += 0.01
    _rewrite_jsonl_and_hash(manifest, "center_local_tracks", rows)

    with pytest.raises(ValueError, match="pose changes"):
        load_replay_fixture(manifest)


def test_training_guard_rejects_test_only_and_held_out_campaign_seed(tmp_path) -> None:
    manifest = _write_replay(tmp_path)

    with pytest.raises(ValueError, match="cannot enter training"):
        reject_replay_as_training_input(manifest)
    with pytest.raises(ValueError, match="cannot enter training"):
        train_main(
            (
                "--output-model",
                str(tmp_path / "forbidden.pt"),
                "--train-seeds",
                "20260001",
                "--validation-seeds",
                "20260101",
                "--train-replay-manifest",
                str(manifest),
            )
        )


def _write_replay(
    root: Path,
    *,
    center_camera_count: int = 20,
    resource_count: int = 8,
) -> Path:
    if center_camera_count != 20:
        raise ValueError("test helper currently uses the frozen 20-target fixture")
    fixture = build_offline_fixture(target_count=20, seed=20260816)
    campaign = root / "saved_campaign"
    fixture_dir = campaign / "fixtures" / "fixture_n20_seed20260816"
    center_dir = campaign / "center_handover"
    crossview_dir = fixture_dir / "crossview"

    write_json(fixture_dir / "scenario.json", asdict(fixture.scenario))
    write_jsonl(center_dir / "online" / "source_cues.jsonl", fixture.source_cues)
    write_jsonl(
        center_dir / "online" / "local_tracks.jsonl",
        (record for frame in fixture.frames for record in frame),
    )
    write_jsonl(center_dir / "truth" / "source_cue_labels.jsonl", fixture.source_truth)
    write_jsonl(center_dir / "truth" / "local_track_labels.jsonl", fixture.local_truth)
    write_json(
        crossview_dir / "calibrations.json",
        {
            "schema_version": "terminal-crossview-calibrations-v1",
            "cameras": [
                {
                    "camera_id": f"Search_CV_{index + 1:02d}",
                    "width_px": 1920,
                    "height_px": 1080,
                    "horizontal_fov_deg": 19.0,
                    "confidence": 0.95,
                }
                for index in range(resource_count)
            ],
        },
    )
    write_json(
        crossview_dir / "capture_plan.json",
        {
            "schema_version": "terminal-crossview-airsim-capture-plan-v1",
            "frames": [
                {
                    "frame_index": 0,
                    "measurement_timestamp": 0.0,
                    "cameras": [
                        {
                            "camera_id": f"Search_CV_{index + 1:02d}",
                            "position_ned_m": [0.0, float(index), -100.0],
                            "yaw_pitch_roll_deg": [0.0, 0.0, 0.0],
                        }
                        for index in range(resource_count)
                    ],
                }
            ],
        },
    )

    manifest = campaign / "replay_manifest.json"
    artifacts = {
        "scenario": fixture_dir / "scenario.json",
        "source_cues": center_dir / "online" / "source_cues.jsonl",
        "center_local_tracks": center_dir / "online" / "local_tracks.jsonl",
        "center_source_truth": center_dir / "truth" / "source_cue_labels.jsonl",
        "center_local_truth": center_dir / "truth" / "local_track_labels.jsonl",
        "crossview_calibrations": crossview_dir / "calibrations.json",
        "crossview_capture_plan": crossview_dir / "capture_plan.json",
    }
    paths = {
        key: os.path.relpath(path, manifest.parent) for key, path in artifacts.items()
    }
    paths.update(
        {
            "crossview_local_tracks": "missing/captured_local_tracks.jsonl",
            "crossview_truth": "missing/local_track_truth_map.json",
        }
    )
    write_json(
        manifest,
        {
            "schema_version": REPLAY_SCHEMA,
            "scenario_id": "n20_m8",
            "campaign_seed": 20260816,
            "target_count": 20,
            "resource_count": resource_count,
            "test_only": True,
            "paths": paths,
            "sha256": {key: sha256_file(path) for key, path in artifacts.items()},
        },
    )
    return manifest


def _artifact_path(manifest: Path, key: str) -> Path:
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    return (manifest.parent / raw["paths"][key]).resolve()


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _rewrite_jsonl_and_hash(
    manifest: Path, key: str, rows: list[dict[str, object]]
) -> None:
    path = _artifact_path(manifest, key)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["sha256"][key] = sha256_file(path)
    manifest.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
