from __future__ import annotations

import json

from d1_sensor_fusion.cv_motion_model_cache_performance import (
    compare_cv_motion_model_cache_variants,
    write_cv_motion_model_cache_performance_report,
)


def test_cv_motion_model_cache_benchmark_is_semantically_auditable(
    tmp_path,
) -> None:
    report = compare_cv_motion_model_cache_variants(
        repetitions=2,
        state_count=20,
        step_count=8,
        dt_s=0.05,
        cache_capacity=4,
    )

    assert report["comparison"]["passed"] is True
    assert report["comparison"]["reference_model_build_count"] == 160
    assert report["comparison"]["candidate_model_build_count"] < 8
    assert (
        report["reference"]["final_state_sha256"]
        == report["candidate"]["final_state_sha256"]
    )
    assert (
        report["candidate"]["diagnostics"]["operation_counts"][
            "cache_hit_count"
        ]
        > 0
    )

    json_path = tmp_path / "benchmark.json"
    markdown_path = tmp_path / "benchmark.md"
    write_cv_motion_model_cache_performance_report(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["comparison"]["passed"] is True
    assert "系统实时准入" in markdown_path.read_text(encoding="utf-8")
