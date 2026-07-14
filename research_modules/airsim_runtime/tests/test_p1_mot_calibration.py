from __future__ import annotations

import json

from airsim_runtime.p1_mot_calibration import (
    build_mot_confirmation_cases,
    build_mot_screening_cases,
    mot_admission,
    select_backend_thresholds,
    write_mot_execution_index,
)


def test_screening_matrix_is_frozen_and_requires_native_mot() -> None:
    cases = build_mot_screening_cases(3)

    assert len(cases) == 18
    assert {case.tracker_backend for case in cases} == {"bytetrack", "botsort"}
    assert {case.target_distance_m for case in cases} == {20.0, 30.0, 50.0}
    assert all(case.metadata()["native_tracker_required"] for case in cases)
    assert all(case.metadata()["iou_fallback_admitted"] is False for case in cases)


def test_threshold_selection_and_confirmation_are_deterministic() -> None:
    rows = [
        _row("bytetrack", 0.1, recall=0.85, precision=0.90, latency=60.0),
        _row("bytetrack", 0.2, recall=0.82, precision=0.96, latency=50.0),
        _row("botsort", 0.1, recall=0.80, precision=0.95, latency=70.0),
        _row("botsort", 0.2, recall=0.88, precision=0.94, latency=75.0),
    ]

    selected = select_backend_thresholds(rows)
    cases = build_mot_confirmation_cases(selected, (1, 2))

    assert selected == {"bytetrack": 0.2, "botsort": 0.2}
    assert len(cases) == 4
    assert all(case.target_distance_m == 30.0 for case in cases)


def test_admission_rejects_iou_fallback_and_writes_index(tmp_path) -> None:
    passing = _row("bytetrack", 0.2, recall=0.85, precision=0.95, latency=70.0)
    failing = {**passing, "tracker_backend": "iou_fallback", "fallback_frame_count": 1}

    assert mot_admission(passing)["admitted"] is True
    assert mot_admission(failing)["admitted"] is False

    path = write_mot_execution_index(
        tmp_path / "index.json",
        cases=build_mot_confirmation_cases({"bytetrack": 0.2}, (1,)),
        rows=(passing, failing),
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["default_detection_backend_changed"] is False
    assert [item["admitted"] for item in payload["admission"]] == [True, False]


def test_threshold_selection_stops_when_screening_has_no_native_tracks() -> None:
    row = _row("bytetrack", 0.1, recall=0.0, precision=0.0, latency=8.0)
    row.update(
        accepted_detection_count=0,
        native_active_frame_rate=0.0,
        detector_precision=None,
        detector_recall=None,
    )

    assert select_backend_thresholds((row,)) == {}


def _row(backend: str, confidence: float, *, recall: float, precision: float, latency: float):
    return {
        "tracker_backend": backend,
        "confidence_threshold": confidence,
        "target_distance_m": 30.0,
        "native_active_frame_rate": 1.0,
        "accepted_detection_count": 100,
        "fallback_frame_count": 0,
        "detector_recall": recall,
        "detector_precision": precision,
        "local_track_continuity": 0.95,
        "terminal_local_id_switch_count": 0,
        "warmup_excluded_p95_latency_ms": latency,
        "online_truth_use_count": 0,
    }
