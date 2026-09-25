from __future__ import annotations

import json
from pathlib import Path

import pytest

from center_terminal_cv_campaign.exp_search.offline_replay import (
    OfflineSearchConfig,
    build_anonymous_perfect_cues,
    build_probability_subcells,
    load_saved_actor_trajectories,
    run_offline_search,
)
from center_terminal_cv_campaign.exp_search.run_offline_matrix import aggregate_rows


def _trajectory_file(path: Path, target_count: int = 2) -> Path:
    rows = []
    for timestamp in (0.0, 0.1, 0.2):
        for index in range(target_count):
            rows.append(
                {
                    "measurement_timestamp": timestamp,
                    "actor_name": f"Actor_{index + 1}",
                    "truth_target_id": f"TGT-{index + 1:03d}",
                    "position_ned_m": [
                        2900.0 - 50.0 * timestamp,
                        -80.0 + 160.0 * index,
                        -120.0,
                    ],
                    "velocity_ned_mps": [-50.0, 0.0, 0.0],
                    "offline_truth_only": True,
                }
            )
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def test_saved_trajectory_is_interpolated_then_extrapolated(tmp_path: Path) -> None:
    path = _trajectory_file(tmp_path / "actor_motion.jsonl")
    evidence = load_saved_actor_trajectories(
        path,
        expected_target_count=2,
        extrapolate_until_s=18.0,
    )

    assert evidence.row_count == 6
    assert evidence.recorded_end_s == pytest.approx(0.2)
    assert evidence.extrapolated_after_s == pytest.approx(17.8)
    assert evidence.trajectories[0].position_at(1.0)[0] == pytest.approx(2850.0)


def test_perfect_cues_have_one_label_per_target_and_real_seeded_error(
    tmp_path: Path,
) -> None:
    evidence = load_saved_actor_trajectories(
        _trajectory_file(tmp_path / "actor_motion.jsonl"),
        expected_target_count=2,
        extrapolate_until_s=18.0,
    )
    config = OfflineSearchConfig(
        target_count=2,
        resource_count=2,
        position_sigma_m=60.0,
        seed=7,
    )
    cues, labels = build_anonymous_perfect_cues(evidence, config)

    assert len(cues) == len(labels) == 2
    assert len({label.truth_target_id for label in labels}) == 2
    assert all(max(abs(value) for value in label.injected_error_ned_m) <= 180.0 for label in labels)
    assert any(any(abs(value) > 1.0e-9 for value in label.injected_error_ned_m) for label in labels)
    assert all(cue.covariance_6x6[0][0] == pytest.approx(3600.0) for cue in cues)
    assert all("TGT-" not in json.dumps(cue.to_online_dict()) for cue in cues)


@pytest.mark.parametrize("sigma, expected_cells_per_cue", ((30.0, 2), (60.0, 8), (100.0, 24)))
def test_three_sigma_region_is_tiled_by_camera_footprint(
    tmp_path: Path,
    sigma: float,
    expected_cells_per_cue: int,
) -> None:
    evidence = load_saved_actor_trajectories(
        _trajectory_file(tmp_path / f"actor_motion_{int(sigma)}.jsonl"),
        expected_target_count=2,
        extrapolate_until_s=18.0,
    )
    config = OfflineSearchConfig(
        target_count=2,
        resource_count=2,
        position_sigma_m=sigma,
        seed=11,
    )
    cues, _ = build_anonymous_perfect_cues(evidence, config)
    cells = build_probability_subcells(cues, config)

    assert len(cells) == 2 * expected_cells_per_cue
    for cue in cues:
        mass = sum(cell.probability_mass for cell in cells if cell.source_track_id == cue.source_track_id)
        assert mass == pytest.approx(1.0)
    assert config.vertical_fov_deg == pytest.approx(10.7548386854)


def test_deadline_and_true_frustum_separate_assignment_from_observation(
    tmp_path: Path,
) -> None:
    trajectory = _trajectory_file(tmp_path / "actor_motion.jsonl")
    result = run_offline_search(
        trajectory_path=trajectory,
        config=OfflineSearchConfig(
            target_count=2,
            resource_count=1,
            position_sigma_m=100.0,
            seed=19,
            duration_s=0.2,
        ),
    )

    assert not result.assignments
    assert not result.observations
    assert result.metrics["executed_observation_task_count"] == 0
    assert result.metrics["true_frustum_covered_cell_count"] == 0
    assert result.metrics["unexecuted_task_count"] == len(result.cells)


def test_offline_search_uses_truth_only_for_observation_and_scoring(tmp_path: Path) -> None:
    result = run_offline_search(
        trajectory_path=_trajectory_file(tmp_path / "actor_motion.jsonl"),
        config=OfflineSearchConfig(
            target_count=2,
            resource_count=2,
            position_sigma_m=30.0,
            seed=23,
        ),
    )

    assert result.metrics["source_fixture_precision"] == 1.0
    assert result.metrics["source_fixture_recall"] == 1.0
    assert result.metrics["online_truth_leakage_count"] == 0
    assert result.metrics["executed_observation_task_count"] == len(result.observations)
    assert all(event.motion.completion_time_s <= 18.0 for event in result.assignments)


def test_matrix_aggregation_keeps_each_scale_and_sigma_separate() -> None:
    rows = [
        {
            "scenario_id": "n20_m8",
            "scenario_label": "20目标/8机",
            "target_count": 20,
            "resource_count": 8,
            "position_sigma_m": 30.0,
            "target_discovery_rate": value,
            "continuous_confirmation_rate": value,
            "true_frustum_probability_mass_coverage_rate": 0.5,
            "first_discovery_mean_s": 2.0,
            "first_discovery_p95_s": 3.0,
            "repeated_confirmed_observation_rate": 0.1,
            "unexecuted_task_count": 4,
            "identity_misclosed_cue_count": 0,
            "planner_compute_p95_ms": 5.0,
            "planner_compute_max_ms": 7.0,
            "online_truth_leakage_count": 0,
        }
        for value in (0.8, 1.0)
    ]
    aggregate = aggregate_rows(rows)
    assert len(aggregate) == 1
    assert aggregate[0]["seed_count"] == 2
    assert aggregate[0]["target_discovery_rate_mean"] == pytest.approx(0.9)
    assert aggregate[0]["target_discovery_rate_min"] == pytest.approx(0.8)

