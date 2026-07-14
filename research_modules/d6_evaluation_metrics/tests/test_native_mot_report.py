from __future__ import annotations

import csv
import json

from d6_evaluation_metrics import (
    NativeMotAirSimInputs,
    NativeMotAirSimReportGenerator,
    load_native_mot_airsim_rows,
    summarize_native_mot_airsim_rows,
)


def _row(stage: str, backend: str, frames: int, *, distance: float, detected: int) -> dict:
    available = detected > 0
    return {
        "case_id": f"{stage}-{backend}-{distance}",
        "stage": stage,
        "seed": 7,
        "tracker_backend": backend,
        "confidence_threshold": 0.1,
        "target_distance_m": distance,
        "frame_count": frames,
        "camera_width": 1920,
        "camera_height": 1080,
        "camera_fov_deg": 90.0,
        "target_asset_name": "Quadrotor1",
        "accepted_detection_count": detected,
        "native_active_frame_rate": detected / frames,
        "local_continuity": 1.0 if available else None,
        "terminal_local_id_switch_count": 0,
        "fallback_frame_count": 0,
        "warmup_excluded_p95_latency_ms": 8.0 if backend == "bytetrack" else 18.0,
        "offline_detector_precision": 0.4 if available else None,
        "offline_detector_recall": 0.4 if available else None,
        "native_mot_admitted": False,
        "rejection_reasons": ["offline_detector_precision_below_threshold"],
        "online_truth_use_count": 0,
        "truth_identity_used_online": False,
        "global_track_id_rewrite_count": 0,
    }


def _write(path, rows) -> None:
    path.write_text(json.dumps(rows), encoding="utf-8")


def test_report_keeps_short_check_and_confirmation_separate(tmp_path) -> None:
    preflight = tmp_path / "preflight.json"
    ranges = tmp_path / "ranges.json"
    confirmation = tmp_path / "confirmation.json"
    _write(preflight, [_row("preflight", "bytetrack", 32, distance=20.0, detected=20)])
    _write(
        ranges,
        [
            _row("range_precheck", "bytetrack", 42, distance=20.0, detected=42),
            _row("range_precheck", "botsort", 42, distance=30.0, detected=0),
        ],
    )
    _write(
        confirmation,
        [
            _row("confirmation", "bytetrack", 102, distance=20.0, detected=102),
            _row("confirmation", "botsort", 102, distance=20.0, detected=102),
        ],
    )
    inputs = NativeMotAirSimInputs(preflight, ranges, confirmation)
    rows, manifest = load_native_mot_airsim_rows(inputs)
    summary = summarize_native_mot_airsim_rows(rows, manifest=manifest)

    assert manifest["range_precheck_40_frame_class"]["actual_frame_counts"] == [42]
    assert manifest["confirmation_102_frame"]["actual_frame_counts"] == [102]
    assert summary["comparability_policy"]["pool_evidence_levels"] is False
    assert set(summary["by_evidence_level"]) == {
        "discovery_preflight",
        "range_precheck_40_frame_class",
        "confirmation_102_frame",
    }
    unavailable = next(row for row in rows if row["target_distance_m"] == 30.0)
    assert unavailable["local_continuity"] is None
    assert unavailable["local_continuity_availability"] == "unavailable"
    assert summary["truth_isolation"]["status"] == "pass"

    outputs = NativeMotAirSimReportGenerator().write_report_bundle(
        tmp_path / "output", inputs=inputs
    )
    assert all(path.exists() and path.stat().st_size > 0 for path in outputs.values())
    report = outputs["markdown"].read_text(encoding="utf-8")
    assert "不能合并为同一统计样本" in report
    assert "未保存 AirSim 截图" in report
    with outputs["cases_csv"].open(encoding="utf-8-sig") as stream:
        header = next(csv.reader(stream))
    assert "证据层级" in header
    assert "局部ID切换数" in header


def test_truth_violation_is_explicit(tmp_path) -> None:
    paths = [tmp_path / name for name in ("pre.json", "range.json", "confirm.json")]
    for index, path in enumerate(paths):
        row = _row("stage", "bytetrack", 32 + index, distance=20.0, detected=20)
        if index == 2:
            row["truth_identity_used_online"] = True
        _write(path, [row])
    rows, manifest = load_native_mot_airsim_rows(NativeMotAirSimInputs(*paths))
    summary = summarize_native_mot_airsim_rows(rows, manifest=manifest)
    assert summary["truth_isolation"]["status"] == "fail"
    assert summary["truth_isolation"]["truth_identity_used_online_count"] == 1
