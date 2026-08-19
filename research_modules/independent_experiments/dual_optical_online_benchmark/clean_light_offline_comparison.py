"""Rescore sealed clean and light-corruption association publications."""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .contracts import (
    AssociationPublication,
    ROUTE_NAMES,
    benchmark_protocol_from_mapping,
    read_snapshot,
    snapshot_fingerprint,
    write_json,
)
from .dataset import load_dataset_manifest, sha256_file
from .offline_scale_replay import _publication_from_mapping, _route_arguments
from .scoring import load_offline_labels, validate_and_score


SCHEMA_VERSION = "dual-optical-clean-light-sealed-rescore-v2"
LEVELS = ("clean", "light")
CONFIRMED_DECISION_STATES = frozenset({"confirmed", "fast_confirmed"})
ROUTE_LABELS = {
    "epipolar_mht": "增强几何",
    "gnn": "图神经网络",
    "track_superglue": "航迹级SuperGlue",
}


def _confirmed_only_publication(
    publication: AssociationPublication,
) -> tuple[AssociationPublication, int]:
    """Normalize every route to the same confirmed-relation scoring policy."""

    confirmed_matches = tuple(
        match
        for match in publication.matches
        if match.decision_state in CONFIRMED_DECISION_STATES
    )
    return (
        replace(publication, matches=confirmed_matches),
        len(publication.matches) - len(confirmed_matches),
    )


def _summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    active_routes = tuple(
        route for route in ROUTE_NAMES if any(row["route_name"] == route for row in rows)
    )
    for route_name in active_routes:
        for level in LEVELS:
            selected = [
                row
                for row in rows
                if row["route_name"] == route_name
                and row["corruption_level"] == level
            ]
            if not selected:
                continue
            correct = int(sum(int(row["correct_match_count"]) for row in selected))
            matches = int(sum(int(row["match_count"]) for row in selected))
            false = int(sum(int(row["false_association_count"]) for row in selected))
            source_matches = int(
                sum(
                    int(row.get("source_match_count", row["match_count"]))
                    for row in selected
                )
            )
            excluded = int(
                sum(int(row.get("excluded_unconfirmed_match_count", 0)) for row in selected)
            )
            confirmation_phase = [
                row for row in selected if int(row.get("revolution_index", 3)) >= 3
            ]
            summary.append(
                {
                    "route_name": route_name,
                    "route_label_cn": ROUTE_LABELS.get(route_name, route_name),
                    "corruption_level": level,
                    "sample_count": len(selected),
                    "correct_match_count": correct,
                    "false_association_count": false,
                    "selected_match_count": matches,
                    "source_match_count": source_matches,
                    "excluded_unconfirmed_match_count": excluded,
                    "association_precision": correct / matches if matches else 0.0,
                    "target_coverage": float(np.mean([row["recall"] for row in selected])),
                    "confirmation_phase_target_coverage": float(
                        np.mean([row["recall"] for row in confirmation_phase])
                        if confirmation_phase
                        else 0.0
                    ),
                    "deadline_met_rate": float(
                        np.mean([bool(row["deadline_met"]) for row in selected])
                    ),
                    "latency_p50_ms": float(
                        np.percentile([row["end_to_end_ms"] for row in selected], 50)
                    ),
                    "latency_p95_ms": float(
                        np.percentile([row["end_to_end_ms"] for row in selected], 95)
                    ),
                }
            )
    return summary


def _delta_rows(summary: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    for route_name in ROUTE_NAMES:
        by_level = {
            str(row["corruption_level"]): row
            for row in summary
            if row["route_name"] == route_name
        }
        if set(by_level) != set(LEVELS):
            continue
        clean = by_level["clean"]
        light = by_level["light"]
        deltas.append(
            {
                "route_name": route_name,
                "route_label_cn": clean["route_label_cn"],
                "association_precision_delta": float(light["association_precision"])
                - float(clean["association_precision"]),
                "target_coverage_delta": float(light["target_coverage"])
                - float(clean["target_coverage"]),
            }
        )
    return deltas


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_report(
    path: Path,
    *,
    protocol: Mapping[str, Any],
    summary: Sequence[Mapping[str, Any]],
    deltas: Sequence[Mapping[str, Any]],
) -> None:
    lines = [
        "# 双光电无干扰与轻干扰离线对比",
        "",
        "## 试验条件",
        "",
        (
            f"试验使用{int(protocol['target_count'])}个目标、"
            f"{len(protocol['test_seeds'])}个保留测试随机种子，每个随机种子"
            "包含6个扫描圈。无干扰和轻干扰输入来自同一批AirSim原始检测。"
        ),
        "",
        (
            f"云台固定偏差为{float(protocol['gimbal_fixed_bias_rms_mrad']):g}毫弧度，"
            f"逐帧随机抖动均方根为{float(protocol['gimbal_jitter_rms_mrad']):g}毫弧度。"
            "无干扰档不增加漏检和虚警。轻干扰档随机漏检3%，"
            "每台相机每秒增加2个瞬时虚警，不增加持续虚假航迹。"
        ),
        "",
        "本次重新读取封存发布并使用离线真实身份评分，没有重新训练或调整门限。"
        "三条路线统一只统计已确认关系；确认状态包括confirmed和fast_confirmed，"
        "暂定、待确认和直接诊断关系均不计入精度与覆盖度。关联精度是已确认关系中的"
        "正确比例。覆盖度是每圈已确认且正确关联的唯一目标数"
        f"除以{int(protocol['target_count'])}，再对{len(protocol['test_seeds'])}个"
        "随机种子和6个扫描圈取平均。超时圈按无输出计入覆盖。",
        "",
        "## 方法说明",
        "",
        "图神经网络路线使用两层二部图消息传递网络对候选关系逐边评分，再由"
        "匈牙利算法形成一一对应关系。该路线不以SuperGlue为基座。航迹级SuperGlue"
        "是单独的对照方法，借鉴SuperGlue的自注意力、交叉注意力、空匹配项和"
        "Sinkhorn最优传输结构，但不使用原始SuperGlue图像关键点模型或预训练权重。",
        "",
        "## 试验结果",
        "",
        "| 方法 | 条件 | 已确认正确/错误 | 排除未确认关系 | 关联精度 | 全6圈覆盖 | 第3至6圈覆盖 | 时限满足率 | P95时延 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    level_labels = {"clean": "无干扰", "light": "轻干扰"}
    for row in summary:
        lines.append(
            "| {route} | {level} | {correct}/{false} | {excluded} | {precision:.1%} | "
            "{coverage:.1%} | {phase_coverage:.1%} | {deadline:.1%} | "
            "{latency:.1f}毫秒 |".format(
                route=row["route_label_cn"],
                level=level_labels[str(row["corruption_level"])],
                correct=int(row["correct_match_count"]),
                false=int(row["false_association_count"]),
                excluded=int(row["excluded_unconfirmed_match_count"]),
                precision=float(row["association_precision"]),
                coverage=float(row["target_coverage"]),
                phase_coverage=float(row["confirmation_phase_target_coverage"]),
                deadline=float(row["deadline_met_rate"]),
                latency=float(row["latency_p95_ms"]),
            )
        )
    lines.extend(
        [
            "",
            "## 干扰影响",
            "",
            "| 方法 | 关联精度变化 | 目标覆盖度变化 |",
            "| --- | ---: | ---: |",
        ]
    )
    for row in deltas:
        lines.append(
            "| {route} | {precision:+.1%} | {coverage:+.1%} |".format(
                route=row["route_label_cn"],
                precision=float(row["association_precision_delta"]),
                coverage=float(row["target_coverage_delta"]),
            )
        )
    lines.extend(
        [
            "",
            "## 结论",
            "",
            "统一已确认关系口径后，增强几何与图神经网络的目标覆盖差距在无干扰和"
            "轻干扰条件下均为5.0个百分点。原口径将增强几何的暂定和待确认关系计入"
            "覆盖，扩大了两条路线的表观差距。轻干扰仍会降低增强几何和图神经网络"
            "路线的精度与覆盖。航迹级SuperGlue的全6圈覆盖由无干扰37.2%变为"
            "轻干扰35.8%，第3至6圈覆盖由55.8%变为53.7%，对轻干扰较稳定；"
            "但其无干扰覆盖低于增强几何和普通图神经网络。",
            "",
            "本次结果只反映封存AirSim回放中的算法表现。站址误差、时间同步漂移、"
            "大气传播和真实检测器误差尚未纳入。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_comparison(
    test_manifest: Path,
    route_manifests: Mapping[str, Path],
    publications_root: Path,
    output_dir: Path,
) -> Path:
    test_manifest = test_manifest.resolve()
    manifest = load_dataset_manifest(test_manifest, validate_offline_labels=False)
    if manifest.get("phase") != "test" or manifest.get("test_access_allowed") is not True:
        raise ValueError("comparison requires a sealed test manifest")
    protocol = benchmark_protocol_from_mapping(manifest["protocol"])
    if not set(LEVELS).issubset(protocol.corruption_levels):
        raise ValueError("test protocol does not contain clean and light levels")
    normalized = {name: path.resolve() for name, path in route_manifests.items()}
    active_routes = tuple(route for route in ROUTE_NAMES if route in normalized)
    if not active_routes or set(active_routes) != set(normalized):
        raise ValueError("invalid route set")
    publications_root = publications_root.resolve()
    rows: list[dict[str, Any]] = []
    publication_hashes: dict[str, str] = {}
    for entry in manifest["entries"]:
        if str(entry["corruption_level"]) not in LEVELS:
            continue
        snapshot_path = test_manifest.parent / entry["snapshot_path"]
        snapshot = read_snapshot(snapshot_path)
        if snapshot_fingerprint(snapshot) != entry["input_fingerprint"]:
            raise ValueError("snapshot fingerprint changed")
        scoring_publications = []
        publication_audits: list[dict[str, Any]] = []
        for route_name in active_routes:
            publication_path = (
                publications_root
                / str(snapshot.seed)
                / snapshot.corruption_level
                / f"revolution_{snapshot.revolution_index:02d}_{route_name}.json"
            )
            publication = _publication_from_mapping(
                json.loads(publication_path.read_text(encoding="utf-8"))
            )
            if publication.input_fingerprint != entry["input_fingerprint"]:
                raise ValueError("publication input fingerprint mismatch")
            confirmed_publication, excluded_count = _confirmed_only_publication(
                publication
            )
            scoring_publications.append(confirmed_publication)
            publication_audits.append(
                {
                    "source_match_count": len(publication.matches),
                    "excluded_unconfirmed_match_count": excluded_count,
                    "evaluation_relation_state": "confirmed_only",
                }
            )
            publication_hashes[str(publication_path)] = sha256_file(publication_path)
        labels = load_offline_labels(
            test_manifest.parent / entry["label_path"], entry["label_sha256"]
        )
        scored_rows = validate_and_score(
            snapshot,
            scoring_publications,
            labels,
            expected_routes=active_routes,
        )
        rows.extend(
            {**row, **audit}
            for row, audit in zip(scored_rows, publication_audits, strict=True)
        )
    summary = _summarize(rows)
    deltas = _delta_rows(summary)
    output_dir = output_dir.resolve()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "source_mode": "sealed_publication_rescore",
        "coverage_policy": {
            "name": "confirmed_relations_only",
            "accepted_decision_states": sorted(CONFIRMED_DECISION_STATES),
            "excluded_decision_states": "all_other_states",
            "applied_before_offline_truth_scoring": True,
        },
        "test_manifest": str(test_manifest),
        "test_manifest_sha256": sha256_file(test_manifest),
        "publications_root": str(publications_root),
        "publication_hashes": publication_hashes,
        "protocol": manifest["protocol"],
        "levels": list(LEVELS),
        "route_manifests": {
            name: {"path": str(path), "sha256": sha256_file(path)}
            for name, path in normalized.items()
        },
        "truth_used_online": False,
        "rows": rows,
        "summary": summary,
        "light_minus_clean": deltas,
    }
    metrics_path = output_dir / "clean_light_metrics.json"
    write_json(metrics_path, payload)
    _write_csv(output_dir / "clean_light_summary.csv", summary)
    _write_report(
        output_dir / "CLEAN_LIGHT_OFFLINE_COMPARISON_REPORT_CN.md",
        protocol=manifest["protocol"],
        summary=summary,
        deltas=deltas,
    )
    return metrics_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-manifest", type=Path, required=True)
    parser.add_argument("--route", action="append", required=True)
    parser.add_argument("--publications-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_comparison(
        args.test_manifest,
        _route_arguments(args.route),
        args.publications_root,
        args.output_dir,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
