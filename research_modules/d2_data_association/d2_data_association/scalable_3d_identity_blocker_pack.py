"""Read-only causal audit packs for formal scalable-3D identity blockers.

The formal discovery path verifies execution-plan, shard, progress, cell,
episode, D6, and D2 artifact identities before selecting strict-unavailable
episodes.  Truth is used only after the episode has finished and never feeds
the online association path.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import csv
import hashlib
import json
from math import isfinite
from pathlib import Path
from statistics import fmean
from typing import Any

from .scalable_3d_identity import (
    evaluate_scalable_3d_identity_files,
    load_scalable_3d_identity_evaluation,
    load_scalable_3d_identity_evidence,
    load_scalable_3d_observation_truth_labels,
    sha256_file,
)
from .scalable_3d_identity_diagnostics import (
    Scalable3DIdentityBlockerDiagnostics,
    build_scalable_3d_identity_blocker_diagnostics,
)


FORMAL_IDENTITY_BLOCKER_SCOPE_SCHEMA_VERSION = (
    "d2.formal_identity_blocker_scope.v1"
)
FORMAL_IDENTITY_BLOCKER_CASE_SCHEMA_VERSION = (
    "d2.formal_identity_blocker_case.v1"
)
FORMAL_IDENTITY_BLOCKER_PACK_SCHEMA_VERSION = (
    "d2.formal_identity_blocker_causal_pack.v1"
)
FORMAL_IDENTITY_BLOCKER_INVENTORY_SCHEMA_VERSION = (
    "d2.formal_identity_blocker_artifact_inventory.v1"
)

_EXECUTION_PLAN_SCHEMA = "scalable3d-experiment-matrix-execution-plan-v1"
_SHARD_PLAN_SCHEMA = "scalable3d-experiment-matrix-shard-plan-v1"
_SHARD_CHECKPOINT_SCHEMA = (
    "scalable3d-experiment-matrix-shard-checkpoint-v1"
)
_SHARD_PROGRESS_SCHEMA = "scalable3d-experiment-matrix-shard-progress-v1"
_CELL_RESULT_SCHEMA = "scalable3d-experiment-matrix-cell-result-v1"
_D6_MANIFEST_SCHEMA = "scalable3d-d6-truth-isolated-manifest-v1"
_D6_EPISODE_SCHEMA = "d6.scalable3d_truth_isolated_episode.v1"
_IDENTITY_MANIFEST_SCHEMA = (
    "scalable3d-offline-identity-evaluation-manifest-v2"
)
_ARCHIVE_MANIFEST_SCHEMA = "scalable3d-formal-shard-archive-manifest-v1"
_ARCHIVE_VERIFICATION_SCHEMA = (
    "scalable3d-formal-shard-archive-verification-v1"
)

STRICT_BLOCKER_REASONS = frozenset(
    {
        "multiple_truth_targets_for_global_track",
        "source_observation_outside_lineage_window",
    }
)


class FormalIdentityBlockerAuditError(ValueError):
    """Formal evidence is missing, inconsistent, or incorrectly laid out."""


@dataclass(frozen=True, slots=True)
class FormalIdentityEpisodeReference:
    """Verified pointer to one completed formal episode."""

    cell_id: str
    shard_id: str
    shard_index: int
    shard_sequence: int
    global_index: int
    scope_index: int
    scenario: str
    scale: int
    seed: int
    variant: str
    episode_id: str
    episode_dir: Path
    strict_identity_metrics_available: bool
    strict_identity_metrics_reason: str | None
    source_git_commit: str
    execution_plan_sha256: str
    execution_plan_file_sha256: str
    shard_plan_sha256: str
    checkpoint_sha256: str
    progress_sha256: str
    cell_result_sha256: str
    declared_episode_artifact_tree_sha256: str
    episode_manifest_sha256: str
    identity_manifest_sha256: str
    identity_evaluation_sha256: str
    d6_manifest_sha256: str
    d6_episode_record_sha256: str
    archive_binding: Mapping[str, Any] | None = None

    def provenance_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "shard_id": self.shard_id,
            "shard_index": self.shard_index,
            "shard_sequence": self.shard_sequence,
            "global_index": self.global_index,
            "scope_index": self.scope_index,
            "scenario": self.scenario,
            "scale": self.scale,
            "seed": self.seed,
            "variant": self.variant,
            "episode_id": self.episode_id,
            "episode_dir": str(self.episode_dir),
            "source_git_commit": self.source_git_commit,
            "execution_plan_sha256": self.execution_plan_sha256,
            "execution_plan_file_sha256": (
                self.execution_plan_file_sha256
            ),
            "shard_plan_sha256": self.shard_plan_sha256,
            "checkpoint_sha256": self.checkpoint_sha256,
            "progress_sha256": self.progress_sha256,
            "cell_result_sha256": self.cell_result_sha256,
            "declared_episode_artifact_tree_sha256": (
                self.declared_episode_artifact_tree_sha256
            ),
            "episode_manifest_sha256": self.episode_manifest_sha256,
            "identity_manifest_sha256": self.identity_manifest_sha256,
            "identity_evaluation_sha256": (
                self.identity_evaluation_sha256
            ),
            "d6_manifest_sha256": self.d6_manifest_sha256,
            "d6_episode_record_sha256": (
                self.d6_episode_record_sha256
            ),
            "archive_binding": (
                None
                if self.archive_binding is None
                else dict(self.archive_binding)
            ),
        }


@dataclass(frozen=True, slots=True)
class FormalIdentityAuditScope:
    """Verified formal scope and its exact strict-unavailable subset."""

    execution_root: Path
    archive_root: Path | None
    source_git_commit: str
    execution_plan_sha256: str
    execution_plan_file_sha256: str
    planned_episode_count: int
    completed_episode_count: int
    completed_shard_count: int
    references: tuple[FormalIdentityEpisodeReference, ...]
    strict_unavailable_references: tuple[
        FormalIdentityEpisodeReference, ...
    ]
    shard_audits: tuple[Mapping[str, Any], ...]
    archive_adapter_mode: str
    schema_version: str = FORMAL_IDENTITY_BLOCKER_SCOPE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_root": str(self.execution_root),
            "archive_root": (
                None if self.archive_root is None else str(self.archive_root)
            ),
            "source_git_commit": self.source_git_commit,
            "execution_plan_sha256": self.execution_plan_sha256,
            "execution_plan_file_sha256": (
                self.execution_plan_file_sha256
            ),
            "planned_episode_count": self.planned_episode_count,
            "completed_episode_count": self.completed_episode_count,
            "completed_shard_count": self.completed_shard_count,
            "strict_unavailable_episode_count": len(
                self.strict_unavailable_references
            ),
            "strict_unavailable_episode_reason_counts": dict(
                sorted(
                    Counter(
                        ref.strict_identity_metrics_reason
                        for ref in self.strict_unavailable_references
                    ).items()
                )
            ),
            "archive_adapter_mode": self.archive_adapter_mode,
            "automatic_archive_unpack_performed": False,
            "archive_restore_policy": (
                "main_restores_at_most_one_verified_shard_at_a_time"
            ),
            "shards": [dict(item) for item in self.shard_audits],
        }


def discover_formal_identity_audit_scope(
    execution_root: str | Path,
    *,
    expected_source_git_commit: str | None = None,
    expected_execution_plan_sha256: str | None = None,
    expected_completed_episode_count: int | None = None,
    expected_strict_unavailable_episode_count: int | None = None,
    archive_root: str | Path | None = None,
    verify_archive_payload_sha256: bool = False,
) -> FormalIdentityAuditScope:
    """Discover completed cells under ``shards/*/cells/*/episode``.

    Archive metadata may be bound to the directory evidence.  This function
    never extracts an archive.  Archive-only shards must first be restored by
    main into a temporary one-shard directory.
    """

    root = Path(execution_root).resolve()
    if not root.is_dir():
        raise FormalIdentityBlockerAuditError(
            f"execution_root_missing:{root}"
        )
    archive = None if archive_root is None else Path(archive_root).resolve()
    if archive is not None and not archive.is_dir():
        raise FormalIdentityBlockerAuditError(
            f"archive_root_missing:{archive}"
        )

    plan_path = root / "experiment_matrix_execution_plan.json"
    plan = _read_json(plan_path, "execution_plan")
    if plan.get("schema_version") != _EXECUTION_PLAN_SCHEMA:
        raise FormalIdentityBlockerAuditError(
            "execution_plan_schema_mismatch"
        )
    declared_plan_sha = _bare_sha256(
        plan.get("execution_plan_sha256"),
        "execution_plan_sha256",
    )
    unhashed = dict(plan)
    unhashed.pop("execution_plan_sha256", None)
    if _digest_json(unhashed) != declared_plan_sha:
        raise FormalIdentityBlockerAuditError(
            "execution_plan_logical_sha256_mismatch"
        )
    if (
        expected_execution_plan_sha256 is not None
        and declared_plan_sha
        != _bare_sha256(
            expected_execution_plan_sha256,
            "expected_execution_plan_sha256",
        )
    ):
        raise FormalIdentityBlockerAuditError(
            "execution_plan_expected_sha256_mismatch"
        )
    plan_file_sha = _bare_file_sha256(plan_path)
    _verify_execution_plan_checksum(root, plan_file_sha)

    source = _require_mapping(plan.get("source"), "execution_plan.source")
    source_commit = _git_commit(source.get("git_commit"), "source.git_commit")
    if source.get("repository_dirty") is not False:
        raise FormalIdentityBlockerAuditError(
            "execution_plan_source_not_clean"
        )
    if (
        expected_source_git_commit is not None
        and source_commit
        != _git_commit(
            expected_source_git_commit,
            "expected_source_git_commit",
        )
    ):
        raise FormalIdentityBlockerAuditError(
            "execution_plan_source_commit_mismatch"
        )

    parent = _require_mapping(plan.get("parent"), "execution_plan.parent")
    if parent.get("formal") is not True:
        raise FormalIdentityBlockerAuditError(
            "execution_plan_parent_not_formal"
        )
    scope = _require_mapping(plan.get("scope"), "execution_plan.scope")
    cells = [
        _require_mapping(item, f"execution_plan.scope.cells[{index}]")
        for index, item in enumerate(
            _require_sequence(
                scope.get("cells"),
                "execution_plan.scope.cells",
            )
        )
    ]
    if int(scope.get("cell_count", -1)) != len(cells):
        raise FormalIdentityBlockerAuditError(
            "execution_plan_scope_cell_count_mismatch"
        )
    if _digest_json(cells) != _bare_sha256(
        scope.get("cells_sha256"),
        "execution_plan.scope.cells_sha256",
    ):
        raise FormalIdentityBlockerAuditError(
            "execution_plan_scope_cells_sha256_mismatch"
        )
    if scope.get("variants") != ["R0"]:
        raise FormalIdentityBlockerAuditError(
            "execution_plan_scope_not_r0_only"
        )
    cell_by_id = {
        _identifier(item.get("cell_id"), "scope cell_id"): dict(item)
        for item in cells
    }
    if len(cell_by_id) != len(cells):
        raise FormalIdentityBlockerAuditError(
            "execution_plan_duplicate_cell_id"
        )

    sharding = _require_mapping(
        plan.get("sharding"),
        "execution_plan.sharding",
    )
    shard_count = _nonnegative_int(
        sharding.get("shard_count"),
        "execution_plan.sharding.shard_count",
    )
    descriptors = [
        _require_mapping(
            item,
            f"execution_plan.sharding.shards[{index}]",
        )
        for index, item in enumerate(
            _require_sequence(
                sharding.get("shards"),
                "execution_plan.sharding.shards",
            )
        )
    ]
    if len(descriptors) != shard_count:
        raise FormalIdentityBlockerAuditError(
            "execution_plan_shard_descriptor_count_mismatch"
        )
    descriptor_by_index = {
        _nonnegative_int(item.get("shard_index"), "shard_index"): dict(item)
        for item in descriptors
    }
    if len(descriptor_by_index) != len(descriptors):
        raise FormalIdentityBlockerAuditError(
            "execution_plan_duplicate_shard_index"
        )

    shard_dirs = sorted((root / "shards").glob("shard_*_of_*"))
    if not shard_dirs:
        if archive is not None:
            raise FormalIdentityBlockerAuditError(
                "archive_only_scope_requires_main_one_shard_restoration"
            )
        raise FormalIdentityBlockerAuditError("completed_shards_missing")

    references: list[FormalIdentityEpisodeReference] = []
    shard_audits: list[dict[str, Any]] = []
    seen_cells: set[str] = set()
    for shard_dir in shard_dirs:
        shard_index = _parse_shard_index(shard_dir.name, shard_count)
        descriptor = descriptor_by_index.get(shard_index)
        if descriptor is None:
            raise FormalIdentityBlockerAuditError(
                f"unplanned_shard_directory:{shard_dir.name}"
            )
        shard_refs, shard_audit = _verify_formal_shard(
            root=root,
            shard_dir=shard_dir,
            shard_index=shard_index,
            descriptor=descriptor,
            cell_by_id=cell_by_id,
            execution_plan_sha256=declared_plan_sha,
            execution_plan_file_sha256=plan_file_sha,
            source_git_commit=source_commit,
            archive_root=archive,
            verify_archive_payload_sha256=verify_archive_payload_sha256,
        )
        for ref in shard_refs:
            if ref.cell_id in seen_cells:
                raise FormalIdentityBlockerAuditError(
                    f"completed_cell_repeated_across_shards:{ref.cell_id}"
                )
            seen_cells.add(ref.cell_id)
        references.extend(shard_refs)
        shard_audits.append(shard_audit)

    references.sort(key=lambda item: item.scope_index)
    strict_refs = tuple(
        ref
        for ref in references
        if not ref.strict_identity_metrics_available
    )
    unexpected_reasons = sorted(
        {
            ref.strict_identity_metrics_reason
            for ref in strict_refs
            if ref.strict_identity_metrics_reason not in STRICT_BLOCKER_REASONS
        }
    )
    if unexpected_reasons:
        raise FormalIdentityBlockerAuditError(
            "unexpected_strict_identity_blocker_reasons:"
            + ",".join(str(item) for item in unexpected_reasons)
        )
    if (
        expected_completed_episode_count is not None
        and len(references) != int(expected_completed_episode_count)
    ):
        raise FormalIdentityBlockerAuditError(
            "completed_episode_count_mismatch:"
            f"expected={expected_completed_episode_count}:"
            f"actual={len(references)}"
        )
    if (
        expected_strict_unavailable_episode_count is not None
        and len(strict_refs)
        != int(expected_strict_unavailable_episode_count)
    ):
        raise FormalIdentityBlockerAuditError(
            "strict_unavailable_episode_count_mismatch:"
            f"expected={expected_strict_unavailable_episode_count}:"
            f"actual={len(strict_refs)}"
        )

    return FormalIdentityAuditScope(
        execution_root=root,
        archive_root=archive,
        source_git_commit=source_commit,
        execution_plan_sha256=declared_plan_sha,
        execution_plan_file_sha256=plan_file_sha,
        planned_episode_count=len(cells),
        completed_episode_count=len(references),
        completed_shard_count=len(shard_audits),
        references=tuple(references),
        strict_unavailable_references=strict_refs,
        shard_audits=tuple(shard_audits),
        archive_adapter_mode=(
            "directory_only"
            if archive is None
            else "directory_with_read_only_archive_binding"
        ),
    )


def _verify_formal_shard(
    *,
    root: Path,
    shard_dir: Path,
    shard_index: int,
    descriptor: Mapping[str, Any],
    cell_by_id: Mapping[str, Mapping[str, Any]],
    execution_plan_sha256: str,
    execution_plan_file_sha256: str,
    source_git_commit: str,
    archive_root: Path | None,
    verify_archive_payload_sha256: bool,
) -> tuple[list[FormalIdentityEpisodeReference], dict[str, Any]]:
    shard_id = shard_dir.name
    shard_plan_path = shard_dir / "shard_plan.json"
    checkpoint_path = shard_dir / "checkpoint.json"
    progress_path = shard_dir / "progress.jsonl"
    shard_plan = _read_json(shard_plan_path, f"{shard_id}.shard_plan")
    checkpoint = _read_json(checkpoint_path, f"{shard_id}.checkpoint")
    progress = _read_jsonl(progress_path, f"{shard_id}.progress")
    if shard_plan.get("schema_version") != _SHARD_PLAN_SCHEMA:
        raise FormalIdentityBlockerAuditError(
            f"{shard_id}:shard_plan_schema_mismatch"
        )
    if checkpoint.get("schema_version") != _SHARD_CHECKPOINT_SCHEMA:
        raise FormalIdentityBlockerAuditError(
            f"{shard_id}:checkpoint_schema_mismatch"
        )

    planned_cell_ids = [
        _identifier(item, f"{shard_id}.descriptor.cell_id")
        for item in _require_sequence(
            descriptor.get("cell_ids"),
            f"{shard_id}.descriptor.cell_ids",
        )
    ]
    planned_cells = [dict(cell_by_id[item]) for item in planned_cell_ids]
    planned_cells.sort(key=lambda item: int(item["shard_sequence"]))
    for field, actual, expected in (
        (
            "execution_plan_sha256",
            shard_plan.get("execution_plan_sha256"),
            execution_plan_sha256,
        ),
        (
            "source_git_commit",
            shard_plan.get("source_git_commit"),
            source_git_commit,
        ),
        ("descriptor", shard_plan.get("descriptor"), descriptor),
        ("cells", shard_plan.get("cells"), planned_cells),
        (
            "cells_sha256",
            shard_plan.get("cells_sha256"),
            _digest_json(planned_cells),
        ),
    ):
        if actual != expected:
            raise FormalIdentityBlockerAuditError(
                f"{shard_id}:shard_plan_{field}_mismatch"
            )

    completed_count = _nonnegative_int(
        checkpoint.get("completed_cell_count"),
        f"{shard_id}.checkpoint.completed_cell_count",
    )
    expected_count = len(planned_cells)
    if completed_count != expected_count:
        raise FormalIdentityBlockerAuditError(
            f"{shard_id}:partial_shard_requires_explicit_main_scope"
        )
    for field, expected in (
        ("execution_plan_sha256", execution_plan_sha256),
        ("source_git_commit", source_git_commit),
        ("shard_id", shard_id),
        ("shard_index", shard_index),
        ("expected_cell_count", expected_count),
        ("completed_cell_count", expected_count),
        ("next_sequence", expected_count),
        ("status", "complete"),
        ("progress_sha256", _bare_file_sha256(progress_path)),
    ):
        if checkpoint.get(field) != expected:
            raise FormalIdentityBlockerAuditError(
                f"{shard_id}:checkpoint_{field}_mismatch"
            )
    if len(progress) != expected_count:
        raise FormalIdentityBlockerAuditError(
            f"{shard_id}:progress_row_count_mismatch"
        )

    archive_binding = None
    if archive_root is not None:
        archive_binding = _verify_archive_binding(
            archive_root=archive_root,
            shard_id=shard_id,
            shard_index=shard_index,
            execution_plan_sha256=execution_plan_sha256,
            execution_plan_file_sha256=execution_plan_file_sha256,
            source_git_commit=source_git_commit,
            shard_plan_path=shard_plan_path,
            checkpoint_path=checkpoint_path,
            progress_path=progress_path,
            cells_sha256=_digest_json(planned_cells),
            verify_payload_sha256=verify_archive_payload_sha256,
        )

    references: list[FormalIdentityEpisodeReference] = []
    seen_progress_ids: set[str] = set()
    for sequence, (row, planned_cell) in enumerate(
        zip(progress, planned_cells, strict=True)
    ):
        if row.get("schema_version") != _SHARD_PROGRESS_SCHEMA:
            raise FormalIdentityBlockerAuditError(
                f"{shard_id}:progress_schema_mismatch:{sequence}"
            )
        cell_id = _identifier(
            row.get("cell_id"),
            f"{shard_id}.progress.cell_id",
        )
        if cell_id in seen_progress_ids:
            raise FormalIdentityBlockerAuditError(
                f"{shard_id}:progress_duplicate_cell_id:{cell_id}"
            )
        seen_progress_ids.add(cell_id)
        for field, expected in (
            ("cell_id", planned_cell["cell_id"]),
            ("global_index", planned_cell["global_index"]),
            ("scope_index", planned_cell["scope_index"]),
            ("shard_index", shard_index),
            ("shard_sequence", planned_cell["shard_sequence"]),
            ("sequence", sequence),
            ("execution_plan_sha256", execution_plan_sha256),
        ):
            if row.get(field) != expected:
                raise FormalIdentityBlockerAuditError(
                    f"{shard_id}:progress_{field}_mismatch:{sequence}"
                )
        expected_cell_result_relative = (
            f"shards/{shard_id}/cells/{cell_id}/cell_result.json"
        )
        if row.get("cell_result_relative_path") != (
            expected_cell_result_relative
        ):
            raise FormalIdentityBlockerAuditError(
                f"{shard_id}:progress_cell_result_path_mismatch:{cell_id}"
            )
        cell_dir = shard_dir / "cells" / cell_id
        references.append(
            _verify_formal_cell(
                root=root,
                cell_dir=cell_dir,
                planned_cell=planned_cell,
                progress_row=row,
                shard_id=shard_id,
                shard_index=shard_index,
                execution_plan_sha256=execution_plan_sha256,
                execution_plan_file_sha256=(
                    execution_plan_file_sha256
                ),
                source_git_commit=source_git_commit,
                shard_plan_sha256=_bare_file_sha256(shard_plan_path),
                checkpoint_sha256=_bare_file_sha256(checkpoint_path),
                progress_sha256=_bare_file_sha256(progress_path),
                archive_binding=archive_binding,
            )
        )

    return references, {
        "shard_id": shard_id,
        "shard_index": shard_index,
        "planned_cell_count": expected_count,
        "completed_cell_count": len(references),
        "source_git_commit": source_git_commit,
        "execution_plan_sha256": execution_plan_sha256,
        "shard_plan_sha256": _prefixed_file_sha256(shard_plan_path),
        "checkpoint_sha256": _prefixed_file_sha256(checkpoint_path),
        "progress_sha256": _prefixed_file_sha256(progress_path),
        "archive_binding": archive_binding,
        "verified": True,
    }


def _verify_formal_cell(
    *,
    root: Path,
    cell_dir: Path,
    planned_cell: Mapping[str, Any],
    progress_row: Mapping[str, Any],
    shard_id: str,
    shard_index: int,
    execution_plan_sha256: str,
    execution_plan_file_sha256: str,
    source_git_commit: str,
    shard_plan_sha256: str,
    checkpoint_sha256: str,
    progress_sha256: str,
    archive_binding: Mapping[str, Any] | None,
) -> FormalIdentityEpisodeReference:
    cell_id = _identifier(planned_cell.get("cell_id"), "planned cell_id")
    cell_result_path = cell_dir / "cell_result.json"
    cell_result = _read_json(cell_result_path, f"{cell_id}.cell_result")
    cell_result_sha = _bare_file_sha256(cell_result_path)
    if cell_result.get("schema_version") != _CELL_RESULT_SCHEMA:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:cell_result_schema_mismatch"
        )
    for field, expected in (
        ("cell", planned_cell),
        ("status", "complete"),
        ("execution_plan_sha256", execution_plan_sha256),
        ("source_git_commit", source_git_commit),
        (
            "episode_relative_path",
            f"shards/{shard_id}/cells/{cell_id}/episode",
        ),
    ):
        if cell_result.get(field) != expected:
            raise FormalIdentityBlockerAuditError(
                f"{cell_id}:cell_result_{field}_mismatch"
            )
    if _bare_sha256(
        progress_row.get("cell_result_sha256"),
        f"{cell_id}.progress.cell_result_sha256",
    ) != cell_result_sha:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:progress_cell_result_sha256_mismatch"
        )
    artifact_tree_sha = _bare_sha256(
        cell_result.get("artifact_tree_sha256"),
        f"{cell_id}.artifact_tree_sha256",
    )
    if _bare_sha256(
        progress_row.get("episode_artifact_tree_sha256"),
        f"{cell_id}.progress.episode_artifact_tree_sha256",
    ) != artifact_tree_sha:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:progress_artifact_tree_sha256_mismatch"
        )

    episode_dir = cell_dir / "episode"
    if not episode_dir.is_dir():
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:episode_directory_missing"
        )
    episode_manifest_path = episode_dir / "manifest.json"
    episode_manifest = _read_json(
        episode_manifest_path,
        f"{cell_id}.episode_manifest",
    )
    episode_id = _identifier(
        episode_manifest.get("episode_id"),
        f"{cell_id}.episode_id",
    )
    if cell_result.get("episode_id") != episode_id:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:episode_id_cell_result_mismatch"
        )
    for field, expected in (
        ("git_commit", source_git_commit),
        ("repository_dirty", False),
        ("seed", int(planned_cell["seed"])),
    ):
        if episode_manifest.get(field) != expected:
            raise FormalIdentityBlockerAuditError(
                f"{cell_id}:episode_manifest_{field}_mismatch"
            )

    identity_dir = episode_dir / "offline_identity"
    identity_manifest_path = identity_dir / "manifest.json"
    identity_manifest = _read_json(
        identity_manifest_path,
        f"{cell_id}.identity_manifest",
    )
    if identity_manifest.get("schema_version") != _IDENTITY_MANIFEST_SCHEMA:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:identity_manifest_schema_mismatch"
        )
    if identity_manifest.get("episode_id") != episode_id:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:identity_manifest_episode_id_mismatch"
        )
    identity_source_hashes = _require_mapping(
        identity_manifest.get("source_hashes"),
        f"{cell_id}.identity_manifest.source_hashes",
    )
    identity_evaluation_path = identity_dir / "identity_evaluation.json"
    identity_evaluation_sha = _verify_prefixed_file_hash(
        identity_evaluation_path,
        identity_source_hashes.get("identity_evaluation"),
        f"{cell_id}.identity_evaluation",
    )

    d6_dir = episode_dir / "d6_truth_isolated"
    d6_manifest_path = d6_dir / "manifest.json"
    d6_manifest = _read_json(d6_manifest_path, f"{cell_id}.d6_manifest")
    if d6_manifest.get("schema_version") != _D6_MANIFEST_SCHEMA:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:d6_manifest_schema_mismatch"
        )
    if d6_manifest.get("episode_id") != episode_id:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:d6_manifest_episode_id_mismatch"
        )
    d6_source_hashes = _require_mapping(
        d6_manifest.get("source_hashes"),
        f"{cell_id}.d6_manifest.source_hashes",
    )
    identity_manifest_sha = _prefixed_file_sha256(identity_manifest_path)
    if _prefixed_sha256(
        d6_source_hashes.get("offline_identity_manifest"),
        f"{cell_id}.d6.offline_identity_manifest",
    ) != identity_manifest_sha:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:d6_identity_manifest_sha256_mismatch"
        )
    if _prefixed_sha256(
        d6_source_hashes.get("offline_identity_evaluation"),
        f"{cell_id}.d6.offline_identity_evaluation",
    ) != identity_evaluation_sha:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:d6_identity_evaluation_sha256_mismatch"
        )
    d6_output_hashes = _require_mapping(
        d6_manifest.get("output_hashes"),
        f"{cell_id}.d6_manifest.output_hashes",
    )
    episode_record_path = d6_dir / "episode_record.json"
    d6_episode_sha = _verify_prefixed_file_hash(
        episode_record_path,
        d6_output_hashes.get("episode_record"),
        f"{cell_id}.d6_episode_record",
    )
    d6_record = _read_json(episode_record_path, f"{cell_id}.d6_episode_record")
    if d6_record.get("schema_version") != _D6_EPISODE_SCHEMA:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:d6_episode_schema_mismatch"
        )
    context = _require_mapping(
        d6_record.get("context"),
        f"{cell_id}.d6.context",
    )
    for field, expected in (
        ("episode_id", episode_id),
        ("seed", int(planned_cell["seed"])),
        ("target_count", int(planned_cell["scale"])),
        ("resource_count", int(planned_cell["scale"])),
    ):
        if context.get(field) != expected:
            raise FormalIdentityBlockerAuditError(
                f"{cell_id}:d6_context_{field}_mismatch"
            )
    d2_identity = _require_mapping(
        d6_record.get("d2_identity"),
        f"{cell_id}.d6.d2_identity",
    )
    if d2_identity.get("episode_id") != episode_id:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:d6_d2_episode_id_mismatch"
        )
    availability = d2_identity.get("id_switch_count_availability")
    value = d2_identity.get("id_switch_count")
    reason_value = d2_identity.get("id_switch_count_unavailable_reason")
    if availability == "available":
        if value is None or reason_value is not None:
            raise FormalIdentityBlockerAuditError(
                f"{cell_id}:available_strict_identity_contract_invalid"
            )
        strict_available = True
        strict_reason = None
    elif availability == "unavailable":
        if value is not None or not str(reason_value or "").strip():
            raise FormalIdentityBlockerAuditError(
                f"{cell_id}:unavailable_strict_identity_contract_invalid"
            )
        strict_available = False
        strict_reason = str(reason_value)
    else:
        raise FormalIdentityBlockerAuditError(
            f"{cell_id}:strict_identity_availability_invalid"
        )

    return FormalIdentityEpisodeReference(
        cell_id=cell_id,
        shard_id=shard_id,
        shard_index=shard_index,
        shard_sequence=int(planned_cell["shard_sequence"]),
        global_index=int(planned_cell["global_index"]),
        scope_index=int(planned_cell["scope_index"]),
        scenario=str(planned_cell["scenario"]),
        scale=int(planned_cell["scale"]),
        seed=int(planned_cell["seed"]),
        variant=str(planned_cell["variant"]),
        episode_id=episode_id,
        episode_dir=episode_dir,
        strict_identity_metrics_available=strict_available,
        strict_identity_metrics_reason=strict_reason,
        source_git_commit=source_git_commit,
        execution_plan_sha256=execution_plan_sha256,
        execution_plan_file_sha256=execution_plan_file_sha256,
        shard_plan_sha256=shard_plan_sha256,
        checkpoint_sha256=checkpoint_sha256,
        progress_sha256=progress_sha256,
        cell_result_sha256=cell_result_sha,
        declared_episode_artifact_tree_sha256=artifact_tree_sha,
        episode_manifest_sha256=_bare_file_sha256(episode_manifest_path),
        identity_manifest_sha256=_bare_sha256(
            identity_manifest_sha,
            f"{cell_id}.identity_manifest_sha256",
        ),
        identity_evaluation_sha256=_bare_sha256(
            identity_evaluation_sha,
            f"{cell_id}.identity_evaluation_sha256",
        ),
        d6_manifest_sha256=_bare_file_sha256(d6_manifest_path),
        d6_episode_record_sha256=_bare_sha256(
            d6_episode_sha,
            f"{cell_id}.d6_episode_record_sha256",
        ),
        archive_binding=archive_binding,
    )


def _verify_archive_binding(
    *,
    archive_root: Path,
    shard_id: str,
    shard_index: int,
    execution_plan_sha256: str,
    execution_plan_file_sha256: str,
    source_git_commit: str,
    shard_plan_path: Path,
    checkpoint_path: Path,
    progress_path: Path,
    cells_sha256: str,
    verify_payload_sha256: bool,
) -> dict[str, Any]:
    archive_dir = archive_root / shard_id
    manifest_path = archive_dir / "shard_archive_manifest.json"
    sums_path = archive_dir / "SHA256SUMS"
    payload_path = archive_dir / "shard_payload.tar.zst"
    verify_result_path = archive_root / f"{shard_id}_verify_result.json"
    manifest = _read_json(manifest_path, f"{shard_id}.archive_manifest")
    if manifest.get("schema_version") != _ARCHIVE_MANIFEST_SCHEMA:
        raise FormalIdentityBlockerAuditError(
            f"{shard_id}:archive_manifest_schema_mismatch"
        )
    binding = _require_mapping(
        manifest.get("binding"),
        f"{shard_id}.archive_manifest.binding",
    )
    for field, expected in (
        ("execution_plan_sha256", execution_plan_sha256),
        ("execution_plan_file_sha256", execution_plan_file_sha256),
        ("source_git_commit", source_git_commit),
        ("shard_id", shard_id),
        ("shard_index", shard_index),
        ("cells_sha256", cells_sha256),
        ("shard_plan_sha256", _bare_file_sha256(shard_plan_path)),
        ("checkpoint_sha256", _bare_file_sha256(checkpoint_path)),
        ("progress_sha256", _bare_file_sha256(progress_path)),
        ("storage_validation_status", "verified_complete"),
    ):
        if binding.get(field) != expected:
            raise FormalIdentityBlockerAuditError(
                f"{shard_id}:archive_binding_{field}_mismatch"
            )
    payload = _require_mapping(
        manifest.get("payload"),
        f"{shard_id}.archive_manifest.payload",
    )
    if payload.get("filename") != payload_path.name or not payload_path.is_file():
        raise FormalIdentityBlockerAuditError(
            f"{shard_id}:archive_payload_missing"
        )
    payload_size = _nonnegative_int(
        payload.get("size_bytes"),
        f"{shard_id}.archive_payload.size_bytes",
    )
    if payload_path.stat().st_size != payload_size:
        raise FormalIdentityBlockerAuditError(
            f"{shard_id}:archive_payload_size_mismatch"
        )
    payload_sha = _bare_sha256(
        payload.get("sha256"),
        f"{shard_id}.archive_payload.sha256",
    )
    sums = _read_sha256s(sums_path)
    if sums.get(manifest_path.name) != _bare_file_sha256(manifest_path):
        raise FormalIdentityBlockerAuditError(
            f"{shard_id}:archive_manifest_SHA256SUMS_mismatch"
        )
    if sums.get(payload_path.name) != payload_sha:
        raise FormalIdentityBlockerAuditError(
            f"{shard_id}:archive_payload_SHA256SUMS_mismatch"
        )
    if verify_payload_sha256 and _bare_file_sha256(payload_path) != payload_sha:
        raise FormalIdentityBlockerAuditError(
            f"{shard_id}:archive_payload_sha256_mismatch"
        )
    verify_result = _read_json(
        verify_result_path,
        f"{shard_id}.archive_verify_result",
    )
    for field, expected in (
        ("schema_version", _ARCHIVE_VERIFICATION_SCHEMA),
        ("status", "verified"),
        ("source_verified", True),
        ("execution_plan_sha256", execution_plan_sha256),
        ("shard_id", shard_id),
        ("shard_index", shard_index),
        ("archive_sha256", payload_sha),
    ):
        if verify_result.get(field) != expected:
            raise FormalIdentityBlockerAuditError(
                f"{shard_id}:archive_verify_{field}_mismatch"
            )
    return {
        "mode": "read_only_metadata_binding",
        "automatic_unpack_performed": False,
        "restore_policy": "main_restores_one_shard_at_a_time",
        "archive_manifest_sha256": _prefixed_file_sha256(manifest_path),
        "archive_payload_sha256": f"sha256:{payload_sha}",
        "archive_payload_size_bytes": payload_size,
        "archive_payload_sha256_recomputed": verify_payload_sha256,
        "archive_verify_result_sha256": _prefixed_file_sha256(
            verify_result_path
        ),
        "archive_source_verified": True,
    }


def audit_formal_identity_blocker_episode(
    reference: FormalIdentityEpisodeReference,
) -> tuple[Scalable3DIdentityBlockerDiagnostics, dict[str, Any]]:
    """Replay and explain one verified strict-unavailable formal episode."""

    if reference.strict_identity_metrics_available:
        raise FormalIdentityBlockerAuditError(
            f"case_is_not_strict_unavailable:{reference.cell_id}"
        )
    episode_dir = reference.episode_dir
    identity_dir = episode_dir / "offline_identity"
    identity_manifest_path = identity_dir / "manifest.json"
    identity_manifest = _read_json(
        identity_manifest_path,
        f"{reference.cell_id}.identity_manifest",
    )
    source_hashes = _require_mapping(
        identity_manifest.get("source_hashes"),
        "identity_manifest.source_hashes",
    )
    evidence_path = identity_dir / "identity_evidence.json"
    evaluation_path = identity_dir / "identity_evaluation.json"
    d1_path = identity_dir / "online_d1_records.jsonl"
    d2_path = identity_dir / "online_d2_records.jsonl"
    labels_path = identity_dir / "observation_truth_labels.jsonl"
    required_sources = {
        "identity_evidence": evidence_path,
        "identity_evaluation": evaluation_path,
        "online_d1_records": d1_path,
        "online_d2_records": d2_path,
        "observation_truth_labels": labels_path,
    }
    actual_source_hashes = {
        name: _verify_prefixed_file_hash(
            path,
            source_hashes.get(name),
            f"{reference.cell_id}.{name}",
        )
        for name, path in required_sources.items()
    }

    persisted = load_scalable_3d_identity_evaluation(
        evaluation_path,
        expected_sha256=actual_source_hashes["identity_evaluation"],
    )
    configuration = persisted.configuration
    replayed = evaluate_scalable_3d_identity_files(
        evidence_path=evidence_path,
        expected_evidence_sha256=actual_source_hashes["identity_evidence"],
        online_d1_records_path=d1_path,
        online_d2_records_path=d2_path,
        observation_truth_labels_path=labels_path,
        timestamp_tolerance_s=float(
            configuration.get("timestamp_tolerance_s", 1.0e-9)
        ),
        lineage_time_window_s=float(
            configuration.get("lineage_time_window_s", 0.9)
        ),
        truth_presence_window_s=float(
            configuration.get("truth_presence_window_s", 0.9)
        ),
    )
    if replayed.to_dict() != persisted.to_dict():
        raise FormalIdentityBlockerAuditError(
            f"producer_replay_differs:{reference.cell_id}"
        )
    if persisted.episode_id != reference.episode_id:
        raise FormalIdentityBlockerAuditError(
            f"identity_evaluation_episode_mismatch:{reference.cell_id}"
        )
    if persisted.metrics.available:
        raise FormalIdentityBlockerAuditError(
            f"persisted_strict_verdict_changed_to_available:{reference.cell_id}"
        )
    if persisted.metrics.reason != reference.strict_identity_metrics_reason:
        raise FormalIdentityBlockerAuditError(
            f"strict_reason_d6_evaluation_mismatch:{reference.cell_id}"
        )
    evidence = load_scalable_3d_identity_evidence(
        evidence_path,
        expected_sha256=actual_source_hashes["identity_evidence"],
    )
    labels = load_scalable_3d_observation_truth_labels(
        labels_path,
        expected_sha256=actual_source_hashes[
            "observation_truth_labels"
        ],
    )

    consistency_dir = episode_dir / "offline_consistency"
    consistency_manifest_path = consistency_dir / "manifest.json"
    consistency_manifest = _read_json(
        consistency_manifest_path,
        f"{reference.cell_id}.consistency_manifest",
    )
    if consistency_manifest.get("episode_id") != reference.episode_id:
        raise FormalIdentityBlockerAuditError(
            f"consistency_manifest_episode_mismatch:{reference.cell_id}"
        )
    consistency_hashes = _require_mapping(
        consistency_manifest.get("source_hashes"),
        "consistency_manifest.source_hashes",
    )
    consistency_evidence_path = consistency_dir / "online_evidence.json"
    consistency_evidence_sha = _verify_prefixed_file_hash(
        consistency_evidence_path,
        consistency_hashes.get("online_evidence"),
        f"{reference.cell_id}.consistency_online_evidence",
    )
    consistency_evidence = _read_json(
        consistency_evidence_path,
        f"{reference.cell_id}.consistency_online_evidence",
    )

    recovery_config = _require_mapping(
        identity_manifest.get("identity_commitment_recovery_config"),
        "identity_manifest.identity_commitment_recovery_config",
    )
    freshness_window_s = _nonnegative_float(
        recovery_config.get("max_recovery_evidence_age_seconds"),
        "max_recovery_evidence_age_seconds",
    )
    diagnostics = build_scalable_3d_identity_blocker_diagnostics(
        evidence,
        replayed,
        labels,
        identity_evaluation_sha256=actual_source_hashes[
            "identity_evaluation"
        ],
        d1_consistency_evidence=consistency_evidence,
        d1_consistency_evidence_sha256=consistency_evidence_sha,
        identity_commitment_freshness_window_s=freshness_window_s,
    )
    events = list(diagnostics.causal_mapping_events)
    if not events:
        raise FormalIdentityBlockerAuditError(
            f"strict_unavailable_case_has_no_blocker_events:{reference.cell_id}"
        )
    if {
        str(event["reason"]) for event in events
    } != {reference.strict_identity_metrics_reason}:
        raise FormalIdentityBlockerAuditError(
            f"case_event_reason_mismatch:{reference.cell_id}"
        )
    allowed_classifications = {
        "multiple_truth_targets_for_global_track": {
            "newest_observation_introduced_new_truth",
            "historical_multi_truth_already_present",
            "persisted_multi_truth_without_new_truth_introduction",
        },
        "source_observation_outside_lineage_window": {
            "historical_lineage_only_stale",
            "active_commitment_source_stale",
        },
    }
    invalid_classifications = sorted(
        {
            str(event["causal_classification"])
            for event in events
            if str(event["causal_classification"])
            not in allowed_classifications[
                str(reference.strict_identity_metrics_reason)
            ]
        }
    )
    if invalid_classifications:
        raise FormalIdentityBlockerAuditError(
            f"causal_evidence_incomplete:{reference.cell_id}:"
            + ",".join(invalid_classifications)
        )
    if any(
        not bool(
            event.get("identity_commitment", {}).get(
                "source_record_matched",
                False,
            )
        )
        for event in events
    ):
        raise FormalIdentityBlockerAuditError(
            f"active_commitment_source_not_uniquely_bound:{reference.cell_id}"
        )

    return diagnostics, {
        "cell_id": reference.cell_id,
        "shard_id": reference.shard_id,
        "shard_index": reference.shard_index,
        "scenario": reference.scenario,
        "scale": reference.scale,
        "seed": reference.seed,
        "episode_id": reference.episode_id,
        "strict_identity_metrics_available": False,
        "strict_identity_metrics_reason": (
            reference.strict_identity_metrics_reason
        ),
        "blocker_mapping_event_count": len(events),
        "blocking_mapping_count": diagnostics.blocking_mapping_count,
        "producer_replay_verified": True,
        "source_hashes_verified": True,
        "episode_identity_verified": True,
        "online_truth_isolation_verified": (
            diagnostics.online_truth_isolation_verified
        ),
        "strict_unavailable_preserved": True,
        "unavailable_backfilled_as_zero": False,
        "lineage_time_window_s": diagnostics.lineage_time_window_s,
        "identity_commitment_freshness_window_s": (
            diagnostics.identity_commitment_freshness_window_s
        ),
        "causal_classification_counts": dict(
            sorted(
                Counter(
                    str(event["causal_classification"])
                    for event in events
                ).items()
            )
        ),
        "commitment_reason_counts": dict(
            sorted(
                Counter(
                    str(event["identity_commitment"]["reason"])
                    for event in events
                ).items()
            )
        ),
        "modality_transition_counts": dict(
            sorted(
                Counter(
                    str(event["sensor_transition"]["modality_transition"])
                    for event in events
                ).items()
            )
        ),
    }


def write_formal_identity_blocker_causal_pack(
    scope: FormalIdentityAuditScope,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write per-case JSON/CSV, aggregate CSV/JSON, and a Chinese report."""

    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    case_dir = destination / "cases"
    case_dir.mkdir(parents=True, exist_ok=True)
    case_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    case_payloads: list[dict[str, Any]] = []
    artifact_rows: list[dict[str, Any]] = []
    for reference in scope.strict_unavailable_references:
        diagnostics, row = audit_formal_identity_blocker_episode(reference)
        payload = {
            "schema_version": FORMAL_IDENTITY_BLOCKER_CASE_SCHEMA_VERSION,
            "case_identity": {
                "cell_id": reference.cell_id,
                "episode_id": reference.episode_id,
                "strict_identity_metrics_available": False,
                "strict_identity_metrics_reason": (
                    reference.strict_identity_metrics_reason
                ),
                "strict_unavailable_preserved": True,
                "unavailable_backfilled_as_zero": False,
            },
            "formal_provenance": reference.provenance_dict(),
            "source_verification": {
                "execution_plan_verified": True,
                "shard_plan_checkpoint_progress_verified": True,
                "cell_result_verified": True,
                "episode_identity_verified": True,
                "identity_manifest_source_hashes_verified": True,
                "d6_manifest_source_hashes_verified": True,
                "producer_replay_verified": True,
                "episode_artifact_tree_sha256": {
                    "declared_and_progress_bound": True,
                    "recomputed_by_d2_pack": False,
                    "reason": (
                        "D2 verifies required source artifacts directly; "
                        "full tree recomputation remains a main/D6 storage audit"
                    ),
                },
            },
            "diagnostics": diagnostics.to_dict(),
            "interpretation_boundary": {
                "usage": "offline_causal_explanation_only",
                "online_association_modified": False,
                "truth_used_for_online_correction": False,
                "global_track_id_modified": False,
                "strict_verdict_recomputed_or_relabelled": False,
                "nearest_position_identity_inference_used": False,
            },
        }
        case_json_path = case_dir / f"{reference.cell_id}.json"
        _write_json(case_json_path, payload)
        case_json_sha = _prefixed_file_sha256(case_json_path)
        case_event_rows = [
            _event_csv_row(reference, event)
            for event in diagnostics.causal_mapping_events
        ]
        case_csv_path = case_dir / f"{reference.cell_id}.csv"
        _write_csv(case_csv_path, case_event_rows)
        case_csv_sha = _prefixed_file_sha256(case_csv_path)
        row = {
            **row,
            "case_json_relative_path": case_json_path.relative_to(
                destination
            ).as_posix(),
            "case_json_sha256": case_json_sha,
            "case_csv_relative_path": case_csv_path.relative_to(
                destination
            ).as_posix(),
            "case_csv_sha256": case_csv_sha,
        }
        case_rows.append(row)
        event_rows.extend(case_event_rows)
        case_payloads.append(payload)
        artifact_rows.extend(
            (
                _artifact_row(destination, case_json_path),
                _artifact_row(destination, case_csv_path),
            )
        )

    per_case_path = destination / "identity_blocker_cases.csv"
    _write_csv(per_case_path, case_rows)
    per_event_path = destination / "identity_blocker_mapping_events.csv"
    _write_csv(per_event_path, event_rows)
    artifact_rows.extend(
        (
            _artifact_row(destination, per_case_path),
            _artifact_row(destination, per_event_path),
        )
    )

    aggregate = _aggregate_pack(
        scope,
        case_rows=case_rows,
        event_rows=event_rows,
        case_payloads=case_payloads,
        source_artifacts={
            "identity_blocker_cases.csv": _prefixed_file_sha256(
                per_case_path
            ),
            "identity_blocker_mapping_events.csv": (
                _prefixed_file_sha256(per_event_path)
            ),
        },
    )
    aggregate_path = destination / "identity_blocker_causal_pack.json"
    _write_json(aggregate_path, aggregate)
    artifact_rows.append(_artifact_row(destination, aggregate_path))

    report_path = destination / "D2_FORMAL_R0_IDENTITY_CAUSAL_AUDIT_CN.md"
    _write_chinese_report(report_path, aggregate)
    artifact_rows.append(_artifact_row(destination, report_path))

    inventory_path = destination / "artifact_inventory.json"
    inventory_payload = {
        "schema_version": FORMAL_IDENTITY_BLOCKER_INVENTORY_SCHEMA_VERSION,
        "source_git_commit": scope.source_git_commit,
        "execution_plan_sha256": scope.execution_plan_sha256,
        "diagnostic_pack_schema_version": (
            FORMAL_IDENTITY_BLOCKER_PACK_SCHEMA_VERSION
        ),
        "artifact_count": len(artifact_rows),
        "artifacts": sorted(artifact_rows, key=lambda item: item["path"]),
    }
    _write_json(inventory_path, inventory_payload)
    artifact_rows.append(_artifact_row(destination, inventory_path))

    sums_path = destination / "ARTIFACT_SHA256SUMS"
    sums_path.write_text(
        "".join(
            f"{_bare_sha256(item['sha256'], 'artifact sha256')}  "
            f"{item['path']}\n"
            for item in sorted(artifact_rows, key=lambda row: row["path"])
        ),
        encoding="utf-8",
    )
    result = {
        "output_dir": str(destination),
        "case_count": len(case_rows),
        "mapping_event_count": len(event_rows),
        "aggregate_path": str(aggregate_path),
        "aggregate_sha256": _prefixed_file_sha256(aggregate_path),
        "report_path": str(report_path),
        "report_sha256": _prefixed_file_sha256(report_path),
        "inventory_path": str(inventory_path),
        "inventory_sha256": _prefixed_file_sha256(inventory_path),
        "sha256sums_path": str(sums_path),
        "sha256sums_sha256": _prefixed_file_sha256(sums_path),
    }
    return result


def _aggregate_pack(
    scope: FormalIdentityAuditScope,
    *,
    case_rows: Sequence[Mapping[str, Any]],
    event_rows: Sequence[Mapping[str, Any]],
    case_payloads: Sequence[Mapping[str, Any]],
    source_artifacts: Mapping[str, str],
) -> dict[str, Any]:
    episode_reason_counts = Counter(
        str(row["strict_identity_metrics_reason"]) for row in case_rows
    )
    event_reason_counts = Counter(str(row["reason"]) for row in event_rows)
    classification_counts = Counter(
        str(row["causal_classification"]) for row in event_rows
    )
    commitment_reason_counts = Counter(
        str(row["commitment_reason"]) for row in event_rows
    )
    transition_counts = Counter(
        str(row["modality_transition"]) for row in event_rows
    )
    newest_sensor_counts = Counter(
        sensor_id
        for row in event_rows
        for sensor_id in str(row["newest_sensor_ids"]).split("|")
        if sensor_id
    )
    reason_grouped_event_counts: dict[str, dict[str, Any]] = {}
    for reason in sorted(event_reason_counts):
        reason_rows = [
            row for row in event_rows if str(row["reason"]) == reason
        ]
        reason_grouped_event_counts[reason] = {
            "event_count": len(reason_rows),
            "commitment_reason_event_counts": dict(
                sorted(
                    Counter(
                        str(row["commitment_reason"])
                        for row in reason_rows
                    ).items()
                )
            ),
            "sensor_modality_transition_event_counts": dict(
                sorted(
                    Counter(
                        str(row["modality_transition"])
                        for row in reason_rows
                    ).items()
                )
            ),
            "newest_sensor_event_counts": dict(
                sorted(
                    Counter(
                        sensor_id
                        for row in reason_rows
                        for sensor_id in str(
                            row["newest_sensor_ids"]
                        ).split("|")
                        if sensor_id
                    ).items()
                )
            ),
        }
    scale_rows: list[dict[str, Any]] = []
    scales = sorted({int(row["scale"]) for row in case_rows})
    for scale in scales:
        scale_cases = [row for row in case_rows if int(row["scale"]) == scale]
        scale_events = [row for row in event_rows if int(row["scale"]) == scale]
        scale_rows.append(
            {
                "scale": scale,
                "strict_unavailable_episode_count": len(scale_cases),
                "blocker_mapping_event_count": len(scale_events),
                "episode_reason_counts": dict(
                    sorted(
                        Counter(
                            str(row["strict_identity_metrics_reason"])
                            for row in scale_cases
                        ).items()
                    )
                ),
                "mapping_event_reason_counts": dict(
                    sorted(
                        Counter(
                            str(row["reason"]) for row in scale_events
                        ).items()
                    )
                ),
            }
        )
    scenario_rows: list[dict[str, Any]] = []
    scenarios = sorted({str(row["scenario"]) for row in case_rows})
    for scenario in scenarios:
        scenario_cases = [
            row for row in case_rows if str(row["scenario"]) == scenario
        ]
        scenario_events = [
            row for row in event_rows if str(row["scenario"]) == scenario
        ]
        scenario_rows.append(
            {
                "scenario": scenario,
                "strict_unavailable_episode_count": len(scenario_cases),
                "blocker_mapping_event_count": len(scenario_events),
                "episode_reason_counts": dict(
                    sorted(
                        Counter(
                            str(row["strict_identity_metrics_reason"])
                            for row in scenario_cases
                        ).items()
                    )
                ),
                "mapping_event_reason_counts": dict(
                    sorted(
                        Counter(
                            str(row["reason"]) for row in scenario_events
                        ).items()
                    )
                ),
            }
        )

    source_window_events = [
        row
        for row in event_rows
        if row["reason"] == "source_observation_outside_lineage_window"
    ]
    oldest_ages = [
        float(row["oldest_source_age_seconds"])
        for row in source_window_events
    ]
    newest_ages = [
        float(row["newest_source_age_seconds"])
        for row in source_window_events
    ]
    commitment_ages = [
        float(row["commitment_source_age_seconds"])
        for row in source_window_events
    ]
    return {
        "schema_version": FORMAL_IDENTITY_BLOCKER_PACK_SCHEMA_VERSION,
        "validation_date": "2026-07-31",
        "scope": scope.to_dict(),
        "diagnostic_contract": {
            "usage": "offline_causal_explanation_only",
            "online_d2_modified": False,
            "online_truth_used": False,
            "global_track_id_modified": False,
            "strict_unavailable_relabelled": False,
            "unavailable_backfilled_as_zero": False,
            "lineage_window_widened": False,
            "position_nearest_neighbor_identity_used": False,
            "evidence_layout_error_count": 0,
        },
        "strict_unavailable_episode_count": len(case_rows),
        "blocker_mapping_event_count": len(event_rows),
        "strict_unavailable_episode_reason_counts": dict(
            sorted(episode_reason_counts.items())
        ),
        "blocker_mapping_event_reason_counts": dict(
            sorted(event_reason_counts.items())
        ),
        "causal_classification_event_counts": dict(
            sorted(classification_counts.items())
        ),
        "commitment_reason_event_counts": dict(
            sorted(commitment_reason_counts.items())
        ),
        "sensor_modality_transition_event_counts": dict(
            sorted(transition_counts.items())
        ),
        "newest_sensor_event_counts": dict(
            sorted(newest_sensor_counts.items())
        ),
        "reason_grouped_event_counts": reason_grouped_event_counts,
        "scale_attribution": scale_rows,
        "scenario_attribution": scenario_rows,
        "source_window_age_seconds": {
            "event_count": len(source_window_events),
            "oldest_source": _summary(oldest_ages),
            "newest_source": _summary(newest_ages),
            "active_commitment_source": _summary(commitment_ages),
        },
        "case_artifacts": [
            {
                "cell_id": row["cell_id"],
                "episode_id": row["episode_id"],
                "strict_identity_metrics_reason": row[
                    "strict_identity_metrics_reason"
                ],
                "blocker_mapping_event_count": row[
                    "blocker_mapping_event_count"
                ],
                "case_json_relative_path": row[
                    "case_json_relative_path"
                ],
                "case_json_sha256": row["case_json_sha256"],
                "case_csv_relative_path": row[
                    "case_csv_relative_path"
                ],
                "case_csv_sha256": row["case_csv_sha256"],
            }
            for row in case_rows
        ],
        "source_artifacts": dict(sorted(source_artifacts.items())),
        "producer_replay_verified_episode_count": sum(
            bool(row["producer_replay_verified"]) for row in case_rows
        ),
        "source_hashes_verified_episode_count": sum(
            bool(row["source_hashes_verified"]) for row in case_rows
        ),
        "episode_identity_verified_episode_count": sum(
            bool(row["episode_identity_verified"]) for row in case_rows
        ),
        "online_truth_isolation_verified_episode_count": sum(
            bool(row["online_truth_isolation_verified"])
            for row in case_rows
        ),
        "formal_source_episode_count": scope.completed_episode_count,
        "formal_source_planned_episode_count": scope.planned_episode_count,
        "case_payload_count": len(case_payloads),
        "remaining_p1": [
            (
                "Use the frozen 36 cases and adjacent passing controls to "
                "design truth-free geometry/covariance/motion/source gates."
            ),
            (
                "Freeze a new producer commit and execution plan before any "
                "online algorithm candidate is rerun from shard 0."
            ),
            (
                "Keep strict availability, ID switches, continuity, track "
                "count, RMSE, and runtime as separate admission gates."
            ),
        ],
    }


def _event_csv_row(
    reference: FormalIdentityEpisodeReference,
    event: Mapping[str, Any],
) -> dict[str, Any]:
    commitment = _require_mapping(
        event.get("identity_commitment"),
        "causal event identity_commitment",
    )
    transition = _require_mapping(
        event.get("sensor_transition"),
        "causal event sensor_transition",
    )
    historical = _require_mapping(
        event.get("historical_truth_cluster"),
        "causal event historical_truth_cluster",
    )
    newest = _require_mapping(
        event.get("newest_observation_truth"),
        "causal event newest_observation_truth",
    )
    return {
        "cell_id": reference.cell_id,
        "shard_id": reference.shard_id,
        "shard_index": reference.shard_index,
        "scenario": reference.scenario,
        "scale": reference.scale,
        "seed": reference.seed,
        "episode_id": reference.episode_id,
        "event_id": event["event_id"],
        "reason": event["reason"],
        "causal_classification": event["causal_classification"],
        "frame_index": event["frame_index"],
        "frame_timestamp": event["frame_timestamp"],
        "global_track_id": event["global_track_id"],
        "lifecycle_state": event["lifecycle_state"],
        "association_state": event["association_state"],
        "candidate_truth_target_ids": "|".join(
            event["candidate_truth_target_ids"]
        ),
        "historical_truth_target_ids": "|".join(
            historical["truth_target_ids"]
        ),
        "newest_truth_target_ids": "|".join(
            newest["truth_target_ids"]
        ),
        "historical_sensor_ids": "|".join(
            transition["historical_sensor_ids"]
        ),
        "newest_sensor_ids": "|".join(
            transition["newest_sensor_ids"]
        ),
        "modality_transition": transition["modality_transition"],
        "source_observation_count": event["source_observation_count"],
        "oldest_source_age_seconds": event["oldest_source_age_seconds"],
        "newest_source_age_seconds": event["newest_source_age_seconds"],
        "lineage_time_window_s": event["lineage_time_window_s"],
        "identity_commitment_freshness_window_s": event[
            "identity_commitment_freshness_window_s"
        ],
        "strict_lineage_stale_observation_count": event[
            "strict_lineage_stale_observation_count"
        ],
        "freshness_stale_observation_count": event[
            "freshness_stale_observation_count"
        ],
        "commitment_state": commitment.get("state"),
        "commitment_reason": commitment.get("reason"),
        "commitment_generation": commitment.get("commitment_generation"),
        "commitment_source_evidence_key": commitment.get(
            "source_observation_evidence_key"
        ),
        "commitment_source_observation_id": commitment.get(
            "source_observation_id"
        ),
        "commitment_source_measurement_timestamp": commitment.get(
            "measurement_timestamp"
        ),
        "commitment_source_age_seconds": commitment.get(
            "source_age_seconds"
        ),
        "commitment_source_record_matched": commitment.get(
            "source_record_matched"
        ),
        "offline_causal_evidence_only": True,
        "online_correction_permitted": False,
    }


def _write_chinese_report(path: Path, aggregate: Mapping[str, Any]) -> None:
    episode_reasons = aggregate[
        "strict_unavailable_episode_reason_counts"
    ]
    event_reasons = aggregate["blocker_mapping_event_reason_counts"]
    classifications = aggregate["causal_classification_event_counts"]
    reason_groups = aggregate["reason_grouped_event_counts"]
    multi_truth_group = reason_groups.get(
        "multiple_truth_targets_for_global_track",
        {},
    )
    transitions = multi_truth_group.get(
        "sensor_modality_transition_event_counts",
        {},
    )
    sensors = multi_truth_group.get("newest_sensor_event_counts", {})
    commitment_reasons = multi_truth_group.get(
        "commitment_reason_event_counts",
        {},
    )
    scope = aggregate["scope"]
    scale_rows = aggregate["scale_attribution"]
    age = aggregate["source_window_age_seconds"]
    lines = [
        "# D2 正式 R0 严格身份不可用因果诊断",
        "",
        "## 结论",
        "",
        (
            f"本次只读检查覆盖正式 R0 已完成的 "
            f"{scope['completed_episode_count']}/"
            f"{scope['planned_episode_count']} 个 episode。严格身份指标在 "
            f"{aggregate['strict_unavailable_episode_count']} 个 episode "
            "不可用。这里的 episode 数与阻断映射事件数分开统计。"
        ),
        "",
        (
            "一航迹多真值涉及 "
            f"{episode_reasons.get('multiple_truth_targets_for_global_track', 0)} "
            "个 episode、"
            f"{event_reasons.get('multiple_truth_targets_for_global_track', 0)} "
            "个映射事件。来源观测超出谱系窗口涉及 "
            f"{episode_reasons.get('source_observation_outside_lineage_window', 0)} "
            "个 episode、"
            f"{event_reasons.get('source_observation_outside_lineage_window', 0)} "
            "个映射事件。不可用值保持为空，没有补写为零。"
        ),
        "",
        "## 证据边界",
        "",
        (
            f"输入根为 `{scope['execution_root']}`。producer commit 为 "
            f"`{scope['source_git_commit']}`，execution-plan 逻辑哈希为 "
            f"`sha256:{scope['execution_plan_sha256']}`。"
        ),
        "",
        (
            "发现过程校验 execution plan、shard plan、checkpoint、progress、"
            "cell result、episode identity、D6 manifest、D2 identity manifest "
            "及其来源文件哈希。每个入选 episode 随后重放既有 D2 离线 evaluator，"
            "重放结果必须与持久化结果逐字段一致。"
        ),
        "",
        (
            "诊断读取独立真值 sidecar 解释既有结果，只能离线使用。它不修改在线 "
            "D2，不拆分航迹，不重写全局航迹号，不用位置最近邻推断身份，也不改变"
            "冻结的 0.9 秒身份承诺新鲜度门控。"
        ),
        "",
        "## 一航迹多真值",
        "",
        (
            "全部一航迹多真值事件均记录历史真值簇、最新观测真值、来源传感器转换、"
            "身份承诺证据键和承诺原因。最新量测引入历史中尚未出现真值的事件为 "
            f"{classifications.get('newest_observation_introduced_new_truth', 0)}；"
            "历史谱系在最新量测前已经同时含多个真值的事件为 "
            f"{classifications.get('historical_multi_truth_already_present', 0)}。"
        ),
        "",
        (
            "该子集的身份承诺原因计数为："
            + _count_text(commitment_reasons)
            + "。"
        ),
        "",
        (
            "来源模态转换计数为："
            + "、".join(
                f"`{name}` {count}"
                for name, count in sorted(transitions.items())
                if name in {"radar->camera", "radar->radar"}
            )
            + "。最新相机来源分别为："
            + "、".join(
                f"`{name}` {count}"
                for name, count in sorted(sensors.items())
                if name.startswith("CAM-")
            )
            + "。"
        ),
        "",
        (
            "这些计数说明多真值合并与高密度、高规模证据相关，但不足以确认单一算法"
            "根因。后续在线候选只能使用几何、协方差、运动一致性、来源一致性、候选"
            "边和身份承诺状态等不含真值的信号。"
        ),
        "",
        "## 谱系超窗",
        "",
        (
            "历史谱系旧、当前承诺来源仍在 0.9 秒内的事件为 "
            f"{classifications.get('historical_lineage_only_stale', 0)}；"
            "当前承诺来源本身也超过 0.9 秒的事件为 "
            f"{classifications.get('active_commitment_source_stale', 0)}。"
        ),
        "",
        (
            "最老来源年龄范围为 "
            f"{_range_text(age['oldest_source'])} 秒，最新来源年龄范围为 "
            f"{_range_text(age['newest_source'])} 秒，当前承诺来源年龄范围为 "
            f"{_range_text(age['active_commitment_source'])} 秒。每个映射事件均保留"
            "逐来源量测时刻、帧时刻、年龄、关联状态、传感器和承诺更新时间轴。"
        ),
        "",
        (
            "该分类不重算既有严格判定。历史来源超窗仍是证据完整性问题；当前承诺"
            "来源超窗则同时暴露发布新鲜度问题。两类问题都不能通过放宽窗口直接关闭。"
        ),
        "",
        "## 规模分布",
        "",
        "| 规模 | 不可用 episode | 阻断映射事件 | episode 原因 | 事件原因 |",
        "| ---: | ---: | ---: | --- | --- |",
        *[
            (
                f"| {row['scale']} | "
                f"{row['strict_unavailable_episode_count']} | "
                f"{row['blocker_mapping_event_count']} | "
                f"{_count_text(row['episode_reason_counts'])} | "
                f"{_count_text(row['mapping_event_reason_counts'])} |"
            )
            for row in scale_rows
        ],
        "",
        (
            "一航迹多真值在 100 和 200 规模出现，5、20、50 规模未出现。该分布作为"
            "密度与规模相关证据保留，不能单独证明门控、匈牙利匹配、航迹起始或某一"
            "传感器是唯一原因。"
        ),
        "",
        "## 制品",
        "",
        "- `cases/<cell_id>.json`：逐案例完整因果证据和正式来源绑定。",
        "- `cases/<cell_id>.csv`：逐案例阻断映射事件。",
        "- `identity_blocker_cases.csv`：36 个 episode 摘要。",
        "- `identity_blocker_mapping_events.csv`：全部阻断映射事件。",
        "- `identity_blocker_causal_pack.json`：聚合计数、年龄和规模归因。",
        "- `artifact_inventory.json` 与 `ARTIFACT_SHA256SUMS`：制品大小和 SHA-256。",
        "",
        "## 后续工作",
        "",
        (
            "D2 P1 下一步使用这 36 个失败样本及同规模、同场景相邻通过样本设计"
            "不含真值的候选门控和承诺策略。任何在线算法变化都必须冻结新 producer "
            "commit 和 execution plan，并从 shard 0 重新运行。旧 450 个 episode "
            "保持原判定，不重标注，也不与新候选结果拼接。"
        ),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _summary(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "mean": None, "max": None}
    return {
        "count": len(values),
        "min": min(values),
        "mean": fmean(values),
        "max": max(values),
    }


def _range_text(summary: Mapping[str, Any]) -> str:
    if int(summary["count"]) <= 0:
        return "不可用"
    return f"{float(summary['min']):.4f} 至 {float(summary['max']):.4f}"


def _count_text(value: Mapping[str, Any]) -> str:
    return "；".join(
        f"{name}={count}" for name, count in sorted(value.items())
    )


def _artifact_row(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _prefixed_file_sha256(path),
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise FormalIdentityBlockerAuditError(
            f"cannot_write_empty_csv:{path.name}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    if any(list(row) != fieldnames for row in rows):
        raise FormalIdentityBlockerAuditError(
            f"csv_field_order_mismatch:{path.name}"
        )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _verify_execution_plan_checksum(root: Path, actual_sha256: str) -> None:
    checksum_path = root / "EXECUTION_PLAN_SHA256"
    try:
        parts = checksum_path.read_text(encoding="utf-8").strip().split()
    except (OSError, UnicodeError) as exc:
        raise FormalIdentityBlockerAuditError(
            "execution_plan_checksum_manifest_missing"
        ) from exc
    if parts != [actual_sha256, "experiment_matrix_execution_plan.json"]:
        raise FormalIdentityBlockerAuditError(
            "execution_plan_file_sha256_mismatch"
        )


def _parse_shard_index(name: str, shard_count: int) -> int:
    expected_suffix = f"_of_{shard_count:03d}"
    if not name.startswith("shard_") or not name.endswith(expected_suffix):
        raise FormalIdentityBlockerAuditError(
            f"invalid_shard_directory_name:{name}"
        )
    value = name[len("shard_") : -len(expected_suffix)]
    if len(value) != 3 or not value.isdigit():
        raise FormalIdentityBlockerAuditError(
            f"invalid_shard_directory_name:{name}"
        )
    index = int(value)
    if index >= shard_count:
        raise FormalIdentityBlockerAuditError(
            f"shard_index_out_of_range:{name}"
        )
    return index


def _read_json(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FormalIdentityBlockerAuditError(
            f"cannot_load_json:{name}:{path}"
        ) from exc
    if not isinstance(value, dict):
        raise FormalIdentityBlockerAuditError(
            f"json_root_not_object:{name}:{path}"
        )
    return value


def _read_jsonl(path: Path, name: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise FormalIdentityBlockerAuditError(
            f"cannot_load_jsonl:{name}:{path}"
        ) from exc
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FormalIdentityBlockerAuditError(
                f"invalid_jsonl_row:{name}:{index}"
            ) from exc
        if not isinstance(value, dict):
            raise FormalIdentityBlockerAuditError(
                f"jsonl_row_not_object:{name}:{index}"
            )
        rows.append(value)
    return rows


def _read_sha256s(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise FormalIdentityBlockerAuditError(
            f"cannot_load_sha256s:{path}"
        ) from exc
    result: dict[str, str] = {}
    for line in lines:
        parts = line.split()
        if len(parts) != 2:
            raise FormalIdentityBlockerAuditError(
                f"invalid_sha256s_row:{path}"
            )
        digest = _bare_sha256(parts[0], "SHA256SUMS digest")
        filename = _identifier(parts[1], "SHA256SUMS filename")
        if filename in result:
            raise FormalIdentityBlockerAuditError(
                f"duplicate_sha256s_filename:{filename}"
            )
        result[filename] = digest
    return result


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FormalIdentityBlockerAuditError(f"mapping_required:{name}")
    return dict(value)


def _require_sequence(value: Any, name: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise FormalIdentityBlockerAuditError(f"sequence_required:{name}")
    return list(value)


def _identifier(value: Any, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise FormalIdentityBlockerAuditError(f"identifier_required:{name}")
    return result


def _git_commit(value: Any, name: str) -> str:
    result = _identifier(value, name).lower()
    if len(result) != 40 or any(
        character not in "0123456789abcdef" for character in result
    ):
        raise FormalIdentityBlockerAuditError(f"git_commit_required:{name}")
    return result


def _nonnegative_int(value: Any, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise FormalIdentityBlockerAuditError(
            f"integer_required:{name}"
        ) from exc
    if result < 0:
        raise FormalIdentityBlockerAuditError(
            f"nonnegative_integer_required:{name}"
        )
    return result


def _nonnegative_float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise FormalIdentityBlockerAuditError(
            f"float_required:{name}"
        ) from exc
    if not isfinite(result) or result < 0.0:
        raise FormalIdentityBlockerAuditError(
            f"nonnegative_finite_float_required:{name}"
        )
    return result


def _digest_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _prefixed_sha256(value: Any, name: str) -> str:
    return f"sha256:{_bare_sha256(value, name)}"


def _bare_sha256(value: Any, name: str) -> str:
    result = str(value).strip().lower()
    if result.startswith("sha256:"):
        result = result[7:]
    if len(result) != 64 or any(
        character not in "0123456789abcdef" for character in result
    ):
        raise FormalIdentityBlockerAuditError(f"sha256_required:{name}")
    return result


def _bare_file_sha256(path: Path) -> str:
    return _bare_sha256(sha256_file(path), f"file_sha256:{path}")


def _prefixed_file_sha256(path: Path) -> str:
    return f"sha256:{_bare_file_sha256(path)}"


def _verify_prefixed_file_hash(
    path: Path,
    expected: Any,
    name: str,
) -> str:
    expected_digest = _prefixed_sha256(expected, name)
    try:
        actual = sha256_file(path)
    except OSError as exc:
        raise FormalIdentityBlockerAuditError(
            f"source_artifact_missing:{name}:{path}"
        ) from exc
    if actual != expected_digest:
        raise FormalIdentityBlockerAuditError(
            f"source_artifact_sha256_mismatch:{name}"
        )
    return actual
