"""Offline evaluation for truth-isolated scalable 3D episode bundles.

This module consumes persisted main-owned artifacts only.  It never imports a
runtime controller, writes to the online bus, or treats evaluator truth as an
online input.  Missing evidence remains null with an explicit availability
reason.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .active_vision_offline import (
    ACTIVE_VISION_NUMERIC_METRIC_FIELDS,
    evaluate_active_vision_runtime_evidence,
)
from .d1_centroid_overlay_shadow import (
    D1_CENTROID_OVERLAY_SHADOW_NUMERIC_METRIC_FIELDS,
    evaluate_d1_centroid_overlay_shadow_evidence,
)
from .experiment_matrix_offline import (
    EXPERIMENT_MATRIX_SCHEMA_VERSION,
    EXPERIMENT_MATRIX_VARIANTS,
    aggregate_experiment_matrix,
    extract_experiment_matrix_evidence,
    finalize_experiment_matrix_evidence,
    render_experiment_matrix_markdown_lines,
)
from .observation_posterior_governance import (
    evaluate_posterior_governance,
    register_module_performance_evidence,
)
from .observation_truth_sidecar import (
    ObservationTruthDispositionAudit,
    ObservationTruthSidecarError,
    SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V2,
    audit_observation_truth_sidecar,
)
from .regional_planning_chain_audit import audit_regional_planning_chain
from .strict_offline_identity import (
    load_strict_offline_id_switch,
)


SCALABLE_3D_OFFLINE_EVALUATION_SCHEMA_VERSION = (
    "d6-scalable3d-offline-evaluation-v12"
)
SCALABLE_3D_OFFLINE_EVALUATION_DATE = "2026-07-31"
SCALABLE_3D_SCHEMA_REGISTRY_VERSION = "d6-scalable3d-schema-registry-v2"
SCALABLE_3D_STAGE_TIMING_SCHEMA_VERSION = "scalable3d-stage-timings-v2"
SCALABLE_3D_CURRENT_SCHEMA_REGISTRY = {
    "world_schema": "scalable3d-world-v1",
    "bus_schema": "scalable3d-episode-bus-v1",
    "scenario_schema": "scalable3d-scenario-v1",
    "online_observation_schema": "scalable3d-observation-v1",
    "offline_truth_schema": SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V2,
    "scenario_config_schema": "scalable3d-scenario-v1",
}
DEFAULT_SCALABLE_3D_BOOTSTRAP_RESAMPLES = 2_000
DEFAULT_SCALABLE_3D_BOOTSTRAP_RNG_SEED = 20260720
FIVE_METER_THRESHOLD_M = 5.0

_LEARNING_RUNTIME_SCHEMA = "scalable3d-learning-runtime-v1"
_D4_REGION_ADVICE_TOPIC = "modules.d4.region_resource_advice"
_D4_REGION_ADVICE_SCHEMA = "d4-region-resource-advisory-runtime-v1"
_D4_REGION_ADVISORY_SCHEMA = "d4-region-resource-advisory-v1"
_D4_REGION_RECOMMENDATION_SCHEMA = "d4-region-resource-recommendation-v1"
_D4_REGION_CONSUMPTION_TOPIC = "modules.d4.region_resource_consumption"
_D4_REGION_CONSUMPTION_SCHEMA = "d4-region-resource-consumption-v1"
_LEARNING_MODULE_VERSION_FIELDS = {
    "d3": "d3_policy_version",
    "d4": "d4_policy_version",
    "d5": "d5_model_version",
}
_ADVISOR_MODES = frozenset({"disabled", "shadow", "assist"})

_OPTIONAL_TRUTH_ARTIFACT = "offline_truth_labels.jsonl"
_EPISODE_DISCOVERY_REQUIRED_ARTIFACTS = (
    "manifest.json",
    "scenario_config.json",
    "summary.json",
)
_GROUP_FIELDS = (
    "scenario_name",
    "scenario_version",
    "target_count",
    "resource_count",
    "recon_count",
    "camera_count",
)
_STAGE_TIMING_BASE_FIELDS = (
    "stage",
    "call_count",
    "wall_time_s",
    "mean_wall_time_ms",
)
_STAGE_TIMING_QUANTILE_FIELDS = (
    "p50_wall_time_ms",
    "p95_wall_time_ms",
    "max_wall_time_ms",
)
_STAGE_TIMING_AVAILABILITY_FIELDS = (
    "distribution_available",
    "distribution_unavailable_reason",
)
_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_entity_id",
        "truth_entity_ids",
        "truth_position",
        "truth_velocity",
        "ground_truth",
        "ground_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "airsim_id",
        "entity_ids",
        "intercepted_target_indices",
        "offline_truth_labels",
    }
)
_METRIC_FIELDS = (
    "finite_state",
    "formal_acceptance_eligible",
    "experiment_matrix_metadata_valid",
    "variant_runtime_resolution_valid",
    "variant_execution_valid",
    "experiment_matrix_formal_acceptance_eligible",
    "current_schema_contract_match",
    "online_truth_use_count",
    "online_truth_field_violation_count",
    "observation_governance_generation_integrity",
    "d1_posterior_generation",
    "d1_full_posterior_publication_count",
    "d2_consumed_d1_posterior_generation",
    "d2_posterior_consumption_count",
    "d2_association_publication_count",
    "d2_pre_tick_posterior_merge_count",
    "d2_finalize_unchanged_posterior_skip_count",
    "d2_pending_generation_empty",
    "d1_track_count",
    "d1_speed_p50_mps",
    "d1_speed_p90_mps",
    "d1_speed_max_mps",
    "d1_velocity_covariance_trace_p50",
    "d1_velocity_covariance_trace_p90",
    "d1_velocity_covariance_trace_max",
    "d2_track_count",
    "d2_speed_p50_mps",
    "d2_speed_p90_mps",
    "d2_speed_max_mps",
    "d2_velocity_covariance_trace_p50",
    "d2_velocity_covariance_trace_p90",
    "d2_velocity_covariance_trace_max",
    "d2_id_switch_count",
    "d2_online_producer_id_switch_count",
    "d2_strict_identity_artifact_verified",
    "d3_current_track_count",
    "d3_plan_target_count",
    "d3_assignment_count",
    "d3_assigned_target_count",
    "d3_plan_coverage_rate",
    "d3_backlog_count",
    "d3_min_dwell_hold_event_count",
    "d3_min_dwell_backlog_max",
    "d3_learning_publication_count",
    "d3_learning_applied_count",
    "d3_learning_fallback_event_count",
    "d3_learning_bundle_loaded",
    "d4_region_count",
    "d4_execution_allowed_region_count",
    "d4_fail_closed_region_count",
    "d4_lease_expired_region_count",
    "d4_commit_count",
    "d4_advice_publication_count",
    "d4_advice_valid_publication_count",
    "d4_advice_invalid_publication_count",
    "d4_advice_recommendation_output_count",
    "d4_advice_shadow_output_count",
    "d4_advice_assist_eligible_count",
    "d4_advice_fallback_count",
    "d4_advice_inference_latency_p50_ms",
    "d4_advice_inference_latency_p95_ms",
    "d4_advice_resource_quota_conservation_violation_count",
    "d4_advice_projection_rejection_count",
    "d4_advice_formal_decision_mutation_count",
    "d4_advice_formal_decision_unchanged_count",
    "d4_advice_stale_version_evidence_count",
    "d4_advice_missing_version_evidence_count",
    "d4_advice_version_evidence_issue_count",
    "d4_advice_control_adoption_count",
    "d4_region_consumption_publication_count",
    "d4_region_consumption_valid_publication_count",
    "d4_region_consumption_invalid_publication_count",
    "d4_region_consumable_count",
    "d4_region_d3_hint_applied_count",
    "d4_region_consumption_summary_consistent",
    "d4_learning_bundle_loaded",
    "d4_learning_formal_unseen_seed_count",
    "d5_candidate_edge_count",
    "d5_graph_density",
    "d5_graph_edge_budget",
    "d5_graph_budget_utilization",
    "d5_graph_budget_dropped_count",
    "d5_binding_count",
    "d5_model_fallback_event_count",
    "d5_learning_bundle_loaded",
    "d7_command_count",
    "d7_hold_count",
    "d7_reject_count",
    "offline_truth_disposition_contract_valid",
    "offline_truth_label_count",
    "offline_truth_target_label_count",
    "offline_truth_known_false_alarm_count",
    "offline_truth_unknown_count",
    "offline_truth_missing_disposition_count",
    "offline_truth_complete_disposition_available",
    "offline_truth_strict_identity_eligible",
    "offline_truth_known_false_alarm_treated_as_target",
    "offline_truth_strict_id_switch_backfilled",
    "offline_proximity_within_5m_count",
    "offline_proximity_unique_target_count",
    "offline_proximity_identity_evaluable_count",
    "offline_proximity_identity_correct_count",
    "offline_proximity_identity_correct_rate",
    *D1_CENTROID_OVERLAY_SHADOW_NUMERIC_METRIC_FIELDS,
    *ACTIVE_VISION_NUMERIC_METRIC_FIELDS,
)

class Scalable3DOfflineEvaluationError(ValueError):
    """Raised when a persisted episode artifact is malformed or contradictory."""


@dataclass(frozen=True)
class Scalable3DOfflineEvaluationInputs:
    """Explicit episode directories supplied by main."""

    episode_dirs: tuple[Path, ...]
    module_performance_json_paths: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        directories = tuple(Path(value).resolve() for value in self.episode_dirs)
        if not directories:
            raise ValueError("at least one scalable 3D episode directory is required")
        if len(set(directories)) != len(directories):
            raise ValueError("episode directories must be unique")
        object.__setattr__(self, "episode_dirs", directories)
        performance_paths = tuple(
            Path(value).resolve() for value in self.module_performance_json_paths
        )
        if len(set(performance_paths)) != len(performance_paths):
            raise ValueError("module performance JSON paths must be unique")
        object.__setattr__(
            self,
            "module_performance_json_paths",
            performance_paths,
        )


class Scalable3DOfflineReportGenerator:
    """Generate per-episode CSV, aggregate JSON, Chinese Markdown, and a curve."""

    def write_report_bundle(
        self,
        output_dir: str | Path,
        *,
        inputs: Scalable3DOfflineEvaluationInputs,
        bootstrap_resamples: int = DEFAULT_SCALABLE_3D_BOOTSTRAP_RESAMPLES,
        bootstrap_rng_seed: int = DEFAULT_SCALABLE_3D_BOOTSTRAP_RNG_SEED,
        title: str = "可扩展三维真值隔离 episode 离线评估报告",
    ) -> dict[str, Path]:
        if int(bootstrap_resamples) <= 0:
            raise ValueError("bootstrap_resamples must be positive")
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        rows = [evaluate_scalable_3d_episode(path) for path in inputs.episode_dirs]
        stage_names = sorted(
            {
                stage
                for row in rows
                for stage in row.get("_stage_records", {})
            }
        )
        stage_slugs = [_stage_slug(stage) for stage in stage_names]
        if len(stage_slugs) != len(set(stage_slugs)):
            raise Scalable3DOfflineEvaluationError(
                "stage names collide after CSV column normalization"
            )
        for row in rows:
            _add_stage_columns(row, stage_names)
            _finalize_episode_status(row)

        aggregate = aggregate_scalable_3d_episodes(
            rows,
            bootstrap_resamples=int(bootstrap_resamples),
            bootstrap_rng_seed=int(bootstrap_rng_seed),
        )
        public_rows = [_public_row(row) for row in rows]
        module_performance_evidence = register_module_performance_evidence(
            inputs.module_performance_json_paths
        )
        aggregate["module_performance_evidence"] = module_performance_evidence

        csv_path = output_path / "scalable_3d_offline_per_episode_seed.csv"
        _write_rows_csv(csv_path, public_rows)

        aggregate_path = output_path / "scalable_3d_offline_aggregate.json"
        aggregate_path.write_text(
            json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        module_performance_path = output_path / "module_performance_evidence.json"
        module_performance_path.write_text(
            json.dumps(
                module_performance_evidence,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        plot_path = output_path / "scalable_3d_stage_timing_curves.png"
        _write_stage_timing_curves(aggregate, plot_path)

        markdown_path = output_path / "SCALABLE_3D_OFFLINE_EVALUATION_CN.md"
        markdown_path.write_text(
            render_scalable_3d_offline_markdown(
                public_rows,
                aggregate,
                title=title,
                plot_name=plot_path.name,
            ),
            encoding="utf-8",
        )
        return {
            "per_episode_seed_csv": csv_path,
            "aggregate_json": aggregate_path,
            "module_performance_evidence": module_performance_path,
            "markdown": markdown_path,
            "stage_timing_curve": plot_path,
        }


def discover_scalable_3d_episode_dirs(
    *,
    episode_dirs: Iterable[str | Path] = (),
    episode_roots: Iterable[str | Path] = (),
) -> tuple[Path, ...]:
    """Resolve explicit directories and discover directories with the episode core."""

    resolved: list[Path] = [Path(value).resolve() for value in episode_dirs]
    for raw_root in episode_roots:
        root = Path(raw_root).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"episode root does not exist: {root}")
        resolved.extend(
            path.parent.resolve()
            for path in sorted(root.rglob("manifest.json"))
            if _has_scalable_3d_episode_core(path.parent)
        )
    unique = tuple(dict.fromkeys(resolved))
    if not unique:
        raise ValueError("no scalable 3D episode directories were supplied or discovered")
    return unique


def _has_scalable_3d_episode_core(directory: Path) -> bool:
    """Return whether discovery evidence distinguishes an episode from a sidecar."""

    return all(
        (directory / artifact_name).is_file()
        for artifact_name in _EPISODE_DISCOVERY_REQUIRED_ARTIFACTS
    )


def evaluate_scalable_3d_episode(episode_dir: str | Path) -> dict[str, Any]:
    """Evaluate one persisted episode without importing or calling runtime code."""

    directory = Path(episode_dir).resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"episode directory does not exist: {directory}")

    manifest, manifest_reason = _load_json_object(directory / "manifest.json")
    config, config_reason = _load_json_object(directory / "scenario_config.json")
    summary, summary_reason = _load_json_object(directory / "summary.json")
    online, online_reason = _load_jsonl(directory / "online_observations.jsonl")
    proximity, proximity_reason = _load_jsonl(
        directory / "offline_proximity_intercepts.jsonl"
    )
    truth_labels, truth_labels_reason = _load_jsonl(
        directory / _OPTIONAL_TRUTH_ARTIFACT
    )
    stages, stages_reason = _load_stage_timings(directory / "stage_timings.csv")

    row: dict[str, Any] = {
        "evaluation_schema_version": SCALABLE_3D_OFFLINE_EVALUATION_SCHEMA_VERSION,
        "evaluation_date": SCALABLE_3D_OFFLINE_EVALUATION_DATE,
        "episode_dir": str(directory),
        "_stage_records": stages or {},
        "_stage_file_reason": stages_reason,
        "_failure_reasons": [],
    }
    row.update(_current_evaluator_provenance())
    artifact_reasons = {
        "manifest.json": manifest_reason,
        "scenario_config.json": config_reason,
        "summary.json": summary_reason,
        "stage_timings.csv": stages_reason,
        "online_observations.jsonl": online_reason,
        "offline_proximity_intercepts.jsonl": proximity_reason,
        _OPTIONAL_TRUTH_ARTIFACT: truth_labels_reason,
    }
    row["artifact_availability_json"] = {
        name: {
            "availability": "available" if reason is None else "unavailable",
            "unavailable_reason": reason,
        }
        for name, reason in artifact_reasons.items()
    }

    _extract_provenance(row, manifest, config, summary)
    row["episode_source_git_commit"] = row.get("git_commit")
    row["episode_source_repository_dirty"] = row.get("repository_dirty")
    _extract_learning_runtime_metrics(row, manifest, config, summary)
    ordered_online = _ordered_online_records(online or [])
    _extract_online_truth_audit(
        row,
        ordered_online,
        summary,
        online_unavailable_reason=online_reason,
    )
    posterior_governance = evaluate_posterior_governance(
        ordered_online,
        summary,
        online_unavailable_reason=online_reason,
    )
    row.update(posterior_governance.metrics)
    row["_failure_reasons"].extend(posterior_governance.failure_reasons)
    centroid_shadow_evidence = (
        evaluate_d1_centroid_overlay_shadow_evidence(
            ordered_online,
            summary,
            stages,
            online_unavailable_reason=online_reason,
            stage_unavailable_reason=stages_reason,
        )
    )
    row.update(centroid_shadow_evidence.metrics)
    row["_failure_reasons"].extend(
        centroid_shadow_evidence.failure_reasons
    )
    _extract_track_metrics(row, ordered_online, module="d1")
    _extract_track_metrics(row, ordered_online, module="d2")
    _extract_d2_online_producer_id_switch(row, ordered_online)
    _extract_d3_metrics(row, ordered_online)
    _extract_d3_learning_metrics(row, ordered_online)
    _extract_d4_metrics(row, ordered_online)
    _extract_d4_region_advice_metrics(row, ordered_online)
    _extract_d4_region_consumption_metrics(row, ordered_online, summary)
    regional_planning_chain = audit_regional_planning_chain(ordered_online)
    row.update(regional_planning_chain.to_scalable_3d_metrics())
    row["_failure_reasons"].extend(
        f"d4_planning_chain:{code}"
        for code in regional_planning_chain.safety_violation_codes
    )
    _extract_d5_metrics(row, ordered_online)
    active_vision_evidence = evaluate_active_vision_runtime_evidence(
        ordered_online,
        summary,
        online_unavailable_reason=online_reason,
        forbidden_field_counter=_count_forbidden_online_fields,
    )
    row.update(active_vision_evidence.metrics)
    row["_failure_reasons"].extend(active_vision_evidence.failure_reasons)
    _extract_d7_metrics(row, ordered_online)
    _extract_camera_count(row, config, ordered_online)
    _extract_d2_strict_offline_id_switch(row, directory)
    truth_disposition = _extract_observation_truth_disposition_metrics(
        row,
        labels=truth_labels,
        labels_reason=truth_labels_reason,
    )
    _extract_proximity_metrics(
        row,
        proximity_records=proximity,
        proximity_reason=proximity_reason,
        online_records=ordered_online,
        truth_labels=truth_labels,
        truth_labels_reason=truth_labels_reason,
        truth_disposition=truth_disposition,
    )
    _put_unavailable(
        row,
        "mission_success",
        "five_meter_proximity_is_not_mission_success",
    )
    extract_experiment_matrix_evidence(row, config, summary)
    _add_stage_columns(row, sorted((stages or {}).keys()))
    _finalize_episode_status(row)
    return row


def aggregate_scalable_3d_episodes(
    rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_resamples: int = DEFAULT_SCALABLE_3D_BOOTSTRAP_RESAMPLES,
    bootstrap_rng_seed: int = DEFAULT_SCALABLE_3D_BOOTSTRAP_RNG_SEED,
) -> dict[str, Any]:
    """Aggregate by explicit scenario/version/scale and bootstrap distinct seeds."""

    if int(bootstrap_resamples) <= 0:
        raise ValueError("bootstrap_resamples must be positive")
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(field) for field in _GROUP_FIELDS)].append(row)

    groups: list[dict[str, Any]] = []
    scale_stage_shares: list[dict[str, Any]] = []
    for key in sorted(grouped, key=_sortable_group_key):
        group_rows = grouped[key]
        group_identity = dict(zip(_GROUP_FIELDS, key))
        seeds = sorted(
            {
                int(row["seed"])
                for row in group_rows
                if _is_int_like(row.get("seed"))
            }
        )
        metric_names = _aggregate_metric_names(group_rows)
        metric_statistics = {
            metric: _metric_statistics(
                group_rows,
                metric,
                bootstrap_resamples=int(bootstrap_resamples),
                bootstrap_rng_seed=int(bootstrap_rng_seed),
                group_identity=group_identity,
            )
            for metric in metric_names
        }
        stage_timing = _aggregate_stage_timing(
            group_rows,
            bootstrap_resamples=int(bootstrap_resamples),
            bootstrap_rng_seed=int(bootstrap_rng_seed),
            group_identity=group_identity,
        )
        seed_groups = _aggregate_exact_seed_groups(group_rows, metric_names)
        group = {
            **group_identity,
            "episode_count": len(group_rows),
            "seed_count": len(seeds),
            "seeds": seeds,
            "inference_status": (
                "bootstrap_across_distinct_seed_means"
                if len(seeds) >= 2
                else "descriptive_only_single_seed"
            ),
            "metric_statistics": metric_statistics,
            "stage_timing": stage_timing,
            "failure_reason_distribution": _counter_from_json_field(
                group_rows, "episode_failure_reasons_json"
            ),
            "evidence_unavailability_reason_distribution": (
                _counter_from_json_field(
                    group_rows, "evidence_unavailability_reasons_json"
                )
            ),
            "d4_fail_closed_reason_distribution": _counter_from_mapping_field(
                group_rows, "d4_fail_closed_reasons_json"
            ),
            "d3_learning_requested_mode_distribution": _counter_from_scalar_field(
                group_rows, "d3_learning_requested_mode"
            ),
            "d3_learning_effective_mode_distribution": _counter_from_scalar_field(
                group_rows, "d3_learning_effective_mode"
            ),
            "d3_learning_runtime_fallback_reason_distribution": (
                _counter_from_scalar_field(
                    group_rows, "d3_learning_fallback_reason"
                )
            ),
            "d3_learning_fallback_reason_distribution": _counter_from_mapping_field(
                group_rows, "d3_learning_fallback_reason_distribution_json"
            ),
            "d4_learning_requested_mode_distribution": _counter_from_scalar_field(
                group_rows, "d4_learning_requested_mode"
            ),
            "d4_learning_effective_mode_distribution": _counter_from_scalar_field(
                group_rows, "d4_learning_effective_mode"
            ),
            "d4_learning_runtime_fallback_reason_distribution": (
                _counter_from_scalar_field(
                    group_rows, "d4_learning_fallback_reason"
                )
            ),
            "d4_advice_requested_mode_distribution": _counter_from_mapping_field(
                group_rows, "d4_advice_requested_mode_distribution_json"
            ),
            "d4_advice_effective_mode_distribution": _counter_from_mapping_field(
                group_rows, "d4_advice_effective_mode_distribution_json"
            ),
            "d4_advice_fallback_reason_distribution": _counter_from_mapping_field(
                group_rows, "d4_advice_fallback_reason_distribution_json"
            ),
            "d4_advice_invalid_reason_distribution": _counter_from_mapping_field(
                group_rows, "d4_advice_invalid_reason_distribution_json"
            ),
            "d4_advice_version_evidence_issue_reason_distribution": (
                _counter_from_mapping_field(
                    group_rows, "d4_advice_version_evidence_issue_reasons_json"
                )
            ),
            "d5_fallback_reason_distribution": _counter_from_mapping_field(
                group_rows, "d5_fallback_reason_distribution_json"
            ),
            "d5_learning_requested_mode_distribution": _counter_from_scalar_field(
                group_rows, "d5_learning_requested_mode"
            ),
            "d5_learning_effective_mode_distribution": _counter_from_scalar_field(
                group_rows, "d5_learning_effective_mode"
            ),
            "d5_learning_runtime_fallback_reason_distribution": (
                _counter_from_scalar_field(
                    group_rows, "d5_learning_fallback_reason"
                )
            ),
            "d5_active_vision_requested_mode_distribution": (
                _counter_from_mapping_field(
                    group_rows,
                    "d5_active_vision_requested_mode_distribution_json",
                )
            ),
            "d5_active_vision_effective_mode_distribution": (
                _counter_from_mapping_field(
                    group_rows,
                    "d5_active_vision_effective_mode_distribution_json",
                )
            ),
            "d5_active_vision_intent_distribution": (
                _counter_from_mapping_field(
                    group_rows,
                    "d5_active_vision_intent_distribution_json",
                )
            ),
            "d5_active_vision_rejection_reason_distribution": (
                _counter_from_mapping_field(
                    group_rows,
                    "d5_active_vision_rejection_reason_distribution_json",
                )
            ),
            "d1_centroid_overlay_shadow_rejection_reason_distribution": (
                _counter_from_mapping_field(
                    group_rows,
                    "d1_centroid_overlay_shadow_rejection_reason_distribution_json",
                )
            ),
            "d7_reject_reason_distribution": _counter_from_mapping_field(
                group_rows, "d7_reject_reason_distribution_json"
            ),
            "per_seed_groups": seed_groups,
        }
        groups.append(group)
        scale_stage_shares.append(
            {
                **group_identity,
                "episode_count": len(group_rows),
                "seed_count": len(seeds),
                "stages": {
                    stage: values["pooled_wall_time_share"]
                    for stage, values in stage_timing.items()
                },
            }
        )

    experiment_matrix = aggregate_experiment_matrix(
        rows,
        bootstrap_resamples=int(bootstrap_resamples),
        bootstrap_rng_seed=int(bootstrap_rng_seed),
    )
    return {
        "schema_version": SCALABLE_3D_OFFLINE_EVALUATION_SCHEMA_VERSION,
        "evaluation_date": SCALABLE_3D_OFFLINE_EVALUATION_DATE,
        "evaluator_provenance": _aggregate_evaluator_provenance(rows),
        "episode_count": len(rows),
        "grouping_fields": list(_GROUP_FIELDS),
        "seed_grouping_field": "seed",
        "bootstrap": {
            "method": "percentile_95_ci_on_distinct_seed_means",
            "resamples": int(bootstrap_resamples),
            "rng_seed": int(bootstrap_rng_seed),
            "single_seed_policy": "descriptive_only_no_ci",
        },
        "formal_acceptance_eligible_episode_count": sum(
            row.get("formal_acceptance_eligible") is True for row in rows
        ),
        "episode_evidence_status_distribution": dict(
            sorted(
                Counter(
                    str(
                        row.get(
                            "episode_evidence_status",
                            "descriptive_or_incomplete_evidence",
                        )
                    )
                    for row in rows
                ).items()
            )
        ),
        "repository_dirty_episode_count": sum(
            row.get("repository_dirty") is True for row in rows
        ),
        "single_seed_group_count": sum(group["seed_count"] < 2 for group in groups),
        "failure_reason_distribution": _counter_from_json_field(
            rows, "episode_failure_reasons_json"
        ),
        "evidence_unavailability_reason_distribution": _counter_from_json_field(
            rows, "evidence_unavailability_reasons_json"
        ),
        "groups": groups,
        "scale_stage_time_shares": scale_stage_shares,
        "stage_timing_quantile_semantics": {
            "episode_statistic": (
                "each value is a within-episode quantile over that stage's "
                "persisted per-call timing samples"
            ),
            "cross_seed_statistic": (
                "group statistics describe the seed distribution of episode-level "
                "call quantiles; bootstrap intervals are on distinct-seed means"
            ),
            "pooled_call_quantiles": (
                "not computed because raw per-call samples are not persisted"
            ),
            "legacy_policy": (
                "legacy rows infer distribution availability from complete quantile "
                "triples; absent values remain null and unavailable"
            ),
        },
        "experiment_matrix": experiment_matrix,
        "physical_outcome_semantics": {
            "offline_proximity_within_5m_count": (
                "offline physical diagnostic only; not mission success"
            ),
            "identity_correctness": (
                "available only with explicit evaluator-side global-track-to-truth mapping"
            ),
        },
        "learning_evidence_layers": {
            "bundle_loaded": (
                "runtime metadata only; proves that a versioned bundle loaded"
            ),
            "shadow_output": (
                "valid projected recommendation publication; not control adoption"
            ),
            "assist_eligible": (
                "advisor gate eligibility only; not control adoption"
            ),
            "control_adoption": (
                "unavailable unless a separate producer field explicitly records adoption"
            ),
            "physical_outcome": (
                "offline proximity diagnostic; no causal attribution to learning advice"
            ),
            "current_d4_contract": (
                "region_resource_advice leaves the formal D4 decision unchanged"
            ),
            "d5_active_vision": {
                "rule_command": "actual deterministic command issued by D5",
                "shadow_suggestion": (
                    "model output observed without replacing the issued rule command"
                ),
                "assist_adopted": (
                    "safety-screened model action selected by D5; runtime ACK remains separate"
                ),
                "ack_applied": "main runtime applied the versioned camera command",
                "physical_attribution": (
                    "null unless paired episodes and applied assist evidence exist"
                ),
            },
            "d1_centroid_overlay_shadow": {
                "shadow_difference": (
                    "canonical/shadow SHA inequality describes a detached "
                    "experimental DTO difference only"
                ),
                "business_nonintervention": (
                    "separate gate over canonical-surface integrity, global "
                    "track identity, zero D2/D3 consumption, summary agreement, "
                    "and zero online truth use"
                ),
                "control_authority": "none; persisted logs are read only",
            },
        },
    }


def render_scalable_3d_offline_markdown(
    rows: Sequence[Mapping[str, Any]],
    aggregate: Mapping[str, Any],
    *,
    title: str,
    plot_name: str,
) -> str:
    """Render a concise Chinese report with explicit evidence boundaries."""

    lines = [
        f"# {title}",
        "",
        f"评估日期：{SCALABLE_3D_OFFLINE_EVALUATION_DATE}",
        "",
        "## 结论",
        "",
        f"本次离线读取 {len(rows)} 个 main-owned episode。评估按 scenario/version、实际 target/resource/recon/camera 数量和 seed 组织，不从 2v2/5v5 名称推断规模。",
        f"基础 clean provenance 条件可用的 episode 为 {aggregate.get('formal_acceptance_eligible_episode_count', 0)}/{len(rows)}；dirty episode 为 {aggregate.get('repository_dirty_episode_count', 0)}。",
        f"最终证据分类分布为 `{json.dumps(aggregate.get('episode_evidence_status_distribution', {}), ensure_ascii=False, sort_keys=True)}`。没有实验矩阵声明的 clean 输入归入 descriptive clean-source calibration，不提升为实验矩阵 formal 证据。",
        f"当前 schema 合同由 `{SCALABLE_3D_SCHEMA_REGISTRY_VERSION}` 核对；原始 schema 字段始终保留，旧值、未知值、篡改值或缺字段不得进入正式 clean acceptance。",
        "五米接近仅是离线物理诊断，不自动代表身份正确、合同许可、控制成功或任务成功。",
        "",
        "## Episode 明细",
        "",
        "| scenario/version | scale T/R/Rc/Cam | seed | finite | dirty | schema current | online truth | D1/D2 tracks | D2 strict IDSW / online diagnostic | D3 coverage/backlog | D4 fail-closed | D5 fallback | D7 cmd/hold/reject | <=5m / identity |",
        "| --- | --- | ---: | :---: | :---: | :---: | ---: | --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for row in rows:
        scale = "/".join(
            _fmt(row.get(field))
            for field in ("target_count", "resource_count", "recon_count", "camera_count")
        )
        idsw = (
            f"{_fmt_available(row, 'd2_id_switch_count')} / "
            f"{_fmt_available(row, 'd2_online_producer_id_switch_count')}"
        )
        identity = _fmt_available(row, "offline_proximity_identity_correct_rate")
        lines.append(
            "| {scenario}/{version} | {scale} | {seed} | {finite} | {dirty} | {schema} | {truth} | "
            "{d1}/{d2} | {idsw} | {coverage}/{backlog} | {fail_closed} | {fallback} | "
            "{commands}/{holds}/{rejects} | {proximity}/{identity} |".format(
                scenario=_fmt(row.get("scenario_name")),
                version=_fmt(row.get("scenario_version")),
                scale=scale,
                seed=_fmt(row.get("seed")),
                finite=_fmt_available(row, "finite_state"),
                dirty=_fmt_available(row, "repository_dirty"),
                schema=_fmt_available(row, "current_schema_contract_match"),
                truth=_fmt_available(row, "online_truth_use_count"),
                d1=_fmt_available(row, "d1_track_count"),
                d2=_fmt_available(row, "d2_track_count"),
                idsw=idsw,
                coverage=_fmt_available(row, "d3_plan_coverage_rate"),
                backlog=_fmt_available(row, "d3_min_dwell_backlog_max"),
                fail_closed=_fmt_available(row, "d4_fail_closed_region_count"),
                fallback=_fmt(row.get("d5_fallback_reason")),
                commands=_fmt_available(row, "d7_command_count"),
                holds=_fmt_available(row, "d7_hold_count"),
                rejects=_fmt_available(row, "d7_reject_count"),
                proximity=_fmt_available(row, "offline_proximity_within_5m_count"),
                identity=identity,
            )
        )

    lines.extend(
        [
            "",
            "## 离线观测处置",
            "",
            "v2 sidecar 对每条观测显式区分目标、已知虚警和未知。已知虚警不进入目标身份映射，未知状态关闭严格身份可用性。D6 不从观测编号、距离、actor 名称或在线状态推断处置，也不利用部分证据回填 D2 严格 ID Switch。",
            "",
            "| seed | schema | contract | total | target | known false alarm | unknown | missing disposition | strict identity eligible | IDSW backfill |",
            "| ---: | --- | :---: | ---: | ---: | ---: | ---: | ---: | :---: | :---: |",
        ]
    )
    for row in rows:
        lines.append(
            "| {seed} | {schema} | {contract} | {total} | {target} | {false_alarm} | "
            "{unknown} | {missing} | {strict} | {backfill} |".format(
                seed=_fmt(row.get("seed")),
                schema=_fmt(
                    row.get("offline_truth_disposition_audit_json", {}).get(
                        "source_schema_version"
                    )
                    if isinstance(
                        row.get("offline_truth_disposition_audit_json"),
                        Mapping,
                    )
                    else None
                ),
                contract=_fmt_available(
                    row,
                    "offline_truth_disposition_contract_valid",
                ),
                total=_fmt_available(row, "offline_truth_label_count"),
                target=_fmt_available(row, "offline_truth_target_label_count"),
                false_alarm=_fmt_available(
                    row,
                    "offline_truth_known_false_alarm_count",
                ),
                unknown=_fmt_available(row, "offline_truth_unknown_count"),
                missing=_fmt_available(
                    row,
                    "offline_truth_missing_disposition_count",
                ),
                strict=_fmt_available(
                    row,
                    "offline_truth_strict_identity_eligible",
                ),
                backfill=_fmt_available(
                    row,
                    "offline_truth_strict_id_switch_backfilled",
                ),
            )
        )

    lines.extend(
        [
            "",
            "## D1-D2 后验代次审计",
            "",
            "运行时 v2 同时核对最终治理快照和在线总线。D1 完整后验代次必须从 1 连续递增；D2 来源代次必须严格递增、不得重复，并且只能引用此前发布的完整后验。episode 结束时待处理代次必须为空，累计消费次数必须等于实际 D2 发布数。D6 会比较末尾逐轨状态、协方差、有效时刻和航迹状态，但现有持久化字段不能证明完整 D2 输入等价；在上游发布版本化完整输入摘要前，declared skip 不进入 formal 守恒。计数守恒本身不能替代内容等价证明。v1 没有这些字段，结果保持 unavailable，不按 0 处理。",
            "",
            "| seed | runtime schema | integrity | D1 final/full pub | D2 final/consumption/pub | pre-tick merge | declared final skip | pending empty | status/reasons |",
            "| ---: | --- | :---: | --- | --- | ---: | ---: | :---: | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| {seed} | {schema} | {integrity} | {d1}/{d1_pub} | "
            "{d2}/{consume}/{d2_pub} | {merge} | {skip} | {pending} | "
            "{status}/{reasons} |".format(
                seed=_fmt(row.get("seed")),
                schema=_fmt_available(
                    row, "observation_governance_runtime_schema"
                ),
                integrity=_fmt_available(
                    row, "observation_governance_generation_integrity"
                ),
                d1=_fmt_available(row, "d1_posterior_generation"),
                d1_pub=_fmt_available(
                    row, "d1_full_posterior_publication_count"
                ),
                d2=_fmt_available(
                    row, "d2_consumed_d1_posterior_generation"
                ),
                consume=_fmt_available(row, "d2_posterior_consumption_count"),
                d2_pub=_fmt_available(row, "d2_association_publication_count"),
                merge=_fmt_available(row, "d2_pre_tick_posterior_merge_count"),
                skip=_fmt_available(
                    row,
                    "d2_finalize_unchanged_posterior_skip_count",
                ),
                pending=_fmt_available(row, "d2_pending_generation_empty"),
                status=_fmt_available(
                    row, "observation_governance_generation_contract_status"
                ),
                reasons=_fmt_available(
                    row,
                    "observation_governance_generation_integrity_reasons_json",
                ),
            )
        )

    performance_registry = aggregate.get("module_performance_evidence", {})
    lines.extend(
        [
            "",
            "## 模块性能描述性证据",
            "",
            "以下登记项来自 D1 或 D5 的独立回放、微基准或 A/B 性能 JSON。D6 只记录来源 schema 和文件哈希；这些结果不等同于 D1-D7 全栈实时能力，也不证明控制效果。",
            "",
            "| 模块 | 来源 schema | SHA-256 | 证据类别 | 全栈实时声明 |",
            "| --- | --- | --- | --- | :---: |",
        ]
    )
    for evidence in performance_registry.get("records", []):
        lines.append(
            "| {module} | {schema} | `{digest}` | {evidence_class} | {claim} |".format(
                module=_fmt(evidence.get("module")),
                schema=_fmt(evidence.get("source_schema_version")),
                digest=_fmt(evidence.get("sha256")),
                evidence_class=_fmt(evidence.get("evidence_class")),
                claim=_fmt(evidence.get("full_stack_realtime_claim")),
            )
        )
    if not performance_registry.get("records"):
        lines.append("| unavailable | unavailable | unavailable | 未显式提供模块性能 JSON | false |")

    lines.extend(["", *render_experiment_matrix_markdown_lines(
        aggregate.get("experiment_matrix", {})
    )])

    lines.extend(
        [
            "",
            "## 学习运行时与 D4 Advice 分层",
            "",
            "以下五层不能互相回填：bundle 能加载只说明版本化产物可用；shadow 有输出只说明产生了合法且经过安全投影的 recommendation；assist 获准只说明门控通过；控制实际采用必须有独立 producer 证据；物理结果仍是离线结果层。",
            "`d4-region-resource-advisory-runtime-v1` 不改变正式 D4 裁决，因此 `assist_eligible` 不是控制生效；control adoption 只接受通过合同与 summary 审计的 main 消费记录及 D3 hint applied 证据。",
            "",
            "| seed | D3 bundle/fingerprint/version | D4 bundle/fingerprint/version | D5 bundle/fingerprint/version | D4 advice pub | shadow output | assist eligible | formal unchanged/mutation | control adopted | physical <=5m |",
            "| ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- | ---: |",
        ]
    )
    for row in rows:
        module_evidence = {}
        for module in ("d3", "d4", "d5"):
            module_evidence[module] = "/".join(
                (
                    _fmt_available(row, f"{module}_learning_bundle_loaded"),
                    _fmt_available(row, f"{module}_learning_model_fingerprint"),
                    _fmt_available(row, f"{module}_learning_model_version"),
                )
            )
        lines.append(
            "| {seed} | {d3} | {d4} | {d5} | {published} | {shadow} | {assist} | "
            "{unchanged}/{mutation} | {adopted} | {physical} |".format(
                seed=_fmt(row.get("seed")),
                d3=module_evidence["d3"],
                d4=module_evidence["d4"],
                d5=module_evidence["d5"],
                published=_fmt_available(row, "d4_advice_publication_count"),
                shadow=_fmt_available(row, "d4_advice_shadow_output_count"),
                assist=_fmt_available(row, "d4_advice_assist_eligible_count"),
                unchanged=_fmt_available(
                    row, "d4_advice_formal_decision_unchanged_count"
                ),
                mutation=_fmt_available(
                    row, "d4_advice_formal_decision_mutation_count"
                ),
                adopted=_fmt_available(row, "d4_advice_control_adoption_count"),
                physical=_fmt_available(row, "offline_proximity_within_5m_count"),
            )
        )

    lines.extend(
        [
            "",
            "| seed | requested modes | effective modes | fallback/reasons | latency P50/P95 ms | quota conservation violations | projection rejections | stale/missing version evidence | invalid advice |",
            "| ---: | --- | --- | --- | --- | ---: | ---: | --- | ---: |",
        ]
    )
    for row in rows:
        fallback = "{}/{}".format(
            _fmt_available(row, "d4_advice_fallback_count"),
            _fmt_available(row, "d4_advice_fallback_reason_distribution_json"),
        )
        lines.append(
            "| {seed} | {requested} | {effective} | {fallback} | {p50}/{p95} | "
            "{quota} | {rejections} | {stale}/{missing} | {invalid} |".format(
                seed=_fmt(row.get("seed")),
                requested=_fmt_available(
                    row, "d4_advice_requested_mode_distribution_json"
                ),
                effective=_fmt_available(
                    row, "d4_advice_effective_mode_distribution_json"
                ),
                fallback=fallback,
                p50=_fmt_available(row, "d4_advice_inference_latency_p50_ms"),
                p95=_fmt_available(row, "d4_advice_inference_latency_p95_ms"),
                quota=_fmt_available(
                    row,
                    "d4_advice_resource_quota_conservation_violation_count",
                ),
                rejections=_fmt_available(
                    row, "d4_advice_projection_rejection_count"
                ),
                stale=_fmt_available(
                    row, "d4_advice_stale_version_evidence_count"
                ),
                missing=_fmt_available(
                    row, "d4_advice_missing_version_evidence_count"
                ),
                invalid=_fmt_available(row, "d4_advice_invalid_publication_count"),
            )
        )

    lines.extend(
        [
            "",
            "## D4 区域规划链",
            "",
            "该审计连接 D4 规划专用建议、main 消费记录和 D3 严格后继计划。真实干预必须改变资源到全局航迹的绑定集合或目标覆盖；单纯升版、续租或元数据刷新不计入。",
            "source/successor 的分配数和未分配数只形成描述性非退化。缺少独立同键 R0 时不形成因果收益；规则建议器的正例始终不记为学习模型收益。故障代际围栏阻断建议消费时只记录安全围栏通过，不记为模型性能失败。",
            "",
            "| seed | status | chain | authority safe | real binding | assignment source/successor/delta | unassigned source/successor/delta | non-degradation scope/result | same-key R0 | model benefit | fault fence | blockers | violations |",
            "| ---: | --- | :---: | :---: | :---: | --- | --- | --- | :---: | :---: | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| {seed} | {status} | {chain} | {authority} | {binding} | "
            "{source_assignment}/{successor_assignment}/{assignment_delta} | "
            "{source_unassigned}/{successor_unassigned}/{unassigned_delta} | "
            "{scope}/{non_degraded} | {r0} | {benefit} | {fence_available}/{fence_passed} | "
            "{blockers} | {violations} |".format(
                seed=_fmt(row.get("seed")),
                status=_fmt(row.get("d4_planning_chain_status")),
                chain=_fmt(
                    row.get("d4_planning_chain_contract_chain_available")
                ),
                authority=_fmt(
                    row.get("d4_planning_chain_planning_only_authority_safe")
                ),
                binding=_fmt(
                    row.get(
                        "d4_planning_chain_real_binding_intervention_available"
                    )
                ),
                source_assignment=_fmt(
                    row.get("d4_planning_chain_source_assignment_count")
                ),
                successor_assignment=_fmt(
                    row.get("d4_planning_chain_successor_assignment_count")
                ),
                assignment_delta=_fmt(
                    row.get("d4_planning_chain_assignment_count_delta")
                ),
                source_unassigned=_fmt(
                    row.get("d4_planning_chain_source_unassigned_count")
                ),
                successor_unassigned=_fmt(
                    row.get("d4_planning_chain_successor_unassigned_count")
                ),
                unassigned_delta=_fmt(
                    row.get("d4_planning_chain_unassigned_count_delta")
                ),
                scope=_fmt(
                    row.get("d4_planning_chain_non_degradation_scope")
                ),
                non_degraded=_fmt(
                    row.get("d4_planning_chain_non_degraded")
                ),
                r0=_fmt(row.get("d4_planning_chain_same_key_r0_available")),
                benefit=_fmt(
                    row.get("d4_planning_chain_model_benefit_available")
                ),
                fence_available=_fmt(
                    row.get(
                        "d4_planning_chain_fault_generation_fence_evidence_available"
                    )
                ),
                fence_passed=_fmt(
                    row.get("d4_planning_chain_fault_generation_fence_passed")
                ),
                blockers=_fmt(
                    row.get("d4_planning_chain_blocker_codes_json")
                ),
                violations=_fmt(
                    row.get("d4_planning_chain_safety_violation_codes_json")
                ),
            )
        )

    lines.extend(
        [
            "",
            "## D1 质心发布影子旁路",
            "",
            "该表只审计 `audit.d1.centroid_publication_overlay_shadow` 的持久化日志。canonical 与 shadow 摘要不同仅说明脱离正式链路的实验副本发生变化，不表示 D1 正式航迹、D2 关联输入或 D3 分配输入发生变化。",
            "业务非干预使用独立判据：全局航迹编号序列不变、禁止表面未修改、正式航迹未替换、D2/D3 消费均为 0、在线真值使用为 0，并且逐条日志与最终摘要一致。缺任一字段时保持 unavailable。",
            "",
            "| seed | enabled/pub | SHA equal/different | ID unchanged/changed | accepted/rejected/error | timestamps M/A/both | forbidden | D2/D3/truth use | overhead P50/P95/max ms | watermark current/peak/cap | payload peak B | summary/timing/nonintervention |",
            "| ---: | --- | --- | --- | --- | --- | ---: | --- | --- | --- | ---: | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| {seed} | {enabled}/{published} | {equal}/{different} | "
            "{unchanged}/{changed} | {accepted}/{rejected}/{errors} | "
            "{measurement}/{arrival}/{dual} | {forbidden} | {d2}/{d3}/{truth} | "
            "{p50}/{p95}/{maximum} | {current}/{peak}/{capacity} | {payload} | "
            "{summary}/{timing}/{nonintervention} |".format(
                seed=_fmt(row.get("seed")),
                enabled=_fmt_available(
                    row, "d1_centroid_overlay_shadow_enabled"
                ),
                published=_fmt_available(
                    row, "d1_centroid_overlay_shadow_publication_count"
                ),
                equal=_fmt_available(
                    row, "d1_centroid_overlay_shadow_sha_equal_count"
                ),
                different=_fmt_available(
                    row, "d1_centroid_overlay_shadow_sha_different_count"
                ),
                unchanged=_fmt_available(
                    row,
                    "d1_centroid_overlay_shadow_global_track_id_unchanged_count",
                ),
                changed=_fmt_available(
                    row,
                    "d1_centroid_overlay_shadow_global_track_id_changed_count",
                ),
                accepted=_fmt_available(
                    row, "d1_centroid_overlay_shadow_accepted_count"
                ),
                rejected=_fmt_available(
                    row, "d1_centroid_overlay_shadow_rejected_count"
                ),
                errors=_fmt_available(
                    row, "d1_centroid_overlay_shadow_error_count"
                ),
                measurement=_fmt_available(
                    row,
                    "d1_centroid_overlay_shadow_measurement_timestamp_publication_count",
                ),
                arrival=_fmt_available(
                    row,
                    "d1_centroid_overlay_shadow_arrival_timestamp_publication_count",
                ),
                dual=_fmt_available(
                    row,
                    "d1_centroid_overlay_shadow_dual_timestamp_publication_count",
                ),
                forbidden=_fmt_available(
                    row,
                    "d1_centroid_overlay_shadow_forbidden_surface_violation_count",
                ),
                d2=_fmt_available(
                    row, "d1_centroid_overlay_shadow_d2_consumption_count"
                ),
                d3=_fmt_available(
                    row, "d1_centroid_overlay_shadow_d3_consumption_count"
                ),
                truth=_fmt_available(
                    row, "d1_centroid_overlay_shadow_online_truth_use_count"
                ),
                p50=_fmt_available(
                    row, "d1_centroid_overlay_shadow_overhead_p50_ms"
                ),
                p95=_fmt_available(
                    row, "d1_centroid_overlay_shadow_overhead_p95_ms"
                ),
                maximum=_fmt_available(
                    row, "d1_centroid_overlay_shadow_overhead_max_ms"
                ),
                current=_fmt_available(
                    row,
                    "d1_centroid_overlay_shadow_generation_watermark_current",
                ),
                peak=_fmt_available(
                    row,
                    "d1_centroid_overlay_shadow_generation_watermark_peak",
                ),
                capacity=_fmt_available(
                    row,
                    "d1_centroid_overlay_shadow_generation_watermark_capacity",
                ),
                payload=_fmt_available(
                    row, "d1_centroid_overlay_shadow_payload_bytes_peak"
                ),
                summary=_fmt_available(
                    row,
                    "d1_centroid_overlay_shadow_summary_counter_consistent",
                ),
                timing=_fmt_available(
                    row,
                    "d1_centroid_overlay_shadow_overhead_stage_consistent",
                ),
                nonintervention=_fmt_available(
                    row,
                    "d1_centroid_overlay_shadow_business_nonintervention_passed",
                ),
            )
        )

    lines.extend(
        [
            "",
            "## D5 主动视觉运行证据",
            "",
            "规则命令是实际发布的确定性动作。影子建议只记录模型产生但未替换规则动作的建议。辅助采用表示 D5 通过安全门后选择模型动作，主运行时仍需返回 applied ACK 才能证明动作实际生效。",
            "目标航迹编号只按此前 D2 发布的中心航迹集合做只读核对。缺少 D2 快照、命令日志或 ACK 时，对应比率和延迟保持 unavailable。物理结果不从同一 episode 的接近事件归因给主动视觉。",
            "",
            "| seed | rule/shadow/assist adopted | issued/ACK/applied/rejected | ACK P50/P95 ms | expired/stale/camera/other | track refs consistent/evaluable | truth fields | summary match | physical attribution |",
            "| ---: | --- | --- | --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| {seed} | {rule}/{shadow}/{assist} | {issued}/{acks}/{applied}/{rejected} | "
            "{p50}/{p95} | {expired}/{stale}/{camera}/{other} | {consistent}/{evaluable} | "
            "{truth} | {summary} | {attribution} |".format(
                seed=_fmt(row.get("seed")),
                rule=_fmt_available(row, "d5_active_vision_rule_command_count"),
                shadow=_fmt_available(
                    row, "d5_active_vision_shadow_suggestion_count"
                ),
                assist=_fmt_available(row, "d5_active_vision_assist_adopted_count"),
                issued=_fmt_available(row, "d5_active_vision_command_issued_count"),
                acks=_fmt_available(row, "d5_active_vision_ack_count"),
                applied=_fmt_available(row, "d5_active_vision_ack_applied_count"),
                rejected=_fmt_available(row, "d5_active_vision_ack_rejected_count"),
                p50=_fmt_available(row, "d5_active_vision_ack_latency_p50_ms"),
                p95=_fmt_available(row, "d5_active_vision_ack_latency_p95_ms"),
                expired=_fmt_available(
                    row, "d5_active_vision_rejected_expired_count"
                ),
                stale=_fmt_available(
                    row, "d5_active_vision_rejected_stale_version_count"
                ),
                camera=_fmt_available(
                    row, "d5_active_vision_rejected_camera_unavailable_count"
                ),
                other=_fmt_available(row, "d5_active_vision_rejected_other_count"),
                consistent=_fmt_available(
                    row, "d5_active_vision_target_reference_consistent_count"
                ),
                evaluable=_fmt_available(
                    row, "d5_active_vision_target_reference_evaluable_count"
                ),
                truth=_fmt_available(
                    row,
                    "d5_active_vision_online_truth_field_violation_count",
                ),
                summary=_fmt_available(
                    row, "d5_active_vision_summary_counter_consistent"
                ),
                attribution=_fmt_available(
                    row, "d5_active_vision_physical_outcome_attribution"
                ),
            )
        )

    lines.extend(
        [
            "",
            "## 聚合与不确定性",
            "",
            f"Bootstrap 使用固定 rng_seed={aggregate.get('bootstrap', {}).get('rng_seed')}、resamples={aggregate.get('bootstrap', {}).get('resamples')}，抽样单位为不同 seed 的 episode 均值。",
            "单 seed 分组只标记 descriptive，不生成 bootstrap 置信区间或推断性结论。",
            "",
            "| scenario/version | scale T/R/Rc/Cam | episodes | seeds | 状态 | schema match mean | finite mean | D3 coverage mean | D7 reject mean |",
            "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for group in aggregate.get("groups", []):
        metrics = group.get("metric_statistics", {})
        scale = "/".join(
            _fmt(group.get(field))
            for field in ("target_count", "resource_count", "recon_count", "camera_count")
        )
        lines.append(
            "| {scenario}/{version} | {scale} | {episodes} | {seeds} | {status} | {schema} | {finite} | {coverage} | {reject} |".format(
                scenario=_fmt(group.get("scenario_name")),
                version=_fmt(group.get("scenario_version")),
                scale=scale,
                episodes=group.get("episode_count", 0),
                seeds=group.get("seed_count", 0),
                status=group.get("inference_status", "unavailable"),
                schema=_fmt_stat(metrics.get("current_schema_contract_match")),
                finite=_fmt_stat(metrics.get("finite_state")),
                coverage=_fmt_stat(metrics.get("d3_plan_coverage_rate")),
                reject=_fmt_stat(metrics.get("d7_reject_count")),
            )
        )

    lines.extend(
        [
            "",
            "## 不同规模阶段耗时占比",
            "",
            f"![阶段耗时曲线]({plot_name})",
            "",
            "| scenario/version | scale T/R/Rc/Cam | dominant stage | pooled share |",
            "| --- | --- | --- | ---: |",
        ]
    )
    for item in aggregate.get("scale_stage_time_shares", []):
        stages = item.get("stages", {})
        available = {
            str(stage): value
            for stage, value in stages.items()
            if _is_finite_number(value)
        }
        dominant = max(available, key=available.get) if available else "unavailable"
        share = available.get(dominant)
        scale = "/".join(
            _fmt(item.get(field))
            for field in ("target_count", "resource_count", "recon_count", "camera_count")
        )
        lines.append(
            f"| {_fmt(item.get('scenario_name'))}/{_fmt(item.get('scenario_version'))} | {scale} | {dominant} | {_fmt(share)} |"
        )

    lines.extend(
        [
            "",
            "## 稳定窗口阶段尾延时",
            "",
            "表内 P50、P95 和最大值先在每个 episode 内按该阶段的单次调用样本计算，再汇总这些 episode 分位在不同 seed 上的分布。表中数值写为“episode 分位均值 [最小值, 最大值]”，不是把 seed P95 当成全部调用样本的合并 P95。",
            "D6 没有原始逐调用样本，因此不计算 pooled quantile。只有 main 明确选定稳定窗口 episode 时，本表才可解释为稳定窗口尾延时。缺失、legacy 空分位和 producer 声明不可用均保持 null，并列出原因。",
            "规模完全取自 episode 合同。5v5 冒烟结果不会被写成 200 对 200 性能验收。",
            "",
            "| scenario/version | scale T/R/Rc/Cam | stage | 分位可用 episodes/seeds | 状态 | episode P50 ms | episode P95 ms | episode max ms | 缺失原因 |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for group in aggregate.get("groups", []):
        scale = "/".join(
            _fmt(group.get(field))
            for field in (
                "target_count",
                "resource_count",
                "recon_count",
                "camera_count",
            )
        )
        for stage, timing in sorted(group.get("stage_timing", {}).items()):
            reasons = timing.get(
                "distribution_unavailability_reason_distribution", {}
            )
            lines.append(
                "| {scenario}/{version} | {scale} | {stage} | {episodes}/{total}, "
                "{seeds}/{seed_total} | {status} | {p50} | {p95} | {maximum} | "
                "{reasons} |".format(
                    scenario=_fmt(group.get("scenario_name")),
                    version=_fmt(group.get("scenario_version")),
                    scale=scale,
                    stage=stage,
                    episodes=timing.get(
                        "distribution_available_episode_count", 0
                    ),
                    total=group.get("episode_count", 0),
                    seeds=timing.get("distribution_available_seed_count", 0),
                    seed_total=group.get("seed_count", 0),
                    status=timing.get(
                        "distribution_availability", "unavailable"
                    ),
                    p50=_fmt_stage_quantile_stat(
                        timing.get("p50_wall_time_ms")
                    ),
                    p95=_fmt_stage_quantile_stat(
                        timing.get("p95_wall_time_ms")
                    ),
                    maximum=_fmt_stage_quantile_stat(
                        timing.get("max_wall_time_ms")
                    ),
                    reasons=(
                        json.dumps(reasons, ensure_ascii=False, sort_keys=True)
                        if reasons
                        else "{}"
                    ),
                )
            )

    lines.extend(
        [
            "",
            "## 失败与可用性",
            "",
            f"Episode 失败/证据质量原因分布：`{json.dumps(aggregate.get('failure_reason_distribution', {}), ensure_ascii=False, sort_keys=True)}`。",
            f"缺失证据原因分布：`{json.dumps(aggregate.get('evidence_unavailability_reason_distribution', {}), ensure_ascii=False, sort_keys=True)}`。",
            "",
            "## 当前限制",
            "",
            "- 当前 producer 的 offline truth label 只含 observation-to-truth 映射，未显式提供 global_track_id-to-truth 映射时，五米接近身份正确性保持 unavailable。",
            "- 当前 schema registry 固定核对 world/bus/scenario/online observation/offline truth，并交叉核对 scenario config schema；旧值继续展示，但 formal acceptance 必须为 false。",
            "- 在线 D2 无真值时，producer IDSW 诊断保持 unavailable；公共 D2 IDSW 只读取经哈希和合同验证的真值隔离制品。严格指标不可用时保留 null 和原始原因，不补写 0。",
            "- D5 `model_missing` 表示确定性几何规则回退，不是学习模型性能证据。",
            "- bundle 未加载时，学习模型 fingerprint/version 保持 null/unavailable；规则路径的 runtime version 不冒充学习模型版本。",
            "- D4 advice 的旧 schema、缺版本、过期 authority/plan/lease、非守恒 quota、非法 projection 或 digest 篡改均 fail closed，不以合法记录子集缩小分母。",
            "- D4 advice 单独不证明控制采用；只有通过完整合同与 summary 一致性审计的 main 消费记录，且 D3 明确应用 hint，才计 control adoption。",
            "- D5 主动视觉必须由命令与 `runtime.camera_command_ack` 复合版本键闭合；命令发布、影子建议、辅助采用和 ACK applied 分层统计。",
            "- 即使辅助动作已 applied 且同一 episode 出现五米接近，没有同 seed 配对控制组时，主动视觉物理归因仍为 null/unavailable。",
            "- 阶段 P50/P95/max 是各 episode 内单次调用分位的跨 seed 描述；没有原始调用样本时，D6 不生成 pooled quantile。",
            "- 报告不把五米接近登记为任务成功；任务成功仍需身份、D4 授权、D7 控制和任务合同的独立证据。",
        ]
    )
    return "\n".join(lines) + "\n"


def _extract_provenance(
    row: dict[str, Any],
    manifest: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None,
    summary: Mapping[str, Any] | None,
) -> None:
    sources = (("scenario_config", config), ("manifest", manifest), ("summary", summary))
    for field in ("episode_id", "scenario_name", "scenario_version", "seed"):
        value, source, reason = _first_explicit_field(sources, field)
        if field == "seed" and reason is None and not (
            _is_int_like(value) and int(value) >= 0
        ):
            reason = "invalid_nonnegative_integer:seed"
        elif field != "seed" and reason is None and not str(value).strip():
            reason = f"explicit_field_empty:{field}"
        if reason is None:
            if field == "seed":
                value = int(value)
            _put_available(row, field, value)
            row[f"{field}_source"] = source
        else:
            _put_unavailable(row, field, reason)

    for field in ("target_count", "resource_count", "recon_count"):
        value, source, reason = _first_explicit_field(
            (("scenario_config", config), ("summary", summary)), field
        )
        if reason is None and _is_int_like(value) and int(value) >= 0:
            _put_available(row, field, int(value))
            row[f"{field}_source"] = source
        else:
            _put_unavailable(
                row,
                field,
                reason or f"invalid_nonnegative_integer:{field}",
            )

    manifest_fields = (
        "git_commit",
        "repository_dirty",
        "config_sha256",
        "world_schema",
        "bus_schema",
        "scenario_schema",
        "online_observation_schema",
        "offline_truth_schema",
        "d1_model_version",
        "d2_model_version",
        "d3_policy_version",
        "d4_policy_version",
        "d5_model_version",
        "d7_model_version",
        "threshold_version",
    )
    for field in manifest_fields:
        value = manifest.get(field) if manifest is not None else None
        invalid = value is None
        if field == "repository_dirty" and value is not None:
            invalid = not isinstance(value, bool)
        elif field != "repository_dirty" and value is not None:
            invalid = not str(value).strip()
        if invalid:
            _put_unavailable(row, field, f"manifest_field_missing:{field}")
        else:
            _put_available(row, field, value)

    if config is not None and config.get("schema_version") is not None:
        _put_available(row, "scenario_config_schema", config["schema_version"])
    else:
        _put_unavailable(row, "scenario_config_schema", "scenario_config_schema_missing")
    _extract_current_schema_contract(row)
    if summary is not None:
        diagnostics = summary.get("module_final_diagnostics")
        if isinstance(diagnostics, Mapping) and diagnostics.get("schema_version") is not None:
            _put_available(row, "module_stack_schema", diagnostics["schema_version"])
        else:
            _put_unavailable(row, "module_stack_schema", "module_stack_schema_missing")
    else:
        _put_unavailable(row, "module_stack_schema", "summary_json_missing")

    _validate_provenance_consistency(row, manifest, config, summary)
    if config is not None:
        canonical = json.dumps(
            config,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        computed = hashlib.sha256(canonical).hexdigest()
        _put_available(row, "computed_config_sha256", computed)
        if manifest is not None and manifest.get("config_sha256") is not None:
            _put_available(
                row,
                "config_hash_match",
                str(manifest["config_sha256"]) == computed,
            )
        else:
            _put_unavailable(row, "config_hash_match", "manifest_config_sha256_missing")
    else:
        _put_unavailable(row, "computed_config_sha256", "scenario_config_json_missing")
        _put_unavailable(row, "config_hash_match", "scenario_config_json_missing")

    if summary is not None and "finite_state" in summary:
        value = summary.get("finite_state")
        if isinstance(value, bool):
            _put_available(row, "finite_state", value)
        else:
            _put_unavailable(
                row,
                "finite_state",
                "summary_finite_state_not_boolean",
            )
    else:
        _put_unavailable(row, "finite_state", "summary_finite_state_missing")


@lru_cache(maxsize=1)
def _current_evaluator_provenance() -> dict[str, Any]:
    """Identify the D6 evaluator independently from episode source provenance."""

    repository = Path(__file__).resolve().parents[3]
    evaluator_scope = repository / "research_modules" / "d6_evaluation_metrics"
    commit = _git_output(repository, "rev-parse", "HEAD")
    dirty_output = _git_output(
        repository,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        "research_modules/d6_evaluation_metrics",
    )
    digest = hashlib.sha256()
    for path in sorted(
        evaluator_scope.joinpath("d6_evaluation_metrics").glob("*.py")
    ):
        digest.update(path.relative_to(repository).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {
        "d6_evaluator_schema_version": (
            SCALABLE_3D_OFFLINE_EVALUATION_SCHEMA_VERSION
        ),
        "d6_evaluator_git_commit": commit,
        "d6_evaluator_repository_dirty": (
            None if dirty_output is None else bool(dirty_output)
        ),
        "d6_evaluator_source_tree_sha256": f"sha256:{digest.hexdigest()}",
    }


def _git_output(repository: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _aggregate_evaluator_provenance(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    def values(field: str) -> list[Any]:
        return sorted(
            {
                row.get(field)
                for row in rows
                if row.get(field) is not None
            },
            key=str,
        )

    return {
        "evaluator_schema_versions": values("d6_evaluator_schema_version"),
        "evaluator_git_commits": values("d6_evaluator_git_commit"),
        "evaluator_repository_dirty_values": values(
            "d6_evaluator_repository_dirty"
        ),
        "evaluator_source_tree_sha256_values": values(
            "d6_evaluator_source_tree_sha256"
        ),
        "episode_source_git_commits": values("episode_source_git_commit"),
        "episode_source_repository_dirty_values": values(
            "episode_source_repository_dirty"
        ),
        "source_and_evaluator_provenance_separated": True,
    }


def _extract_learning_runtime_metrics(
    row: dict[str, Any],
    manifest: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None,
    summary: Mapping[str, Any] | None,
) -> None:
    config_metadata = config.get("metadata") if isinstance(config, Mapping) else None
    config_runtime = (
        config_metadata.get("learning_runtime")
        if isinstance(config_metadata, Mapping)
        else None
    )
    summary_diagnostics = (
        summary.get("module_final_diagnostics")
        if isinstance(summary, Mapping)
        else None
    )
    summary_runtime = (
        summary_diagnostics.get("learning_runtime")
        if isinstance(summary_diagnostics, Mapping)
        else None
    )
    config_runtime = config_runtime if isinstance(config_runtime, Mapping) else None
    summary_runtime = summary_runtime if isinstance(summary_runtime, Mapping) else None

    if config_runtime is not None and summary_runtime is not None:
        consistent = _json_ready(config_runtime) == _json_ready(summary_runtime)
        _put_available(row, "learning_runtime_metadata_consistent", consistent)
        if not consistent:
            row["_failure_reasons"].append("learning_runtime_metadata_mismatch")
        runtime = config_runtime
        source = "scenario_config.metadata.learning_runtime"
    elif config_runtime is not None:
        _put_unavailable(
            row,
            "learning_runtime_metadata_consistent",
            "summary_learning_runtime_metadata_missing",
        )
        runtime = config_runtime
        source = "scenario_config.metadata.learning_runtime"
    elif summary_runtime is not None:
        _put_unavailable(
            row,
            "learning_runtime_metadata_consistent",
            "scenario_config_learning_runtime_metadata_missing",
        )
        runtime = summary_runtime
        source = "summary.module_final_diagnostics.learning_runtime"
    else:
        _put_unavailable(
            row,
            "learning_runtime_metadata_consistent",
            "learning_runtime_metadata_missing",
        )
        _put_unavailable(
            row,
            "learning_runtime_schema_version",
            "learning_runtime_metadata_missing",
        )
        _put_unavailable(
            row,
            "learning_runtime_metadata_source",
            "learning_runtime_metadata_missing",
        )
        for module in _LEARNING_MODULE_VERSION_FIELDS:
            _put_learning_module_unavailable(
                row, module, "learning_runtime_metadata_missing"
            )
        return

    _put_available(row, "learning_runtime_metadata_source", source)
    schema = runtime.get("schema_version")
    if not isinstance(schema, str) or not schema.strip():
        _put_unavailable(
            row,
            "learning_runtime_schema_version",
            "learning_runtime_schema_version_missing",
        )
        reason = "learning_runtime_schema_version_missing"
    else:
        _put_available(row, "learning_runtime_schema_version", schema)
        reason = (
            None
            if schema == _LEARNING_RUNTIME_SCHEMA
            else f"unsupported_learning_runtime_schema:{schema}"
        )
    if reason is not None:
        for module in _LEARNING_MODULE_VERSION_FIELDS:
            _put_learning_module_unavailable(row, module, reason)
        return

    for module, version_field in _LEARNING_MODULE_VERSION_FIELDS.items():
        diagnostics = runtime.get(module)
        if not isinstance(diagnostics, Mapping):
            _put_learning_module_unavailable(
                row, module, f"learning_runtime_module_metadata_missing:{module}"
            )
            continue
        _extract_learning_module_metrics(
            row,
            module=module,
            diagnostics=diagnostics,
            version_field=version_field,
            manifest=manifest,
            config=config,
        )


def _extract_learning_module_metrics(
    row: dict[str, Any],
    *,
    module: str,
    diagnostics: Mapping[str, Any],
    version_field: str,
    manifest: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None,
) -> None:
    prefix = f"{module}_learning"
    for field in ("requested_mode", "effective_mode"):
        value = diagnostics.get(field)
        if isinstance(value, str) and value.strip():
            _put_available(row, f"{prefix}_{field}", value.strip())
        else:
            _put_unavailable(
                row,
                f"{prefix}_{field}",
                f"learning_runtime_field_missing_or_invalid:{module}:{field}",
            )
    for field in ("bundle_requested", "bundle_loaded"):
        value = diagnostics.get(field)
        if isinstance(value, bool):
            _put_available(row, f"{prefix}_{field}", value)
        else:
            _put_unavailable(
                row,
                f"{prefix}_{field}",
                f"learning_runtime_field_missing_or_invalid:{module}:{field}",
            )

    if "fallback_reason" not in diagnostics:
        _put_unavailable(
            row,
            f"{prefix}_fallback_reason",
            f"learning_runtime_field_missing:{module}:fallback_reason",
        )
    else:
        fallback = diagnostics.get("fallback_reason")
        if fallback is None or (isinstance(fallback, str) and fallback.strip()):
            _put_available(row, f"{prefix}_fallback_reason", fallback)
        else:
            _put_unavailable(
                row,
                f"{prefix}_fallback_reason",
                f"learning_runtime_field_invalid:{module}:fallback_reason",
            )

    fingerprint = diagnostics.get("model_fingerprint")
    if fingerprint is None:
        _put_unavailable(
            row,
            f"{prefix}_model_fingerprint",
            f"producer_declared_model_fingerprint_unavailable:{module}",
        )
    elif isinstance(fingerprint, str) and re.fullmatch(r"[0-9a-fA-F]{64}", fingerprint):
        fingerprint = fingerprint.lower()
        _put_available(row, f"{prefix}_model_fingerprint", fingerprint)
    else:
        _put_unavailable(
            row,
            f"{prefix}_model_fingerprint",
            f"learning_model_fingerprint_invalid:{module}",
        )
        row["_failure_reasons"].append(f"learning_model_fingerprint_invalid:{module}")

    version_values = [
        str(source[version_field]).strip()
        for source in (config, manifest)
        if isinstance(source, Mapping)
        and source.get(version_field) is not None
        and str(source[version_field]).strip()
    ]
    if not version_values:
        _put_unavailable(
            row,
            f"{prefix}_runtime_version",
            f"learning_runtime_version_missing:{module}:{version_field}",
        )
    elif any(value != version_values[0] for value in version_values[1:]):
        _put_unavailable(
            row,
            f"{prefix}_runtime_version",
            f"learning_runtime_version_mismatch:{module}:{version_field}",
        )
        row["_failure_reasons"].append(
            f"learning_runtime_version_mismatch:{module}:{version_field}"
        )
    else:
        _put_available(row, f"{prefix}_runtime_version", version_values[0])

    loaded = row.get(f"{prefix}_bundle_loaded")
    loaded_available = row.get(f"{prefix}_bundle_loaded_availability") == "available"
    fingerprint_available = (
        row.get(f"{prefix}_model_fingerprint_availability") == "available"
    )
    version_available = row.get(f"{prefix}_runtime_version_availability") == "available"
    if loaded_available and loaded is False:
        _put_unavailable(
            row,
            f"{prefix}_model_version",
            f"learning_bundle_not_loaded:{module}",
        )
    elif loaded_available and loaded is True and not fingerprint_available:
        _put_unavailable(
            row,
            f"{prefix}_model_version",
            f"loaded_learning_bundle_fingerprint_unavailable:{module}",
        )
        row["_failure_reasons"].append(
            f"loaded_learning_bundle_fingerprint_unavailable:{module}"
        )
    elif loaded_available and loaded is True and not version_available:
        _put_unavailable(
            row,
            f"{prefix}_model_version",
            f"loaded_learning_bundle_version_unavailable:{module}",
        )
    elif loaded_available and loaded is True:
        runtime_version = str(row[f"{prefix}_runtime_version"])
        if str(row[f"{prefix}_model_fingerprint"])[:12] not in runtime_version:
            _put_unavailable(
                row,
                f"{prefix}_model_version",
                f"learning_model_version_fingerprint_mismatch:{module}",
            )
            row["_failure_reasons"].append(
                f"learning_model_version_fingerprint_mismatch:{module}"
            )
        else:
            _put_available(row, f"{prefix}_model_version", runtime_version)
    else:
        _put_unavailable(
            row,
            f"{prefix}_model_version",
            f"learning_bundle_loaded_availability_missing:{module}",
        )

    if module == "d4":
        unseen = diagnostics.get("formal_unseen_seed_count")
        if _is_int_like(unseen) and int(unseen) >= 0:
            _put_available(row, "d4_learning_formal_unseen_seed_count", int(unseen))
        else:
            _put_unavailable(
                row,
                "d4_learning_formal_unseen_seed_count",
                "learning_runtime_field_missing_or_invalid:d4:formal_unseen_seed_count",
            )


def _put_learning_module_unavailable(
    row: dict[str, Any], module: str, reason: str
) -> None:
    prefix = f"{module}_learning"
    for field in (
        "requested_mode",
        "effective_mode",
        "bundle_requested",
        "bundle_loaded",
        "fallback_reason",
        "model_fingerprint",
        "runtime_version",
        "model_version",
    ):
        _put_unavailable(row, f"{prefix}_{field}", reason)
    if module == "d4":
        _put_unavailable(row, "d4_learning_formal_unseen_seed_count", reason)


def _extract_online_truth_audit(
    row: dict[str, Any],
    records: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any] | None,
    *,
    online_unavailable_reason: str | None,
) -> None:
    if summary is not None and "online_truth_use_count" in summary:
        value = summary.get("online_truth_use_count")
        if _is_int_like(value) and int(value) >= 0:
            _put_available(row, "online_truth_use_count", int(value))
        else:
            _put_unavailable(
                row,
                "online_truth_use_count",
                "summary_online_truth_use_count_invalid",
            )
    else:
        _put_unavailable(
            row,
            "online_truth_use_count",
            "summary_online_truth_use_count_missing",
        )
    diagnostics = summary.get("module_final_diagnostics") if summary is not None else None
    if isinstance(diagnostics, Mapping) and "online_truth_use_count" in diagnostics:
        diagnostic_count = diagnostics.get("online_truth_use_count")
        if not (_is_int_like(diagnostic_count) and int(diagnostic_count) >= 0):
            row["_failure_reasons"].append(
                "module_diagnostics_online_truth_use_count_invalid"
            )
        elif (
            row.get("online_truth_use_count_availability") == "available"
            and int(diagnostic_count) != int(row["online_truth_use_count"])
        ):
            row["_failure_reasons"].append("online_truth_use_count_mismatch")
    if online_unavailable_reason is None:
        violations = sum(_count_forbidden_online_fields(record) for record in records)
        _put_available(row, "online_truth_field_violation_count", violations)
        _put_available(row, "online_record_count", len(records))
        _put_available(
            row,
            "online_schema_versions_json",
            dict(
                sorted(
                    Counter(
                        str(record.get("schema_version", "unavailable"))
                        for record in records
                    ).items()
                )
            ),
        )
    else:
        _put_unavailable(
            row,
            "online_truth_field_violation_count",
            online_unavailable_reason,
        )
        _put_unavailable(row, "online_record_count", online_unavailable_reason)
        _put_unavailable(row, "online_schema_versions_json", online_unavailable_reason)


def _extract_track_metrics(
    row: dict[str, Any],
    records: Sequence[Mapping[str, Any]],
    *,
    module: str,
) -> None:
    topic = f"modules.{module}." + (
        "fused_tracks" if module == "d1" else "associated_tracks"
    )
    record = _latest_topic(records, topic)
    fields = (
        f"{module}_speed_p50_mps",
        f"{module}_speed_p90_mps",
        f"{module}_speed_max_mps",
        f"{module}_velocity_covariance_trace_p50",
        f"{module}_velocity_covariance_trace_p90",
        f"{module}_velocity_covariance_trace_max",
    )
    if record is None:
        _put_unavailable(row, f"{module}_track_count", f"{module}_publication_missing")
        for field in fields:
            _put_unavailable(row, field, f"{module}_publication_missing")
        return
    payload = _payload(record)
    tracks = payload.get("tracks")
    declared = payload.get("track_count")
    if isinstance(tracks, list):
        count = len(tracks)
        _put_available(row, f"{module}_track_count", count)
        if _is_int_like(declared) and int(declared) != count:
            row["_failure_reasons"].append(f"{module}_track_count_mismatch")
    elif _is_int_like(declared) and int(declared) >= 0:
        count = int(declared)
        _put_available(row, f"{module}_track_count", count)
        for field in fields:
            _put_unavailable(row, field, f"{module}_track_list_missing")
        return
    else:
        _put_unavailable(row, f"{module}_track_count", f"{module}_track_count_missing")
        for field in fields:
            _put_unavailable(row, field, f"{module}_track_list_missing")
        return

    if not tracks:
        for field in fields:
            _put_unavailable(row, field, f"{module}_no_tracks")
        return

    speeds: list[float] = []
    velocity_traces: list[float] = []
    speed_reason: str | None = None
    covariance_reason: str | None = None
    for track in tracks:
        if not isinstance(track, Mapping):
            speed_reason = f"{module}_track_not_object"
            covariance_reason = speed_reason
            break
        state = track.get("state_ned")
        if not isinstance(state, Sequence) or isinstance(state, (str, bytes)) or len(state) < 6:
            speed_reason = f"{module}_track_state_missing_or_short"
        elif not all(_is_finite_number(value) for value in state[3:6]):
            speed_reason = f"{module}_track_velocity_nonfinite"
        else:
            speeds.append(float(np.linalg.norm(np.asarray(state[3:6], dtype=float))))

        covariance = track.get("covariance")
        try:
            matrix = np.asarray(covariance, dtype=float)
        except (TypeError, ValueError):
            covariance_reason = f"{module}_velocity_covariance_invalid"
        else:
            if (
                matrix.ndim != 2
                or matrix.shape[0] < 6
                or matrix.shape[1] < 6
                or not np.all(np.isfinite(matrix))
            ):
                covariance_reason = f"{module}_velocity_covariance_missing_or_nonfinite"
            else:
                velocity_traces.append(float(np.trace(matrix[3:6, 3:6])))
    if speed_reason is None and len(speeds) == len(tracks):
        _put_distribution(row, f"{module}_speed", speeds, unit_suffix="_mps")
    else:
        for field in fields[:3]:
            _put_unavailable(row, field, speed_reason or f"{module}_track_velocity_incomplete")
    if covariance_reason is None and len(velocity_traces) == len(tracks):
        _put_distribution(
            row,
            f"{module}_velocity_covariance_trace",
            velocity_traces,
            unit_suffix="",
        )
    else:
        for field in fields[3:]:
            _put_unavailable(
                row,
                field,
                covariance_reason or f"{module}_velocity_covariance_incomplete",
            )


def _extract_d2_online_producer_id_switch(
    row: dict[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    record = _latest_topic(records, "modules.d2.associated_tracks")
    if record is None:
        _put_unavailable(
            row,
            "d2_online_producer_id_switch_count",
            "d2_publication_missing",
        )
        return
    payload = _payload(record)
    available = payload.get("id_switch_count_available")
    value = payload.get("id_switch_count")
    if available is True and _is_int_like(value) and int(value) >= 0:
        _put_available(row, "d2_online_producer_id_switch_count", int(value))
    elif available is False:
        _put_unavailable(
            row,
            "d2_online_producer_id_switch_count",
            "producer_declared_id_switch_count_unavailable",
        )
    elif "id_switch_count_available" not in payload:
        _put_unavailable(
            row,
            "d2_online_producer_id_switch_count",
            "d2_id_switch_availability_field_missing",
        )
    else:
        _put_unavailable(
            row,
            "d2_online_producer_id_switch_count",
            "d2_id_switch_count_invalid",
        )


def _extract_d2_strict_offline_id_switch(
    row: dict[str, Any], episode_dir: Path
) -> None:
    evidence = load_strict_offline_id_switch(
        episode_dir,
        expected_context={
            field: row.get(field)
            for field in (
                "episode_id",
                "scenario_name",
                "scenario_version",
                "seed",
                "target_count",
                "resource_count",
                "recon_count",
                "camera_count",
            )
        },
    )
    row["d2_id_switch_count_semantics"] = evidence.semantics
    row["d2_id_switch_count_source_artifact"] = evidence.source_artifact
    row["d2_strict_identity_verification_mode"] = evidence.verification_mode
    row["d2_strict_identity_truth_isolation_verified"] = (
        evidence.truth_isolation_verified
    )
    row["d2_strict_identity_id_switch_backfilled"] = evidence.strict_backfilled
    row["d2_truth_isolated_manifest_sha256"] = evidence.truth_manifest_sha256
    row["d2_truth_isolated_episode_record_sha256"] = (
        evidence.episode_record_sha256
    )
    row["d2_offline_identity_manifest_sha256"] = (
        evidence.identity_manifest_sha256
    )
    row["d2_offline_identity_evaluation_sha256"] = (
        evidence.identity_evaluation_sha256
    )
    _put_available(
        row,
        "d2_strict_identity_artifact_verified",
        evidence.artifact_verified,
    )
    if evidence.available:
        _put_available(row, "d2_id_switch_count", evidence.value)
    else:
        _put_unavailable(
            row,
            "d2_id_switch_count",
            evidence.unavailable_reason
            or "strict_offline_id_switch_metric_unavailable",
        )


def _extract_d3_metrics(
    row: dict[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    current_d2_count: int | None = None
    timeline: list[dict[str, Any]] = []
    for record in records:
        topic = str(record.get("topic", ""))
        payload = _payload(record)
        if topic == "modules.d2.associated_tracks":
            tracks = payload.get("tracks")
            declared = payload.get("track_count")
            if isinstance(tracks, list):
                current_d2_count = len(tracks)
            elif _is_int_like(declared) and int(declared) >= 0:
                current_d2_count = int(declared)
        elif topic == "modules.d3.assignment_plan":
            timeline.append(_d3_snapshot(payload, current_d2_count))

    fields = (
        "d3_current_track_count",
        "d3_plan_target_count",
        "d3_assignment_count",
        "d3_assigned_target_count",
        "d3_plan_coverage_rate",
        "d3_backlog_count",
        "d3_min_dwell_hold_event_count",
        "d3_min_dwell_backlog_max",
    )
    if not timeline:
        for field in fields:
            _put_unavailable(row, field, "d3_publication_missing")
        for field in (
            "d3_hysteresis_state",
            "d3_hysteresis_reason",
            "d3_hysteresis_reasons_json",
        ):
            _put_unavailable(row, field, "d3_publication_missing")
        return

    latest = timeline[-1]
    for field in fields[:6]:
        value = latest.get(field)
        reason = latest.get(f"{field}_unavailable_reason")
        if reason is None:
            _put_available(row, field, value)
        else:
            _put_unavailable(row, field, reason)

    hysteresis_auditable = all(
        "hysteresis_state" in item["metadata"] for item in timeline
    )
    min_dwell_rows = [item for item in timeline if item["min_dwell_hold"]]
    if hysteresis_auditable:
        _put_available(row, "d3_min_dwell_hold_event_count", len(min_dwell_rows))
    else:
        _put_unavailable(
            row,
            "d3_min_dwell_hold_event_count",
            "d3_hysteresis_state_missing",
        )
    if min_dwell_rows and hysteresis_auditable:
        backlogs = [
            item["d3_backlog_count"]
            for item in min_dwell_rows
            if _is_int_like(item.get("d3_backlog_count"))
        ]
        if len(backlogs) == len(min_dwell_rows):
            _put_available(row, "d3_min_dwell_backlog_max", max(backlogs))
        else:
            _put_unavailable(
                row,
                "d3_min_dwell_backlog_max",
                "d3_min_dwell_hold_backlog_unavailable",
            )
    elif hysteresis_auditable:
        _put_available(row, "d3_min_dwell_backlog_max", 0)
    else:
        _put_unavailable(
            row,
            "d3_min_dwell_backlog_max",
            "d3_hysteresis_state_missing",
        )

    metadata = latest["metadata"]
    for field, key in (
        ("d3_hysteresis_state", "hysteresis_state"),
        ("d3_hysteresis_reason", "hysteresis_reason"),
        ("d3_hysteresis_dwell_time_s", "hysteresis_dwell_time_s"),
        ("d3_hysteresis_min_dwell_s", "hysteresis_min_dwell_s"),
    ):
        if key in metadata and metadata[key] is not None:
            _put_available(row, field, metadata[key])
        else:
            _put_unavailable(row, field, f"d3_metadata_missing:{key}")
    reason_counter: Counter[str] = Counter()
    for item in timeline:
        reason_counter.update(item["hysteresis_reasons"])
    if hysteresis_auditable:
        _put_available(
            row,
            "d3_hysteresis_reasons_json",
            dict(sorted(reason_counter.items())),
        )
    else:
        _put_unavailable(
            row,
            "d3_hysteresis_reasons_json",
            "d3_hysteresis_state_missing",
        )
    row["d3_timeline_publication_count"] = len(timeline)


def _d3_snapshot(payload: Mapping[str, Any], current_d2_count: int | None) -> dict[str, Any]:
    metadata = payload.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    current_count = current_d2_count
    candidate_ids = metadata.get("hysteresis_candidate_target_ids")
    if current_count is None and isinstance(candidate_ids, list):
        current_count = len(candidate_ids)

    assignments = payload.get("assignments")
    declared_assignment_count = payload.get("assignment_count")
    assigned_ids: list[str] | None = None
    if isinstance(assignments, list) and all(isinstance(item, Mapping) for item in assignments):
        raw_ids = [item.get("global_track_id") for item in assignments]
        if all(value is not None and str(value) for value in raw_ids):
            assigned_ids = [str(value) for value in raw_ids]
    assignment_count = (
        len(assignments)
        if isinstance(assignments, list)
        else (
            int(declared_assignment_count)
            if _is_int_like(declared_assignment_count) and int(declared_assignment_count) >= 0
            else None
        )
    )
    plan_target_count = payload.get("target_count")
    if not (_is_int_like(plan_target_count) and int(plan_target_count) >= 0):
        plan_target_count = None
    else:
        plan_target_count = int(plan_target_count)

    unique_assigned = None if assigned_ids is None else len(set(assigned_ids))
    if current_count is not None and unique_assigned is not None and current_count > 0:
        coverage = unique_assigned / current_count
    else:
        coverage = None
    pending = metadata.get("hysteresis_pending_new_target_ids")
    if isinstance(pending, list):
        backlog = len({str(value) for value in pending})
    elif current_count is not None and unique_assigned is not None:
        backlog = max(0, current_count - unique_assigned)
    else:
        backlog = None

    raw_reasons = metadata.get("hysteresis_reasons")
    reasons: tuple[str, ...]
    if isinstance(raw_reasons, Sequence) and not isinstance(raw_reasons, (str, bytes)):
        reasons = tuple(str(value) for value in raw_reasons if str(value))
    elif metadata.get("hysteresis_reason") is not None:
        reasons = (str(metadata["hysteresis_reason"]),)
    else:
        reasons = ()
    min_dwell_hold = str(metadata.get("hysteresis_state", "")).lower() == "held" and (
        "min_dwell_not_met" in reasons or metadata.get("hysteresis_dwell_ok") is False
    )
    return {
        "d3_current_track_count": current_count,
        "d3_current_track_count_unavailable_reason": (
            None if current_count is not None else "d3_current_d2_track_count_unavailable"
        ),
        "d3_plan_target_count": plan_target_count,
        "d3_plan_target_count_unavailable_reason": (
            None if plan_target_count is not None else "d3_plan_target_count_missing"
        ),
        "d3_assignment_count": assignment_count,
        "d3_assignment_count_unavailable_reason": (
            None if assignment_count is not None else "d3_assignment_count_missing"
        ),
        "d3_assigned_target_count": unique_assigned,
        "d3_assigned_target_count_unavailable_reason": (
            None if unique_assigned is not None else "d3_assignment_target_ids_missing"
        ),
        "d3_plan_coverage_rate": coverage,
        "d3_plan_coverage_rate_unavailable_reason": (
            None
            if coverage is not None
            else "d3_current_tracks_or_assignment_target_ids_unavailable"
        ),
        "d3_backlog_count": backlog,
        "d3_backlog_count_unavailable_reason": (
            None if backlog is not None else "d3_backlog_inputs_unavailable"
        ),
        "metadata": metadata,
        "hysteresis_reasons": reasons,
        "min_dwell_hold": min_dwell_hold,
    }


def _extract_d3_learning_metrics(
    row: dict[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    d3_records = [
        record
        for record in records
        if record.get("topic") == "modules.d3.assignment_plan"
    ]
    fields = (
        "d3_learning_publication_count",
        "d3_learning_applied_count",
        "d3_learning_fallback_event_count",
        "d3_learning_mode_distribution_json",
        "d3_learning_fallback_reason_distribution_json",
        "d3_online_learning_mode",
        "d3_online_learning_applied",
        "d3_online_learning_bundle_loaded",
        "d3_online_learning_fallback_reason",
    )
    if not d3_records:
        for field in fields:
            _put_unavailable(row, field, "d3_publication_missing")
        return

    metadata_rows = []
    for record in d3_records:
        metadata = _payload(record).get("metadata")
        metadata_rows.append(dict(metadata) if isinstance(metadata, Mapping) else {})
    learning_rows = [
        metadata
        for metadata in metadata_rows
        if any(str(key).startswith("learning_") for key in metadata)
    ]
    _put_available(row, "d3_learning_publication_count", len(learning_rows))
    if not learning_rows:
        for field in fields[1:]:
            _put_unavailable(row, field, "d3_learning_metadata_missing")
        return

    required = (
        "learning_mode",
        "learning_applied",
        "learning_bundle_loaded",
        "learning_fallback_reason",
    )
    complete = all(all(field in metadata for field in required) for metadata in learning_rows)
    latest = learning_rows[-1]
    for output_field, source_field, validator in (
        ("d3_online_learning_mode", "learning_mode", lambda value: isinstance(value, str) and bool(value.strip())),
        ("d3_online_learning_applied", "learning_applied", lambda value: isinstance(value, bool)),
        ("d3_online_learning_bundle_loaded", "learning_bundle_loaded", lambda value: isinstance(value, bool)),
    ):
        value = latest.get(source_field)
        if validator(value):
            _put_available(row, output_field, value)
        else:
            _put_unavailable(
                row,
                output_field,
                f"d3_learning_field_missing_or_invalid:{source_field}",
            )
    if "learning_fallback_reason" in latest:
        fallback = latest.get("learning_fallback_reason")
        if fallback is None or (isinstance(fallback, str) and fallback.strip()):
            _put_available(row, "d3_online_learning_fallback_reason", fallback)
        else:
            _put_unavailable(
                row,
                "d3_online_learning_fallback_reason",
                "d3_learning_field_invalid:learning_fallback_reason",
            )
    else:
        _put_unavailable(
            row,
            "d3_online_learning_fallback_reason",
            "d3_learning_field_missing:learning_fallback_reason",
        )

    if not complete:
        for field in (
            "d3_learning_applied_count",
            "d3_learning_fallback_event_count",
            "d3_learning_mode_distribution_json",
            "d3_learning_fallback_reason_distribution_json",
        ):
            _put_unavailable(row, field, "d3_learning_metadata_incomplete")
        return
    modes = [metadata["learning_mode"] for metadata in learning_rows]
    applied = [metadata["learning_applied"] for metadata in learning_rows]
    bundle_loaded = [metadata["learning_bundle_loaded"] for metadata in learning_rows]
    fallbacks = [metadata["learning_fallback_reason"] for metadata in learning_rows]
    if not all(isinstance(value, str) and value.strip() for value in modes):
        _put_unavailable(
            row,
            "d3_learning_mode_distribution_json",
            "d3_learning_mode_invalid",
        )
    else:
        _put_available(
            row,
            "d3_learning_mode_distribution_json",
            dict(sorted(Counter(str(value) for value in modes).items())),
        )
    if not all(isinstance(value, bool) for value in applied):
        _put_unavailable(row, "d3_learning_applied_count", "d3_learning_applied_invalid")
    else:
        _put_available(row, "d3_learning_applied_count", sum(applied))
    if not all(isinstance(value, bool) for value in bundle_loaded):
        row["_failure_reasons"].append("d3_learning_bundle_loaded_invalid")
    elif (
        row.get("d3_learning_bundle_loaded_availability") == "available"
        and any(value != row["d3_learning_bundle_loaded"] for value in bundle_loaded)
    ):
        row["_failure_reasons"].append(
            "d3_online_learning_bundle_loaded_runtime_mismatch"
        )
    if not all(
        value is None or (isinstance(value, str) and value.strip())
        for value in fallbacks
    ):
        _put_unavailable(
            row,
            "d3_learning_fallback_event_count",
            "d3_learning_fallback_reason_invalid",
        )
        _put_unavailable(
            row,
            "d3_learning_fallback_reason_distribution_json",
            "d3_learning_fallback_reason_invalid",
        )
    else:
        counter = Counter(str(value) for value in fallbacks if value is not None)
        _put_available(row, "d3_learning_fallback_event_count", sum(counter.values()))
        _put_available(
            row,
            "d3_learning_fallback_reason_distribution_json",
            dict(sorted(counter.items())),
        )


def _extract_d4_metrics(
    row: dict[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    record = _latest_topic(records, "modules.d4.regional_failover")
    fields = (
        "d4_region_count",
        "d4_execution_allowed_region_count",
        "d4_fail_closed_region_count",
        "d4_lease_expired_region_count",
        "d4_commit_count",
    )
    if record is None:
        for field in fields:
            _put_unavailable(row, field, "d4_publication_missing")
        for field in (
            "d4_owner_records_json",
            "d4_owner_layer_distribution_json",
            "d4_owner_node_ids_json",
            "d4_owner_epochs_json",
            "d4_owner_lease_expires_at_s_json",
            "d4_commit_state_distribution_json",
            "d4_fail_closed_reasons_json",
        ):
            _put_unavailable(row, field, "d4_publication_missing")
        return
    payload = _payload(record)
    regions = payload.get("regions")
    if not isinstance(regions, list) or not all(isinstance(item, Mapping) for item in regions):
        for field in fields:
            _put_unavailable(row, field, "d4_regions_missing_or_invalid")
        return

    timestamp = payload.get("timestamp_s", record.get("timestamp"))
    timestamp_value = float(timestamp) if _is_finite_number(timestamp) else None
    owner_records: list[dict[str, Any]] = []
    layer_counter: Counter[str] = Counter()
    nodes: set[str] = set()
    epochs: list[int] = []
    leases: list[float] = []
    commit_states: Counter[str] = Counter()
    fail_reasons: Counter[str] = Counter()
    execution_allowed = 0
    fail_closed = 0
    lease_expired = 0
    commit_count = 0
    complete_owner_evidence = True
    execution_fields_complete = True
    fail_closed_fields_complete = True
    commit_fields_complete = True
    for region in regions:
        ownership = region.get("ownership")
        ownership = ownership if isinstance(ownership, Mapping) else {}
        layer = ownership.get("owner_layer", region.get("selected_layer"))
        node = ownership.get("owner_id", region.get("selected_secondary_id"))
        epoch = ownership.get("epoch")
        lease = ownership.get("lease_expires_at_s")
        owner_record = {
            "region_id": region.get("region_id"),
            "owner_layer": layer,
            "owner_node_id": node,
            "owner_node_availability": (
                "available" if node is not None else "unavailable"
            ),
            "owner_node_unavailable_reason": (
                None if node is not None else "region_has_no_active_owner_node"
            ),
            "epoch": epoch,
            "lease_expires_at_s": lease,
            "active": ownership.get("active"),
        }
        owner_records.append(owner_record)
        if layer is None:
            complete_owner_evidence = False
        else:
            layer_counter[str(layer)] += 1
        if node is not None:
            nodes.add(str(node))
        if _is_int_like(epoch) and int(epoch) >= 0:
            epochs.append(int(epoch))
        else:
            complete_owner_evidence = False
        if _is_finite_number(lease):
            lease_value = float(lease)
            leases.append(lease_value)
            if timestamp_value is not None and timestamp_value >= lease_value:
                lease_expired += 1
        else:
            complete_owner_evidence = False

        if "execution_allowed" not in region or not isinstance(
            region.get("execution_allowed"), bool
        ):
            execution_fields_complete = False
        elif region.get("execution_allowed") is True:
            execution_allowed += 1
        if "fail_closed" not in region or not isinstance(region.get("fail_closed"), bool):
            fail_closed_fields_complete = False
        elif region.get("fail_closed") is True:
            fail_closed += 1
            region_fail_reasons: set[str] = set()
            reason = region.get("reason")
            if reason is not None:
                region_fail_reasons.add(str(reason))
            rejection_reasons = region.get("rejection_reasons")
            if isinstance(rejection_reasons, list):
                region_fail_reasons.update(
                    str(value) for value in rejection_reasons if str(value)
                )
            if reason is None and not rejection_reasons:
                region_fail_reasons.add("d4_fail_closed_reason_missing")
            fail_reasons.update(region_fail_reasons)
        commits = region.get("coalition_commits")
        if isinstance(commits, list):
            for commit in commits:
                if not isinstance(commit, Mapping):
                    continue
                commit_count += 1
                state = commit.get("state")
                commit_states[str(state) if state is not None else "unavailable"] += 1
                commit_lease = commit.get("lease_expires_at_s")
                if (
                    timestamp_value is not None
                    and _is_finite_number(commit_lease)
                    and timestamp_value >= float(commit_lease)
                ):
                    fail_reasons["coalition_commit_lease_expired"] += 1
        else:
            commit_fields_complete = False

    _put_available(row, "d4_region_count", len(regions))
    if execution_fields_complete:
        _put_available(row, "d4_execution_allowed_region_count", execution_allowed)
    else:
        _put_unavailable(
            row,
            "d4_execution_allowed_region_count",
            "d4_region_execution_allowed_field_missing",
        )
    if fail_closed_fields_complete:
        _put_available(row, "d4_fail_closed_region_count", fail_closed)
    else:
        _put_unavailable(
            row,
            "d4_fail_closed_region_count",
            "d4_region_fail_closed_field_missing",
        )
    if timestamp_value is not None and len(leases) == len(regions):
        _put_available(row, "d4_lease_expired_region_count", lease_expired)
    else:
        _put_unavailable(
            row,
            "d4_lease_expired_region_count",
            "d4_timestamp_or_region_lease_missing",
        )
    if commit_fields_complete:
        _put_available(row, "d4_commit_count", commit_count)
        _put_available(
            row,
            "d4_commit_state_distribution_json",
            dict(sorted(commit_states.items())),
        )
    else:
        _put_unavailable(row, "d4_commit_count", "d4_coalition_commits_field_missing")
        _put_unavailable(
            row,
            "d4_commit_state_distribution_json",
            "d4_coalition_commits_field_missing",
        )
    _put_available(row, "d4_fail_closed_reasons_json", dict(sorted(fail_reasons.items())))
    if complete_owner_evidence:
        _put_available(row, "d4_owner_records_json", owner_records)
        _put_available(
            row,
            "d4_owner_layer_distribution_json",
            dict(sorted(layer_counter.items())),
        )
        _put_available(row, "d4_owner_node_ids_json", sorted(nodes))
        _put_available(row, "d4_owner_epochs_json", sorted(set(epochs)))
        _put_available(row, "d4_owner_lease_expires_at_s_json", sorted(set(leases)))
    else:
        _put_unavailable(row, "d4_owner_records_json", "d4_owner_contract_fields_missing")
        _put_unavailable(
            row,
            "d4_owner_layer_distribution_json",
            "d4_owner_contract_fields_missing",
        )
        _put_unavailable(row, "d4_owner_node_ids_json", "d4_owner_contract_fields_missing")
        _put_unavailable(row, "d4_owner_epochs_json", "d4_owner_contract_fields_missing")
        _put_unavailable(
            row,
            "d4_owner_lease_expires_at_s_json",
            "d4_owner_contract_fields_missing",
        )
    row["d4_latest_timestamp_s"] = timestamp_value


def _extract_d4_region_advice_metrics(
    row: dict[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    advice_records = [
        record for record in records if record.get("topic") == _D4_REGION_ADVICE_TOPIC
    ]
    _put_available(row, "d4_advice_publication_count", len(advice_records))
    _put_unavailable(
        row,
        "d4_advice_control_adoption_count",
        "d4_advice_schema_has_no_control_adoption_evidence",
    )
    if not advice_records:
        _put_available(row, "d4_advice_valid_publication_count", 0)
        _put_available(row, "d4_advice_invalid_publication_count", 0)
        _put_available(row, "d4_advice_invalid_reason_distribution_json", {})
        _put_available(row, "d4_advice_version_evidence_issue_reasons_json", {})
        requested = row.get("d4_learning_requested_mode")
        requested_available = (
            row.get("d4_learning_requested_mode_availability") == "available"
        )
        if requested_available and requested == "disabled":
            _put_available(row, "d4_advice_evidence_status", "not_expected_disabled")
            missing_reason = "d4_advice_not_published_for_disabled_runtime"
        else:
            _put_available(row, "d4_advice_evidence_status", "missing")
            missing_reason = "d4_region_resource_advice_missing"
            if requested_available and requested != "disabled":
                row["_failure_reasons"].append(
                    "d4_advice_missing_for_requested_runtime"
                )
        for field in _d4_advice_substantive_fields():
            _put_unavailable(row, field, missing_reason)
        return

    audits: list[dict[str, Any]] = []
    latest_formal: Mapping[str, Any] | None = None
    for record in records:
        topic = record.get("topic")
        if topic == "modules.d4.regional_failover":
            latest_formal = _payload(record)
        elif topic == _D4_REGION_ADVICE_TOPIC:
            audits.append(
                _audit_d4_advice_publication(
                    record,
                    row=row,
                    latest_formal=latest_formal,
                )
            )

    invalid_reasons = Counter(
        reason for audit in audits for reason in audit["invalid_reasons"]
    )
    version_reasons = Counter(
        reason
        for audit in audits
        for reason in (*audit["missing_version_reasons"], *audit["stale_version_reasons"])
    )
    invalid_count = sum(bool(audit["invalid_reasons"]) for audit in audits)
    missing_version_count = sum(
        bool(audit["missing_version_reasons"]) for audit in audits
    )
    stale_version_count = sum(bool(audit["stale_version_reasons"]) for audit in audits)
    version_issue_count = sum(
        bool(audit["missing_version_reasons"] or audit["stale_version_reasons"])
        for audit in audits
    )
    _put_available(
        row,
        "d4_advice_valid_publication_count",
        len(audits) - sum(
            bool(
                audit["invalid_reasons"]
                or audit["missing_version_reasons"]
                or audit["stale_version_reasons"]
            )
            for audit in audits
        ),
    )
    _put_available(row, "d4_advice_invalid_publication_count", invalid_count)
    _put_available(
        row,
        "d4_advice_invalid_reason_distribution_json",
        dict(sorted(invalid_reasons.items())),
    )
    _put_available(
        row,
        "d4_advice_stale_version_evidence_count",
        stale_version_count,
    )
    _put_available(
        row,
        "d4_advice_missing_version_evidence_count",
        missing_version_count,
    )
    _put_available(
        row,
        "d4_advice_version_evidence_issue_count",
        version_issue_count,
    )
    _put_available(
        row,
        "d4_advice_version_evidence_issue_reasons_json",
        dict(sorted(version_reasons.items())),
    )

    quota_violations = [audit.get("quota_conservation_violation") for audit in audits]
    if all(isinstance(value, bool) for value in quota_violations):
        _put_available(
            row,
            "d4_advice_resource_quota_conservation_violation_count",
            sum(quota_violations),
        )
    else:
        _put_unavailable(
            row,
            "d4_advice_resource_quota_conservation_violation_count",
            "d4_advice_quota_delta_evidence_invalid",
        )

    mutation_values = [audit.get("formal_decision_mutated") for audit in audits]
    if all(isinstance(value, bool) for value in mutation_values):
        _put_available(
            row,
            "d4_advice_formal_decision_mutation_count",
            sum(mutation_values),
        )
        _put_available(
            row,
            "d4_advice_formal_decision_unchanged_count",
            len(mutation_values) - sum(mutation_values),
        )
    else:
        for field in (
            "d4_advice_formal_decision_mutation_count",
            "d4_advice_formal_decision_unchanged_count",
        ):
            _put_unavailable(
                row, field, "d4_advice_formal_decision_digest_evidence_invalid"
            )

    projection_counts = [audit.get("projection_rejection_count") for audit in audits]
    if all(_is_int_like(value) and int(value) >= 0 for value in projection_counts):
        _put_available(
            row,
            "d4_advice_projection_rejection_count",
            sum(int(value) for value in projection_counts),
        )
    else:
        _put_unavailable(
            row,
            "d4_advice_projection_rejection_count",
            "d4_advice_projection_rejection_evidence_invalid",
        )

    if invalid_count or version_issue_count:
        reason = (
            "d4_advice_payload_invalid"
            if invalid_count
            else "d4_advice_version_evidence_issue"
        )
        for field in _d4_advice_full_validity_fields():
            _put_unavailable(row, field, reason)
        _put_available(row, "d4_advice_evidence_status", "invalid_or_stale")
        if invalid_count:
            row["_failure_reasons"].append("d4_advice_payload_invalid")
        if version_issue_count:
            row["_failure_reasons"].append("d4_advice_version_evidence_issue")
    else:
        requested_modes = Counter(str(audit["requested_mode"]) for audit in audits)
        effective_modes = Counter(str(audit["effective_mode"]) for audit in audits)
        fallback_reasons = Counter(
            str(audit["fallback_reason"])
            for audit in audits
            if audit["fallback_used"] is True and audit["fallback_reason"] is not None
        )
        _put_available(
            row,
            "d4_advice_requested_mode_distribution_json",
            dict(sorted(requested_modes.items())),
        )
        _put_available(
            row,
            "d4_advice_effective_mode_distribution_json",
            dict(sorted(effective_modes.items())),
        )
        _put_available(
            row,
            "d4_advice_fallback_reason_distribution_json",
            dict(sorted(fallback_reasons.items())),
        )
        _put_available(
            row,
            "d4_advice_recommendation_output_count",
            sum(audit["recommendation_output"] is True for audit in audits),
        )
        _put_available(
            row,
            "d4_advice_shadow_output_count",
            sum(
                audit["recommendation_output"] is True
                and audit["effective_mode"] == "shadow"
                for audit in audits
            ),
        )
        _put_available(
            row,
            "d4_advice_assist_eligible_count",
            sum(audit["assist_eligible"] is True for audit in audits),
        )
        _put_available(
            row,
            "d4_advice_fallback_count",
            sum(audit["fallback_used"] is True for audit in audits),
        )
        latencies = np.asarray(
            [float(audit["inference_latency_ms"]) for audit in audits],
            dtype=float,
        )
        _put_available(
            row,
            "d4_advice_inference_latency_p50_ms",
            float(np.percentile(latencies, 50.0)),
        )
        _put_available(
            row,
            "d4_advice_inference_latency_p95_ms",
            float(np.percentile(latencies, 95.0)),
        )
        _put_available(row, "d4_advice_evidence_status", "valid_read_only_advice")

    if row.get("d4_advice_resource_quota_conservation_violation_count", 0):
        row["_failure_reasons"].append(
            "d4_advice_resource_quota_conservation_violation"
        )
    if row.get("d4_advice_formal_decision_mutation_count", 0):
        row["_failure_reasons"].append("d4_advice_formal_decision_mutation")


def _extract_d4_region_consumption_metrics(
    row: dict[str, Any],
    records: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any] | None,
) -> None:
    consumption_records = [
        record
        for record in records
        if record.get("topic") == _D4_REGION_CONSUMPTION_TOPIC
    ]
    _put_available(
        row,
        "d4_region_consumption_publication_count",
        len(consumption_records),
    )
    if not consumption_records:
        _put_available(row, "d4_region_consumption_valid_publication_count", 0)
        _put_available(row, "d4_region_consumption_invalid_publication_count", 0)
        for field in (
            "d4_region_consumable_count",
            "d4_region_d3_hint_applied_count",
            "d4_region_consumption_summary_consistent",
            "d4_region_consumption_rejection_reason_distribution_json",
            "d4_region_consumption_bridge_rejection_reason_distribution_json",
            "d4_region_consumption_evidence_status",
            "d4_advice_control_adoption_count",
        ):
            _put_unavailable(
                row,
                field,
                "d4_region_consumption_publication_missing",
            )
        return

    known_advisory_contracts: dict[str, Mapping[str, Any]] = {}
    conflicting_advisory_ids: set[str] = set()
    audits: list[dict[str, Any]] = []
    for record in records:
        if record.get("topic") == _D4_REGION_ADVICE_TOPIC:
            payload = _payload(record)
            contract = payload.get("advisory_contract")
            if isinstance(contract, Mapping):
                advisory_id = contract.get("advisory_id")
                if isinstance(advisory_id, str) and advisory_id.strip():
                    normalized_id = advisory_id.strip()
                    previous = known_advisory_contracts.get(normalized_id)
                    if (
                        previous is not None
                        and _json_ready(previous) != _json_ready(contract)
                    ):
                        conflicting_advisory_ids.add(normalized_id)
                    else:
                        known_advisory_contracts[normalized_id] = contract
        elif record.get("topic") == _D4_REGION_CONSUMPTION_TOPIC:
            audits.append(
                _audit_d4_region_consumption(
                    record,
                    known_advisory_contracts,
                    conflicting_advisory_ids,
                )
            )

    invalid_reasons = Counter(
        reason for audit in audits for reason in audit["invalid_reasons"]
    )
    invalid_count = sum(bool(audit["invalid_reasons"]) for audit in audits)
    _put_available(
        row,
        "d4_region_consumption_valid_publication_count",
        len(audits) - invalid_count,
    )
    _put_available(
        row,
        "d4_region_consumption_invalid_publication_count",
        invalid_count,
    )
    _put_available(
        row,
        "d4_region_consumption_invalid_reason_distribution_json",
        dict(sorted(invalid_reasons.items())),
    )

    summary_consistent, summary_reason = _audit_d4_consumption_summary(
        summary,
        audits[-1] if audits else None,
    )
    if summary_consistent is None:
        _put_unavailable(
            row,
            "d4_region_consumption_summary_consistent",
            summary_reason or "d4_region_consumption_summary_evidence_missing",
        )
    else:
        _put_available(
            row,
            "d4_region_consumption_summary_consistent",
            summary_consistent,
        )

    if invalid_count or summary_consistent is not True:
        reason = (
            "d4_region_consumption_payload_invalid"
            if invalid_count
            else summary_reason or "d4_region_consumption_summary_mismatch"
        )
        for field in (
            "d4_region_consumable_count",
            "d4_region_d3_hint_applied_count",
            "d4_region_consumption_rejection_reason_distribution_json",
            "d4_region_consumption_bridge_rejection_reason_distribution_json",
            "d4_region_consumption_evidence_status",
            "d4_advice_control_adoption_count",
        ):
            _put_unavailable(row, field, reason)
        row["_failure_reasons"].append(reason)
        return

    consumable_count = sum(audit["consumable"] is True for audit in audits)
    hint_applied_count = sum(audit["d3_hint_applied"] is True for audit in audits)
    adoption_count = sum(
        audit["consumable"] is True
        and audit["d3_hint_applied"] is True
        and audit["bridge_rejection_reason"] is None
        for audit in audits
    )
    rejection_reasons = Counter(
        reason for audit in audits for reason in audit["rejection_reasons"]
    )
    bridge_reasons = Counter(
        str(audit["bridge_rejection_reason"])
        for audit in audits
        if audit["bridge_rejection_reason"] is not None
    )
    _put_available(row, "d4_region_consumable_count", consumable_count)
    _put_available(row, "d4_region_d3_hint_applied_count", hint_applied_count)
    _put_available(row, "d4_advice_control_adoption_count", adoption_count)
    _put_available(
        row,
        "d4_region_consumption_rejection_reason_distribution_json",
        dict(sorted(rejection_reasons.items())),
    )
    _put_available(
        row,
        "d4_region_consumption_bridge_rejection_reason_distribution_json",
        dict(sorted(bridge_reasons.items())),
    )
    _put_available(row, "d4_region_consumption_evidence_status", "valid")


def _audit_d4_region_consumption(
    record: Mapping[str, Any],
    known_advisory_contracts: Mapping[str, Mapping[str, Any]],
    conflicting_advisory_ids: set[str],
) -> dict[str, Any]:
    payload = _payload(record)
    invalid: list[str] = []
    if record.get("schema_version") != _D4_REGION_CONSUMPTION_SCHEMA:
        invalid.append("consumption_envelope_schema_mismatch")
    if record.get("source") != "main":
        invalid.append("consumption_source_not_main")
    if payload.get("schema") != _D4_REGION_CONSUMPTION_SCHEMA:
        invalid.append("consumption_payload_schema_mismatch")
    for field in ("timestamp", "evaluated_at_s"):
        if not (
            _is_finite_number(payload.get(field))
            and float(payload[field]) >= 0.0
        ):
            invalid.append(f"consumption_{field}_invalid")
    if (
        _is_finite_number(payload.get("timestamp"))
        and _is_finite_number(payload.get("evaluated_at_s"))
        and abs(float(payload["timestamp"]) - float(payload["evaluated_at_s"]))
        > 1e-9
    ):
        invalid.append("consumption_timestamp_mismatch")
    if not (
        _is_int_like(payload.get("current_snapshot_version"))
        and int(payload["current_snapshot_version"]) > 0
    ):
        invalid.append("consumption_snapshot_version_invalid")
    for field in ("current_snapshot_id", "current_authority_digest"):
        if not isinstance(payload.get(field), str) or not str(payload[field]).strip():
            invalid.append(f"consumption_{field}_invalid")

    advisory = payload.get("advisory")
    advisory_id = None
    if not isinstance(advisory, Mapping):
        invalid.append("consumption_advisory_missing")
    else:
        if advisory.get("schema") != _D4_REGION_ADVISORY_SCHEMA:
            invalid.append("consumption_advisory_schema_mismatch")
        raw_advisory_id = advisory.get("advisory_id")
        if isinstance(raw_advisory_id, str) and raw_advisory_id.strip():
            advisory_id = raw_advisory_id.strip()
            published_contract = known_advisory_contracts.get(advisory_id)
            if published_contract is None:
                invalid.append("consumption_advisory_not_previously_published")
            elif advisory_id in conflicting_advisory_ids:
                invalid.append("consumption_advisory_publication_conflict")
            elif _json_ready(advisory) != _json_ready(published_contract):
                invalid.append("consumption_advisory_contract_mismatch")
        else:
            invalid.append("consumption_advisory_id_invalid")

    consumable = payload.get("consumable")
    if not isinstance(consumable, bool):
        invalid.append("consumption_consumable_not_boolean")
        consumable = None
    raw_rejections = payload.get("rejection_reasons")
    if not isinstance(raw_rejections, list) or not all(
        isinstance(reason, str) and reason.strip() for reason in raw_rejections
    ):
        invalid.append("consumption_rejection_reasons_invalid")
        rejection_reasons: list[str] = []
    else:
        rejection_reasons = [str(reason) for reason in raw_rejections]
    if consumable is True and rejection_reasons:
        invalid.append("consumable_consumption_has_rejection_reasons")

    hint_applied = payload.get("d3_hint_applied")
    if not isinstance(hint_applied, bool):
        invalid.append("consumption_d3_hint_applied_not_boolean")
        hint_applied = None
    bridge_reason = payload.get("bridge_rejection_reason")
    if bridge_reason is not None and not (
        isinstance(bridge_reason, str) and bridge_reason.strip()
    ):
        invalid.append("consumption_bridge_rejection_reason_invalid")
        bridge_reason = None
    if hint_applied is True and consumable is not True:
        invalid.append("d3_hint_applied_without_consumable_advisory")
    if hint_applied is True and bridge_reason is not None:
        invalid.append("d3_hint_applied_with_bridge_rejection")
    return {
        "advisory_id": advisory_id,
        "consumable": consumable,
        "d3_hint_applied": hint_applied,
        "rejection_reasons": rejection_reasons,
        "bridge_rejection_reason": bridge_reason,
        "invalid_reasons": list(dict.fromkeys(invalid)),
    }


def _audit_d4_consumption_summary(
    summary: Mapping[str, Any] | None,
    latest: Mapping[str, Any] | None,
) -> tuple[bool | None, str | None]:
    diagnostics = (
        summary.get("module_final_diagnostics")
        if isinstance(summary, Mapping)
        else None
    )
    if not isinstance(diagnostics, Mapping) or latest is None:
        return None, "d4_region_consumption_summary_evidence_missing"
    required = (
        "d4_region_consumption_available",
        "d4_region_consumable",
        "d4_region_consumption_rejection_reasons",
        "d4_region_hint_bridge_rejection_reason",
        "d3_regional_hint_applied",
    )
    if any(field not in diagnostics for field in required):
        return None, "d4_region_consumption_summary_fields_missing"
    raw_reasons = diagnostics.get("d4_region_consumption_rejection_reasons")
    if not isinstance(raw_reasons, list) or not all(
        isinstance(reason, str) for reason in raw_reasons
    ):
        return False, "d4_region_consumption_summary_rejections_invalid"
    consistent = (
        diagnostics.get("d4_region_consumption_available") is True
        and diagnostics.get("d4_region_consumable") is latest.get("consumable")
        and list(raw_reasons) == list(latest.get("rejection_reasons", ()))
        and diagnostics.get("d4_region_hint_bridge_rejection_reason")
        == latest.get("bridge_rejection_reason")
        and diagnostics.get("d3_regional_hint_applied")
        is latest.get("d3_hint_applied")
    )
    return (
        consistent,
        None if consistent else "d4_region_consumption_summary_mismatch",
    )


def _d4_advice_substantive_fields() -> tuple[str, ...]:
    return (
        "d4_advice_recommendation_output_count",
        "d4_advice_shadow_output_count",
        "d4_advice_assist_eligible_count",
        "d4_advice_fallback_count",
        "d4_advice_inference_latency_p50_ms",
        "d4_advice_inference_latency_p95_ms",
        "d4_advice_resource_quota_conservation_violation_count",
        "d4_advice_projection_rejection_count",
        "d4_advice_formal_decision_mutation_count",
        "d4_advice_formal_decision_unchanged_count",
        "d4_advice_stale_version_evidence_count",
        "d4_advice_missing_version_evidence_count",
        "d4_advice_version_evidence_issue_count",
        "d4_advice_requested_mode_distribution_json",
        "d4_advice_effective_mode_distribution_json",
        "d4_advice_fallback_reason_distribution_json",
    )


def _d4_advice_full_validity_fields() -> tuple[str, ...]:
    return (
        "d4_advice_recommendation_output_count",
        "d4_advice_shadow_output_count",
        "d4_advice_assist_eligible_count",
        "d4_advice_fallback_count",
        "d4_advice_inference_latency_p50_ms",
        "d4_advice_inference_latency_p95_ms",
        "d4_advice_requested_mode_distribution_json",
        "d4_advice_effective_mode_distribution_json",
        "d4_advice_fallback_reason_distribution_json",
    )


def _audit_d4_advice_publication(
    record: Mapping[str, Any],
    *,
    row: Mapping[str, Any],
    latest_formal: Mapping[str, Any] | None,
) -> dict[str, Any]:
    audit: dict[str, Any] = {
        "invalid_reasons": [],
        "missing_version_reasons": [],
        "stale_version_reasons": [],
        "requested_mode": None,
        "effective_mode": None,
        "recommendation_output": None,
        "assist_eligible": None,
        "fallback_used": None,
        "fallback_reason": None,
        "inference_latency_ms": None,
        "quota_conservation_violation": None,
        "projection_rejection_count": None,
        "formal_decision_mutated": None,
    }
    schema = record.get("schema_version")
    if schema is None or not str(schema).strip():
        audit["missing_version_reasons"].append("advice_envelope_schema_missing")
        audit["invalid_reasons"].append("advice_envelope_schema_missing")
        return audit
    if schema != _D4_REGION_ADVICE_SCHEMA:
        audit["stale_version_reasons"].append(
            f"advice_envelope_schema_unsupported:{schema}"
        )
        audit["invalid_reasons"].append("advice_envelope_schema_unsupported")
        return audit
    if record.get("source") != "D4":
        audit["invalid_reasons"].append("advice_envelope_source_not_d4")
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        audit["invalid_reasons"].append("advice_payload_not_object")
        return audit

    requested = payload.get("requested_mode")
    effective = payload.get("effective_mode")
    if requested not in _ADVISOR_MODES:
        audit["invalid_reasons"].append("advice_requested_mode_invalid")
    else:
        audit["requested_mode"] = requested
    if effective not in _ADVISOR_MODES:
        audit["invalid_reasons"].append("advice_effective_mode_invalid")
    else:
        audit["effective_mode"] = effective

    assist_eligible = payload.get("assist_eligible")
    fallback_used = payload.get("fallback_used")
    if not isinstance(assist_eligible, bool):
        audit["invalid_reasons"].append("advice_assist_eligible_not_boolean")
    else:
        audit["assist_eligible"] = assist_eligible
    if not isinstance(fallback_used, bool):
        audit["invalid_reasons"].append("advice_fallback_used_not_boolean")
    else:
        audit["fallback_used"] = fallback_used
    if "fallback_reason" not in payload:
        audit["invalid_reasons"].append("advice_fallback_reason_field_missing")
    else:
        fallback_reason = payload.get("fallback_reason")
        if fallback_reason is None or (
            isinstance(fallback_reason, str) and fallback_reason.strip()
        ):
            audit["fallback_reason"] = fallback_reason
        else:
            audit["invalid_reasons"].append("advice_fallback_reason_invalid")
    unseen = payload.get("unseen_seed_count")
    if not (_is_int_like(unseen) and int(unseen) >= 0):
        audit["invalid_reasons"].append("advice_unseen_seed_count_invalid")
    latency = payload.get("inference_latency_ms")
    if not (_is_finite_number(latency) and float(latency) >= 0.0):
        audit["invalid_reasons"].append("advice_inference_latency_invalid")
    else:
        audit["inference_latency_ms"] = float(latency)

    if (
        isinstance(assist_eligible, bool)
        and effective in _ADVISOR_MODES
        and assist_eligible != (effective == "assist")
    ):
        audit["invalid_reasons"].append("advice_assist_eligibility_mode_mismatch")
    if effective == "assist" and requested != "assist":
        audit["invalid_reasons"].append("advice_assist_self_promotion")
    if requested == "disabled" and effective != "disabled":
        audit["invalid_reasons"].append("advice_disabled_mode_not_preserved")
    if fallback_used is True and audit["fallback_reason"] is None:
        audit["invalid_reasons"].append("advice_fallback_reason_missing_when_used")
    if fallback_used is True and effective == "assist":
        audit["invalid_reasons"].append("advice_fallback_cannot_be_assist")

    payload_timestamp = payload.get("timestamp")
    envelope_timestamp = record.get("timestamp")
    if not (_is_finite_number(payload_timestamp) and float(payload_timestamp) >= 0.0):
        audit["invalid_reasons"].append("advice_payload_timestamp_invalid")
        payload_timestamp_value = None
    else:
        payload_timestamp_value = float(payload_timestamp)
    if not (_is_finite_number(envelope_timestamp) and float(envelope_timestamp) >= 0.0):
        audit["invalid_reasons"].append("advice_envelope_timestamp_invalid")
    elif (
        payload_timestamp_value is not None
        and not math.isclose(
            payload_timestamp_value,
            float(envelope_timestamp),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    ):
        audit["stale_version_reasons"].append(
            "advice_payload_envelope_timestamp_mismatch"
        )

    recommendation = payload.get("recommendation")
    if recommendation is None:
        audit["recommendation_output"] = False
        audit["quota_conservation_violation"] = False
        audit["projection_rejection_count"] = 0
        if effective != "disabled":
            audit["invalid_reasons"].append(
                "advice_recommendation_missing_for_active_mode"
            )
    elif not isinstance(recommendation, Mapping):
        audit["invalid_reasons"].append("advice_recommendation_not_object")
    else:
        audit["recommendation_output"] = True
        recommendation_audit = _audit_d4_recommendation(
            recommendation,
            row=row,
            advice_timestamp=payload_timestamp_value,
            latest_formal=latest_formal,
        )
        for key in (
            "invalid_reasons",
            "missing_version_reasons",
            "stale_version_reasons",
        ):
            audit[key].extend(recommendation_audit[key])
        audit["quota_conservation_violation"] = recommendation_audit[
            "quota_conservation_violation"
        ]
        audit["projection_rejection_count"] = recommendation_audit[
            "projection_rejection_count"
        ]
    if effective == "disabled" and recommendation is not None:
        audit["invalid_reasons"].append(
            "advice_disabled_mode_has_recommendation_output"
        )

    unchanged = payload.get("formal_decision_unchanged")
    before = payload.get("formal_decision_digest_before")
    after = payload.get("formal_decision_digest_after")
    if not isinstance(unchanged, bool):
        audit["invalid_reasons"].append("formal_decision_unchanged_not_boolean")
    if not (isinstance(before, str) and before.strip()):
        audit["missing_version_reasons"].append(
            "formal_decision_digest_before_missing"
        )
    if not (isinstance(after, str) and after.strip()):
        audit["missing_version_reasons"].append("formal_decision_digest_after_missing")
    if (
        isinstance(unchanged, bool)
        and isinstance(before, str)
        and before.strip()
        and isinstance(after, str)
        and after.strip()
    ):
        digest_unchanged = before == after
        audit["formal_decision_mutated"] = not digest_unchanged
        if unchanged != digest_unchanged:
            audit["invalid_reasons"].append(
                "formal_decision_digest_flag_mismatch"
            )

    for key in ("invalid_reasons", "missing_version_reasons", "stale_version_reasons"):
        audit[key] = list(dict.fromkeys(audit[key]))
    return audit


def _audit_d4_recommendation(
    recommendation: Mapping[str, Any],
    *,
    row: Mapping[str, Any],
    advice_timestamp: float | None,
    latest_formal: Mapping[str, Any] | None,
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "invalid_reasons": [],
        "missing_version_reasons": [],
        "stale_version_reasons": [],
        "quota_conservation_violation": None,
        "projection_rejection_count": None,
    }
    schema = recommendation.get("schema")
    if schema is None or not str(schema).strip():
        output["missing_version_reasons"].append("recommendation_schema_missing")
        output["invalid_reasons"].append("recommendation_schema_missing")
    elif schema != _D4_REGION_RECOMMENDATION_SCHEMA:
        output["stale_version_reasons"].append(
            f"recommendation_schema_unsupported:{schema}"
        )
        output["invalid_reasons"].append("recommendation_schema_unsupported")

    for field in (
        "snapshot_id",
        "scenario_id",
        "scenario_version",
        "authority_digest",
        "policy_name",
        "policy_version",
    ):
        value = recommendation.get(field)
        if not isinstance(value, str) or not value.strip():
            output["missing_version_reasons"].append(
                f"recommendation_{field}_missing"
            )
            output["invalid_reasons"].append(f"recommendation_{field}_invalid")
    seed = recommendation.get("seed")
    if not (_is_int_like(seed) and int(seed) >= 0):
        output["missing_version_reasons"].append("recommendation_seed_missing")
        output["invalid_reasons"].append("recommendation_seed_invalid")
    created_at = recommendation.get("created_at_s")
    if not (_is_finite_number(created_at) and float(created_at) >= 0.0):
        output["invalid_reasons"].append("recommendation_created_at_invalid")
    elif advice_timestamp is not None and not math.isclose(
        float(created_at), advice_timestamp, rel_tol=0.0, abs_tol=1e-9
    ):
        output["stale_version_reasons"].append(
            "recommendation_snapshot_timestamp_stale"
        )
    confidence = recommendation.get("confidence")
    if not (
        _is_finite_number(confidence) and 0.0 <= float(confidence) <= 1.0
    ):
        output["invalid_reasons"].append("recommendation_confidence_invalid")
    if not isinstance(recommendation.get("source"), str) or not str(
        recommendation.get("source", "")
    ).strip():
        output["invalid_reasons"].append("recommendation_source_invalid")
    if not isinstance(recommendation.get("projected"), bool):
        output["invalid_reasons"].append("recommendation_projected_not_boolean")
    elif recommendation.get("projected") is not True:
        output["invalid_reasons"].append("recommendation_not_safety_projected")
    fallback = recommendation.get("fallback_reason")
    if fallback is not None and not (isinstance(fallback, str) and fallback.strip()):
        output["invalid_reasons"].append("recommendation_fallback_reason_invalid")
    model_sha = recommendation.get("model_sha256")
    if model_sha is not None and not (
        isinstance(model_sha, str) and re.fullmatch(r"[0-9a-fA-F]{64}", model_sha)
    ):
        output["invalid_reasons"].append("recommendation_model_sha256_invalid")
    if recommendation.get("source") == "learned" and model_sha is None:
        output["missing_version_reasons"].append(
            "recommendation_learned_model_sha256_missing"
        )
    if recommendation.get("source") == "learned":
        runtime_fingerprint_available = (
            row.get("d4_learning_model_fingerprint_availability") == "available"
        )
        runtime_version_available = (
            row.get("d4_learning_model_version_availability") == "available"
        )
        if not runtime_fingerprint_available:
            output["missing_version_reasons"].append(
                "d4_runtime_model_fingerprint_unavailable_for_learned_advice"
            )
        elif model_sha != row.get("d4_learning_model_fingerprint"):
            output["stale_version_reasons"].append(
                "recommendation_model_fingerprint_mismatch"
            )
        if not runtime_version_available:
            output["missing_version_reasons"].append(
                "d4_runtime_model_version_unavailable_for_learned_advice"
            )
        else:
            runtime_model_version = str(row["d4_learning_model_version"])
            expected_policy_version = runtime_model_version.rsplit("+", 1)[0]
            if recommendation.get("policy_version") != expected_policy_version:
                output["stale_version_reasons"].append(
                    "recommendation_policy_version_mismatch"
                )

    if (
        row.get("scenario_name_availability") == "available"
        and recommendation.get("scenario_id") != row.get("scenario_name")
    ):
        output["stale_version_reasons"].append("recommendation_scenario_id_mismatch")
    if (
        row.get("scenario_version_availability") == "available"
        and recommendation.get("scenario_version") != row.get("scenario_version")
    ):
        output["stale_version_reasons"].append(
            "recommendation_scenario_version_mismatch"
        )
    if (
        row.get("seed_availability") == "available"
        and _is_int_like(seed)
        and int(seed) != int(row["seed"])
    ):
        output["stale_version_reasons"].append("recommendation_seed_mismatch")

    formal_regions = _d4_formal_region_contracts(latest_formal)
    if latest_formal is None:
        output["missing_version_reasons"].append(
            "formal_d4_publication_missing_before_advice"
        )
    actions = recommendation.get("actions")
    action_deltas: dict[str, int] = {}
    if not isinstance(actions, list):
        output["invalid_reasons"].append("recommendation_actions_not_list")
    else:
        for index, action in enumerate(actions):
            _audit_d4_action(
                action,
                index=index,
                advice_timestamp=advice_timestamp,
                formal_regions=formal_regions,
                action_deltas=action_deltas,
                output=output,
            )
        if len(action_deltas) != len(actions):
            output["invalid_reasons"].append(
                "recommendation_action_region_ids_not_unique"
            )
        if all(
            isinstance(action, Mapping)
            and _is_int_like(action.get("resource_quota_delta"))
            for action in actions
        ):
            total_delta = sum(int(action["resource_quota_delta"]) for action in actions)
            output["quota_conservation_violation"] = total_delta != 0
            if total_delta != 0:
                output["invalid_reasons"].append(
                    "projected_recommendation_not_resource_conserving"
                )

    transfers = recommendation.get("transfers")
    transfer_deltas: Counter[str] = Counter()
    transfers_valid = isinstance(transfers, list)
    if not transfers_valid:
        output["invalid_reasons"].append("recommendation_transfers_not_list")
    else:
        for index, transfer in enumerate(transfers):
            if not isinstance(transfer, Mapping):
                output["invalid_reasons"].append(
                    f"recommendation_transfer_not_object:{index}"
                )
                transfers_valid = False
                continue
            source = transfer.get("source_region_id")
            target = transfer.get("target_region_id")
            count = transfer.get("resource_count")
            edge_id = transfer.get("edge_id")
            transfer_time = transfer.get("expected_transfer_time_s")
            if not isinstance(source, str) or not source.strip():
                output["invalid_reasons"].append(
                    f"recommendation_transfer_source_invalid:{index}"
                )
                transfers_valid = False
            if not isinstance(target, str) or not target.strip() or target == source:
                output["invalid_reasons"].append(
                    f"recommendation_transfer_target_invalid:{index}"
                )
                transfers_valid = False
            if not (_is_int_like(count) and int(count) > 0):
                output["invalid_reasons"].append(
                    f"recommendation_transfer_resource_count_invalid:{index}"
                )
                transfers_valid = False
            if not isinstance(edge_id, str) or not edge_id.strip():
                output["invalid_reasons"].append(
                    f"recommendation_transfer_edge_id_invalid:{index}"
                )
                transfers_valid = False
            if not (
                _is_finite_number(transfer_time) and float(transfer_time) >= 0.0
            ):
                output["invalid_reasons"].append(
                    f"recommendation_transfer_time_invalid:{index}"
                )
                transfers_valid = False
            if (
                isinstance(source, str)
                and source.strip()
                and isinstance(target, str)
                and target.strip()
                and source != target
                and _is_int_like(count)
                and int(count) > 0
            ):
                transfer_deltas[source] -= int(count)
                transfer_deltas[target] += int(count)
    if (
        transfers_valid
        and isinstance(actions, list)
        and output["quota_conservation_violation"] is not None
        and any(transfer_deltas)
        and {
            region_id: delta
            for region_id, delta in action_deltas.items()
            if delta != 0
        }
        != {region_id: delta for region_id, delta in transfer_deltas.items() if delta != 0}
    ):
        output["invalid_reasons"].append(
            "recommendation_transfer_action_quota_delta_mismatch"
        )

    rejections = recommendation.get("projection_rejections")
    if not isinstance(rejections, list) or not all(
        isinstance(value, str) and value.strip() for value in rejections
    ):
        output["invalid_reasons"].append(
            "recommendation_projection_rejections_invalid"
        )
    else:
        output["projection_rejection_count"] = len(rejections)

    for key in ("invalid_reasons", "missing_version_reasons", "stale_version_reasons"):
        output[key] = list(dict.fromkeys(output[key]))
    return output


def _audit_d4_action(
    action: Any,
    *,
    index: int,
    advice_timestamp: float | None,
    formal_regions: Mapping[str, Mapping[str, Any]],
    action_deltas: dict[str, int],
    output: dict[str, Any],
) -> None:
    if not isinstance(action, Mapping):
        output["invalid_reasons"].append(f"recommendation_action_not_object:{index}")
        return
    region_id = action.get("region_id")
    if not isinstance(region_id, str) or not region_id.strip():
        output["invalid_reasons"].append(
            f"recommendation_action_region_id_invalid:{index}"
        )
        return
    delta = action.get("resource_quota_delta")
    if not _is_int_like(delta):
        output["invalid_reasons"].append(
            f"recommendation_action_quota_delta_invalid:{region_id}"
        )
    else:
        action_deltas[region_id] = int(delta)
    for field in ("reserve_ratio", "reconnaissance_priority"):
        value = action.get(field)
        if not (_is_finite_number(value) and 0.0 <= float(value) <= 1.0):
            output["invalid_reasons"].append(
                f"recommendation_action_{field}_invalid:{region_id}"
            )
    for field in ("hold", "request_replan"):
        if not isinstance(action.get(field), bool):
            output["invalid_reasons"].append(
                f"recommendation_action_{field}_invalid:{region_id}"
            )
    for field in (
        "expected_owner_id",
        "expected_owner_layer",
        "expected_plan_id",
    ):
        if not isinstance(action.get(field), str) or not str(action.get(field, "")).strip():
            output["missing_version_reasons"].append(
                f"recommendation_action_{field}_missing:{region_id}"
            )
    for field in ("expected_plan_version", "expected_epoch"):
        if not (_is_int_like(action.get(field)) and int(action[field]) >= 0):
            output["missing_version_reasons"].append(
                f"recommendation_action_{field}_missing:{region_id}"
            )
    lease = action.get("expected_lease_expires_at_s")
    if not (_is_finite_number(lease) and float(lease) >= 0.0):
        output["missing_version_reasons"].append(
            f"recommendation_action_expected_lease_missing:{region_id}"
        )
    elif advice_timestamp is not None and float(lease) <= advice_timestamp:
        output["stale_version_reasons"].append(
            f"recommendation_action_lease_expired:{region_id}"
        )

    formal = formal_regions.get(region_id)
    if formal_regions and formal is None:
        output["stale_version_reasons"].append(
            f"recommendation_action_formal_region_missing:{region_id}"
        )
    elif formal is not None:
        comparisons = (
            ("expected_owner_id", "owner_id"),
            ("expected_owner_layer", "owner_layer"),
            ("expected_plan_id", "plan_id"),
            ("expected_plan_version", "plan_version"),
            ("expected_epoch", "epoch"),
            ("expected_lease_expires_at_s", "lease_expires_at_s"),
        )
        for action_field, formal_field in comparisons:
            action_value = action.get(action_field)
            formal_value = formal.get(formal_field)
            if action_value is None or formal_value is None:
                continue
            matches = (
                math.isclose(
                    float(action_value),
                    float(formal_value),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                if _is_finite_number(action_value) and _is_finite_number(formal_value)
                else action_value == formal_value
            )
            if not matches:
                output["stale_version_reasons"].append(
                    f"recommendation_action_formal_{formal_field}_mismatch:{region_id}"
                )


def _d4_formal_region_contracts(
    payload: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return {}
    regions = payload.get("regions")
    if not isinstance(regions, list):
        return {}
    output: dict[str, dict[str, Any]] = {}
    for region in regions:
        if not isinstance(region, Mapping):
            continue
        region_id = region.get("region_id")
        ownership = region.get("ownership")
        if not isinstance(region_id, str) or not isinstance(ownership, Mapping):
            continue
        output[region_id] = {
            "owner_id": ownership.get("owner_id"),
            "owner_layer": ownership.get("owner_layer"),
            "plan_id": ownership.get("plan_id"),
            "plan_version": ownership.get("plan_version"),
            "epoch": ownership.get("epoch"),
            "lease_expires_at_s": ownership.get("lease_expires_at_s"),
        }
    return output


def _extract_d5_metrics(
    row: dict[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    d5_records = [
        record
        for record in records
        if record.get("topic") == "modules.d5.terminal_association"
    ]
    fields = (
        "d5_candidate_edge_count",
        "d5_graph_density",
        "d5_graph_edge_budget",
        "d5_graph_budget_utilization",
        "d5_graph_budget_dropped_count",
        "d5_binding_count",
        "d5_model_fallback_event_count",
    )
    if not d5_records:
        for field in fields:
            _put_unavailable(row, field, "d5_publication_missing")
        for field in (
            "d5_probability_source",
            "d5_scoring_status",
            "d5_fallback_reason",
            "d5_fallback_reason_distribution_json",
        ):
            _put_unavailable(row, field, "d5_publication_missing")
        return
    latest = _payload(d5_records[-1])
    diagnostics = latest.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, Mapping) else {}
    candidate_edges = diagnostics.get("candidate_tracklet_edges", latest.get("graph_edge_count"))
    nodes = latest.get("graph_node_count")
    graph_edges = latest.get("graph_edge_count", candidate_edges)
    per_node_cap = diagnostics.get("max_tracklet_candidate_edges_per_node")
    dropped = diagnostics.get("tracklet_candidate_budget_dropped")
    if _is_int_like(candidate_edges) and int(candidate_edges) >= 0:
        _put_available(row, "d5_candidate_edge_count", int(candidate_edges))
    else:
        _put_unavailable(row, "d5_candidate_edge_count", "d5_candidate_edge_count_missing")
    if _is_int_like(nodes) and int(nodes) >= 0 and _is_int_like(graph_edges):
        node_count = int(nodes)
        possible = node_count * max(0, node_count - 1) // 2
        density = 0.0 if possible == 0 and int(graph_edges) == 0 else (
            float(graph_edges) / possible if possible > 0 else None
        )
        if density is not None:
            _put_available(row, "d5_graph_density", density)
        else:
            _put_unavailable(row, "d5_graph_density", "d5_graph_density_undefined")
    else:
        _put_unavailable(row, "d5_graph_density", "d5_graph_node_or_edge_count_missing")
    if _is_int_like(nodes) and _is_int_like(per_node_cap) and int(per_node_cap) >= 0:
        budget = int(nodes) * int(per_node_cap) // 2
        _put_available(row, "d5_graph_edge_budget", budget)
        if _is_int_like(candidate_edges) and budget > 0:
            _put_available(
                row,
                "d5_graph_budget_utilization",
                float(candidate_edges) / budget,
            )
        elif (
            _is_int_like(candidate_edges)
            and budget == 0
            and int(candidate_edges) == 0
        ):
            _put_available(row, "d5_graph_budget_utilization", 0.0)
        else:
            _put_unavailable(
                row,
                "d5_graph_budget_utilization",
                "d5_candidate_edge_count_missing",
            )
    else:
        _put_unavailable(row, "d5_graph_edge_budget", "d5_graph_degree_cap_missing")
        _put_unavailable(
            row,
            "d5_graph_budget_utilization",
            "d5_graph_degree_cap_missing",
        )
    if _is_int_like(dropped) and int(dropped) >= 0:
        _put_available(row, "d5_graph_budget_dropped_count", int(dropped))
    else:
        _put_unavailable(
            row,
            "d5_graph_budget_dropped_count",
            "d5_graph_budget_drop_diagnostic_missing",
        )
    bindings = latest.get("bindings")
    if (
        isinstance(bindings, list)
        and all(isinstance(item, Mapping) for item in bindings)
        and all("global_track_id" in item for item in bindings)
    ):
        _put_available(
            row,
            "d5_binding_count",
            sum(item.get("global_track_id") is not None for item in bindings),
        )
    else:
        _put_unavailable(row, "d5_binding_count", "d5_bindings_missing")
    for field in ("probability_source", "scoring_status", "fallback_reason"):
        value = latest.get(field)
        if value is not None:
            _put_available(row, f"d5_{field}", value)
        elif field == "fallback_reason" and field in latest:
            _put_available(row, "d5_fallback_reason", "none")
        else:
            _put_unavailable(row, f"d5_{field}", f"d5_{field}_missing")
    fallback_values = [
        _payload(record).get("fallback_reason")
        if "fallback_reason" in _payload(record)
        else ...
        for record in d5_records
    ]
    if not all(
        value is None
        or value is ...
        or (isinstance(value, str) and (value == "none" or bool(value.strip())))
        for value in fallback_values
    ) or any(value is ... for value in fallback_values):
        _put_unavailable(
            row,
            "d5_model_fallback_event_count",
            "d5_fallback_reason_field_missing_or_invalid",
        )
        _put_unavailable(
            row,
            "d5_fallback_reason_distribution_json",
            "d5_fallback_reason_field_missing_or_invalid",
        )
    else:
        fallbacks = Counter(
            str(value)
            for value in fallback_values
            if value not in (None, "none", "")
        )
        _put_available(row, "d5_model_fallback_event_count", sum(fallbacks.values()))
        _put_available(
            row,
            "d5_fallback_reason_distribution_json",
            dict(sorted(fallbacks.items())),
        )
    row["d5_camera_batch_count"] = latest.get("camera_batch_count")
    row["d5_diagnostics_json"] = dict(diagnostics)


def _extract_d7_metrics(
    row: dict[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    d7_records = [
        record
        for record in records
        if record.get("topic") == "modules.d7.guidance_commands"
    ]
    if not d7_records:
        for field in ("d7_command_count", "d7_hold_count", "d7_reject_count"):
            _put_unavailable(row, field, "d7_publication_missing")
        _put_unavailable(row, "d7_mode_distribution_json", "d7_publication_missing")
        _put_unavailable(
            row, "d7_reject_reason_distribution_json", "d7_publication_missing"
        )
        return
    commands: list[Mapping[str, Any]] = []
    declared_total = 0
    declared_counts_complete = True
    command_lists_complete = True
    for record in d7_records:
        payload = _payload(record)
        declared = payload.get("command_count")
        if _is_int_like(declared) and int(declared) >= 0:
            declared_total += int(declared)
        else:
            declared_counts_complete = False
        values = payload.get("commands")
        if isinstance(values, list) and all(isinstance(item, Mapping) for item in values):
            commands.extend(values)
        else:
            command_lists_complete = False
    if command_lists_complete:
        _put_available(row, "d7_command_count", len(commands))
    elif declared_counts_complete:
        _put_available(row, "d7_command_count", declared_total)
    else:
        _put_unavailable(row, "d7_command_count", "d7_command_count_missing")
    if not command_lists_complete:
        _put_unavailable(row, "d7_hold_count", "d7_command_list_missing")
        _put_unavailable(row, "d7_reject_count", "d7_command_list_missing")
        _put_unavailable(row, "d7_mode_distribution_json", "d7_command_list_missing")
        _put_unavailable(
            row,
            "d7_reject_reason_distribution_json",
            "d7_command_list_missing",
        )
        return
    if not all("mode" in command and command.get("mode") is not None for command in commands):
        _put_unavailable(row, "d7_hold_count", "d7_command_mode_missing")
        _put_unavailable(row, "d7_reject_count", "d7_command_mode_missing")
        _put_unavailable(row, "d7_mode_distribution_json", "d7_command_mode_missing")
        _put_unavailable(
            row,
            "d7_reject_reason_distribution_json",
            "d7_command_mode_missing",
        )
        return
    modes = Counter(str(command["mode"]) for command in commands)
    hold_commands = [command for command in commands if command.get("mode") == "hold"]
    rejected = [
        command for command in hold_commands if str(command.get("gate_reason", "")).strip()
    ]
    reasons = Counter(str(command["gate_reason"]) for command in rejected)
    _put_available(row, "d7_hold_count", len(hold_commands))
    _put_available(row, "d7_reject_count", len(rejected))
    _put_available(row, "d7_mode_distribution_json", dict(sorted(modes.items())))
    _put_available(
        row,
        "d7_reject_reason_distribution_json",
        dict(sorted(reasons.items())),
    )


def _extract_camera_count(
    row: dict[str, Any],
    config: Mapping[str, Any] | None,
    records: Sequence[Mapping[str, Any]],
) -> None:
    metadata = config.get("metadata") if isinstance(config, Mapping) else None
    explicit = metadata.get("camera_count") if isinstance(metadata, Mapping) else None
    if _is_int_like(explicit) and int(explicit) >= 0:
        _put_available(row, "camera_count", int(explicit))
        row["camera_count_source"] = "scenario_config.metadata.camera_count"
        return
    if isinstance(config, Mapping) and config.get("visual_enabled") is False:
        _put_available(row, "camera_count", 0)
        row["camera_count_source"] = "scenario_config.visual_enabled_false"
        return
    resource_count = row.get("resource_count")
    recon_count = row.get("recon_count")
    if (
        isinstance(config, Mapping)
        and config.get("visual_enabled") is True
        and _is_int_like(resource_count)
        and _is_int_like(recon_count)
    ):
        _put_available(row, "camera_count", int(resource_count) + int(recon_count))
        row["camera_count_source"] = (
            "producer_one_camera_per_resource_and_recon_contract"
        )
        return
    d5_counts = [
        _payload(record).get("camera_batch_count")
        for record in records
        if record.get("topic") == "modules.d5.terminal_association"
    ]
    valid_d5 = [int(value) for value in d5_counts if _is_int_like(value) and int(value) >= 0]
    if valid_d5:
        _put_available(row, "camera_count", max(valid_d5))
        row["camera_count_source"] = "d5_camera_batch_count"
        return
    observed: set[str] = set()
    for record in records:
        payload = _payload(record)
        measurements = payload.get("measurements")
        if record.get("topic") != "sensor.observations" or not isinstance(measurements, list):
            continue
        if any(
            isinstance(item, Mapping) and item.get("modality") == "vision_bbox"
            for item in measurements
        ):
            sensor_id = payload.get("sensor_id")
            if sensor_id is not None:
                observed.add(str(sensor_id))
    if observed:
        _put_available(row, "camera_count", len(observed))
        row["camera_count_source"] = "observed_visual_sensor_ids"
        return
    if _is_int_like(resource_count) and _is_int_like(recon_count):
        _put_available(row, "camera_count", int(resource_count) + int(recon_count))
        row["camera_count_source"] = "producer_one_camera_per_resource_and_recon_contract"
    else:
        _put_unavailable(row, "camera_count", "camera_count_evidence_missing")


def _extract_observation_truth_disposition_metrics(
    row: dict[str, Any],
    *,
    labels: Sequence[Mapping[str, Any]] | None,
    labels_reason: str | None,
) -> ObservationTruthDispositionAudit | None:
    """Validate the evaluator sidecar and expose version-aware availability."""

    if labels is None:
        reason = labels_reason or "offline_truth_labels_missing"
        for field in (
            "offline_truth_disposition_contract_valid",
            "offline_truth_label_count",
            "offline_truth_target_label_count",
            "offline_truth_known_false_alarm_count",
            "offline_truth_unknown_count",
            "offline_truth_missing_disposition_count",
            "offline_truth_complete_disposition_available",
            "offline_truth_strict_identity_eligible",
        ):
            _put_unavailable(row, field, reason)
        _put_available(
            row,
            "offline_truth_known_false_alarm_treated_as_target",
            False,
        )
        _put_available(row, "offline_truth_strict_id_switch_backfilled", False)
        row["offline_truth_inference_sources_json"] = []
        row["offline_truth_disposition_audit_json"] = {
            "availability": "unavailable",
            "reason": reason,
            "strict_id_switch_backfilled": False,
            "inference_sources_used": [],
        }
        return None

    declared_schema = (
        str(row["offline_truth_schema"])
        if row.get("offline_truth_schema_availability") == "available"
        else None
    )
    try:
        audit = audit_observation_truth_sidecar(
            labels,
            accepted_contract="external",
            declared_schema_version=declared_schema,
        )
    except ObservationTruthSidecarError as exc:
        missing_count = 0
        if declared_schema == SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V2:
            missing_count = sum(
                isinstance(item, Mapping) and "disposition" not in item
                for item in labels
            )
        reason = exc.code
        for field in (
            "offline_truth_label_count",
            "offline_truth_target_label_count",
            "offline_truth_known_false_alarm_count",
            "offline_truth_unknown_count",
            "offline_truth_complete_disposition_available",
            "offline_truth_strict_identity_eligible",
        ):
            _put_unavailable(row, field, reason)
        _put_available(row, "offline_truth_disposition_contract_valid", False)
        _put_available(
            row,
            "offline_truth_missing_disposition_count",
            missing_count,
        )
        _put_available(
            row,
            "offline_truth_known_false_alarm_treated_as_target",
            False,
        )
        _put_available(row, "offline_truth_strict_id_switch_backfilled", False)
        row["offline_truth_inference_sources_json"] = []
        row["offline_truth_disposition_audit_json"] = {
            "availability": "unavailable",
            "reason": reason,
            "error": str(exc),
            "missing_disposition_count": missing_count,
            "strict_id_switch_backfilled": False,
            "inference_sources_used": [],
        }
        row["_failure_reasons"].append(
            f"offline_truth_disposition_contract:{reason}"
        )
        return None

    _put_available(row, "offline_truth_disposition_contract_valid", True)
    _put_available(row, "offline_truth_label_count", audit.record_count)
    _put_available(
        row,
        "offline_truth_target_label_count",
        audit.target_label_count,
    )
    if audit.complete_disposition_available:
        _put_available(
            row,
            "offline_truth_known_false_alarm_count",
            audit.known_false_alarm_count,
        )
        _put_available(row, "offline_truth_unknown_count", audit.unknown_count)
    else:
        reason = audit.complete_disposition_reason or (
            "offline_truth_complete_disposition_unavailable"
        )
        _put_unavailable(
            row,
            "offline_truth_known_false_alarm_count",
            reason,
        )
        _put_unavailable(row, "offline_truth_unknown_count", reason)
    _put_available(
        row,
        "offline_truth_missing_disposition_count",
        audit.missing_disposition_count,
    )
    _put_available(
        row,
        "offline_truth_complete_disposition_available",
        audit.complete_disposition_available,
    )
    row[
        "offline_truth_complete_disposition_reason"
    ] = audit.complete_disposition_reason
    _put_available(
        row,
        "offline_truth_strict_identity_eligible",
        audit.strict_identity_eligible,
    )
    row["offline_truth_strict_identity_blockers_json"] = list(
        audit.strict_identity_blockers
    )
    _put_available(
        row,
        "offline_truth_known_false_alarm_treated_as_target",
        False,
    )
    _put_available(row, "offline_truth_strict_id_switch_backfilled", False)
    row["offline_truth_inference_sources_json"] = []
    row["offline_truth_disposition_audit_json"] = {
        "availability": "available",
        **audit.to_dict(),
    }
    return audit


def _extract_proximity_metrics(
    row: dict[str, Any],
    *,
    proximity_records: Sequence[Mapping[str, Any]] | None,
    proximity_reason: str | None,
    online_records: Sequence[Mapping[str, Any]],
    truth_labels: Sequence[Mapping[str, Any]] | None,
    truth_labels_reason: str | None,
    truth_disposition: ObservationTruthDispositionAudit | None,
) -> None:
    if proximity_records is None:
        for field in (
            "offline_proximity_within_5m_count",
            "offline_proximity_unique_target_count",
            "offline_proximity_identity_evaluable_count",
            "offline_proximity_identity_correct_count",
            "offline_proximity_identity_correct_rate",
        ):
            _put_unavailable(row, field, proximity_reason or "offline_proximity_file_missing")
        row["offline_truth_labels_read"] = False
        return
    within: list[Mapping[str, Any]] = []
    invalid_distance = False
    for record in proximity_records:
        distance = record.get("distance_m")
        if not _is_finite_number(distance):
            invalid_distance = True
            continue
        if float(distance) <= FIVE_METER_THRESHOLD_M + 1.0e-12:
            within.append(record)
    if invalid_distance:
        _put_unavailable(
            row,
            "offline_proximity_within_5m_count",
            "offline_proximity_distance_missing_or_nonfinite",
        )
        _put_unavailable(
            row,
            "offline_proximity_unique_target_count",
            "offline_proximity_distance_missing_or_nonfinite",
        )
    else:
        _put_available(row, "offline_proximity_within_5m_count", len(within))
        truth_ids = [record.get("truth_target_id") for record in within]
        if all(value is not None for value in truth_ids):
            _put_available(
                row,
                "offline_proximity_unique_target_count",
                len({str(value) for value in truth_ids}),
            )
        elif within:
            _put_unavailable(
                row,
                "offline_proximity_unique_target_count",
                "offline_proximity_truth_target_id_missing",
            )
        else:
            _put_available(row, "offline_proximity_unique_target_count", 0)

    if not within:
        row["offline_truth_labels_read"] = False
        _put_available(row, "offline_proximity_identity_evaluable_count", 0)
        _put_unavailable(
            row,
            "offline_proximity_identity_correct_count",
            "no_five_meter_proximity_events",
        )
        _put_unavailable(
            row,
            "offline_proximity_identity_correct_rate",
            "no_five_meter_proximity_events",
        )
        return

    row["offline_truth_labels_read"] = True
    row["offline_truth_labels_read_reason"] = "five_meter_identity_scoring_requested"
    if truth_labels is None:
        _put_available(row, "offline_proximity_identity_evaluable_count", 0)
        _put_unavailable(
            row,
            "offline_proximity_identity_correct_count",
            truth_labels_reason or "offline_truth_labels_missing",
        )
        _put_unavailable(
            row,
            "offline_proximity_identity_correct_rate",
            truth_labels_reason or "offline_truth_labels_missing",
        )
        return
    if truth_disposition is None:
        reason = "offline_truth_disposition_contract_invalid"
        _put_available(row, "offline_proximity_identity_evaluable_count", 0)
        _put_unavailable(row, "offline_proximity_identity_correct_count", reason)
        _put_unavailable(row, "offline_proximity_identity_correct_rate", reason)
        return
    if not truth_disposition.strict_identity_eligible:
        reason = "offline_truth_disposition_not_strict_identity_eligible"
        _put_available(row, "offline_proximity_identity_evaluable_count", 0)
        _put_unavailable(row, "offline_proximity_identity_correct_count", reason)
        _put_unavailable(row, "offline_proximity_identity_correct_rate", reason)
        return
    truth_map, map_reason = _offline_global_track_truth_map(truth_labels)
    if map_reason is not None:
        _put_available(row, "offline_proximity_identity_evaluable_count", 0)
        _put_unavailable(row, "offline_proximity_identity_correct_count", map_reason)
        _put_unavailable(row, "offline_proximity_identity_correct_rate", map_reason)
        return
    evaluations: list[bool] = []
    for event in within:
        assigned_track = _assigned_track_for_proximity_event(event, online_records)
        truth_target = event.get("truth_target_id")
        if assigned_track is None or truth_target is None or assigned_track not in truth_map:
            continue
        evaluations.append(truth_map[assigned_track] == str(truth_target))
    _put_available(row, "offline_proximity_identity_evaluable_count", len(evaluations))
    if len(evaluations) != len(within):
        reason = "incomplete_offline_assignment_or_global_track_truth_mapping"
        _put_unavailable(row, "offline_proximity_identity_correct_count", reason)
        _put_unavailable(row, "offline_proximity_identity_correct_rate", reason)
    else:
        correct = sum(evaluations)
        _put_available(row, "offline_proximity_identity_correct_count", correct)
        _put_available(
            row,
            "offline_proximity_identity_correct_rate",
            correct / len(evaluations),
        )


def _offline_global_track_truth_map(
    labels: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, str], str | None]:
    mapping: dict[str, str] = {}
    saw_mapping_field = False
    for label in labels:
        global_track = label.get("global_track_id", label.get("center_global_track_id"))
        truth = label.get("truth_entity_id", label.get("truth_target_id"))
        if global_track is None:
            continue
        saw_mapping_field = True
        if truth is None:
            return {}, "offline_truth_global_track_mapping_truth_id_missing"
        key = str(global_track)
        value = str(truth)
        if key in mapping and mapping[key] != value:
            return {}, "offline_truth_global_track_mapping_conflict"
        mapping[key] = value
    if not saw_mapping_field:
        return {}, "offline_truth_labels_lack_global_track_mapping"
    return mapping, None


def _assigned_track_for_proximity_event(
    event: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> str | None:
    explicit = event.get("assigned_global_track_id", event.get("global_track_id"))
    if explicit is not None:
        return str(explicit)
    timestamp = event.get("timestamp")
    resource_id = event.get("resource_id")
    if not _is_finite_number(timestamp) or resource_id is None:
        return None
    selected: str | None = None
    for record in records:
        if record.get("topic") != "modules.d3.assignment_plan":
            continue
        record_timestamp = record.get("timestamp")
        if not _is_finite_number(record_timestamp) or float(record_timestamp) > float(timestamp):
            continue
        assignments = _payload(record).get("assignments")
        if not isinstance(assignments, list):
            continue
        for assignment in assignments:
            if not isinstance(assignment, Mapping):
                continue
            if str(assignment.get("resource_id")) == str(resource_id):
                value = assignment.get("global_track_id")
                if value is not None:
                    selected = str(value)
    return selected


def _add_stage_columns(row: dict[str, Any], stage_names: Sequence[str]) -> None:
    stages = row.get("_stage_records", {})
    file_reason = row.get("_stage_file_reason")
    for stage in stage_names:
        prefix = f"stage__{_stage_slug(stage)}"
        record = stages.get(stage) if isinstance(stages, Mapping) else None
        missing_stage_reason = (
            str(file_reason)
            if file_reason is not None
            else f"stage_not_reported:{stage}"
        )
        for source, suffix in (
            ("call_count", "call_count"),
            ("wall_time_s", "wall_time_s"),
            ("mean_wall_time_ms", "mean_wall_time_ms"),
        ):
            field = f"{prefix}__{suffix}"
            if isinstance(record, Mapping) and record.get(source) is not None:
                _put_available(row, field, record[source])
            else:
                _put_unavailable(row, field, missing_stage_reason)

        distribution_available = (
            isinstance(record, Mapping)
            and record.get("distribution_available") is True
        )
        distribution_reason = (
            record.get("distribution_unavailable_reason")
            if isinstance(record, Mapping)
            else missing_stage_reason
        )
        if distribution_available:
            distribution_reason = None
        elif distribution_reason is None:
            distribution_reason = f"stage_distribution_unavailable:{stage}"
        row[f"{prefix}__distribution_availability"] = (
            "available" if distribution_available else "unavailable"
        )
        row[f"{prefix}__distribution_unavailable_reason"] = distribution_reason
        for source in _STAGE_TIMING_QUANTILE_FIELDS:
            field = f"{prefix}__{source}"
            if distribution_available and record.get(source) is not None:
                _put_available(row, field, record[source])
            else:
                _put_unavailable(row, field, str(distribution_reason))
    if file_reason is None:
        _put_available(row, "stage_timings_json", stages)
    else:
        _put_unavailable(row, "stage_timings_json", str(file_reason))


def _finalize_episode_status(row: dict[str, Any]) -> None:
    failures = list(row.get("_failure_reasons", []))
    online_truth_use_count = _available_nonnegative_int(
        row,
        "online_truth_use_count",
    )
    online_truth_field_violation_count = _available_nonnegative_int(
        row,
        "online_truth_field_violation_count",
    )
    active_vision_target_reference_violation_count = _available_nonnegative_int(
        row,
        "d5_active_vision_target_reference_violation_count",
    )
    active_vision_ack_target_mismatch_count = _available_nonnegative_int(
        row,
        "d5_active_vision_ack_target_mismatch_count",
    )
    if row.get("finite_state_availability") == "available" and row.get("finite_state") is False:
        failures.append("non_finite_world_state")
    if online_truth_use_count is not None and online_truth_use_count > 0:
        failures.append("online_truth_use_nonzero")
    if (
        online_truth_field_violation_count is not None
        and online_truth_field_violation_count > 0
    ):
        failures.append("online_truth_field_violation")
    if (
        active_vision_target_reference_violation_count is not None
        and active_vision_target_reference_violation_count > 0
    ):
        failures.append("d5_active_vision_unknown_center_track_reference")
    if (
        active_vision_ack_target_mismatch_count is not None
        and active_vision_ack_target_mismatch_count > 0
    ):
        failures.append("d5_active_vision_ack_target_reference_mismatch")
    if row.get("repository_dirty") is True:
        failures.append("repository_dirty_not_formal_evidence")
    if row.get("config_hash_match") is False:
        failures.append("config_hash_mismatch")
    d4_reasons = row.get("d4_fail_closed_reasons_json")
    if isinstance(d4_reasons, Mapping):
        failures.extend(f"d4_fail_closed:{reason}" for reason in d4_reasons)
    failures = list(dict.fromkeys(str(value) for value in failures if str(value)))

    critical_fields = (
        "finite_state",
        "repository_dirty",
        "config_hash_match",
        "current_schema_contract_match",
        "offline_truth_disposition_contract_valid",
        "d4_policy_version",
        "online_truth_use_count",
        "online_truth_field_violation_count",
    )
    critical_available = all(
        row.get(f"{field}_availability") == "available" for field in critical_fields
    )
    eligible = (
        critical_available
        and row.get("finite_state") is True
        and row.get("repository_dirty") is False
        and row.get("config_hash_match") is True
        and row.get("current_schema_contract_match") is True
        and row.get("offline_truth_disposition_contract_valid") is True
        and row.get("online_truth_use_count") == 0
        and row.get("online_truth_field_violation_count") == 0
        and not any(
            reason.startswith(
                (
                    "provenance_field_mismatch:",
                    "schema_contract_",
                    "d1_track_count_mismatch",
                    "d2_track_count_mismatch",
                    "learning_runtime_metadata_mismatch",
                    "learning_runtime_version_mismatch:",
                    "learning_model_fingerprint_invalid:",
                    "loaded_learning_bundle_fingerprint_unavailable:",
                    "learning_model_version_fingerprint_mismatch:",
                    "d4_advice_missing_for_requested_runtime",
                    "d4_advice_payload_invalid",
                    "d4_advice_version_evidence_issue",
                    "d4_advice_resource_quota_conservation_violation",
                    "d4_advice_formal_decision_mutation",
                    "d4_region_consumption_",
                    "d1_centroid_overlay_shadow_",
                    "d5_active_vision_",
                    "observation_governance_generation_integrity:",
                    "offline_truth_disposition_contract:",
                )
            )
            for reason in failures
        )
    )
    _put_available(row, "formal_acceptance_eligible", eligible)
    failures.extend(finalize_experiment_matrix_evidence(row))
    failures = list(dict.fromkeys(str(value) for value in failures if str(value)))
    row["episode_failure_reasons_json"] = failures
    unavailable_reasons = sorted(
        {
            str(value)
            for key, value in row.items()
            if key.endswith("_unavailable_reason") and value is not None
        }
    )
    row["evidence_unavailability_reasons_json"] = unavailable_reasons
    if (
        eligible
        and row.get("experiment_matrix_formal_acceptance_eligible") is True
    ):
        row["episode_evidence_status"] = "clean_formal_experiment_matrix"
    elif eligible and row.get("experiment_matrix_declared") is not True:
        row["episode_evidence_status"] = "descriptive_clean_source_calibration"
    else:
        row["episode_evidence_status"] = "descriptive_or_incomplete_evidence"


def _available_nonnegative_int(row: dict[str, Any], field: str) -> int | None:
    """Read an available count without coercing missing evidence to zero."""

    if row.get(f"{field}_availability") != "available":
        return None
    value = row.get(field)
    if not _is_int_like(value) or int(value) < 0:
        _put_unavailable(
            row,
            field,
            f"status_finalization_count_missing_or_invalid:{field}",
        )
        return None
    return int(value)


def _validate_provenance_consistency(
    row: dict[str, Any],
    manifest: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None,
    summary: Mapping[str, Any] | None,
) -> None:
    for field in ("scenario_name", "scenario_version", "seed"):
        values = [
            value[field]
            for value in (manifest, config, summary)
            if isinstance(value, Mapping) and field in value and value[field] is not None
        ]
        if values and any(value != values[0] for value in values[1:]):
            row["_failure_reasons"].append(f"provenance_field_mismatch:{field}")
    for field in _LEARNING_MODULE_VERSION_FIELDS.values():
        values = [
            value[field]
            for value in (manifest, config)
            if isinstance(value, Mapping)
            and field in value
            and value[field] is not None
        ]
        if values and any(value != values[0] for value in values[1:]):
            row["_failure_reasons"].append(f"provenance_field_mismatch:{field}")
    for field in ("target_count", "resource_count", "recon_count"):
        values = [
            value[field]
            for value in (config, summary)
            if isinstance(value, Mapping) and field in value and value[field] is not None
        ]
        if values and any(value != values[0] for value in values[1:]):
            row["_failure_reasons"].append(f"provenance_field_mismatch:{field}")


def _extract_current_schema_contract(row: dict[str, Any]) -> None:
    """Compare persisted schema provenance with D6's versioned current registry.

    Raw manifest/config fields remain untouched for historical inspection.  A
    syntactically present but old, unknown, or tampered value is available as a
    raw value while its current-contract match is explicitly false.
    """

    details: dict[str, dict[str, Any]] = {}
    failure_reasons: list[str] = []
    unavailable_fields: list[str] = []
    for field, expected in SCALABLE_3D_CURRENT_SCHEMA_REGISTRY.items():
        match_field = f"{field}_current_contract_match"
        observed_available = row.get(f"{field}_availability") == "available"
        observed = row.get(field)
        if not observed_available:
            reason = f"schema_contract_unavailable:{field}"
            unavailable_fields.append(field)
            failure_reasons.append(reason)
            _put_unavailable(row, match_field, reason)
            details[field] = {
                "observed": observed,
                "expected_current": expected,
                "match": None,
                "status": "unavailable",
                "reason": reason,
            }
            continue

        match = isinstance(observed, str) and observed == expected
        reason = None
        if not match:
            reason = (
                f"schema_contract_mismatch:{field}:"
                f"expected={expected}:observed={observed}"
            )
            failure_reasons.append(reason)
        _put_available(row, match_field, match)
        row[f"{match_field}_failure_reason"] = reason
        details[field] = {
            "observed": observed,
            "expected_current": expected,
            "match": match,
            "status": "current" if match else "historical_or_unknown_read_only",
            "reason": reason,
        }

    _put_available(
        row,
        "schema_contract_registry_version",
        SCALABLE_3D_SCHEMA_REGISTRY_VERSION,
    )
    _put_available(
        row,
        "current_schema_registry_json",
        SCALABLE_3D_CURRENT_SCHEMA_REGISTRY,
    )
    _put_available(row, "current_schema_contract_details_json", details)
    _put_available(
        row,
        "current_schema_contract_failure_reasons_json",
        failure_reasons,
    )
    if unavailable_fields:
        _put_unavailable(
            row,
            "current_schema_contract_match",
            "schema_contract_fields_unavailable:" + ",".join(unavailable_fields),
        )
    else:
        _put_available(
            row,
            "current_schema_contract_match",
            not failure_reasons,
        )
    row["_failure_reasons"].extend(failure_reasons)


def _load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"artifact_missing:{path.name}"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Scalable3DOfflineEvaluationError(f"invalid JSON object {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise Scalable3DOfflineEvaluationError(f"JSON artifact is not an object: {path}")
    return dict(value), None


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not path.is_file():
        return None, f"artifact_missing:{path.name}"
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Scalable3DOfflineEvaluationError(f"cannot read {path}: {exc}") from exc
    for line_number, text in enumerate(lines, start=1):
        if not text.strip():
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise Scalable3DOfflineEvaluationError(
                f"invalid JSONL {path}:{line_number}: {exc}"
            ) from exc
        if not isinstance(value, Mapping):
            raise Scalable3DOfflineEvaluationError(
                f"JSONL record is not an object: {path}:{line_number}"
            )
        records.append(dict(value))
    return records, None


def _load_stage_timings(
    path: Path,
) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    if not path.is_file():
        return None, f"artifact_missing:{path.name}"
    records: dict[str, dict[str, Any]] = {}
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            fieldnames = reader.fieldnames
            if fieldnames is None:
                raise Scalable3DOfflineEvaluationError(
                    f"stage timing header missing in {path}"
                )
            if any(not str(field).strip() for field in fieldnames):
                raise Scalable3DOfflineEvaluationError(
                    f"stage timing header contains an empty field in {path}"
                )
            if len(fieldnames) != len(set(fieldnames)):
                raise Scalable3DOfflineEvaluationError(
                    f"stage timing header contains duplicate fields in {path}"
                )
            missing_base = [
                field
                for field in _STAGE_TIMING_BASE_FIELDS
                if field not in fieldnames
            ]
            if missing_base:
                raise Scalable3DOfflineEvaluationError(
                    f"stage timing base fields missing in {path}: {missing_base}"
                )

            has_schema = "schema_version" in fieldnames
            quantile_columns = [
                field
                for field in _STAGE_TIMING_QUANTILE_FIELDS
                if field in fieldnames
            ]
            availability_columns = [
                field
                for field in _STAGE_TIMING_AVAILABILITY_FIELDS
                if field in fieldnames
            ]
            if has_schema:
                missing_v2 = [
                    field
                    for field in (
                        *_STAGE_TIMING_QUANTILE_FIELDS,
                        *_STAGE_TIMING_AVAILABILITY_FIELDS,
                    )
                    if field not in fieldnames
                ]
                if missing_v2:
                    raise Scalable3DOfflineEvaluationError(
                        f"v2 stage timing fields missing in {path}: {missing_v2}"
                    )
                timing_mode = "v2"
            else:
                if len(quantile_columns) not in {
                    0,
                    len(_STAGE_TIMING_QUANTILE_FIELDS),
                }:
                    raise Scalable3DOfflineEvaluationError(
                        f"legacy stage timing quantile fields are partial in {path}"
                    )
                if availability_columns:
                    raise Scalable3DOfflineEvaluationError(
                        "legacy stage timing cannot declare distribution availability "
                        f"without schema_version in {path}"
                    )
                timing_mode = "legacy"

            for line_number, record in enumerate(reader, start=2):
                if None in record:
                    raise Scalable3DOfflineEvaluationError(
                        f"stage timing row has extra values at {path}:{line_number}"
                    )
                stage = str(record.get("stage", "")).strip()
                if not stage:
                    raise Scalable3DOfflineEvaluationError(
                        f"stage name missing at {path}:{line_number}"
                    )
                if stage in records:
                    raise Scalable3DOfflineEvaluationError(
                        f"duplicate stage {stage!r} in {path}"
                    )
                parsed: dict[str, Any] = {
                    "call_count": _parse_stage_timing_number(
                        record,
                        "call_count",
                        path=path,
                        line_number=line_number,
                        integer=True,
                    ),
                    "wall_time_s": _parse_stage_timing_number(
                        record,
                        "wall_time_s",
                        path=path,
                        line_number=line_number,
                    ),
                    "mean_wall_time_ms": _parse_stage_timing_number(
                        record,
                        "mean_wall_time_ms",
                        path=path,
                        line_number=line_number,
                    ),
                }
                if timing_mode == "v2":
                    schema_version = str(record.get("schema_version", "")).strip()
                    if schema_version != SCALABLE_3D_STAGE_TIMING_SCHEMA_VERSION:
                        raise Scalable3DOfflineEvaluationError(
                            "unsupported stage timing schema at "
                            f"{path}:{line_number}: {schema_version or '<empty>'}"
                        )
                    distribution_available = _parse_stage_timing_bool(
                        record.get("distribution_available"),
                        path=path,
                        line_number=line_number,
                    )
                    unavailable_reason = (
                        str(record.get("distribution_unavailable_reason") or "").strip()
                        or None
                    )
                    raw_quantiles = [
                        record.get(field) for field in _STAGE_TIMING_QUANTILE_FIELDS
                    ]
                    present_count = sum(
                        value is not None and str(value).strip() != ""
                        for value in raw_quantiles
                    )
                    if distribution_available:
                        if present_count != len(_STAGE_TIMING_QUANTILE_FIELDS):
                            raise Scalable3DOfflineEvaluationError(
                                "available v2 stage timing distribution must provide "
                                f"all quantiles at {path}:{line_number}"
                            )
                        if unavailable_reason is not None:
                            raise Scalable3DOfflineEvaluationError(
                                "available v2 stage timing distribution cannot provide "
                                f"an unavailable reason at {path}:{line_number}"
                            )
                    else:
                        if present_count:
                            raise Scalable3DOfflineEvaluationError(
                                "unavailable v2 stage timing distribution must leave "
                                f"all quantiles empty at {path}:{line_number}"
                            )
                        if unavailable_reason is None:
                            raise Scalable3DOfflineEvaluationError(
                                "unavailable v2 stage timing distribution requires "
                                f"a reason at {path}:{line_number}"
                            )
                    parsed["schema_version"] = schema_version
                    parsed["distribution_availability_source"] = "explicit_v2"
                else:
                    schema_version = None
                    unavailable_reason = None
                    if quantile_columns:
                        raw_quantiles = [
                            record.get(field)
                            for field in _STAGE_TIMING_QUANTILE_FIELDS
                        ]
                        present_count = sum(
                            value is not None and str(value).strip() != ""
                            for value in raw_quantiles
                        )
                        if present_count not in {
                            0,
                            len(_STAGE_TIMING_QUANTILE_FIELDS),
                        }:
                            raise Scalable3DOfflineEvaluationError(
                                "legacy stage timing distribution values are partial "
                                f"at {path}:{line_number}"
                            )
                        distribution_available = present_count == len(
                            _STAGE_TIMING_QUANTILE_FIELDS
                        )
                        if not distribution_available:
                            unavailable_reason = (
                                "legacy_stage_timing_distribution_values_absent"
                            )
                    else:
                        distribution_available = False
                        unavailable_reason = (
                            "legacy_stage_timing_distribution_columns_absent"
                        )
                    parsed["schema_version"] = schema_version
                    parsed["distribution_availability_source"] = "legacy_inferred"

                if distribution_available:
                    for field in _STAGE_TIMING_QUANTILE_FIELDS:
                        parsed[field] = _parse_stage_timing_number(
                            record,
                            field,
                            path=path,
                            line_number=line_number,
                        )
                    _validate_stage_timing_distribution(
                        parsed,
                        path=path,
                        line_number=line_number,
                    )
                else:
                    for field in _STAGE_TIMING_QUANTILE_FIELDS:
                        parsed[field] = None
                parsed["distribution_available"] = distribution_available
                parsed["distribution_unavailable_reason"] = unavailable_reason
                records[stage] = parsed
    except OSError as exc:
        raise Scalable3DOfflineEvaluationError(f"cannot read {path}: {exc}") from exc
    return records, None


def _parse_stage_timing_number(
    record: Mapping[str, Any],
    field: str,
    *,
    path: Path,
    line_number: int,
    integer: bool = False,
) -> int | float:
    raw = record.get(field)
    if raw is None or str(raw).strip() == "":
        raise Scalable3DOfflineEvaluationError(
            f"required stage timing field {field} missing at {path}:{line_number}"
        )
    try:
        value = int(raw) if integer else float(raw)
    except (TypeError, ValueError) as exc:
        raise Scalable3DOfflineEvaluationError(
            f"invalid {field} at {path}:{line_number}"
        ) from exc
    if not _is_finite_number(value) or value < 0:
        raise Scalable3DOfflineEvaluationError(
            f"nonfinite or negative {field} at {path}:{line_number}"
        )
    return value


def _parse_stage_timing_bool(
    value: Any,
    *,
    path: Path,
    line_number: int,
) -> bool:
    normalized = "" if value is None else str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise Scalable3DOfflineEvaluationError(
        "distribution_available must be true or false at "
        f"{path}:{line_number}"
    )


def _validate_stage_timing_distribution(
    record: Mapping[str, Any],
    *,
    path: Path,
    line_number: int,
) -> None:
    p50 = float(record["p50_wall_time_ms"])
    p95 = float(record["p95_wall_time_ms"])
    maximum = float(record["max_wall_time_ms"])
    mean = float(record["mean_wall_time_ms"])
    if not p50 <= p95 <= maximum:
        raise Scalable3DOfflineEvaluationError(
            f"stage timing distribution must satisfy p50 <= p95 <= max at "
            f"{path}:{line_number}"
        )
    tolerance = max(1.0e-12, abs(maximum) * 1.0e-12)
    if mean > maximum + tolerance:
        raise Scalable3DOfflineEvaluationError(
            f"mean stage timing cannot exceed max at {path}:{line_number}"
        )


def _ordered_online_records(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized = [dict(record) for record in records]
    return sorted(
        normalized,
        key=lambda record: (
            float(record["timestamp"])
            if _is_finite_number(record.get("timestamp"))
            else math.inf,
            int(record["sequence"])
            if _is_int_like(record.get("sequence"))
            else 2**63 - 1,
        ),
    )


def _payload(record: Mapping[str, Any]) -> dict[str, Any]:
    value = record.get("payload")
    return dict(value) if isinstance(value, Mapping) else {}


def _latest_topic(
    records: Sequence[Mapping[str, Any]], topic: str
) -> Mapping[str, Any] | None:
    for record in reversed(records):
        if record.get("topic") == topic:
            return record
    return None


def _count_forbidden_online_fields(value: Any) -> int:
    count = 0
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, Mapping):
            for key, child in item.items():
                normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
                if (
                    normalized in _FORBIDDEN_ONLINE_KEYS
                    or normalized.startswith("truth_")
                    or normalized.endswith("_truth_id")
                    or normalized.endswith("_actor_id")
                ):
                    count += 1
                pending.append(child)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            pending.extend(item)
    return count


def _put_distribution(
    row: dict[str, Any],
    prefix: str,
    values: Sequence[float],
    *,
    unit_suffix: str,
) -> None:
    array = np.asarray(values, dtype=float)
    for label, value in (
        ("p50", np.percentile(array, 50.0)),
        ("p90", np.percentile(array, 90.0)),
        ("max", np.max(array)),
    ):
        _put_available(row, f"{prefix}_{label}{unit_suffix}", float(value))


def _put_available(row: dict[str, Any], field: str, value: Any) -> None:
    row[field] = _json_ready(value)
    row[f"{field}_availability"] = "available"
    row[f"{field}_unavailable_reason"] = None


def _put_unavailable(row: dict[str, Any], field: str, reason: str) -> None:
    row[field] = None
    row[f"{field}_availability"] = "unavailable"
    row[f"{field}_unavailable_reason"] = str(reason)


def _first_explicit_field(
    sources: Sequence[tuple[str, Mapping[str, Any] | None]], field: str
) -> tuple[Any, str | None, str | None]:
    for source, payload in sources:
        if payload is not None and field in payload and payload[field] is not None:
            return payload[field], source, None
    return None, None, f"explicit_field_missing:{field}"


def _aggregate_metric_names(rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    dynamic = {
        key
        for row in rows
        for key in row
        if key.startswith("stage__")
        and not key.endswith(("_availability", "_unavailable_reason"))
    }
    return tuple(dict.fromkeys((*_METRIC_FIELDS, *sorted(dynamic))))


def _metric_statistics(
    rows: Sequence[Mapping[str, Any]],
    metric: str,
    *,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
    group_identity: Mapping[str, Any],
) -> dict[str, Any]:
    values: list[float] = []
    seed_values: dict[int, list[float]] = defaultdict(list)
    unavailable = Counter()
    for row in rows:
        value = row.get(metric)
        availability = row.get(f"{metric}_availability")
        if availability == "available" and _is_metric_number(value):
            numeric = float(int(value) if isinstance(value, bool) else value)
            values.append(numeric)
            if _is_int_like(row.get("seed")):
                seed_values[int(row["seed"])].append(numeric)
        else:
            reason = row.get(f"{metric}_unavailable_reason")
            unavailable[str(reason or "metric_unavailable_without_reason")] += 1
    if not values:
        return {
            "availability": "unavailable",
            "unavailable_reason": "no_available_episode_values",
            "unavailability_reason_distribution": dict(sorted(unavailable.items())),
            "episode_value_count": 0,
            "seed_value_count": 0,
            "mean": None,
            "standard_deviation": None,
            "minimum": None,
            "maximum": None,
            "bootstrap_ci95_low": None,
            "bootstrap_ci95_high": None,
            "bootstrap_availability": "unavailable",
            "bootstrap_unavailable_reason": "no_available_episode_values",
        }
    array = np.asarray(values, dtype=float)
    seed_means = [float(np.mean(seed_values[seed])) for seed in sorted(seed_values)]
    if len(seed_means) >= 2:
        seed_material = json.dumps(
            {"group": group_identity, "metric": metric},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        offset = int.from_bytes(hashlib.sha256(seed_material).digest()[:4], "big")
        low, high = _bootstrap_mean_ci(
            seed_means,
            resamples=bootstrap_resamples,
            rng_seed=(int(bootstrap_rng_seed) + offset) % (2**32),
        )
        bootstrap_availability = "available"
        bootstrap_reason = None
    else:
        low = high = None
        bootstrap_availability = "unavailable"
        bootstrap_reason = "single_seed_descriptive_only"
    return {
        "availability": "available",
        "unavailable_reason": None,
        "unavailability_reason_distribution": dict(sorted(unavailable.items())),
        "episode_value_count": len(values),
        "seed_value_count": len(seed_means),
        "mean": float(np.mean(array)),
        "standard_deviation": float(np.std(array, ddof=0)),
        "standard_deviation_semantics": "descriptive_population_std",
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
        "bootstrap_ci95_low": low,
        "bootstrap_ci95_high": high,
        "bootstrap_availability": bootstrap_availability,
        "bootstrap_unavailable_reason": bootstrap_reason,
        "bootstrap_resamples": bootstrap_resamples,
        "bootstrap_rng_seed": bootstrap_rng_seed,
    }


def _bootstrap_mean_ci(
    values: Sequence[float], *, resamples: int, rng_seed: int
) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    rng = np.random.default_rng(int(rng_seed))
    indices = rng.integers(0, len(array), size=(int(resamples), len(array)))
    means = np.mean(array[indices], axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _aggregate_stage_timing(
    rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
    group_identity: Mapping[str, Any],
) -> dict[str, Any]:
    stage_names = sorted(
        {
            stage
            for row in rows
            for stage in row.get("_stage_records", {})
        }
    )
    output: dict[str, Any] = {}
    pooled_total = sum(
        float(record.get("wall_time_s"))
        for row in rows
        for record in row.get("_stage_records", {}).values()
        if _is_finite_number(record.get("wall_time_s"))
    )
    for stage in stage_names:
        slug = _stage_slug(stage)
        prefix = f"stage__{slug}"
        timing_rows: list[dict[str, Any]] = []
        distribution_unavailable = Counter()
        distribution_available_episode_count = 0
        distribution_available_seeds: set[int] = set()
        for row in rows:
            prepared = dict(row)
            if f"{prefix}__p50_wall_time_ms_availability" not in prepared:
                _add_stage_columns(prepared, (stage,))
            timing_rows.append(prepared)
            stage_map = row.get("_stage_records", {})
            record = (
                stage_map.get(stage)
                if isinstance(stage_map, Mapping)
                else None
            )
            if (
                isinstance(record, Mapping)
                and record.get("distribution_available") is True
            ):
                distribution_available_episode_count += 1
                if _is_int_like(row.get("seed")):
                    distribution_available_seeds.add(int(row["seed"]))
            else:
                reason = (
                    record.get("distribution_unavailable_reason")
                    if isinstance(record, Mapping)
                    else row.get("_stage_file_reason")
                )
                distribution_unavailable[
                    str(reason or f"stage_not_reported:{stage}")
                ] += 1
        shares: list[float] = []
        share_seed_values: dict[int, list[float]] = defaultdict(list)
        pooled_stage = 0.0
        for row in rows:
            stage_map = row.get("_stage_records", {})
            record = stage_map.get(stage) if isinstance(stage_map, Mapping) else None
            if isinstance(record, Mapping) and _is_finite_number(record.get("wall_time_s")):
                pooled_stage += float(record["wall_time_s"])
            episode_total = sum(
                float(item.get("wall_time_s"))
                for item in stage_map.values()
                if isinstance(item, Mapping) and _is_finite_number(item.get("wall_time_s"))
            )
            if (
                isinstance(record, Mapping)
                and _is_finite_number(record.get("wall_time_s"))
                and episode_total > 0.0
            ):
                share = float(record["wall_time_s"]) / episode_total
                shares.append(share)
                if _is_int_like(row.get("seed")):
                    share_seed_values[int(row["seed"])].append(share)
        share_stats = _plain_statistics(shares)
        seed_share_means = [
            float(np.mean(share_seed_values[seed])) for seed in sorted(share_seed_values)
        ]
        if len(seed_share_means) >= 2:
            material = json.dumps(
                {"group": group_identity, "stage": stage, "metric": "share"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            offset = int.from_bytes(hashlib.sha256(material).digest()[:4], "big")
            ci_low, ci_high = _bootstrap_mean_ci(
                seed_share_means,
                resamples=bootstrap_resamples,
                rng_seed=(bootstrap_rng_seed + offset) % (2**32),
            )
            ci_status = "available"
            ci_reason = None
        else:
            ci_low = ci_high = None
            ci_status = "unavailable"
            ci_reason = "single_seed_descriptive_only"
        if distribution_available_episode_count == len(rows):
            distribution_status = "available"
        elif distribution_available_episode_count:
            distribution_status = "partially_available"
        else:
            distribution_status = "unavailable"
        quantile_statistics = {
            field: _metric_statistics(
                timing_rows,
                f"{prefix}__{field}",
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=bootstrap_rng_seed,
                group_identity={
                    **group_identity,
                    "stage": stage,
                    "source_statistic": field,
                },
            )
            for field in _STAGE_TIMING_QUANTILE_FIELDS
        }
        for field, statistics in quantile_statistics.items():
            statistics["source_statistic_semantics"] = (
                f"within_episode_per_call_{field}"
            )
            statistics["cross_seed_aggregation_semantics"] = (
                "distribution_of_episode_level_call_quantiles_across_available_"
                "episodes_and_distinct_seed_means"
            )
            statistics["is_pooled_call_quantile"] = False

        output[stage] = {
            "call_count": _metric_statistics(
                timing_rows,
                f"{prefix}__call_count",
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=bootstrap_rng_seed,
                group_identity=group_identity,
            ),
            "wall_time_s": _metric_statistics(
                timing_rows,
                f"{prefix}__wall_time_s",
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=bootstrap_rng_seed,
                group_identity=group_identity,
            ),
            "mean_wall_time_ms": _metric_statistics(
                timing_rows,
                f"{prefix}__mean_wall_time_ms",
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=bootstrap_rng_seed,
                group_identity=group_identity,
            ),
            **quantile_statistics,
            "distribution_availability": distribution_status,
            "distribution_available_episode_count": (
                distribution_available_episode_count
            ),
            "distribution_unavailable_episode_count": (
                len(rows) - distribution_available_episode_count
            ),
            "distribution_available_seed_count": len(
                distribution_available_seeds
            ),
            "distribution_unavailability_reason_distribution": dict(
                sorted(distribution_unavailable.items())
            ),
            "pooled_call_quantiles": {
                "availability": "unavailable",
                "unavailable_reason": "raw_per_call_timing_samples_not_persisted",
                "p50_wall_time_ms": None,
                "p95_wall_time_ms": None,
                "max_wall_time_ms": None,
            },
            "pooled_wall_time_share": (
                pooled_stage / pooled_total if pooled_total > 0.0 else None
            ),
            "per_episode_wall_time_share": share_stats,
            "share_bootstrap_ci95_low": ci_low,
            "share_bootstrap_ci95_high": ci_high,
            "share_bootstrap_availability": ci_status,
            "share_bootstrap_unavailable_reason": ci_reason,
        }
    return output


def _aggregate_exact_seed_groups(
    rows: Sequence[Mapping[str, Any]], metric_names: Sequence[str]
) -> list[dict[str, Any]]:
    grouped: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("seed")].append(row)
    output = []
    for seed in sorted(grouped, key=lambda value: (value is None, value)):
        seed_rows = grouped[seed]
        metrics = {}
        for metric in metric_names:
            values = [
                float(row[metric])
                for row in seed_rows
                if row.get(f"{metric}_availability") == "available"
                and _is_metric_number(row.get(metric))
            ]
            metrics[metric] = _plain_statistics(values)
        output.append(
            {
                "seed": seed,
                "episode_count": len(seed_rows),
                "inference_status": "descriptive_only",
                "metric_statistics": metrics,
            }
        )
    return output


def _plain_statistics(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {
            "availability": "unavailable",
            "count": 0,
            "mean": None,
            "standard_deviation": None,
            "minimum": None,
            "maximum": None,
        }
    array = np.asarray(values, dtype=float)
    return {
        "availability": "available",
        "count": len(values),
        "mean": float(np.mean(array)),
        "standard_deviation": float(np.std(array, ddof=0)),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
    }


def _write_stage_timing_curves(aggregate: Mapping[str, Any], path: Path) -> None:
    groups = list(aggregate.get("groups", []))
    labels = [
        f"T{group.get('target_count')}/R{group.get('resource_count')}\nRc{group.get('recon_count')}/C{group.get('camera_count')}"
        for group in groups
    ]
    stages = sorted(
        {
            stage
            for group in groups
            for stage in group.get("stage_timing", {})
        },
        key=lambda stage: -sum(
            float(group.get("stage_timing", {}).get(stage, {}).get("pooled_wall_time_share") or 0.0)
            for group in groups
        ),
    )[:8]
    figure, (time_axis, share_axis) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    x = np.arange(len(groups), dtype=float)
    colors = plt.get_cmap("tab10")
    for index, stage in enumerate(stages):
        mean_ms = [
            group.get("stage_timing", {})
            .get(stage, {})
            .get("mean_wall_time_ms", {})
            .get("mean")
            for group in groups
        ]
        shares = [
            group.get("stage_timing", {}).get(stage, {}).get("pooled_wall_time_share")
            for group in groups
        ]
        time_axis.plot(
            x,
            [np.nan if value is None else value for value in mean_ms],
            marker="o",
            linewidth=1.5,
            label=stage,
            color=colors(index % 10),
        )
        share_axis.plot(
            x,
            [np.nan if value is None else value for value in shares],
            marker="o",
            linewidth=1.5,
            label=stage,
            color=colors(index % 10),
        )
    if not groups:
        time_axis.text(0.5, 0.5, "No episode groups", ha="center", va="center")
        share_axis.text(0.5, 0.5, "No stage timing evidence", ha="center", va="center")
    time_axis.set_ylabel("Mean call time (ms)")
    time_axis.set_title("Scalable 3D stage timing by explicit scale")
    time_axis.grid(True, alpha=0.25)
    share_axis.set_ylabel("Pooled wall-time share")
    share_axis.set_xlabel("Explicit target/resource/recon/camera counts")
    share_axis.grid(True, alpha=0.25)
    share_axis.set_xticks(x, labels, rotation=0)
    if stages:
        time_axis.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)
        share_axis.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def _write_rows_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _public_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _counter_from_json_field(
    rows: Sequence[Mapping[str, Any]], field: str
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(field)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            counter.update(str(item) for item in value)
    return dict(sorted(counter.items()))


def _counter_from_mapping_field(
    rows: Sequence[Mapping[str, Any]], field: str
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(field)
        if isinstance(value, Mapping):
            for key, count in value.items():
                if _is_int_like(count):
                    counter[str(key)] += int(count)
    return dict(sorted(counter.items()))


def _counter_from_scalar_field(
    rows: Sequence[Mapping[str, Any]], field: str
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        if row.get(f"{field}_availability") != "available":
            continue
        value = row.get(field)
        if value is not None:
            counter[str(value)] += 1
    return dict(sorted(counter.items()))


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_ready(item) for item in value]
    return value


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value


def _stage_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_") or "unnamed"


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, bool
    ) and math.isfinite(float(value))


def _is_metric_number(value: Any) -> bool:
    return isinstance(value, bool) or _is_finite_number(value)


def _is_int_like(value: Any) -> bool:
    return isinstance(value, (int, np.integer)) and not isinstance(value, bool)


def _sortable_group_key(key: tuple[Any, ...]) -> tuple[Any, ...]:
    scenario_name, scenario_version, *counts = key
    return (
        "" if scenario_name is None else str(scenario_name),
        "" if scenario_version is None else str(scenario_version),
        *(
            (1, math.inf) if value is None else (0, float(value))
            for value in counts
        ),
    )


def _fmt(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _fmt_available(row: Mapping[str, Any], field: str) -> str:
    if row.get(f"{field}_availability") != "available":
        reason = row.get(f"{field}_unavailable_reason")
        return f"unavailable({reason})"
    return _fmt(row.get(field))


def _fmt_stat(value: Any) -> str:
    if not isinstance(value, Mapping) or value.get("availability") != "available":
        return "unavailable"
    return _fmt(value.get("mean"))


def _fmt_stage_quantile_stat(value: Any) -> str:
    if not isinstance(value, Mapping) or value.get("availability") != "available":
        return "unavailable"
    return "{} [{}, {}]".format(
        _fmt(value.get("mean")),
        _fmt(value.get("minimum")),
        _fmt(value.get("maximum")),
    )


__all__ = [
    "DEFAULT_SCALABLE_3D_BOOTSTRAP_RESAMPLES",
    "DEFAULT_SCALABLE_3D_BOOTSTRAP_RNG_SEED",
    "FIVE_METER_THRESHOLD_M",
    "EXPERIMENT_MATRIX_SCHEMA_VERSION",
    "EXPERIMENT_MATRIX_VARIANTS",
    "SCALABLE_3D_CURRENT_SCHEMA_REGISTRY",
    "SCALABLE_3D_OFFLINE_EVALUATION_DATE",
    "SCALABLE_3D_OFFLINE_EVALUATION_SCHEMA_VERSION",
    "SCALABLE_3D_SCHEMA_REGISTRY_VERSION",
    "SCALABLE_3D_STAGE_TIMING_SCHEMA_VERSION",
    "Scalable3DOfflineEvaluationError",
    "Scalable3DOfflineEvaluationInputs",
    "Scalable3DOfflineReportGenerator",
    "aggregate_experiment_matrix",
    "aggregate_scalable_3d_episodes",
    "discover_scalable_3d_episode_dirs",
    "evaluate_scalable_3d_episode",
    "extract_experiment_matrix_evidence",
    "finalize_experiment_matrix_evidence",
    "render_experiment_matrix_markdown_lines",
    "render_scalable_3d_offline_markdown",
]
