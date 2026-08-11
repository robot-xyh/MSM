"""Visual evidence for the long-range D5 registration experiment.

Raw AirSim scene images remain untouched.  This module creates derived,
annotated evidence from online association records and keeps offline truth
usage confined to explicitly labelled scoring plots.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


def write_long_range_registration_visual_evidence(
    output_dir: Path,
    *,
    snapshot_rows: Sequence[Mapping[str, Any]],
    detection_rows: Sequence[Mapping[str, Any]],
    association_rows: Sequence[Mapping[str, Any]],
    accuracy_rows: Sequence[Mapping[str, Any]],
    metrics: Mapping[str, Any],
    center_vehicle_name: str,
    interceptor_vehicle_name: str,
) -> tuple[dict[str, Path], dict[str, Any]]:
    """Write camera overlays, magnified crops, handover panels, and plots."""

    import cv2  # type: ignore

    evidence_root = Path(output_dir) / "visual_evidence"
    annotated_root = evidence_root / "annotated"
    crop_root = evidence_root / "crops"
    handover_root = evidence_root / "handover"
    for directory in (annotated_root, crop_root, handover_root):
        directory.mkdir(parents=True, exist_ok=True)

    detections_by_frame: dict[tuple[int, str], list[Mapping[str, Any]]] = {}
    for row in detection_rows:
        key = (int(row["frame_index"]), _camera_owner(str(row["camera_id"])))
        detections_by_frame.setdefault(key, []).append(row)
    associations_by_frame: dict[tuple[int, str], list[Mapping[str, Any]]] = {}
    for row in association_rows:
        key = (int(row["frame_index"]), _camera_owner(str(row["camera_id"])))
        associations_by_frame.setdefault(key, []).append(row)

    manifest_rows: list[dict[str, Any]] = []
    best_candidates: dict[tuple[str, str], dict[str, Any]] = {}
    annotated_by_owner: dict[str, list[dict[str, Any]]] = {}
    decode_failures: list[str] = []
    for snapshot in snapshot_rows:
        if not snapshot.get("saved") or not snapshot.get("path"):
            continue
        raw_path = _resolve_existing_path(snapshot["path"])
        frame_index = int(snapshot["frame_index"])
        owner = str(snapshot["camera_vehicle_name"])
        image = cv2.imread(str(raw_path), cv2.IMREAD_COLOR)
        if image is None:
            decode_failures.append(str(raw_path))
            continue
        frame_detections = detections_by_frame.get((frame_index, owner), [])
        frame_associations = associations_by_frame.get((frame_index, owner), [])
        association_by_local = {
            str(row["local_track_id"]): row for row in frame_associations
        }
        annotated = _annotate_frame(
            image,
            snapshot=snapshot,
            detections=frame_detections,
            associations=association_by_local,
        )
        owner_dir = annotated_root / _safe_name(owner)
        owner_dir.mkdir(parents=True, exist_ok=True)
        annotated_path = owner_dir / f"frame_{frame_index:04d}_annotated.png"
        cv2.imwrite(str(annotated_path), annotated)
        entry = {
            "frame_index": frame_index,
            "logical_timestamp": float(snapshot.get("logical_timestamp", 0.0)),
            "camera_vehicle_name": owner,
            "capture_reasons": str(snapshot.get("capture_reasons", "")),
            "raw_path": str(raw_path),
            "annotated_path": str(annotated_path),
            "detection_count": len(frame_detections),
            "association_count": len(frame_associations),
        }
        manifest_rows.append(entry)
        annotated_by_owner.setdefault(owner, []).append(entry)

        detection_by_local = {
            str(row["local_track_id"]): row for row in frame_detections
        }
        for association in frame_associations:
            detection = detection_by_local.get(str(association["local_track_id"]))
            if detection is None:
                continue
            track_id = str(association["global_track_id"])
            bbox = _bbox(detection)
            area = max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
            pixel_error = _optional_float(association.get("pixel_error"))
            rank = (area, -(pixel_error if pixel_error is not None else math.inf))
            key = (track_id, owner)
            previous = best_candidates.get(key)
            if previous is None or rank > previous["rank"]:
                crop = _magnified_crop(image, bbox, track_id=track_id, owner=owner)
                crop_dir = crop_root / _safe_name(track_id)
                crop_dir.mkdir(parents=True, exist_ok=True)
                crop_path = crop_dir / f"{_safe_name(owner)}_best.png"
                cv2.imwrite(str(crop_path), crop)
                best_candidates[key] = {
                    "rank": rank,
                    "path": crop_path,
                    "frame_index": frame_index,
                    "timestamp": float(snapshot.get("logical_timestamp", 0.0)),
                    "local_track_id": str(association["local_track_id"]),
                    "pixel_error": pixel_error,
                    "mahalanobis_d2": _optional_float(association.get("mahalanobis_d2")),
                }

    manifest_path = _write_csv(evidence_root / "visual_evidence_manifest.csv", manifest_rows)
    paths: dict[str, Path] = {
        "visual_evidence_directory": evidence_root,
        "visual_evidence_manifest_csv": manifest_path,
    }

    overview_path = _write_camera_overview(
        evidence_root / "camera_registration_overview.png",
        annotated_by_owner,
        center_vehicle_name=center_vehicle_name,
        interceptor_vehicle_name=interceptor_vehicle_name,
    )
    if overview_path is not None:
        paths["camera_registration_overview"] = overview_path

    for owner, key in (
        (center_vehicle_name, "center_raw_vs_annotated"),
        (interceptor_vehicle_name, "interceptor_raw_vs_annotated"),
    ):
        comparison = _write_raw_annotated_comparison(
            evidence_root / f"{_safe_name(owner)}_raw_vs_annotated.png",
            annotated_by_owner.get(owner, []),
        )
        if comparison is not None:
            paths[key] = comparison

    shared_track_ids = sorted(
        {
            track_id
            for track_id, owner in best_candidates
            if owner == center_vehicle_name
            and (track_id, interceptor_vehicle_name) in best_candidates
        }
    )
    panel_paths: list[Path] = []
    for track_id in shared_track_ids:
        panel = _write_handover_panel(
            handover_root / f"{_safe_name(track_id)}.png",
            track_id=track_id,
            center=best_candidates[(track_id, center_vehicle_name)],
            interceptor=best_candidates[(track_id, interceptor_vehicle_name)],
        )
        panel_paths.append(panel)
    gallery_paths = _write_handover_galleries(evidence_root, panel_paths)
    for index, path in enumerate(gallery_paths, start=1):
        paths[f"handover_gallery_{index:02d}"] = path

    timeline = _write_assignment_timeline(
        evidence_root / "registration_timeline.png", association_rows
    )
    if timeline is not None:
        paths["registration_timeline"] = timeline
    error_plot = _write_error_distribution(
        evidence_root / "registration_error_distribution.png", association_rows
    )
    if error_plot is not None:
        paths["registration_error_distribution"] = error_plot
    confusion = _write_offline_confusion_matrix(
        evidence_root / "offline_registration_confusion_matrix.png", accuracy_rows
    )
    if confusion is not None:
        paths["offline_registration_confusion_matrix"] = confusion

    evidence_metrics = {
        "schema_version": "d5-long-range-visual-evidence-v1",
        "raw_snapshot_count": sum(bool(row.get("saved")) for row in snapshot_rows),
        "annotated_snapshot_count": len(manifest_rows),
        "annotated_center_count": len(annotated_by_owner.get(center_vehicle_name, [])),
        "annotated_interceptor_count": len(
            annotated_by_owner.get(interceptor_vehicle_name, [])
        ),
        "shared_track_handover_panel_count": len(panel_paths),
        "shared_track_handover_ratio": (
            len(panel_paths) / int(metrics.get("target_count", 0))
            if int(metrics.get("target_count", 0)) > 0
            else None
        ),
        "decode_failure_count": len(decode_failures),
        "decode_failures": decode_failures,
        "online_overlay_truth_identity_used": False,
        "offline_confusion_matrix_truth_identity_used": confusion is not None,
    }
    report = _write_visual_report(
        evidence_root / "D5_VISUAL_REGISTRATION_EFFECT_REPORT_CN.md",
        metrics=metrics,
        evidence_metrics=evidence_metrics,
        paths=paths,
        gallery_paths=gallery_paths,
    )
    paths["visual_registration_effect_report"] = report
    return paths, evidence_metrics


def _annotate_frame(
    image: np.ndarray,
    *,
    snapshot: Mapping[str, Any],
    detections: Sequence[Mapping[str, Any]],
    associations: Mapping[str, Mapping[str, Any]],
) -> np.ndarray:
    import cv2  # type: ignore

    output = image.copy()
    for detection in detections:
        local_id = str(detection["local_track_id"])
        association = associations.get(local_id)
        x1, y1, x2, y2 = (int(round(value)) for value in _bbox(detection))
        if association is None:
            color = (150, 150, 150)
            label = f"{_short_local_id(local_id)} unassigned"
        else:
            track_id = str(association["global_track_id"])
            color = _track_color(track_id)
            label = f"{_short_local_id(local_id)} -> {track_id}"
            projected_u = _optional_float(association.get("projected_u"))
            projected_v = _optional_float(association.get("projected_v"))
            if projected_u is not None and projected_v is not None:
                projected = (int(round(projected_u)), int(round(projected_v)))
                measured = (
                    int(round(float(association["bbox_center_u"]))),
                    int(round(float(association["bbox_center_v"]))),
                )
                cv2.drawMarker(
                    output,
                    projected,
                    color,
                    markerType=cv2.MARKER_CROSS,
                    markerSize=22,
                    thickness=2,
                )
                cv2.line(output, projected, measured, color, 1, cv2.LINE_AA)
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 3)
        _put_label(output, label, x1, y1, color)
    reasons = str(snapshot.get("capture_reasons", "periodic"))
    header = (
        f"{snapshot.get('camera_vehicle_name', '')}  frame={int(snapshot.get('frame_index', 0))}  "
        f"t={float(snapshot.get('logical_timestamp', 0.0)):.2f}s  "
        f"det={len(detections)}  matched={len(associations)}  {reasons}"
    )
    cv2.rectangle(output, (0, 0), (output.shape[1], 48), (20, 20, 20), -1)
    cv2.putText(
        output,
        header,
        (12, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.78,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return output


def _magnified_crop(
    image: np.ndarray,
    bbox: tuple[float, float, float, float],
    *,
    track_id: str,
    owner: str,
) -> np.ndarray:
    import cv2  # type: ignore

    height, width = image.shape[:2]
    x1, y1, x2, y2 = bbox
    center_x = 0.5 * (x1 + x2)
    center_y = 0.5 * (y1 + y2)
    span = max(48.0, 3.0 * max(x2 - x1, y2 - y1, 1.0))
    left = max(0, int(math.floor(center_x - span * 0.5)))
    right = min(width, int(math.ceil(center_x + span * 0.5)))
    top = max(0, int(math.floor(center_y - span * 0.5)))
    bottom = min(height, int(math.ceil(center_y + span * 0.5)))
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        crop = np.zeros((80, 80, 3), dtype=np.uint8)
    # Nearest-neighbour enlargement preserves the actual long-range pixels.
    resized = cv2.resize(crop, (420, 280), interpolation=cv2.INTER_NEAREST)
    scale_x = 420.0 / max(1, right - left)
    scale_y = 280.0 / max(1, bottom - top)
    rx1 = int(round((x1 - left) * scale_x))
    ry1 = int(round((y1 - top) * scale_y))
    rx2 = int(round((x2 - left) * scale_x))
    ry2 = int(round((y2 - top) * scale_y))
    color = _track_color(track_id)
    cv2.rectangle(resized, (rx1, ry1), (rx2, ry2), color, 3)
    cv2.rectangle(resized, (0, 0), (420, 34), (20, 20, 20), -1)
    cv2.putText(
        resized,
        f"{owner}  {track_id}  pixel zoom",
        (8, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return resized


def _write_camera_overview(
    path: Path,
    annotated_by_owner: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    center_vehicle_name: str,
    interceptor_vehicle_name: str,
) -> Path | None:
    import cv2  # type: ignore

    selected = []
    for owner in (center_vehicle_name, interceptor_vehicle_name):
        entries = list(annotated_by_owner.get(owner, []))
        if not entries:
            continue
        selected.append(max(entries, key=lambda row: int(row["association_count"])))
    if not selected:
        return None
    tiles = []
    for entry in selected:
        image = cv2.imread(str(entry["annotated_path"]), cv2.IMREAD_COLOR)
        if image is not None:
            tiles.append(_fit_tile(image, 960, 600))
    if not tiles:
        return None
    if len(tiles) == 1:
        canvas = tiles[0]
    else:
        canvas = np.hstack(tiles)
    cv2.imwrite(str(path), canvas)
    return path


def _write_raw_annotated_comparison(
    path: Path,
    entries: Sequence[Mapping[str, Any]],
) -> Path | None:
    import cv2  # type: ignore

    if not entries:
        return None
    entry = max(entries, key=lambda row: int(row["association_count"]))
    raw = cv2.imread(str(entry["raw_path"]), cv2.IMREAD_COLOR)
    annotated = cv2.imread(str(entry["annotated_path"]), cv2.IMREAD_COLOR)
    if raw is None or annotated is None:
        return None
    canvas = np.hstack((_fit_tile(raw, 960, 600), _fit_tile(annotated, 960, 600)))
    cv2.putText(canvas, "RAW CAMERA VIEW", (20, 580), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(canvas, "ONLINE REGISTRATION OVERLAY", (980, 580), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(str(path), canvas)
    return path


def _write_handover_panel(
    path: Path,
    *,
    track_id: str,
    center: Mapping[str, Any],
    interceptor: Mapping[str, Any],
) -> Path:
    import cv2  # type: ignore

    left = cv2.imread(str(center["path"]), cv2.IMREAD_COLOR)
    right = cv2.imread(str(interceptor["path"]), cv2.IMREAD_COLOR)
    canvas = np.full((360, 960, 3), 245, dtype=np.uint8)
    canvas[55:335, 20:440] = left
    canvas[55:335, 520:940] = right
    color = _track_color(track_id)
    cv2.putText(canvas, f"CENTER  {_short_local_id(str(center['local_track_id']))}", (20, 43), cv2.FONT_HERSHEY_SIMPLEX, 0.58, color, 2, cv2.LINE_AA)
    cv2.putText(canvas, f"INTERCEPTOR  {_short_local_id(str(interceptor['local_track_id']))}", (520, 43), cv2.FONT_HERSHEY_SIMPLEX, 0.58, color, 2, cv2.LINE_AA)
    cv2.arrowedLine(canvas, (448, 195), (512, 195), color, 3, tipLength=0.2)
    cv2.putText(canvas, track_id, (447, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.58, color, 2, cv2.LINE_AA)
    cv2.imwrite(str(path), canvas)
    return path


def _write_handover_galleries(output_dir: Path, panels: Sequence[Path]) -> list[Path]:
    import cv2  # type: ignore

    paths: list[Path] = []
    page_size = 4
    for page_index in range(0, len(panels), page_size):
        images = [cv2.imread(str(path), cv2.IMREAD_COLOR) for path in panels[page_index:page_index + page_size]]
        images = [image for image in images if image is not None]
        if not images:
            continue
        while len(images) < page_size:
            images.append(np.full_like(images[0], 245))
        canvas = np.vstack(images)
        path = output_dir / f"cross_view_handover_gallery_{page_index // page_size + 1:02d}.png"
        cv2.imwrite(str(path), canvas)
        paths.append(path)
    return paths


def _write_assignment_timeline(
    path: Path, association_rows: Sequence[Mapping[str, Any]]
) -> Path | None:
    if not association_rows:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(12, 7))
    owners = sorted({_camera_owner(str(row["camera_id"])) for row in association_rows})
    markers = ("o", "x", "s", "^")
    for index, owner in enumerate(owners):
        rows = [row for row in association_rows if _camera_owner(str(row["camera_id"])) == owner]
        axis.scatter(
            [float(row["measurement_timestamp"]) for row in rows],
            [_track_number(str(row["global_track_id"])) for row in rows],
            s=10,
            alpha=0.65,
            marker=markers[index % len(markers)],
            label=owner,
        )
    axis.set_xlabel("Logical time (s)")
    axis.set_ylabel("Assigned GlobalTrack number")
    axis.set_yticks(sorted({_track_number(str(row["global_track_id"])) for row in association_rows}))
    axis.grid(alpha=0.2)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def _write_error_distribution(
    path: Path, association_rows: Sequence[Mapping[str, Any]]
) -> Path | None:
    values_by_owner: dict[str, list[float]] = {}
    for row in association_rows:
        value = _optional_float(row.get("pixel_error"))
        if value is not None:
            values_by_owner.setdefault(_camera_owner(str(row["camera_id"])), []).append(value)
    if not values_by_owner:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(9, 5))
    for owner, values in sorted(values_by_owner.items()):
        ordered = np.sort(np.asarray(values, dtype=float))
        cumulative = np.arange(1, len(ordered) + 1, dtype=float) / len(ordered)
        axis.plot(ordered, cumulative, label=owner)
    axis.set_xlabel("Projection-to-detection pixel error")
    axis.set_ylabel("Cumulative ratio")
    axis.set_xlim(left=0.0)
    axis.set_ylim(0.0, 1.02)
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def _write_offline_confusion_matrix(
    path: Path, accuracy_rows: Sequence[Mapping[str, Any]]
) -> Path | None:
    valid = [row for row in accuracy_rows if row.get("truth_global_track_id")]
    if not valid:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = sorted(
        {str(row["global_track_id"]) for row in valid}
        | {str(row["truth_global_track_id"]) for row in valid}
    )
    index = {label: position for position, label in enumerate(labels)}
    matrix = np.zeros((len(labels), len(labels)), dtype=int)
    for row in valid:
        matrix[index[str(row["truth_global_track_id"])], index[str(row["global_track_id"])]] += 1
    figure, axis = plt.subplots(figsize=(10, 9))
    image = axis.imshow(matrix, cmap="Blues", interpolation="nearest")
    axis.set_xticks(range(len(labels)), labels, rotation=90, fontsize=7)
    axis.set_yticks(range(len(labels)), labels, fontsize=7)
    axis.set_xlabel("Assigned GlobalTrack (offline score)")
    axis.set_ylabel("Truth target (offline score only)")
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def _write_visual_report(
    path: Path,
    *,
    metrics: Mapping[str, Any],
    evidence_metrics: Mapping[str, Any],
    paths: Mapping[str, Path],
    gallery_paths: Sequence[Path],
) -> Path:
    mot = metrics.get("mot_continuity", {}).get("aggregate", {})
    lines = [
        "# D5 长距离视觉配准效果报告",
        "",
        "## 结论",
        "",
        (
            f"本轮中心相机累计发现{metrics.get('center_unique_discovery_count', 0)}/"
            f"{metrics.get('target_count', 0)}个目标，可评分配准准确率为"
            f"{_ratio(metrics.get('association_accuracy'))}。连续可见段身份切换为"
            f"{mot.get('id_switch_count', '不可用')}，短时轨迹中断为"
            f"{mot.get('fragmentation_count', '不可用')}。"
        ),
        (
            f"共保存{evidence_metrics.get('raw_snapshot_count', 0)}幅原始相机图，生成"
            f"{evidence_metrics.get('annotated_snapshot_count', 0)}幅在线配准标注图。"
            f"中心与拦截相机均形成图像证据的全局航迹为"
            f"{evidence_metrics.get('shared_track_handover_panel_count', 0)}个。"
        ),
        "",
        "## 图像说明",
        "",
        "原始相机图不含身份标注。标注图中的方框来自匿名检测，十字为中心航迹投影，连线表示投影点与检测框中心的偏差，`局部航迹 -> GlobalTrack`表示在线几何配准结果。目标局部图采用数字放大，只用于查看像素级证据。",
        "",
    ]
    for key, title in (
        ("camera_registration_overview", "中心与拦截相机配准视图"),
        ("center_raw_vs_annotated", "中心相机原图与标注对照"),
        ("interceptor_raw_vs_annotated", "拦截相机原图与标注对照"),
    ):
        if key in paths:
            lines.extend([f"### {title}", "", f"![{title}]({paths[key].name})", ""])
    if gallery_paths:
        lines.extend(["## 跨视角交接", ""])
        for index, gallery in enumerate(gallery_paths, start=1):
            lines.extend(
                [
                    f"### 航迹对照 {index}",
                    "",
                    f"![跨视角航迹对照{index}]({gallery.name})",
                    "",
                ]
            )
    lines.extend(["## 统计结果", ""])
    for key, title, note in (
        ("registration_timeline", "配准时间轴", "展示两台相机在各时刻绑定到的中心航迹。"),
        ("registration_error_distribution", "投影误差分布", "展示航迹投影点与检测框中心的像素偏差。"),
        ("offline_registration_confusion_matrix", "离线配准混淆矩阵", "该图仅使用离线真值评分，真值没有进入在线配准。"),
    ):
        if key in paths:
            lines.extend([f"### {title}", "", note, "", f"![{title}]({paths[key].name})", ""])
    lines.extend(
        [
            "## 边界",
            "",
            "在线叠加图不使用AirSim Actor名称、对象编号或真实全局身份。当前中心航迹来自合成夹具，尚未注入真实雷达误差、相机位姿误差、时间同步误差、漏检和虚警。本报告反映ComputerVision接口和几何配准链路，不代表实装光电设备性能。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _fit_tile(image: np.ndarray, width: int, height: int) -> np.ndarray:
    import cv2  # type: ignore

    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    scale = min(width / image.shape[1], height / image.shape[0])
    resized = cv2.resize(
        image,
        (max(1, int(round(image.shape[1] * scale))), max(1, int(round(image.shape[0] * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    x = (width - resized.shape[1]) // 2
    y = (height - resized.shape[0]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas


def _put_label(image: np.ndarray, label: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    import cv2  # type: ignore

    baseline_y = max(22, y - 8)
    size, _baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    cv2.rectangle(
        image,
        (max(0, x), max(0, baseline_y - size[1] - 7)),
        (min(image.shape[1] - 1, x + size[0] + 6), min(image.shape[0] - 1, baseline_y + 4)),
        (20, 20, 20),
        -1,
    )
    cv2.putText(image, label, (max(0, x + 3), baseline_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)


def _bbox(row: Mapping[str, Any]) -> tuple[float, float, float, float]:
    return (
        float(row["bbox_x1"]),
        float(row["bbox_y1"]),
        float(row["bbox_x2"]),
        float(row["bbox_y2"]),
    )


def _track_color(track_id: str) -> tuple[int, int, int]:
    palette = (
        (52, 152, 219),
        (46, 204, 113),
        (0, 196, 255),
        (180, 105, 255),
        (40, 130, 255),
        (200, 200, 60),
    )
    return palette[(_track_number(track_id) - 1) % len(palette)]


def _track_number(track_id: str) -> int:
    digits = "".join(character for character in str(track_id) if character.isdigit())
    return int(digits or 0)


def _short_local_id(local_id: str) -> str:
    suffix = str(local_id).rsplit(":", 1)[-1]
    return suffix[-10:]


def _camera_owner(camera_id: str) -> str:
    return str(camera_id).split(":", 1)[0]


def _safe_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in str(value))


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _resolve_existing_path(value: Any) -> Path:
    path = Path(str(value))
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        if fields:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    return path


def _ratio(value: Any) -> str:
    numeric = _optional_float(value)
    return "不可用" if numeric is None else f"{numeric:.3f}"


__all__ = ["write_long_range_registration_visual_evidence"]
