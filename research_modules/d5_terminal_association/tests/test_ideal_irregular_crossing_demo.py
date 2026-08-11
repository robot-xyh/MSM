from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from d5_terminal_association.ideal_irregular_crossing_demo import (
    IrregularCrossingConfig,
    evaluate_irregular_crossing,
    run_irregular_crossing_experiment,
    run_irregular_seed_batch,
)
from d5_terminal_association.ideal_irregular_crossing_reporting import (
    FIGURE_FILES,
    write_irregular_crossing_artifacts,
)


def test_standard_geometry_is_irregular_separated_and_crossing() -> None:
    online_run, _ = run_irregular_crossing_experiment(
        modes=("coverage_safe",)
    )
    geometry = online_run.geometry

    assert geometry.initial_radial_span_m >= 300.0
    assert geometry.initial_altitude_span_m > 25.0
    assert geometry.minimum_pairwise_3d_separation_m >= 25.0
    assert len(geometry.projected_crossing_pairs_a) >= 6
    assert len(geometry.projected_crossing_pairs_b) >= 6
    initial_positions = geometry.target_state_history_ned[0, :, :3]
    centered = initial_positions - np.mean(initial_positions, axis=0)
    assert np.linalg.matrix_rank(centered) == 3
    trailing_distance = np.linalg.norm(
        geometry.camera_b_position_history_ned
        - np.mean(geometry.target_state_history_ned[:, :, :3], axis=1),
        axis=1,
    )
    assert np.all((trailing_distance >= 450.0) & (trailing_distance <= 650.0))
    assert np.allclose(trailing_distance, 500.0)


def test_camera_intrinsics_and_scan_rates_match_configuration() -> None:
    config = IrregularCrossingConfig()
    online_run, _ = run_irregular_crossing_experiment(
        config, modes=("coverage_safe",)
    )

    assert online_run.camera_a_intrinsics.width_px == 2600
    assert online_run.camera_a_intrinsics.height_px == 2160
    assert online_run.camera_b_intrinsics.width_px == 1920
    assert online_run.camera_b_intrinsics.height_px == 1080
    assert np.isclose(
        np.deg2rad(config.camera_a_horizontal_fov_deg) / config.camera_a_width_px,
        4.17e-6,
        rtol=0.01,
    )
    assert np.isclose(
        np.deg2rad(config.camera_b_horizontal_fov_deg) / config.camera_b_width_px,
        25.0e-6,
        rtol=0.01,
    )
    assert np.isclose(config.confirmation_dwell_time_s, 0.05)
    assert np.isclose(config.mechanical_scan_speed_deg_s * config.scan_dt_s, 1.8)
    assert np.isclose(config.coverage_safe_scan_speed_deg_s * config.scan_dt_s, 0.4968)


def test_standard_modes_report_actual_mechanical_gap_and_safe_completion() -> None:
    online_run, offline_truth = run_irregular_crossing_experiment()
    metrics = {metric.mode: metric for metric in evaluate_irregular_crossing(online_run, offline_truth)}
    mechanical = metrics["mechanical_2s"]
    coverage_safe = metrics["coverage_safe"]

    assert mechanical.center_discovery_ratio < 1.0
    assert mechanical.complete_chain_ratio < 1.0
    assert mechanical.scan_actual_duration_s == 15.0
    assert coverage_safe.center_discovery_ratio == 1.0
    assert coverage_safe.camera_b_cued_observation_ratio == 1.0
    assert coverage_safe.complete_chain_ratio == 1.0
    assert coverage_safe.stage_a_association_accuracy == 1.0
    assert coverage_safe.stage_b_association_accuracy == 1.0
    assert coverage_safe.end_to_end_association_accuracy == 1.0
    assert coverage_safe.id_switch_count == 0
    assert coverage_safe.duplicate_assignment_count == 0
    assert coverage_safe.unmatched_count == 0
    assert coverage_safe.online_truth_usage_count == 0
    assert coverage_safe.global_track_id_rewrite_count == 0
    assert coverage_safe.coverage_safe_acceptance_passed()


def test_scan_records_keep_dual_timestamps_covariance_and_center_ids_read_only() -> None:
    online_run, offline_truth = run_irregular_crossing_experiment()
    safe = online_run.mode("coverage_safe")

    assert len(safe.timeline) == 1501
    assert online_run.center_global_track_ids_before == online_run.center_global_track_ids_after
    assert offline_truth.global_to_camera_a
    for record in safe.timeline:
        assert record.measurement_timestamp == record.arrival_timestamp
    assert safe.observations
    for observation in safe.observations:
        assert observation.measurement_timestamp == observation.arrival_timestamp
        assert observation.covariance_px.shape == (2, 2)
        assert np.allclose(np.diag(observation.covariance_px), 1.0e-6)
        assert "GT-" not in observation.local_track_id
    for event in (*safe.stage_a_events, *safe.stage_b_events):
        assert event.measurement_timestamp == event.arrival_timestamp
        assert event.cost.window_frame_count == 5
        assert all(np.isclose(value, 0.0) for value in event.selected_costs)


def test_target_count_is_parameterized() -> None:
    config = IrregularCrossingConfig(target_count=6, duration_s=3.0)
    online_run, offline_truth = run_irregular_crossing_experiment(config)
    metrics = {metric.mode: metric for metric in evaluate_irregular_crossing(online_run, offline_truth)}

    assert len(online_run.geometry.global_track_ids) == 6
    assert online_run.geometry.target_state_history_ned.shape[1] == 6
    assert metrics["coverage_safe"].target_count == 6
    assert metrics["coverage_safe"].coverage_safe_acceptance_passed()


def test_ten_seed_coverage_safe_acceptance() -> None:
    metrics = run_irregular_seed_batch(range(20260810, 20260820))

    assert len(metrics) == 10
    for metric in metrics:
        assert metric.center_discovery_ratio == 1.0
        assert metric.camera_b_cued_observation_ratio == 1.0
        assert metric.complete_chain_ratio == 1.0
        assert metric.stage_a_association_accuracy == 1.0
        assert metric.stage_b_association_accuracy == 1.0
        assert metric.id_switch_count == 0
        assert metric.duplicate_assignment_count == 0
        assert metric.online_truth_usage_count == 0
        assert metric.global_track_id_rewrite_count == 0
        assert metric.coverage_safe_acceptance_passed()


def test_output_manifest_and_media_are_generated(tmp_path: Path) -> None:
    config = IrregularCrossingConfig(target_count=6, duration_s=3.0)
    online_run, offline_truth = run_irregular_crossing_experiment(config)
    standard_metrics = evaluate_irregular_crossing(online_run, offline_truth)
    safe_metric = next(
        metric for metric in standard_metrics if metric.mode == "coverage_safe"
    )
    written = write_irregular_crossing_artifacts(
        online_run,
        offline_truth,
        standard_metrics,
        (safe_metric,),
        tmp_path,
        generate_media=True,
    )
    names = {path.name for path in written}
    assert {
        "scenario.json",
        "metrics.json",
        "global_tracks.csv",
        "mechanical_2s_scan_timeline.csv",
        "coverage_safe_scan_timeline.csv",
        "association_event_costs.csv",
        "assignments.csv",
        "offline_truth.csv",
        "scan_registration_process.gif",
        "D5_IDEAL_IRREGULAR_CROSSING_SCAN_REPORT_CN.md",
    } <= names
    for file_name in FIGURE_FILES:
        path = tmp_path / file_name
        assert path.is_file()
        assert path.stat().st_size > 1_000
    gif = tmp_path / "scan_registration_process.gif"
    assert gif.stat().st_size > 1_000
    payload = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert payload["coverage_safe_batch"]["all_seeds_passed"] is True
