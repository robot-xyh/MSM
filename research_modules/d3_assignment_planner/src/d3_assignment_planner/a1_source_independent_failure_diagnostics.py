"""Read-only failure attribution for the frozen D3 A1 v2 evaluation.

The diagnostic consumes only the immutable v2 result, its contract and
bundle, plus already-published D6/main review evidence.  It never invokes a
model, optimizer, assignment publisher, runtime adapter, or formal holdout.
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
import shutil
from typing import Any, Iterable, Mapping, Sequence


DIAGNOSTIC_SCHEMA_VERSION = "d3_a1_v2_failure_diagnostics_v1"
FRAME_DIAGNOSTIC_SCHEMA_VERSION = "d3_a1_v2_failure_frame_diagnostics_v1"
DIAGNOSTIC_STATUS = (
    "v2_failure_attributed_v3_development_source_requested_not_admitted"
)
V3_REQUEST_SCHEMA_VERSION = (
    "d3_a1_source_independent_v3_development_data_request_v1"
)
V3_SEED_REGISTRY_SCHEMA_VERSION = (
    "d3_a1_source_independent_v3_seed_exclusion_registry_v1"
)

_EXPECTED_CONTRACT_SHA256 = (
    "f47ec9d095af11042c670b0e358e3e7285a166fa48e3df57829b14c1da8497e7"
)
_EXPECTED_CONTRACT_ID = (
    "d3-a1-assignment-aware-source-independent-evaluation-v2-20260730"
)
_EXPECTED_RESULT_HASHES = {
    "SOURCE_INDEPENDENT_EVALUATION_CN.md": (
        "4934c616ce91ac2f9462c5b8718187a7c7781e06b10bd848bdd24748f01b470a"
    ),
    "aggregate.json": (
        "9d44819c50fe7a7b4aa96f1ac99b665235a8e7e7fba0e84b3fbe6ef282a6e3b1"
    ),
    "per_frame_evaluation.csv": (
        "a84bda095cfcecd0d6b6c5649600dbdbbc91b5a4b82ca4166b272337834bf9c2"
    ),
    "per_frame_evaluation.jsonl": (
        "88377f35a874423af3fa55b9b183ec5b8a883f85f4929ff12a66f96d07a2076b"
    ),
}
_EXPECTED_RESULT_SHA256SUMS_SHA256 = (
    "f42170b252f61212c146364adc60d504c024e35bab3e3973d5140cdd1f56fa76"
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
_EXPECTED_D6_AUDIT_SHA256 = (
    "2aff8fb21105d4a3afe9855bf2719631aa4a310d7aad8d74d75a5e69fdb7bbe3"
)
_EXPECTED_EVALUATION_SEEDS = frozenset(range(20000, 20100))
_EXPECTED_FORMAL_SEEDS = frozenset(range(1000, 1020))
_EXPECTED_TRAINING_SEEDS = frozenset(range(100))
_EXPECTED_SPLITS = ("train", "validation", "test")
_EXPECTED_SPLIT_FRAMES = {"train": 178, "validation": 57, "test": 57}
_EXPECTED_SPLIT_EPISODES = {"train": 60, "validation": 20, "test": 20}
_EXPECTED_RESULT_FILES = frozenset({*_EXPECTED_RESULT_HASHES, "SHA256SUMS"})
_EXPECTED_BUNDLE_FILES = frozenset(
    {"manifest.json", "state_dict.json", "SHA256SUMS"}
)
_EXPECTED_CSV_FIELDS = (
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
_EXPECTED_FRAME_FIELDS = frozenset(
    {
        "schema_version",
        "mode",
        "evaluation_group",
        "evaluation_subgroup",
        "source_split",
        "scenario_version",
        "seed",
        "episode",
        "frame_index",
        "timestamp_s",
        "input_finite",
        "online_truth_use_count",
        "r0",
        "teacher",
        "candidate",
        "effective",
        "r0_rule_cost_matrix_sha256",
        "r0_rule_matrix_mutated",
        "ood",
        "rejected",
        "rejection_reasons",
        "rejection_reason_count",
        "permissions",
        "model_outputs",
        "input_cardinality",
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
        "truthid",
        "truthlabel",
    }
)
_FORBIDDEN_IDENTITY_SUFFIXES = (
    "truthid",
    "truthlabel",
    "actorid",
    "actorname",
    "objectid",
    "objectname",
    "globaltrackid",
    "vehicleid",
    "vehiclename",
)
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class A1FailureDiagnosticError(ValueError):
    """Fail-closed diagnostic error with a stable reason code."""

    def __init__(self, code: str, detail: str = "") -> None:
        message = code if not detail else f"{code}: {detail}"
        super().__init__(message)
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class A1FailureDiagnosticInputs:
    """Fixed read-only inputs for the official v2 diagnosis."""

    repository_root: Path
    result_dir: Path
    contract_path: Path
    bundle_dir: Path
    d6_audit_path: Path
    main_report_path: Path
    data_request_path: Path
    seed_registry_path: Path
    analysis_id: str
    analyzed_at_utc: str

    def __post_init__(self) -> None:
        root = _resolve_directory(self.repository_root, "repository_root")
        object.__setattr__(self, "repository_root", root)
        for name in ("result_dir", "bundle_dir"):
            value = _relative_to_root(root, Path(getattr(self, name)))
            object.__setattr__(self, name, _resolve_directory(value, name))
        for name in (
            "contract_path",
            "d6_audit_path",
            "main_report_path",
            "data_request_path",
            "seed_registry_path",
        ):
            value = _relative_to_root(root, Path(getattr(self, name)))
            object.__setattr__(self, name, _resolve_file(value, name))
        if not self.analysis_id.strip() or not self.analyzed_at_utc.strip():
            _fail("analysis_identity_invalid")


@dataclass(frozen=True, slots=True)
class A1FailureDiagnosticResult:
    """In-memory diagnostics and deterministic per-frame projections."""

    summary: Mapping[str, Any]
    per_frame: tuple[Mapping[str, Any], ...]


def diagnose_a1_source_independent_v2(
    inputs: A1FailureDiagnosticInputs,
) -> A1FailureDiagnosticResult:
    """Strictly reload and diagnose the frozen v2 evidence without writes."""

    pre_snapshot = _input_snapshot(inputs)
    contract = _load_json(inputs.contract_path, "contract")
    contract_info = _validate_contract(contract, inputs.contract_path)
    result_hashes = _verify_result_inventory(inputs.result_dir)
    bundle_info = _verify_bundle(inputs.bundle_dir, contract)
    aggregate = _load_json(inputs.result_dir / "aggregate.json", "aggregate")
    rows = tuple(
        _load_jsonl(
            inputs.result_dir / "per_frame_evaluation.jsonl",
            "per_frame_evaluation",
        )
    )
    row_audit = _validate_rows(
        rows,
        aggregate=aggregate,
        cell_by_seed=contract_info["cell_by_seed"],
    )
    csv_audit = _validate_csv(
        inputs.result_dir / "per_frame_evaluation.csv",
        rows,
    )
    d6_evidence = _validate_d6_audit(inputs.d6_audit_path)
    main_evidence = _validate_main_report(inputs.main_report_path)
    registry = _load_json(inputs.seed_registry_path, "v3_seed_registry")
    registry_info = _validate_v3_seed_registry(registry)
    request = _load_json(inputs.data_request_path, "v3_data_request")
    request_info = _validate_v3_data_request(
        request,
        registry=registry,
        registry_path=inputs.seed_registry_path,
    )
    per_frame = tuple(
        _diagnose_frame(
            row,
            configured_target_count=contract_info["cell_by_seed"][int(row["seed"])][
                "configured_scenario_target_count"
            ],
            configured_resource_count=contract_info["cell_by_seed"][int(row["seed"])][
                "resource_count"
            ],
        )
        for row in rows
    )
    stratification = _build_stratification(per_frame)
    test_attribution = _test_positive_failure_attribution(per_frame)
    post_snapshot = _input_snapshot(inputs)
    mutations = sorted(
        name
        for name, digest in pre_snapshot.items()
        if post_snapshot.get(name) != digest
    )
    if mutations:
        _fail("read_only_input_mutation_detected", ",".join(mutations))

    permissions = {key: False for key in _AUTHORITY_KEYS}
    permissions.update(
        {
            "optimizer": False,
            "checkpoint_selection": False,
            "normalization_refit": False,
            "threshold_adjustment": False,
            "generation": False,
            "training": False,
        }
    )
    summary: dict[str, Any] = {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "analysis_id": inputs.analysis_id,
        "analyzed_at_utc": inputs.analyzed_at_utc,
        "status": DIAGNOSTIC_STATUS,
        "scope": {
            "read_only_diagnosis": True,
            "training_count": 0,
            "model_invocation_count": 0,
            "optimizer_step_count": 0,
            "model_weight_update_count": 0,
            "threshold_adjustment_count": 0,
            "normalization_refit_count": 0,
            "new_bundle_write_count": 0,
            "formal_seed_read_count": 0,
            "runtime_output_count": 0,
            "assignment_output_count": 0,
            "plan_output_count": 0,
            "control_output_count": 0,
        },
        "input_integrity": {
            "result_file_sha256": result_hashes,
            "contract_sha256": _sha256_file(inputs.contract_path),
            "bundle": bundle_info,
            "input_snapshot_sha256": _sha256_json(pre_snapshot),
            "input_mutation_count": 0,
            "input_mutations": [],
        },
        "frozen_v2_confirmation": row_audit,
        "csv_jsonl_closure": csv_audit,
        "external_evidence": {
            "d6_independent_audit": d6_evidence,
            "main_report": main_evidence,
        },
        "stratification": stratification,
        "test_positive_failure_attribution": test_attribution,
        "v3_development_data_request": {
            **request_info,
            "request_file_sha256": _sha256_file(inputs.data_request_path),
            "seed_registry_file_sha256": _sha256_file(inputs.seed_registry_path),
            "seed_exclusion": registry_info,
        },
        "epistemic_limits": {
            "teacher_edge_candidate_reachability": {
                "available": False,
                "reason": (
                    "v2 per-frame output omits candidate_edge_indices and action-mask "
                    "contents; D6 audited candidate safety but did not publish a "
                    "teacher-edge reachability denominator"
                ),
            },
            "per_edge_model_ranking": {
                "available": False,
                "reason": (
                    "v2 per-frame output contains selected candidate bindings and the "
                    "maximum correction only, not per-edge residuals or ranks"
                ),
            },
            "per_target_demand_slot_structure": {
                "available": False,
                "reason": (
                    "v2 per-frame output contains only demand-slot cardinality, not the "
                    "anonymous demand vector or slot mapping"
                ),
            },
        },
        "permissions": permissions,
        "conclusion": {
            "v2_remains_frozen": True,
            "v2_admitted": False,
            "v3_data_generation_authorized": False,
            "v3_model_training_authorized": False,
            "formal_holdout_authorized": False,
            "runtime_or_control_authority_granted": False,
        },
    }
    summary["content_sha256"] = _content_sha256(summary)
    return A1FailureDiagnosticResult(summary=summary, per_frame=per_frame)


def write_a1_failure_diagnostics(
    output_dir: str | Path,
    result: A1FailureDiagnosticResult,
) -> Mapping[str, Path]:
    """Write a deterministic diagnostic bundle without overwriting evidence."""

    output = Path(output_dir)
    if output.exists() or output.is_symlink():
        _fail("diagnostic_output_already_exists", str(output))
    temporary = output.with_name(f".{output.name}.staging")
    if temporary.exists() or temporary.is_symlink():
        _fail("diagnostic_staging_already_exists", str(temporary))
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        summary_path = temporary / "diagnostics.json"
        jsonl_path = temporary / "per_frame_attribution.jsonl"
        csv_path = temporary / "per_frame_attribution.csv"
        report_path = temporary / "A1_V2_FAILURE_ATTRIBUTION_AND_V3_REQUEST_CN.md"
        summary_path.write_text(
            json.dumps(
                dict(result.summary),
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        jsonl_path.write_text(
            "".join(_canonical_json(dict(row)) + "\n" for row in result.per_frame),
            encoding="utf-8",
        )
        _write_frame_diagnostic_csv(csv_path, result.per_frame)
        report_path.write_text(
            render_a1_failure_diagnostics_cn(result.summary),
            encoding="utf-8",
        )
        payloads = (summary_path, jsonl_path, csv_path, report_path)
        checksum_path = temporary / "SHA256SUMS"
        checksum_path.write_text(
            "".join(
                f"{_sha256_file(path)}  {path.name}\n"
                for path in sorted(payloads, key=lambda value: value.name)
            ),
            encoding="ascii",
        )
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "summary": output / summary_path.name,
        "jsonl": output / jsonl_path.name,
        "csv": output / csv_path.name,
        "report": output / report_path.name,
        "checksums": output / "SHA256SUMS",
    }


def render_a1_failure_diagnostics_cn(summary: Mapping[str, Any]) -> str:
    """Render the evidence boundary and v3 source request in Chinese."""

    frozen = summary["frozen_v2_confirmation"]
    test = summary["test_positive_failure_attribution"]
    request = summary["v3_development_data_request"]
    lines = [
        "# D3 A1 v2 失败归因与 v3 开发来源请求",
        "",
        f"分析日期：{summary['analyzed_at_utc']}",
        "",
        "## 结论",
        "",
        (
            "冻结 v2 制品已严格复载。100 个 episode、292 帧和 seed 20000-20099 "
            "与合同一致，test 正类教师完全匹配仍为 0/25。94 个拒绝帧的矩阵和绑定"
            "均恢复 exact R0，正式 seed 1000-1019 的读取数为 0。"
        ),
        (
            "25 个 test 正类中，9 帧由 feature OOD 明确触发规则回退；其余 16 帧在"
            "非 OOD 条件下已经出现候选动作与教师动作不一致。22 帧同时发生安全投影"
            "拒绝，但没有一帧在投影前已经精确命中教师，因此投影不是 0/25 的唯一"
            "直接原因。"
        ),
        (
            "v2 输出没有逐边候选集合、逐边模型排序和匿名需求槽映射。候选不可达、"
            "模型排序误差及动作槽结构三者不能继续拆分，相关结论保持 unavailable。"
        ),
        "",
        "## 制品复载",
        "",
        "| 项目 | 结果 |",
        "| --- | ---: |",
        f"| episode | {frozen['episode_count']} |",
        f"| 帧 | {frozen['frame_count']} |",
        f"| seed | {frozen['unique_seed_count']} |",
        f"| 拒绝后 exact-R0 | {frozen['fallback_exact_r0_count']}/94 |",
        f"| 正式 seed 读取 | {frozen['formal_seed_read_count']} |",
        f"| 在线身份字段 | {frozen['forbidden_identity_key_count']} |",
        "",
        "## test 正类归因",
        "",
        "| 归因项 | 帧数 | 状态 |",
        "| --- | ---: | --- |",
        (
            "| feature OOD 规则回退 | "
            f"{test['exclusive_observable_pathway_counts']['feature_ood_rule_fallback']} | 已确认 |"
        ),
        (
            "| 非 OOD 候选动作不匹配 | "
            f"{test['exclusive_observable_pathway_counts']['candidate_selection_mismatch_non_ood']} | "
            "已确认候选结果不一致，内部原因未拆分 |"
        ),
        (
            "| 投影单独阻断已匹配教师的候选 | "
            f"{test['projection_only_failure_count']} | 已确认无此类帧 |"
        ),
        (
            "| 候选不可达 | "
            f"{test['teacher_candidate_reachability_unavailable_count']} | unavailable |"
        ),
        (
            "| 逐边模型排序错误 | "
            f"{test['per_edge_model_ranking_unavailable_count']} | unavailable |"
        ),
        (
            "| 动作槽/需求结构直接致因 | "
            f"{test['demand_structure_attribution_unavailable_count']} | unavailable |"
        ),
        "",
        (
            f"可观测失败路径覆盖 {test['observable_pathway_denominator']}/"
            f"{test['positive_denominator']}；严格根因可确认 {test['strict_root_cause_denominator']}/"
            f"{test['positive_denominator']}，对应 9 帧 OOD。"
        ),
        "",
        "## v3 开发来源请求",
        "",
        (
            f"请求 {request['requested_episode_count']} 个 episode、"
            f"{request['requested_unique_seed_count']} 个全新 seed 和 "
            f"{request['requested_cell_count']} 个场景规模单元。"
            "请求同时覆盖 5、20、50、100、200 规模、资源富余/短缺、动态增删、"
            "中心与二级失效、高威胁 M 对 N 和近决策边界困难负类。"
        ),
        (
            "新来源必须记录匿名候选边可达性、逐边残差排序、动作掩码摘要、匿名需求槽"
            "结构和投影前后原因。它只用于 main 后续生成新的 development 来源，"
            "当前没有分配 seed，也没有授权生成、训练、选模或调阈值。"
        ),
        "",
        "已明确排除训练 seed 0-99、正式 seed 1000-1019、已评价 seed 20000-20099。",
        "main 分配新 seed 前还必须合并所有 D3 已登记 seed；缺少规范注册表快照时失败关闭。",
        "",
        "## 权限",
        "",
        (
            "v2 状态继续为 frozen/not admitted。runtime、assist、assignment、plan、"
            "control、physical、formal admission 和 production admission 均为 false。"
        ),
        "本次没有训练模型，没有写新 bundle，没有读取正式 holdout。",
        "",
    ]
    return "\n".join(lines)


def _validate_contract(
    contract: Mapping[str, Any],
    contract_path: Path,
) -> Mapping[str, Any]:
    if _sha256_file(contract_path) != _EXPECTED_CONTRACT_SHA256:
        _fail("contract_sha256_mismatch")
    if contract.get("schema_version") != (
        "d3_a1_source_independent_evaluation_contract_v2"
    ):
        _fail("contract_schema_mismatch")
    if contract.get("contract_id") != _EXPECTED_CONTRACT_ID:
        _fail("contract_id_mismatch")
    if contract.get("mode") != "source_independent_evaluation":
        _fail("contract_mode_mismatch")
    _require_all_false(_mapping(contract.get("permissions"), "contract_permissions"))
    source = _mapping(contract.get("source_dataset"), "source_dataset")
    seeds = tuple(_integer(value, "source_seed") for value in source.get("seed_values", ()))
    if len(seeds) != 100 or frozenset(seeds) != _EXPECTED_EVALUATION_SEEDS:
        _fail("contract_seed_universe_mismatch")
    if source.get("episode_count") != 100 or source.get("unique_seed_count") != 100:
        _fail("contract_source_count_mismatch")
    if source.get("split_seed_counts") != _EXPECTED_SPLIT_EPISODES:
        _fail("contract_split_count_mismatch")
    formal = frozenset(
        _integer(value, "formal_seed")
        for value in source.get("formal_holdout_seed_values", ())
    )
    if formal != _EXPECTED_FORMAL_SEEDS:
        _fail("contract_formal_seed_universe_mismatch")
    cells = source.get("cells")
    if not isinstance(cells, list) or len(cells) != 10:
        _fail("contract_cells_invalid")
    cell_by_seed: dict[int, Mapping[str, Any]] = {}
    for raw in cells:
        cell = _mapping(raw, "contract_cell")
        for value in cell.get("seed_values", ()):
            seed = _integer(value, "cell_seed")
            if seed in cell_by_seed:
                _fail("contract_duplicate_cell_seed", str(seed))
            cell_by_seed[seed] = cell
    if frozenset(cell_by_seed) != _EXPECTED_EVALUATION_SEEDS:
        _fail("contract_cell_seed_universe_mismatch")
    frozen = _mapping(contract.get("frozen_bundle"), "frozen_bundle")
    if (
        frozen.get("manifest_sha256") != _EXPECTED_BUNDLE_MANIFEST_SHA256
        or frozen.get("state_dict_sha256") != _EXPECTED_BUNDLE_STATE_SHA256
        or frozen.get("tree_sha256") != _EXPECTED_BUNDLE_TREE_SHA256
    ):
        _fail("contract_bundle_hash_mismatch")
    _assert_finite(contract, "contract")
    return {"cell_by_seed": cell_by_seed}


def _verify_result_inventory(root: Path) -> Mapping[str, str]:
    actual = frozenset(path.name for path in root.iterdir())
    if actual != _EXPECTED_RESULT_FILES:
        _fail(
            "result_inventory_mismatch",
            f"missing={sorted(_EXPECTED_RESULT_FILES - actual)};"
            f"extra={sorted(actual - _EXPECTED_RESULT_FILES)}",
        )
    for name in actual:
        _resolve_file(root / name, f"result/{name}")
    manifest = _parse_checksums(root / "SHA256SUMS", _EXPECTED_RESULT_HASHES)
    if _sha256_file(root / "SHA256SUMS") != _EXPECTED_RESULT_SHA256SUMS_SHA256:
        _fail("result_sha256sums_file_mismatch")
    hashes = {name: _sha256_file(root / name) for name in sorted(actual)}
    for name, expected in _EXPECTED_RESULT_HASHES.items():
        if manifest.get(name) != expected or hashes.get(name) != expected:
            _fail("result_file_sha256_mismatch", name)
    return hashes


def _verify_bundle(root: Path, contract: Mapping[str, Any]) -> Mapping[str, Any]:
    actual = frozenset(path.name for path in root.iterdir())
    if actual != _EXPECTED_BUNDLE_FILES:
        _fail("bundle_inventory_mismatch")
    for name in actual:
        _resolve_file(root / name, f"bundle/{name}")
    expected = {
        "manifest.json": _EXPECTED_BUNDLE_MANIFEST_SHA256,
        "state_dict.json": _EXPECTED_BUNDLE_STATE_SHA256,
    }
    checksums = _parse_checksums(root / "SHA256SUMS", expected)
    if checksums != expected:
        _fail("bundle_checksum_manifest_mismatch")
    for name, digest in expected.items():
        if _sha256_file(root / name) != digest:
            _fail("bundle_file_sha256_mismatch", name)
    tree_payload = "".join(f"{name}:{expected[name]}\n" for name in sorted(expected))
    tree_sha = sha256(tree_payload.encode("ascii")).hexdigest()
    frozen = _mapping(contract.get("frozen_bundle"), "frozen_bundle")
    if tree_sha != frozen.get("tree_sha256") or tree_sha != _EXPECTED_BUNDLE_TREE_SHA256:
        _fail("bundle_tree_sha256_mismatch")
    manifest = _load_json(root / "manifest.json", "bundle_manifest")
    _assert_finite(manifest, "bundle_manifest")
    if manifest.get("stage") != "development":
        _fail("bundle_stage_mismatch")
    _require_all_false(_mapping(manifest.get("permissions"), "bundle_permissions"))
    admission = _mapping(manifest.get("admission"), "bundle_admission")
    if admission.get("admitted_bundle") is not False or admission.get(
        "production_bundle"
    ) is not False:
        _fail("bundle_admission_forbidden")
    return {
        "manifest_sha256": expected["manifest.json"],
        "state_dict_sha256": expected["state_dict.json"],
        "tree_sha256": tree_sha,
        "stage": "development",
        "admitted": False,
    }


def _validate_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    aggregate: Mapping[str, Any],
    cell_by_seed: Mapping[int, Mapping[str, Any]],
) -> Mapping[str, Any]:
    if len(rows) != 292:
        _fail("frame_count_mismatch", str(len(rows)))
    _assert_finite(aggregate, "aggregate")
    if aggregate.get("schema_version") != (
        "d3_a1_source_independent_evaluation_aggregate_v2"
    ):
        _fail("aggregate_schema_mismatch")
    if aggregate.get("status") != (
        "source_independent_evaluation_v2_gate_passed_not_admitted"
    ):
        _fail("aggregate_status_mismatch")
    if aggregate.get("contract_id") != _EXPECTED_CONTRACT_ID:
        _fail("aggregate_contract_mismatch")
    if aggregate.get("machine_gate_passed") is not True:
        _fail("aggregate_machine_gate_not_passed")
    _require_all_false(_mapping(aggregate.get("permissions"), "aggregate_permissions"))

    split_frames: Counter[str] = Counter()
    split_episodes: dict[str, set[tuple[str, int, str]]] = defaultdict(set)
    seen_keys: set[tuple[str, int, str, int]] = set()
    seen_seeds: set[int] = set()
    seen_episodes: set[tuple[str, int, str]] = set()
    positive = 0
    negative = 0
    test_positive = 0
    test_exact_teacher = 0
    rejected = 0
    fallback_exact = 0
    identity_count = 0
    model_output_count = 0
    for index, row in enumerate(rows):
        if set(row) != _EXPECTED_FRAME_FIELDS:
            _fail("frame_fields_mismatch", str(index))
        _assert_finite(row, f"frame[{index}]")
        identity_count += len(_find_forbidden_identity_keys(row))
        if row.get("schema_version") != "d3_a1_source_independent_evaluation_frame_v2":
            _fail("frame_schema_mismatch", str(index))
        if row.get("mode") != "source_independent_evaluation":
            _fail("frame_mode_mismatch", str(index))
        split = str(row.get("source_split"))
        if split not in _EXPECTED_SPLITS:
            _fail("frame_split_invalid", split)
        seed = _integer(row.get("seed"), "frame_seed")
        if seed not in _EXPECTED_EVALUATION_SEEDS or seed in _EXPECTED_FORMAL_SEEDS:
            _fail("frame_seed_forbidden", str(seed))
        cell = cell_by_seed.get(seed)
        if cell is None or row.get("scenario_version") != cell.get("scenario_version"):
            _fail("frame_seed_cell_mismatch", str(seed))
        key = (
            str(row["scenario_version"]),
            seed,
            str(row["episode"]),
            _integer(row["frame_index"], "frame_index"),
        )
        if key in seen_keys:
            _fail("duplicate_frame_key", repr(key))
        seen_keys.add(key)
        episode = key[:3]
        seen_episodes.add(episode)
        seen_seeds.add(seed)
        split_frames[split] += 1
        split_episodes[split].add(episode)
        if row.get("input_finite") is not True or row.get("online_truth_use_count") != 0:
            _fail("frame_input_or_truth_claim_invalid", str(index))
        _require_all_false(_mapping(row.get("permissions"), "frame_permissions"))
        model_outputs = _mapping(row.get("model_outputs"), "model_outputs")
        for name in (
            "assignment_output_count",
            "plan_output_count",
            "runtime_output_count",
            "version_output_count",
        ):
            value = _integer(model_outputs.get(name), f"model_outputs.{name}")
            model_output_count += value
        teacher = _mapping(row.get("teacher"), "teacher")
        candidate = _mapping(row.get("candidate"), "candidate")
        effective = _mapping(row.get("effective"), "effective")
        r0 = _mapping(row.get("r0"), "r0")
        _selected_edges(teacher, "teacher")
        _selected_edges(candidate, "candidate")
        _selected_edges(effective, "effective")
        _selected_edges(r0, "r0")
        opportunity = bool(teacher.get("opportunity"))
        if opportunity:
            positive += 1
            if split == "test":
                test_positive += 1
                test_exact_teacher += int(
                    candidate.get("selected_edges") == teacher.get("selected_edges")
                    and effective.get("selected_edges") == teacher.get("selected_edges")
                )
        else:
            negative += 1
        reasons = row.get("rejection_reasons")
        if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
            _fail("rejection_reasons_invalid", str(index))
        if _integer(row.get("rejection_reason_count"), "rejection_reason_count") != len(
            reasons
        ):
            _fail("rejection_reason_count_mismatch", str(index))
        is_rejected = bool(row.get("rejected"))
        if is_rejected != bool(reasons):
            _fail("rejection_reason_presence_mismatch", str(index))
        rejected += int(is_rejected)
        if is_rejected:
            exact = (
                effective.get("selected_edges") == r0.get("selected_edges")
                and effective.get("exact_r0_binding") is True
                and effective.get("exact_r0_matrix") is True
                and effective.get("cost_matrix_sha256")
                == row.get("r0_rule_cost_matrix_sha256")
            )
            fallback_exact += int(exact)
            if not exact:
                _fail("rejected_frame_not_exact_r0", str(index))
        cardinality = _mapping(row.get("input_cardinality"), "input_cardinality")
        if cardinality.get("configured_resource_count") != cell.get("resource_count"):
            _fail("configured_resource_count_mismatch", str(index))
        if cardinality.get("observed_anonymous_resource_count") != cell.get(
            "resource_count"
        ):
            _fail("observed_resource_count_mismatch", str(index))
    if identity_count:
        _fail("forbidden_identity_key_present", str(identity_count))
    if model_output_count:
        _fail("model_authority_output_present", str(model_output_count))
    if seen_seeds != set(_EXPECTED_EVALUATION_SEEDS):
        _fail("frame_seed_universe_mismatch")
    if len(seen_episodes) != 100:
        _fail("episode_count_mismatch", str(len(seen_episodes)))
    if dict(split_frames) != _EXPECTED_SPLIT_FRAMES:
        _fail("split_frame_count_mismatch", repr(dict(split_frames)))
    actual_split_episodes = {
        split: len(split_episodes[split]) for split in _EXPECTED_SPLITS
    }
    if actual_split_episodes != _EXPECTED_SPLIT_EPISODES:
        _fail("split_episode_count_mismatch", repr(actual_split_episodes))
    if (positive, negative, test_positive, test_exact_teacher) != (110, 182, 25, 0):
        _fail(
            "positive_negative_or_test_metric_mismatch",
            repr((positive, negative, test_positive, test_exact_teacher)),
        )
    if rejected != 94 or fallback_exact != 94:
        _fail("fallback_count_mismatch", repr((rejected, fallback_exact)))

    overall = _mapping(aggregate.get("overall_metrics"), "overall_metrics")
    if (
        overall.get("frame_count") != 292
        or overall.get("positive_frame_count") != 110
        or overall.get("negative_frame_count") != 182
        or overall.get("projection_rejection_count") != 94
        or overall.get("fallback_exact_r0_matrix_count") != 94
        or overall.get("fallback_exact_r0_binding_count") != 94
    ):
        _fail("aggregate_overall_reconciliation_failed")
    test_claim = _mapping(
        _mapping(aggregate.get("source_subgroup_metrics"), "source_groups").get("test"),
        "test_metrics",
    )
    teacher_match = _mapping(
        test_claim.get("positive_teacher_exact_match"),
        "test_teacher_exact_match",
    )
    if teacher_match.get("numerator") != 0 or teacher_match.get("denominator") != 25:
        _fail("aggregate_test_teacher_match_mismatch")
    formal = _mapping(aggregate.get("formal_holdout"), "formal_holdout")
    if formal.get("read_count") != 0 or frozenset(formal.get("seed_values", ())) != (
        _EXPECTED_FORMAL_SEEDS
    ):
        _fail("aggregate_formal_holdout_claim_invalid")
    return {
        "episode_count": len(seen_episodes),
        "frame_count": len(rows),
        "unique_seed_count": len(seen_seeds),
        "seed_minimum": min(seen_seeds),
        "seed_maximum": max(seen_seeds),
        "split_frame_counts": dict(split_frames),
        "split_episode_counts": actual_split_episodes,
        "positive_frame_count": positive,
        "negative_frame_count": negative,
        "test_positive_teacher_exact_match_numerator": test_exact_teacher,
        "test_positive_teacher_exact_match_denominator": test_positive,
        "projection_rejection_count": rejected,
        "fallback_exact_r0_count": fallback_exact,
        "formal_seed_read_count": 0,
        "forbidden_identity_key_count": identity_count,
        "model_authority_output_count": model_output_count,
        "all_permissions_false": True,
    }


def _validate_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != _EXPECTED_CSV_FIELDS:
            _fail("csv_header_mismatch")
        csv_rows = list(reader)
    if len(csv_rows) != len(rows):
        _fail("csv_row_count_mismatch")
    mismatch_count = 0
    for index, (csv_row, row) in enumerate(zip(csv_rows, rows, strict=True)):
        expected = _frame_csv_projection(row)
        if csv_row != expected:
            mismatch_count += 1
            _fail("csv_jsonl_mismatch", str(index))
    return {
        "fixed_column_count": len(_EXPECTED_CSV_FIELDS),
        "row_count": len(csv_rows),
        "jsonl_row_count": len(rows),
        "matched_row_count": len(rows) - mismatch_count,
        "mismatch_count": mismatch_count,
        "header_exact": True,
    }


def _frame_csv_projection(row: Mapping[str, Any]) -> dict[str, str]:
    teacher = _mapping(row.get("teacher"), "teacher")
    r0 = _mapping(row.get("r0"), "r0")
    candidate = _mapping(row.get("candidate"), "candidate")
    effective = _mapping(row.get("effective"), "effective")
    opportunity = bool(teacher.get("opportunity"))
    return {
        "evaluation_group": str(row["evaluation_group"]),
        "evaluation_subgroup": str(row["evaluation_subgroup"]),
        "source_split": str(row["source_split"]),
        "scenario_version": str(row["scenario_version"]),
        "seed": str(row["seed"]),
        "episode": str(row["episode"]),
        "frame_index": str(row["frame_index"]),
        "timestamp_s": str(row["timestamp_s"]),
        "teacher_opportunity": str(int(opportunity)),
        "r0_selected_edges": _canonical_json(r0["selected_edges"]),
        "candidate_selected_edges": _canonical_json(candidate["selected_edges"]),
        "effective_selected_edges": _canonical_json(effective["selected_edges"]),
        "candidate_binding_change_count": str(candidate["binding_change_count_from_r0"]),
        "effective_binding_change_count": str(effective["binding_change_count_from_r0"]),
        "positive_teacher_exact_match": str(
            int(opportunity and effective["selected_edges"] == teacher["selected_edges"])
        ),
        "negative_exact_r0": str(
            int(not opportunity and bool(effective["exact_r0_binding"]))
        ),
        "ood": str(int(bool(row["ood"]))),
        "rejected": str(int(bool(row["rejected"]))),
        "rejection_reasons": "|".join(row["rejection_reasons"]),
        "fallback_exact_r0_matrix": str(
            int(bool(row["rejected"] and effective["exact_r0_matrix"]))
        ),
        "fallback_exact_r0_binding": str(
            int(bool(row["rejected"] and effective["exact_r0_binding"]))
        ),
    }


def _diagnose_frame(
    row: Mapping[str, Any],
    *,
    configured_target_count: int,
    configured_resource_count: int,
) -> Mapping[str, Any]:
    teacher = _mapping(row["teacher"], "teacher")
    candidate = _mapping(row["candidate"], "candidate")
    effective = _mapping(row["effective"], "effective")
    r0 = _mapping(row["r0"], "r0")
    cardinality = _mapping(row["input_cardinality"], "input_cardinality")
    opportunity = bool(teacher["opportunity"])
    candidate_exact = candidate["selected_edges"] == teacher["selected_edges"]
    effective_exact = effective["selected_edges"] == teacher["selected_edges"]
    if not opportunity:
        pathway = "negative_not_applicable"
    elif effective_exact:
        pathway = "teacher_exact_match"
    elif bool(row["ood"]):
        pathway = "feature_ood_rule_fallback"
    elif not candidate_exact:
        pathway = "candidate_selection_mismatch_non_ood"
    elif bool(row["rejected"]):
        pathway = "projection_rejected_teacher_exact_candidate"
    else:
        pathway = "other_observable_or_unavailable"
    target_count = int(cardinality["observed_anonymous_target_count"])
    resource_count = int(cardinality["observed_anonymous_resource_count"])
    slot_count = int(cardinality["target_demand_slot_count"])
    if target_count < resource_count:
        cardinality_relation = "anonymous_targets_less_than_resources"
    elif target_count > resource_count:
        cardinality_relation = "anonymous_targets_greater_than_resources"
    else:
        cardinality_relation = "anonymous_targets_equal_resources"
    if slot_count < target_count:
        slot_relation = "aggregate_slots_less_than_targets"
    elif slot_count > target_count:
        slot_relation = "aggregate_slots_greater_than_targets"
    else:
        slot_relation = "aggregate_slots_equal_targets_details_unavailable"
    return {
        "schema_version": FRAME_DIAGNOSTIC_SCHEMA_VERSION,
        "source_split": row["source_split"],
        "scenario_version": row["scenario_version"],
        "configured_scale": f"{configured_target_count}t{configured_resource_count}r",
        "seed": int(row["seed"]),
        "episode": row["episode"],
        "frame_index": int(row["frame_index"]),
        "timestamp_s": float(row["timestamp_s"]),
        "class_label": "positive" if opportunity else "negative",
        "candidate_availability_status": (
            "proposal_available_teacher_edge_reachability_unavailable"
        ),
        "teacher_candidate_reachability": "unavailable",
        "observed_anonymous_target_count": target_count,
        "observed_anonymous_resource_count": resource_count,
        "target_demand_slot_count": slot_count,
        "cardinality_relation": cardinality_relation,
        "demand_slot_relation": slot_relation,
        "teacher_binding_change_count": int(teacher["binding_change_count"]),
        "candidate_binding_change_count_from_r0": int(
            candidate["binding_change_count_from_r0"]
        ),
        "effective_binding_change_count_from_r0": int(
            effective["binding_change_count_from_r0"]
        ),
        "candidate_teacher_symmetric_difference_count": _edge_symmetric_difference(
            candidate["selected_edges"], teacher["selected_edges"]
        ),
        "effective_teacher_symmetric_difference_count": _edge_symmetric_difference(
            effective["selected_edges"], teacher["selected_edges"]
        ),
        "r0_teacher_symmetric_difference_count": _edge_symmetric_difference(
            r0["selected_edges"], teacher["selected_edges"]
        ),
        "candidate_exact_teacher": candidate_exact,
        "effective_exact_teacher": effective_exact,
        "candidate_exact_r0": candidate["selected_edges"] == r0["selected_edges"],
        "effective_exact_r0": bool(effective["exact_r0_binding"]),
        "ood": bool(row["ood"]),
        "rejected": bool(row["rejected"]),
        "rejection_reasons": list(row["rejection_reasons"]),
        "exclusive_observable_failure_pathway": pathway,
        "projection_rejection_cooccurs_after_candidate_mismatch": bool(
            opportunity
            and row["rejected"]
            and not candidate_exact
        ),
        "model_ranking_root_cause": "unavailable",
        "demand_structure_root_cause": "unavailable",
        "online_truth_use_count": 0,
        "all_permissions_false": True,
    }


def _build_stratification(
    rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    dimensions: dict[str, dict[str, list[Mapping[str, Any]]]] = {}
    key_functions = {
        "source_split": lambda row: str(row["source_split"]),
        "scenario": lambda row: str(row["scenario_version"]),
        "configured_scale": lambda row: str(row["configured_scale"]),
        "class_label": lambda row: str(row["class_label"]),
        "candidate_availability": lambda row: str(row["candidate_availability_status"]),
        "ood": lambda row: str(bool(row["ood"])).lower(),
        "cardinality_relation": lambda row: str(row["cardinality_relation"]),
        "demand_slot_relation": lambda row: str(row["demand_slot_relation"]),
        "anonymous_target_count": lambda row: str(row["observed_anonymous_target_count"]),
        "anonymous_resource_count": lambda row: str(row["observed_anonymous_resource_count"]),
        "teacher_binding_change_count": lambda row: str(row["teacher_binding_change_count"]),
        "candidate_teacher_difference_count": lambda row: str(
            row["candidate_teacher_symmetric_difference_count"]
        ),
    }
    for dimension, key_function in key_functions.items():
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[key_function(row)].append(row)
        dimensions[dimension] = {
            key: _stratum_summary(values) for key, values in sorted(groups.items())
        }
    reason_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        reasons = row["rejection_reasons"] or ["none"]
        for reason in reasons:
            reason_groups[str(reason)].append(row)
    dimensions["rejection_reason"] = {
        key: _stratum_summary(values) for key, values in sorted(reason_groups.items())
    }
    return dimensions


def _stratum_summary(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    pathways = Counter(str(row["exclusive_observable_failure_pathway"]) for row in rows)
    return {
        "frame_count": len(rows),
        "positive_frame_count": sum(row["class_label"] == "positive" for row in rows),
        "negative_frame_count": sum(row["class_label"] == "negative" for row in rows),
        "candidate_exact_teacher_count": sum(bool(row["candidate_exact_teacher"]) for row in rows),
        "effective_exact_teacher_count": sum(bool(row["effective_exact_teacher"]) for row in rows),
        "rejected_frame_count": sum(bool(row["rejected"]) for row in rows),
        "ood_frame_count": sum(bool(row["ood"]) for row in rows),
        "observable_failure_pathway_counts": dict(sorted(pathways.items())),
    }


def _test_positive_failure_attribution(
    rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    selected = [
        row
        for row in rows
        if row["source_split"] == "test" and row["class_label"] == "positive"
    ]
    if len(selected) != 25:
        _fail("test_positive_denominator_mismatch", str(len(selected)))
    pathways = Counter(
        str(row["exclusive_observable_failure_pathway"]) for row in selected
    )
    expected = {
        "feature_ood_rule_fallback": 9,
        "candidate_selection_mismatch_non_ood": 16,
    }
    if dict(pathways) != expected:
        _fail("test_failure_pathway_reconciliation_failed", repr(dict(pathways)))
    candidate_exact = sum(bool(row["candidate_exact_teacher"]) for row in selected)
    effective_exact = sum(bool(row["effective_exact_teacher"]) for row in selected)
    rejected = sum(bool(row["rejected"]) for row in selected)
    projection_only = sum(
        row["exclusive_observable_failure_pathway"]
        == "projection_rejected_teacher_exact_candidate"
        for row in selected
    )
    if candidate_exact or effective_exact or rejected != 22 or projection_only:
        _fail(
            "test_failure_counts_mismatch",
            repr((candidate_exact, effective_exact, rejected, projection_only)),
        )
    return {
        "positive_denominator": len(selected),
        "effective_teacher_exact_match_numerator": effective_exact,
        "candidate_teacher_exact_match_numerator": candidate_exact,
        "observable_pathway_denominator": sum(pathways.values()),
        "strict_root_cause_denominator": int(pathways["feature_ood_rule_fallback"]),
        "exclusive_observable_pathway_counts": dict(sorted(pathways.items())),
        "projection_rejection_cooccurrence_count": rejected,
        "projection_after_candidate_mismatch_count": sum(
            bool(row["projection_rejection_cooccurs_after_candidate_mismatch"])
            for row in selected
        ),
        "projection_only_failure_count": projection_only,
        "teacher_candidate_reachability_unavailable_count": len(selected),
        "per_edge_model_ranking_unavailable_count": len(selected),
        "demand_structure_attribution_unavailable_count": len(selected),
        "interpretation": {
            "feature_ood": "confirmed_direct_fallback_path",
            "non_ood_candidate_mismatch": (
                "candidate_result_mismatch_confirmed_internal_ranking_vs_topology_unavailable"
            ),
            "projection_rejection": (
                "cooccurring_fail_closed_gate_not_sole_teacher_match_cause"
            ),
            "candidate_unreachable": "unavailable",
            "model_ranking_error": "unavailable_at_per_edge_level",
            "action_slot_or_demand_structure": "unavailable",
            "other_observable_cause_count": 0,
        },
    }


def _validate_d6_audit(path: Path) -> Mapping[str, Any]:
    if _sha256_file(path) != _EXPECTED_D6_AUDIT_SHA256:
        _fail("d6_audit_sha256_mismatch")
    root = path.parent
    expected_files = {
        "audit.json",
        "D3_A1_SOURCE_INDEPENDENT_V2_EXTERNAL_AUDIT_CN.md",
    }
    checksums = _parse_checksums(root / "SHA256SUMS", expected_files)
    for name, digest in checksums.items():
        if _sha256_file(root / name) != digest:
            _fail("d6_audit_checksum_mismatch", name)
    audit = _load_json(path, "d6_audit")
    if audit.get("schema_version") != (
        "d6.d3-a1-source-independent-v2-external-audit.v1"
    ):
        _fail("d6_audit_schema_mismatch")
    if audit.get("status") != (
        "offline_integrity_and_preregistered_machine_gate_confirmed_not_admitted"
    ):
        _fail("d6_audit_status_mismatch")
    if audit.get("audit_integrity_passed") is not True:
        _fail("d6_audit_integrity_not_passed")
    _require_all_false(_mapping(audit.get("authorities"), "d6_authorities"))
    generalization = _mapping(audit.get("generalization_limit"), "d6_generalization")
    if (
        generalization.get("test_positive_teacher_exact_match_numerator") != 0
        or generalization.get("test_positive_teacher_exact_match_denominator") != 25
    ):
        _fail("d6_generalization_claim_mismatch")
    scope = _mapping(audit.get("scope"), "d6_scope")
    if scope.get("formal_seed_read_count") != 0:
        _fail("d6_formal_seed_read_claim_invalid")
    conclusion = _mapping(audit.get("conclusion"), "d6_conclusion")
    if (
        conclusion.get("offline_result_integrity_confirmed") is not True
        or conclusion.get("preregistered_machine_gate_confirmed") is not True
        or conclusion.get("runtime_or_formal_admission_granted") is not False
        or conclusion.get("physical_benefit_confirmed") is not False
    ):
        _fail("d6_conclusion_mismatch")
    content = str(audit.get("content_sha256", ""))
    payload = dict(audit)
    payload.pop("content_sha256", None)
    if _sha256_json(payload) != content:
        _fail("d6_content_sha256_mismatch")
    return {
        "audit_file_sha256": _sha256_file(path),
        "audit_content_sha256": content,
        "integrity_confirmed": True,
        "preregistered_machine_gate_confirmed": True,
        "test_positive_teacher_exact_match": {"numerator": 0, "denominator": 25},
        "runtime_or_formal_admission_granted": False,
        "physical_benefit_confirmed": False,
    }


def _validate_main_report(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    required = (
        "D3 A1 来源独立评价闭合",
        "D6 外部独立审计：通过，只确认离线完整性和机器门",
        "教师完全匹配为 `0/25`",
        "正式 seed 1000-1019：读取数 0",
    )
    missing = [value for value in required if value not in text]
    if missing:
        _fail("main_report_evidence_missing", repr(missing))
    return {
        "report_sha256": _sha256_file(path),
        "d6_status_consistent": True,
        "test_zero_of_25_recorded": True,
        "formal_seed_read_zero_recorded": True,
        "report_is_read_only_context_not_independent_recomputation": True,
    }


def _validate_v3_seed_registry(registry: Mapping[str, Any]) -> Mapping[str, Any]:
    if registry.get("schema_version") != V3_SEED_REGISTRY_SCHEMA_VERSION:
        _fail("v3_seed_registry_schema_mismatch")
    if registry.get("status") != "exclusion_registry_frozen_seed_allocation_unassigned":
        _fail("v3_seed_registry_status_mismatch")
    catalogs = registry.get("known_forbidden_catalogs")
    if not isinstance(catalogs, list) or len(catalogs) != 3:
        _fail("v3_seed_catalogs_invalid")
    expanded: dict[str, set[int]] = {}
    for raw in catalogs:
        item = _mapping(raw, "v3_seed_catalog")
        catalog_id = str(item.get("catalog_id", ""))
        ranges = item.get("ranges")
        if not catalog_id or not isinstance(ranges, list) or not ranges:
            _fail("v3_seed_catalog_invalid", catalog_id)
        values: set[int] = set()
        for raw_range in ranges:
            seed_range = _mapping(raw_range, "v3_seed_range")
            start = _integer(seed_range.get("start"), "seed_range.start")
            stop = _integer(seed_range.get("stop_inclusive"), "seed_range.stop")
            if start < 0 or stop < start:
                _fail("v3_seed_range_invalid", catalog_id)
            values.update(range(start, stop + 1))
        if len(values) != item.get("seed_count"):
            _fail("v3_seed_catalog_count_mismatch", catalog_id)
        expanded[catalog_id] = values
    expected = {
        "scalable3d_training_v1": set(_EXPECTED_TRAINING_SEEDS),
        "scalable3d_formal_holdout_v1": set(_EXPECTED_FORMAL_SEEDS),
        "d3_a1_source_independent_evaluation_v2": set(_EXPECTED_EVALUATION_SEEDS),
    }
    if expanded != expected:
        _fail("v3_seed_catalog_universe_mismatch")
    union = set().union(*expanded.values())
    if len(union) != 220 or registry.get("known_forbidden_seed_count") != 220:
        _fail("v3_seed_union_count_mismatch")
    policy = _mapping(
        registry.get("additional_d3_registry_policy"),
        "additional_d3_registry_policy",
    )
    expected_policy = {
        "canonical_registry_union_required_at_allocation": True,
        "allocation_must_fail_if_registry_union_unavailable": True,
        "overlap_with_any_registered_d3_seed_allowed": False,
        "registry_snapshot_sha256_required": True,
    }
    if policy != expected_policy:
        _fail("v3_additional_registry_policy_not_fail_closed")
    allocation = _mapping(registry.get("requested_allocation"), "requested_allocation")
    if (
        allocation.get("requested_unique_seed_count") != 300
        or allocation.get("assigned_seed_values") != []
        or allocation.get("allocation_status") != "unassigned"
        or allocation.get("generation_authorized") is not False
    ):
        _fail("v3_seed_allocation_must_remain_unassigned")
    split = _mapping(registry.get("split_request"), "split_request")
    if (
        split.get("train_seed_count") != 180
        or split.get("validation_seed_count") != 60
        or split.get("test_seed_count") != 60
        or split.get("seed_atomic_across_scenarios_scales_and_splits") is not True
        or split.get("cross_split_seed_overlap_allowed") is not False
    ):
        _fail("v3_seed_split_request_invalid")
    _require_all_false(_mapping(registry.get("permissions"), "v3_seed_permissions"))
    return {
        "known_forbidden_seed_count": len(union),
        "training_seed_reuse_allowed": False,
        "formal_seed_reuse_allowed": False,
        "v2_evaluation_seed_reuse_allowed": False,
        "other_registered_d3_seed_reuse_allowed": False,
        "assigned_seed_count": 0,
        "allocation_status": "unassigned",
        "generation_authorized": False,
    }


def _validate_v3_data_request(
    request: Mapping[str, Any],
    *,
    registry: Mapping[str, Any],
    registry_path: Path,
) -> Mapping[str, Any]:
    if request.get("schema_version") != V3_REQUEST_SCHEMA_VERSION:
        _fail("v3_request_schema_mismatch")
    if request.get("status") != "request_frozen_generation_not_authorized":
        _fail("v3_request_status_mismatch")
    basis = _mapping(request.get("basis"), "v3_request_basis")
    expected_basis = {
        "v2_sha256sums_sha256": _EXPECTED_RESULT_SHA256SUMS_SHA256,
        "v2_aggregate_sha256": _EXPECTED_RESULT_HASHES["aggregate.json"],
        "v2_contract_sha256": _EXPECTED_CONTRACT_SHA256,
        "frozen_bundle_tree_sha256": _EXPECTED_BUNDLE_TREE_SHA256,
        "d6_external_audit_sha256": _EXPECTED_D6_AUDIT_SHA256,
    }
    for name, expected in expected_basis.items():
        if basis.get(name) != expected:
            _fail("v3_request_basis_mismatch", name)
    test_claim = _mapping(
        basis.get("test_positive_teacher_exact_match"),
        "v3_request_test_claim",
    )
    if test_claim != {"numerator": 0, "denominator": 25}:
        _fail("v3_request_test_claim_mismatch")
    scope = _mapping(request.get("scope"), "v3_request_scope")
    expected_scope = {
        "request_only": True,
        "data_generated": False,
        "model_trained": False,
        "bundle_written": False,
        "v2_model_or_threshold_changed": False,
        "formal_holdout_read": False,
        "v2_remains_frozen_and_not_admitted": True,
    }
    if scope != expected_scope:
        _fail("v3_request_scope_mismatch")
    dataset = _mapping(request.get("dataset_contract"), "v3_dataset_contract")
    if (
        dataset.get("requested_episode_count") != 300
        or dataset.get("requested_unique_seed_count") != 300
        or dataset.get("requested_cell_count") != 15
        or dataset.get("minimum_positive_frame_count") != 900
        or dataset.get("minimum_negative_frame_count") != 900
        or dataset.get("minimum_hard_negative_frame_count") != 450
    ):
        _fail("v3_dataset_request_count_mismatch")
    cells = request.get("collection_cells")
    if not isinstance(cells, list) or len(cells) != 15:
        _fail("v3_collection_cells_invalid")
    cell_ids: set[str] = set()
    total_episodes = 0
    positive_minimum = 0
    negative_minimum = 0
    hard_negative_minimum = 0
    scale_counts: Counter[int] = Counter()
    for raw in cells:
        cell = _mapping(raw, "v3_collection_cell")
        cell_id = str(cell.get("cell_id", ""))
        if not cell_id or cell_id in cell_ids:
            _fail("v3_collection_cell_id_invalid", cell_id)
        cell_ids.add(cell_id)
        target_count = _integer(cell.get("configured_target_count"), "cell_target_count")
        resource_count = _integer(
            cell.get("configured_resource_count"), "cell_resource_count"
        )
        if target_count < 1 or resource_count < 1:
            _fail("v3_collection_cell_scale_invalid", cell_id)
        scale_counts[target_count] += 1
        total_episodes += _integer(cell.get("requested_episode_count"), "cell_episode_count")
        positive_minimum += _integer(cell.get("minimum_positive_frames"), "cell_positive")
        negative_minimum += _integer(cell.get("minimum_negative_frames"), "cell_negative")
        hard_negative_minimum += _integer(
            cell.get("minimum_hard_negative_frames"), "cell_hard_negative"
        )
        focus = cell.get("difficulty_focus")
        if not isinstance(focus, list) or not focus:
            _fail("v3_collection_cell_focus_invalid", cell_id)
    if total_episodes != 300:
        _fail("v3_collection_episode_total_mismatch")
    if (positive_minimum, negative_minimum, hard_negative_minimum) != (900, 900, 450):
        _fail("v3_collection_frame_quota_mismatch")
    if not {5, 20, 50, 100, 200}.issubset(scale_counts):
        _fail("v3_collection_scale_coverage_incomplete")
    action_types = request.get("action_change_types")
    hard_negatives = request.get("hard_negative_types")
    observability = request.get("diagnostic_observability_requirements")
    if not isinstance(action_types, list) or len(action_types) < 10:
        _fail("v3_action_change_inventory_incomplete")
    if not isinstance(hard_negatives, list) or len(hard_negatives) < 8:
        _fail("v3_hard_negative_inventory_incomplete")
    required_observability = {
        "anonymous_candidate_edge_indices_or_content_sha256",
        "teacher_edges_in_candidate_mask_count_and_boolean",
        "per_edge_model_residual_rank_before_hungarian",
        "anonymous_target_demand_slot_vector_or_content_sha256",
        "pre_projection_and_post_projection_reason_codes",
        "all_permissions_false_and_online_truth_use_zero",
    }
    if not isinstance(observability, list) or not required_observability.issubset(
        set(observability)
    ):
        _fail("v3_observability_request_incomplete")
    seed_binding = _mapping(request.get("seed_registry"), "v3_request_seed_registry")
    if (
        seed_binding.get("path") != f"configs/{registry_path.name}"
        or seed_binding.get("allocation_status") != "unassigned"
        or seed_binding.get("assigned_seed_count") != 0
        or seed_binding.get("generation_requires_new_main_owned_registry_snapshot")
        is not True
    ):
        _fail("v3_request_seed_registry_binding_invalid")
    if registry.get("requested_allocation", {}).get("assigned_seed_values") != []:
        _fail("v3_request_registry_has_assigned_seeds")
    _require_all_false(_mapping(request.get("permissions"), "v3_request_permissions"))
    return {
        "request_id": request.get("request_id"),
        "status": request.get("status"),
        "requested_episode_count": total_episodes,
        "requested_unique_seed_count": dataset["requested_unique_seed_count"],
        "requested_cell_count": len(cells),
        "minimum_positive_frame_count": positive_minimum,
        "minimum_negative_frame_count": negative_minimum,
        "minimum_hard_negative_frame_count": hard_negative_minimum,
        "action_change_type_count": len(action_types),
        "hard_negative_type_count": len(hard_negatives),
        "observability_requirement_count": len(observability),
        "data_generated": False,
        "model_trained": False,
        "bundle_written": False,
        "generation_authorized": False,
        "all_permissions_false": True,
    }


def _write_frame_diagnostic_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    fields = (
        "source_split",
        "scenario_version",
        "configured_scale",
        "seed",
        "episode",
        "frame_index",
        "timestamp_s",
        "class_label",
        "candidate_availability_status",
        "observed_anonymous_target_count",
        "observed_anonymous_resource_count",
        "target_demand_slot_count",
        "teacher_binding_change_count",
        "candidate_teacher_symmetric_difference_count",
        "candidate_exact_teacher",
        "effective_exact_teacher",
        "ood",
        "rejected",
        "rejection_reasons",
        "exclusive_observable_failure_pathway",
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **{name: row[name] for name in fields if name != "rejection_reasons"},
                    "rejection_reasons": "|".join(row["rejection_reasons"]),
                }
            )


def _input_snapshot(inputs: A1FailureDiagnosticInputs) -> dict[str, str]:
    files: dict[str, Path] = {
        "contract": inputs.contract_path,
        "d6_audit": inputs.d6_audit_path,
        "main_report": inputs.main_report_path,
        "v3_data_request": inputs.data_request_path,
        "v3_seed_registry": inputs.seed_registry_path,
    }
    files.update(
        {f"result/{path.name}": path for path in sorted(inputs.result_dir.iterdir())}
    )
    files.update(
        {f"bundle/{path.name}": path for path in sorted(inputs.bundle_dir.iterdir())}
    )
    files.update(
        {
            f"d6_report/{path.name}": path
            for path in sorted(inputs.d6_audit_path.parent.iterdir())
        }
    )
    return {name: _sha256_file(_resolve_file(path, name)) for name, path in files.items()}


def _parse_checksums(
    path: Path,
    expected_names: Iterable[str] | Mapping[str, str],
) -> dict[str, str]:
    expected = set(expected_names)
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2 or _HEX_SHA256.fullmatch(parts[0]) is None:
            _fail("checksum_line_invalid", line)
        digest, name = parts
        if name in rows or Path(name).name != name:
            _fail("checksum_name_invalid", name)
        rows[name] = digest
    if set(rows) != expected:
        _fail("checksum_inventory_mismatch", repr(sorted(rows)))
    return rows


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise A1FailureDiagnosticError(f"{label}_json_invalid") from error
    if not isinstance(value, Mapping):
        _fail(f"{label}_root_invalid")
    return value


def _load_jsonl(path: Path, label: str) -> Iterable[Mapping[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                _fail(f"{label}_blank_line", str(line_number))
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise A1FailureDiagnosticError(
                    f"{label}_line_invalid", str(line_number)
                ) from error
            if not isinstance(value, Mapping):
                _fail(f"{label}_line_root_invalid", str(line_number))
            yield value


def _selected_edges(value: Mapping[str, Any], label: str) -> tuple[tuple[int, int], ...]:
    raw = value.get("selected_edges")
    if not isinstance(raw, list):
        _fail("selected_edges_invalid", label)
    output: list[tuple[int, int]] = []
    for item in raw:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or isinstance(item[0], bool)
            or isinstance(item[1], bool)
            or not isinstance(item[0], int)
            or not isinstance(item[1], int)
            or item[0] < 0
            or item[1] < 0
        ):
            _fail("selected_edge_invalid", label)
        output.append((item[0], item[1]))
    if len(output) != len(set(output)):
        _fail("selected_edge_duplicate", label)
    return tuple(output)


def _edge_symmetric_difference(left: Sequence[Any], right: Sequence[Any]) -> int:
    return len(
        {tuple(item) for item in left}.symmetric_difference(
            {tuple(item) for item in right}
        )
    )


def _find_forbidden_identity_keys(value: Any) -> tuple[str, ...]:
    found: list[str] = []

    def visit(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                key_text = str(key)
                normalized = re.sub(r"[^a-z0-9]", "", key_text.lower())
                child_path = f"{path}.{key_text}" if path else key_text
                if normalized in _FORBIDDEN_IDENTITY_KEYS or normalized.endswith(
                    _FORBIDDEN_IDENTITY_SUFFIXES
                ):
                    found.append(child_path)
                visit(child, child_path)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")

    visit(value, "")
    return tuple(found)


def _assert_finite(value: Any, label: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _assert_finite(child, f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_finite(child, f"{label}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        _fail("non_finite_value", label)


def _require_all_false(value: Mapping[str, Any]) -> None:
    if not value or any(item is not False for item in value.values()):
        _fail("permission_escalation_forbidden")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label}_invalid")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{label}_invalid")
    return int(value)


def _resolve_directory(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise A1FailureDiagnosticError(f"{label}_missing") from error
    if path.is_symlink() or not resolved.is_dir():
        _fail(f"{label}_directory_invalid")
    return resolved


def _resolve_file(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise A1FailureDiagnosticError(f"{label}_missing") from error
    if path.is_symlink() or not resolved.is_file():
        _fail(f"{label}_file_invalid")
    return resolved


def _relative_to_root(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _content_sha256(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("content_sha256", None)
    return _sha256_json(payload)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _fail(code: str, detail: str = "") -> None:
    raise A1FailureDiagnosticError(code, detail)
