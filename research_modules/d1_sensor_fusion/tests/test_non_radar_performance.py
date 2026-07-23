from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import d1_sensor_fusion.non_radar_performance as performance_module
from d1_sensor_fusion.non_radar_performance import (
    NON_RADAR_INNOVATION_PERFORMANCE_SCHEMA_VERSION,
    _release_group_prefix,
    benchmark_batched_non_radar_innovation,
    render_non_radar_innovation_benchmark_cn,
)


def test_release_group_prefix_preserves_order_and_exact_limit() -> None:
    groups = (
        (
            SimpleNamespace(scan_id="scan-001"),
            SimpleNamespace(scan_id="scan-002"),
        ),
        (SimpleNamespace(scan_id="scan-003"),),
    )

    selected = _release_group_prefix(groups, 2)

    assert sum(len(group) for group in selected) == 2
    assert [
        scan.scan_id
        for group in selected
        for scan in group
    ] == [
        scan.scan_id
        for group in groups
        for scan in group
    ][:2]


def test_non_radar_benchmark_reports_same_process_equivalence() -> None:
    groups = (
        (
            SimpleNamespace(scan_id="scan-001", observations=(1, 2)),
            SimpleNamespace(scan_id="scan-002", observations=(3,)),
        ),
    )
    input_summary = {
        "source_path": "frozen.jsonl",
        "source_sha256": "sha256:fixture",
        "online_truth_use_count": 0,
    }

    def fake_run(_groups, *, batched, variant):
        return {
            "variant": variant,
            "process_wall_time_s": 0.8 if batched else 1.0,
            "per_scan_semantic_digests_sha256": "sha256:scan",
            "final_tracks_sha256": "sha256:tracks",
            "consistency_evidence_sha256": "sha256:evidence",
            "operation_totals": {"candidate_count": 7},
            "cumulative_diagnostics": {"batch_count": 2},
            "track_count": 2,
            "materialized_snapshot_count": 2,
            "state_only_scan_count": 0,
        }

    with (
        patch.object(
            performance_module,
            "load_frozen_sensor_scan_release_groups",
            return_value=(groups, input_summary),
        ),
        patch.object(
            performance_module,
            "_run_variant",
            side_effect=fake_run,
        ),
    ):
        report = benchmark_batched_non_radar_innovation(
            "frozen.jsonl",
            repeat_count=2,
            warmup_count=1,
            warmup_scan_count=1,
        )
    rendered = render_non_radar_innovation_benchmark_cn(report)

    assert report["schema_version"] == (
        NON_RADAR_INNOVATION_PERFORMANCE_SCHEMA_VERSION
    )
    assert report["protocol"]["same_process"] is True
    assert report["protocol"]["repeat_count_per_variant"] == 2
    assert all(report["comparison"]["semantic_equivalence"].values())
    assert report["comparison"]["passed"] is True
    assert report["input"]["online_truth_use_count"] == 0
    assert "# D1 非雷达创新批处理性能基准" in rendered
