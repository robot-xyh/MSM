"""Inventory research artifacts and document versions without copying payloads."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from audit_workspace_metadata import document_metadata


SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv"}
MODEL_SUFFIXES = {".pt", ".pth", ".onnx", ".safetensors", ".ckpt"}
SIBLINGS = (
    "MSM-d5-training-clean",
    "MSM-source-audit-request-20260803",
    "MSM-source-audit-result-20260803-v3",
    "MSM-source-generation-output-64dfc08-20260803",
    "MSM-source-generation-output-6737b44-20260803",
    "MSM-source-generation-output-e7c438c-20260802",
)


def discover_output_roots(root: Path, errors: list[dict] | None = None) -> list[Path]:
    found = []

    def onerror(exc):
        if errors is not None:
            errors.append({"path": exc.filename, "error": str(exc)})

    for base, dirs, _ in os.walk(root / "research_modules", followlinks=False, onerror=onerror):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(base) / d).is_symlink())
        if "outputs" in dirs:
            found.append(Path(base) / "outputs")
            dirs.remove("outputs")
    return sorted(found)


def walk_files(root: Path, errors: list[dict]):
    def onerror(exc):
        errors.append({"path": exc.filename, "error": str(exc)})

    for base, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
        for name in sorted(dirs):
            path = Path(base) / name
            if path.is_symlink() and name not in SKIP_DIRS:
                yield path
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(base) / d).is_symlink())
        for name in sorted(files):
            if name != ".git" and not name.endswith((".pyc", ".pyo")):
                yield Path(base) / name


def file_record(path: Path, should_hash: bool, expected: set[str] | None = None) -> dict:
    record = {"path": str(path), "hash_status": "metadata_only"}
    if expected:
        record["expected_sha256"] = sorted(expected)
    try:
        before = path.lstat()
        record.update(bytes=before.st_size, mtime_ns=before.st_mtime_ns, device=before.st_dev)
        if stat.S_ISLNK(before.st_mode):
            record.update(kind="symlink", link_target=os.readlink(path), hash_status="not_followed")
            return record
        if not stat.S_ISREG(before.st_mode):
            record.update(kind="special", hash_status="not_read")
            return record
        record["kind"] = "file"
        if should_hash:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            hasher = hashlib.sha256()
            with os.fdopen(fd, "rb") as stream:
                opened = os.fstat(stream.fileno())
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(block)
                after = os.fstat(stream.fileno())
            final = path.lstat()
            keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            signatures = {tuple(getattr(s, key) for key in keys) for s in (before, opened, after, final)}
            if len(signatures) != 1:
                record["hash_status"] = "changed_during_read"
                return record
            record.update(sha256=hasher.hexdigest(), hash_status="stable_read")
            if expected:
                record["matches_recorded_hashes"] = all(record["sha256"] == value for value in expected)
    except OSError as exc:
        record.update(hash_status="read_error", error=str(exc))
    return record


def group_path(root: Path, file: Path) -> str:
    relative = file.relative_to(root)
    return str(root / relative.parts[0]) if len(relative.parts) > 1 else str(root)


def build_document_register(root: Path) -> dict:
    records = []
    for folder in ("leadership_report", "patents", "project_proposals"):
        for path in sorted((root / "deliverables" / folder).glob("*.docx")):
            item = document_metadata(root, path)
            pair = item.get("markdown_pair")
            item["overwrite_allowed"] = False
            if pair is None:
                item["relationship_status"] = "word_only_or_multi_source"
            elif pair["headings_not_verbatim_in_docx"]:
                item["relationship_status"] = "different_headings_preserve_both"
            else:
                item["relationship_status"] = "headings_aligned_body_not_verified"
            records.append(item)
    return {
        "schema": "msm-document-preservation-register-v1",
        "policy": "Preserve edited Word and Markdown separately; heading agreement is not full equivalence.",
        "documents": records,
    }


def prepare(root: Path, output: Path, prior_snapshot: Path) -> dict:
    root = root.resolve()
    output = output.resolve()
    snapshot = json.loads(prior_snapshot.read_text())
    primary_roots = [(root / value["path"]).resolve() for value in snapshot["evidence_roots"]]
    expected: dict[Path, set[str]] = {}
    for evidence in snapshot["evidence_roots"]:
        for manifest in evidence["manifests"]:
            for item in manifest["input_checks"]:
                if item.get("resolved_path") and item.get("expected"):
                    expected.setdefault(Path(item["resolved_path"]).resolve(), set()).add(item["expected"])

    discovery_errors = []
    outputs = discover_output_roots(root, discovery_errors)
    siblings = [root.parent / name for name in SIBLINGS]
    protected_roots = outputs + siblings
    if any(output == path or output.is_relative_to(path) for path in protected_roots):
        raise ValueError("Inventory output must not be inside an experiment or preservation source.")
    output.mkdir(parents=True, exist_ok=False)

    summary = {
        "schema": "msm-preservation-inventory-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip(),
        "revision_scope": "Repository HEAD at inventory time, not the executed revision of historical experiments.",
        "root": str(root),
        "backup_created": False,
        "backup_destination": None,
        "deletion_authorized": False,
        "scan_scope": "Research output trees, six sibling directories, and retained untracked files.",
        "excluded_directory_names": sorted(SKIP_DIRS),
        "hash_scope": "Primary result roots, six siblings, model artifacts, and prior manifest inputs only.",
        "hash_limit": "New digests establish a baseline, not a second backup or validation of results.",
        "prior_snapshot": str(prior_snapshot.resolve()),
        "scan_roots": [],
        "errors": discovery_errors,
        "hash_mismatches": [],
        "model_files": [],
        "legacy_archive_candidates": [],
    }
    groups: dict[str, dict] = {}
    hashes = Counter()
    totals = Counter()
    seen = set()
    expected_seen = set()
    inventory_path = output / "FILES.jsonl.gz"
    with gzip.open(inventory_path, "wt", encoding="utf-8") as stream:
        def record_file(path, source_root, root_kind, force_hash=False):
            key = str(path.absolute())
            if key in seen:
                return
            seen.add(key)
            model = path.suffix.lower() in MODEL_SUFFIXES
            priority = force_hash or model or path in expected or any(path.is_relative_to(p) for p in primary_roots)
            record = file_record(path, priority, expected.get(path))
            record.update(source_root=str(source_root), source_kind=root_kind)
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            group = group_path(source_root, path)
            item = groups.setdefault(group, {"path": group, "source_root": str(source_root), "source_kind": root_kind, "file_count": 0, "logical_bytes": 0, "hashed_count": 0, "hashed_bytes": 0, "model_count": 0, "nonregular_count": 0, "error_count": 0})
            if record.get("kind") == "file":
                item["file_count"] += 1
                item["logical_bytes"] += record.get("bytes", 0)
                totals["file_count"] += 1
                totals["logical_bytes"] += record.get("bytes", 0)
            else:
                item["nonregular_count"] += 1
            hashes[record["hash_status"]] += 1
            if record["hash_status"] == "stable_read":
                item["hashed_count"] += 1
                item["hashed_bytes"] += record["bytes"]
                totals["hashed_count"] += 1
                totals["hashed_bytes"] += record["bytes"]
            if record["hash_status"] in {"read_error", "changed_during_read"}:
                item["error_count"] += 1
                summary["errors"].append(record)
            if path in expected:
                expected_seen.add(path)
                totals["expected_hash_paths"] += 1
                totals["expected_hash_matches"] += record.get("matches_recorded_hashes") is True
                if record.get("matches_recorded_hashes") is False:
                    summary["hash_mismatches"].append(record)
            if model:
                item["model_count"] += 1
                summary["model_files"].append(record)
            if any(name in str(path).lower() for name in ("80e55eb", "formal_r0", "formal-r0")) and ("archive" in path.name.lower() or path.name.endswith((".tar", ".tar.gz", ".tar.zst", ".zst"))):
                summary["legacy_archive_candidates"].append(str(path))

        for source in protected_roots:
            exists = source.is_dir() and not source.is_symlink()
            kind = "experiment_outputs" if source in outputs else "sibling_preserve"
            summary["scan_roots"].append({"path": str(source), "exists": exists, "source_kind": kind, "same_filesystem_as_repository": source.stat().st_dev == root.stat().st_dev if exists else None})
            if not exists:
                summary["errors"].append({"path": str(source), "error": "source missing or symlink"})
                continue
            for path in walk_files(source, summary["errors"]):
                record_file(path, source, kind, force_hash=kind == "sibling_preserve")
            print(json.dumps({"scanned_root": str(source), "files_so_far": totals["file_count"], "hashed_so_far": totals["hashed_count"]}), flush=True)

        raw = subprocess.check_output(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"])
        summary["nested_repositories"] = []
        for value in raw.decode().split("\0"):
            if not value or value.startswith("deliverables/project_audits/"):
                continue
            path = root / value
            if path.is_dir():
                summary["nested_repositories"].append({"path": str(path), "payload_inventoried": False, "status": "separate_repository_requires_separate_backup"})
            else:
                record_file(path, root, "retained_untracked")

        for path in sorted(set(expected) - expected_seen):
            record_file(path, path.parent, "manifest_dependency", force_hash=True)

    groups_list = sorted(groups.values(), key=lambda row: row["path"])
    summary.update(totals=dict(totals), hash_status_counts=dict(hashes), group_count=len(groups_list))
    filesystem = os.statvfs(root)
    summary["filesystem"] = {"device": root.stat().st_dev, "available_bytes": filesystem.f_bavail * filesystem.f_frsize, "total_bytes": filesystem.f_blocks * filesystem.f_frsize}
    summary["old_tmp_result"] = {"path": "/tmp/msm-formal-r0-20260731-80e55eb/d6_strict_partial_450_b6289c5", "exists": Path("/tmp/msm-formal-r0-20260731-80e55eb/d6_strict_partial_450_b6289c5").exists()}
    summary["inventory_file"] = {"path": inventory_path.name, "sha256": file_record(inventory_path, True)["sha256"], "compressed_bytes": inventory_path.stat().st_size}
    (output / "PRESERVATION_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    with (output / "PRESERVATION_GROUPS.csv").open("w", newline="") as stream:
        fields = ("path", "source_root", "source_kind", "file_count", "logical_bytes", "hashed_count", "hashed_bytes", "model_count", "nonregular_count", "error_count")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(groups_list)
    documents = build_document_register(root)
    documents["source_commit"] = summary["source_commit"]
    documents["created_at_utc"] = summary["created_at_utc"]
    (output / "DOCUMENT_VERSION_REGISTER.json").write_text(json.dumps(documents, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output), "totals": summary["totals"], "groups": len(groups_list), "errors": len(summary["errors"]), "documents": len(documents["documents"]), "backup_created": False}, ensure_ascii=False), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prior-snapshot", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.root, args.output_dir, args.prior_snapshot)


if __name__ == "__main__":
    main()
