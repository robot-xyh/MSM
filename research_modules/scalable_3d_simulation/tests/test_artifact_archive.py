from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.artifact_archive import (
    ARCHIVE_CHECKSUM_FILENAME,
    ARCHIVE_MANIFEST_FILENAME,
    ARCHIVE_PAYLOAD_DIRECTORY,
    ArtifactArchiveError,
    create_verified_artifact_archive,
    inventory_artifact_tree,
    main,
    verify_artifact_archive,
    write_artifact_inventory,
)


def _source_tree(root: Path) -> Path:
    source = root / "formal_outputs"
    (source / "shard_000" / "cell_001").mkdir(parents=True)
    (source / "shard_000" / "cell_001" / "summary.json").write_text(
        '{"finite_state": true}\n',
        encoding="utf-8",
    )
    (source / "progress.jsonl").write_text(
        '{"cell_id": "cell_001"}\n',
        encoding="utf-8",
    )
    return source


def test_inventory_is_deterministic_and_content_addressed(
    tmp_path: Path,
) -> None:
    source = _source_tree(tmp_path)
    first = inventory_artifact_tree(source)
    second = inventory_artifact_tree(source)

    assert first == second
    assert first["file_count"] == 2
    assert first["total_size_bytes"] > 0
    assert len(first["tree_sha256"]) == 64
    assert [
        record["relative_path"] for record in first["files"]
    ] == [
        "progress.jsonl",
        "shard_000/cell_001/summary.json",
    ]


def test_inventory_output_must_remain_outside_source(
    tmp_path: Path,
) -> None:
    source = _source_tree(tmp_path)

    with pytest.raises(ArtifactArchiveError, match="outside"):
        write_artifact_inventory(source, source / "inventory.json")


def test_create_and_verify_archive_preserves_source(
    tmp_path: Path,
) -> None:
    source = _source_tree(tmp_path)
    archive = tmp_path / "archive"

    result = create_verified_artifact_archive(
        source,
        archive,
        created_at_utc="2026-07-26T00:00:00+00:00",
    )

    assert source.is_dir()
    assert result["status"] == "verified"
    assert result["source_verified"] is True
    assert result["source_deletion_eligible"] is True
    assert result["source_deletion_performed"] is False
    assert {
        item.name for item in archive.iterdir()
    } == {
        ARCHIVE_PAYLOAD_DIRECTORY,
        ARCHIVE_MANIFEST_FILENAME,
        ARCHIVE_CHECKSUM_FILENAME,
    }
    assert (
        archive
        / ARCHIVE_PAYLOAD_DIRECTORY
        / "shard_000"
        / "cell_001"
        / "summary.json"
    ).is_file()

    repeated = verify_artifact_archive(archive, source=source)
    assert repeated["payload_tree_sha256"] == result["payload_tree_sha256"]


def test_archive_rejects_destination_inside_source(
    tmp_path: Path,
) -> None:
    source = _source_tree(tmp_path)

    with pytest.raises(ArtifactArchiveError, match="outside"):
        create_verified_artifact_archive(source, source / "archive")


def test_archive_rejects_existing_destination(
    tmp_path: Path,
) -> None:
    source = _source_tree(tmp_path)
    destination = tmp_path / "archive"
    destination.mkdir()

    with pytest.raises(FileExistsError):
        create_verified_artifact_archive(source, destination)


def test_archive_detects_payload_tampering(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    archive = tmp_path / "archive"
    create_verified_artifact_archive(source, archive)
    (
        archive / ARCHIVE_PAYLOAD_DIRECTORY / "progress.jsonl"
    ).write_text('{"tampered": true}\n', encoding="utf-8")

    with pytest.raises(ArtifactArchiveError, match="payload inventory"):
        verify_artifact_archive(archive, source=source)


def test_archive_detects_manifest_tampering(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    archive = tmp_path / "archive"
    create_verified_artifact_archive(source, archive)
    manifest = archive / ARCHIVE_MANIFEST_FILENAME
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["source"]["preserved"] = False
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactArchiveError, match="SHA-256"):
        verify_artifact_archive(archive)


def test_archive_detects_source_changes(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    archive = tmp_path / "archive"
    create_verified_artifact_archive(source, archive)
    (source / "progress.jsonl").write_text(
        '{"cell_id": "changed"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ArtifactArchiveError, match="source"):
        verify_artifact_archive(archive, source=source)


def test_archive_rejects_unexpected_root_entry(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    archive = tmp_path / "archive"
    create_verified_artifact_archive(source, archive)
    (archive / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")

    with pytest.raises(ArtifactArchiveError, match="root entries"):
        verify_artifact_archive(archive)


def test_inventory_rejects_symbolic_links(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    link = source / "linked-summary.json"
    try:
        link.symlink_to(source / "shard_000" / "cell_001" / "summary.json")
    except OSError:
        pytest.skip("symbolic links are unavailable in this environment")

    with pytest.raises(ArtifactArchiveError, match="symbolic links"):
        inventory_artifact_tree(source)


def test_inventory_rejects_symbolic_link_root(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    link = tmp_path / "linked-root"
    try:
        link.symlink_to(source, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable in this environment")

    with pytest.raises(ArtifactArchiveError, match="symbolic link"):
        inventory_artifact_tree(link)


def test_cli_inventory_and_verify(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    inventory_path = tmp_path / "inventory.json"
    archive = tmp_path / "archive"
    result_path = tmp_path / "verification.json"

    assert main(["inventory", str(source), str(inventory_path)]) == 0
    assert inventory_path.is_file()
    assert main(["copy", str(source), str(archive)]) == 0
    assert (
        main(
            [
                "verify",
                str(archive),
                "--source",
                str(source),
                "--result-json",
                str(result_path),
            ]
        )
        == 0
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "verified"
    assert result["source_deletion_eligible"] is True
