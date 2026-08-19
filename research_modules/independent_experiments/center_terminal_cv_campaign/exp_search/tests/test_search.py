from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from center_terminal_cv_campaign.common.scenario import (
    CampaignScenario,
    build_source_fixture,
    generate_targets,
)
from center_terminal_cv_campaign.prepare_campaign import prepare_fixture
from center_terminal_cv_campaign.exp_search.fake_client import (
    FakeAirSimModule,
    ScriptedFakeAirSimClient,
)
from center_terminal_cv_campaign.exp_search.fixture import load_fixture
from center_terminal_cv_campaign.exp_search.models import (
    CameraSearchCommand,
    SearchCell,
    SearchExperimentConfig,
)
from center_terminal_cv_campaign.exp_search.planner import (
    RollingSearchPlanner,
    build_probability_regions_and_cells,
    initial_resource_states,
)
from center_terminal_cv_campaign.exp_search.run_experiment import run_experiment
from center_terminal_cv_campaign.exp_search.runtime import (
    AirSimSearchAdapter,
    SearchExperimentRunner,
)


def _fixture(target_count: int = 5):
    scenario = CampaignScenario(target_count=target_count, seed=20260816)
    targets = generate_targets(scenario)
    cues, labels = build_source_fixture(scenario, targets)
    return scenario, targets, cues, labels


def _cell(
    *,
    cell_id: str = "CELL-GAP-TEST",
    kind: str = "unbound_gap",
    source_ids: tuple[str, ...] = (),
    valid_until: float | None = None,
) -> SearchCell:
    return SearchCell(
        search_cell_id=cell_id,
        region_id=f"REG-{cell_id}",
        center_ned_m=(3000.0, 0.0, -140.0),
        look_at_ned_m=(3000.0, 0.0, -140.0),
        half_extent_ned_m=(100.0, 100.0, 80.0),
        target_probability=0.5,
        cell_kind=kind,
        candidate_source_track_ids=source_ids,
        valid_until=valid_until,
    )


def _runner_with_schedule(
    schedule,
    *,
    cells: tuple[SearchCell, ...],
    frames_per_assignment: int = 2,
):
    _, targets, cues, labels = _fixture()
    config = SearchExperimentConfig(
        target_count=5,
        resource_count=1,
        assignment_cycles=1,
        frames_per_assignment=frames_per_assignment,
    )
    client = ScriptedFakeAirSimClient(schedule)
    adapter = AirSimSearchAdapter(
        config,
        client=client,
        airsim_module=FakeAirSimModule,
        truth_name_to_id={target.actor_name: target.truth_target_id for target in targets},
    )
    runner = SearchExperimentRunner(
        config=config,
        source_cues=cues,
        source_truth_labels=labels,
        targets=targets,
        adapter=adapter,
        fixture_source="unit_test",
        data_source="offline_scripted_fake_client",
        cells=cells,
    )
    return runner.run(), targets, labels, client


def test_probability_regions_include_source_directed_and_unbound_gap_cells() -> None:
    scenario, targets, cues, _ = _fixture()
    config = SearchExperimentConfig(target_count=scenario.target_count, resource_count=8)
    regions, cells = build_probability_regions_and_cells(cues, config)

    source_cells = [cell for cell in cells if cell.cell_kind == "source_directed"]
    gap_cells = [cell for cell in cells if cell.cell_kind == "unbound_gap"]
    assert len(source_cells) == len(cues)
    assert len(gap_cells) >= 5
    assert all(cell.candidate_source_track_ids for cell in source_cells)
    assert all(not cell.candidate_source_track_ids for cell in gap_cells)
    assert source_cells[0].valid_until == pytest.approx(cues[0].valid_until)
    assert len(targets) == 5


def test_default_dwell_keeps_two_frame_gate_with_one_retry_frame() -> None:
    config = SearchExperimentConfig(target_count=5, resource_count=8)
    assert config.frames_per_assignment == 3
    assert config.confirmation_frames == 2
    with pytest.raises(ValueError, match="cannot be below confirmation_frames"):
        SearchExperimentConfig(target_count=5, resource_count=8, frames_per_assignment=1)


@pytest.mark.parametrize("resource_count", (1, 7, 31))
def test_hungarian_assignment_is_unique_and_uses_input_scale(resource_count: int) -> None:
    _, _, cues, _ = _fixture()
    config = SearchExperimentConfig(target_count=5, resource_count=resource_count)
    _, cells = build_probability_regions_and_cells(cues, config)
    planner = RollingSearchPlanner(config, initial_resource_states(resource_count))

    assignments = planner.plan(cells, timestamp=0.0)
    assigned_cells = [item.search_cell_id for item in assignments if item.search_cell_id is not None]
    assert len(assignments) == resource_count
    assert len(assigned_cells) == len(set(assigned_cells))


def test_resource_initial_state_matches_common_world_ned_origin() -> None:
    states = initial_resource_states(8)
    assert all(state.position_ned_m == (0.0, 0.0, 0.0) for state in states)


def test_expired_source_cell_uses_record_valid_until() -> None:
    config = SearchExperimentConfig(target_count=5, resource_count=1)
    planner = RollingSearchPlanner(config, initial_resource_states(1))
    assignments = planner.plan((_cell(valid_until=1.0),), timestamp=1.01)
    assert assignments[0].search_cell_id is None


def test_air_sim_adapter_applies_ten_pixel_gate_and_removes_truth() -> None:
    _, targets, _, _ = _fixture()
    camera_id = "Terminal_CV_01"
    schedule = {
        (0, camera_id): (
            (targets[0].actor_name, (10.0, 10.0, 19.99, 13.0)),
            (targets[1].actor_name, (30.0, 30.0, 40.0, 33.0)),
        )
    }
    config = SearchExperimentConfig(target_count=5, resource_count=1)
    client = ScriptedFakeAirSimClient(schedule)
    adapter = AirSimSearchAdapter(
        config,
        client=client,
        airsim_module=FakeAirSimModule,
        truth_name_to_id={target.actor_name: target.truth_target_id for target in targets},
    )
    adapter.connect()
    adapter.configure_detection_filters((camera_id,))
    adapter.apply_command(
        CameraSearchCommand(
            plan_version=1,
            camera_id=camera_id,
            search_cell_id="CELL-001",
            position_ned_m=(2300.0, 0.0, -140.0),
            look_at_ned_m=(3000.0, 0.0, -140.0),
            yaw_deg=0.0,
            pitch_deg=0.0,
        )
    )
    adapter.begin_frame(0, 0.0)
    online, offline = adapter.capture(camera_id, frame_index=0, measurement_timestamp=0.0)

    commanded_pose = client.pose_commands[-1][1]
    assert (
        commanded_pose.position.x_val,
        commanded_pose.position.y_val,
        commanded_pose.position.z_val,
    ) == (2300.0, 0.0, -140.0)
    assert [record.recognized for record in online] == [False, True]
    serialized = json.dumps([asdict(record) for record in online])
    assert "MSM_TargetActor" not in serialized
    assert "TGT-" not in serialized
    assert [label.truth_target_id for label in offline] == [
        targets[0].truth_target_id,
        targets[1].truth_target_id,
    ]


def test_two_recognizable_frames_confirm_center_missed_target_from_gap_cell() -> None:
    _, targets, _, labels = _fixture()
    correct_ids = {
        label.truth_target_id for label in labels if label.is_correct_source
    }
    missed = next(target for target in targets if target.truth_target_id not in correct_ids)
    camera_id = "Terminal_CV_01"
    schedule = {
        (0, camera_id): ((missed.actor_name, (900.0, 500.0, 912.0, 507.0)),),
        (1, camera_id): ((missed.actor_name, (902.0, 500.0, 914.0, 507.0)),),
    }
    result, _, _, client = _runner_with_schedule(schedule, cells=(_cell(),))

    assert len(result.handover_records) == 1
    assert result.handover_records[0].candidate_source_track_ids == ()
    assert result.metrics["center_missed_recovered_count"] == 1
    assert result.metrics["online_truth_leakage_count"] == 0
    assert client.pose_commands


def test_below_ten_pixels_never_confirms_even_after_two_frames() -> None:
    _, targets, _, _ = _fixture()
    camera_id = "Terminal_CV_01"
    schedule = {
        (0, camera_id): ((targets[0].actor_name, (1.0, 1.0, 10.99, 4.0)),),
        (1, camera_id): ((targets[0].actor_name, (2.0, 1.0, 11.99, 4.0)),),
    }
    result, _, _, _ = _runner_with_schedule(schedule, cells=(_cell(),))
    assert not result.handover_records
    assert result.metrics["below_ten_pixel_detection_count"] == 2


def test_one_recognizable_frame_within_two_frame_dwell_is_not_enough_to_confirm() -> None:
    _, targets, _, _ = _fixture()
    camera_id = "Terminal_CV_01"
    result, _, _, _ = _runner_with_schedule(
        {(0, camera_id): ((targets[0].actor_name, (1.0, 1.0, 11.0, 4.0)),)},
        cells=(_cell(),),
        frames_per_assignment=2,
    )
    assert result.metrics["recognizable_detection_count"] == 1
    assert not result.handover_records


def test_initial_miss_then_two_consecutive_detections_confirm_with_retry_frame() -> None:
    _, targets, _, _ = _fixture()
    camera_id = "Terminal_CV_01"
    schedule = {
        (1, camera_id): ((targets[0].actor_name, (1.0, 1.0, 11.0, 4.0)),),
        (2, camera_id): ((targets[0].actor_name, (2.0, 1.0, 12.0, 4.0)),),
    }
    result, _, _, _ = _runner_with_schedule(
        schedule,
        cells=(_cell(),),
        frames_per_assignment=3,
    )
    assert len(result.handover_records) == 1


def test_retry_frame_does_not_accept_nonconsecutive_detections() -> None:
    _, targets, _, _ = _fixture()
    camera_id = "Terminal_CV_01"
    schedule = {
        (0, camera_id): ((targets[0].actor_name, (1.0, 1.0, 11.0, 4.0)),),
        (2, camera_id): ((targets[0].actor_name, (2.0, 1.0, 12.0, 4.0)),),
    }
    result, _, _, _ = _runner_with_schedule(
        schedule,
        cells=(_cell(),),
        frames_per_assignment=3,
    )
    assert not result.handover_records
    assert result.metrics["recognized_but_unconfirmed_target_count"] == 1


def test_ghost_source_without_visual_detection_does_not_confirm() -> None:
    _, _, cues, labels = _fixture()
    ghost_label = next(label for label in labels if label.corruption_type == "ghost_source")
    ghost_cue = next(cue for cue in cues if cue.source_track_id == ghost_label.source_track_id)
    cell = _cell(
        cell_id="CELL-GHOST",
        kind="source_directed",
        source_ids=(ghost_cue.source_track_id,),
    )
    result, _, _, _ = _runner_with_schedule({}, cells=(cell,))
    assert not result.handover_records
    assert result.metrics["ghost_source_confirmed_count"] == 0


def test_visual_target_seen_near_ghost_cue_remains_candidate_only() -> None:
    _, targets, cues, labels = _fixture()
    ghost_label = next(label for label in labels if label.corruption_type == "ghost_source")
    ghost_cue = next(cue for cue in cues if cue.source_track_id == ghost_label.source_track_id)
    camera_id = "Terminal_CV_01"
    schedule = {
        (0, camera_id): ((targets[0].actor_name, (900.0, 500.0, 912.0, 507.0)),),
        (1, camera_id): ((targets[0].actor_name, (902.0, 500.0, 914.0, 507.0)),),
    }
    result, _, _, _ = _runner_with_schedule(
        schedule,
        cells=(
            _cell(
                cell_id="CELL-GHOST-VISUAL",
                kind="source_directed",
                source_ids=(ghost_cue.source_track_id,),
            ),
        ),
    )
    assert len(result.handover_records) == 1
    assert result.handover_records[0].metadata["source_binding_state"] == "candidate_only"
    assert result.metrics["ghost_source_confirmed_count"] == 0
    assert result.metrics["ghost_source_visual_handover_count"] == 1


def test_common_prepare_fixture_output_and_fixed_output_paths(tmp_path: Path) -> None:
    paths = prepare_fixture(
        output_root=tmp_path / "fixtures",
        target_count=5,
        seed=20260816,
        interceptor_count=8,
    )
    fixture_dir = paths["fixture_dir"]
    assert (
        paths["source_cues"].relative_to(fixture_dir).as_posix()
        == "online/source_cues.jsonl"
    )
    assert (
        paths["source_truth"].relative_to(fixture_dir).as_posix()
        == "truth/source_cue_labels.jsonl"
    )
    assert (
        paths["target_truth"].relative_to(fixture_dir).as_posix()
        == "truth/targets.jsonl"
    )
    loaded = load_fixture(fixture_dir)
    assert len(loaded.targets) == 5
    output_dir = tmp_path / "output"
    result = run_experiment(
        mode="offline",
        fixture_dir=fixture_dir,
        output_dir=output_dir,
        target_count=5,
        resource_count=8,
        assignment_cycles=1,
    )
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "REPORT_CN.md").exists()
    assert (output_dir / "figures" / "search_cell_coverage.png").exists()
    assert result.metrics["online_truth_leakage_count"] == 0
    assert "TGT-" not in (output_dir / "metrics.json").read_text(encoding="utf-8")
    scoring = json.loads((output_dir / "truth" / "scoring.json").read_text(encoding="utf-8"))
    assert scoring["offline_truth_only"] is True
    assert len(scoring["target_diagnostics"]) == 5


def test_scenario_target_count_is_inferred_and_explicit_mismatch_is_rejected(
    tmp_path: Path,
) -> None:
    paths = prepare_fixture(
        output_root=tmp_path / "fixtures",
        target_count=20,
        seed=20260817,
        interceptor_count=8,
    )
    fixture_dir = paths["fixture_dir"]
    result = run_experiment(
        mode="offline",
        fixture_dir=fixture_dir,
        output_dir=tmp_path / "output_n20",
        resource_count=8,
        assignment_cycles=1,
    )
    assert result.config.target_count == 20
    assert result.config.seed == 20260817

    with pytest.raises(ValueError, match="conflicts with scenario target_count 20"):
        load_fixture(fixture_dir, target_count=5)
