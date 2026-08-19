"""Aggregate the 20/40/60-target S180 campaign into one evidence report."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence

from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np

from .contracts import AssociationMatch, ROUTE_NAMES, read_snapshot, write_json
from .dataset import load_dataset_manifest, sha256_file
from .offline_scale_replay import _publication_from_mapping


S180_REPORT_SCHEMA = "dual-optical-s180-combined-report-v2"
S180_REPRODUCTION_SCHEMA = "msm-experiment-reproduction-v1"
LOCAL_TRACK_PURITY_THRESHOLD = 0.85
S180_TARGET_COUNTS = (20, 40, 60)
S180_ROUTES = ("epipolar_mht", "gnn", "track_superglue")
S180_LEVELS = ("clean", "light")
SOURCE_FILES = (
    "research_modules/independent_experiments/dual_optical_online_benchmark/contracts.py",
    "research_modules/independent_experiments/dual_optical_online_benchmark/dataset.py",
    "research_modules/independent_experiments/dual_optical_online_benchmark/episode_worker.py",
    "research_modules/independent_experiments/dual_optical_online_benchmark/batch.py",
    "research_modules/independent_experiments/dual_optical_online_benchmark/cli.py",
    "research_modules/independent_experiments/dual_optical_online_benchmark/orchestrator.py",
    "research_modules/independent_experiments/dual_optical_online_benchmark/offline_scale_replay.py",
    "research_modules/independent_experiments/dual_optical_online_benchmark/scoring.py",
    "research_modules/independent_experiments/dual_optical_online_benchmark/tracking.py",
    "research_modules/independent_experiments/dual_optical_online_benchmark/tracker_calibration.py",
    "research_modules/independent_experiments/dual_optical_online_benchmark/s180_reporting.py",
    "research_modules/independent_experiments/dual_optical_40target/core.py",
    "research_modules/independent_experiments/dual_optical_40target/runtime.py",
    "research_modules/independent_experiments/dual_optical_40target/online.py",
    "research_modules/independent_experiments/dual_optical_40target/online_benchmark.py",
    "research_modules/independent_experiments/dual_optical_100target_gnn/online.py",
    "research_modules/independent_experiments/dual_optical_100target_gnn/online_benchmark.py",
    "research_modules/independent_experiments/dual_optical_100target_gnn/training.py",
    "research_modules/independent_experiments/dual_optical_track_superglue/online_benchmark.py",
)
ROUTE_LABELS = {
    "epipolar_mht": "增强几何",
    "gnn": "图神经网络",
    "track_superglue": "航迹级SuperGlue",
}
LEVEL_LABELS = {"clean": "无干扰", "light": "轻干扰"}


def _dominant_truth(counts: Mapping[str, Any]) -> str | None:
    ranked = sorted(
        (
            (int(count), str(identity))
            for identity, count in counts.items()
            if int(count) > 0 and not str(identity).startswith("FA-")
        ),
        reverse=True,
    )
    if not ranked or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
        return None
    return ranked[0][1]


def _dominant_truth_and_purity(
    counts: Mapping[str, Any],
) -> tuple[str | None, int, int, float]:
    total = sum(max(0, int(count)) for count in counts.values())
    identity = _dominant_truth(counts)
    dominant_count = int(counts.get(identity, 0)) if identity is not None else 0
    purity = dominant_count / total if total else 0.0
    return identity, dominant_count, total, purity


def _offline_association_diagnostics(
    camera_track_ids: Mapping[str, Sequence[str]],
    track_truth_counts: Mapping[str, Mapping[str, Any]],
    matches: Sequence[AssociationMatch],
    target_count: int,
) -> dict[str, int]:
    """Score local tracking first, then cross-station matching conditionally."""

    correct_track_truth: dict[str, str] = {}
    correct_truths_by_camera: dict[str, set[str]] = {}
    dominant_observation_count = 0
    labeled_observation_count = 0
    for camera_id, track_ids in camera_track_ids.items():
        correct_truths: set[str] = set()
        for track_id in track_ids:
            identity, dominant_count, total, purity = _dominant_truth_and_purity(
                track_truth_counts.get(track_id, {})
            )
            dominant_observation_count += dominant_count
            labeled_observation_count += total
            if identity is None or purity < LOCAL_TRACK_PURITY_THRESHOLD:
                continue
            correct_track_truth[track_id] = identity
            correct_truths.add(identity)
        correct_truths_by_camera[str(camera_id)] = correct_truths

    camera_ids = tuple(camera_track_ids)
    if len(camera_ids) != 2:
        raise ValueError("S180 offline diagnostics require exactly two cameras")
    shared_correct_truths = (
        correct_truths_by_camera[camera_ids[0]]
        & correct_truths_by_camera[camera_ids[1]]
    )

    eligible_pair_count = 0
    correct_pair_count = 0
    correctly_matched_truths: set[str] = set()
    for match in matches:
        truth_a = correct_track_truth.get(match.track_a_id)
        truth_b = correct_track_truth.get(match.track_b_id)
        if truth_a is None or truth_b is None:
            continue
        eligible_pair_count += 1
        if truth_a != truth_b:
            continue
        correct_pair_count += 1
        correctly_matched_truths.add(truth_a)

    return {
        "single_station_correct_identity_count": sum(
            len(values) for values in correct_truths_by_camera.values()
        ),
        "single_station_identity_opportunity_count": len(camera_ids)
        * int(target_count),
        "single_station_dominant_observation_count": dominant_observation_count,
        "single_station_labeled_observation_count": labeled_observation_count,
        "conditional_dual_correct_pair_count": correct_pair_count,
        "conditional_dual_eligible_pair_count": eligible_pair_count,
        "conditional_dual_correct_identity_count": len(correctly_matched_truths),
        "conditional_dual_opportunity_identity_count": len(shared_correct_truths),
    }


def _snapshot_diagnostics(
    manifest_path: Path,
) -> tuple[
    dict[tuple[int, str, int], dict[str, Any]],
    dict[tuple[int, str, int], dict[str, Any]],
]:
    manifest = load_dataset_manifest(manifest_path, validate_offline_labels=True)
    root = manifest_path.parent
    previous: dict[tuple[int, str, str, str], str] = {}
    diagnostics: dict[tuple[int, str, int], dict[str, Any]] = {}
    offline_inputs: dict[tuple[int, str, int], dict[str, Any]] = {}
    for entry in manifest["entries"]:
        snapshot = read_snapshot(root / entry["snapshot_path"])
        labels = json.loads((root / entry["label_path"]).read_text(encoding="utf-8"))
        counts = labels["track_truth_counts"]
        truths_by_camera: dict[str, dict[str, list[str]]] = {}
        identity_switch_count = 0
        for camera_id in snapshot.camera_ids:
            by_truth: dict[str, list[str]] = defaultdict(list)
            for track in snapshot.tracks[camera_id]:
                identity = _dominant_truth(counts.get(track.track_id, {}))
                if identity is None:
                    continue
                by_truth[identity].append(track.track_id)
                previous_key = (
                    snapshot.seed,
                    snapshot.corruption_level,
                    camera_id,
                    track.track_id,
                )
                prior_identity = previous.get(previous_key)
                if prior_identity is not None and prior_identity != identity:
                    identity_switch_count += 1
                previous[previous_key] = identity
            truths_by_camera[camera_id] = by_truth
        camera_a, camera_b = snapshot.camera_ids
        shared_truths = set(truths_by_camera[camera_a]) & set(
            truths_by_camera[camera_b]
        )
        fragmentation = sum(
            max(0, len(track_ids) - 1)
            for by_truth in truths_by_camera.values()
            for track_ids in by_truth.values()
        )
        key = (snapshot.seed, snapshot.corruption_level, snapshot.revolution_index)
        diagnostics[key] = {
            "candidate_pair_count": len(snapshot.geometry_candidate_pairs),
            "local_track_count_a": len(snapshot.tracks[camera_a]),
            "local_track_count_b": len(snapshot.tracks[camera_b]),
            "shared_local_truth_count": len(shared_truths),
            "fragment_count": fragmentation,
            "identity_dominance_switch_count": identity_switch_count,
        }
        offline_inputs[key] = {
            "camera_track_ids": {
                camera_id: tuple(
                    track.track_id for track in snapshot.tracks[camera_id]
                )
                for camera_id in snapshot.camera_ids
            },
            "track_truth_counts": counts,
            "target_count": snapshot.target_count,
            "input_fingerprint": str(entry["input_fingerprint"]),
        }
    return diagnostics, offline_inputs


def _load_campaign_rows(campaign_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for target_count in S180_TARGET_COUNTS:
        tier = campaign_root / f"targets_{target_count:03d}"
        metrics_path = tier / "results" / "comparison_metrics.json"
        manifest_path = tier / "dataset" / "test_manifest.json"
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        freeze_marker_path = Path(metrics["freeze_marker"])
        freeze_marker = json.loads(freeze_marker_path.read_text(encoding="utf-8"))
        tracker_freeze_path = Path(freeze_marker["tracker_freeze"])
        tracker_freeze = json.loads(
            tracker_freeze_path.read_text(encoding="utf-8")
        )
        tracker_acceptance = tracker_freeze.get("validation_metrics", {}).get(
            "acceptance", {}
        )
        protocol = metrics["protocol"]
        if int(protocol["target_count"]) != target_count:
            raise ValueError("S180 metrics target count does not match its tier")
        if protocol.get("scan_profile") != "s180_triangle_1s_v1":
            raise ValueError("combined report accepts the S180 profile only")
        diagnostics, offline_inputs = _snapshot_diagnostics(manifest_path)
        active_routes = tuple(metrics.get("active_routes", ()))
        if any(route not in S180_ROUTES for route in active_routes):
            raise ValueError("S180 metrics contain an out-of-scope route")
        for raw in metrics["rows"]:
            route = str(raw["route_name"])
            if route not in S180_ROUTES:
                continue
            key = (
                int(raw["seed"]),
                str(raw["corruption_level"]),
                int(raw["revolution_index"]),
            )
            publication_path = (
                tier
                / "results"
                / "publications"
                / str(key[0])
                / key[1]
                / f"revolution_{key[2]:02d}_{route}.json"
            )
            publication = _publication_from_mapping(
                json.loads(publication_path.read_text(encoding="utf-8"))
            )
            if (
                publication.seed != key[0]
                or publication.corruption_level != key[1]
                or publication.revolution_index != key[2]
                or publication.route_name != route
                or publication.input_fingerprint
                != offline_inputs[key]["input_fingerprint"]
            ):
                raise ValueError("S180 publication does not match its snapshot")
            offline_diagnostics = _offline_association_diagnostics(
                camera_track_ids=offline_inputs[key]["camera_track_ids"],
                track_truth_counts=offline_inputs[key]["track_truth_counts"],
                matches=publication.matches,
                target_count=int(offline_inputs[key]["target_count"]),
            )
            row = {
                **dict(raw),
                **diagnostics[key],
                **offline_diagnostics,
                "target_count": target_count,
                "no_confirmed_output": int(raw["match_count"]) == 0,
                "timed_out": str(raw["availability"]) == "timeout",
                "processing_unavailable": str(raw["availability"]).startswith(
                    "unavailable"
                ),
            }
            rows.append(row)
        evidence.append(
            {
                "target_count": target_count,
                "metrics_path": str(metrics_path.resolve()),
                "metrics_sha256": sha256_file(metrics_path),
                "test_manifest_path": str(manifest_path.resolve()),
                "test_manifest_sha256": sha256_file(manifest_path),
                "protocol": protocol,
                "protocol_fingerprint": metrics["protocol_fingerprint"],
                "active_routes": list(active_routes),
                "diagnostic_only": metrics.get("diagnostic_only") is True,
                "formal_use_allowed": metrics.get("formal_use_allowed", True),
                "promotion_allowed": metrics.get("promotion_allowed", True),
                "tracker_acceptance_passed": tracker_acceptance.get("accepted")
                is True,
                "tracker_failure_reasons": list(
                    tracker_acceptance.get("failure_reasons", ())
                ),
                "tracker_freeze_path": str(tracker_freeze_path.resolve()),
                "tracker_freeze_sha256": sha256_file(tracker_freeze_path),
            }
        )
    return rows, evidence


def _window_rows(
    rows: Sequence[Mapping[str, Any]], window: str, final_round: int
) -> list[Mapping[str, Any]]:
    if window == "all_rounds":
        return list(rows)
    if window == "rounds_3_to_final":
        return [row for row in rows if 3 <= int(row["revolution_index"]) <= final_round]
    if window == "final_round":
        return [row for row in rows if int(row["revolution_index"]) == final_round]
    raise ValueError(f"unknown report window: {window}")


def _summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for target_count in S180_TARGET_COUNTS:
        for route in S180_ROUTES:
            for level in S180_LEVELS:
                base = [
                    row
                    for row in rows
                    if int(row["target_count"]) == target_count
                    and row["route_name"] == route
                    and row["corruption_level"] == level
                ]
                if not base:
                    continue
                final_round = max(int(row["revolution_index"]) for row in base)
                for window in ("all_rounds", "rounds_3_to_final", "final_round"):
                    selected = _window_rows(base, window, final_round)
                    match_count = sum(int(row["match_count"]) for row in selected)
                    correct_count = sum(
                        int(row["correct_match_count"]) for row in selected
                    )
                    single_station_correct = sum(
                        int(row["single_station_correct_identity_count"])
                        for row in selected
                    )
                    single_station_opportunities = sum(
                        int(row["single_station_identity_opportunity_count"])
                        for row in selected
                    )
                    single_station_dominant = sum(
                        int(row["single_station_dominant_observation_count"])
                        for row in selected
                    )
                    single_station_labeled = sum(
                        int(row["single_station_labeled_observation_count"])
                        for row in selected
                    )
                    conditional_correct_pairs = sum(
                        int(row["conditional_dual_correct_pair_count"])
                        for row in selected
                    )
                    conditional_eligible_pairs = sum(
                        int(row["conditional_dual_eligible_pair_count"])
                        for row in selected
                    )
                    conditional_correct_identities = sum(
                        int(row["conditional_dual_correct_identity_count"])
                        for row in selected
                    )
                    conditional_opportunity_identities = sum(
                        int(row["conditional_dual_opportunity_identity_count"])
                        for row in selected
                    )
                    summary.append(
                        {
                            "target_count": target_count,
                            "route_name": route,
                            "route_label_cn": ROUTE_LABELS[route],
                            "corruption_level": level,
                            "window": window,
                            "sample_count": len(selected),
                            "correct_match_count": correct_count,
                            "false_association_count": sum(
                                int(row["false_association_count"])
                                for row in selected
                            ),
                            "selected_match_count": match_count,
                            "association_precision": (
                                correct_count / match_count if match_count else 0.0
                            ),
                            "fixed_denominator_coverage": float(
                                np.mean([float(row["recall"]) for row in selected])
                            ),
                            "single_station_association_coverage": (
                                single_station_correct / single_station_opportunities
                                if single_station_opportunities
                                else 0.0
                            ),
                            "single_station_association_precision": (
                                single_station_dominant / single_station_labeled
                                if single_station_labeled
                                else 0.0
                            ),
                            "conditional_dual_station_association_precision": (
                                conditional_correct_pairs / conditional_eligible_pairs
                                if conditional_eligible_pairs
                                else 0.0
                            ),
                            "conditional_dual_station_association_coverage": (
                                conditional_correct_identities
                                / conditional_opportunity_identities
                                if conditional_opportunity_identities
                                else 0.0
                            ),
                            "mean_shared_local_truth_count": float(
                                np.mean(
                                    [
                                        float(row["shared_local_truth_count"])
                                        for row in selected
                                    ]
                                )
                            ),
                            "mean_fragment_count": float(
                                np.mean(
                                    [float(row["fragment_count"]) for row in selected]
                                )
                            ),
                            "identity_dominance_switch_count": int(
                                sum(
                                    int(row["identity_dominance_switch_count"])
                                    for row in selected
                                )
                                / max(len({row["route_name"] for row in selected}), 1)
                            ),
                            "mean_candidate_pair_count": float(
                                np.mean(
                                    [
                                        float(row["candidate_pair_count"])
                                        for row in selected
                                    ]
                                )
                            ),
                            "latency_p95_ms": float(
                                np.percentile(
                                    [float(row["end_to_end_ms"]) for row in selected],
                                    95,
                                )
                            ),
                            "deadline_met_rate": float(
                                np.mean([bool(row["deadline_met"]) for row in selected])
                            ),
                            "timeout_round_count": sum(
                                bool(row["timed_out"]) for row in selected
                            ),
                            "processing_unavailable_round_count": sum(
                                bool(row["processing_unavailable"])
                                for row in selected
                            ),
                            "no_confirmed_output_round_count": sum(
                                bool(row["no_confirmed_output"]) for row in selected
                            ),
                        }
                    )
    return summary


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("cannot write an empty S180 CSV")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _configure_plotting() -> str:
    """Select an installed CJK font instead of silently drawing empty glyphs."""

    for family in (
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "AR PL UMing CN",
        "Droid Sans Fallback",
    ):
        try:
            font_manager.findfont(family, fallback_to_default=False)
        except ValueError:
            continue
        plt.rcParams["font.family"] = family
        plt.rcParams["axes.unicode_minus"] = False
        return family
    raise RuntimeError("S180 report generation requires an installed CJK font")


def _write_figures(
    figures: Path,
    rows: Sequence[Mapping[str, Any]],
    summary: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> list[Path]:
    _configure_plotting()
    figures.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    evidence_labels = {
        int(item["target_count"]): (
            "诊断" if item["diagnostic_only"] else "正式"
        )
        for item in evidence
    }
    colors = {
        "epipolar_mht": "#2f6b4f",
        "gnn": "#3f66a8",
        "track_superglue": "#a45b3d",
    }
    for level in S180_LEVELS:
        figure, axes = plt.subplots(1, 3, figsize=(13.2, 3.8), sharey=True)
        for axis, target_count in zip(axes, S180_TARGET_COUNTS, strict=True):
            for route in S180_ROUTES:
                selected = [
                    row
                    for row in rows
                    if int(row["target_count"]) == target_count
                    and row["route_name"] == route
                    and row["corruption_level"] == level
                ]
                rounds = sorted({int(row["revolution_index"]) for row in selected})
                coverage = [
                    np.mean(
                        [
                            float(row["recall"])
                            for row in selected
                            if int(row["revolution_index"]) == round_index
                        ]
                    )
                    for round_index in rounds
                ]
                axis.plot(
                    rounds,
                    coverage,
                    marker="o",
                    linewidth=1.6,
                    markersize=3.5,
                    color=colors[route],
                    label=ROUTE_LABELS[route],
                )
            axis.set_title(
                f"{target_count}目标（{evidence_labels[target_count]}）"
            )
            axis.set_xlabel("关联轮次")
            axis.set_xticks(range(1, 13))
            axis.grid(alpha=0.25)
        axes[0].set_ylabel("固定分母覆盖度")
        axes[-1].legend(loc="best", fontsize=8)
        figure.suptitle(f"S180 {LEVEL_LABELS[level]}覆盖度")
        figure.tight_layout()
        path = figures / f"coverage_by_round_{level}.png"
        figure.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(figure)
        paths.append(path)

    final = [row for row in summary if row["window"] == "final_round"]
    figure, axes = plt.subplots(1, 2, figsize=(10.8, 4.2))
    marker = {"clean": "o", "light": "s"}
    for row in final:
        axes[0].scatter(
            float(row["fixed_denominator_coverage"]),
            float(row["association_precision"]),
            color=colors[str(row["route_name"])],
            marker=marker[str(row["corruption_level"])],
            s=28 + int(row["target_count"]),
            alpha=0.85,
        )
    axes[0].set_xlabel("末轮固定分母覆盖度")
    axes[0].set_ylabel("末轮关联精度")
    axes[0].grid(alpha=0.25)
    target_positions = np.arange(len(S180_TARGET_COUNTS), dtype=float)
    bar_width = 0.24
    for route_index, route in enumerate(S180_ROUTES):
        grouped = []
        for target_count in S180_TARGET_COUNTS:
            selected = [
                float(row["latency_p95_ms"])
                for row in final
                if int(row["target_count"]) == target_count
                and row["route_name"] == route
            ]
            grouped.append(max(selected) if selected else 0.0)
        axes[1].bar(
            target_positions + (route_index - 1) * bar_width,
            grouped,
            width=bar_width,
            color=colors[route],
            label=ROUTE_LABELS[route],
        )
    axes[1].set_xticks(
        target_positions,
        [
            f"{target_count}目标\n（{evidence_labels[target_count]}）"
            for target_count in S180_TARGET_COUNTS
        ],
    )
    axes[1].set_ylabel("末轮最差条件P95时延/毫秒")
    axes[1].legend(loc="upper left", fontsize=8)
    axes[1].grid(axis="y", alpha=0.25)
    figure.tight_layout()
    path = figures / "final_round_quality_latency.png"
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    paths.append(path)
    return paths


def _pct(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def _write_report(
    path: Path,
    summary: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> None:
    final = [row for row in summary if row["window"] == "final_round"]
    stable = [row for row in summary if row["window"] == "rounds_3_to_final"]
    evidence_labels = {
        int(item["target_count"]): (
            "诊断" if item["diagnostic_only"] else "正式"
        )
        for item in evidence
    }
    lines = [
        "# 双光电S180扫描关联试验",
        "",
        "## 结论",
        "",
        "本次试验只考察1秒单程扫完180度后的双站航迹关联，不与既有360度周扫结果混合。"
        "20、40和60目标均使用8个训练种子、2个验证种子和5个保留测试种子。"
        "下表和图中的数据来自保留测试种子，训练与验证数据不计入最终结果。",
        "",
        "20目标共享航迹器通过验证，可作为本协议下的正式留出结果。40目标共享航迹器因"
        "错误重接率未通过门限，仅保留诊断结果。60目标同时因错误重接率和航迹器运行时延"
        "未通过门限，仅保留诊断结果。40、60目标结果不得用于算法晋级或主线替换。三条"
        "关联路线在这两个规模上的数值用于定位规模增长后的问题。",
        "",
        "| 目标数 | 证据状态 | 共享航迹器验收 | 失败原因 |",
        "| ---: | --- | --- | --- |",
    ]
    reason_labels = {
        "false_reactivation_rate_absolute": "错误重接率超过门限",
        "sweep_runtime_p95_ms": "航迹器运行时延超过门限",
    }
    for item in evidence:
        reasons = "、".join(
            reason_labels.get(reason, reason)
            for reason in item["tracker_failure_reasons"]
        )
        lines.append(
            f"| {int(item['target_count'])} | "
            f"{'诊断' if item['diagnostic_only'] else '正式'} | "
            f"{'通过' if item['tracker_acceptance_passed'] else '未通过'} | "
            f"{reasons or '-'} |"
        )
    lines.append("")
    for target_count in S180_TARGET_COUNTS:
        for level in S180_LEVELS:
            selected = [
                row
                for row in final
                if int(row["target_count"]) == target_count
                and row["corruption_level"] == level
            ]
            if not selected:
                continue
            best_coverage = max(
                selected, key=lambda row: float(row["fixed_denominator_coverage"])
            )
            lines.append(
                f"{target_count}目标（{evidence_labels[target_count]}）"
                f"{LEVEL_LABELS[level]}条件下，末轮覆盖度最高的是"
                f"{best_coverage['route_label_cn']}，覆盖度"
                f"{_pct(float(best_coverage['fixed_denominator_coverage']))}，"
                f"关联精度{_pct(float(best_coverage['association_precision']))}。"
            )
    lines.extend(
        [
            "",
            "这里的覆盖度始终以场景目标总数20、40或60为分母。某一目标只在单站可见、"
            "未形成双站共同航迹或未达到确认条件，均按未覆盖处理。空输出轮次保留在分母中，"
            "超时不使用事后补算结果。",
            "",
            "## 试验条件",
            "",
            "双光电基线为2千米。两台相机在正负90度边界之间往返扫描，单程180度用时1秒，"
            "完整机械往返周期为2秒。每个12秒场景形成12个关联轮次。目标速度为50米/秒，"
            "一半目标沿0度方向飞行，另一半与光轴方向最大相差30度。采样频率为100赫兹，"
            "AirSim时间倍率为0.1。",
            "",
            "云台固定偏差为0.4毫弧度，逐帧随机抖动均方根为0.3毫弧度。无干扰档不增加"
            "漏检和虚警。轻干扰档随机漏检3%，每台相机每秒增加2个瞬时虚警。在线关联只使用"
            "匿名检测和局部航迹，AirSim目标名称只在测试结束后用于离线评分。",
            "",
            "三条路线共用同一批匿名快照和同一候选关系。增强几何路线使用共面约束、运动一致性、"
            "匈牙利一一分配和时间确认；图神经网络路线在相同候选图上学习关系得分，再执行一一"
            "分配；航迹级SuperGlue路线使用航迹自注意力、交叉注意力、空匹配项和最优传输。"
            "本轮没有调整候选门限、候选数量、休眠池、多假设数量、并行预算或超时策略。",
            "",
            "## 试验结果",
            "",
            "### 第3至12轮",
            "",
            "| 目标数 | 证据状态 | 条件 | 方法 | 单站关联覆盖度 | 单站关联精度 | 双站关联精度 | 双站固定覆盖度 | 单站正确时双站精度 | 单站正确时双站覆盖度 | 共同局部目标数 | 航迹碎片数 | P95时延 | 无确认输出轮次 |",
            "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in stable:
        lines.append(
            "| {targets} | {status} | {level} | {route} | {single_coverage} | "
            "{single_precision} | {precision} | {coverage} | {conditional_precision} | "
            "{conditional_coverage} | {shared:.1f} | {fragments:.1f} | "
            "{latency:.1f}毫秒 | {empty} |".format(
                targets=int(row["target_count"]),
                status=evidence_labels[int(row["target_count"])],
                level=LEVEL_LABELS[str(row["corruption_level"])],
                route=row["route_label_cn"],
                single_coverage=_pct(
                    float(row["single_station_association_coverage"])
                ),
                single_precision=_pct(
                    float(row["single_station_association_precision"])
                ),
                precision=_pct(float(row["association_precision"])),
                coverage=_pct(float(row["fixed_denominator_coverage"])),
                conditional_precision=_pct(
                    float(row["conditional_dual_station_association_precision"])
                ),
                conditional_coverage=_pct(
                    float(row["conditional_dual_station_association_coverage"])
                ),
                shared=float(row["mean_shared_local_truth_count"]),
                fragments=float(row["mean_fragment_count"]),
                latency=float(row["latency_p95_ms"]),
                empty=int(row["no_confirmed_output_round_count"]),
            )
        )
    lines.extend(
        [
            "",
            "### 最后一轮",
            "",
            "| 目标数 | 证据状态 | 条件 | 方法 | 正确/错误关联 | 单站关联覆盖度 | 单站关联精度 | 双站关联精度 | 双站固定覆盖度 | 单站正确时双站精度 | 单站正确时双站覆盖度 | 候选关系数 | 超时/不可用 |",
            "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in final:
        lines.append(
            "| {targets} | {status} | {level} | {route} | {correct}/{false} | "
            "{single_coverage} | {single_precision} | {precision} | {coverage} | "
            "{conditional_precision} | {conditional_coverage} | {candidates:.1f} | "
            "{timeout}/{unavailable} |".format(
                targets=int(row["target_count"]),
                status=evidence_labels[int(row["target_count"])],
                level=LEVEL_LABELS[str(row["corruption_level"])],
                route=row["route_label_cn"],
                correct=int(row["correct_match_count"]),
                false=int(row["false_association_count"]),
                single_coverage=_pct(
                    float(row["single_station_association_coverage"])
                ),
                single_precision=_pct(
                    float(row["single_station_association_precision"])
                ),
                precision=_pct(float(row["association_precision"])),
                coverage=_pct(float(row["fixed_denominator_coverage"])),
                conditional_precision=_pct(
                    float(row["conditional_dual_station_association_precision"])
                ),
                conditional_coverage=_pct(
                    float(row["conditional_dual_station_association_coverage"])
                ),
                candidates=float(row["mean_candidate_pair_count"]),
                timeout=int(row["timeout_round_count"]),
                unavailable=int(row["processing_unavailable_round_count"]),
            )
        )
    lines.extend(
        [
            "",
            "![无干扰覆盖度](figures/coverage_by_round_clean.png)",
            "",
            "![轻干扰覆盖度](figures/coverage_by_round_light.png)",
            "",
            "![末轮质量与时延](figures/final_round_quality_latency.png)",
            "",
            "## 指标说明",
            "",
            "单站航迹以主目标唯一且观测纯度不低于85%作为关联正确。单站关联覆盖度为两站各自"
            "正确关联的唯一目标数之和，除以两倍场景目标总数；单站关联精度为所有单站航迹中主"
            "目标观测数之和，除以分配到这些航迹的全部真值标注观测数。后者按观测数做微平均，"
            "虚警和错误重接会降低该值。",
            "",
            "双站关联精度为全部已输出关系中的正确比例。双站固定覆盖度为正确关联的唯一目标数"
            "除以场景目标总数。单站正确时双站精度只统计两端均为正确单站航迹的已输出关系；单站"
            "正确时双站覆盖度以两站均有正确单站航迹的目标为分母，以其中被双站正确关联的唯一"
            "目标为分子。条件分母为零时记为0，不用事后结果补齐。",
            "",
            "共同局部目标数由离线真值统计两站同时形成局部航迹的目标数量，只用于解释覆盖上限。"
            "航迹碎片数统计同一真实目标在单站形成的多余局部航迹。上述四项新增统计和航迹主身份"
            "变化计数均依赖测试结束后打开的真值标签，属于离线诊断量，在线算法没有读取这些信息。",
            "",
            "前两轮处于航迹形成和时间确认阶段，因此同时给出全12轮、第3至12轮和最后一轮口径。"
            "报告不使用累计曾经关联过的目标数替代当前轮覆盖度。",
            "",
            "## 证据",
            "",
        ]
    )
    for item in evidence:
        lines.append(
            f"- {int(item['target_count'])}目标（"
            f"{'诊断' if item['diagnostic_only'] else '正式'}）：保留测试指标 "
            f"`{item['metrics_path']}`，"
            f"协议指纹 `{item['protocol_fingerprint']}`。"
        )
    lines.extend(
        [
            "",
            "本次结果属于AirSim ComputerVision仿真。站址误差、时间同步漂移、大气传播、真实"
            "检测器误差和光机结构动态尚未纳入，不能直接换算为外场装备性能。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _git_output(repo_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.stdout.strip()


def _reproduction_manifest(
    campaign_root: Path,
    repo_root: Path,
    evidence: Sequence[Mapping[str, Any]],
    metrics_path: Path,
    report_path: Path,
    figure_paths: Sequence[Path],
    source_entries: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    protocol_paths = [
        repo_root
        / "research_modules/independent_experiments/dual_optical_online_benchmark/protocols"
        / f"s180_targets_{target_count:03d}.json"
        for target_count in S180_TARGET_COUNTS
    ]
    commands = []
    for target_count, protocol_path in zip(
        S180_TARGET_COUNTS, protocol_paths, strict=True
    ):
        relative = protocol_path.relative_to(repo_root).as_posix()
        commands.extend(
            [
                f"PYTHONPATH=research_modules/independent_experiments python3 -m dual_optical_online_benchmark.cli preflight --protocol-file {relative}",
                f"PYTHONPATH=research_modules/independent_experiments python3 -m dual_optical_online_benchmark.cli generate calibration --protocol-file {relative}",
                f"PYTHONPATH=research_modules/independent_experiments python3 -m dual_optical_online_benchmark.cli freeze --protocol-file {relative} --active-route epipolar_mht --active-route gnn --active-route track_superglue",
                f"PYTHONPATH=research_modules/independent_experiments python3 -m dual_optical_online_benchmark.cli generate test --protocol-file {relative}",
                f"PYTHONPATH=research_modules/independent_experiments python3 -m dual_optical_online_benchmark.cli evaluate --protocol-file {relative}",
            ]
        )
    inputs = []
    for item in evidence:
        inputs.extend(
            [
                {
                    "role": "test_manifest",
                    "path": str(Path(item["test_manifest_path"]).relative_to(campaign_root)),
                    "sha256": item["test_manifest_sha256"],
                },
                {
                    "role": "per_scale_metrics",
                    "path": str(Path(item["metrics_path"]).relative_to(campaign_root)),
                    "sha256": item["metrics_sha256"],
                },
            ]
        )
    for path in protocol_paths:
        inputs.append(
            {
                "role": "protocol",
                "path": str(path.relative_to(repo_root)),
                "sha256": sha256_file(path),
            }
        )
    inputs.extend(dict(item) for item in source_entries)
    dirty = _git_output(repo_root, "status", "--short")
    return {
        "schema_version": S180_REPRODUCTION_SCHEMA,
        "experiment_id": "s180_1s_sector_v1",
        "status": "mixed_formal_and_diagnostic",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question": "1秒单程180度扫描下三种双站航迹关联方法在20/40/60目标规模的表现",
        "source": {
            "git_commit": _git_output(repo_root, "rev-parse", "HEAD"),
            "worktree_dirty": bool(dirty),
            "git_status_short_sha256": hashlib.sha256(dirty.encode()).hexdigest(),
            "entry_point": "dual_optical_online_benchmark.cli and s180_reporting",
            "cwd": str(repo_root),
            "commands": commands,
            "environment": {
                "PYTHONPATH": "research_modules/independent_experiments"
            },
        },
        "runtime": {
            "python_version": sys.version,
            "platform": platform.platform(),
            "simulator": "AirSim Blocks ComputerVision",
            "simulator_version": "AirSim 1.8.1",
            "hardware_summary": "NVIDIA RTX 4050 Laptop GPU; route training may use CUDA",
        },
        "scenario": {
            "protocols": [item["protocol"] for item in evidence],
            "target_counts": list(S180_TARGET_COUNTS),
            "duration_s": 12.0,
            "clock_speed": 0.1,
            "association_round_period_s": 1.0,
            "association_round_count": 12,
            "scale_evidence_status": [
                {
                    "target_count": int(item["target_count"]),
                    "diagnostic_only": bool(item["diagnostic_only"]),
                    "tracker_acceptance_passed": bool(
                        item["tracker_acceptance_passed"]
                    ),
                    "tracker_failure_reasons": list(
                        item["tracker_failure_reasons"]
                    ),
                }
                for item in evidence
            ],
        },
        "inputs": inputs,
        "outputs": {
            "metrics": [str(metrics_path.relative_to(campaign_root))],
            "reports": [str(report_path.relative_to(campaign_root))],
            "figures": [str(path.relative_to(campaign_root)) for path in figure_paths],
        },
        "metrics_contract": {
            "denominators": {
                "dual_station_fixed_coverage": (
                    "correct unique identities / fixed target_count"
                ),
                "dual_station_precision": (
                    "correct selected relations / all selected relations"
                ),
                "single_station_coverage": (
                    "sum of correct unique identities per camera / "
                    "(camera_count * fixed target_count)"
                ),
                "single_station_precision": (
                    "dominant real observations / all labeled local-track observations"
                ),
                "conditional_dual_station_precision": (
                    "correct pairs / selected pairs with two correct local tracks"
                ),
                "conditional_dual_station_coverage": (
                    "correctly matched unique identities / identities with a correct "
                    "local track in both cameras"
                ),
            },
            "local_track_correctness": (
                "unique dominant real identity and observation purity >= 0.85"
            ),
            "windows": ["all_rounds", "rounds_3_to_final", "final_round"],
            "availability_policy": "timeouts and no-confirmed-output rounds remain in the denominator",
        },
        "reproduction": {
            "offline_replay_command": (
                "PYTHONPATH=research_modules/independent_experiments python3 -m "
                "dual_optical_online_benchmark.s180_reporting --campaign-root "
                "research_modules/independent_experiments/dual_optical_online_benchmark/outputs/s180_1s_sector_v1"
            ),
            "full_rerun_commands": commands,
            "expected_metrics_sha256": sha256_file(metrics_path),
            "comparison_tolerance": "offline aggregation exact; AirSim rerun statistically compared per seed",
            "known_nondeterminism": [
                "AirSim rendering and RPC timing",
                "CUDA training kernels where selected",
                "dirty worktree recorded by hash rather than a clean source commit",
            ],
        },
    }


def _snapshot_sources(campaign_root: Path, repo_root: Path) -> list[dict[str, str]]:
    snapshot_root = campaign_root / "source_snapshot"
    entries: list[dict[str, str]] = []
    for relative_text in SOURCE_FILES:
        relative = Path(relative_text)
        source = repo_root / relative
        if not source.is_file():
            raise FileNotFoundError(f"S180 source file is missing: {relative}")
        destination = snapshot_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        entries.append(
            {
                "role": "source_snapshot",
                "path": str(destination.relative_to(campaign_root)),
                "sha256": sha256_file(destination),
            }
        )
    write_json(snapshot_root / "source_hashes.json", {"files": entries})
    return entries


def run_s180_report(campaign_root: str | Path, repo_root: str | Path) -> Path:
    campaign_root = Path(campaign_root).resolve()
    repo_root = Path(repo_root).resolve()
    rows, evidence = _load_campaign_rows(campaign_root)
    summary = _summarize(rows)
    round_csv = campaign_root / "s180_round_metrics.csv"
    summary_csv = campaign_root / "s180_summary.csv"
    _write_csv(round_csv, rows)
    _write_csv(summary_csv, summary)
    figure_paths = _write_figures(
        campaign_root / "figures", rows, summary, evidence
    )
    metrics_path = campaign_root / "s180_combined_metrics.json"
    payload = {
        "schema_version": S180_REPORT_SCHEMA,
        "experiment_id": "s180_1s_sector_v1",
        "truth_used_online": False,
        "target_counts": list(S180_TARGET_COUNTS),
        "routes": list(S180_ROUTES),
        "corruption_levels": list(S180_LEVELS),
        "coverage_denominator": "fixed_target_count",
        "local_track_purity_threshold": LOCAL_TRACK_PURITY_THRESHOLD,
        "round_count": 12,
        "evidence_status": "mixed_formal_and_diagnostic",
        "evidence": evidence,
        "rows": rows,
        "summary": summary,
    }
    write_json(metrics_path, payload)
    report_path = campaign_root / "CLEAN_LIGHT_OFFLINE_COMPARISON_REPORT_CN.md"
    _write_report(report_path, summary, evidence)
    source_entries = _snapshot_sources(campaign_root, repo_root)
    manifest = _reproduction_manifest(
        campaign_root,
        repo_root,
        evidence,
        metrics_path,
        report_path,
        figure_paths,
        source_entries,
    )
    write_json(campaign_root / "reproduction_manifest.json", manifest)
    return report_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
    )
    args = parser.parse_args(argv)
    print(run_s180_report(args.campaign_root, args.repo_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
