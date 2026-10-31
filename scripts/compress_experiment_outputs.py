#!/usr/bin/env python3
"""Losslessly compress large structured experiment outputs with audit indexes.

The script replaces an eligible source file only after the compressed stream
has been decompressed and its SHA-256 has been matched to the source.  It is
safe to resume after interruption because the catalog is flushed before the
source file is removed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from typing import Iterable


ELIGIBLE_SUFFIXES = {".json", ".jsonl", ".csv"}
EXCLUDED_EXACT_NAMES = {
    "archive_manifest.json",
    "manifest.json",
    "scenario.json",
    "settings.json",
}
EXCLUDED_NAME_MARKERS = (
    "archive_catalog",
    "compression_summary",
)
CATALOG_FIELDS = (
    "experiment_id",
    "run_root",
    "original_path",
    "compressed_path",
    "artifact_type",
    "original_size_bytes",
    "compressed_size_bytes",
    "saved_bytes",
    "compressed_ratio",
    "sha256_original",
    "compression",
    "verified_utc",
    "status",
)


@dataclass(frozen=True)
class PlanEntry:
    experiment_id: str
    run_root: str
    original_path: str
    compressed_path: str
    artifact_type: str
    original_size_bytes: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--scan-root", type=Path, default=Path("research_modules"))
    parser.add_argument("--audit-root", type=Path, required=True)
    parser.add_argument("--min-size", type=int, default=65_536)
    parser.add_argument("--level", type=int, default=9)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--progress-every", type=int, default=100)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_decompressed(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    process = subprocess.Popen(
        ["zstd", "-q", "-d", "-c", str(path)],
        stdout=subprocess.PIPE,
    )
    assert process.stdout is not None
    for chunk in iter(lambda: process.stdout.read(8 * 1024 * 1024), b""):
        digest.update(chunk)
        size += len(chunk)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"zstd verification failed for {path}")
    return digest.hexdigest(), size


def git_tracked_files(repo_root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return {
        item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item
    }


def output_run_root(relative_path: Path) -> Path | None:
    parts = relative_path.parts
    try:
        output_index = parts.index("outputs")
    except ValueError:
        return None
    if output_index + 1 >= len(parts):
        return None
    return Path(*parts[: output_index + 2])


def classify(path: Path) -> str:
    text = str(path).lower()
    if "truth" in text or "label" in text:
        return "truth_or_label"
    if "observation" in text or "frame" in text:
        return "observation_or_frame"
    if "trajectory" in text:
        return "trajectory"
    if "detection" in text:
        return "detection"
    if "track" in text:
        return "track"
    if "candidate" in text or "hypothesis" in text:
        return "candidate_relation"
    if "replay" in text or "revolution" in text:
        return "replay"
    return "structured_data"


def eligible_files(
    repo_root: Path,
    scan_root: Path,
    min_size: int,
    tracked: set[str],
) -> Iterable[PlanEntry]:
    absolute_scan_root = repo_root / scan_root
    for directory, _, names in os.walk(absolute_scan_root):
        directory_path = Path(directory)
        if "outputs" not in directory_path.parts:
            continue
        for name in names:
            lower_name = name.lower()
            path = directory_path / name
            if path.suffix.lower() not in ELIGIBLE_SUFFIXES:
                continue
            if lower_name in EXCLUDED_EXACT_NAMES:
                continue
            if lower_name.endswith("manifest.json"):
                continue
            if any(marker in lower_name for marker in EXCLUDED_NAME_MARKERS):
                continue
            size = path.stat().st_size
            if size < min_size:
                continue
            relative_path = path.relative_to(repo_root)
            relative_text = relative_path.as_posix()
            if relative_text in tracked:
                continue
            run_root = output_run_root(relative_path)
            if run_root is None:
                continue
            yield PlanEntry(
                experiment_id=run_root.name,
                run_root=run_root.as_posix(),
                original_path=relative_text,
                compressed_path=f"{relative_text}.zst",
                artifact_type=classify(relative_path),
                original_size_bytes=size,
            )


def write_plan(path: Path, entries: list[PlanEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PlanEntry.__dataclass_fields__)
        writer.writeheader()
        for entry in entries:
            writer.writerow(asdict(entry))
    os.replace(temporary, path)


def read_catalog(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {
            row["original_path"]: row
            for row in csv.DictReader(handle, delimiter="\t")
        }


def open_catalog(path: Path):
    exists = path.exists() and path.stat().st_size > 0
    handle = path.open("a", encoding="utf-8", newline="", buffering=1)
    writer = csv.DictWriter(handle, fieldnames=CATALOG_FIELDS, delimiter="\t")
    if not exists:
        writer.writeheader()
        handle.flush()
        os.fsync(handle.fileno())
    return handle, writer


def append_catalog(handle, writer, row: dict[str, object]) -> None:
    writer.writerow(row)
    handle.flush()
    os.fsync(handle.fileno())


def compress_and_verify(
    repo_root: Path,
    entry: PlanEntry,
    level: int,
    catalog_handle,
    catalog_writer,
) -> dict[str, object]:
    source = repo_root / entry.original_path
    destination = repo_root / entry.compressed_path
    temporary = destination.with_suffix(destination.suffix + ".tmp")

    source_hash = sha256_file(source)
    if destination.exists():
        destination_hash, decompressed_size = sha256_decompressed(destination)
        if destination_hash != source_hash or decompressed_size != source.stat().st_size:
            raise RuntimeError(f"existing compressed file does not match {source}")
    else:
        temporary.unlink(missing_ok=True)
        with temporary.open("wb") as output_handle:
            result = subprocess.run(
                ["zstd", "-q", f"-{level}", "-T0", "-c", str(source)],
                stdout=output_handle,
            )
        if result.returncode != 0:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"zstd compression failed for {source}")
        destination_hash, decompressed_size = sha256_decompressed(temporary)
        if destination_hash != source_hash or decompressed_size != source.stat().st_size:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"verification mismatch for {source}")
        os.replace(temporary, destination)

    compressed_size = destination.stat().st_size
    original_size = source.stat().st_size
    row: dict[str, object] = {
        **asdict(entry),
        "compressed_size_bytes": compressed_size,
        "saved_bytes": original_size - compressed_size,
        "compressed_ratio": f"{compressed_size / original_size:.8f}",
        "sha256_original": source_hash,
        "compression": f"zstd-{level}",
        "verified_utc": datetime.now(timezone.utc).isoformat(),
        "status": "verified",
    }
    append_catalog(catalog_handle, catalog_writer, row)
    source.unlink()
    return row


def finish_pending_source_deletes(
    repo_root: Path,
    completed: dict[str, dict[str, str]],
) -> None:
    for original_path, row in completed.items():
        source = repo_root / original_path
        compressed = repo_root / row["compressed_path"]
        if not source.exists():
            continue
        if not compressed.exists():
            raise RuntimeError(f"cataloged compressed file is missing: {compressed}")
        source_hash = sha256_file(source)
        compressed_hash, decompressed_size = sha256_decompressed(compressed)
        if source_hash != row["sha256_original"] or compressed_hash != source_hash:
            raise RuntimeError(f"resume verification mismatch for {source}")
        if decompressed_size != source.stat().st_size:
            raise RuntimeError(f"resume size mismatch for {source}")
        source.unlink()


def write_run_manifests(
    repo_root: Path,
    rows: list[dict[str, str]],
) -> None:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["run_root"]].append(row)
    for run_root, run_rows in grouped.items():
        manifest_path = repo_root / run_root / "ARCHIVE_MANIFEST.json"
        payload = {
            "schema_version": 1,
            "experiment_id": Path(run_root).name,
            "run_root": run_root,
            "compression": sorted({row["compression"] for row in run_rows}),
            "file_count": len(run_rows),
            "original_size_bytes": sum(int(row["original_size_bytes"]) for row in run_rows),
            "compressed_size_bytes": sum(int(row["compressed_size_bytes"]) for row in run_rows),
            "files": [
                {
                    key: row[key]
                    for key in (
                        "original_path",
                        "compressed_path",
                        "artifact_type",
                        "original_size_bytes",
                        "compressed_size_bytes",
                        "sha256_original",
                        "verified_utc",
                    )
                }
                for row in sorted(run_rows, key=lambda item: item["original_path"])
            ],
        }
        temporary = manifest_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, manifest_path)


def write_summary(
    audit_root: Path,
    entries: list[PlanEntry],
    rows: list[dict[str, str]],
    min_size: int,
    level: int,
) -> None:
    original = sum(int(row["original_size_bytes"]) for row in rows)
    compressed = sum(int(row["compressed_size_bytes"]) for row in rows)
    payload = {
        "schema_version": 1,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "minimum_source_size_bytes": min_size,
        "compression": f"zstd-{level}",
        "planned_file_count": len(entries),
        "verified_file_count": len(rows),
        "original_size_bytes": original,
        "compressed_size_bytes": compressed,
        "saved_bytes": original - compressed,
        "saved_ratio": (original - compressed) / original if original else 0.0,
    }
    path = audit_root / "COMPRESSION_SUMMARY.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    scan_root = args.scan_root
    audit_root = (repo_root / args.audit_root).resolve()
    audit_root.mkdir(parents=True, exist_ok=True)

    tracked = git_tracked_files(repo_root)
    entries = sorted(
        eligible_files(repo_root, scan_root, args.min_size, tracked),
        key=lambda entry: (-entry.original_size_bytes, entry.original_path),
    )
    write_plan(audit_root / "COMPRESSION_PLAN.csv", entries)
    planned_size = sum(entry.original_size_bytes for entry in entries)
    print(
        f"planned_files={len(entries)} planned_bytes={planned_size} "
        f"execute={args.execute}",
        flush=True,
    )
    if not args.execute:
        return 0

    catalog_path = audit_root / "ARCHIVE_CATALOG.tsv"
    completed = read_catalog(catalog_path)
    finish_pending_source_deletes(repo_root, completed)
    catalog_handle, catalog_writer = open_catalog(catalog_path)
    try:
        processed = 0
        for entry in entries:
            if entry.original_path in completed:
                continue
            row = compress_and_verify(
                repo_root,
                entry,
                args.level,
                catalog_handle,
                catalog_writer,
            )
            completed[entry.original_path] = {key: str(value) for key, value in row.items()}
            processed += 1
            if processed % args.progress_every == 0:
                saved = sum(int(row["saved_bytes"]) for row in completed.values())
                print(
                    f"processed={processed} cataloged={len(completed)} saved_bytes={saved}",
                    flush=True,
                )
    finally:
        catalog_handle.close()

    rows = list(read_catalog(catalog_path).values())
    write_run_manifests(repo_root, rows)
    write_summary(audit_root, entries, rows, args.min_size, args.level)
    print(f"completed_files={len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
