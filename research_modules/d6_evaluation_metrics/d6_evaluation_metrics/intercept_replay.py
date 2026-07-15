"""Adapters for evaluating persisted D7 intercept output files.

This module is offline-only. It reads already-written AirSim/D7
``guidance_records.csv``, ``guidance_summaries.json``,
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
    guidance_records_path: str | Path | None = None,
    guidance_summaries_path: str | Path | None = None,
) -> MetricsCollector:
    """Load D7 intercept outputs into a passive D6 collector."""

    return load_d7_guidance_timeseries(
        guidance_records_path=guidance_records_path,
        guidance_summaries_path=guidance_summaries_path,
        control_commands_path=control_commands_path,
        intercept_summary_path=intercept_summary_path,
    )


def load_d7_guidance_timeseries(
    guidance_records_path: str | Path | None = None,
    guidance_summaries_path: str | Path | None = None,
    control_commands_path: str | Path | None = None,
    intercept_summary_path: str | Path | None = None,
) -> MetricsCollector:
    """Load D7 guidance/intercept time-series outputs into a passive collector."""

    if (
        guidance_records_path is None
        and guidance_summaries_path is None
        and control_commands_path is None
        and intercept_summary_path is None
    ):
        raise ValueError("at least one D7 intercept output path is required")

    collector = MetricsCollector()
    if guidance_summaries_path is not None:
        _add_guidance_summary_events(collector, Path(guidance_summaries_path))
    if guidance_records_path is not None:
        _add_guidance_record_events(collector, Path(guidance_records_path))
    if intercept_summary_path is not None:
        _add_intercept_summary_events(collector, Path(intercept_summary_path))
    if control_commands_path is not None:
        _add_control_command_events(collector, Path(control_commands_path))
    return collector


def _add_guidance_summary_events(collector: MetricsCollector, path: Path) -> None:
    raw_summary = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw_summary, list):
        summary_items = raw_summary
        summary_metadata: Mapping[str, Any] = {}
    elif isinstance(raw_summary, Mapping):
        summary_metadata = raw_summary
        summary_items = (
            raw_summary.get("summaries")
            or raw_summary.get("guidance_summaries")
            or raw_summary.get("pairs")
            or raw_summary.get("records")
            or []
        )
    else:
        raise ValueError(f"{path}: guidance summary must be a JSON object or array")

    collector.add_event(
        EventRecord(
            timestamp=0.0,
            event_type="d7_guidance_summary",
            actor_id="d7",
            metadata={
                "record_count": len(summary_items) if isinstance(summary_items, list) else None,
                "plan_id": _optional_text(summary_metadata.get("plan_id")),
                "plan_version": _optional_int(summary_metadata.get("plan_version")),
                "d4_state": _optional_text(summary_metadata.get("d4_state")),
                "d5_state": _optional_text(summary_metadata.get("d5_state")),
                "source_path": str(path),
            },
        )
    )

    for item in summary_items or []:
        if not isinstance(item, Mapping):
            continue
        metadata = _guidance_summary_metadata(item, source_path=path)
        collector.add_event(
            EventRecord(
                timestamp=float(metadata.get("timestamp_s") or 0.0),
                event_type="d7_guidance_pair_summary",
                actor_id=_optional_text(metadata.get("resource_id")),
                metadata=metadata,
            )
        )


def _add_guidance_record_events(collector: MetricsCollector, path: Path) -> None:
    with path.open("r", newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            metadata = _guidance_record_metadata(row, source_path=path)
            collector.add_event(
                EventRecord(
                    timestamp=float(metadata.get("timestamp_s") or 0.0),
                    event_type="d7_guidance_record",
                    actor_id=_optional_text(metadata.get("resource_id")),
                    metadata=metadata,
                )
            )


def _add_intercept_summary_events(collector: MetricsCollector, path: Path) -> None:
    summary = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(summary, Mapping):
        raise ValueError(f"{path}: intercept summary must be a JSON object")

    parameters = summary.get("parameters", {})
    if not isinstance(parameters, Mapping):
        parameters = {}
    success_semantics = summary.get("success_semantics", {})
    if not isinstance(success_semantics, Mapping):
        success_semantics = {}

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
                "runtime_mode": _optional_text(
                    summary.get("runtime_mode")
                    or summary.get("sim_mode")
                    or parameters.get("runtime_mode")
                ),
                "physical_intercept_available": _optional_bool(
                    summary.get("physical_intercept_available")
                ),
                "physical_intercept_unavailable_reason": _optional_text(
                    summary.get("physical_intercept_unavailable_reason")
                    or summary.get("unavailable_reason")
                ),
                "physical_intercept_source": _optional_text(
                    summary.get("physical_intercept_source")
                ),
                "online_control_state_source": _optional_text(
                    summary.get("online_control_state_source")
                ),
                "intercept_radius_m": _optional_float(
                    parameters.get("intercept_radius_m")
                    or success_semantics.get("range_threshold_m")
                ),
                "intercept_distance_frame": _optional_text(
                    parameters.get("intercept_distance_frame")
                    or success_semantics.get("distance_frame")
                ),
                "intercept_distance_dimension": _optional_text(
                    parameters.get("intercept_distance_dimension")
                    or success_semantics.get("distance_dimension")
                ),
                "intercept_success_criteria_version": _optional_text(
                    parameters.get("intercept_success_criteria_version")
                    or success_semantics.get("criteria_version")
                ),
                "success_semantics": dict(success_semantics),
                "parameters": dict(parameters),
                **_summary_count_metadata(summary, success_semantics),
                **_summary_terminal_delivery_metadata(summary, success_semantics),
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
                    "assigned": _first_mapping_bool(
                        pair,
                        "assigned",
                        "assignment_active",
                    ),
                    "activation_state": _optional_text(pair.get("activation_state")),
                    "status": _optional_text(pair.get("status")),
                    "abort_reason": _optional_text(pair.get("abort_reason")),
                    "min_range_m": _optional_float(pair.get("min_range_m")),
                    "physical_min_range_m": _optional_float(
                        pair.get("physical_min_range_m")
                    ),
                    "physical_evidence_available": _optional_bool(
                        pair.get("physical_evidence_available")
                    ),
                    "physical_intercept_time_s": _optional_float(
                        pair.get("physical_intercept_time_s")
                    ),
                    "time_to_intercept_s": _optional_float(pair.get("time_to_intercept_s")),
                    "last_detection_s": _optional_float(pair.get("last_detection_s")),
                    "physical_success": _optional_bool(pair.get("physical_success")),
                    "truth_identity_online_use": _first_mapping_bool(
                        pair,
                        "truth_identity_online_use",
                        "online_truth_id_used",
                    ),
                    "truth_state_online_use": _first_mapping_bool(
                        pair,
                        "truth_state_online_use",
                        "online_truth_state_used",
                    ),
                    "target_state_source": _optional_text(
                        pair.get("target_state_source")
                    ),
                    "member_role": _optional_text(pair.get("member_role")),
                    "required_primary": _optional_bool(pair.get("required_primary")),
                    "required_primary_count": _first_mapping_int(
                        pair,
                        "required_primary_count",
                        "required_resource_count",
                    ),
                    "arrival_coordination_required": _first_mapping_bool(
                        pair,
                        "arrival_coordination_required",
                    ),
                    "arrival_window": pair.get("arrival_window"),
                    "arrival_window_start_s": _first_mapping_float(
                        pair,
                        "arrival_window_start_s",
                        "arrival_window_start",
                    ),
                    "arrival_window_end_s": _first_mapping_float(
                        pair,
                        "arrival_window_end_s",
                        "arrival_window_end",
                    ),
                    "arrival_timestamp_s": _first_mapping_float(
                        pair,
                        "arrival_timestamp_s",
                        "arrival_timestamp",
                        "time_to_intercept_s",
                    ),
                    "terminal_locked": _optional_bool(pair.get("terminal_locked")),
                    "terminal_mode_entered": _optional_bool(
                        pair.get("terminal_mode_entered")
                    ),
                    "terminal_handover_pending": _optional_bool(
                        pair.get("terminal_handover_pending")
                    ),
                    "guidance_law": _optional_text(pair.get("guidance_law")),
                    "mode": _optional_text(pair.get("mode") or pair.get("guidance_mode")),
                    "terminal_switch_reject_reason": _optional_text(
                        pair.get("terminal_switch_reject_reason")
                        or pair.get("gate_reject_reason")
                    ),
                    "pair_terminal_switch_reject_reason": _optional_text(
                        pair.get("terminal_switch_reject_reason")
                    ),
                    "terminal_contract_reject_reason": _optional_text(
                        pair.get("terminal_contract_reject_reason")
                    ),
                    "plan_id": _optional_text(pair.get("plan_id")),
                    "plan_version": _optional_int(pair.get("plan_version") or pair.get("version")),
                    "track_version": _optional_int(pair.get("track_version")),
                    "d4_state": _optional_text(pair.get("d4_state") or pair.get("d4_action")),
                    "d5_state": _optional_text(
                        pair.get("d5_state") or pair.get("d5_decision_state")
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


def _guidance_summary_metadata(
    item: Mapping[str, Any],
    *,
    source_path: Path,
) -> dict[str, Any]:
    episode_timestamp = _optional_float(item.get("episode_timestamp_s"))
    closest_time = _optional_float(item.get("closest_time_s"))
    timestamp = episode_timestamp if episode_timestamp is not None else closest_time
    mode_sequence = item.get("mode_sequence") or []
    if not isinstance(mode_sequence, list):
        mode_sequence = [mode_sequence]
    mode_sequence = [str(mode) for mode in mode_sequence if _optional_text(mode) is not None]
    metadata: dict[str, Any] = {
        "timestamp_s": timestamp,
        "resource_id": _optional_text(item.get("resource_id")),
        "target_id": _optional_text(item.get("target_id") or item.get("global_track_id")),
        "global_track_id": _optional_text(item.get("global_track_id")),
        "mode": mode_sequence[-1] if mode_sequence else _optional_text(item.get("mode")),
        "mode_sequence": mode_sequence,
        "mode_switch": len(set(mode_sequence)) > 1 if mode_sequence else None,
        "terminal_mode_entered": _optional_bool(item.get("terminal_mode_entered")),
        "terminal_contract_reject_reason": _optional_text(
            item.get("terminal_contract_reject_reason")
        ),
        "terminal_switch_reject_reason": _optional_text(
            item.get("terminal_switch_reject_reason")
        ),
        "d4_state": _optional_text(item.get("d4_state") or item.get("d4_mode")),
        "d5_state": _optional_text(item.get("d5_state") or item.get("terminal_state")),
        "plan_id": _optional_text(item.get("plan_id")),
        "plan_version": _optional_int(item.get("plan_version") or item.get("version")),
        "source": _optional_text(item.get("source")),
        "boundary": _optional_text(item.get("boundary")),
        "initial_range_m": _optional_float(item.get("initial_range_m")),
        "min_range_m": _optional_float(item.get("min_range_m")),
        "final_range_m": _optional_float(item.get("final_range_m")),
        "duration_s": _optional_float(item.get("duration_s")),
        "steps": _optional_int(item.get("steps")),
        "source_path": str(source_path),
    }
    return {key: value for key, value in metadata.items() if value is not None}


def _guidance_record_metadata(
    row: Mapping[str, Any],
    *,
    source_path: Path,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "timestamp_s": _first_float(row, "timestamp_s", "timestamp", "time_s"),
        "resource_id": _optional_text(row.get("resource_id")),
        "target_id": _optional_text(row.get("target_id") or row.get("global_track_id")),
        "global_track_id": _optional_text(row.get("global_track_id")),
        "mode": _optional_text(row.get("mode") or row.get("guidance_mode")),
        "mode_switch": _first_bool(row, "mode_switch", "mode_switched"),
        "terminal_contract_reject_reason": _optional_text(
            row.get("terminal_contract_reject_reason")
        ),
        "terminal_switch_reject_reason": _optional_text(
            row.get("terminal_switch_reject_reason")
        ),
        "d4_state": _optional_text(row.get("d4_state") or row.get("d4_mode")),
        "d5_state": _optional_text(row.get("d5_state") or row.get("terminal_state")),
        "plan_id": _optional_text(row.get("plan_id")),
        "plan_version": _optional_int(row.get("plan_version") or row.get("version")),
        "range_m": _optional_float(row.get("range_m")),
        "los_angle_rad": _optional_float(row.get("los_angle_rad")),
        "los_rate_radps": _optional_float(row.get("los_rate_radps")),
        "closing_speed_mps": _optional_float(row.get("closing_speed_mps")),
        "commanded_lateral_accel_mps2": _optional_float(
            row.get("commanded_lateral_accel_mps2")
        ),
        "limited_lateral_accel_mps2": _optional_float(
            row.get("limited_lateral_accel_mps2")
        ),
        "limited_turn_rate_radps": _optional_float(row.get("limited_turn_rate_radps")),
        "guidance_law": _optional_text(row.get("guidance_law")),
        **_terminal_delivery_metadata(row),
        "source_path": str(source_path),
    }
    return {key: value for key, value in metadata.items() if value is not None}


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
        "mode_switch": _first_bool(row, "mode_switch", "mode_switched"),
        "range_m": _optional_float(row.get("range_m")),
        "command_vx_mps": _optional_float(row.get("command_vx_mps")),
        "command_vy_mps": _optional_float(row.get("command_vy_mps")),
        "command_vz_mps": _optional_float(row.get("command_vz_mps")),
        "command_z_ned_m": _optional_float(row.get("command_z_ned_m")),
        "los_rate_radps": _optional_float(row.get("los_rate_radps")),
        "closing_speed_mps": _optional_float(row.get("closing_speed_mps")),
        "terminal_locked": _optional_bool(row.get("terminal_locked")),
        "terminal_mode_entered": _optional_bool(row.get("terminal_mode_entered")),
        "terminal_handover_pending": _optional_bool(row.get("terminal_handover_pending")),
        "detection_seen": _optional_bool(row.get("detection_seen")),
        "image_kf_mode": _optional_text(row.get("image_kf_mode")),
        "image_kf_predict": _optional_bool(row.get("image_kf_predict")),
        "los_source": _optional_text(row.get("los_source")),
        "using_blind_push": _first_bool(row, "using_blind_push", "blind_push"),
        "blind_push": _optional_bool(row.get("blind_push")),
        "visual_reacquisition": _optional_bool(row.get("visual_reacquisition")),
        "terminal_visual_lost_after_coast": _optional_bool(
            row.get("terminal_visual_lost_after_coast")
        ),
        "truth_identity_online_use": _first_bool(
            row,
            "truth_identity_online_use",
            "online_truth_identity_used",
            "truth_id_used_online",
        ),
        "truth_state_online_use": _first_bool(
            row,
            "truth_state_online_use",
            "online_truth_state_used",
            "truth_state_used_online",
        ),
        "target_state_source": _optional_text(row.get("target_state_source")),
        "target_state_valid_at_s": _optional_float(row.get("target_state_valid_at_s")),
        "target_measurement_timestamp_s": _optional_float(
            row.get("target_measurement_timestamp_s")
        ),
        "target_arrival_timestamp_s": _optional_float(
            row.get("target_arrival_timestamp_s")
        ),
        "target_measurement_age_s": _optional_float(
            row.get("target_measurement_age_s")
        ),
        "target_state_stale": _optional_bool(row.get("target_state_stale")),
        "contract_allowed": _first_bool(
            row,
            "contract_allowed",
            "terminal_contract_allowed",
        ),
        "control_allowed": _first_bool(
            row,
            "control_allowed",
            "terminal_control_allowed",
            "d7_runtime_terminal_switch_allowed",
        ),
        "guidance_law": _optional_text(row.get("guidance_law")),
        "terminal_switch_allowed": _optional_bool(row.get("terminal_switch_allowed")),
        "terminal_switch_reject_reason": _optional_text(
            row.get("terminal_switch_reject_reason") or row.get("gate_reject_reason")
        ),
        "terminal_contract_reject_reason": _optional_text(
            row.get("terminal_contract_reject_reason")
        ),
        "degradation_mode": _optional_text(row.get("d4_mode") or row.get("degradation_mode")),
        "action": _optional_text(row.get("d4_action") or row.get("action")),
        "assignment_phase": _optional_text(row.get("assignment_phase")),
        "target_node_id": _optional_text(row.get("d4_target_node_id") or row.get("target_node_id")),
        "d4_state": _optional_text(
            row.get("d4_state") or row.get("d4_mode") or row.get("d4_action")
        ),
        "d5_state": _optional_text(
            row.get("d5_state")
            or row.get("terminal_state")
            or row.get("d5_decision_state")
        ),
        "plan_id": _optional_text(row.get("plan_id")),
        "plan_version": _optional_int(row.get("plan_version") or row.get("version")),
        "track_version": _optional_int(row.get("track_version")),
        "bbox_area_ratio": _optional_float(row.get("bbox_area_ratio")),
        "los_rate_variance_radps2": _optional_float(row.get("los_rate_variance_radps2")),
        "ttc_s": _optional_float(row.get("ttc_s")),
        "maneuver_margin": _optional_float(row.get("maneuver_margin")),
        "control_saturated": _optional_bool(row.get("control_saturated")),
        "collision_seen": _optional_bool(row.get("collision_seen")),
        "physical_intercept": _optional_bool(row.get("physical_intercept")),
        "physical_evidence_available": _optional_bool(
            row.get("physical_evidence_available")
        ),
        "collision_object_name": _optional_text(row.get("collision_object_name")),
        "status": _optional_text(row.get("status")),
        "abort_reason": _optional_text(row.get("abort_reason")),
        **_terminal_delivery_metadata(row),
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


def _summary_count_metadata(
    summary: Mapping[str, Any],
    success_semantics: Mapping[str, Any],
) -> dict[str, Any]:
    keys = (
        "pair_physical_success_count",
        "pair_physical_opportunity_count",
        "target_intercept_success_count",
        "target_intercept_opportunity_count",
        "coalition_completion_count",
        "coalition_opportunity_count",
        "detection_acquisition_timeout_count",
        "image_kf_predict_count",
        "blind_push_count",
        "visual_reacquisition_count",
        "terminal_visual_lost_after_coast_count",
        "truth_identity_online_use_count",
        "truth_state_online_use_count",
        "terminal_filter_measured_count",
        "terminal_filter_predicted_count",
        "terminal_filter_innovation_rejected_count",
        "terminal_filter_reset_count",
        "terminal_filter_expired_count",
        "ttc_area_jump_reject_count",
        "ttc_bbox_clipping_reject_count",
        "ttc_not_expanding_reject_count",
        "ttc_out_of_range_reject_count",
        "soft_prediction_count",
        "soft_prediction_expired_count",
        "terminal_coast_count",
        "terminal_coast_expired_count",
    )
    metadata: dict[str, Any] = {}
    for key in keys:
        value = summary.get(key, success_semantics.get(key))
        parsed = _optional_int(value)
        if parsed is not None:
            metadata[key] = parsed
    arrival_window_enforced = _optional_bool(
        summary.get(
            "coalition_arrival_window_enforced",
            success_semantics.get("coalition_arrival_window_enforced"),
        )
    )
    if arrival_window_enforced is not None:
        metadata["coalition_arrival_window_enforced"] = arrival_window_enforced
    arrival_coordination_required = _optional_bool(
        summary.get(
            "arrival_coordination_required",
            success_semantics.get("arrival_coordination_required"),
        )
    )
    if arrival_coordination_required is not None:
        metadata["arrival_coordination_required"] = arrival_coordination_required
    return metadata


def _terminal_delivery_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    """Parse optional D7 delivery diagnostics without requiring a new schema."""

    metadata: dict[str, Any] = {
        "local_track_id": _optional_text(row.get("local_track_id")),
        "terminal_filter_state": _optional_text(row.get("terminal_filter_state")),
        "terminal_filter_reason": _optional_text(row.get("terminal_filter_reason")),
        "terminal_filter_innovation_rejected": _first_bool(
            row,
            "terminal_filter_innovation_rejected",
            "innovation_rejected",
        ),
        "terminal_filter_reset": _first_bool(
            row,
            "terminal_filter_reset",
            "image_kf_reset",
            "filter_reset",
        ),
        "terminal_filter_reset_reason": _optional_text(
            row.get("terminal_filter_reset_reason")
            or row.get("image_kf_reset_reason")
        ),
        "terminal_delivery_state": _optional_text(row.get("terminal_delivery_state")),
        "terminal_delivery_reason": _optional_text(row.get("terminal_delivery_reason")),
        "terminal_prediction_age_s": _first_float(
            row,
            "terminal_prediction_age_s",
            "prediction_age_s",
        ),
        "terminal_blind_elapsed_s": _first_float(
            row,
            "terminal_blind_elapsed_s",
            "blind_elapsed_s",
        ),
        "terminal_using_extrapolation": _optional_bool(
            row.get("terminal_using_extrapolation")
        ),
        "ttc_reject_reason": _optional_text(row.get("ttc_reject_reason")),
        "ttc_area_reject_reason": _optional_text(row.get("ttc_area_reject_reason")),
        "ttc_area_jump_rejected": _first_bool(
            row,
            "ttc_area_jump_rejected",
            "area_jump_rejected",
        ),
        "ttc_bbox_clipping_rejected": _first_bool(
            row,
            "ttc_bbox_clipping_rejected",
            "bbox_clipping_rejected",
        ),
        "ttc_not_expanding_rejected": _first_bool(
            row,
            "ttc_not_expanding_rejected",
            "not_expanding_rejected",
        ),
        "ttc_out_of_range_rejected": _first_bool(
            row,
            "ttc_out_of_range_rejected",
            "ttc_range_rejected",
        ),
        "soft_prediction_active": _first_bool(
            row,
            "soft_prediction_active",
            "terminal_soft_prediction",
            "innovation_soft_prediction",
        ),
        "soft_prediction_elapsed_s": _first_float(
            row,
            "soft_prediction_elapsed_s",
            "terminal_soft_prediction_elapsed_s",
        ),
        "soft_prediction_expired": _first_bool(
            row,
            "soft_prediction_expired",
            "terminal_soft_prediction_expired",
        ),
        "terminal_coast_active": _first_bool(
            row,
            "terminal_coast_active",
            "using_blind_push",
            "blind_push",
        ),
        "terminal_coast_elapsed_s": _first_float(
            row,
            "terminal_coast_elapsed_s",
            "coast_elapsed_s",
        ),
        "terminal_coast_expired": _first_bool(
            row,
            "terminal_coast_expired",
            "coast_expired",
        ),
        "visual_mode_active": _optional_bool(row.get("visual_mode_active")),
        "visual_mode_elapsed_s": _first_float(
            row,
            "visual_mode_elapsed_s",
            "terminal_mode_elapsed_s",
        ),
        "command_discontinuity_mps": _first_float(
            row,
            "command_discontinuity_mps",
            "velocity_command_step_mps",
        ),
        "terminal_delivery_profile": _optional_text(
            row.get("terminal_delivery_profile")
        ),
        "comparison_role": _optional_text(row.get("comparison_role")),
        "algorithm_variant": _optional_text(row.get("algorithm_variant")),
    }
    return {key: value for key, value in metadata.items() if value is not None}


def _summary_terminal_delivery_metadata(
    summary: Mapping[str, Any],
    success_semantics: Mapping[str, Any],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in (
        "soft_prediction_duration_s",
        "terminal_coast_duration_s",
        "terminal_lock_continuity",
        "visual_mode_duration_s",
        "command_discontinuity_mean_mps",
        "command_discontinuity_max_mps",
    ):
        value = summary.get(key, success_semantics.get(key))
        parsed = _optional_float(value)
        if parsed is not None:
            metadata[key] = parsed
    for key in ("terminal_delivery_profile", "comparison_role", "algorithm_variant"):
        value = summary.get(key, success_semantics.get(key))
        parsed = _optional_text(value)
        if parsed is not None:
            metadata[key] = parsed
    return metadata


def _first_float(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _optional_float(row.get(key))
        if value is not None:
            return value
    return None


def _first_bool(row: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = _optional_bool(row.get(key))
        if value is not None:
            return value
    return None


def _first_mapping_float(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in row:
            value = _optional_float(row.get(key))
            if value is not None:
                return value
    return None


def _first_mapping_int(row: Mapping[str, Any], *keys: str) -> int | None:
    value = _first_mapping_float(row, *keys)
    return None if value is None else int(value)


def _first_mapping_bool(row: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key in row:
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
