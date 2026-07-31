"""Resumable, hash-bound shards for formal scalable-3D matrix execution.

The contract keeps one complete parent :class:`ExperimentMatrixPlan` and
selects a deterministic execution scope from that immutable inventory.  A
formal R0 run therefore remains bound to the complete 5,700-cell plan even
though only its 900 R0 cells are executed in the first phase.

Shard outputs are append-only at complete-cell boundaries.  A completed cell
is written to a temporary directory, validated, atomically renamed, and only
then appended to the shard progress log.  Resume accepts either a fully
indexed cell or the narrow crash window in which the final cell directory was
published before its progress row.  Partial or conflicting evidence fails
closed.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence

from .experiment_authorization import (
    ExperimentAuthorizationError,
    G1ShadowExperimentAuthorization,
    g1_shadow_scope_payload,
    load_g1_shadow_experiment_authorization,
    validate_authorization_binding_payload,
    validate_authorization_scope_binding,
)
from .experiment_matrix import (
    EXPERIMENT_MATRIX_SCHEMA_VERSION,
    EXPERIMENT_VARIANTS,
    PAIRED_SENSOR_RANDOM_SCHEDULE_VERSION,
    ExperimentCell,
    ExperimentMatrixPlan,
    ModelBundlePaths,
    _validate_resolved_variant,
    paired_exogenous_config_sha256,
    repository_state,
    required_model_components,
    runtime_options_for_variant,
    validate_required_bundles,
)
from .learning_runtime import resolve_learning_runtime
from .models import ScenarioConfig
from .module_stack import IntegratedStackConfig
from .orchestrator import run_episode
from .scenarios import AVAILABLE_SCENARIOS, make_curriculum_scenario


EXPERIMENT_MATRIX_EXECUTION_PLAN_SCHEMA = (
    "scalable3d-experiment-matrix-execution-plan-v1"
)
EXPERIMENT_MATRIX_AUTHORIZED_EXECUTION_PLAN_SCHEMA = (
    "scalable3d-experiment-matrix-execution-plan-v2"
)
EXPERIMENT_MATRIX_SHARD_PLAN_SCHEMA = (
    "scalable3d-experiment-matrix-shard-plan-v1"
)
EXPERIMENT_MATRIX_SHARD_PROGRESS_SCHEMA = (
    "scalable3d-experiment-matrix-shard-progress-v1"
)
EXPERIMENT_MATRIX_SHARD_CHECKPOINT_SCHEMA = (
    "scalable3d-experiment-matrix-shard-checkpoint-v1"
)
EXPERIMENT_MATRIX_CELL_RESULT_SCHEMA = (
    "scalable3d-experiment-matrix-cell-result-v1"
)
EXPERIMENT_MATRIX_SCOPE_MERGE_SCHEMA = (
    "scalable3d-experiment-matrix-scope-merge-v1"
)
EXPERIMENT_MATRIX_SHARD_STORAGE_VALIDATION_SCHEMA = (
    "scalable3d-experiment-matrix-shard-storage-validation-v1"
)
EXPERIMENT_MATRIX_SHARD_MERGE_FRAGMENT_SCHEMA = (
    "scalable3d-experiment-matrix-shard-merge-fragment-v1"
)
EXPERIMENT_MATRIX_MODEL_BUNDLE_BINDING_SCHEMA = (
    "scalable3d-experiment-matrix-model-bundle-binding-v1"
)
FORMAL_R0_DEFAULT_SHARD_COUNT = 20
FORMAL_R0_EXPECTED_CELL_COUNT = 900
FORMAL_PARENT_EXPECTED_CELL_COUNT = 5700
FORMAL_R0_DEFAULT_MINIMUM_FREE_BYTES = 20 * 1024**3
_D5_V5_RUNTIME_AUTHORITY_FIELDS = frozenset(
    {
        "model_promotion_granted",
        "g1_assist_granted",
        "default_path_change_granted",
        "assignment_authority_granted",
        "failover_authority_granted",
        "control_authority_granted",
    }
)

_EXECUTION_PLAN_FILENAME = "experiment_matrix_execution_plan.json"
_EXECUTION_PLAN_CHECKSUM_FILENAME = "EXECUTION_PLAN_SHA256"
_SHARD_PLAN_FILENAME = "shard_plan.json"
_SHARD_PROGRESS_FILENAME = "progress.jsonl"
_SHARD_CHECKPOINT_FILENAME = "checkpoint.json"
_CELL_RESULT_FILENAME = "cell_result.json"
_REQUIRED_EPISODE_ARTIFACTS = (
    "manifest.json",
    "scenario_config.json",
    "summary.json",
    "online_observations.jsonl",
    "offline_proximity_intercepts.jsonl",
    "stage_timings.csv",
)
_HEX64 = frozenset("0123456789abcdef")


class ExperimentMatrixShardError(RuntimeError):
    """Fail-closed matrix shard contract violation."""


def describe_g1_shadow_d5_bundle(
    bundle_dir: str | Path,
) -> dict[str, str]:
    """Return the immutable D5 v5 hashes required by an approval request.

    The descriptor is produced through the same model-bundle inventory and
    authority checks used when an execution plan is frozen.  It therefore
    cannot describe a development bundle that grants runtime authority or a
    bundle whose declared weights digest no longer matches the file.
    """

    bundles = ModelBundlePaths(d5_graph=Path(bundle_dir))
    binding = _build_learning_bundle_binding(("G1",), bundles)
    return _authorization_d5_bundle_descriptor(binding, bundles)


def create_experiment_matrix_execution_plan(
    *,
    root: str | Path,
    output_root: str | Path,
    base_config: ScenarioConfig,
    parent_plan: ExperimentMatrixPlan,
    scope_variants: Sequence[str],
    shard_count: int,
    bundles: ModelBundlePaths | None = None,
    device: str = "cpu",
    created_at_utc: str | None = None,
    experiment_authorization_path: str | Path | None = None,
    expected_experiment_authorization_sha256: str | None = None,
    revocation_registry_path: str | Path | None = None,
    authorization_now_utc: datetime | str | None = None,
) -> Path:
    """Freeze one parent inventory and deterministic round-robin shard map.

    Non-formal plans are supported for development tests, but their manifests
    remain explicitly non-formal.  A formal parent requires a clean source
    worktree and can never be inferred from independently created subplans.
    """

    repository_root = Path(root).resolve()
    destination = Path(output_root).resolve()
    count = int(shard_count)
    if count <= 0:
        raise ValueError("shard_count must be positive")
    if destination.exists():
        raise FileExistsError(f"execution output already exists: {destination}")

    normalized_scope = tuple(
        dict.fromkeys(str(value).strip().upper() for value in scope_variants)
    )
    if not normalized_scope:
        raise ValueError("scope_variants must not be empty")
    unknown = sorted(set(normalized_scope) - set(parent_plan.variants))
    if unknown:
        raise ValueError(f"scope variants are absent from parent plan: {unknown}")
    selected_bundles = bundles or ModelBundlePaths()
    validate_required_bundles(normalized_scope, selected_bundles)
    selected_device = str(device).strip()
    if not selected_device:
        raise ValueError("learning device must be non-empty")

    commit, dirty = repository_state(repository_root)
    if parent_plan.formal and dirty:
        raise ExperimentMatrixShardError(
            "formal execution plan requires repository_dirty=false"
        )
    if (
        experiment_authorization_path is not None
        or expected_experiment_authorization_sha256 is not None
        or revocation_registry_path is not None
    ) and dirty:
        raise ExperimentMatrixShardError(
            "authorized experiment plan requires repository_dirty=false"
        )

    full_cells = tuple(parent_plan.cells())
    scoped_pairs = tuple(
        (global_index, cell)
        for global_index, cell in enumerate(full_cells)
        if cell.variant in normalized_scope
    )
    if not scoped_pairs:
        raise ValueError("execution scope selected no parent cells")
    if count > len(scoped_pairs):
        raise ValueError("shard_count must not exceed scoped cell count")

    parent_payload = _parent_plan_payload(parent_plan)
    parent_inventory = [
        _cell_payload(cell, global_index=index)
        for index, cell in enumerate(full_cells)
    ]
    parent_plan_sha256 = _digest_json(
        {"plan": parent_payload, "cells": parent_inventory}
    )
    scoped_cells: list[dict[str, Any]] = []
    shard_cells: list[list[dict[str, Any]]] = [[] for _ in range(count)]
    for scope_index, (global_index, cell) in enumerate(scoped_pairs):
        shard_index = scope_index % count
        record = {
            **_cell_payload(cell, global_index=global_index),
            "scope_index": scope_index,
            "shard_index": shard_index,
            "shard_sequence": len(shard_cells[shard_index]),
        }
        scoped_cells.append(record)
        shard_cells[shard_index].append(record)

    shards = []
    for shard_index, cells in enumerate(shard_cells):
        shards.append(
            {
                "shard_index": shard_index,
                "shard_id": _shard_id(shard_index, count),
                "cell_count": len(cells),
                "scope_indices": [int(cell["scope_index"]) for cell in cells],
                "global_indices": [int(cell["global_index"]) for cell in cells],
                "cell_ids": [str(cell["cell_id"]) for cell in cells],
                "cells_sha256": _digest_json(cells),
            }
        )

    timestamp = (
        _required_timestamp(created_at_utc)
        if created_at_utc is not None
        else datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    base_payload = base_config.to_dict()
    learning_binding = _build_learning_bundle_binding(
        normalized_scope,
        selected_bundles,
    )
    experiment_authorization = _load_plan_experiment_authorization(
        source_git_commit=commit,
        scope_variants=normalized_scope,
        scenarios=parent_plan.scenarios,
        scales=parent_plan.scales,
        seeds=parent_plan.seeds,
        duration_s=parent_plan.duration_s,
        learning_binding=learning_binding,
        bundles=selected_bundles,
        device=selected_device,
        authorization_path=experiment_authorization_path,
        expected_authorization_sha256=(
            expected_experiment_authorization_sha256
        ),
        revocation_registry_path=revocation_registry_path,
        now_utc=authorization_now_utc,
    )
    variant_preflight = _preflight_scope_variants(
        base_config,
        parent_plan,
        normalized_scope,
        selected_bundles,
        device=selected_device,
        experiment_authorization=experiment_authorization,
    )
    if (
        _build_learning_bundle_binding(
            normalized_scope,
            selected_bundles,
        )
        != learning_binding
    ):
        raise ExperimentMatrixShardError(
            "model bundle changed during execution plan preflight"
        )
    payload: dict[str, Any] = {
        "schema_version": (
            EXPERIMENT_MATRIX_AUTHORIZED_EXECUTION_PLAN_SCHEMA
            if experiment_authorization is not None
            else EXPERIMENT_MATRIX_EXECUTION_PLAN_SCHEMA
        ),
        "created_at_utc": timestamp,
        "source": {
            "git_commit": commit,
            "repository_dirty": dirty,
        },
        "parent": {
            "experiment_matrix_schema": EXPERIMENT_MATRIX_SCHEMA_VERSION,
            "formal": bool(parent_plan.formal),
            "plan": parent_payload,
            "plan_sha256": parent_plan_sha256,
            "full_cell_count": len(parent_inventory),
            "full_cells": parent_inventory,
        },
        "base_config": {
            "schema_version": base_payload["schema_version"],
            "payload": base_payload,
            "sha256": _digest_json(base_payload),
        },
        "learning_bundles": {
            **learning_binding,
            "preflight_device": selected_device,
            "variant_preflight": variant_preflight,
        },
        "scope": {
            "variants": list(normalized_scope),
            "cell_count": len(scoped_cells),
            "cells_sha256": _digest_json(scoped_cells),
            "cells": scoped_cells,
        },
        "sharding": {
            "strategy": "scope_index_modulo_v1",
            "shard_count": count,
            "shards": shards,
        },
        "evidence_class": (
            "formal_parent_scope"
            if parent_plan.formal
            else "development_parent_scope"
        ),
    }
    if experiment_authorization is not None:
        payload["experiment_authorization"] = (
            experiment_authorization.binding_payload()
        )
    payload["execution_plan_sha256"] = _digest_json(payload)

    destination.mkdir(parents=True)
    plan_path = destination / _EXECUTION_PLAN_FILENAME
    _write_json_atomic(plan_path, payload)
    _write_text_atomic(
        destination / _EXECUTION_PLAN_CHECKSUM_FILENAME,
        f"{_sha256_file(plan_path)}  {_EXECUTION_PLAN_FILENAME}\n",
    )
    if parent_plan.formal or experiment_authorization is not None:
        current_commit, current_dirty = repository_state(repository_root)
        if current_commit != commit or current_dirty:
            raise ExperimentMatrixShardError(
                "source state changed while formal or authorized execution "
                "plan was written"
            )
    return plan_path


def create_formal_r0_execution_plan(
    *,
    root: str | Path,
    output_root: str | Path,
    base_config: ScenarioConfig,
    parent_plan: ExperimentMatrixPlan,
    shard_count: int = FORMAL_R0_DEFAULT_SHARD_COUNT,
    created_at_utc: str | None = None,
) -> Path:
    """Freeze the 900-cell R0 scope of one complete formal parent matrix."""

    if not parent_plan.formal:
        raise ValueError("formal R0 execution requires parent_plan.formal=true")
    if set(parent_plan.variants) != set(EXPERIMENT_VARIANTS):
        raise ValueError("formal R0 parent must contain all experiment variants")
    if tuple(parent_plan.scenarios) != tuple(AVAILABLE_SCENARIOS):
        raise ValueError(
            "formal R0 parent scenarios must use the canonical scenario order"
        )
    path = create_experiment_matrix_execution_plan(
        root=root,
        output_root=output_root,
        base_config=base_config,
        parent_plan=parent_plan,
        scope_variants=("R0",),
        shard_count=shard_count,
        created_at_utc=created_at_utc,
    )
    payload = load_experiment_matrix_execution_plan(path)
    if int(payload["parent"]["full_cell_count"]) != FORMAL_PARENT_EXPECTED_CELL_COUNT:
        raise ExperimentMatrixShardError(
            "formal parent inventory is not the expected 5,700 cells"
        )
    if int(payload["scope"]["cell_count"]) != FORMAL_R0_EXPECTED_CELL_COUNT:
        raise ExperimentMatrixShardError(
            "formal R0 execution scope is not the expected 900 cells"
        )
    return path


def load_experiment_matrix_execution_plan(
    path: str | Path,
) -> dict[str, Any]:
    """Load and fully validate an execution plan and its parent inventory."""

    plan_path = Path(path).resolve()
    payload = _read_json_object(plan_path)
    schema_version = payload.get("schema_version")
    if schema_version not in {
        EXPERIMENT_MATRIX_EXECUTION_PLAN_SCHEMA,
        EXPERIMENT_MATRIX_AUTHORIZED_EXECUTION_PLAN_SCHEMA,
    }:
        raise ExperimentMatrixShardError("execution plan schema is unsupported")
    if (
        schema_version == EXPERIMENT_MATRIX_EXECUTION_PLAN_SCHEMA
        and "experiment_authorization" in payload
    ):
        raise ExperimentMatrixShardError(
            "legacy execution plan cannot contain experiment authorization"
        )
    if (
        schema_version == EXPERIMENT_MATRIX_AUTHORIZED_EXECUTION_PLAN_SCHEMA
        and "experiment_authorization" not in payload
    ):
        raise ExperimentMatrixShardError(
            "authorized execution plan is missing experiment authorization"
        )
    expected_digest = _required_sha256(
        payload.get("execution_plan_sha256"),
        "execution_plan_sha256",
    )
    unhashed = dict(payload)
    unhashed.pop("execution_plan_sha256", None)
    if _digest_json(unhashed) != expected_digest:
        raise ExperimentMatrixShardError("execution plan digest mismatch")

    parent = _required_mapping(payload.get("parent"), "parent")
    parent_plan_data = _required_mapping(parent.get("plan"), "parent.plan")
    parent_plan = _plan_from_payload(parent_plan_data)
    expected_cells = [
        _cell_payload(cell, global_index=index)
        for index, cell in enumerate(parent_plan.cells())
    ]
    actual_cells = parent.get("full_cells")
    if actual_cells != expected_cells:
        raise ExperimentMatrixShardError(
            "parent cell inventory does not match ExperimentMatrixPlan.cells()"
        )
    if int(parent.get("full_cell_count", -1)) != len(expected_cells):
        raise ExperimentMatrixShardError("parent full_cell_count mismatch")
    if _digest_json(
        {"plan": parent_plan_data, "cells": expected_cells}
    ) != _required_sha256(parent.get("plan_sha256"), "parent.plan_sha256"):
        raise ExperimentMatrixShardError("parent plan digest mismatch")
    if bool(parent.get("formal")) != parent_plan.formal:
        raise ExperimentMatrixShardError("parent formal flag mismatch")

    base = _required_mapping(payload.get("base_config"), "base_config")
    base_payload = _required_mapping(base.get("payload"), "base_config.payload")
    ScenarioConfig.from_dict(dict(base_payload))
    if _digest_json(base_payload) != _required_sha256(
        base.get("sha256"),
        "base_config.sha256",
    ):
        raise ExperimentMatrixShardError("base config digest mismatch")

    scope = _required_mapping(payload.get("scope"), "scope")
    scope_variants = tuple(str(value) for value in scope.get("variants", ()))
    if not scope_variants or not set(scope_variants).issubset(parent_plan.variants):
        raise ExperimentMatrixShardError("scope variants are invalid")
    expected_scope_pairs = [
        (index, cell)
        for index, cell in enumerate(parent_plan.cells())
        if cell.variant in scope_variants
    ]
    expected_scope: list[dict[str, Any]] = []
    shard_count = int(
        _required_mapping(payload.get("sharding"), "sharding").get(
            "shard_count",
            0,
        )
    )
    if shard_count <= 0:
        raise ExperimentMatrixShardError("shard_count must be positive")
    for scope_index, (global_index, cell) in enumerate(expected_scope_pairs):
        expected_scope.append(
            {
                **_cell_payload(cell, global_index=global_index),
                "scope_index": scope_index,
                "shard_index": scope_index % shard_count,
                "shard_sequence": scope_index // shard_count,
            }
        )
    if scope.get("cells") != expected_scope:
        raise ExperimentMatrixShardError("scope cell inventory mismatch")
    if int(scope.get("cell_count", -1)) != len(expected_scope):
        raise ExperimentMatrixShardError("scope cell_count mismatch")
    if _digest_json(expected_scope) != _required_sha256(
        scope.get("cells_sha256"),
        "scope.cells_sha256",
    ):
        raise ExperimentMatrixShardError("scope cell digest mismatch")

    sharding = _required_mapping(payload.get("sharding"), "sharding")
    if sharding.get("strategy") != "scope_index_modulo_v1":
        raise ExperimentMatrixShardError("unsupported shard strategy")
    expected_shards = []
    for shard_index in range(shard_count):
        cells = [
            item
            for item in expected_scope
            if int(item["shard_index"]) == shard_index
        ]
        expected_shards.append(
            {
                "shard_index": shard_index,
                "shard_id": _shard_id(shard_index, shard_count),
                "cell_count": len(cells),
                "scope_indices": [int(cell["scope_index"]) for cell in cells],
                "global_indices": [int(cell["global_index"]) for cell in cells],
                "cell_ids": [str(cell["cell_id"]) for cell in cells],
                "cells_sha256": _digest_json(cells),
            }
        )
    if sharding.get("shards") != expected_shards:
        raise ExperimentMatrixShardError("shard inventory mismatch")
    _validate_learning_bundle_plan(payload, scope_variants)
    _validate_execution_authorization_binding(payload, parent_plan)
    return payload


def run_experiment_matrix_shard(
    *,
    root: str | Path,
    execution_plan_path: str | Path,
    shard_index: int,
    resume: bool = False,
    max_new_cells: int | None = None,
    device: str = "cpu",
    minimum_free_bytes: int = 0,
    bundles: ModelBundlePaths | None = None,
    experiment_authorization_path: str | Path | None = None,
    revocation_registry_path: str | Path | None = None,
    authorization_now_utc: datetime | str | None = None,
) -> dict[str, Any]:
    """Run or resume one deterministic shard at complete-cell boundaries."""

    repository_root = Path(root).resolve()
    plan_path = Path(execution_plan_path).resolve()
    execution = load_experiment_matrix_execution_plan(plan_path)
    _validate_source_state(repository_root, execution)
    selected_bundles = bundles or ModelBundlePaths()
    _validate_runtime_learning_bundles(
        execution,
        selected_bundles,
        device=device,
    )
    experiment_authorization = _load_runtime_experiment_authorization(
        execution,
        authorization_path=experiment_authorization_path,
        revocation_registry_path=revocation_registry_path,
        now_utc=authorization_now_utc,
    )
    index = int(shard_index)
    descriptors = execution["sharding"]["shards"]
    if index < 0 or index >= len(descriptors):
        raise ValueError("shard_index is out of range")
    if max_new_cells is not None and int(max_new_cells) <= 0:
        raise ValueError("max_new_cells must be positive when provided")
    limit = None if max_new_cells is None else int(max_new_cells)
    free_floor = int(minimum_free_bytes)
    if free_floor < 0:
        raise ValueError("minimum_free_bytes must be non-negative")

    execution_root = plan_path.parent
    descriptor = descriptors[index]
    shard_dir = execution_root / "shards" / str(descriptor["shard_id"])
    expected_cells = [
        cell
        for cell in execution["scope"]["cells"]
        if int(cell["shard_index"]) == index
    ]
    if resume:
        if not shard_dir.is_dir():
            raise FileNotFoundError(
                f"resume shard directory does not exist: {shard_dir}"
            )
        _validate_static_shard_plan(
            shard_dir,
            execution=execution,
            descriptor=descriptor,
            expected_cells=expected_cells,
        )
    else:
        if shard_dir.exists():
            raise FileExistsError(
                f"shard output already exists; use resume: {shard_dir}"
            )
        _initialize_shard(
            shard_dir,
            execution=execution,
            descriptor=descriptor,
            expected_cells=expected_cells,
        )

    progress_path = shard_dir / _SHARD_PROGRESS_FILENAME
    progress = _load_and_validate_progress(
        execution_root,
        shard_dir,
        execution,
        expected_cells,
    )
    checkpoint_path = shard_dir / _SHARD_CHECKPOINT_FILENAME
    checkpoint = _load_checkpoint(checkpoint_path)
    _validate_checkpoint_binding(
        checkpoint,
        execution=execution,
        descriptor=descriptor,
    )
    resume_count = int(checkpoint.get("resume_count", 0))
    checkpoint_count = int(checkpoint.get("completed_cell_count", -1))
    if checkpoint_count > len(progress):
        raise ExperimentMatrixShardError(
            "checkpoint is ahead of validated progress"
        )
    if checkpoint.get("progress_sha256") != _progress_prefix_sha256(
        progress_path,
        checkpoint_count,
    ):
        raise ExperimentMatrixShardError(
            "checkpoint progress digest does not match its validated prefix"
        )
    recovered_checkpoint_rows = len(progress) - checkpoint_count
    if resume:
        resume_count += 1
    _write_checkpoint(
        checkpoint_path,
        execution=execution,
        descriptor=descriptor,
        progress_path=progress_path,
        completed_cell_count=len(progress),
        status=(
            "complete"
            if len(progress) == len(expected_cells)
            else "running"
        ),
        resume_count=resume_count,
        recovered_checkpoint_row_count=(
            int(checkpoint.get("recovered_checkpoint_row_count", 0))
            + recovered_checkpoint_rows
        ),
    )

    new_cell_count = 0
    orphan_recovered_count = 0
    pause_reason: str | None = None
    while len(progress) < len(expected_cells):
        if limit is not None and new_cell_count >= limit:
            pause_reason = "max_new_cells_reached"
            break
        cell = expected_cells[len(progress)]
        final_dir = _cell_container_path(shard_dir, cell)
        if final_dir.exists():
            row = _progress_row_from_completed_cell(
                execution_root,
                final_dir,
                execution,
                cell,
                sequence=len(progress),
            )
            _append_jsonl_fsync(progress_path, row)
            progress.append(row)
            orphan_recovered_count += 1
        else:
            available = shutil.disk_usage(execution_root).free
            if available < free_floor:
                pause_reason = "minimum_free_space_reached"
                break
            _validate_source_state(repository_root, execution)
            if execution.get("experiment_authorization") is not None:
                experiment_authorization = (
                    _load_runtime_experiment_authorization(
                        execution,
                        authorization_path=experiment_authorization_path,
                        revocation_registry_path=revocation_registry_path,
                        now_utc=authorization_now_utc,
                    )
                )
            row = _run_one_cell(
                repository_root=repository_root,
                execution_root=execution_root,
                shard_dir=shard_dir,
                execution=execution,
                cell=cell,
                sequence=len(progress),
                device=device,
                bundles=selected_bundles,
                experiment_authorization=experiment_authorization,
                authorization_now_utc=authorization_now_utc,
            )
            _append_jsonl_fsync(progress_path, row)
            progress.append(row)
            new_cell_count += 1
        _write_checkpoint(
            checkpoint_path,
            execution=execution,
            descriptor=descriptor,
            progress_path=progress_path,
            completed_cell_count=len(progress),
            status=(
                "complete"
                if len(progress) == len(expected_cells)
                else "running"
            ),
            resume_count=resume_count,
            recovered_checkpoint_row_count=(
                int(checkpoint.get("recovered_checkpoint_row_count", 0))
                + recovered_checkpoint_rows
            ),
        )

    status = "complete" if len(progress) == len(expected_cells) else "paused"
    _write_checkpoint(
        checkpoint_path,
        execution=execution,
        descriptor=descriptor,
        progress_path=progress_path,
        completed_cell_count=len(progress),
        status=status,
        resume_count=resume_count,
        recovered_checkpoint_row_count=(
            int(checkpoint.get("recovered_checkpoint_row_count", 0))
            + recovered_checkpoint_rows
        ),
    )
    return {
        "status": status,
        "shard_index": index,
        "shard_id": descriptor["shard_id"],
        "expected_cell_count": len(expected_cells),
        "completed_cell_count": len(progress),
        "new_cell_count": new_cell_count,
        "orphan_recovered_count": orphan_recovered_count,
        "resume_count": resume_count,
        "pause_reason": pause_reason,
        "minimum_free_bytes": free_floor,
        "available_free_bytes": shutil.disk_usage(execution_root).free,
        "shard_dir": shard_dir,
        "checkpoint": checkpoint_path,
        "progress": progress_path,
    }


def validate_experiment_matrix_shard_for_storage(
    *,
    execution_plan_path: str | Path,
    shard_index: int,
) -> dict[str, Any]:
    """Prove that one canonical shard is complete and archive-ready.

    This performs the same static-plan, progress, cell-artifact, and
    checkpoint validation required by the merge path.  It intentionally does
    not validate the current Git checkout because archival may occur from a
    separate control process after the clean execution has finished.
    """

    plan_path = Path(execution_plan_path).resolve()
    execution = load_experiment_matrix_execution_plan(plan_path)
    descriptors = execution["sharding"]["shards"]
    index = int(shard_index)
    if index < 0 or index >= len(descriptors):
        raise ValueError("shard_index is out of range")

    descriptor = descriptors[index]
    execution_root = plan_path.parent
    shard_dir = execution_root / "shards" / str(descriptor["shard_id"])
    expected_cells = [
        cell
        for cell in execution["scope"]["cells"]
        if int(cell["shard_index"]) == index
    ]
    _validate_static_shard_plan(
        shard_dir,
        execution=execution,
        descriptor=descriptor,
        expected_cells=expected_cells,
    )
    progress = _load_and_validate_progress(
        execution_root,
        shard_dir,
        execution,
        expected_cells,
    )
    checkpoint_path = shard_dir / _SHARD_CHECKPOINT_FILENAME
    checkpoint = _load_checkpoint(checkpoint_path)
    _validate_checkpoint_binding(
        checkpoint,
        execution=execution,
        descriptor=descriptor,
    )
    if checkpoint.get("status") != "complete":
        raise ExperimentMatrixShardError(
            f"shard is not complete: {descriptor['shard_id']}"
        )
    if len(progress) != len(expected_cells):
        raise ExperimentMatrixShardError(
            f"shard progress is incomplete: {descriptor['shard_id']}"
        )
    if int(checkpoint.get("completed_cell_count", -1)) != len(
        expected_cells
    ):
        raise ExperimentMatrixShardError(
            f"shard completion count mismatch: {descriptor['shard_id']}"
        )
    progress_path = shard_dir / _SHARD_PROGRESS_FILENAME
    progress_sha256 = _sha256_file(progress_path)
    if checkpoint.get("progress_sha256") != progress_sha256:
        raise ExperimentMatrixShardError(
            f"shard progress digest mismatch: {descriptor['shard_id']}"
        )

    return {
        "schema_version": (
            EXPERIMENT_MATRIX_SHARD_STORAGE_VALIDATION_SCHEMA
        ),
        "status": "verified_complete",
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "execution_plan_file_sha256": _sha256_file(plan_path),
        "parent_plan_sha256": execution["parent"]["plan_sha256"],
        "source_git_commit": execution["source"]["git_commit"],
        "shard_index": index,
        "shard_id": descriptor["shard_id"],
        "expected_cell_count": len(expected_cells),
        "completed_cell_count": len(progress),
        "descriptor_sha256": _digest_json(descriptor),
        "cells_sha256": _digest_json(expected_cells),
        "shard_plan_sha256": _sha256_file(
            shard_dir / _SHARD_PLAN_FILENAME
        ),
        "progress_sha256": progress_sha256,
        "checkpoint_sha256": _sha256_file(checkpoint_path),
        "shard_dir": shard_dir,
    }


def collect_experiment_matrix_shard_merge_fragment(
    *,
    execution_plan_path: str | Path,
    shard_index: int,
    execution_root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate one complete shard and return its deterministic merge data.

    ``execution_root`` may point at a temporary archive restoration.  Paths
    inside the shard remain bound to the canonical relative layout from the
    execution plan, so a staged root must contain ``shards/<shard_id>``.
    """

    plan_path = Path(execution_plan_path).resolve()
    execution = load_experiment_matrix_execution_plan(plan_path)
    descriptors = execution["sharding"]["shards"]
    index = int(shard_index)
    if index < 0 or index >= len(descriptors):
        raise ValueError("shard_index is out of range")
    selected_root = (
        Path(execution_root).resolve()
        if execution_root is not None
        else plan_path.parent
    )
    return _collect_experiment_matrix_shard_merge_fragment(
        selected_root,
        execution,
        descriptors[index],
    )


def validate_experiment_matrix_execution_source(
    *,
    root: str | Path,
    execution_plan_path: str | Path,
) -> dict[str, Any]:
    """Validate the checkout used to merge one frozen execution plan."""

    execution = load_experiment_matrix_execution_plan(execution_plan_path)
    _validate_source_state(Path(root).resolve(), execution)
    return execution


def _collect_experiment_matrix_shard_merge_fragment(
    execution_root: Path,
    execution: Mapping[str, Any],
    descriptor: Mapping[str, Any],
) -> dict[str, Any]:
    index = int(descriptor["shard_index"])
    shard_dir = (
        execution_root / "shards" / str(descriptor["shard_id"])
    )
    expected_cells = [
        cell
        for cell in execution["scope"]["cells"]
        if int(cell["shard_index"]) == index
    ]
    _validate_static_shard_plan(
        shard_dir,
        execution=execution,
        descriptor=descriptor,
        expected_cells=expected_cells,
    )
    progress = _load_and_validate_progress(
        execution_root,
        shard_dir,
        execution,
        expected_cells,
    )
    checkpoint_path = shard_dir / _SHARD_CHECKPOINT_FILENAME
    checkpoint = _load_checkpoint(checkpoint_path)
    _validate_checkpoint_binding(
        checkpoint,
        execution=execution,
        descriptor=descriptor,
    )
    if checkpoint.get("status") != "complete":
        raise ExperimentMatrixShardError(
            f"shard is not complete: {descriptor['shard_id']}"
        )
    if len(progress) != len(expected_cells):
        raise ExperimentMatrixShardError(
            f"shard progress is incomplete: {descriptor['shard_id']}"
        )
    if int(checkpoint.get("completed_cell_count", -1)) != len(
        expected_cells
    ):
        raise ExperimentMatrixShardError(
            f"shard completion count mismatch: {descriptor['shard_id']}"
        )
    progress_path = shard_dir / _SHARD_PROGRESS_FILENAME
    if checkpoint.get("progress_sha256") != _sha256_file(progress_path):
        raise ExperimentMatrixShardError(
            f"shard progress digest mismatch: {descriptor['shard_id']}"
        )
    merged_rows = [_merged_cell_row(execution_root, row) for row in progress]
    return {
        "schema_version": EXPERIMENT_MATRIX_SHARD_MERGE_FRAGMENT_SCHEMA,
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "shard_index": index,
        "shard_id": descriptor["shard_id"],
        "progress": progress,
        "merged_rows": merged_rows,
        "episode_relative_paths": [
            row["episode_relative_path"] for row in merged_rows
        ],
        "shard_digest": {
            "shard_index": index,
            "shard_id": descriptor["shard_id"],
            "cell_count": len(progress),
            "shard_plan_sha256": _sha256_file(
                shard_dir / _SHARD_PLAN_FILENAME
            ),
            "progress_sha256": _sha256_file(progress_path),
            "checkpoint_sha256": _sha256_file(checkpoint_path),
        },
    }


def merge_experiment_matrix_shards(
    *,
    root: str | Path,
    execution_plan_path: str | Path,
    output_dir: str | Path | None = None,
    write_d6_report: bool = False,
) -> dict[str, Path]:
    """Validate and deterministically merge every shard in one scope.

    A complete R0 scope remains a partial formal matrix.  The function does
    not create the legacy ``experiment_matrix_manifest.json`` unless the scope
    exactly equals the complete parent inventory, preventing R0 evidence from
    being mislabeled as a 5,700-cell formal result.
    """

    repository_root = Path(root).resolve()
    plan_path = Path(execution_plan_path).resolve()
    execution = load_experiment_matrix_execution_plan(plan_path)
    _validate_source_state(repository_root, execution)
    execution_root = plan_path.parent
    expected_scope = list(execution["scope"]["cells"])
    fragments: list[dict[str, Any]] = []
    for descriptor in execution["sharding"]["shards"]:
        fragments.append(
            _collect_experiment_matrix_shard_merge_fragment(
                execution_root,
                execution,
                descriptor,
            )
        )
    all_progress = [
        row for fragment in fragments for row in fragment["progress"]
    ]
    shard_digests = [fragment["shard_digest"] for fragment in fragments]

    ordered = sorted(all_progress, key=lambda row: int(row["scope_index"]))
    if [row["cell_id"] for row in ordered] != [
        cell["cell_id"] for cell in expected_scope
    ]:
        raise ExperimentMatrixShardError(
            "merged shard cells are missing, duplicated, or out of scope"
        )
    if len({row["cell_id"] for row in ordered}) != len(expected_scope):
        raise ExperimentMatrixShardError("merged shard contains duplicate cells")

    destination = (
        Path(output_dir).resolve()
        if output_dir is not None
        else execution_root / "merged_scope"
    )
    if destination.exists():
        raise FileExistsError(f"merge output already exists: {destination}")
    destination.mkdir(parents=True)

    parent_count = int(execution["parent"]["full_cell_count"])
    scope_count = int(execution["scope"]["cell_count"])
    parent_formal = bool(execution["parent"]["formal"])
    full_matrix_complete = scope_count == parent_count
    manifest = {
        "schema_version": EXPERIMENT_MATRIX_SCOPE_MERGE_SCHEMA,
        "source_git_commit": execution["source"]["git_commit"],
        "source_repository_dirty": execution["source"][
            "repository_dirty"
        ],
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "parent_plan_sha256": execution["parent"]["plan_sha256"],
        "parent_formal": parent_formal,
        "parent_full_cell_count": parent_count,
        "scope_variants": list(execution["scope"]["variants"]),
        "scope_expected_cell_count": scope_count,
        "scope_completed_cell_count": len(ordered),
        "scope_complete": len(ordered) == scope_count,
        "formal_scope_complete": parent_formal and len(ordered) == scope_count,
        "full_matrix_complete": full_matrix_complete,
        "formal_matrix_complete": parent_formal and full_matrix_complete,
        "legacy_full_matrix_manifest_written": full_matrix_complete,
        "shard_strategy": execution["sharding"]["strategy"],
        "shard_count": execution["sharding"]["shard_count"],
        "shards": shard_digests,
        "paired_random_schedule_version": (
            PAIRED_SENSOR_RANDOM_SCHEDULE_VERSION
        ),
        "status": (
            "formal_matrix_complete"
            if parent_formal and full_matrix_complete
            else (
                "formal_scope_complete"
                if parent_formal
                else "development_scope_complete"
            )
        ),
    }
    manifest_path = destination / "experiment_matrix_scope_manifest.json"
    cells_path = destination / "experiment_matrix_scope_cells.csv"
    episode_dirs_path = destination / "episode_dirs.json"
    _write_json_atomic(manifest_path, manifest)
    rows = sorted(
        [row for fragment in fragments for row in fragment["merged_rows"]],
        key=lambda row: int(row["scope_index"]),
    )
    _write_rows_atomic(cells_path, rows)
    episode_relative_paths = [
        row["episode_relative_path"] for row in rows
    ]
    _write_json_atomic(
        episode_dirs_path,
        {
            "schema_version": EXPERIMENT_MATRIX_SCOPE_MERGE_SCHEMA,
            "execution_plan_sha256": execution["execution_plan_sha256"],
            "episode_count": len(episode_relative_paths),
            "paths_relative_to_execution_root": episode_relative_paths,
        },
    )
    paths: dict[str, Path] = {
        "manifest": manifest_path,
        "cells": cells_path,
        "episode_dirs": episode_dirs_path,
    }
    if full_matrix_complete:
        legacy = {
            "schema_version": EXPERIMENT_MATRIX_SCHEMA_VERSION,
            "git_commit": execution["source"]["git_commit"],
            "repository_dirty": execution["source"]["repository_dirty"],
            "formal": parent_formal,
            "variants": execution["parent"]["plan"]["variants"],
            "scenarios": execution["parent"]["plan"]["scenarios"],
            "scales": execution["parent"]["plan"]["scales"],
            "seeds": execution["parent"]["plan"]["seeds"],
            "training_seed_registry_present": (
                execution["parent"]["plan"]["training_seeds"] is not None
            ),
            "cell_count": parent_count,
            "completed_cell_count": len(ordered),
            "paired_random_schedule_version": (
                PAIRED_SENSOR_RANDOM_SCHEDULE_VERSION
            ),
            "resumable_execution_plan_sha256": execution[
                "execution_plan_sha256"
            ],
        }
        legacy_path = destination / "experiment_matrix_manifest.json"
        _write_json_atomic(legacy_path, legacy)
        paths["legacy_full_manifest"] = legacy_path

    checksum_path = destination / "SHA256SUMS"
    checksum_lines = [
        f"{_sha256_file(path)}  {path.name}"
        for path in sorted(paths.values(), key=lambda item: item.name)
    ]
    _write_text_atomic(checksum_path, "\n".join(checksum_lines) + "\n")
    paths["checksums"] = checksum_path

    if write_d6_report:
        from research_modules.d6_evaluation_metrics.d6_evaluation_metrics.scalable_3d_offline import (
            Scalable3DOfflineEvaluationInputs,
            Scalable3DOfflineReportGenerator,
        )

        episode_dirs = tuple(
            (execution_root / relative).resolve()
            for relative in episode_relative_paths
        )
        report_paths = Scalable3DOfflineReportGenerator().write_report_bundle(
            destination / "d6_evaluation",
            inputs=Scalable3DOfflineEvaluationInputs(
                episode_dirs=episode_dirs
            ),
        )
        paths.update(
            {f"d6_{name}": path for name, path in report_paths.items()}
        )
    return paths


def _run_one_cell(
    *,
    repository_root: Path,
    execution_root: Path,
    shard_dir: Path,
    execution: Mapping[str, Any],
    cell: Mapping[str, Any],
    sequence: int,
    device: str,
    bundles: ModelBundlePaths,
    experiment_authorization: G1ShadowExperimentAuthorization | None,
    authorization_now_utc: datetime | str | None,
) -> dict[str, Any]:
    if experiment_authorization is not None:
        experiment_authorization.assert_cell(
            variant=str(cell["variant"]),
            scenario=str(cell["scenario"]),
            scale=int(cell["scale"]),
            seed=int(cell["seed"]),
            duration_s=float(execution["parent"]["plan"]["duration_s"]),
            now_utc=authorization_now_utc,
        )
    if cell["variant"] != "R0":
        _validate_runtime_learning_bundles(
            execution,
            bundles,
            device=device,
        )
    final_dir = _cell_container_path(shard_dir, cell)
    inflight_root = shard_dir / "inflight"
    inflight_root.mkdir(exist_ok=True)
    partial_dir = inflight_root / f"{cell['cell_id']}.partial"
    if partial_dir.exists():
        marker_path = partial_dir / "inflight_marker.json"
        marker = _read_json_object(marker_path)
        if (
            marker.get("execution_plan_sha256")
            != execution["execution_plan_sha256"]
            or marker.get("cell_id") != cell["cell_id"]
        ):
            raise ExperimentMatrixShardError(
                f"conflicting partial cell output: {partial_dir}"
            )
        shutil.rmtree(partial_dir)
    partial_dir.mkdir()
    _write_json_atomic(
        partial_dir / "inflight_marker.json",
        {
            "schema_version": EXPERIMENT_MATRIX_CELL_RESULT_SCHEMA,
            "execution_plan_sha256": execution["execution_plan_sha256"],
            "cell_id": cell["cell_id"],
            "sequence": sequence,
        },
    )
    try:
        common = {
            "repository_root": repository_root,
            "execution_root": execution_root,
            "execution": execution,
            "cell": cell,
            "cell_container": partial_dir,
            "final_container": final_dir,
            "device": device,
        }
        if cell["variant"] == "R0":
            record = _execute_r0_cell(**common)
        else:
            learning_arguments: dict[str, Any] = {"bundles": bundles}
            if experiment_authorization is not None:
                learning_arguments["experiment_authorization"] = (
                    experiment_authorization
                )
            record = _execute_learning_cell(**common, **learning_arguments)
            _validate_runtime_learning_bundles(
                execution,
                bundles,
                device=device,
            )
        (partial_dir / "inflight_marker.json").unlink()
        _write_json_atomic(partial_dir / _CELL_RESULT_FILENAME, record)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        partial_dir.replace(final_dir)
        _validate_cell_container(
            execution_root,
            final_dir,
            execution,
            cell,
        )
    except Exception:
        # Keep the marked partial directory for a strict, auditable resume.
        raise
    return _progress_row_from_completed_cell(
        execution_root,
        final_dir,
        execution,
        cell,
        sequence=sequence,
    )


def _execute_r0_cell(
    *,
    repository_root: Path,
    execution_root: Path,
    execution: Mapping[str, Any],
    cell: Mapping[str, Any],
    cell_container: Path,
    final_container: Path,
    device: str,
) -> dict[str, Any]:
    """Execute one R0 cell. Kept separate for deterministic unit fakes."""

    if cell["variant"] != "R0":
        raise ExperimentMatrixShardError("R0 shard received a non-R0 cell")
    return _execute_matrix_cell(
        repository_root=repository_root,
        execution_root=execution_root,
        execution=execution,
        cell=cell,
        cell_container=cell_container,
        final_container=final_container,
        device=device,
        bundles=ModelBundlePaths(),
    )


def _execute_learning_cell(
    *,
    repository_root: Path,
    execution_root: Path,
    execution: Mapping[str, Any],
    cell: Mapping[str, Any],
    cell_container: Path,
    final_container: Path,
    device: str,
    bundles: ModelBundlePaths,
    experiment_authorization: G1ShadowExperimentAuthorization | None = None,
) -> dict[str, Any]:
    """Execute one declared learning cell after bundle binding validation."""

    if cell["variant"] == "R0":
        raise ExperimentMatrixShardError(
            "learning executor received an R0 cell"
        )
    return _execute_matrix_cell(
        repository_root=repository_root,
        execution_root=execution_root,
        execution=execution,
        cell=cell,
        cell_container=cell_container,
        final_container=final_container,
        device=device,
        bundles=bundles,
        experiment_authorization=experiment_authorization,
    )


def _execute_matrix_cell(
    *,
    repository_root: Path,
    execution_root: Path,
    execution: Mapping[str, Any],
    cell: Mapping[str, Any],
    cell_container: Path,
    final_container: Path,
    device: str,
    bundles: ModelBundlePaths,
    experiment_authorization: G1ShadowExperimentAuthorization | None = None,
) -> dict[str, Any]:
    """Execute one cell without allowing undeclared model fallback."""

    variant = str(cell["variant"])
    parent_plan = _plan_from_payload(execution["parent"]["plan"])
    base_config = ScenarioConfig.from_dict(
        dict(execution["base_config"]["payload"])
    )
    config = make_curriculum_scenario(
        str(cell["scenario"]),
        scale=int(cell["scale"]),
        seed=int(cell["seed"]),
        duration_s=parent_plan.duration_s,
        base=base_config,
    )
    config = _prepare_cell_config(config, execution, cell)
    options = runtime_options_for_variant(
        variant,
        bundles,
        device=device,
        d5_g1_shadow_authorization=experiment_authorization,
    )
    resolved = resolve_learning_runtime(
        config,
        options,
        stack_config=IntegratedStackConfig(),
    )
    _validate_resolved_variant(
        variant,
        resolved.diagnostics,
        allow_rule_fallback=parent_plan.allow_rule_fallback,
    )
    episode_dir = cell_container / "episode"
    result = run_episode(
        resolved.config,
        output_dir=episode_dir,
        module_stack=resolved.stack,
    )
    if result.manifest.git_commit != execution["source"]["git_commit"]:
        raise ExperimentMatrixShardError(
            "episode source commit differs from execution plan"
        )
    if (
        bool(
            execution["parent"]["formal"]
            or experiment_authorization is not None
        )
        and bool(result.manifest.repository_dirty)
    ):
        raise ExperimentMatrixShardError(
            "formal or authorized shard episode reports "
            "repository_dirty=true"
        )
    summary = result.summary
    if not bool(summary.get("finite_state")):
        raise ExperimentMatrixShardError("episode finite_state is false")
    if int(summary.get("online_truth_use_count", -1)) != 0:
        raise ExperimentMatrixShardError(
            "episode online_truth_use_count is non-zero"
        )
    artifact_tree = _tree_digest(episode_dir)
    record = {
        "schema_version": EXPERIMENT_MATRIX_CELL_RESULT_SCHEMA,
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "parent_plan_sha256": execution["parent"]["plan_sha256"],
        "source_git_commit": execution["source"]["git_commit"],
        "cell": dict(cell),
        "episode_relative_path": _relative_path(
            final_container / "episode",
            execution_root,
        ),
        "episode_id": result.manifest.episode_id,
        "paired_exogenous_config_sha256": (
            paired_exogenous_config_sha256(resolved.config)
        ),
        "sensor_random_schedule_version": (
            resolved.config.sensor_random_schedule_version
        ),
        "artifact_tree_sha256": artifact_tree,
        "metrics": {
            "finite_state": True,
            "online_truth_use_count": 0,
            "real_time_factor": float(summary["real_time_factor"]),
            "intercepted_target_count": int(
                summary["intercepted_target_count"]
            ),
        },
        "status": "complete",
    }
    if variant != "R0":
        module_diagnostics = _required_mapping(
            summary.get("module_final_diagnostics"),
            "summary.module_final_diagnostics",
        )
        record["learning_runtime"] = {
            "bundle_binding_sha256": execution["learning_bundles"][
                "binding_sha256"
            ],
            "diagnostics_sha256": _digest_json(resolved.diagnostics),
            "resolved_versions": {
                "d3_policy_version": resolved.config.d3_policy_version,
                "d4_policy_version": resolved.config.d4_policy_version,
                "d5_model_version": resolved.config.d5_model_version,
                "d5_active_vision_policy_version": (
                    resolved.config.d5_active_vision_policy_version
                ),
            },
            "experiment_authorization_sha256": (
                None
                if experiment_authorization is None
                else experiment_authorization.authorization_file_sha256
            ),
            "d5_g1_shadow_scoring_frame_count": int(
                module_diagnostics.get(
                    "d5_g1_shadow_scoring_frame_count",
                    0,
                )
            ),
            "d5_g1_shadow_scoring_success_count": int(
                module_diagnostics.get(
                    "d5_g1_shadow_scoring_success_count",
                    0,
                )
            ),
            "d5_g1_shadow_scoring_rejected_count": int(
                module_diagnostics.get(
                    "d5_g1_shadow_scoring_rejected_count",
                    0,
                )
            ),
            "d5_g1_shadow_model_output_applied": bool(
                module_diagnostics.get(
                    "d5_g1_shadow_model_output_applied",
                    False,
                )
            ),
        }
    return record


def _prepare_cell_config(
    config: ScenarioConfig,
    execution: Mapping[str, Any],
    cell: Mapping[str, Any],
) -> ScenarioConfig:
    from dataclasses import replace

    config = replace(
        config,
        sensor_random_schedule_version=(
            PAIRED_SENSOR_RANDOM_SCHEDULE_VERSION
        ),
    )
    pairing_hash = paired_exogenous_config_sha256(config)
    metadata = dict(config.metadata)
    metadata.update(
        {
            "experiment_matrix_schema": EXPERIMENT_MATRIX_SCHEMA_VERSION,
            "algorithm_variant": cell["variant"],
            "comparison_key": cell["comparison_key"],
            "paired_exogenous_config_sha256": pairing_hash,
            "full_system_validation": cell["variant"] == "F1",
            "matrix_execution_plan_sha256": execution[
                "execution_plan_sha256"
            ],
            "matrix_parent_plan_sha256": execution["parent"][
                "plan_sha256"
            ],
            "matrix_scope_index": int(cell["scope_index"]),
            "matrix_global_index": int(cell["global_index"]),
            "matrix_shard_index": int(cell["shard_index"]),
        }
    )
    return replace(config, metadata=metadata)


def _initialize_shard(
    shard_dir: Path,
    *,
    execution: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    expected_cells: Sequence[Mapping[str, Any]],
) -> None:
    shard_dir.mkdir(parents=True)
    static = {
        "schema_version": EXPERIMENT_MATRIX_SHARD_PLAN_SCHEMA,
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "source_git_commit": execution["source"]["git_commit"],
        "parent_plan_sha256": execution["parent"]["plan_sha256"],
        "descriptor": dict(descriptor),
        "cells": [dict(cell) for cell in expected_cells],
        "cells_sha256": _digest_json(expected_cells),
    }
    _write_json_atomic(shard_dir / _SHARD_PLAN_FILENAME, static)
    _write_text_atomic(shard_dir / _SHARD_PROGRESS_FILENAME, "")
    _write_checkpoint(
        shard_dir / _SHARD_CHECKPOINT_FILENAME,
        execution=execution,
        descriptor=descriptor,
        progress_path=shard_dir / _SHARD_PROGRESS_FILENAME,
        completed_cell_count=0,
        status="initialized",
        resume_count=0,
        recovered_checkpoint_row_count=0,
    )


def _validate_static_shard_plan(
    shard_dir: Path,
    *,
    execution: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    expected_cells: Sequence[Mapping[str, Any]],
) -> None:
    static = _read_json_object(shard_dir / _SHARD_PLAN_FILENAME)
    expected = {
        "schema_version": EXPERIMENT_MATRIX_SHARD_PLAN_SCHEMA,
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "source_git_commit": execution["source"]["git_commit"],
        "parent_plan_sha256": execution["parent"]["plan_sha256"],
        "descriptor": dict(descriptor),
        "cells": [dict(cell) for cell in expected_cells],
        "cells_sha256": _digest_json(expected_cells),
    }
    if static != expected:
        raise ExperimentMatrixShardError(
            f"stored shard plan does not match execution plan: {shard_dir}"
        )


def _load_and_validate_progress(
    execution_root: Path,
    shard_dir: Path,
    execution: Mapping[str, Any],
    expected_cells: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    path = shard_dir / _SHARD_PROGRESS_FILENAME
    if not path.is_file():
        raise ExperimentMatrixShardError(f"shard progress is missing: {path}")
    progress_text = path.read_text(encoding="utf-8")
    if progress_text and not progress_text.endswith("\n"):
        raise ExperimentMatrixShardError(
            "shard progress does not end at a complete JSONL record"
        )
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(
        progress_text.splitlines(),
        start=1,
    ):
        if not raw.strip():
            raise ExperimentMatrixShardError(
                f"blank shard progress line: {line_number}"
            )
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ExperimentMatrixShardError(
                f"invalid shard progress JSON at line {line_number}"
            ) from exc
        if not isinstance(row, dict):
            raise ExperimentMatrixShardError("shard progress row must be an object")
        sequence = len(rows)
        if sequence >= len(expected_cells):
            raise ExperimentMatrixShardError(
                "shard progress contains excess rows"
            )
        expected = expected_cells[sequence]
        if row.get("schema_version") != EXPERIMENT_MATRIX_SHARD_PROGRESS_SCHEMA:
            raise ExperimentMatrixShardError("shard progress schema mismatch")
        if int(row.get("sequence", -1)) != sequence:
            raise ExperimentMatrixShardError(
                "shard progress sequence is not contiguous"
            )
        for name in (
            "cell_id",
            "global_index",
            "scope_index",
            "shard_index",
            "shard_sequence",
        ):
            if row.get(name) != expected.get(name):
                raise ExperimentMatrixShardError(
                    f"shard progress cell mismatch: {name}"
                )
        if (
            row.get("execution_plan_sha256")
            != execution["execution_plan_sha256"]
        ):
            raise ExperimentMatrixShardError(
                "shard progress execution plan mismatch"
            )
        result_path = _resolve_relative(
            execution_root,
            row.get("cell_result_relative_path"),
        )
        expected_result_path = (
            _cell_container_path(shard_dir, expected)
            / _CELL_RESULT_FILENAME
        ).resolve()
        if result_path != expected_result_path:
            raise ExperimentMatrixShardError(
                "cell result path does not match its deterministic shard path"
            )
        if _sha256_file(result_path) != _required_sha256(
            row.get("cell_result_sha256"),
            "cell_result_sha256",
        ):
            raise ExperimentMatrixShardError("cell result digest mismatch")
        _validate_cell_container(
            execution_root,
            result_path.parent,
            execution,
            expected,
        )
        rows.append(row)
    return rows


def _progress_row_from_completed_cell(
    execution_root: Path,
    final_dir: Path,
    execution: Mapping[str, Any],
    cell: Mapping[str, Any],
    *,
    sequence: int,
) -> dict[str, Any]:
    record = _validate_cell_container(
        execution_root,
        final_dir,
        execution,
        cell,
    )
    result_path = final_dir / _CELL_RESULT_FILENAME
    return {
        "schema_version": EXPERIMENT_MATRIX_SHARD_PROGRESS_SCHEMA,
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "sequence": sequence,
        "cell_id": cell["cell_id"],
        "global_index": cell["global_index"],
        "scope_index": cell["scope_index"],
        "shard_index": cell["shard_index"],
        "shard_sequence": cell["shard_sequence"],
        "cell_result_relative_path": _relative_path(
            result_path,
            execution_root,
        ),
        "cell_result_sha256": _sha256_file(result_path),
        "episode_artifact_tree_sha256": record["artifact_tree_sha256"],
    }


def _validate_cell_container(
    execution_root: Path,
    container: Path,
    execution: Mapping[str, Any],
    expected_cell: Mapping[str, Any],
) -> dict[str, Any]:
    record_path = container / _CELL_RESULT_FILENAME
    record = _read_json_object(record_path)
    if record.get("schema_version") != EXPERIMENT_MATRIX_CELL_RESULT_SCHEMA:
        raise ExperimentMatrixShardError("cell result schema mismatch")
    if record.get("execution_plan_sha256") != execution["execution_plan_sha256"]:
        raise ExperimentMatrixShardError(
            "cell result execution plan mismatch"
        )
    if record.get("parent_plan_sha256") != execution["parent"]["plan_sha256"]:
        raise ExperimentMatrixShardError("cell result parent plan mismatch")
    if record.get("source_git_commit") != execution["source"]["git_commit"]:
        raise ExperimentMatrixShardError("cell result source commit mismatch")
    if record.get("cell") != dict(expected_cell):
        raise ExperimentMatrixShardError("cell result identity mismatch")
    if record.get("status") != "complete":
        raise ExperimentMatrixShardError("cell result is not complete")
    episode_dir = _resolve_relative(
        execution_root,
        record.get("episode_relative_path"),
    )
    if episode_dir != (container / "episode").resolve():
        raise ExperimentMatrixShardError("cell episode path mismatch")
    for name in _REQUIRED_EPISODE_ARTIFACTS:
        if not (episode_dir / name).is_file():
            raise ExperimentMatrixShardError(
                f"required episode artifact is missing: {name}"
            )
    manifest = _read_json_object(episode_dir / "manifest.json")
    config = _read_json_object(episode_dir / "scenario_config.json")
    summary = _read_json_object(episode_dir / "summary.json")
    if manifest.get("git_commit") != execution["source"]["git_commit"]:
        raise ExperimentMatrixShardError("episode manifest commit mismatch")
    if (
        bool(
            execution["parent"]["formal"]
            or execution.get("experiment_authorization") is not None
        )
        and bool(manifest.get("repository_dirty"))
    ):
        raise ExperimentMatrixShardError("episode manifest is dirty")
    metadata = config.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ExperimentMatrixShardError("episode config metadata is missing")
    if metadata.get("algorithm_variant") != expected_cell["variant"]:
        raise ExperimentMatrixShardError("episode algorithm variant mismatch")
    if (
        metadata.get("matrix_execution_plan_sha256")
        != execution["execution_plan_sha256"]
    ):
        raise ExperimentMatrixShardError(
            "episode execution plan lineage mismatch"
        )
    if expected_cell["variant"] != "R0":
        learning_record = _required_mapping(
            record.get("learning_runtime"),
            "cell_result.learning_runtime",
        )
        binding = _required_mapping(
            execution.get("learning_bundles"),
            "learning_bundles",
        )
        if learning_record.get("bundle_binding_sha256") != binding.get(
            "binding_sha256"
        ):
            raise ExperimentMatrixShardError(
                "cell learning bundle binding mismatch"
            )
        authorization_binding = execution.get(
            "experiment_authorization"
        )
        if authorization_binding is None:
            if (
                learning_record.get(
                    "experiment_authorization_sha256"
                )
                is not None
            ):
                raise ExperimentMatrixShardError(
                    "cell claims undeclared experiment authorization"
                )
        else:
            authorization = validate_authorization_binding_payload(
                authorization_binding
            )
            if (
                learning_record.get(
                    "experiment_authorization_sha256"
                )
                != authorization["authorization_file_sha256"]
            ):
                raise ExperimentMatrixShardError(
                    "cell experiment authorization mismatch"
                )
            if (
                learning_record.get(
                    "d5_g1_shadow_model_output_applied"
                )
                is not False
            ):
                raise ExperimentMatrixShardError(
                    "authorized G1 shadow output changed online association"
                )
        diagnostics = _required_mapping(
            metadata.get("learning_runtime"),
            "scenario_config.metadata.learning_runtime",
        )
        if _digest_json(diagnostics) != _required_sha256(
            learning_record.get("diagnostics_sha256"),
            "cell_result.learning_runtime.diagnostics_sha256",
        ):
            raise ExperimentMatrixShardError(
                "cell learning diagnostics digest mismatch"
            )
        preflight = _required_mapping(
            _required_mapping(
                binding.get("variant_preflight"),
                "learning_bundles.variant_preflight",
            ).get(str(expected_cell["variant"])),
            (
                "learning_bundles.variant_preflight."
                f"{expected_cell['variant']}"
            ),
        )
        if learning_record.get("diagnostics_sha256") != _required_sha256(
            preflight.get("diagnostics_sha256"),
            (
                f"{expected_cell['variant']}."
                "preflight.diagnostics_sha256"
            ),
        ):
            raise ExperimentMatrixShardError(
                "cell learning diagnostics differ from execution preflight"
            )
        parent_plan = _plan_from_payload(execution["parent"]["plan"])
        try:
            _validate_resolved_variant(
                str(expected_cell["variant"]),
                diagnostics,
                allow_rule_fallback=parent_plan.allow_rule_fallback,
            )
        except RuntimeError as exc:
            raise ExperimentMatrixShardError(
                "cell learning variant did not retain declared runtime mode"
            ) from exc
        if authorization_binding is not None:
            d5_diagnostics = _required_mapping(
                diagnostics.get("d5"),
                "scenario_config.metadata.learning_runtime.d5",
            )
            if (
                d5_diagnostics.get("effective_mode")
                != "authorized_shadow"
                or d5_diagnostics.get(
                    "experiment_authorization_valid"
                )
                is not True
                or d5_diagnostics.get("model_output_applied") is not False
            ):
                raise ExperimentMatrixShardError(
                    "cell did not retain authorized shadow-only D5 mode"
                )
        resolved_versions = _required_mapping(
            learning_record.get("resolved_versions"),
            "cell_result.learning_runtime.resolved_versions",
        )
        if dict(resolved_versions) != dict(
            _required_mapping(
                preflight.get("resolved_versions"),
                (
                    f"{expected_cell['variant']}."
                    "preflight.resolved_versions"
                ),
            )
        ):
            raise ExperimentMatrixShardError(
                "cell learning versions differ from execution preflight"
            )
        for name in (
            "d3_policy_version",
            "d4_policy_version",
            "d5_model_version",
            "d5_active_vision_policy_version",
        ):
            if resolved_versions.get(name) != config.get(name):
                raise ExperimentMatrixShardError(
                    f"cell learning version mismatch: {name}"
                )
    if not bool(summary.get("finite_state")):
        raise ExperimentMatrixShardError("episode finite_state is false")
    if int(summary.get("online_truth_use_count", -1)) != 0:
        raise ExperimentMatrixShardError(
            "episode online truth use is non-zero"
        )
    artifact_digest = _tree_digest(episode_dir)
    if artifact_digest != _required_sha256(
        record.get("artifact_tree_sha256"),
        "artifact_tree_sha256",
    ):
        raise ExperimentMatrixShardError(
            "episode artifact tree digest mismatch"
        )
    return record


def _write_checkpoint(
    path: Path,
    *,
    execution: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    progress_path: Path,
    completed_cell_count: int,
    status: str,
    resume_count: int,
    recovered_checkpoint_row_count: int,
) -> None:
    _write_json_atomic(
        path,
        {
            "schema_version": EXPERIMENT_MATRIX_SHARD_CHECKPOINT_SCHEMA,
            "execution_plan_sha256": execution["execution_plan_sha256"],
            "source_git_commit": execution["source"]["git_commit"],
            "shard_index": descriptor["shard_index"],
            "shard_id": descriptor["shard_id"],
            "expected_cell_count": descriptor["cell_count"],
            "completed_cell_count": int(completed_cell_count),
            "next_sequence": int(completed_cell_count),
            "status": str(status),
            "resume_count": int(resume_count),
            "recovered_checkpoint_row_count": int(
                recovered_checkpoint_row_count
            ),
            "progress_sha256": _sha256_file(progress_path),
        },
    )


def _load_checkpoint(path: Path) -> dict[str, Any]:
    payload = _read_json_object(path)
    if payload.get("schema_version") != EXPERIMENT_MATRIX_SHARD_CHECKPOINT_SCHEMA:
        raise ExperimentMatrixShardError("shard checkpoint schema mismatch")
    return payload


def _validate_checkpoint_binding(
    checkpoint: Mapping[str, Any],
    *,
    execution: Mapping[str, Any],
    descriptor: Mapping[str, Any],
) -> None:
    expected = {
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "source_git_commit": execution["source"]["git_commit"],
        "shard_index": descriptor["shard_index"],
        "shard_id": descriptor["shard_id"],
        "expected_cell_count": descriptor["cell_count"],
    }
    for name, value in expected.items():
        if checkpoint.get(name) != value:
            raise ExperimentMatrixShardError(
                f"shard checkpoint binding mismatch: {name}"
            )
    completed = int(checkpoint.get("completed_cell_count", -1))
    if completed < 0 or completed > int(descriptor["cell_count"]):
        raise ExperimentMatrixShardError(
            "shard checkpoint completion count is invalid"
        )
    if int(checkpoint.get("next_sequence", -1)) != completed:
        raise ExperimentMatrixShardError(
            "shard checkpoint next_sequence mismatch"
        )
    if int(checkpoint.get("resume_count", -1)) < 0:
        raise ExperimentMatrixShardError(
            "shard checkpoint resume_count is invalid"
        )
    if int(checkpoint.get("recovered_checkpoint_row_count", -1)) < 0:
        raise ExperimentMatrixShardError(
            "shard checkpoint recovered row count is invalid"
        )
    _required_sha256(
        checkpoint.get("progress_sha256"),
        "checkpoint.progress_sha256",
    )


def _merged_cell_row(
    execution_root: Path,
    progress: Mapping[str, Any],
) -> dict[str, Any]:
    result_path = _resolve_relative(
        execution_root,
        progress["cell_result_relative_path"],
    )
    record = _read_json_object(result_path)
    cell = record["cell"]
    metrics = record["metrics"]
    return {
        "cell_index": cell["global_index"],
        "scope_index": cell["scope_index"],
        "variant": cell["variant"],
        "scenario": cell["scenario"],
        "scale": cell["scale"],
        "seed": cell["seed"],
        "comparison_key": cell["comparison_key"],
        "paired_exogenous_config_sha256": record[
            "paired_exogenous_config_sha256"
        ],
        "sensor_random_schedule_version": record[
            "sensor_random_schedule_version"
        ],
        "episode_id": record["episode_id"],
        "episode_relative_path": record["episode_relative_path"],
        "finite_state": metrics["finite_state"],
        "online_truth_use_count": metrics["online_truth_use_count"],
        "real_time_factor": metrics["real_time_factor"],
        "intercepted_target_count": metrics["intercepted_target_count"],
        "cell_result_sha256": progress["cell_result_sha256"],
        "episode_artifact_tree_sha256": progress[
            "episode_artifact_tree_sha256"
        ],
    }


def _build_learning_bundle_binding(
    variants: Sequence[str],
    bundles: ModelBundlePaths,
) -> dict[str, Any]:
    required = required_model_components(variants)
    components: dict[str, dict[str, Any]] = {}
    for component in required:
        path = getattr(bundles, component)
        if path is None or not path.is_dir():
            raise ValueError(f"required model bundle is missing: {component}")
        manifest_path = path / "manifest.json"
        if not manifest_path.is_file():
            raise ExperimentMatrixShardError(
                f"model bundle manifest is missing: {component}"
            )
        inventory = _tree_inventory(path)
        components[component] = {
            "component": component,
            "manifest_sha256": _sha256_file(manifest_path),
            "tree_sha256": _digest_json(inventory),
            "file_count": len(inventory),
            "total_size_bytes": sum(
                int(item["size_bytes"]) for item in inventory
            ),
        }
    binding_payload = {
        "required_components": list(required),
        "components": components,
    }
    return {
        "schema_version": EXPERIMENT_MATRIX_MODEL_BUNDLE_BINDING_SCHEMA,
        **binding_payload,
        "binding_sha256": _digest_json(binding_payload),
    }


def _preflight_scope_variants(
    base_config: ScenarioConfig,
    parent_plan: ExperimentMatrixPlan,
    variants: Sequence[str],
    bundles: ModelBundlePaths,
    *,
    device: str,
    experiment_authorization: G1ShadowExperimentAuthorization | None = None,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for variant in variants:
        if variant == "R0":
            records[variant] = {
                "variant": variant,
                "status": "deterministic_no_model",
                "required_components": [],
            }
            continue
        options = runtime_options_for_variant(
            variant,
            bundles,
            device=device,
            d5_g1_shadow_authorization=experiment_authorization,
        )
        resolved = resolve_learning_runtime(
            base_config,
            options,
            stack_config=IntegratedStackConfig(),
        )
        try:
            _validate_resolved_variant(
                variant,
                resolved.diagnostics,
                allow_rule_fallback=parent_plan.allow_rule_fallback,
            )
        except RuntimeError as exc:
            raise ExperimentMatrixShardError(
                f"variant preflight failed: {variant}"
            ) from exc
        records[variant] = {
            "variant": variant,
            "status": (
                "authorized_shadow_resolved"
                if (
                    variant == "G1"
                    and experiment_authorization is not None
                )
                else (
                    "resolved_with_rule_fallback_allowed"
                    if parent_plan.allow_rule_fallback
                    else "assist_resolved"
                )
            ),
            "required_components": list(
                required_model_components((variant,))
            ),
            "diagnostics_sha256": _digest_json(resolved.diagnostics),
            "resolved_versions": {
                "d3_policy_version": resolved.config.d3_policy_version,
                "d4_policy_version": resolved.config.d4_policy_version,
                "d5_model_version": resolved.config.d5_model_version,
                "d5_active_vision_policy_version": (
                    resolved.config.d5_active_vision_policy_version
                ),
            },
        }
    return records


def _validate_learning_bundle_plan(
    execution: Mapping[str, Any],
    scope_variants: Sequence[str],
) -> None:
    learning = execution.get("learning_bundles")
    required = required_model_components(scope_variants)
    if learning is None:
        if required:
            raise ExperimentMatrixShardError(
                "learned scope is missing model bundle binding"
            )
        return
    payload = _required_mapping(learning, "learning_bundles")
    if (
        payload.get("schema_version")
        != EXPERIMENT_MATRIX_MODEL_BUNDLE_BINDING_SCHEMA
    ):
        raise ExperimentMatrixShardError(
            "model bundle binding schema is unsupported"
        )
    device = payload.get("preflight_device")
    if not isinstance(device, str) or not device.strip():
        raise ExperimentMatrixShardError(
            "model bundle preflight device is invalid"
        )
    if payload.get("required_components") != list(required):
        raise ExperimentMatrixShardError(
            "model bundle required component list mismatch"
        )
    components = _required_mapping(
        payload.get("components"),
        "learning_bundles.components",
    )
    if set(components) != set(required):
        raise ExperimentMatrixShardError(
            "model bundle component inventory mismatch"
        )
    for component in required:
        descriptor = _required_mapping(
            components.get(component),
            f"learning_bundles.components.{component}",
        )
        if descriptor.get("component") != component:
            raise ExperimentMatrixShardError(
                f"model bundle component identity mismatch: {component}"
            )
        _required_sha256(
            descriptor.get("manifest_sha256"),
            f"{component}.manifest_sha256",
        )
        _required_sha256(
            descriptor.get("tree_sha256"),
            f"{component}.tree_sha256",
        )
        if int(descriptor.get("file_count", 0)) <= 0:
            raise ExperimentMatrixShardError(
                f"model bundle file count is invalid: {component}"
            )
        if int(descriptor.get("total_size_bytes", -1)) < 0:
            raise ExperimentMatrixShardError(
                f"model bundle size is invalid: {component}"
            )
    binding_payload = {
        "required_components": list(required),
        "components": dict(components),
    }
    if _digest_json(binding_payload) != _required_sha256(
        payload.get("binding_sha256"),
        "learning_bundles.binding_sha256",
    ):
        raise ExperimentMatrixShardError(
            "model bundle binding digest mismatch"
        )
    preflight = _required_mapping(
        payload.get("variant_preflight"),
        "learning_bundles.variant_preflight",
    )
    if set(preflight) != set(scope_variants):
        raise ExperimentMatrixShardError(
            "model bundle variant preflight inventory mismatch"
        )
    parent_plan = _plan_from_payload(execution["parent"]["plan"])
    authorized_shadow = execution.get("experiment_authorization") is not None
    for variant in scope_variants:
        record = _required_mapping(
            preflight.get(variant),
            f"learning_bundles.variant_preflight.{variant}",
        )
        if record.get("variant") != variant:
            raise ExperimentMatrixShardError(
                f"model bundle preflight variant mismatch: {variant}"
            )
        expected_components = list(
            required_model_components((variant,))
        )
        if record.get("required_components") != expected_components:
            raise ExperimentMatrixShardError(
                f"model bundle preflight component mismatch: {variant}"
            )
        if variant == "R0":
            expected_status = "deterministic_no_model"
        elif variant == "G1" and authorized_shadow:
            expected_status = "authorized_shadow_resolved"
        elif parent_plan.allow_rule_fallback:
            expected_status = "resolved_with_rule_fallback_allowed"
        else:
            expected_status = "assist_resolved"
        if record.get("status") != expected_status:
            raise ExperimentMatrixShardError(
                f"model bundle preflight status mismatch: {variant}"
            )
        if variant != "R0":
            _required_sha256(
                record.get("diagnostics_sha256"),
                f"{variant}.diagnostics_sha256",
            )
            versions = _required_mapping(
                record.get("resolved_versions"),
                f"{variant}.resolved_versions",
            )
            expected_version_keys = {
                "d3_policy_version",
                "d4_policy_version",
                "d5_model_version",
                "d5_active_vision_policy_version",
            }
            if set(versions) != expected_version_keys:
                raise ExperimentMatrixShardError(
                    f"model bundle preflight version inventory mismatch: {variant}"
                )


def _validate_runtime_learning_bundles(
    execution: Mapping[str, Any],
    bundles: ModelBundlePaths,
    *,
    device: str,
) -> None:
    scope_variants = tuple(execution["scope"]["variants"])
    required = required_model_components(scope_variants)
    provided = tuple(
        component
        for component in (
            "d3",
            "d4",
            "d5_graph",
            "d5_active_vision",
        )
        if getattr(bundles, component) is not None
    )
    extra = sorted(set(provided) - set(required))
    if extra:
        raise ExperimentMatrixShardError(
            f"undeclared model bundles were supplied: {extra}"
        )
    validate_required_bundles(scope_variants, bundles)
    learning = execution.get("learning_bundles")
    if learning is None:
        if required:
            raise ExperimentMatrixShardError(
                "learned scope is missing model bundle binding"
            )
        return
    runtime_device = str(device).strip()
    if not runtime_device:
        raise ValueError("learning device must be non-empty")
    if required and learning.get("preflight_device") != runtime_device:
        raise ExperimentMatrixShardError(
            "runtime learning device differs from execution preflight"
        )
    expected = {
        key: value
        for key, value in dict(learning).items()
        if key not in {"preflight_device", "variant_preflight"}
    }
    actual = _build_learning_bundle_binding(scope_variants, bundles)
    if actual != expected:
        raise ExperimentMatrixShardError(
            "runtime model bundle differs from execution plan binding"
        )


def _load_plan_experiment_authorization(
    *,
    source_git_commit: str,
    scope_variants: Sequence[str],
    scenarios: Sequence[str],
    scales: Sequence[int],
    seeds: Sequence[int],
    duration_s: float,
    learning_binding: Mapping[str, Any],
    bundles: ModelBundlePaths,
    device: str,
    authorization_path: str | Path | None,
    expected_authorization_sha256: str | None,
    revocation_registry_path: str | Path | None,
    now_utc: datetime | str | None,
) -> G1ShadowExperimentAuthorization | None:
    provided = (
        authorization_path is not None,
        expected_authorization_sha256 is not None,
        revocation_registry_path is not None,
    )
    if not any(provided):
        return None
    if not all(provided):
        raise ExperimentMatrixShardError(
            "authorization path, explicit SHA-256, and revocation registry "
            "must be provided together"
        )
    if tuple(scope_variants) != ("G1",):
        raise ExperimentMatrixShardError(
            "current experiment authorization permits only a G1-only scope"
        )
    d5_bundle = _authorization_d5_bundle_descriptor(
        learning_binding,
        bundles,
    )
    try:
        grant = load_g1_shadow_experiment_authorization(
            authorization_path,
            expected_authorization_sha256=str(
                expected_authorization_sha256
            ),
            revocation_registry_path=revocation_registry_path,
            now_utc=now_utc,
        )
        validate_authorization_scope_binding(
            grant,
            source_git_commit=source_git_commit,
            scenarios=scenarios,
            scales=scales,
            seeds=seeds,
            duration_s=duration_s,
            d5_bundle_manifest_sha256=d5_bundle["manifest_sha256"],
            d5_bundle_tree_sha256=d5_bundle["tree_sha256"],
            d5_weights_sha256=d5_bundle["weights_sha256"],
            device=device,
            now_utc=now_utc,
        )
    except ExperimentAuthorizationError as exc:
        raise ExperimentMatrixShardError(
            f"G1 shadow experiment authorization rejected: {exc}"
        ) from exc
    return grant


def _load_runtime_experiment_authorization(
    execution: Mapping[str, Any],
    *,
    authorization_path: str | Path | None,
    revocation_registry_path: str | Path | None,
    now_utc: datetime | str | None,
) -> G1ShadowExperimentAuthorization | None:
    binding_payload = execution.get("experiment_authorization")
    if binding_payload is None:
        if (
            authorization_path is not None
            or revocation_registry_path is not None
        ):
            raise ExperimentMatrixShardError(
                "authorization supplied for an execution plan without one"
            )
        return None
    if authorization_path is None or revocation_registry_path is None:
        raise ExperimentMatrixShardError(
            "authorized execution requires authorization and revocation files"
        )
    try:
        binding = validate_authorization_binding_payload(binding_payload)
        grant = load_g1_shadow_experiment_authorization(
            authorization_path,
            expected_authorization_sha256=binding[
                "authorization_file_sha256"
            ],
            revocation_registry_path=revocation_registry_path,
            now_utc=now_utc,
        )
    except ExperimentAuthorizationError as exc:
        raise ExperimentMatrixShardError(
            f"runtime G1 shadow authorization rejected: {exc}"
        ) from exc
    if grant.binding_payload() != binding:
        raise ExperimentMatrixShardError(
            "runtime authorization differs from execution plan binding"
        )
    return grant


def _validate_execution_authorization_binding(
    execution: Mapping[str, Any],
    parent_plan: ExperimentMatrixPlan,
) -> None:
    raw_binding = execution.get("experiment_authorization")
    if raw_binding is None:
        return
    try:
        binding = validate_authorization_binding_payload(raw_binding)
    except ExperimentAuthorizationError as exc:
        raise ExperimentMatrixShardError(
            f"execution authorization binding is invalid: {exc}"
        ) from exc
    scope_variants = tuple(execution["scope"]["variants"])
    if scope_variants != ("G1",):
        raise ExperimentMatrixShardError(
            "authorized execution plan must contain only G1"
        )
    if binding["source_git_commit"] != execution["source"]["git_commit"]:
        raise ExperimentMatrixShardError(
            "authorization source differs from execution source"
        )
    expected_scope = g1_shadow_scope_payload(
        scenarios=parent_plan.scenarios,
        scales=parent_plan.scales,
        seeds=parent_plan.seeds,
        duration_s=parent_plan.duration_s,
    )
    if binding["scope_sha256"] != expected_scope["scope_sha256"]:
        raise ExperimentMatrixShardError(
            "authorization scope digest differs from execution scope"
        )
    learning = _required_mapping(
        execution.get("learning_bundles"),
        "learning_bundles",
    )
    component = _required_mapping(
        _required_mapping(
            learning.get("components"),
            "learning_bundles.components",
        ).get("d5_graph"),
        "learning_bundles.components.d5_graph",
    )
    d5_binding = _required_mapping(
        binding["d5_bundle"],
        "experiment_authorization.d5_bundle",
    )
    if (
        d5_binding["manifest_sha256"] != component["manifest_sha256"]
        or d5_binding["tree_sha256"] != component["tree_sha256"]
    ):
        raise ExperimentMatrixShardError(
            "authorization bundle differs from execution bundle"
        )
    if binding["device"] != learning["preflight_device"]:
        raise ExperimentMatrixShardError(
            "authorization device differs from execution preflight"
        )


def _authorization_d5_bundle_descriptor(
    learning_binding: Mapping[str, Any],
    bundles: ModelBundlePaths,
) -> dict[str, str]:
    components = _required_mapping(
        learning_binding.get("components"),
        "learning_bundles.components",
    )
    component = _required_mapping(
        components.get("d5_graph"),
        "learning_bundles.components.d5_graph",
    )
    bundle_root = bundles.d5_graph
    if bundle_root is None or not bundle_root.is_dir():
        raise ExperimentMatrixShardError(
            "authorized G1 scope requires a D5 graph bundle"
        )
    manifest = _read_json_object(bundle_root / "manifest.json")
    if manifest.get("schema_version") != "d5.tracklet-model-bundle.v5":
        raise ExperimentMatrixShardError(
            "authorized G1 shadow scoring requires a D5 v5 bundle"
        )
    admission = _required_mapping(
        manifest.get("admission"),
        "d5_bundle.manifest.admission",
    )
    if admission.get("g1_assist_eligible") is not True:
        raise ExperimentMatrixShardError(
            "D5 v5 bundle is not evidence-eligible"
        )
    authority_contract = _required_mapping(
        admission.get("authority_contract"),
        "d5_bundle.manifest.admission.authority_contract",
    )
    runtime_authority = _required_mapping(
        authority_contract.get("runtime_authority"),
        "d5_bundle.manifest.admission.authority_contract.runtime_authority",
    )
    if set(runtime_authority) != _D5_V5_RUNTIME_AUTHORITY_FIELDS:
        raise ExperimentMatrixShardError(
            "D5 v5 runtime authority fields are invalid"
        )
    if any(
        value is not False for value in runtime_authority.values()
    ):
        raise ExperimentMatrixShardError(
            "D5 v5 runtime authority must remain fully closed"
        )
    weights = _required_mapping(
        manifest.get("weights"),
        "d5_bundle.manifest.weights",
    )
    weights_sha256 = _required_sha256(
        weights.get("sha256"),
        "d5_bundle.manifest.weights.sha256",
    )
    weights_filename = weights.get("filename")
    if not isinstance(weights_filename, str) or not weights_filename:
        raise ExperimentMatrixShardError(
            "D5 bundle weights filename is invalid"
        )
    weights_path = bundle_root / weights_filename
    if not weights_path.is_file() or _sha256_file(weights_path) != weights_sha256:
        raise ExperimentMatrixShardError(
            "D5 bundle weights digest mismatch"
        )
    return {
        "component": "d5_graph",
        "manifest_sha256": _required_sha256(
            component.get("manifest_sha256"),
            "d5_graph.manifest_sha256",
        ),
        "tree_sha256": _required_sha256(
            component.get("tree_sha256"),
            "d5_graph.tree_sha256",
        ),
        "weights_sha256": weights_sha256,
    }


def _parent_plan_payload(plan: ExperimentMatrixPlan) -> dict[str, Any]:
    return {
        "variants": list(plan.variants),
        "scenarios": list(plan.scenarios),
        "scales": list(plan.scales),
        "seeds": list(plan.seeds),
        "duration_s": plan.duration_s,
        "formal": plan.formal,
        "allow_rule_fallback": plan.allow_rule_fallback,
        "training_seeds": (
            None
            if plan.training_seeds is None
            else sorted(int(value) for value in plan.training_seeds)
        ),
    }


def _plan_from_payload(payload: Mapping[str, Any]) -> ExperimentMatrixPlan:
    training = payload.get("training_seeds")
    return ExperimentMatrixPlan(
        variants=tuple(payload.get("variants", ())),
        scenarios=tuple(payload.get("scenarios", ())),
        scales=tuple(payload.get("scales", ())),
        seeds=tuple(payload.get("seeds", ())),
        duration_s=float(payload.get("duration_s", 0.0)),
        formal=bool(payload.get("formal")),
        allow_rule_fallback=bool(payload.get("allow_rule_fallback")),
        training_seeds=(
            None
            if training is None
            else frozenset(int(value) for value in training)
        ),
    )


def _cell_payload(
    cell: ExperimentCell,
    *,
    global_index: int,
) -> dict[str, Any]:
    return {
        "cell_id": (
            f"{int(global_index):05d}__{cell.variant.lower()}__"
            f"{cell.scenario}__{cell.scale}v{cell.scale}__seed_{cell.seed}"
        ),
        "global_index": int(global_index),
        "variant": cell.variant,
        "scenario": cell.scenario,
        "scale": int(cell.scale),
        "seed": int(cell.seed),
        "comparison_key": cell.comparison_key,
    }


def _shard_id(index: int, count: int) -> str:
    width = max(3, len(str(count - 1)))
    return f"shard_{index:0{width}d}_of_{count:0{width}d}"


def _cell_container_path(
    shard_dir: Path,
    cell: Mapping[str, Any],
) -> Path:
    return shard_dir / "cells" / str(cell["cell_id"])


def _validate_source_state(
    root: Path,
    execution: Mapping[str, Any],
) -> None:
    current_commit, current_dirty = repository_state(root)
    source = execution["source"]
    if current_commit != source["git_commit"]:
        raise ExperimentMatrixShardError(
            "current Git commit differs from execution plan"
        )
    clean_source_required = bool(
        execution["parent"]["formal"]
        or execution.get("experiment_authorization") is not None
    )
    if clean_source_required:
        if bool(source["repository_dirty"]):
            raise ExperimentMatrixShardError(
                "execution plan source is not clean"
            )
        if current_dirty:
            raise ExperimentMatrixShardError(
                "formal or authorized shard execution requires "
                "repository_dirty=false"
            )


def _tree_digest(root: Path) -> str:
    return _digest_json(_tree_inventory(root))


def _tree_inventory(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        raise ExperimentMatrixShardError(
            f"artifact tree is missing: {root}"
        )
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]
    if not entries:
        raise ExperimentMatrixShardError("artifact tree is empty")
    return entries


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
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _progress_prefix_sha256(path: Path, row_count: int) -> str:
    count = int(row_count)
    if count < 0:
        raise ExperimentMatrixShardError(
            "checkpoint progress row count is negative"
        )
    lines = path.read_bytes().splitlines(keepends=True)
    if count > len(lines):
        raise ExperimentMatrixShardError(
            "checkpoint progress row count exceeds progress file"
        )
    return hashlib.sha256(b"".join(lines[:count])).hexdigest()


def _write_json_atomic(path: Path, payload: Any) -> None:
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    _write_text_atomic(path, text)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _write_rows_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    if not rows:
        raise ExperimentMatrixShardError("cannot write an empty merged cell table")
    fieldnames = sorted({name for row in rows for name in row})
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _append_jsonl_fsync(path: Path, payload: Mapping[str, Any]) -> None:
    line = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ExperimentMatrixShardError(f"required JSON is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperimentMatrixShardError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise ExperimentMatrixShardError(f"JSON artifact must be an object: {path}")
    return payload


def _required_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExperimentMatrixShardError(f"{name} must be an object")
    return value


def _required_sha256(value: Any, name: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(character not in _HEX64 for character in text):
        raise ExperimentMatrixShardError(f"{name} must be a SHA-256 digest")
    return text


def _required_timestamp(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("created_at_utc must be non-empty")
    return text


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ExperimentMatrixShardError(
            f"path escapes execution root: {path}"
        ) from exc


def _resolve_relative(root: Path, value: Any) -> Path:
    text = str(value).strip()
    if not text:
        raise ExperimentMatrixShardError("relative artifact path is empty")
    candidate = (root / text).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ExperimentMatrixShardError(
            f"artifact path escapes execution root: {text}"
        ) from exc
    return candidate


__all__ = [
    "EXPERIMENT_MATRIX_CELL_RESULT_SCHEMA",
    "EXPERIMENT_MATRIX_EXECUTION_PLAN_SCHEMA",
    "EXPERIMENT_MATRIX_SCOPE_MERGE_SCHEMA",
    "EXPERIMENT_MATRIX_SHARD_CHECKPOINT_SCHEMA",
    "EXPERIMENT_MATRIX_SHARD_PLAN_SCHEMA",
    "EXPERIMENT_MATRIX_SHARD_PROGRESS_SCHEMA",
    "EXPERIMENT_MATRIX_SHARD_MERGE_FRAGMENT_SCHEMA",
    "EXPERIMENT_MATRIX_SHARD_STORAGE_VALIDATION_SCHEMA",
    "FORMAL_PARENT_EXPECTED_CELL_COUNT",
    "FORMAL_R0_DEFAULT_MINIMUM_FREE_BYTES",
    "FORMAL_R0_DEFAULT_SHARD_COUNT",
    "FORMAL_R0_EXPECTED_CELL_COUNT",
    "ExperimentMatrixShardError",
    "collect_experiment_matrix_shard_merge_fragment",
    "create_experiment_matrix_execution_plan",
    "create_formal_r0_execution_plan",
    "load_experiment_matrix_execution_plan",
    "merge_experiment_matrix_shards",
    "run_experiment_matrix_shard",
    "validate_experiment_matrix_execution_source",
    "validate_experiment_matrix_shard_for_storage",
]
