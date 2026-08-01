"""Pinned D6 audit for a finalized active-vision candidate corpus.

The candidate layer adds immutable production anchors and reserved-seed checks
to the generic D6 low-level source audit.  It never imports D5 code and never
grants model admission or runtime authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .d5_active_vision_source_audit import (
    audit_d5_active_vision_source_dataset,
)


D5_ACTIVE_VISION_CANDIDATE_AUDIT_SCHEMA_VERSION = (
    "d6.d5-active-vision-candidate-audit.v2"
)
D5_ACTIVE_VISION_CANDIDATE_EVIDENCE_SCHEMA_VERSION = (
    "d6.d5-active-vision-candidate-audit-evidence.v2"
)

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_AUTHORITY_FALSE = {
    "airsim_external_proof": False,
    "real_camera_external_proof": False,
    "model_admission": False,
    "behavior_cloning": False,
    "ppo_training": False,
    "assist": False,
    "assignment": False,
    "degradation": False,
    "runtime": False,
    "production": False,
    "control": False,
    "global_track_id_write": False,
}
_CANDIDATE_CHECK_NAMES = (
    "source_low_level_audit_passed",
    "producer_commit_anchor_match",
    "generation_plan_sha256_anchor_valid",
    "manifest_sha256_anchor_match",
    "checksums_sha256_anchor_match",
    "episode_count_match",
    "descriptor_count_match",
    "online_stream_count_match",
    "offline_file_count_match",
    "seed_inventory_match",
    "reserved_seed_overlap_zero",
    "source_domain_evidence_tier_match",
    "authority_all_false",
)


@dataclass(frozen=True, slots=True)
class D5ActiveVisionCandidateAuditInputs:
    dataset_root: Path
    expected_producer_git_commit: str
    expected_generation_plan_sha256: str
    expected_manifest_sha256: str
    expected_checksums_sha256: str
    expected_episode_count: int
    expected_seed_first: int
    expected_seed_last: int
    reserved_seed_first: int
    reserved_seed_last: int


def audit_d5_active_vision_candidate(
    inputs: D5ActiveVisionCandidateAuditInputs,
) -> dict[str, Any]:
    """Audit one pinned candidate using only D6 low-level parsing."""

    _validate_inputs(inputs)
    source_result = audit_d5_active_vision_source_dataset(inputs.dataset_root)
    base = {
        "schema_version": D5_ACTIVE_VISION_CANDIDATE_AUDIT_SCHEMA_VERSION,
        "dataset_root": str(inputs.dataset_root.absolute()),
        "auditor": {
            "read_only": True,
            "uses_d5_validator": False,
            "uses_d5_corpus_gate": False,
            "uses_d5_high_level_loader": False,
            "source_audit_module_sha256": _sha256_file(
                Path(audit_d5_active_vision_source_dataset.__code__.co_filename)
            ),
            "candidate_audit_module_sha256": _sha256_file(Path(__file__)),
        },
        "status": "fail_closed",
        "blocker_codes": [],
        "failure_detail": None,
        "source_checks": dict(source_result["checks"]),
        "candidate_checks": {name: False for name in _CANDIDATE_CHECK_NAMES},
        "production_evidence": {
            "expected_producer_git_commit": inputs.expected_producer_git_commit,
            "expected_generation_plan_sha256": (
                inputs.expected_generation_plan_sha256
            ),
            "generation_plan_anchor_source": "main_supplied_fixed_evidence",
            "generation_plan_content_in_dataset_root": False,
            "generation_plan_content_recomputed": False,
            "expected_manifest_sha256": inputs.expected_manifest_sha256,
            "expected_checksums_sha256": inputs.expected_checksums_sha256,
        },
        "evidence": None,
        "authority": dict(_AUTHORITY_FALSE),
        "scope_boundary": {
            "simulation_research_integrity_evaluated": True,
            "d5_action_role_coverage_evaluated": False,
            "d5_training_gate_evaluated": False,
            "model_admission_evaluated": False,
            "runtime_authority_evaluated": False,
            "d6_control_participation": False,
        },
    }
    if source_result["status"] != "simulation_research_integrity_confirmed":
        base["blocker_codes"] = ["source_low_level_audit_failed"]
        base["failure_detail"] = {
            "source_status": source_result["status"],
            "source_blocker_codes": list(source_result["blocker_codes"]),
            "source_failure_detail": source_result["failure_detail"],
        }
        return base

    evidence = source_result["evidence"]
    checks = base["candidate_checks"]
    checks["source_low_level_audit_passed"] = True
    checks["generation_plan_sha256_anchor_valid"] = True
    checks["producer_commit_anchor_match"] = evidence["source_identity"][
        "git_commits"
    ] == [inputs.expected_producer_git_commit]
    checks["manifest_sha256_anchor_match"] = (
        evidence["dataset_manifest_sha256"] == inputs.expected_manifest_sha256
    )
    checks["checksums_sha256_anchor_match"] = (
        evidence["checksums_sha256"] == inputs.expected_checksums_sha256
    )
    checks["episode_count_match"] = (
        evidence["episode_count"] == inputs.expected_episode_count
    )
    checks["descriptor_count_match"] = (
        evidence["descriptor_count"] == inputs.expected_episode_count
    )
    checks["online_stream_count_match"] = (
        evidence["online_stream_count"] == inputs.expected_episode_count
    )
    checks["offline_file_count_match"] = (
        evidence["offline_file_count"] == inputs.expected_episode_count
    )
    expected_seeds = list(
        range(inputs.expected_seed_first, inputs.expected_seed_last + 1)
    )
    actual_seeds = list(evidence["seed_values"])
    checks["seed_inventory_match"] = (
        len(expected_seeds) == inputs.expected_episode_count
        and actual_seeds == expected_seeds
    )
    reserved_seeds = set(
        range(inputs.reserved_seed_first, inputs.reserved_seed_last + 1)
    )
    reserved_overlap = sorted(set(actual_seeds) & reserved_seeds)
    checks["reserved_seed_overlap_zero"] = not reserved_overlap
    checks["source_domain_evidence_tier_match"] = (
        evidence["source_domain"] == "scalable_3d_point_mass_runtime"
        and evidence["evidence_tier"] == "simulation_research"
    )
    checks["authority_all_false"] = all(
        value is False for value in base["authority"].values()
    ) and all(value is False for value in source_result["authority"].values())

    compact_evidence = {
        "dataset_manifest_sha256": evidence["dataset_manifest_sha256"],
        "checksums_sha256": evidence["checksums_sha256"],
        "checksum_inventory_entry_count": evidence["artifact_count"],
        "audited_file_count_including_sha256sums": evidence["audited_file_count"],
        "descriptor_count": evidence["descriptor_count"],
        "online_stream_count": evidence["online_stream_count"],
        "offline_file_count": evidence["offline_file_count"],
        "episode_count": evidence["episode_count"],
        "sample_count": evidence["sample_count"],
        "online_record_count": evidence["online_record_count"],
        "offline_label_count": evidence["offline_label_count"],
        "online_snapshot_object_count": evidence["online_snapshot_object_count"],
        "online_camera_feedback_object_count": evidence[
            "online_camera_feedback_object_count"
        ],
        "online_header_binding_count": evidence["online_header_binding_count"],
        "online_footer_index_binding_count": evidence[
            "online_footer_index_binding_count"
        ],
        "offline_episode_binding_count": evidence["offline_episode_binding_count"],
        "source_domain": evidence["source_domain"],
        "evidence_tier": evidence["evidence_tier"],
        "source_identity": evidence["source_identity"],
        "split": evidence["split"],
        "seed_inventory": {
            "count": len(actual_seeds),
            "first": min(actual_seeds),
            "last": max(actual_seeds),
            "contiguous": actual_seeds
            == list(range(min(actual_seeds), max(actual_seeds) + 1)),
            "sha256": _sha256_json(actual_seeds),
        },
        "reserved_seed_range": {
            "first": inputs.reserved_seed_first,
            "last": inputs.reserved_seed_last,
            "overlap_count": len(reserved_overlap),
            "overlap_values": reserved_overlap,
        },
        "online_truth_identifier_count": evidence["online_truth_identifier_count"],
        "online_actor_identifier_count": evidence["online_actor_identifier_count"],
        "online_object_identifier_count": evidence["online_object_identifier_count"],
        "external_runtime_attestation_validated": evidence[
            "external_runtime_attestation_validated"
        ],
        "source_audit_canonical_sha256": _sha256_json(source_result),
    }
    base["evidence"] = compact_evidence
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        base["blocker_codes"] = failed
        base["failure_detail"] = "candidate_anchor_or_scope_check_failed"
        return base

    source_check_count = sum(1 for value in source_result["checks"].values() if value)
    candidate_check_count = sum(1 for value in checks.values() if value)
    base.update(
        {
            "status": "simulation_research_integrity_confirmed",
            "check_counts": {
                "source_passed": source_check_count,
                "source_total": len(source_result["checks"]),
                "candidate_passed": candidate_check_count,
                "candidate_total": len(checks),
                "passed": source_check_count + candidate_check_count,
                "total": len(source_result["checks"]) + len(checks),
            },
        }
    )
    return base


def render_d5_active_vision_candidate_audit_markdown(
    evidence: Mapping[str, Any],
    *,
    validation_date: str,
    software_validation: Mapping[str, Any] | None = None,
) -> str:
    dataset = _mapping(evidence.get("evidence"), "evidence missing")
    split = _mapping(dataset.get("split"), "split missing")
    seed_inventory = _mapping(dataset.get("seed_inventory"), "seed inventory missing")
    reserved = _mapping(dataset.get("reserved_seed_range"), "reserved seed range missing")
    check_counts = _mapping(evidence.get("check_counts"), "check counts missing")
    authority = _mapping(evidence.get("authority"), "authority missing")
    production = _mapping(
        evidence.get("production_evidence"), "production evidence missing"
    )
    source_identity = _mapping(dataset.get("source_identity"), "source identity missing")
    split_counts = _mapping(split.get("episode_count_by_split"), "split counts missing")
    seed_counts = _mapping(split.get("seed_count_by_split"), "seed counts missing")
    validation_lines = ["软件回归结果在报告生成时未登记。"]
    if software_validation is not None:
        validation_lines = [
            f"D6 全量测试：`{software_validation.get('passed')}` 项通过，"
            f"`{software_validation.get('warning_count')}` 项告警，耗时 "
            f"`{software_validation.get('duration_seconds')}` 秒。"
        ]
    authority_closed = all(value is False for value in authority.values())
    lines = [
        "# D5 A3 v2 主动视觉候选语料独立审计",
        "",
        f"验证日期：{validation_date}",
        "",
        "## 结论",
        "",
        f"D6 对最终封装的 A3 v2 三维质点主动视觉候选语料完成只读低层审计。"
        f"来源检查和候选锚点检查共 {check_counts['passed']}/{check_counts['total']} 项通过，"
        f"状态为 `{evidence['status']}`。",
        "",
        "该结论只确认仿真研究语料的来源、文件完整性、划分和在线身份隔离。"
        "D6 没有评价 D5 动作角色覆盖、训练门或模型效果，也没有授予运行和控制权限。",
        "",
        "## 审计范围",
        "",
        f"- 生产提交：`{source_identity['git_commits'][0]}`；clean episode "
        f"{source_identity['clean_episode_count']}，dirty episode "
        f"{source_identity['dirty_episode_count']}。",
        f"- 来源域：`{dataset['source_domain']}`；证据等级：`{dataset['evidence_tier']}`。",
        f"- episode、descriptor、在线 gzip 和离线文件："
        f"{dataset['episode_count']}/{dataset['descriptor_count']}/"
        f"{dataset['online_stream_count']}/{dataset['offline_file_count']}。",
        f"- 样本与离线标签：{dataset['sample_count']}/{dataset['offline_label_count']}。",
        f"- 摘要清单工件：{dataset['checksum_inventory_entry_count']}；"
        f"连同 `SHA256SUMS` 共审计 {dataset['audited_file_count_including_sha256sums']} 个文件。",
        f"- seed：{seed_inventory['first']}-{seed_inventory['last']}，共 "
        f"{seed_inventory['count']} 个；保留范围 {reserved['first']}-{reserved['last']} "
        f"重叠数为 {reserved['overlap_count']}。",
        "",
        "## 完整性检查",
        "",
        "D6 从 `SHA256SUMS` 重建实际工件集合并复算每个文件摘要。随后逐项解析 manifest、"
        "100 个 descriptor、100 个在线压缩流和 100 个离线文件。在线流检查 header 身份、"
        "共享对象内容寻址键、样本索引、footer 摘要与计数；离线文件检查 episode 身份和"
        "样本键逐项绑定。所有输入文件在审计开始时为只读，审计结束时设备、inode、大小、"
        "修改时间和权限模式保持不变。",
        "",
        f"manifest SHA-256：`{dataset['dataset_manifest_sha256']}`。",
        f"`SHA256SUMS` 文件 SHA-256：`{dataset['checksums_sha256']}`。",
        f"拆分 SHA-256：`{split['split_sha256']}`。",
        f"训练集 SHA-256：`{split['training_set_sha256']}`。",
        "",
        "## 数据划分",
        "",
        "| 子集 | episode | seed |",
        "| --- | ---: | ---: |",
        f"| 训练 | {split_counts['train']} | {seed_counts['train']} |",
        f"| 验证 | {split_counts['validation']} | {seed_counts['validation']} |",
        f"| 测试 | {split_counts['test']} | {seed_counts['test']} |",
        "",
        "三组 seed 互斥。在线 truth、actor、object 标识计数均为 0。",
        "",
        "## 生产锚点",
        "",
        f"main 提供的生产计划摘要为 `{production['expected_generation_plan_sha256']}`。"
        "该摘要作为外部冻结锚点登记。生产计划文件不在本次只读数据集根目录内，D6 没有"
        "从语料目录重算其内容摘要。manifest、`SHA256SUMS` 和 producer commit 均从输入"
        "语料独立重算或逐 episode 核对。",
        "",
        "## 权限边界",
        "",
        f"全部权限关闭：{str(authority_closed).lower()}。行为克隆、近端策略优化、辅助模式、"
        "分配、降级、运行、生产、控制和全局航迹编号写入均为 `false`。来源完整性通过不"
        "等于模型准入，也不证明 AirSim 或真实相机来源。",
        "",
        "## 软件验证",
        "",
        *validation_lines,
        "",
    ]
    return "\n".join(lines)


def write_d5_active_vision_candidate_audit_report(
    output_dir: Path,
    evidence: Mapping[str, Any],
    *,
    validation_date: str,
    software_validation: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    if evidence.get("status") != "simulation_research_integrity_confirmed":
        raise ValueError("candidate audit did not pass")
    output_dir.mkdir(parents=True, exist_ok=False)
    machine = dict(evidence)
    machine["schema_version"] = D5_ACTIVE_VISION_CANDIDATE_EVIDENCE_SCHEMA_VERSION
    machine["validation_date"] = validation_date
    machine["software_validation"] = (
        None if software_validation is None else dict(software_validation)
    )
    machine_path = output_dir / "audit_evidence.json"
    report_path = output_dir / "D5_A3_V2_SOURCE_INDEPENDENT_AUDIT_CN.md"
    machine_path.write_text(
        json.dumps(machine, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        render_d5_active_vision_candidate_audit_markdown(
            machine,
            validation_date=validation_date,
            software_validation=software_validation,
        ),
        encoding="utf-8",
    )
    checksums = {
        machine_path.name: _sha256_file(machine_path),
        report_path.name: _sha256_file(report_path),
    }
    checksum_path = output_dir / "SHA256SUMS"
    checksum_path.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(checksums.items())),
        encoding="ascii",
    )
    return {**checksums, checksum_path.name: _sha256_file(checksum_path)}


def _validate_inputs(inputs: D5ActiveVisionCandidateAuditInputs) -> None:
    if _GIT_COMMIT.fullmatch(inputs.expected_producer_git_commit) is None:
        raise ValueError(
            "expected producer git commit must be 40 lowercase hex characters"
        )
    for value in (
        inputs.expected_generation_plan_sha256,
        inputs.expected_manifest_sha256,
        inputs.expected_checksums_sha256,
    ):
        if _HEX_SHA256.fullmatch(value) is None:
            raise ValueError("expected SHA-256 must be 64 lowercase hex characters")
    if inputs.expected_episode_count <= 0:
        raise ValueError("expected episode count must be positive")
    if inputs.expected_seed_last < inputs.expected_seed_first:
        raise ValueError("expected seed range is invalid")
    if inputs.reserved_seed_last < inputs.reserved_seed_first:
        raise ValueError("reserved seed range is invalid")


def _sha256_json(value: Any) -> str:
    payload = (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(label)
    return value


__all__ = [
    "D5_ACTIVE_VISION_CANDIDATE_AUDIT_SCHEMA_VERSION",
    "D5_ACTIVE_VISION_CANDIDATE_EVIDENCE_SCHEMA_VERSION",
    "D5ActiveVisionCandidateAuditInputs",
    "audit_d5_active_vision_candidate",
    "render_d5_active_vision_candidate_audit_markdown",
    "write_d5_active_vision_candidate_audit_report",
]
