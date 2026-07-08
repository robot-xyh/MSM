"""Offline loaders for persisted main episode bus metrics JSON files."""

from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .metrics import EpisodeMetrics, _normalize_metric_scope


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

    return EpisodeMetrics(**values)


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
