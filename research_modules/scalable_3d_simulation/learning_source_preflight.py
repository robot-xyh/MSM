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
from .learning_source_adapters import (
    LearningSourceAdapterError,
    self_check_d3_a1_adapter,
    self_check_d4_v8_adapter,
    self_check_d5_a3_adapter,
)


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
D3_SOURCE_GENERATION_REQUEST_PATH = (
    REPOSITORY_ROOT
    / "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_source_generation_request_readiness_v1.json"
)
D4_SOURCE_GENERATION_REQUEST_PATH = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/configs/"
    "region_resource_v8_train_source_generation_request_readiness_v1.json"
)
D5_SOURCE_GENERATION_REQUEST_PATH = (
    REPOSITORY_ROOT
    / "research_modules/d5_terminal_association/configs/"
    "a3_v3_source_generation_request_20260801.json"
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
        "D5": _assess_d5_producer(root, d5_report),
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
    elif all_module_plans_ready and all_producer_adapters_complete:
        status = (
            "blocked_by_source_generation_request"
            if source_worktree_clean
            else "blocked_by_source_generation_request_and_dirty_worktree"
        )
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
        "| 模块 | 冻结计划 | 生产器适配 | 内存 probe | 生成请求 |",
        "| --- | :---: | :---: | ---: | :---: |",
    ]
    for module in ("D3", "D4", "D5"):
        item = report["modules"][module]
        probe = item["producer"].get("adapter_self_check") or {}
        lines.append(
            "| "
            f"{module} | {_yes_no(item['module_plan_ready'])} | "
            f"{_yes_no(item['producer_adapter_complete'])} | "
            f"{int(probe.get('runtime_probe_episode_count', 0))} episode / "
            f"{int(probe.get('runtime_probe_frame_count', 0))} 帧 | "
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
            "- 三个 adapter 已通过冻结日程映射和受控内存 probe；probe 不等同于正式来源清单。",
            (
                "- 三个模块生成请求已通过独立路径和 SHA-256 核对；"
                "请求就绪不等同于 main 执行授权。"
                if report["all_generation_requests_ready"]
                else "- 至少一个模块生成请求尚未就绪，因此不能进入 main 执行授权。"
            ),
            "- 即使后续请求获批，存在未提交改动时仍不得形成可执行生成计划。",
            "- 本阶段没有生成 300/324/104 episode 清单、样本、模型或正式评价结果。",
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
    unequal_count = sum(
        int(item["configured_target_count"])
        != int(item["configured_resource_count"])
        for item in episodes
    )
    self_check, blockers = _run_adapter_self_check(
        "D3", lambda: self_check_d3_a1_adapter(root)
    )
    request = _validated_module_generation_request(
        root,
        "D3",
        report,
        D3_SOURCE_GENERATION_REQUEST_PATH.relative_to(REPOSITORY_ROOT),
    )
    blockers.extend(item for item in request["blockers"] if item not in blockers)
    adapter_complete = self_check is not None
    return {
        "producer_adapter_complete": adapter_complete,
        "source_generation_request_ready": request["ready"],
        "source_generation_request_path": request["path"],
        "source_generation_request_sha256": request["sha256"],
        "module_plan_ready": bool(report.get("ready")),
        "planned_episode_count": len(episodes),
        "schedule_schema_version": payload.get("schema_version"),
        "schedule_file_sha256": _file_sha256(schedule_path),
        "scenario_families": scenario_families,
        "unsupported_scenario_families": [],
        "unequal_target_resource_episode_count": unequal_count,
        "adapter_self_check": self_check,
        "blockers": blockers,
    }


def _assess_d4_producer(
    root: Path, report: Mapping[str, Any]
) -> dict[str, Any]:
    schedule_path = root / D4_SEED_REGISTRY_PATH.relative_to(REPOSITORY_ROOT)
    payload = json.loads(schedule_path.read_text(encoding="utf-8"))
    schedule = payload.get("schedule", ())
    self_check, blockers = _run_adapter_self_check(
        "D4", lambda: self_check_d4_v8_adapter(root)
    )
    request = _validated_module_generation_request(
        root,
        "D4",
        report,
        D4_SOURCE_GENERATION_REQUEST_PATH.relative_to(REPOSITORY_ROOT),
    )
    blockers.extend(item for item in request["blockers"] if item not in blockers)
    return {
        "producer_adapter_complete": self_check is not None,
        "source_generation_request_ready": request["ready"],
        "source_generation_request_path": request["path"],
        "source_generation_request_sha256": request["sha256"],
        "module_plan_ready": bool(report.get("generation_prerequisites_ready")),
        "planned_episode_count": len(schedule),
        "schedule_schema_version": payload.get("schema"),
        "schedule_file_sha256": _file_sha256(schedule_path),
        "region_counts": sorted({int(item["region_count"]) for item in schedule}),
        "topology_ids": sorted({str(item["topology_id"]) for item in schedule}),
        "adapter_self_check": self_check,
        "blockers": blockers,
    }


def _assess_d5_producer(
    root: Path,
    report: Mapping[str, Any],
) -> dict[str, Any]:
    capability = report.get("producer_capability")
    if not isinstance(capability, Mapping):
        raise LearningSourcePreflightError("d5_producer_capability_missing")
    self_check, self_check_blockers = _run_adapter_self_check(
        "D5", lambda: self_check_d5_a3_adapter(root)
    )
    declared_complete = bool(capability.get("producer_adapter_complete"))
    blockers = list(capability.get("blockers", ()))
    blockers.extend(
        item for item in self_check_blockers if item not in blockers
    )
    request = _validated_module_generation_request(
        root,
        "D5",
        report,
        D5_SOURCE_GENERATION_REQUEST_PATH.relative_to(REPOSITORY_ROOT),
    )
    blockers.extend(item for item in request["blockers"] if item not in blockers)
    return {
        "producer_adapter_complete": bool(
            declared_complete and self_check is not None
        ),
        "source_generation_request_ready": request["ready"],
        "source_generation_request_path": request["path"],
        "source_generation_request_sha256": request["sha256"],
        "module_plan_ready": bool(report.get("plan_ready")),
        "planned_episode_count": int(
            report.get("source_schedule", {}).get("planned_episode_count", 0)
        ),
        "entry_field_support": dict(capability.get("entry_field_support", {})),
        "recipe_support": dict(capability.get("recipe_support", {})),
        "module_declared_source_generation_request_ready": bool(
            report.get("source_generation_request_ready")
        ),
        "adapter_self_check": self_check,
        "blockers": blockers,
    }


def _validated_module_generation_request(
    root: Path,
    module: str,
    report: Mapping[str, Any],
    expected_relative_path: Path,
) -> dict[str, Any]:
    """Independently bind one module-ready request to exact repository bytes."""

    declared_ready = _required_bool(
        report, "source_generation_request_ready", module
    )
    declared_path = report.get("source_generation_request_path")
    declared_sha = report.get("source_generation_request_sha256")
    logical_path = expected_relative_path.as_posix()
    if not declared_ready:
        return {
            "ready": False,
            "path": None if declared_path is None else str(declared_path),
            "sha256": None if declared_sha is None else str(declared_sha),
            "blockers": [f"{module.lower()}_source_generation_request_not_ready"],
        }
    if str(declared_path) != logical_path:
        raise LearningSourcePreflightError(
            "source_generation_request_path_mismatch", module
        )
    if (
        not isinstance(declared_sha, str)
        or len(declared_sha) != 64
        or any(character not in "0123456789abcdef" for character in declared_sha)
    ):
        raise LearningSourcePreflightError(
            "source_generation_request_sha256_invalid", module
        )
    candidate = root / expected_relative_path
    if candidate.is_symlink():
        raise LearningSourcePreflightError(
            "source_generation_request_symlink_forbidden", module
        )
    try:
        source = candidate.resolve(strict=True)
        source.relative_to(root)
    except (OSError, ValueError) as exc:
        raise LearningSourcePreflightError(
            "source_generation_request_file_unavailable", module
        ) from exc
    if not source.is_file() or _file_sha256(source) != declared_sha:
        raise LearningSourcePreflightError(
            "source_generation_request_sha256_mismatch", module
        )
    return {
        "ready": True,
        "path": logical_path,
        "sha256": declared_sha,
        "blockers": [],
    }


def _run_adapter_self_check(
    module: str,
    check: Any,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Convert any adapter failure into one stable fail-closed blocker."""

    try:
        result = check()
    except (LearningSourceAdapterError, OSError, TypeError, ValueError) as exc:
        return None, [
            f"{module.lower()}_producer_adapter_self_check_failed:"
            f"{type(exc).__name__}:{exc}"
        ]
    if (
        not isinstance(result, Mapping)
        or result.get("status") != "pass_authority_free_in_memory_smoke"
        or result.get("module") != module
        or result.get("online_truth_use_count") != 0
        or result.get("formal_inventory_generated") is not False
        or result.get("source_payload_written") is not False
        or result.get("training_started") is not False
        or result.get("runtime_authority_granted") is not False
    ):
        return None, [f"{module.lower()}_producer_adapter_self_check_invalid"]
    return dict(result), []


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
