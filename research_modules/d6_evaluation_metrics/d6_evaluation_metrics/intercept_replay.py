"""Adapters for evaluating persisted D7 intercept output files.

This module is offline-only. It reads already-written AirSim/D7
``control_commands.csv`` and ``intercept_summary.json`` files into D6
``EventRecord`` entries without importing AirSim or invoking vehicle APIs.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from .metrics import EventRecord, MetricsCollector


def load_d7_intercept_outputs(
    control_commands_path: str | Path | None = None,
    intercept_summary_path: str | Path | None = None,
) -> MetricsCollector:
    """Load D7 intercept outputs into a passive D6 collector."""

    if control_commands_path is None and intercept_summary_path is None:
        raise ValueError("at least one D7 intercept output path is required")

    collector = MetricsCollector()
    if intercept_summary_path is not None:
        _add_intercept_summary_events(collector, Path(intercept_summary_path))
    if control_commands_path is not None:
        _add_control_command_events(collector, Path(control_commands_path))
    return collector


def _add_intercept_summary_events(collector: MetricsCollector, path: Path) -> None:
    summary = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(summary, Mapping):
        raise ValueError(f"{path}: intercept summary must be a JSON object")

    collector.add_event(
        EventRecord(
            timestamp=0.0,
            event_type="d7_intercept_summary",
            actor_id="d7",
            metadata={
                "control_api_used": _optional_bool(summary.get("control_api_used")),
                "success_count": _optional_int(summary.get("success_count")),
                "pair_count": _optional_int(summary.get("pair_count")),
                "record_count": _optional_int(summary.get("record_count")),
                "parameters": summary.get("parameters", {}),
                "source_path": str(path),
            },
        )
    )

    for pair in summary.get("pairs", []) or []:
        if not isinstance(pair, Mapping):
            continue
        timestamp = (
            _optional_float(pair.get("time_to_intercept_s"))
            or _optional_float(pair.get("last_detection_s"))
            or 0.0
        )
        collector.add_event(
            EventRecord(
                timestamp=timestamp,
                event_type="d7_intercept_pair_summary",
                actor_id=_optional_text(pair.get("resource_id")),
                metadata={
                    "resource_id": _optional_text(pair.get("resource_id")),
                    "vehicle_name": _optional_text(pair.get("vehicle_name")),
                    "target_id": _optional_text(pair.get("target_id")),
                    "active": _optional_bool(pair.get("active")),
                    "status": _optional_text(pair.get("status")),
                    "abort_reason": _optional_text(pair.get("abort_reason")),
                    "min_range_m": _optional_float(pair.get("min_range_m")),
                    "time_to_intercept_s": _optional_float(pair.get("time_to_intercept_s")),
                    "last_detection_s": _optional_float(pair.get("last_detection_s")),
                    "terminal_locked": _optional_bool(pair.get("terminal_locked")),
                    "terminal_handover_pending": _optional_bool(
                        pair.get("terminal_handover_pending")
                    ),
                    "pair_terminal_switch_reject_reason": _optional_text(
                        pair.get("terminal_switch_reject_reason")
                    ),
                    "source_path": str(path),
                },
            )
        )


def _add_control_command_events(collector: MetricsCollector, path: Path) -> None:
    with path.open("r", newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            metadata = _control_command_metadata(row, source_path=path)
            collector.add_event(
                EventRecord(
                    timestamp=float(metadata.get("timestamp_s") or 0.0),
                    event_type="d7_control_command",
                    actor_id=_optional_text(metadata.get("resource_id")),
                    metadata=metadata,
                )
            )


def _control_command_metadata(row: Mapping[str, Any], *, source_path: Path) -> dict[str, Any]:
    camera_gate = _first_bool(row, "camera_quality_gate_passed", "camera_quality_gate_pass")
    los_gate = _first_bool(row, "los_quality_gate_passed", "los_quality_gate_pass")
    maneuver_gate = _first_bool(
        row,
        "maneuver_margin_gate_passed",
        "maneuver_margin_gate_pass",
    )

    metadata: dict[str, Any] = {
        "timestamp_s": _optional_float(row.get("timestamp_s")),
        "resource_id": _optional_text(row.get("resource_id")),
        "vehicle_name": _optional_text(row.get("vehicle_name")),
        "target_id": _optional_text(row.get("target_id")),
        "mode": _optional_text(row.get("mode")),
        "range_m": _optional_float(row.get("range_m")),
        "command_vx_mps": _optional_float(row.get("command_vx_mps")),
        "command_vy_mps": _optional_float(row.get("command_vy_mps")),
        "command_z_ned_m": _optional_float(row.get("command_z_ned_m")),
        "los_rate_radps": _optional_float(row.get("los_rate_radps")),
        "closing_speed_mps": _optional_float(row.get("closing_speed_mps")),
        "terminal_locked": _optional_bool(row.get("terminal_locked")),
        "terminal_handover_pending": _optional_bool(row.get("terminal_handover_pending")),
        "detection_seen": _optional_bool(row.get("detection_seen")),
        "guidance_law": _optional_text(row.get("guidance_law")),
        "terminal_switch_allowed": _optional_bool(row.get("terminal_switch_allowed")),
        "terminal_switch_reject_reason": _optional_text(
            row.get("terminal_switch_reject_reason")
        ),
        "bbox_area_ratio": _optional_float(row.get("bbox_area_ratio")),
        "los_rate_variance_radps2": _optional_float(row.get("los_rate_variance_radps2")),
        "ttc_s": _optional_float(row.get("ttc_s")),
        "maneuver_margin": _optional_float(row.get("maneuver_margin")),
        "control_saturated": _optional_bool(row.get("control_saturated")),
        "collision_seen": _optional_bool(row.get("collision_seen")),
        "collision_object_name": _optional_text(row.get("collision_object_name")),
        "status": _optional_text(row.get("status")),
        "abort_reason": _optional_text(row.get("abort_reason")),
        "source_path": str(source_path),
    }
    if camera_gate is not None:
        metadata["camera_quality_gate_pass"] = camera_gate
        metadata["camera_quality_gate_passed"] = camera_gate
    if los_gate is not None:
        metadata["los_quality_gate_pass"] = los_gate
        metadata["los_quality_gate_passed"] = los_gate
    if maneuver_gate is not None:
        metadata["maneuver_margin_gate_pass"] = maneuver_gate
        metadata["maneuver_margin_gate_passed"] = maneuver_gate
    return {key: value for key, value in metadata.items() if value is not None}


def _first_bool(row: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = _optional_bool(row.get(key))
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


def _optional_int(value: Any) -> int | None:
    number = _optional_float(value)
    return None if number is None else int(number)


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
