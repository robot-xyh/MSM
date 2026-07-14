"""Availability-aware merge of replay and main-bus execution metrics."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


EXECUTION_METRICS_MERGE_SCHEMA_VERSION = "d6.execution-metrics-merge.v1"

# These values describe what happened in the online/main-bus execution path.
# Replay still contributes the remaining offline metrics and remains visible in
# per-metric provenance when an execution value supersedes it.
EXECUTION_CANONICAL_METRIC_NAMES = (
    "terminal_association_accuracy",
    "terminal_id_switch_count",
    "ambiguous_fov_event_count",
    "friend_overlap_hold_count",
    "time_to_terminal_lock",
    "terminal_lock_count",
    "multi_view_consensus_rate",
    "cross_view_conflict_count",
    "duplicate_terminal_lock_count",
    "visual_detection_recall",
    "local_id_continuity",
    "cross_view_registration_rate",
    "visual_pipeline_latency_ms",
    "visual_cpu_budget_utilization",
    "visual_gpu_budget_utilization",
    "visual_budget_violation_count",
    "online_truth_field_violation_count",
    "secondary_network_joint_full_view_frame_rate",
    "secondary_network_mean_coverage_ratio",
    "secondary_single_camera_full_view_frame_rate",
    "cross_view_association_count",
    "secondary_detect_available_but_not_registered_count",
    "camera_quality_gate_pass_rate",
    "los_quality_gate_pass_rate",
    "maneuver_margin_gate_pass_rate",
    "terminal_switch_allowed_rate",
    "visual_png_switch_count",
    "terminal_takeover_rate",
    "terminal_switch_reject_count",
    "mode_switch_count",
    "terminal_contract_reject_count",
    "contract_evaluated_count",
    "contract_allowed_count",
    "contract_allowed_rate",
    "control_evaluated_count",
    "control_allowed_count",
    "control_allowed_rate",
    "mode_switched_count",
    "physical_intercept_count",
    "pair_physical_success_count",
    "pair_physical_success_rate",
    "target_intercept_success_count",
    "target_intercept_success_rate",
    "coalition_completion_count",
    "coalition_completion_rate",
    "detection_acquisition_timeout_count",
    "image_kf_predict_count",
    "blind_push_count",
    "visual_reacquisition_count",
    "terminal_visual_lost_after_coast_count",
    "truth_identity_online_use_count",
    "terminal_filter_measured_count",
    "terminal_filter_predicted_count",
    "terminal_filter_innovation_rejected_count",
    "terminal_filter_reset_count",
    "terminal_filter_expired_count",
    "terminal_coast_count",
    "terminal_coast_duration_s",
    "terminal_coast_expired_count",
    "terminal_lock_continuity",
    "visual_mode_duration_s",
    "intercept_success_count",
    "collision_intercept_count",
    "range_intercept_count",
    "time_to_intercept_s",
    "min_range_m",
    "gate_reject_count",
)


def merge_replay_with_execution_metrics(
    replay_metrics: Mapping[str, Any] | Any,
    execution_metrics: Mapping[str, Any] | Any | None,
    *,
    persisted_frame_count: int | None = None,
    warmup_inclusive_frame_count: int | None = None,
) -> dict[str, Any]:
    """Merge persisted replay metrics with authoritative execution metrics.

    Inputs may be a plain metrics mapping, an existing ``{"metrics": ...}``
    bundle, or an object exposing ``to_dict()``. The function never mutates an
    input. Explicit main-bus execution values take precedence only for the
    online execution metrics listed in ``EXECUTION_CANONICAL_METRIC_NAMES``.
    Missing values remain unavailable; zero is accepted only when explicitly
    present in a source.
    """

    replay = _normalize_source(replay_metrics, source_name="integrated_replay")
    execution = _normalize_source(
        execution_metrics,
        source_name="main_episode_bus_execution",
    )
    merged_metrics = deepcopy(replay["metrics"])
    merged_metric_availability = _mapping_copy(
        merged_metrics.get("metric_availability")
    )
    provenance: dict[str, dict[str, Any]] = {}
    execution_value_merged = False

    for metric_name in EXECUTION_CANONICAL_METRIC_NAMES:
        replay_evidence = _metric_evidence(replay, metric_name)
        execution_evidence = _metric_evidence(execution, metric_name)
        selected = (
            execution_evidence
            if execution_evidence["available"]
            else replay_evidence
        )

        if selected["available"]:
            selected_availability = "available"
            merged_metrics[metric_name] = deepcopy(selected["value"])
            selected_source = str(selected["source"])
            merged_metric_availability[metric_name] = {
                "status": "available",
                "source": selected_source,
                "reason": selected["reason"] or "explicit persisted metric value",
            }
            if selected_source == "main_episode_bus_execution":
                execution_value_merged = True
        else:
            selected_source = None
            merged_metrics.pop(metric_name, None)
            unavailable_evidence = _preferred_unavailable_evidence(
                execution_evidence,
                replay_evidence,
            )
            selected_availability = str(unavailable_evidence["availability"])
            merged_metric_availability[metric_name] = {
                "status": unavailable_evidence["availability"],
                "source": (
                    unavailable_evidence["source"]
                    if unavailable_evidence["declared"]
                    else None
                ),
                "reason": unavailable_evidence["reason"],
            }

        provenance[metric_name] = {
            "selected_source": selected_source,
            "availability": selected_availability,
            "replay": replay_evidence,
            "execution": execution_evidence,
        }

    merged_metrics["metric_availability"] = merged_metric_availability
    frame_counts = _frame_count_summary(
        replay,
        execution,
        persisted_frame_count=persisted_frame_count,
        warmup_inclusive_frame_count=warmup_inclusive_frame_count,
    )
    merge_metadata = {
        "execution_metrics_merged": execution_value_merged,
        "metric_authority": "main_episode_bus_execution_when_available",
        "execution_metric_provenance": provenance,
        **frame_counts,
    }

    metrics_metadata = _mapping_copy(merged_metrics.get("metadata"))
    metrics_metadata.update(deepcopy(merge_metadata))
    merged_metrics["metadata"] = metrics_metadata

    top_metadata = deepcopy(replay["top_metadata"])
    top_metadata.update(deepcopy(merge_metadata))
    return {
        "schema_version": EXECUTION_METRICS_MERGE_SCHEMA_VERSION,
        "execution_metrics_merged": execution_value_merged,
        "metrics": merged_metrics,
        "metadata": top_metadata,
    }


def _normalize_source(value: Any, *, source_name: str) -> dict[str, Any]:
    if value is None:
        return {
            "source": source_name,
            "metrics": {},
            "top_metadata": {},
            "raw": {},
            "source_path": None,
        }
    if not isinstance(value, Mapping) and callable(getattr(value, "to_dict", None)):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        raise TypeError(f"{source_name} metrics must be a mapping or expose to_dict()")

    raw = deepcopy(dict(value))
    nested_metrics = raw.get("metrics")
    metrics = (
        deepcopy(dict(nested_metrics))
        if isinstance(nested_metrics, Mapping)
        else deepcopy(raw)
    )
    top_metadata = _mapping_copy(raw.get("metadata")) if nested_metrics is not None else {}
    metric_metadata = _mapping_copy(metrics.get("metadata"))
    source_path = (
        metric_metadata.get("source_path")
        or top_metadata.get("source_path")
        or raw.get("source_path")
    )
    return {
        "source": source_name,
        "metrics": metrics,
        "top_metadata": top_metadata,
        "raw": raw,
        "source_path": None if source_path is None else str(source_path),
    }


def _metric_evidence(source: Mapping[str, Any], metric_name: str) -> dict[str, Any]:
    metrics = source["metrics"]
    availability = _mapping_copy(metrics.get("metric_availability")).get(metric_name)
    recorded_status = (
        str(availability.get("status", "")).strip().lower()
        if isinstance(availability, Mapping)
        else ""
    )
    recorded_reason = (
        str(availability.get("reason", "")).strip()
        if isinstance(availability, Mapping)
        else ""
    )
    value_present = metric_name in metrics and metrics.get(metric_name) is not None
    available = value_present and recorded_status not in {
        "unavailable",
        "not_applicable",
    }
    normalized_status = (
        "available"
        if available
        else recorded_status
        if recorded_status in {"unavailable", "not_applicable"}
        else "unavailable"
    )
    return {
        "source": source["source"],
        "source_path": source.get("source_path"),
        "declared": value_present or isinstance(availability, Mapping),
        "available": available,
        "availability": normalized_status,
        "reason": recorded_reason or (
            "explicit persisted metric value"
            if available
            else "metric absent or explicitly unavailable"
        ),
        "value": deepcopy(metrics.get(metric_name)) if value_present else None,
    }


def _preferred_unavailable_evidence(
    execution: Mapping[str, Any],
    replay: Mapping[str, Any],
) -> Mapping[str, Any]:
    for evidence in (execution, replay):
        if evidence["declared"] and evidence["availability"] == "not_applicable":
            return evidence
    for evidence in (execution, replay):
        if evidence["declared"]:
            return evidence
    return replay


def _frame_count_summary(
    replay: Mapping[str, Any],
    execution: Mapping[str, Any],
    *,
    persisted_frame_count: int | None,
    warmup_inclusive_frame_count: int | None,
) -> dict[str, Any]:
    persisted = _validated_frame_count(persisted_frame_count)
    persisted_source = "explicit_argument" if persisted is not None else None
    if persisted is None:
        persisted, persisted_source = _find_frame_count(
            replay,
            keys=("persisted_frame_count", "frame_count"),
            allow_clock=True,
        )
    if persisted is None:
        persisted, persisted_source = _find_frame_count(
            execution,
            keys=("persisted_frame_count", "frame_count"),
            allow_clock=True,
        )

    warmup_inclusive = _validated_frame_count(warmup_inclusive_frame_count)
    warmup_source = "explicit_argument" if warmup_inclusive is not None else None
    if warmup_inclusive is None:
        warmup_inclusive, warmup_source = _find_frame_count(
            execution,
            keys=("warmup_inclusive_frame_count",),
            allow_clock=False,
        )

    return {
        "persisted_frame_count": persisted,
        "warmup_inclusive_frame_count": warmup_inclusive,
        "frame_count_availability": {
            "persisted_frame_count": {
                "status": "available" if persisted is not None else "unavailable",
                "source": persisted_source,
            },
            "warmup_inclusive_frame_count": {
                "status": "available" if warmup_inclusive is not None else "unavailable",
                "source": warmup_source,
            },
        },
    }


def _find_frame_count(
    source: Mapping[str, Any],
    *,
    keys: tuple[str, ...],
    allow_clock: bool,
) -> tuple[int | None, str | None]:
    metrics = source["metrics"]
    metric_metadata = _mapping_copy(metrics.get("metadata"))
    top_metadata = source["top_metadata"]
    raw = source["raw"]
    candidates: list[tuple[Any, str]] = []
    for key in keys:
        candidates.extend(
            (
                (metrics.get(key), f"{source['source']}.metrics.{key}"),
                (metric_metadata.get(key), f"{source['source']}.metrics.metadata.{key}"),
                (top_metadata.get(key), f"{source['source']}.metadata.{key}"),
                (raw.get(key), f"{source['source']}.{key}"),
            )
        )
    if allow_clock:
        for metadata, prefix in (
            (metric_metadata, f"{source['source']}.metrics.metadata"),
            (top_metadata, f"{source['source']}.metadata"),
        ):
            clock = metadata.get("clock")
            if isinstance(clock, Mapping):
                candidates.append((clock.get("frame_count"), f"{prefix}.clock.frame_count"))

    for value, path in candidates:
        parsed = _validated_frame_count(value)
        if parsed is not None:
            return parsed, path
    return None, None


def _validated_frame_count(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _mapping_copy(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
