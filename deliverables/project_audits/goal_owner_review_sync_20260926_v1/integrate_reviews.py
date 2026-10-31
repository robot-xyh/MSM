"""Validate owner opinions and preserve original requirement classifications."""

from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
REGISTER = ROOT / "deliverables/project_audits/goal_resume_audit_20260926_v1/GOAL_REQUIREMENT_EVIDENCE.csv"


def owners(value):
    selected = {"main"} if "main" in value else set()
    for start, end in re.findall(r"D([1-7])至D([1-7])", value):
        selected.update(f"D{i}" for i in range(int(start), int(end) + 1))
    selected.update(re.findall(r"D[1-7]", value))
    return selected


def main():
    destination = OUT / "OWNER_REVIEW_SUMMARY.json"
    if destination.exists():
        raise SystemExit("Review summary exists; refusing overwrite.")
    with REGISTER.open(encoding="utf-8", newline="") as handle:
        original = list(csv.DictReader(handle))
    by_id = {r["requirement_id"]: r for r in original}
    reviews, validation, revisions = {}, [], []
    for module in ["main", *(f"D{i}" for i in range(1, 8))]:
        path = OUT / ("MAIN_REVIEW.json" if module == "main" else f"owners/{module}_review.json")
        value = json.loads(path.read_text())
        rows = value["requirements"]
        expected = {r["requirement_id"] for r in original if module in owners(r["owner"])}
        actual = [r["requirement_id"] for r in rows]
        if set(actual) != expected or len(actual) != len(expected):
            raise ValueError(f"coverage mismatch {module}: {sorted(expected - set(actual))}")
        evidence = set()
        for row in rows:
            if row["original_status"] != by_id[row["requirement_id"]]["status"]:
                raise ValueError(f"original status mismatch: {module} {row['requirement_id']}")
            if row["review_result"] not in {"认可", "限定认可", "需修订", "证据不足"}:
                raise ValueError(f"unknown review result: {row['review_result']}")
            if row["suggested_status"] not in {"已完成", "部分完成", "未完成", "证据不足"}:
                raise ValueError("unknown suggested status")
            for item in row["evidence"]:
                if not isinstance(item, str):
                    raise TypeError(f"evidence is not a path: {module}")
                evidence.add(item)
                target = item.split("#", 1)[0]
                if not (ROOT / target).exists():
                    raise ValueError(f"missing evidence {module}: {target}")
            if row["review_result"] == "需修订" or row["suggested_status"] != row["original_status"]:
                revisions.append({"module": module, **row})
        reviews[module] = value
        validation.append({"module": module, "review_count": len(rows),
                           "evidence_path_count": len(evidence), "coverage_complete": True,
                           "opinions": dict(Counter(r["review_result"] for r in rows)),
                           "documentation_checked_count": len(value["documentation_checked"])})

    combined = []
    for original_row in original:
        rid = original_row["requirement_id"]
        needed = owners(original_row["owner"])
        opinions = {module: next(r for r in reviews[module]["requirements"] if r["requirement_id"] == rid)
                    for module in sorted(needed)}
        combined.append({
            "requirement_id": rid, "requirement": original_row["requirement"],
            "original_status": original_row["status"], "retained_status": original_row["status"],
            "required_reviewers": ";".join(sorted(needed)), "review_count": len(opinions),
            "explanation_revision_requested": any(v["review_result"] == "需修订" for v in opinions.values()),
            "classification_difference": any(v["suggested_status"] != original_row["status"] for v in opinions.values()),
            "opinions": json.dumps({m: v["review_result"] for m, v in opinions.items()}, ensure_ascii=False),
            "review_files": ";".join("MAIN_REVIEW.json" if m == "main" else f"owners/{m}_review.json"
                                       for m in sorted(needed)),
        })
    with (OUT / "GOAL_REVIEW_CONSOLIDATED.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(combined[0]))
        writer.writeheader()
        writer.writerows(combined)
    corrections = json.loads((OUT / "REQUIREMENT_TEXT_CORRECTIONS.json").read_text())["updates"]
    amended = []
    for row, agreement in zip(original, combined):
        changes = corrections.get(row["requirement_id"], {})
        if "status" in changes or not set(changes).issubset(row):
            raise ValueError("Only evidence text fields may be corrected")
        amended.append({**row, **changes, "owner_review_reference": agreement["review_files"]})
    with (OUT / "GOAL_REQUIREMENT_EVIDENCE_REVIEWED.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(amended[0]))
        writer.writeheader()
        writer.writerows(amended)
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requirement_count": len(combined), "owner_results": validation,
        "review_total": sum(r["review_count"] for r in validation),
        "unique_revision_ids": sorted({r["requirement_id"] for r in revisions}),
        "revision_opinions": revisions,
        "retained_status_counts": dict(Counter(r["retained_status"] for r in combined)),
        "classification_differences": [r["requirement_id"] for r in combined if r["classification_difference"]],
        "evidence_text_amended_ids": sorted(corrections),
        "meaning": "Owner read-only evidence review; no new experiment, capability certification or GAP closure.",
    }
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({k: summary[k] for k in (
        "requirement_count", "review_total", "unique_revision_ids", "retained_status_counts",
        "classification_differences", "owner_results")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
