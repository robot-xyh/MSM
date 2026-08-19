from __future__ import annotations

import json

import pytest

from center_terminal_cv_campaign.common.airsim_settings import write_campaign_settings
from center_terminal_cv_campaign.common.recognition import is_recognizable_bbox
from center_terminal_cv_campaign.common.scenario import (
    CampaignScenario,
    build_source_fixture,
    generate_targets,
)


@pytest.mark.parametrize("target_count", (5, 20, 40))
def test_source_fixture_is_exact_80_80_without_online_truth(target_count: int) -> None:
    config = CampaignScenario(target_count=target_count)
    targets = generate_targets(config)
    records, labels = build_source_fixture(config, targets)

    correct = sum(label.is_correct_source for label in labels)
    assert correct / len(records) == pytest.approx(0.8)
    assert correct / target_count == pytest.approx(0.8)
    serialized = json.dumps([record.to_online_dict() for record in records])
    assert "truth_target_id" not in serialized
    assert "actor_name" not in serialized


def test_ten_pixel_recognition_gate_uses_longest_bbox_side() -> None:
    assert not is_recognizable_bbox((0.0, 0.0, 9.99, 3.0))
    assert is_recognizable_bbox((0.0, 0.0, 10.0, 3.0))
    assert is_recognizable_bbox((0.0, 0.0, 3.0, 10.0))


def test_settings_use_required_computer_vision_profiles(tmp_path) -> None:
    path = write_campaign_settings(tmp_path / "settings.json", interceptor_count=40)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["SimMode"] == "ComputerVision"
    assert payload["ClockSpeed"] == pytest.approx(0.1)
    assert len(payload["Vehicles"]) == 42
    default_capture = payload["CameraDefaults"]["CaptureSettings"][0]
    center = payload["Vehicles"]["Center_Optical_A"]["Cameras"]["0"]["CaptureSettings"][0]
    terminal = payload["Vehicles"]["Terminal_CV_01"]["Cameras"]["0"]["CaptureSettings"][0]
    assert (center["Width"], center["Height"], center["FOV_Degrees"]) == (1280, 1024, 3.67)
    assert (terminal["Width"], terminal["Height"], terminal["FOV_Degrees"]) == (1920, 1080, 19.0)
    terminal_vehicle = payload["Vehicles"]["Terminal_CV_01"]
    assert (terminal_vehicle["X"], terminal_vehicle["Y"], terminal_vehicle["Z"]) == (0.0, 0.0, 0.0)
    assert (default_capture["Width"], default_capture["Height"], default_capture["FOV_Degrees"]) == (
        1920,
        1080,
        19.0,
    )
