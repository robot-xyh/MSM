from __future__ import annotations

import json

from d1_sensor_fusion.covariance_psd_fast_path_performance import (
    compare_covariance_psd_fast_path_variants,
    write_covariance_psd_fast_path_performance_report,
)


def test_synthetic_benchmark_is_exact_and_auditable(tmp_path) -> None:
    report = compare_covariance_psd_fast_path_variants(
        repetitions=2,
        warmup_count=1,
        matrix_count=40,
        round_count=2,
        fallback_every=10,
        seed=20260724,
    )

    assert report["comparison"]["semantic_passed"] is True
    assert (
        report["reference"]["output_sha256"]
        == report["candidate"]["output_sha256"]
    )
    assert (
        report["reference"]["reason_sha256"]
        == report["candidate"]["reason_sha256"]
    )
    counts = report["candidate"]["diagnostics"]["operation_counts"]
    assert counts == {
        "cholesky_attempt_count": 80,
        "cholesky_success_count": 72,
        "cholesky_fallback_count": 8,
    }
    assert report["input"]["online_truth_use_count"] == 0
    assert report["recommendation_policy"][
        "minimum_median_improvement_fraction"
    ] == 0.02
    assert report["reference"]["profile"]["selected_functions"][
        "eigvalsh"
    ]["primitive_call_count"] >= 80
    assert report["candidate"]["profile"]["selected_functions"][
        "cholesky"
    ]["primitive_call_count"] >= 80

    json_path = tmp_path / "benchmark.json"
    markdown_path = tmp_path / "benchmark.md"
    write_covariance_psd_fast_path_performance_report(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["comparison"]["semantic_passed"] is True
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "不是完整融合" in markdown
    assert "cProfile" in markdown
