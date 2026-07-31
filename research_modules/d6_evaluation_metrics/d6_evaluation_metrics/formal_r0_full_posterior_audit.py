"""Independent full-scope posterior audit for the clean formal R0 run.

The full audit treats the frozen execution plan as the canonical 900-cell
scope.  Producer merge files are untrusted indexes: their checksums, shard
references, cell identities, and episode paths are recomputed before use.
Every episode is then evaluated through the same low-level D6 evaluator used
by the targeted five-cell audit.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .formal_r0_targeted_posterior_audit import (
    FormalR0TargetCell,
    FormalR0TargetedPosteriorAuditError,
    FormalR0TargetedPosteriorAuditInputs,
    _is_hex_digest,
    _read_json_object,
    _sha256_file,
    audit_formal_r0_targeted_posterior,
)
from .strict_offline_identity import strict_id_switch_provenance_is_verified


FORMAL_R0_FULL_POSTERIOR_INPUT_SCHEMA_VERSION = (
    "d6.formal-r0-full-posterior-audit-input.v1"
)
FORMAL_R0_FULL_POSTERIOR_AUDIT_SCHEMA_VERSION = (
    "d6.formal-r0-full-posterior-audit.v2"
)
FORMAL_R0_FULL_POSTERIOR_COMPACT_SCHEMA_VERSION = (
    "d6.formal-r0-full-posterior-audit-compact.v2"
)
FORMAL_R0_FULL_POSTERIOR_AUDIT_DATE = "2026-07-30"

_MERGED_SCOPE_SCHEMA = "scalable3d-experiment-matrix-scope-merge-v1"
_MERGED_SCOPE_FILES = (
    "episode_dirs.json",
    "experiment_matrix_scope_cells.csv",
    "experiment_matrix_scope_manifest.json",
)
_REQUIRED_EVIDENCE_FIELDS = (
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
    "d4_current_d3_plan_binding_verified",
    "d4_current_plan_coalition_commit_verified",
)
_SAFETY_ZERO_FIELDS = (
    "online_truth_use_count",
    "online_truth_field_violation_count",
    "d4_advice_resource_quota_conservation_violation_count",
    "d4_advice_formal_decision_mutation_count",
    "d5_active_vision_target_reference_violation_count",
    "d5_active_vision_ack_target_mismatch_count",
)
_COUNT_FIELDS = (
    "d1_posterior_generation",
    "d1_full_posterior_publication_count",
    "d2_consumed_d1_posterior_generation",
    "d2_posterior_consumption_count",
    "d2_association_publication_count",
    "d2_pre_tick_posterior_merge_count",
    "d2_finalize_unchanged_posterior_skip_count",
    "d2_id_switch_count",
    *_SAFETY_ZERO_FIELDS,
)


class FormalR0FullPosteriorAuditError(ValueError):
    """Raised when the frozen full-scope audit request is malformed."""


@dataclass(frozen=True)
class FormalR0FullPosteriorAuditInputs:
    """Frozen provenance and denominator for one complete R0 scope audit."""

    execution_root: Path
    source_repository: Path
    expected_source_git_commit: str
    expected_execution_plan_sha256: str
    expected_scope_cell_count: int = 900
    expected_parent_cell_count: int = 5700
    expected_shard_count: int = 20
    expected_cells_per_shard: int = 45
    merged_scope_relative_path: Path = Path("merged_scope")

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
        merged_relative = Path(self.merged_scope_relative_path)
        if merged_relative.is_absolute() or ".." in merged_relative.parts:
            raise FormalR0FullPosteriorAuditError(
                "merged_scope_relative_path must remain inside execution_root"
            )
        object.__setattr__(
            self,
            "merged_scope_relative_path",
            merged_relative,
        )
        if not _is_hex_digest(self.expected_source_git_commit, 40):
            raise FormalR0FullPosteriorAuditError(
                "expected_source_git_commit must be a lowercase 40-character Git id"
            )
        if not _is_hex_digest(self.expected_execution_plan_sha256, 64):
            raise FormalR0FullPosteriorAuditError(
                "expected_execution_plan_sha256 must be lowercase SHA-256"
            )
        counts = (
            self.expected_scope_cell_count,
            self.expected_parent_cell_count,
            self.expected_shard_count,
            self.expected_cells_per_shard,
        )
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
            for value in counts
        ):
            raise FormalR0FullPosteriorAuditError(
                "scope, parent, shard, and per-shard counts must be positive integers"
            )
        if (
            self.expected_shard_count * self.expected_cells_per_shard
            != self.expected_scope_cell_count
        ):
            raise FormalR0FullPosteriorAuditError(
                "shard_count * cells_per_shard must equal scope_cell_count"
            )
        if self.expected_parent_cell_count < self.expected_scope_cell_count:
            raise FormalR0FullPosteriorAuditError(
                "parent cell count must not be smaller than R0 scope"
            )

    @property
    def merged_scope_dir(self) -> Path:
        return self.execution_root / self.merged_scope_relative_path


def load_formal_r0_full_posterior_audit_inputs(
    path: str | Path,
) -> FormalR0FullPosteriorAuditInputs:
    """Load a strict full-scope audit configuration."""

    config_path = Path(path).resolve()
    try:
        payload = _read_json_object(config_path)
    except (OSError, FormalR0TargetedPosteriorAuditError) as exc:
        raise FormalR0FullPosteriorAuditError(str(exc)) from exc
    if payload.get("schema_version") != (
        FORMAL_R0_FULL_POSTERIOR_INPUT_SCHEMA_VERSION
    ):
        raise FormalR0FullPosteriorAuditError(
            "full posterior input schema is unsupported"
        )
    try:
        return FormalR0FullPosteriorAuditInputs(
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
            expected_parent_cell_count=int(
                payload["expected_parent_cell_count"]
            ),
            expected_shard_count=int(payload["expected_shard_count"]),
            expected_cells_per_shard=int(
                payload["expected_cells_per_shard"]
            ),
            merged_scope_relative_path=Path(
                str(payload.get("merged_scope_relative_path", "merged_scope"))
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalR0FullPosteriorAuditError(
            f"full posterior input is malformed: {exc}"
        ) from exc


def audit_formal_r0_full_posterior(
    inputs: FormalR0FullPosteriorAuditInputs,
) -> dict[str, Any]:
    """Audit all cells in one frozen, complete formal R0 execution scope."""

    plan_path = inputs.execution_root / "experiment_matrix_execution_plan.json"
    structural_reasons: list[str] = []
    try:
        plan = _read_json_object(plan_path)
    except (OSError, FormalR0TargetedPosteriorAuditError) as exc:
        plan = None
        structural_reasons.append(f"execution_plan_unreadable:{exc}")

    canonical = audit_canonical_r0_scope(plan, inputs)
    structural_reasons.extend(canonical["failure_reasons"])
    targets = tuple(canonical["targets"])

    core_result: dict[str, Any]
    if targets:
        targeted_inputs = FormalR0TargetedPosteriorAuditInputs(
            execution_root=inputs.execution_root,
            source_repository=inputs.source_repository,
            expected_source_git_commit=inputs.expected_source_git_commit,
            expected_execution_plan_sha256=(
                inputs.expected_execution_plan_sha256
            ),
            expected_scope_cell_count=inputs.expected_scope_cell_count,
            expected_completed_cell_count=inputs.expected_scope_cell_count,
            expected_shard_progress=tuple(
                (index, inputs.expected_cells_per_shard)
                for index in range(inputs.expected_shard_count)
            ),
            targets=targets,
        )
        core_result = audit_formal_r0_targeted_posterior(targeted_inputs)
    else:
        core_result = _empty_core_result(inputs)

    core_cells = {
        str(row.get("cell_id")): dict(row)
        for row in core_result.get("cells", ())
        if row.get("cell_id") is not None
    }
    merged_scope = audit_merged_scope_indexes(
        inputs,
        canonical_cells=canonical["cells"],
        core_cells=core_cells,
    )
    structural_reasons.extend(merged_scope["failure_reasons"])
    structural_reasons.extend(
        core_result.get("source", {}).get("failure_reasons", ())
    )
    structural_reasons.extend(
        core_result.get("execution_plan", {}).get("failure_reasons", ())
    )
    structural_reasons.extend(
        core_result.get("execution_progress", {}).get(
            "failure_reasons",
            (),
        )
    )
    structural_reasons = list(dict.fromkeys(str(value) for value in structural_reasons))

    merge_cell_reasons = merged_scope["cell_failure_reasons"]
    cells: list[dict[str, Any]] = []
    for canonical_cell in canonical["cells"]:
        cell_id = str(canonical_cell["cell_id"])
        row = dict(core_cells.get(cell_id, {}))
        if not row:
            row = {
                "cell_id": cell_id,
                "shard_index": canonical_cell.get("shard_index"),
                "scenario": canonical_cell.get("scenario"),
                "scale": canonical_cell.get("scale"),
                "seed": canonical_cell.get("seed"),
                "verified": False,
                "failure_reasons": ["cell_low_level_audit_missing"],
            }
        reasons = list(row.get("failure_reasons", ()))
        reasons.extend(merge_cell_reasons.get(cell_id, ()))
        reasons.extend(required_evidence_gate_reasons(row))
        if structural_reasons:
            reasons.append("full_scope_global_integrity_not_verified")
        reasons = list(dict.fromkeys(str(value) for value in reasons))
        row["merged_scope_index_verified"] = not merge_cell_reasons.get(cell_id)
        row["required_evidence_available"] = not required_evidence_gate_reasons(
            row
        )
        row["verified"] = row.get("verified") is True and not reasons
        row["failure_reasons"] = reasons
        cells.append(row)

    if len(cells) != inputs.expected_scope_cell_count:
        structural_reasons.append(
            "full_scope_audited_cell_count_mismatch:"
            f"expected={inputs.expected_scope_cell_count}:actual={len(cells)}"
        )
    structural_reasons = list(dict.fromkeys(structural_reasons))
    aggregate = aggregate_formal_r0_full_posterior_rows(
        cells,
        expected_scope_cell_count=inputs.expected_scope_cell_count,
        global_failure_reasons=structural_reasons,
    )
    all_reasons = list(
        dict.fromkeys(
            [
                *structural_reasons,
                *(
                    reason
                    for row in cells
                    for reason in row.get("failure_reasons", ())
                ),
            ]
        )
    )
    verdict = (
        "pass"
        if not all_reasons
        and aggregate["verified_cell_count"]
        == inputs.expected_scope_cell_count
        else "fail_closed"
    )
    return {
        "schema_version": FORMAL_R0_FULL_POSTERIOR_AUDIT_SCHEMA_VERSION,
        "evaluation_date": FORMAL_R0_FULL_POSTERIOR_AUDIT_DATE,
        "verdict": verdict,
        "fail_closed": verdict != "pass",
        "scope_boundary": {
            "formal_r0_scope_completed_cell_count": (
                inputs.expected_scope_cell_count
            ),
            "formal_r0_scope_expected_cell_count": (
                inputs.expected_scope_cell_count
            ),
            "formal_r0_scope_complete": (
                aggregate["audited_cell_count"]
                == inputs.expected_scope_cell_count
            ),
            "parent_matrix_completed_cell_count": (
                inputs.expected_scope_cell_count
            ),
            "parent_matrix_expected_cell_count": (
                inputs.expected_parent_cell_count
            ),
            "parent_matrix_complete": False,
            "old_source_result_composition_allowed": False,
            "g1_a1_a2_a3_comparators_available": False,
            "causal_benefit_conclusion_available": False,
        },
        "inputs": {
            "execution_root": str(inputs.execution_root),
            "merged_scope_dir": str(inputs.merged_scope_dir),
            "source_repository": str(inputs.source_repository),
            "expected_source_git_commit": inputs.expected_source_git_commit,
            "expected_execution_plan_sha256": (
                inputs.expected_execution_plan_sha256
            ),
            "ignored_producer_aggregates": (
                "merged_scope/d6_evaluation",
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
        "source": core_result.get("source", {}),
        "evaluator": aggregate["evaluator_provenance"],
        "execution_plan": core_result.get("execution_plan", {}),
        "execution_progress": core_result.get("execution_progress", {}),
        "canonical_scope": {
            key: value
            for key, value in canonical.items()
            if key not in {"targets", "cells"}
        },
        "merged_scope": {
            key: value
            for key, value in merged_scope.items()
            if key != "cell_failure_reasons"
        },
        "comparison_availability": {
            name: {
                "available": False,
                "unavailable_reason": "formal_r0_single_arm_scope_only",
            }
            for name in ("G1", "A1", "A2", "A3")
        },
        "aggregate": aggregate,
        "failure_reasons": all_reasons,
        "cells": cells,
    }


def audit_canonical_r0_scope(
    plan: Mapping[str, Any] | None,
    inputs: FormalR0FullPosteriorAuditInputs,
) -> dict[str, Any]:
    """Extract 900 unique R0 targets only after structural checks."""

    reasons: list[str] = []
    raw_cells: Any = None
    if plan is None:
        reasons.append("canonical_execution_plan_unavailable")
    else:
        scope = plan.get("scope")
        raw_cells = scope.get("cells") if isinstance(scope, Mapping) else None
    if not isinstance(raw_cells, list):
        reasons.append("canonical_scope_cells_unavailable")
        raw_cells = []
    if len(raw_cells) != inputs.expected_scope_cell_count:
        reasons.append(
            "canonical_scope_cell_count_mismatch:"
            f"expected={inputs.expected_scope_cell_count}:actual={len(raw_cells)}"
        )

    cells: list[dict[str, Any]] = []
    cell_ids: list[str] = []
    scope_indices: list[int] = []
    global_indices: list[int] = []
    shard_counts: Counter[int] = Counter()
    for position, raw in enumerate(raw_cells):
        if not isinstance(raw, Mapping):
            reasons.append(f"canonical_cell_not_object:{position}")
            continue
        cell = dict(raw)
        cell_id = cell.get("cell_id")
        if not isinstance(cell_id, str) or not cell_id.strip():
            reasons.append(f"canonical_cell_id_invalid:{position}")
            continue
        cell_ids.append(cell_id)
        integer_fields: dict[str, int] = {}
        for field in (
            "global_index",
            "scope_index",
            "shard_index",
            "shard_sequence",
            "scale",
            "seed",
        ):
            value = cell.get(field)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                reasons.append(
                    f"canonical_cell_integer_invalid:{cell_id}:{field}"
                )
            else:
                integer_fields[field] = value
        if cell.get("variant") != "R0":
            reasons.append(f"canonical_cell_not_r0:{cell_id}")
        if not isinstance(cell.get("scenario"), str):
            reasons.append(f"canonical_cell_scenario_invalid:{cell_id}")
        scope_index = integer_fields.get("scope_index")
        shard_index = integer_fields.get("shard_index")
        shard_sequence = integer_fields.get("shard_sequence")
        if scope_index is not None:
            scope_indices.append(scope_index)
            if scope_index != position:
                reasons.append(
                    f"canonical_scope_order_mismatch:{cell_id}"
                )
        if "global_index" in integer_fields:
            global_indices.append(integer_fields["global_index"])
        if shard_index is not None:
            shard_counts[shard_index] += 1
        if (
            scope_index is not None
            and shard_index is not None
            and shard_index
            != scope_index % inputs.expected_shard_count
        ):
            reasons.append(f"canonical_shard_assignment_mismatch:{cell_id}")
        if (
            scope_index is not None
            and shard_sequence is not None
            and shard_sequence
            != scope_index // inputs.expected_shard_count
        ):
            reasons.append(f"canonical_shard_sequence_mismatch:{cell_id}")
        cells.append(cell)

    if len(set(cell_ids)) != len(cell_ids):
        reasons.append("canonical_duplicate_cell_id")
    if len(set(scope_indices)) != len(scope_indices):
        reasons.append("canonical_duplicate_scope_index")
    if len(set(global_indices)) != len(global_indices):
        reasons.append("canonical_duplicate_global_index")
    if sorted(scope_indices) != list(range(inputs.expected_scope_cell_count)):
        reasons.append("canonical_scope_index_set_mismatch")
    expected_shards = set(range(inputs.expected_shard_count))
    if set(shard_counts) != expected_shards:
        reasons.append("canonical_shard_index_set_mismatch")
    for shard_index in sorted(expected_shards):
        if shard_counts.get(shard_index, 0) != inputs.expected_cells_per_shard:
            reasons.append(
                "canonical_shard_cell_count_mismatch:"
                f"shard={shard_index}:"
                f"expected={inputs.expected_cells_per_shard}:"
                f"actual={shard_counts.get(shard_index, 0)}"
            )
    targets = tuple(
        FormalR0TargetCell(
            shard_index=int(cell["shard_index"]),
            cell_id=str(cell["cell_id"]),
        )
        for cell in cells
        if isinstance(cell.get("shard_index"), int)
        and not isinstance(cell.get("shard_index"), bool)
    )
    reasons = list(dict.fromkeys(reasons))
    return {
        "verified": not reasons,
        "cell_count": len(cells),
        "unique_cell_id_count": len(set(cell_ids)),
        "shard_count": len(shard_counts),
        "shard_cell_counts": {
            str(index): shard_counts.get(index, 0)
            for index in range(inputs.expected_shard_count)
        },
        "failure_reasons": reasons,
        "cells": tuple(cells),
        "targets": targets,
    }


def audit_merged_scope_indexes(
    inputs: FormalR0FullPosteriorAuditInputs,
    *,
    canonical_cells: Sequence[Mapping[str, Any]],
    core_cells: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Cross-check producer merge indexes without trusting their metrics."""

    merged_dir = inputs.merged_scope_dir
    reasons: list[str] = []
    cell_reasons: dict[str, list[str]] = defaultdict(list)
    checksums = audit_checksum_manifest(
        merged_dir / "SHA256SUMS",
        merged_dir=merged_dir,
    )
    reasons.extend(checksums["failure_reasons"])

    manifest = _load_json_for_full_audit(
        merged_dir / "experiment_matrix_scope_manifest.json",
        reasons,
        "merged_manifest",
    )
    episode_index = _load_json_for_full_audit(
        merged_dir / "episode_dirs.json",
        reasons,
        "merged_episode_index",
    )
    manifest_result = validate_merged_scope_manifest(
        manifest,
        inputs=inputs,
    )
    reasons.extend(manifest_result["failure_reasons"])

    expected_paths = [
        _expected_episode_relative_path(cell, inputs.expected_shard_count)
        for cell in canonical_cells
    ]
    index_result = validate_merged_episode_index(
        episode_index,
        inputs=inputs,
        expected_paths=expected_paths,
    )
    reasons.extend(index_result["failure_reasons"])

    shard_result = audit_merged_shard_hashes(
        manifest,
        inputs=inputs,
    )
    reasons.extend(shard_result["failure_reasons"])

    csv_result = audit_merged_scope_csv(
        merged_dir / "experiment_matrix_scope_cells.csv",
        inputs=inputs,
        canonical_cells=canonical_cells,
        core_cells=core_cells,
    )
    reasons.extend(csv_result["failure_reasons"])
    for cell_id, values in csv_result["cell_failure_reasons"].items():
        cell_reasons[cell_id].extend(values)

    indexed_paths = set(index_result.get("paths", ()))
    for cell in canonical_cells:
        cell_id = str(cell.get("cell_id"))
        expected = _expected_episode_relative_path(
            cell,
            inputs.expected_shard_count,
        )
        if expected not in indexed_paths:
            cell_reasons[cell_id].append(
                "merged_episode_index_cell_path_missing"
            )

    reasons = list(dict.fromkeys(reasons))
    return {
        "verified": not reasons and not any(cell_reasons.values()),
        "checksum_manifest": checksums,
        "manifest": manifest_result,
        "episode_index": {
            key: value for key, value in index_result.items() if key != "paths"
        },
        "shard_hashes": shard_result,
        "scope_csv": {
            key: value
            for key, value in csv_result.items()
            if key != "cell_failure_reasons"
        },
        "failure_reasons": reasons,
        "cell_failure_reasons": {
            key: list(dict.fromkeys(values))
            for key, values in sorted(cell_reasons.items())
            if values
        },
    }


def audit_checksum_manifest(
    path: Path,
    *,
    merged_dir: Path,
) -> dict[str, Any]:
    """Verify the merge checksum manifest and its exact three-file scope."""

    reasons: list[str] = []
    entries: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {
            "verified": False,
            "entries": {},
            "failure_reasons": [f"merged_checksum_manifest_unreadable:{exc}"],
        }
    for line_number, line in enumerate(lines, start=1):
        parts = line.split()
        if (
            len(parts) != 2
            or not _is_hex_digest(parts[0], 64)
            or Path(parts[1]).name != parts[1]
        ):
            reasons.append(
                f"merged_checksum_manifest_row_invalid:{line_number}"
            )
            continue
        if parts[1] in entries:
            reasons.append(
                f"merged_checksum_manifest_duplicate_path:{parts[1]}"
            )
            continue
        entries[parts[1]] = parts[0]
    if set(entries) != set(_MERGED_SCOPE_FILES):
        reasons.append("merged_checksum_manifest_file_set_mismatch")
    for name in _MERGED_SCOPE_FILES:
        target = merged_dir / name
        if not target.is_file():
            reasons.append(f"merged_checksum_target_missing:{name}")
            continue
        if entries.get(name) != _sha256_file(target):
            reasons.append(f"merged_checksum_mismatch:{name}")
    reasons = list(dict.fromkeys(reasons))
    return {
        "verified": not reasons,
        "entries": entries,
        "failure_reasons": reasons,
    }


def validate_merged_scope_manifest(
    manifest: Mapping[str, Any] | None,
    *,
    inputs: FormalR0FullPosteriorAuditInputs,
) -> dict[str, Any]:
    """Validate merge metadata before its shard hashes are considered."""

    reasons: list[str] = []
    if manifest is None:
        reasons.append("merged_manifest_unavailable")
        shards: list[Any] = []
    else:
        expectations = (
            ("schema_version", _MERGED_SCOPE_SCHEMA),
            ("execution_plan_sha256", inputs.expected_execution_plan_sha256),
            ("source_git_commit", inputs.expected_source_git_commit),
            ("source_repository_dirty", False),
            ("scope_expected_cell_count", inputs.expected_scope_cell_count),
            ("scope_completed_cell_count", inputs.expected_scope_cell_count),
            ("shard_count", inputs.expected_shard_count),
            ("parent_full_cell_count", inputs.expected_parent_cell_count),
            ("scope_complete", True),
            ("formal_scope_complete", True),
            ("full_matrix_complete", False),
            ("formal_matrix_complete", False),
            ("scope_variants", ["R0"]),
            ("status", "formal_scope_complete"),
        )
        for field, expected in expectations:
            if manifest.get(field) != expected:
                reasons.append(f"merged_manifest_{field}_mismatch")
        raw_shards = manifest.get("shards")
        shards = raw_shards if isinstance(raw_shards, list) else []
        if not isinstance(raw_shards, list):
            reasons.append("merged_manifest_shards_unavailable")
    shard_indices = [
        row.get("shard_index")
        for row in shards
        if isinstance(row, Mapping)
    ]
    if len(shards) != inputs.expected_shard_count:
        reasons.append("merged_manifest_shard_count_mismatch")
    if sorted(shard_indices) != list(range(inputs.expected_shard_count)):
        reasons.append("merged_manifest_shard_index_set_mismatch")
    if len(set(shard_indices)) != len(shard_indices):
        reasons.append("merged_manifest_duplicate_shard_index")
    for row in shards:
        if not isinstance(row, Mapping):
            reasons.append("merged_manifest_shard_not_object")
            continue
        index = row.get("shard_index")
        if not isinstance(index, int) or isinstance(index, bool):
            continue
        if row.get("shard_id") != (
            f"shard_{index:03d}_of_{inputs.expected_shard_count:03d}"
        ):
            reasons.append(
                f"merged_manifest_shard_id_mismatch:{index}"
            )
        if row.get("cell_count") != inputs.expected_cells_per_shard:
            reasons.append(
                f"merged_manifest_shard_cell_count_mismatch:{index}"
            )
        for field in (
            "checkpoint_sha256",
            "progress_sha256",
            "shard_plan_sha256",
        ):
            if not _is_hex_digest(row.get(field), 64):
                reasons.append(
                    f"merged_manifest_shard_digest_invalid:{index}:{field}"
                )
    reasons = list(dict.fromkeys(reasons))
    return {
        "verified": not reasons,
        "shard_count": len(shards),
        "failure_reasons": reasons,
    }


def validate_merged_episode_index(
    payload: Mapping[str, Any] | None,
    *,
    inputs: FormalR0FullPosteriorAuditInputs,
    expected_paths: Sequence[str],
) -> dict[str, Any]:
    """Require the episode index to match all canonical plan paths exactly."""

    reasons: list[str] = []
    if payload is None:
        paths: list[Any] = []
        reasons.append("merged_episode_index_unavailable")
    else:
        if payload.get("schema_version") != _MERGED_SCOPE_SCHEMA:
            reasons.append("merged_episode_index_schema_mismatch")
        if payload.get("execution_plan_sha256") != (
            inputs.expected_execution_plan_sha256
        ):
            reasons.append("merged_episode_index_execution_sha_mismatch")
        if payload.get("episode_count") != inputs.expected_scope_cell_count:
            reasons.append("merged_episode_index_count_mismatch")
        raw_paths = payload.get("paths_relative_to_execution_root")
        paths = raw_paths if isinstance(raw_paths, list) else []
        if not isinstance(raw_paths, list):
            reasons.append("merged_episode_index_paths_unavailable")
    if len(paths) != inputs.expected_scope_cell_count:
        reasons.append("merged_episode_index_path_count_mismatch")
    if any(not isinstance(value, str) for value in paths):
        reasons.append("merged_episode_index_path_not_string")
    string_paths = [value for value in paths if isinstance(value, str)]
    if len(set(string_paths)) != len(string_paths):
        reasons.append("merged_episode_index_duplicate_path")
    for value in string_paths:
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            reasons.append(f"merged_episode_index_unsafe_path:{value}")
    if string_paths != list(expected_paths):
        reasons.append("merged_episode_index_canonical_order_or_set_mismatch")
    for value in string_paths:
        if not (inputs.execution_root / value).is_dir():
            reasons.append(f"merged_episode_index_directory_missing:{value}")
    reasons = list(dict.fromkeys(reasons))
    return {
        "verified": not reasons,
        "episode_count": len(string_paths),
        "paths": tuple(string_paths),
        "failure_reasons": reasons,
    }


def audit_merged_shard_hashes(
    manifest: Mapping[str, Any] | None,
    *,
    inputs: FormalR0FullPosteriorAuditInputs,
) -> dict[str, Any]:
    """Recompute every shard plan, checkpoint, and progress digest."""

    reasons: list[str] = []
    raw_shards = (
        manifest.get("shards")
        if isinstance(manifest, Mapping)
        and isinstance(manifest.get("shards"), list)
        else []
    )
    by_index = {
        row.get("shard_index"): row
        for row in raw_shards
        if isinstance(row, Mapping)
        and isinstance(row.get("shard_index"), int)
        and not isinstance(row.get("shard_index"), bool)
    }
    rows: list[dict[str, Any]] = []
    for index in range(inputs.expected_shard_count):
        shard_id = f"shard_{index:03d}_of_{inputs.expected_shard_count:03d}"
        shard_dir = inputs.execution_root / "shards" / shard_id
        declared = by_index.get(index, {})
        shard_reasons: list[str] = []
        computed: dict[str, str | None] = {}
        for filename, field in (
            ("shard_plan.json", "shard_plan_sha256"),
            ("checkpoint.json", "checkpoint_sha256"),
            ("progress.jsonl", "progress_sha256"),
        ):
            artifact = shard_dir / filename
            digest = _sha256_file(artifact) if artifact.is_file() else None
            computed[field] = digest
            if digest is None:
                shard_reasons.append(f"shard_artifact_missing:{filename}")
            elif declared.get(field) != digest:
                shard_reasons.append(f"shard_artifact_digest_mismatch:{field}")
        reasons.extend(
            f"{shard_id}:{reason}" for reason in shard_reasons
        )
        rows.append(
            {
                "shard_index": index,
                "shard_id": shard_id,
                "verified": not shard_reasons,
                "computed_sha256": computed,
                "failure_reasons": shard_reasons,
            }
        )
    reasons = list(dict.fromkeys(reasons))
    return {
        "verified": not reasons,
        "verified_shard_count": sum(row["verified"] is True for row in rows),
        "expected_shard_count": inputs.expected_shard_count,
        "shards": rows,
        "failure_reasons": reasons,
    }


def audit_merged_scope_csv(
    path: Path,
    *,
    inputs: FormalR0FullPosteriorAuditInputs,
    canonical_cells: Sequence[Mapping[str, Any]],
    core_cells: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Cross-check the producer CSV against canonical and recomputed evidence."""

    reasons: list[str] = []
    cell_reasons: dict[str, list[str]] = defaultdict(list)
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, csv.Error) as exc:
        return {
            "verified": False,
            "row_count": 0,
            "failure_reasons": [f"merged_scope_csv_unreadable:{exc}"],
            "cell_failure_reasons": {},
        }
    if len(rows) != inputs.expected_scope_cell_count:
        reasons.append(
            "merged_scope_csv_row_count_mismatch:"
            f"expected={inputs.expected_scope_cell_count}:actual={len(rows)}"
        )
    by_scope_index: dict[int, Mapping[str, str]] = {}
    for row_number, row in enumerate(rows, start=2):
        try:
            scope_index = int(row["scope_index"])
        except (KeyError, TypeError, ValueError):
            reasons.append(
                f"merged_scope_csv_scope_index_invalid:{row_number}"
            )
            continue
        if scope_index in by_scope_index:
            reasons.append(
                f"merged_scope_csv_duplicate_scope_index:{scope_index}"
            )
            continue
        by_scope_index[scope_index] = row
    for cell in canonical_cells:
        cell_id = str(cell.get("cell_id"))
        scope_index = cell.get("scope_index")
        row = by_scope_index.get(scope_index)
        if row is None:
            cell_reasons[cell_id].append("merged_scope_csv_cell_missing")
            continue
        expected_path = _expected_episode_relative_path(
            cell,
            inputs.expected_shard_count,
        )
        expected_strings = {
            "cell_index": str(scope_index),
            "scope_index": str(scope_index),
            "comparison_key": str(cell.get("comparison_key")),
            "episode_relative_path": expected_path,
            "scale": str(cell.get("scale")),
            "scenario": str(cell.get("scenario")),
            "seed": str(cell.get("seed")),
            "variant": "R0",
        }
        for field, expected in expected_strings.items():
            if row.get(field) != expected:
                cell_reasons[cell_id].append(
                    f"merged_scope_csv_{field}_mismatch"
                )
        core = core_cells.get(cell_id, {})
        for csv_field, core_field in (
            ("cell_result_sha256", "computed_cell_result_sha256"),
            (
                "episode_artifact_tree_sha256",
                "computed_artifact_tree_sha256",
            ),
        ):
            if row.get(csv_field) != core.get(core_field):
                cell_reasons[cell_id].append(
                    f"merged_scope_csv_{csv_field}_mismatch"
                )
        if _parse_csv_bool(row.get("finite_state")) is not core.get(
            "finite_state"
        ):
            cell_reasons[cell_id].append(
                "merged_scope_csv_finite_state_mismatch"
            )
        if _parse_csv_int(row.get("online_truth_use_count")) != core.get(
            "online_truth_use_count"
        ):
            cell_reasons[cell_id].append(
                "merged_scope_csv_online_truth_use_count_mismatch"
            )
    reasons = list(dict.fromkeys(reasons))
    return {
        "verified": not reasons and not any(cell_reasons.values()),
        "row_count": len(rows),
        "unique_scope_index_count": len(by_scope_index),
        "failure_reasons": reasons,
        "cell_failure_reasons": {
            key: list(dict.fromkeys(values))
            for key, values in sorted(cell_reasons.items())
            if values
        },
    }


def required_evidence_gate_reasons(row: Mapping[str, Any]) -> list[str]:
    """Fail closed when a required low-level value is unavailable."""

    reasons: list[str] = []
    for field in _REQUIRED_EVIDENCE_FIELDS:
        if row.get(f"{field}_availability") != "available":
            reasons.append(f"required_evidence_unavailable:{field}")
    if (
        row.get("d2_id_switch_count_availability") == "available"
        and not strict_id_switch_provenance_is_verified(row)
    ):
        reasons.append(
            "required_evidence_invalid_strict_provenance:"
            "d2_id_switch_count"
        )
    return reasons


def aggregate_formal_r0_full_posterior_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_scope_cell_count: int,
    global_failure_reasons: Sequence[str] = (),
) -> dict[str, Any]:
    """Aggregate the exact 900-cell denominator without zero-filling."""

    denominator = int(expected_scope_cell_count)
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
    failure_distribution = Counter(
        reason
        for row in rows
        for reason in row.get("failure_reasons", ())
    )
    return {
        "audit_denominator": denominator,
        "audited_cell_count": len(rows),
        "missing_audit_cell_count": max(0, denominator - len(rows)),
        "verified_cell_count": verified,
        "failed_closed_cell_count": denominator - verified,
        "verified_cell_rate": (
            float(verified) / denominator if denominator else None
        ),
        "clean_formal_cell_count": clean_formal,
        "experiment_matrix_formal_cell_count": matrix_formal,
        "generation_verified_cell_count": generation_verified,
        "generation_verified_cell_rate": (
            float(generation_verified) / denominator
            if denominator
            else None
        ),
        "skip": metric_availability_summary(
            rows,
            "d2_finalize_unchanged_posterior_skip_count",
            denominator=denominator,
        ),
        "pending_empty": boolean_availability_summary(
            rows,
            "d2_pending_generation_empty",
            denominator=denominator,
        ),
        "id_switch_count": metric_availability_summary(
            rows,
            "d2_id_switch_count",
            denominator=denominator,
        ),
        "online_producer_id_switch_diagnostic": metric_availability_summary(
            rows,
            "d2_online_producer_id_switch_count",
            denominator=denominator,
        ),
        "evaluator_provenance": _formal_evaluator_provenance(rows),
        "current_d3_d4_plan_binding": boolean_availability_summary(
            rows,
            "d4_current_d3_plan_binding_verified",
            denominator=denominator,
        ),
        "current_plan_coalition_commit": boolean_availability_summary(
            rows,
            "d4_current_plan_coalition_commit_verified",
            denominator=denominator,
        ),
        "communication_disposition_validation": boolean_availability_summary(
            rows,
            "d4_communication_disposition_validation_verified",
            denominator=denominator,
        ),
        "safety_zero_counts": {
            field: metric_availability_summary(
                rows,
                field,
                denominator=denominator,
                expected_zero=True,
            )
            for field in _SAFETY_ZERO_FIELDS
        },
        "posterior_count_availability": {
            field: metric_availability_summary(
                rows,
                field,
                denominator=denominator,
            )
            for field in _COUNT_FIELDS
            if field not in _SAFETY_ZERO_FIELDS
        },
        "by_scenario": group_audit_rows(rows, "scenario"),
        "by_scale": group_audit_rows(rows, "scale"),
        "by_seed": group_audit_rows(rows, "seed"),
        "cell_failure_reason_distribution": dict(
            sorted(failure_distribution.items())
        ),
        "global_failure_reason_distribution": dict(
            sorted(Counter(global_failure_reasons).items())
        ),
        "full_scope_integrity_verified": (
            len(rows) == denominator
            and verified == denominator
            and not global_failure_reasons
        ),
    }


def metric_availability_summary(
    rows: Sequence[Mapping[str, Any]],
    field: str,
    *,
    denominator: int,
    expected_zero: bool = False,
) -> dict[str, Any]:
    """Summarize a numeric metric while preserving unavailable values."""

    available_values: list[float | int] = []
    unavailable_reasons: Counter[str] = Counter()
    invalid_count = 0
    for row in rows:
        if row.get(f"{field}_availability") != "available":
            reason = row.get(f"{field}_unavailable_reason")
            unavailable_reasons[str(reason or "availability_not_available")] += 1
            continue
        if (
            field == "d2_id_switch_count"
            and not strict_id_switch_provenance_is_verified(row)
        ):
            unavailable_reasons["strict_offline_provenance_not_verified"] += 1
            continue
        value = row.get(field)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
        ):
            invalid_count += 1
            unavailable_reasons["available_value_not_numeric"] += 1
            continue
        available_values.append(value)
    available_count = len(available_values)
    unavailable_count = denominator - available_count
    all_available = available_count == denominator and invalid_count == 0
    return {
        "availability": "available" if all_available else "unavailable",
        "available_cell_count": available_count,
        "unavailable_cell_count": unavailable_count,
        "total": sum(available_values) if all_available else None,
        "zero_cell_count": sum(value == 0 for value in available_values),
        "nonzero_cell_count": sum(value != 0 for value in available_values),
        "expected_zero": expected_zero,
        "expected_zero_verified": (
            (
                all(value == 0 for value in available_values)
                if all_available
                else None
            )
            if expected_zero else None
        ),
        "unavailable_reason_distribution": dict(
            sorted(unavailable_reasons.items())
        ),
    }


def _formal_evaluator_provenance(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    def distinct(field: str) -> list[Any]:
        return sorted(
            {
                row.get(field)
                for row in rows
                if row.get(field) is not None
            },
            key=str,
        )

    return {
        "evaluator_schema_versions": distinct("d6_evaluator_schema_version"),
        "evaluator_git_commits": distinct("d6_evaluator_git_commit"),
        "evaluator_repository_dirty_values": distinct(
            "d6_evaluator_repository_dirty"
        ),
        "evaluator_source_tree_sha256_values": distinct(
            "d6_evaluator_source_tree_sha256"
        ),
        "episode_source_git_commits": distinct("episode_source_git_commit"),
        "source_and_evaluator_provenance_separated": True,
    }


def boolean_availability_summary(
    rows: Sequence[Mapping[str, Any]],
    field: str,
    *,
    denominator: int,
) -> dict[str, Any]:
    """Summarize a boolean metric without coercing missing values."""

    values: list[bool] = []
    unavailable_reasons: Counter[str] = Counter()
    for row in rows:
        value = row.get(field)
        if (
            row.get(f"{field}_availability") != "available"
            or not isinstance(value, bool)
        ):
            reason = row.get(f"{field}_unavailable_reason")
            unavailable_reasons[str(reason or "value_not_available_boolean")] += 1
            continue
        values.append(value)
    available_count = len(values)
    return {
        "availability": (
            "available" if available_count == denominator else "unavailable"
        ),
        "available_cell_count": available_count,
        "unavailable_cell_count": denominator - available_count,
        "true_cell_count": sum(value is True for value in values),
        "false_cell_count": sum(value is False for value in values),
        "all_true": (
            available_count == denominator and all(values)
            if denominator
            else None
        ),
        "unavailable_reason_distribution": dict(
            sorted(unavailable_reasons.items())
        ),
    }


def group_audit_rows(
    rows: Sequence[Mapping[str, Any]],
    field: str,
) -> list[dict[str, Any]]:
    """Produce bounded scenario, scale, or seed summaries."""

    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(field))].append(row)
    output: list[dict[str, Any]] = []
    for value, group in sorted(groups.items(), key=_group_sort_key):
        denominator = len(group)
        output.append(
            {
                field: _restore_group_value(value),
                "cell_count": denominator,
                "verified_cell_count": sum(
                    row.get("verified") is True for row in group
                ),
                "clean_formal_cell_count": sum(
                    row.get("formal_acceptance_eligible") is True
                    for row in group
                ),
                "generation_verified_cell_count": sum(
                    row.get(
                        "observation_governance_generation_integrity"
                    )
                    is True
                    and row.get(
                        "observation_governance_generation_contract_status"
                    )
                    == "verified"
                    for row in group
                ),
                "skip": metric_availability_summary(
                    group,
                    "d2_finalize_unchanged_posterior_skip_count",
                    denominator=denominator,
                ),
                "pending_empty": boolean_availability_summary(
                    group,
                    "d2_pending_generation_empty",
                    denominator=denominator,
                ),
                "online_truth_use": metric_availability_summary(
                    group,
                    "online_truth_use_count",
                    denominator=denominator,
                    expected_zero=True,
                ),
            }
        )
    return output


def write_formal_r0_full_posterior_audit(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Write the full result, per-cell CSV, Chinese report, and checksums."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "formal_r0_full_posterior_audit.json"
    csv_path = output / "formal_r0_full_posterior_cells.csv"
    markdown_path = output / "FORMAL_R0_FULL_POSTERIOR_AUDIT_CN.md"
    checksum_path = output / "SHA256SUMS"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    _write_cell_csv(csv_path, result.get("cells", ()))
    markdown_path.write_text(
        render_formal_r0_full_posterior_audit_markdown(result),
        encoding="utf-8",
    )
    payloads = (json_path, csv_path, markdown_path)
    checksum_path.write_text(
        "".join(
            f"{_sha256_file(path)}  {path.name}\n"
            for path in sorted(payloads, key=lambda item: item.name)
        ),
        encoding="utf-8",
    )
    return {
        "json": json_path,
        "csv": csv_path,
        "markdown": markdown_path,
        "checksums": checksum_path,
    }


def write_formal_r0_full_posterior_docs(
    docs_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Persist the Chinese report and compact evidence in tracked docs."""

    output = Path(docs_dir)
    output.mkdir(parents=True, exist_ok=True)
    markdown_path = output / "FORMAL_R0_FULL_POSTERIOR_AUDIT_CN.md"
    compact_path = (
        output / "FORMAL_R0_FULL_POSTERIOR_AUDIT_RESULT_20260730.json"
    )
    markdown_path.write_text(
        render_formal_r0_full_posterior_audit_markdown(result),
        encoding="utf-8",
    )
    compact_path.write_text(
        json.dumps(
            compact_formal_r0_full_posterior_result(result),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"markdown": markdown_path, "compact_json": compact_path}


def compact_formal_r0_full_posterior_result(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Remove 900 passing rows while preserving every failed row."""

    failed_cells = [
        row
        for row in result.get("cells", ())
        if row.get("verified") is not True
    ]
    return {
        "schema_version": FORMAL_R0_FULL_POSTERIOR_COMPACT_SCHEMA_VERSION,
        "evaluation_date": result.get("evaluation_date"),
        "verdict": result.get("verdict"),
        "fail_closed": result.get("fail_closed"),
        "scope_boundary": result.get("scope_boundary"),
        "inputs": result.get("inputs"),
        "source": result.get("source"),
        "execution_plan": result.get("execution_plan"),
        "execution_progress": result.get("execution_progress"),
        "canonical_scope": result.get("canonical_scope"),
        "merged_scope": result.get("merged_scope"),
        "comparison_availability": result.get("comparison_availability"),
        "evaluator": result.get("evaluator"),
        "aggregate": result.get("aggregate"),
        "failure_reasons": result.get("failure_reasons"),
        "failed_cells": failed_cells,
    }


def render_formal_r0_full_posterior_audit_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render a Chinese full-scope evidence report."""

    aggregate = result.get("aggregate", {})
    boundary = result.get("scope_boundary", {})
    source = result.get("source", {})
    evaluator = result.get("evaluator", {})
    plan = result.get("execution_plan", {})
    merged = result.get("merged_scope", {})
    lines = [
        "# 正式 R0 全量后验独立审计",
        "",
        f"评估日期：{result.get('evaluation_date')}",
        "",
        "## 结论",
        "",
        (
            f"审计结论为 **{result.get('verdict')}**。D6 逐项复算 "
            f"{aggregate.get('audited_cell_count')}/"
            f"{aggregate.get('audit_denominator')} 个正式 R0 episode，"
            f"通过 {aggregate.get('verified_cell_count')}/"
            f"{aggregate.get('audit_denominator')}。"
        ),
        (
            f"来源提交为 `{source.get('actual_git_commit')}`，"
            f"执行计划逻辑摘要为 `{plan.get('computed_logical_sha256')}`。"
        ),
        (
            "本次 D6 评估器提交为 "
            f"`{', '.join(evaluator.get('evaluator_git_commits', ())) or 'unavailable'}`，"
            "与 episode 来源提交分别记录。"
        ),
        (
            "该结论只覆盖单臂 R0 的 900 项。完整父矩阵仍为 "
            f"{boundary.get('parent_matrix_completed_cell_count')}/"
            f"{boundary.get('parent_matrix_expected_cell_count')}，"
            "G1、A1、A2、A3 尚无同范围对照，不能给出因果收益结论。"
        ),
        "",
        "## 审计方法",
        "",
        "1. 重新计算执行计划文件摘要和逻辑摘要，核对 clean source 提交。",
        "2. 独立核对 20 个 shard plan、checkpoint、progress 和 900 个 cell result。",
        "3. 将 merged scope 的 manifest、episode index 和 CSV 仅作为待复核索引，逐项核对其 SHA-256、路径和身份。",
        "4. 逐 episode 重算 artifact tree，并从在线观测总线和 summary 重新评估真值隔离、有限状态、clean formal 和实验矩阵资格。",
        "5. 重算 D1 发布代次、D2 消费代次、节拍前合并、末尾跳过、pending 和 generation integrity；身份交换只读取经清单、哈希和合同复核的真值隔离制品。缺值不补零，矛盾项失败关闭。",
        "6. 以最后 D3 计划为当前代次，逐区域核对最后 D4 的 plan_id、plan_version、可用的权威 epoch/lease 和当前联盟 ACK 闭合状态。旧代 committed 不计入当前计划通过。",
        "",
        "未读取 `merged_scope/d6_evaluation`、旧 `targeted_formal_d6` 或 episode 内 producer 生成的 `observation_governance_audit.json`。",
        "",
        "## 范围完整性",
        "",
        "| 项目 | 结果 |",
        "| --- | ---: |",
        f"| 正式 R0 scope | {aggregate.get('audited_cell_count')}/{aggregate.get('audit_denominator')} |",
        f"| 通过 | {aggregate.get('verified_cell_count')}/{aggregate.get('audit_denominator')} |",
        f"| clean formal | {aggregate.get('clean_formal_cell_count')}/{aggregate.get('audit_denominator')} |",
        f"| 实验矩阵资格 | {aggregate.get('experiment_matrix_formal_cell_count')}/{aggregate.get('audit_denominator')} |",
        f"| generation verified | {aggregate.get('generation_verified_cell_count')}/{aggregate.get('audit_denominator')} |",
        f"| D3-D4 当前计划绑定 | {aggregate.get('current_d3_d4_plan_binding', {}).get('true_cell_count')}/{aggregate.get('audit_denominator')} |",
        f"| 当前计划联盟提交 | {aggregate.get('current_plan_coalition_commit', {}).get('true_cell_count')}/{aggregate.get('audit_denominator')} |",
        f"| 逐消息处置证据可用 | {aggregate.get('communication_disposition_validation', {}).get('available_cell_count')}/{aggregate.get('audit_denominator')} |",
        f"| 20 分片哈希通过 | {merged.get('shard_hashes', {}).get('verified_shard_count')}/{merged.get('shard_hashes', {}).get('expected_shard_count')} |",
        "",
        "## 后验守恒",
        "",
        "| 指标 | 可用项 | 总量 | 零值项 | 非零项 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, field in (
        ("D2 末尾跳过", "skip"),
        ("D2 严格离线身份交换", "id_switch_count"),
        (
            "D2 在线 producer 身份交换诊断",
            "online_producer_id_switch_diagnostic",
        ),
    ):
        item = aggregate.get(field, {})
        lines.append(
            f"| {label} | {item.get('available_cell_count')}/"
            f"{aggregate.get('audit_denominator')} | "
            f"{_display_value(item.get('total'))} | "
            f"{item.get('zero_cell_count')} | "
            f"{item.get('nonzero_cell_count')} |"
        )
    pending = aggregate.get("pending_empty", {})
    lines.extend(
        [
            "",
            (
                "D2 pending 证据可用 "
                f"{pending.get('available_cell_count')}/"
                f"{aggregate.get('audit_denominator')}，"
                f"排空 {pending.get('true_cell_count')}/"
                f"{aggregate.get('audit_denominator')}。"
            ),
            "",
            "## 安全计数",
            "",
            "| 指标 | 可用项 | 总量 | 零计数通过 |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for field, item in aggregate.get("safety_zero_counts", {}).items():
        lines.append(
            f"| `{field}` | {item.get('available_cell_count')}/"
            f"{aggregate.get('audit_denominator')} | "
            f"{_display_value(item.get('total'))} | "
            f"{_bool_cn(item.get('expected_zero_verified'))} |"
        )
    lines.extend(
        [
            "",
            "## 场景结果",
            "",
            "| 场景 | cell | 通过 | clean formal | generation verified | skip 总量 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in aggregate.get("by_scenario", ()):
        lines.append(
            f"| {item.get('scenario')} | {item.get('cell_count')} | "
            f"{item.get('verified_cell_count')} | "
            f"{item.get('clean_formal_cell_count')} | "
            f"{item.get('generation_verified_cell_count')} | "
            f"{_display_value(item.get('skip', {}).get('total'))} |"
        )
    lines.extend(
        [
            "",
            "## 规模结果",
            "",
            "| 规模 | cell | 通过 | clean formal | generation verified | skip 总量 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in aggregate.get("by_scale", ()):
        lines.append(
            f"| {item.get('scale')} | {item.get('cell_count')} | "
            f"{item.get('verified_cell_count')} | "
            f"{item.get('clean_formal_cell_count')} | "
            f"{item.get('generation_verified_cell_count')} | "
            f"{_display_value(item.get('skip', {}).get('total'))} |"
        )
    lines.extend(
        [
            "",
            "## Seed 结果",
            "",
            "| Seed | cell | 通过 | clean formal | generation verified |",
            "| ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in aggregate.get("by_seed", ()):
        lines.append(
            f"| {item.get('seed')} | {item.get('cell_count')} | "
            f"{item.get('verified_cell_count')} | "
            f"{item.get('clean_formal_cell_count')} | "
            f"{item.get('generation_verified_cell_count')} |"
        )
    failed_cells = [
        row
        for row in result.get("cells", ())
        if row.get("verified") is not True
    ]
    if failed_cells:
        lines.extend(
            [
                "",
                "## 失败项",
                "",
                "| cell | 场景 | 规模 | seed | 原因 |",
                "| --- | --- | ---: | ---: | --- |",
            ]
        )
        for row in failed_cells:
            lines.append(
                f"| {row.get('cell_id')} | {row.get('scenario')} | "
                f"{row.get('scale')} | {row.get('seed')} | "
                f"`{json.dumps(row.get('failure_reasons', ()), ensure_ascii=False)}` |"
            )
    if result.get("failure_reasons"):
        lines.extend(
            [
                "",
                "## 失败原因汇总",
                "",
                *(
                    f"- `{reason}`"
                    for reason in result.get("failure_reasons", ())
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            "- 900/900 表示 clean source `1e5ed8d` 的正式 R0 单臂已完成并由 D6 逐项复核。",
            "- 旧 source 的 895/900 结果没有与本批次拼接。",
            "- 身份交换等依赖离线真值配对的指标若不可用，保留 `null` 和不可用原因，不写成 0。",
            "- 完整 5700-cell 父矩阵尚未完成，学习变体也未形成同范围结果。",
            "- 本报告不能用于声明 G1、A1、A2、A3 的收益、因果改进或生产准入。",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_cell_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
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
        "merged_scope_index_verified",
        "required_evidence_available",
        "online_truth_use_count",
        "online_truth_use_count_availability",
        "online_truth_field_violation_count",
        "online_truth_field_violation_count_availability",
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
        "d2_id_switch_count_availability",
        "d2_id_switch_count_unavailable_reason",
        "d2_online_producer_id_switch_count",
        "d2_online_producer_id_switch_count_availability",
        "d2_online_producer_id_switch_count_unavailable_reason",
        "d2_id_switch_count_semantics",
        "d2_id_switch_count_source_artifact",
        "d2_strict_identity_artifact_verified",
        "d2_strict_identity_verification_mode",
        "d2_strict_identity_truth_isolation_verified",
        "d2_strict_identity_id_switch_backfilled",
        "episode_source_git_commit",
        "d6_evaluator_schema_version",
        "d6_evaluator_git_commit",
        "d6_evaluator_repository_dirty",
        "d6_evaluator_source_tree_sha256",
        "d4_advice_resource_quota_conservation_violation_count",
        "d4_advice_formal_decision_mutation_count",
        "d4_current_d3_plan_binding_verified",
        "d4_current_d3_plan_binding_verified_availability",
        "d4_current_d3_plan_id_match",
        "d4_current_d3_plan_version_match",
        "d4_current_d3_authority_epoch_match",
        "d4_current_d3_authority_lease_match",
        "d4_current_plan_coalition_commit_verified",
        "d4_current_plan_coalition_commit_verified_availability",
        "d4_current_plan_coalition_state_distribution_json",
        "d4_current_plan_uncommitted_target_ids_json",
        "d4_communication_disposition_validation_verified",
        "d4_communication_disposition_validation_verified_availability",
        "d4_communication_disposition_record_count",
        "d5_active_vision_target_reference_violation_count",
        "d5_active_vision_ack_target_mismatch_count",
        "verified",
        "failure_reasons",
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for raw in rows:
            row = dict(raw)
            row["failure_reasons"] = ";".join(
                str(value) for value in row.get("failure_reasons", ())
            )
            writer.writerow({field: row.get(field) for field in fields})


def _empty_core_result(
    inputs: FormalR0FullPosteriorAuditInputs,
) -> dict[str, Any]:
    return {
        "source": {
            "verified": False,
            "failure_reasons": ["source_not_audited_without_canonical_cells"],
        },
        "execution_plan": {
            "verified": False,
            "failure_reasons": [
                "execution_plan_not_audited_without_canonical_cells"
            ],
        },
        "execution_progress": {
            "verified": False,
            "scope_cell_count": inputs.expected_scope_cell_count,
            "completed_cell_count": 0,
            "shard_progress": {},
            "failure_reasons": [
                "execution_progress_not_audited_without_canonical_cells"
            ],
        },
        "cells": [],
    }


def _load_json_for_full_audit(
    path: Path,
    reasons: list[str],
    label: str,
) -> dict[str, Any] | None:
    try:
        return _read_json_object(path)
    except (OSError, FormalR0TargetedPosteriorAuditError) as exc:
        reasons.append(f"{label}_unreadable:{exc}")
        return None


def _expected_episode_relative_path(
    cell: Mapping[str, Any],
    shard_count: int,
) -> str:
    shard_index = int(cell.get("shard_index", -1))
    return (
        f"shards/shard_{shard_index:03d}_of_{shard_count:03d}/"
        f"cells/{cell.get('cell_id')}/episode"
    )


def _parse_csv_bool(value: Any) -> bool | None:
    if value == "True":
        return True
    if value == "False":
        return False
    return None


def _parse_csv_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _group_sort_key(item: tuple[str, Any]) -> tuple[int, Any]:
    value = item[0]
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _restore_group_value(value: str) -> int | str | None:
    if value == "None":
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _display_value(value: Any) -> str:
    return "不可用" if value is None else str(value)


def _bool_cn(value: Any) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "不可用"
