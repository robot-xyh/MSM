"""Artifacts, two-view geometry figures, and Chinese experiment report."""

from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
from typing import Sequence
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
    import matplotlib

matplotlib.use("Agg")
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
    import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

from ..common.contracts import LocalVisualTrackRecord
from ..common.io import write_json, write_jsonl
from .contracts import CrossViewResult, OfflineTruthLabels, split_track_key, track_key
from .evaluation import build_offline_error_samples


MAX_PLOTTED_RELATIONS = 200
MAX_PLOTTED_CAMERAS = 20


def _even_camera_sample(camera_ids: Sequence[str]) -> tuple[str, ...]:
    ordered = tuple(sorted(camera_ids))
    if len(ordered) <= MAX_PLOTTED_CAMERAS:
        return ordered
    indices = np.linspace(
        0,
        len(ordered) - 1,
        MAX_PLOTTED_CAMERAS,
        dtype=int,
    )
    return tuple(ordered[int(index)] for index in indices)


def _configure_matplotlib() -> None:
    bundled_candidates = (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    )
    for font_path in bundled_candidates:
        if font_path.exists():
            font_manager.fontManager.addfont(str(font_path))
            selected = font_manager.FontProperties(fname=str(font_path)).get_name()
            break
    else:
        selected = ""
    candidates = (
        "Noto Sans CJK SC",
        "Source Han Sans CN",
        "WenQuanYi Micro Hei",
        "Microsoft YaHei",
        "SimHei",
        "DejaVu Sans",
    )
    installed = {item.name for item in font_manager.fontManager.ttflist}
    if not selected:
        selected = next((value for value in candidates if value in installed), "DejaVu Sans")
    plt.rcParams.update(
        {
            "font.family": selected,
            "axes.unicode_minus": False,
            "figure.dpi": 130,
        }
    )


def _latest_by_track(
    records: Sequence[LocalVisualTrackRecord],
) -> dict[str, LocalVisualTrackRecord]:
    latest: dict[str, LocalVisualTrackRecord] = {}
    for record in records:
        key = track_key(record.camera_id, record.local_track_id)
        if key not in latest or latest[key].measurement_timestamp < record.measurement_timestamp:
            latest[key] = record
    return latest


def _plot_ned_views(
    path: Path,
    result: CrossViewResult,
    records: Sequence[LocalVisualTrackRecord],
) -> None:
    """Use top and side views because this host cannot import Axes3D safely."""

    _configure_matplotlib()
    latest = _latest_by_track(records)
    selected_relations = {(item.key_a, item.key_b) for item in result.matches}
    selected_by_relation = {}
    for item in result.candidates:
        relation = (item.key_a, item.key_b)
        if item.midpoint_ned_m is None or relation not in selected_relations:
            continue
        selected_by_relation.setdefault(relation, item)
        if len(selected_by_relation) >= MAX_PLOTTED_RELATIONS:
            break
    candidates = list(selected_by_relation.values())
    if not candidates:
        candidates = [
            item
            for item in result.candidates
            if item.midpoint_ned_m is not None and item.gate_passed
        ][:30]
    figure, (top, side) = plt.subplots(1, 2, figsize=(12.5, 5.2), constrained_layout=True)
    camera_origins: dict[str, tuple[float, float, float]] = {}
    for record in latest.values():
        camera_origins.setdefault(record.camera_id, record.ray_origin_ned_m)
    for camera_id, origin in sorted(camera_origins.items()):
        top.scatter(origin[0], origin[1], marker="^", s=55, color="#185FA5")
        top.text(origin[0], origin[1], camera_id.replace("Terminal_CV_", "C"), fontsize=8)
        side.scatter(origin[0], origin[2], marker="^", s=55, color="#185FA5")
    for candidate in candidates:
        midpoint = candidate.midpoint_ned_m
        if midpoint is None:
            continue
        for key in (candidate.key_a, candidate.key_b):
            record = latest.get(key)
            if record is None:
                continue
            origin = record.ray_origin_ned_m
            top.plot((origin[0], midpoint[0]), (origin[1], midpoint[1]), color="#7A8A99", alpha=0.28)
            side.plot((origin[0], midpoint[0]), (origin[2], midpoint[2]), color="#7A8A99", alpha=0.28)
        top.scatter(midpoint[0], midpoint[1], s=18, color="#D1495B")
        side.scatter(midpoint[0], midpoint[2], s=18, color="#D1495B")
    top.set(title="NED俯视关系", xlabel="北向 / 米", ylabel="东向 / 米")
    side.set(title="NED高度侧视关系", xlabel="北向 / 米", ylabel="下向 / 米")
    top.grid(alpha=0.25)
    side.grid(alpha=0.25)
    figure.savefig(path)
    plt.close(figure)


def _plot_pixel_tracks(path: Path, records: Sequence[LocalVisualTrackRecord]) -> None:
    _configure_matplotlib()
    histories: dict[str, list[LocalVisualTrackRecord]] = defaultdict(list)
    for record in records:
        if record.recognized:
            histories[track_key(record.camera_id, record.local_track_id)].append(record)
    all_cameras = sorted({record.camera_id for record in records})
    cameras = list(_even_camera_sample(all_cameras))
    columns = min(4, max(1, len(cameras)))
    rows = max(1, math.ceil(len(cameras) / columns))
    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(14.0, 3.0 * rows),
        squeeze=False,
        constrained_layout=True,
    )
    for axis, camera_id in zip(axes.flat, cameras):
        for key, values in sorted(histories.items()):
            if split_track_key(key)[0] != camera_id:
                continue
            ordered = sorted(values, key=lambda item: item.measurement_timestamp)
            axis.plot(
                [item.center_px[0] for item in ordered],
                [item.center_px[1] for item in ordered],
                marker="o",
                markersize=2.5,
                linewidth=1.0,
            )
        axis.set_title(camera_id)
        axis.set_xlabel("水平像素")
        axis.set_ylabel("垂直像素")
        axis.invert_yaxis()
        axis.grid(alpha=0.2)
    for axis in axes.flat[len(cameras) :]:
        axis.axis("off")
    if len(cameras) < len(all_cameras):
        figure.suptitle(
            f"相机内像素航迹（均匀抽取{len(cameras)}/{len(all_cameras)}台相机）"
        )
    figure.savefig(path)
    plt.close(figure)


def _plot_relation_graph(path: Path, result: CrossViewResult) -> None:
    _configure_matplotlib()
    tracks = sorted(
        set(result.unresolved_track_keys)
        | {member for cluster in result.clusters for member in cluster.member_track_keys}
    )
    by_camera: dict[str, list[str]] = defaultdict(list)
    for value in tracks:
        by_camera[split_track_key(value)[0]].append(value)
    all_cameras = sorted(by_camera)
    cameras = list(_even_camera_sample(all_cameras))
    positions: dict[str, tuple[float, float]] = {}
    figure, axis = plt.subplots(
        figsize=(max(9.0, len(cameras) * 1.0), 7.0),
        constrained_layout=True,
    )
    for x, camera_id in enumerate(cameras):
        values = sorted(by_camera[camera_id])
        for y, value in enumerate(values):
            positions[value] = (float(x), float(y))
            axis.scatter(x, y, s=24, color="#185FA5")
            axis.text(x + 0.04, y, split_track_key(value)[1], fontsize=7, va="center")
    for match in result.matches:
        if match.key_a in positions and match.key_b in positions:
            left, right = positions[match.key_a], positions[match.key_b]
            axis.plot((left[0], right[0]), (left[1], right[1]), color="#2E8B57", alpha=0.65, linewidth=1.1)
    axis.set_xticks(range(len(cameras)), [value.replace("Terminal_CV_", "C") for value in cameras])
    axis.set_ylabel("相机内匿名局部航迹")
    title = "跨相机确认关系"
    if len(cameras) < len(all_cameras):
        title += f"（均匀抽取{len(cameras)}/{len(all_cameras)}台相机）"
    axis.set_title(title)
    axis.grid(axis="x", alpha=0.2)
    figure.savefig(path)
    plt.close(figure)


def _plot_candidate_costs(path: Path, result: CrossViewResult) -> None:
    _configure_matplotlib()
    passed = [item for item in result.candidates if item.gate_passed and item.final_cost is not None]
    if not passed:
        passed = list(result.candidates[:1])
    costs = np.asarray([float(item.final_cost if item.final_cost is not None else item.geometry_cost) for item in passed])
    figure, axis = plt.subplots(figsize=(10.5, 4.5), constrained_layout=True)
    axis.plot(np.arange(len(costs)), np.sort(costs), color="#185FA5", linewidth=1.5)
    axis.axhline(1.05, color="#D1495B", linestyle="--", label="空匹配代价")
    title = (
        "候选边代价审计样本"
        if result.audit.omitted_candidate_count
        else "候选边代价分布"
    )
    axis.set(title=title, xlabel="按代价排序的候选边", ylabel="代价")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.savefig(path)
    plt.close(figure)


def _report_text(
    result: CrossViewResult,
    truth: OfflineTruthLabels | None,
    figure_paths: Sequence[Path],
) -> str:
    metrics = result.metrics
    scenario = truth.scenario_name if truth is not None else "AirSim detect在线采集"
    seed = str(truth.seed) if truth is not None else "由main运行时提供"
    precision = (
        f"{metrics.association_precision:.4f}"
        if metrics.association_precision is not None
        else "不可用"
    )
    recall = (
        f"{metrics.association_recall:.4f}"
        if metrics.association_recall is not None
        else "不可用"
    )
    relative_figures = [f"figures/{path.name}" for path in figure_paths]
    return f"""# 拦截无人机跨视角关联实验报告

## 结论

本轮运行采用 `{result.backend}` 关联后端、`{result.audit.camera_pair_policy}` 相机对策略和 `{result.audit.output_mode}` 输出模式。输入中形成 {metrics.recognized_track_count} 条达到10像素门限的相机内局部航迹，最终确认 {metrics.confirmed_relation_count} 条跨相机关系，形成 {metrics.cluster_count} 个多相机统一目标簇，仍有 {metrics.unresolved_track_count} 条局部航迹缺少共同几何证据。每个统一目标在同一相机内最多保留一条局部航迹，违规数为 {metrics.camera_uniqueness_violation_count}。

离线评分精确率为 {precision}，召回率为 {recall}。这些数据来自场景 `{scenario}`、种子 `{seed}` 的独立回放，仅用于检查配准算法。AirSim Actor名称和真实身份没有进入在线候选生成、几何门控、图网络或匈牙利分配，在线真值泄漏计数为 {metrics.truth_leakage_count}。

## 输入与边界

每台ComputerVision相机先在本机生成匿名局部航迹。检测框最长边小于10像素时只保留原始检测状态，不进入跨视角关联。在线记录包含检测框、像素中心、相机位置姿态、测量时间、到达时间和航迹质量，不包含Actor名称或真实目标编号。

本专项不启动AirSim Blocks，不承担中心双光电线索有效期管理，也不依赖D1、D2、D3或D5主线。真实AirSim运行由main注入已经连接的client，并负责场景重置和Actor运动。

## 算法流程

算法先把检测框中心按针孔模型反投影到NED坐标系中的单位视线。两台相机的异步观测插值到共同时间，再计算两条视线的最近交会点。交会夹角过小、两条视线间距过大、重投影误差过大、运动拟合残差过大或运动方向突变时，候选关系被拒绝。

通过硬几何门控的候选进入带空匹配项的匈牙利算法。空匹配允许航迹保持未解决状态，避免在没有共同目标时强制合并。相同关系需要在{result.matches[0].confirmation_count if result.matches else 2}次有效观测中连续成立后才能确认。目标交叉期间，已经确认的关系保持锁定，单帧最近距离不能直接更换身份。

多相机结果按候选代价从低到高聚合。合并两个目标簇前先检查相机集合；若合并后同一相机会出现两条局部航迹，则拒绝该关系。图神经网络模式只对硬几何门控后的稀疏候选边重新排序，最终仍经过匈牙利一一约束和连续确认。

## 结果

| 指标 | 数值 |
| --- | ---: |
| 候选边记录数 | {metrics.candidate_edge_count} |
| 通过几何门控的候选边 | {metrics.geometry_passed_edge_count} |
| 相机对总数 | {result.audit.camera_pair_total_count} |
| 保留相机对 | {result.audit.camera_pair_retained_count} |
| 剔除相机对 | {result.audit.camera_pair_pruned_count} |
| 已确认跨相机关系 | {metrics.confirmed_relation_count} |
| 待确认关系 | {metrics.tentative_relation_count} |
| 未解决局部航迹 | {metrics.unresolved_track_count} |
| 统一目标簇 | {metrics.cluster_count} |
| 关联精确率 | {precision} |
| 关联召回率 | {recall} |
| 身份混合簇数量 | {metrics.id_switch_count if metrics.id_switch_count is not None else '不可用'} |

![NED俯视和高度侧视]({relative_figures[0]})

![相机内像素轨迹]({relative_figures[1]})

![跨相机关系]({relative_figures[2]})

![候选代价]({relative_figures[3]})

## 限制

当前fixture采用准确的相机内外参和轻微像素噪声，未叠加导航误差、云台误差、时间同步漂移和真实检测器误差。图神经网络只是候选排序后端，是否优于几何基线必须使用与训练、验证种子隔离的AirSim留出数据判断。没有共同视场或可靠交接证据的航迹保持未解决，不以提高召回率为由强制建立关系。

当输出模式为`audit`时，候选代价图只显示限量审计样本；完整候选数量和各阶段数量以`candidate_audit.json`中的计数为准。
"""


def write_experiment_outputs(
    output_dir: Path,
    result: CrossViewResult,
    records: Sequence[LocalVisualTrackRecord],
    *,
    truth: OfflineTruthLabels | None = None,
    output_mode: str = "detailed",
    error_sample_limit: int = 100,
) -> tuple[Path, Path]:
    if output_mode not in {"detailed", "audit"}:
        raise ValueError("output_mode must be detailed or audit")
    if result.audit.output_mode != output_mode:
        raise ValueError("result and writer output modes disagree")
    output_dir.mkdir(parents=True, exist_ok=True)
    figures = output_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    online_payload = result.to_online_dict()
    confirmed_relation_keys = {
        (match.key_a, match.key_b) for match in result.matches
    }
    write_jsonl(output_dir / "matches.jsonl", result.matches)
    if output_mode == "detailed":
        write_jsonl(output_dir / "candidate_edges.jsonl", result.candidates)
        write_json(output_dir / "candidate_graph.json", {
            "schema_version": "terminal-crossview-candidate-graph-v1",
            "nodes": sorted(
                set(result.unresolved_track_keys)
                | {member for cluster in result.clusters for member in cluster.member_track_keys}
            ),
            "edges": [
                {
                    "left": item.key_a,
                    "right": item.key_b,
                    "cost": item.final_cost,
                    "gate_passed": item.gate_passed,
                    "decision_state": (
                        "confirmed"
                        if (item.key_a, item.key_b) in confirmed_relation_keys
                        else "candidate"
                    ),
                }
                for item in result.candidates
            ],
        })
    else:
        for stale_name in ("candidate_edges.jsonl", "candidate_graph.json"):
            stale_path = output_dir / stale_name
            if stale_path.exists():
                stale_path.unlink()
    written_candidate_samples = (
        result.candidates
        if output_mode == "audit"
        else result.candidates[:200]
    )
    write_json(
        output_dir / "candidate_audit.json",
        {
            **result.audit.to_dict(),
            "written_candidate_sample_count": len(written_candidate_samples),
            "candidate_samples": [
                item.to_dict() for item in written_candidate_samples
            ],
        },
    )
    write_json(output_dir / "clusters.json", [item.to_dict() for item in result.clusters])
    write_json(output_dir / "pending_relations.json", [item.to_dict() for item in result.pending_relations])
    write_json(output_dir / "unresolved_relations.json", {
        "track_keys": result.unresolved_track_keys,
        "policy": "remain_unresolved_without_common_geometry",
    })
    metrics_path = write_json(output_dir / "metrics.json", result.metrics.to_dict())
    write_json(output_dir / "online_result.json", online_payload)
    if truth is not None:
        write_json(output_dir / "offline_truth_score.json", {
            "offline_only": True,
            "scenario_name": truth.scenario_name,
            "seed": truth.seed,
            "metrics": result.metrics.to_dict(),
        })
        write_json(
            output_dir / "truth" / "offline_error_samples.json",
            build_offline_error_samples(
                result,
                truth,
                limit=error_sample_limit,
            ),
        )
    figure_paths = (
        figures / "01_ned_top_and_height_views.png",
        figures / "02_local_pixel_tracks.png",
        figures / "03_crossview_relation_graph.png",
        figures / "04_candidate_costs.png",
    )
    _plot_ned_views(figure_paths[0], result, records)
    _plot_pixel_tracks(figure_paths[1], records)
    _plot_relation_graph(figure_paths[2], result)
    _plot_candidate_costs(figure_paths[3], result)
    report_path = output_dir / "REPORT_CN.md"
    report_path.write_text(
        _report_text(result, truth, figure_paths), encoding="utf-8"
    )
    return metrics_path, report_path
