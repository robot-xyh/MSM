#!/usr/bin/env python3
"""Replay scalable-3D identity producers and report strict metric blockers."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from typing import Any

from d2_data_association import (
    build_scalable_3d_identity_blocker_diagnostics,
    discover_formal_identity_audit_scope,
    evaluate_scalable_3d_identity_files,
    load_scalable_3d_identity_evaluation,
    load_scalable_3d_identity_evidence,
    load_scalable_3d_observation_truth_labels,
    sha256_file,
    write_formal_identity_blocker_causal_pack,
    write_scalable_3d_identity_blocker_diagnostics,
)


AGGREGATE_SCHEMA_VERSION = (
    "d2.scalable3d_identity_blocker_audit_aggregate.v1"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--episode-root", type=Path)
    input_group.add_argument("--execution-root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--episode-glob",
        default="10p0s_seed_*_nominal",
    )
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument("--expected-source-git-commit")
    parser.add_argument("--expected-execution-plan-sha256")
    parser.add_argument("--expected-completed-episode-count", type=int)
    parser.add_argument(
        "--expected-strict-unavailable-episode-count",
        type=int,
    )
    parser.add_argument(
        "--verify-archive-payload-sha256",
        action="store_true",
    )
    args = parser.parse_args()

    if args.execution_root is not None:
        scope = discover_formal_identity_audit_scope(
            args.execution_root,
            expected_source_git_commit=args.expected_source_git_commit,
            expected_execution_plan_sha256=(
                args.expected_execution_plan_sha256
            ),
            expected_completed_episode_count=(
                args.expected_completed_episode_count
            ),
            expected_strict_unavailable_episode_count=(
                args.expected_strict_unavailable_episode_count
            ),
            archive_root=args.archive_root,
            verify_archive_payload_sha256=(
                args.verify_archive_payload_sha256
            ),
        )
        result = write_formal_identity_blocker_causal_pack(
            scope,
            args.output_dir,
        )
        print(f"completed_episode_count={scope.completed_episode_count}")
        print(
            "strict_unavailable_episode_count="
            f"{len(scope.strict_unavailable_references)}"
        )
        print(f"case_count={result['case_count']}")
        print(f"mapping_event_count={result['mapping_event_count']}")
        print(f"aggregate_sha256={result['aggregate_sha256']}")
        print(f"report_sha256={result['report_sha256']}")
        print(f"sha256sums_sha256={result['sha256sums_sha256']}")
        print(f"output_dir={result['output_dir']}")
        return

    assert args.episode_root is not None
    episode_dirs = sorted(args.episode_root.glob(args.episode_glob))
    if not episode_dirs:
        raise SystemExit("no episode directories matched")
    output_dir = args.output_dir
    episode_output_dir = output_dir / "episodes"
    episode_output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    diagnostics_payloads: list[dict[str, Any]] = []
    for episode_dir in episode_dirs:
        diagnostics, row = _audit_episode(episode_dir)
        destination = episode_output_dir / (
            f"{diagnostics.episode_id}_identity_blockers.json"
        )
        diagnostics_sha = write_scalable_3d_identity_blocker_diagnostics(
            destination,
            diagnostics,
        )
        payload = diagnostics.to_dict()
        payload["artifact_sha256"] = diagnostics_sha
        diagnostics_payloads.append(payload)
        row["diagnostics_sha256"] = diagnostics_sha
        rows.append(row)

    aggregate = _aggregate(rows, diagnostics_payloads)
    aggregate_path = output_dir / "identity_blocker_aggregate.json"
    aggregate_sha = _write_json(aggregate_path, aggregate)
    csv_path = output_dir / "identity_blocker_per_seed.csv"
    csv_sha = _write_csv(csv_path, rows)
    report_path = output_dir / "D2_200V200_IDENTITY_BLOCKER_AUDIT_CN.md"
    report_sha = _write_report(
        report_path,
        aggregate,
        aggregate_sha=aggregate_sha,
        csv_sha=csv_sha,
    )

    print(f"episode_count={aggregate['episode_count']}")
    print(
        "producer_replay_verified_count="
        f"{aggregate['producer_replay_verified_count']}"
    )
    print(
        "strict_identity_metrics_available_count="
        f"{aggregate['strict_identity_metrics_available_count']}"
    )
    print(
        "persisted_multi_truth_track_frame_count="
        f"{aggregate['root_cause_counts'].get('persisted_multi_truth_track_frame', 0)}"
    )
    print(
        "truth_sidecar_label_absent_count="
        f"{aggregate['root_cause_counts'].get('truth_sidecar_label_absent', 0)}"
    )
    print(
        "d1_consumable_episode_count="
        f"{aggregate['d1_lineage_mapping']['consumable_episode_count']}"
    )
    print(f"aggregate_sha256={aggregate_sha}")
    print(f"csv_sha256={csv_sha}")
    print(f"report_sha256={report_sha}")
    print(f"output_dir={output_dir.resolve()}")


def _audit_episode(
    episode_dir: Path,
) -> tuple[Any, dict[str, Any]]:
    identity_dir = episode_dir / "offline_identity"
    identity_manifest = _load_json(identity_dir / "manifest.json")
    source_hashes = _mapping(
        identity_manifest.get("source_hashes"),
        "identity manifest source_hashes",
    )
    evidence_path = identity_dir / "identity_evidence.json"
    evaluation_path = identity_dir / "identity_evaluation.json"
    d1_path = identity_dir / "online_d1_records.jsonl"
    d2_path = identity_dir / "online_d2_records.jsonl"
    labels_path = identity_dir / "observation_truth_labels.jsonl"

    persisted = load_scalable_3d_identity_evaluation(
        evaluation_path,
        expected_sha256=str(source_hashes["identity_evaluation"]),
    )
    configuration = persisted.configuration
    replayed = evaluate_scalable_3d_identity_files(
        evidence_path=evidence_path,
        expected_evidence_sha256=str(source_hashes["identity_evidence"]),
        online_d1_records_path=d1_path,
        online_d2_records_path=d2_path,
        observation_truth_labels_path=labels_path,
        timestamp_tolerance_s=float(
            configuration.get("timestamp_tolerance_s", 1.0e-9)
        ),
        lineage_time_window_s=float(
            configuration.get("lineage_time_window_s", 1.0)
        ),
        truth_presence_window_s=float(
            configuration.get("truth_presence_window_s", 1.0)
        ),
    )
    if replayed.to_dict() != persisted.to_dict():
        raise ValueError(
            f"producer replay differs from persisted evaluation: {episode_dir}"
        )
    evidence = load_scalable_3d_identity_evidence(
        evidence_path,
        expected_sha256=str(source_hashes["identity_evidence"]),
    )
    labels = load_scalable_3d_observation_truth_labels(
        labels_path,
        expected_sha256=str(source_hashes["observation_truth_labels"]),
    )

    consistency_dir = episode_dir / "offline_consistency"
    consistency_manifest = _load_json(consistency_dir / "manifest.json")
    consistency_source_hashes = _mapping(
        consistency_manifest.get("source_hashes"),
        "consistency manifest source_hashes",
    )
    consistency_evidence_path = consistency_dir / "online_evidence.json"
    expected_consistency_sha = str(
        consistency_source_hashes["online_evidence"]
    )
    actual_consistency_sha = sha256_file(consistency_evidence_path)
    if actual_consistency_sha != expected_consistency_sha:
        raise ValueError(
            "D1 consistency evidence source SHA-256 mismatch for "
            f"{episode_dir.name}"
        )
    consistency_evidence = _load_json(consistency_evidence_path)

    diagnostics = build_scalable_3d_identity_blocker_diagnostics(
        evidence,
        replayed,
        labels,
        identity_evaluation_sha256=str(
            source_hashes["identity_evaluation"]
        ),
        d1_consistency_evidence=consistency_evidence,
        d1_consistency_evidence_sha256=actual_consistency_sha,
    )
    d1_audit = _mapping(
        diagnostics.d1_lineage_mapping_audit,
        "D1 lineage mapping audit",
    )
    partial = replayed.partial_identity_diagnostics
    episode_manifest = _load_json(episode_dir / "manifest.json")
    return diagnostics, {
        "seed": int(episode_manifest["seed"]),
        "episode_id": diagnostics.episode_id,
        "producer_replay_verified": True,
        "source_sha256_verified": True,
        "online_truth_isolation_verified": (
            diagnostics.online_truth_isolation_verified
        ),
        "strict_identity_metrics_available": (
            diagnostics.strict_identity_metrics_available
        ),
        "strict_identity_metrics_reason": (
            diagnostics.strict_identity_metrics_reason
        ),
        "scored_mapping_count": diagnostics.scored_mapping_count,
        "blocking_mapping_count": diagnostics.blocking_mapping_count,
        "multi_truth_track_frame_count": diagnostics.root_cause_counts.get(
            "persisted_multi_truth_track_frame",
            0,
        ),
        "truth_sidecar_label_absent_count": (
            diagnostics.root_cause_counts.get(
                "truth_sidecar_label_absent",
                0,
            )
        ),
        "blocker_interval_count": len(diagnostics.blocker_intervals),
        "partial_evaluable_mapping_count": (
            0 if partial is None else partial.evaluable_mapping_count
        ),
        "partial_scored_mapping_count": (
            0 if partial is None else partial.scored_mapping_count
        ),
        "partial_evaluable_frame_count": (
            0 if partial is None else partial.evaluable_frame_count
        ),
        "partial_evaluated_frame_count": (
            0 if partial is None else partial.evaluated_frame_count
        ),
        "partial_evaluable_transition_count": (
            0 if partial is None else partial.evaluable_transition_count
        ),
        "partial_transition_opportunity_count": (
            0 if partial is None else partial.transition_opportunity_count
        ),
        "partial_id_switch_lower_bound": (
            None if partial is None else partial.id_switch_lower_bound
        ),
        "partial_lower_bound_anchor_transition_count": (
            0
            if partial is None
            else partial.lower_bound_anchor_transition_count
        ),
        "d1_estimate_record_count": int(
            d1_audit["estimate_record_count"]
        ),
        "d1_candidate_mapping_count": int(
            d1_audit["available_candidate_mapping_count"]
        ),
        "d1_unresolved_observation_count": int(
            d1_audit["unresolved_observation_count"]
        ),
        "d1_consumable": bool(d1_audit["d1_consumable"]),
        "d1_reason": d1_audit["reason"],
    }


def _aggregate(
    rows: list[dict[str, Any]],
    payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    blocking_reason_counts: Counter[str] = Counter()
    root_cause_counts: Counter[str] = Counter()
    d1_reason_counts: Counter[str] = Counter()
    affected_track_keys: set[tuple[str, str]] = set()
    affected_track_keys_by_reason: dict[
        str,
        set[tuple[str, str]],
    ] = {}
    interval_reason_counts: Counter[str] = Counter()
    representative_multi_truth_intervals: list[dict[str, Any]] = []
    seed_by_episode = {
        str(row["episode_id"]): int(row["seed"]) for row in rows
    }
    for payload in payloads:
        blocking_reason_counts.update(payload["blocking_reason_counts"])
        root_cause_counts.update(payload["root_cause_counts"])
        for interval in payload["blocker_intervals"]:
            interval_reason_counts[str(interval["reason"])] += 1
            affected_track_keys.add(
                (
                    str(payload["episode_id"]),
                    str(interval["global_track_id"]),
                )
            )
            affected_track_keys_by_reason.setdefault(
                str(interval["reason"]),
                set(),
            ).add(
                (
                    str(payload["episode_id"]),
                    str(interval["global_track_id"]),
                )
            )
            if (
                interval["reason"]
                == "multiple_truth_targets_for_global_track"
                and len(representative_multi_truth_intervals) < 5
            ):
                first_frame = interval["frames"][0]
                representative_multi_truth_intervals.append(
                    {
                        "seed": seed_by_episode[str(payload["episode_id"])],
                        "episode_id": str(payload["episode_id"]),
                        "global_track_id": str(
                            interval["global_track_id"]
                        ),
                        "start_frame_index": int(
                            interval["start_frame_index"]
                        ),
                        "end_frame_index": int(
                            interval["end_frame_index"]
                        ),
                        "start_frame_timestamp": float(
                            interval["start_frame_timestamp"]
                        ),
                        "end_frame_timestamp": float(
                            interval["end_frame_timestamp"]
                        ),
                        "candidate_truth_target_ids": list(
                            interval["candidate_truth_target_ids"]
                        ),
                        "first_frame_source_observations": [
                            {
                                "observation_id": str(
                                    observation["observation_id"]
                                ),
                                "measurement_timestamp": float(
                                    observation[
                                        "measurement_timestamp"
                                    ]
                                ),
                                "truth_target_ids": list(
                                    observation["truth_target_ids"]
                                ),
                            }
                            for observation in first_frame[
                                "source_observations"
                            ]
                        ],
                    }
                )
        d1_audit = payload.get("d1_lineage_mapping_audit") or {}
        d1_reason_counts.update(d1_audit.get("unresolved_reason_counts", {}))

    lower_bound_rows = [
        row
        for row in rows
        if row["partial_id_switch_lower_bound"] is not None
    ]
    mapping_numerator = sum(
        int(row["partial_evaluable_mapping_count"]) for row in rows
    )
    mapping_denominator = sum(
        int(row["partial_scored_mapping_count"]) for row in rows
    )
    frame_numerator = sum(
        int(row["partial_evaluable_frame_count"]) for row in rows
    )
    frame_denominator = sum(
        int(row["partial_evaluated_frame_count"]) for row in rows
    )
    transition_numerator = sum(
        int(row["partial_evaluable_transition_count"]) for row in rows
    )
    transition_denominator = sum(
        int(row["partial_transition_opportunity_count"]) for row in rows
    )
    return {
        "schema_version": AGGREGATE_SCHEMA_VERSION,
        "validation_date": "2026-07-23",
        "scenario": "nominal_200v200",
        "duration_seconds": 10.0,
        "episode_count": len(rows),
        "seeds": [int(row["seed"]) for row in rows],
        "producer_replay_verified_count": sum(
            bool(row["producer_replay_verified"]) for row in rows
        ),
        "source_sha256_verified_count": sum(
            bool(row["source_sha256_verified"]) for row in rows
        ),
        "online_truth_isolation_verified_count": sum(
            bool(row["online_truth_isolation_verified"]) for row in rows
        ),
        "strict_identity_metrics_available_count": sum(
            bool(row["strict_identity_metrics_available"]) for row in rows
        ),
        "strict_identity_metrics_unavailable_reason_counts": dict(
            Counter(
                str(row["strict_identity_metrics_reason"])
                for row in rows
                if not row["strict_identity_metrics_available"]
            )
        ),
        "blocking_mapping_count": sum(
            int(row["blocking_mapping_count"]) for row in rows
        ),
        "blocking_reason_counts": dict(sorted(blocking_reason_counts.items())),
        "root_cause_counts": dict(sorted(root_cause_counts.items())),
        "blocker_interval_count": sum(
            int(row["blocker_interval_count"]) for row in rows
        ),
        "blocker_interval_reason_counts": dict(
            sorted(interval_reason_counts.items())
        ),
        "affected_episode_track_count": len(affected_track_keys),
        "affected_episode_track_count_by_reason": {
            reason: len(track_keys)
            for reason, track_keys in sorted(
                affected_track_keys_by_reason.items()
            )
        },
        "representative_multi_truth_intervals": (
            representative_multi_truth_intervals
        ),
        "partial_identity": {
            "evaluable_mapping_count": mapping_numerator,
            "scored_mapping_count": mapping_denominator,
            "evaluable_mapping_coverage": _ratio(
                mapping_numerator,
                mapping_denominator,
            ),
            "evaluable_frame_count": frame_numerator,
            "evaluated_frame_count": frame_denominator,
            "evaluable_frame_coverage": _ratio(
                frame_numerator,
                frame_denominator,
            ),
            "evaluable_transition_count": transition_numerator,
            "transition_opportunity_count": transition_denominator,
            "evaluable_transition_coverage": _ratio(
                transition_numerator,
                transition_denominator,
            ),
            "id_switch_lower_bound_available_episode_count": len(
                lower_bound_rows
            ),
            "id_switch_lower_bound_sum": sum(
                int(row["partial_id_switch_lower_bound"])
                for row in lower_bound_rows
            ),
            "lower_bound_anchor_transition_count": sum(
                int(row["partial_lower_bound_anchor_transition_count"])
                for row in rows
            ),
            "strict_value_backfilled": False,
            "upper_bound_emitted": False,
        },
        "d1_lineage_mapping": {
            "estimate_record_count": sum(
                int(row["d1_estimate_record_count"]) for row in rows
            ),
            "available_candidate_mapping_count": sum(
                int(row["d1_candidate_mapping_count"]) for row in rows
            ),
            "unresolved_observation_count": sum(
                int(row["d1_unresolved_observation_count"]) for row in rows
            ),
            "consumable_episode_count": sum(
                bool(row["d1_consumable"]) for row in rows
            ),
            "unresolved_reason_counts": dict(
                sorted(d1_reason_counts.items())
            ),
            "mapping_records_emitted": False,
        },
        "conclusion": {
            "primary_blocker": "persisted_multi_truth_track_frame",
            "secondary_blocker": "truth_sidecar_label_absent",
            "evaluator_denominator_reclassified": False,
            "online_tracker_modified": False,
            "global_track_id_modified": False,
        },
        "episodes": rows,
    }


def _write_report(
    path: Path,
    aggregate: dict[str, Any],
    *,
    aggregate_sha: str,
    csv_sha: str,
) -> str:
    roots = aggregate["root_cause_counts"]
    partial = aggregate["partial_identity"]
    d1 = aggregate["d1_lineage_mapping"]
    intervals = aggregate["blocker_interval_reason_counts"]
    affected_by_reason = aggregate[
        "affected_episode_track_count_by_reason"
    ]
    lines = [
        "# D2 200 对 200 严格身份指标阻断复核",
        "",
        "## 结论",
        "",
        (
            f"2026-07-23 对 nominal 200v200、10 秒、seed "
            f"{aggregate['seeds'][0]}-{aggregate['seeds'][-1]} 的 "
            f"{aggregate['episode_count']} 个 producer 制品完成重放。"
            f"来源哈希、在线真值隔离和重建结果均为 "
            f"{aggregate['producer_replay_verified_count']}/"
            f"{aggregate['episode_count']} 通过。"
        ),
        "",
        (
            "严格身份切换指标仍不可用。主要原因是持久化谱系中存在 "
            f"{roots.get('persisted_multi_truth_track_frame', 0)} 个"
            "同一全局航迹帧对应多个真实目标的记录；另有 "
            f"{roots.get('truth_sidecar_label_absent', 0)} 个受评分映射"
            "缺少显式真值或非目标标签。两类问题都来自输入证据，"
            "不能通过改变分母或选择多数观测修正。"
        ),
        "",
        "## 证据",
        "",
        "| 项目 | 结果 |",
        "| --- | ---: |",
        (
            "| producer 重放与持久化结果一致 | "
            f"{aggregate['producer_replay_verified_count']}/"
            f"{aggregate['episode_count']} |"
        ),
        (
            "| 来源 SHA-256 校验通过 | "
            f"{aggregate['source_sha256_verified_count']}/"
            f"{aggregate['episode_count']} |"
        ),
        (
            "| 在线真值隔离通过 | "
            f"{aggregate['online_truth_isolation_verified_count']}/"
            f"{aggregate['episode_count']} |"
        ),
        (
            "| 严格身份指标可用 | "
            f"{aggregate['strict_identity_metrics_available_count']}/"
            f"{aggregate['episode_count']} |"
        ),
        (
            "| 多真值混入同一航迹帧 | "
            f"{roots.get('persisted_multi_truth_track_frame', 0)} |"
        ),
        (
            "| 缺少显式 sidecar 标签的受评分映射 | "
            f"{roots.get('truth_sidecar_label_absent', 0)} |"
        ),
        (
            "| 受影响的 episode/航迹组合 | "
            f"{aggregate['affected_episode_track_count']} |"
        ),
        (
            "| 多真值连续时间段 | "
            f"{intervals.get('multiple_truth_targets_for_global_track', 0)} |"
        ),
        (
            "| 多真值涉及的 episode/航迹组合 | "
            f"{affected_by_reason.get('multiple_truth_targets_for_global_track', 0)} |"
        ),
        (
            "| 缺标签连续时间段 | "
            f"{intervals.get('truth_label_missing', 0)} |"
        ),
        (
            "| 缺标签涉及的 episode/航迹组合 | "
            f"{affected_by_reason.get('truth_label_missing', 0)} |"
        ),
        "",
        "每个连续时间段记录全局航迹号、起止帧、起止时刻、候选真值、"
        "观测号、量测时刻和谱系哈希。明细保存在逐 episode 诊断 JSON 中，"
        "可回到冻结的 D1/D2 记录和独立真值标签逐条复核。",
        "",
        "## 代表性混轨",
        "",
        *[
            (
                f"- seed {item['seed']}，`{item['global_track_id']}`，"
                f"帧 {item['start_frame_index']}-"
                f"{item['end_frame_index']}，候选真值 "
                f"`{' / '.join(item['candidate_truth_target_ids'])}`；"
                "首帧证据为 "
                + "、".join(
                    (
                        f"`{observation['observation_id']}`"
                        f" -> `{'/'.join(observation['truth_target_ids'])}`"
                    )
                    for observation in item[
                        "first_frame_source_observations"
                    ]
                )
                + "。"
            )
            for item in aggregate[
                "representative_multi_truth_intervals"
            ]
        ],
        "",
        "## 部分身份诊断",
        "",
        "| 项目 | 数值 |",
        "| --- | ---: |",
        (
            "| mapping coverage | "
            f"{partial['evaluable_mapping_count']}/"
            f"{partial['scored_mapping_count']} = "
            f"{partial['evaluable_mapping_coverage']:.4%} |"
        ),
        (
            "| 完整帧 coverage | "
            f"{partial['evaluable_frame_count']}/"
            f"{partial['evaluated_frame_count']} = "
            f"{partial['evaluable_frame_coverage']:.4%} |"
        ),
        (
            "| 相邻转换 coverage | "
            f"{partial['evaluable_transition_count']}/"
            f"{partial['transition_opportunity_count']} = "
            f"{partial['evaluable_transition_coverage']:.4%} |"
        ),
        (
            "| 保守身份切换下界 | "
            f"{partial['id_switch_lower_bound_sum']}/"
            f"{partial['lower_bound_anchor_transition_count']} "
            "anchor intervals |"
        ),
        "",
        "部分下界没有回填为严格身份切换值，也没有生成上界。完整帧和相邻"
        "转换覆盖率低，说明当前证据只适合定位问题，不能替代严格连续性评分。",
        "",
        "## D1 映射检查",
        "",
        (
            f"D1 一致性证据含 {d1['estimate_record_count']} 条可用估计。"
            f"D2 谱系和独立标签可形成 {d1['available_candidate_mapping_count']} "
            f"条唯一候选，仍有 {d1['unresolved_observation_count']} 条观测"
            "不能形成完整映射。"
        ),
        "",
        (
            "本批未解决原因计数为："
            + "、".join(
                f"`{reason}` {count}"
                for reason, count in d1[
                    "unresolved_reason_counts"
                ].items()
            )
            + "。"
        ),
        "",
        (
            f"{aggregate['episode_count']} 个 episode 中 D1 可直接消费的完整 "
            "`d2_lineage_mapping` 为 "
            f"{d1['consumable_episode_count']} 个。诊断器在覆盖不完整时不输出"
            "映射记录，因此本轮没有生成会被误用的部分 sidecar。"
        ),
        "",
        "## 最小上游修复",
        "",
        "1. D1 在雷达与视觉更新进入同一融合航迹前增加跨模态一致性门控。"
        "门控拒绝后应分裂或保留独立航迹，并继续携带当前量测的观测谱系。"
        "本报告中的多真值时间段可直接作为回归样本。",
        "",
        "2. 传感器离线标签 producer 为每条观测写入显式处置：真实目标、"
        "已知虚警或标签未知。sidecar 同时声明观测全集摘要和完整性摘要。"
        "评估器不得通过观测名称推断虚警。",
        "",
        "3. main 在生成 D1 映射前检查每条可用 D1 估计是否具有唯一的"
        "观测号、量测时刻、D2 全局航迹声明和真值标签。完整覆盖后再调用"
        "D1 sidecar builder；不完整场景继续输出 availability 和缺口计数。",
        "",
        "4. D2 严格身份指标保持现行全时序唯一映射要求。D1 若需要部分"
        "误差统计，应由 D1 单独定义带覆盖率的部分指标，不能借用或覆盖"
        "D2 的严格身份切换结果。",
        "",
        "## 制品",
        "",
        f"- 聚合 JSON：`identity_blocker_aggregate.json`，{aggregate_sha}",
        f"- 逐 seed CSV：`identity_blocker_per_seed.csv`，{csv_sha}",
        "- 逐 episode 明细：`episodes/*_identity_blockers.json`",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return sha256_file(path)


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return sha256_file(path)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return sha256_file(path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else numerator / denominator


if __name__ == "__main__":
    main()
