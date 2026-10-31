"""Additional environment and metadata checks, without importing project code."""

import csv
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import subprocess
import sys
from collections import Counter


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
CAM = ROOT / "research_modules/independent_experiments/center_terminal_cv_campaign/outputs"


def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    packages = {}
    for name in ("numpy", "scipy", "torch", "matplotlib", "airsim"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    source = "research_modules/independent_experiments/center_terminal_cv_campaign/exp_search/run_offline_matrix.py"
    commit = "ad59ff3f48e180248f1168bf72a0e152bd80264a"
    old_source = subprocess.run(["git", "cat-file", "-e", commit + ":" + source], cwd=ROOT, capture_output=True, text=True)
    inventory = ROOT / "research_modules/d2_data_association/docs/formal_r0_identity_causal_pack_summary_20260731/artifact_inventory.json"
    data = json.loads(inventory.read_text())
    format_hashes = []
    for sort in (False, True):
        for indent in (None, 2):
            for newline in (False, True):
                encoded = (json.dumps(data, ensure_ascii=False, sort_keys=sort, indent=indent) + ("\n" if newline else "")).encode()
                format_hashes.append({"sort_keys": sort, "indent": indent, "newline": newline, "sha256": hashlib.sha256(encoded).hexdigest()})
    compact = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    center_path = CAM / "center_handover_sensor_error_20260820"
    manifest = json.loads((center_path / "reproduction_manifest.json").read_text())
    center = load_csv(center_path / "per_run_metrics.csv")
    dual_root = ROOT / "research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v2"
    dual = load_csv(dual_root / "combined_final_case_metrics.csv")
    round_checks = []
    final_by_key = {}
    sequence_keys = ("profile", "target_count", "seed", "condition", "route_name")
    for relative in ("oracle_360/round_metrics.csv", "continuous_360/round_metrics.csv", "s180_derived/round_metrics.csv"):
        rows = load_csv(dual_root / relative)
        keys = Counter(tuple(r[k] for k in (*sequence_keys, "round_index")) for r in rows)
        round_checks.append({"path": str(dual_root / relative), "rows": len(rows), "duplicate_full_keys": sum(v - 1 for v in keys.values())})
        for row in rows:
            key = tuple(row[k] for k in sequence_keys)
            previous = final_by_key.get(key)
            if previous is None or int(row["round_index"]) > int(previous["round_index"]):
                final_by_key[key] = row
    final_matches = sum(final_by_key.get(tuple(r[k] for k in sequence_keys)) == r for r in dual)
    expected = manifest["reproduction"]["expected_metrics_sha256"]
    actual = hashlib.sha256((center_path / "per_run_metrics.csv").read_bytes()).hexdigest()
    strict_json = []
    paths = [center_path / "aggregate_metrics.json", center_path / "metrics_contract.json", center_path / "reproduction_manifest.json", CAM / "offline_search_100pct_cues_20260819/matrix_summary.json", CAM / "gnn_offline_benchmark_20260816/benchmark_summary.json", CAM / "terminal_gnn_diagnostic_selection_20260819_v2/selection_summary.json", ROOT / "research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v2/combined_summary.json"]
    def reject(value):
        raise ValueError("Non-finite JSON token: " + value)
    for path in paths:
        try:
            json.loads(path.read_text(), parse_constant=reject)
            result = "passed"
        except ValueError as error:
            result = str(error)
        strict_json.append({"path": str(path), "result": result})
    result = {
        "current_environment": {"python": platform.python_version(), "executable": sys.executable, "platform": platform.platform(), "packages": packages, "packages_imported_for_version_check": False},
        "search_recorded_commit_source": {"commit": commit, "path": source, "returncode": old_source.returncode, "stderr": old_source.stderr.strip()},
        "historical_d2_inventory_discrepancy": {"expected_cited": "c9bf5e479526cded07aa3d170540aa389b8083af3ec801496f41d620d4ffb68f", "format_variant_hashes": format_hashes, "compact_sorted_sha256": compact, "resolved": False},
        "center_expected_result_hash": {"path": str(center_path / "per_run_metrics.csv"), "expected": expected, "actual": actual, "match": expected == actual},
        "zero_center_output_by_mode": dict(Counter(r["handover_mode"] for r in center if int(r["confirmed_pair_count"]) == 0)),
        "center_scale_tags": [{"target_count": n, "tags": sorted({r["gnn_scale_status"] for r in center if r["backend"] == "gnn" and r["target_count"] == n})} for n in ("20", "40", "60")],
        "dual_timeout_by_route": dict(Counter(r["route_name"] for r in dual if r["timed_out"].lower() == "true")),
        "dual_round_records": round_checks,
        "dual_final_rows_equal_latest_saved_round": {"matched": final_matches, "checked": len(dual), "sequence_count": len(final_by_key)},
        "strict_json_checks": strict_json,
        "boundaries": "No model loading, no simulator, no raw labels interpreted, no original data changed"
    }
    (OUT / "SUPPLEMENTAL_CHECKS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"strict_json_passed": sum(r["result"] == "passed" for r in strict_json), "center_expected_hash_match": expected == actual, "search_entry_in_recorded_commit": old_source.returncode == 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
