from __future__ import annotations

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
    run_experiment_matrix_shard,
    validate_experiment_matrix_shard_for_storage,
)
from research_modules.scalable_3d_simulation.formal_shard_archive import (
    FORMAL_SHARD_ARCHIVE_MANIFEST_FILENAME,
    FORMAL_SHARD_ARCHIVE_PAYLOAD_FILENAME,
    FormalShardArchiveError,
    create_verified_formal_shard_archive,
    main,
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
