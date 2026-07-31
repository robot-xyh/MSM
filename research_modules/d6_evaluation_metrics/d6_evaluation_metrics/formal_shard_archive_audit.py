"""Independent D6 audit for archived formal experiment shards.

This module deliberately does not import the producer archive implementation.
It treats archive manifests, producer merge indexes, and producer D6 reports as
untrusted evidence.  One shard is verified and staged at a time, then the
existing low-level posterior audit is run against that temporary shard.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile
from typing import Any, Callable, Mapping, Sequence

from .formal_r0_targeted_posterior_audit import (
    FormalR0TargetCell,
    FormalR0TargetedPosteriorAuditInputs,
    audit_formal_r0_targeted_posterior,
)


FORMAL_SHARD_ARCHIVE_AUDIT_SCHEMA_VERSION = (
    "d6.formal-shard-archive-audit.v1"
)
FORMAL_SHARD_ARCHIVE_MANIFEST_SCHEMA = (
    "scalable3d-formal-shard-archive-manifest-v1"
)
FORMAL_SHARD_ARCHIVE_FORMAT = "deterministic-pax-tar-zstd-v1"
FORMAL_SHARD_ARCHIVE_SCOPE_MERGE_SCHEMA = (
    "scalable3d-formal-shard-archive-scope-merge-v1"
)
FORMAL_SHARD_ARCHIVE_D6_BINDING_SCHEMA = (
    "scalable3d-formal-shard-archive-d6-binding-v1"
)
FORMAL_SHARD_ARCHIVE_STORAGE_MODE = "verified_formal_shard_archives_v1"
FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME = "shard_archive_manifest.json"
FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME = "shard_payload.tar.zst"
FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME = "SHA256SUMS"
_ARTIFACT_INVENTORY_SCHEMA = "scalable3d-artifact-inventory-v1"
_SHARD_STORAGE_VALIDATION_SCHEMA = (
    "scalable3d-experiment-matrix-shard-storage-validation-v1"
)
_ARCHIVE_ROOT_ENTRIES = frozenset(
    {
        FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME,
        FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME,
        FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME,
    }
)
_MERGE_CORE_FILES = frozenset(
    {
        "episode_dirs.json",
        "experiment_matrix_scope_cells.csv",
        "experiment_matrix_scope_manifest.json",
        "archive_d6_evaluation_binding.json",
    }
)
_EXPECTED_D6_ARTIFACTS = frozenset(
    {
        "aggregate_json",
        "markdown",
        "module_performance_evidence",
        "per_episode_seed_csv",
        "stage_timing_curve",
    }
)
_HEX = frozenset("0123456789abcdef")


class FormalShardArchiveAuditError(ValueError):
    """Raised when an archive cannot be safely inspected."""


def audit_formal_shard_archives(
    *,
    execution_root: Path,
    source_repository: Path,
    archive_root: Path,
    expected_source_git_commit: str,
    expected_execution_plan_sha256: str,
    expected_scope_cell_count: int,
    expected_shard_count: int,
    expected_cells_per_shard: int,
    plan: Mapping[str, Any],
    targets: Sequence[FormalR0TargetCell],
) -> dict[str, Any]:
    """Verify and audit a complete archive set with one staged shard at a time."""

    root = Path(execution_root).resolve()
    archive_path = Path(archive_root).expanduser().absolute()
    plan_path = root / "experiment_matrix_execution_plan.json"
    checksum_path = root / "EXECUTION_PLAN_SHA256"
    reasons: list[str] = []
    archive_rows: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    source_result: dict[str, Any] = {}
    plan_result: dict[str, Any] = {}
    progress_rows: list[dict[str, Any]] = []

    descriptors = _plan_shard_descriptors(plan)
    expected_names = {
        f"shard_{index:03d}_of_{expected_shard_count:03d}"
        for index in range(expected_shard_count)
    }
    if _path_contains_symlink(archive_path) or not archive_path.is_dir():
        return _archive_failure(
            f"archive_root_unavailable_or_unsafe:{archive_path}",
            expected_shard_count=expected_shard_count,
        )
    archives = archive_path.resolve()
    archive_directories: set[str] = set()
    sidecar_files: list[str] = []
    for entry in archives.iterdir():
        if entry.is_symlink():
            return _archive_failure(
                f"archive_root_symlink_entry:{entry.name}",
                expected_shard_count=expected_shard_count,
            )
        if entry.is_dir():
            archive_directories.add(entry.name)
        elif entry.is_file():
            sidecar_files.append(entry.name)
        else:
            return _archive_failure(
                f"archive_root_non_regular_entry:{entry.name}",
                expected_shard_count=expected_shard_count,
            )
    if archive_directories != expected_names:
        missing = sorted(expected_names - archive_directories)
        extra = sorted(archive_directories - expected_names)
        return _archive_failure(
            "archive_set_mismatch:"
            f"missing={','.join(missing)}:extra={','.join(extra)}",
            expected_shard_count=expected_shard_count,
            sidecar_files=sidecar_files,
        )
    targets_by_shard: dict[int, list[FormalR0TargetCell]] = {}
    for target in targets:
        targets_by_shard.setdefault(int(target.shard_index), []).append(target)

    zstd = shutil.which("zstd")
    if zstd is None:
        return _archive_failure(
            "zstd_runtime_unavailable",
            expected_shard_count=expected_shard_count,
        )

    for index in range(expected_shard_count):
        shard_id = f"shard_{index:03d}_of_{expected_shard_count:03d}"
        archive = archives / shard_id
        try:
            with tempfile.TemporaryDirectory(
                prefix=f"d6-{shard_id}-archive-audit-"
            ) as temporary_name:
                temporary_root = Path(temporary_name).resolve()
                staged_shard = temporary_root / "shards" / shard_id
                staged_shard.mkdir(parents=True)
                manifest, archive_record = verify_and_restore_formal_shard_archive(
                    archive=archive,
                    destination=staged_shard,
                    plan_path=plan_path,
                    plan=plan,
                    descriptor=descriptors.get(index),
                    shard_index=index,
                    expected_source_git_commit=expected_source_git_commit,
                    expected_execution_plan_sha256=(
                        expected_execution_plan_sha256
                    ),
                    expected_cells_per_shard=expected_cells_per_shard,
                    zstd_path=zstd,
                )
                shutil.copy2(plan_path, temporary_root / plan_path.name)
                if checksum_path.is_file():
                    shutil.copy2(checksum_path, temporary_root / checksum_path.name)
                shard_targets = tuple(targets_by_shard.get(index, ()))
                if len(shard_targets) != expected_cells_per_shard:
                    raise FormalShardArchiveAuditError(
                        "canonical target count does not match archive shard"
                    )
                targeted = audit_formal_r0_targeted_posterior(
                    FormalR0TargetedPosteriorAuditInputs(
                        execution_root=temporary_root,
                        source_repository=source_repository,
                        expected_source_git_commit=expected_source_git_commit,
                        expected_execution_plan_sha256=(
                            expected_execution_plan_sha256
                        ),
                        expected_scope_cell_count=expected_scope_cell_count,
                        expected_completed_cell_count=expected_cells_per_shard,
                        expected_shard_progress=((index, expected_cells_per_shard),),
                        targets=shard_targets,
                    )
                )
                archive_record["low_level_verdict"] = targeted.get("verdict")
                archive_record["low_level_verified_cell_count"] = sum(
                    row.get("verified") is True
                    for row in targeted.get("cells", ())
                )
                archive_record["staged_tree_sha256"] = manifest["inventory"][
                    "tree_sha256"
                ]
                archive_rows.append(archive_record)
                cells.extend(dict(row) for row in targeted.get("cells", ()))
                if not source_result:
                    source_result = dict(targeted.get("source", {}))
                    plan_result = dict(targeted.get("execution_plan", {}))
                progress_rows.extend(
                    dict(row)
                    for row in targeted.get("execution_progress", {}).get(
                        "shards", ()
                    )
                )
                for section in ("source", "execution_plan", "execution_progress"):
                    reasons.extend(
                        f"{shard_id}:{reason}"
                        for reason in targeted.get(section, {}).get(
                            "failure_reasons", ()
                        )
                    )
        except (OSError, ValueError, tarfile.TarError) as exc:
            reasons.append(f"{shard_id}:archive_verification_failed:{exc}")
            break

    if len(archive_rows) != expected_shard_count:
        reasons.append(
            "verified_archive_count_mismatch:"
            f"expected={expected_shard_count}:actual={len(archive_rows)}"
        )
    if len(cells) != expected_scope_cell_count:
        reasons.append(
            "archive_audited_cell_count_mismatch:"
            f"expected={expected_scope_cell_count}:actual={len(cells)}"
        )
    target_order = {
        target.cell_id: target_index
        for target_index, target in enumerate(targets)
    }
    ordered_cells = sorted(
        cells,
        key=lambda row: target_order.get(
            str(row.get("cell_id")), expected_scope_cell_count
        ),
    )
    reasons = list(dict.fromkeys(str(reason) for reason in reasons))
    return {
        "schema_version": FORMAL_SHARD_ARCHIVE_AUDIT_SCHEMA_VERSION,
        "verified": not reasons,
        "storage_mode": FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
        "archive_root": str(archives),
        "sidecar_files": sorted(sidecar_files),
        "expected_shard_count": expected_shard_count,
        "verified_archive_count": len(archive_rows),
        "low_level_audited_cell_count": len(cells),
        "peak_staged_shard_count": 1 if archive_rows else 0,
        "archive_source_preserved": archives.is_dir(),
        "source_deletion_performed": False,
        "archive_deletion_performed": False,
        "source": source_result,
        "execution_plan": plan_result,
        "execution_progress": {
            "verified": all(row.get("verified") is True for row in progress_rows)
            and len(progress_rows) == expected_shard_count,
            "scope_cell_count": expected_scope_cell_count,
            "completed_cell_count": sum(
                int(row.get("actual_progress_row_count", 0))
                for row in progress_rows
            ),
            "shards": progress_rows,
            "failure_reasons": reasons,
        },
        "archives": archive_rows,
        "cells": ordered_cells,
        "failure_reasons": reasons,
    }


def verify_and_restore_formal_shard_archive(
    *,
    archive: Path,
    destination: Path,
    plan_path: Path,
    plan: Mapping[str, Any],
    descriptor: Mapping[str, Any] | None,
    shard_index: int,
    expected_source_git_commit: str,
    expected_execution_plan_sha256: str,
    expected_cells_per_shard: int,
    zstd_path: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Independently verify one archive and restore only verified members."""

    if archive.is_symlink() or not archive.is_dir():
        raise FormalShardArchiveAuditError("archive directory unavailable or unsafe")
    entries = {entry.name for entry in archive.iterdir()}
    if entries != _ARCHIVE_ROOT_ENTRIES:
        raise FormalShardArchiveAuditError("archive root entries mismatch")
    for name in _ARCHIVE_ROOT_ENTRIES:
        _require_regular_file_without_symlink(
            archive,
            archive / name,
            label=f"archive file {name}",
        )
    checksums = _read_checksum_file(
        archive / FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME,
        expected_names=_ARCHIVE_ROOT_ENTRIES
        - {FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME},
    )
    for name, expected in checksums.items():
        if _sha256_file(archive / name) != expected:
            raise FormalShardArchiveAuditError(f"archive checksum mismatch:{name}")
    manifest = _read_json_object(archive / FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME)
    if manifest.get("schema_version") != FORMAL_SHARD_ARCHIVE_MANIFEST_SCHEMA:
        raise FormalShardArchiveAuditError("archive manifest schema mismatch")
    if manifest.get("archive_format") != FORMAL_SHARD_ARCHIVE_FORMAT:
        raise FormalShardArchiveAuditError("archive format mismatch")
    source = _require_mapping(manifest.get("source"), "archive source")
    shard_id = f"shard_{shard_index:03d}_of_{len(_plan_shard_descriptors(plan)):03d}"
    if source != {
        "name": shard_id,
        "canonical_relative_path": f"shards/{shard_id}",
        "preserved_at_creation": True,
        "deletion_performed_by_tool": False,
    }:
        raise FormalShardArchiveAuditError("archive source contract mismatch")
    binding = _require_mapping(manifest.get("binding"), "archive binding")
    expected_binding = _expected_archive_binding(
        plan_path=plan_path,
        plan=plan,
        descriptor=descriptor,
        shard_index=shard_index,
        expected_source_git_commit=expected_source_git_commit,
        expected_execution_plan_sha256=expected_execution_plan_sha256,
        expected_cells_per_shard=expected_cells_per_shard,
    )
    for field, expected in expected_binding.items():
        if binding.get(field) != expected:
            raise FormalShardArchiveAuditError(
                f"archive execution-plan binding mismatch:{field}"
            )
    if binding.get("storage_validation_schema") != _SHARD_STORAGE_VALIDATION_SCHEMA:
        raise FormalShardArchiveAuditError("archive storage schema mismatch")
    if binding.get("storage_validation_status") != "verified_complete":
        raise FormalShardArchiveAuditError("archive shard is not complete")

    inventory = _require_mapping(manifest.get("inventory"), "archive inventory")
    records = _validate_inventory(inventory)
    for relative, binding_field in (
        ("shard_plan.json", "shard_plan_sha256"),
        ("progress.jsonl", "progress_sha256"),
        ("checkpoint.json", "checkpoint_sha256"),
    ):
        record = records.get(relative)
        if record is None or record["sha256"] != binding.get(binding_field):
            raise FormalShardArchiveAuditError(
                f"archive inventory binding mismatch:{relative}"
            )
    payload = _require_mapping(manifest.get("payload"), "archive payload")
    payload_path = archive / FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME
    if payload.get("filename") != FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME:
        raise FormalShardArchiveAuditError("archive payload filename mismatch")
    if payload.get("sha256") != checksums[FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME]:
        raise FormalShardArchiveAuditError("archive payload digest binding mismatch")
    if payload.get("size_bytes") != payload_path.stat().st_size:
        raise FormalShardArchiveAuditError("archive payload size mismatch")
    compression = _require_mapping(manifest.get("compression"), "compression")
    if (
        compression.get("algorithm") != "zstd"
        or compression.get("threads") != 1
        or not isinstance(compression.get("runtime"), str)
        or not 1 <= int(compression.get("level", 0)) <= 19
    ):
        raise FormalShardArchiveAuditError("archive compression contract mismatch")
    free_bytes = shutil.disk_usage(destination.parent).free
    if int(inventory["total_size_bytes"]) + 16 * 1024**2 > free_bytes:
        raise FormalShardArchiveAuditError("insufficient staging capacity")
    _verify_tar_zst_payload(
        payload_path,
        records=records,
        destination=destination,
        zstd_path=zstd_path,
    )
    if _inventory_tree(destination) != dict(inventory):
        raise FormalShardArchiveAuditError("staged archive inventory mismatch")
    return dict(manifest), {
        "shard_index": shard_index,
        "shard_id": shard_id,
        "archive_manifest_sha256": _sha256_file(
            archive / FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME
        ),
        "archive_checksum_file_sha256": _sha256_file(
            archive / FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME
        ),
        "payload_sha256": _sha256_file(payload_path),
        "payload_tree_sha256": inventory["tree_sha256"],
        "archive_size_bytes": payload_path.stat().st_size,
        "file_count": inventory["file_count"],
        "total_size_bytes": inventory["total_size_bytes"],
        "binding": dict(binding),
    }


def audit_archive_merge_bundle(
    *,
    merged_scope_dir: Path,
    expected_source_git_commit: str,
    expected_execution_plan_sha256: str,
    expected_scope_cell_count: int,
    expected_parent_cell_count: int,
    expected_shard_count: int,
    archive_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Independently validate the archive-native merge and D6 report binding."""

    unresolved_root = Path(merged_scope_dir).expanduser().absolute()
    reasons: list[str] = []
    if _path_contains_symlink(unresolved_root) or not unresolved_root.is_dir():
        return {
            "verified": False,
            "failure_reasons": [
                f"archive_merge_root_unavailable:{unresolved_root}"
            ],
            "cell_failure_reasons": {},
        }
    root = unresolved_root.resolve()
    manifest_path = root / "experiment_matrix_scope_manifest.json"
    cells_path = root / "experiment_matrix_scope_cells.csv"
    episode_index_path = root / "episode_dirs.json"
    binding_path = root / "archive_d6_evaluation_binding.json"
    checksum_path = root / "SHA256SUMS"
    try:
        for path in (
            checksum_path,
            manifest_path,
            cells_path,
            episode_index_path,
            binding_path,
        ):
            _require_regular_file_without_symlink(
                root,
                path,
                label=f"archive merge core file {path.name}",
            )
        checksums = _read_checksum_file(
            checksum_path,
            expected_names=_MERGE_CORE_FILES,
        )
        for name, expected in checksums.items():
            if _sha256_file(root / name) != expected:
                reasons.append(f"archive_merge_checksum_mismatch:{name}")
        manifest = _read_json_object(manifest_path)
        episode_index = _read_json_object(episode_index_path)
        d6_binding = _read_json_object(binding_path)
    except (OSError, ValueError) as exc:
        return {
            "verified": False,
            "failure_reasons": [f"archive_merge_bundle_unreadable:{exc}"],
            "cell_failure_reasons": {},
        }

    expected_manifest = {
        "schema_version": FORMAL_SHARD_ARCHIVE_SCOPE_MERGE_SCHEMA,
        "storage_mode": FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
        "source_git_commit": expected_source_git_commit,
        "source_repository_dirty": False,
        "execution_plan_sha256": expected_execution_plan_sha256,
        "scope_expected_cell_count": expected_scope_cell_count,
        "scope_completed_cell_count": expected_scope_cell_count,
        "parent_full_cell_count": expected_parent_cell_count,
        "scope_complete": True,
        "formal_scope_complete": True,
        "archive_set_complete": True,
        "canonical_episode_directories_materialized": False,
        "peak_restored_shard_count": 1,
        "d6_evaluation_generated": True,
    }
    for field, expected in expected_manifest.items():
        if manifest.get(field) != expected:
            reasons.append(f"archive_merge_manifest_mismatch:{field}")
    if manifest.get("d6_evaluation_binding_sha256") != _sha256_file(binding_path):
        reasons.append("archive_merge_d6_binding_digest_mismatch")
    declared_shards = manifest.get("shards")
    if not isinstance(declared_shards, list):
        reasons.append("archive_merge_shards_unavailable")
        declared_shards = []
    if len(declared_shards) != expected_shard_count:
        reasons.append("archive_merge_shard_count_mismatch")
    declared_indices = [
        row.get("shard_index")
        for row in declared_shards
        if isinstance(row, Mapping)
        and isinstance(row.get("shard_index"), int)
        and not isinstance(row.get("shard_index"), bool)
    ]
    expected_indices = list(range(expected_shard_count))
    if len(set(declared_indices)) != len(declared_indices):
        reasons.append("archive_merge_duplicate_shard_index")
    if sorted(declared_indices) != expected_indices:
        reasons.append("archive_merge_shard_index_set_mismatch")
    if declared_indices != expected_indices:
        reasons.append("archive_merge_shard_order_mismatch")
    records_by_index = {
        int(row["shard_index"]): row for row in archive_records
    }
    for row in declared_shards:
        if (
            not isinstance(row, Mapping)
            or not isinstance(row.get("shard_index"), int)
            or isinstance(row.get("shard_index"), bool)
        ):
            reasons.append("archive_merge_shard_record_invalid")
            continue
        index = int(row["shard_index"])
        verified = records_by_index.get(index)
        archive_contract = row.get("archive")
        if verified is None or not isinstance(archive_contract, Mapping):
            reasons.append(f"archive_merge_shard_binding_missing:{index}")
            continue
        for field in (
            "archive_manifest_sha256",
            "archive_checksum_file_sha256",
            "payload_sha256",
            "payload_tree_sha256",
            "archive_size_bytes",
            "file_count",
            "total_size_bytes",
        ):
            if archive_contract.get(field) != verified.get(field):
                reasons.append(f"archive_merge_shard_binding_mismatch:{index}:{field}")
        if archive_contract.get("directory_name") != verified.get("shard_id"):
            reasons.append(
                f"archive_merge_shard_binding_mismatch:{index}:directory_name"
            )
        if archive_contract.get("archive_format") != FORMAL_SHARD_ARCHIVE_FORMAT:
            reasons.append(
                f"archive_merge_shard_binding_mismatch:{index}:archive_format"
            )
        expected_cell_count = verified.get("binding", {}).get(
            "completed_cell_count"
        )
        if row.get("cell_count") != expected_cell_count:
            reasons.append(
                f"archive_merge_shard_cell_count_mismatch:{index}"
            )
        for field in (
            "shard_id",
            "shard_index",
            "shard_plan_sha256",
            "progress_sha256",
            "checkpoint_sha256",
        ):
            if row.get(field) != verified["binding"].get(field):
                reasons.append(f"archive_merge_shard_digest_mismatch:{index}:{field}")

    expected_paths = _read_merge_cells(cells_path, reasons)
    if len(expected_paths) != expected_scope_cell_count:
        reasons.append("archive_merge_cells_count_mismatch")
    if episode_index.get("schema_version") != FORMAL_SHARD_ARCHIVE_SCOPE_MERGE_SCHEMA:
        reasons.append("archive_merge_episode_index_schema_mismatch")
    if episode_index.get("storage_mode") != FORMAL_SHARD_ARCHIVE_STORAGE_MODE:
        reasons.append("archive_merge_episode_index_storage_mode_mismatch")
    if episode_index.get("execution_plan_sha256") != expected_execution_plan_sha256:
        reasons.append("archive_merge_episode_index_plan_mismatch")
    if episode_index.get("episode_count") != expected_scope_cell_count:
        reasons.append("archive_merge_episode_index_count_mismatch")
    if episode_index.get("canonical_directories_materialized") is not False:
        reasons.append("archive_merge_episode_index_materialization_mismatch")
    paths = episode_index.get("paths_relative_to_execution_root")
    if not isinstance(paths, list) or paths != expected_paths:
        reasons.append("archive_merge_episode_index_paths_mismatch")
    for path in paths if isinstance(paths, list) else ():
        try:
            _safe_relative_path(str(path))
        except FormalShardArchiveAuditError:
            reasons.append("archive_merge_episode_index_path_unsafe")

    reasons.extend(
        _audit_archive_d6_binding(
            root=root,
            payload=d6_binding,
            expected_execution_plan_sha256=expected_execution_plan_sha256,
            expected_scope_cell_count=expected_scope_cell_count,
        )
    )
    reasons = list(dict.fromkeys(reasons))
    return {
        "verified": not reasons,
        "storage_mode": FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
        "scope_row_count": len(expected_paths),
        "episode_index_count": len(paths) if isinstance(paths, list) else 0,
        "d6_report_binding_verified": not any(
            reason.startswith("archive_d6_")
            or "d6_binding" in reason
            for reason in reasons
        ),
        "producer_d6_conclusions_used": False,
        "cell_failure_reasons": {},
        "failure_reasons": reasons,
    }


def _expected_archive_binding(
    *,
    plan_path: Path,
    plan: Mapping[str, Any],
    descriptor: Mapping[str, Any] | None,
    shard_index: int,
    expected_source_git_commit: str,
    expected_execution_plan_sha256: str,
    expected_cells_per_shard: int,
) -> dict[str, Any]:
    if descriptor is None:
        raise FormalShardArchiveAuditError("execution plan shard descriptor missing")
    cells = [
        cell
        for cell in _plan_scope_cells(plan)
        if int(cell.get("shard_index", -1)) == shard_index
    ]
    return {
        "execution_plan_sha256": expected_execution_plan_sha256,
        "execution_plan_file_sha256": _sha256_file(plan_path),
        "parent_plan_sha256": plan.get("parent", {}).get("plan_sha256"),
        "source_git_commit": expected_source_git_commit,
        "shard_index": shard_index,
        "shard_id": descriptor.get("shard_id"),
        "expected_cell_count": expected_cells_per_shard,
        "completed_cell_count": expected_cells_per_shard,
        "descriptor_sha256": _digest_json(descriptor),
        "cells_sha256": _digest_json(cells),
    }


def _validate_inventory(inventory: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if inventory.get("schema_version") != _ARTIFACT_INVENTORY_SCHEMA:
        raise FormalShardArchiveAuditError("archive inventory schema mismatch")
    raw_records = inventory.get("files")
    if not isinstance(raw_records, list) or not raw_records:
        raise FormalShardArchiveAuditError("archive inventory files missing")
    if inventory.get("file_count") != len(raw_records):
        raise FormalShardArchiveAuditError("archive inventory count mismatch")
    records: dict[str, dict[str, Any]] = {}
    digest = hashlib.sha256()
    total = 0
    previous: str | None = None
    for raw in raw_records:
        if not isinstance(raw, Mapping):
            raise FormalShardArchiveAuditError("archive inventory record invalid")
        relative = str(raw.get("relative_path", ""))
        _safe_relative_path(relative)
        if previous is not None and relative <= previous:
            raise FormalShardArchiveAuditError("archive inventory paths not sorted")
        previous = relative
        size = raw.get("size_bytes")
        sha256 = raw.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise FormalShardArchiveAuditError("archive inventory size invalid")
        _require_digest(sha256, "archive inventory file")
        records[relative] = {
            "relative_path": relative,
            "size_bytes": size,
            "sha256": sha256,
        }
        total += size
        digest.update(f"{sha256}  {size}  {relative}\n".encode())
    if inventory.get("total_size_bytes") != total:
        raise FormalShardArchiveAuditError("archive inventory total size mismatch")
    if inventory.get("tree_sha256") != digest.hexdigest():
        raise FormalShardArchiveAuditError("archive inventory tree digest mismatch")
    return records


def _verify_tar_zst_payload(
    payload_path: Path,
    *,
    records: Mapping[str, Mapping[str, Any]],
    destination: Path,
    zstd_path: str,
) -> None:
    process = subprocess.Popen(
        [zstd_path, "-dc", "--quiet", str(payload_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    seen: set[str] = set()
    try:
        if process.stdout is None or process.stderr is None:
            raise FormalShardArchiveAuditError("archive decompressor unavailable")
        stream = tarfile.open(fileobj=process.stdout, mode="r|")
        try:
            for member in stream:
                relative = _safe_tar_member(member)
                if relative in seen or relative not in records:
                    raise FormalShardArchiveAuditError(
                        f"archive tar member unexpected or duplicate:{relative}"
                    )
                seen.add(relative)
                expected = records[relative]
                if member.size != expected["size_bytes"]:
                    raise FormalShardArchiveAuditError(
                        f"archive tar member size mismatch:{relative}"
                    )
                source = stream.extractfile(member)
                if source is None:
                    raise FormalShardArchiveAuditError(
                        f"archive tar member unreadable:{relative}"
                    )
                target = destination / PurePosixPath(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with source, target.open("xb") as output:
                    while block := source.read(1024 * 1024):
                        digest.update(block)
                        output.write(block)
                if digest.hexdigest() != expected["sha256"]:
                    raise FormalShardArchiveAuditError(
                        f"archive tar member digest mismatch:{relative}"
                    )
        finally:
            stream.close()
            process.stdout.close()
        stderr = process.stderr.read().decode(errors="replace")
        code = process.wait()
        if code != 0:
            raise FormalShardArchiveAuditError(
                f"archive decompression failed:{code}:{stderr.strip()}"
            )
    except Exception:
        if process.stdout is not None and not process.stdout.closed:
            process.stdout.close()
        process.terminate()
        process.wait()
        raise
    if seen != set(records):
        raise FormalShardArchiveAuditError("archive tar members missing")


def _safe_tar_member(member: tarfile.TarInfo) -> str:
    if not member.isfile():
        raise FormalShardArchiveAuditError("archive tar member is not regular file")
    relative = _safe_relative_path(member.name)
    if (
        member.uid != 0
        or member.gid != 0
        or int(member.mtime) != 0
        or member.mode != 0o644
    ):
        raise FormalShardArchiveAuditError("archive tar metadata is not deterministic")
    return relative


def _inventory_tree(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    total = 0
    for path in sorted((p for p in root.rglob("*") if p.is_file())):
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        sha256 = _sha256_file(path)
        files.append({"relative_path": relative, "size_bytes": size, "sha256": sha256})
        total += size
        digest.update(f"{sha256}  {size}  {relative}\n".encode())
    return {
        "schema_version": _ARTIFACT_INVENTORY_SCHEMA,
        "file_count": len(files),
        "total_size_bytes": total,
        "tree_sha256": digest.hexdigest(),
        "files": files,
    }


def _audit_archive_d6_binding(
    *,
    root: Path,
    payload: Mapping[str, Any],
    expected_execution_plan_sha256: str,
    expected_scope_cell_count: int,
) -> list[str]:
    reasons: list[str] = []
    if payload.get("schema_version") != FORMAL_SHARD_ARCHIVE_D6_BINDING_SCHEMA:
        reasons.append("archive_d6_binding_schema_mismatch")
    if payload.get("storage_mode") != FORMAL_SHARD_ARCHIVE_STORAGE_MODE:
        reasons.append("archive_d6_binding_storage_mode_mismatch")
    if payload.get("execution_plan_sha256") != expected_execution_plan_sha256:
        reasons.append("archive_d6_binding_plan_mismatch")
    if payload.get("episode_count") != expected_scope_cell_count:
        reasons.append("archive_d6_binding_episode_count_mismatch")
    if payload.get("scope_indices") != list(range(expected_scope_cell_count)):
        reasons.append("archive_d6_binding_scope_indices_mismatch")
    reasons.extend(
        _validate_provenance_list(
            payload,
            field="evaluator_schema_versions",
            validator=lambda value: bool(value.strip()),
        )
    )
    reasons.extend(
        _validate_provenance_list(
            payload,
            field="evaluator_git_commits",
            validator=lambda value: _is_hex_digest(value, 40),
        )
    )
    dirty_values = payload.get("evaluator_repository_dirty_values")
    if (
        not isinstance(dirty_values, list)
        or not dirty_values
        or any(not isinstance(value, bool) for value in dirty_values)
        or len(set(dirty_values)) != len(dirty_values)
    ):
        reasons.append(
            "archive_d6_binding_evaluator_repository_dirty_values_invalid"
        )
    reasons.extend(
        _validate_provenance_list(
            payload,
            field="evaluator_source_tree_sha256s",
            validator=_is_prefixed_sha256,
        )
    )
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != _EXPECTED_D6_ARTIFACTS:
        reasons.append("archive_d6_artifact_set_mismatch")
        return reasons
    seen_paths: set[str] = set()
    for name, raw in artifacts.items():
        if not isinstance(raw, Mapping):
            reasons.append(f"archive_d6_artifact_invalid:{name}")
            continue
        try:
            relative = _safe_relative_path(str(raw.get("relative_path", "")))
        except FormalShardArchiveAuditError:
            reasons.append(f"archive_d6_artifact_path_unsafe:{name}")
            continue
        if relative in seen_paths:
            reasons.append(f"archive_d6_artifact_path_duplicate:{name}")
        seen_paths.add(relative)
        artifact = root / relative
        try:
            _require_regular_file_without_symlink(
                root,
                artifact,
                label=f"archive D6 artifact {name}",
            )
        except FormalShardArchiveAuditError as exc:
            reason = (
                "archive_d6_artifact_symlink"
                if "symbolic link" in str(exc)
                else "archive_d6_artifact_missing"
            )
            reasons.append(f"{reason}:{name}")
            continue
        if raw.get("size_bytes") != artifact.stat().st_size:
            reasons.append(f"archive_d6_artifact_size_mismatch:{name}")
        if raw.get("sha256") != _sha256_file(artifact):
            reasons.append(f"archive_d6_artifact_digest_mismatch:{name}")
    return reasons


def _read_merge_cells(path: Path, reasons: list[str]) -> list[str]:
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, csv.Error) as exc:
        reasons.append(f"archive_merge_cells_unreadable:{exc}")
        return []
    indices: list[int] = []
    paths: list[str] = []
    for row in rows:
        try:
            indices.append(int(row["scope_index"]))
            relative = _safe_relative_path(row["episode_relative_path"])
        except (KeyError, ValueError, FormalShardArchiveAuditError):
            reasons.append("archive_merge_cells_row_invalid")
            continue
        paths.append(relative)
    if indices != list(range(len(rows))):
        reasons.append("archive_merge_cells_scope_order_mismatch")
    if len(set(paths)) != len(paths):
        reasons.append("archive_merge_cells_episode_path_duplicate")
    return paths


def _read_checksum_file(
    path: Path,
    *,
    expected_names: set[str] | frozenset[str],
) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise FormalShardArchiveAuditError("checksum line malformed")
        digest, name = parts
        _require_digest(digest, "checksum")
        if name in entries or Path(name).name != name:
            raise FormalShardArchiveAuditError("checksum filename invalid")
        entries[name] = digest
    if set(entries) != set(expected_names):
        raise FormalShardArchiveAuditError("checksum entry set mismatch")
    return entries


def _require_regular_file_without_symlink(
    root: Path,
    path: Path,
    *,
    label: str,
) -> None:
    """Require a regular file whose in-root path contains no symlink."""

    root_path = Path(root).absolute()
    candidate = Path(path).absolute()
    try:
        relative = candidate.relative_to(root_path)
    except ValueError as exc:
        raise FormalShardArchiveAuditError(f"{label} escapes its root") from exc
    current = root_path
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise FormalShardArchiveAuditError(f"{label} uses a symbolic link")
    if not candidate.is_file():
        raise FormalShardArchiveAuditError(f"{label} is not a regular file")


def _path_contains_symlink(path: Path) -> bool:
    candidate = Path(path).absolute()
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _validate_provenance_list(
    payload: Mapping[str, Any],
    *,
    field: str,
    validator: Callable[[str], bool],
) -> list[str]:
    values = payload.get(field)
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) or not validator(value) for value in values)
        or len(set(values)) != len(values)
    ):
        return [f"archive_d6_binding_{field}_invalid"]
    return []


def _safe_relative_path(value: str) -> str:
    if "\\" in value:
        raise FormalShardArchiveAuditError("unsafe path separator")
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise FormalShardArchiveAuditError("unsafe relative path")
    return value


def _plan_scope_cells(plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    scope = plan.get("scope")
    cells = scope.get("cells") if isinstance(scope, Mapping) else None
    return list(cells) if isinstance(cells, list) else []


def _plan_shard_descriptors(plan: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    sharding = plan.get("sharding")
    rows = sharding.get("shards") if isinstance(sharding, Mapping) else None
    if not isinstance(rows, list):
        return {}
    return {
        int(row["shard_index"]): row
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("shard_index"), int)
    }


def _archive_failure(
    reason: str,
    *,
    expected_shard_count: int,
    sidecar_files: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "schema_version": FORMAL_SHARD_ARCHIVE_AUDIT_SCHEMA_VERSION,
        "verified": False,
        "storage_mode": FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
        "expected_shard_count": expected_shard_count,
        "verified_archive_count": 0,
        "low_level_audited_cell_count": 0,
        "sidecar_files": sorted(str(value) for value in sidecar_files),
        "peak_staged_shard_count": 0,
        "source_deletion_performed": False,
        "archive_deletion_performed": False,
        "source": {},
        "execution_plan": {},
        "execution_progress": {},
        "archives": [],
        "cells": [],
        "failure_reasons": [reason],
    }


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FormalShardArchiveAuditError(f"{label} missing")
    return value


def _require_digest(value: Any, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in _HEX for c in value):
        raise FormalShardArchiveAuditError(f"{label} SHA-256 invalid")


def _is_hex_digest(value: str, length: int) -> bool:
    return (
        len(value) == length
        and bool(value)
        and all(character in _HEX for character in value)
    )


def _is_prefixed_sha256(value: str) -> bool:
    prefix = "sha256:"
    return value.startswith(prefix) and _is_hex_digest(value[len(prefix) :], 64)


def _digest_json(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FormalShardArchiveAuditError(f"JSON object required:{path}")
    return payload


__all__ = [
    "FORMAL_SHARD_ARCHIVE_AUDIT_SCHEMA_VERSION",
    "FormalShardArchiveAuditError",
    "audit_archive_merge_bundle",
    "audit_formal_shard_archives",
    "verify_and_restore_formal_shard_archive",
]
