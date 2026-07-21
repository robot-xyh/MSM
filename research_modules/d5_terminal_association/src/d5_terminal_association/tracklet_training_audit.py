"""Fail-closed readiness audit for versioned D5 tracklet graph datasets."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import gc
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .canonical_seed_view import canonical_view_binding, load_tracklet_canonical_seed_view
from .tracklet_dataset import (
    LoadedTrackletDataset,
    LoadedTrackletEpisode,
    load_tracklet_dataset,
    sha256_file,
)
from .tracklet_training import TrackletTrainingConfig, run_training_pipeline


READINESS_AUDIT_SCHEMA_VERSION = "d5.tracklet-training-readiness-audit.v1"
PROMOTION_ASSESSMENT_SCHEMA_VERSION = "d5.tracklet-promotion-assessment.v1"
_SCENARIO_SCALE_PATTERN = re.compile(
    r"^(?P<scenario>.+)-(?P<resources>\d+)v(?P<targets>\d+)-v(?P<version>\d+)$"
)


@dataclass(frozen=True)
class TrackletReadinessCriteria:
    """Frozen minimum evidence for training and promotion review."""

    maximum_edge_free_ratio: float = 0.90
    minimum_train_positive_edges: int = 100
    minimum_train_negative_edges: int = 100
    minimum_validation_positive_edges: int = 50
    minimum_validation_negative_edges: int = 30
    minimum_test_positive_edges: int = 50
    minimum_test_negative_edges: int = 30
    minimum_candidate_recall_pairs_per_split: int = 100
    minimum_candidate_recall_availability_ratio: float = 1.0
    minimum_scenario_scale_both_class_fraction: float = 0.80
    minimum_test_seed_count: int = 20
    reserved_evaluation_seed_start: int = 1000
    reserved_evaluation_seed_stop: int = 1020
    minimum_test_precision: float = 0.95
    minimum_test_recall: float = 0.90
    minimum_test_f1: float = 0.92
    maximum_test_false_merge_rate: float = 0.01
    minimum_test_candidate_recall: float = 0.95
    maximum_test_ece: float = 0.05
    maximum_p95_inference_latency_ms: float = 100.0

    @property
    def reserved_evaluation_seeds(self) -> tuple[int, ...]:
        return tuple(
            range(self.reserved_evaluation_seed_start, self.reserved_evaluation_seed_stop)
        )


def audit_tracklet_training_readiness(
    dataset: LoadedTrackletDataset,
    *,
    criteria: TrackletReadinessCriteria | None = None,
) -> dict[str, Any]:
    """Summarize evidence and apply immutable, fail-closed readiness gates."""

    rule = criteria or TrackletReadinessCriteria()
    splits = {name: dataset.split(name) for name in ("train", "validation", "test")}
    seeds_by_split = {
        name: sorted({episode.graph.seed for episode in episodes})
        for name, episodes in splits.items()
    }
    split_intersections = {
        "train_validation": sorted(set(seeds_by_split["train"]) & set(seeds_by_split["validation"])),
        "train_test": sorted(set(seeds_by_split["train"]) & set(seeds_by_split["test"])),
        "validation_test": sorted(
            set(seeds_by_split["validation"]) & set(seeds_by_split["test"])
        ),
    }
    split_atomic = not any(split_intersections.values())
    reserved = set(rule.reserved_evaluation_seeds)
    reserved_overlap = {
        name: sorted(set(seeds) & reserved) for name, seeds in seeds_by_split.items()
    }

    split_summaries = {
        name: _summarize_split(episodes) for name, episodes in splits.items()
    }
    all_episodes = dataset.episodes
    total_edge_free = sum(episode.graph.edge_count == 0 for episode in all_episodes)
    edge_summary = {
        "episode_count": len(all_episodes),
        "edge_free_episode_count": total_edge_free,
        "edge_bearing_episode_count": len(all_episodes) - total_edge_free,
        "edge_free_ratio": total_edge_free / len(all_episodes),
        "candidate_edge_count": sum(episode.graph.edge_count for episode in all_episodes),
        "by_split": {
            name: {
                "episode_count": summary["episode_count"],
                "edge_free_episode_count": summary["edge_free_episode_count"],
                "edge_bearing_episode_count": summary["edge_bearing_episode_count"],
                "edge_free_ratio": summary["edge_free_ratio"],
                "candidate_edge_count": summary["class_balance"]["candidate_edges"],
            }
            for name, summary in split_summaries.items()
        },
    }

    cell_summaries = _scenario_scale_summaries(all_episodes)
    cells_by_split = {
        split: [cell for cell in cell_summaries if cell["split"] == split]
        for split in ("train", "validation", "test")
    }
    both_class_fraction = {
        split: (
            sum(
                cell["positive_candidate_edges"] > 0
                and cell["negative_candidate_edges"] > 0
                for cell in cells
            )
            / len(cells)
            if cells
            else 0.0
        )
        for split, cells in cells_by_split.items()
    }

    gates: list[dict[str, Any]] = []
    _gate(gates, "dataset_integrity", True, "strict_loader_passed", "strict_loader_passed")
    _gate(gates, "whole_seed_split_atomicity", split_atomic, split_intersections, "no_seed_overlap")
    _gate(
        gates,
        "reserved_evaluation_seeds_excluded_from_training",
        not reserved_overlap["train"],
        reserved_overlap["train"],
        [],
    )
    _gate(
        gates,
        "minimum_test_seed_count",
        len(seeds_by_split["test"]) >= rule.minimum_test_seed_count,
        len(seeds_by_split["test"]),
        f">={rule.minimum_test_seed_count}",
    )
    for split, summary in split_summaries.items():
        _gate(
            gates,
            f"{split}_edge_free_ratio",
            summary["edge_free_ratio"] <= rule.maximum_edge_free_ratio,
            summary["edge_free_ratio"],
            f"<={rule.maximum_edge_free_ratio}",
        )
        positive_minimum = getattr(rule, f"minimum_{split}_positive_edges")
        negative_minimum = getattr(rule, f"minimum_{split}_negative_edges")
        balance = summary["class_balance"]
        _gate(
            gates,
            f"{split}_positive_edge_support",
            balance["positive_candidate_edges"] >= positive_minimum,
            balance["positive_candidate_edges"],
            f">={positive_minimum}",
        )
        _gate(
            gates,
            f"{split}_negative_edge_support",
            balance["negative_candidate_edges"] >= negative_minimum,
            balance["negative_candidate_edges"],
            f">={negative_minimum}",
        )
        recall = summary["candidate_recall"]
        _gate(
            gates,
            f"{split}_candidate_recall_availability",
            recall["availability_ratio"]
            >= rule.minimum_candidate_recall_availability_ratio,
            recall["availability_ratio"],
            f">={rule.minimum_candidate_recall_availability_ratio}",
        )
        _gate(
            gates,
            f"{split}_candidate_recall_pair_support",
            recall["partial_denominator"]
            >= rule.minimum_candidate_recall_pairs_per_split,
            recall["partial_denominator"],
            f">={rule.minimum_candidate_recall_pairs_per_split}",
        )
        _gate(
            gates,
            f"{split}_scenario_scale_both_class_coverage",
            both_class_fraction[split]
            >= rule.minimum_scenario_scale_both_class_fraction,
            both_class_fraction[split],
            f">={rule.minimum_scenario_scale_both_class_fraction}",
        )

    failed_gates = [gate["name"] for gate in gates if not gate["passed"]]
    development_failures = _development_training_failures(split_summaries, split_atomic)
    development_allowed = not development_failures
    producer_summary = _producer_summary(all_episodes)
    canonical_view = canonical_view_binding(dataset)
    return {
        "schema_version": READINESS_AUDIT_SCHEMA_VERSION,
        "dataset": {
            "name": dataset.root.name,
            "manifest_sha256": dataset.manifest_sha256,
            "split_sha256": dataset.manifest["split_sha256"],
            "training_set_sha256": dataset.manifest["training_set_sha256"],
            "config_sha256": dataset.manifest["config_sha256"],
            "dataset_schema_version": dataset.manifest["schema_version"],
            "graph_schema_version": dataset.manifest["graph_schema_version"],
            "label_schema_version": dataset.manifest["evaluator_label_schema_version"],
            "node_feature_version": dataset.manifest["node_feature_version"],
            "edge_feature_version": dataset.manifest["edge_feature_version"],
            "validated_graph_sha256_count": len(all_episodes),
            "validated_label_sha256_count": len(all_episodes),
            "canonical_seed_view": canonical_view,
        },
        "criteria": {
            **asdict(rule),
            "reserved_evaluation_seeds": list(rule.reserved_evaluation_seeds),
        },
        "split_integrity": {
            "seeds_by_split": seeds_by_split,
            "seed_count_by_split": {
                name: len(seeds) for name, seeds in seeds_by_split.items()
            },
            "split_intersections": split_intersections,
            "whole_seed_atomic": split_atomic,
            "reserved_evaluation_seed_overlap": reserved_overlap,
            "reserved_evaluation_seeds_present_in_corpus": sorted(
                set().union(*(set(seeds) for seeds in seeds_by_split.values())) & reserved
            ),
        },
        "edge_coverage": edge_summary,
        "split_summaries": split_summaries,
        "scenario_scale_coverage": cell_summaries,
        "scenario_scale_both_class_fraction": both_class_fraction,
        "hard_negative_evidence": producer_summary["hard_negative_evidence"],
        "producer_diagnostics": producer_summary["producer_diagnostics"],
        "training_readiness": {
            "status": "pass" if not failed_gates else "fail_closed",
            "passed": not failed_gates,
            "failed_gates": failed_gates,
            "gates": gates,
        },
        "development_training": {
            "status": "allowed_not_admissible" if development_allowed else "fail_closed",
            "allowed": development_allowed,
            "failure_reasons": development_failures,
            "scope": "labeled_candidate_edges_only",
            "g1_assist_eligible": False,
        },
        "promotion_readiness": {
            "status": "fail_closed" if failed_gates else "awaiting_model_evidence",
            "passed": False,
            "g1_assist_eligible": False,
            "failure_reasons": (
                [f"data_gate:{name}" for name in failed_gates]
                if failed_gates
                else ["independent_model_test_evidence_not_evaluated"]
            ),
            "model_thresholds": {
                "minimum_test_precision": rule.minimum_test_precision,
                "minimum_test_recall": rule.minimum_test_recall,
                "minimum_test_f1": rule.minimum_test_f1,
                "maximum_test_false_merge_rate": rule.maximum_test_false_merge_rate,
                "minimum_test_candidate_recall": rule.minimum_test_candidate_recall,
                "maximum_test_ece": rule.maximum_test_ece,
                "maximum_p95_inference_latency_ms": rule.maximum_p95_inference_latency_ms,
            },
        },
        "producer_gaps": _producer_gap_recommendations(edge_summary, split_summaries),
        "identity_safety": {
            "model_output": "same_target_probability_on_existing_candidate_edges_only",
            "global_track_id_rewrite_allowed": False,
            "same_camera_mutual_exclusion_preserved": True,
            "geometry_gate_preserved": True,
            "deterministic_rule_fallback_preserved": True,
        },
    }


def run_tracklet_training_audit(
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    criteria: TrackletReadinessCriteria | None = None,
    canonical_view_manifest_path: str | Path | None = None,
    training_seed_registry_path: str | Path | None = None,
    shared_seed_registry_path: str | Path | None = None,
) -> tuple[dict[str, Any], Path, Path, str]:
    dataset = _load_audit_dataset(
        dataset_dir,
        canonical_view_manifest_path=canonical_view_manifest_path,
        training_seed_registry_path=training_seed_registry_path,
        shared_seed_registry_path=shared_seed_registry_path,
    )
    report = audit_tracklet_training_readiness(dataset, criteria=criteria)
    root = Path(output_dir)
    json_path = root / "training_readiness_audit.json"
    markdown_path = root / "TRAINING_READINESS_AUDIT_CN.md"
    _write_json_atomic(json_path, report)
    _write_markdown_atomic(markdown_path, _audit_markdown(report))
    return report, json_path, markdown_path, sha256_file(json_path)


def assess_tracklet_model_promotion(
    readiness_report: Mapping[str, Any],
    training_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply promotion thresholds without granting admission to the bundle."""

    thresholds = readiness_report["promotion_readiness"]["model_thresholds"]
    failures = list(readiness_report["promotion_readiness"]["failure_reasons"])
    test_metrics = training_report["test"]["metrics"]
    checks = (
        ("precision", "minimum_test_precision", ">="),
        ("recall", "minimum_test_recall", ">="),
        ("f1", "minimum_test_f1", ">="),
        ("false_merge_rate", "maximum_test_false_merge_rate", "<="),
        ("candidate_recall", "minimum_test_candidate_recall", ">="),
        ("ece", "maximum_test_ece", "<="),
        ("p95_inference_latency_ms", "maximum_p95_inference_latency_ms", "<="),
    )
    model_gates: list[dict[str, Any]] = []
    for metric_name, threshold_name, operator in checks:
        metric = test_metrics[metric_name]
        threshold = float(thresholds[threshold_name])
        available = bool(metric.get("available"))
        value = metric.get("value")
        passed = available and (
            float(value) >= threshold if operator == ">=" else float(value) <= threshold
        )
        if not passed:
            reason = metric.get("reason", "threshold_not_met") if not available else "threshold_not_met"
            failures.append(f"model_gate:{metric_name}:{reason}")
        model_gates.append(
            {
                "metric": metric_name,
                "available": available,
                "value": value,
                "operator": operator,
                "threshold": threshold,
                "passed": passed,
            }
        )
    return {
        "schema_version": PROMOTION_ASSESSMENT_SCHEMA_VERSION,
        "status": "fail_closed" if failures else "candidate_for_external_review",
        "passed": not failures,
        "g1_assist_eligible": False,
        "failure_reasons": failures,
        "model_gates": model_gates,
        "dataset_manifest_sha256": readiness_report["dataset"]["manifest_sha256"],
        "readiness_audit_sha256": training_report["readiness_audit_sha256"],
        "bundle_manifest_sha256": training_report["bundle"]["manifest_sha256"],
        "bundle_weights_sha256": training_report["bundle"]["weights_sha256"],
        "statistical_limit": (
            "test metrics cannot override failed data-support, edge-free, class-balance, "
            "or candidate-recall gates"
        ),
    }


def _summarize_split(episodes: Sequence[LoadedTrackletEpisode]) -> dict[str, Any]:
    balance = {
        name: sum(episode.class_balance[name] for episode in episodes)
        for name in (
            "candidate_edges",
            "positive_candidate_edges",
            "negative_candidate_edges",
            "unlabeled_candidate_edges",
        )
    }
    edge_free = sum(episode.graph.edge_count == 0 for episode in episodes)
    recall_numerator, recall_denominator = _partial_candidate_recall(episodes)
    recall_available = sum(
        episode.evaluator_labels.candidate_recall_available for episode in episodes
    )
    negative_count = balance["negative_candidate_edges"]
    positive_count = balance["positive_candidate_edges"]
    return {
        "episode_count": len(episodes),
        "node_count": sum(episode.graph.node_count for episode in episodes),
        "edge_free_episode_count": edge_free,
        "edge_bearing_episode_count": len(episodes) - edge_free,
        "edge_free_ratio": edge_free / len(episodes),
        "class_balance": balance,
        "positive_to_negative_ratio": (
            positive_count / negative_count if negative_count else None
        ),
        "negative_edge_episode_count": sum(
            episode.class_balance["negative_candidate_edges"] > 0 for episode in episodes
        ),
        "candidate_recall": {
            "available_episode_count": recall_available,
            "episode_count": len(episodes),
            "availability_ratio": recall_available / len(episodes),
            "partial_numerator": recall_numerator,
            "partial_denominator": recall_denominator,
            "partial_value": (
                recall_numerator / recall_denominator if recall_denominator else None
            ),
            "formal_value_available": recall_available == len(episodes)
            and recall_denominator > 0,
            "partial_value_is_admission_evidence": False,
        },
    }


def _partial_candidate_recall(
    episodes: Sequence[LoadedTrackletEpisode],
) -> tuple[int, int]:
    numerator = 0
    denominator = 0
    for episode in episodes:
        if not episode.evaluator_labels.candidate_recall_available:
            continue
        labels = episode.evaluator_labels.by_tracklet_key
        groups: dict[str, Counter[str]] = defaultdict(Counter)
        for tracklet_key, camera_key in zip(
            episode.graph.tracklet_keys,
            episode.graph.camera_keys,
            strict=True,
        ):
            groups[labels[tracklet_key].truth_entity_id][camera_key] += 1
        for camera_counts in groups.values():
            total = sum(camera_counts.values())
            denominator += total * (total - 1) // 2
            denominator -= sum(
                count * (count - 1) // 2 for count in camera_counts.values()
            )
        for source, target in episode.graph.edge_index.T:
            source_key = episode.graph.tracklet_keys[int(source)]
            target_key = episode.graph.tracklet_keys[int(target)]
            numerator += int(
                labels[source_key].truth_entity_id == labels[target_key].truth_entity_id
            )
    return numerator, denominator


def _scenario_scale_summaries(
    episodes: Sequence[LoadedTrackletEpisode],
) -> list[dict[str, Any]]:
    cells: dict[tuple[str, str, int, int, int], Counter[str]] = defaultdict(Counter)
    for episode in episodes:
        match = _SCENARIO_SCALE_PATTERN.fullmatch(episode.graph.scenario_version)
        if match is None:
            raise ValueError(
                f"scenario_version does not expose scenario/scale: {episode.graph.scenario_version}"
            )
        key = (
            episode.split,
            match.group("scenario"),
            int(match.group("resources")),
            int(match.group("targets")),
            int(match.group("version")),
        )
        cell = cells[key]
        cell["episode_count"] += 1
        cell["edge_bearing_episode_count"] += int(episode.graph.edge_count > 0)
        cell["candidate_edges"] += episode.class_balance["candidate_edges"]
        cell["positive_candidate_edges"] += episode.class_balance[
            "positive_candidate_edges"
        ]
        cell["negative_candidate_edges"] += episode.class_balance[
            "negative_candidate_edges"
        ]
        cell["unlabeled_candidate_edges"] += episode.class_balance[
            "unlabeled_candidate_edges"
        ]
        cell["candidate_recall_available_episode_count"] += int(
            episode.evaluator_labels.candidate_recall_available
        )
    return [
        {
            "split": key[0],
            "scenario": key[1],
            "resource_count": key[2],
            "target_count": key[3],
            "scenario_version": key[4],
            **dict(cells[key]),
        }
        for key in sorted(cells)
    ]


def _producer_summary(episodes: Sequence[LoadedTrackletEpisode]) -> dict[str, Any]:
    negative_sources: Counter[str] = Counter()
    negative_cells: Counter[str] = Counter()
    candidate_counts: Counter[str] = Counter()
    for episode in episodes:
        candidate_counts.update(episode.graph.candidate_counts)
        negative_edges = episode.class_balance["negative_candidate_edges"]
        if not negative_edges:
            continue
        source = str(episode.hard_negative_provenance.get("source", "unknown"))
        negative_sources[source] += negative_edges
        match = _SCENARIO_SCALE_PATTERN.fullmatch(episode.graph.scenario_version)
        cell = (
            f"{match.group('scenario')}:{match.group('resources')}v{match.group('targets')}"
            if match is not None
            else episode.graph.scenario_version
        )
        negative_cells[cell] += negative_edges
    selected_keys = (
        "possible_cross_camera_pairs",
        "selected_camera_tracklet_pair_space",
        "candidate_tracklet_edges",
        "pre_cap_edges",
        "retained_edges",
        "camera_overlap_rejected_pairs",
        "rejected_epipolar",
        "rejected_global_projection",
        "rejected_reprojection_gate",
    )
    return {
        "hard_negative_evidence": {
            "negative_edges_by_source": dict(sorted(negative_sources.items())),
            "negative_edges_by_scenario_scale": dict(sorted(negative_cells.items())),
            "selection_semantics": "lowest online geometry gate score among labeled negative candidate edges",
            "synthetic_sample_duplication_used": False,
        },
        "producer_diagnostics": {
            key: int(candidate_counts[key]) for key in selected_keys
        },
    }


def _development_training_failures(
    split_summaries: Mapping[str, Mapping[str, Any]],
    split_atomic: bool,
) -> list[str]:
    failures: list[str] = []
    if not split_atomic:
        failures.append("seed_split_not_atomic")
    for split in ("train", "validation", "test"):
        balance = split_summaries[split]["class_balance"]
        if balance["positive_candidate_edges"] <= 0:
            failures.append(f"{split}_has_no_positive_labeled_edges")
        if balance["negative_candidate_edges"] <= 0:
            failures.append(f"{split}_has_no_negative_labeled_edges")
    return failures


def _producer_gap_recommendations(
    edge_summary: Mapping[str, Any],
    split_summaries: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "code": "edge_bearing_frames_too_sparse",
            "evidence": (
                f"{edge_summary['edge_bearing_episode_count']}/"
                f"{edge_summary['episode_count']} frames contain candidate edges"
            ),
            "required_producer_change": (
                "increase physically valid multi-camera overlap windows and retain more frames around "
                "dense crossing, occlusion entry/exit, and delayed reacquisition"
            ),
        },
        {
            "code": "hard_negative_support_too_small",
            "evidence": ", ".join(
                f"{split}={summary['class_balance']['negative_candidate_edges']}"
                for split, summary in split_summaries.items()
            ),
            "required_producer_change": (
                "generate distinct targets with similar epipolar geometry, projected covariance overlap, "
                "bbox scale, and angular rate; keep online geometry and identity gates unchanged"
            ),
        },
        {
            "code": "candidate_recall_not_evaluable",
            "evidence": ", ".join(
                f"{split}={summary['candidate_recall']['available_episode_count']}/"
                f"{summary['candidate_recall']['episode_count']} frames, denominator="
                f"{summary['candidate_recall']['partial_denominator']}"
                for split, summary in split_summaries.items()
            ),
            "required_producer_change": (
                "provide complete offline labels for all camera-local tracklets in evaluation frames and "
                "record all same-target cross-camera pairs before candidate pruning"
            ),
        },
        {
            "code": "no_sample_replication_fix",
            "evidence": "class support must come from new independent scene/seed observations",
            "required_producer_change": (
                "do not duplicate edges or frames; add camera baselines, clutter, crossing trajectories, "
                "partial visibility, time jitter, and bounded extrinsic perturbations"
            ),
        },
    ]


def _gate(
    gates: list[dict[str, Any]],
    name: str,
    passed: bool,
    observed: Any,
    required: Any,
) -> None:
    gates.append(
        {
            "name": name,
            "passed": bool(passed),
            "observed": observed,
            "required": required,
        }
    )


def _audit_markdown(report: Mapping[str, Any]) -> str:
    edge = report["edge_coverage"]
    lines = [
        "# D5 跨视角图数据训练前审计",
        "",
        "## 结论",
        "",
        f"正式数据合同与逐文件哈希校验通过。训练准入状态为 `{report['training_readiness']['status']}`，",
        f"晋级状态为 `{report['promotion_readiness']['status']}`。",
        "当前仅允许生成隔离的开发模型，模型不得进入 G1 或 assist，也不得替换几何规则主线。",
        "",
        "## 数据完整性",
        "",
        f"- 数据 schema：`{report['dataset']['dataset_schema_version']}`",
        f"- manifest SHA256：`{report['dataset']['manifest_sha256']}`",
        f"- split SHA256：`{report['dataset']['split_sha256']}`",
        f"- training-set SHA256：`{report['dataset']['training_set_sha256']}`",
        f"- 图/标签哈希校验：`{report['dataset']['validated_graph_sha256_count']}` / "
        f"`{report['dataset']['validated_label_sha256_count']}`",
        "",
        "## 候选边覆盖",
        "",
        f"全体 `{edge['episode_count']}` 帧中，`{edge['edge_free_episode_count']}` 帧没有候选边，"
        f"edge-free 比例为 `{edge['edge_free_ratio']:.4%}`。仅 "
        f"`{edge['edge_bearing_episode_count']}` 帧含候选边，共 `{edge['candidate_edge_count']}` 条。",
        "",
        "| 分割 | 帧数 | 无边帧 | 无边比例 | 正边 | 负边 | 未标注边 | recall 可评价帧 | partial recall |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split in ("train", "validation", "test"):
        summary = report["split_summaries"][split]
        balance = summary["class_balance"]
        recall = summary["candidate_recall"]
        partial = (
            f"{recall['partial_value']:.4f} ({recall['partial_numerator']}/"
            f"{recall['partial_denominator']})"
            if recall["partial_value"] is not None
            else "不可计算"
        )
        lines.append(
            f"| {split} | {summary['episode_count']} | {summary['edge_free_episode_count']} | "
            f"{summary['edge_free_ratio']:.2%} | {balance['positive_candidate_edges']} | "
            f"{balance['negative_candidate_edges']} | {balance['unlabeled_candidate_edges']} | "
            f"{recall['available_episode_count']} | {partial} |"
        )
    lines.extend(
        [
            "",
            "partial candidate recall 只覆盖具备完整离线标签的少量帧，不能作为候选召回率准入证据。",
            "",
            "## 失败门",
            "",
        ]
    )
    for gate in report["training_readiness"]["gates"]:
        if not gate["passed"]:
            lines.append(
                f"- `{gate['name']}`：观测 `{gate['observed']}`，要求 `{gate['required']}`。"
            )
    lines.extend(["", "## Producer 补数", ""])
    for item in report["producer_gaps"]:
        lines.append(
            f"- `{item['code']}`：{item['evidence']}。{item['required_producer_change']}。"
        )
    lines.extend(
        [
            "",
            "## 安全边界",
            "",
            "图网络只输出既有候选边的同目标概率。后续仍执行同相机互斥、几何门控、中心航迹绑定和规则回退。",
            "D5 不创建、改写或本地换绑 `global_track_id`。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_markdown_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _training_markdown(
    readiness: Mapping[str, Any],
    training: Mapping[str, Any],
    promotion: Mapping[str, Any],
) -> str:
    lines = [
        "# D5 跨视角图网络开发训练报告",
        "",
        "## 结论",
        "",
        "本次固定 seed 训练只验证原生 PyTorch 图网络、校准、制品和严格回载流程。",
        f"模型状态为 `{training['admission_status']}`，晋级评估为 `{promotion['status']}`。",
        "模型不得进入 G1/assist，不替换几何门控、同相机互斥、中心绑定和规则回退。",
        "",
        "## 数据限制",
        "",
        f"`{readiness['edge_coverage']['edge_free_episode_count']}/"
        f"{readiness['edge_coverage']['episode_count']}` 帧没有候选边，edge-free 比例为 "
        f"`{readiness['edge_coverage']['edge_free_ratio']:.4%}`。",
        "训练/验证/测试负边仅为 "
        f"`{readiness['split_summaries']['train']['class_balance']['negative_candidate_edges']}/"
        f"{readiness['split_summaries']['validation']['class_balance']['negative_candidate_edges']}/"
        f"{readiness['split_summaries']['test']['class_balance']['negative_candidate_edges']}`。",
        "candidate recall 只在少量完整标注帧上可局部计算，不能形成正式候选召回证据。",
        "",
        "## 训练配置",
        "",
        f"- 固定 seed：`{training['training']['config']['seed']}`",
        f"- epoch：`{training['training']['config']['epochs']}`",
        f"- 最佳 epoch：`{training['training']['best_epoch']}`",
        f"- 训练设备：`{training['hardware']['selected_device']}`",
        f"- 训练耗时：`{training['training']['training_elapsed_seconds']:.3f} s`",
        f"- 全管线耗时：`{training['pipeline_elapsed_seconds']:.3f} s`",
        f"- 入选正/负边：`{training['training']['selected_positive_edges']}/"
        f"{training['training']['selected_negative_edges']}`",
        "",
        "## 损失与指标",
        "",
        "| 分割 | 最终损失 | 精确率 | 召回率 | F1 | 误合并率 | candidate recall | ECE | P95 推理时延 |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: |",
    ]
    losses = training["training"]["final_loss_by_split"]
    for split in ("train", "validation", "test"):
        metrics = training[split]["metrics"]
        lines.append(
            f"| {split} | {losses[split]:.6f} | {_metric_text(metrics['precision'])} | "
            f"{_metric_text(metrics['recall'])} | {_metric_text(metrics['f1'])} | "
            f"{_metric_text(metrics['false_merge_rate'])} | "
            f"{_metric_text(metrics['candidate_recall'])} | {_metric_text(metrics['ece'])} | "
            f"{_metric_text(metrics['p95_inference_latency_ms'], suffix=' ms')} |"
        )
    lines.extend(
        [
            "",
            f"验证集温度为 `{training['calibration']['temperature']:.6f}`，决策阈值为 "
            f"`{training['calibration']['decision_threshold']:.6f}`。验证/测试 F1 满分建立在 "
            "4 条负边和部分标签上，不能解释为跨场景泛化。误合并率和完整候选召回率仍不可用。",
            "",
            "## 制品",
            "",
            f"- readiness audit SHA256：`{training['readiness_audit_sha256']}`",
            f"- bundle manifest SHA256：`{training['bundle']['manifest_sha256']}`",
            f"- weights SHA256：`{training['bundle']['weights_sha256']}`",
            f"- implementation SHA256：`{training['bundle']['implementation_sha256']}`",
            f"- 权重大小：`{training['test']['metrics']['model_size']['value']} bytes`",
            "",
            "## 补数要求",
            "",
        ]
    )
    for gap in readiness["producer_gaps"]:
        lines.append(f"- `{gap['code']}`：{gap['required_producer_change']}。")
    lines.append("")
    return "\n".join(lines)


def _metric_text(metric: Mapping[str, Any], *, suffix: str = "") -> str:
    if not metric.get("available"):
        return f"不可用（{metric.get('reason', 'unknown')}）"
    value = metric.get("value")
    if isinstance(value, float):
        return f"{value:.6f}{suffix}"
    return f"{value}{suffix}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit a D5 tracklet graph dataset and optionally train a development-only model"
    )
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--canonical-view-manifest")
    parser.add_argument("--training-seed-registry")
    parser.add_argument("--shared-seed-registry")
    parser.add_argument("--train-development", action="store_true")
    parser.add_argument("--seed", type=int, default=20260720)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--learning-rate", type=float, default=1.0e-3)
    parser.add_argument("--hidden-dim", type=int, default=32)
    parser.add_argument("--message-passing-steps", type=int, default=2)
    parser.add_argument("--graphs-per-step", type=int, default=4)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--latency-repeats", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report, json_path, markdown_path, audit_sha256 = run_tracklet_training_audit(
        args.dataset_dir,
        args.output_dir,
        canonical_view_manifest_path=args.canonical_view_manifest,
        training_seed_registry_path=args.training_seed_registry,
        shared_seed_registry_path=args.shared_seed_registry,
    )
    summary: dict[str, Any] = {
        "audit_report": str(json_path),
        "audit_markdown": str(markdown_path),
        "audit_sha256": audit_sha256,
        "training_readiness": report["training_readiness"]["status"],
        "promotion_readiness": report["promotion_readiness"]["status"],
        "development_model_trained": False,
    }
    if args.train_development:
        if not report["development_training"]["allowed"]:
            summary["development_training_failure_reasons"] = report[
                "development_training"
            ]["failure_reasons"]
        else:
            gc.collect()
            output_root = Path(args.output_dir)
            training_report_path = output_root / "development_training_report.json"
            bundle_dir = output_root / "development_model_bundle"
            training_report = run_training_pipeline(
                args.dataset_dir,
                bundle_dir,
                training_report_path,
                config=TrackletTrainingConfig(
                    seed=args.seed,
                    epochs=args.epochs,
                    learning_rate=args.learning_rate,
                    hidden_dim=args.hidden_dim,
                    message_passing_steps=args.message_passing_steps,
                    graphs_per_optimizer_step=args.graphs_per_step,
                    device=args.device,
                    latency_repeats=args.latency_repeats,
                ),
                development_only=True,
                readiness_audit_sha256=audit_sha256,
                canonical_view_manifest_path=args.canonical_view_manifest,
                training_seed_registry_path=args.training_seed_registry,
                shared_seed_registry_path=args.shared_seed_registry,
            )
            promotion = assess_tracklet_model_promotion(report, training_report)
            promotion_path = output_root / "promotion_assessment.json"
            training_markdown_path = output_root / "DEVELOPMENT_MODEL_REPORT_CN.md"
            _write_json_atomic(promotion_path, promotion)
            _write_markdown_atomic(
                training_markdown_path,
                _training_markdown(report, training_report, promotion),
            )
            summary.update(
                {
                    "development_model_trained": True,
                    "training_report": str(training_report_path),
                    "bundle_dir": str(bundle_dir),
                    "bundle_weights_sha256": training_report["bundle"]["weights_sha256"],
                    "promotion_assessment": str(promotion_path),
                    "training_markdown": str(training_markdown_path),
                    "promotion_status": promotion["status"],
                }
            )
    print(json.dumps(summary, ensure_ascii=True, allow_nan=False, sort_keys=True))
    return 0


def _load_audit_dataset(
    dataset_dir: str | Path,
    *,
    canonical_view_manifest_path: str | Path | None,
    training_seed_registry_path: str | Path | None,
    shared_seed_registry_path: str | Path | None,
) -> LoadedTrackletDataset:
    canonical_values = (
        canonical_view_manifest_path,
        training_seed_registry_path,
        shared_seed_registry_path,
    )
    if not any(value is not None for value in canonical_values):
        return load_tracklet_dataset(dataset_dir)
    if not all(value is not None for value in canonical_values):
        raise ValueError(
            "canonical tracklet view requires view manifest, training registry, and shared registry"
        )
    return load_tracklet_canonical_seed_view(
        dataset_dir,
        view_manifest_path=canonical_view_manifest_path,
        training_seed_registry_path=training_seed_registry_path,
        shared_seed_registry_path=shared_seed_registry_path,
    )


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI.
    raise SystemExit(main())


__all__ = [
    "PROMOTION_ASSESSMENT_SCHEMA_VERSION",
    "READINESS_AUDIT_SCHEMA_VERSION",
    "TrackletReadinessCriteria",
    "assess_tracklet_model_promotion",
    "audit_tracklet_training_readiness",
    "run_tracklet_training_audit",
]
