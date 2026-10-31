"""Validate this audit's derived artifacts without running experiment code."""

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

from audit_provenance import ROOT, OUT, EXP, inspect_imports


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    destination = OUT / "VALIDATION_RECORD.json"
    if destination.exists():
        raise SystemExit("Validation record exists; do not overwrite it.")
    checks = []

    def check(name, passed, details):
        checks.append({"name": name, "passed": bool(passed), "details": details})

    fingerprints = read_json(OUT / "INPUT_FINGERPRINTS.json")
    changed = [path for path, value in fingerprints.items()
               if not (ROOT / path).is_file() or digest((ROOT / path).read_bytes()) != value]
    check("original_files_unchanged", not changed,
          {"file_count": len(fingerprints), "changed": changed})
    record = read_json(OUT / "PROVENANCE_FOLLOWUP.json")
    archive_path = OUT / "ATTESTED_EVIDENCE.zip"
    members = rows(OUT / "PRESERVED_MEMBERS.csv")
    with zipfile.ZipFile(archive_path) as archive:
        corrupt = archive.testzip()
        differences = [r["member"] for r in members
                       if digest(archive.read(r["member"])) != r["sha256"]]
        names_match = set(archive.namelist()) == {r["member"] for r in members}
    check("archive_members", corrupt is None and not differences and names_match,
          {"count": len(members), "crc_error": corrupt, "hash_differences": differences})
    check("archive_identity", digest(archive_path.read_bytes()) == record["archive_sha256"],
          record["archive_sha256"])
    sources = [r for r in members if r["role"] == "source"]
    check("sixteen_attested_sources", len(sources) == 16 and all(
        r["sha256"] == r["historical_expected_sha256"] for r in sources), len(sources))

    source_rows = rows(OUT / "STATIC_SOURCE_REGISTER.csv")
    calls = []
    for row in source_rows:
        _, found = inspect_imports(ROOT / row["path"], [EXP, ROOT, ROOT / "research_modules"])
        calls.extend({"batch": row["batch"], "source": row["path"], **item} for item in found)
    key = lambda row: (row["batch"], row["source"], row["line"], row["call"])
    saved_calls = read_json(OUT / "DYNAMIC_IMPORT_NOTES.json")
    check("dynamic_notes_reparsed", sorted(calls, key=key) == sorted(saved_calls, key=key),
          {"count": len(calls), "method_eval_is_not_dynamic_import": True})
    check("static_register_counts", all(
        sum(r["batch"] == batch for r in source_rows) == item["local_file_count"]
        and sum(r["batch"] == batch for r in calls) == item["dynamic_call_count"]
        for batch, item in record["closures"].items()), len(source_rows))
    configs = record["search_config_evidence"]["records"]
    check("saved_search_configurations", len(configs) == 45 and all(
        isinstance(item["config"], dict) and item["config"].get("seed") is not None
        and not item["source_keys_present"] for item in configs), len(configs))

    broken, count = [], 0
    for path in OUT.glob("*.md"):
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            target = target.split("#")[0]
            if not target or "://" in target:
                continue
            referenced = (path.parent / target).resolve()
            count += 1
            if referenced != destination and not referenced.exists():
                broken.append({"document": path.name, "target": target})
    check("document_links", not broken, {"checked": count, "broken": broken})
    actions = rows(OUT / "NEXT_ACTIONS.csv")
    check("twelve_actions_preserved", {r["id"] for r in actions} == {
        f"A{i:02d}" for i in range(1, 13)
    } and len(actions) == 12, len(actions))

    tests = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(OUT), "-p", "test_*.py", "-v"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    check("artificial_file_unit_tests", tests.returncode == 0,
          {"returncode": tests.returncode, "output": tests.stdout + tests.stderr})
    guard = subprocess.run([sys.executable, str(OUT / "audit_provenance.py")],
                           cwd=ROOT, capture_output=True, text=True, timeout=30)
    check("existing_batch_refused", guard.returncode != 0 and "nothing overwritten" in guard.stderr,
          {"returncode": guard.returncode, "output": guard.stdout + guard.stderr})
    diff = subprocess.run(["git", "diff", "--name-only", "--", "research_modules"],
                          cwd=ROOT, capture_output=True, text=True, timeout=30)
    check("no_tracked_research_changes", diff.returncode == 0 and not diff.stdout.strip(), diff.stdout)
    whitespace = subprocess.run(["git", "diff", "--check", "--", "deliverables/project_audits"],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
    check("tracked_audit_diff_whitespace", whitespace.returncode == 0,
          whitespace.stdout + whitespace.stderr)
    check("new_batch_trailing_whitespace", all(
        line == line.rstrip() for path in OUT.iterdir() if path.suffix in {".md", ".py"}
        for line in path.read_text().splitlines()), "new Markdown and Python files")

    value = {"created_at": datetime.now(timezone.utc).isoformat(),
             "passed": all(c["passed"] for c in checks), "checks": checks,
             "scripts_sha256": {p.name: digest(p.read_bytes()) for p in OUT.glob("*.py")},
             "scope": "Audit artifact validation only; no algorithm execution or rescoring."}
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": value["passed"], "checks": len(checks),
                      "failures": [c for c in checks if not c["passed"]]}, ensure_ascii=False, indent=2))
    if not value["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
