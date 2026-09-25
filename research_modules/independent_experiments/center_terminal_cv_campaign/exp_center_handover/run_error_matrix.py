#!/usr/bin/env python3
"""Run the post-search center-to-terminal sensor-error association matrix."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence
import warnings

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


PACKAGE_PARENT = Path(__file__).resolve().parents[2]
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from center_terminal_cv_campaign.common.io import write_json, write_jsonl  # noqa: E402
from center_terminal_cv_campaign.exp_center_handover.association import (  # noqa: E402
    AssociationConfig,
    CenterHandoverAssociator,
)
from center_terminal_cv_campaign.exp_center_handover.error_campaign import (  # noqa: E402
    AttitudeMode,
    DetectionMode,
    HandoverMode,
    NavigationMode,
    SearchTerminalErrorConfig,
    SearchTerminalFixture,
    build_search_terminal_fixture,
)
from center_terminal_cv_campaign.exp_center_handover.gnn import (  # noqa: E402
    SparseGNNScorer,
    load_model,
)
from center_terminal_cv_campaign.exp_center_handover.reporting import (  # noqa: E402
    score_association,
    write_experiment_outputs,
)


MODULE_DIR = Path(__file__).resolve().parent
CAMPAIGN_ROOT = MODULE_DIR.parent
REPOSITORY_ROOT = MODULE_DIR.parents[3]
DEFAULT_OUTPUT_ROOT = CAMPAIGN_ROOT / "outputs" / "center_handover_sensor_error_20260820"
DEFAULT_MODEL_PATH = (
    CAMPAIGN_ROOT
    / "outputs"
    / "gnn_offline_benchmark_20260816"
    / "models"
    / "center_handover"
    / "center_handover_sparse_gnn.pt"
)
DEFAULT_SEEDS = tuple(range(20260820, 20260830))
TARGET_COUNTS = (20, 40, 60)
HANDOVER_MODES: tuple[HandoverMode, ...] = ("anonymous", "coarse_hint")
ATTITUDE_MODES: tuple[AttitudeMode, ...] = ("normal", "degraded")
NAVIGATION_MODES: tuple[NavigationMode, ...] = ("satellite", "visual_navigation")
DETECTION_MODES: tuple[DetectionMode, ...] = ("ideal", "light")
BACKENDS = ("geometry", "gnn")


def association_config() -> AssociationConfig:
    return AssociationConfig(
        projection_noise_px=0.25,
        local_measurement_sigma_px=0.25,
        projection_uncertainty_method="linearized",
    )


def run_matrix(
    *,
    output_dir: Path,
    model_path: Path = DEFAULT_MODEL_PATH,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    target_counts: Sequence[int] = TARGET_COUNTS,
    write_representatives: bool = True,
) -> Path:
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "run.log"
    protocol_path = write_json(
        output_dir / "protocol.json",
        _protocol_payload(seeds=seeds, target_counts=target_counts),
    )
    source_snapshot = _write_source_snapshot(output_dir / "source_snapshot")
    frozen_model_path = _copy_frozen_model(output_dir / "inputs", Path(model_path))
    write_json(output_dir / "environment.json", _environment_payload())
    _append_log(log_path, f"started_utc={datetime.now(timezone.utc).isoformat()}")
    model, model_metadata = load_model(Path(model_path))
    scorer = SparseGNNScorer(model)
    rows: list[dict[str, Any]] = []
    combinations = tuple(
        (target_count, handover_mode, attitude_mode, navigation_mode, detection_mode, seed)
        for target_count in target_counts
        for handover_mode in HANDOVER_MODES
        for attitude_mode in ATTITUDE_MODES
        for navigation_mode in NAVIGATION_MODES
        for detection_mode in DETECTION_MODES
        for seed in seeds
    )
    started = time.perf_counter()
    for combination_index, combination in enumerate(combinations, start=1):
        (
            target_count,
            handover_mode,
            attitude_mode,
            navigation_mode,
            detection_mode,
            seed,
        ) = combination
        config = SearchTerminalErrorConfig(
            target_count=int(target_count),
            seed=int(seed),
            navigation_mode=navigation_mode,
            attitude_mode=attitude_mode,
            detection_mode=detection_mode,
            handover_mode=handover_mode,
        )
        bundle = build_search_terminal_fixture(config)
        fixture = bundle.handover_fixture
        shared_projection_cache: dict[tuple[object, ...], Any] = {}
        for backend in BACKENDS:
            backend_started = time.perf_counter()
            associator = CenterHandoverAssociator(
                fixture.camera_models,
                config=association_config(),
                candidate_scorer=scorer if backend == "gnn" else None,
                use_coarse_hints=handover_mode == "coarse_hint",
                projection_cache=shared_projection_cache,
            )
            results = tuple(
                associator.process_frame(fixture.source_cues, frame)
                for frame in fixture.frames
            )
            elapsed_s = time.perf_counter() - backend_started
            metrics = score_association(
                fixture,
                results,
                mode="offline",
                backend=backend,
            )
            rows.append(
                _row_from_result(
                    bundle,
                    backend=backend,
                    metrics=metrics,
                    results=results,
                    elapsed_s=elapsed_s,
                    cache_was_warm=backend == "gnn",
                )
            )
        if combination_index == 1 or combination_index % 10 == 0:
            elapsed = time.perf_counter() - started
            rate = combination_index / max(elapsed, 1.0e-9)
            remaining = (len(combinations) - combination_index) / max(rate, 1.0e-9)
            print(
                f"completed={combination_index}/{len(combinations)} "
                f"elapsed_s={elapsed:.1f} eta_s={remaining:.1f}",
                flush=True,
            )
            _append_log(
                log_path,
                f"completed={combination_index}/{len(combinations)} "
                f"elapsed_s={elapsed:.3f} eta_s={remaining:.3f}",
            )

    aggregates = aggregate_rows(rows)
    _write_csv(output_dir / "per_run_metrics.csv", rows)
    _write_csv(output_dir / "aggregate_metrics.csv", aggregates)
    write_json(output_dir / "aggregate_metrics.json", aggregates)
    write_json(output_dir / "metrics_contract.json", _metrics_contract())
    _write_figures(output_dir / "figures", aggregates, rows)
    if write_representatives:
        _write_representative_evidence(
            output_dir / "representative_runs",
            model_path=Path(model_path),
            scorer=scorer,
            model_metadata=model_metadata,
        )
    report_path = output_dir / "CENTER_TERMINAL_SENSOR_ERROR_REPORT_CN.md"
    report_path.write_text(
        build_report(
            aggregates,
            rows,
            model_metadata=model_metadata,
            target_counts=target_counts,
            seed_count=len(seeds),
            write_representatives=write_representatives,
        ),
        encoding="utf-8",
    )
    manifest = _build_manifest(
        output_dir=output_dir,
        model_path=Path(model_path),
        seeds=seeds,
        target_counts=target_counts,
        row_count=len(rows),
        aggregate_count=len(aggregates),
        elapsed_s=time.perf_counter() - started,
    )
    write_json(output_dir / "manifest.json", manifest)
    (output_dir / "REPRODUCE.md").write_text(
        _reproduce_text(output_dir, model_path, seeds, target_counts),
        encoding="utf-8",
    )
    write_json(
        output_dir / "reproduction_manifest.json",
        _reproduction_manifest(
            output_dir=output_dir,
            protocol_path=protocol_path,
            frozen_model_path=frozen_model_path,
            source_snapshot=source_snapshot,
            seeds=seeds,
            target_counts=target_counts,
        ),
    )
    _append_log(log_path, f"completed_utc={datetime.now(timezone.utc).isoformat()}")
    print(f"report={report_path.resolve()}", flush=True)
    return report_path


def _row_from_result(
    bundle: SearchTerminalFixture,
    *,
    backend: str,
    metrics: Mapping[str, Any],
    results: Sequence[Any],
    elapsed_s: float,
    cache_was_warm: bool,
) -> dict[str, Any]:
    config = bundle.config
    final = results[-1]
    all_candidates = [candidate for result in results for candidate in result.candidates]
    true_local_ids = {
        label.local_track_id for label in bundle.handover_fixture.local_truth
    }
    observed_true_ids = {
        track.local_track_id
        for frame in bundle.handover_fixture.frames
        for track in frame
        if track.local_track_id in true_local_ids
    }
    false_alarm_count = sum(
        track.metadata.get("detection_source") == "injected_false_alarm"
        for frame in bundle.handover_fixture.frames
        for track in frame
    )
    navigation_norms = [
        float(np.linalg.norm(value.navigation_error_ned_m))
        for value in bundle.camera_error_truth
    ]
    body_yaw_errors = [
        abs(float(value.body_yaw_pitch_roll_error_deg[0]))
        for value in bundle.camera_error_truth
    ]
    return {
        "run_id": (
            f"n{config.target_count}_{config.handover_mode}_{config.attitude_mode}_"
            f"{config.navigation_mode}_{config.detection_mode}_seed{config.seed}_{backend}"
        ),
        "target_count": config.target_count,
        "resource_count": config.target_count,
        "seed": config.seed,
        "handover_mode": config.handover_mode,
        "attitude_mode": config.attitude_mode,
        "navigation_mode": config.navigation_mode,
        "detection_mode": config.detection_mode,
        "backend": backend,
        "gnn_scale_status": (
            "trained_scale" if backend == "gnn" and config.target_count in {20, 40}
            else "unseen_scale" if backend == "gnn"
            else "not_applicable"
        ),
        "binding_precision": metrics.get("binding_precision"),
        "binding_recall": metrics.get("binding_recall"),
        "true_binding_count": metrics.get("true_binding_count"),
        "false_binding_count": metrics.get("false_binding_count"),
        "confirmed_pair_count": metrics.get("confirmed_pair_count"),
        "final_frame_local_track_count": metrics.get("final_frame_local_track_count"),
        "final_frame_recognized_local_track_count": metrics.get(
            "final_frame_recognized_local_track_count"
        ),
        "unregistered_local_track_candidate_count": metrics.get(
            "unregistered_local_track_candidate_count"
        ),
        "realized_distinct_true_track_count": len(observed_true_ids),
        "realized_true_detection_miss_count": (
            config.target_count * len(config.frame_timestamps_s)
            - sum(
                track.local_track_id in true_local_ids
                for frame in bundle.handover_fixture.frames
                for track in frame
            )
        ),
        "realized_false_alarm_count": int(false_alarm_count),
        "eligible_candidate_count_all_frames": sum(
            candidate.eligible for candidate in all_candidates
        ),
        "projected_mean_outside_but_support_retained_count": sum(
            not candidate.projection_mean_in_frame
            and candidate.projection_support_intersects_frame
            for candidate in all_candidates
        ),
        "final_hint_count": final.coarse_hint_count,
        "final_validated_hint_count": final.validated_coarse_hint_count,
        "final_hint_fallback_count": final.fallback_coarse_hint_count,
        "final_hint_validation_rate": (
            final.validated_coarse_hint_count / max(final.coarse_hint_count, 1)
            if config.handover_mode == "coarse_hint"
            else None
        ),
        "realized_navigation_error_mean_m": float(np.mean(navigation_norms)),
        "realized_navigation_error_max_m": float(np.max(navigation_norms)),
        "realized_body_yaw_error_mean_abs_deg": float(np.mean(body_yaw_errors)),
        "realized_body_yaw_error_max_abs_deg": float(np.max(body_yaw_errors)),
        "runtime_s": elapsed_s,
        "runtime_uses_warm_projection_cache": cache_was_warm,
        "metric_condition": "search_already_found_target",
    }


def aggregate_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "target_count",
        "handover_mode",
        "attitude_mode",
        "navigation_mode",
        "detection_mode",
        "backend",
    )
    grouped: dict[tuple[object, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(tuple(row[key] for key in keys), []).append(row)
    aggregates: list[dict[str, Any]] = []
    for key, values in sorted(grouped.items(), key=lambda item: tuple(str(v) for v in item[0])):
        precision = np.asarray([float(value["binding_precision"]) for value in values])
        recall = np.asarray([float(value["binding_recall"]) for value in values])
        runtime = np.asarray([float(value["runtime_s"]) for value in values])
        hint_rates = [
            float(value["final_hint_validation_rate"])
            for value in values
            if value["final_hint_validation_rate"] is not None
        ]
        aggregates.append(
            {
                **dict(zip(keys, key, strict=True)),
                "seed_count": len(values),
                "binding_precision_mean": float(np.mean(precision)),
                "binding_precision_std": float(np.std(precision)),
                "binding_precision_min": float(np.min(precision)),
                "binding_recall_mean": float(np.mean(recall)),
                "binding_recall_std": float(np.std(recall)),
                "binding_recall_min": float(np.min(recall)),
                "seeds_precision_and_recall_gte_0_80": int(
                    np.sum((precision >= 0.8) & (recall >= 0.8))
                ),
                "true_binding_count_mean": _mean(values, "true_binding_count"),
                "false_binding_count_mean": _mean(values, "false_binding_count"),
                "unregistered_local_track_candidate_count_mean": _mean(
                    values,
                    "unregistered_local_track_candidate_count",
                ),
                "realized_true_detection_miss_count_mean": _mean(
                    values,
                    "realized_true_detection_miss_count",
                ),
                "realized_false_alarm_count_mean": _mean(
                    values,
                    "realized_false_alarm_count",
                ),
                "eligible_candidate_count_all_frames_mean": _mean(
                    values,
                    "eligible_candidate_count_all_frames",
                ),
                "projected_mean_outside_but_support_retained_count_mean": _mean(
                    values,
                    "projected_mean_outside_but_support_retained_count",
                ),
                "final_hint_validation_rate_mean": (
                    float(np.mean(hint_rates)) if hint_rates else None
                ),
                "runtime_s_mean": float(np.mean(runtime)),
                "runtime_s_p95": float(np.quantile(runtime, 0.95)),
                "gnn_scale_status": values[0]["gnn_scale_status"],
            }
        )
    return aggregates


def _write_representative_evidence(
    root: Path,
    *,
    model_path: Path,
    scorer: SparseGNNScorer,
    model_metadata: Mapping[str, Any],
) -> None:
    representatives = (
        (20, "anonymous", "normal", "satellite", "ideal", "geometry"),
        (40, "coarse_hint", "normal", "satellite", "light", "gnn"),
        (60, "anonymous", "degraded", "visual_navigation", "light", "geometry"),
        (60, "coarse_hint", "degraded", "visual_navigation", "light", "gnn"),
    )
    for target_count, handover, attitude, navigation, detection, backend in representatives:
        config = SearchTerminalErrorConfig(
            target_count=target_count,
            seed=DEFAULT_SEEDS[0],
            navigation_mode=navigation,
            attitude_mode=attitude,
            detection_mode=detection,
            handover_mode=handover,
        )
        bundle = build_search_terminal_fixture(config)
        fixture = bundle.handover_fixture
        associator = CenterHandoverAssociator(
            fixture.camera_models,
            config=association_config(),
            candidate_scorer=scorer if backend == "gnn" else None,
            use_coarse_hints=handover == "coarse_hint",
        )
        results = tuple(
            associator.process_frame(fixture.source_cues, frame)
            for frame in fixture.frames
        )
        run_id = (
            f"n{target_count}_{handover}_{attitude}_{navigation}_{detection}_{backend}"
        )
        run_dir = root / run_id
        write_experiment_outputs(
            output_dir=run_dir,
            fixture=fixture,
            frames=fixture.frames,
            results=results,
            mode="offline",
            backend=backend,
            model_metadata=model_metadata if backend == "gnn" else None,
        )
        write_json(run_dir / "error_config.json", config.to_public_dict())
        write_jsonl(run_dir / "truth" / "camera_error_truth.jsonl", bundle.camera_error_truth)


def _write_figures(
    figures_dir: Path,
    aggregates: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    _configure_plotting()
    _plot_flow(figures_dir / "01_association_flow.png")
    _plot_scale_results(figures_dir / "02_scale_results.png", aggregates)
    _plot_error_heatmaps(figures_dir / "03_error_heatmaps.png", aggregates)
    _plot_realized_errors(figures_dir / "04_realized_error_samples.png", rows)


def _plot_flow(path: Path) -> None:
    fig, axis = plt.subplots(figsize=(15.5, 5.2))
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")
    labels = (
        "协同搜索完成\n无人机已看到目标",
        "中心输出全部目标\n三维粗航迹",
        "机载像素与拍摄时刻\n位置、姿态、云台角",
        "中心航迹投到\n各无人机画面",
        "误差范围筛选\n位置与运动候选",
        "几何或图网络\n修正候选代价",
        "匈牙利一一匹配\n连续多帧确认",
    )
    colors = ("#d9e8ef", "#e8e4d4", "#e5ecdf", "#dce6f0", "#eee1d8", "#e6e1ed", "#dfeadf")
    centers = np.linspace(0.075, 0.925, len(labels))
    for center, label, color in zip(centers, labels, colors, strict=True):
        axis.add_patch(
            plt.Rectangle(
                (center - 0.061, 0.34),
                0.122,
                0.32,
                facecolor=color,
                edgecolor="#46545d",
                linewidth=1.1,
            )
        )
        axis.text(center, 0.50, label, ha="center", va="center", fontsize=10.2)
    for left, right in zip(centers[:-1], centers[1:], strict=True):
        axis.annotate(
            "",
            xy=(right - 0.064, 0.50),
            xytext=(left + 0.064, 0.50),
            arrowprops={"arrowstyle": "->", "color": "#56636b", "lw": 1.4},
        )
    axis.text(
        0.50,
        0.18,
        "误差注入：定位5米或50米（95%包络）；姿态、航向和云台角误差；轻干扰含3%漏检、每台每秒2个虚警",
        ha="center",
        va="center",
        fontsize=11.0,
        color="#7b2d26",
    )
    axis.set_title("搜索完成后的中心航迹与机载局部航迹配准流程", fontsize=16, pad=10)
    fig.savefig(path, dpi=210, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def _plot_scale_results(path: Path, aggregates: Sequence[Mapping[str, Any]]) -> None:
    selected = [
        row
        for row in aggregates
        if row["attitude_mode"] == "normal"
        and row["navigation_mode"] == "satellite"
        and row["detection_mode"] == "light"
    ]
    fig, axes = plt.subplots(1, 2, figsize=(14.2, 5.7), sharey=True)
    styles = {
        ("geometry", "anonymous"): ("#2f668c", "o", "几何法，无粗线索编号"),
        ("geometry", "coarse_hint"): ("#609966", "s", "几何法，带粗线索编号"),
        ("gnn", "anonymous"): ("#b65b4b", "^", "图网络，无粗线索编号"),
        ("gnn", "coarse_hint"): ("#8b6fa8", "D", "图网络，带粗线索编号"),
    }
    for (backend, handover), (color, marker, label) in styles.items():
        values = sorted(
            [
                row
                for row in selected
                if row["backend"] == backend and row["handover_mode"] == handover
            ],
            key=lambda row: int(row["target_count"]),
        )
        if not values:
            continue
        x = [int(row["target_count"]) for row in values]
        axes[0].plot(
            x,
            [float(row["binding_precision_mean"]) for row in values],
            color=color,
            marker=marker,
            linewidth=1.8,
            label=label,
        )
        axes[1].plot(
            x,
            [float(row["binding_recall_mean"]) for row in values],
            color=color,
            marker=marker,
            linewidth=1.8,
            label=label,
        )
    for axis, title in zip(axes, ("关联准确度", "关联覆盖度"), strict=True):
        axis.set_title(title)
        axis.set_xlabel("目标与拦截无人机数量")
        axis.set_xticks(TARGET_COUNTS)
        axis.set_ylim(0.0, 1.02)
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("比例")
    axes[1].legend(loc="lower left", fontsize=8.5)
    fig.suptitle("有卫星、正常姿态、轻干扰条件下的规模变化", fontsize=15)
    fig.tight_layout()
    fig.savefig(path, dpi=210, bbox_inches="tight")
    plt.close(fig)


def _plot_error_heatmaps(path: Path, aggregates: Sequence[Mapping[str, Any]]) -> None:
    labels = []
    conditions = []
    for attitude in ATTITUDE_MODES:
        for navigation in NAVIGATION_MODES:
            for detection in DETECTION_MODES:
                conditions.append((attitude, navigation, detection))
                labels.append(
                    f"{'正常' if attitude == 'normal' else '强降级'} / "
                    f"{'卫星' if navigation == 'satellite' else '视觉导航'} / "
                    f"{'理想' if detection == 'ideal' else '轻干扰'}"
                )
    matrix_precision = np.full((len(conditions), 2), np.nan)
    matrix_recall = np.full((len(conditions), 2), np.nan)
    for row_index, condition in enumerate(conditions):
        for column, backend in enumerate(BACKENDS):
            values = [
                row
                for row in aggregates
                if (row["attitude_mode"], row["navigation_mode"], row["detection_mode"])
                == condition
                and row["backend"] == backend
            ]
            matrix_precision[row_index, column] = np.mean(
                [float(row["binding_precision_mean"]) for row in values]
            )
            matrix_recall[row_index, column] = np.mean(
                [float(row["binding_recall_mean"]) for row in values]
            )
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 8.0))
    for axis, matrix, title in zip(
        axes,
        (matrix_precision, matrix_recall),
        ("各误差条件平均关联准确度", "各误差条件平均关联覆盖度"),
        strict=True,
    ):
        image = axis.imshow(matrix, vmin=0.0, vmax=1.0, cmap="RdYlGn", aspect="auto")
        axis.set_xticks((0, 1), ("几何法", "图网络"))
        axis.set_yticks(range(len(labels)), labels)
        axis.set_title(title)
        for row_index in range(matrix.shape[0]):
            for column in range(matrix.shape[1]):
                axis.text(
                    column,
                    row_index,
                    f"{matrix[row_index, column]:.2f}",
                    ha="center",
                    va="center",
                    fontsize=9,
                )
        fig.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=210, bbox_inches="tight")
    plt.close(fig)


def _plot_realized_errors(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    unique = {
        (
            int(row["target_count"]),
            int(row["seed"]),
            str(row["attitude_mode"]),
            str(row["navigation_mode"]),
        ): row
        for row in rows
        if row["backend"] == "geometry"
        and row["handover_mode"] == "anonymous"
        and row["detection_mode"] == "ideal"
    }
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.4))
    colors = {
        "satellite": "#356f9a",
        "visual_navigation": "#b75b4a",
        "normal": "#4e8a5a",
        "degraded": "#9168a6",
    }
    for navigation in NAVIGATION_MODES:
        values = [
            float(row["realized_navigation_error_mean_m"])
            for row in unique.values()
            if row["navigation_mode"] == navigation
        ]
        axes[0].hist(values, bins=14, alpha=0.62, color=colors[navigation], label=navigation)
    for attitude in ATTITUDE_MODES:
        values = [
            float(row["realized_body_yaw_error_mean_abs_deg"])
            for row in unique.values()
            if row["attitude_mode"] == attitude
        ]
        axes[1].hist(values, bins=14, alpha=0.62, color=colors[attitude], label=attitude)
    axes[0].set_title("各批次实际定位误差均值")
    axes[0].set_xlabel("米")
    axes[1].set_title("各批次实际航向误差绝对值均值")
    axes[1].set_xlabel("度")
    for axis in axes:
        axis.set_ylabel("批次数")
        axis.grid(alpha=0.2)
        axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=210, bbox_inches="tight")
    plt.close(fig)


def build_report(
    aggregates: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    *,
    model_metadata: Mapping[str, Any],
    target_counts: Sequence[int] = TARGET_COUNTS,
    seed_count: int = len(DEFAULT_SEEDS),
    write_representatives: bool = True,
) -> str:
    normal_rows = [
        row
        for row in aggregates
        if row["attitude_mode"] == "normal"
        and row["navigation_mode"] == "satellite"
        and row["detection_mode"] == "light"
    ]
    degraded_rows = [
        row
        for row in aggregates
        if row["attitude_mode"] == "degraded"
        and row["navigation_mode"] == "visual_navigation"
        and row["detection_mode"] == "light"
    ]
    normal_table = _report_table(normal_rows, seed_count=seed_count)
    degraded_table = _report_table(degraded_rows, seed_count=seed_count)
    geometry_precision = _mean(aggregates, "binding_precision_mean", backend="geometry")
    geometry_recall = _mean(aggregates, "binding_recall_mean", backend="geometry")
    gnn_precision = _mean(aggregates, "binding_precision_mean", backend="gnn")
    gnn_recall = _mean(aggregates, "binding_recall_mean", backend="gnn")
    model_scales = model_metadata.get("training_config", {}).get("target_counts", ())
    target_count_text = "、".join(str(value) for value in target_counts)
    row_count = len(rows)
    aggregate_count = len(aggregates)
    representative_line = (
        "- `representative_runs/`：四组完整候选、决策、真值评分和结果图。"
        if write_representatives
        else "- 本次运行使用 `--no-representatives`，未生成完整代表组。"
    )
    return f"""# 搜索完成后的中心航迹与拦截无人机目标配准误差试验报告

## 一、试验问题

本试验只检查协同搜索完成以后的目标配准。中心节点已经发现并正确识别全部目标，每架拦截无人机也已经在约700米处稳定看到一个目标，目标与拦截无人机按一比一配置。报告中的覆盖度是“已搜索到目标以后，能够与中心航迹正确绑定的比例”，不把前一阶段的搜索成功率重复计入。

中心给出目标三维粗航迹，拦截无人机给出图像中的局部航迹以及拍摄时刻的位置、机体姿态和云台角。算法把每条中心航迹投到各无人机画面，在误差范围内保留候选，再用几何代价或冻结图网络修正候选代价，最后通过一一匹配和连续多帧确认建立绑定关系。图网络只参与候选评分，不越过几何与时效检查，也不改写中心航迹编号。

![算法流程](figures/01_association_flow.png)

## 二、试验条件

目标规模为{target_count_text}，每种组合使用{seed_count}个独立随机种子。相机分辨率1920×1080，水平视场19度；目标长度3米、速度50米/秒；每批读取5帧，间隔0.1秒。定位、姿态和云台误差均按95%包络换算为随机误差，且同一架无人机在5帧内保持主要偏差不变，用来表示安装、标定和导航漂移具有时间相关性。

- 有卫星定位：三维径向误差95%不超过5米；无卫星视觉导航：飞行200秒后95%不超过50米。
- 正常姿态档：横滚和俯仰1度、航向3度、云台0.1度；强降级档：横滚和俯仰5度、航向10度、云台0.5度。
- 两档都叠加200秒累计航向漂移，95%包络为1度。
- 理想检测不加漏检、虚警和像素扰动；轻干扰设置3%漏检、每台每秒2个虚警、检测中心0.25像素标准差扰动。
- 无粗线索编号时执行全局一一配准；带编号时先做几何核验，编号失效、冲突或超门限后自动回到全局配准。

冻结图网络训练规模为{list(model_scales)}，因此60目标结果属于未见规模测试，不能写成已经完成独立训练验证。误差传播采用一阶协方差计算；中心航迹保留1米位置标准差，未注入中心漏检和身份错误。

## 三、结果

### 3.1 有卫星、正常姿态、轻干扰

{normal_table}

![正常条件规模结果](figures/02_scale_results.png)

### 3.2 无卫星、强降级、轻干扰

{degraded_table}

### 3.3 全部误差组合

全部组合平均看，几何法关联准确度为{geometry_precision:.1%}、覆盖度为{geometry_recall:.1%}；冻结图网络关联准确度为{gnn_precision:.1%}、覆盖度为{gnn_recall:.1%}。这些数值来自完整矩阵，没有删除低结果批次。各条件的均值见下图，逐种子结果共{row_count}行，保存在 `per_run_metrics.csv`；分类汇总共{aggregate_count}行，保存在 `aggregate_metrics.csv`。

![误差条件对比](figures/03_error_heatmaps.png)

![实际误差样本](figures/04_realized_error_samples.png)

## 四、判断

本试验验证的是搜索完成后的配准环节，不代表整个发现、搜索、拦截链路的总成功率。中心目标身份完全正确是本轮前提，拦截无人机虽然已经看到目标，仍需依靠拍摄时刻的定位、姿态和云台信息完成空间转换。

有卫星和正常姿态条件可作为近期工程基线。无卫星50米漂移以及10度航向误差属于强降级状态，主要作用是检查失败边界，不宜当作正常消费级传感器能力。若该档覆盖度明显下降，应优先做在线标定、利用目标视线反校航向，并扩大搜索与确认时间，不能只靠放宽匹配门限。

冻结图网络没有针对本轮导航和姿态误差重新训练。若它低于几何法，结论应解释为训练分布不覆盖当前误差，而不是图网络原理不可用；若要进入后续试验，应先用独立训练集加入同档误差，再使用未参与训练的种子复核。60目标还需单独补训练规模验证。

## 五、证据文件

- `manifest.json`：源版本、模型摘要、矩阵规模和运行环境。
- `per_run_metrics.csv`：逐种子结果。
- `aggregate_metrics.csv`：按规模、误差、交接信息和算法汇总的结果。
{representative_line}
- `REPRODUCE.md`：复现实验命令。
"""


def _report_table(
    values: Sequence[Mapping[str, Any]],
    *,
    seed_count: int,
) -> str:
    ordered = sorted(
        values,
        key=lambda row: (
            int(row["target_count"]),
            str(row["handover_mode"]),
            str(row["backend"]),
        ),
    )
    lines = [
        f"| 规模 | 交接信息 | 方法 | 准确度 | 覆盖度 | 达到80%的批数（共{seed_count}批） |",
        "| ---: | --- | --- | ---: | ---: | ---: |",
    ]
    for row in ordered:
        lines.append(
            "| {target_count} | {handover} | {backend} | {precision:.1%} | "
            "{recall:.1%} | {qualified}/{seed_count} |".format(
                target_count=row["target_count"],
                handover="带粗线索编号" if row["handover_mode"] == "coarse_hint" else "无编号",
                backend="图网络" if row["backend"] == "gnn" else "几何法",
                precision=float(row["binding_precision_mean"]),
                recall=float(row["binding_recall_mean"]),
                qualified=int(row["seeds_precision_and_recall_gte_0_80"]),
                seed_count=seed_count,
            )
        )
    return "\n".join(lines)


def _build_manifest(
    *,
    output_dir: Path,
    model_path: Path,
    seeds: Sequence[int],
    target_counts: Sequence[int],
    row_count: int,
    aggregate_count: int,
    elapsed_s: float,
) -> dict[str, Any]:
    return {
        "schema_version": "center-terminal-sensor-error-matrix-v1",
        "status": "completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "metric_condition": "search already found target",
        "source_precision": 1.0,
        "source_recall": 1.0,
        "target_resource_ratio": "1:1",
        "target_counts": list(target_counts),
        "seeds": list(seeds),
        "matrix_dimensions": {
            "handover_modes": list(HANDOVER_MODES),
            "attitude_modes": list(ATTITUDE_MODES),
            "navigation_modes": list(NAVIGATION_MODES),
            "detection_modes": list(DETECTION_MODES),
            "backends": list(BACKENDS),
        },
        "per_run_row_count": row_count,
        "aggregate_row_count": aggregate_count,
        "elapsed_s": elapsed_s,
        "association_config": asdict(association_config()),
        "model_path": str(model_path.resolve()),
        "model_sha256": _sha256(model_path),
        "model_manifest_sha256": _sha256(model_path.with_suffix(model_path.suffix + ".manifest.json")),
        "gnn_60_target_status": "unseen_scale_no_retraining",
        "airsim_status": "representative_runtime_evidence_recorded_separately_or_unavailable",
        "git_head": _command_output(("git", "rev-parse", "HEAD")),
        "git_status_short": _command_output(("git", "status", "--short")),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "outputs": {
            "per_run_metrics": "per_run_metrics.csv",
            "aggregate_metrics": "aggregate_metrics.csv",
            "report": "CENTER_TERMINAL_SENSOR_ERROR_REPORT_CN.md",
            "figures": "figures/",
            "representatives": "representative_runs/",
        },
    }


def _reproduce_text(
    output_dir: Path,
    model_path: Path,
    seeds: Sequence[int],
    target_counts: Sequence[int],
) -> str:
    seed_text = " ".join(str(value) for value in seeds)
    count_text = " ".join(str(value) for value in target_counts)
    return f"""# Reproduction

Run from the repository root. The command refuses to overwrite a non-empty output directory.

```bash
python3 -m research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.run_error_matrix \\
  --output-dir {output_dir} \\
  --model-path {model_path} \\
  --seeds {seed_text} \\
  --target-counts {count_text}
```
"""


def _protocol_payload(
    *,
    seeds: Sequence[int],
    target_counts: Sequence[int],
) -> dict[str, Any]:
    return {
        "schema_version": "center-terminal-sensor-error-protocol-v1",
        "question": (
            "Given that cooperative search has already found every target, how do "
            "navigation, attitude, gimbal and light detection errors affect center-to-terminal "
            "track association?"
        ),
        "metric_condition": "P(association succeeds | search already found target)",
        "target_counts": list(target_counts),
        "resource_counts": list(target_counts),
        "target_resource_ratio": "1:1",
        "seeds": list(seeds),
        "source_precision": 1.0,
        "source_recall": 1.0,
        "source_position_sigma_m": 1.0,
        "frame_timestamps_s": [0.2, 0.3, 0.4, 0.5, 0.6],
        "target_speed_mps": 50.0,
        "target_longest_dimension_m": 3.0,
        "observation_standoff_m": 700.0,
        "camera": {
            "width_px": 1920,
            "height_px": 1080,
            "horizontal_fov_deg": 19.0,
            "recognition_extent_px": 10.0,
        },
        "p95_error_profiles": {
            "satellite_navigation_radial_m": 5.0,
            "visual_navigation_radial_m_after_200_s": 50.0,
            "normal_body_roll_pitch_deg": 1.0,
            "normal_body_yaw_deg": 3.0,
            "normal_gimbal_deg": 0.1,
            "degraded_body_roll_pitch_deg": 5.0,
            "degraded_body_yaw_deg": 10.0,
            "degraded_gimbal_deg": 0.5,
            "additional_yaw_drift_deg_after_200_s": 1.0,
        },
        "detection_profiles": {
            "ideal": {
                "miss_probability": 0.0,
                "false_alarms_per_camera_s": 0.0,
                "center_sigma_px": 0.0,
            },
            "light": {
                "miss_probability": 0.03,
                "false_alarms_per_camera_s": 2.0,
                "center_sigma_px": 0.25,
            },
        },
        "handover_modes": list(HANDOVER_MODES),
        "backends": list(BACKENDS),
        "truth_policy": (
            "truth target identity is used only after online association for scoring"
        ),
        "timeout_policy": "offline matrix has no deadline exclusion; all rows are scored",
    }


def _metrics_contract() -> dict[str, Any]:
    return {
        "schema_version": "center-terminal-sensor-error-metrics-contract-v1",
        "binding_precision": "correct confirmed bindings / all confirmed bindings",
        "binding_recall": "correct confirmed bindings / all correct center source cues",
        "denominator": {
            "binding_recall": "target_count because center precision and recall are both 1.0",
            "seed_aggregate": "all configured seeds, including low-result runs",
        },
        "evaluation_epoch": "confirmed relations active in the final observation frame",
        "search_success_included": False,
        "timeout_included_as_failure": True,
        "acceptance_reference": {
            "precision": 0.8,
            "recall": 0.8,
            "status": "suggested comparison line, not an achieved equipment indicator",
        },
        "gnn_truth_use": "offline scoring only; truth is not a node or edge feature",
    }


def _write_source_snapshot(root: Path) -> tuple[Path, ...]:
    source_paths = (
        REPOSITORY_ROOT
        / "research_modules/independent_experiments/center_terminal_cv_campaign/common/contracts.py",
        REPOSITORY_ROOT
        / "research_modules/independent_experiments/center_terminal_cv_campaign/common/io.py",
        REPOSITORY_ROOT
        / "research_modules/independent_experiments/center_terminal_cv_campaign/common/recognition.py",
        REPOSITORY_ROOT
        / "research_modules/independent_experiments/center_terminal_cv_campaign/common/scenario.py",
        MODULE_DIR / "association.py",
        MODULE_DIR / "error_campaign.py",
        MODULE_DIR / "fixture.py",
        MODULE_DIR / "geometry.py",
        MODULE_DIR / "gnn.py",
        MODULE_DIR / "reporting.py",
        MODULE_DIR / "run_error_matrix.py",
    )
    copied: list[Path] = []
    records: list[dict[str, str]] = []
    for source in source_paths:
        relative = source.relative_to(REPOSITORY_ROOT)
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(destination)
        records.append(
            {
                "repository_path": str(relative),
                "snapshot_path": str(destination.relative_to(root.parent)),
                "sha256": _sha256(destination),
            }
        )
    write_json(root / "source_files.json", records)
    copied.append(root / "source_files.json")
    diff = _command_output(
        (
            "git",
            "diff",
            "--binary",
            "--",
            *[str(path.relative_to(REPOSITORY_ROOT)) for path in source_paths],
        )
    )
    (root / "tracked_worktree.patch").write_text(diff + "\n", encoding="utf-8")
    copied.append(root / "tracked_worktree.patch")
    return tuple(copied)


def _copy_frozen_model(root: Path, model_path: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    destination = root / model_path.name
    sidecar = model_path.with_suffix(model_path.suffix + ".manifest.json")
    shutil.copy2(model_path, destination)
    shutil.copy2(sidecar, root / sidecar.name)
    return destination


def _environment_payload() -> dict[str, Any]:
    versions: dict[str, str] = {}
    for name in ("numpy", "scipy", "torch", "matplotlib"):
        try:
            module = __import__(name)
            versions[name] = str(getattr(module, "__version__", "unknown"))
        except Exception as error:  # pragma: no cover - environment dependent
            versions[name] = f"unavailable: {error}"
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "dependencies": versions,
        "gpu": _command_output(
            (
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            )
        ),
        "gnn_device": "cpu",
        "simulator": "deterministic offline synthetic fixture",
        "airsim_used": False,
    }


def _reproduction_manifest(
    *,
    output_dir: Path,
    protocol_path: Path,
    frozen_model_path: Path,
    source_snapshot: Sequence[Path],
    seeds: Sequence[int],
    target_counts: Sequence[int],
) -> dict[str, Any]:
    relative_model = frozen_model_path.relative_to(output_dir)
    model_sidecar = frozen_model_path.with_suffix(frozen_model_path.suffix + ".manifest.json")
    command = [
        "python3",
        "-m",
        "research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.run_error_matrix",
        "--output-dir",
        "<NEW_OUTPUT_DIR>",
        "--model-path",
        str(frozen_model_path.resolve()),
        "--seeds",
        *[str(value) for value in seeds],
        "--target-counts",
        *[str(value) for value in target_counts],
    ]
    source_inputs = [
        {
            "role": "algorithm_source_snapshot",
            "path": str(path.relative_to(output_dir)),
            "sha256": _sha256(path),
        }
        for path in source_snapshot
    ]
    return {
        "schema_version": "msm-experiment-reproduction-v1",
        "experiment_id": output_dir.name,
        "status": "validation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question": (
            "Post-search center-to-terminal association under navigation, attitude, "
            "gimbal and light detection errors"
        ),
        "source": {
            "git_commit": _command_output(("git", "rev-parse", "HEAD")),
            "worktree_dirty": bool(_command_output(("git", "status", "--short"))),
            "entry_point": (
                "research_modules.independent_experiments.center_terminal_cv_campaign."
                "exp_center_handover.run_error_matrix"
            ),
            "cwd": str(REPOSITORY_ROOT),
            "command": command,
            "environment": {},
            "snapshot_root": "source_snapshot/",
        },
        "runtime": {
            "python_version": platform.python_version(),
            "dependency_lock": {
                "path": "environment.json",
                "sha256": _sha256(output_dir / "environment.json"),
            },
            "simulator": "deterministic offline synthetic fixture",
            "simulator_version": "not applicable",
            "hardware_summary": _environment_payload().get("gpu"),
        },
        "scenario": {
            "config_path": str(protocol_path.relative_to(output_dir)),
            "config_sha256": _sha256(protocol_path),
            "settings_path": None,
            "settings_sha256": None,
            "seeds": list(seeds),
            "target_count": list(target_counts),
            "resource_count": list(target_counts),
            "duration_s": 0.4,
            "clock_speed": None,
        },
        "inputs": [
            {
                "role": "model",
                "path": str(relative_model),
                "sha256": _sha256(frozen_model_path),
            },
            {
                "role": "model_manifest",
                "path": str(model_sidecar.relative_to(output_dir)),
                "sha256": _sha256(model_sidecar),
            },
            *source_inputs,
        ],
        "outputs": {
            "metrics": ["per_run_metrics.csv", "aggregate_metrics.csv", "aggregate_metrics.json"],
            "reports": ["CENTER_TERMINAL_SENSOR_ERROR_REPORT_CN.md"],
            "logs": ["run.log"],
            "figures": [
                "figures/01_association_flow.png",
                "figures/02_scale_results.png",
                "figures/03_error_heatmaps.png",
                "figures/04_realized_error_samples.png",
            ],
        },
        "metrics_contract": {
            "definitions_path": "metrics_contract.json",
            "denominators": {
                "binding_precision": "confirmed bindings",
                "binding_recall": "all center source cues in final frame",
            },
            "acceptance": {"precision": 0.8, "recall": 0.8},
            "availability_policy": "all configured rows retained; no timeout exclusions",
        },
        "reproduction": {
            "offline_replay_command": command,
            "full_rerun_command": command,
            "expected_metrics_sha256": _sha256(output_dir / "per_run_metrics.csv"),
            "comparison_tolerance": "deterministic CSV equality on the recorded software stack",
            "known_nondeterminism": [],
        },
    }


def _append_log(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(str(line).rstrip() + "\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else ()
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _mean(
    rows: Iterable[Mapping[str, Any]],
    key: str,
    *,
    backend: str | None = None,
) -> float:
    values = [
        float(row[key])
        for row in rows
        if row.get(key) is not None and (backend is None or row.get("backend") == backend)
    ]
    return float(np.mean(values)) if values else math.nan


def _configure_plotting() -> None:
    installed = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in (
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "WenQuanYi Micro Hei",
        "Microsoft YaHei",
        "SimHei",
        "DejaVu Sans",
    ):
        if candidate in installed:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    plt.rcParams["axes.unicode_minus"] = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command_output(command: Sequence[str]) -> str:
    try:
        return subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        return f"unavailable: {error}"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--seeds", type=int, nargs="+", default=DEFAULT_SEEDS)
    parser.add_argument("--target-counts", type=int, nargs="+", default=TARGET_COUNTS)
    parser.add_argument("--no-representatives", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
        run_matrix(
            output_dir=args.output_dir,
            model_path=args.model_path,
            seeds=tuple(args.seeds),
            target_counts=tuple(args.target_counts),
            write_representatives=not args.no_representatives,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
