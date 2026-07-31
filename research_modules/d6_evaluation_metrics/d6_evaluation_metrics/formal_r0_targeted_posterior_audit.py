"""Independent targeted audit for formal R0 posterior-generation evidence.

The audit reads the frozen execution plan, shard ledgers, cell results, and
episode artifacts.  It does not read the producer-side ``targeted_formal_d6``
aggregate or ``observation_governance_audit.json``.  D1/D2 generation evidence
is recomputed by the D6 offline evaluator from ``online_observations.jsonl``
and ``summary.json``.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from .formal_r0_plan_binding_audit import (
    audit_formal_r0_plan_binding_episode,
    formal_r0_plan_binding_row_metrics,
)
from .scalable_3d_offline import evaluate_scalable_3d_episode
from .strict_offline_identity import strict_id_switch_provenance_is_verified


FORMAL_R0_TARGETED_POSTERIOR_INPUT_SCHEMA_VERSION = (
    "d6.formal-r0-targeted-posterior-audit-input.v1"
)
FORMAL_R0_TARGETED_POSTERIOR_AUDIT_SCHEMA_VERSION = (
    "d6.formal-r0-targeted-posterior-audit.v2"
)
FORMAL_R0_TARGETED_POSTERIOR_AUDIT_DATE = "2026-07-30"

_EXECUTION_PLAN_SCHEMA = "scalable3d-experiment-matrix-execution-plan-v1"
_SHARD_PLAN_SCHEMA = "scalable3d-experiment-matrix-shard-plan-v1"
_SHARD_CHECKPOINT_SCHEMA = "scalable3d-experiment-matrix-shard-checkpoint-v1"
_SHARD_PROGRESS_SCHEMA = "scalable3d-experiment-matrix-shard-progress-v1"
_CELL_RESULT_SCHEMA = "scalable3d-experiment-matrix-cell-result-v1"
_REQUIRED_EPISODE_ARTIFACTS = (
    "manifest.json",
    "scenario_config.json",
    "summary.json",
    "online_observations.jsonl",
    "offline_proximity_intercepts.jsonl",
    "stage_timings.csv",
)
_HEX64 = frozenset("0123456789abcdef")
_POSTERIOR_AUDIT_LOW_LEVEL_EVIDENCE_FIELDS = (
    "online_truth_use_count",
    "online_truth_field_violation_count",
    "finite_state",
    "formal_acceptance_eligible",
    "experiment_matrix_formal_acceptance_eligible",
    "d1_posterior_generation",
    "d1_full_posterior_publication_count",
    "d2_consumed_d1_posterior_generation",
    "d2_posterior_consumption_count",
    "d2_association_publication_count",
    "d2_pre_tick_posterior_merge_count",
    "d2_finalize_unchanged_posterior_skip_count",
    "d2_pending_generation_empty",
    "observation_governance_generation_integrity",
    "observation_governance_generation_contract_status",
    "d2_id_switch_count",
    "d2_online_producer_id_switch_count",
    "d4_advice_resource_quota_conservation_violation_count",
    "d4_advice_formal_decision_mutation_count",
    "d5_active_vision_target_reference_violation_count",
    "d5_active_vision_ack_target_mismatch_count",
)


class FormalR0TargetedPosteriorAuditError(ValueError):
    """Raised when the explicit audit request itself is malformed."""


@dataclass(frozen=True)
class FormalR0TargetCell:
    """One explicitly selected formal R0 cell."""

    shard_index: int
    cell_id: str

    def __post_init__(self) -> None:
        if int(self.shard_index) < 0:
            raise FormalR0TargetedPosteriorAuditError(
                "target shard_index must be nonnegative"
            )
        if not str(self.cell_id).strip():
            raise FormalR0TargetedPosteriorAuditError(
                "target cell_id must be nonempty"
            )


@dataclass(frozen=True)
class FormalR0TargetedPosteriorAuditInputs:
    """Frozen provenance, progress, and five-cell audit request."""

    execution_root: Path
    source_repository: Path
    expected_source_git_commit: str
    expected_execution_plan_sha256: str
    expected_scope_cell_count: int
    expected_completed_cell_count: int
    expected_shard_progress: tuple[tuple[int, int], ...]
    targets: tuple[FormalR0TargetCell, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "execution_root",
            Path(self.execution_root).resolve(),
        )
        object.__setattr__(
            self,
            "source_repository",
            Path(self.source_repository).resolve(),
        )
        if not _is_hex_digest(self.expected_source_git_commit, 40):
            raise FormalR0TargetedPosteriorAuditError(
                "expected_source_git_commit must be a lowercase SHA-256-like Git id"
            )
        if not _is_hex_digest(self.expected_execution_plan_sha256, 64):
            raise FormalR0TargetedPosteriorAuditError(
                "expected_execution_plan_sha256 must be lowercase SHA-256"
            )
        if int(self.expected_scope_cell_count) <= 0:
            raise FormalR0TargetedPosteriorAuditError(
                "expected_scope_cell_count must be positive"
            )
        if not 0 < int(self.expected_completed_cell_count) <= int(
            self.expected_scope_cell_count
        ):
            raise FormalR0TargetedPosteriorAuditError(
                "expected_completed_cell_count must be within the formal scope"
            )
        progress = tuple(
            (int(shard_index), int(completed))
            for shard_index, completed in self.expected_shard_progress
        )
        if not progress:
            raise FormalR0TargetedPosteriorAuditError(
                "expected_shard_progress must not be empty"
            )
        if len({item[0] for item in progress}) != len(progress):
            raise FormalR0TargetedPosteriorAuditError(
                "expected_shard_progress contains duplicate shard indices"
            )
        if any(shard < 0 or completed <= 0 for shard, completed in progress):
            raise FormalR0TargetedPosteriorAuditError(
                "shard indices must be nonnegative and completed counts positive"
            )
        if sum(item[1] for item in progress) != int(
            self.expected_completed_cell_count
        ):
            raise FormalR0TargetedPosteriorAuditError(
                "expected shard counts do not sum to expected completed count"
            )
        object.__setattr__(self, "expected_shard_progress", tuple(sorted(progress)))
        targets = tuple(self.targets)
        if not targets:
            raise FormalR0TargetedPosteriorAuditError(
                "at least one target cell is required"
            )
        target_keys = {(item.shard_index, item.cell_id) for item in targets}
        if len(target_keys) != len(targets):
            raise FormalR0TargetedPosteriorAuditError(
                "target cell list contains duplicates"
            )
        progress_shards = {item[0] for item in progress}
        if any(item.shard_index not in progress_shards for item in targets):
            raise FormalR0TargetedPosteriorAuditError(
                "every target shard must be present in expected_shard_progress"
            )


def load_formal_r0_targeted_posterior_audit_inputs(
    path: str | Path,
) -> FormalR0TargetedPosteriorAuditInputs:
    """Load one explicit, fail-closed targeted audit request."""

    config_path = Path(path).resolve()
    payload = _read_json_object(config_path)
    if payload.get("schema_version") != (
        FORMAL_R0_TARGETED_POSTERIOR_INPUT_SCHEMA_VERSION
    ):
        raise FormalR0TargetedPosteriorAuditError(
            "targeted posterior input schema is unsupported"
        )
    raw_progress = payload.get("expected_shard_progress")
    if not isinstance(raw_progress, Mapping):
        raise FormalR0TargetedPosteriorAuditError(
            "expected_shard_progress must be an object"
        )
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list):
        raise FormalR0TargetedPosteriorAuditError(
            "targets must be a list"
        )
    targets: list[FormalR0TargetCell] = []
    for index, raw in enumerate(raw_targets):
        if not isinstance(raw, Mapping):
            raise FormalR0TargetedPosteriorAuditError(
                f"target {index} must be an object"
            )
        try:
            targets.append(
                FormalR0TargetCell(
                    shard_index=int(raw["shard_index"]),
                    cell_id=str(raw["cell_id"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FormalR0TargetedPosteriorAuditError(
                f"target {index} is malformed"
            ) from exc
    try:
        return FormalR0TargetedPosteriorAuditInputs(
            execution_root=Path(str(payload["execution_root"])),
            source_repository=Path(str(payload["source_repository"])),
            expected_source_git_commit=str(
                payload["expected_source_git_commit"]
            ),
            expected_execution_plan_sha256=str(
                payload["expected_execution_plan_sha256"]
            ),
            expected_scope_cell_count=int(
                payload["expected_scope_cell_count"]
            ),
            expected_completed_cell_count=int(
                payload["expected_completed_cell_count"]
            ),
            expected_shard_progress=tuple(
                (int(key), int(value))
                for key, value in raw_progress.items()
            ),
            targets=tuple(targets),
        )
    except KeyError as exc:
        raise FormalR0TargetedPosteriorAuditError(
            f"required input field missing: {exc.args[0]}"
        ) from exc


def audit_formal_r0_targeted_posterior(
    inputs: FormalR0TargetedPosteriorAuditInputs,
) -> dict[str, Any]:
    """Independently recompute formal and D1/D2 generation evidence."""

    execution_root = inputs.execution_root
    plan_path = execution_root / "experiment_matrix_execution_plan.json"
    plan_file_checksum_path = execution_root / "EXECUTION_PLAN_SHA256"

    global_reasons: list[str] = []
    plan: Mapping[str, Any] | None
    try:
        plan = _read_json_object(plan_path)
    except (OSError, FormalR0TargetedPosteriorAuditError) as exc:
        plan = None
        global_reasons.append(f"execution_plan_unreadable:{exc}")

    plan_audit = _audit_execution_plan(
        plan,
        plan_path=plan_path,
        checksum_path=plan_file_checksum_path,
        inputs=inputs,
    )
    global_reasons.extend(plan_audit["failure_reasons"])

    source_audit = _audit_source_repository(inputs)
    global_reasons.extend(source_audit["failure_reasons"])

    progress_audit = _audit_execution_progress(plan, inputs)
    global_reasons.extend(progress_audit["failure_reasons"])

    target_rows = [
        _audit_target_cell(
            target,
            inputs=inputs,
            plan=plan,
            global_failure_reasons=global_reasons,
        )
        for target in inputs.targets
    ]
    aggregate = aggregate_formal_r0_targeted_posterior_rows(
        target_rows,
        expected_scope_cell_count=inputs.expected_scope_cell_count,
        expected_completed_cell_count=inputs.expected_completed_cell_count,
        expected_shard_progress=inputs.expected_shard_progress,
    )
    all_reasons = list(
        dict.fromkeys(
            [
                *global_reasons,
                *(
                    reason
                    for row in target_rows
                    for reason in row["failure_reasons"]
                ),
            ]
        )
    )
    verdict = (
        "pass"
        if not all_reasons
        and aggregate["verified_target_cell_count"] == len(target_rows)
        else "fail_closed"
    )
    return {
        "schema_version": FORMAL_R0_TARGETED_POSTERIOR_AUDIT_SCHEMA_VERSION,
        "evaluation_date": FORMAL_R0_TARGETED_POSTERIOR_AUDIT_DATE,
        "verdict": verdict,
        "fail_closed": verdict != "pass",
        "scope_boundary": {
            "formal_r0_execution_progress": (
                f"{inputs.expected_completed_cell_count}/"
                f"{inputs.expected_scope_cell_count}"
            ),
            "targeted_d6_audited_cell_count": len(target_rows),
            "targeted_d6_audit_denominator": len(target_rows),
            "full_completed_scope_d6_audited": False,
            "formal_r0_scope_complete": False,
            "prohibited_claims": (
                f"{inputs.expected_completed_cell_count}/"
                f"{inputs.expected_completed_cell_count}",
                f"{inputs.expected_scope_cell_count}/"
                f"{inputs.expected_scope_cell_count}",
                "complete R0 scope audited",
            ),
        },
        "inputs": {
            "execution_root": str(inputs.execution_root),
            "source_repository": str(inputs.source_repository),
            "expected_source_git_commit": inputs.expected_source_git_commit,
            "expected_execution_plan_sha256": (
                inputs.expected_execution_plan_sha256
            ),
            "ignored_producer_aggregates": (
                "targeted_formal_d6",
                "episode/observation_governance_audit.json",
            ),
            "generation_recompute_inputs": (
                "episode/online_observations.jsonl",
                "episode/summary.json",
            ),
            "current_plan_binding_inputs": (
                "episode/online_observations.jsonl",
                "episode/communication_dispositions.jsonl (optional)",
            ),
        },
        "source": source_audit,
        "execution_plan": plan_audit,
        "execution_progress": progress_audit,
        "aggregate": aggregate,
        "failure_reasons": all_reasons,
        "cells": target_rows,
    }


def aggregate_formal_r0_targeted_posterior_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_scope_cell_count: int,
    expected_completed_cell_count: int,
    expected_shard_progress: Sequence[tuple[int, int]],
) -> dict[str, Any]:
    """Aggregate five-cell evidence without substituting progress as a denominator."""

    row_count = len(rows)
    verified = sum(row.get("verified") is True for row in rows)
    clean_formal = sum(
        row.get("formal_acceptance_eligible") is True for row in rows
    )
    matrix_formal = sum(
        row.get("experiment_matrix_formal_acceptance_eligible") is True
        for row in rows
    )
    generation_verified = sum(
        row.get("observation_governance_generation_integrity") is True
        and row.get("observation_governance_generation_contract_status")
        == "verified"
        for row in rows
    )
    return {
        "targeted_audit_cell_count": row_count,
        "targeted_audit_denominator": row_count,
        "verified_target_cell_count": verified,
        "failed_closed_target_cell_count": row_count - verified,
        "clean_formal_target_cell_count": clean_formal,
        "experiment_matrix_formal_target_cell_count": matrix_formal,
        "generation_verified_target_cell_count": generation_verified,
        "verified_target_cell_rate": (
            float(verified) / row_count if row_count else None
        ),
        "generation_verified_target_cell_rate": (
            float(generation_verified) / row_count if row_count else None
        ),
        "executed_cell_count": int(expected_completed_cell_count),
        "formal_scope_cell_count": int(expected_scope_cell_count),
        "execution_progress_rate": (
            float(expected_completed_cell_count)
            / float(expected_scope_cell_count)
        ),
        "audited_completed_cell_rate": (
            float(row_count) / float(expected_completed_cell_count)
        ),
        "expected_shard_progress": {
            str(shard): int(count)
            for shard, count in expected_shard_progress
        },
        "d6_audit_scope_statement": (
            f"{row_count} targeted cells audited from "
            f"{expected_completed_cell_count}/{expected_scope_cell_count} "
            "executed formal R0 cells"
        ),
    }


def write_formal_r0_targeted_posterior_audit(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Write JSON, per-cell CSV, Chinese report, and checksums."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "formal_r0_targeted_posterior_audit.json"
    csv_path = output / "formal_r0_targeted_posterior_cells.csv"
    markdown_path = output / "FORMAL_R0_TARGETED_POSTERIOR_AUDIT_CN.md"
    checksum_path = output / "SHA256SUMS"

    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    fields = (
        "cell_id",
        "shard_index",
        "scenario",
        "scale",
        "seed",
        "source_clean_verified",
        "execution_plan_verified",
        "shard_and_cell_identity_verified",
        "artifact_tree_verified",
        "online_truth_use_count",
        "finite_state",
        "formal_acceptance_eligible",
        "experiment_matrix_formal_acceptance_eligible",
        "d1_posterior_generation",
        "d1_full_posterior_publication_count",
        "d2_consumed_d1_posterior_generation",
        "d2_posterior_consumption_count",
        "d2_association_publication_count",
        "d2_pre_tick_posterior_merge_count",
        "d2_finalize_unchanged_posterior_skip_count",
        "d2_pending_generation_empty",
        "observation_governance_generation_integrity",
        "observation_governance_generation_contract_status",
        "d4_current_d3_plan_binding_verified",
        "d4_current_d3_plan_id_match",
        "d4_current_d3_plan_version_match",
        "d4_current_d3_authority_epoch_match",
        "d4_current_d3_authority_lease_match",
        "d4_current_plan_coalition_commit_verified",
        "d4_current_plan_coalition_state_distribution_json",
        "d4_current_plan_uncommitted_target_ids_json",
        "d4_communication_disposition_validation_verified",
        "d4_communication_disposition_record_count",
        "verified",
        "failure_reasons",
    )
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for raw in result.get("cells", ()):
            row = dict(raw)
            row["failure_reasons"] = ";".join(
                str(value) for value in row.get("failure_reasons", ())
            )
            writer.writerow({field: row.get(field) for field in fields})

    markdown_path.write_text(
        render_formal_r0_targeted_posterior_audit_markdown(result),
        encoding="utf-8",
    )
    payload_paths = (json_path, csv_path, markdown_path)
    checksum_path.write_text(
        "".join(
            f"{_sha256_file(path)}  {path.name}\n"
            for path in sorted(payload_paths, key=lambda item: item.name)
        ),
        encoding="utf-8",
    )
    return {
        "json": json_path,
        "csv": csv_path,
        "markdown": markdown_path,
        "checksums": checksum_path,
    }


def render_formal_r0_targeted_posterior_audit_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the bounded Chinese formal-R0 audit report."""

    aggregate = result.get("aggregate", {})
    source = result.get("source", {})
    plan = result.get("execution_plan", {})
    progress = result.get("execution_progress", {})
    lines = [
        "# 正式 R0 五项后验定向复核",
        "",
        f"评估日期：{result.get('evaluation_date')}",
        "",
        "## 结论",
        "",
        (
            f"专项结论为 **{result.get('verdict')}**。clean source 为 "
            f"`{source.get('actual_git_commit')}`，执行计划逻辑摘要为 "
            f"`{plan.get('computed_logical_sha256')}`。"
        ),
        (
            "当前正式 R0 总执行进度为 "
            f"{aggregate.get('executed_cell_count')}/"
            f"{aggregate.get('formal_scope_cell_count')}。"
            f"本专项只审计 {aggregate.get('targeted_audit_cell_count')} 个目标 cell，"
            "没有审计全部已执行 cell。"
        ),
        (
            f"五项通过 {aggregate.get('verified_target_cell_count')}/"
            f"{aggregate.get('targeted_audit_denominator')}，generation verified "
            f"{aggregate.get('generation_verified_target_cell_count')}/"
            f"{aggregate.get('targeted_audit_denominator')}。"
        ),
        (
            "该结果不得写成 177/177、900/900 或完整 R0 scope 已完成。"
            "旧 source 的 895 项不得与本批次相加。"
        ),
        "",
        "## 重算方法",
        "",
        "1. 从 clean worktree 读取 Git 提交与 dirty 状态，核对执行计划 source。",
        "2. 移除计划自摘要字段后重新计算规范 JSON 摘要，同时核对计划文件 SHA-256。",
        "3. 读取 shard plan、checkpoint 和 progress，核对 177/900 进度及目标 cell 身份。",
        "4. 对五个目标 cell 重新计算 cell result 摘要与 episode artifact tree 摘要。",
        "5. 读取 episode manifest、配置、summary 和在线总线。D1/D2 后验代次由在线总线与最终 summary 重算。",
        "6. 同时执行 clean formal、实验矩阵、在线真值、有限状态和 generation integrity 门；任一失败即关闭该 cell。",
        "",
        "`targeted_formal_d6` 和 producer 侧 `observation_governance_audit.json` 未作为输入。",
        "",
        "## 执行范围",
        "",
        (
            f"- checkpoint/progress 计数：{progress.get('completed_cell_count')}/"
            f"{progress.get('scope_cell_count')}。"
        ),
        (
            "- 分片进度："
            f"`{json.dumps(progress.get('shard_progress', {}), ensure_ascii=False, sort_keys=True)}`。"
        ),
        f"- 目标审计分母：{aggregate.get('targeted_audit_denominator')}。",
        "",
        "## 逐项结果",
        "",
        "| cell | shard | scale | seed | source/plan/cell/tree | formal/matrix | D1 final/pub | D2 final/consume/pub | merge/skip/pending | generation | verdict |",
        "| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in result.get("cells", ()):
        provenance = "/".join(
            _bool_text(row.get(field))
            for field in (
                "source_clean_verified",
                "execution_plan_verified",
                "shard_and_cell_identity_verified",
                "artifact_tree_verified",
            )
        )
        lines.append(
            "| {cell} | {shard} | {scale} | {seed} | {provenance} | "
            "{formal}/{matrix} | {d1}/{d1pub} | {d2}/{consume}/{d2pub} | "
            "{merge}/{skip}/{pending} | {generation} | {verdict} |".format(
                cell=row.get("cell_id"),
                shard=row.get("shard_index"),
                scale=row.get("scale"),
                seed=row.get("seed"),
                provenance=provenance,
                formal=_bool_text(row.get("formal_acceptance_eligible")),
                matrix=_bool_text(
                    row.get(
                        "experiment_matrix_formal_acceptance_eligible"
                    )
                ),
                d1=row.get("d1_posterior_generation"),
                d1pub=row.get("d1_full_posterior_publication_count"),
                d2=row.get("d2_consumed_d1_posterior_generation"),
                consume=row.get("d2_posterior_consumption_count"),
                d2pub=row.get("d2_association_publication_count"),
                merge=row.get("d2_pre_tick_posterior_merge_count"),
                skip=row.get("d2_finalize_unchanged_posterior_skip_count"),
                pending=_bool_text(row.get("d2_pending_generation_empty")),
                generation=row.get(
                    "observation_governance_generation_contract_status"
                ),
                verdict="通过" if row.get("verified") is True else "失败关闭",
            )
        )
        if row.get("failure_reasons"):
            lines.append(
                f"\n`{row.get('cell_id')}` 失败原因："
                f"`{json.dumps(row.get('failure_reasons'), ensure_ascii=False)}`。\n"
            )
    lines.extend(
        [
            "",
            "## 边界",
            "",
            "- 本专项没有修改、补零、覆盖或删除 source episode。",
            "- 五项通过只关闭这五项在新 source 下的后验代次疑点。",
            "- 其余 172 个已执行 cell 未由本专项逐项审计。",
            "- 正式 R0 剩余 723 个 cell 尚未执行，完整批次验收继续开放。",
            "- 未来若 clean formal 或 generation verified 任一失败，D6 必须保留逐项原因并失败关闭。",
        ]
    )
    if result.get("failure_reasons"):
        lines.extend(
            [
                "",
                "## 失败原因",
                "",
                *(
                    f"- `{reason}`"
                    for reason in result.get("failure_reasons", ())
                ),
            ]
        )
    return "\n".join(lines) + "\n"


def _audit_execution_plan(
    plan: Mapping[str, Any] | None,
    *,
    plan_path: Path,
    checksum_path: Path,
    inputs: FormalR0TargetedPosteriorAuditInputs,
) -> dict[str, Any]:
    reasons: list[str] = []
    file_sha = _sha256_file(plan_path) if plan_path.is_file() else None
    declared_file_sha: str | None = None
    if checksum_path.is_file():
        parts = checksum_path.read_text(encoding="utf-8").strip().split()
        if (
            len(parts) == 2
            and parts[1] == plan_path.name
            and _is_hex_digest(parts[0], 64)
        ):
            declared_file_sha = parts[0]
        else:
            reasons.append("execution_plan_file_checksum_manifest_invalid")
    else:
        reasons.append("execution_plan_file_checksum_manifest_missing")
    if file_sha is None or declared_file_sha != file_sha:
        reasons.append("execution_plan_file_sha256_mismatch")

    computed_logical: str | None = None
    declared_logical: str | None = None
    if plan is None:
        reasons.append("execution_plan_missing")
    else:
        if plan.get("schema_version") != _EXECUTION_PLAN_SCHEMA:
            reasons.append("execution_plan_schema_mismatch")
        declared_logical = _optional_string(plan.get("execution_plan_sha256"))
        unhashed = dict(plan)
        unhashed.pop("execution_plan_sha256", None)
        computed_logical = _digest_json(unhashed)
        if declared_logical != computed_logical:
            reasons.append("execution_plan_logical_sha256_mismatch")
        if computed_logical != inputs.expected_execution_plan_sha256:
            reasons.append("execution_plan_expected_sha256_mismatch")
        source = plan.get("source")
        if not isinstance(source, Mapping):
            reasons.append("execution_plan_source_missing")
        else:
            if source.get("git_commit") != inputs.expected_source_git_commit:
                reasons.append("execution_plan_source_commit_mismatch")
            if source.get("repository_dirty") is not False:
                reasons.append("execution_plan_source_not_clean")
        parent = plan.get("parent")
        if not isinstance(parent, Mapping) or parent.get("formal") is not True:
            reasons.append("execution_plan_parent_not_formal")
        elif int(parent.get("full_cell_count", -1)) != 5700:
            reasons.append("execution_plan_parent_cell_count_mismatch")
        scope = plan.get("scope")
        if not isinstance(scope, Mapping):
            reasons.append("execution_plan_scope_missing")
        else:
            cells = scope.get("cells")
            if scope.get("variants") != ["R0"]:
                reasons.append("execution_plan_scope_not_r0_only")
            if int(scope.get("cell_count", -1)) != (
                inputs.expected_scope_cell_count
            ):
                reasons.append("execution_plan_scope_cell_count_mismatch")
            if not isinstance(cells, list):
                reasons.append("execution_plan_scope_cells_missing")
            elif _digest_json(cells) != scope.get("cells_sha256"):
                reasons.append("execution_plan_scope_cells_sha256_mismatch")
        sharding = plan.get("sharding")
        if not isinstance(sharding, Mapping):
            reasons.append("execution_plan_sharding_missing")
        elif (
            sharding.get("strategy") != "scope_index_modulo_v1"
            or int(sharding.get("shard_count", -1)) != 20
        ):
            reasons.append("execution_plan_sharding_contract_mismatch")
    reasons = list(dict.fromkeys(reasons))
    return {
        "verified": not reasons,
        "path": str(plan_path),
        "declared_logical_sha256": declared_logical,
        "computed_logical_sha256": computed_logical,
        "file_sha256": file_sha,
        "declared_file_sha256": declared_file_sha,
        "failure_reasons": reasons,
    }


def _audit_source_repository(
    inputs: FormalR0TargetedPosteriorAuditInputs,
) -> dict[str, Any]:
    reasons: list[str] = []
    commit: str | None = None
    dirty: bool | None = None
    try:
        commit = _git_output(
            inputs.source_repository,
            ("rev-parse", "HEAD"),
        )
        status = _git_output(
            inputs.source_repository,
            ("status", "--porcelain=v1"),
        )
        dirty = bool(status)
    except (OSError, subprocess.CalledProcessError) as exc:
        reasons.append(f"source_git_audit_failed:{exc}")
    if commit != inputs.expected_source_git_commit:
        reasons.append("source_git_commit_mismatch")
    if dirty is not False:
        reasons.append("source_repository_not_clean")
    reasons = list(dict.fromkeys(reasons))
    return {
        "verified": not reasons,
        "repository": str(inputs.source_repository),
        "actual_git_commit": commit,
        "expected_git_commit": inputs.expected_source_git_commit,
        "repository_dirty": dirty,
        "failure_reasons": reasons,
    }


def _audit_execution_progress(
    plan: Mapping[str, Any] | None,
    inputs: FormalR0TargetedPosteriorAuditInputs,
) -> dict[str, Any]:
    reasons: list[str] = []
    shard_rows: list[dict[str, Any]] = []
    if plan is None:
        return {
            "verified": False,
            "scope_cell_count": inputs.expected_scope_cell_count,
            "completed_cell_count": 0,
            "shard_progress": {},
            "shards": (),
            "failure_reasons": ("execution_plan_missing_for_progress_audit",),
        }
    scope = plan.get("scope")
    sharding = plan.get("sharding")
    scope_cells = (
        scope.get("cells")
        if isinstance(scope, Mapping)
        and isinstance(scope.get("cells"), list)
        else []
    )
    shard_descriptors = (
        sharding.get("shards")
        if isinstance(sharding, Mapping)
        and isinstance(sharding.get("shards"), list)
        else []
    )
    descriptor_by_index = {
        int(item["shard_index"]): item
        for item in shard_descriptors
        if isinstance(item, Mapping)
        and _is_nonnegative_int(item.get("shard_index"))
    }
    plan_cells_by_shard: dict[int, list[Mapping[str, Any]]] = {}
    for cell in scope_cells:
        if not isinstance(cell, Mapping) or not _is_nonnegative_int(
            cell.get("shard_index")
        ):
            continue
        plan_cells_by_shard.setdefault(int(cell["shard_index"]), []).append(cell)
    total = 0
    for shard_index, expected_completed in inputs.expected_shard_progress:
        descriptor = descriptor_by_index.get(shard_index)
        planned_cells = sorted(
            plan_cells_by_shard.get(shard_index, []),
            key=lambda item: int(item.get("shard_sequence", -1)),
        )
        shard_id = f"shard_{shard_index:03d}_of_020"
        shard_dir = inputs.execution_root / "shards" / shard_id
        shard_reasons: list[str] = []
        shard_plan = _load_json_or_reason(
            shard_dir / "shard_plan.json",
            shard_reasons,
            "shard_plan",
        )
        checkpoint = _load_json_or_reason(
            shard_dir / "checkpoint.json",
            shard_reasons,
            "checkpoint",
        )
        progress = _load_jsonl_or_reason(
            shard_dir / "progress.jsonl",
            shard_reasons,
            "progress",
        )
        if descriptor is None:
            shard_reasons.append("shard_descriptor_missing")
        if shard_plan is not None:
            if shard_plan.get("schema_version") != _SHARD_PLAN_SCHEMA:
                shard_reasons.append("shard_plan_schema_mismatch")
            if shard_plan.get("execution_plan_sha256") != (
                inputs.expected_execution_plan_sha256
            ):
                shard_reasons.append("shard_plan_execution_sha_mismatch")
            if shard_plan.get("source_git_commit") != (
                inputs.expected_source_git_commit
            ):
                shard_reasons.append("shard_plan_source_commit_mismatch")
            if shard_plan.get("cells") != planned_cells:
                shard_reasons.append("shard_plan_cells_mismatch")
            if _digest_json(planned_cells) != shard_plan.get("cells_sha256"):
                shard_reasons.append("shard_plan_cells_sha256_mismatch")
            if descriptor is not None and shard_plan.get("descriptor") != descriptor:
                shard_reasons.append("shard_plan_descriptor_mismatch")
        if checkpoint is not None:
            if checkpoint.get("schema_version") != _SHARD_CHECKPOINT_SCHEMA:
                shard_reasons.append("checkpoint_schema_mismatch")
            for field, expected in (
                ("execution_plan_sha256", inputs.expected_execution_plan_sha256),
                ("source_git_commit", inputs.expected_source_git_commit),
                ("shard_id", shard_id),
                ("shard_index", shard_index),
                ("completed_cell_count", expected_completed),
                ("next_sequence", expected_completed),
                ("expected_cell_count", len(planned_cells)),
            ):
                if checkpoint.get(field) != expected:
                    shard_reasons.append(f"checkpoint_{field}_mismatch")
            expected_status = (
                "complete"
                if expected_completed == len(planned_cells)
                else "paused"
            )
            if checkpoint.get("status") != expected_status:
                shard_reasons.append("checkpoint_status_mismatch")
            progress_path = shard_dir / "progress.jsonl"
            if (
                progress_path.is_file()
                and checkpoint.get("progress_sha256")
                != _sha256_file(progress_path)
            ):
                shard_reasons.append("checkpoint_progress_sha256_mismatch")
        if len(progress) != expected_completed:
            shard_reasons.append("progress_row_count_mismatch")
        shard_reasons.extend(
            _progress_identity_reasons(progress, planned_cells)
        )
        for sequence, row in enumerate(progress):
            expected_cell = (
                planned_cells[sequence]
                if sequence < len(planned_cells)
                else None
            )
            if row.get("schema_version") != _SHARD_PROGRESS_SCHEMA:
                shard_reasons.append(f"progress_schema_mismatch:{sequence}")
            if row.get("sequence") != sequence:
                shard_reasons.append(f"progress_sequence_mismatch:{sequence}")
            if row.get("execution_plan_sha256") != (
                inputs.expected_execution_plan_sha256
            ):
                shard_reasons.append(
                    f"progress_execution_sha_mismatch:{sequence}"
                )
            if expected_cell is None:
                shard_reasons.append(f"progress_unplanned_row:{sequence}")
            else:
                for field in (
                    "cell_id",
                    "global_index",
                    "scope_index",
                    "shard_index",
                    "shard_sequence",
                ):
                    if row.get(field) != expected_cell.get(field):
                        shard_reasons.append(
                            f"progress_{field}_mismatch:{sequence}"
                        )
        shard_reasons = list(dict.fromkeys(shard_reasons))
        total += len(progress)
        shard_rows.append(
            {
                "shard_index": shard_index,
                "shard_id": shard_id,
                "expected_completed_cell_count": expected_completed,
                "actual_progress_row_count": len(progress),
                "planned_cell_count": len(planned_cells),
                "verified": not shard_reasons,
                "failure_reasons": shard_reasons,
            }
        )
        reasons.extend(
            f"{shard_id}:{reason}" for reason in shard_reasons
        )
    if total != inputs.expected_completed_cell_count:
        reasons.append("total_completed_cell_count_mismatch")
    reasons = list(dict.fromkeys(reasons))
    return {
        "verified": not reasons,
        "scope_cell_count": inputs.expected_scope_cell_count,
        "completed_cell_count": total,
        "shard_progress": {
            str(row["shard_index"]): row["actual_progress_row_count"]
            for row in shard_rows
        },
        "shards": shard_rows,
        "failure_reasons": reasons,
    }


def _progress_identity_reasons(
    progress: Sequence[Mapping[str, Any]],
    planned_cells: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Detect duplicate or incomplete shard progress identities explicitly."""

    reasons: list[str] = []
    progress_cell_ids = [
        row.get("cell_id") for row in progress if isinstance(row, Mapping)
    ]
    progress_sequences = [
        row.get("sequence") for row in progress if isinstance(row, Mapping)
    ]
    if len(set(progress_cell_ids)) != len(progress_cell_ids):
        reasons.append("progress_duplicate_cell_id")
    if len(set(progress_sequences)) != len(progress_sequences):
        reasons.append("progress_duplicate_sequence")
    planned_cell_ids = [
        row.get("cell_id")
        for row in planned_cells[: len(progress)]
        if isinstance(row, Mapping)
    ]
    if progress_cell_ids != planned_cell_ids:
        reasons.append("progress_cell_identity_order_mismatch")
    return reasons


def _audit_target_cell(
    target: FormalR0TargetCell,
    *,
    inputs: FormalR0TargetedPosteriorAuditInputs,
    plan: Mapping[str, Any] | None,
    global_failure_reasons: Sequence[str],
) -> dict[str, Any]:
    reasons = list(global_failure_reasons)
    planned_cell = _find_planned_cell(plan, target.cell_id)
    if planned_cell is None:
        reasons.append("target_cell_absent_from_execution_plan")
    elif int(planned_cell.get("shard_index", -1)) != target.shard_index:
        reasons.append("target_shard_identity_mismatch")

    shard_id = f"shard_{target.shard_index:03d}_of_020"
    container = (
        inputs.execution_root
        / "shards"
        / shard_id
        / "cells"
        / target.cell_id
    )
    cell_result_path = container / "cell_result.json"
    episode_dir = container / "episode"
    cell_result = _load_json_or_reason(
        cell_result_path,
        reasons,
        "cell_result",
    )
    progress_row = _target_progress_row(
        inputs.execution_root / "shards" / shard_id / "progress.jsonl",
        target.cell_id,
        reasons,
    )
    artifact_tree_verified = False
    computed_artifact_tree_sha256: str | None = None
    declared_artifact_tree_sha256: str | None = None
    computed_cell_result_sha256 = (
        _sha256_file(cell_result_path) if cell_result_path.is_file() else None
    )
    progress_cell_result_sha256 = (
        progress_row.get("cell_result_sha256")
        if progress_row is not None
        else None
    )
    shard_and_cell_identity_verified = False
    if cell_result is not None and planned_cell is not None:
        declared_artifact_tree_sha256 = _optional_string(
            cell_result.get("artifact_tree_sha256")
        )
        if cell_result.get("schema_version") != _CELL_RESULT_SCHEMA:
            reasons.append("cell_result_schema_mismatch")
        if cell_result.get("cell") != planned_cell:
            reasons.append("cell_result_identity_mismatch")
        if cell_result.get("status") != "complete":
            reasons.append("cell_result_not_complete")
        if cell_result.get("execution_plan_sha256") != (
            inputs.expected_execution_plan_sha256
        ):
            reasons.append("cell_result_execution_sha_mismatch")
        if cell_result.get("source_git_commit") != (
            inputs.expected_source_git_commit
        ):
            reasons.append("cell_result_source_commit_mismatch")
        expected_episode_relative = (
            f"shards/{shard_id}/cells/{target.cell_id}/episode"
        )
        if cell_result.get("episode_relative_path") != expected_episode_relative:
            reasons.append("cell_result_episode_path_mismatch")
        shard_and_cell_identity_verified = not any(
            reason.startswith(
                (
                    "target_cell_",
                    "target_shard_",
                    "cell_result_",
                    "progress_target_",
                )
            )
            for reason in reasons
        )
    if progress_row is not None:
        if progress_cell_result_sha256 != computed_cell_result_sha256:
            reasons.append("progress_target_cell_result_sha256_mismatch")
        if cell_result is not None and progress_row.get(
            "episode_artifact_tree_sha256"
        ) != cell_result.get("artifact_tree_sha256"):
            reasons.append("progress_target_artifact_tree_sha256_mismatch")

    missing_artifacts = [
        name
        for name in _REQUIRED_EPISODE_ARTIFACTS
        if not (episode_dir / name).is_file()
    ]
    if missing_artifacts:
        reasons.extend(
            f"required_episode_artifact_missing:{name}"
            for name in missing_artifacts
        )
    elif cell_result is not None:
        computed_artifact_tree_sha256 = _tree_digest(episode_dir)
        if (
            computed_artifact_tree_sha256
            != declared_artifact_tree_sha256
        ):
            reasons.append("episode_artifact_tree_sha256_mismatch")
        else:
            artifact_tree_verified = True

    low_level: dict[str, Any] = {}
    plan_binding_audit = audit_formal_r0_plan_binding_episode(episode_dir)
    plan_binding_metrics = formal_r0_plan_binding_row_metrics(
        plan_binding_audit
    )
    if not missing_artifacts:
        try:
            low_level = evaluate_scalable_3d_episode(episode_dir)
        except (OSError, ValueError) as exc:
            reasons.append(f"d6_low_level_episode_evaluation_failed:{exc}")
    reasons.extend(_low_level_gate_reasons(low_level))
    reasons.extend(
        f"d3_d4_current_plan:{reason}"
        for reason in plan_binding_audit.get("failure_reasons", ())
    )
    if low_level:
        if low_level.get("git_commit") != inputs.expected_source_git_commit:
            reasons.append("episode_manifest_source_commit_mismatch")
        if low_level.get("repository_dirty") is not False:
            reasons.append("episode_not_clean_source")
    reasons = list(dict.fromkeys(reasons))
    source_clean_verified = not any(
        reason.startswith(("source_", "execution_plan_source_", "episode_not_clean"))
        for reason in reasons
    )
    execution_plan_verified = not any(
        "execution_plan_" in reason for reason in reasons
    )
    shard_and_cell_identity_verified = (
        shard_and_cell_identity_verified
        and progress_row is not None
        and not any(
            reason.startswith(("progress_target_", "shard_"))
            for reason in reasons
        )
    )
    row = {
        "cell_id": target.cell_id,
        "shard_index": target.shard_index,
        "scenario": (
            planned_cell.get("scenario") if planned_cell is not None else None
        ),
        "scale": (
            planned_cell.get("scale") if planned_cell is not None else None
        ),
        "seed": (
            planned_cell.get("seed") if planned_cell is not None else None
        ),
        "source_clean_verified": source_clean_verified,
        "execution_plan_verified": execution_plan_verified,
        "shard_and_cell_identity_verified": shard_and_cell_identity_verified,
        "artifact_tree_verified": artifact_tree_verified,
        "episode_dir": str(episode_dir),
        "computed_cell_result_sha256": computed_cell_result_sha256,
        "progress_cell_result_sha256": progress_cell_result_sha256,
        "declared_artifact_tree_sha256": declared_artifact_tree_sha256,
        "computed_artifact_tree_sha256": computed_artifact_tree_sha256,
        "online_truth_use_count": low_level.get("online_truth_use_count"),
        "online_truth_field_violation_count": low_level.get(
            "online_truth_field_violation_count"
        ),
        "finite_state": low_level.get("finite_state"),
        "formal_acceptance_eligible": low_level.get(
            "formal_acceptance_eligible"
        ),
        "experiment_matrix_formal_acceptance_eligible": low_level.get(
            "experiment_matrix_formal_acceptance_eligible"
        ),
        "episode_evidence_status": low_level.get("episode_evidence_status"),
        "episode_failure_reasons": low_level.get(
            "episode_failure_reasons_json"
        ),
        "experiment_matrix_formal_failure_reasons": low_level.get(
            "experiment_matrix_formal_failure_reasons_json"
        ),
        "variant_execution_failure_reasons": low_level.get(
            "variant_execution_failure_reasons_json"
        ),
        "d1_posterior_generation": low_level.get("d1_posterior_generation"),
        "d1_full_posterior_publication_count": low_level.get(
            "d1_full_posterior_publication_count"
        ),
        "d2_consumed_d1_posterior_generation": low_level.get(
            "d2_consumed_d1_posterior_generation"
        ),
        "d2_posterior_consumption_count": low_level.get(
            "d2_posterior_consumption_count"
        ),
        "d2_association_publication_count": low_level.get(
            "d2_association_publication_count"
        ),
        "d2_pre_tick_posterior_merge_count": low_level.get(
            "d2_pre_tick_posterior_merge_count"
        ),
        "d2_finalize_unchanged_posterior_skip_count": low_level.get(
            "d2_finalize_unchanged_posterior_skip_count"
        ),
        "d2_pending_generation_empty": low_level.get(
            "d2_pending_generation_empty"
        ),
        "observation_governance_generation_integrity": low_level.get(
            "observation_governance_generation_integrity"
        ),
        "observation_governance_generation_integrity_reasons": low_level.get(
            "observation_governance_generation_integrity_reasons_json"
        ),
        "observation_governance_generation_contract_status": low_level.get(
            "observation_governance_generation_contract_status"
        ),
        "episode_source_git_commit": low_level.get("episode_source_git_commit"),
        "episode_source_repository_dirty": low_level.get(
            "episode_source_repository_dirty"
        ),
        "d6_evaluator_schema_version": low_level.get(
            "d6_evaluator_schema_version"
        ),
        "d6_evaluator_git_commit": low_level.get("d6_evaluator_git_commit"),
        "d6_evaluator_repository_dirty": low_level.get(
            "d6_evaluator_repository_dirty"
        ),
        "d6_evaluator_source_tree_sha256": low_level.get(
            "d6_evaluator_source_tree_sha256"
        ),
        "verified": not reasons,
        "failure_reasons": reasons,
    }
    row.update(plan_binding_metrics)
    for field in _POSTERIOR_AUDIT_LOW_LEVEL_EVIDENCE_FIELDS:
        if field not in row:
            row[field] = low_level.get(field)
        row[f"{field}_availability"] = low_level.get(
            f"{field}_availability"
        )
        row[f"{field}_unavailable_reason"] = low_level.get(
            f"{field}_unavailable_reason"
        )
    for field in (
        "d2_id_switch_count_semantics",
        "d2_id_switch_count_source_artifact",
        "d2_strict_identity_artifact_verified",
        "d2_strict_identity_verification_mode",
        "d2_strict_identity_truth_isolation_verified",
        "d2_strict_identity_id_switch_backfilled",
        "d2_truth_isolated_manifest_sha256",
        "d2_truth_isolated_episode_record_sha256",
        "d2_offline_identity_manifest_sha256",
        "d2_offline_identity_evaluation_sha256",
    ):
        row[field] = low_level.get(field)
    return row


def _low_level_gate_reasons(
    low_level: Mapping[str, Any],
) -> list[str]:
    """Return explicit fail-closed reasons for one D6 episode evaluation."""

    if not low_level:
        return ["d6_low_level_evidence_unavailable"]
    reasons = [
        f"d6_low_level:{reason}"
        for reason in low_level.get("episode_failure_reasons_json", ())
    ]
    if low_level.get("online_truth_use_count") != 0:
        reasons.append("online_truth_use_nonzero_or_unavailable")
    if low_level.get("online_truth_field_violation_count") != 0:
        reasons.append("online_truth_field_violation_nonzero_or_unavailable")
    if low_level.get("finite_state") is not True:
        reasons.append("finite_state_not_verified")
    if low_level.get("formal_acceptance_eligible") is not True:
        reasons.append("clean_formal_not_eligible")
    if low_level.get(
        "experiment_matrix_formal_acceptance_eligible"
    ) is not True:
        reasons.append("experiment_matrix_formal_not_eligible")
    for field, reason in (
        ("experiment_matrix_formal_failure_reasons_json", "matrix_failures_nonempty"),
        ("variant_execution_failure_reasons_json", "variant_failures_nonempty"),
    ):
        value = low_level.get(field)
        if not isinstance(value, list) or value:
            reasons.append(reason)
    if low_level.get("episode_evidence_status") != (
        "clean_formal_experiment_matrix"
    ):
        reasons.append("episode_evidence_status_not_clean_formal_matrix")
    if low_level.get(
        "observation_governance_generation_integrity"
    ) is not True:
        reasons.append("generation_integrity_not_verified")
    if low_level.get(
        "observation_governance_generation_contract_status"
    ) != "verified":
        reasons.append("generation_contract_not_verified")
    if (
        low_level.get("d2_id_switch_count_availability") == "available"
        and not strict_id_switch_provenance_is_verified(low_level)
    ):
        reasons.append("d2_strict_id_switch_provenance_not_verified")
    return list(dict.fromkeys(reasons))


def _find_planned_cell(
    plan: Mapping[str, Any] | None,
    cell_id: str,
) -> Mapping[str, Any] | None:
    if plan is None:
        return None
    scope = plan.get("scope")
    cells = scope.get("cells") if isinstance(scope, Mapping) else None
    if not isinstance(cells, list):
        return None
    matches = [
        cell
        for cell in cells
        if isinstance(cell, Mapping) and cell.get("cell_id") == cell_id
    ]
    return matches[0] if len(matches) == 1 else None


def _target_progress_row(
    path: Path,
    cell_id: str,
    reasons: list[str],
) -> Mapping[str, Any] | None:
    rows = _load_jsonl_or_reason(path, reasons, "target_progress")
    matches = [row for row in rows if row.get("cell_id") == cell_id]
    if len(matches) != 1:
        reasons.append(
            f"progress_target_identity_count_mismatch:actual={len(matches)}"
        )
        return None
    return matches[0]


def _load_json_or_reason(
    path: Path,
    reasons: list[str],
    label: str,
) -> dict[str, Any] | None:
    try:
        return _read_json_object(path)
    except (OSError, FormalR0TargetedPosteriorAuditError) as exc:
        reasons.append(f"{label}_unreadable:{exc}")
        return None


def _load_jsonl_or_reason(
    path: Path,
    reasons: list[str],
    label: str,
) -> list[dict[str, Any]]:
    try:
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    raise FormalR0TargetedPosteriorAuditError(
                        f"{path}: blank JSONL row {line_number}"
                    )
                payload = _strict_json_loads(line)
                if not isinstance(payload, dict):
                    raise FormalR0TargetedPosteriorAuditError(
                        f"{path}: row {line_number} is not an object"
                    )
                rows.append(payload)
        return rows
    except (OSError, FormalR0TargetedPosteriorAuditError) as exc:
        reasons.append(f"{label}_unreadable:{exc}")
        return []


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = _strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FormalR0TargetedPosteriorAuditError(
            f"JSON root must be an object: {path}"
        )
    return payload


def _strict_json_loads(value: str) -> Any:
    def reject_constant(token: str) -> None:
        raise FormalR0TargetedPosteriorAuditError(
            f"non-finite JSON token is forbidden: {token}"
        )

    try:
        return json.loads(value, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise FormalR0TargetedPosteriorAuditError(
            f"invalid JSON: {exc}"
        ) from exc


def _tree_digest(root: Path) -> str:
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]
    if not entries:
        raise FormalR0TargetedPosteriorAuditError(
            f"artifact tree is empty: {root}"
        )
    return _digest_json(entries)


def _digest_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_output(repository: Path, args: Sequence[str]) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _is_hex_digest(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == int(length)
        and all(character in _HEX64 for character in value)
    )


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _bool_text(value: Any) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "不可用"


__all__ = [
    "FORMAL_R0_TARGETED_POSTERIOR_AUDIT_DATE",
    "FORMAL_R0_TARGETED_POSTERIOR_AUDIT_SCHEMA_VERSION",
    "FORMAL_R0_TARGETED_POSTERIOR_INPUT_SCHEMA_VERSION",
    "FormalR0TargetCell",
    "FormalR0TargetedPosteriorAuditError",
    "FormalR0TargetedPosteriorAuditInputs",
    "aggregate_formal_r0_targeted_posterior_rows",
    "audit_formal_r0_targeted_posterior",
    "load_formal_r0_targeted_posterior_audit_inputs",
    "render_formal_r0_targeted_posterior_audit_markdown",
    "write_formal_r0_targeted_posterior_audit",
]
