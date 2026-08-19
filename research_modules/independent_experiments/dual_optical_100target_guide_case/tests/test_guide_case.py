from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from dual_optical_100target_guide_case.build_word_report import build_document
from dual_optical_100target_guide_case.core import (
    CameraSpec,
    CameraState,
    ScenarioConfig,
    associate_tracks,
    build_synthetic_tracks,
    crossing_pairs,
    generate_target_specs,
    minimum_initial_separation,
    online_truth_leakage_keys,
)
from dual_optical_100target_guide_case.reporting import generate_experiment_report
from dual_optical_100target_guide_case.runtime import (
    GuideCaseAirSimRunner,
    load_experiment_result,
    prepare_case,
    run_synthetic_fixture,
)


@pytest.fixture(scope="module")
def config() -> ScenarioConfig:
    return ScenarioConfig()


@pytest.fixture(scope="module")
def synthetic_association(config: ScenarioConfig):
    tracks_a, tracks_b, truth = build_synthetic_tracks(config, CameraSpec())
    return tracks_a, tracks_b, truth, associate_tracks(tracks_a, tracks_b)


def test_fixed_scene_has_100_targets_4km_baseline_and_ten_crossings(
    config: ScenarioConfig,
) -> None:
    targets = generate_target_specs(config)
    assert len(targets) == 100
    assert math.isclose(
        math.dist(config.camera_a_position_ned, config.camera_b_position_ned),
        4000.0,
    )
    assert minimum_initial_separation(targets) > 100.0
    assert len(crossing_pairs(targets)) == 10
    assert all(40.0 <= target.horizontal_speed_mps <= 60.0 for target in targets)
    assert all(abs(target.velocity_ned[2]) <= 20.0 for target in targets)
    for first_id, second_id in crossing_pairs(targets):
        lookup = {target.truth_id: target for target in targets}
        assert math.dist(
            lookup[first_id].position_at(config.crossing_time_s),
            lookup[second_id].position_at(config.crossing_time_s),
        ) < 1e-6


def test_scan_schedule_contains_exactly_ten_half_sweeps(config: ScenarioConfig) -> None:
    assert config.frame_count == 500
    assert config.half_sweep_count == 10
    assert {int((index * config.dt_s) // 0.5) for index in range(config.frame_count)} == set(range(10))


def test_online_schema_rejects_actor_and_truth_fields() -> None:
    clean = {
        "detection_uid": "Optical_A-F0001-D001",
        "measurement_timestamp": 0.1,
        "arrival_timestamp": 0.11,
        "ray_x_ned": 1.0,
    }
    assert online_truth_leakage_keys([clean]) == ()
    findings = online_truth_leakage_keys([clean | {"actor_name": "hidden", "truth_id": "T1"}])
    assert len(findings) == 2


def test_scan_vote_and_final_result_are_one_to_one(synthetic_association) -> None:
    tracks_a, tracks_b, _, result = synthetic_association
    assert len(tracks_a) == len(tracks_b) == 100
    for sweep in range(10):
        selected = [item for item in result.scan_assignments if item.half_sweep_index == sweep]
        assert len({item.track_a_id for item in selected}) == len(selected)
        assert len({item.track_b_id for item in selected}) == len(selected)
    assert len({item.track_a_id for item in result.final_matches}) == len(result.final_matches)
    assert len({item.track_b_id for item in result.final_matches}) == len(result.final_matches)
    assert result.vote_matrix.shape == (100, 100)


def test_settings_and_scenario_are_dynamic_records(tmp_path: Path, config: ScenarioConfig) -> None:
    paths = prepare_case(tmp_path, config, CameraSpec())
    settings = json.loads(paths["settings"].read_text(encoding="utf-8"))
    assert settings["SimMode"] == "ComputerVision"
    assert set(settings["Vehicles"]) == {"Optical_A", "Optical_B"}
    capture = settings["CameraDefaults"]["CaptureSettings"][0]
    assert capture["Width"] == 1280
    assert capture["Height"] == 1024
    assert capture["FOV_Degrees"] == 2.93
    scenario = json.loads(paths["scenario"].read_text(encoding="utf-8"))
    assert scenario["derived"]["baseline_m"] == 4000.0
    assert scenario["derived"]["half_sweep_count"] == 10
    assert scenario["scenario"]["detection_filter_radius_cm"] == 2_000_000.0


def test_air_sim_adapter_keeps_raw_name_offline_only(tmp_path: Path, config: ScenarioConfig) -> None:
    runner = GuideCaseAirSimRunner(
        config=config,
        camera=CameraSpec(),
        output_dir=tmp_path,
        client=object(),
        airsim_module=SimpleNamespace(),
    )
    box = SimpleNamespace(
        min=SimpleNamespace(x_val=620.0, y_val=490.0),
        max=SimpleNamespace(x_val=660.0, y_val=530.0),
    )
    raw = SimpleNamespace(name="MSM_Guide_Target_001", box2D=box)
    state = CameraState(
        camera_id=config.camera_a_name,
        frame_index=0,
        timestamp=0.0,
        position_ned=config.camera_a_position_ned,
        yaw_deg=0.0,
        pitch_deg=0.0,
        half_sweep_index=0,
    )
    online, offline = runner._anonymize_detections(
        [raw],
        state,
        {"TRUTH-001": (1000.0, 0.0, -100.0)},
        measurement_timestamp=0.0,
        arrival_timestamp=0.01,
    )
    assert online_truth_leakage_keys([asdict(online[0])]) == ()
    assert offline[0]["raw_detection_name"] == "MSM_Guide_Target_001"
    assert offline[0]["offline_truth_only"] is True


def test_fixture_writes_dynamic_report_and_word(tmp_path: Path) -> None:
    result = run_synthetic_fixture(tmp_path)
    assert result.metrics["formal_airsim_result"] is False
    assert result.metrics["acceptance"]["overall_passed"] is True
    assert result.metrics["acceptance"]["formal_detection_requirement_passed"] is True
    assert result.metrics["acceptance"]["final_matches_observed"] is True
    restored = load_experiment_result(tmp_path)
    assert len(restored.tracks_a) == len(restored.tracks_b) == 100
    reports = generate_experiment_report(restored)
    report_text = reports["report"].read_text(encoding="utf-8")
    assert "100个目标" in report_text
    assert "不作为AirSim性能结论" in report_text
    assert "99.95%结果" in report_text
    image_links = [line for line in report_text.splitlines() if line.startswith("![")]
    assert len(image_links) >= 8
    output = tmp_path / "report.docx"
    word_metrics = build_document(reports["report"], output)
    assert output.is_file()
    assert word_metrics["figures"] >= 8
