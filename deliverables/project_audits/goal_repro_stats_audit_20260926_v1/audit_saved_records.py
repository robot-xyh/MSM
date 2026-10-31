"""Inspect provenance and saved numeric records; never execute experiment code."""

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import statistics
import subprocess


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
EXP = ROOT / "research_modules/independent_experiments"
CAM = EXP / "center_terminal_cv_campaign/outputs"
DUAL = EXP / "dual_optical_online_benchmark/outputs/report_replay_20260819_v2"
SEARCH = CAM / "offline_search_100pct_cues_20260819"
CENTER = CAM / "center_handover_sensor_error_20260820"
OLD = CAM / "gnn_offline_benchmark_20260816"
CROSS = CAM / "terminal_gnn_diagnostic_selection_20260819_v2"
HASHES = []
SOURCE_VERSIONS = []
CHECKS = []


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def save_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def save_csv(name, rows):
    with (OUT / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def git(*args, raw=False):
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, timeout=30)
    if raw:
        return p
    return {"args": list(args), "returncode": p.returncode, "stdout": p.stdout.decode(errors="replace").strip(), "stderr": p.stderr.decode(errors="replace").strip()}


def verify(path, expected="", kind="metadata", batch=""):
    path = Path(path)
    actual = sha(path) if path.is_file() else ""
    expected = expected.removeprefix("sha256:")
    row = {"batch": batch, "kind": kind, "path": str(path), "exists": path.is_file(), "bytes": path.stat().st_size if path.is_file() else None, "expected_sha256": expected, "actual_sha256": actual, "status": "missing" if not actual else "match" if actual == expected else "mismatch" if expected else "fingerprinted_only"}
    HASHES.append(row)
    return row


def resolve_input(path, base):
    p = Path(path)
    if p.is_absolute():
        return p
    return (ROOT if p.parts[0] == "research_modules" else base) / p


def compare_source(path, commit, expected, batch):
    path = Path(path)
    rel = str(path.relative_to(ROOT))
    blob = git("show", commit + ":" + rel, raw=True) if commit else None
    historical = hashlib.sha256(blob.stdout).hexdigest() if blob and blob.returncode == 0 else ""
    current = sha(path) if path.is_file() else ""
    SOURCE_VERSIONS.append({"batch": batch, "path": rel, "recorded_commit": commit, "manifest_sha256": expected, "current_sha256": current, "commit_blob_sha256": historical, "current_matches_record": current == expected if expected else None, "commit_matches_record": historical == expected if expected else None, "commit_blob_exists": bool(historical)})


def check(batch, row_key, field, actual, expected):
    if expected is None or actual in (None, ""):
        matches = expected is None and actual in (None, "")
    elif isinstance(expected, bool):
        matches = actual == expected or str(actual).lower() == str(expected).lower()
    else:
        matches = math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-10)
    CHECKS.append({"batch": batch, "row_key": str(row_key), "field": field, "saved_value": actual, "expected_from_saved_counts": expected, "match": matches})


def overview(rows, keys):
    grouped = defaultdict(list)
    for row in rows:
        grouped[tuple(row[k] for k in keys)].append(row)
    return {"rows": len(rows), "unique_seed_ids": sorted({r["seed"] for r in rows}), "group_count": len(grouped), "group_sizes": dict(Counter(str(len(v)) for v in grouped.values())), "duplicate_group_seed_rows": sum(len(v) - len({r["seed"] for r in v}) for v in grouped.values())}


def inspect_manifest(base, batch):
    p = base / "reproduction_manifest.json"
    manifest = read_json(p)
    verify(p, batch=batch)
    source = manifest.get("source", {})
    commit = source.get("git_commit", manifest.get("git_revision", ""))
    for item in manifest.get("inputs", []):
        path = resolve_input(item["path"], base)
        role = item["role"]
        if "source" in role and (role == "source_file" or role == "algorithm_source_snapshot") or role in {"model", "model_manifest"}:
            verify(path, item["sha256"], role, batch)
        if role == "source_file":
            compare_source(path, commit, item["sha256"], batch)
    if source.get("snapshot_root"):
        listing = base / source["snapshot_root"] / "source_files.json"
        verify(listing, batch=batch)
        for item in read_json(listing):
            compare_source(ROOT / item["repository_path"], commit, item["sha256"], batch)
        verify(base / source["snapshot_root"] / "tracked_worktree.patch", batch=batch)
    lock = manifest.get("runtime", {}).get("dependency_lock")
    if isinstance(lock, dict):
        verify(base / lock["path"], lock["sha256"], "environment_record", batch)
    return {"manifest_path": str(p), "source": source, "git_revision": commit, "git_object": git("rev-parse", "--verify", commit + "^{commit}") if commit else None, "working_tree_dirty": source.get("worktree_dirty", manifest.get("working_tree_dirty")), "runtime": manifest.get("runtime"), "scenario": manifest.get("scenario"), "metrics_contract": manifest.get("metrics_contract"), "reproduction": manifest.get("reproduction"), "command": manifest.get("command"), "input_evidence": manifest.get("input_evidence")}


def audit_numbers():
    dual = read_csv(DUAL / "combined_final_case_metrics.csv")
    dual_groups = defaultdict(list)
    for r in dual:
        key = tuple(r[k] for k in ("profile", "target_count", "condition", "route_name"))
        dual_groups[key].append(r)
        row_key = key + (r["seed"],)
        output = int(r["output_match_count"])
        check("dual", row_key, "association_precision", r["association_precision"], int(r["correct_match_count"]) / output if output else None)
        check("dual", row_key, "false_match_count", r["false_match_count"], output - int(r["correct_match_count"]))
        check("dual", row_key, "fixed_target_coverage", r["fixed_target_coverage"], int(r["correct_unique_target_count"]) / int(r["target_count"]))
        check("dual", row_key, "single_station_coverage", r["single_station_coverage"], int(r["single_station_correct_identity_count"]) / int(r["single_station_identity_opportunity_count"]))
        check("dual", row_key, "single_station_identity_opportunity_count", r["single_station_identity_opportunity_count"], 2 * int(r["target_count"]))
        ontime = str(r["deadline_met"]).lower() == "true"
        check("dual", row_key, "timed_out", r["timed_out"], not ontime)
        check("dual", row_key, "deadline_met", r["deadline_met"], float(r["latency_ms"]) <= float(r["deadline_ms"]))
        check("dual", row_key, "on_time_fixed_target_coverage", r["on_time_fixed_target_coverage"], float(r["fixed_target_coverage"]) if ontime else 0.0)
    for group in read_json(DUAL / "combined_summary.json")["summary"]:
        key = tuple(str(group[k]) for k in ("profile", "target_count", "condition", "route_name"))
        rows = dual_groups[key]
        output = sum(int(r["output_match_count"]) for r in rows)
        check("dual_summary", key, "offline_completed_precision", group["offline_completed_precision"], sum(int(r["correct_match_count"]) for r in rows) / output if output else None)
        check("dual_summary", key, "offline_completed_coverage", group["offline_completed_coverage"], statistics.mean(float(r["fixed_target_coverage"]) for r in rows))
        check("dual_summary", key, "on_time_coverage", group["on_time_coverage"], statistics.mean(float(r["on_time_fixed_target_coverage"]) for r in rows))
        check("dual_summary", key, "sample_count", group["sample_count"], len(rows))
    search = read_csv(SEARCH / "matrix.csv")
    for r in search:
        for metric, count in (("target_discovery_rate", "detected_target_count"), ("continuous_confirmation_rate", "continuously_confirmed_target_count")):
            check("search", r["run_id"], metric, r[metric], int(r[count]) / int(r["target_count"]))
    search_groups = defaultdict(list)
    for r in search:
        search_groups[(r["scenario_id"], float(r["position_sigma_m"]))].append(r)
    for g in read_json(SEARCH / "matrix_summary.json")["aggregates"]:
        key = g["scenario_id"], float(g["position_sigma_m"])
        rows = search_groups[key]
        for field in ("target_discovery_rate", "continuous_confirmation_rate"):
            check("search_summary", key, field + "_mean", g[field + "_mean"], statistics.mean(float(r[field]) for r in rows))
        check("search_summary", key, "seed_count", g["seed_count"], len({r["seed"] for r in rows}))
    center = read_csv(CENTER / "per_run_metrics.csv")
    center_keys = ("target_count", "handover_mode", "attitude_mode", "navigation_mode", "detection_mode", "backend")
    center_groups = defaultdict(list)
    zero_output = []
    for r in center:
        center_groups[tuple(r[k] for k in center_keys)].append(r)
        total = int(r["confirmed_pair_count"])
        check("center", r["run_id"], "confirmed_pair_count", total, int(r["true_binding_count"]) + int(r["false_binding_count"]))
        if total:
            check("center", r["run_id"], "binding_precision", r["binding_precision"], int(r["true_binding_count"]) / total)
        else:
            zero_output.append({k: r[k] for k in ("run_id", "binding_precision", "binding_recall")})
        check("center", r["run_id"], "binding_recall", r["binding_recall"], int(r["true_binding_count"]) / int(r["target_count"]))
    for g in read_csv(CENTER / "aggregate_metrics.csv"):
        key = tuple(g[k] for k in center_keys)
        rows = center_groups[key]
        for field in ("binding_precision", "binding_recall"):
            numbers = [float(r[field]) for r in rows]
            check("center_summary", key, field + "_mean", g[field + "_mean"], statistics.mean(numbers))
            check("center_summary", key, field + "_std", g[field + "_std"], statistics.pstdev(numbers))
            check("center_summary", key, field + "_min", g[field + "_min"], min(numbers))
        check("center_summary", key, "seed_count", g["seed_count"], len({r["seed"] for r in rows}))
    result = {
        "dual": {**overview(dual, ("profile", "target_count", "condition", "route_name")), "final_rounds_by_profile": {p: sorted({r["round_index"] for r in dual if r["profile"] == p}) for p in sorted({r["profile"] for r in dual})}, "timed_out_rows": sum(r["timed_out"].lower() == "true" for r in dual), "zero_output_rows": sum(int(r["output_match_count"]) == 0 for r in dual), "zero_single_station_labels": sum(int(r["single_station_labeled_observation_count"]) == 0 for r in dual)},
        "search": {**overview(search, ("scenario_id", "position_sigma_m")), "unique_motion_sha256": sorted({r["trajectory_sha256"] for r in search}), "recorded_end_s": sorted({r["trajectory_recorded_end_s"] for r in search}), "extrapolated_s": sorted({r["trajectory_extrapolated_after_s"] for r in search})},
        "center": {**overview(center, center_keys), "zero_output_rows": zero_output, "warm_cache_by_backend": {b: dict(Counter(r["runtime_uses_warm_projection_cache"] for r in center if r["backend"] == b)) for b in {r["backend"] for r in center}}},
    }
    save_csv("NUMERIC_CONSISTENCY_CHECKS.csv", CHECKS)
    result["check_counts"] = {"total": len(CHECKS), "matched": sum(r["match"] for r in CHECKS), "mismatched": sum(not r["match"] for r in CHECKS)}
    return result


def main():
    if (OUT / "AUDIT_RESULTS.json").exists():
        raise SystemExit("Audit results already exist; choose a new batch.")
    started = datetime.now(timezone.utc).isoformat()
    provenance = {"dual": inspect_manifest(DUAL, "dual"), "search": inspect_manifest(SEARCH, "search"), "center": inspect_manifest(CENTER, "center")}
    prior = ROOT / "deliverables/project_audits/goal_resume_audit_20260926_v1"
    source_dirs = read_json(prior / "SOURCE_DIRECTORY_STATUS.json")
    for item in source_dirs:
        base = Path(item["source_root"])
        session = read_json(base / "generation_session.json")
        verify(base / "generation_session.json", batch=item["module"])
        for field in ("base_config", "schedule"):
            path = ROOT / session[field + "_path"]
            verify(path, session[field + "_sha256"], field, item["module"])
            compare_source(path, session["source_git_commit"], session[field + "_sha256"], item["module"])
        provenance[item["module"]] = {"source_root": str(base), "session": session, "source_git_object": git("rev-parse", "--verify", session["source_git_commit"] + "^{commit}"), "previous_integrity_audit": str(prior / "SOURCE_PAYLOAD_HASH_CHECKS.csv"), "training_checkpoint_claimed": False}
    for batch, base in (("old_handover", OLD), ("crossview", CROSS)):
        manifests = []
        for path in sorted((base / "manifests").glob("*.json")):
            data = read_json(path)
            verify(path, batch=batch)
            resolved = []
            for role, rel in data["paths"].items():
                p = (path.parent / rel).resolve()
                resolved.append({"role": role, "path": str(p), "exists": p.is_file(), "expected_sha256": data["sha256"].get(role)})
            manifests.append({"manifest": str(path), "seed": data.get("campaign_seed"), "paths": resolved})
        provenance[batch] = {"root": str(base), "manifests": manifests, "readme_reproduction_exists": (base / "REPRODUCE.md").is_file()}
    outputs = [DUAL / "combined_final_case_metrics.csv", DUAL / "combined_summary.json", SEARCH / "matrix.csv", SEARCH / "matrix_summary.json", CENTER / "per_run_metrics.csv", CENTER / "aggregate_metrics.csv", OLD / "benchmark_summary.json", CROSS / "selection_summary.json", CROSS / "candidate_scenario_metrics.csv"]
    for path in outputs:
        verify(path, kind="saved_metrics")
    # SHA verification uses bytes only; no model or source module is imported.
    baseline = ROOT / "research_modules/airsim_runtime/baselines/d5_long_range_20target_20260810/baseline_manifest.json"
    verify(baseline, batch="airsim_longrange")
    provenance["airsim_longrange"] = {"manifest": str(baseline), "source_directory": read_json(baseline)["source_directory"], "integrity_record": str(prior / "SUPPLEMENTAL_CHECKS.json")}
    interfaces = []
    for name in ("center_handover_sensor_error_airsim_20260820_n20_retry01", "center_handover_sensor_error_airsim_20260820_n40", "center_handover_sensor_error_airsim_20260820_n60"):
        base = CAM / name
        summary = read_json(base / "summary.json")
        verify(base / "summary.json", batch="interface")
        verify(base / "settings.json", batch="interface")
        verify(base / "summary_metrics.csv", batch="interface")
        interfaces.append({"root": str(base), "seed": summary["seed"], "summary_keys": list(summary), "result_rows": len(read_csv(base / "summary_metrics.csv")), "top_level_files": sorted(p.name for p in base.iterdir() if p.is_file())})
    provenance["interface"] = interfaces
    stats = audit_numbers()
    save_csv("FILE_VERSION_CHECKS.csv", HASHES)
    save_csv("SOURCE_VERSION_REGISTER.csv", SOURCE_VERSIONS)
    save_json("PROVENANCE_EVIDENCE.json", provenance)
    save_json("AUDIT_RESULTS.json", {"started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(), "head": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"), "statistics": stats, "hash_statuses": dict(Counter(x["status"] for x in HASHES)), "source_version_checks": len(SOURCE_VERSIONS), "scope": "Saved metadata and numeric-result arithmetic only; raw truth not parsed; no replay or model execution", "source_modules_modified": False})
    print(json.dumps({"numeric_checks": stats["check_counts"], "zero_output_center_rows": len(stats["center"]["zero_output_rows"]), "hashes": dict(Counter(x["status"] for x in HASHES))}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
