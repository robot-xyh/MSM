"""Verified, non-destructive archival for scalable-3D experiment outputs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence


ARTIFACT_INVENTORY_SCHEMA = "scalable3d-artifact-inventory-v1"
ARTIFACT_ARCHIVE_MANIFEST_SCHEMA = "scalable3d-artifact-archive-manifest-v1"
ARTIFACT_ARCHIVE_VERIFICATION_SCHEMA = (
    "scalable3d-artifact-archive-verification-v1"
)
ARCHIVE_MANIFEST_FILENAME = "archive_manifest.json"
ARCHIVE_CHECKSUM_FILENAME = "SHA256SUMS"
ARCHIVE_PAYLOAD_DIRECTORY = "payload"


class ArtifactArchiveError(RuntimeError):
    """Raised when an archive cannot be proven complete and unchanged."""


def inventory_artifact_tree(root: str | Path) -> dict[str, Any]:
    """Return a deterministic, content-addressed inventory for ``root``."""

    source = _require_directory(root, label="artifact root")
    files: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    total_size = 0

    for item in sorted(source.rglob("*"), key=lambda value: value.as_posix()):
        if item.is_symlink():
            raise ArtifactArchiveError(
                f"symbolic links are not allowed in artifact trees: {item}"
            )
        if item.is_dir():
            continue
        if not item.is_file():
            raise ArtifactArchiveError(
                f"non-regular artifact entry is not allowed: {item}"
            )
        relative = item.relative_to(source).as_posix()
        if "\n" in relative or "\r" in relative:
            raise ArtifactArchiveError(
                "artifact relative paths must not contain line breaks"
            )
        size = int(item.stat().st_size)
        sha256 = _sha256_file(item)
        record = {
            "relative_path": relative,
            "size_bytes": size,
            "sha256": sha256,
        }
        files.append(record)
        total_size += size
        digest.update(
            f"{sha256}  {size}  {relative}\n".encode("utf-8")
        )

    if not files:
        raise ArtifactArchiveError("artifact tree must contain at least one file")

    return {
        "schema_version": ARTIFACT_INVENTORY_SCHEMA,
        "file_count": len(files),
        "total_size_bytes": total_size,
        "tree_sha256": digest.hexdigest(),
        "files": files,
    }


def write_artifact_inventory(
    source: str | Path,
    output: str | Path,
    *,
    created_at_utc: str | None = None,
) -> Path:
    """Write a standalone inventory without modifying the source tree."""

    source_root = _require_directory(source, label="artifact source")
    destination = Path(output).expanduser().resolve()
    if _is_relative_to(destination, source_root):
        raise ArtifactArchiveError(
            "inventory output must be outside the inventoried source tree"
        )
    if destination.exists():
        raise FileExistsError(f"inventory output already exists: {destination}")

    payload = {
        "schema_version": ARTIFACT_INVENTORY_SCHEMA,
        "created_at_utc": _timestamp(created_at_utc),
        "source_name": source_root.name,
        "source_preserved": True,
        "inventory": inventory_artifact_tree(source_root),
    }
    _write_json_atomic(destination, payload)
    return destination


def create_verified_artifact_archive(
    source: str | Path,
    destination: str | Path,
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Copy ``source`` atomically and prove byte-for-byte equivalence.

    The source is never removed.  A caller may consider deletion only after a
    separate verification reports ``source_deletion_eligible=true``.
    """

    source_root = _require_directory(source, label="artifact source")
    archive_root = Path(destination).expanduser().resolve()
    if archive_root.exists():
        raise FileExistsError(
            f"artifact archive destination already exists: {archive_root}"
        )
    if _is_relative_to(archive_root, source_root):
        raise ArtifactArchiveError(
            "artifact archive destination must be outside the source tree"
        )

    archive_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_root.parent / f".{archive_root.name}.partial"
    if temporary.exists():
        raise ArtifactArchiveError(
            f"partial artifact archive already exists: {temporary}"
        )

    initial_inventory = inventory_artifact_tree(source_root)
    try:
        payload_root = temporary / ARCHIVE_PAYLOAD_DIRECTORY
        payload_root.mkdir(parents=True)
        for record in initial_inventory["files"]:
            relative = Path(str(record["relative_path"]))
            source_file = source_root / relative
            destination_file = payload_root / relative
            destination_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination_file)

        copied_inventory = inventory_artifact_tree(payload_root)
        if copied_inventory != initial_inventory:
            raise ArtifactArchiveError(
                "copied artifact payload does not match the source inventory"
            )
        final_source_inventory = inventory_artifact_tree(source_root)
        if final_source_inventory != initial_inventory:
            raise ArtifactArchiveError(
                "artifact source changed while the archive was being copied"
            )

        manifest = {
            "schema_version": ARTIFACT_ARCHIVE_MANIFEST_SCHEMA,
            "created_at_utc": _timestamp(created_at_utc),
            "source": {
                "name": source_root.name,
                "preserved": True,
                "deletion_performed": False,
            },
            "payload_directory": ARCHIVE_PAYLOAD_DIRECTORY,
            "inventory": initial_inventory,
        }
        manifest_path = temporary / ARCHIVE_MANIFEST_FILENAME
        _write_json_atomic(manifest_path, manifest)
        checksum_path = temporary / ARCHIVE_CHECKSUM_FILENAME
        checksum_path.write_text(
            f"{_sha256_file(manifest_path)}  {ARCHIVE_MANIFEST_FILENAME}\n",
            encoding="utf-8",
        )
        verification = verify_artifact_archive(
            temporary,
            source=source_root,
        )
        os.replace(temporary, archive_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        **verification,
        "archive": str(archive_root),
        "manifest": str(archive_root / ARCHIVE_MANIFEST_FILENAME),
        "checksums": str(archive_root / ARCHIVE_CHECKSUM_FILENAME),
    }


def verify_artifact_archive(
    archive: str | Path,
    *,
    source: str | Path | None = None,
) -> dict[str, Any]:
    """Verify archive metadata, payload and optionally the preserved source."""

    archive_root = _require_directory(archive, label="artifact archive")
    expected_entries = {
        ARCHIVE_PAYLOAD_DIRECTORY,
        ARCHIVE_MANIFEST_FILENAME,
        ARCHIVE_CHECKSUM_FILENAME,
    }
    actual_entries = {item.name for item in archive_root.iterdir()}
    if actual_entries != expected_entries:
        raise ArtifactArchiveError(
            "artifact archive root entries do not match the frozen contract"
        )

    manifest_path = archive_root / ARCHIVE_MANIFEST_FILENAME
    checksum_path = archive_root / ARCHIVE_CHECKSUM_FILENAME
    expected_manifest_sha256 = _read_checksum_file(checksum_path)
    actual_manifest_sha256 = _sha256_file(manifest_path)
    if actual_manifest_sha256 != expected_manifest_sha256:
        raise ArtifactArchiveError("artifact archive manifest SHA-256 mismatch")

    manifest = _read_json_object(manifest_path)
    if (
        manifest.get("schema_version")
        != ARTIFACT_ARCHIVE_MANIFEST_SCHEMA
    ):
        raise ArtifactArchiveError(
            "unsupported artifact archive manifest schema"
        )
    if manifest.get("payload_directory") != ARCHIVE_PAYLOAD_DIRECTORY:
        raise ArtifactArchiveError("artifact archive payload directory mismatch")
    source_contract = manifest.get("source")
    if not isinstance(source_contract, Mapping):
        raise ArtifactArchiveError("artifact archive source contract is missing")
    if source_contract.get("preserved") is not True:
        raise ArtifactArchiveError(
            "artifact archive must declare that the source was preserved"
        )
    if source_contract.get("deletion_performed") is not False:
        raise ArtifactArchiveError(
            "artifact archive must not claim source deletion"
        )

    frozen_inventory = manifest.get("inventory")
    if not isinstance(frozen_inventory, Mapping):
        raise ArtifactArchiveError("artifact archive inventory is missing")
    payload_inventory = inventory_artifact_tree(
        archive_root / ARCHIVE_PAYLOAD_DIRECTORY
    )
    if payload_inventory != dict(frozen_inventory):
        raise ArtifactArchiveError(
            "artifact archive payload inventory does not match the manifest"
        )

    source_verified = False
    if source is not None:
        source_inventory = inventory_artifact_tree(source)
        if source_inventory != dict(frozen_inventory):
            raise ArtifactArchiveError(
                "preserved source no longer matches the verified archive"
            )
        source_verified = True

    return {
        "schema_version": ARTIFACT_ARCHIVE_VERIFICATION_SCHEMA,
        "status": "verified",
        "archive_manifest_sha256": actual_manifest_sha256,
        "payload_tree_sha256": payload_inventory["tree_sha256"],
        "file_count": payload_inventory["file_count"],
        "total_size_bytes": payload_inventory["total_size_bytes"],
        "source_verified": source_verified,
        "source_deletion_eligible": source_verified,
        "source_deletion_performed": False,
    }


def _require_directory(path: str | Path, *, label: str) -> Path:
    unresolved = Path(path).expanduser()
    if unresolved.is_symlink():
        raise ArtifactArchiveError(f"{label} must not be a symbolic link")
    root = unresolved.resolve()
    if not root.is_dir():
        raise ArtifactArchiveError(f"{label} is not a directory: {root}")
    return root


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ArtifactArchiveError(f"expected JSON object: {path}")
    return payload


def _read_checksum_file(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise ArtifactArchiveError(
            "artifact archive checksum file must contain exactly one line"
        )
    parts = lines[0].split("  ", maxsplit=1)
    if len(parts) != 2 or parts[1] != ARCHIVE_MANIFEST_FILENAME:
        raise ArtifactArchiveError(
            "artifact archive checksum entry is malformed"
        )
    sha256 = parts[0]
    if len(sha256) != 64 or any(
        character not in "0123456789abcdef" for character in sha256
    ):
        raise ArtifactArchiveError(
            "artifact archive checksum is not a lowercase SHA-256"
        )
    return sha256


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


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
        raise FileExistsError(f"CLI result output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory, copy and verify scalable-3D artifacts without "
            "deleting the source"
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser(
        "inventory",
        help="write a deterministic inventory outside the source tree",
    )
    inventory.add_argument("source")
    inventory.add_argument("output")

    copy = subparsers.add_parser(
        "copy",
        help="atomically copy and verify an artifact tree",
    )
    copy.add_argument("source")
    copy.add_argument("destination")
    copy.add_argument("--result-json")

    verify = subparsers.add_parser(
        "verify",
        help="verify an archive and optionally compare its preserved source",
    )
    verify.add_argument("archive")
    verify.add_argument("--source")
    verify.add_argument("--result-json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "inventory":
        path = write_artifact_inventory(args.source, args.output)
        print(path)
        return 0
    if args.command == "copy":
        result = create_verified_artifact_archive(
            args.source,
            args.destination,
        )
        _write_cli_result(result, args.result_json)
        return 0
    if args.command == "verify":
        result = verify_artifact_archive(
            args.archive,
            source=args.source,
        )
        _write_cli_result(result, args.result_json)
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
