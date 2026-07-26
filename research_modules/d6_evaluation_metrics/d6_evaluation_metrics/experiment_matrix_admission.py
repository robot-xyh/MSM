"""Fail-closed admission precheck for formal scalable-3D experiment matrices.

The evaluator is read-only with respect to producer evidence.  It consumes an
actual ``ExperimentMatrixPlan``-like object or an explicit cell inventory and
never reconstructs missing cells from directory names.  Pre-run mode checks
the frozen inventory, source state, and model bundles.  Post-run mode also
requires the matrix manifest, per-cell D6 evidence, aggregate confidence-
interval inputs, and delivery artifacts.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping, Sequence


EXPERIMENT_MATRIX_ADMISSION_SCHEMA_VERSION = (
    "d6.experiment-matrix-admission-precheck.v1"
)
EXPERIMENT_MATRIX_INVENTORY_SCHEMA_VERSION = (
    "d6.experiment-matrix-expected-inventory.v1"
)
EXPERIMENT_MATRIX_VARIANTS = ("R0", "G1", "A1", "A2", "A3", "C1", "F1")
EXPERIMENT_MATRIX_BASE_VARIANTS = ("R0", "G1", "A1", "A2", "A3", "C1")
EXPERIMENT_MATRIX_SCENARIOS = (
    "nominal",
    "dense_crossing",
    "formation_split",
    "evasive_multilevel",
    "delayed_noisy",
    "communication_degraded",
    "center_failure",
    "secondary_failure",
    "high_threat_m_to_n",
)
EXPERIMENT_MATRIX_SCALES = (5, 20, 50, 100, 200)
MINIMUM_FORMAL_UNSEEN_SEED_COUNT = 20
EXPERIMENT_MATRIX_ADMISSION_DATE = "2026-07-25"

_MODEL_COMPONENTS = ("d3", "d4", "d5_graph", "d5_active_vision")
_VARIANT_MODEL_COMPONENTS = {
    "R0": (),
    "G1": ("d5_graph",),
    "A1": ("d3",),
    "A2": ("d4",),
    "A3": ("d5_active_vision",),
    "C1": _MODEL_COMPONENTS,
    "F1": _MODEL_COMPONENTS,
}
_REQUIRED_PER_CELL_METRICS = (
    "finite_state",
    "online_truth_use_count",
    "d2_id_switch_count",
    "offline_proximity_within_5m_count",
    "offline_proximity_unique_target_count",
)
_REQUIRED_CI_METRICS = (
    "d2_id_switch_count",
    "offline_proximity_within_5m_count",
    "offline_proximity_unique_target_count",
)
_HEX64 = frozenset("0123456789abcdef")


@dataclass(frozen=True, order=True)
class MatrixCellKey:
    """One immutable matrix identity supplied by main."""

    variant: str
    scenario: str
    scale: int
    seed: int

    @property
    def key(self) -> str:
        return f"{self.variant}|{self.scenario}|{self.scale}|{self.seed}"


def inventory_from_plan(plan: Any) -> dict[str, Any]:
    """Convert an actual ExperimentMatrixPlan-like object into an inventory.

    The function intentionally calls ``plan.cells()``.  The expected count and
    F1 scope therefore follow the producer contract instead of a D6 Cartesian
    product constant.
    """

    cells_method = getattr(plan, "cells", None)
    if not callable(cells_method):
        raise TypeError("plan must provide a callable cells() method")
    cells = [_coerce_cell(item) for item in cells_method()]
    training = getattr(plan, "training_seeds", None)
    return {
        "schema_version": EXPERIMENT_MATRIX_INVENTORY_SCHEMA_VERSION,
        "source_kind": "experiment_matrix_plan",
        "formal": bool(getattr(plan, "formal", False)),
        "allow_rule_fallback": bool(
            getattr(plan, "allow_rule_fallback", False)
        ),
        "variants": [
            str(value).strip().upper()
            for value in getattr(plan, "variants", ())
        ],
        "scenarios": [
            str(value).strip().lower()
            for value in getattr(plan, "scenarios", ())
        ],
        "scales": [int(value) for value in getattr(plan, "scales", ())],
        "seeds": [int(value) for value in getattr(plan, "seeds", ())],
        "training_seeds": (
            None
            if training is None
            else sorted({int(value) for value in training})
        ),
        "cells": [_cell_dict(cell) for cell in cells],
    }


def load_expected_inventory(source: Any) -> dict[str, Any]:
    """Load a plan object, JSON inventory, or CSV cell inventory.

    A post-run matrix summary without an explicit cell list is not enough to
    recover absent cells and is rejected by the caller.
    """

    if callable(getattr(source, "cells", None)):
        return inventory_from_plan(source)
    path = Path(source)
    if path.suffix.lower() == ".csv":
        rows = _read_csv(path)
        metadata_path = path.with_suffix(".metadata.json")
        metadata: dict[str, Any] = {}
        if metadata_path.is_file():
            metadata = _read_json_object(metadata_path)
        return {
            "schema_version": EXPERIMENT_MATRIX_INVENTORY_SCHEMA_VERSION,
            "source_kind": "explicit_cell_csv",
            "formal": metadata.get("formal"),
            "allow_rule_fallback": metadata.get("allow_rule_fallback"),
            "variants": metadata.get("variants"),
            "scenarios": metadata.get("scenarios"),
            "scales": metadata.get("scales"),
            "seeds": metadata.get("seeds"),
            "training_seeds": metadata.get("training_seeds"),
            "cells": rows,
            "source_path": str(path.resolve()),
            "metadata_path": (
                str(metadata_path.resolve()) if metadata_path.is_file() else None
            ),
        }
    payload = _read_json(path)
    if isinstance(payload, list):
        return {
            "schema_version": EXPERIMENT_MATRIX_INVENTORY_SCHEMA_VERSION,
            "source_kind": "explicit_cell_json",
            "formal": None,
            "allow_rule_fallback": None,
            "variants": None,
            "scenarios": None,
            "scales": None,
            "seeds": None,
            "training_seeds": None,
            "cells": payload,
            "source_path": str(path.resolve()),
        }
    if not isinstance(payload, Mapping):
        raise ValueError("expected inventory JSON must be an object or list")
    raw_cells = payload.get("cells", payload.get("expected_cells"))
    cells_path = payload.get("cells_path")
    if raw_cells is None and isinstance(cells_path, str) and cells_path.strip():
        resolved = (path.parent / cells_path).resolve()
        if resolved.suffix.lower() == ".csv":
            raw_cells = _read_csv(resolved)
        else:
            nested = _read_json(resolved)
            raw_cells = (
                nested.get("cells", nested.get("expected_cells"))
                if isinstance(nested, Mapping)
                else nested
            )
    if not isinstance(raw_cells, list):
        raise ValueError(
            "expected inventory must contain explicit cells/expected_cells; "
            "matrix dimensions alone cannot identify absent F1 cells"
        )
    result = dict(payload)
    result["cells"] = raw_cells
    result.setdefault("source_kind", "explicit_cell_json")
    result["source_path"] = str(path.resolve())
    return result


def audit_experiment_matrix_admission(
    expected_source: Any | None,
    *,
    mode: str,
    repository_root: str | Path | None = None,
    artifact_root: str | Path | None = None,
    model_bundles: Mapping[str, str | Path | None] | None = None,
    minimum_unseen_seed_count: int = MINIMUM_FORMAL_UNSEEN_SEED_COUNT,
) -> dict[str, Any]:
    """Evaluate formal matrix readiness without running an episode."""

    normalized_mode = str(mode).strip().lower().replace("-", "_")
    if normalized_mode not in {"pre_run", "post_run"}:
        raise ValueError("mode must be pre_run or post_run")
    minimum_seed_count = int(minimum_unseen_seed_count)
    if minimum_seed_count <= 0:
        raise ValueError("minimum_unseen_seed_count must be positive")

    blockers: list[str] = []
    inventory_error: str | None = None
    try:
        inventory = (
            load_expected_inventory(expected_source)
            if expected_source is not None
            else None
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        inventory = None
        inventory_error = f"expected_cell_inventory_invalid:{exc}"
        blockers.append("expected_cell_inventory_invalid")
    if inventory is None:
        inventory = {
            "schema_version": EXPERIMENT_MATRIX_INVENTORY_SCHEMA_VERSION,
            "source_kind": "missing",
            "formal": None,
            "allow_rule_fallback": None,
            "variants": None,
            "scenarios": None,
            "scales": None,
            "seeds": None,
            "training_seeds": None,
            "cells": [],
        }
        if inventory_error is None:
            blockers.append("expected_cell_inventory_missing")

    inventory_audit, expected_cells, inventory_blockers = _audit_inventory(
        inventory,
        minimum_seed_count=minimum_seed_count,
    )
    blockers.extend(inventory_blockers)
    source_audit, source_blockers = _audit_source(
        repository_root,
        mode=normalized_mode,
        artifact_root=artifact_root,
    )
    blockers.extend(source_blockers)
    bundle_audits, bundle_blockers = _audit_model_bundles(
        model_bundles or {},
        required_variants=inventory_audit["variants"],
    )
    blockers.extend(bundle_blockers)

    artifact_audit: dict[str, Any]
    actual_matrix_rows: list[dict[str, str]]
    offline_rows: list[dict[str, str]]
    aggregate: Mapping[str, Any] | None
    if normalized_mode == "post_run":
        (
            artifact_audit,
            actual_matrix_rows,
            offline_rows,
            aggregate,
            artifact_blockers,
        ) = _audit_post_run_artifacts(
            artifact_root,
            expected_cell_count=len(expected_cells),
            bundle_audits=bundle_audits,
        )
        blockers.extend(artifact_blockers)
    else:
        artifact_audit = {
            "mode": "pre_run",
            "status": "not_applicable_before_execution",
            "artifact_root": (
                str(Path(artifact_root).resolve())
                if artifact_root is not None
                else None
            ),
            "matrix_manifest": {
                "available": False,
                "reason": "not_required_in_pre_run_mode",
            },
            "report_bundle": {
                "available": False,
                "reason": "not_generated_before_execution",
            },
            "animation": {
                "available": False,
                "reason": "not_generated_before_execution",
            },
            "model_inventory": {
                "available": bool(bundle_audits),
                "reason": (
                    None if bundle_audits else "model_bundle_inputs_missing"
                ),
            },
        }
        actual_matrix_rows = []
        offline_rows = []
        aggregate = None

    cell_rows = _audit_cells(
        expected_cells,
        mode=normalized_mode,
        inventory_audit=inventory_audit,
        source_audit=source_audit,
        bundle_audits=bundle_audits,
        actual_matrix_rows=actual_matrix_rows,
        offline_rows=offline_rows,
    )
    missing_by_reason: dict[str, list[MatrixCellKey]] = defaultdict(list)
    for row in cell_rows:
        for reason in row["failure_reasons"]:
            if reason in {
                "matrix_cell_missing",
                "offline_cell_evidence_missing",
            }:
                missing_by_reason[reason].append(
                    MatrixCellKey(
                        row["variant"],
                        row["scenario"],
                        int(row["scale"]),
                        int(row["seed"]),
                    )
                )
    compact_missing = _compact_missing_ranges(missing_by_reason)

    ci_audit, ci_blockers = _audit_confidence_interval_inputs(
        aggregate,
        expected_cells=expected_cells,
        mode=normalized_mode,
        minimum_seed_count=minimum_seed_count,
    )
    blockers.extend(ci_blockers)
    blockers.extend(
        reason
        for row in cell_rows
        for reason in row["failure_reasons"]
        if normalized_mode == "post_run"
    )
    blockers = sorted(set(blockers))
    admitted_count = sum(row["accepted"] for row in cell_rows)
    verdict = "pass" if not blockers and admitted_count == len(cell_rows) else "fail_closed"
    if not cell_rows:
        verdict = "fail_closed"
        if "expected_cell_inventory_missing" not in blockers:
            blockers.append("expected_cell_inventory_empty")
            blockers.sort()

    gates = _build_gates(
        inventory_audit=inventory_audit,
        source_audit=source_audit,
        bundle_audits=bundle_audits,
        artifact_audit=artifact_audit,
        ci_audit=ci_audit,
        mode=normalized_mode,
        cell_rows=cell_rows,
    )
    return {
        "schema_version": EXPERIMENT_MATRIX_ADMISSION_SCHEMA_VERSION,
        "evaluation_date": EXPERIMENT_MATRIX_ADMISSION_DATE,
        "mode": normalized_mode,
        "verdict": verdict,
        "fail_closed": verdict != "pass",
        "admission_allowed": verdict == "pass",
        "inventory_error": inventory_error,
        "inventory": inventory_audit,
        "source": source_audit,
        "model_bundles": bundle_audits,
        "artifacts": artifact_audit,
        "confidence_interval_inputs": ci_audit,
        "cell_summary": {
            "expected_cell_count": len(cell_rows),
            "accepted_cell_count": admitted_count,
            "failed_cell_count": len(cell_rows) - admitted_count,
            "actual_matrix_row_count": len(actual_matrix_rows),
            "offline_evidence_row_count": len(offline_rows),
        },
        "gates": gates,
        "blockers": blockers,
        "compact_missing_cell_ranges": compact_missing,
        "cells": cell_rows,
    }


def write_experiment_matrix_admission_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Write full JSON, per-cell CSV, Chinese Markdown, and SHA256SUMS."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "experiment_matrix_admission_precheck.json"
    csv_path = output / "experiment_matrix_admission_cells.csv"
    markdown_path = output / "EXPERIMENT_MATRIX_ADMISSION_PRECHECK_CN.md"
    checksum_path = output / "SHA256SUMS"

    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = list(result.get("cells", ()))
    fieldnames = (
        "variant",
        "scenario",
        "scale",
        "seed",
        "expected",
        "matrix_row_count",
        "offline_row_count",
        "unique",
        "model_bundle_ready",
        "declared_adoption_valid",
        "silent_fallback_absent",
        "online_truth_zero",
        "finite_state_valid",
        "d2_id_switch_available",
        "physical_5m_available",
        "per_seed_input_complete",
        "accepted",
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
        render_experiment_matrix_admission_markdown(result),
        encoding="utf-8",
    )
    artifact_paths = (json_path, csv_path, markdown_path)
    checksum_path.write_text(
        "".join(
            f"{_sha256_file(path)}  {path.name}\n"
            for path in sorted(artifact_paths, key=lambda item: item.name)
        ),
        encoding="utf-8",
    )
    return {
        "json": json_path,
        "csv": csv_path,
        "markdown": markdown_path,
        "checksums": checksum_path,
    }


def render_experiment_matrix_admission_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the compact Chinese admission report."""

    inventory = result.get("inventory", {})
    summary = result.get("cell_summary", {})
    source = result.get("source", {})
    lines = [
        "# 正式实验矩阵准入预检",
        "",
        f"评估日期：{result.get('evaluation_date', EXPERIMENT_MATRIX_ADMISSION_DATE)}",
        "",
        "## 结论",
        "",
        (
            f"预检模式为 `{result.get('mode')}`，结论为 "
            f"**{result.get('verdict')}**。预期 cell 数为 "
            f"{summary.get('expected_cell_count', 0)}，通过 "
            f"{summary.get('accepted_cell_count', 0)}，失败 "
            f"{summary.get('failed_cell_count', 0)}。"
        ),
        (
            "该结论只表示静态清单和制品是否满足正式矩阵入口。"
            "预检不运行 episode，不生成缺失指标，也不参与控制。"
        ),
    ]
    if inventory.get("source_kind") == "missing":
        lines.extend(
            [
                (
                    "本次没有提供 expected inventory。上述预期 cell 数为 0 "
                    "仅表示缺少输入，不表示正式实验矩阵规模为 0，也不是 "
                    "5700-cell 正式清单的评估结果。"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## 清单",
            "",
            f"- 来源：`{inventory.get('source_kind', 'unavailable')}`",
            f"- 唯一 cell：{inventory.get('unique_cell_count', 0)}",
            f"- 重复 cell：{inventory.get('duplicate_cell_count', 0)}",
            (
                "- 变体："
                f"`{json.dumps(inventory.get('variants', []), ensure_ascii=False)}`"
            ),
            (
                "- 场景："
                f"`{json.dumps(inventory.get('scenarios', []), ensure_ascii=False)}`"
            ),
            (
                "- 规模："
                f"`{json.dumps(inventory.get('scales', []), ensure_ascii=False)}`"
            ),
            f"- 评估种子数：{inventory.get('seed_count', 0)}",
            (
                "- 训练种子交集："
                f"`{json.dumps(inventory.get('training_seed_overlap', []))}`"
            ),
            "",
            "## 来源状态",
            "",
            f"- Git commit：`{source.get('git_commit')}`",
            f"- 正式 clean-source：{source.get('formal_clean_source')}",
            f"- 来源说明：`{source.get('formal_clean_source_reason')}`",
            "",
            "## 准入门",
            "",
            "| 准入门 | 结果 | 原因 |",
            "| --- | --- | --- |",
        ]
    )
    for gate in result.get("gates", ()):
        lines.append(
            f"| {gate.get('name')} | "
            f"{'通过' if gate.get('passed') else '拒绝'} | "
            f"`{gate.get('reason')}` |"
        )
    lines.extend(
        [
            "",
            "## 模型制品",
            "",
            "| 组件 | manifest | weights | SHA | assist 声明 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for component, audit in sorted(result.get("model_bundles", {}).items()):
        lines.append(
            f"| {component} | {audit.get('manifest_available')} | "
            f"{audit.get('weights_available')} | {audit.get('sha_valid')} | "
            f"{audit.get('assist_declared')} |"
        )
    missing_ranges = result.get("compact_missing_cell_ranges", ())
    lines.extend(["", "## 缺失 Cell", ""])
    if not missing_ranges:
        lines.append("没有缺失 cell 范围。")
    else:
        for item in missing_ranges:
            lines.append(
                "- `{reason}`：variants={variants}；scenarios={scenarios}；"
                "scales={scales}；seeds={seeds}；cell_count={count}".format(
                    reason=item.get("reason"),
                    variants=",".join(item.get("variants", ())),
                    scenarios=",".join(item.get("scenarios", ())),
                    scales=",".join(
                        str(value) for value in item.get("scales", ())
                    ),
                    seeds=",".join(item.get("seed_ranges", ())),
                    count=item.get("cell_count", 0),
                )
            )
    lines.extend(["", "## 阻断原因", ""])
    blockers = list(result.get("blockers", ()))
    if blockers:
        lines.extend(f"- `{reason}`" for reason in blockers)
    else:
        lines.append("无。")
    lines.extend(
        [
            "",
            "## 制品",
            "",
            "- `experiment_matrix_admission_precheck.json`：完整机器可读结论。",
            "- `experiment_matrix_admission_cells.csv`：逐 cell 检查结果。",
            "- `EXPERIMENT_MATRIX_ADMISSION_PRECHECK_CN.md`：中文摘要。",
            "- `SHA256SUMS`：上述三项制品的校验值。",
            "",
        ]
    )
    return "\n".join(lines)


def _audit_inventory(
    inventory: Mapping[str, Any],
    *,
    minimum_seed_count: int,
) -> tuple[dict[str, Any], tuple[MatrixCellKey, ...], list[str]]:
    blockers: list[str] = []
    raw_cells = inventory.get("cells")
    cells: list[MatrixCellKey] = []
    invalid_cell_count = 0
    if not isinstance(raw_cells, list):
        raw_cells = []
        blockers.append("expected_cell_inventory_cells_missing")
    for raw in raw_cells:
        try:
            cells.append(_coerce_cell(raw))
        except (TypeError, ValueError):
            invalid_cell_count += 1
    if invalid_cell_count:
        blockers.append("expected_cell_inventory_contains_invalid_cells")
    counts = Counter(cells)
    unique_cells = tuple(sorted(counts))
    duplicates = sorted(cell.key for cell, count in counts.items() if count > 1)
    if duplicates:
        blockers.append("expected_cell_inventory_contains_duplicates")
    if not unique_cells:
        blockers.append("expected_cell_inventory_empty")

    variants = sorted(
        {cell.variant for cell in unique_cells},
        key=lambda value: (
            EXPERIMENT_MATRIX_VARIANTS.index(value)
            if value in EXPERIMENT_MATRIX_VARIANTS
            else len(EXPERIMENT_MATRIX_VARIANTS),
            value,
        ),
    )
    scenarios = sorted(
        {cell.scenario for cell in unique_cells},
        key=lambda value: (
            EXPERIMENT_MATRIX_SCENARIOS.index(value)
            if value in EXPERIMENT_MATRIX_SCENARIOS
            else len(EXPERIMENT_MATRIX_SCENARIOS),
            value,
        ),
    )
    scales = sorted({cell.scale for cell in unique_cells})
    seeds = sorted({cell.seed for cell in unique_cells})
    if set(variants) != set(EXPERIMENT_MATRIX_VARIANTS):
        blockers.append("formal_variant_coverage_incomplete")
    if set(scenarios) != set(EXPERIMENT_MATRIX_SCENARIOS):
        blockers.append("formal_scenario_coverage_incomplete")
    if set(scales) != set(EXPERIMENT_MATRIX_SCALES):
        blockers.append("formal_scale_coverage_incomplete")
    if len(seeds) < minimum_seed_count:
        blockers.append("formal_unseen_seed_count_below_minimum")
    if inventory.get("formal") is not True:
        blockers.append("formal_plan_flag_not_true")
    if inventory.get("allow_rule_fallback") is not False:
        blockers.append("formal_plan_allows_rule_fallback_or_is_undeclared")

    training_raw = inventory.get("training_seeds")
    if not isinstance(training_raw, list):
        training_seeds: list[int] = []
        overlap: list[int] = []
        blockers.append("training_seed_registry_missing")
    else:
        try:
            training_seeds = sorted({_strict_int(value) for value in training_raw})
        except ValueError:
            training_seeds = []
            blockers.append("training_seed_registry_invalid")
        overlap = sorted(set(training_seeds) & set(seeds))
        if overlap:
            blockers.append("training_evaluation_seed_overlap")

    cell_set = set(unique_cells)
    combination_holes: list[MatrixCellKey] = []
    for variant in EXPERIMENT_MATRIX_BASE_VARIANTS:
        for scenario in EXPERIMENT_MATRIX_SCENARIOS:
            for scale in scales:
                for seed in seeds:
                    key = MatrixCellKey(variant, scenario, scale, seed)
                    if key not in cell_set:
                        combination_holes.append(key)
    f1_scenarios = sorted(
        {cell.scenario for cell in unique_cells if cell.variant == "F1"}
    )
    if not f1_scenarios:
        blockers.append("f1_scenario_scope_empty")
    for scenario in f1_scenarios:
        for scale in scales:
            for seed in seeds:
                key = MatrixCellKey("F1", scenario, scale, seed)
                if key not in cell_set:
                    combination_holes.append(key)
    if combination_holes:
        blockers.append("expected_cell_inventory_cartesian_holes")

    declared_count = inventory.get("cell_count")
    if declared_count is not None:
        try:
            if _strict_int(declared_count) != len(cells):
                blockers.append("expected_cell_inventory_declared_count_mismatch")
        except ValueError:
            blockers.append("expected_cell_inventory_declared_count_invalid")
    audit = {
        "schema_version": inventory.get("schema_version"),
        "source_kind": inventory.get("source_kind", "unknown"),
        "source_path": inventory.get("source_path"),
        "formal": inventory.get("formal"),
        "allow_rule_fallback": inventory.get("allow_rule_fallback"),
        "raw_cell_count": len(cells) + invalid_cell_count,
        "valid_cell_count": len(cells),
        "unique_cell_count": len(unique_cells),
        "duplicate_cell_count": sum(count - 1 for count in counts.values()),
        "duplicate_cell_keys": duplicates,
        "invalid_cell_count": invalid_cell_count,
        "variants": variants,
        "scenarios": scenarios,
        "scales": scales,
        "seeds": seeds,
        "seed_count": len(seeds),
        "minimum_unseen_seed_count": minimum_seed_count,
        "training_seed_count": len(training_seeds),
        "training_seed_overlap": overlap,
        "f1_scenarios_from_inventory": f1_scenarios,
        "cartesian_hole_count": len(combination_holes),
        "contract_follows_explicit_cell_inventory": True,
        "blockers": sorted(set(blockers)),
    }
    return audit, unique_cells, blockers


def _audit_source(
    repository_root: str | Path | None,
    *,
    mode: str,
    artifact_root: str | Path | None,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    current_commit: str | None = None
    current_dirty: bool | None = None
    current_error: str | None = None
    if repository_root is None:
        current_error = "repository_root_missing"
    else:
        root = Path(repository_root).resolve()
        try:
            current_commit = subprocess.run(
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
            current_dirty = bool(status.strip())
        except (OSError, subprocess.CalledProcessError) as exc:
            current_error = f"repository_state_unavailable:{exc}"

    manifest: Mapping[str, Any] | None = None
    manifest_path: Path | None = None
    if mode == "post_run" and artifact_root is not None:
        candidate = Path(artifact_root).resolve() / "experiment_matrix_manifest.json"
        if candidate.is_file():
            manifest_path = candidate
            try:
                manifest = _read_json_object(candidate)
            except (OSError, ValueError, json.JSONDecodeError):
                manifest = None
    if mode == "pre_run":
        clean = current_dirty is False and _is_git_commit(current_commit)
        reason = (
            None
            if clean
            else current_error
            or (
                "repository_dirty=true"
                if current_dirty is True
                else "repository_state_unavailable"
            )
        )
    elif manifest is None:
        clean = False
        reason = "matrix_manifest_missing_or_invalid"
    else:
        clean = (
            manifest.get("formal") is True
            and manifest.get("repository_dirty") is False
            and _is_git_commit(manifest.get("git_commit"))
        )
        reason = None if clean else "matrix_manifest_not_clean_formal_source"
    if not clean:
        blockers.append("formal_clean_source_not_proven")
    return {
        "repository_root": (
            str(Path(repository_root).resolve())
            if repository_root is not None
            else None
        ),
        "git_commit": current_commit,
        "repository_dirty": current_dirty,
        "repository_state_error": current_error,
        "matrix_manifest_path": (
            str(manifest_path) if manifest_path is not None else None
        ),
        "matrix_manifest_git_commit": (
            manifest.get("git_commit") if manifest is not None else None
        ),
        "matrix_manifest_repository_dirty": (
            manifest.get("repository_dirty") if manifest is not None else None
        ),
        "formal_clean_source": clean,
        "formal_clean_source_reason": reason,
    }, blockers


def _audit_model_bundles(
    model_bundles: Mapping[str, str | Path | None],
    *,
    required_variants: Sequence[str],
) -> tuple[dict[str, Any], list[str]]:
    required_components = {
        component
        for variant in required_variants
        for component in _VARIANT_MODEL_COMPONENTS.get(variant, ())
    }
    audits: dict[str, Any] = {}
    blockers: list[str] = []
    for component in sorted(required_components):
        raw_path = model_bundles.get(component)
        audit = _audit_model_bundle(component, raw_path)
        audits[component] = audit
        if not audit["ready"]:
            blockers.extend(
                f"model_bundle_{component}:{reason}"
                for reason in audit["failure_reasons"]
            )
    for component in model_bundles:
        if component not in _MODEL_COMPONENTS:
            blockers.append(f"unknown_model_bundle_component:{component}")
    return audits, blockers


def _audit_model_bundle(
    component: str,
    raw_path: str | Path | None,
) -> dict[str, Any]:
    failures: list[str] = []
    if raw_path is None:
        return {
            "component": component,
            "path": None,
            "manifest_available": False,
            "weights_available": False,
            "sha_valid": False,
            "assist_declared": False,
            "ready": False,
            "failure_reasons": ["bundle_path_missing"],
        }
    root = Path(raw_path).resolve()
    manifest_path = root / "manifest.json"
    if not root.is_dir():
        failures.append("bundle_directory_missing")
    if not manifest_path.is_file():
        failures.append("manifest_missing")
        manifest: Mapping[str, Any] = {}
    else:
        try:
            manifest = _read_json_object(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError):
            manifest = {}
            failures.append("manifest_invalid")
    weight_name, claimed_weight_sha = _model_weight_reference(component, manifest)
    weight_path = root / weight_name if weight_name else None
    weights_available = bool(weight_path is not None and weight_path.is_file())
    observed_weight_sha = (
        _sha256_file(weight_path) if weights_available and weight_path else None
    )
    if not weight_name:
        failures.append("weight_reference_missing")
    elif not weights_available:
        failures.append("weights_missing")
    if claimed_weight_sha is None:
        failures.append("weight_sha_missing_or_invalid")
    elif observed_weight_sha != claimed_weight_sha:
        failures.append("weight_sha_mismatch")

    checksum_audit = _audit_bundle_checksum_file(root)
    if checksum_audit["available"] and not checksum_audit["valid"]:
        failures.append("bundle_checksum_file_invalid")
    manifest_sha = _sha256_file(manifest_path) if manifest_path.is_file() else None
    bundle_sha = _bundle_sha256(
        {
            "manifest.json": manifest_sha,
            weight_name: observed_weight_sha,
        }
    )
    assist_declared, assist_reason = _model_assist_declaration(component, manifest)
    if not assist_declared:
        failures.append(assist_reason)
    sha_valid = bool(
        manifest_sha
        and observed_weight_sha
        and observed_weight_sha == claimed_weight_sha
        and (not checksum_audit["available"] or checksum_audit["valid"])
    )
    return {
        "component": component,
        "path": str(root),
        "manifest_path": str(manifest_path),
        "manifest_available": manifest_path.is_file(),
        "manifest_sha256": manifest_sha,
        "weights_path": str(weight_path) if weight_path is not None else None,
        "weights_available": weights_available,
        "weights_sha256_claimed": claimed_weight_sha,
        "weights_sha256_observed": observed_weight_sha,
        "bundle_sha256": bundle_sha,
        "checksum_file": checksum_audit,
        "sha_valid": sha_valid,
        "assist_declared": assist_declared,
        "assist_declaration_reason": assist_reason,
        "ready": not failures,
        "failure_reasons": sorted(set(failures)),
    }


def _audit_post_run_artifacts(
    artifact_root: str | Path | None,
    *,
    expected_cell_count: int,
    bundle_audits: Mapping[str, Mapping[str, Any]],
) -> tuple[
    dict[str, Any],
    list[dict[str, str]],
    list[dict[str, str]],
    Mapping[str, Any] | None,
    list[str],
]:
    blockers: list[str] = []
    if artifact_root is None:
        root = None
        blockers.append("matrix_artifact_root_missing")
    else:
        root = Path(artifact_root).resolve()
        if not root.is_dir():
            blockers.append("matrix_artifact_root_missing")
    manifest_path = root / "experiment_matrix_manifest.json" if root else None
    cells_path = root / "experiment_matrix_cells.csv" if root else None
    d6_root = root / "d6_evaluation" if root else None
    offline_path = (
        d6_root / "scalable_3d_offline_per_episode_seed.csv" if d6_root else None
    )
    aggregate_path = (
        d6_root / "scalable_3d_offline_aggregate.json" if d6_root else None
    )
    report_path = (
        d6_root / "SCALABLE_3D_OFFLINE_EVALUATION_CN.md" if d6_root else None
    )
    curve_path = (
        d6_root / "scalable_3d_stage_timing_curves.png" if d6_root else None
    )
    manifest: Mapping[str, Any] | None = None
    if manifest_path is None or not manifest_path.is_file():
        blockers.append("matrix_manifest_missing")
    else:
        try:
            manifest = _read_json_object(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError):
            blockers.append("matrix_manifest_invalid")
    actual_rows = _read_csv(cells_path) if cells_path and cells_path.is_file() else []
    if not actual_rows:
        blockers.append("matrix_cells_csv_missing_or_empty")
    elif len(actual_rows) != expected_cell_count:
        blockers.append("matrix_cells_csv_row_count_mismatch")
    offline_rows = (
        _read_csv(offline_path)
        if offline_path is not None and offline_path.is_file()
        else []
    )
    if not offline_rows:
        blockers.append("d6_per_seed_csv_missing_or_empty")
    elif len(offline_rows) != expected_cell_count:
        blockers.append("d6_per_seed_csv_row_count_mismatch")
    aggregate: Mapping[str, Any] | None = None
    if aggregate_path is not None and aggregate_path.is_file():
        try:
            aggregate = _read_json_object(aggregate_path)
        except (OSError, ValueError, json.JSONDecodeError):
            blockers.append("d6_aggregate_json_invalid")
    else:
        blockers.append("d6_aggregate_json_missing")
    report_available = bool(report_path and report_path.is_file())
    curve_available = bool(curve_path and curve_path.is_file())
    if not report_available or not curve_available:
        blockers.append("d6_report_bundle_incomplete")
    animations = _discover_valid_animations(root)
    if not animations:
        blockers.append("matrix_animation_missing")

    model_inventory_path = (
        root / "experiment_matrix_model_inventory.json" if root else None
    )
    model_inventory: Mapping[str, Any] | None = None
    if model_inventory_path and model_inventory_path.is_file():
        try:
            model_inventory = _read_json_object(model_inventory_path)
        except (OSError, ValueError, json.JSONDecodeError):
            blockers.append("matrix_model_inventory_invalid")
    elif isinstance(manifest, Mapping) and isinstance(
        manifest.get("model_bundles"), Mapping
    ):
        model_inventory = manifest["model_bundles"]
    else:
        blockers.append("matrix_model_inventory_missing")
    model_inventory_match = _model_inventory_matches(
        model_inventory,
        bundle_audits,
    )
    if model_inventory is not None and not model_inventory_match:
        blockers.append("matrix_model_inventory_sha_mismatch")

    if manifest is not None:
        if (
            manifest.get("schema_version")
            != "scalable3d-experiment-matrix-v1"
        ):
            blockers.append("matrix_manifest_schema_mismatch")
        if manifest.get("formal") is not True:
            blockers.append("matrix_manifest_formal_flag_not_true")
        if manifest.get("repository_dirty") is not False:
            blockers.append("matrix_manifest_repository_dirty")
        if manifest.get("cell_count") != expected_cell_count:
            blockers.append("matrix_manifest_expected_cell_count_mismatch")
        if manifest.get("completed_cell_count") != expected_cell_count:
            blockers.append("matrix_manifest_completed_cell_count_mismatch")

    artifact_audit = {
        "mode": "post_run",
        "status": "complete" if not blockers else "incomplete",
        "artifact_root": str(root) if root is not None else None,
        "matrix_manifest": _artifact_record(manifest_path),
        "matrix_cells_csv": _artifact_record(cells_path),
        "per_seed_csv": _artifact_record(offline_path),
        "aggregate_json": _artifact_record(aggregate_path),
        "report_markdown": _artifact_record(report_path),
        "report_curve": _artifact_record(curve_path),
        "report_bundle": {
            "available": report_available and curve_available,
            "reason": (
                None
                if report_available and curve_available
                else "required_d6_report_artifact_missing"
            ),
        },
        "animation": {
            "available": bool(animations),
            "paths": animations,
            "reason": None if animations else "gif_or_mp4_missing_or_invalid",
        },
        "model_inventory": {
            "available": model_inventory is not None,
            "path": (
                str(model_inventory_path)
                if model_inventory_path and model_inventory_path.is_file()
                else "experiment_matrix_manifest.json:model_bundles"
                if model_inventory is not None
                else None
            ),
            "sha_match": model_inventory_match,
            "reason": (
                None
                if model_inventory is not None and model_inventory_match
                else "model_inventory_missing_or_not_bound_to_prechecked_bundles"
            ),
        },
        "blockers": sorted(set(blockers)),
    }
    return artifact_audit, actual_rows, offline_rows, aggregate, blockers


def _audit_cells(
    expected_cells: Sequence[MatrixCellKey],
    *,
    mode: str,
    inventory_audit: Mapping[str, Any],
    source_audit: Mapping[str, Any],
    bundle_audits: Mapping[str, Mapping[str, Any]],
    actual_matrix_rows: Sequence[Mapping[str, str]],
    offline_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    matrix_by_key = _index_rows(actual_matrix_rows, offline=False)
    offline_by_key = _index_rows(offline_rows, offline=True)
    inventory_ready = not inventory_audit.get("blockers")
    source_ready = source_audit.get("formal_clean_source") is True
    rows: list[dict[str, Any]] = []
    for cell in expected_cells:
        failures: list[str] = []
        required_components = _VARIANT_MODEL_COMPONENTS.get(cell.variant, ())
        model_ready = all(
            bundle_audits.get(component, {}).get("ready") is True
            for component in required_components
        )
        if not model_ready:
            failures.append("required_model_bundle_not_ready")
        matrix_matches = matrix_by_key.get(cell, ())
        evidence_matches = offline_by_key.get(cell, ())
        if mode == "pre_run":
            matrix_count = 0
            evidence_count = 0
            unique = True
            adoption_valid = model_ready
            fallback_absent = model_ready
            online_truth_zero = None
            finite_valid = None
            id_switch_available = None
            physical_available = None
            per_seed_complete = True
            if not inventory_ready:
                failures.append("expected_inventory_contract_invalid")
            if not source_ready:
                failures.append("formal_clean_source_not_proven")
        else:
            matrix_count = len(matrix_matches)
            evidence_count = len(evidence_matches)
            if matrix_count == 0:
                failures.append("matrix_cell_missing")
            elif matrix_count > 1:
                failures.append("matrix_cell_duplicate")
            if evidence_count == 0:
                failures.append("offline_cell_evidence_missing")
            elif evidence_count > 1:
                failures.append("offline_cell_evidence_duplicate")
            unique = matrix_count == 1 and evidence_count == 1
            evidence = evidence_matches[0] if evidence_count == 1 else {}
            adoption_valid = _csv_bool(evidence.get("variant_execution_valid"))
            fallback_absent = adoption_valid and not _json_list_value(
                evidence.get("variant_execution_failure_reasons_json")
            )
            if not adoption_valid:
                failures.append("declared_variant_adoption_not_proven")
            if not fallback_absent:
                failures.append("silent_fallback_absence_not_proven")
            online_truth_zero = (
                evidence.get("online_truth_use_count_availability") == "available"
                and _csv_int(evidence.get("online_truth_use_count")) == 0
                and (
                    evidence.get("online_truth_field_violation_count_availability")
                    != "available"
                    or _csv_int(
                        evidence.get("online_truth_field_violation_count")
                    )
                    == 0
                )
            )
            if not online_truth_zero:
                failures.append("online_truth_zero_not_proven")
            finite_valid = (
                evidence.get("finite_state_availability") == "available"
                and _csv_bool(evidence.get("finite_state"))
            )
            if not finite_valid:
                failures.append("finite_state_not_proven")
            id_switch_available = (
                evidence.get("d2_id_switch_count_availability") == "available"
                and _csv_int(evidence.get("d2_id_switch_count")) is not None
            )
            if not id_switch_available:
                failures.append("d2_id_switch_metric_unavailable")
            physical_available = all(
                evidence.get(f"{name}_availability") == "available"
                and _csv_number(evidence.get(name)) is not None
                for name in (
                    "offline_proximity_within_5m_count",
                    "offline_proximity_unique_target_count",
                )
            )
            if not physical_available:
                failures.append("physical_5m_metric_unavailable")
            per_seed_complete = all(
                evidence.get(f"{name}_availability") == "available"
                for name in _REQUIRED_PER_CELL_METRICS
            )
            if not per_seed_complete:
                failures.append("per_seed_metric_input_incomplete")
            formal_cell_evidence = (
                evidence.get(
                    "experiment_matrix_formal_acceptance_eligible_availability"
                )
                == "available"
                and _csv_bool(
                    evidence.get("experiment_matrix_formal_acceptance_eligible")
                )
            )
            if not formal_cell_evidence:
                failures.append("cell_not_clean_formal_evidence")
        rows.append(
            {
                "variant": cell.variant,
                "scenario": cell.scenario,
                "scale": cell.scale,
                "seed": cell.seed,
                "expected": True,
                "matrix_row_count": matrix_count,
                "offline_row_count": evidence_count,
                "unique": unique,
                "model_bundle_ready": model_ready,
                "declared_adoption_valid": adoption_valid,
                "silent_fallback_absent": fallback_absent,
                "online_truth_zero": online_truth_zero,
                "finite_state_valid": finite_valid,
                "d2_id_switch_available": id_switch_available,
                "physical_5m_available": physical_available,
                "per_seed_input_complete": per_seed_complete,
                "accepted": not failures,
                "failure_reasons": sorted(set(failures)),
            }
        )
    return rows


def _audit_confidence_interval_inputs(
    aggregate: Mapping[str, Any] | None,
    *,
    expected_cells: Sequence[MatrixCellKey],
    mode: str,
    minimum_seed_count: int,
) -> tuple[dict[str, Any], list[str]]:
    if mode == "pre_run":
        return {
            "status": "not_applicable_before_execution",
            "available": False,
            "reason": "aggregate_not_generated_before_execution",
        }, []
    blockers: list[str] = []
    if not isinstance(aggregate, Mapping):
        return {
            "status": "unavailable",
            "available": False,
            "reason": "d6_aggregate_json_missing_or_invalid",
        }, ["confidence_interval_inputs_missing"]
    bootstrap = aggregate.get("bootstrap")
    matrix = aggregate.get("experiment_matrix")
    bootstrap_valid = (
        isinstance(bootstrap, Mapping)
        and _positive_int(bootstrap.get("resamples"))
        and _nonnegative_int(bootstrap.get("rng_seed"))
    )
    if not bootstrap_valid:
        blockers.append("bootstrap_contract_missing_or_invalid")
    if not isinstance(matrix, Mapping):
        blockers.append("experiment_matrix_aggregate_missing")
        matrix = {}
    completeness = matrix.get("completeness")
    expected_count = len(expected_cells)
    completeness_valid = (
        isinstance(completeness, Mapping)
        and completeness.get("expected_cell_count") == expected_count
        and completeness.get("present_expected_cell_count") == expected_count
        and completeness.get("execution_valid_cell_count") == expected_count
    )
    if not completeness_valid:
        blockers.append("aggregate_cell_completeness_invalid")
    groups = {
        item.get("algorithm_variant"): item
        for item in matrix.get("variant_groups", ())
        if isinstance(item, Mapping)
    }
    metric_failures: list[str] = []
    expected_seed_counts = {
        variant: len({cell.seed for cell in expected_cells if cell.variant == variant})
        for variant in EXPERIMENT_MATRIX_VARIANTS
    }
    for variant, expected_seed_count in expected_seed_counts.items():
        group = groups.get(variant)
        if not isinstance(group, Mapping):
            metric_failures.append(f"{variant}:variant_group_missing")
            continue
        observed_seed_count = _csv_int(group.get("seed_count"))
        if observed_seed_count is None or observed_seed_count < max(
            minimum_seed_count,
            expected_seed_count,
        ):
            metric_failures.append(f"{variant}:seed_input_incomplete")
        stats = group.get("clean_formal_metric_statistics")
        if not isinstance(stats, Mapping):
            metric_failures.append(f"{variant}:formal_statistics_missing")
            continue
        for metric in _REQUIRED_CI_METRICS:
            record = stats.get(metric)
            if not isinstance(record, Mapping):
                metric_failures.append(f"{variant}:{metric}:missing")
                continue
            seed_value_count = _csv_int(record.get("seed_value_count"))
            if (
                record.get("availability") != "available"
                or seed_value_count is None
                or seed_value_count < expected_seed_count
                or record.get("bootstrap_availability") != "available"
            ):
                metric_failures.append(f"{variant}:{metric}:ci_input_incomplete")
    if metric_failures:
        blockers.append("per_variant_confidence_interval_inputs_incomplete")
    return {
        "status": "complete" if not blockers else "incomplete",
        "available": not blockers,
        "bootstrap_contract_valid": bootstrap_valid,
        "aggregate_completeness_valid": completeness_valid,
        "metric_failures": metric_failures,
        "required_metrics": list(_REQUIRED_CI_METRICS),
        "blockers": blockers,
    }, blockers


def _build_gates(
    *,
    inventory_audit: Mapping[str, Any],
    source_audit: Mapping[str, Any],
    bundle_audits: Mapping[str, Mapping[str, Any]],
    artifact_audit: Mapping[str, Any],
    ci_audit: Mapping[str, Any],
    mode: str,
    cell_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    checks = [
        (
            "expected_inventory",
            not inventory_audit.get("blockers"),
            ",".join(inventory_audit.get("blockers", ())) or None,
        ),
        (
            "formal_clean_source",
            source_audit.get("formal_clean_source") is True,
            source_audit.get("formal_clean_source_reason"),
        ),
        (
            "model_bundle_integrity_and_assist_declaration",
            bool(bundle_audits)
            and all(item.get("ready") is True for item in bundle_audits.values()),
            ",".join(
                f"{name}:{'|'.join(item.get('failure_reasons', ())) }"
                for name, item in bundle_audits.items()
                if item.get("ready") is not True
            )
            or None,
        ),
    ]
    if mode == "post_run":
        checks.extend(
            [
                (
                    "post_run_artifacts",
                    artifact_audit.get("status") == "complete",
                    ",".join(artifact_audit.get("blockers", ())) or None,
                ),
                (
                    "per_cell_runtime_evidence",
                    bool(cell_rows)
                    and all(row.get("accepted") is True for row in cell_rows),
                    "one_or_more_cells_failed" if cell_rows else "no_cells",
                ),
                (
                    "confidence_interval_inputs",
                    ci_audit.get("available") is True,
                    ",".join(ci_audit.get("blockers", ()))
                    or ci_audit.get("reason"),
                ),
            ]
        )
    return [
        {"name": name, "passed": bool(passed), "reason": reason}
        for name, passed, reason in checks
    ]


def _compact_missing_ranges(
    missing_by_reason: Mapping[str, Sequence[MatrixCellKey]],
) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for reason, cells in sorted(missing_by_reason.items()):
        by_variant: dict[str, set[MatrixCellKey]] = defaultdict(set)
        for cell in cells:
            by_variant[cell.variant].add(cell)
        cartesian_groups: dict[
            tuple[tuple[str, ...], tuple[int, ...], tuple[int, ...]],
            list[str],
        ] = defaultdict(list)
        residual: list[MatrixCellKey] = []
        for variant, group in by_variant.items():
            scenarios = tuple(sorted({cell.scenario for cell in group}))
            scales = tuple(sorted({cell.scale for cell in group}))
            seeds = tuple(sorted({cell.seed for cell in group}))
            expected = {
                MatrixCellKey(variant, scenario, scale, seed)
                for scenario in scenarios
                for scale in scales
                for seed in seeds
            }
            if group == expected:
                cartesian_groups[(scenarios, scales, seeds)].append(variant)
            else:
                residual.extend(sorted(group))
        for (scenarios, scales, seeds), variants in sorted(
            cartesian_groups.items()
        ):
            compact.append(
                {
                    "reason": reason,
                    "variants": sorted(
                        variants,
                        key=lambda value: EXPERIMENT_MATRIX_VARIANTS.index(value),
                    ),
                    "scenarios": list(scenarios),
                    "scales": list(scales),
                    "seed_ranges": _integer_ranges(seeds),
                    "cell_count": (
                        len(variants) * len(scenarios) * len(scales) * len(seeds)
                    ),
                }
            )
        residual_groups: dict[tuple[str, str, int], list[int]] = defaultdict(list)
        for cell in residual:
            residual_groups[(cell.variant, cell.scenario, cell.scale)].append(
                cell.seed
            )
        for (variant, scenario, scale), seeds in sorted(residual_groups.items()):
            compact.append(
                {
                    "reason": reason,
                    "variants": [variant],
                    "scenarios": [scenario],
                    "scales": [scale],
                    "seed_ranges": _integer_ranges(seeds),
                    "cell_count": len(seeds),
                }
            )
    return compact


def _index_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    offline: bool,
) -> dict[MatrixCellKey, list[Mapping[str, str]]]:
    indexed: dict[MatrixCellKey, list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        try:
            if offline:
                variant = row.get("algorithm_variant_normalized") or row.get(
                    "algorithm_variant"
                )
                scenario = row.get("experiment_matrix_scenario_family") or row.get(
                    "scenario"
                )
                scale = row.get("experiment_matrix_scale") or row.get("scale")
            else:
                variant = row.get("variant")
                scenario = row.get("scenario")
                scale = row.get("scale")
            cell = MatrixCellKey(
                str(variant).strip().upper(),
                str(scenario).strip().lower(),
                _strict_int(scale),
                _strict_int(row.get("seed")),
            )
        except (TypeError, ValueError):
            continue
        indexed[cell].append(row)
    return indexed


def _model_weight_reference(
    component: str,
    manifest: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    weights = manifest.get("weights")
    if isinstance(weights, Mapping):
        filename = weights.get("filename", weights.get("file"))
        digest = weights.get("sha256")
        return _optional_text(filename), _optional_sha256(digest)
    state = manifest.get("state_dict")
    if isinstance(state, Mapping):
        return (
            _optional_text(state.get("file", state.get("filename"))),
            _optional_sha256(state.get("sha256")),
        )
    return (
        _optional_text(manifest.get("state_dict_file")),
        _optional_sha256(manifest.get("state_dict_sha256")),
    )


def _model_assist_declaration(
    component: str,
    manifest: Mapping[str, Any],
) -> tuple[bool, str]:
    admission = manifest.get("admission")
    admission = admission if isinstance(admission, Mapping) else {}
    if component == "d3":
        allowed = admission.get("allowed_modes")
        valid = (
            admission.get("assist_authorized") is True
            and isinstance(allowed, list)
            and "assist" in allowed
        )
        return valid, "d3_assist_not_authorized"
    if component == "d4":
        holdout_seed_count = _csv_int(
            manifest.get("final_holdout_seed_count")
        )
        valid = (
            manifest.get("maximum_advisor_mode") == "assist"
            and manifest.get("strategy_capability_claim_allowed") is True
            and holdout_seed_count is not None
            and holdout_seed_count >= MINIMUM_FORMAL_UNSEEN_SEED_COUNT
        )
        return valid, "d4_assist_not_authorized"
    if component == "d5_graph":
        return (
            admission.get("g1_assist_eligible") is True,
            "d5_graph_assist_not_authorized",
        )
    runtime = manifest.get("runtime_policy")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    allowed = runtime.get("allowed_runtime_modes")
    valid = (
        admission.get("assist_admitted") is True
        and runtime.get("assist_admitted") is True
        and isinstance(allowed, list)
        and "assist" in allowed
    )
    return valid, "d5_active_vision_assist_not_authorized"


def _audit_bundle_checksum_file(root: Path) -> dict[str, Any]:
    path = root / "SHA256SUMS"
    if not path.is_file():
        return {
            "available": False,
            "valid": None,
            "path": None,
            "reason": "optional_checksum_file_absent",
        }
    valid = True
    entries = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, relative = line.split(None, 1)
            relative = relative.strip().lstrip("*")
            candidate = root / relative
            entries += 1
            if not _is_sha256(digest) or not candidate.is_file():
                valid = False
                continue
            if _sha256_file(candidate) != digest:
                valid = False
    except (OSError, ValueError):
        valid = False
    return {
        "available": True,
        "valid": valid and entries > 0,
        "path": str(path),
        "entry_count": entries,
        "reason": None if valid and entries > 0 else "checksum_mismatch_or_invalid",
    }


def _model_inventory_matches(
    inventory: Mapping[str, Any] | None,
    bundle_audits: Mapping[str, Mapping[str, Any]],
) -> bool:
    if not isinstance(inventory, Mapping):
        return False
    for component, audit in bundle_audits.items():
        record = inventory.get(component)
        if not isinstance(record, Mapping):
            return False
        expected_manifest = audit.get("manifest_sha256")
        expected_weights = audit.get("weights_sha256_observed")
        expected_bundle = audit.get("bundle_sha256")
        if record.get("manifest_sha256") != expected_manifest:
            return False
        if record.get("weights_sha256") != expected_weights:
            return False
        if record.get("bundle_sha256") != expected_bundle:
            return False
    return True


def _discover_valid_animations(root: Path | None) -> list[str]:
    if root is None or not root.is_dir():
        return []
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        suffix = path.suffix.lower()
        if suffix not in {".gif", ".mp4"} or not path.is_file():
            continue
        try:
            header = path.read_bytes()[:16]
        except OSError:
            continue
        valid = (
            suffix == ".gif"
            and header[:6] in {b"GIF87a", b"GIF89a"}
            or suffix == ".mp4"
            and len(header) >= 12
            and header[4:8] == b"ftyp"
        )
        if valid:
            found.append(str(path))
    return found


def _artifact_record(path: Path | None) -> dict[str, Any]:
    available = bool(path is not None and path.is_file())
    return {
        "path": str(path) if path is not None else None,
        "available": available,
        "sha256": _sha256_file(path) if available and path is not None else None,
    }


def _coerce_cell(raw: Any) -> MatrixCellKey:
    if isinstance(raw, MatrixCellKey):
        return raw
    if isinstance(raw, Mapping):
        variant = raw.get("variant", raw.get("algorithm_variant"))
        scenario = raw.get("scenario", raw.get("scenario_family"))
        scale = raw.get("scale")
        seed = raw.get("seed")
    else:
        variant = getattr(raw, "variant", None)
        scenario = getattr(raw, "scenario", None)
        scale = getattr(raw, "scale", None)
        seed = getattr(raw, "seed", None)
    variant_text = _required_text(variant, "variant").upper()
    scenario_text = _required_text(scenario, "scenario").lower()
    scale_value = _strict_int(scale)
    seed_value = _strict_int(seed)
    if scale_value <= 0 or seed_value < 0:
        raise ValueError("scale must be positive and seed non-negative")
    return MatrixCellKey(
        variant=variant_text,
        scenario=scenario_text,
        scale=scale_value,
        seed=seed_value,
    )


def _cell_dict(cell: MatrixCellKey) -> dict[str, Any]:
    return {
        "variant": cell.variant,
        "scenario": cell.scenario,
        "scale": cell.scale,
        "seed": cell.seed,
    }


def _integer_ranges(values: Iterable[int]) -> list[str]:
    ordered = sorted({int(value) for value in values})
    if not ordered:
        return []
    ranges: list[str] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = value
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ranges


def _bundle_sha256(entries: Mapping[str | None, str | None]) -> str | None:
    valid = sorted(
        (str(name), str(digest))
        for name, digest in entries.items()
        if name and digest
    )
    if not valid:
        return None
    payload = "".join(f"{digest}  {name}\n" for name, digest in valid)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON object required: {path}")
    return dict(payload)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_sha256(value: Any) -> str | None:
    return str(value).lower() if _is_sha256(value) else None


def _strict_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        parsed = int(value)
        if str(parsed) != value.strip() and not (
            value.strip().startswith("+")
            and str(parsed) == value.strip()[1:]
        ):
            raise ValueError("integer string is not canonical")
        return parsed
    raise ValueError("integer value required")


def _csv_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _csv_int(value: Any) -> int | None:
    try:
        return _strict_int(value)
    except (TypeError, ValueError):
        return None


def _csv_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [value]
    return parsed if isinstance(parsed, list) else [parsed]


def _positive_int(value: Any) -> bool:
    try:
        return _strict_int(value) > 0
    except (TypeError, ValueError):
        return False


def _nonnegative_int(value: Any) -> bool:
    try:
        return _strict_int(value) >= 0
    except (TypeError, ValueError):
        return False


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value.lower()) <= _HEX64
    )


def _is_git_commit(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 7 <= len(value) <= 64
        and set(value.lower()) <= _HEX64
    )


__all__ = [
    "EXPERIMENT_MATRIX_ADMISSION_DATE",
    "EXPERIMENT_MATRIX_ADMISSION_SCHEMA_VERSION",
    "EXPERIMENT_MATRIX_INVENTORY_SCHEMA_VERSION",
    "EXPERIMENT_MATRIX_SCENARIOS",
    "EXPERIMENT_MATRIX_SCALES",
    "EXPERIMENT_MATRIX_VARIANTS",
    "MINIMUM_FORMAL_UNSEEN_SEED_COUNT",
    "MatrixCellKey",
    "audit_experiment_matrix_admission",
    "inventory_from_plan",
    "load_expected_inventory",
    "render_experiment_matrix_admission_markdown",
    "write_experiment_matrix_admission_report",
]
