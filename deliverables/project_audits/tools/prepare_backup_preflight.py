"""Inspect backup scope and storage without copying or changing source files."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import stat
import subprocess

from prepare_preservation_register import SIBLINGS, file_record


GIB = 1024**3
NESTED_REPOSITORIES = ("Fastlab_world_fly", "YOPO", "ego-planner", "ego-planner-swarm")
COUNT_FIELDS = ("file_count", "logical_bytes", "allocated_bytes", "directory_count", "symlink_count", "special_count", "error_count")


def command_metadata(args: list[str]) -> dict:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=60,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        return {"command": args, "returncode": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": args, "returncode": None, "error": str(exc)}


def required_bytes(logical_bytes: int) -> int:
    return (logical_bytes * 110 + 99) // 100 + GIB


def destination_check(destination: Path | None, sources: list[Path], needed: int) -> dict:
    result = {"path": str(destination) if destination else None,
              "copy_started": False, "independence_verified": False,
              "write_probe_performed": False, "required_available_bytes": needed}
    if destination is None:
        return {**result, "status": "destination_not_specified"}
    destination = destination.resolve()
    result["resolved_path"] = str(destination)
    if not destination.is_dir():
        return {**result, "status": "existing_destination_directory_required"}
    if any(destination == p or destination.is_relative_to(p) or p.is_relative_to(destination) for p in sources):
        return {**result, "status": "source_destination_overlap"}
    try:
        info = destination.stat()
        fs = os.statvfs(destination)
        source_devices = {p.stat().st_dev for p in sources if p.exists()}
        result.update(device=info.st_dev, available_bytes=fs.f_bavail * fs.f_frsize,
                      writable_by_access_check=os.access(destination, os.W_OK | os.X_OK),
                      mount=command_metadata(["findmnt", "--json", "--target", str(destination),
                                              "--output", "TARGET,SOURCE,FSTYPE,OPTIONS"]))
        if info.st_dev in source_devices:
            status = "same_filesystem_not_independent"
        elif not result["writable_by_access_check"]:
            status = "not_writable_by_access_check"
        elif result["available_bytes"] < needed:
            status = "insufficient_capacity"
        else:
            status = "physical_or_service_independence_unverified"
        return {**result, "status": status}
    except OSError as exc:
        return {**result, "status": "inspection_error", "error": str(exc)}


def scan_tree(source: Path, excluded: Path):
    pending = [source]
    while pending:
        path = pending.pop()
        if path == excluded:
            continue
        row = {"path": str(path), "relative_path": str(path.relative_to(source)),
               "source_root": str(source)}
        try:
            info = path.lstat()
            row.update(device=info.st_dev, inode=info.st_ino, mode=stat.S_IMODE(info.st_mode),
                       bytes=info.st_size, allocated_bytes=info.st_blocks * 512,
                       mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns)
            if stat.S_ISLNK(info.st_mode):
                row.update(kind="symlink", link_target=os.readlink(path), target_followed=False)
            elif stat.S_ISREG(info.st_mode):
                row["kind"] = "file"
            elif stat.S_ISDIR(info.st_mode):
                row["kind"] = "directory"
                with os.scandir(path) as children:
                    pending.extend(sorted((Path(p.path) for p in children), reverse=True))
            else:
                row["kind"] = "special"
        except OSError as exc:
            row["error"] = str(exc)
        yield row


def add_counts(counts: Counter, row: dict) -> None:
    kind = row.get("kind")
    if kind == "file":
        counts["file_count"] += 1
        counts["logical_bytes"] += row["bytes"]
        counts["allocated_bytes"] += row["allocated_bytes"]
    elif kind in {"directory", "symlink", "special"}:
        counts[kind + "_count"] += 1
    if "error" in row:
        counts["error_count"] += 1


def repository_metadata(path: Path) -> dict:
    result = {"path": str(path), "exists": path.is_dir()}
    if not path.is_dir():
        return result
    for label, args in {
        "head": ["rev-parse", "HEAD"],
        "status": ["status", "--porcelain=v1", "--untracked-files=all"],
        "git_dir": ["rev-parse", "--absolute-git-dir"],
        "common_dir": ["rev-parse", "--path-format=absolute", "--git-common-dir"],
    }.items():
        result[label] = command_metadata(["git", "-C", str(path), *args])
    return result


def preflight(root: Path, output: Path, destination: Path | None = None) -> dict:
    root = root.resolve()
    output = output.resolve()
    audit_root = (root / "deliverables" / "project_audits").resolve()
    if output == audit_root or not output.is_relative_to(audit_root):
        raise ValueError("Output must be a new directory below deliverables/project_audits.")
    sources = [root, *(root.parent / name for name in SIBLINGS)]
    if any(p.is_symlink() for p in sources):
        raise ValueError("Source roots must not be symbolic links.")
    for index, source in enumerate(sources):
        if any(source == other or source.is_relative_to(other) or other.is_relative_to(source)
               for other in sources[:index]):
            raise ValueError("Source roots must not overlap.")
    output.mkdir(parents=True, exist_ok=False)
    summary = {
        "schema": "msm-backup-preflight-v1", "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "backup_created": False, "restore_verified": False, "source_payload_hashed": False,
        "source_revision": command_metadata(["git", "-C", str(root), "rev-parse", "HEAD"]),
        "revision_scope": "Repository state at preflight, not historical experiment execution revision.",
        "scope": "Entire repository and six sibling trees, including Git metadata, ignored files, environments and caches.",
        "excluded_tree": str(output),
        "exclusion_reason": "This new preflight output is recorded separately after generation.",
        "inventory_limit": "Sequential metadata inventory, not an atomic snapshot or source-content verification. Symlinks are recorded, not followed. Hardlinks are counted by path.",
        "capacity_rule": "ceil(1.10 * logical bytes) + 1 GiB; planning reserve, not an exact destination allocation estimate.",
        "sources": [], "errors": [], "links": [], "special_files": [],
        "mounts": command_metadata(["findmnt", "--json", "--output", "TARGET,SOURCE,FSTYPE,OPTIONS"]),
        "block_devices": command_metadata(["lsblk", "--json", "--bytes", "--output", "NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,PKNAME"]),
        "worktrees": command_metadata(["git", "-C", str(root), "worktree", "list", "--porcelain"]),
    }
    nested = {root / "paper" / name: Counter() for name in NESTED_REPOSITORIES}
    totals = Counter()
    inventory = output / "BACKUP_SOURCE_FILES.jsonl.gz"
    with gzip.open(inventory, "wt", encoding="utf-8") as stream:
        for source in sources:
            counts = Counter()
            source_exists = source.is_dir()
            for row in scan_tree(source, output):
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                add_counts(counts, row)
                for path, group in nested.items():
                    if Path(row["path"]).is_relative_to(path):
                        add_counts(group, row)
                if "error" in row:
                    summary["errors"].append(row)
                if row.get("kind") == "symlink":
                    summary["links"].append(row)
                if row.get("kind") == "special":
                    summary["special_files"].append(row)
            totals.update(counts)
            item = {"path": str(source), "exists": source_exists,
                    "destination_relative_path": source.name,
                    **{field: counts[field] for field in COUNT_FIELDS}}
            summary["sources"].append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
    summary["totals"] = {field: totals[field] for field in COUNT_FIELDS}
    summary["nested_repository_sizes"] = [
        {"path": str(path), **{field: counts[field] for field in COUNT_FIELDS}}
        for path, counts in nested.items()
    ]
    summary["repositories"] = [repository_metadata(p) for p in [root, root.parent / SIBLINGS[0], *nested]] if SIBLINGS else [repository_metadata(root)]
    fs = os.statvfs(root)
    summary["source_filesystem"] = {"device": root.stat().st_dev, "available_bytes": fs.f_bavail * fs.f_frsize}
    summary["destination"] = destination_check(destination, sources, required_bytes(totals["logical_bytes"]))
    summary["inventory"] = file_record(inventory, True)
    summary["tool"] = file_record(Path(__file__).resolve(), True)
    summary["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    with (output / "BACKUP_SCOPE.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "exists", "destination_relative_path", *COUNT_FIELDS], lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary["sources"])
    (output / "BACKUP_PREFLIGHT.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--destination", type=Path, help="Existing backup parent to inspect; nothing is written there.")
    args = parser.parse_args()
    result = preflight(args.root, args.output_dir, args.destination)
    print(json.dumps({"totals": result["totals"], "destination_status": result["destination"]["status"], "backup_created": False}), flush=True)


if __name__ == "__main__":
    main()
