from __future__ import annotations

import math

from dual_optical_online_benchmark.contracts import CORRUPTION_LEVELS
from dual_optical_online_benchmark.report_matrix_replay import (
    ROUTES,
    TARGET_COUNTS,
    _final_rows,
    _summarize,
    _validate_matrix,
)


def _metric_row(
    *,
    seed: int,
    round_index: int,
    latency_ms: float,
    output_count: int,
    correct_count: int,
    correct_targets: int,
) -> dict[str, object]:
    deadline_met = latency_ms <= 1000.0
    return {
        "profile": "continuous_360",
        "target_count": 20,
        "seed": seed,
        "condition": "clean",
        "route_name": "gnn",
        "round_index": round_index,
        "output_match_count": output_count,
        "correct_match_count": correct_count,
        "correct_unique_target_count": correct_targets,
        "on_time_correct_unique_target_count": correct_targets if deadline_met else 0,
        "single_station_dominant_observation_count": 90,
        "single_station_labeled_observation_count": 100,
        "single_station_correct_identity_count": 36,
        "single_station_identity_opportunity_count": 40,
        "single_station_duplicate_track_count": 1,
        "single_station_mixed_track_count": 2,
        "dual_station_residual_loss_count": 3,
        "latency_ms": latency_ms,
        "timed_out": not deadline_met,
        "evidence_status": "offline_replay",
        "protocol_bridge_applied": False,
    }


def test_final_rows_select_only_latest_round() -> None:
    rows = [
        _metric_row(
            seed=1,
            round_index=1,
            latency_ms=10.0,
            output_count=1,
            correct_count=1,
            correct_targets=1,
        ),
        _metric_row(
            seed=1,
            round_index=6,
            latency_ms=50.0,
            output_count=8,
            correct_count=8,
            correct_targets=8,
        ),
    ]

    final = _final_rows(rows)

    assert len(final) == 1
    assert final[0]["round_index"] == 6
    assert final[0]["correct_unique_target_count"] == 8


def test_summary_retains_late_quality_but_not_on_time_coverage() -> None:
    rows = [
        _metric_row(
            seed=1,
            round_index=6,
            latency_ms=50.0,
            output_count=8,
            correct_count=8,
            correct_targets=8,
        ),
        _metric_row(
            seed=2,
            round_index=6,
            latency_ms=2000.0,
            output_count=10,
            correct_count=9,
            correct_targets=9,
        ),
    ]

    summary = _summarize(rows)[0]

    assert math.isclose(summary["offline_completed_precision"], 17 / 18)
    assert math.isclose(summary["offline_completed_coverage"], 17 / 40)
    assert math.isclose(summary["on_time_coverage"], 8 / 40)
    assert summary["timeout_count"] == 1
    assert summary["sample_count"] == 2


def test_validate_matrix_accepts_exact_6_plus_24_plus_24_groups() -> None:
    rows: list[dict[str, object]] = []
    for target_count in TARGET_COUNTS:
        for route_name in ROUTES:
            rows.append(
                {
                    "profile": "oracle_360",
                    "target_count": target_count,
                    "condition": "clean",
                    "route_name": route_name,
                    "sample_count": 5,
                }
            )
            for condition in CORRUPTION_LEVELS:
                for profile in ("continuous_360", "s180"):
                    rows.append(
                        {
                            "profile": profile,
                            "target_count": target_count,
                            "condition": condition,
                            "route_name": route_name,
                            "sample_count": 5,
                        }
                    )

    matrix = _validate_matrix(rows)

    assert matrix == {
        "oracle_360_group_count": 6,
        "continuous_360_group_count": 24,
        "s180_group_count": 24,
        "total_group_count": 54,
        "seed_count_per_group": 5,
        "complete": True,
    }
