"""Recheck and remove only the reviewed main-repository cleanup candidates."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile


ROOT = Path("/home/linux/Documents/MSM")
AUDIT = ROOT / "deliverables/project_audits/20260926_cleanup_review_v1"
OUTPUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "deliverables/project_audits/tools"))
from audit_cleanup_candidates import cache_record, tracked_paths


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def signature(path):
    info = path.lstat()
    return [info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def file_check(path, expected=None):
    before = signature(path)
    if not stat.S_ISREG(before[2]) or path.resolve() != path:
        raise ValueError("Not an ordinary file with a direct path: " + str(path))
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if before != signature(path):
        raise ValueError("File changed during verification: " + str(path))
    if expected is not None and digest != expected:
        raise ValueError("Hash differs from reviewed evidence: " + str(path))
    info = path.lstat()
    return {"path": str(path), "signature": before, "sha256": digest,
            "logical_bytes": info.st_size,
            "allocated_bytes": info.st_blocks * 512 if info.st_nlink == 1 else 0}


def tree_signature(path):
    result = {}
    for current, directories, files in os.walk(path, followlinks=False):
        for name in [".", *directories, *files]:
            item = Path(current) if name == "." else Path(current) / name
            value = signature(item)
            if stat.S_ISLNK(value[2]):
                raise ValueError("Symlink appeared in cache: " + str(item))
            result[str(item.relative_to(path))] = value
    return result


def git_state(repositories):
    return {str(repo): subprocess.check_output(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
        text=True) for repo in repositories}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    summary_path = OUTPUT / ("EXECUTION.json" if args.execute else "PREFLIGHT.json")
    journal_path = OUTPUT / ("EXECUTION.jsonl" if args.execute else "PREFLIGHT.jsonl")
    if summary_path.exists() or journal_path.exists():
        raise FileExistsError("This execution already has records; inspect them before continuing.")

    base = json.loads((AUDIT / "CLEANUP_AUDIT.json").read_text())
    extra = json.loads((AUDIT / "SUPPLEMENTAL_REVIEW.json").read_text())
    with (AUDIT / "REVIEWED_CLEANUP_LIST.csv").open(newline="") as stream:
        selected = [r for r in csv.DictReader(stream)
                    if r["scope"] == "主仓库" and r["decision"] == "可优先清理"]
    expected = Counter({"缓存目录": 84, "ZIP": 7, "论文中间文本": 3})
    if Counter(r["category"] for r in selected) != expected:
        raise ValueError("Candidate scope differs from the reviewed 84/7/3 selection.")
    targets = [Path(r["path"]) for r in selected]
    if len(set(targets)) != 94:
        raise ValueError("Duplicate cleanup target.")
    for path in targets:
        if not path.is_relative_to(ROOT) or path == ROOT or path.resolve() != path:
            raise ValueError("Target outside the main repository or contains symlinks.")
        if ".git" in path.parts:
            raise ValueError("Git storage is not a cleanup target.")

    repositories = [ROOT, *(ROOT / "paper" / name for name in
                           ("YOPO", "Fastlab_world_fly", "ego-planner", "ego-planner-swarm"))]
    tracked = set().union(*(tracked_paths(repo) for repo in repositories))
    archives = {r["path"]: r for r in base["archives"]}
    caches = {r["path"]: r for r in base["caches"]}
    texts = {r["path"]: r for r in extra["derived_texts"]}
    retained = {}
    records = []
    before_git = git_state(repositories)
    free_before = shutil.disk_usage(ROOT).free

    def keep(path, digest=None):
        if any(path == target or path.is_relative_to(target) for target in targets):
            raise ValueError("Retained payload is also selected for cleanup: " + str(path))
        if str(path) not in retained:
            retained[str(path)] = file_check(path, digest)
        elif digest and retained[str(path)]["sha256"] != digest:
            raise ValueError("Conflicting retained payload hash.")

    with journal_path.open("x") as journal:
        def log(event):
            journal.write(json.dumps({"time": timestamp(), **event}, ensure_ascii=False) + "\n")
            journal.flush()

        log({"event": "start", "execute": args.execute, "selected_count": len(selected)})
        for row in selected:
            path = Path(row["path"])
            record = {"path": str(path), "category": row["category"], "status": "pending"}
            try:
                if path in tracked or any(p.is_relative_to(path) for p in tracked):
                    raise ValueError("Target includes Git-tracked content.")
                if row["category"] == "缓存目录":
                    current = cache_record(path, tracked)
                    old = caches[str(path)]
                    if current["status"] != "regenerable_cache":
                        raise ValueError("Cache no longer passes source/format checks.")
                    if any(current[k] != old[k] for k in ("files", "logical_bytes")):
                        raise ValueError("Cache contents changed since review.")
                    record.update({k: current[k] for k in ("files", "logical_bytes", "allocated_bytes")})
                    record["tree_signature"] = tree_signature(path)
                    record["files_to_remove"] = [name for name, info in record["tree_signature"].items()
                                                 if stat.S_ISREG(info[2])]
                elif row["category"] == "ZIP":
                    old = archives[str(path)]
                    record.update(file_check(path, old["fingerprint"]["sha256"]))
                    for member in old["members"]:
                        if member["match"]:
                            keep(Path(member["match"]), member["sha256"])
                        else:
                            link = extra["archive_review"]
                            if str(path) != link["path"] or member["name"] != link["symlink_member"]:
                                raise ValueError("Archive member lacks a retained copy.")
                            target = path.parent / member["name"]
                            with zipfile.ZipFile(path) as archive:
                                stored = archive.read(member["name"])
                            if not target.is_symlink() or stored != os.fsencode(os.readlink(target)):
                                raise ValueError("Archive symlink no longer matches.")
                            record["retained_symlink"] = {"path": str(target), "target": os.readlink(target)}
                    record["files"] = 1
                elif row["category"] == "论文中间文本":
                    old = texts[str(path)]
                    record.update(file_check(path, old["sha256"]))
                    keep(Path(old["source_pdf"]))
                    generated = subprocess.run(["pdftotext", old["source_pdf"], "-"],
                                               check=True, capture_output=True, timeout=30).stdout
                    if hashlib.sha256(generated).hexdigest() != old["sha256"]:
                        raise ValueError("PDF no longer regenerates the same text.")
                    record["files"] = 1
                else:
                    raise ValueError("Unexpected cleanup category.")
                record["status"] = "verified"
            except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
                record["status"] = "skipped"
                record["reason"] = str(exc)
            records.append(record)
            log({"event": "verified" if record["status"] == "verified" else "skipped",
                 "path": str(path), "reason": record.get("reason")})
        print(json.dumps({"verified": sum(r["status"] == "verified" for r in records),
                          "skipped": sum(r["status"] == "skipped" for r in records),
                          "execute": args.execute}), flush=True)

        if args.execute:
            for path, info in retained.items():
                if signature(Path(path)) != info["signature"]:
                    raise ValueError("Retained payload changed after verification: " + path)
            for record in records:
                if record["status"] != "verified":
                    continue
                path = Path(record["path"])
                try:
                    if record["category"] == "缓存目录":
                        if tree_signature(path) != record["tree_signature"]:
                            raise ValueError("Cache changed before deletion.")
                        log({"event": "deleting", "path": str(path)})
                        shutil.rmtree(path)
                    else:
                        if signature(path) != record["signature"]:
                            raise ValueError("File changed before deletion.")
                        log({"event": "deleting", "path": str(path)})
                        path.unlink()
                    record["status"] = "deleted"
                except (OSError, ValueError) as exc:
                    record["status"] = "deletion_incomplete"
                    record["reason"] = str(exc)
                log({"event": record["status"], "path": str(path), "reason": record.get("reason")})

        retained_unchanged = all(signature(Path(path)) == info["signature"]
                                 for path, info in retained.items())
        symlinks_unchanged = all(Path(r["retained_symlink"]["path"]).is_symlink()
                                and os.readlink(r["retained_symlink"]["path"]) == r["retained_symlink"]["target"]
                                for r in records if "retained_symlink" in r)
        after_git = git_state(repositories)
        removed = [r for r in records if r["status"] == "deleted"]
        for record in records:
            record.pop("tree_signature", None)
        report = {"schema": "msm.reviewed-cleanup.execution.v1", "finished_at_utc": timestamp(),
                  "execute": args.execute, "selected_count": len(selected), "records": records,
                  "deleted_items": len(removed), "deleted_files": sum(r["files"] for r in removed),
                  "deleted_by_category": dict(Counter(r["category"] for r in removed)),
                  "deleted_logical_bytes": sum(r["logical_bytes"] for r in removed),
                  "deleted_file_allocated_bytes": sum(r["allocated_bytes"] for r in removed),
                  "retained_files": list(retained.values()), "retained_files_unchanged": retained_unchanged,
                  "retained_symlinks_unchanged": symlinks_unchanged,
                  "tracked_git_status_unchanged": before_git == after_git,
                  "git_status_before": before_git, "git_status_after": after_git,
                  "disk_free_before_bytes": free_before, "disk_free_after_bytes": shutil.disk_usage(ROOT).free,
                  "source_audit": file_check(AUDIT / "CLEANUP_AUDIT.json"),
                  "reviewed_list": file_check(AUDIT / "REVIEWED_CLEANUP_LIST.csv"),
                  "executor": file_check(Path(__file__).resolve())}
        with summary_path.open("x") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        log({"event": "finished", "deleted_items": len(removed)})
        print(json.dumps({k: report[k] for k in ("execute", "deleted_items", "deleted_files",
              "deleted_by_category", "deleted_logical_bytes", "deleted_file_allocated_bytes",
              "retained_files_unchanged", "retained_symlinks_unchanged", "tracked_git_status_unchanged")},
              ensure_ascii=False), flush=True)
        if not all((retained_unchanged, symlinks_unchanged, before_git == after_git)):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
