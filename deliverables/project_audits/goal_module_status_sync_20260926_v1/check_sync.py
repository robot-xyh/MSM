"""Audit documentation-only updates and preservation of historical bodies."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SCOPES = [
    "research_modules/d3_assignment_planner", "research_modules/d4_distributed_fallback",
    "research_modules/d5_terminal_association", "research_modules/d6_evaluation_metrics",
    "subagent_reviews/D3_*", "subagent_reviews/D4_*", "subagent_reviews/D5_*", "subagent_reviews/D6_*",
    "subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md", "research_modules/scalable_3d_simulation/README.md",
]
BEGIN = "<!-- evidence-status-sync:20260926:begin -->"
END = "<!-- evidence-status-sync:20260926:end -->"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, timeout=30, check=True)
    return result.stdout.decode()


def save(name, value):
    with (OUT / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def snapshot():
    if (OUT / "BEFORE.json").exists():
        raise SystemExit("Snapshot exists.")
    paths = git("ls-files", "-z", "--", *SCOPES).strip("\0").split("\0")
    records = []
    for name in paths:
        data = (ROOT / name).read_bytes()
        record = {"path": name, "sha256": sha(data), "bytes": len(data)}
        if name.endswith(".md"):
            record["text"] = data.decode("utf-8")
        records.append(record)
    extra = {}
    prior = ROOT / "deliverables/project_audits/goal_owner_review_sync_20260926_v1/REPORT_VALIDATION.json"
    for row in json.loads(prior.read_text())["documents"]:
        extra[row["path"]] = sha((ROOT / row["path"]).read_bytes())
    save("BEFORE.json", {"created_at": datetime.now(timezone.utc).isoformat(),
                         "head": git("rev-parse", "HEAD").strip(),
                         "initial_diff": git("diff", "--name-only", "--", *SCOPES),
                         "files": records, "reports": extra})
    print(json.dumps({"files": len(records), "reports": len(extra)}))


def strip_blocks(text):
    return re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n\n", "", text, flags=re.S)


def verify():
    if (OUT / "VALIDATION_RECORD.json").exists():
        raise SystemExit("Validation exists.")
    before = json.loads((OUT / "BEFORE.json").read_text())
    checks, changes, failures = [], [], []
    original_names = {r["path"] for r in before["files"]}
    for row in before["files"]:
        path = ROOT / row["path"]
        if not path.exists():
            failures.append({"path": row["path"], "error": "removed"})
            continue
        data = path.read_bytes()
        if sha(data) == row["sha256"]:
            continue
        if path.suffix != ".md":
            failures.append({"path": row["path"], "error": "non_document_changed"})
            continue
        content = data.decode("utf-8")
        preserved = strip_blocks(content) == row["text"]
        changes.append({"path": row["path"], "before_sha256": row["sha256"],
                        "after_sha256": sha(data), "historical_body_preserved": preserved})
        if not preserved:
            failures.append({"path": row["path"], "error": "historical_body_changed"})
    new_paths = git("ls-files", "--others", "--exclude-standard", "-z", "--", *SCOPES).strip("\0").split("\0")
    new_paths = [p for p in new_paths if p]
    for name in new_paths:
        if not name.endswith("/docs/CURRENT_EVIDENCE_STATUS_CN.md"):
            failures.append({"path": name, "error": "unexpected_new_module_file"})
    actual_module_changes = {r["path"] for r in changes if not r["path"].endswith("MAIN_IMPLEMENTATION_GAP_AUDIT.md")
                             and r["path"] != "research_modules/scalable_3d_simulation/README.md"} | set(new_paths)
    declared = set()
    for module in ("D3", "D4", "D5", "D6"):
        listing = OUT / "owners" / (module + "_sync.json")
        result = json.loads(listing.read_text())
        changed_files = result["changed_files"]
        declared.update(changed_files)
        checks.append({"module": module, "changed_files": len(changed_files), "owner_manifest": str(listing.relative_to(ROOT))})
    if declared != actual_module_changes:
        failures.append({"error": "owner_change_list_mismatch", "undeclared": sorted(actual_module_changes - declared),
                         "declared_but_unchanged": sorted(declared - actual_module_changes)})
    links = []
    for name in [r["path"] for r in changes] + new_paths:
        path = ROOT / name
        content = path.read_text()
        blocks = re.findall(re.escape(BEGIN) + r"(.*?)" + re.escape(END), content, flags=re.S)
        selected = "\n".join(blocks) if name in original_names else content
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", selected):
            target = target.strip("<>").split("#", 1)[0]
            if not target or "://" in target:
                continue
            resolved = (path.parent / target).resolve()
            links.append({"source": name, "target": target, "exists": resolved.exists()})
            if not resolved.exists():
                failures.append({"path": name, "error": "new_link_missing", "target": target})
    for path, digest in before["reports"].items():
        if sha((ROOT / path).read_bytes()) != digest:
            failures.append({"path": path, "error": "prior_report_modified"})
    whitespace = subprocess.run(["git", "diff", "--check", "--", *SCOPES], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
    if whitespace.returncode:
        failures.append({"error": "whitespace", "output": whitespace.stdout + whitespace.stderr})
    value = {"created_at": datetime.now(timezone.utc).isoformat(), "passed": not failures,
             "tracked_file_count": len(before["files"]), "module_owner_checks": checks,
             "changed_tracked_documents": changes, "new_module_documents": new_paths,
             "new_links": links, "previous_reports_unchanged": not any(
                 f["error"] == "prior_report_modified" for f in failures), "failures": failures,
             "algorithm_tests_run": False, "experiments_run": False}
    save("VALIDATION_RECORD.json", value)
    print(json.dumps({"passed": not failures, "changed_tracked_documents": len(changes),
                      "new_module_documents": len(new_paths), "new_links": len(links),
                      "failures": failures}, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("snapshot", "verify"))
    args = parser.parse_args()
    snapshot() if args.action == "snapshot" else verify()
