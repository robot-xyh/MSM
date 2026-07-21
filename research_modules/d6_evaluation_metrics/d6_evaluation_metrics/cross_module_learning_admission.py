"""Read-only admission audit for cross-module scalable-3D learning data.

The audit consumes immutable producer manifests, detached canonical views,
and producer-owned full-sample evidence.  It never rewrites D3/D4/D5 data and
never upgrades synthetic curriculum ACKs to runtime execution evidence.  A
module full-sample result is kept separate from cross-module completeness.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import canonical_seed_split_readiness as _canonical


CROSS_MODULE_LEARNING_ADMISSION_SCHEMA_VERSION = (
    "d6.cross-module-learning-data-admission.v1"
)
CROSS_MODULE_LEARNING_ADMISSION_DATE = "2026-07-21"

_SPLITS = ("train", "validation", "test")
_EXPECTED_SEED_COUNTS = {"train": 60, "validation": 20, "test": 20}
_EXPECTED_RESERVED_SEEDS = tuple(range(1000, 1020))
_EXPECTED_UNIT = "numeric_seed_atomic_across_modules_scenarios_and_scales"
_HEX = frozenset("0123456789abcdef")

_D5_VIEW_SCHEMA = "d5.canonical-seed-split-view.v1"
_D5_READINESS_SCHEMA = "d5.canonical-seed-readiness.v1"
_D4_FORMAL_VIEW_SCHEMA = "d4-canonical-region-seed-split-audit-v1"
_D4_FORMAL_BINDING_SCHEMA = "d4-canonical-region-seed-split-view-v1"
_D5_SUPPLEMENTAL_FULL_SAMPLE_AUDIT_SCHEMA = (
    "d5.active-vision-supplemental-bc-full-sample-audit.v1"
)
_D3_FULL_SAMPLE_AUDIT_SCHEMA = "d3.assignment-full-sample-audit.v1"
_D3_FULL_SAMPLE_AUDIT_PURPOSE = (
    "formal_assignment_behavior_cloning_full_sample_admission"
)
_D4_FULL_SAMPLE_AUDIT_SCHEMA = (
    "d4-region-resource-full-sample-admission-audit-v1"
)
_D4_FULL_SAMPLE_AUDIT_PURPOSE = (
    "d4_formal_and_supplemental_full_sample_admission"
)


class CrossModuleLearningAdmissionError(RuntimeError):
    """Stable fail-closed error raised by the joint admission boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class CrossModuleLearningAdmissionInputs:
    """Explicit immutable inputs for one joint admission audit."""

    training_seed_registry_path: Path
    shared_seed_registry_path: Path
    d3_formal_manifest_path: Path
    d3_full_sample_audit_path: Path
    d3_full_sample_audit_file_sha256: str
    d4_formal_manifest_path: Path
    d4_formal_canonical_view_path: Path
    d4_formal_canonical_view_file_sha256: str
    d4_full_sample_audit_path: Path
    d4_full_sample_audit_file_sha256: str
    d5_tracklet_formal_manifest_path: Path
    d5_tracklet_canonical_view_path: Path
    d5_tracklet_canonical_readiness_path: Path
    d5_active_vision_formal_manifest_path: Path
    d5_active_vision_canonical_view_path: Path
    d5_active_vision_canonical_readiness_path: Path
    d4_supplemental_summary_path: Path
    d5_supplemental_summary_path: Path
    d5_supplemental_full_sample_audit_path: Path
    d5_supplemental_full_sample_audit_file_sha256: str

    def resolved(self) -> "CrossModuleLearningAdmissionInputs":
        return CrossModuleLearningAdmissionInputs(
            **{
                field: (
                    Path(getattr(self, field)).resolve()
                    if field.endswith("_path")
                    else getattr(self, field)
                )
                for field in self.__dataclass_fields__
            }
        )


def audit_cross_module_learning_data_admission(
    inputs: CrossModuleLearningAdmissionInputs,
    *,
    audit_date: str = CROSS_MODULE_LEARNING_ADMISSION_DATE,
) -> dict[str, Any]:
    """Validate all formal and supplemental evidence without source writes."""

    source = inputs.resolved()
    if audit_date != CROSS_MODULE_LEARNING_ADMISSION_DATE:
        _fail("audit_date_mismatch", "the frozen evidence date must be 2026-07-21")

    registry = _audit_registries(source)
    d3_formal = _audit_d3_formal(source.d3_formal_manifest_path, registry)
    d4_formal = _audit_d4_formal(
        source.d4_formal_manifest_path,
        source.d4_formal_canonical_view_path,
        source.d4_formal_canonical_view_file_sha256,
        registry,
    )
    d5_tracklet = _audit_d5_formal(
        consumer="tracklet_graph",
        manifest_path=source.d5_tracklet_formal_manifest_path,
        view_path=source.d5_tracklet_canonical_view_path,
        readiness_path=source.d5_tracklet_canonical_readiness_path,
        registry=registry,
    )
    d5_active = _audit_d5_formal(
        consumer="active_vision",
        manifest_path=source.d5_active_vision_formal_manifest_path,
        view_path=source.d5_active_vision_canonical_view_path,
        readiness_path=source.d5_active_vision_canonical_readiness_path,
        registry=registry,
    )
    d4_supplemental = _audit_d4_supplemental(
        source.d4_supplemental_summary_path, registry
    )
    d5_supplemental = _audit_d5_supplemental(
        source.d5_supplemental_summary_path, registry
    )
    d5_supplemental_full_sample = _audit_d5_supplemental_full_sample(
        source.d5_supplemental_full_sample_audit_path,
        expected_file_sha256=(
            source.d5_supplemental_full_sample_audit_file_sha256
        ),
        d5_supplemental=d5_supplemental,
        registry=registry,
    )
    d3_full_sample = _audit_d3_full_sample(
        source.d3_full_sample_audit_path,
        expected_file_sha256=source.d3_full_sample_audit_file_sha256,
        d3_formal=d3_formal,
        registry=registry,
    )
    d4_full_sample = _audit_d4_full_sample(
        source.d4_full_sample_audit_path,
        expected_file_sha256=source.d4_full_sample_audit_file_sha256,
        d4_formal=d4_formal,
        d4_supplemental=d4_supplemental,
        registry=registry,
    )

    availability = _build_availability(
        d3_full_sample=d3_full_sample,
        d4_formal=d4_formal,
        d4_full_sample=d4_full_sample,
        d5_active=d5_active,
        d4_supplemental=d4_supplemental,
        d5_supplemental=d5_supplemental,
    )
    admission = {
        "behavior_cloning_canonical_view_available": True,
        "behavior_cloning_full_sample_audit": {
            "available": True,
            "status": "complete",
            "reason": "d3_d4_d5_structural_full_sample_audits_complete",
            "module_status": {
                "d3_assignment": "complete",
                "d4_region": "complete",
                "d5_supplemental_active_vision": "complete",
            },
        },
        "ppo_allowed": False,
        "assist_allowed": False,
        "authority_allowed": False,
        "rule_fallback_required": True,
        "status": "structural_full_sample_complete_overall_admission_partial",
        "promotion_blockers": [
            "reward_unavailable",
            "outcome_unavailable",
            "causal_and_counterfactual_evidence_unavailable",
            "runtime_ack_attribution_unavailable",
            "paired_shadow_non_degradation_unavailable",
            "held_out_seed_performance_unavailable",
            "d5_tracklet_training_readiness_fail_closed",
        ],
    }

    return {
        "schema_version": CROSS_MODULE_LEARNING_ADMISSION_SCHEMA_VERSION,
        "audit_date": audit_date,
        "audit_mode": "read_only_fail_closed",
        "source_mutation_performed": False,
        "registries": registry["report"],
        "evidence_layers": {
            "formal_observation_corpus": {
                "classification": "formal_observation_corpus",
                "producer_artifacts_modified": False,
                "online_truth_use_count": 0,
                "modules": {
                    "d3_assignment": d3_formal,
                    "d4_region": d4_formal,
                    "d5_tracklet_graph": d5_tracklet,
                    "d5_active_vision": d5_active,
                },
            },
            "supplemental_rule_teacher_curriculum": {
                "classification": "supplemental_rule_teacher_curriculum",
                "formal_corpus_replacement_allowed": False,
                "d4_region": d4_supplemental,
                "d5_active_vision": {
                    **d5_supplemental,
                    "full_sample_audit": d5_supplemental_full_sample,
                },
            },
            "full_sample_audits": {
                "classification": "cross_module_full_sample_audit",
                "status": "complete",
                "complete": True,
                "modules": {
                    "d3_assignment": d3_full_sample,
                    "d4_region": d4_full_sample,
                    "d5_supplemental_active_vision": (
                        d5_supplemental_full_sample
                    ),
                },
            },
            "offline_evaluator_labels": {
                "classification": "offline_evaluator_labels",
                "online_feature_or_control_use_allowed": False,
                "tracklet_association_labels": {
                    "schema_version": d5_tracklet["evaluator_label_schema_version"],
                    **d5_tracklet["association_label_summary"],
                    "note": "offline_edge_labels_do_not_supply_control_reward",
                },
                "active_vision_labels": availability,
            },
            "runtime_ack_evidence": {
                "classification": "runtime_ack_evidence",
                "available": False,
                "reason": "no_applied_action_runtime_ack_attribution",
                "synthetic_fault_coverage": d5_supplemental[
                    "synthetic_ack_fault_coverage"
                ],
                "synthetic_counts_promoted_to_runtime": False,
            },
        },
        "action_coverage": {
            "d4": d4_supplemental["action_coverage"],
            "d5": d5_supplemental["action_coverage"],
        },
        "availability": availability,
        "admission_matrix": admission,
        "audit": {
            "passed": True,
            "fail_closed": True,
            "violation_count": 0,
            "violations": [],
        },
    }


def write_cross_module_learning_data_admission_report(
    inputs: CrossModuleLearningAdmissionInputs,
    output_dir: str | Path,
    *,
    audit_date: str = CROSS_MODULE_LEARNING_ADMISSION_DATE,
) -> dict[str, Path]:
    """Write deterministic JSON and Chinese Markdown admission reports."""

    source = inputs.resolved()
    root = Path(output_dir).resolve()
    formal_generation_root = source.training_seed_registry_path.parent
    _expect(
        root != formal_generation_root and formal_generation_root not in root.parents,
        "output_inside_formal_generation_root",
        "admission reports must be written outside the formal generation root",
    )
    payload = audit_cross_module_learning_data_admission(
        source, audit_date=audit_date
    )
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "cross_module_learning_admission.json"
    markdown_path = root / "cross_module_learning_admission_cn.md"
    _write_json_atomic(json_path, payload)
    _write_text_atomic(
        markdown_path,
        render_cross_module_learning_data_admission_markdown(payload),
    )
    return {"json": json_path, "markdown": markdown_path}


def render_cross_module_learning_data_admission_markdown(
    payload: Mapping[str, Any],
) -> str:
    """Render a concise Chinese report from a validated admission payload."""

    registry = _mapping(payload.get("registries"), "registries")
    layers = _mapping(payload.get("evidence_layers"), "evidence_layers")
    formal = _mapping(layers.get("formal_observation_corpus"), "formal layer")
    formal_modules = _mapping(formal.get("modules"), "formal modules")
    supplemental = _mapping(
        layers.get("supplemental_rule_teacher_curriculum"), "supplemental layer"
    )
    full_sample_layer = _mapping(
        layers.get("full_sample_audits"), "full-sample audit layer"
    )
    full_sample_modules = _mapping(
        full_sample_layer.get("modules"), "full-sample audit modules"
    )
    offline = _mapping(layers.get("offline_evaluator_labels"), "offline labels")
    tracklet_labels = _mapping(
        offline.get("tracklet_association_labels"), "tracklet labels"
    )
    action = _mapping(payload.get("action_coverage"), "action coverage")
    availability = _mapping(payload.get("availability"), "availability")
    admission = _mapping(payload.get("admission_matrix"), "admission matrix")

    d3 = _mapping(formal_modules.get("d3_assignment"), "D3 formal")
    d4 = _mapping(formal_modules.get("d4_region"), "D4 formal")
    d5_tracklet = _mapping(
        formal_modules.get("d5_tracklet_graph"), "D5 tracklet formal"
    )
    d5_active = _mapping(
        formal_modules.get("d5_active_vision"), "D5 active formal"
    )
    d4_supp = _mapping(supplemental.get("d4_region"), "D4 supplemental")
    d5_supp = _mapping(supplemental.get("d5_active_vision"), "D5 supplemental")
    d5_full_sample = _mapping(
        full_sample_modules.get("d5_supplemental_active_vision"),
        "D5 supplemental full-sample audit",
    )
    d3_full_sample = _mapping(
        full_sample_modules.get("d3_assignment"),
        "D3 assignment full-sample audit",
    )
    d4_full_sample = _mapping(
        full_sample_modules.get("d4_region"),
        "D4 regional full-sample audit",
    )
    d4_action = _mapping(action.get("d4"), "D4 action")
    d5_action = _mapping(action.get("d5"), "D5 action")

    lines = [
        "# D6 跨模块学习数据联合准入审计",
        "",
        f"审计日期：{payload['audit_date']}。本次只读校验正式语料、规范 seed 视图和补充规则教师课程，没有修改生产者制品。",
        "",
        "## 结论",
        "",
        "D3、D4、D5 的规范 seed 身份已统一为训练/验证/测试 60/20/20，保留 seed 1000-1019 泄漏为 0。三份 producer 全样本审计均通过文件哈希、内容哈希、来源绑定、完整计数和零违规复核，跨模块结构性全样本状态为 complete。",
        "",
        "结构性完成不等于总体学习准入完成。奖励、结果、反事实、因果标签、真实运行时确认、同 seed 配对 shadow 和保留 seed 性能均不可用。因此 PPO、在线辅助和控制权限保持关闭，规则回退继续强制启用。D3 reward_components 只作规则教师诊断；D4 projected recommendation 和 target.kind=rule 不属于运行确认或真值；D5 applied/rejected/missing 只代表确定性故障注入覆盖。",
        "",
        "## 注册表",
        "",
        "| 项目 | 结果 |",
        "| --- | --- |",
        f"| 训练 seed | {registry['training_seed_count']} |",
        f"| 规范切分 | {registry['split_seed_counts']['train']}/{registry['split_seed_counts']['validation']}/{registry['split_seed_counts']['test']} |",
        f"| 保留 seed | {registry['reserved_evaluation_seed_count']}，泄漏 {registry['reserved_seed_leakage_count']} |",
        f"| 训练注册表 SHA256 | `{registry['training_seed_registry_file_sha256']}` |",
        f"| 共享注册表 SHA256 | `{registry['shared_seed_registry_file_sha256']}` |",
        "",
        "## 正式语料",
        "",
        "| 模块 | episode/记录 | 规范 seed | 状态 |",
        "| --- | ---: | --- | --- |",
        f"| D3 分配 | {d3['episode_count']} episode，{d3['frame_count']} frame | 60/20/20 | 规范映射通过 |",
        f"| D4 区域 | {d4['episode_count']} episode，{d4['frame_count']} frame | 60/20/20 | 独立 formal view 通过 |",
        f"| D5 跨视角图 | {d5_tracklet['episode_count']} graph episode，{d5_tracklet['candidate_edge_count']} candidate edge | 60/20/20 | 标签 {tracklet_labels['labeled_count']} 已标注/{tracklet_labels['unlabeled_count']} 未标注，{tracklet_labels['status']} |",
        f"| D5 主动视觉 | {d5_active['episode_count']} episode，{d5_active['sample_count']} sample | 60/20/20 | 视图通过，开发期 shadow |",
        "",
        f"D4 formal view 文件 SHA256 为 `{d4['canonical_view_file_sha256']}`，binding.view_sha256 为 `{d4['canonical_view_content_sha256']}`。该文件与 D4 补充课程视图分开审计。",
        "",
        f"D5 tracklet 离线关联标签状态为 {tracklet_labels['status']}，正样本 {tracklet_labels['positive_labeled_count']}、负样本 {tracklet_labels['negative_labeled_count']}、未标注 {tracklet_labels['unlabeled_count']}。部分标签不能解释为完整监督语料。",
        "",
        "## 补充课程",
        "",
        f"D4 补充课程包含 {d4_supp['episode_count']} episode、{d4_supp['frame_count']} frame。D5 补充课程包含 {d5_supp['episode_count']} episode、{d5_supp['segment_count']} segment、{d5_supp['sample_count']} sample。两者只提供规则教师动作覆盖，不替代正式观测语料。",
        "",
        "| 模块 | 动作覆盖 |",
        "| --- | --- |",
        f"| D4 | hold {d4_action['hold']}；request_replan {d4_action['request_replan']}；nonzero quota {d4_action['nonzero_quota']}；transfer {d4_action['transfer']} |",
        f"| D5 intent | hold {d5_action['intent']['hold']}；observe_target {d5_action['intent']['observe_target']}；reacquire {d5_action['intent']['reacquire']}；search_sector {d5_action['intent']['search_sector']} |",
        f"| D5 视场 | wide {d5_action['fov']['wide']}；zoom {d5_action['fov']['zoom']} |",
        f"| D5 角色 | interceptor {d5_action['camera_role']['interceptor']}；recon {d5_action['camera_role']['recon']} |",
        "",
        "## 全样本审计",
        "",
        "| 模块 | 状态 | 范围 |",
        "| --- | --- | --- |",
        f"| D3 分配 | {d3_full_sample['status']} | {d3_full_sample['episode_count']} episode，{d3_full_sample['frame_count']} decision frame，{d3_full_sample['candidate_edge_count']} candidate edge |",
        f"| D4 区域 | {d4_full_sample['status']} | formal {d4_full_sample['formal']['episode_count']} episode/{d4_full_sample['formal']['sample_count']} sample；supplemental {d4_full_sample['supplemental']['episode_count']} episode/{d4_full_sample['supplemental']['sample_count']} sample |",
        f"| D5 补充主动视觉 | {d5_full_sample['status']} | {d5_full_sample['episode_count']} episode，{d5_full_sample['sample_count']} sample，校验制品 {d5_full_sample['verified_artifact_count']}/{d5_full_sample['checksummed_artifact_count']} |",
        "",
        f"D3 全样本审计文件/内容 SHA-256 为 `{d3_full_sample['audit_file_sha256']}` / `{d3_full_sample['audit_content_sha256']}`；D4 为 `{d4_full_sample['audit_file_sha256']}` / `{d4_full_sample['audit_content_sha256']}`；D5 为 `{d5_full_sample['audit_file_sha256']}` / `{d5_full_sample['audit_content_sha256']}`。三模块 online truth、保留 seed 泄漏、dirty episode 和结构约束违规均为 0。",
        "",
        "## 证据可用性",
        "",
        "| 证据 | 可用 | 原因 |",
        "| --- | --- | --- |",
    ]
    for name, label in (
        ("reward", "奖励"),
        ("outcome", "结果"),
        ("counterfactual", "反事实"),
        ("causal", "因果"),
        ("runtime_ack", "真实运行时确认"),
        ("paired_shadow", "配对 shadow"),
    ):
        item = _mapping(availability.get(name), name)
        lines.append(
            f"| {label} | {'是' if item['available'] else '否'} | {item['reason']} |"
        )

    lines.extend(
        [
            "",
            "## 准入矩阵",
            "",
            "| 能力 | 结论 |",
            "| --- | --- |",
            f"| 行为克隆规范视图 | {'可用' if admission['behavior_cloning_canonical_view_available'] else '不可用'} |",
            f"| 行为克隆全样本复核 | {admission['behavior_cloning_full_sample_audit']['status']} |",
            f"| PPO | {'允许' if admission['ppo_allowed'] else '关闭'} |",
            f"| 在线辅助 | {'允许' if admission['assist_allowed'] else '关闭'} |",
            f"| 控制权限 | {'允许' if admission['authority_allowed'] else '关闭'} |",
            f"| 规则回退 | {'强制' if admission['rule_fallback_required'] else '非强制'} |",
            "",
            "## 限制",
            "",
            "D3、D4、D5 已复核到 producer 全样本结构证据。总体准入仍为 partial：真实运行时动作执行结果、可归因结果与奖励、反事实/因果标签、配对 shadow 非退化结果和保留 seed 性能尚未形成统一 D6 证据。",
            "",
        ]
    )
    return "\n".join(lines)


def _audit_registries(
    inputs: CrossModuleLearningAdmissionInputs,
) -> dict[str, Any]:
    training_path = inputs.training_seed_registry_path
    shared_path = inputs.shared_seed_registry_path
    training_payload = _read_json_object(training_path, "training_seed_registry")
    shared_payload = _read_json_object(shared_path, "shared_seed_registry")
    expected_training_keys = {
        "schema_version",
        "training_seed_count",
        "training_seeds",
        "reserved_evaluation_seed_count",
        "reserved_evaluation_seeds",
        "overlap_count",
        "git_commit",
        "repository_dirty",
        "schedule_sha256",
    }
    _expect_equal(
        set(training_payload),
        expected_training_keys,
        "training_registry_fields_mismatch",
        "training seed registry fields changed",
    )
    try:
        training = _canonical._validate_training_seed_registry(training_payload)
        shared = _canonical._validate_shared_registry(
            shared_payload,
            registry_file_sha256=_sha256_file(shared_path),
            training_registry=training_payload,
            training_registry_file_sha256=_sha256_file(training_path),
            training=training,
        )
    except _canonical.CanonicalSeedSplitAuditError as exc:
        raise CrossModuleLearningAdmissionError(exc.code, str(exc)) from exc

    _expect(
        training["repository_dirty"] is False,
        "dirty_training_source",
        "formal training registry belongs to a dirty repository",
    )
    source = _mapping(shared_payload.get("source"), "shared registry source")
    _expect(
        source.get("repository_dirty") is False,
        "dirty_shared_registry_source",
        "shared registry is bound to a dirty source",
    )
    split_counts = Counter(shared["assignment_by_seed"].values())
    counts = {name: int(split_counts[name]) for name in _SPLITS}
    _expect_equal(
        counts,
        _EXPECTED_SEED_COUNTS,
        "canonical_seed_count_mismatch",
        "canonical seed counts must be 60/20/20",
    )
    _expect_equal(
        tuple(sorted(training["reserved_seeds"])),
        _EXPECTED_RESERVED_SEEDS,
        "reserved_seed_catalog_mismatch",
        "reserved seeds must remain 1000-1019",
    )
    leaked = sorted(set(shared["assignment_by_seed"]) & set(training["reserved_seeds"]))
    _expect(
        not leaked,
        "reserved_seed_leakage",
        f"reserved seeds entered canonical assignments: {leaked}",
    )
    return {
        "assignment_by_seed": dict(shared["assignment_by_seed"]),
        "training_seeds": tuple(training["training_seeds"]),
        "reserved_seeds": tuple(training["reserved_seeds"]),
        "git_commit": training["git_commit"],
        "schedule_sha256": training_payload["schedule_sha256"],
        "training_file_sha256": _sha256_file(training_path),
        "shared_file_sha256": _sha256_file(shared_path),
        "shared_content_sha256": shared["content_sha256"],
        "assignment_sha256": shared["assignment_sha256"],
        "report": {
            "training_seed_registry_schema_version": training_payload[
                "schema_version"
            ],
            "training_seed_registry_file_sha256": _sha256_file(training_path),
            "shared_seed_registry_schema_version": shared_payload["schema_version"],
            "shared_seed_registry_file_sha256": _sha256_file(shared_path),
            "shared_seed_registry_content_sha256": shared["content_sha256"],
            "shared_assignment_sha256": shared["assignment_sha256"],
            "training_seed_count": len(training["training_seeds"]),
            "reserved_evaluation_seed_count": len(training["reserved_seeds"]),
            "split_seed_counts": counts,
            "reserved_seed_leakage_count": 0,
            "source_repository_dirty": False,
            "validation": {
                "schema": True,
                "source_identity": True,
                "file_and_content_hashes": True,
                "assignment_reproduced": True,
                "reserved_seed_isolation": True,
            },
        },
    }


def _audit_d3_formal(path: Path, registry: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _read_json_object(path, "D3 formal manifest")
    _expect_equal(
        manifest.get("schema_version"),
        "d3_learning_dataset_v2",
        "d3_formal_schema_mismatch",
        "unsupported D3 formal dataset schema",
    )
    _expect_equal(
        manifest.get("split_policy_version"),
        "d3_numeric_seed_atomic_split_v2",
        "d3_formal_split_policy_mismatch",
        "D3 formal split policy changed",
    )
    _expect_equal(
        manifest.get("identity_policy"),
        "anonymous_ordinal_tokens_no_truth_metadata",
        "d3_formal_identity_policy_mismatch",
        "D3 formal identity policy no longer guarantees truth isolation",
    )
    expected_catalog = _canonical_seed_values(registry)
    _expect_equal(
        manifest.get("split_seed_values"),
        expected_catalog,
        "d3_formal_seed_assignment_mismatch",
        "D3 formal seed assignments differ from the shared registry",
    )
    _validate_reserved_absence(expected_catalog, registry, "D3 formal")
    episode_count = _nonnegative_int(manifest.get("episode_count"), "D3 episode_count")
    frame_count = _nonnegative_int(manifest.get("frame_count"), "D3 frame_count")
    unique_seed_count = _nonnegative_int(
        manifest.get("unique_seed_count"), "D3 unique_seed_count"
    )
    _expect_equal(
        episode_count,
        900,
        "d3_formal_episode_count_mismatch",
        "the frozen formal D3 corpus must contain 900 episodes",
    )
    _expect_equal(
        unique_seed_count,
        100,
        "d3_formal_seed_count_mismatch",
        "the frozen formal D3 corpus must contain 100 seeds",
    )
    split_episode_counts = _count_mapping(
        manifest.get("split_episode_counts"), "D3 split_episode_counts"
    )
    _expect_equal(
        split_episode_counts,
        {"train": 540, "validation": 180, "test": 180},
        "d3_formal_episode_split_mismatch",
        "D3 formal episode counts differ from the canonical 60/20/20 view",
    )
    split_frame_counts = _count_mapping(
        manifest.get("split_frame_counts"), "D3 split_frame_counts"
    )
    _expect_equal(
        sum(split_frame_counts.values()),
        frame_count,
        "d3_formal_frame_count_mismatch",
        "D3 split frame counts do not sum to frame_count",
    )
    frames_sha256 = _require_sha256(
        manifest.get("frames_sha256"), "D3 frames_sha256"
    )
    return {
        "classification": "formal_observation_corpus",
        "manifest_schema_version": manifest["schema_version"],
        "manifest_file_sha256": _sha256_file(path),
        "frames_sha256": frames_sha256,
        "episode_count": episode_count,
        "frame_count": frame_count,
        "canonical_episode_counts": split_episode_counts,
        "canonical_frame_counts": split_frame_counts,
        "unique_seed_count": unique_seed_count,
        "canonical_seed_counts": dict(_EXPECTED_SEED_COUNTS),
        "reserved_seed_leakage_count": 0,
        "online_truth_use_count": 0,
        "canonical_view_available": True,
        "full_sample_audit_completed_by_d6": False,
    }


def _audit_d4_formal(
    manifest_path: Path,
    view_path: Path,
    expected_view_file_sha256: str,
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    expected_view_hash = _require_sha256(
        expected_view_file_sha256, "D4 formal view file SHA256"
    )
    actual_view_hash = _sha256_file(view_path)
    _expect_equal(
        actual_view_hash,
        expected_view_hash,
        "d4_formal_view_file_hash_mismatch",
        "D4 formal canonical view file differs from its out-of-band SHA256",
    )
    manifest = _read_json_object(manifest_path, "D4 formal manifest")
    view = _read_json_object(view_path, "D4 formal canonical view")
    _expect_equal(
        manifest.get("schema"),
        "d4-region-learning-dataset-v1",
        "d4_formal_manifest_schema_mismatch",
        "unsupported D4 formal manifest schema",
    )
    _expect_equal(
        view.get("schema"),
        _D4_FORMAL_VIEW_SCHEMA,
        "d4_formal_view_schema_mismatch",
        "D4 formal evidence is not a canonical split audit",
    )
    _expect_equal(
        set(view),
        {"schema", "binding", "source_split", "canonical_split", "readiness"},
        "d4_formal_view_fields_mismatch",
        "D4 formal canonical view fields changed",
    )

    split = _mapping(manifest.get("split"), "D4 formal split")
    availability = _mapping(manifest.get("availability"), "D4 availability")
    _expect(
        availability.get("behavior_cloning_available") is True,
        "d4_formal_bc_unavailable",
        "D4 formal manifest does not expose behavior-cloning data",
    )
    _expect(
        availability.get("ppo_available") is False,
        "d4_formal_ppo_claim_invalid",
        "D4 formal manifest unexpectedly claims PPO availability",
    )
    _expect_equal(
        _nonnegative_int(
            availability.get("dirty_episode_count"), "D4 dirty_episode_count"
        ),
        0,
        "d4_formal_dirty_source",
        "D4 formal corpus contains dirty episodes",
    )
    entries = _mapping_sequence(manifest.get("episodes"), "D4 episodes")
    _expect_equal(
        len(entries),
        900,
        "d4_formal_episode_count_mismatch",
        "the frozen formal D4 corpus must contain 900 episodes",
    )
    canonical_counts = {name: 0 for name in _SPLITS}
    canonical_frames = {name: 0 for name in _SPLITS}
    source_counts = {name: 0 for name in _SPLITS}
    source_seeds: set[int] = set()
    frame_count = 0
    for entry in entries:
        source = _mapping(entry.get("source"), "D4 episode source")
        seed = _nonnegative_int(source.get("seed"), "D4 episode seed")
        source_seeds.add(seed)
        _expect(
            source.get("git_dirty") is False,
            "d4_formal_dirty_source",
            "D4 formal episode is marked dirty",
        )
        _expect_equal(
            source.get("git_commit"),
            registry["git_commit"],
            "d4_formal_source_commit_mismatch",
            "D4 formal episode commit differs from the training registry",
        )
        _expect(
            seed in registry["assignment_by_seed"],
            "d4_formal_unregistered_seed",
            f"D4 formal episode uses unregistered seed {seed}",
        )
        frames = _nonnegative_int(entry.get("frame_count"), "D4 frame_count")
        native_split = _split(entry.get("split"), "D4 source split")
        canonical_split = registry["assignment_by_seed"][seed]
        source_counts[native_split] += 1
        canonical_counts[canonical_split] += 1
        canonical_frames[canonical_split] += frames
        frame_count += frames
    _expect_equal(
        source_seeds,
        set(registry["training_seeds"]),
        "d4_formal_seed_coverage_mismatch",
        "D4 formal corpus does not cover exactly the 100 training seeds",
    )
    _expect_equal(
        frame_count,
        _nonnegative_int(availability.get("frame_count"), "D4 availability frame_count"),
        "d4_formal_frame_count_mismatch",
        "D4 episode frames differ from manifest availability",
    )

    binding = _mapping(view.get("binding"), "D4 formal binding")
    _expect_equal(
        binding.get("schema"),
        _D4_FORMAL_BINDING_SCHEMA,
        "d4_formal_binding_schema_mismatch",
        "D4 formal binding schema changed",
    )
    binding_content = dict(binding)
    claimed_view_content_hash = _require_sha256(
        binding_content.pop("view_sha256", None), "D4 binding.view_sha256"
    )
    _expect_equal(
        _sha256_json(binding_content),
        claimed_view_content_hash,
        "d4_formal_view_content_hash_mismatch",
        "D4 formal canonical binding content hash failed",
    )
    manifest_file_sha = _sha256_file(manifest_path)
    manifest_dataset_sha = _require_sha256(
        manifest.get("dataset_sha256"), "D4 dataset_sha256"
    )
    manifest_split_sha = _require_sha256(split.get("split_sha256"), "D4 split_sha256")
    expected_binding = {
        "source_dataset_sha256": manifest_dataset_sha,
        "source_dataset_manifest_file_sha256": manifest_file_sha,
        "source_dataset_split_sha256": manifest_split_sha,
        "training_seed_registry_sha256": registry["training_file_sha256"],
        "shared_registry_file_sha256": registry["shared_file_sha256"],
        "shared_registry_content_sha256": registry["shared_content_sha256"],
        "assignment_sha256": registry["assignment_sha256"],
        "split_seed": 20260720,
        "train_seeds": _canonical_seed_values(registry)["train"],
        "validation_seeds": _canonical_seed_values(registry)["validation"],
        "test_seeds": _canonical_seed_values(registry)["test"],
        "reserved_evaluation_seeds": list(registry["reserved_seeds"]),
        "episode_count": len(entries),
        "frame_count": frame_count,
    }
    for field, expected in expected_binding.items():
        _expect_equal(
            binding.get(field),
            expected,
            "d4_formal_binding_mismatch",
            f"D4 formal binding differs at {field}",
        )
    _expect_equal(
        view.get("source_split"),
        {"episode_counts": source_counts, "split_sha256": manifest_split_sha},
        "d4_formal_source_split_mismatch",
        "D4 formal source split summary differs from the manifest",
    )
    expected_canonical = {
        "seed_counts": dict(_EXPECTED_SEED_COUNTS),
        "episode_counts": canonical_counts,
        "frame_counts": canonical_frames,
        "numeric_seed_atomic": True,
        "reserved_seed_count": 20,
        "reserved_seed_present": False,
    }
    _expect_equal(
        view.get("canonical_split"),
        expected_canonical,
        "d4_formal_canonical_counts_mismatch",
        "D4 formal canonical counts differ from the shared registry overlay",
    )
    readiness = _mapping(view.get("readiness"), "D4 formal readiness")
    _expect(
        readiness.get("behavior_cloning_view_available") is True
        and readiness.get("ppo_available") is False
        and readiness.get("assist_eligible") is False
        and readiness.get("model_performance_evidence") is False,
        "d4_formal_readiness_claim_invalid",
        "D4 formal canonical view overstates learning readiness",
    )
    return {
        "classification": "formal_observation_corpus",
        "manifest_schema_version": manifest["schema"],
        "manifest_file_sha256": manifest_file_sha,
        "dataset_sha256": manifest_dataset_sha,
        "canonical_view_schema_version": view["schema"],
        "canonical_view_file_sha256": actual_view_hash,
        "canonical_view_content_sha256": claimed_view_content_hash,
        "episode_count": len(entries),
        "frame_count": frame_count,
        "canonical_seed_counts": dict(_EXPECTED_SEED_COUNTS),
        "canonical_episode_counts": canonical_counts,
        "canonical_frame_counts": canonical_frames,
        "reserved_seed_leakage_count": 0,
        "dirty_episode_count": 0,
        "online_truth_use_count": 0,
        "reward_available_count": _nonnegative_int(
            availability.get("reward_available_count"),
            "D4 reward_available_count",
        ),
        "reward_sample_count": frame_count,
        "canonical_view_available": True,
        "full_sample_audit_completed_by_d6": False,
    }


def _audit_d5_formal(
    *,
    consumer: str,
    manifest_path: Path,
    view_path: Path,
    readiness_path: Path,
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    if consumer not in {"tracklet_graph", "active_vision"}:
        _fail("d5_consumer_invalid", f"unsupported D5 consumer: {consumer}")
    manifest = _read_json_object(manifest_path, f"D5 {consumer} manifest")
    view = _read_json_object(view_path, f"D5 {consumer} canonical view")
    readiness = _read_json_object(readiness_path, f"D5 {consumer} readiness")
    expected_manifest_schema = (
        "d5.tracklet-dataset.v2"
        if consumer == "tracklet_graph"
        else "d5.active-vision-episode-dataset.v3"
    )
    expected_consumer_schema = (
        "d5.tracklet-canonical-view-consumer.v1"
        if consumer == "tracklet_graph"
        else "d5.active-vision-canonical-view-consumer.v1"
    )
    _expect_equal(
        manifest.get("schema_version"),
        expected_manifest_schema,
        "d5_formal_manifest_schema_mismatch",
        f"unsupported D5 {consumer} formal manifest schema",
    )
    _expect_equal(
        view.get("schema_version"),
        _D5_VIEW_SCHEMA,
        "d5_canonical_view_schema_mismatch",
        f"D5 {consumer} evidence is not a canonical view",
    )
    _expect_equal(
        set(view),
        {
            "schema_version",
            "validation_date",
            "consumer",
            "consumer_schema_version",
            "source",
            "training_seed_registry",
            "shared_seed_registry",
            "canonical_split",
            "view_contract",
            "content_sha256",
        },
        "d5_canonical_view_fields_mismatch",
        f"D5 {consumer} canonical view fields changed",
    )
    _expect_equal(
        view.get("validation_date"),
        CROSS_MODULE_LEARNING_ADMISSION_DATE,
        "d5_canonical_view_date_mismatch",
        f"D5 {consumer} canonical view date changed",
    )
    _expect_equal(
        view.get("consumer"),
        consumer,
        "d5_canonical_view_consumer_mismatch",
        f"D5 {consumer} canonical view belongs to another consumer",
    )
    _expect_equal(
        view.get("consumer_schema_version"),
        expected_consumer_schema,
        "d5_canonical_view_consumer_schema_mismatch",
        f"D5 {consumer} consumer schema changed",
    )
    unsigned = deepcopy(view)
    claimed_content_hash = _require_sha256(
        unsigned.pop("content_sha256", None), f"D5 {consumer} view content_sha256"
    )
    _expect_equal(
        _sha256_json(unsigned),
        claimed_content_hash,
        "d5_canonical_view_content_hash_mismatch",
        f"D5 {consumer} canonical view content hash failed",
    )
    view_file_sha = _sha256_file(view_path)

    entries = _mapping_sequence(manifest.get("episodes"), f"D5 {consumer} episodes")
    seeds = {_nonnegative_int(item.get("seed"), "D5 episode seed") for item in entries}
    _expect_equal(
        seeds,
        set(registry["training_seeds"]),
        "d5_formal_seed_coverage_mismatch",
        f"D5 {consumer} does not cover exactly the 100 training seeds",
    )
    _expect(
        not seeds.intersection(registry["reserved_seeds"]),
        "d5_formal_reserved_seed_leakage",
        f"D5 {consumer} contains reserved evaluation seeds",
    )
    if consumer == "active_vision":
        source_summary = _mapping(
            manifest.get("source_identity_summary"),
            "D5 active-vision source identity summary",
        )
        _expect_equal(
            _nonnegative_int(
                source_summary.get("dirty_episode_count"),
                "D5 active dirty_episode_count",
            ),
            0,
            "d5_formal_dirty_source",
            "D5 active-vision formal corpus contains dirty episodes",
        )
        for item in entries:
            identity = _mapping(
                item.get("source_identity"), "D5 active source identity"
            )
            _expect(
                identity.get("git_dirty") is False,
                "d5_formal_dirty_source",
                "D5 active-vision episode is marked dirty",
            )

    source = _mapping(view.get("source"), "D5 view source")
    manifest_file_sha = _sha256_file(manifest_path)
    _expect_equal(
        source.get("manifest_sha256"),
        manifest_file_sha,
        "d5_canonical_source_manifest_hash_mismatch",
        f"D5 {consumer} canonical view is bound to another manifest",
    )
    source_content_hash = _d5_source_content_sha256(manifest)
    _expect_equal(
        source.get("content_sha256"),
        source_content_hash,
        "d5_canonical_source_content_hash_mismatch",
        f"D5 {consumer} source content hash differs",
    )
    _expect_equal(
        source.get("split_sha256"),
        manifest.get("split_sha256"),
        "d5_canonical_source_split_hash_mismatch",
        f"D5 {consumer} source split hash differs",
    )
    _expect_equal(
        source.get("training_set_sha256"),
        manifest.get("training_set_sha256"),
        "d5_canonical_source_training_hash_mismatch",
        f"D5 {consumer} source training-set hash differs",
    )
    _expect_equal(
        _nonnegative_int(source.get("episode_count"), "D5 source episode_count"),
        len(entries),
        "d5_canonical_source_episode_count_mismatch",
        f"D5 {consumer} source episode count differs",
    )
    _expect_equal(
        _nonnegative_int(
            source.get("unique_seed_count"), "D5 source unique_seed_count"
        ),
        100,
        "d5_canonical_source_seed_count_mismatch",
        f"D5 {consumer} source seed count differs",
    )
    schema_versions = _mapping(source.get("schema_versions"), "D5 schema versions")
    for key, value in schema_versions.items():
        _expect_equal(
            manifest.get(key),
            value,
            "d5_canonical_source_schema_identity_mismatch",
            f"D5 {consumer} source schema differs at {key}",
        )

    _expect_equal(
        view.get("training_seed_registry"),
        {
            "schema_version": "scalable3d-training-seed-registry-v1",
            "file_sha256": registry["training_file_sha256"],
        },
        "d5_canonical_training_registry_binding_mismatch",
        f"D5 {consumer} training registry binding differs",
    )
    _expect_equal(
        view.get("shared_seed_registry"),
        {
            "schema_version": "scalable3d-shared-seed-split-registry-v1",
            "policy_version": "scalable3d-numeric-seed-atomic-split-v1",
            "file_sha256": registry["shared_file_sha256"],
            "content_sha256": registry["shared_content_sha256"],
            "assignment_sha256": registry["assignment_sha256"],
        },
        "d5_canonical_shared_registry_binding_mismatch",
        f"D5 {consumer} shared registry binding differs",
    )
    _expect_equal(
        view.get("view_contract"),
        {
            "source_manifest_modified": False,
            "source_artifacts_modified": False,
            "complete_episode_rebucket_only": True,
            "sample_copy_allowed": False,
            "online_offline_content_rewrite_allowed": False,
            "default_legacy_loader_unchanged": True,
        },
        "d5_canonical_view_contract_mismatch",
        f"D5 {consumer} canonical view contract changed",
    )

    canonical_descriptors = _d5_canonical_descriptors(entries, registry)
    expected_canonical = _d5_canonical_summary(
        consumer, entries, canonical_descriptors, registry
    )
    _expect_equal(
        view.get("canonical_split"),
        expected_canonical,
        "d5_canonical_counts_or_hash_mismatch",
        f"D5 {consumer} canonical split differs from the shared registry",
    )

    _expect_equal(
        readiness.get("schema_version"),
        _D5_READINESS_SCHEMA,
        "d5_readiness_schema_mismatch",
        f"D5 {consumer} readiness schema changed",
    )
    _expect_equal(
        readiness.get("validation_date"),
        CROSS_MODULE_LEARNING_ADMISSION_DATE,
        "d5_readiness_date_mismatch",
        f"D5 {consumer} readiness date changed",
    )
    _expect_equal(
        readiness.get("consumer"),
        consumer,
        "d5_readiness_consumer_mismatch",
        f"D5 {consumer} readiness belongs to another consumer",
    )
    _expect_equal(
        readiness.get("source_manifest_sha256"),
        manifest_file_sha,
        "d5_readiness_source_hash_mismatch",
        f"D5 {consumer} readiness source hash differs",
    )
    _expect_equal(
        readiness.get("view_manifest_sha256"),
        view_file_sha,
        "d5_readiness_view_file_hash_mismatch",
        f"D5 {consumer} readiness is bound to another canonical view file",
    )
    _expect_equal(
        readiness.get("view_content_sha256"),
        claimed_content_hash,
        "d5_readiness_view_content_hash_mismatch",
        f"D5 {consumer} readiness view content hash differs",
    )
    _expect_equal(
        readiness.get("canonical_split"),
        expected_canonical,
        "d5_readiness_canonical_split_mismatch",
        f"D5 {consumer} readiness canonical split differs",
    )
    alignment = _mapping(readiness.get("split_alignment"), "D5 split alignment")
    _expect(
        alignment.get("status") == "pass"
        and alignment.get("joint_training_split_identity_aligned") is True
        and alignment.get("source_manifest_modified") is False,
        "d5_readiness_split_alignment_invalid",
        f"D5 {consumer} readiness does not confirm detached split alignment",
    )
    admission = _mapping(readiness.get("admission"), "D5 admission")
    if consumer == "tracklet_graph":
        _expect(
            admission.get("g1_assist_eligible") is False
            and admission.get("status") == "fail_closed"
            and admission.get("deterministic_geometry_fallback_required") is True,
            "d5_tracklet_admission_overstated",
            "D5 tracklet readiness overstates assist eligibility",
        )
        training_readiness = _mapping(
            readiness.get("training_readiness"), "D5 tracklet training readiness"
        )
        _expect(
            training_readiness.get("passed") is False
            and training_readiness.get("status") == "fail_closed",
            "d5_tracklet_training_gate_overstated",
            "D5 tracklet training readiness must remain fail closed",
        )
        sample_count = sum(
            _nonnegative_int(item.get("edge_count"), "D5 tracklet edge_count")
            for item in entries
        )
        label_availability: Mapping[str, Any] | None = None
    else:
        _expect(
            admission.get("behavior_cloning_view_available") is True
            and admission.get("ppo") is False
            and admission.get("assist") is False
            and admission.get("rule_fallback_required") is True
            and admission.get("status") == "development_shadow_only",
            "d5_active_admission_overstated",
            "D5 active-vision readiness overstates learning admission",
        )
        label_availability = _validate_unavailable_label_set(
            manifest.get("availability"),
            expected_sample_count=sum(
                _nonnegative_int(item.get("sample_count"), "D5 active sample_count")
                for item in entries
            ),
            context="D5 formal active vision",
        )
        _expect_equal(
            readiness.get("offline_label_availability"),
            label_availability,
            "d5_active_readiness_label_availability_mismatch",
            "D5 active readiness label availability differs from the manifest",
        )
        sample_count = sum(
            _nonnegative_int(item.get("sample_count"), "D5 active sample_count")
            for item in entries
        )

    result = {
        "classification": "formal_observation_corpus",
        "consumer": consumer,
        "manifest_schema_version": manifest["schema_version"],
        "manifest_file_sha256": manifest_file_sha,
        "canonical_view_schema_version": view["schema_version"],
        "canonical_view_file_sha256": view_file_sha,
        "canonical_view_content_sha256": claimed_content_hash,
        "readiness_file_sha256": _sha256_file(readiness_path),
        "episode_count": len(entries),
        "canonical_seed_counts": dict(_EXPECTED_SEED_COUNTS),
        "reserved_seed_leakage_count": 0,
        "online_truth_use_count": 0,
        "canonical_view_available": True,
        "full_sample_audit_completed_by_d6": False,
        "sample_count": sample_count,
    }
    if consumer == "tracklet_graph":
        class_balance_by_split = _mapping(
            expected_canonical.get("class_balance_by_split"),
            "D5 tracklet canonical class balance",
        )
        label_totals = {
            name: sum(
                _nonnegative_int(
                    _mapping(class_balance_by_split.get(split), "D5 class split").get(
                        name
                    ),
                    f"D5 {split} {name}",
                )
                for split in _SPLITS
            )
            for name in (
                "candidate_edges",
                "positive_candidate_edges",
                "negative_candidate_edges",
                "unlabeled_candidate_edges",
            )
        }
        _expect_equal(
            label_totals["candidate_edges"],
            label_totals["positive_candidate_edges"]
            + label_totals["negative_candidate_edges"]
            + label_totals["unlabeled_candidate_edges"],
            "d5_tracklet_label_inventory_mismatch",
            "D5 tracklet labeled and unlabeled counts do not cover candidate edges",
        )
        _expect_equal(
            label_totals["candidate_edges"],
            sample_count,
            "d5_tracklet_candidate_edge_inventory_mismatch",
            "D5 tracklet class balance differs from the candidate edge inventory",
        )
        labeled_count = (
            label_totals["positive_candidate_edges"]
            + label_totals["negative_candidate_edges"]
        )
        unlabeled_count = label_totals["unlabeled_candidate_edges"]
        labels_complete = unlabeled_count == 0
        label_status = (
            "complete"
            if labels_complete
            else "partial"
            if labeled_count > 0
            else "unavailable"
        )
        result.update(
            {
                "candidate_edge_count": sample_count,
                "evaluator_label_schema_version": manifest[
                    "evaluator_label_schema_version"
                ],
                "association_label_summary": {
                    "available": labeled_count > 0,
                    "complete": labels_complete,
                    "status": label_status,
                    "candidate_edge_count": label_totals["candidate_edges"],
                    "positive_labeled_count": label_totals[
                        "positive_candidate_edges"
                    ],
                    "negative_labeled_count": label_totals[
                        "negative_candidate_edges"
                    ],
                    "labeled_count": labeled_count,
                    "unlabeled_count": unlabeled_count,
                },
                "training_readiness": "fail_closed",
            }
        )
    else:
        result.update(
            {
                "offline_label_availability": label_availability,
                "training_readiness": "development_shadow_only",
            }
        )
    return result


def _audit_d4_supplemental(
    path: Path, registry: Mapping[str, Any]
) -> dict[str, Any]:
    summary = _read_json_object(path, "D4 supplemental curriculum summary")
    _expect_equal(
        summary.get("schema"),
        "d4-region-action-coverage-summary-v1",
        "d4_supplemental_schema_mismatch",
        "D4 supplemental evidence is not an action-coverage summary",
    )
    _validate_claimed_content_hash(
        summary, "content_sha256", "d4_supplemental_content_hash_mismatch"
    )
    _expect_equal(
        summary.get("purpose"),
        "behavior_cloning_and_offline_shadow_evaluation_only",
        "d4_supplemental_purpose_mismatch",
        "D4 supplemental curriculum purpose changed",
    )
    source = _mapping(summary.get("source_binding"), "D4 supplemental source")
    expected_source = {
        "training_seed_registry_schema": "scalable3d-training-seed-registry-v1",
        "training_seed_registry_sha256": registry["training_file_sha256"],
        "shared_seed_registry_schema": "scalable3d-shared-seed-split-registry-v1",
        "shared_seed_registry_sha256": registry["shared_file_sha256"],
    }
    for field, expected in expected_source.items():
        _expect_equal(
            source.get(field),
            expected,
            "d4_supplemental_registry_binding_mismatch",
            f"D4 supplemental source differs at {field}",
        )
    dataset = _mapping(summary.get("dataset"), "D4 supplemental dataset")
    _expect_equal(
        dataset.get("schema"),
        "d4-region-learning-dataset-v1",
        "d4_supplemental_dataset_schema_mismatch",
        "D4 supplemental dataset schema changed",
    )
    episode_count = _nonnegative_int(
        dataset.get("episode_count"), "D4 supplemental episode_count"
    )
    frame_count = _nonnegative_int(
        dataset.get("frame_count"), "D4 supplemental frame_count"
    )
    _expect_equal(
        (episode_count, frame_count, dataset.get("numeric_seed_count")),
        (100, 300, 100),
        "d4_supplemental_inventory_mismatch",
        "D4 supplemental inventory differs from the frozen curriculum",
    )
    _expect_equal(
        _nonnegative_int(
            dataset.get("dirty_episode_count"), "D4 supplemental dirty count"
        ),
        0,
        "d4_supplemental_dirty_source",
        "D4 supplemental curriculum contains dirty episodes",
    )
    _require_sha256(dataset.get("dataset_sha256"), "D4 supplemental dataset SHA")

    canonical = _mapping(summary.get("canonical"), "D4 supplemental canonical")
    binding = _mapping(canonical.get("binding"), "D4 supplemental binding")
    _expect_equal(
        binding.get("schema"),
        _D4_FORMAL_BINDING_SCHEMA,
        "d4_supplemental_binding_schema_mismatch",
        "D4 supplemental binding schema changed",
    )
    binding_content = dict(binding)
    claimed_view_hash = _require_sha256(
        binding_content.pop("view_sha256", None), "D4 supplemental view hash"
    )
    _expect_equal(
        _sha256_json(binding_content),
        claimed_view_hash,
        "d4_supplemental_view_content_hash_mismatch",
        "D4 supplemental canonical view content hash failed",
    )
    expected_catalog = _canonical_seed_values(registry)
    for split in _SPLITS:
        _expect_equal(
            binding.get(f"{split}_seeds"),
            expected_catalog[split],
            "d4_supplemental_seed_assignment_mismatch",
            f"D4 supplemental {split} seeds differ from the shared registry",
        )
    _expect_equal(
        binding.get("reserved_evaluation_seeds"),
        list(registry["reserved_seeds"]),
        "d4_supplemental_reserved_catalog_mismatch",
        "D4 supplemental reserved seed catalog differs",
    )
    for field, expected in {
        "training_seed_registry_sha256": registry["training_file_sha256"],
        "shared_registry_file_sha256": registry["shared_file_sha256"],
        "shared_registry_content_sha256": registry["shared_content_sha256"],
        "assignment_sha256": registry["assignment_sha256"],
        "episode_count": episode_count,
        "frame_count": frame_count,
    }.items():
        _expect_equal(
            binding.get(field),
            expected,
            "d4_supplemental_binding_mismatch",
            f"D4 supplemental binding differs at {field}",
        )
    canonical_split = _mapping(
        canonical.get("canonical_split"), "D4 supplemental canonical split"
    )
    _expect_equal(
        canonical_split.get("seed_counts"),
        dict(_EXPECTED_SEED_COUNTS),
        "d4_supplemental_seed_count_mismatch",
        "D4 supplemental canonical seed counts differ",
    )
    _expect_equal(
        _count_mapping(
            canonical_split.get("episode_counts"),
            "D4 supplemental canonical episode_counts",
        ),
        {"train": 60, "validation": 20, "test": 20},
        "d4_supplemental_episode_split_mismatch",
        "D4 supplemental canonical episode counts differ from 60/20/20",
    )
    _expect_equal(
        _count_mapping(
            canonical_split.get("frame_counts"),
            "D4 supplemental canonical frame_counts",
        ),
        {"train": 180, "validation": 60, "test": 60},
        "d4_supplemental_frame_split_mismatch",
        "D4 supplemental canonical frame counts differ from 180/60/60",
    )
    _expect(
        canonical_split.get("numeric_seed_atomic") is True
        and canonical_split.get("reserved_seed_present") is False,
        "d4_supplemental_seed_isolation_invalid",
        "D4 supplemental canonical seed isolation failed",
    )

    inventory = _mapping(summary.get("action_inventory"), "D4 action inventory")
    total = _mapping(inventory.get("total"), "D4 action total")
    action_coverage = {
        "hold": _nonnegative_int(total.get("hold_true_count"), "D4 hold"),
        "request_replan": _nonnegative_int(
            total.get("request_replan_true_count"), "D4 request_replan"
        ),
        "nonzero_quota": _nonnegative_int(
            total.get("resource_quota_nonzero_count"), "D4 nonzero quota"
        ),
        "transfer": _nonnegative_int(total.get("transfer_count"), "D4 transfer"),
    }
    _expect_equal(
        action_coverage,
        {"hold": 100, "request_replan": 200, "nonzero_quota": 200, "transfer": 100},
        "d4_supplemental_action_coverage_mismatch",
        "D4 supplemental action coverage differs from the frozen summary",
    )
    outcome = _mapping(summary.get("outcome_and_reward"), "D4 outcome/reward")
    _expect(
        outcome.get("outcome_availability") == "unavailable"
        and outcome.get("reward_availability") == "unavailable"
        and _nonnegative_int(
            outcome.get("reward_available_count"), "D4 reward available"
        )
        == 0
        and _nonnegative_int(
            outcome.get("reward_unavailable_count"), "D4 reward unavailable"
        )
        == frame_count,
        "d4_supplemental_reward_or_outcome_overstated",
        "D4 supplemental curriculum must keep reward and outcome unavailable",
    )
    safety = _mapping(summary.get("safety"), "D4 safety")
    truth = _mapping(summary.get("truth_isolation"), "D4 truth isolation")
    _expect(
        _nonnegative_int(
            safety.get("hard_constraint_violation_count"),
            "D4 hard constraint violations",
        )
        == 0
        and safety.get("resource_conservation_verified") is True,
        "d4_supplemental_safety_invalid",
        "D4 supplemental curriculum violates deterministic safety",
    )
    _expect(
        _nonnegative_int(
            truth.get("online_truth_identifier_count"), "D4 online truth count"
        )
        == 0
        and _nonnegative_int(
            truth.get("reserved_evaluation_seed_present_count"),
            "D4 reserved seed count",
        )
        == 0,
        "d4_supplemental_truth_or_reserved_leakage",
        "D4 supplemental curriculum leaks truth or reserved seeds",
    )
    admission = _mapping(summary.get("admission"), "D4 supplemental admission")
    _expect(
        admission.get("behavior_cloning_manifest_available") is True
        and admission.get("online_assist_available") is False
        and admission.get("online_authority_available") is False
        and admission.get("ppo_available") is False
        and admission.get("formal_900_episode_dataset_modified") is False,
        "d4_supplemental_admission_overstated",
        "D4 supplemental curriculum overstates admission",
    )
    audit = _mapping(summary.get("audit"), "D4 supplemental audit")
    _expect(
        audit.get("passed") is True and audit.get("violations") == [],
        "d4_supplemental_audit_failed",
        "D4 supplemental producer audit did not pass",
    )
    return {
        "classification": "supplemental_rule_teacher_curriculum",
        "summary_file_sha256": _sha256_file(path),
        "summary_content_sha256": summary["content_sha256"],
        "dataset_sha256": dataset["dataset_sha256"],
        "dataset_manifest_sha256": binding[
            "source_dataset_manifest_file_sha256"
        ],
        "canonical_view_content_sha256": claimed_view_hash,
        "episode_count": episode_count,
        "frame_count": frame_count,
        "canonical_seed_counts": dict(_EXPECTED_SEED_COUNTS),
        "canonical_episode_counts": {"train": 60, "validation": 20, "test": 20},
        "canonical_frame_counts": {"train": 180, "validation": 60, "test": 60},
        "reserved_seed_leakage_count": 0,
        "dirty_episode_count": 0,
        "online_truth_use_count": 0,
        "reward_available_count": 0,
        "reward_sample_count": frame_count,
        "outcome_available": False,
        "canonical_view_available": True,
        "formal_corpus_modified": False,
        "action_coverage": action_coverage,
    }


def _audit_d5_supplemental(
    path: Path, registry: Mapping[str, Any]
) -> dict[str, Any]:
    summary = _read_json_object(path, "D5 supplemental curriculum summary")
    _expect_equal(
        summary.get("schema_version"),
        "d5.active-vision-supplemental-curriculum-summary.v1",
        "d5_supplemental_schema_mismatch",
        "D5 supplemental evidence is not the expected curriculum summary",
    )
    _validate_claimed_content_hash(
        summary, "content_sha256", "d5_supplemental_content_hash_mismatch"
    )
    _expect_equal(
        summary.get("purpose"),
        "synthetic_behavior_cloning_development_and_offline_shadow_only",
        "d5_supplemental_purpose_mismatch",
        "D5 supplemental curriculum purpose changed",
    )
    source = _mapping(summary.get("source_binding"), "D5 supplemental source")
    expected_source = {
        "training_seed_registry_schema_version": "scalable3d-training-seed-registry-v1",
        "training_seed_registry_sha256": registry["training_file_sha256"],
        "shared_seed_registry_schema_version": "scalable3d-shared-seed-split-registry-v1",
        "shared_seed_registry_sha256": registry["shared_file_sha256"],
        "shared_seed_registry_content_sha256": registry["shared_content_sha256"],
        "shared_seed_registry_assignment_sha256": registry["assignment_sha256"],
    }
    for field, expected in expected_source.items():
        _expect_equal(
            source.get(field),
            expected,
            "d5_supplemental_registry_binding_mismatch",
            f"D5 supplemental source differs at {field}",
        )
    _expect(
        source.get("repository_dirty") is False,
        "d5_supplemental_dirty_source",
        "D5 supplemental curriculum belongs to a dirty source",
    )
    dataset_config_sha256 = _require_sha256(
        source.get("dataset_config_sha256"),
        "D5 supplemental dataset config SHA",
    )
    source_git_commit = _require_git_commit(
        source.get("git_commit"), "D5 supplemental source Git commit"
    )
    dataset = _mapping(summary.get("dataset"), "D5 supplemental dataset")
    episode_count = _nonnegative_int(
        dataset.get("episode_count"), "D5 supplemental episode_count"
    )
    sample_count = _nonnegative_int(
        dataset.get("sample_count"), "D5 supplemental sample_count"
    )
    _expect_equal(
        (episode_count, sample_count, dataset.get("unique_seed_count")),
        (100, 1200, 100),
        "d5_supplemental_inventory_mismatch",
        "D5 supplemental inventory differs from the frozen curriculum",
    )
    _require_sha256(dataset.get("manifest_sha256"), "D5 supplemental manifest SHA")
    _require_sha256(dataset.get("content_sha256"), "D5 supplemental content SHA")

    canonical = _mapping(summary.get("canonical"), "D5 supplemental canonical")
    canonical_view_sha256 = _require_sha256(
        canonical.get("view_manifest_sha256"),
        "D5 supplemental canonical view SHA",
    )
    split = _mapping(canonical.get("split"), "D5 supplemental canonical split")
    _validate_canonical_split_catalog(split, registry, context="D5 supplemental")
    _expect_equal(
        split.get("episode_counts"),
        {"train": 60, "validation": 20, "test": 20},
        "d5_supplemental_episode_split_mismatch",
        "D5 supplemental canonical episode counts differ",
    )
    _expect_equal(
        split.get("sample_counts"),
        {"train": 720, "validation": 240, "test": 240},
        "d5_supplemental_sample_split_mismatch",
        "D5 supplemental canonical sample counts differ",
    )

    coverage = _mapping(summary.get("coverage"), "D5 supplemental coverage")
    intent = _count_mapping(coverage.get("intent_counts"), "D5 intent counts")
    fov = _count_mapping(coverage.get("fov_mode_counts"), "D5 FOV counts")
    camera_role = _count_mapping(
        coverage.get("camera_role_counts"), "D5 camera role counts"
    )
    _expect_equal(
        intent,
        {
            "hold": 200,
            "observe_target": 600,
            "reacquire": 200,
            "search_sector": 200,
        },
        "d5_supplemental_intent_coverage_mismatch",
        "D5 supplemental intent coverage differs from the frozen summary",
    )
    _expect_equal(
        fov,
        {"wide": 1000, "zoom": 200},
        "d5_supplemental_fov_coverage_mismatch",
        "D5 supplemental FOV coverage differs from the frozen summary",
    )
    _expect_equal(
        camera_role,
        {"interceptor": 600, "recon": 600},
        "d5_supplemental_role_coverage_mismatch",
        "D5 supplemental camera-role coverage differs from the frozen summary",
    )
    _expect_equal(
        _nonnegative_int(coverage.get("sample_count"), "D5 coverage sample_count"),
        sample_count,
        "d5_supplemental_coverage_sample_mismatch",
        "D5 coverage sample count differs from the dataset",
    )

    ack = _mapping(summary.get("ack_fault_coverage"), "D5 synthetic ACK coverage")
    ack_counts = _count_mapping(ack.get("counts"), "D5 synthetic ACK counts")
    _expect_equal(
        set(ack_counts),
        {"applied", "rejected", "missing"},
        "d5_supplemental_ack_classes_mismatch",
        "D5 synthetic ACK classes changed",
    )
    _expect_equal(
        sum(ack_counts.values()),
        sample_count,
        "d5_supplemental_ack_count_mismatch",
        "D5 synthetic ACK counts do not cover all samples",
    )
    _expect(
        ack.get("interpretation") == "deterministic_fault_injection_coverage_only"
        and ack.get("runtime_distribution_evidence") is False
        and ack.get("reward_or_outcome_evidence") is False,
        "synthetic_ack_claims_runtime_ack",
        "synthetic ACK coverage must not claim runtime attribution",
    )

    labels = _validate_unavailable_label_set(
        summary.get("offline_label_availability"),
        expected_sample_count=sample_count,
        context="D5 supplemental",
        require_zero_padding_flag=True,
    )
    truth = _mapping(
        summary.get("truth_seed_and_formal_isolation"),
        "D5 supplemental truth isolation",
    )
    _expect(
        truth.get("formal_900_episode_dataset_modified") is False
        and _nonnegative_int(
            truth.get("online_truth_identifier_count"), "D5 online truth count"
        )
        == 0
        and truth.get("reserved_seed_overlap") == [],
        "d5_supplemental_truth_or_formal_isolation_invalid",
        "D5 supplemental curriculum leaks truth, reserved seeds, or formal writes",
    )
    identity = _mapping(
        summary.get("version_and_identity_audit"), "D5 version and identity audit"
    )
    _expect(
        identity.get("global_track_id_created_or_rebound") is False,
        "d5_supplemental_global_track_id_rebound",
        "D5 supplemental curriculum created or rebound global_track_id",
    )
    admission = _mapping(summary.get("admission"), "D5 supplemental admission")
    _expect(
        admission.get("behavior_cloning_view_available") is True
        and admission.get("behavior_cloning_development_eligible") is True
        and admission.get("clean_source") is True
        and admission.get("ppo_available") is False
        and admission.get("online_assist_available") is False
        and admission.get("online_authority_available") is False
        and admission.get("camera_command_authority_available") is False
        and admission.get("rule_fallback_required") is True
        and admission.get("synthetic_curriculum_only") is True,
        "d5_supplemental_admission_overstated",
        "D5 supplemental curriculum overstates learning admission",
    )
    audit = _mapping(summary.get("audit"), "D5 supplemental audit")
    _expect(
        audit.get("passed") is True
        and _nonnegative_int(audit.get("violation_count"), "D5 violation count") == 0
        and audit.get("violations") == [],
        "d5_supplemental_audit_failed",
        "D5 supplemental producer audit did not pass",
    )
    return {
        "classification": "supplemental_rule_teacher_curriculum",
        "summary_file_sha256": _sha256_file(path),
        "summary_content_sha256": summary["content_sha256"],
        "dataset_manifest_sha256": _require_sha256(
            dataset.get("manifest_sha256"), "D5 supplemental manifest SHA"
        ),
        "dataset_content_sha256": _require_sha256(
            dataset.get("content_sha256"), "D5 supplemental content SHA"
        ),
        "dataset_config_sha256": dataset_config_sha256,
        "canonical_view_sha256": canonical_view_sha256,
        "source_git_commit": source_git_commit,
        "training_registry_sha256": registry["training_file_sha256"],
        "shared_registry_sha256": registry["shared_file_sha256"],
        "episode_count": episode_count,
        "segment_count": _nonnegative_int(
            coverage.get("segment_count"), "D5 segment_count"
        ),
        "sample_count": sample_count,
        "canonical_seed_counts": dict(_EXPECTED_SEED_COUNTS),
        "canonical_sample_counts": {"train": 720, "validation": 240, "test": 240},
        "reserved_seed_leakage_count": 0,
        "dirty_episode_count": 0,
        "online_truth_use_count": 0,
        "offline_label_availability": labels,
        "canonical_view_available": True,
        "formal_corpus_modified": False,
        "action_coverage": {
            "intent": intent,
            "fov": fov,
            "camera_role": camera_role,
        },
        "synthetic_ack_fault_coverage": {
            "counts": ack_counts,
            "classification": "deterministic_fault_injection_coverage_only",
            "runtime_attribution": False,
        },
    }


def _audit_d3_full_sample(
    path: Path,
    *,
    expected_file_sha256: str,
    d3_formal: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    """Strictly consume the D3 formal assignment full-sample audit."""

    actual_file_hash = _verify_full_sample_file_hash(
        path,
        expected_file_sha256,
        module="d3",
        label="D3 assignment full-sample audit",
    )
    payload = _read_json_object(path, "D3 assignment full-sample audit")
    _expect_equal(
        set(payload),
        {
            "acceptance_thresholds",
            "action_and_constraint_audit",
            "actual_bindings",
            "admission",
            "artifact_integrity",
            "audit",
            "binding_checks",
            "content_sha256",
            "coverage",
            "evidence_availability",
            "expected_bindings",
            "generation_evidence",
            "purpose",
            "remaining_gates",
            "schema_and_numeric_audit",
            "schema_version",
            "source_files",
            "split_and_provenance_audit",
            "validation_date",
            "version_and_identity_audit",
        },
        "d3_full_sample_audit_fields_mismatch",
        "D3 full-sample audit top-level fields changed",
    )
    _expect_equal(
        payload.get("schema_version"),
        _D3_FULL_SAMPLE_AUDIT_SCHEMA,
        "d3_full_sample_audit_schema_mismatch",
        "D3 full-sample audit schema changed",
    )
    _expect_equal(
        payload.get("validation_date"),
        CROSS_MODULE_LEARNING_ADMISSION_DATE,
        "d3_full_sample_audit_date_mismatch",
        "D3 full-sample audit validation date changed",
    )
    _validate_claimed_content_hash(
        payload,
        "content_sha256",
        "d3_full_sample_audit_content_hash_mismatch",
    )
    _expect_equal(
        payload.get("purpose"),
        _D3_FULL_SAMPLE_AUDIT_PURPOSE,
        "d3_full_sample_audit_purpose_mismatch",
        "D3 full-sample audit purpose changed",
    )

    source_files = _mapping(payload.get("source_files"), "D3 source files")
    _expect_equal(
        set(source_files),
        {
            "batch_export_summary",
            "dataset_frames",
            "dataset_manifest",
            "episode_progress",
            "generation_summary",
            "shared_registry",
            "training_registry",
        },
        "d3_full_sample_source_set_mismatch",
        "D3 full-sample source file set changed",
    )
    _expect(
        all(isinstance(value, str) and value.strip() for value in source_files.values()),
        "d3_full_sample_source_path_invalid",
        "D3 full-sample source paths must be explicit non-empty strings",
    )

    producer_audit = _mapping(payload.get("audit"), "D3 producer audit")
    _expect(
        producer_audit.get("passed") is True
        and producer_audit.get("status") == "partial"
        and _nonnegative_int(
            producer_audit.get("violation_count"), "D3 producer violations"
        )
        == 0
        and producer_audit.get("violations") == []
        and producer_audit.get("violation_details_truncated") is False,
        "d3_full_sample_producer_audit_failed",
        "D3 producer audit is not a clean structural audit",
    )

    expected_bindings = _mapping(
        payload.get("expected_bindings"), "D3 expected bindings"
    )
    actual_bindings = _mapping(
        payload.get("actual_bindings"), "D3 actual bindings"
    )
    expected_binding_fields = {
        "batch_export_summary_sha256",
        "dataset_frames_sha256",
        "dataset_manifest_sha256",
        "dataset_split_hash",
        "episode_progress_sha256",
        "generation_summary_sha256",
        "shared_registry_content_sha256",
        "shared_registry_sha256",
        "source_git_commit",
        "source_schedule_sha256",
        "training_registry_sha256",
    }
    _expect_equal(
        set(expected_bindings),
        expected_binding_fields,
        "d3_full_sample_expected_binding_set_mismatch",
        "D3 expected binding fields changed",
    )
    _expect_equal(
        set(actual_bindings),
        expected_binding_fields
        | {
            "shared_registry_assignment_sha256",
            "shared_registry_declared_assignment_sha256",
        },
        "d3_full_sample_actual_binding_set_mismatch",
        "D3 actual binding fields changed",
    )
    caller_bindings = {
        "dataset_frames_sha256": d3_formal["frames_sha256"],
        "dataset_manifest_sha256": d3_formal["manifest_file_sha256"],
        "shared_registry_content_sha256": registry["shared_content_sha256"],
        "shared_registry_sha256": registry["shared_file_sha256"],
        "source_git_commit": registry["git_commit"],
        "source_schedule_sha256": registry["schedule_sha256"],
        "training_registry_sha256": registry["training_file_sha256"],
    }
    for field in expected_binding_fields:
        expected = expected_bindings.get(field)
        if field == "source_git_commit":
            _require_git_commit(expected, f"D3 expected {field}")
        else:
            _require_sha256(expected, f"D3 expected {field}")
        _expect_equal(
            actual_bindings.get(field),
            expected,
            "d3_full_sample_source_binding_mismatch",
            f"D3 expected/actual binding differs at {field}",
        )
    for field, expected in caller_bindings.items():
        _expect_equal(
            expected_bindings.get(field),
            expected,
            "d3_full_sample_expected_binding_mismatch",
            f"D3 full-sample audit is not bound to the consumed {field}",
        )
    _expect(
        actual_bindings.get("shared_registry_assignment_sha256")
        == registry["assignment_sha256"]
        and actual_bindings.get("shared_registry_declared_assignment_sha256")
        == registry["assignment_sha256"],
        "d3_full_sample_registry_assignment_mismatch",
        "D3 full-sample audit is not bound to the canonical seed assignment",
    )
    _validate_binding_checks(
        payload.get("binding_checks"),
        expected_bindings,
        module="d3",
    )

    thresholds = _mapping(
        payload.get("acceptance_thresholds"), "D3 acceptance thresholds"
    )
    expected_episode_split = {"train": 540, "validation": 180, "test": 180}
    expected_frame_split = {"train": 962, "validation": 320, "test": 322}
    expected_edge_split = {
        "train": 2_229_182,
        "validation": 721_445,
        "test": 708_188,
    }
    expected_selected_split = {
        "train": 71_425,
        "validation": 23_147,
        "test": 22_732,
    }
    _expect(
        _nonnegative_int(thresholds.get("episode_count"), "D3 threshold episodes")
        == 900
        and _nonnegative_int(
            thresholds.get("decision_sample_count"), "D3 threshold samples"
        )
        == 1604
        and _nonnegative_int(
            thresholds.get("candidate_edge_count"), "D3 threshold edges"
        )
        == 3_658_815
        and _nonnegative_int(
            thresholds.get("action_label_count"), "D3 threshold labels"
        )
        == 3_658_815
        and _nonnegative_int(
            thresholds.get("selected_action_count"), "D3 threshold actions"
        )
        == 117_304
        and _count_mapping(
            thresholds.get("canonical_episode_counts"),
            "D3 threshold canonical seed counts",
        )
        == dict(_EXPECTED_SEED_COUNTS)
        and _count_mapping(
            thresholds.get("actual_episode_counts"),
            "D3 threshold episode split",
        )
        == expected_episode_split
        and _count_mapping(
            thresholds.get("actual_frame_counts"), "D3 threshold frame split"
        )
        == expected_frame_split
        and all(
            _nonnegative_int(thresholds.get(field), f"D3 threshold {field}") == 0
            for field in (
                "audit_violation_count_maximum",
                "constraint_violation_count_maximum",
                "dirty_episode_count_maximum",
                "global_track_id_illegal_field_count_maximum",
                "online_truth_use_count_maximum",
                "reserved_seed_overlap_maximum",
            )
        ),
        "d3_full_sample_threshold_mismatch",
        "D3 full-sample acceptance thresholds changed",
    )

    coverage = _mapping(payload.get("coverage"), "D3 full-sample coverage")
    expected_coverage_counts = {
        "episode_count": 900,
        "frame_count": 1604,
        "decision_sample_count": 1604,
        "candidate_edge_count": 3_658_815,
        "edge_sample_count": 3_658_815,
        "resource_target_action_label_count": 3_658_815,
        "selected_resource_target_action_count": 117_304,
        "anonymous_resource_record_count": 120_080,
        "anonymous_target_record_count": 118_109,
        "feature_value_count": 43_905_780,
        "training_seed_count": 100,
    }
    _expect(
        all(
            _nonnegative_int(coverage.get(field), f"D3 coverage {field}") == expected
            for field, expected in expected_coverage_counts.items()
        )
        and _count_mapping(
            coverage.get("actual_episode_counts"), "D3 coverage episodes"
        )
        == expected_episode_split
        and _count_mapping(coverage.get("actual_frame_counts"), "D3 coverage frames")
        == expected_frame_split
        and _count_mapping(
            coverage.get("canonical_episode_counts"), "D3 canonical seed identities"
        )
        == dict(_EXPECTED_SEED_COUNTS)
        and _count_mapping(
            coverage.get("split_candidate_edge_counts"), "D3 split candidate edges"
        )
        == expected_edge_split
        and _count_mapping(
            coverage.get("split_action_label_counts"), "D3 split action labels"
        )
        == expected_edge_split
        and _count_mapping(
            coverage.get("split_selected_action_counts"), "D3 selected actions"
        )
        == expected_selected_split,
        "d3_full_sample_inventory_mismatch",
        "D3 full-sample inventory differs from the producer declaration",
    )
    _expect(
        d3_formal["episode_count"] == 900
        and d3_formal["frame_count"] == 1604
        and d3_formal["canonical_episode_counts"] == expected_episode_split
        and d3_formal["canonical_frame_counts"] == expected_frame_split,
        "d3_full_sample_formal_inventory_binding_mismatch",
        "D3 producer counts differ from the consumed formal manifest",
    )

    generation = _mapping(
        payload.get("generation_evidence"), "D3 generation evidence"
    )
    _expect(
        _nonnegative_int(generation.get("episode_count"), "D3 generated episodes")
        == 900
        and _nonnegative_int(
            generation.get("exported_frame_count"), "D3 exported frames"
        )
        == 1604
        and _nonnegative_int(
            generation.get("finite_episode_count"), "D3 finite episodes"
        )
        == 900
        and _nonnegative_int(
            generation.get("dirty_episode_count"), "D3 dirty episodes"
        )
        == 0
        and _nonnegative_int(
            generation.get("online_truth_use_count"), "D3 truth use"
        )
        == 0
        and _count_mapping(generation.get("scale_counts"), "D3 scale counts")
        == {"5": 180, "20": 180, "50": 180, "100": 180, "200": 180}
        and _count_mapping(
            generation.get("scenario_counts"), "D3 scenario counts"
        )
        == {
            "center_failure": 100,
            "communication_degraded": 100,
            "delayed_noisy": 100,
            "dense_crossing": 100,
            "evasive_multilevel": 100,
            "formation_split": 100,
            "high_threat_m_to_n": 100,
            "nominal": 100,
            "secondary_failure": 100,
        }
        and _nonnegative_int(
            generation.get("unavailable_frame_count"), "D3 unavailable frames"
        )
        == 194,
        "d3_full_sample_generation_count_mismatch",
        "D3 generation evidence counts changed",
    )

    provenance = _mapping(
        payload.get("split_and_provenance_audit"), "D3 provenance audit"
    )
    _expect(
        _count_mapping(
            provenance.get("actual_decision_sample_counts"),
            "D3 provenance sample counts",
        )
        == expected_frame_split
        and _count_mapping(
            provenance.get("actual_source_episode_counts"),
            "D3 provenance episode counts",
        )
        == expected_episode_split
        and _count_mapping(
            provenance.get("canonical_episode_identity_counts"),
            "D3 canonical identity counts",
        )
        == dict(_EXPECTED_SEED_COUNTS)
        and _nonnegative_int(
            provenance.get("dirty_episode_count"), "D3 provenance dirty episodes"
        )
        == 0
        and _nonnegative_int(
            provenance.get("online_truth_use_count"), "D3 provenance truth use"
        )
        == 0
        and provenance.get("repository_dirty") is False
        and provenance.get("reserved_evaluation_seeds")
        == list(_EXPECTED_RESERVED_SEEDS)
        and provenance.get("reserved_seed_overlap") == []
        and provenance.get("source_git_commit") == registry["git_commit"]
        and provenance.get("source_schedule_sha256") == registry["schedule_sha256"],
        "d3_full_sample_provenance_failed",
        "D3 full-sample seed, truth, or clean-source provenance failed",
    )

    numeric = _mapping(
        payload.get("schema_and_numeric_audit"), "D3 numeric audit"
    )
    _expect(
        numeric.get("dataset_schema_version") == "d3_learning_dataset_v2"
        and numeric.get("split_policy_version")
        == "d3_numeric_seed_atomic_split_v2"
        and _nonnegative_int(
            numeric.get("validated_frame_count"), "D3 validated frames"
        )
        == 1604
        and _nonnegative_int(
            numeric.get("feature_value_count"), "D3 feature values"
        )
        == 43_905_780
        and numeric.get("all_validated_numeric_features_finite") is True
        and _nonnegative_int(
            numeric.get("nonfinite_numeric_value_count"), "D3 non-finite values"
        )
        == 0
        and _nonnegative_int(
            numeric.get("candidate_dimension_mismatch_count"),
            "D3 dimension mismatches",
        )
        == 0,
        "d3_full_sample_numeric_audit_failed",
        "D3 full-sample schema or numeric audit failed",
    )

    identity = _mapping(
        payload.get("version_and_identity_audit"), "D3 identity audit"
    )
    _expect(
        _nonnegative_int(
            identity.get("version_checked_frame_count"), "D3 version-checked frames"
        )
        == 1604
        and _nonnegative_int(
            identity.get("anonymous_ordinal_identity_checked_frame_count"),
            "D3 identity-checked frames",
        )
        == 1604
        and all(
            _nonnegative_int(identity.get(field), f"D3 identity {field}") == 0
            for field in (
                "frame_sequence_violation_count",
                "global_track_id_illegal_field_count",
                "online_identity_field_occurrence_count",
                "previous_plan_version_regression_count",
                "timestamp_sequence_violation_count",
            )
        )
        and identity.get("global_track_id_created_or_rewritten") is False
        and identity.get("current_plan_owner_binding") == "unavailable"
        and identity.get("current_plan_version_binding") == "unavailable"
        and identity.get("stale_plan_runtime_rejection_evidence") == "unavailable",
        "d3_full_sample_identity_or_version_failed",
        "D3 identity, version, or unavailable-evidence boundary failed",
    )

    constraints = _mapping(
        payload.get("action_and_constraint_audit"), "D3 constraint audit"
    )
    _expect(
        _nonnegative_int(
            constraints.get("constraint_checked_frame_count"),
            "D3 constraint-checked frames",
        )
        == 1604
        and _nonnegative_int(
            constraints.get("candidate_edge_count"), "D3 constraint edges"
        )
        == 3_658_815
        and _nonnegative_int(
            constraints.get("resource_target_action_label_count"),
            "D3 constraint labels",
        )
        == 3_658_815
        and _nonnegative_int(
            constraints.get("selected_resource_target_action_count"),
            "D3 selected actions",
        )
        == 117_304
        and all(
            _nonnegative_int(constraints.get(field), f"D3 constraint {field}") == 0
            for field in (
                "action_index_violation_count",
                "capacity_violation_count",
                "demand_slot_violation_count",
            )
        ),
        "d3_full_sample_constraint_audit_failed",
        "D3 action index, capacity, or demand-slot audit failed",
    )

    integrity = _mapping(payload.get("artifact_integrity"), "D3 integrity")
    before = _mapping(integrity.get("source_hashes_before"), "D3 source hashes before")
    after = _mapping(integrity.get("source_hashes_after"), "D3 source hashes after")
    _expect(
        _nonnegative_int(integrity.get("source_file_count"), "D3 source file count")
        == 7
        and integrity.get("dataset_manifest_frames_binding_valid") is True
        and integrity.get("formal_source_data_modified") is False
        and integrity.get("source_artifacts_unchanged") is True
        and before == after
        and set(before) == set(source_files),
        "d3_full_sample_artifact_integrity_failed",
        "D3 source artifacts are incomplete or changed during audit",
    )
    _require_sha256(
        integrity.get("source_artifact_set_sha256"), "D3 source artifact set SHA"
    )

    evidence = _mapping(
        payload.get("evidence_availability"), "D3 evidence availability"
    )
    _expect(
        evidence.get("causal_or_counterfactual_reward") == "unavailable"
        and evidence.get("real_runtime_applied_ack") == "unavailable"
        and evidence.get("real_runtime_outcome_attribution") == "unavailable"
        and evidence.get("same_seed_paired_shadow_non_degradation") == "unavailable"
        and evidence.get("zero_padding_used_for_unavailable_evidence") is False
        and _nonnegative_int(
            evidence.get("offline_rule_teacher_reward_component_frame_count"),
            "D3 rule-teacher diagnostic frames",
        )
        == 1604,
        "d3_full_sample_availability_overstated",
        "D3 unavailable runtime evidence was promoted or zero-imputed",
    )
    producer_admission = _mapping(
        payload.get("admission"), "D3 producer admission"
    )
    _expect(
        producer_admission.get("assignment_full_sample_structural_audit")
        == "complete"
        and producer_admission.get("overall_status") == "partial"
        and producer_admission.get("runtime_plan_binding_evidence") == "partial"
        and producer_admission.get("model_training_performed") is False
        and producer_admission.get("weights_written") is False
        and producer_admission.get("ppo") is False
        and producer_admission.get("assist") is False
        and producer_admission.get("online_authority") is False
        and producer_admission.get("rule_cost_and_hungarian_default") is True
        and producer_admission.get("rule_fallback_required") is True,
        "d3_full_sample_admission_overstated",
        "D3 full-sample audit opened training, assist, or authority",
    )

    return {
        "status": "complete",
        "complete": True,
        "scope": "d3_formal_assignment_structural_behavior_cloning",
        "audit_file_sha256": actual_file_hash,
        "audit_content_sha256": payload["content_sha256"],
        "manifest_file_sha256": d3_formal["manifest_file_sha256"],
        "training_registry_sha256": registry["training_file_sha256"],
        "shared_registry_sha256": registry["shared_file_sha256"],
        "episode_count": 900,
        "frame_count": 1604,
        "canonical_seed_counts": dict(_EXPECTED_SEED_COUNTS),
        "canonical_episode_counts": expected_episode_split,
        "canonical_frame_counts": expected_frame_split,
        "candidate_edge_count": 3_658_815,
        "selected_action_count": 117_304,
        "finite_feature_value_count": 43_905_780,
        "online_truth_use_count": 0,
        "reserved_seed_leakage_count": 0,
        "dirty_episode_count": 0,
        "runtime_reward_available": False,
        "rule_teacher_reward_components_are_runtime_reward": False,
        "ppo_allowed": False,
        "assist_allowed": False,
        "authority_allowed": False,
        "rule_fallback_required": True,
        "remaining_blockers": [
            "real_runtime_assignment_applied_ack",
            "real_runtime_outcome_attribution",
            "causal_or_counterfactual_reward",
            "same_seed_paired_shadow_non_degradation",
            "current_plan_owner_and_version_runtime_binding",
        ],
    }


def _audit_d4_full_sample(
    path: Path,
    *,
    expected_file_sha256: str,
    d4_formal: Mapping[str, Any],
    d4_supplemental: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    """Strictly consume D4's formal plus supplemental full-sample audit."""

    actual_file_hash = _verify_full_sample_file_hash(
        path,
        expected_file_sha256,
        module="d4",
        label="D4 regional full-sample audit",
    )
    payload = _read_json_object(path, "D4 regional full-sample audit")
    _expect_equal(
        set(payload),
        {
            "actual_bindings",
            "admission",
            "artifact_integrity",
            "audit",
            "audit_mode",
            "binding_checks",
            "content_sha256",
            "evidence_availability",
            "expected_bindings",
            "formal_corpus",
            "purpose",
            "remaining_gates",
            "schema",
            "source_paths",
            "status",
            "supplemental_curriculum",
            "validation_date",
        },
        "d4_full_sample_audit_fields_mismatch",
        "D4 full-sample audit top-level fields changed",
    )
    _expect_equal(
        payload.get("schema"),
        _D4_FULL_SAMPLE_AUDIT_SCHEMA,
        "d4_full_sample_audit_schema_mismatch",
        "D4 full-sample audit schema changed",
    )
    _expect_equal(
        payload.get("validation_date"),
        CROSS_MODULE_LEARNING_ADMISSION_DATE,
        "d4_full_sample_audit_date_mismatch",
        "D4 full-sample audit validation date changed",
    )
    _validate_claimed_content_hash(
        payload,
        "content_sha256",
        "d4_full_sample_audit_content_hash_mismatch",
    )
    _expect_equal(
        payload.get("purpose"),
        _D4_FULL_SAMPLE_AUDIT_PURPOSE,
        "d4_full_sample_audit_purpose_mismatch",
        "D4 full-sample audit purpose changed",
    )
    _expect_equal(
        payload.get("audit_mode"),
        "read_only_fail_closed",
        "d4_full_sample_audit_mode_mismatch",
        "D4 full-sample audit is not read-only fail-closed",
    )

    source_paths = _mapping(payload.get("source_paths"), "D4 source paths")
    _expect_equal(
        set(source_paths),
        {
            "formal_dataset",
            "shared_seed_registry",
            "supplemental_canonical_view",
            "supplemental_dataset",
            "supplemental_summary",
            "training_seed_registry",
        },
        "d4_full_sample_source_set_mismatch",
        "D4 full-sample source path set changed",
    )
    _expect(
        all(isinstance(value, str) and value.strip() for value in source_paths.values()),
        "d4_full_sample_source_path_invalid",
        "D4 full-sample source paths must be explicit non-empty strings",
    )

    producer_audit = _mapping(payload.get("audit"), "D4 producer audit")
    _expect(
        producer_audit.get("passed") is True
        and producer_audit.get("fail_closed") is True
        and _nonnegative_int(
            producer_audit.get("violation_count"), "D4 producer violations"
        )
        == 0
        and producer_audit.get("violations") == []
        and producer_audit.get("common_violations") == []
        and producer_audit.get("formal_violations") == []
        and producer_audit.get("supplemental_violations") == [],
        "d4_full_sample_producer_audit_failed",
        "D4 producer full-sample audit did not pass cleanly",
    )
    status = _mapping(payload.get("status"), "D4 producer status")
    _expect_equal(
        dict(status),
        {
            "combined_full_sample": "complete",
            "formal_full_sample": "complete",
            "supplemental_full_sample": "complete",
        },
        "d4_full_sample_status_invalid",
        "D4 formal, supplemental, and combined status must all be complete",
    )

    expected_bindings = _mapping(
        payload.get("expected_bindings"), "D4 expected bindings"
    )
    actual_bindings = _mapping(
        payload.get("actual_bindings"), "D4 actual bindings"
    )
    binding_fields = {
        "formal_dataset_sha256",
        "formal_manifest_sha256",
        "formal_source_git_commit",
        "shared_registry_sha256",
        "supplemental_canonical_view_sha256",
        "supplemental_dataset_sha256",
        "supplemental_manifest_sha256",
        "supplemental_source_git_commit",
        "supplemental_summary_content_sha256",
        "supplemental_summary_file_sha256",
        "training_registry_sha256",
    }
    _expect_equal(
        set(expected_bindings),
        binding_fields,
        "d4_full_sample_expected_binding_set_mismatch",
        "D4 expected binding fields changed",
    )
    _expect_equal(
        set(actual_bindings),
        binding_fields,
        "d4_full_sample_actual_binding_set_mismatch",
        "D4 actual binding fields changed",
    )
    for field in binding_fields:
        expected = expected_bindings.get(field)
        if field.endswith("git_commit"):
            _require_git_commit(expected, f"D4 expected {field}")
        else:
            _require_sha256(expected, f"D4 expected {field}")
        _expect_equal(
            actual_bindings.get(field),
            expected,
            "d4_full_sample_source_binding_mismatch",
            f"D4 expected/actual binding differs at {field}",
        )
    caller_bindings = {
        "formal_dataset_sha256": d4_formal["dataset_sha256"],
        "formal_manifest_sha256": d4_formal["manifest_file_sha256"],
        "formal_source_git_commit": registry["git_commit"],
        "shared_registry_sha256": registry["shared_file_sha256"],
        "supplemental_dataset_sha256": d4_supplemental["dataset_sha256"],
        "supplemental_manifest_sha256": d4_supplemental[
            "dataset_manifest_sha256"
        ],
        "supplemental_summary_content_sha256": d4_supplemental[
            "summary_content_sha256"
        ],
        "supplemental_summary_file_sha256": d4_supplemental[
            "summary_file_sha256"
        ],
        "training_registry_sha256": registry["training_file_sha256"],
    }
    for field, expected in caller_bindings.items():
        _expect_equal(
            expected_bindings.get(field),
            expected,
            "d4_full_sample_expected_binding_mismatch",
            f"D4 full-sample audit is not bound to the consumed {field}",
        )
    _validate_binding_checks(
        payload.get("binding_checks"),
        expected_bindings,
        module="d4",
    )

    formal = _validate_d4_full_sample_corpus(
        payload.get("formal_corpus"),
        name="formal",
        classification="formal_observation_corpus",
        episode_count=900,
        frame_count=1798,
        action_count=14_384,
        canonical_episode_counts={"train": 540, "validation": 180, "test": 180},
        canonical_frame_counts={"train": 1079, "validation": 359, "test": 360},
        canonical_action_counts={"train": 8632, "validation": 2872, "test": 2880},
        action_counts={
            "hold_true_count": 0,
            "request_replan_true_count": 0,
            "resource_quota_negative_count": 0,
            "resource_quota_nonzero_count": 0,
            "resource_quota_positive_count": 0,
            "resource_quota_zero_count": 14_384,
            "transfer_count": 0,
            "transferred_resource_count": 0,
        },
        reward_reason="d6_episode_outcome_not_joined",
        source_git_commit=expected_bindings["formal_source_git_commit"],
    )
    supplemental = _validate_d4_full_sample_corpus(
        payload.get("supplemental_curriculum"),
        name="supplemental",
        classification="synthetic_rule_teacher_curriculum",
        episode_count=100,
        frame_count=300,
        action_count=1200,
        canonical_episode_counts={"train": 60, "validation": 20, "test": 20},
        canonical_frame_counts={"train": 180, "validation": 60, "test": 60},
        canonical_action_counts={"train": 720, "validation": 240, "test": 240},
        action_counts={
            "hold_true_count": 100,
            "request_replan_true_count": 200,
            "resource_quota_negative_count": 100,
            "resource_quota_nonzero_count": 200,
            "resource_quota_positive_count": 100,
            "resource_quota_zero_count": 1000,
            "transfer_count": 100,
            "transferred_resource_count": 300,
        },
        reward_reason="supplemental_curriculum_has_no_observed_outcome",
        source_git_commit=expected_bindings["supplemental_source_git_commit"],
    )
    _expect(
        d4_formal["episode_count"] == formal["episode_count"]
        and d4_formal["frame_count"] == formal["frame_count"]
        and d4_formal["canonical_episode_counts"]
        == formal["canonical_episode_counts"]
        and d4_formal["canonical_frame_counts"]
        == formal["canonical_frame_counts"],
        "d4_full_sample_formal_inventory_binding_mismatch",
        "D4 producer counts differ from the consumed formal manifest/view",
    )
    _expect(
        d4_supplemental["episode_count"] == supplemental["episode_count"]
        and d4_supplemental["frame_count"] == supplemental["frame_count"]
        and d4_supplemental["canonical_episode_counts"]
        == supplemental["canonical_episode_counts"]
        and d4_supplemental["canonical_frame_counts"]
        == supplemental["canonical_frame_counts"],
        "d4_full_sample_supplemental_inventory_binding_mismatch",
        "D4 producer counts differ from the consumed supplemental summary",
    )

    integrity = _mapping(payload.get("artifact_integrity"), "D4 integrity")
    formal_integrity = _mapping(integrity.get("formal"), "D4 formal integrity")
    supplemental_integrity = _mapping(
        integrity.get("supplemental"), "D4 supplemental integrity"
    )
    _expect(
        integrity.get("formal_900_episode_dataset_modified") is False
        and integrity.get("auxiliary_sources_unchanged_during_audit") is True
        and _mapping(
            integrity.get("auxiliary_source_hashes_before"),
            "D4 auxiliary hashes before",
        )
        == _mapping(
            integrity.get("auxiliary_source_hashes_after"),
            "D4 auxiliary hashes after",
        )
        and formal_integrity.get("artifact_inventory_exact") is True
        and formal_integrity.get("source_unchanged_during_audit") is True
        and _nonnegative_int(
            formal_integrity.get("dataset_file_count"), "D4 formal files"
        )
        == 901
        and _nonnegative_int(
            formal_integrity.get("manifest_episode_file_count"),
            "D4 formal manifest files",
        )
        == 900
        and _nonnegative_int(
            formal_integrity.get("episode_sha256_verified_count"),
            "D4 formal verified files",
        )
        == 900
        and _nonnegative_int(
            formal_integrity.get("episode_sha256_mismatch_count"),
            "D4 formal hash mismatches",
        )
        == 0
        and supplemental_integrity.get("artifact_inventory_exact") is True
        and supplemental_integrity.get("source_unchanged_during_audit") is True
        and _nonnegative_int(
            supplemental_integrity.get("dataset_file_count"),
            "D4 supplemental files",
        )
        == 101
        and _nonnegative_int(
            supplemental_integrity.get("manifest_episode_file_count"),
            "D4 supplemental manifest files",
        )
        == 100
        and _nonnegative_int(
            supplemental_integrity.get("episode_sha256_verified_count"),
            "D4 supplemental verified files",
        )
        == 100
        and _nonnegative_int(
            supplemental_integrity.get("episode_sha256_mismatch_count"),
            "D4 supplemental hash mismatches",
        )
        == 0,
        "d4_full_sample_artifact_integrity_failed",
        "D4 formal or supplemental artifact verification is incomplete",
    )
    _require_sha256(formal_integrity.get("tree_sha256"), "D4 formal tree SHA")
    _require_sha256(
        supplemental_integrity.get("tree_sha256"), "D4 supplemental tree SHA"
    )

    evidence = _mapping(
        payload.get("evidence_availability"), "D4 evidence availability"
    )
    expected_availability = {
        "attributable_reward",
        "explicit_pre_projection_action_mask",
        "observed_outcome",
        "real_runtime_coalition_member_ack",
        "same_seed_paired_shadow",
        "stale_plan_epoch_lease_rejection_samples",
    }
    _expect_equal(
        set(evidence),
        expected_availability,
        "d4_full_sample_availability_set_mismatch",
        "D4 evidence availability fields changed",
    )
    for name in expected_availability:
        item = _mapping(evidence.get(name), f"D4 availability {name}")
        _expect(
            item.get("availability") == "unavailable"
            and item.get("status") == "pending",
            "d4_full_sample_availability_overstated",
            f"D4 unavailable evidence was promoted at {name}",
        )

    producer_admission = _mapping(
        payload.get("admission"), "D4 producer admission"
    )
    _expect(
        producer_admission.get("behavior_cloning_full_sample_audit") == "complete"
        and producer_admission.get("d6_cross_module_learning_admission")
        == "pending_external_audit"
        and producer_admission.get("model_training_performed") is False
        and producer_admission.get("weights_written") is False
        and producer_admission.get("ppo_allowed") is False
        and producer_admission.get("assist_allowed") is False
        and producer_admission.get("online_authority_allowed") is False
        and producer_admission.get("rule_fallback_required") is True
        and producer_admission.get(
            "deterministic_region_rules_are_only_executable_path"
        )
        is True
        and producer_admission.get(
            "lease_epoch_and_safety_projection_remain_mandatory"
        )
        is True,
        "d4_full_sample_admission_overstated",
        "D4 full-sample audit opened training, assist, or authority",
    )

    return {
        "status": "complete",
        "complete": True,
        "scope": "d4_formal_and_supplemental_structural_behavior_cloning",
        "audit_file_sha256": actual_file_hash,
        "audit_content_sha256": payload["content_sha256"],
        "formal_manifest_file_sha256": d4_formal["manifest_file_sha256"],
        "supplemental_summary_file_sha256": d4_supplemental[
            "summary_file_sha256"
        ],
        "training_registry_sha256": registry["training_file_sha256"],
        "shared_registry_sha256": registry["shared_file_sha256"],
        "formal": formal,
        "supplemental": supplemental,
        "online_truth_use_count": 0,
        "reserved_seed_leakage_count": 0,
        "dirty_episode_count": 0,
        "runtime_ack_available": False,
        "projected_recommendation_is_runtime_ack": False,
        "target_kind_rule_is_truth": False,
        "ppo_allowed": False,
        "assist_allowed": False,
        "authority_allowed": False,
        "rule_fallback_required": True,
        "remaining_blockers": [
            "real_runtime_coalition_member_ack_and_outcome_attribution",
            "versioned_reward_causal_and_counterfactual_labels",
            "same_seed_paired_shadow_non_degradation",
            "explicit_stale_plan_epoch_lease_rejection_samples",
        ],
    }


def _validate_d4_full_sample_corpus(
    value: Any,
    *,
    name: str,
    classification: str,
    episode_count: int,
    frame_count: int,
    action_count: int,
    canonical_episode_counts: Mapping[str, int],
    canonical_frame_counts: Mapping[str, int],
    canonical_action_counts: Mapping[str, int],
    action_counts: Mapping[str, int],
    reward_reason: str,
    source_git_commit: str,
) -> dict[str, Any]:
    corpus = _mapping(value, f"D4 {name} corpus")
    _expect_equal(
        corpus.get("classification"),
        classification,
        "d4_full_sample_corpus_classification_mismatch",
        f"D4 {name} corpus classification changed",
    )
    inventory = _mapping(corpus.get("inventory"), f"D4 {name} inventory")
    _expect(
        _nonnegative_int(inventory.get("episode_count"), f"D4 {name} episodes")
        == episode_count
        and _nonnegative_int(inventory.get("frame_count"), f"D4 {name} frames")
        == frame_count
        and _nonnegative_int(inventory.get("sample_count"), f"D4 {name} samples")
        == frame_count
        and _nonnegative_int(inventory.get("action_count"), f"D4 {name} actions")
        == action_count
        and inventory.get("sample_definition") == "one_region_resource_frame",
        "d4_full_sample_inventory_mismatch",
        f"D4 {name} full-sample inventory changed",
    )
    split_inventory = _mapping(
        inventory.get("canonical_split"), f"D4 {name} split inventory"
    )
    _expect_equal(
        set(split_inventory),
        set(_SPLITS),
        "d4_full_sample_split_inventory_mismatch",
        f"D4 {name} split inventory changed",
    )
    for split in _SPLITS:
        item = _mapping(split_inventory.get(split), f"D4 {name} {split} inventory")
        _expect(
            _nonnegative_int(item.get("episode_count"), "D4 split episodes")
            == canonical_episode_counts[split]
            and _nonnegative_int(item.get("frame_count"), "D4 split frames")
            == canonical_frame_counts[split]
            and _nonnegative_int(item.get("sample_count"), "D4 split samples")
            == canonical_frame_counts[split]
            and _nonnegative_int(item.get("action_count"), "D4 split actions")
            == canonical_action_counts[split],
            "d4_full_sample_split_inventory_mismatch",
            f"D4 {name} {split} inventory changed",
        )

    canonical = _mapping(corpus.get("canonical"), f"D4 {name} canonical")
    canonical_split = _mapping(
        canonical.get("canonical_split"), f"D4 {name} canonical split"
    )
    _expect(
        _count_mapping(canonical_split.get("seed_counts"), "D4 seed counts")
        == dict(_EXPECTED_SEED_COUNTS)
        and _count_mapping(
            canonical_split.get("episode_counts"), "D4 episode counts"
        )
        == dict(canonical_episode_counts)
        and _count_mapping(canonical_split.get("frame_counts"), "D4 frame counts")
        == dict(canonical_frame_counts)
        and canonical_split.get("numeric_seed_atomic") is True
        and _nonnegative_int(
            canonical_split.get("reserved_seed_count"), "D4 reserved seed count"
        )
        == 20
        and canonical_split.get("reserved_seed_present") is False,
        "d4_full_sample_canonical_split_mismatch",
        f"D4 {name} canonical 60/20/20 split changed",
    )
    readiness = _mapping(canonical.get("readiness"), f"D4 {name} readiness")
    _expect(
        readiness.get("behavior_cloning_view_available") is True
        and readiness.get("development_data_governance_only") is True
        and readiness.get("model_performance_evidence") is False
        and readiness.get("ppo_available") is False
        and readiness.get("assist_eligible") is False,
        "d4_full_sample_readiness_overstated",
        f"D4 {name} canonical readiness opened learning authority",
    )

    numeric = _mapping(corpus.get("numeric_feature_audit"), f"D4 {name} numeric")
    _expect(
        _nonnegative_int(numeric.get("finite_sample_count"), "D4 finite samples")
        == frame_count
        and _nonnegative_int(
            numeric.get("nonfinite_sample_count"), "D4 non-finite samples"
        )
        == 0
        and _nonnegative_int(
            numeric.get("nonfinite_path_count"), "D4 non-finite paths"
        )
        == 0
        and numeric.get("nonfinite_path_examples") == [],
        "d4_full_sample_numeric_audit_failed",
        f"D4 {name} numeric audit failed",
    )
    truth = _mapping(
        corpus.get("truth_seed_and_dirty_audit"), f"D4 {name} truth audit"
    )
    _expect(
        _nonnegative_int(truth.get("dirty_episode_count"), "D4 dirty episodes")
        == 0
        and _nonnegative_int(truth.get("numeric_seed_count"), "D4 seed count")
        == 100
        and truth.get("numeric_seed_atomic") is True
        and _nonnegative_int(
            truth.get("online_truth_identifier_count"), "D4 truth identifiers"
        )
        == 0
        and truth.get("reserved_evaluation_seed_overlap") == []
        and truth.get("truth_identifier_path_examples") == [],
        "d4_full_sample_truth_seed_dirty_failed",
        f"D4 {name} truth, seed, or dirty-source audit failed",
    )

    action = _mapping(corpus.get("action_coverage"), f"D4 {name} action coverage")
    _expect(
        _nonnegative_int(action.get("action_count"), "D4 action count")
        == action_count
        and _nonnegative_int(
            action.get("rule_teacher_label_count"), "D4 teacher labels"
        )
        == frame_count
        and action.get("target_kind_counts") == {"rule": frame_count}
        and action.get("rule_teacher_label_is_runtime_applied_ack") is False
        and all(
            _nonnegative_int(action.get(field), f"D4 action {field}") == expected
            for field, expected in action_counts.items()
        ),
        "d4_full_sample_action_coverage_mismatch",
        f"D4 {name} action coverage or rule-label boundary changed",
    )
    safety = _mapping(
        corpus.get("safety_and_generation_audit"), f"D4 {name} safety"
    )
    _expect(
        safety.get("owner_plan_epoch_lease_binding_checked") is True
        and safety.get("cross_region_transfer_legality_checked") is True
        and safety.get("resource_quota_conservation_checked") is True
        and _nonnegative_int(
            safety.get("owner_epoch_version_lease_monotonic_episode_count"),
            "D4 monotonic episodes",
        )
        == episode_count
        and _nonnegative_int(
            safety.get("post_projection_recommendation_count"),
            "D4 projected recommendations",
        )
        == frame_count
        and safety.get("post_projection_recommendation_is_runtime_applied_ack")
        is False
        and _nonnegative_int(
            safety.get("safety_valid_sample_count"), "D4 safe samples"
        )
        == frame_count
        and _nonnegative_int(
            safety.get("safety_invalid_sample_count"), "D4 unsafe samples"
        )
        == 0
        and safety.get("explicit_pre_projection_action_mask_available") is False
        and safety.get("explicit_stale_plan_or_lease_rejection_record_available")
        is False
        and safety.get("safety_violation_examples") == []
        and safety.get("version_violation_examples") == [],
        "d4_full_sample_safety_or_version_failed",
        f"D4 {name} safety, version, or projected-action boundary failed",
    )
    reward = _mapping(
        corpus.get("reward_outcome_and_runtime_ack"), f"D4 {name} reward"
    )
    _expect(
        reward.get("observed_outcome_available") is False
        and reward.get("paired_shadow_available") is False
        and reward.get("real_runtime_coalition_member_ack_available") is False
        and _nonnegative_int(
            reward.get("reward_available_count"), "D4 available rewards"
        )
        == 0
        and _nonnegative_int(
            reward.get("reward_unavailable_count"), "D4 unavailable rewards"
        )
        == frame_count
        and reward.get("reward_unavailable_reason_counts")
        == {reward_reason: frame_count},
        "d4_full_sample_runtime_evidence_overstated",
        f"D4 {name} runtime ACK, outcome, reward, or shadow was overstated",
    )

    source = _mapping(corpus.get("schema_and_source"), f"D4 {name} source")
    config_counts = _count_mapping(
        source.get("source_config_sha256_episode_counts"),
        f"D4 {name} config counts",
    )
    _expect(
        source.get("dataset_schema") == "d4-region-learning-dataset-v1"
        and _nonnegative_int(
            source.get("dirty_episode_count"), "D4 source dirty episodes"
        )
        == 0
        and source.get("feature_schema_counts")
        == {"d4-region-resource-features-v1": frame_count}
        and source.get("frame_schema_counts")
        == {"d4-region-learning-frame-v1": frame_count}
        and source.get("recommendation_schema_counts")
        == {"d4-region-resource-recommendation-v1": frame_count}
        and source.get("snapshot_schema_counts")
        == {"d4-region-resource-snapshot-v1": frame_count}
        and source.get("source_schema_counts")
        == {"d4-region-learning-source-v1": episode_count}
        and source.get("source_git_commit_episode_counts")
        == {source_git_commit: episode_count}
        and sum(config_counts.values()) == episode_count
        and all(
            len(key) == 64 and set(key) <= _HEX and count > 0
            for key, count in config_counts.items()
        ),
        "d4_full_sample_schema_or_source_failed",
        f"D4 {name} schema or source counts changed",
    )

    if name == "supplemental":
        synthetic = _mapping(
            corpus.get("synthetic_evidence_boundary"),
            "D4 supplemental evidence boundary",
        )
        _expect_equal(
            dict(synthetic),
            {
                "action_coverage_evidence": True,
                "attributable_reward_evidence": False,
                "center_or_secondary_takeover_effect_evidence": False,
                "deterministic_safety_constraint_evidence": True,
                "finite_value_evidence": True,
                "network_partition_effect_evidence": False,
                "observed_outcome_evidence": False,
                "real_runtime_coalition_member_ack_evidence": False,
                "structure_and_schema_evidence": True,
            },
            "d4_full_sample_synthetic_boundary_overstated",
            "D4 supplemental curriculum was promoted to runtime evidence",
        )

    return {
        "classification": classification,
        "episode_count": episode_count,
        "frame_count": frame_count,
        "sample_count": frame_count,
        "action_count": action_count,
        "canonical_seed_counts": dict(_EXPECTED_SEED_COUNTS),
        "canonical_episode_counts": dict(canonical_episode_counts),
        "canonical_frame_counts": dict(canonical_frame_counts),
        "canonical_action_counts": dict(canonical_action_counts),
        "finite_sample_count": frame_count,
        "online_truth_use_count": 0,
        "dirty_episode_count": 0,
        "safety_violation_count": 0,
        "reward_available_count": 0,
        "runtime_ack_available": False,
    }


def _audit_d5_supplemental_full_sample(
    path: Path,
    *,
    expected_file_sha256: str,
    d5_supplemental: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    """Strictly consume D5's tracked 100-episode full-sample audit."""

    expected_file_hash = _require_sha256(
        expected_file_sha256, "D5 supplemental full-sample audit file SHA"
    )
    actual_file_hash = _sha256_file(path)
    _expect_equal(
        actual_file_hash,
        expected_file_hash,
        "d5_full_sample_audit_file_hash_mismatch",
        "D5 supplemental full-sample audit file SHA differs from caller evidence",
    )
    payload = _read_json_object(path, "D5 supplemental full-sample audit")
    _expect_equal(
        payload.get("schema_version"),
        _D5_SUPPLEMENTAL_FULL_SAMPLE_AUDIT_SCHEMA,
        "d5_full_sample_audit_schema_mismatch",
        "D5 supplemental full-sample audit schema changed",
    )
    _expect_equal(
        payload.get("validation_date"),
        CROSS_MODULE_LEARNING_ADMISSION_DATE,
        "d5_full_sample_audit_date_mismatch",
        "D5 supplemental full-sample audit validation date changed",
    )
    _validate_claimed_content_hash(
        payload,
        "content_sha256",
        "d5_full_sample_audit_content_hash_mismatch",
    )
    _expect_equal(
        payload.get("purpose"),
        "supplemental_rule_teacher_behavior_cloning_full_sample_admission",
        "d5_full_sample_audit_purpose_mismatch",
        "D5 supplemental full-sample audit purpose changed",
    )

    producer_audit = _mapping(payload.get("audit"), "D5 full-sample audit result")
    _expect(
        producer_audit.get("passed") is True
        and _nonnegative_int(
            producer_audit.get("violation_count"), "D5 full-sample violations"
        )
        == 0
        and producer_audit.get("violations") == [],
        "d5_full_sample_producer_audit_failed",
        "D5 producer full-sample audit did not pass cleanly",
    )

    expected_bindings = {
        "canonical_view_sha256": d5_supplemental["canonical_view_sha256"],
        "dataset_config_sha256": d5_supplemental["dataset_config_sha256"],
        "dataset_manifest_sha256": d5_supplemental["dataset_manifest_sha256"],
        "shared_registry_sha256": registry["shared_file_sha256"],
        "source_git_commit": d5_supplemental["source_git_commit"],
        "summary_content_sha256": d5_supplemental["summary_content_sha256"],
        "training_registry_sha256": registry["training_file_sha256"],
    }
    claimed_expected = _mapping(
        payload.get("expected_bindings"), "D5 expected full-sample bindings"
    )
    claimed_actual = _mapping(
        payload.get("actual_bindings"), "D5 actual full-sample bindings"
    )
    _expect_equal(
        dict(claimed_expected),
        expected_bindings,
        "d5_full_sample_expected_binding_mismatch",
        "D5 full-sample expected bindings differ from D6 inputs",
    )
    for field, expected in expected_bindings.items():
        _expect_equal(
            claimed_actual.get(field),
            expected,
            "d5_full_sample_source_binding_mismatch",
            f"D5 full-sample actual binding differs at {field}",
        )
    _expect_equal(
        claimed_actual.get("summary_file_sha256"),
        d5_supplemental["summary_file_sha256"],
        "d5_full_sample_summary_file_binding_mismatch",
        "D5 full-sample audit is not bound to the consumed summary file",
    )
    dataset_checksums_sha256 = _require_sha256(
        claimed_actual.get("dataset_checksums_sha256"),
        "D5 full-sample dataset checksums SHA",
    )

    binding_checks = _mapping(
        payload.get("binding_checks"), "D5 full-sample binding checks"
    )
    _expect_equal(
        set(binding_checks),
        set(expected_bindings),
        "d5_full_sample_binding_check_set_mismatch",
        "D5 full-sample binding check set changed",
    )
    for field, expected in expected_bindings.items():
        item = _mapping(binding_checks.get(field), f"D5 binding check {field}")
        _expect(
            item.get("actual") == expected
            and item.get("expected") == expected
            and item.get("passed") is True,
            "d5_full_sample_binding_check_failed",
            f"D5 full-sample binding check failed at {field}",
        )

    coverage = _mapping(payload.get("coverage"), "D5 full-sample coverage")
    _expect_equal(
        (
            _nonnegative_int(coverage.get("episode_count"), "D5 audited episodes"),
            _nonnegative_int(coverage.get("sample_count"), "D5 audited samples"),
            _nonnegative_int(coverage.get("segment_count"), "D5 audited segments"),
        ),
        (100, 1200, 800),
        "d5_full_sample_inventory_mismatch",
        "D5 full-sample episode/sample inventory changed",
    )
    expected_episode_counts = {"train": 60, "validation": 20, "test": 20}
    expected_sample_counts = {"train": 720, "validation": 240, "test": 240}
    _expect_equal(
        _count_mapping(
            coverage.get("canonical_episode_counts"),
            "D5 full-sample canonical episode counts",
        ),
        expected_episode_counts,
        "d5_full_sample_episode_split_mismatch",
        "D5 full-sample canonical episode counts differ from 60/20/20",
    )
    _expect_equal(
        _count_mapping(
            coverage.get("canonical_sample_counts"),
            "D5 full-sample canonical sample counts",
        ),
        expected_sample_counts,
        "d5_full_sample_sample_split_mismatch",
        "D5 full-sample canonical sample counts differ from 720/240/240",
    )
    _expect_equal(
        _count_mapping(coverage.get("intent_counts"), "D5 audited intent counts"),
        d5_supplemental["action_coverage"]["intent"],
        "d5_full_sample_intent_binding_mismatch",
        "D5 full-sample intent counts differ from the consumed summary",
    )
    _expect_equal(
        _count_mapping(coverage.get("fov_mode_counts"), "D5 audited FOV counts"),
        d5_supplemental["action_coverage"]["fov"],
        "d5_full_sample_fov_binding_mismatch",
        "D5 full-sample FOV counts differ from the consumed summary",
    )
    _expect_equal(
        _count_mapping(
            coverage.get("camera_role_counts"), "D5 audited camera role counts"
        ),
        d5_supplemental["action_coverage"]["camera_role"],
        "d5_full_sample_role_binding_mismatch",
        "D5 full-sample camera-role counts differ from the consumed summary",
    )

    integrity = _mapping(
        payload.get("artifact_integrity"), "D5 full-sample artifact integrity"
    )
    _expect(
        _nonnegative_int(
            integrity.get("checksummed_file_count"), "D5 checksummed files"
        )
        == 302
        and _nonnegative_int(
            integrity.get("sha256_verified_file_count"), "D5 verified files"
        )
        == 302
        and _nonnegative_int(
            integrity.get("sha256_mismatch_file_count"), "D5 hash mismatches"
        )
        == 0
        and _nonnegative_int(
            integrity.get("online_file_count"), "D5 online files"
        )
        == 100
        and _nonnegative_int(
            integrity.get("offline_file_count"), "D5 offline files"
        )
        == 100
        and _nonnegative_int(
            integrity.get("episode_descriptor_file_count"),
            "D5 descriptor files",
        )
        == 100
        and _nonnegative_int(
            integrity.get("descriptor_manifest_match_count"),
            "D5 descriptor/manifest matches",
        )
        == 100
        and integrity.get("checksum_artifact_set_exact") is True
        and integrity.get("online_offline_episode_collections_complete") is True
        and integrity.get("canonical_loader_passed") is True
        and integrity.get("strict_lazy_loader_passed") is True
        and integrity.get("source_artifacts_unchanged") is True
        and integrity.get("formal_900_episode_dataset_modified") is False,
        "d5_full_sample_artifact_integrity_failed",
        "D5 full-sample artifact set or SHA verification is incomplete",
    )
    expected_source_hashes = {
        "canonical_view_sha256": expected_bindings["canonical_view_sha256"],
        "dataset_checksums_sha256": dataset_checksums_sha256,
        "dataset_config_sha256": expected_bindings["dataset_config_sha256"],
        "dataset_manifest_sha256": expected_bindings["dataset_manifest_sha256"],
        "shared_registry_sha256": expected_bindings["shared_registry_sha256"],
        "summary_file_sha256": d5_supplemental["summary_file_sha256"],
        "training_registry_sha256": expected_bindings["training_registry_sha256"],
    }
    _expect_equal(
        dict(_mapping(integrity.get("source_hashes_before"), "D5 source hashes before")),
        expected_source_hashes,
        "d5_full_sample_source_hash_before_mismatch",
        "D5 full-sample pre-audit source hashes differ from D6 inputs",
    )
    _expect_equal(
        dict(_mapping(integrity.get("source_hashes_after"), "D5 source hashes after")),
        expected_source_hashes,
        "d5_full_sample_source_hash_after_mismatch",
        "D5 full-sample audit changed or rebound source artifacts",
    )

    feature = _mapping(
        payload.get("behavior_cloning_feature_audit"),
        "D5 full-sample behavior cloning features",
    )
    _expect(
        _nonnegative_int(feature.get("sample_count"), "D5 feature samples") == 1200
        and _nonnegative_int(
            feature.get("finite_feature_sample_count"), "D5 finite feature samples"
        )
        == 1200
        and _nonnegative_int(
            feature.get("nonfinite_feature_sample_count"),
            "D5 non-finite feature samples",
        )
        == 0
        and feature.get("global_track_id_created_rewritten_or_rebound") is False
        and feature.get("numeric_seed_atomic") is True
        and feature.get("reserved_evaluation_seed_overlap") == []
        and _nonnegative_int(
            feature.get("version_consistency_checked_sample_count"),
            "D5 version-checked samples",
        )
        == 1200
        and _nonnegative_int(
            feature.get("version_monotonic_episode_count"),
            "D5 version-monotonic episodes",
        )
        == 100,
        "d5_full_sample_feature_audit_failed",
        "D5 full-sample feature, identity, or version audit is incomplete",
    )
    _expect_equal(
        _count_mapping(
            feature.get("canonical_seed_counts"), "D5 feature canonical seed counts"
        ),
        dict(_EXPECTED_SEED_COUNTS),
        "d5_full_sample_feature_seed_split_mismatch",
        "D5 feature audit canonical seed counts changed",
    )
    _expect_equal(
        _count_mapping(
            feature.get("canonical_sample_counts"),
            "D5 feature canonical sample counts",
        ),
        expected_sample_counts,
        "d5_full_sample_feature_sample_split_mismatch",
        "D5 feature audit canonical sample counts changed",
    )

    truth = _mapping(
        payload.get("truth_seed_and_source_audit"),
        "D5 full-sample truth/seed/source audit",
    )
    _expect(
        _nonnegative_int(truth.get("dirty_episode_count"), "D5 dirty episodes") == 0
        and truth.get("repository_dirty") is False
        and truth.get("dirty_source_accepted") is False
        and _nonnegative_int(
            truth.get("online_truth_identifier_count"), "D5 online truth count"
        )
        == 0
        and truth.get("online_truth_used_for_behavior_cloning") is False
        and truth.get("reserved_seed_overlap") == []
        and truth.get("reserved_evaluation_seeds")
        == list(_EXPECTED_RESERVED_SEEDS)
        and _nonnegative_int(
            truth.get("training_seed_count"), "D5 training seed count"
        )
        == 100
        and _nonnegative_int(
            truth.get("synthetic_episode_count"), "D5 synthetic episodes"
        )
        == 100
        and _nonnegative_int(
            truth.get("non_synthetic_episode_count"), "D5 non-synthetic episodes"
        )
        == 0
        and _nonnegative_int(
            truth.get("truth_guard_passed_episode_count"),
            "D5 truth-guarded episodes",
        )
        == 100
        and truth.get("formal_900_episode_dataset_modified") is False,
        "d5_full_sample_truth_seed_source_failed",
        "D5 full-sample truth, reserved seed, or clean-source audit failed",
    )

    identity = _mapping(
        payload.get("version_and_identity_audit"),
        "D5 full-sample version/identity audit",
    )
    runtime_modes = _count_mapping(
        identity.get("runtime_mode_counts"), "D5 runtime mode counts"
    )
    _expect(
        identity.get("caller_owned_binding_rechecked_for_all_samples") is True
        and identity.get("d5_created_rewritten_or_rebound_global_track_id") is False
        and identity.get("global_track_id_created_or_rebound") is False
        and identity.get("global_track_id_source") == "caller_owned_center_reference"
        and identity.get("communication_and_track_versions_strictly_increasing")
        is True
        and identity.get("plan_and_coalition_versions_monotonic") is True
        and identity.get("sequence_contiguous") is True
        and identity.get("timestamps_strictly_increasing") is True
        and runtime_modes == {"disabled": 1200},
        "d5_full_sample_identity_or_version_failed",
        "D5 full-sample identity or version contract failed",
    )

    labels = _validate_unavailable_label_set(
        payload.get("offline_label_availability"),
        expected_sample_count=1200,
        context="D5 supplemental full-sample",
        require_zero_padding_flag=True,
    )
    ack = _mapping(
        payload.get("synthetic_ack_fault_coverage"),
        "D5 full-sample synthetic ACK coverage",
    )
    ack_counts = _count_mapping(ack.get("counts"), "D5 full-sample ACK counts")
    _expect(
        ack_counts == {"applied": 400, "rejected": 400, "missing": 400}
        and ack.get("expected_counts") == ack_counts
        and ack.get("interpretation")
        == "deterministic_fault_injection_coverage_only"
        and ack.get("real_runtime_distribution_evidence") is False
        and ack.get("runtime_ack_attribution_available") is False
        and ack.get("reward_or_outcome_evidence") is False,
        "d5_full_sample_synthetic_ack_promoted",
        "D5 synthetic ACK coverage was promoted to runtime evidence",
    )
    corpus = _mapping(
        payload.get("corpus_classification"), "D5 full-sample corpus classification"
    )
    _expect(
        corpus.get("formal_observation_corpus") is False
        and corpus.get("supplemental_rule_teacher_data") is True
        and corpus.get("offline_evaluation_labels_available") is False
        and corpus.get("real_runtime_ack_evidence") is False,
        "d5_full_sample_corpus_classification_invalid",
        "D5 full-sample evidence classification overstates runtime or formal evidence",
    )
    producer_admission = _mapping(
        payload.get("admission"), "D5 full-sample admission"
    )
    _expect(
        producer_admission.get("behavior_cloning_full_sample_audit") == "complete"
        and producer_admission.get("d6_cross_module_learning_admission")
        == "pending_external_audit"
        and producer_admission.get("model_training_performed") is False
        and producer_admission.get("weights_written") is False
        and producer_admission.get("ppo") is False
        and producer_admission.get("assist") is False
        and producer_admission.get("online_authority") is False
        and producer_admission.get("camera_command_authority") is False
        and producer_admission.get("rule_fallback_required") is True,
        "d5_full_sample_admission_overstated",
        "D5 full-sample audit opened training or online authority",
    )

    return {
        "status": "complete",
        "complete": True,
        "scope": "d5_supplemental_behavior_cloning_only",
        "audit_file_sha256": actual_file_hash,
        "audit_content_sha256": payload["content_sha256"],
        "dataset_manifest_sha256": expected_bindings["dataset_manifest_sha256"],
        "canonical_view_sha256": expected_bindings["canonical_view_sha256"],
        "dataset_config_sha256": expected_bindings["dataset_config_sha256"],
        "training_registry_sha256": expected_bindings["training_registry_sha256"],
        "shared_registry_sha256": expected_bindings["shared_registry_sha256"],
        "producer_summary_content_sha256": expected_bindings[
            "summary_content_sha256"
        ],
        "source_git_commit": expected_bindings["source_git_commit"],
        "episode_count": 100,
        "sample_count": 1200,
        "canonical_episode_counts": expected_episode_counts,
        "canonical_sample_counts": expected_sample_counts,
        "checksummed_artifact_count": 302,
        "verified_artifact_count": 302,
        "finite_feature_sample_count": 1200,
        "online_truth_use_count": 0,
        "reserved_seed_leakage_count": 0,
        "dirty_episode_count": 0,
        "offline_label_availability": labels,
        "synthetic_ack_fault_coverage": {
            "counts": ack_counts,
            "runtime_attribution": False,
        },
        "ppo_allowed": False,
        "assist_allowed": False,
        "authority_allowed": False,
        "rule_fallback_required": True,
        "remaining_blockers": [
            "real_runtime_applied_ack_and_outcome_attribution",
            "reward_counterfactual_and_causal_labels",
            "paired_shadow_non_degradation",
        ],
    }


def _build_availability(
    *,
    d3_full_sample: Mapping[str, Any],
    d4_formal: Mapping[str, Any],
    d4_full_sample: Mapping[str, Any],
    d5_active: Mapping[str, Any],
    d4_supplemental: Mapping[str, Any],
    d5_supplemental: Mapping[str, Any],
) -> dict[str, Any]:
    active_labels = _mapping(
        d5_active.get("offline_label_availability"), "D5 formal labels"
    )
    supplemental_labels = _mapping(
        d5_supplemental.get("offline_label_availability"), "D5 supplemental labels"
    )
    sources = {
        "reward": [
            {
                "source": "d3_full_sample_rule_teacher_diagnostics",
                "available_sample_count": 0,
                "sample_count": d3_full_sample["frame_count"],
                "classification": "not_runtime_reward",
            },
            {
                "source": "d4_formal",
                "available_sample_count": d4_formal["reward_available_count"],
                "sample_count": d4_formal["reward_sample_count"],
            },
            {
                "source": "d4_supplemental",
                "available_sample_count": d4_supplemental["reward_available_count"],
                "sample_count": d4_supplemental["reward_sample_count"],
            },
            {
                "source": "d4_full_sample",
                "available_sample_count": 0,
                "sample_count": d4_full_sample["formal"]["sample_count"]
                + d4_full_sample["supplemental"]["sample_count"],
                "classification": "no_attributable_runtime_reward",
            },
            {
                "source": "d5_formal_active_vision",
                "available_sample_count": active_labels["reward"][
                    "available_sample_count"
                ],
                "sample_count": active_labels["reward"]["sample_count"],
            },
            {
                "source": "d5_supplemental",
                "available_sample_count": supplemental_labels["reward"][
                    "available_sample_count"
                ],
                "sample_count": supplemental_labels["reward"]["sample_count"],
            },
        ],
        "outcome": [
            {
                "source": "d4_supplemental",
                "available": d4_supplemental["outcome_available"],
            },
            {
                "source": "d5_formal_active_vision",
                "available_sample_count": active_labels["outcome"][
                    "available_sample_count"
                ],
                "sample_count": active_labels["outcome"]["sample_count"],
            },
            {
                "source": "d5_supplemental",
                "available_sample_count": supplemental_labels["outcome"][
                    "available_sample_count"
                ],
                "sample_count": supplemental_labels["outcome"]["sample_count"],
            },
        ],
        "counterfactual": [
            {
                "source": "d5_formal_active_vision",
                "available_sample_count": active_labels["counterfactual"][
                    "available_sample_count"
                ],
                "sample_count": active_labels["counterfactual"]["sample_count"],
            },
            {
                "source": "d5_supplemental",
                "available_sample_count": supplemental_labels["counterfactual"][
                    "available_sample_count"
                ],
                "sample_count": supplemental_labels["counterfactual"]["sample_count"],
            },
        ],
        "causal": [
            {
                "source": "d5_formal_active_vision",
                "available_sample_count": active_labels["causal_label"][
                    "available_sample_count"
                ],
                "sample_count": active_labels["causal_label"]["sample_count"],
            },
            {
                "source": "d5_supplemental",
                "available_sample_count": supplemental_labels["causal_label"][
                    "available_sample_count"
                ],
                "sample_count": supplemental_labels["causal_label"]["sample_count"],
            },
        ],
    }
    return {
        name: {
            "available": False,
            "status": "unavailable",
            "reason": f"{name}_evidence_unavailable",
            "evidence_sources": evidence,
            "zero_imputation_used": False,
        }
        for name, evidence in sources.items()
    } | {
        "runtime_ack": {
            "available": False,
            "status": "unavailable",
            "reason": "no_applied_action_runtime_ack_attribution",
            "evidence_sources": [
                {
                    "source": "d5_supplemental_synthetic_fault_coverage",
                    "classification": "not_runtime_evidence",
                }
            ],
            "zero_imputation_used": False,
        },
        "paired_shadow": {
            "available": False,
            "status": "unavailable",
            "reason": "no_paired_shadow_non_degradation_evidence",
            "evidence_sources": [],
            "zero_imputation_used": False,
        },
    }


def _d5_source_content_sha256(manifest: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(manifest))
    payload.pop("split_policy", None)
    payload.pop("split_sha256", None)
    payload.pop("training_set_sha256", None)
    descriptors = payload.get("episodes")
    if not isinstance(descriptors, list):
        _fail("d5_source_descriptors_missing", "D5 source manifest has no episodes")
    for descriptor in descriptors:
        _mapping(descriptor, "D5 source descriptor").pop("split", None)
    payload["episodes"] = sorted(
        descriptors, key=lambda item: str(item.get("episode_uid", ""))
    )
    return _sha256_json(payload)


def _d5_canonical_descriptors(
    entries: Sequence[Mapping[str, Any]], registry: Mapping[str, Any]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    episode_uids: set[str] = set()
    for entry in entries:
        descriptor = deepcopy(dict(entry))
        uid = str(descriptor.get("episode_uid", ""))
        _expect(
            bool(uid) and uid not in episode_uids,
            "d5_source_episode_uid_invalid",
            "D5 source episode_uid is empty or duplicated",
        )
        episode_uids.add(uid)
        seed = _nonnegative_int(descriptor.get("seed"), "D5 descriptor seed")
        descriptor["source_split"] = _split(
            descriptor.get("split"), "D5 descriptor source split"
        )
        descriptor["split"] = registry["assignment_by_seed"][seed]
        result.append(descriptor)
    return result


def _d5_canonical_summary(
    consumer: str,
    source_entries: Sequence[Mapping[str, Any]],
    canonical_entries: Sequence[Mapping[str, Any]],
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    split_values = _canonical_seed_values(registry)
    summary: dict[str, Any] = {
        "unit": _EXPECTED_UNIT,
        "split_seed": 20260720,
        "seed_values": split_values,
        "seed_counts": dict(_EXPECTED_SEED_COUNTS),
    }
    counts = Counter(str(item["split"]) for item in canonical_entries)
    summary["episode_counts"] = {name: int(counts[name]) for name in _SPLITS}
    if consumer == "tracklet_graph":
        summary["node_counts"] = {
            split: sum(
                _nonnegative_int(item.get("node_count"), "D5 node_count")
                for item in canonical_entries
                if item["split"] == split
            )
            for split in _SPLITS
        }
        summary["candidate_edge_counts"] = {
            split: sum(
                _nonnegative_int(item.get("edge_count"), "D5 edge_count")
                for item in canonical_entries
                if item["split"] == split
            )
            for split in _SPLITS
        }
        class_names = (
            "candidate_edges",
            "positive_candidate_edges",
            "negative_candidate_edges",
            "unlabeled_candidate_edges",
        )
        summary["class_balance_by_split"] = {
            split: {
                name: sum(
                    _nonnegative_int(
                        _mapping(item.get("class_balance"), "D5 class balance").get(name),
                        f"D5 class balance {name}",
                    )
                    for item in canonical_entries
                    if item["split"] == split
                )
                for name in class_names
            }
            for split in _SPLITS
        }
        hash_fields = ("graph_sha256", "labels_sha256")
    else:
        summary["sample_counts"] = {
            split: sum(
                _nonnegative_int(item.get("sample_count"), "D5 sample_count")
                for item in canonical_entries
                if item["split"] == split
            )
            for split in _SPLITS
        }
        hash_fields = ("online_sha256", "offline_sha256")
    summary["split_sha256"] = _sha256_json(
        sorted(
            [
                {
                    "episode_uid": str(item["episode_uid"]),
                    "scenario_version": str(item["scenario_version"]),
                    "seed": int(item["seed"]),
                    "split": str(item["split"]),
                }
                for item in canonical_entries
            ],
            key=lambda item: item["episode_uid"],
        )
    )
    summary["training_set_sha256"] = _sha256_json(
        sorted(
            [
                {
                    "episode_uid": str(item["episode_uid"]),
                    "scenario_version": str(item["scenario_version"]),
                    "seed": int(item["seed"]),
                    **{
                        field: _require_sha256(item.get(field), f"D5 {field}")
                        for field in hash_fields
                    },
                }
                for item in canonical_entries
                if item["split"] == "train"
            ],
            key=lambda item: item["episode_uid"],
        )
    )
    summary["reassigned_episode_count"] = sum(
        str(source.get("split")) != str(canonical.get("split"))
        for source, canonical in zip(source_entries, canonical_entries, strict=True)
    )
    summary["reserved_evaluation_seed_overlap"] = []
    return summary


def _validate_unavailable_label_set(
    value: Any,
    *,
    expected_sample_count: int,
    context: str,
    require_zero_padding_flag: bool = False,
) -> dict[str, Any]:
    labels = _mapping(value, f"{context} label availability")
    expected_keys = {"reward", "outcome", "counterfactual", "causal_label"}
    if require_zero_padding_flag:
        expected_keys |= {"all_values_explicitly_unavailable", "zero_padding_used"}
        _expect(
            labels.get("all_values_explicitly_unavailable") is True
            and labels.get("zero_padding_used") is False,
            "unavailable_label_zero_imputation",
            f"{context} unavailable labels were zero-imputed or overstated",
        )
    _expect_equal(
        set(labels),
        expected_keys,
        "label_availability_fields_mismatch",
        f"{context} label availability fields changed",
    )
    result: dict[str, Any] = {}
    for name in ("reward", "outcome", "counterfactual", "causal_label"):
        item = _mapping(labels.get(name), f"{context} {name}")
        _expect(
            item.get("status") == "unavailable"
            and _nonnegative_int(
                item.get("available_sample_count"), f"{context} {name} available"
            )
            == 0
            and _nonnegative_int(
                item.get("sample_count"), f"{context} {name} samples"
            )
            == expected_sample_count,
            "unavailable_label_zero_imputation",
            f"{context} {name} must remain explicitly unavailable",
        )
        result[name] = dict(item)
    if require_zero_padding_flag:
        result["all_values_explicitly_unavailable"] = True
        result["zero_padding_used"] = False
    return result


def _validate_canonical_split_catalog(
    split: Mapping[str, Any],
    registry: Mapping[str, Any],
    *,
    context: str,
) -> None:
    _expect_equal(
        split.get("unit"),
        _EXPECTED_UNIT,
        "canonical_split_unit_mismatch",
        f"{context} split unit changed",
    )
    _expect_equal(
        split.get("split_seed"),
        20260720,
        "canonical_split_seed_mismatch",
        f"{context} split seed changed",
    )
    _expect_equal(
        split.get("seed_values"),
        _canonical_seed_values(registry),
        "canonical_seed_assignment_mismatch",
        f"{context} seed assignments differ from the shared registry",
    )
    _expect_equal(
        split.get("seed_counts"),
        dict(_EXPECTED_SEED_COUNTS),
        "canonical_seed_count_mismatch",
        f"{context} seed counts differ from 60/20/20",
    )
    _expect_equal(
        split.get("reserved_evaluation_seed_overlap"),
        [],
        "reserved_seed_leakage",
        f"{context} contains reserved evaluation seeds",
    )


def _canonical_seed_values(registry: Mapping[str, Any]) -> dict[str, list[int]]:
    assignment = _mapping(registry.get("assignment_by_seed"), "canonical assignment")
    return {
        split: sorted(int(seed) for seed, value in assignment.items() if value == split)
        for split in _SPLITS
    }


def _validate_reserved_absence(
    split_catalog: Mapping[str, Sequence[int]],
    registry: Mapping[str, Any],
    context: str,
) -> None:
    seeds = {int(seed) for values in split_catalog.values() for seed in values}
    overlap = sorted(seeds.intersection(registry["reserved_seeds"]))
    _expect(
        not overlap,
        "reserved_seed_leakage",
        f"{context} contains reserved seeds: {overlap}",
    )


def _verify_full_sample_file_hash(
    path: Path,
    expected_file_sha256: str,
    *,
    module: str,
    label: str,
) -> str:
    expected = _require_sha256(expected_file_sha256, f"{label} file SHA256")
    actual = _sha256_file(path)
    _expect_equal(
        actual,
        expected,
        f"{module}_full_sample_audit_file_hash_mismatch",
        f"{label} file SHA differs from caller evidence",
    )
    return actual


def _validate_binding_checks(
    value: Any,
    expected_bindings: Mapping[str, Any],
    *,
    module: str,
) -> None:
    checks = _mapping(value, f"{module.upper()} full-sample binding checks")
    _expect_equal(
        set(checks),
        set(expected_bindings),
        f"{module}_full_sample_binding_check_set_mismatch",
        f"{module.upper()} full-sample binding check set changed",
    )
    for field, expected in expected_bindings.items():
        item = _mapping(checks.get(field), f"{module.upper()} binding check {field}")
        _expect(
            item.get("actual") == expected
            and item.get("expected") == expected
            and item.get("passed") is True,
            f"{module}_full_sample_binding_check_failed",
            f"{module.upper()} full-sample binding check failed at {field}",
        )


def _validate_claimed_content_hash(
    payload: Mapping[str, Any], field: str, code: str
) -> None:
    unsigned = deepcopy(dict(payload))
    claimed = _require_sha256(unsigned.pop(field, None), field)
    _expect_equal(
        _sha256_json(unsigned),
        claimed,
        code,
        f"claimed content hash failed: {field}",
    )


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        _fail("input_missing", f"missing {label}: {path}")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise CrossModuleLearningAdmissionError(
            "input_json_invalid", f"invalid {label}: {path}"
        ) from exc
    if not isinstance(value, dict):
        _fail("input_json_object_required", f"{label} root must be an object")
    return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", f"{name} must be an object")
    return value


def _mapping_sequence(value: Any, name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        _fail("list_required", f"{name} must be a list")
    return tuple(_mapping(item, name) for item in value)


def _count_mapping(value: Any, name: str) -> dict[str, int]:
    mapping = _mapping(value, name)
    return {str(key): _nonnegative_int(item, f"{name}.{key}") for key, item in mapping.items()}


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        _fail("integer_required", f"{name} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise CrossModuleLearningAdmissionError(
            "integer_required", f"{name} must be a non-negative integer"
        ) from exc
    if result < 0 or value != result:
        _fail("integer_required", f"{name} must be a non-negative integer")
    return result


def _split(value: Any, name: str) -> str:
    split = str(value)
    if split not in _SPLITS:
        _fail("split_invalid", f"{name} must be train, validation, or test")
    return split


def _require_sha256(value: Any, name: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(character not in _HEX for character in text):
        _fail("sha256_invalid", f"{name} must be a lowercase SHA256")
    return text


def _require_git_commit(value: Any, name: str) -> str:
    text = str(value or "")
    if len(text) not in {40, 64} or any(character not in _HEX for character in text):
        _fail("git_commit_invalid", f"{name} must be a lowercase full Git object ID")
    return text


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        _fail("input_missing", f"missing input artifact: {path}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CrossModuleLearningAdmissionError(
            "input_hash_failed", f"cannot hash input artifact: {path}"
        ) from exc
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_text_atomic(path, text)


def _write_text_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _expect(condition: bool, code: str, message: str) -> None:
    if not condition:
        _fail(code, message)


def _expect_equal(
    actual: Any,
    expected: Any,
    code: str,
    message: str,
) -> None:
    if actual != expected:
        _fail(code, message)


def _fail(code: str, message: str) -> None:
    raise CrossModuleLearningAdmissionError(code, message)


__all__ = [
    "CROSS_MODULE_LEARNING_ADMISSION_DATE",
    "CROSS_MODULE_LEARNING_ADMISSION_SCHEMA_VERSION",
    "CrossModuleLearningAdmissionError",
    "CrossModuleLearningAdmissionInputs",
    "audit_cross_module_learning_data_admission",
    "render_cross_module_learning_data_admission_markdown",
    "write_cross_module_learning_data_admission_report",
]
