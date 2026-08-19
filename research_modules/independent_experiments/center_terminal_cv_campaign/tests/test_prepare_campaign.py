from __future__ import annotations

import json

from center_terminal_cv_campaign.prepare_campaign import prepare_fixture


def test_prepare_fixture_keeps_online_and_truth_separate(tmp_path) -> None:
    paths = prepare_fixture(
        output_root=tmp_path,
        target_count=5,
        seed=20260816,
        interceptor_count=8,
    )

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    online = paths["source_cues"].read_text(encoding="utf-8")
    assert manifest["source_precision"] == 0.8
    assert manifest["source_recall"] == 0.8
    assert "truth_target_id" not in online
    assert "actor_name" not in online
    assert paths["source_truth"].parent.name == "truth"
    assert paths["target_truth"].parent.name == "truth"

    capture_plan = json.loads(paths["crossview_capture_plan"].read_text(encoding="utf-8"))
    calibrations = json.loads(paths["crossview_calibrations"].read_text(encoding="utf-8"))
    assert capture_plan["recognition_rule"] == "bbox_longest_side_px_gte_10"
    assert len(capture_plan["frames"]) == 7
    assert len(capture_plan["frames"][0]["cameras"]) == 6
    assert len(calibrations["cameras"]) == 6
    assert all(
        camera["camera_id"].startswith("Terminal_CV_")
        for camera in calibrations["cameras"]
    )


def test_prepare_fixture_uses_all_50_crossview_resources_for_40_targets(tmp_path) -> None:
    paths = prepare_fixture(
        output_root=tmp_path,
        target_count=40,
        seed=20260818,
        interceptor_count=50,
        resource_count=50,
    )

    settings = json.loads(paths["settings"].read_text(encoding="utf-8"))
    capture_plan = json.loads(paths["crossview_capture_plan"].read_text(encoding="utf-8"))
    calibrations = json.loads(paths["crossview_calibrations"].read_text(encoding="utf-8"))
    assert len(settings["Vehicles"]) == 52
    assert len(capture_plan["frames"][0]["cameras"]) == 50
    assert len(calibrations["cameras"]) == 50
    assert len({camera["camera_id"] for camera in calibrations["cameras"]}) == 50
