"""Offline re-audit for long-range anonymous MOT records.

The tracker receives only anonymous detections and reconstructed camera
calibration. Offline truth is joined after tracking and is used only for
metrics. Source AirSim output directories are never modified.
"""

from __future__ import annotations

from collections import defaultdict
import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from airsim_dryrun.models import AirSimCameraInfo, AirSimDetectionBox

from .long_range_cv_scan import (
    CENTER_CAMERA_NAME,
    CENTER_CAMERA_SPEC,
    INTERCEPTOR_CAMERA_NAME,
    INTERCEPTOR_CAMERA_SPEC,
    VelocityAwareAnonymousTracker,
    evaluate_mot_continuity,
)


AIRSIM_BODY_TO_OPENCV_CAMERA = np.array(
    [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]],
    dtype=float,
)


def camera_info_from_gimbal_record(
    *,
    vehicle_name: str,
    frame_index: int,
    timestamp: float,
    yaw_deg: float,
    pitch_deg: float,
    position_ned: Sequence[float],
) -> AirSimCameraInfo:
    """Reconstruct the synchronized camera model recorded by scan_gimbal.csv."""

    spec = (
        CENTER_CAMERA_SPEC
        if str(vehicle_name) == CENTER_CAMERA_NAME
        else INTERCEPTOR_CAMERA_SPEC
    )
    yaw = math.radians(float(yaw_deg))
    pitch = math.radians(float(pitch_deg))
    cosine_yaw, sine_yaw = math.cos(yaw), math.sin(yaw)
    cosine_pitch, sine_pitch = math.cos(pitch), math.sin(pitch)
    rotation_yaw = np.array(
        [[cosine_yaw, -sine_yaw, 0.0], [sine_yaw, cosine_yaw, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    rotation_pitch = np.array(
        [[cosine_pitch, 0.0, sine_pitch], [0.0, 1.0, 0.0], [-sine_pitch, 0.0, cosine_pitch]],
        dtype=float,
    )
    body_to_world = rotation_yaw @ rotation_pitch
    world_to_opencv = AIRSIM_BODY_TO_OPENCV_CAMERA @ body_to_world.T
    focal = spec.focal_length_px
    return AirSimCameraInfo(
        camera_id=f"{vehicle_name}:0",
        owner_id=str(vehicle_name),
        timestamp=float(timestamp),
        position_ned=tuple(float(value) for value in position_ned),
        rotation_world_to_camera=tuple(
            tuple(float(value) for value in row) for row in world_to_opencv
        ),
        fx=focal,
        fy=focal,
        cx=spec.width * 0.5,
        cy=spec.height * 0.5,
        width=spec.width,
        height=spec.height,
    )


def reaudit_long_range_profile_rows(
    *,
    detection_rows: Sequence[Mapping[str, Any]],
    scan_rows: Sequence[Mapping[str, Any]],
    offline_truth_rows: Sequence[Mapping[str, Any]],
    crossing_windows: Sequence[Mapping[str, Any]],
    center_position_ned: Sequence[float] = (0.0, 0.0, -100.0),
    continuous_visibility_gap_s: float = 0.05,
    reacquisition_gap_s: float = 0.50,
) -> dict[str, Any]:
    """Re-track one profile and compare old/new IDs under the revised scorer."""

    truth_by_detection = {
        str(row["detection_id"]): str(row.get("global_track_id", ""))
        for row in offline_truth_rows
        if row.get("detection_id")
    }
    baseline_score_rows: list[dict[str, Any]] = []
    for row in detection_rows:
        truth_id = truth_by_detection.get(str(row.get("detection_id", "")), "")
        if not truth_id:
            continue
        baseline_score_rows.append(
            {
                "frame_index": _as_int(row["frame_index"]),
                "measurement_timestamp": _as_float(row["measurement_timestamp"]),
                "camera_vehicle_name": _camera_vehicle_name(row),
                "local_track_id": str(row.get("local_track_id", "")),
                "truth_global_track_id": truth_id,
                "offline_truth_only": True,
            }
        )

    scan_by_frame = {_as_int(row["frame_index"]): row for row in scan_rows}
    grouped: dict[tuple[int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in detection_rows:
        grouped[(_as_int(row["frame_index"]), _camera_vehicle_name(row))].append(row)
    trackers = {
        vehicle_name: VelocityAwareAnonymousTracker(
            f"{vehicle_name}:0:reaudit",
            max_coast_s=reacquisition_gap_s,
        )
        for vehicle_name in sorted({vehicle_name for _frame, vehicle_name in grouped})
    }
    corrected_rows: list[dict[str, Any]] = []
    corrected_score_rows: list[dict[str, Any]] = []
    for (frame_index, vehicle_name), frame_rows in sorted(grouped.items()):
        scan = scan_by_frame[frame_index]
        timestamp = _as_float(frame_rows[0]["measurement_timestamp"])
        if vehicle_name == CENTER_CAMERA_NAME:
            yaw = _as_float(scan["center_yaw_deg"])
            pitch = _as_float(scan["center_pitch_deg"])
            position = tuple(float(value) for value in center_position_ned)
        else:
            yaw = _as_float(scan["interceptor_yaw_deg"])
            pitch = _as_float(scan["interceptor_pitch_deg"])
            position = (
                _as_float(scan["interceptor_position_x"]),
                _as_float(scan["interceptor_position_y"]),
                _as_float(scan["interceptor_position_z"]),
            )
        camera_info = camera_info_from_gimbal_record(
            vehicle_name=vehicle_name,
            frame_index=frame_index,
            timestamp=timestamp,
            yaw_deg=yaw,
            pitch_deg=pitch,
            position_ned=position,
        )
        anonymous_detections = tuple(_anonymous_detection(row) for row in frame_rows)
        tracked = trackers[vehicle_name].update(
            anonymous_detections,
            timestamp=timestamp,
            frame_index=frame_index,
            camera_info=camera_info,
        )
        for source, detection in zip(frame_rows, tracked):
            detection_id = str(source["detection_id"])
            truth_id = truth_by_detection.get(detection_id, "")
            corrected_rows.append(
                {
                    "frame_index": frame_index,
                    "measurement_timestamp": timestamp,
                    "camera_vehicle_name": vehicle_name,
                    "detection_id": detection_id,
                    "old_local_track_id": str(source.get("local_track_id", "")),
                    "corrected_local_track_id": detection.local_track_id,
                    "center_u": detection.center_px[0],
                    "center_v": detection.center_px[1],
                    "world_ray_ned": detection.metadata["world_ray_ned"],
                    "camera_motion_compensated": True,
                    "online_truth_identity_used": False,
                    "truth_global_track_id": truth_id,
                    "offline_truth_only": True,
                }
            )
            if truth_id:
                corrected_score_rows.append(
                    {
                        "frame_index": frame_index,
                        "measurement_timestamp": timestamp,
                        "camera_vehicle_name": vehicle_name,
                        "local_track_id": detection.local_track_id,
                        "truth_global_track_id": truth_id,
                        "offline_truth_only": True,
                    }
                )

    scoring_args = {
        "crossing_windows": crossing_windows,
        "continuous_visibility_gap_s": continuous_visibility_gap_s,
        "reacquisition_gap_s": reacquisition_gap_s,
    }
    return {
        "schema_version": "d5-long-range-mot-offline-reaudit-v1",
        "online_truth_identity_use_count": 0,
        "truth_join_stage": "after_anonymous_tracking_for_offline_scoring_only",
        "baseline_rescored": evaluate_mot_continuity(
            baseline_score_rows,
            **scoring_args,
        ),
        "camera_motion_compensated": evaluate_mot_continuity(
            corrected_score_rows,
            **scoring_args,
        ),
        "corrected_assignments": corrected_rows,
    }


def reaudit_long_range_campaign(
    *,
    source_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Read a completed campaign and write a separate, non-destructive audit."""

    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    if source_dir.resolve() == output_dir.resolve():
        raise ValueError("output_dir must differ from the historical source directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario = json.loads((source_dir / "scenario.json").read_text(encoding="utf-8"))
    center_position = scenario["scenario"]["center_position_ned"]
    profiles: dict[str, Any] = {}
    comparison_rows: list[dict[str, Any]] = []
    for mode in ("mechanical_2s", "coverage_safe"):
        profile_dir = source_dir / mode
        if not profile_dir.exists():
            continue
        audit = reaudit_long_range_profile_rows(
            detection_rows=_read_csv(profile_dir / "detections.csv"),
            scan_rows=_read_csv(profile_dir / "scan_gimbal.csv"),
            offline_truth_rows=_read_csv(profile_dir / "offline_truth.csv"),
            crossing_windows=_read_csv(profile_dir / "crossing_windows.csv"),
            center_position_ned=center_position,
        )
        archived = json.loads((profile_dir / "metrics.json").read_text(encoding="utf-8"))[
            "mot_continuity"
        ]["aggregate"]
        profile_output = output_dir / mode
        profile_output.mkdir(parents=True, exist_ok=True)
        _write_csv(profile_output / "corrected_assignments.csv", audit["corrected_assignments"])
        _write_json(profile_output / "baseline_rescored.json", audit["baseline_rescored"])
        _write_json(
            profile_output / "camera_motion_compensated.json",
            audit["camera_motion_compensated"],
        )
        before = audit["baseline_rescored"]["aggregate"]
        after = audit["camera_motion_compensated"]["aggregate"]
        comparison = {
            "mode": mode,
            "archived_v1_id_switch_count": archived.get("id_switch_count"),
            "archived_v1_fragmentation_count": archived.get("fragmentation_count"),
            **_metric_columns("baseline_v2", before),
            **_metric_columns("motion_compensated_v2", after),
        }
        comparison_rows.append(comparison)
        _write_json(profile_output / "comparison.json", comparison)
        profiles[mode] = {
            "comparison": comparison,
            "baseline_rescored": audit["baseline_rescored"],
            "camera_motion_compensated": audit["camera_motion_compensated"],
        }
    _write_csv(output_dir / "metrics_comparison.csv", comparison_rows)
    payload = {
        "schema_version": "d5-long-range-mot-offline-campaign-reaudit-v1",
        "source_dir": str(source_dir.resolve()),
        "source_modified": False,
        "profiles": profiles,
    }
    _write_json(output_dir / "metrics_comparison.json", payload)
    report_path = _write_report(output_dir / "D5_LONG_RANGE_MOT_REAUDIT_CN.md", payload)
    payload["report"] = str(report_path)
    return payload


def _anonymous_detection(row: Mapping[str, Any]) -> AirSimDetectionBox:
    return AirSimDetectionBox(
        detection_id=str(row["detection_id"]),
        camera_id=str(row["camera_id"]),
        object_id="",
        local_track_id="",
        timestamp=_as_float(row["measurement_timestamp"]),
        center_px=(_as_float(row["center_u"]), _as_float(row["center_v"])),
        bbox_xyxy=(
            _as_float(row["bbox_x1"]),
            _as_float(row["bbox_y1"]),
            _as_float(row["bbox_x2"]),
            _as_float(row["bbox_y2"]),
        ),
        confidence=1.0,
        classification_hint="uav",
        metadata={"online_truth_identity_used": False},
    )


def _camera_vehicle_name(row: Mapping[str, Any]) -> str:
    return str(row.get("camera_vehicle_name") or str(row["camera_id"]).split(":", 1)[0])


def _metric_columns(prefix: str, metrics: Mapping[str, Any]) -> dict[str, Any]:
    names = (
        "raw_total_id_switch_count",
        "raw_total_fragmentation_count",
        "id_switch_count",
        "fragmentation_count",
        "reacquisition_count",
        "track_purity",
        "track_continuity",
        "crossing_evaluable_window_count",
        "crossing_not_evaluable_window_count",
        "crossing_id_switch_count",
        "crossing_track_purity",
        "crossing_track_continuity",
        "gate_passed",
    )
    return {f"{prefix}_{name}": metrics.get(name) for name in names}


def _write_report(path: Path, payload: Mapping[str, Any]) -> Path:
    lines = [
        "# 长距多目标跟踪离线复核",
        "",
        "## 结论",
        "",
        "本复核使用历史检测框和云台记录重建相机视线。匿名跟踪完成后才接入离线真值评分，历史AirSim输出目录未修改。复核结果用于判断修正方向，不能替代重新运行Blocks。",
        "",
        "## 指标",
        "",
        "| 模式 | 旧口径身份切换 | 新口径基线连续段切换 | 运动补偿连续段切换 | 长期重发现 | 可评分交叉窗口 | 交叉切换 | 门控 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for mode, profile in payload["profiles"].items():
        comparison = profile["comparison"]
        lines.append(
            "| {mode} | {old} | {baseline} | {corrected} | {reacq} | {windows} | {crossing} | {gate} |".format(
                mode=mode,
                old=comparison.get("archived_v1_id_switch_count"),
                baseline=comparison.get("baseline_v2_id_switch_count"),
                corrected=comparison.get("motion_compensated_v2_id_switch_count"),
                reacq=comparison.get("motion_compensated_v2_reacquisition_count"),
                windows=comparison.get("motion_compensated_v2_crossing_evaluable_window_count"),
                crossing=comparison.get("motion_compensated_v2_crossing_id_switch_count"),
                gate="通过" if comparison.get("motion_compensated_v2_gate_passed") else "未通过",
            )
        )
    lines.extend(
        [
            "",
            "## 口径",
            "",
            "连续观测间隔不超过0.05秒时，局部编号变化计为连续可见段身份切换。0.05至0.50秒的缺口单列为短缺口中断。超过0.50秒的重新出现计为长期重发现，仍保留其编号变化，但不纳入连续段门控。",
            "",
            "交叉窗口按相机和指定目标对评分。两个目标没有同时出现、任一目标样本不足或没有共同可见帧时，该窗口标记为不可评分。门控至少需要一个可评分交叉窗口。",
            "",
            "## 后续验证",
            "",
            "修正后的在线跟踪仍需重新运行相同Blocks场景，核对真实相机姿态时间戳、视线补偿、短缺口中断和交叉目标编号。离线复核通过也不能写成真实运行通过。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        if fields:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (list, tuple, dict))
                        else value
                        for key, value in row.items()
                    }
                )
    return path


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _as_float(value: Any) -> float:
    return float(value)


def _as_int(value: Any) -> int:
    return int(float(value))


__all__ = [
    "camera_info_from_gimbal_record",
    "reaudit_long_range_campaign",
    "reaudit_long_range_profile_rows",
]
