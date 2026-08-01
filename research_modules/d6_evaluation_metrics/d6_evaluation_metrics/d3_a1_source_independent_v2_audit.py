"""Independent D6 audit for the D3 A1 source-independent v2 result.

The auditor is intentionally implemented with the Python standard library. It
does not import the D3 evaluator, model, aggregate helpers, or assignment
solver. D3 aggregate fields are treated as claims and reconciled against the
contract, generation evidence, identity-free dataset, and per-frame records.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import struct
import subprocess
from typing import Any, Iterable, Iterator, Mapping, Sequence


D3_A1_V2_AUDIT_SCHEMA_VERSION = (
    "d6.d3-a1-source-independent-v2-external-audit.v1"
)
D3_A1_V2_AUDIT_STATUS = (
    "offline_integrity_and_preregistered_machine_gate_confirmed_not_admitted"
)

_EXPECTED_CONTRACT_SHA256 = (
    "f47ec9d095af11042c670b0e358e3e7285a166fa48e3df57829b14c1da8497e7"
)
_EXPECTED_CONTRACT_SCHEMA = "d3_a1_source_independent_evaluation_contract_v2"
_EXPECTED_CONTRACT_ID = (
    "d3-a1-assignment-aware-source-independent-evaluation-v2-20260730"
)
_EXPECTED_MODE = "source_independent_evaluation"
_EXPECTED_SCHEDULE_SHA256 = (
    "468bddc8ccd5932114a1f779e093817a136a67f3c7df07fc458e1e1d5aca1009"
)
_EXPECTED_BUNDLE_MANIFEST_SHA256 = (
    "ec9f93d668e1aa319f65fcda0d73adb0527f316a2d1880e93e88697b6468ad3d"
)
_EXPECTED_BUNDLE_STATE_SHA256 = (
    "c185823bd9a4cf5363d17854385aeb74c340c8ac384327281d224a1097eb8206"
)
_EXPECTED_BUNDLE_TREE_SHA256 = (
    "de7b627df9782d7d2577687f30d02d4faeeaf577ecc557c2b8d91dd6e7115dd9"
)
_EXPECTED_SOURCE_TREE_SHA256 = (
    "b31d0b86f53ff4dc32a01dc9ecc7988539a5635cbc31b674cd74b55a69de2438"
)
_EXPECTED_DATASET_SPLIT_SHA256 = (
    "f1380dd60fded50b2550e5ce63d6d41bb6066022f9e4b201925978acfa025ca5"
)
_EXPECTED_RESULT_FILES = frozenset(
    {
        "per_frame_evaluation.jsonl",
        "per_frame_evaluation.csv",
        "aggregate.json",
        "SOURCE_INDEPENDENT_EVALUATION_CN.md",
        "SHA256SUMS",
    }
)
_EXPECTED_DATASET_FILES = frozenset({"dataset_manifest.json", "frames.jsonl"})
_EXPECTED_BUNDLE_FILES = frozenset(
    {"manifest.json", "state_dict.json", "SHA256SUMS"}
)
_SPLITS = ("train", "validation", "test")
_EXPECTED_SPLIT_EPISODES = {"train": 60, "validation": 20, "test": 20}
_EXPECTED_SPLIT_FRAMES = {"train": 178, "validation": 57, "test": 57}
_EXPECTED_EVALUATION_SEEDS = frozenset(range(20000, 20100))
_EXPECTED_FORMAL_SEEDS = frozenset(range(1000, 1020))
_EXPECTED_PERMISSION_KEYS = frozenset(
    {
        "runtime",
        "assist",
        "authority",
        "assignment",
        "plan",
        "control",
        "physical",
        "formal_admission",
        "production_admission",
        "optimizer",
        "checkpoint_selection",
        "normalization_refit",
        "threshold_adjustment",
    }
)
_AUTHORITY_KEYS = (
    "runtime",
    "assist",
    "authority",
    "assignment",
    "plan",
    "control",
    "physical",
    "formal_admission",
    "production_admission",
)
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CSV_FIELDS = (
    "evaluation_group",
    "evaluation_subgroup",
    "source_split",
    "scenario_version",
    "seed",
    "episode",
    "frame_index",
    "timestamp_s",
    "teacher_opportunity",
    "r0_selected_edges",
    "candidate_selected_edges",
    "effective_selected_edges",
    "candidate_binding_change_count",
    "effective_binding_change_count",
    "positive_teacher_exact_match",
    "negative_exact_r0",
    "ood",
    "rejected",
    "rejection_reasons",
    "fallback_exact_r0_matrix",
    "fallback_exact_r0_binding",
)
_FORBIDDEN_IDENTITY_KEYS = frozenset(
    {
        "actorid",
        "actorname",
        "objectid",
        "objectname",
        "simobjectid",
        "simobjectname",
        "meshname",
        "globaltrackid",
        "targetid",
        "resourceid",
        "vehicleid",
        "vehiclename",
        "groundtruthid",
    }
)


class D3A1V2ExternalAuditError(ValueError):
    """Stable fail-closed error raised for invalid audit evidence."""

    def __init__(self, code: str, detail: str = "") -> None:
        message = code if not detail else f"{code}: {detail}"
        super().__init__(message)
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class D3A1V2ExternalAuditInputs:
    """Read-only paths and explicit identity for one external audit."""

    repository_root: Path
    result_dir: Path
    generation_root: Path
    dataset_dir: Path
    contract_path: Path
    bundle_dir: Path
    audit_id: str
    evaluated_at_utc: str

    def __post_init__(self) -> None:
        root = _resolve_directory(self.repository_root, "repository_root")
        object.__setattr__(self, "repository_root", root)
        for name in ("result_dir", "generation_root", "dataset_dir", "bundle_dir"):
            value = Path(getattr(self, name))
            if not value.is_absolute():
                value = root / value
            object.__setattr__(self, name, _resolve_directory(value, name))
        contract = Path(self.contract_path)
        if not contract.is_absolute():
            contract = root / contract
        object.__setattr__(
            self,
            "contract_path",
            _resolve_regular_file(contract, "contract_path"),
        )
        expected_dataset = (
            self.generation_root / "learning_dataset/d3_assignment"
        ).resolve()
        if self.dataset_dir != expected_dataset:
            _fail(
                "dataset_generation_path_mismatch",
                f"expected={expected_dataset};actual={self.dataset_dir}",
            )
        if not self.audit_id.strip() or not self.evaluated_at_utc.strip():
            _fail("audit_identity_invalid", self.audit_id)


@dataclass(frozen=True, slots=True)
class _DatasetFrameInfo:
    key: tuple[str, int, str, int, float, str]
    resource_count: int
    target_count: int
    rule_shape: tuple[int, int]
    action_shape: tuple[int, int]
    candidate_edge_count: int
    demand_slot_count: int
    resource_capacities: tuple[int, ...]
    target_demand_slots: tuple[int, ...]
    action_mask: tuple[tuple[bool, ...], ...]
    rule_cost_matrix_sha256: str


@dataclass(frozen=True, slots=True)
class _IndependentEdgeSafety:
    edge_count: int
    edge_index_out_of_range_count: int
    duplicate_resource_count: int
    hard_edge_violation_count: int
    m_to_n_atomicity_violation_count: int


def audit_d3_a1_source_independent_v2(
    inputs: D3A1V2ExternalAuditInputs,
) -> dict[str, Any]:
    """Recompute the v2 evidence and return a non-authoritative audit."""

    contract = _load_json_object(inputs.contract_path, "contract")
    contract_sha = _sha256_file(inputs.contract_path)
    contract_info = _validate_contract(inputs, contract, contract_sha)

    result_hashes = _verify_result_inventory(
        inputs.result_dir,
        expected_files=_EXPECTED_RESULT_FILES,
    )
    aggregate = _load_json_object(
        inputs.result_dir / "aggregate.json",
        "d3_aggregate",
    )
    dataset_hashes = _verify_dataset_inventory(inputs.dataset_dir)
    bundle_hashes = _verify_bundle(inputs.bundle_dir, contract)
    claimed_source = _mapping(
        aggregate.get("source_summary"),
        "aggregate_source_summary",
    )
    frozen_source = _verify_frozen_source(
        inputs,
        contract,
        evaluation_commit_claim=str(
            claimed_source.get("repository_git_commit", "")
        ),
    )

    generation = _audit_generation_evidence(
        inputs,
        contract=contract,
        dataset_hashes=dataset_hashes,
    )
    dataset = _audit_dataset(
        inputs.dataset_dir,
        contract=contract,
        dataset_hashes=dataset_hashes,
    )
    rows = tuple(
        _iter_jsonl_objects(
            inputs.result_dir / "per_frame_evaluation.jsonl",
            "d3_per_frame",
        )
    )
    recomputation = _audit_evaluation_rows(
        rows,
        csv_path=inputs.result_dir / "per_frame_evaluation.csv",
        contract=contract,
        dataset_frames=dataset["frames_by_key"],
        cell_by_seed=contract_info["cell_by_seed"],
    )
    gate = _recompute_preregistered_gate(
        contract=contract,
        metrics=recomputation["overall_metrics"],
        generation=generation,
        dataset=dataset,
        bundle_hashes=bundle_hashes,
        all_inputs_finite=(
            generation["all_values_finite"]
            and dataset["all_values_finite"]
            and recomputation["all_values_finite"]
            and _is_finite_tree(aggregate)
        ),
    )
    reconciliation = _reconcile_d3_claims(
        aggregate,
        contract=contract,
        contract_sha256=contract_sha,
        bundle_hashes=bundle_hashes,
        frozen_source=frozen_source,
        generation=generation,
        dataset=dataset,
        recomputation=recomputation,
        gate=gate,
    )

    pre_snapshot = {
        **{f"result/{name}": digest for name, digest in result_hashes.items()},
        **{f"dataset/{name}": digest for name, digest in dataset_hashes.items()},
        **{f"generation/{name}": digest for name, digest in generation["file_hashes"].items()},
        **{f"bundle/{name}": digest for name, digest in bundle_hashes["file_hashes"].items()},
        "contract": contract_sha,
    }
    post_snapshot = _post_audit_snapshot(inputs, pre_snapshot)
    mutations = sorted(
        name
        for name, digest in pre_snapshot.items()
        if post_snapshot.get(name) != digest
    )
    if mutations:
        _fail("input_mutation_detected", ",".join(mutations))

    authorities = {key: False for key in _AUTHORITY_KEYS}
    test_generalization = recomputation["source_subgroup_metrics"]["test"][
        "positive_teacher_exact_match"
    ]
    result: dict[str, Any] = {
        "schema_version": D3_A1_V2_AUDIT_SCHEMA_VERSION,
        "audit_id": inputs.audit_id,
        "evaluated_at_utc": inputs.evaluated_at_utc,
        "status": D3_A1_V2_AUDIT_STATUS,
        "audit_integrity_passed": True,
        "scope": {
            "independent_read_only_external_audit": True,
            "d3_high_level_evaluator_import_count": 0,
            "training_count": 0,
            "model_selection_count": 0,
            "normalization_fit_count": 0,
            "threshold_adjustment_count": 0,
            "formal_seed_read_count": 0,
            "physical_evidence_confirmed": False,
            "runtime_adoption_confirmed": False,
        },
        "input_integrity": {
            "contract_sha256": contract_sha,
            "result_file_sha256": result_hashes,
            "generation_file_sha256": generation["file_hashes"],
            "dataset_file_sha256": dataset_hashes,
            "dataset_tree_sha256": dataset["dataset_tree_sha256"],
            "dataset_split_sha256": dataset["split_hash"],
            "bundle_file_sha256": bundle_hashes["file_hashes"],
            "bundle_tree_sha256": bundle_hashes["tree_sha256"],
            "frozen_source_tree_sha256": frozen_source["tree_sha256"],
            "input_mutation_count": 0,
            "input_mutations": [],
        },
        "generation_audit": _without_internal_keys(generation),
        "dataset_audit": _without_internal_keys(dataset),
        "independent_recomputation": recomputation,
        "preregistered_machine_gate": gate,
        "claim_reconciliation": reconciliation,
        "generalization_limit": {
            "test_positive_teacher_exact_match_numerator": test_generalization[
                "numerator"
            ],
            "test_positive_teacher_exact_match_denominator": test_generalization[
                "denominator"
            ],
            "test_positive_teacher_exact_match_rate": test_generalization["rate"],
            "interpretation": (
                "测试子组教师完全匹配为0/25；预注册门限仅适用于292帧总体聚合，"
                "本审计不增设结果后门限，也不据此授予运行权限。"
            ),
        },
        "authorities": authorities,
        "conclusion": {
            "offline_result_integrity_confirmed": True,
            "preregistered_machine_gate_confirmed": bool(gate["passed"]),
            "runtime_or_formal_admission_granted": False,
            "physical_benefit_confirmed": False,
        },
    }
    if not gate["passed"]:
        _fail("independent_preregistered_machine_gate_failed")
    result["content_sha256"] = _content_sha256(result)
    return result


def write_d3_a1_source_independent_v2_audit(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Write a deterministic JSON/Chinese report bundle without overwrite."""

    root = Path(output_dir)
    if root.exists() or root.is_symlink():
        _fail("output_directory_already_exists", str(root))
    root.mkdir(parents=True, exist_ok=False)
    json_path = root / "audit.json"
    report_path = root / "D3_A1_SOURCE_INDEPENDENT_V2_EXTERNAL_AUDIT_CN.md"
    json_path.write_text(
        json.dumps(
            dict(result),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        render_d3_a1_source_independent_v2_audit_cn(result),
        encoding="utf-8",
    )
    checksum_path = root / "SHA256SUMS"
    checksum_path.write_text(
        "".join(
            f"{_sha256_file(path)}  {path.name}\n"
            for path in (json_path, report_path)
        ),
        encoding="ascii",
    )
    return {
        "json": json_path,
        "report": report_path,
        "checksums": checksum_path,
    }


def render_d3_a1_source_independent_v2_audit_cn(
    result: Mapping[str, Any],
) -> str:
    """Render the independent audit conclusion in Chinese."""

    overall = result["independent_recomputation"]["overall_metrics"]
    groups = result["independent_recomputation"]["source_subgroup_metrics"]
    csv_closure = result["independent_recomputation"]["csv_jsonl_closure"]
    safety = result["independent_recomputation"][
        "independent_selected_edge_safety"
    ]
    generalization = result["generalization_limit"]
    gate = result["preregistered_machine_gate"]
    integrity = result["input_integrity"]
    lines = [
        "# D3 A1 来源独立 v2 结果外部审计",
        "",
        f"审计日期：{result['evaluated_at_utc']}",
        "",
        "## 结论",
        "",
        (
            "D6 独立复算确认结果目录完整，数据源未含在线真值或实体身份字段，"
            "逐帧指标与 D3 汇总闭合，预注册总体机器门通过。"
        ),
        (
            "该结论只适用于离线证据完整性和预注册机器门。运行、辅助、分配、计划、"
            "控制、物理、正式及生产权限均保持关闭。"
        ),
        "",
        "## 数据与完整性",
        "",
        f"- episode：{result['dataset_audit']['episode_count']}。",
        f"- 评价帧：{overall['frame_count']}。",
        "- seed：20000-20099；正式 seed 1000-1019 读取数为 0。",
        f"- 数据集帧摘要：`{integrity['dataset_file_sha256']['frames.jsonl']}`。",
        f"- 数据集树摘要：`{integrity['dataset_tree_sha256']}`。",
        f"- 数据集 split 摘要：`{integrity['dataset_split_sha256']}`。",
        f"- 冻结模型树摘要：`{integrity['bundle_tree_sha256']}`。",
        f"- 冻结评价源码摘要：`{integrity['frozen_source_tree_sha256']}`。",
        (
            f"- 逐帧 CSV 固定 {csv_closure['fixed_column_count']} 列、"
            f"{csv_closure['row_count']} 行，与 JSONL 逐行不一致数为 "
            f"{csv_closure['mismatch_count']}。"
        ),
        "- 输入审计前后摘要一致，文件变更数为 0。",
        "",
        "## 总体复算",
        "",
        "| 指标 | 复算结果 | 预注册门限 |",
        "| --- | ---: | ---: |",
        (
            "| 正类安全换绑 | "
            f"{overall['positive_safe_binding_change']['numerator']}/"
            f"{overall['positive_safe_binding_change']['denominator']} "
            f"({overall['positive_safe_binding_change']['rate']:.2%}) | >=5% 且至少1帧 |"
        ),
        (
            "| 正类教师完全匹配 | "
            f"{overall['positive_teacher_exact_match']['numerator']}/"
            f"{overall['positive_teacher_exact_match']['denominator']} "
            f"({overall['positive_teacher_exact_match']['rate']:.2%}) | >=2% 且至少1帧 |"
        ),
        (
            "| 负类保持规则基线 | "
            f"{overall['negative_exact_r0']['numerator']}/"
            f"{overall['negative_exact_r0']['denominator']} "
            f"({overall['negative_exact_r0']['rate']:.2%}) | >=99% |"
        ),
        f"| 投影拒绝 | {overall['projection_rejection_count']} | 记录分布完整 |",
        f"| 非零代价修正 | {overall['nonzero_cost_correction_frame_count']} | 记录项 |",
        f"| 分布外帧 | {overall['ood_frame_count']} | 记录分布完整 |",
        "",
        "预注册机器门复算结果：" + ("通过。" if gate["passed"] else "未通过。"),
        "",
        "## 分组结果",
        "",
        "| 子组 | 帧数 | 正类安全换绑 | 教师完全匹配 | 负类规则保持 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for split in _SPLITS:
        metric = groups[split]
        lines.append(
            f"| {split} | {metric['frame_count']} | "
            f"{metric['positive_safe_binding_change']['numerator']}/"
            f"{metric['positive_safe_binding_change']['denominator']} | "
            f"{metric['positive_teacher_exact_match']['numerator']}/"
            f"{metric['positive_teacher_exact_match']['denominator']} | "
            f"{metric['negative_exact_r0']['numerator']}/"
            f"{metric['negative_exact_r0']['denominator']} |"
        )
    lines.extend(
        [
            "",
            "## 安全与权限",
            "",
            (
                "D6 从动作掩码、目标需求和资源容量独立重算规则、候选、有效三组边；"
                f"有效边越界、容量超额、硬禁边和 M 对 N 原子性违规分别为 "
                f"{safety['groups']['effective']['edge_index_out_of_range_count']}、"
                f"{safety['groups']['effective']['duplicate_resource_count']}、"
                f"{safety['groups']['effective']['hard_edge_violation_count']}、"
                f"{safety['groups']['effective']['m_to_n_atomicity_violation_count']}。"
            ),
            "版本和规则矩阵突变违规均为 0。",
            "模型分配、计划和运行输出均为 0。94 个拒绝帧的矩阵和绑定全部回退为规则基线。",
            "",
            "## 剩余限制",
            "",
            (
                "test 子组教师完全匹配为 "
                f"{generalization['test_positive_teacher_exact_match_numerator']}/"
                f"{generalization['test_positive_teacher_exact_match_denominator']}。"
                "合同门限预注册为 292 帧总体聚合门，"
                "因此不能在结果产生后增加子组准入门限。该现象仍说明未见数据上的"
                "教师一致性泛化不足，后续正式保留集和物理收益验证仍不可省略。"
            ),
            "",
            (
                "本审计未验证运行采用、计划发布、控制效果、物理拦截或生产可用性，"
                "也未读取正式 seed 1000-1019。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _validate_contract(
    inputs: D3A1V2ExternalAuditInputs,
    contract: Mapping[str, Any],
    contract_sha256: str,
) -> dict[str, Any]:
    if contract_sha256 != _EXPECTED_CONTRACT_SHA256:
        _fail("contract_sha256_mismatch", contract_sha256)
    expected_path = (
        inputs.repository_root
        / "research_modules/d3_assignment_planner/configs/"
        "a1_source_independent_evaluation_contract_v2.json"
    ).resolve()
    if inputs.contract_path != expected_path:
        _fail("official_contract_path_mismatch", str(inputs.contract_path))
    if contract.get("schema_version") != _EXPECTED_CONTRACT_SCHEMA:
        _fail("contract_schema_mismatch", str(contract.get("schema_version")))
    if contract.get("contract_id") != _EXPECTED_CONTRACT_ID:
        _fail("contract_id_mismatch", str(contract.get("contract_id")))
    if contract.get("mode") != _EXPECTED_MODE:
        _fail("contract_mode_mismatch", str(contract.get("mode")))
    if set(contract.get("output_files", ())) != _EXPECTED_RESULT_FILES:
        _fail("contract_output_inventory_mismatch")
    output = _mapping(contract.get("output_identity"), "output_identity")
    if output != {
        "result_identity": "d3-a1-source-independent-evaluation-result-v2",
        "frame_schema_version": "d3_a1_source_independent_evaluation_frame_v2",
        "aggregate_schema_version": "d3_a1_source_independent_evaluation_aggregate_v2",
        "requires_new_output_directory": True,
    }:
        _fail("contract_output_identity_mismatch")
    permissions = _mapping(contract.get("permissions"), "contract_permissions")
    _require_all_permissions_false(permissions, "contract")
    if set(permissions) != _EXPECTED_PERMISSION_KEYS:
        _fail("contract_permission_inventory_mismatch")
    source = _mapping(contract.get("source_dataset"), "source_dataset")
    seeds = tuple(_integer(value, "source_seed") for value in source.get("seed_values", ()))
    if len(seeds) != 100 or frozenset(seeds) != _EXPECTED_EVALUATION_SEEDS:
        _fail("contract_source_seed_universe_mismatch")
    if source.get("episode_count") != 100 or source.get("unique_seed_count") != 100:
        _fail("contract_source_count_mismatch")
    if source.get("split_seed_counts") != _EXPECTED_SPLIT_EPISODES:
        _fail("contract_split_seed_counts_mismatch")
    if source.get("generation_schedule_sha256") != _EXPECTED_SCHEDULE_SHA256:
        _fail("contract_schedule_sha256_mismatch")
    formal = frozenset(
        _integer(value, "formal_seed")
        for value in source.get("formal_holdout_seed_values", ())
    )
    training = frozenset(
        _integer(value, "training_seed")
        for value in source.get("training_seed_values", ())
    )
    if formal != _EXPECTED_FORMAL_SEEDS:
        _fail("contract_formal_seed_universe_mismatch")
    if training & formal or training & _EXPECTED_EVALUATION_SEEDS:
        _fail("contract_seed_class_overlap")
    cells = source.get("cells")
    if not isinstance(cells, list):
        _fail("contract_cells_invalid")
    cell_by_seed: dict[int, Mapping[str, Any]] = {}
    for cell in cells:
        item = _mapping(cell, "source_cell")
        for seed in item.get("seed_values", ()):
            numeric_seed = _integer(seed, "cell_seed")
            if numeric_seed in cell_by_seed:
                _fail("contract_duplicate_cell_seed", str(numeric_seed))
            cell_by_seed[numeric_seed] = item
    if frozenset(cell_by_seed) != _EXPECTED_EVALUATION_SEEDS:
        _fail("contract_cell_seed_universe_mismatch")
    frozen_bundle = _mapping(contract.get("frozen_bundle"), "frozen_bundle")
    if (
        frozen_bundle.get("manifest_sha256") != _EXPECTED_BUNDLE_MANIFEST_SHA256
        or frozen_bundle.get("state_dict_sha256") != _EXPECTED_BUNDLE_STATE_SHA256
        or frozen_bundle.get("tree_sha256") != _EXPECTED_BUNDLE_TREE_SHA256
    ):
        _fail("contract_frozen_bundle_hash_mismatch")
    frozen_source = _mapping(contract.get("frozen_source"), "frozen_source")
    if frozen_source.get("tree_sha256") != _EXPECTED_SOURCE_TREE_SHA256:
        _fail("contract_frozen_source_hash_mismatch")
    _assert_finite(contract, "contract")
    return {
        "cell_by_seed": cell_by_seed,
        "training_seed_values": sorted(training),
        "formal_seed_values": sorted(formal),
    }


def _verify_result_inventory(
    root: Path,
    *,
    expected_files: Iterable[str],
) -> dict[str, str]:
    expected = frozenset(str(name) for name in expected_files)
    actual = frozenset(path.name for path in root.iterdir())
    if actual != expected:
        _fail(
            "result_file_inventory_mismatch",
            f"missing={sorted(expected - actual)};extra={sorted(actual - expected)}",
        )
    for name in sorted(expected):
        _resolve_regular_file(root / name, f"result/{name}")
    payload = expected - {"SHA256SUMS"}
    checksums = _parse_checksums(root / "SHA256SUMS", payload)
    actual_hashes = {name: _sha256_file(root / name) for name in sorted(expected)}
    for name in payload:
        if checksums[name] != actual_hashes[name]:
            _fail("result_checksum_mismatch", name)
    return actual_hashes


def _verify_dataset_inventory(root: Path) -> dict[str, str]:
    actual = frozenset(path.name for path in root.iterdir())
    if actual != _EXPECTED_DATASET_FILES:
        _fail(
            "dataset_file_inventory_mismatch",
            f"missing={sorted(_EXPECTED_DATASET_FILES - actual)};"
            f"extra={sorted(actual - _EXPECTED_DATASET_FILES)}",
        )
    return {
        name: _sha256_file(_resolve_regular_file(root / name, f"dataset/{name}"))
        for name in sorted(_EXPECTED_DATASET_FILES)
    }


def _verify_bundle(
    root: Path,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    actual = frozenset(path.name for path in root.iterdir())
    if actual != _EXPECTED_BUNDLE_FILES:
        _fail("bundle_file_inventory_mismatch")
    for name in sorted(actual):
        _resolve_regular_file(root / name, f"bundle/{name}")
    checksums = _parse_checksums(
        root / "SHA256SUMS",
        _EXPECTED_BUNDLE_FILES - {"SHA256SUMS"},
    )
    file_hashes = {name: _sha256_file(root / name) for name in sorted(actual)}
    for name, expected in checksums.items():
        if file_hashes[name] != expected:
            _fail("bundle_checksum_mismatch", name)
    frozen = _mapping(contract.get("frozen_bundle"), "frozen_bundle")
    if file_hashes["manifest.json"] != frozen.get("manifest_sha256"):
        _fail("bundle_manifest_sha256_mismatch")
    if file_hashes["state_dict.json"] != frozen.get("state_dict_sha256"):
        _fail("bundle_state_sha256_mismatch")
    tree = _named_hash_tree(
        {
            "manifest.json": file_hashes["manifest.json"],
            "state_dict.json": file_hashes["state_dict.json"],
        }
    )
    if tree != frozen.get("tree_sha256"):
        _fail("bundle_tree_sha256_mismatch", tree)
    manifest = _load_json_object(root / "manifest.json", "bundle_manifest")
    _assert_finite(manifest, "bundle_manifest")
    if manifest.get("bundle_schema_version") != frozen.get("bundle_schema_version"):
        _fail("bundle_schema_mismatch")
    if manifest.get("policy_version") != frozen.get("policy_version"):
        _fail("bundle_policy_version_mismatch")
    admission = _mapping(manifest.get("admission"), "bundle_admission")
    if admission.get("admitted_bundle") is not False or admission.get("production_bundle") is not False:
        _fail("bundle_admission_claim_forbidden")
    _require_all_permissions_false(
        _mapping(manifest.get("permissions"), "bundle_permissions"),
        "bundle",
    )
    return {
        "file_hashes": file_hashes,
        "tree_sha256": tree,
        "manifest": manifest,
    }


def _verify_frozen_source(
    inputs: D3A1V2ExternalAuditInputs,
    contract: Mapping[str, Any],
    *,
    evaluation_commit_claim: str,
) -> dict[str, Any]:
    module_root = (
        inputs.repository_root / "research_modules/d3_assignment_planner"
    ).resolve()
    frozen = _mapping(contract.get("frozen_source"), "frozen_source")
    files = tuple(str(value) for value in frozen.get("files", ()))
    digest = sha256()
    for relative in sorted(files):
        path = _resolve_regular_file(module_root / relative, f"frozen_source/{relative}")
        try:
            path.relative_to(module_root)
        except ValueError:
            _fail("frozen_source_path_escape", relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    tree = digest.hexdigest()
    if tree != frozen.get("tree_sha256"):
        _fail("frozen_source_tree_sha256_mismatch", tree)
    current_commit = _git_output(inputs.repository_root, ["rev-parse", "HEAD"])
    status = _git_output(
        inputs.repository_root,
        ["status", "--porcelain", "--", *[str(module_root / item) for item in files]],
    )
    if frozen.get("require_git_clean") is True and status:
        _fail("frozen_source_dirty", status)
    if re.fullmatch(r"[0-9a-f]{40}", evaluation_commit_claim) is None:
        _fail("evaluation_source_commit_invalid", evaluation_commit_claim)
    _git_output(
        inputs.repository_root,
        ["cat-file", "-e", f"{evaluation_commit_claim}^{{commit}}"],
    )
    historical_digest = sha256()
    module_prefix = "research_modules/d3_assignment_planner"
    for relative in sorted(files):
        blob = _git_bytes(
            inputs.repository_root,
            ["show", f"{evaluation_commit_claim}:{module_prefix}/{relative}"],
        )
        historical_digest.update(relative.encode("utf-8"))
        historical_digest.update(b"\0")
        historical_digest.update(sha256(blob).hexdigest().encode("ascii"))
        historical_digest.update(b"\n")
    historical_tree = historical_digest.hexdigest()
    if historical_tree != frozen.get("tree_sha256"):
        _fail(
            "evaluation_commit_source_tree_sha256_mismatch",
            historical_tree,
        )
    return {
        "tree_sha256": tree,
        "evaluation_repository_git_commit": evaluation_commit_claim,
        "evaluation_commit_tree_sha256": historical_tree,
        "current_repository_git_commit": current_commit,
        "owned_source_dirty": bool(status),
    }


def _audit_generation_evidence(
    inputs: D3A1V2ExternalAuditInputs,
    *,
    contract: Mapping[str, Any],
    dataset_hashes: Mapping[str, str],
) -> dict[str, Any]:
    names = (
        "generation_plan.json",
        "generation_summary.json",
        "generation_checkpoint.json",
        "episode_progress.jsonl",
        "training_seed_registry.json",
    )
    paths = {
        name: _resolve_regular_file(inputs.generation_root / name, f"generation/{name}")
        for name in names
    }
    hashes = {name: _sha256_file(path) for name, path in paths.items()}
    plan = _load_json_object(paths["generation_plan.json"], "generation_plan")
    summary = _load_json_object(paths["generation_summary.json"], "generation_summary")
    checkpoint = _load_json_object(
        paths["generation_checkpoint.json"], "generation_checkpoint"
    )
    registry = _load_json_object(
        paths["training_seed_registry.json"], "training_seed_registry"
    )
    progress = tuple(_iter_jsonl_objects(paths["episode_progress.jsonl"], "episode_progress"))
    for name, value in (
        ("generation_plan", plan),
        ("generation_summary", summary),
        ("generation_checkpoint", checkpoint),
        ("training_seed_registry", registry),
        ("episode_progress", progress),
    ):
        _assert_finite(value, name)
    source = _mapping(contract.get("source_dataset"), "source_dataset")
    expected_seeds = frozenset(source["seed_values"])
    expected_schedule = source["generation_schedule_sha256"]
    if expected_schedule != _EXPECTED_SCHEDULE_SHA256:
        _fail("generation_contract_schedule_mismatch")
    for name, value in (("plan", plan), ("summary", summary), ("registry", registry)):
        if value.get("schedule_sha256") != expected_schedule:
            _fail("generation_schedule_mismatch", name)
        if value.get("repository_dirty") is not False:
            _fail("generation_repository_dirty", name)
    source_commits = {
        str(value.get("git_commit")) for value in (plan, summary, checkpoint, registry)
    }
    if len(source_commits) != 1:
        _fail("generation_source_commit_mismatch", repr(sorted(source_commits)))
    source_commit = next(iter(source_commits))
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        _fail("generation_source_commit_invalid", source_commit)
    _git_output(inputs.repository_root, ["cat-file", "-e", f"{source_commit}^{{commit}}"])
    if plan.get("learning_export_components") != ["d3"]:
        _fail("generation_component_scope_mismatch", "plan")
    if summary.get("learning_export_components") != ["d3"]:
        _fail("generation_component_scope_mismatch", "summary")
    if plan.get("cell_count") != 100 or summary.get("cell_count") != 100:
        _fail("generation_cell_count_mismatch")
    if summary.get("completed_episode_count") != 100:
        _fail("generation_episode_count_mismatch")
    if checkpoint.get("completed_episode_count") != 100 or checkpoint.get("remaining_episode_count") != 0:
        _fail("generation_checkpoint_incomplete")
    if checkpoint.get("state") != "finalized":
        _fail("generation_checkpoint_not_finalized")
    if checkpoint.get("plan_sha256") != hashes["generation_plan.json"]:
        _fail("generation_checkpoint_plan_hash_mismatch")
    if checkpoint.get("generation_summary_sha256") != hashes["generation_summary.json"]:
        _fail("generation_checkpoint_summary_hash_mismatch")
    if summary.get("training_seed_registry_sha256") != hashes["training_seed_registry.json"]:
        _fail("generation_registry_hash_mismatch")
    plan_cells = tuple(plan.get("cells", ()))
    summary_cells = tuple(summary.get("cells", ()))
    if plan_cells != summary_cells or len(plan_cells) != 100:
        _fail("generation_cell_inventory_mismatch")
    cell_seeds = frozenset(_integer(cell.get("seed"), "generation_cell_seed") for cell in plan_cells)
    if cell_seeds != expected_seeds:
        _fail("generation_seed_universe_mismatch")
    if len(progress) != 100:
        _fail("generation_progress_count_mismatch", str(len(progress)))
    progress_seeds = frozenset(_integer(row.get("seed"), "progress_seed") for row in progress)
    if progress_seeds != expected_seeds:
        _fail("generation_progress_seed_mismatch")
    if {row.get("sequence") for row in progress} != set(range(100)):
        _fail("generation_progress_sequence_mismatch")
    if any(row.get("finite_state") is not True for row in progress):
        _fail("generation_nonfinite_state")
    online_truth = sum(_integer(row.get("online_truth_use_count"), "online_truth_use_count") for row in progress)
    if online_truth != 0:
        _fail("generation_online_truth_use_nonzero", str(online_truth))
    if any(row.get("repository_dirty") is not False for row in progress):
        _fail("generation_progress_dirty")
    if any(row.get("learning_export_components") != ["d3"] for row in progress):
        _fail("generation_progress_component_scope_mismatch")
    exported_frames = sum(_integer(row.get("d3_exported_frame_count"), "d3_exported_frame_count") for row in progress)
    if exported_frames != 292:
        _fail("generation_exported_frame_count_mismatch", str(exported_frames))
    export = _mapping(summary.get("learning_export_summary"), "learning_export_summary")
    if (
        export.get("learning_export_components") != ["d3"]
        or export.get("online_truth_policy") != "forbidden"
        or export.get("episode_count") != 100
        or export.get("d3_frame_count") != 292
        or export.get("d3_split_frame_counts") != _EXPECTED_SPLIT_FRAMES
        or export.get("d4_frame_count") != 0
        or export.get("d5_staged_frame_count") != 0
        or export.get("d5_active_vision_frame_count") != 0
    ):
        _fail("generation_export_summary_mismatch")
    training_seeds = frozenset(registry.get("training_seeds", ()))
    formal_seeds = frozenset(registry.get("reserved_evaluation_seeds", ()))
    if training_seeds != expected_seeds or formal_seeds != _EXPECTED_FORMAL_SEEDS:
        _fail("generation_seed_registry_mismatch")
    overlap = training_seeds & formal_seeds
    if overlap or registry.get("overlap_count") != 0:
        _fail("generation_formal_seed_overlap", repr(sorted(overlap)))
    if _mapping(summary.get("learning_export_summary"), "learning_export_summary").get("d3_frame_count") != 292:
        _fail("generation_dataset_frame_binding_mismatch")
    if dataset_hashes["frames.jsonl"] == "":
        _fail("dataset_frames_hash_unavailable")
    return {
        "file_hashes": hashes,
        "source_git_commit": source_commit,
        "repository_clean": True,
        "episode_count": 100,
        "seed_count": 100,
        "seed_values": sorted(progress_seeds),
        "schedule_sha256": expected_schedule,
        "learning_export_components": ["d3"],
        "finite_failure_count": 0,
        "online_truth_use_count": 0,
        "formal_seed_overlap_count": 0,
        "all_values_finite": True,
    }


def _audit_dataset(
    root: Path,
    *,
    contract: Mapping[str, Any],
    dataset_hashes: Mapping[str, str],
) -> dict[str, Any]:
    manifest = _load_json_object(root / "dataset_manifest.json", "dataset_manifest")
    _assert_finite(manifest, "dataset_manifest")
    source = _mapping(contract.get("source_dataset"), "source_dataset")
    if manifest.get("schema_version") != source.get("dataset_schema_version"):
        _fail("dataset_schema_mismatch")
    if manifest.get("source_kind") != source.get("source_kind"):
        _fail("dataset_source_kind_mismatch")
    if manifest.get("split_policy_version") != source.get("split_policy_version"):
        _fail("dataset_split_policy_mismatch")
    if manifest.get("frames_sha256") != dataset_hashes["frames.jsonl"]:
        _fail("dataset_frames_sha256_mismatch")
    if manifest.get("episode_count") != 100 or manifest.get("frame_count") != 292:
        _fail("dataset_manifest_count_mismatch")
    if manifest.get("split_episode_counts") != _EXPECTED_SPLIT_EPISODES:
        _fail("dataset_manifest_split_episode_mismatch")
    if manifest.get("split_frame_counts") != _EXPECTED_SPLIT_FRAMES:
        _fail("dataset_manifest_split_frame_mismatch")
    split_seed_values = _mapping(manifest.get("split_seed_values"), "split_seed_values")
    if set(split_seed_values) != set(_SPLITS):
        _fail("dataset_split_inventory_mismatch")
    split_seeds = {
        split: frozenset(_integer(seed, f"{split}_seed") for seed in split_seed_values[split])
        for split in _SPLITS
    }
    if {split: len(values) for split, values in split_seeds.items()} != _EXPECTED_SPLIT_EPISODES:
        _fail("dataset_split_seed_count_mismatch")
    if set.union(*(set(values) for values in split_seeds.values())) != set(_EXPECTED_EVALUATION_SEEDS):
        _fail("dataset_seed_universe_mismatch")
    if any(split_seeds[left] & split_seeds[right] for left in _SPLITS for right in _SPLITS if left < right):
        _fail("dataset_split_seed_overlap")
    if _EXPECTED_FORMAL_SEEDS & set(_EXPECTED_EVALUATION_SEEDS):
        _fail("dataset_formal_seed_overlap")
    training_seeds = frozenset(source.get("training_seed_values", ()))
    if training_seeds & _EXPECTED_EVALUATION_SEEDS or training_seeds & _EXPECTED_FORMAL_SEEDS:
        _fail("dataset_training_seed_overlap")

    frames_by_key: dict[tuple[str, int, str, int, float, str], _DatasetFrameInfo] = {}
    episodes_by_split: dict[str, set[str]] = defaultdict(set)
    derived_seed_splits: dict[int, str] = {}
    derived_episode_splits: dict[tuple[str, int, str], str] = {}
    frame_counts: Counter[str] = Counter()
    forbidden_count = 0
    forbidden_paths: list[str] = []
    for line_number, record in enumerate(
        _iter_jsonl_objects(root / "frames.jsonl", "dataset_frames"),
        start=1,
    ):
        _assert_finite(record, f"dataset_frames:{line_number}")
        findings = _find_forbidden_identity_keys(record)
        forbidden_count += len(findings)
        forbidden_paths.extend(
            f"line={line_number}:{path}" for path in findings[: max(0, 20 - len(forbidden_paths))]
        )
        if forbidden_count:
            _fail("dataset_forbidden_identity_field", ",".join(forbidden_paths))
        if record.get("schema_version") != source.get("dataset_schema_version"):
            _fail("dataset_frame_schema_mismatch", str(line_number))
        split = str(record.get("split"))
        seed = _integer(record.get("seed"), "dataset_frame_seed")
        if split not in _SPLITS or seed not in split_seeds[split]:
            _fail("dataset_frame_split_mismatch", f"line={line_number}")
        episode = str(record.get("episode"))
        scenario = str(record.get("scenario_version"))
        frame_index = _integer(record.get("frame_index"), "dataset_frame_index")
        timestamp = _finite_float(record.get("timestamp_s"), "dataset_timestamp")
        resources = _sequence(record.get("anonymous_resources"), "anonymous_resources")
        targets = _sequence(record.get("anonymous_targets"), "anonymous_targets")
        resource_capacities = tuple(
            _nonnegative_integer(
                _mapping(resource, "anonymous_resource").get("assignment_capacity"),
                "resource_assignment_capacity",
            )
            for resource in resources
        )
        target_demand_slots = tuple(
            _positive_integer(value, "target_demand_slot")
            for value in _sequence(
                record.get("target_demand_slots"),
                "target_demand_slots",
            )
        )
        if len(target_demand_slots) != len(targets):
            _fail("dataset_target_demand_count_mismatch", str(line_number))
        rule_matrix = record.get("rule_cost_matrix")
        rule_shape = _matrix_shape(rule_matrix, "rule_cost_matrix")
        action_mask = _strict_boolean_matrix(record.get("action_mask"), "action_mask")
        action_shape = _matrix_shape(action_mask, "action_mask")
        expected_shape = (len(targets), len(resources))
        if rule_shape != expected_shape or action_shape != expected_shape:
            _fail(
                "dataset_target_resource_shape_mismatch",
                f"line={line_number};expected={expected_shape};"
                f"rule={rule_shape};action={action_shape}",
            )
        rule_cost_matrix_sha256 = _float64_matrix_sha256(rule_matrix)
        key = (episode, seed, scenario, frame_index, timestamp, split)
        if key in frames_by_key:
            _fail("dataset_duplicate_frame_identity", repr(key))
        frames_by_key[key] = _DatasetFrameInfo(
            key=key,
            resource_count=len(resources),
            target_count=len(targets),
            rule_shape=rule_shape,
            action_shape=action_shape,
            candidate_edge_count=len(_sequence(record.get("candidate_edge_indices"), "candidate_edge_indices")),
            demand_slot_count=len(target_demand_slots),
            resource_capacities=resource_capacities,
            target_demand_slots=target_demand_slots,
            action_mask=action_mask,
            rule_cost_matrix_sha256=rule_cost_matrix_sha256,
        )
        prior_seed_split = derived_seed_splits.setdefault(seed, split)
        if prior_seed_split != split:
            _fail("dataset_derived_seed_split_conflict", str(seed))
        episode_key = (scenario, seed, episode)
        prior_episode_split = derived_episode_splits.setdefault(episode_key, split)
        if prior_episode_split != split:
            _fail("dataset_derived_episode_split_conflict", repr(episode_key))
        episodes_by_split[split].add(episode)
        frame_counts[split] += 1
    if len(frames_by_key) != 292:
        _fail("dataset_frame_count_mismatch", str(len(frames_by_key)))
    if dict(frame_counts) != _EXPECTED_SPLIT_FRAMES:
        _fail("dataset_derived_split_frame_mismatch", repr(dict(frame_counts)))
    episode_counts = {split: len(episodes_by_split[split]) for split in _SPLITS}
    if episode_counts != _EXPECTED_SPLIT_EPISODES:
        _fail("dataset_derived_split_episode_mismatch", repr(episode_counts))
    expected_seed_splits = {
        seed: split for split in _SPLITS for seed in split_seeds[split]
    }
    if derived_seed_splits != expected_seed_splits:
        _fail("dataset_manifest_frame_seed_split_mismatch")
    split_hash = _compute_dataset_split_hash(
        derived_seed_splits,
        (
            (scenario, seed, episode, split)
            for (scenario, seed, episode), split in derived_episode_splits.items()
        ),
    )
    _validate_dataset_split_hash(manifest.get("split_hash"), split_hash)
    if split_hash != _EXPECTED_DATASET_SPLIT_SHA256:
        _fail("dataset_frozen_split_hash_mismatch", split_hash)
    dataset_tree = _named_hash_tree(
        {
            "dataset_manifest.json": dataset_hashes["dataset_manifest.json"],
            "frames.jsonl": dataset_hashes["frames.jsonl"],
        }
    )
    return {
        "manifest": manifest,
        "manifest_sha256": dataset_hashes["dataset_manifest.json"],
        "frames_sha256": dataset_hashes["frames.jsonl"],
        "dataset_tree_sha256": dataset_tree,
        "episode_count": sum(episode_counts.values()),
        "frame_count": len(frames_by_key),
        "split_episode_counts": episode_counts,
        "split_frame_counts": dict(frame_counts),
        "seed_values": sorted(_EXPECTED_EVALUATION_SEEDS),
        "split_seed_values": {split: sorted(split_seeds[split]) for split in _SPLITS},
        "split_hash": split_hash,
        "split_hash_verified": True,
        "training_seed_overlap_count": 0,
        "formal_seed_overlap_count": 0,
        "forbidden_identity_field_count": forbidden_count,
        "finite_failure_count": 0,
        "all_values_finite": True,
        "frames_by_key": frames_by_key,
    }


def _audit_evaluation_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    csv_path: Path,
    contract: Mapping[str, Any],
    dataset_frames: Mapping[tuple[str, int, str, int, float, str], _DatasetFrameInfo],
    cell_by_seed: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    if len(rows) != 292:
        _fail("evaluation_frame_count_mismatch", str(len(rows)))
    csv_audit = _audit_frame_csv(csv_path, rows)
    seen: set[tuple[str, int, str, int, float, str]] = set()
    grouped: dict[str, list[Mapping[str, Any]]] = {split: [] for split in _SPLITS}
    independent_safety: list[Mapping[str, _IndependentEdgeSafety]] = []
    grouped_safety: dict[str, list[Mapping[str, _IndependentEdgeSafety]]] = {
        split: [] for split in _SPLITS
    }
    for index, row in enumerate(rows, start=1):
        _assert_finite(row, f"evaluation_row:{index}")
        _assert_evaluation_identity_free(row, row_number=index)
        if row.get("schema_version") != "d3_a1_source_independent_evaluation_frame_v2":
            _fail("evaluation_frame_schema_mismatch", str(index))
        if row.get("mode") != _EXPECTED_MODE or row.get("evaluation_group") != _EXPECTED_MODE:
            _fail("evaluation_frame_mode_mismatch", str(index))
        split = str(row.get("source_split"))
        if split not in _SPLITS or row.get("evaluation_subgroup") != f"{_EXPECTED_MODE}/{split}":
            _fail("evaluation_frame_subgroup_mismatch", str(index))
        key = (
            str(row.get("episode")),
            _integer(row.get("seed"), "evaluation_seed"),
            str(row.get("scenario_version")),
            _integer(row.get("frame_index"), "evaluation_frame_index"),
            _finite_float(row.get("timestamp_s"), "evaluation_timestamp"),
            split,
        )
        if key in seen or key not in dataset_frames:
            _fail("evaluation_dataset_frame_binding_mismatch", repr(key))
        seen.add(key)
        dataset = dataset_frames[key]
        cardinality = _mapping(row.get("input_cardinality"), "input_cardinality")
        cell = cell_by_seed[key[1]]
        expected_cardinality = {
            "configured_scenario_target_count": cell["configured_scenario_target_count"],
            "observed_anonymous_target_count": dataset.target_count,
            "configured_resource_count": cell["resource_count"],
            "observed_anonymous_resource_count": dataset.resource_count,
            "rule_cost_matrix_shape": list(dataset.rule_shape),
            "action_mask_shape": list(dataset.action_shape),
            "candidate_edge_count": dataset.candidate_edge_count,
            "target_demand_slot_count": dataset.demand_slot_count,
        }
        if cardinality != expected_cardinality:
            _fail("evaluation_input_cardinality_mismatch", repr(key))
        if row.get("input_finite") is not True:
            _fail("evaluation_nonfinite_input", repr(key))
        if _integer(row.get("online_truth_use_count"), "evaluation_truth_use") != 0:
            _fail("evaluation_online_truth_use_nonzero", repr(key))
        permissions = _mapping(row.get("permissions"), "evaluation_permissions")
        _require_all_permissions_false(permissions, f"evaluation_row:{index}")
        if permissions != contract.get("permissions"):
            _fail("evaluation_permission_contract_mismatch", str(index))
        reasons = tuple(str(value) for value in _sequence(row.get("rejection_reasons"), "rejection_reasons"))
        if len(reasons) != len(set(reasons)) or row.get("rejection_reason_count") != len(reasons):
            _fail("evaluation_rejection_reason_count_mismatch", str(index))
        if bool(row.get("rejected")) != bool(reasons):
            _fail("evaluation_rejected_flag_mismatch", str(index))
        if bool(row.get("ood")) and "feature_ood" not in reasons:
            _fail("evaluation_ood_reason_missing", str(index))
        model_outputs = _mapping(row.get("model_outputs"), "model_outputs")
        if model_outputs.get("bounded_cost_correction_only") is not True:
            _fail("evaluation_model_output_scope_mismatch", str(index))
        _validate_rule_cost_matrix_hash(
            row.get("r0_rule_cost_matrix_sha256"),
            dataset=dataset,
            label=f"row={index}",
        )
        row_safety: dict[str, _IndependentEdgeSafety] = {}
        parsed_edges: dict[str, tuple[tuple[int, int], ...]] = {}
        for label in ("r0", "candidate", "effective"):
            payload = _mapping(row.get(label), label)
            edges, safety = _validate_selected_edge_safety_claims(
                payload,
                dataset=dataset,
                label=f"row={index};{label}",
            )
            parsed_edges[label] = edges
            row_safety[label] = safety
        for label in ("candidate", "effective"):
            change_count = len(
                set(parsed_edges[label]).symmetric_difference(
                    set(parsed_edges["r0"])
                )
            )
            claimed_change = _integer(
                _mapping(row.get(label), label).get(
                    "binding_change_count_from_r0"
                ),
                f"{label}.binding_change_count_from_r0",
            )
            if claimed_change != change_count:
                _fail(
                    "evaluation_binding_change_claim_mismatch",
                    f"row={index};group={label};"
                    f"claimed={claimed_change};derived={change_count}",
                )
        independent_safety.append(row_safety)
        grouped_safety[split].append(row_safety)
        grouped[split].append(row)
    if seen != set(dataset_frames):
        _fail("evaluation_dataset_coverage_mismatch")
    overall = _recompute_metrics(rows, independent_safety=independent_safety)
    subgroup = {
        split: _recompute_metrics(
            grouped[split],
            independent_safety=grouped_safety[split],
        )
        for split in _SPLITS
    }
    return {
        "overall_metrics": overall,
        "source_subgroup_metrics": subgroup,
        "csv_jsonl_closure": csv_audit,
        "independent_selected_edge_safety": _summarize_independent_safety(
            independent_safety
        ),
        "all_values_finite": True,
        "dataset_frame_binding_count": len(seen),
        "dataset_frame_binding_mismatch_count": 0,
        "evaluation_forbidden_identity_field_count": 0,
        "rule_cost_matrix_hash_match_count": len(seen),
        "rule_cost_matrix_hash_mismatch_count": 0,
    }


def _audit_frame_csv(
    path: Path,
    jsonl_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Parse the fixed CSV transport and close every value to JSONL."""

    source = _resolve_regular_file(path, "per_frame_evaluation_csv")
    try:
        with source.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream)
            try:
                header = tuple(next(reader))
            except StopIteration:
                _fail("evaluation_csv_header_missing")
            csv_rows = tuple(tuple(value for value in row) for row in reader)
    except (OSError, UnicodeError, csv.Error) as error:
        _fail("evaluation_csv_read_failed", str(error))
    if header != _CSV_FIELDS:
        _fail(
            "evaluation_csv_header_mismatch",
            f"expected={_CSV_FIELDS};actual={header}",
        )
    if len(csv_rows) != len(jsonl_rows):
        _fail(
            "evaluation_csv_row_count_mismatch",
            f"csv={len(csv_rows)};jsonl={len(jsonl_rows)}",
        )
    for index, (values, row) in enumerate(zip(csv_rows, jsonl_rows), start=1):
        if len(values) != len(_CSV_FIELDS):
            _fail(
                "evaluation_csv_column_count_mismatch",
                f"row={index};expected={len(_CSV_FIELDS)};actual={len(values)}",
            )
        csv_row = dict(zip(_CSV_FIELDS, values))
        teacher = _mapping(row.get("teacher"), "teacher")
        r0 = _mapping(row.get("r0"), "r0")
        candidate = _mapping(row.get("candidate"), "candidate")
        effective = _mapping(row.get("effective"), "effective")
        r0_edges = _parse_selected_edges(r0.get("selected_edges"), "r0_edges")
        candidate_edges = _parse_selected_edges(
            candidate.get("selected_edges"),
            "candidate_edges",
        )
        effective_edges = _parse_selected_edges(
            effective.get("selected_edges"),
            "effective_edges",
        )
        teacher_edges = _parse_selected_edges(
            teacher.get("selected_edges"),
            "teacher_edges",
        )
        opportunity = _strict_bool(
            teacher.get("opportunity"),
            "teacher.opportunity",
        )
        rejected = _strict_bool(row.get("rejected"), "rejected")
        ood = _strict_bool(row.get("ood"), "ood")
        exact_binding = effective_edges == r0_edges
        exact_matrix = (
            str(effective.get("cost_matrix_sha256", ""))
            == str(row.get("r0_rule_cost_matrix_sha256", ""))
        )
        reasons = tuple(
            str(value)
            for value in _sequence(
                row.get("rejection_reasons"),
                "rejection_reasons",
            )
        )
        expected_scalars: dict[str, Any] = {
            "evaluation_group": str(row.get("evaluation_group")),
            "evaluation_subgroup": str(row.get("evaluation_subgroup")),
            "source_split": str(row.get("source_split")),
            "scenario_version": str(row.get("scenario_version")),
            "seed": _integer(row.get("seed"), "seed"),
            "episode": str(row.get("episode")),
            "frame_index": _integer(row.get("frame_index"), "frame_index"),
            "timestamp_s": _finite_float(row.get("timestamp_s"), "timestamp_s"),
            "teacher_opportunity": int(opportunity),
            "candidate_binding_change_count": len(
                set(candidate_edges).symmetric_difference(set(r0_edges))
            ),
            "effective_binding_change_count": len(
                set(effective_edges).symmetric_difference(set(r0_edges))
            ),
            "positive_teacher_exact_match": int(
                opportunity and effective_edges == teacher_edges
            ),
            "negative_exact_r0": int(not opportunity and exact_binding),
            "ood": int(ood),
            "rejected": int(rejected),
            "rejection_reasons": "|".join(reasons),
            "fallback_exact_r0_matrix": int(rejected and exact_matrix),
            "fallback_exact_r0_binding": int(rejected and exact_binding),
        }
        csv_scalars: dict[str, Any] = {
            "evaluation_group": csv_row["evaluation_group"],
            "evaluation_subgroup": csv_row["evaluation_subgroup"],
            "source_split": csv_row["source_split"],
            "scenario_version": csv_row["scenario_version"],
            "seed": _csv_integer(csv_row["seed"], f"row={index};seed"),
            "episode": csv_row["episode"],
            "frame_index": _csv_integer(
                csv_row["frame_index"],
                f"row={index};frame_index",
            ),
            "timestamp_s": _csv_finite_float(
                csv_row["timestamp_s"],
                f"row={index};timestamp_s",
            ),
            "teacher_opportunity": _csv_flag(
                csv_row["teacher_opportunity"],
                f"row={index};teacher_opportunity",
            ),
            "candidate_binding_change_count": _csv_integer(
                csv_row["candidate_binding_change_count"],
                f"row={index};candidate_binding_change_count",
            ),
            "effective_binding_change_count": _csv_integer(
                csv_row["effective_binding_change_count"],
                f"row={index};effective_binding_change_count",
            ),
            "positive_teacher_exact_match": _csv_flag(
                csv_row["positive_teacher_exact_match"],
                f"row={index};positive_teacher_exact_match",
            ),
            "negative_exact_r0": _csv_flag(
                csv_row["negative_exact_r0"],
                f"row={index};negative_exact_r0",
            ),
            "ood": _csv_flag(csv_row["ood"], f"row={index};ood"),
            "rejected": _csv_flag(
                csv_row["rejected"],
                f"row={index};rejected",
            ),
            "rejection_reasons": csv_row["rejection_reasons"],
            "fallback_exact_r0_matrix": _csv_flag(
                csv_row["fallback_exact_r0_matrix"],
                f"row={index};fallback_exact_r0_matrix",
            ),
            "fallback_exact_r0_binding": _csv_flag(
                csv_row["fallback_exact_r0_binding"],
                f"row={index};fallback_exact_r0_binding",
            ),
        }
        for field, expected in expected_scalars.items():
            if csv_scalars[field] != expected:
                _fail(
                    "evaluation_csv_jsonl_mismatch",
                    f"row={index};field={field};"
                    f"csv={csv_scalars[field]!r};jsonl={expected!r}",
                )
        csv_edge_values = {
            "r0_selected_edges": _parse_csv_selected_edges(
                csv_row["r0_selected_edges"],
                f"row={index};r0_selected_edges",
            ),
            "candidate_selected_edges": _parse_csv_selected_edges(
                csv_row["candidate_selected_edges"],
                f"row={index};candidate_selected_edges",
            ),
            "effective_selected_edges": _parse_csv_selected_edges(
                csv_row["effective_selected_edges"],
                f"row={index};effective_selected_edges",
            ),
        }
        expected_edges = {
            "r0_selected_edges": r0_edges,
            "candidate_selected_edges": candidate_edges,
            "effective_selected_edges": effective_edges,
        }
        for field, expected in expected_edges.items():
            if csv_edge_values[field] != expected:
                _fail(
                    "evaluation_csv_jsonl_mismatch",
                    f"row={index};field={field}",
                )
    return {
        "fixed_column_count": len(_CSV_FIELDS),
        "row_count": len(csv_rows),
        "jsonl_row_count": len(jsonl_rows),
        "matched_row_count": len(csv_rows),
        "mismatch_count": 0,
        "header_exact": True,
    }


def _parse_selected_edges(
    value: Any,
    label: str,
) -> tuple[tuple[int, int], ...]:
    edges: list[tuple[int, int]] = []
    for index, item in enumerate(_sequence(value, label)):
        pair = _sequence(item, f"{label}[{index}]")
        if len(pair) != 2:
            _fail("selected_edge_pair_invalid", f"{label}[{index}]")
        edges.append(
            (
                _integer(pair[0], f"{label}[{index}].target_index"),
                _integer(pair[1], f"{label}[{index}].resource_index"),
            )
        )
    return tuple(edges)


def _parse_csv_selected_edges(
    value: str,
    label: str,
) -> tuple[tuple[int, int], ...]:
    try:
        parsed = json.loads(
            value,
            parse_constant=lambda token: _reject_json_constant(label, token),
        )
    except json.JSONDecodeError as error:
        _fail("evaluation_csv_edge_json_invalid", f"{label}:{error}")
    return _parse_selected_edges(parsed, label)


def _validate_selected_edge_safety_claims(
    payload: Mapping[str, Any],
    *,
    dataset: _DatasetFrameInfo,
    label: str,
) -> tuple[tuple[tuple[int, int], ...], _IndependentEdgeSafety]:
    edges = _parse_selected_edges(payload.get("selected_edges"), label)
    safety = _recompute_selected_edge_safety(edges, dataset=dataset)
    if safety.edge_index_out_of_range_count:
        _fail(
            "evaluation_edge_index_out_of_range",
            f"{label};count={safety.edge_index_out_of_range_count}",
        )
    for field in (
        "duplicate_resource_count",
        "hard_edge_violation_count",
        "m_to_n_atomicity_violation_count",
    ):
        claimed = _integer(payload.get(field), f"{label};{field}")
        derived = int(getattr(safety, field))
        if claimed != derived:
            _fail(
                "evaluation_safety_claim_mismatch",
                f"{label};field={field};claimed={claimed};derived={derived}",
            )
    return edges, safety


def _recompute_selected_edge_safety(
    edges: Sequence[tuple[int, int]],
    *,
    dataset: _DatasetFrameInfo,
) -> _IndependentEdgeSafety:
    resource_use: Counter[int] = Counter()
    target_use: Counter[int] = Counter()
    out_of_range = 0
    hard_edge = 0
    for target_index, resource_index in edges:
        if not (
            0 <= target_index < dataset.target_count
            and 0 <= resource_index < dataset.resource_count
        ):
            out_of_range += 1
            continue
        resource_use[resource_index] += 1
        target_use[target_index] += 1
        if not dataset.action_mask[target_index][resource_index]:
            hard_edge += 1
    capacity_excess = sum(
        max(0, resource_use[index] - dataset.resource_capacities[index])
        for index in range(dataset.resource_count)
    )
    atomicity = sum(
        target_use[index] not in (0, dataset.target_demand_slots[index])
        for index in range(dataset.target_count)
    )
    return _IndependentEdgeSafety(
        edge_count=len(edges),
        edge_index_out_of_range_count=out_of_range,
        duplicate_resource_count=capacity_excess,
        hard_edge_violation_count=hard_edge,
        m_to_n_atomicity_violation_count=atomicity,
    )


def _validate_rule_cost_matrix_hash(
    claimed_value: Any,
    *,
    dataset: _DatasetFrameInfo,
    label: str,
) -> None:
    claimed = str(claimed_value or "")
    if _HEX_SHA256.fullmatch(claimed) is None:
        _fail("evaluation_rule_cost_matrix_sha256_invalid", label)
    if claimed != dataset.rule_cost_matrix_sha256:
        _fail(
            "evaluation_rule_cost_matrix_sha256_mismatch",
            f"{label};claimed={claimed};derived={dataset.rule_cost_matrix_sha256}",
        )


def _summarize_independent_safety(
    rows: Sequence[Mapping[str, _IndependentEdgeSafety]],
) -> dict[str, Any]:
    groups: dict[str, dict[str, int]] = {}
    for label in ("r0", "candidate", "effective"):
        values = [row[label] for row in rows]
        groups[label] = {
            "edge_count": sum(value.edge_count for value in values),
            "edge_index_out_of_range_count": sum(
                value.edge_index_out_of_range_count for value in values
            ),
            "duplicate_resource_count": sum(
                value.duplicate_resource_count for value in values
            ),
            "hard_edge_violation_count": sum(
                value.hard_edge_violation_count for value in values
            ),
            "m_to_n_atomicity_violation_count": sum(
                value.m_to_n_atomicity_violation_count for value in values
            ),
        }
    return {
        "edge_order": "target_index_resource_index",
        "dataset_basis": (
            "action_mask_target_by_resource,target_demand_slots,"
            "anonymous_resources.assignment_capacity"
        ),
        "frame_count": len(rows),
        "group_frame_count": len(rows) * 3,
        "groups": groups,
        "self_report_mismatch_count": 0,
        "effective_machine_gate_source": "independent_dataset_recomputation",
    }


def _recompute_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    independent_safety: Sequence[
        Mapping[str, _IndependentEdgeSafety]
    ] | None = None,
) -> dict[str, Any]:
    if independent_safety is not None and len(independent_safety) != len(rows):
        _fail("independent_safety_row_count_mismatch")
    positive = 0
    negative = 0
    safe_change = 0
    teacher_exact = 0
    negative_exact = 0
    nonzero_correction = 0
    rejected = 0
    fallback_matrix = 0
    fallback_binding = 0
    ood = 0
    duplicate_resource = 0
    hard_edge = 0
    atomicity = 0
    version = 0
    rule_mutation = 0
    assignment_output = 0
    plan_output = 0
    runtime_output = 0
    rejection_reasons: Counter[str] = Counter()
    rejection_scenarios: Counter[str] = Counter()
    ood_reasons: Counter[str] = Counter()
    ood_scenarios: Counter[str] = Counter()
    for index, row in enumerate(rows, start=1):
        teacher = _mapping(row.get("teacher"), "teacher")
        r0 = _mapping(row.get("r0"), "r0")
        candidate = _mapping(row.get("candidate"), "candidate")
        effective = _mapping(row.get("effective"), "effective")
        model = _mapping(row.get("model_outputs"), "model_outputs")
        opportunity = teacher.get("opportunity") is True
        if opportunity:
            positive += 1
        else:
            negative += 1
        r0_edges = r0.get("selected_edges")
        effective_edges = effective.get("selected_edges")
        teacher_edges = teacher.get("selected_edges")
        changed = effective_edges != r0_edges
        exact_binding = effective_edges == r0_edges
        if bool(effective.get("exact_r0_binding")) != exact_binding:
            _fail("evaluation_exact_r0_binding_flag_mismatch", str(index))
        exact_matrix = effective.get("cost_matrix_sha256") == row.get("r0_rule_cost_matrix_sha256")
        if bool(effective.get("exact_r0_matrix")) != exact_matrix:
            _fail("evaluation_exact_r0_matrix_flag_mismatch", str(index))
        if opportunity and changed:
            safe_change += 1
        if opportunity and effective_edges == teacher_edges:
            teacher_exact += 1
        if not opportunity and exact_binding:
            negative_exact += 1
        if _finite_float(candidate.get("maximum_abs_cost_correction"), "maximum_abs_cost_correction") > 0.0:
            nonzero_correction += 1
        is_rejected = row.get("rejected") is True
        if is_rejected:
            rejected += 1
            fallback_matrix += int(exact_matrix)
            fallback_binding += int(exact_binding)
            rejection_scenarios[str(row.get("scenario_version"))] += 1
            rejection_reasons.update(str(value) for value in row.get("rejection_reasons", ()))
        is_ood = row.get("ood") is True
        if is_ood:
            ood += 1
            ood_scenarios[str(row.get("scenario_version"))] += 1
            ood_reasons["feature_ood"] += 1
        if independent_safety is None:
            for label, payload in (
                ("r0", r0),
                ("candidate", candidate),
                ("effective", effective),
            ):
                for field in (
                    "duplicate_resource_count",
                    "hard_edge_violation_count",
                    "m_to_n_atomicity_violation_count",
                ):
                    value = _integer(payload.get(field), f"{label}.{field}")
                    if value != 0:
                        _fail(
                            "evaluation_safety_violation",
                            f"row={index};{label}.{field}={value}",
                        )
            effective_safety = _IndependentEdgeSafety(
                edge_count=len(_sequence(effective_edges, "effective_edges")),
                edge_index_out_of_range_count=0,
                duplicate_resource_count=_integer(
                    effective.get("duplicate_resource_count"),
                    "duplicate_resource_count",
                ),
                hard_edge_violation_count=_integer(
                    effective.get("hard_edge_violation_count"),
                    "hard_edge_violation_count",
                ),
                m_to_n_atomicity_violation_count=_integer(
                    effective.get("m_to_n_atomicity_violation_count"),
                    "m_to_n_atomicity_violation_count",
                ),
            )
        else:
            effective_safety = independent_safety[index - 1]["effective"]
        duplicate_resource += effective_safety.duplicate_resource_count
        hard_edge += effective_safety.hard_edge_violation_count
        atomicity += effective_safety.m_to_n_atomicity_violation_count
        version += _integer(model.get("version_output_count"), "version_output_count")
        rule_mutation += int(row.get("r0_rule_matrix_mutated") is True)
        assignment_output += _integer(model.get("assignment_output_count"), "assignment_output_count")
        plan_output += _integer(model.get("plan_output_count"), "plan_output_count")
        runtime_output += _integer(model.get("runtime_output_count"), "runtime_output_count")
    positive_safe = _rate(safe_change, positive)
    positive_teacher = _rate(teacher_exact, positive)
    negative_r0 = _rate(negative_exact, negative)
    return {
        "frame_count": len(rows),
        "positive_frame_count": positive,
        "negative_frame_count": negative,
        "nonzero_cost_correction_frame_count": nonzero_correction,
        "safe_binding_change_frame_count": safe_change,
        "projection_rejection_count": rejected,
        "fallback_frame_count": rejected,
        "fallback_exact_r0_matrix_count": fallback_matrix,
        "fallback_exact_r0_binding_count": fallback_binding,
        "duplicate_resource_count": duplicate_resource,
        "hard_edge_violation_count": hard_edge,
        "m_to_n_atomicity_violation_count": atomicity,
        "version_violation_count": version,
        "r0_rule_matrix_mutation_count": rule_mutation,
        "model_assignment_output_count": assignment_output,
        "model_plan_output_count": plan_output,
        "model_runtime_output_count": runtime_output,
        "positive_safe_binding_change": positive_safe,
        "positive_teacher_exact_match": positive_teacher,
        "negative_exact_r0": negative_r0,
        "rejection_reason_counts": dict(sorted(rejection_reasons.items())),
        "rejection_scenario_distribution": dict(sorted(rejection_scenarios.items())),
        "rejection_distribution_complete": sum(rejection_scenarios.values()) == rejected,
        "ood_frame_count": ood,
        "ood_reason_counts": dict(sorted(ood_reasons.items())),
        "ood_scenario_distribution": dict(sorted(ood_scenarios.items())),
        "ood_distribution_complete": sum(ood_scenarios.values()) == ood,
    }


def _recompute_preregistered_gate(
    *,
    contract: Mapping[str, Any],
    metrics: Mapping[str, Any],
    generation: Mapping[str, Any],
    dataset: Mapping[str, Any],
    bundle_hashes: Mapping[str, Any],
    all_inputs_finite: bool,
) -> dict[str, Any]:
    thresholds = _mapping(contract.get("thresholds"), "thresholds")
    safe = _mapping(metrics.get("positive_safe_binding_change"), "positive_safe_binding_change")
    teacher = _mapping(metrics.get("positive_teacher_exact_match"), "positive_teacher_exact_match")
    negative = _mapping(metrics.get("negative_exact_r0"), "negative_exact_r0")
    checks = {
        "input_frame_count_matches_manifest": metrics["frame_count"] == dataset["frame_count"],
        "all_input_values_finite": bool(all_inputs_finite),
        "source_seed_universe_exact": dataset["seed_values"] == list(range(20000, 20100)),
        "source_split_seed_counts_exact": {
            key: len(dataset["split_seed_values"][key]) for key in _SPLITS
        }
        == _EXPECTED_SPLIT_EPISODES,
        "all_source_subgroups_present": all(dataset["split_frame_counts"][key] > 0 for key in _SPLITS),
        "training_seed_overlap_zero": dataset["training_seed_overlap_count"] == 0,
        "formal_holdout_seed_overlap_zero": dataset["formal_seed_overlap_count"] == 0,
        "generation_complete_and_finite": generation["episode_count"] == 100 and generation["finite_failure_count"] == 0,
        "online_truth_use_zero": generation["online_truth_use_count"] == 0 and dataset["forbidden_identity_field_count"] == 0,
        "bundle_manifest_tree_state_exact": bundle_hashes["tree_sha256"] == _EXPECTED_BUNDLE_TREE_SHA256,
        "model_weights_unchanged": bundle_hashes["file_hashes"]["state_dict.json"] == _EXPECTED_BUNDLE_STATE_SHA256,
        "normalization_not_refit": contract["permissions"]["normalization_refit"] is False,
        "positive_denominator_nonzero": safe["denominator"] > 0,
        "negative_denominator_nonzero": negative["denominator"] > 0,
        "positive_safe_binding_change_passed": safe["numerator"] >= thresholds["minimum_positive_safe_binding_change_count"] and safe["rate"] >= thresholds["minimum_positive_safe_binding_change_rate"],
        "positive_teacher_exact_match_passed": teacher["numerator"] >= thresholds["minimum_positive_teacher_exact_match_count"] and teacher["rate"] >= thresholds["minimum_positive_teacher_exact_match_rate"],
        "negative_exact_r0_passed": negative["rate"] >= thresholds["minimum_negative_exact_r0_rate"],
        "fallback_matrix_exact_r0": metrics["fallback_exact_r0_matrix_count"] == metrics["fallback_frame_count"],
        "fallback_binding_exact_r0": metrics["fallback_exact_r0_binding_count"] == metrics["fallback_frame_count"],
        "zero_duplicate_resource": metrics["duplicate_resource_count"] == 0,
        "zero_hard_edge_violation": metrics["hard_edge_violation_count"] == 0,
        "zero_m_to_n_atomicity_violation": metrics["m_to_n_atomicity_violation_count"] == 0,
        "zero_version_violation": metrics["version_violation_count"] == 0,
        "zero_rule_matrix_mutation": metrics["r0_rule_matrix_mutation_count"] == 0,
        "zero_model_assignment_output": metrics["model_assignment_output_count"] == 0,
        "zero_model_plan_output": metrics["model_plan_output_count"] == 0,
        "zero_model_runtime_output": metrics["model_runtime_output_count"] == 0,
        "rejection_distribution_complete": metrics["rejection_distribution_complete"] is True,
        "ood_distribution_complete": metrics["ood_distribution_complete"] is True,
        "all_permissions_false": all(value is False for value in contract["permissions"].values()),
    }
    return {"checks": checks, "passed": all(checks.values())}


def _reconcile_d3_claims(
    aggregate: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    contract_sha256: str,
    bundle_hashes: Mapping[str, Any],
    frozen_source: Mapping[str, Any],
    generation: Mapping[str, Any],
    dataset: Mapping[str, Any],
    recomputation: Mapping[str, Any],
    gate: Mapping[str, Any],
) -> dict[str, Any]:
    if aggregate.get("schema_version") != contract["output_identity"]["aggregate_schema_version"]:
        _fail("aggregate_schema_mismatch")
    if aggregate.get("contract_id") != contract["contract_id"]:
        _fail("aggregate_contract_id_mismatch")
    if aggregate.get("contract_sha256") != contract_sha256:
        _fail("aggregate_contract_sha256_mismatch")
    if aggregate.get("mode") != _EXPECTED_MODE:
        _fail("aggregate_mode_mismatch")
    if aggregate.get("output_identity") != contract["output_identity"]:
        _fail("aggregate_output_identity_mismatch")
    if aggregate.get("thresholds") != contract["thresholds"]:
        _fail("aggregate_threshold_claim_mismatch")
    permissions = _mapping(aggregate.get("permissions"), "aggregate_permissions")
    _require_all_permissions_false(permissions, "aggregate")
    if permissions != contract["permissions"]:
        _fail("aggregate_permission_claim_mismatch")
    if aggregate.get("runtime_adoption_granted") is not False or aggregate.get("formal_admission_granted") is not False:
        _fail("aggregate_authority_claim_forbidden")
    _reconcile_metric_claims(aggregate, recomputation)
    data = _mapping(aggregate.get("data_summary"), "aggregate_data_summary")
    if data.get("dataset_manifest") != dataset["manifest"]:
        _fail("aggregate_dataset_manifest_claim_mismatch")
    expected_data = {
        "dataset_frames_sha256": dataset["frames_sha256"],
        "dataset_manifest_sha256": dataset["manifest_sha256"],
        "dataset_schema_version": dataset["manifest"]["schema_version"],
        "seed_values": dataset["seed_values"],
        "source_split_seed_values": dataset["split_seed_values"],
        "split_policy_version": dataset["manifest"]["split_policy_version"],
        "training_seed_overlap_values": [],
        "formal_holdout_seed_overlap_values": [],
    }
    for name, expected in expected_data.items():
        if data.get(name) != expected:
            _fail("aggregate_data_claim_mismatch", name)
    truth = _mapping(data.get("truth_use_audit"), "truth_use_audit")
    expected_truth = {
        "dataset_frames_sha256": dataset["frames_sha256"],
        "dataset_manifest_sha256": dataset["manifest_sha256"],
        "dataset_truth_field_count": 0,
        "episode_progress_sha256": generation["file_hashes"]["episode_progress.jsonl"],
        "generation_cell_count": 100,
        "generation_checkpoint_sha256": generation["file_hashes"]["generation_checkpoint.json"],
        "generation_finite_failure_count": 0,
        "generation_online_truth_use_count": 0,
        "generation_plan_sha256": generation["file_hashes"]["generation_plan.json"],
        "generation_repository_dirty": False,
        "generation_schedule_sha256": _EXPECTED_SCHEDULE_SHA256,
        "generation_summary_sha256": generation["file_hashes"]["generation_summary.json"],
        "truth_audit_basis": "generation_progress_plus_d3_identity_free_schema_parser",
    }
    if truth != expected_truth:
        _fail("aggregate_truth_audit_claim_mismatch")
    model = _mapping(aggregate.get("model_summary"), "model_summary")
    if (
        model.get("manifest_sha256") != bundle_hashes["file_hashes"]["manifest.json"]
        or model.get("state_dict_sha256") != bundle_hashes["file_hashes"]["state_dict.json"]
        or model.get("tree_sha256") != bundle_hashes["tree_sha256"]
        or model.get("normalization_refit_count") != 0
        or model.get("model_weight_update_count") != 0
    ):
        _fail("aggregate_model_claim_mismatch")
    source = _mapping(aggregate.get("source_summary"), "source_summary")
    if (
        source.get("contract_sha256") != contract_sha256
        or source.get("evaluator_source_tree_sha256") != frozen_source["tree_sha256"]
        or source.get("repository_git_commit")
        != frozen_source["evaluation_repository_git_commit"]
        or source.get("owned_source_dirty") is not False
    ):
        _fail("aggregate_source_claim_mismatch")
    v1_contract = (
        Path(__file__).resolve().parents[2]
        / "d3_assignment_planner/configs/a1_source_independent_evaluation_contract_v1.json"
    )
    if source.get("v1_contract_sha256") != _sha256_file(v1_contract):
        _fail("aggregate_v1_contract_sha256_mismatch")
    formal = _mapping(aggregate.get("formal_holdout"), "formal_holdout")
    if (
        formal.get("read_count") != 0
        or frozenset(formal.get("seed_values", ())) != _EXPECTED_FORMAL_SEEDS
        or formal.get("status") != "not_read_not_evaluated"
    ):
        _fail("aggregate_formal_holdout_claim_mismatch")
    if aggregate.get("machine_gate") != gate["checks"]:
        _fail("aggregate_machine_gate_claim_mismatch")
    if aggregate.get("machine_gate_passed") is not gate["passed"]:
        _fail("aggregate_machine_gate_result_mismatch")
    expected_status = "source_independent_evaluation_v2_gate_passed_not_admitted"
    if aggregate.get("status") != expected_status:
        _fail("aggregate_status_mismatch", str(aggregate.get("status")))
    test_metric = recomputation["source_subgroup_metrics"]["test"]["positive_teacher_exact_match"]
    if test_metric != {
        "available": True,
        "denominator": 25,
        "numerator": 0,
        "rate": 0.0,
        "unavailable_reason": None,
    }:
        _fail("test_subgroup_generalization_fact_mismatch")
    return {
        "aggregate_claims_match_independent_recomputation": True,
        "overall_metric_mismatch_count": 0,
        "subgroup_metric_mismatch_count": 0,
        "permission_claim_mismatch_count": 0,
        "machine_gate_claim_mismatch_count": 0,
    }


def _reconcile_metric_claims(
    aggregate: Mapping[str, Any],
    recomputation: Mapping[str, Any],
) -> None:
    """Reject self-reported counts that differ from frame recomputation."""

    if aggregate.get("overall_metrics") != recomputation.get("overall_metrics"):
        _fail("aggregate_overall_metric_claim_mismatch")
    if aggregate.get("source_subgroup_metrics") != recomputation.get(
        "source_subgroup_metrics"
    ):
        _fail("aggregate_subgroup_metric_claim_mismatch")


def _post_audit_snapshot(
    inputs: D3A1V2ExternalAuditInputs,
    pre_snapshot: Mapping[str, str],
) -> dict[str, str]:
    paths: dict[str, Path] = {"contract": inputs.contract_path}
    for name in _EXPECTED_RESULT_FILES:
        paths[f"result/{name}"] = inputs.result_dir / name
    for name in _EXPECTED_DATASET_FILES:
        paths[f"dataset/{name}"] = inputs.dataset_dir / name
    for name in (
        "generation_plan.json",
        "generation_summary.json",
        "generation_checkpoint.json",
        "episode_progress.jsonl",
        "training_seed_registry.json",
    ):
        paths[f"generation/{name}"] = inputs.generation_root / name
    for name in _EXPECTED_BUNDLE_FILES:
        paths[f"bundle/{name}"] = inputs.bundle_dir / name
    return {
        name: _sha256_file(_resolve_regular_file(paths[name], name))
        for name in pre_snapshot
    }


def _find_forbidden_identity_keys(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            text = str(key)
            normalized = "".join(character for character in text.lower() if character.isalnum())
            forbidden = (
                "truth" in normalized
                or normalized in _FORBIDDEN_IDENTITY_KEYS
                or (("actor" in normalized or "object" in normalized) and ("id" in normalized or "name" in normalized))
            )
            child_path = f"{path}.{text}"
            if forbidden:
                findings.append(child_path)
            findings.extend(_find_forbidden_identity_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_find_forbidden_identity_keys(child, f"{path}[{index}]"))
    return findings


def _evaluation_forbidden_identity_paths(value: Mapping[str, Any]) -> list[str]:
    return [
        path
        for path in _find_forbidden_identity_keys(value)
        if path != "$.online_truth_use_count"
    ]


def _assert_evaluation_identity_free(
    value: Mapping[str, Any],
    *,
    row_number: int,
) -> None:
    forbidden_paths = _evaluation_forbidden_identity_paths(value)
    if forbidden_paths:
        _fail(
            "evaluation_forbidden_identity_field",
            f"row={row_number};paths={','.join(forbidden_paths[:20])}",
        )


def _compute_dataset_split_hash(
    split_by_seed: Mapping[int, str],
    episode_inventory: Iterable[tuple[str, int, str, str]],
) -> str:
    payload = {
        "dataset_schema_version": "d3_learning_dataset_v2",
        "split_policy_version": "d3_numeric_seed_atomic_split_v2",
        "seed_identity_scope": "numeric_seed_global_across_scenarios",
        "seed_assignments": [
            [int(seed), str(split)]
            for seed, split in sorted(split_by_seed.items())
        ],
        "episode_assignments": [
            [str(scenario), int(seed), str(episode), str(split)]
            for scenario, seed, episode, split in sorted(set(episode_inventory))
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return sha256(encoded).hexdigest()


def _validate_dataset_split_hash(claimed_value: Any, derived_value: str) -> None:
    claimed = str(claimed_value or "")
    if _HEX_SHA256.fullmatch(claimed) is None:
        _fail("dataset_split_hash_invalid", claimed)
    if claimed != derived_value:
        _fail(
            "dataset_split_hash_mismatch",
            f"manifest={claimed};derived={derived_value}",
        )


def _float64_matrix_sha256(value: Any) -> str:
    rows = _sequence(value, "float64_matrix")
    shape = _matrix_shape(rows, "float64_matrix")
    digest = sha256()
    metadata = json.dumps(
        {"dtype": "<f8", "shape": list(shape)},
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    digest.update(metadata)
    digest.update(b"\0")
    for row_index, raw_row in enumerate(rows):
        row = _sequence(raw_row, f"float64_matrix[{row_index}]")
        finite = tuple(
            _finite_float(item, f"float64_matrix[{row_index}]")
            for item in row
        )
        if finite:
            digest.update(struct.pack(f"<{len(finite)}d", *finite))
    return digest.hexdigest()


def _strict_boolean_matrix(value: Any, label: str) -> tuple[tuple[bool, ...], ...]:
    rows: list[tuple[bool, ...]] = []
    for row_index, raw_row in enumerate(_sequence(value, label)):
        row: list[bool] = []
        for column_index, item in enumerate(
            _sequence(raw_row, f"{label}[{row_index}]")
        ):
            row.append(
                _strict_bool(
                    item,
                    f"{label}[{row_index}][{column_index}]",
                )
            )
        rows.append(tuple(row))
    return tuple(rows)


def _strict_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        _fail("boolean_required", f"{label}:{value!r}")
    return value


def _csv_integer(value: str, label: str) -> int:
    if re.fullmatch(r"0|-?[1-9][0-9]*", value) is None:
        _fail("evaluation_csv_integer_invalid", f"{label}:{value!r}")
    return int(value)


def _csv_flag(value: str, label: str) -> int:
    if value not in {"0", "1"}:
        _fail("evaluation_csv_flag_invalid", f"{label}:{value!r}")
    return int(value)


def _csv_finite_float(value: str, label: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        _fail("evaluation_csv_float_invalid", f"{label}:{value!r}")
    if not math.isfinite(parsed):
        _fail("evaluation_csv_float_invalid", f"{label}:{value!r}")
    return parsed


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "available": denominator > 0,
        "denominator": denominator,
        "numerator": numerator,
        "rate": (numerator / denominator) if denominator > 0 else None,
        "unavailable_reason": None if denominator > 0 else "zero_denominator",
    }


def _parse_checksums(path: Path, expected_files: Iterable[str]) -> dict[str, str]:
    expected = frozenset(str(name) for name in expected_files)
    parsed: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="ascii").splitlines(), start=1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", raw)
        if match is None:
            _fail("checksum_line_invalid", f"{path}:{line_number}")
        digest, name = match.groups()
        if name in parsed:
            _fail("checksum_duplicate_entry", name)
        parsed[name] = digest
    if set(parsed) != expected:
        _fail(
            "checksum_coverage_mismatch",
            f"missing={sorted(expected - set(parsed))};extra={sorted(set(parsed) - expected)}",
        )
    return parsed


def _named_hash_tree(hashes: Mapping[str, str]) -> str:
    for digest in hashes.values():
        if _HEX_SHA256.fullmatch(str(digest)) is None:
            _fail("invalid_tree_member_sha256", str(digest))
    payload = "".join(f"{name}:{hashes[name]}\n" for name in sorted(hashes))
    return sha256(payload.encode("ascii")).hexdigest()


def _content_sha256(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("content_sha256", None)
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: _reject_json_constant(label, token),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _fail("json_read_failed", f"{label}:{error}")
    if not isinstance(value, dict):
        _fail("json_object_required", label)
    return value


def _iter_jsonl_objects(path: Path, label: str) -> Iterator[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, raw in enumerate(stream, start=1):
                if not raw.strip():
                    _fail("jsonl_blank_line", f"{label}:{line_number}")
                try:
                    value = json.loads(
                        raw,
                        parse_constant=lambda token: _reject_json_constant(label, token),
                    )
                except json.JSONDecodeError as error:
                    _fail("jsonl_decode_failed", f"{label}:{line_number}:{error}")
                if not isinstance(value, dict):
                    _fail("jsonl_object_required", f"{label}:{line_number}")
                yield value
    except (OSError, UnicodeError) as error:
        _fail("jsonl_read_failed", f"{label}:{error}")


def _reject_json_constant(label: str, token: str) -> None:
    _fail("nonfinite_json_constant", f"{label}:{token}")


def _assert_finite(value: Any, label: str) -> None:
    if not _is_finite_tree(value):
        _fail("nonfinite_value", label)


def _is_finite_tree(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return all(_is_finite_tree(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return all(_is_finite_tree(child) for child in value)
    return True


def _matrix_shape(value: Any, label: str) -> tuple[int, int]:
    rows = _sequence(value, label)
    if not rows:
        return (0, 0)
    lengths = []
    for row in rows:
        lengths.append(len(_sequence(row, label)))
    if len(set(lengths)) != 1:
        _fail("matrix_not_rectangular", label)
    return (len(rows), lengths[0])


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", label)
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("sequence_required", label)
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("integer_required", f"{label}:{value!r}")
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    result = _integer(value, label)
    if result < 0:
        _fail("nonnegative_integer_required", f"{label}:{result}")
    return result


def _positive_integer(value: Any, label: str) -> int:
    result = _integer(value, label)
    if result < 1:
        _fail("positive_integer_required", f"{label}:{result}")
    return result


def _finite_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("number_required", f"{label}:{value!r}")
    result = float(value)
    if not math.isfinite(result):
        _fail("finite_number_required", label)
    return result


def _require_all_permissions_false(value: Mapping[str, Any], label: str) -> None:
    spoofed = sorted(name for name, enabled in value.items() if enabled is not False)
    if spoofed:
        _fail("permission_authority_spoof", f"{label}:{','.join(spoofed)}")


def _resolve_directory(path: str | Path, label: str) -> Path:
    value = Path(path).expanduser()
    if value.is_symlink() or not value.is_dir():
        _fail("directory_unavailable_or_symlink", f"{label}:{value}")
    return value.resolve(strict=True)


def _resolve_regular_file(path: str | Path, label: str) -> Path:
    value = Path(path).expanduser()
    if value.is_symlink() or not value.is_file():
        _fail("regular_file_required", f"{label}:{value}")
    return value.resolve(strict=True)


def _git_output(root: Path, args: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        _fail("git_query_failed", " ".join(args))
    return completed.stdout.strip()


def _git_bytes(root: Path, args: Sequence[str]) -> bytes:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        _fail("git_query_failed", " ".join(args))
    return completed.stdout


def _without_internal_keys(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        name: item
        for name, item in value.items()
        if name not in {"frames_by_key", "manifest"}
    }


def _fail(code: str, detail: str = "") -> None:
    raise D3A1V2ExternalAuditError(code, detail)


__all__ = [
    "D3_A1_V2_AUDIT_SCHEMA_VERSION",
    "D3_A1_V2_AUDIT_STATUS",
    "D3A1V2ExternalAuditError",
    "D3A1V2ExternalAuditInputs",
    "audit_d3_a1_source_independent_v2",
    "render_d3_a1_source_independent_v2_audit_cn",
    "write_d3_a1_source_independent_v2_audit",
]
