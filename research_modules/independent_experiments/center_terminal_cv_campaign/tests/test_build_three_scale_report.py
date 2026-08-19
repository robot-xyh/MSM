from __future__ import annotations

import json

import pytest

from center_terminal_cv_campaign.build_three_scale_report import (
    RUN_SPECS,
    camera_pair_count,
    fixture_counts,
    index_benchmark_results,
    load_benchmark,
)


def test_exact_eighty_percent_fixture_counts() -> None:
    assert fixture_counts(20) == {
        "true_cues": 16,
        "false_cues": 4,
        "missed_targets": 4,
        "all_cues": 20,
        "gap_cells": 8,
    }
    assert fixture_counts(40) == {
        "true_cues": 32,
        "false_cues": 8,
        "missed_targets": 8,
        "all_cues": 40,
        "gap_cells": 16,
    }


def test_camera_pair_growth() -> None:
    assert camera_pair_count(8) == 28
    assert camera_pair_count(30) == 435
    assert camera_pair_count(50) == 1225


def test_benchmark_result_index_rejects_duplicate_keys() -> None:
    record = {
        "scenario_id": "n20_m8",
        "task": "crossview",
        "camera_pair_policy": "sector_fov",
        "backend": "geometry",
    }
    with pytest.raises(ValueError, match="duplicate benchmark result"):
        index_benchmark_results((record, dict(record)))


def test_load_complete_benchmark(tmp_path) -> None:
    results = []
    for spec in RUN_SPECS:
        for backend in ("geometry", "gnn"):
            results.append(
                {
                    "scenario_id": spec.scenario_id,
                    "task": "center_handover",
                    "backend": backend,
                    "metrics": {"truth_leakage_count": 0},
                }
            )
            for policy in ("full", "sector_fov"):
                results.append(
                    {
                        "scenario_id": spec.scenario_id,
                        "task": "crossview",
                        "camera_pair_policy": policy,
                        "backend": backend,
                        "metrics": {"truth_leakage_count": 0},
                    }
                )
    path = tmp_path / "benchmark_summary.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "center-terminal-gnn-offline-benchmark-v1",
                "held_out_seed": 20260816,
                "results": results,
            }
        ),
        encoding="utf-8",
    )

    benchmark = load_benchmark(path)

    assert len(benchmark.results) == 18
    assert benchmark.result(
        "n40_m50", "crossview", "gnn", "sector_fov"
    )["metrics"]["truth_leakage_count"] == 0
