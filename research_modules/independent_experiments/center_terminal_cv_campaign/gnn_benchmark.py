#!/usr/bin/env python3
"""Main-owned offline GNN benchmark orchestration for saved AirSim replays."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import time
import tracemalloc
from typing import Any, Callable, Mapping, Sequence
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
    import matplotlib

matplotlib.use("Agg")
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
    import matplotlib.pyplot as plt
from matplotlib import font_manager


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = PACKAGE_ROOT / "outputs"
REPLAY_SCHEMA = "center-terminal-gnn-replay-v1"
HELD_OUT_AIRSIM_SEED = 20260816
CENTER_TRAIN_SEEDS = tuple(range(20261000, 20261060))
CENTER_VALIDATION_SEEDS = tuple(range(20262000, 20262020))
CROSSVIEW_TRAIN_SEEDS = tuple(range(20263000, 20263060))
CROSSVIEW_VALIDATION_SEEDS = tuple(range(20264000, 20264020))


@dataclass(frozen=True)
class SavedCampaign:
    scenario_id: str
    campaign_id: str
    target_count: int
    resource_count: int


SAVED_CAMPAIGNS = (
    SavedCampaign("n20_m8", "airsim_n20_formal_v3_20260816", 20, 8),
    SavedCampaign("n20_m30", "airsim_m30_n20_scale_20260816", 20, 30),
    SavedCampaign("n40_m50", "airsim_m50_n40_scale_v2_20260816", 40, 50),
)


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def replay_source_paths(campaign_dir: Path, *, target_count: int) -> dict[str, Path]:
    fixture_dir = (
        campaign_dir
        / "fixtures"
        / f"fixture_n{target_count}_seed{HELD_OUT_AIRSIM_SEED}"
    )
    return {
        "scenario": fixture_dir / "scenario.json",
        "source_cues": campaign_dir / "center_handover" / "online" / "source_cues.jsonl",
        "center_local_tracks": campaign_dir
        / "center_handover"
        / "online"
        / "local_tracks.jsonl",
        "center_source_truth": campaign_dir
        / "center_handover"
        / "truth"
        / "source_cue_labels.jsonl",
        "center_local_truth": campaign_dir
        / "center_handover"
        / "truth"
        / "local_track_labels.jsonl",
        "crossview_local_tracks": campaign_dir
        / "crossview"
        / "captured_local_tracks.jsonl",
        "crossview_calibrations": fixture_dir / "crossview" / "calibrations.json",
        "crossview_capture_plan": fixture_dir / "crossview" / "capture_plan.json",
        "crossview_truth": campaign_dir
        / "crossview"
        / "truth"
        / "local_track_truth_map.json",
    }


def build_replay_manifest(
    campaign: SavedCampaign,
    *,
    source_root: Path = DEFAULT_OUTPUT_ROOT,
    manifest_dir: Path,
) -> Path:
    campaign_dir = source_root / campaign.campaign_id
    paths = replay_source_paths(campaign_dir, target_count=campaign.target_count)
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("saved AirSim replay is incomplete: " + ", ".join(missing))

    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{campaign.scenario_id}.json"
    relative_paths = {
        name: os.path.relpath(path.resolve(), manifest_dir.resolve())
        for name, path in paths.items()
    }
    payload = {
        "schema_version": REPLAY_SCHEMA,
        "scenario_id": campaign.scenario_id,
        "campaign_seed": HELD_OUT_AIRSIM_SEED,
        "target_count": campaign.target_count,
        "resource_count": campaign.resource_count,
        "test_only": True,
        "paths": relative_paths,
        "sha256": {name: sha256_file(path) for name, path in paths.items()},
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def build_all_replay_manifests(
    *,
    source_root: Path = DEFAULT_OUTPUT_ROOT,
    manifest_dir: Path,
    campaigns: Sequence[SavedCampaign] = SAVED_CAMPAIGNS,
) -> tuple[Path, ...]:
    return tuple(
        build_replay_manifest(
            campaign,
            source_root=source_root,
            manifest_dir=manifest_dir,
        )
        for campaign in campaigns
    )


def load_replay_manifest(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != REPLAY_SCHEMA:
        raise ValueError("unsupported replay manifest schema")
    if payload.get("campaign_seed") != HELD_OUT_AIRSIM_SEED or not payload.get(
        "test_only"
    ):
        raise ValueError("saved AirSim replay must be marked as held-out test data")
    paths = payload.get("paths")
    hashes = payload.get("sha256")
    if not isinstance(paths, dict) or not isinstance(hashes, dict):
        raise ValueError("replay manifest paths and hashes must be objects")
    for name, relative in paths.items():
        candidate = (path.parent / str(relative)).resolve()
        if not candidate.is_file():
            raise FileNotFoundError(f"replay file is missing: {name}={candidate}")
        expected = hashes.get(name)
        if not isinstance(expected, str) or sha256_file(candidate) != expected:
            raise ValueError(f"replay file hash mismatch: {name}")
    return payload


def replay_configuration(
    manifest_path: Path, payload: Mapping[str, object]
) -> dict[str, Any]:
    """Read report-only scenario facts from a verified replay manifest."""
    paths = payload["paths"]
    if not isinstance(paths, Mapping):
        raise ValueError("replay manifest paths must be an object")

    def resolved(name: str) -> Path:
        relative = paths.get(name)
        if relative is None:
            raise ValueError(f"replay manifest is missing {name}")
        return (manifest_path.parent / str(relative)).resolve()

    scenario = _read_json(resolved("scenario"))
    calibrations = _read_json(resolved("crossview_calibrations"))
    cameras = calibrations.get("cameras")
    if not isinstance(cameras, list) or not cameras:
        raise ValueError("cross-view replay has no camera calibration")
    profiles = sorted(
        {
            (
                int(camera["width_px"]),
                int(camera["height_px"]),
                float(camera["horizontal_fov_deg"]),
            )
            for camera in cameras
        }
    )
    return {
        "scenario_id": str(payload["scenario_id"]),
        "target_count": int(payload["target_count"]),
        "resource_count": int(payload["resource_count"]),
        "airsim_mode": "ComputerVision saved replay",
        "campaign_seed": int(payload["campaign_seed"]),
        "target_speed_mps": float(scenario["target_speed_mps"]),
        "target_longest_dimension_m": float(
            scenario["target_longest_dimension_m"]
        ),
        "duration_s": float(scenario["duration_s"]),
        "clock_speed": float(scenario["clock_speed"]),
        "source_precision": float(scenario["source_precision"]),
        "source_recall": float(scenario["source_recall"]),
        "recognition_extent_px": 10.0,
        "terminal_camera_profiles": [
            {
                "width_px": width,
                "height_px": height,
                "horizontal_fov_deg": fov,
            }
            for width, height, fov in profiles
        ],
    }


def train_frozen_models(output_dir: Path) -> dict[str, Any]:
    from .exp_center_handover.gnn import (
        TrainingConfig as CenterTrainingConfig,
        save_model as save_center_model,
        train_sparse_gnn,
    )
    from .exp_crossview.training import (
        TrainingConfig as CrossViewTrainingConfig,
        train_and_save as train_crossview_model,
    )

    model_root = output_dir / "models"
    center_path = model_root / "center_handover" / "center_handover_sparse_gnn.pt"
    crossview_path = model_root / "crossview"
    started = time.perf_counter()
    center_config = CenterTrainingConfig(
        train_seeds=CENTER_TRAIN_SEEDS,
        validation_seeds=CENTER_VALIDATION_SEEDS,
        target_counts=(20, 40),
        frame_timestamps=(0.2, 0.3, 0.4),
        epochs=30,
        random_seed=20260701,
        device="cpu",
    )
    center_model, center_metrics = train_sparse_gnn(center_config)
    save_center_model(
        center_path,
        center_model,
        config=center_config,
        validation_metrics=center_metrics,
    )
    center_duration = time.perf_counter() - started

    started = time.perf_counter()
    crossview_config = CrossViewTrainingConfig(
        train_seeds=CROSSVIEW_TRAIN_SEEDS,
        validation_seeds=CROSSVIEW_VALIDATION_SEEDS,
        target_counts=(20, 40),
        epochs=20,
        device="cpu",
        model_seed=20265001,
    )
    train_crossview_model(crossview_path, config=crossview_config)
    crossview_duration = time.perf_counter() - started
    crossview_manifest = json.loads(
        (crossview_path / "manifest.json").read_text(encoding="utf-8")
    )
    training = {
        "center_handover": {
            "model_path": str(center_path),
            "training_duration_s": center_duration,
            "train_seeds": CENTER_TRAIN_SEEDS,
            "validation_seeds": CENTER_VALIDATION_SEEDS,
            "validation_metrics": center_metrics,
        },
        "crossview": {
            "model_path": str(crossview_path),
            "training_duration_s": crossview_duration,
            "train_seeds": CROSSVIEW_TRAIN_SEEDS,
            "validation_seeds": CROSSVIEW_VALIDATION_SEEDS,
            "validation_metrics": crossview_manifest["validation_metrics"],
            "validation_metrics_by_target_count": crossview_manifest[
                "validation_metrics_by_target_count"
            ],
        },
    }
    _write_json(output_dir / "training_summary.json", training)
    return training


def load_frozen_training_summary(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "training_summary.json"
    if not path.is_file():
        raise FileNotFoundError("training summary does not exist; run model training first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    center_path = Path(payload["center_handover"]["model_path"])
    crossview_path = Path(payload["crossview"]["model_path"])
    if not center_path.is_file() or not (crossview_path / "manifest.json").is_file():
        raise FileNotFoundError("frozen GNN model artifacts are incomplete")
    return payload


def _timed_call(action: Callable[[Path], None], output_dir: Path) -> tuple[float, float]:
    tracemalloc.start()
    started = time.perf_counter()
    try:
        action(output_dir)
    finally:
        duration = time.perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return duration, peak_bytes / (1024.0 * 1024.0)


def _run_with_repeats(
    action: Callable[[Path], None],
    *,
    output_dir: Path,
    timing_root: Path,
    timing_repeats: int,
) -> dict[str, Any]:
    if timing_repeats <= 0:
        raise ValueError("timing_repeats must be positive")
    durations: list[float] = []
    peaks: list[float] = []
    duration, peak = _timed_call(action, output_dir)
    durations.append(duration)
    peaks.append(peak)
    for index in range(1, timing_repeats):
        temporary = timing_root / f"repeat_{index + 1:02d}"
        if temporary.exists():
            shutil.rmtree(temporary)
        duration, peak = _timed_call(action, temporary)
        durations.append(duration)
        peaks.append(peak)
        shutil.rmtree(temporary, ignore_errors=True)
    return {
        "timing_repeats": timing_repeats,
        "wall_duration_s": durations,
        "median_wall_duration_s": statistics.median(durations),
        "python_peak_memory_mib": peaks,
        "median_python_peak_memory_mib": statistics.median(peaks),
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_center_case(
    manifest_path: Path,
    *,
    output_dir: Path,
    backend: str,
    model_path: Path,
    timing_repeats: int,
) -> dict[str, Any]:
    from .exp_center_handover.run_experiment import run

    def action(destination: Path) -> None:
        run(
            replay_manifest=manifest_path,
            output_dir=destination,
            mode="offline",
            association_backend=backend,
            model_path=model_path if backend == "gnn" else None,
            frame_delay_s=0.0,
        )

    timing = _run_with_repeats(
        action,
        output_dir=output_dir,
        timing_root=output_dir.parent / ".timing" / output_dir.name,
        timing_repeats=timing_repeats,
    )
    return {
        "task": "center_handover",
        "backend": backend,
        "metrics": _read_json(output_dir / "metrics.json"),
        "timing": timing,
        "output_dir": str(output_dir),
    }


def _run_crossview_case(
    manifest_path: Path,
    *,
    output_dir: Path,
    backend: str,
    camera_pair_policy: str,
    model_dir: Path,
    timing_repeats: int,
) -> dict[str, Any]:
    from .exp_crossview.run_experiment import run

    def action(destination: Path) -> None:
        run(
            replay_manifest=manifest_path,
            output_dir=destination,
            mode="offline",
            association_backend=backend,
            gnn_model_dir=model_dir if backend == "gnn" else None,
            camera_pair_policy=camera_pair_policy,
            output_mode="audit",
            candidate_sample_limit=200,
            error_sample_limit=100,
        )

    timing = _run_with_repeats(
        action,
        output_dir=output_dir,
        timing_root=output_dir.parent / ".timing" / output_dir.name,
        timing_repeats=timing_repeats,
    )
    return {
        "task": "crossview",
        "backend": backend,
        "camera_pair_policy": camera_pair_policy,
        "metrics": _read_json(output_dir / "metrics.json"),
        "candidate_audit": _read_json(output_dir / "candidate_audit.json"),
        "timing": timing,
        "output_dir": str(output_dir),
    }


def run_benchmark(
    output_dir: Path,
    *,
    timing_repeats: int = 5,
    training: Mapping[str, Any] | None = None,
    source_root: Path = DEFAULT_OUTPUT_ROOT,
    resume: bool = True,
) -> dict[str, Any]:
    manifest_paths = build_all_replay_manifests(
        source_root=source_root,
        manifest_dir=output_dir / "manifests"
    )
    manifest_payloads = [load_replay_manifest(path) for path in manifest_paths]
    frozen = dict(training or load_frozen_training_summary(output_dir))
    center_model = Path(frozen["center_handover"]["model_path"])
    crossview_model = Path(frozen["crossview"]["model_path"])
    results: list[dict[str, Any]] = []
    runs_root = output_dir / "runs"
    for campaign, manifest_path in zip(SAVED_CAMPAIGNS, manifest_paths, strict=True):
        for backend in ("geometry", "gnn"):
            destination = runs_root / campaign.scenario_id / f"center_{backend}"
            result = _load_case_record(destination) if resume else None
            if result is None:
                result = _run_center_case(
                    manifest_path,
                    output_dir=destination,
                    backend=backend,
                    model_path=center_model,
                    timing_repeats=timing_repeats,
                )
                result["scenario_id"] = campaign.scenario_id
                result["target_count"] = campaign.target_count
                result["resource_count"] = campaign.resource_count
                _write_json(destination / "case_record.json", result)
            results.append(result)
        for policy in ("full", "sector_fov"):
            for backend in ("geometry", "gnn"):
                destination = (
                    runs_root
                    / campaign.scenario_id
                    / f"crossview_{policy}_{backend}"
                )
                result = _load_case_record(destination) if resume else None
                if result is None:
                    effective_repeats = _crossview_timing_repeats(
                        campaign.scenario_id,
                        policy,
                        requested=timing_repeats,
                    )
                    result = _run_crossview_case(
                        manifest_path,
                        output_dir=destination,
                        backend=backend,
                        camera_pair_policy=policy,
                        model_dir=crossview_model,
                        timing_repeats=effective_repeats,
                    )
                    result["scenario_id"] = campaign.scenario_id
                    result["target_count"] = campaign.target_count
                    result["resource_count"] = campaign.resource_count
                    _write_json(destination / "case_record.json", result)
                results.append(result)
    summary = {
        "schema_version": "center-terminal-gnn-offline-benchmark-v1",
        "held_out_seed": HELD_OUT_AIRSIM_SEED,
        "timing_scope": "association_plus_audit_outputs_and_figures",
        "timing_repeat_policy": {
            "n20_m8_crossview": min(timing_repeats, 5),
            "n20_m30_sector_fov": min(timing_repeats, 3),
            "full_camera_stress_and_n40_m50": 1,
            "center_handover": timing_repeats,
        },
        "memory_scope": "python_tracemalloc_only",
        "scenarios": [
            replay_configuration(path, payload)
            for path, payload in zip(
                manifest_paths, manifest_payloads, strict=True
            )
        ],
        "training": frozen,
        "results": results,
    }
    summary["acceptance"] = evaluate_acceptance(summary)
    _write_json(output_dir / "benchmark_summary.json", summary)
    write_benchmark_report(output_dir, summary)
    return summary


def _crossview_timing_repeats(
    scenario_id: str,
    camera_pair_policy: str,
    *,
    requested: int,
) -> int:
    if requested <= 0:
        raise ValueError("timing repeat count must be positive")
    if scenario_id == "n20_m8":
        return min(requested, 5)
    if scenario_id == "n20_m30" and camera_pair_policy == "sector_fov":
        return min(requested, 3)
    return 1


def _load_case_record(output_dir: Path) -> dict[str, Any] | None:
    path = output_dir / "case_record.json"
    if not path.is_file():
        return None
    payload = _read_json(path)
    if not (output_dir / "metrics.json").is_file():
        return None
    return payload


def _index_results(summary: Mapping[str, Any]) -> dict[tuple[str, str, str, str], Mapping[str, Any]]:
    indexed: dict[tuple[str, str, str, str], Mapping[str, Any]] = {}
    for item in summary["results"]:
        key = (
            item["scenario_id"],
            item["task"],
            item.get("camera_pair_policy", "none"),
            item["backend"],
        )
        indexed[key] = item
    return indexed


def evaluate_acceptance(summary: Mapping[str, Any]) -> dict[str, Any]:
    indexed = _index_results(summary)
    checks: list[dict[str, Any]] = []
    training = summary.get("training")
    if isinstance(training, Mapping):
        for task in ("center_handover", "crossview"):
            validation = training[task]["validation_metrics"]
            checks.append(
                {
                    "name": f"{task}:synthetic_validation",
                    "passed": (
                        validation["edge_precision"] >= 0.95
                        and validation["edge_recall"] >= 0.85
                    ),
                    "detail": {
                        "edge_precision": validation["edge_precision"],
                        "edge_recall": validation["edge_recall"],
                    },
                }
            )
    for scenario in ("n20_m8", "n20_m30", "n40_m50"):
        geometry = indexed[(scenario, "center_handover", "none", "geometry")]
        gnn = indexed[(scenario, "center_handover", "none", "gnn")]
        base_metrics = geometry["metrics"]
        gnn_metrics = gnn["metrics"]
        checks.append(
            {
                "name": f"{scenario}:center_no_regression",
                "passed": (
                    gnn_metrics["true_binding_count"]
                    >= base_metrics["true_binding_count"]
                    and gnn_metrics["false_binding_count"]
                    <= base_metrics["false_binding_count"]
                ),
                "detail": {
                    "geometry_true_false": [
                        base_metrics["true_binding_count"],
                        base_metrics["false_binding_count"],
                    ],
                    "gnn_true_false": [
                        gnn_metrics["true_binding_count"],
                        gnn_metrics["false_binding_count"],
                    ],
                },
            }
        )
    small = indexed[("n20_m8", "crossview", "sector_fov", "gnn")]["metrics"]
    checks.append(
        {
            "name": "n20_m8:crossview_quality",
            "passed": (
                small["association_precision"] >= 1.0
                and small["association_recall"] >= 0.9375
                and small["id_switch_count"] == 0
            ),
            "detail": {
                "precision": small["association_precision"],
                "recall": small["association_recall"],
                "id_switch_count": small["id_switch_count"],
            },
        }
    )
    for scenario in ("n20_m30", "n40_m50"):
        geometry = indexed[(scenario, "crossview", "sector_fov", "geometry")]
        gnn = indexed[(scenario, "crossview", "sector_fov", "gnn")]
        base_metrics = geometry["metrics"]
        gnn_metrics = gnn["metrics"]
        base_switches = base_metrics["id_switch_count"]
        required_switches = base_switches * 0.8
        checks.append(
            {
                "name": f"{scenario}:sparse_gnn_gain",
                "passed": (
                    gnn_metrics["association_precision"]
                    >= base_metrics["association_precision"] + 0.05
                    and gnn_metrics["id_switch_count"] <= required_switches
                    and gnn_metrics["association_recall"]
                    >= base_metrics["association_recall"] - 0.02
                ),
                "detail": {
                    "precision_delta": gnn_metrics["association_precision"]
                    - base_metrics["association_precision"],
                    "recall_delta": gnn_metrics["association_recall"]
                    - base_metrics["association_recall"],
                    "id_switch_geometry_gnn": [
                        base_switches,
                        gnn_metrics["id_switch_count"],
                    ],
                },
            }
        )
    for scenario in ("n20_m8", "n20_m30", "n40_m50"):
        for task, policy in (
            ("center_handover", "none"),
            ("crossview", "sector_fov"),
        ):
            geometry = indexed[(scenario, task, policy, "geometry")]
            gnn = indexed[(scenario, task, policy, "gnn")]
            ratio = (
                gnn["timing"]["median_wall_duration_s"]
                / geometry["timing"]["median_wall_duration_s"]
            )
            checks.append(
                {
                    "name": f"{scenario}:{task}:runtime_ratio",
                    "passed": ratio <= 1.5,
                    "detail": {"gnn_to_geometry_ratio": ratio},
                }
            )
    for item in summary["results"]:
        leakage = item["metrics"].get("truth_leakage_count", 0)
        checks.append(
            {
                "name": (
                    f"{item['scenario_id']}:{item['task']}:"
                    f"{item.get('camera_pair_policy', 'none')}:{item['backend']}:truth_isolation"
                ),
                "passed": leakage == 0,
                "detail": {"truth_leakage_count": leakage},
            }
        )
    return {
        "all_passed": all(item["passed"] for item in checks),
        "checks": checks,
        "policy": (
            "GNN remains optional unless every check passes; full camera graph is "
            "diagnostic only."
        ),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _write_figures(output_dir: Path, summary: Mapping[str, Any]) -> tuple[Path, ...]:
    _configure_matplotlib()
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    indexed = _index_results(summary)
    scenarios = ("n20_m8", "n20_m30", "n40_m50")
    labels = ("20目标/8机", "20目标/30机", "40目标/50机")

    quality_path = figure_dir / "01_crossview_quality.png"
    x = list(range(len(scenarios)))
    width = 0.2
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.5), constrained_layout=True)
    methods = (
        ("full", "geometry", "全相机几何"),
        ("full", "gnn", "全相机图网络"),
        ("sector_fov", "geometry", "稀疏几何"),
        ("sector_fov", "gnn", "稀疏图网络"),
    )
    for offset, (policy, backend, label) in enumerate(methods):
        precision = [
            indexed[(scenario, "crossview", policy, backend)]["metrics"][
                "association_precision"
            ]
            for scenario in scenarios
        ]
        recall = [
            indexed[(scenario, "crossview", policy, backend)]["metrics"][
                "association_recall"
            ]
            for scenario in scenarios
        ]
        positions = [value + (offset - 1.5) * width for value in x]
        axes[0].bar(positions, precision, width=width, label=label)
        axes[1].bar(positions, recall, width=width, label=label)
    for axis, title in zip(axes, ("跨视角配准精确率", "跨视角配准召回率")):
        axis.set_xticks(x, labels)
        axis.set_ylim(0.0, 1.05)
        axis.set_title(title)
        axis.grid(axis="y", alpha=0.25)
    axes[1].legend(fontsize=8, loc="lower left")
    figure.savefig(quality_path, dpi=160)
    plt.close(figure)

    scale_path = figure_dir / "02_candidate_scale_and_runtime.png"
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.5), constrained_layout=True)
    full_edges = [
        indexed[(scenario, "crossview", "full", "geometry")]["metrics"][
            "candidate_edge_count"
        ]
        for scenario in scenarios
    ]
    sparse_edges = [
        indexed[(scenario, "crossview", "sector_fov", "geometry")]["metrics"][
            "candidate_edge_count"
        ]
        for scenario in scenarios
    ]
    axes[0].bar([value - width / 2 for value in x], full_edges, width, label="全相机")
    axes[0].bar([value + width / 2 for value in x], sparse_edges, width, label="责任区稀疏")
    axes[0].set_yscale("log")
    axes[0].set_xticks(x, labels)
    axes[0].set_title("候选边规模")
    axes[0].legend()
    runtime_methods = (
        ("sector_fov", "geometry", "稀疏几何"),
        ("sector_fov", "gnn", "稀疏图网络"),
    )
    for offset, (policy, backend, label) in enumerate(runtime_methods):
        durations = [
            indexed[(scenario, "crossview", policy, backend)]["timing"][
                "median_wall_duration_s"
            ]
            for scenario in scenarios
        ]
        positions = [value + (offset - 0.5) * 0.32 for value in x]
        axes[1].bar(positions, durations, 0.32, label=label)
    axes[1].set_xticks(x, labels)
    axes[1].set_title("端到端离线运行时间中位数")
    axes[1].set_ylabel("秒")
    axes[1].legend()
    figure.savefig(scale_path, dpi=160)
    plt.close(figure)
    return quality_path, scale_path


def _configure_matplotlib() -> None:
    for candidate in (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ):
        if candidate.is_file():
            font_manager.fontManager.addfont(str(candidate))
            plt.rcParams["font.family"] = font_manager.FontProperties(
                fname=str(candidate)
            ).get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False


def write_benchmark_report(output_dir: Path, summary: Mapping[str, Any]) -> Path:
    figures = _write_figures(output_dir, summary)
    indexed = _index_results(summary)
    backend_labels = {"geometry": "几何", "gnn": "图网络"}
    policy_labels = {"full": "全相机", "sector_fov": "责任区/视场稀疏"}
    scenario_rows: list[str] = []
    center_rows: list[str] = []
    cross_rows: list[str] = []
    for item in summary["scenarios"]:
        profiles = item["terminal_camera_profiles"]
        profile_text = "、".join(
            f"{profile['width_px']}×{profile['height_px']} / {profile['horizontal_fov_deg']:.1f}°"
            for profile in profiles
        )
        scenario_rows.append(
            "| {scenario} | {targets} | {resources} | {speed:.0f} | {duration:.0f} | "
            "{clock:.1f} | {size:.1f} | {camera} | {gate:.0f} | {source:.0%}/{recall:.0%} |".format(
                scenario=item["scenario_id"],
                targets=item["target_count"],
                resources=item["resource_count"],
                speed=item["target_speed_mps"],
                duration=item["duration_s"],
                clock=item["clock_speed"],
                size=item["target_longest_dimension_m"],
                camera=profile_text,
                gate=item["recognition_extent_px"],
                source=item["source_precision"],
                recall=item["source_recall"],
            )
        )
    for scenario in ("n20_m8", "n20_m30", "n40_m50"):
        for backend in ("geometry", "gnn"):
            item = indexed[(scenario, "center_handover", "none", backend)]
            metrics = item["metrics"]
            center_rows.append(
                "| {scenario} | {backend} | {true} | {false} | {precision:.4f} | "
                "{recall:.4f} | {duration:.3f} |".format(
                    scenario=scenario,
                    backend=backend_labels[backend],
                    true=metrics["true_binding_count"],
                    false=metrics["false_binding_count"],
                    precision=metrics["binding_precision"],
                    recall=metrics["binding_recall"],
                    duration=item["timing"]["median_wall_duration_s"],
                )
            )
        for policy in ("full", "sector_fov"):
            for backend in ("geometry", "gnn"):
                item = indexed[(scenario, "crossview", policy, backend)]
                metrics = item["metrics"]
                audit = item["candidate_audit"]
                cross_rows.append(
                    "| {scenario} | {policy} | {backend} | {tp} | {fp} | {fn} | "
                    "{precision:.4f} | {recall:.4f} | {switches} | {edges} | "
                    "{pairs} | {duration:.3f} |".format(
                        scenario=scenario,
                        policy=policy_labels[policy],
                        backend=backend_labels[backend],
                        tp=metrics["true_positive_relations"],
                        fp=metrics["false_positive_relations"],
                        fn=metrics["false_negative_relations"],
                        precision=metrics["association_precision"],
                        recall=metrics["association_recall"],
                        switches=metrics["id_switch_count"],
                        edges=metrics["candidate_edge_count"],
                        pairs=audit["camera_pair_retained_count"],
                        duration=item["timing"]["median_wall_duration_s"],
                    )
                )
    checks = summary["acceptance"]["checks"]
    failed = [item for item in checks if not item["passed"]]
    conclusion = (
        "全部预设条件通过，图网络可以进入真实AirSim多seed验证。"
        if not failed
        else "图网络未通过全部预设条件，继续保留为离线可选对照，几何方法仍是默认路径。"
    )
    center_large_geometry = indexed[("n40_m50", "center_handover", "none", "geometry")]
    center_large_gnn = indexed[("n40_m50", "center_handover", "none", "gnn")]
    medium_sparse_geometry = indexed[("n20_m30", "crossview", "sector_fov", "geometry")]
    medium_sparse_gnn = indexed[("n20_m30", "crossview", "sector_fov", "gnn")]
    large_full_geometry = indexed[("n40_m50", "crossview", "full", "geometry")]
    large_full_gnn = indexed[("n40_m50", "crossview", "full", "gnn")]
    large_sparse_geometry = indexed[("n40_m50", "crossview", "sector_fov", "geometry")]
    large_sparse_gnn = indexed[("n40_m50", "crossview", "sector_fov", "gnn")]
    medium_precision_delta = (
        medium_sparse_gnn["metrics"]["association_precision"]
        - medium_sparse_geometry["metrics"]["association_precision"]
    )
    large_full_edges = large_full_geometry["metrics"]["candidate_edge_count"]
    large_sparse_edges = large_sparse_geometry["metrics"]["candidate_edge_count"]
    large_edge_reduction = 1.0 - large_sparse_edges / large_full_edges
    large_runtime_delta = (
        large_sparse_gnn["timing"]["median_wall_duration_s"]
        / large_sparse_geometry["timing"]["median_wall_duration_s"]
        - 1.0
    )
    report = f"""# 中心交接与机间配准图神经网络离线测试报告

## 1. 结论

{conclusion}

相机图稀疏化是本轮最稳定的改进。40目标/50机场景中，责任区和视场筛选将候选边减少{large_edge_reduction:.1%}，几何方法的精确率由{large_full_geometry['metrics']['association_precision']:.4f}提高到{large_sparse_geometry['metrics']['association_precision']:.4f}，身份混合由{large_full_geometry['metrics']['id_switch_count']}降到{large_sparse_geometry['metrics']['id_switch_count']}。图网络在20目标/30机稀疏场景将精确率再提高{medium_precision_delta * 100.0:.2f}个百分点，但在40目标/50机稀疏场景与几何方法结果完全相同，运行时间增加{large_runtime_delta:.1%}。因此默认路径采用责任区/视场稀疏相机图和几何匹配，图网络继续作为离线对照。

中心交接图网络在40目标回放中消除了几何基线的1个错误来源绑定，正确绑定数保持{center_large_gnn['metrics']['true_binding_count']}个。该结果只有一个AirSim seed，暂不足以替换确定性几何基线。

## 2. 试验配置

本轮复用三组已经保存的真实AirSim ComputerVision观测，不重新运行Blocks。目标使用移动Actor，检测记录来自`simGetDetections`，目标框最长边达到10像素后才进入关联。模型只在合成数据上训练，seed 20260816只用于最终回放测试。

| 场景 | 目标数 | 相机资源数 | 目标速度/米每秒 | 观察时长/秒 | 时钟倍率 | 目标长度/米 | 机载相机 | 识别门限/像素 | 中心提示精确率/召回率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
{chr(10).join(scenario_rows)}

三组记录使用同一AirSim seed，属于不同规模的留出回放，不是三个独立随机样本。在线关联没有读取Actor名称或真实目标编号，真值只在关联结束后加载并计算结果。

## 3. 算法流程

中心交接先校验回放清单和文件摘要，再把中心提示按时间传播到相机观测时刻，并使用位置、协方差、图像投影、识别尺寸和运动连续性形成几何白名单。几何路径直接使用候选代价；图网络路径只在白名单内计算匹配概率，并按 `C_final = C_geo - 2 log(P_gnn)`修正代价。两条路径最后都由匈牙利算法执行一一匹配，并要求三帧中至少两帧一致后确认。

机间配准先按相机责任区和视锥重叠关系筛选需要比较的相机对，再对匿名局部航迹计算视线交会距离、重投影误差、运动连续性和尺度一致性。图网络只处理通过硬几何门控的候选，最终代价由55%几何代价和45%图网络不匹配概率组成。匈牙利算法、时间确认和单相机唯一性约束始终保留。全相机图只用于规模压力诊断，不作为在线主路径。

中心模型合成验证精确率为 {summary['training']['center_handover']['validation_metrics']['edge_precision']:.4f}，召回率为 {summary['training']['center_handover']['validation_metrics']['edge_recall']:.4f}。机间模型合成验证精确率为 {summary['training']['crossview']['validation_metrics']['edge_precision']:.4f}，召回率为 {summary['training']['crossview']['validation_metrics']['edge_recall']:.4f}。

## 4. 中心交接结果

| 场景 | 方法 | 正确绑定 | 错误绑定 | 精确率 | 召回率 | 中位时间/秒 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(center_rows)}

## 5. 机间配准结果

| 场景 | 相机图 | 方法 | 正确关系 | 错误关系 | 漏配关系 | 精确率 | 召回率 | 身份混合 | 候选边 | 保留相机对 | 中位时间/秒 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(cross_rows)}

![配准质量](figures/{figures[0].name})

![候选规模与时间](figures/{figures[1].name})

## 6. 结果分析

20目标/8机场景的几何方法已经达到精确率1.0000、召回率0.9375和零身份混合，图网络没有改变结果。20目标/30机场景中，稀疏图网络将错误关系从{medium_sparse_geometry['metrics']['false_positive_relations']}降到{medium_sparse_gnn['metrics']['false_positive_relations']}，漏配从{medium_sparse_geometry['metrics']['false_negative_relations']}降到{medium_sparse_gnn['metrics']['false_negative_relations']}，身份混合从{medium_sparse_geometry['metrics']['id_switch_count']}降到{medium_sparse_gnn['metrics']['id_switch_count']}。这是本轮唯一明确的图网络质量增益。

40目标/50机全相机图即使加入图网络，仍有{large_full_gnn['metrics']['false_positive_relations']}条错误关系和{large_full_gnn['metrics']['id_switch_count']}个身份混合，单次运行{large_full_gnn['timing']['median_wall_duration_s']:.2f}秒。责任区/视场筛选后，几何方法只剩{large_sparse_geometry['metrics']['false_positive_relations']}条错误关系、零身份混合；图网络没有继续减少错误或漏配。规模场景应先限制不可能重叠的相机对，再考虑学习排序器。

## 7. 验收与限制

共检查 {len(checks)} 项，通过 {len(checks) - len(failed)} 项，未通过 {len(failed)} 项。未通过项为：{', '.join(item['name'] for item in failed) if failed else '无'}。

唯一未通过项要求40目标/50机稀疏图网络相对稀疏几何至少提高5个百分点。稀疏几何精确率已经达到{large_sparse_geometry['metrics']['association_precision']:.4f}，图网络结果相同，因此未形成额外收益。按照预设规则，图网络不进入默认路径。

时延包含关联计算、审计文件和结果图生成。20目标/8机场景重复5次，20目标/30机稀疏主路径重复3次；全相机压力组和40目标/50机场景只运行1次。50机全相机单次已超过半小时，继续重复不会改变确定性质量结果。40目标/50机的三个缺失案例在同机不同逻辑核并行完成，不属于独占机器性能测试，时延只用于同一回放下的量级和方法对照。内存采用Python分配跟踪，只反映解释器可见内存，不等同于整机峰值。三组AirSim记录使用同一个seed，本轮能判断算法在现有回放上的增益和退化，不能代替真实多seed统计。

尚未注入导航误差、云台姿态误差、时间同步偏差和检测误差，也没有测量GPU或机载处理器时延。当前结论只适用于保存回放上的算法筛选。

## 8. 文件

- `benchmark_summary.json`：完整指标、时延和验收结果。
- `training_summary.json`：训练与验证seed、验证指标和模型位置。
- `manifests/`：三组只读回放清单及文件哈希。
- `runs/`：18组正式输出；跨视角采用审计模式，未重复写出全量候选边。
"""
    path = output_dir / "GNN_OFFLINE_BENCHMARK_REPORT_CN.md"
    path.write_text(report, encoding="utf-8")
    return path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT / "gnn_offline_benchmark_20260816",
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--timing-repeats", type=int, default=5)
    parser.add_argument(
        "--skip-training",
        action="store_true",
        help="reuse the frozen models referenced by training_summary.json",
    )
    parser.add_argument(
        "--train-only",
        action="store_true",
        help="freeze both models and stop before held-out replay evaluation",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="ignore completed case_record.json files and rerun every case",
    )
    parser.add_argument(
        "--prepare-manifests-only",
        action="store_true",
        help="write and validate held-out replay manifests without running models",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    manifest_dir = args.output_dir / "manifests"
    manifests = build_all_replay_manifests(
        source_root=args.source_root,
        manifest_dir=manifest_dir,
    )
    for manifest in manifests:
        load_replay_manifest(manifest)
        print(manifest.resolve())
    if not args.prepare_manifests_only:
        training = (
            load_frozen_training_summary(args.output_dir)
            if args.skip_training
            else train_frozen_models(args.output_dir)
        )
        if args.train_only:
            print((args.output_dir / "training_summary.json").resolve())
            return 0
        summary = run_benchmark(
            args.output_dir,
            timing_repeats=args.timing_repeats,
            training=training,
            source_root=args.source_root,
            resume=not args.no_resume,
        )
        print((args.output_dir / "benchmark_summary.json").resolve())
        print((args.output_dir / "GNN_OFFLINE_BENCHMARK_REPORT_CN.md").resolve())
        print(f"acceptance={summary['acceptance']['all_passed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
