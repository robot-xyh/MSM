from __future__ import annotations

from d1_sensor_fusion import (
    ASSOCIATION_SPARSE_PREFILTER_MODALITY_BUCKETS,
    ASSOCIATION_SPARSE_PREFILTER_PERFORMANCE_SCHEMA_VERSION,
    benchmark_association_sparse_prefilter,
    render_association_sparse_prefilter_report_cn,
)


def test_sparse_prefilter_microbenchmark_reports_equivalence_and_reductions() -> None:
    report = benchmark_association_sparse_prefilter(
        target_count=12,
        repeat_count=1,
        warmup_count=0,
    )

    assert report["schema_version"] == (
        ASSOCIATION_SPARSE_PREFILTER_PERFORMANCE_SCHEMA_VERSION
    )
    assert report["protocol"]["candidate_pair_count_per_modality"] == 144
    assert report["protocol"]["diagnostic_modality_buckets"] == (
        ASSOCIATION_SPARSE_PREFILTER_MODALITY_BUCKETS
    )
    assert report["protocol"]["other_bucket_benchmark_status"] == (
        "not_applicable_public_contract_rejects_unknown_modalities"
    )
    assert report["acceptance"]["all_modalities_semantically_equivalent"] is True
    assert report["acceptance"]["all_operation_counts_stable"] is True
    assert report["acceptance"]["all_exact_gate_pass_counts_equal"] is True
    assert (
        report["acceptance"]["all_non_radar_modalities_reduce_exact_solves"]
        is True
    )
    for modality in ("radar", "lidar", "acoustic", "acoustic_3d", "eo"):
        item = report["modalities"][modality]
        assert item["semantic_equivalence"] is True
        assert item["exact_gate_pass_equivalence"] is True
        assert item["operation_counts_stable"] is True
        assert item["comparison"]["candidate_pair_count"] == 144
        assert item["reference"]["modality_counts"]["exact_gate_pass_count"] == (
            item["candidate"]["modality_counts"]["exact_gate_pass_count"]
        )
    assert (
        report["modalities"]["radar"]["comparison"][
            "exact_solve_reduction_count"
        ]
        == 0
    )
    for modality in ("lidar", "acoustic", "acoustic_3d", "eo"):
        assert (
            report["modalities"][modality]["comparison"][
                "exact_solve_reduction_count"
            ]
            > 0
        )

    rendered = render_association_sparse_prefilter_report_cn(report)
    assert "D1 模态感知保守稀疏预筛微基准" in rendered
    assert "建议 main 进入正式 A/B" in rendered
    assert "不代表完整 200v200 实时倍率" in rendered
