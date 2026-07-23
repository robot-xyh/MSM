"""Cross-build semantic equivalence audit for persisted scalable 3D episodes."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

import numpy as np


CROSS_BUILD_EQUIVALENCE_SCHEMA_VERSION = (
    "scalable3d-cross-build-semantic-equivalence-v1"
)
_PLAN_TOPIC = "modules.d3.assignment_plan"
_D1_TOPIC = "modules.d1.fused_tracks"
_D4_DECISION_TOPIC = "modules.d4.regional_failover"
_D4_ADVICE_TOPIC = "modules.d4.region_resource_advice"
_D7_TOPIC = "modules.d7.guidance_commands"
_ACK_TOPIC = "runtime.assignment_plan_ack"
_ADVISORY_ID_PATTERN = re.compile(r"^d4-rr-advisory-[0-9a-f]{64}$")
_SUMMARY_CONTRACT_FIELDS = (
    "scenario_name",
    "scenario_version",
    "seed",
    "target_count",
    "resource_count",
    "recon_count",
    "simulated_duration_s",
    "physics_step_count",
    "finite_state",
    "online_truth_use_count",
    "online_observation_count",
    "online_batch_count",
    "radar_observation_count",
    "acoustic_observation_count",
    "visual_observation_count",
    "module_publication_count",
    "module_publication_topic_counts",
    "assignment_plan_ack_count",
    "assignment_plan_binding_ack_count",
    "assignment_plan_control_applied_count",
    "assignment_plan_hold_count",
    "camera_command_ack_count",
    "camera_command_applied_count",
    "camera_command_issued_count",
    "camera_command_rejected_count",
    "camera_command_rejection_reason_counts",
    "intercepted_target_count",
)
_MODULE_FINAL_COUNT_FIELDS = (
    "d1_track_count",
    "d2_track_count",
    "d3_assignment_count",
    "d5_binding_count",
    "d7_command_count",
)


def compare_cross_build_episodes(
    reference_episode_dir: str | Path,
    candidate_episode_dir: str | Path,
    *,
    mismatch_limit: int = 20,
) -> dict[str, Any]:
    """Compare same-input episodes while preserving lineage relationships.

    D3 creates fresh opaque plan identifiers for independent planner instances. The
    audit maps each first-seen plan identity to its lineage occurrence, then keeps
    plan versions and all references intact. Hashes derived from raw plan payloads
    are normalized only after their in-run source bindings have been verified.
    """

    if mismatch_limit < 1:
        raise ValueError("mismatch_limit must be positive")
    reference = _load_episode(Path(reference_episode_dir))
    candidate = _load_episode(Path(candidate_episode_dir))
    comparability = _comparability(reference, candidate)

    reference_audit = _audit_online_stream(reference["root"])
    candidate_audit = _audit_online_stream(candidate["root"])
    online = _compare_online_streams(
        reference["root"],
        candidate["root"],
        reference_audit,
        candidate_audit,
        mismatch_limit=mismatch_limit,
    )
    truth = _compare_truth_artifacts(reference["root"], candidate["root"])
    summary_contract_equal = (
        reference["summary_contract"] == candidate["summary_contract"]
    )
    checks = {
        **comparability,
        "summary_contract_equal": summary_contract_equal,
        "truth_state_equal": truth["truth_state_equal"],
        "truth_labels_semantically_equal": truth[
            "truth_labels_semantically_equal"
        ],
        "proximity_events_semantically_equal": truth[
            "proximity_events_semantically_equal"
        ],
        "online_record_count_equal": online["record_count_equal"],
        "online_topic_counts_equal": online["topic_counts_equal"],
        "plan_lineage_pattern_equal": online["plan_lineage_pattern_equal"],
        "reference_plan_lineage_valid": reference_audit["plan_lineage_valid"],
        "candidate_plan_lineage_valid": candidate_audit["plan_lineage_valid"],
        "ack_source_integrity": (
            reference_audit["ack_source_integrity"]
            and candidate_audit["ack_source_integrity"]
        ),
        "d4_content_address_integrity": (
            reference_audit["d4_content_address_integrity"]
            and candidate_audit["d4_content_address_integrity"]
        ),
        "normalized_online_payloads_equal": online[
            "normalized_online_payloads_equal"
        ],
    }
    return {
        "schema_version": CROSS_BUILD_EQUIVALENCE_SCHEMA_VERSION,
        "evidence_class": "descriptive_clean_source_cross_build_audit",
        "reference": _episode_descriptor(reference),
        "candidate": _episode_descriptor(candidate),
        "checks": checks,
        "passed": all(checks.values()),
        "truth_artifacts": truth,
        "online_bus": online,
        "allowed_performance_diagnostics": {
            "d1_association_innovation_solve_count": {
                "reference_total": reference_audit[
                    "d1_association_innovation_solve_count"
                ],
                "candidate_total": candidate_audit[
                    "d1_association_innovation_solve_count"
                ],
                "semantic_status": "reported_not_compared",
            }
        },
        "summary_contract": {
            "equal": summary_contract_equal,
            "reference_sha256": _canonical_sha256(reference["summary_contract"]),
            "candidate_sha256": _canonical_sha256(candidate["summary_contract"]),
        },
    }


def render_cross_build_equivalence_markdown(report: Mapping[str, Any]) -> str:
    """Render a concise Chinese audit report."""

    reference = report["reference"]
    candidate = report["candidate"]
    online = report["online_bus"]
    diagnostic = report["allowed_performance_diagnostics"][
        "d1_association_innovation_solve_count"
    ]
    lines = [
        "# 三维跨提交语义等价审计",
        "",
        "## 结论",
        "",
        (
            f"参考提交 `{reference['git_commit'][:12]}` 与候选提交 "
            f"`{candidate['git_commit'][:12]}` 的同 seed、同配置 episode "
            f"语义等价审计{'通过' if report['passed'] else '未通过'}。"
        ),
        (
            f"在线总线各含 {online['reference_record_count']} 条记录。"
            f"D3 的不透明计划编号按首次出现顺序归一化，计划版本、前序关系、"
            f"owner、联盟和下游引用仍参与逐条比较。"
        ),
        (
            "D4 的 authority、正式裁决和 advisory 内容地址先在原始记录中校验，"
            "再按规范计划谱系重新计算；无法回算时审计失败关闭。"
        ),
        "",
        "## 审计条件",
        "",
        "| 项目 | 参考 | 候选 |",
        "| --- | --- | --- |",
        f"| Git 提交 | `{reference['git_commit']}` | `{candidate['git_commit']}` |",
        f"| seed | {reference['seed']} | {candidate['seed']} |",
        f"| 场景 | `{reference['scenario_version']}` | `{candidate['scenario_version']}` |",
        f"| 仿真时长/s | {reference['duration_s']:.3f} | {candidate['duration_s']:.3f} |",
        f"| 来源工作区干净 | {str(reference['repository_dirty']).lower() == 'false'} | {str(candidate['repository_dirty']).lower() == 'false'} |",
        "",
        "## 核心检查",
        "",
        "| 检查 | 结果 |",
        "| --- | :---: |",
    ]
    for name, value in report["checks"].items():
        lines.append(f"| `{name}` | {'通过' if value else '失败'} |")
    lines.extend(
        [
            "",
            "## 允许变化的性能诊断",
            "",
            (
                "D1 实际创新求解次数由 "
                f"{diagnostic['reference_total']} 降至 "
                f"{diagnostic['candidate_total']}。该字段用于描述执行成本，"
                "不参与业务等价判定。"
            ),
            "",
            "## 逐主题摘要",
            "",
            "| 主题 | 记录数 | 规范哈希一致 |",
            "| --- | ---: | :---: |",
        ]
    )
    for topic, item in sorted(online["topics"].items()):
        lines.append(
            f"| `{topic}` | {item['reference_count']} | "
            f"{'是' if item['normalized_sha256_equal'] else '否'} |"
        )
    if online["mismatches"]:
        lines.extend(["", "## 首批差异", ""])
        for item in online["mismatches"]:
            lines.append(
                f"- 记录 {item['record_index']}，主题 `{item['topic']}`，"
                f"路径 `{item['path']}`。"
            )
    return "\n".join(lines) + "\n"


def write_cross_build_equivalence_bundle(
    output_dir: str | Path,
    report: Mapping[str, Any],
) -> dict[str, Path]:
    """Persist JSON and Chinese Markdown evidence."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "cross_build_semantic_equivalence.json"
    markdown_path = root / "CROSS_BUILD_SEMANTIC_EQUIVALENCE_CN.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_cross_build_equivalence_markdown(report), encoding="utf-8"
    )
    return {"json": json_path, "markdown": markdown_path}


def _load_episode(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest = _load_mapping(root / "manifest.json")
    scenario = _load_mapping(root / "scenario_config.json")
    summary = _load_mapping(root / "summary.json")
    required_files = (
        "online_observations.jsonl",
        "offline_truth_labels.jsonl",
        "offline_truth_state.npz",
        "offline_proximity_intercepts.jsonl",
    )
    for name in required_files:
        if not (root / name).is_file():
            raise FileNotFoundError(f"required episode artifact is missing: {root / name}")
    diagnostics = _mapping(summary.get("module_final_diagnostics", {}))
    summary_contract = {name: summary.get(name) for name in _SUMMARY_CONTRACT_FIELDS}
    summary_contract["module_final_counts"] = {
        name: diagnostics.get(name) for name in _MODULE_FINAL_COUNT_FIELDS
    }
    return {
        "root": root,
        "manifest": manifest,
        "scenario": scenario,
        "summary": summary,
        "summary_contract": summary_contract,
    }


def _episode_descriptor(episode: Mapping[str, Any]) -> dict[str, Any]:
    manifest = episode["manifest"]
    summary = episode["summary"]
    return {
        "episode_dir": str(episode["root"]),
        "episode_id": str(summary.get("episode_id", manifest.get("episode_id", ""))),
        "git_commit": str(manifest.get("git_commit", "")),
        "repository_dirty": bool(manifest.get("repository_dirty")),
        "scenario_version": str(summary.get("scenario_version", "")),
        "seed": int(summary.get("seed")),
        "duration_s": float(summary.get("simulated_duration_s")),
    }


def _comparability(
    reference: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, bool]:
    ref_descriptor = _episode_descriptor(reference)
    cand_descriptor = _episode_descriptor(candidate)
    return {
        "reference_source_clean": not ref_descriptor["repository_dirty"],
        "candidate_source_clean": not cand_descriptor["repository_dirty"],
        "same_seed": ref_descriptor["seed"] == cand_descriptor["seed"],
        "same_scenario_version": (
            ref_descriptor["scenario_version"] == cand_descriptor["scenario_version"]
        ),
        "same_duration": ref_descriptor["duration_s"] == cand_descriptor["duration_s"],
        "same_scenario_config": (
            _canonical_sha256(reference["scenario"])
            == _canonical_sha256(candidate["scenario"])
        ),
    }


def _audit_online_stream(root: Path) -> dict[str, Any]:
    path = root / "online_observations.jsonl"
    plan_map: dict[str, str] = {}
    plan_pattern: list[dict[str, Any]] = []
    plan_versions: dict[str, int] = {}
    current_plan_token: str | None = None
    current_plan_version: int | None = None
    plan_lineage_valid = True
    source_payloads: dict[int, Mapping[str, Any]] = {}
    topic_counts: Counter[str] = Counter()
    d1_solve_total = 0
    ack_count = 0
    d4_advice_count = 0
    latest_d4_decision: tuple[float, Mapping[str, Any]] | None = None
    with path.open("r", encoding="utf-8") as stream:
        for record_index, line in enumerate(stream, start=1):
            record = _parse_record(line, path, record_index)
            sequence = _required_int(record.get("sequence"), "record sequence")
            topic = str(record.get("topic", ""))
            payload = _mapping(record.get("payload"))
            topic_counts[topic] += 1
            if topic in {_PLAN_TOPIC, _D7_TOPIC}:
                source_payloads[sequence] = payload
            if topic == _PLAN_TOPIC:
                raw_plan_id = _required_text(payload.get("plan_id"), "D3 plan_id")
                plan_version = _required_int(
                    payload.get("plan_version"), "D3 plan_version"
                )
                if raw_plan_id not in plan_map:
                    plan_map[raw_plan_id] = f"PLAN@{len(plan_map) + 1:04d}"
                    expected_version = (
                        1 if current_plan_version is None else current_plan_version + 1
                    )
                    if plan_version != expected_version:
                        plan_lineage_valid = False
                    current_plan_token = plan_map[raw_plan_id]
                    current_plan_version = plan_version
                    plan_versions[current_plan_token] = plan_version
                else:
                    token = plan_map[raw_plan_id]
                    if (
                        token != current_plan_token
                        or plan_versions.get(token) != plan_version
                    ):
                        plan_lineage_valid = False
                plan_pattern.append(
                    {
                        "token": plan_map[raw_plan_id],
                        "plan_version": plan_version,
                    }
                )
            elif topic == _D1_TOPIC:
                summary = _mapping(payload.get("summary", {}))
                value = summary.get("association_innovation_solve_count")
                if value is not None:
                    d1_solve_total += _required_int(
                        value, "association_innovation_solve_count"
                    )
            elif topic == _D4_DECISION_TOPIC:
                latest_d4_decision = (
                    _required_float(record.get("timestamp"), "D4 decision timestamp"),
                    payload,
                )
            elif topic == _D4_ADVICE_TOPIC:
                if latest_d4_decision is None:
                    raise ValueError(
                        "D4 advice has no preceding formal decision publication"
                    )
                advice_timestamp = _required_float(
                    record.get("timestamp"), "D4 advice timestamp"
                )
                decision_timestamp, decision_payload = latest_d4_decision
                if abs(advice_timestamp - decision_timestamp) > 1.0e-9:
                    raise ValueError(
                        "D4 advice is not bound to the same-timestamp formal decision"
                    )
                _validate_d4_advice_integrity(payload, decision_payload)
                d4_advice_count += 1
            elif topic == _ACK_TOPIC:
                _verify_ack_source_hashes(payload, source_payloads)
                ack_count += 1
    return {
        "record_count": sum(topic_counts.values()),
        "topic_counts": dict(sorted(topic_counts.items())),
        "plan_map": plan_map,
        "plan_pattern": plan_pattern,
        "plan_lineage_valid": plan_lineage_valid,
        "lineage_relation_source": (
            "derived_from_contiguous_publication_order"
        ),
        "ack_count": ack_count,
        "ack_source_integrity": True,
        "d4_advice_count": d4_advice_count,
        "d4_content_address_integrity": True,
        "d1_association_innovation_solve_count": d1_solve_total,
    }


def _compare_online_streams(
    reference_root: Path,
    candidate_root: Path,
    reference_audit: Mapping[str, Any],
    candidate_audit: Mapping[str, Any],
    *,
    mismatch_limit: int,
) -> dict[str, Any]:
    reference_path = reference_root / "online_observations.jsonl"
    candidate_path = candidate_root / "online_observations.jsonl"
    reference_hashes: dict[str, Any] = {}
    candidate_hashes: dict[str, Any] = {}
    mismatches: list[dict[str, Any]] = []
    reference_count = 0
    candidate_count = 0
    reference_normalization_state: dict[str, Any] = {}
    candidate_normalization_state: dict[str, Any] = {}
    with reference_path.open("r", encoding="utf-8") as reference_stream, (
        candidate_path.open("r", encoding="utf-8")
    ) as candidate_stream:
        record_index = 0
        while True:
            reference_line = reference_stream.readline()
            candidate_line = candidate_stream.readline()
            if not reference_line and not candidate_line:
                break
            record_index += 1
            if reference_line:
                reference_count += 1
            if candidate_line:
                candidate_count += 1
            if not reference_line or not candidate_line:
                if len(mismatches) < mismatch_limit:
                    mismatches.append(
                        {
                            "record_index": record_index,
                            "topic": "stream_length",
                            "path": "$",
                        }
                    )
                continue
            reference_record = _parse_record(
                reference_line, reference_path, record_index
            )
            candidate_record = _parse_record(candidate_line, candidate_path, record_index)
            reference_normalized = _normalize_record(
                reference_record,
                reference_audit["plan_map"],
                state=reference_normalization_state,
            )
            candidate_normalized = _normalize_record(
                candidate_record,
                candidate_audit["plan_map"],
                state=candidate_normalization_state,
            )
            _update_topic_hash(reference_hashes, reference_normalized)
            _update_topic_hash(candidate_hashes, candidate_normalized)
            if reference_normalized != candidate_normalized and len(mismatches) < mismatch_limit:
                topic = str(reference_normalized.get("topic", ""))
                for path in _difference_paths(
                    reference_normalized, candidate_normalized
                ):
                    mismatches.append(
                        {
                            "record_index": record_index,
                            "topic": topic,
                            "path": path,
                        }
                    )
                    if len(mismatches) >= mismatch_limit:
                        break

    topics: dict[str, Any] = {}
    for topic in sorted(set(reference_hashes) | set(candidate_hashes)):
        ref = reference_hashes.get(topic, {})
        cand = candidate_hashes.get(topic, {})
        ref_digest = _finish_topic_hash(ref)
        cand_digest = _finish_topic_hash(cand)
        topics[topic] = {
            "reference_count": int(ref.get("count", 0)),
            "candidate_count": int(cand.get("count", 0)),
            "reference_normalized_sha256": ref_digest,
            "candidate_normalized_sha256": cand_digest,
            "normalized_sha256_equal": ref_digest == cand_digest,
        }
    normalized_equal = not mismatches and all(
        item["normalized_sha256_equal"] for item in topics.values()
    )
    return {
        "reference_record_count": reference_count,
        "candidate_record_count": candidate_count,
        "record_count_equal": reference_count == candidate_count,
        "reference_topic_counts": reference_audit["topic_counts"],
        "candidate_topic_counts": candidate_audit["topic_counts"],
        "topic_counts_equal": (
            reference_audit["topic_counts"] == candidate_audit["topic_counts"]
        ),
        "reference_plan_pattern": reference_audit["plan_pattern"],
        "candidate_plan_pattern": candidate_audit["plan_pattern"],
        "lineage_relation_source": reference_audit["lineage_relation_source"],
        "plan_lineage_pattern_equal": (
            reference_audit["plan_pattern"] == candidate_audit["plan_pattern"]
        ),
        "normalized_online_payloads_equal": normalized_equal,
        "topics": topics,
        "mismatches": mismatches,
    }


def _normalize_record(
    record: Mapping[str, Any],
    plan_map: Mapping[str, str],
    *,
    state: dict[str, Any],
) -> dict[str, Any]:
    normalized = _replace_plan_ids(record, plan_map)
    topic = str(normalized.get("topic", ""))
    payload = _mapping(normalized.get("payload"))
    if topic == _D1_TOPIC:
        summary = payload.get("summary")
        if isinstance(summary, dict) and "association_innovation_solve_count" in summary:
            summary["association_innovation_solve_count"] = (
                "PERFORMANCE_DIAGNOSTIC_REPORTED_SEPARATELY"
            )
    elif topic == _D4_DECISION_TOPIC:
        state["latest_d4_decision"] = (
            _required_float(normalized.get("timestamp"), "D4 decision timestamp"),
            payload,
        )
    elif topic == _D4_ADVICE_TOPIC:
        latest = state.get("latest_d4_decision")
        if latest is None:
            raise ValueError(
                "normalized D4 advice has no preceding formal decision publication"
            )
        advice_timestamp = _required_float(
            normalized.get("timestamp"), "D4 advice timestamp"
        )
        decision_timestamp, decision_payload = latest
        if abs(advice_timestamp - decision_timestamp) > 1.0e-9:
            raise ValueError(
                "normalized D4 advice is not bound to its formal decision"
            )
        _normalize_d4_content_addresses(payload, decision_payload)
    elif topic == _ACK_TOPIC:
        if payload.get("source_plan_payload_sha256") is not None:
            payload["source_plan_payload_sha256"] = "VERIFIED_SOURCE_PLAN_SHA256"
        if payload.get("source_guidance_payload_sha256") is not None:
            payload["source_guidance_payload_sha256"] = (
                "VERIFIED_SOURCE_GUIDANCE_SHA256"
            )
    return normalized


def _normalize_d4_content_addresses(
    payload: Mapping[str, Any],
    formal_decision_payload: Mapping[str, Any],
) -> None:
    if not isinstance(payload, dict):
        raise TypeError("D4 payload must be mutable during normalization")
    advisory_contract = _mapping(payload.get("advisory_contract"))
    if not isinstance(advisory_contract, dict):
        raise TypeError("D4 advisory_contract must be mutable")
    authority_digest = _d4_authority_digest(advisory_contract)
    advisory_contract["authority_digest"] = authority_digest
    recommendation = _mapping(payload.get("recommendation"))
    if not isinstance(recommendation, dict):
        raise TypeError("D4 recommendation must be mutable")
    recommendation["authority_digest"] = authority_digest
    regions = advisory_contract.get("regions", ())
    if not isinstance(regions, list):
        raise TypeError("D4 advisory regions must be a list")
    for region in regions:
        region_mapping = _mapping(region)
        source_version = _mapping(region_mapping.get("source_version"))
        if not isinstance(source_version, dict):
            raise TypeError("D4 source_version must be mutable")
        source_version["authority_digest"] = authority_digest
    transfers = advisory_contract.get("transfers", ())
    if not isinstance(transfers, list):
        raise TypeError("D4 advisory transfers must be a list")
    for transfer in transfers:
        transfer_mapping = _mapping(transfer)
        for key in ("source_version", "target_version"):
            source_version = _mapping(transfer_mapping.get(key))
            if not isinstance(source_version, dict):
                raise TypeError("D4 transfer source version must be mutable")
            source_version["authority_digest"] = authority_digest

    decision_digest = _d4_json_sha256(formal_decision_payload)
    payload["formal_decision_digest_before"] = decision_digest
    payload["formal_decision_digest_after"] = decision_digest
    advisory_contract["advisory_id"] = _d4_advisory_id(advisory_contract)
    _validate_d4_advice_integrity(payload, formal_decision_payload)


def _validate_d4_advice_integrity(
    payload: Mapping[str, Any],
    formal_decision_payload: Mapping[str, Any],
) -> None:
    advisory_contract = _mapping(payload.get("advisory_contract"))
    advisory_id = _required_text(
        advisory_contract.get("advisory_id"), "D4 advisory_id"
    )
    if not _ADVISORY_ID_PATTERN.fullmatch(advisory_id):
        raise ValueError("D4 advisory_id does not match the versioned digest format")
    if advisory_id != _d4_advisory_id(advisory_contract):
        raise ValueError("D4 advisory_id does not match advisory content")

    authority_digest = _d4_authority_digest(advisory_contract)
    digest_copies = [
        _required_text(
            advisory_contract.get("authority_digest"),
            "D4 advisory authority_digest",
        )
    ]
    recommendation = _mapping(payload.get("recommendation"))
    digest_copies.append(
        _required_text(
            recommendation.get("authority_digest"),
            "D4 recommendation authority_digest",
        )
    )
    regions = advisory_contract.get("regions")
    if not isinstance(regions, list) or not regions:
        raise ValueError("D4 advisory regions must be a non-empty list")
    for region in regions:
        source_version = _mapping(_mapping(region).get("source_version"))
        digest_copies.append(
            _required_text(
                source_version.get("authority_digest"),
                "D4 region authority_digest",
            )
        )
    transfers = advisory_contract.get("transfers", ())
    if not isinstance(transfers, list):
        raise ValueError("D4 advisory transfers must be a list")
    for transfer in transfers:
        transfer_mapping = _mapping(transfer)
        for key in ("source_version", "target_version"):
            source_version = _mapping(transfer_mapping.get(key))
            digest_copies.append(
                _required_text(
                    source_version.get("authority_digest"),
                    "D4 transfer authority_digest",
                )
            )
    if any(item != authority_digest for item in digest_copies):
        raise ValueError("D4 authority_digest cannot be reconstructed consistently")

    decision_digest = _d4_json_sha256(formal_decision_payload)
    if payload.get("formal_decision_unchanged") is not True:
        raise ValueError("D4 advice altered the formal decision")
    for key in ("formal_decision_digest_before", "formal_decision_digest_after"):
        if _required_text(payload.get(key), f"D4 {key}") != decision_digest:
            raise ValueError(f"D4 {key} does not match the formal decision")


def _d4_authority_digest(advisory_contract: Mapping[str, Any]) -> str:
    regions = advisory_contract.get("regions")
    if not isinstance(regions, list) or not regions:
        raise ValueError("D4 authority reconstruction requires advisory regions")
    authority_payload: list[dict[str, Any]] = []
    for region in regions:
        region_mapping = _mapping(region)
        source = _mapping(region_mapping.get("source_version"))
        authority_payload.append(
            {
                "region_id": _required_text(source.get("region_id"), "D4 region_id"),
                "owner_id": source.get("owner_id"),
                "owner_layer": _required_text(
                    source.get("owner_layer"), "D4 owner_layer"
                ),
                "plan_id": _required_text(source.get("plan_id"), "D4 plan_id"),
                "plan_version": _required_int(
                    source.get("plan_version"), "D4 plan_version"
                ),
                "epoch": _required_int(source.get("epoch"), "D4 epoch"),
                "lease_expires_at_s": _required_float(
                    source.get("lease_expires_at_s"), "D4 lease_expires_at_s"
                ),
                "owner_active": _required_bool(
                    source.get("owner_active"), "D4 owner_active"
                ),
                "coalition_ack_complete": _required_bool(
                    source.get("coalition_ack_complete"),
                    "D4 coalition_ack_complete",
                ),
                "committed_resources": _required_int(
                    region_mapping.get("protected_committed_resources"),
                    "D4 protected_committed_resources",
                ),
                "fault_fenced": _required_bool(
                    source.get("fault_fenced"), "D4 fault_fenced"
                ),
                "fault_fence_epoch": source.get("fault_fence_epoch"),
            }
        )
    authority_payload.sort(key=lambda item: item["region_id"])
    return _d4_json_sha256(authority_payload)


def _d4_advisory_id(advisory_contract: Mapping[str, Any]) -> str:
    unhashed = dict(advisory_contract)
    unhashed.pop("advisory_id", None)
    return f"d4-rr-advisory-{_d4_json_sha256(unhashed)}"


def _d4_json_sha256(value: Any) -> str:
    serialized = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def _verify_ack_source_hashes(
    payload: Mapping[str, Any], source_payloads: Mapping[int, Mapping[str, Any]]
) -> None:
    plan_sequence = _required_int(
        payload.get("source_plan_bus_sequence"), "ACK source plan sequence"
    )
    plan_payload = source_payloads.get(plan_sequence)
    if plan_payload is None:
        raise ValueError("ACK source plan sequence is absent from the online stream")
    if _canonical_sha256(plan_payload) != _required_text(
        payload.get("source_plan_payload_sha256"), "ACK source plan SHA256"
    ):
        raise ValueError("ACK source plan payload SHA256 mismatch")
    guidance_sequence = payload.get("source_guidance_bus_sequence")
    guidance_digest = payload.get("source_guidance_payload_sha256")
    if guidance_sequence is None:
        if guidance_digest is not None:
            raise ValueError("ACK guidance SHA256 exists without a source sequence")
        return
    guidance_payload = source_payloads.get(
        _required_int(guidance_sequence, "ACK source guidance sequence")
    )
    if guidance_payload is None:
        raise ValueError("ACK source guidance sequence is absent from the online stream")
    if _canonical_sha256(guidance_payload) != _required_text(
        guidance_digest, "ACK source guidance SHA256"
    ):
        raise ValueError("ACK source guidance payload SHA256 mismatch")


def _compare_truth_artifacts(
    reference_root: Path, candidate_root: Path
) -> dict[str, Any]:
    reference_state = reference_root / "offline_truth_state.npz"
    candidate_state = candidate_root / "offline_truth_state.npz"
    state_equal, state_keys = _npz_equal(reference_state, candidate_state)
    reference_labels = _semantic_jsonl_sha256(
        reference_root / "offline_truth_labels.jsonl"
    )
    candidate_labels = _semantic_jsonl_sha256(
        candidate_root / "offline_truth_labels.jsonl"
    )
    reference_proximity = _semantic_jsonl_sha256(
        reference_root / "offline_proximity_intercepts.jsonl"
    )
    candidate_proximity = _semantic_jsonl_sha256(
        candidate_root / "offline_proximity_intercepts.jsonl"
    )
    return {
        "truth_state_equal": state_equal,
        "truth_state_array_keys": state_keys,
        "reference_truth_state_file_sha256": _file_sha256(reference_state),
        "candidate_truth_state_file_sha256": _file_sha256(candidate_state),
        "reference_truth_labels_semantic_sha256": reference_labels,
        "candidate_truth_labels_semantic_sha256": candidate_labels,
        "truth_labels_semantically_equal": reference_labels == candidate_labels,
        "reference_proximity_events_semantic_sha256": reference_proximity,
        "candidate_proximity_events_semantic_sha256": candidate_proximity,
        "proximity_events_semantically_equal": (
            reference_proximity == candidate_proximity
        ),
    }


def _npz_equal(reference: Path, candidate: Path) -> tuple[bool, list[str]]:
    with np.load(reference, allow_pickle=False) as reference_data, np.load(
        candidate, allow_pickle=False
    ) as candidate_data:
        reference_keys = sorted(reference_data.files)
        candidate_keys = sorted(candidate_data.files)
        if reference_keys != candidate_keys:
            return False, sorted(set(reference_keys) | set(candidate_keys))
        equal = all(
            _array_equal(reference_data[key], candidate_data[key])
            for key in reference_keys
        )
        return equal, reference_keys


def _array_equal(reference: np.ndarray, candidate: np.ndarray) -> bool:
    if reference.dtype.kind in {"f", "c"} and candidate.dtype.kind in {"f", "c"}:
        return bool(np.array_equal(reference, candidate, equal_nan=True))
    return bool(np.array_equal(reference, candidate))


def _semantic_jsonl_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("r", encoding="utf-8") as stream:
        for record_index, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            digest.update(_canonical_json_bytes(value))
            digest.update(b"\n")
    return digest.hexdigest()


def _replace_plan_ids(value: Any, plan_map: Mapping[str, str]) -> Any:
    replacements = sorted(plan_map.items(), key=lambda item: len(item[0]), reverse=True)

    def replace(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {str(key): replace(child) for key, child in item.items()}
        if isinstance(item, list):
            return [replace(child) for child in item]
        if isinstance(item, tuple):
            return [replace(child) for child in item]
        if isinstance(item, str):
            for raw, token in replacements:
                item = item.replace(raw, token)
        return item

    return replace(value)


def _update_topic_hash(topic_hashes: dict[str, Any], record: Mapping[str, Any]) -> None:
    topic = str(record.get("topic", ""))
    item = topic_hashes.setdefault(topic, {"count": 0, "digest": sha256()})
    item["count"] += 1
    item["digest"].update(_canonical_json_bytes(record))
    item["digest"].update(b"\n")


def _finish_topic_hash(item: Mapping[str, Any]) -> str | None:
    digest = item.get("digest")
    return None if digest is None else digest.hexdigest()


def _difference_paths(reference: Any, candidate: Any, path: str = "$") -> Iterable[str]:
    if type(reference) is not type(candidate):
        yield path
        return
    if isinstance(reference, Mapping):
        for key in sorted(set(reference) | set(candidate)):
            child_path = f"{path}.{key}"
            if key not in reference or key not in candidate:
                yield child_path
            else:
                yield from _difference_paths(
                    reference[key], candidate[key], child_path
                )
        return
    if isinstance(reference, list):
        if len(reference) != len(candidate):
            yield f"{path}.length"
        for index, (left, right) in enumerate(zip(reference, candidate)):
            yield from _difference_paths(left, right, f"{path}[{index}]")
        return
    if reference != candidate:
        yield path


def _parse_record(line: str, path: Path, record_index: int) -> dict[str, Any]:
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError(f"online record must be an object: {path}:{record_index}")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("required mapping is unavailable")
    return value


def _required_text(value: Any, name: str) -> str:
    result = str(value).strip() if value is not None else ""
    if not result:
        raise ValueError(f"{name} must be non-empty")
    return result


def _required_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return int(value)


def _required_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _required_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a bool")
    return value
