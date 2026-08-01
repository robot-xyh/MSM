"""Cross-module pre-generation gate for scalable learning source data.

The main runtime owns this gate.  It combines the read-only D3, D4 and D5
readiness reports with the global seed registry, then separately assesses
whether the current scalable-3D producer can execute each frozen schedule.
It does not generate episodes, read held-out payloads, train models, or grant
runtime authority.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

from .global_seed_registry import (
    GlobalSeedRegistryError,
    load_global_seed_registry,
    validate_registry_source_contracts,
)
from .scenarios import AVAILABLE_SCENARIOS


LEARNING_SOURCE_PREFLIGHT_SCHEMA_VERSION = (
    "scalable3d-learning-source-preflight-v1"
)
LEARNING_SOURCE_PREFLIGHT_REPORT_FILENAME = "learning_source_preflight.json"
LEARNING_SOURCE_PREFLIGHT_MARKDOWN_FILENAME = (
    "LEARNING_SOURCE_PREFLIGHT_CN.md"
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GLOBAL_SEED_REGISTRY_PATH = (
    REPOSITORY_ROOT
    / "research_modules/scalable_3d_simulation/configs/"
    "scalable_learning_global_seed_registry_v1.json"
)
D3_SCHEDULE_PATH = (
    REPOSITORY_ROOT
    / "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_generation_schedule_v1.json"
)
D4_SEED_REGISTRY_PATH = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/reports/"
    "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801/"
    "v8_development_seed_registry.json"
)

_FALSE_PERMISSIONS = {
    "generation": False,
    "training": False,
    "validation": False,
    "test": False,
    "optimizer": False,
    "checkpoint_selection": False,
    "threshold_adjustment": False,
    "shadow": False,
    "assist": False,
    "promotion": False,
    "runtime": False,
    "assignment": False,
    "degradation": False,
    "coalition": False,
    "control": False,
    "physical": False,
    "production": False,
    "global_track_id_create": False,
    "global_track_id_write": False,
}


class LearningSourcePreflightError(ValueError):
    """Stable fail-closed error from the main source-data boundary."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = str(code)
        detail = str(message).strip()
        super().__init__(f"{self.code}: {detail}" if detail else self.code)


def evaluate_learning_source_preflight(
    *,
    repository_root: str | Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Evaluate all frozen source plans without generating or training."""

    root = Path(repository_root).expanduser().resolve()
    if not root.is_dir():
        raise LearningSourcePreflightError(
            "repository_root_invalid", str(root)
        )

    registry_path = root / GLOBAL_SEED_REGISTRY_PATH.relative_to(REPOSITORY_ROOT)
    try:
        registry = load_global_seed_registry(registry_path)
        source_audit = validate_registry_source_contracts(
            registry,
            repository_root=root,
        )
    except GlobalSeedRegistryError as exc:
        raise LearningSourcePreflightError(
            f"global_seed_registry_{exc.code}", str(exc)
        ) from exc

    d3_report, d4_report, d5_report = _load_module_readiness(root)
    producer = {
        "D3": _assess_d3_producer(root, d3_report),
        "D4": _assess_d4_producer(root, d4_report),
        "D5": _assess_d5_producer(d5_report),
    }
    source_state = _source_state(root)
    return assemble_learning_source_preflight(
        registry={
            "registry_id": registry.registry_id,
            "policy_version": registry.policy_version,
            "content_sha256": registry.content_sha256,
            "file_sha256": _file_sha256(registry_path),
            "protected_seed_count": len(registry.protected_seeds),
            "allocation_count": len(registry.allocations),
            "allocated_seed_count": sum(
                len(allocation.seeds)
                for allocation in registry.allocations.values()
            ),
            "unallocated_request_count": len(registry.unallocated_requests),
            "source_contract_audit": source_audit,
        },
        module_reports={"D3": d3_report, "D4": d4_report, "D5": d5_report},
        producer_assessments=producer,
        source_state=source_state,
    )


def assemble_learning_source_preflight(
    *,
    registry: Mapping[str, Any],
    module_reports: Mapping[str, Mapping[str, Any]],
    producer_assessments: Mapping[str, Mapping[str, Any]],
    source_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Assemble a deterministic, authority-free preflight result."""

    expected_modules = ("D3", "D4", "D5")
    if tuple(sorted(module_reports)) != expected_modules:
        raise LearningSourcePreflightError("module_report_set_invalid")
    if tuple(sorted(producer_assessments)) != expected_modules:
        raise LearningSourcePreflightError("producer_assessment_set_invalid")

    module_plan_ready = {
        "D3": _required_bool(module_reports["D3"], "ready", "D3"),
        "D4": _required_bool(
            module_reports["D4"], "generation_prerequisites_ready", "D4"
        ),
        "D5": _required_bool(module_reports["D5"], "plan_ready", "D5"),
    }
    producer_ready = {
        module: _required_bool(
            producer_assessments[module], "producer_adapter_complete", module
        )
        for module in expected_modules
    }
    request_ready = {
        module: _required_bool(
            producer_assessments[module], "source_generation_request_ready", module
        )
        for module in expected_modules
    }
    for module in expected_modules:
        if request_ready[module] and not (
            module_plan_ready[module] and producer_ready[module]
        ):
            raise LearningSourcePreflightError(
                "generation_request_inconsistent", module
            )

    repository_dirty = _required_bool(
        source_state, "repository_dirty", "main_source_state"
    )
    source_worktree_clean = not repository_dirty
    all_module_plans_ready = all(module_plan_ready.values())
    all_producer_adapters_complete = all(producer_ready.values())
    all_generation_requests_ready = all(request_ready.values())
    execution_plan_ready = bool(
        all_module_plans_ready
        and all_producer_adapters_complete
        and all_generation_requests_ready
        and source_worktree_clean
    )

    blockers: list[str] = []
    for module in expected_modules:
        if not module_plan_ready[module]:
            blockers.append(f"{module.lower()}_module_plan_not_ready")
        for blocker in producer_assessments[module].get("blockers", ()):
            code = str(blocker).strip()
            if code and code not in blockers:
                blockers.append(code)
        if not request_ready[module]:
            code = f"{module.lower()}_source_generation_request_not_ready"
            if code not in blockers:
                blockers.append(code)
    if not source_worktree_clean:
        blockers.append("generation_worktree_dirty")

    if execution_plan_ready:
        status = "ready_for_explicit_main_execution_authorization"
    elif (
        all_module_plans_ready
        and all_producer_adapters_complete
        and all_generation_requests_ready
    ):
        status = "blocked_by_dirty_generation_worktree"
    else:
        status = "blocked_by_producer_adapter_or_module_readiness"
    return {
        "schema_version": LEARNING_SOURCE_PREFLIGHT_SCHEMA_VERSION,
        "status": status,
        "plan_only": True,
        "all_module_plans_ready": all_module_plans_ready,
        "all_producer_adapters_complete": all_producer_adapters_complete,
        "all_generation_requests_ready": all_generation_requests_ready,
        "source_worktree_clean": source_worktree_clean,
        "execution_plan_ready": execution_plan_ready,
        "execution_authorized": False,
        "generation_started": False,
        "training_started": False,
        "formal_seed_payload_read": False,
        "formal_shards_10_19_run": False,
        "existing_formal_450_of_900_conclusion_modified": False,
        "registry": dict(registry),
        "source_state": dict(source_state),
        "modules": {
            module: {
                "module_plan_ready": module_plan_ready[module],
                "producer_adapter_complete": producer_ready[module],
                "source_generation_request_ready": request_ready[module],
                "readiness": dict(module_reports[module]),
                "producer": dict(producer_assessments[module]),
            }
            for module in expected_modules
        },
        "generation_commands": [],
        "blockers": blockers,
        "permissions": dict(_FALSE_PERMISSIONS),
    }


def write_learning_source_preflight_report(
    report: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write JSON and Chinese Markdown without touching source artifacts."""

    if report.get("schema_version") != LEARNING_SOURCE_PREFLIGHT_SCHEMA_VERSION:
        raise ValueError("unexpected learning source preflight schema")
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / LEARNING_SOURCE_PREFLIGHT_REPORT_FILENAME
    markdown_path = root / LEARNING_SOURCE_PREFLIGHT_MARKDOWN_FILENAME
    json_path.write_text(
        json.dumps(
            dict(report),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_learning_source_preflight_markdown(report),
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": markdown_path}


def render_learning_source_preflight_markdown(
    report: Mapping[str, Any],
) -> str:
    """Render the current cross-module readiness decision in Chinese."""

    lines = [
        "# 可扩展三维学习来源预生成检查",
        "",
        "## 结论",
        "",
        (
            f"当前状态为 `{report['status']}`。D3、D4、D5 模块计划完整性为 "
            f"`{_yes_no(report['all_module_plans_ready'])}`，生产器适配完整性为 "
            f"`{_yes_no(report['all_producer_adapters_complete'])}`，生成工作树干净状态为 "
            f"`{_yes_no(report['source_worktree_clean'])}`。"
        ),
        (
            "本检查不授予生成、训练、运行或控制权限。执行命令保持为空，正式种子 "
            "1000--1019 未读取，既有正式 450/900 结论未修改。"
        ),
        "",
        "## 模块状态",
        "",
        "| 模块 | 计划 | 生产器适配 | 生成请求 |",
        "| --- | :---: | :---: | :---: |",
    ]
    for module in ("D3", "D4", "D5"):
        item = report["modules"][module]
        lines.append(
            "| "
            f"{module} | {_yes_no(item['module_plan_ready'])} | "
            f"{_yes_no(item['producer_adapter_complete'])} | "
            f"{_yes_no(item['source_generation_request_ready'])} |"
        )
    lines.extend(["", "## 阻断项", ""])
    blockers = list(report.get("blockers", ()))
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- 无。仍需 main 显式授权后才能执行。")
    lines.extend(
        [
            "",
            "## 执行边界",
            "",
            "- D3、D4、D5 的种子集合保持互斥，并继续受全局登记表约束。",
            "- 模块计划通过只表示元数据完整，不表示 producer 已能形成所需样本。",
            "- 即使全部 adapter 就绪，存在未提交改动时仍不得形成可执行生成计划。",
            "- 生产器适配完成后须由模块 owner 复核 readiness，再由 main 重新生成本报告。",
            "- 本阶段没有生成 episode、样本、模型或正式评价结果。",
        ]
    )
    return "\n".join(lines) + "\n"


def _load_module_readiness(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    d3_src = root / "research_modules/d3_assignment_planner/src"
    d5_src = root / "research_modules/d5_terminal_association/src"
    for source in (d3_src, d5_src):
        value = str(source)
        if value not in sys.path:
            sys.path.insert(0, value)

    from d3_assignment_planner.a1_v3_data_contract import (  # noqa: PLC0415
        validate_a1_v3_pre_generation_readiness,
    )
    from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v8_main_allocation_readiness import (  # noqa: E501, PLC0415
        validate_v8_main_allocation_pre_generation_readiness,
    )
    from d5_terminal_association.active_vision_a3_v3_source_readiness import (  # noqa: E501, PLC0415
        validate_a3_v3_pre_generation_readiness,
    )

    d3 = validate_a1_v3_pre_generation_readiness(
        request_path=(
            root
            / "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_development_data_request_v1.json"
        ),
        exclusion_registry_path=(
            root
            / "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_seed_exclusion_registry_v1.json"
        ),
        contract_path=(
            root
            / "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_data_contract_v1.json"
        ),
        generator_config_path=(
            root
            / "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_generator_config_v1.json"
        ),
        global_registry_path=(
            root
            / "research_modules/scalable_3d_simulation/configs/"
            "scalable_learning_global_seed_registry_v1.json"
        ),
        registry_path=(
            root
            / "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_main_allocation_registry_v1.json"
        ),
        schedule_path=(
            root
            / "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_generation_schedule_v1.json"
        ),
    ).to_dict()
    d4 = validate_v8_main_allocation_pre_generation_readiness(
        repository_root=root
    ).to_dict()
    d5 = validate_a3_v3_pre_generation_readiness(
        repository_root=root,
        protocol_path=(
            root
            / "research_modules/d5_terminal_association/configs/"
            "a3_v3_minority_intent_protocol_20260801.json"
        ),
        allocation_binding_path=(
            root
            / "research_modules/d5_terminal_association/configs/"
            "a3_v3_global_seed_allocation_binding_20260801.json"
        ),
        source_schedule_path=(
            root
            / "research_modules/d5_terminal_association/configs/"
            "a3_v3_source_collection_schedule_20260801.json"
        ),
        global_registry_path=(
            root
            / "research_modules/scalable_3d_simulation/configs/"
            "scalable_learning_global_seed_registry_v1.json"
        ),
    ).to_dict()
    return d3, d4, d5


def _assess_d3_producer(
    root: Path, report: Mapping[str, Any]
) -> dict[str, Any]:
    schedule_path = root / D3_SCHEDULE_PATH.relative_to(REPOSITORY_ROOT)
    payload = json.loads(schedule_path.read_text(encoding="utf-8"))
    episodes = payload.get("episodes", ())
    scenario_families = sorted(
        {str(item["scenario_family"]) for item in episodes}
    )
    unsupported = sorted(set(scenario_families) - set(AVAILABLE_SCENARIOS))
    unequal_count = sum(
        int(item["configured_target_count"])
        != int(item["configured_resource_count"])
        for item in episodes
    )
    blockers = [
        "d3_schedule_schema_not_supported_by_run_learning_dataset",
        "d3_per_episode_target_resource_counts_not_mapped",
        "d3_a1_v3_online_offline_writer_not_bound",
    ]
    if unsupported:
        blockers.append("d3_scenario_family_mapping_incomplete")
    return {
        "producer_adapter_complete": False,
        "source_generation_request_ready": False,
        "module_plan_ready": bool(report.get("ready")),
        "planned_episode_count": len(episodes),
        "schedule_schema_version": payload.get("schema_version"),
        "schedule_file_sha256": _file_sha256(schedule_path),
        "scenario_families": scenario_families,
        "unsupported_scenario_families": unsupported,
        "unequal_target_resource_episode_count": unequal_count,
        "blockers": blockers,
    }


def _assess_d4_producer(
    root: Path, report: Mapping[str, Any]
) -> dict[str, Any]:
    schedule_path = root / D4_SEED_REGISTRY_PATH.relative_to(REPOSITORY_ROOT)
    payload = json.loads(schedule_path.read_text(encoding="utf-8"))
    schedule = payload.get("schedule", ())
    return {
        "producer_adapter_complete": False,
        "source_generation_request_ready": False,
        "module_plan_ready": bool(report.get("generation_prerequisites_ready")),
        "planned_episode_count": len(schedule),
        "schedule_schema_version": payload.get("schema"),
        "schedule_file_sha256": _file_sha256(schedule_path),
        "region_counts": sorted({int(item["region_count"]) for item in schedule}),
        "topology_ids": sorted({str(item["topology_id"]) for item in schedule}),
        "blockers": [
            "d4_v8_schedule_schema_not_supported_by_run_learning_dataset",
            "d4_region_topology_and_communication_treatment_not_mapped",
            "d4_transfer_class_and_hard_negative_treatment_not_mapped",
            "d4_v8_online_offline_writer_not_bound",
        ],
    }


def _assess_d5_producer(report: Mapping[str, Any]) -> dict[str, Any]:
    capability = report.get("producer_capability")
    if not isinstance(capability, Mapping):
        raise LearningSourcePreflightError("d5_producer_capability_missing")
    return {
        "producer_adapter_complete": bool(
            capability.get("producer_adapter_complete")
        ),
        "source_generation_request_ready": bool(
            capability.get("source_generation_request_ready")
        ),
        "module_plan_ready": bool(report.get("plan_ready")),
        "planned_episode_count": int(
            report.get("source_schedule", {}).get("planned_episode_count", 0)
        ),
        "entry_field_support": dict(capability.get("entry_field_support", {})),
        "recipe_support": dict(capability.get("recipe_support", {})),
        "blockers": list(capability.get("blockers", ())),
    }


def _source_state(root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise LearningSourcePreflightError("git_source_state_unavailable") from exc
    return {
        "git_commit": commit,
        "repository_dirty": bool(status.strip()),
        "clean_generation_worktree_required": True,
    }


def _required_bool(
    payload: Mapping[str, Any], field: str, module: str
) -> bool:
    value = payload.get(field)
    if type(value) is not bool:
        raise LearningSourcePreflightError(
            "module_readiness_boolean_missing", f"{module}.{field}"
        )
    return value


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _yes_no(value: Any) -> str:
    return "是" if value is True else "否"
