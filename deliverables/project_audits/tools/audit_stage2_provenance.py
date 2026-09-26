"""Supplement stage-two metadata with file hashes, row counts and figure lineage."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from audit_workspace_metadata import digest


BASE = "research_modules/independent_experiments/"
DUAL = BASE + "dual_optical_online_benchmark/outputs/"
CENTER = BASE + "center_terminal_cv_campaign/outputs/"


def csv_metadata(path: Path, root: Path) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    fields = ("seed", "target_count", "resource_count", "profile", "route_name", "condition",
              "backend", "scenario_id", "evidence_status", "round_index")
    return {"path": path.relative_to(root).as_posix(), "sha256": digest(path),
            "rows": len(rows), "distinct_values": {
                name: sorted({row[name] for row in rows if row.get(name) not in (None, "")})
                for name in fields if rows and name in rows[0]}}


def hash_check(path: Path, expected: str, root: Path, origin: str) -> dict:
    actual = digest(path) if path.is_file() else None
    return {"path": str(path.relative_to(root)), "origin": origin, "expected": expected,
            "actual": actual, "status": "missing" if actual is None else
            "match" if actual == expected else "mismatch"}


def collect(root: Path) -> dict:
    csv_paths = [
        DUAL + "report_replay_20260819_v2/combined_final_case_metrics.csv",
        CENTER + "offline_search_100pct_cues_20260819/matrix.csv",
        CENTER + "terminal_gnn_diagnostic_selection_20260819_v2/candidate_aggregate_metrics.csv",
        CENTER + "terminal_gnn_diagnostic_selection_20260819_v2/candidate_scenario_metrics.csv",
        CENTER + "terminal_gnn_diagnostic_selection_20260819_v2/geometry_scenario_metrics.csv",
        CENTER + "center_handover_sensor_error_20260820/per_run_metrics.csv",
        CENTER + "center_handover_sensor_error_20260820/aggregate_metrics.csv",
    ]
    csv_paths += [CENTER + name + "/summary_metrics.csv" for name in (
        "center_handover_sensor_error_airsim_20260820_n20_retry01",
        "center_handover_sensor_error_airsim_20260820_n40",
        "center_handover_sensor_error_airsim_20260820_n60")]
    manifest_path = root / DUAL / "report_replay_20260819_v2/reproduction_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    freezes, model_checks = [], []
    for entry in manifest["inputs"]:
        if entry.get("role") not in {"continuous_360_gnn_freeze", "s180_gnn_freeze"}:
            continue
        path = root / entry["path"]
        data = json.loads(path.read_text())
        seeds = {name: data.get(name, []) for name in ("train_seeds", "validation_seeds", "reserved_test_seeds")}
        sets = [set(value) for value in seeds.values()]
        overlap = set().union(*(a & b for index, a in enumerate(sets) for b in sets[index + 1:]))
        freezes.append({"path": entry["path"], "sha256": digest(path), "role": entry["role"],
                        "target_count": data.get("target_count"), **seeds,
                        "listed_seed_overlap": sorted(overlap),
                        "freeze_allowed": data.get("freeze_allowed"),
                        "test_accessed_before_freeze": data.get("test_accessed_before_freeze"),
                        "limit": "Seed lists are manifest declarations, not a fresh audit of training execution."})
        for key in ("weights", "normalizer", "model_config", "training_history", "dataset_manifest",
                    "validation_selection", "initialization_selection", "edge_sampling_evidence", "validation_evidence"):
            if data.get(key) and data.get(key + "_sha256"):
                target = Path(data[key])
                if not target.is_absolute():
                    target = path.parent / target
                model_checks.append(hash_check(target.resolve(), data[key + "_sha256"], root, entry["path"] + "#" + key))
    model_root = root / CENTER / "gnn_offline_benchmark_20260816/models"
    cross = json.loads((model_root / "crossview/manifest.json").read_text())
    for name, sha in cross["sha256"].items():
        model_checks.append(hash_check(model_root / "crossview" / name, sha, root,
                                       CENTER + "gnn_offline_benchmark_20260816/models/crossview/manifest.json"))
    center = json.loads((model_root / "center_handover/center_handover_sparse_gnn.pt.manifest.json").read_text())
    model_checks.append(hash_check(model_root / "center_handover" / center["model_file"],
                                   center["model_sha256"], root,
                                   CENTER + "gnn_offline_benchmark_20260816/models/center_handover/center_handover_sparse_gnn.pt.manifest.json"))
    benchmark_path = root / CENTER / "gnn_offline_benchmark_20260816/benchmark_summary.json"
    benchmark = json.loads(benchmark_path.read_text())
    totals = []
    for backend in ("geometry", "gnn"):
        rows = [row for row in benchmark["results"] if row["task"] == "center_handover" and row["backend"] == backend]
        correct = sum(row["metrics"]["true_binding_count"] for row in rows)
        incorrect = sum(row["metrics"]["false_binding_count"] for row in rows)
        eligible = sum(row["metrics"]["correct_source_count"] for row in rows)
        totals.append({"backend": backend, "correct": correct, "incorrect": incorrect,
                       "correct_source_denominator": eligible,
                       "precision_display": f"{correct / (correct + incorrect):.4f}",
                       "coverage_display": f"{correct / eligible:.4f}",
                       "source": str(benchmark_path.relative_to(root)),
                       "operation": "Arithmetic on already-saved counts; not reassociation or rescoring."})
    asset_root = "deliverables/leadership_report/assets/center_terminal_split_reports/"
    figure_pairs = [(asset_root + target, CENTER + "offline_search_100pct_cues_20260819/figures/" + source)
                    for target, source in (
                        ("search100_01_flow.png", "01_search_flow.png"),
                        ("search100_02_cells_3d.png", "02_search_cells_3d.png"),
                        ("search100_03_results.png", "03_search_results.png"),
                        ("search100_04_coverage_budget.png", "04_search_coverage_budget.png"),
                        ("search100_05_timing.png", "05_search_timing.png"))]
    figure_pairs += [(asset_root + target, CENTER + "terminal_gnn_diagnostic_selection_20260819_v2/selected/n20_m30/gnn/figures/" + source)
                     for target, source in (("13_local_pixel_tracks.png", "02_local_pixel_tracks.png"),
                                             ("14_crossview_relation_graph.png", "03_crossview_relation_graph.png"))]
    figures = []
    for target, source in figure_pairs:
        actual, expected = digest(root / target), digest(root / source)
        figures.append({"report_asset": target, "source_asset": source, "report_sha256": actual,
                        "source_sha256": expected, "status": "match" if actual == expected else "mismatch"})
    return {
        "schema": "msm-stage-two-provenance-v1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "tool_sha256": digest(Path(__file__)), "csv_metadata": [csv_metadata(root / path, root) for path in csv_paths],
        "gnn_freeze_metadata": freezes, "model_and_training_file_checks": model_checks,
        "model_check_counts": dict(Counter(row["status"] for row in model_checks)),
        "benchmark_seed_roles": {"held_out_seed": benchmark["held_out_seed"],
                                 "training": {key: {name: value[name] for name in ("train_seeds", "validation_seeds")}
                                              for key, value in benchmark["training"].items()}},
        "handover_table_totals": totals, "figure_lineage": figures,
        "scope": "File bytes and saved aggregate arithmetic only; model files were not loaded or executed."}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if not output.is_relative_to(root / "deliverables/project_audits"):
        raise ValueError("Output must remain in the audit tree.")
    if output.exists():
        raise FileExistsError(output)
    result = collect(root)
    with output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"csv_files": len(result["csv_metadata"]), "model_checks": result["model_check_counts"],
                      "figure_checks": dict(Counter(row["status"] for row in result["figure_lineage"]))}))


if __name__ == "__main__":
    main()
