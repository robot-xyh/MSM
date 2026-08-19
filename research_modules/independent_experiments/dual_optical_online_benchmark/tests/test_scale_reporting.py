from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from dual_optical_online_benchmark.scale_reporting import (
    collect_scale_funnel,
    generate_scale_funnel_report,
    main,
)


COUNTS = (20, 40, 60, 100)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _aggregate(target_count: int, route_index: int) -> dict[str, float | int | dict]:
    return {
        "publication_count": 24,
        "availability_rate": 1.0,
        "deadline_met_rate": 1.0,
        "macro_precision": 0.82 - route_index * 0.03,
        "macro_recall": 0.68 - target_count / 1000.0,
        "macro_on_time_recall": 0.68 - target_count / 1000.0,
        "macro_f1": 0.74 - target_count / 1200.0,
        "mean_candidate_true_retention_rate": 0.92 - target_count / 1000.0,
        "false_association_count": target_count // 10,
        "duplicate_identity_match_count": 0,
        "latency_p50_ms": target_count * 2.0,
        "latency_p95_ms": target_count * 4.0,
        "stage_latency_p95_ms": {},
    }


def _preflight(path: Path, count: int, fingerprint: str) -> None:
    _write(
        path,
        {
            "schema_version": "fixture-preflight",
            "protocol_fingerprint": fingerprint,
            "test_data_accessed": False,
            "acceptance": {
                "accepted": True,
                "by_scenario": {
                    "ideal": {"mean_common_confirmed_rate": 0.95},
                    "pose_error": {"mean_common_confirmed_rate": 0.90},
                    "full_interference": {
                        "mean_common_confirmed_rate": 0.85 - count / 1000.0
                    },
                },
            },
        },
    )


def _build_tier(root: Path, count: int) -> None:
    tier = root / f"targets_{count:03d}"
    fingerprint = f"protocol-{count}"
    preflight_path = tier / "preflight/preflight_summary.json"
    tracker_path = tier / "dataset/freezes/shared_tracker.json"
    freeze_path = tier / "dataset/freezes/all_routes_frozen.json"
    metrics_path = tier / "results/comparison_metrics.json"
    promotion_path = tier / "results/promotion_manifest.json"
    _preflight(preflight_path, count, fingerprint)
    _write(
        tracker_path,
        {
            "schema_version": "fixture-tracker",
            "test_data_accessed": False,
            "validation_metrics": {
                "by_corruption_level": {
                    "clean": {"mean_common_confirmed_rate": 0.95},
                    "light": {"mean_common_confirmed_rate": 0.90},
                    "medium": {"mean_common_confirmed_rate": 0.85},
                    "heavy": {"mean_common_confirmed_rate": 0.80},
                }
            },
        },
    )

    if count == 20:
        requested = ["epipolar_mht", "lightweight", "gnn"]
        active = ["epipolar_mht", "gnn"]
        validation_eliminated = {
            "lightweight": {
                "status": "eliminated_on_main_validation_gate",
                "reason_code": "conditional_precision_floor_not_met",
                "failure_evidence": "/must/not/be/read/lightweight.json",
            }
        }
    else:
        requested = active = ["gnn"]
        validation_eliminated = {}
    frozen_routes = {
        route: {
            "validation_acceptance": {
                "accepted": True,
                "validation_f1": 0.72,
            }
        }
        for route in active
    }
    _write(
        freeze_path,
        {
            "schema_version": "fixture-freeze",
            "protocol_fingerprint": fingerprint,
            "test_data_accessed": False,
            "requested_routes": requested,
            "active_routes": active,
            "eliminated_routes": validation_eliminated,
            "routes": frozen_routes,
            "tracker_freeze_sha256": _sha256(tracker_path),
        },
    )

    aggregate = {
        route: _aggregate(count, index) for index, route in enumerate(active)
    }
    rows = []
    for route in active:
        rows.append(
            {
                "route_name": route,
                "seed": 1,
                "corruption_level": "medium",
                "revolution_index": 1,
                "precision": 0.8,
                "recall": 0.6,
                "f1": 0.68,
                "match_count": 10,
                "correct_match_count": 8,
                "false_association_count": 2,
                "candidate_true_opportunity_count": 10,
                "candidate_true_retention_rate": 0.9,
            }
        )
    _write(
        metrics_path,
        {
            "schema_version": "fixture-metrics",
            "protocol": {"target_count": count},
            "protocol_fingerprint": fingerprint,
            "truth_used_online": False,
            "active_routes": active,
            "rows": rows,
            "aggregate": {"routes": aggregate},
            "shared_input_checks": [{"all_equal": True}],
            "freeze_marker_sha256": _sha256(freeze_path),
        },
    )

    if count == 20:
        promoted = ["gnn"]
        heldout_eliminated = {
            "epipolar_mht": ["latency_p95_exceeded_1000ms"]
        }
    else:
        promoted = ["gnn"]
        heldout_eliminated = {}
    decisions = {}
    for route in active:
        reasons = heldout_eliminated.get(route, [])
        decisions[route] = {
            "promoted": route in promoted,
            "reasons": reasons,
            "conditional_precision": 0.8,
            "identity_contract_violations": 0,
        }
    next_count = None if count == 100 else COUNTS[COUNTS.index(count) + 1]
    _write(
        promotion_path,
        {
            "schema_version": "fixture-promotion",
            "source_target_count": count,
            "source_protocol_fingerprint": fingerprint,
            "next_target_count": next_count,
            "active_routes": active,
            "promoted_routes": promoted,
            "eliminated_routes": heldout_eliminated,
            "decisions": decisions,
            "promotion_allowed": True,
            "reserved_test_used_for_parameter_selection": False,
            "reserved_test_used_for_single_promotion_decision": True,
            "metrics_sha256": _sha256(metrics_path),
        },
    )


def _build_funnel(root: Path, completed_count: int, *, pending: bool = False) -> None:
    for count in COUNTS[:completed_count]:
        _build_tier(root, count)
    if pending and completed_count < len(COUNTS):
        count = COUNTS[completed_count]
        _preflight(
            root / f"targets_{count:03d}/preflight/preflight_summary.json",
            count,
            f"protocol-{count}",
        )


def _tracker_validation(
    *, medium: float, purity: float = 1.0
) -> dict[str, object]:
    rates = {
        "clean": 0.76,
        "light": 0.72,
        "medium": medium,
        "heavy": 0.64,
    }
    return {
        "episode_level_count": 24,
        "median_track_purity": purity,
        "by_corruption_level": {
            level: {
                "episode_count": 6,
                "mean_common_confirmed_rate": rate,
                "median_common_confirmed_rate": rate,
                "mean_fragments_per_real_identity": 1.1,
                "median_track_purity": purity,
            }
            for level, rate in rates.items()
        },
    }


def _build_tracker_calibration_failure(root: Path, count: int = 100) -> None:
    tier = root / f"targets_{count:03d}"
    fingerprint = f"protocol-{count}"
    preflight_path = tier / "preflight/preflight_summary.json"
    manifest_path = tier / "dataset/raw_calibration_manifest.json"
    calibration_path = tier / "dataset/freezes/shared_tracker_calibration.json"
    _preflight(preflight_path, count, fingerprint)
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["schema_version"] = "dual-optical-online-preflight-v1"
    _write(preflight_path, preflight)

    episodes = [
        {
            "episode_dir": f"/fixture/train/{seed}",
            "receipt_sha256": f"receipt-train-{seed}",
            "seed": seed,
            "split": "train",
        }
        for seed in range(1, 25)
    ] + [
        {
            "episode_dir": f"/fixture/validation/{seed}",
            "receipt_sha256": f"receipt-validation-{seed}",
            "seed": seed,
            "split": "validation",
        }
        for seed in range(101, 107)
    ]
    _write(
        manifest_path,
        {
            "schema_version": "dual-optical-raw-calibration-manifest-v1",
            "protocol_fingerprint": fingerprint,
            "test_data_accessed": False,
            "episodes": episodes,
        },
    )

    candidates = []
    for index in range(13):
        medium = 0.64 + 0.002 * index
        purity = 1.0
        if index == 6:
            medium = 0.6617
        if index == 12:
            medium = 0.6933
            purity = 0.9091
        validation = _tracker_validation(
            medium=medium,
            purity=purity,
        )
        candidates.append(
            {
                "tracker_fingerprint": f"tracker-{index:02d}",
                "config": {"candidate_index": index},
                "train": validation,
                "validation": validation,
                "rows": [],
            }
        )
    selected = candidates[6]
    _write(
        calibration_path,
        {
            "schema_version": "dual-optical-shared-tracker-calibration-v2",
            "protocol_fingerprint": fingerprint,
            "test_data_accessed": False,
            "calibration_manifest": str(manifest_path.resolve()),
            "calibration_manifest_sha256": _sha256(manifest_path),
            "candidate_count": 13,
            "accepted_candidate_count": 0,
            "selected_tracker_fingerprint": selected["tracker_fingerprint"],
            "selected_validation_metrics": selected["validation"],
            "acceptance": {
                "accepted": False,
                "checks": {
                    "median_track_purity": True,
                    "light_common_confirmed_rate": True,
                    "medium_common_confirmed_rate": False,
                    "heavy_common_confirmed_rate": True,
                },
                "failure_reasons": ["medium_common_confirmed_rate"],
                "thresholds": {
                    "median_track_purity": 0.85,
                    "light_common_confirmed_rate": 0.70,
                    "medium_common_confirmed_rate": 0.70,
                    "heavy_common_confirmed_rate": 0.50,
                },
            },
            "candidates": candidates,
        },
    )


@pytest.mark.parametrize("completed_count", [1, 2, 3, 4])
def test_generate_report_supports_every_contiguous_scale_prefix(
    tmp_path: Path, completed_count: int
) -> None:
    root = tmp_path / "funnel"
    _build_funnel(root, completed_count, pending=completed_count < 4)
    output = tmp_path / "report"

    artifacts = generate_scale_funnel_report(root, output)

    summary = json.loads(artifacts["summary_json"].read_text(encoding="utf-8"))
    assert summary["completed_target_counts"] == list(COUNTS[:completed_count])
    assert summary["final_tier_reached"] is (completed_count == 4)
    assert len(artifacts["tier_csvs"]) == completed_count
    assert artifacts["combined_csv"].stat().st_size > 0
    assert artifacts["performance_figure"].stat().st_size > 0
    assert artifacts["tracking_figure"].stat().st_size > 0
    report = artifacts["report"].read_text(encoding="utf-8")
    assert "AirSim仿真证据" in report
    assert "在线跟踪和配准不读取Actor名称或真实身份" in report
    assert "验证淘汰" in report
    assert "保留集淘汰" in report
    if completed_count == 4:
        assert "最终档通过" in report
    else:
        assert "仅预检" in report


def test_validation_elimination_never_requires_route_metrics(tmp_path: Path) -> None:
    root = tmp_path / "funnel"
    _build_funnel(root, 1)

    summary = collect_scale_funnel(root)

    lightweight = next(
        route
        for route in summary["scales"][0]["routes"]
        if route["route_name"] == "lightweight"
    )
    assert lightweight["status"] == "eliminated_on_validation"
    assert lightweight["precision"] is None
    assert lightweight["failure_reason_codes"] == [
        "conditional_precision_floor_not_met"
    ]


def test_partially_sealed_tier_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "funnel"
    _build_funnel(root, 1)
    (root / "targets_020/dataset/freezes/shared_tracker.json").unlink()

    with pytest.raises(FileNotFoundError, match="partially sealed.*shared_tracker"):
        collect_scale_funnel(root)


def test_noncontiguous_completed_tiers_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "funnel"
    _build_tier(root, 20)
    _build_tier(root, 60)

    with pytest.raises(ValueError, match="contiguous prefix"):
        collect_scale_funnel(root)


def test_tracker_calibration_failure_is_a_terminal_scale_state(
    tmp_path: Path,
) -> None:
    root = tmp_path / "funnel"
    _build_funnel(root, 3)
    _build_tracker_calibration_failure(root)
    output = tmp_path / "report"

    artifacts = generate_scale_funnel_report(root, output)

    summary = json.loads(artifacts["summary_json"].read_text(encoding="utf-8"))
    assert summary["completed_target_counts"] == [20, 40, 60]
    assert summary["preflight_only_target_counts"] == []
    assert summary["tracker_calibration_failed_target_counts"] == [100]
    assert summary["funnel_state"] == "tracker_calibration_failed"
    failure = summary["tracker_calibration_failure"]
    assert failure["status"] == "tracker_calibration_failed"
    assert failure["status_cn"] == "共享跟踪器正式标定失败"
    assert failure["calibration_episode_count"] == 30
    assert failure["candidate_count"] == 13
    assert failure["accepted_candidate_count"] == 0
    assert failure["failure_reason_codes"] == [
        "medium_common_confirmed_rate"
    ]
    assert failure["selected_validation"]["common_confirmed_rate_by_level"][
        "medium"
    ] == pytest.approx(0.6617)
    medium_best = failure["best_by_metric"]["medium_common_confirmed_rate"]
    assert medium_best["value"] == pytest.approx(0.6933)
    assert medium_best["candidate_index"] == 12
    assert medium_best["candidate_median_track_purity"] == pytest.approx(0.9091)
    assert len(failure["candidates"]) == 13
    assert artifacts["tracker_candidate_csv"] is not None
    with artifacts["tracker_candidate_csv"].open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        candidate_rows = list(csv.DictReader(stream))
    assert len(candidate_rows) == 13
    with (output / "targets_100_metrics.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        failure_rows = list(csv.DictReader(stream))
    assert failure_rows[0]["status"] == "tracker_calibration_failed"
    report = artifacts["report"].read_text(encoding="utf-8")
    assert "共享跟踪器正式标定失败" in report
    assert "评估13组共享跟踪器候选" in report
    assert "标定选定候选值" in report
    assert "全部候选按该指标最高值" in report
    assert "全部候选均未通过全部门槛" in report
    assert "单项最高值为0.6933" in report
    assert "航迹纯度为0.9091" in report
    assert "门槛为0.7000" in report
    assert "候选最优值" not in report
    assert "100目标（仅预检）" not in report


def test_v3_tracker_calibration_failure_reads_continuity_gates(
    tmp_path: Path,
) -> None:
    root = tmp_path / "scale_funnel_v4"
    for index, count in enumerate((20, 40, 60)):
        _build_tier(root, count)
    _build_tracker_calibration_failure(root)
    path = root / "targets_100/dataset/freezes/shared_tracker_calibration.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "dual-optical-shared-tracker-calibration-v3"
    for candidate in payload["candidates"]:
        for split in ("train", "validation"):
            values = candidate[split]
            values.update(
                {
                    "mean_fragments_per_real_identity": 1.1,
                    "baseline_mean_fragments_per_real_identity": 1.1,
                    "false_reactivation_rate": 0.0,
                    "baseline_false_reactivation_rate": 0.0,
                    "sweep_runtime_p95_ms": 10.0,
                }
            )
    payload["selected_validation_metrics"] = payload["candidates"][6][
        "validation"
    ]
    payload["acceptance"]["thresholds"].update(
        {
            "maximum_false_reactivation_rate": 0.005,
            "maximum_sweep_runtime_p95_ms": 250.0,
        }
    )
    payload["acceptance"]["checks"].update(
        {
            "false_reactivation_rate_absolute": True,
            "false_reactivation_rate_not_above_baseline": True,
            "fragmentation_not_above_baseline": True,
            "sweep_runtime_p95_ms": True,
        }
    )
    _write(path, payload)

    summary = collect_scale_funnel(root)
    failure = summary["tracker_calibration_failure"]
    assert failure["candidate_count"] == 13
    assert failure["selected_validation"]["false_reactivation_rate"] == 0.0
    assert failure["selected_validation"]["sweep_runtime_p95_ms"] == 10.0


@pytest.mark.parametrize(
    "relative_path",
    [
        "preflight/preflight_summary.json",
        "dataset/raw_calibration_manifest.json",
        "dataset/freezes/shared_tracker_calibration.json",
    ],
)
def test_partial_tracker_calibration_failure_fails_closed(
    tmp_path: Path, relative_path: str
) -> None:
    root = tmp_path / "funnel"
    _build_funnel(root, 3)
    _build_tracker_calibration_failure(root)
    (root / "targets_100" / relative_path).unlink()

    with pytest.raises(FileNotFoundError, match="partial tracker calibration"):
        collect_scale_funnel(root)


def test_tracker_calibration_protocol_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "funnel"
    _build_funnel(root, 3)
    _build_tracker_calibration_failure(root)
    manifest_path = root / "targets_100/dataset/raw_calibration_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["protocol_fingerprint"] = "foreign-protocol"
    _write(manifest_path, manifest)

    with pytest.raises(ValueError, match="protocol fingerprint mismatch"):
        collect_scale_funnel(root)


def test_module_main_writes_to_caller_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "funnel"
    output = tmp_path / "caller-output"
    _build_funnel(root, 1)

    assert main(["--funnel-root", str(root), "--output-dir", str(output)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert Path(printed["report"]) == output / "DUAL_OPTICAL_SCALE_FUNNEL_SUMMARY_CN.md"
    with (output / "scale_route_metrics.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert {row["status"] for row in rows} == {
        "eliminated_on_validation",
        "eliminated_on_heldout",
        "promoted",
    }
