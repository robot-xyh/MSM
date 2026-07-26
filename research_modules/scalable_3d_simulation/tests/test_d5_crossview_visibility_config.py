from __future__ import annotations

import json
from pathlib import Path

from research_modules.scalable_3d_simulation.models import ScenarioConfig


CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "d5_crossview_visibility_calibration_v1.json"
)


def test_d5_crossview_visibility_config_is_isolated_from_nominal_runtime() -> None:
    config = ScenarioConfig.from_dict(
        json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    )

    assert (config.resource_count, config.target_count, config.recon_count) == (
        5,
        5,
        2,
    )
    assert config.visual_false_alarm_rate == 0.0
    assert config.visual_detection_probability == 1.0
    assert config.communication_drop_probability == 0.0
    assert config.metadata["calibration_scope"] == (
        "d5_truth_isolated_crossview_visibility"
    )
    assert config.metadata["default_operational_scenario"] is False
    assert config.metadata["online_truth_policy"] == "forbidden"
