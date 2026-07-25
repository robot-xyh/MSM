from __future__ import annotations

import json

import pytest

from d1_sensor_fusion.opaque_source_identity_cache_performance import (
    MINIMUM_CANDIDATE_FASTER_FRACTION,
    MINIMUM_MEDIAN_IMPROVEMENT_FRACTION,
    compare_opaque_source_identity_cache_variants,
    write_opaque_source_identity_cache_report,
)


def test_interleaved_microbenchmark_is_semantically_auditable(
    tmp_path,
) -> None:
    report = compare_opaque_source_identity_cache_variants(
        repetitions=7,
        track_count=16,
        releases_per_sample=2,
        cache_capacity=16,
    )

    assert report["configuration"]["repetitions"] == 7
    assert report["configuration"]["warmup_count_per_variant"] == 1
    assert report["configuration"]["interleaved_order"] is True
    assert report["configuration"]["publish_opaque_source_key"] is True
    assert (
        report["configuration"][
            "radar_assignment_ambiguity_hold_evidence"
        ]
        is False
    )
    assert all(
        report["comparison"]["semantic_acceptance"].values()
    )
    assert (
        report["preregistered_policy"][
            "minimum_median_improvement_fraction"
        ]
        == MINIMUM_MEDIAN_IMPROVEMENT_FRACTION
    )
    assert (
        report["preregistered_policy"][
            "minimum_candidate_faster_fraction"
        ]
        == MINIMUM_CANDIDATE_FASTER_FRACTION
    )
    assert report["comparison"]["recommend_default_promotion"] is False
    assert report["constraints"]["online_truth_use_count"] == 0
    assert report["constraints"]["no_source_default_path_claimed"] is False
    assert report["constraints"]["system_realtime_claimed"] is False

    json_path = tmp_path / "benchmark.json"
    markdown_path = tmp_path / "benchmark.md"
    write_opaque_source_identity_cache_report(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["comparison"]["semantic_acceptance"] == (
        report["comparison"]["semantic_acceptance"]
    )
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "source-only" in markdown
    assert "默认 R0 主线收益" in markdown
    assert "系统实时准入" in markdown


def test_microbenchmark_rejects_non_preregistered_sample_count() -> None:
    with pytest.raises(ValueError, match="at least 7"):
        compare_opaque_source_identity_cache_variants(
            repetitions=6,
            track_count=8,
            releases_per_sample=1,
            cache_capacity=8,
        )


def test_microbenchmark_requires_non_thrashing_admission_capacity() -> None:
    with pytest.raises(ValueError, match="cover track_count"):
        compare_opaque_source_identity_cache_variants(
            repetitions=7,
            track_count=8,
            releases_per_sample=1,
            cache_capacity=7,
        )
