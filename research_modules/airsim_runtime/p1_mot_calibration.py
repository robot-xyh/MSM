"""Main-owned case matrix and admission policy for real D5 MOT runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


MOT_BACKENDS = ("bytetrack", "botsort")
MOT_CONFIDENCE_THRESHOLDS = (0.10, 0.20, 0.30)
MOT_TARGET_DISTANCES_M = (20.0, 30.0, 50.0)


@dataclass(frozen=True, slots=True)
class MotCalibrationCase:
    case_id: str
    stage: str
    seed: int
    tracker_backend: str
    confidence_threshold: float
    target_distance_m: float
    frame_count: int = 100
    camera_width: int = 1920
    camera_height: int = 1080
    camera_fov_deg: float = 90.0
    warmup_frames: int = 5

    def metadata(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "schema_version": "main-p1-native-mot-case-v1",
            "target_asset_name": "Quadrotor1",
            "native_tracker_required": True,
            "iou_fallback_admitted": False,
            "offline_truth_policy": "evaluation_only_after_online_tracking",
        }


def build_mot_screening_cases(seed: int) -> tuple[MotCalibrationCase, ...]:
    return tuple(
        MotCalibrationCase(
            case_id=(
                f"mot-screen-{backend}-c{confidence:.2f}-r{distance:.0f}-seed{seed:03d}"
            ),
            stage="single_camera_screening",
            seed=int(seed),
            tracker_backend=backend,
            confidence_threshold=confidence,
            target_distance_m=distance,
        )
        for backend in MOT_BACKENDS
        for confidence in MOT_CONFIDENCE_THRESHOLDS
        for distance in MOT_TARGET_DISTANCES_M
    )


def build_mot_confirmation_cases(
    selected_thresholds: Mapping[str, float],
    seeds: Iterable[int],
) -> tuple[MotCalibrationCase, ...]:
    cases: list[MotCalibrationCase] = []
    for backend in MOT_BACKENDS:
        if backend not in selected_thresholds:
            continue
        for seed in seeds:
            cases.append(
                MotCalibrationCase(
                    case_id=f"mot-confirm-{backend}-seed{int(seed):03d}",
                    stage="two_camera_confirmation",
                    seed=int(seed),
                    tracker_backend=backend,
                    confidence_threshold=float(selected_thresholds[backend]),
                    target_distance_m=30.0,
                    frame_count=200,
                )
            )
    return tuple(cases)


def mot_admission(row: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        "native_active_frame_rate": _number(row, "native_active_frame_rate") >= 0.95,
        "fallback_frame_count_zero": int(row.get("fallback_frame_count") or 0) == 0,
        "recall_at_least_0_80": _number(row, "detector_recall") >= 0.80,
        "precision_at_least_0_90": _number(row, "detector_precision") >= 0.90,
        "continuity_at_least_0_90": _number(row, "local_track_continuity") >= 0.90,
        "id_switch_at_most_one": int(row.get("terminal_local_id_switch_count") or 0) <= 1,
        "p95_latency_at_most_100_ms": _number(row, "warmup_excluded_p95_latency_ms") <= 100.0,
        "online_truth_use_zero": int(row.get("online_truth_use_count") or 0) == 0,
    }
    return {
        "admitted": all(checks.values()),
        "checks": checks,
        "tracker_backend": row.get("tracker_backend"),
        "confidence_threshold": row.get("confidence_threshold"),
    }


def select_backend_thresholds(rows: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """Select one threshold per backend from the 30 m screening evidence."""

    selected: dict[str, float] = {}
    for backend in MOT_BACKENDS:
        candidates = [
            row
            for row in rows
            if str(row.get("tracker_backend")) == backend
            and abs(_number(row, "target_distance_m") - 30.0) < 1e-6
            and _number(row, "accepted_detection_count") > 0.0
            and _number(row, "native_active_frame_rate") > 0.0
            and row.get("detector_precision") is not None
            and row.get("detector_recall") is not None
        ]
        if not candidates:
            continue
        best = max(
            candidates,
            key=lambda row: (
                _f1(row),
                _number(row, "local_track_continuity"),
                -_number(row, "warmup_excluded_p95_latency_ms"),
                -_number(row, "confidence_threshold"),
            ),
        )
        selected[backend] = _number(best, "confidence_threshold")
    return selected


def write_mot_execution_index(
    output_path: str | Path,
    *,
    cases: Iterable[MotCalibrationCase],
    rows: Iterable[Mapping[str, Any]],
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    row_list = [dict(row) for row in rows]
    payload = {
        "schema_version": "main-p1-native-mot-index-v1",
        "cases": [case.metadata() for case in cases],
        "rows": row_list,
        "admission": [mot_admission(row) for row in row_list],
        "default_detection_backend_changed": False,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _f1(row: Mapping[str, Any]) -> float:
    precision = _number(row, "detector_precision")
    recall = _number(row, "detector_recall")
    return 0.0 if precision + recall <= 0.0 else 2.0 * precision * recall / (precision + recall)


def _number(row: Mapping[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0
