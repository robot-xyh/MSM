from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil

import pytest

from research_modules.scalable_3d_simulation import (
    formal_shard_archive as archive_module,
)
from research_modules.scalable_3d_simulation.artifact_archive import (
    inventory_artifact_tree,
)
from research_modules.scalable_3d_simulation.experiment_matrix import (
    ExperimentMatrixPlan,
)
from research_modules.scalable_3d_simulation.experiment_matrix_sharding import (
    create_experiment_matrix_execution_plan,
    merge_experiment_matrix_shards,
    run_experiment_matrix_shard,
    validate_experiment_matrix_shard_for_storage,
)
from research_modules.scalable_3d_simulation.formal_shard_archive import (
    FORMAL_SHARD_ARCHIVE_D6_BINDING_SCHEMA,
    FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME,
    FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME,
    FORMAL_SHARD_ARCHIVE_SCOPE_MERGE_SCHEMA,
    FORMAL_SHARD_ARCHIVE_STORAGE_MODE,
    FormalShardArchiveError,
    create_verified_formal_shard_archive,
    main,
    merge_verified_formal_shard_archives,
    restore_verified_formal_shard_archive,
    verify_formal_shard_archive,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig


ROOT = Path(__file__).resolve().parents[3]
ZSTD_AVAILABLE = shutil.which("zstd") is not None
pytestmark = pytest.mark.skipif(
    not ZSTD_AVAILABLE,
    reason="zstd executable is required",
)


def test_complete_shard_storage_validation_and_deterministic_archive(
    tmp_path: Path,
) -> None:
    plan, source = _completed_shard(tmp_path / "run")
    first_archive = tmp_path / "archive-a"
    second_archive = tmp_path / "archive-b"

    validation = validate_experiment_matrix_shard_for_storage(
        execution_plan_path=plan,
        shard_index=0,
    )
    assert validation["status"] == "verified_complete"
    assert validation["completed_cell_count"] == 1

    first = create_verified_formal_shard_archive(
        execution_plan_path=plan,
        shard_index=0,
        destination=first_archive,
        created_at_utc="2026-07-31T00:00:00+00:00",
        minimum_free_bytes=0,
    )
    second = create_verified_formal_shard_archive(
        execution_plan_path=plan,
        shard_index=0,
        destination=second_archive,
        created_at_utc="2026-07-31T00:00:00+00:00",
        minimum_free_bytes=0,
    )

    assert source.is_dir()
    assert first["status"] == "verified"
    assert first["source_verified"] is True
    assert first["source_deletion_performed"] is False
    assert first["archive_sha256"] == second["archive_sha256"]
    assert (
        first_archive / FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME
    ).read_bytes() == (
        second_archive / FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME
    ).read_bytes()


def test_archive_detects_source_mutation_during_compression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, source = _completed_shard(tmp_path / "run")
    destination = tmp_path / "archive"
    original = archive_module._create_deterministic_tar_zst

    def _compress_then_mutate(**kwargs: object) -> None:
        original(**kwargs)
        checkpoint = source / "checkpoint.json"
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        payload["resume_count"] = int(payload["resume_count"]) + 1
        checkpoint.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(
        archive_module,
        "_create_deterministic_tar_zst",
        _compress_then_mutate,
    )

    with pytest.raises(FormalShardArchiveError, match="source changed"):
        create_verified_formal_shard_archive(
            execution_plan_path=plan,
            shard_index=0,
            destination=destination,
            minimum_free_bytes=0,
        )

    assert source.is_dir()
    assert not destination.exists()


def test_archive_detects_compressed_payload_corruption(
    tmp_path: Path,
) -> None:
    plan, _ = _completed_shard(tmp_path / "run")
    archive = tmp_path / "archive"
    create_verified_formal_shard_archive(
        execution_plan_path=plan,
        shard_index=0,
        destination=archive,
        minimum_free_bytes=0,
    )
    payload_path = archive / FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME
    payload = bytearray(payload_path.read_bytes())
    payload[len(payload) // 2] ^= 0x01
    payload_path.write_bytes(payload)

    with pytest.raises(FormalShardArchiveError, match="SHA-256 mismatch"):
        verify_formal_shard_archive(
            archive,
            execution_plan_path=plan,
            shard_index=0,
        )


def test_archive_rejects_execution_plan_mismatch(tmp_path: Path) -> None:
    plan, _ = _completed_shard(tmp_path / "run")
    archive = tmp_path / "archive"
    create_verified_formal_shard_archive(
        execution_plan_path=plan,
        shard_index=0,
        destination=archive,
        minimum_free_bytes=0,
    )
    other_plan = _create_plan(tmp_path / "other", seed=29)

    with pytest.raises(FormalShardArchiveError, match="binding mismatch"):
        verify_formal_shard_archive(
            archive,
            execution_plan_path=other_plan,
            shard_index=0,
        )


def test_restore_is_canonical_safe_and_preserves_archive(
    tmp_path: Path,
) -> None:
    plan, source = _completed_shard(tmp_path / "run")
    archive = tmp_path / "archive"
    create_verified_formal_shard_archive(
        execution_plan_path=plan,
        shard_index=0,
        destination=archive,
        minimum_free_bytes=0,
    )
    original_inventory = inventory_artifact_tree(source)
    held_source = tmp_path / "source-held-by-test"
    source.rename(held_source)

    restored = restore_verified_formal_shard_archive(
        archive,
        execution_plan_path=plan,
        shard_index=0,
    )

    assert restored["status"] == "restored_and_verified"
    assert restored["archive_preserved"] is True
    assert archive.is_dir()
    assert held_source.is_dir()
    assert source.is_dir()
    assert inventory_artifact_tree(source) == original_inventory


def test_verify_rejects_source_changed_after_archive(
    tmp_path: Path,
) -> None:
    plan, source = _completed_shard(tmp_path / "run")
    archive = tmp_path / "archive"
    create_verified_formal_shard_archive(
        execution_plan_path=plan,
        shard_index=0,
        destination=archive,
        minimum_free_bytes=0,
    )
    checkpoint = source / "checkpoint.json"
    checkpoint.write_text(
        checkpoint.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(FormalShardArchiveError, match="source"):
        verify_formal_shard_archive(
            archive,
            execution_plan_path=plan,
            shard_index=0,
            source=source,
        )


def test_cli_pack_and_verify_preserve_source(tmp_path: Path) -> None:
    plan, source = _completed_shard(tmp_path / "run")
    archive = tmp_path / "archive"
    pack_result = tmp_path / "pack-result.json"
    verify_result = tmp_path / "verify-result.json"
    merge_result = tmp_path / "merge-result.json"

    assert (
        main(
            [
                "pack-shard",
                "--execution-plan",
                str(plan),
                "--shard-index",
                "0",
                "--destination",
                str(archive),
                "--minimum-free-gib",
                "0",
                "--result-json",
                str(pack_result),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "verify-shard",
                "--execution-plan",
                str(plan),
                "--shard-index",
                "0",
                "--archive",
                str(archive),
                "--source",
                str(source),
                "--result-json",
                str(verify_result),
            ]
        )
        == 0
    )
    assert source.is_dir()
    assert (
        json.loads(verify_result.read_text(encoding="utf-8"))["status"]
        == "verified"
    )
    assert (
        archive / FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME
    ).is_file()
    archives = tmp_path / "archives"
    archives.mkdir()
    archive.rename(archives / source.name)
    assert (
        main(
            [
                "merge-archives",
                "--repository-root",
                str(ROOT),
                "--execution-plan",
                str(plan),
                "--archive-root",
                str(archives),
                "--output",
                str(tmp_path / "archive-merge"),
                "--minimum-free-gib",
                "0",
                "--result-json",
                str(merge_result),
            ]
        )
        == 0
    )
    merged = json.loads(merge_result.read_text(encoding="utf-8"))
    assert merged["status"] == "verified_archive_scope_merged"
    assert Path(merged["paths"]["cells"]).is_file()
    assert source.is_dir()


def test_archive_scope_merge_matches_canonical_cells_and_cleans_staging(
    tmp_path: Path,
) -> None:
    plan, sources = _completed_scope(tmp_path / "run")
    canonical = merge_experiment_matrix_shards(
        root=ROOT,
        execution_plan_path=plan,
        output_dir=tmp_path / "canonical-merge",
    )
    archives = tmp_path / "archives"
    archives.mkdir()
    held_sources = tmp_path / "held-canonical-sources"
    held_sources.mkdir()
    for shard_index, source in enumerate(sources):
        create_verified_formal_shard_archive(
            execution_plan_path=plan,
            shard_index=shard_index,
            destination=archives / source.name,
            minimum_free_bytes=0,
        )
        source.rename(held_sources / source.name)
    (archives / "pack-and-verify-results.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    staging = tmp_path / "staging"

    result = merge_verified_formal_shard_archives(
        repository_root=ROOT,
        execution_plan_path=plan,
        archive_root=archives,
        output_dir=tmp_path / "archive-merge",
        staging_root=staging,
        minimum_free_bytes=0,
    )

    output = Path(result["output"])
    manifest = json.loads(
        (output / "experiment_matrix_scope_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    episode_index = json.loads(
        (output / "episode_dirs.json").read_text(encoding="utf-8")
    )
    assert result["peak_restored_shard_count"] == 1
    assert result["archive_source_preserved"] is True
    assert result["canonical_source_deletion_performed"] is False
    assert manifest["schema_version"] == (
        FORMAL_SHARD_ARCHIVE_SCOPE_MERGE_SCHEMA
    )
    assert manifest["storage_mode"] == FORMAL_SHARD_ARCHIVE_STORAGE_MODE
    assert manifest["archive_set_complete"] is True
    assert manifest["canonical_episode_directories_materialized"] is False
    assert [
        row["archive"]["directory_name"] for row in manifest["shards"]
    ] == [source.name for source in sources]
    assert episode_index["canonical_directories_materialized"] is False
    assert Path(canonical["cells"]).read_bytes() == (
        output / "experiment_matrix_scope_cells.csv"
    ).read_bytes()
    assert all((archives / source.name).is_dir() for source in sources)
    assert all((held_sources / source.name).is_dir() for source in sources)
    assert all(not source.exists() for source in sources)
    assert staging.is_dir()
    assert not list(staging.iterdir())


def test_archive_scope_merge_requires_exact_complete_archive_set(
    tmp_path: Path,
) -> None:
    plan, source = _completed_shard(tmp_path / "run")
    archives = tmp_path / "archives"
    archives.mkdir()
    output = tmp_path / "archive-merge"

    with pytest.raises(
        FormalShardArchiveError,
        match="archive directory set does not match",
    ):
        merge_verified_formal_shard_archives(
            repository_root=ROOT,
            execution_plan_path=plan,
            archive_root=archives,
            output_dir=output,
            minimum_free_bytes=0,
        )

    assert source.is_dir()
    assert not output.exists()


def test_archive_scope_merge_rejects_unexpected_archive_directory(
    tmp_path: Path,
) -> None:
    plan, source = _completed_shard(tmp_path / "run")
    archives = tmp_path / "archives"
    archives.mkdir()
    create_verified_formal_shard_archive(
        execution_plan_path=plan,
        shard_index=0,
        destination=archives / source.name,
        minimum_free_bytes=0,
    )
    (archives / "unexpected_archive").mkdir()
    output = tmp_path / "archive-merge"

    with pytest.raises(
        FormalShardArchiveError,
        match="archive directory set does not match",
    ):
        merge_verified_formal_shard_archives(
            repository_root=ROOT,
            execution_plan_path=plan,
            archive_root=archives,
            output_dir=output,
            minimum_free_bytes=0,
        )

    assert source.is_dir()
    assert not output.exists()


def test_archive_scope_merge_rejects_corruption_without_partial_output(
    tmp_path: Path,
) -> None:
    plan, source = _completed_shard(tmp_path / "run")
    archives = tmp_path / "archives"
    archives.mkdir()
    archive = archives / source.name
    create_verified_formal_shard_archive(
        execution_plan_path=plan,
        shard_index=0,
        destination=archive,
        minimum_free_bytes=0,
    )
    payload_path = archive / FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME
    payload = bytearray(payload_path.read_bytes())
    payload[len(payload) // 2] ^= 0x01
    payload_path.write_bytes(payload)
    output = tmp_path / "archive-merge"
    staging = tmp_path / "staging"

    with pytest.raises(FormalShardArchiveError, match="SHA-256 mismatch"):
        merge_verified_formal_shard_archives(
            repository_root=ROOT,
            execution_plan_path=plan,
            archive_root=archives,
            output_dir=output,
            staging_root=staging,
            minimum_free_bytes=0,
        )

    assert source.is_dir()
    assert archive.is_dir()
    assert not output.exists()
    assert staging.is_dir()
    assert not list(staging.iterdir())


def test_archive_scope_merge_honours_staging_free_space_floor(
    tmp_path: Path,
) -> None:
    plan, source = _completed_shard(tmp_path / "run")
    archives = tmp_path / "archives"
    archives.mkdir()
    create_verified_formal_shard_archive(
        execution_plan_path=plan,
        shard_index=0,
        destination=archives / source.name,
        minimum_free_bytes=0,
    )
    output = tmp_path / "archive-merge"
    staging = tmp_path / "staging"

    with pytest.raises(
        FormalShardArchiveError,
        match="insufficient destination capacity to restore",
    ):
        merge_verified_formal_shard_archives(
            repository_root=ROOT,
            execution_plan_path=plan,
            archive_root=archives,
            output_dir=output,
            staging_root=staging,
            minimum_free_bytes=10**18,
        )

    assert source.is_dir()
    assert not output.exists()
    assert staging.is_dir()
    assert not list(staging.iterdir())


@pytest.mark.parametrize("staging_name", ("output", ".output.partial"))
def test_archive_scope_merge_rejects_staging_publication_overlap(
    tmp_path: Path,
    staging_name: str,
) -> None:
    plan, source = _completed_shard(tmp_path / "run")
    archives = tmp_path / "archives"
    archives.mkdir()
    create_verified_formal_shard_archive(
        execution_plan_path=plan,
        shard_index=0,
        destination=archives / source.name,
        minimum_free_bytes=0,
    )
    output = tmp_path / "output"

    with pytest.raises(FormalShardArchiveError, match="must not overlap"):
        merge_verified_formal_shard_archives(
            repository_root=ROOT,
            execution_plan_path=plan,
            archive_root=archives,
            output_dir=output,
            staging_root=tmp_path / staging_name,
            minimum_free_bytes=0,
        )

    assert source.is_dir()
    assert not output.exists()
    assert not (tmp_path / ".output.partial").exists()


def test_archive_scope_merge_writes_d6_report_after_source_is_unavailable(
    tmp_path: Path,
) -> None:
    plan, source = _completed_shard(tmp_path / "run")
    archives = tmp_path / "archives"
    archives.mkdir()
    create_verified_formal_shard_archive(
        execution_plan_path=plan,
        shard_index=0,
        destination=archives / source.name,
        minimum_free_bytes=0,
    )
    held_source = tmp_path / "held-source"
    source.rename(held_source)
    staging = tmp_path / "staging"

    result = merge_verified_formal_shard_archives(
        repository_root=ROOT,
        execution_plan_path=plan,
        archive_root=archives,
        output_dir=tmp_path / "archive-merge",
        staging_root=staging,
        write_d6_report=True,
        minimum_free_bytes=0,
    )

    csv_path = Path(result["paths"]["d6_per_episode_seed_csv"])
    aggregate_path = Path(result["paths"]["d6_aggregate_json"])
    report_path = Path(result["paths"]["d6_markdown"])
    binding_path = Path(result["paths"]["d6_binding"])
    merge_manifest = json.loads(
        Path(result["paths"]["manifest"]).read_text(encoding="utf-8")
    )
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    episode_index = json.loads(
        Path(result["paths"]["episode_dirs"]).read_text(encoding="utf-8")
    )
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["episode_dir"] == str(
        (
            plan.parent
            / episode_index["paths_relative_to_execution_root"][0]
        ).resolve()
    )
    assert rows[0]["d2_id_switch_count_availability"] in {
        "available",
        "unavailable",
    }
    assert json.loads(aggregate_path.read_text(encoding="utf-8"))[
        "episode_count"
    ] == 1
    assert report_path.is_file()
    assert binding["schema_version"] == FORMAL_SHARD_ARCHIVE_D6_BINDING_SCHEMA
    assert binding["episode_count"] == 1
    assert set(binding["artifacts"]) == {
        "aggregate_json",
        "markdown",
        "module_performance_evidence",
        "per_episode_seed_csv",
        "stage_timing_curve",
    }
    assert merge_manifest["d6_evaluation_generated"] is True
    assert merge_manifest["d6_evaluation_binding_sha256"] == (
        archive_module._sha256_file(binding_path)
    )
    checksum_names = {
        line.split("  ", maxsplit=1)[1]
        for line in Path(result["paths"]["checksums"])
        .read_text(encoding="utf-8")
        .splitlines()
    }
    assert binding_path.name in checksum_names
    assert held_source.is_dir()
    assert not source.exists()
    assert not list(staging.iterdir())


def _completed_shard(root: Path) -> tuple[Path, Path]:
    plan = _create_plan(root, seed=17)
    result = run_experiment_matrix_shard(
        root=ROOT,
        execution_plan_path=plan,
        shard_index=0,
        minimum_free_bytes=0,
    )
    assert result["status"] == "complete"
    return plan, Path(result["shard_dir"])


def _completed_scope(root: Path) -> tuple[Path, tuple[Path, ...]]:
    plan = create_experiment_matrix_execution_plan(
        root=ROOT,
        output_root=root,
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
            seeds=(17, 18),
            duration_s=0.05,
            formal=False,
        ),
        scope_variants=("R0",),
        shard_count=2,
        created_at_utc="2026-07-31T00:00:00+00:00",
    )
    sources: list[Path] = []
    for shard_index in range(2):
        result = run_experiment_matrix_shard(
            root=ROOT,
            execution_plan_path=plan,
            shard_index=shard_index,
            minimum_free_bytes=0,
        )
        assert result["status"] == "complete"
        sources.append(Path(result["shard_dir"]))
    return plan, tuple(sources)


def _create_plan(root: Path, *, seed: int) -> Path:
    return create_experiment_matrix_execution_plan(
        root=ROOT,
        output_root=root,
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
            seeds=(seed,),
            duration_s=0.05,
            formal=False,
        ),
        scope_variants=("R0",),
        shard_count=1,
        created_at_utc="2026-07-31T00:00:00+00:00",
    )
