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
from d1_sensor_fusion.fusion import (
    REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR,
    REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR,
)
from d1_sensor_fusion.replay_prefix_summary_performance import (
    _build_workload,
    _run_fresh_variant,
    _semantic_equivalence_checks,
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
    assert (
        report["acceptance"][
            "append_only_compression_at_least_20_percent"
        ]
        is True
    )
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


def test_frozen_200v200_append_only_setup_compresses_and_stays_exact() -> None:
    fixture = load_replay_prefix_summary_fixture()
    workload = _build_workload(
        fixture,
        target_count=fixture["target_count"],
    )
    reference = _run_fresh_variant(
        workload,
        fixture,
        selector=REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR,
        replay_sweep_count=fixture["timed_replay_sweep_count"],
    )
    candidate = _run_fresh_variant(
        workload,
        fixture,
        selector=REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR,
        replay_sweep_count=fixture["timed_replay_sweep_count"],
    )

    assert all(_semantic_equivalence_checks(reference, candidate).values())
    diagnostics = candidate["setup_append_only_diagnostics"]
    assert diagnostics["revision_advance_count"] == 1400
    assert diagnostics["pending_preservation_count"] == 1200
    assert diagnostics["pending_preserved_record_count"] == 5200
    assert diagnostics["logical_refresh_record_count"] == 5200
    assert diagnostics["materialized_record_count"] == 2400
    assert diagnostics["materialized_record_compression_fraction"] == (
        pytest.approx(0.5384615384615384)
    )
    assert diagnostics["append_materialization_count"] == 0
    assert diagnostics["all_summaries_bind_latest_revision"] is True
    assert diagnostics["online_snapshot_count"] == 8
    assert diagnostics["online_snapshot_pending_preservation_count"] == 4
    assert diagnostics["online_snapshot_pending_violation_count"] == 0
    assert diagnostics["public_snapshot_projection_count"] == 4
    assert diagnostics["public_snapshot_projected_ledger_count"] == 800
    assert diagnostics["public_snapshot_projected_event_count"] == 2000
    assert diagnostics["public_snapshot_projected_record_count"] == 2800
    assert diagnostics["public_snapshot_materialization_count"] == 0
    assert diagnostics["materialization_reasons"] == {
        "fixed_lag_rebase": 200,
        "summary_fallback": 200,
    }


def test_frozen_200v200_short_snapshot_workload_exceeds_compression_gate() -> None:
    fixture = load_replay_prefix_summary_fixture()
    workload = _build_workload(
        fixture,
        target_count=fixture["target_count"],
    )[:3]
    reference = _run_fresh_variant(
        workload,
        fixture,
        selector=REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR,
        replay_sweep_count=2,
    )
    candidate = _run_fresh_variant(
        workload,
        fixture,
        selector=REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR,
        replay_sweep_count=2,
    )

    assert all(_semantic_equivalence_checks(reference, candidate).values())
    diagnostics = candidate["setup_append_only_diagnostics"]
    assert diagnostics["scan_count"] == 3
    assert diagnostics["online_snapshot_count"] == 3
    assert diagnostics["online_snapshot_pending_preservation_count"] == 1
    assert diagnostics["online_snapshot_pending_violation_count"] == 0
    assert diagnostics["logical_refresh_record_count"] == 400
    assert diagnostics["materialized_record_count"] == 0
    assert diagnostics["materialized_record_compression_fraction"] == 1.0
    assert diagnostics["materialized_record_compression_fraction"] >= 0.2
    assert diagnostics["public_snapshot_projection_count"] == 1
    assert diagnostics["public_snapshot_projected_ledger_count"] == 200
    assert diagnostics["public_snapshot_projected_event_count"] == 200
    assert diagnostics["public_snapshot_projected_record_count"] == 400
    assert diagnostics["public_snapshot_materialization_count"] == 0
    assert (
        candidate["candidate_diagnostics_delta"][
            "pending_consistency_ledger_count"
        ]
        == 0
    )


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
    assert "append-only" in rendered
    assert "精确非破坏性一致性证据快照" in rendered
    assert "consistency_evidence_snapshot" in rendered
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
