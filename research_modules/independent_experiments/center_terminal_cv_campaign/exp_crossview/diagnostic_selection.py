#!/usr/bin/env python3
"""Diagnostic GNN parameter selection on the three saved AirSim replays.

This is intentionally test-set tuning. Truth labels are loaded only after each
anonymous association result has been produced, then used for offline ranking.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from ..common.io import write_json
from ..gnn_benchmark import (
    DEFAULT_OUTPUT_ROOT,
    HELD_OUT_AIRSIM_SEED,
    SAVED_CAMPAIGNS,
    SavedCampaign,
    build_replay_manifest,
)
from .association import PairCandidateCache, associate_crossview_tracks
from .camera_pairs import build_camera_pair_plan
from .config import CrossViewConfig
from .evaluation import score_with_offline_truth
from .gnn import load_model_bundle
from .replay_io import (
    load_replay_manifest,
    load_saved_replay_online,
    load_saved_replay_truth,
    sha256_file,
)
from .reporting import write_experiment_outputs


SCHEMA_VERSION = "terminal-crossview-testset-diagnostic-selection-v1"
DEFAULT_MODEL_DIR = (
    DEFAULT_OUTPUT_ROOT
    / "gnn_offline_benchmark_20260816"
    / "models"
    / "crossview"
)


@dataclass(frozen=True, order=True)
class ParameterSet:
    probability_threshold: float
    gnn_weight: float
    unmatched_cost: float

    @property
    def parameter_id(self) -> str:
        return (
            f"p{self.probability_threshold:.2f}_"
            f"w{self.gnn_weight:.2f}_u{self.unmatched_cost:.2f}"
        ).replace(".", "p")

    def to_dict(self) -> dict[str, float]:
        return {
            "gnn_probability_threshold": self.probability_threshold,
            "gnn_probability_weight": self.gnn_weight,
            "unmatched_cost": self.unmatched_cost,
        }


class CachedGNNCandidateScorer:
    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self._values: dict[tuple[object, ...], Mapping[tuple[str, str], float]] = {}
        self.hit_count = 0
        self.miss_count = 0

    @staticmethod
    def _history_signature(histories: Mapping[str, Sequence[Any]]) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                local_id,
                len(history),
                float(history[0].measurement_timestamp),
                float(history[-1].measurement_timestamp),
            )
            for local_id, history in sorted(histories.items())
        )

    def score(
        self,
        histories_a: Mapping[str, Sequence[Any]],
        histories_b: Mapping[str, Sequence[Any]],
        candidates: Sequence[Any],
        calibration_a: Any,
        calibration_b: Any,
    ) -> Mapping[tuple[str, str], float]:
        key = (
            calibration_a.camera_id,
            calibration_b.camera_id,
            self._history_signature(histories_a),
            self._history_signature(histories_b),
            tuple((item.track_a_id, item.track_b_id, item.reference_timestamp) for item in candidates),
        )
        cached = self._values.get(key)
        if cached is not None:
            self.hit_count += 1
            return cached
        self.miss_count += 1
        value = self.delegate.score(
            histories_a,
            histories_b,
            candidates,
            calibration_a,
            calibration_b,
        )
        self._values[key] = dict(value)
        return value


def _parameter_grid(
    thresholds: Sequence[float],
    weights: Sequence[float],
    unmatched_costs: Sequence[float],
) -> tuple[ParameterSet, ...]:
    values = tuple(
        ParameterSet(float(threshold), float(weight), float(unmatched))
        for threshold in thresholds
        for weight in weights
        for unmatched in unmatched_costs
    )
    for value in values:
        CrossViewConfig(**value.to_dict())
    return values


def _metrics_record(
    scenario_id: str,
    parameters: ParameterSet | None,
    backend: str,
    result: Any,
    elapsed_s: float,
) -> dict[str, Any]:
    metrics = result.metrics.to_dict()
    return {
        "scenario_id": scenario_id,
        "backend": backend,
        "parameter_id": parameters.parameter_id if parameters is not None else "geometry",
        "parameters": parameters.to_dict() if parameters is not None else {},
        "elapsed_s": elapsed_s,
        "candidate_edge_count": metrics["candidate_edge_count"],
        "retained_camera_pair_count": result.audit.camera_pair_retained_count,
        **metrics,
    }


def _aggregate_parameter(
    parameters: ParameterSet,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    false_relations = sum(int(item["false_positive_relations"] or 0) for item in records)
    mixed_targets = sum(int(item["mixed_identity_target_count"] or 0) for item in records)
    opportunity_targets = sum(int(item["opportunity_target_count"] or 0) for item in records)
    independent_targets = sum(int(item["independently_correct_target_count"] or 0) for item in records)
    unregistered_targets = sum(
        int(item["unregistered_opportunity_target_count"] or 0) for item in records
    )
    weighted_purity = sum(
        float(item["target_equal_mean_purity"] or 0.0)
        * int(item["opportunity_target_count"] or 0)
        for item in records
    ) / max(opportunity_targets, 1)
    weighted_completeness = sum(
        float(item["target_equal_mean_completeness"] or 0.0)
        * int(item["opportunity_target_count"] or 0)
        for item in records
    ) / max(opportunity_targets, 1)
    harmonic = (
        2.0 * weighted_purity * weighted_completeness
        / (weighted_purity + weighted_completeness)
        if weighted_purity + weighted_completeness > 0.0
        else 0.0
    )
    precisions = [float(item["association_precision"] or 0.0) for item in records]
    return {
        "parameter_id": parameters.parameter_id,
        "parameters": parameters.to_dict(),
        "mixed_identity_target_count": mixed_targets,
        "false_positive_relations": false_relations,
        "minimum_relation_precision": min(precisions),
        "all_scenarios_relation_precision_at_least_0_80": all(
            value >= 0.80 for value in precisions
        ),
        "target_equal_mean_purity": weighted_purity,
        "target_equal_mean_completeness": weighted_completeness,
        "target_equal_purity_completeness_hmean": harmonic,
        "independently_correct_target_count": independent_targets,
        "independently_correct_target_rate": independent_targets / max(opportunity_targets, 1),
        "unregistered_opportunity_target_count": unregistered_targets,
        "opportunity_target_count": opportunity_targets,
        "total_elapsed_s": sum(float(item["elapsed_s"]) for item in records),
    }


def _selection_key(record: Mapping[str, Any], *, has_qualified: bool) -> tuple[Any, ...]:
    if has_qualified:
        return (
            int(record["mixed_identity_target_count"]),
            int(record["false_positive_relations"]),
            -float(record["target_equal_purity_completeness_hmean"]),
            -float(record["independently_correct_target_rate"]),
            int(record["unregistered_opportunity_target_count"]),
            float(record["total_elapsed_s"]),
            str(record["parameter_id"]),
        )
    return (
        -float(record["minimum_relation_precision"]),
        int(record["mixed_identity_target_count"]),
        int(record["false_positive_relations"]),
        -float(record["target_equal_purity_completeness_hmean"]),
        -float(record["independently_correct_target_rate"]),
        int(record["unregistered_opportunity_target_count"]),
        float(record["total_elapsed_s"]),
        str(record["parameter_id"]),
    )


def _write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for record in records for key in record if key != "parameters"})
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key) for key in fieldnames})


def _source_hashes(manifests: Sequence[Path], model_dir: Path) -> dict[str, str]:
    paths = [
        *manifests,
        model_dir / "manifest.json",
        model_dir / "weights.pt",
        model_dir / "normalizer.json",
        Path(__file__),
        Path(__file__).with_name("association.py"),
        Path(__file__).with_name("evaluation.py"),
    ]
    return {str(path.resolve()): sha256_file(path) for path in paths}


def run_selection(
    output_dir: Path,
    *,
    source_root: Path = DEFAULT_OUTPUT_ROOT,
    model_dir: Path = DEFAULT_MODEL_DIR,
    campaigns: Sequence[SavedCampaign] = SAVED_CAMPAIGNS,
    thresholds: Sequence[float] = (0.0, 0.45, 0.65, 0.80),
    weights: Sequence[float] = (0.25, 0.45, 0.65),
    unmatched_costs: Sequence[float] = (0.85, 1.05, 1.25),
    device: str = "cuda",
) -> Path:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir = output_dir / "manifests"
    manifests = tuple(
        build_replay_manifest(
            campaign,
            source_root=source_root,
            manifest_dir=manifests_dir,
        )
        for campaign in campaigns
    )
    parameters = _parameter_grid(thresholds, weights, unmatched_costs)
    scorer = CachedGNNCandidateScorer(
        load_model_bundle(
            model_dir,
            device=device,
            evaluation_seeds=(HELD_OUT_AIRSIM_SEED,),
        )
    )
    geometry_records: list[dict[str, Any]] = []
    candidate_records: list[dict[str, Any]] = []
    results_by_parameter: dict[str, dict[str, Any]] = {
        value.parameter_id: {} for value in parameters
    }
    replay_context: dict[str, tuple[Any, ...]] = {}

    for manifest_path in manifests:
        manifest = load_replay_manifest(manifest_path)
        online = load_saved_replay_online(manifest)
        pair_plan = build_camera_pair_plan(
            online.calibrations,
            policy="sector_fov",
            capture_plan=online.capture_plan,
        )
        truth = load_saved_replay_truth(manifest)
        candidate_cache = PairCandidateCache()
        replay_context[manifest.scenario_id] = (
            online,
            pair_plan,
            truth,
            candidate_cache,
        )

        started = time.perf_counter()
        geometry_online = associate_crossview_tracks(
            online.records,
            online.calibrations,
            config=CrossViewConfig(),
            backend="geometry",
            camera_pair_plan=pair_plan,
            output_mode="audit",
            candidate_sample_limit=200,
            candidate_cache=candidate_cache,
        )
        geometry_elapsed = time.perf_counter() - started
        geometry = score_with_offline_truth(geometry_online, truth)
        geometry_record = _metrics_record(
            manifest.scenario_id, None, "geometry", geometry, geometry_elapsed
        )
        geometry_records.append(geometry_record)
        write_experiment_outputs(
            output_dir / "selected" / manifest.scenario_id / "geometry",
            geometry,
            online.records,
            truth=truth,
            output_mode="audit",
        )

        for parameter in parameters:
            config = replace(
                CrossViewConfig(),
                **parameter.to_dict(),
            )
            started = time.perf_counter()
            online_result = associate_crossview_tracks(
                online.records,
                online.calibrations,
                config=config,
                backend="gnn",
                scorer=scorer,
                camera_pair_plan=pair_plan,
                output_mode="audit",
                candidate_sample_limit=200,
                candidate_cache=candidate_cache,
            )
            elapsed = time.perf_counter() - started
            # Truth is deliberately introduced only after online association.
            scored = score_with_offline_truth(online_result, truth)
            record = _metrics_record(
                manifest.scenario_id,
                parameter,
                "gnn",
                scored,
                elapsed,
            )
            candidate_records.append(record)
            results_by_parameter[parameter.parameter_id][manifest.scenario_id] = scored

    aggregate_records = []
    for parameter in parameters:
        rows = [
            record
            for record in candidate_records
            if record["parameter_id"] == parameter.parameter_id
        ]
        aggregate_records.append(_aggregate_parameter(parameter, rows))
    qualified = [
        record
        for record in aggregate_records
        if record["all_scenarios_relation_precision_at_least_0_80"]
    ]
    selection_pool = qualified if qualified else aggregate_records
    selected = min(
        selection_pool,
        key=lambda item: _selection_key(item, has_qualified=bool(qualified)),
    )
    selected_id = str(selected["parameter_id"])
    selected_parameters = next(
        value for value in parameters if value.parameter_id == selected_id
    )
    selected_scenario_records = [
        record for record in candidate_records if record["parameter_id"] == selected_id
    ]
    selected_cold_records: list[dict[str, Any]] = []
    for manifest_path in manifests:
        manifest = load_replay_manifest(manifest_path)
        online = load_saved_replay_online(manifest)
        pair_plan = build_camera_pair_plan(
            online.calibrations,
            policy="sector_fov",
            capture_plan=online.capture_plan,
        )
        started = time.perf_counter()
        cold_online_result = associate_crossview_tracks(
            online.records,
            online.calibrations,
            config=replace(CrossViewConfig(), **selected_parameters.to_dict()),
            backend="gnn",
            scorer=scorer.delegate,
            camera_pair_plan=pair_plan,
            output_mode="audit",
            candidate_sample_limit=200,
        )
        cold_elapsed = time.perf_counter() - started
        truth = load_saved_replay_truth(manifest)
        result = score_with_offline_truth(cold_online_result, truth)
        expected = results_by_parameter[selected_id][manifest.scenario_id]
        if result.metrics.to_dict() != expected.metrics.to_dict():
            raise RuntimeError("cold selected run does not reproduce cached selection metrics")
        selected_cold_records.append(
            _metrics_record(
                manifest.scenario_id,
                selected_parameters,
                "gnn",
                result,
                cold_elapsed,
            )
        )
        write_experiment_outputs(
            output_dir / "selected" / manifest.scenario_id / "gnn",
            result,
            online.records,
            truth=truth,
            output_mode="audit",
        )

    _write_csv(output_dir / "candidate_scenario_metrics.csv", candidate_records)
    _write_csv(output_dir / "candidate_aggregate_metrics.csv", aggregate_records)
    _write_csv(output_dir / "geometry_scenario_metrics.csv", geometry_records)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "diagnostic_testset_tuning": True,
        "independent_holdout_validation": False,
        "truth_usage": "offline_scoring_and_parameter_ranking_only",
        "online_truth_leakage_count": 0,
        "camera_pair_policy": "sector_fov",
        "campaign_seed": HELD_OUT_AIRSIM_SEED,
        "device": device,
        "grid": {
            "probability_thresholds": list(thresholds),
            "gnn_weights": list(weights),
            "unmatched_costs": list(unmatched_costs),
            "candidate_count": len(parameters),
        },
        "selection_rule": (
            "minimize mixed targets then false relations; among candidates with "
            "relation precision >=0.80 in every scenario maximize target-equal "
            "purity/completeness harmonic mean, then independent-target rate, "
            "minimize unfinished targets, then elapsed time"
        ),
        "selected_parameters": selected_parameters.to_dict(),
        "selected_parameter_id": selected_id,
        "selected_aggregate_metrics": selected,
        "selected_scenario_metrics": selected_scenario_records,
        "selected_cold_scenario_metrics": selected_cold_records,
        "geometry_scenario_metrics": geometry_records,
        "cache_audit": {
            "gnn_score_hits": scorer.hit_count,
            "gnn_score_misses": scorer.miss_count,
            "geometry_cache_by_scenario": {
                scenario_id: {
                    "hits": context[3].hit_count,
                    "misses": context[3].miss_count,
                }
                for scenario_id, context in replay_context.items()
            },
        },
        "input_sha256": _source_hashes(manifests, model_dir),
    }
    summary_path = write_json(output_dir / "selection_summary.json", summary)
    (output_dir / "REPRODUCE.md").write_text(
        "# Reproduction\n\n"
        "This run deliberately tunes on the three report replays and is not an independent holdout.\n\n"
        "```bash\n"
        "python3 -m research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.diagnostic_selection "
        f"--output-dir {output_dir}\n"
        "```\n",
        encoding="utf-8",
    )
    return summary_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--thresholds", type=float, nargs="+", default=(0.0, 0.45, 0.65, 0.80))
    parser.add_argument("--weights", type=float, nargs="+", default=(0.25, 0.45, 0.65))
    parser.add_argument("--unmatched-costs", type=float, nargs="+", default=(0.85, 1.05, 1.25))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run_selection(
        args.output_dir,
        source_root=args.source_root,
        model_dir=args.model_dir,
        thresholds=args.thresholds,
        weights=args.weights,
        unmatched_costs=args.unmatched_costs,
        device=args.device,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
