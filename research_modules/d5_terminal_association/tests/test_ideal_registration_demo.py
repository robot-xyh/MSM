from __future__ import annotations

import csv
import json
from dataclasses import fields
from pathlib import Path

import numpy as np

from d5_terminal_association.ideal_registration_demo import (
    FORBIDDEN_ONLINE_IDENTITY_TOKENS,
    IdealRegistrationConfig,
    assert_online_run_truth_free,
    build_temporal_cost_matrix,
    evaluate_ideal_registration,
    run_ideal_registration,
    run_seed_batch,
)
from d5_terminal_association.ideal_registration_reporting import (
    FIGURE_FILES,
    write_ideal_registration_artifacts,
)


def _config(**overrides: object) -> IdealRegistrationConfig:
    payload: dict[str, object] = {
        "target_count": 7,
        "seed": 1234,
        "duration_s": 1.0,
        "physics_dt_s": 0.1,
        "image_period_s": 0.2,
    }
    payload.update(overrides)
    return IdealRegistrationConfig(**payload)


def test_parameterized_episode_is_deterministic() -> None:
    first_run, first_truth = run_ideal_registration(_config())
    second_run, second_truth = run_ideal_registration(_config())

    assert first_run.config.target_count == 7
    assert len(first_run.frames) == 6
    assert len(first_run.frames[0].global_track_ids) == 7
    assert first_truth == second_truth
    for first, second in zip(first_run.frames, second_run.frames, strict=True):
        assert np.array_equal(first.global_states_ned, second.global_states_ned)
        assert np.array_equal(first.camera_a_local_pixels, second.camera_a_local_pixels)
        assert np.array_equal(first.camera_b_local_pixels, second.camera_b_local_pixels)
    assert first_run.associations[-1].global_camera_a_to_camera_b == (
        second_run.associations[-1].global_camera_a_to_camera_b
    )


def test_temporal_cost_uses_position_then_displacement() -> None:
    projected = [
        np.array([[0.0, 0.0], [100.0, 0.0]]),
        np.array([[2.0, 0.0], [104.0, 0.0]]),
    ]
    anonymous = [
        np.array([[100.0, 0.0], [0.0, 0.0]]),
        np.array([[104.0, 0.0], [2.0, 0.0]]),
    ]
    first = build_temporal_cost_matrix(
        projected[:1],
        anonymous[:1],
        window_frames=5,
        position_scale_px=20.0,
        displacement_scale_px=10.0,
        displacement_weight=0.25,
    )
    second = build_temporal_cost_matrix(
        projected,
        anonymous,
        window_frames=5,
        position_scale_px=20.0,
        displacement_scale_px=10.0,
        displacement_weight=0.25,
    )

    assert np.all(first.displacement_cost == 0.0)
    assert first.window_frame_count == 1
    assert second.window_frame_count == 2
    assert second.total_cost[0, 1] == 0.0
    assert second.total_cost[1, 0] == 0.0
    assert second.displacement_cost[0, 0] > 0.0


def test_online_schema_is_truth_free_and_global_ids_are_unchanged() -> None:
    online_run, offline_truth = run_ideal_registration(_config())
    assert_online_run_truth_free(online_run)

    online_field_names = {
        field.name.lower()
        for value in (online_run, *online_run.frames, *online_run.associations)
        for field in fields(value)
    }
    assert not {
        name
        for name in online_field_names
        if any(token in name for token in FORBIDDEN_ONLINE_IDENTITY_TOKENS)
    }
    assert offline_truth.global_to_camera_a
    assert online_run.center_global_track_ids_before == online_run.center_global_track_ids_after
    metrics = evaluate_ideal_registration(online_run, offline_truth)
    assert metrics.online_truth_usage_count == 0
    assert metrics.global_track_id_rewrite_count == 0


def test_dual_timestamps_covariance_and_complete_chain() -> None:
    online_run, offline_truth = run_ideal_registration(_config(target_count=9))
    for frame in online_run.frames:
        assert frame.measurement_timestamp == frame.arrival_timestamp
        assert frame.global_covariances.shape == (9, 6, 6)
        assert frame.camera_a_local_covariances.shape == (9, 2, 2)
        assert frame.camera_b_local_covariances.shape == (9, 2, 2)
        assert np.allclose(np.diagonal(frame.global_covariances, axis1=1, axis2=2), 1.0e-6)
        assert np.allclose(np.diagonal(frame.camera_a_local_covariances, axis1=1, axis2=2), 1.0e-6)
    metrics = evaluate_ideal_registration(online_run, offline_truth)
    assert metrics.acceptance_passed()


def test_default_ten_seed_acceptance() -> None:
    metrics = run_seed_batch(range(20260810, 20260820))
    assert len(metrics) == 10
    for result in metrics:
        assert result.camera_a_accuracy == 1.0
        assert result.camera_b_accuracy == 1.0
        assert result.end_to_end_accuracy == 1.0
        assert result.id_switch_count == 0
        assert result.duplicate_assignment_count == 0
        assert result.unmatched_count == 0
        assert result.complete_chain_ratio == 1.0
        assert result.online_truth_usage_count == 0
        assert result.global_track_id_rewrite_count == 0
        assert result.full_visibility_rate == 1.0
        assert result.acceptance_passed()


def test_csv_json_outputs_keep_truth_in_offline_sidecar(tmp_path: Path) -> None:
    online_run, offline_truth = run_ideal_registration(_config())
    metric = evaluate_ideal_registration(online_run, offline_truth)
    written = write_ideal_registration_artifacts(
        online_run,
        offline_truth,
        (metric,),
        tmp_path,
        generate_media=False,
    )
    written_names = {path.name for path in written}
    assert {
        "scenario.json",
        "global_tracks.csv",
        "camera_a_anonymous_tracks.csv",
        "camera_b_anonymous_tracks.csv",
        "stage_a_costs.csv",
        "stage_b_costs.csv",
        "assignments.csv",
        "offline_truth.csv",
        "metrics.json",
        "D5_IDEAL_20_TARGET_TWO_STAGE_REGISTRATION_CN.md",
    } <= written_names
    for file_name in (
        "camera_a_anonymous_tracks.csv",
        "camera_b_anonymous_tracks.csv",
        "assignments.csv",
    ):
        header = next(csv.reader((tmp_path / file_name).open(encoding="utf-8")))
        assert not any("truth" in value.lower() for value in header)
    offline_header = next(
        csv.reader((tmp_path / "offline_truth.csv").open(encoding="utf-8"))
    )
    assert "usage_scope" in offline_header
    metrics_payload = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert metrics_payload["aggregate"]["all_seeds_passed"] is True


def test_small_media_output_contains_thirteen_figures_and_gif(tmp_path: Path) -> None:
    online_run, offline_truth = run_ideal_registration(
        _config(target_count=4, duration_s=0.4)
    )
    metric = evaluate_ideal_registration(online_run, offline_truth)
    write_ideal_registration_artifacts(
        online_run,
        offline_truth,
        (metric,),
        tmp_path,
        generate_media=True,
    )

    for file_name in FIGURE_FILES:
        path = tmp_path / file_name
        assert path.is_file()
        assert path.stat().st_size > 1_000
    gif_path = tmp_path / "registration_process.gif"
    assert gif_path.is_file()
    assert gif_path.stat().st_size > 1_000
