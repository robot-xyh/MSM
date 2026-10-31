"""Read-only provenance audit; writes metadata only into this new audit directory."""

import ast
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SUMMARY = ROOT / "research_modules/d2_data_association/docs/formal_r0_identity_causal_pack_summary_20260731"
OLD = "98fd3978a6a6e9a0d1bc5ab341c5db8a77624214"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    with (OUT / name).open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def table(name, rows):
    if not rows:
        return
    with (OUT / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def git(*args):
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=45)
    return {"command": ["git", *args], "returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}


def main():
    if (OUT / "AUDIT_SNAPSHOT.json").exists():
        raise SystemExit("Existing audit snapshot: use a new audit directory.")
    started = datetime.now(timezone.utc).isoformat()
    pack = json.loads((SUMMARY / "identity_blocker_causal_pack.json").read_text())
    scope = pack["scope"]
    save("FORMAL_450_EXPECTED_SCOPE.json", {"extracted_from": str(SUMMARY / "identity_blocker_causal_pack.json"), "source_sha256": digest(SUMMARY / "identity_blocker_causal_pack.json"), "historical_not_current_verification": True, "scope": scope})
    expected = {}
    checks = []
    for line in (SUMMARY / "ARTIFACT_SHA256SUMS").read_text().splitlines():
        sha, rel = line.split(maxsplit=1)
        expected[sha] = rel
        path = SUMMARY / rel
        actual = digest(path) if path.is_file() else ""
        checks.append({"group": "D2_causal_summary", "path": str(path), "expected_sha256": sha, "actual_sha256": actual, "status": "match" if actual == sha else "missing" if not actual else "mismatch", "scope": "file_bytes"})
    for s in scope["shards"]:
        expected[s["archive_binding"]["archive_payload_sha256"].removeprefix("sha256:")] = s["shard_id"] + "/shard_payload.tar.zst"
        expected[s["archive_binding"]["archive_manifest_sha256"].removeprefix("sha256:")] = s["shard_id"] + "/shard_archive_manifest.json"
    expected.update({
        "4d8c8265dc43539dd51c2f753a09731ad437225277b182b60a8822ad580b5d06": "d6_per_episode_csv",
        "f37087dd8fa5608bf617f2270fcd07652722db9bae16f784e4d5ca3d21c7a349": "d6_aggregate_json",
        "86f812be3862ce4c464b39f2af17f6d4fbdc3df430373df1b4a61f433f10bc0b": "d6_report_md",
        scope["execution_plan_file_sha256"]: "execution_plan_file",
    })
    inventory = ROOT / "deliverables/project_audits/20260925_preservation_v1/FILES.jsonl.gz"
    prior_hits = []
    count = 0
    with gzip.open(inventory, "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            count += 1
            path = record["path"]
            sha = record.get("sha256", "").removeprefix("sha256:")
            if any(k in path.lower() for k in ("80e55eb", "partial_450", "shard_payload.tar.zst", "shard_archive_manifest.json", "formal_r0_identity_causal")) or sha in expected:
                prior_hits.append(record)
    save("PRIOR_INVENTORY_MATCHES.json", {"inventory": str(inventory), "inventory_sha256": digest(inventory), "records_read": count, "hits": prior_hits, "limitation": "Metadata-only inventory rows cannot be matched by checksum."})
    roots = ["/home/linux/Documents", "/home/linux/Downloads", "/tmp", "/var/tmp", "/dev/shm", "/mnt", "/media", "/run/media"]
    excluded = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".claude", ".mypy_cache"}
    candidates, errors = [], []
    files_seen = 0
    sizes = {s["archive_binding"]["archive_payload_size_bytes"] for s in scope["shards"]}
    for root in roots:
        if not Path(root).exists():
            errors.append({"path": root, "reason": "root_missing"})
            continue
        def onerror(error):
            errors.append({"path": error.filename, "reason": str(error)})
        for directory, dirs, files in os.walk(root, onerror=onerror, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in excluded and Path(directory, d) != OUT)
            for name in files:
                files_seen += 1
                path = Path(directory, name)
                lower = name.lower()
                relevant = any(k in lower for k in ("80e55eb", "b6289c5", "partial_450", "identity_blocker_", "artifact_inventory")) or lower in {"shard_payload.tar.zst", "shard_archive_manifest.json"}
                archive = lower.endswith((".tar.zst", ".tar.gz", ".tgz", ".zip", ".7z", ".tar", ".zst"))
                if archive:
                    try:
                        relevant = relevant or path.stat().st_size in sizes or any(k in lower for k in ("formal", "shard", "msm"))
                    except OSError as e:
                        onerror(e)
                if relevant:
                    try:
                        size = path.stat().st_size
                        sha = digest(path) if size < 4 * 1024 * 1024 or size in sizes else ""
                        candidates.append({"path": str(path), "bytes": size, "sha256": sha, "expected_match": expected.get(sha, ""), "symlink": path.is_symlink()})
                    except OSError as e:
                        onerror(e)
    save("ARCHIVE_SEARCH.json", {"roots": roots, "excluded_directory_names": sorted(excluded), "symlink_directories_followed": False, "files_seen": files_seen, "candidates": candidates, "errors": errors, "limits": ["No remote or unmounted backup searched", "Only candidate small files and exact archive-size candidates hashed", "Unrelated paper archives not opened", "No archive extracted", "No claim of whole-disk absence"]})
    print(f"Archive search: {files_seen} filenames, {len(candidates)} candidates, {len(errors)} limitations", flush=True)
    archive_rows = []
    for s in scope["shards"]:
        sha = s["archive_binding"]["archive_payload_sha256"].removeprefix("sha256:")
        found = [c["path"] for c in candidates if c["sha256"] == sha]
        archive_rows.append({"item": s["shard_id"], "historical_archive_root": scope["archive_root"], "expected_payload_basename": "shard_payload.tar.zst", "path_note": "root and shard identifier recorded; nested archive path not assumed", "completed_cells": s["completed_cell_count"], "source_commit": s["source_git_commit"], "execution_plan_sha256": s["execution_plan_sha256"], "expected_payload_bytes": s["archive_binding"]["archive_payload_size_bytes"], "expected_payload_sha256": sha, "expected_manifest_sha256": s["archive_binding"]["archive_manifest_sha256"].removeprefix("sha256:"), "located_payload": ";".join(found), "status": "载荷校验匹配" if found else "摘要可查、完整记录未定位"})
    table("ARCHIVE_LOCATION_REGISTER.csv", archive_rows)
    audit_root = Path("/home/linux/Documents/MSM-source-audit-result-20260803-v3")
    for line in (audit_root / "SHA256SUMS").read_text().splitlines():
        sha, rel = line.split(maxsplit=1)
        path = audit_root / rel
        actual = digest(path) if path.is_file() else ""
        checks.append({"group": "D6_source_audit", "path": str(path), "expected_sha256": sha, "actual_sha256": actual, "status": "match" if actual == sha else "missing" if not actual else "mismatch", "scope": "audit_result_bytes_not_source_payload"})
    source_audit = json.loads((audit_root / "source_audit.json").read_text())
    sources = []
    for source in source_audit["sources"].values():
        path = Path(source["source_root"])
        files = sorted(p for p in path.rglob("*") if p.is_file())
        metadata = []
        for p in files:
            if p.name in {"generation_session.json", "generation_checkpoint.json", "generation_result.json", "source_manifest.json", "dataset_manifest.json", "manifest.json"}:
                metadata.append({"path": str(p), "bytes": p.stat().st_size, "sha256": digest(p)})
        sources.append({"module": source["module"], "source_root": str(path), "exists": path.is_dir(), "file_count_now": len(files), "bytes_now": sum(p.stat().st_size for p in files), "historical_file_count": source["inventory_file_count"], "historical_bytes": source["inventory_total_size_bytes"], "historical_episode_count": source["semantic_episode_count"], "historical_record_count": source["semantic_record_count"], "historical_source_commit": source["source_git_commit"], "historical_status": source["status"], "current_metadata_hashes": metadata, "current_full_payload_hash_audit": False})
        for item in metadata:
            checks.append({"group": source["module"] + "_source_metadata", "path": item["path"], "expected_sha256": "", "actual_sha256": item["sha256"], "status": "fingerprint_only", "scope": "metadata_only_no_historical_byte_comparison"})
    save("SOURCE_DIRECTORY_STATUS.json", sources)
    table("SOURCE_INTEGRITY_CHECKS.csv", checks)
    modules = ["scalable_3d_simulation", "d1_sensor_fusion", "d2_data_association", "d3_assignment_planner", "d4_distributed_fallback", "d5_terminal_association", "d6_evaluation_metrics", "d7_proportional_guidance", "airsim_runtime", "independent_experiments"]
    versions = {name: git("diff", "--name-status", OLD, "HEAD", "--", "research_modules/" + name) for name in modules}
    save("VERSION_DIFFS.json", versions)
    imports = []
    for name in ("scalable_3d_simulation", "airsim_runtime", "independent_experiments"):
        for p in sorted((ROOT / "research_modules" / name).rglob("*.py")):
            if any(s in {"outputs", "tests", "__pycache__", "assets"} for s in p.parts):
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except (UnicodeError, SyntaxError) as error:
                imports.append({"file": str(p.relative_to(ROOT)), "line": 0, "import": "PARSE_ERROR: " + str(error)})
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    value = module + ":" + ",".join(n.name for n in node.names)
                elif isinstance(node, ast.Import):
                    value = ",".join(n.name for n in node.names)
                else:
                    continue
                if re.search(r"independent_experiments|d[1-7]_|temporal_geometry|TemporalGeometric|superglue|dual_optical|center_terminal", value):
                    imports.append({"file": str(p.relative_to(ROOT)), "line": node.lineno, "import": value})
    save("STATIC_IMPORT_EVIDENCE.json", {"imports": imports, "limits": "Static import evidence only; not execution proof. No project module imported by this audit."})
    attachments = []
    base = Path("/home/linux/.codex/attachments/7c61b9dc-0aec-4068-85b1-7b17498b1905")
    for name in ("pasted-text-1.txt", "pasted-text-2.txt"):
        p = base / name
        attachments.append({"path": str(p), "sha256": digest(p), "lines": len(p.read_text().splitlines())})
    paths = [scope["archive_root"], scope["execution_root"], scope["execution_root"] + "/d6_strict_partial_450_b6289c5"]
    snapshot = {"started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(), "root": str(ROOT), "head": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"), "original_tip": git("rev-parse", "feat/scalable-3d-200v200"), "original_tip_ancestor": git("merge-base", "--is-ancestor", OLD, "HEAD"), "tags": git("tag", "-l", "scalable3d-*"), "inventory_history": git("log", "--format=%H %aI %s", "--all", "--", str((SUMMARY / "artifact_inventory.json").relative_to(ROOT))), "original_requirements": attachments, "historical_paths": [{"path": p, "exists": Path(p).exists()} for p in paths], "goal_status": "See separate current get_goal tool result; audit does not create or resume a goal", "experiments_run": False, "models_loaded": False, "payload_audit_repeated": False}
    save("AUDIT_SNAPSHOT.json", snapshot)
    print(json.dumps({"summary_checksum_matches": sum(c["status"] == "match" for c in checks), "missing_summary_members": sum(c["status"] == "missing" for c in checks), "source_directories": [{k: s[k] for k in ("module", "file_count_now", "bytes_now", "historical_file_count", "historical_bytes")} for s in sources], "archive_payloads_found": sum(bool(r["located_payload"]) for r in archive_rows)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
