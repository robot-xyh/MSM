"""Adapters for evaluating persisted D4 degradation output files."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Mapping

from .metrics import EventRecord, MetricsCollector


def load_d4_active_degradation_decisions(
    active_degradation_decisions_path: str | Path,
) -> MetricsCollector:
    """Load D4 active-degradation decisions into a passive D6 collector."""

    collector = MetricsCollector()
    _add_active_degradation_decision_events(
        collector,
        Path(active_degradation_decisions_path),
    )
    return collector


def _add_active_degradation_decision_events(
    collector: MetricsCollector,
    path: Path,
) -> None:
    with path.open("r", newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            metadata = _active_degradation_metadata(row, source_path=path)
            collector.add_event(
                EventRecord(
                    timestamp=float(metadata.get("timestamp_s") or 0.0),
                    event_type="d4_active_degradation_decision",
                    actor_id=_optional_text(metadata.get("resource_id")),
                    metadata=metadata,
                )
            )


def _active_degradation_metadata(
    row: Mapping[str, Any],
    *,
    source_path: Path,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "timestamp_s": _first_float(row, "timestamp_s", "timestamp", "time_s"),
        "resource_id": _optional_text(row.get("resource_id")),
        "global_track_id": _optional_text(row.get("global_track_id")),
        "target_id": _optional_text(row.get("target_id") or row.get("global_track_id")),
        "mode": _optional_text(row.get("mode") or row.get("degradation_mode")),
        "action": _optional_text(row.get("action")),
        "trigger_reason": _optional_text(
            row.get("trigger_reason") or row.get("reason") or row.get("failover_reason")
        ),
        "review_label": _optional_text(
            row.get("review_label")
            or row.get("active_degradation_review_label")
            or row.get("degradation_review_label")
        ),
        "active_degradation_necessary": _optional_bool(
            row.get("active_degradation_necessary")
            or row.get("degradation_necessary")
            or row.get("was_necessary")
        ),
        "post_window_outcome": _optional_text(
            row.get("post_window_outcome")
            or row.get("post_active_outcome")
            or row.get("review_outcome")
        ),
        "trigger_timestamp_s": _first_float(
            row,
            "trigger_timestamp_s",
            "trigger_timestamp",
            "trigger_time_s",
        ),
        "decision_timestamp_s": _first_float(
            row,
            "decision_timestamp_s",
            "decision_timestamp",
            "decision_time_s",
        ),
        "selected_coordinator": _optional_text(
            row.get("selected_coordinator")
            or row.get("selected_coordinator_id")
            or row.get("coordinator_id")
        ),
        "coverage_cell": _optional_text(row.get("coverage_cell")),
        "target_node_id": _optional_text(row.get("target_node_id")),
        "terminal_consistent": _optional_bool(row.get("terminal_consistent")),
        "risk_factors": _split_text(row.get("risk_factors")),
        "risk_reduction": _first_float(
            row,
            "risk_reduction",
            "risk_reduction_score",
            "post_window_risk_reduction",
        ),
        "pre_window_risk_score": _first_float(
            row,
            "pre_window_risk_score",
            "pre_active_risk_score",
            "risk_score_before",
        ),
        "post_window_risk_score": _first_float(
            row,
            "post_window_risk_score",
            "post_active_risk_score",
            "risk_score_after",
        ),
        "fallback_type": _optional_text(row.get("fallback_type")),
        "pre_window_start_s": _first_float(
            row,
            "pre_window_start_s",
            "pre_window_start",
        ),
        "pre_window_end_s": _first_float(row, "pre_window_end_s", "pre_window_end"),
        "post_window_start_s": _first_float(
            row,
            "post_window_start_s",
            "post_window_start",
        ),
        "post_window_end_s": _first_float(row, "post_window_end_s", "post_window_end"),
        "active_window_start_s": _first_float(
            row,
            "active_window_start_s",
            "active_window_start",
        ),
        "active_window_end_s": _first_float(row, "active_window_end_s", "active_window_end"),
        "failover_timestamp_s": _first_float(
            row,
            "failover_timestamp_s",
            "takeover_timestamp_s",
            "failover_timestamp",
            "takeover_timestamp",
        ),
        "failover_active_window_delta_s": _first_float(
            row,
            "failover_active_window_delta_s",
            "active_window_delta_s",
            "failover_window_delta_s",
        ),
        "source_path": str(source_path),
    }
    return {key: value for key, value in metadata.items() if value not in (None, [])}


def _first_float(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _optional_float(row.get(key))
        if value is not None:
            return value
    return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    text = _optional_text(value)
    if text is None:
        return None
    return float(text)


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _optional_text(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in {"true", "t", "yes", "y", "1", "pass", "passed", "ok"}:
        return True
    if lowered in {"false", "f", "no", "n", "0", "fail", "failed", "reject", "rejected"}:
        return False
    return None


def _split_text(value: Any) -> list[str]:
    text = _optional_text(value)
    if text is None:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]
