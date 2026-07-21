"""Read-only admission audit for cross-module scalable-3D learning data.

The audit consumes immutable producer manifests and detached canonical views.
It never rewrites D3/D4/D5 data and never upgrades synthetic curriculum ACKs
to runtime execution evidence.  Manifest-level readiness is intentionally
separate from a future full-sample audit.
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
    d4_formal_manifest_path: Path
    d4_formal_canonical_view_path: Path
    d4_formal_canonical_view_file_sha256: str
    d5_tracklet_formal_manifest_path: Path
    d5_tracklet_canonical_view_path: Path
    d5_tracklet_canonical_readiness_path: Path
    d5_active_vision_formal_manifest_path: Path
    d5_active_vision_canonical_view_path: Path
    d5_active_vision_canonical_readiness_path: Path
    d4_supplemental_summary_path: Path
    d5_supplemental_summary_path: Path

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

    availability = _build_availability(
        d4_formal=d4_formal,
        d5_active=d5_active,
        d4_supplemental=d4_supplemental,
        d5_supplemental=d5_supplemental,
    )
    admission = {
        "behavior_cloning_canonical_view_available": True,
        "behavior_cloning_full_sample_audit": {
            "available": False,
            "status": "pending",
            "reason": "manifest_and_summary_level_audit_only",
        },
        "ppo_allowed": False,
        "assist_allowed": False,
        "authority_allowed": False,
        "rule_fallback_required": True,
        "status": "bc_canonical_view_available_full_sample_audit_pending",
        "promotion_blockers": [
            "behavior_cloning_full_sample_audit_pending",
            "reward_unavailable",
            "outcome_unavailable",
            "runtime_ack_attribution_unavailable",
            "paired_shadow_non_degradation_unavailable",
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
                "d5_active_vision": d5_supplemental,
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
    d4_action = _mapping(action.get("d4"), "D4 action")
    d5_action = _mapping(action.get("d5"), "D5 action")

    lines = [
        "# D6 跨模块学习数据联合准入审计",
        "",
        f"审计日期：{payload['audit_date']}。本次只读校验正式语料、规范 seed 视图和补充规则教师课程，没有修改生产者制品。",
        "",
        "## 结论",
        "",
        "D3、D4、D5 的规范 seed 身份已统一为训练/验证/测试 60/20/20，保留 seed 1000-1019 泄漏为 0。行为克隆规范视图可用于开发期读取；跨模块全样本复核仍未完成。",
        "",
        "奖励、结果、反事实、因果标签、真实运行时确认和配对 shadow 证据均不可用。因此 PPO、在线辅助和控制权限保持关闭，规则回退继续强制启用。D5 的 applied/rejected/missing 只代表确定性故障注入覆盖。",
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
            "本次复核到 manifest、detached view 和 summary 层。D3/D4/D5 的逐样本内容、真实运行时动作执行结果、配对 shadow 非退化结果和保留 seed 性能尚未形成统一 D6 全样本证据。",
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
    _require_sha256(manifest.get("frames_sha256"), "D3 frames_sha256")
    return {
        "classification": "formal_observation_corpus",
        "manifest_schema_version": manifest["schema_version"],
        "manifest_file_sha256": _sha256_file(path),
        "episode_count": episode_count,
        "frame_count": frame_count,
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


def _build_availability(
    *,
    d4_formal: Mapping[str, Any],
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
