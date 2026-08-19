from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from dual_optical_online_benchmark.analysis import generate_diagnostics
from dual_optical_online_benchmark.contracts import (
    RevolutionSnapshot,
    benchmark_protocol_for_target_count,
    write_json,
    write_snapshot,
)
from dual_optical_online_benchmark.reporting import ROUTE_LABELS, generate_report


ROUTES = ("epipolar_mht", "lightweight", "gnn", "track_superglue")


def _aggregate() -> dict[str, float | int]:
    return {
        "publication_count": 4,
        "availability_rate": 1.0,
        "deadline_met_rate": 1.0,
        "macro_precision": 0.8,
        "macro_recall": 0.6,
        "macro_on_time_recall": 0.6,
        "macro_f1": 0.68,
        "mean_candidate_true_retention_rate": 0.9,
        "false_association_count": 1,
        "duplicate_identity_match_count": 0,
        "latency_p50_ms": 10.0,
        "latency_p95_ms": 15.0,
        "stage_latency_p95_ms": {},
    }


def _build_fixture(tmp_path: Path, active_routes: tuple[str, ...]) -> Path:
    protocol = benchmark_protocol_for_target_count(20)
    tier_root = tmp_path / "targets_020"
    dataset_root = tier_root / "dataset"
    results_root = tier_root / "results"
    preflight_root = tier_root / "preflight"

    entries = []
    for level in protocol.corruption_levels:
        for revolution in range(1, protocol.revolution_count + 1):
            snapshot = RevolutionSnapshot(
                protocol_fingerprint=protocol.fingerprint,
                seed=protocol.test_seeds[0],
                split="test",
                corruption_level=level,
                revolution_index=revolution,
                cutoff_timestamp=2.0 * revolution,
                camera_ids=("Optical_A", "Optical_B"),
                camera_positions_ned={
                    "Optical_A": (0.0, -1000.0, -100.0),
                    "Optical_B": (0.0, 1000.0, -100.0),
                },
                focal_length_px=24999.0,
                tracks={"Optical_A": (), "Optical_B": ()},
                target_count=protocol.target_count,
                tracker_fingerprint="test-tracker",
            )
            snapshot_path = (
                dataset_root / "snapshots" / level
                / f"revolution_{revolution:02d}.json"
            )
            label_path = (
                dataset_root / "labels" / level
                / f"revolution_{revolution:02d}.json"
            )
            write_snapshot(snapshot_path, snapshot)
            write_json(label_path, {"track_truth_counts": {}})
            entries.append({
                "snapshot_path": str(snapshot_path.relative_to(dataset_root)),
                "label_path": str(label_path.relative_to(dataset_root)),
            })
    manifest_path = dataset_root / "test_manifest.json"
    write_json(manifest_path, {"entries": entries})

    write_json(
        preflight_root / "preflight_summary.json",
        {
            "acceptance": {
                "by_scenario": {
                    scenario: {
                        "mean_common_confirmed_rate": rate,
                        "median_track_purity": 1.0,
                    }
                    for scenario, rate in (
                        ("ideal", 1.0),
                        ("pose_error", 0.95),
                        ("full_interference", 0.9),
                    )
                }
            }
        },
    )
    tracker_freeze_path = dataset_root / "freezes" / "shared_tracker.json"
    write_json(
        tracker_freeze_path,
        {
            "tracker_config": {
                "motion_initialization_residual_gate_m": 3.0,
                "maximum_global_hypotheses": 1,
                "chi2_confidence": 0.995,
                "process_noise_deg_s2": 0.2,
            },
            "validation_metrics": {
                "median_track_purity": 1.0,
                "by_corruption_level": {
                    level: {"mean_common_confirmed_rate": 0.9}
                    for level in protocol.corruption_levels
                },
            },
        },
    )

    eliminated = {
        route: {
            "status": "eliminated_on_main_validation_gate",
            "reason_code": "conditional_precision_floor_not_met",
            "failure_evidence": f"/must/not/be/read/{route}.json",
        }
        for route in ROUTES
        if route not in active_routes
    }
    freeze_marker_path = dataset_root / "freezes" / "all_routes_frozen.json"
    write_json(
        freeze_marker_path,
        {
            "schema_version": "dual-optical-all-routes-freeze-v4",
            "tracker_freeze": str(tracker_freeze_path),
            "active_routes": list(active_routes),
            "eliminated_routes": eliminated,
            "routes": {
                route: {
                    "validation_acceptance": {
                        "validation_f1": 0.7,
                        "validation_correct_association_count": 10,
                        "validation_selected_count": 12,
                    }
                }
                for route in active_routes
            },
        },
    )

    rows = []
    for route in active_routes:
        for level in protocol.corruption_levels:
            rows.append({
                "route_name": route,
                "corruption_level": level,
                "availability": "available",
                "deadline_met": True,
                "match_count": 12,
                "correct_match_count": 10,
                "f1": 0.68,
            })
    metrics_path = results_root / "comparison_metrics.json"
    write_json(
        metrics_path,
        {
            "protocol": asdict(protocol),
            "test_manifest": str(manifest_path),
            "freeze_marker": str(freeze_marker_path),
            "active_routes": list(active_routes),
            "rows": rows,
            "aggregate": {
                "routes": {route: _aggregate() for route in active_routes}
            },
            "shared_input_checks": [{"all_equal": True}],
        },
    )
    return metrics_path


@pytest.mark.parametrize(
    "active_routes",
    [
        ("gnn",),
        ("epipolar_mht", "gnn"),
        ROUTES,
    ],
)
def test_diagnostics_and_report_support_dynamic_routes(
    tmp_path: Path,
    active_routes: tuple[str, ...],
) -> None:
    metrics_path = _build_fixture(tmp_path, active_routes)

    summary_path, diagnostics_figure = generate_diagnostics(metrics_path)
    report_path = generate_report(metrics_path)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["active_routes"] == list(active_routes)
    assert set(summary["route_availability"]) == set(active_routes)
    assert set(summary["eliminated_routes"]) == set(ROUTES) - set(active_routes)
    assert diagnostics_figure.stat().st_size > 0
    assert (metrics_path.parent / "figures/02_route_test_comparison.png").stat().st_size > 0

    report = report_path.read_text(encoding="utf-8")
    for route in active_routes:
        assert ROUTE_LABELS[route] in report
    if len(active_routes) < len(ROUTES):
        assert "验证阶段淘汰" in report
        assert "淘汰路线未进入保留测试" in report
        assert "### 4.5 保留测试" in report
    else:
        assert "验证阶段淘汰" not in report
        assert "### 4.4 保留测试" in report
