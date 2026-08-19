"""Same-input candidate ablation and fail-closed scale-promotion gate."""

from __future__ import annotations

import csv
from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from dual_optical_100target_gnn.dataset import (
    candidate_graph_fingerprint as route_graph_fingerprint,
    canonical_json_sha256,
)
from dual_optical_online_benchmark.contracts import (
    BenchmarkProtocol,
    RevolutionSnapshot,
    benchmark_protocol_from_mapping,
)
from dual_optical_online_benchmark.dataset import (
    load_dataset_manifest,
    sha256_file,
)
from dual_optical_online_benchmark.scoring import score_publication

from .benchmark_adapter import (
    SharedSnapshotLightweightAdapter,
    _build_candidate_snapshot,
    read_shared_snapshot,
    shared_snapshot_fingerprint,
)
from .online import OnlineLightweightAdapter
from .online_benchmark import _verify_freeze
from .pipeline import MINIMUM_CONDITIONAL_PRECISION


ABLATION_SCHEMA_VERSION = "dual-optical-lightweight-candidate-ablation-v1"
NEGATIVE_RECALL_DELTA = -0.02
PROMOTION_CORRUPTION_LEVELS = ("medium", "heavy")
ABLATION_MODES = ("shared_allowlist", "legacy_all_pairs")


def _snapshot_for_mode(
    snapshot: RevolutionSnapshot, mode: str
) -> RevolutionSnapshot:
    """Change only candidate construction for the offline-only baseline."""

    if mode == "shared_allowlist":
        return snapshot
    if mode == "legacy_all_pairs":
        return replace(
            snapshot,
            geometry_candidate_pairs=(),
            candidate_graph_fingerprint="",
            candidate_graph_summary={},
        )
    raise ValueError(f"unsupported candidate ablation mode: {mode}")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("candidate ablation produced no rows")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _dominant_truth(counts: Mapping[str, Any]) -> str | None:
    positive = sorted(
        (
            (int(count), str(identity))
            for identity, count in counts.items()
            if int(count) > 0
        ),
        reverse=True,
    )
    if not positive or positive[0][1].startswith("FA-"):
        return None
    if len(positive) > 1 and positive[0][0] == positive[1][0]:
        return None
    return positive[0][1]


def _candidate_truth_metrics(
    snapshot: RevolutionSnapshot,
    graph: Any,
    labels: Mapping[str, Any],
) -> dict[str, int | float]:
    track_counts = labels["track_truth_counts"]
    identities = {
        track_id: _dominant_truth(track_counts.get(track_id, {}))
        for camera_id in snapshot.camera_ids
        for track_id in (track.track_id for track in snapshot.tracks[camera_id])
    }
    camera_a, camera_b = snapshot.camera_ids
    common_identities = {
        identities.get(track.track_id)
        for track in snapshot.tracks[camera_a]
        if identities.get(track.track_id) is not None
    } & {
        identities.get(track.track_id)
        for track in snapshot.tracks[camera_b]
        if identities.get(track.track_id) is not None
    }
    correct_pairs: list[tuple[str, str, str]] = []
    for index_a, index_b in graph.edge_index.T:
        track_a = graph.track_ids_a[int(index_a)]
        track_b = graph.track_ids_b[int(index_b)]
        identity_a = identities.get(track_a)
        identity_b = identities.get(track_b)
        if identity_a is not None and identity_a == identity_b:
            correct_pairs.append((track_a, track_b, identity_a))
    retained_identities = {identity for _, _, identity in correct_pairs}
    opportunity_count = len(common_identities)
    return {
        "candidate_correct_pair_count": len(correct_pairs),
        "candidate_correct_identity_count": len(retained_identities),
        "candidate_true_identity_opportunity_count": opportunity_count,
        "candidate_true_edge_retention_rate": (
            len(retained_identities) / opportunity_count
            if opportunity_count
            else 0.0
        ),
    }


def _aggregate(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(rows)
    if not values:
        raise ValueError("cannot aggregate an empty candidate ablation group")
    match_count = sum(int(row["match_count"]) for row in values)
    correct_count = sum(int(row["correct_match_count"]) for row in values)
    latency_fields = (
        "candidate_generation_ms",
        "model_scoring_ms",
        "hungarian_assignment_ms",
        "confirmation_and_publication_ms",
        "end_to_end_ms",
    )
    return {
        "sample_count": len(values),
        "independent_seed_count": len({int(row["seed"]) for row in values}),
        "macro_precision": float(np.mean([float(row["precision"]) for row in values])),
        "macro_recall": float(np.mean([float(row["recall"]) for row in values])),
        "macro_f1": float(np.mean([float(row["f1"]) for row in values])),
        "conditional_precision": (
            float(correct_count / match_count) if match_count else 0.0
        ),
        "match_count": match_count,
        "correct_match_count": correct_count,
        "false_association_count": sum(
            int(row["false_association_count"]) for row in values
        ),
        "mean_full_pair_count": float(
            np.mean([int(row["full_pair_count"]) for row in values])
        ),
        "mean_evaluated_pair_count": float(
            np.mean([int(row["evaluated_pair_count"]) for row in values])
        ),
        "mean_candidate_edge_count": float(
            np.mean([int(row["candidate_edge_count"]) for row in values])
        ),
        "mean_probability_accepted_edge_count": float(
            np.mean(
                [int(row["probability_accepted_edge_count"]) for row in values]
            )
        ),
        "mean_hungarian_selected_count": float(
            np.mean([int(row["hungarian_selected_count"]) for row in values])
        ),
        "mean_candidate_true_edge_retention_rate": float(
            np.mean(
                [float(row["candidate_true_edge_retention_rate"]) for row in values]
            )
        ),
        "deadline_met_rate": float(
            np.mean([bool(row["deadline_met"]) for row in values])
        ),
        "stage_latency_p95_ms": {
            name: float(np.percentile([float(row[name]) for row in values], 95))
            for name in latency_fields
        },
    }


def _ablation_delta(
    shared: Mapping[str, Any], baseline: Mapping[str, Any]
) -> dict[str, Any]:
    baseline_evaluated = float(baseline["mean_evaluated_pair_count"])
    baseline_candidates = float(baseline["mean_candidate_edge_count"])
    latency_names = tuple(shared["stage_latency_p95_ms"])
    return {
        "macro_precision_delta": float(shared["macro_precision"])
        - float(baseline["macro_precision"]),
        "macro_recall_delta": float(shared["macro_recall"])
        - float(baseline["macro_recall"]),
        "macro_f1_delta": float(shared["macro_f1"])
        - float(baseline["macro_f1"]),
        "conditional_precision_delta": float(shared["conditional_precision"])
        - float(baseline["conditional_precision"]),
        "false_association_count_delta": int(shared["false_association_count"])
        - int(baseline["false_association_count"]),
        "evaluated_pair_reduction_ratio": (
            1.0
            - float(shared["mean_evaluated_pair_count"]) / baseline_evaluated
            if baseline_evaluated > 0.0
            else 0.0
        ),
        "candidate_edge_reduction_ratio": (
            1.0
            - float(shared["mean_candidate_edge_count"]) / baseline_candidates
            if baseline_candidates > 0.0
            else 0.0
        ),
        "deadline_met_rate_delta": float(shared["deadline_met_rate"])
        - float(baseline["deadline_met_rate"]),
        "stage_latency_p95_ms_delta": {
            name: float(shared["stage_latency_p95_ms"][name])
            - float(baseline["stage_latency_p95_ms"][name])
            for name in latency_names
        },
    }


def _seed_metric(rows: Sequence[Mapping[str, Any]], metric: str) -> dict[int, float]:
    grouped: dict[int, list[float]] = {}
    for row in rows:
        grouped.setdefault(int(row["seed"]), []).append(float(row[metric]))
    return {seed: float(np.mean(values)) for seed, values in grouped.items()}


def _paired_delta_ci(
    shared: Sequence[Mapping[str, Any]],
    baseline: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    random_seed: int,
    resamples: int,
) -> dict[str, float | int]:
    if resamples <= 0:
        raise ValueError("bootstrap resamples must be positive")
    shared_samples = {
        (
            int(row["seed"]),
            int(row["revolution_index"]),
            str(row["source_input_fingerprint"]),
        )
        for row in shared
    }
    baseline_samples = {
        (
            int(row["seed"]),
            int(row["revolution_index"]),
            str(row["source_input_fingerprint"]),
        )
        for row in baseline
    }
    if (
        len(shared_samples) != len(shared)
        or len(baseline_samples) != len(baseline)
        or shared_samples != baseline_samples
    ):
        raise ValueError(
            "paired ablation requires identical unique source snapshots"
        )
    shared_by_seed = _seed_metric(shared, metric)
    baseline_by_seed = _seed_metric(baseline, metric)
    if set(shared_by_seed) != set(baseline_by_seed) or not shared_by_seed:
        raise ValueError("paired ablation requires identical non-empty seed sets")
    seeds = sorted(shared_by_seed)
    deltas = np.asarray(
        [shared_by_seed[seed] - baseline_by_seed[seed] for seed in seeds],
        dtype=float,
    )
    rng = np.random.default_rng(random_seed)
    indices = rng.integers(0, len(deltas), size=(resamples, len(deltas)))
    estimates = np.mean(deltas[indices], axis=1)
    return {
        "independent_seed_count": len(seeds),
        "point": float(np.mean(deltas)),
        "lower": float(np.percentile(estimates, 2.5)),
        "upper": float(np.percentile(estimates, 97.5)),
    }


def promotion_decision(
    rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_seed: int = 20260813,
    bootstrap_resamples: int = 2000,
) -> dict[str, Any]:
    """Stop scale promotion when the allowlist harms medium or heavy noise."""

    by_level: dict[str, Any] = {}
    stop_reasons: list[str] = []
    for level_index, level in enumerate(PROMOTION_CORRUPTION_LEVELS):
        shared = [
            row
            for row in rows
            if row["mode"] == "shared_allowlist"
            and row["corruption_level"] == level
        ]
        baseline = [
            row
            for row in rows
            if row["mode"] == "legacy_all_pairs"
            and row["corruption_level"] == level
        ]
        if not shared or not baseline:
            by_level[level] = {"available": False}
            stop_reasons.append(f"{level}_evidence_missing")
            continue
        shared_summary = _aggregate(shared)
        baseline_summary = _aggregate(baseline)
        recall_ci = _paired_delta_ci(
            shared,
            baseline,
            metric="recall",
            random_seed=bootstrap_seed + level_index,
            resamples=bootstrap_resamples,
        )
        clear_negative = bool(
            float(recall_ci["point"]) <= NEGATIVE_RECALL_DELTA
            or float(recall_ci["upper"]) < 0.0
        )
        precision_floor_failed = bool(
            float(shared_summary["conditional_precision"])
            < MINIMUM_CONDITIONAL_PRECISION
        )
        if clear_negative:
            stop_reasons.append(f"{level}_shared_allowlist_negative_recall")
        if precision_floor_failed:
            stop_reasons.append(f"{level}_conditional_precision_below_0.70")
        by_level[level] = {
            "available": True,
            "shared_allowlist": shared_summary,
            "legacy_all_pairs": baseline_summary,
            "shared_minus_baseline_recall_95ci": recall_ci,
            "negative_recall_detected": clear_negative,
            "precision_floor_failed": precision_floor_failed,
        }
    return {
        "negative_recall_delta_threshold": NEGATIVE_RECALL_DELTA,
        "minimum_conditional_precision": MINIMUM_CONDITIONAL_PRECISION,
        "levels": by_level,
        "negative_benefit_stop": any(
            reason.endswith("negative_recall") for reason in stop_reasons
        ),
        "promotion_allowed": not stop_reasons,
        "stop_before_next_scale": bool(stop_reasons),
        "stop_reasons": stop_reasons,
    }


def _validate_test_manifest(
    manifest: Mapping[str, Any], protocol: BenchmarkProtocol
) -> list[dict[str, Any]]:
    if manifest.get("phase") != "test" or manifest.get("test_access_allowed") is not True:
        raise ValueError("candidate ablation requires a reserved-test manifest")
    if manifest.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("test manifest protocol fingerprint mismatch")
    entries = [dict(item) for item in manifest["entries"]]
    expected = {
        (int(seed), level, revolution)
        for seed in protocol.test_seeds
        for level in protocol.corruption_levels
        for revolution in range(1, protocol.revolution_count + 1)
    }
    actual = {
        (
            int(entry["seed"]),
            str(entry["corruption_level"]),
            int(entry["revolution_index"]),
        )
        for entry in entries
    }
    if actual != expected or len(actual) != len(entries):
        raise ValueError("reserved-test manifest does not cover the frozen protocol")
    return sorted(
        entries,
        key=lambda entry: (
            int(entry["seed"]),
            str(entry["corruption_level"]),
            int(entry["revolution_index"]),
        ),
    )


def run_candidate_ablation(
    test_manifest: str | Path,
    freeze_manifest: str | Path,
    output_dir: str | Path,
    *,
    bootstrap_seed: int = 20260813,
    bootstrap_resamples: int = 2000,
) -> Path:
    """Compare shared-allowlist and legacy all-pair candidates on each snapshot."""

    manifest_path = Path(test_manifest).resolve()
    manifest = load_dataset_manifest(
        manifest_path,
        validate_offline_labels=False,
    )
    protocol = benchmark_protocol_from_mapping(manifest["protocol"])
    entries = _validate_test_manifest(manifest, protocol)
    freeze, routes = _verify_freeze(Path(freeze_manifest))
    if freeze["protocol_fingerprint"] != protocol.fingerprint:
        raise ValueError("test and lightweight freeze protocols differ")
    selected = tuple(
        route for route in routes if route.route_id == freeze["selected_route_id"]
    )
    if len(selected) != 1:
        raise ValueError("freeze must identify exactly one selected lightweight route")

    adapters = {
        mode: SharedSnapshotLightweightAdapter(
            OnlineLightweightAdapter(
                selected,
                freeze["geometry_gate"],
                allowed_seeds=protocol.test_seeds,
                confirmation_window_revolutions=3,
                confirmation_hits=2,
                latency_budget_ms=protocol.online_deadline_ms,
            ),
            selected_route_id=selected[0].route_id,
        )
        for mode in ABLATION_MODES
    }
    rows: list[dict[str, Any]] = []
    root = manifest_path.parent
    for entry in entries:
        snapshot_path = root / entry["snapshot_path"]
        if sha256_file(snapshot_path) != entry["snapshot_sha256"]:
            raise ValueError("candidate ablation snapshot hash mismatch")
        source_snapshot = read_shared_snapshot(snapshot_path)
        source_fingerprint = shared_snapshot_fingerprint(source_snapshot)
        if source_fingerprint != entry["input_fingerprint"]:
            raise ValueError("candidate ablation source fingerprint mismatch")
        if (
            source_snapshot.target_count is not None
            and source_snapshot.target_count != protocol.target_count
        ):
            raise ValueError(
                "candidate ablation snapshot target_count differs from protocol"
            )

        publications: dict[str, Any] = {}
        for mode in ABLATION_MODES:
            route_snapshot = _snapshot_for_mode(source_snapshot, mode)
            publication = adapters[mode].process(route_snapshot)
            publications[mode] = replace(
                publication,
                input_fingerprint=source_fingerprint,
            )

        label_path = root / entry["label_path"]
        if sha256_file(label_path) != entry["label_sha256"]:
            raise ValueError("candidate ablation offline-label hash mismatch")
        labels = json.loads(label_path.read_text(encoding="utf-8"))
        if labels.get("offline_truth_only") is not True:
            raise ValueError("candidate ablation label is not marked offline-only")

        for mode in ABLATION_MODES:
            adapter = adapters[mode]
            publication = publications[mode]
            # The public adapter keeps the exact graph diagnostics but not the
            # graph object. Rebuild from the same immutable snapshot only for
            # offline candidate-retention scoring.
            route_snapshot = _snapshot_for_mode(source_snapshot, mode)
            candidate_snapshot, _ = _build_candidate_snapshot(
                route_snapshot, freeze["geometry_gate"]
            )
            candidate_graph = candidate_snapshot.graph
            scored = score_publication(publication, labels)
            truth_metrics = _candidate_truth_metrics(
                source_snapshot, candidate_graph, labels
            )
            diagnostics = adapter.last_graph_diagnostics
            stage = publication.stage_latencies_ms
            rows.append(
                {
                    "mode": mode,
                    "seed": source_snapshot.seed,
                    "corruption_level": source_snapshot.corruption_level,
                    "revolution_index": source_snapshot.revolution_index,
                    "source_input_fingerprint": source_fingerprint,
                    "candidate_graph_fingerprint": (
                        source_snapshot.candidate_graph_fingerprint
                        if mode == "shared_allowlist"
                        else route_graph_fingerprint(candidate_graph)
                    ),
                    "candidate_source": diagnostics["geometry_candidate_source"],
                    "full_pair_count": int(diagnostics["full_pair_count"]),
                    "evaluated_pair_count": int(diagnostics["evaluated_pair_count"]),
                    "candidate_edge_count": int(diagnostics["candidate_edge_count"]),
                    "probability_accepted_edge_count": int(
                        publication.rejection_reasons.get(
                            "probability_accepted_edge_count", 0
                        )
                    ),
                    "hungarian_selected_count": int(
                        publication.rejection_reasons.get(
                            "hungarian_selected_count", 0
                        )
                    ),
                    **truth_metrics,
                    "match_count": int(scored["match_count"]),
                    "confirmed_match_count": sum(
                        match.decision_state == "confirmed"
                        for match in publication.matches
                    ),
                    "correct_match_count": int(scored["correct_match_count"]),
                    "false_association_count": int(scored["false_association_count"]),
                    "precision": float(scored["precision"]),
                    "recall": float(scored["recall"]),
                    "f1": float(scored["f1"]),
                    "deadline_met": bool(scored["deadline_met"]),
                    "candidate_generation_ms": float(stage["candidate_generation"]),
                    "model_scoring_ms": float(stage["model_scoring"]),
                    "hungarian_assignment_ms": float(stage["hungarian_assignment"]),
                    "confirmation_and_publication_ms": float(
                        stage["confirmation_and_publication"]
                    ),
                    "end_to_end_ms": float(publication.end_to_end_ms),
                }
            )

    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows_path = output / "candidate_ablation_rows.csv"
    _write_csv(rows_path, rows)
    aggregate = {}
    for level in protocol.corruption_levels:
        summaries = {
            mode: _aggregate(
                row
                for row in rows
                if row["corruption_level"] == level and row["mode"] == mode
            )
            for mode in ABLATION_MODES
        }
        aggregate[level] = {
            **summaries,
            "shared_minus_legacy": _ablation_delta(
                summaries["shared_allowlist"],
                summaries["legacy_all_pairs"],
            ),
        }
    promotion = promotion_decision(
        rows,
        bootstrap_seed=bootstrap_seed,
        bootstrap_resamples=bootstrap_resamples,
    )
    result = {
        "schema_version": ABLATION_SCHEMA_VERSION,
        "target_count": protocol.target_count,
        "protocol_fingerprint": protocol.fingerprint,
        "freeze_fingerprint": freeze["freeze_fingerprint_sha256"],
        "selected_route_id": freeze["selected_route_id"],
        "same_input_contract": {
            "source_snapshot_identical_between_modes": True,
            "model_threshold_and_confirmation_identical": True,
            "only_candidate_construction_changes": True,
            "shared_allowlist_never_expands_online": True,
            "legacy_all_pairs_is_offline_ablation_only": True,
            "offline_truth_loaded_after_both_publications": True,
        },
        "reported_metric_groups": {
            "candidate_funnel": [
                "full_pair_count",
                "evaluated_pair_count",
                "candidate_edge_count",
                "candidate_true_edge_retention_rate",
                "probability_accepted_edge_count",
                "hungarian_selected_count",
            ],
            "association_quality": [
                "precision",
                "recall",
                "f1",
                "conditional_precision",
                "false_association_count",
            ],
            "latency": [
                "candidate_generation_ms",
                "model_scoring_ms",
                "hungarian_assignment_ms",
                "confirmation_and_publication_ms",
                "end_to_end_ms",
            ],
        },
        "aggregate_by_corruption": aggregate,
        "promotion_gate": promotion,
        "row_count": len(rows),
        "rows_sha256": sha256_file(rows_path),
        "artifacts": {"rows_csv": rows_path.name},
    }
    result["result_fingerprint_sha256"] = canonical_json_sha256(result)
    result_path = output / "candidate_ablation_summary.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result_path


__all__ = [
    "NEGATIVE_RECALL_DELTA",
    "promotion_decision",
    "run_candidate_ablation",
]
