from __future__ import annotations

import json

from research_modules.scalable_3d_simulation.observation_governance_calibration import (
    run_observation_governance_calibration,
)


def test_fast_governance_calibration_writes_hash_verified_d6_bundle(tmp_path) -> None:
    paths = run_observation_governance_calibration(
        tmp_path,
        scales=(3, 5),
        seeds_per_scale=1,
        seed_base=7_000,
        frame_count=12,
        dt_seconds=0.25,
        retention_seconds=1.0,
        max_lateness_seconds=0.5,
        bootstrap_resamples=25,
    )

    assert all(path.is_file() for path in paths.values())
    summary = json.loads(paths["runner_summary"].read_text(encoding="utf-8"))
    aggregate = json.loads(paths["d6_aggregate_json"].read_text(encoding="utf-8"))
    assert summary["evidence_layer"] == "fast_3d_governance_benchmark"
    assert summary["full_system_evidence"] is False
    assert summary["episode_count"] == 2
    assert summary["online_truth_use_count"] == 0
    assert aggregate["episode_count"] == 2
    assert [item["scale"] for item in aggregate["scales"]] == [3, 5]
    assert aggregate["truth_isolation"]["online_truth_use_count"] == 0
    assert all(
        row["d2_peak_claim_count"] <= row["d2_claim_capacity"]
        for row in summary["episodes"]
    )
