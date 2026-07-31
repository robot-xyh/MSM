"""Deterministic, verified compression for completed experiment shards."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile
from typing import Any, Mapping, Sequence

from research_modules.scalable_3d_simulation.artifact_archive import (
    ARTIFACT_INVENTORY_SCHEMA,
    ArtifactArchiveError,
    inventory_artifact_tree,
)
from research_modules.scalable_3d_simulation.experiment_matrix import (
    EXPERIMENT_MATRIX_SCHEMA_VERSION,
    PAIRED_SENSOR_RANDOM_SCHEDULE_VERSION,
)
from research_modules.scalable_3d_simulation.experiment_matrix_sharding import (
    EXPERIMENT_MATRIX_SHARD_STORAGE_VALIDATION_SCHEMA,
    FORMAL_R0_DEFAULT_MINIMUM_FREE_BYTES,
    collect_experiment_matrix_shard_merge_fragment,
    load_experiment_matrix_execution_plan,
    validate_experiment_matrix_execution_source,
    validate_experiment_matrix_shard_for_storage,
)


FORMAL_SHARD_ARCHIVE_MANIFEST_SCHEMA = (
    "scalable3d-formal-shard-archive-manifest-v1"
)
FORMAL_SHARD_ARCHIVE_VERIFICATION_SCHEMA = (
    "scalable3d-formal-shard-archive-verification-v1"
)
FORMAL_SHARD_ARCHIVE_FORMAT = "deterministic-pax-tar-zstd-v1"
FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME = "shard_payload.tar.zst"
FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME = "shard_archive_manifest.json"
FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME = "SHA256SUMS"
FORMAL_SHARD_ARCHIVE_SCOPE_MERGE_SCHEMA = (
    "scalable3d-formal-shard-archive-scope-merge-v1"
)
FORMAL_SHARD_ARCHIVE_D6_BINDING_SCHEMA = (
    "scalable3d-formal-shard-archive-d6-binding-v1"
)
FORMAL_SHARD_ARCHIVE_STORAGE_MODE = "verified_formal_shard_archives_v1"
DEFAULT_ZSTD_COMPRESSION_LEVEL = 10
_ARCHIVE_CAPACITY_OVERHEAD_BYTES = 16 * 1024**2
_HEX64 = frozenset("0123456789abcdef")


class FormalShardArchiveError(ArtifactArchiveError):
    """Raised when a compressed shard cannot be proven safe and complete."""


def create_verified_formal_shard_archive(
    *,
    execution_plan_path: str | Path,
    shard_index: int,
    destination: str | Path,
    created_at_utc: str | None = None,
    compression_level: int = DEFAULT_ZSTD_COMPRESSION_LEVEL,
    minimum_free_bytes: int = FORMAL_R0_DEFAULT_MINIMUM_FREE_BYTES,
) -> dict[str, Any]:
    """Compress one complete canonical shard without deleting its source."""

    plan_path = _require_file(execution_plan_path, label="execution plan")
    binding = _storage_binding(
        validate_experiment_matrix_shard_for_storage(
            execution_plan_path=plan_path,
            shard_index=shard_index,
        )
    )
    source = Path(str(binding.pop("shard_dir"))).resolve()
    archive_root = Path(destination).expanduser().resolve()
    if archive_root.exists():
        raise FileExistsError(
            f"formal shard archive already exists: {archive_root}"
        )
    if _is_relative_to(archive_root, source):
        raise FormalShardArchiveError(
            "formal shard archive must be outside the source shard"
        )
    level = _compression_level(compression_level)
    free_floor = _minimum_free_bytes(minimum_free_bytes)

    archive_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_root.parent / f".{archive_root.name}.partial"
    if temporary.exists():
        raise FormalShardArchiveError(
            f"partial formal shard archive already exists: {temporary}"
        )

    initial_inventory = inventory_artifact_tree(source)
    _require_archive_capacity(
        archive_root.parent,
        initial_inventory,
        minimum_free_bytes=free_floor,
    )
    zstd_path, zstd_version = _zstd_runtime()

    try:
        temporary.mkdir()
        payload_path = temporary / FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME
        _create_deterministic_tar_zst(
            source=source,
            inventory=initial_inventory,
            destination=payload_path,
            zstd_path=zstd_path,
            compression_level=level,
        )
        payload_sha256 = _sha256_file(payload_path)
        payload_size_bytes = int(payload_path.stat().st_size)
        _verify_tar_zst_payload(
            payload_path,
            initial_inventory,
            zstd_path=zstd_path,
        )

        final_inventory = inventory_artifact_tree(source)
        if final_inventory != initial_inventory:
            raise FormalShardArchiveError(
                "formal shard source changed while it was being compressed"
            )
        final_binding = _storage_binding(
            validate_experiment_matrix_shard_for_storage(
                execution_plan_path=plan_path,
                shard_index=shard_index,
            )
        )
        final_binding.pop("shard_dir")
        if final_binding != binding:
            raise FormalShardArchiveError(
                "formal shard binding changed while it was being compressed"
            )

        manifest = {
            "schema_version": FORMAL_SHARD_ARCHIVE_MANIFEST_SCHEMA,
            "created_at_utc": _timestamp(created_at_utc),
            "archive_format": FORMAL_SHARD_ARCHIVE_FORMAT,
            "compression": {
                "algorithm": "zstd",
                "level": level,
                "threads": 1,
                "runtime": zstd_version,
            },
            "source": {
                "name": source.name,
                "canonical_relative_path": (
                    f"shards/{binding['shard_id']}"
                ),
                "preserved_at_creation": True,
                "deletion_performed_by_tool": False,
            },
            "binding": binding,
            "inventory": initial_inventory,
            "payload": {
                "filename": FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME,
                "size_bytes": payload_size_bytes,
                "sha256": payload_sha256,
            },
        }
        manifest_path = (
            temporary / FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME
        )
        _write_json_atomic(manifest_path, manifest)
        checksum_path = (
            temporary / FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME
        )
        _write_checksum_file(
            checksum_path,
            {
                FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME: _sha256_file(
                    manifest_path
                ),
                FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME: payload_sha256,
            },
        )
        verification = verify_formal_shard_archive(
            temporary,
            execution_plan_path=plan_path,
            shard_index=shard_index,
            source=source,
        )
        if shutil.disk_usage(archive_root.parent).free < free_floor:
            raise FormalShardArchiveError(
                "formal shard archive would cross the minimum free-space floor"
            )
        os.replace(temporary, archive_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        **verification,
        "archive": str(archive_root),
        "manifest": str(
            archive_root / FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME
        ),
        "payload": str(
            archive_root / FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME
        ),
        "checksums": str(
            archive_root / FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME
        ),
    }


def verify_formal_shard_archive(
    archive: str | Path,
    *,
    execution_plan_path: str | Path,
    shard_index: int,
    source: str | Path | None = None,
) -> dict[str, Any]:
    """Verify archive bytes, file inventory, binding, and optional source."""

    archive_root = _require_directory(
        archive,
        label="formal shard archive",
    )
    plan_path = _require_file(execution_plan_path, label="execution plan")
    expected_entries = {
        FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME,
        FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME,
        FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME,
    }
    actual_entries = {entry.name for entry in archive_root.iterdir()}
    if actual_entries != expected_entries:
        raise FormalShardArchiveError(
            "formal shard archive root entries do not match the contract"
        )

    payload_path = archive_root / FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME
    manifest_path = archive_root / FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME
    checksum_path = archive_root / FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME
    checksums = _read_checksum_file(checksum_path, expected_entries - {
        FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME
    })
    for filename, expected_sha256 in checksums.items():
        actual_sha256 = _sha256_file(archive_root / filename)
        if actual_sha256 != expected_sha256:
            raise FormalShardArchiveError(
                f"formal shard archive SHA-256 mismatch: {filename}"
            )

    manifest = _read_json_object(manifest_path)
    if manifest.get("schema_version") != FORMAL_SHARD_ARCHIVE_MANIFEST_SCHEMA:
        raise FormalShardArchiveError(
            "unsupported formal shard archive manifest schema"
        )
    if manifest.get("archive_format") != FORMAL_SHARD_ARCHIVE_FORMAT:
        raise FormalShardArchiveError(
            "unsupported formal shard archive payload format"
        )
    expected_binding = _expected_binding(
        plan_path,
        shard_index=shard_index,
    )
    source_contract = manifest.get("source")
    if not isinstance(source_contract, Mapping):
        raise FormalShardArchiveError(
            "formal shard archive source contract is missing"
        )
    if source_contract.get("preserved_at_creation") is not True:
        raise FormalShardArchiveError(
            "formal shard archive must preserve its source at creation"
        )
    if source_contract.get("deletion_performed_by_tool") is not False:
        raise FormalShardArchiveError(
            "formal shard archive tool must not claim source deletion"
        )
    if source_contract.get("name") != expected_binding["shard_id"]:
        raise FormalShardArchiveError(
            "formal shard archive source name does not match its shard"
        )
    if (
        source_contract.get("canonical_relative_path")
        != f"shards/{expected_binding['shard_id']}"
    ):
        raise FormalShardArchiveError(
            "formal shard archive canonical source path mismatch"
        )

    frozen_binding = manifest.get("binding")
    if not isinstance(frozen_binding, Mapping):
        raise FormalShardArchiveError(
            "formal shard archive execution binding is missing"
        )
    for name, expected_value in expected_binding.items():
        if frozen_binding.get(name) != expected_value:
            raise FormalShardArchiveError(
                f"formal shard archive binding mismatch: {name}"
            )

    frozen_inventory = manifest.get("inventory")
    if not isinstance(frozen_inventory, Mapping):
        raise FormalShardArchiveError(
            "formal shard archive inventory is missing"
        )
    _validate_inventory_contract(frozen_inventory)
    _validate_frozen_binding_contract(
        frozen_binding,
        frozen_inventory,
    )
    payload_contract = manifest.get("payload")
    if not isinstance(payload_contract, Mapping):
        raise FormalShardArchiveError(
            "formal shard archive payload contract is missing"
        )
    if (
        payload_contract.get("filename")
        != FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME
    ):
        raise FormalShardArchiveError(
            "formal shard archive payload filename mismatch"
        )
    if int(payload_contract.get("size_bytes", -1)) != payload_path.stat().st_size:
        raise FormalShardArchiveError(
            "formal shard archive payload size mismatch"
        )
    if payload_contract.get("sha256") != checksums[
        FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME
    ]:
        raise FormalShardArchiveError(
            "formal shard archive payload digest contract mismatch"
        )
    compression = manifest.get("compression")
    if (
        not isinstance(compression, Mapping)
        or compression.get("algorithm") != "zstd"
        or int(compression.get("threads", -1)) != 1
        or not isinstance(compression.get("runtime"), str)
        or not str(compression["runtime"]).strip()
    ):
        raise FormalShardArchiveError(
            "formal shard archive compression contract mismatch"
        )
    _compression_level(int(compression.get("level", 0)))

    zstd_path, _ = _zstd_runtime()
    _verify_tar_zst_payload(
        payload_path,
        dict(frozen_inventory),
        zstd_path=zstd_path,
    )

    source_verified = False
    if source is not None:
        source_root = _require_directory(
            source,
            label="formal shard source",
        )
        if inventory_artifact_tree(source_root) != dict(frozen_inventory):
            raise FormalShardArchiveError(
                "formal shard source no longer matches the archive"
            )
        source_binding = _storage_binding(
            validate_experiment_matrix_shard_for_storage(
                execution_plan_path=plan_path,
                shard_index=shard_index,
            )
        )
        canonical_source = Path(
            str(source_binding.pop("shard_dir"))
        ).resolve()
        if source_root != canonical_source:
            raise FormalShardArchiveError(
                "formal shard source is not the canonical plan shard"
            )
        if source_binding != dict(frozen_binding):
            raise FormalShardArchiveError(
                "formal shard source binding no longer matches the archive"
            )
        source_verified = True

    inventory = dict(frozen_inventory)
    return {
        "schema_version": FORMAL_SHARD_ARCHIVE_VERIFICATION_SCHEMA,
        "status": "verified",
        "archive_sha256": checksums[
            FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME
        ],
        "archive_size_bytes": int(payload_path.stat().st_size),
        "payload_tree_sha256": inventory["tree_sha256"],
        "file_count": int(inventory["file_count"]),
        "total_size_bytes": int(inventory["total_size_bytes"]),
        "execution_plan_sha256": frozen_binding[
            "execution_plan_sha256"
        ],
        "shard_index": int(frozen_binding["shard_index"]),
        "shard_id": frozen_binding["shard_id"],
        "source_verified": source_verified,
        "source_deletion_eligible": source_verified,
        "source_deletion_performed": False,
    }


def restore_verified_formal_shard_archive(
    archive: str | Path,
    *,
    execution_plan_path: str | Path,
    shard_index: int,
    minimum_free_bytes: int = 0,
) -> dict[str, Any]:
    """Restore one archive to its canonical shard path and revalidate it."""

    archive_root = _require_directory(
        archive,
        label="formal shard archive",
    )
    plan_path = _require_file(execution_plan_path, label="execution plan")
    verification = verify_formal_shard_archive(
        archive_root,
        execution_plan_path=plan_path,
        shard_index=shard_index,
    )
    manifest = _read_json_object(
        archive_root / FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME
    )
    binding = dict(manifest["binding"])
    destination = (
        plan_path.parent / "shards" / str(binding["shard_id"])
    ).resolve()
    if destination.exists():
        raise FileExistsError(
            f"formal shard restore destination already exists: {destination}"
        )
    free_floor = _minimum_free_bytes(minimum_free_bytes)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _require_restore_capacity(
        destination.parent,
        manifest["inventory"],
        minimum_free_bytes=free_floor,
    )
    temporary = destination.parent / f".{destination.name}.restore-partial"
    if temporary.exists():
        raise FormalShardArchiveError(
            f"partial formal shard restore already exists: {temporary}"
        )

    zstd_path, _ = _zstd_runtime()
    published = False
    try:
        temporary.mkdir()
        _verify_tar_zst_payload(
            archive_root / FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME,
            manifest["inventory"],
            zstd_path=zstd_path,
            restore_root=temporary,
        )
        restored_inventory = inventory_artifact_tree(temporary)
        if restored_inventory != manifest["inventory"]:
            raise FormalShardArchiveError(
                "restored formal shard inventory does not match the archive"
            )
        os.replace(temporary, destination)
        published = True
        restored_binding = _storage_binding(
            validate_experiment_matrix_shard_for_storage(
                execution_plan_path=plan_path,
                shard_index=shard_index,
            )
        )
        restored_binding.pop("shard_dir")
        if restored_binding != binding:
            raise FormalShardArchiveError(
                "restored formal shard binding does not match the archive"
            )
        if shutil.disk_usage(destination.parent).free < free_floor:
            raise FormalShardArchiveError(
                "formal shard restore crossed the requested free-space floor"
            )
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if published:
            shutil.rmtree(destination, ignore_errors=True)
        raise

    return {
        **verification,
        "status": "restored_and_verified",
        "archive": str(archive_root),
        "archive_preserved": archive_root.is_dir(),
        "restored_shard": str(destination),
        "restored_tree_sha256": manifest["inventory"]["tree_sha256"],
        "source_deletion_performed": False,
    }


def merge_verified_formal_shard_archives(
    *,
    repository_root: str | Path,
    execution_plan_path: str | Path,
    archive_root: str | Path,
    output_dir: str | Path | None = None,
    staging_root: str | Path | None = None,
    write_d6_report: bool = False,
    minimum_free_bytes: int = FORMAL_R0_DEFAULT_MINIMUM_FREE_BYTES,
) -> dict[str, Any]:
    """Merge a complete scope while restoring at most one shard at a time.

    Every archive is fully verified, restored into an isolated temporary
    execution root, validated through the ordinary shard merge contract, and
    removed before the next shard is staged.  Canonical shards and archives
    are never deleted or modified by this function.
    """

    plan_path = _require_file(execution_plan_path, label="execution plan")
    execution = validate_experiment_matrix_execution_source(
        root=repository_root,
        execution_plan_path=plan_path,
    )
    archives = _require_directory(
        archive_root,
        label="formal shard archive root",
    )
    descriptors = list(execution["sharding"]["shards"])
    expected_archive_names = {
        str(descriptor["shard_id"]) for descriptor in descriptors
    }
    archive_root_entries = tuple(archives.iterdir())
    symbolic_links = sorted(
        entry.name for entry in archive_root_entries if entry.is_symlink()
    )
    if symbolic_links:
        raise FormalShardArchiveError(
            "formal shard archive root contains symbolic links: "
            f"{symbolic_links[:3]}"
        )
    actual_archive_names = {
        entry.name for entry in archive_root_entries if entry.is_dir()
    }
    if actual_archive_names != expected_archive_names:
        missing = sorted(expected_archive_names - actual_archive_names)
        unexpected = sorted(actual_archive_names - expected_archive_names)
        raise FormalShardArchiveError(
            "formal shard archive directory set does not match the execution "
            "plan: "
            f"missing={missing[:3]}, unexpected={unexpected[:3]}"
        )

    destination = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else plan_path.parent / "merged_scope_from_archives"
    )
    if destination.exists():
        raise FileExistsError(
            f"formal archive merge output already exists: {destination}"
        )
    if _is_relative_to(destination, archives):
        raise FormalShardArchiveError(
            "formal archive merge output must be outside the archive root"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.parent / f".{destination.name}.partial"
    if partial.exists():
        raise FormalShardArchiveError(
            f"partial formal archive merge already exists: {partial}"
        )

    if staging_root is None:
        staging_parent = destination.parent
    else:
        unresolved_staging = Path(staging_root).expanduser()
        if unresolved_staging.is_symlink():
            raise FormalShardArchiveError(
                "formal archive merge staging root must not be a symbolic link"
            )
        staging_parent = unresolved_staging.resolve()
    if _is_relative_to(staging_parent, archives):
        raise FormalShardArchiveError(
            "formal archive merge staging root must be outside the archive root"
        )
    if _is_relative_to(staging_parent, destination) or _is_relative_to(
        staging_parent,
        partial,
    ):
        raise FormalShardArchiveError(
            "formal archive merge staging root must not overlap the output "
            "or its partial publication directory"
        )
    staging_parent.mkdir(parents=True, exist_ok=True)
    free_floor = _minimum_free_bytes(minimum_free_bytes)

    fragments: list[dict[str, Any]] = []
    archive_bindings: list[dict[str, Any]] = []
    d6_rows_by_scope: list[tuple[int, dict[str, Any]]] = []
    zstd_path, _ = _zstd_runtime()
    try:
        partial.mkdir()
        for descriptor in descriptors:
            index = int(descriptor["shard_index"])
            shard_id = str(descriptor["shard_id"])
            archive = _require_directory(
                archives / shard_id,
                label=f"formal shard archive {shard_id}",
            )
            verification = verify_formal_shard_archive(
                archive,
                execution_plan_path=plan_path,
                shard_index=index,
            )
            archive_manifest = _read_json_object(
                archive / FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME
            )
            _require_restore_capacity(
                staging_parent,
                archive_manifest["inventory"],
                minimum_free_bytes=free_floor,
            )
            with tempfile.TemporaryDirectory(
                prefix=f".{shard_id}.archive-merge-",
                dir=staging_parent,
            ) as temporary_name:
                staged_execution_root = Path(temporary_name).resolve()
                staged_shard = (
                    staged_execution_root / "shards" / shard_id
                )
                staged_shard.mkdir(parents=True)
                _verify_tar_zst_payload(
                    archive / FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME,
                    archive_manifest["inventory"],
                    zstd_path=zstd_path,
                    restore_root=staged_shard,
                )
                if inventory_artifact_tree(staged_shard) != archive_manifest[
                    "inventory"
                ]:
                    raise FormalShardArchiveError(
                        "staged formal shard inventory does not match the archive"
                    )
                fragment = collect_experiment_matrix_shard_merge_fragment(
                    execution_plan_path=plan_path,
                    shard_index=index,
                    execution_root=staged_execution_root,
                )
                _validate_archive_merge_fragment_binding(
                    fragment,
                    archive_manifest,
                )
                if write_d6_report:
                    d6_rows_by_scope.extend(
                        _evaluate_staged_fragment_for_d6(
                            fragment,
                            staged_execution_root=staged_execution_root,
                            canonical_execution_root=plan_path.parent,
                        )
                    )
                fragments.append(fragment)
            archive_bindings.append(
                _archive_merge_binding(
                    archive,
                    verification=verification,
                    archive_manifest=archive_manifest,
                    shard_digest=fragment["shard_digest"],
                )
            )

        output_paths = _write_archive_scope_merge_bundle(
            partial,
            execution=execution,
            fragments=fragments,
            archive_bindings=archive_bindings,
            d6_rows_by_scope=(
                d6_rows_by_scope if write_d6_report else None
            ),
        )
        if shutil.disk_usage(destination.parent).free < free_floor:
            raise FormalShardArchiveError(
                "formal archive merge crossed the requested free-space floor"
            )
        relative_outputs = {
            name: path.relative_to(partial)
            for name, path in output_paths.items()
        }
        os.replace(partial, destination)
    except Exception:
        shutil.rmtree(partial, ignore_errors=True)
        raise

    return {
        "schema_version": FORMAL_SHARD_ARCHIVE_SCOPE_MERGE_SCHEMA,
        "status": "verified_archive_scope_merged",
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "shard_count": len(descriptors),
        "scope_cell_count": int(execution["scope"]["cell_count"]),
        "peak_restored_shard_count": 1,
        "archive_source_preserved": True,
        "canonical_source_deletion_performed": False,
        "output": str(destination),
        "paths": {
            name: str(destination / relative)
            for name, relative in relative_outputs.items()
        },
    }


def _validate_archive_merge_fragment_binding(
    fragment: Mapping[str, Any],
    archive_manifest: Mapping[str, Any],
) -> None:
    binding = archive_manifest.get("binding")
    if not isinstance(binding, Mapping):
        raise FormalShardArchiveError(
            "formal shard archive binding is missing during merge"
        )
    digest = fragment.get("shard_digest")
    if not isinstance(digest, Mapping):
        raise FormalShardArchiveError(
            "formal shard merge fragment digest is missing"
        )
    for field in (
        "shard_index",
        "shard_id",
        "shard_plan_sha256",
        "progress_sha256",
        "checkpoint_sha256",
    ):
        if digest.get(field) != binding.get(field):
            raise FormalShardArchiveError(
                f"staged shard merge fragment binding mismatch: {field}"
            )
    if digest.get("cell_count") != binding.get("completed_cell_count"):
        raise FormalShardArchiveError(
            "staged shard merge fragment binding mismatch: cell_count"
        )


def _evaluate_staged_fragment_for_d6(
    fragment: Mapping[str, Any],
    *,
    staged_execution_root: Path,
    canonical_execution_root: Path,
) -> list[tuple[int, dict[str, Any]]]:
    from research_modules.d6_evaluation_metrics.d6_evaluation_metrics.scalable_3d_offline import (
        evaluate_scalable_3d_episode,
    )

    merged_rows = fragment.get("merged_rows")
    if not isinstance(merged_rows, list):
        raise FormalShardArchiveError(
            "formal shard merge fragment rows are missing"
        )
    evaluated: list[tuple[int, dict[str, Any]]] = []
    for merged_row in merged_rows:
        relative = str(merged_row["episode_relative_path"])
        staged_episode = (staged_execution_root / relative).resolve()
        row = evaluate_scalable_3d_episode(staged_episode)
        row["episode_dir"] = str(
            (canonical_execution_root / relative).resolve()
        )
        evaluated.append((int(merged_row["scope_index"]), row))
    return evaluated


def _archive_merge_binding(
    archive: Path,
    *,
    verification: Mapping[str, Any],
    archive_manifest: Mapping[str, Any],
    shard_digest: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **dict(shard_digest),
        "archive": {
            "directory_name": archive.name,
            "archive_format": archive_manifest["archive_format"],
            "archive_manifest_sha256": _sha256_file(
                archive / FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME
            ),
            "archive_checksum_file_sha256": _sha256_file(
                archive / FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME
            ),
            "payload_sha256": verification["archive_sha256"],
            "payload_tree_sha256": verification[
                "payload_tree_sha256"
            ],
            "archive_size_bytes": int(verification["archive_size_bytes"]),
            "file_count": int(verification["file_count"]),
            "total_size_bytes": int(verification["total_size_bytes"]),
        },
    }


def _write_archive_scope_merge_bundle(
    destination: Path,
    *,
    execution: Mapping[str, Any],
    fragments: Sequence[Mapping[str, Any]],
    archive_bindings: Sequence[Mapping[str, Any]],
    d6_rows_by_scope: Sequence[tuple[int, Mapping[str, Any]]] | None,
) -> dict[str, Path]:
    expected_scope = list(execution["scope"]["cells"])
    progress = sorted(
        [row for fragment in fragments for row in fragment["progress"]],
        key=lambda row: int(row["scope_index"]),
    )
    if [row["cell_id"] for row in progress] != [
        cell["cell_id"] for cell in expected_scope
    ]:
        raise FormalShardArchiveError(
            "archive merge cells are missing, duplicated, or out of scope"
        )
    if len({row["cell_id"] for row in progress}) != len(expected_scope):
        raise FormalShardArchiveError(
            "archive merge contains duplicate cells"
        )
    rows = sorted(
        [row for fragment in fragments for row in fragment["merged_rows"]],
        key=lambda row: int(row["scope_index"]),
    )
    if [int(row["scope_index"]) for row in rows] != list(
        range(len(expected_scope))
    ):
        raise FormalShardArchiveError(
            "archive merge rows are not in canonical scope order"
        )
    episode_relative_paths = [
        str(row["episode_relative_path"]) for row in rows
    ]
    parent_count = int(execution["parent"]["full_cell_count"])
    scope_count = int(execution["scope"]["cell_count"])
    parent_formal = bool(execution["parent"]["formal"])
    full_matrix_complete = scope_count == parent_count
    manifest = {
        "schema_version": FORMAL_SHARD_ARCHIVE_SCOPE_MERGE_SCHEMA,
        "storage_mode": FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
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
        "scope_completed_cell_count": len(rows),
        "scope_complete": len(rows) == scope_count,
        "formal_scope_complete": parent_formal and len(rows) == scope_count,
        "full_matrix_complete": full_matrix_complete,
        "formal_matrix_complete": parent_formal and full_matrix_complete,
        "legacy_full_matrix_manifest_written": full_matrix_complete,
        "shard_strategy": execution["sharding"]["strategy"],
        "shard_count": execution["sharding"]["shard_count"],
        "shards": [dict(value) for value in archive_bindings],
        "paired_random_schedule_version": (
            PAIRED_SENSOR_RANDOM_SCHEDULE_VERSION
        ),
        "canonical_episode_directories_materialized": False,
        "archive_set_complete": len(archive_bindings)
        == int(execution["sharding"]["shard_count"]),
        "peak_restored_shard_count": 1,
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
    _write_rows_csv_atomic(cells_path, rows)
    _write_json_atomic(
        episode_dirs_path,
        {
            "schema_version": FORMAL_SHARD_ARCHIVE_SCOPE_MERGE_SCHEMA,
            "storage_mode": FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
            "execution_plan_sha256": execution["execution_plan_sha256"],
            "episode_count": len(episode_relative_paths),
            "canonical_directories_materialized": False,
            "paths_relative_to_execution_root": episode_relative_paths,
        },
    )
    paths: dict[str, Path] = {
        "cells": cells_path,
        "episode_dirs": episode_dirs_path,
    }
    if d6_rows_by_scope is not None:
        ordered_d6 = sorted(d6_rows_by_scope, key=lambda item: item[0])
        if [index for index, _ in ordered_d6] != list(range(scope_count)):
            raise FormalShardArchiveError(
                "archive merge D6 rows are not in canonical scope order"
            )
        from research_modules.d6_evaluation_metrics.d6_evaluation_metrics.scalable_3d_offline import (
            Scalable3DOfflineReportGenerator,
        )

        report_paths = (
            Scalable3DOfflineReportGenerator().write_report_bundle_from_rows(
                destination / "d6_evaluation",
                rows=tuple(dict(row) for _, row in ordered_d6),
            )
        )
        d6_binding_path = destination / "archive_d6_evaluation_binding.json"
        _write_archive_d6_binding(
            d6_binding_path,
            execution=execution,
            ordered_rows=ordered_d6,
            report_paths=report_paths,
            destination=destination,
        )
        manifest["d6_evaluation_generated"] = True
        manifest["d6_evaluation_binding_sha256"] = _sha256_file(
            d6_binding_path
        )
        paths["d6_binding"] = d6_binding_path
        paths.update(
            {f"d6_{name}": path for name, path in report_paths.items()}
        )
    else:
        manifest["d6_evaluation_generated"] = False
        manifest["d6_evaluation_binding_sha256"] = None

    _write_json_atomic(manifest_path, manifest)
    paths["manifest"] = manifest_path
    if full_matrix_complete:
        legacy_path = destination / "experiment_matrix_manifest.json"
        _write_json_atomic(
            legacy_path,
            {
                "schema_version": EXPERIMENT_MATRIX_SCHEMA_VERSION,
                "git_commit": execution["source"]["git_commit"],
                "repository_dirty": execution["source"][
                    "repository_dirty"
                ],
                "formal": parent_formal,
                "variants": execution["parent"]["plan"]["variants"],
                "scenarios": execution["parent"]["plan"]["scenarios"],
                "scales": execution["parent"]["plan"]["scales"],
                "seeds": execution["parent"]["plan"]["seeds"],
                "training_seed_registry_present": (
                    execution["parent"]["plan"]["training_seeds"]
                    is not None
                ),
                "cell_count": parent_count,
                "completed_cell_count": len(rows),
                "paired_random_schedule_version": manifest[
                    "paired_random_schedule_version"
                ],
                "resumable_execution_plan_sha256": execution[
                    "execution_plan_sha256"
                ],
            },
        )
        paths["legacy_full_manifest"] = legacy_path

    checksum_path = destination / "SHA256SUMS"
    _write_checksum_file(
        checksum_path,
        {
            path.name: _sha256_file(path)
            for name, path in paths.items()
            if not name.startswith("d6_") or name == "d6_binding"
        },
    )
    paths["checksums"] = checksum_path
    return paths


def _write_archive_d6_binding(
    path: Path,
    *,
    execution: Mapping[str, Any],
    ordered_rows: Sequence[tuple[int, Mapping[str, Any]]],
    report_paths: Mapping[str, Path],
    destination: Path,
) -> None:
    evaluator_schema_versions = sorted(
        {
            str(row.get("d6_evaluator_schema_version"))
            for _, row in ordered_rows
        }
    )
    evaluator_git_commits = sorted(
        {
            str(row.get("d6_evaluator_git_commit"))
            for _, row in ordered_rows
        }
    )
    evaluator_dirty_values = sorted(
        {
            bool(row.get("d6_evaluator_repository_dirty"))
            for _, row in ordered_rows
        }
    )
    evaluator_tree_sha256s = sorted(
        {
            str(row.get("d6_evaluator_source_tree_sha256"))
            for _, row in ordered_rows
        }
    )
    artifacts = {}
    for name, artifact in sorted(report_paths.items()):
        relative = artifact.resolve().relative_to(destination.resolve()).as_posix()
        artifacts[name] = {
            "relative_path": relative,
            "size_bytes": int(artifact.stat().st_size),
            "sha256": _sha256_file(artifact),
        }
    _write_json_atomic(
        path,
        {
            "schema_version": FORMAL_SHARD_ARCHIVE_D6_BINDING_SCHEMA,
            "storage_mode": FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
            "execution_plan_sha256": execution["execution_plan_sha256"],
            "episode_count": len(ordered_rows),
            "scope_indices": [index for index, _ in ordered_rows],
            "evaluator_schema_versions": evaluator_schema_versions,
            "evaluator_git_commits": evaluator_git_commits,
            "evaluator_repository_dirty_values": evaluator_dirty_values,
            "evaluator_source_tree_sha256s": evaluator_tree_sha256s,
            "artifacts": artifacts,
        },
    )


def _create_deterministic_tar_zst(
    *,
    source: Path,
    inventory: Mapping[str, Any],
    destination: Path,
    zstd_path: str,
    compression_level: int,
) -> None:
    process = subprocess.Popen(
        [
            zstd_path,
            f"-{compression_level}",
            "-T1",
            "--no-progress",
            "--quiet",
            "-o",
            str(destination),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        if process.stdin is None or process.stderr is None:
            raise FormalShardArchiveError(
                "failed to open deterministic archive compression streams"
            )
        archive = tarfile.open(
            fileobj=process.stdin,
            mode="w|",
            format=tarfile.PAX_FORMAT,
        )
        try:
            for record in inventory["files"]:
                relative = str(record["relative_path"])
                source_file = source / Path(relative)
                info = tarfile.TarInfo(name=relative)
                info.size = int(record["size_bytes"])
                info.mtime = 0
                info.mode = 0o644
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.pax_headers = {}
                with source_file.open("rb") as stream:
                    archive.addfile(info, fileobj=stream)
        finally:
            archive.close()
            if not process.stdin.closed:
                process.stdin.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace")
        return_code = process.wait()
        if return_code != 0:
            raise FormalShardArchiveError(
                f"zstd compression failed ({return_code}): {stderr.strip()}"
            )
    except Exception:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        process.terminate()
        process.wait()
        raise


def _verify_tar_zst_payload(
    archive: Path,
    inventory: Mapping[str, Any],
    *,
    zstd_path: str,
    restore_root: Path | None = None,
) -> None:
    expected = {
        str(record["relative_path"]): dict(record)
        for record in inventory["files"]
    }
    if len(expected) != int(inventory["file_count"]):
        raise FormalShardArchiveError(
            "formal shard inventory contains duplicate file paths"
        )
    seen: set[str] = set()
    process = subprocess.Popen(
        [zstd_path, "-dc", "--quiet", str(archive)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        if process.stdout is None or process.stderr is None:
            raise FormalShardArchiveError(
                "failed to open formal shard decompression streams"
            )
        stream = tarfile.open(fileobj=process.stdout, mode="r|")
        try:
            for member in stream:
                relative = _safe_member_path(member)
                if relative in seen:
                    raise FormalShardArchiveError(
                        f"duplicate formal shard archive member: {relative}"
                    )
                if relative not in expected:
                    raise FormalShardArchiveError(
                        f"unexpected formal shard archive member: {relative}"
                    )
                seen.add(relative)
                record = expected[relative]
                if int(member.size) != int(record["size_bytes"]):
                    raise FormalShardArchiveError(
                        f"formal shard archive member size mismatch: {relative}"
                    )
                payload = stream.extractfile(member)
                if payload is None:
                    raise FormalShardArchiveError(
                        f"formal shard archive member is unreadable: {relative}"
                    )
                digest = hashlib.sha256()
                output = None
                try:
                    if restore_root is not None:
                        destination = restore_root / Path(relative)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        output = destination.open("xb")
                    while block := payload.read(1024 * 1024):
                        digest.update(block)
                        if output is not None:
                            output.write(block)
                finally:
                    payload.close()
                    if output is not None:
                        output.close()
                if digest.hexdigest() != record["sha256"]:
                    raise FormalShardArchiveError(
                        f"formal shard archive member digest mismatch: {relative}"
                    )
        finally:
            stream.close()
            process.stdout.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace")
        return_code = process.wait()
        if return_code != 0:
            raise FormalShardArchiveError(
                f"zstd decompression failed ({return_code}): {stderr.strip()}"
            )
    except Exception:
        if process.stdout is not None and not process.stdout.closed:
            process.stdout.close()
        process.terminate()
        process.wait()
        raise
    if seen != set(expected):
        missing = sorted(set(expected) - seen)
        raise FormalShardArchiveError(
            f"formal shard archive members are missing: {missing[:3]}"
        )


def _safe_member_path(member: tarfile.TarInfo) -> str:
    if not member.isfile():
        raise FormalShardArchiveError(
            f"formal shard archive member is not a regular file: {member.name}"
        )
    name = member.name
    if "\\" in name:
        raise FormalShardArchiveError(
            f"formal shard archive member uses an unsafe separator: {name}"
        )
    relative = PurePosixPath(name)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.as_posix() != name
    ):
        raise FormalShardArchiveError(
            f"formal shard archive member path is unsafe: {name}"
        )
    if (
        member.uid != 0
        or member.gid != 0
        or int(member.mtime) != 0
        or member.mode != 0o644
    ):
        raise FormalShardArchiveError(
            f"formal shard archive member metadata is not deterministic: {name}"
        )
    return relative.as_posix()


def _validate_inventory_contract(inventory: Mapping[str, Any]) -> None:
    if inventory.get("schema_version") != ARTIFACT_INVENTORY_SCHEMA:
        raise FormalShardArchiveError(
            "formal shard archive inventory schema mismatch"
        )
    records = inventory.get("files")
    if not isinstance(records, list) or not records:
        raise FormalShardArchiveError(
            "formal shard archive inventory files are missing"
        )
    if int(inventory.get("file_count", -1)) != len(records):
        raise FormalShardArchiveError(
            "formal shard archive inventory file count mismatch"
        )
    digest = hashlib.sha256()
    total_size = 0
    previous_path: str | None = None
    for record in records:
        if not isinstance(record, Mapping):
            raise FormalShardArchiveError(
                "formal shard archive inventory record is invalid"
            )
        relative = str(record.get("relative_path", ""))
        if previous_path is not None and relative <= previous_path:
            raise FormalShardArchiveError(
                "formal shard archive inventory paths are not unique and sorted"
            )
        _safe_inventory_path(relative)
        previous_path = relative
        size = int(record.get("size_bytes", -1))
        if size < 0:
            raise FormalShardArchiveError(
                "formal shard archive inventory size is invalid"
            )
        sha256 = str(record.get("sha256", ""))
        _require_sha256(sha256, label="inventory file")
        total_size += size
        digest.update(f"{sha256}  {size}  {relative}\n".encode("utf-8"))
    if int(inventory.get("total_size_bytes", -1)) != total_size:
        raise FormalShardArchiveError(
            "formal shard archive inventory total size mismatch"
        )
    tree_sha256 = str(inventory.get("tree_sha256", ""))
    _require_sha256(tree_sha256, label="inventory tree")
    if tree_sha256 != digest.hexdigest():
        raise FormalShardArchiveError(
            "formal shard archive inventory tree digest mismatch"
        )


def _validate_frozen_binding_contract(
    binding: Mapping[str, Any],
    inventory: Mapping[str, Any],
) -> None:
    if (
        binding.get("storage_validation_schema")
        != EXPERIMENT_MATRIX_SHARD_STORAGE_VALIDATION_SCHEMA
        or binding.get("storage_validation_status") != "verified_complete"
    ):
        raise FormalShardArchiveError(
            "formal shard archive storage validation contract mismatch"
        )
    expected_count = int(binding.get("expected_cell_count", -1))
    completed_count = int(binding.get("completed_cell_count", -1))
    if expected_count <= 0 or completed_count != expected_count:
        raise FormalShardArchiveError(
            "formal shard archive is not bound to a complete shard"
        )
    for name in (
        "execution_plan_sha256",
        "execution_plan_file_sha256",
        "parent_plan_sha256",
        "descriptor_sha256",
        "cells_sha256",
        "shard_plan_sha256",
        "progress_sha256",
        "checkpoint_sha256",
    ):
        _require_sha256(str(binding.get(name, "")), label=f"binding {name}")
    source_commit = str(binding.get("source_git_commit", ""))
    if len(source_commit) != 40 or any(
        character not in _HEX64 for character in source_commit
    ):
        raise FormalShardArchiveError(
            "formal shard archive source commit is invalid"
        )

    records = {
        str(record["relative_path"]): record
        for record in inventory["files"]
    }
    for relative, binding_name in (
        ("shard_plan.json", "shard_plan_sha256"),
        ("progress.jsonl", "progress_sha256"),
        ("checkpoint.json", "checkpoint_sha256"),
    ):
        record = records.get(relative)
        if (
            not isinstance(record, Mapping)
            or record.get("sha256") != binding[binding_name]
        ):
            raise FormalShardArchiveError(
                f"formal shard archive binding does not match {relative}"
            )


def _safe_inventory_path(name: str) -> None:
    if "\\" in name:
        raise FormalShardArchiveError(
            f"formal shard archive inventory path is unsafe: {name}"
        )
    relative = PurePosixPath(name)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.as_posix() != name
    ):
        raise FormalShardArchiveError(
            f"formal shard archive inventory path is unsafe: {name}"
        )


def _require_sha256(value: str, *, label: str) -> None:
    if len(value) != 64 or any(character not in _HEX64 for character in value):
        raise FormalShardArchiveError(
            f"formal shard archive {label} SHA-256 is invalid"
        )


def _storage_binding(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "storage_validation_schema": payload["schema_version"],
        "storage_validation_status": payload["status"],
        "execution_plan_sha256": payload["execution_plan_sha256"],
        "execution_plan_file_sha256": payload[
            "execution_plan_file_sha256"
        ],
        "parent_plan_sha256": payload["parent_plan_sha256"],
        "source_git_commit": payload["source_git_commit"],
        "shard_index": int(payload["shard_index"]),
        "shard_id": payload["shard_id"],
        "expected_cell_count": int(payload["expected_cell_count"]),
        "completed_cell_count": int(payload["completed_cell_count"]),
        "descriptor_sha256": payload["descriptor_sha256"],
        "cells_sha256": payload["cells_sha256"],
        "shard_plan_sha256": payload["shard_plan_sha256"],
        "progress_sha256": payload["progress_sha256"],
        "checkpoint_sha256": payload["checkpoint_sha256"],
        "shard_dir": str(payload["shard_dir"]),
    }


def _expected_binding(
    execution_plan_path: Path,
    *,
    shard_index: int,
) -> dict[str, Any]:
    execution = load_experiment_matrix_execution_plan(execution_plan_path)
    descriptors = execution["sharding"]["shards"]
    index = int(shard_index)
    if index < 0 or index >= len(descriptors):
        raise ValueError("shard_index is out of range")
    descriptor = descriptors[index]
    expected_cells = [
        cell
        for cell in execution["scope"]["cells"]
        if int(cell["shard_index"]) == index
    ]
    return {
        "execution_plan_sha256": execution["execution_plan_sha256"],
        "execution_plan_file_sha256": _sha256_file(execution_plan_path),
        "parent_plan_sha256": execution["parent"]["plan_sha256"],
        "source_git_commit": execution["source"]["git_commit"],
        "shard_index": index,
        "shard_id": descriptor["shard_id"],
        "expected_cell_count": len(expected_cells),
        "descriptor_sha256": _digest_json(descriptor),
        "cells_sha256": _digest_json(expected_cells),
    }


def _require_archive_capacity(
    path: Path,
    inventory: Mapping[str, Any],
    *,
    minimum_free_bytes: int,
) -> None:
    estimated_archive_bytes = (
        int(inventory["total_size_bytes"])
        + int(inventory["file_count"]) * 2048
        + _ARCHIVE_CAPACITY_OVERHEAD_BYTES
    )
    free_bytes = shutil.disk_usage(path).free
    if free_bytes - estimated_archive_bytes < minimum_free_bytes:
        raise FormalShardArchiveError(
            "insufficient destination capacity for a worst-case shard archive: "
            f"{free_bytes} available, {estimated_archive_bytes} estimated, "
            f"{minimum_free_bytes} reserved"
        )


def _require_restore_capacity(
    path: Path,
    inventory: Mapping[str, Any],
    *,
    minimum_free_bytes: int,
) -> None:
    required = (
        int(inventory["total_size_bytes"])
        + _ARCHIVE_CAPACITY_OVERHEAD_BYTES
        + minimum_free_bytes
    )
    free_bytes = shutil.disk_usage(path).free
    if free_bytes < required:
        raise FormalShardArchiveError(
            "insufficient destination capacity to restore the formal shard: "
            f"{free_bytes} available, {required} required"
        )


def _compression_level(value: int) -> int:
    level = int(value)
    if level < 1 or level > 19:
        raise ValueError("compression_level must be between 1 and 19")
    return level


def _minimum_free_bytes(value: int) -> int:
    minimum = int(value)
    if minimum < 0:
        raise ValueError("minimum_free_bytes must be non-negative")
    return minimum


def _zstd_runtime() -> tuple[str, str]:
    executable = shutil.which("zstd")
    if executable is None:
        raise FormalShardArchiveError(
            "zstd executable is required for formal shard archives"
        )
    completed = subprocess.run(
        [executable, "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    version = completed.stdout.strip()
    if not version:
        raise FormalShardArchiveError("zstd version output is empty")
    return executable, version


def _require_directory(path: str | Path, *, label: str) -> Path:
    unresolved = Path(path).expanduser()
    if unresolved.is_symlink():
        raise FormalShardArchiveError(f"{label} must not be a symbolic link")
    resolved = unresolved.resolve()
    if not resolved.is_dir():
        raise FormalShardArchiveError(
            f"{label} is not a directory: {resolved}"
        )
    return resolved


def _require_file(path: str | Path, *, label: str) -> Path:
    unresolved = Path(path).expanduser()
    if unresolved.is_symlink():
        raise FormalShardArchiveError(f"{label} must not be a symbolic link")
    resolved = unresolved.resolve()
    if not resolved.is_file():
        raise FormalShardArchiveError(f"{label} is not a file: {resolved}")
    return resolved


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    text = str(value).strip()
    if not text:
        raise ValueError("created_at_utc must be non-empty")
    return text


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
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FormalShardArchiveError(f"expected JSON object: {path}")
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_rows_csv_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    if not rows:
        raise FormalShardArchiveError(
            "cannot write an empty formal archive merge table"
        )
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


def _write_checksum_file(
    path: Path,
    checksums: Mapping[str, str],
) -> None:
    path.write_text(
        "".join(
            f"{checksums[name]}  {name}\n"
            for name in sorted(checksums)
        ),
        encoding="utf-8",
    )


def _read_checksum_file(
    path: Path,
    expected_names: set[str],
) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", maxsplit=1)
        if len(parts) != 2:
            raise FormalShardArchiveError(
                "formal shard archive checksum entry is malformed"
            )
        sha256, filename = parts
        if (
            len(sha256) != 64
            or any(character not in _HEX64 for character in sha256)
        ):
            raise FormalShardArchiveError(
                "formal shard archive checksum is not a lowercase SHA-256"
            )
        if filename in checksums:
            raise FormalShardArchiveError(
                "formal shard archive checksum filename is duplicated"
            )
        checksums[filename] = sha256
    if set(checksums) != expected_names:
        raise FormalShardArchiveError(
            "formal shard archive checksum entries do not match the contract"
        )
    return checksums


def _write_cli_result(
    payload: Mapping[str, Any],
    output: str | Path | None,
) -> None:
    text = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    if output is None:
        print(text, end="")
        return
    destination = Path(output).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"CLI result output already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create, verify, restore, and stream-merge deterministic formal "
            "shard archives without deleting source evidence"
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pack = subparsers.add_parser(
        "pack-shard",
        help="compress and verify one completed canonical shard",
    )
    _add_binding_arguments(pack)
    pack.add_argument("--destination", type=Path, required=True)
    pack.add_argument(
        "--compression-level",
        type=int,
        default=DEFAULT_ZSTD_COMPRESSION_LEVEL,
    )
    pack.add_argument(
        "--minimum-free-gib",
        type=float,
        default=FORMAL_R0_DEFAULT_MINIMUM_FREE_BYTES / 1024**3,
    )
    pack.add_argument("--created-at-utc")
    pack.add_argument("--result-json")

    verify = subparsers.add_parser(
        "verify-shard",
        help="verify one compressed shard and its frozen binding",
    )
    _add_binding_arguments(verify)
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--source", type=Path)
    verify.add_argument("--result-json")

    restore = subparsers.add_parser(
        "restore-shard",
        help="restore one archive to the execution plan's canonical shard path",
    )
    _add_binding_arguments(restore)
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--minimum-free-gib", type=float, default=0.0)
    restore.add_argument("--result-json")

    merge = subparsers.add_parser(
        "merge-archives",
        help="verify and merge a complete scope with one staged shard at a time",
    )
    merge.add_argument("--repository-root", type=Path, required=True)
    merge.add_argument("--execution-plan", type=Path, required=True)
    merge.add_argument("--archive-root", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--staging-root", type=Path)
    merge.add_argument("--write-d6-report", action="store_true")
    merge.add_argument(
        "--minimum-free-gib",
        type=float,
        default=FORMAL_R0_DEFAULT_MINIMUM_FREE_BYTES / 1024**3,
    )
    merge.add_argument("--result-json")
    return parser


def _add_binding_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--execution-plan", type=Path, required=True)
    parser.add_argument("--shard-index", type=int, required=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "pack-shard":
        result = create_verified_formal_shard_archive(
            execution_plan_path=args.execution_plan,
            shard_index=args.shard_index,
            destination=args.destination,
            created_at_utc=args.created_at_utc,
            compression_level=args.compression_level,
            minimum_free_bytes=int(args.minimum_free_gib * 1024**3),
        )
    elif args.command == "verify-shard":
        result = verify_formal_shard_archive(
            args.archive,
            execution_plan_path=args.execution_plan,
            shard_index=args.shard_index,
            source=args.source,
        )
    elif args.command == "restore-shard":
        result = restore_verified_formal_shard_archive(
            args.archive,
            execution_plan_path=args.execution_plan,
            shard_index=args.shard_index,
            minimum_free_bytes=int(args.minimum_free_gib * 1024**3),
        )
    elif args.command == "merge-archives":
        result = merge_verified_formal_shard_archives(
            repository_root=args.repository_root,
            execution_plan_path=args.execution_plan,
            archive_root=args.archive_root,
            output_dir=args.output,
            staging_root=args.staging_root,
            write_d6_report=bool(args.write_d6_report),
            minimum_free_bytes=int(args.minimum_free_gib * 1024**3),
        )
    else:
        raise AssertionError(f"unhandled command: {args.command}")
    _write_cli_result(result, args.result_json)
    return 0


__all__ = [
    "DEFAULT_ZSTD_COMPRESSION_LEVEL",
    "FORMAL_SHARD_ARCHIVE_CHECKSUM_FILENAME",
    "FORMAL_SHARD_ARCHIVE_D6_BINDING_SCHEMA",
    "FORMAL_SHARD_ARCHIVE_FORMAT",
    "FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME",
    "FORMAL_SHARD_ARCHIVE_MANIFEST_SCHEMA",
    "FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME",
    "FORMAL_SHARD_ARCHIVE_SCOPE_MERGE_SCHEMA",
    "FORMAL_SHARD_ARCHIVE_STORAGE_MODE",
    "FORMAL_SHARD_ARCHIVE_VERIFICATION_SCHEMA",
    "FormalShardArchiveError",
    "create_verified_formal_shard_archive",
    "main",
    "merge_verified_formal_shard_archives",
    "restore_verified_formal_shard_archive",
    "verify_formal_shard_archive",
]


if __name__ == "__main__":
    raise SystemExit(main())
