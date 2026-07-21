"""Detached formal-plus-supplemental canonical admission view for D5 graphs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .canonical_seed_view import (
    load_tracklet_canonical_seed_view,
    write_tracklet_canonical_seed_view,
)
from .tracklet_dataset import (
    DATASET_SCHEMA_VERSION,
    EDGE_FEATURE_VERSION,
    EVALUATOR_LABEL_SCHEMA_VERSION,
    GRAPH_SCHEMA_VERSION,
    NODE_FEATURE_VERSION,
    LoadedTrackletDataset,
    LoadedTrackletEpisode,
    sha256_file,
)
from .tracklet_supplemental_curriculum import (
    FORMAL_SCENARIO_CELLS,
    SupplementalCurriculumResult,
    TrackletSupplementalCurriculumError,
    load_tracklet_supplemental_curriculum,
)
from .tracklet_training_audit import (
    TrackletReadinessCriteria,
    audit_tracklet_training_readiness,
)


COMPOSITE_ADMISSION_VIEW_SCHEMA_VERSION = "d5.tracklet-composite-admission-view.v1"
COMPOSITE_SELECTION_POLICY_VERSION = "d5-tracklet-complete-label-source-selection-v1"


class TrackletCompositeAdmissionError(ValueError):
    """Stable fail-closed error at the detached admission boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class LoadedTrackletCompositeAdmission:
    view_manifest_path: Path
    view_manifest: Mapping[str, Any]
    view_manifest_sha256: str
    dataset: LoadedTrackletDataset
    readiness: Mapping[str, Any]

    def split(self, name: str) -> tuple[LoadedTrackletEpisode, ...]:
        return self.dataset.split(name)


def write_tracklet_composite_admission_view(
    *,
    formal_dataset_dir: str | Path,
    supplemental_root: str | Path,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    view_manifest_path: str | Path,
) -> LoadedTrackletCompositeAdmission:
    """Write a detached immutable source selection and strict readiness view."""

    view_path = Path(view_manifest_path).resolve()
    formal_root = Path(formal_dataset_dir).resolve()
    supplemental_dir = Path(supplemental_root).resolve()
    _assert_detached(view_path, (formal_root, supplemental_dir))
    if view_path.exists():
        _fail("view_already_exists", str(view_path))
    view_path.parent.mkdir(parents=True, exist_ok=True)
    formal_subview = view_path.with_name(view_path.stem + ".formal.json")
    supplemental_subview = view_path.with_name(view_path.stem + ".supplemental.json")
    if formal_subview.exists() or supplemental_subview.exists():
        _fail("canonical_subview_already_exists", str(view_path.parent))

    supplemental = load_tracklet_supplemental_curriculum(supplemental_dir)
    formal, formal_view, formal_view_sha = write_tracklet_canonical_seed_view(
        formal_root,
        training_seed_registry_path=training_seed_registry_path,
        shared_seed_registry_path=shared_seed_registry_path,
        view_manifest_path=formal_subview,
    )
    supplemental_dataset, supplemental_view, supplemental_view_sha = (
        write_tracklet_canonical_seed_view(
            supplemental.output_dir / "dataset",
            training_seed_registry_path=training_seed_registry_path,
            shared_seed_registry_path=shared_seed_registry_path,
            view_manifest_path=supplemental_subview,
        )
    )
    try:
        payload, dataset, readiness = _build_view_payload(
            formal=formal,
            supplemental=supplemental,
            supplemental_dataset=supplemental_dataset,
            formal_subview_path=formal_subview,
            formal_subview=formal_view,
            formal_subview_sha256=formal_view_sha,
            supplemental_subview_path=supplemental_subview,
            supplemental_subview=supplemental_view,
            supplemental_subview_sha256=supplemental_view_sha,
        )
        _write_json_atomic(view_path, payload)
    except Exception:
        formal_subview.unlink(missing_ok=True)
        supplemental_subview.unlink(missing_ok=True)
        raise
    return LoadedTrackletCompositeAdmission(
        view_manifest_path=view_path,
        view_manifest=MappingProxyType(payload),
        view_manifest_sha256=sha256_file(view_path),
        dataset=dataset,
        readiness=MappingProxyType(readiness),
    )


def load_tracklet_composite_admission_view(
    *,
    formal_dataset_dir: str | Path,
    supplemental_root: str | Path,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    view_manifest_path: str | Path,
) -> LoadedTrackletCompositeAdmission:
    """Recompute all source bindings and reject a stale or tampered view."""

    view_path = Path(view_manifest_path).resolve()
    formal_root = Path(formal_dataset_dir).resolve()
    supplemental_dir = Path(supplemental_root).resolve()
    _assert_detached(view_path, (formal_root, supplemental_dir))
    actual = _read_json(view_path)
    if actual.get("schema_version") != COMPOSITE_ADMISSION_VIEW_SCHEMA_VERSION:
        _fail("composite_view_schema_mismatch", "composite view schema changed")
    subviews = actual.get("canonical_subviews")
    if not isinstance(subviews, Mapping):
        _fail("canonical_subviews_missing", "canonical subview binding is missing")
    formal_subview = _bound_subview_path(view_path, subviews, "formal")
    supplemental_subview = _bound_subview_path(view_path, subviews, "supplemental")
    formal = load_tracklet_canonical_seed_view(
        formal_root,
        training_seed_registry_path=training_seed_registry_path,
        shared_seed_registry_path=shared_seed_registry_path,
        view_manifest_path=formal_subview,
    )
    supplemental = load_tracklet_supplemental_curriculum(supplemental_dir)
    supplemental_dataset = load_tracklet_canonical_seed_view(
        supplemental.output_dir / "dataset",
        training_seed_registry_path=training_seed_registry_path,
        shared_seed_registry_path=shared_seed_registry_path,
        view_manifest_path=supplemental_subview,
    )
    expected, dataset, readiness = _build_view_payload(
        formal=formal,
        supplemental=supplemental,
        supplemental_dataset=supplemental_dataset,
        formal_subview_path=formal_subview,
        formal_subview=_read_json(formal_subview),
        formal_subview_sha256=sha256_file(formal_subview),
        supplemental_subview_path=supplemental_subview,
        supplemental_subview=_read_json(supplemental_subview),
        supplemental_subview_sha256=sha256_file(supplemental_subview),
    )
    if actual != expected:
        _fail("composite_view_mismatch", "detached admission view no longer reproduces")
    return LoadedTrackletCompositeAdmission(
        view_manifest_path=view_path,
        view_manifest=MappingProxyType(actual),
        view_manifest_sha256=sha256_file(view_path),
        dataset=dataset,
        readiness=MappingProxyType(readiness),
    )


def write_composite_admission_report(
    admission: LoadedTrackletCompositeAdmission,
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> tuple[str, str]:
    """Write the full-sample readiness evidence without training a model."""

    report = dict(admission.readiness)
    report["view_manifest_sha256"] = admission.view_manifest_sha256
    report["view_content_sha256"] = admission.view_manifest["content_sha256"]
    report["content_sha256"] = _sha256_json(report)
    json_file = Path(json_path)
    markdown_file = Path(markdown_path)
    _write_json_atomic(json_file, report)
    _write_text_atomic(markdown_file, render_composite_admission_markdown(report))
    return sha256_file(json_file), sha256_file(markdown_file)


def render_composite_admission_markdown(report: Mapping[str, Any]) -> str:
    """Render a Chinese admission report with exact gate counts."""

    summary = report["selected_corpus"]
    support = report["data_support_readiness"]
    lines = [
        "# D5 跨视角图正式与补充语料准入审计",
        "",
        "## 结论",
        "",
        f"分离式视图纳入 `{summary['episode_count']}` 个图帧和 "
        f"`{summary['candidate_edge_count']}` 条候选边。数据量与标签门状态为 "
        f"`{support['status']}`，总体训练准入状态为 `{report['training_readiness']['status']}`。",
        "",
        "本轮没有训练模型，没有生成 `.pt`，G1、assist 和在线控制权限均保持关闭。"
        "正式源标签不完整帧未被回填，只按固定规则从准入视图排除。",
        "",
        "## 来源与选择",
        "",
        f"- 正式源 manifest SHA-256：`{report['sources']['formal_manifest_sha256']}`",
        f"- 补充源 manifest SHA-256：`{report['sources']['supplemental_manifest_sha256']}`",
        f"- 正式入选/排除帧：`{summary['formal_selected_episode_count']}` / "
        f"`{summary['formal_excluded_episode_count']}`",
        f"- 补充入选帧：`{summary['supplemental_selected_episode_count']}`",
        f"- 未标注候选边：`{summary['unlabeled_candidate_edge_count']}`",
        f"- 标签可用率：`{summary['label_availability_ratio']:.2%}`",
        "",
        "## 分割门",
        "",
        "| 分割 | 帧数 | 无边比例 | 正边 | 负边 | candidate recall 同目标 pair | 双类 cell 比例 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split in ("train", "validation", "test"):
        item = report["split_summaries"][split]
        lines.append(
            f"| {split} | {item['episode_count']} | {item['edge_free_ratio']:.2%} | "
            f"{item['positive_candidate_edges']} | {item['negative_candidate_edges']} | "
            f"{item['candidate_recall_pair_support']} | "
            f"{item['scenario_scale_both_class_fraction']:.2%} |"
        )
    lines.extend(["", "## 失败门", ""])
    failures = report["training_readiness"]["failure_reasons"]
    if failures:
        lines.extend(f"- `{value}`" for value in failures)
    else:
        lines.append("- 无数据准入失败门。")
    lines.extend(
        [
            "",
            "## 边界",
            "",
            "图网络仍只能为已通过默认几何门的候选边输出同目标概率。中心航迹编号由中心"
            "链路管理，D5 不创建、改写或换绑 `global_track_id`。模型准入、保留 seed 独立"
            "评估和同 seed 影子对照仍需后续完成。",
            "",
        ]
    )
    return "\n".join(lines)


def _build_view_payload(
    *,
    formal: LoadedTrackletDataset,
    supplemental: SupplementalCurriculumResult,
    supplemental_dataset: LoadedTrackletDataset,
    formal_subview_path: Path,
    formal_subview: Mapping[str, Any],
    formal_subview_sha256: str,
    supplemental_subview_path: Path,
    supplemental_subview: Mapping[str, Any],
    supplemental_subview_sha256: str,
) -> tuple[dict[str, Any], LoadedTrackletDataset, dict[str, Any]]:
    if supplemental.manifest["formal_source"]["manifest_sha256"] != formal_subview["source"][
        "manifest_sha256"
    ]:
        _fail("formal_source_changed", "supplemental source does not bind current formal manifest")
    formal_selected = tuple(
        episode
        for episode in formal.episodes
        if episode.evaluator_labels.labels_complete
        and episode.evaluator_labels.candidate_recall_available
    )
    formal_selected_uids = {episode.graph.episode_uid for episode in formal_selected}
    formal_excluded = tuple(
        episode
        for episode in formal.episodes
        if episode.graph.episode_uid not in formal_selected_uids
    )
    supplemental_selected = tuple(supplemental_dataset.episodes)
    if any(
        not episode.evaluator_labels.labels_complete
        or not episode.evaluator_labels.candidate_recall_available
        for episode in supplemental_selected
    ):
        _fail("supplemental_incomplete_in_admission", "supplemental source is not fully labeled")
    selected = tuple(
        sorted(
            (*formal_selected, *supplemental_selected),
            key=lambda item: (
                item.split,
                item.graph.seed,
                item.graph.scenario_version,
                item.graph.episode_uid,
            ),
        )
    )
    selection_records = [
        {
            "episode_uid": item.graph.episode_uid,
            "source": (
                "formal"
                if item.graph.episode_uid in formal_selected_uids
                else "supplemental"
            ),
            "split": item.split,
            "seed": item.graph.seed,
            "graph_sha256": item.graph_sha256,
            "labels_sha256": item.labels_sha256,
        }
        for item in selected
    ]
    split_sha = _sha256_json({"selection": selection_records})
    training_sha = _sha256_json(
        {"train": [item for item in selection_records if item["split"] == "train"]}
    )
    effective_manifest = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "evaluator_label_schema_version": EVALUATOR_LABEL_SCHEMA_VERSION,
        "node_feature_version": NODE_FEATURE_VERSION,
        "edge_feature_version": EDGE_FEATURE_VERSION,
        "config_sha256": _sha256_json(
            {
                "formal": formal_subview["source"]["manifest_sha256"],
                "supplemental": supplemental.manifest_sha256,
                "selection_policy": COMPOSITE_SELECTION_POLICY_VERSION,
            }
        ),
        "split_sha256": split_sha,
        "training_set_sha256": training_sha,
        "canonical_seed_view": {
            "schema_version": COMPOSITE_ADMISSION_VIEW_SCHEMA_VERSION,
            "formal_subview_sha256": formal_subview_sha256,
            "supplemental_subview_sha256": supplemental_subview_sha256,
            "selection_sha256": split_sha,
        },
    }
    dataset = LoadedTrackletDataset(
        root=formal_subview_path.parent,
        manifest=MappingProxyType(effective_manifest),
        manifest_sha256=_sha256_json(effective_manifest),
        episodes=selected,
    )
    audit = audit_tracklet_training_readiness(
        dataset,
        criteria=TrackletReadinessCriteria(),
    )
    labels_available = sum(
        item.class_balance["unlabeled_candidate_edges"] for item in selected
    ) == 0 and all(item.evaluator_labels.labels_complete for item in selected)
    support_pass = audit["training_readiness"]["passed"] and labels_available
    clean_source = not bool(supplemental.manifest["source"]["repository_dirty"])
    training_pass = support_pass and clean_source
    failure_reasons = [
        *(f"data_gate:{name}" for name in audit["training_readiness"]["failed_gates"]),
        *([] if labels_available else ["label_availability_below_100_percent"]),
        *([] if clean_source else ["supplemental_source_repository_dirty"]),
    ]
    selected_summary = _selected_summary(
        selected,
        formal_selected_count=len(formal_selected),
        formal_excluded_count=len(formal_excluded),
        supplemental_count=len(supplemental_selected),
    )
    readiness = {
        "schema_version": "d5.tracklet-composite-admission-readiness.v1",
        "sources": {
            "formal_manifest_sha256": formal_subview["source"]["manifest_sha256"],
            "supplemental_manifest_sha256": supplemental.manifest_sha256,
            "formal_source_modified": False,
            "supplemental_source_modified": False,
            "supplemental_source_repository_dirty": not clean_source,
        },
        "selected_corpus": selected_summary,
        "criteria": audit["criteria"],
        "data_support_readiness": {
            "status": "pass" if support_pass else "fail_closed",
            "passed": support_pass,
            "existing_gate_results": audit["training_readiness"]["gates"],
            "label_availability_100_percent": labels_available,
        },
        "training_readiness": {
            "status": "pass" if training_pass else "fail_closed",
            "passed": training_pass,
            "failure_reasons": failure_reasons,
        },
        "promotion_readiness": {
            "status": "awaiting_new_model_evidence" if training_pass else "fail_closed",
            "passed": False,
            "g1_assist_eligible": False,
            "model_training_performed": False,
            "pt_generated": False,
        },
        "split_summaries": _compact_split_summaries(audit),
        "identity_safety": audit["identity_safety"],
    }
    payload: dict[str, Any] = {
        "schema_version": COMPOSITE_ADMISSION_VIEW_SCHEMA_VERSION,
        "selection_policy_version": COMPOSITE_SELECTION_POLICY_VERSION,
        "canonical_subviews": {
            "formal": {
                "file": formal_subview_path.name,
                "file_sha256": formal_subview_sha256,
                "content_sha256": formal_subview["content_sha256"],
            },
            "supplemental": {
                "file": supplemental_subview_path.name,
                "file_sha256": supplemental_subview_sha256,
                "content_sha256": supplemental_subview["content_sha256"],
            },
        },
        "sources": readiness["sources"],
        "source_contract": {
            "source_manifest_modified": False,
            "source_artifact_modified": False,
            "sample_copy_allowed": False,
            "source_label_backfill_allowed": False,
            "complete_seed_atomic_split_required": True,
            "reserved_seed_allowed": False,
        },
        "selection": {
            "formal_policy": "labels_complete_and_candidate_recall_available",
            "supplemental_policy": "all_full_profile_episodes",
            "selection_sha256": split_sha,
            "training_set_sha256": training_sha,
            **selected_summary,
        },
        "duplicate_audit": dict(supplemental.manifest["duplicate_audit"]),
        "readiness": readiness,
    }
    payload["content_sha256"] = _sha256_json(payload)
    return payload, dataset, readiness


def _selected_summary(
    episodes: Sequence[LoadedTrackletEpisode],
    *,
    formal_selected_count: int,
    formal_excluded_count: int,
    supplemental_count: int,
) -> dict[str, Any]:
    edge_count = sum(item.graph.edge_count for item in episodes)
    unlabeled = sum(item.class_balance["unlabeled_candidate_edges"] for item in episodes)
    seeds_by_split = {
        split: sorted({item.graph.seed for item in episodes if item.split == split})
        for split in ("train", "validation", "test")
    }
    return {
        "episode_count": len(episodes),
        "formal_selected_episode_count": formal_selected_count,
        "formal_excluded_episode_count": formal_excluded_count,
        "supplemental_selected_episode_count": supplemental_count,
        "node_count": sum(item.graph.node_count for item in episodes),
        "candidate_edge_count": edge_count,
        "unlabeled_candidate_edge_count": unlabeled,
        "label_availability_ratio": 1.0 if not unlabeled else 0.0,
        "seed_counts": {split: len(values) for split, values in seeds_by_split.items()},
        "reserved_evaluation_seed_overlap": sorted(
            set(range(1000, 1020))
            & set().union(*(set(values) for values in seeds_by_split.values()))
        ),
    }


def _compact_split_summaries(audit: Mapping[str, Any]) -> dict[str, Any]:
    output = {}
    both = audit["scenario_scale_both_class_fraction"]
    for split in ("train", "validation", "test"):
        item = audit["split_summaries"][split]
        output[split] = {
            "episode_count": item["episode_count"],
            "edge_free_episode_count": item["edge_free_episode_count"],
            "edge_free_ratio": item["edge_free_ratio"],
            "positive_candidate_edges": item["class_balance"]["positive_candidate_edges"],
            "negative_candidate_edges": item["class_balance"]["negative_candidate_edges"],
            "unlabeled_candidate_edges": item["class_balance"]["unlabeled_candidate_edges"],
            "candidate_recall_availability_ratio": item["candidate_recall"]["availability_ratio"],
            "candidate_recall_pair_support": item["candidate_recall"]["partial_denominator"],
            "scenario_scale_both_class_fraction": both[split],
        }
    return output


def _bound_subview_path(
    view_path: Path,
    subviews: Mapping[str, Any],
    name: str,
) -> Path:
    item = subviews.get(name)
    if not isinstance(item, Mapping) or set(item) != {"file", "file_sha256", "content_sha256"}:
        _fail("canonical_subview_binding_invalid", name)
    filename = Path(str(item["file"]))
    if filename.is_absolute() or len(filename.parts) != 1:
        _fail("canonical_subview_path_invalid", str(filename))
    path = view_path.parent / filename
    if sha256_file(path) != item["file_sha256"]:
        _fail("canonical_subview_hash_mismatch", name)
    return path


def _assert_detached(path: Path, source_roots: Sequence[Path]) -> None:
    for root in source_roots:
        resolved = root.resolve()
        if path == resolved or resolved in path.parents or path in resolved.parents:
            _fail("view_not_detached", f"view and source overlap: {resolved}")


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("view_json_invalid", f"{path}: {exc}")
    if not isinstance(value, dict):
        _fail("view_json_not_object", str(path))
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    _write_bytes_atomic(
        path,
        (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        ),
    )


def _write_text_atomic(path: Path, value: str) -> None:
    _write_bytes_atomic(path, value.encode("utf-8"))


def _write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _fail(code: str, message: str) -> None:
    raise TrackletCompositeAdmissionError(code, message)


__all__ = [
    "COMPOSITE_ADMISSION_VIEW_SCHEMA_VERSION",
    "COMPOSITE_SELECTION_POLICY_VERSION",
    "LoadedTrackletCompositeAdmission",
    "TrackletCompositeAdmissionError",
    "load_tracklet_composite_admission_view",
    "render_composite_admission_markdown",
    "write_composite_admission_report",
    "write_tracklet_composite_admission_view",
]
