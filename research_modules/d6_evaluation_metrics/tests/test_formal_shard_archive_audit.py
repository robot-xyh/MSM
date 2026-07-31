from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

import d6_evaluation_metrics.formal_r0_full_posterior_audit as full_audit_module
import d6_evaluation_metrics.formal_shard_archive_audit as archive_audit_module
from d6_evaluation_metrics.formal_r0_full_posterior_audit import (
    FORMAL_R0_FULL_POSTERIOR_INPUT_SCHEMA_VERSION,
    FormalR0FullPosteriorAuditInputs,
    audit_formal_r0_full_posterior,
    compact_formal_r0_full_posterior_result,
    load_formal_r0_full_posterior_audit_inputs,
    render_formal_r0_full_posterior_audit_markdown,
)
from d6_evaluation_metrics.formal_r0_targeted_posterior_audit import (
    FormalR0TargetCell,
)
from d6_evaluation_metrics.formal_shard_archive_audit import (
    FORMAL_SHARD_ARCHIVE_D6_BINDING_SCHEMA,
    FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
    FormalShardArchiveAuditError,
    _audit_archive_d6_binding,
    audit_archive_merge_bundle,
    audit_formal_shard_archives,
    verify_and_restore_formal_shard_archive,
)
from research_modules.scalable_3d_simulation.experiment_matrix import (
    ExperimentMatrixPlan,
)
from research_modules.scalable_3d_simulation.experiment_matrix_sharding import (
    create_experiment_matrix_execution_plan,
    run_experiment_matrix_shard,
)
from research_modules.scalable_3d_simulation.formal_shard_archive import (
    create_verified_formal_shard_archive,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig


ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(
    shutil.which("zstd") is None,
    reason="zstd executable is required",
)


def test_archive_root_is_optional_in_v1_config(tmp_path: Path) -> None:
    config = tmp_path / "audit.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": FORMAL_R0_FULL_POSTERIOR_INPUT_SCHEMA_VERSION,
                "execution_root": str(tmp_path / "execution"),
                "source_repository": str(tmp_path / "source"),
                "archive_root": str(tmp_path / "archives"),
                "expected_source_git_commit": "a" * 40,
                "expected_execution_plan_sha256": "b" * 64,
                "expected_scope_cell_count": 20,
                "expected_parent_cell_count": 20,
                "expected_shard_count": 20,
                "expected_cells_per_shard": 1,
                "merged_scope_relative_path": "merged_scope_from_archives",
            }
        ),
        encoding="utf-8",
    )

    inputs = load_formal_r0_full_posterior_audit_inputs(config)

    assert inputs.archive_root == (tmp_path / "archives").resolve()
    assert inputs.merged_scope_dir == (
        tmp_path / "execution" / "merged_scope_from_archives"
    ).resolve()


def test_full_audit_dispatches_archive_mode_without_raw_shards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution = tmp_path / "execution"
    execution.mkdir()
    cells = [
        {
            "cell_id": f"cell_{index}",
            "comparison_key": f"nominal|1|{index}",
            "global_index": index,
            "scope_index": index,
            "shard_index": index,
            "shard_sequence": 0,
            "scale": 1,
            "scenario": "nominal",
            "seed": index,
            "variant": "R0",
        }
        for index in range(2)
    ]
    (execution / "experiment_matrix_execution_plan.json").write_text(
        json.dumps({"scope": {"cells": cells}}),
        encoding="utf-8",
    )
    rows = [_passing_row(cell) for cell in cells]
    monkeypatch.setattr(
        archive_audit_module,
        "audit_formal_shard_archives",
        lambda **_: {
            "verified": True,
            "failure_reasons": [],
            "low_level_audited_cell_count": 2,
            "verified_archive_count": 2,
            "cells": rows,
            "archives": [{"shard_index": 0}, {"shard_index": 1}],
            "source": {"verified": True},
            "execution_plan": {"verified": True},
            "execution_progress": {"verified": True},
        },
    )
    monkeypatch.setattr(
        archive_audit_module,
        "audit_archive_merge_bundle",
        lambda **_: {
            "verified": True,
            "failure_reasons": [],
            "cell_failure_reasons": {},
        },
    )
    monkeypatch.setattr(
        full_audit_module,
        "audit_merged_scope_csv",
        lambda *_, **__: {
            "verified": True,
            "failure_reasons": [],
            "cell_failure_reasons": {},
        },
    )
    inputs = FormalR0FullPosteriorAuditInputs(
        execution_root=execution,
        source_repository=tmp_path / "source",
        archive_root=tmp_path / "archives",
        expected_source_git_commit="a" * 40,
        expected_execution_plan_sha256="b" * 64,
        expected_scope_cell_count=2,
        expected_parent_cell_count=2,
        expected_shard_count=2,
        expected_cells_per_shard=1,
    )

    result = audit_formal_r0_full_posterior(inputs)

    assert result["verdict"] == "pass"
    assert result["inputs"]["archive_root"] == str((tmp_path / "archives").resolve())
    assert result["aggregate"]["verified_cell_count"] == 2
    assert result["scope_boundary"]["formal_r0_scope_completed_cell_count"] == 2
    assert result["scope_boundary"]["parent_matrix_completed_cell_count"] == 2
    compact = compact_formal_r0_full_posterior_result(result)
    assert compact["archive_set"]["verified"] is True
    markdown = render_formal_r0_full_posterior_audit_markdown(result)
    assert "正式 R0 低层审计" in markdown
    assert "20 个归档" in markdown


def test_archive_scope_boundary_uses_actual_zero_when_set_is_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution = tmp_path / "execution"
    execution.mkdir()
    cell = {
        "cell_id": "cell_0",
        "comparison_key": "nominal|1|0",
        "global_index": 0,
        "scope_index": 0,
        "shard_index": 0,
        "shard_sequence": 0,
        "scale": 1,
        "scenario": "nominal",
        "seed": 0,
        "variant": "R0",
    }
    (execution / "experiment_matrix_execution_plan.json").write_text(
        json.dumps({"scope": {"cells": [cell]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        archive_audit_module,
        "audit_formal_shard_archives",
        lambda **_: {
            "verified": False,
            "failure_reasons": ["archive_set_mismatch:missing=shard_000_of_001"],
            "low_level_audited_cell_count": 0,
            "verified_archive_count": 0,
            "cells": [],
            "archives": [],
            "source": {},
            "execution_plan": {},
            "execution_progress": {},
        },
    )
    monkeypatch.setattr(
        archive_audit_module,
        "audit_archive_merge_bundle",
        lambda **_: {
            "verified": False,
            "failure_reasons": ["archive_merge_root_unavailable"],
            "cell_failure_reasons": {},
        },
    )
    monkeypatch.setattr(
        full_audit_module,
        "audit_merged_scope_csv",
        lambda *_, **__: {
            "verified": False,
            "failure_reasons": ["merged_scope_csv_unreadable"],
            "cell_failure_reasons": {},
        },
    )
    result = audit_formal_r0_full_posterior(
        FormalR0FullPosteriorAuditInputs(
            execution_root=execution,
            source_repository=tmp_path / "source",
            archive_root=tmp_path / "archives",
            expected_source_git_commit="a" * 40,
            expected_execution_plan_sha256="b" * 64,
            expected_scope_cell_count=1,
            expected_parent_cell_count=2,
            expected_shard_count=1,
            expected_cells_per_shard=1,
        )
    )

    assert result["verdict"] == "fail_closed"
    assert result["scope_boundary"]["formal_r0_scope_completed_cell_count"] == 0
    assert result["scope_boundary"]["parent_matrix_completed_cell_count"] == 0
    assert result["scope_boundary"]["formal_r0_scope_complete"] is False


def test_independent_archive_verifier_restores_and_preserves_sources(
    tmp_path: Path,
) -> None:
    plan_path, source, archive = _completed_archive(tmp_path)
    plan = _read_json(plan_path)
    descriptor = plan["sharding"]["shards"][0]
    destination = tmp_path / "staging" / "shards" / descriptor["shard_id"]
    destination.mkdir(parents=True)

    manifest, result = verify_and_restore_formal_shard_archive(
        archive=archive,
        destination=destination,
        plan_path=plan_path,
        plan=plan,
        descriptor=descriptor,
        shard_index=0,
        expected_source_git_commit=plan["source"]["git_commit"],
        expected_execution_plan_sha256=plan["execution_plan_sha256"],
        expected_cells_per_shard=1,
        zstd_path=shutil.which("zstd") or "zstd",
    )

    assert result["payload_tree_sha256"] == manifest["inventory"]["tree_sha256"]
    assert destination.is_dir()
    assert source.is_dir()
    assert archive.is_dir()


@pytest.mark.parametrize("tamper", ("payload", "binding", "unsafe_path"))
def test_independent_archive_verifier_fails_closed_on_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    plan_path, source, archive = _completed_archive(tmp_path)
    plan = _read_json(plan_path)
    descriptor = plan["sharding"]["shards"][0]
    if tamper == "payload":
        path = archive / "shard_payload.tar.zst"
        payload = bytearray(path.read_bytes())
        payload[len(payload) // 2] ^= 1
        path.write_bytes(payload)
    else:
        manifest_path = archive / "shard_archive_manifest.json"
        manifest = _read_json(manifest_path)
        if tamper == "binding":
            manifest["binding"]["execution_plan_sha256"] = "f" * 64
        else:
            manifest["inventory"]["files"][0]["relative_path"] = "../escape"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _rewrite_archive_checksums(archive)
    destination = tmp_path / "staging" / "shard"
    destination.mkdir(parents=True)

    with pytest.raises(FormalShardArchiveAuditError):
        verify_and_restore_formal_shard_archive(
            archive=archive,
            destination=destination,
            plan_path=plan_path,
            plan=plan,
            descriptor=descriptor,
            shard_index=0,
            expected_source_git_commit=plan["source"]["git_commit"],
            expected_execution_plan_sha256=plan["execution_plan_sha256"],
            expected_cells_per_shard=1,
            zstd_path=shutil.which("zstd") or "zstd",
        )

    assert source.is_dir()
    assert archive.is_dir()


def test_archive_set_allows_regular_sidecar_files(tmp_path: Path) -> None:
    plan_path, source, archives = _completed_archive_root(tmp_path)
    sidecar = archives / "shard_000_of_001_verify_result.json"
    sidecar.write_text("{}\n", encoding="utf-8")
    plan = _read_json(plan_path)
    targets = tuple(
        FormalR0TargetCell(
            shard_index=int(cell["shard_index"]),
            cell_id=str(cell["cell_id"]),
        )
        for cell in plan["scope"]["cells"]
    )

    result = audit_formal_shard_archives(
        execution_root=plan_path.parent,
        source_repository=ROOT,
        archive_root=archives,
        expected_source_git_commit=plan["source"]["git_commit"],
        expected_execution_plan_sha256=plan["execution_plan_sha256"],
        expected_scope_cell_count=1,
        expected_shard_count=1,
        expected_cells_per_shard=1,
        plan=plan,
        targets=targets,
    )

    assert result["verified_archive_count"] == 1
    assert result["sidecar_files"] == [sidecar.name]
    assert not any(
        reason.startswith("archive_set_mismatch")
        for reason in result["failure_reasons"]
    )
    assert source.is_dir()
    assert sidecar.is_file()


def test_archive_set_rejects_extra_directory_without_deletion(
    tmp_path: Path,
) -> None:
    _, source, archives = _completed_archive_root(tmp_path)
    extra = archives / "unexpected"
    extra.mkdir()

    result = audit_formal_shard_archives(
        execution_root=tmp_path / "execution",
        source_repository=tmp_path / "source",
        archive_root=archives,
        expected_source_git_commit="a" * 40,
        expected_execution_plan_sha256="b" * 64,
        expected_scope_cell_count=1,
        expected_shard_count=1,
        expected_cells_per_shard=1,
        plan={},
        targets=(),
    )

    assert result["verified"] is False
    assert "extra=unexpected" in result["failure_reasons"][0]
    assert extra.is_dir()
    assert source.is_dir()


def test_archive_set_rejects_symlink_entry(tmp_path: Path) -> None:
    _, source, archives = _completed_archive_root(tmp_path)
    target = tmp_path / "sidecar.json"
    target.write_text("{}\n", encoding="utf-8")
    link = archives / "sidecar-link.json"
    link.symlink_to(target)

    result = audit_formal_shard_archives(
        execution_root=tmp_path / "execution",
        source_repository=tmp_path / "source",
        archive_root=archives,
        expected_source_git_commit="a" * 40,
        expected_execution_plan_sha256="b" * 64,
        expected_scope_cell_count=1,
        expected_shard_count=1,
        expected_cells_per_shard=1,
        plan={},
        targets=(),
    )

    assert result["verified"] is False
    assert result["failure_reasons"] == [
        "archive_root_symlink_entry:sidecar-link.json"
    ]
    assert link.is_symlink()
    assert source.is_dir()


def test_archive_root_symlink_is_preserved_and_rejected(tmp_path: Path) -> None:
    real_root = tmp_path / "real-archives"
    real_root.mkdir()
    archive_link = tmp_path / "archive-link"
    archive_link.symlink_to(real_root, target_is_directory=True)
    inputs = FormalR0FullPosteriorAuditInputs(
        execution_root=tmp_path / "execution",
        source_repository=tmp_path / "source",
        archive_root=archive_link,
        expected_source_git_commit="a" * 40,
        expected_execution_plan_sha256="b" * 64,
        expected_scope_cell_count=1,
        expected_parent_cell_count=1,
        expected_shard_count=1,
        expected_cells_per_shard=1,
    )

    assert inputs.archive_root == archive_link.absolute()
    assert inputs.archive_root.is_symlink()
    result = audit_formal_shard_archives(
        execution_root=inputs.execution_root,
        source_repository=inputs.source_repository,
        archive_root=inputs.archive_root,
        expected_source_git_commit=inputs.expected_source_git_commit,
        expected_execution_plan_sha256=inputs.expected_execution_plan_sha256,
        expected_scope_cell_count=1,
        expected_shard_count=1,
        expected_cells_per_shard=1,
        plan={},
        targets=(),
    )
    assert result["verified"] is False
    assert result["failure_reasons"][0].startswith(
        "archive_root_unavailable_or_unsafe:"
    )


def test_d6_report_binding_recomputes_size_and_digest(tmp_path: Path) -> None:
    artifacts: dict[str, dict[str, object]] = {}
    for index, name in enumerate(
        (
            "aggregate_json",
            "markdown",
            "module_performance_evidence",
            "per_episode_seed_csv",
            "stage_timing_curve",
        )
    ):
        path = tmp_path / "d6_evaluation" / f"artifact_{index}.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"artifact-{index}".encode())
        artifacts[name] = {
            "relative_path": path.relative_to(tmp_path).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
    binding = {
        "schema_version": FORMAL_SHARD_ARCHIVE_D6_BINDING_SCHEMA,
        "storage_mode": FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
        "execution_plan_sha256": "b" * 64,
        "episode_count": 3,
        "scope_indices": [0, 1, 2],
        **_valid_evaluator_provenance(),
        "artifacts": artifacts,
    }

    assert _audit_archive_d6_binding(
        root=tmp_path,
        payload=binding,
        expected_execution_plan_sha256="b" * 64,
        expected_scope_cell_count=3,
    ) == []

    for field, invalid, expected_reason in (
        (
            "evaluator_schema_versions",
            [],
            "archive_d6_binding_evaluator_schema_versions_invalid",
        ),
        (
            "evaluator_git_commits",
            ["not-a-git-id"],
            "archive_d6_binding_evaluator_git_commits_invalid",
        ),
        (
            "evaluator_repository_dirty_values",
            ["false"],
            "archive_d6_binding_evaluator_repository_dirty_values_invalid",
        ),
        (
            "evaluator_source_tree_sha256s",
            [],
            "archive_d6_binding_evaluator_source_tree_sha256s_invalid",
        ),
        (
            "evaluator_source_tree_sha256s",
            [""],
            "archive_d6_binding_evaluator_source_tree_sha256s_invalid",
        ),
        (
            "evaluator_source_tree_sha256s",
            ["b" * 64],
            "archive_d6_binding_evaluator_source_tree_sha256s_invalid",
        ),
        (
            "evaluator_source_tree_sha256s",
            ["sha512:" + "b" * 64],
            "archive_d6_binding_evaluator_source_tree_sha256s_invalid",
        ),
        (
            "evaluator_source_tree_sha256s",
            ["sha256:" + "g" * 64],
            "archive_d6_binding_evaluator_source_tree_sha256s_invalid",
        ),
    ):
        invalid_binding = dict(binding)
        invalid_binding[field] = invalid
        assert expected_reason in _audit_archive_d6_binding(
            root=tmp_path,
            payload=invalid_binding,
            expected_execution_plan_sha256="b" * 64,
            expected_scope_cell_count=3,
        )
    deleted_binding = dict(binding)
    deleted_binding.pop("evaluator_git_commits")
    assert "archive_d6_binding_evaluator_git_commits_invalid" in (
        _audit_archive_d6_binding(
            root=tmp_path,
            payload=deleted_binding,
            expected_execution_plan_sha256="b" * 64,
            expected_scope_cell_count=3,
        )
    )

    tampered = tmp_path / str(artifacts["markdown"]["relative_path"])
    tampered.write_bytes(tampered.read_bytes() + b"tamper")
    reasons = _audit_archive_d6_binding(
        root=tmp_path,
        payload=binding,
        expected_execution_plan_sha256="b" * 64,
        expected_scope_cell_count=3,
    )
    assert "archive_d6_artifact_size_mismatch:markdown" in reasons
    assert "archive_d6_artifact_digest_mismatch:markdown" in reasons


def test_archive_merge_bundle_fails_closed_when_scope_cell_is_missing(
    tmp_path: Path,
) -> None:
    root, archive_record = _write_merge_bundle(tmp_path)
    passing = audit_archive_merge_bundle(
        merged_scope_dir=root,
        expected_source_git_commit="a" * 40,
        expected_execution_plan_sha256="b" * 64,
        expected_scope_cell_count=1,
        expected_parent_cell_count=2,
        expected_shard_count=1,
        archive_records=(archive_record,),
    )
    assert passing["verified"] is True

    cells = root / "experiment_matrix_scope_cells.csv"
    cells.write_text("scope_index,episode_relative_path\n", encoding="utf-8")
    _rewrite_merge_checksums(root)
    failed = audit_archive_merge_bundle(
        merged_scope_dir=root,
        expected_source_git_commit="a" * 40,
        expected_execution_plan_sha256="b" * 64,
        expected_scope_cell_count=1,
        expected_parent_cell_count=2,
        expected_shard_count=1,
        archive_records=(archive_record,),
    )
    assert failed["verified"] is False
    assert "archive_merge_cells_count_mismatch" in failed["failure_reasons"]


@pytest.mark.parametrize(
    ("tamper", "expected_reason"),
    (
        ("duplicate", "archive_merge_duplicate_shard_index"),
        ("missing", "archive_merge_shard_index_set_mismatch"),
        ("order", "archive_merge_shard_order_mismatch"),
        ("cell_count", "archive_merge_shard_cell_count_mismatch:0"),
    ),
)
def test_archive_merge_rejects_shard_manifest_tamper(
    tmp_path: Path,
    tamper: str,
    expected_reason: str,
) -> None:
    root, archive_records = _write_two_shard_merge_bundle(tmp_path)
    manifest_path = root / "experiment_matrix_scope_manifest.json"
    manifest = _read_json(manifest_path)
    shards = manifest["shards"]
    if tamper == "duplicate":
        shards[1]["shard_index"] = 0
    elif tamper == "missing":
        shards.pop()
    elif tamper == "order":
        shards.reverse()
    else:
        shards[0]["cell_count"] = 2
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )
    _rewrite_merge_checksums(root)

    result = audit_archive_merge_bundle(
        merged_scope_dir=root,
        expected_source_git_commit="a" * 40,
        expected_execution_plan_sha256="b" * 64,
        expected_scope_cell_count=2,
        expected_parent_cell_count=3,
        expected_shard_count=2,
        archive_records=archive_records,
    )

    assert result["verified"] is False
    assert any(
        reason == expected_reason or reason.startswith(expected_reason)
        for reason in result["failure_reasons"]
    )


@pytest.mark.parametrize("symlink_target", ("core", "artifact", "artifact_parent"))
def test_archive_merge_rejects_symlinked_evidence(
    tmp_path: Path,
    symlink_target: str,
) -> None:
    root, archive_record = _write_merge_bundle(tmp_path)
    if symlink_target == "core":
        path = root / "experiment_matrix_scope_cells.csv"
        real = root / "real_cells.csv"
        path.rename(real)
        path.symlink_to(real)
    elif symlink_target == "artifact":
        binding = _read_json(root / "archive_d6_evaluation_binding.json")
        relative = binding["artifacts"]["markdown"]["relative_path"]
        path = root / relative
        real = root / "real_markdown.bin"
        path.rename(real)
        path.symlink_to(real)
    else:
        directory = root / "d6_evaluation"
        real = root / "real_d6_evaluation"
        directory.rename(real)
        directory.symlink_to(real, target_is_directory=True)
    _rewrite_merge_checksums(root)

    result = audit_archive_merge_bundle(
        merged_scope_dir=root,
        expected_source_git_commit="a" * 40,
        expected_execution_plan_sha256="b" * 64,
        expected_scope_cell_count=1,
        expected_parent_cell_count=2,
        expected_shard_count=1,
        archive_records=(archive_record,),
    )

    assert result["verified"] is False
    assert any(
        "unreadable" in reason
        or "archive_d6_artifact_missing" in reason
        or "archive_d6_artifact_symlink" in reason
        for reason in result["failure_reasons"]
    )


def _completed_archive(tmp_path: Path) -> tuple[Path, Path, Path]:
    plan_path = create_experiment_matrix_execution_plan(
        root=ROOT,
        output_root=tmp_path / "run",
        base_config=ScenarioConfig(
            target_count=1,
            resource_count=1,
            recon_count=0,
            duration_s=0.05,
            metadata={"online_truth_policy": "forbidden"},
        ),
        parent_plan=ExperimentMatrixPlan(
            variants=("R0",),
            scenarios=("nominal",),
            scales=(1,),
            seeds=(17,),
            duration_s=0.05,
            formal=False,
        ),
        scope_variants=("R0",),
        shard_count=1,
        created_at_utc="2026-07-31T00:00:00+00:00",
    )
    result = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=plan_path,
        shard_index=0,
        minimum_free_bytes=0,
    )
    source = Path(result["shard_dir"])
    archive = tmp_path / "archive"
    create_verified_formal_shard_archive(
        execution_plan_path=plan_path,
        shard_index=0,
        destination=archive,
        minimum_free_bytes=0,
    )
    return plan_path, source, archive


def _completed_archive_root(tmp_path: Path) -> tuple[Path, Path, Path]:
    plan_path, source, archive = _completed_archive(tmp_path)
    archives = tmp_path / "archives"
    archives.mkdir()
    archive.rename(archives / source.name)
    return plan_path, source, archives


def _rewrite_archive_checksums(archive: Path) -> None:
    manifest = archive / "shard_archive_manifest.json"
    payload = archive / "shard_payload.tar.zst"
    (archive / "SHA256SUMS").write_text(
        f"{_sha256(manifest)}  {manifest.name}\n"
        f"{_sha256(payload)}  {payload.name}\n",
        encoding="utf-8",
    )


def _write_merge_bundle(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    root = tmp_path / "merged"
    root.mkdir()
    d6_artifacts: dict[str, dict[str, object]] = {}
    for index, name in enumerate(
        sorted(
            {
                "aggregate_json",
                "markdown",
                "module_performance_evidence",
                "per_episode_seed_csv",
                "stage_timing_curve",
            }
        )
    ):
        path = root / "d6_evaluation" / f"artifact_{index}.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        d6_artifacts[name] = {
            "relative_path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
    binding_path = root / "archive_d6_evaluation_binding.json"
    binding_path.write_text(
        json.dumps(
            {
                "schema_version": FORMAL_SHARD_ARCHIVE_D6_BINDING_SCHEMA,
                "storage_mode": FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
                "execution_plan_sha256": "b" * 64,
                "episode_count": 1,
                "scope_indices": [0],
                **_valid_evaluator_provenance(),
                "artifacts": d6_artifacts,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    archive_record: dict[str, object] = {
        "shard_index": 0,
        "shard_id": "shard_000_of_001",
        "archive_manifest_sha256": "c" * 64,
        "archive_checksum_file_sha256": "d" * 64,
        "payload_sha256": "e" * 64,
        "payload_tree_sha256": "f" * 64,
        "archive_size_bytes": 10,
        "file_count": 3,
        "total_size_bytes": 100,
        "binding": {
            "shard_index": 0,
            "shard_id": "shard_000_of_001",
            "completed_cell_count": 1,
            "shard_plan_sha256": "1" * 64,
            "progress_sha256": "2" * 64,
            "checkpoint_sha256": "3" * 64,
        },
    }
    manifest = {
        "schema_version": "scalable3d-formal-shard-archive-scope-merge-v1",
        "storage_mode": FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
        "source_git_commit": "a" * 40,
        "source_repository_dirty": False,
        "execution_plan_sha256": "b" * 64,
        "scope_expected_cell_count": 1,
        "scope_completed_cell_count": 1,
        "parent_full_cell_count": 2,
        "scope_complete": True,
        "formal_scope_complete": True,
        "archive_set_complete": True,
        "canonical_episode_directories_materialized": False,
        "peak_restored_shard_count": 1,
        "d6_evaluation_generated": True,
        "d6_evaluation_binding_sha256": _sha256(binding_path),
        "shards": [
            {
                **archive_record["binding"],
                "cell_count": 1,
                "archive": {
                    "directory_name": "shard_000_of_001",
                    "archive_format": "deterministic-pax-tar-zstd-v1",
                    **{
                        key: archive_record[key]
                        for key in (
                            "archive_manifest_sha256",
                            "archive_checksum_file_sha256",
                            "payload_sha256",
                            "payload_tree_sha256",
                            "archive_size_bytes",
                            "file_count",
                            "total_size_bytes",
                        )
                    },
                },
            }
        ],
    }
    (root / "experiment_matrix_scope_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )
    relative = "shards/shard_000_of_001/cells/cell_0/episode"
    (root / "experiment_matrix_scope_cells.csv").write_text(
        "scope_index,episode_relative_path\n" f"0,{relative}\n",
        encoding="utf-8",
    )
    (root / "episode_dirs.json").write_text(
        json.dumps(
            {
                "schema_version": "scalable3d-formal-shard-archive-scope-merge-v1",
                "storage_mode": FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
                "execution_plan_sha256": "b" * 64,
                "episode_count": 1,
                "canonical_directories_materialized": False,
                "paths_relative_to_execution_root": [relative],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    _rewrite_merge_checksums(root)
    return root, archive_record


def _write_two_shard_merge_bundle(
    tmp_path: Path,
) -> tuple[Path, tuple[dict[str, object], ...]]:
    root, first = _write_merge_bundle(tmp_path)
    second = json.loads(json.dumps(first))
    second["shard_index"] = 1
    second["shard_id"] = "shard_001_of_002"
    second["binding"]["shard_index"] = 1
    second["binding"]["shard_id"] = "shard_001_of_002"
    first["shard_id"] = "shard_000_of_002"
    first["binding"]["shard_id"] = "shard_000_of_002"

    binding_path = root / "archive_d6_evaluation_binding.json"
    binding = _read_json(binding_path)
    binding["episode_count"] = 2
    binding["scope_indices"] = [0, 1]
    binding_path.write_text(json.dumps(binding, sort_keys=True), encoding="utf-8")

    manifest_path = root / "experiment_matrix_scope_manifest.json"
    manifest = _read_json(manifest_path)
    manifest["scope_expected_cell_count"] = 2
    manifest["scope_completed_cell_count"] = 2
    manifest["parent_full_cell_count"] = 3
    first_row = manifest["shards"][0]
    first_row["shard_id"] = "shard_000_of_002"
    first_row["archive"]["directory_name"] = "shard_000_of_002"
    second_row = json.loads(json.dumps(first_row))
    second_row["shard_index"] = 1
    second_row["shard_id"] = "shard_001_of_002"
    second_row["archive"]["directory_name"] = "shard_001_of_002"
    manifest["shards"] = [first_row, second_row]
    manifest["d6_evaluation_binding_sha256"] = _sha256(binding_path)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    relatives = [
        "shards/shard_000_of_002/cells/cell_0/episode",
        "shards/shard_001_of_002/cells/cell_1/episode",
    ]
    (root / "experiment_matrix_scope_cells.csv").write_text(
        "scope_index,episode_relative_path\n"
        + "".join(f"{index},{relative}\n" for index, relative in enumerate(relatives)),
        encoding="utf-8",
    )
    episode_index = _read_json(root / "episode_dirs.json")
    episode_index["episode_count"] = 2
    episode_index["paths_relative_to_execution_root"] = relatives
    (root / "episode_dirs.json").write_text(
        json.dumps(episode_index, sort_keys=True),
        encoding="utf-8",
    )
    _rewrite_merge_checksums(root)
    return root, (first, second)


def _rewrite_merge_checksums(root: Path) -> None:
    names = (
        "archive_d6_evaluation_binding.json",
        "episode_dirs.json",
        "experiment_matrix_scope_cells.csv",
        "experiment_matrix_scope_manifest.json",
    )
    (root / "SHA256SUMS").write_text(
        "".join(f"{_sha256(root / name)}  {name}\n" for name in names),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_evaluator_provenance() -> dict[str, object]:
    return {
        "evaluator_schema_versions": ["d6.scalable-3d-offline-evaluation.v12"],
        "evaluator_git_commits": ["a" * 40],
        "evaluator_repository_dirty_values": [False],
        "evaluator_source_tree_sha256s": ["sha256:" + "b" * 64],
    }


def _passing_row(cell: dict[str, object]) -> dict[str, object]:
    row: dict[str, object] = {
        "cell_id": cell["cell_id"],
        "shard_index": cell["shard_index"],
        "scenario": cell["scenario"],
        "scale": cell["scale"],
        "seed": cell["seed"],
        "verified": True,
        "failure_reasons": [],
        "d2_id_switch_count": None,
        "d2_id_switch_count_availability": "unavailable",
        "d2_id_switch_count_unavailable_reason": "truth_pairing_unavailable",
    }
    values = {
        "online_truth_use_count": 0,
        "online_truth_field_violation_count": 0,
        "finite_state": True,
        "formal_acceptance_eligible": True,
        "experiment_matrix_formal_acceptance_eligible": True,
        "d1_posterior_generation": 1,
        "d1_full_posterior_publication_count": 1,
        "d2_consumed_d1_posterior_generation": 1,
        "d2_posterior_consumption_count": 1,
        "d2_association_publication_count": 1,
        "d2_pre_tick_posterior_merge_count": 0,
        "d2_finalize_unchanged_posterior_skip_count": 0,
        "d2_pending_generation_empty": True,
        "observation_governance_generation_integrity": True,
        "observation_governance_generation_contract_status": "verified",
        "d4_advice_resource_quota_conservation_violation_count": 0,
        "d4_advice_formal_decision_mutation_count": 0,
        "d4_current_d3_plan_binding_verified": True,
        "d4_current_plan_coalition_commit_verified": True,
        "d5_active_vision_target_reference_violation_count": 0,
        "d5_active_vision_ack_target_mismatch_count": 0,
    }
    for field, value in values.items():
        row[field] = value
        row[f"{field}_availability"] = "available"
        row[f"{field}_unavailable_reason"] = None
    return row
