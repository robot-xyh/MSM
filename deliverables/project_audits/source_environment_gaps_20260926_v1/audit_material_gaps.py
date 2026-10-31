"""Inspect bounded historical metadata; do not import or execute research code."""

from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
from pathlib import Path
import subprocess
import sys


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PRIOR = ROOT / "deliverables/project_audits/goal_evidence_followup_20260926_v1"
sys.path.insert(0, str(ROOT / "deliverables/project_audits/tools"))
from audit_record_validation import read_strict_json
from audit_report_evidence import write_csv


METADATA_KEYS = {"git_revision", "git_commit", "source_git_commit", "python_version",
                 "dependencies", "environment", "runtime", "source", "source_snapshot",
                 "source_sha256", "code_sha256", "source_hashes", "source_files"}


def metadata_fields(value, prefix=""):
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if key in METADATA_KEYS:
                found.append(path)
            found.extend(metadata_fields(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(metadata_fields(child, f"{prefix}[{index}]"))
    return found


def dependency_evidence(edges, versions):
    grouped = {}
    for row in edges:
        if row["kind"] != "external_or_unresolved":
            continue
        module = row["import"].split(".")[0]
        grouped.setdefault((row["batch"], module), []).append(
            {"source": row["source"], "line": int(row["line"]), "import": row["import"]})
    result = []
    for (batch, module), witnesses in sorted(grouped.items()):
        distribution = "scikit-learn" if module == "sklearn" else module
        version = versions.get(batch, {}).get(distribution, versions.get(batch, {}).get(module))
        result.append({"batch": batch, "module": module, "distribution": distribution,
                       "recorded_version": version,
                       "status": "version_declared" if version is not None else "version_not_found_in_checked_metadata",
                       "actual_runtime_import_proven": False, "static_witnesses": witnesses})
    return result


def main():
    if (OUT / "AUDIT_RESULTS.json").exists():
        raise SystemExit("Audit exists; preserve it rather than overwriting.")
    fingerprints = {}

    def watch(path):
        data = path.read_bytes()
        fingerprints[str(path.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()
        return data

    def json_file(path):
        watch(path)
        return read_strict_json(path)

    def csv_file(path):
        watch(path)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    started = datetime.now(timezone.utc).isoformat()
    exp = ROOT / "research_modules/independent_experiments"
    batches = {
        "dual": exp / "dual_optical_online_benchmark/outputs/report_replay_20260819_v2",
        "center": exp / "center_terminal_cv_campaign/outputs/center_handover_sensor_error_20260820",
        "search": exp / "center_terminal_cv_campaign/outputs/offline_search_100pct_cues_20260819",
    }
    manifests = {key: json_file(path / "reproduction_manifest.json") for key, path in batches.items()}
    environment_path = batches["center"] / "environment.json"
    environment = json_file(environment_path)
    expected_environment_hash = manifests["center"]["runtime"]["dependency_lock"]["sha256"]
    actual_environment_hash = fingerprints[str(environment_path.relative_to(ROOT))]
    if actual_environment_hash != expected_environment_hash:
        raise ValueError("Center environment no longer matches its historical manifest")
    versions = {"dual": manifests["dual"]["runtime"].get("dependencies", {}),
                "center": environment.get("dependencies", {}), "search": {}}
    edges = csv_file(PRIOR / "STATIC_IMPORT_EDGES.csv")
    source_rows = csv_file(PRIOR / "STATIC_SOURCE_REGISTER.csv")
    dependencies = dependency_evidence(edges, versions)

    gaps, source_checks = [], []
    for row in source_rows:
        data = watch(ROOT / row["path"])
        current = hashlib.sha256(data).hexdigest()
        source_checks.append({"batch": row["batch"], "path": row["path"],
                              "matches_previous_audit": current == row["current_sha256"]})
        if not row["historical_expected_sha256"]:
            gaps.append({"batch": row["batch"], "path": row["path"],
                         "previous_evidence_status": row["status"],
                         "current_sha256": current, "bytes": len(data),
                         "actual_runtime_import_proven": False,
                         "needed_evidence": "Run-bound source snapshot or historical file hash; current/base equality is insufficient."})

    search_checks = []
    for path in sorted((batches["search"] / "runs").glob("*/evidence_manifest.json")):
        value = json_file(path)
        search_checks.append({"path": str(path.relative_to(ROOT)),
                              "config_present": isinstance(value.get("config"), dict),
                              "provenance_fields_found": metadata_fields(value),
                              "rule": "Only named metadata keys inspected; not a claim about all possible external evidence."})

    patterns = ["*requirements*.txt", "*environment*.json", "*environment*.yml", "*environment*.yaml",
                "*freeze*.txt", "*.lock", "conda-lock.*", "source_files.json", "tracked_worktree.patch",
                "reproduction_manifest.json"]
    metadata_files = []
    for batch, directory in batches.items():
        for path in sorted(directory.rglob("*")):
            if path.is_file() and any(fnmatch.fnmatch(path.name, pattern) for pattern in patterns):
                watch(path)
                metadata_files.append({"batch": batch, "path": str(path.relative_to(ROOT)),
                                       "bytes": path.stat().st_size, "sha256": fingerprints[str(path.relative_to(ROOT))]})

    environments = {
        "dual": {"source": str((batches["dual"] / "reproduction_manifest.json").relative_to(ROOT)),
                 "python_version": manifests["dual"]["runtime"].get("python_version"),
                 "dependencies": versions["dual"], "complete_environment_lock_established": False,
                 "record_kind": "three_direct_package_versions_in_manifest"},
        "center": {"source": str(environment_path.relative_to(ROOT)), "sha256_matches_manifest": True,
                   "python_version": environment.get("python_version"), "dependencies": versions["center"],
                   "recorded_gnn_device": environment.get("gnn_device"), "recorded_gpu": environment.get("gpu"),
                   "recorded_airsim_used": environment.get("airsim_used"),
                   "complete_environment_lock_established": False,
                   "record_kind": "hashed_four_package_version_summary_not_installer_lock"},
        "search": {"source": str((batches["search"] / "reproduction_manifest.json").relative_to(ROOT)),
                   "python_version": None, "dependencies": {}, "complete_environment_lock_established": False,
                   "record_kind": "no_environment_version_fields_in_checked_manifests"},
    }
    findings = {"started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "scope": "Three named output roots, prior static registers, and 45 search metadata manifests; no broad disk/Git search.",
                "source_register_rows": len(source_rows), "historically_hashed_source_rows": sum(bool(r["historical_expected_sha256"]) for r in source_rows),
                "unbound_static_candidate_rows": len(gaps), "source_gaps_by_batch": dict(Counter(r["batch"] for r in gaps)),
                "source_checks": source_checks, "dependency_records": dependencies,
                "search_manifest_count": len(search_checks),
                "search_manifests_with_provenance_fields": sum(bool(r["provenance_fields_found"]) for r in search_checks),
                "metadata_candidate_patterns": patterns, "metadata_candidate_files": metadata_files,
                "environments": environments,
                "passed": all(r["matches_previous_audit"] for r in source_checks) and len(search_checks) == 45,
                "pass_meaning": "Bounded metadata inspection completed; not reproducibility or environment completeness.",
                "package_installation_performed": False, "research_code_imported": False,
                "current_environment_used_as_historical_evidence": False,
                "original_goal_status_changed": False, "archive_450_recovered": False}
    preservation = [{"path": path, "before_sha256": digest, "after_sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
                    for path, digest in sorted(fingerprints.items())]
    for row in preservation:
        row["unchanged"] = row["before_sha256"] == row["after_sha256"]
    findings["passed"] = findings["passed"] and all(row["unchanged"] for row in preservation)
    for name, data in [("AUDIT_RESULTS.json", findings), ("SEARCH_METADATA_CHECKS.json", search_checks),
                       ("INPUT_FINGERPRINTS.json", preservation)]:
        with (OUT / name).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    write_csv(OUT / "SOURCE_GAPS.csv", gaps, list(gaps[0]))
    write_csv(OUT / "DEPENDENCY_EVIDENCE.csv", dependencies, list(dependencies[0]))
    write_csv(OUT / "CHECKED_METADATA_FILES.csv", metadata_files, list(metadata_files[0]))
    print(json.dumps({"passed": findings["passed"], "unbound_static_candidates": len(gaps),
                      "dependency_records": len(dependencies), "search_manifests": len(search_checks),
                      "source_files_unchanged": all(r["unchanged"] for r in preservation)}, ensure_ascii=False))
    raise SystemExit(0 if findings["passed"] else 1)


if __name__ == "__main__":
    main()
