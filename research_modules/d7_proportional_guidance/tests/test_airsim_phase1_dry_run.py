from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from d7_proportional_guidance import (
    AIRSIM_PHASE1_DRY_RUN_BOUNDARY,
    GuidanceMode,
    guidance_records_from_airsim_dry_run_fixture,
    guidance_records_from_assignment_dry_run,
    make_minimal_airsim_dry_run_fixture,
)


def test_airsim_phase1_fixture_produces_radar_and_vision_records() -> None:
    fixture = make_minimal_airsim_dry_run_fixture()

    records, summary = guidance_records_from_airsim_dry_run_fixture(fixture)

    assert [record.mode for record in records] == [
        GuidanceMode.RADAR_MIDCOURSE,
        GuidanceMode.VISION_TERMINAL,
    ]
    assert records[0].resource_id == "R01"
    assert records[0].target_id == "T01"
    assert records[1].mode_switch is True
    assert summary["dry_run"] is True
    assert summary["phase"] == "airsim_phase1"
    assert summary["boundary"] == AIRSIM_PHASE1_DRY_RUN_BOUNDARY
    assert summary["terminal_mode_entered"] is True

    for record in records:
        assert record.observation["dry_run"] is True
        assert record.observation["boundary"] == AIRSIM_PHASE1_DRY_RUN_BOUNDARY
        assert record.observation["truth_state_available"] is False
        data = record.as_dict()
        assert data["mode"] in {"radar_midcourse", "vision_terminal"}
        assert data["range_m"] > 0.0


def test_assignment_resource_target_estimate_objects_are_accepted() -> None:
    assignment = SimpleNamespace(
        plan_id="plan_7",
        plan_version=3,
        resource_id="R02",
        assigned_global_track_id="G10",
        authorization_state="recorded",
        created_at=12.5,
    )
    resource = SimpleNamespace(
        resource_id="R02",
        position_ned=[10.0, -20.0, -5.0],
    )
    target_estimate = SimpleNamespace(
        global_track_id="G10",
        valid_at=12.5,
        state_ned=[410.0, 80.0, -8.0, -12.0, -1.0, 0.0],
        covariance_trace=42.0,
        source="global_track_estimate",
        metadata={"frame_id": "ned"},
    )

    records, summary = guidance_records_from_assignment_dry_run(
        assignment=assignment,
        resource=resource,
        target_estimate=target_estimate,
    )

    assert len(records) == 2
    assert summary["plan_id"] == "plan_7"
    assert summary["plan_version"] == 3
    assert records[0].pursuer_velocity_mps != (0.0, 0.0)
    assert records[0].observation["authorization_state"] == "recorded"
    assert records[1].observation["source"] == "vision_los_dry_run"


def test_airsim_phase1_dry_run_does_not_import_airsim() -> None:
    existing_airsim = sys.modules.pop("airsim", None)
    try:
        fixture = make_minimal_airsim_dry_run_fixture()
        guidance_records_from_airsim_dry_run_fixture(fixture)
        assert "airsim" not in sys.modules
    finally:
        if existing_airsim is not None:
            sys.modules["airsim"] = existing_airsim


def test_assignment_target_mismatch_is_rejected() -> None:
    fixture = make_minimal_airsim_dry_run_fixture()
    fixture["target_estimate"] = {
        **fixture["target_estimate"],
        "global_track_id": "different_target",
    }

    with pytest.raises(ValueError, match="target_id"):
        guidance_records_from_airsim_dry_run_fixture(fixture)
