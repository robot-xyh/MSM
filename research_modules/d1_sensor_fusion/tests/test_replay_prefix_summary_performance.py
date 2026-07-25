from __future__ import annotations

import json

import pytest

from d1_sensor_fusion import (
    REPLAY_PREFIX_SUMMARY_FIXTURE_SCHEMA_VERSION,
    REPLAY_PREFIX_SUMMARY_PERFORMANCE_SCHEMA_VERSION,
    benchmark_replay_prefix_summary,
    load_replay_prefix_summary_fixture,
    render_replay_prefix_summary_report_cn,
    write_replay_prefix_summary_report,
)


def test_frozen_fixture_is_exactly_200v200_and_truth_free() -> None:
    fixture = load_replay_prefix_summary_fixture()

    assert fixture["schema_version"] == (
        REPLAY_PREFIX_SUMMARY_FIXTURE_SCHEMA_VERSION
    )
    assert fixture["target_count"] == 200
    assert fixture["resource_count"] == 200
    assert fixture["recon_node_count"] == 2
    assert fixture["buffer_horizon_s"] == 6.0
    assert fixture["timed_replay_sweep_count"] == 5
    assert fixture["online_truth_use_count"] == 0
    assert fixture["source_sha256"].startswith("sha256:")


def test_development_pair_benchmark_keeps_all_semantics_exact() -> None:
    report = benchmark_replay_prefix_summary(
        paired_run_count=5,
        warmup_pair_count=0,
        development_target_count=4,
        development_replay_sweep_count=2,
    )

    assert report["schema_version"] == (
        REPLAY_PREFIX_SUMMARY_PERFORMANCE_SCHEMA_VERSION
    )
    assert report["workload"]["frozen_fixture_compliant"] is False
    assert report["acceptance"]["all_semantic_checks_passed"] is True
    assert report["acceptance"]["candidate_summary_hits_exercised"] is True
    assert report["module_microbenchmark_passed"] is False
    assert report["main_default_promotion_claimed"] is False
    assert report["airsim_or_full_stack_evidence_claimed"] is False
    for pair in report["pairs"]:
        assert pair["all_semantic_checks_passed"] is True
        assert all(pair["semantic_checks"].values())
        delta = pair["candidate"]["candidate_diagnostics_delta"]
        assert delta["operation_counts"]["summary_hit_count"] > 0
        assert delta["fallback_reasons"] == {}
        assert delta["pending_consistency_ledger_count"] == 0


def test_report_writer_preserves_json_and_chinese_scope(tmp_path) -> None:
    report = benchmark_replay_prefix_summary(
        paired_run_count=5,
        warmup_pair_count=0,
        development_target_count=2,
        development_replay_sweep_count=1,
    )
    rendered = render_replay_prefix_summary_report_cn(report)
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"
    write_replay_prefix_summary_report(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
    )

    assert "固定滞后回放前缀累计摘要微基准" in rendered
    assert "不构成主线默认晋升" in rendered
    assert "AirSim" in rendered
    assert json.loads(json_path.read_text(encoding="utf-8"))[
        "schema_version"
    ] == REPLAY_PREFIX_SUMMARY_PERFORMANCE_SCHEMA_VERSION
    assert markdown_path.read_text(encoding="utf-8") == rendered


def test_benchmark_rejects_underfilled_pair_count() -> None:
    with pytest.raises(ValueError, match="at least 5"):
        benchmark_replay_prefix_summary(
            paired_run_count=4,
            warmup_pair_count=0,
            development_target_count=2,
        )
