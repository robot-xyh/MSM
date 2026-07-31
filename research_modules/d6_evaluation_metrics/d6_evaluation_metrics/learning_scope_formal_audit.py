"""Fail-closed audit of hash-bound learned experiment scopes.

The auditor is an optional, read-only D6 consumer.  It validates persisted
execution-plan, shard, merge, cell, and episode evidence without importing a
controller or modifying the default runtime path.  Missing evidence remains
unavailable; it is never replaced with a zero-valued metric.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any, Mapping, Sequence

from .formal_shard_archive_audit import (
    FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
    audit_archive_merge_bundle,
    audit_verified_formal_shard_archive_set,
)
from .scalable_3d_offline import (
    Scalable3DOfflineEvaluationError,
    evaluate_scalable_3d_episode,
)


LEARNING_SCOPE_FORMAL_AUDIT_SCHEMA_VERSION = (
    "d6.learning-scope-formal-evidence-audit.v1"
)
LEARNING_SCOPE_FORMAL_AUDIT_DATE = "2026-07-31"
LEARNING_SCOPE_DIRECTORY_STORAGE_MODE = "materialized_scope_directories_v1"

_EXECUTION_PLAN_SCHEMA = "scalable3d-experiment-matrix-execution-plan-v1"
_MODEL_BINDING_SCHEMA = (
    "scalable3d-experiment-matrix-model-bundle-binding-v1"
)
_SCOPE_MERGE_SCHEMA = "scalable3d-experiment-matrix-scope-merge-v1"
_SHARD_PLAN_SCHEMA = "scalable3d-experiment-matrix-shard-plan-v1"
_SHARD_PROGRESS_SCHEMA = "scalable3d-experiment-matrix-shard-progress-v1"
_SHARD_CHECKPOINT_SCHEMA = (
    "scalable3d-experiment-matrix-shard-checkpoint-v1"
)
_CELL_RESULT_SCHEMA = "scalable3d-experiment-matrix-cell-result-v1"

_VARIANT_COMPONENTS = {
    "R0": (),
    "G1": ("d5_graph",),
    "A1": ("d3",),
    "A2": ("d4",),
    "A3": ("d5_active_vision",),
    "C1": ("d3", "d4", "d5_graph", "d5_active_vision"),
    "F1": ("d3", "d4", "d5_graph", "d5_active_vision"),
}
_RUNTIME_COMPONENT_NAMES = {
    "d3": "d3",
    "d4": "d4",
    "d5_graph": "d5",
    "d5_active_vision": "d5_active_vision",
}
_VERSION_FIELDS = (
    "d3_policy_version",
    "d4_policy_version",
    "d5_model_version",
    "d5_active_vision_policy_version",
)
_REQUIRED_EPISODE_ARTIFACTS = (
    "manifest.json",
    "scenario_config.json",
    "summary.json",
    "online_observations.jsonl",
    "offline_proximity_intercepts.jsonl",
    "stage_timings.csv",
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

_PAIR_METRIC_POLICY = {
    "intercepted_target_count": {
        "direction": "higher_or_equal",
        "required": True,
        "source": "summary.json",
    },
    "offline_proximity_unique_target_count": {
        "direction": "higher_or_equal",
        "required": True,
        "source": "D6 offline episode evaluation",
    },
    "offline_proximity_within_5m_count": {
        "direction": "higher_or_equal",
        "required": False,
        "source": "D6 offline episode evaluation",
    },
    "d2_id_switch_count": {
        "direction": "lower_or_equal",
        "required": False,
        "source": "D6 offline episode evaluation",
    },
    "d3_plan_coverage_rate": {
        "direction": "higher_or_equal",
        "required": False,
        "source": "D6 offline episode evaluation",
    },
    "d3_backlog_count": {
        "direction": "lower_or_equal",
        "required": False,
        "source": "D6 offline episode evaluation",
    },
    "d5_binding_count": {
        "direction": "higher_or_equal",
        "required": False,
        "source": "D6 offline episode evaluation",
    },
}


class LearningScopeFormalAuditError(ValueError):
    """Stable validation failure used inside the fail-closed result."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ScopeEvidenceArtifacts:
    """One explicitly selected directory or archive scope evidence source."""

    execution_plan_path: Path
    merge_dir: Path | None = None
    label: str = "scope"
    archive_root: Path | None = None
    archive_merge_dir: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "execution_plan_path",
            Path(self.execution_plan_path).resolve(),
        )
        directory_mode = self.merge_dir is not None
        archive_mode = (
            self.archive_root is not None or self.archive_merge_dir is not None
        )
        if directory_mode == archive_mode:
            raise ValueError(
                "scope evidence must select exactly one storage mode: "
                "merge_dir or archive_root+archive_merge_dir"
            )
        if archive_mode and (
            self.archive_root is None or self.archive_merge_dir is None
        ):
            raise ValueError(
                "archive scope evidence requires archive_root and "
                "archive_merge_dir"
            )
        if self.merge_dir is not None:
            object.__setattr__(
                self,
                "merge_dir",
                Path(self.merge_dir).resolve(),
            )
        if self.archive_root is not None:
            object.__setattr__(
                self,
                "archive_root",
                Path(self.archive_root).expanduser().absolute(),
            )
        if self.archive_merge_dir is not None:
            object.__setattr__(
                self,
                "archive_merge_dir",
                Path(self.archive_merge_dir).expanduser().absolute(),
            )
        label = str(self.label).strip()
        if not label:
            raise ValueError("scope evidence label must be non-empty")
        object.__setattr__(self, "label", label)

    @property
    def storage_mode(self) -> str:
        """Return the explicit storage mode without probing the filesystem."""

        if self.archive_root is not None:
            return FORMAL_SHARD_ARCHIVE_STORAGE_MODE
        return LEARNING_SCOPE_DIRECTORY_STORAGE_MODE

    @property
    def evidence_merge_dir(self) -> Path:
        """Return the selected mode's merge evidence directory."""

        path = self.archive_merge_dir or self.merge_dir
        if path is None:  # guarded by __post_init__
            raise ValueError("scope merge evidence directory is unavailable")
        return path


@dataclass(frozen=True, slots=True)
class LearningScopeFormalAuditInputs:
    """Explicit learned scope and optional R0 scope evidence supplied by main."""

    learned_scope: ScopeEvidenceArtifacts
    r0_scopes: tuple[ScopeEvidenceArtifacts, ...] = ()
    expected_preflight_device: str | None = None

    def __post_init__(self) -> None:
        scopes = tuple(self.r0_scopes)
        if len({item.execution_plan_path for item in scopes}) != len(scopes):
            raise ValueError(
                "each R0 execution plan must select exactly one evidence source"
            )
        if len(
            {
                (
                    item.execution_plan_path,
                    item.storage_mode,
                    item.evidence_merge_dir,
                    item.archive_root,
                )
                for item in scopes
            }
        ) != len(scopes):
            raise ValueError("R0 scope evidence sources must be unique")
        object.__setattr__(self, "r0_scopes", scopes)
        if self.expected_preflight_device is not None:
            device = str(self.expected_preflight_device).strip()
            if not device:
                raise ValueError("expected_preflight_device must be non-empty")
            object.__setattr__(self, "expected_preflight_device", device)


def audit_learning_scope_formal_evidence(
    inputs: LearningScopeFormalAuditInputs,
    *,
    model_bundles: Mapping[str, str | Path | None] | None = None,
) -> dict[str, Any]:
    """Audit one learned scope and same-comparison-key R0 evidence.

    A passing result means only that D6 found a complete, internally
    consistent evidence chain and no degradation in the required paired
    metrics. D6 never grants model promotion or control authority.
    """

    normalized_bundles = {
        str(name): (
            None if path is None else Path(path).resolve()
        )
        for name, path in (model_bundles or {}).items()
    }
    learned = _audit_scope(
        inputs.learned_scope,
        model_bundles=normalized_bundles,
        expected_preflight_device=inputs.expected_preflight_device,
        require_learned_cells=True,
    )
    baseline_scopes = [
        _audit_scope(
            source,
            model_bundles={},
            expected_preflight_device=None,
            require_learned_cells=False,
        )
        for source in inputs.r0_scopes
    ]

    learned_cells = [
        row for row in learned["_internal_cells"] if row["variant"] != "R0"
    ]
    baseline_cells = [
        row for row in learned["_internal_cells"] if row["variant"] == "R0"
    ]
    for scope in baseline_scopes:
        baseline_cells.extend(
            row
            for row in scope["_internal_cells"]
            if row["variant"] == "R0"
        )

    pairing = _audit_r0_pairing(
        learned_cells,
        baseline_cells,
        learned_scope=learned,
        baseline_scopes=baseline_scopes,
    )
    blockers = list(learned["blockers"])
    blockers.extend(
        f"r0_scope:{reason}"
        for scope in baseline_scopes
        for reason in scope["blockers"]
    )
    blockers.extend(pairing["blockers"])
    blockers = sorted(set(blockers))
    passed = (
        not blockers
        and learned["formal_evidence_eligible"] is True
        and pairing["all_required_pairs_available"] is True
        and pairing["all_required_pairs_non_degraded"] is True
    )
    return {
        "schema_version": LEARNING_SCOPE_FORMAL_AUDIT_SCHEMA_VERSION,
        "evaluation_date": LEARNING_SCOPE_FORMAL_AUDIT_DATE,
        "verdict": "pass" if passed else "fail_closed",
        "fail_closed": not passed,
        "formal_evidence_eligible": passed,
        "evidence_admission_allowed": passed,
        "model_promotion": {
            "availability": "unavailable",
            "allowed": False,
            "reason": (
                "D6 evidence audit does not grant model promotion or control "
                "authority"
            ),
        },
        "default_control_path_modified": False,
        "learned_scope": _public_scope(learned),
        "r0_scopes": [_public_scope(scope) for scope in baseline_scopes],
        "r0_pairing": pairing,
        "blockers": blockers,
        "availability_policy": {
            "missing_evidence": "unavailable_and_fail_closed",
            "zero_fill_allowed": False,
            "shadow_is_adoption": False,
            "rule_fallback_is_adoption": False,
            "bundle_loaded_is_adoption": False,
            "missing_r0_is_non_degraded": False,
            "missing_physical_result_is_success": False,
        },
    }


def write_learning_scope_formal_audit_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Write JSON, per-cell CSV, Chinese Markdown, and checksums."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "learning_scope_formal_audit.json"
    csv_path = output / "learning_scope_formal_audit_cells.csv"
    markdown_path = output / "LEARNING_SCOPE_FORMAL_AUDIT_CN.md"
    checksum_path = output / "SHA256SUMS"

    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = [
        *result.get("learned_scope", {}).get("cells", ()),
        *[
            row
            for scope in result.get("r0_scopes", ())
            for row in scope.get("cells", ())
        ],
    ]
    fieldnames = (
        "scope_label",
        "variant",
        "scenario",
        "scale",
        "seed",
        "comparison_key",
        "cell_id",
        "evidence_status",
        "assist_adoption_status",
        "online_truth_status",
        "physical_result_status",
        "failure_reasons",
    )
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for raw in rows:
            row = dict(raw)
            row["failure_reasons"] = ";".join(
                str(value) for value in row.get("failure_reasons", ())
            )
            writer.writerow({name: row.get(name) for name in fieldnames})
    markdown_path.write_text(
        render_learning_scope_formal_audit_markdown(result),
        encoding="utf-8",
    )
    artifacts = (json_path, csv_path, markdown_path)
    checksum_path.write_text(
        "".join(
            f"{_sha256_file(path)}  {path.name}\n"
            for path in sorted(artifacts, key=lambda item: item.name)
        ),
        encoding="utf-8",
    )
    return {
        "json": json_path,
        "csv": csv_path,
        "markdown": markdown_path,
        "checksums": checksum_path,
    }


def render_learning_scope_formal_audit_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render a compact Chinese evidence audit."""

    learned = result.get("learned_scope", {})
    pairing = result.get("r0_pairing", {})
    lines = [
        "# 学习作用域正式证据审计",
        "",
        f"评估日期：{result.get('evaluation_date')}",
        "",
        "## 结论",
        "",
        (
            f"审计结论为 **{result.get('verdict')}**。学习作用域预期 "
            f"{learned.get('expected_cell_count', 0)} 个 cell，验证通过 "
            f"{learned.get('accepted_cell_count', 0)} 个；R0 完整配对 "
            f"{pairing.get('available_pair_count', 0)}/"
            f"{pairing.get('expected_pair_count', 0)}。"
        ),
        (
            "该结论只表示持久化证据是否满足 D6 审计。D6 不授予模型晋级，"
            "也不改变默认控制路径。"
        ),
        "",
        "## 证据链",
        "",
        f"- 存储模式：`{learned.get('storage_mode')}`",
        f"- archive root：`{learned.get('archive_root')}`",
        (
            "- 已独立验证归档："
            f"{learned.get('verified_archive_count', 0)}，"
            "峰值暂存分片："
            f"{learned.get('peak_staged_shard_count', 0)}"
        ),
        f"- sidecar 文件：`{learned.get('sidecar_files', [])}`",
        f"- execution plan：`{learned.get('execution_plan_path')}`",
        f"- merge 目录：`{learned.get('merge_dir')}`",
        f"- 来源提交：`{learned.get('source_git_commit')}`",
        f"- 预检设备：`{learned.get('preflight_device')}`",
        f"- bundle binding：`{learned.get('bundle_binding_status')}`",
        f"- scope 完整性：`{learned.get('scope_completeness_status')}`",
        "",
        "## R0 配对",
        "",
        "| comparison key | 变体 | 状态 | 非退化 | 原因 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in pairing.get("pairs", ()):
        lines.append(
            "| {key} | {variant} | {status} | {non_degraded} | `{reason}` |".format(
                key=row.get("comparison_key"),
                variant=row.get("variant"),
                status=row.get("availability"),
                non_degraded=row.get("non_degraded"),
                reason=row.get("unavailable_reason")
                or ";".join(row.get("failure_reasons", ())),
            )
        )
    if not pairing.get("pairs"):
        lines.append("| unavailable | unavailable | unavailable | unavailable | `R0 配对缺失` |")
    lines.extend(["", "## 阻断原因", ""])
    blockers = list(result.get("blockers", ()))
    lines.extend(f"- `{reason}`" for reason in blockers)
    if not blockers:
        lines.append("无。")
    lines.extend(
        [
            "",
            "## 判定边界",
            "",
            "- shadow 输出、规则回退和仅加载 bundle 均不计学习采用。",
            "- 缺 R0、缺逐回合采用、缺物理结果或作用域不完整时保持 unavailable，并失败关闭。",
            "- 可选指标只在候选和 R0 两侧均可用时计算，不以 0 补齐。",
            "- 审计通过不等于模型晋级，也不构成因果效果结论。",
            "",
        ]
    )
    return "\n".join(lines)


def _audit_scope(
    source: ScopeEvidenceArtifacts,
    *,
    model_bundles: Mapping[str, Path | None],
    expected_preflight_device: str | None,
    require_learned_cells: bool,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "label": source.label,
        "execution_plan_path": str(source.execution_plan_path),
        "storage_mode": source.storage_mode,
        "merge_dir": str(source.evidence_merge_dir),
        "archive_root": (
            None if source.archive_root is None else str(source.archive_root)
        ),
        "archive_verification_performed": False,
        "verified_archive_count": 0,
        "peak_staged_shard_count": 0,
        "sidecar_files": [],
        "source_deletion_performed": False,
        "archive_deletion_performed": False,
        "source_git_commit": None,
        "parent_plan_sha256": None,
        "execution_plan_sha256": None,
        "scope_variants": [],
        "expected_cell_count": 0,
        "accepted_cell_count": 0,
        "formal_evidence_eligible": False,
        "bundle_binding_status": "unavailable",
        "scope_completeness_status": "unavailable",
        "preflight_device": None,
        "cells": [],
        "blockers": [],
        "_internal_cells": [],
    }
    try:
        plan = _load_execution_plan(source.execution_plan_path)
    except (OSError, json.JSONDecodeError, LearningScopeFormalAuditError) as exc:
        code = getattr(exc, "code", "execution_plan_unreadable")
        base["blockers"] = [str(code)]
        return base

    base.update(
        source_git_commit=plan["source"]["git_commit"],
        parent_plan_sha256=plan["parent"]["plan_sha256"],
        execution_plan_sha256=plan["execution_plan_sha256"],
        scope_variants=list(plan["scope"]["variants"]),
        expected_cell_count=int(plan["scope"]["cell_count"]),
        preflight_device=plan["learning_bundles"].get("preflight_device"),
    )
    blockers: list[str] = []
    learned_variants = [
        value for value in plan["scope"]["variants"] if value != "R0"
    ]
    if require_learned_cells and not learned_variants:
        blockers.append("learned_scope_contains_no_learned_variant")
    if not require_learned_cells and any(learned_variants):
        blockers.append("r0_scope_contains_learned_variant")

    bundle_audit, bundle_blockers = _audit_bound_bundles(
        plan,
        model_bundles=model_bundles,
        expected_preflight_device=expected_preflight_device,
        verify_bundle_files=bool(learned_variants),
    )
    blockers.extend(bundle_blockers)
    base["bundle_binding"] = bundle_audit
    base["bundle_binding_status"] = (
        "available_and_valid" if not bundle_blockers else "fail_closed"
    )

    expected_by_id = {
        str(cell["cell_id"]): cell for cell in plan["scope"]["cells"]
    }
    internal_cells: list[dict[str, Any]] = []
    if source.archive_root is not None:
        archive_result = _audit_archive_scope(
            source=source,
            plan=plan,
        )
        base.update(
            archive_verification_performed=bool(
                archive_result.get("archive_verification_performed", False)
            ),
            verified_archive_count=int(
                archive_result.get("verified_archive_count", 0)
            ),
            peak_staged_shard_count=int(
                archive_result.get("peak_staged_shard_count", 0)
            ),
            sidecar_files=list(archive_result.get("sidecar_files", ())),
            source_deletion_performed=bool(
                archive_result.get("source_deletion_performed", False)
            ),
            archive_deletion_performed=bool(
                archive_result.get("archive_deletion_performed", False)
            ),
        )
        blockers.extend(archive_result.get("blockers", ()))
        internal_cells.extend(archive_result.get("cells", ()))
        base["scope_completeness_status"] = (
            "complete"
            if archive_result.get("verified") is True
            else "fail_closed"
        )
    else:
        try:
            merge = _load_merge_evidence(source, plan)
            base["scope_completeness_status"] = "complete"
        except (
            OSError,
            csv.Error,
            json.JSONDecodeError,
            LearningScopeFormalAuditError,
        ) as exc:
            code = getattr(exc, "code", "scope_merge_unreadable")
            blockers.append(str(code))
            base["blockers"] = sorted(set(blockers))
            return base

        rows_by_id = merge["rows_by_cell_id"]
        for cell_id, expected in expected_by_id.items():
            try:
                audited = _audit_cell(
                    source=source,
                    plan=plan,
                    expected=expected,
                    merged_row=rows_by_id[cell_id],
                    progress_row=merge["progress_by_cell_id"][cell_id],
                )
            except (
                OSError,
                csv.Error,
                json.JSONDecodeError,
                Scalable3DOfflineEvaluationError,
                LearningScopeFormalAuditError,
            ) as exc:
                code = getattr(exc, "code", "cell_evidence_unreadable")
                audited = _failed_cell(source.label, expected, str(code))
            internal_cells.append(audited)

    blockers.extend(
        reason
        for audited in internal_cells
        for reason in audited["failure_reasons"]
    )

    accepted_count = sum(
        row["evidence_status"] == "accepted" for row in internal_cells
    )
    base["accepted_cell_count"] = accepted_count
    base["_internal_cells"] = internal_cells
    base["cells"] = [_public_cell(row) for row in internal_cells]
    if accepted_count != len(expected_by_id):
        blockers.append("scope_contains_failed_or_unavailable_cells")
    if len(internal_cells) != len(expected_by_id):
        blockers.append("scope_audited_cell_count_mismatch")
    blockers = sorted(set(blockers))
    base["blockers"] = blockers
    base["formal_evidence_eligible"] = not blockers
    return base


def _audit_archive_scope(
    *,
    source: ScopeEvidenceArtifacts,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    expected_cells = list(plan["scope"]["cells"])
    try:
        merge = _load_archive_merge_evidence(source, plan)
    except (
        OSError,
        csv.Error,
        json.JSONDecodeError,
        LearningScopeFormalAuditError,
    ) as exc:
        code = str(getattr(exc, "code", "archive_scope_merge_unreadable"))
        return {
            "verified": False,
            "archive_verification_performed": False,
            "verified_archive_count": 0,
            "peak_staged_shard_count": 0,
            "sidecar_files": [],
            "source_deletion_performed": False,
            "archive_deletion_performed": False,
            "cells": [
                _failed_cell(source.label, cell, code)
                for cell in expected_cells
            ],
            "blockers": [code],
        }

    merge_shards_by_index = {
        int(row["shard_index"]): row for row in merge["manifest"]["shards"]
    }

    def audit_staged_shard(
        shard_index: int,
        temporary_root: Path,
        staged_shard: Path,
        archive_manifest: Mapping[str, Any],
        archive_record: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del staged_shard, archive_manifest, archive_record
        temporary_plan = temporary_root / source.execution_plan_path.name
        shutil.copy2(source.execution_plan_path, temporary_plan)
        staged_source = ScopeEvidenceArtifacts(
            execution_plan_path=temporary_plan,
            merge_dir=temporary_root,
            label=source.label,
        )
        descriptor = plan["sharding"]["shards"][shard_index]
        shard_cells = [
            cell
            for cell in expected_cells
            if int(cell["shard_index"]) == shard_index
        ]
        progress = _validate_one_shard_evidence(
            execution_root=temporary_root,
            plan=plan,
            merged=merge_shards_by_index[shard_index],
            descriptor=descriptor,
        )
        expected_ids = [str(cell["cell_id"]) for cell in shard_cells]
        _require(
            list(progress) == expected_ids,
            f"archive_shard_progress_inventory_mismatch:{shard_index}",
            "staged shard progress differs from the execution-plan shard",
        )
        cells: list[dict[str, Any]] = []
        for expected in shard_cells:
            cell_id = str(expected["cell_id"])
            try:
                audited = _audit_cell(
                    source=staged_source,
                    plan=plan,
                    expected=expected,
                    merged_row=merge["rows_by_cell_id"][cell_id],
                    progress_row=progress[cell_id],
                )
            except (
                OSError,
                csv.Error,
                json.JSONDecodeError,
                Scalable3DOfflineEvaluationError,
                LearningScopeFormalAuditError,
            ) as exc:
                code = str(getattr(exc, "code", "cell_evidence_unreadable"))
                audited = _failed_cell(source.label, expected, code)
            cells.append(audited)
        return {
            "shard_index": shard_index,
            "cell_ids": expected_ids,
            "cells": cells,
            "offline_evaluation_completed_before_cleanup": True,
        }

    archive_set = audit_verified_formal_shard_archive_set(
        execution_plan_path=source.execution_plan_path,
        archive_root=source.archive_root,
        expected_source_git_commit=str(plan["source"]["git_commit"]),
        expected_execution_plan_sha256=str(plan["execution_plan_sha256"]),
        plan=plan,
        shard_auditor=audit_staged_shard,
    )
    blockers = list(archive_set.get("failure_reasons", ()))
    audited_cells = [
        dict(cell)
        for shard in archive_set.get("shard_results", ())
        for cell in shard.get("cells", ())
    ]

    if archive_set.get("verified") is True:
        merge_audit = audit_archive_merge_bundle(
            merged_scope_dir=source.archive_merge_dir,
            expected_source_git_commit=str(plan["source"]["git_commit"]),
            expected_execution_plan_sha256=str(
                plan["execution_plan_sha256"]
            ),
            expected_scope_cell_count=int(plan["scope"]["cell_count"]),
            expected_parent_cell_count=int(
                plan["parent"]["full_cell_count"]
            ),
            expected_shard_count=int(plan["sharding"]["shard_count"]),
            archive_records=archive_set.get("archives", ()),
        )
        blockers.extend(merge_audit.get("failure_reasons", ()))

    audited_ids = [str(cell.get("cell_id")) for cell in audited_cells]
    expected_ids = [str(cell["cell_id"]) for cell in expected_cells]
    if audited_ids != expected_ids or len(set(audited_ids)) != len(audited_ids):
        blockers.append("archive_scope_cell_order_or_inventory_mismatch")
    audited_by_id = {
        str(cell.get("cell_id")): cell for cell in audited_cells
    }
    complete_cells = [
        audited_by_id.get(str(expected["cell_id"]))
        or _failed_cell(
            source.label,
            expected,
            "archive_scope_cell_not_audited",
        )
        for expected in expected_cells
    ]
    blockers = sorted(set(str(value) for value in blockers))
    return {
        "verified": not blockers,
        "archive_verification_performed": True,
        "verified_archive_count": int(
            archive_set.get("verified_archive_count", 0)
        ),
        "peak_staged_shard_count": int(
            archive_set.get("peak_staged_shard_count", 0)
        ),
        "sidecar_files": list(archive_set.get("sidecar_files", ())),
        "source_deletion_performed": bool(
            archive_set.get("source_deletion_performed", False)
        ),
        "archive_deletion_performed": bool(
            archive_set.get("archive_deletion_performed", False)
        ),
        "cells": complete_cells,
        "blockers": blockers,
    }


def _load_archive_merge_evidence(
    source: ScopeEvidenceArtifacts,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    merge_dir = source.archive_merge_dir
    _require(
        merge_dir is not None
        and not _path_contains_symlink(merge_dir)
        and merge_dir.is_dir(),
        "archive_scope_merge_root_unavailable_or_unsafe",
        "archive scope merge directory is unavailable or uses a symlink",
    )
    manifest_path = merge_dir / "experiment_matrix_scope_manifest.json"
    cells_path = merge_dir / "experiment_matrix_scope_cells.csv"
    episode_dirs_path = merge_dir / "episode_dirs.json"
    for path in (manifest_path, cells_path, episode_dirs_path):
        _require(
            path.is_file() and not path.is_symlink(),
            f"archive_scope_merge_artifact_missing:{path.name}",
            f"archive scope merge artifact is missing or unsafe: {path.name}",
        )
    manifest = _read_json_object(
        manifest_path,
        "archive_scope_merge_manifest",
    )
    expected_count = int(plan["scope"]["cell_count"])
    expected_manifest_fields = {
        "schema_version": "scalable3d-formal-shard-archive-scope-merge-v1",
        "storage_mode": FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
        "source_git_commit": plan["source"]["git_commit"],
        "source_repository_dirty": False,
        "execution_plan_sha256": plan["execution_plan_sha256"],
        "parent_plan_sha256": plan["parent"]["plan_sha256"],
        "parent_formal": True,
        "parent_full_cell_count": plan["parent"]["full_cell_count"],
        "scope_variants": plan["scope"]["variants"],
        "scope_expected_cell_count": expected_count,
        "scope_completed_cell_count": expected_count,
        "scope_complete": True,
        "formal_scope_complete": True,
        "shard_strategy": "scope_index_modulo_v1",
        "shard_count": plan["sharding"]["shard_count"],
        "canonical_episode_directories_materialized": False,
        "archive_set_complete": True,
        "peak_restored_shard_count": 1,
    }
    for field, expected in expected_manifest_fields.items():
        _require(
            manifest.get(field) == expected,
            f"archive_scope_merge_field_mismatch:{field}",
            f"archive scope merge differs from the execution plan: {field}",
        )
    _require(
        manifest.get("status")
        in {"formal_scope_complete", "formal_matrix_complete"},
        "archive_scope_merge_status_not_formal_complete",
        "archive scope merge is not formally complete",
    )
    shards = manifest.get("shards")
    _require(
        isinstance(shards, list)
        and len(shards) == int(plan["sharding"]["shard_count"]),
        "archive_scope_merge_shard_inventory_invalid",
        "archive scope merge shard inventory differs from the plan",
    )
    shard_indices = [
        row.get("shard_index") if isinstance(row, Mapping) else None
        for row in shards
    ]
    _require(
        shard_indices == list(range(len(shards)))
        and len(set(shard_indices)) == len(shard_indices),
        "archive_scope_merge_shard_order_or_identity_invalid",
        "archive scope merge shard indices are missing, duplicated, or unordered",
    )

    with cells_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    _require(
        len(rows) == expected_count,
        "archive_scope_merge_cell_row_count_mismatch",
        "archive scope merge cell row count differs from the plan",
    )
    expected_cells = list(plan["scope"]["cells"])
    rows_by_cell_id: dict[str, dict[str, Any]] = {}
    logical_paths: list[str] = []
    for scope_index, row in enumerate(rows):
        expected = expected_cells[scope_index]
        _require(
            _strict_int_text(row.get("scope_index")) == scope_index,
            "archive_scope_merge_cell_order_invalid",
            "archive scope merge cells are not in canonical scope order",
        )
        for field in ("variant", "scenario", "comparison_key"):
            _require(
                row.get(field) == str(expected[field]),
                f"archive_scope_merge_cell_field_mismatch:{field}",
                f"archive scope merge cell identity mismatch: {field}",
            )
        for field in ("scale", "seed"):
            _require(
                _strict_int_text(row.get(field)) == int(expected[field]),
                f"archive_scope_merge_cell_field_mismatch:{field}",
                f"archive scope merge cell identity mismatch: {field}",
            )
        relative = _logical_relative_path(
            row.get("episode_relative_path"),
            "archive_scope_merge_episode_path_invalid",
        )
        rows_by_cell_id[str(expected["cell_id"])] = row
        logical_paths.append(relative)
    _require(
        len(rows_by_cell_id) == expected_count
        and len(set(logical_paths)) == expected_count,
        "archive_scope_merge_cell_duplicate_or_missing",
        "archive scope merge contains duplicate or missing cells",
    )

    episode_dirs = _read_json_object(
        episode_dirs_path,
        "archive_scope_episode_dirs",
    )
    _require(
        episode_dirs.get("schema_version")
        == "scalable3d-formal-shard-archive-scope-merge-v1"
        and episode_dirs.get("storage_mode")
        == FORMAL_SHARD_ARCHIVE_STORAGE_MODE
        and episode_dirs.get("execution_plan_sha256")
        == plan["execution_plan_sha256"]
        and episode_dirs.get("episode_count") == expected_count
        and episode_dirs.get("canonical_directories_materialized") is False,
        "archive_scope_merge_episode_inventory_invalid",
        "archive episode index is not bound to the archive scope",
    )
    _require(
        episode_dirs.get("paths_relative_to_execution_root") == logical_paths,
        "archive_scope_merge_episode_inventory_mismatch",
        "archive episode index differs from the merge cell inventory",
    )
    return {
        "manifest": manifest,
        "rows_by_cell_id": rows_by_cell_id,
        "logical_episode_paths": logical_paths,
    }


def _load_execution_plan(path: Path) -> dict[str, Any]:
    plan = _read_json_object(path, "execution_plan")
    _require(
        plan.get("schema_version") == _EXECUTION_PLAN_SCHEMA,
        "execution_plan_schema_mismatch",
        "execution plan schema is unsupported",
    )
    expected_digest = _required_sha256(
        plan.get("execution_plan_sha256"),
        "execution_plan_sha256_invalid",
    )
    unsigned = dict(plan)
    unsigned.pop("execution_plan_sha256", None)
    _require(
        _digest_json(unsigned) == expected_digest,
        "execution_plan_digest_mismatch",
        "execution plan digest does not match content",
    )
    source = _mapping(plan.get("source"), "execution_plan_source_invalid")
    commit = source.get("git_commit")
    _require(
        isinstance(commit, str) and _GIT_COMMIT_RE.fullmatch(commit) is not None,
        "execution_plan_source_commit_invalid",
        "execution plan source commit is invalid",
    )
    _require(
        source.get("repository_dirty") is False,
        "execution_plan_source_not_clean",
        "formal learned evidence requires repository_dirty=false",
    )

    parent = _mapping(plan.get("parent"), "execution_plan_parent_invalid")
    _require(
        parent.get("formal") is True,
        "execution_plan_parent_not_formal",
        "formal learned evidence requires parent.formal=true",
    )
    parent_plan = _mapping(
        parent.get("plan"),
        "execution_plan_parent_plan_invalid",
    )
    _require(
        parent_plan.get("formal") is True
        and parent_plan.get("allow_rule_fallback") is False,
        "execution_plan_parent_allows_fallback",
        "formal parent must disable rule fallback",
    )
    full_cells = parent.get("full_cells")
    _require(
        isinstance(full_cells, list) and bool(full_cells),
        "execution_plan_parent_cells_missing",
        "parent cell inventory is missing",
    )
    _require(
        _nonnegative_int(parent.get("full_cell_count")) == len(full_cells),
        "execution_plan_parent_cell_count_mismatch",
        "parent full cell count does not match inventory",
    )
    parent_digest = _required_sha256(
        parent.get("plan_sha256"),
        "execution_plan_parent_digest_invalid",
    )
    _require(
        _digest_json({"plan": parent_plan, "cells": full_cells})
        == parent_digest,
        "execution_plan_parent_digest_mismatch",
        "parent plan digest does not match inventory",
    )
    full_ids = [str(item.get("cell_id", "")) for item in full_cells]
    _require(
        all(full_ids) and len(set(full_ids)) == len(full_ids),
        "execution_plan_parent_cell_identity_invalid",
        "parent cell identities are empty or duplicated",
    )

    scope = _mapping(plan.get("scope"), "execution_plan_scope_invalid")
    variants = scope.get("variants")
    cells = scope.get("cells")
    _require(
        isinstance(variants, list)
        and bool(variants)
        and len(set(variants)) == len(variants)
        and all(value in _VARIANT_COMPONENTS for value in variants),
        "execution_plan_scope_variants_invalid",
        "scope variants are missing, duplicated, or unknown",
    )
    _require(
        isinstance(cells, list) and bool(cells),
        "execution_plan_scope_cells_missing",
        "scope cells are missing",
    )
    _require(
        _nonnegative_int(scope.get("cell_count")) == len(cells),
        "execution_plan_scope_cell_count_mismatch",
        "scope cell count does not match inventory",
    )
    _require(
        _digest_json(cells)
        == _required_sha256(
            scope.get("cells_sha256"),
            "execution_plan_scope_digest_invalid",
        ),
        "execution_plan_scope_digest_mismatch",
        "scope cell digest does not match inventory",
    )
    scope_ids = [str(item.get("cell_id", "")) for item in cells]
    _require(
        all(scope_ids) and len(set(scope_ids)) == len(scope_ids),
        "execution_plan_scope_cell_identity_invalid",
        "scope cell identities are empty or duplicated",
    )
    _require(
        [item.get("scope_index") for item in cells] == list(range(len(cells))),
        "execution_plan_scope_index_invalid",
        "scope indices are not contiguous",
    )
    parent_by_id = {str(item["cell_id"]): item for item in full_cells}
    for cell in cells:
        cell_id = str(cell["cell_id"])
        parent_cell = parent_by_id.get(cell_id)
        _require(
            parent_cell is not None,
            "execution_plan_scope_cell_not_in_parent",
            f"scope cell is absent from parent inventory: {cell_id}",
        )
        for field in (
            "global_index",
            "variant",
            "scenario",
            "scale",
            "seed",
            "comparison_key",
        ):
            _require(
                cell.get(field) == parent_cell.get(field),
                "execution_plan_scope_parent_identity_mismatch",
                f"scope cell differs from parent: {cell_id}:{field}",
            )
        _require(
            cell.get("variant") in variants,
            "execution_plan_scope_variant_inventory_mismatch",
            f"cell variant is outside scope variants: {cell_id}",
        )
    _validate_sharding_inventory(plan)
    _validate_model_binding_structure(plan)
    return plan


def _validate_sharding_inventory(plan: Mapping[str, Any]) -> None:
    sharding = _mapping(
        plan.get("sharding"),
        "execution_plan_sharding_invalid",
    )
    _require(
        sharding.get("strategy") == "scope_index_modulo_v1",
        "execution_plan_sharding_strategy_invalid",
        "unsupported shard strategy",
    )
    count = _positive_int(sharding.get("shard_count"))
    shards = sharding.get("shards")
    _require(
        isinstance(shards, list) and len(shards) == count,
        "execution_plan_shard_inventory_invalid",
        "shard inventory count mismatch",
    )
    cells = plan["scope"]["cells"]
    for index, descriptor in enumerate(shards):
        expected = [
            cell for cell in cells if int(cell.get("shard_index", -1)) == index
        ]
        _require(
            descriptor.get("shard_index") == index
            and descriptor.get("cell_count") == len(expected)
            and descriptor.get("cell_ids")
            == [cell["cell_id"] for cell in expected]
            and descriptor.get("cells_sha256") == _digest_json(expected),
            "execution_plan_shard_descriptor_mismatch",
            f"shard descriptor does not match scope: {index}",
        )


def _validate_model_binding_structure(plan: Mapping[str, Any]) -> None:
    variants = tuple(plan["scope"]["variants"])
    required = _required_components(variants)
    binding = _mapping(
        plan.get("learning_bundles"),
        "model_bundle_binding_missing",
    )
    _require(
        binding.get("schema_version") == _MODEL_BINDING_SCHEMA,
        "model_bundle_binding_schema_mismatch",
        "model bundle binding schema is unsupported",
    )
    _require(
        binding.get("required_components") == list(required),
        "model_bundle_required_components_mismatch",
        "model bundle required component list mismatch",
    )
    components = _mapping(
        binding.get("components"),
        "model_bundle_component_inventory_invalid",
    )
    _require(
        set(components) == set(required),
        "model_bundle_component_inventory_mismatch",
        "model bundle component inventory mismatch",
    )
    for component in required:
        descriptor = _mapping(
            components.get(component),
            f"model_bundle_descriptor_invalid:{component}",
        )
        _require(
            descriptor.get("component") == component
            and _positive_int(descriptor.get("file_count")) > 0
            and _nonnegative_int(descriptor.get("total_size_bytes")) >= 0,
            f"model_bundle_descriptor_invalid:{component}",
            f"model bundle descriptor is invalid: {component}",
        )
        _required_sha256(
            descriptor.get("manifest_sha256"),
            f"model_bundle_manifest_digest_invalid:{component}",
        )
        _required_sha256(
            descriptor.get("tree_sha256"),
            f"model_bundle_tree_digest_invalid:{component}",
        )
    binding_payload = {
        "required_components": list(required),
        "components": dict(components),
    }
    _require(
        _digest_json(binding_payload)
        == _required_sha256(
            binding.get("binding_sha256"),
            "model_bundle_binding_digest_invalid",
        ),
        "model_bundle_binding_digest_mismatch",
        "model bundle binding digest mismatch",
    )
    device = binding.get("preflight_device")
    _require(
        isinstance(device, str) and bool(device.strip()),
        "model_bundle_preflight_device_invalid",
        "preflight device is missing or invalid",
    )
    preflight = _mapping(
        binding.get("variant_preflight"),
        "model_bundle_variant_preflight_invalid",
    )
    _require(
        set(preflight) == set(variants),
        "model_bundle_variant_preflight_inventory_mismatch",
        "variant preflight inventory does not match scope",
    )
    for variant in variants:
        record = _mapping(
            preflight.get(variant),
            f"model_bundle_variant_preflight_invalid:{variant}",
        )
        expected_components = list(_VARIANT_COMPONENTS[variant])
        expected_status = (
            "deterministic_no_model" if variant == "R0" else "assist_resolved"
        )
        _require(
            record.get("variant") == variant
            and record.get("required_components") == expected_components
            and record.get("status") == expected_status,
            f"model_bundle_variant_preflight_mismatch:{variant}",
            f"variant preflight does not prove the declared mode: {variant}",
        )
        if variant != "R0":
            _required_sha256(
                record.get("diagnostics_sha256"),
                f"model_bundle_preflight_diagnostics_invalid:{variant}",
            )
            versions = _mapping(
                record.get("resolved_versions"),
                f"model_bundle_preflight_versions_invalid:{variant}",
            )
            _require(
                set(versions) == set(_VERSION_FIELDS)
                and all(
                    isinstance(versions[field], str)
                    and bool(versions[field].strip())
                    for field in _VERSION_FIELDS
                ),
                f"model_bundle_preflight_versions_invalid:{variant}",
                f"variant preflight versions are incomplete: {variant}",
            )


def _audit_bound_bundles(
    plan: Mapping[str, Any],
    *,
    model_bundles: Mapping[str, Path | None],
    expected_preflight_device: str | None,
    verify_bundle_files: bool,
) -> tuple[dict[str, Any], list[str]]:
    binding = plan["learning_bundles"]
    required = tuple(binding["required_components"])
    blockers: list[str] = []
    device = str(binding.get("preflight_device", "")).strip()
    if (
        expected_preflight_device is not None
        and device != expected_preflight_device
    ):
        blockers.append("model_bundle_preflight_device_mismatch")
    provided = {
        name for name, path in model_bundles.items() if path is not None
    }
    unknown = provided - set(_RUNTIME_COMPONENT_NAMES)
    extra = provided - set(required)
    if unknown:
        blockers.append("model_bundle_unknown_component_input")
    if extra:
        blockers.append("model_bundle_undeclared_component_input")

    components: dict[str, Any] = {}
    for component in required:
        expected = binding["components"][component]
        path = model_bundles.get(component)
        audit = {
            "path": None if path is None else str(path),
            "available": False,
            "manifest_sha256_match": False,
            "tree_sha256_match": False,
            "file_count_match": False,
            "total_size_bytes_match": False,
            "failure_reason": None,
        }
        if not verify_bundle_files:
            audit.update(
                available=True,
                manifest_sha256_match=True,
                tree_sha256_match=True,
                file_count_match=True,
                total_size_bytes_match=True,
            )
        elif path is None or not path.is_dir():
            audit["failure_reason"] = "model_bundle_path_missing"
            blockers.append(f"model_bundle_path_missing:{component}")
        else:
            manifest = path / "manifest.json"
            if not manifest.is_file():
                audit["failure_reason"] = "model_bundle_manifest_missing"
                blockers.append(f"model_bundle_manifest_missing:{component}")
            else:
                inventory = _tree_inventory(path)
                actual = {
                    "manifest_sha256": _sha256_file(manifest),
                    "tree_sha256": _digest_json(inventory),
                    "file_count": len(inventory),
                    "total_size_bytes": sum(
                        int(item["size_bytes"]) for item in inventory
                    ),
                }
                audit.update(
                    available=True,
                    manifest_sha256_match=(
                        actual["manifest_sha256"]
                        == expected["manifest_sha256"]
                    ),
                    tree_sha256_match=(
                        actual["tree_sha256"] == expected["tree_sha256"]
                    ),
                    file_count_match=(
                        actual["file_count"] == expected["file_count"]
                    ),
                    total_size_bytes_match=(
                        actual["total_size_bytes"]
                        == expected["total_size_bytes"]
                    ),
                    actual=actual,
                )
                if not all(
                    audit[field]
                    for field in (
                        "manifest_sha256_match",
                        "tree_sha256_match",
                        "file_count_match",
                        "total_size_bytes_match",
                    )
                ):
                    audit["failure_reason"] = "model_bundle_binding_mismatch"
                    blockers.append(
                        f"model_bundle_binding_mismatch:{component}"
                    )
        components[component] = audit
    return {
        "schema_version": binding.get("schema_version"),
        "binding_sha256": binding.get("binding_sha256"),
        "required_components": list(required),
        "preflight_device": device,
        "components": components,
    }, sorted(set(blockers))


def _load_merge_evidence(
    source: ScopeEvidenceArtifacts,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    merge_dir = source.evidence_merge_dir
    manifest_path = merge_dir / "experiment_matrix_scope_manifest.json"
    cells_path = merge_dir / "experiment_matrix_scope_cells.csv"
    episode_dirs_path = merge_dir / "episode_dirs.json"
    checksum_path = merge_dir / "SHA256SUMS"
    for path in (manifest_path, cells_path, episode_dirs_path, checksum_path):
        _require(
            path.is_file(),
            f"scope_merge_artifact_missing:{path.name}",
            f"scope merge artifact is missing: {path}",
        )
    _validate_checksum_file(
        checksum_path,
        required_names={
            manifest_path.name,
            cells_path.name,
            episode_dirs_path.name,
        },
    )
    manifest = _read_json_object(manifest_path, "scope_merge_manifest")
    _require(
        manifest.get("schema_version") == _SCOPE_MERGE_SCHEMA,
        "scope_merge_schema_mismatch",
        "scope merge schema is unsupported",
    )
    expected_count = int(plan["scope"]["cell_count"])
    checks = {
        "source_git_commit": plan["source"]["git_commit"],
        "execution_plan_sha256": plan["execution_plan_sha256"],
        "parent_plan_sha256": plan["parent"]["plan_sha256"],
        "parent_formal": True,
        "scope_variants": plan["scope"]["variants"],
        "scope_expected_cell_count": expected_count,
        "scope_completed_cell_count": expected_count,
        "scope_complete": True,
        "formal_scope_complete": True,
        "shard_strategy": "scope_index_modulo_v1",
        "shard_count": plan["sharding"]["shard_count"],
    }
    for field, expected in checks.items():
        _require(
            manifest.get(field) == expected,
            f"scope_merge_field_mismatch:{field}",
            f"scope merge field differs from execution plan: {field}",
        )
    _require(
        manifest.get("status")
        in {"formal_scope_complete", "formal_matrix_complete"},
        "scope_merge_status_not_formal_complete",
        "scope merge is not formally complete",
    )

    with cells_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    _require(
        len(rows) == expected_count,
        "scope_merge_cell_row_count_mismatch",
        "merged cell row count differs from execution scope",
    )
    expected_by_scope = {
        int(cell["scope_index"]): cell for cell in plan["scope"]["cells"]
    }
    rows_by_cell_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            scope_index = int(row["scope_index"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LearningScopeFormalAuditError(
                "scope_merge_cell_identity_invalid",
                "merged row scope_index is invalid",
            ) from exc
        expected = expected_by_scope.get(scope_index)
        _require(
            expected is not None,
            "scope_merge_cell_out_of_scope",
            f"merged row is outside scope: {scope_index}",
        )
        for field in ("variant", "scenario", "comparison_key"):
            _require(
                row.get(field) == str(expected[field]),
                f"scope_merge_cell_field_mismatch:{field}",
                f"merged row identity mismatch: {scope_index}:{field}",
            )
        for field in ("scale", "seed"):
            _require(
                _strict_int_text(row.get(field)) == int(expected[field]),
                f"scope_merge_cell_field_mismatch:{field}",
                f"merged row identity mismatch: {scope_index}:{field}",
            )
        rows_by_cell_id[str(expected["cell_id"])] = row
    _require(
        len(rows_by_cell_id) == expected_count,
        "scope_merge_cell_duplicate_or_missing",
        "merged scope contains duplicate or missing cells",
    )

    episode_dirs = _read_json_object(episode_dirs_path, "episode_dirs")
    _require(
        episode_dirs.get("schema_version") == _SCOPE_MERGE_SCHEMA
        and episode_dirs.get("execution_plan_sha256")
        == plan["execution_plan_sha256"]
        and episode_dirs.get("episode_count") == expected_count,
        "scope_merge_episode_inventory_invalid",
        "episode directory inventory is not bound to the scope",
    )
    expected_paths = [row.get("episode_relative_path") for row in rows]
    _require(
        episode_dirs.get("paths_relative_to_execution_root") == expected_paths,
        "scope_merge_episode_inventory_mismatch",
        "episode path inventory differs from merged cells",
    )
    progress_by_cell_id = _validate_shard_evidence(
        source.execution_plan_path.parent,
        plan,
        manifest,
    )
    _require(
        set(progress_by_cell_id) == set(rows_by_cell_id),
        "scope_merge_progress_inventory_mismatch",
        "validated shard progress differs from merged scope",
    )
    return {
        "manifest": manifest,
        "rows_by_cell_id": rows_by_cell_id,
        "progress_by_cell_id": progress_by_cell_id,
    }


def _validate_shard_evidence(
    execution_root: Path,
    plan: Mapping[str, Any],
    merge_manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    merge_shards = merge_manifest.get("shards")
    _require(
        isinstance(merge_shards, list)
        and len(merge_shards) == int(plan["sharding"]["shard_count"]),
        "scope_merge_shard_inventory_invalid",
        "merged shard inventory count mismatch",
    )
    descriptors = list(plan["sharding"]["shards"])
    _require(
        [
            row.get("shard_index") if isinstance(row, Mapping) else None
            for row in merge_shards
        ]
        == list(range(len(descriptors))),
        "scope_merge_shard_order_or_identity_invalid",
        "merged shards are missing, duplicated, or out of order",
    )
    progress_by_cell: dict[str, dict[str, Any]] = {}
    for descriptor, merged in zip(descriptors, merge_shards, strict=True):
        _require(
            isinstance(merged, Mapping)
            and merged.get("shard_id") == descriptor.get("shard_id"),
            "scope_merge_unknown_shard",
            "merged scope references an unknown shard",
        )
        progress_by_cell.update(
            _validate_one_shard_evidence(
                execution_root=execution_root,
                plan=plan,
                merged=merged,
                descriptor=descriptor,
            )
        )
    return progress_by_cell


def _validate_one_shard_evidence(
    *,
    execution_root: Path,
    plan: Mapping[str, Any],
    merged: Mapping[str, Any],
    descriptor: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    shard_id = str(descriptor["shard_id"])
    _require(
        merged.get("shard_id") == shard_id
        and merged.get("shard_index") == descriptor.get("shard_index"),
        f"scope_merge_unknown_shard:{shard_id}",
        f"merged scope references the wrong shard: {shard_id}",
    )
    shard_dir = execution_root / "shards" / shard_id
    plan_path = shard_dir / "shard_plan.json"
    progress_path = shard_dir / "progress.jsonl"
    checkpoint_path = shard_dir / "checkpoint.json"
    for name, path in (
        ("shard_plan_sha256", plan_path),
        ("progress_sha256", progress_path),
        ("checkpoint_sha256", checkpoint_path),
    ):
        _require(
            path.is_file() and _sha256_file(path) == merged.get(name),
            f"scope_merge_shard_digest_mismatch:{shard_id}:{name}",
            f"merged shard digest mismatch: {shard_id}:{name}",
        )
    expected_cells = [
        cell
        for cell in plan["scope"]["cells"]
        if int(cell["shard_index"]) == int(descriptor["shard_index"])
    ]
    static = _read_json_object(plan_path, "shard_plan")
    _require(
        static.get("schema_version") == _SHARD_PLAN_SCHEMA
        and static.get("execution_plan_sha256")
        == plan["execution_plan_sha256"]
        and static.get("source_git_commit") == plan["source"]["git_commit"]
        and static.get("parent_plan_sha256")
        == plan["parent"]["plan_sha256"]
        and static.get("descriptor") == descriptor
        and static.get("cells") == expected_cells
        and static.get("cells_sha256") == _digest_json(expected_cells),
        f"shard_plan_binding_mismatch:{shard_id}",
        f"stored shard plan differs from execution plan: {shard_id}",
    )
    progress_rows = _read_jsonl_objects(progress_path, "shard_progress")
    _require(
        len(progress_rows) == len(expected_cells),
        f"shard_progress_count_mismatch:{shard_id}",
        f"shard progress is incomplete: {shard_id}",
    )
    progress_by_cell: dict[str, dict[str, Any]] = {}
    for sequence, (row, expected) in enumerate(
        zip(progress_rows, expected_cells, strict=True)
    ):
        _require(
            row.get("schema_version") == _SHARD_PROGRESS_SCHEMA
            and row.get("execution_plan_sha256")
            == plan["execution_plan_sha256"]
            and row.get("sequence") == sequence
            and row.get("cell_id") == expected["cell_id"]
            and row.get("scope_index") == expected["scope_index"]
            and row.get("shard_index") == expected["shard_index"]
            and row.get("shard_sequence") == expected["shard_sequence"],
            f"shard_progress_binding_mismatch:{expected['cell_id']}",
            f"shard progress row differs from expected cell: {expected['cell_id']}",
        )
        _required_sha256(
            row.get("cell_result_sha256"),
            f"shard_progress_cell_digest_invalid:{expected['cell_id']}",
        )
        _required_sha256(
            row.get("episode_artifact_tree_sha256"),
            f"shard_progress_episode_digest_invalid:{expected['cell_id']}",
        )
        progress_by_cell[str(expected["cell_id"])] = row
    checkpoint = _read_json_object(checkpoint_path, "shard_checkpoint")
    _require(
        checkpoint.get("schema_version") == _SHARD_CHECKPOINT_SCHEMA
        and checkpoint.get("execution_plan_sha256")
        == plan["execution_plan_sha256"]
        and checkpoint.get("source_git_commit")
        == plan["source"]["git_commit"]
        and checkpoint.get("shard_id") == shard_id
        and checkpoint.get("status") == "complete"
        and checkpoint.get("expected_cell_count") == len(expected_cells)
        and checkpoint.get("completed_cell_count") == len(expected_cells)
        and checkpoint.get("next_sequence") == len(expected_cells)
        and checkpoint.get("progress_sha256") == _sha256_file(progress_path),
        f"shard_checkpoint_incomplete_or_invalid:{shard_id}",
        f"shard checkpoint is incomplete or invalid: {shard_id}",
    )
    return progress_by_cell


def _audit_cell(
    *,
    source: ScopeEvidenceArtifacts,
    plan: Mapping[str, Any],
    expected: Mapping[str, Any],
    merged_row: Mapping[str, Any],
    progress_row: Mapping[str, Any],
) -> dict[str, Any]:
    execution_root = source.execution_plan_path.parent
    result_path = _resolve_within(
        execution_root,
        progress_row.get("cell_result_relative_path"),
        "cell_result_path_invalid",
    )
    _require(
        result_path.name == "cell_result.json"
        and result_path.is_file()
        and _sha256_file(result_path)
        == progress_row.get("cell_result_sha256")
        == merged_row.get("cell_result_sha256"),
        "cell_result_digest_mismatch",
        f"cell result digest mismatch: {expected['cell_id']}",
    )
    record = _read_json_object(result_path, "cell_result")
    _require(
        record.get("schema_version") == _CELL_RESULT_SCHEMA
        and record.get("execution_plan_sha256")
        == plan["execution_plan_sha256"]
        and record.get("parent_plan_sha256")
        == plan["parent"]["plan_sha256"]
        and record.get("source_git_commit")
        == plan["source"]["git_commit"]
        and record.get("cell") == dict(expected)
        and record.get("status") == "complete",
        "cell_result_binding_mismatch",
        f"cell result is not bound to the expected plan: {expected['cell_id']}",
    )
    episode_dir = _resolve_within(
        execution_root,
        record.get("episode_relative_path"),
        "cell_episode_path_invalid",
    )
    _require(
        episode_dir == result_path.parent / "episode"
        and merged_row.get("episode_relative_path")
        == record.get("episode_relative_path"),
        "cell_episode_path_mismatch",
        f"cell episode path mismatch: {expected['cell_id']}",
    )
    for name in _REQUIRED_EPISODE_ARTIFACTS:
        _require(
            (episode_dir / name).is_file(),
            f"cell_episode_artifact_missing:{name}",
            f"required episode artifact is missing: {name}",
        )
    artifact_digest = _tree_digest(episode_dir)
    _require(
        artifact_digest
        == record.get("artifact_tree_sha256")
        == progress_row.get("episode_artifact_tree_sha256")
        == merged_row.get("episode_artifact_tree_sha256"),
        "cell_episode_artifact_tree_mismatch",
        f"episode artifact tree digest mismatch: {expected['cell_id']}",
    )

    manifest = _read_json_object(episode_dir / "manifest.json", "manifest")
    config = _read_json_object(
        episode_dir / "scenario_config.json",
        "scenario_config",
    )
    summary = _read_json_object(episode_dir / "summary.json", "summary")
    _require(
        manifest.get("git_commit") == plan["source"]["git_commit"]
        and manifest.get("repository_dirty") is False,
        "cell_episode_source_not_clean_or_mismatched",
        f"episode source does not match clean plan: {expected['cell_id']}",
    )
    metadata = _mapping(
        config.get("metadata"),
        "cell_episode_metadata_missing",
    )
    _require(
        metadata.get("algorithm_variant") == expected["variant"]
        and metadata.get("comparison_key") == expected["comparison_key"]
        and metadata.get("matrix_execution_plan_sha256")
        == plan["execution_plan_sha256"]
        and metadata.get("matrix_parent_plan_sha256")
        == plan["parent"]["plan_sha256"],
        "cell_episode_matrix_lineage_mismatch",
        f"episode matrix lineage mismatch: {expected['cell_id']}",
    )
    _require(
        summary.get("finite_state") is True,
        "cell_episode_nonfinite",
        f"episode finite_state is not true: {expected['cell_id']}",
    )
    _require(
        _nonnegative_int(summary.get("online_truth_use_count")) == 0,
        "cell_episode_online_truth_nonzero_or_missing",
        f"episode online truth count is missing or non-zero: {expected['cell_id']}",
    )
    intercepted = _optional_nonnegative_int(
        summary.get("intercepted_target_count")
    )
    _require(
        intercepted is not None,
        "cell_episode_physical_result_missing",
        f"episode physical result is missing: {expected['cell_id']}",
    )
    metrics = _mapping(record.get("metrics"), "cell_result_metrics_invalid")
    _require(
        metrics.get("finite_state") is True
        and _nonnegative_int(metrics.get("online_truth_use_count")) == 0
        and _optional_nonnegative_int(metrics.get("intercepted_target_count"))
        == intercepted,
        "cell_result_metrics_mismatch",
        f"cell metrics differ from episode summary: {expected['cell_id']}",
    )

    learning = _audit_cell_learning_evidence(
        expected=expected,
        plan=plan,
        record=record,
        manifest=manifest,
        config=config,
        summary=summary,
    )
    offline_row = evaluate_scalable_3d_episode(episode_dir)
    failures: list[str] = []
    if (
        offline_row.get("online_truth_use_count_availability") != "available"
        or offline_row.get("online_truth_use_count") != 0
        or offline_row.get("online_truth_field_violation_count_availability")
        != "available"
        or offline_row.get("online_truth_field_violation_count") != 0
    ):
        failures.append("cell_offline_online_truth_evidence_invalid")
    if expected["variant"] != "R0":
        if offline_row.get("variant_execution_valid") is not True:
            failures.append("cell_actual_assist_adoption_invalid")
        failures.extend(
            _strict_actual_adoption_failures(
                expected["variant"],
                offline_row,
            )
        )
    elif offline_row.get("variant_execution_valid") is not True:
        failures.append("cell_r0_learning_isolation_invalid")

    physical_metrics = {
        "intercepted_target_count": _available(intercepted),
        "offline_proximity_within_5m_count": _metric_evidence(
            offline_row,
            "offline_proximity_within_5m_count",
        ),
        "offline_proximity_unique_target_count": _metric_evidence(
            offline_row,
            "offline_proximity_unique_target_count",
        ),
    }
    for name, evidence in physical_metrics.items():
        if evidence["availability"] != "available":
            failures.append(f"cell_physical_metric_unavailable:{name}")
    metric_evidence = {
        name: (
            _available(intercepted)
            if name == "intercepted_target_count"
            else _metric_evidence(offline_row, name)
        )
        for name in _PAIR_METRIC_POLICY
    }
    failures = sorted(set(failures))
    assist_status = (
        "not_applicable_r0"
        if expected["variant"] == "R0"
        else (
            "actual_assist_adopted"
            if not any("assist" in reason for reason in failures)
            else "unavailable_or_not_adopted"
        )
    )
    return {
        "scope_label": source.label,
        "variant": expected["variant"],
        "scenario": expected["scenario"],
        "scale": int(expected["scale"]),
        "seed": int(expected["seed"]),
        "comparison_key": expected["comparison_key"],
        "cell_id": expected["cell_id"],
        "parent_plan_sha256": plan["parent"]["plan_sha256"],
        "source_git_commit": plan["source"]["git_commit"],
        "paired_exogenous_config_sha256": record.get(
            "paired_exogenous_config_sha256"
        ),
        "sensor_random_schedule_version": record.get(
            "sensor_random_schedule_version"
        ),
        "evidence_status": "accepted" if not failures else "fail_closed",
        "assist_adoption_status": assist_status,
        "online_truth_status": (
            "zero_verified"
            if "cell_offline_online_truth_evidence_invalid" not in failures
            else "unavailable_or_nonzero"
        ),
        "physical_result_status": (
            "available"
            if not any(
                reason.startswith("cell_physical_metric_unavailable:")
                for reason in failures
            )
            else "unavailable"
        ),
        "learning_evidence": learning,
        "physical_metrics": physical_metrics,
        "metric_evidence": metric_evidence,
        "failure_reasons": failures,
    }


def _audit_cell_learning_evidence(
    *,
    expected: Mapping[str, Any],
    plan: Mapping[str, Any],
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    variant = str(expected["variant"])
    if variant == "R0":
        _require(
            record.get("learning_runtime") is None,
            "r0_cell_contains_learning_runtime_binding",
            "R0 cell must not carry a learned cell binding",
        )
        return {
            "status": "deterministic_r0",
            "required_components": [],
            "actual_assist_adoption": "not_applicable",
        }
    binding = plan["learning_bundles"]
    preflight = binding["variant_preflight"][variant]
    cell_learning = _mapping(
        record.get("learning_runtime"),
        "cell_learning_runtime_binding_missing",
    )
    _require(
        cell_learning.get("bundle_binding_sha256")
        == binding.get("binding_sha256"),
        "cell_learning_bundle_binding_mismatch",
        f"cell bundle binding mismatch: {expected['cell_id']}",
    )
    config_metadata = _mapping(
        config.get("metadata"),
        "cell_episode_metadata_missing",
    )
    config_runtime = _mapping(
        config_metadata.get("learning_runtime"),
        "cell_learning_config_diagnostics_missing",
    )
    summary_diagnostics = _mapping(
        summary.get("module_final_diagnostics"),
        "cell_learning_summary_diagnostics_missing",
    )
    summary_runtime = _mapping(
        summary_diagnostics.get("learning_runtime"),
        "cell_learning_summary_runtime_missing",
    )
    _require(
        _canonical_json(config_runtime) == _canonical_json(summary_runtime),
        "cell_learning_config_summary_diagnostics_mismatch",
        f"learning diagnostics differ between config and summary: {expected['cell_id']}",
    )
    diagnostics_sha = _digest_json(config_runtime)
    _require(
        diagnostics_sha
        == cell_learning.get("diagnostics_sha256")
        == preflight.get("diagnostics_sha256"),
        "cell_learning_diagnostics_preflight_mismatch",
        f"cell diagnostics differ from preflight: {expected['cell_id']}",
    )
    _require(
        config_runtime.get("device")
        == binding.get("preflight_device"),
        "cell_learning_device_preflight_mismatch",
        f"cell learning device differs from preflight: {expected['cell_id']}",
    )
    versions = _mapping(
        cell_learning.get("resolved_versions"),
        "cell_learning_resolved_versions_missing",
    )
    _require(
        dict(versions) == dict(preflight.get("resolved_versions", {})),
        "cell_learning_versions_preflight_mismatch",
        f"cell versions differ from preflight: {expected['cell_id']}",
    )
    for field in _VERSION_FIELDS:
        _require(
            config.get(field) == versions.get(field)
            and manifest.get(field) == versions.get(field),
            f"cell_learning_version_artifact_mismatch:{field}",
            f"cell version differs across evidence artifacts: {field}",
        )
    for component in _VARIANT_COMPONENTS[variant]:
        runtime_name = _RUNTIME_COMPONENT_NAMES[component]
        diagnostics = _mapping(
            config_runtime.get(runtime_name),
            f"cell_learning_component_diagnostics_missing:{component}",
        )
        _require(
            diagnostics.get("requested_mode") == "assist"
            and diagnostics.get("effective_mode") == "assist"
            and diagnostics.get("bundle_loaded") is True
            and diagnostics.get("fallback_reason") is None,
            f"cell_learning_component_not_assist:{component}",
            f"required learning component did not remain in assist: {component}",
        )
    return {
        "status": "preflight_and_episode_consistent",
        "required_components": list(_VARIANT_COMPONENTS[variant]),
        "bundle_binding_sha256": binding.get("binding_sha256"),
        "diagnostics_sha256": diagnostics_sha,
        "resolved_versions": dict(versions),
        "preflight_device": binding.get("preflight_device"),
    }


def _strict_actual_adoption_failures(
    variant: str,
    row: Mapping[str, Any],
) -> list[str]:
    failures: list[str] = []
    for component in _VARIANT_COMPONENTS[variant]:
        if component == "d3":
            _require_positive_available_metric(
                row,
                "d3_learning_applied_count",
                component,
                failures,
            )
        elif component == "d4":
            _require_positive_available_metric(
                row,
                "d4_advice_control_adoption_count",
                component,
                failures,
            )
        elif component == "d5_graph":
            if (
                row.get("d5_probability_source_availability") != "available"
                or row.get("d5_probability_source") != "loaded_edge_model"
                or row.get("d5_scoring_status_availability") != "available"
                or row.get("d5_scoring_status") != "model_scored"
                or row.get("d5_model_fallback_event_count_availability")
                != "available"
                or row.get("d5_model_fallback_event_count") != 0
            ):
                failures.append(
                    "cell_actual_assist_not_adopted:d5_graph"
                )
            _require_positive_available_metric(
                row,
                "d5_candidate_edge_count",
                component,
                failures,
            )
        elif component == "d5_active_vision":
            _require_positive_available_metric(
                row,
                "d5_active_vision_assist_adopted_count",
                component,
                failures,
            )
            _require_positive_available_metric(
                row,
                "d5_active_vision_assist_applied_count",
                f"{component}_runtime_ack",
                failures,
            )
    return failures


def _require_positive_available_metric(
    row: Mapping[str, Any],
    field: str,
    component: str,
    failures: list[str],
) -> None:
    if (
        row.get(f"{field}_availability") != "available"
        or not isinstance(row.get(field), int)
        or isinstance(row.get(field), bool)
        or int(row[field]) <= 0
    ):
        failures.append(f"cell_actual_assist_not_adopted:{component}")


def _audit_r0_pairing(
    learned_cells: Sequence[Mapping[str, Any]],
    baseline_cells: Sequence[Mapping[str, Any]],
    *,
    learned_scope: Mapping[str, Any],
    baseline_scopes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    blockers: list[str] = []
    by_key: dict[str, list[Mapping[str, Any]]] = {}
    for row in baseline_cells:
        by_key.setdefault(str(row["comparison_key"]), []).append(row)
    pairs: list[dict[str, Any]] = []
    available_count = 0
    non_degraded_count = 0
    for learned in learned_cells:
        key = str(learned["comparison_key"])
        candidates = by_key.get(key, [])
        pair: dict[str, Any] = {
            "comparison_key": key,
            "variant": learned["variant"],
            "learned_cell_id": learned["cell_id"],
            "r0_cell_id": None,
            "availability": "unavailable",
            "unavailable_reason": None,
            "non_degraded": None,
            "failure_reasons": [],
            "metric_comparisons": {},
        }
        if len(candidates) != 1:
            reason = (
                "r0_comparison_missing"
                if not candidates
                else "r0_comparison_duplicated"
            )
            pair["unavailable_reason"] = reason
            pair["failure_reasons"] = [reason]
            blockers.append(f"{reason}:{key}:{learned['variant']}")
            pairs.append(pair)
            continue
        baseline = candidates[0]
        pair["r0_cell_id"] = baseline["cell_id"]
        lineage_failures = []
        if learned["evidence_status"] != "accepted":
            lineage_failures.append("learned_cell_evidence_not_accepted")
        if baseline["evidence_status"] != "accepted":
            lineage_failures.append("r0_cell_evidence_not_accepted")
        if (
            learned.get("parent_plan_sha256")
            != baseline.get("parent_plan_sha256")
        ):
            lineage_failures.append("r0_parent_plan_mismatch")
        if learned.get("source_git_commit") != baseline.get(
            "source_git_commit"
        ):
            lineage_failures.append("r0_source_commit_mismatch")
        if learned.get("paired_exogenous_config_sha256") != baseline.get(
            "paired_exogenous_config_sha256"
        ):
            lineage_failures.append("r0_exogenous_config_mismatch")
        if learned.get("sensor_random_schedule_version") != baseline.get(
            "sensor_random_schedule_version"
        ):
            lineage_failures.append("r0_sensor_schedule_version_mismatch")
        if lineage_failures:
            pair["unavailable_reason"] = "r0_pair_lineage_invalid"
            pair["failure_reasons"] = lineage_failures
            blockers.extend(
                f"{reason}:{key}:{learned['variant']}"
                for reason in lineage_failures
            )
            pairs.append(pair)
            continue

        required_available = True
        required_non_degraded = True
        for metric, policy in _PAIR_METRIC_POLICY.items():
            learned_metric = learned["metric_evidence"][metric]
            baseline_metric = baseline["metric_evidence"][metric]
            comparison = _compare_metric_evidence(
                learned_metric,
                baseline_metric,
                direction=policy["direction"],
                required=bool(policy["required"]),
            )
            pair["metric_comparisons"][metric] = {
                **comparison,
                "direction": policy["direction"],
                "required": policy["required"],
                "source": policy["source"],
            }
            if policy["required"]:
                required_available &= comparison["availability"] == "available"
                required_non_degraded &= comparison["non_degraded"] is True
        pair["availability"] = (
            "available" if required_available else "unavailable"
        )
        if not required_available:
            pair["unavailable_reason"] = "required_physical_pair_metric_unavailable"
            pair["failure_reasons"].append(
                "required_physical_pair_metric_unavailable"
            )
            blockers.append(
                "required_physical_pair_metric_unavailable:"
                f"{key}:{learned['variant']}"
            )
        else:
            available_count += 1
            pair["non_degraded"] = required_non_degraded
            if required_non_degraded:
                non_degraded_count += 1
            else:
                pair["failure_reasons"].append(
                    "required_physical_metric_degraded"
                )
                blockers.append(
                    f"required_physical_metric_degraded:{key}:{learned['variant']}"
                )
        pairs.append(pair)
    expected = len(learned_cells)
    if expected == 0:
        blockers.append("learned_scope_contains_no_learned_cell")
    if expected > 0 and not baseline_cells:
        blockers.append("r0_scope_evidence_missing")
    return {
        "availability": (
            "available"
            if expected > 0 and available_count == expected
            else "unavailable"
        ),
        "expected_pair_count": expected,
        "available_pair_count": available_count,
        "non_degraded_pair_count": non_degraded_count,
        "all_required_pairs_available": (
            expected > 0 and available_count == expected
        ),
        "all_required_pairs_non_degraded": (
            expected > 0 and non_degraded_count == expected
        ),
        "metric_policy": _PAIR_METRIC_POLICY,
        "pairs": pairs,
        "blockers": sorted(set(blockers)),
        "causal_attribution": {
            "availability": "unavailable",
            "reason": (
                "same-comparison-key paired non-degradation is descriptive "
                "evidence and does not by itself prove causal effect"
            ),
        },
        "scope_lineage": {
            "learned_parent_plan_sha256": learned_scope.get(
                "parent_plan_sha256"
            ),
            "r0_parent_plan_sha256": sorted(
                {
                    str(scope.get("parent_plan_sha256"))
                    for scope in baseline_scopes
                    if scope.get("parent_plan_sha256") is not None
                }
            ),
        },
    }


def _compare_metric_evidence(
    learned: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    direction: str,
    required: bool,
) -> dict[str, Any]:
    if baseline.get("availability") != "available":
        return {
            "availability": "unavailable",
            "unavailable_reason": "r0_metric_unavailable",
            "r0_value": None,
            "learned_value": None,
            "delta_learned_minus_r0": None,
            "non_degraded": None,
        }
    if learned.get("availability") != "available":
        return {
            "availability": "unavailable",
            "unavailable_reason": "learned_metric_unavailable",
            "r0_value": baseline.get("value"),
            "learned_value": None,
            "delta_learned_minus_r0": None,
            "non_degraded": None,
        }
    r0_value = baseline.get("value")
    learned_value = learned.get("value")
    if not _is_number(r0_value) or not _is_number(learned_value):
        return {
            "availability": "unavailable",
            "unavailable_reason": "paired_metric_not_numeric",
            "r0_value": None,
            "learned_value": None,
            "delta_learned_minus_r0": None,
            "non_degraded": None,
        }
    r0_number = float(r0_value)
    learned_number = float(learned_value)
    if direction == "higher_or_equal":
        non_degraded = learned_number >= r0_number
    elif direction == "lower_or_equal":
        non_degraded = learned_number <= r0_number
    else:
        raise ValueError(f"unsupported non-degradation direction: {direction}")
    return {
        "availability": "available",
        "unavailable_reason": None,
        "r0_value": r0_value,
        "learned_value": learned_value,
        "delta_learned_minus_r0": learned_number - r0_number,
        "non_degraded": non_degraded,
        "required": required,
    }


def _public_scope(scope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in scope.items()
        if not str(key).startswith("_")
    }


def _public_cell(row: Mapping[str, Any]) -> dict[str, Any]:
    return dict(row)


def _failed_cell(
    scope_label: str,
    expected: Mapping[str, Any],
    reason: str,
) -> dict[str, Any]:
    unavailable_metrics = {
        name: _unavailable(reason) for name in _PAIR_METRIC_POLICY
    }
    return {
        "scope_label": scope_label,
        "variant": expected.get("variant"),
        "scenario": expected.get("scenario"),
        "scale": expected.get("scale"),
        "seed": expected.get("seed"),
        "comparison_key": expected.get("comparison_key"),
        "cell_id": expected.get("cell_id"),
        "parent_plan_sha256": None,
        "source_git_commit": None,
        "paired_exogenous_config_sha256": None,
        "sensor_random_schedule_version": None,
        "evidence_status": "fail_closed",
        "assist_adoption_status": "unavailable_or_not_adopted",
        "online_truth_status": "unavailable_or_nonzero",
        "physical_result_status": "unavailable",
        "learning_evidence": _unavailable(reason),
        "physical_metrics": {
            name: _unavailable(reason)
            for name in (
                "intercepted_target_count",
                "offline_proximity_within_5m_count",
                "offline_proximity_unique_target_count",
            )
        },
        "metric_evidence": unavailable_metrics,
        "failure_reasons": [reason],
    }


def _metric_evidence(
    row: Mapping[str, Any],
    field: str,
) -> dict[str, Any]:
    if row.get(f"{field}_availability") != "available":
        return _unavailable(
            str(
                row.get(f"{field}_unavailable_reason")
                or "metric_unavailable_without_reason"
            )
        )
    value = row.get(field)
    if not _is_number(value):
        return _unavailable("metric_available_value_not_numeric")
    return _available(value)


def _available(value: Any) -> dict[str, Any]:
    return {
        "availability": "available",
        "unavailable_reason": None,
        "value": value,
    }


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "unavailable_reason": str(reason),
        "value": None,
    }


def _required_components(variants: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            component
            for variant in variants
            for component in _VARIANT_COMPONENTS[str(variant)]
        )
    )


def _tree_inventory(root: Path) -> list[dict[str, Any]]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise LearningScopeFormalAuditError(
            "artifact_tree_empty",
            f"artifact tree is empty: {root}",
        )
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in files
    ]


def _tree_digest(root: Path) -> str:
    return _digest_json(_tree_inventory(root))


def _validate_checksum_file(
    path: Path,
    *,
    required_names: set[str],
) -> None:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        _require(
            len(parts) == 2
            and _HEX64_RE.fullmatch(parts[0]) is not None
            and bool(parts[1]),
            "scope_merge_checksum_file_invalid",
            "scope merge checksum file contains an invalid line",
        )
        entries[parts[1]] = parts[0]
    _require(
        required_names.issubset(entries),
        "scope_merge_checksum_inventory_incomplete",
        "scope merge checksums omit required artifacts",
    )
    for name in required_names:
        artifact = path.parent / name
        _require(
            artifact.is_file() and _sha256_file(artifact) == entries[name],
            f"scope_merge_checksum_mismatch:{name}",
            f"scope merge artifact checksum mismatch: {name}",
        )


def _read_json_object(path: Path, name: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LearningScopeFormalAuditError(
            f"{name}_not_object",
            f"{name} must be a JSON object",
        )
    return value


def _read_jsonl_objects(path: Path, name: str) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    _require(
        not text or text.endswith("\n"),
        f"{name}_truncated",
        f"{name} does not end on a complete line",
    )
    output: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        _require(
            bool(line.strip()),
            f"{name}_blank_line",
            f"{name} contains a blank line: {number}",
        )
        value = json.loads(line)
        _require(
            isinstance(value, dict),
            f"{name}_record_not_object",
            f"{name} record is not an object: {number}",
        )
        output.append(value)
    return output


def _resolve_within(root: Path, raw: Any, code: str) -> Path:
    _require(
        isinstance(raw, str) and bool(raw.strip()),
        code,
        "relative evidence path is missing",
    )
    relative = Path(raw)
    _require(
        not relative.is_absolute(),
        code,
        "evidence path must be relative to execution root",
    )
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise LearningScopeFormalAuditError(
            code,
            "evidence path escapes execution root",
        ) from exc
    return resolved


def _logical_relative_path(raw: Any, code: str) -> str:
    _require(
        isinstance(raw, str) and bool(raw) and "\\" not in raw,
        code,
        "logical episode path is missing or uses an unsafe separator",
    )
    path = PurePosixPath(raw)
    _require(
        not path.is_absolute()
        and path.as_posix() == raw
        and all(part not in {"", ".", ".."} for part in path.parts),
        code,
        "logical episode path is unsafe",
    )
    return raw


def _path_contains_symlink(path: Path) -> bool:
    candidate = Path(path).absolute()
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LearningScopeFormalAuditError(code, f"{code} must be an object")
    return value


def _required_sha256(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
        raise LearningScopeFormalAuditError(code, f"{code} is not SHA-256")
    return value


def _positive_int(value: Any) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
    ):
        raise LearningScopeFormalAuditError(
            "positive_integer_required",
            "value must be a positive integer",
        )
    return int(value)


def _nonnegative_int(value: Any) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise LearningScopeFormalAuditError(
            "nonnegative_integer_required",
            "value must be a non-negative integer",
        )
    return int(value)


def _optional_nonnegative_int(value: Any) -> int | None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        return None
    return int(value)


def _strict_int_text(value: Any) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"-?[0-9]+", value):
        raise LearningScopeFormalAuditError(
            "integer_text_invalid",
            "CSV integer field is invalid",
        )
    return int(value)


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value
        and value not in (float("inf"), float("-inf"))
    )


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise LearningScopeFormalAuditError(code, message)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _digest_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "LEARNING_SCOPE_DIRECTORY_STORAGE_MODE",
    "LEARNING_SCOPE_FORMAL_AUDIT_DATE",
    "LEARNING_SCOPE_FORMAL_AUDIT_SCHEMA_VERSION",
    "LearningScopeFormalAuditError",
    "LearningScopeFormalAuditInputs",
    "ScopeEvidenceArtifacts",
    "audit_learning_scope_formal_evidence",
    "render_learning_scope_formal_audit_markdown",
    "write_learning_scope_formal_audit_report",
]
