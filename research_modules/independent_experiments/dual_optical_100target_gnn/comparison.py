"""Seed-grouped statistics and a directory-independent comparison contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from .dataset import canonical_json_sha256
from .loader import sha256_file


COMPARISON_SCHEMA_VERSION = "dual-optical-association-comparison-v1"
COMPARISON_RESULT_SCHEMA_VERSION = "dual-optical-association-comparison-result-v1"
DEFAULT_BOOTSTRAP_REPEATS = 5000
DEFAULT_BOOTSTRAP_SEED = 20260820


def per_seed_summaries(
    rows: Iterable[Mapping[str, Any]],
    mode: str,
    corruption_levels: Iterable[str],
) -> list[dict[str, Any]]:
    selected = [dict(row) for row in rows if str(row["mode"]) == mode]
    levels = tuple(str(level) for level in corruption_levels)
    seeds = sorted({int(row["seed"]) for row in selected})
    summaries: list[dict[str, Any]] = []
    for seed in seeds:
        seed_rows = [row for row in selected if int(row["seed"]) == seed]
        actual_levels = [str(row["corruption_level"]) for row in seed_rows]
        if len(actual_levels) != len(levels) or set(actual_levels) != set(levels):
            raise ValueError(
                f"seed {seed} does not contain one complete corruption group for {mode}"
            )
        summaries.append(
            {
                "seed": seed,
                "macro_precision": float(
                    np.mean([float(row["precision"]) for row in seed_rows])
                ),
                "macro_recall": float(
                    np.mean([float(row["recall"]) for row in seed_rows])
                ),
                "macro_f1": float(np.mean([float(row["f1"]) for row in seed_rows])),
                "false_association_count": int(
                    sum(int(row["false_association_count"]) for row in seed_rows)
                ),
                "duplicate_identity_match_count": int(
                    sum(int(row["duplicate_identity_match_count"]) for row in seed_rows)
                ),
            }
        )
    if not summaries:
        raise ValueError(f"no rows available for mode {mode}")
    return summaries


def _interval(values: np.ndarray, samples: np.ndarray) -> dict[str, float]:
    return {
        "estimate": float(np.mean(values)),
        "lower_95": float(np.percentile(samples, 2.5)),
        "upper_95": float(np.percentile(samples, 97.5)),
    }


def grouped_bootstrap(
    rows: Iterable[Mapping[str, Any]],
    modes: Iterable[str],
    corruption_levels: Iterable[str],
    *,
    repeats: int = DEFAULT_BOOTSTRAP_REPEATS,
    random_seed: int = DEFAULT_BOOTSTRAP_SEED,
    reference_mode: str = "geometry",
) -> dict[str, Any]:
    if repeats < 100:
        raise ValueError("grouped bootstrap requires at least 100 repeats")
    rows = [dict(row) for row in rows]
    summaries = {
        mode: per_seed_summaries(rows, mode, corruption_levels) for mode in modes
    }
    seed_contract = [item["seed"] for item in summaries[reference_mode]]
    for mode, values in summaries.items():
        if [item["seed"] for item in values] != seed_contract:
            raise ValueError(f"seed groups differ between {reference_mode} and {mode}")
    rng = np.random.default_rng(random_seed)
    count = len(seed_contract)
    indices = rng.integers(0, count, size=(repeats, count))
    metric_names = (
        "macro_precision",
        "macro_recall",
        "macro_f1",
        "false_association_count",
        "duplicate_identity_match_count",
    )
    by_mode: dict[str, Any] = {}
    arrays: dict[str, dict[str, np.ndarray]] = {}
    for mode, mode_rows in summaries.items():
        arrays[mode] = {
            metric: np.asarray([float(row[metric]) for row in mode_rows], dtype=float)
            for metric in metric_names
        }
        by_mode[mode] = {
            metric: _interval(values, np.mean(values[indices], axis=1))
            for metric, values in arrays[mode].items()
        }
    paired: dict[str, Any] = {}
    reference = arrays[reference_mode]
    for mode in modes:
        if mode == reference_mode:
            continue
        paired[mode] = {}
        for metric in metric_names:
            delta = arrays[mode][metric] - reference[metric]
            paired[mode][metric] = _interval(delta, np.mean(delta[indices], axis=1))
    return {
        "resampling_unit": "complete_seed_with_all_corruption_levels",
        "seed_count": count,
        "seed_values": seed_contract,
        "repeats": repeats,
        "random_seed": random_seed,
        "confidence_level": 0.95,
        "count_metrics_are_reported_as_mean_per_seed": True,
        "by_mode": by_mode,
        "paired_delta_vs_reference": {
            "reference_mode": reference_mode,
            "routes": paired,
        },
    }


def build_comparison_export(
    metrics: Mapping[str, Any],
    *,
    method_family: str,
    method_id: str,
    selected_route: str,
) -> dict[str, Any]:
    seed_rows = [
        dict(row)
        for row in metrics["per_seed_summary"]
        if str(row["mode"]) == selected_route
    ]
    aggregate = dict(metrics["assignment"][selected_route])
    payload = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "method_family": method_family,
        "method_id": method_id,
        "selected_route": selected_route,
        "dataset_fingerprint_sha256": metrics["reproducibility"][
            "dataset_fingerprint_sha256"
        ],
        "candidate_fingerprint_sha256": metrics["reproducibility"][
            "candidate_fingerprint_sha256"
        ],
        "test_seeds": list(metrics["test_seeds"]),
        "corruption_levels": list(metrics["corruption_levels"]),
        "aggregate": {
            "macro_precision": aggregate["macro_precision"],
            "macro_recall": aggregate["macro_recall"],
            "macro_f1": aggregate["macro_f1"],
            "false_association_count": aggregate["false_association_count"],
            "duplicate_identity_match_count": aggregate[
                "duplicate_identity_match_count"
            ],
        },
        "per_seed": seed_rows,
        "latency": dict(metrics["latency"]),
    }
    payload["payload_fingerprint_sha256"] = canonical_json_sha256(payload)
    return payload


def validate_comparison_export(payload: Mapping[str, Any]) -> dict[str, Any]:
    values = dict(payload)
    fingerprint = values.pop("payload_fingerprint_sha256", None)
    if values.get("schema_version") != COMPARISON_SCHEMA_VERSION:
        raise ValueError("unsupported comparison export schema")
    if fingerprint != canonical_json_sha256(values):
        raise ValueError("comparison export fingerprint mismatch")
    seeds = [int(seed) for seed in values.get("test_seeds", [])]
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("comparison export test seeds are empty or duplicated")
    per_seed = [dict(row) for row in values.get("per_seed", [])]
    if sorted(int(row["seed"]) for row in per_seed) != sorted(seeds):
        raise ValueError("comparison export per-seed rows do not match test seeds")
    required = {
        "macro_f1",
        "false_association_count",
        "duplicate_identity_match_count",
    }
    if not required <= set(values.get("aggregate", {})):
        raise ValueError("comparison export aggregate metrics are incomplete")
    values["payload_fingerprint_sha256"] = fingerprint
    return values


def _paired_export_interval(
    gnn: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    repeats: int,
    random_seed: int,
) -> dict[str, Any]:
    gnn_rows = {int(row["seed"]): row for row in gnn["per_seed"]}
    baseline_rows = {int(row["seed"]): row for row in baseline["per_seed"]}
    seeds = sorted(gnn_rows)
    if seeds != sorted(baseline_rows):
        raise ValueError("comparison exports do not have the same per-seed rows")
    rng = np.random.default_rng(random_seed)
    indices = rng.integers(0, len(seeds), size=(repeats, len(seeds)))
    result: dict[str, Any] = {}
    for metric in (
        "macro_f1",
        "false_association_count",
        "duplicate_identity_match_count",
    ):
        delta = np.asarray(
            [float(gnn_rows[seed][metric]) - float(baseline_rows[seed][metric]) for seed in seeds],
            dtype=float,
        )
        result[metric] = _interval(delta, np.mean(delta[indices], axis=1))
    return result


def compare_exports(
    gnn_payload: Mapping[str, Any],
    baseline_payload: Mapping[str, Any],
    *,
    repeats: int = DEFAULT_BOOTSTRAP_REPEATS,
    random_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    if repeats < 100:
        raise ValueError("paired bootstrap requires at least 100 repeats")
    gnn = validate_comparison_export(gnn_payload)
    baseline = validate_comparison_export(baseline_payload)
    if gnn["method_family"] != "gnn":
        raise ValueError("the first comparison export must be the GNN route")
    if baseline["method_family"] == "gnn":
        raise ValueError("the external baseline must not identify itself as GNN")
    for key in (
        "dataset_fingerprint_sha256",
        "candidate_fingerprint_sha256",
        "test_seeds",
        "corruption_levels",
    ):
        if gnn[key] != baseline[key]:
            raise ValueError(f"comparison contract mismatch: {key}")
    paired = _paired_export_interval(
        gnn,
        baseline,
        repeats=repeats,
        random_seed=random_seed,
    )
    aggregate_delta = float(
        gnn["aggregate"]["macro_f1"] - baseline["aggregate"]["macro_f1"]
    )
    false_pass = int(gnn["aggregate"]["false_association_count"]) <= int(
        baseline["aggregate"]["false_association_count"]
    )
    duplicate_pass = int(
        gnn["aggregate"]["duplicate_identity_match_count"]
    ) <= int(baseline["aggregate"]["duplicate_identity_match_count"])
    gpu = gnn.get("latency", {}).get("gpu", {})
    gpu_pass = bool(gpu.get("available")) and float(
        gpu.get("p95_ms", float("inf"))
    ) <= 100.0
    ci_pass = float(paired["macro_f1"]["lower_95"]) > 0.0
    f1_pass = aggregate_delta >= 0.02
    promotion_pass = f1_pass and ci_pass and false_pass and duplicate_pass and gpu_pass
    result = {
        "schema_version": COMPARISON_RESULT_SCHEMA_VERSION,
        "status": "promotion_passed" if promotion_pass else "promotion_not_passed",
        "gnn_method_id": gnn["method_id"],
        "external_baseline_method_id": baseline["method_id"],
        "dataset_fingerprint_sha256": gnn["dataset_fingerprint_sha256"],
        "candidate_fingerprint_sha256": gnn["candidate_fingerprint_sha256"],
        "test_seeds": gnn["test_seeds"],
        "paired_bootstrap": {
            "resampling_unit": "complete_seed_with_all_corruption_levels",
            "repeats": repeats,
            "random_seed": random_seed,
            "confidence_level": 0.95,
            "delta_is_gnn_minus_external_baseline": True,
            "metrics": paired,
        },
        "criteria": {
            "macro_f1_delta": aggregate_delta,
            "macro_f1_improvement_at_least_0_02": f1_pass,
            "paired_f1_ci_lower_above_zero": ci_pass,
            "false_association_non_increase": false_pass,
            "duplicate_identity_non_increase": duplicate_pass,
            "gpu_p95_at_most_100_ms": gpu_pass,
        },
        "recommend_continue_toward_mainline": promotion_pass,
        "recommendation_scope": "next_isolated_engineering_validation_only",
    }
    result["result_fingerprint_sha256"] = canonical_json_sha256(result)
    return result


def compare_files(
    gnn_export_path: str | Path,
    external_baseline_path: str | Path,
    output_path: str | Path,
    *,
    repeats: int = DEFAULT_BOOTSTRAP_REPEATS,
    random_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> Path:
    gnn_export_path = Path(gnn_export_path).resolve()
    external_baseline_path = Path(external_baseline_path).resolve()
    result = compare_exports(
        json.loads(gnn_export_path.read_text(encoding="utf-8")),
        json.loads(external_baseline_path.read_text(encoding="utf-8")),
        repeats=repeats,
        random_seed=random_seed,
    )
    result["input_hashes"] = {
        "gnn_export_sha256": sha256_file(gnn_export_path),
        "external_baseline_export_sha256": sha256_file(external_baseline_path),
    }
    result.pop("result_fingerprint_sha256", None)
    result["result_fingerprint_sha256"] = canonical_json_sha256(result)
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
