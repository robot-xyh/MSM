"""Read-only cleanup audit: caches, duplicate PDFs, ZIP payloads and references."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import zipfile

from prepare_preservation_register import SIBLINGS, file_record


CACHE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SKIP_NAMES = {".git", ".venv", "venv", "node_modules"}
TEXT_SUFFIXES = {".md", ".py", ".json", ".yaml", ".yml", ".toml", ".txt", ".sh"}
TEXT_LIMIT = 2 * 1024 * 1024


def tracked_paths(root: Path) -> set[Path]:
    raw = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"])
    return {root / os.fsdecode(name) for name in raw.split(b"\0") if name}


def cache_record(path: Path, tracked: set[Path]) -> dict:
    result = {"path": str(path), "kind": "cache", "files": 0, "logical_bytes": 0,
              "allocated_bytes": 0, "issues": [], "status": "review_required"}

    def onerror(exc):
        result["issues"].append(str(exc))

    for base, dirs, files in os.walk(path, followlinks=False, onerror=onerror):
        for name in dirs[:]:
            target = Path(base) / name
            if target.is_symlink():
                result["issues"].append("symlink: " + str(target))
                dirs.remove(name)
        for name in files:
            target = Path(base) / name
            info = target.lstat()
            if not stat.S_ISREG(info.st_mode):
                result["issues"].append("nonregular: " + str(target))
                continue
            result["files"] += 1
            result["logical_bytes"] += info.st_size
            if info.st_nlink == 1:
                result["allocated_bytes"] += info.st_blocks * 512
            if target in tracked:
                result["issues"].append("tracked: " + str(target))
            if path.name == "__pycache__":
                pytest_name = re.fullmatch(r"(.+)\.cpython-\d+-pytest-[A-Za-z0-9.+-]+\.pyc", target.name)
                if pytest_name:
                    source = path.parent / (pytest_name.group(1) + ".py")
                else:
                    try:
                        source = Path(importlib.util.source_from_cache(str(target)))
                    except ValueError:
                        source = None
                if target.suffix != ".pyc" or source is None or not source.is_file() or source.is_symlink():
                    result["issues"].append("source_not_verified: " + str(target))
            elif path.name == ".pytest_cache":
                relative = target.relative_to(path).as_posix()
                allowed = {"README.md", ".gitignore", "CACHEDIR.TAG", "v/cache/nodeids",
                           "v/cache/lastfailed", "v/cache/stepwise", "v/cache/durations"}
                if relative not in allowed:
                    result["issues"].append("unrecognized_cache_file: " + str(target))
    if path.name == ".pytest_cache":
        tag = path / "CACHEDIR.TAG"
        if not tag.is_file() or tag.is_symlink() or "Signature: 8a477f597d28d172789f06886806bc55" not in tag.read_text():
            result["issues"].append("pytest_cache_signature_not_verified")
    if path.name not in {"__pycache__", ".pytest_cache"}:
        result["issues"].append("cache_format_not_verified")
    if not result["issues"]:
        result["status"] = "regenerable_cache"
    return result


def fingerprint(path: Path, memo: dict) -> dict:
    if path not in memo:
        record = file_record(path, True)
        try:
            info = path.lstat()
            record["allocated_bytes"] = info.st_blocks * 512 if info.st_nlink == 1 else 0
            record["nlink"] = info.st_nlink
        except OSError:
            pass
        memo[path] = record
    return memo[path]


def duplicate_pdfs(paths: list[Path], tracked: set[Path], memo: dict) -> list[dict]:
    by_size = defaultdict(list)
    for path in paths:
        by_size[path.stat().st_size].append(path)
    matches = defaultdict(list)
    for candidates in by_size.values():
        if len(candidates) < 2:
            continue
        for path in candidates:
            record = fingerprint(path, memo)
            if record["hash_status"] == "stable_read":
                matches[record["sha256"]].append(path)
    result = []
    for digest, candidates in matches.items():
        if len(candidates) < 2:
            continue
        candidates.sort(key=lambda p: (p not in tracked, "duplicates" in p.parts,
                                      "损坏重复文件" in p.parts, len(p.parts), str(p)))
        result.append({"sha256": digest, "suggested_keep": str(candidates[0]),
                       "files": [fingerprint(path, memo) for path in candidates],
                       "status": "identical_content_reference_review_required"})
    return result


def safe_zip_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name and ":" not in name


def archive_record(path: Path, by_size: dict[int, list[Path]], tracked: set[Path], memo: dict) -> dict:
    result = {"path": str(path), "kind": "archive", "logical_bytes": path.stat().st_size,
              "status": "review_required", "members": [], "issues": [], "tracked": path in tracked}
    if path in tracked:
        result["status"] = "keep_tracked_archive"
        return result
    before = path.stat()
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if sum(item.file_size for item in members) > 8 * 1024**3:
                result["issues"].append("uncompressed_size_exceeds_audit_budget")
                return result
            names = [item.filename for item in members if not item.is_dir()]
            if len(names) != len(set(names)):
                result["issues"].append("duplicate_member_names")
            for member in members:
                if member.is_dir():
                    continue
                entry = {"name": member.filename, "bytes": member.file_size, "match": None}
                result["members"].append(entry)
                if not safe_zip_member(member.filename) or stat.S_ISLNK(member.external_attr >> 16):
                    result["issues"].append("unsafe_or_symlink_member: " + member.filename)
                    continue
                hasher = hashlib.sha256()
                with archive.open(member) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        hasher.update(block)
                digest = hasher.hexdigest()
                entry["sha256"] = digest
                direct = path.parent / member.filename
                candidates = sorted(by_size.get(member.file_size, []), key=lambda p: (
                    p != direct, p.suffix.lower() != Path(member.filename).suffix.lower(),
                    p.name != PurePosixPath(member.filename).name, str(p)))
                for candidate in candidates:
                    if candidate == path:
                        continue
                    record = fingerprint(candidate, memo)
                    if record.get("sha256") == digest and record["hash_status"] == "stable_read":
                        entry["match"] = str(candidate)
                        entry["original_relative_path_preserved"] = candidate == direct
                        break
            if not result["issues"] and result["members"] and all(item["match"] for item in result["members"]):
                result["status"] = "all_payloads_present_optional_archive_cleanup"
            elif not result["members"]:
                result["issues"].append("empty_archive")
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        result["issues"].append(str(exc))
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        result["issues"].append("archive_changed_during_read")
        result["status"] = "review_required"
    result["matched_files"] = sum(item["match"] is not None for item in result["members"])
    result["missing_payload_files"] = sum(item["match"] is None for item in result["members"])
    result["original_layout_preserved"] = bool(result["members"]) and all(item.get("original_relative_path_preserved") for item in result["members"])
    result["fingerprint"] = fingerprint(path, memo)
    return result


def reference_scan(paths: list[Path], candidates: list[dict], errors: list[dict]) -> dict:
    token_map = defaultdict(list)
    for item in candidates:
        token_map[Path(item["path"]).name].append(item)
        item["reference_files"] = []
        item["reference_file_count"] = 0
    if not token_map:
        return {"scanned": 0, "skipped_large": 0}
    pattern = re.compile("|".join(re.escape(name) for name in sorted(token_map, key=len, reverse=True)))
    totals = {"scanned": 0, "skipped_large": 0}
    for path in paths:
        try:
            if path.suffix.lower() == ".docx":
                with zipfile.ZipFile(path) as archive:
                    text = "\n".join(archive.read(name).decode("utf-8") for name in archive.namelist()
                                     if name == "word/document.xml" or name.endswith(".rels"))
            else:
                if path.stat().st_size > TEXT_LIMIT:
                    totals["skipped_large"] += 1
                    continue
                text = path.read_text(errors="replace")
                if path.suffix.lower() == ".json":
                    try:
                        text = json.dumps(json.loads(text), ensure_ascii=False)
                    except ValueError:
                        pass
            totals["scanned"] += 1
            for name in {match.group() for match in pattern.finditer(text)}:
                for item in token_map[name]:
                    target = Path(item["path"])
                    if path == target or path.is_relative_to(target):
                        continue
                    item["reference_file_count"] += 1
                    if len(item["reference_files"]) < 8:
                        item["reference_files"].append(str(path))
        except (OSError, zipfile.BadZipFile) as exc:
            errors.append({"path": str(path), "error": str(exc)})
    return totals


def run(root: Path, inventory: Path, output: Path) -> dict:
    root = root.resolve()
    output = output.resolve()
    if not output.is_relative_to(root / "deliverables/project_audits"):
        raise ValueError("Audit output must be a new directory under deliverables/project_audits.")
    output.mkdir(parents=True, exist_ok=False)
    result = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "root": str(root),
              "source_commit_at_audit": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip(),
              "prior_inventory": str(inventory.resolve()),
              "tool_sha256": file_record(Path(__file__), True)["sha256"],
              "deletion_performed": False, "backup_created": False, "errors": [], "caches": [],
              "scan_roots": [], "scope_limits": [
                  "No simulation, model loading, algorithm evaluation, move, or deletion.",
                  "Literal references only; dynamic paths, external documents and external storage are not resolved.",
                  "Experiment sizes come from the prior inventory, not an atomic current snapshot.",
                  "Archive comparison verifies regular-file payloads, not permissions, directory layout or archival value.",
                  "No age-based deletion verdict. Lack of a detected reference is not deletion approval."]}
    tracked = set()
    repositories = [root, *(root / "paper" / name for name in ("YOPO", "Fastlab_world_fly", "ego-planner", "ego-planner-swarm")), root.parent / SIBLINGS[0]]
    for repository in repositories:
        if (repository / ".git").exists():
            tracked.update(tracked_paths(repository))
    by_size = defaultdict(list)
    pdfs, archives, texts = [], [], []
    sources = [root, *(root.parent / name for name in SIBLINGS)]
    for source in sources:
        if not source.is_dir():
            result["errors"].append({"path": str(source), "error": "source_missing"})
            continue
        result["scan_roots"].append(str(source))
        for base, dirs, files in os.walk(source, followlinks=False,
                                        onerror=lambda exc: result["errors"].append({"path": exc.filename, "error": str(exc)})):
            parent = Path(base)
            for name in dirs[:]:
                child = parent / name
                if name in SKIP_NAMES or child.is_symlink() or child == root / "deliverables/project_audits":
                    dirs.remove(name)
                elif name in CACHE_NAMES:
                    result["caches"].append(cache_record(child, tracked))
                    dirs.remove(name)
            for name in files:
                path = parent / name
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or name == ".git":
                    continue
                by_size[info.st_size].append(path)
                suffix = path.suffix.lower()
                if path.is_relative_to(root / "paper") and suffix == ".pdf":
                    pdfs.append(path)
                if source == root and suffix == ".zip":
                    archives.append(path)
                if suffix == ".docx":
                    texts.append(path)
                elif suffix in TEXT_SUFFIXES:
                    in_outputs = "outputs" in path.parts
                    metadata = suffix == ".md" or any(token in name.lower() for token in ("manifest", "summary", "config", "checkpoint", "report", "plan", "settings"))
                    if not in_outputs or metadata:
                        texts.append(path)
        print(json.dumps({"scanned_tree": str(source), "cache_directories": len(result["caches"])}), flush=True)
    memo = {}
    result["duplicate_pdf_groups"] = duplicate_pdfs(pdfs, tracked, memo)
    print(json.dumps({"pdf_files": len(pdfs), "duplicate_groups": len(result["duplicate_pdf_groups"])}), flush=True)
    result["archives"] = []
    for path in sorted(archives):
        record = archive_record(path, by_size, tracked, memo)
        result["archives"].append(record)
        print(json.dumps({"archive": str(path), "status": record["status"], "matched": record.get("matched_files"), "missing": record.get("missing_payload_files")}), flush=True)
    with (inventory / "PRESERVATION_GROUPS.csv").open(newline="") as stream:
        groups = [row for row in csv.DictReader(stream) if row["source_kind"] == "experiment_outputs"]
    groups.sort(key=lambda item: int(item["logical_bytes"]), reverse=True)
    selected = [item for i, item in enumerate(groups) if i < 30 or (int(item["logical_bytes"]) > 100 * 1024**2 and re.search(r"preflight|smoke|dev|diagnostic|replay.*v1", Path(item["path"]).name))]
    result["large_experiment_directories"] = [{"path": row["path"], "kind": "experiment_directory",
                                                "logical_bytes": int(row["logical_bytes"]), "files": int(row["file_count"]),
                                                "status": "retain_pending_dependency_and_backup_review"} for row in selected]
    duplicate_candidates = []
    for group in result["duplicate_pdf_groups"]:
        for entry in group["files"]:
            if entry["path"] != group["suggested_keep"]:
                duplicate_candidates.append({"path": entry["path"], "kind": "duplicate_pdf", "logical_bytes": entry["bytes"],
                                             "allocated_bytes": entry.get("allocated_bytes", 0), "sha256": group["sha256"],
                                             "suggested_keep": group["suggested_keep"], "tracked": Path(entry["path"]) in tracked,
                                             "status": "identical_content_reference_review_required"})
    result["duplicate_pdf_candidates"] = duplicate_candidates
    references = [*result["archives"], *duplicate_candidates, *result["large_experiment_directories"]]
    result["reference_scan"] = reference_scan(texts, references, result["errors"])
    result["fingerprint_failures"] = [record for record in memo.values() if record["hash_status"] != "stable_read"]
    safe = [item for item in result["caches"] if item["status"] == "regenerable_cache"]
    complete_zips = [item for item in result["archives"] if item["status"] == "all_payloads_present_optional_archive_cleanup"]
    result["totals"] = {"cache_directories": len(result["caches"]), "regenerable_cache_directories": len(safe),
                        "regenerable_cache_files": sum(item["files"] for item in safe),
                        "regenerable_cache_logical_bytes": sum(item["logical_bytes"] for item in safe),
                        "regenerable_cache_allocated_bytes": sum(item["allocated_bytes"] for item in safe),
                        "pdf_files": len(pdfs), "duplicate_pdf_groups": len(result["duplicate_pdf_groups"]),
                        "duplicate_pdf_candidates": len(duplicate_candidates),
                        "duplicate_pdf_logical_bytes": sum(item["logical_bytes"] for item in duplicate_candidates),
                        "archives": len(result["archives"]), "archives_all_payloads_present": len(complete_zips),
                        "archives_all_payloads_present_bytes": sum(item["logical_bytes"] for item in complete_zips)}
    (output / "CLEANUP_AUDIT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    fields = ["kind", "path", "status", "logical_bytes", "reference_file_count", "suggested_keep"]
    with (output / "CLEANUP_CANDIDATES.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows([*result["caches"], *references])
    print(json.dumps({"output": str(output), "totals": result["totals"], "reference_scan": result["reference_scan"], "errors": len(result["errors"]), "fingerprint_failures": len(result["fingerprint_failures"])}), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--inventory-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.root, args.inventory_dir, args.output_dir)


if __name__ == "__main__":
    main()
