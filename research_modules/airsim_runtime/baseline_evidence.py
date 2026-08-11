"""Freeze compact, truth-isolated evidence from a long-range AirSim episode."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


BASELINE_SCHEMA_VERSION = "d5-long-range-baseline-v1"
ONLINE_FIXTURE_SCHEMA_VERSION = "d5-long-range-online-replay-v1"
OFFLINE_SIDECAR_SCHEMA_VERSION = "d5-long-range-offline-sidecar-v1"


def freeze_long_range_baseline(source_dir: str | Path, output_dir: str | Path) -> dict[str, Path]:
    """Write a compact baseline without copying actor identity into online inputs."""

    source = Path(source_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    metrics = _read_json(source / "metrics.json")
    associations = _read_csv(source / "associations.csv")
    detections = _read_csv(source / "detections.csv")
    global_tracks = _read_csv(source / "global_tracks.csv")
    gimbal_rows = _read_csv(source / "scan_gimbal.csv")
    truth_rows = _read_csv(source / "mot_offline_score.csv")

    truth_by_key = {
        (
            str(row["camera_vehicle_name"]),
            int(row["frame_index"]),
            str(row["local_track_id"]),
        ): str(row["truth_global_track_id"])
        for row in truth_rows
        if row.get("truth_global_track_id")
    }
    incorrect = _incorrect_associations(associations, truth_by_key)
    switches = _binding_switches(associations)
    short_gaps = _short_gaps(truth_rows)
    selected_frames = _selected_frame_indices(incorrect, short_gaps)
    selected_frames.intersection_update(int(row["frame_index"]) for row in gimbal_rows)

    detections_by_frame: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in detections:
        frame_index = int(row["frame_index"])
        if frame_index not in selected_frames:
            continue
        camera_id = str(row["camera_id"])
        detections_by_frame[(frame_index, camera_id.split(":", 1)[0])].append(
            {
                "local_track_id": str(row["local_track_id"]),
                "measurement_timestamp": float(row["measurement_timestamp"]),
                "arrival_timestamp": float(row["arrival_timestamp"]),
                "bbox_xyxy": [
                    float(row["bbox_x1"]),
                    float(row["bbox_y1"]),
                    float(row["bbox_x2"]),
                    float(row["bbox_y2"]),
                ],
                "center_px": [float(row["center_u"]), float(row["center_v"])],
                "covariance_px": [
                    [float(row["covariance_uu"]), float(row["covariance_uv"])],
                    [float(row["covariance_uv"]), float(row["covariance_vv"])],
                ],
                "mot_history_length": int(row["mot_history_length"]),
                "mot_backend": str(row["mot_backend"]),
                "world_ray_ned": _json_value(row.get("world_ray_ned", "")),
                "online_truth_identity_used": False,
            }
        )

    tracks_by_frame: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in global_tracks:
        frame_index = int(row["frame_index"])
        if frame_index not in selected_frames:
            continue
        tracks_by_frame[frame_index].append(
            {
                "global_track_id": str(row["global_track_id"]),
                "measurement_timestamp": float(row["measurement_timestamp"]),
                "arrival_timestamp": float(row["arrival_timestamp"]),
                "position_ned_m": [
                    float(row["px_ned_m"]),
                    float(row["py_ned_m"]),
                    float(row["pz_ned_m"]),
                ],
                "velocity_ned_mps": [
                    float(row["vx_ned_mps"]),
                    float(row["vy_ned_mps"]),
                    float(row["vz_ned_mps"]),
                ],
                "covariance_ned_m2": [
                    [float(row["covariance_xx"]), 0.0, 0.0],
                    [0.0, float(row["covariance_yy"]), 0.0],
                    [0.0, 0.0, float(row["covariance_zz"])],
                ],
            }
        )

    gimbal_by_frame = {int(row["frame_index"]): row for row in gimbal_rows}
    online_path = output / "online_replay.jsonl"
    with online_path.open("w", encoding="utf-8") as stream:
        for frame_index in sorted(selected_frames):
            gimbal = gimbal_by_frame[frame_index]
            timestamp = float(gimbal["measurement_timestamp"])
            for camera_name in ("Center_CV", "Interceptor_CV"):
                is_center = camera_name == "Center_CV"
                position = (
                    [0.0, 0.0, -100.0]
                    if is_center
                    else [
                        float(gimbal["interceptor_position_x"]),
                        float(gimbal["interceptor_position_y"]),
                        float(gimbal["interceptor_position_z"]),
                    ]
                )
                payload = {
                    "schema_version": ONLINE_FIXTURE_SCHEMA_VERSION,
                    "frame_index": frame_index,
                    "camera_vehicle_name": camera_name,
                    "camera_id": f"{camera_name}:0",
                    "measurement_timestamp": timestamp,
                    "camera_pose_ned": {
                        "position": position,
                        "yaw_deg": float(
                            gimbal["center_yaw_deg"]
                            if is_center
                            else gimbal["interceptor_yaw_deg"]
                        ),
                        "pitch_deg": float(
                            gimbal["center_pitch_deg"]
                            if is_center
                            else gimbal["interceptor_pitch_deg"]
                        ),
                    },
                    "global_tracks": sorted(
                        tracks_by_frame[frame_index], key=lambda item: item["global_track_id"]
                    ),
                    "local_tracks": sorted(
                        detections_by_frame.get((frame_index, camera_name), ()),
                        key=lambda item: item["local_track_id"],
                    ),
                    "truth_identity_used": False,
                }
                stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    sidecar_path = output / "offline_truth_sidecar.json"
    _write_json(
        sidecar_path,
        {
            "schema_version": OFFLINE_SIDECAR_SCHEMA_VERSION,
            "offline_truth_only": True,
            "incorrect_associations": incorrect,
            "binding_switches": switches,
            "short_gaps": short_gaps,
            "truth_labels": [
                {
                    "camera_vehicle_name": camera,
                    "frame_index": frame,
                    "local_track_id": local,
                    "truth_global_track_id": truth,
                }
                for (camera, frame, local), truth in sorted(truth_by_key.items())
                if frame in selected_frames
            ],
        },
    )

    source_files = (
        "metrics.json",
        "associations.csv",
        "mot_continuity.json",
        "mot_offline_score.csv",
        "offline_truth.csv",
        "record_manifest.json",
    )
    mot = metrics["mot_continuity"]["aggregate"]
    manifest_path = output / "baseline_manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": BASELINE_SCHEMA_VERSION,
            "scenario_id": "d5_cv_long_range_20target_visual_evidence_20260810",
            "source_directory": str(source),
            "source_artifact_sha256": {
                name: _sha256(source / name) for name in source_files
            },
            "frozen_fixture_sha256": {
                online_path.name: _sha256(online_path),
                sidecar_path.name: _sha256(sidecar_path),
            },
            "selected_frame_count": len(selected_frames),
            "online_fixture_record_count": len(selected_frames) * 2,
            "core_metrics": {
                "target_count": int(metrics["target_count"]),
                "seed": 20260810,
                "association_evaluable_count": int(metrics["association_evaluable_count"]),
                "association_accuracy": float(metrics["association_accuracy"]),
                "id_switch_count": int(metrics["id_switch_count"]),
                "short_gap_fragmentation_count": int(mot["fragmentation_count"]),
                "reacquisition_count": int(mot["reacquisition_count"]),
                "geometric_binding_switch_count": int(
                    metrics["geometric_binding_switch_count"]
                ),
                "crossing_window_count": int(mot["crossing_window_count"]),
                "crossing_evaluable_window_count": int(
                    mot["crossing_evaluable_window_count"]
                ),
                "duplicate_assignment_count": int(metrics["duplicate_assignment_count"]),
                "online_truth_identity_use_count": int(
                    metrics["online_truth_identity_use_count"]
                ),
                "global_track_id_rewrite_count": int(
                    metrics["global_track_id_rewrite_count"]
                ),
            },
            "failure_counts": {
                "incorrect_association_count": len(incorrect),
                "binding_switch_count": len(switches),
                "short_gap_count": len(short_gaps),
                "crossing_unavailable_reason_counts": dict(
                    Counter(
                        str(row.get("unavailable_reason", ""))
                        for row in mot.get("crossing_window_results", ())
                        if not row.get("availability")
                    )
                ),
            },
            "identity_boundary": {
                "online_actor_or_object_identity_present": False,
                "truth_sidecar_offline_only": True,
                "global_track_id_center_owned": True,
            },
        },
    )
    return {
        "manifest": manifest_path,
        "online_replay": online_path,
        "offline_truth_sidecar": sidecar_path,
    }


def _incorrect_associations(
    associations: Iterable[Mapping[str, str]],
    truth_by_key: Mapping[tuple[str, int, str], str],
) -> list[dict[str, Any]]:
    result = []
    for row in associations:
        camera = str(row["camera_id"]).split(":", 1)[0]
        key = (camera, int(row["frame_index"]), str(row["local_track_id"]))
        truth = truth_by_key.get(key)
        if truth and truth != row["global_track_id"]:
            result.append(
                {
                    "camera_vehicle_name": camera,
                    "frame_index": int(row["frame_index"]),
                    "measurement_timestamp": float(row["measurement_timestamp"]),
                    "local_track_id": str(row["local_track_id"]),
                    "assigned_global_track_id": str(row["global_track_id"]),
                    "truth_global_track_id": truth,
                    "pixel_error_px": float(row["pixel_error"]),
                    "mahalanobis_d2": float(row["mahalanobis_d2"]),
                }
            )
    return result


def _binding_switches(associations: Iterable[Mapping[str, str]]) -> list[dict[str, Any]]:
    previous: dict[tuple[str, str], str] = {}
    result = []
    ordered = sorted(
        associations,
        key=lambda row: (int(row["frame_index"]), str(row["camera_id"]), str(row["local_track_id"])),
    )
    for row in ordered:
        key = (str(row["camera_id"]), str(row["local_track_id"]))
        old = previous.get(key)
        new = str(row["global_track_id"])
        if old is not None and old != new:
            result.append(
                {
                    "camera_id": key[0],
                    "frame_index": int(row["frame_index"]),
                    "measurement_timestamp": float(row["measurement_timestamp"]),
                    "local_track_id": key[1],
                    "previous_global_track_id": old,
                    "proposed_global_track_id": new,
                    "pixel_error_px": float(row["pixel_error"]),
                    "mahalanobis_d2": float(row["mahalanobis_d2"]),
                }
            )
        previous[key] = new
    return result


def _short_gaps(rows: Iterable[Mapping[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("truth_global_track_id"):
            grouped[(str(row["camera_vehicle_name"]), str(row["truth_global_track_id"]))].append(row)
    result = []
    for (camera, truth), values in grouped.items():
        ordered = sorted(values, key=lambda row: float(row["measurement_timestamp"]))
        for previous, current in zip(ordered, ordered[1:]):
            gap = float(current["measurement_timestamp"]) - float(previous["measurement_timestamp"])
            if 0.05 < gap <= 0.50:
                result.append(
                    {
                        "camera_vehicle_name": camera,
                        "truth_global_track_id": truth,
                        "from_frame_index": int(previous["frame_index"]),
                        "to_frame_index": int(current["frame_index"]),
                        "from_timestamp": float(previous["measurement_timestamp"]),
                        "to_timestamp": float(current["measurement_timestamp"]),
                        "gap_s": gap,
                        "same_local_track_id": (
                            previous["local_track_id"] == current["local_track_id"]
                        ),
                        "from_local_track_id": str(previous["local_track_id"]),
                        "to_local_track_id": str(current["local_track_id"]),
                    }
                )
    return sorted(result, key=lambda row: (row["from_frame_index"], row["camera_vehicle_name"]))


def _selected_frame_indices(
    incorrect: Iterable[Mapping[str, Any]], short_gaps: Iterable[Mapping[str, Any]]
) -> set[int]:
    selected: set[int] = set()
    for row in incorrect:
        frame = int(row["frame_index"])
        selected.update(range(max(0, frame - 2), frame + 3))
    for row in short_gaps:
        selected.update(
            range(int(row["from_frame_index"]), int(row["to_frame_index"]) + 1)
        )
    return selected


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_value(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


__all__ = [
    "BASELINE_SCHEMA_VERSION",
    "OFFLINE_SIDECAR_SCHEMA_VERSION",
    "ONLINE_FIXTURE_SCHEMA_VERSION",
    "freeze_long_range_baseline",
]
