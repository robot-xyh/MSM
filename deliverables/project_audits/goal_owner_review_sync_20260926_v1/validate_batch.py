"""Final documentation and evidence checks; never imports research modules."""

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    destination = OUT / "BATCH_VALIDATION.json"
    if destination.exists():
        raise SystemExit("Validation exists; refusing overwrite.")
    checks = []

    def check(name, result, details):
        checks.append({"name": name, "passed": bool(result), "details": details})

    summary = load(OUT / "OWNER_REVIEW_SUMMARY.json")
    check("all_requirements_and_owners", summary["requirement_count"] == 60
          and len(summary["owner_results"]) == 8 and all(r["coverage_complete"] for r in summary["owner_results"]),
          {"requirements": summary["requirement_count"], "reviews": summary["review_total"]})
    check("original_classifications_retained", not summary["classification_differences"],
          summary["retained_status_counts"])
    main = load(OUT / "MAIN_REVIEW.json")
    changed = [p for p, value in main["source_hashes"].items() if sha(ROOT / p) != value]
    check("original_goal_sources_unchanged", not changed, changed)

    prior = load(ROOT / "deliverables/project_audits/goal_evidence_followup_20260926_v1/INPUT_FINGERPRINTS.json")
    report_paths = {r["path"] for r in load(OUT / "REPORTS_BEFORE.json")["documents"]}
    original_inputs = {p: v for p, v in prior.items() if p not in report_paths}
    differences = [p for p, value in original_inputs.items() if sha(ROOT / p) != value]
    check("prior_experiment_inputs_unchanged", not differences,
          {"checked": len(original_inputs), "changed": differences})
    report = load(OUT / "REPORT_VALIDATION.json")
    check("report_structural_validation", report["passed"] and len(report["documents"]) == 8,
          {"documents": len(report["documents"]), "rendered": len(report["rendered"])})
    check("current_reports_match_validation", all(sha(ROOT / r["path"]) == r["after_sha256"]
                                                for r in report["documents"]), 8)

    errata = load(OUT / "METADATA_ERRATA.json")
    fields = []
    for item in errata["items"]:
        value = load(ROOT / item["source"])
        for component in item["field"].split("."):
            value = value[component]
        fields.append({"id": item["id"], "source": item["source"], "sha256": sha(ROOT / item["source"]),
                       "original_field_matches": value == item["original"]})
    check("errata_originals_still_match", all(r["original_field_matches"] for r in fields), fields)

    broken, inspected = [], 0
    for path in OUT.rglob("*.md"):
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            target = target.strip("<>").split("#", 1)[0]
            if not target or "://" in target:
                continue
            target = re.sub(r":\d+$", "", target)
            resolved = (path.parent / target).resolve()
            inspected += 1
            if resolved != destination and not resolved.exists():
                broken.append({"document": str(path.relative_to(OUT)), "target": target})
    check("new_audit_links", not broken, {"checked": inspected, "broken": broken})
    with (OUT / "NEXT_ACTIONS.csv").open(encoding="utf-8", newline="") as handle:
        actions = list(csv.DictReader(handle))
    check("action_ids_preserved", {r["id"] for r in actions} == {f"A{i:02d}" for i in range(1, 13)}, len(actions))
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(OUT), "-p", "test_*.py", "-v"],
                           capture_output=True, text=True, cwd=ROOT, timeout=30)
    check("audit_unit_tests", tests.returncode == 0, tests.stdout + tests.stderr)
    for name, command in (
        ("no_module_edits", ["git", "diff", "--name-only", "--", "research_modules", "subagent_reviews"]),
        ("diff_whitespace", ["git", "diff", "--check", "--", "deliverables/project_audits", "deliverables/leadership_report"]),
    ):
        result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT, timeout=30)
        check(name, result.returncode == 0 and not result.stdout.strip(), result.stdout + result.stderr)
    value = {"created_at": datetime.now(timezone.utc).isoformat(),
             "passed": all(r["passed"] for r in checks), "checks": checks,
             "visual_review": "Main inspected the four changed-note preview pages; no text overlap or clipping observed on those pages.",
             "algorithm_execution": False, "module_tests_run": False}
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"passed": value["passed"], "check_count": len(checks),
                      "failures": [r for r in checks if not r["passed"]]}, ensure_ascii=False, indent=2))
    if not value["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
