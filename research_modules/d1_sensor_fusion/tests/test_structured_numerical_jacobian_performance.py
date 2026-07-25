from __future__ import annotations

import json

from d1_sensor_fusion.structured_numerical_jacobian_performance import (
    DEFAULT_BENCHMARK_CONFIG_PATH,
    compare_structured_numerical_jacobian_variants,
    write_structured_numerical_jacobian_performance_report,
)


def test_frozen_benchmark_is_exact_and_auditable(tmp_path) -> None:
    report = compare_structured_numerical_jacobian_variants(
        DEFAULT_BENCHMARK_CONFIG_PATH,
        repetitions=2,
        warmup_count=0,
        sample_count=24,
        round_count=2,
    )

    assert report["comparison"]["semantic_passed"] is True
    assert (
        report["reference"]["jacobian_sha256"]
        == report["candidate"]["jacobian_sha256"]
    )
    assert (
        report["reference"]["nis_sha256"]
        == report["candidate"]["nis_sha256"]
    )
    assert (
        report["reference"]["gate_decision_sha256"]
        == report["candidate"]["gate_decision_sha256"]
    )
    assert report["input"]["online_truth_use_count"] == 0
    assert report["configuration"]["sample_count"] == 24
    assert report["recommendation_policy"][
        "minimum_median_improvement_fraction"
    ] == 0.10
    reference_counts = report["reference"]["diagnostics"][
        "operation_counts"
    ]
    candidate_counts = report["candidate"]["diagnostics"][
        "operation_counts"
    ]
    assert reference_counts["jacobian_attempt_count"] == 48
    assert candidate_counts["jacobian_attempt_count"] == 48
    assert reference_counts["output_probe_evaluation_count"] == 48
    assert candidate_counts["output_probe_elision_count"] == 48
    assert (
        candidate_counts["measurement_function_evaluation_count"]
        < reference_counts["measurement_function_evaluation_count"]
    )

    json_path = tmp_path / "benchmark.json"
    markdown_path = tmp_path / "benchmark.md"
    write_structured_numerical_jacobian_performance_report(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["comparison"]["semantic_passed"] is True
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "不是完整融合" in markdown
    assert "结构稀疏数值雅可比" in markdown
    stale_disposition = "保留为待 " + "main 全栈准入"
    assert stale_disposition not in markdown
    assert "scalable 3D 正式矩阵已准入" in markdown
    assert (
        "main 默认已晋级为 `known_dimension_structural_columns_v1`"
        in markdown
    )
    assert (
        "D1 独立 `FusionAdapter` 构造默认仍为 "
        "`structured_numerical_jacobian=False`"
        in markdown
    )
