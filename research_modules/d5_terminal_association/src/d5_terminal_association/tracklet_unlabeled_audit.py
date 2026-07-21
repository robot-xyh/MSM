"""Fail-closed lineage audit for unlabeled formal tracklet candidate edges.

The formal graph corpus is immutable.  This module only inspects its detached
graph and evaluator-label artifacts.  A missing endpoint is recoverable only
when an independently supplied offline observation-lineage record proves the
same episode, anonymous tracklet key, and measurement timestamp.  Temporal
nearest-neighbour propagation and local-track continuity are deliberately not
accepted as labels.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from .tracklet_dataset import LoadedTrackletDataset, load_tracklet_dataset


UNLABELED_AUDIT_SCHEMA_VERSION = "d5.tracklet-unlabeled-lineage-audit.v1"
OFFLINE_LINEAGE_SCHEMA_VERSION = "d5.tracklet-offline-observation-lineage.v1"


class TrackletUnlabeledAuditError(ValueError):
    """Stable fail-closed error raised by the lineage audit boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


def audit_formal_unlabeled_edges(
    dataset_dir: str | Path,
    *,
    offline_lineage_path: str | Path | None = None,
) -> dict[str, Any]:
    """Audit every unlabeled edge without modifying the formal source.

    ``offline_lineage_path`` is optional because the frozen 2026-07-20 formal
    export did not preserve such an artifact.  When supplied, it must bind the
    exact source manifest and contain exact-timestamp evaluator-only records.
    """

    dataset = load_tracklet_dataset(dataset_dir)
    lineage, lineage_binding = _load_lineage(
        offline_lineage_path,
        expected_manifest_sha256=dataset.manifest_sha256,
    )
    rows: list[dict[str, Any]] = []
    pattern_counts: Counter[str] = Counter()
    scenario_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    missing_endpoint_count = 0
    exact_lineage_endpoint_count = 0
    recoverable_edge_count = 0

    for episode in dataset.episodes:
        if episode.class_balance["unlabeled_candidate_edges"] <= 0:
            continue
        labels = episode.evaluator_labels.by_tracklet_key
        graph = episode.graph
        for edge_index in range(graph.edge_count):
            source_index = int(graph.edge_index[0, edge_index])
            target_index = int(graph.edge_index[1, edge_index])
            endpoint_values = (
                (
                    "source",
                    graph.tracklet_keys[source_index],
                    float(graph.measurement_timestamps[source_index]),
                ),
                (
                    "target",
                    graph.tracklet_keys[target_index],
                    float(graph.measurement_timestamps[target_index]),
                ),
            )
            missing = [item for item in endpoint_values if item[1] not in labels]
            if not missing:
                continue
            missing_endpoint_count += len(missing)
            pattern = (
                "both_endpoints_missing"
                if len(missing) == 2
                else f"{missing[0][0]}_endpoint_missing"
            )
            pattern_counts[pattern] += 1
            scenario_counts[graph.scenario_version] += 1
            split_counts[episode.split] += 1
            missing_rows: list[dict[str, Any]] = []
            all_missing_proven = True
            for side, tracklet_key, timestamp in missing:
                proof = lineage.get((graph.episode_uid, tracklet_key, _time_key(timestamp)))
                proven = proof is not None
                exact_lineage_endpoint_count += int(proven)
                all_missing_proven &= proven
                missing_rows.append(
                    {
                        "side": side,
                        "tracklet_key": tracklet_key,
                        "measurement_timestamp": timestamp,
                        "status": (
                            "recoverable_exact_offline_observation_lineage"
                            if proven
                            else "unavailable_source_observation_lineage_missing"
                        ),
                        "source_observation_id_sha256": (
                            proof["source_observation_id_sha256"] if proven else None
                        ),
                    }
                )
            recoverable_edge_count += int(all_missing_proven)
            rows.append(
                {
                    "episode_uid": graph.episode_uid,
                    "episode_id": graph.episode_id,
                    "scenario_version": graph.scenario_version,
                    "seed": graph.seed,
                    "split": episode.split,
                    "edge_index": edge_index,
                    "source_tracklet_key": endpoint_values[0][1],
                    "target_tracklet_key": endpoint_values[1][1],
                    "missing_pattern": pattern,
                    "edge_status": (
                        "recoverable_without_source_rewrite"
                        if all_missing_proven
                        else "unavailable"
                    ),
                    "missing_endpoints": missing_rows,
                }
            )

    expected_unlabeled = sum(
        episode.class_balance["unlabeled_candidate_edges"]
        for episode in dataset.episodes
    )
    if len(rows) != expected_unlabeled:
        raise TrackletUnlabeledAuditError(
            "unlabeled_edge_inventory_mismatch",
            f"manifest={expected_unlabeled};audited={len(rows)}",
        )
    unavailable = len(rows) - recoverable_edge_count
    report: dict[str, Any] = {
        "schema_version": UNLABELED_AUDIT_SCHEMA_VERSION,
        "source": {
            "dataset_manifest_sha256": dataset.manifest_sha256,
            "dataset_schema_version": dataset.manifest["schema_version"],
            "episode_count": len(dataset.episodes),
            "source_modified": False,
        },
        "offline_lineage": lineage_binding,
        "summary": {
            "unlabeled_candidate_edge_count": len(rows),
            "missing_endpoint_count": missing_endpoint_count,
            "exact_lineage_endpoint_count": exact_lineage_endpoint_count,
            "recoverable_edge_count": recoverable_edge_count,
            "unavailable_edge_count": unavailable,
            "nearest_neighbor_or_track_continuity_labels_used": 0,
            "formal_source_records_rewritten": 0,
        },
        "missing_pattern_counts": dict(sorted(pattern_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "scenario_counts": dict(sorted(scenario_counts.items())),
        "decision": {
            "formal_backfill_allowed": bool(recoverable_edge_count),
            "formal_backfill_performed": False,
            "unproven_edges_remain_unavailable": unavailable,
            "training_view_must_exclude_incomplete_label_frames": bool(unavailable),
        },
        "edges": rows,
    }
    report["content_sha256"] = _sha256_json(report)
    return report


def render_unlabeled_audit_markdown(report: Mapping[str, Any]) -> str:
    """Render a concise Chinese evidence report."""

    summary = report["summary"]
    lineage = report["offline_lineage"]
    lines = [
        "# D5 正式图未标注边溯源审计",
        "",
        "## 结论",
        "",
        f"正式语料包含 `{summary['unlabeled_candidate_edge_count']}` 条未标注候选边，"
        f"涉及 `{summary['missing_endpoint_count']}` 个缺失端点。可由同帧离线观测来源链"
        f"直接证明的边为 `{summary['recoverable_edge_count']}` 条，仍不可用的边为 "
        f"`{summary['unavailable_edge_count']}` 条。",
        "",
        "未使用最近邻、跨帧轨迹编号沿用或几何相似度生成标签。正式图、标签和 manifest "
        "均未修改。标签不完整帧只在后续分离式准入视图中排除。",
        "",
        "## 来源证据",
        "",
        f"- 正式 manifest SHA-256：`{report['source']['dataset_manifest_sha256']}`",
        f"- 独立观测来源链：`{lineage['status']}`",
        f"- 来源链记录数：`{lineage['record_count']}`",
        f"- 精确来源链端点数：`{summary['exact_lineage_endpoint_count']}`",
        "",
        "## 缺失类型",
        "",
    ]
    for name, count in report["missing_pattern_counts"].items():
        lines.append(f"- `{name}`：`{count}` 条。")
    lines.extend(["", "## 分割", ""])
    for name, count in report["split_counts"].items():
        lines.append(f"- `{name}`：`{count}` 条。")
    lines.extend(["", "## 场景", ""])
    for name, count in report["scenario_counts"].items():
        lines.append(f"- `{name}`：`{count}` 条。")
    lines.extend(
        [
            "",
            "## 处置",
            "",
            "不可证明的端点继续标记为 `unavailable`。补充课程使用独立物理投影和独立 "
            "evaluator 标签生成新样本，不回填冻结正式语料。",
            "",
        ]
    )
    return "\n".join(lines)


def write_unlabeled_audit(
    report: Mapping[str, Any],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> tuple[str, str]:
    """Write detached audit artifacts atomically."""

    json_file = Path(json_path)
    markdown_file = Path(markdown_path)
    _write_bytes_atomic(
        json_file,
        (json.dumps(report, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        ),
    )
    _write_bytes_atomic(
        markdown_file,
        render_unlabeled_audit_markdown(report).encode("utf-8"),
    )
    return _sha256_file(json_file), _sha256_file(markdown_file)


def _load_lineage(
    path: str | Path | None,
    *,
    expected_manifest_sha256: str,
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], dict[str, Any]]:
    if path is None:
        return {}, {
            "status": "not_preserved_in_frozen_formal_export",
            "path_supplied": False,
            "file_sha256": None,
            "record_count": 0,
            "source_manifest_bound": False,
        }
    file = Path(path)
    payload = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        _fail("lineage_payload_invalid", "offline lineage must be a JSON object")
    if payload.get("schema_version") != OFFLINE_LINEAGE_SCHEMA_VERSION:
        _fail("lineage_schema_mismatch", "offline lineage schema changed")
    if payload.get("source_manifest_sha256") != expected_manifest_sha256:
        _fail("lineage_source_mismatch", "offline lineage does not bind the formal manifest")
    records = payload.get("records")
    if not isinstance(records, list):
        _fail("lineage_records_invalid", "offline lineage records must be a list")
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in records:
        if not isinstance(item, Mapping):
            _fail("lineage_record_invalid", "offline lineage record must be an object")
        required = {
            "episode_uid",
            "tracklet_key",
            "measurement_timestamp",
            "source_observation_id",
            "truth_entity_id",
            "evidence_kind",
        }
        if set(item) != required:
            _fail("lineage_record_fields_mismatch", "offline lineage record fields changed")
        if item["evidence_kind"] != "offline_observation_truth_lineage":
            _fail("lineage_evidence_kind_invalid", "lineage evidence is not direct observation truth")
        timestamp = float(item["measurement_timestamp"])
        if not np.isfinite(timestamp):
            _fail("lineage_timestamp_invalid", "lineage timestamp must be finite")
        for name in ("episode_uid", "tracklet_key", "source_observation_id", "truth_entity_id"):
            if not str(item[name]).strip():
                _fail("lineage_identity_invalid", f"{name} must be non-empty")
        key = (str(item["episode_uid"]), str(item["tracklet_key"]), _time_key(timestamp))
        if key in index:
            _fail("lineage_duplicate", f"duplicate exact lineage record: {key}")
        index[key] = {
            "truth_entity_id": str(item["truth_entity_id"]),
            "source_observation_id_sha256": hashlib.sha256(
                str(item["source_observation_id"]).encode("utf-8")
            ).hexdigest(),
        }
    return index, {
        "status": "available_exact_observation_lineage",
        "path_supplied": True,
        "file_sha256": _sha256_file(file),
        "record_count": len(index),
        "source_manifest_bound": True,
    }


def _time_key(value: float) -> str:
    return format(float(value), ".17g")


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _fail(code: str, message: str) -> None:
    raise TrackletUnlabeledAuditError(code, message)


__all__ = [
    "OFFLINE_LINEAGE_SCHEMA_VERSION",
    "TrackletUnlabeledAuditError",
    "UNLABELED_AUDIT_SCHEMA_VERSION",
    "audit_formal_unlabeled_edges",
    "render_unlabeled_audit_markdown",
    "write_unlabeled_audit",
]
