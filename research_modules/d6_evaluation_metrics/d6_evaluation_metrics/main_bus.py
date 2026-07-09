"""Offline loaders for persisted main episode bus metrics JSON files."""

from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .metrics import EpisodeMetrics, _normalize_metric_scope
from .standard_mapping import (
    STANDARD_MAPPING_VERSION,
    standard_mapping_summary,
    standard_metric_families,
    standard_metric_family_summary as _standard_metric_family_summary,
)


def load_main_episode_bus_metrics(path: str | Path) -> EpisodeMetrics:
    """Load one persisted main episode bus metrics JSON file.

    The AirSim runtime writes both ``main_episode_bus_metrics.json`` and
    ``main_episode_bus_contract_metrics.json`` as already-computed D6 metrics.
    This loader keeps D6 offline-only by reading those JSON files directly and
    converting the ``metrics`` payload back to an ``EpisodeMetrics`` instance.
    """

    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path}: main episode bus metrics must be a JSON object")

    metrics_payload = raw.get("metrics", raw)
    if not isinstance(metrics_payload, Mapping):
        raise ValueError(f"{path}: metrics payload must be a JSON object")

    values = _episode_metric_values(metrics_payload)
    values.setdefault("episode_id", _episode_id_from_payload(metrics_payload, path))
    mission_outcome_missing = "mission_outcome" not in values
    eval_priority_missing = "eval_priority" not in values
    implementation_status_missing = "implementation_status" not in values
    evidence_path_missing = "evidence_path" not in values
    scenario_version_missing = "scenario_version" not in values
    standard_mapping_version_missing = "standard_mapping_version" not in values
    standard_family_summary_missing = "standard_metric_family_summary" not in values

    metric_scope = _normalize_metric_scope(values.get("metric_scope"))
    if metric_scope == "not_recorded":
        values["metric_scope"] = _metric_scope_from_payload_or_path(
            metrics_payload,
            path,
        )
    else:
        values["metric_scope"] = metric_scope

    raw_metadata = metrics_payload.get("metadata", {})
    metadata = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
    top_level_metadata = raw.get("metadata")
    if isinstance(top_level_metadata, Mapping):
        metadata.setdefault("main_bus_file_metadata", dict(top_level_metadata))
    metadata.setdefault("source_path", str(path))
    values["metadata"] = metadata

    metrics = EpisodeMetrics(**values)
    if mission_outcome_missing:
        _backfill_mission_status(metrics)
    if eval_priority_missing:
        metrics.eval_priority = str(metadata.get("eval_priority") or "P0")
    if implementation_status_missing:
        metrics.implementation_status = str(
            metadata.get("implementation_status") or "implemented"
        )
    if evidence_path_missing:
        metrics.evidence_path = str(metadata.get("evidence_path") or path)
    if scenario_version_missing:
        metrics.scenario_version = str(metadata.get("scenario_version") or "")
    if standard_mapping_version_missing:
        metrics.standard_mapping_version = str(
            metadata.get("standard_mapping_version") or STANDARD_MAPPING_VERSION
        )
    else:
        metrics.standard_mapping_version = str(
            metrics.standard_mapping_version or STANDARD_MAPPING_VERSION
        )
    if standard_family_summary_missing:
        metrics.standard_metric_family_summary = str(
            metadata.get("standard_metric_family_summary")
            or _standard_metric_family_summary()
        )
    metrics.metadata.setdefault("mission_outcome", metrics.mission_outcome)
    metrics.metadata.setdefault("success_reason", metrics.success_reason)
    metrics.metadata.setdefault("failure_reason", metrics.failure_reason)
    metrics.metadata.setdefault("eval_priority", metrics.eval_priority)
    metrics.metadata.setdefault("implementation_status", metrics.implementation_status)
    metrics.metadata.setdefault("evidence_path", metrics.evidence_path)
    metrics.metadata.setdefault("scenario_version", metrics.scenario_version)
    metrics.metadata.setdefault(
        "standard_mapping_version",
        metrics.standard_mapping_version,
    )
    metrics.metadata.setdefault("standard_metric_families", standard_metric_families())
    metrics.metadata.setdefault(
        "standard_metric_family_summary",
        metrics.standard_metric_family_summary,
    )
    metrics.metadata.setdefault("standard_mapping", standard_mapping_summary())
    return metrics


def load_main_episode_bus_metric_files(
    paths: Iterable[str | Path],
) -> list[EpisodeMetrics]:
    """Load multiple main episode bus metrics files for batch reports."""

    return [load_main_episode_bus_metrics(path) for path in paths]


def _episode_metric_values(payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {field.name for field in fields(EpisodeMetrics)}
    return {key: value for key, value in payload.items() if key in allowed}


def _episode_id_from_payload(payload: Mapping[str, Any], path: Path) -> str:
    episode_id = payload.get("episode_id")
    if episode_id is not None and str(episode_id).strip():
        return str(episode_id)
    return path.parent.name or path.stem


def _metric_scope_from_payload_or_path(
    payload: Mapping[str, Any],
    path: Path,
) -> str:
    for key in (
        "metric_scope",
        "metrics_scope",
        "evaluation_scope",
        "metrics_kind",
        "source_scope",
        "source_path",
        "metrics_path",
        "metrics_file",
    ):
        value = payload.get(key)
        if value is None:
            continue
        scope = _normalize_metric_scope(value)
        if scope != "not_recorded":
            return scope
    return _normalize_metric_scope(path.name)


def _backfill_mission_status(metrics: EpisodeMetrics) -> None:
    required_success_count = int(metrics.target_count or 0)
    if required_success_count <= 0 and metrics.intercept_success_count > 0:
        required_success_count = int(metrics.intercept_success_count)

    if (
        required_success_count > 0
        and metrics.intercept_success_count >= required_success_count
        and metrics.constraint_violation_count == 0
        and metrics.human_override_count == 0
    ):
        metrics.mission_outcome = "success"
        metrics.success_reason = (
            "intercept_success_count="
            f"{metrics.intercept_success_count}/{required_success_count}"
        )
        return

    if metrics.intercept_success_count > 0:
        metrics.mission_outcome = "partial"
        metrics.success_reason = (
            "partial_intercept_success_count="
            f"{metrics.intercept_success_count}/{required_success_count or 'unknown'}"
        )
        metrics.failure_reason = "not_all_required_intercepts_confirmed"
        return

    metrics.mission_outcome = "failed"
    metrics.failure_reason = "no_success_evidence"
