from __future__ import annotations

import json
from pathlib import Path

import pytest

from center_terminal_cv_campaign.gnn_benchmark import (
    REPLAY_SCHEMA,
    SavedCampaign,
    _crossview_timing_repeats,
    build_replay_manifest,
    evaluate_acceptance,
    load_replay_manifest,
    replay_configuration,
)


def _saved_campaign(tmp_path: Path) -> tuple[SavedCampaign, Path]:
    campaign = SavedCampaign("n20_m8", "saved", 20, 8)
    root = tmp_path / "outputs"
    campaign_dir = root / campaign.campaign_id
    fixture = campaign_dir / "fixtures" / "fixture_n20_seed20260816"
    files = (
        fixture / "scenario.json",
        campaign_dir / "center_handover" / "online" / "source_cues.jsonl",
        campaign_dir / "center_handover" / "online" / "local_tracks.jsonl",
        campaign_dir / "center_handover" / "truth" / "source_cue_labels.jsonl",
        campaign_dir / "center_handover" / "truth" / "local_track_labels.jsonl",
        campaign_dir / "crossview" / "captured_local_tracks.jsonl",
        fixture / "crossview" / "calibrations.json",
        fixture / "crossview" / "capture_plan.json",
        campaign_dir / "crossview" / "truth" / "local_track_truth_map.json",
    )
    for index, path in enumerate(files):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture-{index}\n", encoding="utf-8")
    files[0].write_text(
        json.dumps(
            {
                "target_speed_mps": 50.0,
                "target_longest_dimension_m": 3.0,
                "duration_s": 18.0,
                "clock_speed": 0.1,
                "source_precision": 0.8,
                "source_recall": 0.8,
            }
        ),
        encoding="utf-8",
    )
    files[6].write_text(
        json.dumps(
            {
                "cameras": [
                    {
                        "width_px": 1920,
                        "height_px": 1080,
                        "horizontal_fov_deg": 19.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return campaign, root


def test_manifest_references_sources_and_verifies_hashes(tmp_path: Path) -> None:
    campaign, root = _saved_campaign(tmp_path)
    manifest = build_replay_manifest(
        campaign,
        source_root=root,
        manifest_dir=tmp_path / "benchmark" / "manifests",
    )

    payload = load_replay_manifest(manifest)

    assert payload["schema_version"] == REPLAY_SCHEMA
    assert payload["test_only"] is True
    assert payload["campaign_seed"] == 20260816
    assert len(payload["paths"]) == 9
    assert all(not Path(value).is_absolute() for value in payload["paths"].values())


def test_manifest_rejects_modified_replay(tmp_path: Path) -> None:
    campaign, root = _saved_campaign(tmp_path)
    manifest = build_replay_manifest(
        campaign,
        source_root=root,
        manifest_dir=tmp_path / "benchmark" / "manifests",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    source = (manifest.parent / payload["paths"]["source_cues"]).resolve()
    source.write_text("changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        load_replay_manifest(manifest)


def test_manifest_rejects_training_like_metadata(tmp_path: Path) -> None:
    campaign, root = _saved_campaign(tmp_path)
    manifest = build_replay_manifest(
        campaign,
        source_root=root,
        manifest_dir=tmp_path / "benchmark" / "manifests",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["test_only"] = False
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="held-out"):
        load_replay_manifest(manifest)


def test_replay_configuration_reads_verified_report_facts(tmp_path: Path) -> None:
    campaign, root = _saved_campaign(tmp_path)
    manifest = build_replay_manifest(
        campaign,
        source_root=root,
        manifest_dir=tmp_path / "benchmark" / "manifests",
    )
    payload = load_replay_manifest(manifest)

    configuration = replay_configuration(manifest, payload)

    assert configuration["target_count"] == 20
    assert configuration["resource_count"] == 8
    assert configuration["target_speed_mps"] == 50.0
    assert configuration["recognition_extent_px"] == 10.0
    assert configuration["terminal_camera_profiles"] == [
        {"width_px": 1920, "height_px": 1080, "horizontal_fov_deg": 19.0}
    ]


def _acceptance_summary(*, large_precision_gain: float = 0.05) -> dict:
    results = []
    for scenario in ("n20_m8", "n20_m30", "n40_m50"):
        for backend in ("geometry", "gnn"):
            results.append(
                {
                    "scenario_id": scenario,
                    "task": "center_handover",
                    "backend": backend,
                    "metrics": {
                        "true_binding_count": 16,
                        "false_binding_count": 0,
                    },
                    "timing": {"median_wall_duration_s": 1.0 if backend == "geometry" else 1.4},
                }
            )
        for policy in ("full", "sector_fov"):
            for backend in ("geometry", "gnn"):
                base_precision = 1.0 if scenario == "n20_m8" else 0.6
                precision = (
                    base_precision
                    if backend == "geometry"
                    else min(1.0, base_precision + large_precision_gain)
                )
                results.append(
                    {
                        "scenario_id": scenario,
                        "task": "crossview",
                        "camera_pair_policy": policy,
                        "backend": backend,
                        "metrics": {
                            "association_precision": precision,
                            "association_recall": 0.94 if scenario == "n20_m8" else 0.88,
                            "id_switch_count": 0 if scenario == "n20_m8" else (5 if backend == "geometry" else 4),
                        },
                        "timing": {"median_wall_duration_s": 2.0 if backend == "geometry" else 2.8},
                    }
                )
    return {"results": results}


def test_acceptance_requires_large_scene_precision_gain() -> None:
    passing = evaluate_acceptance(_acceptance_summary(large_precision_gain=0.05))
    failing = evaluate_acceptance(_acceptance_summary(large_precision_gain=0.049))

    assert passing["all_passed"] is True
    assert failing["all_passed"] is False
    assert any(
        not item["passed"] and item["name"].endswith("sparse_gnn_gain")
        for item in failing["checks"]
    )


def test_crossview_timing_policy_bounds_scale_stress_repeats() -> None:
    assert _crossview_timing_repeats("n20_m8", "full", requested=8) == 5
    assert _crossview_timing_repeats("n20_m30", "sector_fov", requested=8) == 3
    assert _crossview_timing_repeats("n20_m30", "full", requested=8) == 1
    assert _crossview_timing_repeats("n40_m50", "sector_fov", requested=8) == 1
