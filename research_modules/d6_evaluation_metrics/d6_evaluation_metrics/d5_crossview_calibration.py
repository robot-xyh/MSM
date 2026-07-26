"""Offline, truth-isolated calibration of D5 cross-view candidate graphs.

The evaluator consumes finalized ``d5.tracklet-dataset.v2`` datasets through
the D5 strict loader.  ``graph.edge_index`` is treated only as the output of
geometry candidate generation.  The dataset has no model edge probability,
decision threshold, or cluster output, so this module cannot measure G1
scoring benefit.  Online graph arrays and evaluator-only labels remain
physically separate until this offline module computes candidate-graph
metrics.  No result is written back to D5 or to any assignment or control
path.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import csv
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


D5_CROSSVIEW_CALIBRATION_SCHEMA_VERSION = "d6.d5-crossview-calibration.v1"
D5_CROSSVIEW_FRAME_INDEX_SCHEMA_VERSION = "d6.d5-crossview-frame-index.v1"
D5_CROSSVIEW_CALIBRATION_DATE = "2026-07-26"
DEFAULT_MEASUREMENT_WINDOW_S = 0.35
DEFAULT_ARRIVAL_WINDOW_S = 1.0
DEFAULT_BOOTSTRAP_RESAMPLES = 2_000
DEFAULT_BOOTSTRAP_RNG_SEED = 20260726
SUPPORTED_VARIANTS = ("R0", "G1")

_HARD_VIOLATION_FIELDS = (
    "same_camera_edge_count",
    "self_loop_count",
    "duplicate_undirected_edge_count",
    "missing_label_node_count",
    "duplicate_label_key_count",
    "non_finite_array_count",
    "non_finite_value_count",
    "duplicate_tracklet_key_count",
    "invalid_edge_endpoint_count",
    "time_ineligible_candidate_edge_count",
)
_COUNT_FIELDS = (
    "frame_count",
    "node_count",
    "edge_count",
    "time_eligible_true_pair_count",
    "geometry_retained_true_edge_count",
    "geometry_retained_false_edge_count",
    *_HARD_VIOLATION_FIELDS,
)
_RATIO_FIELDS = (
    "geometry_false_edge_rate",
    "geometry_candidate_precision",
    "geometry_candidate_recall",
    "geometry_candidate_f1",
)
_GRAPH_NUMERIC_ARRAY_NAMES = (
    "node_features",
    "edge_index",
    "edge_features",
    "measurement_timestamps",
    "arrival_timestamps",
    "gate_scores",
    "candidate_count_values",
)


class D5CrossviewCalibrationError(ValueError):
    """Stable fail-closed error at the D5 dataset to D6 evaluator boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True, slots=True)
class D5CrossviewDatasetInput:
    """One explicitly named R0 or G1 finalized D5 dataset."""

    variant: str
    dataset_dir: Path
    frame_index_sidecar: Path | None = None

    def __post_init__(self) -> None:
        variant = str(self.variant).strip().upper()
        if variant not in SUPPORTED_VARIANTS:
            raise ValueError(f"variant must be one of {SUPPORTED_VARIANTS}")
        object.__setattr__(self, "variant", variant)
        object.__setattr__(
            self,
            "dataset_dir",
            Path(self.dataset_dir).expanduser().resolve(),
        )
        object.__setattr__(
            self,
            "frame_index_sidecar",
            (
                None
                if self.frame_index_sidecar is None
                else Path(self.frame_index_sidecar).expanduser().resolve()
            ),
        )


@dataclass(frozen=True, slots=True)
class D5CrossviewCalibrationConfig:
    """Evaluation mode, time gates, and deterministic statistical settings."""

    mode: str = "development"
    expected_seeds: tuple[int, ...] = ()
    measurement_window_s: float = DEFAULT_MEASUREMENT_WINDOW_S
    arrival_window_s: float = DEFAULT_ARRIVAL_WINDOW_S
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES
    bootstrap_rng_seed: int = DEFAULT_BOOTSTRAP_RNG_SEED

    def __post_init__(self) -> None:
        mode = str(self.mode).strip().lower()
        if mode not in {"development", "formal"}:
            raise ValueError("mode must be development or formal")
        seeds = tuple(int(seed) for seed in self.expected_seeds)
        if len(seeds) != len(set(seeds)):
            raise ValueError("expected_seeds must be unique")
        if any(seed < 0 for seed in seeds):
            raise ValueError("expected_seeds must be non-negative")
        measurement = float(self.measurement_window_s)
        arrival = float(self.arrival_window_s)
        if not math.isfinite(measurement) or measurement <= 0.0:
            raise ValueError("measurement_window_s must be finite and positive")
        if not math.isfinite(arrival) or arrival <= 0.0:
            raise ValueError("arrival_window_s must be finite and positive")
        if int(self.bootstrap_resamples) <= 0:
            raise ValueError("bootstrap_resamples must be positive")
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "expected_seeds", tuple(sorted(seeds)))
        object.__setattr__(self, "measurement_window_s", measurement)
        object.__setattr__(self, "arrival_window_s", arrival)
        object.__setattr__(self, "bootstrap_resamples", int(self.bootstrap_resamples))
        object.__setattr__(self, "bootstrap_rng_seed", int(self.bootstrap_rng_seed))


def evaluate_d5_crossview_calibration(
    datasets: Sequence[D5CrossviewDatasetInput],
    *,
    config: D5CrossviewCalibrationConfig | None = None,
) -> dict[str, Any]:
    """Evaluate explicit candidate graph variants without granting authority."""

    cfg = config or D5CrossviewCalibrationConfig()
    inputs = tuple(datasets)
    if not inputs:
        raise D5CrossviewCalibrationError(
            "dataset_input_missing",
            "at least one explicit R0 or G1 dataset is required",
        )
    variants = tuple(item.variant for item in inputs)
    if len(variants) != len(set(variants)):
        raise D5CrossviewCalibrationError(
            "dataset_variant_duplicate",
            "each variant may be supplied at most once",
        )
    roots = tuple(item.dataset_dir for item in inputs)
    if len(roots) != len(set(roots)):
        raise D5CrossviewCalibrationError(
            "dataset_path_duplicate",
            "R0 and G1 must not alias the same dataset directory",
        )

    blockers: list[str] = []
    variant_results: dict[str, dict[str, Any]] = {}
    for item in sorted(inputs, key=lambda value: value.variant):
        result = _evaluate_dataset(item, cfg)
        variant_results[item.variant] = result
        blockers.extend(
            f"{item.variant}:{reason}" for reason in result.get("blockers", ())
        )

    comparison = _compare_variants(variant_results)
    if cfg.mode == "formal" and comparison["required"] and not comparison["comparable"]:
        blockers.append("R0_G1:paired_frame_or_node_contract_mismatch")

    all_scenarios = sorted(
        {
            scenario
            for result in variant_results.values()
            for scenario in result.get("_scenario_values", ())
        }
    )
    all_seeds = sorted(
        {
            seed
            for result in variant_results.values()
            for seed in result.get("_seed_values", ())
        }
    )
    summary = {
        "dataset_count": _available(len(inputs)),
        "scenario_version": (
            _available(all_scenarios[0])
            if len(all_scenarios) == 1
            else _unavailable(
                "scenario_version_missing"
                if not all_scenarios
                else "mixed_scenario_versions"
            )
        ),
        "unique_seed_count": _available(len(all_seeds)),
        "unique_seed_values": _available(all_seeds),
        "frame_count": _sum_available_variant_count(variant_results, "frame_count"),
        "node_count": _sum_available_variant_count(variant_results, "node_count"),
        "edge_count": _sum_available_variant_count(variant_results, "edge_count"),
    }

    if cfg.mode == "formal":
        if len(cfg.expected_seeds) < 20:
            blockers.append("formal_expected_seed_count_below_20")
        if len(all_scenarios) != 1:
            blockers.append("formal_scenario_version_not_uniform")
        if not cfg.expected_seeds:
            blockers.append("formal_expected_seeds_missing")
    hard_total = sum(
        int(result["hard_violations"]["total"])
        for result in variant_results.values()
    )
    if hard_total:
        blockers.append("hard_violation_count_nonzero")

    blockers = sorted(set(blockers))
    if cfg.mode == "formal":
        formal_acceptance = not blockers
        status = "pass" if formal_acceptance else "fail_closed"
        descriptive_only = False
    else:
        formal_acceptance = False
        status = (
            "fail_closed"
            if hard_total or _input_contract_failed(variant_results)
            else "development_descriptive"
        )
        descriptive_only = True
        if status == "fail_closed" and not blockers:
            blockers.append("development_input_integrity_failure")

    public_variants = {
        variant: _drop_private_keys(result)
        for variant, result in sorted(variant_results.items())
    }
    report: dict[str, Any] = {
        "schema_version": D5_CROSSVIEW_CALIBRATION_SCHEMA_VERSION,
        "evaluation_date": D5_CROSSVIEW_CALIBRATION_DATE,
        "evaluation_scope": "candidate_graph_geometry_calibration",
        "status": status,
        "mode": cfg.mode,
        "formal_acceptance": formal_acceptance,
        "descriptive_only": descriptive_only,
        "conclusion_scope": (
            "formal_candidate_graph_geometry_contract_only"
            if formal_acceptance
            else "candidate_graph_single_or_multi_seed_descriptive_only"
            if status == "development_descriptive"
            else "failed_closed_input_or_contract"
        ),
        "configuration": {
            "expected_seeds": list(cfg.expected_seeds),
            "expected_seed_count": len(cfg.expected_seeds),
            "measurement_window_s": cfg.measurement_window_s,
            "arrival_window_s": cfg.arrival_window_s,
            "bootstrap_resamples": cfg.bootstrap_resamples,
            "bootstrap_rng_seed": cfg.bootstrap_rng_seed,
            "frame_semantics": "one_finalized_dataset_episode_is_one_graph_frame",
            "stable_pair_coordinate": "scenario_version_seed_explicit_frame_index",
            "episode_id_pairing_allowed": False,
            "scale_inference_from_scenario_name": False,
        },
        "availability_summary": summary,
        "variants": public_variants,
        "candidate_graph_R0_G1_comparison": comparison,
        "hard_violation_count": hard_total,
        "blockers": blockers,
        "unsupported_metrics": {
            "G1_edge_scoring_benefit": _unavailable(
                "dataset_contains_no_edge_probabilities_or_decision_threshold"
            ),
            "G1_selected_edge_metrics": _unavailable(
                "dataset_edge_index_is_geometry_candidate_set_not_model_selection"
            ),
            "cluster_purity": _unavailable(
                "dataset_contains_no_model_clusters"
            ),
            "global_track_id_binding_correctness": _unavailable(
                "input_contract_contains_no_center_binding_result"
            ),
            "control_outcome": _unavailable(
                "input_contract_contains_no_guidance_or_control_record"
            ),
            "physical_intercept_outcome": _unavailable(
                "input_contract_contains_no_physical_result"
            ),
        },
        "truth_and_identity_boundary": {
            "dataset_loader": "d5.load_tracklet_dataset",
            "graph_edge_semantics": "geometry_candidate_edges_only",
            "model_edge_probabilities_present": False,
            "model_decision_threshold_present": False,
            "model_clusters_present": False,
            "online_graph_truth_field_count": 0,
            "truth_join_scope": "offline_evaluator_labels_only",
            "writes_back_to_d5_d3_d7": False,
            "global_track_id_created_or_rebound": False,
        },
        "authority": {
            "evaluation_only": True,
            "model_promotion": False,
            "default_path": False,
            "assignment": False,
            "failover": False,
            "control": False,
        },
        "availability_policy": {
            "zero_fill_allowed": False,
            "missing_denominator": "unavailable",
            "missing_label": "unavailable_and_fail_closed_in_formal",
            "strict_loader_failure": "fail_closed",
            "scenario_name_scale_inference": False,
        },
    }
    return _with_content_sha256(report)


def write_d5_crossview_calibration_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
    *,
    datasets: Sequence[D5CrossviewDatasetInput],
) -> dict[str, Path]:
    """Atomically write aggregate JSON, per-seed CSV, Chinese Markdown, and SHA."""

    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise D5CrossviewCalibrationError(
            "output_directory_exists",
            str(output),
        )
    for item in datasets:
        if _paths_overlap(output, item.dataset_dir):
            raise D5CrossviewCalibrationError(
                "output_input_overlap",
                f"{output} overlaps {item.dataset_dir}",
            )
        if (
            item.frame_index_sidecar is not None
            and _paths_overlap(output, item.frame_index_sidecar)
        ):
            raise D5CrossviewCalibrationError(
                "output_input_overlap",
                f"{output} overlaps {item.frame_index_sidecar}",
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent)
    )
    try:
        json_path = staging / "d5_crossview_calibration_aggregate.json"
        csv_path = staging / "d5_crossview_calibration_per_seed.csv"
        markdown_path = staging / "D5_CROSSVIEW_CALIBRATION_CN.md"
        checksums_path = staging / "SHA256SUMS"
        _write_json(json_path, result)
        _write_seed_csv(csv_path, result)
        markdown_path.write_text(
            render_d5_crossview_calibration_markdown(result),
            encoding="utf-8",
        )
        artifacts = (json_path, csv_path, markdown_path)
        checksums_path.write_text(
            "".join(
                f"{_sha256_file(path)}  {path.name}\n"
                for path in sorted(artifacts, key=lambda value: value.name)
            ),
            encoding="ascii",
        )
        os.replace(staging, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "json": output / "d5_crossview_calibration_aggregate.json",
        "csv": output / "d5_crossview_calibration_per_seed.csv",
        "markdown": output / "D5_CROSSVIEW_CALIBRATION_CN.md",
        "checksums": output / "SHA256SUMS",
    }


def render_d5_crossview_calibration_markdown(result: Mapping[str, Any]) -> str:
    """Render a concise Chinese calibration report with explicit limitations."""

    summary = result["availability_summary"]
    lines = [
        "# D5 跨视角候选图几何校准",
        "",
        "## 结论",
        "",
        (
            f"本次状态为 `{result['status']}`，模式为 `{result['mode']}`。"
            f"正式合同通过为 `{result['formal_acceptance']}`。"
        ),
        "该结论只覆盖几何门后匿名候选图和离线标签。数据集不含边概率、判定阈值和聚类结果，"
        "因此不能评价 G1 打分收益。模型晋级、默认路径、分配、降级和控制权限均未开放。",
        "",
        "## 数据范围",
        "",
        f"- 数据集数：{_metric_text(summary['dataset_count'])}。",
        f"- 场景版本：{_metric_text(summary['scenario_version'])}。",
        f"- seed 数：{_metric_text(summary['unique_seed_count'])}。",
        f"- 图帧、节点、候选边：{_metric_text(summary['frame_count'])} / "
        f"{_metric_text(summary['node_count'])} / {_metric_text(summary['edge_count'])}。",
        "- 一个 finalized dataset episode 按一个图帧计算，未从场景名称推断规模。",
        "",
        "## 候选边结果",
        "",
        "| 候选图变体 | 图帧 | seed | 真值时间合格对 | 几何保留真边 | 几何保留假边 | 候选精确率 | 候选召回率 | 候选 F1 | 几何假边率 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant, payload in result["variants"].items():
        aggregate = payload["aggregate"]
        lines.append(
            f"| {variant} | {_metric_text(payload['counts']['frame_count'])} | "
            f"{_metric_text(payload['counts']['unique_seed_count'])} | "
            f"{aggregate['time_eligible_true_pair_count']} | "
            f"{aggregate['geometry_retained_true_edge_count']} | "
            f"{aggregate['geometry_retained_false_edge_count']} | "
            f"{_metric_text(aggregate['geometry_candidate_precision'])} | "
            f"{_metric_text(aggregate['geometry_candidate_recall'])} | "
            f"{_metric_text(aggregate['geometry_candidate_f1'])} | "
            f"{_metric_text(aggregate['geometry_false_edge_rate'])} |"
        )

    lines.extend(
        [
            "",
            "## 完整性",
            "",
            "| 变体 | 标签完整覆盖 | 候选召回声明覆盖 | 硬违规 | 严格加载 |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for variant, payload in result["variants"].items():
        coverage = payload["coverage"]
        lines.append(
            f"| {variant} | {_metric_text(coverage['labels_complete_ratio'])} | "
            f"{_metric_text(coverage['candidate_recall_available_ratio'])} | "
            f"{payload['hard_violations']['total']} | "
            f"{payload['strict_loader']['status']} |"
        )
    lines.extend(
        [
            "",
            "逐帧指标保存在聚合 JSON，逐 seed 微平均指标保存在 CSV。无候选边、无同真值跨相机对"
            "或标签声明不完整时，对应比率保持不可用，没有补零。",
            "R0/G1 候选图只按显式 sidecar 中的场景版本、seed 和 frame_index 配对。episode_id "
            "不参与配对；缺少稳定帧坐标时比较保持不可用，formal 成对比较失败关闭。",
            "",
            "## 未覆盖指标",
            "",
            "- G1 打分收益：输入没有边概率和判定阈值。",
            "- 聚类纯度：输入没有模型聚类结果。",
            "- 中心全局航迹绑定正确率：输入没有中心绑定字段。",
            "- 控制与物理拦截结果：输入没有导引、控制或物理结果记录。",
            "",
            "## 失败项",
            "",
        ]
    )
    blockers = result.get("blockers", ())
    if blockers:
        lines.extend(f"- `{value}`" for value in blockers)
    else:
        lines.append("- 无输入合同失败项。")
    lines.append("")
    return "\n".join(lines)


def load_expected_seeds_file(path: str | Path) -> tuple[int, ...]:
    """Load an explicit JSON list or newline/comma-separated seed file."""

    source = Path(path)
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        raise D5CrossviewCalibrationError(
            "expected_seed_file_empty",
            str(source),
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = [
            token
            for line in text.splitlines()
            for token in line.replace(",", " ").split()
        ]
    if not isinstance(payload, list):
        raise D5CrossviewCalibrationError(
            "expected_seed_file_invalid",
            "seed file must contain a JSON list or separated integers",
        )
    try:
        seeds = tuple(int(value) for value in payload)
    except (TypeError, ValueError) as exc:
        raise D5CrossviewCalibrationError(
            "expected_seed_file_invalid",
            "seed file contains a non-integer value",
        ) from exc
    if len(seeds) != len(set(seeds)):
        raise D5CrossviewCalibrationError(
            "expected_seed_file_duplicate",
            "seed file contains duplicates",
        )
    return tuple(sorted(seeds))


def verify_sha256sums(output_dir: str | Path) -> bool:
    """Verify the generated report inventory exactly and deterministically."""

    root = Path(output_dir)
    checksum_path = root / "SHA256SUMS"
    if not checksum_path.is_file():
        return False
    expected_names = {
        "D5_CROSSVIEW_CALIBRATION_CN.md",
        "d5_crossview_calibration_aggregate.json",
        "d5_crossview_calibration_per_seed.csv",
    }
    parsed: dict[str, str] = {}
    previous = ""
    for line in checksum_path.read_text(encoding="ascii").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            return False
        digest, name = parts
        if (
            len(digest) != 64
            or any(value not in "0123456789abcdef" for value in digest)
            or not name
            or name <= previous
            or name in parsed
        ):
            return False
        parsed[name] = digest
        previous = name
    if set(parsed) != expected_names:
        return False
    return all(
        (root / name).is_file() and _sha256_file(root / name) == digest
        for name, digest in parsed.items()
    )


def _evaluate_dataset(
    item: D5CrossviewDatasetInput,
    config: D5CrossviewCalibrationConfig,
) -> dict[str, Any]:
    preflight = _preflight_dataset(item.dataset_dir)
    blockers: list[str] = []
    try:
        api = _load_d5_dataset_api()
        dataset = api.load_tracklet_dataset(item.dataset_dir)
    except Exception as exc:  # D5 exposes a stable ``code`` on validation errors.
        code = str(getattr(exc, "code", "strict_loader_failure"))
        blockers.append(f"strict_loader:{code}")
        hard = dict(preflight["hard_violations"])
        hard["loader_validation_failure_count"] = 1
        hard["total"] = sum(
            int(value) for key, value in hard.items() if key != "total"
        )
        return {
            "variant": item.variant,
            "dataset_dir": str(item.dataset_dir),
            "manifest_sha256": preflight.get("manifest_sha256"),
            "strict_loader": {
                "status": "fail_closed",
                "available": False,
                "reason": code,
            },
            "frame_index_sidecar": {
                "status": "unavailable",
                "availability": "unavailable",
                "reason": "strict_dataset_loader_failed",
                "path": (
                    None
                    if item.frame_index_sidecar is None
                    else str(item.frame_index_sidecar)
                ),
                "sha256": None,
            },
            "counts": {
                "frame_count": _availability_from_optional(preflight.get("frame_count")),
                "unique_seed_count": _availability_from_optional(
                    len(preflight.get("seed_values", ()))
                ),
                "node_count": _availability_from_optional(preflight.get("node_count")),
                "edge_count": _availability_from_optional(preflight.get("edge_count")),
            },
            "coverage": {
                "labels_complete_ratio": _unavailable("strict_loader_failed"),
                "candidate_recall_available_ratio": _unavailable("strict_loader_failed"),
            },
            "frames": [],
            "per_seed": [],
            "aggregate": _empty_aggregate("strict_loader_failed"),
            "seed_statistics": {},
            "hard_violations": hard,
            "blockers": blockers,
            "_scenario_values": tuple(preflight.get("scenario_values", ())),
            "_seed_values": tuple(preflight.get("seed_values", ())),
            "_frame_contracts": {},
        }

    sidecar_blockers: list[str] = []
    try:
        frame_indices, sidecar_evidence = _load_frame_index_sidecar(
            item.frame_index_sidecar,
            dataset,
        )
    except D5CrossviewCalibrationError as exc:
        frame_indices = {}
        sidecar_evidence = {
            "status": "fail_closed",
            "availability": "unavailable",
            "reason": exc.code,
            "path": (
                None
                if item.frame_index_sidecar is None
                else str(item.frame_index_sidecar)
            ),
            "sha256": (
                _sha256_file(item.frame_index_sidecar)
                if item.frame_index_sidecar is not None
                and item.frame_index_sidecar.is_file()
                else None
            ),
        }
        sidecar_blockers.append(f"frame_index_sidecar:{exc.code}")
    blockers.extend(sidecar_blockers)
    frames = [
        _evaluate_loaded_frame(
            episode,
            measurement_window_s=config.measurement_window_s,
            arrival_window_s=config.arrival_window_s,
            frame_index=frame_indices.get(episode.graph.episode_uid),
            raw_hard=preflight["frame_hard_violations"].get(
                episode.graph.episode_uid,
                _zero_hard_violations(),
            ),
        )
        for episode in dataset.episodes
    ]
    per_seed = _aggregate_per_seed(frames)
    aggregate = _aggregate_frames(frames)
    seed_statistics = _seed_statistics(
        per_seed,
        bootstrap_resamples=config.bootstrap_resamples,
        bootstrap_rng_seed=config.bootstrap_rng_seed,
        variant=item.variant,
    )
    scenarios = sorted({frame["scenario_version"] for frame in frames})
    seeds = sorted({int(frame["seed"]) for frame in frames})
    labels_complete_count = sum(bool(frame["labels_complete"]) for frame in frames)
    candidate_available_count = sum(
        bool(frame["candidate_recall_available"]) for frame in frames
    )
    hard = _sum_hard_violations(frame["hard_violations"] for frame in frames)

    if config.mode == "formal":
        expected = set(config.expected_seeds)
        actual = set(seeds)
        if actual != expected:
            blockers.append(
                "formal_seed_set_mismatch:"
                f"missing={sorted(expected - actual)}:"
                f"extra={sorted(actual - expected)}"
            )
        if len(scenarios) != 1:
            blockers.append("formal_scenario_version_not_uniform")
        if labels_complete_count != len(frames):
            blockers.append("formal_labels_not_complete")
        if candidate_available_count != len(frames):
            blockers.append("formal_candidate_recall_not_declared_for_all_frames")
        if aggregate["geometry_candidate_recall"]["availability"] != "available":
            blockers.append("formal_candidate_recall_denominator_unavailable")
    if hard["total"]:
        blockers.append("hard_violation_count_nonzero")

    frame_contracts = (
        {
            (
                frame["scenario_version"],
                int(frame["seed"]),
                int(frame["frame_index"]),
            ): frame["_comparison_contract"]
            for frame in frames
        }
        if sidecar_evidence["status"] == "pass"
        else {}
    )
    public_frames = [_drop_private_keys(frame) for frame in frames]
    return {
        "variant": item.variant,
        "dataset_dir": str(item.dataset_dir),
        "manifest_sha256": dataset.manifest_sha256,
        "strict_loader": {
            "status": "pass",
            "available": True,
            "reason": None,
        },
        "frame_index_sidecar": sidecar_evidence,
        "counts": {
            "frame_count": _available(len(frames)),
            "unique_seed_count": _available(len(seeds)),
            "node_count": _available(sum(frame["node_count"] for frame in frames)),
            "edge_count": _available(sum(frame["edge_count"] for frame in frames)),
        },
        "coverage": {
            "labels_complete_ratio": _ratio_metric(
                labels_complete_count,
                len(frames),
                "no_frames",
            ),
            "candidate_recall_available_ratio": _ratio_metric(
                candidate_available_count,
                len(frames),
                "no_frames",
            ),
            "labels_complete_frame_count": labels_complete_count,
            "candidate_recall_available_frame_count": candidate_available_count,
        },
        "frames": public_frames,
        "per_seed": per_seed,
        "aggregate": aggregate,
        "seed_statistics": seed_statistics,
        "hard_violations": hard,
        "blockers": sorted(set(blockers)),
        "_scenario_values": tuple(scenarios),
        "_seed_values": tuple(seeds),
        "_frame_contracts": frame_contracts,
    }


def _evaluate_loaded_frame(
    episode: Any,
    *,
    measurement_window_s: float,
    arrival_window_s: float,
    frame_index: int | None,
    raw_hard: Mapping[str, int],
) -> dict[str, Any]:
    graph = episode.graph
    labels = episode.evaluator_labels.by_tracklet_key
    positive_pairs: set[tuple[int, int]] = set()
    for left in range(graph.node_count):
        left_label = labels.get(graph.tracklet_keys[left])
        if left_label is None:
            continue
        for right in range(left + 1, graph.node_count):
            right_label = labels.get(graph.tracklet_keys[right])
            if right_label is None:
                continue
            if graph.camera_keys[left] == graph.camera_keys[right]:
                continue
            if left_label.truth_entity_id != right_label.truth_entity_id:
                continue
            if not _time_eligible(
                graph,
                left,
                right,
                measurement_window_s=measurement_window_s,
                arrival_window_s=arrival_window_s,
            ):
                continue
            positive_pairs.add((left, right))

    retained_true = 0
    retained_false = 0
    time_ineligible = 0
    for raw_left, raw_right in graph.edge_index.T:
        left = int(raw_left)
        right = int(raw_right)
        if left == right or not 0 <= left < graph.node_count or not 0 <= right < graph.node_count:
            continue
        if graph.camera_keys[left] == graph.camera_keys[right]:
            continue
        left_label = labels.get(graph.tracklet_keys[left])
        right_label = labels.get(graph.tracklet_keys[right])
        if left_label is None or right_label is None:
            continue
        if not _time_eligible(
            graph,
            left,
            right,
            measurement_window_s=measurement_window_s,
            arrival_window_s=arrival_window_s,
        ):
            time_ineligible += 1
            continue
        if left_label.truth_entity_id == right_label.truth_entity_id:
            retained_true += 1
        else:
            retained_false += 1

    label_complete = bool(episode.evaluator_labels.labels_complete)
    recall_declared = bool(episode.evaluator_labels.candidate_recall_available)
    ratios = _edge_metrics(
        retained_true,
        retained_false,
        len(positive_pairs),
        recall_available=label_complete and recall_declared,
    )
    hard = dict(raw_hard)
    hard["time_ineligible_candidate_edge_count"] = time_ineligible
    hard["total"] = sum(
        int(value) for key, value in hard.items() if key != "total"
    )
    comparison_contract = {
        key: (
            graph.camera_keys[index],
            float(graph.measurement_timestamps[index]),
            float(graph.arrival_timestamps[index]),
            labels[key].truth_entity_id if key in labels else None,
        )
        for index, key in enumerate(graph.tracklet_keys)
    }
    return {
        "episode_uid": graph.episode_uid,
        "episode_id": graph.episode_id,
        "frame_index": frame_index,
        "frame_coordinate_availability": (
            "available" if frame_index is not None else "unavailable"
        ),
        "scenario_version": graph.scenario_version,
        "seed": int(graph.seed),
        "split": episode.split,
        "node_count": graph.node_count,
        "edge_count": graph.edge_count,
        "labels_complete": label_complete,
        "candidate_recall_available": recall_declared,
        "time_eligible_true_pair_count": len(positive_pairs),
        "geometry_retained_true_edge_count": retained_true,
        "geometry_retained_false_edge_count": retained_false,
        **ratios,
        "hard_violations": hard,
        "_comparison_contract": comparison_contract,
    }


def _aggregate_per_seed(frames: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for frame in frames:
        grouped[int(frame["seed"])].append(frame)
    rows: list[dict[str, Any]] = []
    for seed in sorted(grouped):
        members = grouped[seed]
        true_pairs = sum(int(item["time_eligible_true_pair_count"]) for item in members)
        retained_true = sum(
            int(item["geometry_retained_true_edge_count"]) for item in members
        )
        retained_false = sum(
            int(item["geometry_retained_false_edge_count"]) for item in members
        )
        recall_available = all(
            bool(item["labels_complete"]) and bool(item["candidate_recall_available"])
            for item in members
        )
        row = {
            "seed": seed,
            "scenario_versions": sorted(
                {str(item["scenario_version"]) for item in members}
            ),
            "frame_count": len(members),
            "node_count": sum(int(item["node_count"]) for item in members),
            "edge_count": sum(int(item["edge_count"]) for item in members),
            "labels_complete_frame_count": sum(
                bool(item["labels_complete"]) for item in members
            ),
            "candidate_recall_available_frame_count": sum(
                bool(item["candidate_recall_available"]) for item in members
            ),
            "time_eligible_true_pair_count": true_pairs,
            "geometry_retained_true_edge_count": retained_true,
            "geometry_retained_false_edge_count": retained_false,
            **_edge_metrics(
                retained_true,
                retained_false,
                true_pairs,
                recall_available=recall_available,
            ),
            "hard_violations": _sum_hard_violations(
                item["hard_violations"] for item in members
            ),
        }
        rows.append(row)
    return rows


def _aggregate_frames(frames: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not frames:
        return _empty_aggregate("no_loaded_frames")
    true_pairs = sum(int(item["time_eligible_true_pair_count"]) for item in frames)
    retained_true = sum(
        int(item["geometry_retained_true_edge_count"]) for item in frames
    )
    retained_false = sum(
        int(item["geometry_retained_false_edge_count"]) for item in frames
    )
    recall_available = all(
        bool(item["labels_complete"]) and bool(item["candidate_recall_available"])
        for item in frames
    )
    return {
        "frame_count": len(frames),
        "time_eligible_true_pair_count": true_pairs,
        "geometry_retained_true_edge_count": retained_true,
        "geometry_retained_false_edge_count": retained_false,
        **_edge_metrics(
            retained_true,
            retained_false,
            true_pairs,
            recall_available=recall_available,
        ),
    }


def _edge_metrics(
    retained_true: int,
    retained_false: int,
    true_pair_count: int,
    *,
    recall_available: bool,
) -> dict[str, Any]:
    predicted_count = int(retained_true) + int(retained_false)
    precision = _ratio_metric(
        retained_true,
        predicted_count,
        "no_retained_labeled_cross_camera_edges",
    )
    false_rate = _ratio_metric(
        retained_false,
        predicted_count,
        "no_retained_labeled_cross_camera_edges",
    )
    if not recall_available:
        recall = _unavailable("candidate_recall_contract_unavailable")
    else:
        recall = _ratio_metric(
            retained_true,
            true_pair_count,
            "no_time_eligible_same_truth_cross_camera_pairs",
        )
    if precision["availability"] != "available" or recall["availability"] != "available":
        f1 = _unavailable("precision_or_recall_unavailable")
    else:
        denominator = float(precision["value"]) + float(recall["value"])
        f1 = _available(
            0.0
            if denominator == 0.0
            else 2.0
            * float(precision["value"])
            * float(recall["value"])
            / denominator
        )
    return {
        "geometry_false_edge_rate": false_rate,
        "geometry_candidate_precision": precision,
        "geometry_candidate_recall": recall,
        "geometry_candidate_f1": f1,
    }


def _seed_statistics(
    rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
    variant: str,
) -> dict[str, Any]:
    statistics: dict[str, Any] = {}
    for field in (*_COUNT_FIELDS, *_RATIO_FIELDS):
        values: list[float] = []
        unavailable = Counter()
        for row in rows:
            if field in _RATIO_FIELDS:
                metric = row[field]
                if metric["availability"] == "available":
                    values.append(float(metric["value"]))
                else:
                    unavailable[str(metric["reason"])] += 1
            elif field in _HARD_VIOLATION_FIELDS:
                values.append(float(row["hard_violations"].get(field, 0)))
            else:
                values.append(float(row[field]))
        statistics[field] = _statistics(
            values,
            unavailable=unavailable,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_rng_seed=bootstrap_rng_seed,
            identity=f"{variant}:{field}",
            total_seed_count=len(rows),
        )
    return statistics


def _statistics(
    values: Sequence[float],
    *,
    unavailable: Counter[str],
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
    identity: str,
    total_seed_count: int,
) -> dict[str, Any]:
    if not values:
        return {
            "availability": "unavailable",
            "reason": "no_available_seed_values",
            "available_seed_count": 0,
            "total_seed_count": total_seed_count,
            "unavailable_reason_distribution": dict(sorted(unavailable.items())),
            "mean": None,
            "standard_deviation": None,
            "bootstrap_ci95_low": None,
            "bootstrap_ci95_high": None,
            "bootstrap_availability": "unavailable",
            "bootstrap_unavailable_reason": "no_available_seed_values",
        }
    array = np.asarray(values, dtype=np.float64)
    if len(values) >= 20:
        offset = int.from_bytes(
            hashlib.sha256(identity.encode("utf-8")).digest()[:4],
            "big",
        )
        low, high = _bootstrap_mean_ci(
            array,
            resamples=bootstrap_resamples,
            rng_seed=(bootstrap_rng_seed + offset) % (2**32),
        )
        bootstrap_availability = "available"
        bootstrap_reason = None
    else:
        low = high = None
        bootstrap_availability = "unavailable"
        bootstrap_reason = "fewer_than_20_available_seeds_descriptive_only"
    return {
        "availability": "available",
        "reason": None,
        "available_seed_count": len(values),
        "total_seed_count": total_seed_count,
        "unavailable_reason_distribution": dict(sorted(unavailable.items())),
        "mean": float(np.mean(array)),
        "standard_deviation": float(np.std(array, ddof=0)),
        "standard_deviation_semantics": "descriptive_population_std",
        "bootstrap_ci95_low": low,
        "bootstrap_ci95_high": high,
        "bootstrap_availability": bootstrap_availability,
        "bootstrap_unavailable_reason": bootstrap_reason,
        "bootstrap_resamples": bootstrap_resamples,
        "bootstrap_rng_seed": bootstrap_rng_seed,
    }


def _load_frame_index_sidecar(
    path: Path | None,
    dataset: Any,
) -> tuple[dict[str, int], dict[str, Any]]:
    if path is None:
        return {}, {
            "status": "not_provided",
            "availability": "unavailable",
            "reason": "stable_frame_coordinate_sidecar_not_provided",
            "path": None,
            "sha256": None,
        }
    if not path.is_file():
        raise D5CrossviewCalibrationError(
            "frame_index_sidecar_missing",
            str(path),
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise D5CrossviewCalibrationError(
            "frame_index_sidecar_invalid_json",
            str(path),
        ) from exc
    expected_top = {
        "schema_version",
        "coordinate_semantics",
        "dataset_manifest_sha256",
        "records",
    }
    if not isinstance(payload, Mapping) or set(payload) != expected_top:
        raise D5CrossviewCalibrationError(
            "frame_index_sidecar_fields_mismatch",
            str(path),
        )
    if payload["schema_version"] != D5_CROSSVIEW_FRAME_INDEX_SCHEMA_VERSION:
        raise D5CrossviewCalibrationError(
            "frame_index_sidecar_schema_mismatch",
            str(path),
        )
    if (
        payload["coordinate_semantics"]
        != "scenario_version_seed_frame_index"
    ):
        raise D5CrossviewCalibrationError(
            "frame_index_coordinate_semantics_mismatch",
            str(path),
        )
    if payload["dataset_manifest_sha256"] != dataset.manifest_sha256:
        raise D5CrossviewCalibrationError(
            "frame_index_dataset_manifest_sha256_mismatch",
            str(path),
        )
    records = payload["records"]
    if not isinstance(records, list):
        raise D5CrossviewCalibrationError(
            "frame_index_records_invalid",
            str(path),
        )
    episodes = {
        episode.graph.episode_uid: episode
        for episode in dataset.episodes
    }
    by_uid: dict[str, int] = {}
    coordinates: set[tuple[str, int, int]] = set()
    expected_record_fields = {
        "episode_uid",
        "scenario_version",
        "seed",
        "frame_index",
    }
    for raw in records:
        if not isinstance(raw, Mapping) or set(raw) != expected_record_fields:
            raise D5CrossviewCalibrationError(
                "frame_index_record_fields_mismatch",
                str(path),
            )
        uid = str(raw["episode_uid"]).strip()
        episode = episodes.get(uid)
        if episode is None:
            raise D5CrossviewCalibrationError(
                "frame_index_unknown_episode_uid",
                uid,
            )
        if uid in by_uid:
            raise D5CrossviewCalibrationError(
                "frame_index_duplicate_episode_uid",
                uid,
            )
        if type(raw["seed"]) is not int or type(raw["frame_index"]) is not int:
            raise D5CrossviewCalibrationError(
                "frame_index_integer_type_invalid",
                uid,
            )
        try:
            seed = int(raw["seed"])
            frame_index = int(raw["frame_index"])
        except (TypeError, ValueError) as exc:
            raise D5CrossviewCalibrationError(
                "frame_index_integer_type_invalid",
                uid,
            ) from exc
        if frame_index < 0:
            raise D5CrossviewCalibrationError(
                "frame_index_integer_value_invalid",
                uid,
            )
        scenario = str(raw["scenario_version"])
        if (
            scenario != episode.graph.scenario_version
            or seed != int(episode.graph.seed)
        ):
            raise D5CrossviewCalibrationError(
                "frame_index_episode_identity_mismatch",
                uid,
            )
        coordinate = (scenario, seed, frame_index)
        if coordinate in coordinates:
            raise D5CrossviewCalibrationError(
                "frame_index_coordinate_duplicate",
                str(coordinate),
            )
        coordinates.add(coordinate)
        by_uid[uid] = frame_index
    if set(by_uid) != set(episodes):
        missing = sorted(set(episodes) - set(by_uid))
        raise D5CrossviewCalibrationError(
            "frame_index_episode_coverage_mismatch",
            f"missing={missing}",
        )
    return by_uid, {
        "status": "pass",
        "availability": "available",
        "reason": None,
        "path": str(path),
        "sha256": _sha256_file(path),
        "record_count": len(by_uid),
        "coordinate_semantics": "scenario_version_seed_frame_index",
        "dataset_manifest_sha256": dataset.manifest_sha256,
    }


def _compare_variants(
    variants: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    required = set(variants) == set(SUPPORTED_VARIANTS)
    if not required:
        return {
            "required": False,
            "scope": "candidate_graph_geometry_only",
            "availability": "unavailable",
            "reason": "both_R0_and_G1_not_supplied",
            "comparable": False,
            "paired_frame_count": None,
            "missing_R0_frame_count": None,
            "missing_G1_frame_count": None,
            "node_or_label_contract_mismatch_count": None,
            "metric_deltas_G1_minus_R0": {
                name: _unavailable("both_R0_and_G1_not_supplied")
                for name in _RATIO_FIELDS
            },
            "model_scoring_benefit": _unavailable(
                "edge_probabilities_threshold_and_clusters_absent"
            ),
        }
    r0 = variants["R0"]
    g1 = variants["G1"]
    if (
        r0["strict_loader"]["status"] != "pass"
        or g1["strict_loader"]["status"] != "pass"
    ):
        return {
            "required": True,
            "scope": "candidate_graph_geometry_only",
            "availability": "unavailable",
            "reason": "strict_loader_failed",
            "comparable": False,
            "paired_frame_count": None,
            "missing_R0_frame_count": None,
            "missing_G1_frame_count": None,
            "node_or_label_contract_mismatch_count": None,
            "metric_deltas_G1_minus_R0": {
                name: _unavailable("strict_loader_failed") for name in _RATIO_FIELDS
            },
            "model_scoring_benefit": _unavailable(
                "edge_probabilities_threshold_and_clusters_absent"
            ),
        }
    if (
        r0["frame_index_sidecar"]["status"] != "pass"
        or g1["frame_index_sidecar"]["status"] != "pass"
    ):
        return {
            "required": True,
            "scope": "candidate_graph_geometry_only",
            "availability": "unavailable",
            "reason": "stable_frame_coordinate_sidecar_missing_or_invalid",
            "comparable": False,
            "paired_frame_count": None,
            "missing_R0_frame_count": None,
            "missing_G1_frame_count": None,
            "node_or_label_contract_mismatch_count": None,
            "metric_deltas_G1_minus_R0": {
                name: _unavailable(
                    "stable_frame_coordinate_sidecar_missing_or_invalid"
                )
                for name in _RATIO_FIELDS
            },
            "model_scoring_benefit": _unavailable(
                "edge_probabilities_threshold_and_clusters_absent"
            ),
        }
    r0_frames = r0["_frame_contracts"]
    g1_frames = g1["_frame_contracts"]
    r0_keys = set(r0_frames)
    g1_keys = set(g1_frames)
    shared = sorted(r0_keys & g1_keys)
    mismatches = sum(r0_frames[key] != g1_frames[key] for key in shared)
    comparable = r0_keys == g1_keys and mismatches == 0
    deltas: dict[str, Any] = {}
    for name in _RATIO_FIELDS:
        left = r0["aggregate"][name]
        right = g1["aggregate"][name]
        if (
            comparable
            and left["availability"] == "available"
            and right["availability"] == "available"
        ):
            deltas[name] = _available(float(right["value"]) - float(left["value"]))
        else:
            deltas[name] = _unavailable(
                "paired_frame_or_metric_unavailable"
            )
    return {
        "required": True,
        "scope": "candidate_graph_geometry_only",
        "availability": "available" if comparable else "unavailable",
        "reason": None if comparable else "paired_frame_or_node_contract_mismatch",
        "comparable": comparable,
        "paired_frame_count": len(shared),
        "missing_R0_frame_count": len(g1_keys - r0_keys),
        "missing_G1_frame_count": len(r0_keys - g1_keys),
        "node_or_label_contract_mismatch_count": mismatches,
        "metric_deltas_G1_minus_R0": deltas,
        "model_scoring_benefit": _unavailable(
            "edge_probabilities_threshold_and_clusters_absent"
        ),
    }


def _preflight_dataset(root: Path) -> dict[str, Any]:
    hard = _zero_hard_violations()
    frame_hard: dict[str, dict[str, int]] = {}
    scenarios: set[str] = set()
    seeds: set[int] = set()
    frame_count = 0
    node_count = 0
    edge_count = 0
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return {
            "manifest_sha256": None,
            "frame_count": None,
            "node_count": None,
            "edge_count": None,
            "scenario_values": (),
            "seed_values": (),
            "hard_violations": hard,
            "frame_hard_violations": frame_hard,
        }
    manifest_sha = _sha256_file(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "manifest_sha256": manifest_sha,
            "frame_count": None,
            "node_count": None,
            "edge_count": None,
            "scenario_values": (),
            "seed_values": (),
            "hard_violations": hard,
            "frame_hard_violations": frame_hard,
        }
    descriptors = manifest.get("episodes")
    if not isinstance(descriptors, list):
        descriptors = []
    for descriptor in descriptors:
        if not isinstance(descriptor, Mapping):
            continue
        frame_count += 1
        uid = str(descriptor.get("episode_uid", f"raw-frame-{frame_count}"))
        frame_values = _zero_hard_violations()
        frame_hard[uid] = frame_values
        try:
            scenarios.add(str(descriptor["scenario_version"]))
            seeds.add(int(descriptor["seed"]))
        except (KeyError, TypeError, ValueError):
            pass
        graph_path = _safe_source_path(root, descriptor.get("graph_file"))
        labels_path = _safe_source_path(root, descriptor.get("labels_file"))
        if graph_path is None or not graph_path.is_file():
            continue
        try:
            with np.load(graph_path, allow_pickle=False) as archive:
                arrays = {
                    name: np.array(archive[name], copy=True)
                    for name in archive.files
                }
        except Exception:
            continue
        for name in _GRAPH_NUMERIC_ARRAY_NAMES:
            array = arrays.get(name)
            if array is None or not np.issubdtype(array.dtype, np.number):
                continue
            finite = np.isfinite(array)
            if not bool(np.all(finite)):
                frame_values["non_finite_array_count"] += 1
                frame_values["non_finite_value_count"] += int(np.size(finite) - np.sum(finite))
        tracklet_keys = tuple(
            str(value)
            for value in np.asarray(
                arrays.get("tracklet_keys", np.asarray((), dtype=np.str_))
            ).tolist()
        )
        camera_keys = tuple(
            str(value)
            for value in np.asarray(
                arrays.get("camera_keys", np.asarray((), dtype=np.str_))
            ).tolist()
        )
        node_count += len(tracklet_keys)
        frame_values["duplicate_tracklet_key_count"] += len(tracklet_keys) - len(
            set(tracklet_keys)
        )
        edge_index = np.asarray(
            arrays.get("edge_index", np.empty((2, 0), dtype=np.int64))
        )
        if edge_index.ndim == 2 and edge_index.shape[0] == 2:
            edge_count += int(edge_index.shape[1])
            seen: set[tuple[int, int]] = set()
            for raw_left, raw_right in edge_index.T:
                try:
                    left = int(raw_left)
                    right = int(raw_right)
                except (TypeError, ValueError, OverflowError):
                    frame_values["invalid_edge_endpoint_count"] += 1
                    continue
                if left == right:
                    frame_values["self_loop_count"] += 1
                if not 0 <= left < len(tracklet_keys) or not 0 <= right < len(tracklet_keys):
                    frame_values["invalid_edge_endpoint_count"] += 1
                    continue
                pair = (min(left, right), max(left, right))
                if pair in seen:
                    frame_values["duplicate_undirected_edge_count"] += 1
                seen.add(pair)
                if (
                    left < len(camera_keys)
                    and right < len(camera_keys)
                    and camera_keys[left] == camera_keys[right]
                ):
                    frame_values["same_camera_edge_count"] += 1
        if labels_path is not None and labels_path.is_file():
            try:
                label_payload = json.loads(labels_path.read_text(encoding="utf-8"))
                raw_labels = label_payload.get("labels", ())
                label_keys = [
                    str(value.get("tracklet_key"))
                    for value in raw_labels
                    if isinstance(value, Mapping)
                ]
                frame_values["duplicate_label_key_count"] += len(label_keys) - len(
                    set(label_keys)
                )
                frame_values["missing_label_node_count"] += len(
                    set(tracklet_keys) - set(label_keys)
                )
            except (OSError, json.JSONDecodeError, AttributeError):
                frame_values["missing_label_node_count"] += len(set(tracklet_keys))
        else:
            frame_values["missing_label_node_count"] += len(set(tracklet_keys))
    for values in frame_hard.values():
        for field in _HARD_VIOLATION_FIELDS:
            hard[field] += int(values.get(field, 0))
    hard["total"] = sum(int(hard[field]) for field in _HARD_VIOLATION_FIELDS)
    return {
        "manifest_sha256": manifest_sha,
        "frame_count": frame_count,
        "node_count": node_count,
        "edge_count": edge_count,
        "scenario_values": tuple(sorted(scenarios)),
        "seed_values": tuple(sorted(seeds)),
        "hard_violations": hard,
        "frame_hard_violations": frame_hard,
    }


def _load_d5_dataset_api() -> Any:
    try:
        return importlib.import_module("d5_terminal_association.tracklet_dataset")
    except ModuleNotFoundError as first_error:
        research_root = Path(__file__).resolve().parents[2]
        d5_src = research_root / "d5_terminal_association" / "src"
        if not d5_src.is_dir():
            raise D5CrossviewCalibrationError(
                "d5_dataset_loader_unavailable",
                str(first_error),
            ) from first_error
        source = str(d5_src)
        if source not in sys.path:
            sys.path.insert(0, source)
        try:
            return importlib.import_module("d5_terminal_association.tracklet_dataset")
        except ModuleNotFoundError as exc:
            raise D5CrossviewCalibrationError(
                "d5_dataset_loader_unavailable",
                str(exc),
            ) from exc


def _sum_available_variant_count(
    variants: Mapping[str, Mapping[str, Any]],
    field: str,
) -> dict[str, Any]:
    values: list[int] = []
    for result in variants.values():
        metric = result["counts"][field]
        if metric["availability"] != "available":
            return _unavailable(f"{field}_unavailable_for_one_or_more_datasets")
        values.append(int(metric["value"]))
    return _available(sum(values))


def _input_contract_failed(variants: Mapping[str, Mapping[str, Any]]) -> bool:
    return any(
        result["strict_loader"]["status"] != "pass"
        or result["frame_index_sidecar"]["status"] == "fail_closed"
        for result in variants.values()
    )


def _time_eligible(
    graph: Any,
    left: int,
    right: int,
    *,
    measurement_window_s: float,
    arrival_window_s: float,
) -> bool:
    return (
        abs(
            float(graph.measurement_timestamps[left])
            - float(graph.measurement_timestamps[right])
        )
        <= measurement_window_s + 1.0e-12
        and abs(
            float(graph.arrival_timestamps[left])
            - float(graph.arrival_timestamps[right])
        )
        <= arrival_window_s + 1.0e-12
    )


def _zero_hard_violations() -> dict[str, int]:
    return {field: 0 for field in _HARD_VIOLATION_FIELDS}


def _sum_hard_violations(
    values: Iterable[Mapping[str, int]],
) -> dict[str, int]:
    result = _zero_hard_violations()
    for item in values:
        for field in _HARD_VIOLATION_FIELDS:
            result[field] += int(item.get(field, 0))
    result["total"] = sum(result.values())
    return result


def _empty_aggregate(reason: str) -> dict[str, Any]:
    return {
        "frame_count": 0,
        "time_eligible_true_pair_count": 0,
        "geometry_retained_true_edge_count": 0,
        "geometry_retained_false_edge_count": 0,
        **{name: _unavailable(reason) for name in _RATIO_FIELDS},
    }


def _ratio_metric(
    numerator: int | float,
    denominator: int | float,
    unavailable_reason: str,
) -> dict[str, Any]:
    if float(denominator) <= 0.0:
        return _unavailable(unavailable_reason)
    return _available(float(numerator) / float(denominator))


def _available(value: Any) -> dict[str, Any]:
    return {"availability": "available", "value": value, "reason": None}


def _unavailable(reason: str) -> dict[str, Any]:
    return {"availability": "unavailable", "value": None, "reason": str(reason)}


def _availability_from_optional(value: Any) -> dict[str, Any]:
    return _available(value) if value is not None else _unavailable("preflight_count_unavailable")


def _bootstrap_mean_ci(
    values: np.ndarray,
    *,
    resamples: int,
    rng_seed: int,
) -> tuple[float, float]:
    rng = np.random.default_rng(int(rng_seed))
    indices = rng.integers(0, len(values), size=(int(resamples), len(values)))
    means = np.mean(values[indices], axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _with_content_sha256(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("content_sha256", None)
    result["content_sha256"] = hashlib.sha256(
        _canonical_json_bytes(result)
    ).hexdigest()
    return result


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _drop_private_keys(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if not str(key).startswith("_")
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_seed_csv(path: Path, result: Mapping[str, Any]) -> None:
    base_fields = (
        "variant",
        "seed",
        "scenario_versions",
        "frame_count",
        "node_count",
        "edge_count",
        "labels_complete_frame_count",
        "candidate_recall_available_frame_count",
        "time_eligible_true_pair_count",
        "geometry_retained_true_edge_count",
        "geometry_retained_false_edge_count",
    )
    ratio_fields = tuple(
        f"{name}_{suffix}"
        for name in _RATIO_FIELDS
        for suffix in ("value", "availability", "reason")
    )
    hard_fields = tuple(f"hard_{name}" for name in (*_HARD_VIOLATION_FIELDS, "total"))
    fieldnames = (*base_fields, *ratio_fields, *hard_fields)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for variant, payload in sorted(result["variants"].items()):
            for raw in payload["per_seed"]:
                row = {
                    "variant": variant,
                    **{
                        name: (
                            ";".join(raw[name])
                            if name == "scenario_versions"
                            else raw[name]
                        )
                        for name in base_fields
                        if name != "variant"
                    },
                }
                for name in _RATIO_FIELDS:
                    metric = raw[name]
                    row[f"{name}_value"] = metric["value"]
                    row[f"{name}_availability"] = metric["availability"]
                    row[f"{name}_reason"] = metric["reason"]
                for name in (*_HARD_VIOLATION_FIELDS, "total"):
                    row[f"hard_{name}"] = raw["hard_violations"].get(name, 0)
                writer.writerow(row)


def _metric_text(metric: Mapping[str, Any]) -> str:
    if metric.get("availability") != "available":
        return f"不可用（{metric.get('reason')}）"
    value = metric.get("value")
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_source_path(root: Path, raw: Any) -> Path | None:
    if not isinstance(raw, str) or not raw:
        return None
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _paths_overlap(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left in right.parents or right in left.parents
