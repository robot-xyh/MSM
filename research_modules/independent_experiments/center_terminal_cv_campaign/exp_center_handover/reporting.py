"""Metrics, two-dimensional figures, and Chinese report generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: E402
    from matplotlib.patches import Ellipse  # noqa: E402
import numpy as np

from ..common import LocalVisualTrackRecord, SourceCueTruthLabel
from ..common.io import write_json, write_jsonl
from .association import FrameAssociationResult
from .fixture import HandoverFixture, LocalTrackTruthLabel


@dataclass(frozen=True)
class OutputPaths:
    metrics: Path
    report: Path
    candidates: Path
    associations: Path
    local_tracks: Path
    projection_figure: Path
    matrix_figure: Path


def write_experiment_outputs(
    *,
    output_dir: Path,
    fixture: HandoverFixture,
    frames: Sequence[Sequence[LocalVisualTrackRecord]],
    results: Sequence[FrameAssociationResult],
    mode: str,
    backend: str,
    model_metadata: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], OutputPaths]:
    output_dir.mkdir(parents=True, exist_ok=True)
    online_dir = output_dir / "online"
    truth_dir = output_dir / "truth"
    figures_dir = output_dir / "figures"
    candidates_path = write_jsonl(
        online_dir / "candidates.jsonl",
        (candidate.to_dict() for result in results for candidate in result.candidates),
    )
    associations_path = write_jsonl(
        online_dir / "associations.jsonl",
        (decision for result in results for decision in result.decisions),
    )
    local_tracks_path = write_jsonl(
        online_dir / "local_tracks.jsonl",
        (track for frame in frames for track in frame),
    )
    write_jsonl(online_dir / "source_cues.jsonl", fixture.source_cues)
    if fixture.source_truth:
        write_jsonl(truth_dir / "source_cue_labels.jsonl", fixture.source_truth)
    if fixture.local_truth:
        write_jsonl(truth_dir / "local_track_labels.jsonl", fixture.local_truth)

    metrics = score_association(fixture, results, mode=mode, backend=backend)
    metrics["truth_leakage_count"] = online_truth_leakage_count(online_dir)
    if model_metadata:
        metrics["gnn_validation"] = dict(model_metadata.get("validation_metrics", {}))
        metrics["gnn_train_seed_count"] = len(model_metadata.get("train_seeds", ()))
        metrics["gnn_validation_seed_count"] = len(model_metadata.get("validation_seeds", ()))
    metrics_path = write_json(output_dir / "metrics.json", metrics)
    projection_path = figures_dir / "projection_ellipse_matching.png"
    matrix_path = figures_dir / "matching_cost_matrix.png"
    plot_projection_and_matches(projection_path, frames[-1], results[-1])
    plot_cost_matrix(matrix_path, fixture, frames[-1], results[-1])
    report_path = output_dir / "REPORT_CN.md"
    report_path.write_text(
        build_chinese_report(metrics, mode=mode, backend=backend), encoding="utf-8"
    )
    write_json(
        output_dir / "manifest.json",
        {
            "schema_version": "center-handover-output-v1",
            "mode": mode,
            "association_backend": backend,
            "online_truth_allowed": False,
            "metrics": "metrics.json",
            "report": "REPORT_CN.md",
            "figures": [
                "figures/projection_ellipse_matching.png",
                "figures/matching_cost_matrix.png",
            ],
        },
    )
    return metrics, OutputPaths(
        metrics=metrics_path,
        report=report_path,
        candidates=candidates_path,
        associations=associations_path,
        local_tracks=local_tracks_path,
        projection_figure=projection_path,
        matrix_figure=matrix_path,
    )


def score_association(
    fixture: HandoverFixture,
    results: Sequence[FrameAssociationResult],
    *,
    mode: str,
    backend: str,
) -> dict[str, Any]:
    final_pairs = set(results[-1].confirmed_pairs) if results else set()
    final_result = results[-1] if results else None
    final_frame = fixture.frames[-1] if fixture.frames else ()
    unregistered_count = (
        len(final_result.unregistered_local_track_ids) if final_result is not None else 0
    )
    final_local_by_key = {
        (track.camera_id, track.local_track_id): track for track in final_frame
    }
    unregistered_decisions = (
        tuple(
            decision
            for decision in final_result.decisions
            if decision.decision_state == "unregistered_candidate"
        )
        if final_result is not None
        else ()
    )
    unregistered_tracks = tuple(
        track
        for decision in unregistered_decisions
        if (
            track := final_local_by_key.get(
                (str(decision.metadata.get("camera_id", "")), decision.left_track_id)
            )
        )
        is not None
    )
    base: dict[str, Any] = {
        "schema_version": "center-handover-metrics-v1",
        "mode": mode,
        "association_backend": backend,
        "target_count": fixture.scenario.target_count,
        "source_cue_count": len(fixture.source_cues),
        "frame_count": len(results),
        "confirmed_pair_count": len(final_pairs),
        "truth_metrics_available": bool(fixture.source_truth and fixture.local_truth),
        "recognition_rule": "bbox_longest_side_px_gte_10",
        "global_track_id_created_or_rewritten": 0,
        "final_frame_local_track_count": len(final_frame),
        "final_frame_recognized_local_track_count": sum(
            bool(track.recognized) for track in final_frame
        ),
        # Backward-compatible alias. Its unit has always been camera-local tracks.
        "unregistered_candidate_count": unregistered_count,
        "unregistered_candidate_count_semantics": (
            "final_frame_unmatched_camera_local_track_count"
        ),
        "unregistered_local_track_candidate_count": unregistered_count,
        "unregistered_recognized_local_track_candidate_count": sum(
            bool(track.recognized) for track in unregistered_tracks
        ),
        "unregistered_below_recognition_threshold_count": sum(
            not bool(track.recognized) for track in unregistered_tracks
        ),
    }
    if not fixture.source_truth or not fixture.local_truth:
        base.update(
            {
                "binding_precision": None,
                "binding_recall": None,
                "false_source_rejection_rate": None,
                "missed_target_wrong_binding_count": None,
                "unregistered_candidate_truth_breakdown_available": False,
                "unregistered_distinct_truth_target_count": None,
                "unregistered_registered_target_redundant_observation_count": None,
                "unregistered_registered_target_distinct_count": None,
                "unregistered_center_missed_target_observation_count": None,
                "unregistered_center_missed_target_distinct_count": None,
                "unregistered_correct_source_unbound_observation_count": None,
                "unregistered_correct_source_unbound_distinct_count": None,
                "unregistered_unknown_truth_label_count": None,
            }
        )
        return base
    source_truth = {label.source_track_id: label for label in fixture.source_truth}
    local_truth_by_key = {
        (label.camera_id, label.local_track_id): label.truth_target_id
        for label in fixture.local_truth
    }
    local_truth = {label.local_track_id: label.truth_target_id for label in fixture.local_truth}
    true_positive = false_positive = 0
    confirmed_sources: set[str] = set()
    for source_id, local_id in final_pairs:
        confirmed_sources.add(source_id)
        source_label = source_truth[source_id]
        if (
            source_label.is_correct_source
            and source_label.truth_target_id == local_truth.get(local_id)
        ):
            true_positive += 1
        else:
            false_positive += 1
    correct_sources = {key for key, value in source_truth.items() if value.is_correct_source}
    false_sources = set(source_truth) - correct_sources
    rejected_false_sources = false_sources - confirmed_sources
    correct_target_ids = {
        value.truth_target_id for value in source_truth.values() if value.is_correct_source
    }
    all_target_ids = {label.truth_target_id for label in fixture.local_truth}
    missed_target_ids = all_target_ids - correct_target_ids
    wrong_missed_bindings = sum(
        1
        for source_id, local_id in final_pairs
        if local_truth.get(local_id) in missed_target_ids
        and source_truth[source_id].truth_target_id != local_truth.get(local_id)
    )
    confirmed_target_ids = {
        local_truth_by_key[(str(decision.metadata.get("camera_id", "")), decision.right_track_id)]
        for decision in (final_result.decisions if final_result is not None else ())
        if decision.decision_state == "confirmed"
        and decision.right_track_id is not None
        and (str(decision.metadata.get("camera_id", "")), decision.right_track_id)
        in local_truth_by_key
    }
    unregistered_truth_ids = [
        local_truth_by_key.get(
            (str(decision.metadata.get("camera_id", "")), decision.left_track_id)
        )
        for decision in unregistered_decisions
    ]
    known_unregistered_truth_ids = {
        target_id for target_id in unregistered_truth_ids if target_id is not None
    }
    redundant_registered = [
        target_id for target_id in unregistered_truth_ids if target_id in confirmed_target_ids
    ]
    center_missed_observations = [
        target_id for target_id in unregistered_truth_ids if target_id in missed_target_ids
    ]
    correct_source_unbound = [
        target_id
        for target_id in unregistered_truth_ids
        if target_id in correct_target_ids and target_id not in confirmed_target_ids
    ]
    base.update(
        {
            "correct_source_count": len(correct_sources),
            "false_source_count": len(false_sources),
            "center_missed_target_count": len(missed_target_ids),
            "true_binding_count": true_positive,
            "false_binding_count": false_positive,
            "binding_precision": true_positive / max(true_positive + false_positive, 1),
            "binding_recall": true_positive / max(len(correct_sources), 1),
            "binding_recall_denominator": "correct_source_cues",
            "registered_target_fraction": true_positive / max(fixture.scenario.target_count, 1),
            "false_source_rejection_rate": len(rejected_false_sources)
            / max(len(false_sources), 1),
            "missed_target_wrong_binding_count": wrong_missed_bindings,
            "unregistered_candidate_truth_breakdown_available": True,
            "unregistered_distinct_truth_target_count": len(known_unregistered_truth_ids),
            "unregistered_registered_target_redundant_observation_count": len(
                redundant_registered
            ),
            "unregistered_registered_target_distinct_count": len(
                set(redundant_registered)
            ),
            "unregistered_center_missed_target_observation_count": len(
                center_missed_observations
            ),
            "unregistered_center_missed_target_distinct_count": len(
                set(center_missed_observations)
            ),
            "unregistered_correct_source_unbound_observation_count": len(
                correct_source_unbound
            ),
            "unregistered_correct_source_unbound_distinct_count": len(
                set(correct_source_unbound)
            ),
            "unregistered_unknown_truth_label_count": sum(
                target_id is None for target_id in unregistered_truth_ids
            ),
        }
    )
    return base


def online_truth_leakage_count(online_dir: Path) -> int:
    forbidden = ("truth_target_id", "actor_name", "raw_detection_name", "global_track_id")
    count = 0
    for path in online_dir.glob("*.jsonl"):
        text = path.read_text(encoding="utf-8")
        count += sum(text.count(value) for value in forbidden)
    return count


def plot_projection_and_matches(
    path: Path,
    frame: Sequence[LocalVisualTrackRecord],
    result: FrameAssociationResult,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    camera_counts: dict[str, int] = {}
    for local in frame:
        camera_counts[local.camera_id] = camera_counts.get(local.camera_id, 0) + 1
    camera_id = max(camera_counts, key=camera_counts.get) if camera_counts else "none"
    local_by_id = {local.local_track_id: local for local in frame if local.camera_id == camera_id}
    selected = {
        decision.right_track_id: decision.left_track_id
        for decision in result.decisions
        if decision.right_track_id is not None
        and decision.decision_state in {"selected_pending", "confirmed"}
        and decision.metadata.get("camera_id") == camera_id
    }
    best_candidates: dict[str, Any] = {}
    for candidate in result.candidates:
        if candidate.camera_id != camera_id or candidate.projected_center_px is None:
            continue
        current = best_candidates.get(candidate.source_track_id)
        if current is None or candidate.baseline_cost < current.baseline_cost:
            best_candidates[candidate.source_track_id] = candidate
    fig, axis = plt.subplots(figsize=(11.0, 6.2))
    for source_id, candidate in best_candidates.items():
        center = np.asarray(candidate.projected_center_px, dtype=float)
        covariance = np.asarray(candidate.projection_covariance_px2, dtype=float)
        values, vectors = np.linalg.eigh(covariance)
        order = np.argsort(values)[::-1]
        values = values[order]
        vectors = vectors[:, order]
        angle = np.degrees(np.arctan2(vectors[1, 0], vectors[0, 0]))
        ellipse = Ellipse(
            center,
            width=2.0 * math_sqrt(values[0]) * 2.0,
            height=2.0 * math_sqrt(values[1]) * 2.0,
            angle=angle,
            fill=False,
            edgecolor="#4472C4",
            linewidth=0.8,
            alpha=0.45,
        )
        axis.add_patch(ellipse)
        axis.scatter(center[0], center[1], marker="+", color="#4472C4", s=35)
        if source_id in selected.values():
            axis.annotate(source_id, center, fontsize=7, color="#2F5597")
    for local_id, local in local_by_id.items():
        axis.scatter(local.center_px[0], local.center_px[1], marker="o", color="#C00000", s=24)
        source_id = selected.get(local_id)
        if source_id is not None and source_id in best_candidates:
            projected = best_candidates[source_id].projected_center_px
            axis.plot(
                (projected[0], local.center_px[0]),
                (projected[1], local.center_px[1]),
                color="#70AD47",
                linewidth=1.2,
            )
    axis.set_title(f"Projection ellipses and selected matches - {camera_id}")
    axis.set_xlabel("u / px")
    axis.set_ylabel("v / px")
    axis.set_xlim(0.0, 1920.0)
    axis.set_ylim(1080.0, 0.0)
    axis.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def plot_cost_matrix(
    path: Path,
    fixture: HandoverFixture,
    frame: Sequence[LocalVisualTrackRecord],
    result: FrameAssociationResult,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sources = [source.source_track_id for source in fixture.source_cues]
    locals_ = [local.local_track_id for local in frame]
    matrix = np.full((len(sources), len(locals_)), np.nan, dtype=float)
    for candidate in result.candidates:
        if candidate.eligible:
            matrix[candidate.source_index, candidate.local_index] = candidate.assignment_cost
    fig, axis = plt.subplots(figsize=(10.5, 7.0))
    image = axis.imshow(np.ma.masked_invalid(matrix), aspect="auto", cmap="viridis_r")
    axis.set_title("Geometry-gated assignment cost")
    axis.set_xlabel("terminal local track index")
    axis.set_ylabel("center source track index")
    fig.colorbar(image, ax=axis, label="cost")
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def build_chinese_report(metrics: Mapping[str, Any], *, mode: str, backend: str) -> str:
    evidence = "离线固定场景" if mode == "offline" else "已运行AirSim实例采集"
    precision = _format_metric(metrics.get("binding_precision"))
    recall = _format_metric(metrics.get("binding_recall"))
    registered_fraction = _format_metric(metrics.get("registered_target_fraction"))
    false_rejection = _format_metric(metrics.get("false_source_rejection_rate"))
    unregistered_explanation = _unregistered_explanation(metrics)
    return f"""# 中心双光电到末端交接关联实验报告

## 结论

本次结果来自{evidence}，关联后端为 `{backend}`。中心输入按80%精度、80%召回率构造；该数值是实验条件，不是双光电设备实测指标。实验共处理{metrics['target_count']}个目标、{metrics['source_cue_count']}条中心源航迹和{metrics['frame_count']}帧末端观测。

已确认{metrics['confirmed_pair_count']}组中心源航迹与机载局部航迹。在具备正确中心源航迹的目标范围内，绑定精度为{precision}，绑定召回率为{recall}。按全部目标计算，已注册目标比例为{registered_fraction}。错误源航迹拒绝率为{false_rejection}。中心漏掉目标的错误套号数量为{metrics.get('missed_target_wrong_binding_count')}，在线记录中的真实编号泄漏数量为{metrics.get('truth_leakage_count')}。

{unregistered_explanation}

## 方法

源航迹从测量时刻按速度外推到图像时刻，六维状态协方差同步传播。目标位置依次转换到北东地坐标系、机体系、云台系和相机系，再按针孔模型投影到图像。位置协方差通过投影雅可比矩阵转换为像面预测椭圆，并与检测中心协方差合并计算马氏距离。

候选首先通过时间、10像素识别、马氏距离和运动连续性门控。剩余候选由带未匹配项的匈牙利算法统一选择。单帧结果只作待确认记录，三帧中至少两帧保持同一对应关系后才确认绑定。中心漏检目标保留机载临时编号，不套用其他中心源航迹编号。

图网络后端只对通过几何门的稀疏候选边重新评分。最终选择仍执行一一匹配和连续确认。被几何门拒绝的候选不会由图网络恢复。

## 图示

![投影椭圆与匹配](figures/projection_ellipse_matching.png)

![匹配代价](figures/matching_cost_matrix.png)

## 适用边界

本专项假定搜索已经完成。采集适配器保留全部detect观测用于审计，只有检测框最长边达到10像素的局部航迹才能进入有效匹配。当前结果不代表导航误差、云台安装误差、时间同步漂移和真实目标检测误差下的最终性能。AirSim模式只读取已有Blocks实例的检测框与相机信息，不负责启动、重置或控制场景。
"""


def _format_metric(value: Any) -> str:
    return "待离线标注" if value is None else f"{float(value) * 100.0:.1f}%"


def _unregistered_explanation(metrics: Mapping[str, Any]) -> str:
    local_count = int(metrics.get("unregistered_local_track_candidate_count", 0))
    recognized_count = int(
        metrics.get("unregistered_recognized_local_track_candidate_count", 0)
    )
    if not metrics.get("unregistered_candidate_truth_breakdown_available"):
        return (
            f"末帧另有{local_count}条未匹配的相机内局部航迹候选，其中"
            f"{recognized_count}条达到10像素门限。该数值的单位是局部航迹，"
            "不能直接解释为未注册目标数量。"
        )
    distinct_targets = int(metrics.get("unregistered_distinct_truth_target_count", 0))
    redundant = int(
        metrics.get("unregistered_registered_target_redundant_observation_count", 0)
    )
    redundant_targets = int(
        metrics.get("unregistered_registered_target_distinct_count", 0)
    )
    missed_observations = int(
        metrics.get("unregistered_center_missed_target_observation_count", 0)
    )
    missed_targets = int(
        metrics.get("unregistered_center_missed_target_distinct_count", 0)
    )
    unbound_observations = int(
        metrics.get("unregistered_correct_source_unbound_observation_count", 0)
    )
    unbound_targets = int(
        metrics.get("unregistered_correct_source_unbound_distinct_count", 0)
    )
    unknown_labels = int(metrics.get("unregistered_unknown_truth_label_count", 0))
    breakdown = [
        f"{redundant}条来自{redundant_targets}个已完成绑定目标的重复视角",
        f"{missed_observations}条来自中心漏掉的{missed_targets}个目标",
    ]
    if unbound_observations:
        breakdown.append(
            f"{unbound_observations}条来自有正确中心线索但尚未确认的"
            f"{unbound_targets}个目标"
        )
    if unknown_labels:
        breakdown.append(f"{unknown_labels}条缺少离线目标标签")
    return (
        f"末帧另有{local_count}条未匹配的相机内局部航迹候选，其中"
        f"{recognized_count}条达到10像素门限。离线标签表明这些候选对应"
        f"{distinct_targets}个目标：{'；'.join(breakdown)}。"
        f"因此旧字段 `unregistered_candidate_count={local_count}` 表示局部航迹数量，"
        "不表示漏注册了同等数量的目标。"
    )


def math_sqrt(value: float) -> float:
    return float(np.sqrt(max(float(value), 0.0)))
