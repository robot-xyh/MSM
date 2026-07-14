from __future__ import annotations

import json
import math

import pytest

from airsim_runtime.p1_cooperative_closure import (
    build_candidate_grid,
    build_cooperative_closure_cases,
    build_pair_funnel_rows,
    run_pointmass_candidate_screen,
    select_screened_candidates,
    summarize_cooperative_closure,
    write_cooperative_closure_bundle,
)
from airsim_runtime.models import write_dynamic_multirotor_settings
from airsim_runtime.models import BlocksSmokeConfig
from airsim_runtime.real_runtime import RealAirSimRuntimeClient
from airsim_runtime.run_blocks_sequence import (
    _cooperative_primary_vehicle_positions,
    _vehicle_position_offsets,
)


def _screening_rows():
    rows = []
    for index, candidate in enumerate(build_candidate_grid()):
        rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "safety_violation_count": 0 if candidate.approach_sector_separation_deg >= 40 else 1,
                "coalition_completion_score": 100 - index,
                "pair_success_score": 50 - index,
                "arrival_spread_s": candidate.primary_arrival_window_width_s,
            }
        )
    return rows


def test_candidate_grid_and_screening_are_frozen_and_deterministic() -> None:
    candidates = build_candidate_grid()
    assert len(candidates) == 27
    assert len({candidate.candidate_id for candidate in candidates}) == 27

    selected = select_screened_candidates(candidates, _screening_rows(), limit=3)
    assert len(selected) == 3
    assert all(candidate.approach_sector_separation_deg >= 40 for candidate in selected)
    assert selected == select_screened_candidates(candidates, _screening_rows(), limit=3)


def test_case_matrix_preserves_baseline_and_dynamic_scale() -> None:
    selected = select_screened_candidates(build_candidate_grid(), _screening_rows())
    cases = build_cooperative_closure_cases(
        (1, 2), selected, resource_count=7, target_count=3
    )

    assert len(cases) == 8
    assert sum(case.comparison_role == "baseline" for case in cases) == 2
    assert all((case.resource_count, case.target_count) == (7, 3) for case in cases)
    assert all(case.metadata()["calibration_suite_version"] == "p1-cooperative-closure-v2" for case in cases)


def test_pointmass_screen_and_sector_settings_are_executable(tmp_path) -> None:
    candidate = build_candidate_grid()[0]
    rows = run_pointmass_candidate_screen((candidate,), seeds=(3,))
    assert len(rows) == 1
    assert rows[0]["evidence_source"] == "d7_offline_2d_point_mass"
    assert rows[0]["pair_opportunity_count"] == 2

    names = ("Interceptor1", "Interceptor2", "Interceptor3")
    positions = _cooperative_primary_vehicle_positions(
        names,
        target_count=2,
        target_distance_m=35.0,
        target_spacing_m=10.0,
        default_resource_spacing_m=10.0,
        sector_separation_deg=40.0,
    )
    assert positions is not None
    offset = positions[names[1]][1] - (-5.0)
    assert math.degrees(2.0 * math.atan2(offset, 35.0)) == pytest.approx(40.0)

    path = write_dynamic_multirotor_settings(
        tmp_path / "settings.json",
        vehicle_names=names,
        vehicle_positions_ned=positions,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["Vehicles"][names[0]]["Y"] == positions[names[0]][1]

    offsets = _vehicle_position_offsets(
        names,
        desired_positions=positions,
        default_resource_spacing_m=10.0,
    )
    assert offsets[names[0]][1] != 0.0


def test_real_runtime_applies_candidate_offsets_after_each_reset() -> None:
    calls = []

    class Client:
        def simSetVehiclePose(self, pose, ignore_collision=True, vehicle_name=""):
            calls.append((vehicle_name, pose, ignore_collision))
            return True

    runtime = object.__new__(RealAirSimRuntimeClient)
    runtime.client = Client()
    runtime._quaternion_from_euler = lambda *_: "identity"
    runtime._pose_from_position_orientation = lambda position, orientation: (
        position,
        orientation,
    )
    config = BlocksSmokeConfig(
        resource_vehicle_names=("Interceptor1", "Interceptor2"),
        metadata={
            "cooperative_pose_via_api": True,
            "cooperative_vehicle_pose_offsets_ned": {
                "Interceptor1": (0.0, -2.0, 0.0),
                "Interceptor2": (0.0, 2.0, 0.0),
            },
        },
    )

    runtime._apply_cooperative_initial_pose_offsets(config)

    assert calls == [
        ("Interceptor1", ((0.0, -2.0, 0.0), "identity"), True),
        ("Interceptor2", ((0.0, 2.0, 0.0), "identity"), True),
    ]


def test_pair_funnel_and_summary_keep_layers_separate(tmp_path) -> None:
    selected = select_screened_candidates(build_candidate_grid(), _screening_rows(), limit=1)
    cases = build_cooperative_closure_cases((7,), selected)
    case = cases[1]
    summary = {
        "pairs": [
            {
                "resource_id": "R1",
                "target_id": "T1",
                "member_role": "primary",
                "activation_state": "active",
                "assigned": True,
                "physical_success": True,
                "min_range_m": 3.0,
                "arrival_timestamp_s": 6.0,
                "arrival_window": [5.0, 8.0],
                "plan_id": "plan-1",
                "plan_version": 2,
            },
            {
                "resource_id": "R2",
                "target_id": "T1",
                "member_role": "primary",
                "activation_state": "active",
                "assigned": True,
                "physical_success": True,
                "min_range_m": 4.0,
                "arrival_timestamp_s": 7.0,
                "arrival_window": [5.0, 8.0],
                "plan_id": "plan-1",
                "plan_version": 2,
            },
            {
                "resource_id": "R3",
                "target_id": "T1",
                "member_role": "reserve",
                "activation_state": "standby",
                "assigned": True,
                "physical_success": False,
            },
        ]
    }
    commands = []
    for resource_id in ("R1", "R2"):
        for timestamp in (1.0, 1.1):
            commands.append(
                {
                    "resource_id": resource_id,
                    "target_id": "T1",
                    "timestamp_s": timestamp,
                    "detection_seen": True,
                    "d5_decision_state": "locked",
                    "terminal_contract_allowed": True,
                    "terminal_control_allowed": True,
                    "mode_switched": True,
                    "mode": "vision_terminal",
                    "truth_identity_online_use": False,
                }
            )

    rows = build_pair_funnel_rows(case, summary, commands)
    assert len(rows) == 3
    assert rows[0]["common_lock_frame_count"] == 2
    assert rows[0]["arrival_error_s"] == 0.0
    assert rows[2]["reserve_unauthorized"] is False

    payload = summarize_cooperative_closure((case,), rows)
    aggregate = payload["aggregates"][0]
    assert aggregate["pair_opportunity_count"] == 2
    assert aggregate["target_opportunity_count"] == 1
    assert aggregate["coalition_opportunity_count"] == 1
    assert aggregate["coalition_completion_count"] == 1
    assert payload["acceptance"]["online_truth_use_zero"] is True

    paths = write_cooperative_closure_bundle(tmp_path, (case,), rows)
    assert json.loads(paths["json"].read_text(encoding="utf-8"))["pair_row_count"] == 3
    assert paths["csv"].exists()
    assert "协同物理闭环" in paths["markdown"].read_text(encoding="utf-8")
